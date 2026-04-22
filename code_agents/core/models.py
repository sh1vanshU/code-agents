from __future__ import annotations

from typing import Any, Optional

import logging

from pydantic import BaseModel, ConfigDict, field_validator

logger = logging.getLogger("code_agents.core.models")


def _coerce_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


class Message(BaseModel):
    role: str
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[Any]] = None
    name: Optional[str] = None

    @field_validator("content", mode="before")
    @classmethod
    def _content_to_str(cls, v: Any) -> Any:
        """Open WebUI / some clients send multimodal content as a list of parts (OpenAI-style)."""
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, list):
            parts: list[str] = []
            for item in v:
                if isinstance(item, dict):
                    if item.get("type") == "text" and "text" in item:
                        parts.append(str(item.get("text") or ""))
                    elif "text" in item:
                        parts.append(str(item.get("text") or ""))
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts) if parts else None
        return v


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: Optional[str] = None
    messages: list[Message]
    stream: bool = False

    # Session
    session_id: Optional[str] = None
    include_session: Optional[bool] = None

    # Tool activity visibility (None = use agent YAML default)
    stream_tool_activity: Optional[bool] = None

    @field_validator("stream", mode="before")
    @classmethod
    def _stream_bool(cls, v: Any) -> bool:
        return _coerce_bool(v, default=False)

    @field_validator("include_session", "stream_tool_activity", mode="before")
    @classmethod
    def _optional_bool(cls, v: Any) -> Any:
        if v is None:
            return None
        return _coerce_bool(v, default=False)

    # Standard OpenAI fields (accepted but not all forwarded)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    n: Optional[int] = None
    stop: Optional[Any] = None
    seed: Optional[int] = None
    user: Optional[str] = None

    # Working directory override
    cwd: Optional[str] = None
