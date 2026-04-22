"""Transaction State Machine Validator — parse and validate payment state machines from code."""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.domain.state_machine_validator")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class State:
    name: str
    is_terminal: bool = False
    is_error: bool = False
    has_timeout_handler: bool = False


@dataclass
class Transition:
    from_state: str
    to_state: str
    trigger: str = ""
    guard_condition: str = ""


@dataclass
class StateMachine:
    name: str
    states: list[State] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    initial_state: str = ""
    terminal_states: list[str] = field(default_factory=list)


@dataclass
class ValidationFinding:
    severity: str  # "critical", "warning", "info"
    message: str
    states_involved: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Heuristics for classifying states
# ---------------------------------------------------------------------------

_TERMINAL_KEYWORDS = {
    "success", "completed", "done", "paid", "settled", "delivered",
    "closed", "fulfilled", "finished", "approved", "confirmed",
    "refunded", "cancelled", "canceled", "rejected", "declined",
    "expired", "voided", "reversed", "charged_back",
}

_ERROR_KEYWORDS = {
    "error", "failed", "failure", "timeout", "timedout", "timed_out",
    "declined", "rejected", "invalid", "aborted", "exception",
}

_PENDING_KEYWORDS = {
    "pending", "processing", "in_progress", "initiated", "awaiting",
    "waiting", "queued", "submitted", "authorizing",
}

_INITIAL_KEYWORDS = {
    "created", "new", "init", "initial", "initiated", "start",
}


def _classify_state(name: str) -> tuple[bool, bool, bool]:
    """Return (is_terminal, is_error, is_pending) for a state name."""
    lower = name.lower().replace("-", "_")
    is_terminal = any(kw in lower for kw in _TERMINAL_KEYWORDS)
    is_error = any(kw in lower for kw in _ERROR_KEYWORDS)
    is_pending = any(kw in lower for kw in _PENDING_KEYWORDS)
    return is_terminal, is_error, is_pending


def _guess_initial(names: list[str]) -> str:
    """Pick the most likely initial state from a list of names."""
    for n in names:
        if any(kw in n.lower().replace("-", "_") for kw in _INITIAL_KEYWORDS):
            return n
    return names[0] if names else ""


# ---------------------------------------------------------------------------
# File scanning helpers
# ---------------------------------------------------------------------------

# Python enums: class FooStatus(Enum): / class FooState(str, Enum):
_RE_PY_ENUM_CLASS = re.compile(
    r"class\s+(\w*(?:Status|State|Phase|Stage)\w*)\s*\(.*?Enum.*?\)\s*:",
    re.IGNORECASE,
)
_RE_PY_ENUM_MEMBER = re.compile(r"^\s+(\w+)\s*=", re.MULTILINE)

# Java enums: public enum PaymentStatus { CREATED, PENDING, ... }
_RE_JAVA_ENUM = re.compile(
    r"enum\s+(\w*(?:Status|State|Phase|Stage)\w*)\s*\{([^}]+)\}",
    re.IGNORECASE | re.DOTALL,
)

# TypeScript string unions: type OrderStatus = "created" | "pending" | ...
_RE_TS_UNION = re.compile(
    r"type\s+(\w*(?:Status|State|Phase|Stage)\w*)\s*=\s*((?:['\"][^'\"]+['\"]\s*\|\s*)*['\"][^'\"]+['\"])",
    re.IGNORECASE,
)

# Transition maps: ALLOWED_TRANSITIONS = { STATE: [STATE, ...], ... }
_RE_TRANSITION_MAP_START = re.compile(
    r"(\w*(?:TRANSITION|ALLOWED|VALID|STATE_MACHINE|NEXT_STATE|STATUS_FLOW)\w*)\s*[=:]\s*\{",
    re.IGNORECASE,
)

_SOURCE_EXTENSIONS = {".py", ".java", ".ts", ".tsx", ".js", ".jsx", ".kt", ".go"}


