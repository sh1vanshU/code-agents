"""Tests for code_agents.tools.watch_mode — file watcher with auto-lint, auto-test, auto-fix."""

from __future__ import annotations

import os
import time
from unittest.mock import MagicMock, patch

import pytest

from code_agents.tools.watch_mode import (
    FileChange,
    LintResult,
    TestResult,
    WatchCycle,
    WatchMode,
    WatchStats,
    format_watch_event,
    format_watch_stats,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def python_repo(tmp_path):
    """Create a minimal Python project."""
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'demo'\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (src / "auth.py").write_text("def login(user, pwd):\n    pass\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_calc.py").write_text("def test_add():\n    from src.calc import add\n    assert add(1, 2) == 3\n")
    return tmp_path


@pytest.fixture
def js_repo(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "demo"}')
    src = tmp_path / "src"
    src.mkdir()
    (src / "utils.js").write_text("function greet(name) { return `Hello ${name}`; }\n")
    return tmp_path


@pytest.fixture
def go_repo(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/demo")
    return tmp_path


# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------


class TestStackDetection:
    def test_detect_python(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        assert wm.language == "python"
        assert wm.test_framework == "pytest"

    def test_detect_javascript(self, js_repo):
        wm = WatchMode(repo_path=str(js_repo))
        assert wm.language == "javascript"
        assert wm.test_framework == "jest"
        assert wm.lint_tool == "eslint"

    def test_detect_java(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        wm = WatchMode(repo_path=str(tmp_path))
        assert wm.language == "java"

    def test_detect_go(self, go_repo):
        wm = WatchMode(repo_path=str(go_repo))
        assert wm.language == "go"
        assert wm.test_framework == "go test"

    def test_no_stack(self, tmp_path):
        wm = WatchMode(repo_path=str(tmp_path))
        assert wm.language == ""


# ---------------------------------------------------------------------------
# File watching
# ---------------------------------------------------------------------------


class TestFileWatching:
    def test_snapshot_files(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        wm.snapshot()
        assert len(wm._file_hashes) >= 2  # calc.py, auth.py at minimum

    def test_detect_no_changes(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        wm.snapshot()
        changes = wm.detect_changes()
        assert len(changes) == 0

    def test_detect_modified_file(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        wm.snapshot()
        # Modify a file
        (python_repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b + 0\n")
        changes = wm.detect_changes()
        assert len(changes) == 1
        assert changes[0].file == "src/calc.py"
        assert changes[0].change_type == "modified"

    def test_detect_new_file(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        wm.snapshot()
        (python_repo / "src" / "new_module.py").write_text("x = 1\n")
        changes = wm.detect_changes()
        assert len(changes) == 1
        assert changes[0].change_type == "created"

    def test_skips_pycache(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        pycache = python_repo / "src" / "__pycache__"
        pycache.mkdir()
        (pycache / "calc.cpython-310.pyc").write_bytes(b"\x00")
        wm.snapshot()
        # No .pyc files should be in hashes
        for fpath in wm._file_hashes:
            assert "__pycache__" not in fpath

    def test_match_pattern(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        assert wm._match_pattern("foo.py") is True
        assert wm._match_pattern("bar.js") is True
        assert wm._match_pattern("readme.md") is False

    def test_custom_patterns(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), watch_patterns=["*.txt"])
        (python_repo / "src" / "notes.txt").write_text("hello")
        files = wm._get_watched_files()
        names = [os.path.basename(f) for f in files]
        assert "notes.txt" in names
        assert "calc.py" not in names

    def test_watch_specific_path(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), watch_path="src")
        files = wm._get_watched_files()
        # Should only find files under src/
        for f in files:
            assert f.startswith(str(python_repo / "src"))


# ---------------------------------------------------------------------------
# Test file mapping
# ---------------------------------------------------------------------------


class TestFindTestFile:
    def test_python_mapping(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        result = wm.find_test_file("src/calc.py")
        assert result == "tests/test_calc.py"

    def test_no_test_file(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        result = wm.find_test_file("src/auth.py")
        assert result == ""

    def test_js_mapping(self, js_repo):
        wm = WatchMode(repo_path=str(js_repo))
        # No test file exists
        result = wm.find_test_file("src/utils.js")
        assert result == ""

    def test_go_mapping(self, go_repo):
        wm = WatchMode(repo_path=str(go_repo))
        (go_repo / "handler.go").write_text("package main\n")
        (go_repo / "handler_test.go").write_text("package main\n")
        result = wm.find_test_file("handler.go")
        assert result == "handler_test.go"


# ---------------------------------------------------------------------------
# Lint running
# ---------------------------------------------------------------------------


class TestLintRunning:
    def test_lint_skipped_when_test_only(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), test_only=True)
        results = wm.run_lint(["src/calc.py"])
        assert len(results) == 0

    def test_lint_skipped_when_no_tool(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        wm.lint_tool = ""
        results = wm.run_lint(["src/calc.py"])
        assert len(results) == 0

    def test_lint_file_not_found_tool(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        wm.lint_tool = "nonexistent_linter_xyz"
        results = wm.run_lint(["src/calc.py"])
        assert len(results) == 1
        assert results[0].passed is True  # FileNotFoundError → treated as pass
        assert results[0].tool == "none"

    def test_auto_fix_lint_no_tool(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        wm.lint_tool = "flake8"  # flake8 has no --fix
        lr = LintResult(file="src/calc.py", passed=False, tool="flake8", errors=["E501"])
        result = wm.auto_fix_lint(lr)
        assert result is False


# ---------------------------------------------------------------------------
# Test running
# ---------------------------------------------------------------------------


class TestTestRunning:
    def test_tests_skipped_when_lint_only(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), lint_only=True)
        results = wm.run_tests(["src/calc.py"])
        assert len(results) == 0

    def test_runs_mapped_test_file(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        results = wm.run_tests(["src/calc.py"])
        assert len(results) == 1
        assert results[0].test_file == "tests/test_calc.py"
        assert results[0].passed is True
        assert results[0].passed_count >= 1

    def test_skips_files_without_tests(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        results = wm.run_tests(["src/auth.py"])
        assert len(results) == 0  # No test file for auth.py

    def test_deduplicates_test_files(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        # Two source files mapping to same test shouldn't run it twice
        results = wm.run_tests(["src/calc.py", "src/calc.py"])
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Process changes (single cycle)
# ---------------------------------------------------------------------------


class TestProcessChanges:
    @pytest.mark.asyncio
    async def test_cycle_with_lint_and_test(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), no_fix=True)
        wm.lint_tool = ""  # skip lint for this test
        changes = [FileChange(file="src/calc.py", change_type="modified")]
        cycle = await wm.process_changes(changes)
        assert cycle.files_changed == ["src/calc.py"]
        assert len(cycle.test_results) == 1
        assert cycle.test_results[0].passed is True

    @pytest.mark.asyncio
    async def test_cycle_lint_only(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), lint_only=True, no_fix=True)
        changes = [FileChange(file="src/calc.py", change_type="modified")]
        cycle = await wm.process_changes(changes)
        assert len(cycle.test_results) == 0

    @pytest.mark.asyncio
    async def test_cycle_test_only(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), test_only=True, no_fix=True)
        changes = [FileChange(file="src/calc.py", change_type="modified")]
        cycle = await wm.process_changes(changes)
        assert len(cycle.lint_results) == 0
        assert len(cycle.test_results) == 1

    @pytest.mark.asyncio
    async def test_event_callback(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), no_fix=True)
        wm.lint_tool = ""
        changes = [FileChange(file="src/calc.py", change_type="modified")]
        events = []

        def on_event(etype, detail):
            events.append(etype)

        await wm.process_changes(changes, on_event=on_event)
        assert "test_ok" in events or "cycle_done" not in events  # at least ran

    @pytest.mark.asyncio
    async def test_stats_updated(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), no_fix=True)
        wm.lint_tool = ""
        changes = [FileChange(file="src/calc.py", change_type="modified")]
        await wm.process_changes(changes)
        assert wm.stats.cycles == 1
        assert wm.stats.files_changed == 1


# ---------------------------------------------------------------------------
# Code extraction
# ---------------------------------------------------------------------------


class TestExtractCode:
    def test_extract_from_fence(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        response = "```python\ndef foo():\n    pass\n```"
        code = wm._extract_code(response)
        assert "def foo" in code

    def test_extract_raw(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        response = "import os\ndef bar():\n    return 1\n"
        code = wm._extract_code(response)
        assert "import os" in code


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


class TestFormatting:
    def test_format_stats(self):
        stats = WatchStats(
            started_at=time.time() - 120,
            cycles=5,
            files_changed=10,
            lint_errors_found=3,
            lint_errors_fixed=2,
            test_failures_found=1,
            test_failures_fixed=1,
        )
        output = format_watch_stats(stats)
        assert "5 cycles" in output
        assert "10" in output
        assert "3 found" in output
        assert "2 auto-fixed" in output

    def test_format_event_types(self):
        for event_type in ["started", "stopped", "changes", "lint_ok", "lint_fail",
                           "lint_fixed", "test_ok", "test_fail", "test_fixed", "cycle_done"]:
            output = format_watch_event(event_type, "test detail")
            assert "test detail" in output

    def test_format_stats_zero(self):
        stats = WatchStats(started_at=time.time())
        output = format_watch_stats(stats)
        assert "0 cycles" in output


# ---------------------------------------------------------------------------
# Stop behavior
# ---------------------------------------------------------------------------


class TestStopBehavior:
    def test_stop_sets_inactive(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo))
        wm.active = True
        wm.stop()
        assert wm.active is False

    def test_interval_clamped(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), interval=0.1)
        assert wm.interval == 1.0  # minimum 1s


# ---------------------------------------------------------------------------
# Configuration flags
# ---------------------------------------------------------------------------


class TestBackgroundMode:
    def test_run_in_background(self, python_repo):
        import time
        wm = WatchMode(repo_path=str(python_repo), interval=1.0)
        events = []

        def on_event(etype, detail):
            events.append(etype)

        thread = wm.run_in_background(on_event=on_event)
        assert thread.is_alive()

        # Give the thread time to start the async loop
        time.sleep(1.5)
        assert wm.active is True
        assert "started" in events

        # Stop it
        wm.stop()
        thread.join(timeout=5)
        assert wm.active is False


class TestConfigFlags:
    def test_lint_only_flag(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), lint_only=True)
        assert wm.lint_only is True
        assert wm.test_only is False

    def test_test_only_flag(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), test_only=True)
        assert wm.test_only is True

    def test_no_fix_flag(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), no_fix=True)
        assert wm.no_fix is True

    def test_custom_interval(self, python_repo):
        wm = WatchMode(repo_path=str(python_repo), interval=10.0)
        assert wm.interval == 10.0
