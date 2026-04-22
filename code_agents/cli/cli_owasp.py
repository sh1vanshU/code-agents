"""CLI owasp-scan command — OWASP Top 10 security scanner."""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_owasp")


def cmd_owasp_scan():
    """Scan codebase for OWASP Top 10 vulnerabilities.

    Usage:
      code-agents owasp-scan                          # text report (default)
      code-agents owasp-scan --format json             # JSON output
      code-agents owasp-scan --severity critical       # only critical findings
      code-agents owasp-scan --severity high           # critical + high
      code-agents owasp-scan --output report.json      # write to file
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
            print(cmd_owasp_scan.__doc__)
            return
        i += 1

    if fmt not in ("text", "json"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: text, json"))
        return

    # Lazy import
    from code_agents.security.owasp_scanner import OWASPScanner, format_owasp_report, owasp_report_to_json

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Scanning {repo_path} for OWASP Top 10 vulnerabilities..."))

    scanner = OWASPScanner(cwd=repo_path)
    report = scanner.scan()

    # Filter by severity if requested
    if severity_filter != "all":
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        threshold = severity_order.get(severity_filter, 3)
        report.findings = [
            f for f in report.findings
            if severity_order.get(f.severity, 3) <= threshold
        ]

    if fmt == "json":
        output = json.dumps(owasp_report_to_json(report), indent=2)
    else:
        output = format_owasp_report(report)

    if output_path:
        from pathlib import Path
        out = Path(output_path).resolve()
        out.write_text(output, encoding="utf-8")
        print(green(f"  Report written to {out}"))
    else:
        print(output)
