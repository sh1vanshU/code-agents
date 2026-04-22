"""CLI commands for git hooks — install and run hook analysis."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_hooks")


def cmd_install_hooks():
    """Install AI-powered git hooks (pre-commit, pre-push).

    Usage:
      code-agents install-hooks              # install both hooks
      code-agents install-hooks --uninstall  # remove hooks, restore backups
      code-agents install-hooks --status     # show which hooks are installed
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    from code_agents.git_ops.git_hooks import GitHooksManager
    manager = GitHooksManager(cwd)

    if "--status" in args:
        status = manager.status()
        print()
        print(bold("  Git Hooks Status"))
        print()
        for hook, installed in status.items():
            icon = green("installed") if installed else dim("not installed")
            print(f"  {hook:15s} {icon}")
        print()
        return

    if "--uninstall" in args:
        removed = manager.uninstall()
        if removed:
            print(green(f"  Uninstalled hooks: {', '.join(removed)}"))
        else:
            print(yellow("  No code-agents hooks found to remove."))
        return

    if "--help" in args or "-h" in args:
        print(cmd_install_hooks.__doc__)
        return

    installed = manager.install()
    if installed:
        print(green(f"  Installed hooks: {', '.join(installed)}"))
        print(dim("  Existing hooks backed up as <name>.backup"))
    else:
        print(red("  Failed to install hooks — is this a git repository?"))


def cmd_hook_run():
    """Run hook analysis (called by git hook scripts).

    Usage:
      code-agents hook-run pre-commit
      code-agents hook-run pre-push
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    hook_type = args[0] if args else "pre-commit"

    from code_agents.git_ops.git_hooks import (
        PreCommitAnalyzer,
        PrePushAnalyzer,
        render_hook_report,
    )

    if hook_type == "pre-commit":
        analyzer = PreCommitAnalyzer(cwd)
    elif hook_type == "pre-push":
        analyzer = PrePushAnalyzer(cwd)
    else:
        print(red(f"  Unknown hook type: {hook_type}"))
        sys.exit(1)

    report = analyzer.analyze()
    print(render_hook_report(report))

    if not report.passed:
        print(red("  Hook blocked the operation. Fix critical issues above."))
        print(dim("  To bypass: git commit --no-verify / git push --no-verify"))
        sys.exit(1)
