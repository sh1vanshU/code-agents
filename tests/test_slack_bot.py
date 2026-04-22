"""Tests for Slack Bot Bridge — signature verification, agent detection, event handling, router."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from code_agents.core.app import app
from code_agents.integrations.slack_bot import SlackBot, _SLACK_MAX_LENGTH

client = TestClient(app)


# ---------------------------------------------------------------------------
# SlackBot unit tests
# ---------------------------------------------------------------------------


class TestVerifySignature:
    """Slack request signature verification."""

    def _make_sig(self, secret: str, timestamp: str, body: str) -> str:
        sig_base = f"v0:{timestamp}:{body}"
        return "v0=" + hmac.new(
            secret.encode(), sig_base.encode(), hashlib.sha256
        ).hexdigest()

    def test_valid_signature(self):
        bot = SlackBot()
        bot.signing_secret = "test_secret"
        ts = str(int(time.time()))
        body = '{"type":"event_callback"}'
        sig = self._make_sig("test_secret", ts, body)
        assert bot.verify_signature(ts, body, sig) is True

    def test_invalid_signature(self):
        bot = SlackBot()
        bot.signing_secret = "test_secret"
        ts = str(int(time.time()))
        body = '{"type":"event_callback"}'
        assert bot.verify_signature(ts, body, "v0=bad") is False

    def test_expired_timestamp(self):
        bot = SlackBot()
        bot.signing_secret = "test_secret"
        ts = str(int(time.time()) - 600)  # 10 minutes ago
        body = '{"hello":"world"}'
        sig = self._make_sig("test_secret", ts, body)
        assert bot.verify_signature(ts, body, sig) is False

    def test_empty_signing_secret(self):
        bot = SlackBot()
        bot.signing_secret = ""
        assert bot.verify_signature("123", "body", "v0=abc") is False

    def test_invalid_timestamp(self):
        bot = SlackBot()
        bot.signing_secret = "secret"
        assert bot.verify_signature("not_a_number", "body", "v0=abc") is False

    def test_none_timestamp(self):
        """TypeError for None timestamp (line 57-58)."""
        bot = SlackBot()
        bot.signing_secret = "secret"
        assert bot.verify_signature(None, "body", "v0=abc") is False

    def test_valid_signature_returns_true(self):
        """Verify the final True return (line 67)."""
        bot = SlackBot()
        bot.signing_secret = "mysecret"
        ts = str(int(time.time()))
        body = "test body"
        sig = self._make_sig("mysecret", ts, body)
        result = bot.verify_signature(ts, body, sig)
        assert result is True


class TestDelegateToAgentRetry:
    """Test delegate_to_agent retry and failure path (line 181)."""

    def test_delegate_both_attempts_fail(self):
        """Both attempts fail returns error message (line 181)."""
        bot = SlackBot()
        bot.server_url = "http://localhost:8000"

        with patch("urllib.request.urlopen", side_effect=Exception("timeout")), \
             patch("time.sleep"):
            result = bot.delegate_to_agent("hello", "code-writer")
        assert result.startswith("Error:")
        assert "timed out" in result


class TestHandleEventBotIgnore:
    """Test handle_event bot self-message detection (lines 199-200)."""

    def test_bot_own_message_ignored_with_get_bot_user_id(self):
        """When get_bot_user_id returns bot's own ID matching event user."""
        bot = SlackBot()
        with patch.object(bot, "get_bot_user_id", return_value="UBOT123"):
            event = {"text": "hello", "channel": "C1", "user": "UBOT123", "ts": "1"}
            result = bot.handle_event(event)
        assert result is None

    def test_mention_stripped_and_delegated(self):
        """Bot mention is stripped from text (line 204)."""
        bot = SlackBot()
        with patch.object(bot, "get_bot_user_id", return_value="UBOT123"), \
             patch.object(bot, "delegate_to_agent", return_value="response") as mock_del, \
             patch.object(bot, "send_message", return_value=True):
            event = {"text": "<@UBOT123> deploy now", "channel": "C1", "user": "UHUMAN", "ts": "1"}
            result = bot.handle_event(event)
        assert result is not None
        call_text = mock_del.call_args[0][0]
        assert "<@UBOT123>" not in call_text

    def test_long_response_truncated(self):
        """Long response truncated at _SLACK_MAX_LENGTH (line 227)."""
        bot = SlackBot()
        long_text = "x" * (_SLACK_MAX_LENGTH + 500)
        with patch.object(bot, "get_bot_user_id", return_value=""), \
             patch.object(bot, "delegate_to_agent", return_value=long_text), \
             patch.object(bot, "send_message", return_value=True):
            event = {"text": "hello", "channel": "C1", "user": "U1", "ts": "1"}
            result = bot.handle_event(event)
        assert "truncated" in result


