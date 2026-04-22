"""Tests for notifications.py — Slack webhook notifications."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from code_agents.domain.notifications import (
    send_slack,
    notify_build_status,
    notify_deploy_status,
    notify_test_status,
)


# ---------------------------------------------------------------------------
# send_slack (async)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_slack_no_url_returns_false():
    with patch.dict("os.environ", {}, clear=True):
        result = await send_slack("hello")
    assert result is False


@pytest.mark.asyncio
async def test_send_slack_explicit_url_success():
    mock_resp = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("code_agents.domain.notifications.httpx.AsyncClient", return_value=mock_client):
        result = await send_slack("test msg", webhook_url="https://hooks.slack.com/test")
    assert result is True
    mock_client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_slack_env_url():
    mock_resp = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.dict("os.environ", {"CODE_AGENTS_SLACK_WEBHOOK_URL": "https://hooks.slack.com/env"}):
        with patch("code_agents.domain.notifications.httpx.AsyncClient", return_value=mock_client):
            result = await send_slack("msg from env")
    assert result is True


@pytest.mark.asyncio
async def test_send_slack_non_200_returns_false():
    mock_resp = MagicMock(status_code=500)
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("code_agents.domain.notifications.httpx.AsyncClient", return_value=mock_client):
        result = await send_slack("fail", webhook_url="https://hooks.slack.com/x")
    assert result is False


@pytest.mark.asyncio
async def test_send_slack_exception_returns_false():
    mock_client = AsyncMock()
    mock_client.post.side_effect = Exception("network error")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("code_agents.domain.notifications.httpx.AsyncClient", return_value=mock_client):
        result = await send_slack("fail", webhook_url="https://hooks.slack.com/x")
    assert result is False


# ---------------------------------------------------------------------------
# notify_build_status
# ---------------------------------------------------------------------------

def test_build_status_success():
    msg = notify_build_status("my-job", "SUCCESS", build_number=42)
    assert "SUCCESS" in msg
    assert "my-job" in msg
    assert "#42" in msg
    assert msg.startswith("\u2705")  # checkmark emoji


def test_build_status_failure():
    msg = notify_build_status("my-job", "FAILURE", build_number=1)
    assert "FAILURE" in msg
    assert msg.startswith("\u274c")  # x emoji


def test_build_status_pending():
    msg = notify_build_status("my-job", "PENDING", build_number=1)
    assert "\u23f3" in msg  # hourglass


def test_build_status_with_url():
    msg = notify_build_status("j", "SUCCESS", url="https://jenkins/42")
    assert "View build" in msg
    assert "https://jenkins/42" in msg


def test_build_status_without_url():
    msg = notify_build_status("j", "SUCCESS")
    assert "View build" not in msg


# ---------------------------------------------------------------------------
# notify_deploy_status
# ---------------------------------------------------------------------------

def test_deploy_status_healthy():
    msg = notify_deploy_status("my-app", "prod", "Healthy")
    assert "my-app" in msg
    assert "prod" in msg
    assert "\U0001f680" in msg  # rocket


def test_deploy_status_degraded():
    msg = notify_deploy_status("app", "staging", "Degraded")
    assert "\U0001f534" in msg  # red circle


def test_deploy_status_unknown():
    msg = notify_deploy_status("app", "staging", "Unknown")
    assert "\U0001f534" in msg


def test_deploy_status_syncing():
    msg = notify_deploy_status("app", "dev", "Syncing")
    assert "\u23f3" in msg  # hourglass


def test_deploy_status_with_version():
    msg = notify_deploy_status("app", "prod", "Healthy", version="1.2.3")
    assert "v1.2.3" in msg


def test_deploy_status_without_version():
    msg = notify_deploy_status("app", "prod", "Healthy")
    assert "(v" not in msg


# ---------------------------------------------------------------------------
# notify_test_status
# ---------------------------------------------------------------------------

def test_test_status_all_pass():
    msg = notify_test_status(10, 0, 10)
    assert "10/10 passed" in msg
    assert "0 failed" in msg
    assert "\u2705" in msg


def test_test_status_with_failures():
    msg = notify_test_status(8, 2, 10)
    assert "8/10 passed" in msg
    assert "2 failed" in msg
    assert "\u274c" in msg


def test_test_status_with_branch():
    msg = notify_test_status(5, 0, 5, branch="feature-x")
    assert "feature-x" in msg


def test_test_status_without_branch():
    msg = notify_test_status(5, 0, 5)
    assert "(`" not in msg
