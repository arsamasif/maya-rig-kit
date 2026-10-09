"""Small vector and matrix helpers for rig math.

Plain-Python 3D vectors (tuples) and 3x3 rotation matrices using Maya's
row-vector convention: each matrix row is a local axis expressed in world
space, and a point is transformed as ``p * M``. Euler conversion supports all
six Maya rotate orders so results can be written straight to ``rotate``.

"""

import math

EPSILON = 1e-9
ROTATE_ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")
IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def vec(x, y, z):
    """Build a vector tuple of floats.

    Args:
        x (float): X component.
        y (float): Y component.
        z (float): Z component.

    Returns:
        tuple: ``(x, y, z)`` as floats.

    """
    return (float(x), float(y), float(z))


def add(a, b):
    """Return ``a + b``."""
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    """Return ``a - b``."""
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a, s):
    """Return ``a * s`` for a scalar ``s``."""
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    """Return the dot product of two vectors."""
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    """Return the cross product ``a x b``."""
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a):
    """Return the Euclidean length of a vector."""
    return math.sqrt(dot(a, a))


def distance(a, b):
    """Return the distance between two points."""
    return length(sub(a, b))


def normalize(a):
    """Return a unit-length copy of ``a``.

    Args:
        a (tuple): Vector to normalize.

    Returns:
        tuple: Unit vector pointing along ``a``.

    Raises:
        ValueError: If ``a`` has (near) zero length.

    """
    size = length(a)
    if size < EPSILON:
        raise ValueError("Cannot normalize a zero-length vector: {0}".format(a))
    return scale(a, 1.0 / size)


def reject(a, axis):
    """Return the part of ``a`` perpendicular to the unit vector ``axis``."""
    return sub(a, scale(axis, dot(a, axis)))


def transpose(m):
    """Return the transpose of a 3x3 matrix."""
    return tuple(tuple(m[r][c] for r in range(3)) for c in range(3))


def mat_mul(a, b):
    """Return the 3x3 matrix product ``a * b``."""
    return tuple(
        tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3))
        for r in range(3)
    )


def vec_mat_mul(v, m):
    """Transform a row vector by a 3x3 matrix (``v * m``)."""
    return tuple(sum(v[k] * m[k][c] for k in range(3)) for c in range(3))


def orthonormalize(m):
    """Strip scale and shear from a 3x3 matrix, keeping the X axis direction.

    Args:
        m (tuple): 3x3 matrix whose rows are (possibly scaled) axes.

    Returns:
        tuple: Orthonormal right-handed 3x3 rotation matrix.

    """
    x_axis = normalize(m[0])
    z_axis = normalize(cross(x_axis, m[1]))
    y_axis = cross(z_axis, x_axis)
    return (x_axis, y_axis, z_axis)


def frame_from_axes(aim, up, aim_axis="x", up_axis="y"):
    """Build a rotation matrix that points one local axis along ``aim``.

    The secondary local axis is placed as close to ``up`` as possible while
    staying perpendicular to ``aim``. Axis names may carry a leading ``-`` to
    flip them, which is how mirrored (right side) controls are usually built.

    Args:
        aim (tuple): World direction for ``aim_axis``.
        up (tuple): World direction hint for ``up_axis``.
        aim_axis (str): Local axis to aim, e.g. ``"x"`` or ``"-x"``.
        up_axis (str): Local axis to point at ``up``, e.g. ``"y"``.

    Returns:
        tuple: 3x3 row-vector rotation matrix.

    Raises:
        ValueError: If the axes are the same or ``aim`` and ``up`` are parallel.

    """
    aim_sign, aim_index = parse_axis(aim_axis)
    up_sign, up_index = parse_axis(up_axis)
    if aim_index == up_index:
        raise ValueError(
            "Aim and up axis must differ: {0}, {1}".format(aim_axis, up_axis)
        )
    aim_dir = normalize(aim)
    up_dir = reject(up, aim_dir)
    if length(up_dir) < EPSILON:
        raise ValueError("Up vector is parallel to the aim vector.")
    up_dir = normalize(up_dir)

    rows = [None, None, None]
    rows[aim_index] = scale(aim_dir, aim_sign)
    rows[up_index] = scale(up_dir, up_sign)
    last = 3 - aim_index - up_index
    nxt, prv = (last + 1) % 3, (last + 2) % 3
    rows[last] = cross(rows[nxt], rows[prv])
    return tuple(rows)


def parse_axis(name):
    """Split ``"-y"`` style axis names into ``(sign, index)``.

    Args:
        name (str): Axis name such as ``"x"`` or ``"-z"``.

    Returns:
        tuple: ``(sign, index)`` with sign ``1.0`` or ``-1.0``.

    Raises:
        ValueError: If the name is not a principal axis.

    """
    text = name.strip().lower()
    sign = -1.0 if text.startswith("-") else 1.0
    key = text.lstrip("+-")
    if key not in _AXIS_INDEX:
        raise ValueError("Unknown axis name: {0}".format(name))
    return sign, _AXIS_INDEX[key]


