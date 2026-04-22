"""Tests for routers/atlassian_oauth_web.py — full coverage."""

from __future__ import annotations

import html
import os
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from code_agents.routers.atlassian_oauth_web import (
    router,
    _cleanup_states,
    _pending_state,
    _public_base,
    _open_webui_public_url,
    _success_redirect_url,
    _require_oauth_config,
    CALLBACK_SUFFIX,
    _STATE_TTL_SEC,
)


@pytest.fixture
def oauth_client():
    """Create a test client with the OAuth router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_pending_state():
    """Clear pending state before each test."""
    _pending_state.clear()
    yield
    _pending_state.clear()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestPublicBase:
    def test_from_env_code_agents(self):
        mock_request = MagicMock()
        with patch.dict(os.environ, {"CODE_AGENTS_PUBLIC_BASE_URL": "https://api.example.com/"}):
            result = _public_base(mock_request)
        assert result == "https://api.example.com"

    def test_from_env_atlassian_oauth(self):
        mock_request = MagicMock()
        with patch.dict(os.environ, {
            "CODE_AGENTS_PUBLIC_BASE_URL": "",
            "ATLASSIAN_OAUTH_PUBLIC_BASE_URL": "https://oauth.example.com/",
        }, clear=False):
            result = _public_base(mock_request)
        assert result == "https://oauth.example.com"

    def test_fallback_to_request_base(self):
        mock_request = MagicMock()
        mock_request.base_url = "http://localhost:8000/"
        with patch.dict(os.environ, {
            "CODE_AGENTS_PUBLIC_BASE_URL": "",
            "ATLASSIAN_OAUTH_PUBLIC_BASE_URL": "",
        }, clear=False):
            result = _public_base(mock_request)
        assert result == "http://localhost:8000"


class TestOpenWebuiPublicUrl:
    def test_from_open_webui_public_url(self):
        with patch.dict(os.environ, {"OPEN_WEBUI_PUBLIC_URL": "http://localhost:8080/"}):
            result = _open_webui_public_url()
        assert result == "http://localhost:8080"

    def test_from_open_webui_url(self):
        with patch.dict(os.environ, {
            "OPEN_WEBUI_PUBLIC_URL": "",
            "OPEN_WEBUI_URL": "http://webui:8080/",
        }, clear=False):
            result = _open_webui_public_url()
        assert result == "http://webui:8080"

    def test_returns_none_when_unset(self):
        with patch.dict(os.environ, {
            "OPEN_WEBUI_PUBLIC_URL": "",
            "OPEN_WEBUI_URL": "",
        }, clear=False):
            result = _open_webui_public_url()
        assert result is None


class TestSuccessRedirectUrl:
    def test_returns_url_when_set(self):
        with patch.dict(os.environ, {"ATLASSIAN_OAUTH_SUCCESS_REDIRECT": "https://my-app.com/done"}):
            result = _success_redirect_url()
        assert result == "https://my-app.com/done"

    def test_returns_none_when_empty(self):
        with patch.dict(os.environ, {"ATLASSIAN_OAUTH_SUCCESS_REDIRECT": ""}):
            result = _success_redirect_url()
        assert result is None

    def test_returns_none_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ATLASSIAN_OAUTH_SUCCESS_REDIRECT", None)
            result = _success_redirect_url()
        assert result is None


class TestRequireOauthConfig:
    def test_missing_client_id(self):
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
        }):
            with pytest.raises(HTTPException) as exc:
                _require_oauth_config()
            assert exc.value.status_code == 500
            assert "CLIENT_ID" in exc.value.detail

    def test_missing_client_secret(self):
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
        }):
            with pytest.raises(HTTPException) as exc:
                _require_oauth_config()
            assert exc.value.status_code == 500

    def test_missing_scopes(self):
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "",
        }):
            with pytest.raises(HTTPException) as exc:
                _require_oauth_config()
            assert exc.value.status_code == 500
            assert "SCOPES" in exc.value.detail

    def test_success(self):
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira offline_access",
        }):
            cid, sec, scopes = _require_oauth_config()
        assert cid == "cid"
        assert sec == "sec"
        assert scopes == "read:jira offline_access"


class TestCleanupStates:
    def test_removes_expired(self):
        _pending_state["old"] = (time.time() - 100, "uri1")
        _pending_state["fresh"] = (time.time() + 600, "uri2")
        _cleanup_states()
        assert "old" not in _pending_state
        assert "fresh" in _pending_state


# ---------------------------------------------------------------------------
# OAuth Home endpoint
# ---------------------------------------------------------------------------


class TestOauthHome:
    def test_renders_html(self, oauth_client):
        with patch.dict(os.environ, {
            "CODE_AGENTS_PUBLIC_BASE_URL": "https://api.test",
            "OPEN_WEBUI_PUBLIC_URL": "",
            "OPEN_WEBUI_URL": "",
        }, clear=False):
            with patch("code_agents.routers.atlassian_oauth_web.atlassian_cloud_site_url", return_value=None):
                resp = oauth_client.get("/oauth/atlassian")
        assert resp.status_code == 200
        assert "Atlassian" in resp.text
        assert "https://api.test/oauth/atlassian/callback" in resp.text

    def test_renders_site_block(self, oauth_client):
        with patch.dict(os.environ, {
            "CODE_AGENTS_PUBLIC_BASE_URL": "https://api.test",
        }, clear=False):
            with patch("code_agents.routers.atlassian_oauth_web.atlassian_cloud_site_url", return_value="https://mysite.atlassian.net"):
                resp = oauth_client.get("/oauth/atlassian")
        assert "mysite.atlassian.net" in resp.text

    def test_renders_webui_note(self, oauth_client):
        with patch.dict(os.environ, {
            "CODE_AGENTS_PUBLIC_BASE_URL": "https://api.test",
            "OPEN_WEBUI_PUBLIC_URL": "http://localhost:8080",
        }, clear=False):
            with patch("code_agents.routers.atlassian_oauth_web.atlassian_cloud_site_url", return_value=None):
                resp = oauth_client.get("/oauth/atlassian")
        assert "localhost:8080" in resp.text


# ---------------------------------------------------------------------------
# OAuth Start endpoint
# ---------------------------------------------------------------------------


class TestOauthStart:
    def test_redirects_to_atlassian(self, oauth_client):
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
            "CODE_AGENTS_PUBLIC_BASE_URL": "https://api.test",
        }):
            with patch("code_agents.routers.atlassian_oauth_web.build_authorize_url", return_value="https://auth.atlassian.com/authorize?...") as mock_build:
                resp = oauth_client.get("/oauth/atlassian/start", follow_redirects=False)
        assert resp.status_code == 302
        assert "atlassian" in resp.headers["location"]
        # State should be stored
        assert len(_pending_state) == 1

    def test_missing_config_returns_500(self, oauth_client):
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "",
            "ATLASSIAN_OAUTH_SCOPES": "",
        }):
            resp = oauth_client.get("/oauth/atlassian/start")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# OAuth Callback endpoint
# ---------------------------------------------------------------------------


class TestOauthCallback:
    def test_error_param(self, oauth_client):
        resp = oauth_client.get("/oauth/atlassian/callback?error=access_denied&error_description=User+denied")
        assert resp.status_code == 400
        assert "User denied" in resp.text

    def test_error_no_description(self, oauth_client):
        resp = oauth_client.get("/oauth/atlassian/callback?error=server_error")
        assert resp.status_code == 400
        assert "server_error" in resp.text

    def test_missing_code(self, oauth_client):
        resp = oauth_client.get("/oauth/atlassian/callback?state=abc")
        assert resp.status_code == 400

    def test_missing_state(self, oauth_client):
        resp = oauth_client.get("/oauth/atlassian/callback?code=abc")
        assert resp.status_code == 400

    def test_invalid_state(self, oauth_client):
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
        }):
            resp = oauth_client.get("/oauth/atlassian/callback?code=abc&state=invalid_state")
        assert resp.status_code == 400

    def test_expired_state(self, oauth_client):
        _pending_state["expired_state"] = (time.time() - 10, "https://api.test/oauth/atlassian/callback")
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
        }):
            resp = oauth_client.get("/oauth/atlassian/callback?code=abc&state=expired_state")
        assert resp.status_code == 400

    def test_successful_callback_with_webui(self, oauth_client):
        state = "valid_state_123"
        _pending_state[state] = (time.time() + 600, "https://api.test/oauth/atlassian/callback")
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
            "OPEN_WEBUI_PUBLIC_URL": "http://localhost:8080",
            "ATLASSIAN_OAUTH_SUCCESS_REDIRECT": "",
        }):
            with patch("code_agents.routers.atlassian_oauth_web.exchange_code_for_tokens", return_value={"access_token": "at", "refresh_token": "rt"}):
                with patch("code_agents.routers.atlassian_oauth_web.persist_oauth_token_response"):
                    resp = oauth_client.get(f"/oauth/atlassian/callback?code=auth_code&state={state}")
        assert resp.status_code == 200
        assert "Signed in" in resp.text
        assert "localhost:8080" in resp.text

    def test_successful_callback_no_webui(self, oauth_client):
        state = "valid_state_456"
        _pending_state[state] = (time.time() + 600, "https://api.test/oauth/atlassian/callback")
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
            "OPEN_WEBUI_PUBLIC_URL": "",
            "OPEN_WEBUI_URL": "",
            "ATLASSIAN_OAUTH_SUCCESS_REDIRECT": "",
        }):
            with patch("code_agents.routers.atlassian_oauth_web.exchange_code_for_tokens", return_value={"access_token": "at"}):
                with patch("code_agents.routers.atlassian_oauth_web.persist_oauth_token_response"):
                    resp = oauth_client.get(f"/oauth/atlassian/callback?code=auth_code&state={state}")
        assert resp.status_code == 200
        assert "Signed in" in resp.text
        assert "localhost:8080" in resp.text  # Default hint

    def test_successful_callback_with_redirect(self, oauth_client):
        state = "valid_state_789"
        _pending_state[state] = (time.time() + 600, "https://api.test/oauth/atlassian/callback")
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
            "ATLASSIAN_OAUTH_SUCCESS_REDIRECT": "https://my-app.com/done",
        }):
            with patch("code_agents.routers.atlassian_oauth_web.exchange_code_for_tokens", return_value={"access_token": "at"}):
                with patch("code_agents.routers.atlassian_oauth_web.persist_oauth_token_response"):
                    resp = oauth_client.get(f"/oauth/atlassian/callback?code=auth_code&state={state}", follow_redirects=False)
        assert resp.status_code == 302
        assert "my-app.com/done" in resp.headers["location"]

    def test_token_exchange_http_4xx_error(self, oauth_client):
        state = "valid_err_1"
        _pending_state[state] = (time.time() + 600, "https://api.test/oauth/atlassian/callback")
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
        }):
            with patch("code_agents.routers.atlassian_oauth_web.exchange_code_for_tokens",
                        side_effect=RuntimeError("Code exchange failed HTTP 400: invalid_grant")):
                resp = oauth_client.get(f"/oauth/atlassian/callback?code=bad_code&state={state}")
        assert resp.status_code == 400
        assert "Token exchange failed" in resp.text
        assert "Common causes" in resp.text

    def test_token_exchange_cert_error(self, oauth_client):
        state = "valid_err_2"
        _pending_state[state] = (time.time() + 600, "https://api.test/oauth/atlassian/callback")
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
        }):
            with patch("code_agents.routers.atlassian_oauth_web.exchange_code_for_tokens",
                        side_effect=RuntimeError("certificate verification failed CERTIFICATE_VERIFY_FAILED")):
                resp = oauth_client.get(f"/oauth/atlassian/callback?code=bad_code&state={state}")
        assert resp.status_code == 503
        assert "Quick fix" in resp.text

    def test_token_exchange_5xx_error(self, oauth_client):
        state = "valid_err_3"
        _pending_state[state] = (time.time() + 600, "https://api.test/oauth/atlassian/callback")
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
        }):
            with patch("code_agents.routers.atlassian_oauth_web.exchange_code_for_tokens",
                        side_effect=RuntimeError("Code exchange failed HTTP 500: server error")):
                resp = oauth_client.get(f"/oauth/atlassian/callback?code=bad_code&state={state}")
        assert resp.status_code == 502

    def test_token_exchange_connection_error(self, oauth_client):
        state = "valid_err_4"
        _pending_state[state] = (time.time() + 600, "https://api.test/oauth/atlassian/callback")
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
        }):
            with patch("code_agents.routers.atlassian_oauth_web.exchange_code_for_tokens",
                        side_effect=RuntimeError("Connection to auth.atlassian.com failed")):
                resp = oauth_client.get(f"/oauth/atlassian/callback?code=bad_code&state={state}")
        assert resp.status_code == 503

    def test_token_exchange_generic_error(self, oauth_client):
        state = "valid_err_5"
        _pending_state[state] = (time.time() + 600, "https://api.test/oauth/atlassian/callback")
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "cid",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "sec",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira",
        }):
            with patch("code_agents.routers.atlassian_oauth_web.exchange_code_for_tokens",
                        side_effect=RuntimeError("Some other error")):
                resp = oauth_client.get(f"/oauth/atlassian/callback?code=bad_code&state={state}")
        assert resp.status_code == 502
        assert "Token exchange failed" in resp.text
