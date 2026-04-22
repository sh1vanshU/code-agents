"""CLI lang-migrate command — migrate modules between programming languages."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_lang_migrate")


def cmd_lang_migrate(args: list[str] | None = None):
    """Migrate a source module to another programming language.

    Usage:
      code-agents lang-migrate --source src/ --to go
      code-agents lang-migrate --source src/ --to go --output /tmp/migrated

    Examples:
      code-agents lang-migrate --source lib/ --to typescript
      code-agents lang-migrate --source app/ --to java --output /tmp/java-app
    """
    from .cli_helpers import _colors

    bold, green, yellow, red, cyan, dim = _colors()

    args = args if args is not None else sys.argv[2:]

    if not args or "--help" in args or "-h" in args:
        print(cmd_lang_migrate.__doc__)
        return

    source_dir = ""
    target_lang = ""
    output_dir = ""

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--source" and i + 1 < len(args):
            source_dir = args[i + 1]
            i += 1
        elif a == "--to" and i + 1 < len(args):
            target_lang = args[i + 1]
            i += 1
        elif a == "--output" and i + 1 < len(args):
            output_dir = args[i + 1]
            i += 1
        i += 1

    if not source_dir:
        print(red("  Missing --source <dir>. Specify a source directory."))
        return

    if not target_lang:
        print(red("  Missing --to <lang>. Specify a target language."))
        print(dim("  Supported: python, javascript, typescript, java, go"))
        return

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    from code_agents.knowledge.lang_migration import LanguageMigrator, format_migration_result

    print(dim(f"  Source: {source_dir}"))
    print(dim(f"  Target language: {target_lang}"))
    if output_dir:
        print(dim(f"  Output: {output_dir}"))
    print()

    migrator = LanguageMigrator(cwd=cwd)
    result = migrator.migrate_module(
        source_dir=source_dir,
        target_lang=target_lang,
        output_dir=output_dir or None,
    )

    print(format_migration_result(result))

    if result.errors:
        print()
        print(red(f"  {len(result.errors)} error(s) occurred during migration."))
    elif result.translated_files:
        print()
        print(green(f"  Migration complete: {result.total_files} files generated."))
