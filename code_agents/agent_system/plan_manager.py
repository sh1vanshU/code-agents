"""Plan mode — create, approve, edit, reject execution plans before running.

Supports a structured workflow:
1. Agent analyzes the request and proposes a plan
2. User reviews the plan via questionnaire
3. User approves (auto/manual), edits, or rejects
4. On approval, agent executes the plan

Also supports legacy file-based plans (saved as markdown at ~/.code-agents/plans/).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.plan_manager")

PLANS_DIR = Path.home() / ".code-agents" / "plans"


# ---------------------------------------------------------------------------
# Enhanced plan lifecycle (in-memory, structured)
# ---------------------------------------------------------------------------


class PlanStatus(Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"


class ApprovalMode(Enum):
    AUTO_ACCEPT = "auto_accept"        # Execute without asking per-edit
    MANUAL_APPROVE = "manual_approve"  # Ask before each edit
    FEEDBACK = "feedback"              # User wants to give feedback first


@dataclass
class PlanStep:
    description: str
    file_path: str = ""
    action: str = ""  # "create", "modify", "delete", "run"
    status: str = "pending"  # pending, in_progress, completed, skipped


@dataclass
class ExecutionPlan:
    title: str
    steps: list[PlanStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    approval_mode: Optional[ApprovalMode] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    feedback: str = ""
    summary: str = ""


class PlanManager:
    """Manages the lifecycle of execution plans."""

    def __init__(self) -> None:
        self._active_plan: Optional[ExecutionPlan] = None
        self._history: list[ExecutionPlan] = []

    @property
    def active_plan(self) -> Optional[ExecutionPlan]:
        return self._active_plan

    @property
    def is_plan_mode(self) -> bool:
        return self._active_plan is not None and self._active_plan.status in (
            PlanStatus.DRAFT, PlanStatus.PROPOSED,
        )

    def create_plan(self, title: str, summary: str = "") -> ExecutionPlan:
        """Create a new plan. Replaces any existing draft."""
        if self._active_plan and self._active_plan.status == PlanStatus.EXECUTING:
            raise ValueError("Cannot create plan while another is executing")
        plan = ExecutionPlan(title=title, summary=summary)
        self._active_plan = plan
        logger.info("Plan created: %s", title)
        return plan

    def add_step(self, description: str, file_path: str = "", action: str = "") -> PlanStep:
        """Add a step to the active plan."""
        if not self._active_plan:
            raise ValueError("No active plan")
        step = PlanStep(description=description, file_path=file_path, action=action)
        self._active_plan.steps.append(step)
        return step

    def propose(self) -> ExecutionPlan:
        """Mark plan as proposed (ready for user review)."""
        if not self._active_plan:
            raise ValueError("No active plan")
        self._active_plan.status = PlanStatus.PROPOSED
        logger.info("Plan proposed: %s (%d steps)", self._active_plan.title, len(self._active_plan.steps))
        return self._active_plan

    def approve(self, mode: ApprovalMode = ApprovalMode.AUTO_ACCEPT) -> ExecutionPlan:
        """Approve the plan with specified execution mode."""
        if not self._active_plan:
            raise ValueError("No active plan")
        self._active_plan.status = PlanStatus.APPROVED
        self._active_plan.approval_mode = mode
        logger.info("Plan approved: %s (mode=%s)", self._active_plan.title, mode.value)
        return self._active_plan

    def reject(self, feedback: str = "") -> ExecutionPlan:
        """Reject the plan with optional feedback."""
        if not self._active_plan:
            raise ValueError("No active plan")
        self._active_plan.status = PlanStatus.REJECTED
        self._active_plan.feedback = feedback
        logger.info("Plan rejected: %s", self._active_plan.title)
        self._history.append(self._active_plan)
        rejected = self._active_plan
        self._active_plan = None
        return rejected

    def start_execution(self) -> ExecutionPlan:
        """Begin executing an approved plan."""
        if not self._active_plan or self._active_plan.status != PlanStatus.APPROVED:
            raise ValueError("No approved plan to execute")
        self._active_plan.status = PlanStatus.EXECUTING
        return self._active_plan

    def complete(self) -> ExecutionPlan:
        """Mark plan as completed."""
        if not self._active_plan:
            raise ValueError("No active plan")
        self._active_plan.status = PlanStatus.COMPLETED
        self._history.append(self._active_plan)
        completed = self._active_plan
        self._active_plan = None
        logger.info("Plan completed: %s", completed.title)
        return completed

    def edit_plan(self, feedback: str) -> ExecutionPlan:
        """Send feedback to modify the plan (returns to DRAFT)."""
        if not self._active_plan:
            raise ValueError("No active plan")
        self._active_plan.feedback = feedback
        self._active_plan.status = PlanStatus.DRAFT
        return self._active_plan

    def get_status(self) -> dict:
        """Get current plan status summary."""
        if not self._active_plan:
            return {"active": False}
        p = self._active_plan
        return {
            "active": True,
            "title": p.title,
            "status": p.status.value,
            "steps": len(p.steps),
            "completed_steps": sum(1 for s in p.steps if s.status == "completed"),
            "approval_mode": p.approval_mode.value if p.approval_mode else None,
        }

    def format_plan(self) -> str:
        """Format the active plan for display."""
        if not self._active_plan:
            return "  No active plan."
        p = self._active_plan
        lines = [f"  Plan: {p.title}", f"  Status: {p.status.value}", ""]
        if p.summary:
            lines.append(f"  {p.summary}")
            lines.append("")
        for i, step in enumerate(p.steps, 1):
            icon = {"pending": "\u25cb", "in_progress": "\u25c9", "completed": "\u25cf", "skipped": "\u25cc"}.get(step.status, "\u25cb")
            lines.append(f"  {icon} {i}. {step.description}")
            if step.file_path:
                lines.append(f"       {step.file_path}")
        return "\n".join(lines)

    def build_plan_approval_questionnaire(self) -> str:
        """Build the plan approval questionnaire text (like Claude Code's UX)."""
        if not self._active_plan:
            return ""
        lines = [
            "",
            "  Agent has proposed a plan. How would you like to proceed?",
            "",
            "  \u276f 1. Yes, auto-accept edits",
            "    2. Yes, manually approve edits",
            "    3. Tell the agent what to change",
            "       shift+tab to approve with feedback",
            "",
        ]
        return "\n".join(lines)


# Singleton
_manager: Optional[PlanManager] = None


def get_plan_manager() -> PlanManager:
    """Get or create the singleton PlanManager instance."""
    global _manager
    if _manager is None:
        _manager = PlanManager()
    return _manager


# ---------------------------------------------------------------------------
# Legacy file-based plan functions (backward compatible)
# ---------------------------------------------------------------------------


def create_plan_file(title: str, steps: list[str], session_id: str = "") -> dict:
    """Create a new plan and save to disk (legacy file-based)."""
    plan_id = session_id[:8] if session_id else uuid.uuid4().hex[:8]
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    content = f"# {title}\n\nCreated: {datetime.now().isoformat()}\n\n## Steps\n\n"
    for i, step in enumerate(steps, 1):
        content += f"- [ ] Step {i}: {step}\n"
    path = PLANS_DIR / f"{plan_id}.md"
    path.write_text(content, encoding="utf-8")
    logger.info("Plan created: id=%s, title='%s', steps=%d", plan_id, title, len(steps))
    return {"id": plan_id, "title": title, "steps": len(steps), "path": str(path)}


# Keep old name as alias for backward compat
def create_plan_legacy(title: str, steps: list[str], session_id: str = "") -> dict:
    """Alias for create_plan_file (backward compat)."""
    return create_plan_file(title, steps, session_id)


def load_plan(plan_id: str) -> Optional[dict]:
    """Load a plan by ID (or prefix match)."""
    path = PLANS_DIR / f"{plan_id}.md"
    if not path.is_file():
        for f in PLANS_DIR.glob(f"{plan_id}*.md"):
            path = f
            break
        else:
            logger.warning("Plan not found: %s", plan_id)
            return None
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else "Untitled"
    steps = []
    for line in lines:
        if line.startswith("- [ ] ") or line.startswith("- [x] "):
            done = line.startswith("- [x] ")
            text = line[6:].strip()
            steps.append({"text": text, "done": done})
    current = next((i for i, s in enumerate(steps) if not s["done"]), len(steps))
    return {
        "id": path.stem, "title": title, "steps": steps,
        "current_step": current, "total": len(steps), "path": str(path),
    }


def update_step(plan_id: str, step_idx: int, done: bool = True) -> bool:
    """Mark a step as done or undone."""
    plan = load_plan(plan_id)
    if not plan or step_idx >= len(plan["steps"]):
        return False
    path = Path(plan["path"])
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    step_count = 0
    for i, line in enumerate(lines):
        if line.startswith("- [ ] ") or line.startswith("- [x] "):
            if step_count == step_idx:
                new_prefix = "- [x] " if done else "- [ ] "
                lines[i] = new_prefix + line[6:]
                break
            step_count += 1
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Plan %s: step %d marked %s", plan_id, step_idx, "done" if done else "undone")
    return True


def list_plans() -> list[dict]:
    """List all saved plans (newest first)."""
    if not PLANS_DIR.is_dir():
        return []
    plans = []
    for f in sorted(PLANS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        plan = load_plan(f.stem)
        if plan:
            done_count = sum(1 for s in plan["steps"] if s["done"])
            plans.append({
                "id": plan["id"], "title": plan["title"],
                "progress": f"{done_count}/{plan['total']}", "path": str(f),
            })
    return plans


def format_plan_for_prompt(plan: dict) -> str:
    """Format plan for injection into agent system prompt."""
    if not plan:
        return ""
    lines = [
        f"Active Plan: {plan['title']}",
        f"Progress: Step {plan['current_step'] + 1}/{plan['total']}",
        "",
    ]
    for i, step in enumerate(plan["steps"]):
        marker = "\u2713" if step["done"] else "\u2192" if i == plan["current_step"] else " "
        lines.append(f"  [{marker}] {step['text']}")
    return "\n".join(lines)
