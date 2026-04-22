"""Usage Tracer — find where any symbol is used across the codebase.

Traces functions, classes, config keys, env vars, constants, and API
endpoints. Groups results by usage type (import, call, test, config, etc.).

Usage:
    from code_agents.domain.usage_tracer import UsageTracer
    tracer = UsageTracer("/path/to/repo")
    result = tracer.trace("build_prompt")
    print(format_usage(result))
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.domain.usage_tracer")


@dataclass
class UsageTraceConfig:
    """Configuration for usage tracing."""
    cwd: str = "."
    include_tests: bool = True
    include_configs: bool = True
    max_results: int = 100


@dataclass
class UsageEntry:
    """A single usage site."""
    file: str
    line: int
    usage_type: str  # import, call, definition, assignment, reference, test, config
    content: str = ""
    context: str = ""  # enclosing function/class name


@dataclass
class UsageTraceResult:
    """Result of tracing a symbol's usage."""
    symbol: str
    total_usages: int = 0
    definition_count: int = 0
    import_count: int = 0
    call_count: int = 0
    test_count: int = 0
    config_count: int = 0
    reference_count: int = 0
    usages_by_type: dict[str, list[UsageEntry]] = field(default_factory=lambda: defaultdict(list))
    usages_by_file: dict[str, list[UsageEntry]] = field(default_factory=lambda: defaultdict(list))
    files_affected: list[str] = field(default_factory=list)


class UsageTracer:
    """Trace symbol usage across the codebase."""

    def __init__(self, config: UsageTraceConfig):
        self.config = config

    def trace(self, symbol: str) -> UsageTraceResult:
        """Find all usages of a symbol."""
        logger.info("Tracing usage of: %s", symbol)

        from code_agents.tools._pattern_matchers import find_usage_sites

        sites = find_usage_sites(self.config.cwd, symbol, max_results=self.config.max_results)

        result = UsageTraceResult(symbol=symbol)
        seen_files = set()

        for site in sites:
            if not self.config.include_tests and site.usage_type == "test":
                continue
            if not self.config.include_configs and site.usage_type == "config":
                continue

            entry = UsageEntry(
                file=site.file,
                line=site.line,
                usage_type=site.usage_type,
                content=site.content,
                context=site.function_context,
            )

            result.usages_by_type[site.usage_type].append(entry)
            result.usages_by_file[site.file].append(entry)
            seen_files.add(site.file)

        result.files_affected = sorted(seen_files)
        result.total_usages = sum(len(v) for v in result.usages_by_type.values())
        result.definition_count = len(result.usages_by_type.get("definition", []))
        result.import_count = len(result.usages_by_type.get("import", []))
        result.call_count = len(result.usages_by_type.get("call", []))
        result.test_count = len(result.usages_by_type.get("test", []))
        result.config_count = len(result.usages_by_type.get("config", []))
        result.reference_count = len(result.usages_by_type.get("reference", []))

        logger.info("Found %d usages across %d files", result.total_usages, len(result.files_affected))
        return result


def format_usage(result: UsageTraceResult) -> str:
    """Format usage trace for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Usage trace: {result.symbol}")
    lines.append(f"{'=' * 60}")
    lines.append(f"  Total: {result.total_usages} usages across {len(result.files_affected)} files")
    lines.append(f"  Definitions: {result.definition_count} | Imports: {result.import_count} | "
                 f"Calls: {result.call_count} | Tests: {result.test_count} | "
                 f"Configs: {result.config_count} | Refs: {result.reference_count}")
    lines.append("")

    for usage_type, entries in sorted(result.usages_by_type.items()):
        lines.append(f"  [{usage_type.upper()}] ({len(entries)})")
        for entry in entries[:10]:
            lines.append(f"    {entry.file}:{entry.line}  {entry.content[:80]}")
        if len(entries) > 10:
            lines.append(f"    ... and {len(entries) - 10} more")
        lines.append("")

    return "\n".join(lines)
