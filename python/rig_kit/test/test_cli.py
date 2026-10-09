"""Tests for the ``segment`` sub-command of rig_kit.cli."""

import json

from rig_kit import cli
from rig_kit.test import meshes


def test_segment_prints_piece_sizes(tmp_path, capsys):
    faces, coords = meshes.grid(4, 12)
    dump = {
        "faces": faces,
        "weights": meshes.blended_weights(coords, height=12, influences=4),
        "influences": ["hip_jnt", "knee_jnt", "ankle_jnt", "toe_jnt"],
    }
    path = tmp_path / "mesh.json"
    path.write_text(json.dumps({**dump, "weights": [
        {str(k): v for k, v in row.items()} for row in dump["weights"]
    ]}))

    assert cli.main(["segment", str(path), "--min-faces", "4"]) == 0
    out = capsys.readouterr().out
    assert "48 faces, 4 islands" in out
    assert "knee_jnt" in out


def test_segment_rejects_incomplete_dump(tmp_path, capsys):
    path = tmp_path / "mesh.json"
    path.write_text(json.dumps({"faces": []}))
    assert cli.main(["segment", str(path)]) == 2
    assert "missing 'weights'" in capsys.readouterr().err
