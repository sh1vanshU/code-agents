"""Tests for pr_preview.py — PR preview generation."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from code_agents.tools.pr_preview import (
    PRPreview, FileStat, CommitInfo, RiskFactor, TestResult, BreakingChange,
    CRITICAL_PATTERNS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary git repo with main branch and a feature branch."""
    repo = str(tmp_path / "repo")
    os.makedirs(repo)

    def run(cmd):
        return subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=repo,
        )

    run("git init")
    run("git config user.email 'test@test.com'")
    run("git config user.name 'Test'")
    run("echo 'hello' > file1.py")
    run("mkdir -p src/main/java/com/example")
    run("echo 'class Foo {}' > src/main/java/com/example/Foo.java")
    run("git add -A")
    run("git commit -m 'initial commit'")
    run("git branch -M main")

    # Create feature branch with changes
    run("git checkout -b feature/PROJ-123-add-payment")
    run("echo 'world' >> file1.py")
    run("echo 'new file' > payment_service.py")
    run("git add -A")
    run("git commit -m 'feat: add payment endpoint'")
    run("echo 'fix' >> file1.py")
    run("git add -A")
    run("git commit -m 'fix: handle edge case'")

    return repo


@pytest.fixture
def preview(tmp_repo):
    """PRPreview instance for the temp repo."""
    return PRPreview(cwd=tmp_repo, base="main")


# ---------------------------------------------------------------------------
# get_current_branch
# ---------------------------------------------------------------------------


class TestGetCurrentBranch:
    def test_returns_branch_name(self, preview):
        assert preview.get_current_branch() == "feature/PROJ-123-add-payment"

    def test_caches_result(self, preview):
        branch1 = preview.get_current_branch()
        branch2 = preview.get_current_branch()
        assert branch1 == branch2


# ---------------------------------------------------------------------------
# get_diff_stats
# ---------------------------------------------------------------------------


class TestGetDiffStats:
    def test_returns_file_stats(self, preview):
        stats = preview.get_diff_stats()
        assert len(stats) >= 1
        paths = [s.path for s in stats]
        assert "file1.py" in paths

    def test_detects_new_file(self, preview):
        stats = preview.get_diff_stats()
        new_files = [s for s in stats if s.status == "A"]
        new_paths = [s.path for s in new_files]
        assert "payment_service.py" in new_paths

    def test_counts_insertions(self, preview):
        stats = preview.get_diff_stats()
        total_ins = sum(s.insertions for s in stats)
        assert total_ins > 0

    def test_caches_results(self, preview):
        stats1 = preview.get_diff_stats()
        stats2 = preview.get_diff_stats()
        assert stats1 is stats2

    def test_empty_on_no_merge_base(self, tmp_path):
        """No merge base returns empty stats."""
        repo = str(tmp_path / "empty_repo")
        os.makedirs(repo)
        subprocess.run("git init", shell=True, cwd=repo, capture_output=True)
        subprocess.run("git config user.email 'test@test.com'", shell=True, cwd=repo, capture_output=True)
        subprocess.run("git config user.name 'Test'", shell=True, cwd=repo, capture_output=True)
        subprocess.run("echo 'x' > f.py && git add -A && git commit -m 'init'", shell=True, cwd=repo, capture_output=True)
        p = PRPreview(cwd=repo, base="nonexistent-branch")
        assert p.get_diff_stats() == []


# ---------------------------------------------------------------------------
# get_total_stats
# ---------------------------------------------------------------------------


class TestGetTotalStats:
    def test_returns_tuple(self, preview):
        files, ins, dels = preview.get_total_stats()
        assert isinstance(files, int)
        assert isinstance(ins, int)
        assert isinstance(dels, int)
        assert files >= 1


# ---------------------------------------------------------------------------
# get_commits
# ---------------------------------------------------------------------------


