"""Tests for deadcode.py — dead code finder static analysis."""

import os
import tempfile
from pathlib import Path

import pytest

from code_agents.analysis.deadcode import DeadCodeFinder, DeadCodeReport, format_deadcode_report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def python_repo(tmp_path):
    """Create a minimal Python repo with unused imports and functions."""
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'demo'\n")

    # File with unused import
    (tmp_path / "app.py").write_text(
        "import os\n"
        "import json\n"
        "\n"
        "def main():\n"
        "    path = os.getcwd()\n"
        "    print(path)\n"
    )

    # File with unused private function
    (tmp_path / "utils.py").write_text(
        "def public_func():\n"
        "    return 42\n"
        "\n"
        "def _unused_helper():\n"
        "    return 99\n"
        "\n"
        "def _used_helper():\n"
        "    return 1\n"
        "\n"
        "def caller():\n"
        "    return _used_helper()\n"
    )

    # File with from-import unused
    (tmp_path / "models.py").write_text(
        "from pathlib import Path, PurePath\n"
        "\n"
        "def get_home():\n"
        "    return Path.home()\n"
    )

    return tmp_path


@pytest.fixture
def java_repo(tmp_path):
    """Create a minimal Java repo."""
    (tmp_path / "pom.xml").write_text("<project></project>")

    src = tmp_path / "src" / "main"
    src.mkdir(parents=True)
    (src / "App.java").write_text(
        "import java.util.List;\n"
        "import java.util.Map;\n"
        "\n"
        "public class App {\n"
        "    public void run() {\n"
        "        List<String> items = new ArrayList<>();\n"
        "    }\n"
        "    private void unusedMethod() {\n"
        "        System.out.println(\"never called\");\n"
        "    }\n"
        "}\n"
    )
    return tmp_path


@pytest.fixture
def js_repo(tmp_path):
    """Create a minimal JS repo."""
    (tmp_path / "package.json").write_text('{"name": "demo"}')
    (tmp_path / "index.js").write_text(
        "import { useState, useEffect } from 'react';\n"
        "\n"
        "function App() {\n"
        "  const [x, setX] = useState(0);\n"
        "  return x;\n"
        "}\n"
    )
    return tmp_path


