"""Tests for questionnaire.py — interactive Q&A for agent clarification."""

from __future__ import annotations

import pytest

from code_agents.agent_system.questionnaire import (
    ask_question,
    ask_multiple,
    format_qa_for_prompt,
    TEMPLATES,
)


class TestFormatQaForPrompt:
    """Test Q&A formatting for prompt injection."""

    def test_empty_list(self):
        assert format_qa_for_prompt([]) == ""

    def test_single_qa(self):
        qa = [{"question": "Which env?", "answer": "staging", "is_other": False}]
        result = format_qa_for_prompt(qa)
        assert "User clarifications:" in result
        assert "Q: Which env?" in result
        assert "A: staging" in result

    def test_other_tag(self):
        qa = [{"question": "Which env?", "answer": "custom-env", "is_other": True}]
        result = format_qa_for_prompt(qa)
        assert "(custom answer)" in result

    def test_no_other_tag(self):
        qa = [{"question": "Which env?", "answer": "dev", "is_other": False}]
        result = format_qa_for_prompt(qa)
        assert "(custom answer)" not in result

    def test_multiple_qa(self):
        qa = [
            {"question": "Q1?", "answer": "A1", "is_other": False},
            {"question": "Q2?", "answer": "A2", "is_other": True},
        ]
        result = format_qa_for_prompt(qa)
        assert "Q: Q1?" in result
        assert "Q: Q2?" in result
        assert "A: A1" in result
        assert "A: A2" in result


class TestTemplates:
    """Verify pre-built templates."""

    def test_all_templates_have_question(self):
        for key, tmpl in TEMPLATES.items():
            assert "question" in tmpl, f"Template {key} missing 'question'"
            assert "options" in tmpl, f"Template {key} missing 'options'"

    def test_all_templates_have_options(self):
        for key, tmpl in TEMPLATES.items():
            assert len(tmpl["options"]) >= 2, f"Template {key} needs >= 2 options"

    def test_expected_templates_exist(self):
        expected = ["environment", "database", "deploy_strategy", "branch",
                    "test_scope", "review_depth", "jira_type"]
        for key in expected:
            assert key in TEMPLATES, f"Missing template: {key}"

    def test_environment_options(self):
        assert "dev" in TEMPLATES["environment"]["options"]
        assert "staging" in TEMPLATES["environment"]["options"]

    def test_deploy_strategy_options(self):
        opts = TEMPLATES["deploy_strategy"]["options"]
        assert any("Rolling" in o for o in opts)
        assert any("Canary" in o for o in opts)


