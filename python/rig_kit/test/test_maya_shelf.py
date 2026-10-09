"""Maya tests for the shelf actions and the installer. Run with ``mayapy -m pytest``.

Uses the same skinned cylinder and three-joint arm as the smoke tests, but
goes through the selection-based shelf actions and the real
``install_rig_kit.py`` entry point. Skipped when Maya is not importable.

"""

import importlib.util
import os

import pytest

pytest.importorskip("maya.standalone")

from maya import cmds  # noqa: E402
from maya import standalone  # noqa: E402

from rig_kit import install  # noqa: E402
from rig_kit import maya_shelf  # noqa: E402

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

ARM_CONFIG = """\
limbs:
  arm:
    blend_attr: ui_ctl.blend
    chain: [a0, a1, a2]
    fk: [a0_fk_ctl, a1_fk_ctl, a2_fk_ctl]
    ik: ik_ctl
    pole: pole_ctl
    up_axis: -z
"""


@pytest.fixture(scope="module", autouse=True)
def maya_session():
    standalone.initialize(name="python")
    yield


@pytest.fixture
def skinned_cylinder():
    cmds.file(new=True, force=True)
    mesh = cmds.polyCylinder(name="limb_geo", height=6, subdivisionsY=12, subdivisionsX=8)[0]
    cmds.move(0, 3, 0, mesh)
    cmds.select(clear=True)
    joints = [cmds.joint(name="limb_{0}_jnt".format(i), position=(0, y, 0))
              for i, y in enumerate((0, 2, 4, 6))]
    cmds.skinCluster(joints, mesh, toSelectedBones=True, maximumInfluences=2)
    return mesh


@pytest.fixture
def arm(tmp_path):
    cmds.file(new=True, force=True)
    cmds.select(clear=True)
    chain = [cmds.joint(name=n, position=p) for n, p in
             (("a0", (0, 10, 0)), ("a1", (3, 10, -0.5)), ("a2", (6, 10, 0)))]
    parent = None
    for joint in chain:
        kwargs = {"parent": parent} if parent else {}
        ctl = cmds.group(empty=True, name=joint + "_fk_ctl", **kwargs)
        cmds.matchTransform(ctl, joint)
        parent = ctl
    for name in ("ik_ctl", "pole_ctl", "ui_ctl"):
        cmds.group(empty=True, name=name)
    cmds.addAttr("ui_ctl", longName="blend", minValue=0, maxValue=1, defaultValue=1)
    config = tmp_path / "limbs.yaml"
    config.write_text(ARM_CONFIG)
    return str(config)


def test_proxy_button_needs_a_selection(skinned_cylinder):
    cmds.select(clear=True)
    assert maya_shelf.build_proxies_from_selection() == []


def test_proxy_button_builds_pieces_for_the_selection(skinned_cylinder):
    cmds.select(skinned_cylinder)
    pieces = maya_shelf.build_proxies_from_selection(min_faces=4)
    total = sum(cmds.polyEvaluate(piece, face=True) for piece in pieces)
    assert total == cmds.polyEvaluate(skinned_cylinder, face=True)


def test_proxy_button_reports_an_unskinned_mesh():
    cmds.file(new=True, force=True)
    cmds.select(cmds.polyCube()[0])
    assert maya_shelf.build_proxies_from_selection() == []


def test_ikfk_button_switches_the_selected_limb(arm):
    cmds.select("a1_fk_ctl")
    assert maya_shelf.switch_selected_limbs(arm) == {"arm": "fk"}
    assert cmds.getAttr("ui_ctl.blend") == 0
    cmds.select("ik_ctl", "a0_fk_ctl")
    assert maya_shelf.switch_selected_limbs(arm) == {"arm": "ik"}


def test_ikfk_button_ignores_unrelated_selection(arm):
    cmds.select(cmds.group(empty=True, name="spine_ctl"))
    assert maya_shelf.switch_selected_limbs(arm) == {}


def test_default_limb_config_is_the_mgear_biped():
    assert os.path.isfile(maya_shelf.limb_config_path())


def test_check_button_returns_issues(skinned_cylinder):
    issues = maya_shelf.check_scene()
    assert isinstance(issues, list)


def test_drop_installer_writes_the_module_file(tmp_path, monkeypatch):
    modules = str(tmp_path / "modules")
    monkeypatch.setattr(install, "user_modules_dir", lambda: modules)
    spec = importlib.util.spec_from_file_location(
        "install_rig_kit", os.path.join(REPO_ROOT, "install_rig_kit.py")
    )
    dropped = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dropped)

    dropped.onMayaDroppedPythonFile()

    with open(os.path.join(modules, "rig_kit.mod"), encoding="utf-8") as handle:
        assert handle.read() == install.module_text(REPO_ROOT)
    assert install.build_shelf() is None
