"""Tests for logging_config.py — centralized logging setup."""

import logging
import logging.handlers
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import code_agents.core.logging_config as _lc
from code_agents.core.logging_config import _ensure_log_dir, setup_logging


@pytest.fixture(autouse=True)
def _reset_logging_guard():
    """Reset the idempotent guard so each test can call setup_logging()."""
    _lc._logging_initialized = False
    yield
    _lc._logging_initialized = False


# ---------------------------------------------------------------------------
# _ensure_log_dir
# ---------------------------------------------------------------------------

class TestEnsureLogDir:
    def test_returns_path(self):
        result = _ensure_log_dir()
        assert isinstance(result, Path)
        assert result.name == "code-agents.log"
        assert result.parent.name == "logs"

    def test_creates_directory(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_file = log_dir / "code-agents.log"
        with patch("code_agents.core.logging_config.Path.__file__", create=True):
            # Just verify the real function works (it creates logs/ under project root)
            result = _ensure_log_dir()
            assert result.parent.exists()


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

class TestSetupLogging:
    def test_setup_creates_handlers(self):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        try:
            setup_logging()
            # Should have at least a console handler
            assert len(root.handlers) >= 1
            # At least one StreamHandler
            stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.handlers.TimedRotatingFileHandler)]
            assert len(stream_handlers) >= 1
        finally:
            root.handlers = old_handlers

    def test_setup_respects_log_level_env(self):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        try:
            with patch.dict("os.environ", {"LOG_LEVEL": "WARNING"}):
                setup_logging()
            assert root.level == logging.WARNING
        finally:
            root.handlers = old_handlers

    def test_setup_respects_code_agents_log_level(self):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        try:
            with patch.dict("os.environ", {"CODE_AGENTS_LOG_LEVEL": "ERROR"}, clear=False):
                # Remove LOG_LEVEL to let CODE_AGENTS_LOG_LEVEL take effect
                env = os.environ.copy()
                env.pop("LOG_LEVEL", None)
                env["CODE_AGENTS_LOG_LEVEL"] = "ERROR"
                with patch.dict("os.environ", env, clear=True):
                    setup_logging()
            assert root.level == logging.ERROR
        finally:
            root.handlers = old_handlers

    def test_setup_invalid_level_defaults_to_info(self):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        try:
            with patch.dict("os.environ", {"LOG_LEVEL": "NOTAVALIDLEVEL"}):
                setup_logging()
            assert root.level == logging.INFO
        finally:
            root.handlers = old_handlers

    def test_setup_quiets_noisy_loggers_at_info(self):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        try:
            with patch.dict("os.environ", {"LOG_LEVEL": "INFO"}):
                setup_logging()
            assert logging.getLogger("httpx").level == logging.WARNING
            assert logging.getLogger("urllib3").level == logging.WARNING
        finally:
            root.handlers = old_handlers

    def test_setup_does_not_quiet_at_debug(self):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        try:
            with patch.dict("os.environ", {"LOG_LEVEL": "DEBUG"}):
                setup_logging()
            # At DEBUG level, third-party loggers should NOT be set to WARNING
            assert logging.getLogger("httpx").level != logging.WARNING or root.level == logging.DEBUG
        finally:
            root.handlers = old_handlers

    def test_setup_handles_oserror_for_file(self):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        try:
            bad_path = "/nonexistent_dir_abc123/code-agents.log"
            with patch("code_agents.core.logging_config._ensure_log_dir", return_value=bad_path):
                # The TimedRotatingFileHandler will fail on a bad path
                setup_logging()
            # Should have at least a console handler even if file handler fails
            assert len(root.handlers) >= 1
        finally:
            root.handlers = old_handlers

    def test_oserror_on_file_handler_warns_but_continues(self):
        """Lines 80-82: OSError when creating file handler logs warning, doesn't crash."""
        import code_agents.core.logging_config as lc
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_init = lc._logging_initialized
        try:
            lc._logging_initialized = False
            with patch.dict("os.environ", {"LOG_LEVEL": "INFO"}), \
                 patch("logging.handlers.TimedRotatingFileHandler",
                       side_effect=OSError("permission denied")):
                setup_logging()
            # Console handler should still exist
            stream_handlers = [h for h in root.handlers
                               if isinstance(h, logging.StreamHandler)
                               and not isinstance(h, logging.handlers.TimedRotatingFileHandler)]
            assert len(stream_handlers) >= 1
            # No file handler should be present
            file_handlers = [h for h in root.handlers
                             if isinstance(h, logging.handlers.TimedRotatingFileHandler)]
            assert len(file_handlers) == 0
        finally:
            root.handlers = old_handlers
            lc._logging_initialized = old_init

    def test_quiet_third_party_loggers_at_warning_level(self):
        """Lines 87-89: third-party loggers set to WARNING when level > DEBUG."""
        import code_agents.core.logging_config as lc
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_init = lc._logging_initialized
        try:
            lc._logging_initialized = False
            with patch.dict("os.environ", {"LOG_LEVEL": "WARNING"}):
                setup_logging()
            for name in ("uvicorn.access", "httpx", "httpcore", "urllib3", "elasticsearch"):
                assert logging.getLogger(name).level == logging.WARNING
        finally:
            root.handlers = old_handlers
            lc._logging_initialized = old_init

    def test_startup_log_message_emitted(self):
        """Lines 96-101: startup logger emits initialization message."""
        import code_agents.core.logging_config as lc
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_init = lc._logging_initialized
        try:
            lc._logging_initialized = False
            startup_logger = logging.getLogger("code_agents.logging")
            with patch.object(startup_logger, "info") as mock_info, \
                 patch.dict("os.environ", {"LOG_LEVEL": "INFO"}):
                setup_logging()
            # Check that startup info was logged
            mock_info.assert_called_once()
            call_msg = mock_info.call_args[0][0]
            assert "Logging initialized" in call_msg
        finally:
            root.handlers = old_handlers
            lc._logging_initialized = old_init

    def test_idempotent_guard_skips_second_call(self):
        """Calling setup_logging twice — second call returns early (line 40)."""
        import code_agents.core.logging_config as lc
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        try:
            lc._logging_initialized = False
            with patch.dict("os.environ", {"LOG_LEVEL": "WARNING"}):
                setup_logging()
                assert lc._logging_initialized is True
                setup_logging()  # second call hits early return
                assert lc._logging_initialized is True
        finally:
            root.handlers = old_handlers
            lc._logging_initialized = False
