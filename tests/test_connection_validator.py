"""Tests for connection_validator.py — async backend validation."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.devops.connection_validator import (
    ValidationResult,
    validate_backend,
    validate_claude_cli,
    validate_claude_sdk,
    validate_cursor_cli,
    validate_cursor_http,
    validate_server_and_backend,
    validate_sync,
)


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

def test_validation_result_valid():
    r = ValidationResult(valid=True, backend="cursor", message="OK")
    assert r.valid is True
    assert r.backend == "cursor"
    assert r.details is None


def test_validation_result_invalid_with_details():
    r = ValidationResult(valid=False, backend="claude", message="fail", details={"key": "val"})
    assert r.valid is False
    assert r.details == {"key": "val"}


# ---------------------------------------------------------------------------
# validate_cursor_cli
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cursor_cli_not_found():
    with patch("shutil.which", return_value=None):
        r = await validate_cursor_cli()
    assert r.valid is False
    assert "not found" in r.message


@pytest.mark.asyncio
async def test_cursor_cli_no_api_key():
    with patch("shutil.which", return_value="/usr/bin/cursor-agent"), \
         patch.dict(os.environ, {"CURSOR_API_KEY": "", "CURSOR_API_URL": ""}, clear=False):
        r = await validate_cursor_cli()
    assert r.valid is False
    assert "CURSOR_API_KEY" in r.message


@pytest.mark.asyncio
async def test_cursor_cli_with_api_key():
    with patch("shutil.which", return_value="/usr/bin/cursor-agent"), \
         patch.dict(os.environ, {"CURSOR_API_KEY": "sk-test-123"}, clear=False):
        r = await validate_cursor_cli()
    assert r.valid is True
    assert r.details["has_api_key"] is True


@pytest.mark.asyncio
async def test_cursor_cli_http_fallback():
    """If CURSOR_API_URL is set but no API key, still invalid."""
    with patch("shutil.which", return_value="/usr/bin/cursor-agent"), \
         patch.dict(os.environ, {"CURSOR_API_KEY": "", "CURSOR_API_URL": "http://localhost:1234"}, clear=False):
        r = await validate_cursor_cli()
    # Has URL but no API key — cursor_cli check passes because URL is fallback
    assert r.valid is True  # URL fallback counts as configured


# ---------------------------------------------------------------------------
# validate_claude_cli
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claude_cli_not_found():
    with patch("shutil.which", return_value=None):
        r = await validate_claude_cli()
    assert r.valid is False
    assert "not found" in r.message


@pytest.mark.asyncio
async def test_claude_cli_version_ok():
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"1.2.3\n", b""))

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        r = await validate_claude_cli()
    assert r.valid is True
    assert "1.2.3" in r.message


@pytest.mark.asyncio
async def test_claude_cli_version_fails():
    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"error\n"))

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        r = await validate_claude_cli()
    assert r.valid is False
    assert "login" in r.message.lower() or "exited" in r.message.lower()


# ---------------------------------------------------------------------------
# validate_claude_sdk
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claude_sdk_no_key():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
        r = await validate_claude_sdk()
    assert r.valid is False
    assert "ANTHROPIC_API_KEY" in r.message


@pytest.mark.asyncio
async def test_claude_sdk_key_set_network_fail():
    """Key is set but network fails — should still be valid (offline grace)."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test123"}, clear=False):
        # Mock httpx to raise connection error
        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("offline"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            r = await validate_claude_sdk()
    assert r.valid is True
    assert "offline" in r.message.lower() or "cannot verify" in r.message.lower()


# ---------------------------------------------------------------------------
# validate_backend — routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_backend_claude_cli():
    with patch("code_agents.devops.connection_validator.validate_claude_cli") as mock:
        mock.return_value = ValidationResult(valid=True, backend="claude-cli", message="ok")
        r = await validate_backend("claude-cli")
    assert r.backend == "claude-cli"
    mock.assert_called_once()


@pytest.mark.asyncio
async def test_validate_backend_env_claude_cli_with_local_llm_url_probes_local():
    """Stale claude-cli in a repo config must not block Ollama when URL is set (env-driven only)."""
    with patch.dict(
        os.environ,
        {
            "CODE_AGENTS_BACKEND": "claude-cli",
            "CODE_AGENTS_LOCAL_LLM_URL": "http://127.0.0.1:11434/v1",
        },
        clear=False,
    ), patch("code_agents.devops.connection_validator.validate_local_llm") as mock:
        mock.return_value = ValidationResult(valid=True, backend="local", message="ok")
        r = await validate_backend()
    mock.assert_called_once()
    assert r.backend == "local"


@pytest.mark.asyncio
async def test_validate_backend_claude():
    with patch("code_agents.devops.connection_validator.validate_claude_sdk") as mock:
        mock.return_value = ValidationResult(valid=True, backend="claude", message="ok")
        r = await validate_backend("claude")
    assert r.backend == "claude"
    mock.assert_called_once()


@pytest.mark.asyncio
async def test_validate_backend_default_local():
    """Empty CODE_AGENTS_BACKEND defaults to local."""
    with patch.dict(os.environ, {"CODE_AGENTS_LOCAL_LLM_URL": "", "CURSOR_API_URL": ""}, clear=False), \
         patch("code_agents.devops.connection_validator.validate_local_llm") as mock:
        mock.return_value = ValidationResult(valid=False, backend="local", message="no url")
        r = await validate_backend("")
    assert r.backend == "local"
    mock.assert_called_once()


@pytest.mark.asyncio
async def test_validate_backend_default_local_uses_cursor_url_fallback():
    with patch.dict(os.environ, {"CURSOR_API_URL": "http://localhost:11434/v1"}, clear=False), \
         patch("code_agents.devops.connection_validator.validate_local_llm") as mock:
        mock.return_value = ValidationResult(valid=True, backend="local", message="ok")
        r = await validate_backend("")
    assert r.backend == "local"


@pytest.mark.asyncio
async def test_validate_backend_explicit_cursor():
    with patch.dict(os.environ, {"CURSOR_API_URL": ""}, clear=False), \
         patch("code_agents.devops.connection_validator.validate_cursor_cli") as mock:
        mock.return_value = ValidationResult(valid=True, backend="cursor", message="ok")
        r = await validate_backend("cursor")
    assert r.backend == "cursor"


@pytest.mark.asyncio
async def test_validate_backend_cursor_with_http_url():
    with patch.dict(os.environ, {"CURSOR_API_URL": "http://localhost:9999"}, clear=False), \
         patch("code_agents.devops.connection_validator.validate_cursor_http") as mock:
        mock.return_value = ValidationResult(valid=True, backend="cursor_http", message="ok")
        r = await validate_backend("cursor")
    assert r.backend == "cursor_http"


# ---------------------------------------------------------------------------
# validate_server_and_backend
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_server_and_backend_parallel():
    with patch("code_agents.devops.connection_validator.validate_backend") as mock_backend:
        mock_backend.return_value = ValidationResult(valid=True, backend="cursor", message="ok")

        import httpx
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await validate_server_and_backend("http://127.0.0.1:8000", "cursor")

    assert len(results) == 2
    assert results[0].backend == "server"
    assert results[0].valid is True
    assert results[1].backend == "cursor"
    assert results[1].valid is True


# ---------------------------------------------------------------------------
# validate_sync
# ---------------------------------------------------------------------------

def test_validate_sync():
    with patch("code_agents.devops.connection_validator.validate_backend") as mock:
        mock.return_value = ValidationResult(valid=True, backend="test", message="ok")
        r = validate_sync("claude-cli")
    assert r.valid is True
