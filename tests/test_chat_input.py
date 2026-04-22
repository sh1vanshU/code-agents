"""Tests for chat_input.py — input handling, model/backend loading, session creation."""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest


class TestLoadAvailableModels:
    """Test _load_available_models discovers models from env and defaults."""

    def test_default_models_included(self):
        from code_agents.chat.chat_input import _load_available_models
        models = _load_available_models()
        assert "opus" in models
        assert "sonnet" in models
        assert "haiku" in models
        assert "claude-opus-4-6" in models
        assert "claude-sonnet-4-6" in models
        assert "Composer 2 Fast" in models

    def test_env_model_picked_up(self):
        from code_agents.chat.chat_input import _load_available_models
        with patch.dict(os.environ, {"CODE_AGENTS_MODEL_CODE_WRITER": "gpt-4o-test"}):
            models = _load_available_models()
            assert "gpt-4o-test" in models

    def test_global_model_from_env(self):
        from code_agents.chat.chat_input import _load_available_models
        with patch.dict(os.environ, {"CODE_AGENTS_MODEL": "custom-model-xyz"}):
            models = _load_available_models()
            assert "custom-model-xyz" in models

    def test_cli_model_from_env(self):
        from code_agents.chat.chat_input import _load_available_models
        with patch.dict(os.environ, {"CODE_AGENTS_CLAUDE_CLI_MODEL": "claude-haiku-test"}):
            models = _load_available_models()
            assert "claude-haiku-test" in models

    def test_no_duplicates_for_existing(self):
        from code_agents.chat.chat_input import _load_available_models
        with patch.dict(os.environ, {"CODE_AGENTS_MODEL": "opus"}):
            models = _load_available_models()
            assert models.count("opus") == 1


class TestLoadAvailableBackends:
    """Test _load_available_backends discovers backends."""

    def test_default_backends(self):
        from code_agents.chat.chat_input import _load_available_backends
        backends = _load_available_backends()
        assert "cursor" in backends
        assert "claude" in backends
        assert "claude-cli" in backends

    def test_custom_backend_from_env(self):
        from code_agents.chat.chat_input import _load_available_backends
        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND_CODE_WRITER": "custom-backend"}):
            backends = _load_available_backends()
            assert "custom-backend" in backends


class TestCreateSession:
    """Test create_session with and without prompt_toolkit."""

    def test_returns_none_without_prompt_toolkit(self):
        from code_agents.chat import chat_input
        orig = chat_input._HAS_PT
        try:
            chat_input._HAS_PT = False
            result = chat_input.create_session()
            assert result is None
        finally:
            chat_input._HAS_PT = orig

    def test_creates_session_with_prompt_toolkit(self):
        from code_agents.chat import chat_input
        if not chat_input._HAS_PT:
            pytest.skip("prompt_toolkit not available")
        session = chat_input.create_session(
            slash_commands=["/help", "/quit", "/model", "/backend", "/agent", "/blame"],
            agent_names=["code-writer", "code-tester"],
        )
        assert session is not None

    def test_creates_session_with_history(self, tmp_path):
        from code_agents.chat import chat_input
        if not chat_input._HAS_PT:
            pytest.skip("prompt_toolkit not available")
        history_file = str(tmp_path / "test_history")
        session = chat_input.create_session(
            history_file=history_file,
            slash_commands=["/help"],
            agent_names=["code-writer"],
        )
        assert session is not None

    def test_creates_session_empty_args(self):
        from code_agents.chat import chat_input
        if not chat_input._HAS_PT:
            pytest.skip("prompt_toolkit not available")
        session = chat_input.create_session()
        assert session is not None


class TestPromptInput:
    """Test prompt_input fallback path."""

    def test_fallback_to_input_without_session(self):
        from code_agents.chat.chat_input import prompt_input
        with patch("builtins.input", return_value="hello world"):
            result = prompt_input(None, nickname="tester")
            assert result == "hello world"

    def test_fallback_strips_whitespace(self):
        from code_agents.chat.chat_input import prompt_input
        with patch("builtins.input", return_value="  spaced  "):
            result = prompt_input(None)
            assert result == "spaced"

    def test_prompt_with_role(self):
        from code_agents.chat.chat_input import prompt_input
        with patch("builtins.input", return_value="test"):
            result = prompt_input(None, nickname="dev", role="Senior Engineer")
            assert result == "test"


