"""Tests for dead_code_eliminator.py — cross-file dead code detection + removal."""

from __future__ import annotations

import os
import textwrap

import pytest

from code_agents.reviews.dead_code_eliminator import (
    DeadCodeEliminator,
    DeadCodeFinding,
    DeadCodeReport,
    format_dead_code_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def py_repo(tmp_path):
    """Minimal Python repo with various dead code patterns."""
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'demo'\n")

    # A module with an unused private function
    (tmp_path / "utils.py").write_text(textwrap.dedent("""\
        def public_helper():
            return 42

        def _unused_private():
            return 99

        def _used_private():
            return 1
    """))

    # A module that uses _used_private
    (tmp_path / "app.py").write_text(textwrap.dedent("""\
        from utils import _used_private

        def main():
            return _used_private()
    """))

    # An unused class
    (tmp_path / "models.py").write_text(textwrap.dedent("""\
        class UsedModel:
            pass

        class _UnusedInternal:
            pass
    """))

    # A file that references UsedModel
    (tmp_path / "service.py").write_text(textwrap.dedent("""\
        from models import UsedModel

        obj = UsedModel()
    """))

    # An orphan file — never imported anywhere
    (tmp_path / "orphan_script.py").write_text(textwrap.dedent("""\
        print("I am never imported")
    """))

    # A module-level unused variable
    (tmp_path / "config.py").write_text(textwrap.dedent("""\
        active_setting = "production"
        stale_var = "never_used_anywhere_xyz"
    """))

    # A file that uses active_setting
    (tmp_path / "runner.py").write_text(textwrap.dedent("""\
        from config import active_setting

        def run():
            return active_setting
    """))

    return tmp_path


@pytest.fixture
def protected_repo(tmp_path):
    """Repo with protected files that should never be flagged."""
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'safe'\n")
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "__main__.py").write_text("print('main')")
    (tmp_path / "conftest.py").write_text("import pytest\n")
    (tmp_path / "test_something.py").write_text(textwrap.dedent("""\
        def test_it():
            assert True
    """))
    return tmp_path


@pytest.fixture
def empty_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'empty'\n")
    return tmp_path


# ---------------------------------------------------------------------------
# DeadCodeFinding dataclass
# ---------------------------------------------------------------------------

class TestDeadCodeFinding:
    def test_fields(self):
        f = DeadCodeFinding(
            file="utils.py", line=5, name="_unused",
            kind="function", proof="0 callers found in 10 files scanned",
        )
        assert f.file == "utils.py"
        assert f.line == 5
        assert f.name == "_unused"
        assert f.kind == "function"
        assert "0 callers" in f.proof


# ---------------------------------------------------------------------------
# DeadCodeReport dataclass
# ---------------------------------------------------------------------------

class TestDeadCodeReport:
    def test_defaults(self):
        r = DeadCodeReport()
        assert r.findings == []
        assert r.total_dead_lines == 0
        assert r.by_kind == {}
        assert r.safe_to_remove == []

    def test_independent_instances(self):
        r1 = DeadCodeReport()
        r2 = DeadCodeReport()
        r1.findings.append(DeadCodeFinding("a.py", 1, "x", "function", "proof"))
        assert len(r2.findings) == 0


# ---------------------------------------------------------------------------
# Scan — unused functions
# ---------------------------------------------------------------------------

