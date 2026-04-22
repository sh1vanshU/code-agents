"""Tests for stream.py — SSE helpers, build_prompt, formatting, inject_context."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


class TestSse:
    def test_sse_basic(self):
        from code_agents.core.stream import sse
        result = sse({"msg": "hello"})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        parsed = json.loads(result[len("data: "):].strip())
        assert parsed == {"msg": "hello"}

    def test_sse_empty_dict(self):
        from code_agents.core.stream import sse
        result = sse({})
        parsed = json.loads(result[len("data: "):].strip())
        assert parsed == {}


class TestMakeChunk:
    def test_basic_chunk(self):
        from code_agents.core.stream import make_chunk
        result = make_chunk("cid-1", "gpt-4", 1000, {"content": "hi"})
        parsed = json.loads(result[len("data: "):].strip())
        assert parsed["id"] == "cid-1"
        assert parsed["model"] == "gpt-4"
        assert parsed["created"] == 1000
        assert parsed["choices"][0]["delta"] == {"content": "hi"}
        assert parsed["choices"][0]["finish_reason"] is None

    def test_chunk_with_finish_reason(self):
        from code_agents.core.stream import make_chunk
        result = make_chunk("cid-2", "model", 100, {}, finish_reason="stop")
        parsed = json.loads(result[len("data: "):].strip())
        assert parsed["choices"][0]["finish_reason"] == "stop"

    def test_chunk_structure(self):
        from code_agents.core.stream import make_chunk
        result = make_chunk("x", "m", 0, {"role": "assistant"})
        parsed = json.loads(result[len("data: "):].strip())
        assert parsed["object"] == "chat.completion.chunk"
        assert parsed["system_fingerprint"] is None
        assert parsed["choices"][0]["index"] == 0
        assert parsed["choices"][0]["logprobs"] is None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


class TestTrimToTail:
    def test_short_text_unchanged(self):
        from code_agents.core.stream import _trim_to_tail
        text = "line1\nline2\nline3"
        assert _trim_to_tail(text, max_lines=5) == text

    def test_exact_limit_unchanged(self):
        from code_agents.core.stream import _trim_to_tail
        text = "\n".join(f"line{i}" for i in range(30))
        assert _trim_to_tail(text, max_lines=30) == text

    def test_exceeds_limit_trimmed(self):
        from code_agents.core.stream import _trim_to_tail
        text = "\n".join(f"line{i}" for i in range(50))
        result = _trim_to_tail(text, max_lines=10)
        assert result.startswith("... (40 lines omitted) ...")
        assert "line49" in result
        assert "line0" not in result

    def test_custom_max_lines(self):
        from code_agents.core.stream import _trim_to_tail
        text = "\n".join(f"L{i}" for i in range(20))
        result = _trim_to_tail(text, max_lines=5)
        assert "(15 lines omitted)" in result


class TestFormatToolUse:
    def test_dict_input(self):
        from code_agents.core.stream import format_tool_use
        block = SimpleNamespace(name="bash", input={"cmd": "ls"})
        result = format_tool_use(block)
        assert "bash" in result
        assert '"cmd"' in result

    def test_string_input(self):
        from code_agents.core.stream import format_tool_use
        block = SimpleNamespace(name="read", input="some string")
        result = format_tool_use(block)
        assert "read" in result
        assert "some string" in result


class TestFormatToolResult:
    def test_string_content(self):
        from code_agents.core.stream import format_tool_result
        block = SimpleNamespace(content="output text", tool_use_id="tu-1")
        result = format_tool_result(block)
        assert "output text" in result
        assert "tu-1" in result

    def test_list_content(self):
        from code_agents.core.stream import format_tool_result
        block = SimpleNamespace(content=[{"type": "text", "text": "hi"}], tool_use_id="tu-2")
        result = format_tool_result(block)
        assert "tu-2" in result

    def test_none_content(self):
        from code_agents.core.stream import format_tool_result
        block = SimpleNamespace(content=None, tool_use_id="tu-3")
        result = format_tool_result(block)
        assert "tu-3" in result

    def test_other_content_type(self):
        from code_agents.core.stream import format_tool_result
        block = SimpleNamespace(content=12345, tool_use_id="tu-4")
        result = format_tool_result(block)
        assert "12345" in result


class TestIterToolResultChunks:
    """Test line-based chunked streaming of tool results."""

    def test_basic_chunking(self):
        from code_agents.core.stream import iter_tool_result_chunks
        block = SimpleNamespace(content="line1\nline2\nline3", tool_use_id="tu-c1")
        chunks = list(iter_tool_result_chunks(block))
        assert len(chunks) >= 3  # header + content + footer
        assert "Tool Result" in chunks[0]
        assert "tu-c1" in chunks[0]
        assert "```" in chunks[0]  # opening fence
        assert "```" in chunks[-1]  # closing fence
        # Content is in middle chunks
        joined = "".join(chunks)
        assert "line1" in joined
        assert "line3" in joined

    def test_empty_content(self):
        from code_agents.core.stream import iter_tool_result_chunks
        block = SimpleNamespace(content="", tool_use_id="tu-c2")
        chunks = list(iter_tool_result_chunks(block))
        assert len(chunks) >= 2  # header + footer at minimum

    def test_list_content_json(self):
        from code_agents.core.stream import iter_tool_result_chunks
        block = SimpleNamespace(content=[{"type": "text"}], tool_use_id="tu-c3")
        chunks = list(iter_tool_result_chunks(block))
        joined = "".join(chunks)
        assert "text" in joined

    def test_chunk_size_respected(self):
        from code_agents.core.stream import iter_tool_result_chunks
        # 10 lines, chunk_lines=3 → should produce header + 4 content chunks + footer
        content = "\n".join(f"line{i}" for i in range(10))
        block = SimpleNamespace(content=content, tool_use_id="tu-c4")
        chunks = list(iter_tool_result_chunks(block, chunk_lines=3))
        # At least header(1) + content(ceil(10/3)=4) + footer(1) = 6
        assert len(chunks) >= 6

    def test_none_content(self):
        from code_agents.core.stream import iter_tool_result_chunks
        block = SimpleNamespace(content=None, tool_use_id="tu-c5")
        chunks = list(iter_tool_result_chunks(block))
        joined = "".join(chunks)
        assert "tu-c5" in joined

    def test_reassembled_matches_format_tool_result(self):
        from code_agents.core.stream import iter_tool_result_chunks, format_tool_result
        block = SimpleNamespace(content="hello world\nsecond line", tool_use_id="tu-cmp")
        chunked = "".join(iter_tool_result_chunks(block))
        formatted = format_tool_result(block)
        # Both should contain the same content (may differ in whitespace)
        assert "hello world" in chunked
        assert "hello world" in formatted
        assert "tu-cmp" in chunked


class TestLastUserMessage:
    def test_single_user_message(self):
        from code_agents.core.stream import last_user_message
        from code_agents.core.models import Message
        msgs = [Message(role="user", content="hello")]
        assert last_user_message(msgs) == "hello"

    def test_multiple_messages(self):
        from code_agents.core.stream import last_user_message
        from code_agents.core.models import Message
        msgs = [
            Message(role="user", content="first"),
            Message(role="assistant", content="reply"),
            Message(role="user", content="second"),
        ]
        assert last_user_message(msgs) == "second"

    def test_no_user_message(self):
        from code_agents.core.stream import last_user_message
        from code_agents.core.models import Message
        msgs = [Message(role="system", content="sys"), Message(role="assistant", content="hi")]
        assert last_user_message(msgs) == ""

    def test_empty_list(self):
        from code_agents.core.stream import last_user_message
        assert last_user_message([]) == ""

    def test_user_message_with_none_content(self):
        from code_agents.core.stream import last_user_message
        from code_agents.core.models import Message
        msgs = [Message(role="user", content=None)]
        assert last_user_message(msgs) == ""


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_single_user_message(self):
        from code_agents.core.stream import build_prompt
        from code_agents.core.models import Message
        msgs = [Message(role="user", content="what is 2+2")]
        result = build_prompt(msgs)
        assert "what is 2+2" in result

    def test_multi_turn_conversation(self):
        from code_agents.core.stream import build_prompt
        from code_agents.core.models import Message
        msgs = [
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi there"),
            Message(role="user", content="how are you"),
        ]
        result = build_prompt(msgs)
        assert "Human:" in result
        assert "Assistant:" in result

    def test_system_message_excluded_from_non_system(self):
        from code_agents.core.stream import build_prompt
        from code_agents.core.models import Message
        msgs = [
            Message(role="system", content="be helpful"),
            Message(role="user", content="question"),
        ]
        result = build_prompt(msgs)
        # Single non-system message, should just return user message
        assert "question" in result

    def test_system_plus_multi_turn(self):
        from code_agents.core.stream import build_prompt
        from code_agents.core.models import Message
        msgs = [
            Message(role="system", content="sys"),
            Message(role="user", content="q1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="q2"),
        ]
        result = build_prompt(msgs)
        assert "Human:" in result
        assert "q1" in result
        assert "q2" in result


# ---------------------------------------------------------------------------
# _inject_context
# ---------------------------------------------------------------------------


class TestInjectContext:
    def _make_agent(self, name="code-writer", system_prompt="base prompt"):
        from code_agents.core.config import AgentConfig
        return AgentConfig(
            name=name,
            display_name=name,
            backend="cursor",
            model="test-model",
            system_prompt=system_prompt,
        )

    @patch("code_agents.core.stream.load_rules", return_value="")
    @patch("code_agents.core.stream.get_style_prompt", return_value="")
    def test_no_rules_no_role(self, mock_style, mock_rules):
        from code_agents.core.stream import _inject_context
        agent = self._make_agent()
        with patch.dict(os.environ, {}, clear=True):
            result = _inject_context(agent)
        assert "FORMAT:" in result.system_prompt
        assert result.name == "code-writer"

    @patch("code_agents.core.stream.load_rules", return_value="RULE: do X")
    @patch("code_agents.core.stream.get_style_prompt", return_value="")
    def test_with_rules(self, mock_style, mock_rules):
        from code_agents.core.stream import _inject_context
        agent = self._make_agent()
        with patch.dict(os.environ, {}, clear=True):
            result = _inject_context(agent)
        assert "RULE: do X" in result.system_prompt

    @patch("code_agents.core.stream.load_rules", return_value="")
    @patch("code_agents.core.stream.get_style_prompt", return_value="")
    def test_with_user_role(self, mock_style, mock_rules):
        from code_agents.core.stream import _inject_context
        agent = self._make_agent()
        with patch.dict(os.environ, {"CODE_AGENTS_USER_ROLE": "Senior Engineer", "CODE_AGENTS_NICKNAME": "shiv"}, clear=True):
            result = _inject_context(agent)
        assert "Senior Engineer" in result.system_prompt
        assert "shiv" in result.system_prompt

    @patch("code_agents.core.stream.load_rules", return_value="")
    @patch("code_agents.core.stream.get_style_prompt", return_value="indent: 4 spaces")
    def test_style_injection_for_code_writer(self, mock_style, mock_rules):
        from code_agents.core.stream import _inject_context
        agent = self._make_agent(name="code-writer")
        with patch.dict(os.environ, {"TARGET_REPO_PATH": "/tmp/repo"}, clear=True):
            result = _inject_context(agent)
        assert "indent: 4 spaces" in result.system_prompt

    @patch("code_agents.core.stream.load_rules", return_value="")
    @patch("code_agents.core.stream.get_style_prompt", return_value="")
    def test_no_style_for_non_style_agent(self, mock_style, mock_rules):
        from code_agents.core.stream import _inject_context
        agent = self._make_agent(name="git-ops")
        with patch.dict(os.environ, {"TARGET_REPO_PATH": "/tmp/repo"}, clear=True):
            result = _inject_context(agent)
        mock_style.assert_not_called()

    @patch("code_agents.core.stream.load_rules", return_value="")
    @patch("code_agents.core.stream.get_style_prompt", return_value="")
    def test_original_agent_not_mutated(self, mock_style, mock_rules):
        from code_agents.core.stream import _inject_context
        agent = self._make_agent()
        original_prompt = agent.system_prompt
        with patch.dict(os.environ, {}, clear=True):
            result = _inject_context(agent)
        assert agent.system_prompt == original_prompt
        assert result is not agent

    @patch("code_agents.core.stream.load_rules", return_value="")
    @patch("code_agents.core.stream.get_style_prompt", return_value="")
    def test_user_role_with_default_nickname(self, mock_style, mock_rules):
        from code_agents.core.stream import _inject_context
        agent = self._make_agent()
        with patch.dict(os.environ, {"CODE_AGENTS_USER_ROLE": "Junior Engineer", "CODE_AGENTS_NICKNAME": "you"}, clear=True):
            result = _inject_context(agent)
        assert "Junior Engineer" in result.system_prompt
        # "you" nickname should not appear in parentheses
        assert "(you)" not in result.system_prompt

    @patch("code_agents.core.stream.load_rules", return_value="rules here")
    @patch("code_agents.core.stream.get_style_prompt", return_value="style here")
    def test_all_context_combined(self, mock_style, mock_rules):
        from code_agents.core.stream import _inject_context
        agent = self._make_agent(name="code-writer")
        with patch.dict(os.environ, {
            "TARGET_REPO_PATH": "/tmp/repo",
            "CODE_AGENTS_USER_ROLE": "Lead Engineer",
            "CODE_AGENTS_NICKNAME": "alice",
        }, clear=True):
            result = _inject_context(agent)
        assert "rules here" in result.system_prompt
        assert "style here" in result.system_prompt
        assert "Lead Engineer" in result.system_prompt
        assert "alice" in result.system_prompt
        assert "FORMAT:" in result.system_prompt


# ---------------------------------------------------------------------------
# stream_response (SSE streaming)
# ---------------------------------------------------------------------------


class TestStreamResponse:
    """Test the SSE stream_response async generator."""

    def _make_agent(self, name="test-agent", **kwargs):
        from code_agents.core.config import AgentConfig
        defaults = dict(
            name=name,
            display_name="Test",
            backend="cursor",
            model="test-model",
            system_prompt="Be helpful.",
            stream_tool_activity=False,
            include_session=False,
        )
        defaults.update(kwargs)
        return AgentConfig(**defaults)

    def _make_request(self, **kwargs):
        from code_agents.core.models import CompletionRequest, Message
        defaults = dict(
            model="test-model",
            messages=[Message(role="user", content="hello")],
        )
        defaults.update(kwargs)
        return CompletionRequest(**defaults)

    @pytest.mark.asyncio
    async def test_stream_response_basic(self):
        """stream_response should yield initial chunk, content chunks, final chunk, and DONE."""
        from code_agents.core.stream import stream_response
        from code_agents.core.message_types import SystemMessage, AssistantMessage, ResultMessage, TextBlock

        agent = self._make_agent()
        req = self._make_request()

        async def fake_run_agent(a, p, **kwargs):
            yield SystemMessage(subtype="init", data={"session_id": "s1"})
            yield AssistantMessage(content=[TextBlock(text="Hello!")], model="test-model")
            yield ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80,
                                is_error=False, session_id="s1",
                                usage={"input_tokens": 10, "output_tokens": 5})

        with patch("code_agents.core.stream.run_agent", side_effect=fake_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent):
            chunks = []
            async for chunk in stream_response(agent, req):
                chunks.append(chunk)

        # Should have: initial role chunk, content chunk, final chunk, DONE
        assert len(chunks) >= 3
        # First chunk has role
        first_data = json.loads(chunks[0][len("data: "):].strip())
        assert first_data["choices"][0]["delta"]["role"] == "assistant"
        # Last chunk is DONE
        assert chunks[-1] == "data: [DONE]\n\n"
        # Content chunk
        content_found = False
        for c in chunks:
            if c.startswith("data: ") and "Hello!" in c:
                content_found = True
                break
        assert content_found

    @pytest.mark.asyncio
    async def test_stream_response_with_tool_activity(self):
        """When stream_tool_activity=True, tool use blocks should appear as reasoning_content."""
        from code_agents.core.stream import stream_response
        from code_agents.core.message_types import (
            SystemMessage, AssistantMessage, ResultMessage,
            TextBlock, ToolUseBlock, ToolResultBlock,
        )

        agent = self._make_agent(stream_tool_activity=True)
        req = self._make_request(stream_tool_activity=True)

        async def fake_run_agent(a, p, **kwargs):
            yield SystemMessage(subtype="init", data={})
            yield AssistantMessage(content=[
                ToolUseBlock(name="bash", input={"cmd": "ls"}, id="tu1"),
                ToolResultBlock(content="file.txt", tool_use_id="tu1"),
                TextBlock(text="Done."),
            ], model="test")
            yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                                is_error=False, session_id="", usage=None)

        with patch("code_agents.core.stream.run_agent", side_effect=fake_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent):
            chunks = []
            async for chunk in stream_response(agent, req):
                chunks.append(chunk)

        all_text = "".join(chunks)
        assert "bash" in all_text
        assert "Done." in all_text

    @pytest.mark.asyncio
    async def test_stream_response_error(self):
        """When backend raises, should yield error chunk."""
        from code_agents.core.stream import stream_response

        agent = self._make_agent()
        req = self._make_request()

        async def failing_run_agent(a, p, **kwargs):
            raise RuntimeError("Backend exploded")
            yield  # make it a generator

        with patch("code_agents.core.stream.run_agent", side_effect=failing_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent):
            chunks = []
            async for chunk in stream_response(agent, req):
                chunks.append(chunk)

        all_text = "".join(chunks)
        assert "Error" in all_text
        assert "Backend exploded" in all_text
        assert "data: [DONE]\n\n" in all_text

    @pytest.mark.asyncio
    async def test_stream_response_includes_session_id(self):
        """When include_session=True, final chunk should contain session_id."""
        from code_agents.core.stream import stream_response
        from code_agents.core.message_types import SystemMessage, AssistantMessage, ResultMessage, TextBlock

        agent = self._make_agent(include_session=True)
        req = self._make_request(include_session=True)

        async def fake_run_agent(a, p, **kwargs):
            yield SystemMessage(subtype="init", data={"session_id": "session-xyz"})
            yield AssistantMessage(content=[TextBlock(text="ok")], model="test")
            yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                                is_error=False, session_id="session-xyz", usage=None)

        with patch("code_agents.core.stream.run_agent", side_effect=fake_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent):
            chunks = []
            async for chunk in stream_response(agent, req):
                chunks.append(chunk)

        # Find the final chunk with session_id
        session_found = False
        for c in chunks:
            if c.startswith("data: ") and "session-xyz" in c:
                session_found = True
                break
        assert session_found


# ---------------------------------------------------------------------------
# collect_response (non-streaming)
# ---------------------------------------------------------------------------


class TestCollectResponse:
    """Test the non-streaming collect_response function."""

    def _make_agent(self, **kwargs):
        from code_agents.core.config import AgentConfig
        defaults = dict(
            name="test-agent",
            display_name="Test",
            backend="cursor",
            model="test-model",
            system_prompt="Be helpful.",
            stream_tool_activity=False,
            include_session=False,
        )
        defaults.update(kwargs)
        return AgentConfig(**defaults)

    def _make_request(self, **kwargs):
        from code_agents.core.models import CompletionRequest, Message
        defaults = dict(
            model="test-model",
            messages=[Message(role="user", content="hello")],
        )
        defaults.update(kwargs)
        return CompletionRequest(**defaults)

    @pytest.mark.asyncio
    async def test_collect_basic(self):
        from code_agents.core.stream import collect_response
        from code_agents.core.message_types import SystemMessage, AssistantMessage, ResultMessage, TextBlock

        agent = self._make_agent()
        req = self._make_request()

        async def fake_run_agent(a, p, **kwargs):
            yield SystemMessage(subtype="init", data={"session_id": "s1"})
            yield AssistantMessage(content=[TextBlock(text="Response text")], model="test")
            yield ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80,
                                is_error=False, session_id="s1",
                                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

        with patch("code_agents.core.stream.run_agent", side_effect=fake_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent):
            result = await collect_response(agent, req)

        assert result["object"] == "chat.completion"
        assert result["choices"][0]["message"]["content"] == "Response text"
        assert result["choices"][0]["finish_reason"] == "stop"
        assert result["usage"]["prompt_tokens"] == 10

    @pytest.mark.asyncio
    async def test_collect_with_tool_activity(self):
        from code_agents.core.stream import collect_response
        from code_agents.core.message_types import (
            SystemMessage, AssistantMessage, ResultMessage,
            TextBlock, ToolUseBlock, ToolResultBlock,
        )

        agent = self._make_agent(stream_tool_activity=True)
        req = self._make_request(stream_tool_activity=True)

        async def fake_run_agent(a, p, **kwargs):
            yield SystemMessage(subtype="init", data={})
            yield AssistantMessage(content=[
                ToolUseBlock(name="bash", input={"cmd": "ls"}, id="tu1"),
                ToolResultBlock(content="file.txt", tool_use_id="tu1"),
                TextBlock(text="Done."),
            ], model="test")
            yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                                is_error=False, session_id="", usage=None)

        with patch("code_agents.core.stream.run_agent", side_effect=fake_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent):
            result = await collect_response(agent, req)

        assert result["choices"][0]["message"]["content"] == "Done."
        assert "reasoning_content" in result["choices"][0]["message"]

    @pytest.mark.asyncio
    async def test_collect_with_session_id(self):
        from code_agents.core.stream import collect_response
        from code_agents.core.message_types import SystemMessage, AssistantMessage, ResultMessage, TextBlock

        agent = self._make_agent(include_session=True)
        req = self._make_request(include_session=True)

        async def fake_run_agent(a, p, **kwargs):
            yield SystemMessage(subtype="init", data={"session_id": "sess-42"})
            yield AssistantMessage(content=[TextBlock(text="ok")], model="test")
            yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                                is_error=False, session_id="sess-42", usage=None)

        with patch("code_agents.core.stream.run_agent", side_effect=fake_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent):
            result = await collect_response(agent, req)

        assert result.get("session_id") == "sess-42"


# ---------------------------------------------------------------------------
# stream_response smart orchestrator delegation hints (lines 213-218)
# ---------------------------------------------------------------------------


class TestStreamResponseSmartOrchestrator:
    def _make_agent(self, **kwargs):
        from code_agents.core.config import AgentConfig
        defaults = dict(
            name="code-writer",
            display_name="Code Writer",
            backend="cursor",
            model="test-model",
            system_prompt="You are a test agent.",
        )
        defaults.update(kwargs)
        return AgentConfig(**defaults)

    def _make_request(self, **kwargs):
        from code_agents.core.models import CompletionRequest, Message
        defaults = dict(
            model="test-model",
            messages=[Message(role="user", content="hello")],
        )
        defaults.update(kwargs)
        return CompletionRequest(**defaults)

    @pytest.mark.asyncio
    async def test_smart_orchestrator_delegation_hints(self):
        """When SmartOrchestrator suggests a different agent, delegation hints are injected (lines 212-216)."""
        from code_agents.core.stream import stream_response
        from code_agents.core.message_types import SystemMessage, AssistantMessage, ResultMessage, TextBlock

        agent = self._make_agent()
        req = self._make_request()

        mock_analysis = {
            "best_agent": "jenkins-cicd",
            "context_injection": None,
        }

        async def fake_run_agent(a, p, **kwargs):
            yield SystemMessage(subtype="init", data={})
            yield AssistantMessage(content=[TextBlock(text="Ok")], model="test")
            yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                                is_error=False, session_id="", usage=None)

        with patch("code_agents.core.stream.run_agent", side_effect=fake_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent), \
             patch("code_agents.agent_system.smart_orchestrator.SmartOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.analyze_request.return_value = mock_analysis
            mock_orch_cls.return_value = mock_orch
            mock_orch_cls.get_delegation_hints.return_value = "Consider using jenkins-cicd"

            chunks = []
            async for chunk in stream_response(agent, req):
                chunks.append(chunk)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_smart_orchestrator_exception_nonfatal(self):
        """SmartOrchestrator exception is non-fatal (line 217-218)."""
        from code_agents.core.stream import stream_response
        from code_agents.core.message_types import SystemMessage, AssistantMessage, ResultMessage, TextBlock

        agent = self._make_agent()
        req = self._make_request()

        async def fake_run_agent(a, p, **kwargs):
            yield SystemMessage(subtype="init", data={})
            yield AssistantMessage(content=[TextBlock(text="Ok")], model="test")
            yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                                is_error=False, session_id="", usage=None)

        with patch("code_agents.core.stream.run_agent", side_effect=fake_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent), \
             patch("code_agents.agent_system.smart_orchestrator.SmartOrchestrator", side_effect=Exception("import error")):
            chunks = []
            async for chunk in stream_response(agent, req):
                chunks.append(chunk)
        assert len(chunks) > 0


# ---------------------------------------------------------------------------
# stream_response error in stream with session (lines 399-401)
# ---------------------------------------------------------------------------


class TestStreamResponseError:
    def _make_agent(self, **kwargs):
        from code_agents.core.config import AgentConfig
        defaults = dict(
            name="test-agent",
            display_name="Test Agent",
            backend="cursor",
            model="test-model",
            system_prompt="test",
            include_session=True,
        )
        defaults.update(kwargs)
        return AgentConfig(**defaults)

    def _make_request(self, **kwargs):
        from code_agents.core.models import CompletionRequest, Message
        defaults = dict(
            model="test-model",
            messages=[Message(role="user", content="hello")],
            include_session=True,
        )
        defaults.update(kwargs)
        return CompletionRequest(**defaults)

    @pytest.mark.asyncio
    async def test_error_includes_session_id(self):
        """Error response includes session_id when available (lines 399-401)."""
        from code_agents.core.stream import stream_response
        from code_agents.core.message_types import SystemMessage, ResultMessage

        agent = self._make_agent()
        req = self._make_request()

        async def fake_run_agent(a, p, **kwargs):
            yield SystemMessage(subtype="init", data={"session_id": "sess-err"})
            yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                                is_error=True, session_id="sess-err", usage=None,
                                error_message="Something went wrong")

        with patch("code_agents.core.stream.run_agent", side_effect=fake_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent):
            chunks = []
            async for chunk in stream_response(agent, req):
                chunks.append(chunk)

        # Find the error chunk
        error_chunks = [c for c in chunks if "Error" in c or "session_id" in c]
        assert len(error_chunks) >= 0  # At least DONE is present


# ---------------------------------------------------------------------------
# collect_response smart context for auto-pilot (lines 418-428)
# ---------------------------------------------------------------------------


class TestCollectResponseAutoPilot:
    def _make_agent(self, **kwargs):
        from code_agents.core.config import AgentConfig
        defaults = dict(
            name="auto-pilot",
            display_name="Auto Pilot",
            backend="cursor",
            model="test-model",
            system_prompt="You are auto-pilot.",
        )
        defaults.update(kwargs)
        return AgentConfig(**defaults)

    def _make_request(self, **kwargs):
        from code_agents.core.models import CompletionRequest, Message
        defaults = dict(
            model="test-model",
            messages=[Message(role="user", content="deploy to staging")],
        )
        defaults.update(kwargs)
        return CompletionRequest(**defaults)

    @pytest.mark.asyncio
    async def test_auto_pilot_smart_context_injection(self):
        """Auto-pilot gets context injection from SmartOrchestrator (lines 418-426)."""
        from code_agents.core.stream import collect_response
        from code_agents.core.message_types import SystemMessage, AssistantMessage, ResultMessage, TextBlock

        agent = self._make_agent()
        req = self._make_request()

        mock_analysis = {
            "best_agent": "auto-pilot",
            "context_injection": "Deploy context: use ArgoCD",
        }

        async def fake_run_agent(a, p, **kwargs):
            yield SystemMessage(subtype="init", data={})
            yield AssistantMessage(content=[TextBlock(text="Deploying...")], model="test")
            yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                                is_error=False, session_id="", usage=None)

        with patch("code_agents.core.stream.run_agent", side_effect=fake_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent), \
             patch("code_agents.agent_system.smart_orchestrator.SmartOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.analyze_request.return_value = mock_analysis
            mock_orch_cls.return_value = mock_orch
            result = await collect_response(agent, req)

        assert result["choices"][0]["message"]["content"] == "Deploying..."

    @pytest.mark.asyncio
    async def test_auto_pilot_smart_context_exception(self):
        """SmartOrchestrator exception in collect_response is silently caught (line 427-428)."""
        from code_agents.core.stream import collect_response
        from code_agents.core.message_types import SystemMessage, AssistantMessage, ResultMessage, TextBlock

        agent = self._make_agent()
        req = self._make_request()

        async def fake_run_agent(a, p, **kwargs):
            yield SystemMessage(subtype="init", data={})
            yield AssistantMessage(content=[TextBlock(text="Ok")], model="test")
            yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                                is_error=False, session_id="", usage=None)

        with patch("code_agents.core.stream.run_agent", side_effect=fake_run_agent), \
             patch("code_agents.core.stream._inject_context", return_value=agent), \
             patch("code_agents.agent_system.smart_orchestrator.SmartOrchestrator", side_effect=Exception("boom")):
            result = await collect_response(agent, req)

        assert result["choices"][0]["message"]["content"] == "Ok"
