"""Skill Marketplace — install, search, and share community skills.

Skills are standalone .md files with YAML frontmatter.
This module enables:
  - Fetching skills from URLs (GitHub raw, gists, registry)
  - Installing to the community skills directory
  - Listing/removing installed community skills
  - Validating skill files for safety

Community skills are stored in:
  ~/.code-agents/community-skills/<agent>/<skill>.md
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen, Request

logger = logging.getLogger("code_agents.agent_system.skill_marketplace")

COMMUNITY_SKILLS_DIR = Path.home() / ".code-agents" / "community-skills"
REGISTRY_CACHE = Path.home() / ".code-agents" / ".skill-registry-cache.json"
REGISTRY_TTL = 3600  # 1 hour cache

# Default registry URL (can be overridden via env)
DEFAULT_REGISTRY_URL = os.getenv(
    "CODE_AGENTS_SKILL_REGISTRY",
    "https://raw.githubusercontent.com/code-agents-org/code-agents-skills/main/registry.json",
)


@dataclass
class SkillInfo:
    """A skill entry from the registry."""
    name: str
    agent: str
    description: str
    url: str
    author: str = ""
    version: str = ""
    downloads: int = 0
    tags: list[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def fetch_registry(force: bool = False) -> list[SkillInfo]:
    """Fetch the skill registry, using cache if available."""
    # Check cache
    if not force and REGISTRY_CACHE.is_file():
        try:
            cache = json.loads(REGISTRY_CACHE.read_text())
            if time.time() - cache.get("fetched_at", 0) < REGISTRY_TTL:
                return [SkillInfo(**s) for s in cache.get("skills", [])]
        except (json.JSONDecodeError, OSError):
            pass

    # Fetch from URL
    try:
        req = Request(DEFAULT_REGISTRY_URL, headers={"User-Agent": "code-agents"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        skills = [SkillInfo(**s) for s in data.get("skills", [])]

        # Cache
        REGISTRY_CACHE.parent.mkdir(parents=True, exist_ok=True)
        REGISTRY_CACHE.write_text(json.dumps({
            "fetched_at": time.time(),
            "skills": [s.__dict__ for s in skills],
        }))
        return skills
    except (URLError, OSError, json.JSONDecodeError, TypeError) as e:
        logger.warning("Failed to fetch skill registry: %s", e)
        return []


def search_registry(query: str, force_refresh: bool = False) -> list[SkillInfo]:
    """Search the registry for skills matching a query."""
    query_lower = query.lower()
    results = []
    for skill in fetch_registry(force=force_refresh):
        searchable = f"{skill.name} {skill.description} {skill.agent} {' '.join(skill.tags)}"
        if query_lower in searchable.lower():
            results.append(skill)
    return results


# ---------------------------------------------------------------------------
# Install / Remove
# ---------------------------------------------------------------------------


def install_skill(source: str, agent: str = "_shared") -> tuple[bool, str]:
    """Install a skill from URL or registry name.

    Args:
        source: URL to a .md file, or a registry shortname
        agent: Target agent directory (default: _shared)

    Returns:
        (success, message)
    """
    # Resolve source to URL
    url = _resolve_source(source)
    if not url:
        return False, f"Could not resolve source: {source}"

    # Download
    content = _download_skill(url)
    if not content:
        return False, f"Failed to download: {url}"

    # Validate
    is_valid, validation_msg = validate_skill(content)
    if not is_valid:
        return False, f"Validation failed: {validation_msg}"

    # Extract name from frontmatter
    name = _extract_skill_name(content)
    if not name:
        # Use URL filename
        name = url.rstrip("/").split("/")[-1].replace(".md", "")

    # Sanitize name — reject path traversal attempts
    name = name.replace("..", "").replace("/", "").replace("\\", "").strip(".")
    if not name:
        return False, "Invalid skill name (empty after sanitization)"

    # Install
    target_dir = COMMUNITY_SKILLS_DIR / agent / "skills"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{name}.md"

    if target_file.exists():
        return False, f"Skill already installed: {name} (use remove first)"

    try:
        target_file.write_text(content)
        logger.info("Installed skill: %s → %s", name, target_file)
        return True, f"Installed: {agent}:{name} → {target_file}"
    except OSError as e:
        return False, f"Failed to write skill: {e}"


def remove_skill(agent: str, skill_name: str) -> tuple[bool, str]:
    """Remove an installed community skill."""
    target_file = COMMUNITY_SKILLS_DIR / agent / "skills" / f"{skill_name}.md"
    if not target_file.exists():
        return False, f"Skill not found: {agent}:{skill_name}"

    try:
        target_file.unlink()
        logger.info("Removed skill: %s:%s", agent, skill_name)
        return True, f"Removed: {agent}:{skill_name}"
    except OSError as e:
        return False, f"Failed to remove: {e}"


def list_installed() -> dict[str, list[dict]]:
    """List all installed community skills, grouped by agent."""
    result: dict[str, list[dict]] = {}
    if not COMMUNITY_SKILLS_DIR.exists():
        return result

    for agent_dir in sorted(COMMUNITY_SKILLS_DIR.iterdir()):
        if not agent_dir.is_dir():
            continue
        skills_dir = agent_dir / "skills"
        if not skills_dir.is_dir():
            continue
        agent_name = agent_dir.name
        skills = []
        for md_file in sorted(skills_dir.glob("*.md")):
            content = md_file.read_text()
            name = _extract_skill_name(content) or md_file.stem
            desc = _extract_skill_description(content)
            skills.append({
                "name": name,
                "description": desc,
                "path": str(md_file),
                "size": md_file.stat().st_size,
            })
        if skills:
            result[agent_name] = skills
    return result


def get_skill_info(agent: str, skill_name: str) -> Optional[dict]:
    """Get detailed info about an installed skill."""
    target_file = COMMUNITY_SKILLS_DIR / agent / "skills" / f"{skill_name}.md"
    if not target_file.exists():
        return None

    content = target_file.read_text()
    return {
        "name": _extract_skill_name(content) or skill_name,
        "agent": agent,
        "description": _extract_skill_description(content),
        "path": str(target_file),
        "size": target_file.stat().st_size,
        "content_preview": content[:500],
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


_SUSPICIOUS_PATTERNS = [
    r"subprocess\.(?:call|run|Popen)",
    r"os\.system\s*\(",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__\s*\(",
    r"rm\s+-rf\s+/",
    r"curl\s+.*\|\s*(?:bash|sh)",
    r"wget\s+.*\|\s*(?:bash|sh)",
]


def validate_skill(content: str) -> tuple[bool, str]:
    """Validate a skill file for safety and correctness.

    Returns (is_valid, message).
    """
    if not content.strip():
        return False, "Empty skill content"

    # Must have frontmatter
    if not content.strip().startswith("---"):
        return False, "Missing YAML frontmatter (must start with ---)"

    # Check for suspicious patterns in the body
    for pattern in _SUSPICIOUS_PATTERNS:
        if re.search(pattern, content):
            return False, f"Suspicious pattern detected: {pattern}"

    # Must have a name in frontmatter
    name = _extract_skill_name(content)
    if not name:
        return False, "Missing 'name' field in frontmatter"

    # Reasonable size check
    if len(content) > 100_000:
        return False, "Skill too large (>100KB)"

    return True, "Valid"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_source(source: str) -> Optional[str]:
    """Resolve a source string to a download URL."""
    # Already a URL
    if source.startswith("http://") or source.startswith("https://"):
        # Convert GitHub blob URLs to raw
        if "github.com" in source and "/blob/" in source:
            return source.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        return source

    # GitHub gist shorthand: gist:<id>
    if source.startswith("gist:"):
        gist_id = source[5:]
        return f"https://gist.githubusercontent.com/{gist_id}/raw"

    # Registry shortname — search registry
    registry = fetch_registry()
    for skill in registry:
        if skill.name == source or f"{skill.agent}:{skill.name}" == source:
            return skill.url

    return None


def _download_skill(url: str) -> Optional[str]:
    """Download a skill from URL. Returns content or None."""
    try:
        req = Request(url, headers={"User-Agent": "code-agents"})
        with urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except (URLError, OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to download skill from %s: %s", url, e)
        return None


def _extract_skill_name(content: str) -> str:
    """Extract skill name from YAML frontmatter."""
    match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if match:
        for line in match.group(1).splitlines():
            if line.strip().startswith("name:"):
                return line.partition(":")[2].strip().strip("'\"")
    return ""


def _extract_skill_description(content: str) -> str:
    """Extract skill description from YAML frontmatter."""
    match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if match:
        for line in match.group(1).splitlines():
            if line.strip().startswith("description:"):
                return line.partition(":")[2].strip().strip("'\"")
    return ""
