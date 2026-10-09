"""Match and switch two-bone limbs between IK and FK in Maya.

Reads the limb pose from the nodes listed in a :mod:`rig_kit.limb_config`
file, computes the target pose with :mod:`rig_kit.ikfk` and writes it to the
controls. Rotations are converted into each control's local space, taking its
parent, rotate order, ``rotateAxis`` and (for joints) ``jointOrient`` into
account, so the controls can be built any way the rig needs.

Example::

    from rig_kit import limb_config, maya_ikfk
    limbs = limb_config.load("limbs_mgear_biped.yaml")
    maya_ikfk.switch(limbs["arm_L"], key=True)

"""

from maya import cmds

from rig_kit import ikfk
from rig_kit import vecmath


def world_position(node):
    """Return the world-space position of a node's transform.

    Args:
        node (str): Transform name.

    Returns:
        tuple: World position.

    """
    _, translation = vecmath.split_matrix(
        cmds.xform(node, query=True, worldSpace=True, matrix=True)
    )
    return translation


def world_rotation(node):
    """Return the world-space rotation of a node without scale.

    Args:
        node (str): Transform name.

    Returns:
        tuple: 3x3 orthonormal rotation matrix.

    """
    rows, _ = vecmath.split_matrix(
        cmds.xform(node, query=True, worldSpace=True, matrix=True)
    )
    return vecmath.orthonormalize(rows)


def set_world_rotation(node, rotation):
    """Rotate a node so its world orientation matches ``rotation``.

    Args:
        node (str): Transform or joint name.
        rotation (tuple): 3x3 world rotation matrix.

    """
    parent_inverse, _ = vecmath.split_matrix(
        cmds.getAttr(node + ".parentInverseMatrix[0]")
    )
    local = vecmath.mat_mul(rotation, vecmath.orthonormalize(parent_inverse))

    # Maya composes rotation as rotateAxis * rotate * jointOrient (row vectors).
    rotate_axis = vecmath.matrix_from_euler(cmds.getAttr(node + ".rotateAxis")[0])
    local = vecmath.mat_mul(vecmath.transpose(rotate_axis), local)
    if cmds.objectType(node, isAType="joint"):
        orient = vecmath.matrix_from_euler(cmds.getAttr(node + ".jointOrient")[0])
        local = vecmath.mat_mul(local, vecmath.transpose(orient))

    order = vecmath.ROTATE_ORDERS[cmds.getAttr(node + ".rotateOrder")]
    current = cmds.getAttr(node + ".rotate")[0]
    euler = vecmath.closest_euler(vecmath.euler_from_matrix(local, order), current)
    _set_channels(node, ("rx", "ry", "rz"), euler)


def set_world_position(node, position):
    """Move a node so its transform sits at ``position`` in world space.

    Args:
        node (str): Transform name.
        position (tuple): World position.

    """
    cmds.xform(node, worldSpace=True, translation=list(position))


def _set_channels(node, channels, values):
    """Set channels, skipping any that are locked or connected."""
    for channel, value in zip(channels, values):
        plug = "{0}.{1}".format(node, channel)
        if cmds.getAttr(plug, settable=True):
            cmds.setAttr(plug, value)


def _chain_pose(spec):
    """Read root, mid and end positions plus the end rotation of a limb."""
    root, mid, end = (world_position(node) for node in spec.chain)
    return root, mid, end, world_rotation(spec.chain[2])


def is_ik(spec):
    """Return True when the limb's blend attribute is closer to IK than FK.

    Args:
        spec (LimbSpec): Limb description.

    Returns:
        bool: Whether the limb currently runs in IK.

    """
    value = cmds.getAttr(spec.blend_attr)
    return abs(value - spec.ik_value) < abs(value - spec.fk_value)


def match_fk_to_ik(spec, key=False):
    """Pose the FK controls on the IK limb and switch to FK.

    Args:
        spec (LimbSpec): Limb description.
        key (bool): Set keys on the FK controls and the blend attribute.

    """
    root, mid, end, end_rotation = _chain_pose(spec)
    pose = ikfk.fk_from_ik(
        root, mid, end, end_rotation,
        aim_axis=spec.aim_axis, up_axis=spec.up_axis,
    )
    # Parents first: each child reads its parent's freshly updated matrix.
    for control, rotation in zip(spec.fk, (pose.upper, pose.lower, pose.end)):
        set_world_rotation(control, rotation)
    cmds.setAttr(spec.blend_attr, spec.fk_value)
    if key:
        _key(list(spec.fk), spec.blend_attr)


def match_ik_to_fk(spec, key=False):
    """Place the IK handle and pole vector on the FK limb and switch to IK.

    Args:
        spec (LimbSpec): Limb description.
        key (bool): Set keys on the IK controls and the blend attribute.

    """
    root, mid, end, end_rotation = _chain_pose(spec)
    pose = ikfk.ik_from_fk(
        root, mid, end, end_rotation, pole_distance=spec.pole_distance,
    )
    set_world_position(spec.ik, pose.handle_position)
    if spec.match_ik_rotation:
        set_world_rotation(spec.ik, pose.handle_rotation)
    set_world_position(spec.pole, pose.pole_position)
    cmds.setAttr(spec.blend_attr, spec.ik_value)
    if key:
        _key([spec.ik, spec.pole], spec.blend_attr)


def switch(spec, key=False):
    """Match the inactive side to the current pose and flip the limb mode.

    Args:
        spec (LimbSpec): Limb description.
        key (bool): Set keys on the matched controls.

    Returns:
        str: ``"fk"`` or ``"ik"``, the mode the limb is in afterwards.

    """
    cmds.undoInfo(openChunk=True, chunkName="rig_kit_ikfk_switch")
    try:
        if is_ik(spec):
            match_fk_to_ik(spec, key=key)
            return "fk"
        match_ik_to_fk(spec, key=key)
        return "ik"
    finally:
        cmds.undoInfo(closeChunk=True)


def _key(controls, blend_attr):
    """Key transform channels on controls and the blend attribute."""
    cmds.setKeyframe(controls, attribute=["translate", "rotate"])
    node, attr = blend_attr.split(".", 1)
    cmds.setKeyframe(node, attribute=attr)
