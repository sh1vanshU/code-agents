"""Performance pattern checker — detect async/sync mix, connection issues, eager imports.

Scans Python code for common performance anti-patterns including mixing
sync/async handlers, missing connection pooling, slow startup from
eager imports, and N+1 query patterns.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.observability.perf_pattern_checker")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}

# Heavy modules that slow startup when imported eagerly
HEAVY_IMPORTS = {
    "torch", "tensorflow", "pandas", "numpy", "scipy", "matplotlib",
    "sklearn", "transformers", "openai", "langchain", "anthropic",
    "boto3", "google.cloud", "azure", "PIL", "cv2", "pydantic",
    "sqlalchemy", "celery", "dramatiq",
}

# Sync blocking calls in async context
SYNC_BLOCKERS = {
    "time.sleep", "os.system", "subprocess.run", "subprocess.call",
    "requests.get", "requests.post", "requests.put", "requests.delete",
    "requests.patch", "open(", "input(",
}


@dataclass
class PerfFinding:
    """A single performance pattern finding."""

    file: str = ""
    line: int = 0
    category: str = ""  # async_sync_mix | connection | startup | n_plus_1
    severity: str = "warning"
    message: str = ""
    suggestion: str = ""
    estimated_impact: str = "medium"  # low | medium | high


@dataclass
class PerfCheckResult:
    """Result of performance pattern check."""

    files_scanned: int = 0
    findings: list[PerfFinding] = field(default_factory=list)
    startup_imports: int = 0  # Number of heavy top-level imports
    async_handlers: int = 0
    sync_handlers: int = 0
    perf_score: float = 0.0  # 0-100
    summary: dict[str, int] = field(default_factory=dict)


class PerfPatternChecker:
    """Check for performance anti-patterns in Python code."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("PerfPatternChecker initialized for %s", cwd)

    def check(
        self,
        categories: list[str] | None = None,
    ) -> PerfCheckResult:
        """Run performance pattern checks.

        Args:
            categories: Which checks to run. Default: all.
                Options: async_sync_mix, connection, startup, n_plus_1

        Returns:
            PerfCheckResult with findings and score.
        """
        if categories is None:
            categories = ["async_sync_mix", "connection", "startup", "n_plus_1"]

        result = PerfCheckResult()
        files = self._collect_files()
        result.files_scanned = len(files)
        logger.info("Checking %d files for perf patterns", len(files))

        for fpath in files:
            try:
                content = Path(fpath).read_text(errors="replace")
            except OSError:
                continue

            rel = os.path.relpath(fpath, self.cwd)

            if "async_sync_mix" in categories:
                findings, async_count, sync_count = self._check_async_sync(content, rel)
                result.findings.extend(findings)
                result.async_handlers += async_count
                result.sync_handlers += sync_count

            if "connection" in categories:
                result.findings.extend(self._check_connections(content, rel))

            if "startup" in categories:
                heavy = self._check_startup_imports(content, rel)
                result.findings.extend(heavy)
                result.startup_imports += len(heavy)

            if "n_plus_1" in categories:
                result.findings.extend(self._check_n_plus_1(content, rel))

        # Calculate score
        high_count = sum(1 for f in result.findings if f.estimated_impact == "high")
        med_count = sum(1 for f in result.findings if f.estimated_impact == "medium")
        total = result.files_scanned or 1
        result.perf_score = round(max(0, 100 - (high_count * 10 + med_count * 3) / total * 10), 1)

        result.summary = {
            "files_scanned": result.files_scanned,
            "total_findings": len(result.findings),
            "high_impact": high_count,
            "medium_impact": med_count,
            "startup_imports": result.startup_imports,
            "async_handlers": result.async_handlers,
            "sync_handlers": result.sync_handlers,
            "perf_score": result.perf_score,
        }
        logger.info("Perf check complete: %d findings, score=%.1f", len(result.findings), result.perf_score)
        return result

    def _collect_files(self) -> list[str]:
        """Collect Python files to check."""
        files: list[str] = []
        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                if fname.endswith(".py") and not fname.startswith("test_"):
                    files.append(os.path.join(root, fname))
        return files

    def _check_async_sync(
        self, content: str, rel_path: str,
    ) -> tuple[list[PerfFinding], int, int]:
        """Check for async/sync handler mixing."""
        findings: list[PerfFinding] = []
        async_count = 0
        sync_count = 0

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings, 0, 0

        # Find async functions that call sync blockers
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                async_count += 1
                # Extract actual source lines for this function
                end_line = getattr(node, "end_lineno", None) or (node.lineno + 50)
                func_lines = content.splitlines()[node.lineno - 1:end_line]
                func_text = "\n".join(func_lines)
                for blocker in SYNC_BLOCKERS:
                    name = blocker.rstrip("(")
                    if name in func_text:
                        findings.append(PerfFinding(
                            file=rel_path, line=node.lineno,
                            category="async_sync_mix",
                            severity="error",
                            message=f"Sync blocker '{name}' in async function '{node.name}'",
                            suggestion=f"Use async equivalent or run_in_executor for '{name}'",
                            estimated_impact="high",
                        ))
                        break
            elif isinstance(node, ast.FunctionDef):
                # Count top-level sync functions with route decorators
                for dec in node.decorator_list:
                    dec_str = ast.dump(dec)
                    if "get" in dec_str or "post" in dec_str or "route" in dec_str:
                        sync_count += 1
                        break

        # Warn if mixing async and sync handlers in same file
        if async_count > 0 and sync_count > 0:
            findings.append(PerfFinding(
                file=rel_path, category="async_sync_mix",
                severity="warning",
                message=f"Mixed {async_count} async and {sync_count} sync handlers",
                suggestion="Prefer all-async handlers for consistent performance",
                estimated_impact="medium",
            ))

        return findings, async_count, sync_count

    def _check_connections(self, content: str, rel_path: str) -> list[PerfFinding]:
        """Check connection management patterns."""
        findings: list[PerfFinding] = []

        # Check for connections created inside functions (not pooled)
        conn_patterns = [
            (r"\.connect\(\s*\)", "Database connection created per-call"),
            (r"requests\.Session\(\)", "HTTP session created per-call"),
            (r"aiohttp\.ClientSession\(\)", "aiohttp session created per-call"),
            (r"redis\.Redis\(\)", "Redis connection created per-call"),
        ]

        for i, line in enumerate(content.splitlines(), 1):
            for pattern, msg in conn_patterns:
                if re.search(pattern, line):
                    # Check if inside a function
                    indent = len(line) - len(line.lstrip())
                    if indent > 0:  # Inside a function
                        findings.append(PerfFinding(
                            file=rel_path, line=i, category="connection",
                            severity="warning", message=msg,
                            suggestion="Use connection pooling or create session at module/class level",
                            estimated_impact="medium",
                        ))

        return findings

    def _check_startup_imports(self, content: str, rel_path: str) -> list[PerfFinding]:
        """Check for heavy imports at module level."""
        findings: list[PerfFinding] = []
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            # Only top-level imports (no indentation)
            if line[0] in (" ", "\t"):
                continue

            for mod in HEAVY_IMPORTS:
                if mod in stripped:
                    findings.append(PerfFinding(
                        file=rel_path, line=i, category="startup",
                        severity="warning",
                        message=f"Heavy import '{mod}' at module level slows startup",
                        suggestion=f"Lazy-import '{mod}' inside the function that needs it",
                        estimated_impact="medium",
                    ))
                    break

        return findings

    def _check_n_plus_1(self, content: str, rel_path: str) -> list[PerfFinding]:
        """Check for N+1 query patterns."""
        findings: list[PerfFinding] = []

        # Pattern: query inside a for loop
        lines = content.splitlines()
        in_loop = False
        loop_start = 0

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith(("for ", "async for ")):
                in_loop = True
                loop_start = i
            elif in_loop and stripped and not line[0] in (" ", "\t"):
                in_loop = False

            if in_loop:
                query_patterns = [
                    ".query(", ".filter(", ".execute(", ".fetch(",
                    "await db.", "session.get(", "cursor.execute(",
                ]
                for qp in query_patterns:
                    if qp in stripped:
                        findings.append(PerfFinding(
                            file=rel_path, line=i, category="n_plus_1",
                            severity="error",
                            message=f"Potential N+1 query: DB call inside loop (loop at L{loop_start})",
                            suggestion="Batch the query outside the loop or use eager loading",
                            estimated_impact="high",
                        ))
                        break

        return findings


def check_perf_patterns(
    cwd: str,
    categories: list[str] | None = None,
) -> dict:
    """Convenience function to check performance patterns.

    Returns:
        Dict with findings, score, and summary.
    """
    checker = PerfPatternChecker(cwd)
    result = checker.check(categories=categories)
    return {
        "findings": [
            {"file": f.file, "line": f.line, "category": f.category,
             "severity": f.severity, "message": f.message,
             "estimated_impact": f.estimated_impact}
            for f in result.findings
        ],
        "perf_score": result.perf_score,
        "summary": result.summary,
    }
