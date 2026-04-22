"""CLI command: migrate-tracing — OpenTelemetry migration tool."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_migrate_tracing")


def cmd_migrate_tracing():
    """Scan for legacy tracing patterns and migrate to OpenTelemetry.

    Usage:
      code-agents migrate-tracing                 # scan + show plan
      code-agents migrate-tracing --scan           # scan only
      code-agents migrate-tracing --apply          # scan + apply
      code-agents migrate-tracing --dry-run        # scan + dry-run apply
      code-agents migrate-tracing --rollback       # restore from backup
      code-agents migrate-tracing --language py    # force language
      code-agents migrate-tracing --exporter otlp  # exporter hint
    """
    from code_agents.observability.tracing_migration import (
        TracingMigrator,
        format_migration_plan,
        format_migration_result,
    )

    args = sys.argv[2:] if len(sys.argv) > 2 else []

    repo_path = os.getenv("TARGET_REPO_PATH", os.getcwd())
    scan_only = "--scan" in args
    do_apply = "--apply" in args
    dry_run = "--dry-run" in args
    do_rollback = "--rollback" in args

    try:
        migrator = TracingMigrator(repo_path)
    except FileNotFoundError as e:
        print(f"  Error: {e}")
        sys.exit(1)

    # Rollback mode
    if do_rollback:
        print("  Rolling back migration...")
        ok = migrator.rollback()
        if ok:
            print("  Rollback complete — files restored from backup.")
        else:
            print("  No backup found. Nothing to rollback.")
        return

    # Scan
    print(f"  Scanning {repo_path} for tracing patterns...")
    plan = migrator.scan()
    print(format_migration_plan(plan))

    if not plan.patterns_found:
        print("  No legacy tracing patterns found.")
        return

    if scan_only:
        return

    # Dry run
    if dry_run:
        print("  Dry-run mode — no files will be changed.")
        result = migrator.apply(plan, dry_run=True)
        print(format_migration_result(result))
        return

    # Apply (with confirmation unless --apply flag)
    if not do_apply:
        try:
            answer = input("  Apply migration? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return
        if answer not in ("y", "yes"):
            print("  Cancelled.")
            return

    result = migrator.apply(plan)
    print(format_migration_result(result))
