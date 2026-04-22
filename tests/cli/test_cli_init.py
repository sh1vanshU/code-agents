"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdInit:
    """Test cmd_init function — the interactive setup wizard."""

    def test_init_section_flag_backend(self, capsys, tmp_path):
        """Test init with --backend flag only."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--backend"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.analysis.project_scanner.format_scan_report", return_value=""), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt_choice", return_value=4), \
             patch("code_agents.setup.setup.prompt", side_effect=["claude-sonnet-4-6"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Init Repository" in output

    def test_init_backend_cursor_overwrites_prior_claude_cli(self, capsys, tmp_path):
        """Choosing Cursor must set CODE_AGENTS_BACKEND=cursor so merge does not keep claude-cli."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        mock_write = MagicMock()
        existing = {"CODE_AGENTS_BACKEND": "claude-cli", "CURSOR_API_KEY": "old"}
        with patch("sys.argv", ["code-agents", "init", "--backend"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.analysis.project_scanner.format_scan_report", return_value=""), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value=existing), \
             patch("code_agents.setup.setup.prompt_choice", return_value=2), \
             patch("code_agents.setup.setup.prompt", side_effect=["sk-cursor-new", ""]), \
             patch("code_agents.setup.setup.write_env_file", mock_write), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        mock_write.assert_called_once()
        written = mock_write.call_args[0][0]
        unset = mock_write.call_args.kwargs.get("unset_keys", frozenset())
        assert written["CODE_AGENTS_BACKEND"] == "cursor"
        assert written["CURSOR_API_KEY"] == "sk-cursor-new"
        assert "CODE_AGENTS_CLAUDE_CLI_MODEL" in unset

    def test_init_section_flag_server(self, capsys, tmp_path):
        """Test init with --server flag only."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--server"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["0.0.0.0", "8000"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Server" in output

    def test_init_section_flag_jira(self, capsys, tmp_path):
        """Test init with --jira flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--jira"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["http://jira.example.com", "user@example.com", "token123", "PROJ"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Jira" in output

    def test_init_section_flag_kibana(self, capsys, tmp_path):
        """Test init with --kibana flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--kibana"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["http://kibana.example.com", "user", "pass"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Kibana" in output

    def test_init_section_flag_k8s(self, capsys, tmp_path):
        """Test init with --k8s flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--k8s"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["default", "", ""]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Kubernetes" in output

    def test_init_section_flag_notifications(self, capsys, tmp_path):
        """Test init with --notifications flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--notifications"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["https://hooks.slack.com/test"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Notifications" in output

    def test_init_section_flag_slack(self, capsys, tmp_path):
        """Test init with --slack flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--slack"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["xoxb-token", "signing-secret"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Slack" in output

    def test_init_section_flag_redash(self, capsys, tmp_path):
        """Test init with --redash flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--redash"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["http://redash.example.com", "", "user", "pass"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Redash" in output

    def test_init_section_flag_elastic(self, capsys, tmp_path):
        """Test init with --elastic flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--elastic"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["http://es.example.com:9200", ""]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Elasticsearch" in output

    def test_init_section_flag_atlassian(self, capsys, tmp_path):
        """Test init with --atlassian flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--atlassian"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["https://mysite.atlassian.net", "client-id", "client-secret"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Atlassian" in output

    def test_init_no_env_vars_saved(self, capsys, tmp_path):
        """Test init when all prompts return empty (no changes saved)."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--server"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["", ""]), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"):
            cmd_init()
        output = capsys.readouterr().out
        assert "No changes to save" in output

    def test_init_full_wizard_no_git(self, capsys, tmp_path):
        """Test init full wizard in non-git directory, cancelled."""
        from code_agents.cli.cli import cmd_init
        with patch("sys.argv", ["code-agents", "init"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.setup.setup.prompt_yes_no", return_value=False):
            cmd_init()
        output = capsys.readouterr().out
        assert "No .git found" in output or "Cancelled" in output

    def test_init_full_wizard_existing_config_cancel(self, capsys, tmp_path):
        """Test init full wizard with existing config, cancelled."""
        from code_agents.cli.cli import cmd_init
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        global_env = tmp_path / "config.env"
        global_env.write_text("CURSOR_API_KEY=test\n")
        with patch("sys.argv", ["code-agents", "init"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", global_env), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={"CURSOR_API_KEY": "test"}), \
             patch("code_agents.setup.setup.prompt_choice", return_value=3):
            cmd_init()
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_init_section_flag_build(self, capsys, tmp_path):
        """Test init with --build flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--build"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["mvn clean install"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Build" in output

    def test_init_section_flag_testing(self, capsys, tmp_path):
        """Test init with --testing flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        mock_qa = MagicMock()
        mock_qa.analysis.language = None
        with patch("sys.argv", ["code-agents", "init", "--testing"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["pytest", "80"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_qa), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Test Command" in output

    def test_init_section_flag_jenkins(self, capsys, tmp_path):
        """Test init with --jenkins flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--jenkins"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=[
                 "https://jenkins.example.com/", "user@example.com", "api-token",
                 "pg2/build-jobs/my-project",
                 "pg2/build-jobs/deploy/DEV-PIPELINE",
                 "pg2/build-jobs/deploy/QA-PIPELINE",
             ]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Jenkins" in output or "Init Repository" in output

    def test_init_section_flag_argocd(self, capsys, tmp_path):
        """Test init with --argocd flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--argocd"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=[
                 "https://argocd.example.com", "admin", "password",
             ]), \
             patch("code_agents.setup.setup.prompt_yes_no", return_value=True), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "ArgoCD" in output or "Init Repository" in output

    def test_init_section_flag_profile(self, capsys, tmp_path):
        """Test init with --profile flag."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--profile"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["Shivanshu"]), \
             patch("code_agents.agent_system.questionnaire.ask_question", return_value={"answer": "Senior Engineer"}), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "User Profile" in output

    def test_init_server_already_running(self, capsys, tmp_path):
        """Test init when server is already running."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("sys.argv", ["code-agents", "init", "--server"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["0.0.0.0", "8000"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", return_value=mock_resp), \
             patch("builtins.input", return_value="n"), \
             patch("code_agents.cli.cli.cmd_restart"):
            cmd_init()
        output = capsys.readouterr().out
        assert "already running" in output.lower()

    def test_init_backend_cursor(self, capsys, tmp_path):
        """Test init backend choice 2 (Cursor)."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--backend"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt_choice", return_value=2), \
             patch("code_agents.setup.setup.prompt", side_effect=["sk-cursor-key", ""]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Backend" in output or "Init Repository" in output

    def test_init_backend_claude_api(self, capsys, tmp_path):
        """Test init backend choice 3 (Claude API)."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--backend"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt_choice", return_value=3), \
             patch("code_agents.setup.setup.prompt", side_effect=["sk-ant-key"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Init Repository" in output
class TestCmdFlagsJsonStale:
    """Test flags --json --stale combination."""

    def test_flags_json_stale(self, capsys):
        from code_agents.cli.cli_analysis import cmd_flags
        from dataclasses import dataclass, field

        @dataclass
        class FakeReport:
            total_flags: int = 3
            flags: list = field(default_factory=lambda: [
                {"name": "F1", "stale": True},
                {"name": "F2", "stale": False},
            ])
            stale_flags: list = field(default_factory=list)
            env_matrix: dict = field(default_factory=dict)

        with patch("code_agents.analysis.feature_flags.FeatureFlagScanner") as MockScanner:
            MockScanner.return_value.scan.return_value = FakeReport()
            cmd_flags(["--json", "--stale"])
        output = capsys.readouterr().out
        # JSON output has prefix lines from the print statements; find the JSON part
        assert '"total_flags"' in output
        assert '"F1"' in output
        # F2 (not stale) should be filtered out
        assert '"F2"' not in output
class TestCOMMANDSDict:
    """Test the COMMANDS dictionary is well-formed."""

    def test_commands_dict_structure(self):
        from code_agents.cli.cli import COMMANDS
        assert isinstance(COMMANDS, dict)
        assert len(COMMANDS) > 30  # at least 30+ commands

    def test_all_commands_have_descriptions(self):
        from code_agents.cli.cli import COMMANDS
        for cmd_name, (desc, _func) in COMMANDS.items():
            assert isinstance(desc, str), f"{cmd_name} missing description"
            assert len(desc) > 5, f"{cmd_name} description too short"

    def test_key_commands_present(self):
        from code_agents.cli.cli import COMMANDS
        for cmd in ["init", "start", "chat", "status", "agents", "doctor", "config",
                     "diff", "branches", "test", "review", "pipeline", "curls"]:
            assert cmd in COMMANDS, f"Missing command: {cmd}"
class TestInitSections:
    """Test _INIT_SECTIONS mapping."""

    def test_init_sections_structure(self):
        from code_agents.cli.cli import _INIT_SECTIONS
        assert isinstance(_INIT_SECTIONS, dict)
        assert len(_INIT_SECTIONS) > 10

    def test_all_sections_have_descriptions(self):
        from code_agents.cli.cli import _INIT_SECTIONS
        for flag, desc in _INIT_SECTIONS.items():
            assert flag.startswith("--"), f"Flag should start with --: {flag}"
            assert isinstance(desc, str) and len(desc) > 3

    def test_key_sections_present(self):
        from code_agents.cli.cli import _INIT_SECTIONS
        for flag in ["--backend", "--server", "--jenkins", "--argocd", "--jira",
                      "--kibana", "--testing", "--k8s", "--slack"]:
            assert flag in _INIT_SECTIONS
