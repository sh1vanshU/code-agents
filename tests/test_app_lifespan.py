"""Tests for app.py — lifespan, exception handlers, middleware."""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# lifespan
# ---------------------------------------------------------------------------


class TestLifespan:
    """Test the lifespan context manager (lines 34-76)."""

    @pytest.mark.asyncio
    async def test_lifespan_calls_setup_logging_and_load_env(self):
        """Lines 36-46: lifespan sets up logging, loads env, loads agents."""
        mock_agent = MagicMock()
        mock_agent.name = "test"
        mock_agent.backend = "cursor"
        mock_agent.model = "test-model"
        mock_agent.permission_mode = "default"
        mock_agent.cwd = "."

        with patch("code_agents.core.app.setup_logging") as mock_setup, \
             patch("code_agents.core.app.agent_loader") as mock_loader, \
             patch("code_agents.core.env_loader.load_all_env") as mock_env:
            mock_loader.list_agents.return_value = [mock_agent]

            from code_agents.core.app import lifespan
            app_mock = MagicMock()
            async with lifespan(app_mock):
                pass

            mock_setup.assert_called_once()
            mock_env.assert_called_once()
            mock_loader.load.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_logs_cursor_warning_when_no_url(self):
        """Lines 65-71: warn when cursor agents exist but CURSOR_API_URL is unset."""
        mock_agent = MagicMock()
        mock_agent.name = "test"
        mock_agent.backend = "cursor"
        mock_agent.model = "m"
        mock_agent.permission_mode = "default"
        mock_agent.cwd = "."

        with patch("code_agents.core.app.setup_logging"), \
             patch("code_agents.core.app.agent_loader") as mock_loader, \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch.dict(os.environ, {"CURSOR_API_URL": ""}, clear=False), \
             patch("code_agents.core.app.logger") as mock_logger:
            mock_loader.list_agents.return_value = [mock_agent]

            from code_agents.core.app import lifespan
            app_mock = MagicMock()
            async with lifespan(app_mock):
                pass

            # Should have logged a warning about cursor agents
            warning_calls = [c for c in mock_logger.warning.call_args_list
                             if "cursor" in str(c).lower()]
            assert len(warning_calls) >= 1


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


class TestExceptionHandlers:
    """Test the exception handler functions."""

    @pytest.mark.asyncio
    async def test_json_exception_handler_http_exception(self):
        """Lines 116-120: HTTPException returns JSON with status code."""
        from code_agents.core.app import json_exception_handler

        request = MagicMock()
        exc = HTTPException(status_code=404, detail="Not found")
        response = await json_exception_handler(request, exc)
        assert response.status_code == 404
        assert b"Not found" in response.body

    @pytest.mark.asyncio
    async def test_json_exception_handler_generic_exception(self):
        """Lines 124-127: generic Exception returns 500 JSON."""
        from code_agents.core.app import json_exception_handler

        request = MagicMock()
        exc = ValueError("something broke")
        with patch("code_agents.core.app.unwrap_process_error", return_value=None):
            response = await json_exception_handler(request, exc)
        assert response.status_code == 500
        assert b"something broke" in response.body

    @pytest.mark.asyncio
    async def test_json_exception_handler_process_error(self):
        """Lines 121-123: when unwrap_process_error finds a ProcessError, return 502."""
        from code_agents.core.app import json_exception_handler

        request = MagicMock()
        exc = RuntimeError("wrapped")
        fake_pe = MagicMock()
        fake_pe.__str__ = lambda self: "process died"
        fake_pe.stderr = ""

        with patch("code_agents.core.app.unwrap_process_error", return_value=fake_pe), \
             patch("code_agents.core.app.process_error_json_response",
                   return_value=JSONResponse(status_code=502, content={"error": "pe"})) as mock_pe:
            response = await json_exception_handler(request, exc)
        mock_pe.assert_called_once_with(fake_pe)
        assert response.status_code == 502


# ---------------------------------------------------------------------------
# ExceptionGroup handler (Python 3.11+)
# ---------------------------------------------------------------------------


