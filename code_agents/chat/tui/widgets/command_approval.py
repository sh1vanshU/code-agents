"""Inline command approval widget for the TUI.

Replaces the legacy _tab_selector for command execution prompts.
Presents the command in a highlighted box with action buttons.
"""

import logging

from textual.widgets import Static, Button
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual import on

logger = logging.getLogger("code_agents.chat.tui.widgets.command_approval")


class CommandApproval(Vertical):
    """Inline widget that asks the user to approve a shell command."""

    DEFAULT_CSS = """
    CommandApproval {
        height: auto;
        margin: 1 0;
        padding: 0 1;
    }

    CommandApproval .command-box {
        border: solid red;
        padding: 0 1;
        margin-bottom: 1;
        height: auto;
    }

    CommandApproval .button-row {
        height: auto;
        layout: horizontal;
    }

    CommandApproval .button-row Button {
        margin-right: 1;
        min-width: 12;
    }
    """

    class Decided(Message):
        """Posted when the user selects an option."""

        def __init__(self, index: int, choice: str) -> None:
            super().__init__()
            self.index = index
            self.choice = choice

    def __init__(
        self,
        command: str,
        options: list[str] | None = None,
        default: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.command = command
        self.options = options or ["Yes", "Yes & Save", "Edit", "No"]
        self.default = default

    def compose(self):
        yield Static(
            f"[bold]$ [cyan]{self.command}[/cyan][/bold]",
            classes="command-box",
        )
        with Horizontal(classes="button-row"):
            for idx, label in enumerate(self.options):
                variant = "primary" if idx == self.default else "default"
                yield Button(label, id=f"opt-{idx}", variant=variant)

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Resolve which button was clicked and post the decision."""
        button_id = event.button.id or ""
        if button_id.startswith("opt-"):
            idx = int(button_id.split("-", 1)[1])
        else:
            idx = 0
        choice = self.options[idx] if idx < len(self.options) else self.options[0]
        self.post_message(self.Decided(index=idx, choice=choice))
        self.remove()

    def key_enter(self) -> None:
        """Press Enter to select the currently focused button."""
        focused = self.app.focused
        if isinstance(focused, Button) and focused.id and focused.id.startswith("opt-"):
            focused.press()

    def key_left(self) -> None:
        """Move focus to the previous button."""
        self.screen.focus_previous()

    def key_right(self) -> None:
        """Move focus to the next button."""
        self.screen.focus_next()
