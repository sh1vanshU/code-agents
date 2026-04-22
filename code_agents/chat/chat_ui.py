"""Chat UI helpers — colors, spinners, selectors, markdown, welcome boxes."""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_ui")

# ---------------------------------------------------------------------------
# Colors (same as setup.py, no deps)
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR", "") == ""

# ANSI escape regex — used to strip codes when output doesn't support them
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return _ANSI_RE.sub("", text)


def use_color() -> bool:
    """Dynamic color check — respects runtime TTY state."""
    return _USE_COLOR


def _w(code: str, t: str) -> str:
    return f"\033[{code}m{t}\033[0m" if _USE_COLOR else t


# Theme support — CODE_AGENTS_THEME=light|dark(default)|minimal
_THEME = os.getenv("CODE_AGENTS_THEME", "dark").strip().lower()

if _THEME == "minimal":
    # Minimal: no colors at all
    _USE_COLOR = False

if _THEME == "light":
    # Light theme: swap some colors for better contrast on light terminals
    def bold(t: str) -> str: return _w("1", t)
    def green(t: str) -> str: return _w("32", t)
    def yellow(t: str) -> str: return _w("33", t)
    def red(t: str) -> str: return _w("31", t)
    def cyan(t: str) -> str: return _w("34", t)  # blue instead of cyan for light bg
    def dim(t: str) -> str: return _w("90", t)    # dark gray for light bg
    def magenta(t: str) -> str: return _w("35", t)
    def blue(t: str) -> str: return _w("34", t)
    def white(t: str) -> str: return _w("97", t)
    def bright_red(t: str) -> str: return _w("91", t)
    def bright_green(t: str) -> str: return _w("92", t)
    def bright_yellow(t: str) -> str: return _w("93", t)
    def bright_cyan(t: str) -> str: return _w("96", t)
    def bright_magenta(t: str) -> str: return _w("95", t)
else:
    # Dark theme (default)
    def bold(t: str) -> str: return _w("1", t)
    def green(t: str) -> str: return _w("32", t)
    def yellow(t: str) -> str: return _w("33", t)
    def red(t: str) -> str: return _w("31", t)
    def cyan(t: str) -> str: return _w("36", t)
    def dim(t: str) -> str: return _w("2", t)
    def magenta(t: str) -> str: return _w("35", t)
    def blue(t: str) -> str: return _w("34", t)
    def white(t: str) -> str: return _w("97", t)
    def bright_red(t: str) -> str: return _w("91", t)
    def bright_green(t: str) -> str: return _w("92", t)
    def bright_yellow(t: str) -> str: return _w("93", t)
    def bright_cyan(t: str) -> str: return _w("96", t)
    def bright_magenta(t: str) -> str: return _w("95", t)


# ---------------------------------------------------------------------------
# Agent colors — each agent gets a unique terminal color
# ---------------------------------------------------------------------------

AGENT_COLORS: dict[str, callable] = {
    "code-reasoning":       cyan,            # analysis = cool blue
    "code-writer":          green,           # creation = green
    "code-reviewer":        yellow,          # review = caution yellow
    "code-tester":          bright_cyan,     # testing = bright cyan
    "redash-query":         blue,            # data = blue
    "git-ops":              magenta,         # git = magenta
    "test-coverage":        bright_green,    # coverage = bright green
    "jenkins-cicd":         red,             # CI/CD = red (action)
    "argocd-verify":        bright_magenta,  # deploy verify = bright magenta
    "qa-regression":        bright_red,      # QA = bright red
    "auto-pilot":           white,           # autonomous = white (all-encompassing)
}


def agent_color(agent_name: str) -> callable:
    """Get the color function for an agent. Falls back to magenta."""
    return AGENT_COLORS.get(agent_name, magenta)


def _rl_wrap(code: str, t: str) -> str:
    """Wrap ANSI escape in readline invisible markers for prompts."""
    if not _USE_COLOR:
        return t
    return f"\x01\033[{code}m\x02{t}\x01\033[0m\x02"


def _rl_bold(t: str) -> str: return _rl_wrap("1", t)
def _rl_green(t: str) -> str: return _rl_wrap("32", t)


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_ANSI_STRIP_RE = re.compile(r"\033\[[0-9;]*m")


def _visible_len(text: str) -> int:
    """Return the visible length of a string, ignoring ANSI escape codes."""
    return len(_ANSI_STRIP_RE.sub("", text))


