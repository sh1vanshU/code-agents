"""CLI subcommand: code-agents validate-config [--json]."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_config_validator")


def cmd_validate_config(rest: list[str] | None = None):
    """Validate config files (YAML, JSON, TOML, .env) in the project.

    Usage:
      code-agents validate-config          # text report
      code-agents validate-config --json   # JSON output
    """
    rest = rest or sys.argv[2:]
    as_json = False

    for arg in rest:
        if arg == "--json":
            as_json = True
        elif arg in ("--help", "-h"):
            print(cmd_validate_config.__doc__)
            return

    from code_agents.devops.config_validator import ConfigValidator, format_config_report

    cwd = os.environ.get("TARGET_REPO_PATH") or os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    validator = ConfigValidator(cwd=cwd)
    findings = validator.validate()

    if as_json:
        import json
        data = [
            {
                "file": f.file, "line": f.line, "issue": f.issue,
                "severity": f.severity, "suggestion": f.suggestion,
            }
            for f in findings
        ]
        print(json.dumps(data, indent=2))
    else:
        print(format_config_report(findings))
