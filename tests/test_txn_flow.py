"""Tests for code_agents.txn_flow — Transaction Flow Visualizer."""

from __future__ import annotations

import os
import textwrap
import tempfile
from pathlib import Path

import pytest

from code_agents.domain.txn_flow import FlowStep, TransactionFlow, TxnFlowTracer


# ---------------------------------------------------------------------------
# TestFlowStep
# ---------------------------------------------------------------------------

class TestFlowStep:
    """FlowStep dataclass construction."""

    def test_basic_construction(self):
        step = FlowStep(service="gateway", action="authorize", status="AUTHORIZED")
        assert step.service == "gateway"
        assert step.action == "authorize"
        assert step.status == "AUTHORIZED"
        assert step.timestamp == ""
        assert step.latency_ms == 0
        assert step.metadata == {}

    def test_full_construction(self):
        step = FlowStep(
            service="acquirer",
            action="capture",
            status="CAPTURED",
            timestamp="2026-04-09T10:00:00Z",
            latency_ms=120.5,
            metadata={"mid": "M123"},
        )
        assert step.latency_ms == 120.5
        assert step.metadata["mid"] == "M123"

    def test_defaults_are_independent(self):
        a = FlowStep(service="a", action="a", status="A")
        b = FlowStep(service="b", action="b", status="B")
        a.metadata["key"] = "val"
        assert "key" not in b.metadata


# ---------------------------------------------------------------------------
# TestTransactionFlow
# ---------------------------------------------------------------------------

class TestTransactionFlow:
    def test_empty_flow(self):
        flow = TransactionFlow(
            order_id="ORD-001",
            steps=[],
            total_latency_ms=0,
            current_state="UNKNOWN",
        )
        assert flow.order_id == "ORD-001"
        assert flow.steps == []
        assert flow.bottleneck == ""
        assert flow.diagram == ""


# ---------------------------------------------------------------------------
# TestTraceFromCode
# ---------------------------------------------------------------------------

class TestTraceFromCode:
    """Create a temp repo with enum OrderStatus and verify extraction."""

    def _make_repo(self, tmp_path: Path, code: str, filename: str = "models.py") -> str:
        src = tmp_path / "src"
        src.mkdir()
        (src / filename).write_text(textwrap.dedent(code), encoding="utf-8")
        return str(tmp_path)

    def test_python_enum_detection(self, tmp_path):
        code = """\
        from enum import Enum

        class OrderStatus(Enum):
            CREATED = "created"
            AUTHORIZED = "authorized"
            CAPTURED = "captured"
            SETTLED = "settled"
            REFUNDED = "refunded"
        """
        repo = self._make_repo(tmp_path, code)
        tracer = TxnFlowTracer(cwd=repo)
        flow = tracer.trace_from_code()

        assert flow.order_id == "(from-code)"
        assert len(flow.steps) >= 1
        # States should include at least some of the enum values
        all_actions = " ".join(s.action for s in flow.steps)
        assert "CREATED" in all_actions or "AUTHORIZED" in all_actions

    def test_java_enum_detection(self, tmp_path):
        code = """\
        public enum TransactionState {
            CREATED,
            AUTHORIZED,
            CAPTURED,
            FAILED;
        }
        """
        repo = self._make_repo(tmp_path, code, filename="TransactionState.java")
        tracer = TxnFlowTracer(cwd=repo)
        flow = tracer.trace_from_code()
        assert len(flow.steps) >= 1

    def test_transition_pattern_detection(self, tmp_path):
        code = """\
        from enum import Enum

        class PaymentState(Enum):
            CREATED = "created"
            AUTHORIZED = "authorized"
            CAPTURED = "captured"

        def process(order):
            # CREATED -> AUTHORIZED
            # AUTHORIZED -> CAPTURED
            pass
        """
        repo = self._make_repo(tmp_path, code)
        tracer = TxnFlowTracer(cwd=repo)
        flow = tracer.trace_from_code()
        assert len(flow.steps) >= 1

    def test_no_states_found(self, tmp_path):
        code = """\
        def hello():
            print("hello world")
        """
        repo = self._make_repo(tmp_path, code)
        tracer = TxnFlowTracer(cwd=repo)
        flow = tracer.trace_from_code()
        assert flow.steps == []
        assert flow.current_state == "NONE"