def _render_markdown(text: str) -> str:
    """Render markdown to terminal ANSI: **bold**, `code`, ```bash blocks, ## headers."""
    if not _USE_COLOR:
        return text

    # Handle fenced code blocks: ```bash ... ``` → yellow box
    def _render_code_block(m):
        lang = m.group(1) or ""
        code = m.group(2).strip()
        import shutil
        tw = shutil.get_terminal_size((80, 24)).columns
        bw = min(tw - 8, 100)
        lines = []
        label = f" {lang} " if lang else " code "
        rp = bw - 2 - len(label) - 1
        lines.append(f"\033[33m┌─{label}{'─' * max(0, rp)}┐\033[0m")
        for line in code.splitlines():
            # Wrap long lines
            while len(line) > bw - 4:
                lines.append(f"\033[33m│\033[0m \033[36m{line[:bw-4]}\033[0m \033[33m│\033[0m")
                line = line[bw-4:]
            pad = bw - 4 - len(line)
            lines.append(f"\033[33m│\033[0m \033[36m{line}\033[0m{' ' * max(0, pad)} \033[33m│\033[0m")
        lines.append(f"\033[33m└{'─' * (bw - 2)}┘\033[0m")
        return "\n" + "\n".join(lines) + "\n"

    text = re.sub(r'```(\w*)\n(.*?)```', _render_code_block, text, flags=re.DOTALL)

    # Inline markdown — bold+italic+colored, not white/black
    # **bold** → bold + italic + bright yellow
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: f"\033[1;3;33m{m.group(1)}\033[0m", text)
    # *italic* → italic + bright magenta
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', lambda m: f"\033[3;35m{m.group(1)}\033[0m", text)
    # `inline code` → cyan on dark bg
    text = re.sub(r'`([^`\n]+)`', lambda m: f"\033[36m{m.group(1)}\033[0m", text)
    # ## headers → bold + underline + bright cyan
    text = re.sub(r'^(#{1,4})\s+(.+)$', lambda m: f"\033[1;4;36m{m.group(2)}\033[0m", text, flags=re.MULTILINE)
    # --- horizontal rule → dim line
    text = re.sub(r'^---+\s*$', lambda m: f"\033[2m{'─' * 40}\033[0m", text, flags=re.MULTILINE)
    # > blockquote → italic + dim green
    text = re.sub(r'^>\s*(.+)$', lambda m: f"\033[3;2;32m▎ {m.group(1)}\033[0m", text, flags=re.MULTILINE)
    # - list items → bright bullet
    text = re.sub(r'^(\s*)- (.+)$', lambda m: f"{m.group(1)}\033[33m•\033[0m {m.group(2)}", text, flags=re.MULTILINE)

    # Table rendering — detect markdown tables and format with borders + colors
    def _render_table(text: str) -> str:
        lines = text.split("\n")
        result = []
        table_lines = []
        in_table = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                in_table = True
                table_lines.append(stripped)
            else:
                if in_table and table_lines:
                    result.append(_format_table(table_lines))
                    table_lines = []
                    in_table = False
                result.append(line)

        if table_lines:
            result.append(_format_table(table_lines))

        return "\n".join(result)

    def _format_table(table_lines: list[str]) -> str:
        import shutil
        tw = shutil.get_terminal_size((80, 24)).columns - 8

        # Parse cells
        rows = []
        sep_idx = -1
        for i, line in enumerate(table_lines):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c.strip()) <= {"-", ":"} for c in cells):
                sep_idx = i
                continue
            rows.append(cells)

        if not rows:
            return "\n".join(table_lines)

        # Calculate column widths
        num_cols = max(len(r) for r in rows)
        col_widths = [0] * num_cols
        for row in rows:
            for j, cell in enumerate(row):
                if j < num_cols:
                    col_widths[j] = max(col_widths[j], len(cell))

        # Cap total width
        total = sum(col_widths) + num_cols * 3 + 1
        if total > tw:
            scale = tw / total
            col_widths = [max(5, int(w * scale)) for w in col_widths]

        # Render
        out = []
        border = "\033[2m" + "┌" + "┬".join("─" * (w + 2) for w in col_widths) + "┐" + "\033[0m"
        mid = "\033[2m" + "├" + "┼".join("─" * (w + 2) for w in col_widths) + "┤" + "\033[0m"
        bottom = "\033[2m" + "└" + "┴".join("─" * (w + 2) for w in col_widths) + "┘" + "\033[0m"

        out.append(border)
        for i, row in enumerate(rows):
            cells = []
            for j in range(num_cols):
                cell = row[j] if j < len(row) else ""
                cell = cell[:col_widths[j]]
                pad = col_widths[j] - len(cell)
                if i == 0:
                    # Header row — bold + cyan
                    cells.append(f"\033[1;36m {cell}{' ' * pad} \033[0m")
                else:
                    cells.append(f" {cell}{' ' * pad} ")
            out.append("\033[2m│\033[0m" + "\033[2m│\033[0m".join(cells) + "\033[2m│\033[0m")
            if i == 0:
                out.append(mid)

        out.append(bottom)
        return "\n".join(out)

    text = _render_table(text)
    return text


