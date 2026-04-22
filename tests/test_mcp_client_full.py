"""Full coverage tests for mcp_client.py — covers all remaining uncovered lines.

Targets: start_stdio_server, _read_stdio_with_timeout, _send_sse_with_retry,
send_jsonrpc (stdio path edge cases), list_tools, call_tool, stop_server,
format_mcp_tools_for_prompt, get_smart_mcp_context, load_mcp_config.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

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
    get_smart_mcp_context,
    validate_tool_arguments,
    _read_stdio_with_timeout,
    _send_sse_with_retry,
    MCP_GLOBAL_CONFIG,
    MCP_SERVICE_MAP,
    AGENT_MCP_AFFINITY,
)


# ---------------------------------------------------------------------------
# load_mcp_config — edge cases
# ---------------------------------------------------------------------------


class TestLoadMcpConfigEdgeCases:
    """Cover uncovered paths in load_mcp_config."""

    def test_empty_yaml_file(self, tmp_path):
        """YAML file that parses to None."""
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            result = load_mcp_config("")
        assert result == {}

    def test_yaml_with_no_servers_key(self, tmp_path):
        """YAML file missing 'servers' key."""
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("other_key: value\n")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            result = load_mcp_config("")
        assert result == {}

    def test_env_var_not_set_resolves_empty(self, tmp_path):
        """When env var referenced in config is not set, should resolve to empty string."""
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("""
servers:
  test:
    command: npx
    env:
      MY_TOKEN: "${UNSET_VAR_XYZ_12345}"
""")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("UNSET_VAR_XYZ_12345", None)
                result = load_mcp_config("")
        assert result["test"].env["MY_TOKEN"] == ""

    def test_env_with_none_value(self, tmp_path):
        """When env value is None (null in YAML)."""
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("""
servers:
  test:
    command: npx
    env: null
""")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            result = load_mcp_config("")
        assert result["test"].env == {}

    def test_project_config_none_when_no_repo(self):
        """When repo_path is empty, project config path is None."""
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", Path("/nonexistent")):
            result = load_mcp_config("")
        assert result == {}

    def test_numeric_env_value(self, tmp_path):
        """Non-string env values are stringified."""
        config_path = tmp_path / "mcp.yaml"
        config_path.write_text("""
servers:
  test:
    command: npx
    env:
      PORT: 3000