class TestAskQuestion:
    """Test ask_question with mocked input."""

    def test_default_selection(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        result = ask_question("Pick one", ["A", "B", "C"], allow_other=False, default=1)
        assert result["answer"] == "B"
        assert result["option_idx"] == 1
        assert result["is_other"] is False

    def test_letter_selection(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "b")
        result = ask_question("Pick one", ["A", "B", "C"], allow_other=False, default=0)
        assert result["answer"] == "B"
        assert result["option_idx"] == 1

    def test_first_option(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "a")
        result = ask_question("Pick one", ["X", "Y"], allow_other=False, default=0)
        assert result["answer"] == "X"
        assert result["option_idx"] == 0

    def test_other_option(self, monkeypatch):
        inputs = iter(["c", "my custom answer"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        result = ask_question("Pick one", ["A", "B"], allow_other=True, default=0)
        assert result["is_other"] is True
        assert result["answer"] == "my custom answer"

    def test_other_empty_detail(self, monkeypatch):
        inputs = iter(["c", ""])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        result = ask_question("Pick one", ["A", "B"], allow_other=True, default=0)
        assert result["is_other"] is True
        assert result["answer"] == "No details provided"

    def test_eof_returns_default(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError))
        result = ask_question("Pick one", ["A", "B"], allow_other=False, default=0)
        assert result["answer"] == "A"
        assert result["option_idx"] == 0

    def test_invalid_input_uses_default(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "zzz")
        result = ask_question("Pick one", ["A", "B"], allow_other=False, default=1)
        assert result["answer"] == "B"

    def test_question_preserved(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        result = ask_question("My question?", ["Yes"], allow_other=False, default=0)
        assert result["question"] == "My question?"


class TestAskMultiple:
    """Test ask_multiple with mocked input."""

    def test_two_questions(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "")
        questions = [
            {"question": "Q1?", "options": ["A", "B"], "default": 0},
            {"question": "Q2?", "options": ["X", "Y"], "default": 1},
        ]
        results = ask_multiple(questions)
        assert len(results) == 2
        assert results[0]["answer"] == "A"
        assert results[1]["answer"] == "Y"

    def test_empty_list(self):
        assert ask_multiple([]) == []


class TestQuestionSelectorTTY:
    """Test _question_selector TTY path via show_panel delegation."""

    def test_tty_panel_selects_index(self):
        from code_agents.agent_system.questionnaire import _question_selector
        from unittest.mock import patch, MagicMock

        mock_isatty = MagicMock(return_value=True)
        with patch("code_agents.agent_system.questionnaire.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", return_value=2) as mock_panel:
            mock_stdout.isatty = mock_isatty
            result = _question_selector("prompt", ["A", "B", "C"], default=0)
        assert result == 2
        mock_panel.assert_called_once()

    def test_tty_panel_cancel_returns_default(self):
        from code_agents.agent_system.questionnaire import _question_selector
        from unittest.mock import patch, MagicMock

        mock_isatty = MagicMock(return_value=True)
        with patch("code_agents.agent_system.questionnaire.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", return_value=None):
            mock_stdout.isatty = mock_isatty
            result = _question_selector("prompt", ["A", "B", "C"], default=1)
        assert result == 1

    def test_tty_panel_default_index(self):
        from code_agents.agent_system.questionnaire import _question_selector
        from unittest.mock import patch, MagicMock

        mock_isatty = MagicMock(return_value=True)
        with patch("code_agents.agent_system.questionnaire.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", return_value=0) as mock_panel:
            mock_stdout.isatty = mock_isatty
            result = _question_selector("prompt", ["A", "B", "C"], default=1)
        assert result == 0
        # Verify default is passed through to show_panel
        args = mock_panel.call_args[0]
        assert args[3] == 1  # default parameter

    def test_tty_panel_exception_falls_to_fallback(self):
        from code_agents.agent_system.questionnaire import _question_selector
        from unittest.mock import patch, MagicMock

        mock_isatty = MagicMock(return_value=True)
        with patch("code_agents.agent_system.questionnaire.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", side_effect=RuntimeError("test")), \
             patch("builtins.input", return_value="b"), \
             patch("builtins.print"):
            mock_stdout.isatty = mock_isatty
            result = _question_selector("prompt", ["A", "B", "C"], default=0)
        assert result == 1  # 'b' selects second option

    def test_tty_panel_keyboard_interrupt_returns_default(self):
        from code_agents.agent_system.questionnaire import _question_selector
        from unittest.mock import patch, MagicMock

        mock_isatty = MagicMock(return_value=True)
        with patch("code_agents.agent_system.questionnaire.sys.stdout") as mock_stdout, \
             patch("code_agents.chat.command_panel.show_panel", side_effect=KeyboardInterrupt):
            mock_stdout.isatty = mock_isatty
            result = _question_selector("prompt", ["A", "B", "C"], default=2)
        assert result == 2

    def test_non_tty_uses_fallback(self):
        from code_agents.agent_system.questionnaire import _question_selector
        from unittest.mock import patch, MagicMock

        mock_isatty = MagicMock(return_value=False)
        with patch("code_agents.agent_system.questionnaire.sys.stdout") as mock_stdout, \
             patch("builtins.input", return_value="c"), \
             patch("builtins.print"):
            mock_stdout.isatty = mock_isatty
            result = _question_selector("prompt", ["A", "B", "C"], default=0)
        assert result == 2  # 'c' selects third option


class TestSuggestQuestions:
    """Test suggest_questions (lines 110-111 area)."""

    def test_deploy_keywords(self):
        from code_agents.agent_system.questionnaire import suggest_questions
        result = suggest_questions("deploy to staging", "jenkins-cicd")
        assert "environment" in result
        assert "deploy_strategy" in result

    def test_no_match(self):
        from code_agents.agent_system.questionnaire import suggest_questions
        result = suggest_questions("hello world", "code-writer")
        assert result == []

    def test_database_keywords(self):
        from code_agents.agent_system.questionnaire import suggest_questions
        result = suggest_questions("migrate the database", "code-writer")
        assert "database" in result

    def test_test_keywords(self):
        from code_agents.agent_system.questionnaire import suggest_questions
        result = suggest_questions("run regression tests", "qa")
        assert "test_scope" in result

    def test_review_keywords(self):
        from code_agents.agent_system.questionnaire import suggest_questions
        result = suggest_questions("review the pull request", "code-reviewer")
        assert "review_depth" in result

    def test_jira_keywords(self):
        from code_agents.agent_system.questionnaire import suggest_questions
        result = suggest_questions("create a jira ticket", "jira-ops")
        assert "jira_type" in result

    def test_rollback_keywords(self):
        from code_agents.agent_system.questionnaire import suggest_questions
        result = suggest_questions("rollback the deploy", "jenkins-cicd")
        assert "rollback_confirm" in result


class TestSessionAnswers:
    """Test get_session_answers and has_been_answered."""

    def test_get_session_answers(self):
        from code_agents.agent_system.questionnaire import get_session_answers
        state = {"_qa_pairs": [{"question": "Q?", "answer": "A"}]}
        assert len(get_session_answers(state)) == 1

    def test_get_session_answers_empty(self):
        from code_agents.agent_system.questionnaire import get_session_answers
        assert get_session_answers({}) == []

    def test_has_been_answered_true(self):
        from code_agents.agent_system.questionnaire import has_been_answered
        state = {"_qa_pairs": [{"question": "Q?", "answer": "A"}]}
        assert has_been_answered(state, "Q?") is True

    def test_has_been_answered_false(self):
        from code_agents.agent_system.questionnaire import has_been_answered
        state = {"_qa_pairs": [{"question": "Q?", "answer": "A"}]}
        assert has_been_answered(state, "Other?") is False


class TestAskQuestionOtherTTY:
    """Cover 'Other' option detail input via tty/panel path."""

    def test_other_option_detail_via_tty(self):
        """When panel works and user selects 'Other', detail is gathered via input()."""
        from code_agents.agent_system.questionnaire import ask_question
        from unittest.mock import patch, MagicMock

        # Options: ["A", "B"] + "Other" => index 2 selects Other
        mock_isatty = MagicMock(return_value=True)
        with patch("code_agents.chat.command_panel.show_panel", return_value=2), \
             patch("code_agents.agent_system.questionnaire.sys.stdout") as mock_stdout, \
             patch("code_agents.agent_system.questionnaire._HAS_QUESTIONARY", False), \
             patch("code_agents.agent_system.questionnaire._HAS_RICH", False), \
             patch("builtins.input", return_value="my custom detail"), \
             patch("builtins.print"):
            mock_stdout.isatty = mock_isatty
            result = ask_question("Pick one", ["A", "B"], allow_other=True, default=0)
        assert result["is_other"] is True
        assert result["answer"] == "my custom detail"

    def test_other_option_eof_in_detail(self):
        """When user presses Ctrl+D during detail input (EOFError)."""
        from code_agents.agent_system.questionnaire import ask_question
        from unittest.mock import patch, MagicMock

        mock_isatty = MagicMock(return_value=True)
        with patch("code_agents.chat.command_panel.show_panel", return_value=2), \
             patch("code_agents.agent_system.questionnaire.sys.stdout") as mock_stdout, \
             patch("code_agents.agent_system.questionnaire._HAS_QUESTIONARY", False), \
             patch("code_agents.agent_system.questionnaire._HAS_RICH", False), \
             patch("builtins.input", side_effect=EOFError), \
             patch("builtins.print"):
            mock_stdout.isatty = mock_isatty
            result = ask_question("Pick one", ["A", "B"], allow_other=True, default=0)
        assert result["is_other"] is True
        assert result["answer"] == "No details provided"

    def test_other_option_keyboard_interrupt_in_detail(self):
        """When user presses Ctrl+C during detail input (KeyboardInterrupt)."""
        from code_agents.agent_system.questionnaire import ask_question
        from unittest.mock import patch, MagicMock

        mock_isatty = MagicMock(return_value=True)
        with patch("code_agents.chat.command_panel.show_panel", return_value=2), \
             patch("code_agents.agent_system.questionnaire.sys.stdout") as mock_stdout, \
             patch("code_agents.agent_system.questionnaire._HAS_QUESTIONARY", False), \
             patch("code_agents.agent_system.questionnaire._HAS_RICH", False), \
             patch("builtins.input", side_effect=KeyboardInterrupt), \
             patch("builtins.print"):
            mock_stdout.isatty = mock_isatty
            result = ask_question("Pick one", ["A", "B"], allow_other=True, default=0)
        assert result["is_other"] is True
        assert result["answer"] == "No details provided"


class TestSafeAsk:
    """Test _safe_ask handles asyncio event loop detection correctly."""

    def test_safe_ask_no_running_loop(self):
        """When no asyncio loop, calls unsafe_ask directly."""
        from code_agents.agent_system.questionnaire import _safe_ask
        from unittest.mock import MagicMock, patch

        mock_question = MagicMock()
        mock_question.unsafe_ask.return_value = "answer"

        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            result = _safe_ask(mock_question)
        assert result == "answer"
        mock_question.unsafe_ask.assert_called_once()

    def test_safe_ask_with_running_loop(self):
        """When asyncio loop is running, runs in thread pool."""
        from code_agents.agent_system.questionnaire import _safe_ask
        from unittest.mock import MagicMock, patch

        mock_question = MagicMock()
        mock_question.unsafe_ask.return_value = "threaded_answer"
        mock_loop = MagicMock()

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            result = _safe_ask(mock_question)
        assert result == "threaded_answer"
        mock_question.unsafe_ask.assert_called()

    def test_safe_ask_none_result(self):
        """_safe_ask passes through None (cancelled)."""
        from code_agents.agent_system.questionnaire import _safe_ask
        from unittest.mock import MagicMock, patch

        mock_question = MagicMock()
        mock_question.unsafe_ask.return_value = None

        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            result = _safe_ask(mock_question)
        assert result is None


class TestPromptIndicesNumeric:
    """prompt_indices_numeric — comma-separated 1-based indices (init section picker)."""

    def test_parses_comma_separated(self):
        from code_agents.agent_system.questionnaire import prompt_indices_numeric
        from unittest.mock import patch

        with patch("builtins.input", return_value="1, 3"):
            r = prompt_indices_numeric("Pick:", ["A", "B", "C"])
        assert r == [0, 2]

    def test_q_aborts(self):
        from code_agents.agent_system.questionnaire import prompt_indices_numeric
        from unittest.mock import patch

        with patch("builtins.input", return_value="q"):
            r = prompt_indices_numeric("Pick:", ["A", "B"])
        assert r == []

    def test_rejects_out_of_range(self):
        from code_agents.agent_system.questionnaire import prompt_indices_numeric
        from unittest.mock import patch

        with patch("builtins.input", side_effect=["99", "1"]):
            r = prompt_indices_numeric("Pick:", ["Only"])
        assert r == [0]