class TestChatModeCycling:
    """Test Shift+Tab mode cycling: Chat -> Plan -> Edit."""

    def setup_method(self):
        """Reset mode to default before each test."""
        from code_agents.chat import chat_input
        chat_input._current_mode_index = 0

    def test_default_mode_is_chat(self):
        from code_agents.chat.chat_input import get_current_mode
        assert get_current_mode() == "chat"

    def test_cycle_chat_to_plan(self):
        from code_agents.chat.chat_input import cycle_mode, get_current_mode
        result = cycle_mode()
        assert result == "plan"
        assert get_current_mode() == "plan"

    def test_cycle_plan_to_edit(self):
        from code_agents.chat.chat_input import cycle_mode, get_current_mode
        cycle_mode()  # chat -> plan
        result = cycle_mode()  # plan -> edit
        assert result == "edit"
        assert get_current_mode() == "edit"

    def test_cycle_edit_wraps_to_chat(self):
        from code_agents.chat.chat_input import cycle_mode, get_current_mode
        cycle_mode()  # chat -> plan
        cycle_mode()  # plan -> edit
        result = cycle_mode()  # edit -> chat
        assert result == "chat"
        assert get_current_mode() == "chat"

    def test_set_mode_plan(self):
        from code_agents.chat.chat_input import set_mode, get_current_mode
        result = set_mode("plan")
        assert result == "plan"
        assert get_current_mode() == "plan"

    def test_set_mode_edit(self):
        from code_agents.chat.chat_input import set_mode, get_current_mode
        result = set_mode("edit")
        assert result == "edit"
        assert get_current_mode() == "edit"

    def test_set_mode_invalid_stays_current(self):
        from code_agents.chat.chat_input import set_mode, get_current_mode
        set_mode("chat")
        result = set_mode("nonexistent")
        assert result == "chat"  # stays on current

    def test_set_mode_case_insensitive(self):
        from code_agents.chat.chat_input import set_mode, get_current_mode
        result = set_mode("PLAN")
        assert result == "plan"

    def test_toolbar_shows_chat_mode(self):
        from code_agents.chat.chat_input import _get_toolbar, set_mode
        set_mode("chat")
        toolbar = _get_toolbar()
        toolbar_str = str(toolbar.value) if hasattr(toolbar, 'value') else str(toolbar)
        assert "Chat" in toolbar_str
        assert "shift+tab" in toolbar_str

    def test_toolbar_shows_plan_mode(self):
        from code_agents.chat.chat_input import _get_toolbar, set_mode
        set_mode("plan")
        toolbar = _get_toolbar()
        toolbar_str = str(toolbar.value) if hasattr(toolbar, 'value') else str(toolbar)
        assert "Plan mode" in toolbar_str

    def test_toolbar_shows_edit_mode(self):
        from code_agents.chat.chat_input import _get_toolbar, set_mode
        set_mode("edit")
        toolbar = _get_toolbar()
        toolbar_str = str(toolbar.value) if hasattr(toolbar, 'value') else str(toolbar)
        assert "Accept edits on" in toolbar_str

    def test_chat_modes_list(self):
        from code_agents.chat.chat_input import _CHAT_MODES
        assert _CHAT_MODES == ["chat", "plan", "edit"]

    def test_is_edit_mode_false_in_chat(self):
        from code_agents.chat.chat_input import set_mode, is_edit_mode
        set_mode("chat")
        assert is_edit_mode() is False

    def test_is_edit_mode_true_in_edit(self):
        from code_agents.chat.chat_input import set_mode, is_edit_mode
        set_mode("edit")
        assert is_edit_mode() is True

    def test_is_edit_mode_false_in_plan(self):
        from code_agents.chat.chat_input import set_mode, is_edit_mode
        set_mode("plan")
        assert is_edit_mode() is False

    def test_is_plan_mode_active(self):
        from code_agents.chat.chat_input import set_mode, is_plan_mode_active
        set_mode("plan")
        assert is_plan_mode_active() is True
        set_mode("chat")
        assert is_plan_mode_active() is False

    def test_toolbar_edit_shows_esc_hint(self):
        from code_agents.chat.chat_input import _get_toolbar, set_mode
        set_mode("edit")
        toolbar = _get_toolbar()
        toolbar_str = str(toolbar.value) if hasattr(toolbar, 'value') else str(toolbar)
        assert "esc to interrupt" in toolbar_str

    def test_toolbar_chat_no_esc_hint(self):
        from code_agents.chat.chat_input import _get_toolbar, set_mode
        set_mode("chat")
        toolbar = _get_toolbar()
        toolbar_str = str(toolbar.value) if hasattr(toolbar, 'value') else str(toolbar)
        assert "esc to interrupt" not in toolbar_str


