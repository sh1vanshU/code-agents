"""Tests for context_manager module — Smart Context Window (#48)."""

from unittest.mock import patch

import pytest

from code_agents.core.context_manager import ContextManager, _has_code_block, _get_max_pairs


# ---------------------------------------------------------------------------
# _get_max_pairs
# ---------------------------------------------------------------------------


class TestGetMaxPairs:
    def test_default(self):
        with patch.dict("os.environ", {}, clear=False):
            # Remove env var if set
            import os
            os.environ.pop("CODE_AGENTS_CONTEXT_WINDOW", None)
            assert _get_max_pairs() == 10

    def test_custom_value(self):
        with patch.dict("os.environ", {"CODE_AGENTS_CONTEXT_WINDOW": "10"}):
            assert _get_max_pairs() == 10

    def test_minimum_clamped_to_1(self):
        with patch.dict("os.environ", {"CODE_AGENTS_CONTEXT_WINDOW": "0"}):
            assert _get_max_pairs() == 1

    def test_invalid_value_falls_back(self):
        with patch.dict("os.environ", {"CODE_AGENTS_CONTEXT_WINDOW": "abc"}):
            assert _get_max_pairs() == 5


# ---------------------------------------------------------------------------
# _has_code_block
# ---------------------------------------------------------------------------


class TestHasCodeBlock:
    def test_with_code_block(self):
        assert _has_code_block({"content": "Here is code:\n```python\nprint('hi')\n```"})

    def test_without_code_block(self):
        assert not _has_code_block({"content": "Just plain text"})

    def test_empty_content(self):
        assert not _has_code_block({"content": ""})

    def test_none_content(self):
        assert not _has_code_block({"content": None})

    def test_missing_content_key(self):
        assert not _has_code_block({"role": "user"})


# ---------------------------------------------------------------------------
# ContextManager.__init__
# ---------------------------------------------------------------------------


class TestContextManagerInit:
    def test_explicit_max_pairs(self):
        cm = ContextManager(max_pairs=3)
        assert cm.max_pairs == 3

    def test_env_default(self):
        with patch.dict("os.environ", {"CODE_AGENTS_CONTEXT_WINDOW": "7"}):
            cm = ContextManager()
            assert cm.max_pairs == 7


# ---------------------------------------------------------------------------
# ContextManager.trim_messages — no trimming cases
# ---------------------------------------------------------------------------


class TestTrimMessagesNoOp:
    def test_empty_messages(self):
        cm = ContextManager(max_pairs=5)
        assert cm.trim_messages([]) == []

    def test_single_user_message(self):
        msgs = [{"role": "user", "content": "Hello"}]
        cm = ContextManager(max_pairs=5)
        assert cm.trim_messages(msgs) == msgs

    def test_within_window(self):
        msgs = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "Great!"},
        ]
        cm = ContextManager(max_pairs=5)
        result = cm.trim_messages(msgs)
        assert result == msgs

    def test_exact_window_size(self):
        msgs = [{"role": "system", "content": "sys"}]
        for i in range(3):
            msgs.append({"role": "user", "content": f"Q{i}"})
            msgs.append({"role": "assistant", "content": f"A{i}"})
        cm = ContextManager(max_pairs=3)
        result = cm.trim_messages(msgs)
        assert result == msgs

    def test_system_only_messages(self):
        msgs = [{"role": "system", "content": "sys prompt"}]
        cm = ContextManager(max_pairs=5)
        result = cm.trim_messages(msgs)
        assert result == msgs


# ---------------------------------------------------------------------------
# ContextManager.trim_messages — trimming cases
# ---------------------------------------------------------------------------


