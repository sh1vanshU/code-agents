"""Tech Debt Scanner — enhanced with effort estimates, priority scoring, ROI ranking.

Scans codebase for technical debt indicators, estimates remediation effort,
calculates priority scores based on severity and blast radius, and ranks
items by ROI (impact / effort).

Usage:
    from code_agents.reviews.techdebt_scanner import TechDebtScanner, TechDebtScannerConfig
    scanner = TechDebtScanner(TechDebtScannerConfig(cwd="/path/to/repo"))
    result = scanner.scan()
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.techdebt_scanner")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TechDebtScannerConfig:
    cwd: str = "."
    max_files: int = 500
    min_priority: int = 3  # 1-10 scale, filter out low priority


@dataclass
class TechDebtItem:
    """A single tech debt finding with effort and priority."""
    file: str
    line: int
    category: str  # "todo", "complexity", "duplication", "deprecated", "coupling", "missing_test"
    description: str
    severity: str = "medium"  # low | medium | high | critical
    effort_hours: float = 1.0  # estimated hours to fix
    impact_score: int = 5  # 1-10, how much fixing this improves the codebase
    priority_score: float = 0.0  # calculated: impact / effort
    code: str = ""
    suggestion: str = ""


@dataclass
class TechDebtScannerReport:
    """Full tech debt analysis with ROI ranking."""
    files_scanned: int = 0
    total_items: int = 0
    total_effort_hours: float = 0.0
    items: list[TechDebtItem] = field(default_factory=list)
    category_breakdown: dict[str, int] = field(default_factory=dict)
    top_roi: list[TechDebtItem] = field(default_factory=list)
    severity_breakdown: dict[str, int] = field(default_factory=dict)
    summary: str = ""


# ---------------------------------------------------------------------------
# Detection rules: (category, pattern, severity, effort_hours, impact, description, suggestion)
# ---------------------------------------------------------------------------

DEBT_RULES: list[dict] = [
    # TODOs and FIXMEs
    {
        "category": "todo",
        "pattern": re.compile(r"#\s*TODO\b", re.IGNORECASE),
        "severity": "low",
        "effort": 0.5,
        "impact": 3,
        "description": "Unresolved TODO comment",
        "suggestion": "Convert to a tracked ticket or resolve inline.",
    },
    {
        "category": "todo",
        "pattern": re.compile(r"#\s*FIXME\b", re.IGNORECASE),
        "severity": "medium",
        "effort": 1.0,
        "impact": 5,
        "description": "FIXME indicates known broken behaviour",
        "suggestion": "Fix the issue or create a high-priority ticket.",
    },
    {
        "category": "todo",
        "pattern": re.compile(r"#\s*HACK\b|#\s*XXX\b", re.IGNORECASE),
        "severity": "medium",
        "effort": 2.0,
        "impact": 6,
        "description": "HACK/XXX indicates fragile workaround",
        "suggestion": "Refactor to a proper solution.",
    },
    # Complexity
    {
        "category": "complexity",
        "pattern": re.compile(r"if\s+.+(?:\s+and\s+.+){3,}|if\s+.+(?:\s+or\s+.+){3,}"),
        "severity": "medium",
        "effort": 1.5,
        "impact": 5,
        "description": "Complex boolean expression — high cyclomatic complexity",
        "suggestion": "Extract to a named predicate function.",
    },
    {
        "category": "complexity",
        "pattern": re.compile(r"(?:elif\s+){4,}"),
        "severity": "high",
        "effort": 3.0,
        "impact": 7,
        "description": "Long elif chain — consider dispatch table or strategy pattern",
        "suggestion": "Refactor to dictionary dispatch or polymorphism.",
    },
    {
        "category": "complexity",
        "pattern": re.compile(r"^\s{16,}\S"),  # deep nesting
        "severity": "medium",
        "effort": 2.0,
        "impact": 5,
        "description": "Deeply nested code (4+ levels)",
        "suggestion": "Use early returns, extract helper methods, or flatten with guard clauses.",
    },
    # Deprecated
    {
        "category": "deprecated",
        "pattern": re.compile(r"@deprecated|DeprecationWarning|warnings\.warn"),
        "severity": "medium",
        "effort": 2.0,
        "impact": 4,
        "description": "Usage of deprecated API or deprecation warning",
        "suggestion": "Migrate to the recommended replacement.",
    },
    {
        "category": "deprecated",
        "pattern": re.compile(r"import\s+(?:imp|optparse|cgi)\b"),
        "severity": "medium",
        "effort": 1.5,
        "impact": 4,
        "description": "Import of deprecated stdlib module",
        "suggestion": "Replace imp->importlib, optparse->argparse, cgi->urllib.parse.",
    },
    # Coupling
    {
        "category": "coupling",
        "pattern": re.compile(r"^from\s+\S+\s+import\s+.+,.+,.+,.+,.+"),
        "severity": "medium",
        "effort": 3.0,
        "impact": 6,
        "description": "Heavy import coupling — importing 5+ names from one module",
        "suggestion": "Consider importing the module itself or splitting dependencies.",
    },
    {
        "category": "coupling",
        "pattern": re.compile(r"global\s+\w+"),
        "severity": "high",
        "effort": 2.5,
        "impact": 7,
        "description": "Global mutable state introduces hidden coupling",
        "suggestion": "Use dependency injection or module-level constants.",
    },
    # Missing error handling
    {
        "category": "error_handling",
        "pattern": re.compile(r"except\s*:\s*$|except\s+Exception\s*:"),
        "severity": "high",
        "effort": 1.0,
        "impact": 7,
        "description": "Bare except or broad Exception catch",
        "suggestion": "Catch specific exceptions, log errors.",
    },
    # Magic numbers
    {
        "category": "readability",
        "pattern": re.compile(r"(?<!=)\s*(?<!\w)[2-9]\d{2,}\s*(?!\w)"),
        "severity": "low",
        "effort": 0.5,
        "impact": 3,
        "description": "Magic number — use a named constant",
        "suggestion": "Extract to a well-named constant for clarity.",
    },
    # Long functions (heuristic: many lines between def)
    {
        "category": "complexity",
        "pattern": re.compile(r"def\s+\w+\s*\([^)]*\)\s*(?:->\s*\w+)?\s*:"),
        "severity": "low",  # upgraded dynamically if function is long
        "effort": 4.0,
        "impact": 6,
        "description": "Function detected — checked for length",
        "suggestion": "Split long functions (> 50 lines) into smaller, focused helpers.",
        "_is_func_check": True,
    },
]


# ---------------------------------------------------------------------------
# TechDebtScanner
# ---------------------------------------------------------------------------


class TechDebtScanner:
    """Scan codebase for tech debt with effort/priority/ROI analysis."""

    def __init__(self, config: Optional[TechDebtScannerConfig] = None):
        self.config = config or TechDebtScannerConfig()

    def scan(self) -> TechDebtScannerReport:
        """Run tech debt scan."""
        logger.info("Starting tech debt scan in %s", self.config.cwd)
        report = TechDebtScannerReport()
        root = Path(self.config.cwd)

        count = 0
        for ext in ("*.py", "*.js", "*.ts"):
            for fpath in root.rglob(ext):
                if count >= self.config.max_files:
                    break
                count += 1
                if any(p.startswith(".") or p in ("node_modules", "__pycache__", ".venv") for p in fpath.parts):
                    continue
                rel = str(fpath.relative_to(root))
                try:
                    lines = fpath.read_text(errors="replace").splitlines()
                except Exception:
                    continue
                self._scan_file(rel, lines, report)

        report.files_scanned = count

        # Calculate priority scores and sort by ROI
        for item in report.items:
            if item.effort_hours > 0:
                item.priority_score = round(item.impact_score / item.effort_hours, 2)

        # Filter by minimum priority
        report.items = [
            i for i in report.items if i.priority_score >= self.config.min_priority or i.severity in ("high", "critical")
        ]

        # Sort by priority (ROI) descending
        report.items.sort(key=lambda x: x.priority_score, reverse=True)
        report.top_roi = report.items[:10]

        # Tallies
        report.total_items = len(report.items)
        report.total_effort_hours = sum(i.effort_hours for i in report.items)

        for item in report.items:
            report.category_breakdown[item.category] = report.category_breakdown.get(item.category, 0) + 1
            report.severity_breakdown[item.severity] = report.severity_breakdown.get(item.severity, 0) + 1

        report.summary = (
            f"Scanned {report.files_scanned} files, {report.total_items} debt items, "
            f"~{report.total_effort_hours:.0f} hours estimated effort. "
            f"Top ROI: {report.top_roi[0].description if report.top_roi else 'none'}."
        )
        logger.info("Tech debt scan complete: %s", report.summary)
        return report

    def _scan_file(self, rel: str, lines: list[str], report: TechDebtScannerReport) -> None:
        """Scan a single file for tech debt."""
        func_start_lines: list[int] = []
        for idx, line in enumerate(lines, 1):
            for rule in DEBT_RULES:
                if rule.get("_is_func_check"):
                    if rule["pattern"].search(line):
                        func_start_lines.append(idx)
                    continue
                if rule["pattern"].search(line):
                    report.items.append(TechDebtItem(
                        file=rel, line=idx,
                        category=rule["category"],
                        description=rule["description"],
                        severity=rule["severity"],
                        effort_hours=rule["effort"],
                        impact_score=rule["impact"],
                        code=line.strip(),
                        suggestion=rule["suggestion"],
                    ))

        # Check function lengths
        for i, start in enumerate(func_start_lines):
            end = func_start_lines[i + 1] if i + 1 < len(func_start_lines) else len(lines)
            length = end - start
            if length > 50:
                report.items.append(TechDebtItem(
                    file=rel, line=start,
                    category="complexity",
                    description=f"Long function ({length} lines) — split into smaller helpers",
                    severity="high" if length > 100 else "medium",
                    effort_hours=4.0 if length > 100 else 2.0,
                    impact_score=7 if length > 100 else 5,
                    suggestion="Extract logical sections into well-named helper functions.",
                ))


def format_techdebt_report(report: TechDebtScannerReport) -> str:
    """Render tech debt report with ROI ranking."""
    lines = ["=== Tech Debt Scanner Report ===", ""]
    lines.append(f"Files scanned:     {report.files_scanned}")
    lines.append(f"Total items:       {report.total_items}")
    lines.append(f"Total effort:      ~{report.total_effort_hours:.0f} hours")
    lines.append("")

    if report.category_breakdown:
        lines.append("By category:")
        for cat, cnt in sorted(report.category_breakdown.items()):
            lines.append(f"  {cat}: {cnt}")
        lines.append("")

    if report.severity_breakdown:
        lines.append("By severity:")
        for sev, cnt in sorted(report.severity_breakdown.items()):
            lines.append(f"  {sev}: {cnt}")
        lines.append("")

    if report.top_roi:
        lines.append("--- Top ROI Items ---")
        for item in report.top_roi:
            lines.append(f"  [{item.severity.upper()}] {item.file}:{item.line} (ROI: {item.priority_score})")
            lines.append(f"    {item.description}")
            lines.append(f"    Effort: {item.effort_hours}h, Impact: {item.impact_score}/10")
            lines.append(f"    Fix: {item.suggestion}")
        lines.append("")

    lines.append(report.summary)
    return "\n".join(lines)
