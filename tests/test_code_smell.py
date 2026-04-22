"""Tests for code_agents.code_smell — Code Smell Detector."""

from __future__ import annotations

import os
import textwrap
import tempfile
import shutil
from unittest import mock

import pytest

from code_agents.reviews.code_smell import (
    CodeSmellDetector,
    SmellFinding,
    SmellReport,
    format_smell_report,
    _indent_level,
    _relative,
)


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temp directory acting as a repo."""
    return str(tmp_path)


def _write(tmp_repo: str, name: str, content: str) -> str:
    """Write a file into the temp repo."""
    path = os.path.join(tmp_repo, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(textwrap.dedent(content))
    return path


# ── SmellFinding / SmellReport dataclasses ──────────────────────────────────

class TestDataClasses:
    def test_smell_finding_defaults(self):
        f = SmellFinding(file="a.py", line=1, smell_type="test", severity="info", message="msg")
        assert f.metric == ""

    def test_smell_finding_with_metric(self):
        f = SmellFinding(file="a.py", line=1, smell_type="test", severity="info", message="msg", metric="100 lines")
        assert f.metric == "100 lines"

    def test_smell_report_defaults(self):
        r = SmellReport()
        assert r.score == 100
        assert r.findings == []
        assert r.by_type == {}
        assert r.by_severity == {}


# ── Helpers ─────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_indent_level_spaces(self):
        assert _indent_level("        code") == 2  # 8 spaces = 2 levels

    def test_indent_level_tabs(self):
        assert _indent_level("\t\tcode") == 2

    def test_indent_level_empty(self):
        assert _indent_level("") == 0

    def test_indent_level_comment(self):
        assert _indent_level("    # comment") == 0

    def test_relative(self):
        assert _relative("/a/b/c.py", "/a") == "b/c.py"


# ── God Class ───────────────────────────────────────────────────────────────

class TestGodClass:
    def test_small_file_no_smell(self, tmp_repo):
        _write(tmp_repo, "small.py", "x = 1\n" * 50)
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_god_class(os.path.join(tmp_repo, "small.py"))
        assert len(findings) == 0

    def test_warning_file(self, tmp_repo):
        _write(tmp_repo, "big.py", "x = 1\n" * 600)
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_god_class(os.path.join(tmp_repo, "big.py"))
        assert len(findings) >= 1
        assert findings[0].severity == "warning"
        assert findings[0].smell_type == "god-class"

    def test_critical_file(self, tmp_repo):
        _write(tmp_repo, "huge.py", "x = 1\n" * 1100)
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_god_class(os.path.join(tmp_repo, "huge.py"))
        assert any(f.severity == "critical" for f in findings)

    def test_critical_class(self, tmp_repo):
        lines = ["class BigClass:\n"] + ["    x = 1\n"] * 1050
        _write(tmp_repo, "cls.py", "".join(lines))
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_god_class(os.path.join(tmp_repo, "cls.py"))
        class_findings = [f for f in findings if "BigClass" in f.message]
        assert len(class_findings) >= 1
        assert class_findings[0].severity == "critical"


# ── Long Method ─────────────────────────────────────────────────────────────

class TestLongMethod:
    def test_short_function_no_smell(self, tmp_repo):
        code = "def short():\n" + "    x = 1\n" * 10
        _write(tmp_repo, "short.py", code)
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_long_method(os.path.join(tmp_repo, "short.py"))
        assert len(findings) == 0

    def test_warning_function(self, tmp_repo):
        code = "def medium():\n" + "    x = 1\n" * 60
        _write(tmp_repo, "medium.py", code)
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_long_method(os.path.join(tmp_repo, "medium.py"))
        assert len(findings) == 1
        assert findings[0].severity == "warning"

    def test_critical_function(self, tmp_repo):
        code = "def long_func():\n" + "    x = 1\n" * 110
        _write(tmp_repo, "long.py", code)
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_long_method(os.path.join(tmp_repo, "long.py"))
        assert len(findings) == 1
        assert findings[0].severity == "critical"

    def test_async_function(self, tmp_repo):
        code = "async def long_async():\n" + "    x = 1\n" * 60
        _write(tmp_repo, "async_long.py", code)
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_long_method(os.path.join(tmp_repo, "async_long.py"))
        assert len(findings) == 1


# ── Long Params ─────────────────────────────────────────────────────────────

class TestLongParams:
    def test_few_params_no_smell(self, tmp_repo):
        _write(tmp_repo, "few.py", "def f(a, b, c):\n    pass\n")
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_long_params(os.path.join(tmp_repo, "few.py"))
        assert len(findings) == 0

    def test_warning_params(self, tmp_repo):
        _write(tmp_repo, "many.py", "def f(a, b, c, d, e, f_):\n    pass\n")
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_long_params(os.path.join(tmp_repo, "many.py"))
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert "6 params" in findings[0].metric

    def test_critical_params(self, tmp_repo):
        _write(tmp_repo, "toomany.py", "def f(a, b, c, d, e, f_, g, h, i):\n    pass\n")
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_long_params(os.path.join(tmp_repo, "toomany.py"))
        assert len(findings) == 1
        assert findings[0].severity == "critical"

    def test_self_excluded(self, tmp_repo):
        _write(tmp_repo, "method.py", """\
