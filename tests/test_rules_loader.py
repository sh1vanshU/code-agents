"""Tests for rules_loader.py — rules file discovery, loading, and merging."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.agent_system.rules_loader import (
    GLOBAL_RULES_DIR,
    PROJECT_RULES_DIRNAME,
    _read_rules_dir,
    list_rules,
    load_rules,
)


class TestReadRulesDir:
    """Test _read_rules_dir with various filesystem states."""

    def test_empty_dir(self, tmp_path):
        assert _read_rules_dir(tmp_path) == {}

    def test_reads_md_files(self, tmp_path):
        (tmp_path / "_global.md").write_text("Global rule")
        (tmp_path / "code-writer.md").write_text("Writer rule")
        result = _read_rules_dir(tmp_path)
        assert result == {"_global": "Global rule", "code-writer": "Writer rule"}

    def test_ignores_non_md_files(self, tmp_path):
        (tmp_path / "notes.txt").write_text("Not a rule")
        (tmp_path / "config.yaml").write_text("not: a rule")
        (tmp_path / "_global.md").write_text("Real rule")
        result = _read_rules_dir(tmp_path)
        assert list(result.keys()) == ["_global"]

    def test_skips_empty_files(self, tmp_path):
        (tmp_path / "_global.md").write_text("")
        (tmp_path / "code-writer.md").write_text("   ")
        (tmp_path / "code-tester.md").write_text("Has content")
        result = _read_rules_dir(tmp_path)
        assert result == {"code-tester": "Has content"}

    def test_nonexistent_dir(self):
        result = _read_rules_dir(Path("/nonexistent/path"))
        assert result == {}


class TestLoadRules:
    """Test load_rules merging and targeting."""

    def test_no_rules_returns_empty(self, tmp_path):
        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", tmp_path / "norules"):
            result = load_rules("code-writer", str(tmp_path))
        assert result == ""

    def test_global_only(self, tmp_path):
        rules_dir = tmp_path / "global_rules"
        rules_dir.mkdir()
        (rules_dir / "_global.md").write_text("Always be concise")

        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", rules_dir):
            result = load_rules("code-writer")
        assert result == "Always be concise"

    def test_agent_specific_included(self, tmp_path):
        rules_dir = tmp_path / "global_rules"
        rules_dir.mkdir()
        (rules_dir / "code-writer.md").write_text("Use 4-space indent")

        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", rules_dir):
            result = load_rules("code-writer")
        assert "Use 4-space indent" in result

    def test_agent_specific_excluded_for_other_agent(self, tmp_path):
        rules_dir = tmp_path / "global_rules"
        rules_dir.mkdir()
        (rules_dir / "code-writer.md").write_text("Writer only rule")

        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", rules_dir):
            result = load_rules("code-tester")
        assert result == ""

    def test_project_rules_appended(self, tmp_path):
        global_dir = tmp_path / "global_rules"
        global_dir.mkdir()
        (global_dir / "_global.md").write_text("Global rule")

        repo = tmp_path / "repo"
        project_dir = repo / ".code-agents" / "rules"
        project_dir.mkdir(parents=True)
        (project_dir / "_global.md").write_text("Project rule")

        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", global_dir):
            result = load_rules("code-writer", str(repo))
        assert "Global rule" in result
        assert "Project rule" in result
        # Global comes first
        assert result.index("Global rule") < result.index("Project rule")

    def test_merge_all_four_sources(self, tmp_path):
        global_dir = tmp_path / "global_rules"
        global_dir.mkdir()
        (global_dir / "_global.md").write_text("G-global")
        (global_dir / "code-writer.md").write_text("G-writer")

        repo = tmp_path / "repo"
        project_dir = repo / ".code-agents" / "rules"
        project_dir.mkdir(parents=True)
        (project_dir / "_global.md").write_text("P-global")
        (project_dir / "code-writer.md").write_text("P-writer")

        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", global_dir):
            result = load_rules("code-writer", str(repo))

        # All 4 present in correct order
        parts = result.split("\n\n")
        assert parts == ["G-global", "G-writer", "P-global", "P-writer"]

    def test_no_repo_path_skips_project(self, tmp_path):
        global_dir = tmp_path / "global_rules"
        global_dir.mkdir()
        (global_dir / "_global.md").write_text("Global only")

        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", global_dir):
            result = load_rules("code-writer", None)
        assert result == "Global only"

    def test_fresh_read_every_call(self, tmp_path):
        """Proves no caching — file changes are picked up immediately."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        rule_file = rules_dir / "_global.md"
        rule_file.write_text("Version 1")

        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", rules_dir):
            result1 = load_rules("code-writer")
            rule_file.write_text("Version 2")
            result2 = load_rules("code-writer")

        assert result1 == "Version 1"
        assert result2 == "Version 2"


class TestListRules:
    """Test list_rules for CLI/chat display."""

    def test_empty_when_no_rules(self, tmp_path):
        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", tmp_path / "norules"):
            result = list_rules(repo_path=str(tmp_path))
        assert result == []

    def test_lists_all_rules(self, tmp_path):
        rules_dir = tmp_path / "global_rules"
        rules_dir.mkdir()
        (rules_dir / "_global.md").write_text("Global")
        (rules_dir / "code-writer.md").write_text("Writer")

        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", rules_dir):
            result = list_rules()
        assert len(result) == 2
        assert result[0]["scope"] == "global"
        assert result[0]["target"] == "_global"
        assert result[1]["target"] == "code-writer"

    def test_filters_by_agent(self, tmp_path):
        rules_dir = tmp_path / "global_rules"
        rules_dir.mkdir()
        (rules_dir / "_global.md").write_text("For all")
        (rules_dir / "code-writer.md").write_text("For writer")
        (rules_dir / "code-tester.md").write_text("For tester")

        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", rules_dir):
            writer_rules = list_rules(agent_name="code-writer")
            tester_rules = list_rules(agent_name="code-tester")

        # _global + code-writer
        assert len(writer_rules) == 2
        targets = {r["target"] for r in writer_rules}
        assert targets == {"_global", "code-writer"}

        # _global + code-tester
        assert len(tester_rules) == 2
        targets = {r["target"] for r in tester_rules}
        assert targets == {"_global", "code-tester"}

    def test_preview_truncation(self, tmp_path):
        rules_dir = tmp_path / "global_rules"
        rules_dir.mkdir()
        (rules_dir / "_global.md").write_text("A" * 200)

        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", rules_dir):
            result = list_rules()
        assert result[0]["preview"].endswith("...")
        assert len(result[0]["preview"]) == 83  # 80 + "..."

    def test_shows_both_scopes(self, tmp_path):
        global_dir = tmp_path / "global_rules"
        global_dir.mkdir()
        (global_dir / "_global.md").write_text("Global")

        repo = tmp_path / "repo"
        project_dir = repo / ".code-agents" / "rules"
        project_dir.mkdir(parents=True)
        (project_dir / "_global.md").write_text("Project")

        with patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", global_dir):
            result = list_rules(repo_path=str(repo))
        scopes = [r["scope"] for r in result]
        assert "global" in scopes
        assert "project" in scopes
