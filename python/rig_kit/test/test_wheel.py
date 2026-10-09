"""Tests for rig_kit.wheel_math and the structure of the wheel_01 component.

mGear is not importable outside Maya, so the component files are parsed with
``ast`` to check that they follow the Shifter component layout.

"""

import ast
import math
import os

import pytest

from rig_kit import wheel_math

COMPONENT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "shifter_components", "wheel_01"
)


def _parse(name):
    with open(os.path.join(COMPONENT_DIR, name), encoding="utf-8") as handle:
        return ast.parse(handle.read())


def _constants(tree):
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return values


def _class_methods(tree, class_name):
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
    raise AssertionError("Class {0} not found".format(class_name))


def test_full_turn_after_one_circumference():
    radius = 0.35
    travel = 2.0 * math.pi * radius
    assert wheel_math.roll_angle(travel, radius) == pytest.approx(360.0)
    assert wheel_math.roll_angle(-travel, radius, degrees=False) == pytest.approx(-2 * math.pi)


def test_travel_projects_onto_forward_axis():
    rest = (1.0, 0.0, 0.0)
    assert wheel_math.travel_distance((1.0, 0.0, 5.0), rest, (0, 0, 2)) == pytest.approx(5.0)
    assert wheel_math.travel_distance((4.0, 0.0, 0.0), rest, (0, 0, 1)) == pytest.approx(0.0)
    assert wheel_math.travel_distance((1.0, 0.0, -3.0), rest, (0, 0, 1)) == pytest.approx(-3.0)


def test_degrees_per_unit_matches_roll_angle():
    assert wheel_math.degrees_per_unit(0.5) == pytest.approx(wheel_math.roll_angle(1.0, 0.5))


def test_non_positive_radius_raises():
    with pytest.raises(ValueError, match="positive"):
        wheel_math.roll_angle(1.0, 0.0)


def test_guide_declares_shifter_metadata():
    constants = _constants(_parse("guide.py"))
    assert constants["TYPE"] == "wheel_01"
    assert constants["NAME"] == "wheel"
    assert constants["AUTHOR"] == "Arsam Ali"
    assert isinstance(constants["VERSION"], list) and len(constants["VERSION"]) == 3
    methods = _class_methods(_parse("guide.py"), "Guide")
    assert {"postInit", "addObjects", "addParameters"} <= methods


def test_component_implements_build_steps():
    methods = _class_methods(_parse("__init__.py"), "Component")
    assert {"addObjects", "addAttributes", "addOperators",
            "setRelation", "addConnection"} <= methods


def test_guide_parameters_used_by_component_exist():
    guide_source = open(os.path.join(COMPONENT_DIR, "guide.py"), encoding="utf-8").read()
    component_source = open(os.path.join(COMPONENT_DIR, "__init__.py"), encoding="utf-8").read()
    used = set()
    for node in ast.walk(ast.parse(component_source)):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
                and node.value.attr == "settings"):
            used.add(ast.literal_eval(node.slice))
    for name in used:
        assert 'addParam("{0}"'.format(name) in guide_source, name
