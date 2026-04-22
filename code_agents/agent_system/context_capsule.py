"""Context Capsule — capture complete work state and restore with briefing."""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.context_capsule")


@dataclass
class FileState:
    """State of a file at capture time."""
    file_path: str = ""
    modified: bool = False
    staged: bool = False
    content_hash: str = ""
    changes_summary: str = ""


@dataclass
class TaskState:
    """State of the current task."""
    description: str = ""
    status: str = "in_progress"  # in_progress, blocked, paused
    current_step: str = ""
    completed_steps: list[str] = field(default_factory=list)
    remaining_steps: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


@dataclass
class ContextCapsule:
    """Complete captured work context."""
    capsule_id: str = ""
    timestamp: float = 0.0
    branch_name: str = ""
    task: TaskState = field(default_factory=TaskState)
    files: list[FileState] = field(default_factory=list)
    open_files: list[str] = field(default_factory=list)
    conversation_summary: str = ""
    scratch_notes: list[str] = field(default_factory=list)
    environment: dict = field(default_factory=dict)
    session_memory: dict = field(default_factory=dict)


@dataclass
class ResumeBriefing:
    """A briefing document for resuming work."""
    capsule_id: str = ""
    summary: str = ""
    where_you_left_off: str = ""
    next_steps: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    context_refresh: str = ""
    time_since_capture: str = ""


@dataclass
class CapsuleReport:
    """Report from capsule operations."""
    capsule: Optional[ContextCapsule] = None
    briefing: Optional[ResumeBriefing] = None
    operation: str = ""  # capture, restore
    success: bool = True
    warnings: list[str] = field(default_factory=list)


