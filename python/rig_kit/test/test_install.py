"""Tests for rig_kit.install that do not need Maya."""

import os
import sys
import types

import pytest

from rig_kit import __version__
from rig_kit import install

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def test_module_text_sets_python_deps_and_mgear_paths():
    root = os.path.join(os.path.abspath(os.sep), "tools", "maya-rig-kit")
    lines = install.module_text(root).splitlines()
    assert lines[0] == "+ rig_kit {0} {1}".format(__version__, root.replace("\\", "/"))
    assert "\\" not in lines[0]
    assert lines[1:] == [
        "PYTHONPATH +:= python",
        "PYTHONPATH +:= deps",
        "MGEAR_SHIFTER_COMPONENT_PATH +:= python/rig_kit/shifter_components",
    ]


def test_write_module_file(tmp_path):
    modules = str(tmp_path / "modules")
    path = install.write_module_file(REPO_ROOT, modules)
    with open(path, encoding="utf-8") as handle:
        assert handle.read() == install.module_text(REPO_ROOT)
    with pytest.raises(FileNotFoundError, match="Missing rig_kit package"):
        install.write_module_file(str(tmp_path), modules)


def test_add_to_session_adds_paths_and_component_folder_once(monkeypatch):
    python_dir = os.path.normpath(os.path.join(REPO_ROOT, "python"))
    monkeypatch.setattr(sys, "path", [p for p in sys.path if os.path.normpath(p) != python_dir])
    monkeypatch.setenv(install.COMPONENT_ENV, "/other/components")
    install.add_to_session(REPO_ROOT)
    install.add_to_session(REPO_ROOT)
    assert [os.path.normpath(p) for p in sys.path].count(python_dir) == 1
    entries = os.environ[install.COMPONENT_ENV].split(os.pathsep)
    assert entries[0] == "/other/components"
    assert len(entries) == 2
    assert os.path.isdir(os.path.join(entries[1], "wheel_01"))


def test_ensure_yaml_does_nothing_when_present():
    def runner(*args, **kwargs):
        raise AssertionError("pip should not run")

    assert install.ensure_yaml(REPO_ROOT, runner=runner) == "present"


def test_ensure_yaml_installs_into_deps(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.setattr(sys, "path", list(sys.path))
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    assert install.ensure_yaml(str(tmp_path), runner=runner, python="mayapy") == "installed"
    deps = os.path.join(str(tmp_path), "deps")
    assert calls == [["mayapy", "-m", "pip", "install", "--target", deps, "PyYAML"]]
    assert deps in sys.path


def test_ensure_yaml_reports_pip_failure(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "yaml", None)

    def runner(command, **kwargs):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="no network")

    status = install.ensure_yaml(str(tmp_path), runner=runner, python="mayapy")
    assert status == "PyYAML install failed: no network"
