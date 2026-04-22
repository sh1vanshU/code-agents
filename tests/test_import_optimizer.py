"""Tests for import_optimizer module."""

from __future__ import annotations

import os
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.reviews.import_optimizer import (
    ImportFinding,
    ImportOptimizer,
    format_import_report,
)


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with sample files."""
    return tmp_path


def _write(path: Path, content: str) -> Path:
    """Write dedented content to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


# ------------------------------------------------------------------
# Test ImportFinding dataclass
# ------------------------------------------------------------------

class TestImportFinding:
    def test_creation(self):
        f = ImportFinding(
            file="src/main.py", line=3, import_statement="import os",
            issue="unused", severity="warning", suggestion="Remove unused import: os",
        )
        assert f.file == "src/main.py"
        assert f.line == 3
        assert f.issue == "unused"
        assert f.severity == "warning"

    def test_all_issue_types(self):
        for issue in ("unused", "circular", "heavy", "wildcard", "duplicate", "shadowed"):
            f = ImportFinding(
                file="a.py", line=1, import_statement="import x",
                issue=issue, severity="warning", suggestion="fix it",
            )
            assert f.issue == issue


# ------------------------------------------------------------------
# Test unused import detection
# ------------------------------------------------------------------

class TestFindUnused:
    def test_detects_unused_import(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import os
            import sys
            print("hello")
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        unused = [f for f in findings if f.issue == "unused"]
        names = [f.suggestion for f in unused]
        assert any("os" in s for s in names)
        assert any("sys" in s for s in names)

    def test_used_import_not_flagged(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import os
            path = os.path.join("a", "b")
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        unused = [f for f in findings if f.issue == "unused"]
        assert len(unused) == 0

    def test_from_import_unused(self, tmp_project):
        _write(tmp_project / "app.py", """\
            from os.path import join, exists
            result = join("a", "b")
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        unused = [f for f in findings if f.issue == "unused"]
        assert len(unused) == 1
        assert "exists" in unused[0].suggestion

    def test_aliased_import_used(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import numpy as np
            x = np.array([1, 2])
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        unused = [f for f in findings if f.issue == "unused"]
        assert len(unused) == 0

    def test_aliased_import_unused(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import numpy as np
            x = 42
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        unused = [f for f in findings if f.issue == "unused"]
        assert len(unused) >= 1
        assert any("np" in f.suggestion for f in unused)


# ------------------------------------------------------------------
# Test heavy import detection
# ------------------------------------------------------------------

class TestFindHeavy:
    def test_detects_heavy_import(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import tensorflow
            import pandas as pd
            x = 1
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        heavy = [f for f in findings if f.issue == "heavy"]
        assert len(heavy) == 2

    def test_detects_from_heavy_import(self, tmp_project):
        _write(tmp_project / "app.py", """\
            from torch import nn
            model = nn.Linear(10, 5)
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        heavy = [f for f in findings if f.issue == "heavy"]
        assert len(heavy) == 1
        assert "lazy" in heavy[0].suggestion.lower()

    def test_non_heavy_not_flagged(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import os
            import json
            x = os.getcwd()
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        heavy = [f for f in findings if f.issue == "heavy"]
        assert len(heavy) == 0


# ------------------------------------------------------------------
# Test wildcard import detection
# ------------------------------------------------------------------

class TestFindWildcard:
    def test_detects_wildcard(self, tmp_project):
        _write(tmp_project / "app.py", """\
            from os.path import *
            p = join("a", "b")
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        wildcards = [f for f in findings if f.issue == "wildcard"]
        assert len(wildcards) == 1
        assert "explicit" in wildcards[0].suggestion.lower()

    def test_no_wildcard_clean(self, tmp_project):
        _write(tmp_project / "app.py", """\
            from os.path import join
            p = join("a", "b")
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        wildcards = [f for f in findings if f.issue == "wildcard"]
        assert len(wildcards) == 0


# ------------------------------------------------------------------
# Test duplicate import detection
# ------------------------------------------------------------------

class TestFindDuplicate:
    def test_detects_duplicate_module(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import os
            import os
            os.getcwd()
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        dupes = [f for f in findings if f.issue == "duplicate"]
        assert len(dupes) >= 1

    def test_detects_duplicate_name(self, tmp_project):
        _write(tmp_project / "app.py", """\
            from os.path import join
            from posixpath import join
            join("a", "b")
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        dupes = [f for f in findings if f.issue == "duplicate"]
        assert len(dupes) >= 1


# ------------------------------------------------------------------
# Test shadowed import detection
# ------------------------------------------------------------------

class TestFindShadowed:
    def test_detects_shadowed_by_assignment(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import os
            os = "overwritten"
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        shadowed = [f for f in findings if f.issue == "shadowed"]
        assert len(shadowed) == 1
        assert "os" in shadowed[0].suggestion

    def test_detects_shadowed_by_function(self, tmp_project):
        _write(tmp_project / "app.py", """\
            from typing import Any

            def Any():
                pass
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        shadowed = [f for f in findings if f.issue == "shadowed"]
        assert len(shadowed) == 1

    def test_no_shadow_normal_code(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import os
            path = os.getcwd()
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("app.py")
        shadowed = [f for f in findings if f.issue == "shadowed"]
        assert len(shadowed) == 0


# ------------------------------------------------------------------
# Test circular dependency detection
# ------------------------------------------------------------------

class TestFindCircular:
    def test_detects_circular(self, tmp_project):
        _write(tmp_project / "mod_a.py", """\
            import mod_b
        """)
        _write(tmp_project / "mod_b.py", """\
            import mod_a
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan()
        circular = [f for f in findings if f.issue == "circular"]
        assert len(circular) >= 1
        assert "mod_a" in circular[0].import_statement
        assert "mod_b" in circular[0].import_statement

    def test_no_circular_clean(self, tmp_project):
        _write(tmp_project / "mod_a.py", """\
            import os
        """)
        _write(tmp_project / "mod_b.py", """\
            import sys
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan()
        circular = [f for f in findings if f.issue == "circular"]
        assert len(circular) == 0


# ------------------------------------------------------------------
# Test auto-fix
# ------------------------------------------------------------------

class TestAutoFix:
    def test_fix_removes_unused(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import os
            import sys
            print("hello")
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        count = opt.fix("app.py")
        assert count >= 1

        content = (tmp_project / "app.py").read_text()
        assert "import os" not in content
        assert "import sys" not in content
        assert 'print("hello")' in content

    def test_fix_preserves_used(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import os
            import sys
            os.getcwd()
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        count = opt.fix("app.py")
        assert count >= 1

        content = (tmp_project / "app.py").read_text()
        assert "import os" in content
        assert "import sys" not in content

    def test_fix_returns_zero_when_clean(self, tmp_project):
        _write(tmp_project / "app.py", """\
            import os
            os.getcwd()
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        count = opt.fix("app.py")
        assert count == 0


# ------------------------------------------------------------------
# Test format_import_report
# ------------------------------------------------------------------

class TestFormatReport:
    def test_empty_findings(self):
        report = format_import_report([])
        assert "No import issues" in report

    def test_report_with_findings(self):
        findings = [
            ImportFinding("a.py", 1, "import os", "unused", "warning", "Remove unused import: os"),
            ImportFinding("b.py", 5, "from torch import nn", "heavy", "info", "Move inside function"),
            ImportFinding("c.py", 1, "a -> b -> a", "circular", "error", "Break cycle"),
        ]
        report = format_import_report(findings)
        assert "Unused Imports" in report
        assert "Heavy" in report
        assert "Circular" in report
        assert "3 issue(s)" in report

    def test_report_severity_counts(self):
        findings = [
            ImportFinding("a.py", 1, "import os", "unused", "warning", "fix"),
            ImportFinding("a.py", 2, "import sys", "unused", "warning", "fix"),
            ImportFinding("b.py", 1, "cycle", "circular", "error", "fix"),
        ]
        report = format_import_report(findings)
        assert "1 error(s)" in report
        assert "2 warning(s)" in report


# ------------------------------------------------------------------
# Test scan with target
# ------------------------------------------------------------------

class TestScanTarget:
    def test_scan_specific_file(self, tmp_project):
        _write(tmp_project / "clean.py", """\
            import os
            os.getcwd()
        """)
        _write(tmp_project / "messy.py", """\
            import os
            import sys
            x = 1
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("clean.py")
        # Should only scan clean.py (plus circular which is project-wide)
        file_findings = [f for f in findings if f.issue != "circular"]
        assert all("clean.py" in f.file for f in file_findings) or len(file_findings) == 0

    def test_scan_directory(self, tmp_project):
        sub = tmp_project / "src"
        _write(sub / "a.py", """\
            import os
            x = 1
        """)
        _write(sub / "b.py", """\
            import sys
            y = 2
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("src")
        unused = [f for f in findings if f.issue == "unused"]
        assert len(unused) >= 2

    def test_scan_nonexistent(self, tmp_project):
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("nonexistent.py")
        # No crash, just empty
        assert findings == []


# ------------------------------------------------------------------
# Test edge cases
# ------------------------------------------------------------------

class TestEdgeCases:
    def test_syntax_error_file(self, tmp_project):
        _write(tmp_project / "broken.py", """\
            import os
            def foo(:
                pass
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("broken.py")
        # Should not crash, just skip
        assert isinstance(findings, list)

    def test_empty_file(self, tmp_project):
        _write(tmp_project / "empty.py", "")
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan("empty.py")
        assert findings == []

    def test_skip_hidden_dirs(self, tmp_project):
        _write(tmp_project / ".git" / "hook.py", """\
            import os
            x = 1
        """)
        _write(tmp_project / "app.py", """\
            import os
            os.getcwd()
        """)
        opt = ImportOptimizer(cwd=str(tmp_project))
        findings = opt.scan()
        # Should not include .git files
        git_findings = [f for f in findings if ".git" in f.file]
        assert len(git_findings) == 0

    def test_init_sets_cwd(self, tmp_project):
        opt = ImportOptimizer(cwd=str(tmp_project))
        assert opt.cwd == str(tmp_project)


# ------------------------------------------------------------------
# Test CLI command (basic smoke)
# ------------------------------------------------------------------

class TestCLICommand:
    def test_cmd_imports_help(self):
        from code_agents.cli.cli_imports import cmd_imports
        with patch("sys.argv", ["code-agents", "imports", "--help"]):
            cmd_imports()  # should not raise

    def test_cmd_imports_scan(self, tmp_project):
        from code_agents.cli.cli_imports import cmd_imports
        _write(tmp_project / "test_file.py", """\
            import os
            x = 1
        """)
        with patch("sys.argv", ["code-agents", "imports"]), \
             patch.dict(os.environ, {"TARGET_REPO_PATH": str(tmp_project)}):
            cmd_imports()  # should not raise
