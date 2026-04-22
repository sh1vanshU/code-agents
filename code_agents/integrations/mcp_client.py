"""
MCP (Model Context Protocol) client — connect any MCP service to agents.

MCP servers expose tools via JSON-RPC over stdio or HTTP SSE.
Config: per-agent MCP servers in ~/.code-agents/mcp.yaml or per-repo .code-agents/mcp.yaml

Example mcp.yaml:
  servers:
    filesystem:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
    github:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-github"]
      env:
        GITHUB_TOKEN: "${GITHUB_TOKEN}"
    slack:
      url: "http://localhost:3001/sse"
    custom:
      command: python
      args: ["my_mcp_server.py"]
      agents: ["code-writer", "auto-pilot"]  # restrict to specific agents
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("code_agents.integrations.mcp_client")

MCP_GLOBAL_CONFIG = Path.home() / ".code-agents" / "mcp.yaml"
MCP_PROJECT_CONFIG = ".code-agents/mcp.yaml"


@dataclass
class MCPTool:
    """A tool exposed by an MCP server."""
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    server_name: str = ""


@dataclass
class MCPServer:
    """An MCP server connection."""
    name: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""  # For HTTP SSE transport
    agents: list[str] = field(default_factory=list)  # Empty = all agents
    _process: Optional[subprocess.Popen] = field(default=None, repr=False)
    _tools: list[MCPTool] = field(default_factory=list, repr=False)

    @property
    def is_stdio(self) -> bool:
        return bool(self.command)

    @property
    def is_sse(self) -> bool:
        return bool(self.url)


def load_mcp_config(repo_path: str = "") -> dict[str, MCPServer]:
    """Load MCP server configs from global + project files."""
    servers: dict[str, MCPServer] = {}

    for config_path in [MCP_GLOBAL_CONFIG, Path(repo_path) / MCP_PROJECT_CONFIG if repo_path else None]:
        if config_path and config_path.is_file():
            try:
                raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                for name, cfg in raw.get("servers", {}).items():
                    # Expand env vars in env dict
                    env = {}
                    for k, v in (cfg.get("env") or {}).items():
                        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                            env[k] = os.getenv(v[2:-1], "")
                        else:
                            env[k] = str(v)

                    servers[name] = MCPServer(
                        name=name,
                        command=cfg.get("command", ""),
                        args=cfg.get("args", []),
                        env=env,
                        url=cfg.get("url", ""),
                        agents=cfg.get("agents", []),
                    )
                    logger.debug("Loaded MCP server: %s (from %s)", name, config_path)
            except Exception as e:
                logger.warning("Failed to load MCP config %s: %s", config_path, e)

    return servers


def get_servers_for_agent(agent_name: str, repo_path: str = "") -> dict[str, MCPServer]:
    """Get MCP servers available for a specific agent."""
    all_servers = load_mcp_config(repo_path)
    return {
        name: server
        for name, server in all_servers.items()
        if not server.agents or agent_name in server.agents
    }


async def start_stdio_server(server: MCPServer) -> Optional[subprocess.Popen]:
    """Start an MCP server via stdio transport."""
    if not server.is_stdio:
        return None

    env = {**os.environ, **server.env}
    try:
        proc = subprocess.Popen(
            [server.command] + server.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        server._process = proc
        logger.info("Started MCP server: %s (pid=%d)", server.name, proc.pid)
        return proc
    except Exception as e:
        logger.error("Failed to start MCP server %s: %s", server.name, e)
        return None


async def _read_stdio_with_timeout(process, length: int, timeout: float = 30.0):
    """Read from process stdout with timeout."""
    try:
        loop = asyncio.get_event_loop()
        data = await asyncio.wait_for(
            loop.run_in_executor(None, process.stdout.read, length),
            timeout=timeout,
        )
        return data
    except asyncio.TimeoutError:
        logger.error("MCP stdio read timed out after %ds", timeout)
        return None


async def _send_sse_with_retry(url: str, payload: dict, max_retries: int = 3) -> Any:
    """Send JSON-RPC over SSE with exponential backoff."""
    import httpx

    backoff = 1
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, json=payload)
                if r.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error: {r.status_code}",
                        request=r.request,
                        response=r,
                    )
                return r.json() if r.status_code == 200 else None
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning(
                    "MCP SSE attempt %d failed: %s, retrying in %ds",
                    attempt + 1, e, backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= 2
    logger.error("MCP SSE failed after %d attempts: %s", max_retries, last_error)
    return None


async def send_jsonrpc(server: MCPServer, method: str, params: dict = None) -> Any:
    """Send a JSON-RPC request to an MCP server."""
    if server.is_stdio and server._process and server._process.stdin:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {},
        }
        msg = json.dumps(request)
        content = f"Content-Length: {len(msg)}\r\n\r\n{msg}"
        server._process.stdin.write(content.encode())
        server._process.stdin.flush()

        # Read response with timeout
        if server._process.stdout:
            loop = asyncio.get_event_loop()
            try:
                header_bytes = await asyncio.wait_for(
                    loop.run_in_executor(None, server._process.stdout.readline),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                logger.error("MCP stdio header read timed out after 30s")
                return None
            header = header_bytes.decode()
            if header.startswith("Content-Length:"):
                length = int(header.split(":")[1].strip())
                server._process.stdout.readline()  # empty line
                body_bytes = await _read_stdio_with_timeout(server._process, length)
                if body_bytes is None:
                    return None
                return json.loads(body_bytes.decode())
    elif server.is_sse:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {},
        }
        return await _send_sse_with_retry(
            server.url.replace("/sse", "/message"), payload,
        )
    return None


async def list_tools(server: MCPServer) -> list[MCPTool]:
    """List tools available from an MCP server."""
    response = await send_jsonrpc(server, "tools/list")
    if response and "result" in response:
        tools = []
        for t in response["result"].get("tools", []):
            tools.append(MCPTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
                server_name=server.name,
            ))
        server._tools = tools
        return tools
    return []


def validate_tool_arguments(tool: MCPTool, arguments: dict | None) -> list[str]:
    """Validate arguments against tool's input_schema. Returns list of error strings."""
    errors: list[str] = []
    schema = getattr(tool, "input_schema", None)
    if not schema or not isinstance(schema, dict):
        return errors  # No schema to validate against

    arguments = arguments or {}

    # Check required fields
    required = schema.get("required", [])
    for f in required:
        if f not in arguments:
            errors.append(f"Missing required argument: {f}")

    # Check types for properties
    properties = schema.get("properties", {})
    for key, value in arguments.items():
        if key in properties:
            expected_type = properties[key].get("type")
            if expected_type == "string" and not isinstance(value, str):
                errors.append(f"Argument '{key}' should be string, got {type(value).__name__}")
            elif expected_type == "integer" and not isinstance(value, int):
                errors.append(f"Argument '{key}' should be integer, got {type(value).__name__}")
            elif expected_type == "boolean" and not isinstance(value, bool):
                errors.append(f"Argument '{key}' should be boolean, got {type(value).__name__}")
            elif expected_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"Argument '{key}' should be number, got {type(value).__name__}")

    return errors


