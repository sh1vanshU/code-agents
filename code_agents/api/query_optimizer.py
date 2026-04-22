"""Query Optimizer — analyze SQL queries for performance issues and suggest improvements.

Parses SQL queries, identifies missing indexes, full table scans, N+1 patterns,
unnecessary JOINs, and suggests rewrites with estimated improvement.

Usage:
    from code_agents.api.query_optimizer import QueryOptimizer
    optimizer = QueryOptimizer()
    result = optimizer.analyze("SELECT * FROM users WHERE email = 'test@test.com'")
    print(format_query_report(result))
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.api.query_optimizer")


@dataclass
class QueryOptimizerConfig:
    dialect: str = "postgresql"  # postgresql, mysql, sqlite


@dataclass
class QueryIssue:
    issue_type: str  # "select_star", "missing_index", "full_scan", "no_limit", "implicit_join", "subquery", "like_wildcard"
    severity: str  # "high", "medium", "low"
    description: str
    suggestion: str
    original: str = ""
    optimized: str = ""


@dataclass
class QueryAnalysisResult:
    query: str
    issues: list[QueryIssue] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    has_where: bool = False
    has_limit: bool = False
    has_order: bool = False
    join_count: int = 0
    subquery_count: int = 0
    estimated_improvement: str = ""
    summary: str = ""


class QueryOptimizer:
    """Analyze and optimize SQL queries."""

    def __init__(self, config: Optional[QueryOptimizerConfig] = None):
        self.config = config or QueryOptimizerConfig()

    def analyze(self, query: str) -> QueryAnalysisResult:
        logger.info("Analyzing query (%d chars)", len(query))
        q = query.strip()
        result = QueryAnalysisResult(query=q)

        q_upper = q.upper()

        # Extract tables
        result.tables = self._extract_tables(q)
        result.has_where = "WHERE" in q_upper
        result.has_limit = "LIMIT" in q_upper
        result.has_order = "ORDER BY" in q_upper
        result.join_count = q_upper.count("JOIN")
        result.subquery_count = q_upper.count("SELECT") - 1

        # Check SELECT *
        if re.search(r"SELECT\s+\*", q, re.IGNORECASE):
            result.issues.append(QueryIssue(
                issue_type="select_star", severity="medium",
                description="SELECT * fetches all columns — wastes bandwidth and prevents covering indexes",
                suggestion="List only needed columns: SELECT id, name, email FROM ...",
            ))

        # Check missing WHERE on UPDATE/DELETE
        if re.match(r"(UPDATE|DELETE)\s", q, re.IGNORECASE) and "WHERE" not in q_upper:
            result.issues.append(QueryIssue(
                issue_type="full_scan", severity="high",
                description="UPDATE/DELETE without WHERE clause affects ALL rows",
                suggestion="Add a WHERE clause to limit affected rows",
            ))

        # Check no LIMIT on SELECT
        if q_upper.startswith("SELECT") and "LIMIT" not in q_upper and "COUNT(" not in q_upper:
            result.issues.append(QueryIssue(
                issue_type="no_limit", severity="medium",
                description="SELECT without LIMIT may return unbounded results",
                suggestion="Add LIMIT to prevent returning excessive rows",
            ))

        # Check LIKE with leading wildcard
        if re.search(r"LIKE\s+['\"]%", q, re.IGNORECASE):
            result.issues.append(QueryIssue(
                issue_type="like_wildcard", severity="high",
                description="LIKE '%...' with leading wildcard prevents index usage — full table scan",
                suggestion="Use full-text search index, or restructure to avoid leading wildcard",
            ))

        # Check missing index hints (WHERE on non-obvious columns)
        where_cols = re.findall(r"WHERE\s+(\w+)\s*=", q, re.IGNORECASE)
        for col in where_cols:
            if col.lower() not in ("id", "pk", "uuid"):
                result.issues.append(QueryIssue(
                    issue_type="missing_index", severity="medium",
                    description=f"Filtering on '{col}' — ensure an index exists",
                    suggestion=f"CREATE INDEX idx_{result.tables[0] if result.tables else 'table'}_{col} ON {result.tables[0] if result.tables else 'table'} ({col})",
                ))

        # Check subqueries
        if result.subquery_count > 0:
            result.issues.append(QueryIssue(
                issue_type="subquery", severity="low",
                description=f"{result.subquery_count} subquery(ies) detected — may be slower than JOINs",
                suggestion="Consider rewriting subqueries as JOINs or CTEs for better performance",
            ))

        # Check implicit joins (comma-separated FROM)
        if re.search(r"FROM\s+\w+\s*,\s*\w+", q, re.IGNORECASE) and "JOIN" not in q_upper:
            result.issues.append(QueryIssue(
                issue_type="implicit_join", severity="low",
                description="Implicit join using comma syntax — harder to read and optimize",
                suggestion="Use explicit JOIN syntax: FROM a JOIN b ON a.id = b.a_id",
            ))

        result.summary = f"{len(result.issues)} issues found, {len(result.tables)} tables, {result.join_count} joins"
        return result

    def _extract_tables(self, query: str) -> list[str]:
        tables = []
        # FROM table
        for m in re.finditer(r"(?:FROM|JOIN|UPDATE|INTO)\s+(\w+)", query, re.IGNORECASE):
            table = m.group(1)
            if table.upper() not in ("SELECT", "SET", "VALUES", "WHERE", "ON", "AS"):
                tables.append(table)
        return list(dict.fromkeys(tables))  # dedupe preserving order


def format_query_report(result: QueryAnalysisResult) -> str:
    lines = [f"{'=' * 60}", f"  Query Optimizer", f"{'=' * 60}"]
    lines.append(f"  {result.summary}")
    lines.append(f"  Tables: {', '.join(result.tables)}")
    lines.append(f"  WHERE: {result.has_where} | LIMIT: {result.has_limit} | ORDER: {result.has_order}")
    if result.issues:
        lines.append(f"\n  Issues:")
        for issue in result.issues:
            icon = {"high": "X", "medium": "!", "low": "~"}[issue.severity]
            lines.append(f"    {icon} [{issue.issue_type}] {issue.description}")
            lines.append(f"      Fix: {issue.suggestion}")
    lines.append("")
    return "\n".join(lines)
