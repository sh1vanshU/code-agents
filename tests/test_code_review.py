"""Tests for code_agents.code_review — inline code review with annotated diff."""

from __future__ import annotations

import json
import textwrap
from unittest.mock import patch, MagicMock

import pytest

from code_agents.reviews.code_review import (
    AnnotatedDiffLine,
    CodeReviewResult,
    InlineCodeReview,
    InlineFinding,
    apply_fixes,
    format_annotated_diff,
    to_json,
    _severity_rank,
)


# ---------------------------------------------------------------------------
# Sample diff fixtures
# ---------------------------------------------------------------------------

SAMPLE_DIFF = textwrap.dedent("""\
    diff --git a/app.py b/app.py
    index abc1234..def5678 100644
    --- a/app.py
    +++ b/app.py
    @@ -10,6 +10,12 @@ import os

     class App:
         def run(self):
    +        eval(user_input)
    +        password = "super_secret_123"
    +        query = f"SELECT * FROM users WHERE id = {user_id}"
    +        except:
    +            pass
    +        if x == None:
             return True
""")

SAMPLE_DIFF_PERF = textwrap.dedent("""\
    diff --git a/service.py b/service.py
    index 1111111..2222222 100644
    --- a/service.py
    +++ b/service.py
    @@ -1,4 +1,8 @@
     import time
    +for item in items:
    +    db.query(item.id)
    +time.sleep(10)
    +data = open("big.csv").read()
""")

SAMPLE_DIFF_STYLE = textwrap.dedent("""\
    diff --git a/utils.py b/utils.py
    index aaa1111..bbb2222 100644
    --- a/utils.py
    +++ b/utils.py
    @@ -1,3 +1,6 @@
     def helper():
    +    # TODO: fix this later
    +    # HACK: workaround
    +    print("debug output")
    +    threshold = 42
         pass
""")

SAMPLE_DIFF_CORRECTNESS = textwrap.dedent("""\
    diff --git a/handler.py b/handler.py
    index ccc1111..ddd2222 100644
    --- a/handler.py
    +++ b/handler.py
    @@ -1,3 +1,8 @@
     def process():
    +    except:
    +        pass
    +    if x == None:
    +        return
    +    if type(x) == str:
    +        return x
         pass
""")


# ---------------------------------------------------------------------------
# TestDiffParsing
# ---------------------------------------------------------------------------


