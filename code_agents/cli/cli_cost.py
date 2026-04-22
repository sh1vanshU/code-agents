"""CLI cost dashboard — surface token spend by agent, session, day, model."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_cost")


def cmd_cost():
    """Show token usage and cost breakdown.

    Usage:
      code-agents cost                # today's summary (default)
      code-agents cost --daily        # daily breakdown
      code-agents cost --monthly      # monthly breakdown
      code-agents cost --yearly       # yearly totals
      code-agents cost --all          # all-time summary
      code-agents cost --agent <name> # filter by agent
      code-agents cost --model        # breakdown by model
      code-agents cost --session      # current session stats
      code-agents cost --export csv   # dump to stdout as CSV
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]  # everything after 'cost'
    agent_filter = ""
    mode = "today"  # default

    # Parse args
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--daily":
            mode = "daily"
        elif a == "--monthly":
            mode = "monthly"
        elif a == "--yearly":
            mode = "yearly"
        elif a == "--all":
            mode = "all"
        elif a == "--session":
            mode = "session"
        elif a == "--model":
            mode = "model"
        elif a == "--agent" and i + 1 < len(args):
            agent_filter = args[i + 1]
            i += 1
        elif a == "--export" and i + 1 < len(args):
            _export_csv(args[i + 1], agent_filter)
            return
        elif a in ("--help", "-h"):
            print(cmd_cost.__doc__)
            return
        i += 1

    _display_cost(mode, agent_filter)


def _display_cost(mode: str, agent_filter: str = "") -> None:
    """Render cost dashboard with Rich tables."""
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        _rich = True
    except ImportError:
        _rich = False

    from code_agents.core.token_tracker import (
        get_session_summary, get_daily_summary, get_monthly_summary,
        get_yearly_summary, get_all_time_summary, get_model_breakdown,
        get_agent_breakdown, get_daily_history, USAGE_CSV_PATH,
    )

    if not USAGE_CSV_PATH.is_file():
        print(yellow("  No usage data found. Start chatting to record token usage."))
        return

    console = Console() if _rich else None

    if mode == "session":
        data = get_session_summary()
        if _rich:
            table = Table(title="Current Session", show_header=True, header_style="bold cyan")
            table.add_column("Metric", style="bold")
            table.add_column("Value", justify="right")
            table.add_row("Messages", f"{data['messages']:,}")
            table.add_row("Input tokens", f"{data['input_tokens']:,}")
            table.add_row("Output tokens", f"{data['output_tokens']:,}")
            table.add_row("Cache read", f"{data['cache_read_tokens']:,}")
            table.add_row("Cache write", f"{data['cache_write_tokens']:,}")
            table.add_row("Total tokens", f"{data['total_tokens']:,}")
            table.add_row("Cost", _format_cost(data['cost_usd']))
            table.add_row("Duration", f"{data['duration_ms'] / 1000:.1f}s")
            table.add_row("Agent", data.get('agent', '-'))
            table.add_row("Model", data.get('model', '-'))
            console.print(table)
        else:
            _print_summary("Current Session", data)
        return

    if mode == "model":
        rows = get_model_breakdown()
        if not rows:
            print(yellow("  No model data available."))
            return
        if _rich:
            table = Table(title="Token Usage by Model", show_header=True, header_style="bold cyan")
            table.add_column("Backend / Model", style="bold")
            table.add_column("Messages", justify="right")
            table.add_column("Input", justify="right")
            table.add_column("Output", justify="right")
            table.add_column("Total", justify="right")
            table.add_column("Cost", justify="right")
            for r in rows:
                label = f"{r['backend']} / {r['model']}"
                table.add_row(
                    label,
                    f"{r['messages']:,}",
                    f"{r['input_tokens']:,}",
                    f"{r['output_tokens']:,}",
                    f"{r['total_tokens']:,}",
                    _format_cost(r['cost_usd']),
                )
            console.print(table)
        else:
            for r in rows:
                print(f"  {r['backend']}/{r['model']}: {r['total_tokens']:,} tokens, {_format_cost(r['cost_usd'])}")
        return

    # Agent breakdown
    if agent_filter or mode == "today":
        agent_rows = get_agent_breakdown(agent_filter=agent_filter)
        if agent_rows and _rich:
            table = Table(
                title=f"Token Usage by Agent{f' (filter: {agent_filter})' if agent_filter else ' — Today'}",
                show_header=True, header_style="bold cyan",
            )
            table.add_column("Agent", style="bold")
            table.add_column("Messages", justify="right")
            table.add_column("Input", justify="right")
            table.add_column("Output", justify="right")
            table.add_column("Total", justify="right")
            table.add_column("Cost", justify="right")
            table.add_column("", justify="left")  # bar
            max_tokens = max(r["total_tokens"] for r in agent_rows) if agent_rows else 1
            for r in agent_rows:
                bar_len = int(20 * r["total_tokens"] / max_tokens) if max_tokens else 0
                bar = _cost_color_bar(r["cost_usd"], bar_len)
                table.add_row(
                    r["agent"] or "(unknown)",
                    f"{r['messages']:,}",
                    f"{r['input_tokens']:,}",
                    f"{r['output_tokens']:,}",
                    f"{r['total_tokens']:,}",
                    _format_cost(r["cost_usd"]),
                    bar,
                )
            # Totals row
            total_msgs = sum(r["messages"] for r in agent_rows)
            total_in = sum(r["input_tokens"] for r in agent_rows)
            total_out = sum(r["output_tokens"] for r in agent_rows)
            total_tok = sum(r["total_tokens"] for r in agent_rows)
            total_cost = sum(r["cost_usd"] for r in agent_rows)
            table.add_row(
                bold("TOTAL"), f"{total_msgs:,}", f"{total_in:,}",
                f"{total_out:,}", f"{total_tok:,}",
                _format_cost(total_cost), "",
                style="bold",
            )
            console.print(table)
        elif agent_rows:
            for r in agent_rows:
                print(f"  {r['agent']}: {r['total_tokens']:,} tokens, {_format_cost(r['cost_usd'])}")
        else:
            print(yellow("  No usage data for the specified filter."))
        if not agent_filter:
            # Also show today's summary
            data = get_daily_summary()
            print()
            _print_summary_rich(console, "Today's Summary", data) if _rich else _print_summary("Today", data)
        return

    # Period summaries
    if mode == "daily":
        history = get_daily_history(limit=14)
        if not history:
            print(yellow("  No daily data available."))
            return
        if _rich:
            table = Table(title="Daily Token Usage (last 14 days)", show_header=True, header_style="bold cyan")
            table.add_column("Date", style="bold")
            table.add_column("Messages", justify="right")
            table.add_column("Tokens", justify="right")
            table.add_column("Cost", justify="right")
            table.add_column("", justify="left")
            max_tok = max(r["total_tokens"] for r in history) if history else 1
            for r in history:
                bar_len = int(20 * r["total_tokens"] / max_tok) if max_tok else 0
                table.add_row(
                    r["date"], f"{r['messages']:,}", f"{r['total_tokens']:,}",
                    _format_cost(r["cost_usd"]),
                    _cost_color_bar(r["cost_usd"], bar_len),
                )
            console.print(table)
        else:
            for r in history:
                print(f"  {r['date']}: {r['total_tokens']:,} tokens, {_format_cost(r['cost_usd'])}")
        return

    # Monthly / yearly / all
    lookup = {
        "monthly": ("This Month", get_monthly_summary),
        "yearly": ("This Year", get_yearly_summary),
        "all": ("All Time", get_all_time_summary),
    }
    title, fn = lookup[mode]
    data = fn()
    if _rich:
        _print_summary_rich(console, title, data)
    else:
        _print_summary(title, data)


