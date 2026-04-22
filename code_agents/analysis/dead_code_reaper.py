"""Dead Code Reaper — combine runtime coverage + feature flags to find truly dead code."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.analysis.dead_code_reaper")


@dataclass
class CodeSegment:
    """A segment of code being analyzed."""
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    name: str = ""
    kind: str = ""  # function, class, method, module
    lines_of_code: int = 0


@dataclass
class ReaperCandidate:
    """A candidate for removal."""
    segment: CodeSegment = field(default_factory=CodeSegment)
    confidence: float = 0.0  # 0.0 to 1.0
    reasons: list[str] = field(default_factory=list)
    behind_feature_flag: Optional[str] = None
    last_executed: Optional[str] = None  # timestamp or "never"
    removal_risk: str = "low"  # low, medium, high
    estimated_savings_loc: int = 0


@dataclass
class ReaperReport:
    """Complete dead code reaping report."""
    candidates: list[ReaperCandidate] = field(default_factory=list)
    total_loc_analyzed: int = 0
    dead_loc: int = 0
    dead_percentage: float = 0.0
    feature_flags_found: list[str] = field(default_factory=list)
    safe_to_remove: list[ReaperCandidate] = field(default_factory=list)
    needs_review: list[ReaperCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


FUNC_PATTERN = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)", re.MULTILINE)
CLASS_PATTERN = re.compile(r"^\s*class\s+(\w+)", re.MULTILINE)
FLAG_PATTERNS = [
    re.compile(r"feature_flag\s*\(\s*['\"](\w+)['\"]\s*\)"),
    re.compile(r"is_enabled\s*\(\s*['\"](\w+)['\"]\s*\)"),
    re.compile(r"FEATURE_(\w+)\s*="),
    re.compile(r"toggle\s*\(\s*['\"](\w+)['\"]\s*\)"),
]
IMPORT_PATTERN = re.compile(r"(?:from\s+\S+\s+)?import\s+.+")


class DeadCodeReaper:
    """Combines static analysis, runtime coverage, and feature flags to find dead code."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, file_contents: dict[str, str],
                coverage_data: Optional[dict] = None,
                feature_flags: Optional[dict] = None) -> ReaperReport:
        """Analyze codebase for truly dead code."""
        logger.info("Analyzing %d files for dead code", len(file_contents))

        coverage_data = coverage_data or {}
        feature_flags = feature_flags or {}

        all_segments = []
        all_references: dict[str, set] = {}  # name -> set of files referencing it
        all_flags: set[str] = set()
        total_loc = 0

        # Phase 1: Extract segments and references
        for fpath, content in file_contents.items():
            lines = content.splitlines()
            total_loc += len(lines)

            segments = self._extract_segments(fpath, content)
            all_segments.extend(segments)

            # Build reference map
            for other_path, other_content in file_contents.items():
                if other_path == fpath:
                    continue
                for seg in segments:
                    if seg.name in other_content:
                        all_references.setdefault(seg.name, set()).add(other_path)

            # Extract feature flags
            for pattern in FLAG_PATTERNS:
                for m in pattern.finditer(content):
                    all_flags.add(m.group(1))

        # Phase 2: Score each segment
        candidates = []
        for seg in all_segments:
            candidate = self._score_segment(
                seg, all_references, coverage_data, feature_flags
            )
            if candidate.confidence > 0.3:
                candidates.append(candidate)

        # Phase 3: Classify
        safe = [c for c in candidates if c.confidence >= 0.8 and c.removal_risk == "low"]
        review = [c for c in candidates if c not in safe]

        dead_loc = sum(c.estimated_savings_loc for c in candidates)
        report = ReaperReport(
            candidates=sorted(candidates, key=lambda c: -c.confidence),
            total_loc_analyzed=total_loc,
            dead_loc=dead_loc,
            dead_percentage=(dead_loc / total_loc * 100) if total_loc else 0.0,
            feature_flags_found=sorted(all_flags),
            safe_to_remove=safe,
            needs_review=review,
            warnings=self._generate_warnings(candidates),
        )
        logger.info(
            "Found %d dead code candidates (%d LOC, %.1f%%)",
            len(candidates), dead_loc, report.dead_percentage,
        )
        return report

    def _extract_segments(self, fpath: str, content: str) -> list[CodeSegment]:
        """Extract functions and classes from file."""
        segments = []
        lines = content.splitlines()

        for m in FUNC_PATTERN.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            end_line = self._find_block_end(lines, line_num - 1)
            segments.append(CodeSegment(
                file_path=fpath, start_line=line_num, end_line=end_line,
                name=m.group(1), kind="function",
                lines_of_code=end_line - line_num + 1,
            ))

        for m in CLASS_PATTERN.finditer(content):
            line_num = content[:m.start()].count("\n") + 1
            end_line = self._find_block_end(lines, line_num - 1)
            segments.append(CodeSegment(
                file_path=fpath, start_line=line_num, end_line=end_line,
                name=m.group(1), kind="class",
                lines_of_code=end_line - line_num + 1,
            ))

        return segments

    def _find_block_end(self, lines: list[str], start_idx: int) -> int:
        """Find the end of a code block by indentation."""
        if start_idx >= len(lines):
            return start_idx + 1
        indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        for i in range(start_idx + 1, min(start_idx + 500, len(lines))):
            line = lines[i]
            if line.strip() and not line.strip().startswith("#"):
                line_indent = len(line) - len(line.lstrip())
                if line_indent <= indent:
                    return i
        return min(start_idx + 10, len(lines))

    def _score_segment(self, seg: CodeSegment, references: dict[str, set],
                       coverage: dict, flags: dict) -> ReaperCandidate:
        """Score a segment for deadness."""
        reasons = []
        confidence = 0.0

        # Check references
        refs = references.get(seg.name, set())
        if not refs:
            confidence += 0.4
            reasons.append("No cross-file references found")
        elif len(refs) == 1:
            confidence += 0.1
            reasons.append(f"Only referenced in 1 file: {list(refs)[0]}")

        # Check coverage
        file_cov = coverage.get(seg.file_path, {})
        if file_cov:
            covered_lines = set(file_cov.get("covered", []))
            seg_lines = set(range(seg.start_line, seg.end_line + 1))
            overlap = seg_lines & covered_lines
            if not overlap:
                confidence += 0.3
                reasons.append("Zero runtime coverage")
            elif len(overlap) / len(seg_lines) < 0.1:
                confidence += 0.15
                reasons.append(f"Very low coverage ({len(overlap)}/{len(seg_lines)} lines)")
        else:
            confidence += 0.1
            reasons.append("No coverage data available for file")

        # Check feature flags
        flag_name = None
        for flag, state in flags.items():
            if flag.lower() in seg.name.lower():
                flag_name = flag
                if not state:
                    confidence += 0.2
                    reasons.append(f"Behind disabled feature flag: {flag}")
                break

        # Private/underscore prefix
        if seg.name.startswith("_") and not seg.name.startswith("__"):
            confidence += 0.1
            reasons.append("Private function/class")

        confidence = min(confidence, 1.0)

        # Determine risk
        risk = "low"
        if seg.kind == "class":
            risk = "medium"
        if refs and len(refs) > 2:
            risk = "high"
        if seg.name.startswith("__"):
            risk = "high"

        return ReaperCandidate(
            segment=seg,
            confidence=round(confidence, 2),
            reasons=reasons,
            behind_feature_flag=flag_name,
            last_executed="never" if not file_cov else None,
            removal_risk=risk,
            estimated_savings_loc=seg.lines_of_code,
        )

    def _generate_warnings(self, candidates: list[ReaperCandidate]) -> list[str]:
        """Generate warnings."""
        warnings = []
        high_risk = [c for c in candidates if c.removal_risk == "high"]
        if high_risk:
            warnings.append(f"{len(high_risk)} high-risk candidates — review carefully")
        dunder = [c for c in candidates if c.segment.name.startswith("__")]
        if dunder:
            warnings.append(f"{len(dunder)} dunder methods flagged — likely false positives")
        return warnings


def format_report(report: ReaperReport) -> str:
    """Format reaper report."""
    lines = [
        "# Dead Code Reaper Report",
        f"Analyzed: {report.total_loc_analyzed} LOC",
        f"Dead: {report.dead_loc} LOC ({report.dead_percentage:.1f}%)",
        f"Safe to remove: {len(report.safe_to_remove)}",
        f"Needs review: {len(report.needs_review)}",
        "",
    ]
    for c in report.candidates[:20]:
        lines.append(
            f"[{c.confidence:.0%}] {c.segment.kind} {c.segment.name} "
            f"({c.segment.file_path}:{c.segment.start_line}) - {c.removal_risk} risk"
        )
        for r in c.reasons:
            lines.append(f"  - {r}")
        lines.append("")
    return "\n".join(lines)
