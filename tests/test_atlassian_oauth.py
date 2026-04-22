"""Tests for atlassian_oauth.py — Atlassian Cloud OAuth 2.0 (3LO)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.domain.atlassian_oauth import (
    _httpx_verify,
    _cache_path,
    _load_cache,
    _save_cache,
    _token_expired,
    _persist_tokens,
    _parse_redirect_uri,
    build_authorize_url,
    refresh_access_token,
    exchange_code_for_tokens,
    clear_token_cache,
    persist_oauth_token_response,
    AUTH_BASE,
    AUTHORIZE_URL,
    TOKEN_URL,
)


# ── _httpx_verify ────────────────────────────────────────────────────


class TestHttpxVerify:
    def test_default_uses_certifi(self, monkeypatch):
        monkeypatch.delenv("ATLASSIAN_OAUTH_HTTPS_VERIFY", raising=False)
        monkeypatch.delenv("CODE_AGENTS_HTTPS_VERIFY", raising=False)
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
        result = _httpx_verify()
        # Should return certifi path (a string ending in .pem)
        assert isinstance(result, str)
        assert result.endswith(".pem")

    def test_verify_disabled(self, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_HTTPS_VERIFY", "0")
        assert _httpx_verify() is False

    def test_verify_disabled_false(self, monkeypatch):
        monkeypatch.setenv("CODE_AGENTS_HTTPS_VERIFY", "false")
        monkeypatch.delenv("ATLASSIAN_OAUTH_HTTPS_VERIFY", raising=False)
        assert _httpx_verify() is False

    def test_verify_custom_cert(self, tmp_path, monkeypatch):
        cert = tmp_path / "custom.pem"
        cert.write_text("cert content")
        monkeypatch.setenv("ATLASSIAN_OAUTH_HTTPS_VERIFY", str(cert))
        assert _httpx_verify() == str(cert)

    def test_ssl_cert_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ATLASSIAN_OAUTH_HTTPS_VERIFY", raising=False)
        monkeypatch.delenv("CODE_AGENTS_HTTPS_VERIFY", raising=False)
        cert = tmp_path / "ca.pem"
        cert.write_text("ca cert")
        monkeypatch.setenv("SSL_CERT_FILE", str(cert))
        assert _httpx_verify() == str(cert)

    def test_requests_ca_bundle(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ATLASSIAN_OAUTH_HTTPS_VERIFY", raising=False)
        monkeypatch.delenv("CODE_AGENTS_HTTPS_VERIFY", raising=False)
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        cert = tmp_path / "bundle.pem"
        cert.write_text("bundle")
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(cert))
        assert _httpx_verify() == str(cert)


# ── Token cache ──────────────────────────────────────────────────────


class TestTokenCache:
    def test_cache_path_default(self, monkeypatch):
        monkeypatch.delenv("ATLASSIAN_OAUTH_TOKEN_CACHE", raising=False)
        p = _cache_path()
        assert p == Path.home() / ".code-agents-atlassian-oauth.json"

    def test_cache_path_custom(self, tmp_path, monkeypatch):
        custom = tmp_path / "my-cache.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(custom))
        assert _cache_path() == custom

    def test_save_and_load_cache(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        data = {"access_token": "at123", "client_id": "cid"}
        _save_cache(data)
        loaded = _load_cache()
        assert loaded == data

    def test_load_cache_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(tmp_path / "missing.json"))
        assert _load_cache() is None

    def test_load_cache_corrupt(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "bad.json"
        cache_file.write_text("not json {{{")
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        assert _load_cache() is None

    def test_clear_token_cache(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("{}")
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        clear_token_cache()
        assert not cache_file.exists()

    def test_clear_missing_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(tmp_path / "missing.json"))
        clear_token_cache()  # should not raise


# ── _token_expired ───────────────────────────────────────────────────


class TestTokenExpired:
    def test_none_expires_at(self):
        assert _token_expired(None) is True

    def test_expired(self):
        # Expired 2 minutes ago
        assert _token_expired(time.time() - 120) is True

    def test_not_expired(self):
        # Expires in 10 minutes
        assert _token_expired(time.time() + 600) is False

    def test_within_skew(self):
        # Expires in 30 seconds, skew is 60
        assert _token_expired(time.time() + 30, skew_seconds=60) is True


# ── _persist_tokens ──────────────────────────────────────────────────


class TestPersistTokens:
    def test_persist_with_expires(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        tokens = {
            "access_token": "at-new",
            "refresh_token": "rt-new",
            "expires_in": 3600,
            "scope": "read write",
        }
        result = _persist_tokens("my-client-id", tokens, previous_refresh=None)
        assert result["access_token"] == "at-new"
        assert result["refresh_token"] == "rt-new"
        assert result["client_id"] == "my-client-id"
        assert result["expires_at"] is not None
        assert result["scope"] == "read write"

    def test_persist_preserves_previous_refresh(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        tokens = {"access_token": "at-new"}
        result = _persist_tokens("cid", tokens, previous_refresh="old-rt")
        assert result["refresh_token"] == "old-rt"

    def test_persist_no_expires(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        tokens = {"access_token": "at"}
        result = _persist_tokens("cid", tokens, previous_refresh=None)
        assert result["expires_at"] is None


# ── persist_oauth_token_response (public wrapper) ────────────────────


class TestPersistOauthTokenResponse:
    def test_calls_persist(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        tokens = {"access_token": "at", "expires_in": 1800}
        result = persist_oauth_token_response("cid", tokens, previous_refresh="rt")
        assert result["access_token"] == "at"
        assert result["refresh_token"] == "rt"


# ── _parse_redirect_uri ─────────────────────────────────────────────


class TestParseRedirectUri:
    def test_valid_localhost(self):
        full, host, port, path = _parse_redirect_uri("http://127.0.0.1:8766/callback")
        assert full == "http://127.0.0.1:8766/callback"
        assert host == "127.0.0.1"
        assert port == 8766
        assert path == "/callback"

    def test_no_port_localhost_raises(self):
        with pytest.raises(ValueError, match="explicit port"):
            _parse_redirect_uri("http://127.0.0.1/callback")

    def test_invalid_scheme(self):
        with pytest.raises(ValueError, match="http:// or https://"):
            _parse_redirect_uri("ftp://example.com/callback")

    def test_external_host_default_port(self):
        full, host, port, path = _parse_redirect_uri("https://myapp.example.com/auth/callback")
        assert host == "myapp.example.com"
        assert port == 443
        assert path == "/auth/callback"

    def test_no_path(self):
        full, host, port, path = _parse_redirect_uri("http://127.0.0.1:9000")
        assert path == "/"


# ── build_authorize_url ──────────────────────────────────────────────


class TestBuildAuthorizeUrl:
    def test_url_structure(self):
        url = build_authorize_url(
            client_id="my-client",
            redirect_uri="http://127.0.0.1:8766/callback",
            scope="read:jira-work write:jira-work offline_access",
            state="random-state-123",
        )
        assert url.startswith(AUTHORIZE_URL)
        assert "client_id=my-client" in url
        assert "response_type=code" in url
        assert "state=random-state-123" in url
        assert "prompt=consent" in url


# ── refresh_access_token ─────────────────────────────────────────────


class TestRefreshAccessToken:
    @patch("code_agents.domain.atlassian_oauth._post_token")
    def test_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.is_error = False
        mock_resp.json.return_value = {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_resp
        result = refresh_access_token(
            client_id="cid",
            client_secret="csec",
            refresh_token="old-rt",
        )
        assert result["access_token"] == "new-at"

    @patch("code_agents.domain.atlassian_oauth._post_token")
    def test_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.is_error = True
        mock_resp.status_code = 401
        mock_resp.text = "invalid_grant"
        mock_post.return_value = mock_resp
        with pytest.raises(RuntimeError, match="Token refresh failed"):
            refresh_access_token(
                client_id="cid",
                client_secret="csec",
                refresh_token="bad-rt",
            )


# ── exchange_code_for_tokens ─────────────────────────────────────────


class TestExchangeCodeForTokens:
    @patch("code_agents.domain.atlassian_oauth._post_token")
    def test_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.is_error = False
        mock_resp.json.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_resp
        result = exchange_code_for_tokens(
            client_id="cid",
            client_secret="csec",
            code="auth-code",
            redirect_uri="http://127.0.0.1:8766/callback",
        )
        assert result["access_token"] == "at"

    @patch("code_agents.domain.atlassian_oauth._post_token")
    def test_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.is_error = True
        mock_resp.status_code = 400
        mock_resp.text = "invalid_code"
        mock_post.return_value = mock_resp
        with pytest.raises(RuntimeError, match="Code exchange failed"):
            exchange_code_for_tokens(
                client_id="cid",
                client_secret="csec",
                code="bad-code",
                redirect_uri="http://127.0.0.1:8766/callback",
            )


# ── Constants ────────────────────────────────────────────────────────


class TestConstants:
    def test_auth_base(self):
        assert AUTH_BASE == "https://auth.atlassian.com"

    def test_authorize_url(self):
        assert AUTHORIZE_URL == "https://auth.atlassian.com/authorize"

    def test_token_url(self):
        assert TOKEN_URL == "https://auth.atlassian.com/oauth/token"
