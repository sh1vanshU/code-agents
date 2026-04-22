"""
Agent skill loader — discover and load reusable workflows from agent subfolders.

Skills are markdown files in agents/<agent>/skills/<skill>.md with YAML frontmatter:

    ---
    name: build
    description: Trigger Jenkins build, poll, extract version
    ---

    ## Workflow
    1. Fetch build job parameters
    2. Trigger build with /jenkins/build-and-wait
    ...

Skills can be invoked from chat as /<agent>:<skill> or listed with /skills.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.skill_loader")


@dataclass
class Skill:
    """A reusable workflow/capability belonging to an agent."""
    name: str
    agent: str
    description: str
    body: str  # markdown content (the workflow instructions)
    path: str = ""  # file path for reference
    resources_dir: str = ""  # directory with bundled scripts/references (Level 3)
    risk_tier: str = ""  # "high", "medium", "low" (enterprise governance)
    requires: list = field(default_factory=list)  # required env vars (e.g. ["JENKINS_URL"])

    @property
    def full_name(self) -> str:
        """Agent-qualified name: agent:skill."""
        return f"{self.agent}:{self.name}"


_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)",
    re.DOTALL,
)


def _parse_list(value: str) -> list[str]:
    """Parse a YAML-ish list value: '[A, B]' or 'A, B' → ['A', 'B']."""
    value = value.strip().strip("[]")
    if not value:
        return []
    return [v.strip().strip('"').strip("'") for v in value.split(",") if v.strip()]


def _parse_skill_file(path: Path, agent_name: str) -> Optional[Skill]:
    """Parse a skill .md file with YAML frontmatter."""
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if not content:
        return None

    # Parse frontmatter
    match = _FRONTMATTER_RE.match(content)
    if match:
        frontmatter_text = match.group(1)
        body = match.group(2).strip()

        # Simple key: value parsing (avoid yaml dependency for speed)
        meta: dict[str, str] = {}
        for line in frontmatter_text.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip().strip('"').strip("'")

        name = meta.get("name", path.stem)
        # Sanitize name — reject path traversal
        name = name.replace("..", "").replace("/", "").replace("\\", "").strip(".")
        if not name:
            name = path.stem
        description = meta.get("description", "")
    else:
        # No frontmatter — use filename as name, entire content as body
        name = path.stem
        description = ""
        body = content

    # Check for bundled resources directory (Level 3)
    resources_dir = ""
    skill_dir = path.parent / name
    if skill_dir.is_dir():
        resources_dir = str(skill_dir)
    elif path.name == "SKILL.md":
        # Skill is a directory — resources are siblings
        resources_dir = str(path.parent)

    return Skill(
        name=name,
        agent=agent_name,
        description=description,
        body=body,
        path=str(path),
        resources_dir=resources_dir,
        risk_tier=meta.get("risk_tier", "") if match else "",
        requires=_parse_list(meta.get("requires", "")) if match else [],
    )


def load_agent_skills(agents_dir: str | Path) -> dict[str, list[Skill]]:
    """
    Load all skills from agents/<agent>/skills/*.md.

    Also loads shared engineering skills from agents/_shared/skills/*.md.
    Shared skills are available to ALL agents under the key "_shared".

    Returns: {agent_name: [Skill, ...], "_shared": [Skill, ...]}
    """
    agents_dir = Path(agents_dir)
    result: dict[str, list[Skill]] = {}

    if not agents_dir.is_dir():
        return result

    # Load community-installed skills from ~/.code-agents/community-skills/
    community_dir = Path.home() / ".code-agents" / "community-skills"
    if community_dir.is_dir():
        for agent_dir in sorted(community_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            skills_dir = agent_dir / "skills"
            if not skills_dir.is_dir():
                continue
            agent_name = agent_dir.name
            community_skills: list[Skill] = []
            for md_file in sorted(skills_dir.glob("*.md")):
                skill = _parse_skill_file(md_file, agent_name)
                if skill:
                    community_skills.append(skill)
                    logger.debug("Loaded community skill: %s (%s)", skill.full_name, md_file)
            if community_skills:
                result.setdefault(agent_name, []).extend(community_skills)

    # Load shared skills from agents/_shared/skills/
    shared_dir = agents_dir / "_shared" / "skills"
    if shared_dir.is_dir():
        shared_skills: list[Skill] = []
        for md_file in sorted(shared_dir.glob("*.md")):
            skill = _parse_skill_file(md_file, "_shared")
            if skill:
                shared_skills.append(skill)
                logger.debug("Loaded shared skill: %s (%s)", skill.name, md_file)
        if shared_skills:
            result["_shared"] = shared_skills

    # Load per-agent skills
    for subdir in sorted(agents_dir.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith((".", "_")):
            continue

        skills_dir = subdir / "skills"
        if not skills_dir.is_dir():
            continue

        # Agent name: snake_case folder → kebab-case agent name
        agent_name = subdir.name.replace("_", "-")
        skills: list[Skill] = []

        # Load skill files (*.md)
        for md_file in sorted(skills_dir.glob("*.md")):
            skill = _parse_skill_file(md_file, agent_name)
            if skill:
                skills.append(skill)
                logger.debug("Loaded skill: %s (%s)", skill.full_name, md_file)

        # Load skill directories (*/SKILL.md) — Level 3 support
        _seen_names = {s.name for s in skills}
        for skill_subdir in sorted(skills_dir.iterdir()):
            if skill_subdir.is_dir() and not skill_subdir.name.startswith("."):
                skill_md = skill_subdir / "SKILL.md"
                if skill_md.exists() and skill_subdir.name not in _seen_names:
                    skill = _parse_skill_file(skill_md, agent_name)
                    if skill:
                        skills.append(skill)
                        logger.debug("Loaded skill dir: %s (%s)", skill.full_name, skill_md)

        if skills:
            result[agent_name] = skills

    return result


