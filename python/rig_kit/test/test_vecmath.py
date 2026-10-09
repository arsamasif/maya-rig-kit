"""Tests for rig_kit.vecmath.

Checks Euler round trips for every Maya rotate order, gimbal lock handling
and the aim/up frame builder.

"""

import itertools
import math
import random

import pytest

from rig_kit import vecmath


def assert_vec_close(a, b, tol=1e-9):
    assert all(abs(x - y) < tol for x, y in zip(a, b)), (a, b)


def assert_mat_close(a, b, tol=1e-9):
    for row_a, row_b in zip(a, b):
        assert_vec_close(row_a, row_b, tol)


def test_basic_vector_ops():
    assert vecmath.cross((1, 0, 0), (0, 1, 0)) == (0, 0, 1)
    assert vecmath.dot((1, 2, 3), (4, 5, 6)) == 32
    assert vecmath.length(vecmath.normalize((3, 4, 0))) == pytest.approx(1.0)
    assert vecmath.reject((1, 1, 0), (1, 0, 0)) == (0, 1, 0)


def test_normalize_zero_raises():
    with pytest.raises(ValueError):
        vecmath.normalize((0, 0, 0))


def test_rotation_about_z_moves_x_to_y():
    m = vecmath.matrix_from_euler((0, 0, 90))
    assert_vec_close(vecmath.vec_mat_mul((1, 0, 0), m), (0, 1, 0))


def test_rotate_order_xyz_applies_x_first():
    m = vecmath.matrix_from_euler((90, 0, 90), "xyz")
    # X first: Y axis -> Z, then Z about Z stays Z.
    assert_vec_close(vecmath.vec_mat_mul((0, 1, 0), m), (0, 0, 1))


@pytest.mark.parametrize("order", vecmath.ROTATE_ORDERS)
def test_euler_round_trip_all_orders(order):
    rng = random.Random(order)
    for _ in range(50):
        angles = tuple(rng.uniform(-170, 170) for _ in range(3))
        matrix = vecmath.matrix_from_euler(angles, order)
        recovered = vecmath.euler_from_matrix(matrix, order)
        assert_mat_close(vecmath.matrix_from_euler(recovered, order), matrix, 1e-9)


@pytest.mark.parametrize("order, middle", list(itertools.product(vecmath.ROTATE_ORDERS, (90, -90))))
def test_euler_gimbal_lock_rebuilds_same_matrix(order, middle):
    angles = [0.0, 0.0, 0.0]
    angles[vecmath.parse_axis(order[0])[1]] = 25.0
    angles[vecmath.parse_axis(order[1])[1]] = middle
    angles[vecmath.parse_axis(order[2])[1]] = -40.0
    matrix = vecmath.matrix_from_euler(angles, order)
    recovered = vecmath.euler_from_matrix(matrix, order)
    assert_mat_close(vecmath.matrix_from_euler(recovered, order), matrix, 1e-7)


def test_unknown_rotate_order_raises():
    with pytest.raises(ValueError, match="rotate order"):
        vecmath.matrix_from_euler((0, 0, 0), "xxy")


@pytest.mark.parametrize("aim_axis, up_axis", [
    ("x", "y"), ("x", "z"), ("-x", "y"), ("y", "-z"), ("z", "x"),
])
def test_frame_from_axes_is_right_handed_and_aimed(aim_axis, up_axis):
    aim, up = (1.0, 2.0, 0.5), (0.0, 0.0, 1.0)
    frame = vecmath.frame_from_axes(aim, up, aim_axis, up_axis)
    sign, index = vecmath.parse_axis(aim_axis)
    assert_vec_close(vecmath.scale(frame[index], sign), vecmath.normalize(aim))
    assert vecmath.dot(vecmath.cross(frame[0], frame[1]), frame[2]) == pytest.approx(1.0)
    up_sign, up_index = vecmath.parse_axis(up_axis)
    assert vecmath.dot(vecmath.scale(frame[up_index], up_sign), up) > 0


def test_frame_from_parallel_vectors_raises():
    with pytest.raises(ValueError, match="parallel"):
        vecmath.frame_from_axes((1, 0, 0), (2, 0, 0))


def test_orthonormalize_strips_scale():
    scaled = ((2.0, 0.0, 0.0), (0.0, 3.0, 0.0), (0.0, 0.0, 0.5))
    assert_mat_close(vecmath.orthonormalize(scaled), vecmath.IDENTITY)


def test_compose_and_split_matrix_round_trip():
    rotation = vecmath.matrix_from_euler((10, 20, 30))
    flat = vecmath.compose_matrix(rotation, (1, 2, 3))
    rows, translation = vecmath.split_matrix(flat)
    assert_mat_close(rows, rotation)
    assert translation == (1, 2, 3)


def test_closest_euler_unwraps_turns():
    assert vecmath.closest_euler((-170.0, 10.0, 350.0), (180.0, 0.0, 0.0)) == (
        190.0, 10.0, -10.0
    )
    assert math.isclose(vecmath.closest_euler((720.0,), (0.0,))[0], 0.0)
