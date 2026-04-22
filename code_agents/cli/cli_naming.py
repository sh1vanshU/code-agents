"""CLI naming-audit command — enforce naming conventions in the target repo."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_naming")


def cmd_naming_audit():
    """Audit naming conventions in the codebase.

    Usage:
      code-agents naming-audit                     # scan entire repo
      code-agents naming-audit src/module.py       # scan a specific file or directory
      code-agents naming-audit --json              # output as JSON
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    target = ""
    as_json = False

    for a in args:
        if a == "--json":
            as_json = True
        elif a in ("--help", "-h"):
            print(cmd_naming_audit.__doc__)
            return
        elif not a.startswith("-"):
            target = a

    from code_agents.reviews.naming_audit import NamingAuditor, format_naming_report

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Auditing naming conventions in {repo_path}..."))

    auditor = NamingAuditor(cwd=repo_path)
    findings = auditor.audit(target=target)

    if as_json:
        import json
        data = [
            {
                "file": f.file, "line": f.line, "name": f.name,
                "issue": f.issue, "suggestion": f.suggestion,
                "severity": f.severity,
            }
            for f in findings
        ]
        print(json.dumps(data, indent=2))
    else:
        print(format_naming_report(findings))
