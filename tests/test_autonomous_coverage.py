"""Tests for autonomous test-coverage agent — skill files, autorun config, and YAML config."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
TC_DIR = AGENTS_DIR / "test_coverage"


# ---------------------------------------------------------------------------
# Skill file integrity
# ---------------------------------------------------------------------------


class TestSkillFiles:
    """Verify all test-coverage skills have valid frontmatter and content."""

    EXPECTED_SKILLS = {
        "auto-coverage",
        "autonomous-boost",
        "write-python-tests",
        "write-unit-tests",
        "write-integration-tests",
        "write-e2e-tests",
        "coverage-plan",
        "coverage-gate",
        "coverage-diff",
        "find-gaps",
        "run-coverage",
        "jacoco-report",
    }

    def test_skills_dir_exists(self):
        assert (TC_DIR / "skills").is_dir()

    def test_all_expected_skills_present(self):
        skill_files = {f.stem for f in (TC_DIR / "skills").glob("*.md")}
        for skill in self.EXPECTED_SKILLS:
            assert skill in skill_files, f"Missing skill: {skill}"

    @pytest.mark.parametrize("skill_file", list((TC_DIR / "skills").glob("*.md")))
    def test_skill_has_valid_frontmatter(self, skill_file):
        content = skill_file.read_text()
        assert content.startswith("---"), f"{skill_file.name} missing YAML frontmatter"
        # Split on --- to get frontmatter
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"{skill_file.name} incomplete frontmatter"
        meta = yaml.safe_load(parts[1])
        assert "name" in meta, f"{skill_file.name} missing 'name' in frontmatter"
        assert "description" in meta, f"{skill_file.name} missing 'description' in frontmatter"

    @pytest.mark.parametrize("skill_file", list((TC_DIR / "skills").glob("*.md")))
    def test_skill_has_workflow_content(self, skill_file):
        content = skill_file.read_text()
        # Should have actual workflow content after frontmatter
        parts = content.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else ""
        assert len(body) > 50, f"{skill_file.name} has too little content ({len(body)} chars)"


# ---------------------------------------------------------------------------
# Autonomous-boost skill specifics
# ---------------------------------------------------------------------------


class TestAutonomousBoostSkill:
    """Verify the autonomous-boost skill has all required phases."""

    @pytest.fixture
    def skill_content(self):
        return (TC_DIR / "skills" / "autonomous-boost.md").read_text()

    def test_has_phase_1_discovery(self, skill_content):
        assert "Phase 1" in skill_content
        assert "Discovery" in skill_content or "Baseline" in skill_content

    def test_has_phase_2_planning(self, skill_content):
        assert "Phase 2" in skill_content
        assert "Gap Analysis" in skill_content or "Planning" in skill_content

    def test_has_phase_3_writing_loop(self, skill_content):
        assert "Phase 3" in skill_content
        assert "Writing" in skill_content or "Test Writing" in skill_content

    def test_has_phase_4_commit(self, skill_content):
        assert "Phase 4" in skill_content
        assert "Commit" in skill_content or "Git" in skill_content

    def test_uses_remember_tags(self, skill_content):
        assert "[REMEMBER:" in skill_content

    def test_has_scratchpad_keys(self, skill_content):
        required_keys = [
            "baseline_coverage",
            "target_threshold",
            "current_batch",
            "phase",
        ]
        for key in required_keys:
            assert key in skill_content, f"Missing scratchpad key: {key}"

    def test_has_error_recovery(self, skill_content):
        assert "Error Recovery" in skill_content or "error" in skill_content.lower()

    def test_has_self_driving_rules(self, skill_content):
        assert "Self-Driving" in skill_content or "DO NOT stop" in skill_content

    def test_has_max_iterations_limit(self, skill_content):
        assert "5 batches" in skill_content or "MAX" in skill_content

    def test_delegates_to_write_skills(self, skill_content):
        assert "[SKILL:write-python-tests]" in skill_content
        assert "[SKILL:write-unit-tests]" in skill_content


# ---------------------------------------------------------------------------
# Write-python-tests skill specifics
# ---------------------------------------------------------------------------


class TestWritePythonTestsSkill:
    """Verify the write-python-tests skill covers pytest patterns."""

    @pytest.fixture
    def skill_content(self):
        return (TC_DIR / "skills" / "write-python-tests.md").read_text()

    def test_has_pytest_patterns(self, skill_content):
        assert "pytest" in skill_content
        assert "unittest.mock" in skill_content

    def test_has_fixture_examples(self, skill_content):
        assert "@pytest.fixture" in skill_content

    def test_has_parametrize(self, skill_content):
        assert "parametrize" in skill_content

    def test_has_async_support(self, skill_content):
        assert "asyncio" in skill_content or "async" in skill_content

    def test_has_mock_patterns(self, skill_content):
        assert "@patch" in skill_content or "patch(" in skill_content
        assert "MagicMock" in skill_content

    def test_has_coverage_verification_step(self, skill_content):
        assert "--cov" in skill_content or "coverage" in skill_content

    def test_has_poetry_run(self, skill_content):
        assert "poetry run pytest" in skill_content


# ---------------------------------------------------------------------------
# Auto-coverage skill entry point
# ---------------------------------------------------------------------------


class TestAutoCoverageSkill:
    """Verify auto-coverage delegates to autonomous-boost."""

    @pytest.fixture
    def skill_content(self):
        return (TC_DIR / "skills" / "auto-coverage.md").read_text()

    def test_delegates_to_autonomous_boost(self, skill_content):
        assert "[SKILL:autonomous-boost]" in skill_content

    def test_has_parameter_extraction(self, skill_content):
        assert "Scope" in skill_content
        assert "Threshold" in skill_content

    def test_has_progress_tracking(self, skill_content):
        assert "[REMEMBER:]" in skill_content or "scratchpad" in skill_content.lower()

    def test_has_language_routing(self, skill_content):
        assert "[SKILL:write-python-tests]" in skill_content
        assert "[SKILL:write-unit-tests]" in skill_content


# ---------------------------------------------------------------------------
# Agent YAML config
# ---------------------------------------------------------------------------


class TestAgentYamlConfig:
    """Verify test_coverage.yaml has autonomous mode."""

    @pytest.fixture
    def config(self):
        with open(TC_DIR / "test_coverage.yaml") as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def system_prompt(self, config):
        return config["system_prompt"]

    def test_name(self, config):
        assert config["name"] == "test-coverage"

    def test_has_autonomous_mode_section(self, system_prompt):
        assert "AUTONOMOUS MODE" in system_prompt

    def test_autonomous_triggers(self, system_prompt):
        assert "boost coverage" in system_prompt
        assert "improve coverage" in system_prompt
        assert "increase coverage" in system_prompt

    def test_autonomous_must_rules(self, system_prompt):
        # Must not stop to ask
        assert "DO NOT stop to ask" in system_prompt or "MUST NOT" in system_prompt
        # Must use REMEMBER tags
        assert "[REMEMBER:" in system_prompt or "REMEMBER" in system_prompt

    def test_has_file_write_safety_section(self, system_prompt):
        assert "FILE WRITE SAFETY" in system_prompt

    def test_restricts_writes_to_test_dirs(self, system_prompt):
        assert "tests/" in system_prompt
        assert "src/test/java/" in system_prompt
        assert "ONLY create or modify files in test directories" in system_prompt

    def test_blocks_source_writes(self, system_prompt):
        assert "NEVER write to source/production" in system_prompt
        assert "src/main/java/" in system_prompt

    def test_no_source_modification_rule(self, system_prompt):
        assert "ONLY write test files" in system_prompt or "Modify production/source code" in system_prompt

    def test_language_specific_skills(self, system_prompt):
        assert "[SKILL:write-python-tests]" in system_prompt
        assert "[SKILL:write-unit-tests]" in system_prompt

    def test_git_privileges(self, system_prompt):
        assert "git add" in system_prompt
        assert "git commit" in system_prompt
        assert "git push" in system_prompt  # mentioned as NOT allowed

    def test_stream_tool_activity(self, config):
        assert config["stream_tool_activity"] is True

    def test_include_session(self, config):
        assert config["include_session"] is True

    def test_permission_mode(self, config):
        assert config["permission_mode"] == "default"


# ---------------------------------------------------------------------------
# Autorun YAML config
# ---------------------------------------------------------------------------


class TestAutorunConfig:
    """Verify autorun.yaml allows coverage commands and blocks dangerous ones."""

    @pytest.fixture
    def autorun(self):
        with open(TC_DIR / "autorun.yaml") as f:
            return yaml.safe_load(f)

    def test_allows_poetry_pytest(self, autorun):
        allows = autorun["allow"]
        assert "poetry run pytest" in allows

    def test_allows_coverage_commands(self, autorun):
        allows = autorun["allow"]
        assert "poetry run coverage" in allows

    def test_allows_git_stage_commit(self, autorun):
        allows = autorun["allow"]
        assert any("git add" in a for a in allows)
        assert "git commit" in allows
        assert "git checkout -b" in allows

    def test_blocks_git_push(self, autorun):
        blocks = autorun["block"]
        assert "git push" in blocks

    def test_blocks_destructive(self, autorun):
        blocks = autorun["block"]
        assert "rm " in blocks
        assert "git reset --hard" in blocks

    def test_blocks_full_suite_coverage(self, autorun):
        """Ensure we block running --cov on the full project (80GB+ memory issue)."""
        blocks = autorun["block"]
        assert any("pytest --cov" in b for b in blocks)

    def test_allows_read_only_commands(self, autorun):
        allows = autorun["allow"]
        for cmd in ["ls ", "find ", "grep ", "pwd"]:
            assert cmd in allows, f"Missing allow: {cmd}"
        # cat is scoped to specific directories, not blanket "cat "
        cat_allows = [a for a in allows if a.startswith("cat ")]
        assert len(cat_allows) > 0, "No cat read commands allowed"

    def test_allows_testing_api(self, autorun):
        allows = autorun["allow"]
        assert "/testing/coverage" in allows
        assert "/testing/gaps" in allows
        assert "/testing/run" in allows

    def test_allows_writes_only_to_test_dirs(self, autorun):
        allows = autorun["allow"]
        write_allows = [a for a in allows if "cat >" in a or "cat >>" in a]
        for entry in write_allows:
            assert any(d in entry for d in ["tests/", "test/", "src/test/"]), \
                f"Write allow '{entry}' is not restricted to test dirs"

    def test_allows_java_test_paths(self, autorun):
        allows = autorun["allow"]
        assert "mkdir -p src/test/java" in allows
        assert "git add src/test/java/" in allows

    def test_blocks_writes_to_source_dirs(self, autorun):
        blocks = autorun["block"]
        assert "cat > code_agents/" in blocks
        assert "cat > src/main/" in blocks

    def test_blocks_git_add_source_dirs(self, autorun):
        blocks = autorun["block"]
        assert "git add code_agents/" in blocks
        assert "git add -A" in blocks
        assert "git add ." in blocks

    def test_cat_read_not_globally_allowed(self, autorun):
        """Ensure bare 'cat ' is NOT in allow list (would match cat > anything)."""
        allows = autorun["allow"]
        assert "cat " not in allows, "Bare 'cat ' would allow writing to any path via 'cat > file'"

    def test_allows_git_add_only_test_dirs(self, autorun):
        allows = autorun["allow"]
        git_add_allows = [a for a in allows if a.startswith("git add")]
        for entry in git_add_allows:
            assert any(d in entry for d in ["tests/", "test/", "src/test/", "conftest"]), \
                f"git add allow '{entry}' is not restricted to test dirs"


# ---------------------------------------------------------------------------
# Temp-script autorun resolution
# ---------------------------------------------------------------------------


class TestTempScriptAutorunResolution:
    """Verify _check_agent_autorun resolves temp-script content for matching."""

    def test_resolve_temp_script_reads_file(self):
        from code_agents.chat.chat_commands import _resolve_temp_script_content
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", prefix="code-agents-", delete=False
        ) as f:
            f.write("cat > tests/test_foo.py << 'EOF'\nimport pytest\nEOF\n")
            f.flush()
            cmd = f"bash {f.name} && rm -f {f.name}"
            content = _resolve_temp_script_content(cmd)
            assert "cat > tests/test_foo.py" in content
            os.unlink(f.name)

    def test_resolve_temp_script_returns_cmd_if_not_temp(self):
        from code_agents.chat.chat_commands import _resolve_temp_script_content
        assert _resolve_temp_script_content("ls -la") == "ls -la"

    def test_resolve_temp_script_returns_cmd_if_file_missing(self):
        from code_agents.chat.chat_commands import _resolve_temp_script_content
        cmd = "bash /tmp/code-agents-nonexistent.sh && rm -f /tmp/code-agents-nonexistent.sh"
        assert _resolve_temp_script_content(cmd) == cmd

    def test_check_autorun_matches_temp_script_content(self):
        from code_agents.chat.chat_commands import _check_agent_autorun
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", prefix="code-agents-", delete=False
        ) as f:
            f.write("cat > tests/test_foo.py << 'EOF'\nimport pytest\ndef test_x(): pass\nEOF\n")
            f.flush()
            cmd = f"bash {f.name} && rm -f {f.name}"
            # Patch to use test-coverage autorun config
            result = _check_agent_autorun(cmd, "test-coverage")
            assert result == "allow"
            os.unlink(f.name)

    def test_check_autorun_blocks_temp_script_writing_to_source(self):
        from code_agents.chat.chat_commands import _check_agent_autorun
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", prefix="code-agents-", delete=False
        ) as f:
            f.write("cat > code_agents/backend.py << 'EOF'\nprint('hacked')\nEOF\n")
            f.flush()
            cmd = f"bash {f.name} && rm -f {f.name}"
            result = _check_agent_autorun(cmd, "test-coverage")
            assert result == "block"
            os.unlink(f.name)
