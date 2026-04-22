"""Streaming response handling with activity indicators.

Handles SSE streaming with blinking dot spinners, session summaries,
and duration formatting.
"""

from __future__ import annotations

import logging
import sys
import time as _time_mod
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_streaming")

from .chat_ui import (
    bold, green, yellow, red, cyan, dim,
    _render_markdown, agent_color,
)
from .chat_server import _stream_chat


def _format_session_duration(seconds: float) -> str:
    """Format session duration: 2m 15s, 1h 23m, etc."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s:02d}s"
    else:
        h, remainder = divmod(int(seconds), 3600)
        m, s = divmod(remainder, 60)
        return f"{h}h {m:02d}m"


def _stream_with_spinner(
    url: str, agent_name: str, messages: list[dict],
    session_id: str | None, cwd: str | None, state: dict,
    label: str = "Thinking",
    output_target=None,
) -> list[str]:
    """
    Stream a chat response with a blinking activity dot while waiting for first token.

    Shows: . Thinking -> agent label -> streamed response.
    Returns the list of response text pieces.

    Args:
        output_target: Optional OutputTarget for background task support.
    """
    import threading
    import time as _t

    # Import _last_ctrl_c from chat module at call time to avoid circular import
    from . import chat as _chat_mod

    # Output routing
    def _out_write(text: str) -> None:
        if output_target is not None:
            output_target.write(text)
        else:
            sys.stdout.write(text)
            sys.stdout.flush()

    def _out_flush() -> None:
        if output_target is not None:
            output_target.flush()
        else:
            sys.stdout.flush()

    _start = _t.monotonic()
    _stop = threading.Event()
    _activity_label = [label, ""]  # [action, target] — mutable for live updates

    def _format_time(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.0f}s"
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s:02d}s"

    def _blink():
        frames = [
            f"\033[1;34m⏺\033[0m",  # bright blue
            f"\033[2;34m⏺\033[0m",  # dim blue
        ]
        i = 0
        while not _stop.is_set():
            dot = frames[i % len(frames)]
            elapsed = _t.monotonic() - _start
            cur_action, cur_target = _activity_label
            target_str = f"({cur_target})" if cur_target else ""
            text = f"{cur_action}{target_str} {_format_time(elapsed)}"
            _out_write(f"\r  {dot} {dim(text)}  ")
            _out_flush()
            i += 1
            _stop.wait(0.5)
        _out_write(f"\r{' ' * 80}\r")
        _out_flush()

    spin_thread = threading.Thread(target=_blink, daemon=True)
    spin_thread.start()

    # Echo suppression no longer needed — patch_stdout keeps prompt separate
    _old_term = None

    got_text = False
    response: list[str] = []
    _interrupted = False
    agent_label = bold(agent_color(agent_name)(agent_name.upper()))

    try:
        for piece_type, piece_content in _stream_chat(
            url, agent_name, messages, session_id, cwd=cwd,
        ):
            if piece_type == "text":
                if not got_text:
                    _stop.set()
                    spin_thread.join(timeout=1)
                    _out_write(f"  {agent_label} › ")
                    _out_flush()
                got_text = True
                response.append(piece_content)
                _out_write(_render_markdown(piece_content))
                _out_flush()
            elif piece_type == "reasoning":
                # Update activity label with tool info while dot is still blinking
                activity_text = piece_content.strip()
                if activity_text and not _stop.is_set():
                    # Parse: "Reading file src/Foo.java" -> action="Reading", target="src/Foo.java"
                    parts = activity_text.split(None, 1)
                    if len(parts) == 2:
                        _activity_label[0] = parts[0]
                        _activity_label[1] = parts[1][:40]
                    else:
                        _activity_label[0] = activity_text[:40]
                        _activity_label[1] = ""
                elif _stop.is_set():
                    if not (activity_text.startswith("**") or "```" in activity_text or "{" in activity_text or "Tool Result" in activity_text):
                        _out_write(f"\n    {dim(activity_text[:80])}")
                        _out_flush()
            elif piece_type == "session_id":
                state["session_id"] = piece_content
                # Track session creation time for age-based expiry
                try:
                    from code_agents.core.backend import record_session_start
                    record_session_start(piece_content)
                except Exception:
                    pass
            elif piece_type == "usage":
                state["_last_usage"] = piece_content
            elif piece_type == "duration_ms":
                state["_last_duration_ms"] = piece_content
            elif piece_type == "error":
                if not _stop.is_set():
                    _stop.set()
                    spin_thread.join(timeout=1)
                print(red(f"\n  Error: {piece_content}"))
    except KeyboardInterrupt:
        _interrupted = True
        if not _stop.is_set():
            _stop.set()
            spin_thread.join(timeout=1)
        # Restore terminal echo before handling interrupt
        if _old_term is not None:
            try:
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, _old_term)
            except (ImportError, OSError, ValueError):
                pass
        now = _time_mod.time()
        if now - _chat_mod._last_ctrl_c < 1.5:
            # Double Ctrl+C — propagate to caller
            _chat_mod._last_ctrl_c = now
            raise
        _chat_mod._last_ctrl_c = now
        print()
        print(yellow("  Response interrupted."))
        print()

    if not _stop.is_set():
        _stop.set()
        spin_thread.join(timeout=1)

    if got_text and not _interrupted:
        print()

    elapsed = _t.monotonic() - _start
    usage = state.get("_last_usage")
    token_str = ""
    if usage:
        inp_uncached = usage.get("input_tokens", 0) or 0
        cache_create = usage.get("cache_creation_input_tokens", 0) or 0
        cache_read = usage.get("cache_read_input_tokens", 0) or 0
        inp = inp_uncached + cache_create + cache_read
        out = usage.get("output_tokens", 0) or 0
        total = inp + out
        est = " ~est" if usage.get("estimated") else ""
        if inp or out:
            cache_note = ""
            if cache_read:
                cache_note = f", {cache_read:,} cached"
            token_str = f" · request: {inp:,}, response: {out:,} tokens ({total:,} total{est}{cache_note})"
    # Restore terminal echo
    if _old_term is not None:
        try:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, _old_term)
        except (ImportError, OSError, ValueError):
            pass

    _out_write(f"  {dim(f'✻ Response took {_format_time(elapsed)}{token_str}')}\n")
    _out_write("\n")

    return response


def _print_session_summary(
    session_start: float, message_count: int, agent_name: str,
    commands_run: int,
) -> None:
    """Print session summary when chat ends — like Claude CLI."""
    import time as _t
    elapsed = _t.monotonic() - session_start
    duration = _format_session_duration(elapsed)

    # Get token totals from tracker
    from code_agents.core.token_tracker import get_session_summary
    usage = get_session_summary()
    total_tokens = usage.get("total_tokens", 0)
    cost = usage.get("cost_usd", 0)

    print()
    print(f"  {bold(cyan('━━━ Session Summary ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'))}")
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_tokens", 0)
    cache_write = usage.get("cache_write_tokens", 0)

    print(f"  {dim('Agent:')}       {bold(agent_name)}")
    print(f"  {dim('Messages:')}    {message_count}")
    print(f"  {dim('Commands:')}    {commands_run}")
    print(f"  {dim('Duration:')}    {bold(duration)}")
    if total_tokens:
        cache_note = f", {cache_read:,} cached" if cache_read else ""
        print(f"  {dim('Tokens:')}      {green(f'{input_tokens:,} in')} → {cyan(f'{output_tokens:,} out')} ({total_tokens:,} total{cache_note})")
    if cost > 0:
        print(f"  {dim('Cost:')}        ${cost:.4f}")
    print(f"  {bold(cyan('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'))}")
    print()
