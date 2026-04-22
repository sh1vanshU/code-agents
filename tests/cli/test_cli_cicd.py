"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdTest:
    """Test the test command."""

    def test_test_with_api_pass(self, capsys):
        from code_agents.cli.cli_cicd import cmd_test
        mock_data = {
            "passed": True,
            "total": 100,
            "passed_count": 98,
            "failed_count": 2,
            "error_count": 0,
            "test_command": "pytest",
        }
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.cli.cli_cicd._api_post", return_value=mock_data):
            cmd_test([])
        output = capsys.readouterr().out
        assert "PASSED" in output
        assert "100" in output

    def test_test_with_api_fail(self, capsys):
        from code_agents.cli.cli_cicd import cmd_test
        mock_data = {
            "passed": False,
            "total": 50,
            "passed_count": 45,
            "failed_count": 5,
            "error_count": 0,
            "test_command": "pytest",
            "output": "FAILED test_foo.py::test_bar\nAssertionError",
        }
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.cli.cli_cicd._api_post", return_value=mock_data):
            cmd_test([])
        output = capsys.readouterr().out
        assert "FAILED" in output

    def test_test_fallback(self, capsys):
        from code_agents.cli.cli_cicd import cmd_test
        mock_data = {
            "passed": True,
            "total": 10,
            "passed_count": 10,
            "failed_count": 0,
            "error_count": 0,
            "test_command": "pytest",
        }
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.cli.cli_cicd._api_post", return_value=None), \
             patch("asyncio.run", return_value=mock_data):
            cmd_test(["feature-branch"])
        output = capsys.readouterr().out
        assert "PASSED" in output