# ---------------------------------------------------------------------------
# Spinner
# ---------------------------------------------------------------------------

def _spinner(message: str):
    """Context manager that shows a spinner while waiting."""
    import threading
    import itertools

    stop_event = threading.Event()

    def _spin():
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        for frame in itertools.cycle(frames):
            if stop_event.is_set():
                break
            sys.stdout.write(f"\r  {yellow(frame)} {dim(message)}")
            sys.stdout.flush()
            stop_event.wait(0.1)
        sys.stdout.write(f"\r{' ' * (len(message) + 10)}\r")
        sys.stdout.flush()

    class _SpinnerCtx:
        def __enter__(self):
            self._thread = threading.Thread(target=_spin, daemon=True)
            self._thread.start()
            return self

        def __exit__(self, *args):
            stop_event.set()
            self._thread.join(timeout=1)

    return _SpinnerCtx()


def activity_indicator(action: str = "Thinking", target: str = ""):
    """Show a blinking activity dot with action label.

    Usage:
        with activity_indicator("Reading", "PaymentService.java"):
            # ... do work ...

    Shows: ⏺ Reading(PaymentService.java)
    The dot blinks between bright blue and dim blue.
    """
    import threading

    stop_event = threading.Event()
    # Use a mutable container so the blink thread picks up label changes
    _label = [action, target]

    def _blink():
        frames = [
            f"\033[1;34m⏺\033[0m",  # bright blue
            f"\033[2;34m⏺\033[0m",  # dim blue
        ]
        i = 0
        while not stop_event.is_set():
            dot = frames[i % len(frames)]
            cur_action, cur_target = _label
            target_str = f"({cur_target})" if cur_target else ""
            label_text = f"{cur_action}{target_str}"
            sys.stdout.write(f"\r  {dot} {label_text}  ")
            sys.stdout.flush()
            i += 1
            stop_event.wait(0.5)
        # Clear line
        sys.stdout.write(f"\r{' ' * 80}\r")
        sys.stdout.flush()

    class _ActivityCtx:
        def __enter__(self):
            self._thread = threading.Thread(target=_blink, daemon=True)
            self._thread.start()
            return self

        def update(self, new_action: str, new_target: str = ""):
            """Update the activity label mid-execution."""
            _label[0] = new_action
            _label[1] = new_target

        def __exit__(self, *args):
            stop_event.set()
            self._thread.join(timeout=1)

    return _ActivityCtx()


# ---------------------------------------------------------------------------
# Agent response box
# ---------------------------------------------------------------------------

# Centralized agent ANSI color codes — used for boxes, labels, delegation banners
# Colors chosen to be visible on BOTH dark and light terminal backgrounds
AGENT_ANSI_COLORS = {
    "code-reasoning": "36",        # cyan
    "code-writer": "32",           # green
    "code-reviewer": "33",         # yellow
    "code-tester": "1;36",         # bright cyan
    "redash-query": "34",          # blue
    "git-ops": "35",               # magenta
    "test-coverage": "1;32",       # bright green
    "jenkins-cicd": "31",          # red
    "argocd-verify": "1;35",       # bright magenta
    "qa-regression": "1;31",       # bright red
    "auto-pilot": "1;36",          # bright cyan (not white — visible on both dark/light)
    "jira-ops": "1;34",            # bright blue
}

# For backward compat
_AGENT_COLORS = AGENT_ANSI_COLORS


def agent_color_fn(agent_name: str):
    """Return a function that wraps text in the agent's ANSI color."""
    code = AGENT_ANSI_COLORS.get(agent_name, "37")
    if not _USE_COLOR:
        return lambda s: s
    return lambda s: f"\033[{code}m{s}\033[0m"


