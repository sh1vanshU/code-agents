"""CLI preview command — launch live preview server for static files."""

from __future__ import annotations

import logging
import os
import sys
import time

logger = logging.getLogger("code_agents.cli.cli_preview")


def cmd_preview(args: list[str] | None = None):
    """Start a live preview server for static files.

    Usage:
      code-agents preview
      code-agents preview --port 8080

    Detects public/, dist/, build/, or static/ directories and serves them
    on localhost with CORS headers and live-reload support.
    """
    from .cli_helpers import _colors

    bold, green, yellow, red, cyan, dim = _colors()

    args = args if args is not None else sys.argv[2:]

    if "--help" in args or "-h" in args:
        print(cmd_preview.__doc__)
        return

    port = 3333
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--port" and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except ValueError:
                print(red(f"  Invalid port: {args[i + 1]}"))
                return
            i += 1
        i += 1

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    from code_agents.ui.live_preview import LivePreviewServer, detect_static_dir

    static = detect_static_dir(cwd)
    if not static:
        print(red("  No static directory found."))
        print(dim("  Expected one of: public/, dist/, build/, static/, or index.html in project root."))
        return

    print(bold(f"  Live Preview Server"))
    print(dim(f"  Serving: {static}"))
    print(dim(f"  Port: {port}"))
    print()

    server = LivePreviewServer(cwd=cwd, port=port)
    try:
        server.start()
        print(green(f"  Running at {server.url}"))
        print(dim("  Press Ctrl+C to stop"))
        print()
        # Keep running until Ctrl+C
        while True:
            time.sleep(1.0)
    except FileNotFoundError as exc:
        print(red(f"  {exc}"))
    except KeyboardInterrupt:
        print()
        print(dim("  Stopping preview server..."))
    finally:
        server.stop()
        print(dim("  Stopped."))
