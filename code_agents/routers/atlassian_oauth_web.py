"""
Atlassian OAuth 2.0 (3LO) web flow on the same origin as the Code Agents API.

Register callback in Atlassian Developer Console — must match CODE_AGENTS_PUBLIC_BASE_URL + /oauth/atlassian/callback
(not your *.atlassian.net site URL; that is ATLASSIAN_CLOUD_SITE_URL for Jira/Confluence context only).
"""

from __future__ import annotations

import html
import logging
import os
import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from code_agents.domain.atlassian_oauth import (
    build_authorize_url,
    exchange_code_for_tokens,
    persist_oauth_token_response,
)
from code_agents.core.public_urls import atlassian_cloud_site_url

router = APIRouter(prefix="/oauth/atlassian", tags=["atlassian-oauth"])
logger = logging.getLogger(__name__)

# state -> (expiry_epoch, redirect_uri used in /authorize — must match token exchange exactly)
_pending_state: dict[str, tuple[float, str]] = {}
_STATE_TTL_SEC = 600.0

CALLBACK_SUFFIX = "/callback"


def _cleanup_states() -> None:
    now = time.time()
    for s, (exp, _uri) in list(_pending_state.items()):
        if exp < now:
            _pending_state.pop(s, None)


def _public_base(request: Request) -> str:
    for key in ("CODE_AGENTS_PUBLIC_BASE_URL", "ATLASSIAN_OAUTH_PUBLIC_BASE_URL"):
        v = os.getenv(key, "").strip().rstrip("/")
        if v:
            return v
    return str(request.base_url).rstrip("/")


def _open_webui_public_url() -> str | None:
    """Chat UI origin (port 8080 by default), not this API server — used for post-OAuth links."""
    for key in ("OPEN_WEBUI_PUBLIC_URL", "OPEN_WEBUI_URL"):
        v = os.getenv(key, "").strip().rstrip("/")
        if v:
            return v
    return None


def _success_redirect_url() -> str | None:
    """If set, after a successful token save the browser gets HTTP 302 here instead of an HTML page."""
    raw = os.getenv("ATLASSIAN_OAUTH_SUCCESS_REDIRECT", "").strip()
    if not raw:
        return None
    return raw


def _require_oauth_config() -> tuple[str, str, str]:
    cid = os.getenv("ATLASSIAN_OAUTH_CLIENT_ID", "").strip()
    sec = os.getenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "").strip()
    scopes = os.getenv("ATLASSIAN_OAUTH_SCOPES", "").strip()
    if not cid or not sec:
        raise HTTPException(
            status_code=500,
            detail="Set ATLASSIAN_OAUTH_CLIENT_ID and ATLASSIAN_OAUTH_CLIENT_SECRET",
        )
    if not scopes:
        raise HTTPException(
            status_code=500,
            detail="Set ATLASSIAN_OAUTH_SCOPES (include offline_access for refresh)",
        )
    return cid, sec, scopes


@router.get("", response_class=HTMLResponse)
def oauth_home(request: Request) -> str:
    base = _public_base(request)
    cb = f"{base}/oauth/atlassian{CALLBACK_SUFFIX}"
    api_base = f"{base}/v1"
    site = atlassian_cloud_site_url()
    site_block = ""
    if site:
        site_block = (
            f'<p style="color:#666;font-size:0.9rem;">Atlassian Cloud site (Jira/Confluence): '
            f'<a href="{site}">{site}</a> — set <code>ATLASSIAN_CLOUD_SITE_URL</code> if wrong.</p>'
        )
    webui = _open_webui_public_url()
    webui_note = ""
    if webui:
        webui_note = (
            f'<p style="color:#666;font-size:0.9rem;">Open WebUI (chat): '
            f'<a href="{html.escape(webui)}">{html.escape(webui)}</a> — OAuth uses this server only.</p>'
        )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Atlassian sign-in</title></head>
<body style="font-family: system-ui; max-width: 36rem; margin: 3rem auto;">
  <h1>Atlassian (Code Agents)</h1>
  <p>Use this before calling Atlassian MCP tools from scripts. Tokens are saved on disk and shared with
  <code>examples/atlassian_mcp_client.py</code>.</p>
  <p style="color:#444;font-size:0.9rem;"><strong>Tip:</strong> Use <strong>Safari, Chrome, or Firefox</strong>
  for this flow. Cursor’s embedded browser or OAuth from inside the IDE has been reported to crash the IDE when
  combined with Open WebUI; keep chat on Open WebUI and sign-in in an external browser tab.</p>
  <p><a href="/oauth/atlassian/start" style="display:inline-block;padding:0.6rem 1rem;
  background:#0052CC;color:#fff;text-decoration:none;border-radius:4px;">
  Sign in with Atlassian</a></p>
  <p style="color:#666;font-size:0.9rem;"><strong>OAuth callback</strong> (register in Developer Console, must match):<br/>
  <code>{cb}</code></p>
  {site_block}
  {webui_note}
  <p style="color:#666;font-size:0.9rem;">Code Agents API (models): <code>{api_base}</code> (this server).</p>
