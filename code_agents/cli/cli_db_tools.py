"""CLI commands for database development tools.

Commands:
  code-agents query-optimize <query|file>    Analyze SQL query for optimization
  code-agents schema-design <entity-json>    Design database schema from entities
  code-agents orm-review                     Scan ORM code for anti-patterns
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_db_tools")


def _user_cwd() -> str:
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def cmd_query_optimize(rest: list[str] | None = None):
    """Analyze a SQL query for optimization opportunities.

    Usage:
      code-agents query-optimize "SELECT * FROM users WHERE name LIKE '%john%'"
      code-agents query-optimize query.sql
      code-agents query-optimize --format json < query.sql
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest or rest[0] in ("--help", "-h"):
        print(cmd_query_optimize.__doc__)
        return

    fmt = "text"
    query_text = ""

    # Check for format flag
    filtered = []
    i = 0
    while i < len(rest):
        if rest[i] == "--format" and i + 1 < len(rest):
            fmt = rest[i + 1].lower()
            i += 2
            continue
        filtered.append(rest[i])
        i += 1

    if filtered and filtered[0] == "-":
        query_text = sys.stdin.read()
    elif filtered:
        # Try reading as file first
        try:
            with open(filtered[0], "r") as f:
                query_text = f.read()
        except OSError:
            query_text = " ".join(filtered)
    else:
        print(f"\n  {red('Usage: code-agents query-optimize <query|file>')}")
        return

    print(f"  {cyan('Analyzing SQL query...')}")

    from code_agents.api.query_optimizer import QueryOptimizer, QueryOptimizerConfig, format_query_report

    config = QueryOptimizerConfig(cwd=_user_cwd())
    result = QueryOptimizer(config).analyze(query_text)
    print(format_query_report(result, fmt=fmt))


def cmd_schema_design(rest: list[str] | None = None):
    """Design database schema from entity definitions.

    Usage:
      code-agents schema-design entities.json
      code-agents schema-design '{"User": {"name": "str", "email": "str"}}'
      code-agents schema-design --format sql entities.json
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest or rest[0] in ("--help", "-h"):
        print(cmd_schema_design.__doc__)
        return

    fmt = "text"
    entity_input = ""

    filtered = []
    i = 0
    while i < len(rest):
        if rest[i] == "--format" and i + 1 < len(rest):
            fmt = rest[i + 1].lower()
            i += 2
            continue
        filtered.append(rest[i])
        i += 1

    if filtered:
        # Try reading as file first
        try:
            with open(filtered[0], "r") as f:
                entity_input = f.read()
        except OSError:
            entity_input = " ".join(filtered)
    else:
        print(f"\n  {red('Usage: code-agents schema-design <entity-json|file>')}")
        return

    print(f"  {cyan('Designing database schema...')}")

    from code_agents.api.schema_designer import SchemaDesigner, SchemaDesignerConfig, format_schema

    config = SchemaDesignerConfig(cwd=_user_cwd())
    result = SchemaDesigner(config).design(entity_input)
    print(format_schema(result, fmt=fmt))


def cmd_orm_review(rest: list[str] | None = None):
    """Scan ORM code for anti-patterns.

    Usage:
      code-agents orm-review
      code-agents orm-review --path src/models/
      code-agents orm-review --format json
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if rest and rest[0] in ("--help", "-h"):
        print(cmd_orm_review.__doc__)
        return

    cwd = _user_cwd()
    fmt = "text"
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--path" and i + 1 < len(rest):
            cwd = rest[i + 1]
            i += 1
        elif a == "--format" and i + 1 < len(rest):
            fmt = rest[i + 1].lower()
            i += 1
        i += 1

    print(f"  {cyan('Scanning ORM code for anti-patterns...')}")

    from code_agents.api.orm_reviewer import OrmReviewer, OrmReviewConfig, format_orm_review

    config = OrmReviewConfig(cwd=cwd)
    result = OrmReviewer(config).scan()
    print(format_orm_review(result, fmt=fmt))
