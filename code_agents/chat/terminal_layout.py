"""
Terminal layout — fixed input bar at bottom, scrolling output above.

Uses ANSI scroll regions to split the terminal:
  - Top region (rows 1..N-3): scrolling output
  - Bottom region (rows N-2..N): fixed input bar

The input bar stays visible while the agent streams responses or
shows command approval prompts. A background thread collects user
input and feeds it into the message queue.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import shutil
import threading

logger = logging.getLogger("code_agents.chat.terminal_layout")

# Module state
_layout_active = False
_input_height = 3  # separator + prompt + padding


def supports_layout() -> bool:
    """Check if terminal supports the fixed layout."""
    if not sys.stdout.isatty():
        return False
    if os.getenv("CODE_AGENTS_SIMPLE_UI", "").lower() in ("1", "true"):
        return False
    term = os.getenv("TERM", "")
    if term in ("dumb", ""):
        return False
    return True


def get_terminal_size() -> tuple[int, int]:
    """Get terminal (columns, rows)."""
    size = shutil.get_terminal_size((80, 24))
    return size.columns, size.lines


def enter_input_region() -> None:
    """Activate the fixed input region at the bottom of the terminal.

    Sets an ANSI scroll region so output scrolls in the top area while
    the bottom 3 rows stay fixed for the input bar.
    """
    global _layout_active
    if not supports_layout() or _layout_active:
        return

    cols, rows = get_terminal_size()
    if rows < 10:
        return  # terminal too small

    scroll_end = rows - _input_height

    # Set scroll region to top area
    sys.stdout.write(f"\033[1;{scroll_end}r")
    # Move cursor to end of scroll region
    sys.stdout.write(f"\033[{scroll_end};1H")
    sys.stdout.flush()

    _layout_active = True

    # Handle terminal resize
    try:
        signal.signal(signal.SIGWINCH, _handle_resize)
    except (OSError, ValueError):
        pass


def exit_input_region() -> None:
    """Restore normal terminal mode — full scroll region."""
    global _layout_active
    if not _layout_active:
        return

    cols, rows = get_terminal_size()
    # Reset scroll region to full terminal
    sys.stdout.write(f"\033[1;{rows}r")
    # Move cursor to bottom
    sys.stdout.write(f"\033[{rows};1H")
    sys.stdout.flush()

    _layout_active = False

    # Restore default SIGWINCH
    try:
        signal.signal(signal.SIGWINCH, signal.SIG_DFL)
    except (OSError, ValueError):
        pass


def draw_input_bar(
    agent_name: str = "",
    nickname: str = "you",
    queue_size: int = 0,
) -> None:
    """Draw the fixed input bar at the bottom of the terminal."""
    if not _layout_active:
        return

    cols, rows = get_terminal_size()
    separator_row = rows - 2
    input_row = rows - 1

    # Save cursor position
    sys.stdout.write("\033[s")

    # Draw separator line
    sys.stdout.write(f"\033[{separator_row};1H\033[2K")
    sep = "\u2500" * cols
    sys.stdout.write(f"\033[90m{sep}\033[0m")

    # Draw prompt line
    sys.stdout.write(f"\033[{input_row};1H\033[2K")
    queue_label = f" \033[33m({queue_size} queued)\033[0m" if queue_size else ""
    prompt = f"  \033[1m{nickname}\033[0m \u276f {queue_label}"
    sys.stdout.write(prompt)

    # Restore cursor
    sys.stdout.write("\033[u")
    sys.stdout.flush()


def update_queue_count(count: int, nickname: str = "you") -> None:
    """Update just the queue count on the input bar without full redraw."""
    if not _layout_active:
        return
    draw_input_bar(nickname=nickname, queue_size=count)


def is_layout_active() -> bool:
    """Return whether the fixed layout is currently active."""
    return _layout_active


def _handle_resize(signum, frame):
    """Handle terminal resize — reapply scroll region."""
    if not _layout_active:
        return
    cols, rows = get_terminal_size()
    if rows < 10:
        return
    scroll_end = rows - _input_height
    sys.stdout.write(f"\033[1;{scroll_end}r")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Legacy API (kept for /layout command compatibility)
# ---------------------------------------------------------------------------

enter_layout = enter_input_region
exit_layout = exit_input_region


def move_to_output() -> None:
    """Move cursor to the output (scroll) region."""
    if not _layout_active:
        return
    cols, rows = get_terminal_size()
    scroll_end = rows - _input_height
    sys.stdout.write(f"\033[{scroll_end};1H")
    sys.stdout.flush()


def move_to_input() -> None:
    """Move cursor to the input line."""
    if not _layout_active:
        return
    cols, rows = get_terminal_size()
    input_row = rows - 1
    sys.stdout.write(f"\033[{input_row};1H\033[2K")
    sys.stdout.flush()
