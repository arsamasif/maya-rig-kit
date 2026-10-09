"""IK/FK matching math for a two-bone limb.

Everything here works on world-space positions and 3x3 rotation matrices, so
it is independent of Maya and of any particular rig. The Maya adapter reads
the current limb pose, asks this module where the other half of the switch
should go, and writes the result back to the controls.

Two directions are supported:

* IK to FK: build an orientation frame for the upper and lower bone from the
  joint positions and the plane the limb bends in.
* FK to IK: place the IK handle on the end joint and find a pole vector
  position in the bend plane, pushed out from the middle joint.

"""

import math
from dataclasses import dataclass

from rig_kit import vecmath

DEFAULT_POLE_DISTANCE_FACTOR = 0.5


@dataclass(frozen=True)
class FkPose:
    """World orientations for the three FK controls of a limb.

    Attributes:
        upper (tuple): 3x3 world rotation of the upper bone control.
        lower (tuple): 3x3 world rotation of the lower bone control.
        end (tuple): 3x3 world rotation of the end (hand/foot) control.

    """

    upper: tuple
    lower: tuple
    end: tuple


@dataclass(frozen=True)
class IkPose:
    """World placement for the IK handle and pole vector controls.

    Attributes:
        handle_position (tuple): World position of the IK handle control.
        handle_rotation (tuple): 3x3 world rotation of the IK handle control.
        pole_position (tuple): World position of the pole vector control.

    """

    handle_position: tuple
    handle_rotation: tuple
    pole_position: tuple


def bend_normal(root, mid, end, fallback=None):
    """Return the unit normal of the plane a limb bends in.

    Args:
        root (tuple): World position of the root joint (shoulder/hip).
        mid (tuple): World position of the middle joint (elbow/knee).
        end (tuple): World position of the end joint (wrist/ankle).
        fallback (tuple): Normal to use when the limb is perfectly straight.

    Returns:
        tuple: Unit normal ``(mid - root) x (end - root)``.

    Raises:
        ValueError: If the limb is straight and no fallback was given.

    """
    normal = vecmath.cross(vecmath.sub(mid, root), vecmath.sub(end, root))
    if vecmath.length(normal) < vecmath.EPSILON:
        if fallback is None:
            raise ValueError("Limb is straight; pass a fallback bend normal.")
        return vecmath.normalize(fallback)
    return vecmath.normalize(normal)


def pole_direction(root, mid, end, fallback=None):
    """Return the unit direction from the limb's root-end line to the mid joint.

    Args:
        root (tuple): World position of the root joint.
        mid (tuple): World position of the middle joint.
        end (tuple): World position of the end joint.
        fallback (tuple): Direction to use when the limb is straight.

    Returns:
        tuple: Unit vector perpendicular to the root-end line.

    Raises:
        ValueError: If the limb is straight and no usable fallback was given.

    """
    axis = vecmath.normalize(vecmath.sub(end, root))
    offset = vecmath.reject(vecmath.sub(mid, root), axis)
    if vecmath.length(offset) < vecmath.EPSILON:
        if fallback is None:
            raise ValueError("Limb is straight; pass a fallback pole direction.")
        offset = vecmath.reject(fallback, axis)
    return vecmath.normalize(offset)


def pole_vector_position(root, mid, end, distance=None, fallback=None):
    """Place a pole vector control in the bend plane, out from the mid joint.

    Args:
        root (tuple): World position of the root joint.
        mid (tuple): World position of the middle joint.
        end (tuple): World position of the end joint.
        distance (float): Offset from the mid joint. Defaults to half the
            chain length.
        fallback (tuple): Pole direction used when the limb is straight.

    Returns:
        tuple: World position for the pole vector control.

    """
    if distance is None:
        chain = vecmath.distance(root, mid) + vecmath.distance(mid, end)
        distance = chain * DEFAULT_POLE_DISTANCE_FACTOR
    direction = pole_direction(root, mid, end, fallback=fallback)
    return vecmath.add(mid, vecmath.scale(direction, distance))


