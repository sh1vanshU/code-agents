"""Claude Code CLI plugin exporter.

Exports code-agents as a Claude Code CLI plugin directory with:
  - plugin.json manifest
  - agents/<name>.md per agent (system prompt + context)
  - skills/<agent>/<skill>/SKILL.md per skill
  - .mcp.json for MCP server integration
  - settings.json for defaults
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.plugin_exporter")

_VERSION = "1.3.0"

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)",
    re.DOTALL,
)


def _parse_yaml_simple(text: str) -> dict[str, str]:
    """Minimal key: value YAML parser (avoids PyYAML dependency)."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _read_agent_yaml(yaml_path: Path) -> Optional[dict[str, str]]:
    """Read agent YAML and extract flat key-value pairs.

    Handles the multi-line system_prompt by capturing everything between
    'system_prompt: |' and the next top-level key.
    """
    try:
        content = yaml_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Cannot read %s: %s", yaml_path, e)
        return None

    meta: dict[str, str] = {}

    # Extract simple top-level keys
    for line in content.splitlines():
        if line and not line[0].isspace() and ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"').strip("'")

    # Extract system_prompt block (indented under system_prompt: |)
    sp_match = re.search(
        r"^system_prompt:\s*\|\s*\n((?:[ \t]+.*\n?)*)",
        content,
        re.MULTILINE,
    )
    if sp_match:
        raw = sp_match.group(1)
        # Dedent: find minimum indent and strip it
        lines = raw.splitlines()
        indent = min(
            (len(l) - len(l.lstrip()) for l in lines if l.strip()),
            default=0,
        )
        meta["system_prompt"] = "\n".join(l[indent:] for l in lines).strip()

    # Extract routing.description
    rd_match = re.search(
        r"^\s+description:\s*(.+)$",
        content,
        re.MULTILINE,
    )
    if rd_match:
        meta["routing_description"] = rd_match.group(1).strip().strip('"').strip("'")

    return meta


