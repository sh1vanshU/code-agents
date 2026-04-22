"""Message shapes shared with cursor-agent-sdk / claude-agent-sdk (duck-typed in stream)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("code_agents.core.message_types")

__all__ = [
    "AssistantMessage",
    "ResultMessage",
    "SystemMessage",
    "TextBlock",
    "ToolResultBlock",
    "ToolUseBlock",
]


@dataclass
class TextBlock:
    text: str = ""


@dataclass
class ToolUseBlock:
    name: str = ""
    input: Any = None
    id: str = ""


@dataclass
class ToolResultBlock:
    content: Any = None
    tool_use_id: str = ""


@dataclass
class SystemMessage:
    subtype: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantMessage:
    content: list[Any] = field(default_factory=list)
    model: str = ""


@dataclass
class ResultMessage:
    subtype: str = ""
    duration_ms: int = 0
    duration_api_ms: int = 0
    is_error: bool = False
    session_id: str = ""
    usage: Optional[dict[str, Any]] = None
