"""CLI global audit — run all scanners, quality gates, produce unified report."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_audit")


def cmd_full_audit(rest: list[str] | None = None):
    """Global audit orchestrator — run ALL scanners and produce a unified report.

    Usage:
      code-agents full-audit                              # full audit
      code-agents full-audit --quick                      # skip slow scanners
      code-agents full-audit --category security,payment  # specific categories
      code-agents full-audit --format html --output report.html
      code-agents full-audit --ci                         # exit code 1 on critical
      code-agents full-audit --trend                      # show trend history
      code-agents full-audit --gates-only                 # only run quality gates
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    quick = False
    ci_mode = False
    gates_only = False
    show_trend = False
    categories: list[str] | None = None
    fmt = "terminal"
    output_path = ""

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--quick":
            quick = True
        elif a == "--ci":
            ci_mode = True
        elif a == "--gates-only":
            gates_only = True
        elif a == "--trend":
            show_trend = True
        elif a == "--category" and i + 1 < len(args):
            categories = [c.strip() for c in args[i + 1].split(",") if c.strip()]
            i += 1
        elif a == "--format" and i + 1 < len(args):
            fmt = args[i + 1]
            i += 1
        elif a == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_full_audit.__doc__)
            return
        i += 1

    import os
    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    from code_agents.security.audit_orchestrator import (
        AuditOrchestrator,
        format_audit_report,
        format_audit_json,
        format_audit_html,
    )

    orchestrator = AuditOrchestrator(cwd)

    # Trend-only mode
    if show_trend:
        history = orchestrator.get_trend_history(limit=20)
        if not history:
            print(yellow("  No audit history found. Run a full audit first."))
            return
        print(bold("\n  Audit Trend History\n"))
        for entry in history:
            score = entry["score"]
            ts = entry["timestamp"]
            crit = entry.get("critical", 0)
            bar_len = round(score / 100 * 20)
            bar = "\u2588" * bar_len + "\u2591" * (20 - bar_len)
            color = green if score >= 80 else (yellow if score >= 50 else red)
            print(f"  {dim(ts)}  {color(f'{score:>3}/100')} {bar}  critical={crit}")
        print()
        return

    # Run audit
    print(bold("\n  Running global audit...\n"))
    report = orchestrator.run(categories=categories, quick=quick, gates_only=gates_only)

    # Format output
    if fmt == "json":
        text = format_audit_json(report)
    elif fmt == "html":
        text = format_audit_html(report)
    else:
        text = format_audit_report(report)

    # Output
    if output_path:
        with open(output_path, "w") as f:
            f.write(text)
        print(green(f"  Report written to {output_path}"))
    else:
        print(text)

    # CI exit code
    if ci_mode and report.critical_count > 0:
        print(red(f"\n  CI FAIL: {report.critical_count} critical finding(s)"))
        sys.exit(1)
