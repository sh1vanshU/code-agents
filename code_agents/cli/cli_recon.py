"""CLI recon command — payment reconciliation debugger."""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_recon")


def cmd_recon():
    """Reconcile payment orders against bank settlements from CSV files.

    Usage:
      code-agents recon --orders orders.csv --settlements settlements.csv
      code-agents recon --orders orders.csv --settlements bank.tsv --format json
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    orders_file = None
    settlements_file = None
    fmt = "text"

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--orders" and i + 1 < len(args):
            orders_file = args[i + 1]
            i += 1
        elif a == "--settlements" and i + 1 < len(args):
            settlements_file = args[i + 1]
            i += 1
        elif a == "--format" and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_recon.__doc__)
            return
        i += 1

    if not orders_file or not settlements_file:
        print(red("  Missing required flags: --orders and --settlements"))
        print(dim("  Usage: code-agents recon --orders orders.csv --settlements settlements.csv"))
        return

    if fmt not in ("text", "json"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: text, json"))
        return

    from code_agents.observability.recon_debug import ReconDebugger, format_recon_report, format_recon_json

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Orders file: {orders_file}"))
    print(dim(f"  Settlements file: {settlements_file}"))
    print()

    debugger = ReconDebugger(cwd=cwd)

    try:
        report = debugger.reconcile_from_files(orders_file, settlements_file)
    except (FileNotFoundError, ValueError) as exc:
        print(red(f"  Error: {exc}"))
        return

    if fmt == "json":
        print(json.dumps(format_recon_json(report), indent=2))
    else:
        print(format_recon_report(report))
