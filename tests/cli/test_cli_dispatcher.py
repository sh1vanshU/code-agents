"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestMainDispatcher:
    """Test the main() CLI dispatcher."""

    def test_help_flag(self, capsys):
        from code_agents.cli import main
        with patch.object(sys, "argv", ["code-agents", "help"]):
            main()
        output = capsys.readouterr().out
        assert "code-agents" in output
        assert "USAGE" in output

    def test_version_flag(self, capsys):
        from code_agents.cli import main
        with patch.object(sys, "argv", ["code-agents", "version"]):
            main()
        output = capsys.readouterr().out
        assert "Python" in output

    def test_unknown_command(self, capsys):
        from code_agents.cli import main
        with patch.object(sys, "argv", ["code-agents", "foobar"]):
            with pytest.raises(SystemExit):
                main()
        output = capsys.readouterr().out
        assert "Unknown command" in output
class TestMainDispatcherExtended:
    """Test main() dispatcher with more commands."""

    def test_dispatch_standup(self, capsys):
        from code_agents.cli import main
        mock_result = MagicMock()
        mock_result.stdout = "abc fix: something"
        mock_result_status = MagicMock()
        mock_result_status.stdout = ""
        with patch.object(sys, "argv", ["code-agents", "standup"]), \
             patch("subprocess.run", return_value=mock_result), \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": "/tmp/fake"}), \
             patch("httpx.get", side_effect=Exception("no server")):
            main()
        output = capsys.readouterr().out
        assert "Standup" in output

    def test_dispatch_keyboard_interrupt(self, capsys):
        from code_agents.cli.cli_completions import main
        with patch.object(sys, "argv", ["code-agents", "version"]), \
             patch("code_agents.cli.cli_tools.cmd_version", side_effect=KeyboardInterrupt):
            main()
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_dispatch_eof_error(self, capsys):
        from code_agents.cli.cli_completions import main
        with patch.object(sys, "argv", ["code-agents", "version"]), \
             patch("code_agents.cli.cli_tools.cmd_version", side_effect=EOFError):
            main()
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_dispatch_no_args(self, capsys):
        from code_agents.cli.cli_completions import main
        with patch.object(sys, "argv", ["code-agents"]), \
             patch("code_agents.cli.cli.cmd_start") as mock_start:
            main()
        mock_start.assert_called_once()

    def test_dispatch_unknown_command(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "nonexistent"]), \
             pytest.raises(SystemExit):
            main()
        output = capsys.readouterr().out
        assert "Unknown command" in output

    def test_dispatch_version(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "version"]):
            main()
        output = capsys.readouterr().out
        assert "code-agents" in output

    def test_dispatch_version_flag(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "--version"]):
            main()
        output = capsys.readouterr().out
        assert "code-agents" in output

    def test_dispatch_help(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "help"]):
            main()
        output = capsys.readouterr().out
        assert "init" in output

    def test_dispatch_help_flag(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "--help"]):
            main()
        output = capsys.readouterr().out
        assert "init" in output

    def test_dispatch_branches(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "branches"]), \
             patch("code_agents.cli.cli_git.cmd_branches") as mock_cmd:
            main()
        mock_cmd.assert_called_once()

    def test_dispatch_diff(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "diff", "main", "HEAD"]), \
             patch("code_agents.cli.cli_git.cmd_diff") as mock_cmd:
            main()
        mock_cmd.assert_called_once_with(["main", "HEAD"])

    def test_dispatch_test(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "test", "feature"]), \
             patch("code_agents.cli.cli_cicd.cmd_test") as mock_cmd:
            main()
        mock_cmd.assert_called_once_with(["feature"])

    def test_dispatch_review(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "review"]):
            main()
        output = capsys.readouterr().out
        assert "Reviewing" in output or "review" in output.lower()

    def test_dispatch_pipeline(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "pipeline", "status"]), \
             patch("code_agents.cli.cli_cicd.cmd_pipeline") as mock_cmd:
            main()
        mock_cmd.assert_called_once_with(["status"])

    def test_dispatch_deadcode(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "deadcode"]), \
             patch("code_agents.cli.cli_analysis.cmd_deadcode") as mock_cmd:
            main()
        mock_cmd.assert_called_once_with([])

    def test_dispatch_oncall_report(self, capsys):
        from code_agents.cli.cli import main
        with patch.object(sys, "argv", ["code-agents", "oncall-report", "--days", "14"]), \
             patch("code_agents.cli.cli_reports.cmd_oncall_report") as mock_cmd:
            main()
        mock_cmd.assert_called_once_with(["--days", "14"])