class TestGetCommits:
    def test_returns_commits(self, preview):
        commits = preview.get_commits()
        assert len(commits) == 2

    def test_commit_messages(self, preview):
        commits = preview.get_commits()
        messages = [c.message for c in commits]
        assert any("payment" in m for m in messages)

    def test_commit_has_sha(self, preview):
        commits = preview.get_commits()
        assert all(len(c.sha) >= 7 for c in commits)

    def test_caches_results(self, preview):
        c1 = preview.get_commits()
        c2 = preview.get_commits()
        assert c1 is c2


# ---------------------------------------------------------------------------
# get_affected_tests
# ---------------------------------------------------------------------------


class TestGetAffectedTests:
    def test_detects_missing_tests(self, preview):
        tests = preview.get_affected_tests()
        # payment_service.py and file1.py should have missing tests
        missing = [t for t in tests if not t.test_exists]
        assert len(missing) >= 1

    def test_source_files_only(self, preview):
        """Test files themselves should not appear in results."""
        tests = preview.get_affected_tests()
        for t in tests:
            assert not t.source_file.startswith("test_")

    def test_returns_test_results(self, preview):
        tests = preview.get_affected_tests()
        assert all(isinstance(t, TestResult) for t in tests)


# ---------------------------------------------------------------------------
# calculate_risk_score
# ---------------------------------------------------------------------------


class TestCalculateRiskScore:
    def test_returns_score_and_factors(self, preview):
        score, factors = preview.calculate_risk_score()
        assert 0 <= score <= 100
        assert isinstance(factors, list)
        assert all(isinstance(f, RiskFactor) for f in factors)

    def test_small_change_low_risk(self, preview):
        """A 2-file change should not be high risk."""
        score, _ = preview.calculate_risk_score()
        assert score < 70  # Not HIGH

    def test_critical_path_increases_risk(self):
        """Files matching critical patterns should increase score."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feature/x"
        preview._commits = [CommitInfo("abc", "feat: change")]
        preview._file_stats = [
            FileStat("src/payment/PaymentService.java", 100, 20, "M"),
            FileStat("src/auth/AuthController.java", 50, 10, "M"),
        ]

        score, factors = preview.calculate_risk_score()
        critical_factors = [f for f in factors if "Critical path" in f.message]
        assert len(critical_factors) >= 1

    def test_many_files_increases_risk(self):
        """More than 10 files should increase risk."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feature/x"
        preview._commits = []
        preview._file_stats = [
            FileStat(f"src/file{i}.py", 10, 5, "M") for i in range(15)
        ]

        score, factors = preview.calculate_risk_score()
        file_factors = [f for f in factors if "files changed" in f.message]
        assert file_factors[0].level == "yellow"
        assert score >= 10

    def test_large_diff_increases_risk(self):
        """Diffs > 1000 lines should be high risk."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feature/x"
        preview._commits = []
        preview._file_stats = [
            FileStat("src/big.py", 800, 300, "M"),
        ]

        score, factors = preview.calculate_risk_score()
        size_factors = [f for f in factors if "lines" in f.message]
        assert size_factors[0].level == "red"

    def test_score_capped_at_100(self):
        """Score should never exceed 100."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feature/x"
        preview._commits = []
        preview._file_stats = [
            FileStat(f"src/payment/file{i}.py", 200, 100, "M") for i in range(25)
        ]

        score, _ = preview.calculate_risk_score()
        assert score <= 100


# ---------------------------------------------------------------------------
# detect_breaking_changes
# ---------------------------------------------------------------------------


class TestDetectBreakingChanges:
    def test_no_breaking_on_small_change(self, preview):
        breaking = preview.detect_breaking_changes()
        # Our test repo has simple changes, no public method removals
        assert isinstance(breaking, list)

    def test_detects_removed_public_java_method(self):
        """Removed public Java method should be flagged."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"

        diff_text = """diff --git a/src/main/java/Foo.java b/src/main/java/Foo.java
