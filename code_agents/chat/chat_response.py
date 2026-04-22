"""Chat response processing — streaming SSE, response box rendering, post-response handling.

Extracted from chat.py to reduce the size of the REPL orchestrator.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time as _time

from .chat_ui import (
    bold, green, yellow, red, cyan, dim, magenta,
    _render_markdown, agent_color, agent_color_fn, strip_ansi,
)
from .chat_commands import _extract_commands, _extract_skill_requests, _extract_delegations
from .chat_server import _stream_chat
from .chat_streaming import _stream_with_spinner
from .chat_context import _build_system_context

logger = logging.getLogger("code_agents.chat")

# ANSI color codes for delegation UI (agent → color)
_AGENT_COLOR_CODES = {
    "code-reasoning": "36", "code-writer": "32", "code-reviewer": "33",
    "code-tester": "36", "redash-query": "34", "git-ops": "35",
    "test-coverage": "32", "jenkins-cicd": "31", "argocd-verify": "35",
    "qa-regression": "31", "auto-pilot": "37", "jira-ops": "34",
}


def _agent_color_code(agent_name: str) -> str:
    """Return ANSI color code for an agent name."""
    return _AGENT_COLOR_CODES.get(agent_name, "37")


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def process_streaming_response(
    url: str,
    current_agent: str,
    messages: list[dict],
    state: dict,
    *,
    _last_ctrl_c_ref: list[float],
    output_target=None,
) -> tuple[bool, list[str], bool]:
    """Stream a response from the server, rendering into a response box.

    Args:
        output_target: Optional OutputTarget for background task support.
            When provided, all output is routed through it instead of sys.stdout.

    Returns:
        (got_text, full_response_parts, was_interrupted)
    """
    import shutil as _shutil

    # Output routing: use output_target if provided, else write directly to stdout
    _out = output_target or sys.stdout

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

    _response_start = _time.monotonic()
    _stop_spin = threading.Event()
    _main_activity_label = ["Thinking", ""]  # [action, target] — mutable
    _spinner_line_written = [False]  # track if we wrote a spinner line

    def _show_spinner():
        """Spinner that works with prompt_toolkit's patch_stdout.

        Uses simple print() instead of cursor manipulation (\r, \033[2K) which
        conflicts with prompt_toolkit's input line management.
        """
        frames = [
            "\033[1;34m\u23fa\033[0m",  # bright blue
            "\033[2;34m\u23fa\033[0m",  # dim blue
        ]
        i = 0
        _spinner_line_written[0] = True
        _last_text = ""
        while not _stop_spin.is_set():
            dot = frames[i % len(frames)]
            elapsed = _time.monotonic() - _response_start
            cur_action, cur_target = _main_activity_label
            target_str = f" ({cur_target})" if cur_target else ""
            text = f"{cur_action}{target_str} {_format_elapsed(elapsed)}"
            # Only update if text changed or on first frame
            if i == 0:
                _out_write(f"  {dot} {dim(text)}")
                _out_flush()
                _last_text = text
            elif text != _last_text or i % 2 == 0:
                # Overwrite current line — use \r within the same line
                _out_write(f"\r  {dot} {dim(text)}  ")
                _out_flush()
                _last_text = text
            i += 1
            _stop_spin.wait(0.5)
        # Clear spinner: overwrite with spaces then return carriage
        _out_write(f"\r{' ' * (len(_last_text) + 10)}\r")
        _out_flush()

    spin_thread = threading.Thread(target=_show_spinner, daemon=True)
    spin_thread.start()

    got_text = False
    full_response: list[str] = []
    _cb = lambda s: s  # default no-color box
    _bw = 80
    _streaming_interrupted = False
    _consecutive_newlines = 0
    _line_pos = 0

    try:
        for piece_type, piece_content in _stream_chat(
            url, current_agent, messages, state.get("session_id"),
            cwd=state.get("repo_path"),
        ):
            if piece_type == "text":
                if not got_text:
                    # Stop spinner — no flicker: spinner clears its own line
                    _stop_spin.set()
                    spin_thread.join(timeout=1)
                    # Clear spinner line before rendering response box
                    if _spinner_line_written[0]:
                        _out_write("\r\033[2K")
                    _tw = _shutil.get_terminal_size((80, 24)).columns
                    _bw = min(_tw - 4, 120)
                    _cb = agent_color_fn(current_agent)
                    _lbl = f" {current_agent.upper()} "
                    _rp = _bw - 2 - len(_lbl) - 1
                    # Write box header directly — no extra newlines that cause jumps
                    _out_write(f"  {_cb('\u2554' + '\u2550' + _lbl + '\u2550' * max(0, _rp) + '\u2557')}\n")
                    _out_write(f"  {_cb('\u2551')}  \n")
                    _out_flush()
                got_text = True
                full_response.append(piece_content)
                # Strip internal tags from display — they're processed post-response
                _display_content = piece_content
                _display_content = re.sub(r"\[SKILL:[a-z0-9_:-]+\]", "", _display_content)
                _display_content = re.sub(r"\[DELEGATE:[a-z0-9_-]+\]", "", _display_content)
                _display_content = re.sub(r"\[REMEMBER:[^\]]+\]", "", _display_content)
                _display_content = re.sub(r"\[QUESTION:[^\]]+\]", "", _display_content)
                if not _display_content.strip():
                    continue
                # Render with indent — suppress excessive blank lines
                rendered = _render_markdown(_display_content)
                _wrap_at = _bw - 6  # 4 indent + 2 margin
                filtered = []
                # Ensure first chunk starts with indent (box header ends with \n but no indent)
                if _line_pos == 0 and (not filtered or not rendered.startswith("\n")):
                    filtered.append("    ")
                    _line_pos = 4
                for ch in rendered:
                    if ch == "\n":
                        _consecutive_newlines += 1
                        _line_pos = 0
                        if _consecutive_newlines <= 2:
                            filtered.append("\n    ")
                    elif ch == "\033":
                        filtered.append(ch)
                    else:
                        _consecutive_newlines = 0
                        _line_pos += 1
                        if _line_pos >= _wrap_at and ch == " ":
                            filtered.append("\n    ")
                            _line_pos = 0
                        else:
                            filtered.append(ch)
                _out_write("".join(filtered))
                _out_flush()

            elif piece_type == "reasoning":
                activity_text = piece_content.strip()
                _is_tool_output = (
                    activity_text.startswith("**Tool Result")
                    or activity_text.startswith("```")
                    or "Tool Result" in activity_text[:30]
                )
                if _is_tool_output:
                    # Stream tool results directly to output (dimmed)
                    _out_write(dim(piece_content))
                    _out_flush()
                elif activity_text and not _stop_spin.is_set():
                    # Update spinner label in-place (spinner thread handles rendering)
                    parts = activity_text.split(None, 1)
                    if len(parts) == 2:
                        _main_activity_label[0] = parts[0]
                        _main_activity_label[1] = parts[1][:40]
                    else:
                        _main_activity_label[0] = activity_text[:40]
                        _main_activity_label[1] = ""
                elif _stop_spin.is_set() and activity_text:
                    # After spinner stopped, show reasoning as dim inline text
                    if not (activity_text.startswith("**") or "```" in activity_text
                            or "{" in activity_text):
                        brief = activity_text[:80]
                        _out_write(f"\n    {dim(brief)}")
                        _out_flush()

            elif piece_type == "session_id":
                state["session_id"] = piece_content

            elif piece_type == "usage":
                state["_last_usage"] = piece_content

            elif piece_type == "duration_ms":
                state["_last_duration_ms"] = piece_content

            elif piece_type == "error":
                if not _stop_spin.is_set():
                    _stop_spin.set()
                    spin_thread.join(timeout=1)
                print(red(f"\n  Error: {piece_content}"))
    except KeyboardInterrupt:
        _streaming_interrupted = True
        if not _stop_spin.is_set():
            _stop_spin.set()
            spin_thread.join(timeout=1)
        import time as _time_mod
        now = _time_mod.time()
        _last_ctrl_c_ref[0] = now
        print()
        print(yellow("  ⏸ Interrupted — say \"go ahead\" to resume, or type a new message."))
        print()

    # Ensure spinner is stopped
    if not _stop_spin.is_set():
        _stop_spin.set()
        spin_thread.join(timeout=1)

    if got_text and not _streaming_interrupted:
        # Close the response box
        _out_write(f"\n  {_cb('\u255a' + '\u2550' * (_bw - 2) + '\u255d')}\n\n")
        _out_flush()

    # Store timing for post-response
    state["_response_start"] = _response_start

    return got_text, full_response, _streaming_interrupted


def handle_post_response(
    full_response: list[str],
    user_input: str,
    state: dict,
    url: str,
    current_agent: str,
    system_context: str,
    cwd: str,
) -> tuple[list[str], str]:
    """Handle everything after streaming completes — saving, scoring, verification, skills, delegation.

    Returns (full_response, effective_agent) — effective_agent is the delegate
    agent name if delegation occurred, otherwise the original current_agent.
    """
    effective_agent = current_agent
    full_text = "".join(full_response) if full_response else ""

    # Capture [REMEMBER:key=value] tags → save to session scratchpad, strip from display
    if full_text:
        try:
            from code_agents.agent_system.session_scratchpad import extract_remember_tags, strip_remember_tags
            _remember_pairs = extract_remember_tags(full_text)
            if _remember_pairs:
                _sp_session_id = (state.get("_chat_session") or {}).get("id")
                if _sp_session_id:
                    from code_agents.agent_system.session_scratchpad import SessionScratchpad
                    _sp = SessionScratchpad(_sp_session_id, current_agent)
                    for _rk, _rv in _remember_pairs:
                        _sp.set(_rk, _rv)
                full_text = strip_remember_tags(full_text)
                full_response = [full_text]
        except Exception:
            pass

    state["_last_output"] = full_text

    # Record trace step (user + assistant) for session replay
    try:
        from code_agents.agent_system.agent_replay import TraceRecorder
        _trace_recorder: TraceRecorder | None = state.get("_trace_recorder")
        if _trace_recorder is None:
            _session_id = (state.get("_chat_session") or {}).get("id", "unknown")
            _trace_recorder = TraceRecorder(
                session_id=_session_id,
                agent=current_agent,
                repo=state.get("repo_path", cwd),
            )
            state["_trace_recorder"] = _trace_recorder
        # Record the user message
        if user_input:
            _trace_recorder.record_step("user", user_input)
        # Record the assistant response
        if full_text:
            _trace_meta: dict = {}
            _usage = state.get("_last_usage")
            if _usage:
                _trace_meta["usage"] = _usage
            _trace_recorder.record_step("assistant", full_text, metadata=_trace_meta)
        # Auto-save trace periodically (every 10 steps)
        if len(_trace_recorder.get_trace().steps) % 10 == 0:
            _trace_recorder.save()
    except Exception:
        pass

    # Auto-save agent response to chat history
    if full_text and state.get("_chat_session"):
        from .chat_history import add_message as _save_msg
        _save_msg(state["_chat_session"], "assistant", full_text)

    # Append clean agent response to summary doc
    if full_text and state.get("_md_file"):
        try:
            _clean = full_text
            import re as _re_md
            _clean = _re_md.sub(r'```bash\n.*?```', '', _clean, flags=_re_md.DOTALL)
            _clean = _clean.strip()
            if _clean:
                with open(state["_md_file"], "a") as _mf:
                    _mf.write(f"{_clean}\n\n---\n\n")
        except OSError:
            pass

    # Append agent plan to plan report (.md) in plan mode
    if full_text and state.get("_plan_report"):
        try:
            from .chat_input import get_current_mode
            if get_current_mode() == "plan":
                import re as _re_plan
                _plan_clean = full_text.strip()
                with open(state["_plan_report"], "a") as _pf:
                    _pf.write(f"{_plan_clean}\n\n---\n\n")
        except OSError:
            pass
        if state.get("session_id"):
            state["_chat_session"]["_server_session_id"] = state["session_id"]
            from .chat_history import _save as _persist
            _persist(state["_chat_session"])

    # Response was already streamed and rendered in the response box above.
    # No need to re-render — that causes duplicate output.

    # Show elapsed time + token usage
    _response_start = state.pop("_response_start", _time.monotonic())
    elapsed = _time.monotonic() - _response_start
    usage = state.pop("_last_usage", None)
    dur_ms = state.pop("_last_duration_ms", 0)

    usage_str = ""
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
            usage_str = f" \u00b7 request: {inp:,}, response: {out:,} tokens ({total:,} total{est}{cache_note})"

        from code_agents.core.token_tracker import record_usage
        record_usage(
            agent=current_agent,
            backend=os.getenv("CODE_AGENTS_BACKEND", "cursor"),
            model=(
                os.getenv("CODE_AGENTS_CLAUDE_CLI_MODEL", "").strip()
                or os.getenv("CODE_AGENTS_MODEL", "Composer 2 Fast")
            ),
            usage=usage,
            duration_ms=dur_ms or int(elapsed * 1000),
            session_id=state.get("session_id", ""),
        )

    print(f"  {dim(f'\u273b Response took {_format_elapsed(elapsed)}{usage_str}')}")
    print()

    # Confidence scoring
    if full_text and user_input.strip():
        try:
            from code_agents.core.confidence_scorer import get_scorer
            _conf = get_scorer().score_response(current_agent, user_input, full_text)
            if _conf.should_delegate and _conf.suggested_agent:
                from .chat_welcome import AGENT_ROLES as _AR
                _role_hint = _AR.get(_conf.suggested_agent, "")
                _hint = f"  {dim(f'\U0001f4a1 Low confidence ({_conf.score}/5). Try: /agent {_conf.suggested_agent}')}"
                if _role_hint:
                    _hint += f" {dim(f'\u2014 {_role_hint}')}"
                print(_hint)
                print()
        except Exception:
            pass

    # Response verification
    if full_text and current_agent and user_input.strip():
        try:
            from code_agents.core.response_verifier import get_verifier
            _rv = get_verifier()
            if _rv.should_verify(current_agent, full_text):
                _verify_result = _rv.build_verify_prompt(user_input, full_text)
                _verify_prompt = _verify_result["prompt"]
                _cache_key = _verify_result.get("cache_key")
                _cached = _rv.get_cached_result(_cache_key) if _cache_key else None
                if _cached:
                    _verify_text = _cached
                else:
                    print(f"  {dim('\u23f3 Verifying with code-reviewer...')}")
                    _verify_context = _build_system_context(
                        state.get("repo_path", ""), "code-reviewer",
                        btw_messages=[], superpower=False,
                    )
                    _verify_msgs = [
                        {"role": "system", "content": _verify_context},
                        {"role": "user", "content": _verify_prompt},
                    ]
                    _verify_response = _stream_with_spinner(
                        url, "code-reviewer", _verify_msgs,
                        state.get("session_id"),
                        cwd=state.get("repo_path"),
                        state=state,
                        label="Verifying with code-reviewer...",
                    )
                    _verify_text = "".join(_verify_response) if _verify_response else ""
                    if _verify_text and _cache_key:
                        _rv.cache_result(_cache_key, _verify_text)
                if _verify_text:
                    _is_lgtm = "lgtm" in _verify_text.lower() or "no issues" in _verify_text.lower()
                    if _is_lgtm:
                        print(f"  {green('\u2713 LGTM \u2014 no issues found')}")
                    else:
                        print(f"  {yellow('\u26a0 Review notes:')}")
                        for _vline in _verify_text.strip().splitlines():
                            _vline = _vline.strip()
                            if _vline:
                                if _vline.startswith(('- ', '* ', '\u2022 ')):
                                    print(f"    {yellow('\u2022')} {_vline[2:].strip()}")
                                elif _vline.startswith(('1.', '2.', '3.')):
                                    print(f"    {yellow('\u2022')} {_vline[2:].strip()}")
                                else:
                                    print(f"    {yellow('\u2022')} {_vline}")
                    print()
        except Exception as _ve:
            logger.debug("Response verification failed: %s", _ve)

    # Skill loading: detect [SKILL:name] -> load skill body -> feed to agent
    if full_response:
        skill_names = _extract_skill_requests("".join(full_response))
        if skill_names:
            from code_agents.agent_system.skill_loader import get_skill
            from code_agents.core.config import settings
            for skill_name in skill_names:
                skill = get_skill(settings.agents_dir, current_agent, skill_name)
                if skill:
                    print(dim(f"  Loading skill: {bold(cyan(skill.full_name))}"))
                    print()

                    skill_message = (
                        f"[Skill loaded: {skill.name}]\n\n"
                        f"{skill.body}\n\n"
                        f"Now proceed with this workflow. "
                        f"Output the first ```bash command to begin."
                    )

                    # Include conversation history so the agent retains context
                    # (repo name, branch, build results, user confirmations)
                    # Inject fresh scratchpad into system context for skill execution
                    _skill_context = system_context
                    try:
                        from code_agents.agent_system.session_scratchpad import SessionScratchpad
                        _sp_sid = (state.get("_chat_session") or {}).get("id")
                        if _sp_sid:
                            _sp = SessionScratchpad(_sp_sid, current_agent)
                            _mb = _sp.format_for_prompt()
                            if _mb and _mb not in _skill_context:
                                _skill_context += f"\n\n{_mb}"
                    except Exception:
                        pass
                    followup_msgs = [{"role": "system", "content": _skill_context}]
                    chat_session = state.get("_chat_session")
                    if chat_session and chat_session.get("messages"):
                        for hist_msg in chat_session["messages"]:
                            if hist_msg.get("role") in ("user", "assistant"):
                                followup_msgs.append({"role": hist_msg["role"], "content": hist_msg["content"]})
                    followup_msgs.append({"role": "assistant", "content": "".join(full_response)})
                    followup_msgs.append({"role": "user", "content": skill_message})

                    skill_response = _stream_with_spinner(
                        url, current_agent, followup_msgs,
                        state.get("session_id"),
                        cwd=state.get("repo_path"),
                        state=state,
                        label=f"Loading {skill.name}...",
                    )

                    full_response = skill_response
                    full_text = "".join(skill_response)
                    state["_last_output"] = full_text

                    if full_text and state.get("_chat_session"):
                        from .chat_history import add_message as _save_skill
                        _save_skill(state["_chat_session"], "assistant", full_text)

                    elapsed = _time.monotonic() - _response_start
                    print(f"  {dim(f'\u273b Skill response took {_format_elapsed(elapsed)}')}")
                    print()

    # Round-trip delegation: delegate executes as a tool, result returns to source agent.
    # Like Claude Code's Agent() tool — parent calls specialist, gets result back, continues.
    _delegation_depth = state.get("_delegation_depth", 0)
    MAX_DELEGATION_DEPTH = 3

    if full_response and _delegation_depth < MAX_DELEGATION_DEPTH:
        delegations = _extract_delegations("".join(full_response))
        for delegate_target, delegate_prompt in delegations:
            if not delegate_target or not delegate_prompt.strip():
                continue

            # ── UI: show delegation as a tool call (compact, not full stream) ──
            _dc = _agent_color_code(delegate_target)
            _df = lambda s, _c=_dc: f"\033[{_c}m{s}\033[0m" if sys.stdout.isatty() else s
            print()
            print(f"  {_df(bold(f'> Agent({delegate_target})'))}  {dim(delegate_prompt.strip()[:60])}")

            # ── Build delegate context ──
            delegate_context = _build_system_context(
                state.get("repo_path", ""), delegate_target,
                btw_messages=state.get("_btw_messages", []),
                superpower=state.get("superpower", False),
            )
            # Tell delegate who called it and what to return
            delegate_context += (
                f"\n\n[DELEGATION CONTEXT]\n"
                f"You were invoked as a tool by {current_agent}.\n"
                f"Depth: {_delegation_depth + 1}/{MAX_DELEGATION_DEPTH}\n"
                f"Return a concise, actionable result. Do NOT use [DELEGATE:] tags "
                f"(your result flows back to the calling agent).\n"
                f"[END DELEGATION CONTEXT]"
            )
            # Inject session scratchpad
            _sp_session_id = (state.get("_chat_session") or {}).get("id")
            if _sp_session_id:
                try:
                    from code_agents.agent_system.session_scratchpad import SessionScratchpad
                    _sp = SessionScratchpad(_sp_session_id, delegate_target)
                    _sp_block = _sp.format_for_prompt()
                    if _sp_block:
                        delegate_context += f"\n\n{_sp_block}"
                except Exception:
                    pass

            # ── Execute delegate (captured, not streamed to user) ──
            delegate_msgs = [{"role": "system", "content": delegate_context}]
            chat_session = state.get("_chat_session")
            if chat_session and chat_session.get("messages"):
                for hist_msg in chat_session["messages"]:
                    if hist_msg.get("role") in ("user", "assistant"):
                        delegate_msgs.append({"role": hist_msg["role"], "content": hist_msg["content"]})
            delegate_msgs.append({"role": "user", "content": delegate_prompt.strip()})

            # Track depth to prevent infinite delegation chains
            _prev_depth = state.get("_delegation_depth", 0)
            state["_delegation_depth"] = _prev_depth + 1

            delegate_response = _stream_with_spinner(
                url, delegate_target, delegate_msgs,
                state.get("session_id"),
                cwd=state.get("repo_path"),
                state=state,
                label=f"Agent({delegate_target})",
            )

            state["_delegation_depth"] = _prev_depth  # restore depth

            if not delegate_response:
                print(f"  {dim('(no result)')}")
                continue

            delegate_text = "".join(delegate_response)

            # Extract [REMEMBER:] tags from delegate into shared scratchpad
            try:
                from code_agents.agent_system.session_scratchpad import extract_remember_tags, strip_remember_tags
                _del_pairs = extract_remember_tags(delegate_text)
                if _del_pairs:
                    _del_sp_id = (state.get("_chat_session") or {}).get("id")
                    if _del_sp_id:
                        from code_agents.agent_system.session_scratchpad import SessionScratchpad
                        _del_sp = SessionScratchpad(_del_sp_id, delegate_target)
                        for _dk, _dv in _del_pairs:
                            _del_sp.set(_dk, _dv)
                    delegate_text = strip_remember_tags(delegate_text)
            except Exception:
                pass

            # ── UI: show compact result summary ──
            _result_preview = delegate_text.strip().split('\n')[0][:80]
            print(f"  {_df(dim(f'  Result: {_result_preview}'))}")

            # ── Feed result back to source agent (round-trip) ──
            # Source agent gets the delegate's output as context and continues.
            _roundtrip_inject = (
                f"[Agent Result from {delegate_target}]\n"
                f"{delegate_text}\n"
                f"[End Agent Result]\n\n"
                f"Continue with the above result from {delegate_target}. "
                f"Synthesize the findings and respond to the user."
            )

            _rt_context = system_context
            # Inject fresh scratchpad for source agent's continuation
            if _sp_session_id:
                try:
                    from code_agents.agent_system.session_scratchpad import SessionScratchpad
                    _sp_rt = SessionScratchpad(_sp_session_id, current_agent)
                    _sp_rt_block = _sp_rt.format_for_prompt()
                    if _sp_rt_block and _sp_rt_block not in _rt_context:
                        _rt_context += f"\n\n{_sp_rt_block}"
                except Exception:
                    pass

            _rt_msgs = [{"role": "system", "content": _rt_context}]
            if chat_session and chat_session.get("messages"):
                for hist_msg in chat_session["messages"]:
                    if hist_msg.get("role") in ("user", "assistant"):
                        _rt_msgs.append({"role": hist_msg["role"], "content": hist_msg["content"]})
            # Include source agent's original response that triggered delegation
            _rt_msgs.append({"role": "assistant", "content": "".join(full_response)})
            # Inject delegate result as a follow-up user message (tool result)
            _rt_msgs.append({"role": "user", "content": _roundtrip_inject})

            print(f"  {dim(f'Returning to {current_agent}...')}")
            print()

            continuation = _stream_with_spinner(
                url, current_agent, _rt_msgs,
                state.get("session_id"),
                cwd=state.get("repo_path"),
                state=state,
                label=f"Continuing ({current_agent})...",
            )

            if continuation:
                full_response = continuation
                full_text = "".join(continuation)
                state["_last_output"] = full_text
                if full_text and state.get("_chat_session"):
                    from .chat_history import add_message as _save_rt
                    _save_rt(state["_chat_session"], "assistant", full_text)

    # Questionnaire: detect free-form numbered questions (Q1, Q2, etc.)
    if full_response and sys.stdout.isatty():
        _assistant_text_q = "".join(full_response)
        if "[QUESTION:" not in _assistant_text_q:
            from code_agents.agent_system.question_parser import parse_questions
            _parsed_qs = parse_questions(_assistant_text_q)
            if _parsed_qs:
                from code_agents.agent_system.questionnaire import ask_multiple_tabbed, format_qa_for_prompt as _fmt_qa_tab
                _tab_answers = ask_multiple_tabbed(_parsed_qs)
                if _tab_answers:
                    _qa_pairs = state.setdefault("_qa_pairs", [])
                    _qa_pairs.extend(_tab_answers)

                    # Plan mode: handle the three confirmation options
                    for _ta in _tab_answers:
                        _ans_lower = _ta.get("answer", "").lower()

                        # Option 1: "Accepted" — switch to chat mode for execution
                        if "accepted" in _ans_lower:
                            try:
                                from .chat_input import get_current_mode, set_mode
                                if get_current_mode() == "plan":
                                    set_mode("chat")
                                    print(f"  {green('✓ Plan accepted')} {dim('— switching to Chat mode for execution')}")
                                    print()
                            except Exception:
                                pass

                        # Option 2: "Edit" — prompt for inline modification
                        elif "edit" in _ans_lower:
                            print()
                            print(f"  {yellow('✎')} {bold('Describe your modifications:')}")
                            print(f"  {dim('(type your changes, press Enter to submit)')}")
                            print()
                            try:
                                import sys as _sys_edit
                                _sys_edit.stdout.write(f"  {cyan('>')} ")
                                _sys_edit.stdout.flush()
                                _edit_text = _sys_edit.stdin.readline().strip()
                                if _edit_text:
                                    _ta["answer"] = f"Edit with modifications: {_edit_text}"
                                    print(f"  {dim(f'Modification: {_edit_text[:80]}')}")
                                    print()
                            except (EOFError, KeyboardInterrupt):
                                pass

                        # Option 3: "Rejected" — discard plan, stay in plan mode
                        elif "rejected" in _ans_lower or "reject" in _ans_lower:
                            print(f"  {red('✗ Plan rejected')} {dim('— send a new request or update your requirement')}")
                            print()

                    _qa_context = _fmt_qa_tab(_tab_answers)
                    if _qa_context:
                        # Inject fresh scratchpad
                        _fq_ctx = system_context
                        try:
                            from code_agents.agent_system.session_scratchpad import SessionScratchpad
                            _sp_sid = (state.get("_chat_session") or {}).get("id")
                            if _sp_sid:
                                _mb = SessionScratchpad(_sp_sid, current_agent).format_for_prompt()
                                if _mb and _mb not in _fq_ctx:
                                    _fq_ctx += f"\n\n{_mb}"
                        except Exception:
                            pass
                        _qa_msgs = [
                            {"role": "system", "content": _fq_ctx},
                            {"role": "assistant", "content": _assistant_text_q},
                            {"role": "user", "content": _qa_context},
                        ]
                        _qa_response = _stream_with_spinner(
                            url, current_agent, _qa_msgs,
                            state.get("session_id"),
                            cwd=state.get("repo_path"),
                            state=state,
                            label="Processing your answers...",
                        )
                        if _qa_response:
                            full_response = _qa_response
                            full_text = "".join(_qa_response)
                            state["_last_output"] = full_text

    # Questionnaire: detect [QUESTION:key] tags
    if full_response:
        import re as _re_q
        _assistant_text = "".join(full_response)
        _question_matches = _re_q.findall(r'\[QUESTION:(.*?)\]', _assistant_text)
        if _question_matches:
            from code_agents.agent_system.questionnaire import (
                ask_question as _ask_q,
                ask_multiple_tabbed as _ask_multi,
                TEMPLATES as _Q_TEMPLATES,
                format_qa_for_prompt as _fmt_qa,
                has_been_answered as _qa_answered,
            )
            _qa_pairs = state.setdefault("_qa_pairs", [])

            # Build list of unanswered questions
            _pending_qs = []
            for _q_key in _question_matches:
                _q_key = _q_key.strip()
                _q_text = _Q_TEMPLATES[_q_key]["question"] if _q_key in _Q_TEMPLATES else _q_key
                if _qa_answered(state, _q_text):
                    continue
                if _q_key in _Q_TEMPLATES:
                    _pending_qs.append(_Q_TEMPLATES[_q_key])
                else:
                    _pending_qs.append({"question": _q_key, "options": ["Yes", "No", "Skip"]})

            # Use tabbed wizard for multiple questions, single ask for one
            _new_answers = []
            if len(_pending_qs) > 1:
                _tab_result = _ask_multi(_pending_qs)
                if _tab_result:
                    _new_answers = _tab_result
            elif len(_pending_qs) == 1:
                _single = _ask_q(**_pending_qs[0])
                if _single:
                    _new_answers = [_single]

            # Handle follow-up questions (e.g., "Which specific env?" after "Dev")
            if _new_answers:
                _follow_ups = []
                for _ans in _new_answers:
                    _q_key = None
                    for _mk, _mv in _Q_TEMPLATES.items():
                        if _mv.get("question") == _ans.get("question"):
                            _q_key = _mk
                            break
                    if _q_key and "follow_up" in _Q_TEMPLATES.get(_q_key, {}):
                        _fu = _Q_TEMPLATES[_q_key]["follow_up"]
                        if _fu.get("type") == "text":
                            # Free-text follow-up
                            try:
                                _fu_answer = input(f"  {_fu['question']} ").strip()
                            except (EOFError, KeyboardInterrupt):
                                _fu_answer = ""
                            if _fu_answer:
                                _follow_ups.append({
                                    "question": _fu["question"],
                                    "answer": _fu_answer,
                                    "option_idx": -1,
                                    "is_other": False,
                                })
                if _follow_ups:
                    _new_answers.extend(_follow_ups)

            if _new_answers:
                _qa_pairs.extend(_new_answers)
                if state.get("_chat_session"):
                    from .chat_history import save_qa_pairs as _persist_qa
                    _persist_qa(state["_chat_session"], _qa_pairs)
                _qa_context = _fmt_qa(_qa_pairs)
                if _qa_context:
                    # Inject fresh scratchpad into Q&A follow-up context
                    _qa_sys_ctx = system_context
                    try:
                        from code_agents.agent_system.session_scratchpad import SessionScratchpad
                        _sp_sid = (state.get("_chat_session") or {}).get("id")
                        if _sp_sid:
                            _mb = SessionScratchpad(_sp_sid, current_agent).format_for_prompt()
                            if _mb and _mb not in _qa_sys_ctx:
                                _qa_sys_ctx += f"\n\n{_mb}"
                    except Exception:
                        pass
                    _qa_msgs = [
                        {"role": "system", "content": _qa_sys_ctx},
                        {"role": "assistant", "content": _assistant_text},
                        {"role": "user", "content": _qa_context},
                    ]
                    _qa_response = _stream_with_spinner(
                        url, current_agent, _qa_msgs,
                        state.get("session_id"),
                        cwd=state.get("repo_path"),
                        state=state,
                        label="Processing your answers...",
                    )
                    if _qa_response:
                        full_response = _qa_response
                        full_text = "".join(_qa_response)
                        state["_last_output"] = full_text

    # Auto-compile check (only when build location is local or unset)
    _build_loc = os.getenv("CODE_AGENTS_BUILD_LOCATION", "ask").strip().lower()
    if full_response and _build_loc != "jenkins":
        from code_agents.analysis.compile_check import is_auto_compile_enabled, CompileChecker
        if is_auto_compile_enabled():
            _compile_cwd = state.get("repo_path", cwd)
            _compiler = CompileChecker(cwd=_compile_cwd)
            _full_text_for_compile = "".join(full_response)
            if _compiler.should_check(_full_text_for_compile):
                print(f"  {dim('Compile check...')}")
                _compile_result = _compiler.run_compile()
                if _compile_result.success:
                    _warn_str = f" with {len(_compile_result.warnings)} warning(s)" if _compile_result.warnings else ""
                    print(f"  {green(f'\u2713 Compilation successful ({_compile_result.elapsed:.1f}s){_warn_str}')}")
                else:
                    print(f"  {red(f'\u2717 Compilation failed ({_compile_result.elapsed:.1f}s):')}")
                    for _cerr in _compile_result.errors[:5]:
                        print(f"    {_cerr}")
                    if len(_compile_result.errors) > 5:
                        print(dim(f"    ... and {len(_compile_result.errors) - 5} more errors"))
                print()

    return full_response, effective_agent
