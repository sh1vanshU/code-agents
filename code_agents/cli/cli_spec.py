"""CLI command for spec-to-implementation validation."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_spec")


def cmd_spec_validate(args: list[str] | None = None):
    """Validate spec/PRD/Jira requirements against codebase implementation.

    Usage:
      code-agents spec-validate --spec "As a user, I want login with email"
      code-agents spec-validate --jira PROJ-123
      code-agents spec-validate --prd docs/prd.md
      code-agents spec-validate --prd docs/prd.md --format json

    Options:
      --spec <text>     Inline spec text (quoted)
      --jira <key>      Jira ticket key (requires JIRA_URL/JIRA_EMAIL/JIRA_TOKEN env)
      --prd <file>      Path to PRD/spec file (markdown, text)
      --format text|json Output format (default: text)
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = args if args is not None else sys.argv[2:]

    spec_text = ""
    jira_key = ""
    prd_file = ""
    fmt = "text"

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--spec" and i + 1 < len(args):
            spec_text = args[i + 1]
            i += 1
        elif a == "--jira" and i + 1 < len(args):
            jira_key = args[i + 1]
            i += 1
        elif a == "--prd" and i + 1 < len(args):
            prd_file = args[i + 1]
            i += 1
        elif a == "--format" and i + 1 < len(args):
            fmt = args[i + 1]
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_spec_validate.__doc__)
            return
        i += 1

    if not spec_text and not jira_key and not prd_file:
        print(yellow("  No spec source provided."))
        print(dim("  Use --spec, --jira, or --prd. See --help for usage."))
        return

    import os
    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    from code_agents.testing.spec_validator import SpecValidator, format_spec_report

    validator = SpecValidator(cwd=cwd)
    report = validator.validate(spec_text=spec_text, jira_key=jira_key, prd_file=prd_file)
    output = format_spec_report(report, fmt=fmt)
    print(output)
