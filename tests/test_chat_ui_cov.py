"""Coverage tests for chat_ui.py — covers missing lines from coverage_run.json.

Missing lines: 29,33-46,173-175,211-212,448,450,471-534,548-549
"""

from __future__ import annotations

import os
import sys
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Lines 29, 33-46: light theme color functions
# ---------------------------------------------------------------------------


class TestLightTheme:
    """Test that light theme color functions are callable and return strings."""

    def test_light_theme_colors(self):
        """Lines 33-46: light theme defines all color functions."""
        # We need to reimport the module with THEME=light
        # Instead, just verify the functions exist and work by patching
        import importlib
        import code_agents.chat.chat_ui as ui_module

        # Save originals
        orig_theme = os.environ.get("CODE_AGENTS_THEME", "")
        try:
            os.environ["CODE_AGENTS_THEME"] = "light"
            importlib.reload(ui_module)

            # Verify all functions work
            assert isinstance(ui_module.bold("test"), str)
            assert isinstance(ui_module.green("test"), str)
            assert isinstance(ui_module.yellow("test"), str)
            assert isinstance(ui_module.red("test"), str)
            assert isinstance(ui_module.cyan("test"), str)
            assert isinstance(ui_module.dim("test"), str)
            assert isinstance(ui_module.magenta("test"), str)
            assert isinstance(ui_module.blue("test"), str)
            assert isinstance(ui_module.white("test"), str)
            assert isinstance(ui_module.bright_red("test"), str)
            assert isinstance(ui_module.bright_green("test"), str)
            assert isinstance(ui_module.bright_yellow("test"), str)
            assert isinstance(ui_module.bright_cyan("test"), str)
            assert isinstance(ui_module.bright_magenta("test"), str)
        finally:
            if orig_theme:
                os.environ["CODE_AGENTS_THEME"] = orig_theme
            else:
                os.environ.pop("CODE_AGENTS_THEME", None)
            importlib.reload(ui_module)

    def test_minimal_theme(self):
        """Line 29: minimal theme disables all colors."""
        import importlib
        import code_agents.chat.chat_ui as ui_module

        orig_theme = os.environ.get("CODE_AGENTS_THEME", "")
        try:
            os.environ["CODE_AGENTS_THEME"] = "minimal"
            importlib.reload(ui_module)

            # In minimal mode, _USE_COLOR should be False
            assert ui_module._USE_COLOR is False
            # Colors should be passthrough
            assert ui_module.bold("hello") == "hello"
        finally:
            if orig_theme:
                os.environ["CODE_AGENTS_THEME"] = orig_theme
            else:
                os.environ.pop("CODE_AGENTS_THEME", None)
            importlib.reload(ui_module)


# ---------------------------------------------------------------------------
# Lines 173-175, 211-212: _render_markdown — table end-of-input handling
# ---------------------------------------------------------------------------


class TestRenderMarkdownTableEdge:
    def test_table_at_end_of_input(self):
        """Lines 173-175: table at end of input (no trailing non-table line)."""
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            text = "Some text\n| Col1 | Col2 |\n| --- | --- |\n| a | b |"
            result = _render_markdown(text)
            assert "Col1" in result
            assert "a" in result

    def test_wide_table_columns_scaled(self):
        """Lines 211-212: table columns scaled when total > terminal width."""
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            # Create a very wide table
            cols = "|" + "|".join([f" {'x' * 30} " for _ in range(10)]) + "|"
            sep = "|" + "|".join([" --- " for _ in range(10)]) + "|"
            data = "|" + "|".join([f" {'y' * 30} " for _ in range(10)]) + "|"
            text = f"{cols}\n{sep}\n{data}"
            result = _render_markdown(text)
            assert "x" in result


# ---------------------------------------------------------------------------
# Lines 448, 450, 471-534: _tab_selector — raw tty path
# ---------------------------------------------------------------------------


