"""CLI txn-flow command — transaction flow visualizer."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_txn_flow")


def cmd_txn_flow():
    """Visualize transaction flow from logs or code.

    Usage:
      code-agents txn-flow --from-code                     # scan code for state machines
      code-agents txn-flow --order-id ORD123 --env dev     # trace from ES logs
      code-agents txn-flow --from-code --format mermaid    # Mermaid sequence diagram
      code-agents txn-flow --from-code --format state      # Mermaid state diagram
      code-agents txn-flow --from-code --format terminal   # colored terminal output (default)
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]  # everything after 'txn-flow'

    order_id = ""
    env = "dev"
    from_code = False
    fmt = "terminal"

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--order-id" and i + 1 < len(args):
            order_id = args[i + 1]
            i += 1
        elif a == "--env" and i + 1 < len(args):
            env = args[i + 1]
            i += 1
        elif a == "--from-code":
            from_code = True
        elif a == "--format" and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_txn_flow.__doc__)
            return
        i += 1

    if not from_code and not order_id:
        print(yellow("  Specify --from-code or --order-id <id>"))
        print(dim("  Run: code-agents txn-flow --help"))
        return

    if fmt not in ("terminal", "mermaid", "sequence", "state"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: terminal, mermaid, sequence, state"))
        return

    # Lazy import
    from code_agents.domain.txn_flow import TxnFlowTracer

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    tracer = TxnFlowTracer(cwd=repo_path)

    if from_code:
        print(dim(f"  Scanning {repo_path} for state machines..."))
        flow = tracer.trace_from_code()
    else:
        print(dim(f"  Querying {env} logs for order {order_id}..."))
        flow = tracer.trace_from_logs(order_id, env=env)

    if not flow.steps:
        print(yellow("  No transaction steps found."))
        return

    if fmt == "terminal":
        print(tracer.generate_terminal(flow))
    elif fmt in ("mermaid", "sequence"):
        print(tracer.generate_sequence_diagram(flow))
    elif fmt == "state":
        print(tracer.generate_state_diagram(flow))
