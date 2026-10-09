# -*- coding: utf-8 -*-
name = "rig_kit"

version = "1.0.0"

authors = ["Arsam Ali"]

description = (
    "Rigging toolkit for Maya: skin-weight proxy segmentation, IK/FK "
    "matching, rig validation reports and an mGear Shifter wheel component."
)

requires = [
    "python-3.7+",
    "PyYAML",
]

tools = ["rig-kit"]


def commands():
    env.PYTHONPATH.append("{root}/python")
    env.MGEAR_SHIFTER_COMPONENT_PATH.append("{root}/python/rig_kit/shifter_components")
