"""CLI command for automated API documentation generation."""

from __future__ import annotations

import json
import logging
import os
import sys

from .cli_helpers import _colors

logger = logging.getLogger("code_agents.cli.cli_api_docs")


def cmd_api_docs(rest: list[str] | None = None):
    """Generate API documentation from source code.

    Usage:
      code-agents api-docs                          # terminal table
      code-agents api-docs --format openapi          # OpenAPI JSON to stdout
      code-agents api-docs --format markdown         # Markdown to stdout
      code-agents api-docs --format html             # HTML to stdout
      code-agents api-docs --format openapi --output api.json
    """
    bold, green, yellow, red, cyan, dim = _colors()
    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    args = rest or []

    # Parse flags
    fmt = "terminal"
    output_path = ""

    i = 0
    while i < len(args):
        if args[i] == "--format" and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 1
        elif args[i] == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 1
        i += 1

    print()
    print(bold(cyan("  Automated API Documentation Generator")))
    print(dim(f"  Scanning {cwd}..."))
    print()

    from code_agents.api.api_docs import APIDocGenerator, format_api_summary

    gen = APIDocGenerator(cwd=cwd)
    result = gen.scan()

    if not result.routes:
        print(yellow("  No API routes discovered."))
        print(dim("  Supports: FastAPI, Flask, Spring Boot, Express"))
        print()
        return

    if fmt == "openapi":
        spec = gen.generate_openapi(result)
        text = json.dumps(spec, indent=2)
    elif fmt == "markdown":
        text = gen.generate_markdown(result)
    elif fmt == "html":
        text = gen.generate_html(result)
    else:
        text = format_api_summary(result)

    if output_path:
        out = os.path.join(cwd, output_path) if not os.path.isabs(output_path) else output_path
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(green(f"  Saved: {out}"))
        print(dim(f"  {len(result.routes)} endpoints ({result.framework})"))
    else:
        print(text)

    print()
