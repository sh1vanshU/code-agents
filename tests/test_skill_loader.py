"""Tests for skill_loader.py — agent skill discovery and loading."""

import os
import tempfile
from pathlib import Path

import pytest

from code_agents.chat.chat_commands import _extract_skill_requests
from code_agents.agent_system.skill_loader import (
    Skill,
    _parse_skill_file,
    format_skills_for_prompt,
    get_skill,
    list_all_skills,
    load_agent_skills,
)


@pytest.fixture
def agents_dir(tmp_path):
    """Create a temp agents directory with skills."""
    # Agent: jenkins-cicd → folder jenkins_cicd
    agent_dir = tmp_path / "jenkins_cicd"
    agent_dir.mkdir()
    skills_dir = agent_dir / "skills"
    skills_dir.mkdir()

    # Skill with frontmatter
    (skills_dir / "build.md").write_text(
        "---\n"
        "name: build\n"
        "description: Trigger Jenkins build and extract version\n"
        "---\n\n"
        "## Workflow\n"
        "1. Fetch build parameters\n"
        "2. Trigger build-and-wait\n"
    )

    # Skill without frontmatter
    (skills_dir / "deploy.md").write_text(
        "## Deploy Workflow\n"
        "1. Use build_version as image_tag\n"
        "2. Trigger deploy job\n"
    )

    # Empty file (should be skipped)
    (skills_dir / "empty.md").write_text("")

    # Agent: code-writer → folder code_writer
    writer_dir = tmp_path / "code_writer"
    writer_dir.mkdir()
    writer_skills = writer_dir / "skills"
    writer_skills.mkdir()
    (writer_skills / "implement.md").write_text(
        "---\n"
        "name: implement\n"
        "description: Implement a feature from requirements\n"
        "---\n\n"
        "## Steps\n"
        "1. Analyze requirements\n"
        "2. Write code\n"
    )

    # Agent with no skills
    no_skills_dir = tmp_path / "code_reasoning"
    no_skills_dir.mkdir()

    # Hidden dir (should be skipped)
    hidden = tmp_path / ".hidden"
    hidden.mkdir()

    return tmp_path


# ---------------------------------------------------------------------------
# Skill dataclass
# ---------------------------------------------------------------------------

def test_skill_full_name():
    s = Skill(name="build", agent="jenkins-cicd", description="Build", body="steps")
    assert s.full_name == "jenkins-cicd:build"


# ---------------------------------------------------------------------------
# _parse_skill_file
# ---------------------------------------------------------------------------

def test_parse_with_frontmatter(agents_dir):
    path = agents_dir / "jenkins_cicd" / "skills" / "build.md"
    s = _parse_skill_file(path, "jenkins-cicd")
    assert s is not None
    assert s.name == "build"
    assert s.agent == "jenkins-cicd"
    assert s.description == "Trigger Jenkins build and extract version"
    assert "Fetch build parameters" in s.body


def test_parse_without_frontmatter(agents_dir):
    path = agents_dir / "jenkins_cicd" / "skills" / "deploy.md"
    s = _parse_skill_file(path, "jenkins-cicd")
    assert s is not None
    assert s.name == "deploy"  # from filename
    assert s.description == ""
    assert "Deploy Workflow" in s.body


def test_parse_empty_file(agents_dir):
    path = agents_dir / "jenkins_cicd" / "skills" / "empty.md"
    s = _parse_skill_file(path, "jenkins-cicd")
    assert s is None


def test_parse_nonexistent():
    s = _parse_skill_file(Path("/nonexistent/skill.md"), "test")
    assert s is None


# ---------------------------------------------------------------------------
# load_agent_skills
# ---------------------------------------------------------------------------

def test_load_agent_skills(agents_dir):
    result = load_agent_skills(agents_dir)
    assert "jenkins-cicd" in result
    assert "code-writer" in result
    assert "code-reasoning" not in result  # no skills dir
    assert len(result["jenkins-cicd"]) == 2  # build + deploy (empty skipped)
    assert len(result["code-writer"]) == 1


