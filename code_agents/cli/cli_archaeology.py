"""CLI handler for Code Archaeology.

Usage:
  code-agents archaeology src/api.py:45
  code-agents archaeology src/api.py:45 --function process_payment
  code-agents archaeology src/api.py --function process_payment
"""

from __future__ import annotations

import logging
import os
import re
import sys

logger = logging.getLogger("code_agents.cli.cli_archaeology")


def _user_cwd() -> str:
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def cmd_archaeology(rest: list[str] | None = None):
    """Investigate the origin and intent behind code."""
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    if not rest:
        print(f"\n  {red('Usage: code-agents archaeology <file>[:line] [--function <name>]')}")
        print(f"  {dim('Examples:')}")
        print(f"    code-agents archaeology src/api.py:45")
        print(f"    code-agents archaeology src/api.py:45 --function process_payment")
        print(f"    code-agents archaeology src/api.py --function handle_request")
        return

    file_arg = rest[0]
    line = 0
    function = ""

    # Parse file:line syntax
    m = re.match(r"^(.+?):(\d+)$", file_arg)
    if m:
        file_arg = m.group(1)
        line = int(m.group(2))

    # Parse --function flag
    i = 1
    while i < len(rest):
        if rest[i] in ("--function", "--fn", "-f") and i + 1 < len(rest):
            function = rest[i + 1]
            i += 2
            continue
        if rest[i] == "--json":
            # Will be handled below
            pass
        i += 1

    json_mode = "--json" in rest
    cwd = _user_cwd()

    from code_agents.knowledge.code_archaeology import CodeArchaeologist, format_report_rich

    archaeologist = CodeArchaeologist(cwd=cwd)

    if not json_mode:
        print(f"\n  {bold('Code Archaeology')}")
        parts = [f"File: {file_arg}"]
        if line:
            parts.append(f"Line: {line}")
        if function:
            parts.append(f"Function: {function}")
        print(f"  {dim(' | '.join(parts))}\n")

    report = archaeologist.investigate(
        file_path=file_arg,
        line=line,
        function=function,
    )

    if json_mode:
        import json
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report_rich(report))
