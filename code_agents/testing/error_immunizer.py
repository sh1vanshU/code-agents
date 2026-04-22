"""Error Immunizer — analyze bug fixes to auto-generate prevention checks."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.testing.error_immunizer")


@dataclass
class BugFix:
    """A bug fix with context."""
    commit_sha: str = ""
    file_path: str = ""
    description: str = ""
    diff_content: str = ""
    bug_class: str = ""  # null_deref, off_by_one, type_error, boundary, race, resource_leak
    lines_changed: list[int] = field(default_factory=list)


@dataclass
class PreventionCheck:
    """An auto-generated check to prevent a bug class."""
    name: str = ""
    bug_class: str = ""
    check_type: str = ""  # lint_rule, pre_commit_hook, test_case, assertion
    code: str = ""
    description: str = ""
    applies_to: list[str] = field(default_factory=list)  # file patterns
    confidence: float = 0.0


@dataclass
class ImmunizationReport:
    """Complete immunization report."""
    bugs_analyzed: int = 0
    bug_classes_found: dict[str, int] = field(default_factory=dict)
    prevention_checks: list[PreventionCheck] = field(default_factory=list)
    coverage_improvement: float = 0.0
    existing_coverage: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


BUG_CLASS_PATTERNS = {
    "null_deref": [
        re.compile(r"(?:is not none|is none|!= none|== none|if\s+\w+:)", re.IGNORECASE),
        re.compile(r"(?:nonetype|attributeerror|typeerror.*none)", re.IGNORECASE),
    ],
    "off_by_one": [
        re.compile(r"(?:len\(\w+\)\s*-\s*1|range\(.*,.*[+-]\s*1)", re.IGNORECASE),
        re.compile(r"(?:indexerror|index out of range)", re.IGNORECASE),
    ],
    "type_error": [
        re.compile(r"(?:int\(|str\(|float\(|isinstance)", re.IGNORECASE),
        re.compile(r"(?:typeerror|cannot.*convert|unexpected type)", re.IGNORECASE),
    ],
    "boundary": [
        re.compile(r"(?:max\(|min\(|clamp|boundary|limit|cap|floor|ceil)", re.IGNORECASE),
        re.compile(r"(?:overflow|underflow|exceeded|out of bounds)", re.IGNORECASE),
    ],
    "resource_leak": [
        re.compile(r"(?:with\s+open|\.close\(\)|finally:|__exit__)", re.IGNORECASE),
        re.compile(r"(?:resourcewarning|file descriptor|connection leak)", re.IGNORECASE),
    ],
    "race_condition": [
        re.compile(r"(?:lock\.|lock\(|synchronized|atomic|mutex)", re.IGNORECASE),
        re.compile(r"(?:race condition|concurrent|thread.safe)", re.IGNORECASE),
    ],
}

CHECK_TEMPLATES = {
    "null_deref": PreventionCheck(
        name="null_safety_check",
        check_type="lint_rule",
        code='def check_null_safety(node):\n    """Flag attribute access without None check."""\n    if node.type == "attribute" and not has_null_guard(node):\n        report("Potential None dereference", node.lineno)',
        description="Detect attribute access on potentially None values",
    ),
    "off_by_one": PreventionCheck(
        name="boundary_index_check",
        check_type="test_case",
        code='def test_boundary_indices(func, data):\n    """Test with empty, single-element, and edge indices."""\n    assert func([]) == expected_empty\n    assert func([1]) == expected_single\n    assert func(data, len(data) - 1) == expected_last',
        description="Test boundary conditions for index operations",
    ),
    "type_error": PreventionCheck(
        name="type_validation_check",
        check_type="assertion",
        code='def validate_types(**kwargs):\n    """Validate argument types at function entry."""\n    for name, (value, expected) in kwargs.items():\n        if not isinstance(value, expected):\n            raise TypeError(f"{name}: expected {expected}, got {type(value)}")',
        description="Runtime type validation at function boundaries",
    ),
    "boundary": PreventionCheck(
        name="boundary_value_check",
        check_type="pre_commit_hook",
        code='def check_numeric_bounds(code):\n    """Flag numeric operations without boundary checks."""\n    for op in find_arithmetic_ops(code):\n        if not has_bounds_check(op):\n            warn(f"Arithmetic at line {op.line} lacks bounds checking")',
        description="Detect arithmetic without bounds checking",
    ),
    "resource_leak": PreventionCheck(
        name="resource_cleanup_check",
        check_type="lint_rule",
        code='def check_resource_cleanup(node):\n    """Flag resource acquisition without context manager."""\n    if is_resource_open(node) and not in_with_block(node):\n        report("Resource opened without context manager", node.lineno)',
        description="Detect resources opened without context manager",
    ),
    "race_condition": PreventionCheck(
        name="thread_safety_check",
        check_type="lint_rule",
        code='def check_thread_safety(node):\n    """Flag shared mutable state without synchronization."""\n    if is_shared_state(node) and not has_lock(node):\n        report("Shared state access without lock", node.lineno)',
        description="Detect shared state access without synchronization",
    ),
}


class ErrorImmunizer:
    """Analyzes bug fixes and generates prevention checks."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, bug_fixes: list[dict],
                existing_checks: Optional[list[str]] = None) -> ImmunizationReport:
        """Analyze bug fixes and generate immunization checks."""
        logger.info("Analyzing %d bug fixes", len(bug_fixes))
        existing_checks = existing_checks or []

        fixes = [self._parse_fix(f) for f in bug_fixes]
        fixes = [f for f in fixes if f.bug_class]

        # Count bug classes
        class_counts: dict[str, int] = {}
        for fix in fixes:
            class_counts[fix.bug_class] = class_counts.get(fix.bug_class, 0) + 1

        # Generate prevention checks
        checks = []
        for bug_class, count in sorted(class_counts.items(), key=lambda x: -x[1]):
            check = self._generate_check(bug_class, count, fixes)
            if check and check.name not in existing_checks:
                checks.append(check)

        report = ImmunizationReport(
            bugs_analyzed=len(fixes),
            bug_classes_found=class_counts,
            prevention_checks=checks,
            coverage_improvement=len(checks) / max(len(class_counts), 1) * 100,
            existing_coverage=existing_checks,
            warnings=self._generate_warnings(class_counts, checks),
        )
        logger.info("Immunization: %d checks for %d bug classes", len(checks), len(class_counts))
        return report

    def _parse_fix(self, raw: dict) -> BugFix:
        """Parse a raw bug fix dict."""
        fix = BugFix(
            commit_sha=raw.get("sha", raw.get("commit", "")),
            file_path=raw.get("file", raw.get("file_path", "")),
            description=raw.get("description", raw.get("message", "")),
            diff_content=raw.get("diff", ""),
        )
        fix.bug_class = self._classify_bug(fix)
        return fix

    def _classify_bug(self, fix: BugFix) -> str:
        """Classify a bug fix into a bug class."""
        text = f"{fix.description} {fix.diff_content}".lower()
        best_class = ""
        best_score = 0
        for bug_class, patterns in BUG_CLASS_PATTERNS.items():
            score = sum(1 for p in patterns if p.search(text))
            if score > best_score:
                best_score = score
                best_class = bug_class
        return best_class

    def _generate_check(self, bug_class: str, count: int,
                        fixes: list[BugFix]) -> Optional[PreventionCheck]:
        """Generate a prevention check for a bug class."""
        template = CHECK_TEMPLATES.get(bug_class)
        if not template:
            return None

        affected_files = list(set(
            f.file_path for f in fixes if f.bug_class == bug_class and f.file_path
        ))

        return PreventionCheck(
            name=template.name,
            bug_class=bug_class,
            check_type=template.check_type,
            code=template.code,
            description=template.description,
            applies_to=affected_files[:10],
            confidence=min(0.9, 0.5 + count * 0.1),
        )

    def _generate_warnings(self, classes: dict[str, int],
                           checks: list[PreventionCheck]) -> list[str]:
        """Generate warnings."""
        warnings = []
        high_freq = {k: v for k, v in classes.items() if v >= 3}
        if high_freq:
            for k, v in high_freq.items():
                warnings.append(f"Recurring bug class '{k}' ({v} occurrences) — high priority for prevention")
        return warnings


def format_report(report: ImmunizationReport) -> str:
    """Format immunization report."""
    lines = [
        "# Error Immunization Report",
        f"Bugs analyzed: {report.bugs_analyzed}",
        f"Bug classes: {report.bug_classes_found}",
        f"Prevention checks: {len(report.prevention_checks)}",
        "",
    ]
    for check in report.prevention_checks:
        lines.append(f"## {check.name} ({check.bug_class})")
        lines.append(f"Type: {check.check_type} | Confidence: {check.confidence:.0%}")
        lines.append(f"  {check.description}")
    return "\n".join(lines)
