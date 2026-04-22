#!/usr/bin/env python3
"""
Atlassian Rovo MCP client (Jira + Confluence) using OAuth 2.0 (3LO) only:
browser login → localhost callback → access token → MCP Streamable HTTP.

Requires: poetry install --with dev
Configure: ATLASSIAN_OAUTH_CLIENT_ID, ATLASSIAN_OAUTH_CLIENT_SECRET, ATLASSIAN_OAUTH_SCOPES
Optional: ATLASSIAN_OAUTH_REDIRECT_URI (CLI callback; use main app /oauth/atlassian for Open WebUI)

MCP endpoint: https://mcp.atlassian.com/v1/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import httpx
import mcp.types as mcp_types
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, ContentBlock, TextContent

from code_agents.domain.atlassian_oauth import clear_token_cache, get_valid_access_token

DEFAULT_MCP_URL = "https://mcp.atlassian.com/v1/mcp"


def _block_to_text(block: ContentBlock) -> str | None:
    if isinstance(block, TextContent):
        return block.text
    return None


def _print_tool_result(result: CallToolResult) -> None:
    if result.isError:
        print("Tool returned error flag (isError=True).", file=sys.stderr)
    for block in result.content:
        text = _block_to_text(block)
        if text is not None:
            print(text)
        else:
            print(block, file=sys.stderr)
    if result.structuredContent is not None:
        print(json.dumps(result.structuredContent, indent=2, ensure_ascii=False))


async def run_atlassian_session(
    *,
    url: str,
    access_token: str,
    list_tools_only: bool,
    tool_name: str | None,
    tool_args: dict[str, Any],
) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}

    timeout = httpx.Timeout(120.0, connect=30.0)
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read_stream,
            write_stream,
            _get_session_id,
        ):
            async with ClientSession(
                read_stream,
                write_stream,
                client_info=mcp_types.Implementation(
                    name="code-agents-atlassian-example",
                    version="0.1.0",
                ),
            ) as session:
                await session.initialize()

                tools = await session.list_tools()
                if list_tools_only:
                    for t in tools.tools:
                        desc = (t.description or "").strip().replace("\n", " ")[:200]
                        print(f"- {t.name}: {desc}")
                    return

                if not tool_name:
                    print(
                        "Pass --tool NAME and --args JSON (or use --list-tools).",
                        file=sys.stderr,
                    )
                    sys.exit(2)

                result = await session.call_tool(tool_name, tool_args)
                _print_tool_result(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Atlassian Rovo MCP via OAuth 2.0 (browser login + callback) only.",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("ATLASSIAN_MCP_URL", DEFAULT_MCP_URL),
        help="MCP endpoint (default: Rovo MCP)",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List tool names/descriptions and exit",
    )
    parser.add_argument("--tool", default=None, help="Tool name to invoke")
    parser.add_argument(
        "--args",
        default="{}",
        help='JSON object for tool arguments, e.g. \'{"limit": 10}\'',
    )
    parser.add_argument(
        "--force-login",
        action="store_true",
        help="Ignore cache and run full browser login again",
    )
    parser.add_argument(
        "--clear-token-cache",
        action="store_true",
        help="Delete saved OAuth tokens and exit",
    )
    args = parser.parse_args()

    if args.clear_token_cache:
        clear_token_cache()
        print("Token cache cleared.", flush=True)
        return

    try:
        tool_args = json.loads(args.args)
    except json.JSONDecodeError as e:
        print(f"Invalid --args JSON: {e}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(tool_args, dict):
        print("--args must be a JSON object", file=sys.stderr)
        sys.exit(2)

    def _token() -> str:
        return get_valid_access_token(force_login=args.force_login)

    async def _run() -> None:
        access_token = await asyncio.to_thread(_token)
        await run_atlassian_session(
            url=args.url.rstrip("/"),
            access_token=access_token,
            list_tools_only=args.list_tools,
            tool_name=args.tool,
            tool_args=tool_args,
        )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
