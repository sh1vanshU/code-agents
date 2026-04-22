"""CLI imports command — scan and fix import issues in the target repo."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_imports")


def cmd_imports():
    """Optimize imports — find unused, circular, heavy, wildcard, duplicate, shadowed.

    Usage:
      code-agents imports                     # scan entire repo
      code-agents imports src/module.py       # scan a specific file or directory
      code-agents imports --fix               # auto-fix unused imports
      code-agents imports --json              # output as JSON
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    target = ""
    do_fix = False
    as_json = False

    for a in args:
        if a == "--fix":
            do_fix = True
        elif a == "--json":
            as_json = True
        elif a in ("--help", "-h"):
            print(cmd_imports.__doc__)
            return
        elif not a.startswith("-"):
            target = a

    from code_agents.reviews.import_optimizer import ImportOptimizer, format_import_report

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    optimizer = ImportOptimizer(cwd=repo_path)

    if do_fix:
        print(dim(f"  Auto-fixing imports in {repo_path}..."))
        count = optimizer.fix(target=target)
        if count:
            print(green(f"  Fixed {count} unused import(s)."))
        else:
            print(dim("  No unused imports to fix."))
        return

    print(dim(f"  Scanning imports in {repo_path}..."))
    findings = optimizer.scan(target=target)

    if as_json:
        import json
        data = [
            {
                "file": f.file, "line": f.line,
                "import_statement": f.import_statement,
                "issue": f.issue, "severity": f.severity,
                "suggestion": f.suggestion,
            }
            for f in findings
        ]
        print(json.dumps(data, indent=2))
    else:
        print(format_import_report(findings))
