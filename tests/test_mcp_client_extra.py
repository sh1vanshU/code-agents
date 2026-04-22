"""Extra tests for mcp_client.py — cover missing lines for config errors,
send_jsonrpc stdio timeout, SSE retry details."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from code_agents.integrations.mcp_client import (
    MCPServer,
    MCPTool,
    load_mcp_config,
    send_jsonrpc,
    list_tools,
    call_tool,
    stop_server,
    format_mcp_tools_for_prompt,
    get_smart_mcp_context,
    validate_tool_arguments,
    _read_stdio_with_timeout,
    _send_sse_with_retry,
    start_stdio_server,
)


class TestLoadMcpConfigError:
    """Lines 99-100: Config load error."""

    def test_config_yaml_parse_error(self, tmp_path):
        config_path = tmp_path / "mcp.yaml"
        # Valid YAML but raises in processing
        config_path.write_text("servers:\n  test:\n    command: [[[invalid")
        with patch("code_agents.integrations.mcp_client.MCP_GLOBAL_CONFIG", config_path):
            result = load_mcp_config("")
        assert isinstance(result, dict)


class TestSendJsonrpcStdioTimeout:
    """Lines 118, 132-134: stdio header read timeout and body read timeout."""

    @pytest.mark.asyncio
    async def test_stdio_header_timeout(self):
        """Header readline times out."""
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()

        # Make readline block
        import time
        mock_stdout.readline.side_effect = lambda: time.sleep(5)

        mock_proc = MagicMock()
        mock_proc.stdin = mock_stdin
        mock_proc.stdout = mock_stdout

        srv = MCPServer(name="test", command="cmd")
        srv._process = mock_proc

        # Use very short timeout
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await send_jsonrpc(srv, "tools/list")
        assert result is None

    @pytest.mark.asyncio
    async def test_stdio_body_read_timeout(self):
        """Body read returns None on timeout."""
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()

        async def mock_wait_for(coro, timeout):
            if "readline" in str(coro):
                return b"Content-Length: 100\r\n"
            raise asyncio.TimeoutError()

        mock_stdout.readline.return_value = b"Content-Length: 100\r\n"

        mock_proc = MagicMock()
        mock_proc.stdin = mock_stdin
        mock_proc.stdout = mock_stdout

        srv = MCPServer(name="test", command="cmd")
        srv._process = mock_proc

        with patch("code_agents.integrations.mcp_client._read_stdio_with_timeout",
                    new_callable=AsyncMock, return_value=None):
            # Need to also handle the header read
            header_future = asyncio.Future()
            header_future.set_result(b"Content-Length: 100\r\n")
            with patch("asyncio.wait_for", return_value=b"Content-Length: 100\r\n"):
                result = await send_jsonrpc(srv, "tools/list")
        # Should return None when body read fails
        assert result is None


class TestSendSseWithRetryDetails:
    """Lines 162, 177-178: SSE retry with 500 error and exhausted retries."""

    @pytest.mark.asyncio
    async def test_sse_timeout_retry(self):
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _send_sse_with_retry("http://localhost/msg", {}, max_retries=2)
        assert result is None


class TestStartStdioServerFailure:
    """Lines 132-134: Start stdio server failure."""

    @pytest.mark.asyncio
    async def test_start_failure_returns_none(self):
        srv = MCPServer(name="test", command="/nonexistent/cmd")
        with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
            result = await start_stdio_server(srv)
        assert result is None


class TestCallToolWithValidation:
    """Lines 281-283: call_tool with matching tool and validation warnings."""

    @pytest.mark.asyncio
    async def test_call_tool_validation_multiple_errors(self):
        srv = MCPServer(name="test", command="cmd")
        srv._tools = [MCPTool(
            name="write",
            input_schema={
                "required": ["path", "content"],
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
            server_name="test",
        )]
        response = {"result": {"content": [{"type": "text", "text": "done"}]}}
        with patch("code_agents.integrations.mcp_client.send_jsonrpc",
                    new_callable=AsyncMock, return_value=response):
            result = await call_tool(srv, "write", {"path": 123})
        assert result == "done"


class TestStopServerNone:
    """Lines 307-308: stop_server with kill fallback."""

    def test_stop_no_process_is_noop(self):
        srv = MCPServer(name="test")
        srv._process = None
        stop_server(srv)  # Should not crash


class TestFormatMcpToolsService:
    """Lines 316: format with service map hints."""

    def test_format_with_unknown_service(self):
        srv = MCPServer(name="custom-tool", command="npx")
        result = format_mcp_tools_for_prompt({"custom-tool": srv})
        assert "mcp:custom-tool" in result
        assert "[MCP:" in result


class TestGetSmartMcpContextDetails:
    """Lines 298: Smart context with partial affinity match."""

    def test_partial_affinity_match(self):
        """Server name partially matches an affinity entry."""
        srv = MCPServer(name="atlassian-cloud", command="npx")
        srv._tools = [MCPTool(name="get_issue", description="Get Jira issue", server_name="atlassian-cloud")]
        result = get_smart_mcp_context("jira-ops", {"atlassian-cloud": srv})
        assert "MCP INTEGRATIONS" in result
        assert "PREFER" in result

    def test_smart_context_usage_hint(self):
        """Context always includes usage hint when servers present."""
        srv = MCPServer(name="github", command="npx")
        result = get_smart_mcp_context("code-writer", {"github": srv})
        assert "[MCP:" in result
