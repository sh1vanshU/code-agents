"""Setup UI helpers — colors, prompts, validators."""

from __future__ import annotations

import getpass
import logging
import re
import sys
from typing import Callable, Optional

logger = logging.getLogger("code_agents.setup.setup_ui")

# ---------------------------------------------------------------------------
# ANSI color helpers
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty()


def _wrap(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def bold(t: str) -> str:
    return _wrap("1", t)

def green(t: str) -> str:
    return _wrap("32", t)

def yellow(t: str) -> str:
    return _wrap("33", t)

def red(t: str) -> str:
    return _wrap("31", t)

def cyan(t: str) -> str:
    return _wrap("36", t)

def dim(t: str) -> str:
    return _wrap("2", t)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def prompt(
    label: str,
    default: Optional[str] = None,
    secret: bool = False,
    required: bool = False,
    validator: Optional[Callable[[str], bool]] = None,
    transform: Optional[Callable[[str], str]] = None,
    error_msg: str = "Invalid input.",
) -> str:
    """Prompt user for input. Loops on validation failure. Optional transform."""
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            if secret:
                value = getpass.getpass(f"  {label}{suffix}: ")
            else:
                value = input(f"  {label}{suffix}: ")
        except EOFError:
            value = ""

        value = value.strip()
        if not value and default is not None:
            value = default
        if required and not value:
            print(red("    Required — please enter a value."))
            continue
        if value and validator and not validator(value):
            print(red(f"    {error_msg}"))
            continue
        if value and transform:
            value = transform(value)
        return value


def _prompt_yes_no_plain(label: str, default: bool) -> bool:
    """Yes/No when stdin is not a TTY (CI, pipes) or termios unavailable: type y/n or 1/2."""
    hint = "Y/n" if default else "y/N"
    while True:
        try:
            value = input(f"  {label} [{hint}]: ").strip().lower()
        except EOFError:
            return default
        except KeyboardInterrupt:
            print()
            return default
        if not value:
            return default
        if value in ("y", "yes", "1"):
            return True
        if value in ("n", "no", "2"):
            return False
        print(red("    Enter y/n or 1 (yes) / 2 (no)."))


def prompt_yes_no(label: str, default: bool = True) -> bool:
    """Interactive Yes/No: arrow keys or Tab to move, Enter to confirm (TTY).

    Falls back to typed y/n or 1/2 when not interactive.
    """
    import sys

    if not sys.stdin.isatty():
        return _prompt_yes_no_plain(label, default)
    try:
        import tty
        import termios  # noqa: F401
    except ImportError:
        return _prompt_yes_no_plain(label, default)

    idx = prompt_choice(label, ["Yes", "No"], default=1 if default else 2)
    return idx == 1


def prompt_choice(label: str, choices: list[str], default: int = 1) -> int:
    """Arrow-key selector for choices. Falls back to numbered input if no tty.

    Returns 1-based index of selected choice.
    """
    import sys
    if not sys.stdin.isatty():
        # Fallback: plain numbered input
        return _prompt_choice_plain(label, choices, default)

    try:
        import tty, termios
    except ImportError:
        return _prompt_choice_plain(label, choices, default)

    selected = default - 1  # 0-based
    rendered_lines = [0]

    def _render():
        # Clear previously rendered lines
        for _ in range(rendered_lines[0]):
            sys.stdout.write("\033[A\033[2K")
        if rendered_lines[0] > 0:
            sys.stdout.write("\r")
        sys.stdout.flush()
        count = 0
        for i, c in enumerate(choices):
            num = str(i + 1)
            if i == selected:
                sys.stdout.write(f"    {bold(green(f'{num}. ❯ {c}'))}\n")
            else:
                sys.stdout.write(f"    {dim(f'{num}.   {c}')}\n")
            count += 1
        sys.stdout.write(f"    {dim('↑↓ Tab · Enter to confirm')}\n")
        count += 1
        sys.stdout.flush()
        rendered_lines[0] = count

    print(f"  {bold(label)}")
    _render()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        while True:
            tty.setcbreak(fd)
            ch = sys.stdin.read(1)

            if ch == "\r" or ch == "\n":  # Enter
                break
            elif ch == "\t":  # Tab — cycle forward (same as Down for 2-item lists)
                selected = (selected + 1) % len(choices)
            elif ch == "\x1b":  # Escape sequence
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":  # Up
                        selected = (selected - 1) % len(choices)
                    elif ch3 == "B":  # Down
                        selected = (selected + 1) % len(choices)
                    elif ch3 == "Z":  # Shift+Tab
                        selected = (selected - 1) % len(choices)
                elif ch2 == "\x1b" or ch2 == "":  # Esc key
                    break
            elif ch.isdigit():
                idx = int(ch)
                if 1 <= idx <= len(choices):
                    selected = idx - 1
                    break

            _render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    # Clear selector and show final choice
    for _ in range(rendered_lines[0]):
        sys.stdout.write("\033[A\033[2K")
    sys.stdout.write("\r")
    sys.stdout.flush()
    print(f"    {green('✓')} {choices[selected]}")

    return selected + 1  # 1-based


def _prompt_choice_plain(label: str, choices: list[str], default: int = 1) -> int:
    """Fallback numbered choice prompt (no tty). Returns 1-based index."""
    for i, c in enumerate(choices, 1):
        marker = bold("*") if i == default else " "
        print(f"    {marker} [{i}] {c}")
    while True:
        try:
            value = input(f"  {label} (default: {default}): ").strip()
        except EOFError:
            value = ""
        if not value:
            return default
        try:
            idx = int(value)
            if 1 <= idx <= len(choices):
                return idx
        except ValueError:
            pass
        print(red(f"    Enter a number 1-{len(choices)}."))


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_url(v: str) -> bool:
    try:
        result = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(v)
        return bool(result.scheme and result.netloc)
    except Exception:
        return False


def validate_port(v: str) -> bool:
    try:
        return 1 <= int(v) <= 65535
    except ValueError:
        return False


def validate_job_path(v: str) -> bool:
    """Jenkins job should be a clean folder path, not a full URL."""
    if v.startswith("http://") or v.startswith("https://"):
        return False
    return bool(v.strip("/"))


def clean_job_path(v: str) -> str:
    """Strip 'job/' prefixes from Jenkins paths."""
    raw_parts = [p for p in v.strip("/").split("/") if p]
    parts = []
    for i, p in enumerate(raw_parts):
        if p == "job" and i + 1 < len(raw_parts):
            continue
        else:
            parts.append(p)
    cleaned = "/".join(parts)
    if cleaned != v.strip("/"):
        print(dim(f"    Auto-cleaned: {v} -> {cleaned}"))
    return cleaned
