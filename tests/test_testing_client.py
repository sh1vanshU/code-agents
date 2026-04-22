"""Tests for testing_client.py — test runner and coverage analysis."""

from __future__ import annotations

import asyncio
import os

import pytest

from code_agents.cicd.testing_client import TestingClient, TestingError


@pytest.fixture
def python_repo(tmp_path):
    """Create a minimal Python project with pytest and a test."""
    repo = str(tmp_path / "pyrepo")
    os.makedirs(repo)

    # pyproject.toml to mark as pytest project
    with open(os.path.join(repo, "pyproject.toml"), "w") as f:
        f.write("[tool.pytest.ini_options]\n")

    # A simple module
    with open(os.path.join(repo, "mylib.py"), "w") as f:
        f.write("def add(a, b):\n    return a + b\n\ndef unused():\n    return 42\n")

    # A test
    with open(os.path.join(repo, "test_mylib.py"), "w") as f:
        f.write("from mylib import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")

    return repo


class TestTestingClient:
    def test_detect_python(self, python_repo):
        client = TestingClient(python_repo)
        cmd = client._detect_test_command()
        assert "pytest" in cmd

    def test_detect_node(self, tmp_path):
        repo = str(tmp_path / "noderepo")
        os.makedirs(repo)
        with open(os.path.join(repo, "package.json"), "w") as f:
            f.write("{}")
        client = TestingClient(repo)
        cmd = client._detect_test_command()
        assert "npm test" in cmd

    def test_detect_go(self, tmp_path):
        repo = str(tmp_path / "gorepo")
        os.makedirs(repo)
        with open(os.path.join(repo, "go.mod"), "w") as f:
            f.write("module example.com/test\n")
        client = TestingClient(repo)
        cmd = client._detect_test_command()
        assert "go test" in cmd

    def test_detect_maven(self, tmp_path):
        repo = str(tmp_path / "mvnrepo")
        os.makedirs(repo)
        with open(os.path.join(repo, "pom.xml"), "w") as f:
            f.write("<project></project>")
        client = TestingClient(repo)
        cmd = client._detect_test_command()
        assert "mvn test" in cmd

    def test_detect_gradle(self, tmp_path):
        repo = str(tmp_path / "gradlerepo")
        os.makedirs(repo)
        with open(os.path.join(repo, "build.gradle"), "w") as f:
            f.write("")
        client = TestingClient(repo)
        cmd = client._detect_test_command()
        assert cmd == "./gradlew test"

    def test_custom_command_override(self, python_repo):
        client = TestingClient(python_repo, test_command="echo hello")
        cmd = client._detect_test_command()
        assert cmd == "echo hello"

    def test_run_tests_simple(self, python_repo):
        """Run a real pytest invocation on the temp repo."""
        client = TestingClient(python_repo)
        result = asyncio.run(
            client.run_tests(test_command="python -m pytest test_mylib.py -q --tb=short")
        )
        assert result["passed"] is True
        assert result["return_code"] == 0

    def test_run_tests_failure(self, python_repo):
        """Test that failing tests are correctly detected."""
        with open(os.path.join(python_repo, "test_fail.py"), "w") as f:
            f.write("def test_fail():\n    assert False\n")
        client = TestingClient(python_repo)
        result = asyncio.run(
            client.run_tests(test_command="python -m pytest test_fail.py -q --tb=short")
        )
        assert result["passed"] is False
        assert result["return_code"] != 0

    def test_get_coverage_no_file(self, python_repo):
        """Should raise when no coverage.xml exists."""
        client = TestingClient(python_repo)
        with pytest.raises(TestingError, match="No coverage.xml"):
            asyncio.run(client.get_coverage())

    def test_get_coverage_with_xml(self, python_repo):
        """Test coverage XML parsing with a minimal coverage file."""
        coverage_xml = """<?xml version="1.0" ?>
<coverage version="7.0" timestamp="1234" lines-valid="4" lines-covered="3" line-rate="0.75" branches-covered="0" branches-valid="0" branch-rate="0" complexity="0">
    <packages>
        <package name="." line-rate="0.75" branch-rate="0" complexity="0">
            <classes>
                <class name="mylib.py" filename="mylib.py" line-rate="0.75" branch-rate="0" complexity="0">
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="1"/>
                        <line number="4" hits="0"/>
                        <line number="5" hits="1"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>"""
        with open(os.path.join(python_repo, "coverage.xml"), "w") as f:
            f.write(coverage_xml)

        client = TestingClient(python_repo, coverage_threshold=80.0)
        result = asyncio.run(client.get_coverage())
        assert result["total_coverage"] == 75.0
        assert result["meets_threshold"] is False
        assert len(result["file_coverage"]) == 1
        assert result["file_coverage"][0]["file"] == "mylib.py"
        assert "mylib.py" in result["uncovered_lines"]
        assert 4 in result["uncovered_lines"]["mylib.py"]


