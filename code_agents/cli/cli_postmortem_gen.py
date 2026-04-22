"""CLI command for the Incident Postmortem Auto-Generator."""

from __future__ import annotations

import logging

logger = logging.getLogger("code_agents.cli.cli_postmortem_gen")


def cmd_postmortem_gen(rest: list[str] | None = None):
    """Generate structured incident postmortem with timeline, root cause, impact.

    Usage:
      code-agents postmortem-gen --incident INC-1234
      code-agents postmortem-gen --time-range "2h ago..now"
      code-agents postmortem-gen --title "API Gateway P1" --format terminal
      code-agents postmortem-gen --incident INC-5678 --time-range "2026-04-08 14:00..2026-04-08 16:00"
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    incident_id = ""
    time_range = ""
    title = ""
    fmt = "markdown"

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--incident" and i + 1 < len(rest):
            incident_id = rest[i + 1]; i += 2; continue
        elif a == "--time-range" and i + 1 < len(rest):
            time_range = rest[i + 1]; i += 2; continue
        elif a == "--title" and i + 1 < len(rest):
            title = rest[i + 1]; i += 2; continue
        elif a == "--format" and i + 1 < len(rest):
            fmt = rest[i + 1]; i += 2; continue
        i += 1

    from code_agents.domain.postmortem_gen import PostmortemGenerator

    print(f"\n  {bold('Incident Postmortem Auto-Generator')}")
    print(f"  {dim(f'Incident: {incident_id or 'auto'} | Range: {time_range or 'auto'} | Format: {fmt}')}\n")

    gen = PostmortemGenerator(cwd=_user_cwd())
    pm = gen.generate(incident_id=incident_id, time_range=time_range, title=title)

    if fmt == "terminal":
        print(gen.format_terminal(pm))
    else:
        print(gen.format_markdown(pm))


def _user_cwd() -> str:
    """Get the user's working directory."""
    import os
    return os.environ.get("TARGET_REPO_PATH", os.getcwd())
