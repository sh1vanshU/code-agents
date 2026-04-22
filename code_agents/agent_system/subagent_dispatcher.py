"""Subagent dispatcher — invoke agents programmatically via API."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger("code_agents.agent_system.subagent_dispatcher")


@dataclass
class SubagentResult:
    """Result from a subagent invocation."""

    agent: str
    response: str
    duration_ms: int
    success: bool
    error: Optional[str] = None


class SubagentDispatcher:
    """Dispatch requests to agents via the local API server."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")

    def dispatch(
        self,
        agent_name: str,
        query: str,
        cwd: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout: int = 120,
    ) -> SubagentResult:
        """Send a query to an agent and collect the full response."""
        url = f"{self.base_url}/v1/agents/{agent_name}/chat/completions"
        payload = {
            "messages": [{"role": "user", "content": query}],
            "stream": False,
        }
        if session_id:
            payload["session_id"] = session_id

        headers = {"Content-Type": "application/json"}
        if cwd:
            headers["X-Repo-Path"] = cwd

        start = time.monotonic()
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            elapsed = int((time.monotonic() - start) * 1000)

            if resp.status_code != 200:
                return SubagentResult(
                    agent=agent_name,
                    response="",
                    duration_ms=elapsed,
                    success=False,
                    error=f"HTTP {resp.status_code}: {resp.text[:500]}",
                )

            data = resp.json()
            content = ""
            if "choices" in data and data["choices"]:
                msg = data["choices"][0].get("message", {})
                content = msg.get("content", "")

            return SubagentResult(
                agent=agent_name,
                response=content,
                duration_ms=elapsed,
                success=True,
            )

        except requests.Timeout:
            elapsed = int((time.monotonic() - start) * 1000)
            return SubagentResult(
                agent=agent_name,
                response="",
                duration_ms=elapsed,
                success=False,
                error=f"Timeout after {timeout}s",
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return SubagentResult(
                agent=agent_name,
                response="",
                duration_ms=elapsed,
                success=False,
                error=str(e),
            )

    def explore(
        self,
        query: str,
        cwd: Optional[str] = None,
        timeout: int = 120,
    ) -> SubagentResult:
        """Shortcut for invoking the explore agent."""
        return self.dispatch("explore", query, cwd=cwd, timeout=timeout)