class TestCmdPipeline:
    """Test pipeline command."""

    def test_pipeline_start(self, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_data = {"run_id": "run-123", "current_step_name": "Build"}
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._api_get", return_value={"branch": "main"}), \
             patch("code_agents.cli.cli_cicd._api_post", return_value=mock_data):
            cmd_pipeline(["start"])
        output = capsys.readouterr().out
        assert "Pipeline started" in output
        assert "run-123" in output

    def test_pipeline_start_with_branch(self, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_data = {"run_id": "run-456", "current_step_name": "Test"}
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._api_post", return_value=mock_data):
            cmd_pipeline(["start", "feature-x"])
        output = capsys.readouterr().out
        assert "feature-x" in output

    def test_pipeline_status_with_id(self, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_data = {
            "run_id": "run-123",
            "branch": "main",
            "current_step": 2,
            "current_step_name": "Test",
            "steps": {},
        }
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._api_get", return_value=mock_data):
            cmd_pipeline(["status", "run-123"])
        output = capsys.readouterr().out
        assert "run-123" in output

    def test_pipeline_status_no_runs(self, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._api_get", return_value={"runs": []}):
            cmd_pipeline(["status"])
        output = capsys.readouterr().out
        assert "No pipeline runs" in output

    def test_pipeline_advance_no_id(self, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        with patch("code_agents.cli.cli_cicd._load_env"):
            cmd_pipeline(["advance"])
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_pipeline_advance(self, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_data = {"current_step": 3, "current_step_name": "Deploy"}
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._api_post", return_value=mock_data):
            cmd_pipeline(["advance", "run-123"])
        output = capsys.readouterr().out
        assert "Advanced" in output

    def test_pipeline_rollback_no_id(self, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        with patch("code_agents.cli.cli_cicd._load_env"):
            cmd_pipeline(["rollback"])
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_pipeline_rollback(self, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_data = {"rollback_info": {"instruction": "Rollback to v1.0"}}
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._api_post", return_value=mock_data):
            cmd_pipeline(["rollback", "run-123"])
        output = capsys.readouterr().out
        assert "Rollback triggered" in output

    def test_pipeline_unknown_subcommand(self, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        with patch("code_agents.cli.cli_cicd._load_env"):
            cmd_pipeline(["foobar"])
        output = capsys.readouterr().out
        assert "Unknown pipeline command" in output
class TestCmdRelease:
    """Test release command."""

    def test_release_no_args(self, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        with patch("code_agents.cli.cli_cicd._load_env"):
            cmd_release([])
        output = capsys.readouterr().out
        assert "Release Automation" in output
        assert "Usage" in output

    def test_release_flag_only(self, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        with patch("code_agents.cli.cli_cicd._load_env"):
            cmd_release(["--dry-run"])
        output = capsys.readouterr().out
        assert "Usage" in output
class TestCmdServerStatus:
    """Test server status command."""

    def test_status_server_not_running(self, capsys):
        from code_agents.cli.cli_server import cmd_status
        with patch("code_agents.cli.cli_server._load_env"), \
             patch("code_agents.cli.cli_server._api_get", return_value=None), \
             patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp/fake"):
            cmd_status()
        output = capsys.readouterr().out
        assert "not running" in output

    def test_status_server_running(self, capsys):
        from code_agents.cli.cli_server import cmd_status
        mock_health = {"status": "ok"}
        mock_diag = {
            "package_version": "0.2.0",
            "agents": ["a", "b", "c"],
            "jenkins_configured": True,
            "argocd_configured": False,
            "elasticsearch_configured": False,
            "pipeline_enabled": True,
        }
        with patch("code_agents.cli.cli_server._load_env"), \
             patch("code_agents.cli.cli_server._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_server._api_get") as mock_get:
            mock_get.side_effect = [mock_health, mock_diag]
            cmd_status()
        output = capsys.readouterr().out
        assert "running" in output
        assert "Jenkins" in output
class TestCmdAgents:
    """Test agents listing command."""

    def test_agents_from_api(self, capsys):
        from code_agents.cli.cli_server import cmd_agents
        mock_data = {
            "data": [
                {"name": "code-reasoning", "display_name": "Code Reasoning", "endpoint": "/v1/agents/code-reasoning/chat/completions"},
                {"name": "code-writer", "display_name": "Code Writer", "endpoint": "/v1/agents/code-writer/chat/completions"},
            ]
        }
        with patch("code_agents.cli.cli_server._load_env"), \
             patch("code_agents.cli.cli_server._api_get", return_value=mock_data):
            cmd_agents()
        output = capsys.readouterr().out
        assert "code-reasoning" in output
        assert "code-writer" in output
        assert "2" in output  # Total: 2 agents

    def test_agents_no_server(self, capsys):
        from code_agents.cli.cli_server import cmd_agents
        mock_agent = MagicMock()
        mock_agent.name = "code-reasoning"
        mock_agent.display_name = "Code Reasoning"
        mock_agent.backend = "cursor"
        mock_agent.model = "Composer 2 Fast"
        mock_agent.permission_mode = "suggest"
        with patch("code_agents.cli.cli_server._load_env"), \
             patch("code_agents.cli.cli_server._api_get", return_value=None), \
             patch("code_agents.core.config.agent_loader") as mock_loader:
            mock_loader.list_agents.return_value = [mock_agent]
            cmd_agents()
        output = capsys.readouterr().out
        assert "code-reasoning" in output
        assert "from YAML" in output
class TestPrintPipelineStatus:
    """Test _print_pipeline_status helper."""

    def test_print_pipeline_status(self, capsys):
        from code_agents.cli.cli_cicd import _print_pipeline_status
        data = {
            "run_id": "run-001",
            "branch": "main",
            "current_step": 3,
            "current_step_name": "Deploy",
            "build_number": 42,
            "error": None,
            "steps": {
                "1": {"status": "success", "name": "Build"},
                "2": {"status": "success", "name": "Test"},
                "3": {"status": "in_progress", "name": "Deploy"},
                "4": {"status": "pending", "name": "Sanity"},
                "5": {"status": "pending", "name": "Jira"},
                "6": {"status": "pending", "name": "Done"},
            },
        }
        _print_pipeline_status(data)
        output = capsys.readouterr().out
        assert "run-001" in output
        assert "main" in output
        assert "Build" in output
        assert "#42" in output
class TestCmdReleaseWithVersion:
    """Test release command with version arg."""

    def test_release_dry_run(self, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        mock_mgr = MagicMock()
        mock_mgr.version = "1.0.0"
        mock_mgr.branch_name = "release/1.0.0"
        mock_mgr.steps_completed = ["Create release branch", "Generate changelog"]
        mock_mgr.errors = []
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp"), \
             patch("code_agents.tools.release.ReleaseManager", return_value=mock_mgr):
            # All step_fns succeed
            mock_mgr.create_branch.return_value = True
            mock_mgr.generate_changelog.return_value = True
            mock_mgr.bump_version.return_value = True
            mock_mgr.commit_changes.return_value = True
            mock_mgr.push_branch.return_value = True
            cmd_release(["1.0.0", "--dry-run", "--skip-tests", "--skip-deploy", "--skip-jira"])
        output = capsys.readouterr().out
        assert "Release" in output
        assert "DRY RUN" in output

    def test_release_step_fails(self, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        mock_mgr = MagicMock()
        mock_mgr.version = "1.0.0"
        mock_mgr.branch_name = "release/1.0.0"
        mock_mgr.steps_completed = []
        mock_mgr.errors = []
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp"), \
             patch("code_agents.tools.release.ReleaseManager", return_value=mock_mgr), \
             patch("code_agents.cli.cli_cicd.prompt_yes_no", return_value=True):
            mock_mgr.create_branch.return_value = False
            cmd_release(["1.0.0", "--skip-tests", "--skip-deploy", "--skip-jira"])
        output = capsys.readouterr().out
        assert "failed" in output.lower()

    def test_release_cancelled(self, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        mock_mgr = MagicMock()
        mock_mgr.version = "1.0.0"
        mock_mgr.branch_name = "release/1.0.0"
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp"), \
             patch("code_agents.tools.release.ReleaseManager", return_value=mock_mgr), \
             patch("code_agents.cli.cli_cicd.prompt_yes_no", return_value=False):
            cmd_release(["1.0.0"])
        output = capsys.readouterr().out
        assert "Cancelled" in output
class TestCmdCoverageBoost:
    """Test coverage-boost command."""

    def test_coverage_boost_dry_run(self, capsys):
        from code_agents.cli.cli_cicd import cmd_coverage_boost
        mock_gap = MagicMock()
        mock_gap.risk = "critical"
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp"), \
             patch("code_agents.tools.auto_coverage.AutoCoverageBoost") as MockBoost, \
             patch("code_agents.tools.auto_coverage.format_coverage_report", return_value="Coverage Report"):
            inst = MockBoost.return_value
            inst.scan_existing_tests.return_value = {"files": 5, "methods": 20}
            inst.identify_gaps.return_value = [mock_gap]
            inst.prioritize_gaps.return_value = [mock_gap]
            inst.build_test_prompts.return_value = ["prompt1"]
            inst.report = MagicMock()
            inst.build_delegation_prompt.return_value = "delegate"
            cmd_coverage_boost(["--dry-run"])
        output = capsys.readouterr().out
        assert "Auto-Coverage Boost" in output

    def test_coverage_boost_already_meets_target(self, capsys):
        from code_agents.cli.cli_cicd import cmd_coverage_boost
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp"), \
             patch("code_agents.tools.auto_coverage.AutoCoverageBoost") as MockBoost, \
             patch("code_agents.tools.auto_coverage.format_coverage_report", return_value="Report"):
            inst = MockBoost.return_value
            inst.scan_existing_tests.return_value = {"files": 10, "methods": 50}
            inst.run_coverage_baseline.return_value = {"coverage": 95}
            cmd_coverage_boost(["--target", "90"])
        output = capsys.readouterr().out
        assert "meets target" in output.lower() or "95%" in output
class TestCmdQaSuite:
    """Test qa-suite command."""

    def test_qa_suite_no_language(self, capsys):
        from code_agents.cli.cli_cicd import cmd_qa_suite
        mock_analysis = MagicMock()
        mock_analysis.language = None
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp"), \
             patch("code_agents.generators.qa_suite_generator.QASuiteGenerator") as MockGen:
            MockGen.return_value.analyze.return_value = mock_analysis
            cmd_qa_suite([])
        output = capsys.readouterr().out
        assert "Could not detect" in output

    def test_qa_suite_analyze_only(self, capsys):
        from code_agents.cli.cli_cicd import cmd_qa_suite
        mock_analysis = MagicMock()
        mock_analysis.language = "python"
        mock_analysis.has_existing_tests = False
        mock_analysis.existing_test_count = 0
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp"), \
             patch("code_agents.generators.qa_suite_generator.QASuiteGenerator") as MockGen, \
             patch("code_agents.generators.qa_suite_generator.format_analysis", return_value="Analysis"):
            MockGen.return_value.analyze.return_value = mock_analysis
            cmd_qa_suite(["--analyze"])
        output = capsys.readouterr().out
        assert "Analyze-only" in output

    def test_qa_suite_write(self, capsys, tmp_path):
        from code_agents.cli.cli_cicd import cmd_qa_suite
        mock_analysis = MagicMock()
        mock_analysis.language = "python"
        mock_analysis.has_existing_tests = False
        mock_analysis.existing_test_count = 0
        generated = [{"path": "tests/test_new.py", "description": "Test file", "content": "# test"}]
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.generators.qa_suite_generator.QASuiteGenerator") as MockGen, \
             patch("code_agents.generators.qa_suite_generator.format_analysis", return_value="Analysis"):
            MockGen.return_value.analyze.return_value = mock_analysis
            MockGen.return_value.generate_suite.return_value = generated
            cmd_qa_suite(["--write"])
        output = capsys.readouterr().out
        assert "WROTE" in output or "files written" in output

    def test_qa_suite_no_generated(self, capsys):
        from code_agents.cli.cli_cicd import cmd_qa_suite
        mock_analysis = MagicMock()
        mock_analysis.language = "python"
        mock_analysis.has_existing_tests = False
        mock_analysis.existing_test_count = 0
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp"), \
             patch("code_agents.generators.qa_suite_generator.QASuiteGenerator") as MockGen, \
             patch("code_agents.generators.qa_suite_generator.format_analysis", return_value="Analysis"):
            MockGen.return_value.analyze.return_value = mock_analysis
            MockGen.return_value.generate_suite.return_value = []
            cmd_qa_suite([])
        output = capsys.readouterr().out
        assert "No test files generated" in output
class TestCmdTestFallbackError:
    """Test cmd_test fallback error."""

    def test_test_fallback_error(self, capsys):
        from code_agents.cli.cli_cicd import cmd_test
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_cicd._api_post", return_value=None), \
             patch("asyncio.run", side_effect=Exception("test error")):
            cmd_test([])
        output = capsys.readouterr().out
        assert "Error" in output
class TestCmdPipelineStatusRuns:
    """Test pipeline status with runs list."""

    def test_pipeline_status_with_runs(self, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_runs = {
            "runs": [
                {
                    "run_id": "run-1", "branch": "main",
                    "current_step": 2, "current_step_name": "Test",
                    "steps": {},
                },
            ]
        }
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._api_get", return_value=mock_runs):
            cmd_pipeline(["status"])
        output = capsys.readouterr().out
        assert "run-1" in output

    def test_pipeline_status_run_not_found(self, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        with patch("code_agents.cli.cli_cicd._load_env"), \
             patch("code_agents.cli.cli_cicd._api_get", return_value=None):
            cmd_pipeline(["status", "run-999"])
        output = capsys.readouterr().out
        assert "not found" in output
class TestPrintPipelineStatusError:
    """Test _print_pipeline_status with error."""

    def test_pipeline_status_with_error(self, capsys):
        from code_agents.cli.cli_cicd import _print_pipeline_status
        data = {
            "run_id": "run-err",
            "branch": "main",
            "current_step": 2,
            "current_step_name": "Deploy",
            "error": "Build failed",
            "steps": {},
        }
        _print_pipeline_status(data)
        output = capsys.readouterr().out
        assert "Build failed" in output
