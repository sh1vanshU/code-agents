"""Tests for code_agents.background_agent — Background Agent Manager."""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from code_agents.devops.background_agent import (
    AgentStatus,
    BackgroundAgentManager,
    BackgroundTask,
    _format_elapsed,
    render_tasks_panel,
)


class TestAgentStatus(unittest.TestCase):
    """Test the AgentStatus enum."""

    def test_values(self):
        self.assertEqual(AgentStatus.PENDING, "pending")
        self.assertEqual(AgentStatus.RUNNING, "running")
        self.assertEqual(AgentStatus.COMPLETED, "completed")
        self.assertEqual(AgentStatus.FAILED, "failed")
        self.assertEqual(AgentStatus.STOPPED, "stopped")

    def test_string_enum(self):
        self.assertIsInstance(AgentStatus.RUNNING, str)
        self.assertEqual(str(AgentStatus.RUNNING), "AgentStatus.RUNNING")
        self.assertEqual(AgentStatus.RUNNING.value, "running")


class TestBackgroundTask(unittest.TestCase):
    """Test BackgroundTask dataclass."""

    def test_construction_defaults(self):
        task = BackgroundTask(
            task_id="bg-0001",
            name="Test Task",
            agent="code-writer",
            prompt="do something",
        )
        self.assertEqual(task.task_id, "bg-0001")
        self.assertEqual(task.name, "Test Task")
        self.assertEqual(task.agent, "code-writer")
        self.assertEqual(task.prompt, "do something")
        self.assertEqual(task.status, AgentStatus.PENDING)
        self.assertGreater(task.created_at, 0)
        self.assertEqual(task.started_at, 0.0)
        self.assertEqual(task.completed_at, 0.0)
        self.assertEqual(task.result, "")
        self.assertEqual(task.error, "")
        self.assertIsNone(task.thread)

    def test_is_active(self):
        task = BackgroundTask(
            task_id="bg-0001", name="t", agent="a", prompt="p",
        )
        self.assertTrue(task.is_active)

        task.status = AgentStatus.RUNNING
        self.assertTrue(task.is_active)

        task.status = AgentStatus.COMPLETED
        self.assertFalse(task.is_active)

        task.status = AgentStatus.FAILED
        self.assertFalse(task.is_active)

        task.status = AgentStatus.STOPPED
        self.assertFalse(task.is_active)

    def test_is_terminal(self):
        task = BackgroundTask(
            task_id="bg-0001", name="t", agent="a", prompt="p",
        )
        self.assertFalse(task.is_terminal)

        for status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.STOPPED):
            task.status = status
            self.assertTrue(task.is_terminal, f"Expected terminal for {status}")

    def test_status_transitions(self):
        task = BackgroundTask(
            task_id="bg-0001", name="t", agent="a", prompt="p",
        )
        self.assertEqual(task.status, AgentStatus.PENDING)

        task.status = AgentStatus.RUNNING
        task.started_at = time.time()
        self.assertEqual(task.status, AgentStatus.RUNNING)

        task.status = AgentStatus.COMPLETED
        task.completed_at = time.time()
        task.result = "done"
        self.assertEqual(task.status, AgentStatus.COMPLETED)
        self.assertEqual(task.result, "done")

    def test_elapsed_pending(self):
        task = BackgroundTask(
            task_id="bg-0001", name="t", agent="a", prompt="p",
            created_at=time.time() - 5,
        )
        self.assertGreaterEqual(task.elapsed, 4.5)

    def test_elapsed_running(self):
        task = BackgroundTask(
            task_id="bg-0001", name="t", agent="a", prompt="p",
            status=AgentStatus.RUNNING,
            started_at=time.time() - 10,
        )
        self.assertGreaterEqual(task.elapsed, 9.5)

    def test_elapsed_completed(self):
        now = time.time()
        task = BackgroundTask(
            task_id="bg-0001", name="t", agent="a", prompt="p",
            status=AgentStatus.COMPLETED,
            started_at=now - 30,
            completed_at=now - 10,
        )
        self.assertAlmostEqual(task.elapsed, 20.0, delta=0.5)

    def test_elapsed_str(self):
        task = BackgroundTask(
            task_id="bg-0001", name="t", agent="a", prompt="p",
            status=AgentStatus.COMPLETED,
            started_at=100.0,
            completed_at=145.0,
        )
        self.assertEqual(task.elapsed_str, "45s")

    def test_status_icon(self):
        task = BackgroundTask(
            task_id="bg-0001", name="t", agent="a", prompt="p",
        )
        self.assertEqual(task.status_icon, "\u25cb")  # ○ pending

        task.status = AgentStatus.RUNNING
        self.assertEqual(task.status_icon, "\u27f3")  # ⟳

        task.status = AgentStatus.COMPLETED
        self.assertEqual(task.status_icon, "\u2713")  # ✓

        task.status = AgentStatus.FAILED
        self.assertEqual(task.status_icon, "\u2717")  # ✗

        task.status = AgentStatus.STOPPED
        self.assertEqual(task.status_icon, "\u25a0")  # ■