def format_response_box(text: str, agent_name: str = "") -> str:
    """Format agent response text in a styled box with agent name header.

    Called AFTER streaming completes — wraps the full response in a box.
    """
    if not text or not text.strip():
        return ""

    import shutil
    term_width = shutil.get_terminal_size((80, 24)).columns
    box_width = min(term_width - 4, 120)  # cap at 120 for readability
    inner = box_width - 4  # padding inside box

    color_code = _AGENT_COLORS.get(agent_name, "37")
    c = lambda s: f"\033[{color_code}m{s}\033[0m" if _USE_COLOR else s

    lines_out = []

    # Top border with agent name
    if agent_name:
        label = f" {agent_name.upper()} "
        pad = box_width - 2 - len(label)
        left_pad = 1
        right_pad = pad - left_pad
        lines_out.append(f"  {c('╔' + '═' * left_pad + label + '═' * max(0, right_pad) + '╗')}")
    else:
        lines_out.append(f"  {c('╔' + '═' * (box_width - 2) + '╗')}")

    # Content lines
    for line in text.strip().splitlines():
        # Wrap long lines
        while len(line) > inner:
            chunk = line[:inner]
            lines_out.append(f"  {c('║')}  {chunk}{' ' * max(0, inner - len(chunk))}  {c('║')}")
            line = line[inner:]
        pad = inner - len(line)
        lines_out.append(f"  {c('║')}  {line}{' ' * max(0, pad)}  {c('║')}")

    # Bottom border
    lines_out.append(f"  {c('╚' + '═' * (box_width - 2) + '╝')}")

    return "\n".join(lines_out)


def print_response_box(text: str, agent_name: str = "") -> None:
    """Print agent response in a formatted box."""
    box = format_response_box(text, agent_name)
    if box:
        print(box)


# ---------------------------------------------------------------------------
# Interactive selectors
# ---------------------------------------------------------------------------

def _ask_yes_no(prompt_text: str, default: bool = True) -> bool:
    """Interactive Yes/No prompt with Tab switching."""
    return _tab_selector(prompt_text, ["Yes", "No"], default=0 if default else 1) == 0


def _amend_prompt() -> str:
    """Show inline amend prompt — user types what to change."""
    try:
        text = input("  > ").strip()
        return text
    except (EOFError, KeyboardInterrupt):
        return ""


def _tab_selector(prompt_text: str, options: list[str], default: int = 0) -> int:
    """Interactive selector using command_panel (raw TTY arrow-key navigation).

    Returns:
      0..N-1  — index of selected option
      -2      — Tab pressed (amend) — only via fallback
    """
    if sys.stdout.isatty():
        try:
            from code_agents.chat.command_panel import show_panel
            panel_options = [{"name": opt, "description": "", "active": False} for opt in options]
            idx = show_panel(prompt_text or "Select", "", panel_options, default)
            if idx is not None:
                return idx
            return len(options) - 1  # cancelled → last option (skip/cancel)
        except (ImportError, KeyboardInterrupt, EOFError):
            pass
        except Exception as e:
            logger.debug("_tab_selector: command_panel failed (%s), using fallback", e)

    # Fallback: numbered input
    print(f"  {bold(prompt_text)}")
    for i, opt in enumerate(options):
        marker = " *" if i == default else ""
        print(f"    {i + 1}. {opt}{marker}")
    try:
        answer = input(f"  [{default + 1}]: ").strip().lower()
        if answer == "t":
            return -2
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer) - 1
    except (EOFError, KeyboardInterrupt):
        return len(options) - 1

    return default


# ---------------------------------------------------------------------------
# Welcome message
# ---------------------------------------------------------------------------

# Import AGENT_WELCOME from chat_data to avoid circular imports
def _print_welcome(agent_name: str, agent_welcome: dict) -> None:
    """Print agent welcome message in a color-coded bordered box."""
    import shutil

    welcome = agent_welcome.get(agent_name)
    if not welcome:
        return

    title, capabilities, examples = welcome
    term_width = shutil.get_terminal_size((80, 24)).columns
    box_width = min(term_width - 4, 80)
    inner = box_width - 2

    # Use agent-specific color for the box border
    bc = agent_color(agent_name)

    def _line(text: str = "") -> str:
        """Render a box line with proper padding using visible length."""
        vis = _visible_len(text)
        pad = max(0, inner - vis - 1)
        return f"  {bc('│')} {text}{' ' * pad}{bc('│')}"

    print(f"  {bc('┌' + '─' * box_width + '┐')}")
    # Title line — use _visible_len for padding
    title_text = bold(bc(title))
    title_vis = _visible_len(title_text)
    title_pad = max(0, inner - title_vis - 1)
    print(f"  {bc('│')} {title_text}{' ' * title_pad}{bc('│')}")
    print(f"  {bc('├' + '─' * box_width + '┤')}")
    print(_line())
    print(_line(bold("What I can do:")))
    for cap in capabilities:
        print(_line(f"  • {cap}"))
    print(_line())
    print(_line(bold("Try asking:")))
    for ex in examples:
        print(_line(f"  {dim(ex)}"))
    print(_line())
    print(f"  {bc('└' + '─' * box_width + '┘')}")
    print()
