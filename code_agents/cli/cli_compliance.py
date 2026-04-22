"""CLI compliance-report command — compliance report generator."""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_compliance")


def cmd_compliance_report():
    """Generate compliance report against PCI, SOC2, or GDPR standards.

    Usage:
      code-agents compliance-report                            # PCI (default), text
      code-agents compliance-report --standard soc2            # SOC2 report
      code-agents compliance-report --standard gdpr            # GDPR report
      code-agents compliance-report --format markdown          # Markdown output
      code-agents compliance-report --format json              # JSON output
      code-agents compliance-report --output report.md         # write to file
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    fmt = "text"
    output_path = None
    standard = "pci"

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--format" and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 1
        elif a == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 1
        elif a == "--standard" and i + 1 < len(args):
            standard = args[i + 1].lower()
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_compliance_report.__doc__)
            return
        i += 1

    if fmt not in ("text", "markdown", "json"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: text, markdown, json"))
        return

    if standard not in ("pci", "soc2", "gdpr"):
        print(red(f"  Unknown standard: {standard}"))
        print(dim("  Supported: pci, soc2, gdpr"))
        return

    # Lazy import
    from code_agents.security.compliance_report import ComplianceReportGenerator

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Generating {standard.upper()} compliance report for {repo_path}..."))

    generator = ComplianceReportGenerator(cwd=repo_path)
    report = generator.generate(standard=standard)

    if fmt == "json":
        output = generator.format_json(report)
    elif fmt == "markdown":
        output = generator.format_markdown(report)
    else:
        output = generator.format_terminal(report)

    if output_path:
        from pathlib import Path
        out = Path(output_path).resolve()
        out.write_text(output, encoding="utf-8")
        print(green(f"  Report written to {out}"))
    else:
        print(output)