class TestFormatElapsed(unittest.TestCase):
    """Test the _format_elapsed helper."""

    def test_seconds(self):
        self.assertEqual(_format_elapsed(0), "0s")
        self.assertEqual(_format_elapsed(30), "30s")
        self.assertEqual(_format_elapsed(59.9), "60s")

    def test_minutes(self):
        self.assertEqual(_format_elapsed(60), "1m 00s")
        self.assertEqual(_format_elapsed(90), "1m 30s")
        self.assertEqual(_format_elapsed(3599), "59m 59s")

    def test_hours(self):
        self.assertEqual(_format_elapsed(3600), "1h 00m")
        self.assertEqual(_format_elapsed(7200), "2h 00m")

    def test_negative(self):
        self.assertEqual(_format_elapsed(-5), "0s")


class TestBackgroundAgentManager(unittest.TestCase):
    """Test the BackgroundAgentManager class."""

    def setUp(self):
        BackgroundAgentManager.reset_instance()
        self.mgr = BackgroundAgentManager()

    def test_singleton(self):
        BackgroundAgentManager.reset_instance()
        m1 = BackgroundAgentManager.get_instance()
        m2 = BackgroundAgentManager.get_instance()
        self.assertIs(m1, m2)

    def test_reset_instance(self):
        m1 = BackgroundAgentManager.get_instance()
        BackgroundAgentManager.reset_instance()
        m2 = BackgroundAgentManager.get_instance()
        self.assertIsNot(m1, m2)

    def test_start_task(self):
        event = threading.Event()

        def execute_fn(agent, prompt):
            event.wait(timeout=5)
            return "result"

        task = self.mgr.start_task("Test", "agent", "prompt", execute_fn)
        self.assertEqual(task.task_id, "bg-0001")
        self.assertEqual(task.name, "Test")
        self.assertEqual(task.agent, "agent")
        self.assertEqual(task.prompt, "prompt")

        # Wait briefly for thread to start
        time.sleep(0.1)
        self.assertEqual(task.status, AgentStatus.RUNNING)

        # Complete it
        event.set()
        task.thread.join(timeout=5)
        self.assertEqual(task.status, AgentStatus.COMPLETED)
        self.assertEqual(task.result, "result")

    def test_start_task_failure(self):
        def execute_fn(agent, prompt):
            raise ValueError("test error")

        task = self.mgr.start_task("Fail", "agent", "prompt", execute_fn)
        task.thread.join(timeout=5)
        self.assertEqual(task.status, AgentStatus.FAILED)
        self.assertEqual(task.error, "test error")

    def test_stop_task(self):
        event = threading.Event()

        def execute_fn(agent, prompt):
            event.wait(timeout=10)
            return "done"

        task = self.mgr.start_task("Test", "agent", "prompt", execute_fn)
        time.sleep(0.1)
        self.assertTrue(self.mgr.stop_task(task.task_id))
        self.assertEqual(task.status, AgentStatus.STOPPED)
        event.set()  # Unblock the thread

    def test_stop_task_not_running(self):
        self.assertFalse(self.mgr.stop_task("nonexistent"))

    def test_stop_task_already_completed(self):
        def execute_fn(agent, prompt):
            return "done"

        task = self.mgr.start_task("Test", "agent", "prompt", execute_fn)
        task.thread.join(timeout=5)
        self.assertFalse(self.mgr.stop_task(task.task_id))

    def test_stop_all(self):
        events = []
        for i in range(3):
            e = threading.Event()
            events.append(e)

            def make_fn(ev):
                def fn(agent, prompt):
                    ev.wait(timeout=10)
                    return "done"
                return fn

            self.mgr.start_task(f"Task {i}", "agent", "prompt", make_fn(e))

        time.sleep(0.1)
        count = self.mgr.stop_all()
        self.assertEqual(count, 3)

        # Cleanup
        for e in events:
            e.set()

    def test_stop_all_no_running(self):
        self.assertEqual(self.mgr.stop_all(), 0)

    def test_get_task(self):
        def execute_fn(agent, prompt):
            return "done"

        task = self.mgr.start_task("Test", "agent", "prompt", execute_fn)
        found = self.mgr.get_task(task.task_id)
        self.assertIs(found, task)
        self.assertIsNone(self.mgr.get_task("nonexistent"))

    def test_list_tasks(self):
        def execute_fn(agent, prompt):
            return "done"

        self.mgr.start_task("A", "agent", "p1", execute_fn)
        self.mgr.start_task("B", "agent", "p2", execute_fn)
        tasks = self.mgr.list_tasks()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].name, "A")
        self.assertEqual(tasks[1].name, "B")

    def test_list_tasks_active_only(self):
        event = threading.Event()

        def blocking_fn(agent, prompt):
            event.wait(timeout=10)
            return "done"

        def instant_fn(agent, prompt):
            return "done"

        self.mgr.start_task("Running", "agent", "p", blocking_fn)
        t2 = self.mgr.start_task("Done", "agent", "p", instant_fn)
        t2.thread.join(timeout=5)

        time.sleep(0.1)
        active = self.mgr.list_tasks(active_only=True)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].name, "Running")

        event.set()  # Cleanup

    def test_active_count(self):
        self.assertEqual(self.mgr.active_count(), 0)

        event = threading.Event()

        def fn(agent, prompt):
            event.wait(timeout=10)
            return "done"

        self.mgr.start_task("A", "agent", "p", fn)
        self.mgr.start_task("B", "agent", "p", fn)
        time.sleep(0.1)
        self.assertEqual(self.mgr.active_count(), 2)

        event.set()  # Cleanup

    def test_remove_completed(self):
        def fn(agent, prompt):
            return "done"

        t1 = self.mgr.start_task("A", "agent", "p", fn)
        t2 = self.mgr.start_task("B", "agent", "p", fn)
        t1.thread.join(timeout=5)
        t2.thread.join(timeout=5)

        count = self.mgr.remove_completed()
        self.assertEqual(count, 2)
        self.assertEqual(len(self.mgr.list_tasks()), 0)

    def test_remove_completed_keeps_active(self):
        event = threading.Event()

        def blocking_fn(agent, prompt):
            event.wait(timeout=10)
            return "done"

        def instant_fn(agent, prompt):
            return "done"

        self.mgr.start_task("Running", "agent", "p", blocking_fn)
        t2 = self.mgr.start_task("Done", "agent", "p", instant_fn)
        t2.thread.join(timeout=5)

        time.sleep(0.1)
        count = self.mgr.remove_completed()
        self.assertEqual(count, 1)
        self.assertEqual(len(self.mgr.list_tasks()), 1)
        self.assertEqual(self.mgr.list_tasks()[0].name, "Running")

        event.set()  # Cleanup

    def test_remove_task(self):
        def fn(agent, prompt):
            return "done"

        task = self.mgr.start_task("A", "agent", "p", fn)
        task.thread.join(timeout=5)
        self.assertTrue(self.mgr.remove_task(task.task_id))
        self.assertFalse(self.mgr.remove_task(task.task_id))

    def test_task_id_increments(self):
        def fn(agent, prompt):
            return "done"

        t1 = self.mgr.start_task("A", "agent", "p", fn)
        t2 = self.mgr.start_task("B", "agent", "p", fn)
        t3 = self.mgr.start_task("C", "agent", "p", fn)
        self.assertEqual(t1.task_id, "bg-0001")
        self.assertEqual(t2.task_id, "bg-0002")
        self.assertEqual(t3.task_id, "bg-0003")


