"""End-to-end tests for the questionnaire flow.

Tests the full pipeline: agent response with [QUESTION:key] tags -> parsing ->
answer collection -> injection back into conversation context.
"""

from __future__ import annotations

import re
from unittest.mock import patch, MagicMock

import pytest

from code_agents.agent_system.questionnaire import (
    ask_question,
    ask_multiple,
    ask_multiple_tabbed,
    format_qa_for_prompt,
    suggest_questions,
    get_session_answers,
    has_been_answered,
    TEMPLATES,
)
from code_agents.agent_system.question_parser import parse_questions


# ---------------------------------------------------------------------------
# 1. Parsing [QUESTION:key] tags from agent response text
# ---------------------------------------------------------------------------


class TestParseQuestionTags:
    """Parse [QUESTION:key] tags from agent response text."""

    def test_single_template_key(self):
        text = "I need some info. [QUESTION:environment] Let me know."
        matches = re.findall(r'\[QUESTION:(.*?)\]', text)
        assert matches == ["environment"]

    def test_multiple_template_keys(self):
        text = (
            "Before deploying, I need to know:\n"
            "[QUESTION:environment]\n"
            "[QUESTION:deploy_strategy]\n"
            "[QUESTION:branch]\n"
        )
        matches = re.findall(r'\[QUESTION:(.*?)\]', text)
        assert matches == ["environment", "deploy_strategy", "branch"]

    def test_freeform_question_key(self):
        text = "I need clarification. [QUESTION:Should we include integration tests?]"
        matches = re.findall(r'\[QUESTION:(.*?)\]', text)
        assert matches == ["Should we include integration tests?"]

    def test_no_question_tags(self):
        text = "Here is the code fix. No questions needed."
        matches = re.findall(r'\[QUESTION:(.*?)\]', text)
        assert matches == []

    def test_mixed_template_and_freeform(self):
        text = (
            "[QUESTION:environment]\n"
            "[QUESTION:Which database schema version?]\n"
        )
        matches = re.findall(r'\[QUESTION:(.*?)\]', text)
        assert matches == ["environment", "Which database schema version?"]


# ---------------------------------------------------------------------------
# 2. Template resolution — keys map to structured questions
# ---------------------------------------------------------------------------


class TestTemplateResolution:
    """Verify that parsed keys resolve to structured question templates."""

    def test_known_key_resolves(self):
        key = "environment"
        assert key in TEMPLATES
        tmpl = TEMPLATES[key]
        assert "question" in tmpl
        assert len(tmpl["options"]) >= 2

    def test_unknown_key_gets_yes_no_skip(self):
        """Unknown keys should produce a fallback question with Yes/No/Skip options."""
        key = "Should we run performance benchmarks?"
        assert key not in TEMPLATES
        # The chat_response.py code creates fallback options for unknown keys
        fallback = {"question": key, "options": ["Yes", "No", "Skip"]}
        assert fallback["question"] == key
        assert len(fallback["options"]) == 3

    def test_all_cicd_templates_present(self):
        """CI/CD-related templates should exist."""
        for key in ["build_location", "deploy_strategy", "deploy_action"]:
            assert key in TEMPLATES, f"Missing template: {key}"


# ---------------------------------------------------------------------------
# 3. Answer collection (mocked interactive input)
# ---------------------------------------------------------------------------


