"""CLI command: code-agents audit-idempotency — Idempotency Key Auditor."""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_idempotency")


def cmd_idempotency(rest: list[str] | None = None):
    """Scan payment endpoints for idempotency issues.

    Usage:
      code-agents audit-idempotency                      # all findings
      code-agents audit-idempotency --severity critical   # critical only
      code-agents audit-idempotency --format json         # JSON output
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    severity_filter = "all"
    output_format = "text"

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--severity" and i + 1 < len(rest):
            severity_filter = rest[i + 1].lower()
            i += 2
            continue
        if a == "--format" and i + 1 < len(rest):
            output_format = rest[i + 1].lower()
            i += 2
            continue
        i += 1

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    from code_agents.domain.idempotency_audit import IdempotencyAuditor, format_idempotency_report

    print(f"\n  {bold('Idempotency Key Auditor')}")
    print(f"  {dim(f'Scanning {cwd} for payment endpoints...')}\n")

    auditor = IdempotencyAuditor(cwd=cwd)
    findings = auditor.audit()

    if severity_filter != "all":
        findings = [f for f in findings if f.severity == severity_filter]

    if output_format == "json":
        data = [
            {
                "file": f.file,
                "line": f.line,
                "endpoint": f.endpoint,
                "issue": f.issue,
                "severity": f.severity,
                "suggestion": f.suggestion,
            }
            for f in findings
        ]
        print(json.dumps(data, indent=2))
    else:
        print(format_idempotency_report(findings))

    crit = sum(1 for f in findings if f.severity == "critical")
    if crit > 0:
        print(f"  {red(f'{crit} critical issue(s) found.')}\n")
    elif findings:
        print(f"  {green('No critical issues.')}\n")
    else:
        print(f"  {green('All clear — no findings.')}\n")
