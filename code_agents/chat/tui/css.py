"""Textual CSS for the Code Agents TUI."""

import logging

logger = logging.getLogger("code_agents.chat.tui.css")

CHAT_TUI_CSS = """
Screen {
    layout: vertical;
}

#chat-output {
    height: 1fr;
    min-height: 10;
    scrollbar-size: 1 1;
    padding: 0 1;
    background: $surface;
    overflow-y: auto;
}

#input-container {
    height: auto;
    max-height: 30%;
    padding: 0 1;
    border-top: heavy $primary;
}

#chat-input {
    height: auto;
    min-height: 1;
    max-height: 6;
    background: $surface;
}

#status-bar {
    height: 1;
    dock: bottom;
    background: $surface-darken-1;
    color: $text-muted;
    padding: 0 1;
}

.turn-separator {
    color: $text-muted;
    height: 1;
}

ThinkingIndicator {
    height: 1;
    color: $warning;
}

CommandApproval {
    height: auto;
    padding: 0 1;
    margin: 1 0;
    border: round $error;
}

CommandApproval .cmd-box {
    color: $accent;
    padding: 0 1;
}

CommandApproval Button {
    margin: 0 1 0 0;
    min-width: 8;
}

QuestionnaireWidget {
    height: auto;
    padding: 1;
    margin: 1 0;
    border: round $primary;
}

QuestionnaireWidget Button {
    margin: 0 1 0 0;
}
"""
