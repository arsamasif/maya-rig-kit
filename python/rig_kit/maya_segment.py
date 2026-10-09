"""Build animation proxy pieces from a skinned mesh in Maya.

Reads the mesh with :mod:`rig_kit.maya_skin`, runs :func:`rig_kit.segment.segment`
and, per influence, duplicates the mesh, deletes every face it does not own
and parent-constrains the piece to the joint. The result is a light, fast
playback rig that follows the skeleton without any skinning cost.

Example::

    from rig_kit import maya_segment
    maya_segment.build_proxies("body_geo", smooth_iterations=2, min_faces=20)

"""

from maya import cmds

from rig_kit import maya_skin
from rig_kit import segment

PROXY_ATTR = "proxyInfluence"
TRANSFORM_CHANNELS = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")


def build_proxies(mesh, smooth_iterations=2, min_faces=10, group=None,
                  constrain=True):
    """Split a skinned mesh into per-joint proxy pieces.

    Args:
        mesh (str): Skinned mesh transform.
        smooth_iterations (int): Neighbour voting rounds, 0 to disable.
        min_faces (int): Merge islands smaller than this into a neighbour.
        group (str): Name of the group to hold the pieces. Defaults to
            ``<mesh>_proxy_grp``.
        constrain (bool): Parent-constrain each piece to its joint.

    Returns:
        list: Names of the created proxy pieces.

    """
    data = maya_skin.read_skin(mesh)
    result = segment.segment(
        data.faces, data.weights,
        smooth_iterations=smooth_iterations, min_faces=min_faces,
    )
    short_name = mesh.split("|")[-1]
    cmds.undoInfo(openChunk=True, chunkName="rig_kit_build_proxies")
    try:
        root = cmds.group(empty=True, name=group or "{0}_proxy_grp".format(short_name))
        pieces = []
        for influence, faces in result.pieces.items():
            joint = data.influences[influence]
            name = "{0}_{1}_proxy".format(short_name, joint.split("|")[-1])
            piece = extract_faces(mesh, faces, len(data.faces), name)
            piece = cmds.parent(piece, root)[0]
            _tag(piece, joint)
            if constrain:
                cmds.parentConstraint(joint, piece, maintainOffset=True)
            pieces.append(piece)
    finally:
        cmds.undoInfo(closeChunk=True)
    return pieces


def extract_faces(mesh, keep_faces, face_count, name):
    """Duplicate ``mesh`` and keep only ``keep_faces``.

    Args:
        mesh (str): Source mesh transform.
        keep_faces (list): Face indices to keep.
        face_count (int): Total face count of the source mesh.
        name (str): Name for the duplicate.

    Returns:
        str: Name of the new mesh transform, without history.

    """
    duplicate = cmds.duplicate(mesh, name=name)[0]
    _delete_intermediate_shapes(duplicate)
    _unlock_transform(duplicate)

    keep = set(keep_faces)
    drop = [index for index in range(face_count) if index not in keep]
    if drop:
        cmds.delete([
            "{0}.f[{1}:{2}]".format(duplicate, start, end)
            for start, end in segment.compress_indices(drop)
        ])
    cmds.delete(duplicate, constructionHistory=True)
    return duplicate


def _delete_intermediate_shapes(node):
    """Remove the Orig shapes a skinned mesh duplicate carries along."""
    for shape in cmds.listRelatives(node, shapes=True, fullPath=True) or []:
        if cmds.getAttr(shape + ".intermediateObject"):
            cmds.delete(shape)


def _unlock_transform(node):
    """Unlock transform channels so the piece can be constrained."""
    for channel in TRANSFORM_CHANNELS:
        cmds.setAttr("{0}.{1}".format(node, channel), lock=False)


def _tag(piece, joint):
    """Store the driving joint on the piece for later rebuilds."""
    if not cmds.attributeQuery(PROXY_ATTR, node=piece, exists=True):
        cmds.addAttr(piece, longName=PROXY_ATTR, dataType="string")
    cmds.setAttr("{0}.{1}".format(piece, PROXY_ATTR), joint, type="string")
