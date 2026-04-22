"""Cache Designer — analyze data access patterns, recommend cache strategies.

Scans code for data access patterns (DB queries, API calls, file reads),
analyses frequency and mutability to recommend caching strategies with
TTL, invalidation approach, and storage backend.

Usage:
    from code_agents.observability.cache_designer import CacheDesigner, CacheDesignerConfig
    designer = CacheDesigner(CacheDesignerConfig(cwd="/path/to/repo"))
    result = designer.analyze()
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.observability.cache_designer")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CacheDesignerConfig:
    cwd: str = "."
    max_files: int = 500


@dataclass
class DataAccessPattern:
    """A detected data access operation."""
    file: str
    line: int
    access_type: str  # "db_read", "db_write", "api_call", "file_read", "config_read"
    pattern: str
    code: str = ""
    function_name: str = ""


@dataclass
class CacheStrategy:
    """Recommended cache strategy for an access pattern."""
    target: str  # function or pattern being cached
    file: str
    backend: str  # "in_memory", "redis", "memcached", "lru_cache", "disk"
    ttl_seconds: int = 300
    invalidation: str = ""  # "time_based", "event_driven", "write_through", "write_behind"
    rationale: str = ""
    implementation: str = ""  # code snippet
    estimated_hit_rate: str = ""  # "high", "medium", "low"


@dataclass
class CacheDesignerReport:
    """Full cache design analysis."""
    files_scanned: int = 0
    access_patterns_found: int = 0
    strategies: list[CacheStrategy] = field(default_factory=list)
    patterns: list[DataAccessPattern] = field(default_factory=list)
    read_write_ratio: str = ""
    summary: str = ""


# ---------------------------------------------------------------------------
# Access pattern detectors
# ---------------------------------------------------------------------------

READ_PATTERNS = [
    ("db_read", re.compile(r"\.(?:find|select|query|fetch|get|all|first|one|count)\s*\("), "Database read query"),
    ("db_read", re.compile(r"SELECT\s+.+\s+FROM\s+", re.IGNORECASE), "Raw SQL SELECT"),
    ("api_call", re.compile(r"requests\.get\s*\(|httpx\.get\s*\(|fetch\s*\("), "HTTP GET request"),
    ("api_call", re.compile(r"\.get\s*\(\s*['\"]https?://"), "API GET call"),
    ("file_read", re.compile(r"(?:open\([^,]+,\s*['\"]r|\.read_text\(|\.read_bytes\()"), "File read"),
    ("config_read", re.compile(r"(?:os\.getenv|os\.environ\.get|settings\.)\s*\("), "Config/env read"),
]

WRITE_PATTERNS = [
    ("db_write", re.compile(r"\.(?:insert|update|delete|save|commit|create|bulk_create|put)\s*\("), "Database write"),
    ("db_write", re.compile(r"(?:INSERT|UPDATE|DELETE)\s+", re.IGNORECASE), "Raw SQL write"),
    ("api_write", re.compile(r"requests\.(?:post|put|patch|delete)\s*\("), "HTTP mutating request"),
    ("file_write", re.compile(r"(?:open\([^,]+,\s*['\"]w|\.write_text\(|\.write_bytes\()"), "File write"),
]

FUNC_DEF_RE = re.compile(r"(?:def|async\s+def)\s+(\w+)\s*\(")
EXISTING_CACHE_RE = re.compile(
    r"(?:@lru_cache|@cache|@cached|@memoize|functools\.cache|cache\.get|redis\.get)"
)


# ---------------------------------------------------------------------------
# CacheDesigner
# ---------------------------------------------------------------------------


class CacheDesigner:
    """Analyze data access patterns and recommend cache strategies."""

    def __init__(self, config: Optional[CacheDesignerConfig] = None):
        self.config = config or CacheDesignerConfig()

    def analyze(self) -> CacheDesignerReport:
        """Run cache strategy analysis."""
        logger.info("Starting cache analysis in %s", self.config.cwd)
        report = CacheDesignerReport()
        root = Path(self.config.cwd)

        reads: list[DataAccessPattern] = []
        writes: list[DataAccessPattern] = []
        cached_files: set[str] = set()
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

                current_func = ""
                has_cache = False
                for idx, line in enumerate(lines, 1):
                    fm = FUNC_DEF_RE.search(line)
                    if fm:
                        current_func = fm.group(1)
                    if EXISTING_CACHE_RE.search(line):
                        has_cache = True
                        cached_files.add(rel)

                    for access_type, pattern, desc in READ_PATTERNS:
                        if pattern.search(line):
                            dap = DataAccessPattern(
                                file=rel, line=idx, access_type=access_type,
                                pattern=desc, code=line.strip(),
                                function_name=current_func,
                            )
                            reads.append(dap)
                            report.patterns.append(dap)

                    for access_type, pattern, desc in WRITE_PATTERNS:
                        if pattern.search(line):
                            dap = DataAccessPattern(
                                file=rel, line=idx, access_type=access_type,
                                pattern=desc, code=line.strip(),
                                function_name=current_func,
                            )
                            writes.append(dap)
                            report.patterns.append(dap)

        report.files_scanned = count
        report.access_patterns_found = len(report.patterns)

        total = len(reads) + len(writes)
        if total > 0:
            ratio = len(reads) / total
            report.read_write_ratio = f"{ratio:.0%} reads / {1 - ratio:.0%} writes"
        else:
            report.read_write_ratio = "no data access detected"

        # Generate strategies for uncached read-heavy functions
        func_reads: dict[str, list[DataAccessPattern]] = {}
        for r in reads:
            key = f"{r.file}::{r.function_name}" if r.function_name else r.file
            func_reads.setdefault(key, []).append(r)

        for key, pats in func_reads.items():
            file = pats[0].file
            if file in cached_files:
                continue
            strategy = self._design_strategy(key, pats, writes)
            report.strategies.append(strategy)

        report.summary = (
            f"Scanned {report.files_scanned} files, {report.access_patterns_found} access patterns "
            f"({len(reads)} reads, {len(writes)} writes). "
            f"{len(report.strategies)} cache strategies recommended."
        )
        logger.info("Cache analysis complete: %s", report.summary)
        return report

    def _design_strategy(
        self,
        key: str,
        reads: list[DataAccessPattern],
        all_writes: list[DataAccessPattern],
    ) -> CacheStrategy:
        """Design a cache strategy for a function/pattern."""
        file = reads[0].file
        func = reads[0].function_name or key

        # Check if related writes exist for the same file
        file_writes = [w for w in all_writes if w.file == file]
        has_mutations = len(file_writes) > 0

        # Determine access type mix
        access_types = {r.access_type for r in reads}

        # Select backend
        if "config_read" in access_types:
            backend = "in_memory"
            ttl = 3600
            invalidation = "time_based"
            impl = f"from functools import lru_cache\n\n@lru_cache(maxsize=128)\ndef {func}(...):"
            hit_rate = "high"
        elif "api_call" in access_types:
            backend = "redis"
            ttl = 300
            invalidation = "time_based"
            impl = f'cache_key = f"{func}:{{params_hash}}"\nresult = redis.get(cache_key) or fetch_and_cache(cache_key, ttl={ttl})'
            hit_rate = "medium"
        elif "db_read" in access_types and not has_mutations:
            backend = "redis"
            ttl = 600
            invalidation = "time_based"
            impl = f'@cache(ttl={ttl})\ndef {func}(...):\n    # DB read cached for {ttl}s'
            hit_rate = "high"
        elif "db_read" in access_types and has_mutations:
            backend = "redis"
            ttl = 120
            invalidation = "write_through"
            impl = f"# Write-through: invalidate cache on write\ndef {func}_invalidate():\n    redis.delete(f'{func}:*')"
            hit_rate = "medium"
        else:
            backend = "lru_cache"
            ttl = 60
            invalidation = "time_based"
            impl = f"@lru_cache(maxsize=256)\ndef {func}(...):"
            hit_rate = "medium"

        return CacheStrategy(
            target=func, file=file, backend=backend,
            ttl_seconds=ttl, invalidation=invalidation,
            rationale=f"{'|'.join(access_types)} pattern with {'mutations' if has_mutations else 'read-only'} workload.",
            implementation=impl,
            estimated_hit_rate=hit_rate,
        )


def format_cache_report(report: CacheDesignerReport) -> str:
    """Render cache design report."""
    lines = ["=== Cache Designer Report ===", ""]
    lines.append(f"Files scanned:      {report.files_scanned}")
    lines.append(f"Access patterns:    {report.access_patterns_found}")
    lines.append(f"Read/write ratio:   {report.read_write_ratio}")
    lines.append(f"Strategies:         {len(report.strategies)}")
    lines.append("")

    for s in report.strategies:
        lines.append(f"  {s.target} ({s.file})")
        lines.append(f"    Backend: {s.backend}, TTL: {s.ttl_seconds}s, Invalidation: {s.invalidation}")
        lines.append(f"    Hit rate: {s.estimated_hit_rate}, Rationale: {s.rationale}")
        lines.append(f"    Implementation:")
        for il in s.implementation.splitlines():
            lines.append(f"      {il}")
        lines.append("")

    lines.append(report.summary)
    return "\n".join(lines)
