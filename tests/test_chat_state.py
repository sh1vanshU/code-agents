"""Tests for code_agents.chat.chat_state and chat_skill_runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# chat_skill_runner — re-export test
# ---------------------------------------------------------------------------

class TestChatSkillRunner:
    def test_handle_post_response_importable(self):
        """chat_skill_runner re-exports handle_post_response from chat_response."""
        from code_agents.chat.chat_skill_runner import handle_post_response
        assert callable(handle_post_response)


# ---------------------------------------------------------------------------
# SLASH_COMMANDS
# ---------------------------------------------------------------------------

class TestSlashCommands:
    def test_is_list(self):
        from code_agents.chat.chat_state import SLASH_COMMANDS
        assert isinstance(SLASH_COMMANDS, list)

    def test_not_empty(self):
        from code_agents.chat.chat_state import SLASH_COMMANDS
        assert len(SLASH_COMMANDS) > 0

    def test_all_start_with_slash(self):
        from code_agents.chat.chat_state import SLASH_COMMANDS
        for cmd in SLASH_COMMANDS:
            assert cmd.startswith("/"), f"{cmd!r} does not start with /"

    def test_contains_common_commands(self):
        from code_agents.chat.chat_state import SLASH_COMMANDS
        for expected in ["/help", "/quit", "/exit", "/agents", "/clear", "/resume"]:
            assert expected in SLASH_COMMANDS

    def test_all_strings(self):
        from code_agents.chat.chat_state import SLASH_COMMANDS
        for cmd in SLASH_COMMANDS:
            assert isinstance(cmd, str)


# ---------------------------------------------------------------------------
# initial_chat_state
# ---------------------------------------------------------------------------

class TestInitialChatState:
    def test_returns_dict(self):
        from code_agents.chat.chat_state import initial_chat_state
        result = initial_chat_state("code-gen", "/repo", "developer")
        assert isinstance(result, dict)

    def test_agent_key(self):
        from code_agents.chat.chat_state import initial_chat_state
        result = initial_chat_state("explore", "/repo", "dev")
        assert result["agent"] == "explore"

    def test_repo_path_key(self):
        from code_agents.chat.chat_state import initial_chat_state
        result = initial_chat_state("a", "/my/repo", "dev")
        assert result["repo_path"] == "/my/repo"

    def test_user_role_key(self):
        from code_agents.chat.chat_state import initial_chat_state
        result = initial_chat_state("a", "/r", "admin")
        assert result["user_role"] == "admin"

    def test_session_id_is_none(self):
        from code_agents.chat.chat_state import initial_chat_state
        result = initial_chat_state("a", "/r", "dev")
        assert result["session_id"] is None

    def test_chat_session_is_none(self):
        from code_agents.chat.chat_state import initial_chat_state
        result = initial_chat_state("a", "/r", "dev")
        assert result["_chat_session"] is None

    def test_has_exactly_expected_keys(self):
        from code_agents.chat.chat_state import initial_chat_state
        result = initial_chat_state("a", "/r", "dev")
        assert set(result.keys()) == {"agent", "session_id", "repo_path", "_chat_session", "user_role"}


# ---------------------------------------------------------------------------
# apply_resume_session
# ---------------------------------------------------------------------------

class TestApplyResumeSession:
    @patch("code_agents.chat.chat_history.get_qa_pairs")
    @patch("code_agents.chat.chat_history.load_session")
    def test_returns_false_when_load_fails(self, mock_load, mock_qa):
        from code_agents.chat.chat_state import apply_resume_session
        mock_load.return_value = None

        state: dict = {"agent": "x", "session_id": None, "_chat_session": None}
        ok, agent = apply_resume_session(state, "bad-uuid")

        assert ok is False
        assert agent is None

    @patch("code_agents.chat.chat_history.get_qa_pairs")
    @patch("code_agents.chat.chat_history.load_session")
    def test_returns_true_and_agent_on_success(self, mock_load, mock_qa):
        from code_agents.chat.chat_state import apply_resume_session
        mock_load.return_value = {
            "agent": "code-gen",
            "_server_session_id": "sid-1",
        }
        mock_qa.return_value = []

        state: dict = {"agent": "x", "session_id": None, "_chat_session": None}
        ok, agent = apply_resume_session(state, "some-uuid")

        assert ok is True
        assert agent == "code-gen"

    @patch("code_agents.chat.chat_history.get_qa_pairs")
    @patch("code_agents.chat.chat_history.load_session")
    def test_state_updated_on_success(self, mock_load, mock_qa):
        from code_agents.chat.chat_state import apply_resume_session
        loaded_session = {
            "agent": "explore",
            "_server_session_id": "sid-2",
        }
        mock_load.return_value = loaded_session
        mock_qa.return_value = []

        state: dict = {"agent": "x", "session_id": None, "_chat_session": None}
        apply_resume_session(state, "uuid-1")

        assert state["agent"] == "explore"
        assert state["session_id"] == "sid-2"
        assert state["_chat_session"] is loaded_session

    @patch("code_agents.chat.chat_history.get_qa_pairs")
    @patch("code_agents.chat.chat_history.load_session")
    def test_qa_pairs_set_when_present(self, mock_load, mock_qa):
        from code_agents.chat.chat_state import apply_resume_session
        mock_load.return_value = {"agent": "a", "_server_session_id": "s"}
        mock_qa.return_value = [("q", "a")]

        state: dict = {"agent": "x", "session_id": None, "_chat_session": None}
        apply_resume_session(state, "uuid")

        assert state["_qa_pairs"] == [("q", "a")]

    @patch("code_agents.chat.chat_history.get_qa_pairs")
    @patch("code_agents.chat.chat_history.load_session")
    def test_qa_pairs_not_set_when_empty(self, mock_load, mock_qa):
        from code_agents.chat.chat_state import apply_resume_session
        mock_load.return_value = {"agent": "a", "_server_session_id": "s"}
        mock_qa.return_value = []

        state: dict = {"agent": "x", "session_id": None, "_chat_session": None}
        apply_resume_session(state, "uuid")

        assert "_qa_pairs" not in state

    @patch("code_agents.chat.chat_history.get_qa_pairs")
    @patch("code_agents.chat.chat_history.load_session")
    def test_resume_id_stripped(self, mock_load, mock_qa):
        from code_agents.chat.chat_state import apply_resume_session
        mock_load.return_value = None

        state: dict = {}
        apply_resume_session(state, "  uuid-with-spaces  ")
        mock_load.assert_called_once_with("uuid-with-spaces")
