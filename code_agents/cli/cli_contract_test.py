"""CLI handler for API Contract Testing.

Usage:
  code-agents contract-test
  code-agents contract-test --format pact|schema|both
  code-agents contract-test --output tests/contracts/
  code-agents contract-test --target code_agents/routers/ --format both
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("code_agents.cli.cli_contract_test")


def _user_cwd() -> str:
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def cmd_contract_test(rest: list[str] | None = None):
    """Generate API contract tests from route definitions."""
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    fmt = "pact"
    target = ""
    output_dir = ""
    json_mode = False

    # Parse args
    i = 0
    while i < len(rest):
        if rest[i] in ("--format", "-f") and i + 1 < len(rest):
            fmt = rest[i + 1]
            i += 2
            continue
        elif rest[i] in ("--output", "-o") and i + 1 < len(rest):
            output_dir = rest[i + 1]
            i += 2
            continue
        elif rest[i] in ("--target", "-t") and i + 1 < len(rest):
            target = rest[i + 1]
            i += 2
            continue
        elif rest[i] == "--json":
            json_mode = True
        i += 1

    if fmt not in ("pact", "schema", "both"):
        print(f"  {red(f'Invalid format: {fmt}. Use pact, schema, or both.')}")
        return

    cwd = _user_cwd()

    from code_agents.testing.contract_testing import ContractTestGenerator, format_tests_summary

    generator = ContractTestGenerator(cwd=cwd)

    if not json_mode:
        print(f"\n  {bold('API Contract Test Generator')}")
        parts = [f"Format: {fmt}"]
        if target:
            parts.append(f"Target: {target}")
        print(f"  {dim(' | '.join(parts))}\n")
        print(f"  {dim('Scanning for API routes...')}")

    tests = generator.generate(target=target, fmt=fmt)

    if json_mode:
        import json
        print(json.dumps([t.to_dict() for t in tests], indent=2))
        return

    if not tests:
        print(f"\n  {yellow('No API routes found.')} Make sure your project has FastAPI or Flask route decorators.")
        return

    print(format_tests_summary(tests))

    # Write to output dir if requested
    if output_dir:
        out_path = os.path.join(cwd, output_dir) if not os.path.isabs(output_dir) else output_dir
        os.makedirs(out_path, exist_ok=True)

        written = 0
        for test in tests:
            fpath = os.path.join(out_path, test.file_name)
            Path(fpath).write_text(test.test_code, encoding="utf-8")
            written += 1

        print(f"  {green(f'Wrote {written} test files to {output_dir}')}")
    else:
        print(f"  {dim('Use --output <dir> to write test files to disk.')}")
    print()
