"""CLI replay command — replay, list, fork, and search agent traces."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_replay")


def cmd_replay(rest: list[str] | None = None):
    """Agent Replay / Time Travel Debugging.

    Usage:
      code-agents replay                    # list recent traces
      code-agents replay list [--limit N]   # list traces
      code-agents replay show <trace_id>    # show trace steps
      code-agents replay play <trace_id>    # replay step-by-step
      code-agents replay fork <trace_id> <step_id>  # fork at step
      code-agents replay delete <trace_id>  # delete a trace
      code-agents replay search <query>     # search traces
    """
    from .cli_helpers import _colors

    bold, green, yellow, red, cyan, dim = _colors()
    args = rest or sys.argv[2:]

    if not args or args[0] in ("list", "-l"):
        _cmd_list(args[1:] if args and args[0] == "list" else args, bold, green, yellow, cyan, dim)
    elif args[0] == "show":
        _cmd_show(args[1:], bold, green, yellow, red, cyan, dim)
    elif args[0] == "play":
        _cmd_play(args[1:], bold, green, yellow, cyan, dim)
    elif args[0] == "fork":
        _cmd_fork(args[1:], bold, green, yellow, red, cyan, dim)
    elif args[0] == "delete":
        _cmd_delete(args[1:], bold, green, yellow, red, dim)
    elif args[0] == "search":
        _cmd_search(args[1:], bold, green, yellow, cyan, dim)
    elif args[0] in ("--help", "-h"):
        print(cmd_replay.__doc__)
    else:
        print(yellow(f"  Unknown replay subcommand: {args[0]}"))
        print(dim("  Run 'code-agents replay --help' for usage."))


def _cmd_list(args, bold, green, yellow, cyan, dim):
    from code_agents.agent_system.agent_replay import list_traces
    from datetime import datetime

    limit = 20
    for i, a in enumerate(args):
        if a == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                pass

    traces = list_traces(limit=limit)
    if not traces:
        print(yellow("  No traces found. Start a chat session with tracing enabled."))
        return

    print()
    print(bold("  Recent Agent Traces"))
    print()
    for t in traces:
        ts = datetime.fromtimestamp(t["created_at"]).strftime("%Y-%m-%d %H:%M")
        fork_info = f" {dim('(forked)')}" if t.get("forked_from") else ""
        print(
            f"  {cyan(t['trace_id'])}  {t['agent']:<16}  "
            f"{t['step_count']:>3} steps  {dim(ts)}{fork_info}"
        )
    print()
    print(dim(f"  {len(traces)} trace(s). Use 'code-agents replay show <id>' to inspect."))
    print()


def _cmd_show(args, bold, green, yellow, red, cyan, dim):
    from code_agents.agent_system.agent_replay import TracePlayer

    if not args:
        print(yellow("  Usage: code-agents replay show <trace_id>"))
        return

    trace_id = args[0]
    try:
        player = TracePlayer(trace_id)
        trace = player.load()
    except FileNotFoundError:
        print(red(f"  Trace not found: {trace_id}"))
        return

    from datetime import datetime

    print()
    print(bold(f"  Trace: {trace.trace_id}"))
    print(f"  Agent: {cyan(trace.agent)}  Session: {dim(trace.session_id)}")
    print(f"  Repo: {dim(trace.repo)}")
    ts = datetime.fromtimestamp(trace.created_at).strftime("%Y-%m-%d %H:%M:%S")
    print(f"  Created: {dim(ts)}")
    if trace.forked_from:
        print(f"  Forked from: {cyan(trace.forked_from)} at step {trace.fork_point}")
    print()

    for step in trace.steps:
        role_color = cyan if step.role == "user" else green if step.role == "assistant" else dim
        prefix = role_color(f"[{step.role}]")
        content_preview = step.content[:120].replace("\n", " ")
        if len(step.content) > 120:
            content_preview += "..."
        print(f"  {dim(f'#{step.step_id:>3}')} {prefix} {content_preview}")

    print()
    print(dim(f"  {len(trace.steps)} step(s). Use 'replay fork {trace.trace_id} <step>' to fork."))
    print()


def _cmd_play(args, bold, green, yellow, cyan, dim):
    from code_agents.agent_system.agent_replay import TracePlayer

    if not args:
        print(yellow("  Usage: code-agents replay play <trace_id> [--delay <sec>]"))
        return

    trace_id = args[0]
    delay = 0.5
    for i, a in enumerate(args):
        if a == "--delay" and i + 1 < len(args):
            try:
                delay = float(args[i + 1])
            except ValueError:
                pass

    try:
        player = TracePlayer(trace_id)
        player.load()
    except FileNotFoundError:
        from .cli_helpers import _colors
        _, _, _, red, _, _ = _colors()
        print(red(f"  Trace not found: {trace_id}"))
        return

    print()
    print(bold(f"  Replaying trace {cyan(trace_id)} (delay={delay}s)..."))
    print()

    def _step_cb(step):
        role_tag = f"[{step.role}]"
        content_preview = step.content[:200].replace("\n", " ")
        print(f"  {dim(f'#{step.step_id:>3}')} {cyan(role_tag)} {content_preview}")

    player.play(_step_cb, delay=delay)
    print()
    print(green("  Replay complete."))
    print()


def _cmd_fork(args, bold, green, yellow, red, cyan, dim):
    from code_agents.agent_system.agent_replay import TraceFork

    if len(args) < 2:
        print(yellow("  Usage: code-agents replay fork <trace_id> <step_id>"))
        return

    trace_id = args[0]
    try:
        step_id = int(args[1])
    except ValueError:
        print(red(f"  Invalid step_id: {args[1]}"))
        return

    try:
        forked = TraceFork.fork_at(trace_id, step_id)
    except FileNotFoundError:
        print(red(f"  Trace not found: {trace_id}"))
        return

    print()
    print(green(f"  Forked trace {cyan(trace_id)} at step {step_id}"))
    print(f"  New trace: {bold(forked.trace_id)} ({len(forked.steps)} steps)")
    print(dim("  Continue from this point with a new chat session."))
    print()


def _cmd_delete(args, bold, green, yellow, red, dim):
    from code_agents.agent_system.agent_replay import delete_trace

    if not args:
        print(yellow("  Usage: code-agents replay delete <trace_id>"))
        return

    trace_id = args[0]
    if delete_trace(trace_id):
        print(green(f"  Deleted trace: {trace_id}"))
    else:
        print(red(f"  Trace not found: {trace_id}"))


def _cmd_search(args, bold, green, yellow, cyan, dim):
    from code_agents.agent_system.agent_replay import search_traces
    from datetime import datetime

    if not args:
        print(yellow("  Usage: code-agents replay search <query>"))
        return

    query = " ".join(args)
    results = search_traces(query)

    if not results:
        print(yellow(f"  No traces matching '{query}'."))
        return

    print()
    print(bold(f"  Search results for '{query}'"))
    print()
    for t in results:
        ts = datetime.fromtimestamp(t["created_at"]).strftime("%Y-%m-%d %H:%M")
        print(
            f"  {cyan(t['trace_id'])}  {t['agent']:<16}  "
            f"{t['step_count']:>3} steps  {dim(ts)}"
        )
    print()
    print(dim(f"  {len(results)} result(s)."))
    print()
