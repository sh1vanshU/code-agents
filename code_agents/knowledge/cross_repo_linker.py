"""Cross-repo linker — discover cross-repo dependencies and breaking change propagation.

Analyzes imports, package references, and shared interfaces across
repositories to map cross-repo dependency chains and predict breaking
change propagation.
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.knowledge.cross_repo_linker")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}


@dataclass
class RepoLink:
    """A dependency link between repositories."""

    source_repo: str = ""
    target_repo: str = ""
    link_type: str = ""  # package | api | shared_model | config | proto
    details: str = ""
    strength: str = "weak"  # weak | moderate | strong
    files: list[str] = field(default_factory=list)


@dataclass
class BreakingPropagation:
    """Predicted breaking change propagation."""

    origin_repo: str = ""
    origin_change: str = ""
    affected_repos: list[str] = field(default_factory=list)
    propagation_path: list[str] = field(default_factory=list)
    severity: str = "low"  # low | medium | high | critical
    mitigation: str = ""


@dataclass
class SharedInterface:
    """A shared interface between repos."""

    name: str = ""
    interface_type: str = ""  # api_contract | shared_model | event_schema | config_key
    defined_in: str = ""
    consumed_by: list[str] = field(default_factory=list)
    version: str = ""


@dataclass
class CrossRepoResult:
    """Result of cross-repo analysis."""

    repos_analyzed: int = 0
    links: list[RepoLink] = field(default_factory=list)
    shared_interfaces: list[SharedInterface] = field(default_factory=list)
    propagations: list[BreakingPropagation] = field(default_factory=list)
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)
    summary: dict[str, int] = field(default_factory=dict)


class CrossRepoLinker:
    """Discover and analyze cross-repository dependencies."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("CrossRepoLinker initialized for %s", cwd)

    def analyze(
        self,
        repo_paths: list[str] | None = None,
        scan_depth: int = 3,
    ) -> CrossRepoResult:
        """Analyze cross-repo dependencies.

        Args:
            repo_paths: Paths to other repos. Auto-detected from parent dir if None.
            scan_depth: Directory depth to scan.

        Returns:
            CrossRepoResult with links, interfaces, and propagation risks.
        """
        result = CrossRepoResult()

        repos = repo_paths or self._detect_sibling_repos()
        repos = [self.cwd] + [r for r in repos if r != self.cwd]
        result.repos_analyzed = len(repos)
        logger.info("Analyzing %d repositories", len(repos))

        # Extract package names and shared interfaces per repo
        repo_packages: dict[str, set[str]] = {}
        repo_interfaces: dict[str, list[SharedInterface]] = {}
        repo_imports: dict[str, set[str]] = {}

        for repo in repos:
            repo_name = os.path.basename(repo)
            repo_packages[repo_name] = self._extract_packages(repo)
            repo_interfaces[repo_name] = self._extract_interfaces(repo)
            repo_imports[repo_name] = self._extract_external_imports(repo)

        # Find links between repos
        for src_repo, imports in repo_imports.items():
            for tgt_repo, packages in repo_packages.items():
                if src_repo == tgt_repo:
                    continue
                overlap = imports & packages
                if overlap:
                    result.links.append(RepoLink(
                        source_repo=src_repo,
                        target_repo=tgt_repo,
                        link_type="package",
                        details=f"Imports: {', '.join(list(overlap)[:5])}",
                        strength="strong" if len(overlap) > 3 else "moderate",
                    ))

        # Find shared interfaces
        all_interfaces: list[SharedInterface] = []
        for repo_name, interfaces in repo_interfaces.items():
            for iface in interfaces:
                iface.defined_in = repo_name
                # Check if consumed by other repos
                for other_repo, other_imports in repo_imports.items():
                    if other_repo != repo_name and iface.name in other_imports:
                        iface.consumed_by.append(other_repo)
                if iface.consumed_by:
                    all_interfaces.append(iface)

        result.shared_interfaces = all_interfaces

        # Build dependency graph
        for link in result.links:
            result.dependency_graph.setdefault(link.source_repo, []).append(link.target_repo)

        # Predict breaking change propagation
        for link in result.links:
            if link.strength == "strong":
                prop = self._predict_propagation(link, result.dependency_graph)
                result.propagations.append(prop)

        result.summary = {
            "repos_analyzed": result.repos_analyzed,
            "total_links": len(result.links),
            "shared_interfaces": len(result.shared_interfaces),
            "propagation_risks": len(result.propagations),
            "strong_links": sum(1 for l in result.links if l.strength == "strong"),
        }
        logger.info("Cross-repo analysis: %d links, %d shared interfaces",
                     len(result.links), len(result.shared_interfaces))
        return result

    def _detect_sibling_repos(self) -> list[str]:
        """Detect sibling repositories in the parent directory."""
        parent = os.path.dirname(self.cwd)
        repos: list[str] = []
        try:
            for entry in os.listdir(parent):
                path = os.path.join(parent, entry)
                if os.path.isdir(path) and os.path.exists(os.path.join(path, ".git")):
                    repos.append(path)
        except OSError:
            pass
        return repos[:10]

    def _extract_packages(self, repo_path: str) -> set[str]:
        """Extract package names defined in a repository."""
        packages: set[str] = set()

        # Python packages
        for entry in os.listdir(repo_path):
            init = os.path.join(repo_path, entry, "__init__.py")
            if os.path.exists(init):
                packages.add(entry)

        # From pyproject.toml
        pyproject = os.path.join(repo_path, "pyproject.toml")
        if os.path.exists(pyproject):
            try:
                content = Path(pyproject).read_text(errors="replace")
                match = re.search(r'name\s*=\s*"([^"]+)"', content)
                if match:
                    packages.add(match.group(1))
                    packages.add(match.group(1).replace("-", "_"))
            except OSError:
                pass

        # From package.json
        pkg_json = os.path.join(repo_path, "package.json")
        if os.path.exists(pkg_json):
            try:
                content = Path(pkg_json).read_text(errors="replace")
                match = re.search(r'"name"\s*:\s*"([^"]+)"', content)
                if match:
                    packages.add(match.group(1))
            except OSError:
                pass

        return packages

    def _extract_interfaces(self, repo_path: str) -> list[SharedInterface]:
        """Extract shared interface definitions."""
        interfaces: list[SharedInterface] = []

        # Look for schema/model files
        for root, dirs, fnames in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            depth = root[len(repo_path):].count(os.sep)
            if depth > 3:
                dirs.clear()
                continue

            for fname in fnames:
                if fname in ("models.py", "schemas.py", "interfaces.py"):
                    fpath = os.path.join(root, fname)
                    try:
                        content = Path(fpath).read_text(errors="replace")
                    except OSError:
                        continue

                    # Extract class names as interfaces
                    for match in re.finditer(r"class\s+(\w+)", content):
                        interfaces.append(SharedInterface(
                            name=match.group(1),
                            interface_type="shared_model",
                        ))

                elif fname.endswith((".proto", ".graphql", ".schema.json")):
                    interfaces.append(SharedInterface(
                        name=fname,
                        interface_type="api_contract",
                    ))

        return interfaces[:50]

    def _extract_external_imports(self, repo_path: str) -> set[str]:
        """Extract external package imports from a repository."""
        imports: set[str] = set()
        internal_packages = self._extract_packages(repo_path)

        for root, dirs, fnames in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            depth = root[len(repo_path):].count(os.sep)
            if depth > 3:
                dirs.clear()
                continue

            for fname in fnames:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    content = Path(fpath).read_text(errors="replace")
                except OSError:
                    continue

                for match in re.finditer(r"^(?:from|import)\s+(\w+)", content, re.MULTILINE):
                    pkg = match.group(1)
                    if pkg not in internal_packages and pkg not in (
                        "os", "sys", "re", "json", "typing", "logging",
                        "pathlib", "datetime", "collections", "dataclasses",
                        "unittest", "pytest", "abc", "enum", "functools",
                        "itertools", "hashlib", "subprocess", "ast",
                    ):
                        imports.add(pkg)

        return imports

    def _predict_propagation(
        self, link: RepoLink, graph: dict[str, list[str]],
    ) -> BreakingPropagation:
        """Predict breaking change propagation from a link."""
        prop = BreakingPropagation(
            origin_repo=link.target_repo,
            origin_change=f"Breaking change in {link.details}",
        )

        # BFS through dependency graph
        visited: set[str] = set()
        queue = [link.source_repo]
        path = [link.target_repo]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            path.append(current)
            prop.affected_repos.append(current)

            for dep in graph.get(current, []):
                if dep not in visited:
                    queue.append(dep)

        prop.propagation_path = path

        # Severity based on breadth
        if len(prop.affected_repos) > 5:
            prop.severity = "critical"
        elif len(prop.affected_repos) > 2:
            prop.severity = "high"
        elif len(prop.affected_repos) > 1:
            prop.severity = "medium"
        else:
            prop.severity = "low"

        prop.mitigation = (
            f"Coordinate release with {', '.join(prop.affected_repos[:3])}"
            if prop.affected_repos else "No downstream impact"
        )

        return prop


def link_cross_repos(
    cwd: str,
    repo_paths: list[str] | None = None,
) -> dict:
    """Convenience function for cross-repo linking.

    Returns:
        Dict with links, shared interfaces, and propagation risks.
    """
    linker = CrossRepoLinker(cwd)
    result = linker.analyze(repo_paths=repo_paths)
    return {
        "links": [
            {"source": l.source_repo, "target": l.target_repo,
             "type": l.link_type, "strength": l.strength, "details": l.details}
            for l in result.links
        ],
        "shared_interfaces": [
            {"name": i.name, "type": i.interface_type,
             "defined_in": i.defined_in, "consumed_by": i.consumed_by}
            for i in result.shared_interfaces
        ],
        "propagation_risks": [
            {"origin": p.origin_repo, "affected": p.affected_repos,
             "severity": p.severity, "mitigation": p.mitigation}
            for p in result.propagations
        ],
        "dependency_graph": result.dependency_graph,
        "summary": result.summary,
    }