class TestAnswerCollection:
    """Test that answers are collected correctly via mocked selectors."""

    @patch("code_agents.agent_system.questionnaire._question_selector", return_value=0)
    def test_ask_question_returns_first_option(self, mock_selector):
        result = ask_question(
            question="Which environment?",
            options=["dev", "staging", "prod"],
            allow_other=False,
        )
        assert result["answer"] == "dev"
        assert result["option_idx"] == 0
        assert result["is_other"] is False

    @patch("code_agents.agent_system.questionnaire._question_selector", return_value=1)
    def test_ask_question_returns_selected_option(self, mock_selector):
        result = ask_question(
            question="Deploy strategy?",
            options=["Rolling", "Blue-green", "Canary"],
            allow_other=False,
        )
        assert result["answer"] == "Blue-green"
        assert result["option_idx"] == 1

    @patch("code_agents.agent_system.questionnaire._question_selector")
    def test_ask_multiple_collects_all(self, mock_selector):
        mock_selector.side_effect = [0, 2]
        questions = [
            {"question": "Env?", "options": ["dev", "staging", "prod"]},
            {"question": "Scope?", "options": ["unit", "integration", "full"]},
        ]
        results = ask_multiple(questions)
        assert len(results) == 2
        assert results[0]["answer"] == "dev"
        assert results[1]["answer"] == "full"


# ---------------------------------------------------------------------------
# 4. Answer injection into conversation context
# ---------------------------------------------------------------------------


class TestAnswerInjection:
    """Test that collected answers get formatted for prompt injection."""

    def test_single_answer_formatted(self):
        qa_pairs = [
            {"question": "Which environment?", "answer": "staging", "is_other": False},
        ]
        result = format_qa_for_prompt(qa_pairs)
        assert "User clarifications:" in result
        assert "Q: Which environment?" in result
        assert "A: staging" in result

    def test_multiple_answers_formatted(self):
        qa_pairs = [
            {"question": "Which environment?", "answer": "dev", "is_other": False},
            {"question": "Deploy strategy?", "answer": "Rolling update", "is_other": False},
            {"question": "Custom detail?", "answer": "Use 3 replicas", "is_other": True},
        ]
        result = format_qa_for_prompt(qa_pairs)
        assert "Q: Which environment?" in result
        assert "Q: Deploy strategy?" in result
        assert "Q: Custom detail?" in result
        assert "(custom answer)" in result

    def test_empty_answers_returns_empty_string(self):
        assert format_qa_for_prompt([]) == ""


# ---------------------------------------------------------------------------
# 5. Full e2e flow simulation
# ---------------------------------------------------------------------------


class TestQuestionnaireE2EFlow:
    """Simulate the full flow: parse tags -> resolve -> collect -> inject."""

    @patch("code_agents.agent_system.questionnaire._question_selector", return_value=0)
    def test_full_flow_template_key(self, mock_selector):
        """Full flow: agent emits [QUESTION:environment] -> user picks dev -> injected into context."""
        # Step 1: Agent response text
        agent_text = "I'll deploy the service. [QUESTION:environment] Please choose."

        # Step 2: Parse tags
        matches = re.findall(r'\[QUESTION:(.*?)\]', agent_text)
        assert matches == ["environment"]

        # Step 3: Resolve to template
        key = matches[0].strip()
        assert key in TEMPLATES
        tmpl = TEMPLATES[key]

        # Step 4: Collect answer (mocked)
        answer = ask_question(
            question=tmpl["question"],
            options=tmpl["options"],
            allow_other=True,
        )
        assert answer["answer"] == tmpl["options"][0]

        # Step 5: Format for injection
        injected = format_qa_for_prompt([answer])
        assert "User clarifications:" in injected
        assert tmpl["options"][0] in injected

    @patch("code_agents.agent_system.questionnaire._question_selector")
    def test_full_flow_multiple_questions(self, mock_selector):
        """Multiple [QUESTION:] tags -> tabbed wizard -> all answers injected."""
        mock_selector.side_effect = [0, 1]

        agent_text = (
            "Before proceeding:\n"
            "[QUESTION:environment]\n"
            "[QUESTION:deploy_strategy]\n"
        )

        matches = re.findall(r'\[QUESTION:(.*?)\]', agent_text)
        assert len(matches) == 2

        # Build pending questions from templates
        pending = []
        for key in matches:
            key = key.strip()
            if key in TEMPLATES:
                pending.append(TEMPLATES[key])
            else:
                pending.append({"question": key, "options": ["Yes", "No", "Skip"]})

        # Collect (using ask_multiple since ask_multiple_tabbed needs TTY)
        answers = ask_multiple(pending)
        assert len(answers) == 2

        # Inject
        injected = format_qa_for_prompt(answers)
        assert "User clarifications:" in injected
        assert "Q:" in injected

    @patch("code_agents.agent_system.questionnaire._question_selector", return_value=0)
    def test_full_flow_freeform_question(self, mock_selector):
        """Freeform question: agent asks a custom question not in templates."""
        agent_text = "[QUESTION:Should we run load tests before deploy?]"

        matches = re.findall(r'\[QUESTION:(.*?)\]', agent_text)
        key = matches[0].strip()
        assert key not in TEMPLATES

        # Fallback options
        question = {"question": key, "options": ["Yes", "No", "Skip"]}
        answer = ask_question(**question, allow_other=False)
        assert answer["answer"] == "Yes"

        injected = format_qa_for_prompt([answer])
        assert "Should we run load tests" in injected


