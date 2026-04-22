"""Tests for plan_manager.py — enhanced plan mode management."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.agent_system import plan_manager
from code_agents.agent_system.plan_manager import (
    # Legacy file-based functions
    create_plan_file,
    load_plan,
    update_step,
    list_plans,
    format_plan_for_prompt,
    # Enhanced lifecycle classes
    PlanStatus,
    ApprovalMode,
    PlanStep,
    ExecutionPlan,
    PlanManager,
    get_plan_manager,
)


@pytest.fixture(autouse=True)
def temp_plans_dir(tmp_path):
    """Redirect PLANS_DIR to a temp directory for all tests."""
    with patch.object(plan_manager, "PLANS_DIR", tmp_path / "plans"):
        yield tmp_path / "plans"


@pytest.fixture
def pm():
    """Fresh PlanManager for each test."""
    return PlanManager()


# ---------------------------------------------------------------------------
# PlanStatus and ApprovalMode enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_plan_status_values(self):
        assert PlanStatus.DRAFT.value == "draft"
        assert PlanStatus.PROPOSED.value == "proposed"
        assert PlanStatus.APPROVED.value == "approved"
        assert PlanStatus.REJECTED.value == "rejected"
        assert PlanStatus.EXECUTING.value == "executing"
        assert PlanStatus.COMPLETED.value == "completed"

    def test_approval_mode_values(self):
        assert ApprovalMode.AUTO_ACCEPT.value == "auto_accept"
        assert ApprovalMode.MANUAL_APPROVE.value == "manual_approve"
        assert ApprovalMode.FEEDBACK.value == "feedback"


# ---------------------------------------------------------------------------
# PlanStep dataclass
# ---------------------------------------------------------------------------

class TestPlanStep:
    def test_defaults(self):
        step = PlanStep(description="Do something")
        assert step.description == "Do something"
        assert step.file_path == ""
        assert step.action == ""
        assert step.status == "pending"

    def test_with_all_fields(self):
        step = PlanStep(description="Edit file", file_path="/a/b.py", action="modify", status="completed")
        assert step.file_path == "/a/b.py"
        assert step.action == "modify"
        assert step.status == "completed"


# ---------------------------------------------------------------------------
# ExecutionPlan dataclass
# ---------------------------------------------------------------------------

class TestExecutionPlan:
    def test_defaults(self):
        plan = ExecutionPlan(title="My Plan")
        assert plan.title == "My Plan"
        assert plan.steps == []
        assert plan.status == PlanStatus.DRAFT
        assert plan.approval_mode is None
        assert plan.feedback == ""
        assert plan.summary == ""
        assert plan.created_at  # non-empty

    def test_with_steps(self):
        plan = ExecutionPlan(
            title="Test",
            steps=[PlanStep("step 1"), PlanStep("step 2")],
            summary="A test plan",
        )
        assert len(plan.steps) == 2
        assert plan.summary == "A test plan"


# ---------------------------------------------------------------------------
# PlanManager — create_plan
# ---------------------------------------------------------------------------

class TestPlanManagerCreate:
    def test_create_basic(self, pm):
        plan = pm.create_plan("My Plan")
        assert plan.title == "My Plan"
        assert plan.status == PlanStatus.DRAFT
        assert pm.active_plan is plan

    def test_create_with_summary(self, pm):
        plan = pm.create_plan("Plan", summary="A summary")
        assert plan.summary == "A summary"

    def test_create_replaces_draft(self, pm):
        pm.create_plan("First")
        pm.create_plan("Second")
        assert pm.active_plan.title == "Second"

    def test_create_fails_during_execution(self, pm):
        plan = pm.create_plan("Running")
        pm.add_step("step 1")
        pm.propose()
        pm.approve()
        pm.start_execution()
        with pytest.raises(ValueError, match="Cannot create plan while another is executing"):
            pm.create_plan("New")


# ---------------------------------------------------------------------------
# PlanManager — add_step
# ---------------------------------------------------------------------------

class TestPlanManagerAddStep:
    def test_add_step(self, pm):
        pm.create_plan("Plan")
        step = pm.add_step("Do something", file_path="/a.py", action="modify")
        assert step.description == "Do something"
        assert len(pm.active_plan.steps) == 1

    def test_add_multiple_steps(self, pm):
        pm.create_plan("Plan")
        pm.add_step("Step 1")
        pm.add_step("Step 2")
        pm.add_step("Step 3")
        assert len(pm.active_plan.steps) == 3

    def test_add_step_no_plan(self, pm):
        with pytest.raises(ValueError, match="No active plan"):
            pm.add_step("step")


# ---------------------------------------------------------------------------
# PlanManager — propose
# ---------------------------------------------------------------------------

class TestPlanManagerPropose:
    def test_propose(self, pm):
        pm.create_plan("Plan")
        pm.add_step("step 1")
        result = pm.propose()
        assert result.status == PlanStatus.PROPOSED

    def test_propose_no_plan(self, pm):
        with pytest.raises(ValueError, match="No active plan"):
            pm.propose()


# ---------------------------------------------------------------------------
# PlanManager — approve
# ---------------------------------------------------------------------------

class TestPlanManagerApprove:
    def test_approve_auto(self, pm):
        pm.create_plan("Plan")
        pm.add_step("step 1")
        pm.propose()
        result = pm.approve(ApprovalMode.AUTO_ACCEPT)
        assert result.status == PlanStatus.APPROVED
        assert result.approval_mode == ApprovalMode.AUTO_ACCEPT

    def test_approve_manual(self, pm):
        pm.create_plan("Plan")
        pm.propose()
        result = pm.approve(ApprovalMode.MANUAL_APPROVE)
        assert result.approval_mode == ApprovalMode.MANUAL_APPROVE

    def test_approve_default_is_auto(self, pm):
        pm.create_plan("Plan")
        pm.propose()
        result = pm.approve()
        assert result.approval_mode == ApprovalMode.AUTO_ACCEPT

    def test_approve_no_plan(self, pm):
        with pytest.raises(ValueError, match="No active plan"):
            pm.approve()


# ---------------------------------------------------------------------------
# PlanManager — reject
# ---------------------------------------------------------------------------

class TestPlanManagerReject:
    def test_reject(self, pm):
        pm.create_plan("Plan")
        pm.propose()
        result = pm.reject("Not good enough")
        assert result.status == PlanStatus.REJECTED
        assert result.feedback == "Not good enough"
        assert pm.active_plan is None
        assert len(pm._history) == 1

    def test_reject_no_feedback(self, pm):
        pm.create_plan("Plan")
        result = pm.reject()
        assert result.status == PlanStatus.REJECTED
        assert result.feedback == ""

    def test_reject_no_plan(self, pm):
        with pytest.raises(ValueError, match="No active plan"):
            pm.reject()


# ---------------------------------------------------------------------------
# PlanManager — start_execution / complete
# ---------------------------------------------------------------------------

class TestPlanManagerExecution:
    def test_start_execution(self, pm):
        pm.create_plan("Plan")
        pm.add_step("step 1")
        pm.propose()
        pm.approve()
        result = pm.start_execution()
        assert result.status == PlanStatus.EXECUTING

    def test_start_execution_not_approved(self, pm):
        pm.create_plan("Plan")
        pm.propose()
        with pytest.raises(ValueError, match="No approved plan"):
            pm.start_execution()

    def test_complete(self, pm):
        pm.create_plan("Plan")
        pm.add_step("step 1")
        pm.propose()
        pm.approve()
        pm.start_execution()
        result = pm.complete()
        assert result.status == PlanStatus.COMPLETED
        assert pm.active_plan is None
        assert len(pm._history) == 1

    def test_complete_no_plan(self, pm):
        with pytest.raises(ValueError, match="No active plan"):
            pm.complete()


# ---------------------------------------------------------------------------
# PlanManager — edit_plan
# ---------------------------------------------------------------------------

class TestPlanManagerEdit:
    def test_edit_returns_to_draft(self, pm):
        pm.create_plan("Plan")
        pm.add_step("step 1")
        pm.propose()
        result = pm.edit_plan("Change step 1 approach")
        assert result.status == PlanStatus.DRAFT
        assert result.feedback == "Change step 1 approach"

    def test_edit_no_plan(self, pm):
        with pytest.raises(ValueError, match="No active plan"):
            pm.edit_plan("feedback")


# ---------------------------------------------------------------------------
# PlanManager — is_plan_mode
# ---------------------------------------------------------------------------

class TestPlanManagerIsPlanMode:
    def test_no_plan(self, pm):
        assert pm.is_plan_mode is False

    def test_draft(self, pm):
        pm.create_plan("Plan")
        assert pm.is_plan_mode is True

    def test_proposed(self, pm):
        pm.create_plan("Plan")
        pm.propose()
        assert pm.is_plan_mode is True

    def test_approved(self, pm):
        pm.create_plan("Plan")
        pm.propose()
        pm.approve()
        assert pm.is_plan_mode is False

    def test_executing(self, pm):
        pm.create_plan("Plan")
        pm.propose()
        pm.approve()
        pm.start_execution()
        assert pm.is_plan_mode is False


# ---------------------------------------------------------------------------
# PlanManager — get_status
# ---------------------------------------------------------------------------

class TestPlanManagerGetStatus:
    def test_no_plan(self, pm):
        status = pm.get_status()
        assert status == {"active": False}

    def test_with_plan(self, pm):
        pm.create_plan("Plan")
        pm.add_step("step 1")
        pm.add_step("step 2")
        status = pm.get_status()
        assert status["active"] is True
        assert status["title"] == "Plan"
        assert status["status"] == "draft"
        assert status["steps"] == 2
        assert status["completed_steps"] == 0
        assert status["approval_mode"] is None

    def test_with_approval_mode(self, pm):
        pm.create_plan("Plan")
        pm.propose()
        pm.approve(ApprovalMode.MANUAL_APPROVE)
        status = pm.get_status()
        assert status["approval_mode"] == "manual_approve"


# ---------------------------------------------------------------------------
# PlanManager — format_plan
# ---------------------------------------------------------------------------

class TestPlanManagerFormat:
    def test_no_plan(self, pm):
        assert "No active plan" in pm.format_plan()

    def test_with_steps(self, pm):
        pm.create_plan("My Plan", summary="A test plan")
        pm.add_step("First step")
        pm.add_step("Second step", file_path="/a.py")
        text = pm.format_plan()
        assert "My Plan" in text
        assert "draft" in text
        assert "First step" in text
        assert "Second step" in text
        assert "/a.py" in text
        assert "A test plan" in text

    def test_completed_step_icon(self, pm):
        pm.create_plan("Plan")
        pm.add_step("Done step")
        pm.active_plan.steps[0].status = "completed"
        text = pm.format_plan()
        assert "\u25cf" in text  # completed icon


# ---------------------------------------------------------------------------
# PlanManager — build_plan_approval_questionnaire
# ---------------------------------------------------------------------------

class TestPlanManagerQuestionnaire:
    def test_no_plan(self, pm):
        assert pm.build_plan_approval_questionnaire() == ""

    def test_with_plan(self, pm):
        pm.create_plan("Plan")
        pm.add_step("step 1")
        pm.propose()
        text = pm.build_plan_approval_questionnaire()
        assert "auto-accept" in text
        assert "manually approve" in text
        assert "shift+tab" in text


# ---------------------------------------------------------------------------
# Singleton — get_plan_manager
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_returns_same_instance(self):
        # Reset singleton
        plan_manager._manager = None
        m1 = get_plan_manager()
        m2 = get_plan_manager()
        assert m1 is m2
        # Clean up
        plan_manager._manager = None


# ---------------------------------------------------------------------------
# Legacy file-based functions (backward compat)
# ---------------------------------------------------------------------------

class TestCreatePlanFile:
    def test_create_basic(self, temp_plans_dir):
        result = create_plan_file("My Plan", ["step 1", "step 2"])
        assert result["title"] == "My Plan"
        assert result["steps"] == 2
        assert "id" in result
        assert "path" in result
        assert Path(result["path"]).is_file()

    def test_create_with_session_id(self, temp_plans_dir):
        result = create_plan_file("Plan", ["a"], session_id="abcdef1234567890")
        assert result["id"] == "abcdef12"

    def test_create_without_session_id(self, temp_plans_dir):
        result = create_plan_file("Plan", ["a"])
        assert len(result["id"]) == 8

    def test_plan_file_content(self, temp_plans_dir):
        result = create_plan_file("Test Title", ["first", "second", "third"])
        content = Path(result["path"]).read_text(encoding="utf-8")
        assert "# Test Title" in content
        assert "- [ ] Step 1: first" in content
        assert "- [ ] Step 2: second" in content
        assert "- [ ] Step 3: third" in content
        assert "Created:" in content


class TestLoadPlan:
    def test_load_existing(self, temp_plans_dir):
        created = create_plan_file("Load Me", ["a", "b"])
        loaded = load_plan(created["id"])
        assert loaded is not None
        assert loaded["title"] == "Load Me"
        assert len(loaded["steps"]) == 2
        assert loaded["current_step"] == 0
        assert loaded["total"] == 2

    def test_load_nonexistent(self, temp_plans_dir):
        temp_plans_dir.mkdir(parents=True, exist_ok=True)
        assert load_plan("nonexistent") is None

    def test_load_prefix_match(self, temp_plans_dir):
        created = create_plan_file("Prefix", ["x"], session_id="xyzabc1234567890")
        loaded = load_plan("xyzabc12")
        assert loaded is not None
        assert loaded["title"] == "Prefix"

    def test_load_steps_done_state(self, temp_plans_dir):
        created = create_plan_file("Done Test", ["a", "b", "c"])
        update_step(created["id"], 0, done=True)
        loaded = load_plan(created["id"])
        assert loaded["steps"][0]["done"] is True
        assert loaded["steps"][1]["done"] is False
        assert loaded["current_step"] == 1


class TestUpdateStep:
    def test_mark_done(self, temp_plans_dir):
        created = create_plan_file("Update", ["a", "b"])
        assert update_step(created["id"], 0, done=True) is True
        loaded = load_plan(created["id"])
        assert loaded["steps"][0]["done"] is True

    def test_mark_undone(self, temp_plans_dir):
        created = create_plan_file("Undo", ["a", "b"])
        update_step(created["id"], 0, done=True)
        update_step(created["id"], 0, done=False)
        loaded = load_plan(created["id"])
        assert loaded["steps"][0]["done"] is False

    def test_invalid_plan_id(self, temp_plans_dir):
        temp_plans_dir.mkdir(parents=True, exist_ok=True)
        assert update_step("nonexistent", 0) is False

    def test_invalid_step_index(self, temp_plans_dir):
        created = create_plan_file("Bounds", ["a"])
        assert update_step(created["id"], 5) is False


class TestListPlans:
    def test_empty_dir(self, temp_plans_dir):
        assert list_plans() == []

    def test_lists_plans(self, temp_plans_dir):
        create_plan_file("Plan A", ["x"])
        create_plan_file("Plan B", ["y", "z"])
        plans = list_plans()
        assert len(plans) == 2
        for p in plans:
            assert "id" in p
            assert "title" in p
            assert "progress" in p

    def test_progress_format(self, temp_plans_dir):
        created = create_plan_file("Progress", ["a", "b", "c"])
        update_step(created["id"], 0, done=True)
        plans = list_plans()
        plan = [p for p in plans if p["id"] == created["id"]][0]
        assert plan["progress"] == "1/3"


class TestFormatPlan:
    def test_empty_plan(self):
        assert format_plan_for_prompt({}) == ""
        assert format_plan_for_prompt(None) == ""

    def test_format_active_plan(self, temp_plans_dir):
        created = create_plan_file("Format Test", ["do X", "do Y"])
        loaded = load_plan(created["id"])
        text = format_plan_for_prompt(loaded)
        assert "Format Test" in text
        assert "Step 1/2" in text
        assert "do X" in text or "Step 1:" in text

    def test_format_with_done_steps(self, temp_plans_dir):
        created = create_plan_file("Done", ["a", "b"])
        update_step(created["id"], 0, done=True)
        loaded = load_plan(created["id"])
        text = format_plan_for_prompt(loaded)
        assert "\u2713" in text  # checkmark for done step
