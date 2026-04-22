#!/usr/bin/env python3
"""CLI: validate (or --fix) extension package.json `repository` fields for vsce packaging."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ensure extensions/*/package.json define repository for @vscode/vsce.",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Write repository from `git remote get-url origin` (fallback: default upstream URL).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --fix, show what would be written without saving.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    from code_agents.tools.extension_repositories import (
        apply_default_repositories,
        format_validation_failure,
        validate_extension_repositories,
    )

    if args.fix:
        ok, msgs = apply_default_repositories(repo_root, dry_run=args.dry_run)
        for m in msgs:
            print(m)
        if not ok:
            _, errs = validate_extension_repositories(repo_root)
            print(format_validation_failure(repo_root, errs), file=sys.stderr)
            return 1
        return 0

    ok, errs = validate_extension_repositories(repo_root)
    if ok:
        print("OK: extension package.json repository fields are valid.")
        return 0
    print(format_validation_failure(repo_root, errs), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
