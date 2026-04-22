"""CLI team-kb command — manage team knowledge base."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_team_kb")


def cmd_team_kb():
    """Manage the team knowledge base.

    Usage:
      code-agents team-kb list                                              # list all topics
      code-agents team-kb add "deployment" --content "Always deploy dev first"  # add entry
      code-agents team-kb get "deployment"                                  # view entry
      code-agents team-kb search "deploy"                                   # search entries
      code-agents team-kb delete "deployment"                               # delete entry
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    sub = args[0] if args else "list"

    if sub in ("--help", "-h"):
        print(cmd_team_kb.__doc__)
        return

    from code_agents.knowledge.team_knowledge import TeamKnowledgeBase

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    kb = TeamKnowledgeBase(cwd)

    if sub in ("list", "ls"):
        topics = kb.list_topics()
        if not topics:
            print(dim("  No knowledge base entries found."))
            print(dim("  Add one: code-agents team-kb add \"topic\" --content \"...\""))
            return
        print(bold(f"  Team Knowledge Base ({len(topics)} topics)"))
        print()
        for t in topics:
            print(f"  - {t}")
        print()

    elif sub == "add":
        if len(args) < 2:
            print(yellow("  Usage: code-agents team-kb add \"topic\" --content \"...\""))
            return
        topic = args[1]
        content = ""
        author = ""

        i = 2
        while i < len(args):
            if args[i] == "--content" and i + 1 < len(args):
                content = args[i + 1]
                i += 1
            elif args[i] == "--author" and i + 1 < len(args):
                author = args[i + 1]
                i += 1
            i += 1

        if not content:
            print(yellow("  --content is required."))
            return

        result = kb.add(topic, content, author=author)
        if "error" in result:
            print(red(f"  Error: {result['error']}"))
        else:
            print(green(f"  {result['action'].title()}: {topic}"))
            print(dim(f"  Path: {result['path']}"))

    elif sub == "get":
        if len(args) < 2:
            print(yellow("  Usage: code-agents team-kb get \"topic\""))
            return
        topic = args[1]
        entry = kb.get(topic)
        if not entry:
            print(yellow(f"  Topic not found: {topic}"))
            return
        print(bold(f"  {entry['topic']}"))
        if entry.get("author"):
            print(dim(f"  Author: {entry['author']}"))
        if entry.get("updated"):
            print(dim(f"  Updated: {entry['updated']}"))
        print()
        print(entry["content"])
        print()

    elif sub == "search":
        if len(args) < 2:
            print(yellow("  Usage: code-agents team-kb search \"query\""))
            return
        query = args[1]
        results = kb.search(query)
        if not results:
            print(dim(f"  No results for: {query}"))
            return
        print(bold(f"  Search results for '{query}' ({len(results)})"))
        print()
        for r in results:
            print(f"  {r['topic']}")
            print(dim(f"    {r.get('preview', '')[:100]}"))
        print()

    elif sub == "delete":
        if len(args) < 2:
            print(yellow("  Usage: code-agents team-kb delete \"topic\""))
            return
        topic = args[1]
        if kb.delete(topic):
            print(green(f"  Deleted: {topic}"))
        else:
            print(yellow(f"  Topic not found: {topic}"))

    else:
        print(yellow(f"  Unknown subcommand: {sub}"))
        print(dim("  Usage: code-agents team-kb [list|add|get|search|delete]"))
