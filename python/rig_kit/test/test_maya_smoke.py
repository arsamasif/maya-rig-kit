"""Smoke tests for the Maya adapters. Run with ``mayapy -m pytest``.

Builds a small skinned cylinder and a three-joint arm in a fresh scene, then
exercises proxy building, rig export and IK/FK matching end to end. Skipped
when Maya is not importable.

"""

import pytest

pytest.importorskip("maya.standalone")

from maya import cmds  # noqa: E402
from maya import standalone  # noqa: E402

from rig_kit import ikfk  # noqa: E402
from rig_kit import limb_config  # noqa: E402
from rig_kit import maya_export  # noqa: E402
from rig_kit import maya_ikfk  # noqa: E402
from rig_kit import maya_segment  # noqa: E402
from rig_kit import maya_skin  # noqa: E402
from rig_kit import validate  # noqa: E402
from rig_kit import vecmath  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def maya_session():
    standalone.initialize(name="python")
    yield


@pytest.fixture
def skinned_cylinder():
    cmds.file(new=True, force=True)
    mesh = cmds.polyCylinder(name="limb_geo", height=6, subdivisionsY=12,
                             subdivisionsX=8)[0]
    cmds.move(0, 3, 0, mesh)
    cmds.select(clear=True)
    joints = [cmds.joint(name="limb_C0_{0}_jnt".format(i), position=(0, y, 0))
              for i, y in enumerate((0, 2, 4, 6))]
    cmds.skinCluster(joints, mesh, toSelectedBones=True, maximumInfluences=2)
    return mesh, joints


def test_read_skin(skinned_cylinder):
    mesh, joints = skinned_cylinder
    data = maya_skin.read_skin(mesh)
    assert data.influences == joints
    assert len(data.weights) == cmds.polyEvaluate(mesh, vertex=True)
    assert len(data.faces) == cmds.polyEvaluate(mesh, face=True)


def test_build_proxies(skinned_cylinder):
    mesh, joints = skinned_cylinder
    pieces = maya_segment.build_proxies(mesh, min_faces=4)
    assert pieces
    total = sum(cmds.polyEvaluate(p, face=True) for p in pieces)
    assert total == cmds.polyEvaluate(mesh, face=True)
    assert all(cmds.listRelatives(p, type="parentConstraint") for p in pieces)


def test_export_and_validate(skinned_cylinder):
    rig = maya_export.export_rig("smoke")
    assert rig["skin_clusters"][0]["max_influences_found"] <= 2
    issues = validate.run(rig, rules=["max_influences", "unused_joints"])
    assert not [i for i in issues if i.rule == "max_influences"]


def test_set_world_rotation_on_rotated_parent():
    cmds.file(new=True, force=True)
    parent = cmds.group(empty=True, name="parent_grp")
    cmds.setAttr(parent + ".rotate", 30, 40, 50)
    child = cmds.group(empty=True, name="child_ctl", parent=parent)
    cmds.setAttr(child + ".rotateOrder", 4)
    cmds.setAttr(child + ".rotateAxis", 10, 0, 0)
    target = vecmath.matrix_from_euler((-20, 70, 15))
    maya_ikfk.set_world_rotation(child, target)
    result = maya_ikfk.world_rotation(child)
    for row_a, row_b in zip(result, target):
        assert vecmath.distance(row_a, row_b) < 1e-5


def test_ik_fk_switch_round_trip():
    cmds.file(new=True, force=True)
    cmds.select(clear=True)
    chain = [cmds.joint(name=n, position=p) for n, p in
             (("a0", (0, 10, 0)), ("a1", (3, 10, -0.5)), ("a2", (6, 10, 0)))]
    fk = []
    parent = None
    for joint in chain:
        ctl = cmds.group(empty=True, name=joint + "_fk_ctl", parent=parent) if parent \
            else cmds.group(empty=True, name=joint + "_fk_ctl")
        cmds.matchTransform(ctl, joint)
        fk.append(ctl)
        parent = ctl
    ik = cmds.group(empty=True, name="ik_ctl")
    pole = cmds.group(empty=True, name="pole_ctl")
    host = cmds.group(empty=True, name="ui_ctl")
    cmds.addAttr(host, longName="blend", minValue=0, maxValue=1, defaultValue=1)
    spec = limb_config.parse({"limbs": {"arm": {
        "blend_attr": host + ".blend", "chain": chain, "fk": fk,
        "ik": ik, "pole": pole, "up_axis": "-z",
    }}})["arm"]

    assert maya_ikfk.switch(spec) == "fk"
    root, mid, end = (maya_ikfk.world_position(n) for n in chain)
    _, _, fk_end = ikfk.chain_positions(
        maya_ikfk.world_position(fk[0]), maya_ikfk.world_rotation(fk[0]),
        maya_ikfk.world_rotation(fk[1]), vecmath.distance(root, mid),
        vecmath.distance(mid, end),
    )
    assert vecmath.distance(fk_end, end) < 1e-4

    assert maya_ikfk.switch(spec) == "ik"
    assert vecmath.distance(maya_ikfk.world_position(ik), end) < 1e-4
