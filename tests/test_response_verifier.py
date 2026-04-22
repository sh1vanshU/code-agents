"""Tests for response_verifier.py — auto-verify code-writer output."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from code_agents.core.response_verifier import ResponseVerifier, get_verifier


class TestResponseVerifier:
    """Core ResponseVerifier behavior."""

    def test_default_disabled(self):
        rv = ResponseVerifier()
        assert rv.enabled is False

    def test_enabled_via_env(self):
        with patch.dict(os.environ, {"CODE_AGENTS_AUTO_VERIFY": "true"}):
            rv = ResponseVerifier()
            assert rv.enabled is True

    def test_enabled_case_insensitive(self):
        with patch.dict(os.environ, {"CODE_AGENTS_AUTO_VERIFY": "True"}):
            rv = ResponseVerifier()
            assert rv.enabled is True

    def test_disabled_when_env_false(self):
        with patch.dict(os.environ, {"CODE_AGENTS_AUTO_VERIFY": "false"}):
            rv = ResponseVerifier()
            assert rv.enabled is False

    def test_disabled_when_env_empty(self):
        with patch.dict(os.environ, {"CODE_AGENTS_AUTO_VERIFY": ""}):
            rv = ResponseVerifier()
            assert rv.enabled is False


class TestShouldVerify:
    """Conditions under which verification should trigger."""

    def test_not_enabled(self):
        rv = ResponseVerifier()
        assert rv.should_verify("code-writer", "```python\nprint()```") is False

    def test_enabled_code_writer_with_code(self):
        rv = ResponseVerifier()
        rv.enabled = True
        assert rv.should_verify("code-writer", "Here:\n```python\nprint()```") is True

    def test_wrong_agent(self):
        rv = ResponseVerifier()
        rv.enabled = True
        assert rv.should_verify("code-reviewer", "```python\nprint()```") is False

    def test_no_code_blocks(self):
        rv = ResponseVerifier()
        rv.enabled = True
        assert rv.should_verify("code-writer", "Here is the explanation.") is False

    def test_code_reasoning_not_verified(self):
        rv = ResponseVerifier()
        rv.enabled = True
        assert rv.should_verify("code-reasoning", "```bash\nls```") is False

    def test_auto_pilot_not_verified(self):
        rv = ResponseVerifier()
        rv.enabled = True
        assert rv.should_verify("auto-pilot", "```python\ncode```") is False


class TestBuildVerifyPrompt:
    """Verify prompt construction."""

    def test_basic_prompt(self):
        rv = ResponseVerifier()
        result = rv.build_verify_prompt("Fix the bug", "```python\nprint()```")
        prompt = result["prompt"]
        assert "VERIFY" in prompt
        assert "Fix the bug" in prompt
        assert "```python" in prompt
        assert "LGTM" in prompt
        assert "bugs" in prompt

    def test_returns_dict_with_keys(self):
        rv = ResponseVerifier()
        result = rv.build_verify_prompt("q", "```code```")
        assert "prompt" in result
        assert "delegate_to" in result
        assert "cache_key" in result
        assert result["delegate_to"] == "code-reviewer"

    def test_cache_key_from_code_blocks(self):
        rv = ResponseVerifier()
        result = rv.build_verify_prompt("q", "```python\nprint()```")
        assert result["cache_key"] is not None
        assert len(result["cache_key"]) == 32  # md5 hex

    def test_cache_key_none_without_code(self):
        rv = ResponseVerifier()
        result = rv.build_verify_prompt("q", "no code blocks here")
        assert result["cache_key"] is None

    def test_same_code_same_cache_key(self):
        rv = ResponseVerifier()
        r1 = rv.build_verify_prompt("q1", "```python\nprint()```")
        r2 = rv.build_verify_prompt("q2", "```python\nprint()```")
        assert r1["cache_key"] == r2["cache_key"]

    def test_long_query_truncated(self):
        rv = ResponseVerifier()
        long_query = "x" * 1000
        result = rv.build_verify_prompt(long_query, "```code```")
        prompt = result["prompt"]
        # Should be truncated to 500 chars
        assert len(long_query) > 500
        assert "x" * 500 in prompt
        assert "x" * 600 not in prompt

    def test_long_response_truncated(self):
        rv = ResponseVerifier()
        long_response = "y" * 5000
        result = rv.build_verify_prompt("query", long_response)
        prompt = result["prompt"]
        # Should be truncated to 3000 chars
        assert "y" * 3000 in prompt
        assert "y" * 3500 not in prompt

    def test_prompt_contains_review_criteria(self):
        rv = ResponseVerifier()
        result = rv.build_verify_prompt("q", "```code```")
        prompt = result["prompt"]
        assert "security" in prompt.lower()
        assert "edge cases" in prompt.lower()
        assert "error handling" in prompt.lower()


class TestCache:
    """Cache get/set/eviction behavior."""

    def test_cache_miss_returns_none(self):
        rv = ResponseVerifier()
        assert rv.get_cached_result("nonexistent") is None

    def test_cache_hit(self):
        rv = ResponseVerifier()
        rv.cache_result("key1", "LGTM")
        assert rv.get_cached_result("key1") == "LGTM"

    def test_cache_overwrite(self):
        rv = ResponseVerifier()
        rv.cache_result("key1", "old")
        rv.cache_result("key1", "new")
        assert rv.get_cached_result("key1") == "new"

    def test_cache_bounded(self):
        rv = ResponseVerifier()
        # Fill cache beyond 100
        for i in range(105):
            rv.cache_result(f"key-{i}", f"result-{i}")
        # Cache should not exceed 100 entries
        assert len(rv._cache) <= 101  # 100 + current (eviction happens after insert)

    def test_cache_evicts_oldest(self):
        rv = ResponseVerifier()
        for i in range(102):
            rv.cache_result(f"key-{i}", f"result-{i}")
        # key-0 should have been evicted
        assert rv.get_cached_result("key-0") is None
        # Latest should still be there
        assert rv.get_cached_result("key-101") == "result-101"

    def test_init_has_empty_cache(self):
        rv = ResponseVerifier()
        assert rv._cache == {}


class TestToggle:
    """Toggle on/off behavior."""

    def test_toggle_on(self):
        rv = ResponseVerifier()
        assert rv.enabled is False
        result = rv.toggle(True)
        assert result is True
        assert rv.enabled is True

    def test_toggle_off(self):
        rv = ResponseVerifier()
        rv.enabled = True
        result = rv.toggle(False)
        assert result is False
        assert rv.enabled is False

    def test_toggle_flip(self):
        rv = ResponseVerifier()
        assert rv.enabled is False
        rv.toggle()  # flip to True
        assert rv.enabled is True
        rv.toggle()  # flip to False
        assert rv.enabled is False


class TestGetVerifier:
    """Singleton lazy loading."""

    def test_returns_instance(self):
        # Reset singleton
        import code_agents.core.response_verifier as mod
        mod._verifier = None
        v = get_verifier()
        assert isinstance(v, ResponseVerifier)

    def test_returns_same_instance(self):
        import code_agents.core.response_verifier as mod
        mod._verifier = None
        v1 = get_verifier()
        v2 = get_verifier()
        assert v1 is v2

    def test_singleton_reset(self):
        import code_agents.core.response_verifier as mod
        mod._verifier = None
        v1 = get_verifier()
        mod._verifier = None
        v2 = get_verifier()
        assert v1 is not v2


class TestSlashCommand:
    """Test /verify slash command handling."""

    def test_verify_on(self, capsys):
        from code_agents.chat.chat_slash import _handle_command
        state = {"agent": "code-writer", "repo_path": "/tmp"}
        _handle_command("/verify on", state, "http://localhost:8000")
        out = capsys.readouterr().out
        assert "ON" in out

    def test_verify_off(self, capsys):
        from code_agents.chat.chat_slash import _handle_command
        state = {"agent": "code-writer", "repo_path": "/tmp"}
        _handle_command("/verify off", state, "http://localhost:8000")
        out = capsys.readouterr().out
        assert "OFF" in out

    def test_verify_status(self, capsys):
        from code_agents.chat.chat_slash import _handle_command
        # First enable, then check status
        state = {"agent": "code-writer", "repo_path": "/tmp"}
        _handle_command("/verify on", state, "http://localhost:8000")
        _handle_command("/verify status", state, "http://localhost:8000")
        out = capsys.readouterr().out
        assert "ON" in out

    def test_verify_no_arg_enables(self, capsys):
        from code_agents.chat.chat_slash import _handle_command
        import code_agents.core.response_verifier as mod
        mod._verifier = None  # reset
        state = {"agent": "code-writer", "repo_path": "/tmp"}
        _handle_command("/verify", state, "http://localhost:8000")
        out = capsys.readouterr().out
        assert "ON" in out
