"""CLI command: code-agents impact — Interactive Dependency Impact Scanner."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_dep_impact")


def cmd_dep_impact(rest: list[str] | None = None):
    """Scan dependency upgrade impact before upgrading.

    Usage:
      code-agents impact --upgrade requests==3.0.0      # scan impact
      code-agents impact --upgrade requests==3.0.0 --check  # exit 1 if high risk
      code-agents impact --upgrade requests==3.0.0 --apply  # apply patches
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    package = ""
    target_version = ""
    check_mode = "--check" in rest
    apply_mode = "--apply" in rest

    # Parse --upgrade pkg==ver
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--upgrade" and i + 1 < len(rest):
            spec = rest[i + 1]
            if "==" in spec:
                package, target_version = spec.split("==", 1)
            else:
                package = spec
                target_version = "latest"
            i += 2
            continue
        i += 1

    if not package:
        print(f"\n  {bold('Dependency Impact Scanner')}")
        print(f"  {dim('Scan upgrade impact before you upgrade.')}\n")
        print(f"  {cyan('Usage:')}")
        print(f"    code-agents impact --upgrade <pkg>==<version>")
        print(f"    code-agents impact --upgrade <pkg>==<version> --check")
        print(f"    code-agents impact --upgrade <pkg>==<version> --apply\n")
        return

    import os
    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    from code_agents.domain.dep_impact import DependencyImpactScanner, format_impact_report

    print(f"\n  {bold('Dependency Impact Scanner')}")
    print(f"  {dim(f'Package: {package} -> {target_version}')}\n")

    scanner = DependencyImpactScanner(
        cwd=cwd,
        package=package,
        target_version=target_version,
        dry_run=not apply_mode,
    )
    report = scanner.scan()
    print(format_impact_report(report))

    if apply_mode and report.patches:
        patched = scanner.apply_patches()
        print(f"  {green(f'Applied {patched} patch(es).')}\n")
    elif apply_mode:
        print(f"  {dim('No patches to apply.')}\n")

    if check_mode:
        if report.risk_level in ("high", "critical"):
            print(f"  {red(f'Risk level is {report.risk_level.upper()} — failing check.')}\n")
            sys.exit(1)
        else:
            print(f"  {green(f'Risk level is {report.risk_level.upper()} — check passed.')}\n")
