"""Tests for rig_kit.limb_config."""

import os

import pytest
import yaml

from rig_kit import limb_config

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "config")


def _limb(**overrides):
    entry = {
        "blend_attr": "armUI_L0_ctl.arm_blend",
        "chain": ["a", "b", "c"],
        "fk": ["fk0", "fk1", "fk2"],
        "ik": "ik_ctl",
        "pole": "upv_ctl",
    }
    entry.update(overrides)
    return {"limbs": {"arm_L": entry}}


def test_parse_applies_defaults():
    spec = limb_config.parse(_limb())["arm_L"]
    assert spec.chain == ("a", "b", "c")
    assert spec.ik_value == 1.0 and spec.fk_value == 0.0
    assert (spec.aim_axis, spec.up_axis) == ("x", "y")
    assert spec.pole_distance is None
    assert spec.match_ik_rotation is True


def test_load_example_config():
    limbs = limb_config.load(os.path.join(CONFIG_DIR, "limbs_mgear_biped.yaml"))
    assert set(limbs) == {"arm_L", "arm_R", "leg_L"}
    assert limbs["arm_R"].aim_axis == "-x"
    assert limbs["leg_L"].match_ik_rotation is False


def test_load_from_tmp_file(tmp_path):
    path = tmp_path / "limbs.yaml"
    path.write_text(yaml.safe_dump(_limb(pole_distance=12.0)))
    assert limb_config.load(str(path))["arm_L"].pole_distance == 12.0


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        limb_config.load("/nope/limbs.yaml")


@pytest.mark.parametrize("data, message", [
    ({}, "non-empty 'limbs'"),
    ({"limbs": {"arm": "x"}}, "must be a mapping"),
    (_limb(chain=["a", "b"]), "exactly 3"),
    (_limb(blend_attr="no_dot"), "node.attr"),
    (_limb(colour="red"), "unknown keys: colour"),
    (_limb(aim_axis="w"), "Unknown axis"),
    (_limb(aim_axis="-y", up_axis="y"), "must differ"),
])
def test_invalid_config_raises(data, message):
    with pytest.raises(ValueError, match=message):
        limb_config.parse(data)


def test_missing_required_key_raises():
    data = _limb()
    del data["limbs"]["arm_L"]["pole"]
    with pytest.raises(ValueError, match="missing: pole"):
        limb_config.parse(data)


def test_find_limb_from_any_of_its_nodes():
    limbs = limb_config.parse(_limb())
    for node in ("fk1", "ik_ctl", "upv_ctl", "b", "|rig|armUI_L0_ctl"):
        assert limb_config.find_limb(limbs, node).name == "arm_L"
    assert limb_config.find_limb(limbs, "spine_ctl") is None


def test_find_limb_adds_the_selected_namespace():
    limbs = limb_config.parse(_limb())
    spec = limb_config.find_limb(limbs, "hero:fk0")
    assert spec.fk == ("hero:fk0", "hero:fk1", "hero:fk2")
    assert spec.chain[0] == "hero:a"
    assert (spec.ik, spec.pole) == ("hero:ik_ctl", "hero:upv_ctl")
    assert spec.blend_attr == "hero:armUI_L0_ctl.arm_blend"
