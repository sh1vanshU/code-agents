"""CLI code ownership command — analyze git blame for ownership and bus factor."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_ownership")


def cmd_ownership():
    """Analyze code ownership from git blame.

    Usage:
      code-agents ownership                    # show ownership analysis
      code-agents ownership --generate-codeowners  # generate CODEOWNERS file
      code-agents ownership --silos            # find knowledge silos (bus_factor=1)
      code-agents ownership --json             # JSON output
    """
    from .cli_helpers import _colors, _user_cwd
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]  # after 'ownership'
    if args and args[0] in ("--help", "-h"):
        print(cmd_ownership.__doc__)
        return

    from code_agents.knowledge.code_ownership import CodeOwnershipMapper
    mapper = CodeOwnershipMapper(cwd=_user_cwd())

    if "--generate-codeowners" in args:
        content = mapper.generate_codeowners()
        if "--output" in args:
            idx = args.index("--output")
            if idx + 1 < len(args):
                with open(args[idx + 1], "w") as f:
                    f.write(content)
                print(f"  {green('✓')} CODEOWNERS written to {args[idx + 1]}")
                print()
                return
        print(content)
        return

    if "--silos" in args:
        silos = mapper._find_knowledge_silos()
        if not silos:
            print(f"  {green('✓')} No knowledge silos found (all dirs have bus_factor > 1)")
        else:
            print(f"  {red('⚠ Knowledge silos')} (bus_factor = 1):")
            for s in silos:
                print(f"    {yellow(s)}")
        print()
        return

    # Default: show ownership table
    print(f"\n  {dim('Analyzing git blame (this may take a moment)...')}")
    ownership = mapper.analyze()

    if not ownership:
        print(yellow("  No ownership data found. Is this a git repo with history?"))
        print()
        return

    json_output = "--json" in args
    if json_output:
        import json
        data = [
            {"path": o.path, "primary_owner": o.primary_owner,
             "contributors": o.contributors, "bus_factor": o.bus_factor}
            for o in ownership
        ]
        print(json.dumps(data, indent=2))
        return

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title="Code Ownership", show_header=True, header_style="bold cyan")
        table.add_column("Path", style="bold")
        table.add_column("Primary Owner")
        table.add_column("Bus Factor", justify="center")
        table.add_column("Contributors")
        for o in ownership:
            bf_color = "red" if o.bus_factor <= 1 else ("yellow" if o.bus_factor == 2 else "green")
            table.add_row(
                o.path,
                o.primary_owner,
                f"[{bf_color}]{o.bus_factor}[/{bf_color}]",
                ", ".join(o.contributors[:3]) + ("..." if len(o.contributors) > 3 else ""),
            )
        console.print(table)
    except ImportError:
        print()
        print(bold("  Code Ownership:"))
        for o in ownership:
            bf_warn = f" {red('⚠ SILO')}" if o.bus_factor <= 1 else ""
            print(f"    {bold(o.path)}: {o.primary_owner} (bus_factor={o.bus_factor}){bf_warn}")
    print()
