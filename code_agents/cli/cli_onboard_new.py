"""CLI onboard-tour command — new developer onboarding tour."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_onboard_new")


def cmd_onboard_tour():
    """Generate an onboarding tour for new developers.

    Usage:
      code-agents onboard-tour              # generate full tour
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    if args and args[0] in ("--help", "-h"):
        print(cmd_onboard_tour.__doc__)
        return

    from code_agents.knowledge.onboarding_agent import OnboardingAgent

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    agent = OnboardingAgent(cwd)

    print(dim("  Generating onboarding tour..."))
    print()
    tour = agent.start_tour()
    print(tour)
