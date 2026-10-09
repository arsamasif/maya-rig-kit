"""Numerical tests for rig_kit.ikfk.

The core check is a round trip: solve an IK pose, convert it to FK
rotations, rebuild the joints with forward kinematics and compare. The
reverse direction checks that the pole vector solves back to the same knee.

"""

import random

import pytest

from rig_kit import ikfk
from rig_kit import vecmath

UPPER, LOWER = 3.0, 2.5


def assert_vec_close(a, b, tol=1e-7):
    assert vecmath.distance(a, b) < tol, (a, b)


def assert_mat_close(a, b, tol=1e-9):
    for row_a, row_b in zip(a, b):
        assert_vec_close(row_a, row_b, tol)


def _random_pose(rng):
    """Return (root, target, pole) for a reachable, non-degenerate limb."""
    root = tuple(rng.uniform(-5, 5) for _ in range(3))
    direction = vecmath.normalize(tuple(rng.uniform(-1, 1) for _ in range(3)))
    reach = rng.uniform(1.0, UPPER + LOWER - 0.2)
    target = vecmath.add(root, vecmath.scale(direction, reach))
    side = vecmath.reject(tuple(rng.uniform(-1, 1) for _ in range(3)), direction)
    pole = vecmath.add(root, vecmath.scale(vecmath.normalize(side), 4.0))
    return root, target, pole


def test_solve_two_bone_keeps_bone_lengths():
    rng = random.Random(1)
    for _ in range(50):
        root, target, pole = _random_pose(rng)
        mid = ikfk.solve_two_bone(root, target, pole, UPPER, LOWER)
        assert vecmath.distance(root, mid) == pytest.approx(UPPER)
        assert vecmath.distance(mid, target) == pytest.approx(LOWER)


def test_solve_two_bone_bends_toward_pole():
    mid = ikfk.solve_two_bone((0, 0, 0), (0, -4, 0), (0, -2, 5), UPPER, LOWER)
    assert mid[2] > 0
    assert mid[0] == pytest.approx(0.0)


def test_solve_two_bone_clamps_unreachable_target():
    mid = ikfk.solve_two_bone((0, 0, 0), (0, -20, 0), (0, 0, 1), UPPER, LOWER)
    assert_vec_close(mid, (0, -UPPER, 0))


@pytest.mark.parametrize("aim_axis, up_axis", [("x", "y"), ("x", "-z"), ("-x", "y")])
def test_ik_to_fk_round_trip(aim_axis, up_axis):
    rng = random.Random(7)
    for _ in range(50):
        root, target, pole = _random_pose(rng)
        mid = ikfk.solve_two_bone(root, target, pole, UPPER, LOWER)
        end_rotation = vecmath.matrix_from_euler((10, 20, 30))
        fk = ikfk.fk_from_ik(root, mid, target, end_rotation, aim_axis, up_axis)
        _, fk_mid, fk_end = ikfk.chain_positions(
            root, fk.upper, fk.lower, UPPER, LOWER, aim_axis
        )
        assert_vec_close(fk_mid, mid)
        assert_vec_close(fk_end, target)
        assert_mat_close(fk.end, end_rotation)


def test_fk_frames_share_the_bend_plane():
    root, mid, end = (0, 0, 0), (0, -3, 1), (0, -5, 0)
    fk = ikfk.fk_from_ik(root, mid, end, vecmath.IDENTITY, "x", "y")
    normal = ikfk.bend_normal(root, mid, end)
    # The third axis of both frames is the bend normal (up to sign).
    assert abs(vecmath.dot(fk.upper[2], normal)) == pytest.approx(1.0)
    assert vecmath.dot(fk.upper[2], fk.lower[2]) == pytest.approx(1.0)


def test_fk_to_ik_pole_solves_back_to_same_mid():
    rng = random.Random(3)
    for _ in range(50):
        root, target, pole = _random_pose(rng)
        mid = ikfk.solve_two_bone(root, target, pole, UPPER, LOWER)
        ik = ikfk.ik_from_fk(root, mid, target, vecmath.IDENTITY)
        assert_vec_close(ik.handle_position, target)
        solved = ikfk.solve_two_bone(root, ik.handle_position, ik.pole_position, UPPER, LOWER)
        assert_vec_close(solved, mid, 1e-6)


def test_pole_vector_distance_defaults_to_half_chain():
    root, mid, end = (0, 0, 0), (0, -3, 1), (0, -5, 0)
    pole = ikfk.pole_vector_position(root, mid, end)
    chain = vecmath.distance(root, mid) + vecmath.distance(mid, end)
    assert vecmath.distance(pole, mid) == pytest.approx(chain * 0.5)
    assert pole[2] > mid[2]


def test_straight_limb_needs_fallback():
    root, mid, end = (0, 0, 0), (0, -3, 0), (0, -6, 0)
    with pytest.raises(ValueError, match="straight"):
        ikfk.pole_vector_position(root, mid, end)
    pole = ikfk.pole_vector_position(root, mid, end, distance=2.0, fallback=(0, 0, 1))
    assert_vec_close(pole, (0, -3, 2))


def test_local_rotation_inverts_parent():
    parent = vecmath.matrix_from_euler((30, -10, 45))
    child = vecmath.matrix_from_euler((5, 60, -20))
    local = ikfk.local_rotation(child, parent)
    assert_mat_close(vecmath.mat_mul(local, parent), child)


def test_bad_bone_lengths_raise():
    with pytest.raises(ValueError, match="positive"):
        ikfk.solve_two_bone((0, 0, 0), (1, 0, 0), (0, 1, 0), 0.0, 1.0)
