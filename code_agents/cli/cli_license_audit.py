"""CLI subcommand: code-agents license-audit [--sbom] [--format text|json]."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_license_audit")


def cmd_license_audit(rest: list[str] | None = None):
    """Audit dependency licenses for compliance issues.

    Usage:
      code-agents license-audit                # text report
      code-agents license-audit --json         # JSON output
      code-agents license-audit --sbom         # generate SBOM
      code-agents license-audit --format json  # alias for --json
    """
    rest = rest or sys.argv[2:]
    as_json = False
    sbom = False

    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg == "--json":
            as_json = True
        elif arg == "--sbom":
            sbom = True
        elif arg == "--format" and i + 1 < len(rest):
            if rest[i + 1] == "json":
                as_json = True
            i += 2
            continue
        elif arg in ("--help", "-h"):
            print(cmd_license_audit.__doc__)
            return
        i += 1

    from code_agents.security.license_audit import LicenseAuditor, format_license_report

    cwd = os.environ.get("TARGET_REPO_PATH") or os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    auditor = LicenseAuditor(cwd=cwd)

    if sbom:
        print(auditor.generate_sbom())
        return

    deps = auditor.audit()

    if as_json:
        import json
        data = [
            {"package": d.package, "version": d.version, "license": d.license, "risk": d.risk}
            for d in deps
        ]
        print(json.dumps(data, indent=2))
    else:
        print(format_license_report(deps))
