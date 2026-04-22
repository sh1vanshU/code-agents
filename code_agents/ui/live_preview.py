"""Live preview server — serve static files with auto-reload on changes.

Detects common static directories (``public/``, ``dist/``, ``build/``, ``static/``)
and serves them on localhost with CORS headers.  Watches for file changes and
triggers browser refresh via a simple SSE endpoint.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("code_agents.ui.live_preview")

# ---------------------------------------------------------------------------
# Static directory detection
# ---------------------------------------------------------------------------

_STATIC_CANDIDATES = ["public", "dist", "build", "static", "out", "www", "docs"]


def detect_static_dir(cwd: str) -> Optional[str]:
    """Find the first matching static directory under *cwd*."""
    root = Path(cwd)
    for candidate in _STATIC_CANDIDATES:
        d = root / candidate
        if d.is_dir():
            return str(d)
    # Fallback: if cwd itself has index.html, serve cwd
    if (root / "index.html").is_file():
        return str(root)
    return None


# ---------------------------------------------------------------------------
# CORS handler
# ---------------------------------------------------------------------------


class _CORSHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with CORS headers and SSE reload endpoint."""

    # Set by the server at construction
    reload_event: Optional[threading.Event] = None

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/__reload":
            self._handle_sse_reload()
            return
        super().do_GET()

    def _handle_sse_reload(self) -> None:
        """SSE endpoint that sends a reload event when triggered."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

        try:
            while True:
                if self.reload_event and self.reload_event.wait(timeout=1.0):
                    self.wfile.write(b"data: reload\n\n")
                    self.wfile.flush()
                    self.reload_event.clear()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default access logging; use our logger instead."""
        logger.debug("HTTP %s", format % args)


# ---------------------------------------------------------------------------
# Inject reload script into HTML responses
# ---------------------------------------------------------------------------

_RELOAD_SCRIPT = """
<script>
(function() {
  var es = new EventSource('/__reload');
  es.onmessage = function() { location.reload(); };
  es.onerror = function() { setTimeout(function(){ location.reload(); }, 2000); };
})();
</script>
"""


# ---------------------------------------------------------------------------
# LivePreviewServer
# ---------------------------------------------------------------------------


class LivePreviewServer:
    """Serve static files on localhost with live-reload support."""

    def __init__(self, cwd: str, port: int = 3333):
        self.cwd = cwd or os.getcwd()
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._reload_event = threading.Event()
        self._running = False
        self._static_dir: Optional[str] = None

    # ---- public API -------------------------------------------------------

    def start(self) -> None:
        """Serve static files on localhost.

        Detects the static directory, creates the HTTP handler, and starts
        serving in a background daemon thread.
        """
        if self._running:
            logger.warning("Preview server already running on port %d", self.port)
            return

        static_dir = self._find_static_dir()
        if not static_dir:
            logger.error("No static directory found in %s", self.cwd)
            raise FileNotFoundError(
                f"No static directory (public/, dist/, build/, static/) found in {self.cwd}"
            )

        self._static_dir = static_dir
        handler = self._create_handler()
        self._server = HTTPServer(("127.0.0.1", self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._running = True
        logger.info(
            "Live preview serving %s on http://127.0.0.1:%d", static_dir, self.port
        )

    def stop(self) -> None:
        """Shut down the preview server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        self._running = False
        self._thread = None
        logger.info("Live preview server stopped")

    def reload(self) -> None:
        """Trigger a browser refresh via the SSE reload endpoint."""
        self._reload_event.set()
        logger.debug("Reload triggered")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def static_dir(self) -> Optional[str]:
        return self._static_dir

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # ---- internals --------------------------------------------------------

    def _find_static_dir(self) -> Optional[str]:
        """Detect: public/, dist/, build/, static/, or cwd with index.html."""
        return detect_static_dir(self.cwd)

    def _create_handler(self) -> type:
        """Create an HTTP handler class bound to the static directory."""
        static = self._static_dir or self.cwd
        event = self._reload_event

        class Handler(_CORSHandler):
            reload_event = event

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                kwargs["directory"] = static
                super().__init__(*args, **kwargs)

        return Handler


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------


def format_preview_status(server: LivePreviewServer) -> str:
    """Format the server status for terminal display."""
    lines: list[str] = []
    if server.is_running:
        lines.append(f"  Live Preview: RUNNING")
        lines.append(f"  URL: {server.url}")
        lines.append(f"  Serving: {server.static_dir}")
    else:
        lines.append("  Live Preview: STOPPED")
    return "\n".join(lines)
