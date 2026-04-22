"""CLI acquirer-health command — check payment acquirer integration health."""

from __future__ import annotations

import json
import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_acquirer")


def cmd_acquirer_health():
    """Check acquirer integration health — success rates, latency, errors.

    Usage:
      code-agents acquirer-health
      code-agents acquirer-health --env staging --window 30m
      code-agents acquirer-health --format json
      code-agents acquirer-health --logs /var/log/payments
    """
    args = sys.argv[2:]  # after 'code-agents acquirer-health'

    env = "prod"
    window = "1h"
    fmt = "text"
    log_dir = ""

    i = 0
    while i < len(args):
        if args[i] == "--env" and i + 1 < len(args):
            env = args[i + 1]; i += 2
        elif args[i] == "--window" and i + 1 < len(args):
            window = args[i + 1]; i += 2
        elif args[i] == "--format" and i + 1 < len(args):
            fmt = args[i + 1]; i += 2
        elif args[i] == "--logs" and i + 1 < len(args):
            log_dir = args[i + 1]; i += 2
        else:
            i += 1

    from code_agents.domain.acquirer_health import (
        AcquirerHealthMonitor,
        format_health_dashboard,
        report_to_dict,
    )

    monitor = AcquirerHealthMonitor()

    if log_dir:
        report = monitor.check_from_logs(log_dir=log_dir)
    else:
        report = monitor.check(env=env, window=window)

    if fmt == "json":
        print(json.dumps(report_to_dict(report), indent=2))
    else:
        print(format_health_dashboard(report))
