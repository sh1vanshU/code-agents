"""CLI environment diff command — compare .env files across environments."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_env_diff")


def cmd_env_diff():
    """Compare environment configs between environments.

    Usage:
      code-agents env-diff dev staging        # compare dev vs staging
      code-agents env-diff dev prod --json    # JSON output
      code-agents env-diff --list             # list available environments
    """
    from .cli_helpers import _colors, _user_cwd
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]  # after 'env-diff'
    if not args or args[0] in ("--help", "-h"):
        print(cmd_env_diff.__doc__)
        return

    if args[0] == "--list":
        _env_diff_list()
        return

    if len(args) < 2:
        print(yellow("  Usage: code-agents env-diff <env_a> <env_b>"))
        return

    env_a = args[0]
    env_b = args[1]
    json_output = "--json" in args

    from code_agents.devops.env_diff import EnvDiffChecker
    checker = EnvDiffChecker(cwd=_user_cwd())
    result = checker.compare(env_a, env_b)

    if json_output:
        import json
        print(json.dumps({
            "env_a": result.env_a,
            "env_b": result.env_b,
            "missing_in_b": result.missing_in_b,
            "missing_in_a": result.missing_in_a,
            "different_values": result.different_values,
            "secrets_differ": result.secrets_differ,
            "total_diffs": result.total_diffs,
        }, indent=2))
        return

    print()
    print(bold(f"  Environment Diff: {env_a} vs {env_b}"))
    print()

    if not result.has_differences:
        print(f"  {green('✓')} No differences found")
        print()
        return

    if result.missing_in_b:
        print(f"  {red(f'Missing in {env_b}:')} ({len(result.missing_in_b)})")
        for key in result.missing_in_b:
            print(f"    - {yellow(key)}")
        print()

    if result.missing_in_a:
        print(f"  {red(f'Missing in {env_a}:')} ({len(result.missing_in_a)})")
        for key in result.missing_in_a:
            print(f"    - {yellow(key)}")
        print()

    if result.different_values:
        print(f"  {cyan('Different values:')} ({len(result.different_values)})")
        for diff in result.different_values:
            key = diff["key"]
            val_a = diff["value_a"]
            val_b = diff["value_b"]
            secret_tag = f" {red('[SECRET]')}" if diff.get("is_secret") else ""
            print(f"    {bold(key)}{secret_tag}")
            print(f"      {env_a}: {dim(val_a)}")
            print(f"      {env_b}: {dim(val_b)}")
        print()

    if result.secrets_differ:
        print(f"  {red('⚠ Secrets that differ:')} {', '.join(result.secrets_differ)}")
        print()

    print(f"  {dim('Summary:')} {result.summary()}")
    print()


def _env_diff_list():
    from .cli_helpers import _colors, _user_cwd
    bold, green, yellow, red, cyan, dim = _colors()

    from code_agents.devops.env_diff import EnvDiffChecker
    checker = EnvDiffChecker(cwd=_user_cwd())
    envs = checker.list_environments()

    if not envs:
        print(dim("  No environment files found."))
        print(dim("  Expected: .env.dev, .env.staging, .env.prod, etc."))
        print()
        return

    print()
    print(bold("  Available Environments:"))
    for env in envs:
        print(f"    {cyan(env)}")
    print()
    print(dim("  Compare: code-agents env-diff <env_a> <env_b>"))
    print()
