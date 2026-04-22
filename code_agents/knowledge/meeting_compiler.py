"""Meeting Compiler — transform meeting transcripts into actionable artifacts."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.meeting_compiler")


@dataclass
class ActionItem:
    """An action item extracted from meeting transcript."""
    description: str = ""
    assignee: str = ""
    deadline: str = ""
    priority: str = "medium"
    source_line: int = 0


@dataclass
class JiraTicketDraft:
    """A Jira ticket generated from meeting content."""
    title: str = ""
    description: str = ""
    ticket_type: str = "Task"
    priority: str = "Medium"
    assignee: str = ""
    labels: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass
class ADRDraft:
    """Architecture Decision Record from meeting decisions."""
    title: str = ""
    status: str = "Proposed"
    context: str = ""
    decision: str = ""
    consequences: list[str] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)


@dataclass
class ConflictFlag:
    """A detected conflict or disagreement in the meeting."""
    topic: str = ""
    positions: list[dict] = field(default_factory=list)
    resolution: str = ""
    resolved: bool = False


@dataclass
class MeetingReport:
    """Complete compiled output from a meeting transcript."""
    summary: str = ""
    participants: list[str] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    jira_tickets: list[JiraTicketDraft] = field(default_factory=list)
    adrs: list[ADRDraft] = field(default_factory=list)
    conflicts: list[ConflictFlag] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    key_topics: list[str] = field(default_factory=list)


# Patterns for extraction
ACTION_PATTERNS = [
    re.compile(r"(?:action\s*(?:item)?|todo|task)\s*[:\-]\s*(.+)", re.IGNORECASE),
    re.compile(r"(\w+)\s+(?:will|should|needs? to|must)\s+(.+)", re.IGNORECASE),
    re.compile(r"(?:assigned?\s+to|owner)\s*[:\-]?\s*(\w+)\s*[:\-]\s*(.+)", re.IGNORECASE),
]

DECISION_PATTERNS = [
    re.compile(r"(?:decided?|agreed?|decision)\s*[:\-]\s*(.+)", re.IGNORECASE),
    re.compile(r"(?:we(?:'ll| will)|let'?s)\s+(?:go with|use|pick|choose)\s+(.+)", re.IGNORECASE),
]

QUESTION_PATTERNS = [
    re.compile(r"(?:open\s+question|tbd|to\s+be\s+decided?)\s*[:\-]\s*(.+)", re.IGNORECASE),
    re.compile(r"(.+\?)\s*$"),
]

CONFLICT_PATTERNS = [
    re.compile(r"(?:disagree|but\s+I\s+think|however|on\s+the\s+other\s+hand)\s+(.+)", re.IGNORECASE),
    re.compile(r"(\w+)\s*:\s*(?:no,|I\s+disagree|that\s+won't\s+work)\s*(.+)", re.IGNORECASE),
]

ARCH_PATTERNS = [
    re.compile(r"(?:architecture|design|pattern|approach|stack|framework|migration)\s", re.IGNORECASE),
]


class MeetingCompiler:
    """Compiles meeting transcripts into structured artifacts."""

    def __init__(self, project_context: Optional[str] = None):
        self.project_context = project_context or ""
        self.participants: set[str] = set()

    def analyze(self, transcript: str) -> MeetingReport:
        """Main entry: analyze transcript and produce artifacts."""
        logger.info("Compiling meeting transcript (%d chars)", len(transcript))

        lines = transcript.strip().splitlines()
        self._extract_participants(lines)

        action_items = self._extract_action_items(lines)
        decisions = self._extract_decisions(lines)
        questions = self._extract_open_questions(lines)
        conflicts = self._extract_conflicts(lines)
        topics = self._extract_key_topics(lines)

        jira_tickets = self._generate_jira_tickets(action_items, decisions)
        adrs = self._generate_adrs(decisions, lines)
        summary = self._generate_summary(topics, decisions, action_items)

        report = MeetingReport(
            summary=summary,
            participants=sorted(self.participants),
            action_items=action_items,
            jira_tickets=jira_tickets,
            adrs=adrs,
            conflicts=conflicts,
            decisions=decisions,
            open_questions=questions,
            key_topics=topics,
        )
        logger.info(
            "Compiled: %d actions, %d tickets, %d ADRs, %d conflicts",
            len(action_items), len(jira_tickets), len(adrs), len(conflicts),
        )
        return report

    def _extract_participants(self, lines: list[str]):
        """Extract participant names from transcript."""
        speaker_pattern = re.compile(r"^(\w[\w\s]{0,20})\s*:\s+")
        for line in lines:
            m = speaker_pattern.match(line.strip())
            if m:
                name = m.group(1).strip()
                if len(name) > 1 and name.lower() not in ("action", "todo", "note", "decision"):
                    self.participants.add(name)

    def _extract_action_items(self, lines: list[str]) -> list[ActionItem]:
        """Extract action items from transcript lines."""
        items = []
        for i, line in enumerate(lines):
            for pattern in ACTION_PATTERNS:
                m = pattern.search(line)
                if m:
                    groups = m.groups()
                    if len(groups) >= 2:
                        item = ActionItem(
                            description=groups[1].strip(),
                            assignee=groups[0].strip(),
                            source_line=i + 1,
                        )
                    else:
                        item = ActionItem(
                            description=groups[0].strip(),
                            source_line=i + 1,
                        )
                    items.append(item)
                    break
        return items

    def _extract_decisions(self, lines: list[str]) -> list[str]:
        """Extract decisions made during the meeting."""
        decisions = []
        for line in lines:
            for pattern in DECISION_PATTERNS:
                m = pattern.search(line)
                if m:
                    decisions.append(m.group(1).strip())
                    break
        return decisions

    def _extract_open_questions(self, lines: list[str]) -> list[str]:
        """Extract unresolved questions."""
        questions = []
        for line in lines:
            for pattern in QUESTION_PATTERNS:
                m = pattern.search(line.strip())
                if m:
                    q = m.group(1).strip()
                    if len(q) > 10:
                        questions.append(q)
                    break
        return questions

    def _extract_conflicts(self, lines: list[str]) -> list[ConflictFlag]:
        """Detect disagreements and conflicts."""
        conflicts = []
        for i, line in enumerate(lines):
            for pattern in CONFLICT_PATTERNS:
                m = pattern.search(line)
                if m:
                    topic = self._get_context_topic(lines, i)
                    conflict = ConflictFlag(
                        topic=topic,
                        positions=[{"speaker": m.groups()[0] if len(m.groups()) > 1 else "unknown",
                                    "position": m.groups()[-1].strip()}],
                    )
                    conflicts.append(conflict)
                    break
        return conflicts

    def _extract_key_topics(self, lines: list[str]) -> list[str]:
        """Extract key topics discussed."""
        topics = set()
        heading_pattern = re.compile(r"^#+\s+(.+)|^(?:topic|agenda)\s*[:\-]\s*(.+)", re.IGNORECASE)
        for line in lines:
            m = heading_pattern.match(line.strip())
            if m:
                topic = (m.group(1) or m.group(2) or "").strip()
                if topic:
                    topics.add(topic)
        return sorted(topics)

    def _get_context_topic(self, lines: list[str], index: int) -> str:
        """Get the topic context around a line."""
        start = max(0, index - 3)
        context = " ".join(lines[start:index]).strip()
        return context[:100] if context else "general discussion"

    def _generate_jira_tickets(self, actions: list[ActionItem], decisions: list[str]) -> list[JiraTicketDraft]:
        """Generate Jira ticket drafts from actions and decisions."""
        tickets = []
        for action in actions:
            ticket = JiraTicketDraft(
                title=action.description[:80],
                description=f"From meeting action item: {action.description}",
                assignee=action.assignee,
                priority=action.priority.capitalize(),
                labels=["meeting-action"],
                acceptance_criteria=[f"Complete: {action.description}"],
            )
            tickets.append(ticket)
        return tickets

    def _generate_adrs(self, decisions: list[str], lines: list[str]) -> list[ADRDraft]:
        """Generate ADR drafts from architectural decisions."""
        adrs = []
        for decision in decisions:
            is_arch = any(p.search(decision) for p in ARCH_PATTERNS)
            if is_arch:
                adr = ADRDraft(
                    title=f"ADR: {decision[:60]}",
                    status="Proposed",
                    context=f"Discussed in meeting. Participants: {', '.join(sorted(self.participants))}",
                    decision=decision,
                    participants=sorted(self.participants),
                )
                adrs.append(adr)
        return adrs

    def _generate_summary(self, topics: list[str], decisions: list[str],
                          actions: list[ActionItem]) -> str:
        """Generate meeting summary."""
        parts = []
        if topics:
            parts.append(f"Topics: {', '.join(topics)}")
        if decisions:
            parts.append(f"Decisions ({len(decisions)}): {'; '.join(decisions[:3])}")
        if actions:
            parts.append(f"Action items: {len(actions)}")
        return ". ".join(parts) if parts else "No structured content extracted."


def format_report(report: MeetingReport) -> str:
    """Format meeting report as text."""
    lines = [f"# Meeting Summary\n\n{report.summary}\n"]
    if report.participants:
        lines.append(f"## Participants\n{', '.join(report.participants)}\n")
    if report.action_items:
        lines.append("## Action Items")
        for ai in report.action_items:
            lines.append(f"- [{ai.priority}] {ai.description} (assignee: {ai.assignee or 'TBD'})")
    if report.decisions:
        lines.append("\n## Decisions")
        for d in report.decisions:
            lines.append(f"- {d}")
    if report.conflicts:
        lines.append("\n## Conflicts / Disagreements")
        for c in report.conflicts:
            lines.append(f"- {c.topic}: {'resolved' if c.resolved else 'unresolved'}")
    return "\n".join(lines)
