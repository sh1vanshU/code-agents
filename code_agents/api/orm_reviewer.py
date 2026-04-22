"""ORM Reviewer — analyze ORM code for N+1 queries, missing eager loads, transaction issues.

Scans Python ORM code (SQLAlchemy, Django, Peewee) for common performance
and correctness anti-patterns.

Usage:
    from code_agents.api.orm_reviewer import OrmReviewer
    reviewer = OrmReviewer(OrmReviewConfig(cwd="/path/to/repo"))
    result = reviewer.scan()
    print(format_orm_review(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.api.orm_reviewer")


@dataclass
class OrmReviewConfig:
    cwd: str = "."
    max_files: int = 300


@dataclass
class OrmFinding:
    file: str
    line: int
    pattern: str  # "n_plus_1", "missing_eager_load", "no_transaction", "raw_sql", "missing_index", "lazy_in_loop"
    severity: str
    description: str
    suggestion: str
    code: str = ""


@dataclass
class OrmReviewResult:
    files_scanned: int = 0
    findings: list[OrmFinding] = field(default_factory=list)
    orm_detected: str = ""  # "sqlalchemy", "django", "peewee", "unknown"
    summary: str = ""


ORM_PATTERNS = [
    {
        "name": "n_plus_1",
        "pattern": re.compile(r"for\s+\w+\s+in.*:\s*\n\s+.*\.query\b|for\s+\w+\s+in.*:\s*\n\s+.*\.filter\b|for\s+\w+\s+in.*:\s*\n\s+.*\.get\(", re.MULTILINE),
        "severity": "high",
        "description": "N+1 query pattern — database query inside a loop",
        "suggestion": "Use eager loading (joinedload/selectinload) or batch queries",
    },
    {
        "name": "lazy_in_loop",
        "pattern": re.compile(r"for\s+\w+\s+in\s+\w+:\s*\n\s+.*\.\w+\.all\(\)"),
        "severity": "high",
        "description": "Lazy-loaded relationship accessed in loop — triggers N+1",
        "suggestion": "Pre-load relationships with joinedload() or selectinload() in the initial query",
    },
    {
        "name": "missing_eager_load",
        "pattern": re.compile(r"\.query\.filter.*\n(?:(?!joinedload|selectinload|subqueryload|contains_eager).)*.\.(\w+)"),
        "severity": "medium",
        "description": "Query result has relationship access without explicit eager loading",
        "suggestion": "Add .options(joinedload(Model.relationship)) to the query",
    },
    {
        "name": "raw_sql",
        "pattern": re.compile(r'(?:execute|raw|text)\(["\'](?:SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE),
        "severity": "medium",
        "description": "Raw SQL query — bypasses ORM protections and may have injection risk",
        "suggestion": "Use ORM query builder or parameterized queries with bound parameters",
    },
    {
        "name": "no_transaction",
        "pattern": re.compile(r"session\.add\(.*\n(?:(?!session\.commit|session\.flush|with\s+session).)*.session\.add\(", re.MULTILINE | re.DOTALL),
        "severity": "medium",
        "description": "Multiple session.add() without explicit transaction boundary",
        "suggestion": "Wrap related operations in a transaction: with session.begin():",
    },
]


class OrmReviewer:
    """Review ORM code for anti-patterns."""

    def __init__(self, config: OrmReviewConfig):
        self.config = config

    def scan(self) -> OrmReviewResult:
        logger.info("Scanning ORM code in %s", self.config.cwd)
        result = OrmReviewResult()

        from code_agents.analysis._ast_helpers import scan_python_files

        files = scan_python_files(self.config.cwd)[:self.config.max_files]
        result.files_scanned = 0

        for fpath in files:
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue

            # Only scan files that use ORM
            if not re.search(r"(sqlalchemy|django\.db|peewee|tortoise|Session|Base\.metadata)", content):
                continue

            result.files_scanned += 1
            rel_path = os.path.relpath(fpath, self.config.cwd)

            # Detect ORM
            if "sqlalchemy" in content:
                result.orm_detected = "sqlalchemy"
            elif "django.db" in content:
                result.orm_detected = "django"
            elif "peewee" in content:
                result.orm_detected = "peewee"

            # Line-by-line patterns
            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                for pattern_def in ORM_PATTERNS:
                    if re.search(r"(?:execute|raw|text)\([\"'](?:SELECT|INSERT|UPDATE|DELETE)", line, re.IGNORECASE):
                        if pattern_def["name"] == "raw_sql":
                            result.findings.append(OrmFinding(
                                file=rel_path, line=i, pattern="raw_sql",
                                severity="medium", code=line.strip()[:120],
                                description=pattern_def["description"],
                                suggestion=pattern_def["suggestion"],
                            ))

            # Multi-line patterns on full content
            for pattern_def in ORM_PATTERNS:
                if pattern_def["name"] == "raw_sql":
                    continue  # already handled
                for match in pattern_def["pattern"].finditer(content):
                    line_num = content[:match.start()].count("\n") + 1
                    result.findings.append(OrmFinding(
                        file=rel_path, line=line_num, pattern=pattern_def["name"],
                        severity=pattern_def["severity"],
                        code=match.group(0).strip()[:120],
                        description=pattern_def["description"],
                        suggestion=pattern_def["suggestion"],
                    ))

        result.summary = f"{len(result.findings)} issues in {result.files_scanned} ORM files (detected: {result.orm_detected or 'none'})"
        return result


def format_orm_review(result: OrmReviewResult) -> str:
    lines = [f"{'=' * 60}", f"  ORM Reviewer", f"{'=' * 60}"]
    lines.append(f"  {result.summary}")
    if not result.findings:
        lines.append("\n  No ORM issues found.")
    else:
        for sev in ("high", "medium", "low"):
            findings = [f for f in result.findings if f.severity == sev]
            if findings:
                lines.append(f"\n  [{sev.upper()}] ({len(findings)})")
                for f in findings[:10]:
                    lines.append(f"    {f.file}:{f.line} [{f.pattern}]")
                    lines.append(f"      {f.description}")
                    lines.append(f"      Fix: {f.suggestion}")
    lines.append("")
    return "\n".join(lines)
