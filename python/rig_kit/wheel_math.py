"""Wheel roll math shared by the ``wheel_01`` Shifter component and tests.

A wheel that rolls without slipping turns by ``travel / radius`` radians. The
component measures travel as the wheel's displacement from its rest position
projected onto its current forward axis. That is scrubbable (no frame-to-frame
state) and exact for straight-line motion, which is what most shots need.

"""

import math

from rig_kit import vecmath


def travel_distance(position, rest_position, forward):
    """Signed distance travelled along the forward axis.

    Args:
        position (tuple): Current world position of the wheel centre.
        rest_position (tuple): World position of the wheel at bind time.
        forward (tuple): Forward direction (does not need to be unit length).

    Returns:
        float: Positive when the wheel moved forward.

    """
    return vecmath.dot(vecmath.sub(position, rest_position), vecmath.normalize(forward))


def roll_angle(travel, radius, degrees=True):
    """Rotation of a wheel that rolled ``travel`` units without slipping.

    Args:
        travel (float): Signed distance travelled.
        radius (float): Wheel radius.
        degrees (bool): Return degrees instead of radians.

    Returns:
        float: Rotation about the axle.

    Raises:
        ValueError: If ``radius`` is not positive.

    """
    if radius <= 0:
        raise ValueError("Wheel radius must be positive, got {0}".format(radius))
    angle = travel / radius
    return math.degrees(angle) if degrees else angle


def degrees_per_unit(radius):
    """Multiplier from travel distance to degrees, used to drive a node graph.

    Args:
        radius (float): Wheel radius.

    Returns:
        float: Degrees of roll per unit of travel.

    """
    return roll_angle(1.0, radius, degrees=True)
