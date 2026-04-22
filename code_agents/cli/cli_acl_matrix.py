"""CLI acl-matrix command — generate access control matrix from codebase."""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_acl_matrix")


def cmd_acl_matrix():
    """Generate ACL matrix from role and endpoint analysis.

    Usage:
      code-agents acl-matrix                       # text report
      code-agents acl-matrix --format json         # JSON output
      code-agents acl-matrix --format markdown     # Markdown table
      code-agents acl-matrix --output matrix.json  # write to file
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    fmt = "text"
    output_path = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--format" and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 1
        elif a == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_acl_matrix.__doc__)
            return
        i += 1

    if fmt not in ("text", "json", "markdown"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: text, json, markdown"))
        return

    from code_agents.security.acl_matrix import (
        ACLMatrixGenerator,
        acl_matrix_to_json,
        format_acl_markdown,
    )

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Scanning {repo_path} for roles and permissions..."))

    gen = ACLMatrixGenerator(cwd=repo_path)
    matrix = gen.generate()

    if fmt == "json":
        output = json.dumps(acl_matrix_to_json(matrix), indent=2)
    elif fmt == "markdown":
        output = format_acl_markdown(matrix)
    else:
        output = gen.format_matrix(matrix)

    if output_path:
        from pathlib import Path
        out = Path(output_path).resolve()
        out.write_text(output, encoding="utf-8")
        print(green(f"  ACL matrix written to {out}"))
    else:
        print(output)
