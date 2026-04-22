"""Tests for argocd_client.py — ArgoCD REST API client."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.cicd.argocd_client import (
    ArgoCDClient,
    ArgoCDError,
    resolve_app_name,
)


# ── resolve_app_name ─────────────────────────────────────────────────


class TestResolveAppName:
    def test_pattern_resolution(self, monkeypatch):
        monkeypatch.delenv("ARGOCD_APP_PATTERN", raising=False)
        monkeypatch.delenv("ARGOCD_APP_NAME", raising=False)
        result = resolve_app_name(
            env_name="dev-stable",
            app_name="pg-acquiring-biz",
            pattern="{env}-project-bombay-{app}",
        )
        assert result == "dev-stable-project-bombay-pg-acquiring-biz"

    def test_env_pattern(self, monkeypatch):
        monkeypatch.setenv("ARGOCD_APP_PATTERN", "{env}-{app}")
        monkeypatch.delenv("ARGOCD_APP_NAME", raising=False)
        result = resolve_app_name(env_name="prod", app_name="my-svc")
        assert result == "prod-my-svc"

    def test_static_fallback(self, monkeypatch):
        monkeypatch.delenv("ARGOCD_APP_PATTERN", raising=False)
        monkeypatch.setenv("ARGOCD_APP_NAME", "static-app")
        result = resolve_app_name()
        assert result == "static-app"

    def test_build_from_parts(self, monkeypatch):
        monkeypatch.delenv("ARGOCD_APP_PATTERN", raising=False)
        monkeypatch.delenv("ARGOCD_APP_NAME", raising=False)
        result = resolve_app_name(env_name="staging", app_name="my-svc")
        assert result == "staging-project-bombay-my-svc"

    def test_empty_returns_empty(self, monkeypatch):
        monkeypatch.delenv("ARGOCD_APP_PATTERN", raising=False)
        monkeypatch.delenv("ARGOCD_APP_NAME", raising=False)
        result = resolve_app_name()
        assert result == ""

    def test_app_name_only(self, monkeypatch):
        monkeypatch.delenv("ARGOCD_APP_PATTERN", raising=False)
        monkeypatch.delenv("ARGOCD_APP_NAME", raising=False)
        result = resolve_app_name(app_name="my-app")
        assert result == "my-app"


# ── ArgoCDError ──────────────────────────────────────────────────────


class TestArgoCDError:
    def test_error_with_status(self):
        err = ArgoCDError("fail", status_code=404, response_text="not found")
        assert err.status_code == 404
        assert err.response_text == "not found"
        assert str(err) == "fail"

    def test_error_defaults(self):
        err = ArgoCDError("message")
        assert err.status_code is None
        assert err.response_text is None


# ── ArgoCDClient init ────────────────────────────────────────────────


class TestArgoCDClientInit:
    def test_init(self):
        c = ArgoCDClient(
            base_url="https://argocd.example.com/",
            auth_token="test-token",
            verify_ssl=False,
        )
        assert c.base_url == "https://argocd.example.com"
        assert c.auth_token == "test-token"
        assert c.verify_ssl is False

    def test_defaults(self):
        c = ArgoCDClient(base_url="https://argocd.example.com", auth_token="t")
        assert c.verify_ssl is True
        assert c.timeout == 30.0
        assert c.poll_interval == 5.0
        assert c.poll_timeout == 300.0

    def test_init_with_username_password(self):
        c = ArgoCDClient(
            base_url="https://argocd.example.com",
            username="admin",
            password="secret",
        )
        assert c.auth_token == ""
        assert c._username == "admin"
        assert c._password == "secret"
        assert c._logged_in is False


# ── Async method tests ───────────────────────────────────────────────


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


class TestGetAppStatus:
    def test_success(self):
        client = ArgoCDClient(base_url="https://argocd.test", auth_token="tok")
        mock_resp = _mock_response(200, json_data={
            "status": {
                "sync": {"status": "Synced", "revision": "abc123"},
                "health": {"status": "Healthy"},
                "summary": {"images": ["registry/app:v1.0"]},
                "conditions": [],
            },
            "spec": {"source": {"repoURL": "git@github.com:test/repo.git"}},
        })

        async def run():
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(client, "_client", return_value=mock_client):
                return await client.get_app_status("my-app")

        result = asyncio.run(run())
        assert result["app_name"] == "my-app"
        assert result["sync_status"] == "Synced"
        assert result["health_status"] == "Healthy"
        assert result["revision"] == "abc123"
        assert "registry/app:v1.0" in result["images"]

    def test_failure(self):
        client = ArgoCDClient(base_url="https://argocd.test", auth_token="tok")
        mock_resp = _mock_response(404, text="not found")

        async def run():
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(client, "_client", return_value=mock_client):
                return await client.get_app_status("missing-app")

        with pytest.raises(ArgoCDError) as exc_info:
            asyncio.run(run())
        assert exc_info.value.status_code == 404


class TestListPods:
    def test_success(self):
        client = ArgoCDClient(base_url="https://argocd.test", auth_token="tok")
        mock_resp = _mock_response(200, json_data={
            "nodes": [
                {
                    "kind": "Pod",
                    "name": "my-app-abc123",
                    "namespace": "default",
                    "health": {"status": "Healthy", "message": ""},
                    "images": ["registry/app:v1.0"],
                },
                {
                    "kind": "ReplicaSet",
                    "name": "my-app-rs-abc",
                    "namespace": "default",
                },
            ],
        })

        async def run():
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(client, "_client", return_value=mock_client):
                return await client.list_pods("my-app")

        pods = asyncio.run(run())
        assert len(pods) == 1
        assert pods[0]["name"] == "my-app-abc123"
        assert pods[0]["ready"] is True


class TestGetPodLogs:
    def test_with_errors(self):
        client = ArgoCDClient(base_url="https://argocd.test", auth_token="tok")
        log_text = "INFO Starting...\nERROR NullPointerException\nINFO Done\n"
        mock_resp = _mock_response(200, text=log_text)
        mock_resp.text = log_text

        async def run():
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(client, "_client", return_value=mock_client):
                return await client.get_pod_logs("my-app", "pod-1", "default")

        result = asyncio.run(run())
        assert result["has_errors"] is True
        assert len(result["error_lines"]) == 1
        assert "NullPointerException" in result["error_lines"][0]
        assert result["total_lines"] == 3


class TestSyncApp:
    def test_sync_success(self):
        client = ArgoCDClient(base_url="https://argocd.test", auth_token="tok")
        mock_resp = _mock_response(200)

        async def run():
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(client, "_client", return_value=mock_client):
                return await client.sync_app("my-app", revision="abc123")

        result = asyncio.run(run())
        assert result["status"] == "sync_triggered"
        assert result["revision"] == "abc123"

    def test_sync_failure(self):
        client = ArgoCDClient(base_url="https://argocd.test", auth_token="tok")
        mock_resp = _mock_response(403, text="forbidden")

        async def run():
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(client, "_client", return_value=mock_client):
                return await client.sync_app("my-app")

        with pytest.raises(ArgoCDError):
            asyncio.run(run())


class TestRollback:
    def test_rollback_success(self):
        client = ArgoCDClient(base_url="https://argocd.test", auth_token="tok")
        mock_resp = _mock_response(200)

        async def run():
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(client, "_client", return_value=mock_client):
                return await client.rollback("my-app", 42)

        result = asyncio.run(run())
        assert result["status"] == "rollback_triggered"
        assert result["target_revision_id"] == 42


class TestGetHistory:
    def test_history(self):
        client = ArgoCDClient(base_url="https://argocd.test", auth_token="tok")
        mock_resp = _mock_response(200, json_data={
            "status": {
                "history": [
                    {"id": 1, "revision": "abc", "deployedAt": "2026-01-01", "source": {}},
                    {"id": 2, "revision": "def", "deployedAt": "2026-01-02", "source": {}},
                ],
            },
        })

        async def run():
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(client, "_client", return_value=mock_client):
                return await client.get_history("my-app")

        history = asyncio.run(run())
        assert len(history) == 2
        assert history[0]["revision"] == "abc"


class TestWaitForSync:
    def test_already_synced(self):
        client = ArgoCDClient(base_url="https://argocd.test", auth_token="tok",
                              poll_interval=0.01, poll_timeout=1.0)

        async def run():
            with patch.object(client, "get_app_status", new_callable=AsyncMock) as mock_status:
                mock_status.return_value = {
                    "sync_status": "Synced",
                    "health_status": "Healthy",
                }
                return await client.wait_for_sync("my-app")

        result = asyncio.run(run())
        assert result["sync_status"] == "Synced"

    def test_timeout(self):
        client = ArgoCDClient(base_url="https://argocd.test", auth_token="tok",
                              poll_interval=0.01, poll_timeout=0.05)

        async def run():
            with patch.object(client, "get_app_status", new_callable=AsyncMock) as mock_status:
                mock_status.return_value = {
                    "sync_status": "OutOfSync",
                    "health_status": "Progressing",
                }
                return await client.wait_for_sync("my-app")

        with pytest.raises(ArgoCDError, match="did not reach"):
            asyncio.run(run())


# ── Login / Username+Password Auth ──────────────────────────────────


class TestLoginAuth:
    def test_login_success(self):
        client = ArgoCDClient(
            base_url="https://argocd.test",
            username="admin",
            password="secret",
        )
        login_resp = _mock_response(200, json_data={"token": "session-jwt-123"})

        async def run():
            mock_http = AsyncMock()
            mock_http.post.return_value = login_resp
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            with patch("code_agents.cicd.argocd_client.httpx.AsyncClient", return_value=mock_http):
                await client._login()

        asyncio.run(run())
        assert client.auth_token == "session-jwt-123"
        assert client._logged_in is True

    def test_login_failure_401(self):
        client = ArgoCDClient(
            base_url="https://argocd.test",
            username="admin",
            password="wrong",
        )
        login_resp = _mock_response(401, text="Unauthorized")

        async def run():
            mock_http = AsyncMock()
            mock_http.post.return_value = login_resp
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            with patch("code_agents.cicd.argocd_client.httpx.AsyncClient", return_value=mock_http):
                await client._login()

        with pytest.raises(ArgoCDError, match="login failed"):
            asyncio.run(run())

    def test_login_missing_token_in_response(self):
        client = ArgoCDClient(
            base_url="https://argocd.test",
            username="admin",
            password="secret",
        )
        login_resp = _mock_response(200, json_data={})

        async def run():
            mock_http = AsyncMock()
            mock_http.post.return_value = login_resp
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            with patch("code_agents.cicd.argocd_client.httpx.AsyncClient", return_value=mock_http):
                await client._login()

        with pytest.raises(ArgoCDError, match="missing token"):
            asyncio.run(run())

    def test_login_skipped_when_token_exists(self):
        client = ArgoCDClient(
            base_url="https://argocd.test",
            auth_token="existing-token",
            username="admin",
            password="secret",
        )

        async def run():
            await client._ensure_auth()

        asyncio.run(run())
        assert client.auth_token == "existing-token"
        assert client._logged_in is False  # login was never called

    def test_ensure_auth_idempotent(self):
        client = ArgoCDClient(
            base_url="https://argocd.test",
            username="admin",
            password="secret",
        )
        login_resp = _mock_response(200, json_data={"token": "jwt-tok"})
        call_count = 0

        async def run():
            nonlocal call_count
            mock_http = AsyncMock()

            async def mock_post(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return login_resp

            mock_http.post = mock_post
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            with patch("code_agents.cicd.argocd_client.httpx.AsyncClient", return_value=mock_http):
                await client._ensure_auth()
                await client._ensure_auth()  # second call should be a no-op

        asyncio.run(run())
        assert call_count == 1

    def test_no_credentials_raises(self):
        client = ArgoCDClient(base_url="https://argocd.test")

        async def run():
            await client._ensure_auth()

        with pytest.raises(ArgoCDError, match="No auth_token"):
            asyncio.run(run())

    def test_get_app_status_with_login(self):
        """End-to-end: login + API call using username/password."""
        client = ArgoCDClient(
            base_url="https://argocd.test",
            username="admin",
            password="secret",
        )
        login_resp = _mock_response(200, json_data={"token": "jwt-tok"})
        app_resp = _mock_response(200, json_data={
            "status": {
                "sync": {"status": "Synced", "revision": "abc"},
                "health": {"status": "Healthy"},
                "summary": {},
                "conditions": [],
            },
            "spec": {"source": {}},
        })

        async def run():
            # Mock login
            mock_login_http = AsyncMock()
            mock_login_http.post.return_value = login_resp
            mock_login_http.__aenter__ = AsyncMock(return_value=mock_login_http)
            mock_login_http.__aexit__ = AsyncMock(return_value=False)

            # Mock API call
            mock_api_http = AsyncMock()
            mock_api_http.request.return_value = app_resp
            mock_api_http.__aenter__ = AsyncMock(return_value=mock_api_http)
            mock_api_http.__aexit__ = AsyncMock(return_value=False)

            with patch("code_agents.cicd.argocd_client.httpx.AsyncClient", return_value=mock_login_http):
                await client._ensure_auth()
            with patch.object(client, "_client", return_value=mock_api_http):
                return await client.get_app_status("my-app")

        result = asyncio.run(run())
        assert result["sync_status"] == "Synced"
        assert client.auth_token == "jwt-tok"

    def test_401_retry_reauth(self):
        """On 401, client clears token, re-logs in, and retries the request."""
        client = ArgoCDClient(
            base_url="https://argocd.test",
            auth_token="expired-token",
            username="admin",
            password="secret",
        )
        expired_resp = _mock_response(401, text="Unauthorized")
        ok_resp = _mock_response(200, json_data={
            "status": {
                "sync": {"status": "Synced", "revision": "abc"},
                "health": {"status": "Healthy"},
                "summary": {},
                "conditions": [],
            },
            "spec": {"source": {}},
        })
        login_resp = _mock_response(200, json_data={"token": "fresh-token"})

        async def run():
            call_count = 0

            # First call returns 401, second returns 200 (after re-auth)
            mock_api = AsyncMock()

            def make_request(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return expired_resp if call_count == 1 else ok_resp

            mock_api.request.side_effect = make_request
            mock_api.__aenter__ = AsyncMock(return_value=mock_api)
            mock_api.__aexit__ = AsyncMock(return_value=False)

            mock_login = AsyncMock()
            mock_login.post.return_value = login_resp
            mock_login.__aenter__ = AsyncMock(return_value=mock_login)
            mock_login.__aexit__ = AsyncMock(return_value=False)

            with patch.object(client, "_client", return_value=mock_api), \
                 patch("code_agents.cicd.argocd_client.httpx.AsyncClient", return_value=mock_login):
                return await client.get_app_status("my-app")

        result = asyncio.run(run())
        assert result["sync_status"] == "Synced"
        assert client.auth_token == "fresh-token"
        assert client._logged_in is True


# ---------------------------------------------------------------------------
# _login skip when already logged in (line 92)
# ---------------------------------------------------------------------------


class TestLoginSkip:
    """Test _login early return when already logged in."""

    def test_login_skip_when_already_logged_in(self):
        """_login returns immediately when _logged_in is True (line 92)."""
        from code_agents.cicd.argocd_client import ArgoCDClient
        import asyncio

        client = ArgoCDClient(
            base_url="http://argo:443",
            username="admin",
            password="pass",
        )
        client._logged_in = True
        client.auth_token = "existing-token"

        # If _login tried to make HTTP calls, it would fail
        asyncio.run(client._login())
        assert client.auth_token == "existing-token"

    def test_login_skip_when_auth_token_set(self):
        """_login returns immediately when auth_token is already set (line 91)."""
        from code_agents.cicd.argocd_client import ArgoCDClient
        import asyncio

        client = ArgoCDClient(
            base_url="http://argo:443",
            auth_token="pre-set-token",
        )
        asyncio.run(client._login())
        assert client.auth_token == "pre-set-token"


# ---------------------------------------------------------------------------
# list_pods (line 189)
# ---------------------------------------------------------------------------


class TestListPods:
    """Test list_pods error path."""

    def test_list_pods_error(self):
        """list_pods raises ArgoCDError on non-200 (line 189)."""
        from code_agents.cicd.argocd_client import ArgoCDClient, ArgoCDError
        from unittest.mock import AsyncMock
        import asyncio

        client = ArgoCDClient(
            base_url="http://argo:443",
            auth_token="token",
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not found"

        async def run():
            with patch.object(client, "_request", new_callable=AsyncMock, return_value=mock_resp):
                return await client.list_pods("my-app")

        with pytest.raises(ArgoCDError, match="Failed to get resource tree"):
            asyncio.run(run())


# ---------------------------------------------------------------------------
# run_smoke_test (lines 315-336)
# ---------------------------------------------------------------------------


class TestRunSmokeTest:
    """Test run_smoke_test success and failure paths."""

    def test_smoke_test_success(self):
        """Successful smoke test returns healthy=True (lines 316-327)."""
        from code_agents.cicd.argocd_client import ArgoCDClient
        from unittest.mock import AsyncMock
        import asyncio

        client = ArgoCDClient(
            base_url="http://argo:443",
            auth_token="token",
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def run():
            with patch("httpx.AsyncClient", return_value=mock_client):
                return await client.run_smoke_test("http://app.example.com/health")

        result = asyncio.run(run())
        assert result["healthy"] is True
        assert result["status_code"] == 200
        assert "latency_ms" in result

    def test_smoke_test_failure(self):
        """Failed smoke test returns healthy=False (lines 328-336)."""
        from code_agents.cicd.argocd_client import ArgoCDClient
        from unittest.mock import AsyncMock
        import asyncio

        client = ArgoCDClient(
            base_url="http://argo:443",
            auth_token="token",
        )

        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def run():
            with patch("httpx.AsyncClient", return_value=mock_client):
                return await client.run_smoke_test("http://app.example.com/health")

        result = asyncio.run(run())
        assert result["healthy"] is False
        assert result["status_code"] == 0

    def test_smoke_test_wrong_status(self):
        """Smoke test with non-expected status returns healthy=False (line 320)."""
        from code_agents.cicd.argocd_client import ArgoCDClient
        from unittest.mock import AsyncMock
        import asyncio

        client = ArgoCDClient(
            base_url="http://argo:443",
            auth_token="token",
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 503

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def run():
            with patch("httpx.AsyncClient", return_value=mock_client):
                return await client.run_smoke_test("http://app.example.com/health")

        result = asyncio.run(run())
        assert result["healthy"] is False
        assert result["status_code"] == 503


# ---------------------------------------------------------------------------
# get_history error (line 342)
# ---------------------------------------------------------------------------


class TestGetHistory:
    def test_get_history_error(self):
        """get_history raises on non-200 (line 342)."""
        from code_agents.cicd.argocd_client import ArgoCDClient, ArgoCDError
        from unittest.mock import AsyncMock
        import asyncio

        client = ArgoCDClient(base_url="http://argo:443", auth_token="token")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal error"

        async def run():
            with patch.object(client, "_request", new_callable=AsyncMock, return_value=mock_resp):
                return await client.get_history("my-app")

        with pytest.raises(ArgoCDError):
            asyncio.run(run())
