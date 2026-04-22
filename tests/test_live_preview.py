"""Tests for the live preview server."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.ui.live_preview import (
    LivePreviewServer,
    detect_static_dir,
    format_preview_status,
    _CORSHandler,
    _STATIC_CANDIDATES,
)


class TestDetectStaticDir:
    """Test static directory detection."""

    def test_public_dir(self, tmp_path):
        (tmp_path / "public").mkdir()
        result = detect_static_dir(str(tmp_path))
        assert result is not None
        assert result.endswith("public")

    def test_dist_dir(self, tmp_path):
        (tmp_path / "dist").mkdir()
        result = detect_static_dir(str(tmp_path))
        assert result is not None
        assert result.endswith("dist")

    def test_build_dir(self, tmp_path):
        (tmp_path / "build").mkdir()
        result = detect_static_dir(str(tmp_path))
        assert result is not None
        assert result.endswith("build")

    def test_static_dir(self, tmp_path):
        (tmp_path / "static").mkdir()
        result = detect_static_dir(str(tmp_path))
        assert result is not None
        assert result.endswith("static")

    def test_index_html_fallback(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>")
        result = detect_static_dir(str(tmp_path))
        assert result == str(tmp_path)

    def test_no_static_dir(self, tmp_path):
        result = detect_static_dir(str(tmp_path))
        assert result is None

    def test_priority_order(self, tmp_path):
        """public/ should be preferred over dist/."""
        (tmp_path / "public").mkdir()
        (tmp_path / "dist").mkdir()
        result = detect_static_dir(str(tmp_path))
        assert result is not None
        assert result.endswith("public")


class TestLivePreviewServer:
    """Test LivePreviewServer lifecycle."""

    def test_init_defaults(self):
        server = LivePreviewServer(cwd="/tmp", port=4444)
        assert server.port == 4444
        assert server.cwd == "/tmp"
        assert not server.is_running
        assert server.url == "http://127.0.0.1:4444"

    def test_start_no_static_dir(self, tmp_path):
        """Should raise FileNotFoundError when no static dir exists."""
        server = LivePreviewServer(cwd=str(tmp_path), port=0)
        with pytest.raises(FileNotFoundError, match="No static directory"):
            server.start()

    def test_start_and_stop(self, tmp_path):
        """Should start and stop cleanly when a static dir exists."""
        (tmp_path / "public").mkdir()
        (tmp_path / "public" / "index.html").write_text("<h1>Hello</h1>")

        server = LivePreviewServer(cwd=str(tmp_path), port=0)
        # Use a random available port
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        server.port = port
        server.start()
        assert server.is_running
        assert server.static_dir is not None
        assert "public" in server.static_dir

        server.stop()
        assert not server.is_running

    def test_reload_sets_event(self, tmp_path):
        (tmp_path / "public").mkdir()
        server = LivePreviewServer(cwd=str(tmp_path))
        # reload should not crash even when not running
        server.reload()
        assert server._reload_event.is_set()

    def test_double_start_warning(self, tmp_path):
        """Starting twice should not crash."""
        (tmp_path / "dist").mkdir()
        (tmp_path / "dist" / "index.html").write_text("<html></html>")

        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        server = LivePreviewServer(cwd=str(tmp_path), port=port)
        try:
            server.start()
            server.start()  # second start should be a no-op
            assert server.is_running
        finally:
            server.stop()


class TestFormatPreviewStatus:
    def test_running(self, tmp_path):
        (tmp_path / "public").mkdir()
        server = LivePreviewServer(cwd=str(tmp_path), port=5555)
        server._running = True
        server._static_dir = str(tmp_path / "public")
        output = format_preview_status(server)
        assert "RUNNING" in output
        assert "5555" in output

    def test_stopped(self, tmp_path):
        server = LivePreviewServer(cwd=str(tmp_path))
        output = format_preview_status(server)
        assert "STOPPED" in output
