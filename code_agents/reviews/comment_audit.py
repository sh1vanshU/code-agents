"""Comment Quality Analyzer — audit comments for staleness, obviousness, TODOs.

Scans source code comments for:
  - Obvious/redundant comments ("increment i", "return result")
  - TODO/FIXME without a ticket reference (JIRA-123, #123)
  - Large blocks of commented-out code
  - Outdated comments (heuristic: code changed recently, comment didn't)
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.comment_audit")

_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb",
    ".cs", ".php", ".rs", ".kt", ".scala", ".swift",
}

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".tox", "venv", ".venv",
    "dist", "build", ".eggs", "vendor", "third_party", ".mypy_cache",
    ".pytest_cache", "htmlcov", "site-packages",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CommentFinding:
    """A single comment quality issue."""
    file: str
    line: int
    category: str  # "obvious", "todo_no_ticket", "commented_code", "outdated"
    severity: str  # "low", "medium", "high"
    message: str
    comment_text: str = ""


@dataclass
class CommentAuditReport:
    """Full audit report."""
    findings: list[CommentFinding] = field(default_factory=list)
    files_scanned: int = 0
    total_comments: int = 0

    @property
    def by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.category] = counts.get(f.category, 0) + 1
        return counts

    @property
    def by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Obvious comment patterns
# ---------------------------------------------------------------------------

_OBVIOUS_PATTERNS = [
    re.compile(r"#\s*increment\s+\w+", re.IGNORECASE),
    re.compile(r"#\s*decrement\s+\w+", re.IGNORECASE),
    re.compile(r"#\s*return\s+(the\s+)?result", re.IGNORECASE),
    re.compile(r"#\s*return\s+(the\s+)?value", re.IGNORECASE),
    re.compile(r"#\s*set\s+\w+\s+to\s+", re.IGNORECASE),
    re.compile(r"#\s*initialize\s+\w+", re.IGNORECASE),
    re.compile(r"#\s*init\s+\w+", re.IGNORECASE),
    re.compile(r"#\s*create\s+(a\s+)?(new\s+)?\w+\s*(variable|var|list|dict|array|object)", re.IGNORECASE),
    re.compile(r"#\s*loop\s+(through|over)\s+", re.IGNORECASE),
    re.compile(r"#\s*iterate\s+(through|over)\s+", re.IGNORECASE),
    re.compile(r"#\s*check\s+if\s+\w+\s+is\s+(not\s+)?(None|null|empty|zero)", re.IGNORECASE),
    re.compile(r"#\s*import\s+\w+", re.IGNORECASE),
    re.compile(r"#\s*add\s+\w+\s+to\s+\w+", re.IGNORECASE),
    re.compile(r"#\s*open\s+(the\s+)?file", re.IGNORECASE),
    re.compile(r"#\s*close\s+(the\s+)?file", re.IGNORECASE),
    re.compile(r"#\s*print\s+(the\s+)?result", re.IGNORECASE),
    re.compile(r"#\s*call\s+(the\s+)?\w+\s*(function|method)?", re.IGNORECASE),
    re.compile(r"#\s*define\s+(a\s+)?(new\s+)?(function|method|class)", re.IGNORECASE),
    re.compile(r"#\s*constructor", re.IGNORECASE),
    re.compile(r"#\s*default\s+case", re.IGNORECASE),
    re.compile(r"#\s*else\s+case", re.IGNORECASE),
    re.compile(r"#\s*end\s+of\s+(loop|function|class|if|for|while)", re.IGNORECASE),
    # JS/TS style
    re.compile(r"//\s*increment\s+\w+", re.IGNORECASE),
    re.compile(r"//\s*return\s+(the\s+)?result", re.IGNORECASE),
    re.compile(r"//\s*return\s+(the\s+)?value", re.IGNORECASE),
    re.compile(r"//\s*set\s+\w+\s+to\s+", re.IGNORECASE),
    re.compile(r"//\s*loop\s+(through|over)\s+", re.IGNORECASE),
    re.compile(r"//\s*constructor", re.IGNORECASE),
]

# Ticket reference patterns
_TICKET_PATTERN = re.compile(
    r"[A-Z]{2,10}-\d+|#\d+|github\.com/\S+/issues/\d+|jira\.\S+/browse/\S+"
)

# Commented-out code patterns
_CODE_COMMENT_PATTERNS = [
    re.compile(r"^#\s*(def |class |import |from |if |for |while |return |try:|except|raise |with |yield )"),
    re.compile(r"^#\s*\w+\s*=\s*"),
    re.compile(r"^#\s*\w+\.\w+\("),
    re.compile(r"^#\s*print\("),
    re.compile(r"^//\s*(function |const |let |var |import |export |if |for |while |return |try |class )"),
    re.compile(r"^//\s*\w+\s*=\s*"),
    re.compile(r"^//\s*console\.\w+\("),
]


class CommentAuditor:
    """Audit code comments for quality issues."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._is_git = (Path(cwd) / ".git").is_dir()
        logger.info("CommentAuditor initialized for %s (git=%s)", cwd, self._is_git)

    def audit(self, target: str = "") -> CommentAuditReport:
        """Run full comment audit on the target path."""
        path = Path(self.cwd) / target if target else Path(self.cwd)
        report = CommentAuditReport()

        files = self._collect_files(path)
        report.files_scanned = len(files)
        logger.info("Auditing comments in %d files", len(files))

        for fpath in files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            rel = str(fpath.relative_to(self.cwd))
            lines = content.split("\n")

            report.findings.extend(self._check_obvious(rel, lines))
            report.findings.extend(self._check_todo_without_ticket(rel, lines))
            report.findings.extend(self._check_commented_code(rel, lines))
            if self._is_git:
                report.findings.extend(self._check_outdated(rel, fpath))

        logger.info(
            "Audit complete: %d findings in %d files",
            len(report.findings), report.files_scanned,
        )
        return report

    def _check_outdated(self, rel_path: str, fpath: Path) -> list[CommentFinding]:
        """Detect comments that may be outdated via git blame heuristics."""
        findings: list[CommentFinding] = []
        try:
            result = subprocess.run(
                ["git", "blame", "--line-porcelain", str(fpath)],
                capture_output=True, text=True, cwd=self.cwd, timeout=30,
            )
            if result.returncode != 0:
                return findings
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return findings

        blame_lines = result.stdout.split("\n")
        line_timestamps: dict[int, int] = {}
        current_line = 0
        current_ts = 0

        for bl in blame_lines:
            if bl.startswith("author-time "):
                try:
                    current_ts = int(bl.split(" ", 1)[1])
                except ValueError:
                    current_ts = 0
            elif bl.startswith("\t"):
                current_line += 1
                line_timestamps[current_line] = current_ts

        # Find comments near code that changed much later
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return findings

        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not (stripped.startswith("#") or stripped.startswith("//")):
                continue
            if stripped.startswith("#!"):
                continue

            comment_ts = line_timestamps.get(i, 0)
            if comment_ts == 0:
                continue

            # Check if adjacent code lines are much newer
            for offset in range(1, 4):
                neighbor = i + offset
                if neighbor > len(lines):
                    break
                neighbor_line = lines[neighbor - 1].strip()
                if not neighbor_line or neighbor_line.startswith("#") or neighbor_line.startswith("//"):
                    continue
                neighbor_ts = line_timestamps.get(neighbor, 0)
                if neighbor_ts == 0:
                    continue
                # If code is > 90 days newer than comment
                age_diff = neighbor_ts - comment_ts
                if age_diff > 90 * 86400:
                    findings.append(CommentFinding(
                        file=rel_path,
                        line=i,
                        category="outdated",
                        severity="medium",
                        message=f"Comment may be outdated — adjacent code changed {age_diff // 86400} days later",
                        comment_text=stripped[:80],
                    ))
                    break

        return findings

    def _check_obvious(self, rel_path: str, lines: list[str]) -> list[CommentFinding]:
        """Find obvious/redundant comments."""
        findings: list[CommentFinding] = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            for pat in _OBVIOUS_PATTERNS:
                if pat.search(stripped):
                    findings.append(CommentFinding(
                        file=rel_path,
                        line=i,
                        category="obvious",
                        severity="low",
                        message="Obvious/redundant comment — adds no information",
                        comment_text=stripped[:80],
                    ))
                    break
        return findings

    def _check_todo_without_ticket(self, rel_path: str, lines: list[str]) -> list[CommentFinding]:
        """Find TODO/FIXME/HACK/XXX without a ticket reference."""
        findings: list[CommentFinding] = []
        todo_pattern = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not (stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*")):
                continue
            if todo_pattern.search(stripped):
                if not _TICKET_PATTERN.search(stripped):
                    findings.append(CommentFinding(
                        file=rel_path,
                        line=i,
                        category="todo_no_ticket",
                        severity="medium",
                        message="TODO/FIXME without ticket reference (e.g. JIRA-123, #456)",
                        comment_text=stripped[:80],
                    ))
        return findings

    def _check_commented_code(self, rel_path: str, lines: list[str]) -> list[CommentFinding]:
        """Find blocks of commented-out code (3+ consecutive lines)."""
        findings: list[CommentFinding] = []
        consecutive = 0
        block_start = 0

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            is_code_comment = False
            for pat in _CODE_COMMENT_PATTERNS:
                if pat.match(stripped):
                    is_code_comment = True
                    break

            if is_code_comment:
                if consecutive == 0:
                    block_start = i
                consecutive += 1
            else:
                if consecutive >= 3:
                    findings.append(CommentFinding(
                        file=rel_path,
                        line=block_start,
                        category="commented_code",
                        severity="high",
                        message=f"Block of {consecutive} lines of commented-out code (L{block_start}-L{block_start + consecutive - 1})",
                        comment_text=lines[block_start - 1].strip()[:80],
                    ))
                consecutive = 0

        # Handle block at end of file
        if consecutive >= 3:
            findings.append(CommentFinding(
                file=rel_path,
                line=block_start,
                category="commented_code",
                severity="high",
                message=f"Block of {consecutive} lines of commented-out code (L{block_start}-L{block_start + consecutive - 1})",
                comment_text=lines[block_start - 1].strip()[:80],
            ))

        return findings

    def _collect_files(self, target: Path) -> list[Path]:
        """Collect source files for analysis."""
        if target.is_file() and target.suffix in _CODE_EXTENSIONS:
            return [target]
        if not target.is_dir():
            return []
        files: list[Path] = []
        for root, dirs, fnames in os.walk(target):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fn in fnames:
                if Path(fn).suffix in _CODE_EXTENSIONS:
                    files.append(Path(root) / fn)
        return sorted(files)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_comment_report(report: CommentAuditReport) -> str:
    """Format a human-readable comment audit report."""
    if not report.findings:
        return "  No comment quality issues found!"

    parts = [
        f"  Comment Audit: {len(report.findings)} findings in {report.files_scanned} files\n",
    ]

    category_labels = {
        "obvious": "Obvious/Redundant",
        "todo_no_ticket": "TODO without ticket",
        "commented_code": "Commented-out code",
        "outdated": "Potentially outdated",
    }

    for cat, count in sorted(report.by_category.items()):
        parts.append(f"    {category_labels.get(cat, cat)}: {count}")
    parts.append("")

    by_file: dict[str, list[CommentFinding]] = {}
    for f in report.findings:
        by_file.setdefault(f.file, []).append(f)

    for fpath, findings in sorted(by_file.items()):
        parts.append(f"  {fpath}")
        for f in sorted(findings, key=lambda x: x.line):
            sev_icon = {"high": "[!]", "medium": "[~]", "low": "[-]"}.get(f.severity, "[ ]")
            parts.append(f"    {sev_icon} L{f.line}: {f.message}")
            if f.comment_text:
                parts.append(f"        {f.comment_text}")
        parts.append("")

    return "\n".join(parts)


def comment_report_to_json(report: CommentAuditReport) -> dict:
    """Convert report to JSON-serializable dict."""
    return {
        "files_scanned": report.files_scanned,
        "total_findings": len(report.findings),
        "by_category": report.by_category,
        "by_severity": report.by_severity,
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "category": f.category,
                "severity": f.severity,
                "message": f.message,
                "comment_text": f.comment_text,
            }
            for f in report.findings
        ],
    }
