"""Public URLs for OAuth registration, Open WebUI, and docs (avoid hardcoding localhost)."""

from __future__ import annotations

import logging
import os

from .config import settings

logger = logging.getLogger("code_agents.core.public_urls")


def code_agents_public_base_url() -> str:
    """
    Origin where users reach Code Agents in a browser (Open WebUI API base is this + /v1).

    Set CODE_AGENTS_PUBLIC_BASE_URL (or ATLASSIAN_OAUTH_PUBLIC_BASE_URL) when tunneled or behind a proxy.
    Default: http://127.0.0.1:{PORT}
    """
    for key in ("CODE_AGENTS_PUBLIC_BASE_URL", "ATLASSIAN_OAUTH_PUBLIC_BASE_URL"):
        v = os.getenv(key, "").strip().rstrip("/")
        if v:
            return v
    return f"http://127.0.0.1:{settings.port}"


def atlassian_cloud_site_url() -> str | None:
    """Your Jira/Confluence site, e.g. https://acme.atlassian.net — not the OAuth callback host."""
    v = os.getenv("ATLASSIAN_CLOUD_SITE_URL", "").strip().rstrip("/")
    return v or None
