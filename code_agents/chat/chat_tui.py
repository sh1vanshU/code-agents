"""Backward-compat shim — TUI moved to code_agents.chat.tui package.

Replaces the prompt_toolkit REPL with a full terminal UI:
  - Top: scrolling output (agent responses, command results)
  - Bottom: fixed input box (always visible, always functional)
  - Footer: status bar (mode, keyboard hints)

Uses Textual's CSS layout with Rich rendering for markdown, tables,
and syntax highlighting.

Enable with: CODE_AGENTS_TUI=1 code-agents chat
"""
from __future__ import annotations

import io
import logging
import os
import sys
import time as _time_mod
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Input, RichLog, Static

logger = logging.getLogger("code_agents.chat.chat_tui")


# ---------------------------------------------------------------------------
# Stdout proxy — redirects print/write to RichLog widget
# ---------------------------------------------------------------------------

class _RichLogProxy(io.TextIOBase):
    """Proxy that captures sys.stdout writes and sends them to a RichLog widget."""

    def __init__(self, richlog: RichLog, app: "ChatTUI"):
        self._richlog = richlog
        self._app = app
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        self._buffer += text
        # Flush complete lines to RichLog
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            # Strip ANSI escape codes for RichLog (it uses Rich markup)
            clean = _strip_ansi(line)
            if clean.strip():
                try:
                    self._app.call_from_thread(self._richlog.write, clean)
                except Exception:
                    pass
        return len(text)

    def flush(self) -> None:
        if self._buffer.strip():
            clean = _strip_ansi(self._buffer)
            if clean.strip():
                try:
                    self._app.call_from_thread(self._richlog.write, clean)
                except Exception:
                    pass
            self._buffer = ""

    def isatty(self) -> bool:
        return True

    @property
    def encoding(self) -> str:
        return "utf-8"


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text."""
    import re
    return re.sub(r'\033\[[0-9;]*[a-zA-Z]', '', text)


# ---------------------------------------------------------------------------
# Chat TUI App
# ---------------------------------------------------------------------------

class ChatTUI(App):
    """Full-screen chat interface with persistent input."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #output {
        height: 1fr;
        min-height: 10;
        scrollbar-size: 1 1;
        padding: 0 1;
        background: $surface;
    }
    #input-box {
        height: 3;
        padding: 0 1;
        border-top: heavy $primary;
    }
    #input-field {
        height: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "quit_chat", "Exit", show=True),
        Binding("shift+tab", "cycle_mode", "Cycle mode", show=True),
    ]

    def __init__(
        self,
        *,
        state: dict,
        url: str,
        cwd: str,
        nickname: str,
        agent_name: str,
        session_start: float,
    ):
        super().__init__()
        self.chat_state = state
        self.chat_url = url
        self.chat_cwd = cwd
        self.nickname = nickname
        self.agent_name = agent_name
        self.session_start = session_start
        self._session_messages = 0
        self._session_commands = 0
        self._mode = "chat"
        self._modes = ["chat", "plan", "edit"]
        self._agent_busy = False
        self._queued_messages: list[str] = []

    def compose(self) -> ComposeResult:
        yield RichLog(id="output", wrap=True, markup=True, highlight=True, auto_scroll=True)
        with Vertical(id="input-box"):
            yield Input(id="input-field", placeholder=f"{self.nickname} › Type your message...")
        yield Footer()

    def on_mount(self) -> None:
        """Show welcome info on startup."""
        output = self.query_one("#output", RichLog)

        try:
            from .chat_welcome import AGENT_ROLES
            role = AGENT_ROLES.get(self.agent_name, "")
        except Exception:
            role = ""

        output.write(f"[bold cyan]═══ Code Agents Chat ═══[/]")
        output.write("")
        output.write(f"  [bold]Agent:[/]  {self.agent_name}")
        if role:
            output.write(f"  [dim]Role:[/]   {role}")
        output.write(f"  [dim]Dir:[/]    {self.chat_cwd}")
        output.write(f"  [dim]Server:[/] {self.chat_url}")
        output.write("")
        output.write("[dim]  /help · /quit · /agents · /history · Esc to exit[/]")
        output.write("")

        self._update_sub_title()
        self.query_one("#input-field", Input).focus()

    def _update_sub_title(self) -> None:
        mode_labels = {"chat": "Chat", "plan": "Plan mode", "edit": "Accept edits"}
        label = mode_labels.get(self._mode, self._mode)
        busy = " · streaming..." if self._agent_busy else ""
        queued = f" · {len(self._queued_messages)} queued" if self._queued_messages else ""
        self.sub_title = f"▸▸ {label} (shift+tab){busy}{queued}"

    def action_cycle_mode(self) -> None:
        idx = self._modes.index(self._mode)
        self._mode = self._modes[(idx + 1) % len(self._modes)]
        self._update_sub_title()
        output = self.query_one("#output", RichLog)
        output.write(f"  [green]✓ Mode: {self._mode}[/]")

    def action_quit_chat(self) -> None:
        self._print_summary()
        self.exit()

    def _print_summary(self) -> None:
        output = self.query_one("#output", RichLog)
        elapsed = _time_mod.monotonic() - self.session_start
        if elapsed < 60:
            dur = f"{elapsed:.0f}s"
        elif elapsed < 3600:
            m, s = divmod(int(elapsed), 60)
            dur = f"{m}m {s:02d}s"
        else:
            h, r = divmod(int(elapsed), 3600)
            m, s = divmod(r, 60)
            dur = f"{h}h {m:02d}m"

        output.write("")
        output.write("[bold cyan]━━━ Session Summary ━━━━━━━━━━━━━━━[/]")
        output.write(f"  Agent:    {self.agent_name}")
        output.write(f"  Messages: {self._session_messages}")
        output.write(f"  Commands: {self._session_commands}")
        output.write(f"  Duration: {dur}")
        output.write("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission."""
        user_input = event.value.strip()
        input_widget = self.query_one("#input-field", Input)
        input_widget.value = ""

        if not user_input:
            return

        output = self.query_one("#output", RichLog)

        if self._agent_busy:
            self._queued_messages.append(user_input)
            output.write(f"  [dim]⟫ Message queued (position {len(self._queued_messages)})[/]")
            self._update_sub_title()
            return

        output.write(f"[bold green]  {self.nickname}[/] › {user_input}")

        if user_input.startswith("/"):
            await self._handle_slash(user_input, output)
            return

        self._session_messages += 1
        self._process_message(user_input)

    @work(thread=True)
    def _process_message(self, user_input: str) -> None:
        """Process user message — runs in background thread."""
        output = self.query_one("#output", RichLog)
        self._agent_busy = True
        self.call_from_thread(self._update_sub_title)

        # Redirect stdout to RichLog so streaming output appears in the widget
        _original_stdout = sys.stdout
        _proxy = _RichLogProxy(output, self)
        sys.stdout = _proxy

        try:
            from . import chat as _chat_mod
            from .chat_response import process_streaming_response, handle_post_response
            from .chat_repl import run_agentic_followup_loop

            current_agent = self.chat_state["agent"]
            system_context = _chat_mod._build_system_context(
                self.chat_state.get("repo_path", self.chat_cwd),
                current_agent,
                btw_messages=self.chat_state.get("_btw_messages", []),
                superpower=self.chat_state.get("superpower", False),
            )

            messages = [{"role": "system", "content": system_context}]
            chat_session = self.chat_state.get("_chat_session")
            if chat_session and chat_session.get("messages"):
                for hist_msg in chat_session["messages"]:
                    if hist_msg.get("role") in ("user", "assistant"):
                        messages.append({"role": hist_msg["role"], "content": hist_msg["content"]})

            if not messages or messages[-1].get("content") != user_input:
                messages.append({"role": "user", "content": user_input})

            if not self.chat_state.get("_chat_session"):
                from .chat_history import create_session
                self.chat_state["_chat_session"] = create_session(current_agent, self.chat_state.get("repo_path", ""))
            from .chat_history import add_message as _add_msg
            _add_msg(self.chat_state["_chat_session"], "user", user_input)

            _ctrl_c_ref = [_chat_mod._last_ctrl_c]
            try:
                got_text, full_response, interrupted = process_streaming_response(
                    self.chat_url, current_agent, messages, self.chat_state,
                    _last_ctrl_c_ref=_ctrl_c_ref,
                )
            except KeyboardInterrupt:
                self.call_from_thread(lambda: output.write("[yellow]  Response interrupted.[/]"))
                return

            _chat_mod._last_ctrl_c = _ctrl_c_ref[0]
            full_text = "".join(full_response) if full_response else ""

            if full_text:
                from code_agents.core.logging_config import log_agent_response
                _out_tokens = self.chat_state.get("_last_usage", {}).get("output_tokens", 0) if self.chat_state.get("_last_usage") else 0
                log_agent_response(current_agent, full_text, tokens=_out_tokens)

            if not interrupted:
                full_response, effective_agent = handle_post_response(
                    full_response, user_input, self.chat_state, self.chat_url,
                    current_agent, system_context, self.chat_cwd,
                )
                _, extra_cmds = run_agentic_followup_loop(
                    full_response=full_response,
                    cwd=self.chat_cwd,
                    url=self.chat_url,
                    state=self.chat_state,
                    current_agent=current_agent,
                    effective_agent=effective_agent,
                    system_context=system_context,
                    superpower=self.chat_state.get("superpower", False),
                )
                self._session_commands += extra_cmds

        except Exception as e:
            logger.error("Processing error: %s", e, exc_info=True)
            self.call_from_thread(lambda: output.write(f"[red]  Error: {e}[/]"))

        finally:
            # Restore stdout
            sys.stdout = _original_stdout
            _proxy.flush()

            self._agent_busy = False
            self.call_from_thread(self._update_sub_title)

            if self._queued_messages:
                next_msg = self._queued_messages.pop(0)
                self.call_from_thread(self._update_sub_title)
                self.call_from_thread(lambda: output.write("[dim]  ⟫ Processing queued message[/]"))
                self._process_message(next_msg)

    async def _handle_slash(self, user_input: str, output: RichLog) -> None:
        if user_input in ("/quit", "/exit", "/q"):
            self._print_summary()
            self.exit()
            return

        if user_input == "/help":
            output.write("[bold]  Available commands:[/]")
            output.write("    /quit, /exit    — Exit chat")
            output.write("    /agent <name>   — Switch agent")
            output.write("    /agents         — List agents")
            output.write("    /history        — List sessions")
            output.write("    /clear          — Clear output")
            output.write("    /sandbox on|off — Toggle sandbox")
            output.write("")
            return

        if user_input == "/clear":
            output.clear()
            return

        if user_input.startswith("/agent "):
            agent = user_input.split(None, 1)[1].strip()
            self.chat_state["agent"] = agent
            self.agent_name = agent
            output.write(f"  [green]✓ Switched to {agent}[/]")
            return

        # Delegate to existing handler (runs sync operations)
        try:
            from . import chat as _chat_mod
            result = _chat_mod._handle_command(user_input, self.chat_state, self.chat_url)
            if result == "quit":
                self._print_summary()
                self.exit()
        except Exception as e:
            output.write(f"  [red]Command error: {e}[/]")


def run_chat_tui(
    *,
    state: dict,
    url: str,
    cwd: str,
    nickname: str,
    agent_name: str,
    session_start: float,
) -> None:
    """Launch the Textual chat TUI."""
    app = ChatTUI(
        state=state,
        url=url,
        cwd=cwd,
        nickname=nickname,
        agent_name=agent_name,
        session_start=session_start,
    )
    app.run()