class TestPipelineState:
    """Test the pipeline state manager."""

    def test_create_and_get_run(self):
        from code_agents.cicd.pipeline_state import PipelineStateManager, StepStatus

        mgr = PipelineStateManager()
        run = mgr.create_run(branch="feature", repo_path="/tmp/repo")
        assert run.branch == "feature"
        assert run.current_step == 1
        assert all(s == StepStatus.PENDING for s in run.step_status.values())

        fetched = mgr.get_run(run.run_id)
        assert fetched is not None
        assert fetched.run_id == run.run_id

    def test_advance(self):
        from code_agents.cicd.pipeline_state import PipelineStateManager, StepStatus

        mgr = PipelineStateManager()
        run = mgr.create_run(branch="feature", repo_path="/tmp/repo")
        mgr.start_step(run.run_id)
        assert run.step_status[1] == StepStatus.IN_PROGRESS

        mgr.advance(run.run_id)
        assert run.step_status[1] == StepStatus.SUCCESS
        assert run.current_step == 2
        assert run.step_status[2] == StepStatus.IN_PROGRESS

    def test_fail_step(self):
        from code_agents.cicd.pipeline_state import PipelineStateManager, StepStatus

        mgr = PipelineStateManager()
        run = mgr.create_run(branch="feature", repo_path="/tmp/repo")
        mgr.start_step(run.run_id)
        mgr.fail_step(run.run_id, "build broke")
        assert run.step_status[1] == StepStatus.FAILED
        assert run.error == "build broke"

    def test_trigger_rollback(self):
        from code_agents.cicd.pipeline_state import PipelineStateManager, StepStatus

        mgr = PipelineStateManager()
        run = mgr.create_run(branch="feature", repo_path="/tmp/repo")
        # Advance to step 4
        for _ in range(3):
            mgr.start_step(run.run_id)
            mgr.advance(run.run_id)
        assert run.current_step == 4

        mgr.trigger_rollback(run.run_id)
        assert run.current_step == 7
        assert run.step_status[6] == StepStatus.SKIPPED
        assert run.step_status[7] == StepStatus.IN_PROGRESS

    def test_to_dict(self):
        from code_agents.cicd.pipeline_state import PipelineStateManager

        mgr = PipelineStateManager()
        run = mgr.create_run(
            branch="feature",
            repo_path="/tmp/repo",
            build_job="my-build",
            argocd_app="my-app",
        )
        d = run.to_dict()
        assert d["branch"] == "feature"
        assert d["build_job"] == "my-build"
        assert d["argocd_app"] == "my-app"
        assert d["current_step_name"] == "connect"
        assert len(d["steps"]) == 7

    def test_list_runs(self):
        from code_agents.cicd.pipeline_state import PipelineStateManager

        mgr = PipelineStateManager()
        mgr.create_run(branch="a", repo_path="/tmp/a")
        mgr.create_run(branch="b", repo_path="/tmp/b")
        assert len(mgr.list_runs()) == 2

    def test_get_nonexistent(self):
        from code_agents.cicd.pipeline_state import PipelineStateManager

        mgr = PipelineStateManager()
        assert mgr.get_run("nonexistent") is None

    def test_advance_nonexistent_raises(self):
        from code_agents.cicd.pipeline_state import PipelineStateManager

        mgr = PipelineStateManager()
        with pytest.raises(KeyError):
            mgr.advance("nonexistent")
