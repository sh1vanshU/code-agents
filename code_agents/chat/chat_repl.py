"""Agentic follow-up loop — run extracted shell commands and feed output back to the agent."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from .chat_commands import _extract_commands, _offer_run_commands

logger = logging.getLogger("code_agents.chat.chat_repl")
from .chat_streaming import _stream_with_spinner
from .chat_ui import dim, red, yellow


def run_agentic_followup_loop(
    *,
    full_response: list[str],
    cwd: str,
    url: str,
    state: dict[str, Any],
    current_agent: str,
    effective_agent: str = "",
    system_context: str,
    superpower: bool,
) -> tuple[list[str], int]:
    """Detect ```bash`` commands in the last response, offer run, feed results back. Returns (last_response, commands_executed_count)."""
    from .chat_input import is_edit_mode

    # Use effective_agent for command autorun checks and follow-up LLM calls.
    # After delegation, effective_agent is the delegate (e.g. argocd-verify)
    # while current_agent is the original (e.g. jenkins-cicd).
    _cmd_agent = effective_agent or current_agent

    _loop_response = full_response
    _loop_auto_run = False
    if superpower or is_edit_mode():
        _loop_auto_run = True
    _max_loops = int(os.getenv("CODE_AGENTS_MAX_LOOPS", "10"))
    extra_commands = 0

    for _loop_i in range(_max_loops):
        if not _loop_response:
            break

        from code_agents.core.token_tracker import check_cost_guard

        if not check_cost_guard():
            print(yellow("  ⚠ Token budget exceeded (CODE_AGENTS_MAX_SESSION_TOKENS). Stopping agentic loop."))
            print(dim("  Increase the limit or start a new session."))
            print()
            break

        commands = _extract_commands("".join(_loop_response))
        if not commands:
            break

        try:
            _effective_superpower = superpower or is_edit_mode()
            exec_results = _offer_run_commands(
                commands,
                state.get("repo_path", cwd),
                agent_name=_cmd_agent,
                auto_run=_loop_auto_run,
                superpower=_effective_superpower,
            )
            extra_commands += len(exec_results)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        except Exception as e:
            print(red(f"\n  Command execution error: {e}"))
            break

        if not exec_results:
            break

        feedback_parts = []
        for er in exec_results:
            output_preview = er["output"][:2000] if er["output"] else "(no output)"
            feedback_parts.append(
                f"Command: {er['command']}\nOutput:\n{output_preview}"
            )
        feedback = (
            "I ran the following commands. Here are the results. "
            "Please analyze the output and suggest next steps if needed.\n\n"
            + "\n\n---\n\n".join(feedback_parts)
        )

        # Capture [REMEMBER:key=value] tags from the previous response
        _prev_text = "".join(_loop_response) if _loop_response else ""
        if _prev_text:
            try:
                from code_agents.agent_system.session_scratchpad import extract_remember_tags, strip_remember_tags, SessionScratchpad
                _remember_pairs = extract_remember_tags(_prev_text)
                if _remember_pairs:
                    _sp_sid = (state.get("_chat_session") or {}).get("id")
                    if _sp_sid:
                        _sp = SessionScratchpad(_sp_sid, _cmd_agent)
                        for _rk, _rv in _remember_pairs:
                            _sp.set(_rk, _rv)
            except Exception:
                pass

        # Rebuild system_context with fresh scratchpad values
        _fresh_context = system_context
        try:
            _sp_sid = (state.get("_chat_session") or {}).get("id")
            if _sp_sid:
                from code_agents.agent_system.session_scratchpad import SessionScratchpad
                _sp = SessionScratchpad(_sp_sid, _cmd_agent)
                _memory_block = _sp.format_for_prompt()
                if _memory_block and _memory_block not in _fresh_context:
                    _fresh_context += f"\n\n{_memory_block}"
        except Exception:
            pass

        # Include conversation history so agent retains context across agentic loop rounds
        followup_messages = [{"role": "system", "content": _fresh_context}]
        chat_session = state.get("_chat_session")
        if chat_session and chat_session.get("messages"):
            for hist_msg in chat_session["messages"]:
                if hist_msg.get("role") in ("user", "assistant"):
                    followup_messages.append({"role": hist_msg["role"], "content": hist_msg["content"]})
        followup_messages.append({"role": "user", "content": feedback})

        _loop_response = _stream_with_spinner(
            url,
            _cmd_agent,
            followup_messages,
            state.get("session_id"),
            cwd=state.get("repo_path"),
            state=state,
            label="Analyzing results...",
        )

        # Save agentic loop messages to chat history so they persist for next user message
        if state.get("_chat_session"):
            from .chat_history import add_message as _save_loop_msg
            _save_loop_msg(state["_chat_session"], "user", feedback)
            if _loop_response:
                _loop_text = "".join(_loop_response)
                if _loop_text:
                    # Strip [REMEMBER:] tags before saving
                    try:
                        from code_agents.agent_system.session_scratchpad import strip_remember_tags
                        _loop_text = strip_remember_tags(_loop_text)
                    except Exception:
                        pass
                    _save_loop_msg(state["_chat_session"], "assistant", _loop_text)

        _loop_auto_run = True

    return _loop_response, extra_commands
