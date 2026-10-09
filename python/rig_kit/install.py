"""Install rig_kit for one Maya user without touching environment setup.

Writes a Maya module file (``rig_kit.mod``) into the user's modules folder.
At startup Maya then adds the ``python`` and ``deps`` folders to
``sys.path`` and the wheel component folder to
``MGEAR_SHIFTER_COMPONENT_PATH``. Stock Maya has no PyYAML, which the limb
and validation configs need, so the installer pip-installs it into the
repo's ``deps`` folder with Maya's own Python. Finally it builds a
"RigKit" shelf. ``install_rig_kit.py`` at the repo root calls ``run``.

"""

import importlib
import os
import subprocess
import sys

from rig_kit import __version__

MODULE_NAME = "rig_kit"
MOD_FILE = MODULE_NAME + ".mod"
DEPS_DIR = "deps"
COMPONENTS_DIR = "python/rig_kit/shifter_components"
COMPONENT_ENV = "MGEAR_SHIFTER_COMPONENT_PATH"
SHELF_NAME = "RigKit"
SHELF_ICON = "pythonFamily.png"
SHELF_BUTTONS = (
    ("Proxy", "Build per-joint proxy pieces from the selected skinned mesh",
     "build_proxies_from_selection()"),
    ("IK/FK", "Switch IK/FK on the limbs of the selected controls",
     "switch_selected_limbs()"),
    ("Check", "Validate the rig in this scene and show the report",
     "check_scene()"),
)


def module_text(root):
    """Return the contents of the module file for a repo folder.

    Args:
        root (str): Folder that holds ``python/rig_kit``.

    Returns:
        str: Module file text with forward slashes.

    """
    path = os.path.abspath(root).replace("\\", "/")
    lines = [
        "+ {0} {1} {2}".format(MODULE_NAME, __version__, path),
        "PYTHONPATH +:= python",
        "PYTHONPATH +:= {0}".format(DEPS_DIR),
        "{0} +:= {1}".format(COMPONENT_ENV, COMPONENTS_DIR),
    ]
    return "\n".join(lines) + "\n"


def write_module_file(root, modules_dir):
    """Write (or overwrite) the module file.

    Args:
        root (str): Folder that holds ``python/rig_kit``.
        modules_dir (str): The user's Maya modules folder.

    Returns:
        str: Path of the written file.

    Raises:
        FileNotFoundError: If ``root`` does not contain the package.

    """
    package = os.path.join(root, "python", MODULE_NAME)
    if not os.path.isdir(package):
        raise FileNotFoundError("Missing rig_kit package: {0}".format(package))
    if not os.path.isdir(modules_dir):
        os.makedirs(modules_dir)
    path = os.path.join(modules_dir, MOD_FILE)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(module_text(root))
    return path


def add_to_session(root):
    """Set up paths for the running session, like the module file will.

    Args:
        root (str): Folder that holds ``python/rig_kit``.

    Returns:
        list: The folders that are now on ``sys.path``.

    """
    root = os.path.abspath(root)
    folders = [os.path.normpath(os.path.join(root, name)) for name in ("python", DEPS_DIR)]
    current = [os.path.normpath(entry) for entry in sys.path]
    for folder in folders:
        if folder not in current:
            sys.path.append(folder)
    components = os.path.normpath(os.path.join(root, COMPONENTS_DIR))
    existing = [entry for entry in os.environ.get(COMPONENT_ENV, "").split(os.pathsep) if entry]
    if components not in [os.path.normpath(entry) for entry in existing]:
        os.environ[COMPONENT_ENV] = os.pathsep.join(existing + [components])
    return folders


def ensure_yaml(root, runner=subprocess.run, python=None):
    """Make PyYAML importable, installing it into ``deps`` if needed.

    Args:
        root (str): Repo folder; PyYAML goes into ``<root>/deps``.
        runner (callable): ``subprocess.run`` or a stand-in for tests.
        python (str): Interpreter to run pip with; defaults to ``mayapy``.

    Returns:
        str: ``"present"``, ``"installed"`` or an error message.

    """
    try:
        import yaml  # noqa: F401

        return "present"
    except ImportError:
        pass
    target = os.path.join(os.path.abspath(root), DEPS_DIR)
    command = [python or mayapy_path(), "-m", "pip", "install", "--target", target, "PyYAML"]
    result = runner(command, capture_output=True, text=True)
    if result.returncode != 0:
        return "PyYAML install failed: {0}".format((result.stderr or result.stdout).strip()[-300:])
    if target not in sys.path:
        sys.path.append(target)
    importlib.invalidate_caches()
    return "installed"


def mayapy_path():
    """Return Maya's standalone interpreter next to the running executable.

    Returns:
        str: Path to ``mayapy`` (``mayapy.exe`` on Windows).

    """
    folder = os.path.dirname(sys.executable)
    name = "mayapy.exe" if os.name == "nt" else "mayapy"
    return os.path.join(folder, name)


def user_modules_dir():
    """Return the current user's Maya modules folder.

    Returns:
        str: ``<user app dir>/modules``.

    """
    from maya import cmds

    return os.path.join(cmds.internalVar(userAppDir=True), "modules")


def build_shelf():
    """Create (or refresh) the RigKit shelf with one button per action.

    Returns:
        str: The shelf name, or None when Maya has no shelves (batch mode).

    """
    from maya import cmds
    from maya import mel

    # In batch mode the shelf variable is not declared; checking first avoids
    # a MEL error in the log.
    if mel.eval('whatIs "$gShelfTopLevel"') == "Unknown":
        return None
    top_level = mel.eval("$rigKitShelfTop = $gShelfTopLevel")
    if not top_level or not cmds.tabLayout(top_level, exists=True):
        return None
    if cmds.shelfLayout(SHELF_NAME, exists=True):
        for child in cmds.shelfLayout(SHELF_NAME, query=True, childArray=True) or []:
            cmds.deleteUI(child)
        shelf = SHELF_NAME
    else:
        shelf = cmds.shelfLayout(SHELF_NAME, parent=top_level)
    for label, annotation, call in SHELF_BUTTONS:
        cmds.shelfButton(
            parent=shelf,
            label=label,
            annotation=annotation,
            image=SHELF_ICON,
            imageOverlayLabel=label,
            sourceType="python",
            command="from rig_kit import maya_shelf\nmaya_shelf.{0}".format(call),
        )
    return shelf


def run(root, modules_dir=None, runner=subprocess.run):
    """Install for the current user and print what was done.

    Args:
        root (str): Folder that holds ``python/rig_kit``.
        modules_dir (str): Modules folder; defaults to the user's.
        runner (callable): Used to run pip; replaced in tests.

    Returns:
        dict: ``module_file``, ``yaml`` and ``shelf``.

    """
    module_file = write_module_file(root, modules_dir or user_modules_dir())
    add_to_session(root)
    yaml_status = ensure_yaml(root, runner=runner)
    shelf = build_shelf()
    print("=" * 60)
    print(f"rig_kit {__version__} installed")
    print(f"  module file : {module_file}")
    print(f"  PyYAML      : {yaml_status}")
    print(f"  shelf       : {shelf or 'none (no shelves in this session)'}")
    print("  mGear       : wheel_01 is on " + COMPONENT_ENV)
    print("=" * 60)
    return {"module_file": module_file, "yaml": yaml_status, "shelf": shelf}
