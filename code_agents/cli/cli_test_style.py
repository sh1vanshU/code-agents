"""CLI test-style command — analyze and match test conventions."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_test_style")


def cmd_test_style():
    """Analyze project test style or generate matching tests.

    Usage:
      code-agents test-style --analyze                   # detect style profile
      code-agents test-style --generate src/api.py       # generate matching tests
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    if not args or args[0] in ("--help", "-h"):
        print(cmd_test_style.__doc__)
        return

    analyze = "--analyze" in args
    generate_file = ""

    i = 0
    while i < len(args):
        if args[i] == "--generate" and i + 1 < len(args):
            generate_file = args[i + 1]
            i += 1
        i += 1

    from code_agents.testing.test_style import TestStyleAnalyzer

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    analyzer = TestStyleAnalyzer(cwd)

    if analyze or not generate_file:
        print(dim("  Analyzing test style..."))
        print()
        profile = analyzer.analyze()
        print(bold("  Test Style Profile"))
        print()
        for line in profile.summary().splitlines():
            print(f"  {line}")
        print()

    if generate_file:
        print(dim(f"  Generating tests matching style for {generate_file}..."))
        print()
        result = analyzer.generate_matching(generate_file)
        print(result)
