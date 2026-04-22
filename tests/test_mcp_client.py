"""Tests for mcp_client.py — MCP plugin system."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, mock_open

import pytest

from code_agents.integrations.mcp_client import (
    MCPTool,
    MCPServer,
    load_mcp_config,
    get_servers_for_agent,
    start_stdio_server,
    send_jsonrpc,
    list_tools,
    call_tool,
    stop_server,
    format_mcp_tools_for_prompt,
    MCP_SERVICE_MAP,
    AGENT_MCP_AFFINITY,
    get_smart_mcp_context,
    validate_tool_arguments,
    _read_stdio_with_timeout,
    _send_sse_with_retry,
)


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestMCPTool:
    def test_defaults(self):
        tool = MCPTool(name="test_tool")
        assert tool.name == "test_tool"
        assert tool.description == ""
        assert tool.input_schema == {}
        assert tool.server_name == ""

    def test_with_values(self):
        tool = MCPTool(name="bash", description="Run shell", input_schema={"type": "object"}, server_name="fs")
        assert tool.description == "Run shell"
        assert tool.server_name == "fs"


class TestMCPServer:
    def test_stdio_server(self):
        srv = MCPServer(name="fs", command="npx", args=["-y", "server"])
        assert srv.is_stdio is True
        assert srv.is_sse is False

    def test_sse_server(self):
        srv = MCPServer(name="slack", url="http://localhost:3001/sse")
        assert srv.is_stdio is False
        assert srv.is_sse is True

    def test_neither_transport(self):
        srv = MCPServer(name="empty")
        assert srv.is_stdio is False
        assert srv.is_sse is False

    def test_agents_list(self):
        srv = MCPServer(name="test", agents=["code-writer", "auto-pilot"])
        assert "code-writer" in srv.agents

    def test_default_fields(self):
        srv = MCPServer(name="x")
        assert srv.env == {}
        assert srv.args == []
        assert srv._process is None
        assert srv._tools == []


# ---------------------------------------------------------------------------
# load_mcp_config
# ---------------------------------------------------------------------------


class TestLoadMcpConfig:
    def test_no_config_files(self, tmp_path):
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", tmp_path / "missing.yaml"):
            result = load_mcp_config(str(tmp_path))
        assert result == {}

    def test_load_global_config(self, tmp_path):
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("""
servers:
  filesystem:
    command: npx
    args: ["-y", "server-fs"]
  slack:
    url: "http://localhost:3001/sse"
""")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            result = load_mcp_config("")
        assert "filesystem" in result
        assert result["filesystem"].command == "npx"
        assert result["slack"].url == "http://localhost:3001/sse"

    def test_env_var_expansion(self, tmp_path):
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("""
servers:
  github:
    command: npx
    env:
      GITHUB_TOKEN: "${MY_GH_TOKEN}"
      STATIC: "plain_value"
""")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            with patch.dict(os.environ, {"MY_GH_TOKEN": "ghp_abc123"}):
                result = load_mcp_config("")
        assert result["github"].env["GITHUB_TOKEN"] == "ghp_abc123"
        assert result["github"].env["STATIC"] == "plain_value"

    def test_project_config_overlay(self, tmp_path):
        global_cfg = tmp_path / "global.yaml"
        global_cfg.write_text("""
servers:
  fs:
    command: npx
""")
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project_cfg = project_dir / ".code-agents" / "mcp.yaml"
        project_cfg.parent.mkdir(parents=True)
        project_cfg.write_text("""
servers:
  custom:
    command: python
    args: ["server.py"]
""")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", global_cfg):
            result = load_mcp_config(str(project_dir))
        assert "fs" in result
        assert "custom" in result

    def test_agents_restriction(self, tmp_path):
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("""
servers:
  restricted:
    command: npx
    agents: ["code-writer", "auto-pilot"]
""")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            result = load_mcp_config("")
        assert result["restricted"].agents == ["code-writer", "auto-pilot"]

    def test_malformed_yaml(self, tmp_path):
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("invalid: yaml: [[[")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            result = load_mcp_config("")
        # Should not crash
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# get_servers_for_agent
# ---------------------------------------------------------------------------


class TestGetServersForAgent:
    def test_unrestricted_server(self, tmp_path):
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("""
servers:
  fs:
    command: npx