class TestMainDispatcherDup2:
    """Test main() dispatches to the correct subcommand handler."""

    def test_no_args_calls_start(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli.cmd_start") as mock_start, \
             patch("sys.argv", ["code-agents"]):
            main()
            mock_start.assert_called_once()

    def test_help_flag(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_completions.cmd_help") as mock_help, \
             patch("sys.argv", ["code-agents", "help"]):
            main()
            mock_help.assert_called_once()

    def test_help_dash_h(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_completions.cmd_help") as mock_help, \
             patch("sys.argv", ["code-agents", "-h"]):
            main()
            mock_help.assert_called_once()

    def test_version_flag(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_version") as mock_ver, \
             patch("sys.argv", ["code-agents", "--version"]):
            main()
            mock_ver.assert_called_once()

    def test_status_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_server.cmd_status") as mock_status, \
             patch("sys.argv", ["code-agents", "status"]):
            main()
            mock_status.assert_called_once()

    def test_agents_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_server.cmd_agents") as mock_agents, \
             patch("sys.argv", ["code-agents", "agents"]):
            main()
            mock_agents.assert_called_once()

    def test_config_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_server.cmd_config") as mock_config, \
             patch("sys.argv", ["code-agents", "config"]):
            main()
            mock_config.assert_called_once()

    def test_shutdown_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_server.cmd_shutdown") as mock_shutdown, \
             patch("sys.argv", ["code-agents", "shutdown"]):
            main()
            mock_shutdown.assert_called_once()

    def test_branches_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_git.cmd_branches") as mock_branches, \
             patch("sys.argv", ["code-agents", "branches"]):
            main()
            mock_branches.assert_called_once()

    def test_doctor_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_doctor.cmd_doctor") as mock_doctor, \
             patch("sys.argv", ["code-agents", "doctor"]):
            main()
            mock_doctor.assert_called_once()

    def test_start_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_server.cmd_start") as mock_start, \
             patch("sys.argv", ["code-agents", "start"]):
            main()
            mock_start.assert_called_once()

    def test_restart_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_server.cmd_restart") as mock_restart, \
             patch("sys.argv", ["code-agents", "restart"]):
            main()
            mock_restart.assert_called_once()

    def test_update_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_update") as mock_update, \
             patch("sys.argv", ["code-agents", "update"]):
            main()
            mock_update.assert_called_once()

    def test_migrate_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_migrate") as mock_migrate, \
             patch("sys.argv", ["code-agents", "migrate"]):
            main()
            mock_migrate.assert_called_once()

    def test_standup_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_reports.cmd_standup") as mock_standup, \
             patch("sys.argv", ["code-agents", "standup"]):
            main()
            mock_standup.assert_called_once()

    def test_commit_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_git.cmd_commit") as mock_commit, \
             patch("sys.argv", ["code-agents", "commit"]):
            main()
            mock_commit.assert_called_once()

    def test_curls_command(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_curls.cmd_curls") as mock_curls, \
             patch("sys.argv", ["code-agents", "curls"]):
            main()
            mock_curls.assert_called_once()

    def test_unknown_command_exits(self, capsys):
        from code_agents.cli.cli import main
        with patch("sys.argv", ["code-agents", "nonexistent"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
        output = capsys.readouterr().out
        assert "Unknown command" in output

    def test_keyboard_interrupt(self, capsys):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_server.cmd_status", side_effect=KeyboardInterrupt), \
             patch("sys.argv", ["code-agents", "status"]):
            main()
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_eof_error(self, capsys):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_server.cmd_status", side_effect=EOFError), \
             patch("sys.argv", ["code-agents", "status"]):
            main()
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_diff_dispatches_with_rest(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_git.cmd_diff") as mock_diff, \
             patch("sys.argv", ["code-agents", "diff", "main", "develop"]):
            main()
            mock_diff.assert_called_once_with(["main", "develop"])

    def test_test_dispatches_with_rest(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_cicd.cmd_test") as mock_test, \
             patch("sys.argv", ["code-agents", "test", "feature-branch"]):
            main()
            mock_test.assert_called_once_with(["feature-branch"])

    def test_pipeline_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_cicd.cmd_pipeline") as mock_pipeline, \
             patch("sys.argv", ["code-agents", "pipeline", "start"]):
            main()
            mock_pipeline.assert_called_once_with(["start"])

    def test_review_dispatches(self):
        from code_agents.cli.cli import main
        with patch("sys.argv", ["code-agents", "review", "main"]):
            main()
        # cmd_review runs directly — verify via output (dispatched through registry)

    def test_logs_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_server.cmd_logs") as mock_logs, \
             patch("sys.argv", ["code-agents", "logs", "50"]):
            main()
            mock_logs.assert_called_once_with(["50"])

    def test_chat_dispatches(self):
        from code_agents.cli.cli import main
        # Default chat launches TS terminal via subprocess
        with patch("subprocess.run") as mock_run, \
             patch("sys.argv", ["code-agents", "chat", "code-writer"]):
            main()
            mock_run.assert_called()

    def test_chat_legacy_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.chat.chat.chat_main") as mock_chat, \
             patch("sys.argv", ["code-agents", "chat", "--legacy", "code-writer"]):
            main()
            mock_chat.assert_called_once_with(["code-writer"])

    def test_repos_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_repos") as mock_repos, \
             patch("sys.argv", ["code-agents", "repos", "add", "/tmp"]):
            main()
            mock_repos.assert_called_once_with(["add", "/tmp"])

    def test_sessions_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_sessions") as mock_sessions, \
             patch("sys.argv", ["code-agents", "sessions", "--all"]):
            main()
            mock_sessions.assert_called_once_with(["--all"])

    def test_deadcode_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_analysis.cmd_deadcode") as mock_dc, \
             patch("sys.argv", ["code-agents", "deadcode", "--json"]):
            main()
            mock_dc.assert_called_once_with(["--json"])

    def test_security_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_analysis.cmd_security") as mock_sec, \
             patch("sys.argv", ["code-agents", "security"]):
            main()
            mock_sec.assert_called_once_with([])

    def test_flags_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_analysis.cmd_flags") as mock_flags, \
             patch("sys.argv", ["code-agents", "flags", "--stale"]):
            main()
            mock_flags.assert_called_once_with(["--stale"])

    def test_complexity_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_analysis.cmd_complexity") as mock_cx, \
             patch("sys.argv", ["code-agents", "complexity"]):
            main()
            mock_cx.assert_called_once_with([])

    def test_techdebt_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_analysis.cmd_techdebt") as mock_td, \
             patch("sys.argv", ["code-agents", "techdebt"]):
            main()
            mock_td.assert_called_once_with([])

    def test_watchdog_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_watchdog") as mock_wd, \
             patch("sys.argv", ["code-agents", "watchdog"]):
            main()
            mock_wd.assert_called_once_with([])

    def test_auto_review_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_git.cmd_auto_review") as mock_ar, \
             patch("sys.argv", ["code-agents", "auto-review"]):
            main()
            mock_ar.assert_called_once_with([])

    def test_setup_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.setup.setup.main") as mock_setup, \
             patch("sys.argv", ["code-agents", "setup"]):
            main()
            mock_setup.assert_called_once()

    def test_completions_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_completions.cmd_completions") as mock_comp, \
             patch("sys.argv", ["code-agents", "completions", "--zsh"]):
            main()
            mock_comp.assert_called_once_with(["--zsh"])

    def test_release_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_cicd.cmd_release") as mock_rel, \
             patch("sys.argv", ["code-agents", "release", "v1.0.0"]):
            main()
            mock_rel.assert_called_once_with(["v1.0.0"])

    def test_incident_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_reports.cmd_incident") as mock_inc, \
             patch("sys.argv", ["code-agents", "incident", "my-service"]):
            main()
            mock_inc.assert_called_once_with(["my-service"])

    def test_sprint_velocity_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_reports.cmd_sprint_velocity") as mock_sv, \
             patch("sys.argv", ["code-agents", "sprint-velocity"]):
            main()
            mock_sv.assert_called_once_with([])

    def test_coverage_boost_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_cicd.cmd_coverage_boost") as mock_cb, \
             patch("sys.argv", ["code-agents", "coverage-boost", "--dry-run"]):
            main()
            mock_cb.assert_called_once_with(["--dry-run"])

    def test_qa_suite_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_cicd.cmd_qa_suite") as mock_qa, \
             patch("sys.argv", ["code-agents", "qa-suite"]):
            main()
            mock_qa.assert_called_once_with([])

    def test_pr_preview_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_git.cmd_pr_preview") as mock_pp, \
             patch("sys.argv", ["code-agents", "pr-preview"]):
            main()
            mock_pp.assert_called_once_with([])

    def test_sprint_report_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_reports.cmd_sprint_report") as mock_sr, \
             patch("sys.argv", ["code-agents", "sprint-report"]):
            main()
            mock_sr.assert_called_once_with([])

    def test_onboard_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_onboard") as mock_ob, \
             patch("sys.argv", ["code-agents", "onboard"]):
            main()
            mock_ob.assert_called_once_with([])

    def test_changelog_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_changelog") as mock_cl, \
             patch("sys.argv", ["code-agents", "changelog"]):
            main()
            mock_cl.assert_called_once_with([])

    def test_env_health_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_reports.cmd_env_health") as mock_eh, \
             patch("sys.argv", ["code-agents", "env-health"]):
            main()
            mock_eh.assert_called_once_with([])

    def test_morning_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_reports.cmd_morning") as mock_m, \
             patch("sys.argv", ["code-agents", "morning"]):
            main()
            mock_m.assert_called_once_with([])

    def test_pre_push_check_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_pre_push") as mock_pp, \
             patch("sys.argv", ["code-agents", "pre-push-check"]):
            main()
            mock_pp.assert_called_once_with([])

    def test_pre_push_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_pre_push") as mock_pp, \
             patch("sys.argv", ["code-agents", "pre-push", "install"]):
            main()
            mock_pp.assert_called_once_with(["install"])

    def test_config_diff_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_analysis.cmd_config_diff") as mock_cd, \
             patch("sys.argv", ["code-agents", "config-diff"]):
            main()
            mock_cd.assert_called_once_with([])

    def test_api_check_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_analysis.cmd_api_check") as mock_ac, \
             patch("sys.argv", ["code-agents", "api-check"]):
            main()
            mock_ac.assert_called_once_with([])

    def test_apidoc_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_analysis.cmd_apidoc") as mock_ad, \
             patch("sys.argv", ["code-agents", "apidoc"]):
            main()
            mock_ad.assert_called_once_with([])

    def test_audit_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_analysis.cmd_audit") as mock_au, \
             patch("sys.argv", ["code-agents", "audit"]):
            main()
            mock_au.assert_called_once_with([])

    def test_perf_baseline_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_reports.cmd_perf_baseline") as mock_pb, \
             patch("sys.argv", ["code-agents", "perf-baseline"]):
            main()
            mock_pb.assert_called_once_with([])

    def test_version_bump_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_version_bump") as mock_vb, \
             patch("sys.argv", ["code-agents", "version-bump", "patch"]):
            main()
            mock_vb.assert_called_once_with(["patch"])

    def test_rules_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli_tools.cmd_rules") as mock_r, \
             patch("sys.argv", ["code-agents", "rules", "list"]):
            main()
            mock_r.assert_called_once_with(["list"])

    def test_init_dispatches(self):
        from code_agents.cli.cli import main
        with patch("code_agents.cli.cli.cmd_init") as mock_init, \
             patch("sys.argv", ["code-agents", "init"]):
            main()
            mock_init.assert_called_once()
class TestResolveCLIHandler:
    """Test _resolve_cli_handler function."""

    def test_resolve_callable(self):
        from code_agents.cli.cli import _resolve_cli_handler
        from code_agents.cli.cli_tools import cmd_version
        resolved = _resolve_cli_handler(cmd_version)
        assert callable(resolved)

    def test_resolve_non_callable(self):
        from code_agents.cli.cli import _resolve_cli_handler
        result = _resolve_cli_handler(None)
        assert result is None

    def test_resolve_no_module(self):
        from code_agents.cli.cli import _resolve_cli_handler
        fn = lambda: None
        fn.__module__ = None
        result = _resolve_cli_handler(fn)
        assert result is fn

    def test_resolve_bad_module(self):
        from code_agents.cli.cli import _resolve_cli_handler
        fn = lambda: None
        fn.__module__ = "nonexistent.module.xyz"
        fn.__name__ = "fake_fn"
        result = _resolve_cli_handler(fn)
        assert result is fn