# ---------------------------------------------------------------------------
# TestSequenceDiagram
# ---------------------------------------------------------------------------

class TestSequenceDiagram:
    """Verify Mermaid sequenceDiagram syntax."""

    def test_basic_sequence(self):
        steps = [
            FlowStep(service="Gateway", action="Create Order", status="CREATED", latency_ms=10),
            FlowStep(service="Acquirer", action="Authorize", status="AUTHORIZED", latency_ms=45),
            FlowStep(service="Bank", action="Capture", status="CAPTURED", latency_ms=120),
        ]
        flow = TransactionFlow(
            order_id="ORD-1", steps=steps, total_latency_ms=175,
            current_state="CAPTURED",
        )
        tracer = TxnFlowTracer(cwd=".")
        diagram = tracer.generate_sequence_diagram(flow)

        assert diagram.startswith("sequenceDiagram")
        assert "participant Gateway" in diagram
        assert "participant Acquirer" in diagram
        assert "participant Bank" in diagram
        assert "->>" in diagram

    def test_failed_step_uses_dashed_arrow(self):
        steps = [
            FlowStep(service="Gateway", action="Create", status="CREATED"),
            FlowStep(service="Bank", action="Decline", status="DECLINED"),
        ]
        flow = TransactionFlow(
            order_id="ORD-2", steps=steps, total_latency_ms=0,
            current_state="DECLINED",
        )
        tracer = TxnFlowTracer(cwd=".")
        diagram = tracer.generate_sequence_diagram(flow)
        assert "-->>" in diagram

    def test_empty_flow_still_valid(self):
        flow = TransactionFlow(
            order_id="ORD-3", steps=[], total_latency_ms=0,
            current_state="UNKNOWN",
        )
        tracer = TxnFlowTracer(cwd=".")
        diagram = tracer.generate_sequence_diagram(flow)
        assert diagram.startswith("sequenceDiagram")


# ---------------------------------------------------------------------------
# TestStateDiagram
# ---------------------------------------------------------------------------

class TestStateDiagram:
    """Verify Mermaid stateDiagram-v2 syntax."""

    def test_basic_state_diagram(self):
        steps = [
            FlowStep(service="payment", action="CREATED -> AUTHORIZED", status="AUTHORIZED",
                     metadata={"trigger": "authorize"}),
            FlowStep(service="payment", action="AUTHORIZED -> CAPTURED", status="CAPTURED",
                     metadata={"trigger": "capture"}),
        ]
        flow = TransactionFlow(
            order_id="(from-code)", steps=steps, total_latency_ms=0,
            current_state="CAPTURED",
        )
        tracer = TxnFlowTracer(cwd=".")
        diagram = tracer.generate_state_diagram(flow)

        assert diagram.startswith("stateDiagram-v2")
        assert "[*] --> CREATED" in diagram
        assert "CREATED --> AUTHORIZED" in diagram
        assert "AUTHORIZED --> CAPTURED" in diagram
        assert "CAPTURED --> [*]" in diagram

    def test_empty_flow_state_diagram(self):
        flow = TransactionFlow(
            order_id="X", steps=[], total_latency_ms=0, current_state="NONE",
        )
        tracer = TxnFlowTracer(cwd=".")
        diagram = tracer.generate_state_diagram(flow)
        assert "stateDiagram-v2" in diagram
        assert "[*] --> EMPTY" in diagram


# ---------------------------------------------------------------------------
# TestTerminalFormat
# ---------------------------------------------------------------------------

