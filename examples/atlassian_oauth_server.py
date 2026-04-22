#!/usr/bin/env python3
"""
Standalone Atlassian OAuth UI (optional). Prefer the main Code Agents app:

  poetry run code-agents
  # with ATLASSIAN_OAUTH_* set → http://localhost:8000/oauth/atlassian/

This file runs the same router on its own port (e.g. 8766) if you do not use the main server.
"""

from __future__ import annotations

from fastapi import FastAPI

from code_agents.routers.atlassian_oauth_web import router

app = FastAPI(title="Atlassian OAuth (standalone)")
app.include_router(router)