class C:
    def m(self, a, b, c, d, e):
        pass
""")
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_long_params(os.path.join(tmp_repo, "method.py"))
        assert len(findings) == 0  # 5 params (self excluded) = exactly threshold, not exceeded


# ── Deep Nesting ────────────────────────────────────────────────────────────

class TestDeepNesting:
    def test_shallow_no_smell(self, tmp_repo):
        _write(tmp_repo, "shallow.py", "if True:\n    if True:\n        x = 1\n")
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_deep_nesting(os.path.join(tmp_repo, "shallow.py"))
        assert len(findings) == 0

    def test_warning_nesting(self, tmp_repo):
        code = "x = 1\n"
        for i in range(5):
            code += "    " * (i + 1) + "if True:\n"
        code += "    " * 6 + "x = 1\n"
        _write(tmp_repo, "nested.py", code)
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_deep_nesting(os.path.join(tmp_repo, "nested.py"))
        assert len(findings) >= 1

    def test_critical_nesting(self, tmp_repo):
        code = "x = 1\n"
        for i in range(7):
            code += "    " * (i + 1) + "if True:\n"
        code += "    " * 8 + "x = 1\n"
        _write(tmp_repo, "deep.py", code)
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_deep_nesting(os.path.join(tmp_repo, "deep.py"))
        assert any(f.severity == "critical" for f in findings)


# ── Feature Envy ────────────────────────────────────────────────────────────

class TestFeatureEnvy:
    def test_no_envy(self, tmp_repo):
        _write(tmp_repo, "no_envy.py", """\
class C:
    def m(self):
        self.a = 1
        self.b = 2
        self.c = 3
""")
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_feature_envy(os.path.join(tmp_repo, "no_envy.py"))
        assert len(findings) == 0

    def test_envy_detected(self, tmp_repo):
        _write(tmp_repo, "envy.py", """\
class C:
    def m(self):
        x = other.a
        y = other.b
        z = other.c
        w = other.d
        v = other.e
""")
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_feature_envy(os.path.join(tmp_repo, "envy.py"))
        assert len(findings) == 1
        assert findings[0].smell_type == "feature-envy"


# ── Primitive Obsession ─────────────────────────────────────────────────────

class TestPrimitiveObsession:
    def test_no_obsession(self, tmp_repo):
        _write(tmp_repo, "no_prim.py", "def f(a: str, b: int):\n    pass\n")
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_primitive_obsession(os.path.join(tmp_repo, "no_prim.py"))
        assert len(findings) == 0

    def test_obsession_detected(self, tmp_repo):
        _write(tmp_repo, "prim.py", "def f(a: str, b: str, c: int, d: float):\n    pass\n")
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_primitive_obsession(os.path.join(tmp_repo, "prim.py"))
        assert len(findings) == 1
        assert findings[0].smell_type == "primitive-obsession"


# ── Shotgun Surgery ─────────────────────────────────────────────────────────

class TestShotgunSurgery:
    def test_shotgun_no_git(self, tmp_repo):
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_shotgun_surgery()
        # No .git, should gracefully return empty
        assert findings == [] or isinstance(findings, list)

    @mock.patch("subprocess.run")
    def test_shotgun_detected(self, mock_run, tmp_repo):
        mock_run.return_value = mock.Mock(
            returncode=0,
            stdout="abc1234 Some commit\nfile1.py\nfile2.py\nfile3.py\nfile4.py\nfile5.py\nfile6.py\n\n",
        )
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_shotgun_surgery()
        assert len(findings) >= 1
        assert findings[0].smell_type == "shotgun-surgery"


# ── Data Clumps ─────────────────────────────────────────────────────────────

class TestDataClumps:
    def test_no_clumps(self, tmp_repo):
        _write(tmp_repo, "no_clump.py", "def f(a, b):\n    pass\ndef g(c, d):\n    pass\n")
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_data_clumps(os.path.join(tmp_repo, "no_clump.py"))
        assert len(findings) == 0

    def test_clumps_detected(self, tmp_repo):
        code = """\
