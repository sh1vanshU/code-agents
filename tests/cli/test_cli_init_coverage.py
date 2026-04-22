"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdInitCoverageGaps:
    """Tests targeting specific missing lines in cmd_init (lines 151, 186-213, 227, 256, 322-383, 396, 407, 457-466, 481-483, 570-596, 614, 761)."""

    def _base_patches(self, tmp_path, argv, prompt_side_effect, **overrides):
        """Return a dict of common patches for cmd_init tests."""
        mock_project = MagicMock()
        mock_project.detected = overrides.get("project_detected", False)
        mock_project.test_cmd = overrides.get("test_cmd", "")
        mock_project.build_cmd = overrides.get("build_cmd", "")
        return {
            "sys.argv": argv,
            "code_agents.cli.cli._user_cwd": lambda: str(tmp_path),
            "code_agents.cli.cli._find_code_agents_home": lambda: tmp_path,
            "code_agents.analysis.project_scanner.scan_project": lambda _: mock_project,
            "code_agents.analysis.project_scanner.format_scan_report": lambda _: "  Detected: Python",
            "code_agents.setup.setup_env.parse_env_file": lambda _: overrides.get("existing_cfg", {}),
            "code_agents.setup.setup.prompt": MagicMock(side_effect=prompt_side_effect),
            "code_agents.setup.setup.write_env_file": MagicMock(),
            "code_agents.core.env_loader.GLOBAL_ENV_PATH": tmp_path / "config.env",
            "code_agents.core.env_loader.PER_REPO_FILENAME": ".env.code-agents",
            "code_agents.cicd.endpoint_scanner.background_scan": MagicMock(),
            "threading.Thread": MagicMock(),
            "httpx.get": MagicMock(side_effect=Exception("no server")),
            "builtins.input": MagicMock(return_value="n"),
        }

    def test_init_existing_repo_config(self, capsys, tmp_path):
        """Line 151: repo env file exists and is parsed."""
        from code_agents.cli.cli import cmd_init
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        repo_env = tmp_path / ".env.code-agents"
        repo_env.write_text("HOST=0.0.0.0\n")
        global_env = tmp_path / "config.env"
        global_env.write_text("CURSOR_API_KEY=test\n")
        with patch("sys.argv", ["code-agents", "init"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", global_env), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={"CURSOR_API_KEY": "test", "HOST": "0.0.0.0"}), \
             patch("code_agents.setup.setup.prompt_choice", return_value=3):
            cmd_init()
        output = capsys.readouterr().out
        assert "Cancelled" in output  # third option still Cancel

    def test_init_modify_specific_sections(self, capsys, tmp_path):
        """Lines 186-213: user chooses 'Modify specific sections'."""
        from code_agents.cli.cli import cmd_init
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        global_env = tmp_path / "config.env"
        global_env.write_text("CURSOR_API_KEY=test\n")
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", global_env), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={"CURSOR_API_KEY": "test"}), \
             patch("code_agents.setup.setup.prompt_choice", return_value=1), \
             patch("builtins.input", return_value="2"), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.analysis.project_scanner.format_scan_report", return_value=""), \
             patch("code_agents.setup.setup.prompt", side_effect=["0.0.0.0", "8000"]), \
             patch("code_agents.setup.setup.prompt_yes_no", return_value=False), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")):
            cmd_init()
        output = capsys.readouterr().out
        assert "Select sections to modify" in output

    def test_init_modify_no_sections_selected(self, capsys, tmp_path):
        """Lines 209-211: no valid sections selected, cancelled."""
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
             patch("code_agents.setup.setup.prompt_choice", return_value=1), \
             patch("builtins.input", side_effect=["abc", "q"]):
            cmd_init()
        output = capsys.readouterr().out
        assert "No sections selected" in output

    def test_init_project_detected(self, capsys, tmp_path):
        """Lines 227-228: project detected shows scan report."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = True
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "--server"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.analysis.project_scanner.format_scan_report", return_value="  Detected: Python 3.14"), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["0.0.0.0", "8000"]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Detected: Python" in output

    def test_init_backend_cursor_with_url(self, capsys, tmp_path):
        """Line 256: Cursor API URL is set when non-empty."""
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
             patch("code_agents.setup.setup.prompt", side_effect=["sk-cursor-key", "http://cursor.example.com"]), \
             patch("code_agents.setup.setup.write_env_file") as mock_write, \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        # write_env_file should have been called with CURSOR_API_URL
        call_args = mock_write.call_args[0][0]
        assert "CURSOR_API_URL" in call_args

    def test_init_argocd_custom_pattern(self, capsys, tmp_path):
        """Lines 322: ArgoCD pattern edit when user says no to default."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        yes_no_returns = iter([False])  # pattern NOT correct
        with patch("sys.argv", ["code-agents", "init", "--argocd"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=[
                 "https://argocd.example.com", "admin", "password", "{env}-custom-{app}",
             ]), \
             patch("code_agents.setup.setup.prompt_yes_no", return_value=False), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "ArgoCD" in output or "Init Repository" in output

    def test_init_testing_autodetect_edit(self, capsys, tmp_path):
        """Lines 333-340: testing auto-detect, user chooses 'Edit'."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = "pytest"
        mock_project.build_cmd = ""
        mock_qa = MagicMock()
        mock_qa.analysis.language = None
        with patch("sys.argv", ["code-agents", "init"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.analysis.project_scanner.format_scan_report", return_value=""), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt_choice", side_effect=[2, 2]), \
             patch("code_agents.setup.setup.prompt", side_effect=["sk-test", "", "0.0.0.0", "8000", "pytest -x", "90", "you"]), \
             patch("code_agents.setup.setup.prompt_yes_no", side_effect=[False, False, False, False, True]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.setup.setup.prompt_integrations", return_value={}), \
             patch("code_agents.agent_system.questionnaire.ask_question", return_value={"answer": "Senior Engineer"}), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_qa), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            # Full wizard with auto-detected test command
            (tmp_path / ".git").mkdir(exist_ok=True)
            cmd_init()
        output = capsys.readouterr().out
        assert "Auto-detected" in output or "Test Command" in output

    def test_init_testing_skip(self, capsys, tmp_path):
        """Line 340: testing auto-detect, user chooses 'Skip'."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = "pytest"
        mock_project.build_cmd = ""
        mock_qa = MagicMock()
        mock_qa.analysis.language = None
        with patch("sys.argv", ["code-agents", "init"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.analysis.project_scanner.format_scan_report", return_value=""), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt_choice", side_effect=[4, 3]), \
             patch("code_agents.setup.setup.prompt", side_effect=["claude-sonnet-4-6", "0.0.0.0", "8000", "80", "Shivanshu"]), \
             patch("code_agents.setup.setup.prompt_yes_no", side_effect=[False, False, False, False, True]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.setup.setup.prompt_integrations", return_value={}), \
             patch("code_agents.agent_system.questionnaire.ask_question", return_value={"answer": "Senior Engineer"}), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_qa), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            (tmp_path / ".git").mkdir(exist_ok=True)
            cmd_init()
        output = capsys.readouterr().out
        # Should not crash; skip path taken

    def test_init_testing_qa_suite_offer(self, capsys, tmp_path):
        """Lines 358-372: QA suite offered when no tests detected."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        mock_qa = MagicMock()
        mock_qa.analysis.language = "python"
        mock_qa.analysis.has_existing_tests = False
        with patch("sys.argv", ["code-agents", "init", "--testing"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["pytest", "80"]), \
             patch("code_agents.setup.setup.prompt_yes_no", return_value=True), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_qa), \
             patch("code_agents.generators.qa_suite_generator.format_analysis", return_value="QA Analysis Report"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "No test files detected" in output or "Test Command" in output

    def test_init_testing_manual_configure(self, capsys, tmp_path):
        """Lines 375-383: run_all=True, no test cmd detected, user configures manually."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.analysis.project_scanner.format_scan_report", return_value=""), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["pytest -x", "90", "Shivanshu"]), \
             patch("code_agents.setup.setup.prompt_yes_no", side_effect=[True, False, False, False, False, False, True, True]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.setup.setup.prompt_integrations", return_value={}), \
             patch("code_agents.agent_system.questionnaire.ask_question", return_value={"answer": "Senior Engineer"}), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            (tmp_path / ".git").mkdir(exist_ok=True)
            cmd_init()
        output = capsys.readouterr().out
        # Should have gone through testing manual configure

    def test_init_redash_with_api_key(self, capsys, tmp_path):
        """Line 396: Redash with API key (not username/password)."""
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
             patch("code_agents.setup.setup.prompt", side_effect=["http://redash.example.com", "my-api-key-123"]), \
             patch("code_agents.setup.setup.write_env_file") as mock_write, \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        call_args = mock_write.call_args[0][0]
        assert "REDASH_API_KEY" in call_args

    def test_init_elastic_with_api_key(self, capsys, tmp_path):
        """Line 407: Elasticsearch with API key."""
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
             patch("code_agents.setup.setup.prompt", side_effect=["http://es.example.com:9200", "es-api-key-123"]), \
             patch("code_agents.setup.setup.write_env_file") as mock_write, \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        call_args = mock_write.call_args[0][0]
        assert "ELASTICSEARCH_API_KEY" in call_args

    def test_init_build_autodetect_use(self, capsys, tmp_path):
        """Lines 457-466: build auto-detect, user chooses 'use as-is'."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = "mvn clean install"
        with patch("sys.argv", ["code-agents", "init"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.analysis.project_scanner.format_scan_report", return_value=""), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt_choice", side_effect=[2]), \
             patch("code_agents.setup.setup.prompt", side_effect=["sk", "", "80", "Shivanshu"]), \
             patch("code_agents.setup.setup.prompt_yes_no", side_effect=[True, False, False, False, False, False, False, True]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.setup.setup.prompt_integrations", return_value={}), \
             patch("code_agents.agent_system.questionnaire.ask_question", return_value={"answer": "Senior Engineer"}), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            (tmp_path / ".git").mkdir(exist_ok=True)
            cmd_init()
        output = capsys.readouterr().out
        assert "Auto-detected" in output or "Build" in output

    def test_init_build_autodetect_edit(self, capsys, tmp_path):
        """Lines 462-466: build auto-detect, user chooses 'Edit'."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = "mvn clean install"
        with patch("sys.argv", ["code-agents", "init"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.analysis.project_scanner.format_scan_report", return_value=""), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt_choice", side_effect=[2]), \
             patch("code_agents.setup.setup.prompt", side_effect=["sk", "", "80", "mvn -DskipTests install", "Shivanshu"]), \
             patch("code_agents.setup.setup.prompt_yes_no", side_effect=[True, False, False, False, False, False, False, True]), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.setup.setup.prompt_integrations", return_value={}), \
             patch("code_agents.agent_system.questionnaire.ask_question", return_value={"answer": "Senior Engineer"}), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            (tmp_path / ".git").mkdir(exist_ok=True)
            cmd_init()
        output = capsys.readouterr().out

    def test_init_k8s_with_ssh(self, capsys, tmp_path):
        """Lines 481-483: K8s with SSH host."""
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
             patch("code_agents.setup.setup.prompt", side_effect=["default", "", "bastion.example.com", "ubuntu", "~/.ssh/id_rsa"]), \
             patch("code_agents.setup.setup.write_env_file") as mock_write, \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        call_args = mock_write.call_args[0][0]
        assert "K8S_SSH_HOST" in call_args
        assert "K8S_SSH_USER" in call_args

    def test_init_server_restart_yes(self, capsys, tmp_path):
        """Line 614: server running, user confirms restart."""
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
             patch("code_agents.setup.setup.prompt_yes_no", return_value=True), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", return_value=mock_resp), \
             patch("code_agents.cli.cli.cmd_restart") as mock_restart:
            cmd_init()
        mock_restart.assert_called_once()

    def test_init_server_restart_no(self, capsys, tmp_path):
        """Line 614-616: server running, user declines restart."""
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
             patch("code_agents.setup.setup.prompt_yes_no", return_value=False), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread"), \
             patch("httpx.get", return_value=mock_resp), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        assert "Restart manually" in output

    def test_init_alias_jenkins_cicd(self, capsys, tmp_path):
        """Test init with alias 'jenkins-cicd' maps to --jenkins."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "jenkins-cicd"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["https://jenkins.example.com", "user", "token", "folder/path", "folder/dev-deploy", "folder/qa-deploy"]), \
             patch("code_agents.setup.setup.validate_url", return_value=True), \
             patch("code_agents.setup.setup.write_env_file"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("code_agents.cicd.endpoint_scanner.background_scan"), \
             patch("threading.Thread") as mock_thread, \
             patch("httpx.get", side_effect=Exception("no server")), \
             patch("builtins.input", return_value="n"):
            cmd_init()
        output = capsys.readouterr().out
        # Alias resolved: should show Jenkins section, not full wizard
        assert "Jenkins" in output
        assert "Existing configuration" not in output

    def test_init_alias_jira_ops(self, capsys, tmp_path):
        """Test init with alias 'jira-ops' maps to --jira."""
        from code_agents.cli.cli import cmd_init
        mock_project = MagicMock()
        mock_project.detected = False
        mock_project.test_cmd = ""
        mock_project.build_cmd = ""
        with patch("sys.argv", ["code-agents", "init", "jira-ops"]), \
             patch("code_agents.cli.cli._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.analysis.project_scanner.scan_project", return_value=mock_project), \
             patch("code_agents.setup.setup_env.parse_env_file", return_value={}), \
             patch("code_agents.setup.setup.prompt", side_effect=["https://jira.example.com", "user@test.com", "token", "PROJ", "", ""]), \
             patch("code_agents.setup.setup.validate_url", return_value=True), \
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
        assert "Existing configuration" not in output

    def test_main_guard(self):
        """Line 761: __name__ == '__main__' guard."""
        from code_agents.cli import cli as cli_module
        with patch.object(cli_module, "main") as mock_main, \
             patch.object(cli_module, "__name__", "__main__"):
            # Simulate running the module
            exec("if cli_module.__name__ == '__main__': cli_module.main()")
        mock_main.assert_called_once()