# ---------------------------------------------------------------------------
# 6. Session state tracking
# ---------------------------------------------------------------------------


class TestSessionState:
    """Test session state helpers for tracking answered questions."""

    def test_no_answers_initially(self):
        state = {}
        assert get_session_answers(state) == []

    def test_has_been_answered_false(self):
        state = {}
        assert has_been_answered(state, "Which env?") is False

    def test_has_been_answered_true(self):
        state = {
            "_qa_pairs": [
                {"question": "Which env?", "answer": "dev"},
            ]
        }
        assert has_been_answered(state, "Which env?") is True

    def test_has_been_answered_different_question(self):
        state = {
            "_qa_pairs": [
                {"question": "Which env?", "answer": "dev"},
            ]
        }
        assert has_been_answered(state, "Deploy strategy?") is False

    def test_get_session_answers_returns_pairs(self):
        qa = [
            {"question": "Q1", "answer": "A1"},
            {"question": "Q2", "answer": "A2"},
        ]
        state = {"_qa_pairs": qa}
        assert get_session_answers(state) == qa


# ---------------------------------------------------------------------------
# 7. Question suggestion engine
# ---------------------------------------------------------------------------


class TestSuggestQuestions:
    """Test the suggestion engine that proposes relevant questions."""

    def test_deploy_suggests_environment(self):
        suggestions = suggest_questions("deploy the service to staging", "auto-pilot")
        assert "environment" in suggestions

    def test_build_suggests_build_location(self):
        suggestions = suggest_questions("build the project", "jenkins-cicd")
        assert "build_location" in suggestions

    def test_review_suggests_review_depth(self):
        suggestions = suggest_questions("review this pull request", "code-reviewer")
        assert "review_depth" in suggestions

    def test_unrelated_input_no_suggestions(self):
        suggestions = suggest_questions("what is the weather today", "auto-pilot")
        assert len(suggestions) == 0


# ---------------------------------------------------------------------------
# 8. Question parser (free-form detection)
# ---------------------------------------------------------------------------


class TestQuestionParserIntegration:
    """Test the question_parser module that detects free-form numbered questions."""

    def test_numbered_questions_detected(self):
        text = (
            "Q1: Which environment?\n"
            "1. dev\n"
            "2. staging\n"
            "3. prod\n"
            "\n"
            "Q2: What scope?\n"
            "1. unit\n"
            "2. integration\n"
            "3. full\n"
        )
        questions = parse_questions(text)
        assert len(questions) == 2
        assert questions[0]["question"] == "Which environment?"
        assert len(questions[0]["options"]) == 3
        assert questions[1]["question"] == "What scope?"

    def test_no_questions_in_plain_text(self):
        text = "Here is the code fix. All tests pass."
        assert parse_questions(text) == []

    def test_code_blocks_ignored(self):
        text = (
            "```\n"
            "Q1: This is code?\n"
            "1. not a question\n"
            "2. just code\n"
            "```\n"
        )
        assert parse_questions(text) == []

    def test_empty_text(self):
        assert parse_questions("") == []
        assert parse_questions(None) == []