def _read_identity_from_agents_md(agents_md_path: Path) -> str:
    """Extract the Identity section from agents.md, or first paragraph."""
    try:
        content = agents_md_path.read_text(encoding="utf-8")
    except OSError:
        return ""

    # Look for ## Identity section
    match = re.search(
        r"^##\s+Identity\s*\n(.*?)(?=\n##\s|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    # Fallback: first non-heading paragraph
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def export_claude_code_plugin(
    output_dir: str,
    agents_dir: str = "",
) -> dict:
    """Export code-agents as a Claude Code CLI plugin.

    Creates a plugin directory structure at *output_dir* containing manifests,
    agent definitions, and skill files in Claude Code's expected format.

    Args:
        output_dir: Destination directory for the plugin.
        agents_dir: Path to the agents/ directory. Auto-detected if empty.

    Returns:
        Stats dict: {"agents": N, "skills": N, "output_dir": str}
    """
    out = Path(output_dir)
    agents_root = Path(agents_dir) if agents_dir else _find_agents_dir()

    if not agents_root or not agents_root.is_dir():
        logger.error("Agents directory not found: %s", agents_root)
        return {"agents": 0, "skills": 0, "output_dir": str(out), "error": "agents dir not found"}

    logger.info("Exporting Claude Code plugin to %s", out)

    agent_count = 0
    skill_count = 0

    # --- 1. plugin.json manifest ---
    plugin_dir = out / ".claude-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": "code-agents",
        "version": _VERSION,
        "description": "13 specialist AI agents for CI/CD, code analysis, testing, and DevOps",
        "userConfig": {
            "JENKINS_URL": {
                "description": "Jenkins server URL",
                "sensitive": False,
            },
            "JENKINS_TOKEN": {
                "description": "Jenkins API token",
                "sensitive": True,
            },
            "ARGOCD_URL": {
                "description": "ArgoCD server URL",
                "sensitive": False,
            },
            "ARGOCD_TOKEN": {
                "description": "ArgoCD auth token",
                "sensitive": True,
            },
            "JIRA_URL": {
                "description": "Jira instance URL",
                "sensitive": False,
            },
            "JIRA_TOKEN": {
                "description": "Jira API token",
                "sensitive": True,
            },
        },
    }
    _write_json(plugin_dir / "plugin.json", manifest)
    logger.info("Created plugin manifest: %s", plugin_dir / "plugin.json")

    # --- 2. Agent definitions ---
    agents_out = out / "agents"
    agents_out.mkdir(parents=True, exist_ok=True)

    for subdir in sorted(agents_root.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith((".", "_")):
            continue

        yaml_path = subdir / f"{subdir.name}.yaml"
        if not yaml_path.is_file():
            continue

        agent_name = subdir.name.replace("_", "-")
        meta = _read_agent_yaml(yaml_path)
        if not meta:
            continue

        # Build agent markdown
        agents_md_path = subdir / "agents.md"
        identity = _read_identity_from_agents_md(agents_md_path)
        description = identity or meta.get("routing_description", meta.get("display_name", agent_name))

        system_prompt = meta.get("system_prompt", "")

        sections = [
            f"---\nname: {agent_name}\ndescription: {description}\n---\n",
        ]
        if system_prompt:
            sections.append(system_prompt)

        # Append full agents.md content if it exists
        if agents_md_path.is_file():
            try:
                agents_md_content = agents_md_path.read_text(encoding="utf-8").strip()
                if agents_md_content:
                    sections.append(agents_md_content)
            except OSError:
                pass

        agent_file = agents_out / f"{agent_name}.md"
        agent_file.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
        agent_count += 1
        logger.info("Exported agent: %s", agent_name)

    # --- 3. Skill files per agent ---
    skills_out = out / "skills"
    skills_out.mkdir(parents=True, exist_ok=True)

    for subdir in sorted(agents_root.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("."):
            continue

        skills_dir = subdir / "skills"
        if not skills_dir.is_dir():
            continue

        agent_name = subdir.name.replace("_", "-") if subdir.name != "_shared" else "_shared"

        for md_file in sorted(skills_dir.glob("*.md")):
            skill_name = md_file.stem
            skill_out_dir = skills_out / agent_name / skill_name
            skill_out_dir.mkdir(parents=True, exist_ok=True)

            dest = skill_out_dir / "SKILL.md"
            try:
                dest.write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")
                skill_count += 1
                logger.debug("Exported skill: %s/%s", agent_name, skill_name)
            except OSError as e:
                logger.warning("Failed to export skill %s/%s: %s", agent_name, skill_name, e)

    logger.info("Exported %d skills across agents + _shared", skill_count)

    # --- 4. .mcp.json ---
    mcp_config = {
        "mcpServers": {
            "code-agents": {
                "command": "code-agents",
                "args": ["serve", "--mcp"],
            }
        }
    }
    _write_json(out / ".mcp.json", mcp_config)
    logger.info("Created MCP config: %s", out / ".mcp.json")

    # --- 5. settings.json ---
    settings = {"default_agent": "auto-pilot"}
    _write_json(out / "settings.json", settings)
    logger.info("Created settings: %s", out / "settings.json")

    stats = {
        "agents": agent_count,
        "skills": skill_count,
        "output_dir": str(out),
    }
    logger.info(
        "Claude Code plugin export complete: %d agents, %d skills → %s",
        agent_count, skill_count, out,
    )
    return stats


def _write_json(path: Path, data: dict) -> None:
    """Write a JSON file with consistent formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _find_agents_dir() -> Optional[Path]:
    """Auto-detect the agents/ directory relative to this package."""
    # Walk up from this file to find agents/
    here = Path(__file__).resolve()
    for parent in [here.parent, here.parent.parent, here.parent.parent.parent]:
        candidate = parent / "agents"
        if candidate.is_dir() and (candidate / "_shared").is_dir():
            return candidate
    return None