class ContextCapsuleManager:
    """Manages capturing and restoring work context."""

    _counter = 0

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.capsules: dict[str, ContextCapsule] = {}

    def capture(self, task_description: str = "",
                current_step: str = "",
                completed: Optional[list[str]] = None,
                remaining: Optional[list[str]] = None,
                modified_files: Optional[list[dict]] = None,
                conversation: str = "",
                notes: Optional[list[str]] = None,
                branch: str = "",
                session_memory: Optional[dict] = None) -> CapsuleReport:
        """Capture current work context into a capsule."""
        logger.info("Capturing context capsule for: %s", task_description[:60])

        ContextCapsuleManager._counter += 1
        capsule_id = f"capsule_{int(time.time())}_{ContextCapsuleManager._counter}"
        files = [self._parse_file_state(f) for f in (modified_files or [])]

        task = TaskState(
            description=task_description,
            status="paused",
            current_step=current_step,
            completed_steps=completed or [],
            remaining_steps=remaining or [],
        )

        capsule = ContextCapsule(
            capsule_id=capsule_id,
            timestamp=time.time(),
            branch_name=branch,
            task=task,
            files=files,
            conversation_summary=conversation,
            scratch_notes=notes or [],
            session_memory=session_memory or {},
        )

        self.capsules[capsule_id] = capsule
        logger.info("Captured capsule %s: %d files, %d steps remaining",
                     capsule_id, len(files), len(task.remaining_steps))

        return CapsuleReport(
            capsule=capsule,
            operation="capture",
            success=True,
        )

    def restore(self, capsule_id: Optional[str] = None,
                capsule_data: Optional[dict] = None) -> CapsuleReport:
        """Restore a capsule and generate a resume briefing."""
        logger.info("Restoring capsule: %s", capsule_id or "from data")

        capsule = None
        if capsule_id and capsule_id in self.capsules:
            capsule = self.capsules[capsule_id]
        elif capsule_data:
            capsule = self._parse_capsule(capsule_data)
        elif self.capsules:
            # Restore most recent
            capsule = max(self.capsules.values(), key=lambda c: c.timestamp)

        if not capsule:
            return CapsuleReport(
                operation="restore",
                success=False,
                warnings=["No capsule found to restore"],
            )

        briefing = self._generate_briefing(capsule)

        return CapsuleReport(
            capsule=capsule,
            briefing=briefing,
            operation="restore",
            success=True,
        )

    def _parse_file_state(self, raw: dict) -> FileState:
        """Parse file state from dict."""
        return FileState(
            file_path=raw.get("path", raw.get("file_path", "")),
            modified=raw.get("modified", True),
            staged=raw.get("staged", False),
            content_hash=raw.get("hash", ""),
            changes_summary=raw.get("summary", raw.get("changes", "")),
        )

    def _parse_capsule(self, data: dict) -> ContextCapsule:
        """Parse capsule from dict."""
        task_data = data.get("task", {})
        task = TaskState(
            description=task_data.get("description", ""),
            current_step=task_data.get("current_step", ""),
            completed_steps=task_data.get("completed", []),
            remaining_steps=task_data.get("remaining", []),
        )
        files = [self._parse_file_state(f) for f in data.get("files", [])]
        return ContextCapsule(
            capsule_id=data.get("id", f"imported_{int(time.time())}"),
            timestamp=data.get("timestamp", time.time()),
            branch_name=data.get("branch", ""),
            task=task,
            files=files,
            conversation_summary=data.get("conversation", ""),
            scratch_notes=data.get("notes", []),
            session_memory=data.get("memory", {}),
        )

    def _generate_briefing(self, capsule: ContextCapsule) -> ResumeBriefing:
        """Generate a resume briefing from a capsule."""
        elapsed = time.time() - capsule.timestamp
        elapsed_str = self._format_elapsed(elapsed)

        # Build summary
        summary_parts = [f"Task: {capsule.task.description}"]
        if capsule.task.completed_steps:
            summary_parts.append(f"Completed: {len(capsule.task.completed_steps)} steps")
        if capsule.task.remaining_steps:
            summary_parts.append(f"Remaining: {len(capsule.task.remaining_steps)} steps")

        # Where you left off
        where = capsule.task.current_step or "No specific step recorded"
        if capsule.branch_name:
            where = f"Branch: {capsule.branch_name}. {where}"

        # Modified files
        mod_files = [f.file_path for f in capsule.files if f.modified]

        # Context refresh
        refresh_parts = []
        if capsule.conversation_summary:
            refresh_parts.append(f"Last conversation: {capsule.conversation_summary[:200]}")
        if capsule.scratch_notes:
            refresh_parts.append(f"Notes: {'; '.join(capsule.scratch_notes[:5])}")

        return ResumeBriefing(
            capsule_id=capsule.capsule_id,
            summary=". ".join(summary_parts),
            where_you_left_off=where,
            next_steps=capsule.task.remaining_steps[:5],
            modified_files=mod_files,
            blockers=capsule.task.blockers,
            context_refresh="\n".join(refresh_parts),
            time_since_capture=elapsed_str,
        )

    def _format_elapsed(self, seconds: float) -> str:
        """Format elapsed seconds as human-readable."""
        if seconds < 60:
            return f"{int(seconds)}s ago"
        elif seconds < 3600:
            return f"{int(seconds / 60)}m ago"
        elif seconds < 86400:
            return f"{int(seconds / 3600)}h ago"
        else:
            return f"{int(seconds / 86400)}d ago"

    def list_capsules(self) -> list[dict]:
        """List all stored capsules."""
        return [
            {
                "id": c.capsule_id,
                "task": c.task.description[:60],
                "timestamp": c.timestamp,
                "files": len(c.files),
                "branch": c.branch_name,
            }
            for c in sorted(self.capsules.values(), key=lambda c: -c.timestamp)
        ]


def format_briefing(briefing: ResumeBriefing) -> str:
    """Format resume briefing as text."""
    lines = [
        "# Resume Briefing",
        f"Time away: {briefing.time_since_capture}",
        f"\n## Summary\n{briefing.summary}",
        f"\n## Where You Left Off\n{briefing.where_you_left_off}",
    ]
    if briefing.next_steps:
        lines.append("\n## Next Steps")
        for i, step in enumerate(briefing.next_steps, 1):
            lines.append(f"  {i}. {step}")
    if briefing.modified_files:
        lines.append(f"\n## Modified Files ({len(briefing.modified_files)})")
        for f in briefing.modified_files:
            lines.append(f"  - {f}")
    if briefing.context_refresh:
        lines.append(f"\n## Context\n{briefing.context_refresh}")
    return "\n".join(lines)