</body></html>"""


@router.get("/start")
def oauth_start(request: Request) -> RedirectResponse:
    client_id, _client_secret, scopes = _require_oauth_config()
    _cleanup_states()
    base = _public_base(request)
    redirect_uri = f"{base}/oauth/atlassian{CALLBACK_SUFFIX}"

    state = secrets.token_urlsafe(32)
    _pending_state[state] = (time.time() + _STATE_TTL_SEC, redirect_uri)

    url = build_authorize_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scopes,
        state=state,
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback")
def oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> HTMLResponse:
    if error:
        msg = error_description or error
        return HTMLResponse(
            f"<html><body><h1>Authorization failed</h1><p>{msg}</p></body></html>",
            status_code=400,
        )
    if not code or not state:
        raise HTTPException(400, "Missing code or state")

    _cleanup_states()
    entry = _pending_state.pop(state, None)
    if entry is None:
        raise HTTPException(400, "Invalid or expired state — open /oauth/atlassian and try again")
    exp, redirect_uri = entry
    if exp < time.time():
        raise HTTPException(400, "Invalid or expired state — open /oauth/atlassian and try again")

    client_id, client_secret, _scopes = _require_oauth_config()

    try:
        tokens = exchange_code_for_tokens(
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            redirect_uri=redirect_uri,
        )
    except RuntimeError as e:
        msg = str(e)
        logger.error(
            "Atlassian OAuth token exchange failed (redirect_uri=%s): %s",
            redirect_uri,
            msg,
        )
        detail = html.escape(msg)
        hint = ""
        if "Code exchange failed HTTP 4" in msg or "invalid_grant" in msg.lower():
            hint = (
                "<p><strong>Common causes:</strong> OAuth <code>code</code> was already used (refresh the page "
                "and start again from <code>/oauth/atlassian</code>), "
                "<code>redirect_uri</code> does not match the Atlassian Developer Console callback URL "
                "byte-for-byte, or the code expired.</p>"
            )
        elif (
            "certificate verification failed" in msg.lower()
            or "CERTIFICATE_VERIFY_FAILED" in msg
        ):
            hint = (
                "<p><strong>Quick fix (dev only, insecure):</strong> add "
                "<code>CODE_AGENTS_HTTPS_VERIFY=0</code> to <code>.env</code>, restart Code Agents, then start "
                "OAuth again from <code>/oauth/atlassian/</code> (the previous authorization code is invalid).</p>"
                "<p><strong>Better:</strong> set <code>SSL_CERT_FILE</code> to a PEM bundle that trusts your "
                "corporate TLS inspection root.</p>"
            )
        # 400 = Atlassian rejected the request; 503 = local TLS/connect to auth.atlassian.com; 502 = Atlassian 5xx
        if "Code exchange failed HTTP 4" in msg:
            status = 400
        elif (
            "certificate verification failed" in msg.lower()
            or "CERTIFICATE_VERIFY_FAILED" in msg
            or msg.startswith("Connection to auth.atlassian.com failed")
        ):
            status = 503
        elif "Code exchange failed HTTP 5" in msg:
            status = 502
        else:
            status = 502
        return HTMLResponse(
            f"<html><body><h1>Token exchange failed</h1><pre>{detail}</pre>{hint}</body></html>",
            status_code=status,
        )

    persist_oauth_token_response(client_id, tokens, previous_refresh=None)

    goto = _success_redirect_url()
    if goto:
        logger.info("Atlassian OAuth success, redirecting to ATLASSIAN_OAUTH_SUCCESS_REDIRECT")
        return RedirectResponse(url=goto, status_code=302)

    webui = _open_webui_public_url()
    if webui:
        back = (
            f'<p>Tokens saved. Return to <a href="{html.escape(webui)}">Open WebUI</a>.</p>'
            "<p>You can close this tab.</p>"
        )
    else:
        back = (
            "<p>Tokens saved. If you use Open WebUI for chat, open it in another tab "
            "(often <a href=\"http://localhost:8080\">http://localhost:8080</a> — not this server’s port).</p>"
            "<p>Or run <code>examples/atlassian_mcp_client.py</code>. Set "
            "<code>OPEN_WEBUI_PUBLIC_URL</code> in <code>.env</code> so this page links to your chat UI.</p>"
        )

    return HTMLResponse(
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Authorized</title></head>"
        "<body style=\"font-family: system-ui; max-width: 36rem; margin: 3rem auto;\">"
        "<h1>Signed in</h1>"
        f"{back}"
        "</body></html>"
    )