def _print_summary(title: str, data: dict) -> None:
    """Plain text summary."""
    print(f"\n  {title}")
    print(f"  {'─' * 40}")
    print(f"  Messages:      {data.get('messages', 0):,}")
    print(f"  Input tokens:  {data.get('input_tokens', 0):,}")
    print(f"  Output tokens: {data.get('output_tokens', 0):,}")
    print(f"  Total tokens:  {data.get('total_tokens', 0):,}")
    print(f"  Cost:          {_format_cost(data.get('cost_usd', 0))}")
    print()


def _print_summary_rich(console, title: str, data: dict) -> None:
    """Rich panel summary."""
    from rich.table import Table
    from rich.panel import Panel

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Messages", f"{data.get('messages', 0):,}")
    table.add_row("Input tokens", f"{data.get('input_tokens', 0):,}")
    table.add_row("Output tokens", f"{data.get('output_tokens', 0):,}")
    table.add_row("Cache read", f"{data.get('cache_read_tokens', 0):,}")
    table.add_row("Cache write", f"{data.get('cache_write_tokens', 0):,}")
    table.add_row("Total tokens", f"{data.get('total_tokens', 0):,}")
    table.add_row("Cost", _format_cost(data.get("cost_usd", 0)))
    console.print(Panel(table, title=title, border_style="cyan"))


def _format_cost(cost: float) -> str:
    """Format cost with color coding."""
    if cost <= 0:
        return "$0.00"
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _cost_color_bar(cost: float, length: int) -> str:
    """Generate a colored bar based on cost level."""
    if length <= 0:
        return ""
    if cost < 1.0:
        color = "green"
    elif cost < 10.0:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]{'█' * length}[/{color}]"


def _export_csv(fmt: str, agent_filter: str = "") -> None:
    """Export usage data as CSV to stdout."""
    import csv
    import sys as _sys

    from code_agents.core.token_tracker import USAGE_CSV_PATH, CSV_HEADERS

    if not USAGE_CSV_PATH.is_file():
        print("No usage data found.", file=_sys.stderr)
        return

    writer = csv.DictWriter(_sys.stdout, fieldnames=CSV_HEADERS)
    writer.writeheader()

    with open(USAGE_CSV_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if agent_filter and row.get("agent") != agent_filter:
                continue
            writer.writerow(row)
