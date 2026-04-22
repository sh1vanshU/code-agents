"""Multi-line input area with history support."""

import logging
from collections import deque

from textual.events import Key
from textual.message import Message
from textual.widgets import TextArea

logger = logging.getLogger("code_agents.chat.tui.widgets.input_area")


class ChatInput(TextArea):
    """Multi-line input with submit-on-Enter and command history."""

    class Submitted(Message):
        """Posted when the user presses Enter to submit input."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._history: deque[str] = deque(maxlen=500)
        self._history_index: int = -1
        self._saved_text: str = ""

    def on_key(self, event: Key) -> None:
        """Handle Enter (submit), Shift+Enter (newline), Up/Down (history)."""
        if event.key == "enter":
            # Submit the current text
            event.prevent_default()
            text = self.text.strip()
            if text:
                self._history.appendleft(text)
            self._history_index = -1
            self._saved_text = ""
            self.post_message(self.Submitted(text))
            self.clear()

        elif event.key == "up":
            # Cycle history only when on the first line and text is single-line
            if "\n" not in self.text and self._history:
                event.prevent_default()
                if self._history_index == -1:
                    self._saved_text = self.text
                if self._history_index < len(self._history) - 1:
                    self._history_index += 1
                    self.clear()
                    self.insert(self._history[self._history_index])

        elif event.key == "down":
            if "\n" not in self.text and self._history_index >= 0:
                event.prevent_default()
                self._history_index -= 1
                self.clear()
                if self._history_index == -1:
                    self.insert(self._saved_text)
                else:
                    self.insert(self._history[self._history_index])
