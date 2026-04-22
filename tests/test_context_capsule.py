"""Tests for context_capsule.py — work state capture and restore."""

import pytest

from code_agents.agent_system.context_capsule import (
    ContextCapsuleManager,
    CapsuleReport,
    ContextCapsule,
    ResumeBriefing,
    format_briefing,
)


@pytest.fixture
def manager(tmp_path):
    return ContextCapsuleManager(str(tmp_path))


class TestCapture:
    def test_captures_state(self, manager):
        report = manager.capture(
            task_description="Implement user auth",
            current_step="Writing login handler",
            completed=["Setup routes", "Create models"],
            remaining=["Write tests", "Add validation"],
            modified_files=[{"path": "auth.py", "modified": True}],
            branch="feature/auth",
        )
        assert isinstance(report, CapsuleReport)
        assert report.success is True
        assert report.capsule is not None
        assert report.capsule.task.description == "Implement user auth"

    def test_stores_capsule(self, manager):
        manager.capture(task_description="Task 1")
        assert len(manager.capsules) == 1

    def test_multiple_capsules(self, manager):
        manager.capture(task_description="Task 1")
        manager.capture(task_description="Task 2")
        assert len(manager.capsules) == 2


class TestRestore:
    def test_restores_latest(self, manager):
        manager.capture(task_description="My task", current_step="Step 3")
        report = manager.restore()
        assert report.success is True
        assert report.briefing is not None
        assert "My task" in report.briefing.summary

    def test_restores_by_id(self, manager):
        cap_report = manager.capture(task_description="Specific task")
        capsule_id = cap_report.capsule.capsule_id
        report = manager.restore(capsule_id=capsule_id)
        assert report.success is True

    def test_restore_empty(self, manager):
        report = manager.restore()
        assert report.success is False

    def test_restore_from_data(self, manager):
        data = {
            "id": "test_cap",
            "task": {"description": "From data", "current_step": "Step 1"},
            "files": [{"path": "a.py", "modified": True}],
        }
        report = manager.restore(capsule_data=data)
        assert report.success is True


class TestBriefing:
    def test_briefing_has_next_steps(self, manager):
        manager.capture(
            task_description="Build API",
            remaining=["Add auth", "Write docs"],
        )
        report = manager.restore()
        assert len(report.briefing.next_steps) == 2

    def test_format_briefing(self, manager):
        manager.capture(task_description="Test task", remaining=["Step 1"])
        report = manager.restore()
        text = format_briefing(report.briefing)
        assert "Resume Briefing" in text

    def test_list_capsules(self, manager):
        manager.capture(task_description="Task 1")
        manager.capture(task_description="Task 2")
        listing = manager.list_capsules()
        assert len(listing) == 2
