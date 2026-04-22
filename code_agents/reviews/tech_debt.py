"""Tech Debt Tracker — scans for TODOs, FIXMEs, complexity, test gaps, outdated deps, dead code."""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.tech_debt")

_SKIP_DIRS = frozenset({
    '.git', '__pycache__', 'venv', '.venv', 'node_modules',
    '.tox', 'dist', 'build', '.eggs', 'target', '.gradle', '.mvn', '.next',
})

_SOURCE_EXTS = frozenset({
    '.py', '.java', '.js', '.ts', '.jsx', '.tsx', '.go', '.kt', '.scala',
    '.rb', '.rs', '.c', '.cpp', '.h', '.hpp', '.cs',
})

# Patterns for debt categories
_TODO_PATTERN = re.compile(r'#\s*(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)', re.IGNORECASE)
_TODO_BLOCK_PATTERN = re.compile(r'//\s*(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)', re.IGNORECASE)
_TODO_MULTILINE_PATTERN = re.compile(r'\*\s*(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)', re.IGNORECASE)
_DEPRECATED_PATTERN = re.compile(r'@[Dd]eprecated')
_SUPPRESS_PATTERN = re.compile(r'@SuppressWarnings')
_SKIP_TEST_PY = re.compile(r'@pytest\.mark\.skip|pytest\.skip\(|@unittest\.skip')
_SKIP_TEST_JAVA = re.compile(r'@(?:Ignore|Disabled)')
_NOQA_PATTERN = re.compile(r'#\s*noqa|//\s*noinspection|//\s*eslint-disable|/\*\s*eslint-disable')

_DEBT_HISTORY_ROOT = Path.home() / ".code-agents" / "debt-history"
_COMPLEXITY_THRESHOLD = 15


@dataclass
class DebtItem:
    """A single tech debt item."""

    category: str  # "todo", "complexity", "duplication", "test_gap", "outdated_dep", "dead_code", "deprecated", "suppress", "skipped_test", "lint_disable"
    file: str
    line: int
    description: str
    effort: str = "low"  # "low", "medium", "high"

    # Legacy compat fields (used by TechDebtScanner)
    tag: str = ""
    content: str = ""
    severity: str = "low"


@dataclass
class DebtReport:
    """Full tech debt report."""

    score: int = 100  # 0-100 (100=debt-free)
    items: list[DebtItem] = field(default_factory=list)
    by_category: dict[str, int] = field(default_factory=dict)
    trend: dict = field(default_factory=dict)
    prioritized: list[DebtItem] = field(default_factory=list)
    repo_path: str = ""

    @property
    def total_score(self) -> int:
        """Legacy compat: weighted score."""
        weights = {"low": 1, "medium": 3, "high": 5}
        return sum(weights.get(item.severity or item.effort, 1) for item in self.items)

    @property
    def by_file(self) -> dict[str, list[DebtItem]]:
        groups: dict[str, list[DebtItem]] = {}
        for item in self.items:
            groups.setdefault(item.file, []).append(item)
        return groups


# ---------------------------------------------------------------------------
# TechDebtTracker — the enhanced tracker (new)
# ---------------------------------------------------------------------------

