"""Transaction Flow Visualizer — trace payment journeys from logs or code.

Two modes:
  - from-logs: query Elasticsearch by order_id to reconstruct the flow
  - from-code: scan the repo for state machine patterns (enums, transitions)

Works standalone (from-code) without any external services.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("code_agents.domain.txn_flow")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FlowStep:
    """A single step in a transaction flow."""

    service: str
    action: str
    status: str
    timestamp: str = ""
    latency_ms: float = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class TransactionFlow:
    """Complete transaction journey."""

    order_id: str
    steps: list[FlowStep]
    total_latency_ms: float
    current_state: str
    bottleneck: str = ""
    diagram: str = ""


# ---------------------------------------------------------------------------
# Patterns for code scanning
# ---------------------------------------------------------------------------

# Common payment-related state names
_PAYMENT_STATE_PATTERNS = re.compile(
    r"\b(CREATED|INITIATED|PENDING|AUTHORIZED|CAPTURED|SETTLED|REFUNDED|"
    r"CANCELLED|FAILED|DECLINED|EXPIRED|PROCESSING|COMPLETED|"
    r"VOIDED|REVERSED|CHARGED_BACK|PARTIAL_REFUND|"
    r"CHECKOUT|SUBMITTED|APPROVED|REJECTED|DISPUTED|"
    r"INIT|SUCCESS|FAILURE|TIMEOUT|IN_PROGRESS)\b"
)

# Patterns for enum/class definitions that look like state machines
_ENUM_CLASS_PATTERNS = [
    # Python: class OrderStatus(Enum):
    re.compile(
        r"class\s+(\w*(?:Status|State|Phase|Stage)\w*)\s*\(\s*(?:str\s*,\s*)?(?:Enum|IntEnum|StrEnum)\s*\)\s*:",
        re.IGNORECASE,
    ),
    # Python: class OrderStatus(enum.Enum):
    re.compile(
        r"class\s+(\w*(?:Status|State|Phase|Stage)\w*)\s*\(\s*enum\.(?:Enum|IntEnum|StrEnum)\s*\)\s*:",
        re.IGNORECASE,
    ),
    # Java/Kotlin: enum TransactionState {
    re.compile(
        r"enum\s+(?:class\s+)?(\w*(?:Status|State|Phase|Stage)\w*)\s*\{",
        re.IGNORECASE,
    ),
    # TypeScript: enum PaymentStatus {
    re.compile(
        r"(?:export\s+)?enum\s+(\w*(?:Status|State|Phase|Stage)\w*)\s*\{",
        re.IGNORECASE,
    ),
    # Go: type OrderState int / type OrderState string
    re.compile(
        r"type\s+(\w*(?:Status|State|Phase|Stage)\w*)\s+(?:int|string|uint)\b",
        re.IGNORECASE,
    ),
]

# Transition patterns: function calls, switch/match arms, if-chains
_TRANSITION_PATTERNS = [
    # Python/generic: transition(from_state, to_state) or set_status(new_state)
    re.compile(
        r"(?:transition|set_status|change_state|update_status|move_to)\s*\(\s*['\"]?(\w+)['\"]?\s*(?:,|to=)\s*['\"]?(\w+)['\"]?",
        re.IGNORECASE,
    ),
    # Assignment: self.status = "CAPTURED"  /  order.state = State.SETTLED
    re.compile(
        r"(?:self|this|order|txn|transaction|payment)\s*\.\s*(?:status|state)\s*=\s*(?:\w+\.)?['\"]?(\w+)['\"]?",
        re.IGNORECASE,
    ),
    # Arrow / mapping: CREATED -> AUTHORIZED  or  CREATED => AUTHORIZED
    re.compile(
        r"['\"]?(\b[A-Z_]{3,})\b['\"]?\s*(?:->|=>|→)\s*['\"]?(\b[A-Z_]{3,})\b['\"]?",
    ),
    # Match/case or switch: case "AUTHORIZED": ... -> CAPTURED
    re.compile(
        r"case\s+['\"]?(\b[A-Z_]{3,})\b['\"]?\s*(?::|=>|->)",
    ),
]

# File extensions to scan
_SOURCE_EXTENSIONS = {
    ".py", ".java", ".kt", ".kts", ".go", ".ts", ".tsx", ".js", ".jsx",
    ".scala", ".rs", ".rb", ".cs", ".swift",
}

# Directories to skip
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "vendor", "target", ".gradle", ".idea", ".vscode",
}

# Maximum files to scan (safety valve)
_MAX_FILES = 5000
_MAX_FILE_SIZE = 512 * 1024  # 512 KB


# ---------------------------------------------------------------------------
# Core tracer
# ---------------------------------------------------------------------------

class TxnFlowTracer:
    """Trace transaction flows from logs (ES) or from code (AST scan)."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("TxnFlowTracer initialized for %s", cwd)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def trace_from_logs(self, order_id: str, env: str = "dev") -> TransactionFlow:
        """Reconstruct a transaction flow from Elasticsearch/Kibana logs.

        Queries ES filtered by *order_id*, sorts by timestamp, and rebuilds
        the step sequence.  Returns an empty flow if ES is unavailable.
        """
        logger.info("Tracing order %s from %s logs", order_id, env)
        raw_logs = self._query_es_logs(order_id, env)

        if not raw_logs:
            logger.warning("No logs found for order %s in %s", order_id, env)
            return TransactionFlow(
                order_id=order_id,
                steps=[],
                total_latency_ms=0,
                current_state="UNKNOWN",
                bottleneck="",
            )

        steps = self._logs_to_steps(raw_logs)
        total_latency = sum(s.latency_ms for s in steps)
        current = steps[-1].status if steps else "UNKNOWN"
        bottleneck = self._identify_bottleneck(steps)

        flow = TransactionFlow(
            order_id=order_id,
            steps=steps,
            total_latency_ms=total_latency,
            current_state=current,
            bottleneck=bottleneck,
        )
        flow.diagram = self.generate_sequence_diagram(flow)
        return flow

    def trace_from_code(self) -> TransactionFlow:
        """Scan the repo for state machine patterns and build a flow.

        Works purely from code — no external services required.
        """
        logger.info("Tracing transaction flow from code in %s", self.cwd)

        states = self._scan_state_enums()
        if not states:
            logger.info("No payment state enums found")
            return TransactionFlow(
                order_id="(from-code)",
                steps=[],
                total_latency_ms=0,
                current_state="NONE",
            )

        transitions = self._scan_transitions(states)
        steps = self._transitions_to_steps(states, transitions)
        current = states[-1] if states else "NONE"
        bottleneck = self._identify_bottleneck(steps)

        flow = TransactionFlow(
            order_id="(from-code)",
            steps=steps,
            total_latency_ms=0,
            current_state=current,
            bottleneck=bottleneck,
        )
        flow.diagram = self.generate_state_diagram(flow)
        return flow

    # -----------------------------------------------------------------------
    # Diagram generators
    # -----------------------------------------------------------------------

    def generate_sequence_diagram(self, flow: TransactionFlow) -> str:
        """Generate a Mermaid sequenceDiagram from the flow steps."""
        lines: list[str] = ["sequenceDiagram"]

        # Collect unique services in order
        seen: dict[str, bool] = {}
        for step in flow.steps:
            if step.service not in seen:
                seen[step.service] = True

        participants = list(seen.keys()) if seen else ["Client", "Gateway", "Acquirer", "Bank"]
        for p in participants:
            lines.append(f"    participant {p}")

        prev_service = participants[0] if participants else "Client"
        for step in flow.steps:
            target = step.service if step.service != prev_service else (
                participants[min(participants.index(step.service) + 1, len(participants) - 1)]
                if step.service in participants else step.service
            )
            latency_note = f" ({step.latency_ms:.0f}ms)" if step.latency_ms else ""
            arrow = "-->>" if step.status in ("FAILED", "DECLINED", "ERROR") else "->>"
            lines.append(f"    {prev_service}{arrow}{target}: {step.action}{latency_note}")
            prev_service = target

        return "\n".join(lines)

    def generate_state_diagram(self, flow: TransactionFlow) -> str:
        """Generate a Mermaid stateDiagram-v2 from the flow steps."""
        lines: list[str] = ["stateDiagram-v2"]

        if not flow.steps:
            lines.append("    [*] --> EMPTY")
            return "\n".join(lines)

        # First state from [*]
        first_state = flow.steps[0].action.split(" -> ")[0] if " -> " in flow.steps[0].action else flow.steps[0].status
        lines.append(f"    [*] --> {first_state}")

        seen_transitions: set[str] = set()
        for step in flow.steps:
            if " -> " in step.action:
                parts = step.action.split(" -> ")
                from_s, to_s = parts[0].strip(), parts[1].strip()
                trigger = step.metadata.get("trigger", step.service)
                key = f"{from_s}->{to_s}"
                if key not in seen_transitions:
                    seen_transitions.add(key)
                    lines.append(f"    {from_s} --> {to_s}: {trigger}")
            elif step.status:
                key = f"{step.action}->{step.status}"
                if key not in seen_transitions:
                    seen_transitions.add(key)
                    lines.append(f"    {step.action} --> {step.status}: {step.service}")

        # Terminal state
        last_state = flow.current_state
        if last_state and last_state not in ("NONE", "UNKNOWN"):
            lines.append(f"    {last_state} --> [*]")

        return "\n".join(lines)

    def generate_terminal(self, flow: TransactionFlow) -> str:
        """Render a colored terminal view with latency bars."""
        if not flow.steps:
            return "  No steps found."

        lines: list[str] = []
        max_latency = max((s.latency_ms for s in flow.steps), default=1) or 1
        bar_width = 10

        for step in flow.steps:
            # Status icon
            if step.status in ("FAILED", "DECLINED", "ERROR", "CANCELLED"):
                icon = "\033[31m\u2718\033[0m"  # red X
            elif step.latency_ms == 0 and step.status not in ("COMPLETED", "SETTLED", "SUCCESS"):
                icon = "\u23f3"  # hourglass (pending)
            else:
                icon = "\033[32m\u2705\033[0m"  # green checkmark

            # Latency bar
            if step.latency_ms > 0:
                filled = max(1, int((step.latency_ms / max_latency) * bar_width))
                bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
                latency_str = f"({step.latency_ms:.0f}ms) {bar}"
            else:
                latency_str = "(pending)"

            lines.append(f"  {icon} {step.action:<40s} {latency_str}")

        # Summary
        lines.append("")
        lines.append(f"  Total latency: {flow.total_latency_ms:.0f}ms")
        if flow.bottleneck:
            lines.append(f"  Bottleneck:    {flow.bottleneck}")
        lines.append(f"  Current state: {flow.current_state}")

        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # Code scanning internals
    # -----------------------------------------------------------------------

    def _scan_state_enums(self) -> list[str]:
        """Find enum/class definitions that look like payment states."""
        logger.debug("Scanning for state enums in %s", self.cwd)
        found_states: list[str] = []
        enum_files = self._source_files()

        for filepath in enum_files:
            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue

            # Check if file has an enum-like class with state names
            for pattern in _ENUM_CLASS_PATTERNS:
                match = pattern.search(content)
                if match:
                    logger.debug("Found state enum '%s' in %s", match.group(1), filepath)
                    # Extract individual state values from the enum body
                    states = self._extract_enum_values(content, match.end())
                    if states:
                        found_states.extend(states)
                        break  # one enum per file is enough

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for s in found_states:
            upper = s.upper()
            if upper not in seen:
                seen.add(upper)
                unique.append(upper)

        # Sort by likely lifecycle order if we recognize the states
        ordered = self._order_states(unique)
        logger.info("Found %d unique states: %s", len(ordered), ordered)
        return ordered

    def _extract_enum_values(self, content: str, start_pos: int) -> list[str]:
        """Extract enum member names from the body after an enum class definition."""
        # Take a chunk after the class/enum definition
        chunk = content[start_pos:start_pos + 2000]
        values: list[str] = []

        for line in chunk.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//", "/*", "*")):
                continue
            # End of enum body
            if stripped.startswith(("class ", "def ", "}", "enum ")):
                break

            # Python: STATE_NAME = "value" or STATE_NAME = auto()
            m = re.match(r"(\b[A-Z][A-Z0-9_]{2,})\b\s*=", stripped)
            if m and _PAYMENT_STATE_PATTERNS.search(m.group(1)):
                values.append(m.group(1))
                continue

            # Java/TS/Go: STATE_NAME, or STATE_NAME(...)
            m = re.match(r"(\b[A-Z][A-Z0-9_]{2,})\b\s*[,(;]?", stripped)
            if m and _PAYMENT_STATE_PATTERNS.search(m.group(1)):
                values.append(m.group(1))

        return values

    def _scan_transitions(self, states: list[str]) -> list[tuple[str, str, str]]:
        """Find state transition logic — returns (from_state, to_state, trigger)."""
        logger.debug("Scanning for transitions among %d states", len(states))
        state_set = {s.upper() for s in states}
        transitions: list[tuple[str, str, str]] = []
        seen: set[str] = set()

        for filepath in self._source_files():
            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue

            # Look for arrow / mapping transitions
            for pattern in _TRANSITION_PATTERNS:
                for match in pattern.finditer(content):
                    groups = match.groups()
                    if len(groups) >= 2:
                        from_s = groups[0].upper()
                        to_s = groups[1].upper()
                        if from_s in state_set and to_s in state_set:
                            key = f"{from_s}->{to_s}"
                            if key not in seen:
                                seen.add(key)
                                trigger = filepath.stem
                                transitions.append((from_s, to_s, trigger))

            # Implicit sequential transitions from ordered appearances
            last_state: Optional[str] = None
            for line in content.splitlines():
                for state in states:
                    if re.search(rf"\b{re.escape(state)}\b", line, re.IGNORECASE):
                        if last_state and last_state != state:
                            key = f"{last_state}->{state}"
                            if key not in seen:
                                seen.add(key)
                                transitions.append((last_state, state, filepath.stem))
                        last_state = state
                        break

        logger.info("Found %d transitions", len(transitions))
        return transitions

    def _transitions_to_steps(
        self,
        states: list[str],
        transitions: list[tuple[str, str, str]],
    ) -> list[FlowStep]:
        """Convert transitions into FlowStep objects."""
        steps: list[FlowStep] = []

        if transitions:
            for from_s, to_s, trigger in transitions:
                steps.append(FlowStep(
                    service=trigger,
                    action=f"{from_s} -> {to_s}",
                    status=to_s,
                    metadata={"trigger": trigger},
                ))
        elif states:
            # No explicit transitions found — create linear flow from states
            for i in range(len(states) - 1):
                steps.append(FlowStep(
                    service="code",
                    action=f"{states[i]} -> {states[i + 1]}",
                    status=states[i + 1],
                    metadata={"trigger": "sequential"},
                ))

        return steps

    def _order_states(self, states: list[str]) -> list[str]:
        """Sort states by typical payment lifecycle order."""
        order_map = {
            "INIT": 0, "CREATED": 1, "INITIATED": 2, "CHECKOUT": 3,
            "SUBMITTED": 4, "PENDING": 5, "PROCESSING": 6, "IN_PROGRESS": 7,
            "AUTHORIZED": 10, "APPROVED": 11,
            "CAPTURED": 20, "COMPLETED": 21, "SUCCESS": 22,
            "SETTLED": 30,
            "REFUNDED": 40, "PARTIAL_REFUND": 41, "REVERSED": 42,
            "VOIDED": 43, "CHARGED_BACK": 44,
            "FAILED": 50, "DECLINED": 51, "REJECTED": 52,
            "CANCELLED": 53, "EXPIRED": 54, "TIMEOUT": 55, "FAILURE": 56,
            "DISPUTED": 60,
        }

        def sort_key(s: str) -> int:
            return order_map.get(s, 99)

        return sorted(states, key=sort_key)

    # -----------------------------------------------------------------------
    # Elasticsearch / log helpers
    # -----------------------------------------------------------------------

    def _query_es_logs(self, order_id: str, env: str) -> list[dict]:
        """Query Elasticsearch logs filtered by order_id.

        Uses elasticsearch_client if available; returns empty list otherwise.
        """
        try:
            from code_agents.cicd.elasticsearch_client import ElasticsearchClient  # type: ignore
        except ImportError:
            logger.debug("elasticsearch_client not available — skipping log query")
            return []

        try:
            es = ElasticsearchClient()
            index = f"transactions-{env}-*"
            query = {
                "bool": {
                    "must": [
                        {"match": {"order_id": order_id}},
                    ]
                }
            }
            results = es.search(index=index, query=query, sort="@timestamp:asc", size=100)
            return results.get("hits", {}).get("hits", [])
        except Exception as exc:
            logger.warning("ES query failed for order %s: %s", order_id, exc)
            return []

    def _logs_to_steps(self, raw_logs: list[dict]) -> list[FlowStep]:
        """Convert raw ES log hits into FlowStep objects."""
        steps: list[FlowStep] = []
        prev_ts: Optional[float] = None

        for hit in raw_logs:
            source = hit.get("_source", {})
            ts_str = source.get("@timestamp", "")
            service = source.get("service", source.get("service_name", "unknown"))
            action = source.get("action", source.get("message", ""))
            status = source.get("status", source.get("state", ""))

            # Calculate latency from previous step
            latency = 0.0
            ts_epoch = source.get("timestamp_epoch")
            if ts_epoch and prev_ts:
                latency = (ts_epoch - prev_ts) * 1000  # ms
            if ts_epoch:
                prev_ts = ts_epoch

            steps.append(FlowStep(
                service=service,
                action=action,
                status=status,
                timestamp=ts_str,
                latency_ms=max(0, latency),
                metadata={k: v for k, v in source.items() if k not in (
                    "@timestamp", "service", "action", "status", "state",
                    "message", "timestamp_epoch", "service_name",
                )},
            ))

        return steps

    def _identify_bottleneck(self, steps: list[FlowStep]) -> str:
        """Return the step with the highest latency."""
        if not steps:
            return ""

        slowest = max(steps, key=lambda s: s.latency_ms)
        if slowest.latency_ms <= 0:
            return ""

        return f"{slowest.action} ({slowest.latency_ms:.0f}ms)"

    # -----------------------------------------------------------------------
    # File discovery
    # -----------------------------------------------------------------------

    def _source_files(self) -> list[Path]:
        """Return source files in the repo, respecting skip rules."""
        root = Path(self.cwd)
        files: list[Path] = []
        count = 0

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skipped directories in-place
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]

            for fname in filenames:
                if count >= _MAX_FILES:
                    return files
                ext = os.path.splitext(fname)[1]
                if ext in _SOURCE_EXTENSIONS:
                    fpath = Path(dirpath) / fname
                    try:
                        if fpath.stat().st_size <= _MAX_FILE_SIZE:
                            files.append(fpath)
                            count += 1
                    except OSError:
                        continue

        return files
