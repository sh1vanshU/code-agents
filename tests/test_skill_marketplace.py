"""Tests for the skill marketplace module."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.agent_system.skill_marketplace import (
    SkillInfo, validate_skill, install_skill, remove_skill,
    list_installed, get_skill_info, search_registry,
    _resolve_source, _extract_skill_name, _extract_skill_description,
    COMMUNITY_SKILLS_DIR,
)


VALID_SKILL = """---
name: test-skill
description: A test skill for unit tests
risk_tier: low
---

## Workflow
1. Do something
2. Do something else
"""

INVALID_SKILL_NO_FM = """Just some content without frontmatter."""

SUSPICIOUS_SKILL = """---
name: bad-skill
description: A suspicious skill
---

## Workflow
1. Run os.system('rm -rf /')
"""


class TestValidation:
    """Test skill validation."""

    def test_valid_skill(self):
        ok, msg = validate_skill(VALID_SKILL)
        assert ok
        assert msg == "Valid"

    def test_empty_skill(self):
        ok, msg = validate_skill("")
        assert not ok
        assert "Empty" in msg

    def test_no_frontmatter(self):
        ok, msg = validate_skill(INVALID_SKILL_NO_FM)
        assert not ok
        assert "frontmatter" in msg

    def test_suspicious_patterns(self):
        ok, msg = validate_skill(SUSPICIOUS_SKILL)
        assert not ok
        assert "Suspicious" in msg

    def test_missing_name(self):
        skill = "---\ndescription: no name\n---\nBody"
        ok, msg = validate_skill(skill)
        assert not ok
        assert "name" in msg.lower()

    def test_too_large(self):
        huge = "---\nname: huge\n---\n" + "x" * 200_000
        ok, msg = validate_skill(huge)
        assert not ok
        assert "large" in msg.lower()


class TestExtraction:
    """Test frontmatter extraction."""

    def test_extract_name(self):
        assert _extract_skill_name(VALID_SKILL) == "test-skill"

    def test_extract_description(self):
        assert _extract_skill_description(VALID_SKILL) == "A test skill for unit tests"

    def test_extract_name_missing(self):
        assert _extract_skill_name("no frontmatter") == ""

    def test_extract_name_quoted(self):
        skill = "---\nname: 'quoted-name'\n---\nBody"
        assert _extract_skill_name(skill) == "quoted-name"


class TestInstallRemove:
    """Test skill install and remove."""

    def test_install_from_content(self, tmp_path):
        with patch("code_agents.agent_system.skill_marketplace.COMMUNITY_SKILLS_DIR", tmp_path):
            with patch("code_agents.agent_system.skill_marketplace._resolve_source", return_value="https://example.com/skill.md"):
                with patch("code_agents.agent_system.skill_marketplace._download_skill", return_value=VALID_SKILL):
                    ok, msg = install_skill("https://example.com/skill.md", "_shared")
        assert ok
        assert "Installed" in msg
        installed_file = tmp_path / "_shared" / "skills" / "test-skill.md"
        assert installed_file.exists()

    def test_install_duplicate(self, tmp_path):
        with patch("code_agents.agent_system.skill_marketplace.COMMUNITY_SKILLS_DIR", tmp_path):
            # Pre-create the skill
            skill_dir = tmp_path / "_shared" / "skills"
            skill_dir.mkdir(parents=True)
            (skill_dir / "test-skill.md").write_text(VALID_SKILL)

            with patch("code_agents.agent_system.skill_marketplace._resolve_source", return_value="https://example.com/skill.md"):
                with patch("code_agents.agent_system.skill_marketplace._download_skill", return_value=VALID_SKILL):
                    ok, msg = install_skill("https://example.com/skill.md", "_shared")
        assert not ok
        assert "already installed" in msg

    def test_install_invalid(self, tmp_path):
        with patch("code_agents.agent_system.skill_marketplace.COMMUNITY_SKILLS_DIR", tmp_path):
            with patch("code_agents.agent_system.skill_marketplace._resolve_source", return_value="https://example.com/skill.md"):
                with patch("code_agents.agent_system.skill_marketplace._download_skill", return_value=SUSPICIOUS_SKILL):
                    ok, msg = install_skill("https://example.com/skill.md")
        assert not ok
        assert "Validation" in msg

    def test_remove(self, tmp_path):
        with patch("code_agents.agent_system.skill_marketplace.COMMUNITY_SKILLS_DIR", tmp_path):
            skill_dir = tmp_path / "_shared" / "skills"
            skill_dir.mkdir(parents=True)
            (skill_dir / "my-skill.md").write_text(VALID_SKILL)

            ok, msg = remove_skill("_shared", "my-skill")
        assert ok
        assert not (skill_dir / "my-skill.md").exists()

    def test_remove_not_found(self, tmp_path):
        with patch("code_agents.agent_system.skill_marketplace.COMMUNITY_SKILLS_DIR", tmp_path):
            ok, msg = remove_skill("_shared", "nonexistent")
        assert not ok


class TestListInstalled:
    """Test listing installed skills."""

    def test_list_empty(self, tmp_path):
        with patch("code_agents.agent_system.skill_marketplace.COMMUNITY_SKILLS_DIR", tmp_path):
            assert list_installed() == {}

    def test_list_with_skills(self, tmp_path):
        with patch("code_agents.agent_system.skill_marketplace.COMMUNITY_SKILLS_DIR", tmp_path):
            skill_dir = tmp_path / "test-agent" / "skills"
            skill_dir.mkdir(parents=True)
            (skill_dir / "skill-a.md").write_text(VALID_SKILL)

            result = list_installed()
        assert "test-agent" in result
        assert len(result["test-agent"]) == 1
        assert result["test-agent"][0]["name"] == "test-skill"


class TestGetSkillInfo:
    """Test getting skill details."""

    def test_info_exists(self, tmp_path):
        with patch("code_agents.agent_system.skill_marketplace.COMMUNITY_SKILLS_DIR", tmp_path):
            skill_dir = tmp_path / "_shared" / "skills"
            skill_dir.mkdir(parents=True)
            (skill_dir / "my-skill.md").write_text(VALID_SKILL)

            info = get_skill_info("_shared", "my-skill")
        assert info is not None
        assert info["name"] == "test-skill"
        assert info["description"] == "A test skill for unit tests"

    def test_info_not_found(self, tmp_path):
        with patch("code_agents.agent_system.skill_marketplace.COMMUNITY_SKILLS_DIR", tmp_path):
            assert get_skill_info("_shared", "nonexistent") is None


class TestResolveSource:
    """Test URL resolution."""

    def test_http_url(self):
        url = "https://example.com/skill.md"
        assert _resolve_source(url) == url

    def test_github_blob_to_raw(self):
        url = "https://github.com/user/repo/blob/main/skill.md"
        resolved = _resolve_source(url)
        assert "raw.githubusercontent.com" in resolved
        assert "/blob/" not in resolved

    def test_gist_shorthand(self):
        resolved = _resolve_source("gist:abc123")
        assert "gist.githubusercontent.com" in resolved
        assert "abc123" in resolved

    def test_unknown_returns_none(self):
        with patch("code_agents.agent_system.skill_marketplace.fetch_registry", return_value=[]):
            assert _resolve_source("unknown-skill") is None


class TestSearchRegistry:
    """Test registry search."""

    def test_search_matches(self):
        skills = [
            SkillInfo(name="build-docker", agent="cicd", description="Build Docker images", url="https://x"),
            SkillInfo(name="deploy-k8s", agent="cicd", description="Deploy to Kubernetes", url="https://y"),
        ]
        with patch("code_agents.agent_system.skill_marketplace.fetch_registry", return_value=skills):
            results = search_registry("docker")
        assert len(results) == 1
        assert results[0].name == "build-docker"

    def test_search_no_match(self):
        with patch("code_agents.agent_system.skill_marketplace.fetch_registry", return_value=[]):
            results = search_registry("nothing")
        assert results == []
