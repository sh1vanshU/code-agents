"""Background task management — push running tasks to background, continue working.

Provides:
- OutputTarget: switchable stdout/buffer for capturing output mid-stream
- BackgroundTask: task state (running, done, error)
- BackgroundTaskManager: singleton manager with max concurrent limit
- Ctrl+B listener: raw stdin detection for backgrounding
- Desktop notification on completion
- Scratchpad merge on foreground
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_background")


# ---------------------------------------------------------------------------
# OutputTarget — switchable stdout / buffer
# ---------------------------------------------------------------------------

class OutputTarget:
    """Routes writes to stdout or an internal buffer.

    Starts writing to stdout.  On Ctrl+B, call ``redirect_to_buffer()`` to
    capture all subsequent output.  On ``/fg``, call ``restore_to_stdout()``
    to resume live output, or ``get_buffer()`` to replay buffered content.
    """

    def __init__(self):
        self._target: Optional[object] = sys.stdout  # stdout or None (buffering)
        self._buffer: list[str] = []
        self._lock = threading.Lock()

    def write(self, text: str) -> None:
        """Write to current target (stdout or buffer)."""
        with self._lock:
            if self._target is not None:
                self._target.write(text)
                self._target.flush()
            else:
                self._buffer.append(text)

    def flush(self) -> None:
        """Flush stdout if targeting it."""
        with self._lock:
            if self._target is not None:
                self._target.flush()

    def redirect_to_buffer(self) -> None:
        """Switch from stdout to internal buffer (called on Ctrl+B)."""
        with self._lock:
            self._target = None

    def restore_to_stdout(self) -> None:
        """Switch back to stdout (called on /fg for running tasks)."""
        with self._lock:
            self._target = sys.stdout

    def get_buffer(self) -> str:
        """Return all buffered output as a single string."""
        with self._lock:
            return "".join(self._buffer)

    @property
    def is_buffering(self) -> bool:
        """True when output is going to buffer instead of stdout."""
        with self._lock:
            return self._target is None


# ---------------------------------------------------------------------------
# Task naming
# ---------------------------------------------------------------------------

def generate_task_name(agent_name: str, user_input: str) -> str:
    """Auto-generate readable task name from agent + prompt.

    Examples:
        "build and deploy pg-acquiring-biz to dev" -> "build:pg-acquiring-biz"
        "run tests for payment-service" -> "test:payment-service"
        "explain the auth module" -> "task:code-reasoning"
    """
    input_lower = user_input.lower()

    # Extract action
    action = "task"
    for word in ["build", "deploy", "review", "test", "analyze", "check",
                 "run", "investigate", "search", "create", "fix", "debug"]:
        if word in input_lower:
            action = word
            break

    # Extract target (repo name, file, etc.)
    words = user_input.split()
    target = ""
    for w in words:
        # Likely a repo name like pg-acquiring-biz or payment-service
        if "-" in w and len(w) > 5:
            target = w.strip(".,;:\"'()[]")
            break
        # Likely a file path
        if "/" in w and "http" not in w:
            target = w.split("/")[-1].strip(".,;:\"'()[]")
            break

    return f"{action}:{target}" if target else f"{action}:{agent_name}"


# ---------------------------------------------------------------------------
# BackgroundTask
# ---------------------------------------------------------------------------

@dataclass
class BackgroundTask:
    """State for a single backgrounded task."""

    task_id: int
    display_name: str               # "build:pg-acquiring-biz"
    agent_name: str                 # "jenkins-cicd"
    user_input: str                 # original prompt
    status: str = "running"         # "running" | "done" | "error"
    state: dict = field(default_factory=dict)  # deep copy of session state
    output_target: OutputTarget = field(default_factory=OutputTarget)
    streaming_task: Optional[object] = None  # asyncio.Task wrapping the thread
    started_at: float = field(default_factory=time.monotonic)
    scratchpad_session_id: str = ""

    # Results (populated on completion)
    full_response: Optional[list[str]] = None
    error: Optional[str] = None
    result_summary: str = ""        # "Build #916 SUCCESS"

    # Messages snapshot for resuming conversation
    messages: Optional[list[dict]] = None
    system_context: str = ""

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def elapsed_str(self) -> str:
        return _format_elapsed(self.elapsed)


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


# ---------------------------------------------------------------------------
# BackgroundTaskManager — singleton
# ---------------------------------------------------------------------------

class BackgroundTaskManager:
    """Manages background tasks with a configurable concurrency limit."""

    def __init__(self):
        self._tasks: dict[int, BackgroundTask] = {}
        self._next_id: int = 1
        self._max_concurrent: int = int(
            os.getenv("CODE_AGENTS_MAX_BACKGROUND", "3")
        )
        self._lock = threading.Lock()
        self._on_complete_callbacks: list = []

    def create_task(
        self,
        agent_name: str,
        user_input: str,
        state: dict,
        output_target: OutputTarget,
        *,
        scratchpad_session_id: str = "",
        messages: Optional[list[dict]] = None,
        system_context: str = "",
    ) -> BackgroundTask:
        """Create and register a new background task."""
        with self._lock:
            task_id = self._next_id
            self._next_id += 1

        display_name = generate_task_name(agent_name, user_input)
        task = BackgroundTask(
            task_id=task_id,
            display_name=display_name,
            agent_name=agent_name,
            user_input=user_input,
            state=state,
            output_target=output_target,
            scratchpad_session_id=scratchpad_session_id,
            messages=messages,
            system_context=system_context,
        )
        with self._lock:
            self._tasks[task_id] = task

        logger.info("Background task #%d created: %s", task_id, display_name)
        return task

    def get_task(self, task_id: int) -> Optional[BackgroundTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[BackgroundTask]:
        with self._lock:
            return list(self._tasks.values())

    def remove_task(self, task_id: int) -> None:
        with self._lock:
            self._tasks.pop(task_id, None)

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.status == "running")

    def can_create(self) -> bool:
        return self.active_count() < self._max_concurrent

    def has_tasks(self) -> bool:
        with self._lock:
            return len(self._tasks) > 0

    def done_tasks(self) -> list[BackgroundTask]:
        with self._lock:
            return [t for t in self._tasks.values() if t.status in ("done", "error")]

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent


# Singleton
_bg_manager: Optional[BackgroundTaskManager] = None


def get_background_manager() -> BackgroundTaskManager:
    """Get (or create) the singleton BackgroundTaskManager."""
    global _bg_manager
    if _bg_manager is None:
        _bg_manager = BackgroundTaskManager()
    return _bg_manager


# ---------------------------------------------------------------------------
# Ctrl+B listener — raw stdin detection
# ---------------------------------------------------------------------------

_ctrl_b_event: Optional[threading.Event] = None
_ctrl_b_thread: Optional[threading.Thread] = None
_ctrl_b_stop: Optional[threading.Event] = None


def start_ctrl_b_listener() -> threading.Event:
    """Start a raw stdin listener that sets an event on Ctrl+B (\\x02).

    Returns the Event that gets set when Ctrl+B is pressed.
    Only active while agent is streaming.
    """
    global _ctrl_b_event, _ctrl_b_thread, _ctrl_b_stop

    _ctrl_b_event = threading.Event()
    _ctrl_b_stop = threading.Event()

    # Capture in local var to avoid race with stop_ctrl_b_listener() setting global to None
    stop_event = _ctrl_b_stop

    def _listen():
        import tty
        import termios
        try:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
        except (ValueError, OSError, termios.error):
            return
        try:
            tty.setcbreak(fd)
            while not stop_event.is_set():
                # Non-blocking read with select
                import select
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if ready:
                    ch = sys.stdin.read(1)
                    if ch == "\x02":  # Ctrl+B
                        _ctrl_b_event.set()
                        break
                    elif ch == "\x06":  # Ctrl+F
                        # Store Ctrl+F as a separate signal
                        _ctrl_b_event._ctrl_f = True  # type: ignore[attr-defined]
                        _ctrl_b_event.set()
                        break
        except (OSError, ValueError):
            pass
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except (OSError, ValueError, termios.error):
                pass

    _ctrl_b_thread = threading.Thread(target=_listen, daemon=True, name="ctrl-b-listener")
    _ctrl_b_thread.start()
    return _ctrl_b_event


def stop_ctrl_b_listener() -> None:
    """Stop the Ctrl+B listener thread."""
    global _ctrl_b_thread, _ctrl_b_stop
    if _ctrl_b_stop:
        _ctrl_b_stop.set()
    _ctrl_b_thread = None
    _ctrl_b_stop = None


# ---------------------------------------------------------------------------
# Desktop notification
# ---------------------------------------------------------------------------

def send_desktop_notification(task: BackgroundTask) -> None:
    """Send macOS desktop notification when a background task completes."""
    import platform
    if platform.system() != "Darwin":
        return
    import subprocess
    title = f"code-agents: {task.display_name}"
    message = task.result_summary or f"Task {task.status}"
    # Escape quotes for osascript
    title = title.replace('"', '\\"')
    message = message.replace('"', '\\"')
    try:
        subprocess.Popen(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}" sound name "Glass"'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    # Terminal bell
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Scratchpad merge
# ---------------------------------------------------------------------------

def merge_scratchpad(bg_session_id: str, main_state: dict) -> None:
    """Merge background task's scratchpad discoveries into main session."""
    try:
        from code_agents.agent_system.session_scratchpad import SessionScratchpad
    except ImportError:
        return

    main_session_id = (main_state.get("_chat_session") or {}).get("id")
    if not main_session_id or not bg_session_id:
        return

    bg_sp = SessionScratchpad(bg_session_id)
    main_sp = SessionScratchpad(main_session_id)

    bg_facts = bg_sp.get_all()
    for key, value in bg_facts.items():
        main_sp.set(key, value)

    if bg_facts:
        logger.info(
            "Merged %d scratchpad facts from bg session %s into main %s",
            len(bg_facts), bg_session_id, main_session_id,
        )