def solve_two_bone(root, target, pole, upper_length, lower_length):
    """Solve the middle joint position of a two-bone IK chain.

    Uses the law of cosines. Targets out of reach are clamped so the chain
    straightens toward the target instead of failing.

    Args:
        root (tuple): World position of the root joint.
        target (tuple): World position the end joint should reach.
        pole (tuple): World position of the pole vector.
        upper_length (float): Length of the upper bone.
        lower_length (float): Length of the lower bone.

    Returns:
        tuple: World position of the middle joint.

    Raises:
        ValueError: If a bone length is not positive.

    """
    if upper_length <= 0 or lower_length <= 0:
        raise ValueError("Bone lengths must be positive.")
    to_target = vecmath.sub(target, root)
    axis = vecmath.normalize(to_target)
    reach = vecmath.length(to_target)
    reach = min(max(reach, abs(upper_length - lower_length)), upper_length + lower_length)

    cos_root = (upper_length ** 2 + reach ** 2 - lower_length ** 2) / (
        2.0 * upper_length * reach
    )
    cos_root = max(-1.0, min(1.0, cos_root))
    along = upper_length * cos_root
    across = upper_length * math.sqrt(max(0.0, 1.0 - cos_root ** 2))

    bend = vecmath.reject(vecmath.sub(pole, root), axis)
    if vecmath.length(bend) < vecmath.EPSILON:
        raise ValueError("Pole vector lies on the root-target line.")
    bend = vecmath.normalize(bend)
    return vecmath.add(
        root, vecmath.add(vecmath.scale(axis, along), vecmath.scale(bend, across))
    )


def bone_rotation(start, end, pole_dir, aim_axis="x", up_axis="y"):
    """Build the world rotation of a bone aimed from ``start`` to ``end``.

    Args:
        start (tuple): World position at the start of the bone.
        end (tuple): World position at the end of the bone.
        pole_dir (tuple): Direction the ``up_axis`` should lean toward.
        aim_axis (str): Local axis running down the bone.
        up_axis (str): Local axis pointing toward the pole side.

    Returns:
        tuple: 3x3 world rotation matrix.

    """
    return vecmath.frame_from_axes(
        vecmath.sub(end, start), pole_dir, aim_axis=aim_axis, up_axis=up_axis
    )


def fk_from_ik(root, mid, end, end_rotation, aim_axis="x", up_axis="y",
               fallback_pole=None):
    """Compute FK control orientations that reproduce an IK limb pose.

    Args:
        root (tuple): World position of the root joint.
        mid (tuple): World position of the middle joint.
        end (tuple): World position of the end joint.
        end_rotation (tuple): 3x3 world rotation of the end joint.
        aim_axis (str): Local axis the FK controls aim down the bone.
        up_axis (str): Local axis the FK controls point at the pole side.
        fallback_pole (tuple): Pole direction used for a straight limb.

    Returns:
        FkPose: World rotations for the upper, lower and end FK controls.

    """
    pole_dir = pole_direction(root, mid, end, fallback=fallback_pole)
    upper = bone_rotation(root, mid, pole_dir, aim_axis, up_axis)
    lower = bone_rotation(mid, end, pole_dir, aim_axis, up_axis)
    return FkPose(upper=upper, lower=lower, end=vecmath.orthonormalize(end_rotation))


def ik_from_fk(root, mid, end, end_rotation, pole_distance=None,
               fallback_pole=None):
    """Compute IK handle and pole vector placement from an FK limb pose.

    Args:
        root (tuple): World position of the root joint.
        mid (tuple): World position of the middle joint.
        end (tuple): World position of the end joint.
        end_rotation (tuple): 3x3 world rotation of the end FK control.
        pole_distance (float): Pole offset from the mid joint.
        fallback_pole (tuple): Pole direction used for a straight limb.

    Returns:
        IkPose: Where to put the IK handle and the pole vector control.

    """
    pole = pole_vector_position(
        root, mid, end, distance=pole_distance, fallback=fallback_pole
    )
    return IkPose(
        handle_position=tuple(end),
        handle_rotation=vecmath.orthonormalize(end_rotation),
        pole_position=pole,
    )


def local_rotation(world_rotation, parent_rotation):
    """Express a world rotation relative to a parent rotation.

    Args:
        world_rotation (tuple): 3x3 world rotation of the child.
        parent_rotation (tuple): 3x3 world rotation of the parent.

    Returns:
        tuple: 3x3 local rotation such that ``local * parent == world``.

    """
    parent = vecmath.orthonormalize(parent_rotation)
    return vecmath.mat_mul(world_rotation, vecmath.transpose(parent))


def chain_positions(root, upper_rotation, lower_rotation, upper_length,
                    lower_length, aim_axis="x"):
    """Forward kinematics: rebuild joint positions from FK bone rotations.

    Args:
        root (tuple): World position of the root joint.
        upper_rotation (tuple): 3x3 world rotation of the upper bone.
        lower_rotation (tuple): 3x3 world rotation of the lower bone.
        upper_length (float): Length of the upper bone.
        lower_length (float): Length of the lower bone.
        aim_axis (str): Local axis running down each bone.

    Returns:
        tuple: ``(root, mid, end)`` world positions.

    """
    sign, index = vecmath.parse_axis(aim_axis)
    mid = vecmath.add(root, vecmath.scale(upper_rotation[index], sign * upper_length))
    end = vecmath.add(mid, vecmath.scale(lower_rotation[index], sign * lower_length))
    return tuple(root), mid, end