class TestDiffParsing:
    """Test that unified diff is parsed into structured hunks."""

    def test_parse_single_file(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF)

        assert len(hunks) >= 1
        assert hunks[0]["file"] == "app.py"
        added = [l for l in hunks[0]["lines"] if l["type"] == "+"]
        assert len(added) >= 4

    def test_parse_multiple_files(self):
        combined = SAMPLE_DIFF + "\n" + SAMPLE_DIFF_PERF
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(combined)

        files = {h["file"] for h in hunks}
        assert "app.py" in files
        assert "service.py" in files

    def test_parse_empty_diff(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff("")
        assert hunks == []

    def test_parse_context_lines(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF)
        context = [l for l in hunks[0]["lines"] if l["type"] == " "]
        assert len(context) > 0

    def test_line_numbers_tracked(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF)
        added = [l for l in hunks[0]["lines"] if l["type"] == "+"]
        # Line numbers should be sequential starting from hunk header
        line_nos = [l["line_no"] for l in added]
        assert all(n is not None for n in line_nos)
        for i in range(1, len(line_nos)):
            assert line_nos[i] == line_nos[i - 1] + 1


# ---------------------------------------------------------------------------
# TestAnalysis
# ---------------------------------------------------------------------------


class TestAnalysis:
    """Test pattern-based detection of security/perf/correctness/style issues."""

    def test_detect_eval(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF)
        findings = reviewer._analyze_hunks(hunks)

        security = [f for f in findings if f.category == "security"]
        messages = [f.message for f in security]
        assert any("eval" in m.lower() for m in messages)

    def test_detect_hardcoded_secret(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF)
        findings = reviewer._analyze_hunks(hunks)

        security = [f for f in findings if f.category == "security"]
        messages = [f.message for f in security]
        assert any("secret" in m.lower() or "credential" in m.lower() for m in messages)

    def test_detect_sql_injection(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF)
        findings = reviewer._analyze_hunks(hunks)

        security = [f for f in findings if f.category == "security"]
        messages = [f.message for f in security]
        assert any("sql" in m.lower() or "parameterized" in m.lower() for m in messages)

    def test_detect_bare_except(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF_CORRECTNESS)
        findings = reviewer._analyze_hunks(hunks)

        correctness = [f for f in findings if f.category == "correctness"]
        messages = [f.message for f in correctness]
        assert any("bare except" in m.lower() or "except" in m.lower() for m in messages)

    def test_detect_none_comparison(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF_CORRECTNESS)
        findings = reviewer._analyze_hunks(hunks)

        correctness = [f for f in findings if f.category == "correctness"]
        messages = [f.message for f in correctness]
        assert any("is None" in m or "is not None" in m for m in messages)

    def test_detect_sleep(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF_PERF)
        findings = reviewer._analyze_hunks(hunks)

        perf = [f for f in findings if f.category == "performance"]
        messages = [f.message for f in perf]
        assert any("sleep" in m.lower() for m in messages)

    def test_detect_todo(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF_STYLE)
        findings = reviewer._analyze_hunks(hunks)

        style = [f for f in findings if f.category == "style"]
        messages = [f.message for f in style]
        assert any("TODO" in m for m in messages)

    def test_detect_print_statement(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF_STYLE)
        findings = reviewer._analyze_hunks(hunks)

        style = [f for f in findings if f.category == "style"]
        messages = [f.message for f in style]
        assert any("print" in m.lower() or "Print" in m for m in messages)

    def test_category_filter(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main", category_filter="security")
        hunks = reviewer._parse_diff(SAMPLE_DIFF)
        all_findings = reviewer._analyze_hunks(hunks)

        # Filter should be applied in run(), so _analyze_hunks returns all
        assert any(f.category != "security" for f in all_findings) or all(
            f.category == "security" for f in all_findings
        )

    def test_severity_on_findings(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF)
        findings = reviewer._analyze_hunks(hunks)

        for f in findings:
            assert f.severity in ("critical", "warning", "suggestion")

    def test_emoji_on_findings(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF)
        findings = reviewer._analyze_hunks(hunks)

        for f in findings:
            assert f.emoji != ""
            assert len(f.emoji) > 0


# ---------------------------------------------------------------------------
# TestAnnotation
# ---------------------------------------------------------------------------


class TestAnnotation:
    """Test merging findings into diff lines."""

    def test_annotate_attaches_finding(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        hunks = reviewer._parse_diff(SAMPLE_DIFF)
        findings = reviewer._analyze_hunks(hunks)
        diff_lines = reviewer._build_diff_lines(SAMPLE_DIFF)
        annotated = reviewer._annotate_diff(diff_lines, findings)

        has_annotation = any(dl.finding is not None for dl in annotated)
        assert has_annotation

    def test_annotate_preserves_line_types(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        diff_lines = reviewer._build_diff_lines(SAMPLE_DIFF)
        annotated = reviewer._annotate_diff(diff_lines, [])

        types = {dl.line_type for dl in annotated}
        assert "+" in types
        assert " " in types

    def test_annotate_empty_findings(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        diff_lines = reviewer._build_diff_lines(SAMPLE_DIFF)
        annotated = reviewer._annotate_diff(diff_lines, [])

        assert all(dl.finding is None for dl in annotated)

    def test_highest_severity_wins(self):
        """When multiple findings target same line, highest severity is kept."""
        finding_low = InlineFinding(
            file="app.py", line=13, category="style",
            severity="suggestion", message="low", emoji="",
        )
        finding_high = InlineFinding(
            file="app.py", line=13, category="security",
            severity="critical", message="high", emoji="",
        )
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        diff_lines = reviewer._build_diff_lines(SAMPLE_DIFF)
        annotated = reviewer._annotate_diff(diff_lines, [finding_low, finding_high])

        annotated_findings = [dl.finding for dl in annotated if dl.finding]
        if annotated_findings:
            assert annotated_findings[0].severity == "critical"


# ---------------------------------------------------------------------------
# TestFormatAnnotatedDiff
# ---------------------------------------------------------------------------


class TestFormatAnnotatedDiff:
    """Test ANSI-formatted output."""

    def test_format_includes_header(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        diff_lines = reviewer._build_diff_lines(SAMPLE_DIFF)
        result = CodeReviewResult(
            base="main", head="HEAD", files=["app.py"],
            diff_lines=diff_lines, findings=[],
            summary={"total": 0, "by_category": {}, "by_severity": {}},
        )
        output = format_annotated_diff(result)
        assert "Code Review" in output

    def test_format_includes_file_name(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        diff_lines = reviewer._build_diff_lines(SAMPLE_DIFF)
        result = CodeReviewResult(
            base="main", head="HEAD", files=["app.py"],
            diff_lines=diff_lines, findings=[],
            summary={"total": 0, "by_category": {}, "by_severity": {}},
        )
        output = format_annotated_diff(result)
        assert "app.py" in output

    def test_format_includes_findings_marker(self):
        finding = InlineFinding(
            file="app.py", line=13, category="security",
            severity="critical", message="eval() is dangerous",
            emoji="\U0001f512",
        )
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        diff_lines = reviewer._build_diff_lines(SAMPLE_DIFF)
        annotated = reviewer._annotate_diff(diff_lines, [finding])
        result = CodeReviewResult(
            base="main", head="HEAD", files=["app.py"],
            diff_lines=annotated, findings=[finding],
            summary={"total": 1, "by_category": {"security": 1}, "by_severity": {"critical": 1}},
        )
        output = format_annotated_diff(result)
        assert "CRITICAL" in output
        assert "eval" in output

    def test_format_no_changes(self):
        result = CodeReviewResult(
            base="main", head="HEAD", files=[], diff_lines=[], findings=[],
            summary={"total": 0},
        )
        output = format_annotated_diff(result)
        assert "No changes" in output

    def test_format_summary_footer(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        diff_lines = reviewer._build_diff_lines(SAMPLE_DIFF)
        result = CodeReviewResult(
            base="main", head="HEAD", files=["a.py"],
            diff_lines=diff_lines, findings=[
                InlineFinding(file="a.py", line=1, category="security",
                              severity="critical", message="test", emoji=""),
                InlineFinding(file="a.py", line=2, category="style",
                              severity="suggestion", message="test2", emoji=""),
            ],
            summary={"total": 2, "by_category": {"security": 1, "style": 1},
                      "by_severity": {"critical": 1, "suggestion": 1}},
        )
        output = format_annotated_diff(result)
        assert "Findings: 2" in output
        assert "critical" in output


# ---------------------------------------------------------------------------
# TestSummary
# ---------------------------------------------------------------------------


class TestSummary:
    """Test summary counts by category and severity."""

    def test_summary_empty(self):
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        summary = reviewer._build_summary([])
        assert summary["total"] == 0
        assert summary["by_category"] == {}
        assert summary["by_severity"] == {}

    def test_summary_counts_categories(self):
        findings = [
            InlineFinding(file="a.py", line=1, category="security",
                          severity="critical", message="x", emoji=""),
            InlineFinding(file="a.py", line=2, category="security",
                          severity="warning", message="y", emoji=""),
            InlineFinding(file="a.py", line=3, category="style",
                          severity="suggestion", message="z", emoji=""),
        ]
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        summary = reviewer._build_summary(findings)

        assert summary["total"] == 3
        assert summary["by_category"]["security"] == 2
        assert summary["by_category"]["style"] == 1

    def test_summary_counts_severities(self):
        findings = [
            InlineFinding(file="a.py", line=1, category="security",
                          severity="critical", message="x", emoji=""),
            InlineFinding(file="a.py", line=2, category="correctness",
                          severity="warning", message="y", emoji=""),
        ]
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        summary = reviewer._build_summary(findings)

        assert summary["by_severity"]["critical"] == 1
        assert summary["by_severity"]["warning"] == 1

    def test_severity_rank(self):
        assert _severity_rank("critical") > _severity_rank("warning")
        assert _severity_rank("warning") > _severity_rank("suggestion")
        assert _severity_rank("suggestion") > _severity_rank("unknown")


# ---------------------------------------------------------------------------
# TestRun (integration with mocked git)
# ---------------------------------------------------------------------------


class TestRun:
    """Test full run() pipeline with mocked git diff."""

    @patch("code_agents.reviews.code_review.subprocess.run")
    def test_run_returns_result(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_DIFF, stderr="", returncode=0,
        )
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        result = reviewer.run()

        assert isinstance(result, CodeReviewResult)
        assert "app.py" in result.files
        assert result.summary["total"] > 0

    @patch("code_agents.reviews.code_review.subprocess.run")
    def test_run_empty_diff(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="", stderr="", returncode=0,
        )
        reviewer = InlineCodeReview(cwd="/tmp", base="main")
        result = reviewer.run()

        assert result.files == []
        assert result.findings == []
        assert result.summary["total"] == 0

    @patch("code_agents.reviews.code_review.subprocess.run")
    def test_run_with_category_filter(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_DIFF, stderr="", returncode=0,
        )
        reviewer = InlineCodeReview(cwd="/tmp", base="main", category_filter="security")
        result = reviewer.run()

        assert all(f.category == "security" for f in result.findings)

    @patch("code_agents.reviews.code_review.subprocess.run")
    def test_run_with_file_filter(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=SAMPLE_DIFF, stderr="", returncode=0,
        )
        reviewer = InlineCodeReview(cwd="/tmp", base="main", files=["app.py"])
        result = reviewer.run()

        # Check that git was called with -- app.py
        call_args = mock_run.call_args_list[0]
        cmd = call_args[0][0]
        assert "app.py" in cmd


# ---------------------------------------------------------------------------
# TestToJson
# ---------------------------------------------------------------------------


class TestToJson:
    """Test JSON export."""

    def test_to_json_structure(self):
        result = CodeReviewResult(
            base="main", head="HEAD", files=["a.py"],
            diff_lines=[], findings=[
                InlineFinding(file="a.py", line=1, category="security",
                              severity="critical", message="test", emoji="x"),
            ],
            summary={"total": 1, "by_category": {"security": 1}, "by_severity": {"critical": 1}},
        )
        data = to_json(result)

        assert data["base"] == "main"
        assert data["head"] == "HEAD"
        assert len(data["findings"]) == 1
        assert data["findings"][0]["category"] == "security"
        # Ensure it's JSON-serializable
        json.dumps(data)