def axis_rotation(axis, angle):
    """Return the row-vector matrix for a rotation about a principal axis.

    Args:
        axis (str): ``"x"``, ``"y"`` or ``"z"``.
        angle (float): Angle in radians.

    Returns:
        tuple: 3x3 rotation matrix.

    """
    c, s = math.cos(angle), math.sin(angle)
    if axis == "x":
        return ((1.0, 0.0, 0.0), (0.0, c, s), (0.0, -s, c))
    if axis == "y":
        return ((c, 0.0, -s), (0.0, 1.0, 0.0), (s, 0.0, c))
    if axis == "z":
        return ((c, s, 0.0), (-s, c, 0.0), (0.0, 0.0, 1.0))
    raise ValueError("Unknown axis name: {0}".format(axis))


def matrix_from_euler(angles, order="xyz", degrees=True):
    """Compose a rotation matrix from Euler angles the way Maya does.

    Args:
        angles (tuple): Rotation about X, Y and Z (always in XYZ slots).
        order (str): Maya rotate order, e.g. ``"xyz"`` or ``"zxy"``.
        degrees (bool): Whether ``angles`` are in degrees.

    Returns:
        tuple: 3x3 row-vector rotation matrix.

    """
    _check_order(order)
    values = [math.radians(a) if degrees else a for a in angles]
    result = IDENTITY
    for axis in order:
        result = mat_mul(result, axis_rotation(axis, values[_AXIS_INDEX[axis]]))
    return result


def euler_from_matrix(m, order="xyz", degrees=True):
    """Decompose a rotation matrix into Euler angles for a rotate order.

    Inverse of :func:`matrix_from_euler`. At gimbal lock the first axis of the
    order is set to zero and the remaining rotation goes to the last axis.

    Args:
        m (tuple): Orthonormal 3x3 row-vector rotation matrix.
        order (str): Maya rotate order.
        degrees (bool): Return degrees instead of radians.

    Returns:
        tuple: Rotation about X, Y and Z.

    """
    _check_order(order)
    i, j, k = (_AXIS_INDEX[a] for a in order)
    parity = 1.0 if (j - i) % 3 == 1 else -1.0
    # Column-vector form of the same rotation: C = Rk * Rj * Ri.
    c = transpose(m)

    sin_b = max(-1.0, min(1.0, -parity * c[k][i]))
    b = math.asin(sin_b)
    if abs(sin_b) < 1.0 - 1e-10:
        a = math.atan2(parity * c[k][j], c[k][k])
        g = math.atan2(parity * c[j][i], c[i][i])
    else:
        a = 0.0
        g = math.atan2(-parity * c[i][j], c[j][j])

    result = [0.0, 0.0, 0.0]
    result[i], result[j], result[k] = a, b, g
    if degrees:
        result = [math.degrees(v) for v in result]
    return tuple(result)


def _check_order(order):
    """Raise if ``order`` is not a Maya rotate order."""
    if order not in ROTATE_ORDERS:
        raise ValueError("Unknown rotate order: {0}".format(order))


def compose_matrix(rotation, translation):
    """Build a flat 16-float Maya matrix from rotation rows and translation.

    Args:
        rotation (tuple): 3x3 rotation matrix.
        translation (tuple): World translation.

    Returns:
        list: 16 floats in Maya ``xform -matrix`` order.

    """
    flat = []
    for row in rotation:
        flat.extend([row[0], row[1], row[2], 0.0])
    flat.extend([translation[0], translation[1], translation[2], 1.0])
    return flat


def split_matrix(flat):
    """Split a flat 16-float Maya matrix into a 3x3 block and translation.

    Args:
        flat (list): 16 floats as returned by ``cmds.xform(q=True, matrix=True)``.

    Returns:
        tuple: ``(rotation_rows, translation)``. Rows keep any scale.

    Raises:
        ValueError: If ``flat`` does not hold 16 values.

    """
    if len(flat) != 16:
        raise ValueError("Expected 16 matrix values, got {0}".format(len(flat)))
    rows = tuple(tuple(float(v) for v in flat[r * 4:r * 4 + 3]) for r in range(3))
    return rows, (float(flat[12]), float(flat[13]), float(flat[14]))


def closest_euler(angles, reference):
    """Shift each angle by whole turns so it lands nearest the reference.

    Keeps matched controls from jumping 360 degrees between keys.

    Args:
        angles (tuple): Euler angles in degrees.
        reference (tuple): Current angles in degrees to stay close to.

    Returns:
        tuple: Equivalent angles within 180 degrees of ``reference`` per axis.

    """
    return tuple(
        value + 360.0 * round((ref - value) / 360.0)
        for value, ref in zip(angles, reference)
    )
