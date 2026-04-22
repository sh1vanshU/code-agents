"""CLI session-audit command — audit session management security patterns."""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_session_audit")


def cmd_session_audit():
    """Audit session management for security issues.

    Usage:
      code-agents session-audit                    # text report
      code-agents session-audit --format json      # JSON output
      code-agents session-audit --severity critical # filter by severity
      code-agents session-audit --output report.json
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    fmt = "text"
    output_path = None
    severity_filter = "all"

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--format" and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 1
        elif a == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 1
        elif a == "--severity" and i + 1 < len(args):
            severity_filter = args[i + 1].lower()
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_session_audit.__doc__)
            return
        i += 1

    if fmt not in ("text", "json"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: text, json"))
        return

    from code_agents.security.session_audit import (
        SessionAuditor,
        format_session_report,
        session_report_to_json,
    )

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Auditing session management in {repo_path}..."))

    auditor = SessionAuditor(cwd=repo_path)
    report = auditor.audit()

    if severity_filter != "all":
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        threshold = severity_order.get(severity_filter, 3)
        report.findings = [
            f for f in report.findings
            if severity_order.get(f.severity, 3) <= threshold
        ]

    if fmt == "json":
        output = json.dumps(session_report_to_json(report), indent=2)
    else:
        output = format_session_report(report)

    if output_path:
        from pathlib import Path
        out = Path(output_path).resolve()
        out.write_text(output, encoding="utf-8")
        print(green(f"  Report written to {out}"))
    else:
        print(output)
