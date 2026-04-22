"""Tests for Slack webhook integration — notifications, slash command, interactive, channel routing, CLI."""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call

# ---------------------------------------------------------------------------
# 1. Enhanced notifications
# ---------------------------------------------------------------------------

from code_agents.domain.notifications import (
    send_slack,
    send_slack_blocks,
    notify_build_status,
    notify_deploy_status,
    notify_test_status,
    notify_agent_completion,
    notify_error,
    notify_pr_review,
    notify_audit_result,
    notify_daily_digest,
    block_section,
    block_divider,
    block_header,
    block_actions,
    block_context,
    button,
    static_select,
    notify_agent_completion_blocks,
    notify_agent_selection_blocks,
    notify_approval_blocks,
)


class TestSendSlackBlocks:
    @pytest.mark.asyncio
    async def test_send_blocks_no_url_returns_false(self):
        with patch.dict("os.environ", {}, clear=True):
            result = await send_slack_blocks([block_section("hello")])
        assert result is False

    @pytest.mark.asyncio
    async def test_send_blocks_success(self):
        mock_resp = MagicMock(status_code=200)
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("code_agents.domain.notifications.httpx.AsyncClient", return_value=mock_client):
            result = await send_slack_blocks(
                [block_section("test")],
                text="fallback",
                webhook_url="https://hooks.slack.com/test",
            )
        assert result is True
        # Verify blocks and text are in the payload
        posted = mock_client.post.call_args
        payload = posted.kwargs.get("json") or posted[1].get("json")
        assert "blocks" in payload
        assert payload["text"] == "fallback"

    @pytest.mark.asyncio
    async def test_send_blocks_exception_returns_false(self):
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("network")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("code_agents.domain.notifications.httpx.AsyncClient", return_value=mock_client):
            result = await send_slack_blocks(
                [block_section("x")], webhook_url="https://hooks.slack.com/x"
            )
        assert result is False


class TestBlockKitBuilders:
    def test_block_section(self):
        b = block_section("hello *world*")
        assert b["type"] == "section"
        assert b["text"]["type"] == "mrkdwn"
        assert b["text"]["text"] == "hello *world*"
        assert "accessory" not in b

    def test_block_section_with_accessory(self):
        acc = {"type": "image", "image_url": "x", "alt_text": "y"}
        b = block_section("test", accessory=acc)
        assert b["accessory"] == acc

    def test_block_divider(self):
        assert block_divider() == {"type": "divider"}

    def test_block_header(self):
        b = block_header("My Header")
        assert b["type"] == "header"
        assert b["text"]["text"] == "My Header"

    def test_block_actions(self):
        b = block_actions([{"type": "button"}])
        assert b["type"] == "actions"
        assert len(b["elements"]) == 1

    def test_block_context(self):
        b = block_context(["line1", "line2"])
        assert b["type"] == "context"
        assert len(b["elements"]) == 2
        assert b["elements"][0]["text"] == "line1"

    def test_button_basic(self):
        b = button("Click", "my_action")
        assert b["type"] == "button"
        assert b["action_id"] == "my_action"
        assert "value" not in b
        assert "style" not in b

    def test_button_with_style(self):
        b = button("Go", "go_action", value="v1", style="primary")
        assert b["value"] == "v1"
        assert b["style"] == "primary"

    def test_button_invalid_style_ignored(self):
        b = button("Go", "go_action", style="invalid")
        assert "style" not in b

    def test_static_select(self):
        s = static_select("Pick one", "select_it", [("A", "a"), ("B", "b")])
        assert s["type"] == "static_select"
        assert s["action_id"] == "select_it"
        assert len(s["options"]) == 2
        assert s["options"][0]["value"] == "a"


