"""Tests for code_agents.mutation_testing — mutation generation, apply/restore, test run, report."""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from code_agents.testing.mutation_testing import (
    Mutation,
    MutationReport,
    MutationTester,
    format_mutation_report,
    format_mutation_report_json,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal Python project for testing."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "calc.py").write_text(textwrap.dedent("""\
        def add(a, b):
            return a + b

        def is_positive(x):
            if x > 0:
                return True
            return False

        def greet(name):
            print(f"Hello, {name}")
            return name

        def safe_divide(a, b):
            if b == 0:
                return None
            return a / b

        def check_range(x):
            if x >= 0 and x <= 100:
                return True
            return False
    """))

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text(textwrap.dedent("""\
        from src.calc import add, is_positive

        def test_add():
            assert add(1, 2) == 3

        def test_is_positive():
            assert is_positive(5) is True
            assert is_positive(-1) is False
    """))

    # Add pyproject.toml so it detects pytest
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")

    return tmp_path


@pytest.fixture
def tester(tmp_project):
    """Create a MutationTester for the temp project."""
    t = MutationTester(cwd=str(tmp_project), test_command="pytest -x -q --tb=no --no-header")
    yield t
    t.cleanup()


# ---------------------------------------------------------------------------
# TestMutationGeneration
# ---------------------------------------------------------------------------

class TestMutationGeneration:
    """Verify all mutation types are generated from sample code."""

    def test_generates_negate_condition(self, tester, tmp_project):
        mutations = tester._generate_mutations(str(tmp_project / "src" / "calc.py"))
        types = {m.mutation_type for m in mutations}
        assert "negate_condition" in types

    def test_generates_remove_return(self, tester, tmp_project):
        mutations = tester._generate_mutations(str(tmp_project / "src" / "calc.py"))
        types = {m.mutation_type for m in mutations}
        assert "remove_return" in types

    def test_generates_swap_operator(self, tester, tmp_project):
        mutations = tester._generate_mutations(str(tmp_project / "src" / "calc.py"))
        types = {m.mutation_type for m in mutations}
        assert "swap_operator" in types

    def test_generates_remove_call(self, tester, tmp_project):
        mutations = tester._generate_mutations(str(tmp_project / "src" / "calc.py"))
        types = {m.mutation_type for m in mutations}
        assert "remove_call" in types

    def test_generates_boundary(self, tester, tmp_project):
        mutations = tester._generate_mutations(str(tmp_project / "src" / "calc.py"))
        types = {m.mutation_type for m in mutations}
        assert "boundary" in types

    def test_generates_swap_boolean(self, tester, tmp_project):
        mutations = tester._generate_mutations(str(tmp_project / "src" / "calc.py"))
        types = {m.mutation_type for m in mutations}
        assert "swap_boolean" in types

    def test_mutation_count_positive(self, tester, tmp_project):
        mutations = tester._generate_mutations(str(tmp_project / "src" / "calc.py"))
        assert len(mutations) > 0

    def test_each_mutation_has_required_fields(self, tester, tmp_project):
        mutations = tester._generate_mutations(str(tmp_project / "src" / "calc.py"))
        for m in mutations:
            assert m.file, "file must be set"
            assert m.line > 0, "line must be positive"
            assert m.original, "original must be set"
            assert m.mutated, "mutated must be set"
            assert m.mutation_type, "mutation_type must be set"
            assert m.original != m.mutated, "mutated must differ from original"

    def test_no_mutations_for_empty_file(self, tester, tmp_project):
        empty = tmp_project / "src" / "empty.py"
        empty.write_text("")
        mutations = tester._generate_mutations(str(empty))
        assert mutations == []


# ---------------------------------------------------------------------------
# TestApplyRestore
# ---------------------------------------------------------------------------

class TestApplyRestore:
    """Verify mutations are applied and then restored correctly."""

    def test_apply_changes_file(self, tester, tmp_project):
        src_file = str(tmp_project / "src" / "calc.py")
        original_content = open(src_file).read()

        mutations = tester._generate_mutations(src_file)
        assert len(mutations) > 0

        mutation = mutations[0]
        tester._apply_mutation(mutation)

        modified_content = open(src_file).read()
        assert modified_content != original_content

    def test_restore_returns_to_original(self, tester, tmp_project):
        src_file = str(tmp_project / "src" / "calc.py")
        original_content = open(src_file).read()

        mutations = tester._generate_mutations(src_file)
        mutation = mutations[0]

        tester._apply_mutation(mutation)
        tester._restore_original(mutation)

        restored_content = open(src_file).read()
        assert restored_content == original_content

    def test_multiple_apply_restore_cycles(self, tester, tmp_project):
        src_file = str(tmp_project / "src" / "calc.py")
        original_content = open(src_file).read()

        mutations = tester._generate_mutations(src_file)
        for mutation in mutations[:5]:
            tester._apply_mutation(mutation)
            tester._restore_original(mutation)

        final_content = open(src_file).read()
        assert final_content == original_content

    def test_backup_file_removed_after_restore(self, tester, tmp_project):
        src_file = str(tmp_project / "src" / "calc.py")
        mutations = tester._generate_mutations(src_file)
        mutation = mutations[0]

        tester._apply_mutation(mutation)
        backup_path = tester._backup_path(src_file)
        assert os.path.isfile(backup_path)

        tester._restore_original(mutation)
        assert not os.path.isfile(backup_path)


# ---------------------------------------------------------------------------
# TestRunTests
# ---------------------------------------------------------------------------

class TestRunTests:
    """Mock subprocess to verify killed/survived classification."""

    def test_killed_when_tests_fail(self, tester):
        mutation = Mutation(file="src/calc.py", line=1, original="x", mutated="y", mutation_type="swap_operator")
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            result = tester._run_tests(mutation)
        assert result == "killed"

    def test_survived_when_tests_pass(self, tester):
        mutation = Mutation(file="src/calc.py", line=1, original="x", mutated="y", mutation_type="swap_operator")
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            result = tester._run_tests(mutation)
        assert result == "survived"

    def test_timeout_when_tests_hang(self, tester):
        mutation = Mutation(file="src/calc.py", line=1, original="x", mutated="y", mutation_type="swap_operator")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="test", timeout=30)):
            result = tester._run_tests(mutation)
        assert result == "timeout"

    def test_error_when_command_fails(self, tester):
        mutation = Mutation(file="src/calc.py", line=1, original="x", mutated="y", mutation_type="swap_operator")
        with patch("subprocess.run", side_effect=OSError("command not found")):
            result = tester._run_tests(mutation)
        assert result == "error"

    def test_uses_test_file_when_found(self, tester, tmp_project):
        mutation = Mutation(
            file=str(tmp_project / "src" / "calc.py"),
            line=1, original="x", mutated="y", mutation_type="swap_operator",
        )
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            tester._run_tests(mutation)
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "test_calc" in cmd


# ---------------------------------------------------------------------------
# TestReport
# ---------------------------------------------------------------------------

class TestReport:
    """Score calculation and format output."""

    def test_score_all_killed(self):
        report = MutationReport(total_mutations=10, killed=10, survived=0, score=1.0)
        assert report.score == 1.0

    def test_score_all_survived(self):
        report = MutationReport(total_mutations=10, killed=0, survived=10, score=0.0)
        assert report.score == 0.0

    def test_score_mixed(self):
        report = MutationReport(total_mutations=10, killed=8, survived=2, score=0.8)
        assert report.score == 0.8

    def test_format_text_contains_score(self):
        report = MutationReport(
            total_mutations=50, killed=41, survived=7, score=0.82,
            timed_out=0, errors=2, duration_seconds=12.5,
            survivors=[
                Mutation(file="src/api.py", line=45, original="x > y", mutated="x >= y",
                         mutation_type="swap_operator", surviving=True),
            ],
        )
        text = format_mutation_report(report)
        assert "82%" in text
        assert "41" in text
        assert "50" in text
        assert "killed" in text
        assert "SURVIVORS" in text
        assert "api.py:45" in text

    def test_format_text_no_mutations(self):
        report = MutationReport()
        text = format_mutation_report(report)
        assert "No mutations" in text

    def test_format_json(self):
        report = MutationReport(
            total_mutations=10, killed=8, survived=2, score=0.8,
            timed_out=0, errors=0, duration_seconds=5.0,
            survivors=[
                Mutation(file="src/x.py", line=10, original="a + b", mutated="a - b",
                         mutation_type="swap_operator", surviving=True),
            ],
        )
        data = format_mutation_report_json(report)
        assert data["total_mutations"] == 10
        assert data["killed"] == 8
        assert data["survived"] == 2
        assert data["score"] == 0.8
        assert data["score_percent"] == 80.0
        assert len(data["survivors"]) == 1
        assert data["survivors"][0]["file"] == "src/x.py"
        assert data["survivors"][0]["line"] == 10

    def test_format_text_many_survivors_truncated(self):
        survivors = [
            Mutation(file=f"src/mod{i}.py", line=i, original="x", mutated="y",
                     mutation_type="swap_operator", surviving=True)
            for i in range(15)
        ]
        report = MutationReport(
            total_mutations=20, killed=5, survived=15, score=0.25,
            survivors=survivors, duration_seconds=30.0,
        )
        text = format_mutation_report(report)
        assert "... and 5 more" in text


# ---------------------------------------------------------------------------
# TestAutoDetect
# ---------------------------------------------------------------------------

class TestAutoDetect:
    """Verify auto-detection of test commands."""

    def test_detect_pytest_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n")
        with patch("shutil.which", return_value=None):
            tester = MutationTester(cwd=str(tmp_path))
            assert "pytest" in tester.test_command
            tester.cleanup()

    def test_detect_pytest_with_poetry(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n")
        with patch("shutil.which", return_value="/usr/bin/poetry"):
            tester = MutationTester(cwd=str(tmp_path))
            assert "poetry run pytest" in tester.test_command
            tester.cleanup()

    def test_detect_npm_test(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        tester = MutationTester(cwd=str(tmp_path))
        assert tester.test_command == "npm test"
        tester.cleanup()

    def test_detect_go_test(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/foo\n")
        tester = MutationTester(cwd=str(tmp_path))
        assert "go test" in tester.test_command
        tester.cleanup()

    def test_detect_maven(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project></project>")
        tester = MutationTester(cwd=str(tmp_path))
        assert "mvn test" in tester.test_command
        tester.cleanup()

    def test_detect_gradle(self, tmp_path):
        (tmp_path / "build.gradle").write_text("")
        tester = MutationTester(cwd=str(tmp_path))
        assert "gradlew test" in tester.test_command
        tester.cleanup()

    def test_fallback_to_pytest(self, tmp_path):
        tester = MutationTester(cwd=str(tmp_path))
        assert "pytest" in tester.test_command
        tester.cleanup()

    def test_custom_test_command(self, tmp_path):
        tester = MutationTester(cwd=str(tmp_path), test_command="make test")
        assert tester.test_command == "make test"
        tester.cleanup()


# ---------------------------------------------------------------------------
# TestFindTestFile
# ---------------------------------------------------------------------------

class TestFindTestFile:
    """Verify source -> test file mapping."""

    def test_finds_test_in_tests_dir(self, tester, tmp_project):
        result = tester._find_test_file(str(tmp_project / "src" / "calc.py"))
        assert result.endswith("test_calc.py")

    def test_returns_empty_for_unknown(self, tester, tmp_project):
        result = tester._find_test_file(str(tmp_project / "src" / "nonexistent.py"))
        assert result == ""


# ---------------------------------------------------------------------------
# TestFindSourceFiles
# ---------------------------------------------------------------------------

class TestFindSourceFiles:
    """Verify source file discovery."""

    def test_finds_files_in_src(self, tester, tmp_project):
        files = tester._find_source_files()
        assert len(files) >= 1
        assert any("calc.py" in f for f in files)

    def test_excludes_test_files(self, tester, tmp_project):
        files = tester._find_source_files()
        for f in files:
            assert "test_" not in os.path.basename(f)

    def test_specific_target_file(self, tester, tmp_project):
        files = tester._find_source_files("src/calc.py")
        assert len(files) == 1
        assert files[0].endswith("calc.py")

    def test_specific_target_dir(self, tester, tmp_project):
        files = tester._find_source_files("src")
        assert len(files) >= 1


# ---------------------------------------------------------------------------
# TestNegateCondition
# ---------------------------------------------------------------------------

class TestNegateCondition:
    """Test the condition negation helper."""

    def test_negate_if(self):
        result = MutationTester._negate_condition_line("    if x > 0:\n")
        assert result == "    if not (x > 0):\n"

    def test_negate_while(self):
        result = MutationTester._negate_condition_line("    while running:\n")
        assert result == "    while not (running):\n"

    def test_un_negate(self):
        result = MutationTester._negate_condition_line("    if not x:\n")
        assert result == "    if x:\n"

    def test_returns_none_for_non_condition(self):
        result = MutationTester._negate_condition_line("    x = 5\n")
        assert result is None


# ---------------------------------------------------------------------------
# TestCleanup
# ---------------------------------------------------------------------------

class TestCleanup:
    """Verify backup directory cleanup."""

    def test_cleanup_removes_backup_dir(self, tmp_path):
        tester = MutationTester(cwd=str(tmp_path))
        backup_dir = tester._backup_dir
        assert os.path.isdir(backup_dir)
        tester.cleanup()
        assert not os.path.isdir(backup_dir)