class StateMachineValidator:
    """Extract and validate state machines from a code repository."""

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        self._source_files: list[Path] = []
        self._collect_source_files()

    # ------------------------------------------------------------------
    # File collection
    # ------------------------------------------------------------------

    def _collect_source_files(self) -> None:
        root = Path(self.cwd)
        skip_dirs = {
            "node_modules", ".git", "__pycache__", "dist", "build",
            ".tox", ".venv", "venv", "env", ".mypy_cache",
        }
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                ext = os.path.splitext(fn)[1]
                if ext in _SOURCE_EXTENSIONS:
                    self._source_files.append(Path(dirpath) / fn)

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def extract(self) -> list[StateMachine]:
        """Find state machines in code and return structured models."""
        machines: list[StateMachine] = []
        enum_machines = self._extract_enum_machines()
        machines.extend(enum_machines)

        transition_machines = self._extract_transition_map_machines()
        # Merge transition info into matching enum machines
        for tm in transition_machines:
            merged = False
            for em in enum_machines:
                if tm.name.lower() in em.name.lower() or em.name.lower() in tm.name.lower():
                    em.transitions.extend(tm.transitions)
                    merged = True
                    break
            if not merged:
                machines.append(tm)

        # Deduplicate terminal_states
        for sm in machines:
            sm.terminal_states = list(dict.fromkeys(sm.terminal_states))

        logger.info("Extracted %d state machine(s) from %s", len(machines), self.cwd)
        return machines

    def _extract_enum_machines(self) -> list[StateMachine]:
        """Scan for enum classes with state-like names."""
        machines: list[StateMachine] = []
        for fpath in self._source_files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            ext = fpath.suffix

            if ext == ".py":
                machines.extend(self._parse_py_enums(content, str(fpath)))
            elif ext == ".java" or ext == ".kt":
                machines.extend(self._parse_java_enums(content, str(fpath)))
            elif ext in (".ts", ".tsx", ".js", ".jsx"):
                machines.extend(self._parse_ts_unions(content, str(fpath)))

        return machines

    def _parse_py_enums(self, content: str, fpath: str) -> list[StateMachine]:
        results: list[StateMachine] = []
        for match in _RE_PY_ENUM_CLASS.finditer(content):
            class_name = match.group(1)
            start = match.end()
            # Find the body: lines indented after class definition
            body_lines: list[str] = []
            for line in content[start:].splitlines():
                stripped = line.lstrip()
                if stripped and not line[0].isspace() and not stripped.startswith("#"):
                    break
                body_lines.append(line)
            body = "\n".join(body_lines)
            members = _RE_PY_ENUM_MEMBER.findall(body)
            members = [m for m in members if not m.startswith("_")]
            if members:
                results.append(self._build_machine(class_name, members))
        return results

    def _parse_java_enums(self, content: str, fpath: str) -> list[StateMachine]:
        results: list[StateMachine] = []
        for match in _RE_JAVA_ENUM.finditer(content):
            enum_name = match.group(1)
            body = match.group(2)
            # Java enum members: NAME, NAME, ... (possibly with constructor args)
            members = re.findall(r"\b([A-Z][A-Z0-9_]+)\b", body)
            # Filter out common Java noise
            members = [m for m in members if len(m) > 1]
            if members:
                results.append(self._build_machine(enum_name, members))
        return results

    def _parse_ts_unions(self, content: str, fpath: str) -> list[StateMachine]:
        results: list[StateMachine] = []
        for match in _RE_TS_UNION.finditer(content):
            type_name = match.group(1)
            union_str = match.group(2)
            members = re.findall(r"['\"]([^'\"]+)['\"]", union_str)
            if members:
                results.append(self._build_machine(type_name, members))
        return results

    def _build_machine(self, name: str, state_names: list[str]) -> StateMachine:
        states: list[State] = []
        terminal: list[str] = []
        for sn in state_names:
            is_term, is_err, is_pend = _classify_state(sn)
            s = State(
                name=sn,
                is_terminal=is_term or is_err,
                is_error=is_err,
                has_timeout_handler=False,
            )
            states.append(s)
            if is_term or is_err:
                terminal.append(sn)

        initial = _guess_initial(state_names)
        return StateMachine(
            name=name,
            states=states,
            transitions=[],
            initial_state=initial,
            terminal_states=terminal,
        )

    def _extract_transition_map_machines(self) -> list[StateMachine]:
        """Look for ALLOWED_TRANSITIONS = {STATE: [STATE, STATE]} patterns."""
        machines: list[StateMachine] = []
        for fpath in self._source_files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for match in _RE_TRANSITION_MAP_START.finditer(content):
                var_name = match.group(1)
                start = match.start()
                # Extract the full dict body by brace matching
                brace_count = 0
                body_start = content.index("{", start)
                i = body_start
                while i < len(content):
                    if content[i] == "{":
                        brace_count += 1
                    elif content[i] == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            break
                    i += 1
                body = content[body_start:i + 1]
                transitions = self._parse_transition_body(body)
                if transitions:
                    # Infer states from transitions
                    all_names: set[str] = set()
                    for t in transitions:
                        all_names.add(t.from_state)
                        all_names.add(t.to_state)
                    states = []
                    terminal = []
                    for sn in sorted(all_names):
                        is_term, is_err, _ = _classify_state(sn)
                        states.append(State(
                            name=sn,
                            is_terminal=is_term or is_err,
                            is_error=is_err,
                        ))
                        if is_term or is_err:
                            terminal.append(sn)
                    machines.append(StateMachine(
                        name=var_name,
                        states=states,
                        transitions=transitions,
                        initial_state=_guess_initial([s.name for s in states]),
                        terminal_states=terminal,
                    ))
        return machines

    def _parse_transition_body(self, body: str) -> list[Transition]:
        """Parse a dict-like body into Transition objects.

        Handles patterns like:
          STATE_A: [STATE_B, STATE_C],
          "created": ["pending", "cancelled"],
        """
        transitions: list[Transition] = []
        # Match key: [values] or key: {values}
        quote = r"""['"]*"""
        word = r"""([\w.]+)"""
        pattern = re.compile(
            quote + word + quote + r"""\s*[:=]\s*[\[{(]\s*"""
            + r"""((?:""" + quote + r"""[\w.]+""" + quote + r"""\s*,?\s*)*)"""
            + r"""\s*[\]})]\s*""",
            re.MULTILINE,
        )
        word_re = re.compile(r"[\w.]+")
        for m in pattern.finditer(body):
            from_state = m.group(1).split(".")[-1]  # Handle Enum.MEMBER
            targets_str = m.group(2)
            targets = word_re.findall(targets_str)
            for t in targets:
                to_state = t.split(".")[-1]
                transitions.append(Transition(from_state=from_state, to_state=to_state))
        return transitions

    # ------------------------------------------------------------------
    # Scanning helpers (public)
    # ------------------------------------------------------------------

    def _scan_enum_states(self) -> list[tuple[str, list[str]]]:
        """Return (enum_name, [member_names]) for every state-like enum."""
        results: list[tuple[str, list[str]]] = []
        for sm in self._extract_enum_machines():
            results.append((sm.name, [s.name for s in sm.states]))
        return results

    def _scan_transition_maps(self) -> list[dict]:
        """Return raw transition map dicts."""
        results: list[dict] = []
        for sm in self._extract_transition_map_machines():
            tmap: dict[str, list[str]] = defaultdict(list)
            for t in sm.transitions:
                tmap[t.from_state].append(t.to_state)
            results.append({"name": sm.name, "transitions": dict(tmap)})
        return results

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, sm: StateMachine) -> list[ValidationFinding]:
        """Run all validation checks on a state machine."""
        findings: list[ValidationFinding] = []
        findings.extend(self._check_unreachable_states(sm))
        findings.extend(self._check_dead_end_states(sm))
        findings.extend(self._check_impossible_transitions(sm))
        findings.extend(self._check_error_recovery(sm))
        findings.extend(self._check_timeout_handlers(sm))
        findings.extend(self._check_terminal_reachability(sm))
        logger.info(
            "Validated %s: %d finding(s) (%d critical)",
            sm.name,
            len(findings),
            sum(1 for f in findings if f.severity == "critical"),
        )
        return findings

    def _check_unreachable_states(self, sm: StateMachine) -> list[ValidationFinding]:
        """States with no incoming transitions (except initial)."""
        findings: list[ValidationFinding] = []
        incoming: set[str] = set()
        for t in sm.transitions:
            incoming.add(t.to_state)
        for s in sm.states:
            if s.name == sm.initial_state:
                continue
            if s.name not in incoming:
                findings.append(ValidationFinding(
                    severity="warning",
                    message=f"State '{s.name}' has no incoming transitions (unreachable)",
                    states_involved=[s.name],
                ))
        return findings

    def _check_dead_end_states(self, sm: StateMachine) -> list[ValidationFinding]:
        """Non-terminal states with no outgoing transitions."""
        findings: list[ValidationFinding] = []
        outgoing: set[str] = set()
        for t in sm.transitions:
            outgoing.add(t.from_state)
        terminal_names = {s.name for s in sm.states if s.is_terminal}
        for s in sm.states:
            if s.is_terminal:
                continue
            if s.name not in outgoing:
                findings.append(ValidationFinding(
                    severity="critical",
                    message=f"Non-terminal state '{s.name}' has no outgoing transitions (dead end)",
                    states_involved=[s.name],
                ))
        return findings

    def _check_impossible_transitions(self, sm: StateMachine) -> list[ValidationFinding]:
        """Transitions from terminal states."""
        findings: list[ValidationFinding] = []
        terminal_names = {s.name for s in sm.states if s.is_terminal}
        for t in sm.transitions:
            if t.from_state in terminal_names:
                findings.append(ValidationFinding(
                    severity="warning",
                    message=f"Transition from terminal state '{t.from_state}' -> '{t.to_state}' (impossible transition)",
                    states_involved=[t.from_state, t.to_state],
                ))
        return findings

    def _check_error_recovery(self, sm: StateMachine) -> list[ValidationFinding]:
        """Error states without recovery transitions."""
        findings: list[ValidationFinding] = []
        error_states = {s.name for s in sm.states if s.is_error}
        outgoing_from_error: set[str] = set()
        for t in sm.transitions:
            if t.from_state in error_states:
                outgoing_from_error.add(t.from_state)
        for es in error_states:
            if es not in outgoing_from_error:
                findings.append(ValidationFinding(
                    severity="warning",
                    message=f"Error state '{es}' has no recovery transitions",
                    states_involved=[es],
                ))
        return findings

    def _check_timeout_handlers(self, sm: StateMachine) -> list[ValidationFinding]:
        """Pending/processing states without timeout handlers."""
        findings: list[ValidationFinding] = []
        for s in sm.states:
            _, _, is_pending = _classify_state(s.name)
            if is_pending and not s.has_timeout_handler:
                findings.append(ValidationFinding(
                    severity="warning",
                    message=f"Pending state '{s.name}' has no timeout handler",
                    states_involved=[s.name],
                ))
        return findings

    def _check_terminal_reachability(self, sm: StateMachine) -> list[ValidationFinding]:
        """BFS: can every state eventually reach a terminal state?"""
        findings: list[ValidationFinding] = []
        if not sm.transitions:
            return findings

        terminal_names = {s.name for s in sm.states if s.is_terminal}
        if not terminal_names:
            return findings

        # Build adjacency list
        adj: dict[str, list[str]] = defaultdict(list)
        for t in sm.transitions:
            adj[t.from_state].append(t.to_state)

        # For each non-terminal state, BFS to see if any terminal is reachable
        all_state_names = {s.name for s in sm.states}
        for s in sm.states:
            if s.is_terminal:
                continue
            # BFS from s
            visited: set[str] = set()
            queue: deque[str] = deque([s.name])
            reached_terminal = False
            while queue:
                cur = queue.popleft()
                if cur in terminal_names:
                    reached_terminal = True
                    break
                if cur in visited:
                    continue
                visited.add(cur)
                for nxt in adj.get(cur, []):
                    if nxt not in visited:
                        queue.append(nxt)
            if not reached_terminal:
                findings.append(ValidationFinding(
                    severity="critical",
                    message=f"State '{s.name}' cannot reach any terminal state",
                    states_involved=[s.name],
                ))
        return findings

    # ------------------------------------------------------------------
    # Diagram generation
    # ------------------------------------------------------------------

    def generate_diagram(self, sm: StateMachine) -> str:
        """Generate Mermaid stateDiagram-v2 for a state machine."""
        lines: list[str] = []
        lines.append("stateDiagram-v2")

        # Initial state arrow
        if sm.initial_state:
            lines.append(f"    [*] --> {sm.initial_state}")

        # Transitions
        for t in sm.transitions:
            label = ""
            if t.trigger:
                label = f" : {t.trigger}"
                if t.guard_condition:
                    label += f" [{t.guard_condition}]"
            lines.append(f"    {t.from_state} --> {t.to_state}{label}")

        # Terminal states
        for ts in sm.terminal_states:
            lines.append(f"    {ts} --> [*]")

        # State notes for error states
        for s in sm.states:
            if s.is_error:
                lines.append(f"    note right of {s.name} : error state")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_validation_report(
    machines: list[StateMachine],
    findings: list[ValidationFinding],
) -> str:
    """Format a human-readable validation report."""
    lines: list[str] = []

    lines.append("")
    lines.append(f"  State Machine Validation Report")
    lines.append(f"  {'=' * 40}")
    lines.append("")

    for sm in machines:
        state_names = [s.name for s in sm.states]
        terminal_names = [s.name for s in sm.states if s.is_terminal]
        error_names = [s.name for s in sm.states if s.is_error]

        lines.append(f"  {sm.name}")
        lines.append(f"    States ({len(sm.states)}): {', '.join(state_names)}")
        lines.append(f"    Initial: {sm.initial_state or '(unknown)'}")
        lines.append(f"    Terminal: {', '.join(terminal_names) or '(none)'}")
        if error_names:
            lines.append(f"    Error: {', '.join(error_names)}")
        lines.append(f"    Transitions: {len(sm.transitions)}")
        lines.append("")

    if not findings:
        lines.append("  No issues found.")
        lines.append("")
        return "\n".join(lines)

    # Group by severity
    critical = [f for f in findings if f.severity == "critical"]
    warnings = [f for f in findings if f.severity == "warning"]
    info = [f for f in findings if f.severity == "info"]

    if critical:
        lines.append(f"  CRITICAL ({len(critical)})")
        for f in critical:
            lines.append(f"    [!] {f.message}")

    if warnings:
        lines.append(f"  WARNINGS ({len(warnings)})")
        for f in warnings:
            lines.append(f"    [~] {f.message}")

    if info:
        lines.append(f"  INFO ({len(info)})")
        for f in info:
            lines.append(f"    [i] {f.message}")

    lines.append("")
    lines.append(f"  Total: {len(critical)} critical, {len(warnings)} warning(s), {len(info)} info")
    lines.append("")
    return "\n".join(lines)
