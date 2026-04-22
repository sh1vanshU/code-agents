"""Tests for architecture wiring — background agent live data, audit gates, corrections/RAG/trace injection."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 1. Background Agent live data feed (#30)
# ---------------------------------------------------------------------------


class TestBackgroundAgentLiveData(unittest.TestCase):
    """Test that background tasks track live token/tool/file progress."""

    def setUp(self):
        from code_agents.devops.background_agent import BackgroundAgentManager
        BackgroundAgentManager.reset_instance()
        self.mgr = BackgroundAgentManager.get_instance()

    def tearDown(self):
        from code_agents.devops.background_agent import BackgroundAgentManager
        self.mgr.stop_all()
        BackgroundAgentManager.reset_instance()

    def test_update_task_progress_tokens(self):
        """update_task_progress increments token counter."""
        def fake_fn(agent, prompt):
            time.sleep(0.05)
            return "done"

        task = self.mgr.start_task("test", "code-writer", "hi", fake_fn)
        time.sleep(0.02)  # let it start
        self.mgr.update_task_progress(task.task_id, tokens_delta=500)
        self.assertEqual(task.progress.tokens_used, 500)
        self.mgr.update_task_progress(task.task_id, tokens_delta=300)
        self.assertEqual(task.progress.tokens_used, 800)

    def test_update_task_progress_tools(self):
        """update_task_progress increments tool counter."""
        def fake_fn(agent, prompt):
            time.sleep(0.05)
            return "done"

        task = self.mgr.start_task("test", "code-writer", "hi", fake_fn)
        time.sleep(0.02)
        self.mgr.update_task_progress(task.task_id, tools_delta=1)
        self.mgr.update_task_progress(task.task_id, tools_delta=1)
        self.assertEqual(task.progress.tools_used, 2)

    def test_update_task_progress_files(self):
        """update_task_progress tracks modified files (deduped)."""
        def fake_fn(agent, prompt):
            time.sleep(0.05)
            return "done"

        task = self.mgr.start_task("test", "code-writer", "hi", fake_fn)
        time.sleep(0.02)
        self.mgr.update_task_progress(task.task_id, file_modified="src/main.py")
        self.mgr.update_task_progress(task.task_id, file_modified="src/main.py")  # dupe
        self.mgr.update_task_progress(task.task_id, file_modified="src/utils.py")
        self.assertEqual(len(task.progress.files_modified), 2)
        self.assertIn("src/main.py", task.progress.files_modified)

    def test_progress_callback_attached(self):
        """_make_progress_callback attaches _progress_cb to task."""
        def fake_fn(agent, prompt):
            time.sleep(0.05)
            return "done"

        task = self.mgr.start_task("test", "code-writer", "hi", fake_fn)
        time.sleep(0.02)
        # The _run wrapper calls _make_progress_callback which sets task._progress_cb
        self.assertTrue(hasattr(task, "_progress_cb"))
        # Use the callback directly
        task._progress_cb({"tokens": 1000, "tools": 5, "file": "app.py"})
        self.assertEqual(task.progress.tokens_used, 1000)
        self.assertEqual(task.progress.tools_used, 5)
        self.assertIn("app.py", task.progress.files_modified)

    def test_update_nonexistent_task(self):
        """update_task_progress on missing task is a no-op."""
        self.mgr.update_task_progress("bg-9999", tokens_delta=100)  # should not raise

    def test_elapsed_seconds_updated(self):
        """update_task_progress also updates elapsed_seconds."""
        def fake_fn(agent, prompt):
            time.sleep(0.1)
            return "done"

        task = self.mgr.start_task("test", "code-writer", "hi", fake_fn)
        time.sleep(0.05)
        self.mgr.update_task_progress(task.task_id, tokens_delta=1)
        self.assertGreater(task.progress.elapsed_seconds, 0)


# ---------------------------------------------------------------------------
# 2. Audit quality gates wiring (#32)
# ---------------------------------------------------------------------------


class TestAuditLoadGates(unittest.TestCase):
    """Test load_gates() reading from .foundry/casts/ YAML files."""

    def test_load_gates_no_cwd(self):
        """Without cwd, returns built-in QUALITY_GATES."""
        from code_agents.security.audit_orchestrator import load_gates, QUALITY_GATES
        result = load_gates(None)
        self.assertEqual(result, QUALITY_GATES)

    def test_load_gates_missing_dir(self):
        """With a cwd lacking .foundry/casts/, returns built-in gates."""
        from code_agents.security.audit_orchestrator import load_gates, QUALITY_GATES
        with tempfile.TemporaryDirectory() as tmp:
            result = load_gates(tmp)
            self.assertEqual(result, QUALITY_GATES)

    def test_load_gates_from_yaml(self):
        """Reads gate definitions from YAML files in .foundry/casts/."""
        from code_agents.security.audit_orchestrator import load_gates

        with tempfile.TemporaryDirectory() as tmp:
            casts_dir = Path(tmp) / ".foundry" / "casts"
            casts_dir.mkdir(parents=True)
            (casts_dir / "test-gates.yaml").write_text(
                "gates:\n"
                '  - name: "Test gate"\n'
                '    check: "_gate_test"\n'
                '    severity: "warning"\n'
                '    description: "A test gate"\n'
            )
            try:
                import yaml  # noqa: F401
            except ImportError:
                self.skipTest("PyYAML not installed")

            result = load_gates(tmp)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["name"], "Test gate")
            self.assertEqual(result[0]["check"], "_gate_test")
            self.assertEqual(result[0]["source"], "test-gates.yaml")
            self.assertEqual(result[0]["severity"], "warning")

    def test_load_gates_skips_bad_yaml(self):
        """Malformed YAML files are skipped gracefully."""
        from code_agents.security.audit_orchestrator import load_gates, QUALITY_GATES

        with tempfile.TemporaryDirectory() as tmp:
            casts_dir = Path(tmp) / ".foundry" / "casts"
            casts_dir.mkdir(parents=True)
            (casts_dir / "broken.yaml").write_text("not: valid: yaml: [")
            try:
                import yaml  # noqa: F401
            except ImportError:
                self.skipTest("PyYAML not installed")
            result = load_gates(tmp)
            # Falls back to built-in since no valid gates
            self.assertEqual(result, QUALITY_GATES)

    def test_load_gates_from_repo_root(self):
        """The repo's own .foundry/casts/ should contain valid gate files."""
        from code_agents.security.audit_orchestrator import load_gates
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        casts_dir = Path(repo_root) / ".foundry" / "casts"
        if not casts_dir.is_dir():
            self.skipTest(".foundry/casts/ not present in repo")
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML not installed")
        result = load_gates(repo_root)
        self.assertGreater(len(result), 0)
        # All entries should have required keys
        for gate in result:
            self.assertIn("name", gate)
            self.assertIn("check", gate)
            self.assertIn("source", gate)

    def test_run_quality_gates_uses_load_gates(self):
        """AuditOrchestrator._run_quality_gates delegates to load_gates."""
        from code_agents.security.audit_orchestrator import AuditOrchestrator
        orch = AuditOrchestrator("/tmp")
        with patch("code_agents.security.audit_orchestrator.load_gates") as mock_lg:
            mock_lg.return_value = [
                {"name": "Mock gate", "source": "mock.yaml", "check": "_gate_no_secrets"},
            ]
            gates = orch._run_quality_gates()
            mock_lg.assert_called_once_with("/tmp")
            # Should have exactly one gate result
            self.assertEqual(len(gates), 1)
            # The gate method sets its own name internally, but source comes from config
            self.assertEqual(gates[0].source, "mock.yaml")


