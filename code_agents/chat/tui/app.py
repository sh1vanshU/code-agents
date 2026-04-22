"""Textual TUI App for Code Agents chat — Claude Code-style interface."""

from __future__ import annotations

import logging
import sys
import time as _time_mod

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual import work

from .css import CHAT_TUI_CSS
from .widgets import ChatOutput, ChatInput, StatusBar, ThinkingIndicator

logger = logging.getLogger("code_agents.chat.tui")


class ChatTUI(App):
    """Code Agents chat — Textual terminal UI."""

    TITLE = "Code Agents"
    CSS = CHAT_TUI_CSS

    BINDINGS = [
        Binding("escape", "interrupt_or_quit", "Interrupt / Exit", show=True),
        Binding("shift+tab", "cycle_mode", "Cycle mode", show=False),
    ]

    def __init__(
        self,
        *,
        state: dict,
        url: str,
        cwd: str,
        nickname: str = "you",
        agent_name: str = "",
        session_start: float = 0.0,
    ):
        super().__init__()
        self.chat_state = state
        self.chat_url = url
        self.chat_cwd = cwd
        self.nickname = nickname
        self.agent_name = agent_name or state.get("agent", "auto-pilot")
        self.session_start = session_start or _time_mod.monotonic()

        self._session_messages = 0
        self._session_commands = 0
        self._agent_busy = False
        self._queued_messages: list[str] = []
        self._modes = ["chat", "plan", "edit"]
        self._mode = "chat"
        self._bridge = None
        self._cancel_requested = False

    # -------------------------------------------------------------------
    # Compose
    # -------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield ChatOutput(id="chat-output")
        with Vertical(id="input-container"):
            yield ChatInput(placeholder=f"Send a message...")
        yield StatusBar(id="status-bar")

    # -------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------

    def on_mount(self) -> None:
        """Show welcome and install bridge."""
        # Install pipeline bridge (patches interactive terminal calls)
        from .bridge import TUIBridge
        self._bridge = TUIBridge(self)
        self._bridge.install()

        output = self.query_one(ChatOutput)

        try:
            from ..chat_welcome import AGENT_ROLES
            role = AGENT_ROLES.get(self.agent_name, "")
        except Exception:
            role = ""

        output.write("[bold cyan]═══ Code Agents Chat ═══[/]")
        output.write("")
        output.write(f"  [bold]Agent:[/]  {self.agent_name}")
        if role:
            output.write(f"  [dim]Role:[/]   {role}")
        output.write(f"  [dim]Dir:[/]    {self.chat_cwd}")
        output.write(f"  [dim]Server:[/] {self.chat_url}")
        output.write("")
        output.write("[dim]  /help · /quit · /agents · /history · Esc to exit[/]")
        output.write("")

        self._update_status()
        self.query_one(ChatInput).focus()

    def on_unmount(self) -> None:
        if self._bridge:
            self._bridge.uninstall()

    # -------------------------------------------------------------------
    # Status updates
    # -------------------------------------------------------------------

    def _update_status(self, thinking: str = "") -> None:
        status = self.query_one(StatusBar)
        status.mode = self._mode
        status.agent_busy = self._agent_busy
        status.thinking_label = thinking

    # -------------------------------------------------------------------
    # Input handling
    # -------------------------------------------------------------------

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        """Handle user message submission."""
        user_input = event.value.strip()
        if not user_input:
            return

        output = self.query_one(ChatOutput)

        # Queue if agent is busy
        if self._agent_busy:
            self._queued_messages.append(user_input)
            output.write(f"[dim]  ⟫ Message queued (position {len(self._queued_messages)})[/]")
            return

        # Slash commands
        if user_input.startswith("/"):
            self._handle_slash(user_input)
            return

        # Regular message
        self._session_messages += 1
        output.add_turn_separator()
        output.write_user(user_input)

        # Auto-save session
        if not self.chat_state.get("_chat_session"):
            from ..chat_history import create_session
            self.chat_state["_chat_session"] = create_session(
                self.agent_name, self.chat_state.get("repo_path", "")
            )
        from ..chat_history import add_message as _add_msg
        _add_msg(self.chat_state["_chat_session"], "user", user_input)

        self._process_message(user_input)

    # -------------------------------------------------------------------
    # Message processing (background thread)
    # -------------------------------------------------------------------

    @work(thread=True)
    def _process_message(self, user_input: str) -> None:
        """Process user message — runs in background thread."""
        output = self.query_one(ChatOutput)
        self._agent_busy = True
        self._cancel_requested = False
        self.call_from_thread(self._update_status, "Thinking...")

        # Mount spinner
        spinner = ThinkingIndicator()
        self.call_from_thread(output.mount, spinner)

        # Redirect stdout to TUI proxy
        from .proxy import TUIOutputTarget
        _original_stdout = sys.stdout
        _proxy = TUIOutputTarget(self, output)
        sys.stdout = _proxy

        try:
            from .. import chat as _chat_mod
            from ..chat_response import process_streaming_response, handle_post_response
            from ..chat_repl import run_agentic_followup_loop
            from ..chat_context import _build_system_context

            current_agent = self.chat_state["agent"]
            system_context = _build_system_context(
                self.chat_state.get("repo_path", self.chat_cwd),
                current_agent,
                btw_messages=self.chat_state.get("_btw_messages", []),
                superpower=self.chat_state.get("superpower", False),
            )

            # Build message history
            messages = [{"role": "system", "content": system_context}]
            chat_session = self.chat_state.get("_chat_session")
            if chat_session and chat_session.get("messages"):
                for hist_msg in chat_session["messages"]:
                    if hist_msg.get("role") in ("user", "assistant"):
                        messages.append({"role": hist_msg["role"], "content": hist_msg["content"]})
            if not messages or messages[-1].get("content") != user_input:
                messages.append({"role": "user", "content": user_input})

            # Remove spinner on first output
            def _remove_spinner():
                try:
                    spinner.remove()
                except Exception:
                    pass
            _first_output = [True]
            _orig_write = _proxy.write
            def _write_and_remove_spinner(text):
                if _first_output[0] and text.strip():
                    _first_output[0] = False
                    self.call_from_thread(_remove_spinner)
                    self.call_from_thread(self._update_status, "Streaming...")
                return _orig_write(text)
            _proxy.write = _write_and_remove_spinner

            # Stream response
            _ctrl_c_ref = [getattr(_chat_mod, '_last_ctrl_c', 0)]
            try:
                got_text, full_response, interrupted = process_streaming_response(
                    self.chat_url, current_agent, messages, self.chat_state,
                    _last_ctrl_c_ref=_ctrl_c_ref,
                )
            except KeyboardInterrupt:
                self.call_from_thread(lambda: output.write_thinking("Response interrupted."))
                return

            if hasattr(_chat_mod, '_last_ctrl_c'):
                _chat_mod._last_ctrl_c = _ctrl_c_ref[0]

            full_text = "".join(full_response) if full_response else ""

            # Log response
            if full_text:
                from code_agents.core.logging_config import log_agent_response
                _out_tokens = self.chat_state.get("_last_usage", {}).get("output_tokens", 0) if self.chat_state.get("_last_usage") else 0
                log_agent_response(current_agent, full_text, tokens=_out_tokens)

            # Save to history
            if full_text and self.chat_state.get("_chat_session"):
                from ..chat_history import add_message as _save_msg
                _save_msg(self.chat_state["_chat_session"], "assistant", full_text)

            # Post-response processing (skills, delegation, questionnaire)
            if not interrupted:
                full_response, effective_agent = handle_post_response(
                    full_response, user_input, self.chat_state, self.chat_url,
                    current_agent, system_context, self.chat_cwd,
                )
                # Agentic follow-up loop
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
            self.call_from_thread(lambda: output.write_error(str(e)))

        finally:
            # Restore stdout
            sys.stdout = _original_stdout
            _proxy.flush()

            # Remove spinner if still mounted
            try:
                self.call_from_thread(_remove_spinner)
            except Exception:
                pass

            self._agent_busy = False
            self.call_from_thread(self._update_status)

            # Process queued messages
            if self._queued_messages:
                next_msg = self._queued_messages.pop(0)
                self.call_from_thread(lambda: output.write("[dim]  ⟫ Processing queued message[/]"))
                self._process_message(next_msg)

    # -------------------------------------------------------------------
    # Slash commands
    # -------------------------------------------------------------------

    def _handle_slash(self, user_input: str) -> None:
        """Handle slash commands."""
        output = self.query_one(ChatOutput)
        cmd = user_input.strip().lower()

        if cmd in ("/quit", "/exit", "/q"):
            self._print_summary()
            self.exit()
            return

        if cmd == "/help":
            output.write("[bold]Available commands:[/]")
            output.write("  /agent <name>  — switch agent")
            output.write("  /agents        — list all agents")
            output.write("  /clear         — clear output")
            output.write("  /history       — show chat history")
            output.write("  /status        — show current status")
            output.write("  /confirm on|off — toggle requirement confirmation")
            output.write("  /quit          — exit chat")
            output.write("")
            return

        if cmd == "/clear":
            output.clear()
            output.write("[dim]  Output cleared.[/]")
            return

        if cmd.startswith("/agent "):
            new_agent = user_input[7:].strip()
            if new_agent:
                self.chat_state["agent"] = new_agent
                self.agent_name = new_agent
                output.write_success(f"Switched to {new_agent}")
                self._update_status()
            return

        # Delegate to main slash handler
        try:
            from .. import chat as _chat_mod
            result = _chat_mod._handle_command(user_input, self.chat_state, self.chat_url)
            if result == "quit":
                self._print_summary()
                self.exit()
        except Exception as e:
            output.write_error(f"Command error: {e}")

    # -------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------

    def action_interrupt_or_quit(self) -> None:
        """Escape key: interrupt agent if busy, else quit."""
        if self._agent_busy:
            self._cancel_requested = True
            output = self.query_one(ChatOutput)
            output.write_thinking("Interrupt requested...")
        else:
            self._print_summary()
            self.exit()

    def action_cycle_mode(self) -> None:
        """Shift+Tab: cycle chat mode."""
        idx = self._modes.index(self._mode)
        self._mode = self._modes[(idx + 1) % len(self._modes)]
        self._update_status()
        output = self.query_one(ChatOutput)
        output.write_success(f"Mode: {self._mode}")

    # -------------------------------------------------------------------
    # Session summary
    # -------------------------------------------------------------------

    def _print_summary(self) -> None:
        output = self.query_one(ChatOutput)
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
