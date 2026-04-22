"""Cognitive Monitor — detect developer thrashing vs flow from coding patterns."""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.observability.cognitive_monitor")


@dataclass
class CodingEvent:
    """A single coding activity event."""
    timestamp: float = 0.0
    event_type: str = ""  # edit, save, compile, error, navigate, search, debug
    file_path: str = ""
    duration_ms: float = 0.0
    details: str = ""


@dataclass
class FlowState:
    """A detected flow state period."""
    start_time: float = 0.0
    end_time: float = 0.0
    duration_min: float = 0.0
    state: str = "neutral"  # flow, thrashing, idle, ramping
    confidence: float = 0.0
    indicators: list[str] = field(default_factory=list)


@dataclass
class CognitiveMetrics:
    """Quantified cognitive metrics."""
    flow_time_pct: float = 0.0
    thrashing_time_pct: float = 0.0
    idle_time_pct: float = 0.0
    avg_focus_duration_min: float = 0.0
    context_switches_per_hour: float = 0.0
    error_recovery_time_ms: float = 0.0
    edit_velocity: float = 0.0  # edits per minute during flow


@dataclass
class CognitiveReport:
    """Complete cognitive monitoring report."""
    metrics: CognitiveMetrics = field(default_factory=CognitiveMetrics)
    flow_states: list[FlowState] = field(default_factory=list)
    total_events: int = 0
    session_duration_min: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Thresholds
FLOW_MIN_EDITS_PER_MIN = 3
THRASH_MAX_FILE_SWITCHES = 5  # per 5 min window
IDLE_THRESHOLD_MS = 120_000  # 2 min gap = idle


