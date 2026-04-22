"""Full coverage tests for integrations/slack_bot.py and routers/slack_bot.py."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from code_agents.integrations.slack_bot import SlackBot, _AGENT_KEYWORDS, _SLACK_MAX_LENGTH


# ---------------------------------------------------------------------------
# SlackBot.get_bot_user_id
# ---------------------------------------------------------------------------


class TestGetBotUserId:
    def test_cached(self):
        bot = SlackBot()
        bot._bot_user_id = "U_CACHED"
        assert bot.get_bot_user_id() == "U_CACHED"

    def test_no_token(self):
        bot = SlackBot()
        bot.bot_token = ""
        bot._bot_user_id = ""
        assert bot.get_bot_user_id() == ""

    def test_success(self):
        bot = SlackBot()
        bot.bot_token = "xoxb-test"
        bot._bot_user_id = ""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "user_id": "U_BOT_123"}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.get_bot_user_id()
        assert result == "U_BOT_123"
        assert bot._bot_user_id == "U_BOT_123"

    def test_auth_test_not_ok(self):
        bot = SlackBot()
        bot.bot_token = "xoxb-test"
        bot._bot_user_id = ""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": False, "error": "invalid_auth"}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.get_bot_user_id()
        assert result == ""

    def test_request_exception(self):
        bot = SlackBot()
        bot.bot_token = "xoxb-test"
        bot._bot_user_id = ""
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            result = bot.get_bot_user_id()
        assert result == ""


# ---------------------------------------------------------------------------
# SlackBot.send_message
# ---------------------------------------------------------------------------


class TestSendMessage:
    def test_success(self):
        bot = SlackBot()
        bot.bot_token = "xoxb-test"
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.send_message("C123", "hello", "1234.5678")
        assert result is True

    def test_without_thread_ts(self):
        bot = SlackBot()
        bot.bot_token = "xoxb-test"
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = bot.send_message("C123", "hello")
        assert result is True

    def test_slack_api_error(self):
        bot = SlackBot()
        bot.bot_token = "xoxb-test"
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": False, "error": "channel_not_found"}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.send_message("INVALID", "hello")
        assert result is False

    def test_network_exception(self):
        bot = SlackBot()
        bot.bot_token = "xoxb-test"
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = bot.send_message("C123", "hello")
        assert result is False


# ---------------------------------------------------------------------------
# SlackBot.delegate_to_agent
# ---------------------------------------------------------------------------


class TestDelegateToAgent:
    def test_success(self):
        bot = SlackBot()
        bot.server_url = "http://localhost:8000"
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Agent response"}}]
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.delegate_to_agent("hello", "auto-pilot")
        assert result == "Agent response"

    def test_no_choices(self):
        bot = SlackBot()
        bot.server_url = "http://localhost:8000"
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"choices": []}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.delegate_to_agent("hello")
        assert result == "No response from agent"

    def test_retry_on_first_failure(self):
        bot = SlackBot()
        bot.server_url = "http://localhost:8000"
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("timeout")
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "choices": [{"message": {"content": "retry ok"}}]
            }).encode()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=side_effect):
            with patch("time.sleep"):
                result = bot.delegate_to_agent("hello")
        assert result == "retry ok"
        assert call_count == 2

    def test_both_attempts_fail(self):
        bot = SlackBot()
        bot.server_url = "http://localhost:8000"
        with patch("urllib.request.urlopen", side_effect=Exception("persistent error")):
            with patch("time.sleep"):
                result = bot.delegate_to_agent("hello")
        assert result.startswith("Error:")

    def test_no_content_in_message(self):
        bot = SlackBot()
        bot.server_url = "http://localhost:8000"
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {}}]
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.delegate_to_agent("hello")
        assert result == "No response"


# ---------------------------------------------------------------------------
# SlackBot.handle_event — additional edge cases
# ---------------------------------------------------------------------------


class TestHandleEventEdgeCases:
    def test_uses_ts_when_no_thread_ts(self):
        bot = SlackBot()
        bot._bot_user_id = ""
        with patch.object(bot, "delegate_to_agent", return_value="answer"):
            with patch.object(bot, "send_message", return_value=True) as mock_send:
                event = {"type": "message", "user": "U1", "text": "hello", "channel": "C1", "ts": "123.456"}
                bot.handle_event(event)
        # thread_ts defaults to ts
        reply_call = mock_send.call_args_list[-1]
        assert reply_call[0][2] == "123.456"

    def test_no_text_at_all(self):
        bot = SlackBot()
        bot._bot_user_id = ""
        event = {"type": "message", "user": "U1", "text": "", "channel": "C1", "ts": "1"}
        assert bot.handle_event(event) is None

    def test_empty_user_field(self):
        bot = SlackBot()
        bot._bot_user_id = ""
        with patch.object(bot, "delegate_to_agent", return_value="answer"):
            with patch.object(bot, "send_message", return_value=True):
                event = {"type": "message", "user": "", "text": "hi", "channel": "C1", "ts": "1"}
                result = bot.handle_event(event)
        assert result == "answer"


# ---------------------------------------------------------------------------
# SlackBot.detect_agent — additional coverage
# ---------------------------------------------------------------------------


class TestDetectAgentEdgeCases:
    def test_single_keyword_unambiguous(self):
        """Single keyword hit with only one agent matching => that agent."""
        bot = SlackBot()
        result = bot.detect_agent("jenkins")
        assert result == "jenkins-cicd"

    def test_multiple_agents_single_hit_each(self):
        """Multiple agents with 1 hit each => auto-pilot (ambiguous)."""
        bot = SlackBot()
        # "build" matches jenkins-cicd, "test" matches code-tester
        result = bot.detect_agent("build test")
        assert result == "auto-pilot"


# ---------------------------------------------------------------------------
# Router: _process_event
# ---------------------------------------------------------------------------


class TestProcessEvent:
    @pytest.mark.asyncio
    async def test_process_event_success(self):
        from code_agents.routers.slack_bot import _process_event
        mock_bot = MagicMock()
        mock_bot.handle_event.return_value = "ok"
        await _process_event(mock_bot, {"text": "hello"})
        mock_bot.handle_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_event_exception(self):
        from code_agents.routers.slack_bot import _process_event
        mock_bot = MagicMock()
        mock_bot.handle_event.side_effect = RuntimeError("failed")
        # Should not raise — just logs
        await _process_event(mock_bot, {"text": "hello"})


# ---------------------------------------------------------------------------
# Router: slack_events endpoint — additional edge cases
# ---------------------------------------------------------------------------


class TestSlackRouterEdgeCases:
    @pytest.fixture
    def slack_client(self):
        from code_agents.routers.slack_bot import router as slack_router
        app = FastAPI()
        app.include_router(slack_router)
        return TestClient(app)

    def test_non_event_callback_returns_ok(self, slack_client):
        """Unknown type (not url_verification or event_callback) returns ok."""
        resp = slack_client.post(
            "/slack/events",
            json={"type": "unknown_type"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_event_callback_non_message_type(self, slack_client):
        """Event callback with type != message/app_mention."""
        with patch("code_agents.integrations.slack_bot.SlackBot.verify_signature", return_value=True):
            resp = slack_client.post(
                "/slack/events",
                json={
                    "type": "event_callback",
                    "event": {"type": "reaction_added", "user": "U1"},
                },
                headers={
                    "X-Slack-Request-Timestamp": str(int(time.time())),
                    "X-Slack-Signature": "v0=fake",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_no_signing_secret_skips_verification(self, slack_client):
        """When bot has no signing_secret, verification is skipped."""
        with patch("code_agents.integrations.slack_bot.SlackBot.__init__", lambda self: (
            setattr(self, 'bot_token', ''),
            setattr(self, 'signing_secret', ''),
            setattr(self, 'server_url', 'http://127.0.0.1:8000'),
            setattr(self, '_bot_user_id', ''),
        )[-1]):
            resp = slack_client.post(
                "/slack/events",
                json={"type": "event_callback", "event": {"type": "message", "subtype": "bot_message"}},
                headers={
                    "X-Slack-Request-Timestamp": str(int(time.time())),
                    "X-Slack-Signature": "v0=whatever",
                },
            )
        assert resp.status_code == 200
