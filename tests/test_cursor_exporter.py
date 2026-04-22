"""Tests for cursor_exporter.py — Cursor IDE export."""

from __future__ import annotations

import json
import os

import pytest

from code_agents.tools.cursor_exporter import (
    export_cursor,
    _read_routing_description,
    _parse_skill_meta,
    _api_endpoints_section,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def agents_tree(tmp_path):
    """Minimal agents/ directory for testing."""
    agents = tmp_path / "agents"
    agents.mkdir()

    # _shared
    shared = agents / "_shared" / "skills"
    shared.mkdir(parents=True)
    (shared / "debug.md").write_text(
        "---\nname: debug\ndescription: Debug issues\n---\n\nDebug steps.\n"
    )

    # jenkins_cicd
    jc = agents / "jenkins_cicd"
    jc.mkdir()
    (jc / "jenkins_cicd.yaml").write_text(
        'name: jenkins-cicd\n'
        'display_name: "Jenkins CI/CD Agent"\n'
        'system_prompt: |\n'
        '  You are Jenkins.\n'
        'routing:\n'
        '  description: "Build, deploy, ArgoCD verify"\n'
    )
    skills = jc / "skills"
    skills.mkdir()
    (skills / "build.md").write_text(
        "---\nname: build\ndescription: Trigger Jenkins build\n---\n\nWorkflow.\n"
    )

    # code_reasoning
    cr = agents / "code_reasoning"
    cr.mkdir()
    (cr / "code_reasoning.yaml").write_text(
        'name: code-reasoning\n'
        'routing:\n'
        '  description: "Read-only code analysis"\n'
    )
    cr_skills = cr / "skills"
    cr_skills.mkdir()
    (cr_skills / "explain.md").write_text(
        "---\nname: explain\ndescription: Explain code\n---\n\nExplain.\n"
    )

    return agents


# ---------------------------------------------------------------------------
# Tests — export_cursor
# ---------------------------------------------------------------------------


class TestExportCursor:
    def test_creates_cursorrules(self, agents_tree, tmp_path):
        repo = tmp_path / "my_repo"
        stats = export_cursor(str(repo), str(agents_tree))

        cr_path = repo / ".cursorrules"
        assert cr_path.exists()
        content = cr_path.read_text()
        assert "# Code Agents" in content

    def test_cursorrules_has_agents_table(self, agents_tree, tmp_path):
        repo = tmp_path / "my_repo"
        export_cursor(str(repo), str(agents_tree))

        content = (repo / ".cursorrules").read_text()
        assert "| jenkins-cicd |" in content
        assert "| code-reasoning |" in content

    def test_cursorrules_has_skills_section(self, agents_tree, tmp_path):
        repo = tmp_path / "my_repo"
        export_cursor(str(repo), str(agents_tree))

        content = (repo / ".cursorrules").read_text()
        assert "### jenkins-cicd" in content
        assert "- build" in content
        assert "- explain" in content

    def test_cursorrules_has_shared_skills(self, agents_tree, tmp_path):
        repo = tmp_path / "my_repo"
        export_cursor(str(repo), str(agents_tree))

        content = (repo / ".cursorrules").read_text()
        assert "_shared" in content
        assert "debug" in content

    def test_cursorrules_has_api_endpoints(self, agents_tree, tmp_path):
        repo = tmp_path / "my_repo"
        export_cursor(str(repo), str(agents_tree))

        content = (repo / ".cursorrules").read_text()
        assert "### Jenkins" in content
        assert "/jenkins/build-and-wait" in content
        assert "### ArgoCD" in content
        assert "### Git" in content

    def test_cursorrules_under_token_limit(self, agents_tree, tmp_path):
        repo = tmp_path / "my_repo"
        export_cursor(str(repo), str(agents_tree))

        content = (repo / ".cursorrules").read_text()
        # Rough token estimate: ~4 chars per token
        tokens = len(content) // 4
        assert tokens < 5000, f".cursorrules is {tokens} tokens, exceeds 5000 limit"

    def test_creates_cursor_mcp_json(self, agents_tree, tmp_path):
        repo = tmp_path / "my_repo"
        export_cursor(str(repo), str(agents_tree))

        mcp_path = repo / ".cursor" / "mcp.json"
        assert mcp_path.exists()
        mcp = json.loads(mcp_path.read_text())
        assert mcp["mcpServers"]["code-agents"]["command"] == "code-agents"
        assert mcp["mcpServers"]["code-agents"]["args"] == ["serve", "--mcp"]

    def test_returns_correct_stats(self, agents_tree, tmp_path):
        repo = tmp_path / "my_repo"
        stats = export_cursor(str(repo), str(agents_tree))

        assert stats["agents"] == 2
        assert stats["skills"] == 3  # build + explain + shared debug
        assert stats["repo_path"] == str(repo)

    def test_missing_agents_dir(self, tmp_path):
        repo = tmp_path / "my_repo"
        stats = export_cursor(str(repo), str(tmp_path / "nonexistent"))
        assert stats["agents"] == 0
        assert "error" in stats

    def test_cursorrules_has_usage_section(self, agents_tree, tmp_path):
        repo = tmp_path / "my_repo"
        export_cursor(str(repo), str(agents_tree))

        content = (repo / ".cursorrules").read_text()
        assert "## Usage" in content
        assert "code-agents start" in content


# ---------------------------------------------------------------------------
# Tests — helper functions
# ---------------------------------------------------------------------------


class TestReadRoutingDescription:
    def test_reads_description(self, agents_tree):
        yaml_path = agents_tree / "jenkins_cicd" / "jenkins_cicd.yaml"
        desc = _read_routing_description(yaml_path)
        assert desc == "Build, deploy, ArgoCD verify"

    def test_handles_missing_file(self, tmp_path):
        result = _read_routing_description(tmp_path / "nope.yaml")
        assert result == ""


class TestParseSkillMeta:
    def test_parses_frontmatter(self, agents_tree):
        path = agents_tree / "jenkins_cicd" / "skills" / "build.md"
        meta = _parse_skill_meta(path)
        assert meta["name"] == "build"
        assert meta["description"] == "Trigger Jenkins build"

    def test_no_frontmatter_uses_stem(self, tmp_path):
        md = tmp_path / "my-skill.md"
        md.write_text("Just some workflow content.\n")
        meta = _parse_skill_meta(md)
        assert meta["name"] == "my-skill"
        assert meta["description"] == ""


class TestApiEndpointsSection:
    def test_contains_key_endpoints(self):
        section = _api_endpoints_section()
        assert "/jenkins/build-and-wait" in section
        assert "/argocd/apps/" in section
        assert "/git/status" in section
        assert "/jira/issue/" in section


# ---------------------------------------------------------------------------
# Tests — real agents directory (skip if not present)
# ---------------------------------------------------------------------------


_REAL_AGENTS = os.path.join(os.path.dirname(__file__), "..", "agents")


@pytest.mark.skipif(
    not os.path.isdir(_REAL_AGENTS),
    reason="Real agents/ directory not found",
)
class TestRealAgentsCursorExport:
    def test_exports_real_agents(self, tmp_path):
        repo = tmp_path / "real_cursor"
        stats = export_cursor(str(repo), _REAL_AGENTS)
        assert stats["agents"] >= 13
        assert stats["skills"] >= 100

        # Verify token budget with real data
        content = (repo / ".cursorrules").read_text()
        tokens = len(content) // 4
        assert tokens < 8000, f"Real .cursorrules is {tokens} tokens, exceeds 8000 limit"