class TestStatusBar(unittest.TestCase):
    """Test the get_status_bar_text method."""

    def setUp(self):
        BackgroundAgentManager.reset_instance()
        self.mgr = BackgroundAgentManager()

    def test_no_tasks(self):
        self.assertEqual(self.mgr.get_status_bar_text(), "")

    def test_one_agent(self):
        event = threading.Event()

        def fn(agent, prompt):
            event.wait(timeout=10)
            return "done"

        self.mgr.start_task("A", "agent", "p", fn)
        time.sleep(0.1)
        self.assertEqual(self.mgr.get_status_bar_text(), "1 local agent")
        event.set()

    def test_three_agents(self):
        events = []
        for i in range(3):
            e = threading.Event()
            events.append(e)

            def make_fn(ev):
                def fn(agent, prompt):
                    ev.wait(timeout=10)
                    return "done"
                return fn

            self.mgr.start_task(f"Task {i}", "agent", "p", make_fn(e))

        time.sleep(0.1)
        self.assertEqual(self.mgr.get_status_bar_text(), "3 local agents")

        for e in events:
            e.set()

    def test_completed_not_counted(self):
        def fn(agent, prompt):
            return "done"

        task = self.mgr.start_task("A", "agent", "p", fn)
        task.thread.join(timeout=5)
        self.assertEqual(self.mgr.get_status_bar_text(), "")


