"""Cursor IDE exporter for code-agents.

Generates .cursorrules and .cursor/mcp.json in a target repo, giving
Cursor's AI full awareness of available agents, skills, and API endpoints.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.cursor_exporter")


def _parse_yaml_simple(text: str) -> dict[str, str]:
    """Minimal top-level key: value YAML parser."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if line and not line[0].isspace() and ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _read_routing_description(yaml_path: Path) -> str:
    """Read the routing.description field from an agent YAML."""
    try:
        content = yaml_path.read_text(encoding="utf-8")
    except OSError:
        return ""

    match = re.search(
        r"^\s+description:\s*(.+)$",
        content,
        re.MULTILINE,
    )
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return ""


_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


def _parse_skill_meta(md_path: Path) -> dict[str, str]:
    """Extract name and description from a skill's YAML frontmatter."""
    try:
        content = md_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {"name": md_path.stem, "description": ""}

    meta: dict[str, str] = {"name": md_path.stem, "description": ""}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def export_cursor(
    repo_path: str,
    agents_dir: str = "",
) -> dict:
    """Export code-agents config for Cursor IDE.

    Generates ``.cursorrules`` and ``.cursor/mcp.json`` in *repo_path*.

    Args:
        repo_path: Target repository root where files are written.
        agents_dir: Path to the agents/ directory. Auto-detected if empty.

    Returns:
        Stats dict: {"agents": N, "skills": N, "repo_path": str}
    """
    repo = Path(repo_path)
    agents_root = Path(agents_dir) if agents_dir else _find_agents_dir()

    if not agents_root or not agents_root.is_dir():
        logger.error("Agents directory not found: %s", agents_root)
        return {"agents": 0, "skills": 0, "repo_path": str(repo), "error": "agents dir not found"}

    logger.info("Exporting Cursor config to %s", repo)

    # --- Collect agents + skills ---
    agents: list[dict[str, str]] = []  # [{name, description}]
    skills_by_agent: dict[str, list[dict[str, str]]] = {}  # {agent: [{name, desc}]}
    total_skills = 0

    for subdir in sorted(agents_root.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith((".", "_")):
            continue

        yaml_path = subdir / f"{subdir.name}.yaml"
        if not yaml_path.is_file():
            continue

        agent_name = subdir.name.replace("_", "-")
        description = _read_routing_description(yaml_path)
        agents.append({"name": agent_name, "description": description})

        # Skills
        skills_dir = subdir / "skills"
        if skills_dir.is_dir():
            agent_skills: list[dict[str, str]] = []
            for md_file in sorted(skills_dir.glob("*.md")):
                meta = _parse_skill_meta(md_file)
                if meta:
                    agent_skills.append(meta)
                    total_skills += 1
            if agent_skills:
                skills_by_agent[agent_name] = agent_skills

    # Shared skills
    shared_dir = agents_root / "_shared" / "skills"
    shared_skills: list[dict[str, str]] = []
    if shared_dir.is_dir():
        for md_file in sorted(shared_dir.glob("*.md")):
            meta = _parse_skill_meta(md_file)
            if meta:
                shared_skills.append(meta)
                total_skills += 1

    # --- Load project rules (best effort) ---
    rules_text = _load_rules_safe(repo_path)

    # --- Build .cursorrules ---
    lines: list[str] = []
    lines.append("# Code Agents — Project Rules for Cursor\n")

    # Agents table
    lines.append("## Available Specialist Agents")
    lines.append("| Agent | Specialization |")
    lines.append("|-------|---------------|")
    for a in agents:
        lines.append(f"| {a['name']} | {a['description']} |")
    lines.append("")

    # Skills (name + one-liner only, keep under token budget)
    lines.append("## Available Skills")
    for agent_name, agent_skills in sorted(skills_by_agent.items()):
        lines.append(f"### {agent_name}")
        for s in agent_skills:
            desc = f" — {s['description']}" if s.get("description") else ""
            lines.append(f"- {s['name']}{desc}")
        lines.append("")

    if shared_skills:
        lines.append("### _shared (cross-agent)")
        for s in shared_skills:
            desc = f" — {s['description']}" if s.get("description") else ""
            lines.append(f"- {s['name']}{desc}")
        lines.append("")

    # API endpoints (concise reference)
    lines.append("## API Endpoints (curl to http://127.0.0.1:8000)")
    lines.append(_api_endpoints_section())
    lines.append("")

    # Project rules
    if rules_text:
        lines.append("## Project Rules")
        lines.append(rules_text)
        lines.append("")

    # Usage hint
    lines.append("## Usage")
    lines.append("Start the server: `code-agents start`")
    lines.append("Interactive chat: `code-agents chat`")
    lines.append("Switch agents in chat: `/agent <name>` or `/<agent> <prompt>`")
    lines.append("Invoke a skill: `/<agent>:<skill>`")
    lines.append("")

    cursorrules_content = "\n".join(lines)

    # Write .cursorrules
    repo.mkdir(parents=True, exist_ok=True)
    cursorrules_path = repo / ".cursorrules"
    cursorrules_path.write_text(cursorrules_content, encoding="utf-8")
    logger.info("Created %s (%d chars)", cursorrules_path, len(cursorrules_content))

    # --- .cursor/mcp.json ---
    cursor_dir = repo / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)

    mcp_config = {
        "mcpServers": {
            "code-agents": {
                "command": "code-agents",
                "args": ["serve", "--mcp"],
            }
        }
    }
    mcp_path = cursor_dir / "mcp.json"
    mcp_path.write_text(json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8")
    logger.info("Created %s", mcp_path)

    stats = {
        "agents": len(agents),
        "skills": total_skills,
        "repo_path": str(repo),
    }
    logger.info(
        "Cursor export complete: %d agents, %d skills → %s",
        len(agents), total_skills, repo,
    )
    return stats


def _api_endpoints_section() -> str:
    """Return a concise API endpoint reference."""
    return """### Jenkins
- GET /jenkins/jobs?folder=FOLDER
- GET /jenkins/jobs/{JOB_PATH}/parameters
- POST /jenkins/build-and-wait
- GET /jenkins/build/{job_name}/{build_number}/status
- GET /jenkins/build/{job_name}/{build_number}/log
- GET /jenkins/build/{job_name}/last

### ArgoCD
- GET /argocd/apps/{app}/status
- GET /argocd/apps/{app}/pods
- GET /argocd/apps/{app}/events
- POST /argocd/apps/{app}/sync
- POST /argocd/apps/{app}/rollback

### Git
- GET /git/status
- GET /git/branches
- GET /git/current-branch
- GET /git/log?branch=BRANCH&limit=5
- GET /git/diff?base=main&head=BRANCH

### Jira
- GET /jira/issue/{key}
- POST /jira/issue
- PUT /jira/issue/{key}/transition
- GET /jira/search?jql=JQL

### Testing
- POST /testing/run
- GET /testing/coverage

### Redash
- GET /redash/queries
- POST /redash/queries/{id}/results"""


def _load_rules_safe(repo_path: str) -> str:
    """Load project rules via rules_loader, silently returning '' on failure."""
    try:
        from code_agents.agent_system.rules_loader import load_rules
        return load_rules("_global", repo_path=repo_path)
    except Exception:
        logger.debug("Could not load rules for %s", repo_path)
        return ""


def _find_agents_dir() -> Optional[Path]:
    """Auto-detect the agents/ directory relative to this package."""
    here = Path(__file__).resolve()
    for parent in [here.parent, here.parent.parent, here.parent.parent.parent]:
        candidate = parent / "agents"
        if candidate.is_dir() and (candidate / "_shared").is_dir():
            return candidate
    return None
