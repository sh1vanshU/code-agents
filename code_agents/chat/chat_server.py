"""Chat server communication — health check, agent list, streaming.

The interactive chat REPL (``chat_async_repl`` / ``chat.py``) talks to the **local
FastAPI server** over HTTP; it does not spawn ``cursor-agent`` itself. For each
user message it POSTs to ``/v1/agents/{agent}/chat/completions`` (see ``_stream_chat``).
The server then runs :func:`code_agents.core.backend.run_agent`, which either:

- calls **Cursor Cloud HTTP** (``CURSOR_API_URL`` + ``_run_cursor_http``), or
- invokes the **cursor-agent** subprocess via ``cursor_agent_sdk.query`` (default ``cursor`` backend).

So failures in the REPL are either HTTP errors (server down, 502 from handler) or
backend errors logged under ``code_agents.core.backend`` / ``code_agents.core.stream``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_server")


def _server_url() -> str:
    host = os.getenv("HOST", "127.0.0.1")
    port = os.getenv("PORT", "8000")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def _check_server(url: str) -> bool:
    """Check if the server is running. Delegates to chat_validation."""
    from .chat_validation import check_server
    return check_server(url)


def _check_workspace_trust(repo_path: str) -> bool:
    """Workspace trust check. Delegates to chat_validation."""
    from .chat_validation import check_workspace_trust
    return check_workspace_trust(repo_path)


def _get_agents(url: str) -> dict[str, str]:
    """Fetch agent list from server. Returns {name: display_name}."""
    import httpx
    try:
        r = httpx.get(f"{url}/v1/agents", timeout=5.0)
        data = r.json()
        if isinstance(data, dict):
            agents = data.get("data") or data.get("agents") or []
        elif isinstance(data, list):
            agents = data
        else:
            agents = []
        return {a.get("name", "?"): a.get("display_name", "") for a in agents if isinstance(a, dict)}
    except Exception:
        return {}


def _stream_chat(
    url: str,
    agent: str,
    messages: list[dict],
    session_id: Optional[str] = None,
    cwd: Optional[str] = None,
):
    """Send a chat request with streaming and yield response pieces."""
    import httpx

    body: dict = {
        "messages": messages,
        "stream": True,
        "include_session": True,
        "stream_tool_activity": True,
    }
    if session_id:
        body["session_id"] = session_id
    if cwd:
        body["cwd"] = cwd

    endpoint = f"{url}/v1/agents/{agent}/chat/completions"
    logger.info(
        "Chat REPL → POST %s (messages=%d stream=%s session=%s cwd=%s)",
        endpoint,
        len(messages),
        body.get("stream"),
        session_id or "-",
        cwd or "-",
    )

    try:
        # Long read timeout: agents may run tools (tests, coverage) for minutes
        # between SSE chunks.  Keep connect timeout short.
        _timeout = httpx.Timeout(connect=10.0, read=900.0, write=30.0, pool=10.0)
        _headers = {"Content-Type": "application/json"}
        if cwd:
            _headers["X-Repo-Path"] = cwd  # Multi-repo: pass repo path per request
        with httpx.stream(
            "POST", endpoint,
            json=body,
            headers=_headers,
            timeout=_timeout,
        ) as response:
            if response.status_code != 200:
                try:
                    _detail = response.text[:2000]
                except Exception:
                    _detail = ""
                logger.error(
                    "Chat stream failed: HTTP %s for %s body_snippet=%r",
                    response.status_code,
                    endpoint,
                    _detail[:800],
                )
                yield (
                    "error",
                    f"Server returned HTTP {response.status_code} for {endpoint}. "
                    f"{_detail[:500]}",
                )
                return

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if "session_id" in chunk:
                    yield ("session_id", chunk["session_id"])

                if "usage" in chunk:
                    yield ("usage", chunk["usage"])

                if "duration_ms" in chunk:
                    yield ("duration_ms", chunk["duration_ms"])

                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})

                content = delta.get("content", "")
                if content:
                    yield ("text", content)

                reasoning = delta.get("reasoning_content", "")
                if reasoning:
                    yield ("reasoning", reasoning)

    except httpx.ConnectError:
        yield ("error", "Cannot connect to server. Is it running? (code-agents start)")
    except httpx.ReadTimeout:
        yield ("error", "Request timed out (300s). The agent may be processing a large task.")
    except Exception as e:
        yield ("error", str(e))
