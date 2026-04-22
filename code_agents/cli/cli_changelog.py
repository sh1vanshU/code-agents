"""CLI subcommand: code-agents changelog <from>..<to> [--format markdown|terminal] [--output FILE]."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_changelog")


def cmd_changelog_v2(rest: list[str] | None = None):
    """Generate changelog between two git refs with PR enrichment.

    Usage:
      code-agents changelog v1.0.0..v1.1.0
      code-agents changelog v1.0.0..HEAD --format markdown
      code-agents changelog v1.0.0..v1.1.0 --output CHANGELOG.md
      code-agents changelog v1.0.0..HEAD --format terminal
    """
    from code_agents.git_ops.changelog import ChangelogGenerator

    rest = rest or []

    # ── Parse flags ──────────────────────────────────────────────────
    fmt = "terminal"
    output_path: str | None = None
    ref_range: str | None = None

    i = 0
    positional: list[str] = []
    while i < len(rest):
        arg = rest[i]
        if arg == "--format" and i + 1 < len(rest):
            fmt = rest[i + 1]
            i += 2
            continue
        elif arg == "--output" and i + 1 < len(rest):
            output_path = rest[i + 1]
            i += 2
            continue
        elif not arg.startswith("-"):
            positional.append(arg)
        i += 1

    # First positional should be <from>..<to>
    if positional:
        ref_range = positional[0]

    if not ref_range or ".." not in ref_range:
        print()
        print("  Usage: code-agents changelog <from>..<to> [--format markdown|terminal] [--output FILE]")
        print()
        print("  Examples:")
        print("    code-agents changelog v1.0.0..HEAD")
        print("    code-agents changelog v1.0.0..v1.1.0 --format markdown --output CHANGELOG.md")
        print()
        return

    parts = ref_range.split("..", 1)
    from_ref = parts[0]
    to_ref = parts[1] if parts[1] else "HEAD"

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()

    gen = ChangelogGenerator(cwd=cwd)
    changelog = gen.generate(from_ref=from_ref, to_ref=to_ref)

    if fmt == "markdown":
        text = gen.format_markdown(changelog)
    else:
        text = gen.format_terminal(changelog)

    if output_path:
        written = gen.write_markdown(changelog, filepath=output_path)
        print()
        print(f"  Changelog written to: {written}")
        print()
    else:
        print(text)
        print()
