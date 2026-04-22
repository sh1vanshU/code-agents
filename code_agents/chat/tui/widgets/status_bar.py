"""Contextual footer status bar for the TUI."""

import logging

from textual.reactive import reactive
from textual.widgets import Static

logger = logging.getLogger("code_agents.chat.tui.widgets.status_bar")


class StatusBar(Static):
    """Footer bar showing current mode, agent status, and key hints."""

    mode: reactive[str] = reactive("chat")
    agent_busy: reactive[bool] = reactive(False)
    thinking_label: reactive[str] = reactive("")

    def render(self) -> str:
        """Return Rich-formatted status string."""
        mode_display = f"[bold]{self.mode.capitalize()}[/bold]"

        if self.agent_busy:
            label = self.thinking_label or "Thinking..."
            return (
                f" {mode_display} │ "
                f"[yellow]⏳ {label}[/yellow] │ "
                f"[dim]esc interrupt[/dim] │ "
                f"[dim]⇧tab mode[/dim]"
            )

        return (
            f" {mode_display} │ "
            f"Ready │ "
            f"[dim]esc quit[/dim] │ "
            f"[dim]⇧tab mode[/dim]"
        )
