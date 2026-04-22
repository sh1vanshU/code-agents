"""Async REPL — persistent input box during agent streaming.

Uses prompt_toolkit's ``prompt_async()`` + ``patch_stdout()`` so the
input prompt stays visible and functional while agent output streams
above it.  Streaming runs via ``asyncio.to_thread()`` in a background
thread.

This module is the async replacement for the sync ``while True`` REPL
loop in ``chat.py``.  It is called from ``_chat_main_inner()`` when
prompt_toolkit is available.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time as _time_mod

logger = logging.getLogger("code_agents.chat.chat_async_repl")


async def run_async_repl(
    *,
    state: dict,
    url: str,
    cwd: str,
    nickname: str,
    agent_name: str,
    pt_session,
    session_start: float,
) -> None:
    """Run the chat REPL with persistent input using async prompt."""
    from .chat_ui import bold, green, yellow, red, cyan, dim, agent_color
    from .chat_input import (
        get_message_queue, prompt_input_async,
        get_current_mode, set_mode, is_edit_mode,
        show_static_toolbar, clear_static_toolbar,
    )
    from .chat_response import process_streaming_response, handle_post_response
    from .chat_streaming import _stream_with_spinner, _print_session_summary
    from .chat_repl import run_agentic_followup_loop
    from .chat_server import _stream_chat
    from .chat_ui import _render_markdown, agent_color_fn
    from .chat_background import (
        OutputTarget, get_background_manager, start_ctrl_b_listener,
        stop_ctrl_b_listener, on_background_complete, show_task_selector,
        bring_to_foreground,
    )

    # Import shared helpers from chat.py
    from . import chat as _chat_mod
    _handle_command = _chat_mod._handle_command
    _build_system_context = _chat_mod._build_system_context
    _suggest_skills = _chat_mod._suggest_skills
    _parse_inline_delegation = _chat_mod._parse_inline_delegation
    _get_agents = _chat_mod._get_agents
    _init_plan_report = _chat_mod._init_plan_report
    AGENT_ROLES = _chat_mod.AGENT_ROLES

    # Activate patch_stdout — keeps input prompt fixed at bottom while output scrolls above
    from .chat_input import enter_persistent_input, exit_persistent_input
    enter_persistent_input()

    _mq = get_message_queue()
    _session_messages = 0
    _session_commands = 0
    _last_ctrl_c = _chat_mod._last_ctrl_c

    while True:
        try:
            # --- Input Phase (async — prompt stays visible) ---
            _queued_msg = _mq.dequeue()
            if _queued_msg:
                user_input = _queued_msg
                _q_remaining = _mq.size
                print(f"  {dim(f'⟫ Processing queued message' + (f' ({_q_remaining} more in queue)' if _q_remaining else ''))}")
            else:
                try:
                    line = await prompt_input_async(
                        pt_session, nickname,
                        state.get("agent", ""),
                        os.getenv("CODE_AGENTS_USER_ROLE", ""),
                    )
                    if line == "\x03":
                        raise KeyboardInterrupt
                    if line == "\x04":
                        raise EOFError
                except KeyboardInterrupt:
                    # Ctrl+C at prompt: clear input. Triple Ctrl+C within 2s exits.
                    import time as _t
                    _now = _t.time()
                    _ctrl_c_count = state.get("_ctrl_c_count", 0)
                    _ctrl_c_last = state.get("_ctrl_c_last", 0)
                    if _now - _ctrl_c_last < 2.0:
                        _ctrl_c_count += 1
                    else:
                        _ctrl_c_count = 1
                    state["_ctrl_c_count"] = _ctrl_c_count
                    state["_ctrl_c_last"] = _now
                    if _ctrl_c_count >= 3:
                        exit_persistent_input()
                        print()
                        print(dim("  Exiting code-agents chat..."))
                        _print_session_summary(session_start, _session_messages, state["agent"], _session_commands)
                        return
                    print()
                    if _ctrl_c_count == 2:
                        print(dim("  Press Ctrl+C once more to exit, or Ctrl+D."))
                    continue
                except EOFError:
                    # Ctrl+D: exit session (like Claude Code CLI)
                    exit_persistent_input()
                    print()
                    print(dim("  Exiting code-agents chat..."))
                    _print_session_summary(session_start, _session_messages, state["agent"], _session_commands)
                    return

                user_input = line.strip()
                if not user_input:
                    continue

                if _mq.agent_is_busy:
                    pos = _mq.enqueue(user_input)
                    print(f"  {dim(f'⟫ Message queued (position {pos}) — will process when agent is free')}")
                    continue

            # --- Resume after interrupt: "go ahead" / "continue" → resume hint ---
            if state.get("_interrupted"):
                from code_agents.agent_system.requirement_confirm import is_simple_confirmation
                if is_simple_confirmation(user_input):
                    user_input = "Continue from where you left off. Your previous response was interrupted."
                state["_interrupted"] = False

            # --- Pre-processing (sync — fast, no IO) ---

            # Skills suggestion
            try:
                from code_agents.core.config import settings as _sk_settings
                _suggest_skills(user_input, state["agent"], str(_sk_settings.agents_dir))
            except Exception:
                pass

            # Smart orchestrator — suggest best agent for the request.
            # On routing agents (agent-router, auto-pilot, unset): always suggest.
            # On specialist agents: only suggest if confidence is high (score >= 2).
            if not user_input.startswith("/"):
                try:
                    from code_agents.agent_system.smart_orchestrator import SmartOrchestrator
                    _orch = SmartOrchestrator()
                    _analysis = _orch.analyze_request(user_input)
                    if _analysis.get("should_delegate") and _analysis.get("best_agent"):
                        _best = _analysis["best_agent"]
                        _cur = state.get("agent", "")
                        _score = _analysis.get("score", 0)
                        _on_routing_agent = _cur in ("agent-router", "auto-pilot", "")

                        # Check if current agent also matches the request
                        _cur_score = 0
                        _cur_caps = _orch.AGENT_CAPABILITIES if hasattr(_orch, 'AGENT_CAPABILITIES') else {}
                        if not _cur_caps:
                            from code_agents.agent_system.smart_orchestrator import AGENT_CAPABILITIES, _keyword_matches
                            _cur_caps = AGENT_CAPABILITIES
                        if _cur in _cur_caps:
                            for _kw in _cur_caps[_cur].get("keywords", []):
                                if _keyword_matches(_kw, user_input.lower()):
                                    _cur_score += len(_kw.split())

                        # Only suggest switch if:
                        # 1. Best agent differs from current
                        # 2. On routing agent (always) OR score >= 2 (high confidence on specialist)
                        # 3. Current agent does NOT match the request (score=0)
                        if _best != _cur and (_on_routing_agent or (_score >= 2 and _cur_score == 0)):
                            # Auto-switch to specialist — no prompt needed
                            state["agent"] = _best
                            print()
                            print(f"  {cyan('\u2192')} {bold(_best)} specializes in this — auto-switching.")
                            print()
                except Exception:
                    pass

            # Auto-save session
            if not state.get("_chat_session"):
                from .chat_history import create_session
                state["_chat_session"] = create_session(state["agent"], state["repo_path"])
            from .chat_history import add_message as _add_msg
            _add_msg(state["_chat_session"], "user", user_input)

            # Session summary doc
            if not state.get("_md_file"):
                from datetime import datetime as _dt
                import random as _rnd
                from pathlib import Path
                _md_dir = Path.home() / ".code-agents" / "sessions"
                _md_dir.mkdir(parents=True, exist_ok=True)
                _adj = ["tejas", "dhira", "shubh", "veer", "pragya", "nirmala", "ujjwal", "shakti", "param", "divya", "satya", "mangal", "amrit", "prashant", "vijay"]
                _nouns = ["garuda", "simha", "vayu", "agni", "surya", "chandra", "indra", "rudra", "nakshatra", "vajra", "padma", "dharma", "vidya", "karma", "moksha"]
                _acts = ["gaman", "dhyan", "rachna", "vichar", "nirman", "sanchalan", "khoj", "sadhana", "yatra", "pariksha"]
                _sn = f"{_rnd.choice(_adj)}-{_rnd.choice(_acts)}-{_rnd.choice(_nouns)}"
                _md_path = _md_dir / f"{_sn}.md"
                state["_md_file"] = str(_md_path)
                state["_md_count"] = 0
                with open(_md_path, "w") as _mf:
                    _agent = state.get("agent", "chat")
                    _mf.write(f"# {_agent.upper()} — Summary Report\n\n")
                    _mf.write(f"**Agent:** {_agent}\n")
                    _mf.write(f"**Date:** {_dt.now().strftime('%Y-%m-%d %H:%M')}\n")
                    _mf.write(f"**Repo:** {state.get('repo_path', 'N/A')}\n\n---\n\n")
                print(f"  {dim(f'📄 Report: {_md_path}')}")

            if state.get("_md_file") and user_input and not user_input.startswith("/"):
                try:
                    with open(state["_md_file"], "a") as _mf:
                        state["_md_count"] = state.get("_md_count", 0) + 1
                        _mf.write(f"## Task {state['_md_count']}\n\n")
                except OSError:
                    pass

            # --- Slash commands (sync) ---
            if user_input.startswith("/"):
                # Handle /bg and /fg inline (need access to bg_manager + repl state)
                _bg_manager = get_background_manager()
                if user_input.strip() == "/bg" or user_input.startswith("/bg "):
                    _handle_bg_command(user_input, _bg_manager)
                    continue
                if user_input.strip() == "/fg" or user_input.startswith("/fg "):
                    _handle_fg_command(user_input, _bg_manager, state, url, cwd)
                    continue
                result = _handle_command(user_input, state, url)
                if result == "quit":
                    # Warn if background tasks are still running
                    if _bg_manager.has_tasks():
                        _running = _bg_manager.active_count()
                        if _running:
                            print(yellow(f"  \u26a0 {_running} background task(s) still running!"))
                            try:
                                import sys
                                sys.stdout.write(dim("  Abandon running tasks and exit? [y/N]: "))
                                sys.stdout.flush()
                                _confirm = sys.stdin.readline().strip().lower()
                            except (EOFError, KeyboardInterrupt):
                                _confirm = "n"
                            if _confirm not in ("y", "yes"):
                                print(dim("  Staying in chat."))
                                continue
                    exit_persistent_input()
                    _print_session_summary(session_start, _session_messages, state["agent"], _session_commands)
                    return
                continue

            # Requirement confirmation gate — spec before execution
            from code_agents.agent_system.requirement_confirm import (
                RequirementStatus, is_simple_confirmation, should_confirm,
                is_confirm_enabled,
            )
            _req_status = state.get("_req_status", RequirementStatus.NONE)

            if _req_status == RequirementStatus.PENDING:
                if is_simple_confirmation(user_input):
                    # User confirmed the spec — proceed with execution
                    state["_req_status"] = RequirementStatus.CONFIRMED
                    user_input = "The requirement has been confirmed. Please proceed with implementation."
                else:
                    # User sent edits or a new requirement while spec is pending
                    # Keep PENDING — agent will revise the spec
                    state["_confirmed_requirement"] = None
            elif _req_status in (RequirementStatus.NONE, RequirementStatus.CONFIRMED):
                if should_confirm(user_input, state):
                    state["_req_status"] = RequirementStatus.PENDING
                    state["_confirmed_requirement"] = None

            # --- Show mode banner if not in default chat mode ---
            from .chat_input import get_current_mode
            _current_mode = get_current_mode()
            if _current_mode == "plan":
                print()
                print(yellow("  ┌─ PLAN MODE ─────────────────────────────────────────────┐"))
                print(yellow("  │") + dim("  Agent will produce a plan, NOT execute.") + yellow("              │"))
                print(yellow("  │") + dim("  Switch to Chat mode: press Shift+Tab") + yellow("                │"))
                print(yellow("  └─────────────────────────────────────────────────────────┘"))
                print()
            elif _current_mode == "edit":
                print(f"  {green('✓ Accept edits on')} {dim('— agent will auto-execute all commands')}")
                print()

            # --- Build messages ---
            repo = state.get("repo_path", cwd)
            current_agent = state["agent"]
            system_context = _build_system_context(
                repo, current_agent,
                btw_messages=state.get("_btw_messages", []),
                superpower=state.get("superpower", False),
            )

            _existing_qa = state.get("_qa_pairs", [])
            if _existing_qa:
                from code_agents.agent_system.questionnaire import format_qa_for_prompt as _fmt_qa_ctx
                _qa_ctx = _fmt_qa_ctx(_existing_qa)
                if _qa_ctx:
                    system_context += f"\n\n{_qa_ctx}"

            # Inject requirement confirmation context
            _req_status = state.get("_req_status", RequirementStatus.NONE)
            if _req_status == RequirementStatus.PENDING:
                from code_agents.agent_system.requirement_confirm import build_spec_prompt
                system_context += build_spec_prompt()
            elif _req_status == RequirementStatus.CONFIRMED:
                _conf_req = state.get("_confirmed_requirement")
                if _conf_req:
                    from code_agents.agent_system.requirement_confirm import format_confirmed_spec
                    system_context += format_confirmed_spec(_conf_req)

            messages = [{"role": "system", "content": system_context}]
            chat_session = state.get("_chat_session")
            if chat_session and chat_session.get("messages"):
                for hist_msg in chat_session["messages"]:
                    if hist_msg.get("role") in ("user", "assistant"):
                        messages.append({"role": hist_msg["role"], "content": hist_msg["content"]})
            if not messages or messages[-1].get("content") != user_input:
                from .chat_clipboard import get_pending_images, build_multimodal_content
                _pending_imgs = get_pending_images()
                if _pending_imgs:
                    import re as _re
                    clean_text = _re.sub(r'\[image attached: [^\]]+\]\s*', '', user_input).strip()
                    content = build_multimodal_content(clean_text or "What's in this image?", _pending_imgs)
                    messages.append({"role": "user", "content": content})
                else:
                    messages.append({"role": "user", "content": user_input})

            _session_messages += 1

            # --- Streaming Phase (background thread — prompt stays visible) ---
            _mq.set_agent_busy()
            _ctrl_c_ref = [_last_ctrl_c]
            _bg_manager = get_background_manager()
            _output_target = OutputTarget()

            # Start Ctrl+B listener for backgrounding
            _ctrl_b_evt = start_ctrl_b_listener()

            # Launch streaming as an asyncio task so we can monitor Ctrl+B
            _streaming_future = asyncio.get_event_loop().run_in_executor(
                None,
                lambda: process_streaming_response(
                    url, current_agent, messages, state,
                    _last_ctrl_c_ref=_ctrl_c_ref,
                    output_target=_output_target,
                ),
            )

            _was_backgrounded = False

            # Poll loop: wait for streaming to finish OR Ctrl+B
            while not _streaming_future.done():
                if _ctrl_b_evt.is_set():
                    # Check if this was Ctrl+F (switch to existing bg task)
                    _is_ctrl_f = getattr(_ctrl_b_evt, '_ctrl_f', False)
                    if _is_ctrl_f:
                        _ctrl_b_evt._ctrl_f = False  # type: ignore[attr-defined]
                        _ctrl_b_evt.clear()
                        # Show task selector
                        _sel_task = show_task_selector(_bg_manager)
                        if _sel_task:
                            bring_to_foreground(_sel_task, state, url, cwd)
                        # Restart listener
                        stop_ctrl_b_listener()
                        _ctrl_b_evt = start_ctrl_b_listener()
                        continue

                    # Ctrl+B: background the current task
                    if not _bg_manager.can_create():
                        print(yellow(f"  Max {_bg_manager.max_concurrent} background tasks reached"))
                        _ctrl_b_evt.clear()
                        # Restart listener for next attempt
                        stop_ctrl_b_listener()
                        _ctrl_b_evt = start_ctrl_b_listener()
                        continue

                    # Switch output to buffer
                    _output_target.redirect_to_buffer()

                    # Create background task with deep copy of relevant state
                    import copy
                    _bg_state = copy.deepcopy({
                        k: v for k, v in state.items()
                        if k not in ("_chat_session",)  # don't deep-copy session obj
                    })
                    _sp_session_id = (state.get("_chat_session") or {}).get("id", "")

                    _bg_task = _bg_manager.create_task(
                        agent_name=current_agent,
                        user_input=user_input,
                        state=_bg_state,
                        output_target=_output_target,
                        scratchpad_session_id=_sp_session_id,
                        messages=messages,
                        system_context=system_context,
                    )
                    _bg_task.streaming_task = _streaming_future

                    # Register completion callback
                    def _on_done(fut, task=_bg_task):
                        try:
                            got, resp, interrupted = fut.result()
                            on_background_complete(task, got, resp, interrupted)
                            # In superpower mode, run agentic loop in background
                            if task.status == "done" and task.state.get("superpower") and resp:
                                import threading as _thr
                                def _bg_agentic():
                                    try:
                                        resp, _eff_agent = handle_post_response(
                                            resp, task.user_input, task.state, url,
                                            task.agent_name, task.system_context, cwd,
                                        )
                                        run_agentic_followup_loop(
                                            full_response=resp, cwd=cwd, url=url,
                                            state=task.state,
                                            current_agent=task.agent_name,
                                            effective_agent=_eff_agent,
                                            system_context=task.system_context,
                                            superpower=True,
                                        )
                                    except Exception:
                                        pass
                                _thr.Thread(target=_bg_agentic, daemon=True).start()
                        except Exception as e:
                            task.status = "error"
                            task.error = str(e)

                    _streaming_future.add_done_callback(_on_done)

                    print(dim(f"  \u27eb Task backgrounded: {_bg_task.display_name} (#{_bg_task.task_id})"))
                    stop_ctrl_b_listener()
                    _mq.set_agent_free()
                    _was_backgrounded = True
                    break

                await asyncio.sleep(0.05)

            stop_ctrl_b_listener()

            if _was_backgrounded:
                continue

            # Normal completion — get results
            try:
                got_text, full_response, _streaming_interrupted = await _streaming_future
            except KeyboardInterrupt:
                _mq.set_agent_free()
                _last_ctrl_c = _ctrl_c_ref[0]
                _chat_mod._last_ctrl_c = _last_ctrl_c
                state["_interrupted"] = True
                print()
                print(dim("  ⏸ Interrupted — say \"go ahead\" to resume, or type a new message."))
                print()
                continue

            _last_ctrl_c = _ctrl_c_ref[0]
            _chat_mod._last_ctrl_c = _last_ctrl_c
            _mq.set_agent_free()

            full_text = "".join(full_response) if full_response else ""

            if full_text:
                from code_agents.core.logging_config import log_agent_response
                _out_tokens = state.get("_last_usage", {}).get("output_tokens", 0) if state.get("_last_usage") else 0
                log_agent_response(current_agent, full_text, tokens=_out_tokens)

            if _streaming_interrupted:
                state["_last_output"] = full_text
                state["_interrupted"] = True
                if full_text and state.get("_chat_session"):
                    from .chat_history import add_message as _save_msg
                    _save_msg(state["_chat_session"], "assistant", full_text)
                print()
                print(dim("  ⏸ Interrupted — say \"go ahead\" to resume, or type a new message."))
                print()
                continue

            # --- Post-response (sync — runs in main thread) ---
            full_response, effective_agent = handle_post_response(
                full_response, user_input, state, url,
                current_agent, system_context, cwd,
            )

            # Requirement spec mode: capture spec text, skip agentic loop
            _req_status = state.get("_req_status", RequirementStatus.NONE)
            if _req_status == RequirementStatus.PENDING and full_response:
                state["_confirmed_requirement"] = "".join(full_response)
                continue  # Back to input — user confirms or edits

            # Agentic loop (sync — command approval needs tty)
            _, extra_cmds = run_agentic_followup_loop(
                full_response=full_response,
                cwd=cwd,
                url=url,
                state=state,
                current_agent=current_agent,
                effective_agent=effective_agent,
                system_context=system_context,
                superpower=state.get("superpower", False),
            )
            _session_commands += extra_cmds

        except KeyboardInterrupt:
            exit_persistent_input()
            print()
            print(dim("  Exiting code-agents chat..."))
            _print_session_summary(session_start, _session_messages, state["agent"], _session_commands)
            return

        except EOFError:
            # Spurious EOF from terminal state corruption (e.g. after raw mode
            # operations in agentic loop) — don't exit, just continue the REPL.
            # Intentional Ctrl+D is caught inside prompt_input_async and returns "".
            logger.debug("EOFError in REPL loop — continuing")
            continue

        # Check for completed background tasks and print notifications
        _bg_manager = get_background_manager()
        _done = _bg_manager.done_tasks()
        if _done:
            for _dt in _done:
                if not getattr(_dt, '_notified_in_repl', False):
                    _dt._notified_in_repl = True  # type: ignore[attr-defined]


def _handle_bg_command(cmd: str, bg_manager) -> None:
    """Handle /bg command — list tasks or cancel a task."""
    from .chat_ui import dim, bold, yellow, green, red
    from .chat_background import _format_elapsed

    parts = cmd.strip().split()
    # /bg — list all background tasks
    if len(parts) == 1:
        tasks = bg_manager.list_tasks()
        if not tasks:
            print(dim("  No background tasks."))
            return
        print(f"  {bold('Background tasks:')}")
        for t in tasks:
            elapsed = _format_elapsed(t.elapsed)
            if t.status == "running":
                icon = "\u27f3"
                color = yellow
            elif t.status == "done":
                icon = "\u2713"
                color = green
            else:
                icon = "\u2717"
                color = red
            summary = t.result_summary or t.user_input[:50]
            print(f"  #{t.task_id} {color(f'{icon} {t.display_name}')} ({t.status}, {elapsed}) \u2014 {dim(summary)}")
        print(dim(f"  Use /fg N to bring a task to foreground, /bg cancel N to cancel"))
        print()
        return

    # /bg cancel N
    if len(parts) >= 3 and parts[1] == "cancel":
        try:
            task_id = int(parts[2])
        except ValueError:
            print(yellow("  Usage: /bg cancel <task_id>"))
            return
        task = bg_manager.get_task(task_id)
        if not task:
            print(yellow(f"  No task #{task_id}"))
            return
        elapsed = _format_elapsed(task.elapsed)
        print(f"  Task #{task_id} {task.display_name} is {task.status} ({elapsed} elapsed).")
        try:
            import sys
            sys.stdout.write(dim("  Cancel? [y/N]: "))
            sys.stdout.flush()
            confirm = sys.stdin.readline().strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = "n"
        if confirm in ("y", "yes"):
            # Cancel the streaming task if running
            if task.streaming_task and not task.streaming_task.done():
                task.streaming_task.cancel()
            task.status = "error"
            task.error = "Cancelled by user"
            bg_manager.remove_task(task_id)
            print(dim(f"  \u27eb Task #{task_id} cancelled."))
        else:
            print(dim("  Not cancelled."))
        print()
        return

    print(yellow("  Usage: /bg [cancel N]"))


def _handle_fg_command(cmd: str, bg_manager, state: dict, url: str, cwd: str) -> None:
    """Handle /fg N — bring a background task to foreground."""
    from .chat_ui import dim, yellow
    from .chat_background import bring_to_foreground, show_task_selector

    parts = cmd.strip().split()
    if len(parts) == 1:
        # No task ID — show selector
        task = show_task_selector(bg_manager)
        if task:
            bring_to_foreground(task, state, url, cwd)
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        print(yellow("  Usage: /fg [task_id]"))
        return

    task = bg_manager.get_task(task_id)
    if not task:
        print(yellow(f"  No task #{task_id}"))
        return

    bring_to_foreground(task, state, url, cwd)
