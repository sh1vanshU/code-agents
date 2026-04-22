"""Coverage tests for chat_commands.py — covers all missing lines from coverage_run.json.

Missing lines: 127,128,146,277,278,295,296,325,371,372,503,504,540-569,578-607,
633-650,659-663,676,677,685,686
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.chat.chat_commands import (
    _extract_commands,
    _is_valid_command,
    _is_safe_command,
    _resolve_placeholders,
    _extract_context_from_output,
    _command_context,
    _save_command_to_rules,
    _is_command_trusted,
    _load_agent_autorun_config,
    _load_global_autorun_config,
    _check_agent_autorun,
    _offer_run_commands,
    _log_auto_run,
    _run_single_command,
)


# ---------------------------------------------------------------------------
# Lines 127-128, 146: _extract_commands — blank/comment lines flush current,
# trailing current after loop
# ---------------------------------------------------------------------------


class TestExtractCommandsBlankFlush:
    def test_blank_line_flushes_current_command(self):
        """Lines 127-128: blank line encountered while current is non-empty."""
        text = '```bash\necho hello\n\necho world\n```'
        cmds = _extract_commands(text)
        assert "echo hello" in cmds
        assert "echo world" in cmds

    def test_comment_flushes_current_command(self):
        """Lines 127-128: comment line while current is non-empty (continuation)."""
        text = '```bash\necho hello\n# a comment\necho world\n```'
        cmds = _extract_commands(text)
        assert "echo hello" in cmds
        assert "echo world" in cmds

    def test_trailing_current_after_continuation(self):
        """Line 146: current is non-empty after loop ends (last line is continuation)."""
        text = '```bash\ncurl -s \\\n  http://localhost:8080\n```'
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "curl" in cmds[0]

    def test_blank_between_continuation_lines(self):
        """Blank line flushes the in-progress continuation."""
        text = '```bash\ncurl -s \\\n  http://example.com\n\nls -la\n```'
        cmds = _extract_commands(text)
        assert len(cmds) == 2


# ---------------------------------------------------------------------------
# Lines 277-278: _save_command_to_rules — OSError path
# ---------------------------------------------------------------------------


class TestSaveCommandOSError:
    def test_save_os_error_prints_warning(self, tmp_path, capsys):
        """Lines 277-278: OSError during file write prints warning."""
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"), \
             patch("builtins.open", side_effect=OSError("permission denied")):
            _save_command_to_rules("git status", "code-writer", str(tmp_path))
        output = capsys.readouterr().out
        assert "Could not save" in output


# ---------------------------------------------------------------------------
# Lines 295-296: _is_command_trusted — OSError returns False
# ---------------------------------------------------------------------------


class TestIsCommandTrustedOSError:
    def test_trusted_os_error_returns_false(self, tmp_path):
        """Lines 295-296: OSError during file read returns False."""
        # Create the rules file so .is_file() passes, but reading fails
        rules_dir = tmp_path / ".code-agents"
        rules_dir.mkdir()
        rules_file = rules_dir / "code-writer.md"
        rules_file.write_text("some content")

        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"), \
             patch("builtins.open", side_effect=OSError("read error")):
            result = _is_command_trusted("git status", "code-writer", str(tmp_path))
        assert result is False


# ---------------------------------------------------------------------------
# Line 325: _run_single_command — error appended to non-empty output
# ---------------------------------------------------------------------------


class TestRunSingleCommandErrorWithOutput:
    def test_error_appended_to_existing_output(self, tmp_path):
        """Line 325: result has both output and error."""
        mock_result = MagicMock()
        mock_result.output = "some output"
        mock_result.error = "some error"
        mock_result.success = False
        mock_result.exit_code = 1
        mock_tool = MagicMock()
        mock_tool.is_blocked.return_value = False
        mock_tool.execute.return_value = mock_result
        with patch("code_agents.agent_system.bash_tool.BashTool", return_value=mock_tool), \
             patch("code_agents.agent_system.bash_tool.print_command_output"):
            result = _run_single_command("bad cmd", str(tmp_path))
        assert "some output" in result
        assert "some error" in result
        assert "exit code: 1" in result


# ---------------------------------------------------------------------------
# Lines 371-372: _load_agent_autorun_config — per-agent yaml parse error
# ---------------------------------------------------------------------------


class TestLoadAgentAutorunParseError:
    def test_per_agent_yaml_parse_error(self, tmp_path):
        """Lines 371-372: YAML parse error in per-agent config is swallowed."""
        agent_dir = tmp_path / "code_writer"
        agent_dir.mkdir()
        (agent_dir / "autorun.yaml").write_text("invalid: yaml: [broken")

        # Reset global cache
        import code_agents.chat.chat_commands as cc
        old_cache = cc._global_autorun_cache
        cc._global_autorun_cache = {"allow": [], "block": []}
        try:
            with patch("code_agents.core.config.settings") as mock_settings:
                mock_settings.agents_dir = str(tmp_path)
                result = _load_agent_autorun_config("code-writer")
            assert isinstance(result, dict)
        finally:
            cc._global_autorun_cache = old_cache


# ---------------------------------------------------------------------------
# Lines 503-504: _offer_run_commands — dry-run for trusted commands
# Already tested in existing tests, but let's cover the dry_run env var path
# ---------------------------------------------------------------------------


class TestOfferRunCommandsDryRunTrusted:
    def test_dry_run_trusted_command(self, tmp_path):
        """Lines 503-504: DRY_RUN mode for trusted commands."""
        repo = str(tmp_path)
        with patch.dict(os.environ, {"CODE_AGENTS_DRY_RUN": "1"}), \
             patch("code_agents.chat.chat_commands._is_command_trusted", return_value=True), \
             patch("code_agents.chat.chat_commands._log_auto_run"), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(["git status"], repo, agent_name="code-writer")
            assert len(results) == 1
            assert "dry-run" in results[0]["output"]


# ---------------------------------------------------------------------------
# Lines 540-569: _offer_run_commands — invalid command skip, superpower blocked
# with various edit/amend/no flows
# ---------------------------------------------------------------------------


class TestOfferRunCommandsSuperpowerBlocked:
    def test_superpower_blocked_amend(self, tmp_path):
        """Lines 570-577: superpower blocked + Tab amend."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value="block"), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=-2), \
             patch("code_agents.chat.chat_commands._amend_prompt", return_value="use different command"):
            results = _offer_run_commands(["rm -rf /"], repo, agent_name="a", superpower=True)
        assert len(results) == 1
        assert "AMENDMENT" in results[0]["output"]

    def test_superpower_blocked_edit(self, tmp_path, capsys):
        """Lines 583-600: superpower blocked + Edit option."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value="block"), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=2), \
             patch("builtins.input", return_value="echo safe"), \
             patch("code_agents.chat.chat_commands._run_single_command", return_value="ok"), \
             patch("code_agents.chat.chat_commands._log_auto_run"):
            results = _offer_run_commands(["rm -rf /"], repo, agent_name="a", superpower=True)
        assert len(results) == 1

    def test_superpower_blocked_edit_empty(self, tmp_path, capsys):
        """Lines 591-594: superpower blocked + Edit + empty input -> skip."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value="block"), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=2), \
             patch("builtins.input", side_effect=EOFError):
            results = _offer_run_commands(["rm -rf /"], repo, agent_name="a", superpower=True)
        assert results == []

    def test_superpower_blocked_edit_feedback(self, tmp_path, capsys):
        """Lines 595-600: superpower blocked + Edit + // feedback."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value="block"), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=2), \
             patch("builtins.input", return_value="//use a safer command"):
            results = _offer_run_commands(["rm -rf /"], repo, agent_name="a", superpower=True)
        assert len(results) == 1
        assert "USER EDIT FEEDBACK" in results[0]["output"]

    def test_superpower_blocked_yes(self, tmp_path):
        """Line 578: superpower blocked + Yes option runs command."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value="block"), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=0), \
             patch("code_agents.chat.chat_commands._run_single_command", return_value="ok"):
            results = _offer_run_commands(["rm -rf /tmp/test"], repo, agent_name="a", superpower=True)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Lines 633-650: _offer_run_commands — auto_run unsafe edit/amend/feedback paths
