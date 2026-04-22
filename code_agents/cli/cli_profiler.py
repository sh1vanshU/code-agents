"""CLI profiler command — performance profiling with cProfile."""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_profiler")


def cmd_profiler():
    """Profile a Python command with cProfile and show hotspots.

    Usage:
      code-agents profiler --command "pytest tests/test_api.py"
      code-agents profiler --command "python app.py" --top 10
      code-agents profiler --command "python -m mymod" --format json
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    command = None
    top = 20
    fmt = "text"

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--command" and i + 1 < len(args):
            command = args[i + 1]
            i += 1
        elif a == "--top" and i + 1 < len(args):
            try:
                top = int(args[i + 1])
            except ValueError:
                print(red(f"  Invalid --top value: {args[i + 1]}"))
                return
            i += 1
        elif a == "--format" and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_profiler.__doc__)
            return
        i += 1

    if not command:
        print(red("  Missing --command flag."))
        print(dim("  Usage: code-agents profiler --command \"pytest tests/\""))
        return

    if fmt not in ("text", "json"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: text, json"))
        return

    from code_agents.observability.profiler import ProfilerAgent, format_profile_result, format_profile_json

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Profiling: {command}"))
    print(dim(f"  Working directory: {cwd}"))
    print()

    agent = ProfilerAgent(cwd=cwd, command=command)
    result = agent.run()

    if fmt == "json":
        print(json.dumps(format_profile_json(result), indent=2))
    else:
        print(format_profile_result(result, top=top))
