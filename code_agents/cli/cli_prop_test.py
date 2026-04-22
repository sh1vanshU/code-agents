"""CLI property test command — generate Hypothesis property-based tests."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_prop_test")


def cmd_prop_test():
    """Generate property-based tests using Hypothesis.

    Usage:
      code-agents prop-test <file>                      # all functions
      code-agents prop-test <file> --function encode     # specific function
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    if not args or args[0] in ("--help", "-h"):
        print(cmd_prop_test.__doc__)
        return

    file_path = args[0]
    function = ""

    i = 1
    while i < len(args):
        if args[i] in ("--function", "--fn", "-f") and i + 1 < len(args):
            function = args[i + 1]
            i += 1
        i += 1

    from code_agents.testing.property_tests import PropertyTestGenerator

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    gen = PropertyTestGenerator(cwd)

    print(dim(f"  Generating property tests for {file_path}..."))
    if function:
        print(dim(f"  Function: {function}"))
    print()

    result = gen.generate(file_path, function=function)
    print(result)