@pytest.fixture
def go_repo(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/demo\n")
    return tmp_path


@pytest.fixture
def endpoint_repo(tmp_path):
    """Repo with FastAPI endpoints, one orphan."""
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'api'\n")
    (tmp_path / "router.py").write_text(
        'from fastapi import APIRouter\n'
        'router = APIRouter()\n'
        '\n'
        '@router.get("/health")\n'
        'def health():\n'
        '    return {"ok": True}\n'
        '\n'
        '@router.post("/internal/orphan-action")\n'
        'def orphan():\n'
        '    return {"done": True}\n'
    )
    # A client that calls /health
    (tmp_path / "client.py").write_text(
        'import httpx\n'
        'def check():\n'
        '    return httpx.get("http://localhost/health")\n'
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

class TestLanguageDetection:
    def test_detect_python(self, python_repo):
        finder = DeadCodeFinder(str(python_repo))
        assert finder.language == "python"

    def test_detect_java(self, java_repo):
        finder = DeadCodeFinder(str(java_repo))
        assert finder.language == "java"

    def test_detect_javascript(self, js_repo):
        finder = DeadCodeFinder(str(js_repo))
        assert finder.language == "javascript"

    def test_detect_go(self, go_repo):
        finder = DeadCodeFinder(str(go_repo))
        assert finder.language == "go"

    def test_detect_unknown(self, tmp_path):
        finder = DeadCodeFinder(str(tmp_path))
        assert finder.language == "unknown"

    def test_language_override(self, python_repo):
        finder = DeadCodeFinder(str(python_repo), language="java")
        assert finder.language == "java"


# ---------------------------------------------------------------------------
# _name_used_in_file
# ---------------------------------------------------------------------------

class TestNameUsedInFile:
    def test_name_used(self):
        source = "import os\npath = os.getcwd()\n"
        assert DeadCodeFinder._name_used_in_file("os", source, 1) is True

    def test_name_not_used(self):
        source = "import json\npath = 'hello'\n"
        assert DeadCodeFinder._name_used_in_file("json", source, 1) is False

    def test_ignores_comments(self):
        source = "import json\n# json is great\npath = 'x'\n"
        assert DeadCodeFinder._name_used_in_file("json", source, 1) is False

    def test_same_line_skipped(self):
        source = "import os\n"
        assert DeadCodeFinder._name_used_in_file("os", source, 1) is False

    def test_partial_match_rejected(self):
        source = "import os\nostriches = 5\n"
        # "os" should not match "ostriches" because of word boundary
        assert DeadCodeFinder._name_used_in_file("os", source, 1) is False


# ---------------------------------------------------------------------------
# Python scanning
# ---------------------------------------------------------------------------

class TestScanPython:
    def test_unused_import_detected(self, python_repo):
        finder = DeadCodeFinder(str(python_repo))
        report = finder.scan()
        unused_names = [i["import"] for i in report.unused_imports]
        assert "json" in unused_names

    def test_used_import_not_flagged(self, python_repo):
        finder = DeadCodeFinder(str(python_repo))
        report = finder.scan()
        unused_names = [i["import"] for i in report.unused_imports]
        assert "os" not in unused_names

    def test_unused_private_function(self, python_repo):
        finder = DeadCodeFinder(str(python_repo))
        report = finder.scan()
        unused_fns = [f["name"] for f in report.unused_functions]
        assert "_unused_helper" in unused_fns

    def test_used_private_function_not_flagged(self, python_repo):
        finder = DeadCodeFinder(str(python_repo))
        report = finder.scan()
        unused_fns = [f["name"] for f in report.unused_functions]
        assert "_used_helper" not in unused_fns

    def test_from_import_unused(self, python_repo):
        finder = DeadCodeFinder(str(python_repo))
        report = finder.scan()
        unused_names = [i["import"] for i in report.unused_imports]
        assert any("PurePath" in name for name in unused_names)

    def test_total_dead_lines_counted(self, python_repo):
        finder = DeadCodeFinder(str(python_repo))
        report = finder.scan()
        assert report.total_dead_lines > 0
        assert report.total_dead_lines == (
            len(report.unused_imports)
            + len(report.unused_functions)
            + len(report.unused_classes)
            + len(report.orphan_endpoints)
            + len(report.unused_variables)
        )


# ---------------------------------------------------------------------------
# Java scanning
# ---------------------------------------------------------------------------

class TestScanJava:
    def test_unused_java_import(self, java_repo):
        finder = DeadCodeFinder(str(java_repo))
        report = finder.scan()
        unused_names = [i["import"] for i in report.unused_imports]
        assert "java.util.Map" in unused_names

    def test_unused_java_private_method(self, java_repo):
        finder = DeadCodeFinder(str(java_repo))
        report = finder.scan()
        unused_fns = [f["name"] for f in report.unused_functions]
        assert "unusedMethod" in unused_fns


# ---------------------------------------------------------------------------
# JS scanning
# ---------------------------------------------------------------------------

class TestScanJs:
    def test_unused_js_import(self, js_repo):
        finder = DeadCodeFinder(str(js_repo))
        report = finder.scan()
        unused_names = [i["import"] for i in report.unused_imports]
        assert "useEffect" in unused_names

    def test_used_js_import_not_flagged(self, js_repo):
        finder = DeadCodeFinder(str(js_repo))
        report = finder.scan()
        unused_names = [i["import"] for i in report.unused_imports]
        assert "useState" not in unused_names


# ---------------------------------------------------------------------------
# Orphan endpoints
# ---------------------------------------------------------------------------

class TestOrphanEndpoints:
    def test_orphan_detected(self, endpoint_repo):
        finder = DeadCodeFinder(str(endpoint_repo))
        report = finder.scan()
        orphan_routes = [e["route"] for e in report.orphan_endpoints]
        assert any("orphan-action" in r for r in orphan_routes)

    def test_used_endpoint_not_flagged(self, endpoint_repo):
        finder = DeadCodeFinder(str(endpoint_repo))
        report = finder.scan()
        orphan_routes = [e["route"] for e in report.orphan_endpoints]
        assert not any("/health" in r for r in orphan_routes)


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_format_with_issues(self, python_repo):
        finder = DeadCodeFinder(str(python_repo))
        report = finder.scan()
        text = format_deadcode_report(report)
        assert "DEAD CODE REPORT" in text
        assert "Unused Imports" in text
        assert "Issues:" in text

    def test_format_clean_repo(self, tmp_path):
        report = DeadCodeReport(repo_path=str(tmp_path), language="python", total_dead_lines=0)
        text = format_deadcode_report(report)
        assert "No dead code detected" in text

    def test_format_truncation(self):
        """Reports with >20 items show '... and N more'."""
        items = [{"file": "f.py", "import": f"mod{i}", "line": i} for i in range(25)]
        report = DeadCodeReport(
            repo_path="/tmp/test", language="python",
            unused_imports=items, total_dead_lines=25,
        )
        text = format_deadcode_report(report)
        assert "and 5 more" in text


# ---------------------------------------------------------------------------
# DeadCodeReport dataclass
# ---------------------------------------------------------------------------

class TestDeadCodeReport:
    def test_defaults(self):
        report = DeadCodeReport(repo_path="/tmp", language="python")
        assert report.unused_imports == []
        assert report.unused_functions == []
        assert report.unused_classes == []
        assert report.orphan_endpoints == []
        assert report.unused_variables == []
        assert report.total_dead_lines == 0

    def test_fields_independent(self):
        """Each instance gets its own lists (no shared mutable defaults)."""
        r1 = DeadCodeReport(repo_path="/a", language="python")
        r2 = DeadCodeReport(repo_path="/b", language="java")
        r1.unused_imports.append({"file": "x.py", "import": "os", "line": 1})
        assert len(r2.unused_imports) == 0