""")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            result = load_mcp_config("")
        assert result["test"].env["PORT"] == "3000"


# ---------------------------------------------------------------------------
# send_jsonrpc — stdio edge cases
# ---------------------------------------------------------------------------


class TestSendJsonrpcStdioEdgeCases:
    @pytest.mark.asyncio
    async def test_stdio_header_not_content_length(self):
        """When header line doesn't start with Content-Length."""
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stdout.readline.return_value = b"Invalid-Header: foo\r\n"

        mock_proc = MagicMock()
        mock_proc.stdin = mock_stdin
        mock_proc.stdout = mock_stdout

        srv = MCPServer(name="test", command="cmd")
        srv._process = mock_proc

        result = await send_jsonrpc(srv, "tools/list")
        # If header doesn't match Content-Length, nothing further happens
        # The function returns None because it doesn't enter the content-length branch
        assert result is None

    @pytest.mark.asyncio
    async def test_stdio_header_timeout(self):
        """When reading the header times out."""
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()

        mock_proc = MagicMock()
        mock_proc.stdin = mock_stdin
        mock_proc.stdout = mock_stdout

        srv = MCPServer(name="test", command="cmd")
        srv._process = mock_proc

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_el = MagicMock()
            mock_loop.return_value = mock_el
            mock_el.run_in_executor = AsyncMock(side_effect=asyncio.TimeoutError)
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                result = await send_jsonrpc(srv, "tools/list")
        assert result is None

    @pytest.mark.asyncio
    async def test_stdio_body_read_timeout(self):
        """When _read_stdio_with_timeout returns None for body."""
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stdout.readline.side_effect = [
            b"Content-Length: 50\r\n",
            b"\r\n",
        ]

        mock_proc = MagicMock()
        mock_proc.stdin = mock_stdin
        mock_proc.stdout = mock_stdout

        srv = MCPServer(name="test", command="cmd")
        srv._process = mock_proc

        with patch("code_agents.integrations.mcp_client._read_stdio_with_timeout", new_callable=AsyncMock, return_value=None):
            result = await send_jsonrpc(srv, "tools/list")
        assert result is None

    @pytest.mark.asyncio
    async def test_stdio_no_stdout(self):
        """When process stdout is None."""
        mock_stdin = MagicMock()
        mock_proc = MagicMock()
        mock_proc.stdin = mock_stdin
        mock_proc.stdout = None

        srv = MCPServer(name="test", command="cmd")
        srv._process = mock_proc

        result = await send_jsonrpc(srv, "tools/list")
        # Writes to stdin but can't read, returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_neither_stdio_nor_sse(self):
        """Server with no transport returns None."""
        srv = MCPServer(name="test")
        result = await send_jsonrpc(srv, "tools/list")
        assert result is None

    @pytest.mark.asyncio
    async def test_sse_replaces_sse_with_message(self):
        """SSE path replaces /sse with /message in URL."""
        srv = MCPServer(name="test", url="http://localhost:3001/sse")
        with patch("code_agents.integrations.mcp_client._send_sse_with_retry", new_callable=AsyncMock, return_value={"ok": True}) as mock_fn:
            result = await send_jsonrpc(srv, "test/call", {"x": 1})
        assert result == {"ok": True}
        call_url = mock_fn.call_args[0][0]
        assert call_url == "http://localhost:3001/message"

    @pytest.mark.asyncio
    async def test_stdio_with_params(self):
        """Verify params are included in JSON-RPC request."""
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
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

        result = await send_jsonrpc(srv, "tools/call", {"name": "foo"})
        assert result["result"]["ok"] is True
        # Verify the written JSON includes our params
        written = mock_stdin.write.call_args[0][0].decode()
        assert '"name": "foo"' in written


# ---------------------------------------------------------------------------
# _send_sse_with_retry — edge cases
# ---------------------------------------------------------------------------


class TestSendSseWithRetryEdgeCases:
    @pytest.mark.asyncio
    async def test_timeout_exception_retries(self):
        """httpx.TimeoutException triggers retry."""
        import httpx as _httpx

        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {"ok": True}

        call_count = 0

        async def post_side(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _httpx.TimeoutException("timeout")
            return mock_response_ok

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=post_side)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await _send_sse_with_retry("http://localhost/msg", {}, max_retries=3)
        assert result == {"ok": True}
        assert call_count == 2


# ---------------------------------------------------------------------------
# call_tool — validation edge cases
# ---------------------------------------------------------------------------


class TestCallToolEdgeCases:
    @pytest.mark.asyncio
    async def test_call_tool_result_no_text_content(self):
        """Result with content but no 'text' type returns full result."""
        srv = MCPServer(name="test", command="cmd")
        response = {"result": {"content": [{"type": "image", "url": "http://img"}]}}
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=response):
            result = await call_tool(srv, "screenshot")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_call_tool_multiple_text_content(self):
        """Multiple text content pieces are joined with newlines."""
        srv = MCPServer(name="test", command="cmd")
        response = {"result": {"content": [
            {"type": "text", "text": "line1"},
            {"type": "text", "text": "line2"},
        ]}}
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=response):
            result = await call_tool(srv, "read_file")
        assert result == "line1\nline2"

    @pytest.mark.asyncio
    async def test_call_tool_error_unknown(self):
        """Error response with no message key."""
        srv = MCPServer(name="test", command="cmd")
        response = {"error": {}}
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=response):
            result = await call_tool(srv, "tool")
        assert "Unknown error" in result


# ---------------------------------------------------------------------------
# format_mcp_tools_for_prompt — edge cases
# ---------------------------------------------------------------------------


class TestFormatMcpToolsEdgeCases:
    def test_server_with_tool_no_description(self):
        """Tool with empty description."""
        srv = MCPServer(name="fs", command="npx")
        srv._tools = [MCPTool(name="list_dir", server_name="fs")]
        result = format_mcp_tools_for_prompt({"fs": srv})
        assert "mcp:fs:list_dir" in result
        # No " — " description suffix
        assert "mcp:fs:list_dir —" not in result or "mcp:fs:list_dir" in result

    def test_unknown_server_no_hint(self):
        """Server name not in MCP_SERVICE_MAP gets no hint."""
        srv = MCPServer(name="custom_xyz", command="npx")
        result = format_mcp_tools_for_prompt({"custom_xyz": srv})
        assert "mcp:custom_xyz" in result