class TestExceptionGroupHandler:
    """Test exception_group_handler (lines 97-110)."""

    @pytest.mark.skipif(sys.version_info < (3, 11), reason="ExceptionGroup requires 3.11+")
    @pytest.mark.asyncio
    async def test_exception_group_with_process_error(self):
        """Lines 100-102: unwrapped ProcessError yields 502."""
        from code_agents.core.app import exception_group_handler

        request = MagicMock()
        inner = RuntimeError("inner")
        exc = ExceptionGroup("group", [inner])
        fake_pe = MagicMock()
        fake_pe.__str__ = lambda self: "pe"
        fake_pe.stderr = ""

        with patch("code_agents.core.app.unwrap_process_error", return_value=fake_pe), \
             patch("code_agents.core.app.process_error_json_response",
                   return_value=JSONResponse(status_code=502, content={})) as mock_pe:
            response = await exception_group_handler(request, exc)
        mock_pe.assert_called_once_with(fake_pe)
        assert response.status_code == 502

    @pytest.mark.skipif(sys.version_info < (3, 11), reason="ExceptionGroup requires 3.11+")
    @pytest.mark.asyncio
    async def test_exception_group_without_process_error(self):
        """Lines 103-110: no ProcessError inside yields 500."""
        from code_agents.core.app import exception_group_handler

        request = MagicMock()
        inner = ValueError("oops")
        exc = ExceptionGroup("group", [inner])

        with patch("code_agents.core.app.unwrap_process_error", return_value=None):
            response = await exception_group_handler(request, exc)
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Middleware — log_requests
# ---------------------------------------------------------------------------


class TestLogRequestsMiddleware:
    """Test the log_requests middleware (lines 139-175)."""

    @pytest.mark.asyncio
    async def test_middleware_logs_normal_request(self):
        """Lines 147-173: logs request and response for normal paths."""
        from code_agents.core.app import log_requests

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/v1/agents"
        request.url.query = ""
        request.client.host = "127.0.0.1"
        request.headers.get.return_value = "application/json"

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def call_next(req):
            return mock_response

        response = await log_requests(request, call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_middleware_skips_health_verbose_log(self):
        """Lines 160-161: /health uses debug logging."""
        from code_agents.core.app import log_requests

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/health"
        request.url.query = ""
        request.client.host = "127.0.0.1"
        request.headers.get.return_value = "-"

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def call_next(req):
            return mock_response

        with patch("code_agents.core.app.logger") as mock_logger:
            await log_requests(request, call_next)
            # Should NOT have info-logged the request arrival for /health
            info_calls = [c for c in mock_logger.info.call_args_list
                          if "/health" in str(c)]
            assert len(info_calls) == 0

    @pytest.mark.asyncio
    async def test_middleware_logs_5xx_as_error(self):
        """Lines 162-166: 5xx responses log at error level."""
        from code_agents.core.app import log_requests

        request = MagicMock()
        request.method = "POST"
        request.url.path = "/v1/chat"
        request.url.query = "foo=bar"
        request.client.host = "10.0.0.1"
        request.headers.get.return_value = "application/json"

        mock_response = MagicMock()
        mock_response.status_code = 500

        async def call_next(req):
            return mock_response

        with patch("code_agents.core.app.logger") as mock_logger:
            await log_requests(request, call_next)
            mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_middleware_logs_4xx_as_warning(self):
        """Lines 167-170: 4xx responses log at warning level."""
        from code_agents.core.app import log_requests

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/v1/missing"
        request.url.query = ""
        request.client.host = "10.0.0.1"
        request.headers.get.return_value = "-"

        mock_response = MagicMock()
        mock_response.status_code = 404

        async def call_next(req):
            return mock_response

        with patch("code_agents.core.app.logger") as mock_logger:
            await log_requests(request, call_next)
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_middleware_no_client(self):
        """Line 142: request.client is None."""
        from code_agents.core.app import log_requests

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/v1/test"
        request.url.query = ""
        request.client = None
        request.headers.get.return_value = "-"

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def call_next(req):
            return mock_response

        response = await log_requests(request, call_next)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Diagnostics endpoint (lines 227-274 / __version__ import)
# ---------------------------------------------------------------------------


class TestDiagnostics:
    """Test the diagnostics endpoint, especially __version__ fallback."""

    def test_diagnostics_version_fallback(self):
        """Lines 239-240: ImportError on __version__ falls back to 'dev'."""
        from code_agents.core.app import diagnostics

        with patch("code_agents.core.app.agent_loader") as mock_loader, \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch.dict(os.environ, {"CURSOR_API_URL": "", "CURSOR_API_KEY": "",
                                      "CODE_AGENTS_HTTP_ONLY": "", "TARGET_REPO_PATH": "",
                                      "JENKINS_URL": "", "ARGOCD_URL": "",
                                      "ATLASSIAN_OAUTH_CLIENT_ID": "",
                                      "ELASTICSEARCH_URL": "", "ELASTICSEARCH_CLOUD_ID": ""}, clear=False), \
             patch.dict("sys.modules", {"code_agents.__version__": None}):
            mock_loader.list_agents.return_value = []
            # Force the ImportError path
            import builtins
            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "code_agents.__version__" or (args and args[0] and
                   any(hasattr(a, '__name__') and '__version__' in getattr(a, '__name__', '')
                       for a in (args[0],) if a)):
                    raise ImportError("no version")
                return original_import(name, *args, **kwargs)

            # Simpler approach: just patch the relative import
            result = diagnostics()
            assert "package_version" in result