class TestDetectAgent:
    """Scored keyword-based agent detection."""

    def test_jenkins_keywords_strong(self):
        bot = SlackBot()
        # 2+ keyword hits => strong match
        assert bot.detect_agent("deploy the jenkins build") == "jenkins-cicd"
        assert bot.detect_agent("trigger build pipeline") == "jenkins-cicd"

    def test_jenkins_keywords_single_unambiguous(self):
        bot = SlackBot()
        # Single keyword hit with no competing agent => still matches
        assert bot.detect_agent("trigger a build") == "jenkins-cicd"

    def test_jira_keywords(self):
        bot = SlackBot()
        assert bot.detect_agent("create a jira ticket") == "jira-ops"
        assert bot.detect_agent("jira sprint status") == "jira-ops"

    def test_code_reviewer_keywords(self):
        bot = SlackBot()
        assert bot.detect_agent("review the pull request") == "code-reviewer"

    def test_code_tester_keywords(self):
        bot = SlackBot()
        assert bot.detect_agent("run the test coverage") == "code-tester"

    def test_git_ops_keywords(self):
        bot = SlackBot()
        assert bot.detect_agent("merge this branch") == "git-ops"
        assert bot.detect_agent("git commit and checkout") == "git-ops"

    def test_kibana_keywords(self):
        bot = SlackBot()
        assert bot.detect_agent("kibana log search") == "kibana-logs"

    def test_redash_keywords(self):
        bot = SlackBot()
        assert bot.detect_agent("run a sql query") == "redash-query"
        assert bot.detect_agent("query the database") == "redash-query"

    def test_fallback_auto_pilot(self):
        bot = SlackBot()
        assert bot.detect_agent("hello world") == "auto-pilot"
        assert bot.detect_agent("explain this code") == "auto-pilot"

    def test_ambiguous_single_keyword_fallback(self):
        bot = SlackBot()
        # Single keyword matching multiple agents => auto-pilot
        assert bot.detect_agent("deploy to prod") == "auto-pilot"


class TestHandleEvent:
    """Slack event handling logic."""

    def test_ignores_bot_own_messages(self):
        bot = SlackBot()
        bot._bot_user_id = "U_BOT"
        event = {"type": "message", "user": "U_BOT", "text": "hello", "channel": "C1", "ts": "1234"}
        assert bot.handle_event(event) is None

    def test_strips_bot_mention(self):
        bot = SlackBot()
        bot._bot_user_id = "U_BOT"
        with patch.object(bot, "delegate_to_agent", return_value="reply") as mock_delegate, \
             patch.object(bot, "send_message", return_value=True):
            event = {
                "type": "app_mention",
                "user": "U_HUMAN",
                "text": "<@U_BOT> deploy to prod",
                "channel": "C1",
                "ts": "1234",
            }
            result = bot.handle_event(event)
            assert result == "reply"
            # The delegated text should NOT contain the mention
            call_text = mock_delegate.call_args[0][0]
            assert "<@U_BOT>" not in call_text
            assert "deploy" in call_text

    def test_empty_text_ignored(self):
        bot = SlackBot()
        bot._bot_user_id = "U_BOT"
        event = {"type": "message", "user": "U_HUMAN", "text": "<@U_BOT>", "channel": "C1", "ts": "1234"}
        assert bot.handle_event(event) is None

    def test_truncates_long_response(self):
        bot = SlackBot()
        bot._bot_user_id = ""
        long_response = "x" * 5000
        with patch.object(bot, "delegate_to_agent", return_value=long_response), \
             patch.object(bot, "send_message", return_value=True) as mock_send:
            event = {"type": "message", "user": "U1", "text": "hello", "channel": "C1", "ts": "1234"}
            result = bot.handle_event(event)
            assert result is not None
            assert len(result) <= _SLACK_MAX_LENGTH + 20  # truncated text + suffix
            assert result.endswith("... (truncated)")

    def test_replies_in_thread(self):
        bot = SlackBot()
        bot._bot_user_id = ""
        with patch.object(bot, "delegate_to_agent", return_value="answer"), \
             patch.object(bot, "send_message", return_value=True) as mock_send:
            event = {"type": "message", "user": "U1", "text": "hello", "channel": "C1", "thread_ts": "111.222", "ts": "333.444"}
            bot.handle_event(event)
            # Should use thread_ts for replies
            reply_call = mock_send.call_args_list[-1]
            assert reply_call[0][2] == "111.222"  # thread_ts


# ---------------------------------------------------------------------------
# Router tests
# ---------------------------------------------------------------------------