# ---------------------------------------------------------------------------


class TestOfferRunCommandsAutoRunUnsafe:
    def test_unsafe_auto_run_amend(self, tmp_path):
        """Lines 609-615: auto_run unsafe + Tab amend."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=-2), \
             patch("code_agents.chat.chat_commands._amend_prompt", return_value="do it differently"):
            results = _offer_run_commands(["npm install"], repo, auto_run=True)
        assert len(results) == 1
        assert "AMENDMENT" in results[0]["output"]

    def test_unsafe_auto_run_edit(self, tmp_path):
        """Lines 621-639: auto_run unsafe + Edit option sends feedback."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=1), \
             patch("builtins.input", return_value="npm ci"):
            results = _offer_run_commands(["npm install"], repo, auto_run=True)
        assert len(results) == 1
        assert results[0]["command"] == "npm install"
        assert "USER EDIT FEEDBACK" in results[0]["output"]

    def test_unsafe_auto_run_edit_empty(self, tmp_path):
        """Lines 629-632: auto_run unsafe + Edit + empty -> skip."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=1), \
             patch("builtins.input", side_effect=EOFError):
            results = _offer_run_commands(["npm install"], repo, auto_run=True)
        assert results == []

    def test_unsafe_auto_run_edit_feedback(self, tmp_path):
        """Lines 633-638: auto_run unsafe + Edit + // feedback."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=1), \
             patch("builtins.input", return_value="//use npm ci instead"):
            results = _offer_run_commands(["npm install"], repo, auto_run=True)
        assert len(results) == 1
        assert "USER EDIT FEEDBACK" in results[0]["output"]