class TestFindUnusedFunctions:
    def test_unused_private_detected(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        fn_names = [f.name for f in report.findings if f.kind == "function"]
        assert "_unused_private" in fn_names

    def test_used_private_not_flagged(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        fn_names = [f.name for f in report.findings if f.kind == "function"]
        assert "_used_private" not in fn_names

    def test_dunder_methods_skipped(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='t'\n")
        (tmp_path / "a.py").write_text("def __repr__(self): return ''\n")
        e = DeadCodeEliminator(str(tmp_path))
        report = e.scan()
        fn_names = [f.name for f in report.findings if f.kind == "function"]
        assert "__repr__" not in fn_names

    def test_decorated_functions_skipped(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='t'\n")
        (tmp_path / "a.py").write_text(
            "def my_decorator(f): return f\n"
            "@my_decorator\n"
            "def decorated_fn(): pass\n"
        )
        e = DeadCodeEliminator(str(tmp_path))
        report = e.scan()
        fn_names = [f.name for f in report.findings if f.kind == "function"]
        assert "decorated_fn" not in fn_names


# ---------------------------------------------------------------------------
# Scan — unused classes
# ---------------------------------------------------------------------------

class TestFindUnusedClasses:
    def test_unused_internal_class(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        cls_names = [f.name for f in report.findings if f.kind == "class"]
        assert "_UnusedInternal" in cls_names

    def test_used_class_not_flagged(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        cls_names = [f.name for f in report.findings if f.kind == "class"]
        assert "UsedModel" not in cls_names


# ---------------------------------------------------------------------------
# Scan — orphan files
# ---------------------------------------------------------------------------

class TestFindOrphanFiles:
    def test_orphan_detected(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        orphans = [f.name for f in report.findings if f.kind == "file"]
        assert "orphan_script" in orphans

    def test_imported_file_not_flagged(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        orphans = [f.name for f in report.findings if f.kind == "file"]
        assert "utils" not in orphans

    def test_protected_files_never_flagged(self, protected_repo):
        e = DeadCodeEliminator(str(protected_repo))
        report = e.scan()
        orphans = [f.name for f in report.findings if f.kind == "file"]
        assert "__init__" not in orphans
        assert "__main__" not in orphans
        assert "conftest" not in orphans

    def test_test_files_never_flagged(self, protected_repo):
        e = DeadCodeEliminator(str(protected_repo))
        report = e.scan()
        file_names = [f.file for f in report.findings]
        assert not any("test_" in n for n in file_names)


# ---------------------------------------------------------------------------
# Scan — unused variables
# ---------------------------------------------------------------------------

class TestFindUnusedVariables:
    def test_unused_variable_detected(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        var_names = [f.name for f in report.findings if f.kind == "variable"]
        assert "stale_var" in var_names

    def test_used_variable_not_flagged(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        var_names = [f.name for f in report.findings if f.kind == "variable"]
        assert "active_setting" not in var_names

    def test_constants_skipped(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='t'\n")
        (tmp_path / "a.py").write_text("MAX_RETRIES = 3\n")
        e = DeadCodeEliminator(str(tmp_path))
        report = e.scan()
        var_names = [f.name for f in report.findings if f.kind == "variable"]
        assert "MAX_RETRIES" not in var_names


# ---------------------------------------------------------------------------
# Report aggregation
# ---------------------------------------------------------------------------

class TestReportAggregation:
    def test_by_kind_populated(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        assert isinstance(report.by_kind, dict)
        assert report.by_kind.get("function", 0) >= 1

    def test_total_dead_lines_positive(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        assert report.total_dead_lines > 0

    def test_safe_to_remove_subset(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        for item in report.safe_to_remove:
            assert item in report.findings

    def test_empty_repo_clean(self, empty_repo):
        e = DeadCodeEliminator(str(empty_repo))
        report = e.scan()
        assert report.findings == [] or all(
            f.kind == "file" for f in report.findings
        )


# ---------------------------------------------------------------------------
# Apply — removal
# ---------------------------------------------------------------------------

class TestApply:
    def test_apply_removes_dead_code(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        safe = report.safe_to_remove
        if not safe:
            pytest.skip("No safe items to remove in fixture")

        count = e.apply(safe)
        assert count > 0

    def test_apply_creates_backup(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        # Find a function finding to apply
        fn_findings = [
            f for f in report.safe_to_remove if f.kind == "function"
        ]
        if not fn_findings:
            pytest.skip("No function findings")

        e.apply(fn_findings)
        bak = os.path.join(str(py_repo), fn_findings[0].file + ".deadcode.bak")
        assert os.path.exists(bak)

    def test_apply_empty_list(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        count = e.apply([])
        assert count == 0

    def test_apply_none_runs_scan(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        count = e.apply(None)
        # Should either remove items or return 0 if nothing safe
        assert isinstance(count, int)

    def test_apply_orphan_file_removed(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='t'\n")
        (tmp_path / "lonely.py").write_text("x = 1\n")
        e = DeadCodeEliminator(str(tmp_path))
        orphan = DeadCodeFinding(
            file="lonely.py", line=1, name="lonely",
            kind="file", proof="no imports",
        )
        count = e.apply([orphan])
        assert count == 1
        assert not os.path.exists(str(tmp_path / "lonely.py"))
        assert os.path.exists(str(tmp_path / "lonely.py.deadcode.bak"))


# ---------------------------------------------------------------------------
# Target filtering
# ---------------------------------------------------------------------------

class TestTargetFilter:
    def test_scan_with_target(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan(target="utils.py")
        # Should only contain findings from utils.py
        for f in report.findings:
            if f.kind != "file":
                assert f.file.startswith("utils.py")


# ---------------------------------------------------------------------------
# Build proof
# ---------------------------------------------------------------------------

class TestBuildProof:
    def test_function_proof(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        e._collect_python_files()
        proof = e._build_proof("foo", "function")
        assert "callers" in proof
        assert "files scanned" in proof

    def test_file_proof(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        e._collect_python_files()
        proof = e._build_proof("mod", "file")
        assert "imports" in proof

    def test_class_proof(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        e._collect_python_files()
        proof = e._build_proof("Cls", "class")
        assert "instantiations" in proof or "subclasses" in proof

    def test_variable_proof(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        e._collect_python_files()
        proof = e._build_proof("var", "variable")
        assert "references" in proof


# ---------------------------------------------------------------------------
# Format report
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_format_with_findings(self, py_repo):
        e = DeadCodeEliminator(str(py_repo))
        report = e.scan()
        text = format_dead_code_report(report)
        assert "DEAD CODE ELIMINATOR" in text
        assert "Findings:" in text

    def test_format_empty(self):
        report = DeadCodeReport()
        text = format_dead_code_report(report)
        assert "No dead code detected" in text

    def test_format_truncation(self):
        findings = [
            DeadCodeFinding(f"f{i}.py", i, f"fn{i}", "function", "proof")
            for i in range(25)
        ]
        report = DeadCodeReport(
            findings=findings,
            total_dead_lines=25,
            by_kind={"function": 25},
        )
        text = format_dead_code_report(report)
        assert "and 5 more" in text

    def test_format_safe_marker(self):
        f = DeadCodeFinding("a.py", 1, "_priv", "function", "0 callers")
        report = DeadCodeReport(
            findings=[f],
            total_dead_lines=1,
            by_kind={"function": 1},
            safe_to_remove=[f],
        )
        text = format_dead_code_report(report)
        assert "[safe]" in text

    def test_format_by_kind(self):
        report = DeadCodeReport(
            findings=[
                DeadCodeFinding("a.py", 1, "fn", "function", "proof"),
                DeadCodeFinding("b.py", 1, "Cls", "class", "proof"),
            ],
            total_dead_lines=10,
            by_kind={"function": 1, "class": 1},
        )
        text = format_dead_code_report(report)
        assert "By kind:" in text
        assert "function: 1" in text
        assert "class: 1" in text


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_syntax_error_file_skipped(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='t'\n")
        (tmp_path / "bad.py").write_text("def oops(\n")
        e = DeadCodeEliminator(str(tmp_path))
        report = e.scan()
        # Should not crash, may find orphan but no AST-based findings
        assert isinstance(report, DeadCodeReport)

    def test_empty_file_handled(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='t'\n")
        (tmp_path / "empty.py").write_text("")
        e = DeadCodeEliminator(str(tmp_path))
        report = e.scan()
        assert isinstance(report, DeadCodeReport)

    def test_binary_file_skipped(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname='t'\n")
        (tmp_path / "data.py").write_bytes(b"\x00\x01\x02\x03")
        e = DeadCodeEliminator(str(tmp_path))
        report = e.scan()
        assert isinstance(report, DeadCodeReport)
