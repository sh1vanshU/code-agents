"""Tests for bug_patterns.py — historical bug pattern detector."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_agents.analysis.bug_patterns import (
    BugPattern,
    BugPatternDetector,
    format_bug_warnings,
)


# ---------------------------------------------------------------------------
# BugPattern dataclass
# ---------------------------------------------------------------------------

class TestBugPattern:
    def test_defaults(self):
        bp = BugPattern(pattern="foo", description="test bug")
        assert bp.occurrences == 1
        assert bp.fix_applied == ""
        assert bp.commit_refs == []

    def test_with_fields(self):
        bp = BugPattern(
            pattern=r"null\.field",
            description="NPE pattern",
            occurrences=3,
            fix_applied="added null check",
            commit_refs=["abc123"],
        )
        assert bp.occurrences == 3
        assert bp.commit_refs == ["abc123"]


# ---------------------------------------------------------------------------
# BugPatternDetector — persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_and_load(self, tmp_path):
        store = tmp_path / "patterns.json"
        det = BugPatternDetector(store_path=store)
        det.add_pattern(r"print\(", "Debug print left in", "replaced with logger")
        assert store.exists()

        det2 = BugPatternDetector(store_path=store)
        assert len(det2.patterns) == 1
        assert det2.patterns[0].description == "Debug print left in"

    def test_load_missing_file(self, tmp_path):
        store = tmp_path / "nonexistent.json"
        det = BugPatternDetector(store_path=store)
        assert det.patterns == []

    def test_load_corrupt_file(self, tmp_path):
        store = tmp_path / "bad.json"
        store.write_text("not valid json{{{")
        det = BugPatternDetector(store_path=store)
        assert det.patterns == []


# ---------------------------------------------------------------------------
# check_diff
# ---------------------------------------------------------------------------

class TestCheckDiff:
    def test_matches_known_pattern(self, tmp_path):
        store = tmp_path / "p.json"
        det = BugPatternDetector(store_path=store)
        det.add_pattern(r"System\.exit", "Don't call System.exit in library code")

        diff = """\
+import sys
+System.exit(1)
 other line
"""
        matches = det.check_diff(diff)
        assert len(matches) == 1
        assert "System.exit" in matches[0].description

    def test_no_match_on_clean_diff(self, tmp_path):
        store = tmp_path / "p.json"
        det = BugPatternDetector(store_path=store)
        det.add_pattern(r"System\.exit", "bad pattern")

        diff = """\
+logger.info("starting")
+return result
"""
        matches = det.check_diff(diff)
        assert len(matches) == 0

    def test_only_checks_added_lines(self, tmp_path):
        store = tmp_path / "p.json"
        det = BugPatternDetector(store_path=store)
        det.add_pattern(r"System\.exit", "bad")

        diff = """\
-System.exit(1)
 safe line
