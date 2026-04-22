"""CLI tail command — start live tail mode for log streaming."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_tail")


def cmd_tail():
    """Live tail mode — stream logs with anomaly detection.

    Usage:
      code-agents tail --service payments-api
      code-agents tail --service payments-api --env staging
      code-agents tail --service payments-api --level ERROR --interval 2
      code-agents tail --service payments-api --index app-logs-*
    """
    import asyncio

    args = sys.argv[2:]  # after 'code-agents tail'

    service = ""
    env = "dev"
    index = "logs-*"
    level = ""
    interval = 5.0

    i = 0
    while i < len(args):
        if args[i] == "--service" and i + 1 < len(args):
            service = args[i + 1]; i += 2
        elif args[i] == "--env" and i + 1 < len(args):
            env = args[i + 1]; i += 2
        elif args[i] == "--index" and i + 1 < len(args):
            index = args[i + 1]; i += 2
        elif args[i] == "--level" and i + 1 < len(args):
            level = args[i + 1]; i += 2
        elif args[i] == "--interval" and i + 1 < len(args):
            interval = float(args[i + 1]); i += 2
        else:
            if not service:
                service = args[i]
            i += 1

    if not service:
        print("\033[91mError: --service is required.\033[0m")
        print("Usage: code-agents tail --service <name> [--env dev] [--level ERROR] [--interval 5]")
        return

    from code_agents.observability.live_tail import TailConfig, run_tail

    config = TailConfig(
        service=service,
        env=env,
        index=index,
        log_level=level,
        poll_interval=interval,
    )

    try:
        asyncio.run(run_tail(config))
    except KeyboardInterrupt:
        print("\nTail stopped.")