class TestToolbarStyleConsistency:
    """Test that bottom toolbar style uses dark theme (not white) in all code paths."""

    _TOOLBAR_STYLE_KEYS = ("bottom-toolbar", "bottom-toolbar.text", "toolbar")
    _EXPECTED_BG = "bg:default"

    def _style_dict_from_session(self, session):
        """Extract the style_rules list from a PromptSession's style."""
        # PTStyle stores rules as a list of (selector, style_str) tuples
        rules = session.style.style_rules if hasattr(session.style, 'style_rules') else []
        return {sel: style_str for sel, style_str in rules}

    def test_session_style_has_dark_toolbar(self):
        """create_session must define dark-bg toolbar styles."""
        from code_agents.chat import chat_input
        if not chat_input._HAS_PT:
            pytest.skip("prompt_toolkit not available")
        session = chat_input.create_session()
        rules = self._style_dict_from_session(session)
        for key in self._TOOLBAR_STYLE_KEYS:
            assert key in rules, f"Missing style rule '{key}' in session style"
            assert self._EXPECTED_BG in rules[key], (
                f"Session style '{key}' should use {self._EXPECTED_BG}, got: {rules[key]}"
            )

    def test_prompt_style_has_dark_toolbar(self):
        """prompt_input's per-call style must also include dark-bg toolbar rules.

        This is the fix for the white-background toolbar bug — the per-call
        style passed to session.prompt() was overriding the session-level style
        and losing the toolbar entries.
        """
        from code_agents.chat import chat_input
        if not chat_input._HAS_PT:
            pytest.skip("prompt_toolkit not available")
        # Create a real session then intercept the style passed to session.prompt()
        session = chat_input.create_session()
        captured_style = {}

        _orig_prompt = session.prompt

        def _spy_prompt(*args, **kwargs):
            captured_style['style'] = kwargs.get('style')
            raise EOFError  # exit cleanly without waiting for input

        session.prompt = _spy_prompt
        # prompt_input should trigger our spy (EOFError → returns "")
        chat_input.prompt_input(session, nickname="test")
        style_obj = captured_style.get('style')
        assert style_obj is not None, "prompt_input did not pass a style to session.prompt()"
        rules = {sel: s for sel, s in style_obj.style_rules}
        for key in self._TOOLBAR_STYLE_KEYS:
            assert key in rules, (
                f"Prompt-level style missing '{key}' — toolbar will fall back to white bg"
            )
            assert self._EXPECTED_BG in rules[key], (
                f"Prompt-level style '{key}' should use {self._EXPECTED_BG}, got: {rules[key]}"
            )

    def test_session_and_prompt_toolbar_styles_match(self):
        """The toolbar style in create_session and prompt_input must be identical."""
        from code_agents.chat import chat_input
        if not chat_input._HAS_PT:
            pytest.skip("prompt_toolkit not available")
        session = chat_input.create_session()
        session_rules = self._style_dict_from_session(session)

        captured_style = {}
        _orig = session.prompt

        def _spy(*args, **kwargs):
            captured_style['style'] = kwargs.get('style')
            raise EOFError

        session.prompt = _spy
        chat_input.prompt_input(session, nickname="test")
        prompt_rules = {sel: s for sel, s in captured_style['style'].style_rules}

        for key in self._TOOLBAR_STYLE_KEYS:
            assert session_rules.get(key) == prompt_rules.get(key), (
                f"Style mismatch for '{key}': session={session_rules.get(key)!r} "
                f"vs prompt={prompt_rules.get(key)!r}"
            )

    def test_toolbar_style_no_reverse(self):
        """Toolbar style must include noreverse to prevent color inversion."""
        from code_agents.chat import chat_input
        if not chat_input._HAS_PT:
            pytest.skip("prompt_toolkit not available")
        session = chat_input.create_session()
        rules = self._style_dict_from_session(session)
        for key in self._TOOLBAR_STYLE_KEYS:
            assert "noreverse" in rules.get(key, ""), (
                f"Style '{key}' must include 'noreverse' to prevent white-bg inversion"
            )


