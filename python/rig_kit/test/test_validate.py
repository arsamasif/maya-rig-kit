"""Tests for rig_kit.validate, rig_kit.report and the validate CLI."""

import json
import os

import pytest

from rig_kit import cli
from rig_kit import report
from rig_kit import validate

EXAMPLE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "examples", "rig_description.json"
)


def _control(name="arm_L0_fk0_ctl", locked=("v",), keyable=("rx",), **values):
    channels = {"tx": 0.0, "ty": 0.0, "tz": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0,
                "sx": 1.0, "sy": 1.0, "sz": 1.0, "v": 1.0}
    channels.update(values)
    return {"name": name, "values": channels, "locked": list(locked), "keyable": list(keyable)}


def _rules(issues):
    return sorted({issue.rule for issue in issues})


def test_clean_rig_passes():
    rig = {
        "controls": [_control()],
        "joints": [{"name": "arm_L0_0_jnt", "deform": True}],
        "skin_clusters": [{"name": "sc", "influences": ["arm_L0_0_jnt"],
                           "max_influences_found": 4}],
    }
    assert validate.run(rig) == []


def test_control_values_flags_offsets_beyond_tolerance():
    rig = {"controls": [_control(ry=12.5, sx=1.00001)]}
    issues = validate.run(rig, rules=["control_values"])
    assert len(issues) == 1
    assert "ry=12.5" in issues[0].message and "sx" not in issues[0].message


def test_locked_channels_only_flags_keyable_open_channels():
    rig = {"controls": [
        _control("a_L0_ctl", locked=(), keyable=("v",)),
        _control("b_L0_ctl", locked=(), keyable=()),
    ]}
    issues = validate.run(rig, rules=["locked_channels"])
    assert [issue.node for issue in issues] == ["a_L0_ctl"]


def test_unused_joints_respects_ignore_and_deform_flag():
    rig = {
        "joints": [
            {"name": "a_L0_0_jnt"},
            {"name": "a_L0_end_jnt"},
            {"name": "a_L0_helper_jnt", "deform": False},
            {"name": "a_L0_1_jnt"},
        ],
        "skin_clusters": [{"name": "sc", "influences": ["a_L0_0_jnt"]}],
    }
    issues = validate.run(rig, rules=["unused_joints"])
    assert [issue.node for issue in issues] == ["a_L0_1_jnt"]


def test_max_influences_uses_setting():
    rig = {"skin_clusters": [{"name": "sc", "geometry": "body", "max_influences_found": 6}]}
    assert len(validate.run(rig, rules=["max_influences"])) == 1
    assert validate.run(rig, {"max_influences": 8}, rules=["max_influences"]) == []


def test_naming_checks_controls_and_joints():
    rig = {"controls": [_control("spineCtrl")], "joints": [{"name": "joint1"}]}
    issues = validate.run(rig, rules=["naming"])
    assert sorted(issue.node for issue in issues) == ["joint1", "spineCtrl"]


def test_unique_names_uses_short_names():
    rig = {"controls": [_control("grp|a_L0_ctl"), _control("other|a_L0_ctl")]}
    issues = validate.run(rig, rules=["unique_names"])
    assert issues[0].node == "a_L0_ctl" and "2 times" in issues[0].message


def test_errors_sort_before_warnings():
    with open(EXAMPLE, encoding="utf-8") as handle:
        rig = json.load(handle)
    issues = validate.run(rig)
    severities = [issue.severity for issue in issues]
    assert severities == sorted(severities, key=lambda s: s != validate.ERROR)
    assert _rules(issues) == [
        "control_values", "locked_channels", "max_influences", "naming", "unused_joints",
    ]


@pytest.mark.parametrize("kwargs, message", [
    ({"rules": ["nope"]}, "Unknown rules"),
    ({"settings": {"bogus": 1}}, "Unknown validation settings"),
])
def test_run_rejects_bad_arguments(kwargs, message):
    with pytest.raises(ValueError, match=message):
        validate.run({}, **kwargs)


def test_markdown_report_lists_issues_and_escapes_pipes():
    issues = [validate.Issue("naming", validate.WARNING, "x", "a|b")]
    text = report.to_markdown("hero", issues)
    assert "**PASSED** - 0 error(s), 1 warning(s)" in text
    assert "a\\|b" in text


def test_markdown_report_for_clean_rig():
    assert "No issues found." in report.to_markdown("hero", [])


def test_json_report_round_trips():
    issues = [validate.Issue("max_influences", validate.ERROR, "sc", "too many")]
    data = json.loads(report.to_json("hero", issues))
    assert data["summary"] == {"rig": "hero", "errors": 1, "warnings": 0, "passed": False}
    assert data["issues"][0]["node"] == "sc"


def test_cli_validate_writes_report_and_fails_on_errors(tmp_path, capsys):
    out = tmp_path / "report.json"
    code = cli.main(["validate", EXAMPLE, "--format", "json", "--output", str(out)])
    assert code == 1
    assert json.loads(out.read_text())["summary"]["rig"] == "hero_rig"
    assert "Wrote" in capsys.readouterr().out


def test_cli_validate_passes_with_subset_of_rules(capsys):
    assert cli.main(["validate", EXAMPLE, "--rules", "unique_names"]) == 0
    assert "PASSED" in capsys.readouterr().out


def test_cli_settings_file(tmp_path):
    settings = tmp_path / "settings.yaml"
    settings.write_text("max_influences: 8\n")
    code = cli.main(["validate", EXAMPLE, "--rules", "max_influences",
                     "--settings", str(settings)])
    assert code == 0


def test_cli_missing_file_returns_2(capsys):
    assert cli.main(["validate", "/nope/rig.json"]) == 2
    assert "Missing file" in capsys.readouterr().err