# ---------------------------------------------------------------------------
# Task selector (Ctrl+F / /fg)
# ---------------------------------------------------------------------------

def show_task_selector(bg_manager: BackgroundTaskManager) -> Optional[BackgroundTask]:
    """Show interactive selector for background tasks.

    Returns the selected task, or None if cancelled / no tasks.
    """
    from .chat_ui import dim, bold, yellow, green, red, _tab_selector

    tasks = bg_manager.list_tasks()
    if not tasks:
        print(dim("  No background tasks."))
        return None

    options = []
    for t in tasks:
        elapsed = _format_elapsed(t.elapsed)
        if t.status == "running":
            icon = "\u27f3"  # ⟳
        elif t.status == "done":
            icon = "\u2713"  # ✓
        else:
            icon = "\u2717"  # ✗
        summary = t.result_summary or t.user_input[:40]
        options.append(f"{t.display_name} ({t.status}, {elapsed}) {icon} \u2014 {summary}")
    options.append("Back to prompt")

    choice = _tab_selector("Switch to background task:", options, default=0)
    if choice < 0 or choice == len(options) - 1:
        return None
    return tasks[choice]


# ---------------------------------------------------------------------------
# Bring task to foreground
# ---------------------------------------------------------------------------

def bring_to_foreground(task: BackgroundTask, main_state: dict, url: str, cwd: str) -> None:
    """Bring a background task to the foreground.

    For done tasks: replay buffer, merge scratchpad, run post-response.
    For running tasks: swap output back to stdout, block until done.
    """
    from .chat_ui import dim, green, yellow, red
    from .chat_response import handle_post_response
    from .chat_repl import run_agentic_followup_loop

    bg_manager = get_background_manager()

    if task.status == "done":
        # Replay buffered output
        buffered = task.output_target.get_buffer()
        if buffered:
            print(dim(f"\n  \u2500\u2500 Replaying {task.display_name} \u2500\u2500"))
            sys.stdout.write(buffered)
            sys.stdout.flush()
            print()

        # Merge scratchpad into main session
        if task.scratchpad_session_id:
            merge_scratchpad(task.scratchpad_session_id, main_state)

        # Run post-response handling if not already run
        if task.full_response:
            task.full_response, effective_agent = handle_post_response(
                task.full_response, task.user_input, main_state, url,
                task.agent_name, task.system_context, cwd,
            )
            # Agentic follow-up loop
            run_agentic_followup_loop(
                full_response=task.full_response,
                cwd=cwd,
                url=url,
                state=main_state,
                current_agent=task.agent_name,
                effective_agent=effective_agent,
                system_context=task.system_context,
                superpower=main_state.get("superpower", False),
            )

        # Save to main chat history
        if task.full_response and main_state.get("_chat_session"):
            from .chat_history import add_message
            add_message(main_state["_chat_session"], "user", task.user_input)
            add_message(main_state["_chat_session"], "assistant", "".join(task.full_response))

        bg_manager.remove_task(task.task_id)
        print(green(f"  \u2713 Task #{task.task_id} {task.display_name} completed and merged."))
        print()

    elif task.status == "running":
        # Swap output back to stdout
        task.output_target.restore_to_stdout()
        print(dim(f"  Resuming {task.display_name}..."))
        # The streaming task is still running — it will now output to stdout
        # The caller (REPL) should await the streaming_task
        # We don't block here — the REPL handles this

    elif task.status == "error":
        # Show error
        buffered = task.output_target.get_buffer()
        if buffered:
            sys.stdout.write(buffered)
            sys.stdout.flush()
        if task.error:
            print(red(f"  Error: {task.error}"))
        bg_manager.remove_task(task.task_id)
        print()


