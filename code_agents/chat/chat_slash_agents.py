"""Agent & skill operations: /agent, /agents, /rules, /skills, /tokens, /stats, /memory."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_slash_agents")

from .chat_ui import bold, green, yellow, red, cyan, dim
from .chat_server import _get_agents


def _handle_agent_ops(command: str, arg: str, state: dict, url: str) -> Optional[str]:
    """Handle agent and skill related slash commands."""
    from .chat_welcome import AGENT_ROLES, _print_welcome

    if command == "/agents":
        agents = _get_agents(url)
        current = state.get("agent", "")
        print()
        print(bold("  Available agents:"))
        for name, display in sorted(agents.items()):
            marker = f" {green('← current')}" if name == current else ""
            role = AGENT_ROLES.get(name, "")
            print(f"    {cyan(name):<28} {dim(role)}{marker}")
        print()
        print(dim(f"  Switch: /agent <name>"))
        print()

    elif command == "/skills":
        from code_agents.agent_system.skill_loader import load_agent_skills
        from code_agents.core.config import settings
        all_skills = load_agent_skills(settings.agents_dir)
        target_agent = arg.strip() if arg else state.get("agent", "")
        print()
        if target_agent and target_agent in all_skills:
            skills = all_skills[target_agent]
            print(bold(f"  Skills for {cyan(target_agent)}:"))
            for s in skills:
                print(f"    {green(s.name):<24} {dim(s.description)}")
            print()
            print(dim(f"  Invoke: /{target_agent}:{skills[0].name}"))
        elif target_agent and target_agent not in all_skills:
            print(dim(f"  No skills defined for '{target_agent}'."))
            print(dim(f"  Create: agents/{target_agent.replace('-', '_')}/skills/<name>.md"))
        else:
            # Show all agents with skills
            print(bold("  Agent Skills:"))
            for agent_name, skills in sorted(all_skills.items()):
                skill_names = ", ".join(s.name for s in skills)
                print(f"    {cyan(agent_name):<24} {dim(skill_names)}")
            print()
            print(dim(f"  Details: /skills <agent>"))
            print(dim(f"  Invoke:  /<agent>:<skill>"))
        print()

    elif command == "/agent":
        if not arg:
            try:
                from .command_panel import show_panel
                from .command_panel_options import get_agent_options
                agents = _get_agents(url)
                current = state.get("agent", "")
                title, subtitle, opts = get_agent_options(current, sorted(agents.keys()))
                idx = show_panel(title, subtitle, opts)
                if idx is not None:
                    arg = opts[idx]["name"]
                else:
                    print(f"  {dim('Agent unchanged.')}")
                    return None
            except Exception:
                print(yellow("  Usage: /agent <name>  (e.g. /agent code-writer)"))
                return None
        agents = _get_agents(url)
        if arg not in agents:
            print(red(f"  Agent '{arg}' not found."))
            print(dim(f"  Available: {', '.join(sorted(agents.keys()))}"))
            return None
        # Show token summary for the outgoing agent before switching
        from code_agents.core.token_tracker import get_session_summary as _get_switch_summary
        usage = _get_switch_summary()
        if usage.get("messages", 0) > 0:
            old_agent = state.get("agent", "")
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            msgs = usage.get("messages", 0)
            print(f"  {dim('━━━')} {bold(old_agent)} {dim('━━━━━━━━━━━━━━━━━━━━━')}")
            print(f"  {dim('Messages:')} {msgs} · {dim('request:')} {inp:,} {dim('response:')} {out:,} tokens")
            print(f"  {dim('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')}")
            print()
        # Reset session tracker for the new agent
        from code_agents.core.token_tracker import init_session as _init_switch_session
        _init_switch_session(agent=arg)
        state["agent"] = arg
        state["session_id"] = None
        # Clear session scratchpad on agent switch (old facts may not apply)
        _sp_sid = (state.get("_chat_session") or {}).get("id")
        if _sp_sid:
            try:
                from code_agents.agent_system.session_scratchpad import SessionScratchpad
                SessionScratchpad(_sp_sid, arg).clear()
            except Exception:
                pass
        role = AGENT_ROLES.get(arg, agents.get(arg, ""))
        print()
        print(green(f"  ✓ Switched to: {bold(arg)} ({agents.get(arg, '')})"))
        print(f"    Session: {dim('new')}")
        print()
        _print_welcome(arg, state.get("repo_path", ""))

    elif command == "/memory":
        from code_agents.agent_system.agent_memory import load_memory, list_memories, clear_memory
        current = state.get("agent", "")
        if arg == "clear":
            cleared = clear_memory(current)
            print(green(f"  \u2713 Memory cleared for {current}") if cleared else dim(f"  No memory to clear for {current}"))
        elif arg == "list":
            memories = list_memories()
            if memories:
                print(bold("  Agent memories:"))
                for agent, lines in sorted(memories.items()):
                    print(f"    {cyan(agent)}: {lines} entries")
            else:
                print(dim("  No agent memories saved yet."))
        else:
            memory = load_memory(current)
            if memory:
                print(bold(f"  Memory for {cyan(current)}:"))
                for line in memory.splitlines():
                    print(f"    {dim(line)}")
            else:
                print(dim(f"  No memory for {current}. Agent will learn over time."))
        print()

    elif command == "/tokens":
        from code_agents.core.token_tracker import get_session_summary, get_daily_summary, get_monthly_summary, get_yearly_summary, get_model_breakdown
        session = get_session_summary()
        daily = get_daily_summary()
        monthly = get_monthly_summary()
        yearly = get_yearly_summary()

        print()
        print(bold("  Token Usage"))
        print()
        print(f"  {bold('This session:')}")
        print(f"    Messages:  {session['messages']}")
        print(f"    Tokens:    {session['input_tokens']:,} in → {session['output_tokens']:,} out ({session['total_tokens']:,} total)")
        if session['cost_usd']:
            print(f"    Cost:      ${session['cost_usd']:.4f}")
        print()
        print(f"  {bold('Today:')}")
        print(f"    Messages:  {daily['messages']}")
        print(f"    Tokens:    {daily['total_tokens']:,}")
        if daily['cost_usd']:
            print(f"    Cost:      ${daily['cost_usd']:.4f}")
        print()
        print(f"  {bold('This month:')}")
        print(f"    Messages:  {monthly['messages']}")
        print(f"    Tokens:    {monthly['total_tokens']:,}")
        if monthly['cost_usd']:
            print(f"    Cost:      ${monthly['cost_usd']:.4f}")
        print()
        print(f"  {bold('This year:')}")
        print(f"    Messages:  {yearly['messages']}")
        print(f"    Tokens:    {yearly['total_tokens']:,}")
        if yearly['cost_usd']:
            print(f"    Cost:      ${yearly['cost_usd']:.4f}")

        breakdown = get_model_breakdown()
        if breakdown:
            print()
            print(f"  {bold('By backend/model:')}")
            for b in breakdown:
                print(f"    {cyan(b['backend'])} / {b['model']}: {b['total_tokens']:,} tokens, {b['messages']} msgs")

        print()
        print(dim(f"  CSV: ~/.code-agents/token_usage.csv"))
        print()

    elif command in ("/cost", "/costs", "/spend"):
        # Rich cost dashboard
        mode = "today"
        if arg:
            if arg in ("daily", "monthly", "yearly", "all", "session", "model"):
                mode = arg
            elif arg.startswith("--"):
                mode = arg.lstrip("-")
        from code_agents.cli.cli_cost import _display_cost
        _display_cost(mode)
        print()

    elif command == "/rules":
        from code_agents.agent_system.rules_loader import list_rules
        repo = state.get("repo_path", ".")
        agent = state.get("agent", "")
        rules = list_rules(agent_name=agent, repo_path=repo)
        print()
        if not rules:
            print(dim(f"  No rules active for {bold(agent)}."))
            print(dim(f"  Create one: code-agents rules create --agent {agent}"))
        else:
            print(bold(f"  Rules for {cyan(agent)}:"))
            for r in rules:
                scope_label = green("global") if r["scope"] == "global" else cyan("project")
                target_label = "all agents" if r["target"] == "_global" else r["target"]
                print(f"    [{scope_label}] {bold(target_label)}")
                print(f"      {dim(r['preview'])}")
                print(f"      {dim(r['path'])}")
        print()

    elif command == "/stats":
        from code_agents.observability.telemetry import get_summary, get_agent_usage, is_enabled
        if not is_enabled():
            print(dim("  Telemetry disabled. Set CODE_AGENTS_TELEMETRY=true to enable."))
            print()
        else:
            days = int(arg) if arg and arg.isdigit() else 1
            label = "today" if days == 1 else f"last {days} days"
            s = get_summary(days)
            print()
            print(bold(f"  Stats ({label}):"))
            total_tokens = s["tokens_in"] + s["tokens_out"]
            print(f"    Sessions: {s['sessions']}  |  Messages: {s['messages']}  |  Tokens: {total_tokens:,}")
            print(f"    Commands: {s['commands']}  |  Errors: {s['errors']}  |  Est. cost: ${s['cost_estimate']:.2f}")
            agents = get_agent_usage(days)
            if agents:
                top = agents[0]
                pct = round(top["messages"] / max(s["messages"], 1) * 100)
                print(f"    Top agent: {top['agent']} ({pct}%)")
            print()
            print(dim(f"  Dashboard: http://localhost:{os.getenv('PORT', '8000')}/telemetry-dashboard"))
            print()

    elif command == "/corrections":
        from code_agents.agent_system.agent_corrections import CorrectionStore
        current = state.get("agent", "")
        repo = state.get("repo_path") or None
        store = CorrectionStore(current, project_path=repo)
        if arg == "clear":
            count = store.clear()
            print(green(f"  \u2713 Cleared {count} corrections for {current}") if count else dim(f"  No corrections to clear for {current}"))
        elif arg == "list" or not arg:
            entries = store.list_all()
            if entries:
                print(bold(f"  Corrections for {cyan(current)}: ({len(entries)} total)"))
                for i, e in enumerate(entries[-10:], 1):
                    ctx = f" [{e.context[:40]}]" if e.context else ""
                    print(f"    {dim(str(i))}. {e.original[:60]} {yellow('->')} {e.expected[:60]}{dim(ctx)}")
                if len(entries) > 10:
                    print(dim(f"    ... and {len(entries) - 10} more"))
            else:
                print(dim(f"  No corrections recorded for {current}."))
        else:
            print(yellow(f"  Usage: /corrections [list|clear]"))
        print()

    else:
        return "_not_handled"

    return None
