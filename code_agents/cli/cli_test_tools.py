"""CLI commands for testing tools.

Commands:
  code-agents edge-cases <file:function>    Suggest edge cases for a function
  code-agents mock-build <file:Class>       Generate mock for a class
  code-agents test-fix <error-output-file>  Diagnose and fix failing tests
  code-agents integration-scaffold <svc>... Generate docker-compose + test setup
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_test_tools")


def _user_cwd() -> str:
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def cmd_edge_cases(rest: list[str] | None = None):
    """Suggest untested edge cases for a function.

    Usage: code-agents edge-cases <file.py:function_name>
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest:
        print(f"\n  {red('Usage: code-agents edge-cases <file.py:function_name>')}")
        return

    from code_agents.testing.edge_case_suggester import EdgeCaseSuggester, EdgeCaseConfig, format_edge_cases
    config = EdgeCaseConfig(cwd=_user_cwd())
    result = EdgeCaseSuggester(config).suggest(rest[0])
    print(format_edge_cases(result))


def cmd_mock_build(rest: list[str] | None = None):
    """Generate mock implementation for a class.

    Usage: code-agents mock-build <file.py:ClassName>
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest:
        print(f"\n  {red('Usage: code-agents mock-build <file.py:ClassName>')}")
        return

    from code_agents.testing.mock_builder import MockBuilder, MockBuilderConfig, format_mock
    config = MockBuilderConfig(cwd=_user_cwd())
    result = MockBuilder(config).build(rest[0])
    print(format_mock(result))


def cmd_test_fix(rest: list[str] | None = None):
    """Diagnose failing tests and suggest fixes.

    Usage: code-agents test-fix <error-output-file>
           poetry run pytest ... 2>&1 | code-agents test-fix -
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    error_output = ""
    if rest and rest[0] == "-":
        error_output = sys.stdin.read()
    elif rest:
        try:
            with open(rest[0], "r") as f:
                error_output = f.read()
        except OSError:
            error_output = " ".join(rest)
    else:
        print(f"\n  {red('Usage: code-agents test-fix <file|->  pipe pytest output')}")
        return

    from code_agents.testing.test_fixer import TestFixer, TestFixerConfig, format_test_fix
    config = TestFixerConfig(cwd=_user_cwd())
    result = TestFixer(config).diagnose(error_output)
    print(format_test_fix(result))


def cmd_integration_scaffold(rest: list[str] | None = None):
    """Generate docker-compose + test fixtures for integration testing.

    Usage: code-agents integration-scaffold postgres redis kafka
    """
    from .cli_helpers import _colors, _load_env
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    rest = rest or []

    if not rest:
        print(f"\n  {red('Usage: code-agents integration-scaffold <service> [service...]')}")
        print(f"  {dim('Available: postgres, redis, kafka, elasticsearch, mongodb, rabbitmq, mysql, minio')}")
        return

    from code_agents.knowledge.integration_scaffold import IntegrationScaffolder, format_scaffold
    result = IntegrationScaffolder().generate(rest)
    print(format_scaffold(result))
