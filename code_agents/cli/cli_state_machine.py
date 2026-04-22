"""CLI command: code-agents validate-states — Transaction State Machine Validator."""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("code_agents.cli.cli_state_machine")


def cmd_validate_states(rest: list[str] | None = None):
    """Validate transaction state machines in the codebase.

    Usage:
      code-agents validate-states                   # text report
      code-agents validate-states --format json      # JSON output
      code-agents validate-states --format mermaid   # Mermaid diagrams
    """
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    output_format = "text"

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--format" and i + 1 < len(rest):
            output_format = rest[i + 1].lower()
            i += 2
            continue
        i += 1

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    from code_agents.domain.state_machine_validator import (
        StateMachineValidator,
        format_validation_report,
    )

    print(f"\n  {bold('Transaction State Machine Validator')}")
    print(f"  {dim(f'Scanning {cwd}...')}\n")

    validator = StateMachineValidator(cwd=cwd)
    machines = validator.extract()

    if not machines:
        print(f"  {yellow('No state machines found in the codebase.')}\n")
        return

    all_findings = []
    for sm in machines:
        findings = validator.validate(sm)
        all_findings.extend(findings)

    if output_format == "json":
        data = {
            "machines": [
                {
                    "name": sm.name,
                    "states": [s.name for s in sm.states],
                    "initial_state": sm.initial_state,
                    "terminal_states": sm.terminal_states,
                    "transitions": [
                        {"from": t.from_state, "to": t.to_state, "trigger": t.trigger}
                        for t in sm.transitions
                    ],
                }
                for sm in machines
            ],
            "findings": [
                {"severity": f.severity, "message": f.message, "states_involved": f.states_involved}
                for f in all_findings
            ],
        }
        print(json.dumps(data, indent=2))
    elif output_format == "mermaid":
        for sm in machines:
            print(f"  {bold(sm.name)}")
            print()
            print(validator.generate_diagram(sm))
            print()
    else:
        print(format_validation_report(machines, all_findings))

    crit = sum(1 for f in all_findings if f.severity == "critical")
    if crit > 0:
        print(f"  {red(f'{crit} critical issue(s) found.')}\n")
    elif all_findings:
        print(f"  {green('No critical issues.')}\n")
    else:
        print(f"  {green('All state machines valid.')}\n")
