"""
Atlassian Cloud OAuth 2.0 (3LO): browser login + redirect callback.

Docs: https://developer.atlassian.com/cloud/oauth/getting-started/implementing-oauth-3lo/
Refresh: https://developer.atlassian.com/cloud/oauth/getting-started/refresh-tokens/
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import certifi
import httpx
import logging

logger = logging.getLogger("code_agents.domain.atlassian_oauth")

AUTH_BASE = "https://auth.atlassian.com"
AUTHORIZE_URL = f"{AUTH_BASE}/authorize"
TOKEN_URL = f"{AUTH_BASE}/oauth/token"

DEFAULT_REDIRECT_PATH = "/callback"
DEFAULT_CALLBACK_PORT = 8766


def _httpx_verify() -> bool | str:
    """TLS verification for outbound calls to ``auth.atlassian.com``.

    Default uses **certifi**’s CA bundle (``httpx`` depends on certifi) so Homebrew / older
    macOS Python builds that lack a working system store often still verify public CAs.

    Corporate SSL inspection needs ``SSL_CERT_FILE`` (or ``REQUESTS_CA_BUNDLE``) with your
    root CA, or ``CODE_AGENTS_HTTPS_VERIFY=0`` / ``ATLASSIAN_OAUTH_HTTPS_VERIFY=0`` for
    local dev only (insecure).
    """
    for key in ("ATLASSIAN_OAUTH_HTTPS_VERIFY", "CODE_AGENTS_HTTPS_VERIFY"):
        raw = os.getenv(key, "").strip()
        if not raw:
            continue
        low = raw.lower()
        if low in ("0", "false", "no", "off"):
            return False
        if os.path.isfile(raw):
            return raw
    for key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        path = os.getenv(key, "").strip()
        if path and os.path.isfile(path):
            return path
    return certifi.where()


def _post_token(body: dict[str, Any]) -> httpx.Response:
    try:
        with httpx.Client(timeout=60.0, verify=_httpx_verify()) as client:
            return client.post(
                TOKEN_URL,
                json=body,
                headers={"Content-Type": "application/json"},
            )
    except httpx.ConnectError as e:
        msg = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in msg or "certificate verify failed" in msg.lower():
            raise RuntimeError(
                "HTTPS certificate verification failed connecting to auth.atlassian.com "
                "(certifi or SSL_CERT_FILE could not validate the server chain). "
                "If TLS inspection / a corporate proxy re-signs HTTPS, set SSL_CERT_FILE "
                "(or REQUESTS_CA_BUNDLE) to a PEM bundle that includes your inspection root. "
                "Otherwise for local troubleshooting only, set CODE_AGENTS_HTTPS_VERIFY=0 "
                "in .env and restart the server (insecure)."
            ) from e
        raise RuntimeError(f"Connection to auth.atlassian.com failed: {msg}") from e


def _cache_path() -> Path:
    p = os.getenv("ATLASSIAN_OAUTH_TOKEN_CACHE")
    if p:
        return Path(p)
    return Path.home() / ".code-agents-atlassian-oauth.json"


def _load_cache() -> dict[str, Any] | None:
    path = _cache_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_cache(data: dict[str, Any]) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _token_expired(expires_at: float | None, skew_seconds: int = 60) -> bool:
    if expires_at is None:
        return True
    return time.time() >= expires_at - skew_seconds


def refresh_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict[str, Any]:
    """POST refresh_token grant; returns token JSON from Atlassian."""
    body = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    r = _post_token(body)
    if r.is_error:
        raise RuntimeError(f"Token refresh failed HTTP {r.status_code}: {r.text}") from None
    return r.json()


def exchange_code_for_tokens(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    body = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    r = _post_token(body)
    if r.is_error:
        raise RuntimeError(f"Code exchange failed HTTP {r.status_code}: {r.text}") from None
    return r.json()


def _run_local_callback_server(
    *,
    host: str,
    port: int,
    redirect_path: str,
    expected_state: str,
    timeout_seconds: float = 300.0,
) -> tuple[str | None, str | None]:
    """
    Start a one-shot HTTP server; returns (authorization_code, error_message).
    Browser is opened by the caller.
    """
    container: dict[str, str | None] = {"code": None, "error": None}
    redirect_path = redirect_path.rstrip("/") or "/"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            want = redirect_path.rstrip("/") or "/"
            if path != want and path + "/" != want:
                self.send_response(404)
                self.end_headers()
                return
            qs = parse_qs(parsed.query)
            if qs.get("error"):
                err = qs["error"][0]
                detail = (qs.get("error_description") or [""])[0]
                container["error"] = f"{err}: {detail}".strip()
                body = b"<html><body><p>Authorization failed. You can close this window.</p></body></html>"
            elif qs.get("code") and qs.get("state"):
                st = qs["state"][0]
                if st != expected_state:
                    container["error"] = "state_mismatch"
                    body = b"<html><body><p>Invalid state. Close this window.</p></body></html>"
                else:
                    container["code"] = qs["code"][0]
                    body = (
                        b"<html><body><p>Success. You can close this window and return to the terminal.</p></body></html>"
                    )
            else:
                container["error"] = "missing_code_or_state"
                body = b"<html><body><p>Missing parameters. Close this window.</p></body></html>"

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer((host, port), Handler)
    server.timeout = 0.5
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
    thread.start()
    deadline = time.time() + timeout_seconds
    try:
        while time.time() < deadline:
            if container["code"] is not None:
                return container["code"], None
            if container["error"] is not None:
                return None, container["error"]
            time.sleep(0.2)
        return None, "timeout_waiting_for_browser"
    finally:
        try:
            server.shutdown()
        except Exception:
            pass
        server.server_close()


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
) -> str:
    q = {
        "client_id": client_id,
        "scope": scope,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    }
    return f"{AUTHORIZE_URL}?{urlencode(q)}"


def _parse_redirect_uri(explicit: str) -> tuple[str, str, int, str]:
    """Return (full_redirect_uri, bind_host, bind_port, path_only).

    ``full_redirect_uri`` must match the Callback URL in the Atlassian Developer Console exactly
    (scheme, host, port, path; no query string).
    """
    u = urlparse(explicit.strip())
    if u.scheme not in ("http", "https"):
        raise ValueError("Redirect URI must start with http:// or https://")
    host = u.hostname or "127.0.0.1"
    port = u.port
    if port is None:
        if host in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                "Local redirect URI must include an explicit port, e.g. "
                "http://127.0.0.1:8766/callback (and register the same URL in the Developer Console)."
            )
        port = 443 if u.scheme == "https" else 80
    path = u.path if u.path else "/"
    full = f"{u.scheme}://{host}:{port}{path}"
    return full, host, port, path


def interactive_login(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str | None = None,
    callback_host: str = "127.0.0.1",
    callback_port: int = DEFAULT_CALLBACK_PORT,
    redirect_path: str = DEFAULT_REDIRECT_PATH,
    scope: str | None = None,
) -> dict[str, Any]:
    """
    Open browser to Atlassian, wait for callback, exchange code for tokens.
    """
    env_redirect = os.getenv("ATLASSIAN_OAUTH_REDIRECT_URI", "").strip()
    if redirect_uri:
        full_redirect, bind_host, bind_port, path_only = _parse_redirect_uri(redirect_uri)
    elif env_redirect:
        full_redirect, bind_host, bind_port, path_only = _parse_redirect_uri(env_redirect)
    else:
        path_only = redirect_path
        bind_host = callback_host
        bind_port = callback_port
        full_redirect = f"http://{bind_host}:{bind_port}{path_only}"

    scopes = scope or os.getenv("ATLASSIAN_OAUTH_SCOPES", "")
    if not scopes.strip():
        raise ValueError(
            "Set ATLASSIAN_OAUTH_SCOPES to space-separated scopes "
            "(and add offline_access for refresh). See examples/README-atlassian-mcp.md"
        )

    state = secrets.token_urlsafe(32)
    url = build_authorize_url(
        client_id=client_id,
        redirect_uri=full_redirect,
        scope=scopes.strip(),
        state=state,
    )

    print("Opening browser for Atlassian login...", flush=True)
    print(f"If it does not open, visit:\n{url}\n", flush=True)

    webbrowser.open(url)

    code, err = _run_local_callback_server(
        host=bind_host,
        port=bind_port,
        redirect_path=path_only,
        expected_state=state,
    )
    if err:
        raise RuntimeError(f"OAuth callback failed: {err}")
    if not code:
        raise RuntimeError("No authorization code received")

    tokens = exchange_code_for_tokens(
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=full_redirect,
    )
    return tokens


def get_valid_access_token(
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    force_login: bool = False,
) -> str:
    """
    Return a usable OAuth access token: cache, refresh, or interactive login.
    """
    client_id = client_id or os.getenv("ATLASSIAN_OAUTH_CLIENT_ID", "").strip()
    client_secret = client_secret or os.getenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ValueError(
            "Set ATLASSIAN_OAUTH_CLIENT_ID and ATLASSIAN_OAUTH_CLIENT_SECRET "
            "(Atlassian Developer Console → your app → Settings)."
        )

    cache = _load_cache() if not force_login else None
    if cache and cache.get("client_id") == client_id:
        expires_at = cache.get("expires_at")
        access = cache.get("access_token")
        refresh = cache.get("refresh_token")
        if access and not _token_expired(expires_at) and not force_login:
            return access
        if refresh and not force_login:
            try:
                new_t = refresh_access_token(
                    client_id=client_id,
                    client_secret=client_secret,
                    refresh_token=refresh,
                )
                merged = persist_oauth_token_response(client_id, new_t, previous_refresh=refresh)
                return merged["access_token"]
            except (httpx.HTTPStatusError, httpx.RequestError):
                pass

    tokens = interactive_login(client_id=client_id, client_secret=client_secret)
    merged = persist_oauth_token_response(client_id, tokens, previous_refresh=None)
    return merged["access_token"]


def persist_oauth_token_response(
    client_id: str,
    tokens: dict[str, Any],
    *,
    previous_refresh: str | None = None,
) -> dict[str, Any]:
    """Persist access (and refresh) tokens from authorize or refresh responses; same cache as the CLI."""
    return _persist_tokens(client_id, tokens, previous_refresh=previous_refresh)


def _persist_tokens(
    client_id: str,
    tokens: dict[str, Any],
    *,
    previous_refresh: str | None,
) -> dict[str, Any]:
    expires_in = tokens.get("expires_in")
    expires_at = None
    if isinstance(expires_in, (int, float)):
        expires_at = time.time() + float(expires_in)
    refresh = tokens.get("refresh_token") or previous_refresh
    row = {
        "client_id": client_id,
        "access_token": tokens["access_token"],
        "refresh_token": refresh,
        "expires_at": expires_at,
        "scope": tokens.get("scope"),
    }
    _save_cache(row)
    return row


def clear_token_cache() -> None:
    path = _cache_path()
    if path.is_file():
        path.unlink()
