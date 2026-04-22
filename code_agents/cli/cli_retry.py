"""CLI command: code-agents retry-audit — Payment Retry Strategy Analyzer."""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("code_agents.cli.cli_retry")


def cmd_retry_audit(rest: list[str] | None = None):
    """Scan codebase for retry anti-patterns.

    Usage:
      code-agents retry-audit                      # all findings
      code-agents retry-audit --severity critical   # critical only
      code-agents retry-audit --format json         # JSON output
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

    from code_agents.domain.retry_analyzer import RetryAnalyzer, format_retry_report

    print(f"\n  {bold('Payment Retry Strategy Analyzer')}")
    print(f"  {dim(f'Scanning {cwd} for retry patterns...')}\n")

    analyzer = RetryAnalyzer(cwd=cwd)
    findings = analyzer.analyze()

    if severity_filter != "all":
        findings = [f for f in findings if f.severity == severity_filter]

    if output_format == "json":
        data = [
            {
                "file": f.file,
                "line": f.line,
                "issue": f.issue,
                "severity": f.severity,
                "recommendation": f.recommendation,
            }
            for f in findings
        ]
        print(json.dumps(data, indent=2))
    else:
        print(format_retry_report(findings))

    crit = sum(1 for f in findings if f.severity == "critical")
    if crit > 0:
        print(f"  {red(f'{crit} critical issue(s) found.')}\n")
    elif findings:
        print(f"  {green('No critical issues.')}\n")
    else:
        print(f"  {green('All clear — no retry issues found.')}\n")