def test_load_skills_nonexistent_dir():
    result = load_agent_skills("/nonexistent/path")
    assert result == {}


def test_load_skips_hidden_dirs(agents_dir):
    result = load_agent_skills(agents_dir)
    assert ".hidden" not in str(result)


# ---------------------------------------------------------------------------
# get_skill
# ---------------------------------------------------------------------------

def test_get_skill_found(agents_dir):
    s = get_skill(agents_dir, "jenkins-cicd", "build")
    assert s is not None
    assert s.name == "build"
    assert s.agent == "jenkins-cicd"


def test_get_skill_not_found(agents_dir):
    s = get_skill(agents_dir, "jenkins-cicd", "nonexistent")
    assert s is None


def test_get_skill_no_skills_dir(agents_dir):
    s = get_skill(agents_dir, "code-reasoning", "anything")
    assert s is None


# ---------------------------------------------------------------------------
# list_all_skills
# ---------------------------------------------------------------------------

def test_list_all_skills(agents_dir):
    skills = list_all_skills(agents_dir)
    assert len(skills) == 3  # build + deploy + implement
    names = {s.full_name for s in skills}
    assert "jenkins-cicd:build" in names
    assert "jenkins-cicd:deploy" in names
    assert "code-writer:implement" in names


# ---------------------------------------------------------------------------
# format_skills_for_prompt
# ---------------------------------------------------------------------------

def test_format_skills_empty():
    assert format_skills_for_prompt([]) == ""


def test_format_skills():
    skills = [
        Skill(name="build", agent="jenkins-cicd", description="Trigger build", body=""),
        Skill(name="deploy", agent="jenkins-cicd", description="Deploy to env", body=""),
    ]
    text = format_skills_for_prompt(skills)
    assert "build" in text
    assert "Trigger build" in text
    assert "deploy" in text
    assert "Deploy to env" in text


# ---------------------------------------------------------------------------
# _extract_skill_requests (from chat_commands.py)
# ---------------------------------------------------------------------------

def test_extract_skill_single():
    text = "I need the build workflow.\n[SKILL:build]\nLet me proceed."
    assert _extract_skill_requests(text) == ["build"]


def test_extract_skill_multiple():
    text = "First [SKILL:git-precheck] then [SKILL:build]"
    assert _extract_skill_requests(text) == ["git-precheck", "build"]


def test_extract_skill_none():
    text = "Let me check the build parameters.\n```bash\ncurl ...\n```"
    assert _extract_skill_requests(text) == []


def test_extract_skill_with_hyphens():
    text = "[SKILL:log-analysis]"
    assert _extract_skill_requests(text) == ["log-analysis"]


def test_extract_skill_with_underscores():
    text = "[SKILL:full_regression]"
    assert _extract_skill_requests(text) == ["full_regression"]


def test_extract_skill_cross_agent():
    text = "[SKILL:jenkins-cicd:build]"
    assert _extract_skill_requests(text) == ["jenkins-cicd:build"]


# ---------------------------------------------------------------------------
# Cross-agent skill sharing
# ---------------------------------------------------------------------------

def test_get_skill_cross_agent(agents_dir):
    """Cross-agent syntax: get_skill(dir, 'auto-pilot', 'jenkins-cicd:build')."""
    s = get_skill(agents_dir, "auto-pilot", "jenkins-cicd:build")
    assert s is not None
    assert s.name == "build"
    assert s.agent == "jenkins-cicd"


def test_get_skill_cross_agent_not_found(agents_dir):
    s = get_skill(agents_dir, "auto-pilot", "jenkins-cicd:nonexistent")
    assert s is None


def test_get_skill_cross_agent_no_agent(agents_dir):
    s = get_skill(agents_dir, "auto-pilot", "fake-agent:build")
    assert s is None
