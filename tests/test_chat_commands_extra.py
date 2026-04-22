"""Extra tests for chat_commands.py — covers interactive paths, command validation,
placeholder resolution, autorun config, save/trust, and _offer_run_commands branches."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.chat.chat_commands import (
    _extract_commands,
    _extract_delegations,
    _extract_skill_requests,
    _is_valid_command,
    _is_safe_command,
    _resolve_placeholders,
    _extract_context_from_output,
    _command_context,
    _save_command_to_rules,
    _is_command_trusted,
    _load_agent_autorun_config,
    _check_agent_autorun,
    _offer_run_commands,
    _log_auto_run,
    _run_single_command,
)


# ---------------------------------------------------------------------------
# _is_valid_command
# ---------------------------------------------------------------------------


class TestIsValidCommand:
    def test_empty(self):
        assert _is_valid_command("") is False
        assert _is_valid_command("   ") is False

    def test_english_starters(self):
        assert _is_valid_command("Please install this") is False
        assert _is_valid_command("You should run tests") is False
        assert _is_valid_command("Here is the plan for today") is False

    def test_long_english_sentence(self):
        assert _is_valid_command("This is a long sentence that describes what to do next") is False

    def test_shell_command(self):
        assert _is_valid_command("curl -s http://localhost:8000") is True
        assert _is_valid_command("git status") is True
        assert _is_valid_command("ls -la /tmp") is True

    def test_safe_prefix(self):
        assert _is_valid_command("python manage.py runserver") is True
        assert _is_valid_command("docker compose up") is True

    def test_unknown_but_short(self):
        # Short unknown commands default to True
        assert _is_valid_command("mycustomtool --flag") is True

    def test_with_shell_chars(self):
        assert _is_valid_command("something long with many words but has pipe | grep") is True

    def test_with_flags(self):
        assert _is_valid_command("something long with many words but --flag") is True


# ---------------------------------------------------------------------------
# _extract_commands — script detection
# ---------------------------------------------------------------------------


class TestExtractCommandsScripts:
    def test_script_with_if(self):
        text = '```bash\nif [ -f "test" ]; then\n  echo "found"\nfi\n```'
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert cmds[0].startswith("bash ")

    def test_script_with_for(self):
        text = '```bash\nfor i in 1 2 3; do\n  echo $i\ndone\n```'
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert cmds[0].startswith("bash ")

    def test_script_with_variable_assignment(self):
        text = '```bash\nVAR=value\necho $VAR\n```'
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert cmds[0].startswith("bash ")

    def test_dollar_prompt_stripped(self):
        text = '```bash\n$ git status\n```'
        cmds = _extract_commands(text)
        assert cmds == ["git status"]

    def test_angle_bracket_prompt_stripped(self):
        text = '```bash\n> echo hello\n```'
        cmds = _extract_commands(text)
        assert cmds == ["echo hello"]

    def test_backslash_continuation(self):
        text = '```bash\ncurl -s \\\n  http://localhost\n```'
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "curl" in cmds[0]
        assert "http://localhost" in cmds[0]

    def test_comments_skipped(self):
        text = '```bash\n# This is a comment\ngit status\n```'
        cmds = _extract_commands(text)
        assert cmds == ["git status"]

    def test_english_in_bash_block_filtered(self):
        text = '```bash\nPlease run the following command to check\n```'
        cmds = _extract_commands(text)
        assert cmds == []


# ---------------------------------------------------------------------------
# _extract_skill_requests / _extract_delegations
# ---------------------------------------------------------------------------


class TestExtractTags:
    def test_skill_tags(self):
        text = "Loading [SKILL:debug] and [SKILL:jenkins-cicd:build]"
        skills = _extract_skill_requests(text)
        assert "debug" in skills
        assert "jenkins-cicd:build" in skills

    def test_no_skills(self):
        assert _extract_skill_requests("No skills here") == []

    def test_delegation(self):
        text = "[DELEGATE:code-writer] Please write this function"
        pairs = _extract_delegations(text)
        assert len(pairs) == 1
        assert pairs[0][0] == "code-writer"
        assert "write this function" in pairs[0][1]

    def test_no_delegation(self):
        assert _extract_delegations("No delegation") == []


# ---------------------------------------------------------------------------
# _resolve_placeholders
# ---------------------------------------------------------------------------


class TestResolvePlaceholders:
    def test_no_placeholders(self):
        assert _resolve_placeholders("git status") == "git status"

    def test_auto_fill_from_context(self):
        _command_context["BUILD_VERSION"] = "1.2.3"
        try:
            result = _resolve_placeholders("deploy <BUILD_VERSION>")
            assert result == "deploy 1.2.3"
        finally:
            _command_context.pop("BUILD_VERSION", None)

    def test_prompt_for_unknown(self):
        with patch("builtins.input", return_value="my-value"):
            result = _resolve_placeholders("deploy <MY_VAR>")
            assert result == "deploy my-value"

    def test_prompt_cancelled(self):
        with patch("builtins.input", side_effect=EOFError):
            result = _resolve_placeholders("deploy <MY_VAR>")
            assert result is None

    def test_empty_value_skips(self):
        with patch("builtins.input", return_value=""):
            result = _resolve_placeholders("deploy <MY_VAR>")
            assert result is None

    def test_curly_brace_placeholder(self):
        _command_context["build_version"] = "2.0.0"
        try:
            result = _resolve_placeholders("deploy {build_version}")
            assert result == "deploy 2.0.0"
        finally:
            _command_context.pop("build_version", None)


# ---------------------------------------------------------------------------
# _extract_context_from_output
# ---------------------------------------------------------------------------


class TestExtractContext:
    def test_build_version(self):
        _command_context.clear()
        output = json.dumps({"build_version": "3.0.1", "number": 42, "job_name": "my-job"})
        _extract_context_from_output(output)
        assert _command_context["BUILD_VERSION"] == "3.0.1"
        assert _command_context["build_version"] == "3.0.1"
        assert _command_context["BUILD_NUMBER"] == "42"
        assert _command_context["job_name"] == "my-job"
        _command_context.clear()

    def test_non_json(self):
        # Should not crash on non-JSON output
        _extract_context_from_output("plain text output")

    def test_non_dict_json(self):
        _extract_context_from_output(json.dumps([1, 2, 3]))


# ---------------------------------------------------------------------------
# _is_safe_command
# ---------------------------------------------------------------------------


class TestIsSafeCommand:
    def test_safe_curl(self):
        assert _is_safe_command("curl -s http://localhost:8000/api") is True

    def test_unsafe_curl_post(self):
        assert _is_safe_command("curl -X POST http://localhost/api") is False

    def test_unsafe_curl_data(self):
        assert _is_safe_command('curl -d \'{"key":"val"}\' http://localhost') is False

    def test_safe_git(self):
        assert _is_safe_command("git status") is True
        assert _is_safe_command("git log --oneline") is True
        assert _is_safe_command("git diff HEAD") is True

    def test_safe_cat_ls(self):
        assert _is_safe_command("cat /etc/hosts") is True
        assert _is_safe_command("ls -la") is True
        assert _is_safe_command("echo hello") is True

    def test_unsafe_commands(self):
        assert _is_safe_command("rm -rf /") is False
        assert _is_safe_command("git push origin main") is False
        assert _is_safe_command("npm install") is False


# ---------------------------------------------------------------------------
# _save_command_to_rules / _is_command_trusted
# ---------------------------------------------------------------------------


class TestCommandTrust:
    def test_save_and_trust(self, tmp_path):
        with patch("code_agents.chat.chat_commands.Path") as mock_path_cls:
            # Use real Path for the rules_dir construction
            pass

        # Direct file system test
        repo = str(tmp_path)
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            _save_command_to_rules("git status", "code-writer", repo)
            assert _is_command_trusted("git status", "code-writer", repo)

    def test_not_trusted_when_no_file(self, tmp_path):
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            assert _is_command_trusted("git status", "code-writer", str(tmp_path)) is False

    def test_save_duplicate_skipped(self, tmp_path):
        repo = str(tmp_path)
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            _save_command_to_rules("git status", "code-writer", repo)
            _save_command_to_rules("git status", "code-writer", repo)  # duplicate
            # Read file and ensure command appears only once
            rules_file = tmp_path / ".code-agents" / "code-writer.md"
            content = rules_file.read_text()
            assert content.count("git status") == 1


# ---------------------------------------------------------------------------
# _load_agent_autorun_config / _check_agent_autorun
# ---------------------------------------------------------------------------


class TestAgentAutorun:
    def test_no_agent_name_returns_global(self):
        config = _load_agent_autorun_config("")
        # With no agent name, returns global config (from _shared/autorun.yaml)
        assert "allow" in config
        assert "block" in config

    def test_no_config_file_returns_global(self):
        with patch("code_agents.core.config.settings") as mock_settings:
            mock_settings.agents_dir = "/nonexistent"
            # No per-agent config, but global cache may exist
            config = _load_agent_autorun_config("code-writer")
            assert isinstance(config, dict)

    def test_valid_config(self, tmp_path):
        import yaml
        agent_dir = tmp_path / "code_writer"
        agent_dir.mkdir()
        config = {"allow": ["git status", "curl -s"], "block": ["rm ", "curl -X DELETE"]}
        (agent_dir / "autorun.yaml").write_text(yaml.dump(config))

        with patch("code_agents.core.config.settings") as mock_settings:
            mock_settings.agents_dir = str(tmp_path)
            result = _load_agent_autorun_config("code-writer")
            assert "git status" in result["allow"]
            assert "rm " in result["block"]

    def test_check_block_takes_priority(self):
        config = {"allow": ["curl"], "block": ["curl -x delete"]}
        with patch("code_agents.chat.chat_commands._load_agent_autorun_config", return_value=config):
            assert _check_agent_autorun("curl -X DELETE http://x", "agent") == "block"

    def test_check_allow(self):
        config = {"allow": ["git status"], "block": []}
        with patch("code_agents.chat.chat_commands._load_agent_autorun_config", return_value=config):
            assert _check_agent_autorun("git status", "agent") == "allow"

    def test_check_no_match(self):
        config = {"allow": ["git status"], "block": ["rm"]}
        with patch("code_agents.chat.chat_commands._load_agent_autorun_config", return_value=config):
            assert _check_agent_autorun("npm test", "agent") is None

    def test_check_empty_config(self):
        with patch("code_agents.chat.chat_commands._load_agent_autorun_config", return_value={}):
            assert _check_agent_autorun("anything", "agent") is None


# ---------------------------------------------------------------------------
# _log_auto_run
# ---------------------------------------------------------------------------


class TestLogAutoRun:
    def test_log_writes_file(self, tmp_path):
        log_file = tmp_path / ".code-agents" / "auto_run.log"
        with patch("pathlib.Path.home", return_value=tmp_path):
            _log_auto_run("git status", "safe-auto-run")
        assert log_file.exists()
        content = log_file.read_text()
        assert "git status" in content
        assert "safe-auto-run" in content

    def test_log_handles_os_error(self, tmp_path):
        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("builtins.open", side_effect=OSError("disk full")):
            # Should not raise
            _log_auto_run("git status", "test")


# ---------------------------------------------------------------------------
# _offer_run_commands — auto_run safe path
# ---------------------------------------------------------------------------


class TestOfferRunCommands:
    def test_empty_commands(self):
        assert _offer_run_commands([], "/tmp") == []

    def test_auto_run_safe_command(self, tmp_path):
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._run_single_command", return_value="ok") as mock_run, \
             patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._log_auto_run"):
            results = _offer_run_commands(["cat /etc/hosts"], repo, auto_run=True)
            assert len(results) == 1
            assert results[0]["output"] == "ok"
            mock_run.assert_called_once()

    def test_auto_run_disabled_by_env(self, tmp_path):
        repo = str(tmp_path)
        with patch.dict(os.environ, {"CODE_AGENTS_AUTO_RUN": "false"}), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=2) as mock_sel, \
             patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False):
            # auto_run=True but env disables it, falls to manual, user picks "No"
            results = _offer_run_commands(["cat file"], repo, auto_run=True)
            assert results == []

    def test_dry_run_mode(self, tmp_path):
        repo = str(tmp_path)
        with patch.dict(os.environ, {"CODE_AGENTS_DRY_RUN": "true"}), \
             patch("code_agents.chat.chat_commands._is_command_trusted", return_value=True):
            results = _offer_run_commands(["git status"], repo, agent_name="code-writer", auto_run=True)
            assert len(results) == 1
            assert "dry-run" in results[0]["output"]

    def test_trusted_command_auto_runs(self, tmp_path):
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=True), \
             patch("code_agents.chat.chat_commands._run_single_command", return_value="ok"), \
             patch("code_agents.chat.chat_commands._log_auto_run"), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(["git status"], repo, agent_name="code-writer", auto_run=True)
            assert len(results) == 1

    def test_unsafe_auto_run_asks_user_no(self, tmp_path):
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=2):  # "No"
            results = _offer_run_commands(["rm -rf /tmp/test"], repo, auto_run=True)
            assert results == []

    def test_superpower_auto_runs(self, tmp_path):
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._run_single_command", return_value="done"), \
             patch("code_agents.chat.chat_commands._log_auto_run"), \
             patch("code_agents.chat.chat_input.is_edit_mode", return_value=False):
            results = _offer_run_commands(["npm install"], repo, agent_name="a", superpower=True)
            assert len(results) == 1

    def test_superpower_blocked_command_asks(self, tmp_path):
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value="block"), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=3):  # "No"
            results = _offer_run_commands(["rm -rf /"], repo, agent_name="a", superpower=True)
            assert results == []

    def test_manual_yes_and_save(self, tmp_path):
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=1), \
             patch("code_agents.chat.chat_commands._run_single_command", return_value="ok"), \
             patch("code_agents.chat.chat_commands._log_auto_run"), \
             patch("code_agents.chat.chat_commands._save_command_to_rules") as mock_save, \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["git status"], repo, agent_name="code-writer", auto_run=False,
            )
            assert len(results) == 1
            mock_save.assert_called_once()

    def test_manual_no_option(self, tmp_path):
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=3), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["npm install"], repo, agent_name="code-writer", auto_run=False,
            )
            assert results == []

    def test_amend_tab(self, tmp_path):
        """Tab pressed in selector -> amendment flow."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=-2), \
             patch("code_agents.chat.chat_commands._amend_prompt", return_value="change the branch"), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["git push"], repo, agent_name="code-writer", auto_run=False,
            )
            assert len(results) == 1
            assert "AMENDMENT" in results[0]["output"]

    def test_command_execution_exception(self, tmp_path):
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=True), \
             patch("code_agents.chat.chat_commands._run_single_command", side_effect=RuntimeError("boom")), \
             patch("code_agents.chat.chat_commands._log_auto_run"), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(["bad-cmd"], repo, agent_name="a", auto_run=True)
            assert results == []

    def test_invalid_command_skipped(self, tmp_path):
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_valid_command", return_value=False):
            results = _offer_run_commands(
                ["Please install the dependencies"], repo, auto_run=False,
            )
            assert results == []

    def test_edit_mode_in_superpower(self, tmp_path):
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._run_single_command", return_value="ok"), \
             patch("code_agents.chat.chat_commands._log_auto_run"), \
             patch("code_agents.chat.chat_input.is_edit_mode", return_value=True):
            results = _offer_run_commands(["echo test"], repo, agent_name="a", superpower=True)
            assert len(results) == 1


