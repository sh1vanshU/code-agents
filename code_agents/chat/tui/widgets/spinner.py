"""Animated thinking indicator widget with elapsed time display."""

from __future__ import annotations

import logging
import time

from textual.reactive import reactive
from textual.widgets import Static

logger = logging.getLogger("code_agents.chat.tui.widgets.spinner")


class ThinkingIndicator(Static):
    """Shows a blinking dot with elapsed time and action label."""

    action: reactive[str] = reactive("Thinking")
    target: reactive[str] = reactive("")

    def __init__(self, **kwargs) -> None:
        super().__init__("", id="thinking-indicator", **kwargs)
        self._start_time: float = 0.0
        self._frame: int = 0

    # ── Lifecycle ────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Record start time and begin the animation timer."""
        self._start_time = time.monotonic()
        self._frame = 0
        self.set_interval(0.5, self._tick)

    def _tick(self) -> None:
        """Advance animation frame and trigger re-render."""
        self._frame += 1
        self.refresh()

    # ── Rendering ────────────────────────────────────────────────────

    def render(self) -> str:
        elapsed = int(time.monotonic() - self._start_time)

        # Alternate between bright and dim blue dot
        if self._frame % 2 == 0:
            dot = "[bold blue]\u25cf[/]"
        else:
            dot = "[dim blue]\u25cf[/]"

        label = self.action
        if self.target:
            label = f"{label} {self.target}"

        return f"  {dot} {label}... {elapsed}s"
