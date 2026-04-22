"""CLI visual-test command — visual regression testing."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_visual_test")


def cmd_visual_test():
    """Visual regression testing — capture and compare page snapshots.

    Usage:
      code-agents visual-test --url http://localhost:3000 --name homepage   # capture baseline
      code-agents visual-test --url http://localhost:3000 --compare         # compare against baseline
      code-agents visual-test --list                                        # list baselines
      code-agents visual-test --delete homepage                             # delete a baseline
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    if not args or args[0] in ("--help", "-h"):
        print(cmd_visual_test.__doc__)
        return

    url = ""
    name = ""
    compare_mode = "--compare" in args
    list_mode = "--list" in args
    delete_name = ""

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--url" and i + 1 < len(args):
            url = args[i + 1]
            i += 1
        elif a == "--name" and i + 1 < len(args):
            name = args[i + 1]
            i += 1
        elif a == "--delete" and i + 1 < len(args):
            delete_name = args[i + 1]
            i += 1
        i += 1

    from code_agents.testing.visual_regression import VisualRegressionTester

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    tester = VisualRegressionTester(cwd)

    if list_mode:
        baselines = tester.list_baselines()
        if not baselines:
            print(dim("  No baselines found."))
            return
        print(bold(f"  Visual Baselines ({len(baselines)})"))
        print()
        for b in baselines:
            print(f"  {b['name']}")
            if "url" in b:
                print(dim(f"    URL: {b['url']}"))
            if "captured_at" in b:
                print(dim(f"    Captured: {b['captured_at']}"))
        print()
        return

    if delete_name:
        if tester.delete_baseline(delete_name):
            print(green(f"  Deleted baseline: {delete_name}"))
        else:
            print(yellow(f"  Baseline not found: {delete_name}"))
        return

    if not url:
        print(yellow("  --url is required. Use --help for usage."))
        return

    if compare_mode:
        print(dim(f"  Comparing {url} against baseline..."))
        diff = tester.compare(url, name=name)
        print()
        if diff.passed:
            print(green(f"  PASS: {diff.name} ({diff.diff_percentage:.2f}% diff)"))
        else:
            print(red(f"  FAIL: {diff.name} ({diff.diff_percentage:.2f}% diff)"))
        print(dim(f"  Baseline: {diff.baseline_path}"))
        print(dim(f"  Current:  {diff.current_path}"))
        print()
    else:
        print(dim(f"  Capturing baseline for {url}..."))
        path = tester.capture(url, name=name)
        print(green(f"  Baseline saved: {path}"))
