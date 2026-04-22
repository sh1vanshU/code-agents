"""Architecture Drift Detector — monitor for violations of intended design rules."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.analysis.arch_drift_detector")


@dataclass
class ArchRule:
    """An architectural rule to enforce."""
    id: str = ""
    name: str = ""
    description: str = ""
    rule_type: str = ""  # dependency, naming, layer, pattern
    source_pattern: str = ""  # regex for files this rule applies to
    constraint: str = ""  # the actual constraint
    severity: str = "warning"  # info, warning, error


@dataclass
class Violation:
    """A detected architectural violation."""
    rule_id: str = ""
    rule_name: str = ""
    file_path: str = ""
    line_number: int = 0
    description: str = ""
    severity: str = "warning"
    suggestion: str = ""


@dataclass
class DriftReport:
    """Complete architecture drift report."""
    rules_checked: int = 0
    violations: list[Violation] = field(default_factory=list)
    compliant_files: int = 0
    non_compliant_files: int = 0
    drift_score: float = 0.0  # 0.0 = fully compliant, 1.0 = fully drifted
    rules_summary: dict[str, int] = field(default_factory=dict)  # rule_id -> violation count
    warnings: list[str] = field(default_factory=list)


# Default architectural rules
DEFAULT_RULES = [
    ArchRule(
        id="no_circular_imports",
        name="No Circular Imports",
        rule_type="dependency",
        source_pattern=r".*\.py$",
        constraint="no_circular",
        severity="error",
    ),
    ArchRule(
        id="layer_separation",
        name="Layer Separation",
        description="Routers should not import from CLI; CLI should not import from routers",
        rule_type="layer",
        source_pattern=r"routers/.*\.py$",
        constraint="no_import:cli",
        severity="error",
    ),
    ArchRule(
        id="no_direct_db_in_router",
        name="No Direct DB in Router",
        description="Routers should use service layer, not direct DB access",
        rule_type="layer",
        source_pattern=r"routers/.*\.py$",
        constraint="no_import:sqlalchemy,psycopg2,pymongo",
        severity="warning",
    ),
    ArchRule(
        id="test_naming",
        name="Test File Naming",
        description="Test files must start with test_",
        rule_type="naming",
        source_pattern=r"tests/.*\.py$",
        constraint="filename:test_*",
        severity="warning",
    ),
    ArchRule(
        id="no_print_in_lib",
        name="No Print in Library Code",
        description="Library code should use logging, not print",
        rule_type="pattern",
        source_pattern=r"code_agents/.*\.py$",
        constraint="no_pattern:^\\s*print\\(",
        severity="info",
    ),
]

IMPORT_PATTERN = re.compile(r"^(?:from\s+(\S+)|import\s+(\S+))", re.MULTILINE)


class ArchDriftDetector:
    """Detects architectural drift from intended design rules."""

    def __init__(self, cwd: str, custom_rules: Optional[list[ArchRule]] = None):
        self.cwd = cwd
        self.rules = (custom_rules or []) + DEFAULT_RULES

    def analyze(self, file_contents: dict[str, str]) -> DriftReport:
        """Analyze codebase for architectural drift."""
        logger.info("Checking %d files against %d rules", len(file_contents), len(self.rules))

        violations = []
        files_with_violations: set[str] = set()
        rules_summary: dict[str, int] = {}

        for rule in self.rules:
            rule_violations = self._check_rule(rule, file_contents)
            violations.extend(rule_violations)
            rules_summary[rule.id] = len(rule_violations)
            for v in rule_violations:
                files_with_violations.add(v.file_path)

        compliant = len(file_contents) - len(files_with_violations)
        total = len(file_contents)
        drift = len(files_with_violations) / total if total else 0.0

        report = DriftReport(
            rules_checked=len(self.rules),
            violations=violations,
            compliant_files=compliant,
            non_compliant_files=len(files_with_violations),
            drift_score=round(drift, 3),
            rules_summary=rules_summary,
            warnings=self._generate_warnings(violations, drift),
        )
        logger.info("Drift report: %.1f%% drift, %d violations", drift * 100, len(violations))
        return report

    def _check_rule(self, rule: ArchRule, file_contents: dict[str, str]) -> list[Violation]:
        """Check a single rule against all matching files."""
        violations = []
        source_re = re.compile(rule.source_pattern)

        for fpath, content in file_contents.items():
            if not source_re.search(fpath):
                continue

            if rule.rule_type == "dependency" or rule.rule_type == "layer":
                violations.extend(self._check_import_rule(rule, fpath, content))
            elif rule.rule_type == "naming":
                violations.extend(self._check_naming_rule(rule, fpath))
            elif rule.rule_type == "pattern":
                violations.extend(self._check_pattern_rule(rule, fpath, content))

        return violations

    def _check_import_rule(self, rule: ArchRule, fpath: str, content: str) -> list[Violation]:
        """Check import-based rules."""
        violations = []
        constraint = rule.constraint

        if constraint.startswith("no_import:"):
            forbidden = constraint.split(":", 1)[1].split(",")
            for m in IMPORT_PATTERN.finditer(content):
                imported = m.group(1) or m.group(2) or ""
                for forbidden_mod in forbidden:
                    if forbidden_mod.strip() in imported:
                        line_num = content[:m.start()].count("\n") + 1
                        violations.append(Violation(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            file_path=fpath,
                            line_number=line_num,
                            description=f"Forbidden import '{imported}' (rule: {rule.name})",
                            severity=rule.severity,
                            suggestion=f"Remove import of '{forbidden_mod.strip()}'; use the service layer instead",
                        ))
        return violations

    def _check_naming_rule(self, rule: ArchRule, fpath: str) -> list[Violation]:
        """Check naming convention rules."""
        violations = []
        constraint = rule.constraint

        if constraint.startswith("filename:"):
            pattern = constraint.split(":", 1)[1].replace("*", ".*")
            import os
            basename = os.path.basename(fpath)
            if not re.match(pattern, basename):
                violations.append(Violation(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    file_path=fpath,
                    description=f"File '{basename}' doesn't match pattern '{constraint.split(':', 1)[1]}'",
                    severity=rule.severity,
                    suggestion=f"Rename to match pattern: {constraint.split(':', 1)[1]}",
                ))
        return violations

    def _check_pattern_rule(self, rule: ArchRule, fpath: str, content: str) -> list[Violation]:
        """Check code pattern rules."""
        violations = []
        constraint = rule.constraint

        if constraint.startswith("no_pattern:"):
            pattern = constraint.split(":", 1)[1]
            pat_re = re.compile(pattern, re.MULTILINE)
            for m in pat_re.finditer(content):
                line_num = content[:m.start()].count("\n") + 1
                violations.append(Violation(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    file_path=fpath,
                    line_number=line_num,
                    description=f"Pattern violation: {rule.description or rule.name}",
                    severity=rule.severity,
                    suggestion="Replace with logger.info() or appropriate logging call",
                ))
        return violations

    def _generate_warnings(self, violations: list[Violation], drift: float) -> list[str]:
        """Generate high-level warnings."""
        warnings = []
        if drift > 0.3:
            warnings.append(f"High drift ({drift:.0%}) — architecture review recommended")
        errors = [v for v in violations if v.severity == "error"]
        if errors:
            warnings.append(f"{len(errors)} error-level violations need immediate attention")
        return warnings


def format_report(report: DriftReport) -> str:
    """Format drift report as text."""
    lines = [
        "# Architecture Drift Report",
        f"Drift Score: {report.drift_score:.1%}",
        f"Rules: {report.rules_checked} | Violations: {len(report.violations)}",
        f"Compliant: {report.compliant_files} | Non-compliant: {report.non_compliant_files}",
        "",
    ]
    for v in report.violations[:30]:
        lines.append(f"  [{v.severity}] {v.file_path}:{v.line_number} — {v.description}")
    return "\n".join(lines)
