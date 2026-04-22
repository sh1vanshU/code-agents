"""Tests for code_agents.tools.vscode_extension."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.tools import vscode_extension as vx


def test_vscode_extension_dir():
    root = Path("/tmp/fake/repo")
    assert vx.vscode_extension_dir(root) == root / "extensions" / "vscode"


def test_newest_vsix_empty(tmp_path: Path):
    d = tmp_path / "vscode"
    d.mkdir()
    assert vx.newest_vsix(d) is None


def test_newest_vsix_picks_newer(tmp_path: Path):
    d = tmp_path / "vscode"
    d.mkdir()
    old = d / "a.vsix"
    new = d / "b.vsix"
    old.write_text("x")
    time.sleep(0.02)
    new.write_text("y")
    assert vx.newest_vsix(d) == new


def test_build_vscode_extension_invokes_npm_scripts(tmp_path: Path):
    d = tmp_path / "vscode"
    d.mkdir()
    (d / "package.json").write_text("{}")
    calls: list[tuple[str, ...]] = []

    def fake_run(cmd, **kwargs):
        calls.append(tuple(cmd))
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    with patch("subprocess.run", side_effect=fake_run):
        vx.build_vscode_extension(d, capture_output=False)
    assert calls[0][0] == "npm"
    assert "install" in calls[0]
    assert list(calls[1]) == ["npm", "run", "build:webview"]
    assert list(calls[2]) == ["npm", "run", "compile"]


def test_main_build_requires_package_json(tmp_path: Path):
    assert vx.main(["build", "--root", str(tmp_path)]) == 1
