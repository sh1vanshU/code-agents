"""CLI browse command — browser interaction agent."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_browse")


def cmd_browse():
    """Browse a URL and extract content or API docs.

    Usage:
      code-agents browse --url https://docs.example.com               # fetch and show text
      code-agents browse --url https://docs.example.com --extract-api  # scrape API docs
      code-agents browse --url https://docs.example.com --links        # show all links
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    if not args or args[0] in ("--help", "-h"):
        print(cmd_browse.__doc__)
        return

    url = ""
    extract_api = "--extract-api" in args
    show_links = "--links" in args

    i = 0
    while i < len(args):
        if args[i] == "--url" and i + 1 < len(args):
            url = args[i + 1]
            i += 1
        i += 1

    if not url:
        print(yellow("  --url is required. Use --help for usage."))
        return

    from code_agents.ui.browser_agent import BrowserAgent

    agent = BrowserAgent()

    if extract_api:
        print(dim(f"  Extracting API docs from {url}..."))
        print()
        docs = agent.extract_api_docs(url)
        if not docs:
            print(dim("  No API endpoints found."))
            return
        print(bold(f"  API Endpoints ({len(docs)})"))
        print()
        for d in docs:
            print(f"  {d['method']:8s} {d['path']}")
        print()
    elif show_links:
        print(dim(f"  Fetching links from {url}..."))
        result = agent.navigate(url)
        print()
        print(bold(f"  Links ({len(result['links'])})"))
        print()
        for link in result["links"][:50]:
            print(f"  {link}")
        if len(result["links"]) > 50:
            print(dim(f"  ... ({len(result['links']) - 50} more)"))
        print()
    else:
        print(dim(f"  Navigating to {url}..."))
        result = agent.navigate(url)
        print()
        print(bold(f"  {result['title']}"))
        print(dim(f"  Status: {result['status']} | {result['content_length']} bytes | {len(result['links'])} links"))
        print()
        # Show text preview
        text = result["text"][:3000]
        for line in text.splitlines()[:50]:
            print(f"  {line}")
        if len(result["text"]) > 3000:
            print(dim(f"  ... (truncated, {len(result['text'])} total chars)"))
        print()