class TestRenderPanel(unittest.TestCase):
    """Test the render_tasks_panel function."""

    def setUp(self):
        BackgroundAgentManager.reset_instance()
        self.mgr = BackgroundAgentManager()

    def test_empty_panel(self):
        output = render_tasks_panel(self.mgr)
        self.assertIn("Background tasks", output)
        self.assertIn("No background tasks", output)

    def test_panel_with_tasks(self):
        event = threading.Event()

        def fn(agent, prompt):
            event.wait(timeout=10)
            return "done"

        self.mgr.start_task("Implement Feature 21", "code-writer", "implement", fn)
        self.mgr.start_task("Test Coverage Boost", "code-tester", "test", fn)
        time.sleep(0.1)

        output = render_tasks_panel(self.mgr)
        self.assertIn("Background tasks", output)
        self.assertIn("2 active agents", output)
        self.assertIn("Local agents (2)", output)
        self.assertIn("Implement Feature 21", output)
        self.assertIn("Test Coverage Boost", output)
        self.assertIn("running", output)

        event.set()

    def test_panel_with_completed(self):
        def fn(agent, prompt):
            return "done"

        task = self.mgr.start_task("Done Task", "agent", "p", fn)
        task.thread.join(timeout=5)

        output = render_tasks_panel(self.mgr)
        self.assertIn("completed", output)
        self.assertIn("Done Task", output)

    def test_panel_with_failed(self):
        def fn(agent, prompt):
            raise RuntimeError("boom")

        task = self.mgr.start_task("Fail Task", "agent", "p", fn)
        task.thread.join(timeout=5)

        output = render_tasks_panel(self.mgr)
        self.assertIn("failed", output)
        self.assertIn("Fail Task", output)

    def test_panel_footer(self):
        event = threading.Event()

        def fn(agent, prompt):
            event.wait(timeout=10)
            return "done"

        self.mgr.start_task("T", "agent", "p", fn)
        time.sleep(0.1)

        output = render_tasks_panel(self.mgr)
        self.assertIn("to select", output)
        self.assertIn("Enter to view", output)
        self.assertIn("Esc to close", output)

        event.set()


class TestThreadSafety(unittest.TestCase):
    """Test concurrent access to the manager."""

    def test_concurrent_start(self):
        mgr = BackgroundAgentManager()
        events = []
        results = []

        def fn(agent, prompt):
            return "ok"

        def start_worker():
            task = mgr.start_task("T", "agent", "p", fn)
            results.append(task.task_id)

        threads = [threading.Thread(target=start_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # All task IDs should be unique
        self.assertEqual(len(set(results)), 10)
        self.assertEqual(len(mgr.list_tasks()), 10)


if __name__ == "__main__":
    unittest.main()
