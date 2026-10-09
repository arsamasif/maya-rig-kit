"""Split a skinned mesh into per-influence proxy pieces.

The algorithm runs on plain data (face vertex lists and per-vertex skin
weights), so it can be tested on synthetic meshes without Maya:

1. Assign: each face goes to the influence with the highest summed weight
   over its vertices.
2. Smooth: a few rounds of neighbour voting relabel faces that disagree with
   their surroundings. A face only switches to an influence that actually
   weights it, so smoothing never invents ownership.
3. Merge: connected islands smaller than ``min_faces`` are folded into the
   neighbouring island they share the longest border with. Islands are merged
   smallest first through a region adjacency graph, so the result does not
   depend on face order and always terminates.

The output maps each influence index to the faces of its proxy piece.

"""

import heapq
from collections import Counter, defaultdict
from dataclasses import dataclass, field

WEIGHT_EPSILON = 1e-6


@dataclass
class Segmentation:
    """Result of a segmentation run.

    Attributes:
        labels (list): Influence index per face.
        pieces (dict): Influence index to sorted list of face indices.
        islands (list): Lists of face indices, one per connected piece part.

    """

    labels: list
    pieces: dict = field(default_factory=dict)
    islands: list = field(default_factory=list)

    def piece_sizes(self):
        """Return face count per influence index.

        Returns:
            dict: Influence index to number of faces.

        """
        return {influence: len(faces) for influence, faces in self.pieces.items()}


def segment(faces, weights, smooth_iterations=2, min_faces=0):
    """Run assignment, smoothing and merging on a mesh.

    Args:
        faces (list): Vertex index sequence per face.
        weights (list): Per-vertex weights, either dicts of
            ``{influence: weight}`` or dense rows (lists or numpy arrays).
        smooth_iterations (int): Rounds of neighbour voting; 0 disables it.
        min_faces (int): Islands with fewer faces get merged into a neighbour;
            0 or 1 disables merging.

    Returns:
        Segmentation: Face labels, pieces and islands.

    Raises:
        ValueError: On empty or inconsistent input.

    """
    sparse = to_sparse_weights(weights)
    _validate_faces(faces, len(sparse))
    scores = face_scores(faces, sparse)
    labels = assign_faces(scores)
    adjacency = face_adjacency(faces)
    labels = smooth_labels(labels, adjacency, scores, iterations=smooth_iterations)
    labels = merge_small_islands(labels, adjacency, min_faces=min_faces)
    return Segmentation(
        labels=labels,
        pieces=group_pieces(labels),
        islands=find_islands(labels, adjacency),
    )


def to_sparse_weights(weights):
    """Normalise per-vertex weights into ``{influence: weight}`` dicts.

    Zero (and near-zero) weights are dropped. Dense rows are accepted so that
    a numpy matrix of shape ``(vertices, influences)`` can be passed directly.

    Args:
        weights (list): Dicts or dense rows, one per vertex.

    Returns:
        list: One ``{influence: weight}`` dict per vertex.

    Raises:
        ValueError: If there are no vertices or a weight is negative.

    """
    result = []
    for vertex, row in enumerate(weights):
        items = row.items() if isinstance(row, dict) else enumerate(row)
        clean = {}
        for influence, value in items:
            value = float(value)
            if value < -WEIGHT_EPSILON:
                raise ValueError(
                    "Negative weight {0} on vertex {1}".format(value, vertex)
                )
            if value > WEIGHT_EPSILON:
                clean[int(influence)] = value
        result.append(clean)
    if not result:
        raise ValueError("No vertex weights given.")
    return result


def _validate_faces(faces, vertex_count):
    """Raise if faces are empty or reference missing vertices."""
    if not faces:
        raise ValueError("Mesh has no faces.")
    for index, face in enumerate(faces):
        if len(face) < 3:
            raise ValueError("Face {0} has fewer than 3 vertices.".format(index))
        for vertex in face:
            if vertex < 0 or vertex >= vertex_count:
                raise ValueError(
                    "Face {0} uses vertex {1}, but only {2} vertices have "
                    "weights.".format(index, vertex, vertex_count)
                )


def face_scores(faces, weights):
    """Sum vertex weights per face and influence.

    Args:
        faces (list): Vertex index sequence per face.
        weights (list): ``{influence: weight}`` dict per vertex.

    Returns:
        list: ``{influence: summed weight}`` dict per face.

    """
    scores = []
    for face in faces:
        total = defaultdict(float)
        for vertex in face:
            for influence, value in weights[vertex].items():
                total[influence] += value
        scores.append(dict(total))
    return scores


def assign_faces(scores):
    """Pick the strongest influence for every face.

    Ties go to the lowest influence index so the result is deterministic.

    Args:
        scores (list): ``{influence: summed weight}`` dict per face.

    Returns:
        list: Influence index per face, or ``-1`` for unweighted faces.

    """
    return [_best(score) for score in scores]


def _best(score):
    """Return the influence with the highest score (lowest index on ties)."""
    if not score:
        return -1
    return min(score, key=lambda influence: (-score[influence], influence))


def face_adjacency(faces):
    """Find faces that share an edge.

    Args:
        faces (list): Vertex index sequence per face.

    Returns:
        list: For each face, a dict of ``{neighbour face: shared edge count}``.

    """
    edge_faces = defaultdict(list)
    for index, face in enumerate(faces):
        for a, b in zip(face, list(face[1:]) + [face[0]]):
            edge_faces[(min(a, b), max(a, b))].append(index)

    adjacency = [defaultdict(int) for _ in faces]
    for owners in edge_faces.values():
        for a in owners:
            for b in owners:
                if a != b:
                    adjacency[a][b] += 1
    return [dict(neighbours) for neighbours in adjacency]


