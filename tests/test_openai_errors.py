"""Tests for openai_errors.py — OpenAI-style error formatting."""

from unittest.mock import patch, MagicMock

import pytest

from code_agents.core.openai_errors import (
    openai_style_error,
    unwrap_process_error,
    format_process_error_message,
    process_error_json_response,
)


# ---------------------------------------------------------------------------
# openai_style_error
# ---------------------------------------------------------------------------

class TestOpenaiStyleError:
    def test_default_fields(self):
        result = openai_style_error("something broke")
        assert result == {
            "error": {
                "message": "something broke",
                "type": "internal_error",
                "code": "cursor_agent_error",
            }
        }

    def test_custom_type_and_code(self):
        result = openai_style_error("bad req", error_type="invalid_request", code="bad_param")
        assert result["error"]["type"] == "invalid_request"
        assert result["error"]["code"] == "bad_param"

    def test_empty_message(self):
        result = openai_style_error("")
        assert result["error"]["message"] == ""


# ---------------------------------------------------------------------------
# unwrap_process_error
# ---------------------------------------------------------------------------

class TestUnwrapProcessError:
    def test_none_input(self):
        assert unwrap_process_error(None) is None

    def test_no_cursor_sdk(self):
        with patch.dict("sys.modules", {"cursor_agent_sdk": None, "cursor_agent_sdk._errors": None}):
            with patch("builtins.__import__", side_effect=ImportError):
                assert unwrap_process_error(Exception("test")) is None

    def test_plain_exception_no_process_error(self):
        # Without cursor_agent_sdk installed, should return None
        result = unwrap_process_error(ValueError("just a value error"))
        # If cursor_agent_sdk is not installed, returns None (ImportError path)
        assert result is None

    def test_with_cause_chain(self):
        inner = ValueError("inner")
        outer = RuntimeError("outer")
        outer.__cause__ = inner
        # Without ProcessError class available, should return None
        result = unwrap_process_error(outer)
        assert result is None

    def test_direct_process_error(self):
        """When exc is a ProcessError, return it directly."""
        mock_pe_class = type("ProcessError", (Exception,), {})
        mock_pe = mock_pe_class("agent failed")
        mock_module = MagicMock()
        mock_module.ProcessError = mock_pe_class
        with patch.dict("sys.modules", {"cursor_agent_sdk._errors": mock_module, "cursor_agent_sdk": MagicMock()}):
            result = unwrap_process_error(mock_pe)
            assert result is mock_pe

    def test_exception_group_unwrap(self):
        """ProcessError inside an ExceptionGroup is found."""
        mock_pe_class = type("ProcessError", (Exception,), {})
        mock_pe = mock_pe_class("nested error")
        mock_module = MagicMock()
        mock_module.ProcessError = mock_pe_class
        # Create a real ExceptionGroup (Python 3.11+)
        try:
            group = ExceptionGroup("group", [ValueError("a"), mock_pe])
        except NameError:
            pytest.skip("ExceptionGroup requires Python 3.11+")
        with patch.dict("sys.modules", {"cursor_agent_sdk._errors": mock_module, "cursor_agent_sdk": MagicMock()}):
            result = unwrap_process_error(group)
            assert result is mock_pe

    def test_cause_chain_with_process_error(self):
        """ProcessError in __cause__ chain is found."""
        mock_pe_class = type("ProcessError", (Exception,), {})
        mock_pe = mock_pe_class("deep error")
        mock_module = MagicMock()
        mock_module.ProcessError = mock_pe_class
        outer = RuntimeError("wrapper")
        outer.__cause__ = mock_pe
        with patch.dict("sys.modules", {"cursor_agent_sdk._errors": mock_module, "cursor_agent_sdk": MagicMock()}):
            result = unwrap_process_error(outer)
            assert result is mock_pe


# ---------------------------------------------------------------------------
# format_process_error_message
# ---------------------------------------------------------------------------

class TestFormatProcessErrorMessage:
    def test_basic_message(self):
        exc = Exception("connection refused")
        msg = format_process_error_message(exc)
        assert "connection refused" in msg
        assert "Hint:" in msg

    def test_with_stderr(self):
        exc = Exception("failed")
        exc.stderr = "some stderr output"
        msg = format_process_error_message(exc)
        assert "cursor-agent stderr" in msg
        assert "some stderr output" in msg

    def test_no_stderr_attr(self):
        exc = Exception("no stderr")
        msg = format_process_error_message(exc)
        assert "cursor-agent stderr" not in msg

    def test_empty_stderr(self):
        exc = Exception("empty")
        exc.stderr = "   "
        msg = format_process_error_message(exc)
        assert "cursor-agent stderr" not in msg

    def test_unicode_safety(self):
        exc = Exception("bad \ud800 surrogate")
        exc.stderr = None
        msg = format_process_error_message(exc)
        # Should not raise, message should be a valid string
        msg.encode("utf-8")  # should not raise


# ---------------------------------------------------------------------------
# process_error_json_response
# ---------------------------------------------------------------------------

class TestProcessErrorJsonResponse:
    def test_returns_502(self):
        exc = Exception("process failed")
        resp = process_error_json_response(exc)
        assert resp.status_code == 502

    def test_response_body_structure(self):
        exc = Exception("test error")
        resp = process_error_json_response(exc)
        assert resp.status_code == 502
        # The body is set via content kwarg

    def test_with_stderr(self):
        exc = Exception("err")
        exc.stderr = "detailed error"
        resp = process_error_json_response(exc)
        assert resp.status_code == 502


class TestUnwrapProcessErrorImportFallback:
    """Cover lines 30-31: BaseExceptionGroup import failure fallback."""

    def test_import_error_fallback(self):
        """When BaseExceptionGroup can't be imported, unwrap still works."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "builtins":
                raise ImportError("simulated: no BaseExceptionGroup")
            return original_import(name, *args, **kwargs)

        exc = ValueError("test")
        with patch("builtins.__import__", side_effect=mock_import):
            result = unwrap_process_error(exc)
        assert result is None