# ---------------------------------------------------------------------------
# Lines 659-686: _offer_run_commands — manual (no auto_run, no superpower) paths
# ---------------------------------------------------------------------------


class TestOfferRunCommandsManualPaths:
    def test_manual_amend_empty_falls_through(self, tmp_path):
        """Lines 650-656: manual mode + Tab amend with empty amendment → falls through to options[-2].

        When amend returns empty, the code falls through to `options[choice]` where choice=-2,
        which indexes from end. For 4 options (Yes, Save, Edit, No), options[-2] = "Edit".
        Then the Edit path calls input() — we mock that to return empty → skip.
        """
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=-2), \
             patch("code_agents.chat.chat_commands._amend_prompt", return_value=""), \
             patch("builtins.input", side_effect=EOFError), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["git push"], repo, agent_name="code-writer", auto_run=False,
            )
        # Falls through to Edit (options[-2]) → EOFError → empty → skip
        assert results == []

    def test_manual_no_agent_options(self, tmp_path):
        """Lines 647-648: no agent_name → 3 options (Yes/Edit/No)."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=0) as mock_sel, \
             patch("code_agents.chat.chat_commands._run_single_command", return_value="ok"):
            results = _offer_run_commands(["git push"], repo, auto_run=False)
        assert len(results) == 1
        # 3-option selector was used (Yes/Edit/No)
        call_args = mock_sel.call_args
        assert len(call_args[0][1]) == 3

    def test_manual_edit_option(self, tmp_path):
        """Lines 664-682: manual mode + Edit option sends feedback."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=2), \
             patch("builtins.input", return_value="git push origin develop"), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["git push origin main"], repo, agent_name="code-writer", auto_run=False,
            )
        assert len(results) == 1
        assert results[0]["command"] == "git push origin main"
        assert "USER EDIT FEEDBACK" in results[0]["output"]

    def test_manual_edit_empty(self, tmp_path):
        """Lines 672-674: manual Edit + empty -> skip."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=2), \
             patch("builtins.input", side_effect=KeyboardInterrupt), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["git push"], repo, agent_name="code-writer", auto_run=False,
            )
        assert results == []

    def test_manual_edit_feedback(self, tmp_path):
        """Lines 676-681: manual Edit + // feedback."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=2), \
             patch("builtins.input", return_value="//push to develop instead"), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["git push origin main"], repo, agent_name="code-writer", auto_run=False,
            )
        assert len(results) == 1
        assert "USER EDIT FEEDBACK" in results[0]["output"]

    def test_manual_yes_and_save_option(self, tmp_path):
        """Lines 685-686: manual mode with 'Yes & Save' option."""
        repo = str(tmp_path)
        # Selecting option index 1 (second option = "Yes & Save to code-writer rules")
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=1), \
             patch("code_agents.chat.chat_commands._run_single_command", return_value="ok"), \
             patch("code_agents.chat.chat_commands._save_command_to_rules") as mock_save, \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["git status"], repo, agent_name="code-writer", auto_run=False,
            )
        assert len(results) == 1
        mock_save.assert_called_once()

    def test_manual_no_option_with_agent(self, tmp_path, capsys):
        """Lines 660-662: manual mode + No option."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=3), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["npm install"], repo, agent_name="code-writer", auto_run=False,
            )
        assert results == []
        assert "Skipped" in capsys.readouterr().out

    def test_placeholder_resolve_eof_during_offer(self, tmp_path):
        """Lines 691-692: EOFError during placeholder resolution."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=True), \
             patch("code_agents.chat.chat_commands._log_auto_run"), \
             patch("code_agents.chat.chat_commands._resolve_placeholders", side_effect=EOFError), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["deploy <VERSION>"], repo, agent_name="a", auto_run=True,
            )
        assert results == []

    def test_command_keyboard_interrupt(self, tmp_path, capsys):
        """Lines 707-708: KeyboardInterrupt during command execution."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=True), \
             patch("code_agents.chat.chat_commands._log_auto_run"), \
             patch("code_agents.chat.chat_commands._run_single_command", side_effect=KeyboardInterrupt), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["long-running-cmd"], repo, agent_name="a", auto_run=True,
            )
        assert results == []
        assert "interrupted" in capsys.readouterr().out

    def test_save_after_exception(self, tmp_path, capsys):
        """Lines 717-718: save_command_to_rules raises exception."""
        repo = str(tmp_path)
        with patch("code_agents.chat.chat_commands._is_command_trusted", return_value=False), \
             patch("code_agents.chat.chat_commands._check_agent_autorun", return_value=None), \
             patch("code_agents.chat.chat_commands._tab_selector", return_value=1), \
             patch("code_agents.chat.chat_commands._run_single_command", return_value="ok"), \
             patch("code_agents.chat.chat_commands._save_command_to_rules", side_effect=RuntimeError("disk")), \
             patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents"):
            results = _offer_run_commands(
                ["git status"], repo, agent_name="code-writer", auto_run=False,
            )
        assert len(results) == 1
        assert "Could not save" in capsys.readouterr().out