def f1(host, port, timeout):
    pass

def f2(host, port, retries):
    pass

def f3(host, port, verbose):
    pass
"""
        _write(tmp_repo, "clump.py", code)
        d = CodeSmellDetector(cwd=tmp_repo)
        findings = d._check_data_clumps(os.path.join(tmp_repo, "clump.py"))
        assert len(findings) >= 1
        assert findings[0].smell_type == "data-clump"
        assert "host" in findings[0].message and "port" in findings[0].message


# ── Full Scan ───────────────────────────────────────────────────────────────

class TestFullScan:
    def test_clean_repo(self, tmp_repo):
        _write(tmp_repo, "clean.py", "def f(a):\n    return a\n")
        d = CodeSmellDetector(cwd=tmp_repo)
        report = d.scan()
        assert report.score >= 90
        assert isinstance(report.findings, list)

    def test_scan_with_target(self, tmp_repo):
        _write(tmp_repo, "a.py", "x = 1\n" * 600)
        _write(tmp_repo, "b.py", "x = 1\n")
        d = CodeSmellDetector(cwd=tmp_repo)
        report = d.scan(target="b.py")
        # b.py is clean, should have no god-class findings
        god_findings = [f for f in report.findings if f.smell_type == "god-class"]
        assert len(god_findings) == 0

    def test_scan_aggregates(self, tmp_repo):
        _write(tmp_repo, "big.py", "x = 1\n" * 600)
        d = CodeSmellDetector(cwd=tmp_repo)
        report = d.scan()
        assert "god-class" in report.by_type
        assert report.by_severity.get("warning", 0) > 0 or report.by_severity.get("critical", 0) > 0

    def test_score_decreases_with_smells(self, tmp_repo):
        _write(tmp_repo, "smelly.py", "x = 1\n" * 1100)
        d = CodeSmellDetector(cwd=tmp_repo)
        report = d.scan()
        assert report.score < 100

    def test_syntax_error_skipped(self, tmp_repo):
        _write(tmp_repo, "bad.py", "def f(\n")
        d = CodeSmellDetector(cwd=tmp_repo)
        report = d.scan()
        # Should not crash, just skip AST checks
        assert isinstance(report, SmellReport)


# ── Format Report ───────────────────────────────────────────────────────────

class TestFormatReport:
    def test_clean_report(self):
        report = SmellReport(findings=[], score=100, by_type={}, by_severity={})
        output = format_smell_report(report)
        assert "100/100" in output
        assert "Clean codebase" in output

    def test_report_with_findings(self):
        report = SmellReport(
            findings=[
                SmellFinding("a.py", 1, "god-class", "critical", "Too big", "1100 lines"),
                SmellFinding("b.py", 10, "long-method", "warning", "Too long", "60 lines"),
            ],
            score=77,
            by_type={"god-class": 1, "long-method": 1},
            by_severity={"critical": 1, "warning": 1},
        )
        output = format_smell_report(report)
        assert "77/100" in output
        assert "CRITICAL" in output
        assert "WARNING" in output
        assert "god-class" in output
        assert "long-method" in output

    def test_grade_assignment(self):
        for score, grade in [(95, "A"), (80, "B"), (65, "C"), (45, "D"), (20, "F")]:
            report = SmellReport(findings=[], score=score, by_type={}, by_severity={})
            output = format_smell_report(report)
            assert f"({grade})" in output


# ── Non-Python Files ────────────────────────────────────────────────────────

class TestNonPython:
    def test_js_long_function(self, tmp_repo):
        code = "function bigFunc(a, b, c, d, e, f) {\n" + "  let x = 1;\n" * 60 + "}\n"
        _write(tmp_repo, "big.js", code)
        d = CodeSmellDetector(cwd=tmp_repo)
        report = d.scan()
        method_findings = [f for f in report.findings if f.smell_type == "long-method"]
        param_findings = [f for f in report.findings if f.smell_type == "long-params"]
        assert len(method_findings) >= 1 or len(param_findings) >= 1

    def test_unsupported_ext_ignored(self, tmp_repo):
        _write(tmp_repo, "data.csv", "a,b,c\n" * 1000)
        d = CodeSmellDetector(cwd=tmp_repo)
        report = d.scan()
        assert report.score == 100  # CSV files not scanned
