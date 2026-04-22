"""CLI subcommand: code-agents release-notes <from>..<to> [--format markdown|slack]."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_release_notes")


def cmd_release_notes(rest: list[str] | None = None):
    """Generate release notes from git history between two refs.

    Usage:
      code-agents release-notes v1.0..v1.1
      code-agents release-notes v1.0..HEAD --format markdown
      code-agents release-notes v1.0..v1.1 --format slack
      code-agents release-notes v1.0..v1.1 --output RELEASE.md
    """
    rest = rest or sys.argv[2:]
    fmt = "markdown"
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
        elif arg in ("--help", "-h"):
            print(cmd_release_notes.__doc__)
            return
        elif not arg.startswith("-"):
            positional.append(arg)
        i += 1

    if positional:
        ref_range = positional[0]

    if not ref_range or ".." not in ref_range:
        print()
        print("  Usage: code-agents release-notes <from>..<to> [--format markdown|slack] [--output FILE]")
        print()
        print("  Examples:")
        print("    code-agents release-notes v1.0.0..HEAD")
        print("    code-agents release-notes v1.0.0..v1.1.0 --format slack")
        print("    code-agents release-notes v1.0.0..HEAD --output RELEASE_NOTES.md")
        print()
        return

    parts = ref_range.split("..", 1)
    from_ref = parts[0]
    to_ref = parts[1] if parts[1] else "HEAD"

    from code_agents.git_ops.release_notes import ReleaseNotesGenerator

    cwd = os.environ.get("TARGET_REPO_PATH") or os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    gen = ReleaseNotesGenerator(cwd=cwd)
    notes = gen.generate(from_ref=from_ref, to_ref=to_ref)

    if fmt == "slack":
        text = gen.format_slack(notes)
    else:
        text = gen.format_markdown(notes)

    if output_path:
        with open(output_path, "w") as f:
            f.write(text)
        print()
        print(f"  Release notes written to: {output_path}")
        print()
    else:
        print(text)