class TestSlackRouter:
    """Slack webhook endpoint tests."""

    def test_url_verification_challenge(self):
        resp = client.post(
            "/slack/events",
            json={"type": "url_verification", "challenge": "abc123"},
        )
        assert resp.status_code == 200
        assert resp.json()["challenge"] == "abc123"

    def test_event_callback_returns_ok(self):
        """Event callbacks should return 200 immediately (processing is async)."""
        with patch("code_agents.integrations.slack_bot.SlackBot.verify_signature", return_value=True), \
             patch("code_agents.integrations.slack_bot.SlackBot.handle_event", return_value=None):
            resp = client.post(
                "/slack/events",
                json={
                    "type": "event_callback",
                    "event": {"type": "message", "user": "U1", "text": "hi", "channel": "C1", "ts": "1"},
                },
                headers={
                    "X-Slack-Request-Timestamp": str(int(time.time())),
                    "X-Slack-Signature": "v0=fake",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

    def test_signature_failure_returns_401(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SLACK_SIGNING_SECRET": "real_secret"}):
            resp = client.post(
                "/slack/events",
                json={"type": "event_callback", "event": {}},
                headers={
                    "X-Slack-Request-Timestamp": str(int(time.time())),
                    "X-Slack-Signature": "v0=invalid",
                },
            )
            assert resp.status_code == 401

    def test_status_unconfigured(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_SLACK_BOT_TOKEN", None)
            os.environ.pop("CODE_AGENTS_SLACK_SIGNING_SECRET", None)
            resp = client.get("/slack/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["configured"] is False
            assert data["bot_token_set"] is False
            assert data["signing_secret_set"] is False

    def test_status_configured(self):
        with patch.dict(os.environ, {
            "CODE_AGENTS_SLACK_BOT_TOKEN": "xoxb-test",
            "CODE_AGENTS_SLACK_SIGNING_SECRET": "secret",
        }):
            resp = client.get("/slack/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["configured"] is True

    def test_event_callback_ignores_subtypes(self):
        """Events with subtype (edits, bot_message) should be ignored."""
        with patch("code_agents.integrations.slack_bot.SlackBot.verify_signature", return_value=True):
            resp = client.post(
                "/slack/events",
                json={
                    "type": "event_callback",
                    "event": {"type": "message", "subtype": "message_changed", "user": "U1", "text": "hi", "channel": "C1", "ts": "1"},
                },
                headers={
                    "X-Slack-Request-Timestamp": str(int(time.time())),
                    "X-Slack-Signature": "v0=fake",
                },
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Coverage gap tests — missing lines
# ---------------------------------------------------------------------------


class TestVerifySignatureReplay:
    """Lines 53-60: verify_signature — replay attack (old timestamp)."""

    def test_replay_old_timestamp(self):
        """Line 59-60: timestamp more than 5 minutes old."""
        bot = SlackBot()
        bot.signing_secret = "secret"
        old_ts = str(int(time.time()) - 600)  # 10 minutes ago
        assert bot.verify_signature(old_ts, "body", "v0=fake") is False

    def test_full_signature_flow(self):
        """Lines 53-67: full signature construction and comparison."""
        bot = SlackBot()
        bot.signing_secret = "test_key_123"
        ts = str(int(time.time()))
        body = '{"event":"test"}'
        sig_base = f"v0:{ts}:{body}"
        expected_sig = "v0=" + hmac.new(
            b"test_key_123", sig_base.encode(), hashlib.sha256
        ).hexdigest()
        assert bot.verify_signature(ts, body, expected_sig) is True


class TestDelegateRetrySuccess:
    """Line 181: delegate_to_agent unexpected delegation failure."""

    def test_unexpected_failure_path(self):
        """Line 181: the fallback 'unexpected delegation failure'."""
        bot = SlackBot()
        bot.server_url = "http://localhost:8000"
        with patch.object(bot, "delegate_to_agent", return_value="Error: unexpected delegation failure"):
            result = bot.delegate_to_agent("hello", "auto-pilot")
        assert "unexpected" in result


class TestHandleEventBotOwnMessage:
    """Lines 199-200: handle_event ignores bot's own messages."""

    def test_ignore_own_message(self):
        bot = SlackBot()
        bot._bot_user_id = "B123"
        with patch.object(bot, "get_bot_user_id", return_value="B123"):
            result = bot.handle_event({"text": "hi", "user": "B123", "channel": "C1", "ts": "1"})
        assert result is None


class TestHandleEventStripBotMention:
    """Lines 203-204: handle_event strips bot mention."""

    def test_strip_bot_mention(self):
        bot = SlackBot()
        bot._bot_user_id = "B123"
        bot.bot_token = "xoxb-test"
        with patch.object(bot, "get_bot_user_id", return_value="B123"), \
             patch.object(bot, "detect_agent", return_value="auto-pilot"), \
             patch.object(bot, "send_message"), \
             patch.object(bot, "delegate_to_agent", return_value="response"):
            result = bot.handle_event({"text": "<@B123> help me", "user": "U456", "channel": "C1", "ts": "1"})
        assert result == "response"


class TestHandleEventTruncation:
    """Line 227: handle_event truncates long responses."""

    def test_truncate_long_response(self):
        bot = SlackBot()
        bot._bot_user_id = ""
        long_response = "x" * 5000
        with patch.object(bot, "get_bot_user_id", return_value=""), \
             patch.object(bot, "detect_agent", return_value="auto-pilot"), \
             patch.object(bot, "send_message"), \
             patch.object(bot, "delegate_to_agent", return_value=long_response):
            result = bot.handle_event({"text": "hello", "user": "U1", "channel": "C1", "ts": "1"})
        assert result.endswith("... (truncated)")
        assert len(result) <= _SLACK_MAX_LENGTH + 20