# ---------------------------------------------------------------------------
# 3a. Agent corrections injection (#33)
# ---------------------------------------------------------------------------


class TestCorrectionsInjection(unittest.TestCase):
    """Test that inject_corrections is wired into _build_system_context."""

    @patch("code_agents.agent_system.agent_corrections.inject_corrections")
    def test_corrections_wired_into_context(self, mock_inject):
        """_build_system_context calls inject_corrections and appends result."""
        mock_inject.return_value = "--- Past Corrections ---\nCorrection 1: ...\n--- End Corrections ---"
        from code_agents.chat.chat_context import _build_system_context
        with patch("code_agents.agent_system.rules_loader.load_rules", return_value=""):
            ctx = _build_system_context("/tmp/test-repo", "code-writer", btw_messages=["fix the bug"])
        mock_inject.assert_called_once()
        self.assertIn("Past Corrections", ctx)

    @patch("code_agents.agent_system.agent_corrections.inject_corrections")
    def test_corrections_empty_is_noop(self, mock_inject):
        """When inject_corrections returns empty string, nothing is added."""
        mock_inject.return_value = ""
        from code_agents.chat.chat_context import _build_system_context
        with patch("code_agents.agent_system.rules_loader.load_rules", return_value=""):
            ctx = _build_system_context("/tmp/test-repo", "code-writer")
        self.assertNotIn("Past Corrections", ctx)


# ---------------------------------------------------------------------------
# 3b. RAG context injection (#34)
# ---------------------------------------------------------------------------


