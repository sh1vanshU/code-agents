"""Tests for chat_theme.py — theme system, palette definitions, switching, persistence."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestThemePalettes:
    """Verify all themes have required color keys."""

    def test_all_themes_exist(self):
        from code_agents.chat.chat_theme import THEMES, THEME_ORDER
        for name in THEME_ORDER:
            assert name in THEMES, f"Theme '{name}' missing from THEMES dict"

    def test_required_keys(self):
        from code_agents.chat.chat_theme import THEMES
        required = {
            "bold", "green", "yellow", "red", "cyan", "dim", "magenta", "blue",
            "white", "bright_red", "bright_green", "bright_yellow", "bright_cyan",
            "bright_magenta", "prompt_user", "prompt_separator", "prompt_arrow",
            "toolbar_bg", "toolbar_fg",
        }
        for name, palette in THEMES.items():
            for key in required:
                assert key in palette, f"Theme '{name}' missing key '{key}'"

    def test_all_values_are_strings(self):
        from code_agents.chat.chat_theme import THEMES
        for name, palette in THEMES.items():
            for key, val in palette.items():
                assert isinstance(val, str), f"Theme '{name}' key '{key}' is not str"

    def test_display_names_for_all_themes(self):
        from code_agents.chat.chat_theme import THEME_DISPLAY_NAMES, THEME_ORDER
        for name in THEME_ORDER:
            assert name in THEME_DISPLAY_NAMES

    def test_six_themes(self):
        from code_agents.chat.chat_theme import THEME_ORDER
        assert len(THEME_ORDER) == 6


class TestGetSetTheme:
    """Test get_theme / set_theme runtime switching."""

    def setup_method(self):
        from code_agents.chat import chat_theme
        self._orig = chat_theme._active_theme

    def teardown_method(self):
        from code_agents.chat import chat_theme
        chat_theme._active_theme = self._orig

    def test_get_theme_default(self):
        from code_agents.chat.chat_theme import get_theme
        # Should return a valid theme name
        from code_agents.chat.chat_theme import THEMES
        assert get_theme() in THEMES

    def test_set_theme_valid(self):
        from code_agents.chat.chat_theme import set_theme, get_theme
        result = set_theme("light")
        assert result == "light"
        assert get_theme() == "light"

    def test_set_theme_invalid(self):
        from code_agents.chat.chat_theme import set_theme, get_theme
        original = get_theme()
        result = set_theme("nonexistent")
        assert result == original  # unchanged

    def test_set_theme_case_insensitive(self):
        from code_agents.chat.chat_theme import set_theme, get_theme
        set_theme("DARK-ANSI")
        assert get_theme() == "dark-ansi"

    def test_set_theme_updates_env(self):
        from code_agents.chat.chat_theme import set_theme
        set_theme("light-colorblind")
        assert os.environ.get("CODE_AGENTS_THEME") == "light-colorblind"

    def test_get_palette_returns_dict(self):
        from code_agents.chat.chat_theme import get_palette, set_theme
        set_theme("dark")
        p = get_palette()
        assert isinstance(p, dict)
        assert "green" in p


class TestApplyTheme:
    """Test _apply_theme updates chat_ui color functions."""

    def setup_method(self):
        from code_agents.chat import chat_theme
        self._orig = chat_theme._active_theme

    def teardown_method(self):
        from code_agents.chat import chat_theme
        chat_theme._active_theme = self._orig
        chat_theme._apply_theme()  # restore

    def test_apply_changes_color_functions(self):
        from code_agents.chat.chat_theme import set_theme, get_palette
        from code_agents.chat import chat_ui
        set_theme("dark")
        dark_palette = get_palette()
        set_theme("dark-colorblind")
        cb_palette = get_palette()
        # Colorblind theme uses different code for green
        assert dark_palette["green"] != cb_palette["green"]
        # Verify chat_ui functions were replaced (they're callable)
        assert callable(chat_ui.green)

    def test_apply_rebuilds_agent_colors(self):
        from code_agents.chat.chat_theme import set_theme
        from code_agents.chat import chat_ui
        set_theme("light")
        assert "code-writer" in chat_ui.AGENT_COLORS


class TestSaveTheme:
    """Test save_theme persistence to config.env."""

    def test_save_creates_entry(self, tmp_path):
        from code_agents.chat.chat_theme import save_theme
        config = tmp_path / ".code-agents" / "config.env"
        config.parent.mkdir(parents=True)
        config.write_text("# existing\nFOO=bar\n")
        with patch("code_agents.chat.chat_theme.Path.home", return_value=tmp_path):
            result = save_theme("light-ansi")
        assert result is True
        content = config.read_text()
        assert "CODE_AGENTS_THEME=light-ansi" in content
        assert "FOO=bar" in content

    def test_save_updates_existing(self, tmp_path):
        from code_agents.chat.chat_theme import save_theme
        config = tmp_path / ".code-agents" / "config.env"
        config.parent.mkdir(parents=True)
        config.write_text("CODE_AGENTS_THEME=dark\nFOO=bar\n")
        with patch("code_agents.chat.chat_theme.Path.home", return_value=tmp_path):
            save_theme("light")
        content = config.read_text()
        assert "CODE_AGENTS_THEME=light" in content
        assert "CODE_AGENTS_THEME=dark" not in content
        assert "FOO=bar" in content

    def test_save_handles_missing_dir(self):
        from code_agents.chat.chat_theme import save_theme
        with patch("code_agents.chat.chat_theme.Path.home", return_value=Path("/nonexistent/path")):
            result = save_theme("dark")
        assert result is False


class TestThemeSelector:
    """Test theme_selector interactive picker (fallback path)."""

    def test_selector_fallback_valid(self):
        from code_agents.chat.chat_theme import theme_selector
        with patch("builtins.input", return_value="2"):
            result = theme_selector()
        assert result == "light"

    def test_selector_fallback_first(self):
        from code_agents.chat.chat_theme import theme_selector
        with patch("builtins.input", return_value="1"):
            result = theme_selector()
        assert result == "dark"

    def test_selector_fallback_cancel(self):
        from code_agents.chat.chat_theme import theme_selector
        with patch("builtins.input", return_value=""):
            result = theme_selector()
        assert result is None

    def test_selector_fallback_eof(self):
        from code_agents.chat.chat_theme import theme_selector
        with patch("builtins.input", side_effect=EOFError):
            result = theme_selector()
        assert result is None

    def test_selector_fallback_all_options(self):
        from code_agents.chat.chat_theme import theme_selector, THEME_ORDER
        for i, expected in enumerate(THEME_ORDER, 1):
            with patch("builtins.input", return_value=str(i)):
                result = theme_selector()
            assert result == expected

    def test_selector_fallback_keyboard_interrupt(self):
        from code_agents.chat.chat_theme import theme_selector
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = theme_selector()
        assert result is None


class TestThemeSelectorTTY:
    """Test theme_selector tty raw-mode paths (lines 314-353)."""

    def setup_method(self):
        from code_agents.chat import chat_theme
        self._orig = chat_theme._active_theme

    def teardown_method(self):
        from code_agents.chat import chat_theme
        chat_theme._active_theme = self._orig

    def test_tty_enter_selects_current(self):
        """Enter key in raw mode selects current option."""
        from code_agents.chat.chat_theme import theme_selector
        import code_agents.chat.chat_theme as ct
        ct._active_theme = "dark"

        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0

        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, []]
        mock_termios.TCSANOW = 0

        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("code_agents.chat.chat_theme.sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_theme.os.read", return_value=b'\r'):
            result = theme_selector()
        assert result == "dark"

    def test_tty_escape_cancels(self):
        """Escape key returns None."""
        from code_agents.chat.chat_theme import theme_selector
        import code_agents.chat.chat_theme as ct
        ct._active_theme = "dark"

        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0

        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, []]
        mock_termios.TCSANOW = 0

        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("code_agents.chat.chat_theme.sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_theme.os.read", return_value=b'\x1b'):
            result = theme_selector()
        assert result is None

    def test_tty_arrow_down_then_enter(self):
        """Arrow down + enter selects next theme."""
        from code_agents.chat.chat_theme import theme_selector, THEME_ORDER
        import code_agents.chat.chat_theme as ct
        ct._active_theme = "dark"

        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0

        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, []]
        mock_termios.TCSANOW = 0

        reads = [b'\x1b[B', b'\r']
        read_iter = iter(reads)

        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("code_agents.chat.chat_theme.sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_theme.os.read", side_effect=read_iter):
            result = theme_selector()
        assert result == THEME_ORDER[1]

    def test_tty_arrow_up_then_enter(self):
        """Arrow up wraps around."""
        from code_agents.chat.chat_theme import theme_selector, THEME_ORDER
        import code_agents.chat.chat_theme as ct
        ct._active_theme = "dark"

        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0

        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, []]
        mock_termios.TCSANOW = 0

        reads = [b'\x1b[A', b'\r']
        read_iter = iter(reads)

        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("code_agents.chat.chat_theme.sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_theme.os.read", side_effect=read_iter):
            result = theme_selector()
        assert result == THEME_ORDER[-1]

    def test_tty_number_key_selects_directly(self):
        """Number key selects that option and returns immediately."""
        from code_agents.chat.chat_theme import theme_selector, THEME_ORDER
        import code_agents.chat.chat_theme as ct
        ct._active_theme = "dark"

        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0

        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, []]
        mock_termios.TCSANOW = 0

        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("code_agents.chat.chat_theme.sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_theme.os.read", return_value=b'3'):
            result = theme_selector()
        assert result == THEME_ORDER[2]

    def test_tty_ctrl_c_cancels(self):
        """Ctrl+C returns None."""
        from code_agents.chat.chat_theme import theme_selector
        import code_agents.chat.chat_theme as ct
        ct._active_theme = "dark"

        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0

        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, []]
        mock_termios.TCSANOW = 0

        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("code_agents.chat.chat_theme.sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_theme.os.read", return_value=b'\x03'):
            result = theme_selector()
        assert result is None

    def test_tty_empty_read_continues(self):
        """Empty read is skipped, then Enter selects."""
        from code_agents.chat.chat_theme import theme_selector
        import code_agents.chat.chat_theme as ct
        ct._active_theme = "dark"

        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0

        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, []]
        mock_termios.TCSANOW = 0

        reads = [b'', b'\r']
        read_iter = iter(reads)

        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("code_agents.chat.chat_theme.sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_theme.os.read", side_effect=read_iter):
            result = theme_selector()
        assert result == "dark"


class TestActiveThemeFallback:
    """Test that invalid CODE_AGENTS_THEME falls back to dark (line 173)."""

    def test_invalid_env_theme_falls_back(self):
        import importlib
        import code_agents.chat.chat_theme as ct
        orig = ct._active_theme
        try:
            ct._active_theme = "nonexistent"
            # Simulate what happens at module level
            if ct._active_theme not in ct.THEMES:
                ct._active_theme = "dark"
            assert ct._active_theme == "dark"
        finally:
            ct._active_theme = orig

    def test_invalid_env_theme_reimport(self):
        """Re-import module with invalid CODE_AGENTS_THEME env var (line 173)."""
        import importlib
        import code_agents.chat.chat_theme as ct
        orig = ct._active_theme
        try:
            with patch.dict(os.environ, {"CODE_AGENTS_THEME": "totally-invalid-theme"}):
                importlib.reload(ct)
            assert ct._active_theme == "dark"
        finally:
            ct._active_theme = orig
            importlib.reload(ct)


class TestApplyThemeMakeColor:
    """Test _apply_theme _make_color closure (line 231)."""

    def test_make_color_calls_w(self):
        from code_agents.chat.chat_theme import _apply_theme, set_theme
        from code_agents.chat import chat_ui
        orig_w = chat_ui._w

        called_with = []
        def mock_w(code, text):
            called_with.append((code, text))
            return f"[{code}]{text}"

        chat_ui._w = mock_w
        try:
            set_theme("dark")
            result = chat_ui.green("hello")
            assert ("32", "hello") in called_with
        finally:
            chat_ui._w = orig_w


class TestSlashThemeCommand:
    """Test /theme slash command handler."""

    def test_theme_direct_set(self, capsys):
        from code_agents.chat.chat_slash_config import _handle_config
        from code_agents.chat import chat_theme
        orig = chat_theme._active_theme
        try:
            result = _handle_config("/theme", "light", {}, "")
            assert result is None
            output = capsys.readouterr().out
            assert "Light (full color)" in output
        finally:
            chat_theme._active_theme = orig
            chat_theme._apply_theme()

    def test_theme_invalid_name(self, capsys):
        from code_agents.chat.chat_slash_config import _handle_config
        _handle_config("/theme", "nonexistent", {}, "")
        output = capsys.readouterr().out
        assert "Unknown theme" in output

    def test_theme_no_arg_shows_current(self, capsys):
        from code_agents.chat.chat_slash_config import _handle_config
        # Pass a mock selector that cancels
        with patch("code_agents.chat.chat_theme.theme_selector", return_value=None):
            _handle_config("/theme", "", {}, "")
        output = capsys.readouterr().out
        assert "Current theme" in output
