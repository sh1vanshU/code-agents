"""Extra tests for atlassian_oauth.py — interactive_login, get_valid_access_token, callback server."""

from __future__ import annotations

import json
import os
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.parse import urlencode

import pytest

from code_agents.domain.atlassian_oauth import (
    _run_local_callback_server,
    interactive_login,
    get_valid_access_token,
    _post_token,
    _parse_redirect_uri,
)


# ═══════════════════════════════════════════════════════════════════════════
# _run_local_callback_server — lines 167-226
# ═══════════════════════════════════════════════════════════════════════════


class TestRunLocalCallbackServer:
    """Test the local callback HTTP server — lines 167-226."""

    def test_callback_timeout(self):
        """No callback arrives within timeout."""
        code, err = _run_local_callback_server(
            host="127.0.0.1",
            port=18771,
            redirect_path="/callback",
            expected_state="s",
            timeout_seconds=0.5,
        )
        assert code is None
        assert "timeout" in err

    def test_callback_success(self):
        """Server receives valid code + state, returns code."""
        import urllib.request
        import socket

        # Find a free port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        state = "test-state-123"

        def send_callback():
            # Wait for server to start
            for _ in range(20):
                time.sleep(0.1)
                try:
                    url = f"http://127.0.0.1:{port}/callback?code=auth-code-abc&state={state}"
                    urllib.request.urlopen(url, timeout=2)
                    return
                except Exception:
                    continue

        thread = threading.Thread(target=send_callback, daemon=True)
        thread.start()

        code, err = _run_local_callback_server(
            host="127.0.0.1",
            port=port,
            redirect_path="/callback",
            expected_state=state,
            timeout_seconds=5.0,
        )
        assert code == "auth-code-abc"
        assert err is None

    def test_callback_error_from_provider(self):
        """Server receives error query param."""
        import urllib.request
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        def send_callback():
            for _ in range(20):
                time.sleep(0.1)
                try:
                    url = f"http://127.0.0.1:{port}/callback?error=access_denied&error_description=User+denied"
                    urllib.request.urlopen(url, timeout=2)
                    return
                except Exception:
                    continue

        thread = threading.Thread(target=send_callback, daemon=True)
        thread.start()

        code, err = _run_local_callback_server(
            host="127.0.0.1",
            port=port,
            redirect_path="/callback",
            expected_state="state",
            timeout_seconds=5.0,
        )
        assert code is None
        assert "access_denied" in err

    def test_callback_state_mismatch(self):
        """Server receives mismatched state."""
        import urllib.request
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        def send_callback():
            for _ in range(20):
                time.sleep(0.1)
                try:
                    url = f"http://127.0.0.1:{port}/callback?code=abc&state=wrong"
                    urllib.request.urlopen(url, timeout=2)
                    return
                except Exception:
                    continue

        thread = threading.Thread(target=send_callback, daemon=True)
        thread.start()

        code, err = _run_local_callback_server(
            host="127.0.0.1",
            port=port,
            redirect_path="/callback",
            expected_state="expected",
            timeout_seconds=5.0,
        )
        assert code is None
        assert "state_mismatch" in err

    def test_callback_missing_params(self):
        """Server receives request without code or state."""
        import urllib.request
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        def send_callback():
            for _ in range(20):
                time.sleep(0.1)
                try:
                    url = f"http://127.0.0.1:{port}/callback?other=param"
                    urllib.request.urlopen(url, timeout=2)
                    return
                except Exception:
                    continue

        thread = threading.Thread(target=send_callback, daemon=True)
        thread.start()

        code, err = _run_local_callback_server(
            host="127.0.0.1",
            port=port,
            redirect_path="/callback",
            expected_state="state",
            timeout_seconds=5.0,
        )
        assert code is None
        assert "missing_code_or_state" in err


# ═══════════════════════════════════════════════════════════════════════════
# interactive_login — lines 270-331
# ═══════════════════════════════════════════════════════════════════════════


