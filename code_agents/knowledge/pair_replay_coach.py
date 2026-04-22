"""Pair Replay Coach — analyze coding session patterns for coaching suggestions."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.pair_replay_coach")


@dataclass
class SessionEvent:
    """A single event in a coding session."""
    timestamp: str = ""
    event_type: str = ""  # edit, save, run, error, search, navigate, undo
    file_path: str = ""
    details: str = ""
    duration_ms: float = 0.0


@dataclass
class PatternInsight:
    """An identified coding pattern with coaching suggestion."""
    pattern_name: str = ""
    description: str = ""
    frequency: int = 0
    impact: str = "low"  # low, medium, high
    coaching_tip: str = ""
    examples: list[str] = field(default_factory=list)


@dataclass
class EfficiencyMetrics:
    """Quantified efficiency metrics from the session."""
    total_duration_min: float = 0.0
    active_coding_pct: float = 0.0
    context_switches: int = 0
    undo_redo_count: int = 0
    error_fix_cycles: int = 0
    search_count: int = 0
    files_touched: int = 0
    avg_time_per_file_min: float = 0.0


@dataclass
class CoachingReport:
    """Complete coaching report from session analysis."""
    summary: str = ""
    metrics: EfficiencyMetrics = field(default_factory=EfficiencyMetrics)
    patterns: list[PatternInsight] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    improvement_areas: list[str] = field(default_factory=list)
    productivity_score: int = 0  # 1-100
    recommendations: list[str] = field(default_factory=list)


# Anti-patterns to detect
ANTI_PATTERNS = {
    "thrashing": {
        "description": "Rapidly switching between files without completing changes",
        "tip": "Focus on one file at a time. Use a task list to stay on track.",
    },
    "trial_and_error": {
        "description": "Multiple run-error-fix cycles on the same issue",
        "tip": "Read error messages carefully. Add debugging output before retrying.",
    },
    "excessive_undo": {
        "description": "Frequent undo/redo indicating uncertainty about approach",
        "tip": "Plan your approach before coding. Sketch the solution first.",
    },
    "yak_shaving": {
        "description": "Getting sidetracked by tangential fixes",
        "tip": "Note side-tasks in a TODO list. Complete the main task first.",
    },
    "copy_paste_heavy": {
        "description": "Excessive copy-paste indicating potential for abstraction",
        "tip": "Extract repeated patterns into functions or templates.",
    },
}


class PairReplayCoach:
    """Analyzes coding session recordings for efficiency coaching."""

    def __init__(self):
        self.events: list[SessionEvent] = []

    def analyze(self, events: list[dict]) -> CoachingReport:
        """Analyze a coding session and produce coaching report."""
        logger.info("Analyzing coding session with %d events", len(events))

        self.events = [self._parse_event(e) for e in events]
        self.events = [e for e in self.events if e.event_type]

        metrics = self._compute_metrics()
        patterns = self._detect_patterns()
        strengths = self._identify_strengths(metrics, patterns)
        improvements = self._identify_improvements(metrics, patterns)
        score = self._compute_score(metrics, patterns)
        recommendations = self._generate_recommendations(patterns, metrics)

        report = CoachingReport(
            summary=self._generate_summary(metrics, patterns),
            metrics=metrics,
            patterns=patterns,
            strengths=strengths,
            improvement_areas=improvements,
            productivity_score=score,
            recommendations=recommendations,
        )
        logger.info("Coaching report: score=%d, %d patterns, %d recommendations",
                     score, len(patterns), len(recommendations))
        return report

    def _parse_event(self, raw: dict) -> SessionEvent:
        """Parse raw event dict."""
        return SessionEvent(
            timestamp=raw.get("timestamp", ""),
            event_type=raw.get("type", raw.get("event_type", "")),
            file_path=raw.get("file", raw.get("file_path", "")),
            details=raw.get("details", ""),
            duration_ms=float(raw.get("duration_ms", raw.get("duration", 0))),
        )

    def _compute_metrics(self) -> EfficiencyMetrics:
        """Compute efficiency metrics from events."""
        total_ms = sum(e.duration_ms for e in self.events)
        files = set(e.file_path for e in self.events if e.file_path)
        edits = [e for e in self.events if e.event_type == "edit"]
        undos = [e for e in self.events if e.event_type == "undo"]
        errors = [e for e in self.events if e.event_type == "error"]
        searches = [e for e in self.events if e.event_type == "search"]

        # Context switches: file changes in sequence
        switches = 0
        prev_file = None
        for e in self.events:
            if e.file_path and e.file_path != prev_file:
                switches += 1
                prev_file = e.file_path

        active_ms = sum(e.duration_ms for e in self.events
                        if e.event_type in ("edit", "run", "search"))
        active_pct = (active_ms / total_ms * 100) if total_ms else 0.0

        total_min = total_ms / 60000
        return EfficiencyMetrics(
            total_duration_min=round(total_min, 1),
            active_coding_pct=round(active_pct, 1),
            context_switches=switches,
            undo_redo_count=len(undos),
            error_fix_cycles=self._count_error_cycles(),
            search_count=len(searches),
            files_touched=len(files),
            avg_time_per_file_min=round(total_min / len(files), 1) if files else 0.0,
        )

    def _count_error_cycles(self) -> int:
        """Count run-error-fix cycles."""
        cycles = 0
        i = 0
        while i < len(self.events) - 1:
            if self.events[i].event_type == "error":
                # Look for subsequent edit
                for j in range(i + 1, min(i + 5, len(self.events))):
                    if self.events[j].event_type == "edit":
                        cycles += 1
                        break
            i += 1
        return cycles

    def _detect_patterns(self) -> list[PatternInsight]:
        """Detect coding patterns (good and bad)."""
        patterns = []

        # Thrashing detection
        switches = self._compute_metrics().context_switches
        events_count = len(self.events)
        if events_count > 10 and switches / events_count > 0.3:
            cfg = ANTI_PATTERNS["thrashing"]
            patterns.append(PatternInsight(
                pattern_name="thrashing",
                description=cfg["description"],
                frequency=switches,
                impact="high",
                coaching_tip=cfg["tip"],
            ))

        # Trial and error
        cycles = self._count_error_cycles()
        if cycles > 3:
            cfg = ANTI_PATTERNS["trial_and_error"]
            patterns.append(PatternInsight(
                pattern_name="trial_and_error",
                description=cfg["description"],
                frequency=cycles,
                impact="medium",
                coaching_tip=cfg["tip"],
            ))

        # Excessive undo
        undos = sum(1 for e in self.events if e.event_type == "undo")
        if undos > 5:
            cfg = ANTI_PATTERNS["excessive_undo"]
            patterns.append(PatternInsight(
                pattern_name="excessive_undo",
                description=cfg["description"],
                frequency=undos,
                impact="medium",
                coaching_tip=cfg["tip"],
            ))

        return patterns

    def _identify_strengths(self, metrics: EfficiencyMetrics,
                            patterns: list[PatternInsight]) -> list[str]:
        """Identify positive behaviors."""
        strengths = []
        if metrics.active_coding_pct > 70:
            strengths.append("High active coding time — good focus")
        if metrics.undo_redo_count < 3:
            strengths.append("Low undo count — confident coding approach")
        if metrics.error_fix_cycles < 2:
            strengths.append("Few error cycles — good first-pass accuracy")
        if not patterns:
            strengths.append("No anti-patterns detected — clean workflow")
        return strengths

    def _identify_improvements(self, metrics: EfficiencyMetrics,
                               patterns: list[PatternInsight]) -> list[str]:
        """Identify areas for improvement."""
        areas = []
        if metrics.active_coding_pct < 50:
            areas.append("Low active coding time — reduce idle/distraction periods")
        if metrics.context_switches > 10:
            areas.append("Many context switches — batch related changes per file")
        for p in patterns:
            if p.impact in ("high", "medium"):
                areas.append(f"{p.pattern_name}: {p.coaching_tip}")
        return areas

    def _compute_score(self, metrics: EfficiencyMetrics,
                       patterns: list[PatternInsight]) -> int:
        """Compute overall productivity score (1-100)."""
        score = 70  # baseline
        score += min(15, int(metrics.active_coding_pct / 10))
        score -= len(patterns) * 5
        score -= min(15, metrics.error_fix_cycles * 3)
        score -= min(10, metrics.undo_redo_count)
        return max(1, min(100, score))

    def _generate_recommendations(self, patterns: list[PatternInsight],
                                  metrics: EfficiencyMetrics) -> list[str]:
        """Generate actionable recommendations."""
        recs = []
        for p in patterns:
            recs.append(f"[{p.impact}] {p.coaching_tip}")
        if metrics.search_count > 10:
            recs.append("Consider using IDE bookmarks/symbols instead of frequent searches")
        if metrics.files_touched > 10 and metrics.total_duration_min < 30:
            recs.append("Many files in short time — consider breaking task into smaller PRs")
        return recs

    def _generate_summary(self, metrics: EfficiencyMetrics,
                          patterns: list[PatternInsight]) -> str:
        """Generate session summary."""
        return (
            f"Session: {metrics.total_duration_min}min, "
            f"{metrics.files_touched} files, "
            f"{metrics.active_coding_pct:.0f}% active, "
            f"{len(patterns)} patterns detected"
        )


def format_report(report: CoachingReport) -> str:
    """Format coaching report as text."""
    lines = [f"# Pair Replay Coaching Report", f"\n{report.summary}\n"]
    lines.append(f"Productivity Score: {report.productivity_score}/100\n")
    if report.strengths:
        lines.append("## Strengths")
        for s in report.strengths:
            lines.append(f"  + {s}")
    if report.improvement_areas:
        lines.append("\n## Improvement Areas")
        for a in report.improvement_areas:
            lines.append(f"  - {a}")
    if report.recommendations:
        lines.append("\n## Recommendations")
        for r in report.recommendations:
            lines.append(f"  * {r}")
    return "\n".join(lines)
