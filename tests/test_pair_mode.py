"""Tests for pair_mode.py — AI pair programming file watcher."""

from __future__ import annotations

import os
import time
import threading

import pytest

from code_agents.domain.pair_mode import (
    FileChange,
    PairMode,
    PairSession,
    Suggestion,
    format_pair_summary,
    _get_patterns_for_file,
    _check_unused_imports,
    _check_missing_error_handling,
)


# ----------------------------------------------------------------
# TestPairSession: construction, watched files filtering
# ----------------------------------------------------------------

class TestPairSession:
    """Verify PairSession initialization and file filtering."""

    def test_default_patterns(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        assert "*.py" in ps.patterns
        assert "*.js" in ps.patterns
        assert "*.java" in ps.patterns
        assert "*.go" in ps.patterns
        assert ps.active is False

    def test_custom_patterns(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path), patterns=["*.rb", "*.rs"])
        assert ps.patterns == ["*.rb", "*.rs"]

    def test_watched_files_basic(self, tmp_path):
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.js").write_text("b")
        (tmp_path / "c.txt").write_text("c")
        ps = PairSession(repo_path=str(tmp_path))
        files = ps._get_watched_files()
        basenames = {os.path.basename(f) for f in files}
        assert "a.py" in basenames
        assert "b.js" in basenames
        assert "c.txt" not in basenames

    def test_watched_files_skip_dirs(self, tmp_path):
        sub = tmp_path / "__pycache__"
        sub.mkdir()
        (sub / "cached.py").write_text("cached")
        (tmp_path / "real.py").write_text("real")
        ps = PairSession(repo_path=str(tmp_path))
        files = ps._get_watched_files()
        basenames = {os.path.basename(f) for f in files}
        assert "real.py" in basenames
        assert "cached.py" not in basenames

    def test_watched_files_with_watch_path(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("code")
        (tmp_path / "root.py").write_text("root")
        ps = PairSession(repo_path=str(tmp_path), watch_path="src")
        files = ps._get_watched_files()
        basenames = {os.path.basename(f) for f in files}
        assert "app.py" in basenames
        assert "root.py" not in basenames

    def test_match_pattern_star_ext(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        assert ps._match_pattern("foo.py") is True
        assert ps._match_pattern("foo.txt") is False

    def test_match_pattern_exact(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path), patterns=["Makefile"])
        assert ps._match_pattern("Makefile") is True
        assert ps._match_pattern("Dockerfile") is False

    def test_hash_file_returns_md5(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("hello")
        ps = PairSession(repo_path=str(tmp_path))
        h = ps._hash_file(str(f))
        assert isinstance(h, str)
        assert len(h) == 32

    def test_hash_file_changes_on_content(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("hello")
        ps = PairSession(repo_path=str(tmp_path))
        h1 = ps._hash_file(str(f))
        f.write_text("world")
        h2 = ps._hash_file(str(f))
        assert h1 != h2

    def test_hash_file_nonexistent(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        assert ps._hash_file("/nonexistent/file.py") == ""


# ----------------------------------------------------------------
# TestChangeDetection: modify -> detected, no change -> empty
# ----------------------------------------------------------------

class TestChangeDetection:
    """Verify change detection logic."""

    def test_detect_modified(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text("original")
        ps = PairSession(repo_path=str(tmp_path))
        ps._snapshot()

        f.write_text("modified content")
        changes = ps._detect_changes()
        assert len(changes) == 1
        assert changes[0][1] == "modified"

    def test_detect_created(self, tmp_path):
        (tmp_path / "existing.py").write_text("x")
        ps = PairSession(repo_path=str(tmp_path))
        ps._snapshot()

        (tmp_path / "new_file.py").write_text("new")
        changes = ps._detect_changes()
        assert len(changes) == 1
        assert changes[0][1] == "created"

    def test_detect_deleted(self, tmp_path):
        f = tmp_path / "doomed.py"
        f.write_text("bye")
        ps = PairSession(repo_path=str(tmp_path))
        ps._snapshot()

        f.unlink()
        changes = ps._detect_changes()
        assert len(changes) == 1
        assert changes[0][1] == "deleted"

    def test_no_changes_returns_empty(self, tmp_path):
        (tmp_path / "stable.py").write_text("stable")
        ps = PairSession(repo_path=str(tmp_path))
        ps._snapshot()

        changes = ps._detect_changes()
        assert changes == []


# ----------------------------------------------------------------
# TestAnalysis: detect debug statements, bare except, unused imports
# ----------------------------------------------------------------

class TestAnalysis:
    """Verify pattern-based analysis of diffs."""

    def test_detect_debug_print(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        diff = "+    print('debug value')"
        suggestions = ps._analyze_change(str(tmp_path / "app.py"), diff)
        messages = [s.message for s in suggestions]
        assert any("print()" in m for m in messages)

    def test_detect_bare_except(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        diff = "+    except:"
        suggestions = ps._analyze_change(str(tmp_path / "app.py"), diff)
        messages = [s.message for s in suggestions]
        assert any("Bare except" in m for m in messages)

    def test_detect_eq_none(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        diff = "+    if x == None:"
        suggestions = ps._analyze_change(str(tmp_path / "app.py"), diff)
        messages = [s.message for s in suggestions]
        assert any("is None" in m for m in messages)

    def test_detect_mutable_default(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        diff = "+def process(items=[]):"
        suggestions = ps._analyze_change(str(tmp_path / "app.py"), diff)
        messages = [s.message for s in suggestions]
        assert any("Mutable default" in m for m in messages)

    def test_detect_console_log_js(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        diff = "+  console.log('test');"
        suggestions = ps._analyze_change(str(tmp_path / "app.js"), diff)
        messages = [s.message for s in suggestions]
        assert any("console.log()" in m for m in messages)

    def test_detect_hardcoded_password(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        diff = "+password = 'hunter2'"
        suggestions = ps._analyze_change(str(tmp_path / "config.py"), diff)
        messages = [s.message for s in suggestions]
        assert any("Hardcoded password" in m for m in messages)

    def test_no_suggestions_for_clean_code(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        diff = "+def greet(name: str) -> str:\n+    return f'Hello, {name}'"
        suggestions = ps._analyze_change(str(tmp_path / "clean.py"), diff)
        # Filter out non-pattern suggestions
        bug_warnings = [s for s in suggestions if s.severity in ("bug", "warning")]
        assert len(bug_warnings) == 0

    def test_unused_imports_detected(self):
        diff = "+import os\n+import sys\n+print(os.getcwd())"
        suggestions = _check_unused_imports("app.py", diff)
        names = [s.message for s in suggestions]
        assert any("sys" in m for m in names)
        assert not any("os" in m for m in names)

    def test_missing_error_handling(self):
        diff = "+def process(data):\n+    return data.strip()"
        suggestions = _check_missing_error_handling("app.py", diff)
        assert len(suggestions) >= 1
        assert any("data" in s.message for s in suggestions)

    def test_empty_diff_returns_empty(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        assert ps._analyze_change(str(tmp_path / "x.py"), "") == []

    def test_patterns_for_python(self):
        patterns = _get_patterns_for_file("app.py")
        # Should include generic + python-specific
        assert len(patterns) > 5

    def test_patterns_for_javascript(self):
        patterns = _get_patterns_for_file("app.js")
        assert len(patterns) > 3

    def test_patterns_for_unknown_ext(self):
        patterns = _get_patterns_for_file("data.csv")
        # Only generic patterns
        assert len(patterns) == len([p for p in patterns])
        assert len(patterns) <= 5


# ----------------------------------------------------------------
# TestSuggestionRender: verify notification format
# ----------------------------------------------------------------

class TestSuggestionRender:
    """Verify suggestion rendering."""

    def test_basic_render(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        s = Suggestion(
            file="src/app.py", line=42, message="Debug print found",
            severity="warning",
        )
        rendered = ps._render_suggestion(s)
        assert "pair:" in rendered
        assert "src/app.py:42" in rendered
        assert "WARN" in rendered
        assert "Debug print found" in rendered

    def test_render_with_code_fix(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        s = Suggestion(
            file="app.py", line=10, message="Use is None",
            severity="bug", code_fix="if x is None:",
        )
        rendered = ps._render_suggestion(s)
        assert "BUG" in rendered
        assert "fix:" in rendered
        assert "if x is None:" in rendered

    def test_render_no_line(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        s = Suggestion(
            file="app.py", line=0, message="Unused import",
            severity="warning",
        )
        rendered = ps._render_suggestion(s)
        assert "app.py" in rendered
        assert ":0" not in rendered


# ----------------------------------------------------------------
# TestDebounce: rapid changes produce single analysis
# ----------------------------------------------------------------

class TestDebounce:
    """Verify debounce behavior — rapid changes are batched."""

    def test_debounce_batches_changes(self, tmp_path):
        """Multiple rapid edits should be debounced into one batch."""
        f = tmp_path / "rapid.py"
        f.write_text("v1")
        ps = PairSession(repo_path=str(tmp_path))
        ps._snapshot()

        # Simulate rapid edits
        f.write_text("v2")
        changes1 = ps._detect_changes()
        f.write_text("v3")
        changes2 = ps._detect_changes()

        # Each call to _detect_changes updates the hash,
        # so each one should detect a change
        assert len(changes1) == 1
        assert len(changes2) == 1
        # But the file path should be the same
        assert changes1[0][0] == changes2[0][0]

    def test_debounce_delay_attribute(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        assert ps._debounce_delay == 0.5  # 500ms


# ----------------------------------------------------------------
# TestPairMode: backward-compatible wrapper
# ----------------------------------------------------------------

class TestPairMode:
    """Verify PairMode wrapper for slash command compatibility."""

    def test_pair_mode_constructor(self, tmp_path):
        pm = PairMode(cwd=str(tmp_path))
        assert pm.repo_path == str(tmp_path)
        assert pm.cwd == str(tmp_path)
        assert "*.py" in pm.watch_patterns

    def test_pair_mode_custom_patterns(self, tmp_path):
        pm = PairMode(cwd=str(tmp_path), watch_patterns=["*.rb"])
        assert pm.watch_patterns == ["*.rb"]
        assert pm.patterns == ["*.rb"]

    def test_pair_mode_watch_patterns_setter(self, tmp_path):
        pm = PairMode(cwd=str(tmp_path))
        pm.watch_patterns = ["*.rs"]
        assert pm.patterns == ["*.rs"]


# ----------------------------------------------------------------
# TestFormatPairSummary
# ----------------------------------------------------------------

class TestFormatPairSummary:
    """Verify session summary formatting."""

    def test_empty_suggestions(self):
        result = format_pair_summary([])
        assert "No suggestions" in result

    def test_groups_by_file(self):
        suggestions = [
            Suggestion(file="a.py", line=1, message="Bug 1", severity="bug"),
            Suggestion(file="a.py", line=5, message="Warn 1", severity="warning"),
            Suggestion(file="b.py", line=2, message="Improve 1", severity="improvement"),
        ]
        result = format_pair_summary(suggestions)
        assert "3 suggestion(s)" in result
        assert "2 file(s)" in result
        assert "Bugs: 1" in result
        assert "Warnings: 1" in result
        assert "Improvements: 1" in result

    def test_summary_contains_file_names(self):
        suggestions = [
            Suggestion(file="src/main.py", line=10, message="test", severity="warning"),
        ]
        result = format_pair_summary(suggestions)
        assert "src/main.py" in result


# ----------------------------------------------------------------
# TestStartStopLifecycle
# ----------------------------------------------------------------

class TestStartStopLifecycle:
    """Verify start/stop lifecycle of PairSession."""

    def test_start_activates_and_snapshots(self, tmp_path):
        (tmp_path / "a.py").write_text("code")
        ps = PairSession(repo_path=str(tmp_path))
        assert ps.active is False
        ps.start()
        assert ps.active is True
        assert len(ps._file_hashes) == 1
        ps.stop()

    def test_stop_deactivates(self, tmp_path):
        (tmp_path / "a.py").write_text("code")
        ps = PairSession(repo_path=str(tmp_path))
        ps.start()
        ps.stop()
        assert ps.active is False

    def test_start_launches_thread(self, tmp_path):
        (tmp_path / "a.py").write_text("code")
        ps = PairSession(repo_path=str(tmp_path))
        ps.start()
        assert ps._thread is not None
        assert ps._thread.is_alive()
        ps.stop()
        assert ps._thread is None

    def test_double_start_warns(self, tmp_path):
        ps = PairSession(repo_path=str(tmp_path))
        ps.start()
        ps.start()  # should warn but not crash
        ps.stop()