# ---------------------------------------------------------------------------
# Background completion callback
# ---------------------------------------------------------------------------

def on_background_complete(
    task: BackgroundTask,
    got_text: bool,
    full_response: list[str],
    streaming_interrupted: bool,
) -> None:
    """Called when a background streaming task finishes."""
    from .chat_ui import dim, green, yellow

    if streaming_interrupted:
        task.status = "error"
        task.error = "Interrupted"
    elif full_response:
        task.status = "done"
        task.full_response = full_response
        # Extract a brief summary from the response
        full_text = "".join(full_response)
        # Look for common result patterns
        for line in full_text.splitlines():
            line = line.strip()
            if any(kw in line.upper() for kw in ["SUCCESS", "FAILED", "ERROR", "BUILD #", "DEPLOYED"]):
                task.result_summary = line[:80]
                break
        if not task.result_summary:
            task.result_summary = full_text[:60].replace("\n", " ")
    else:
        task.status = "error"
        task.error = "No response received"

    # Handle [REMEMBER:] tags in background
    if task.full_response:
        try:
            from code_agents.agent_system.session_scratchpad import extract_remember_tags
            full_text = "".join(task.full_response)
            pairs = extract_remember_tags(full_text)
            if pairs and task.scratchpad_session_id:
                from code_agents.agent_system.session_scratchpad import SessionScratchpad
                sp = SessionScratchpad(task.scratchpad_session_id, task.agent_name)
                for key, value in pairs:
                    sp.set(key, value)
        except Exception:
            pass

    # Desktop notification
    send_desktop_notification(task)

    # Print hint (may appear mid-prompt but that's acceptable)
    try:
        icon = "\u2713" if task.status == "done" else "\u2717"
        summary = task.result_summary or task.status
        hint = f"\n  \U0001f514 Background task done: {task.display_name} {icon} \u2014 {summary}"
        hint += f"\n  {dim('Ctrl+F to view')}\n"
        sys.stdout.write(hint)
        sys.stdout.flush()
    except Exception:
        pass

    logger.info(
        "Background task #%d %s completed: %s",
        task.task_id, task.display_name, task.status,
    )
