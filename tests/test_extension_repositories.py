"""Tests for extension package.json repository validation (vsce)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_agents.tools.extension_repositories import (
    EXTENSION_PACKAGES,
    DEFAULT_REPO_HTTPS,
    apply_default_repositories,
    format_validation_failure,
    validate_extension_repositories,
    _normalize_git_url_to_https,
    _parse_repository,
)


def test_normalize_git_ssh_to_https():
    assert _normalize_git_url_to_https("git@github.com:code-agents-org/code-agents.git").startswith(
        "https://bitbucket.org/"
    )


def test_parse_repository_missing():
    ok, msg = _parse_repository({})
    assert not ok
    assert "missing" in msg.lower()


def test_parse_repository_object_ok():
    ok, msg = _parse_repository(
        {"repository": {"type": "git", "url": "https://example.com/x.git", "directory": "ext/vscode"}},
    )
    assert ok and not msg


def test_validate_extension_repositories_ok_repo(tmp_path: Path):
    root = tmp_path / "repo"
    for rel, _ in EXTENSION_PACKAGES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        pkg = {
            "name": "x",
            "repository": {
                "type": "git",
                "url": DEFAULT_REPO_HTTPS,
                "directory": dict(EXTENSION_PACKAGES)[rel],
            },
        }
        (root / rel).write_text(json.dumps(pkg), encoding="utf-8")
    ok, errs = validate_extension_repositories(root)
    assert ok, errs


def test_validate_extension_repositories_missing_directory(tmp_path: Path):
    root = tmp_path / "repo"
    rel = "extensions/vscode/package.json"
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(
        json.dumps(
            {
                "name": "x",
                "repository": {"type": "git", "url": DEFAULT_REPO_HTTPS},
            }
        ),
        encoding="utf-8",
    )
    ok, errs = validate_extension_repositories(root)
    assert not ok
    assert any("directory" in e.lower() for e in errs)


def test_format_validation_failure_contains_hint(tmp_path: Path):
    text = format_validation_failure(tmp_path, ["extensions/vscode/package.json: missing"])
    assert "repository" in text.lower()
    assert "vsce" in text.lower() or "@vscode" in text


def test_apply_default_repositories_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "repo"
    for rel, _ in EXTENSION_PACKAGES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(json.dumps({"name": "x"}), encoding="utf-8")

    monkeypatch.setattr(
        "code_agents.tools.extension_repositories._git_remote_https",
        lambda _: "https://bitbucket.org/org/repo.git",
    )
    ok, msgs = apply_default_repositories(root, dry_run=True)
    assert ok
    assert any("would write" in m.lower() for m in msgs)