def smooth_labels(labels, adjacency, scores, iterations=2):
    """Relabel faces that disagree with most of their neighbours.

    Each round counts the labels of a face and its edge neighbours (the face
    itself votes once). The face takes the winning label only when it beats
    the current one outright and the face carries weight for that influence.
    All faces update from the previous round's labels, so the order of faces
    does not matter.

    Args:
        labels (list): Influence index per face.
        adjacency (list): Neighbour dicts from :func:`face_adjacency`.
        scores (list): Per-face score dicts from :func:`face_scores`.
        iterations (int): Maximum number of voting rounds.

    Returns:
        list: Smoothed influence index per face.

    """
    current = list(labels)
    for _ in range(max(0, iterations)):
        updated = list(current)
        for face, neighbours in enumerate(adjacency):
            votes = Counter(current[n] for n in neighbours)
            votes[current[face]] += 1
            winner = min(votes, key=lambda label: (-votes[label], label))
            if (
                winner != current[face]
                and votes[winner] > votes[current[face]]
                and scores[face].get(winner, 0.0) > 0.0
            ):
                updated[face] = winner
        if updated == current:
            break
        current = updated
    return current


def find_islands(labels, adjacency):
    """Group faces into connected islands that share the same label.

    Args:
        labels (list): Influence index per face.
        adjacency (list): Neighbour dicts from :func:`face_adjacency`.

    Returns:
        list: Sorted face index lists, ordered by their first face.

    """
    seen = [False] * len(labels)
    islands = []
    for start in range(len(labels)):
        if seen[start]:
            continue
        seen[start] = True
        stack, island = [start], []
        while stack:
            face = stack.pop()
            island.append(face)
            for neighbour in adjacency[face]:
                if not seen[neighbour] and labels[neighbour] == labels[start]:
                    seen[neighbour] = True
                    stack.append(neighbour)
        islands.append(sorted(island))
    return islands


def merge_small_islands(labels, adjacency, min_faces=0):
    """Fold islands smaller than ``min_faces`` into their best neighbour.

    Builds a region adjacency graph (island -> neighbouring island -> shared
    edge count) and repeatedly takes the smallest undersized region. It joins
    the neighbour with the longest shared border; ties go to the larger
    neighbour, then the lower label. Unweighted regions are only chosen when
    nothing else borders the island. An undersized region with no neighbours
    (a separate shell) is kept as is.

    Args:
        labels (list): Influence index per face.
        adjacency (list): Neighbour dicts from :func:`face_adjacency`.
        min_faces (int): Minimum island size to keep.

    Returns:
        list: Influence index per face after merging.

    """
    if min_faces <= 1:
        return list(labels)

    islands = find_islands(labels, adjacency)
    region_of = [0] * len(labels)
    for region, faces in enumerate(islands):
        for face in faces:
            region_of[face] = region

    size = {region: len(faces) for region, faces in enumerate(islands)}
    label = {region: labels[faces[0]] for region, faces in enumerate(islands)}
    members = {region: list(faces) for region, faces in enumerate(islands)}
    borders = _region_borders(adjacency, region_of)

    heap = [(size[r], r) for r in size if size[r] < min_faces]
    heapq.heapify(heap)
    while heap:
        region_size, region = heapq.heappop(heap)
        if region not in size or size[region] != region_size:
            continue  # stale entry: region was merged or has grown
        if region_size >= min_faces or not borders[region]:
            continue
        target = min(
            borders[region],
            key=lambda n: (label[n] < 0, -borders[region][n], -size[n], label[n], n),
        )
        _absorb(target, region, size, members, borders)
        if size[target] < min_faces:
            heapq.heappush(heap, (size[target], target))

    result = list(labels)
    for region, faces in members.items():
        for face in faces:
            result[face] = label[region]
    return result


def _region_borders(adjacency, region_of):
    """Count shared edges between neighbouring regions."""
    borders = defaultdict(lambda: defaultdict(int))
    for face, neighbours in enumerate(adjacency):
        for neighbour, shared in neighbours.items():
            a, b = region_of[face], region_of[neighbour]
            if a != b:
                borders[a][b] += shared
    return defaultdict(dict, {r: dict(n) for r, n in borders.items()})


def _absorb(target, region, size, members, borders):
    """Merge ``region`` into ``target`` and rewire the border counts."""
    size[target] += size.pop(region)
    members[target].extend(members.pop(region))
    for neighbour, shared in borders.pop(region).items():
        borders[neighbour].pop(region, None)
        if neighbour == target:
            continue
        borders[target][neighbour] = borders[target].get(neighbour, 0) + shared
        borders[neighbour][target] = borders[neighbour].get(target, 0) + shared


def group_pieces(labels):
    """Collect face indices per influence, skipping unweighted faces.

    Args:
        labels (list): Influence index per face.

    Returns:
        dict: Influence index to sorted list of face indices.

    """
    pieces = defaultdict(list)
    for face, influence in enumerate(labels):
        if influence >= 0:
            pieces[influence].append(face)
    return dict(sorted(pieces.items()))


def compress_indices(indices):
    """Turn face indices into inclusive ``(start, end)`` ranges.

    Maya component strings like ``mesh.f[10:42]`` are much faster to pass to
    ``cmds.delete`` than thousands of single faces.

    Args:
        indices (list): Integer indices in any order.

    Returns:
        list: Sorted ``(start, end)`` tuples covering every index once.

    """
    ranges = []
    for index in sorted(set(indices)):
        if ranges and index == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], index)
        else:
            ranges.append((index, index))
    return ranges