def get_skill(
    agents_dir: str | Path,
    agent_name: str,
    skill_name: str,
) -> Optional[Skill]:
    """
    Load a specific skill by name.

    Supports cross-agent skill sharing:
      - "build"              → look in current agent's skills/
      - "jenkins-cicd:build" → look in jenkins-cicd's skills/ (cross-agent)

    This allows agents like auto-pilot to use skills from specialist agents.
    """
    agents_dir = Path(agents_dir)

    # OTel span — wraps skill loading for distributed tracing
    _otel_span = None
    try:
        from code_agents.observability.otel import get_tracer
        _otel_tracer = get_tracer()
        _otel_span = _otel_tracer.start_span("get_skill")
        _otel_span.set_attribute("skill.name", skill_name)
        _otel_span.set_attribute("skill.agent", agent_name)
    except Exception:
        _otel_span = None  # OTel is optional

    try:
        # Cross-agent syntax: "other-agent:skill-name"
        if ":" in skill_name:
            target_agent, target_skill = skill_name.split(":", 1)
            return get_skill(agents_dir, target_agent, target_skill)

        folder_name = agent_name.replace("-", "_")
        skills_dir = agents_dir / folder_name / "skills"

        if not skills_dir.is_dir():
            return None

        # Try exact match first
        skill_file = skills_dir / f"{skill_name}.md"
        if skill_file.is_file():
            return _parse_skill_file(skill_file, agent_name)

        # Try with hyphens/underscores
        for md_file in skills_dir.glob("*.md"):
            skill = _parse_skill_file(md_file, agent_name)
            if skill and skill.name == skill_name:
                return skill

        # Fall back to shared skills (agents/_shared/skills/)
        shared_dir = agents_dir / "_shared" / "skills"
        if shared_dir.is_dir():
            shared_file = shared_dir / f"{skill_name}.md"
            if shared_file.is_file():
                return _parse_skill_file(shared_file, "_shared")
            for md_file in shared_dir.glob("*.md"):
                skill = _parse_skill_file(md_file, "_shared")
                if skill and skill.name == skill_name:
                    return skill

        return None
    finally:
        if _otel_span is not None:
            try:
                _otel_span.end()
            except Exception:
                pass


def list_all_skills(agents_dir: str | Path) -> list[Skill]:
    """Flat list of all skills across all agents."""
    all_skills: list[Skill] = []
    for agent_skills in load_agent_skills(agents_dir).values():
        all_skills.extend(agent_skills)
    return all_skills


def format_skills_for_prompt(skills: list[Skill]) -> str:
    """Format agent skills for injection into system prompt."""
    if not skills:
        return ""

    lines = ["Available skills (reusable workflows):"]
    for s in skills:
        desc = f" — {s.description}" if s.description else ""
        lines.append(f"  - {s.name}{desc}")
    return "\n".join(lines)


def generate_skill_index(agents_dir: str | Path, agent_name: str) -> str:
    """Auto-generate skill index from agent's skills/ directory + shared skills."""
    agents_dir = Path(agents_dir)
    folder_name = agent_name.replace("-", "_")
    skills_dir = agents_dir / folder_name / "skills"

    lines: list[str] = []
    if skills_dir.is_dir():
        for md_file in sorted(skills_dir.glob("*.md")):
            skill = _parse_skill_file(md_file, agent_name)
            if skill:
                desc = f" — {skill.description}" if skill.description else ""
                lines.append(f"  - {skill.name}{desc}")

    # Shared skills — compact summary (saves ~200 tokens)
    shared_dir = agents_dir / "_shared" / "skills"
    if shared_dir.is_dir():
        shared_count = sum(1 for f in shared_dir.glob("*.md") if f.is_file())
        if shared_count:
            lines.append("")
            lines.append(
                f"Engineering skills: {shared_count} shared workflows also available "
                f"(architecture, code-review, debug, deploy-checklist, etc). "
                f"Use [SKILL:name] to load any."
            )

    return "\n".join(lines) if lines else ""


def get_all_agents_with_skills(agents_dir: str | Path) -> str:
    """Generate a catalog of ALL agents and their skills for auto-pilot.

    Auto-pilot is the primary agent — it can delegate to any sub-agent.
    This function builds the full catalog so auto-pilot knows what's available.
    """
    agents_dir = Path(agents_dir)
    all_skills = load_agent_skills(agents_dir)
    if not all_skills:
        return ""

    lines = [
        "Available sub-agents and their skills:",
        "Use [DELEGATE:agent-name] to delegate, or POST /v1/agents/{name}/chat/completions",
        "Use [SKILL:agent:skill] to load a specific workflow from any agent.",
        "",
    ]

    for agent_name, skills in sorted(all_skills.items()):
        if agent_name == "_shared":
            continue
        lines.append(f"  {agent_name}:")
        for s in skills:
            desc = f" — {s.description}" if s.description else ""
            lines.append(f"    - {s.name}{desc}")
        lines.append("")

    # Shared skills summary
    shared = all_skills.get("_shared", [])
    if shared:
        lines.append(f"  _shared ({len(shared)} engineering skills): architecture, code-review, debug, deploy-checklist, etc.")

    return "\n".join(lines)


def estimate_prompt_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4