""")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            result = get_servers_for_agent("any-agent", "")
        assert "fs" in result

    def test_restricted_server_matching(self, tmp_path):
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("""
servers:
  restricted:
    command: npx
    agents: ["code-writer"]
""")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            result = get_servers_for_agent("code-writer", "")
        assert "restricted" in result

    def test_restricted_server_not_matching(self, tmp_path):
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("""
servers:
  restricted:
    command: npx
    agents: ["code-writer"]
""")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            result = get_servers_for_agent("git-ops", "")
        assert "restricted" not in result


# ---------------------------------------------------------------------------
# start_stdio_server
# ---------------------------------------------------------------------------


class TestStartStdioServer:
    @pytest.mark.asyncio
    async def test_start_stdio(self):
        srv = MCPServer(name="test", command="echo", args=["hello"])
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        with patch("subprocess.Popen", return_value=mock_proc):
            result = await start_stdio_server(srv)
        assert result == mock_proc
        assert srv._process == mock_proc

    @pytest.mark.asyncio
    async def test_start_sse_returns_none(self):
        srv = MCPServer(name="test", url="http://localhost/sse")
        result = await start_stdio_server(srv)
        assert result is None

    @pytest.mark.asyncio
    async def test_start_failure(self):
        srv = MCPServer(name="test", command="nonexistent_cmd")
        with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
            result = await start_stdio_server(srv)
        assert result is None


# ---------------------------------------------------------------------------
# send_jsonrpc
# ---------------------------------------------------------------------------


class TestSendJsonrpc:
    @pytest.mark.asyncio
    async def test_stdio_jsonrpc(self):
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})
        mock_stdout.readline.side_effect = [
            f"Content-Length: {len(response)}\r\n".encode(),
            b"\r\n",
        ]
        mock_stdout.read.return_value = response.encode()

        mock_proc = MagicMock()
        mock_proc.stdin = mock_stdin
        mock_proc.stdout = mock_stdout

        srv = MCPServer(name="test", command="cmd")
        srv._process = mock_proc

        result = await send_jsonrpc(srv, "tools/list")
        assert result["result"] == {"tools": []}
        mock_stdin.write.assert_called_once()
        mock_stdin.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_process_returns_none(self):
        srv = MCPServer(name="test", command="cmd")
        srv._process = None
        result = await send_jsonrpc(srv, "tools/list")
        assert result is None

    @pytest.mark.asyncio
    async def test_sse_jsonrpc(self):
        srv = MCPServer(name="test", url="http://localhost:3001/sse")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {"data": "ok"}}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await send_jsonrpc(srv, "test/method", {"key": "val"})
        assert result["result"]["data"] == "ok"


# ---------------------------------------------------------------------------
# list_tools
# ---------------------------------------------------------------------------


class TestListTools:
    @pytest.mark.asyncio
    async def test_list_tools_success(self):
        srv = MCPServer(name="test", command="cmd")
        response = {
            "result": {
                "tools": [
                    {"name": "read_file", "description": "Read a file", "inputSchema": {"type": "object"}},
                    {"name": "write_file", "description": "Write a file"},
                ]
            }
        }
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=response):
            tools = await list_tools(srv)
        assert len(tools) == 2
        assert tools[0].name == "read_file"
        assert tools[0].server_name == "test"
        assert srv._tools == tools

    @pytest.mark.asyncio
    async def test_list_tools_no_response(self):
        srv = MCPServer(name="test", command="cmd")
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=None):
            tools = await list_tools(srv)
        assert tools == []

    @pytest.mark.asyncio
    async def test_list_tools_empty_result(self):
        srv = MCPServer(name="test", command="cmd")
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value={"result": {}}):
            tools = await list_tools(srv)
        assert tools == []


# ---------------------------------------------------------------------------
# call_tool
# ---------------------------------------------------------------------------


class TestCallTool:
    @pytest.mark.asyncio
    async def test_call_tool_text_result(self):
        srv = MCPServer(name="test", command="cmd")
        response = {
            "result": {
                "content": [
                    {"type": "text", "text": "file contents here"},
                ]
            }
        }
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=response):
            result = await call_tool(srv, "read_file", {"path": "/tmp/x"})
        assert result == "file contents here"

    @pytest.mark.asyncio
    async def test_call_tool_error(self):
        srv = MCPServer(name="test", command="cmd")
        response = {"error": {"message": "Not found"}}
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=response):
            result = await call_tool(srv, "read_file")
        assert "MCP Error" in result
        assert "Not found" in result

    @pytest.mark.asyncio
    async def test_call_tool_none_response(self):
        srv = MCPServer(name="test", command="cmd")
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=None):
            result = await call_tool(srv, "read_file")
        assert result is None

    @pytest.mark.asyncio
    async def test_call_tool_non_text_content(self):
        srv = MCPServer(name="test", command="cmd")
        response = {"result": {"content": [{"type": "image", "data": "..."}]}}
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=response):
            result = await call_tool(srv, "screenshot")
        # No text content, returns the full result
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# stop_server
# ---------------------------------------------------------------------------


class TestStopServer:
    def test_stop_running_server(self):
        mock_proc = MagicMock()
        srv = MCPServer(name="test", command="cmd")
        srv._process = mock_proc
        stop_server(srv)
        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=5)
        assert srv._process is None

    def test_stop_with_timeout(self):
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = subprocess.TimeoutExpired("cmd", 5)
        srv = MCPServer(name="test", command="cmd")
        srv._process = mock_proc
        stop_server(srv)
        mock_proc.kill.assert_called_once()
        assert srv._process is None

    def test_stop_no_process(self):
        srv = MCPServer(name="test", command="cmd")
        srv._process = None
        stop_server(srv)  # should not crash


# ---------------------------------------------------------------------------
# format_mcp_tools_for_prompt
# ---------------------------------------------------------------------------


class TestFormatMcpToolsForPrompt:
    def test_empty_servers(self):
        result = format_mcp_tools_for_prompt({})
        assert result == ""

    def test_servers_with_tools(self):
        srv = MCPServer(name="fs", command="npx")
        srv._tools = [
            MCPTool(name="read_file", description="Read a file", server_name="fs"),
        ]
        result = format_mcp_tools_for_prompt({"fs": srv})
        assert "mcp:fs:read_file" in result
        assert "Read a file" in result
        assert "[MCP:" in result

    def test_servers_without_tools(self):
        srv = MCPServer(name="github", command="npx")
        result = format_mcp_tools_for_prompt({"github": srv})
        assert "mcp:github" in result
        assert "[MCP:github]" in result

    def test_known_service_hint(self):
        srv = MCPServer(name="slack", command="npx")
        result = format_mcp_tools_for_prompt({"slack": srv})
        assert "Slack" in result


# ---------------------------------------------------------------------------
# Service Intelligence
# ---------------------------------------------------------------------------


class TestServiceIntelligence:
    def test_service_map_entries(self):
        assert "github" in MCP_SERVICE_MAP
        assert "slack" in MCP_SERVICE_MAP
        assert "postgres" in MCP_SERVICE_MAP

    def test_agent_affinity_entries(self):
        assert "jira-ops" in AGENT_MCP_AFFINITY
        assert "atlassian" in AGENT_MCP_AFFINITY["jira-ops"]

    def test_smart_context_empty(self):
        result = get_smart_mcp_context("code-writer", {})
        assert result == ""

    def test_smart_context_with_affinity(self):
        srv = MCPServer(name="github", command="npx")
        srv._tools = [MCPTool(name="create_pr", description="Create PR", server_name="github")]
        result = get_smart_mcp_context("code-writer", {"github": srv})
        assert "MCP INTEGRATIONS" in result
        assert "mcp:github" in result
        assert "PREFER" in result

    def test_smart_context_other_servers(self):
        srv = MCPServer(name="postgres", command="pg_mcp")
        result = get_smart_mcp_context("code-writer", {"postgres": srv})
        # postgres is not in code-writer affinity, goes to "other"
        assert "Other MCP services" in result
        assert "postgres" in result

    def test_smart_context_mixed(self):
        gh = MCPServer(name="github", command="npx")
        pg = MCPServer(name="postgres", command="pg")
        result = get_smart_mcp_context("code-writer", {"github": gh, "postgres": pg})
        assert "MCP INTEGRATIONS" in result
        assert "Other MCP services" in result

    def test_smart_context_tool_limit(self):
        srv = MCPServer(name="github", command="npx")
        # Add more than 5 tools
        srv._tools = [MCPTool(name=f"tool_{i}", server_name="github") for i in range(10)]
        result = get_smart_mcp_context("code-writer", {"github": srv})
        # Should only show top 5
        assert "tool_4" in result
        assert "tool_5" not in result


# ---------------------------------------------------------------------------
# validate_tool_arguments
# ---------------------------------------------------------------------------


class TestValidateToolArguments:
    def test_no_schema(self):
        tool = MCPTool(name="t")
        assert validate_tool_arguments(tool, {"a": 1}) == []

    def test_empty_schema(self):
        tool = MCPTool(name="t", input_schema={})
        assert validate_tool_arguments(tool, {"a": 1}) == []

    def test_missing_required(self):
        tool = MCPTool(name="t", input_schema={
            "type": "object",
            "required": ["path", "content"],
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        })
        errors = validate_tool_arguments(tool, {"path": "/tmp"})
        assert len(errors) == 1
        assert "Missing required argument: content" in errors[0]

    def test_all_required_present(self):
        tool = MCPTool(name="t", input_schema={
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}},
        })
        errors = validate_tool_arguments(tool, {"path": "/tmp"})
        assert errors == []

    def test_wrong_type_string(self):
        tool = MCPTool(name="t", input_schema={
            "properties": {"name": {"type": "string"}},
        })
        errors = validate_tool_arguments(tool, {"name": 123})
        assert len(errors) == 1
        assert "should be string" in errors[0]

    def test_wrong_type_integer(self):
        tool = MCPTool(name="t", input_schema={
            "properties": {"count": {"type": "integer"}},
        })
        errors = validate_tool_arguments(tool, {"count": "five"})
        assert len(errors) == 1
        assert "should be integer" in errors[0]

    def test_wrong_type_boolean(self):
        tool = MCPTool(name="t", input_schema={
            "properties": {"flag": {"type": "boolean"}},
        })
        errors = validate_tool_arguments(tool, {"flag": "true"})
        assert len(errors) == 1
        assert "should be boolean" in errors[0]

    def test_wrong_type_number(self):
        tool = MCPTool(name="t", input_schema={
            "properties": {"score": {"type": "number"}},
        })
        errors = validate_tool_arguments(tool, {"score": "high"})
        assert len(errors) == 1
        assert "should be number" in errors[0]

    def test_number_accepts_int_and_float(self):
        tool = MCPTool(name="t", input_schema={
            "properties": {"val": {"type": "number"}},
        })
        assert validate_tool_arguments(tool, {"val": 42}) == []
        assert validate_tool_arguments(tool, {"val": 3.14}) == []

    def test_none_arguments(self):
        tool = MCPTool(name="t", input_schema={
            "required": ["x"],
            "properties": {"x": {"type": "string"}},
        })
        errors = validate_tool_arguments(tool, None)
        assert len(errors) == 1
        assert "Missing required" in errors[0]

    def test_unknown_args_no_error(self):
        tool = MCPTool(name="t", input_schema={
            "properties": {"a": {"type": "string"}},
        })
        # Extra arg not in properties — no error (lenient)
        errors = validate_tool_arguments(tool, {"a": "ok", "b": 99})
        assert errors == []

    def test_multiple_errors(self):
        tool = MCPTool(name="t", input_schema={
            "required": ["a", "b"],
            "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
        })
        errors = validate_tool_arguments(tool, {"a": 123})
        assert len(errors) == 2  # missing b + wrong type a

    def test_non_dict_schema(self):
        tool = MCPTool(name="t", input_schema="not a dict")
        assert validate_tool_arguments(tool, {"x": 1}) == []


# ---------------------------------------------------------------------------
# call_tool with validation
# ---------------------------------------------------------------------------


class TestCallToolValidation:
    @pytest.mark.asyncio
    async def test_call_tool_validates_arguments(self):
        """call_tool logs warnings for invalid args but still proceeds."""
        srv = MCPServer(name="test", command="cmd")
        srv._tools = [MCPTool(
            name="write",
            input_schema={"required": ["path"], "properties": {"path": {"type": "string"}}},
            server_name="test",
        )]
        response = {"result": {"content": [{"type": "text", "text": "ok"}]}}
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=response) as mock_send:
            with patch("code_agents.integrations.mcp_client.logger") as mock_logger:
                result = await call_tool(srv, "write", {"path": 123})
        # Should still return result (non-blocking validation)
        assert result == "ok"
        mock_logger.warning.assert_called_once()
        assert "validation warnings" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_call_tool_no_matching_tool_skips_validation(self):
        """If tool not in server._tools, skip validation."""
        srv = MCPServer(name="test", command="cmd")
        srv._tools = []  # no tools loaded
        response = {"result": {"content": [{"type": "text", "text": "ok"}]}}
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=response):
            result = await call_tool(srv, "unknown_tool", {"a": 1})
        assert result == "ok"


# ---------------------------------------------------------------------------
# _send_sse_with_retry
# ---------------------------------------------------------------------------


class TestSendSseWithRetry:
    @pytest.mark.asyncio
    async def test_success_first_attempt(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _send_sse_with_retry("http://localhost/message", {"method": "test"})
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        import httpx as _httpx

        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500
        mock_response_fail.request = MagicMock()

        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {"result": "ok"}

        call_count = 0
        async def post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_response_fail
            return mock_response_ok

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=post_side_effect)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await _send_sse_with_retry("http://localhost/msg", {}, max_retries=3)
        assert result == {"result": "ok"}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        import httpx as _httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=_httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await _send_sse_with_retry("http://localhost/msg", {}, max_retries=2)
        assert result is None

    @pytest.mark.asyncio
    async def test_non_200_no_retry(self):
        """Non-5xx, non-200 returns None without retrying."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.request = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _send_sse_with_retry("http://localhost/msg", {}, max_retries=3)
        assert result is None
        # Only 1 call — no retry for 404
        assert mock_client.post.await_count == 1


