"""Tests for code_agents/chat/chat_slash_ops.py — /run, /exec, /bash, /btw, /repo,
/endpoints, /superpower, /layout, /voice, /plan, /mcp slash command handlers."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from code_agents.chat.chat_slash_ops import _handle_operations


# ---------------------------------------------------------------------------
# /run
# ---------------------------------------------------------------------------

class TestRunCommand:
    def test_run_no_arg_prints_usage(self, capsys):
        result = _handle_operations("/run", "", {}, "http://localhost:8000")
        assert result is None
        assert "Usage" in capsys.readouterr().out

    def test_run_with_arg_calls_run_single(self):
        state = {"repo_path": "/my/repo"}
        with patch("code_agents.chat.chat_slash_ops._run_single_command") as mock_run:
            result = _handle_operations("/run", "ls -la", state, "http://localhost:8000")
        assert result is None
        mock_run.assert_called_once_with("ls -la", "/my/repo")

    def test_run_defaults_repo_path(self):
        state = {}
        with patch("code_agents.chat.chat_slash_ops._run_single_command") as mock_run:
            _handle_operations("/run", "pwd", state, "http://localhost:8000")
        mock_run.assert_called_once_with("pwd", ".")


# ---------------------------------------------------------------------------
# /execute, /exec
# ---------------------------------------------------------------------------

class TestExecCommand:
    def test_exec_no_arg_prints_usage(self, capsys):
        result = _handle_operations("/exec", "", {}, "http://localhost:8000")
        assert result is None
        assert "Usage" in capsys.readouterr().out

    def test_execute_alias(self, capsys):
        result = _handle_operations("/execute", "", {}, "http://localhost:8000")
        assert result is None
        assert "Usage" in capsys.readouterr().out

    def test_exec_with_arg_returns_exec_feedback(self):
        state = {"repo_path": "/repo"}
        with patch("code_agents.chat.chat_slash_ops._resolve_placeholders", return_value="ls"):
            with patch("code_agents.chat.chat_slash_ops._run_single_command", return_value="file1\nfile2"):
                result = _handle_operations("/exec", "ls", state, "http://localhost:8000")
        assert result == "exec_feedback"
        assert state["_exec_feedback"]["command"] == "ls"
        assert state["_exec_feedback"]["output"] == "file1\nfile2"

    def test_exec_placeholder_resolve_fails(self):
        state = {}
        with patch("code_agents.chat.chat_slash_ops._resolve_placeholders", return_value=None):
            result = _handle_operations("/exec", "test", state, "http://localhost:8000")
        assert result is None


# ---------------------------------------------------------------------------
# /bash
# ---------------------------------------------------------------------------

class TestBashCommand:
    def test_bash_no_arg_prints_usage(self, capsys):
        result = _handle_operations("/bash", "", {}, "http://localhost:8000")
        assert result is None
        assert "Usage" in capsys.readouterr().out

    def test_bash_runs_command_success(self, capsys):
        import subprocess
        mock_result = MagicMock()
        mock_result.stdout = "hello world\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        state = {"repo_path": "/repo"}
        with patch("subprocess.run", return_value=mock_result):
            with patch("builtins.input", side_effect=EOFError):
                result = _handle_operations("/bash", "echo hello", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "hello world" in output
        assert "Done" in output

    def test_bash_nonzero_exit_code(self, capsys):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "error msg"
        mock_result.returncode = 1
        state = {}
        with patch("subprocess.run", return_value=mock_result):
            with patch("builtins.input", side_effect=EOFError):
                _handle_operations("/bash", "false", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Exit code: 1" in output

    def test_bash_timeout(self, capsys):
        import subprocess
        state = {}
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 120)):
            _handle_operations("/bash", "sleep 999", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Timed out" in output

    def test_bash_generic_exception(self, capsys):
        state = {}
        with patch("subprocess.run", side_effect=OSError("disk error")):
            _handle_operations("/bash", "test", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Error" in output

    def test_bash_feed_output_yes(self):
        mock_result = MagicMock()
        mock_result.stdout = "some output\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        state = {"repo_path": "/repo"}
        with patch("subprocess.run", return_value=mock_result):
            with patch("builtins.input", return_value="y"):
                result = _handle_operations("/bash", "echo test", state, "http://localhost:8000")
        assert result is not None
        assert "echo test" in result
        assert "some output" in result

    def test_bash_feed_output_no(self, capsys):
        mock_result = MagicMock()
        mock_result.stdout = "output\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        state = {"repo_path": "/repo"}
        with patch("subprocess.run", return_value=mock_result):
            with patch("builtins.input", return_value="n"):
                result = _handle_operations("/bash", "echo hi", state, "http://localhost:8000")
        assert result is None

    def test_bash_no_output_no_feed_prompt(self, capsys):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0
        state = {}
        with patch("subprocess.run", return_value=mock_result):
            result = _handle_operations("/bash", "true", state, "http://localhost:8000")
        assert result is None


# ---------------------------------------------------------------------------
# /btw
# ---------------------------------------------------------------------------

class TestBtwCommand:
    def test_btw_no_arg_no_messages(self, capsys):
        state = {}
        result = _handle_operations("/btw", "", state, "http://localhost:8000")
        assert result is None
        assert "No side messages" in capsys.readouterr().out

    def test_btw_no_arg_shows_messages(self, capsys):
        state = {"_btw_messages": ["msg1", "msg2"]}
        _handle_operations("/btw", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "msg1" in output
        assert "msg2" in output
        assert "Side messages" in output

    def test_btw_clear(self, capsys):
        state = {"_btw_messages": ["old"]}
        _handle_operations("/btw", "clear", state, "http://localhost:8000")
        assert state["_btw_messages"] == []
        assert "cleared" in capsys.readouterr().out

    def test_btw_add_message(self, capsys):
        state = {}
        _handle_operations("/btw", "remember to use TypeScript", state, "http://localhost:8000")
        assert "remember to use TypeScript" in state["_btw_messages"]
        assert "Noted" in capsys.readouterr().out

    def test_btw_add_multiple(self):
        state = {}
        _handle_operations("/btw", "first", state, "http://localhost:8000")
        _handle_operations("/btw", "second", state, "http://localhost:8000")
        assert len(state["_btw_messages"]) == 2


# ---------------------------------------------------------------------------
# /superpower
# ---------------------------------------------------------------------------

class TestSuperpowerCommand:
    def test_superpower_on(self, capsys):
        state = {}
        _handle_operations("/superpower", "", state, "http://localhost:8000")
        assert state["superpower"] is True
        assert os.environ.get("CODE_AGENTS_SUPERPOWER") == "1"
        assert "SUPERPOWER" in capsys.readouterr().out
        # cleanup
        os.environ.pop("CODE_AGENTS_SUPERPOWER", None)

    def test_superpower_off(self, capsys):
        state = {"superpower": True}
        os.environ["CODE_AGENTS_SUPERPOWER"] = "1"
        _handle_operations("/superpower", "off", state, "http://localhost:8000")
        assert state["superpower"] is False
        assert "CODE_AGENTS_SUPERPOWER" not in os.environ
        assert "OFF" in capsys.readouterr().out

    def test_superpower_on_with_arg(self, capsys):
        state = {}
        _handle_operations("/superpower", "on", state, "http://localhost:8000")
        assert state["superpower"] is True
        os.environ.pop("CODE_AGENTS_SUPERPOWER", None)


# ---------------------------------------------------------------------------
# /layout
# ---------------------------------------------------------------------------

class TestLayoutCommand:
    def test_layout_no_arg_shows_help(self, capsys):
        state = {}
        _handle_operations("/layout", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "/layout on" in output
        assert "/layout off" in output

    def test_layout_on_no_support(self, capsys):
        state = {}
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=False):
            _handle_operations("/layout", "on", state, "http://localhost:8000")
        assert "does not support" in capsys.readouterr().out

    def test_layout_on_supported(self, capsys):
        state = {"agent": "code-writer"}
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=True):
            with patch("code_agents.chat.terminal_layout.enter_layout"):
                with patch("code_agents.chat.terminal_layout.draw_input_bar"):
                    _handle_operations("/layout", "on", state, "http://localhost:8000")
        assert state.get("_fixed_layout") is True
        assert "Fixed layout ON" in capsys.readouterr().out

    def test_layout_off(self, capsys):
        state = {"_fixed_layout": True}
        with patch("code_agents.chat.terminal_layout.exit_layout"):
            _handle_operations("/layout", "off", state, "http://localhost:8000")
        assert state["_fixed_layout"] is False
        assert "restored" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# /voice
# ---------------------------------------------------------------------------

class TestVoiceCommand:
    def test_voice_not_available(self, capsys):
        state = {}
        with patch("code_agents.ui.voice_input.is_available", return_value=False):
            with patch("code_agents.ui.voice_input.get_install_instructions", return_value="Install sounddevice"):
                _handle_operations("/voice", "", state, "http://localhost:8000")
        assert "Install sounddevice" in capsys.readouterr().out

    def test_voice_no_speech_detected(self, capsys):
        state = {}
        with patch("code_agents.ui.voice_input.is_available", return_value=True):
            with patch("code_agents.ui.voice_input.listen_and_transcribe", return_value=None):
                _handle_operations("/voice", "", state, "http://localhost:8000")
        assert "No speech" in capsys.readouterr().out

    def test_voice_speech_accepted(self, capsys):
        state = {}
        with patch("code_agents.ui.voice_input.is_available", return_value=True):
            with patch("code_agents.ui.voice_input.listen_and_transcribe", return_value="hello world"):
                with patch("builtins.input", return_value="y"):
                    result = _handle_operations("/voice", "", state, "http://localhost:8000")
        assert result == "hello world"

    def test_voice_speech_cancelled(self, capsys):
        state = {}
        with patch("code_agents.ui.voice_input.is_available", return_value=True):
            with patch("code_agents.ui.voice_input.listen_and_transcribe", return_value="hello"):
                with patch("builtins.input", return_value="n"):
                    result = _handle_operations("/voice", "", state, "http://localhost:8000")
        assert result is None
        assert "Cancelled" in capsys.readouterr().out

    def test_voice_speech_edit(self, capsys):
        state = {}
        mock_readline = MagicMock()
        with patch("code_agents.ui.voice_input.is_available", return_value=True):
            with patch("code_agents.ui.voice_input.listen_and_transcribe", return_value="hello"):
                with patch("builtins.input", side_effect=["edit", "hello world edited"]):
                    with patch.dict("sys.modules", {"readline": mock_readline}):
                        result = _handle_operations("/voice", "", state, "http://localhost:8000")
        assert result == "hello world edited"

    def test_voice_custom_timeout(self, capsys):
        state = {}
        with patch("code_agents.ui.voice_input.is_available", return_value=True):
            with patch("code_agents.ui.voice_input.listen_and_transcribe", return_value=None) as mock_listen:
                _handle_operations("/voice", "30", state, "http://localhost:8000")
        mock_listen.assert_called_once_with(timeout=30)

    def test_voice_confirm_eof(self, capsys):
        state = {}
        with patch("code_agents.ui.voice_input.is_available", return_value=True):
            with patch("code_agents.ui.voice_input.listen_and_transcribe", return_value="text"):
                with patch("builtins.input", side_effect=EOFError):
                    result = _handle_operations("/voice", "", state, "http://localhost:8000")
        assert result is None


# ---------------------------------------------------------------------------
# /plan
# ---------------------------------------------------------------------------

class TestPlanCommand:
    def _mock_pm(self, **kwargs):
        pm = MagicMock()
        pm.active_plan = kwargs.get("active_plan", None)
        pm.format_plan.return_value = "Plan display"
        pm.get_status.return_value = {"status": "executing", "approval_mode": "auto", "completed_steps": 1, "steps": 3}
        pm.build_plan_approval_questionnaire.return_value = "Choose: 1/2/3"
        return pm

    def test_plan_no_arg_no_active_plan_no_plans(self, capsys):
        pm = self._mock_pm()
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            with patch("code_agents.agent_system.plan_manager.list_plans", return_value=[]):
                _handle_operations("/plan", "", {}, "http://localhost:8000")
        assert "No plans yet" in capsys.readouterr().out

    def test_plan_no_arg_with_saved_plans(self, capsys):
        pm = self._mock_pm()
        plans = [{"id": "abc", "title": "Login feature", "progress": "2/5"}]
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            with patch("code_agents.agent_system.plan_manager.list_plans", return_value=plans):
                _handle_operations("/plan", "", {}, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Login feature" in output

    def test_plan_no_arg_proposed_plan_approve_auto(self, capsys):
        from code_agents.agent_system.plan_manager import PlanStatus, ApprovalMode
        active = MagicMock()
        active.status = PlanStatus.PROPOSED
        active.title = "My plan"
        pm = self._mock_pm(active_plan=active)
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            with patch("builtins.input", return_value="1"):
                _handle_operations("/plan", "", {}, "http://localhost:8000")
        pm.approve.assert_called_once_with(ApprovalMode.AUTO_ACCEPT)

    def test_plan_no_arg_proposed_plan_manual(self, capsys):
        from code_agents.agent_system.plan_manager import PlanStatus, ApprovalMode
        active = MagicMock()
        active.status = PlanStatus.PROPOSED
        pm = self._mock_pm(active_plan=active)
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            # _question_selector returns 0-based index; 1 = manual approve
            with patch("code_agents.agent_system.questionnaire._question_selector", return_value=1):
                _handle_operations("/plan", "", {}, "http://localhost:8000")
        pm.approve.assert_called_once_with(ApprovalMode.MANUAL_APPROVE)

    def test_plan_no_arg_proposed_plan_feedback(self, capsys):
        from code_agents.agent_system.plan_manager import PlanStatus
        active = MagicMock()
        active.status = PlanStatus.PROPOSED
        pm = self._mock_pm(active_plan=active)
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            with patch("builtins.input", side_effect=["3", "add more tests"]):
                _handle_operations("/plan", "", {}, "http://localhost:8000")
        pm.edit_plan.assert_called_once_with("add more tests")

    def test_plan_no_arg_proposed_plan_feedback_empty(self, capsys):
        from code_agents.agent_system.plan_manager import PlanStatus
        active = MagicMock()
        active.status = PlanStatus.PROPOSED
        pm = self._mock_pm(active_plan=active)
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            with patch("builtins.input", side_effect=["3", ""]):
                _handle_operations("/plan", "", {}, "http://localhost:8000")
        pm.edit_plan.assert_not_called()

    def test_plan_no_arg_active_plan_shows_status(self, capsys):
        from code_agents.agent_system.plan_manager import PlanStatus
        active = MagicMock()
        active.status = PlanStatus.EXECUTING
        pm = self._mock_pm(active_plan=active)
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "", {}, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Plan display" in output

    def test_plan_approve_enhanced(self, capsys):
        from code_agents.agent_system.plan_manager import PlanStatus, ApprovalMode
        active = MagicMock()
        active.status = PlanStatus.PROPOSED
        active.title = "My plan"
        pm = self._mock_pm(active_plan=active)
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "approve", {}, "http://localhost:8000")
        pm.approve.assert_called_once_with(ApprovalMode.AUTO_ACCEPT)

    def test_plan_approve_legacy(self, capsys):
        pm = self._mock_pm()
        plan_data = {"title": "Old plan", "total": 3}
        state = {"_last_plan_id": "xyz"}
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            with patch("code_agents.agent_system.plan_manager.load_plan", return_value=plan_data):
                _handle_operations("/plan", "approve", state, "http://localhost:8000")
        assert state.get("plan_active") == "xyz"

    def test_plan_approve_no_plan(self, capsys):
        pm = self._mock_pm()
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "approve", {}, "http://localhost:8000")
        assert "No plan" in capsys.readouterr().out

    def test_plan_approve_manual(self, capsys):
        from code_agents.agent_system.plan_manager import PlanStatus, ApprovalMode
        active = MagicMock()
        active.status = PlanStatus.DRAFT
        active.title = "Plan"
        pm = self._mock_pm(active_plan=active)
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "approve manual", {}, "http://localhost:8000")
        pm.approve.assert_called_once_with(ApprovalMode.MANUAL_APPROVE)

    def test_plan_approve_manual_no_plan(self, capsys):
        pm = self._mock_pm()
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "approve manual", {}, "http://localhost:8000")
        assert "No plan" in capsys.readouterr().out

    def test_plan_status_enhanced(self, capsys):
        from code_agents.agent_system.plan_manager import PlanStatus
        active = MagicMock()
        active.status = PlanStatus.EXECUTING
        pm = self._mock_pm(active_plan=active)
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "status", {}, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Completed" in output

    def test_plan_status_legacy(self, capsys):
        pm = self._mock_pm()
        plan_data = {
            "title": "Legacy plan",
            "steps": [
                {"text": "step1", "done": True},
                {"text": "step2", "done": False},
            ],
            "current_step": 1,
            "total": 2,
        }
        state = {"plan_active": "p1"}
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            with patch("code_agents.agent_system.plan_manager.load_plan", return_value=plan_data):
                _handle_operations("/plan", "status", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Legacy plan" in output

    def test_plan_status_no_plan(self, capsys):
        pm = self._mock_pm()
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "status", {}, "http://localhost:8000")
        assert "No active plan" in capsys.readouterr().out

    def test_plan_edit_with_feedback(self, capsys):
        from code_agents.agent_system.plan_manager import PlanStatus
        active = MagicMock()
        active.status = PlanStatus.PROPOSED
        pm = self._mock_pm(active_plan=active)
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "edit add more detail", {}, "http://localhost:8000")
        pm.edit_plan.assert_called_once_with("add more detail")

    def test_plan_edit_no_feedback_no_plan(self, capsys):
        pm = self._mock_pm()
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "edit", {}, "http://localhost:8000")
        assert "No plan" in capsys.readouterr().out

    def test_plan_reject_active(self, capsys):
        active = MagicMock()
        active.title = "Bad plan"
        pm = self._mock_pm(active_plan=active)
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "reject", {}, "http://localhost:8000")
        pm.reject.assert_called_once()

    def test_plan_reject_no_active(self, capsys):
        pm = self._mock_pm()
        state = {"plan_active": "x", "_last_plan_id": "y"}
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "reject", state, "http://localhost:8000")
        assert "plan_active" not in state
        assert "_last_plan_id" not in state

    def test_plan_complete_executing(self, capsys):
        from code_agents.agent_system.plan_manager import PlanStatus
        active = MagicMock()
        active.status = PlanStatus.EXECUTING
        active.title = "Done plan"
        pm = self._mock_pm(active_plan=active)
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "complete", {}, "http://localhost:8000")
        pm.complete.assert_called_once()

    def test_plan_complete_not_executing(self, capsys):
        pm = self._mock_pm()
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "complete", {}, "http://localhost:8000")
        assert "No executing" in capsys.readouterr().out

    def test_plan_list(self, capsys):
        pm = self._mock_pm()
        plans = [{"id": "a", "title": "Plan A", "progress": "1/3"}]
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            with patch("code_agents.agent_system.plan_manager.list_plans", return_value=plans):
                _handle_operations("/plan", "list", {}, "http://localhost:8000")
        assert "Plan A" in capsys.readouterr().out

    def test_plan_list_empty(self, capsys):
        pm = self._mock_pm()
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            with patch("code_agents.agent_system.plan_manager.list_plans", return_value=[]):
                _handle_operations("/plan", "list", {}, "http://localhost:8000")
        assert "No plans" in capsys.readouterr().out

    def test_plan_prompt_returns_signal(self):
        pm = self._mock_pm()
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            result = _handle_operations("/plan", "implement login with OAuth", {}, "http://localhost:8000")
        assert result == "plan_prompt"


# ---------------------------------------------------------------------------
# /repo
# ---------------------------------------------------------------------------

class TestRepoCommand:
    def _mock_rm(self, repos=None, active=None):
        rm = MagicMock()
        rm.repos = repos or {}
        rm.active_repo = active
        return rm

    def test_repo_no_arg_no_repos(self, capsys):
        rm = self._mock_rm()
        rm.list_repos.return_value = []
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            _handle_operations("/repo", "", {"repo_path": "/r"}, "http://localhost:8000")
        assert "No repos" in capsys.readouterr().out

    def test_repo_no_arg_lists_repos(self, capsys):
        rm = self._mock_rm(repos={"my-app": True}, active="/repos/my-app")
        ctx = MagicMock()
        ctx.path = "/repos/my-app"
        ctx.name = "my-app"
        ctx.git_branch = "main"
        rm.list_repos.return_value = [ctx]
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            _handle_operations("/repo", "", {"repo_path": "/repos/my-app"}, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "my-app" in output
        assert "active" in output

    def test_repo_add_success(self, capsys):
        rm = self._mock_rm(repos={"x": True})
        ctx = MagicMock()
        ctx.name = "new-repo"
        ctx.path = "/repos/new-repo"
        ctx.git_branch = "develop"
        ctx.config_file = ".code-agents/config.yaml"
        rm.add_repo.return_value = ctx
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            _handle_operations("/repo", "add /repos/new-repo", {"repo_path": "/r"}, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Registered" in output
        assert "new-repo" in output

    def test_repo_add_no_path(self, capsys):
        rm = self._mock_rm(repos={"x": True})
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            result = _handle_operations("/repo", "add ", {"repo_path": "/r"}, "http://localhost:8000")
        assert "Usage" in capsys.readouterr().out

    def test_repo_add_error(self, capsys):
        rm = self._mock_rm(repos={"x": True})
        rm.add_repo.side_effect = ValueError("Not a git repo")
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            _handle_operations("/repo", "add /bad/path", {"repo_path": "/r"}, "http://localhost:8000")
        assert "Not a git repo" in capsys.readouterr().out

    def test_repo_remove_success(self, capsys):
        rm = self._mock_rm(repos={"my-repo": True})
        rm.remove_repo.return_value = True
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            _handle_operations("/repo", "remove my-repo", {"repo_path": "/r"}, "http://localhost:8000")
        assert "Removed" in capsys.readouterr().out

    def test_repo_remove_not_found(self, capsys):
        rm = self._mock_rm(repos={"x": True})
        rm.remove_repo.return_value = False
        rm.list_repos.return_value = []
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            _handle_operations("/repo", "remove nonexistent", {"repo_path": "/r"}, "http://localhost:8000")
        assert "not found" in capsys.readouterr().out

    def test_repo_remove_no_name(self, capsys):
        rm = self._mock_rm(repos={"x": True})
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            result = _handle_operations("/repo", "remove ", {"repo_path": "/r"}, "http://localhost:8000")
        assert "Usage" in capsys.readouterr().out

    def test_repo_switch(self, capsys):
        rm = self._mock_rm(repos={"my-app": True})
        ctx = MagicMock()
        ctx.path = "/repos/my-app"
        ctx.name = "my-app"
        ctx.git_branch = "main"
        rm.switch_repo.return_value = ctx
        state = {"repo_path": "/old"}
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            with patch("code_agents.core.env_loader.load_all_env"):
                _handle_operations("/repo", "my-app", state, "http://localhost:8000")
        assert state["repo_path"] == "/repos/my-app"
        assert "Switched" in capsys.readouterr().out

    def test_repo_switch_error(self, capsys):
        rm = self._mock_rm(repos={"x": True})
        rm.switch_repo.side_effect = ValueError("Unknown repo")
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            _handle_operations("/repo", "unknown", {"repo_path": "/r"}, "http://localhost:8000")
        assert "Unknown repo" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# /mcp
# ---------------------------------------------------------------------------

class TestMcpCommand:
    def test_mcp_no_servers(self, capsys):
        state = {"agent": "code-writer", "repo_path": "/r"}
        with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value={}):
            _handle_operations("/mcp", "", state, "http://localhost:8000")
        assert "No MCP servers" in capsys.readouterr().out

    def test_mcp_shows_servers(self, capsys):
        srv = MagicMock()
        srv.is_stdio = True
        srv.agents = ["code-writer"]
        servers = {"my-server": srv}
        state = {"agent": "code-writer", "repo_path": "/r"}
        with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value=servers):
            _handle_operations("/mcp", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "my-server" in output
        assert "stdio" in output


# ---------------------------------------------------------------------------
# /endpoints (basic coverage — scan, list, run paths)
# ---------------------------------------------------------------------------

class TestEndpointsCommand:
    def test_endpoints_scan(self, capsys):
        mock_result = MagicMock()
        mock_result.total = 3
        mock_result.summary.return_value = "3 endpoints"
        state = {"repo_path": "/repo"}
        with patch("code_agents.cicd.endpoint_scanner.scan_all", return_value=mock_result):
            with patch("code_agents.cicd.endpoint_scanner.save_cache"):
                _handle_operations("/endpoints", "scan", state, "http://localhost:8000")
        assert "3 endpoints" in capsys.readouterr().out

    def test_endpoints_scan_none_found(self, capsys):
        mock_result = MagicMock()
        mock_result.total = 0
        state = {"repo_path": "/repo"}
        with patch("code_agents.cicd.endpoint_scanner.scan_all", return_value=mock_result):
            _handle_operations("/endpoints", "scan", state, "http://localhost:8000")
        assert "No endpoints" in capsys.readouterr().out

    def test_endpoints_list_no_cache(self, capsys):
        mock_result = MagicMock()
        mock_result.total = 0
        state = {"repo_path": "/repo"}
        with patch("code_agents.cicd.endpoint_scanner.load_cache", return_value=None):
            with patch("code_agents.cicd.endpoint_scanner.scan_all", return_value=mock_result):
                _handle_operations("/endpoints", "", state, "http://localhost:8000")
        assert "No endpoints" in capsys.readouterr().out

    def test_endpoints_list_with_cache(self, capsys):
        cached = {
            "repo_name": "my-app",
            "summary": "5 REST, 1 gRPC",
            "rest_endpoints": [{"method": "GET", "path": "/api/health", "controller": "HealthCtrl"}],
            "grpc_services": [],
            "kafka_listeners": [],
        }
        state = {"repo_path": "/repo"}
        with patch("code_agents.cicd.endpoint_scanner.load_cache", return_value=cached):
            _handle_operations("/endpoints", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "my-app" in output
        assert "/api/health" in output

    def test_endpoints_run_invalid_type(self, capsys):
        state = {"repo_path": "/repo"}
        _handle_operations("/endpoints", "run xml", state, "http://localhost:8000")
        assert "Unknown type" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# /confirm
# ---------------------------------------------------------------------------

class TestConfirmCommand:
    def test_confirm_no_arg_shows_status(self, capsys):
        state = {}
        result = _handle_operations("/confirm", "", state, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "Requirement Confirmation" in output
        assert "Enabled" in output
        assert "Status" in output

    def test_confirm_on(self, capsys):
        state = {}
        result = _handle_operations("/confirm", "on", state, "http://localhost:8000")
        assert result is None
        assert state["_require_confirm_enabled"] is True
        assert "ON" in capsys.readouterr().out

    def test_confirm_off(self, capsys):
        state = {}
        result = _handle_operations("/confirm", "off", state, "http://localhost:8000")
        assert result is None
        assert state["_require_confirm_enabled"] is False
        assert "OFF" in capsys.readouterr().out

    def test_confirm_show_no_requirement(self, capsys):
        state = {}
        result = _handle_operations("/confirm", "show", state, "http://localhost:8000")
        assert result is None
        assert "No confirmed requirement" in capsys.readouterr().out

    def test_confirm_show_with_requirement(self, capsys):
        state = {"_confirmed_requirement": "Add OAuth login page"}
        result = _handle_operations("/confirm", "show", state, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "Add OAuth login page" in output
        assert "Confirmed Requirement" in output

    def test_confirm_status_pending(self, capsys):
        from code_agents.agent_system.requirement_confirm import RequirementStatus
        state = {"_req_status": RequirementStatus.PENDING}
        result = _handle_operations("/confirm", "", state, "http://localhost:8000")
        assert result is None
        assert "pending" in capsys.readouterr().out

    def test_confirm_status_confirmed_with_spec_preview(self, capsys):
        from code_agents.agent_system.requirement_confirm import RequirementStatus
        state = {
            "_req_status": RequirementStatus.CONFIRMED,
            "_confirmed_requirement": "First line of spec\nSecond line",
        }
        result = _handle_operations("/confirm", "", state, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "confirmed" in output
        assert "First line of spec" in output

    def test_confirm_status_string_enum_coercion(self, capsys):
        """Status stored as string should be coerced to enum."""
        state = {"_req_status": "pending"}
        result = _handle_operations("/confirm", "", state, "http://localhost:8000")
        assert result is None
        assert "pending" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Unknown command
# ---------------------------------------------------------------------------

class TestUnknownCommand:
    def test_unknown_command_returns_not_handled(self):
        result = _handle_operations("/foobar", "", {}, "http://localhost:8000")
        assert result == "_not_handled"
