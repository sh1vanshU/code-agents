"""Agent memory — persist learnings across sessions.

Each agent can save/load memories to ~/.code-agents/memory/<agent>.md
Memories are markdown files with key observations the agent learned.
Injected into system prompt context on each message.
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.agent_memory")

MEMORY_DIR = Path.home() / ".code-agents" / "memory"


def load_memory(agent_name: str) -> str:
    """Load agent's memory file. Returns empty string if none."""
    path = MEMORY_DIR / f"{agent_name}.md"
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return ""


def save_memory(agent_name: str, content: str) -> None:
    """Save/overwrite agent's memory."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    path = MEMORY_DIR / f"{agent_name}.md"
    path.write_text(content, encoding="utf-8")


def append_memory(agent_name: str, entry: str) -> None:
    """Append a learning entry to agent's memory."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    path = MEMORY_DIR / f"{agent_name}.md"
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n- {entry}\n")


def clear_memory(agent_name: str) -> bool:
    """Clear agent's memory. Returns True if file existed."""
    path = MEMORY_DIR / f"{agent_name}.md"
    if path.is_file():
        path.unlink()
        return True
    return False


def list_memories() -> dict[str, int]:
    """List all agents with memories. Returns {agent: line_count}."""
    if not MEMORY_DIR.is_dir():
        return {}
    result = {}
    for f in MEMORY_DIR.glob("*.md"):
        lines = f.read_text(encoding="utf-8").strip().splitlines()
        result[f.stem] = len(lines)
    return result
