"""Tests for the security agent configuration and skills."""

from pathlib import Path

import pytest
import yaml


AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents" / "security"


class TestSecurityAgentConfig:
    """Verify the security agent YAML config is well-formed."""

    def test_yaml_exists(self):
        assert (AGENTS_DIR / "security.yaml").exists()

    def test_yaml_loads(self):
        cfg = yaml.safe_load((AGENTS_DIR / "security.yaml").read_text())
        assert cfg["name"] == "security"
        assert cfg["display_name"] == "Security Agent"

    def test_permission_mode_is_default(self):
        cfg = yaml.safe_load((AGENTS_DIR / "security.yaml").read_text())
        assert cfg["permission_mode"] == "default"

    def test_mode_is_ask(self):
        cfg = yaml.safe_load((AGENTS_DIR / "security.yaml").read_text())
        assert cfg["extra_args"]["mode"] == "ask"

    def test_system_prompt_mentions_review_only(self):
        cfg = yaml.safe_load((AGENTS_DIR / "security.yaml").read_text())
        assert "REVIEW-ONLY" in cfg["system_prompt"]

    def test_system_prompt_mentions_owasp(self):
        cfg = yaml.safe_load((AGENTS_DIR / "security.yaml").read_text())
        assert "OWASP" in cfg["system_prompt"]

    def test_system_prompt_mentions_delegation(self):
        cfg = yaml.safe_load((AGENTS_DIR / "security.yaml").read_text())
        assert "code-writer" in cfg["system_prompt"]
        assert "code-reviewer" in cfg["system_prompt"]


class TestSecurityAutorun:
    """Verify autorun.yaml is well-formed."""

    def test_autorun_exists(self):
        assert (AGENTS_DIR / "autorun.yaml").exists()

    def test_autorun_loads(self):
        cfg = yaml.safe_load((AGENTS_DIR / "autorun.yaml").read_text())
        assert "allow" in cfg
        assert "block" in cfg

    def test_allows_read_commands(self):
        cfg = yaml.safe_load((AGENTS_DIR / "autorun.yaml").read_text())
        allow = cfg["allow"]
        assert "cat " in allow
        assert "grep " in allow
        assert "git log" in allow

    def test_allows_audit_commands(self):
        cfg = yaml.safe_load((AGENTS_DIR / "autorun.yaml").read_text())
        allow = cfg["allow"]
        assert "pip audit" in allow
        assert "npm audit" in allow

    def test_blocks_destructive_commands(self):
        cfg = yaml.safe_load((AGENTS_DIR / "autorun.yaml").read_text())
        block = cfg["block"]
        assert "rm " in block
        assert "git push" in block

    def test_blocks_network_commands(self):
        cfg = yaml.safe_load((AGENTS_DIR / "autorun.yaml").read_text())
        block = cfg["block"]
        assert "curl " in block
        assert "wget " in block


class TestSecuritySkills:
    """Verify all skill files exist and have valid frontmatter."""

    EXPECTED_SKILLS = [
        "vulnerability-scan",
        "dependency-audit",
        "secrets-detection",
        "attack-surface",
        "compliance-review",
        "security-report",
    ]

    def test_skills_dir_exists(self):
        assert (AGENTS_DIR / "skills").is_dir()

    @pytest.mark.parametrize("skill", EXPECTED_SKILLS)
    def test_skill_file_exists(self, skill):
        assert (AGENTS_DIR / "skills" / f"{skill}.md").exists()

    @pytest.mark.parametrize("skill", EXPECTED_SKILLS)
    def test_skill_has_frontmatter(self, skill):
        content = (AGENTS_DIR / "skills" / f"{skill}.md").read_text()
        assert content.startswith("---")
        # Extract frontmatter
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"Skill {skill} missing YAML frontmatter"
        fm = yaml.safe_load(parts[1])
        assert "name" in fm
        assert "description" in fm

    @pytest.mark.parametrize("skill", EXPECTED_SKILLS)
    def test_skill_name_matches_filename(self, skill):
        content = (AGENTS_DIR / "skills" / f"{skill}.md").read_text()
        parts = content.split("---", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["name"] == skill

    def test_security_report_references_other_skills(self):
        content = (AGENTS_DIR / "skills" / "security-report.md").read_text()
        assert "[SKILL:vulnerability-scan]" in content
        assert "[SKILL:dependency-audit]" in content
        assert "[SKILL:secrets-detection]" in content


class TestSecurityAgentIntegration:
    """Verify the security agent is properly registered across the codebase."""

    def test_agent_roles_includes_security(self):
        from code_agents.chat.chat_welcome import AGENT_ROLES
        assert "security" in AGENT_ROLES

    def test_agent_welcome_includes_security(self):
        from code_agents.chat.chat_welcome import AGENT_WELCOME
        assert "security" in AGENT_WELCOME
        title, caps, examples = AGENT_WELCOME["security"]
        assert "Surakshak" in title
        assert len(caps) >= 4
        assert len(examples) >= 3

    def test_agent_router_lists_security(self):
        # agent_router merged into auto_pilot
        router_yaml = Path(__file__).resolve().parent.parent / "agents" / "auto_pilot" / "auto_pilot.yaml"
        content = router_yaml.read_text()
        assert "security" in content

    def test_agents_md_documents_security(self):
        agents_md = Path(__file__).resolve().parent.parent / "AGENTS.md"
        content = agents_md.read_text()
        assert "## Security" in content
        assert "vulnerability-scan" in content

    def test_cli_curls_has_security_examples(self):
        curls_path = Path(__file__).resolve().parent.parent / "code_agents" / "cli" / "cli_curls.py"
        content = curls_path.read_text()
        assert '"security"' in content
        assert "Security audit" in content