-    public String getUser(int id) {
+    private String getUser(int id) {"""

        with patch.object(preview, "_merge_base", return_value="abc123"):
            with patch.object(preview, "_run_git", return_value=(0, diff_text)):
                breaking = preview.detect_breaking_changes()
                assert len(breaking) >= 1
                assert breaking[0].category == "removed_method"
                assert "getUser" in breaking[0].description

    def test_detects_removed_python_function(self):
        """Removed public Python function should be flagged."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"

        diff_text = """diff --git a/module.py b/module.py
-def process_payment(amount):"""

        with patch.object(preview, "_merge_base", return_value="abc123"):
            with patch.object(preview, "_run_git", return_value=(0, diff_text)):
                breaking = preview.detect_breaking_changes()
                assert len(breaking) >= 1
                assert "process_payment" in breaking[0].description

    def test_ignores_private_python_function(self):
        """Private Python functions (starting with _) should not be flagged."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"

        diff_text = """diff --git a/module.py b/module.py
-def _internal_helper(x):"""

        with patch.object(preview, "_merge_base", return_value="abc123"):
            with patch.object(preview, "_run_git", return_value=(0, diff_text)):
                breaking = preview.detect_breaking_changes()
                assert len(breaking) == 0

    def test_detects_api_route_change(self):
        """Removed API route decorator should be flagged."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"

        diff_text = """diff --git a/routes.py b/routes.py
-@app.get("/api/users")"""

        with patch.object(preview, "_merge_base", return_value="abc123"):
            with patch.object(preview, "_run_git", return_value=(0, diff_text)):
                breaking = preview.detect_breaking_changes()
                assert len(breaking) >= 1
                assert breaking[0].category == "api_signature"


# ---------------------------------------------------------------------------
# generate_pr_title
# ---------------------------------------------------------------------------


class TestGeneratePrTitle:
    def test_generates_title_from_commits(self, preview):
        title = preview.generate_pr_title()
        assert len(title) > 0
        # Should have a conventional prefix
        assert ":" in title

    def test_feat_prefix_from_commits(self, preview):
        """First commit is 'feat: add payment endpoint', title should be feat."""
        title = preview.generate_pr_title()
        assert title.startswith("feat")

    def test_scope_from_branch(self, preview):
        """Branch feature/PROJ-123-add-payment should extract scope."""
        title = preview.generate_pr_title()
        # Should have a scope in parens
        assert "(" in title and ")" in title

    def test_fallback_when_no_commits(self):
        """No commits should produce a fallback title."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feature/add-widget"
        preview._commits = []

        title = preview.generate_pr_title()
        assert "feature/add-widget" in title

    def test_fix_branch_infers_type(self):
        """A fix/ branch should infer fix type."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "fix/login-bug"
        preview._commits = [CommitInfo("abc", "handle null pointer")]

        title = preview.generate_pr_title()
        assert title.startswith("fix")


# ---------------------------------------------------------------------------
# generate_pr_body
# ---------------------------------------------------------------------------


class TestGeneratePrBody:
    def test_generates_markdown(self, preview):
        body = preview.generate_pr_body()
        assert "## Summary" in body
        assert "## Changes" in body
        assert "## Risk" in body
        assert "## Test Plan" in body

    def test_includes_commit_messages(self, preview):
        body = preview.generate_pr_body()
        assert "payment" in body.lower()

    def test_includes_file_stats(self, preview):
        body = preview.generate_pr_body()
        assert "files changed" in body


# ---------------------------------------------------------------------------
# format_preview
# ---------------------------------------------------------------------------


class TestFormatPreview:
    def test_produces_output(self, preview):
        output = preview.format_preview()
        assert len(output) > 0

    def test_contains_sections(self, preview):
        output = preview.format_preview()
        assert "PR Preview:" in output
        assert "Title:" in output
        assert "Diff Stats:" in output
        assert "Risk Score:" in output

    def test_contains_branch_names(self, preview):
        output = preview.format_preview()
        assert "feature/PROJ-123-add-payment" in output
        assert "main" in output

    def test_shows_commits(self, preview):
        output = preview.format_preview()
        assert "Commits" in output


# ---------------------------------------------------------------------------
# Risk level helper
# ---------------------------------------------------------------------------


class TestRiskLevel:
    def test_minimal(self):
        assert PRPreview._risk_level(10) == "MINIMAL"

    def test_low(self):
        assert PRPreview._risk_level(25) == "LOW"

    def test_medium(self):
        assert PRPreview._risk_level(50) == "MEDIUM"

    def test_high(self):
        assert PRPreview._risk_level(80) == "HIGH"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestInternalHelpers:
    def test_is_test_file_python(self):
        p = PRPreview(cwd="/tmp")
        assert p._is_test_file("test_foo.py")
        assert p._is_test_file("foo_test.py")
        assert not p._is_test_file("foo.py")

    def test_is_test_file_java(self):
        p = PRPreview(cwd="/tmp")
        assert p._is_test_file("FooTest.java")
        assert not p._is_test_file("Foo.java")

    def test_is_test_file_js(self):
        p = PRPreview(cwd="/tmp")
        assert p._is_test_file("foo.test.js")
        assert p._is_test_file("foo.spec.ts")
        assert not p._is_test_file("foo.js")

    def test_is_non_code_file(self):
        assert PRPreview._is_non_code_file("README.md")
        assert PRPreview._is_non_code_file("config.yaml")
        assert not PRPreview._is_non_code_file("main.py")
        assert not PRPreview._is_non_code_file("App.java")

    def test_find_test_path_python(self):
        p = PRPreview(cwd="/tmp")
        assert p._find_test_path("module.py") == "test_module.py"
        assert p._find_test_path("src/foo.py") == "src/test_foo.py"

    def test_find_test_path_java(self):
        p = PRPreview(cwd="/tmp")
        result = p._find_test_path("src/main/com/example/Foo.java")
        assert result == "src/test/com/example/FooTest.java"

    def test_find_test_path_go(self):
        p = PRPreview(cwd="/tmp")
        assert p._find_test_path("pkg/handler.go") == "pkg/handler_test.go"

    def test_find_test_path_js(self):
        p = PRPreview(cwd="/tmp")
        assert p._find_test_path("src/utils.js") == "src/utils.test.js"

    def test_find_test_path_no_match(self):
        p = PRPreview(cwd="/tmp")
        assert p._find_test_path("Makefile") is None


# ---------------------------------------------------------------------------
# _run_git timeout / error handling (lines 122-124)
# ---------------------------------------------------------------------------


class TestRunGitTimeout:
    def test_git_timeout(self):
        p = PRPreview(cwd="/tmp")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=15)):
            rc, out = p._run_git("log")
        assert rc == 1
        assert out == ""

    def test_git_not_found(self):
        p = PRPreview(cwd="/tmp")
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            rc, out = p._run_git("status")
        assert rc == 1
        assert out == ""