class TechDebtTracker:
    """Full tech debt tracker with scoring, trend, and prioritization."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._repo_hash = hashlib.sha256(cwd.encode()).hexdigest()[:12]
        logger.info("TechDebtTracker initialized — repo=%s", cwd)

    def scan(self) -> DebtReport:
        """Run all debt scanners and produce a scored, prioritized report."""
        logger.info("Starting full tech debt scan for %s", self.cwd)
        items: list[DebtItem] = []
        items.extend(self._count_todos())
        items.extend(self._measure_complexity())
        items.extend(self._check_test_gaps())
        items.extend(self._check_outdated_deps())
        items.extend(self._check_dead_code())

        score = self._calculate_score(items)
        prioritized = self._prioritize_payoff(items)
        trend = self._load_trend(score, items)

        by_category: dict[str, int] = {}
        for item in items:
            by_category[item.category] = by_category.get(item.category, 0) + 1

        return DebtReport(
            score=score,
            items=items,
            by_category=by_category,
            trend=trend,
            prioritized=prioritized,
            repo_path=self.cwd,
        )

    # --- Scanners ---

    def _iter_source_files(self):
        """Yield (rel_path, abs_path) for all source files."""
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1]
                if ext not in _SOURCE_EXTS:
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, self.cwd)
                yield rel, fpath

    def _count_todos(self) -> list[DebtItem]:
        """Grep for TODO, FIXME, HACK, XXX across codebase."""
        items: list[DebtItem] = []
        patterns = [_TODO_PATTERN, _TODO_BLOCK_PATTERN, _TODO_MULTILINE_PATTERN]
        for rel, fpath in self._iter_source_files():
            try:
                source = Path(fpath).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(source.split("\n"), 1):
                for pat in patterns:
                    m = pat.search(line)
                    if m:
                        tag = m.group(1).upper()
                        content = m.group(2).strip()
                        effort = "medium" if tag in ("FIXME", "HACK") else "low"
                        items.append(DebtItem(
                            category="todo", file=rel, line=i,
                            description=f"{tag}: {content}" if content else tag,
                            effort=effort, tag=tag, content=content,
                            severity=effort,
                        ))
                        break
        logger.info("Found %d TODO/FIXME items", len(items))
        return items

    def _measure_complexity(self) -> list[DebtItem]:
        """Find Python functions with cyclomatic complexity > threshold."""
        items: list[DebtItem] = []
        for rel, fpath in self._iter_source_files():
            if not fpath.endswith(".py"):
                continue
            try:
                source = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source, filename=rel)
            except (SyntaxError, OSError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cc = self._cyclomatic_complexity(node)
                    if cc > _COMPLEXITY_THRESHOLD:
                        effort = "high" if cc > 30 else "medium"
                        items.append(DebtItem(
                            category="complexity", file=rel,
                            line=node.lineno,
                            description=f"Function '{node.name}' has cyclomatic complexity {cc} (>{_COMPLEXITY_THRESHOLD})",
                            effort=effort, severity=effort,
                        ))
        logger.info("Found %d high-complexity functions", len(items))
        return items

    @staticmethod
    def _cyclomatic_complexity(node: ast.AST) -> int:
        """Calculate cyclomatic complexity of an AST node."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                # each and/or adds a branch
                complexity += len(child.values) - 1
            elif isinstance(child, ast.Assert):
                complexity += 1
            elif isinstance(child, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                complexity += 1
        return complexity

    def _check_test_gaps(self) -> list[DebtItem]:
        """Find source files without corresponding test files."""
        items: list[DebtItem] = []
        source_files: set[str] = set()
        test_files: set[str] = set()

        for rel, _fpath in self._iter_source_files():
            if not rel.endswith(".py"):
                continue
            basename = os.path.basename(rel)
            if basename.startswith("test_") or basename.endswith("_test.py"):
                # strip test_ prefix or _test suffix to get the module name
                name = basename
                if name.startswith("test_"):
                    name = name[5:]
                elif name.endswith("_test.py"):
                    name = name[:-8] + ".py"
                test_files.add(name)
            elif not basename.startswith("__"):
                source_files.add(rel)

        for src in sorted(source_files):
            basename = os.path.basename(src)
            if basename in test_files:
                continue
            # Also check if test_<module>.py exists
            module_name = basename
            if module_name not in test_files:
                items.append(DebtItem(
                    category="test_gap", file=src, line=0,
                    description=f"No test file found for '{basename}'",
                    effort="medium", severity="medium",
                ))

        logger.info("Found %d files without tests", len(items))
        return items

    def _check_outdated_deps(self) -> list[DebtItem]:
        """Parse pyproject.toml/package.json for unpinned or loose version constraints."""
        items: list[DebtItem] = []

        # Check pyproject.toml
        pyproject = os.path.join(self.cwd, "pyproject.toml")
        if os.path.isfile(pyproject):
            items.extend(self._scan_pyproject(pyproject))

        # Check package.json
        pkgjson = os.path.join(self.cwd, "package.json")
        if os.path.isfile(pkgjson):
            items.extend(self._scan_package_json(pkgjson))

        # Check requirements.txt
        reqtxt = os.path.join(self.cwd, "requirements.txt")
        if os.path.isfile(reqtxt):
            items.extend(self._scan_requirements_txt(reqtxt))

        logger.info("Found %d dependency concerns", len(items))
        return items

    def _scan_pyproject(self, path: str) -> list[DebtItem]:
        """Scan pyproject.toml for wildcard or unpinned deps."""
        items: list[DebtItem] = []
        try:
            content = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return items

        in_deps = False
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("[tool.poetry.dependencies]") or stripped.startswith("[project.dependencies]"):
                in_deps = True
                continue
            if stripped.startswith("[") and in_deps:
                in_deps = False
                continue
            if in_deps and "=" in stripped and not stripped.startswith("#"):
                # Check for wildcard versions like "*"
                if '"*"' in stripped or "'*'" in stripped:
                    pkg = stripped.split("=")[0].strip().strip('"').strip("'")
                    items.append(DebtItem(
                        category="outdated_dep", file="pyproject.toml", line=i,
                        description=f"Unpinned dependency: {pkg} = \"*\"",
                        effort="low", severity="low",
                    ))
        return items

    def _scan_package_json(self, path: str) -> list[DebtItem]:
        """Scan package.json for wildcard version ranges."""
        items: list[DebtItem] = []
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            return items

        for section in ("dependencies", "devDependencies"):
            deps = data.get(section, {})
            for pkg, ver in deps.items():
                if ver in ("*", "latest"):
                    items.append(DebtItem(
                        category="outdated_dep", file="package.json", line=0,
                        description=f"Unpinned dependency: {pkg}@{ver} in {section}",
                        effort="low", severity="low",
                    ))
        return items

    def _scan_requirements_txt(self, path: str) -> list[DebtItem]:
        """Scan requirements.txt for unpinned deps (no ==)."""
        items: list[DebtItem] = []
        try:
            lines = Path(path).read_text(encoding="utf-8", errors="ignore").split("\n")
        except OSError:
            return items

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue
            if "==" not in stripped and ">=" not in stripped and "<=" not in stripped:
                pkg = re.split(r'[><!~]', stripped)[0].strip()
                if pkg:
                    items.append(DebtItem(
                        category="outdated_dep", file="requirements.txt", line=i,
                        description=f"Unpinned dependency: {pkg} (no version constraint)",
                        effort="low", severity="low",
                    ))
        return items

    def _check_dead_code(self) -> list[DebtItem]:
        """Quick scan: Python functions defined but never imported/referenced elsewhere."""
        items: list[DebtItem] = []
        defined: list[tuple[str, str, int]] = []  # (func_name, file, line)
        all_source = ""

        py_files: list[tuple[str, str]] = []
        for rel, fpath in self._iter_source_files():
            if not fpath.endswith(".py"):
                continue
            py_files.append((rel, fpath))

        # Collect all defined top-level functions
        for rel, fpath in py_files:
            try:
                source = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                all_source += source + "\n"
                tree = ast.parse(source, filename=rel)
            except (SyntaxError, OSError):
                continue
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = node.name
                    # Skip private/dunder/test functions
                    if name.startswith("_") or name.startswith("test"):
                        continue
                    defined.append((name, rel, node.lineno))

        # Check which names appear only once in the entire codebase
        for func_name, rel, lineno in defined:
            # Count occurrences: must appear at least twice (definition + usage)
            pattern = re.compile(r'\b' + re.escape(func_name) + r'\b')
            matches = pattern.findall(all_source)
            if len(matches) <= 1:
                items.append(DebtItem(
                    category="dead_code", file=rel, line=lineno,
                    description=f"Function '{func_name}' defined but never referenced",
                    effort="low", severity="low",
                ))

        logger.info("Found %d potential dead code items", len(items))
        return items

    # --- Scoring & Prioritization ---

    def _calculate_score(self, items: list[DebtItem]) -> int:
        """Calculate debt score 0-100 (100 = debt-free)."""
        if not items:
            return 100
        weights = {"low": 1, "medium": 3, "high": 5}
        total_weight = sum(weights.get(item.effort, 1) for item in items)
        # Normalize: 0 items = 100, 500+ weighted = 0
        score = max(0, 100 - int(total_weight * 100 / 500))
        return min(100, score)

    def _prioritize_payoff(self, items: list[DebtItem]) -> list[DebtItem]:
        """Sort by ROI: effort low + severity high = highest priority."""
        effort_rank = {"low": 0, "medium": 1, "high": 2}
        severity_rank = {"high": 0, "medium": 1, "low": 2}

        def sort_key(item: DebtItem):
            # Lower effort + higher severity = higher priority (lower sort key)
            e = effort_rank.get(item.effort, 1)
            s = severity_rank.get(item.severity or item.effort, 1)
            return (e, s, item.file, item.line)

        return sorted(items, key=sort_key)

    # --- Snapshots & Trend ---

    def save_snapshot(self, report: Optional[DebtReport] = None) -> None:
        """Save report to ~/.code-agents/debt-history/<repo-hash>/<date>.json."""
        if report is None:
            report = self.scan()
        snapshot_dir = _DEBT_HISTORY_ROOT / self._repo_hash
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file = snapshot_dir / f"{date.today().isoformat()}.json"

        data = {
            "date": date.today().isoformat(),
            "repo_path": self.cwd,
            "score": report.score,
            "total_items": len(report.items),
            "by_category": report.by_category,
            "items": [asdict(i) for i in report.items],
        }
        snapshot_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Saved debt snapshot to %s", snapshot_file)

    def _load_trend(self, current_score: int = 0, current_items: list[DebtItem] | None = None) -> dict:
        """Compare with last snapshot: score_delta, new_items, resolved."""
        snapshot_dir = _DEBT_HISTORY_ROOT / self._repo_hash
        if not snapshot_dir.is_dir():
            return {"has_previous": False}

        snapshots = sorted(snapshot_dir.glob("*.json"), reverse=True)
        if not snapshots:
            return {"has_previous": False}

        # Load the most recent snapshot
        try:
            prev_data = json.loads(snapshots[0].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"has_previous": False}

        prev_score = prev_data.get("score", 0)
        prev_total = prev_data.get("total_items", 0)
        curr_total = len(current_items) if current_items else 0

        return {
            "has_previous": True,
            "previous_date": prev_data.get("date", "unknown"),
            "previous_score": prev_score,
            "score_delta": current_score - prev_score,
            "previous_items": prev_total,
            "items_delta": curr_total - prev_total,
            "new_items": max(0, curr_total - prev_total),
            "resolved": max(0, prev_total - curr_total),
        }


# ---------------------------------------------------------------------------
# TechDebtScanner — Legacy compat (wraps TechDebtTracker)
# ---------------------------------------------------------------------------

class TechDebtScanner:
    """Scans a repository for tech debt markers (legacy interface, delegates to TechDebtTracker)."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._tracker = TechDebtTracker(cwd)
        self.report = DebtReport(repo_path=cwd)
        logger.info("TechDebtScanner initialized — repo=%s", cwd)

    def scan(self) -> DebtReport:
        """Scan all source files for tech debt markers."""
        return self._tracker.scan()


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_debt_report(report: DebtReport) -> str:
    """Format tech debt report grouped by category with severity and trend."""
    lines: list[str] = []
    lines.append("")
    lines.append("  Tech Debt Report")
    lines.append("  " + "=" * 60)
    lines.append("")

    if not report.items:
        lines.append("  No tech debt markers found. Clean codebase!")
        return "\n".join(lines)

    # Health score
    lines.append(f"  Health Score: {report.score}/100")
    if report.trend.get("has_previous"):
        delta = report.trend.get("score_delta", 0)
        arrow = "+" if delta > 0 else ""
        lines.append(f"  Trend: {arrow}{delta} vs {report.trend.get('previous_date', '?')} "
                      f"(resolved {report.trend.get('resolved', 0)}, new {report.trend.get('new_items', 0)})")
    lines.append("")

    category_labels = {
        "todo": "TODO / FIXME / HACK / XXX",
        "complexity": "High Complexity Functions",
        "test_gap": "Missing Test Files",
        "outdated_dep": "Dependency Concerns",
        "dead_code": "Potentially Dead Code",
        "deprecated": "@Deprecated Usage",
        "suppress": "@SuppressWarnings",
        "skipped_test": "Skipped Tests",
        "lint_disable": "Disabled Linting (noqa / eslint-disable)",
        "duplication": "Code Duplication",
    }

    severity_icons = {"high": "[!]", "medium": "[~]", "low": "[-]"}

    # Group items by category
    by_cat: dict[str, list[DebtItem]] = {}
    for item in report.items:
        by_cat.setdefault(item.category, []).append(item)

    for cat, label in category_labels.items():
        cat_items = by_cat.get(cat, [])
        if not cat_items:
            continue
        lines.append(f"  {label} ({len(cat_items)})")
        lines.append("  " + "-" * 50)
        for item in cat_items[:20]:
            icon = severity_icons.get(item.effort, "[-]")
            desc = item.description[:70] if item.description else item.category
            if item.line > 0:
                lines.append(f"    {icon} {item.file}:{item.line} — {desc}")
            else:
                lines.append(f"    {icon} {item.file} — {desc}")
        if len(cat_items) > 20:
            lines.append(f"    ... and {len(cat_items) - 20} more")
        lines.append("")

    # Summary
    lines.append(f"  Total items: {len(report.items)}")
    lines.append(f"  Score: {report.score}/100")
    high = sum(1 for i in report.items if i.effort == "high")
    med = sum(1 for i in report.items if i.effort == "medium")
    low = sum(1 for i in report.items if i.effort == "low")
    lines.append(f"  Effort: {high} high, {med} medium, {low} low")

    # Category summary
    if report.by_category:
        lines.append("")
        lines.append("  By category:")
        for cat, count in sorted(report.by_category.items(), key=lambda x: -x[1]):
            label = category_labels.get(cat, cat)
            lines.append(f"    {label}: {count}")

    # Top files
    by_file = report.by_file
    top_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)[:5]
    if top_files:
        lines.append("")
        lines.append("  Top files by debt:")
        for f, fitems in top_files:
            lines.append(f"    {f}: {len(fitems)} items")

    # Top priorities
    if report.prioritized:
        lines.append("")
        lines.append("  Top priorities (highest ROI):")
        for item in report.prioritized[:5]:
            desc = item.description[:60]
            lines.append(f"    [{item.effort}] {item.file}:{item.line} — {desc}")

    return "\n".join(lines)