# ---------------------------------------------------------------------------
# _run_single_command
# ---------------------------------------------------------------------------


class TestRunSingleCommand:
    def test_blocked_command(self, tmp_path):
        mock_tool = MagicMock()
        mock_tool.is_blocked.return_value = True
        with patch("code_agents.agent_system.bash_tool.BashTool", return_value=mock_tool), \
             patch("code_agents.agent_system.bash_tool.print_command_output"):
            result = _run_single_command("rm -rf /", str(tmp_path))
            assert result == "BLOCKED"

    def test_successful_command(self, tmp_path):
        mock_result = MagicMock()
        mock_result.output = "output text"
        mock_result.error = ""
        mock_result.success = True
        mock_result.exit_code = 0
        mock_tool = MagicMock()
        mock_tool.is_blocked.return_value = False
        mock_tool.execute.return_value = mock_result
        with patch("code_agents.agent_system.bash_tool.BashTool", return_value=mock_tool), \
             patch("code_agents.agent_system.bash_tool.print_command_output"):
            result = _run_single_command("echo hello", str(tmp_path))
            assert result == "output text"

    def test_failed_command(self, tmp_path):
        mock_result = MagicMock()
        mock_result.output = ""
        mock_result.error = "error msg"
        mock_result.success = False
        mock_result.exit_code = 1
        mock_tool = MagicMock()
        mock_tool.is_blocked.return_value = False
        mock_tool.execute.return_value = mock_result
        with patch("code_agents.agent_system.bash_tool.BashTool", return_value=mock_tool), \
             patch("code_agents.agent_system.bash_tool.print_command_output"):
            result = _run_single_command("false", str(tmp_path))
            assert "error msg" in result
            assert "exit code: 1" in result
