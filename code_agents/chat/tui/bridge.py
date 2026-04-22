"""Pipeline bridge that monkey-patches interactive terminal calls for TUI compatibility."""

from __future__ import annotations

import logging
import threading
from typing import Any, TYPE_CHECKING

logger = logging.getLogger("code_agents.chat.tui.bridge")

if TYPE_CHECKING:
    from .app import ChatTUI


class TUIBridge:
    """Monkey-patches interactive terminal functions so they work inside the TUI.

    Interactive prompts (tab selectors, amend dialogs, questionnaires) block
    on the terminal in normal CLI mode. Inside the TUI these must be replaced
    with widget-based equivalents that:
      1. Post a widget to the output area via ``app.call_from_thread``.
      2. Block the worker thread with a ``threading.Event``.
      3. Resume when the widget's message handler sets the result and signals.
    """

    def __init__(self, app: "ChatTUI") -> None:
        self._app = app
        self._originals: dict[str, Any] = {}

    # ── Install / Uninstall ──────────────────────────────────────────

    def install(self) -> None:
        """Monkey-patch interactive functions for TUI compatibility."""
        import code_agents.chat.chat_ui as chat_ui
        import code_agents.chat.chat_commands as chat_commands
        import code_agents.agent_system.questionnaire as questionnaire

        # Save originals
        self._originals["chat_ui._tab_selector"] = chat_ui._tab_selector
        self._originals["chat_commands._tab_selector"] = chat_commands._tab_selector
        self._originals["chat_ui._amend_prompt"] = chat_ui._amend_prompt
        self._originals["questionnaire.ask_multiple_tabbed"] = (
            questionnaire.ask_multiple_tabbed
        )

        # Patch
        chat_ui._tab_selector = self._tui_tab_selector
        chat_commands._tab_selector = self._tui_tab_selector
        chat_ui._amend_prompt = self._tui_amend_prompt
        questionnaire.ask_multiple_tabbed = self._tui_ask_multiple_tabbed

    def uninstall(self) -> None:
        """Restore all original functions."""
        if not self._originals:
            return

        import code_agents.chat.chat_ui as chat_ui
        import code_agents.chat.chat_commands as chat_commands
        import code_agents.agent_system.questionnaire as questionnaire

        chat_ui._tab_selector = self._originals["chat_ui._tab_selector"]
        chat_commands._tab_selector = self._originals["chat_commands._tab_selector"]
        chat_ui._amend_prompt = self._originals["chat_ui._amend_prompt"]
        questionnaire.ask_multiple_tabbed = self._originals[
            "questionnaire.ask_multiple_tabbed"
        ]
        self._originals.clear()

    # ── Patched implementations ──────────────────────────────────────

    def _tui_tab_selector(
        self, prompt: str, options: list[str], default: int = 0
    ) -> int:
        """Replace terminal tab-selector with a TUI widget.

        Mounts a CommandApproval widget, blocks until the user picks an option,
        then returns the selected index.
        """
        event = threading.Event()
        result_holder: list[int] = [default]

        def _mount_widget() -> None:
            from .widgets.command_approval import CommandApproval

            widget = CommandApproval(
                prompt=prompt,
                options=options,
                default=default,
            )

            def _on_selected(index: int) -> None:
                result_holder[0] = index
                event.set()

            widget.on_selected = _on_selected
            output = self._app.query_one("#chat-output")
            output.mount(widget)

        self._app.call_from_thread(_mount_widget)
        event.wait(timeout=120)
        return result_holder[0]

    def _tui_amend_prompt(self) -> str:
        """Replace terminal amend prompt with a TUI input dialog.

        Shows a simple text input in the output area and blocks until the
        user submits or cancels.
        """
        event = threading.Event()
        result_holder: list[str] = [""]

        def _mount_input() -> None:
            from textual.widgets import Input

            inp = Input(placeholder="Amend your message...", id="amend-input")

            def _on_submit(value: str) -> None:
                result_holder[0] = value
                inp.remove()
                event.set()

            inp.on_submitted = _on_submit
            output = self._app.query_one("#chat-output")
            output.mount(inp)
            inp.focus()

        self._app.call_from_thread(_mount_input)
        event.wait(timeout=120)
        return result_holder[0]

    def _tui_ask_multiple_tabbed(
        self, questions: list[dict]
    ) -> list[dict] | None:
        """Replace terminal questionnaire with a TUI widget.

        Mounts a QuestionnaireWidget, blocks until the user completes all
        questions or cancels.
        """
        event = threading.Event()
        result_holder: list[list[dict] | None] = [None]

        def _mount_widget() -> None:
            from .widgets.questionnaire import QuestionnaireWidget

            widget = QuestionnaireWidget(questions=questions)

            def _on_complete(answers: list[dict] | None) -> None:
                result_holder[0] = answers
                event.set()

            widget.on_complete = _on_complete
            output = self._app.query_one("#chat-output")
            output.mount(widget)

        self._app.call_from_thread(_mount_widget)
        event.wait(timeout=120)
        return result_holder[0]
