"""CLI handler for the code explanation engine.

Usage:
  code-agents explain-code src/api.py:45-80
  code-agents explain-code src/api.py --function process_payment
  code-agents explain-code src/api.py              # whole file
"""

from __future__ import annotations

import logging
import os
import re
import sys

logger = logging.getLogger("code_agents.cli.cli_explain")


def _user_cwd() -> str:
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def cmd_explain_code(rest: list[str] | None = None):
    """Explain a code block, function, or file with static analysis.

    Supports:
      code-agents explain-code src/api.py:45-80
      code-agents explain-code src/api.py --function process_payment
      code-agents explain-code src/api.py
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    if not rest:
        print(f"\n  {red('Usage: code-agents explain-code <file>[:start-end] [--function <name>]')}")
        print(f"  {dim('Examples:')}")
        print(f"    code-agents explain-code src/api.py:45-80")
        print(f"    code-agents explain-code src/api.py --function process_payment")
        print(f"    code-agents explain-code src/api.py")
        return

    file_arg = rest[0]
    function_name = ""
    start_line = 0
    end_line = 0

    # Parse --function flag
    i = 1
    while i < len(rest):
        if rest[i] in ("--function", "--fn", "-f") and i + 1 < len(rest):
            function_name = rest[i + 1]
            i += 2
            continue
        i += 1

    # Parse file:start-end syntax
    m = re.match(r"^(.+?):(\d+)-(\d+)$", file_arg)
    if m:
        file_arg = m.group(1)
        start_line = int(m.group(2))
        end_line = int(m.group(3))

    cwd = _user_cwd()

    from code_agents.knowledge.code_explainer import CodeExplainer, format_explanation

    explainer = CodeExplainer(cwd=cwd)

    if function_name:
        print(f"\n  {bold('Code Explanation Engine')}")
        print(f"  {dim(f'File: {file_arg} | Function: {function_name}')}\n")
    elif start_line and end_line:
        print(f"\n  {bold('Code Explanation Engine')}")
        print(f"  {dim(f'File: {file_arg} | Lines: {start_line}-{end_line}')}\n")
    else:
        print(f"\n  {bold('Code Explanation Engine')}")
        print(f"  {dim(f'File: {file_arg} (whole file)')}\n")

    explanation = explainer.explain(
        file_path=file_arg,
        start_line=start_line,
        end_line=end_line,
        function_name=function_name,
    )

    print(format_explanation(explanation))
