"""Export a rig description dict from the open Maya scene.

The dict is the input of :mod:`rig_kit.validate`. Exporting first and
validating outside Maya keeps the rules testable and lets a publish step run
the checks on a farm machine against a JSON file.

Controls come from mGear's ``*_controllers_grp`` object sets when present,
otherwise from transforms whose name ends with ``_ctl``. Deform joints come
from ``*_deformers_grp`` sets when present, otherwise every joint counts.

"""

import json

from maya import cmds

from rig_kit import maya_skin

CHANNELS = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v")
CONTROL_SETS = "*_controllers_grp"
DEFORMER_SETS = "*_deformers_grp"
CONTROL_SUFFIX = "_ctl"


def export_rig(name=None):
    """Describe controls, joints and skin clusters of the open scene.

    Args:
        name (str): Rig name for the report. Defaults to the scene file name.

    Returns:
        dict: Rig description understood by :func:`rig_kit.validate.run`.

    """
    if name is None:
        scene = cmds.file(query=True, sceneName=True, shortName=True)
        name = scene.rsplit(".", 1)[0] if scene else "untitled"
    return {
        "name": name,
        "controls": [describe_control(c) for c in find_controls()],
        "joints": describe_joints(),
        "skin_clusters": [describe_skin_cluster(s) for s in cmds.ls(type="skinCluster")],
    }


def write_json(path, rig):
    """Write a rig description to disk.

    Args:
        path (str): Output JSON path.
        rig (dict): Rig description.

    Returns:
        str: The path written.

    """
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(rig, handle, indent=2)
    return path


def _set_members(pattern):
    """Return members of all object sets matching ``pattern``."""
    members = []
    for object_set in cmds.ls(pattern, type="objectSet") or []:
        members.extend(cmds.sets(object_set, query=True) or [])
    return sorted(set(cmds.ls(members)))


def find_controls():
    """Find animation controls in the scene.

    Returns:
        list: Control transform names.

    """
    controls = _set_members(CONTROL_SETS)
    if controls:
        return controls
    return sorted(cmds.ls("*" + CONTROL_SUFFIX, type="transform") or [])


def describe_control(control):
    """Collect channel values, locks and keyable state of a control.

    Args:
        control (str): Control transform name.

    Returns:
        dict: ``name``, ``values``, ``locked`` and ``keyable``.

    """
    values, locked, keyable = {}, [], []
    for channel in CHANNELS:
        if not cmds.attributeQuery(channel, node=control, exists=True):
            continue
        plug = "{0}.{1}".format(control, channel)
        values[channel] = float(cmds.getAttr(plug))
        if cmds.getAttr(plug, lock=True):
            locked.append(channel)
        if cmds.getAttr(plug, keyable=True):
            keyable.append(channel)
    return {"name": control, "values": values, "locked": locked, "keyable": keyable}


def describe_joints():
    """List joints and whether they are meant to deform.

    Returns:
        list: Dicts with ``name`` and ``deform``.

    """
    deformers = set(_set_members(DEFORMER_SETS))
    joints = cmds.ls(type="joint") or []
    return [
        {"name": joint, "deform": (joint in deformers) if deformers else True}
        for joint in joints
    ]


def describe_skin_cluster(skin_cluster):
    """Collect influences and the worst per-vertex influence count.

    Args:
        skin_cluster (str): skinCluster node name.

    Returns:
        dict: ``name``, ``geometry``, ``influences``, ``max_influences_found``
        and the cluster's own ``max_influences_setting``.

    """
    geometry = cmds.skinCluster(skin_cluster, query=True, geometry=True) or []
    influences = cmds.skinCluster(skin_cluster, query=True, influence=True) or []
    found = 0
    for shape in cmds.ls(geometry, type="mesh"):
        _, weights = maya_skin.read_weights(skin_cluster, shape)
        found = max(found, maya_skin.max_influences_found(weights))
    return {
        "name": skin_cluster,
        "geometry": geometry[0] if geometry else "",
        "influences": influences,
        "max_influences_found": found,
        "max_influences_setting": cmds.getAttr(skin_cluster + ".maxInfluences"),
    }
