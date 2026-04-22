"""Tests for project_context.py — repo scanning, ignore patterns, project summary."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


class TestLoadIgnorePatterns:
    def test_no_ignore_file(self, tmp_path):
        from code_agents.domain.project_context import load_ignore_patterns
        assert load_ignore_patterns(str(tmp_path)) == []

    def test_ignore_file_with_patterns(self, tmp_path):
        from code_agents.domain.project_context import load_ignore_patterns
        ignore_dir = tmp_path / ".code-agents"
        ignore_dir.mkdir()
        (ignore_dir / ".ignore").write_text("*.log\n# comment\n/vendor/\n!important.log\n\n")
        patterns = load_ignore_patterns(str(tmp_path))
        assert "*.log" in patterns
        assert "/vendor/" in patterns
        assert "!important.log" in patterns
        assert "# comment" not in patterns
        assert "" not in patterns


class TestShouldIgnore:
    def test_always_skip(self):
        from code_agents.domain.project_context import _should_ignore
        assert _should_ignore("node_modules", "node_modules", []) is True
        assert _should_ignore(".git", ".git", []) is True
        assert _should_ignore("__pycache__", "__pycache__", []) is True

    def test_pattern_match(self):
        from code_agents.domain.project_context import _should_ignore
        assert _should_ignore("app.log", "app.log", ["*.log"]) is True
        assert _should_ignore("app.py", "app.py", ["*.log"]) is False

    def test_negation_overrides(self):
        from code_agents.domain.project_context import _should_ignore
        assert _should_ignore("important.log", "important.log", ["*.log", "!important.log"]) is False

    def test_no_patterns(self):
        from code_agents.domain.project_context import _should_ignore
        assert _should_ignore("src/main.py", "main.py", []) is False


class TestScanProject:
    def test_scan_python_project(self, tmp_path):
        from code_agents.domain.project_context import scan_project
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'myapp'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("def test_main(): pass")
        (tmp_path / "README.md").write_text("# My App")

        result = scan_project(str(tmp_path))
        assert "Python" in result["languages"]
        assert "pyproject.toml" in result["key_files"]
        assert "README.md" in result["key_files"]
        assert "src/" in result["structure"]

    def test_scan_empty_dir(self, tmp_path):
        from code_agents.domain.project_context import scan_project
        result = scan_project(str(tmp_path))
        assert result["languages"] == []
        assert result["file_count"] == 0

    def test_scan_respects_ignore(self, tmp_path):
        from code_agents.domain.project_context import scan_project
        (tmp_path / ".code-agents").mkdir()
        (tmp_path / ".code-agents" / ".ignore").write_text("secret*\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("x = 1")
        (tmp_path / "secrets").mkdir()
        (tmp_path / "secrets" / "key.pem").write_text("PRIVATE")

        result = scan_project(str(tmp_path))
        assert "secrets/" not in result["structure"]
        assert "src/" in result["structure"]

    def test_scan_nonexistent(self):
        from code_agents.domain.project_context import scan_project
        assert scan_project("/nonexistent/path") == {}


class TestBuildProjectSummary:
    def test_summary_has_key_info(self, tmp_path):
        from code_agents.domain.project_context import build_project_summary
        (tmp_path / "pom.xml").write_text("<project><spring-boot></spring-boot></project>")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "Main.java").write_text("class Main {}")
        (tmp_path / "Dockerfile").write_text("FROM java:17")

        summary = build_project_summary(str(tmp_path))
        assert "Java" in summary
        assert "Dockerfile" in summary

    def test_summary_empty_project(self, tmp_path):
        from code_agents.domain.project_context import build_project_summary
        summary = build_project_summary(str(tmp_path))
        # Empty project may have no languages/files
        assert isinstance(summary, str)

    def test_summary_nonexistent(self):
        from code_agents.domain.project_context import build_project_summary
        assert build_project_summary("/nonexistent") == ""