class TestTrimMessagesTrimming:
    def _make_conversation(self, n_pairs: int, system: bool = True):
        """Helper to build a conversation with n user+assistant pairs."""
        msgs = []
        if system:
            msgs.append({"role": "system", "content": "You are a helpful assistant"})
        for i in range(n_pairs):
            msgs.append({"role": "user", "content": f"Question {i} about topic_{i}"})
            msgs.append({"role": "assistant", "content": f"Answer {i} about topic_{i}"})
        return msgs

    def test_trims_excess_pairs(self):
        msgs = self._make_conversation(10)
        cm = ContextManager(max_pairs=3)
        result = cm.trim_messages(msgs)
        # Should have: system + first pair + summary + last 3 pairs
        # Count user messages in result (non-system)
        user_msgs = [m for m in result if m["role"] == "user"]
        # First user + last 3 users = 4
        assert len(user_msgs) == 4

    def test_system_messages_always_kept(self):
        msgs = self._make_conversation(10)
        cm = ContextManager(max_pairs=2)
        result = cm.trim_messages(msgs)
        system_msgs = [m for m in result if m["role"] == "system"]
        # Original system + trimming summary
        assert len(system_msgs) >= 1
        assert system_msgs[0]["content"] == "You are a helpful assistant"

    def test_first_user_message_preserved(self):
        msgs = self._make_conversation(10)
        cm = ContextManager(max_pairs=2)
        result = cm.trim_messages(msgs)
        non_system = [m for m in result if m["role"] != "system"]
        assert non_system[0]["role"] == "user"
        assert non_system[0]["content"] == "Question 0 about topic_0"

    def test_last_n_pairs_preserved(self):
        msgs = self._make_conversation(10)
        cm = ContextManager(max_pairs=3)
        result = cm.trim_messages(msgs)
        non_system = [m for m in result if m["role"] != "system"]
        # Last message should be the final assistant response
        assert non_system[-1]["content"] == "Answer 9 about topic_9"
        # Second to last should be last user message
        assert non_system[-2]["content"] == "Question 9 about topic_9"

    def test_summary_message_inserted(self):
        msgs = self._make_conversation(10)
        cm = ContextManager(max_pairs=2)
        result = cm.trim_messages(msgs)
        summary_msgs = [m for m in result if m["role"] == "system" and "Context trimmed" in (m.get("content") or "")]
        assert len(summary_msgs) == 1
        assert "earlier messages removed" in summary_msgs[0]["content"]

    def test_summary_contains_topic_keywords(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Tell me about kubernetes deployment"},
            {"role": "assistant", "content": "Kubernetes deployments use pods"},
            {"role": "user", "content": "How about jenkins pipelines?"},
            {"role": "assistant", "content": "Jenkins pipelines are CI/CD tools"},
            {"role": "user", "content": "And docker containers?"},
            {"role": "assistant", "content": "Docker containers are lightweight"},
            {"role": "user", "content": "Final question about testing"},
            {"role": "assistant", "content": "Testing is important"},
        ]
        cm = ContextManager(max_pairs=1)
        result = cm.trim_messages(msgs)
        summary_msgs = [m for m in result if m["role"] == "system" and "Context trimmed" in (m.get("content") or "")]
        assert len(summary_msgs) == 1
        summary = summary_msgs[0]["content"].lower()
        # Should contain at least some topic keywords from trimmed messages
        assert "key topics discussed:" in summary

    def test_code_block_messages_preserved(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Here is code:\n```python\ndef foo():\n    pass\n```"},
            {"role": "assistant", "content": "That code looks good"},
            {"role": "user", "content": "Plain question 1"},
            {"role": "assistant", "content": "Plain answer 1"},
            {"role": "user", "content": "Plain question 2"},
            {"role": "assistant", "content": "Plain answer 2"},
            {"role": "user", "content": "Latest question"},
            {"role": "assistant", "content": "Latest answer"},
        ]
        cm = ContextManager(max_pairs=2)
        result = cm.trim_messages(msgs)
        # The code block message should be preserved even though it's outside the window
        code_msgs = [m for m in result if "```python" in (m.get("content") or "")]
        assert len(code_msgs) == 1

    def test_no_trimming_without_excess(self):
        msgs = self._make_conversation(5)
        cm = ContextManager(max_pairs=5)
        result = cm.trim_messages(msgs)
        assert len(result) == len(msgs)

    def test_max_pairs_1(self):
        msgs = self._make_conversation(5)
        cm = ContextManager(max_pairs=1)
        result = cm.trim_messages(msgs)
        non_system = [m for m in result if m["role"] != "system"]
        user_msgs = [m for m in non_system if m["role"] == "user"]
        # First user + last 1 user = 2
        assert len(user_msgs) == 2


# ---------------------------------------------------------------------------
# ContextManager._extract_topics
# ---------------------------------------------------------------------------


class TestExtractTopics:
    def test_basic_extraction(self):
        cm = ContextManager(max_pairs=5)
        msgs = [
            {"role": "user", "content": "Tell me about kubernetes deployment strategies"},
            {"role": "assistant", "content": "Kubernetes deployment includes rolling updates"},
        ]
        topics = cm._extract_topics(msgs)
        assert len(topics) > 0
        assert "kubernetes" in topics

    def test_filters_stop_words(self):
        cm = ContextManager(max_pairs=5)
        msgs = [{"role": "user", "content": "the quick brown fox jumps over the lazy dog"}]
        topics = cm._extract_topics(msgs)
        assert "the" not in topics
        assert "over" not in topics

    def test_filters_short_words(self):
        cm = ContextManager(max_pairs=5)
        msgs = [{"role": "user", "content": "go is a programming language by Google"}]
        topics = cm._extract_topics(msgs)
        # "go", "is", "a", "by" are too short or stop words
        assert "go" not in topics
        assert "is" not in topics

    def test_ignores_code_blocks(self):
        cm = ContextManager(max_pairs=5)
        msgs = [{"role": "user", "content": "Here:\n```\nvariable_inside_code = 1\n```\nkubernetes topic"}]
        topics = cm._extract_topics(msgs)
        assert "variable_inside_code" not in topics

    def test_empty_messages(self):
        cm = ContextManager(max_pairs=5)
        assert cm._extract_topics([]) == []

    def test_max_8_topics(self):
        cm = ContextManager(max_pairs=5)
        msgs = [{"role": "user", "content": " ".join(f"topic{i}" for i in range(20))}]
        topics = cm._extract_topics(msgs)
        assert len(topics) <= 8


