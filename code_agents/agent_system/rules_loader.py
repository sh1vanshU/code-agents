"""
Rules loader for Code Agents.

Two-tier rules that get injected into agent system prompts:
  1. Global:   ~/.code-agents/rules/       (apply to all projects)
  2. Project:  {repo}/.code-agents/rules/  (apply to this project only)

File naming determines targeting:
  _global.md        → all agents
  code-writer.md    → only the "code-writer" agent

Merge order (all concatenated, later appends):
  global/_global → global/{agent} → project/_global → project/{agent}

Rules are read from disk on every call — no cache, auto-refresh.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.rules_loader")

GLOBAL_RULES_DIR = Path.home() / ".code-agents" / "rules"
PROJECT_RULES_DIRNAME = ".code-agents/rules"
ALL_AGENTS_FILENAME = "_global.md"


def _read_rules_dir(rules_dir: Path) -> dict[str, str]:
    """
    Read all .md files from a rules directory.
    Returns {filename_stem: content} e.g. {"_global": "...", "code-writer": "..."}.
    """
    result = {}
    if not rules_dir.is_dir():
        return result
    logger.debug("Reading rules from %s", rules_dir)
    for path in sorted(rules_dir.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                result[path.stem] = content
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Could not read rule file %s: %s", path, e)
    return result


def load_rules(
    agent_name: str,
    repo_path: Optional[str] = None,
) -> str:
    """
    Load and merge rules for a given agent.

    Returns a single string (possibly empty) to prepend to the system prompt.
    Called on every chat message — reads from disk every time (no cache).
    """
    sections: list[str] = []

    # Tier 1: Global rules
    global_rules = _read_rules_dir(GLOBAL_RULES_DIR)
    if "_global" in global_rules:
        sections.append(global_rules["_global"])
    if agent_name in global_rules:
        sections.append(global_rules[agent_name])

    # Tier 2: Project rules
    if repo_path:
        project_rules_dir = Path(repo_path) / PROJECT_RULES_DIRNAME
        project_rules = _read_rules_dir(project_rules_dir)
        if "_global" in project_rules:
            sections.append(project_rules["_global"])
        if agent_name in project_rules:
            sections.append(project_rules[agent_name])

    if not sections:
        logger.debug("No rules found for agent=%s", agent_name)
        return ""

    logger.info("Loaded %d rule sections for agent=%s", len(sections), agent_name)
    return "\n\n".join(sections)


def list_rules(
    agent_name: Optional[str] = None,
    repo_path: Optional[str] = None,
) -> list[dict[str, str]]:
    """
    List all rule files that apply to a given agent (or all if agent_name is None).

    Returns list of dicts:
      [{"path": str, "scope": "global"|"project", "target": "_global"|"code-writer", "preview": str}]
    """
    results = []

    tiers = [("global", GLOBAL_RULES_DIR)]
    if repo_path:
        tiers.append(("project", Path(repo_path) / PROJECT_RULES_DIRNAME))

    for scope, rules_dir in tiers:
        if not rules_dir.is_dir():
            continue
        for path in sorted(rules_dir.glob("*.md")):
            target = path.stem
            # Filter: show if no agent specified, or if _global, or if matches agent
            if agent_name and target != "_global" and target != agent_name:
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeDecodeError):
                content = "(unreadable)"
            preview = content[:80] + "..." if len(content) > 80 else content
            preview = preview.replace("\n", " ")
            results.append({
                "path": str(path),
                "scope": scope,
                "target": target,
                "preview": preview,
            })

    return results
