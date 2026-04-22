"""Tests for the redesigned Textual TUI package (code_agents.chat.tui)."""

import unittest
from unittest.mock import MagicMock, patch


class TestTUIImports(unittest.TestCase):
    """Verify all TUI components are importable."""

    def test_run_chat_tui_importable(self):
        from code_agents.chat.tui import run_chat_tui
        assert callable(run_chat_tui)

    def test_app_importable(self):
        from code_agents.chat.tui.app import ChatTUI
        assert ChatTUI is not None

    def test_widgets_importable(self):
        from code_agents.chat.tui.widgets import (
            ChatOutput, ChatInput, StatusBar,
            ThinkingIndicator, CommandApproval, QuestionnaireWidget,
        )
        for cls in (ChatOutput, ChatInput, StatusBar, ThinkingIndicator, CommandApproval, QuestionnaireWidget):
            assert cls is not None

    def test_proxy_importable(self):
        from code_agents.chat.tui.proxy import TUIOutputTarget
        assert TUIOutputTarget is not None

    def test_bridge_importable(self):
        from code_agents.chat.tui.bridge import TUIBridge
        assert TUIBridge is not None

    def test_css_importable(self):
        from code_agents.chat.tui.css import CHAT_TUI_CSS
        assert "chat-output" in CHAT_TUI_CSS
        assert "status-bar" in CHAT_TUI_CSS

    def test_backward_compat_shim(self):
        """Old chat_tui.py should still export run_chat_tui."""
        from code_agents.chat.chat_tui import run_chat_tui as old_import
        from code_agents.chat.tui import run_chat_tui as new_import
        # Both should be callable (old one is the original monolithic version)
        assert callable(old_import)
        assert callable(new_import)


class TestProxyANSIConversion(unittest.TestCase):
    """Test ANSI → Rich markup conversion in TUIOutputTarget."""

    def test_ansi_to_rich_basic(self):
        from code_agents.chat.tui.proxy import TUIOutputTarget
        proxy = TUIOutputTarget.__new__(TUIOutputTarget)
        proxy._app = MagicMock()
        proxy._output = MagicMock()
        proxy._buffer = ""
        proxy._open_tags = []

        # Test the conversion function
        from code_agents.chat.tui.proxy import _ansi_to_rich
        result = _ansi_to_rich("\033[32mgreen text\033[0m")
        assert "[green]" in result
        assert "green text" in result

    def test_ansi_strips_unknown(self):
        from code_agents.chat.tui.proxy import _ansi_to_rich
        result = _ansi_to_rich("\033[999mweird\033[0m")
        assert "weird" in result

    def test_isatty(self):
        from code_agents.chat.tui.proxy import TUIOutputTarget
        proxy = TUIOutputTarget.__new__(TUIOutputTarget)
        proxy._app = MagicMock()
        proxy._output = MagicMock()
        proxy._buffer = ""
        proxy._open_tags = []
        assert proxy.isatty() is True


class TestStatusBarRender(unittest.TestCase):
    """Test StatusBar class structure."""

    def test_has_reactive_attributes(self):
        from code_agents.chat.tui.widgets.status_bar import StatusBar
        # Verify reactives are defined at class level
        assert hasattr(StatusBar, 'mode')
        assert hasattr(StatusBar, 'agent_busy')
        assert hasattr(StatusBar, 'thinking_label')

    def test_render_method_exists(self):
        from code_agents.chat.tui.widgets.status_bar import StatusBar
        assert hasattr(StatusBar, 'render')
        assert callable(StatusBar.render)


class TestChatInputHistory(unittest.TestCase):
    """Test ChatInput history mechanism."""

    def test_history_deque_exists(self):
        from code_agents.chat.tui.widgets.input_area import ChatInput
        # Verify the class has the right message type
        assert hasattr(ChatInput, 'Submitted')

    def test_submitted_message(self):
        from code_agents.chat.tui.widgets.input_area import ChatInput
        msg = ChatInput.Submitted("test input")
        assert msg.value == "test input"


class TestCommandApproval(unittest.TestCase):
    """Test CommandApproval widget."""

    def test_decided_message(self):
        from code_agents.chat.tui.widgets.command_approval import CommandApproval
        msg = CommandApproval.Decided(0, "yes")
        assert msg.index == 0
        assert msg.choice == "yes"

    def test_constructor(self):
        from code_agents.chat.tui.widgets.command_approval import CommandApproval
        widget = CommandApproval("ls -la", ["Yes", "No"], default=0)
        assert widget.command == "ls -la"
        assert widget.options == ["Yes", "No"]


class TestQuestionnaireWidget(unittest.TestCase):
    """Test QuestionnaireWidget."""

    def test_completed_message(self):
        from code_agents.chat.tui.widgets.questionnaire import QuestionnaireWidget
        answers = [{"question": "Q1", "answer": "A1", "option_idx": 0}]
        msg = QuestionnaireWidget.Completed(answers)
        assert msg.answers == answers

    def test_constructor(self):
        from code_agents.chat.tui.widgets.questionnaire import QuestionnaireWidget
        qs = [{"question": "Pick one", "options": ["A", "B"]}]
        widget = QuestionnaireWidget(qs)
        assert widget.questions == qs


class TestChatTUIApp(unittest.TestCase):
    """Test ChatTUI app construction."""

    def test_app_creation(self):
        from code_agents.chat.tui.app import ChatTUI
        state = {"agent": "auto-pilot", "repo_path": "/tmp/test"}
        app = ChatTUI(
            state=state,
            url="http://localhost:8000",
            cwd="/tmp/test",
            nickname="test",
            agent_name="auto-pilot",
        )
        assert app.agent_name == "auto-pilot"
        assert app.chat_url == "http://localhost:8000"
        assert app._agent_busy is False
        assert app._mode == "chat"

    def test_mode_list(self):
        from code_agents.chat.tui.app import ChatTUI
        state = {"agent": "auto-pilot"}
        app = ChatTUI(state=state, url="", cwd="/tmp", nickname="test")
        assert app._modes == ["chat", "plan", "edit"]


if __name__ == "__main__":
    unittest.main()
