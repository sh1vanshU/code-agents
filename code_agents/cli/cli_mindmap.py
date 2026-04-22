"""CLI mindmap command — generate a visual mindmap of the repository."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_mindmap")


def cmd_mindmap():
    """Generate a visual mindmap of the repository.

    Usage:
      code-agents mindmap                    # terminal ASCII tree (default)
      code-agents mindmap --format mermaid   # Mermaid mindmap syntax
      code-agents mindmap --format html      # interactive HTML with D3.js
      code-agents mindmap --depth 5          # tree depth (default 3)
      code-agents mindmap --focus src/       # focus on a subdirectory
      code-agents mindmap --output map.html  # write to file instead of stdout
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]  # everything after 'mindmap'
    fmt = "text"
    depth = 3
    focus = None
    output_path = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--format" and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 1
        elif a == "--depth" and i + 1 < len(args):
            try:
                depth = int(args[i + 1])
            except ValueError:
                print(red(f"  Invalid depth: {args[i + 1]}"))
                return
            i += 1
        elif a == "--focus" and i + 1 < len(args):
            focus = args[i + 1]
            i += 1
        elif a == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_mindmap.__doc__)
            return
        i += 1

    if fmt not in ("text", "mermaid", "html"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: text, mermaid, html"))
        return

    # Lazy import
    from code_agents.ui.mindmap import RepoMindmap, format_terminal, format_mermaid, format_html

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Scanning {repo_path}..."))

    try:
        mindmap = RepoMindmap(repo_path=repo_path, depth=depth, focus=focus)
        result = mindmap.build()
    except ValueError as exc:
        print(red(f"  Error: {exc}"))
        return

    if fmt == "text":
        output = format_terminal(result, depth=depth)
    elif fmt == "mermaid":
        output = format_mermaid(result)
    else:
        output = format_html(result)

    if output_path:
        from pathlib import Path
        out = Path(output_path).resolve()
        out.write_text(output, encoding="utf-8")
        print(green(f"  Written to {out}"))
        if fmt == "html":
            print(dim(f"  Open in browser: file://{out}"))
    else:
        print(output)
