"""Theme system — interactive theme picker and color palette definitions.

Themes control all UI colors: prompt, toolbar, agent labels, status messages.
Persisted as CODE_AGENTS_THEME in ~/.code-agents/config.env.

Available themes:
  dark            Full-color dark (default)
  light           Full-color light
  dark-colorblind Daltonized dark (colorblind-friendly)
  light-colorblind Daltonized light (colorblind-friendly)
  dark-ansi       Terminal's native 16-color dark palette
  light-ansi      Terminal's native 16-color light palette
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_theme")


# ---------------------------------------------------------------------------
# Theme palette definitions — each maps semantic names to ANSI codes
# ---------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bold": "1",
        "green": "32",
        "yellow": "33",
        "red": "31",
        "cyan": "36",
        "dim": "2",
        "magenta": "35",
        "blue": "34",
        "white": "97",
        "bright_red": "91",
        "bright_green": "92",
        "bright_yellow": "93",
        "bright_cyan": "96",
        "bright_magenta": "95",
        "prompt_user": "32",       # green
        "prompt_separator": "90",  # dark gray
        "prompt_arrow": "97",      # white
        "toolbar_bg": "40",        # black bg
        "toolbar_fg": "37",        # gray fg
    },
    "light": {
        "bold": "1",
        "green": "32",
        "yellow": "33",
        "red": "31",
        "cyan": "34",              # blue for light bg contrast
        "dim": "90",               # dark gray for light bg
        "magenta": "35",
        "blue": "34",
        "white": "30",             # black text on light bg
        "bright_red": "91",
        "bright_green": "92",
        "bright_yellow": "93",
        "bright_cyan": "94",       # bright blue
        "bright_magenta": "95",
        "prompt_user": "32",
        "prompt_separator": "37",  # light gray
        "prompt_arrow": "30",      # black
        "toolbar_bg": "47",        # white bg
        "toolbar_fg": "30",        # black fg
    },
    "dark-colorblind": {
        "bold": "1",
        "green": "96",             # bright cyan instead of green
        "yellow": "93",            # bright yellow (distinct from green)
        "red": "91",               # bright red
        "cyan": "94",              # bright blue instead of cyan
        "dim": "2",
        "magenta": "97",           # white instead of magenta
        "blue": "94",              # bright blue
        "white": "97",
        "bright_red": "1;91",
        "bright_green": "1;96",
        "bright_yellow": "1;93",
        "bright_cyan": "1;94",
        "bright_magenta": "1;97",
        "prompt_user": "96",
        "prompt_separator": "90",
        "prompt_arrow": "97",
        "toolbar_bg": "40",
        "toolbar_fg": "37",
    },
    "light-colorblind": {
        "bold": "1",
        "green": "34",             # blue instead of green
        "yellow": "33",
        "red": "31",
        "cyan": "36",
        "dim": "90",
        "magenta": "30",           # black instead of magenta
        "blue": "34",
        "white": "30",
        "bright_red": "1;31",
        "bright_green": "1;34",
        "bright_yellow": "1;33",
        "bright_cyan": "1;36",
        "bright_magenta": "1;30",
        "prompt_user": "34",
        "prompt_separator": "37",
        "prompt_arrow": "30",
        "toolbar_bg": "47",
        "toolbar_fg": "30",
    },
    "dark-ansi": {
        "bold": "1",
        "green": "32",
        "yellow": "33",
        "red": "31",
        "cyan": "36",
        "dim": "2",
        "magenta": "35",
        "blue": "34",
        "white": "37",
        "bright_red": "1;31",
        "bright_green": "1;32",
        "bright_yellow": "1;33",
        "bright_cyan": "1;36",
        "bright_magenta": "1;35",
        "prompt_user": "32",
        "prompt_separator": "2",
        "prompt_arrow": "1;37",
        "toolbar_bg": "40",
        "toolbar_fg": "37",
    },
    "light-ansi": {
        "bold": "1",
        "green": "32",
        "yellow": "33",
        "red": "31",
        "cyan": "36",
        "dim": "2",
        "magenta": "35",
        "blue": "34",
        "white": "37",
        "bright_red": "1;31",
        "bright_green": "1;32",
        "bright_yellow": "1;33",
        "bright_cyan": "1;36",
        "bright_magenta": "1;35",
        "prompt_user": "32",
        "prompt_separator": "2",
        "prompt_arrow": "1;30",
        "toolbar_bg": "47",
        "toolbar_fg": "30",
    },
}

THEME_DISPLAY_NAMES: dict[str, str] = {
    "dark": "Dark (full color)",
    "light": "Light (full color)",
    "dark-colorblind": "Dark (colorblind-friendly)",
    "light-colorblind": "Light (colorblind-friendly)",
    "dark-ansi": "Dark (ANSI \u2014 terminal palette)",
    "light-ansi": "Light (ANSI \u2014 terminal palette)",
}

THEME_ORDER = ["dark", "light", "dark-colorblind", "light-colorblind", "dark-ansi", "light-ansi"]

# Active theme — loaded once at import, can be changed at runtime
_active_theme: str = os.getenv("CODE_AGENTS_THEME", "dark").strip().lower()
if _active_theme not in THEMES:
    _active_theme = "dark"


def get_theme() -> str:
    """Return the current theme name."""
    return _active_theme


def get_palette() -> dict[str, str]:
    """Return the ANSI code palette for the active theme."""
    return THEMES.get(_active_theme, THEMES["dark"])


def set_theme(name: str) -> str:
    """Switch theme at runtime. Returns the theme actually set."""
    global _active_theme
    name = name.strip().lower()
    if name not in THEMES:
        return _active_theme
    _active_theme = name
    os.environ["CODE_AGENTS_THEME"] = name
    # Re-apply color functions in chat_ui
    _apply_theme()
    logger.info("theme switched to %s", name)
    return _active_theme


def save_theme(name: str) -> bool:
    """Persist theme choice to ~/.code-agents/config.env."""
    try:
        env_file = Path.home() / ".code-agents" / "config.env"
        # Read existing content and update or append
        lines: list[str] = []
        found = False
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.strip().startswith("CODE_AGENTS_THEME="):
                    lines.append(f"CODE_AGENTS_THEME={name}")
                    found = True
                else:
                    lines.append(line)
        if not found:
            lines.append(f"CODE_AGENTS_THEME={name}")
        env_file.write_text("\n".join(lines) + "\n")
        logger.info("theme saved to %s", env_file)
        return True
    except OSError as e:
        logger.warning("failed to save theme: %s", e)
        return False


def _apply_theme() -> None:
    """Re-define color functions in chat_ui to match the active palette."""
    from . import chat_ui
    p = get_palette()

    def _make_color(code: str):
        def _color(t: str) -> str:
            return chat_ui._w(code, t)
        return _color

    chat_ui.bold = _make_color(p["bold"])
    chat_ui.green = _make_color(p["green"])
    chat_ui.yellow = _make_color(p["yellow"])
    chat_ui.red = _make_color(p["red"])
    chat_ui.cyan = _make_color(p["cyan"])
    chat_ui.dim = _make_color(p["dim"])
    chat_ui.magenta = _make_color(p["magenta"])
    chat_ui.blue = _make_color(p["blue"])
    chat_ui.white = _make_color(p["white"])
    chat_ui.bright_red = _make_color(p["bright_red"])
    chat_ui.bright_green = _make_color(p["bright_green"])
    chat_ui.bright_yellow = _make_color(p["bright_yellow"])
    chat_ui.bright_cyan = _make_color(p["bright_cyan"])
    chat_ui.bright_magenta = _make_color(p["bright_magenta"])

    # Rebuild AGENT_COLORS with new functions
    chat_ui.AGENT_COLORS = {
        "code-reasoning":       chat_ui.cyan,
        "code-writer":          chat_ui.green,
        "code-reviewer":        chat_ui.yellow,
        "code-tester":          chat_ui.bright_cyan,
        "redash-query":         chat_ui.blue,
        "git-ops":              chat_ui.magenta,
        "test-coverage":        chat_ui.bright_green,
        "jenkins-cicd":         chat_ui.red,
        "argocd-verify":        chat_ui.bright_magenta,
        "qa-regression":        chat_ui.bright_red,
        "auto-pilot":           chat_ui.white,
    }


# ---------------------------------------------------------------------------
# Interactive theme picker
# ---------------------------------------------------------------------------


def theme_selector() -> Optional[str]:
    """Arrow-key theme picker. Returns selected theme name or None on cancel."""
    options = [THEME_DISPLAY_NAMES[t] for t in THEME_ORDER]
    current_idx = THEME_ORDER.index(_active_theme) if _active_theme in THEME_ORDER else 0
    selected = current_idx
    _rendered = [0]

    def _bold(t: str) -> str:
        return f"\033[1m{t}\033[0m"

    def _green(t: str) -> str:
        return f"\033[32m{t}\033[0m"

    def _dim(t: str) -> str:
        return f"\033[2m{t}\033[0m"

    def _render():
        for _ in range(_rendered[0]):
            sys.stdout.write("\033[A\033[2K")
        if _rendered[0] > 0:
            sys.stdout.write("\r")
        sys.stdout.flush()
        count = 0
        for i, opt in enumerate(options):
            num = str(i + 1)
            if i == selected:
                print(f"    {_bold(_green(f'{num}. \u276f {opt}'))}")
            else:
                print(f"    {_dim(f'{num}.   {opt}')}")
            count += 1
        print(f"    {_dim('\u2191\u2193 navigate \u00b7 Enter select \u00b7 Esc cancel')}")
        count += 1
        _rendered[0] = count

    print(f"  {_bold('Choose a theme:')}")
    print()
    _render()

    try:
        import tty, termios

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)
            while True:
                ch = os.read(fd, 1)
                if not ch:
                    continue
                b = ch[0]

                # Ctrl+C → cancel
                if b == 0x03:
                    termios.tcsetattr(fd, termios.TCSANOW, old)
                    print()
                    return None

                # Escape byte — could be standalone Esc or start of arrow sequence
                if b == 0x1b:
                    import select
                    ready, _, _ = select.select([fd], [], [], 0.05)
                    if not ready:
                        # Standalone Esc — cancel
                        termios.tcsetattr(fd, termios.TCSANOW, old)
                        print()
                        return None
                    rest = os.read(fd, 7)
                    seq = ch + rest
                    seq_str = seq.decode("utf-8", errors="ignore")

                    # Arrow up
                    if seq_str in ("\x1b[A", "\x1bOA"):
                        selected = (selected - 1) % len(options)
                        termios.tcsetattr(fd, termios.TCSANOW, old)
                        _render()
                        tty.setraw(fd)
                    # Arrow down
                    elif seq_str in ("\x1b[B", "\x1bOB"):
                        selected = (selected + 1) % len(options)
                        termios.tcsetattr(fd, termios.TCSANOW, old)
                        _render()
                        tty.setraw(fd)
                    continue

                # Enter
                if b in (0x0d, 0x0a):
                    break
                # Number keys
                c = chr(b)
                if c.isdigit() and 1 <= int(c) <= len(options):
                    selected = int(c) - 1
                    termios.tcsetattr(fd, termios.TCSANOW, old)
                    _render()
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old)

    except (ImportError, OSError, ValueError):
        # Fallback: numbered input
        try:
            answer = input(f"  [{current_idx + 1}]: ").strip()
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                selected = int(answer) - 1
            else:
                return None
        except (EOFError, KeyboardInterrupt):
            return None

    print()
    return THEME_ORDER[selected]
