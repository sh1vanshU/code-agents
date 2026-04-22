"""
Chat input — prompt_toolkit based input with fixed bottom bar.

Replaces readline input() with prompt_toolkit for:
- Fixed input at bottom of terminal
- Output scrolls above without affecting input
- Spinner/timer don't clobber input
- Better autocomplete (dropdown)
- Mode cycling: Chat / Plan / Edit via Shift+Tab
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from collections import deque
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_input")

_HAS_PT = False
_HAS_PATCH_STDOUT = False
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import WordCompleter, NestedCompleter
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.patch_stdout import patch_stdout as _patch_stdout
    _HAS_PT = True
    _HAS_PATCH_STDOUT = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Chat mode cycling: Chat -> Plan -> Edit (Shift+Tab)
# ---------------------------------------------------------------------------

_CHAT_MODES = ["chat", "plan", "edit"]
_current_mode_index = 0


def get_current_mode() -> str:
    """Return the current chat mode name."""
    return _CHAT_MODES[_current_mode_index]


def is_edit_mode() -> bool:
    """True when terminal is in accept-all-edits mode."""
    return get_current_mode() == "edit"


def is_plan_mode_active() -> bool:
    """True when terminal is in plan mode."""
    return get_current_mode() == "plan"


def cycle_mode() -> str:
    """Cycle to the next chat mode and return the new mode name."""
    global _current_mode_index
    _current_mode_index = (_current_mode_index + 1) % len(_CHAT_MODES)
    return _CHAT_MODES[_current_mode_index]


def set_mode(mode: str) -> str:
    """Set chat mode directly. Returns the mode name set."""
    global _current_mode_index
    mode_lower = mode.lower()
    if mode_lower in _CHAT_MODES:
        _current_mode_index = _CHAT_MODES.index(mode_lower)
    return get_current_mode()


# ---------------------------------------------------------------------------
# Message queue: allows typing while agent is processing
# ---------------------------------------------------------------------------


class MessageQueue:
    """Thread-safe message queue for queuing user input while agent is busy."""

    def __init__(self):
        self._queue: deque[str] = deque()
        self._lock = threading.Lock()
        self._agent_busy = threading.Event()  # set when agent is processing

    def enqueue(self, message: str) -> int:
        """Add a message to the queue. Returns queue position."""
        with self._lock:
            self._queue.append(message)
            pos = len(self._queue)
            logger.debug("Message queued at position %d: %s", pos, message[:50])
            return pos

    def dequeue(self) -> str | None:
        """Get next message from queue. Returns None if empty."""
        with self._lock:
            if self._queue:
                return self._queue.popleft()
            return None

    def peek(self) -> str | None:
        """Peek at next message without removing it."""
        with self._lock:
            return self._queue[0] if self._queue else None

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._queue) == 0

    def clear(self) -> int:
        """Clear all queued messages. Returns count of cleared messages."""
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count

    def set_agent_busy(self) -> None:
        """Mark agent as busy (processing a message)."""
        self._agent_busy.set()

    def set_agent_free(self) -> None:
        """Mark agent as free (ready for next message)."""
        self._agent_busy.clear()

    @property
    def agent_is_busy(self) -> bool:
        return self._agent_busy.is_set()

    def list_queued(self) -> list[str]:
        """List all queued messages (for display)."""
        with self._lock:
            return list(self._queue)


# Singleton
_message_queue: MessageQueue | None = None


def get_message_queue() -> MessageQueue:
    """Get the singleton message queue."""
    global _message_queue
    if _message_queue is None:
        _message_queue = MessageQueue()
    return _message_queue


# ---------------------------------------------------------------------------
# Background input reader — collects user input while agent is busy
# ---------------------------------------------------------------------------

_bg_input_thread: threading.Thread | None = None
_bg_input_stop = threading.Event()


def start_background_input(nickname: str = "you") -> None:
    """Start a background thread that reads user input into the message queue.

    Called when the agent starts streaming. The thread reads lines from stdin
    and enqueues them. The fixed input bar (terminal_layout) shows the prompt.
    """
    global _bg_input_thread, _bg_input_stop
    if _bg_input_thread and _bg_input_thread.is_alive():
        return  # already running

    _bg_input_stop.clear()
    mq = get_message_queue()

    def _reader():
        from .terminal_layout import (
            is_layout_active, draw_input_bar, move_to_input,
        )
        while not _bg_input_stop.is_set():
            try:
                if is_layout_active():
                    move_to_input()
                line = sys.stdin.readline()
                if _bg_input_stop.is_set():
                    break
                text = line.strip()
                if text:
                    pos = mq.enqueue(text)
                    logger.debug("Background input queued at position %d: %s", pos, text[:50])
                    if is_layout_active():
                        draw_input_bar(nickname=nickname, queue_size=mq.size)
            except (EOFError, OSError):
                break

    _bg_input_thread = threading.Thread(target=_reader, daemon=True, name="bg-input")
    _bg_input_thread.start()


def stop_background_input() -> None:
    """Stop the background input reader thread."""
    global _bg_input_thread
    _bg_input_stop.set()
    _bg_input_thread = None


def _load_available_models() -> list[str]:
    """Load available models from env + well-known Claude/Cursor models."""
    models = []
    # Shortcuts
    models.extend(["opus", "sonnet", "haiku"])
    # Claude model IDs
    models.extend(["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"])
    # Cursor models
    models.extend(["Composer 2 Fast", "composer 1.5"])
    # From env vars (per-agent overrides like CODE_AGENTS_MODEL_CODE_WRITER)
    for key, val in os.environ.items():
        if key.startswith("CODE_AGENTS_MODEL") and val:
            v = val.strip()
            if v and v not in models:
                models.append(v)
    # Current global model
    global_model = os.getenv("CODE_AGENTS_MODEL", "")
    if global_model and global_model not in models:
        models.append(global_model)
    cli_model = os.getenv("CODE_AGENTS_CLAUDE_CLI_MODEL", "")
    if cli_model and cli_model not in models:
        models.append(cli_model)
    return models


def _load_available_backends() -> list[str]:
    """Load available backends."""
    backends = ["cursor", "claude", "claude-cli"]
    # Per-agent overrides
    for key, val in os.environ.items():
        if key.startswith("CODE_AGENTS_BACKEND") and val:
            v = val.strip()
            if v and v not in backends:
                backends.append(v)
    return backends


def _get_toolbar():
    """Build bottom toolbar showing current mode + background tasks. shift+tab to switch."""
    if not _HAS_PT:
        return ""
    mode = get_current_mode()
    # Show only the active mode — shift+tab cycles to the next
    mode_labels = {
        "chat": "Chat",
        "plan": "Plan mode",
        "edit": "Accept edits on \u2713",
    }
    esc_hint = " \u00b7  esc to interrupt" if mode == "edit" else ""
    label = mode_labels.get(mode, mode)

    # Background tasks indicator
    bg_text = ""
    try:
        from .chat_background import get_background_manager
        bg = get_background_manager()
        tasks = bg.list_tasks()
        if tasks:
            parts = []
            for t in tasks:
                icon = "\u27f3" if t.status == "running" else "\u2713" if t.status == "done" else "\u2717"
                parts.append(f"[{t.display_name} {icon}]")
            bg_text = f" | BG: {' '.join(parts)} | Ctrl+F"
    except Exception:
        pass

    # Background agent manager indicator
    bg_agent_text = ""
    try:
        from code_agents.devops.background_agent import BackgroundAgentManager
        ba_mgr = BackgroundAgentManager.get_instance()
        ba_status = ba_mgr.get_status_bar_text()
        if ba_status:
            bg_agent_text = f" \u00b7 \u25b6\u25b6 {ba_status}"
    except Exception:
        pass

    return HTML(f"\n<toolbar> {label}{esc_hint}{bg_text}{bg_agent_text}  \u00b7  shift+tab mode \u00b7 ctrl+c clear \u00b7 ctrl+d exit</toolbar>")


# ---------------------------------------------------------------------------
# Persistent status bar — shows while agent is working (outside prompt_toolkit)
# ---------------------------------------------------------------------------

_static_bar_shown = False


def show_static_toolbar():
    """Print a static toolbar at the bottom while the agent is streaming.

    This replicates the prompt_toolkit bottom toolbar appearance so the mode
    indicator stays visible even when we're outside ``session.prompt()``.
    """
    global _static_bar_shown
    import shutil
    tw = shutil.get_terminal_size((80, 24)).columns
    mode = get_current_mode()
    mode_labels = {
        "chat": "Chat",
        "plan": "Plan mode",
        "edit": "Accept edits on \u2713",
    }
    label = mode_labels.get(mode, mode)
    hint = "shift+tab to cycle"
    # Background tasks
    bg_hint = ""
    try:
        from .chat_background import get_background_manager
        bg = get_background_manager()
        tasks = bg.list_tasks()
        if tasks:
            parts = []
            for t in tasks:
                icon = "\u27f3" if t.status == "running" else "\u2713" if t.status == "done" else "\u2717"
                parts.append(f"[{t.display_name} {icon}]")
            bg_hint = f" | BG: {' '.join(parts)}"
    except Exception:
        pass
    # Background agent manager indicator
    ba_hint = ""
    try:
        from code_agents.devops.background_agent import BackgroundAgentManager
        ba_mgr = BackgroundAgentManager.get_instance()
        ba_status = ba_mgr.get_status_bar_text()
        if ba_status:
            ba_hint = f" | {ba_status}"
    except Exception:
        pass
    bar_text = f" \u25b8\u25b8 {label} ({hint}){bg_hint}{ba_hint}"
    # Pad to terminal width, dim grey on black
    padded = bar_text.ljust(tw)
    sys.stdout.write(f"\033[2m{padded}\033[0m\n")
    sys.stdout.flush()
    _static_bar_shown = True


def clear_static_toolbar():
    """Remove the static toolbar line before re-entering prompt_toolkit."""
    global _static_bar_shown
    if _static_bar_shown:
        # Move up one line and clear it
        sys.stdout.write("\033[A\033[2K\r")
        sys.stdout.flush()
        _static_bar_shown = False


def create_session(
    history_file: str = "",
    slash_commands: list[str] = None,
    agent_names: list[str] = None,
) -> Optional["PromptSession"]:
    """Create a prompt_toolkit session with history and completion."""
    if not _HAS_PT:
        return None

    history = FileHistory(history_file) if history_file else None

    # Load models and backends from env (dynamic, not hardcoded)
    _agents = list(agent_names or [])
    _model_choices = WordCompleter(_load_available_models(), ignore_case=True)
    _backend_choices = WordCompleter(_load_available_backends(), ignore_case=True)
    _agent_choices = WordCompleter(_agents, ignore_case=True) if _agents else None

    nested: dict = {}
    for cmd in (slash_commands or []):
        if cmd == "/model":
            nested[cmd] = _model_choices
        elif cmd == "/backend":
            nested[cmd] = _backend_choices
        elif cmd == "/agent":
            nested[cmd] = _agent_choices
        elif cmd in ("/blame", "/generate-tests", "/investigate", "/review-reply", "/impact"):
            nested[cmd] = None  # free-form argument
        else:
            nested[cmd] = None
    # Agent-as-slash-command: /<agent-name> <prompt>
    for a in _agents:
        nested[f"/{a}"] = None

    completer = NestedCompleter.from_nested_dict(nested) if nested else None

    # Key bindings
    kb = KeyBindings()

    # Tab: accept auto-suggestion if showing, otherwise trigger completion
    @kb.add('tab')
    def _accept_suggestion_or_complete(event):
        buf = event.app.current_buffer
        suggestion = buf.suggestion
        if suggestion and suggestion.text:
            # Use apply_suggestion() to properly accept and clear the suggestion overlay
            buf.insert_text(suggestion.text)
            buf.suggestion = None
        else:
            # Fall through to default completion behavior
            buf.complete_next()

    # Shift+Tab cycles chat mode
    @kb.add('s-tab')
    def _cycle_mode(event):
        cycle_mode()
        event.app.invalidate()

    # Ctrl+F shows background task selector
    @kb.add('c-f')
    def _ctrl_f(event):
        try:
            from .chat_background import get_background_manager, show_task_selector
            bg = get_background_manager()
            if bg.has_tasks():
                # Insert a special command that the REPL will intercept
                event.app.current_buffer.text = "/fg"
                event.app.current_buffer.validate_and_handle()
        except Exception:
            pass

    # Ctrl+V pastes clipboard image
    @kb.add('c-v')
    def _paste_image(event):
        from .chat_clipboard import read_clipboard_image, add_pending_image
        img = read_clipboard_image()
        if img:
            count = add_pending_image(img)
            size_kb = img["size_bytes"] / 1024
            # Insert marker text so user sees the attachment
            event.app.current_buffer.insert_text(
                f"[image attached: {size_kb:.0f}KB {img['media_type']}] "
            )
        else:
            # No image in clipboard — let terminal handle normal paste
            event.app.current_buffer.paste_clipboard_data(
                event.app.clipboard.get_data()
            )

    from prompt_toolkit.styles import Style as PTStyle
    session_style = PTStyle.from_dict({
        "bottom-toolbar": "bg:default #666666 noinherit noreverse nounderline nobold",
        "bottom-toolbar.text": "bg:default #666666 noinherit noreverse nounderline nobold",
        "toolbar": "bg:default #666666 noinherit noreverse",
    })

    return PromptSession(
        history=history,
        auto_suggest=AutoSuggestFromHistory(),
        completer=completer,
        enable_history_search=True,
        mouse_support=False,
        key_bindings=kb,
        bottom_toolbar=_get_toolbar,
        style=session_style,
    )


def prompt_input(
    session: Optional["PromptSession"],
    nickname: str = "you",
    agent_name: str = "",
    role: str = "",
) -> str:
    """Get user input using prompt_toolkit or fallback to input()."""
    # Build prompt message
    role_short = role.split()[0] if role else ""
    user_tag = f"{nickname}"
    if role_short:
        user_tag += f" ({role_short})"

    if session and _HAS_PT:
        import shutil
        tw = shutil.get_terminal_size((80, 24)).columns
        bar_len = tw - len(user_tag) - 3
        # Show mode indicator in prompt when not in chat mode
        mode = get_current_mode()
        mode_indicator = f" [{mode.upper()}]" if mode != "chat" else ""
        lower_bar_len = tw - 1
        prompt_text = [
            ("class:prompt", "\u276f "),
        ]
        from prompt_toolkit.styles import Style
        style = Style.from_dict({
            "separator": "#666666",
            "user": "#00ff00 bold",
            "prompt": "#ffffff bold",
            "bottom-toolbar": "bg:default #666666 noinherit noreverse nounderline nobold",
            "bottom-toolbar.text": "bg:default #666666 noinherit noreverse nounderline nobold",
            "toolbar": "bg:default #666666 noinherit noreverse",
        })
        try:
            result = session.prompt(prompt_text, style=style)
            return result.strip()
        except KeyboardInterrupt:
            return "\x03"  # special signal for Ctrl+C
        except EOFError:
            return ""
    else:
        # Fallback to regular input
        import shutil
        tw = shutil.get_terminal_size((80, 24)).columns
        result = input("\u276f ").strip()
        print(f"\033[90m{'─' * (tw - 1)}\033[0m")
        return result


# ---------------------------------------------------------------------------
# Persistent input — patch_stdout keeps prompt visible during streaming
# ---------------------------------------------------------------------------

_patch_ctx = None


def enter_persistent_input() -> None:
    """Activate patch_stdout so prompt stays visible during agent output."""
    global _patch_ctx
    if not _HAS_PATCH_STDOUT or _patch_ctx is not None:
        return
    _patch_ctx = _patch_stdout(raw=True)
    _patch_ctx.__enter__()
    logger.debug("patch_stdout activated")


def exit_persistent_input() -> None:
    """Deactivate patch_stdout — restore normal terminal mode."""
    global _patch_ctx
    if _patch_ctx is not None:
        try:
            _patch_ctx.__exit__(None, None, None)
        except Exception:
            pass
        _patch_ctx = None
        logger.debug("patch_stdout deactivated")


async def prompt_input_async(
    session: Optional["PromptSession"],
    nickname: str = "you",
    agent_name: str = "",
    role: str = "",
) -> str:
    """Async version of prompt_input — allows concurrent output while waiting."""
    if not session or not _HAS_PT:
        # Fallback to sync input on a thread
        import asyncio
        try:
            return await asyncio.to_thread(input, "\u276f ")
        except EOFError:
            return ""

    prompt_text = [
        ("class:prompt", "\u276f "),
    ]
    from prompt_toolkit.styles import Style
    style = Style.from_dict({
        "separator": "#666666",
        "user": "#00ff00 bold",
        "prompt": "#ffffff bold",
        "bottom-toolbar": "bg:default #666666 noinherit noreverse nounderline nobold",
        "bottom-toolbar.text": "bg:default #666666 noinherit noreverse nounderline nobold",
        "toolbar": "bg:default #666666 noinherit noreverse",
    })

    try:
        result = await session.prompt_async(prompt_text, style=style)
        return result.strip()
    except KeyboardInterrupt:
        return "\x03"  # Ctrl+C signal
    except EOFError:
        return "\x04"  # Ctrl+D signal (EOF)
