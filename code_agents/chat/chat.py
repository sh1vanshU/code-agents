"""
Interactive CLI chat REPL for Code Agents.

Supports all 14 agents — each stays in its role. Switch agents mid-session
with /agent <name>. Streams responses in real-time.

Usage:
    code-agents chat                    # default: code-reasoning
    code-agents chat code-writer        # specific agent
    code-agents chat --agent code-tester

Split into modules:
    chat_ui.py        — colors, spinners, selectors, markdown, welcome boxes
    chat_commands.py  — command extraction, execution, placeholders, trust
    chat_server.py    — server communication, streaming
    chat_validation.py   — pre-flight checks: server, backend, workspace trust
    chat_context.py   — system context building (rules, skills, memory, bash tool)
    chat_slash.py     — slash command handlers (/help, /agent, /plan, etc.)
    chat_streaming.py — streaming with activity indicators, session summary
    chat_welcome.py   — AGENT_ROLES, AGENT_WELCOME, welcome printing, agent selection
    chat.py              — this file: REPL loop orchestrator
    chat_state.py        — session dict, slash list, resume helpers
    chat_delegation.py   — inline /<agent> and /agent:skill parsing
    chat_repl.py         — agentic follow-up command loop
    chat_skill_runner.py — re-export of handle_post_response (skill/post hooks)
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time as _time_mod
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.chat")

# Ctrl+C graceful interrupt: timestamp of last Ctrl+C for double-press detection
_last_ctrl_c: float = 0.0

# Re-export from split modules so existing imports (tests, etc.) still work
from .chat_ui import (  # noqa: F401
    bold, green, yellow, red, cyan, dim, magenta,
    _rl_bold, _rl_green, _USE_COLOR,
    _visible_len, _render_markdown, _spinner,
    _ask_yes_no, _tab_selector, _amend_prompt,
    _print_welcome as _print_welcome_raw,
    agent_color, AGENT_COLORS,
    activity_indicator,
)
from .chat_commands import (  # noqa: F401
    _extract_commands, _extract_skill_requests, _extract_delegations,
    _resolve_placeholders,
    _offer_run_commands, _run_single_command,
    _save_command_to_rules, _is_command_trusted,
)
from .chat_server import (  # noqa: F401
    _server_url, _check_server, _check_workspace_trust,
    _get_agents, _stream_chat,
)
from .chat_validation import (  # noqa: F401
    check_server, ensure_server_running, check_workspace_trust,
    BackendValidator,
)

# Re-export from new split modules
from .chat_welcome import (  # noqa: F401
    AGENT_ROLES, AGENT_WELCOME,
    _print_welcome, _select_agent,
)
from .chat_context import (  # noqa: F401
    _suggest_skills, _build_system_context,
)
from .chat_slash import (  # noqa: F401
    _handle_command,
)
from .chat_streaming import (  # noqa: F401
    _format_session_duration, _stream_with_spinner,
    _print_session_summary,
)
from .chat_response import (  # noqa: F401
    process_streaming_response, handle_post_response,
    _format_elapsed,
)
from .chat_state import SLASH_COMMANDS, apply_resume_session, initial_chat_state
from .chat_delegation import parse_inline_delegation as _parse_inline_delegation
from .chat_repl import run_agentic_followup_loop
from .terminal_layout import exit_layout  # noqa: F401

# Whether fixed terminal layout is active (set by enter_layout)
_use_fixed = False


# ---------------------------------------------------------------------------
# Plan report (created only in plan mode)
# ---------------------------------------------------------------------------


def _init_plan_report(state: dict, user_input: str) -> None:
    """Create a .md plan report file when entering plan mode."""
    if state.get("_plan_report"):
        return  # already initialized
    from datetime import datetime as _dt
    from pathlib import Path

    _plans_dir = Path.home() / ".code-agents" / "plans"
    _plans_dir.mkdir(parents=True, exist_ok=True)
    _ts = _dt.now().strftime("%Y%m%d-%H%M%S")
    _agent = state.get("agent", "chat")
    _plan_path = _plans_dir / f"plan-{_agent}-{_ts}.md"
    state["_plan_report"] = str(_plan_path)

    with open(_plan_path, "w") as f:
        f.write(f"# Plan Report — {_agent}\n\n")
        f.write(f"**Date:** {_dt.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Agent:** {_agent}\n")
        f.write(f"**Repo:** {state.get('repo_path', 'N/A')}\n\n")
        f.write(f"---\n\n## Requirement\n\n")
        f.write(f"{user_input}\n\n")
        f.write(f"---\n\n## Plan\n\n")
        f.write(f"*(Agent will fill this in)*\n\n")

    from .chat_ui import dim
    print(f"  {dim(f'📋 Plan report: {_plan_path}')}")


def _append_plan_report(state: dict, section: str, content: str) -> None:
    """Append a section to the plan report file."""
    report_path = state.get("_plan_report")
    if not report_path:
        return
    try:
        with open(report_path, "a") as f:
            f.write(f"\n## {section}\n\n{content}\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Completer
# ---------------------------------------------------------------------------


def _make_completer(
    slash_commands: list[str], agent_names: list[str]
) -> callable:
    """
    Build a readline completer for slash commands, agent names, and skills.

    Completes:
    - First token starting with / -> slash commands + /agent-name + /agent:skill
    - Second token after '/agent ' -> bare agent names
    - /agent: -> skill names for that agent

    Returns a function suitable for readline.set_completer().
    """
    # Build skill completions: /agent:skill
    skill_completions: list[str] = []
    try:
        from code_agents.agent_system.skill_loader import load_agent_skills
        from code_agents.core.config import settings
        all_skills = load_agent_skills(settings.agents_dir)
        for agent, skills in all_skills.items():
            for s in skills:
                skill_completions.append(f"/{agent}:{s.name}")
    except Exception:
        pass

    agent_completions = [f"/{name}" for name in agent_names]
    all_completions = slash_commands + agent_completions + skill_completions

    def completer(text: str, idx: int) -> Optional[str]:
        try:
            import readline
            line = readline.get_line_buffer().lstrip()
        except (ImportError, AttributeError):
            line = text

        # Second word after '/agent ' -> complete bare agent names
        if line.startswith("/agent ") and not text.startswith("/"):
            matches = [n for n in agent_names if n.startswith(text)]
            return matches[idx] if idx < len(matches) else None

        # Second word after '/skills ' -> complete bare agent names
        if line.startswith("/skills ") and not text.startswith("/"):
            matches = [n for n in agent_names if n.startswith(text)]
            return matches[idx] if idx < len(matches) else None

        # Second word after '/session ', '/resume ', '/delete-chat ' -> complete session IDs
        if any(line.startswith(prefix) for prefix in ("/session ", "/resume ", "/delete-chat ")):
            try:
                from code_agents.chat.chat_history import list_sessions
                session_ids = [s["id"][:8] for s in list_sessions()]
                matches = [sid for sid in session_ids if sid.startswith(text)]
                return matches[idx] if idx < len(matches) else None
            except Exception:
                return None

        # First token starting with /
        if text.startswith("/"):
            matches = [c for c in all_completions if c.startswith(text)]
            return matches[idx] if idx < len(matches) else None

        return None

    return completer


# ---------------------------------------------------------------------------
# Main chat loop
# ---------------------------------------------------------------------------


def chat_main(args: list[str] | None = None):
    """Entry point for the interactive chat REPL."""
    try:
        _chat_main_inner(args)
    except KeyboardInterrupt:
        # Final fallback — should rarely reach here since REPL handles Ctrl+C
        print()
        print(dim("  Exiting code-agents chat..."))
    except Exception:
        # Log crash to file so it survives terminal close
        import traceback
        crash_file = Path.home() / ".code-agents" / "crash.log"
        crash_file.parent.mkdir(parents=True, exist_ok=True)
        with open(crash_file, "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"CRASH at {datetime.now().isoformat()}\n")
            traceback.print_exc(file=f)
        print(red(f"\n  Chat crashed. Traceback saved to: {crash_file}"))
        print(dim(f"  View with: cat {crash_file}"))
        raise


def _chat_main_inner(args: list[str] | None = None):
    """Inner REPL logic — wrapped by chat_main for crash logging."""
    args = args or []
    import time as _session_time
    _session_start = _session_time.monotonic()
    _session_messages = 0
    _session_commands = 0

    # Load env — global config + per-repo overrides
    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    from code_agents.core.env_loader import load_all_env
    load_all_env(cwd)

    # User nickname — from env or ask on first chat
    nickname = os.getenv("CODE_AGENTS_NICKNAME", "").strip() or ""
    if not nickname:
        # First chat — ask for nickname and persist
        try:
            print()
            answer = input(f"  {bold('Your name/nickname?')} [you]: ").strip()
            nickname = answer if answer else "you"
        except (EOFError, KeyboardInterrupt):
            nickname = "you"
        if nickname != "you":
            # Save to global config
            from code_agents.core.env_loader import GLOBAL_ENV_PATH
            GLOBAL_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(GLOBAL_ENV_PATH, "a") as f:
                f.write(f"\nCODE_AGENTS_NICKNAME={nickname}\n")
            os.environ["CODE_AGENTS_NICKNAME"] = nickname
    if not nickname:
        nickname = "you"

    # User designation — calibrate agent behavior
    role = os.getenv("CODE_AGENTS_USER_ROLE", "").strip()
    if not role:
        from code_agents.agent_system.questionnaire import ask_question
        print()
        answer = ask_question(
            question="What is your role/designation?",
            options=[
                "Junior Engineer",
                "Senior Engineer",
                "Lead Engineer",
                "Principal Engineer / Architect",
                "Engineering Manager",
            ],
            allow_other=True,
            default=2,  # Lead Engineer default
        )
        role = answer["answer"]
        # Save to env file
        try:
            env_file = Path.home() / ".code-agents" / "config.env"
            with open(env_file, "a") as f:
                f.write(f'\nCODE_AGENTS_USER_ROLE="{role}"\n')
            os.environ["CODE_AGENTS_USER_ROLE"] = role
        except OSError:
            pass
    # state["user_role"] set after state dict is created below

    url = _server_url()

    # Check server — offer to start if not running
    if not ensure_server_running(url, cwd):
        return

    # Fetch agents from server
    agents = _get_agents(url)
    if not agents:
        print()
        print(red("  No agents loaded from server."))
        print(f"  Server is running at {url} but returned no agents.")
        print()
        print(bold("  Troubleshoot:"))
        print(f"    code-agents doctor                  {dim('# diagnose issues')}")
        print(f"    code-agents logs                    {dim('# check server logs')}")
        print(f"    curl -s {url}/v1/agents | python3 -m json.tool")
        print()
        return

    # Determine agent: from args or interactive selection
    agent_name = None
    for i, a in enumerate(args):
        if a == "--agent" and i + 1 < len(args):
            agent_name = args[i + 1]
            break
        elif not a.startswith("-"):
            agent_name = a
            break

    # Check for --resume flag
    _resume_id = None
    for i, a in enumerate(args):
        if a == "--resume" and i + 1 < len(args):
            _resume_id = args[i + 1]
            break

    if agent_name and agent_name not in agents:
        print(red(f"  Agent '{agent_name}' not found."))
        agent_name = None

    if not agent_name:
        # Show banner then agent selection
        print()
        print(bold(cyan("  ╔══════════════════════════════════════════════╗")))
        print(bold(cyan("  ║       Code Agents — Interactive Chat         ║")))
        print(bold(cyan("  ╚══════════════════════════════════════════════╝")))

        agent_name = _select_agent(agents)
        if not agent_name:
            print(dim("  Cancelled."))
            return

    # Detect repository — prefer TARGET_REPO_PATH, then find git root from cwd
    # IMPORTANT: cwd might be ~/.code-agents (the tool's own repo), not the user's project
    target_repo = os.getenv("TARGET_REPO_PATH", "").strip()
    if target_repo and os.path.isdir(target_repo):
        repo_path = target_repo
        is_repo = os.path.isdir(os.path.join(repo_path, ".git"))
    else:
        repo_path = cwd
        is_repo = False
        check_dir = cwd
        while True:
            if os.path.isdir(os.path.join(check_dir, ".git")):
                repo_path = check_dir
                is_repo = True
                break
            parent = os.path.dirname(check_dir)
            if parent == check_dir:
                break  # reached filesystem root
            check_dir = parent
        # Guard: don't use ~/.code-agents as the target repo
        home_agents = str(Path.home() / ".code-agents")
        if repo_path == home_agents:
            # Wrong repo — use cwd instead
            repo_path = cwd
            is_repo = False

    # Pre-flight: check cursor-agent workspace trust
    if not check_workspace_trust(repo_path):
        return

    # Pre-flight: async backend connection validation (non-blocking background thread)
    _backend_validator = BackendValidator()
    _backend_validator.start()

    # State
    state = initial_chat_state(agent_name, repo_path, role)

    # Cleanup stale session scratchpads (older than 1 hour)
    try:
        from code_agents.agent_system.session_scratchpad import SessionScratchpad
        SessionScratchpad.cleanup_stale()
    except Exception:
        pass

    # Handle --resume flag: load a previous session by UUID
    if _resume_id:
        ok, resumed_agent = apply_resume_session(state, _resume_id)
        if ok:
            loaded = state["_chat_session"]
            agent_name = resumed_agent
            print()
            print(green(f"  ✓ Resumed: {bold(loaded['title'])}"))
            print(f"    Agent: {cyan(loaded['agent'])}  Messages: {len(loaded['messages'])}")
            recent = loaded["messages"][-4:]
            if recent:
                print()
                print(dim("  Recent context:"))
                for msg in recent:
                    role_label = green("you") if msg["role"] == "user" else magenta(loaded["agent"])
                    preview = msg["content"][:100]
                    if len(msg["content"]) > 100:
                        preview += "..."
                    print(f"    {bold(role_label)} › {dim(preview)}")
            print()
        else:
            print(red(f"  Session '{_resume_id}' not found."))
            print(dim("  Use 'code-agents sessions' to see session IDs."))
            return

    # Tab-completion for slash commands and agent names
    _slash_commands = SLASH_COMMANDS
    _completer = _make_completer(_slash_commands, list(agents.keys()))
    _has_readline = False

    # Try prompt_toolkit first (better UX), fall back to readline
    from .chat_input import create_session as _create_pt_session, prompt_input, _HAS_PT, get_message_queue, show_static_toolbar, clear_static_toolbar
    # Auto-cleanup old sessions at startup
    from .chat_history import auto_cleanup as _session_cleanup
    _session_cleanup()
    _history_path = str(Path.home() / ".code-agents" / "chat_input_history")
    _pt_session = None

    if _HAS_PT and os.getenv("CODE_AGENTS_SIMPLE_UI", "").lower() not in ("1", "true"):
        _pt_session = _create_pt_session(
            history_file=_history_path,
            slash_commands=_slash_commands,
            agent_names=list(agents.keys()) if agents else [],
        )

    if not _pt_session:
        # Fallback: use readline (old behavior)
        try:
            import readline
            import atexit
            readline.set_completer(_completer)
            readline.set_completer_delims(" \t")
            if "libedit" in (readline.__doc__ or ""):
                readline.parse_and_bind("bind ^I rl_complete")
            else:
                readline.parse_and_bind("tab: complete")
            _history_file = Path(_history_path)
            _history_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                readline.read_history_file(str(_history_file))
            except (FileNotFoundError, OSError):
                pass
            readline.set_history_length(500)
            atexit.register(readline.write_history_file, str(_history_file))
            _has_readline = True
        except ImportError:
            pass

    # Banner
    display_name = agents.get(agent_name, agent_name)
    role = AGENT_ROLES.get(agent_name, "")

    print()
    print(bold(cyan("  ╔══════════════════════════════════════════════╗")))
    print(bold(cyan("  ║       Code Agents — Interactive Chat         ║")))
    print(bold(cyan("  ╚══════════════════════════════════════════════╝")))
    print()
    print(f"  Agent:   {bold(agent_name)} ({display_name})")
    print(f"  Role:    {dim(role)}")
    if is_repo:
        # Show repo name prominently
        repo_name = os.path.basename(repo_path)
        print(f"  Repo:    {bold(cyan(repo_name))} ({repo_path})")
        print(f"           {dim('Agent will work on this project')}")
    else:
        print(f"  Dir:     {yellow(cwd)}")
        print(f"           {yellow('No git repo detected — agent has no project context')}")
    print(f"  Server:  {dim(url)}")
    print()
    print(dim("  Commands: /help /quit /agents /agent <name> /history /resume /clear"))
    print()

    # Welcome message
    _print_welcome(agent_name, repo_path)

    # Check background backend validation result (wait up to 2s if still running)
    if not _backend_validator.check(timeout=2.0):
        return

    # Sessions managed via /resume and /history commands in chat — no startup selector

    # Textual TUI (opt-in: CODE_AGENTS_TUI=1) — requires output module rewrites
    _use_textual = os.getenv("CODE_AGENTS_TUI", "").strip().lower() in ("1", "true", "yes")
    if _use_textual and sys.stdout.isatty():
        try:
            from .tui import run_chat_tui
            run_chat_tui(
                state=state,
                url=url,
                cwd=cwd,
                nickname=nickname,
                agent_name=agent_name,
                session_start=_session_start,
            )
            return
        except ImportError:
            logger.debug("Textual not available, falling back to async REPL")
        except Exception as e:
            logger.warning("Textual TUI failed: %s, falling back", e)

    # Default: async REPL with prompt_toolkit
    if _pt_session and _HAS_PT:
        import asyncio as _asyncio
        from .chat_async_repl import run_async_repl
        try:
            _asyncio.run(run_async_repl(
                state=state,
                url=url,
                cwd=cwd,
                nickname=nickname,
                agent_name=agent_name,
                pt_session=_pt_session,
                session_start=_session_start,
            ))
        except KeyboardInterrupt:
            print()
            print(dim("  Exiting code-agents chat..."))
        return

    # Fallback: sync REPL (no prompt_toolkit)
    global _last_ctrl_c
    # Activate patch_stdout — keeps input prompt fixed at bottom
    from .chat_input import enter_persistent_input, exit_persistent_input
    enter_persistent_input()

    while True:
        try:
            _mq = get_message_queue()
            _queued_msg = _mq.dequeue()
            if _queued_msg:
                user_input = _queued_msg
                print(f"  {dim('⟫ Processing queued message')}")
            else:
                try:
                    user_input = input("\u276f ").strip()
                except KeyboardInterrupt:
                    # Ctrl+C at prompt: clear input (like Claude Code CLI)
                    print()
                    continue
                except EOFError:
                    # Ctrl+D: exit session
                    print(dim("\n  Exiting code-agents chat..."))
                    _print_session_summary(_session_start, _session_messages, state["agent"], _session_commands)
                    return
                if not user_input:
                    continue

            # Resume after interrupt: "go ahead" / "continue" → resume hint
            if state.get("_interrupted"):
                from code_agents.agent_system.requirement_confirm import is_simple_confirmation
                if is_simple_confirmation(user_input):
                    user_input = "Continue from where you left off. Your previous response was interrupted."
                state["_interrupted"] = False

            # Suggest relevant skills based on user input keywords
            try:
                from code_agents.core.config import settings as _sk_settings
                _suggest_skills(user_input, state["agent"], str(_sk_settings.agents_dir))
            except Exception:
                pass

            # Smart orchestrator — suggest best agent for the request.
            # On routing agents: always suggest. On specialists: only if high confidence.
            if not user_input.startswith("/"):
                try:
                    from code_agents.agent_system.smart_orchestrator import SmartOrchestrator
                    _orch = SmartOrchestrator()
                    _analysis = _orch.analyze_request(user_input)
                    if _analysis.get("should_delegate") and _analysis.get("best_agent"):
                        _best = _analysis["best_agent"]
                        _cur = state.get("agent", "")
                        _score = _analysis.get("score", 0)
                        _on_routing = _cur in ("agent-router", "auto-pilot", "")

                        # Check if current agent also matches the request
                        _cur_score = 0
                        from code_agents.agent_system.smart_orchestrator import AGENT_CAPABILITIES, _keyword_matches
                        if _cur in AGENT_CAPABILITIES:
                            for _kw in AGENT_CAPABILITIES[_cur].get("keywords", []):
                                if _keyword_matches(_kw, user_input.lower()):
                                    _cur_score += len(_kw.split())

                        if _best != _cur and (_on_routing or (_score >= 2 and _cur_score == 0)):
                            # Auto-switch to specialist — no prompt needed
                            state["agent"] = _best
                            current_agent = _best
                            print()
                            print(f"  {cyan('\u2192')} {bold(_best)} specializes in this — auto-switching.")
                            print()
                except Exception:
                    pass

            # Auto-suggest on first message if it looks like a question/problem
            if _session_messages == 0 and not user_input.startswith("/"):
                _question_starters = ("how ", "why ", "i need", "i want", "help me", "can you", "what ", "is there")
                if any(user_input.lower().startswith(s) for s in _question_starters):
                    try:
                        from code_agents.knowledge.problem_solver import ProblemSolver
                        _solver = ProblemSolver()
                        _analysis = _solver.analyze(user_input)
                        if _analysis.recommended and _analysis.recommended.confidence > 0.5:
                            _r = _analysis.recommended
                            print(dim(f"  💡 Tip: {_r.title} — {_r.action}"))
                    except Exception:
                        pass

            # Auto-save: ensure a chat session exists and save user message
            if not state.get("_chat_session"):
                from .chat_history import create_session
                state["_chat_session"] = create_session(state["agent"], state["repo_path"])
            from .chat_history import add_message as _add_msg
            _add_msg(state["_chat_session"], "user", user_input)

            # Initialize session summary doc on first message
            if not state.get("_md_file"):
                from datetime import datetime as _dt
                import random as _rnd
                _md_dir = Path.home() / ".code-agents" / "sessions"
                _md_dir.mkdir(parents=True, exist_ok=True)
                _adjectives = ["tejas", "dhira", "shubh", "veer", "pragya", "nirmala", "ujjwal", "shakti", "param", "divya", "satya", "mangal", "amrit", "prashant", "vijay"]
                _nouns = ["garuda", "simha", "vayu", "agni", "surya", "chandra", "indra", "rudra", "nakshatra", "vajra", "padma", "dharma", "vidya", "karma", "moksha"]
                _actions = ["gaman", "dhyan", "rachna", "vichar", "nirman", "sanchalan", "khoj", "sadhana", "yatra", "pariksha"]
                _session_name = f"{_rnd.choice(_adjectives)}-{_rnd.choice(_actions)}-{_rnd.choice(_nouns)}"
                _md_path = _md_dir / f"{_session_name}.md"
                state["_md_file"] = str(_md_path)
                state["_md_count"] = 0
                with open(_md_path, "w") as _mf:
                    _agent = state.get("agent", "chat")
                    _mf.write(f"# {_agent.upper()} — Summary Report\n\n")
                    _mf.write(f"**Agent:** {_agent}\n")
                    _mf.write(f"**Date:** {_dt.now().strftime('%Y-%m-%d %H:%M')}\n")
                    _mf.write(f"**Repo:** {state.get('repo_path', 'N/A')}\n\n---\n\n")
                print(f"  {dim(f'📄 Report: {_md_path}')}")

            # Track requirement (brief, not full message)
            if state.get("_md_file") and user_input and not user_input.startswith("/"):
                try:
                    with open(state["_md_file"], "a") as _mf:
                        state["_md_count"] = state.get("_md_count", 0) + 1
                        _mf.write(f"## Task {state['_md_count']}\n\n")
                except OSError:
                    pass

            # Slash commands
            if user_input.startswith("/"):
                # Is this an agent name? e.g. /code-reasoning, /code-writer
                available_agents = _get_agents(url) if not hasattr(state, "_agents_cache") else state.get("_agents_cache", {})
                if not available_agents:
                    available_agents = _get_agents(url)
                state["_agents_cache"] = available_agents

                delegate_agent, delegate_prompt = _parse_inline_delegation(
                    user_input, available_agents
                )

                if delegate_agent and delegate_prompt:
                    # Inline delegation — visible context switch
                    role = AGENT_ROLES.get(delegate_agent, "")
                    _ic = {"code-reasoning":"36","code-writer":"32","code-reviewer":"33","code-tester":"36","redash-query":"34","git-ops":"35","test-coverage":"32","jenkins-cicd":"31","argocd-verify":"35","qa-regression":"31","jira-ops":"34","auto-pilot":"1;36"}.get(delegate_agent,"37")
                    _if = lambda s: f"\033[{_ic}m{s}\033[0m" if sys.stdout.isatty() else s
                    print()
                    print(f"  {_if('┌──')} {_if(bold(f'↘ SWITCHING TO {delegate_agent.upper()}'))} {_if('──')}")
                    if role:
                        print(f"  {_if('│')}  {dim(role)}")
                    print(f"  {_if('└──')}")
                    print()

                    # Build messages with repo context + bash tool + rules
                    repo = state.get("repo_path", cwd)
                    system_context = _build_system_context(repo, delegate_agent, btw_messages=state.get("_btw_messages", []), superpower=state.get("superpower", False))
                    delegate_messages = [
                        {"role": "system", "content": system_context},
                        {"role": "user", "content": delegate_prompt},
                    ]

                    agent_label = bold(agent_color(delegate_agent)(delegate_agent.upper()))
                    sys.stdout.write(f"\n  {agent_label} › ")
                    sys.stdout.flush()

                    got_text = False
                    delegate_response: list[str] = []
                    _delegate_interrupted = False
                    try:
                        for piece_type, piece_content in _stream_chat(
                            url, delegate_agent, delegate_messages, None,
                            cwd=state.get("repo_path"),
                        ):
                            if piece_type == "text":
                                got_text = True
                                delegate_response.append(piece_content)
                                # Word wrap delegate response too
                                import shutil as _dshutil
                                _dwrap = _dshutil.get_terminal_size((80, 24)).columns - 10
                                _drendered = _render_markdown(piece_content)
                                _dout = []
                                _dpos = 0
                                for _dc in _drendered:
                                    if _dc == "\n":
                                        _dout.append("\n    ")
                                        _dpos = 0
                                    else:
                                        _dpos += 1
                                        if _dpos >= _dwrap and _dc == " ":
                                            _dout.append("\n    ")
                                            _dpos = 0
                                        else:
                                            _dout.append(_dc)
                                sys.stdout.write("".join(_dout))
                                sys.stdout.flush()
                            elif piece_type == "reasoning":
                                _rt = piece_content.strip()
                                if _rt and not (_rt.startswith("**") or "```" in _rt or "{" in _rt or "Tool Result" in _rt):
                                    sys.stdout.write(f"\n    {dim(_rt[:80])}")
                                    sys.stdout.flush()
                            elif piece_type == "error":
                                print(red(f"\n  Error: {piece_content}"))
                    except KeyboardInterrupt:
                        _delegate_interrupted = True
                        now = _time_mod.time()
                        if now - _last_ctrl_c < 1.5:
                            print()
                            if _use_fixed: exit_layout()
                            print(dim("  Exiting code-agents chat..."))
                            _print_session_summary(_session_start, _session_messages, state["agent"], _session_commands)
                            return
                        _last_ctrl_c = now
                        print()
                        print(yellow("  Response interrupted. Type your message or Ctrl+C again to exit."))

                    if got_text and not _delegate_interrupted:
                        print()
                    print()

                    # Offer to run detected shell commands
                    if delegate_response:
                        cmds = _extract_commands("".join(delegate_response))
                        if cmds:
                            _offer_run_commands(cmds, state.get("repo_path", cwd), agent_name=delegate_agent, superpower=state.get("superpower", False))

                    # Back to current agent — visible return
                    current = state["agent"]
                    _rc = {"auto-pilot":"37","code-writer":"32","code-reviewer":"33"}.get(current,"37")
                    _rf = lambda s: f"\033[{_rc}m{s}\033[0m" if sys.stdout.isatty() else s
                    print(f"\n  {_rf('┌──')} {_rf(f'↗ BACK TO {current.upper()}')} {_rf('──')}")
                    print(f"  {_rf('└──')}")
                    print()
                    continue

                elif delegate_agent and not delegate_prompt:
                    # Just agent name with no prompt — switch permanently (same as /agent)
                    _handle_command(f"/agent {delegate_agent}", state, url)
                    continue

                # Regular slash command
                result = _handle_command(user_input, state, url)
                if result == "quit":
                    _print_session_summary(_session_start, _session_messages, state["agent"], _session_commands)
                    break
                elif result == "exec_feedback":
                    # /execute ran a command — feed output to agent
                    fb = state.pop("_exec_feedback", None)
                    if fb:
                        repo = state.get("repo_path", cwd)
                        current_agent = state["agent"]
                        system_context = _build_system_context(repo, current_agent, btw_messages=state.get("_btw_messages", []), superpower=state.get("superpower", False))

                        output_preview = fb["output"][:3000] if fb["output"] else "(no output)"
                        feedback = (
                            f"I ran this command:\n{fb['command']}\n\n"
                            f"Output:\n{output_preview}\n\n"
                            f"Please analyze the output and suggest next steps."
                        )

                        show_static_toolbar()
                        # Include conversation history so agent retains context
                        # Inject fresh scratchpad
                        _fu_ctx = system_context
                        try:
                            from code_agents.agent_system.session_scratchpad import SessionScratchpad
                            _sp_sid = (state.get("_chat_session") or {}).get("id")
                            if _sp_sid:
                                _mb = SessionScratchpad(_sp_sid, current_agent).format_for_prompt()
                                if _mb and _mb not in _fu_ctx:
                                    _fu_ctx += f"\n\n{_mb}"
                        except Exception:
                            pass
                        _followup = [{"role": "system", "content": _fu_ctx}]
                        _cs = state.get("_chat_session")
                        if _cs and _cs.get("messages"):
                            for _hm in _cs["messages"]:
                                if _hm.get("role") in ("user", "assistant"):
                                    _followup.append({"role": _hm["role"], "content": _hm["content"]})
                        _followup.append({"role": "user", "content": feedback})
                        _stream_with_spinner(
                            url, current_agent,
                            _followup,
                            state.get("session_id"),
                            cwd=state.get("repo_path"),
                            state=state,
                            label="Analyzing output...",
                        )
                        clear_static_toolbar()
                continue

            # Check pair mode for file changes
            if state.get("_pair_mode") and state["_pair_mode"].active:
                _pair_changes = state["_pair_mode"].check_changes()
                if _pair_changes:
                    _pair_summary = state["_pair_mode"].format_changes_summary(_pair_changes)
                    print(dim(f"  [pair] Detected changes:"))
                    print(dim(_pair_summary))
                    _pair_prompt = state["_pair_mode"].build_review_prompt(_pair_changes)
                    if _pair_prompt and not user_input.startswith("/"):
                        # Prepend pair review to user's message
                        user_input = f"{_pair_prompt}\n\n---\nUser message: {user_input}"

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

            # Auto plan-mode: detect complex tasks and offer plan mode
            from .chat_input import get_current_mode, set_mode, is_edit_mode
            if get_current_mode() == "chat" and not state.get("_skip_plan_suggest"):
                from .chat_complexity import should_suggest_plan_mode
                _should_plan, _plan_score, _plan_reasons = should_suggest_plan_mode(user_input)
                if _should_plan:
                    print()
                    print(yellow("  ⚡ This looks like a complex task") + dim(f" (score: {_plan_score})"))
                    print(dim(f"     Detected: {', '.join(_plan_reasons[:4])}"))
                    print()
                    print(f"  How would you like to proceed?")
                    print()
                    from code_agents.agent_system.questionnaire import _question_selector
                    _plan_options = [
                        "Plan first, then execute",
                        "Plan first, auto-accept edits",
                        "Just do it (skip planning)",
                    ]
                    _plan_idx = _question_selector("  Approach:", _plan_options, default=0)
                    if _plan_idx == 0:
                        set_mode("plan")
                        _init_plan_report(state, user_input)
                        print(green("  ✓ Switched to Plan mode. Agent will propose a plan first."))
                        print()
                    elif _plan_idx == 1:
                        set_mode("plan")
                        state["_auto_edit_after_plan"] = True
                        _init_plan_report(state, user_input)
                        print(green("  ✓ Plan mode → auto-accept edits after approval."))
                        print()
                    else:
                        print(dim("  Proceeding directly."))
                        print()

            # Create plan report when entering plan mode via shift+tab
            if get_current_mode() == "plan" and not state.get("_plan_report"):
                _init_plan_report(state, user_input)

            # Show mode banner if not in default chat mode
            if get_current_mode() == "plan":
                print()
                print(yellow("  ┌─ PLAN MODE ─────────────────────────────────────────────┐"))
                print(yellow("  │") + dim("  Agent will produce a plan, NOT execute.") + yellow("              │"))
                print(yellow("  │") + dim("  Switch to Chat mode: press Shift+Tab") + yellow("                │"))
                print(yellow("  └─────────────────────────────────────────────────────────┘"))
                print()
            elif get_current_mode() == "edit":
                print(f"  {green('✓ Accept edits on')} {dim('— agent will auto-execute all commands')}")
                print()

            # Build messages — inject repo context + bash tool + rules
            repo = state.get("repo_path", cwd)
            current_agent = state["agent"]
            system_context = _build_system_context(repo, current_agent, btw_messages=state.get("_btw_messages", []), superpower=state.get("superpower", False))

            # Inject previous Q&A answers into system context so agent doesn't re-ask
            _existing_qa = state.get("_qa_pairs", [])
            if _existing_qa:
                from code_agents.agent_system.questionnaire import format_qa_for_prompt as _fmt_qa_ctx
                _qa_ctx = _fmt_qa_ctx(_existing_qa)
                if _qa_ctx:
                    system_context += f"\n\n{_qa_ctx}"

            # Inject session scratchpad (persisted facts from previous turns)
            _scratchpad_session_id = (state.get("_chat_session") or {}).get("id")
            if _scratchpad_session_id:
                try:
                    from code_agents.agent_system.session_scratchpad import SessionScratchpad
                    _scratchpad = SessionScratchpad(_scratchpad_session_id, current_agent)
                    _memory_block = _scratchpad.format_for_prompt()
                    if _memory_block:
                        system_context += f"\n\n{_memory_block}"
                except Exception:
                    pass

            # Inject query-specific knowledge graph context
            try:
                from code_agents.knowledge.knowledge_graph import KnowledgeGraph
                _kg = KnowledgeGraph(repo)
                if _kg.is_ready and len(user_input) > 15:
                    _kg_ctx = _kg.get_context_for_prompt(user_input, max_tokens=1200)
                    if _kg_ctx:
                        system_context += f"\n\n{_kg_ctx}"
            except Exception:
                pass

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

            # Send full conversation history (like Claude CLI)
            messages = [{"role": "system", "content": system_context}]
            chat_session = state.get("_chat_session")
            if chat_session and chat_session.get("messages"):
                for hist_msg in chat_session["messages"]:
                    # Skip current message (already being added below)
                    if hist_msg.get("role") in ("user", "assistant"):
                        messages.append({"role": hist_msg["role"], "content": hist_msg["content"]})
            # Only add current user_input if not already the last message in history
            if not messages or messages[-1].get("content") != user_input:
                # Check for pending image attachments (Ctrl+V paste)
                from .chat_clipboard import get_pending_images, build_multimodal_content
                _pending_imgs = get_pending_images()
                if _pending_imgs:
                    # Strip "[image attached: ...]" markers from text
                    import re as _re
                    clean_text = _re.sub(r'\[image attached: [^\]]+\]\s*', '', user_input).strip()
                    content = build_multimodal_content(clean_text or "What's in this image?", _pending_imgs)
                    messages.append({"role": "user", "content": content})
                else:
                    messages.append({"role": "user", "content": user_input})

            _session_messages += 1

            # Stream response with activity indicators + post-response processing
            current_agent = state["agent"]

            # Stream response synchronously — patch_stdout keeps prompt visible
            _mq.set_agent_busy()

            _ctrl_c_ref = [_last_ctrl_c]
            try:
                got_text, full_response, _streaming_interrupted = process_streaming_response(
                    url, current_agent, messages, state,
                    _last_ctrl_c_ref=_ctrl_c_ref,
                )
            except KeyboardInterrupt:
                _mq.set_agent_free()
                _last_ctrl_c = _ctrl_c_ref[0]
                print(dim("  Exiting code-agents chat..."))
                _print_session_summary(_session_start, _session_messages, state["agent"], _session_commands)
                exit_persistent_input()
                return
            _last_ctrl_c = _ctrl_c_ref[0]
            _mq.set_agent_free()

            full_text = "".join(full_response) if full_response else ""

            # Log agent response
            if full_text:
                from code_agents.core.logging_config import log_agent_response
                _out_tokens = state.get("_last_usage", {}).get("output_tokens", 0) if state.get("_last_usage") else 0
                log_agent_response(current_agent, full_text, tokens=_out_tokens)

            if _streaming_interrupted:
                # Save partial response
                state["_last_output"] = full_text
                if full_text and state.get("_chat_session"):
                    from .chat_history import add_message as _save_msg
                    _save_msg(state["_chat_session"], "assistant", full_text)
                continue

            # Post-response handling (saving, scoring, verification, skills, delegation, compile check)
            full_response, effective_agent = handle_post_response(
                full_response, user_input, state, url,
                current_agent, system_context, cwd,
            )

            # Requirement spec mode: capture spec text, skip agentic loop
            _req_status = state.get("_req_status", RequirementStatus.NONE)
            if _req_status == RequirementStatus.PENDING and full_response:
                state["_confirmed_requirement"] = "".join(full_response)
                continue  # Back to input — user confirms or edits

            # Agentic loop: detect ```bash`` blocks -> run -> feed output back
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
            # Double Ctrl+C propagated from streaming or other code paths
            print()
            if _use_fixed: exit_layout()
            print(dim("  Exiting code-agents chat..."))
            _print_session_summary(_session_start, _session_messages, state["agent"], _session_commands)
            # Use os._exit to avoid threading shutdown exception on Ctrl+C
            # (concurrent.futures thread pool join interrupted by KeyboardInterrupt)
            import os as _os_exit
            _os_exit._exit(0)

        except EOFError:
            # Spurious EOF from terminal state corruption — continue REPL
            continue