class TestTabSelectorPanel:
    """Test _tab_selector with command_panel (mocked) and fallback paths."""

    def test_tab_selector_panel_selects_option(self):
        """show_panel returns selected index → correct index."""
        from code_agents.chat.chat_ui import _tab_selector

        with patch("code_agents.chat.chat_ui.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", return_value=1):
            mock_stdout.isatty = MagicMock(return_value=True)
            result = _tab_selector("Choose:", ["A", "B", "C"], default=0)
        assert result == 1

    def test_tab_selector_panel_cancelled(self):
        """show_panel returns None (cancelled) → last option index."""
        from code_agents.chat.chat_ui import _tab_selector

        with patch("code_agents.chat.chat_ui.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", return_value=None):
            mock_stdout.isatty = MagicMock(return_value=True)
            result = _tab_selector("Choose:", ["A", "B", "C"], default=0)
        assert result == 2  # last option

    def test_tab_selector_panel_default_passed(self):
        """Default option is passed to show_panel."""
        from code_agents.chat.chat_ui import _tab_selector

        with patch("code_agents.chat.chat_ui.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", return_value=1) as mock_panel:
            mock_stdout.isatty = MagicMock(return_value=True)
            _tab_selector("Choose:", ["A", "B", "C"], default=1)
        args = mock_panel.call_args[0]
        assert args[3] == 1  # default parameter

    def test_tab_selector_keyboard_interrupt_uses_fallback(self):
        """KeyboardInterrupt in panel falls through to fallback."""
        from code_agents.chat.chat_ui import _tab_selector

        with patch("code_agents.chat.chat_ui.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", side_effect=KeyboardInterrupt), \
             patch("builtins.input", return_value=""):
            mock_stdout.isatty = MagicMock(return_value=True)
            result = _tab_selector("Choose:", ["A", "B", "C"], default=0)
        assert result == 0  # fallback returns default

    def test_tab_selector_import_error_uses_fallback(self):
        """If command_panel not available, uses numbered input fallback."""
        from code_agents.chat.chat_ui import _tab_selector

        with patch("code_agents.chat.chat_ui.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", side_effect=ImportError), \
             patch("builtins.input", return_value="2"):
            mock_stdout.isatty = MagicMock(return_value=True)
            result = _tab_selector("Choose:", ["A", "B", "C"], default=0)
        assert result == 1  # selected "2" = index 1

    def test_tab_selector_fallback_tab_returns_minus2(self):
        """Fallback: typing 't' returns -2 (amend)."""
        from code_agents.chat.chat_ui import _tab_selector

        with patch("code_agents.chat.chat_ui.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", side_effect=ImportError), \
             patch("builtins.input", return_value="t"):
            mock_stdout.isatty = MagicMock(return_value=True)
            result = _tab_selector("Choose:", ["A", "B"], default=0)
        assert result == -2

    def test_tab_selector_fallback_eof_returns_last(self):
        """Fallback: EOFError returns last option."""
        from code_agents.chat.chat_ui import _tab_selector

        with patch("code_agents.chat.chat_ui.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", side_effect=ImportError), \
             patch("builtins.input", side_effect=EOFError):
            mock_stdout.isatty = MagicMock(return_value=True)
            result = _tab_selector("Choose:", ["A", "B", "C"], default=0)
        assert result == 2  # last option

    def test_tab_selector_fallback_empty_returns_default(self):
        """Fallback: empty input returns default."""
        from code_agents.chat.chat_ui import _tab_selector

        with patch("code_agents.chat.chat_ui.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", side_effect=ImportError), \
             patch("builtins.input", return_value=""):
            mock_stdout.isatty = MagicMock(return_value=True)
            result = _tab_selector("Choose:", ["A", "B"], default=0)
        assert result == 0

    def test_tab_selector_non_tty_uses_fallback(self):
        """Non-TTY skips panel, uses numbered fallback directly."""
        from code_agents.chat.chat_ui import _tab_selector

        with patch("code_agents.chat.chat_ui.sys.stdout") as mock_stdout, \
             patch("builtins.input", return_value="2"):
            mock_stdout.isatty = MagicMock(return_value=False)
            result = _tab_selector("Choose:", ["A", "B", "C"], default=0)
        assert result == 1