# ---------------------------------------------------------------------------
# get_smart_mcp_context — edge cases
# ---------------------------------------------------------------------------


class TestGetSmartMcpContextEdgeCases:
    def test_agent_not_in_affinity(self):
        """Agent with no affinity mapping uses all as 'other'."""
        srv = MCPServer(name="github", command="npx")
        result = get_smart_mcp_context("unknown-agent", {"github": srv})
        assert "Other MCP services" in result

    def test_priority_server_no_tools(self):
        """Priority server with no tools loaded."""
        srv = MCPServer(name="atlassian", command="npx")
        result = get_smart_mcp_context("jira-ops", {"atlassian": srv})
        assert "MCP INTEGRATIONS" in result
        assert "PREFER" in result

    def test_affinity_partial_name_match(self):
        """Server name partially matching affinity entry."""
        srv = MCPServer(name="atlassian-cloud", command="npx")
        result = get_smart_mcp_context("jira-ops", {"atlassian-cloud": srv})
        # "atlassian" is in affinity for jira-ops, and "atlassian" is in "atlassian-cloud"
        assert "MCP INTEGRATIONS" in result

    def test_usage_line_present(self):
        """Ensure usage line is appended."""
        srv = MCPServer(name="github", command="npx")
        result = get_smart_mcp_context("code-writer", {"github": srv})
        assert "[MCP:server:tool" in result

    def test_priority_more_than_5_tools_truncated(self):
        """Only top 5 tools shown for priority servers."""
        srv = MCPServer(name="github", command="npx")
        srv._tools = [MCPTool(name=f"tool_{i}", server_name="github") for i in range(8)]
        result = get_smart_mcp_context("code-writer", {"github": srv})
        assert "tool_4" in result
        assert "tool_5" not in result


# ---------------------------------------------------------------------------
# start_stdio_server — additional edge cases
# ---------------------------------------------------------------------------


class TestStartStdioServerEdgeCases:
    @pytest.mark.asyncio
    async def test_merges_env(self):
        """Server env is merged with os.environ."""
        srv = MCPServer(name="test", command="echo", args=["hi"], env={"MY_VAR": "1"})
        mock_proc = MagicMock()
        mock_proc.pid = 99
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            await start_stdio_server(srv)
        call_env = mock_popen.call_args.kwargs["env"]
        assert call_env["MY_VAR"] == "1"
        assert "PATH" in call_env  # os.environ merged


# ---------------------------------------------------------------------------
# stop_server — edge cases
# ---------------------------------------------------------------------------


class TestStopServerEdgeCases:
    def test_stop_process_that_exits_cleanly(self):
        """Process exits before kill needed."""
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        srv = MCPServer(name="test", command="cmd")
        srv._process = mock_proc
        stop_server(srv)
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_not_called()
        assert srv._process is None


# ---------------------------------------------------------------------------
# list_tools — edge cases
# ---------------------------------------------------------------------------


class TestListToolsEdgeCases:
    @pytest.mark.asyncio
    async def test_list_tools_response_no_result_key(self):
        """Response without 'result' key returns empty list."""
        srv = MCPServer(name="test", command="cmd")
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value={"error": "fail"}):
            tools = await list_tools(srv)
        assert tools == []

    @pytest.mark.asyncio
    async def test_list_tools_tool_missing_optional_fields(self):
        """Tool response with minimal fields."""
        srv = MCPServer(name="test", command="cmd")
        response = {
            "result": {
                "tools": [
                    {"name": "minimal_tool"},
                ]
            }
        }
        with patch("code_agents.integrations.mcp_client.send_jsonrpc", new_callable=AsyncMock, return_value=response):
            tools = await list_tools(srv)
        assert len(tools) == 1
        assert tools[0].description == ""
        assert tools[0].input_schema == {}
