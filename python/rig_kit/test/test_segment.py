"""Tests for rig_kit.segment on synthetic quad grids.

Covers face assignment, neighbour smoothing, small island merging and the
full pipeline on a blended "limb" with injected weight noise.

"""

import pytest

from rig_kit import segment
from rig_kit.test import meshes


def _strip(labels):
    """Return grid adjacency for a single row of len(labels) quads."""
    faces, _ = meshes.grid(len(labels), 1)
    return segment.face_adjacency(faces)


def test_assign_picks_highest_summed_weight():
    faces, coords = meshes.grid(4, 6)
    weights = meshes.banded_weights(coords, bands=[2, 6])
    result = segment.segment(faces, weights, smooth_iterations=0)
    # Row 2 straddles the band edge (2 vs 2 votes) and the tie goes to 0.
    assert result.piece_sizes() == {0: 12, 1: 12}
    assert result.labels[meshes.face_index(4, 0, 2)] == 0
    assert result.labels[meshes.face_index(4, 0, 3)] == 1


def test_assign_tie_breaks_on_lowest_influence():
    scores = [{3: 1.0, 1: 1.0, 2: 0.5}, {}]
    assert segment.assign_faces(scores) == [1, -1]


def test_face_adjacency_counts_shared_edges():
    faces, _ = meshes.grid(2, 2)
    adjacency = segment.face_adjacency(faces)
    assert adjacency[0] == {1: 1, 2: 1}
    assert adjacency[3] == {1: 1, 2: 1}


def test_smoothing_removes_single_face_speckle():
    faces, _ = meshes.grid(3, 3)
    adjacency = segment.face_adjacency(faces)
    labels = [0] * 9
    labels[4] = 1
    scores = [{0: 1.0} for _ in range(9)]
    scores[4] = {0: 1.0, 1: 1.5}
    assert segment.smooth_labels(labels, adjacency, scores) == [0] * 9


def test_smoothing_never_assigns_unweighted_influence():
    faces, _ = meshes.grid(3, 3)
    adjacency = segment.face_adjacency(faces)
    labels = [0] * 9
    labels[4] = 1
    scores = [{0: 1.0} for _ in range(9)]
    scores[4] = {1: 4.0}
    assert segment.smooth_labels(labels, adjacency, scores)[4] == 1


def test_smoothing_keeps_straight_borders():
    faces, coords = meshes.grid(4, 6)
    weights = meshes.banded_weights(coords, bands=[2, 6])
    scores = segment.face_scores(faces, weights)
    labels = segment.assign_faces(scores)
    adjacency = segment.face_adjacency(faces)
    assert segment.smooth_labels(labels, adjacency, scores, iterations=5) == labels


def test_merge_is_noop_below_threshold_of_two():
    labels = [0, 1, 0]
    assert segment.merge_small_islands(labels, _strip(labels), min_faces=1) == labels


def test_merge_small_island_into_surrounding_piece():
    labels = [0, 0, 0, 1, 0, 0]
    merged = segment.merge_small_islands(labels, _strip(labels), min_faces=2)
    assert merged == [0] * 6


def test_merge_prefers_longest_shared_border():
    # Row 0: 0 1 2 2 / Row 1: 0 0 2 2. The lone "1" touches piece 0 on two
    # edges and the larger piece 2 on one edge.
    faces, _ = meshes.grid(4, 2)
    labels = [0, 1, 2, 2, 0, 0, 2, 2]
    merged = segment.merge_small_islands(
        labels, segment.face_adjacency(faces), min_faces=2
    )
    assert merged[1] == 0


def test_merge_tie_goes_to_larger_neighbour():
    labels = [0, 0, 1, 2, 2, 2]
    merged = segment.merge_small_islands(labels, _strip(labels), min_faces=2)
    assert merged == [0, 0, 2, 2, 2, 2]


