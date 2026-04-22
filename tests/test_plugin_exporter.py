"""Tests for plugin_exporter.py — Claude Code CLI plugin export."""

from __future__ import annotations

import json
import os

import pytest

from code_agents.tools.plugin_exporter import (
    export_claude_code_plugin,
    _read_agent_yaml,
    _read_identity_from_agents_md,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def agents_tree(tmp_path):
    """Create a minimal agents/ directory structure for testing."""
    agents = tmp_path / "agents"
    agents.mkdir()

    # _shared
    shared = agents / "_shared" / "skills"
    shared.mkdir(parents=True)
    (shared / "debug.md").write_text(
        "---\nname: debug\ndescription: Debug issues\n---\n\n## Steps\n1. Check logs\n"
    )

    # jenkins_cicd agent
    jc = agents / "jenkins_cicd"
    jc.mkdir()
    (jc / "jenkins_cicd.yaml").write_text(
        'name: jenkins-cicd\n'
        'display_name: "Jenkins CI/CD Agent"\n'
        'system_prompt: |\n'
        '  You are the Jenkins CI/CD Agent.\n'
        '  Build and deploy code.\n'
        'routing:\n'
        '  keywords: ["build", "deploy"]\n'
        '  description: "Jenkins CI/CD: build, deploy"\n'
    )
    (jc / "agents.md").write_text(
        "# Jenkins CI/CD Agent\n\n## Identity\nJenkins specialist that builds and deploys code.\n\n## Endpoints\n..."
    )
    skills = jc / "skills"
    skills.mkdir()
    (skills / "build.md").write_text(
        "---\nname: build\ndescription: Trigger Jenkins build\n---\n\n## Workflow\n1. Trigger build\n"
    )
    (skills / "deploy.md").write_text(
        "---\nname: deploy\ndescription: Deploy via Jenkins\n---\n\n## Workflow\n1. Deploy\n"
    )

    # code_reasoning agent (no agents.md)
    cr = agents / "code_reasoning"
    cr.mkdir()
    (cr / "code_reasoning.yaml").write_text(
        'name: code-reasoning\n'
        'display_name: "Code Reasoning Agent"\n'
        'system_prompt: |\n'
        '  Analyze codebases.\n'
        'routing:\n'
        '  description: "Read-only code analysis"\n'
    )
    cr_skills = cr / "skills"
    cr_skills.mkdir()
    (cr_skills / "explain.md").write_text(
        "---\nname: explain\ndescription: Explain code\n---\n\nExplain architecture.\n"
    )

    return agents


# ---------------------------------------------------------------------------
# Tests — export_claude_code_plugin
# ---------------------------------------------------------------------------


class TestExportClaudeCodePlugin:
    """Full integration tests for Claude Code plugin export."""

    def test_creates_plugin_manifest(self, agents_tree, tmp_path):
        out = tmp_path / "plugin_out"
        stats = export_claude_code_plugin(str(out), str(agents_tree))

        manifest_path = out / ".claude-plugin" / "plugin.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["name"] == "code-agents"
        assert "userConfig" in manifest
        assert manifest["userConfig"]["JENKINS_TOKEN"]["sensitive"] is True

    def test_creates_agent_markdown(self, agents_tree, tmp_path):
        out = tmp_path / "plugin_out"
        export_claude_code_plugin(str(out), str(agents_tree))

        agent_file = out / "agents" / "jenkins-cicd.md"
        assert agent_file.exists()
        content = agent_file.read_text()
        assert "name: jenkins-cicd" in content
        assert "Jenkins CI/CD Agent" in content or "Jenkins specialist" in content
        # System prompt included
        assert "You are the Jenkins CI/CD Agent" in content
        # agents.md content included
        assert "## Identity" in content

    def test_creates_skill_files(self, agents_tree, tmp_path):
        out = tmp_path / "plugin_out"
        export_claude_code_plugin(str(out), str(agents_tree))

        skill_file = out / "skills" / "jenkins-cicd" / "build" / "SKILL.md"
        assert skill_file.exists()
        content = skill_file.read_text()
        assert "Trigger Jenkins build" in content

    def test_exports_shared_skills(self, agents_tree, tmp_path):
        out = tmp_path / "plugin_out"
        export_claude_code_plugin(str(out), str(agents_tree))

        shared_skill = out / "skills" / "_shared" / "debug" / "SKILL.md"
        assert shared_skill.exists()
        assert "Debug issues" in shared_skill.read_text()

    def test_creates_mcp_json(self, agents_tree, tmp_path):
        out = tmp_path / "plugin_out"
        export_claude_code_plugin(str(out), str(agents_tree))

        mcp = json.loads((out / ".mcp.json").read_text())
        assert "mcpServers" in mcp
        assert mcp["mcpServers"]["code-agents"]["command"] == "code-agents"

    def test_creates_settings_json(self, agents_tree, tmp_path):
        out = tmp_path / "plugin_out"
        export_claude_code_plugin(str(out), str(agents_tree))

        settings = json.loads((out / "settings.json").read_text())
        assert settings["default_agent"] == "auto-pilot"

    def test_returns_correct_stats(self, agents_tree, tmp_path):
        out = tmp_path / "plugin_out"
        stats = export_claude_code_plugin(str(out), str(agents_tree))

        assert stats["agents"] == 2  # jenkins_cicd + code_reasoning
        assert stats["skills"] == 4  # build, deploy, explain + shared debug
        assert stats["output_dir"] == str(out)

    def test_missing_agents_dir(self, tmp_path):
        out = tmp_path / "plugin_out"
        stats = export_claude_code_plugin(str(out), str(tmp_path / "nonexistent"))
        assert stats["agents"] == 0
        assert "error" in stats

    def test_skips_hidden_and_shared_dirs_for_agents(self, agents_tree, tmp_path):
        """_shared should not appear in agents/ output, only in skills/."""
        out = tmp_path / "plugin_out"
        export_claude_code_plugin(str(out), str(agents_tree))

        agents_dir = out / "agents"
        agent_files = [f.stem for f in agents_dir.iterdir()]
        assert "_shared" not in agent_files

    def test_agent_without_agents_md(self, agents_tree, tmp_path):
        """Agent with no agents.md should still export using routing description."""
        out = tmp_path / "plugin_out"
        export_claude_code_plugin(str(out), str(agents_tree))

        cr_file = out / "agents" / "code-reasoning.md"
        assert cr_file.exists()
        content = cr_file.read_text()
        assert "code-reasoning" in content
        assert "Analyze codebases" in content


# ---------------------------------------------------------------------------
# Tests — helper functions
# ---------------------------------------------------------------------------


class TestReadAgentYaml:
    def test_extracts_system_prompt(self, agents_tree):
        yaml_path = agents_tree / "jenkins_cicd" / "jenkins_cicd.yaml"
        meta = _read_agent_yaml(yaml_path)
        assert meta is not None
        assert "You are the Jenkins CI/CD Agent" in meta["system_prompt"]

    def test_extracts_routing_description(self, agents_tree):
        yaml_path = agents_tree / "jenkins_cicd" / "jenkins_cicd.yaml"
        meta = _read_agent_yaml(yaml_path)
        assert meta["routing_description"] == "Jenkins CI/CD: build, deploy"

    def test_handles_missing_file(self, tmp_path):
        result = _read_agent_yaml(tmp_path / "nonexistent.yaml")
        assert result is None


class TestReadIdentityFromAgentsMd:
    def test_extracts_identity_section(self, agents_tree):
        path = agents_tree / "jenkins_cicd" / "agents.md"
        identity = _read_identity_from_agents_md(path)
        assert "Jenkins specialist" in identity

    def test_returns_empty_for_missing_file(self, tmp_path):
        result = _read_identity_from_agents_md(tmp_path / "missing.md")
        assert result == ""


# ---------------------------------------------------------------------------
# Tests — real agents directory (skip if not present)
# ---------------------------------------------------------------------------


_REAL_AGENTS = os.path.join(os.path.dirname(__file__), "..", "agents")


@pytest.mark.skipif(
    not os.path.isdir(_REAL_AGENTS),
    reason="Real agents/ directory not found",
)
class TestRealAgentsExport:
    def test_exports_all_real_agents(self, tmp_path):
        out = tmp_path / "real_plugin"
        stats = export_claude_code_plugin(str(out), _REAL_AGENTS)
        assert stats["agents"] >= 13
        assert stats["skills"] >= 100