async def call_tool(server: MCPServer, tool_name: str, arguments: dict = None) -> Any:
    """Call a tool on an MCP server."""
    # Validate arguments against tool schema if available
    matching_tools = [t for t in server._tools if t.name == tool_name]
    if matching_tools:
        validation_errors = validate_tool_arguments(matching_tools[0], arguments)
        if validation_errors:
            logger.warning(
                "MCP tool %s:%s argument validation warnings: %s",
                server.name, tool_name, "; ".join(validation_errors),
            )
    response = await send_jsonrpc(server, "tools/call", {
        "name": tool_name,
        "arguments": arguments or {},
    })
    if response and "result" in response:
        content = response["result"].get("content", [])
        # Return text content
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "\n".join(texts) if texts else response["result"]
    if response and "error" in response:
        return f"MCP Error: {response['error'].get('message', 'Unknown error')}"
    return None


def stop_server(server: MCPServer) -> None:
    """Stop a stdio MCP server."""
    if server._process:
        server._process.terminate()
        try:
            server._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server._process.kill()
        server._process = None
        logger.info("Stopped MCP server: %s", server.name)


def format_mcp_tools_for_prompt(servers: dict[str, MCPServer]) -> str:
    """Format MCP tools for injection into agent system prompt."""
    if not servers:
        return ""
    lines = ["", "MCP Tools (external services — use these when available):"]
    for name, server in servers.items():
        service_hint = MCP_SERVICE_MAP.get(name, "")
        hint_str = f" [{service_hint}]" if service_hint else ""
        if server._tools:
            for tool in server._tools:
                desc = f" — {tool.description}" if tool.description else ""
                lines.append(f"  - mcp:{name}:{tool.name}{desc}")
        else:
            lines.append(f"  - mcp:{name}{hint_str} (connect with [MCP:{name}])")
    lines.append("")
    lines.append("To use an MCP tool, output: [MCP:server:tool {\"arg\": \"value\"}]")
    lines.append("MCP tools are PREFERRED over REST endpoints when both are available.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Service Intelligence — maps MCP server names to agent capabilities
# ---------------------------------------------------------------------------

# Known MCP server → service category mapping
MCP_SERVICE_MAP: dict[str, str] = {
    # Atlassian
    "atlassian": "Jira + Confluence — read tickets, update status, wiki pages",
    "jira": "Jira — issue tracking, transitions, comments",
    "confluence": "Confluence — wiki pages, documentation",
    # Code & Git
    "github": "GitHub — repos, PRs, issues, actions",
    "gitlab": "GitLab — repos, MRs, pipelines",
    "filesystem": "File system — read/write/search files",
    # Communication
    "slack": "Slack — send messages, read channels, search",
    "teams": "Microsoft Teams — messages, channels",
    "gmail": "Gmail — read/send emails",
    # Databases
    "postgres": "PostgreSQL — run SQL queries",
    "mysql": "MySQL — run SQL queries",
    "mongodb": "MongoDB — document queries",
    "redis": "Redis — cache operations",
    # Monitoring
    "grafana": "Grafana — dashboards, alerts, metrics",
    "datadog": "Datadog — APM, logs, metrics",
    "sentry": "Sentry — error tracking, issues",
    # Cloud
    "aws": "AWS — S3, Lambda, EC2, etc.",
    "gcp": "Google Cloud — GCS, Cloud Run, etc.",
    # CI/CD
    "jenkins": "Jenkins — builds, deploys, pipelines",
    "argocd": "ArgoCD — k8s deployments, sync, rollback",
    # Search
    "brave-search": "Web search via Brave",
    "google-search": "Web search via Google",
}

# Agent → preferred MCP server mapping (which agents should auto-use which MCP)
AGENT_MCP_AFFINITY: dict[str, list[str]] = {
    "jira-ops": ["atlassian", "jira", "confluence"],
    "code-writer": ["filesystem", "github", "gitlab"],
    "code-reviewer": ["github", "gitlab"],
    "git-ops": ["github", "gitlab"],
    "jenkins-cicd": ["jenkins"],
    "argocd-verify": ["argocd", "grafana", "datadog"],
    "redash-query": ["postgres", "mysql", "mongodb"],
    "auto-pilot": ["atlassian", "github", "slack", "jenkins", "argocd"],
    "qa-regression": ["github", "filesystem"],
}


def get_smart_mcp_context(agent_name: str, servers: dict[str, MCPServer]) -> str:
    """Generate intelligent MCP context for a specific agent.

    Tells the agent which MCP tools are available AND how they relate
    to the agent's capabilities. For example, jira-ops will see:
    'Atlassian MCP is connected — use MCP tools for Jira/Confluence
    instead of REST API endpoints.'
    """
    if not servers:
        return ""

    lines = []
    affinity = AGENT_MCP_AFFINITY.get(agent_name, [])

    # Highlight high-affinity MCP servers for this agent
    priority_servers = {
        name: srv for name, srv in servers.items()
        if name in affinity or any(a in name for a in affinity)
    }
    other_servers = {
        name: srv for name, srv in servers.items()
        if name not in priority_servers
    }

    if priority_servers:
        lines.append("")
        lines.append("⚡ MCP INTEGRATIONS (use these — they extend your capabilities):")
        for name, srv in priority_servers.items():
            service = MCP_SERVICE_MAP.get(name, "external service")
            lines.append(f"  ✦ mcp:{name} — {service}")
            if srv._tools:
                for tool in srv._tools[:5]:  # Show top 5 tools
                    desc = f": {tool.description}" if tool.description else ""
                    lines.append(f"      → mcp:{name}:{tool.name}{desc}")
            lines.append(f"    PREFER MCP tools over REST endpoints for {name} operations.")

    if other_servers:
        lines.append("")
        lines.append("Other MCP services available:")
        for name, srv in other_servers.items():
            service = MCP_SERVICE_MAP.get(name, "")
            hint = f" — {service}" if service else ""
            lines.append(f"  - mcp:{name}{hint}")

    if lines:
        lines.append("")
        lines.append("Usage: [MCP:server:tool {\"key\": \"value\"}]")

    return "\n".join(lines)