class TestInteractiveLogin:
    """Test interactive_login function."""

    def test_login_success(self):
        tokens = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
        }
        with patch("code_agents.domain.atlassian_oauth.webbrowser.open"), \
             patch("code_agents.domain.atlassian_oauth._run_local_callback_server",
                   return_value=("auth-code", None)), \
             patch("code_agents.domain.atlassian_oauth.exchange_code_for_tokens",
                   return_value=tokens), \
             patch.dict(os.environ, {"ATLASSIAN_OAUTH_SCOPES": "read:jira-work offline_access"}):
            result = interactive_login(
                client_id="cid",
                client_secret="csec",
                redirect_uri="http://127.0.0.1:8766/callback",
            )
        assert result["access_token"] == "at"

    def test_login_no_scopes_raises(self):
        with patch.dict(os.environ, {"ATLASSIAN_OAUTH_SCOPES": ""}):
            with pytest.raises(ValueError, match="ATLASSIAN_OAUTH_SCOPES"):
                interactive_login(
                    client_id="cid",
                    client_secret="csec",
                )

    def test_login_callback_error_raises(self):
        with patch("code_agents.domain.atlassian_oauth.webbrowser.open"), \
             patch("code_agents.domain.atlassian_oauth._run_local_callback_server",
                   return_value=(None, "access_denied")), \
             patch.dict(os.environ, {"ATLASSIAN_OAUTH_SCOPES": "read:jira-work"}):
            with pytest.raises(RuntimeError, match="OAuth callback failed"):
                interactive_login(
                    client_id="cid",
                    client_secret="csec",
                    redirect_uri="http://127.0.0.1:8766/callback",
                )

    def test_login_no_code_raises(self):
        with patch("code_agents.domain.atlassian_oauth.webbrowser.open"), \
             patch("code_agents.domain.atlassian_oauth._run_local_callback_server",
                   return_value=(None, None)), \
             patch.dict(os.environ, {"ATLASSIAN_OAUTH_SCOPES": "read:jira-work"}):
            with pytest.raises(RuntimeError, match="No authorization code"):
                interactive_login(
                    client_id="cid",
                    client_secret="csec",
                    redirect_uri="http://127.0.0.1:8766/callback",
                )

    def test_login_env_redirect_uri(self):
        """Uses ATLASSIAN_OAUTH_REDIRECT_URI from env."""
        tokens = {"access_token": "at", "expires_in": 3600}
        with patch("code_agents.domain.atlassian_oauth.webbrowser.open"), \
             patch("code_agents.domain.atlassian_oauth._run_local_callback_server",
                   return_value=("code", None)), \
             patch("code_agents.domain.atlassian_oauth.exchange_code_for_tokens",
                   return_value=tokens), \
             patch.dict(os.environ, {
                 "ATLASSIAN_OAUTH_REDIRECT_URI": "http://127.0.0.1:9999/cb",
                 "ATLASSIAN_OAUTH_SCOPES": "read:jira-work",
             }):
            result = interactive_login(client_id="cid", client_secret="csec")
        assert result["access_token"] == "at"

    def test_login_default_redirect(self):
        """Uses default redirect when no explicit or env URI."""
        tokens = {"access_token": "at", "expires_in": 3600}
        with patch("code_agents.domain.atlassian_oauth.webbrowser.open"), \
             patch("code_agents.domain.atlassian_oauth._run_local_callback_server",
                   return_value=("code", None)), \
             patch("code_agents.domain.atlassian_oauth.exchange_code_for_tokens",
                   return_value=tokens), \
             patch.dict(os.environ, {
                 "ATLASSIAN_OAUTH_REDIRECT_URI": "",
                 "ATLASSIAN_OAUTH_SCOPES": "read:jira-work",
             }):
            result = interactive_login(client_id="cid", client_secret="csec")
        assert result["access_token"] == "at"


# ═══════════════════════════════════════════════════════════════════════════
# get_valid_access_token — tested indirectly but missing some branches
# ═══════════════════════════════════════════════════════════════════════════


class TestGetValidAccessToken:
    def test_no_credentials_raises(self):
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "",
        }):
            with pytest.raises(ValueError, match="ATLASSIAN_OAUTH_CLIENT_ID"):
                get_valid_access_token()

    def test_cached_valid_token(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        cache_data = {
            "client_id": "cid",
            "access_token": "cached-token",
            "refresh_token": "rt",
            "expires_at": time.time() + 3600,
        }
        cache_file.write_text(json.dumps(cache_data))
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_ID", "cid")
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "csec")

        result = get_valid_access_token()
        assert result == "cached-token"

    def test_refresh_token_used(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        cache_data = {
            "client_id": "cid",
            "access_token": "expired-token",
            "refresh_token": "rt-123",
            "expires_at": time.time() - 100,  # expired
        }
        cache_file.write_text(json.dumps(cache_data))
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_ID", "cid")
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "csec")

        refreshed = {
            "access_token": "new-token",
            "refresh_token": "new-rt",
            "expires_in": 3600,
        }
        with patch("code_agents.domain.atlassian_oauth.refresh_access_token", return_value=refreshed):
            result = get_valid_access_token()
        assert result == "new-token"

    def test_force_login(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        cache_data = {
            "client_id": "cid",
            "access_token": "cached",
            "expires_at": time.time() + 3600,
        }
        cache_file.write_text(json.dumps(cache_data))
        monkeypatch.setenv("ATLASSIAN_OAUTH_TOKEN_CACHE", str(cache_file))
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_ID", "cid")
        monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "csec")

        tokens = {"access_token": "fresh", "expires_in": 3600}
        with patch("code_agents.domain.atlassian_oauth.interactive_login", return_value=tokens):
            result = get_valid_access_token(force_login=True)
        assert result == "fresh"


# ═══════════════════════════════════════════════════════════════════════════
# _post_token — TLS error handling
# ═══════════════════════════════════════════════════════════════════════════


class TestPostToken:
    def test_connect_error_cert_verify(self):
        import httpx
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.ConnectError("CERTIFICATE_VERIFY_FAILED")
            MockClient.return_value = mock_client
            with pytest.raises(RuntimeError, match="HTTPS certificate verification failed"):
                _post_token({"grant_type": "test"})

    def test_connect_error_other(self):
        import httpx
        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            MockClient.return_value = mock_client
            with pytest.raises(RuntimeError, match="Connection to auth.atlassian.com failed"):
                _post_token({"grant_type": "test"})
