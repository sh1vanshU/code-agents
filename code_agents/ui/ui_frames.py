"""
Unified UI Frame System — consistent terminal output formatting.

All CLI output should use these helpers for consistent look:
  frame_header()    → titled box header
  frame_section()   → section divider
  frame_kv()        → key-value pair
  frame_table()     → formatted table
  frame_list()      → bullet list
  frame_status()    → status line with icon
  frame_box()       → full content box
  frame_bar()       → progress bar
  frame_footer()    → bottom border

Usage:
    from code_agents.ui.ui_frames import frame_header, frame_section, frame_status, frame_kv

    frame_header("Security Scan", subtitle="pg-acquiring-biz")
    frame_section("Findings")
    frame_status("ok", "No vulnerabilities found")
    frame_kv("Files scanned", "142")
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Optional

logger = logging.getLogger("code_agents.ui.ui_frames")


def _term_width() -> int:
    """Get terminal width, capped for readability."""
    return min(shutil.get_terminal_size((80, 24)).columns, 120)


def _visible_len(text: str) -> int:
    """Length of text excluding ANSI escape codes."""
    import re
    return len(re.sub(r'\x1b\[[0-9;]*m', '', text))


# ── Colors (lazy import from chat_ui if available, else no-op) ──

def _get_colors():
    """Get color functions. Returns (bold, green, yellow, red, cyan, dim)."""
    try:
        from code_agents.chat.chat_ui import bold, green, yellow, red, cyan, dim
        return bold, green, yellow, red, cyan, dim
    except ImportError:
        _noop = lambda x: x
        return _noop, _noop, _noop, _noop, _noop, _noop


# ═══════════════════════════════════════════════════════════════════
# Frame Components
# ═══════════════════════════════════════════════════════════════════


def frame_header(title: str, subtitle: str = "", width: int = 0) -> str:
    """Render a titled header box.

    ╔══ TITLE ═════════════════════════╗
    ║ Subtitle                         ║
    ╚══════════════════════════════════╝
    """
    bold, green, yellow, red, cyan, dim = _get_colors()
    w = width or (_term_width() - 4)
    inner = w - 2

    lines = []
    # Title line
    title_str = f" {title} "
    remaining = inner - len(title_str) - 2  # -2 for ══ prefix
    lines.append(f"  {cyan('╔══')}{bold(cyan(title_str))}{cyan('═' * max(0, remaining))}{cyan('╗')}")

    if subtitle:
        sub_pad = inner - _visible_len(subtitle)
        lines.append(f"  {cyan('║')} {subtitle}{' ' * max(0, sub_pad - 1)}{cyan('║')}")

    lines.append(f"  {cyan('╚' + '═' * inner + '╝')}")
    return "\n".join(lines)


def frame_section(title: str, width: int = 0) -> str:
    """Render a section divider.

      ── Title ──────────────────────
    """
    bold, *_ = _get_colors()
    _, _, _, _, _, dim = _get_colors()
    w = width or (_term_width() - 4)
    title_str = f" {title} "
    remaining = w - len(title_str) - 2
    return f"\n  {dim('──')}{bold(title_str)}{dim('─' * max(0, remaining))}"


def frame_status(status: str, message: str, detail: str = "") -> str:
    """Render a status line with icon.

    status: "ok", "warn", "error", "info", "skip", "progress"
    """
    bold, green, yellow, red, cyan, dim = _get_colors()

    icons = {
        "ok": green("✓"),
        "warn": yellow("!"),
        "error": red("✗"),
        "info": cyan("ℹ"),
        "skip": dim("·"),
        "progress": yellow("⏳"),
        "critical": red("🔴"),
        "high": yellow("🟠"),
        "medium": yellow("🟡"),
        "low": green("🟢"),
    }
    icon = icons.get(status, dim("·"))
    line = f"  {icon} {message}"
    if detail:
        line += f" {dim(detail)}"
    return line


def frame_kv(key: str, value: str, indent: int = 4, key_width: int = 20) -> str:
    """Render a key-value pair.

        Key:           value
    """
    bold, *_ = _get_colors()
    return f"  {' ' * indent}{bold(key + ':'):<{key_width + 10}} {value}"


def frame_table(headers: list[str], rows: list[list[str]], indent: int = 4) -> str:
    """Render a formatted table.

      | Header1 | Header2 | Header3 |
      |---------|---------|---------|
      | val1    | val2    | val3    |
    """
    if not headers or not rows:
        return ""

    bold, *_ = _get_colors()
    _, _, _, _, _, dim = _get_colors()

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], _visible_len(str(cell)))

    pad = " " * indent
    lines = []

    # Header
    header_line = f"  {pad}| " + " | ".join(
        f"{bold(h):<{col_widths[i]}}" for i, h in enumerate(headers)
    ) + " |"
    lines.append(header_line)

    # Separator
    sep_line = f"  {pad}|" + "|".join(
        "-" * (w + 2) for w in col_widths
    ) + "|"
    lines.append(sep_line)

    # Rows
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            w = col_widths[i] if i < len(col_widths) else 10
            cells.append(f"{str(cell):<{w}}")
        lines.append(f"  {pad}| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def frame_list(items: list[str], bullet: str = "•", indent: int = 4, max_items: int = 15) -> str:
    """Render a bullet list.

      • Item one
      • Item two
      ... and 5 more
    """
    _, _, _, _, _, dim = _get_colors()
    pad = " " * indent
    lines = []
    for item in items[:max_items]:
        lines.append(f"  {pad}{bullet} {item}")
    if len(items) > max_items:
        lines.append(f"  {pad}{dim(f'... and {len(items) - max_items} more')}")
    return "\n".join(lines)


def frame_bar(value: float, max_value: float = 100, width: int = 30, label: str = "") -> str:
    """Render a progress bar.

      [████████████░░░░░░░░] 62% (label)
    """
    bold, green, yellow, red, *_ = _get_colors()
    pct = min(value / max_value, 1.0) if max_value > 0 else 0
    filled = int(pct * width)
    empty = width - filled

    # Color based on percentage
    if pct >= 0.8:
        color = green
    elif pct >= 0.5:
        color = yellow
    else:
        color = red

    bar = color("█" * filled) + "░" * empty
    pct_str = f"{pct * 100:.0f}%"
    label_str = f" ({label})" if label else ""
    return f"  [{bar}] {pct_str}{label_str}"


def frame_box(content: str, title: str = "", width: int = 0) -> str:
    """Render content inside a bordered box.

    ┌── Title ──────────────────────┐
    │ Content line 1                │
    │ Content line 2                │
    └───────────────────────────────┘
    """
    bold, _, _, _, cyan, dim = _get_colors()
    w = width or (_term_width() - 4)
    inner = w - 2

    lines = []

    # Top border
    if title:
        title_str = f" {title} "
        remaining = inner - len(title_str) - 2
        lines.append(f"  {cyan('┌──')}{bold(title_str)}{cyan('─' * max(0, remaining))}{cyan('┐')}")
    else:
        lines.append(f"  {cyan('┌' + '─' * inner + '┐')}")

    # Content
    for line in content.split("\n"):
        vis = _visible_len(line)
        pad = max(0, inner - vis - 2)
        lines.append(f"  {cyan('│')} {line}{' ' * pad} {cyan('│')}")

    # Bottom border
    lines.append(f"  {cyan('└' + '─' * inner + '┘')}")
    return "\n".join(lines)


def frame_footer(message: str = "") -> str:
    """Render a footer separator.

    ────────────────────────────────
    """
    _, _, _, _, _, dim = _get_colors()
    w = _term_width() - 4
    if message:
        return f"\n  {dim('─' * 2)} {dim(message)} {dim('─' * max(0, w - len(message) - 4))}"
    return f"\n  {dim('─' * w)}"


def frame_empty(message: str = "No data") -> str:
    """Render an empty state message."""
    _, _, _, _, _, dim = _get_colors()
    return f"\n  {dim(message)}\n"


# ═══════════════════════════════════════════════════════════════════
# Convenience: print versions (call print() for you)
# ═══════════════════════════════════════════════════════════════════

def print_header(title: str, subtitle: str = "", **kw):
    print(frame_header(title, subtitle, **kw))

def print_section(title: str, **kw):
    print(frame_section(title, **kw))

def print_status(status: str, message: str, detail: str = ""):
    print(frame_status(status, message, detail))

def print_kv(key: str, value: str, **kw):
    print(frame_kv(key, value, **kw))

def print_table(headers: list[str], rows: list[list[str]], **kw):
    print(frame_table(headers, rows, **kw))

def print_list(items: list[str], **kw):
    print(frame_list(items, **kw))

def print_bar(value: float, max_value: float = 100, **kw):
    print(frame_bar(value, max_value, **kw))

def print_box(content: str, title: str = "", **kw):
    print(frame_box(content, title, **kw))

def print_footer(message: str = ""):
    print(frame_footer(message))