class TestNewFormatters:
    def test_agent_completion_success(self):
        msg = notify_agent_completion("code-reviewer", "review my PR", elapsed=2.5)
        assert "code-reviewer" in msg
        assert "success" in msg
        assert "2.5s" in msg

    def test_agent_completion_error(self):
        msg = notify_agent_completion("git-ops", "commit", status="error")
        assert msg.startswith("\u274c")

    def test_agent_completion_long_query_truncated(self):
        long_q = "x" * 100
        msg = notify_agent_completion("a", long_q)
        assert "..." in msg

    def test_error_notification(self):
        msg = notify_error("app.py", "NullPointerException")
        assert "ERROR" in msg
        assert "app.py" in msg

    def test_error_warning(self):
        msg = notify_error("router", "slow query", severity="warning")
        assert "WARNING" in msg

    def test_error_with_traceback(self):
        msg = notify_error("x", "err", traceback="line1\nline2")
        assert "line1" in msg

    def test_pr_review_approved(self):
        msg = notify_pr_review("Fix auth", 42, "approved")
        assert "#42" in msg
        assert "approved" in msg

    def test_pr_review_changes_requested(self):
        msg = notify_pr_review("Fix auth", 42, "changes_requested", issues=3, url="https://gh/pr/42")
        assert "3 issue" in msg
        assert "View PR" in msg

    def test_audit_result_all_pass(self):
        msg = notify_audit_result(100, 14, 14, 0, repo="my-repo")
        assert "100/100" in msg
        assert "my-repo" in msg
        assert msg.startswith("\u2705")

    def test_audit_result_some_fail(self):
        msg = notify_audit_result(72, 14, 10, 4)
        assert "4 failed" in msg

    def test_daily_digest(self):
        msg = notify_daily_digest(agents_used=5, queries_handled=42, errors=1, top_agent="auto-pilot")
        assert "42" in msg
        assert "auto-pilot" in msg


class TestBlockKitFormatters:
    def test_agent_completion_blocks(self):
        blocks = notify_agent_completion_blocks("code-reviewer", "review PR", elapsed=1.0)
        assert len(blocks) >= 3
        assert blocks[0]["type"] == "header"
        assert any("code-reviewer" in json.dumps(b) for b in blocks)

    def test_agent_selection_blocks(self):
        blocks = notify_agent_selection_blocks("help me", ["auto-pilot", "git-ops"])
        assert any(b["type"] == "actions" for b in blocks)

    def test_approval_blocks(self):
        blocks = notify_approval_blocks("deploy to prod", "v2.1.0", request_id="req-123")
        actions_block = [b for b in blocks if b["type"] == "actions"][0]
        assert len(actions_block["elements"]) == 2


# ---------------------------------------------------------------------------
# 2. Channel-specific routing
# ---------------------------------------------------------------------------

from code_agents.integrations.slack_bot import SlackBot


class TestChannelRouting:
    def test_parse_channel_map_empty(self):
        with patch.dict("os.environ", {"CODE_AGENTS_SLACK_CHANNEL_MAP": ""}):
            bot = SlackBot()
        assert bot._channel_map == {}

    def test_parse_channel_map_single(self):
        with patch.dict("os.environ", {"CODE_AGENTS_SLACK_CHANNEL_MAP": "C123=jenkins-cicd"}):
            bot = SlackBot()
        assert bot._channel_map == {"C123": "jenkins-cicd"}

    def test_parse_channel_map_multiple(self):
        with patch.dict("os.environ", {
            "CODE_AGENTS_SLACK_CHANNEL_MAP": "C1=jenkins-cicd, C2=code-reviewer, C3=git-ops"
        }):
            bot = SlackBot()
        assert len(bot._channel_map) == 3
        assert bot._channel_map["C2"] == "code-reviewer"

    def test_parse_channel_map_strips_hash(self):
        with patch.dict("os.environ", {"CODE_AGENTS_SLACK_CHANNEL_MAP": "#deployments=jenkins-cicd"}):
            bot = SlackBot()
        assert "deployments" in bot._channel_map

    def test_parse_channel_map_ignores_invalid(self):
        with patch.dict("os.environ", {"CODE_AGENTS_SLACK_CHANNEL_MAP": "garbage,C1=ok"}):
            bot = SlackBot()
        assert len(bot._channel_map) == 1

    def test_get_channel_agent_mapped(self):
        with patch.dict("os.environ", {"CODE_AGENTS_SLACK_CHANNEL_MAP": "C123=jenkins-cicd"}):
            bot = SlackBot()
        assert bot.get_channel_agent("C123") == "jenkins-cicd"

    def test_get_channel_agent_unmapped(self):
        with patch.dict("os.environ", {"CODE_AGENTS_SLACK_CHANNEL_MAP": "C123=jenkins-cicd"}):
            bot = SlackBot()
        assert bot.get_channel_agent("C999") == ""

    def test_handle_event_uses_channel_routing(self):
        with patch.dict("os.environ", {
            "CODE_AGENTS_SLACK_CHANNEL_MAP": "C100=jenkins-cicd",
            "CODE_AGENTS_SLACK_BOT_TOKEN": "",
        }):
            bot = SlackBot()

        with patch.object(bot, "get_bot_user_id", return_value=""):
            with patch.object(bot, "send_message"):
                with patch.object(bot, "delegate_to_agent", return_value="ok") as mock_delegate:
                    bot.handle_event({
                        "text": "some random text",
                        "channel": "C100",
                        "ts": "123",
                        "user": "U999",
                    })
        # Should use channel mapping, not keyword detection
        mock_delegate.assert_called_once_with("some random text", "jenkins-cicd")


