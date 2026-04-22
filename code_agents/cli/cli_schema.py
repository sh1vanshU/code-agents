"""CLI schema command — database schema visualizer."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_schema")


def cmd_schema():
    """Visualize database schema as ER diagram.

    Usage:
      code-agents schema --sql-file schema.sql                    # parse SQL file (offline)
      code-agents schema --database mydb                          # scan live database
      code-agents schema --database mydb --schema public          # specific schema
      code-agents schema --sql-file schema.sql --format mermaid   # Mermaid erDiagram
      code-agents schema --sql-file schema.sql --format html      # interactive HTML
      code-agents schema --sql-file schema.sql --output erd.html  # write to file
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    database = ""
    schema = "public"
    fmt = "terminal"
    sql_file = ""
    output_path = ""

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--database" and i + 1 < len(args):
            database = args[i + 1]; i += 1
        elif a == "--schema" and i + 1 < len(args):
            schema = args[i + 1]; i += 1
        elif a == "--format" and i + 1 < len(args):
            fmt = args[i + 1].lower(); i += 1
        elif a == "--sql-file" and i + 1 < len(args):
            sql_file = args[i + 1]; i += 1
        elif a == "--output" and i + 1 < len(args):
            output_path = args[i + 1]; i += 1
        elif a in ("--help", "-h"):
            print(cmd_schema.__doc__)
            return
        i += 1

    if fmt not in ("terminal", "mermaid", "html"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: terminal, mermaid, html"))
        return

    if not sql_file and not database:
        print(red("  Either --sql-file or --database is required."))
        print(dim("  Run: code-agents schema --help"))
        return

    # Lazy import
    from code_agents.api.schema_viz import SchemaVisualizer, format_schema_summary

    viz = SchemaVisualizer(database_url="")

    if sql_file:
        from pathlib import Path
        p = Path(sql_file)
        if not p.exists():
            print(red(f"  File not found: {sql_file}"))
            return
        sql_content = p.read_text(encoding="utf-8")
        print(dim(f"  Parsing {sql_file}..."))
        result = viz.scan_from_sql(sql_content)
    else:
        import asyncio
        print(dim(f"  Scanning {database}.{schema}..."))
        try:
            result = asyncio.run(viz.scan(database=database, schema=schema))
        except Exception as exc:
            print(red(f"  Database error: {exc}"))
            return

    print(green(f"  {format_schema_summary(result)}"))
    print()

    if fmt == "terminal":
        output = viz.generate_terminal(result)
    elif fmt == "mermaid":
        output = viz.generate_mermaid(result)
    else:
        output = viz.generate_html(result)

    if output_path:
        from pathlib import Path as P
        out = P(output_path).resolve()
        out.write_text(output, encoding="utf-8")
        print(green(f"  Written to {out}"))
        if fmt == "html":
            print(dim(f"  Open in browser: file://{out}"))
    else:
        print(output)
