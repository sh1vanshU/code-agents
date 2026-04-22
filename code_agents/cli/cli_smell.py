"""CLI smell command — detect code smells in the target repo."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_smell")


def cmd_smell():
    """Detect code smells in the codebase.

    Usage:
      code-agents smell                     # scan entire repo
      code-agents smell src/module.py       # scan a specific file or directory
      code-agents smell --json              # output as JSON
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    target = ""
    as_json = False

    for i, a in enumerate(args):
        if a == "--json":
            as_json = True
        elif a in ("--help", "-h"):
            print(cmd_smell.__doc__)
            return
        elif not a.startswith("-"):
            target = a

    from code_agents.reviews.code_smell import CodeSmellDetector, format_smell_report

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Scanning {repo_path} for code smells..."))

    detector = CodeSmellDetector(cwd=repo_path)
    report = detector.scan(target=target)

    if as_json:
        import json
        data = {
            "score": report.score,
            "total_findings": len(report.findings),
            "by_type": report.by_type,
            "by_severity": report.by_severity,
            "findings": [
                {
                    "file": f.file, "line": f.line, "smell_type": f.smell_type,
                    "severity": f.severity, "message": f.message, "metric": f.metric,
                }
                for f in report.findings
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        print(format_smell_report(report))