def test_merge_avoids_unweighted_regions():
    labels = [-1, -1, -1, 1, 0]
    merged = segment.merge_small_islands(labels, _strip(labels), min_faces=2)
    assert merged == [-1, -1, -1, 0, 0]


def test_merge_keeps_disconnected_shells():
    faces = [(0, 1, 2, 3), (4, 5, 6, 7)]
    labels = [0, 1]
    adjacency = segment.face_adjacency(faces)
    assert segment.merge_small_islands(labels, adjacency, min_faces=5) == labels


def test_merge_cascades_until_all_islands_are_large_enough():
    labels = [0, 0, 0, 0, 1, 2, 3, 3, 3, 3]
    merged = segment.merge_small_islands(labels, _strip(labels), min_faces=3)
    islands = segment.find_islands(merged, _strip(labels))
    assert all(len(island) >= 3 for island in islands)


def _noisy_limb():
    """Four-influence blended grid with one bad edge painted to joint 3."""
    faces, coords = meshes.grid(4, 12)
    weights = meshes.blended_weights(coords, height=12, influences=4)
    for vertex, (x, y) in enumerate(coords):
        if y == 4 and x in (1, 2):
            weights[vertex] = {3: 1.0}
    return faces, weights


def test_noise_creates_a_fragment_without_cleanup():
    faces, weights = _noisy_limb()
    result = segment.segment(faces, weights, smooth_iterations=0, min_faces=0)
    assert result.labels[meshes.face_index(4, 1, 4)] == 3
    assert len(result.pieces[3]) > 2
    assert len(result.islands) == 5


@pytest.mark.parametrize("smooth, min_faces", [(2, 0), (0, 4)])
def test_cleanup_folds_the_fragment_back(smooth, min_faces):
    faces, weights = _noisy_limb()
    result = segment.segment(faces, weights, smooth_iterations=smooth, min_faces=min_faces)
    assert result.labels[meshes.face_index(4, 1, 4)] == 1
    assert len(result.islands) == 4


def test_blended_limb_gives_ordered_contiguous_bands():
    faces, coords = meshes.grid(4, 12)
    weights = meshes.blended_weights(coords, height=12, influences=4)
    result = segment.segment(faces, weights, min_faces=4)
    rows = [result.labels[meshes.face_index(4, 0, y)] for y in range(12)]
    assert rows == sorted(rows)
    assert set(result.pieces) == {0, 1, 2, 3}
    assert len(result.islands) == 4
    assert sum(result.piece_sizes().values()) == len(faces)


def test_dense_rows_match_sparse_dicts():
    faces, coords = meshes.grid(3, 6)
    sparse = meshes.blended_weights(coords, height=6, influences=3)
    dense = [[row.get(i, 0.0) for i in range(3)] for row in sparse]
    assert segment.segment(faces, dense).labels == segment.segment(faces, sparse).labels


def test_numpy_matrix_input():
    numpy = pytest.importorskip("numpy")
    faces, coords = meshes.grid(3, 6)
    sparse = meshes.blended_weights(coords, height=6, influences=3)
    matrix = numpy.array([[row.get(i, 0.0) for i in range(3)] for row in sparse])
    assert segment.segment(faces, matrix).labels == segment.segment(faces, sparse).labels


@pytest.mark.parametrize("faces, weights, message", [
    ([], [{0: 1.0}], "no faces"),
    ([(0, 1, 2)], [], "No vertex weights"),
    ([(0, 1)], [{0: 1.0}] * 2, "fewer than 3"),
    ([(0, 1, 5)], [{0: 1.0}] * 3, "uses vertex 5"),
    ([(0, 1, 2)], [{0: -0.5}] * 3, "Negative weight"),
])
def test_invalid_input_raises(faces, weights, message):
    with pytest.raises(ValueError, match=message):
        segment.segment(faces, weights)


def test_compress_indices_builds_ranges():
    assert segment.compress_indices([7, 1, 2, 3, 9, 8, 2]) == [(1, 3), (7, 9)]
    assert segment.compress_indices([]) == []
