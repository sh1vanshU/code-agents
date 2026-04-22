"""CLI encryption-audit command — encryption/crypto pattern scanner."""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_encryption_audit")


def cmd_encryption_audit():
    """Scan codebase for weak encryption and cryptographic patterns.

    Usage:
      code-agents encryption-audit                    # text report (default)
      code-agents encryption-audit --format json      # JSON output
      code-agents encryption-audit --severity critical # only critical findings
      code-agents encryption-audit --output report.json
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
            print(cmd_encryption_audit.__doc__)
            return
        i += 1

    if fmt not in ("text", "json"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: text, json"))
        return

    from code_agents.security.encryption_audit import (
        EncryptionAuditor,
        format_encryption_report,
        encryption_report_to_json,
    )

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Scanning {repo_path} for encryption issues..."))

    auditor = EncryptionAuditor(cwd=repo_path)
    findings = auditor.audit()

    if severity_filter != "all":
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        threshold = severity_order.get(severity_filter, 3)
        findings = [
            f for f in findings
            if severity_order.get(f.severity, 3) <= threshold
        ]

    if fmt == "json":
        output = json.dumps(encryption_report_to_json(findings), indent=2)
    else:
        output = format_encryption_report(findings)

    if output_path:
        from pathlib import Path
        out = Path(output_path).resolve()
        out.write_text(output, encoding="utf-8")
        print(green(f"  Report written to {out}"))
    else:
        print(output)