# ---------------------------------------------------------------------------
# 3. Slack router — slash command
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient
from code_agents.routers.slack_bot import router as slack_router
from fastapi import FastAPI

_test_app = FastAPI()
_test_app.include_router(slack_router)
_client = TestClient(_test_app)


class TestSlashCommandEndpoint:
    def test_slash_empty_text_shows_usage(self):
        with patch("code_agents.routers.slack_bot._get_bot") as mock_bot:
            mock_bot.return_value = MagicMock(signing_secret="")
            resp = _client.post(
                "/slack/slash",
                content="text=&user_id=U1&channel_id=C1&response_url=",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response_type"] == "ephemeral"
        assert "Usage" in data["text"]

    def test_slash_with_text_returns_processing(self):
        mock_bot_instance = MagicMock()
        mock_bot_instance.signing_secret = ""
        mock_bot_instance.detect_agent.return_value = "auto-pilot"

        with patch("code_agents.routers.slack_bot._get_bot", return_value=mock_bot_instance):
            resp = _client.post(
                "/slack/slash",
                content="text=review+my+code&user_id=U1&channel_id=C1&response_url=http://x",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response_type"] == "in_channel"
        assert "Processing" in data["text"]

    def test_slash_signature_failure(self):
        mock_bot_instance = MagicMock()
        mock_bot_instance.signing_secret = "secret123"
        mock_bot_instance.verify_signature.return_value = False

        with patch("code_agents.routers.slack_bot._get_bot", return_value=mock_bot_instance):
            resp = _client.post(
                "/slack/slash",
                content="text=hello",
                headers={
                    "X-Slack-Request-Timestamp": "0",
                    "X-Slack-Signature": "bad",
                },
            )
        assert resp.status_code == 401


class TestInteractiveEndpoint:
    def test_interactive_no_actions_returns_ok(self):
        payload = json.dumps({"type": "block_actions", "actions": [], "user": {}, "channel": {}})
        with patch("code_agents.routers.slack_bot._get_bot") as mock_bot:
            mock_bot.return_value = MagicMock(signing_secret="")
            resp = _client.post(
                "/slack/interactive",
                content=f"payload={payload}",
            )
        assert resp.status_code == 200

    def test_interactive_approve_action(self):
        payload = json.dumps({
            "type": "block_actions",
            "user": {"id": "U123"},
            "channel": {"id": "C123"},
            "response_url": "",
            "actions": [{"action_id": "approve_action", "value": "req-1"}],
        })
        with patch("code_agents.routers.slack_bot._get_bot") as mock_bot:
            mock_bot.return_value = MagicMock(signing_secret="")
            resp = _client.post(
                "/slack/interactive",
                content=f"payload={payload}",
            )
        data = resp.json()
        assert "Approved" in data["text"]
        assert "U123" in data["text"]

    def test_interactive_reject_action(self):
        payload = json.dumps({
            "type": "block_actions",
            "user": {"id": "U123"},
            "channel": {"id": "C123"},
            "response_url": "",
            "actions": [{"action_id": "reject_action", "value": "req-1"}],
        })
        with patch("code_agents.routers.slack_bot._get_bot") as mock_bot:
            mock_bot.return_value = MagicMock(signing_secret="")
            resp = _client.post(
                "/slack/interactive",
                content=f"payload={payload}",
            )
        data = resp.json()
        assert "Rejected" in data["text"]

    def test_interactive_select_agent(self):
        payload = json.dumps({
            "type": "block_actions",
            "user": {"id": "U1"},
            "channel": {"id": "C1"},
            "response_url": "",
            "actions": [{
                "action_id": "select_agent",
                "type": "static_select",
                "selected_option": {"value": "git-ops"},
            }],
            "message": {"blocks": []},
        })
        with patch("code_agents.routers.slack_bot._get_bot") as mock_bot:
            mock_bot.return_value = MagicMock(signing_secret="")
            resp = _client.post(
                "/slack/interactive",
                content=f"payload={payload}",
            )
        data = resp.json()
        assert "git-ops" in data["text"]

    def test_interactive_auto_detect(self):
        mock_bot_instance = MagicMock()
        mock_bot_instance.signing_secret = ""
        mock_bot_instance.detect_agent.return_value = "jenkins-cicd"

        payload = json.dumps({
            "type": "block_actions",
            "user": {"id": "U1"},
            "channel": {"id": "C1"},
            "response_url": "",
            "actions": [{"action_id": "auto_detect_agent", "value": ""}],
            "message": {"blocks": [
                {"text": {"text": "*Query:*\n>deploy my app"}}
            ]},
        })
        with patch("code_agents.routers.slack_bot._get_bot", return_value=mock_bot_instance):
            resp = _client.post(
                "/slack/interactive",
                content=f"payload={payload}",
            )
        data = resp.json()
        assert "jenkins-cicd" in data["text"]

    def test_interactive_signature_failure(self):
        mock_bot_instance = MagicMock()
        mock_bot_instance.signing_secret = "secret"
        mock_bot_instance.verify_signature.return_value = False

        with patch("code_agents.routers.slack_bot._get_bot", return_value=mock_bot_instance):
            resp = _client.post(
                "/slack/interactive",
                content="payload={}",
                headers={
                    "X-Slack-Request-Timestamp": "0",
                    "X-Slack-Signature": "bad",
                },
            )
        assert resp.status_code == 401


class TestSlackStatusEndpoint:
    def test_status_unconfigured(self):
        with patch.dict("os.environ", {}, clear=True):
            resp = _client.get("/slack/status")
        data = resp.json()
        assert data["configured"] is False
        assert "endpoints" in data

    def test_status_configured(self):
        with patch.dict("os.environ", {
            "CODE_AGENTS_SLACK_BOT_TOKEN": "xoxb-test",
            "CODE_AGENTS_SLACK_SIGNING_SECRET": "secret",
            "CODE_AGENTS_SLACK_WEBHOOK_URL": "https://hooks.slack.com/x",
            "CODE_AGENTS_SLACK_CHANNEL_MAP": "C1=auto-pilot",
        }):
            resp = _client.get("/slack/status")
        data = resp.json()
        assert data["configured"] is True
        assert data["webhook_url_set"] is True
        assert data["channel_map"] == "C1=auto-pilot"


# ---------------------------------------------------------------------------
# 4. Router helpers
# ---------------------------------------------------------------------------

from code_agents.routers.slack_bot import _extract_query_from_blocks


class TestExtractQueryFromBlocks:
    def test_extracts_query(self):
        msg = {"blocks": [{"text": {"text": "*Query:*\n>deploy to prod"}}]}
        assert _extract_query_from_blocks(msg) == "deploy to prod"

    def test_empty_blocks(self):
        assert _extract_query_from_blocks({"blocks": []}) == ""

    def test_no_query_block(self):
        msg = {"blocks": [{"text": {"text": "no query here"}}]}
        assert _extract_query_from_blocks(msg) == ""


# ---------------------------------------------------------------------------
# 5. CLI commands
# ---------------------------------------------------------------------------

from code_agents.cli.cli_slack import cmd_slack


class TestCLISlack:
    def test_no_args_shows_help(self, capsys):
        cmd_slack()
        out = capsys.readouterr().out
        assert "Slack Integration" in out

    def test_help_subcommand(self, capsys):
        cmd_slack(["help"])
        out = capsys.readouterr().out
        assert "slack test" in out

    def test_status_unconfigured(self, capsys):
        with patch.dict("os.environ", {}, clear=True):
            with patch("code_agents.cli.cli_slack._api_get", return_value=None):
                cmd_slack(["status"])
        out = capsys.readouterr().out
        assert "Slack Configuration" in out

    def test_status_configured(self, capsys):
        with patch.dict("os.environ", {
            "CODE_AGENTS_SLACK_BOT_TOKEN": "xoxb-test",
            "CODE_AGENTS_SLACK_SIGNING_SECRET": "secret",
            "CODE_AGENTS_SLACK_WEBHOOK_URL": "https://hooks.slack.com/x",
        }):
            with patch("code_agents.cli.cli_slack._api_get", return_value={"configured": True}):
                cmd_slack(["status"])
        out = capsys.readouterr().out
        assert "reachable" in out

    def test_test_no_url(self, capsys):
        with patch.dict("os.environ", {}, clear=True):
            cmd_slack(["test"])
        out = capsys.readouterr().out
        assert "No webhook URL" in out

    def test_test_success(self, capsys):
        with patch("code_agents.cli.cli_slack.asyncio") as mock_asyncio:
            mock_asyncio.run.return_value = True
            cmd_slack(["test", "https://hooks.slack.com/test"])
        out = capsys.readouterr().out
        assert "sent successfully" in out

    def test_test_failure(self, capsys):
        with patch("code_agents.cli.cli_slack.asyncio") as mock_asyncio:
            mock_asyncio.run.return_value = False
            cmd_slack(["test", "https://hooks.slack.com/test"])
        out = capsys.readouterr().out
        assert "Failed" in out

    def test_send_no_message(self, capsys):
        cmd_slack(["send"])
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_send_no_url(self, capsys):
        with patch.dict("os.environ", {}, clear=True):
            cmd_slack(["send", "hello"])
        out = capsys.readouterr().out
        assert "No webhook URL" in out

    def test_send_success(self, capsys):
        with patch.dict("os.environ", {"CODE_AGENTS_SLACK_WEBHOOK_URL": "https://hooks.slack.com/x"}):
            with patch("code_agents.cli.cli_slack.asyncio") as mock_asyncio:
                mock_asyncio.run.return_value = True
                cmd_slack(["send", "deploy", "complete"])
        out = capsys.readouterr().out
        assert "sent" in out.lower()

    def test_channels_empty(self, capsys):
        with patch.dict("os.environ", {"CODE_AGENTS_SLACK_CHANNEL_MAP": ""}):
            cmd_slack(["channels"])
        out = capsys.readouterr().out
        assert "No channel mappings" in out

    def test_channels_configured(self, capsys):
        with patch.dict("os.environ", {"CODE_AGENTS_SLACK_CHANNEL_MAP": "C1=jenkins-cicd,C2=git-ops"}):
            cmd_slack(["channels"])
        out = capsys.readouterr().out
        assert "jenkins-cicd" in out
        assert "git-ops" in out

    def test_unknown_subcommand(self, capsys):
        cmd_slack(["foobar"])
        out = capsys.readouterr().out
        assert "Unknown subcommand" in out


# ---------------------------------------------------------------------------
# 6. CLI registry
# ---------------------------------------------------------------------------

from code_agents.cli.registry import COMMAND_REGISTRY


class TestCLIRegistry:
    def test_slack_command_registered(self):
        assert "slack" in COMMAND_REGISTRY
        entry = COMMAND_REGISTRY["slack"]
        assert entry.takes_args is True
        assert "Slack" in entry.help


# ---------------------------------------------------------------------------
# 7. Slash registry
# ---------------------------------------------------------------------------

from code_agents.chat.slash_registry import SLASH_REGISTRY


class TestSlashRegistry:
    def test_slack_slash_registered(self):
        assert "/slack" in SLASH_REGISTRY
        entry = SLASH_REGISTRY["/slack"]
        assert entry.group == "tools"
        assert entry.handler_func == "_handle_tools"
