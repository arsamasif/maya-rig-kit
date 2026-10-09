"""Read skinned mesh data from Maya into plain Python structures.

Uses ``maya.api.OpenMayaAnim.MFnSkinCluster.getWeights`` to pull every
vertex weight in a single call, which is orders of magnitude faster than
querying ``skinPercent`` per vertex on production meshes.

"""

from dataclasses import dataclass

from maya import cmds
from maya.api import OpenMaya as om
from maya.api import OpenMayaAnim as oma

WEIGHT_EPSILON = 1e-6


@dataclass
class SkinData:
    """Topology and weights of one skinned mesh.

    Attributes:
        mesh (str): Transform name of the mesh.
        shape (str): Full path of the deformed (non-intermediate) shape.
        skin_cluster (str): Name of the skinCluster node.
        influences (list): Influence names, in weight column order.
        faces (list): Vertex index tuples per face.
        weights (list): ``{influence index: weight}`` per vertex.

    """

    mesh: str
    shape: str
    skin_cluster: str
    influences: list
    faces: list
    weights: list


def find_skin_cluster(mesh):
    """Return the skinCluster deforming ``mesh``.

    Args:
        mesh (str): Mesh transform or shape name.

    Returns:
        str: skinCluster node name.

    Raises:
        ValueError: If the mesh does not exist or has no skinCluster.

    """
    if not cmds.objExists(mesh):
        raise ValueError("Mesh does not exist: {0}".format(mesh))
    history = cmds.listHistory(mesh, pruneDagObjects=True) or []
    clusters = cmds.ls(history, type="skinCluster")
    if not clusters:
        raise ValueError("No skinCluster found on {0}".format(mesh))
    return clusters[0]


def deformed_shape(mesh):
    """Return the full path of the visible (non-intermediate) mesh shape.

    Args:
        mesh (str): Mesh transform name.

    Returns:
        str: Full DAG path of the shape.

    Raises:
        ValueError: If no mesh shape is found.

    """
    shapes = cmds.listRelatives(
        mesh, shapes=True, noIntermediate=True, fullPath=True, type="mesh"
    ) or []
    if not shapes:
        raise ValueError("No mesh shape under {0}".format(mesh))
    return shapes[0]


def _mobject(name):
    """Return the MObject for a dependency node name."""
    selection = om.MSelectionList()
    selection.add(name)
    return selection.getDependNode(0)


def _dag_path(name):
    """Return the MDagPath for a DAG node name."""
    selection = om.MSelectionList()
    selection.add(name)
    return selection.getDagPath(0)


def read_faces(shape):
    """Read face vertex indices with one MFnMesh call.

    Args:
        shape (str): Mesh shape name.

    Returns:
        list: Vertex index tuples, one per face.

    """
    counts, connects = om.MFnMesh(_dag_path(shape)).getVertices()
    faces, cursor = [], 0
    for count in counts:
        faces.append(tuple(connects[cursor:cursor + count]))
        cursor += count
    return faces


def read_weights(skin_cluster, shape):
    """Read all vertex weights of a skinned shape.

    Args:
        skin_cluster (str): skinCluster node name.
        shape (str): Deformed mesh shape name.

    Returns:
        tuple: ``(influence names, list of {influence index: weight})``.

    """
    skin_fn = oma.MFnSkinCluster(_mobject(skin_cluster))
    shape_path = _dag_path(shape)

    component_fn = om.MFnSingleIndexedComponent()
    components = component_fn.create(om.MFn.kMeshVertComponent)
    component_fn.setCompleteData(om.MFnMesh(shape_path).numVertices)

    flat, influence_count = skin_fn.getWeights(shape_path, components)
    influences = [path.partialPathName() for path in skin_fn.influenceObjects()]

    weights = []
    for start in range(0, len(flat), influence_count):
        row = flat[start:start + influence_count]
        weights.append({i: w for i, w in enumerate(row) if w > WEIGHT_EPSILON})
    return influences, weights


def read_skin(mesh):
    """Collect topology and weights for a skinned mesh.

    Args:
        mesh (str): Mesh transform name.

    Returns:
        SkinData: Everything the segmentation algorithm needs.

    """
    skin_cluster = find_skin_cluster(mesh)
    shape = deformed_shape(mesh)
    influences, weights = read_weights(skin_cluster, shape)
    return SkinData(
        mesh=mesh,
        shape=shape,
        skin_cluster=skin_cluster,
        influences=influences,
        faces=read_faces(shape),
        weights=weights,
    )


def max_influences_found(weights):
    """Return the largest number of non-zero influences on any vertex.

    Args:
        weights (list): ``{influence index: weight}`` per vertex.

    Returns:
        int: Highest influence count, 0 for an empty list.

    """
    return max((len(row) for row in weights), default=0)
