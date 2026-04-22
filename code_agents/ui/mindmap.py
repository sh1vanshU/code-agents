"""Repo Mindmap Generator — build a visual mindmap of any repository.

Reuses KnowledgeGraph (symbols, edges), DependencyGraph (import relationships),
and scan_project (language, framework detection) to create structured mindmaps
in terminal (ANSI), Mermaid, or interactive HTML (D3.js) formats.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.ui.mindmap")

# Directories to skip when walking the repo
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    "target", "vendor", ".idea", ".vscode", ".next", "coverage",
    ".code-agents", ".eggs", "*.egg-info",
}

# Known entry-point file names
_ENTRY_POINT_FILES = {
    "main.py", "app.py", "manage.py", "server.py", "wsgi.py", "asgi.py",
    "index.js", "index.ts", "server.js", "server.ts", "app.js", "app.ts",
    "main.go", "main.rs", "Main.java", "Application.java",
    "cli.py", "__main__.py",
}

# Known integration keywords (mapped from project scanner detections)
_INTEGRATION_KEYWORDS = {
    "jenkins": "Jenkins CI",
    "argocd": "ArgoCD",
    "jira": "Jira",
    "kibana": "Kibana",
    "kubernetes": "Kubernetes",
    "docker": "Docker",
    "kafka": "Kafka",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "grafana": "Grafana",
    "slack": "Slack",
    "grpc": "gRPC",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MindmapNode:
    """A node in the mindmap tree."""

    name: str
    kind: str  # "directory", "module", "class", "function", "agent", "entrypoint", "integration"
    children: list["MindmapNode"] = field(default_factory=list)
    file: str = ""
    metadata: dict = field(default_factory=dict)

    def add_child(self, child: "MindmapNode") -> "MindmapNode":
        """Add a child node and return it."""
        self.children.append(child)
        return child

    def child_count(self) -> int:
        """Total number of descendants."""
        return len(self.children) + sum(c.child_count() for c in self.children)


@dataclass
class MindmapResult:
    """Result of a mindmap build."""

    root: MindmapNode
    entry_points: list[MindmapNode] = field(default_factory=list)
    agents: list[MindmapNode] = field(default_factory=list)
    integrations: list[MindmapNode] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# RepoMindmap builder
# ---------------------------------------------------------------------------

class RepoMindmap:
    """Build a mindmap for a repository."""

    def __init__(self, repo_path: str, depth: int = 3, focus: str | None = None):
        resolved = Path(repo_path).resolve()
        if not resolved.is_dir():
            raise ValueError(f"Not a valid directory: {repo_path}")
        self.repo_path = str(resolved)
        self.depth = max(1, min(depth, 10))
        self.focus = focus
        self._kg = None
        self._project_info = None

    def build(self) -> MindmapResult:
        """Build the full mindmap."""
        logger.info("Building mindmap for %s (depth=%d, focus=%s)", self.repo_path, self.depth, self.focus)

        root = self._build_directory_tree()
        entry_points = self._identify_entry_points()
        agents = self._identify_agents()
        integrations = self._identify_integrations()

        # Gather stats
        dir_count = self._count_nodes(root, "directory")
        mod_count = self._count_nodes(root, "module")

        stats = {
            "repo_path": self.repo_path,
            "repo_name": Path(self.repo_path).name,
            "depth": self.depth,
            "directories": dir_count,
            "modules": mod_count,
            "entry_points": len(entry_points),
            "agents": len(agents),
            "integrations": len(integrations),
        }

        # Enrich with project scanner info
        try:
            from code_agents.analysis.project_scanner import scan_project
            info = scan_project(self.repo_path)
            self._project_info = info
            stats["language"] = info.language or "unknown"
            stats["framework"] = info.framework or "unknown"
            stats["build_tool"] = info.build_tool or "unknown"
        except Exception as exc:
            logger.debug("Project scanner unavailable: %s", exc)
            stats["language"] = "unknown"
            stats["framework"] = "unknown"
            stats["build_tool"] = "unknown"

        result = MindmapResult(
            root=root,
            entry_points=entry_points,
            agents=agents,
            integrations=integrations,
            stats=stats,
        )

        logger.info(
            "Mindmap built: %d dirs, %d modules, %d entry points, %d agents, %d integrations",
            dir_count, mod_count, len(entry_points), len(agents), len(integrations),
        )
        return result

    # -- Private builders --------------------------------------------------

    def _build_directory_tree(self) -> MindmapNode:
        """Walk repo dirs and build a tree of MindmapNodes."""
        repo = Path(self.repo_path)
        root_node = MindmapNode(
            name=repo.name,
            kind="directory",
            file=str(repo),
        )

        if self.focus:
            focus_path = (repo / self.focus).resolve()
            # Validate no path traversal
            if not str(focus_path).startswith(str(repo)):
                raise ValueError(f"Focus path escapes repo: {self.focus}")
            if focus_path.is_dir():
                self._walk_dir(focus_path, root_node, current_depth=1)
            elif focus_path.is_file():
                root_node.add_child(MindmapNode(
                    name=focus_path.name,
                    kind="module",
                    file=str(focus_path),
                ))
            return root_node

        self._walk_dir(repo, root_node, current_depth=1)
        return root_node

    def _walk_dir(self, dir_path: Path, parent: MindmapNode, current_depth: int) -> None:
        """Recursively walk a directory up to self.depth."""
        if current_depth > self.depth:
            return

        try:
            entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            if entry.name.startswith(".") and entry.name in _SKIP_DIRS:
                continue
            if entry.name in _SKIP_DIRS:
                continue
            if entry.name.endswith(".egg-info"):
                continue

            resolved = entry.resolve()
            # Security: ensure we stay within repo
            if not str(resolved).startswith(self.repo_path):
                continue

            if entry.is_dir():
                child = parent.add_child(MindmapNode(
                    name=entry.name,
                    kind="directory",
                    file=str(entry),
                ))
                self._walk_dir(entry, child, current_depth + 1)
            elif entry.is_file() and self._is_source_file(entry):
                parent.add_child(MindmapNode(
                    name=entry.name,
                    kind="module",
                    file=str(entry),
                ))

    def _identify_entry_points(self) -> list[MindmapNode]:
        """Find entry-point files (main.py, app.py, CLI entry, etc.)."""
        repo = Path(self.repo_path)
        entry_points: list[MindmapNode] = []

        for root, dirs, files in os.walk(repo):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fname in files:
                if fname in _ENTRY_POINT_FILES:
                    fpath = Path(root) / fname
                    rel = str(fpath.relative_to(repo))
                    entry_points.append(MindmapNode(
                        name=rel,
                        kind="entrypoint",
                        file=str(fpath),
                        metadata={"filename": fname},
                    ))

        # Also check pyproject.toml for [tool.poetry.scripts]
        pyproject = repo / "pyproject.toml"
        if pyproject.is_file():
            try:
                text = pyproject.read_text(encoding="utf-8")
                if "[tool.poetry.scripts]" in text:
                    entry_points.append(MindmapNode(
                        name="pyproject.toml [scripts]",
                        kind="entrypoint",
                        file=str(pyproject),
                        metadata={"type": "poetry-scripts"},
                    ))
            except Exception:
                pass

        # Check package.json for bin/main
        pkg_json = repo / "package.json"
        if pkg_json.is_file():
            try:
                import json
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
                if "bin" in data or "main" in data:
                    entry_points.append(MindmapNode(
                        name="package.json [bin/main]",
                        kind="entrypoint",
                        file=str(pkg_json),
                        metadata={"type": "npm-entry"},
                    ))
            except Exception:
                pass

        return entry_points

    def _identify_agents(self) -> list[MindmapNode]:
        """Detect agents from agents/ directory."""
        agents_dir = Path(self.repo_path) / "agents"
        agents: list[MindmapNode] = []

        if not agents_dir.is_dir():
            return agents

        for entry in sorted(agents_dir.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                yaml_file = entry / f"{entry.name}.yaml"
                skills_dir = entry / "skills"
                skill_count = 0
                if skills_dir.is_dir():
                    skill_count = sum(1 for f in skills_dir.iterdir() if f.suffix == ".md")

                node = MindmapNode(
                    name=entry.name,
                    kind="agent",
                    file=str(yaml_file) if yaml_file.is_file() else str(entry),
                    metadata={
                        "has_yaml": yaml_file.is_file(),
                        "skill_count": skill_count,
                    },
                )
                # Add skills as children
                if skills_dir.is_dir():
                    for skill_file in sorted(skills_dir.iterdir()):
                        if skill_file.suffix == ".md":
                            node.add_child(MindmapNode(
                                name=skill_file.stem,
                                kind="function",
                                file=str(skill_file),
                            ))
                agents.append(node)

        return agents

    def _identify_integrations(self) -> list[MindmapNode]:
        """Identify integrations from project info and known patterns."""
        integrations: list[MindmapNode] = []

        # Check from project scanner
        if self._project_info:
            info = self._project_info
            if info.has_docker:
                integrations.append(MindmapNode(name="Docker", kind="integration"))
            if info.kafka_count > 0:
                integrations.append(MindmapNode(name="Kafka", kind="integration",
                                                metadata={"count": info.kafka_count}))
            if info.grpc_count > 0:
                integrations.append(MindmapNode(name="gRPC", kind="integration",
                                                metadata={"count": info.grpc_count}))
            for det in info.detected:
                det_lower = det.lower()
                for keyword, label in _INTEGRATION_KEYWORDS.items():
                    if keyword in det_lower and not any(i.name == label for i in integrations):
                        integrations.append(MindmapNode(name=label, kind="integration"))

        # Also scan for known config files
        repo = Path(self.repo_path)
        _config_files = {
            "Jenkinsfile": "Jenkins CI",
            "Dockerfile": "Docker",
            "docker-compose.yml": "Docker Compose",
            "docker-compose.yaml": "Docker Compose",
            ".github/workflows": "GitHub Actions",
            "kubernetes": "Kubernetes",
            "k8s": "Kubernetes",
            "terraform": "Terraform",
        }
        for fname, label in _config_files.items():
            if (repo / fname).exists() and not any(i.name == label for i in integrations):
                integrations.append(MindmapNode(name=label, kind="integration"))

        return integrations

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _is_source_file(path: Path) -> bool:
        """Check if a file is a source code file worth showing."""
        _exts = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
            ".rb", ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt",
            ".scala", ".php", ".yaml", ".yml", ".toml", ".json", ".md",
            ".sh", ".bash", ".sql", ".graphql", ".proto",
        }
        return path.suffix.lower() in _exts

    @staticmethod
    def _count_nodes(node: MindmapNode, kind: str) -> int:
        """Count nodes of a specific kind in the tree."""
        count = 1 if node.kind == kind else 0
        for child in node.children:
            count += RepoMindmap._count_nodes(child, kind)
        return count


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

# ANSI color codes
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_BLUE = "\033[34m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_MAGENTA = "\033[35m"
_RED = "\033[31m"
_WHITE = "\033[37m"

_KIND_COLORS = {
    "directory": _BLUE + _BOLD,
    "module": _GREEN,
    "class": _YELLOW,
    "function": _CYAN,
    "agent": _MAGENTA + _BOLD,
    "entrypoint": _RED + _BOLD,
    "integration": _YELLOW + _BOLD,
}

_KIND_ICONS = {
    "directory": "📁",
    "module": "📄",
    "class": "🔷",
    "function": "⚡",
    "agent": "🤖",
    "entrypoint": "🚀",
    "integration": "🔌",
}


def format_terminal(result: MindmapResult, depth: int = 3) -> str:
    """Format mindmap as colored ASCII tree with ANSI escape codes."""
    lines: list[str] = []

    # Header
    stats = result.stats
    repo_name = stats.get("repo_name", "repo")
    lines.append(f"{_BOLD}{_CYAN}╔══ Repo Mindmap: {repo_name} ══╗{_RESET}")
    lines.append(f"{_DIM}  Language: {stats.get('language', '?')} | Framework: {stats.get('framework', '?')} | Build: {stats.get('build_tool', '?')}{_RESET}")
    lines.append("")

    # Directory tree
    lines.append(f"{_BOLD}Directory Structure{_RESET}")
    _format_tree_node(result.root, lines, "", True, depth, 0)
    lines.append("")

    # Entry points
    if result.entry_points:
        lines.append(f"{_BOLD}Entry Points{_RESET}")
        for ep in result.entry_points:
            color = _KIND_COLORS.get(ep.kind, "")
            icon = _KIND_ICONS.get(ep.kind, "")
            lines.append(f"  {icon} {color}{ep.name}{_RESET}")
        lines.append("")

    # Agents
    if result.agents:
        lines.append(f"{_BOLD}Agents ({len(result.agents)}){_RESET}")
        for agent in result.agents:
            color = _KIND_COLORS.get(agent.kind, "")
            icon = _KIND_ICONS.get(agent.kind, "")
            skill_count = agent.metadata.get("skill_count", 0)
            suffix = f" ({skill_count} skills)" if skill_count else ""
            lines.append(f"  {icon} {color}{agent.name}{_RESET}{_DIM}{suffix}{_RESET}")
        lines.append("")

    # Integrations
    if result.integrations:
        lines.append(f"{_BOLD}Integrations ({len(result.integrations)}){_RESET}")
        for integ in result.integrations:
            color = _KIND_COLORS.get(integ.kind, "")
            icon = _KIND_ICONS.get(integ.kind, "")
            lines.append(f"  {icon} {color}{integ.name}{_RESET}")
        lines.append("")

    # Footer stats
    lines.append(f"{_DIM}─── {stats.get('directories', 0)} dirs | {stats.get('modules', 0)} modules | {stats.get('entry_points', 0)} entry points | {stats.get('agents', 0)} agents | {stats.get('integrations', 0)} integrations ───{_RESET}")

    return "\n".join(lines)


def _format_tree_node(
    node: MindmapNode,
    lines: list[str],
    prefix: str,
    is_last: bool,
    max_depth: int,
    current_depth: int,
) -> None:
    """Recursively format a tree node with box-drawing characters."""
    if current_depth > max_depth:
        return

    connector = "└── " if is_last else "├── "
    color = _KIND_COLORS.get(node.kind, "")
    icon = _KIND_ICONS.get(node.kind, "")

    if current_depth == 0:
        lines.append(f"  {icon} {color}{node.name}{_RESET}")
    else:
        lines.append(f"  {prefix}{connector}{icon} {color}{node.name}{_RESET}")

    # Children
    child_prefix = prefix + ("    " if is_last else "│   ")
    visible_children = node.children
    if len(visible_children) > 20:
        visible_children = visible_children[:18]
        truncated = len(node.children) - 18
    else:
        truncated = 0

    for i, child in enumerate(visible_children):
        is_child_last = (i == len(visible_children) - 1) and truncated == 0
        _format_tree_node(child, lines, child_prefix, is_child_last, max_depth, current_depth + 1)

    if truncated > 0:
        lines.append(f"  {child_prefix}└── {_DIM}... and {truncated} more{_RESET}")


def format_mermaid(result: MindmapResult) -> str:
    """Format mindmap as Mermaid mindmap syntax."""
    lines: list[str] = []
    lines.append("mindmap")

    repo_name = result.stats.get("repo_name", "repo")
    lines.append(f"  root(({repo_name}))")

    # Directory structure (condensed)
    if result.root.children:
        lines.append("    Structure")
        for child in result.root.children[:15]:
            _safe = _mermaid_safe(child.name)
            if child.kind == "directory":
                lines.append(f"      {_safe}")
                for grandchild in child.children[:8]:
                    lines.append(f"        {_mermaid_safe(grandchild.name)}")
                if len(child.children) > 8:
                    lines.append(f"        ...{len(child.children) - 8} more")
            else:
                lines.append(f"      {_safe}")

    # Entry points
    if result.entry_points:
        lines.append("    Entry Points")
        for ep in result.entry_points:
            lines.append(f"      {_mermaid_safe(ep.name)}")

    # Agents
    if result.agents:
        lines.append("    Agents")
        for agent in result.agents:
            skill_count = agent.metadata.get("skill_count", 0)
            label = f"{agent.name} ({skill_count} skills)" if skill_count else agent.name
            lines.append(f"      {_mermaid_safe(label)}")

    # Integrations
    if result.integrations:
        lines.append("    Integrations")
        for integ in result.integrations:
            lines.append(f"      {_mermaid_safe(integ.name)}")

    return "\n".join(lines)


def _mermaid_safe(text: str) -> str:
    """Escape text for Mermaid syntax — remove special chars."""
    # Mermaid doesn't like parens, brackets, etc. in bare text
    for ch in "()[]{}#<>":
        text = text.replace(ch, "")
    return text.strip()


def format_html(result: MindmapResult) -> str:
    """Format mindmap as standalone HTML with D3.js CDN for interactive graph."""
    import json

    def _node_to_d3(node: MindmapNode, max_depth: int = 4, depth: int = 0) -> dict:
        """Convert MindmapNode tree to D3 hierarchy format."""
        d3_node: dict = {
            "name": node.name,
            "kind": node.kind,
        }
        if node.children and depth < max_depth:
            d3_node["children"] = [
                _node_to_d3(child, max_depth, depth + 1)
                for child in node.children[:30]
            ]
        return d3_node

    # Build combined tree
    combined = {
        "name": result.stats.get("repo_name", "repo"),
        "kind": "directory",
        "children": [],
    }

    # Structure
    if result.root.children:
        structure_node = {"name": "Structure", "kind": "directory", "children": [
            _node_to_d3(c) for c in result.root.children[:20]
        ]}
        combined["children"].append(structure_node)

    # Entry points
    if result.entry_points:
        combined["children"].append({
            "name": "Entry Points",
            "kind": "entrypoint",
            "children": [{"name": ep.name, "kind": "entrypoint"} for ep in result.entry_points],
        })

    # Agents
    if result.agents:
        combined["children"].append({
            "name": f"Agents ({len(result.agents)})",
            "kind": "agent",
            "children": [{"name": a.name, "kind": "agent"} for a in result.agents],
        })

    # Integrations
    if result.integrations:
        combined["children"].append({
            "name": "Integrations",
            "kind": "integration",
            "children": [{"name": i.name, "kind": "integration"} for i in result.integrations],
        })

    tree_json = json.dumps(combined, indent=2)
    stats = result.stats

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Repo Mindmap: {stats.get('repo_name', 'repo')}</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0;
    background: #1a1a2e;
    color: #e0e0e0;
    overflow: hidden;
  }}
  #header {{
    padding: 16px 24px;
    background: #16213e;
    border-bottom: 1px solid #0f3460;
  }}
  #header h1 {{ margin: 0; font-size: 20px; color: #53d8fb; }}
  #header .stats {{ font-size: 13px; color: #8e8e8e; margin-top: 4px; }}
  #chart {{ width: 100vw; height: calc(100vh - 70px); }}
  .node circle {{
    stroke-width: 2px;
    cursor: pointer;
  }}
  .node text {{
    font-size: 12px;
    fill: #e0e0e0;
  }}
  .link {{
    fill: none;
    stroke: #3a3a5c;
    stroke-width: 1.5px;
  }}
</style>
</head>
<body>
<div id="header">
  <h1>Repo Mindmap: {stats.get('repo_name', 'repo')}</h1>
  <div class="stats">
    {stats.get('language', '?')} | {stats.get('framework', '?')} |
    {stats.get('directories', 0)} dirs | {stats.get('modules', 0)} modules |
    {stats.get('agents', 0)} agents | {stats.get('integrations', 0)} integrations
  </div>
</div>
<div id="chart"></div>
<script>
const data = {tree_json};

const kindColors = {{
  directory: '#4fc3f7',
  module: '#81c784',
  'class': '#ffd54f',
  'function': '#4dd0e1',
  agent: '#ce93d8',
  entrypoint: '#ef5350',
  integration: '#ffb74d',
}};

const width = window.innerWidth;
const height = window.innerHeight - 70;
const svg = d3.select('#chart').append('svg')
  .attr('width', width)
  .attr('height', height);

const g = svg.append('g');

// Zoom
svg.call(d3.zoom().scaleExtent([0.2, 4]).on('zoom', (e) => {{
  g.attr('transform', e.transform);
}}));

const root = d3.hierarchy(data);
const treeLayout = d3.tree().size([height - 40, width - 300]);
treeLayout(root);

// Center
g.attr('transform', `translate(120, 20)`);

// Links
g.selectAll('.link')
  .data(root.links())
  .join('path')
  .attr('class', 'link')
  .attr('d', d3.linkHorizontal().x(d => d.y).y(d => d.x));

// Nodes
const node = g.selectAll('.node')
  .data(root.descendants())
  .join('g')
  .attr('class', 'node')
  .attr('transform', d => `translate(${{d.y}},${{d.x}})`);

node.append('circle')
  .attr('r', d => d.children ? 6 : 4)
  .attr('fill', d => kindColors[d.data.kind] || '#999')
  .attr('stroke', d => d3.color(kindColors[d.data.kind] || '#999').darker(0.5));

node.append('text')
  .attr('dx', d => d.children ? -10 : 10)
  .attr('dy', 4)
  .attr('text-anchor', d => d.children ? 'end' : 'start')
  .text(d => d.data.name);

// Tooltip on hover
node.append('title')
  .text(d => `${{d.data.name}} (${{d.data.kind}})`);
</script>
</body>
</html>"""

    return html