class TestStaticToolbar:
    """Test persistent static toolbar shown while agent is working."""

    def setup_method(self):
        from code_agents.chat import chat_input
        chat_input._current_mode_index = 0
        chat_input._static_bar_shown = False

    def test_show_static_toolbar_sets_flag(self, capsys):
        from code_agents.chat.chat_input import show_static_toolbar, _static_bar_shown
        from code_agents.chat import chat_input
        show_static_toolbar()
        assert chat_input._static_bar_shown is True
        output = capsys.readouterr().out
        assert "Chat" in output
        assert "shift+tab" in output

    def test_show_static_toolbar_edit_mode(self, capsys):
        from code_agents.chat.chat_input import show_static_toolbar, set_mode
        from code_agents.chat import chat_input
        set_mode("edit")
        show_static_toolbar()
        output = capsys.readouterr().out
        assert "Accept edits" in output

    def test_show_static_toolbar_plan_mode(self, capsys):
        from code_agents.chat.chat_input import show_static_toolbar, set_mode
        from code_agents.chat import chat_input
        set_mode("plan")
        show_static_toolbar()
        output = capsys.readouterr().out
        assert "Plan mode" in output

    def test_clear_static_toolbar_resets_flag(self, capsys):
        from code_agents.chat.chat_input import show_static_toolbar, clear_static_toolbar
        from code_agents.chat import chat_input
        show_static_toolbar()
        capsys.readouterr()  # drain
        clear_static_toolbar()
        assert chat_input._static_bar_shown is False

    def test_clear_static_toolbar_noop_when_not_shown(self, capsys):
        from code_agents.chat.chat_input import clear_static_toolbar
        from code_agents.chat import chat_input
        assert chat_input._static_bar_shown is False
        clear_static_toolbar()
        output = capsys.readouterr().out
        # No ANSI escape sequences should be written
        assert "\033[A" not in output

    def test_show_clear_cycle(self, capsys):
        from code_agents.chat.chat_input import show_static_toolbar, clear_static_toolbar
        from code_agents.chat import chat_input
        show_static_toolbar()
        assert chat_input._static_bar_shown is True
        clear_static_toolbar()
        assert chat_input._static_bar_shown is False
        # Can show again
        show_static_toolbar()
        assert chat_input._static_bar_shown is True


class TestMessageQueue:
    """Test thread-safe message queue."""

    def test_enqueue_dequeue(self):
        from code_agents.chat.chat_input import MessageQueue
        mq = MessageQueue()
        pos = mq.enqueue("hello")
        assert pos == 1
        assert mq.size == 1
        msg = mq.dequeue()
        assert msg == "hello"
        assert mq.is_empty

    def test_fifo_order(self):
        from code_agents.chat.chat_input import MessageQueue
        mq = MessageQueue()
        mq.enqueue("first")
        mq.enqueue("second")
        mq.enqueue("third")
        assert mq.size == 3
        assert mq.dequeue() == "first"
        assert mq.dequeue() == "second"
        assert mq.dequeue() == "third"
        assert mq.dequeue() is None

    def test_peek(self):
        from code_agents.chat.chat_input import MessageQueue
        mq = MessageQueue()
        assert mq.peek() is None
        mq.enqueue("msg")
        assert mq.peek() == "msg"
        assert mq.size == 1  # peek doesn't remove

    def test_clear(self):
        from code_agents.chat.chat_input import MessageQueue
        mq = MessageQueue()
        mq.enqueue("a")
        mq.enqueue("b")
        count = mq.clear()
        assert count == 2
        assert mq.is_empty

    def test_agent_busy_state(self):
        from code_agents.chat.chat_input import MessageQueue
        mq = MessageQueue()
        assert mq.agent_is_busy is False
        mq.set_agent_busy()
        assert mq.agent_is_busy is True
        mq.set_agent_free()
        assert mq.agent_is_busy is False

    def test_list_queued(self):
        from code_agents.chat.chat_input import MessageQueue
        mq = MessageQueue()
        mq.enqueue("a")
        mq.enqueue("b")
        assert mq.list_queued() == ["a", "b"]

    def test_dequeue_empty(self):
        from code_agents.chat.chat_input import MessageQueue
        mq = MessageQueue()
        assert mq.dequeue() is None

    def test_singleton(self):
        from code_agents.chat.chat_input import get_message_queue
        q1 = get_message_queue()
        q2 = get_message_queue()
        assert q1 is q2


