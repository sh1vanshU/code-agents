"""Claude Code-style interactive command panel.

Renders a selectable option list below the input with arrow-key navigation,
descriptions, active markers, and Enter/Esc handling. Uses raw terminal mode
(tty + ANSI escapes) — no external dependencies.

Usage::

    from .command_panel import show_panel

    idx = show_panel(
        title="Select model",
        subtitle="Switch between models. Applies to this session.",
        options=[
            {"name": "Opus 4.6", "description": "Most capable", "active": True},
            {"name": "Sonnet 4.6", "description": "Fast everyday", "active": False},
        ],
        default=0,
    )
    # idx = selected index (int) or None (Esc)
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.chat.command_panel")


def show_panel(
    title: str,
    subtitle: str = "",
    options: list[dict] | None = None,
    default: int = 0,
) -> int | None:
    """Show an interactive panel and return the selected index, or None on cancel.

    Each option dict: ``{"name": str, "description": str, "active": bool}``
    """
    if not options:
        return None

    # Non-TTY fallback: numbered list
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        return _fallback_selector(title, options, default)

    try:
        import tty
        import termios
    except ImportError:
        return _fallback_selector(title, options, default)

    selected = default
    n_options = len(options)
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        # Calculate total lines for clearing
        total_lines = _render(title, subtitle, options, selected)

        tty.setraw(fd)

        while True:
            key = _read_key(fd)

            if key == "up":
                selected = (selected - 1) % n_options
            elif key == "down":
                selected = (selected + 1) % n_options
            elif key == "enter":
                # Clear panel before returning
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                _clear(total_lines)
                return selected
            elif key == "esc":
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                _clear(total_lines)
                return None
            elif key and key.isdigit():
                num = int(key)
                if 1 <= num <= n_options:
                    selected = num - 1
            else:
                continue

            # Restore terminal briefly to re-render
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            _clear(total_lines)
            total_lines = _render(title, subtitle, options, selected)
            tty.setraw(fd)

    except (KeyboardInterrupt, EOFError):
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        _clear(total_lines)
        return None
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"
_ERASE_LINE = "\033[2K"
_CURSOR_UP = "\033[A"


def _render(title: str, subtitle: str, options: list[dict], selected: int) -> int:
    """Render the panel and return number of lines printed."""
    lines: list[str] = []

    # Header
    lines.append("")
    lines.append(f"  {_BOLD}{_CYAN}{title}{_RESET}")
    if subtitle:
        lines.append(f"  {_DIM}{subtitle}{_RESET}")
    lines.append("")

    # Options
    for i, opt in enumerate(options):
        name = opt.get("name", "")
        desc = opt.get("description", "")
        active = opt.get("active", False)

        # Cursor and styling
        if i == selected:
            cursor = f"{_CYAN}›{_RESET}"
            name_fmt = f"{_BOLD}{_GREEN}{name}{_RESET}"
        else:
            cursor = " "
            name_fmt = f"  {name}"

        # Active marker
        check = f" {_GREEN}✔{_RESET}" if active else ""

        # Description
        desc_fmt = f"  {_DIM}{desc}{_RESET}" if desc else ""

        num = f"{_DIM}{i + 1}.{_RESET}"
        lines.append(f"    {num} {cursor} {name_fmt}{check}{desc_fmt}")

    # Footer
    lines.append("")
    lines.append(f"  {_DIM}↑↓ navigate · Enter select · Esc cancel{_RESET}")
    lines.append("")

    output = "\r\n".join(lines)
    sys.stdout.write(output)
    sys.stdout.flush()
    return len(lines)


def _clear(n: int) -> None:
    """Move cursor up n lines and erase each one."""
    for _ in range(n):
        sys.stdout.write(f"{_CURSOR_UP}{_ERASE_LINE}")
    sys.stdout.write("\r")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Key reading
# ---------------------------------------------------------------------------

def _read_key(fd: int) -> str:
    """Read a single keypress in raw mode. Returns key name string.

    Uses os.read(fd) instead of sys.stdin.read() to bypass prompt_toolkit's
    stdin wrapper which can echo escape sequences when patch_stdout is active.
    """
    import os as _os
    ch = _os.read(fd, 1)
    if ch == b"\x1b":  # Escape sequence
        ch2 = _os.read(fd, 1)
        if ch2 == b"[":
            ch3 = _os.read(fd, 1)
            if ch3 == b"A":
                return "up"
            elif ch3 == b"B":
                return "down"
            elif ch3 == b"C":
                return "right"
            elif ch3 == b"D":
                return "left"
        return "esc"
    elif ch in (b"\r", b"\n"):
        return "enter"
    elif ch == b"\x03":  # Ctrl+C
        return "esc"
    elif ch == b"\x04":  # Ctrl+D
        return "esc"
    elif ch.isdigit():
        return ch.decode()
    return ""


# ---------------------------------------------------------------------------
# Fallback (non-TTY)
# ---------------------------------------------------------------------------

def _fallback_selector(title: str, options: list[dict], default: int) -> int:
    """Simple numbered fallback for non-TTY environments."""
    print(f"\n  {title}")
    print()
    for i, opt in enumerate(options):
        name = opt.get("name", "")
        active = " ✔" if opt.get("active") else ""
        marker = " *" if i == default else "  "
        print(f"  {marker} {i + 1}. {name}{active}")
    print()
    try:
        choice = input(f"  Choose [1-{len(options)}]: ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
    except (EOFError, KeyboardInterrupt):
        pass
    return default
