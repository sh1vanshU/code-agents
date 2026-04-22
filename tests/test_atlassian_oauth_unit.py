"""Unit tests for code_agents/atlassian_oauth.py."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from code_agents.domain.atlassian_oauth import (
    AUTH_BASE,
    AUTHORIZE_URL,
    TOKEN_URL,
    _cache_path,
    _httpx_verify,
    _load_cache,
    _parse_redirect_uri,
    _persist_tokens,
    _post_token,
    _save_cache,
    _token_expired,
    build_authorize_url,
    clear_token_cache,
    exchange_code_for_tokens,
    get_valid_access_token,
    interactive_login,
    persist_oauth_token_response,
    refresh_access_token,
)


# ---------------------------------------------------------------------------
# _httpx_verify
# ---------------------------------------------------------------------------

class TestHttpxVerify:
    def test_default_returns_certifi(self, monkeypatch):
        for key in ("ATLASSIAN_OAUTH_HTTPS_VERIFY", "CODE_AGENTS_HTTPS_VERIFY",
                     "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
            monkeypatch.delenv(key, raising=False)
        result = _httpx_verify()
        assert isinstance(result, str)
        assert "certifi" in result or result.endswith(".pem")

    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_HTTPS_VERIFY", "0")
        assert _httpx_verify() is False

    def test_disabled_false_string(self, monkeypatch):
        monkeypatch.setenv("CODE_AGENTS_HTTPS_VERIFY", "false")
        monkeypatch.delenv("ATLASSIAN_OAUTH_HTTPS_VERIFY", raising=False)
        assert _httpx_verify() is False

    def test_custom_cert_file(self, monkeypatch, tmp_path):
        cert = tmp_path / "custom.pem"
        cert.write_text("CERT")
        monkeypatch.setenv("ATLASSIAN_OAUTH_HTTPS_VERIFY", str(cert))
        result = _httpx_verify()
        assert result == str(cert)

    def test_ssl_cert_file_env(self, monkeypatch, tmp_path):
        cert = tmp_path / "ca.pem"
        cert.write_text("CA")
        monkeypatch.delenv("ATLASSIAN_OAUTH_HTTPS_VERIFY", raising=False)
        monkeypatch.delenv("CODE_AGENTS_HTTPS_VERIFY", raising=False)
        monkeypatch.setenv("SSL_CERT_FILE", str(cert))
        result = _httpx_verify()
        assert result == str(cert)

    def test_requests_ca_bundle(self, monkeypatch, tmp_path):
        cert = tmp_path / "bundle.pem"
        cert.write_text("BUNDLE")
        monkeypatch.delenv("ATLASSIAN_OAUTH_HTTPS_VERIFY", raising=False)
        monkeypatch.delenv("CODE_AGENTS_HTTPS_VERIFY", raising=False)
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(cert))
        result = _httpx_verify()
        assert result == str(cert)


# ---------------------------------------------------------------------------
# _post_token
# ---------------------------------------------------------------------------

class TestPostToken:
    @patch("code_agents.domain.atlassian_oauth._httpx_verify", return_value=False)
    @patch("code_agents.domain.atlassian_oauth.httpx.Client")
    def test_success(self, mock_client_cls, mock_verify):
        mock_resp = MagicMock()
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client
        result = _post_token({"grant_type": "authorization_code"})
        assert result is mock_resp

    @patch("code_agents.domain.atlassian_oauth._httpx_verify", return_value=False)
    @patch("code_agents.domain.atlassian_oauth.httpx.Client")
    def test_cert_verify_failed(self, mock_client_cls, mock_verify):
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = httpx.ConnectError("CERTIFICATE_VERIFY_FAILED")
        mock_client_cls.return_value = mock_client
        with pytest.raises(RuntimeError, match="certificate verification failed"):
            _post_token({})

    @patch("code_agents.domain.atlassian_oauth._httpx_verify", return_value=False)
    @patch("code_agents.domain.atlassian_oauth.httpx.Client")
    def test_connection_error(self, mock_client_cls, mock_verify):
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client_cls.return_value = mock_client
        with pytest.raises(RuntimeError, match="Connection.*failed"):
            _post_token({})


# ---------------------------------------------------------------------------
# Cache functions
# ---------------------------------------------------------------------------

class TestCache:
    def test_cache_path_default(self, monkeypatch):
        monkeypatch.delenv("ATLASSIAN_OAUTH_TOKEN_CACHE", raising=False)
        p = _cache_path()
        assert ".code-agents-atlassian-oauth.json" in str(p)

    def test_cache_path_custom(self, monkeypatch, tmp_path):
        custom = tmp_path / "tokens.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(custom))
        assert _cache_path() == custom

    def test_save_and_load(self, monkeypatch, tmp_path):
        cache_file = tmp_path / "cache.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        data = {"access_token": "tok", "client_id": "cid"}
        _save_cache(data)
        loaded = _load_cache()
        assert loaded == data

    def test_load_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(tmp_path / "missing.json"))
        assert _load_cache() is None

    def test_load_corrupt(self, monkeypatch, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{{{invalid")
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(f))
        assert _load_cache() is None


# ---------------------------------------------------------------------------
# _token_expired
# ---------------------------------------------------------------------------

class TestTokenExpired:
    def test_none_expires_at(self):
        assert _token_expired(None) is True

    def test_not_expired(self):
        assert _token_expired(time.time() + 3600) is False

    def test_expired(self):
        assert _token_expired(time.time() - 100) is True

    def test_within_skew(self):
        # Expires in 30 seconds, but skew is 60 → should be considered expired
        assert _token_expired(time.time() + 30, skew_seconds=60) is True


# ---------------------------------------------------------------------------
# build_authorize_url
# ---------------------------------------------------------------------------

class TestBuildAuthorizeUrl:
    def test_basic(self):
        url = build_authorize_url(
            client_id="cid", redirect_uri="http://localhost:8766/callback",
            scope="read write", state="abc",
        )
        assert url.startswith(AUTHORIZE_URL)
        assert "client_id=cid" in url
        assert "state=abc" in url
        assert "response_type=code" in url


# ---------------------------------------------------------------------------
# _parse_redirect_uri
# ---------------------------------------------------------------------------

class TestParseRedirectUri:
    def test_valid_local(self):
        full, host, port, path = _parse_redirect_uri("http://127.0.0.1:8766/callback")
        assert host == "127.0.0.1"
        assert port == 8766
        assert path == "/callback"

    def test_invalid_scheme(self):
        with pytest.raises(ValueError, match="http://"):
            _parse_redirect_uri("ftp://example.com/cb")

    def test_local_no_port_raises(self):
        with pytest.raises(ValueError, match="explicit port"):
            _parse_redirect_uri("http://127.0.0.1/callback")

    def test_remote_host_default_port(self):
        full, host, port, path = _parse_redirect_uri("https://myapp.example.com/callback")
        assert port == 443

    def test_remote_host_http_default(self):
        full, host, port, path = _parse_redirect_uri("http://myapp.example.com/callback")
        assert port == 80


# ---------------------------------------------------------------------------
# refresh_access_token
# ---------------------------------------------------------------------------

class TestRefreshAccessToken:
    @patch("code_agents.domain.atlassian_oauth._post_token")
    def test_success(self, mock_post):
        resp = MagicMock()
        resp.is_error = False
        resp.json.return_value = {"access_token": "new_at", "refresh_token": "new_rt"}
        mock_post.return_value = resp
        result = refresh_access_token(
            client_id="cid", client_secret="cs", refresh_token="old_rt",
        )
        assert result["access_token"] == "new_at"

    @patch("code_agents.domain.atlassian_oauth._post_token")
    def test_error_raises(self, mock_post):
        resp = MagicMock()
        resp.is_error = True
        resp.status_code = 400
        resp.text = "bad request"
        mock_post.return_value = resp
        with pytest.raises(RuntimeError, match="Token refresh failed"):
            refresh_access_token(client_id="c", client_secret="s", refresh_token="r")


# ---------------------------------------------------------------------------
# exchange_code_for_tokens
# ---------------------------------------------------------------------------

class TestExchangeCode:
    @patch("code_agents.domain.atlassian_oauth._post_token")
    def test_success(self, mock_post):
        resp = MagicMock()
        resp.is_error = False
        resp.json.return_value = {"access_token": "at", "refresh_token": "rt"}
        mock_post.return_value = resp
        result = exchange_code_for_tokens(
            client_id="c", client_secret="s", code="auth_code",
            redirect_uri="http://localhost:8766/cb",
        )
        assert result["access_token"] == "at"

    @patch("code_agents.domain.atlassian_oauth._post_token")
    def test_error_raises(self, mock_post):
        resp = MagicMock()
        resp.is_error = True
        resp.status_code = 401
        resp.text = "unauthorized"
        mock_post.return_value = resp
        with pytest.raises(RuntimeError, match="Code exchange failed"):
            exchange_code_for_tokens(
                client_id="c", client_secret="s", code="bad",
                redirect_uri="http://localhost/cb",
            )


# ---------------------------------------------------------------------------
# _persist_tokens / persist_oauth_token_response
# ---------------------------------------------------------------------------

class TestPersistTokens:
    def test_persist_with_expires_in(self, monkeypatch, tmp_path):
        cache_file = tmp_path / "tok.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        tokens = {"access_token": "at", "expires_in": 3600, "scope": "read"}
        result = _persist_tokens("cid", tokens, previous_refresh=None)
        assert result["access_token"] == "at"
        assert result["expires_at"] is not None
        assert result["client_id"] == "cid"

    def test_persist_preserves_previous_refresh(self, monkeypatch, tmp_path):
        cache_file = tmp_path / "tok.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        tokens = {"access_token": "at2"}
        result = _persist_tokens("cid", tokens, previous_refresh="old_rt")
        assert result["refresh_token"] == "old_rt"

    def test_persist_oauth_delegates(self, monkeypatch, tmp_path):
        cache_file = tmp_path / "tok.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        tokens = {"access_token": "at3", "refresh_token": "rt3"}
        result = persist_oauth_token_response("cid", tokens, previous_refresh=None)
        assert result["access_token"] == "at3"
        assert result["refresh_token"] == "rt3"

    def test_no_expires_in(self, monkeypatch, tmp_path):
        cache_file = tmp_path / "tok.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        tokens = {"access_token": "at4"}
        result = _persist_tokens("cid", tokens, previous_refresh=None)
        assert result["expires_at"] is None


# ---------------------------------------------------------------------------
# clear_token_cache
# ---------------------------------------------------------------------------

class TestClearTokenCache:
    def test_removes_file(self, monkeypatch, tmp_path):
        cache_file = tmp_path / "tok.json"
        cache_file.write_text("{}")
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        clear_token_cache()
        assert not cache_file.exists()

    def test_no_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(tmp_path / "missing.json"))
        clear_token_cache()  # should not raise


# ---------------------------------------------------------------------------
# interactive_login
# ---------------------------------------------------------------------------

class TestInteractiveLogin:
    @patch("code_agents.domain.atlassian_oauth.exchange_code_for_tokens")
    @patch("code_agents.domain.atlassian_oauth._run_local_callback_server")
    @patch("code_agents.domain.atlassian_oauth.webbrowser.open")
    def test_success(self, mock_browser, mock_server, mock_exchange, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_SCOPES", "read:jira-work")
        mock_server.return_value = ("auth_code_123", None)
        mock_exchange.return_value = {"access_token": "at", "refresh_token": "rt"}
        result = interactive_login(client_id="cid", client_secret="cs")
        assert result["access_token"] == "at"
        mock_browser.assert_called_once()

    @patch("code_agents.domain.atlassian_oauth._run_local_callback_server")
    @patch("code_agents.domain.atlassian_oauth.webbrowser.open")
    def test_callback_error(self, mock_browser, mock_server, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_SCOPES", "read:jira-work")
        mock_server.return_value = (None, "timeout_waiting_for_browser")
        with pytest.raises(RuntimeError, match="callback failed"):
            interactive_login(client_id="cid", client_secret="cs")

    @patch("code_agents.domain.atlassian_oauth._run_local_callback_server")
    @patch("code_agents.domain.atlassian_oauth.webbrowser.open")
    def test_no_code(self, mock_browser, mock_server, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_SCOPES", "read:jira-work")
        mock_server.return_value = (None, None)
        with pytest.raises(RuntimeError, match="No authorization code"):
            interactive_login(client_id="cid", client_secret="cs")

    def test_no_scopes_raises(self, monkeypatch):
        monkeypatch.delenv("ATLASSIAN_OAUTH_SCOPES", raising=False)
        with pytest.raises(ValueError, match="ATLASSIAN_OAUTH_SCOPES"):
            interactive_login(client_id="cid", client_secret="cs")

    @patch("code_agents.domain.atlassian_oauth.exchange_code_for_tokens")
    @patch("code_agents.domain.atlassian_oauth._run_local_callback_server")
    @patch("code_agents.domain.atlassian_oauth.webbrowser.open")
    def test_explicit_redirect_uri(self, mock_browser, mock_server, mock_exchange, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_SCOPES", "read:jira-work")
        mock_server.return_value = ("code", None)
        mock_exchange.return_value = {"access_token": "at"}
        interactive_login(
            client_id="cid", client_secret="cs",
            redirect_uri="http://127.0.0.1:9999/mycb",
        )
        mock_server.assert_called_once()
        call_kw = mock_server.call_args[1]
        assert call_kw["port"] == 9999

    @patch("code_agents.domain.atlassian_oauth.exchange_code_for_tokens")
    @patch("code_agents.domain.atlassian_oauth._run_local_callback_server")
    @patch("code_agents.domain.atlassian_oauth.webbrowser.open")
    def test_env_redirect_uri(self, mock_browser, mock_server, mock_exchange, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_SCOPES", "read:jira-work")
        monkeypatch.setenv("ATLASSIAN_OAUTH_REDIRECT_URI", "http://127.0.0.1:7777/cb")
        mock_server.return_value = ("code", None)
        mock_exchange.return_value = {"access_token": "at"}
        interactive_login(client_id="cid", client_secret="cs")
        call_kw = mock_server.call_args[1]
        assert call_kw["port"] == 7777


# ---------------------------------------------------------------------------
# get_valid_access_token
# ---------------------------------------------------------------------------

class TestGetValidAccessToken:
    def test_missing_credentials(self, monkeypatch):
        monkeypatch.delenv("ATLASSIAN_OAUTH_CLIENT_ID", raising=False)
        monkeypatch.delenv("ATLASSIAN_OAUTH_CLIENT_SECRET", raising=False)
        with pytest.raises(ValueError, match="CLIENT_ID"):
            get_valid_access_token()

    @patch("code_agents.domain.atlassian_oauth._load_cache")
    def test_returns_cached_token(self, mock_cache, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_ID", "cid")
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "cs")
        mock_cache.return_value = {
            "client_id": "cid",
            "access_token": "cached_at",
            "refresh_token": "rt",
            "expires_at": time.time() + 3600,
        }
        token = get_valid_access_token()
        assert token == "cached_at"

    @patch("code_agents.domain.atlassian_oauth.persist_oauth_token_response")
    @patch("code_agents.domain.atlassian_oauth.refresh_access_token")
    @patch("code_agents.domain.atlassian_oauth._load_cache")
    def test_refreshes_expired_token(self, mock_cache, mock_refresh, mock_persist, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_ID", "cid")
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "cs")
        mock_cache.return_value = {
            "client_id": "cid",
            "access_token": "old_at",
            "refresh_token": "rt",
            "expires_at": time.time() - 100,  # expired
        }
        mock_refresh.return_value = {"access_token": "new_at"}
        mock_persist.return_value = {"access_token": "new_at"}
        token = get_valid_access_token()
        assert token == "new_at"
        mock_refresh.assert_called_once()

    @patch("code_agents.domain.atlassian_oauth.persist_oauth_token_response")
    @patch("code_agents.domain.atlassian_oauth.interactive_login")
    @patch("code_agents.domain.atlassian_oauth._load_cache")
    def test_force_login(self, mock_cache, mock_login, mock_persist, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_ID", "cid")
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "cs")
        mock_login.return_value = {"access_token": "fresh"}
        mock_persist.return_value = {"access_token": "fresh"}
        token = get_valid_access_token(force_login=True)
        assert token == "fresh"
        mock_login.assert_called_once()

    @patch("code_agents.domain.atlassian_oauth.persist_oauth_token_response")
    @patch("code_agents.domain.atlassian_oauth.interactive_login")
    @patch("code_agents.domain.atlassian_oauth._load_cache")
    def test_no_cache_triggers_login(self, mock_cache, mock_login, mock_persist, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_ID", "cid")
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "cs")
        mock_cache.return_value = None
        mock_login.return_value = {"access_token": "new"}
        mock_persist.return_value = {"access_token": "new"}
        token = get_valid_access_token()
        assert token == "new"

    @patch("code_agents.domain.atlassian_oauth.persist_oauth_token_response")
    @patch("code_agents.domain.atlassian_oauth.interactive_login")
    @patch("code_agents.domain.atlassian_oauth.refresh_access_token")
    @patch("code_agents.domain.atlassian_oauth._load_cache")
    def test_refresh_failure_triggers_login(self, mock_cache, mock_refresh, mock_login, mock_persist, monkeypatch):
        import httpx
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_ID", "cid")
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "cs")
        mock_cache.return_value = {
            "client_id": "cid",
            "access_token": "old",
            "refresh_token": "rt",
            "expires_at": time.time() - 100,
        }
        mock_refresh.side_effect = httpx.RequestError("fail")
        mock_login.return_value = {"access_token": "login_at"}
        mock_persist.return_value = {"access_token": "login_at"}
        token = get_valid_access_token()
        assert token == "login_at"
