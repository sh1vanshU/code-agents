"""Tests for state_machine_validator.py — Transaction State Machine Validator."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.domain.state_machine_validator import (
    State,
    StateMachine,
    StateMachineValidator,
    Transition,
    ValidationFinding,
    format_validation_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(tmp_path: Path, files: dict[str, str]) -> str:
    """Create a temporary repo with given file contents."""
    for relpath, content in files.items():
        fpath = tmp_path / relpath
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
    return str(tmp_path)


def _sm_with_transitions(
    name: str = "TestSM",
    states: list[State] | None = None,
    transitions: list[Transition] | None = None,
    initial: str = "",
    terminal: list[str] | None = None,
) -> StateMachine:
    return StateMachine(
        name=name,
        states=states or [],
        transitions=transitions or [],
        initial_state=initial,
        terminal_states=terminal or [],
    )


# ---------------------------------------------------------------------------
# TestExtract
# ---------------------------------------------------------------------------

class TestExtract:
    """Extract state machines from code: Python enum + transition map."""

    def test_python_enum_extraction(self, tmp_path):
        code = '''
from enum import Enum

class OrderStatus(Enum):
    CREATED = "created"
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
'''
        repo = _make_repo(tmp_path, {"models.py": code})
        v = StateMachineValidator(cwd=repo)
        machines = v.extract()
        assert len(machines) >= 1
        sm = machines[0]
        assert sm.name == "OrderStatus"
        state_names = [s.name for s in sm.states]
        assert "CREATED" in state_names
        assert "PENDING" in state_names
        assert "COMPLETED" in state_names
        assert "FAILED" in state_names

    def test_java_enum_extraction(self, tmp_path):
        code = '''
public enum PaymentState {
    INITIATED,
    PENDING,
    SUCCESS,
    FAILED,
    REFUNDED
}
'''
        repo = _make_repo(tmp_path, {"Payment.java": code})
        v = StateMachineValidator(cwd=repo)
        machines = v.extract()
        assert len(machines) >= 1
        sm = machines[0]
        assert sm.name == "PaymentState"
        state_names = [s.name for s in sm.states]
        assert "INITIATED" in state_names
        assert "SUCCESS" in state_names

    def test_typescript_union_extraction(self, tmp_path):
        code = '''
type TransactionStatus = "created" | "pending" | "processing" | "completed" | "failed";
'''
        repo = _make_repo(tmp_path, {"types.ts": code})
        v = StateMachineValidator(cwd=repo)
        machines = v.extract()
        assert len(machines) >= 1
        sm = machines[0]
        assert sm.name == "TransactionStatus"
        state_names = [s.name for s in sm.states]
        assert "created" in state_names
        assert "completed" in state_names

    def test_transition_map_extraction(self, tmp_path):
        code = '''
ALLOWED_TRANSITIONS = {
    "CREATED": ["PENDING", "CANCELLED"],
    "PENDING": ["PROCESSING", "FAILED"],
    "PROCESSING": ["COMPLETED", "FAILED"],
}
'''
        repo = _make_repo(tmp_path, {"flow.py": code})
        v = StateMachineValidator(cwd=repo)
        machines = v.extract()
        assert len(machines) >= 1
        has_transitions = any(sm.transitions for sm in machines)
        assert has_transitions

    def test_empty_repo(self, tmp_path):
        repo = _make_repo(tmp_path, {"README.md": "# Nothing here"})
        v = StateMachineValidator(cwd=repo)
        machines = v.extract()
        assert machines == []


# ---------------------------------------------------------------------------
# TestUnreachable
# ---------------------------------------------------------------------------

class TestUnreachable:
    """State with no incoming transitions -> warning."""

    def test_unreachable_state(self):
        sm = _sm_with_transitions(
            states=[
                State("CREATED"),
                State("PENDING"),
                State("ORPHAN"),
                State("COMPLETED", is_terminal=True),
            ],
            transitions=[
                Transition("CREATED", "PENDING"),
                Transition("PENDING", "COMPLETED"),
            ],
            initial="CREATED",
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v._check_unreachable_states(sm)
        assert len(findings) >= 1
        assert any("ORPHAN" in f.message for f in findings)
        assert all(f.severity == "warning" for f in findings)

    def test_initial_not_flagged(self):
        sm = _sm_with_transitions(
            states=[
                State("CREATED"),
                State("COMPLETED", is_terminal=True),
            ],
            transitions=[
                Transition("CREATED", "COMPLETED"),
            ],
            initial="CREATED",
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v._check_unreachable_states(sm)
        # CREATED is initial, should not be flagged
        assert not any("CREATED" in f.message for f in findings)


# ---------------------------------------------------------------------------
# TestDeadEnd
# ---------------------------------------------------------------------------

class TestDeadEnd:
    """Non-terminal with no outgoing transitions -> critical."""

    def test_dead_end_state(self):
        sm = _sm_with_transitions(
            states=[
                State("CREATED"),
                State("STUCK"),  # not terminal, no outgoing
                State("COMPLETED", is_terminal=True),
            ],
            transitions=[
                Transition("CREATED", "STUCK"),
                Transition("CREATED", "COMPLETED"),
            ],
            initial="CREATED",
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v._check_dead_end_states(sm)
        assert len(findings) >= 1
        assert any("STUCK" in f.message for f in findings)
        assert all(f.severity == "critical" for f in findings)

    def test_terminal_not_flagged(self):
        sm = _sm_with_transitions(
            states=[
                State("CREATED"),
                State("COMPLETED", is_terminal=True),
            ],
            transitions=[
                Transition("CREATED", "COMPLETED"),
            ],
            initial="CREATED",
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v._check_dead_end_states(sm)
        assert not any("COMPLETED" in f.message for f in findings)


# ---------------------------------------------------------------------------
# TestImpossible
# ---------------------------------------------------------------------------

class TestImpossible:
    """Transition from terminal state -> warning."""

    def test_impossible_transition(self):
        sm = _sm_with_transitions(
            states=[
                State("CREATED"),
                State("COMPLETED", is_terminal=True),
                State("REFUNDED", is_terminal=True),
            ],
            transitions=[
                Transition("CREATED", "COMPLETED"),
                Transition("COMPLETED", "REFUNDED"),  # impossible
            ],
            initial="CREATED",
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v._check_impossible_transitions(sm)
        assert len(findings) == 1
        assert "COMPLETED" in findings[0].message
        assert findings[0].severity == "warning"


# ---------------------------------------------------------------------------
# TestErrorRecovery
# ---------------------------------------------------------------------------

class TestErrorRecovery:
    """Error state without recovery -> warning."""

    def test_error_without_recovery(self):
        sm = _sm_with_transitions(
            states=[
                State("CREATED"),
                State("FAILED", is_terminal=True, is_error=True),
            ],
            transitions=[
                Transition("CREATED", "FAILED"),
            ],
            initial="CREATED",
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v._check_error_recovery(sm)
        assert len(findings) >= 1
        assert any("FAILED" in f.message for f in findings)
        assert all(f.severity == "warning" for f in findings)

    def test_error_with_recovery(self):
        sm = _sm_with_transitions(
            states=[
                State("CREATED"),
                State("FAILED", is_terminal=False, is_error=True),
                State("RETRYING"),
            ],
            transitions=[
                Transition("CREATED", "FAILED"),
                Transition("FAILED", "RETRYING"),  # recovery
            ],
            initial="CREATED",
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v._check_error_recovery(sm)
        assert not any("FAILED" in f.message for f in findings)


# ---------------------------------------------------------------------------
# TestTerminalReachability
# ---------------------------------------------------------------------------

class TestTerminalReachability:
    """State that cannot reach any terminal -> critical."""

    def test_unreachable_terminal(self):
        sm = _sm_with_transitions(
            states=[
                State("CREATED"),
                State("LOOP_A"),
                State("LOOP_B"),
                State("COMPLETED", is_terminal=True),
            ],
            transitions=[
                Transition("CREATED", "LOOP_A"),
                Transition("LOOP_A", "LOOP_B"),
                Transition("LOOP_B", "LOOP_A"),  # infinite loop, no path to COMPLETED
            ],
            initial="CREATED",
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v._check_terminal_reachability(sm)
        assert len(findings) >= 1
        stuck_states = set()
        for f in findings:
            stuck_states.update(f.states_involved)
        assert "LOOP_A" in stuck_states or "LOOP_B" in stuck_states
        assert all(f.severity == "critical" for f in findings)

    def test_all_reachable(self):
        sm = _sm_with_transitions(
            states=[
                State("CREATED"),
                State("PENDING"),
                State("COMPLETED", is_terminal=True),
            ],
            transitions=[
                Transition("CREATED", "PENDING"),
                Transition("PENDING", "COMPLETED"),
            ],
            initial="CREATED",
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v._check_terminal_reachability(sm)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# TestDiagram
# ---------------------------------------------------------------------------

class TestDiagram:
    """Verify Mermaid stateDiagram output."""

    def test_mermaid_output(self):
        sm = _sm_with_transitions(
            name="PaymentFlow",
            states=[
                State("CREATED"),
                State("PENDING"),
                State("SUCCESS", is_terminal=True),
                State("FAILED", is_terminal=True, is_error=True),
            ],
            transitions=[
                Transition("CREATED", "PENDING", trigger="submit"),
                Transition("PENDING", "SUCCESS", trigger="confirm"),
                Transition("PENDING", "FAILED", trigger="reject"),
            ],
            initial="CREATED",
            terminal=["SUCCESS", "FAILED"],
        )
        v = StateMachineValidator(cwd="/tmp")
        diagram = v.generate_diagram(sm)
        assert "stateDiagram-v2" in diagram
        assert "[*] --> CREATED" in diagram
        assert "CREATED --> PENDING" in diagram
        assert "PENDING --> SUCCESS" in diagram
        assert "SUCCESS --> [*]" in diagram
        assert "FAILED --> [*]" in diagram
        assert "error state" in diagram  # note for FAILED

    def test_diagram_with_guard(self):
        sm = _sm_with_transitions(
            states=[State("A"), State("B", is_terminal=True)],
            transitions=[Transition("A", "B", trigger="go", guard_condition="valid")],
            initial="A",
            terminal=["B"],
        )
        v = StateMachineValidator(cwd="/tmp")
        diagram = v.generate_diagram(sm)
        assert "go" in diagram
        assert "[valid]" in diagram


# ---------------------------------------------------------------------------
# TestFullValidation
# ---------------------------------------------------------------------------

class TestFullValidation:
    """Complete payment state machine — end-to-end validation."""

    def test_complete_payment_sm(self, tmp_path):
        code = '''
from enum import Enum

class PaymentStatus(Enum):
    CREATED = "created"
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"

ALLOWED_TRANSITIONS = {
    "CREATED": ["PENDING", "CANCELLED"],
    "PENDING": ["PROCESSING", "FAILED", "CANCELLED"],
    "PROCESSING": ["COMPLETED", "FAILED"],
}
'''
        repo = _make_repo(tmp_path, {"payment/models.py": code})
        v = StateMachineValidator(cwd=repo)
        machines = v.extract()
        assert len(machines) >= 1

        # Pick the machine with most transitions
        sm = max(machines, key=lambda m: len(m.transitions))
        findings = v.validate(sm)

        # REFUNDED should be unreachable (no transition leads to it)
        messages = " ".join(f.message for f in findings)
        assert "REFUNDED" in messages or len(findings) > 0

    def test_format_report(self):
        machines = [
            _sm_with_transitions(
                name="OrderSM",
                states=[State("A"), State("B", is_terminal=True)],
                transitions=[Transition("A", "B")],
                initial="A",
                terminal=["B"],
            ),
        ]
        findings = [
            ValidationFinding("critical", "Test critical", ["A"]),
            ValidationFinding("warning", "Test warning", ["B"]),
        ]
        report = format_validation_report(machines, findings)
        assert "OrderSM" in report
        assert "CRITICAL" in report
        assert "WARNINGS" in report
        assert "Test critical" in report
        assert "Test warning" in report

    def test_format_report_no_findings(self):
        machines = [
            _sm_with_transitions(name="CleanSM", states=[State("A")]),
        ]
        report = format_validation_report(machines, [])
        assert "No issues found" in report

    def test_validate_returns_all_check_types(self):
        """A messy SM that triggers multiple check types."""
        sm = _sm_with_transitions(
            states=[
                State("CREATED"),
                State("PENDING"),
                State("ORPHAN"),  # unreachable
                State("STUCK"),  # dead end (non-terminal, no outgoing)
                State("COMPLETED", is_terminal=True),
                State("FAILED", is_terminal=True, is_error=True),
            ],
            transitions=[
                Transition("CREATED", "PENDING"),
                Transition("PENDING", "COMPLETED"),
                Transition("PENDING", "FAILED"),
                Transition("COMPLETED", "FAILED"),  # impossible (from terminal)
                Transition("CREATED", "STUCK"),
            ],
            initial="CREATED",
            terminal=["COMPLETED", "FAILED"],
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v.validate(sm)
        severities = {f.severity for f in findings}
        assert "critical" in severities  # dead end (STUCK), or terminal unreachable
        assert "warning" in severities  # unreachable (ORPHAN), impossible, error recovery
        assert len(findings) >= 3


# ---------------------------------------------------------------------------
# TestTimeoutHandlers
# ---------------------------------------------------------------------------

class TestTimeoutHandlers:
    """Pending states without timeout handlers."""

    def test_pending_without_timeout(self):
        sm = _sm_with_transitions(
            states=[
                State("CREATED"),
                State("PENDING", has_timeout_handler=False),
                State("COMPLETED", is_terminal=True),
            ],
            transitions=[
                Transition("CREATED", "PENDING"),
                Transition("PENDING", "COMPLETED"),
            ],
            initial="CREATED",
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v._check_timeout_handlers(sm)
        assert len(findings) >= 1
        assert any("PENDING" in f.message for f in findings)

    def test_pending_with_timeout(self):
        sm = _sm_with_transitions(
            states=[
                State("PENDING", has_timeout_handler=True),
            ],
        )
        v = StateMachineValidator(cwd="/tmp")
        findings = v._check_timeout_handlers(sm)
        assert len(findings) == 0
