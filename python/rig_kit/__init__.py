"""Rigging toolkit for Maya: proxy segmentation, IK/FK matching, validation.

The pure-Python modules (``segment``, ``ikfk``, ``vecmath``, ``validate``,
``report``, ``wheel_math``) import without Maya. The ``maya_*`` modules are
thin adapters that read and write scene data through ``maya.cmds`` and
``maya.api``. An mGear Shifter component lives in ``shifter_components``.

"""

__version__ = "1.0.0"
