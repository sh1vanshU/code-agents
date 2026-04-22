"""CLI pair command — start AI pair programming mode."""

from __future__ import annotations

import logging

logger = logging.getLogger("code_agents.cli.cli_pair")


def cmd_pair():
    """Start AI pair programming mode — watches files and suggests improvements.

    Usage:
      code-agents pair                       # watch cwd, default patterns
      code-agents pair --watch-path src/     # watch specific directory
      code-agents pair --interval 2          # poll every 2s (default 1s)
      code-agents pair --quiet               # suppress info-level output
    """
    import os
    import sys

    from code_agents.domain.pair_mode import PairSession, format_pair_summary

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    watch_path = ""
    interval = 1.0
    quiet = False

    args = sys.argv[2:]  # skip "code-agents pair"
    i = 0
    while i < len(args):
        if args[i] == "--watch-path" and i + 1 < len(args):
            watch_path = args[i + 1]
            i += 2
        elif args[i] == "--interval" and i + 1 < len(args):
            try:
                interval = float(args[i + 1])
            except ValueError:
                pass
            i += 2
        elif args[i] == "--quiet":
            quiet = True
            i += 1
        else:
            i += 1

    session = PairSession(repo_path=repo_path, watch_path=watch_path)
    session._quiet = quiet

    print(f"  Pair programming mode — watching {repo_path}")
    if watch_path:
        print(f"  Watch path: {watch_path}")
    print(f"  Interval: {interval}s | Ctrl+C to stop\n")

    session.start()
    try:
        while session.active:
            import time
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        session.stop()
        print()
        print(format_pair_summary(session.suggestions))