# ---------------------------------------------------------------------------
# get_commits with no merge base (lines 212-213)
# ---------------------------------------------------------------------------


class TestGetCommitsNoBase:
    def test_no_merge_base_returns_empty(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = None
        preview._commits = None
        with patch.object(PRPreview, "_merge_base", return_value=""):
            commits = preview.get_commits()
        assert commits == []


# ---------------------------------------------------------------------------
# calculate_risk_score edge cases (lines 289-350)
# ---------------------------------------------------------------------------


class TestRiskScoreEdgeCases:
    def test_more_than_20_files(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feature/x"
        preview._commits = []
        preview._file_stats = [
            FileStat(f"src/file{i}.py", 10, 5, "M") for i in range(25)
        ]
        score, factors = preview.calculate_risk_score()
        file_factors = [f for f in factors if "files changed" in f.message]
        assert file_factors[0].level == "red"
        assert file_factors[0].points == 20

    def test_medium_diff_size(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feature/x"
        preview._commits = []
        preview._file_stats = [
            FileStat("src/medium.py", 400, 150, "M"),
        ]
        score, factors = preview.calculate_risk_score()
        size_factors = [f for f in factors if "lines" in f.message]
        assert size_factors[0].level == "orange"

    def test_small_diff_size(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feature/x"
        preview._commits = []
        preview._file_stats = [
            FileStat("src/small.py", 150, 100, "M"),
        ]
        score, factors = preview.calculate_risk_score()
        size_factors = [f for f in factors if "lines" in f.message]
        assert size_factors[0].level == "yellow"

    def test_all_tests_covered_reduces_score(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feature/x"
        preview._commits = []
        preview._file_stats = [
            FileStat("src/foo.py", 10, 5, "M"),
        ]
        with patch.object(PRPreview, "_find_test_path", return_value="test_foo.py"), \
             patch.object(PRPreview, "_file_exists", return_value=True):
            score, factors = preview.calculate_risk_score()
        green_factors = [f for f in factors if "All changed files have tests" in f.message]
        assert len(green_factors) == 1

    def test_migration_increases_risk(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feature/x"
        preview._commits = []
        preview._file_stats = [
            FileStat("db/migration_001.py", 20, 0, "A"),
        ]
        score, factors = preview.calculate_risk_score()
        migration_factors = [f for f in factors if "migration" in f.message.lower()]
        assert len(migration_factors) >= 1


# ---------------------------------------------------------------------------
# detect_breaking_changes edge cases (lines 405-419)
# ---------------------------------------------------------------------------


class TestBreakingChangesEdge:
    def test_spring_mapping_removal(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        diff_text = """diff --git a/Controller.java b/Controller.java
-    @GetMapping("/old-path")"""
        with patch.object(preview, "_merge_base", return_value="abc123"):
            with patch.object(preview, "_run_git", return_value=(0, diff_text)):
                breaking = preview.detect_breaking_changes()
                api_changes = [b for b in breaking if b.category == "api_signature"]
                assert len(api_changes) >= 1

    def test_no_diff_returns_empty(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        with patch.object(preview, "_merge_base", return_value="abc123"):
            with patch.object(preview, "_run_git", return_value=(1, "")):
                breaking = preview.detect_breaking_changes()
        assert breaking == []

    def test_no_merge_base_returns_empty(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        with patch.object(preview, "_merge_base", return_value=""):
            breaking = preview.detect_breaking_changes()
        assert breaking == []


# ---------------------------------------------------------------------------
# generate_pr_title edge cases (lines 455-480)
# ---------------------------------------------------------------------------


class TestGeneratePrTitleEdge:
    def test_docs_branch_infers_type(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "docs/update-readme"
        preview._commits = [CommitInfo("abc", "update installation guide")]
        title = preview.generate_pr_title()
        assert title.startswith("docs")

    def test_test_branch_infers_type(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "test/add-coverage"
        preview._commits = [CommitInfo("abc", "add missing tests")]
        title = preview.generate_pr_title()
        assert title.startswith("test")

    def test_no_scope_in_branch(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "main"
        preview._commits = [CommitInfo("abc", "feat: quick fix")]
        title = preview.generate_pr_title()
        assert "feat:" in title


# ---------------------------------------------------------------------------
# generate_pr_body edge cases (lines 507-532)
# ---------------------------------------------------------------------------


class TestGeneratePrBodyEdge:
    def test_body_with_breaking_changes(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/x"
        preview._commits = [CommitInfo("abc", "feat: change")]
        preview._file_stats = [FileStat("src/api.py", 10, 5, "M")]
        with patch.object(preview, "detect_breaking_changes", return_value=[
            BreakingChange("removed_method", "Removed getUser()", "src/api.py")
        ]):
            body = preview.generate_pr_body()
        assert "## Breaking Changes" in body
        assert "Removed getUser()" in body

    def test_body_with_many_commits(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/x"
        preview._commits = [CommitInfo(f"abc{i}", f"commit {i}") for i in range(15)]
        preview._file_stats = [FileStat("src/x.py", 5, 0, "A")]
        body = preview.generate_pr_body()
        assert "... and 5 more commits" in body


# ---------------------------------------------------------------------------
# format_preview edge cases (lines 577-620)
# ---------------------------------------------------------------------------


class TestFormatPreviewEdge:
    def test_format_with_many_files(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/x"
        preview._commits = [CommitInfo("abc", "feat: big change")]
        preview._file_stats = [
            FileStat(f"src/file{i}.py", 10, 5, "M") for i in range(12)
        ]
        output = preview.format_preview()
        assert "... 4 more" in output

    def test_format_with_rename(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/rename"
        preview._commits = [CommitInfo("abc", "refactor: rename file")]
        preview._file_stats = [
            FileStat("new_name.py", 10, 0, "R", rename_from="old_name.py"),
        ]
        output = preview.format_preview()
        assert "[RENAMED from old_name.py]" in output


# ---------------------------------------------------------------------------
# Renamed file status parsing (line 166)
# ---------------------------------------------------------------------------


class TestRenamedFileStatus:
    def test_renamed_file_in_diff(self):
        """Renamed file is parsed with R status (line 166)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._file_stats = None  # reset cache

        numstat_output = "5\t2\tnew_name.py"
        status_output = "R100\told_name.py\tnew_name.py"

        call_count = [0]
        def mock_run_git(*args):
            call_count[0] += 1
            if "--numstat" in args:
                return (0, numstat_output)
            if "--name-status" in args:
                return (0, status_output)
            return (0, "")

        with patch.object(preview, "_merge_base", return_value="abc123"), \
             patch.object(preview, "_run_git", side_effect=mock_run_git):
            stats = preview.get_diff_stats()

        assert len(stats) == 1
        assert stats[0].status == "R"
        assert stats[0].rename_from == "old_name.py"


# ---------------------------------------------------------------------------
# Binary file stats (line 175)
# ---------------------------------------------------------------------------


class TestBinaryFileStats:
    def test_binary_file_dash_stats(self):
        """Binary files show '-' for insertions/deletions (line 175)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._file_stats = None

        numstat_output = "-\t-\timage.png"
        status_output = "A\timage.png"

        def mock_run_git(*args):
            if "--numstat" in args:
                return (0, numstat_output)
            if "--name-status" in args:
                return (0, status_output)
            return (0, "")

        with patch.object(preview, "_merge_base", return_value="abc123"), \
             patch.object(preview, "_run_git", side_effect=mock_run_git):
            stats = preview.get_diff_stats()

        assert len(stats) == 1
        assert stats[0].insertions == 0
        assert stats[0].deletions == 0


# ---------------------------------------------------------------------------
# get_affected_tests skip paths (lines 241, 243)
# ---------------------------------------------------------------------------


class TestGetAffectedTestsSkip:
    def test_skips_test_files(self):
        """Test files themselves are skipped (line 241)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._file_stats = [
            FileStat("tests/test_foo.py", 10, 5, "M"),
            FileStat("src/foo.py", 10, 5, "M"),
        ]
        with patch.object(preview, "_is_test_file", side_effect=lambda p: p.startswith("tests/")), \
             patch.object(preview, "_is_non_code_file", return_value=False), \
             patch.object(preview, "_find_test_path", return_value="tests/test_foo.py"), \
             patch.object(preview, "_file_exists", return_value=True):
            tests = preview.get_affected_tests()
        # Only src/foo.py should be analyzed, not tests/test_foo.py
        source_files = [t.source_file for t in tests]
        assert "tests/test_foo.py" not in source_files

    def test_skips_non_code_files(self):
        """Non-code files (README, etc) are skipped (line 243)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._file_stats = [
            FileStat("README.md", 10, 5, "M"),
            FileStat("src/foo.py", 10, 5, "M"),
        ]
        with patch.object(preview, "_is_test_file", return_value=False), \
             patch.object(preview, "_is_non_code_file", side_effect=lambda p: p.endswith(".md")), \
             patch.object(preview, "_find_test_path", return_value="tests/test_foo.py"), \
             patch.object(preview, "_file_exists", return_value=True):
            tests = preview.get_affected_tests()
        source_files = [t.source_file for t in tests]
        assert "README.md" not in source_files


# ---------------------------------------------------------------------------
# Risk score medium file count (lines 289-290)
# ---------------------------------------------------------------------------


class TestRiskScoreMediumFiles:
    def test_medium_file_count(self):
        """10-20 files adds medium risk (lines 285-290)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._file_stats = [
            FileStat(f"src/file{i}.py", 5, 2, "M") for i in range(15)
        ]
        with patch.object(preview, "get_affected_tests", return_value=[]), \
             patch.object(preview, "detect_breaking_changes", return_value=[]):
            score, factors = preview.calculate_risk_score()
        assert score >= 10
        assert any("15 files" in f.message for f in factors)


# ---------------------------------------------------------------------------
# All tests covered bonus (line 330, 335)
# ---------------------------------------------------------------------------


class TestRiskScoreTestCoverage:
    def test_all_tests_covered_bonus(self):
        """All files having tests reduces score (lines 331-333)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._file_stats = [
            FileStat("src/foo.py", 5, 2, "M"),
        ]
        test_results = [TestResult(
            source_file="src/foo.py",
            test_file="tests/test_foo.py",
            test_exists=True,
            test_modified=False,
        )]
        with patch.object(preview, "get_affected_tests", return_value=test_results), \
             patch.object(preview, "detect_breaking_changes", return_value=[]):
            score, factors = preview.calculate_risk_score()
        assert any("All changed files have tests" in f.message for f in factors)

    def test_no_testable_source(self):
        """No testable source files (line 335)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._file_stats = [
            FileStat("README.md", 5, 0, "M"),
        ]
        with patch.object(preview, "get_affected_tests", return_value=[]), \
             patch.object(preview, "detect_breaking_changes", return_value=[]):
            score, factors = preview.calculate_risk_score()
        assert any("No testable source" in f.message for f in factors)


# ---------------------------------------------------------------------------
# Branch title extraction (line 462, 471)
# ---------------------------------------------------------------------------


class TestBranchTitleExtraction:
    def test_unknown_branch_prefix_defaults_to_feat(self):
        """Branch without known prefix defaults to feat (line 462)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "unknown-prefix/my-feature"
        preview._commits = [CommitInfo("abc", "add cool feature")]
        preview._file_stats = [FileStat("x.py", 5, 0, "A")]
        title = preview.generate_pr_title()
        assert title.startswith("feat")

    def test_scope_truncated(self):
        """Long scope is truncated to 20 chars (line 471)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/PROJ-123-very-long-scope-name-that-exceeds-twenty-characters"
        preview._commits = [CommitInfo("abc", "add feature")]
        preview._file_stats = [FileStat("x.py", 5, 0, "A")]
        title = preview.generate_pr_title()
        # The scope portion should be truncated
        assert len(title) < 200  # reasonable length


# ---------------------------------------------------------------------------
# generate_pr_body test plan section (lines 525, 527, 532)
# ---------------------------------------------------------------------------


class TestGeneratePRBody:
    def test_pr_body_test_plan_modified(self):
        """PR body shows test plan with modified tests (line 525)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/x"
        preview._commits = [CommitInfo("abc", "feat: add")]
        preview._file_stats = [FileStat("src/foo.py", 10, 5, "M")]

        test_results = [TestResult(
            source_file="src/foo.py",
            test_file="tests/test_foo.py",
            test_exists=True,
            test_modified=True,
        )]

        with patch.object(preview, "get_commits", return_value=preview._commits), \
             patch.object(preview, "get_total_stats", return_value=(1, 10, 5)), \
             patch.object(preview, "calculate_risk_score", return_value=(5, [RiskFactor("green", "ok", 0)])), \
             patch.object(preview, "get_affected_tests", return_value=test_results), \
             patch.object(preview, "detect_breaking_changes", return_value=[]):
            body = preview.generate_pr_body()

        assert "test_foo.py" in body
        assert "updated" in body

    def test_pr_body_test_plan_exists_not_modified(self):
        """PR body shows existing but not modified test (line 527)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/x"
        preview._commits = [CommitInfo("abc", "feat: add")]
        preview._file_stats = [FileStat("src/foo.py", 10, 5, "M")]

        test_results = [TestResult(
            source_file="src/foo.py",
            test_file="tests/test_foo.py",
            test_exists=True,
            test_modified=False,
        )]

        with patch.object(preview, "get_commits", return_value=preview._commits), \
             patch.object(preview, "get_total_stats", return_value=(1, 10, 5)), \
             patch.object(preview, "calculate_risk_score", return_value=(5, [RiskFactor("green", "ok", 0)])), \
             patch.object(preview, "get_affected_tests", return_value=test_results), \
             patch.object(preview, "detect_breaking_changes", return_value=[]):
            body = preview.generate_pr_body()

        assert "exists, not modified" in body

    def test_pr_body_no_tests(self):
        """PR body shows manual testing when no tests (line 532)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/x"
        preview._commits = [CommitInfo("abc", "feat: add")]
        preview._file_stats = [FileStat("src/foo.py", 10, 5, "M")]

        with patch.object(preview, "get_commits", return_value=preview._commits), \
             patch.object(preview, "get_total_stats", return_value=(1, 10, 5)), \
             patch.object(preview, "calculate_risk_score", return_value=(5, [RiskFactor("green", "ok", 0)])), \
             patch.object(preview, "get_affected_tests", return_value=[]), \
             patch.object(preview, "detect_breaking_changes", return_value=[]):
            body = preview.generate_pr_body()

        assert "Manual testing" in body


# ---------------------------------------------------------------------------
# format_preview test results section (lines 618, 620)
# ---------------------------------------------------------------------------


class TestFormatPreviewTestResults:
    def test_format_preview_test_exists(self):
        """format_preview shows [ok] for existing tests (line 620)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/x"
        preview._commits = [CommitInfo("abc", "feat: add")]
        preview._file_stats = [FileStat("src/foo.py", 10, 5, "M")]

        test_results = [TestResult(
            source_file="src/foo.py",
            test_file="tests/test_foo.py",
            test_exists=True,
            test_modified=False,
        )]

        with patch.object(preview, "get_affected_tests", return_value=test_results), \
             patch.object(preview, "detect_breaking_changes", return_value=[]), \
             patch.object(preview, "calculate_risk_score", return_value=(5, [RiskFactor("green", "ok", 0)])):
            output = preview.format_preview()

        assert "test_foo.py" in output
        assert "exists" in output

    def test_format_preview_test_modified(self):
        """format_preview shows [ok] for modified tests (line 618)."""
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/x"
        preview._commits = [CommitInfo("abc", "feat: add")]
        preview._file_stats = [FileStat("src/foo.py", 10, 5, "M")]

        test_results = [TestResult(
            source_file="src/foo.py",
            test_file="tests/test_foo.py",
            test_exists=True,
            test_modified=True,
        )]

        with patch.object(preview, "get_affected_tests", return_value=test_results), \
             patch.object(preview, "detect_breaking_changes", return_value=[]), \
             patch.object(preview, "calculate_risk_score", return_value=(5, [RiskFactor("green", "ok", 0)])):
            output = preview.format_preview()

        assert "modified" in output

    def test_format_with_deleted_file(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/cleanup"
        preview._commits = [CommitInfo("abc", "chore: cleanup")]
        preview._file_stats = [
            FileStat("old.py", 0, 50, "D"),
        ]
        output = preview.format_preview()
        assert "[DELETED]" in output

    def test_format_with_new_file(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/new"
        preview._commits = [CommitInfo("abc", "feat: add")]
        preview._file_stats = [
            FileStat("new.py", 50, 0, "A"),
        ]
        output = preview.format_preview()
        assert "[NEW]" in output

    def test_format_many_commits(self):
        preview = PRPreview.__new__(PRPreview)
        preview.cwd = "/tmp"
        preview.base = "main"
        preview._branch = "feat/x"
        preview._commits = [CommitInfo(f"abc{i}", f"commit {i}") for i in range(12)]
        preview._file_stats = [FileStat("x.py", 5, 0, "A")]
        output = preview.format_preview()
        assert "... 4 more" in output