# ---------------------------------------------------------------------------
# Background input reader
# ---------------------------------------------------------------------------

class TestBackgroundInput:
    """Tests for start_background_input / stop_background_input."""

    def test_start_sets_thread(self):
        from code_agents.chat.chat_input import (
            start_background_input, stop_background_input, _bg_input_thread,
        )
        import code_agents.chat.chat_input as _mod

        with patch("code_agents.chat.chat_input.threading.Thread") as mock_thread:
            mock_inst = MagicMock()
            mock_thread.return_value = mock_inst
            mock_inst.is_alive.return_value = False
            start_background_input("tester")
            mock_thread.assert_called_once()
            mock_inst.start.assert_called_once()
            stop_background_input()

    def test_stop_sets_event(self):
        from code_agents.chat.chat_input import (
            start_background_input, stop_background_input, _bg_input_stop,
        )
        with patch("code_agents.chat.chat_input.threading.Thread") as mock_thread:
            mock_inst = MagicMock()
            mock_thread.return_value = mock_inst
            mock_inst.is_alive.return_value = False
            start_background_input("tester")
            stop_background_input()
            assert _bg_input_stop.is_set()

    def test_does_not_start_twice(self):
        from code_agents.chat.chat_input import start_background_input, stop_background_input
        import code_agents.chat.chat_input as _mod

        with patch("code_agents.chat.chat_input.threading.Thread") as mock_thread:
            mock_inst = MagicMock()
            mock_thread.return_value = mock_inst
            mock_inst.is_alive.return_value = True
            _mod._bg_input_thread = mock_inst
            start_background_input("tester")
            # Should NOT create a new thread
            mock_thread.assert_not_called()
            stop_background_input()


# ---------------------------------------------------------------------------
# Terminal layout
# ---------------------------------------------------------------------------

class TestTerminalLayout:
    """Tests for terminal_layout scroll region management."""

    def test_supports_layout_requires_tty(self):
        from code_agents.chat.terminal_layout import supports_layout
        with patch("code_agents.chat.terminal_layout.sys.stdout") as mock_out:
            mock_out.isatty.return_value = False
            assert supports_layout() is False

    def test_supports_layout_rejects_dumb_term(self):
        from code_agents.chat.terminal_layout import supports_layout
        with patch("code_agents.chat.terminal_layout.sys.stdout") as mock_out, \
             patch.dict(os.environ, {"TERM": "dumb"}):
            mock_out.isatty.return_value = True
            assert supports_layout() is False

    def test_enter_exit_region(self):
        from code_agents.chat.terminal_layout import (
            enter_input_region, exit_input_region, is_layout_active,
        )
        import code_agents.chat.terminal_layout as _mod

        with patch.object(_mod, "supports_layout", return_value=True), \
             patch.object(_mod.sys.stdout, "write"), \
             patch.object(_mod.sys.stdout, "flush"), \
             patch.object(_mod, "get_terminal_size", return_value=(120, 40)):
            _mod._layout_active = False
            enter_input_region()
            assert is_layout_active() is True
            exit_input_region()
            assert is_layout_active() is False

    def test_draw_input_bar_shows_queue(self):
        import code_agents.chat.terminal_layout as _mod
        writes = []
        with patch.object(_mod.sys.stdout, "write", side_effect=writes.append), \
             patch.object(_mod.sys.stdout, "flush"), \
             patch.object(_mod, "get_terminal_size", return_value=(120, 40)):
            _mod._layout_active = True
            try:
                _mod.draw_input_bar(nickname="dev", queue_size=3)
                output = "".join(writes)
                assert "dev" in output
                assert "3 queued" in output
            finally:
                _mod._layout_active = False
