"""Drag this file into the Maya viewport to install rig_kit.

Maya runs a dropped Python file and calls ``onMayaDroppedPythonFile``. The
function finds this repo folder and hands over to ``rig_kit.install.run``,
which writes a module file for the current user, installs PyYAML if Maya
lacks it, and builds the RigKit shelf.

"""

import os
import sys


def _repo_root():
    # Maya does not always set __file__ for dropped files, so the path comes
    # from this function's code object instead.
    return os.path.dirname(os.path.abspath(_repo_root.__code__.co_filename))


def onMayaDroppedPythonFile(*args):
    """Entry point Maya calls when the file is dropped into the viewport."""
    root = _repo_root()
    python_dir = os.path.join(root, "python")
    if python_dir not in sys.path:
        sys.path.insert(0, python_dir)
    from rig_kit import install

    try:
        install.run(root)
    finally:
        # Maya imports dropped files as modules named after the file, and a
        # cached module would be reused on the next drop. Forgetting it here
        # makes a re-drop run the current file.
        sys.modules.pop(__name__, None)
