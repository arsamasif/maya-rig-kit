"""Synthetic meshes and skin weights for segmentation tests.

Builds quad grids with a vertex weight function, so tests can describe a
"limb" as weights blending along one axis without any Maya scene.

"""


def grid(columns, rows):
    """Build a flat quad grid.

    Args:
        columns (int): Number of quads along X.
        rows (int): Number of quads along Y.

    Returns:
        tuple: ``(faces, vertex_coords)`` where faces are 4-vertex tuples and
        coords are ``(x, y)`` integer pairs, both in row-major order.

    """
    coords = [(x, y) for y in range(rows + 1) for x in range(columns + 1)]

    def vid(x, y):
        return y * (columns + 1) + x

    faces = [
        (vid(x, y), vid(x + 1, y), vid(x + 1, y + 1), vid(x, y + 1))
        for y in range(rows)
        for x in range(columns)
    ]
    return faces, coords


def face_index(columns, x, y):
    """Return the face index of quad ``(x, y)`` in a :func:`grid`."""
    return y * columns + x


def banded_weights(coords, bands):
    """Rigid weights: each vertex belongs fully to the band its Y falls in.

    Args:
        coords (list): ``(x, y)`` vertex coordinates.
        bands (list): Upper Y bound (inclusive) per influence, ascending.

    Returns:
        list: ``{influence: 1.0}`` per vertex.

    """
    weights = []
    for _, y in coords:
        influence = next(i for i, top in enumerate(bands) if y <= top)
        weights.append({influence: 1.0})
    return weights


def blended_weights(coords, height, influences):
    """Smooth linear blend between neighbouring influences along Y.

    Args:
        coords (list): ``(x, y)`` vertex coordinates.
        height (float): Total grid height.
        influences (int): Number of influences spread evenly along Y.

    Returns:
        list: ``{influence: weight}`` per vertex, each summing to 1.

    """
    weights = []
    span = height / float(influences - 1)
    for _, y in coords:
        position = y / span
        low = min(int(position), influences - 2)
        t = position - low
        row = {low: 1.0 - t, low + 1: t}
        weights.append({k: v for k, v in row.items() if v > 0.0})
    return weights
