"""CLI skill marketplace command — install, search, list, remove community skills."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_skill")


def cmd_skill():
    """Manage skills — list, search, install, remove.

    Usage:
      code-agents skill list                         # list installed skills
      code-agents skill search <query>               # search registry
      code-agents skill install <url-or-name>        # install a skill
      code-agents skill install <url> --agent <name> # install to specific agent
      code-agents skill remove <agent>:<skill>       # remove a skill
      code-agents skill info <agent>:<skill>         # show skill details
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]  # after 'skill'
    if not args or args[0] in ("--help", "-h"):
        print(cmd_skill.__doc__)
        return

    subcmd = args[0]
    rest = args[1:]

    if subcmd == "list":
        _skill_list()
    elif subcmd == "search":
        query = " ".join(rest) if rest else ""
        if not query:
            print(yellow("  Usage: code-agents skill search <query>"))
            return
        _skill_search(query)
    elif subcmd == "install":
        if not rest:
            print(yellow("  Usage: code-agents skill install <url-or-name> [--agent <agent>]"))
            return
        source = rest[0]
        agent = "_shared"
        if "--agent" in rest:
            idx = rest.index("--agent")
            if idx + 1 < len(rest):
                agent = rest[idx + 1]
        _skill_install(source, agent)
    elif subcmd == "remove":
        if not rest:
            print(yellow("  Usage: code-agents skill remove <agent>:<skill>"))
            return
        _skill_remove(rest[0])
    elif subcmd == "info":
        if not rest:
            print(yellow("  Usage: code-agents skill info <agent>:<skill>"))
            return
        _skill_info(rest[0])
    else:
        print(yellow(f"  Unknown subcommand: {subcmd}"))
        print(dim("  Try: list, search, install, remove, info"))


def _skill_list():
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    from code_agents.agent_system.skill_marketplace import list_installed
    installed = list_installed()

    if not installed:
        print(dim("  No community skills installed."))
        print(dim("  Install one: code-agents skill install <url-or-name>"))
        print()
        return

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()

        table = Table(title="Installed Community Skills", show_header=True, header_style="bold cyan")
        table.add_column("Agent", style="bold")
        table.add_column("Skill")
        table.add_column("Description")
        table.add_column("Size", justify="right")

        for agent, skills in installed.items():
            for s in skills:
                size = f"{s['size'] / 1024:.1f}KB" if s["size"] > 1024 else f"{s['size']}B"
                table.add_row(agent, s["name"], s["description"][:60] or dim("—"), size)

        console.print(table)
    except ImportError:
        for agent, skills in installed.items():
            print(f"  {bold(agent)}:")
            for s in skills:
                desc = f" — {s['description'][:60]}" if s["description"] else ""
                print(f"    {s['name']}{desc}")
    print()


def _skill_search(query: str):
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    from code_agents.agent_system.skill_marketplace import search_registry
    results = search_registry(query)

    if not results:
        print(yellow(f"  No skills found for: {query}"))
        print(dim("  Registry may be unavailable. Try again later."))
        return

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()

        table = Table(title=f"Skills matching '{query}'", show_header=True, header_style="bold cyan")
        table.add_column("Name", style="bold")
        table.add_column("Agent")
        table.add_column("Description")
        table.add_column("Author")

        for s in results:
            table.add_row(s.name, s.agent, s.description[:60], s.author or "—")
        console.print(table)
    except ImportError:
        print(f"  Results for '{query}':")
        for s in results:
            print(f"    {bold(s.name)} ({s.agent}) — {s.description[:60]}")
    print()
    print(dim("  Install: code-agents skill install <name>"))
    print()


def _skill_install(source: str, agent: str):
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    from code_agents.agent_system.skill_marketplace import install_skill
    print(f"  Installing from: {cyan(source)}")
    ok, msg = install_skill(source, agent)
    if ok:
        print(f"  {green('✓')} {msg}")
    else:
        print(f"  {red('✗')} {msg}")
    print()


def _skill_remove(spec: str):
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    if ":" not in spec:
        print(yellow("  Format: <agent>:<skill> (e.g. _shared:my-skill)"))
        return

    agent, skill_name = spec.split(":", 1)
    from code_agents.agent_system.skill_marketplace import remove_skill
    ok, msg = remove_skill(agent, skill_name)
    if ok:
        print(f"  {green('✓')} {msg}")
    else:
        print(f"  {red('✗')} {msg}")
    print()


def _skill_info(spec: str):
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    if ":" not in spec:
        print(yellow("  Format: <agent>:<skill>"))
        return

    agent, skill_name = spec.split(":", 1)
    from code_agents.agent_system.skill_marketplace import get_skill_info
    info = get_skill_info(agent, skill_name)

    if not info:
        print(yellow(f"  Skill not found: {spec}"))
        return

    print()
    print(f"  {bold('Name:')}        {info['name']}")
    print(f"  {bold('Agent:')}       {info['agent']}")
    print(f"  {bold('Description:')} {info['description'] or '—'}")
    print(f"  {bold('Path:')}        {dim(info['path'])}")
    print(f"  {bold('Size:')}        {info['size']} bytes")
    print()
    if info.get("content_preview"):
        print(f"  {bold('Preview:')}")
        for line in info["content_preview"].splitlines()[:15]:
            print(f"    {dim(line)}")
    print()