class TestRAGContextInjection(unittest.TestCase):
    """Test that RAGContextInjector is wired into _build_system_context."""

    @patch("code_agents.knowledge.rag_context.RAGContextInjector")
    def test_rag_wired_into_context(self, MockRAG):
        """_build_system_context calls RAGContextInjector.get_context and appends result."""
        mock_instance = MagicMock()
        mock_instance.store.is_ready.return_value = True
        mock_instance.get_context.return_value = "--- Relevant Code ---\nfoo.py...\n--- End Relevant Code ---"
        MockRAG.return_value = mock_instance

        from code_agents.chat.chat_context import _build_system_context
        with patch("code_agents.agent_system.rules_loader.load_rules", return_value=""):
            ctx = _build_system_context("/tmp/test-repo", "code-writer", btw_messages=["search for auth"])
        self.assertIn("Relevant Code", ctx)

    @patch("code_agents.knowledge.rag_context.RAGContextInjector")
    def test_rag_not_ready_is_noop(self, MockRAG):
        """When store is not ready, nothing is added."""
        mock_instance = MagicMock()
        mock_instance.store.is_ready.return_value = False
        MockRAG.return_value = mock_instance

        from code_agents.chat.chat_context import _build_system_context
        with patch("code_agents.agent_system.rules_loader.load_rules", return_value=""):
            ctx = _build_system_context("/tmp/test-repo", "code-writer")
        self.assertNotIn("Relevant Code", ctx)


# ---------------------------------------------------------------------------
# 3c. Trace recording (#35)
# ---------------------------------------------------------------------------


class TestTraceRecordingWiring(unittest.TestCase):
    """Test that TraceRecorder.record_step is called in handle_post_response."""

    @patch("code_agents.agent_system.agent_replay.TraceRecorder")
    def test_trace_recorder_created_and_records(self, MockRecorder):
        """handle_post_response creates a TraceRecorder and records steps."""
        mock_instance = MagicMock()
        mock_trace = MagicMock()
        mock_trace.steps = []
        mock_instance.get_trace.return_value = mock_trace
        MockRecorder.return_value = mock_instance

        from code_agents.chat.chat_response import handle_post_response

        state = {
            "_chat_session": {"id": "test-session", "messages": []},
            "repo_path": "/tmp/test-repo",
            "session_id": "sid-123",
            "_response_start": time.time(),
        }

        with patch("code_agents.chat.chat_response._stream_chat"), \
             patch("code_agents.chat.chat_response._build_system_context", return_value=""), \
             patch("code_agents.core.token_tracker.record_usage"), \
             patch("code_agents.core.confidence_scorer.get_scorer", side_effect=ImportError), \
             patch("code_agents.core.response_verifier.get_verifier", side_effect=ImportError), \
             patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=False):
            result, agent = handle_post_response(
                full_response=["Hello, world!"],
                user_input="test prompt",
                state=state,
                url="http://localhost:8000",
                current_agent="code-writer",
                system_context="",
                cwd="/tmp/test-repo",
            )

        # Verify recorder was created
        MockRecorder.assert_called_once_with(
            session_id="test-session",
            agent="code-writer",
            repo="/tmp/test-repo",
        )
        # Verify both user and assistant steps were recorded
        calls = mock_instance.record_step.call_args_list
        self.assertGreaterEqual(len(calls), 2)
        # First call: user message
        self.assertEqual(calls[0][0][0], "user")
        self.assertEqual(calls[0][0][1], "test prompt")
        # Second call: assistant response
        self.assertEqual(calls[1][0][0], "assistant")
        self.assertEqual(calls[1][0][1], "Hello, world!")

    def test_trace_recorder_reuses_existing(self):
        """If state already has _trace_recorder, it reuses it."""
        from code_agents.agent_system.agent_replay import TraceRecorder

        mock_recorder = MagicMock(spec=TraceRecorder)
        mock_trace = MagicMock()
        mock_trace.steps = []
        mock_recorder.get_trace.return_value = mock_trace

        from code_agents.chat.chat_response import handle_post_response

        state = {
            "_chat_session": {"id": "test-session", "messages": []},
            "repo_path": "/tmp/test-repo",
            "session_id": "sid-123",
            "_response_start": time.time(),
            "_trace_recorder": mock_recorder,  # pre-existing
        }

        with patch("code_agents.core.token_tracker.record_usage"), \
             patch("code_agents.core.confidence_scorer.get_scorer", side_effect=ImportError), \
             patch("code_agents.core.response_verifier.get_verifier", side_effect=ImportError), \
             patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=False):
            handle_post_response(
                full_response=["response"],
                user_input="input",
                state=state,
                url="http://localhost:8000",
                current_agent="code-writer",
                system_context="",
                cwd="/tmp/test-repo",
            )

        # Should reuse the existing recorder, not create a new one
        self.assertIs(state["_trace_recorder"], mock_recorder)
        self.assertTrue(mock_recorder.record_step.called)


if __name__ == "__main__":
    unittest.main()
