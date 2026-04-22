"""
JaCoCo XML parser — extract coverage data from JaCoCo reports.

Parses target/site/jacoco/jacoco.xml (Maven) or build/reports/jacoco/test/jacocoTestReport.xml (Gradle).
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.jacoco_parser")


@dataclass
class ClassCoverage:
    name: str
    package: str = ""
    line_covered: int = 0
    line_missed: int = 0
    branch_covered: int = 0
    branch_missed: int = 0
    method_covered: int = 0
    method_missed: int = 0

    @property
    def line_total(self) -> int:
        return self.line_covered + self.line_missed

    @property
    def line_pct(self) -> float:
        return (self.line_covered / self.line_total * 100) if self.line_total > 0 else 0.0

    @property
    def branch_pct(self) -> float:
        total = self.branch_covered + self.branch_missed
        return (self.branch_covered / total * 100) if total > 0 else 0.0

    @property
    def full_name(self) -> str:
        return f"{self.package}.{self.name}" if self.package else self.name


@dataclass
class CoverageReport:
    classes: list[ClassCoverage] = field(default_factory=list)
    total_line_covered: int = 0
    total_line_missed: int = 0
    total_branch_covered: int = 0
    total_branch_missed: int = 0

    @property
    def line_pct(self) -> float:
        total = self.total_line_covered + self.total_line_missed
        return (self.total_line_covered / total * 100) if total > 0 else 0.0

    @property
    def branch_pct(self) -> float:
        total = self.total_branch_covered + self.total_branch_missed
        return (self.total_branch_covered / total * 100) if total > 0 else 0.0

    @property
    def class_count(self) -> int:
        return len(self.classes)


def parse_jacoco_xml(xml_path: str) -> Optional[CoverageReport]:
    """Parse a JaCoCo XML report file."""
    path = Path(xml_path)
    if not path.is_file():
        logger.warning("JaCoCo XML not found: %s", xml_path)
        return None

    try:
        tree = ET.parse(str(path))
        root = tree.getroot()
    except ET.ParseError as e:
        logger.error("Failed to parse JaCoCo XML: %s", e)
        return None

    report = CoverageReport()

    for package in root.findall(".//package"):
        pkg_name = package.get("name", "").replace("/", ".")

        for cls in package.findall("class"):
            cls_name = cls.get("name", "").split("/")[-1]
            cc = ClassCoverage(name=cls_name, package=pkg_name)

            for counter in cls.findall("counter"):
                ctype = counter.get("type", "")
                covered = int(counter.get("covered", 0))
                missed = int(counter.get("missed", 0))

                if ctype == "LINE":
                    cc.line_covered = covered
                    cc.line_missed = missed
                elif ctype == "BRANCH":
                    cc.branch_covered = covered
                    cc.branch_missed = missed
                elif ctype == "METHOD":
                    cc.method_covered = covered
                    cc.method_missed = missed

            report.classes.append(cc)

    # Totals from root counters
    for counter in root.findall("counter"):
        ctype = counter.get("type", "")
        covered = int(counter.get("covered", 0))
        missed = int(counter.get("missed", 0))

        if ctype == "LINE":
            report.total_line_covered = covered
            report.total_line_missed = missed
        elif ctype == "BRANCH":
            report.total_branch_covered = covered
            report.total_branch_missed = missed

    # Sort by line coverage ascending (worst first)
    report.classes.sort(key=lambda c: c.line_pct)

    logger.info("Parsed JaCoCo: %d classes, %.1f%% line coverage", report.class_count, report.line_pct)
    return report


def find_jacoco_xml(repo_path: str) -> Optional[str]:
    """Find JaCoCo XML report in common locations."""
    candidates = [
        "target/site/jacoco/jacoco.xml",
        "build/reports/jacoco/test/jacocoTestReport.xml",
        "target/jacoco.xml",
    ]
    for candidate in candidates:
        path = Path(repo_path) / candidate
        if path.is_file():
            return str(path)
    # Search recursively
    for xml in Path(repo_path).rglob("jacoco*.xml"):
        if "site" in str(xml) or "reports" in str(xml):
            return str(xml)
    return None


def get_uncovered_methods(report: CoverageReport, threshold: float = 80.0) -> list[dict]:
    """Get classes below threshold with their uncovered stats."""
    below = []
    for cc in report.classes:
        if cc.line_pct < threshold and cc.line_total > 0:
            below.append({
                "class": cc.full_name,
                "line_pct": round(cc.line_pct, 1),
                "branch_pct": round(cc.branch_pct, 1),
                "lines_to_cover": cc.line_missed,
                "branches_to_cover": cc.branch_missed,
            })
    return below


def format_coverage_report(report: CoverageReport, threshold: float = 80.0) -> str:
    """Format coverage report as a readable table."""
    if not report:
        return "No coverage data available."

    lines = [
        "",
        f"Overall: {report.line_pct:.1f}% line, {report.branch_pct:.1f}% branch ({report.class_count} classes)",
        "",
        f"{'Class':<45} {'Line':>6} {'Branch':>8} {'Status':>8}",
        "\u2500" * 70,
    ]

    for cc in report.classes:
        if cc.line_total == 0:
            continue
        status = "\u2705" if cc.line_pct >= threshold else "\u274c"
        lines.append(f"{cc.full_name:<45} {cc.line_pct:>5.1f}% {cc.branch_pct:>7.1f}% {status:>6}")

    below_count = sum(1 for c in report.classes if c.line_pct < threshold and c.line_total > 0)
    lines.append("")
    lines.append(f"Below {threshold}%: {below_count} classes")
    lines.append(f"Target: {threshold}% | Current: {report.line_pct:.1f}%")

    return "\n".join(lines)


def coverage_meets_threshold(report: CoverageReport, threshold: float = 80.0) -> bool:
    """Check if overall coverage meets threshold."""
    return report.line_pct >= threshold
