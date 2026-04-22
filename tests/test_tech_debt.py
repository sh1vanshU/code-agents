"""Tests for tech_debt.py — tech debt tracker."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.reviews.tech_debt import (
    TechDebtScanner,
    TechDebtTracker,
    DebtReport,
    DebtItem,
    format_debt_report,
    _DEBT_HISTORY_ROOT,
)


@pytest.fixture
def debt_repo(tmp_path):
    """Create a repo with various tech debt markers."""
    (tmp_path / "app.py").write_text(
        "import os\n"
        "\n"
        "# TODO: refactor this later\n"
        "def main():\n"
        "    pass\n"
        "\n"
        "# FIXME: broken on Windows\n"
        "def broken():\n"
        "    pass\n"
        "\n"
        "# HACK: workaround for API bug\n"
        "def workaround():\n"
        "    pass\n"
        "\n"
        "# XXX: this is terrible\n"
        "def terrible():\n"
        "    pass\n"
    )

    (tmp_path / "tests.py").write_text(
        "import pytest\n"
        "\n"
        "@pytest.mark.skip(reason='flaky')\n"
        "def test_flaky():\n"
        "    pass\n"
        "\n"
        "def test_ok():\n"
        "    x = 1  # noqa: E501\n"
        "    assert x == 1\n"
    )

    (tmp_path / "Service.java").write_text(
        "public class Service {\n"
        "    @Deprecated\n"
        "    public void oldMethod() {}\n"
        "\n"
        "    @SuppressWarnings(\"unchecked\")\n"
        "    public void unsafe() {}\n"
        "\n"
        "    // TODO: optimize this query\n"
        "    public void query() {}\n"
        "}\n"
    )

    return tmp_path


@pytest.fixture
def tracker_repo(tmp_path):
    """Create a repo for TechDebtTracker tests."""
    # Python file with TODO and FIXME
    src = tmp_path / "app.py"
    src.write_text(
        "# TODO: refactor this later\n"
        "def foo():\n"
        "    # FIXME: broken edge case\n"
        "    pass\n"
        "\n"
        "def bar():\n"
        "    pass\n"
        "\n"
        "# HACK: workaround for upstream bug\n"
        "def baz():\n"
        "    pass\n"
    )
    # Python file with complex function
    complex_src = tmp_path / "complex.py"
    body_lines = []
    for j in range(20):
        body_lines.append(f"    if x == {j}:\n        y = {j}\n")
    complex_src.write_text(
        "def mega_function(x):\n"
        "    y = 0\n"
        + "".join(body_lines)
        + "    return y\n"
    )
    # Test file for app.py
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_app.py"
    test_file.write_text("def test_foo():\n    pass\n")
    # No test for complex.py — should be flagged as test gap

    # pyproject.toml with a wildcard dep
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.poetry.dependencies]\n'
        'python = "^3.10"\n'
        'requests = "*"\n'
        'fastapi = "^0.100"\n'
    )
    return tmp_path


# ---------------------------------------------------------------------------
# DebtItem tests
# ---------------------------------------------------------------------------

class TestDebtItem:
    def test_creation(self):
        item = DebtItem(
            category="todo", file="app.py", line=10,
            description="TODO: fix this", effort="low",
        )
        assert item.category == "todo"
        assert item.file == "app.py"
        assert item.line == 10
        assert item.effort == "low"

    def test_defaults(self):
        item = DebtItem(category="dead_code", file="x.py", line=1, description="unused")
        assert item.effort == "low"
        assert item.tag == ""
        assert item.severity == "low"


# ---------------------------------------------------------------------------
# DebtReport tests
# ---------------------------------------------------------------------------

class TestDebtReport:
    def test_empty_report(self):
        report = DebtReport()
        assert report.score == 100
        assert report.items == []
        assert report.by_category == {}
        assert report.total_score == 0

    def test_total_score_calculation(self):
        report = DebtReport(items=[
            DebtItem(category="todo", file="a.py", line=1, description="", effort="low", severity="low"),
            DebtItem(category="todo", file="b.py", line=2, description="", effort="medium", severity="medium"),
            DebtItem(category="todo", file="c.py", line=3, description="", effort="high", severity="high"),
        ])
        # low=1 + medium=3 + high=5 = 9
        assert report.total_score == 9

    def test_by_file(self):
        report = DebtReport(items=[
            DebtItem(category="todo", file="a.py", line=1, description="x"),
            DebtItem(category="todo", file="a.py", line=5, description="y"),
            DebtItem(category="todo", file="b.py", line=1, description="z"),
        ])
        by_file = report.by_file
        assert len(by_file["a.py"]) == 2
        assert len(by_file["b.py"]) == 1


# ---------------------------------------------------------------------------
# TechDebtScanner (legacy compat) tests
# ---------------------------------------------------------------------------

class TestTechDebtScanner:
    """Tests for TechDebtScanner."""

    def test_scan_finds_todos(self, debt_repo):
        scanner = TechDebtScanner(cwd=str(debt_repo))
        report = scanner.scan()
        todos = [i for i in report.items if i.category == "todo"]
        assert len(todos) >= 4  # TODO, FIXME, HACK, XXX + Java TODO

    def test_scan_returns_debt_report(self, debt_repo):
        scanner = TechDebtScanner(cwd=str(debt_repo))
        report = scanner.scan()
        assert isinstance(report, DebtReport)
        assert len(report.items) > 0

    def test_debt_score(self, debt_repo):
        scanner = TechDebtScanner(cwd=str(debt_repo))
        report = scanner.scan()
        assert report.total_score > 0

    def test_by_category(self, debt_repo):
        scanner = TechDebtScanner(cwd=str(debt_repo))
        report = scanner.scan()
        by_cat = report.by_category
        assert isinstance(by_cat, dict)
        assert "todo" in by_cat

    def test_empty_repo(self, tmp_path):
        scanner = TechDebtScanner(cwd=str(tmp_path))
        report = scanner.scan()
        assert len(report.items) == 0
        assert report.total_score == 0


# ---------------------------------------------------------------------------
# TechDebtTracker tests
# ---------------------------------------------------------------------------

class TestTechDebtTracker:
    def test_scan_todos(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        todo_items = [i for i in report.items if i.category == "todo"]
        assert len(todo_items) >= 3  # TODO, FIXME, HACK
        tags = {i.tag for i in todo_items}
        assert "TODO" in tags
        assert "FIXME" in tags
        assert "HACK" in tags

    def test_scan_complexity(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        complex_items = [i for i in report.items if i.category == "complexity"]
        assert len(complex_items) >= 1
        assert "mega_function" in complex_items[0].description

    def test_scan_test_gaps(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        gap_items = [i for i in report.items if i.category == "test_gap"]
        gap_files = [i.file for i in gap_items]
        assert any("complex.py" in f for f in gap_files)

    def test_scan_outdated_deps(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        dep_items = [i for i in report.items if i.category == "outdated_dep"]
        assert len(dep_items) >= 1
        assert any("requests" in i.description for i in dep_items)

    def test_scan_dead_code(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        dead_items = [i for i in report.items if i.category == "dead_code"]
        names = [i.description for i in dead_items]
        assert any("bar" in n or "baz" in n for n in names)

    def test_score_empty(self, tmp_path):
        tracker = TechDebtTracker(cwd=str(tmp_path))
        report = tracker.scan()
        assert report.score == 100
        assert report.items == []

    def test_score_not_empty(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        assert 0 <= report.score <= 100
        assert report.score < 100

    def test_by_category_populated(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        assert "todo" in report.by_category
        assert report.by_category["todo"] >= 3

    def test_prioritized_sorted(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        assert len(report.prioritized) > 0
        first = report.prioritized[0]
        assert first.effort in ("low", "medium", "high")

    def test_trend_no_previous(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        assert report.trend.get("has_previous") is False

    def test_save_and_load_trend(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        tracker.save_snapshot(report)
        trend = tracker._load_trend(report.score, report.items)
        assert trend["has_previous"] is True
        assert trend["score_delta"] == 0

    def test_save_snapshot_creates_file(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        tracker.save_snapshot(report)
        snapshot_dir = _DEBT_HISTORY_ROOT / tracker._repo_hash
        snapshots = list(snapshot_dir.glob("*.json"))
        assert len(snapshots) >= 1
        data = json.loads(snapshots[0].read_text())
        assert "score" in data
        assert "total_items" in data


# ---------------------------------------------------------------------------
# Complexity calculation tests
# ---------------------------------------------------------------------------

class TestCyclomaticComplexity:
    def test_simple_function(self):
        import ast
        code = "def foo():\n    return 1\n"
        tree = ast.parse(code)
        func = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)][0]
        cc = TechDebtTracker._cyclomatic_complexity(func)
        assert cc == 1

    def test_if_branches(self):
        import ast
        code = "def foo(x):\n    if x > 0:\n        return 1\n    elif x < 0:\n        return -1\n    return 0\n"
        tree = ast.parse(code)
        func = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)][0]
        cc = TechDebtTracker._cyclomatic_complexity(func)
        assert cc >= 2

    def test_for_loop(self):
        import ast
        code = "def foo(xs):\n    for x in xs:\n        if x:\n            pass\n"
        tree = ast.parse(code)
        func = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)][0]
        cc = TechDebtTracker._cyclomatic_complexity(func)
        assert cc >= 3


# ---------------------------------------------------------------------------
# Formatting tests
# ---------------------------------------------------------------------------

class TestFormatDebtReport:
    """Tests for format_debt_report."""

    def test_format_with_data(self, debt_repo):
        scanner = TechDebtScanner(cwd=str(debt_repo))
        report = scanner.scan()
        output = format_debt_report(report)
        assert "Tech Debt Report" in output
        assert "Total items" in output

    def test_format_empty(self):
        report = DebtReport(repo_path="/tmp")
        output = format_debt_report(report)
        assert "No tech debt markers found" in output

    def test_format_shows_categories(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        output = format_debt_report(report)
        assert "TODO" in output
        assert "Top files by debt" in output

    def test_format_shows_priorities(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        output = format_debt_report(report)
        assert "Top priorities" in output

    def test_trend_display(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        tracker.save_snapshot(report)
        report2 = tracker.scan()
        output = format_debt_report(report2)
        assert "Trend" in output

    def test_format_health_score(self, tracker_repo):
        tracker = TechDebtTracker(cwd=str(tracker_repo))
        report = tracker.scan()
        output = format_debt_report(report)
        assert "Health Score" in output
        assert "/100" in output


# ---------------------------------------------------------------------------
# Package.json scanning tests
# ---------------------------------------------------------------------------

class TestPackageJsonScan:
    def test_wildcard_dep(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "dependencies": {"lodash": "*", "express": "^4.0.0"},
            "devDependencies": {"jest": "latest"},
        }))
        tracker = TechDebtTracker(cwd=str(tmp_path))
        items = tracker._scan_package_json(str(pkg))
        assert len(items) == 2
        descs = [i.description for i in items]
        assert any("lodash" in d for d in descs)
        assert any("jest" in d for d in descs)

    def test_no_wildcards(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "dependencies": {"express": "^4.18.0"},
        }))
        tracker = TechDebtTracker(cwd=str(tmp_path))
        items = tracker._scan_package_json(str(pkg))
        assert len(items) == 0


# ---------------------------------------------------------------------------
# Requirements.txt scanning tests
# ---------------------------------------------------------------------------

class TestRequirementsTxtScan:
    def test_unpinned_deps(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("flask\nrequests==2.31.0\nnumpy\n")
        tracker = TechDebtTracker(cwd=str(tmp_path))
        items = tracker._scan_requirements_txt(str(req))
        assert len(items) == 2
        descs = [i.description for i in items]
        assert any("flask" in d for d in descs)
        assert any("numpy" in d for d in descs)

    def test_all_pinned(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("flask==2.3.0\nrequests>=2.28.0\n")
        tracker = TechDebtTracker(cwd=str(tmp_path))
        items = tracker._scan_requirements_txt(str(req))
        assert len(items) == 0


# ---------------------------------------------------------------------------
# CLI command test
# ---------------------------------------------------------------------------

class TestCLITechDebt:
    def test_cmd_runs(self, tracker_repo, capsys):
        with patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": str(tracker_repo)}):
            from code_agents.cli.cli_tech_debt import cmd_tech_debt
            cmd_tech_debt([])
        captured = capsys.readouterr()
        assert "Tech Debt Tracker" in captured.out

    def test_cmd_json(self, tracker_repo, capsys):
        with patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": str(tracker_repo)}):
            from code_agents.cli.cli_tech_debt import cmd_tech_debt
            cmd_tech_debt(["--json"])
        captured = capsys.readouterr()
        # Extract JSON from output (after header lines)
        output_lines = captured.out.strip().split("\n")
        json_start = None
        for idx, line in enumerate(output_lines):
            if line.strip().startswith("{"):
                json_start = idx
                break
        assert json_start is not None
        json_text = "\n".join(output_lines[json_start:])
        data = json.loads(json_text)
        assert "score" in data
        assert "items" in data
