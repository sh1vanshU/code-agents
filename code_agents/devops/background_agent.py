"""Background Agent Manager — manage background agent tasks with interactive panel.

Replicates Claude Code's "Background tasks" panel UI. Provides:
- BackgroundAgentManager: singleton to start/stop/list background agent tasks
- Interactive terminal panel with arrow key navigation
- Status bar text for bottom toolbar integration
- Thread-safe task management

Usage::

    from code_agents.devops.background_agent import BackgroundAgentManager, render_tasks_panel

    mgr = BackgroundAgentManager.get_instance()
    task = mgr.start_task("Implement Feature 21", "code-writer", "implement ...", execute_fn)
    print(render_tasks_panel(mgr))
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("code_agents.devops.background_agent")


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------

class AgentStatus(str, Enum):
    """Lifecycle status of a background agent task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


# ---------------------------------------------------------------------------
# BackgroundTask dataclass
# ---------------------------------------------------------------------------

@dataclass
class TaskProgress:
    """Progress tracking for a background task."""

    files_modified: list[str] = field(default_factory=list)
    tools_used: int = 0
    tokens_used: int = 0
    elapsed_seconds: float = 0.0


@dataclass
class BackgroundTask:
    """State for a single background agent task."""

    task_id: str
    name: str
    agent: str
    prompt: str
    status: AgentStatus = AgentStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    result: str = ""
    error: str = ""
    thread: threading.Thread | None = field(default=None, repr=False)
    progress: TaskProgress | None = None
    prompt_preview: str = ""  # first 200 chars of prompt

    # ---- derived helpers ----

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since task started (or since creation if not started)."""
        if self.completed_at > 0:
            return self.completed_at - (self.started_at or self.created_at)
        if self.started_at > 0:
            return time.time() - self.started_at
        return time.time() - self.created_at

    @property
    def elapsed_str(self) -> str:
        """Human readable elapsed string."""
        return _format_elapsed(self.elapsed)

    @property
    def is_active(self) -> bool:
        """True if task is pending or running."""
        return self.status in (AgentStatus.PENDING, AgentStatus.RUNNING)

    @property
    def is_terminal(self) -> bool:
        """True if task is completed, failed, or stopped."""
        return self.status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.STOPPED)

    @property
    def status_icon(self) -> str:
        """Unicode icon for current status."""
        return _STATUS_ICONS.get(self.status, "?")


_STATUS_ICONS = {
    AgentStatus.PENDING: "\u25cb",     # ○
    AgentStatus.RUNNING: "\u27f3",     # ⟳
    AgentStatus.COMPLETED: "\u2713",   # ✓
    AgentStatus.FAILED: "\u2717",      # ✗
    AgentStatus.STOPPED: "\u25a0",     # ■
}


def _format_elapsed(seconds: float) -> str:
    """Format seconds as human readable string."""
    if seconds < 0:
        return "0s"
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


# ---------------------------------------------------------------------------
# BackgroundAgentManager — singleton
# ---------------------------------------------------------------------------

def _make_progress_callback(task: BackgroundTask) -> Callable[[dict], None]:
    """Create a progress callback bound to a specific task.

    The callback accepts a dict with optional keys:
    - ``tokens``: int — token count to add
    - ``tools``: int — tool-use count to add
    - ``file``: str — file path that was modified

    This is stored as ``task._progress_cb`` so that streaming code can
    invoke it to feed live data into the detail view.
    """
    def _cb(data: dict) -> None:
        if not task.progress:
            return
        tokens = data.get("tokens", 0)
        tools = data.get("tools", 0)
        fpath = data.get("file")
        if tokens:
            task.progress.tokens_used += tokens
        if tools:
            task.progress.tools_used += tools
        if fpath and fpath not in task.progress.files_modified:
            task.progress.files_modified.append(fpath)
        task.progress.elapsed_seconds = task.elapsed

    # Attach to task so callers can retrieve it
    task._progress_cb = _cb  # type: ignore[attr-defined]
    return _cb


class BackgroundAgentManager:
    """Manages background agent tasks — start, stop, list, view results.

    Thread-safe. Uses a singleton pattern via ``get_instance()``.
    """

    _instance: BackgroundAgentManager | None = None

    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}
        self._lock = threading.Lock()
        self._counter = 0

    @classmethod
    def get_instance(cls) -> BackgroundAgentManager:
        """Get (or create) the singleton BackgroundAgentManager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    # ---- Task lifecycle ----

    def start_task(
        self,
        name: str,
        agent: str,
        prompt: str,
        execute_fn: Callable[[str, str], str],
    ) -> BackgroundTask:
        """Launch an agent task in a background thread.

        Args:
            name: Human readable task name.
            agent: Agent name to execute with.
            prompt: The prompt / instruction to execute.
            execute_fn: Callable ``(agent, prompt) -> result_string``.

        Returns:
            The created BackgroundTask.
        """
        with self._lock:
            self._counter += 1
            task_id = f"bg-{self._counter:04d}"

        task = BackgroundTask(
            task_id=task_id, name=name, agent=agent, prompt=prompt,
            progress=TaskProgress(),
            prompt_preview=prompt[:200],
        )

        def _run() -> None:
            task.status = AgentStatus.RUNNING
            task.started_at = time.time()
            logger.info("Background task %s running: %s", task_id, name)
            try:
                # Install a progress callback so execute_fn can report live data
                _progress_cb = _make_progress_callback(task)
                task.result = execute_fn(agent, prompt)
                task.status = AgentStatus.COMPLETED
                logger.info("Background task %s completed", task_id)
            except Exception as e:
                task.error = str(e)
                task.status = AgentStatus.FAILED
                logger.error("Background task %s failed: %s", task_id, e)
            finally:
                task.completed_at = time.time()
                if task.progress:
                    task.progress.elapsed_seconds = task.elapsed

        task.thread = threading.Thread(
            target=_run, daemon=True, name=f"bg-agent-{task_id}",
        )
        with self._lock:
            self._tasks[task_id] = task
        task.thread.start()
        logger.info("Started background task: %s (%s)", name, task_id)
        return task

    def update_task_progress(
        self,
        task_id: str,
        *,
        tokens_delta: int = 0,
        tools_delta: int = 0,
        file_modified: str | None = None,
    ) -> None:
        """Update live progress counters for a running background task.

        Called from streaming callbacks to feed real token/tool data into
        the task detail view.

        Args:
            task_id: The background task ID.
            tokens_delta: Number of tokens to add to the running total.
            tools_delta: Number of tool uses to add (typically 1 per tool call).
            file_modified: A file path to append to the modified files list.
        """
        with self._lock:
            task = self._tasks.get(task_id)
        if not task or not task.progress:
            return
        if tokens_delta:
            task.progress.tokens_used += tokens_delta
        if tools_delta:
            task.progress.tools_used += tools_delta
        if file_modified and file_modified not in task.progress.files_modified:
            task.progress.files_modified.append(file_modified)
        task.progress.elapsed_seconds = task.elapsed

    def stop_task(self, task_id: str) -> bool:
        """Stop a running task (sets status; thread should check ``task.status``).

        Returns True if the task was running and is now stopped.
        """
        with self._lock:
            task = self._tasks.get(task_id)
        if not task or task.status != AgentStatus.RUNNING:
            return False
        task.status = AgentStatus.STOPPED
        task.completed_at = time.time()
        logger.info("Stopped background task: %s (%s)", task.name, task_id)
        return True

    def stop_all(self) -> int:
        """Stop all running tasks. Returns count of tasks stopped."""
        count = 0
        with self._lock:
            for task in self._tasks.values():
                if task.status == AgentStatus.RUNNING:
                    task.status = AgentStatus.STOPPED
                    task.completed_at = time.time()
                    count += 1
        if count:
            logger.info("Stopped %d background tasks", count)
        return count

    def get_task(self, task_id: str) -> BackgroundTask | None:
        """Get a task by its ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, active_only: bool = False) -> list[BackgroundTask]:
        """List all tasks, optionally only active (pending/running) ones."""
        with self._lock:
            tasks = list(self._tasks.values())
        if active_only:
            tasks = [t for t in tasks if t.is_active]
        return tasks

    def active_count(self) -> int:
        """Count of running/pending tasks — used for status bar."""
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.is_active)

    def remove_completed(self) -> int:
        """Remove completed/failed/stopped tasks. Returns count removed."""
        with self._lock:
            to_remove = [
                tid for tid, t in self._tasks.items() if t.is_terminal
            ]
            for tid in to_remove:
                del self._tasks[tid]
        if to_remove:
            logger.info("Removed %d completed background tasks", len(to_remove))
        return len(to_remove)

    def remove_task(self, task_id: str) -> bool:
        """Remove a specific task by ID."""
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    # ---- Status bar ----

    def get_status_bar_text(self) -> str:
        """Returns text for the status bar: 'N local agents' or empty string."""
        count = self.active_count()
        if count == 0:
            return ""
        return f"{count} local agent{'s' if count != 1 else ''}"


# ---------------------------------------------------------------------------
# ANSI helpers (inline — no dependency on chat_ui)
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"
_ERASE_LINE = "\033[2K"
_CURSOR_UP = "\033[A"


# ---------------------------------------------------------------------------
# Static panel renderer
# ---------------------------------------------------------------------------

def render_tasks_panel(manager: BackgroundAgentManager) -> str:
    """Render the background tasks panel as a string for terminal display.

    Example output::

        Background tasks
        3 active agents

          Local agents (3)
          > Task Name (running)
            Task Name (completed) ✓
            Task Name (failed) ✗

          ↑↓ to select · Enter to view · x to stop · ctrl+x ctrl+k to stop all · Esc to close
    """
    tasks = manager.list_tasks()
    active = manager.active_count()
    total = len(tasks)

    lines: list[str] = []
    lines.append("")
    lines.append(f"  {_BOLD}{_CYAN}Background tasks{_RESET}")

    if total == 0:
        lines.append(f"  {_DIM}No background tasks.{_RESET}")
        lines.append("")
        return "\n".join(lines)

    # Summary
    active_label = f"{active} active agent{'s' if active != 1 else ''}" if active else "no active agents"
    lines.append(f"  {active_label}")
    lines.append("")

    # Group: local agents
    lines.append(f"  {_BOLD}Local agents ({total}){_RESET}")

    for i, task in enumerate(tasks):
        status_str = task.status.value
        icon = task.status_icon
        elapsed = task.elapsed_str

        if task.status == AgentStatus.RUNNING:
            name_fmt = f"{_YELLOW}{task.name}{_RESET}"
            status_fmt = f"{_YELLOW}({status_str}){_RESET}"
        elif task.status == AgentStatus.COMPLETED:
            name_fmt = f"{_GREEN}{task.name}{_RESET}"
            status_fmt = f"{_GREEN}({status_str}){_RESET}"
            icon = f"{_GREEN}{icon}{_RESET}"
        elif task.status == AgentStatus.FAILED:
            name_fmt = f"{_RED}{task.name}{_RESET}"
            status_fmt = f"{_RED}({status_str}){_RESET}"
            icon = f"{_RED}{icon}{_RESET}"
        elif task.status == AgentStatus.STOPPED:
            name_fmt = f"{_DIM}{task.name}{_RESET}"
            status_fmt = f"{_DIM}({status_str}){_RESET}"
        else:
            name_fmt = task.name
            status_fmt = f"({status_str})"

        prefix = "\u203a" if i == 0 else " "  # › for first item
        lines.append(f"  {prefix} {name_fmt} {status_fmt} {icon}  {_DIM}{elapsed}{_RESET}")

    lines.append("")
    lines.append(f"  {_DIM}\u2191\u2193 to select \u00b7 Enter to view \u00b7 x to stop \u00b7 ctrl+x ctrl+k to stop all \u00b7 \u2190/Esc to close{_RESET}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interactive panel with arrow-key navigation
# ---------------------------------------------------------------------------

def interactive_tasks_panel(manager: BackgroundAgentManager) -> str | None:
    """Interactive panel with arrow key navigation.

    Returns:
        - task_id of selected task (Enter pressed)
        - ``"stop:<task_id>"`` if x pressed on a task
        - ``"stop_all"`` if ctrl+x ctrl+k pressed
        - None on Esc / no tasks
    """
    tasks = manager.list_tasks()
    if not tasks:
        sys.stdout.write(f"\n  {_DIM}No background tasks.{_RESET}\n\n")
        sys.stdout.flush()
        return None

    # Non-TTY fallback
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        return _fallback_panel(manager)

    try:
        import tty
        import termios
    except ImportError:
        return _fallback_panel(manager)

    selected = 0
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        total_lines = _render_interactive(tasks, selected, manager)
        tty.setraw(fd)

        while True:
            key = _read_key(fd)

            if key == "up":
                selected = (selected - 1) % len(tasks)
            elif key == "down":
                selected = (selected + 1) % len(tasks)
            elif key == "enter":
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                _clear_lines(total_lines)
                # Show detail view, then return to panel
                interactive_task_detail(manager, tasks[selected].task_id)
                # Re-render panel after detail view
                tasks = manager.list_tasks()
                if not tasks:
                    sys.stdout.write(f"\n  {_DIM}No background tasks remaining.{_RESET}\n\n")
                    sys.stdout.flush()
                    return None
                if selected >= len(tasks):
                    selected = len(tasks) - 1
                total_lines = _render_interactive(tasks, selected, manager)
                tty.setraw(fd)
                continue
            elif key == "esc" or key == "left":
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                _clear_lines(total_lines)
                return None
            elif key == "x":
                # Stop selected task
                task = tasks[selected]
                if task.is_active:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    _clear_lines(total_lines)
                    return f"stop:{task.task_id}"
                # If not active, just ignore
                continue
            elif key == "ctrl_x_k":
                # Stop all
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                _clear_lines(total_lines)
                return "stop_all"
            else:
                continue

            # Re-render
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            _clear_lines(total_lines)
            # Refresh task list (statuses may have changed)
            tasks = manager.list_tasks()
            if not tasks:
                sys.stdout.write(f"\n  {_DIM}No background tasks remaining.{_RESET}\n\n")
                sys.stdout.flush()
                return None
            if selected >= len(tasks):
                selected = len(tasks) - 1
            total_lines = _render_interactive(tasks, selected, manager)
            tty.setraw(fd)

    except (KeyboardInterrupt, EOFError):
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        _clear_lines(total_lines)
        return None
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass


def _render_interactive(
    tasks: list[BackgroundTask], selected: int, manager: BackgroundAgentManager,
) -> int:
    """Render the interactive panel. Returns number of lines printed."""
    active = manager.active_count()
    total = len(tasks)
    lines: list[str] = []

    lines.append("")
    lines.append(f"  {_BOLD}{_CYAN}Background tasks{_RESET}")
    active_label = f"{active} active agent{'s' if active != 1 else ''}" if active else "no active agents"
    lines.append(f"  {active_label}")
    lines.append("")
    lines.append(f"  {_BOLD}Local agents ({total}){_RESET}")

    for i, task in enumerate(tasks):
        status_str = task.status.value
        icon = task.status_icon
        elapsed = task.elapsed_str

        # Styling per status
        if task.status == AgentStatus.RUNNING:
            name_fmt = f"{_YELLOW}{task.name}{_RESET}"
            status_fmt = f"{_YELLOW}({status_str}){_RESET}"
        elif task.status == AgentStatus.COMPLETED:
            name_fmt = f"{_GREEN}{task.name}{_RESET}"
            status_fmt = f"{_GREEN}({status_str}){_RESET}"
            icon = f"{_GREEN}{icon}{_RESET}"
        elif task.status == AgentStatus.FAILED:
            name_fmt = f"{_RED}{task.name}{_RESET}"
            status_fmt = f"{_RED}({status_str}){_RESET}"
            icon = f"{_RED}{icon}{_RESET}"
        elif task.status == AgentStatus.STOPPED:
            name_fmt = f"{_DIM}{task.name}{_RESET}"
            status_fmt = f"{_DIM}({status_str}){_RESET}"
        else:
            name_fmt = task.name
            status_fmt = f"({status_str})"

        # Selection cursor
        if i == selected:
            prefix = f"{_CYAN}\u203a{_RESET}"
        else:
            prefix = " "

        lines.append(f"  {prefix} {name_fmt} {status_fmt} {icon}  {_DIM}{elapsed}{_RESET}")

    lines.append("")
    lines.append(
        f"  {_DIM}\u2191\u2193 to select \u00b7 Enter to view \u00b7 "
        f"x to stop \u00b7 ctrl+x ctrl+k to stop all \u00b7 "
        f"\u2190/Esc to close{_RESET}"
    )
    lines.append("")

    output = "\r\n".join(lines)
    sys.stdout.write(output)
    sys.stdout.flush()
    return len(lines)


def _clear_lines(n: int) -> None:
    """Move cursor up n lines and erase each one."""
    for _ in range(n):
        sys.stdout.write(f"{_CURSOR_UP}{_ERASE_LINE}")
    sys.stdout.write("\r")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Key reading — uses os.read to bypass prompt_toolkit echo
# ---------------------------------------------------------------------------

def _read_key(fd: int) -> str:
    """Read a single keypress in raw mode. Returns key name string.

    Uses ``os.read(fd, 1)`` instead of ``sys.stdin.read(1)`` to bypass
    prompt_toolkit's stdin wrapper which can echo escape sequences when
    ``patch_stdout`` is active.
    """
    ch = os.read(fd, 1)

    if ch == b"\x1b":  # Escape sequence start
        ch2 = os.read(fd, 1)
        if ch2 == b"[":
            ch3 = os.read(fd, 1)
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
    elif ch == b"\x18":  # Ctrl+X — start of ctrl+x chord
        # Read next key for ctrl+x ctrl+k
        ch2 = os.read(fd, 1)
        if ch2 == b"\x0b":  # Ctrl+K
            return "ctrl_x_k"
        return ""
    elif ch in (b"x", b"X"):
        return "x"
    return ""


# ---------------------------------------------------------------------------
# Fallback panel (non-TTY)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Task detail view
# ---------------------------------------------------------------------------

def render_task_detail(task: BackgroundTask) -> str:
    """Render a detailed view for a single background task.

    Matches Claude Code's agent detail layout:
    - Header: agent type › task name (status)
    - Stats line: elapsed · tokens · tools
    - Progress: file list with › cursor on latest
    - Prompt: truncated original prompt
    - Controls: ← back · Esc close · x stop
    """
    lines: list[str] = []
    lines.append("")

    # Header: general-purpose › Implement Feature 21 (running)
    status_color = {
        AgentStatus.RUNNING: _YELLOW, AgentStatus.COMPLETED: _GREEN,
        AgentStatus.FAILED: _RED, AgentStatus.STOPPED: _DIM,
    }.get(task.status, "")
    lines.append(
        f"  {_BOLD}{_CYAN}{task.agent}{_RESET} {_DIM}\u203a{_RESET} "
        f"{_BOLD}{task.name}{_RESET} {status_color}({task.status.value}){_RESET}"
    )

    # Stats line: 5m 17s · 82.7k tokens · 31 tools
    stats_parts = [task.elapsed_str]
    if task.progress:
        if task.progress.tokens_used:
            tk = task.progress.tokens_used
            tk_str = f"{tk / 1000:.1f}k" if tk >= 1000 else str(tk)
            stats_parts.append(f"{tk_str} tokens")
        if task.progress.tools_used:
            stats_parts.append(f"{task.progress.tools_used} tools")
    lines.append(f"  {_DIM}{' \u00b7 '.join(stats_parts)}{_RESET}")
    lines.append("")

    # Progress: file list with › on latest modified file
    if task.progress and task.progress.files_modified:
        lines.append(f"  {_BOLD}Progress{_RESET}")
        files = task.progress.files_modified
        for i, f in enumerate(files[-15:]):  # show last 15
            if i == len(files[-15:]) - 1 and task.is_active:
                # Latest file gets › cursor
                lines.append(f"  {_CYAN}\u203a{_RESET} {_BOLD}{f}{_RESET}")
            else:
                prefix = f"  {_GREEN}\u2713{_RESET}" if not task.is_active else f"    "
                lines.append(f"{prefix} {_DIM}{f}{_RESET}")
        if len(files) > 15:
            lines.append(f"    {_DIM}... ({len(files) - 15} more){_RESET}")
        lines.append("")

    # Prompt preview
    if task.prompt_preview:
        lines.append(f"  {_BOLD}Prompt{_RESET}")
        # Show first 4 lines of prompt, truncated
        prompt_lines = task.prompt_preview.splitlines()
        for pl in prompt_lines[:4]:
            lines.append(f"  {_DIM}{pl[:100]}{_RESET}")
        if len(prompt_lines) > 4:
            lines.append(f"  {_DIM}...{_RESET}")
        lines.append("")

    # Result preview (only when completed)
    if task.result and task.is_terminal:
        lines.append(f"  {_BOLD}Result{_RESET}")
        for line in task.result.splitlines()[:10]:
            lines.append(f"    {line[:120]}")
        if len(task.result.splitlines()) > 10:
            lines.append(f"    {_DIM}... ({len(task.result.splitlines()) - 10} more lines){_RESET}")
        lines.append("")

    # Error
    if task.error:
        lines.append(f"  {_RED}{_BOLD}Error:{_RESET} {_RED}{task.error[:200]}{_RESET}")
        lines.append("")

    # Controls
    lines.append(f"  {_DIM}\u2190 to go back \u00b7 Esc/Enter/Space to close \u00b7 x to stop{_RESET}")
    lines.append("")

    return "\n".join(lines)


def interactive_task_detail(manager: BackgroundAgentManager, task_id: str) -> None:
    """Interactive detail view for a specific task with live auto-refresh.

    Shows detailed info that updates every second while the task is running.
    Called when user presses Enter on a task in the panel.

    Controls: ← back, Esc/Enter/Space close, x stop
    """
    import select

    task = manager.get_task(task_id)
    if not task:
        sys.stdout.write(f"\n  {_DIM}Task {task_id} not found.{_RESET}\n\n")
        sys.stdout.flush()
        return

    # Non-TTY: just print
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        sys.stdout.write(render_task_detail(task))
        sys.stdout.flush()
        return

    try:
        import tty
        import termios
    except ImportError:
        sys.stdout.write(render_task_detail(task))
        sys.stdout.flush()
        return

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    refresh_interval = 1.0  # auto-refresh every second for live stats

    try:
        detail = render_task_detail(task)
        total_lines = detail.count("\n") + 1
        sys.stdout.write(detail)
        sys.stdout.flush()
        tty.setraw(fd)

        while True:
            # Wait for keypress OR timeout (auto-refresh for live tasks)
            ready, _, _ = select.select([fd], [], [], refresh_interval if task.is_active else 60)

            if ready:
                key = _read_key(fd)
                if key in ("esc", "left", "enter", " "):
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    _clear_lines(total_lines)
                    return
                elif key == "x":
                    if task.is_active:
                        manager.stop_task(task_id)
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    _clear_lines(total_lines)
                    return

            # Auto-refresh: re-render with updated stats
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            _clear_lines(total_lines)
            task = manager.get_task(task_id)
            if not task:
                return
            detail = render_task_detail(task)
            total_lines = detail.count("\n") + 1
            sys.stdout.write(detail)
            sys.stdout.flush()
            tty.setraw(fd)

    except (KeyboardInterrupt, EOFError):
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        _clear_lines(total_lines)
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Fallback panel (non-TTY)
# ---------------------------------------------------------------------------

def _fallback_panel(manager: BackgroundAgentManager) -> str | None:
    """Simple numbered list fallback for non-TTY environments."""
    tasks = manager.list_tasks()
    if not tasks:
        print(f"\n  No background tasks.\n")
        return None

    print(f"\n  Background tasks ({len(tasks)}):\n")
    for i, task in enumerate(tasks, 1):
        icon = task.status_icon
        print(f"  {i}. {task.name} ({task.status.value}) {icon}  {task.elapsed_str}")
    print()
    print("  Enter number to view, 's' to stop, 'q' to cancel:")

    try:
        choice = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None

    if choice == "q" or not choice:
        return None
    if choice == "s":
        return "stop_all"
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(tasks):
            return tasks[idx].task_id
    except ValueError:
        pass
    return None