class CognitiveMonitor:
    """Monitors developer coding patterns for cognitive state detection."""

    def __init__(self):
        self.events: list[CodingEvent] = []

    def analyze(self, events: list[dict]) -> CognitiveReport:
        """Analyze coding events for cognitive states."""
        logger.info("Analyzing %d coding events", len(events))

        self.events = [self._parse_event(e) for e in events]
        self.events.sort(key=lambda e: e.timestamp)

        if not self.events:
            return CognitiveReport()

        # Compute session duration
        session_min = (self.events[-1].timestamp - self.events[0].timestamp) / 60000
        if session_min <= 0:
            session_min = sum(e.duration_ms for e in self.events) / 60000

        # Detect flow states in windows
        states = self._detect_states()

        # Compute metrics
        metrics = self._compute_metrics(states, session_min)

        # Generate recommendations
        recommendations = self._recommend(metrics, states)

        report = CognitiveReport(
            metrics=metrics,
            flow_states=states,
            total_events=len(self.events),
            session_duration_min=round(session_min, 1),
            recommendations=recommendations,
            warnings=self._generate_warnings(metrics),
        )
        logger.info("Cognitive report: %.0f%% flow, %.0f%% thrashing",
                     metrics.flow_time_pct, metrics.thrashing_time_pct)
        return report

    def _parse_event(self, raw: dict) -> CodingEvent:
        """Parse raw event."""
        return CodingEvent(
            timestamp=float(raw.get("timestamp", raw.get("time", 0))),
            event_type=raw.get("type", raw.get("event_type", "")),
            file_path=raw.get("file", raw.get("file_path", "")),
            duration_ms=float(raw.get("duration_ms", raw.get("duration", 0))),
            details=raw.get("details", ""),
        )

    def _detect_states(self) -> list[FlowState]:
        """Detect flow/thrashing states using sliding windows."""
        if not self.events:
            return []

        window_ms = 300_000  # 5 min windows
        states = []
        start = self.events[0].timestamp
        end = self.events[-1].timestamp

        current = start
        while current < end:
            window_end = current + window_ms
            window_events = [e for e in self.events if current <= e.timestamp < window_end]

            if not window_events:
                states.append(FlowState(
                    start_time=current, end_time=window_end,
                    duration_min=window_ms / 60000,
                    state="idle", confidence=0.8,
                    indicators=["No events in window"],
                ))
            else:
                state = self._classify_window(window_events)
                state.start_time = current
                state.end_time = window_end
                state.duration_min = window_ms / 60000
                states.append(state)

            current = window_end

        return states

    def _classify_window(self, events: list[CodingEvent]) -> FlowState:
        """Classify a window of events as flow/thrashing/etc."""
        edits = [e for e in events if e.event_type == "edit"]
        errors = [e for e in events if e.event_type == "error"]
        navigations = [e for e in events if e.event_type == "navigate"]
        searches = [e for e in events if e.event_type == "search"]

        # File switches
        files = []
        for e in events:
            if e.file_path and (not files or files[-1] != e.file_path):
                files.append(e.file_path)
        switches = len(files) - 1 if files else 0

        indicators = []
        state = "neutral"
        confidence = 0.5

        # Flow detection: steady edits, few switches, few errors
        edits_per_min = len(edits) / 5.0
        if edits_per_min >= FLOW_MIN_EDITS_PER_MIN and switches <= 2 and len(errors) <= 1:
            state = "flow"
            confidence = min(0.9, 0.5 + edits_per_min * 0.05)
            indicators.append(f"Steady editing ({edits_per_min:.1f}/min)")
            indicators.append(f"Low context switches ({switches})")

        # Thrashing detection: many switches, errors, searches
        elif switches >= THRASH_MAX_FILE_SWITCHES or (len(errors) > 3 and len(searches) > 2):
            state = "thrashing"
            confidence = min(0.9, 0.5 + switches * 0.05)
            indicators.append(f"High file switches ({switches})")
            if errors:
                indicators.append(f"Many errors ({len(errors)})")

        # Ramping: some edits but with searches/navigation
        elif len(searches) > len(edits) or len(navigations) > len(edits):
            state = "ramping"
            confidence = 0.6
            indicators.append("More searching than editing")

        return FlowState(state=state, confidence=confidence, indicators=indicators)

    def _compute_metrics(self, states: list[FlowState],
                         session_min: float) -> CognitiveMetrics:
        """Compute cognitive metrics from detected states."""
        total_min = session_min if session_min > 0 else 1.0
        flow_min = sum(s.duration_min for s in states if s.state == "flow")
        thrash_min = sum(s.duration_min for s in states if s.state == "thrashing")
        idle_min = sum(s.duration_min for s in states if s.state == "idle")

        # Context switches
        files = []
        for e in self.events:
            if e.file_path and (not files or files[-1] != e.file_path):
                files.append(e.file_path)
        switches_per_hour = (len(files) - 1) / (total_min / 60) if total_min > 0 and len(files) > 1 else 0

        # Edit velocity during flow
        flow_edits = sum(1 for e in self.events
                         if e.event_type == "edit"
                         and any(s.state == "flow" and s.start_time <= e.timestamp < s.end_time
                                 for s in states))
        edit_velocity = flow_edits / flow_min if flow_min > 0 else 0

        # Focus duration: avg consecutive flow state length
        flow_groups = []
        current_group = 0
        for s in states:
            if s.state == "flow":
                current_group += s.duration_min
            else:
                if current_group > 0:
                    flow_groups.append(current_group)
                current_group = 0
        if current_group > 0:
            flow_groups.append(current_group)
        avg_focus = sum(flow_groups) / len(flow_groups) if flow_groups else 0

        return CognitiveMetrics(
            flow_time_pct=round(flow_min / total_min * 100, 1),
            thrashing_time_pct=round(thrash_min / total_min * 100, 1),
            idle_time_pct=round(idle_min / total_min * 100, 1),
            avg_focus_duration_min=round(avg_focus, 1),
            context_switches_per_hour=round(switches_per_hour, 1),
            edit_velocity=round(edit_velocity, 1),
        )

    def _recommend(self, metrics: CognitiveMetrics,
                   states: list[FlowState]) -> list[str]:
        """Generate recommendations."""
        recs = []
        if metrics.thrashing_time_pct > 30:
            recs.append("High thrashing — take a break and plan approach before continuing")
        if metrics.context_switches_per_hour > 20:
            recs.append("Frequent context switches — batch related changes per file")
        if metrics.flow_time_pct < 20:
            recs.append("Low flow time — minimize interruptions and close distractions")
        if metrics.avg_focus_duration_min < 10:
            recs.append("Short focus spans — use Pomodoro technique for longer sessions")
        return recs

    def _generate_warnings(self, metrics: CognitiveMetrics) -> list[str]:
        """Generate warnings."""
        warnings = []
        if metrics.thrashing_time_pct > 50:
            warnings.append("Excessive thrashing — developer may be stuck")
        if metrics.idle_time_pct > 40:
            warnings.append("High idle time — possible blockers or distractions")
        return warnings


def format_report(report: CognitiveReport) -> str:
    """Format cognitive report."""
    lines = [
        "# Cognitive Monitor Report",
        f"Session: {report.session_duration_min}min | Events: {report.total_events}",
        f"Flow: {report.metrics.flow_time_pct:.0f}% | Thrashing: {report.metrics.thrashing_time_pct:.0f}%",
        f"Focus: {report.metrics.avg_focus_duration_min:.0f}min avg | Switches: {report.metrics.context_switches_per_hour:.0f}/hr",
        "",
    ]
    for s in report.flow_states:
        lines.append(f"  [{s.state}] {s.duration_min:.0f}min ({s.confidence:.0%})")
    for r in report.recommendations:
        lines.append(f"  * {r}")
    return "\n".join(lines)