# ---------------------------------------------------------------------------
# ContextManager._build_summary
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_with_topics(self):
        cm = ContextManager(max_pairs=5)
        summary = cm._build_summary(10, ["kubernetes", "deployment", "testing"])
        assert "10 earlier messages removed" in summary
        assert "kubernetes, deployment, testing" in summary

    def test_no_topics(self):
        cm = ContextManager(max_pairs=5)
        summary = cm._build_summary(5, [])
        assert "general discussion" in summary

    def test_single_topic(self):
        cm = ContextManager(max_pairs=5)
        summary = cm._build_summary(3, ["jenkins"])
        assert "jenkins" in summary


# ---------------------------------------------------------------------------
# Integration with stream.build_prompt
# ---------------------------------------------------------------------------


class TestBuildPromptIntegration:
    def test_small_conversation_unchanged(self):
        """build_prompt should pass through small conversations untouched."""
        from code_agents.core.models import Message
        from code_agents.core.stream import build_prompt

        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi!"),
            Message(role="user", content="How are you?"),
        ]
        result = build_prompt(messages)
        assert "Human: Hello" in result
        assert "Assistant: Hi!" in result
        assert "Human: How are you?" in result

    def test_large_conversation_trimmed(self):
        """build_prompt should trim large conversations."""
        from code_agents.core.models import Message
        from code_agents.core.stream import build_prompt

        messages = [Message(role="system", content="You are helpful")]
        for i in range(20):
            messages.append(Message(role="user", content=f"Question {i}"))
            messages.append(Message(role="assistant", content=f"Answer {i}"))

        with patch.dict("os.environ", {"CODE_AGENTS_CONTEXT_WINDOW": "3"}):
            result = build_prompt(messages)
        # Should contain the last few messages
        assert "Question 19" in result
        assert "Answer 19" in result
        # Should contain the first user message
        assert "Question 0" in result

    def test_single_message_still_works(self):
        """Single user message should still return just the content."""
        from code_agents.core.models import Message
        from code_agents.core.stream import build_prompt

        messages = [Message(role="user", content="Hello")]
        assert build_prompt(messages) == "Hello"

    def test_empty_messages_still_works(self):
        """Empty messages should still return empty string."""
        from code_agents.core.stream import build_prompt

        assert build_prompt([]) == ""


# ---------------------------------------------------------------------------
# Skill body compaction
# ---------------------------------------------------------------------------


class TestSkillCompaction:
    """Skill-loaded messages should be compacted when trimmed."""

    def test_skill_body_not_preserved_as_code_block(self):
        """Skill bodies contain ```bash but should NOT be preserved like code blocks."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Build pg-acquiring-biz"},
            {"role": "assistant", "content": "Loading build skill... [SKILL:build]"},
            {"role": "user", "content": "[Skill loaded: build]\n\n## Workflow\n\n```bash\ncurl -sS ...\n```\n\nProceed."},
            {"role": "assistant", "content": "Running build..."},
            {"role": "user", "content": "Now deploy"},
            {"role": "assistant", "content": "Deploying..."},
            {"role": "user", "content": "Check status"},
            {"role": "assistant", "content": "Status is healthy"},
            {"role": "user", "content": "Final question"},
            {"role": "assistant", "content": "Final answer"},
        ]
        cm = ContextManager(max_pairs=2)
        result = cm.trim_messages(msgs)
        # Full skill body (with ```bash) should NOT be preserved in the result
        skill_bodies = [m for m in result if "## Workflow" in (m.get("content") or "")]
        assert len(skill_bodies) == 0, "Full skill body should be trimmed away"
        # Verify the skill ```bash block is NOT kept as a code block
        code_skill = [m for m in result if "curl -sS" in (m.get("content") or "") and "Skill" not in (m.get("content") or "")]
        assert len(code_skill) == 0, "Skill curl example should not be preserved"

    def test_recent_skill_not_compacted(self):
        """Skill in the tail (recent messages) should NOT be compacted."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "[Skill loaded: deploy]\n\n## Deploy Workflow\n\n```bash\ncurl ...\n```"},
            {"role": "assistant", "content": "Deploying now..."},
        ]
        cm = ContextManager(max_pairs=3)
        result = cm.trim_messages(msgs)
        # Within window — nothing should be compacted
        skill_msgs = [m for m in result if "[Skill loaded: deploy]" in (m.get("content") or "")]
        assert len(skill_msgs) == 1, "Recent skill should NOT be compacted"

    def test_skill_code_blocks_not_preserved_when_trimmed(self):
        """_has_code_block should return False for skill-loaded messages."""
        from code_agents.core.context_manager import _has_code_block
        skill_msg = {"role": "user", "content": "[Skill loaded: build]\n\n```bash\ncurl -sS ...\n```"}
        assert _has_code_block(skill_msg) is False

    def test_normal_code_blocks_still_preserved(self):
        """Regular code block messages should still be preserved."""
        from code_agents.core.context_manager import _has_code_block
        code_msg = {"role": "user", "content": "Here's code:\n```python\ndef foo(): pass\n```"}
        assert _has_code_block(code_msg) is True
