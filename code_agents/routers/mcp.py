"""
MCP (Model Context Protocol) router: manage MCP servers and invoke tools.

Provides endpoints to list configured servers, discover tools, start/stop
servers, and call tools on running MCP servers.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from code_agents.integrations.mcp_client import (
    MCPServer,
    call_tool,
    get_servers_for_agent,
    list_tools,
    load_mcp_config,
    start_stdio_server,
    stop_server,
)

logger = logging.getLogger("code_agents.routers.mcp")
router = APIRouter(prefix="/mcp", tags=["mcp"])

# In-memory cache of started servers (keyed by name)
_active_servers: dict[str, MCPServer] = {}


def _repo_path() -> str:
    return os.getenv("TARGET_REPO_PATH", "") or os.getcwd()


# ── Models ────────────────────────────────────────────────────────────────


class ToolCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class ServerInfo(BaseModel):
    name: str
    transport: str  # "stdio" or "sse"
    command: str = ""
    url: str = ""
    agents: list[str] = Field(default_factory=list)
    running: bool = False


class ToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict = Field(default_factory=dict)
    server_name: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/servers", response_model=list[ServerInfo])
async def list_servers():
    """List all configured MCP servers."""
    logger.info("Listing MCP servers")
    servers = load_mcp_config(_repo_path())
    return [
        ServerInfo(
            name=s.name,
            transport="stdio" if s.is_stdio else "sse",
            command=s.command,
            url=s.url,
            agents=s.agents,
            running=s.name in _active_servers,
        )
        for s in servers.values()
    ]


@router.get("/servers/{name}/tools", response_model=list[ToolInfo])
async def get_server_tools(name: str):
    """List tools available from an MCP server. Starts the server if needed."""
    servers = load_mcp_config(_repo_path())
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not configured")

    server = _active_servers.get(name, servers[name])

    # Auto-start stdio servers if not running
    if server.is_stdio and server._process is None:
        await start_stdio_server(server)
        _active_servers[name] = server

    tools = await list_tools(server)
    return [
        ToolInfo(
            name=t.name,
            description=t.description,
            input_schema=t.input_schema,
            server_name=t.server_name,
        )
        for t in tools
    ]


@router.post("/servers/{name}/tools/{tool_name}")
async def invoke_tool(name: str, tool_name: str, body: ToolCallRequest):
    """Call a tool on an MCP server."""
    if name not in _active_servers:
        # Try to start it
        servers = load_mcp_config(_repo_path())
        if name not in servers:
            raise HTTPException(status_code=404, detail=f"MCP server '{name}' not configured")
        server = servers[name]
        if server.is_stdio:
            await start_stdio_server(server)
            _active_servers[name] = server
        else:
            _active_servers[name] = server

    server = _active_servers[name]
    result = await call_tool(server, tool_name, body.arguments)
    if result is None:
        raise HTTPException(status_code=502, detail=f"No response from MCP server '{name}'")
    return {"result": result}


@router.post("/servers/{name}/start")
async def start_server(name: str):
    """Start a stdio MCP server."""
    servers = load_mcp_config(_repo_path())
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not configured")

    server = servers[name]
    if not server.is_stdio:
        return {"status": "ok", "message": f"SSE server '{name}' does not need starting"}

    if name in _active_servers and _active_servers[name]._process:
        return {"status": "ok", "message": f"Server '{name}' already running"}

    proc = await start_stdio_server(server)
    if proc:
        _active_servers[name] = server
        logger.info("MCP server started: name=%s, pid=%d", name, proc.pid)
        return {"status": "ok", "message": f"Started MCP server '{name}' (pid={proc.pid})"}
    logger.error("Failed to start MCP server: %s", name)
    raise HTTPException(status_code=500, detail=f"Failed to start MCP server '{name}'")


@router.post("/servers/{name}/stop")
async def stop_server_endpoint(name: str):
    """Stop a running MCP server."""
    if name not in _active_servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' is not running")

    server = _active_servers.pop(name)
    stop_server(server)
    return {"status": "ok", "message": f"Stopped MCP server '{name}'"}
