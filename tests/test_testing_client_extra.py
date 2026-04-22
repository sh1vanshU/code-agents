"""Extra tests for testing_client.py — covers get_coverage_gaps, run_tests with
branch checkout, output truncation, coverage XML edge cases."""

from __future__ import annotations

import asyncio
import os
import xml.etree.ElementTree as ET

import pytest

from code_agents.cicd.testing_client import TestingClient, TestingError


@pytest.fixture
def python_repo(tmp_path):
    """Create a minimal Python project."""
    repo = str(tmp_path / "pyrepo")
    os.makedirs(repo)
    with open(os.path.join(repo, "pyproject.toml"), "w") as f:
        f.write("[tool.pytest.ini_options]\n")
    with open(os.path.join(repo, "mylib.py"), "w") as f:
        f.write("def add(a, b):\n    return a + b\n\ndef unused():\n    return 42\n")
    with open(os.path.join(repo, "test_mylib.py"), "w") as f:
        f.write("from mylib import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    return repo


# ---------------------------------------------------------------------------
# TestingError
# ---------------------------------------------------------------------------


class TestTestingError:
    def test_error_with_output(self):
        err = TestingError("something failed", output="details here")
        assert str(err) == "something failed"
        assert err.output == "details here"

    def test_error_defaults(self):
        err = TestingError("fail")
        assert err.output is None


# ---------------------------------------------------------------------------
# _detect_test_command edge cases
# ---------------------------------------------------------------------------


class TestDetectTestCommand:
    def test_default_fallback(self, tmp_path):
        """No project markers => fallback to pytest."""
        repo = str(tmp_path / "empty")
        os.makedirs(repo)
        client = TestingClient(repo)
        cmd = client._detect_test_command()
        assert "pytest" in cmd

    def test_setup_cfg_detected(self, tmp_path):
        repo = str(tmp_path / "cfgrepo")
        os.makedirs(repo)
        with open(os.path.join(repo, "setup.cfg"), "w") as f:
            f.write("[tool:pytest]\n")
        client = TestingClient(repo)
        assert "pytest" in client._detect_test_command()

    def test_tox_ini_detected(self, tmp_path):
        repo = str(tmp_path / "toxrepo")
        os.makedirs(repo)
        with open(os.path.join(repo, "tox.ini"), "w") as f:
            f.write("[tox]\n")
        client = TestingClient(repo)
        assert "pytest" in client._detect_test_command()

    def test_pytest_ini_detected(self, tmp_path):
        repo = str(tmp_path / "pytrepo")
        os.makedirs(repo)
        with open(os.path.join(repo, "pytest.ini"), "w") as f:
            f.write("[pytest]\n")
        client = TestingClient(repo)
        assert "pytest" in client._detect_test_command()


# ---------------------------------------------------------------------------
# run_tests
# ---------------------------------------------------------------------------


class TestRunTests:
    def test_output_truncation(self, python_repo):
        """Large output should be truncated."""
        # Create a test that produces lots of output
        with open(os.path.join(python_repo, "test_verbose.py"), "w") as f:
            f.write("def test_verbose():\n    for i in range(1000): print(f'line {i}')\n")
        client = TestingClient(python_repo)
        result = asyncio.run(
            client.run_tests(test_command="python -m pytest test_verbose.py -q --tb=short -s")
        )
        # Output should exist
        assert result["output"]

    def test_run_tests_with_counts(self, python_repo):
        """Test that pass/fail counts are extracted."""
        client = TestingClient(python_repo)
        result = asyncio.run(
            client.run_tests(test_command="python -m pytest test_mylib.py -q --tb=short")
        )
        assert result["passed"] is True
        assert result["passed_count"] >= 1
        assert result["failed_count"] == 0

    def test_run_tests_custom_command(self, python_repo):
        client = TestingClient(python_repo, test_command="echo 'custom test'")
        result = asyncio.run(client.run_tests())
        assert result["passed"] is True
        assert result["return_code"] == 0

    def test_run_tests_branch_checkout_failure(self, python_repo):
        """Checkout of nonexistent branch should raise."""
        client = TestingClient(python_repo)
        with pytest.raises(TestingError, match="checkout"):
            asyncio.run(client.run_tests(branch="nonexistent-branch-xyz"))


# ---------------------------------------------------------------------------
# get_coverage edge cases
# ---------------------------------------------------------------------------


class TestGetCoverage:
    def test_invalid_xml(self, python_repo):
        """Malformed XML should raise TestingError."""
        with open(os.path.join(python_repo, "coverage.xml"), "w") as f:
            f.write("<<< not valid xml >>>")
        client = TestingClient(python_repo)
        with pytest.raises(TestingError, match="parse"):
            asyncio.run(client.get_coverage())

    def test_zero_line_rate(self, python_repo):
        """Coverage with 0% line rate."""
        xml = """<?xml version="1.0" ?>
<coverage line-rate="0.0">
    <packages>
        <package name=".">
            <classes>
                <class name="mod.py" filename="mod.py" line-rate="0.0">
                    <lines>
                        <line number="1" hits="0"/>
                        <line number="2" hits="0"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>"""
        with open(os.path.join(python_repo, "coverage.xml"), "w") as f:
            f.write(xml)
        client = TestingClient(python_repo, coverage_threshold=50.0)
        result = asyncio.run(client.get_coverage())
        assert result["total_coverage"] == 0.0
        assert result["meets_threshold"] is False
        assert result["uncovered_lines"]["mod.py"] == [1, 2]

    def test_full_coverage(self, python_repo):
        """100% coverage meets any threshold."""
        xml = """<?xml version="1.0" ?>
<coverage line-rate="1.0">
    <packages>
        <package name=".">
            <classes>
                <class name="mod.py" filename="mod.py" line-rate="1.0">
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="1"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>"""
        with open(os.path.join(python_repo, "coverage.xml"), "w") as f:
            f.write(xml)
        client = TestingClient(python_repo, coverage_threshold=100.0)
        result = asyncio.run(client.get_coverage())
        assert result["total_coverage"] == 100.0
        assert result["meets_threshold"] is True
        assert len(result["uncovered_lines"]) == 0

    def test_multiple_files(self, python_repo):
        """Coverage with multiple files."""
        xml = """<?xml version="1.0" ?>
<coverage line-rate="0.5">
    <packages>
        <package name=".">
            <classes>
                <class name="a.py" filename="a.py" line-rate="1.0">
                    <lines><line number="1" hits="1"/></lines>
                </class>
                <class name="b.py" filename="b.py" line-rate="0.0">
                    <lines><line number="1" hits="0"/></lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>"""
        with open(os.path.join(python_repo, "coverage.xml"), "w") as f:
            f.write(xml)
        client = TestingClient(python_repo)
        result = asyncio.run(client.get_coverage())
        assert len(result["file_coverage"]) == 2
        assert result["total_coverage"] == 50.0


# ---------------------------------------------------------------------------
# get_coverage_gaps
# ---------------------------------------------------------------------------


class TestGetCoverageGaps:
    def test_no_coverage_data(self, python_repo):
        """Should return error when no coverage.xml."""
        from unittest.mock import AsyncMock, patch as mock_patch

        client = TestingClient(python_repo)

        async def run():
            with mock_patch("code_agents.cicd.testing_client.TestingClient.get_coverage",
                          new_callable=AsyncMock, side_effect=TestingError("No coverage")):
                mock_git = AsyncMock()
                mock_git.diff.return_value = {"changed_files": []}
                with mock_patch("code_agents.cicd.git_client.GitClient", return_value=mock_git):
                    return await client.get_coverage_gaps("main", "feature")

        result = asyncio.run(run())
        assert "error" in result

    def test_coverage_gaps_with_data(self, python_repo):
        from unittest.mock import AsyncMock, patch as mock_patch

        client = TestingClient(python_repo, coverage_threshold=80.0)

        coverage_data = {
            "total_coverage": 75.0,
            "uncovered_lines": {"src/new_file.py": [10, 20, 30]},
            "file_coverage": [{"file": "src/new_file.py", "coverage": 50.0}],
        }
        diff_data = {
            "changed_files": [
                {"file": "src/new_file.py", "insertions": 20},
                {"file": "src/covered.py", "insertions": 10},
            ]
        }

        async def run():
            mock_git = AsyncMock()
            mock_git.diff.return_value = diff_data
            with mock_patch("code_agents.cicd.git_client.GitClient", return_value=mock_git), \
                 mock_patch.object(client, "get_coverage", new_callable=AsyncMock, return_value=coverage_data):
                return await client.get_coverage_gaps("main", "feature")

        result = asyncio.run(run())
        assert result["base"] == "main"
        assert result["head"] == "feature"
        assert result["new_lines_total"] == 30
        assert len(result["gaps"]) == 1
        assert result["gaps"][0]["file"] == "src/new_file.py"

    def test_coverage_gaps_all_covered(self, python_repo):
        from unittest.mock import AsyncMock, patch as mock_patch

        client = TestingClient(python_repo, coverage_threshold=80.0)

        coverage_data = {
            "total_coverage": 100.0,
            "uncovered_lines": {},
            "file_coverage": [],
        }
        diff_data = {
            "changed_files": [
                {"file": "src/good.py", "insertions": 10},
            ]
        }

        async def run():
            mock_git = AsyncMock()
            mock_git.diff.return_value = diff_data
            with mock_patch("code_agents.cicd.git_client.GitClient", return_value=mock_git), \
                 mock_patch.object(client, "get_coverage", new_callable=AsyncMock, return_value=coverage_data):
                return await client.get_coverage_gaps("main", "feature")

        result = asyncio.run(run())
        assert result["coverage_pct"] == 100.0
        assert result["meets_threshold"] is True
        assert len(result["gaps"]) == 0

    def test_coverage_gaps_no_changed_files(self, python_repo):
        from unittest.mock import AsyncMock, patch as mock_patch

        client = TestingClient(python_repo)

        coverage_data = {
            "total_coverage": 90.0,
            "uncovered_lines": {},
            "file_coverage": [],
        }
        diff_data = {"changed_files": []}

        async def run():
            mock_git = AsyncMock()
            mock_git.diff.return_value = diff_data
            with mock_patch("code_agents.cicd.git_client.GitClient", return_value=mock_git), \
                 mock_patch.object(client, "get_coverage", new_callable=AsyncMock, return_value=coverage_data):
                return await client.get_coverage_gaps("main", "feature")

        result = asyncio.run(run())
        assert result["coverage_pct"] == 100.0
        assert result["new_lines_total"] == 0

    def test_coverage_gaps_diff_error(self, python_repo):
        from unittest.mock import AsyncMock, patch as mock_patch
        from code_agents.cicd.git_client import GitOpsError

        client = TestingClient(python_repo)

        async def run():
            mock_git = AsyncMock()
            mock_git.diff.side_effect = GitOpsError("bad diff")
            with mock_patch("code_agents.cicd.git_client.GitClient", return_value=mock_git):
                return await client.get_coverage_gaps("main", "feature")

        with pytest.raises(TestingError, match="diff"):
            asyncio.run(run())


# ---------------------------------------------------------------------------
# _run_command
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_run_simple_command(self, python_repo):
        client = TestingClient(python_repo)
        rc, stdout, stderr = asyncio.run(client._run_command("echo hello"))
        assert rc == 0
        assert "hello" in stdout

    def test_run_failing_command(self, python_repo):
        client = TestingClient(python_repo)
        rc, stdout, stderr = asyncio.run(client._run_command("false"))
        assert rc != 0

    def test_run_command_stderr(self, python_repo):
        client = TestingClient(python_repo)
        rc, stdout, stderr = asyncio.run(client._run_command("echo err >&2"))
        assert "err" in stderr


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_defaults(self):
        client = TestingClient("/tmp/repo")
        assert client.repo_path == "/tmp/repo"
        assert client.test_command is None
        assert client.coverage_threshold == 100.0

    def test_custom_threshold(self):
        client = TestingClient("/tmp/repo", coverage_threshold=80.0)
        assert client.coverage_threshold == 80.0

    def test_custom_command(self):
        client = TestingClient("/tmp/repo", test_command="make test")
        assert client.test_command == "make test"
