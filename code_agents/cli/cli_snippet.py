"""CLI snippet library command — save, search, list, delete code snippets."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_snippet")


def cmd_snippet():
    """Manage code snippets — search, save, list, delete.

    Usage:
      code-agents snippet search <query>           # search snippets
      code-agents snippet save <name> --file <f>   # save from file
      code-agents snippet save <name> --code "..." # save inline
      code-agents snippet list [--tag <tag>]       # list all snippets
      code-agents snippet delete <name>            # delete a snippet
      code-agents snippet show <name>              # show snippet details
    """
    from .cli_helpers import _colors, _user_cwd
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]  # after 'snippet'
    if not args or args[0] in ("--help", "-h"):
        print(cmd_snippet.__doc__)
        return

    subcmd = args[0]
    rest = args[1:]

    if subcmd == "search":
        query = " ".join(rest) if rest else ""
        if not query:
            print(yellow("  Usage: code-agents snippet search <query>"))
            return
        _snippet_search(query)
    elif subcmd == "save":
        _snippet_save(rest)
    elif subcmd == "list":
        tag = ""
        if "--tag" in rest:
            idx = rest.index("--tag")
            if idx + 1 < len(rest):
                tag = rest[idx + 1]
        _snippet_list(tag)
    elif subcmd == "delete":
        if not rest:
            print(yellow("  Usage: code-agents snippet delete <name>"))
            return
        _snippet_delete(rest[0])
    elif subcmd == "show":
        if not rest:
            print(yellow("  Usage: code-agents snippet show <name>"))
            return
        _snippet_show(rest[0])
    else:
        print(yellow(f"  Unknown subcommand: {subcmd}"))
        print(dim("  Try: search, save, list, delete, show"))


def _snippet_search(query: str):
    from .cli_helpers import _colors, _user_cwd
    bold, green, yellow, red, cyan, dim = _colors()

    from code_agents.ui.snippet_library import SnippetLibrary
    lib = SnippetLibrary(cwd=_user_cwd())
    results = lib.search(query)

    if not results:
        print(yellow(f"  No snippets found for: {query}"))
        return

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title=f"Snippets matching '{query}'", show_header=True, header_style="bold cyan")
        table.add_column("Name", style="bold")
        table.add_column("Language")
        table.add_column("Tags")
        table.add_column("Description")
        for s in results:
            table.add_row(s.name, s.language, ", ".join(s.tags), s.description[:60] or dim("--"))
        console.print(table)
    except ImportError:
        for s in results:
            tags = ", ".join(s.tags) if s.tags else ""
            print(f"  {bold(s.name)} [{s.language}] {tags} — {s.description[:60]}")
    print()


def _snippet_save(rest: list[str]):
    from .cli_helpers import _colors, _user_cwd
    bold, green, yellow, red, cyan, dim = _colors()

    if not rest:
        print(yellow("  Usage: code-agents snippet save <name> --file <f> | --code \"...\""))
        return

    name = rest[0]
    code = ""
    language = ""
    tags: list[str] = []
    description = ""

    if "--file" in rest:
        idx = rest.index("--file")
        if idx + 1 < len(rest):
            fpath = rest[idx + 1]
            try:
                with open(fpath) as f:
                    code = f.read()
                # Infer language from extension
                if fpath.endswith(".py"):
                    language = "python"
                elif fpath.endswith(".js"):
                    language = "javascript"
                elif fpath.endswith(".ts"):
                    language = "typescript"
                elif fpath.endswith(".go"):
                    language = "go"
                elif fpath.endswith(".java"):
                    language = "java"
            except OSError as exc:
                print(red(f"  Cannot read file: {exc}"))
                return
    elif "--code" in rest:
        idx = rest.index("--code")
        if idx + 1 < len(rest):
            code = rest[idx + 1]

    if "--language" in rest:
        idx = rest.index("--language")
        if idx + 1 < len(rest):
            language = rest[idx + 1]

    if "--tags" in rest:
        idx = rest.index("--tags")
        if idx + 1 < len(rest):
            tags = [t.strip() for t in rest[idx + 1].split(",")]

    if "--description" in rest:
        idx = rest.index("--description")
        if idx + 1 < len(rest):
            description = rest[idx + 1]

    if not code:
        print(yellow("  No code provided. Use --file <path> or --code \"...\""))
        return

    from code_agents.ui.snippet_library import SnippetLibrary
    lib = SnippetLibrary(cwd=_user_cwd())
    snippet = lib.save(name, code, language=language, tags=tags, description=description)
    print(f"  {green('✓')} Saved snippet: {bold(snippet.name)} [{snippet.language}]")
    print()


def _snippet_list(tag: str = ""):
    from .cli_helpers import _colors, _user_cwd
    bold, green, yellow, red, cyan, dim = _colors()

    from code_agents.ui.snippet_library import SnippetLibrary
    lib = SnippetLibrary(cwd=_user_cwd())
    snippets = lib.list_snippets(tag=tag)

    if not snippets:
        print(dim("  No snippets found."))
        print(dim("  Save one: code-agents snippet save <name> --file code.py"))
        print()
        return

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title="Snippet Library", show_header=True, header_style="bold cyan")
        table.add_column("Name", style="bold")
        table.add_column("Language")
        table.add_column("Tags")
        table.add_column("Description")
        for s in snippets:
            table.add_row(s.name, s.language, ", ".join(s.tags), s.description[:60] or dim("--"))
        console.print(table)
    except ImportError:
        for s in snippets:
            tags = ", ".join(s.tags) if s.tags else ""
            print(f"  {bold(s.name)} [{s.language}] {tags} — {s.description[:60]}")
    print()


def _snippet_delete(name: str):
    from .cli_helpers import _colors, _user_cwd
    bold, green, yellow, red, cyan, dim = _colors()

    from code_agents.ui.snippet_library import SnippetLibrary
    lib = SnippetLibrary(cwd=_user_cwd())
    ok = lib.delete(name)
    if ok:
        print(f"  {green('✓')} Deleted snippet: {name}")
    else:
        print(f"  {red('✗')} Snippet not found: {name}")
    print()


def _snippet_show(name: str):
    from .cli_helpers import _colors, _user_cwd
    bold, green, yellow, red, cyan, dim = _colors()

    from code_agents.ui.snippet_library import SnippetLibrary
    lib = SnippetLibrary(cwd=_user_cwd())
    snippet = lib.get(name)
    if not snippet:
        print(yellow(f"  Snippet not found: {name}"))
        return

    print()
    print(f"  {bold('Name:')}        {snippet.name}")
    print(f"  {bold('Language:')}    {snippet.language}")
    print(f"  {bold('Tags:')}        {', '.join(snippet.tags) or '—'}")
    print(f"  {bold('Description:')} {snippet.description or '—'}")
    print()
    print(f"  {bold('Code:')}")
    for line in snippet.code.splitlines()[:20]:
        print(f"    {dim(line)}")
    if len(snippet.code.splitlines()) > 20:
        print(f"    {dim('... (truncated)')}")
    print()
