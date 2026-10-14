"""Actions behind the RigKit shelf buttons.

Each action works on the current selection, reports problems in Maya's
command line instead of raising, and returns what it did so scripts and
tests can call it too. The installer (``install.py``) puts one button per
action on a "RigKit" shelf.

"""

import os

import maya.api.OpenMaya as om
from maya import cmds

from rig_kit import limb_config
from rig_kit import maya_export
from rig_kit import maya_ikfk
from rig_kit import maya_segment
from rig_kit import report
from rig_kit import validate

CONFIG_ENV = "RIG_KIT_LIMB_CONFIG"
VALIDATION_ENV = "RIG_KIT_VALIDATION_CONFIG"
DEFAULT_CONFIG = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "config", "limbs_mgear_biped.yaml")
)


def limb_config_path():
    """Return the limb config the IK/FK button uses.

    Returns:
        str: ``$RIG_KIT_LIMB_CONFIG`` if set, else the mGear biped config
        shipped with the repo.

    """
    return os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG


def build_proxies_from_selection(smooth_iterations=2, min_faces=10):
    """Build proxy pieces for every selected skinned mesh.

    Args:
        smooth_iterations (int): Neighbour voting rounds.
        min_faces (int): Merge islands smaller than this.

    Returns:
        list: Names of all created pieces.

    """
    meshes = cmds.ls(selection=True, long=True, transforms=True) or []
    if not meshes:
        _error("Select a skinned mesh to build proxies from.")
        return []
    pieces = []
    for mesh in meshes:
        try:
            pieces.extend(
                maya_segment.build_proxies(
                    mesh, smooth_iterations=smooth_iterations, min_faces=min_faces
                )
            )
        except (ValueError, RuntimeError) as error:
            _error("{0}: {1}".format(mesh.rsplit("|", 1)[-1], error))
    if pieces:
        _info("Built {0} proxy pieces".format(len(pieces)))
    return pieces


def switch_selected_limbs(config_path=None, key=False):
    """Switch IK/FK on every limb that has a selected node.

    Args:
        config_path (str): Limb config; defaults to ``limb_config_path()``.
        key (bool): Key the controls and the blend attribute.

    Returns:
        dict: Limb name (with namespace) to the mode it switched to.

    """
    path = config_path or limb_config_path()
    try:
        limbs = limb_config.load(path)
    except ImportError:
        _error("PyYAML is missing; drag install_rig_kit.py into Maya again to install it.")
        return {}
    except (OSError, ValueError) as error:
        _error(str(error))
        return {}

    switched = {}
    for node in cmds.ls(selection=True) or []:
        spec = limb_config.find_limb(limbs, node)
        if spec is None:
            continue
        namespace = spec.ik.rpartition(":")[0]
        label = "{0}:{1}".format(namespace, spec.name) if namespace else spec.name
        if label in switched:
            continue
        try:
            switched[label] = maya_ikfk.switch(spec, key=key)
        except (ValueError, RuntimeError) as error:
            _error("{0}: {1}".format(label, error))
    if not switched:
        _error("No selected node belongs to a limb in {0}".format(os.path.basename(path)))
        return {}
    _info(", ".join("{0} -> {1}".format(name, mode) for name, mode in sorted(switched.items())))
    return switched


def validation_settings():
    """Load the validation overrides the Check button uses.

    Returns:
        dict: Overrides from the YAML file in ``$RIG_KIT_VALIDATION_CONFIG``,
        or None when the variable is not set.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not valid YAML or not a mapping.

    """
    path = os.environ.get(VALIDATION_ENV)
    if not path:
        return None
    if not os.path.isfile(path):
        raise FileNotFoundError("Missing validation config: {0}".format(path))
    import yaml

    with open(path, "r", encoding="utf-8") as handle:
        try:
            data = yaml.safe_load(handle) or {}
        except yaml.YAMLError as error:
            raise ValueError("Invalid YAML in {0}: {1}".format(path, error)) from error
    if not isinstance(data, dict):
        raise ValueError("Validation config must be a mapping: {0}".format(path))
    return data


def check_scene(settings=None):
    """Validate the rig in the open scene and show the report.

    The Markdown report goes to the Script Editor; a dialog shows the
    summary when Maya runs with a UI.

    Args:
        settings (dict): Validation setting overrides; defaults to
            ``validation_settings()``.

    Returns:
        list: :class:`rig_kit.validate.Issue` objects.

    """
    try:
        if settings is None:
            settings = validation_settings()
        validate.merged_settings(settings)
    except ImportError:
        _error("PyYAML is missing; drag install_rig_kit.py into Maya again to install it.")
        return []
    except (OSError, ValueError) as error:
        _error(str(error))
        return []
    rig = maya_export.export_rig()
    issues = validate.run(rig, settings)
    print(report.to_markdown(rig["name"], issues))
    counts = report.summary(rig["name"], issues)
    message = "{0}: {1} error(s), {2} warning(s). Full report in the Script Editor.".format(
        "Passed" if counts["passed"] else "Failed", counts["errors"], counts["warnings"]
    )
    if cmds.about(batch=True):
        _info(message)
    else:
        cmds.confirmDialog(title="Rig Check: {0}".format(rig["name"]), message=message, button=["OK"])
    return issues


def _info(message):
    om.MGlobal.displayInfo("rig_kit: " + message)


def _error(message):
    om.MGlobal.displayError("rig_kit: " + message)
