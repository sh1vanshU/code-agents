"""CLI commands for debugging and troubleshooting tools.

Commands:
  code-agents stack-decode <file|->         Decode a stack trace
  code-agents log-analyze <file|->          Analyze log entries
  code-agents env-diff <file1> <file2>      Diff environment configs
  code-agents leak-scan                     Scan for memory leak patterns
  code-agents deadlock-scan                 Scan for concurrency hazards
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_debug_tools")


def _user_cwd() -> str:
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def cmd_stack_decode(rest: list[str] | None = None):
    """Decode a stack trace — map to code, explain error, suggest fix.

    Usage: code-agents stack-decode <file>
           cat trace.txt | code-agents stack-decode -
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    # Read from file, stdin, or clipboard
    trace_text = ""
    if rest and rest[0] == "-":
        trace_text = sys.stdin.read()
    elif rest:
        try:
            with open(rest[0], "r") as f:
                trace_text = f.read()
        except OSError as e:
            # Treat as inline trace text
            trace_text = " ".join(rest)
    else:
        print(f"\n  {red('Usage: code-agents stack-decode <file|->  or paste trace as argument')}")
        return

    from code_agents.observability.stack_decoder import StackDecoder, StackDecodeConfig, format_stack_decode
    config = StackDecodeConfig(cwd=_user_cwd())
    result = StackDecoder(config).decode(trace_text)
    print(format_stack_decode(result))


def cmd_log_analyze(rest: list[str] | None = None):
    """Analyze logs — correlate, build timeline, find root cause.

    Usage: code-agents log-analyze <file>
           cat logs.txt | code-agents log-analyze -
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    log_text = ""
    if rest and rest[0] == "-":
        log_text = sys.stdin.read()
    elif rest:
        try:
            with open(rest[0], "r") as f:
                log_text = f.read()
        except OSError:
            log_text = " ".join(rest)
    else:
        print(f"\n  {red('Usage: code-agents log-analyze <file|->  or paste logs as argument')}")
        return

    from code_agents.observability.log_analyzer import LogAnalyzer, format_log_analysis
    result = LogAnalyzer().analyze(log_text)
    print(format_log_analysis(result))


def cmd_env_diff(rest: list[str] | None = None):
    """Diff two environment config files.

    Usage: code-agents env-diff <file1> <file2>
    Example: code-agents env-diff .env.local .env.staging
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if len(rest) < 2:
        print(f"\n  {red('Usage: code-agents env-diff <file1> <file2>')}")
        print(f"  {dim('Example: code-agents env-diff .env.local .env.staging')}")
        return

    from code_agents.devops.env_differ import EnvDiffer, EnvDiffConfig, format_env_diff
    config = EnvDiffConfig(cwd=_user_cwd(), mask_secrets="--show-secrets" not in rest)
    result = EnvDiffer(config).diff_files(rest[0], rest[1])
    print(format_env_diff(result))


def cmd_leak_scan(rest: list[str] | None = None):
    """Scan for memory leak patterns — unclosed resources, growing caches.

    Usage: code-agents leak-scan [--path <dir>]
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    cwd = _user_cwd()
    if "--path" in rest:
        idx = rest.index("--path")
        if idx + 1 < len(rest):
            cwd = rest[idx + 1]

    print(f"  {cyan('Scanning for memory leak patterns...')}")
    from code_agents.observability.leak_finder import LeakFinder, LeakFinderConfig, format_leak_report
    config = LeakFinderConfig(cwd=cwd)
    result = LeakFinder(config).scan()
    print(format_leak_report(result))


def cmd_deadlock_scan(rest: list[str] | None = None):
    """Scan for concurrency hazards — race conditions, deadlocks, async issues.

    Usage: code-agents deadlock-scan [--path <dir>]
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    cwd = _user_cwd()
    if "--path" in rest:
        idx = rest.index("--path")
        if idx + 1 < len(rest):
            cwd = rest[idx + 1]

    print(f"  {cyan('Scanning for concurrency hazards...')}")
    from code_agents.observability.deadlock_detector import DeadlockDetector, DeadlockDetectorConfig, format_deadlock_report
    config = DeadlockDetectorConfig(cwd=cwd)
    result = DeadlockDetector(config).scan()
    print(format_deadlock_report(result))