"""
        matches = det.check_diff(diff)
        assert len(matches) == 0


# ---------------------------------------------------------------------------
# add_pattern
# ---------------------------------------------------------------------------

class TestAddPattern:
    def test_add_pattern_returns_bug_pattern(self, tmp_path):
        det = BugPatternDetector(store_path=tmp_path / "p.json")
        bp = det.add_pattern(r"Thread\.sleep", "Blocking sleep in async code", "use async delay")
        assert isinstance(bp, BugPattern)
        assert bp.fix_applied == "use async delay"
        assert len(det.patterns) == 1

    def test_multiple_patterns(self, tmp_path):
        det = BugPatternDetector(store_path=tmp_path / "p.json")
        det.add_pattern(r"a", "bug a")
        det.add_pattern(r"b", "bug b")
        assert len(det.patterns) == 2


# ---------------------------------------------------------------------------
# format_bug_warnings
# ---------------------------------------------------------------------------

class TestFormatBugWarnings:
    def test_no_matches(self):
        output = format_bug_warnings([])
        assert "No known bug patterns" in output

    def test_with_matches(self):
        matches = [
            BugPattern(pattern="x", description="NPE risk", occurrences=3, fix_applied="null check"),
            BugPattern(pattern="y", description="Race condition", occurrences=1),
        ]
        output = format_bug_warnings(matches)
        assert "BUG PATTERN WARNINGS" in output
        assert "NPE risk" in output
        assert "Race condition" in output
        assert "null check" in output

    def test_with_commit_refs(self):
        matches = [
            BugPattern(pattern="x", description="leak", occurrences=2, commit_refs=["aaa", "bbb"]),
        ]
        output = format_bug_warnings(matches)
        assert "aaa" in output
        assert "bbb" in output


# ---------------------------------------------------------------------------
# learn_from_history
# ---------------------------------------------------------------------------

class TestLearnFromHistory:
    def test_learn_success(self, tmp_path, monkeypatch):
        """Test learn_from_history parses git log and diffs."""
        import subprocess
        store = tmp_path / "p.json"
        det = BugPatternDetector(repo_path=str(tmp_path), store_path=store)

        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if "log" in cmd:
                result = type("R", (), {
                    "returncode": 0,
                    "stdout": "abc123def4 fix null pointer bug\n",
                    "stderr": "",
                })()
                return result
            if "diff" in cmd:
                result = type("R", (), {
                    "returncode": 0,
                    "stdout": "--- a/foo.py\n+++ b/foo.py\n-old_line_that_was_buggy_and_removed\n+new_line_added\n",
                    "stderr": "",
                })()
                return result
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        count = det.learn_from_history(days=30)
        assert count == 1
        assert len(det.patterns) == 1

    def test_learn_git_timeout(self, tmp_path, monkeypatch):
        import subprocess
        store = tmp_path / "p.json"
        det = BugPatternDetector(repo_path=str(tmp_path), store_path=store)

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 30)

        monkeypatch.setattr(subprocess, "run", fake_run)
        count = det.learn_from_history()
        assert count == 0

    def test_learn_git_not_found(self, tmp_path, monkeypatch):
        import subprocess
        store = tmp_path / "p.json"
        det = BugPatternDetector(repo_path=str(tmp_path), store_path=store)

        def fake_run(cmd, **kwargs):
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(subprocess, "run", fake_run)
        count = det.learn_from_history()
        assert count == 0

    def test_learn_nonzero_returncode(self, tmp_path, monkeypatch):
        import subprocess
        store = tmp_path / "p.json"
        det = BugPatternDetector(repo_path=str(tmp_path), store_path=store)

        def fake_run(cmd, **kwargs):
            return type("R", (), {"returncode": 128, "stdout": "", "stderr": "fatal"})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        count = det.learn_from_history()
        assert count == 0

    def test_learn_existing_pattern_increments(self, tmp_path, monkeypatch):
        """When the same removed line appears again, occurrences increments."""
        import subprocess
        import re
        store = tmp_path / "p.json"
        det = BugPatternDetector(repo_path=str(tmp_path), store_path=store)

        removed_line = "some_buggy_code_that_is_long_enough"

        call_count = [0]
        def fake_run(cmd, **kwargs):
            call_count[0] += 1
            if "log" in cmd:
                return type("R", (), {
                    "returncode": 0,
                    "stdout": "aaa111 fix bug A\nbbb222 fix bug B\n",
                    "stderr": "",
                })()
            if "diff" in cmd:
                return type("R", (), {
                    "returncode": 0,
                    "stdout": f"-{removed_line}\n+fixed_code\n",
                    "stderr": "",
                })()
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        count = det.learn_from_history()
        # First commit creates the pattern, second increments it
        assert count == 1
        assert det.patterns[0].occurrences == 2

    def test_learn_diff_failure_skips(self, tmp_path, monkeypatch):
        """When git diff fails for a commit, it's skipped."""
        import subprocess
        store = tmp_path / "p.json"
        det = BugPatternDetector(repo_path=str(tmp_path), store_path=store)

        def fake_run(cmd, **kwargs):
            if "log" in cmd:
                return type("R", (), {
                    "returncode": 0,
                    "stdout": "aaa111 fix something\n",
                    "stderr": "",
                })()
            # diff always fails
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        count = det.learn_from_history()
        assert count == 0


# ---------------------------------------------------------------------------
# _find_similar
# ---------------------------------------------------------------------------

class TestFindSimilar:
    def test_finds_exact_match(self, tmp_path):
        det = BugPatternDetector(store_path=tmp_path / "p.json")
        det.patterns.append(BugPattern(pattern="exact_pat", description="d"))
        result = det._find_similar("exact_pat")
        assert result is not None
        assert result.pattern == "exact_pat"

    def test_no_match(self, tmp_path):
        det = BugPatternDetector(store_path=tmp_path / "p.json")
        det.patterns.append(BugPattern(pattern="other", description="d"))
        result = det._find_similar("different")
        assert result is None


# ---------------------------------------------------------------------------
# check_diff — edge cases
# ---------------------------------------------------------------------------

class TestCheckDiffEdgeCases:
    def test_invalid_regex_pattern_skipped(self, tmp_path):
        store = tmp_path / "p.json"
        det = BugPatternDetector(store_path=store)
        # Add a pattern with invalid regex
        det.patterns.append(BugPattern(pattern="[invalid", description="bad regex"))
        diff = "+some added line\n"
        matches = det.check_diff(diff)
        assert matches == []

    def test_header_lines_ignored(self, tmp_path):
        store = tmp_path / "p.json"
        det = BugPatternDetector(store_path=store)
        det.add_pattern("dangerous", "dangerous pattern")
        diff = "+++ b/dangerous_file.py\n+safe line\n"
        matches = det.check_diff(diff)
        assert len(matches) == 0


class TestLearnFromHistory:
    """Test learn_from_history — covers line 89 (parts < 2 continue)."""

    @pytest.fixture
    def detector(self, tmp_path):
        from code_agents.analysis.bug_patterns import BugPatternDetector
        store = tmp_path / "p.json"
        return BugPatternDetector(store_path=store, repo_path=str(tmp_path))

    def test_git_log_with_malformed_line(self, detector):
        """Line with no space (single hash, no message) should be skipped."""
        from unittest.mock import patch, MagicMock
        log_result = MagicMock()
        log_result.returncode = 0
        log_result.stdout = "abc123\nabc456 fix: real commit\n"
        diff_result = MagicMock()
        diff_result.returncode = 0
        diff_result.stdout = ""
        with patch("subprocess.run", side_effect=[log_result, diff_result]):
            count = detector.learn_from_history(days=7)
        assert count == 0  # no patterns matched but no crash
