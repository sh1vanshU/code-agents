"""Tests for models.py — Pydantic request/response models."""

import pytest

from code_agents.core.models import _coerce_bool, Message, CompletionRequest


# ---------------------------------------------------------------------------
# _coerce_bool
# ---------------------------------------------------------------------------

class TestCoerceBool:
    def test_none_default_false(self):
        assert _coerce_bool(None) is False

    def test_none_default_true(self):
        assert _coerce_bool(None, default=True) is True

    def test_bool_true(self):
        assert _coerce_bool(True) is True

    def test_bool_false(self):
        assert _coerce_bool(False) is False

    def test_int_0(self):
        assert _coerce_bool(0) is False

    def test_int_1(self):
        assert _coerce_bool(1) is True

    def test_float_0(self):
        assert _coerce_bool(0.0) is False

    def test_float_1(self):
        assert _coerce_bool(1.0) is True

    def test_string_true_variants(self):
        for s in ("1", "true", "yes", "on", "TRUE", " True ", " YES "):
            assert _coerce_bool(s) is True, f"Failed for {s!r}"

    def test_string_false_variants(self):
        for s in ("0", "false", "no", "off", "random"):
            assert _coerce_bool(s) is False, f"Failed for {s!r}"

    def test_other_type(self):
        assert _coerce_bool([1, 2]) is True
        assert _coerce_bool([]) is False


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

class TestMessage:
    def test_basic_message(self):
        m = Message(role="user", content="hello")
        assert m.role == "user"
        assert m.content == "hello"

    def test_none_content(self):
        m = Message(role="assistant", content=None)
        assert m.content is None

    def test_list_content_text_parts(self):
        m = Message(role="user", content=[
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ])
        assert m.content == "Hello\nWorld"

    def test_list_content_text_key_only(self):
        m = Message(role="user", content=[
            {"text": "just text"},
        ])
        assert m.content == "just text"

    def test_list_content_string_items(self):
        m = Message(role="user", content=["part1", "part2"])
        assert m.content == "part1\npart2"

    def test_list_content_empty(self):
        m = Message(role="user", content=[])
        assert m.content is None

    def test_optional_fields(self):
        m = Message(role="user")
        assert m.tool_call_id is None
        assert m.tool_calls is None
        assert m.name is None


# ---------------------------------------------------------------------------
# CompletionRequest
# ---------------------------------------------------------------------------

class TestCompletionRequest:
    def test_minimal(self):
        req = CompletionRequest(messages=[Message(role="user", content="hi")])
        assert req.stream is False
        assert req.model is None

    def test_stream_coercion_string(self):
        req = CompletionRequest(
            messages=[Message(role="user", content="x")],
            stream="true",
        )
        assert req.stream is True

    def test_stream_coercion_int(self):
        req = CompletionRequest(
            messages=[Message(role="user", content="x")],
            stream=1,
        )
        assert req.stream is True

    def test_optional_bool_none(self):
        req = CompletionRequest(
            messages=[Message(role="user", content="x")],
            include_session=None,
        )
        assert req.include_session is None

    def test_optional_bool_coercion(self):
        req = CompletionRequest(
            messages=[Message(role="user", content="x")],
            include_session="true",
            stream_tool_activity="1",
        )
        assert req.include_session is True
        assert req.stream_tool_activity is True

    def test_extra_fields_ignored(self):
        req = CompletionRequest(
            messages=[Message(role="user", content="x")],
            some_unknown_field="value",
        )
        assert not hasattr(req, "some_unknown_field")

    def test_standard_openai_fields(self):
        req = CompletionRequest(
            messages=[Message(role="user", content="x")],
            temperature=0.7,
            max_tokens=100,
            top_p=0.9,
        )
        assert req.temperature == 0.7
        assert req.max_tokens == 100
        assert req.top_p == 0.9
