"""Stdout proxy that captures writes and routes to ChatOutput with ANSI to Rich markup."""

from __future__ import annotations

import io
import logging
import re
from typing import TYPE_CHECKING

logger = logging.getLogger("code_agents.chat.tui.proxy")

if TYPE_CHECKING:
    from .app import ChatTUI
    from .widgets.output_log import ChatOutput

# ── ANSI escape code → Rich markup lookup ────────────────────────────
_ANSI_TO_RICH: dict[str, str] = {
    "\033[1m": "[bold]",
    "\033[2m": "[dim]",
    "\033[3m": "[italic]",
    "\033[31m": "[red]",
    "\033[32m": "[green]",
    "\033[33m": "[yellow]",
    "\033[34m": "[blue]",
    "\033[35m": "[magenta]",
    "\033[36m": "[cyan]",
    "\033[37m": "[white]",
    "\033[90m": "[dim]",
    "\033[91m": "[bright_red]",
}

# Matches any SGR escape sequence: ESC [ <digits> (;<digits>)* m
_ANSI_RE = re.compile(r"\033\[\d+(?:;\d+)*m")


def _ansi_to_rich(text: str) -> str:
    """Convert known ANSI escape codes to Rich markup, strip unknown ones."""

    def _replace(match: re.Match) -> str:
        code = match.group(0)
        if code == "\033[0m":
            return "[/]"
        return _ANSI_TO_RICH.get(code, "")

    return _ANSI_RE.sub(_replace, text)


class TUIOutputTarget(io.TextIOBase):
    """Captures sys.stdout writes and routes to ChatOutput with Rich markup."""

    def __init__(self, app: "ChatTUI", output: "ChatOutput") -> None:
        super().__init__()
        self._app = app
        self._output = output
        self._buffer: str = ""

    # ── io.TextIOBase interface ──────────────────────────────────────

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return "utf-8"

    def isatty(self) -> bool:
        """Return True so pipeline code emits colour codes."""
        return True

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        """Buffer text until newline, then flush completed lines to widget."""
        if not text:
            return 0

        length = len(text)
        self._buffer += text

        # Flush all complete lines
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            rich_line = _ansi_to_rich(line)
            self._app.call_from_thread(self._output.write, rich_line)

        return length

    def flush(self) -> None:
        """Flush any remaining buffer content to the widget."""
        if self._buffer:
            rich_line = _ansi_to_rich(self._buffer)
            self._app.call_from_thread(self._output.write, rich_line)
            self._buffer = ""
