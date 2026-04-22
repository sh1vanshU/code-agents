"""Tests for chat_background.py — background task management."""

from __future__ import annotations

import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from code_agents.chat.chat_background import (
    OutputTarget,
    BackgroundTask,
    BackgroundTaskManager,
    generate_task_name,
    _format_elapsed,
    send_desktop_notification,
    merge_scratchpad,
    on_background_complete,
    get_background_manager,
)


# ---------------------------------------------------------------------------
# OutputTarget
# ---------------------------------------------------------------------------

class TestOutputTarget:
    """Tests for OutputTarget — switchable stdout/buffer."""

    def test_write_to_stdout_by_default(self, capsys):
        ot = OutputTarget()
        ot.write("hello")
        captured = capsys.readouterr()
        assert "hello" in captured.out

    def test_redirect_to_buffer(self, capsys):
        ot = OutputTarget()
        ot.redirect_to_buffer()
        ot.write("buffered text")
        captured = capsys.readouterr()
        assert "buffered text" not in captured.out
        assert ot.get_buffer() == "buffered text"

    def test_restore_to_stdout(self, capsys):
        ot = OutputTarget()
        ot.redirect_to_buffer()
        ot.write("hidden")
        ot.restore_to_stdout()
        ot.write("visible")
        captured = capsys.readouterr()
        assert "visible" in captured.out
        assert "hidden" not in captured.out

    def test_get_buffer_concatenates(self):
        ot = OutputTarget()
        ot.redirect_to_buffer()
        ot.write("part1")
        ot.write("part2")
        ot.write("part3")
        assert ot.get_buffer() == "part1part2part3"

    def test_is_buffering_property(self):
        ot = OutputTarget()
        assert not ot.is_buffering
        ot.redirect_to_buffer()
        assert ot.is_buffering
        ot.restore_to_stdout()
        assert not ot.is_buffering

    def test_flush_no_error_when_buffering(self):
        ot = OutputTarget()
        ot.redirect_to_buffer()
        ot.flush()  # should not raise

    def test_thread_safety(self):
        ot = OutputTarget()
        ot.redirect_to_buffer()
        errors = []

        def writer(prefix):
            try:
                for i in range(100):
                    ot.write(f"{prefix}{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(f"t{i}-",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        buf = ot.get_buffer()
        assert len(buf) > 0


# ---------------------------------------------------------------------------
# Task naming
# ---------------------------------------------------------------------------

class TestTaskNaming:
    """Tests for generate_task_name()."""

    def test_build_with_repo(self):
        name = generate_task_name("jenkins-cicd", "build and deploy pg-acquiring-biz to dev")
        assert name == "build:pg-acquiring-biz"

    def test_deploy_with_repo(self):
        name = generate_task_name("jenkins-cicd", "deploy payment-service to staging")
        assert name == "deploy:payment-service"

    def test_test_with_repo(self):
        name = generate_task_name("code-tester", "test pg-acquiring-biz unit tests")
        assert name == "test:pg-acquiring-biz"

    def test_no_action_no_target(self):
        name = generate_task_name("code-reasoning", "explain the auth module")
        assert name == "task:code-reasoning"

    def test_file_path_target(self):
        name = generate_task_name("code-writer", "review src/main/App.java changes")
        assert name == "review:App.java"

    def test_action_check(self):
        name = generate_task_name("code-reviewer", "check if the login flow is correct")
        assert name == "check:code-reviewer"

    def test_strips_punctuation(self):
        name = generate_task_name("jenkins-cicd", 'build "pg-acquiring-biz" now')
        assert "pg-acquiring-biz" in name


# ---------------------------------------------------------------------------
# BackgroundTask
# ---------------------------------------------------------------------------

class TestBackgroundTask:
    """Tests for BackgroundTask dataclass."""

    def test_defaults(self):
        task = BackgroundTask(
            task_id=1,
            display_name="build:test",
            agent_name="jenkins-cicd",
            user_input="build test",
        )
        assert task.status == "running"
        assert task.full_response is None
        assert task.error is None
        assert task.result_summary == ""
        assert task.elapsed >= 0

    def test_elapsed_str(self):
        task = BackgroundTask(
            task_id=1,
            display_name="test",
            agent_name="test",
            user_input="test",
            started_at=time.monotonic() - 125,  # 2m 5s ago
        )
        assert "2m" in task.elapsed_str


# ---------------------------------------------------------------------------
# BackgroundTaskManager
# ---------------------------------------------------------------------------

class TestBackgroundTaskManager:
    """Tests for BackgroundTaskManager."""

    def test_create_and_list(self):
        mgr = BackgroundTaskManager()
        task = mgr.create_task("jenkins-cicd", "build repo", {}, OutputTarget())
        assert task.task_id == 1
        assert len(mgr.list_tasks()) == 1

    def test_auto_increment_ids(self):
        mgr = BackgroundTaskManager()
        t1 = mgr.create_task("a", "test1", {}, OutputTarget())
        t2 = mgr.create_task("b", "test2", {}, OutputTarget())
        assert t2.task_id == t1.task_id + 1

    def test_get_task(self):
        mgr = BackgroundTaskManager()
        task = mgr.create_task("a", "test", {}, OutputTarget())
        assert mgr.get_task(task.task_id) is task
        assert mgr.get_task(999) is None

    def test_remove_task(self):
        mgr = BackgroundTaskManager()
        task = mgr.create_task("a", "test", {}, OutputTarget())
        mgr.remove_task(task.task_id)
        assert mgr.get_task(task.task_id) is None
        assert len(mgr.list_tasks()) == 0

    def test_active_count(self):
        mgr = BackgroundTaskManager()
        t1 = mgr.create_task("a", "test1", {}, OutputTarget())
        t2 = mgr.create_task("b", "test2", {}, OutputTarget())
        assert mgr.active_count() == 2
        t1.status = "done"
        assert mgr.active_count() == 1

    def test_can_create_respects_limit(self):
        mgr = BackgroundTaskManager()
        mgr._max_concurrent = 2
        mgr.create_task("a", "t1", {}, OutputTarget())
        mgr.create_task("b", "t2", {}, OutputTarget())
        assert not mgr.can_create()

    def test_can_create_after_done(self):
        mgr = BackgroundTaskManager()
        mgr._max_concurrent = 1
        t1 = mgr.create_task("a", "t1", {}, OutputTarget())
        assert not mgr.can_create()
        t1.status = "done"
        assert mgr.can_create()

    def test_has_tasks(self):
        mgr = BackgroundTaskManager()
        assert not mgr.has_tasks()
        mgr.create_task("a", "t1", {}, OutputTarget())
        assert mgr.has_tasks()

    def test_done_tasks(self):
        mgr = BackgroundTaskManager()
        t1 = mgr.create_task("a", "t1", {}, OutputTarget())
        t2 = mgr.create_task("b", "t2", {}, OutputTarget())
        assert len(mgr.done_tasks()) == 0
        t1.status = "done"
        assert len(mgr.done_tasks()) == 1
        t2.status = "error"
        assert len(mgr.done_tasks()) == 2

    @patch.dict("os.environ", {"CODE_AGENTS_MAX_BACKGROUND": "5"})
    def test_max_from_env(self):
        mgr = BackgroundTaskManager()
        assert mgr.max_concurrent == 5


# ---------------------------------------------------------------------------
# _format_elapsed
# ---------------------------------------------------------------------------

class TestFormatElapsed:
    def test_seconds(self):
        assert _format_elapsed(45) == "45s"

    def test_minutes(self):
        assert _format_elapsed(125) == "2m 05s"

    def test_zero(self):
        assert _format_elapsed(0) == "0s"


# ---------------------------------------------------------------------------
# on_background_complete
# ---------------------------------------------------------------------------

class TestOnBackgroundComplete:
    """Tests for the completion callback."""

    @patch("code_agents.chat.chat_background.send_desktop_notification")
    def test_done_with_response(self, mock_notify):
        task = BackgroundTask(
            task_id=1, display_name="build:test",
            agent_name="jenkins", user_input="build test",
        )
        on_background_complete(task, True, ["Build #916 SUCCESS\nDone."], False)
        assert task.status == "done"
        assert "SUCCESS" in task.result_summary
        mock_notify.assert_called_once()

    @patch("code_agents.chat.chat_background.send_desktop_notification")
    def test_interrupted(self, mock_notify):
        task = BackgroundTask(
            task_id=1, display_name="test",
            agent_name="test", user_input="test",
        )
        on_background_complete(task, False, [], True)
        assert task.status == "error"
        assert task.error == "Interrupted"

    @patch("code_agents.chat.chat_background.send_desktop_notification")
    def test_no_response(self, mock_notify):
        task = BackgroundTask(
            task_id=1, display_name="test",
            agent_name="test", user_input="test",
        )
        on_background_complete(task, False, [], False)
        assert task.status == "error"


# ---------------------------------------------------------------------------
# Desktop notification
# ---------------------------------------------------------------------------

class TestDesktopNotification:
    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.Popen")
    def test_macos_notification(self, mock_popen, mock_platform):
        task = BackgroundTask(
            task_id=1, display_name="build:test",
            agent_name="test", user_input="test",
            result_summary="Build SUCCESS",
        )
        send_desktop_notification(task)
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert "osascript" in call_args
        assert "Build SUCCESS" in call_args[-1]

    @patch("platform.system", return_value="Linux")
    @patch("subprocess.Popen")
    def test_non_macos_noop(self, mock_popen, mock_platform):
        task = BackgroundTask(
            task_id=1, display_name="test",
            agent_name="test", user_input="test",
        )
        send_desktop_notification(task)
        mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# Scratchpad merge
# ---------------------------------------------------------------------------

class TestScratchpadMerge:
    @patch("code_agents.agent_system.session_scratchpad.SessionScratchpad")
    def test_merge_facts(self, MockSP):
        bg_instance = MagicMock()
        bg_instance.get_all.return_value = {"branch": "main", "build_id": "916"}
        main_instance = MagicMock()

        MockSP.side_effect = [bg_instance, main_instance]

        main_state = {"_chat_session": {"id": "main-sess-123"}}
        merge_scratchpad("bg-sess-456", main_state)

        assert main_instance.set.call_count == 2
        main_instance.set.assert_any_call("branch", "main")
        main_instance.set.assert_any_call("build_id", "916")

    def test_merge_no_session_noop(self):
        # Should not raise
        merge_scratchpad("", {})
        merge_scratchpad("bg-123", {"_chat_session": None})


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_background_manager_returns_same(self):
        import code_agents.chat.chat_background as mod
        old = mod._bg_manager
        mod._bg_manager = None
        try:
            m1 = get_background_manager()
            m2 = get_background_manager()
            assert m1 is m2
        finally:
            mod._bg_manager = old