# ---------------------------------------------------------------------------
# _read_stdio_with_timeout
# ---------------------------------------------------------------------------


class TestReadStdioWithTimeout:
    @pytest.mark.asyncio
    async def test_successful_read(self):
        mock_proc = MagicMock()
        mock_proc.stdout.read.return_value = b"hello"
        result = await _read_stdio_with_timeout(mock_proc, 5, timeout=5.0)
        assert result == b"hello"

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Simulate a timeout by making stdout.read block."""
        import threading
        import time

        mock_proc = MagicMock()
        # Make read block long enough to trigger timeout
        mock_proc.stdout.read.side_effect = lambda n: time.sleep(2) or b""
        result = await _read_stdio_with_timeout(mock_proc, 5, timeout=0.05)
        assert result is None


# ---------------------------------------------------------------------------
# send_jsonrpc with retry (SSE path)
# ---------------------------------------------------------------------------


class TestSendJsonrpcSseRetry:
    @pytest.mark.asyncio
    async def test_sse_uses_retry(self):
        """SSE path in send_jsonrpc should use _send_sse_with_retry."""
        srv = MCPServer(name="test", url="http://localhost:3001/sse")
        with patch("code_agents.integrations.mcp_client._send_sse_with_retry", new_callable=AsyncMock, return_value={"result": "ok"}) as mock_retry:
            result = await send_jsonrpc(srv, "test/method", {"key": "val"})
        assert result == {"result": "ok"}
        mock_retry.assert_awaited_once()
        call_args = mock_retry.call_args
        assert call_args[0][0] == "http://localhost:3001/message"


# ---------------------------------------------------------------------------
# Coverage gap tests — missing lines
# ---------------------------------------------------------------------------


class TestStartStdioServerNotStdio:
    """Line 118: start_stdio_server returns None for non-stdio server."""

    @pytest.mark.asyncio
    async def test_non_stdio_returns_none(self):
        srv = MCPServer(name="web", url="http://localhost:3001/sse")
        result = await start_stdio_server(srv)
        assert result is None


class TestStdioReadTimeout:
    """Lines 146-148: stdio read timeout."""

    @pytest.mark.asyncio
    async def test_read_timeout_returns_none(self):
        from code_agents.integrations.mcp_client import _read_stdio_with_timeout
        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.read = MagicMock()
        with patch("asyncio.wait_for", new_callable=AsyncMock, side_effect=asyncio.TimeoutError()):
            result = await _read_stdio_with_timeout(mock_proc, 10, timeout=0.1)
        assert result is None


class TestSendSseRetry500:
    """Lines 162: _send_sse_with_retry retries on 500."""

    @pytest.mark.asyncio
    async def test_sse_retry_on_500(self):
        from code_agents.integrations.mcp_client import _send_sse_with_retry
        import httpx

        call_count = [0]
        async def _mock_post(self_client, url, **kw):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] < 2:
                resp.status_code = 500
                resp.request = MagicMock()
                raise httpx.HTTPStatusError("500", request=resp.request, response=resp)
            resp.status_code = 200
            resp.json.return_value = {"result": "ok"}
            return resp

        with patch("httpx.AsyncClient.post", new=_mock_post), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _send_sse_with_retry("http://localhost/msg", {"method": "test"})
        assert result == {"result": "ok"}


class TestValidateToolArgumentsTypes:
    """Lines 266-271: validate_tool_arguments type checks."""

    def test_integer_type_mismatch(self):
        from code_agents.integrations.mcp_client import validate_tool_arguments
        tool = MCPTool(name="t", description="d", input_schema={
            "properties": {"count": {"type": "integer"}},
        })
        errors = validate_tool_arguments(tool, {"count": "not-int"})
        assert any("integer" in e for e in errors)

    def test_boolean_type_mismatch(self):
        from code_agents.integrations.mcp_client import validate_tool_arguments
        tool = MCPTool(name="t", description="d", input_schema={
            "properties": {"flag": {"type": "boolean"}},
        })
        errors = validate_tool_arguments(tool, {"flag": "yes"})
        assert any("boolean" in e for e in errors)

    def test_number_type_mismatch(self):
        from code_agents.integrations.mcp_client import validate_tool_arguments
        tool = MCPTool(name="t", description="d", input_schema={
            "properties": {"val": {"type": "number"}},
        })
        errors = validate_tool_arguments(tool, {"val": "string"})
        assert any("number" in e for e in errors)

    def test_valid_types_no_errors(self):
        from code_agents.integrations.mcp_client import validate_tool_arguments
        tool = MCPTool(name="t", description="d", input_schema={
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "flag": {"type": "boolean"},
                "val": {"type": "number"},
            },
        })
        errors = validate_tool_arguments(tool, {"name": "hi", "count": 5, "flag": True, "val": 3.14})
        assert errors == []


class TestCallToolErrorResponse:
    """Lines 296-298: call_tool handles error response."""

    @pytest.mark.asyncio
    async def test_call_tool_error_response(self):
        srv = MCPServer(name="test", command="echo")
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock,
                    return_value={"error": {"message": "tool failed"}}):
            result = await call_tool(srv, "bad_tool", {})
        assert "MCP Error" in result
        assert "tool failed" in result

    @pytest.mark.asyncio
    async def test_call_tool_none_response(self):
        srv = MCPServer(name="test", command="echo")
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock,
                    return_value=None):
            result = await call_tool(srv, "missing_tool", {})
        assert result is None


class TestStopServerTimeout:
    """Lines 307-308: stop_server kills on timeout."""

    def test_stop_server_kills_on_timeout(self):
        import subprocess as sp
        srv = MCPServer(name="test", command="echo")
        mock_proc = MagicMock()
        mock_proc.terminate = MagicMock()
        mock_proc.wait = MagicMock(side_effect=sp.TimeoutExpired(cmd="echo", timeout=5))
        mock_proc.kill = MagicMock()
        srv._process = mock_proc
        stop_server(srv)
        mock_proc.kill.assert_called_once()
        assert srv._process is None


class TestFormatMcpToolsForPromptEmpty:
    """Line 316: format_mcp_tools_for_prompt with no tools."""

    def test_empty_servers(self):
        result = format_mcp_tools_for_prompt({})
        assert result == ""
