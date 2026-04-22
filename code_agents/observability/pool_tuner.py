"""Pool Tuner — analyze connection usage, recommend pool configurations.

Scans code for database connections, HTTP clients, thread/process pools
and recommends optimal pool sizes, timeouts, and retry settings based
on detected usage patterns.

Usage:
    from code_agents.observability.pool_tuner import PoolTuner, PoolTunerConfig
    tuner = PoolTuner(PoolTunerConfig(cwd="/path/to/repo"))
    result = tuner.analyze()
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.observability.pool_tuner")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PoolTunerConfig:
    cwd: str = "."
    max_files: int = 500
    target_concurrency: int = 100  # expected concurrent requests


@dataclass
class PoolUsage:
    """A detected pool or connection pattern."""
    file: str
    line: int
    pool_type: str  # "db", "http", "thread", "process", "redis", "custom"
    pattern: str
    code: str = ""
    current_size: Optional[int] = None
    current_timeout: Optional[int] = None


@dataclass
class PoolRecommendation:
    """Recommended pool configuration."""
    pool_type: str
    file: str
    recommended_size: int
    recommended_min: int = 5
    recommended_timeout: int = 30
    recommended_idle_timeout: int = 300
    retry_count: int = 3
    retry_backoff: float = 0.5
    rationale: str = ""
    config_snippet: str = ""
    current_config: str = ""


@dataclass
class PoolTunerReport:
    """Full pool tuning analysis."""
    files_scanned: int = 0
    pools_found: int = 0
    usages: list[PoolUsage] = field(default_factory=list)
    recommendations: list[PoolRecommendation] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

POOL_PATTERNS = [
    ("db", re.compile(r"(?:create_engine|sessionmaker|connect)\s*\("), "SQLAlchemy/DB engine"),
    ("db", re.compile(r"(?:pool_size|max_overflow|pool_recycle)\s*=\s*(\d+)"), "DB pool config"),
    ("db", re.compile(r"(?:psycopg2|asyncpg|pymysql|sqlite3)\.connect"), "Direct DB connection"),
    ("http", re.compile(r"(?:Session|ClientSession|AsyncClient|Client)\s*\("), "HTTP session/client"),
    ("http", re.compile(r"(?:max_connections|pool_connections|pool_maxsize)\s*=\s*(\d+)"), "HTTP pool config"),
    ("http", re.compile(r"(?:timeout)\s*=\s*(\d+)"), "Timeout setting"),
    ("thread", re.compile(r"ThreadPoolExecutor\s*\(\s*(?:max_workers\s*=\s*)?(\d+)?"), "Thread pool"),
    ("process", re.compile(r"ProcessPoolExecutor\s*\(\s*(?:max_workers\s*=\s*)?(\d+)?"), "Process pool"),
    ("redis", re.compile(r"(?:Redis|StrictRedis|ConnectionPool)\s*\("), "Redis connection"),
    ("redis", re.compile(r"max_connections\s*=\s*(\d+)"), "Redis pool config"),
]

SIZE_EXTRACT_RE = re.compile(r"(\d+)")


# ---------------------------------------------------------------------------
# PoolTuner
# ---------------------------------------------------------------------------


class PoolTuner:
    """Analyze connection pools and recommend configurations."""

    def __init__(self, config: Optional[PoolTunerConfig] = None):
        self.config = config or PoolTunerConfig()

    def analyze(self) -> PoolTunerReport:
        """Run pool configuration analysis."""
        logger.info("Starting pool analysis in %s", self.config.cwd)
        report = PoolTunerReport()
        root = Path(self.config.cwd)

        count = 0
        for ext in ("*.py", "*.js", "*.ts", "*.yaml", "*.yml", "*.toml"):
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
                for idx, line in enumerate(lines, 1):
                    for pool_type, pattern, desc in POOL_PATTERNS:
                        m = pattern.search(line)
                        if m:
                            current_size = None
                            if m.lastindex and m.lastindex >= 1 and m.group(1):
                                try:
                                    current_size = int(m.group(1))
                                except (ValueError, TypeError):
                                    pass
                            report.usages.append(PoolUsage(
                                file=rel, line=idx,
                                pool_type=pool_type, pattern=desc,
                                code=line.strip(), current_size=current_size,
                            ))

        report.files_scanned = count
        report.pools_found = len(report.usages)

        # Group by type and generate recommendations
        type_files: dict[str, list[PoolUsage]] = {}
        for u in report.usages:
            type_files.setdefault(u.pool_type, []).append(u)

        for pool_type, usages in type_files.items():
            rec = self._recommend(pool_type, usages)
            report.recommendations.append(rec)

        report.summary = (
            f"Scanned {report.files_scanned} files, found {report.pools_found} pool configurations. "
            f"{len(report.recommendations)} recommendations generated."
        )
        logger.info("Pool analysis complete: %s", report.summary)
        return report

    def _recommend(self, pool_type: str, usages: list[PoolUsage]) -> PoolRecommendation:
        """Generate pool configuration recommendation."""
        concurrency = self.config.target_concurrency
        file = usages[0].file

        # Detect current size
        current_sizes = [u.current_size for u in usages if u.current_size is not None]
        current = current_sizes[0] if current_sizes else None
        current_str = str(current) if current else "default/unknown"

        if pool_type == "db":
            # DB: pool_size ~ concurrency / 4, min 5, max 50
            recommended = max(5, min(50, concurrency // 4))
            timeout = 30
            idle = 300
            snippet = (
                f"engine = create_engine(url,\n"
                f"    pool_size={recommended},\n"
                f"    max_overflow={recommended // 2},\n"
                f"    pool_timeout={timeout},\n"
                f"    pool_recycle={idle},\n"
                f"    pool_pre_ping=True,\n"
                f")"
            )
            rationale = f"For {concurrency} concurrent requests, {recommended} persistent DB connections with {recommended // 2} overflow."
        elif pool_type == "http":
            recommended = max(10, min(100, concurrency // 2))
            timeout = 15
            idle = 120
            snippet = (
                f"session = requests.Session()\n"
                f"adapter = HTTPAdapter(\n"
                f"    pool_connections={recommended},\n"
                f"    pool_maxsize={recommended},\n"
                f"    max_retries=Retry(total=3, backoff_factor=0.5),\n"
                f")\n"
                f"session.mount('https://', adapter)"
            )
            rationale = f"HTTP pool of {recommended} for {concurrency} concurrent requests with retry."
        elif pool_type == "thread":
            recommended = max(4, min(32, concurrency // 5))
            timeout = 60
            idle = 600
            snippet = f"executor = ThreadPoolExecutor(max_workers={recommended})"
            rationale = f"Thread pool of {recommended} workers balances I/O parallelism with GIL constraints."
        elif pool_type == "process":
            import os as _os
            cpu_count = _os.cpu_count() or 4
            recommended = max(2, min(cpu_count, concurrency // 10))
            timeout = 120
            idle = 600
            snippet = f"executor = ProcessPoolExecutor(max_workers={recommended})"
            rationale = f"Process pool of {recommended} (matched to CPU cores) for CPU-bound work."
        elif pool_type == "redis":
            recommended = max(10, min(50, concurrency // 3))
            timeout = 5
            idle = 300
            snippet = (
                f"pool = redis.ConnectionPool(\n"
                f"    max_connections={recommended},\n"
                f"    timeout={timeout},\n"
                f")"
            )
            rationale = f"Redis pool of {recommended} connections for {concurrency} concurrent requests."
        else:
            recommended = max(5, concurrency // 5)
            timeout = 30
            idle = 300
            snippet = f"# Configure pool_size={recommended}, timeout={timeout}"
            rationale = "Generic pool sizing based on target concurrency."

        return PoolRecommendation(
            pool_type=pool_type, file=file,
            recommended_size=recommended,
            recommended_min=max(2, recommended // 4),
            recommended_timeout=timeout,
            recommended_idle_timeout=idle,
            rationale=rationale,
            config_snippet=snippet,
            current_config=current_str,
        )


def format_pool_report(report: PoolTunerReport) -> str:
    """Render pool tuning report."""
    lines = ["=== Pool Tuner Report ===", ""]
    lines.append(f"Files scanned:    {report.files_scanned}")
    lines.append(f"Pools found:      {report.pools_found}")
    lines.append(f"Recommendations:  {len(report.recommendations)}")
    lines.append("")

    for rec in report.recommendations:
        lines.append(f"  [{rec.pool_type.upper()}] {rec.file}")
        lines.append(f"    Current: {rec.current_config} -> Recommended: {rec.recommended_size}")
        lines.append(f"    Timeout: {rec.recommended_timeout}s, Idle: {rec.recommended_idle_timeout}s")
        lines.append(f"    {rec.rationale}")
        lines.append(f"    Config:")
        for sl in rec.config_snippet.splitlines():
            lines.append(f"      {sl}")
        lines.append("")

    lines.append(report.summary)
    return "\n".join(lines)