class TestTerminalFormat:
    """Verify colored terminal output with latency bars."""

    def test_terminal_with_latency(self):
        steps = [
            FlowStep(service="gw", action="CREATED -> AUTHORIZED", status="AUTHORIZED", latency_ms=45),
            FlowStep(service="acq", action="AUTHORIZED -> CAPTURED", status="CAPTURED", latency_ms=120),
        ]
        flow = TransactionFlow(
            order_id="ORD-T", steps=steps, total_latency_ms=165,
            current_state="CAPTURED", bottleneck="AUTHORIZED -> CAPTURED (120ms)",
        )
        tracer = TxnFlowTracer(cwd=".")
        output = tracer.generate_terminal(flow)

        assert "45ms" in output
        assert "120ms" in output
        assert "\u2588" in output  # filled bar character
        assert "Total latency: 165ms" in output
        assert "Bottleneck" in output

    def test_terminal_pending_step(self):
        steps = [
            FlowStep(service="gw", action="CAPTURED -> SETTLING", status="SETTLING", latency_ms=0),
        ]
        flow = TransactionFlow(
            order_id="ORD-P", steps=steps, total_latency_ms=0,
            current_state="SETTLING",
        )
        tracer = TxnFlowTracer(cwd=".")
        output = tracer.generate_terminal(flow)
        assert "(pending)" in output

    def test_terminal_failed_step(self):
        steps = [
            FlowStep(service="bank", action="authorize", status="FAILED", latency_ms=50),
        ]
        flow = TransactionFlow(
            order_id="ORD-F", steps=steps, total_latency_ms=50,
            current_state="FAILED",
        )
        tracer = TxnFlowTracer(cwd=".")
        output = tracer.generate_terminal(flow)
        assert "50ms" in output

    def test_terminal_empty(self):
        flow = TransactionFlow(
            order_id="E", steps=[], total_latency_ms=0, current_state="NONE",
        )
        tracer = TxnFlowTracer(cwd=".")
        output = tracer.generate_terminal(flow)
        assert "No steps found" in output


# ---------------------------------------------------------------------------
# TestBottleneck
# ---------------------------------------------------------------------------

class TestBottleneck:
    """Identify the slowest step."""

    def test_identifies_slowest(self):
        steps = [
            FlowStep(service="a", action="step1", status="OK", latency_ms=10),
            FlowStep(service="b", action="step2", status="OK", latency_ms=200),
            FlowStep(service="c", action="step3", status="OK", latency_ms=50),
        ]
        tracer = TxnFlowTracer(cwd=".")
        bottleneck = tracer._identify_bottleneck(steps)
        assert "step2" in bottleneck
        assert "200ms" in bottleneck

    def test_no_bottleneck_when_zero_latency(self):
        steps = [
            FlowStep(service="a", action="step1", status="OK", latency_ms=0),
        ]
        tracer = TxnFlowTracer(cwd=".")
        bottleneck = tracer._identify_bottleneck(steps)
        assert bottleneck == ""

    def test_no_bottleneck_when_empty(self):
        tracer = TxnFlowTracer(cwd=".")
        assert tracer._identify_bottleneck([]) == ""


# ---------------------------------------------------------------------------
# TestEmptyRepo
# ---------------------------------------------------------------------------

class TestEmptyRepo:
    """Handle gracefully when repo has no relevant code."""

    def test_empty_directory(self, tmp_path):
        tracer = TxnFlowTracer(cwd=str(tmp_path))
        flow = tracer.trace_from_code()
        assert flow.steps == []
        assert flow.current_state == "NONE"

    def test_no_es_returns_empty(self, tmp_path):
        tracer = TxnFlowTracer(cwd=str(tmp_path))
        flow = tracer.trace_from_logs("ORD-MISSING", env="dev")
        assert flow.steps == []
        assert flow.current_state == "UNKNOWN"

    def test_only_non_source_files(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "data.csv").write_text("a,b,c")
        tracer = TxnFlowTracer(cwd=str(tmp_path))
        flow = tracer.trace_from_code()
        assert flow.steps == []
