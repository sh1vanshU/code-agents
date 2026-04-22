"""Scrollable output area with semantic write methods and auto-scroll."""

import logging

from textual.widgets import RichLog

logger = logging.getLogger("code_agents.chat.tui.widgets.output_log")


class ChatOutput(RichLog):
    """Scrollable output area with semantic write methods and auto-scroll."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            id="chat-output",
            wrap=True,
            markup=True,
            highlight=True,
            auto_scroll=True,
            **kwargs,
        )

    def write_user(self, text: str) -> None:
        """Write a user message with bold prompt indicator."""
        self.write(f"[bold]❯ {text}[/bold]")

    def write_assistant(self, text: str) -> None:
        """Write an assistant message as-is."""
        self.write(text)

    def write_tool_call(self, text: str) -> None:
        """Write a tool call in dim style."""
        self.write(f"[dim]{text}[/dim]")

    def write_thinking(self, text: str) -> None:
        """Write a thinking indicator in yellow."""
        self.write(f"[yellow]* {text}[/yellow]")

    def write_error(self, text: str) -> None:
        """Write an error message in red."""
        self.write(f"[red]✗ {text}[/red]")

    def write_success(self, text: str) -> None:
        """Write a success message in green."""
        self.write(f"[green]✓ {text}[/green]")

    def add_turn_separator(self) -> None:
        """Write a horizontal rule to separate conversation turns."""
        self.write(f"[dim]{'─' * 50}[/dim]")
