"""Inline agent delegation — /<agent> prompts and /agent:skill parsing."""

from __future__ import annotations

import logging
import sys
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_delegation")


def parse_inline_delegation(
    user_input: str, available_agents: dict[str, str]
) -> tuple[Optional[str], Optional[str]]:
    """
    Parse a slash command for inline agent delegation.

    Supports:
      /<agent> <prompt>         -> delegate to agent with prompt
      /<agent>                  -> permanent switch to agent (empty prompt)
      /<agent>:<skill>          -> invoke agent's skill
      /<agent>:<skill> <prompt> -> invoke skill with extra context

    Returns (agent_name, prompt) if it matches, or (None, None) otherwise.
    """
    from .chat_ui import dim, yellow

    if not user_input.startswith("/"):
        return None, None
    parts = user_input.split(None, 1)
    slash_cmd = parts[0][1:]  # strip leading /
    slash_arg = parts[1] if len(parts) > 1 else ""

    if ":" in slash_cmd:
        agent_part, skill_name = slash_cmd.split(":", 1)
        if agent_part in available_agents and skill_name:
            from code_agents.core.config import settings
            from code_agents.agent_system.skill_loader import get_skill

            skill = get_skill(settings.agents_dir, agent_part, skill_name)
            if skill:
                skill_prompt = f"[Skill: {skill.name}]\n{skill.body}"
                if slash_arg:
                    skill_prompt += f"\n\nUser context: {slash_arg}"
                return agent_part, skill_prompt
            print(yellow(f"  Skill '{skill_name}' not found for agent '{agent_part}'."))
            print(dim(f"  Use /skills {agent_part} to see available skills."))
            return None, None

    if slash_cmd in available_agents:
        return slash_cmd, slash_arg
    return None, None
