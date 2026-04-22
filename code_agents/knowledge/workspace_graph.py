"""Cross-repo knowledge graph orchestrator — builds on WorkspaceManager.

Builds a KnowledgeGraph per repo in the workspace, finds cross-repo
dependencies (shared package imports), and enables cross-repo queries
and blast radius analysis.

Usage:
    from code_agents.knowledge.workspace_graph import WorkspaceGraph

    wg = WorkspaceGraph(["/path/to/repo-a", "/path/to/repo-b"])
    wg.build_all()
    deps = wg.find_cross_repo_deps()
    results = wg.query_all(["some_function"])
    impact = wg.blast_radius_cross_repo("src/foo.py", "/path/to/repo-a")
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.knowledge.workspace_graph")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CrossRepoDependency:
    """A dependency between two repos discovered via shared import names."""
    source_repo: str
    target_repo: str
    import_path: str
    source_file: str


# ---------------------------------------------------------------------------
# WorkspaceGraph
# ---------------------------------------------------------------------------


class WorkspaceGraph:
    """Cross-repo knowledge graph orchestrator.

    Builds a KnowledgeGraph per repo and provides cross-repo queries,
    dependency detection, and blast radius analysis.
    """

    def __init__(self, repos: list[str]) -> None:
        self.repos = [os.path.abspath(r) for r in repos]
        self._graphs: dict[str, Any] = {}  # repo_path -> KnowledgeGraph
        self._import_maps: dict[str, dict[str, list[str]]] = {}  # repo -> {file: [imports]}

    # -------------------------------------------------------------------
    # Build
    # -------------------------------------------------------------------

    def build_all(self) -> dict[str, Any]:
        """Build a KnowledgeGraph for each repo. Returns {repo: stats}."""
        # Lazy import to avoid heavy load at module level
        from code_agents.knowledge.knowledge_graph import KnowledgeGraph

        stats: dict[str, Any] = {}
        for repo in self.repos:
            if not Path(repo).is_dir():
                logger.warning("Skipping non-existent repo: %s", repo)
                continue

            logger.info("Building knowledge graph for %s", repo)
            kg = KnowledgeGraph(repo)
            kg.build()
            self._graphs[repo] = kg

            # Cache the imports map for cross-repo dep analysis
            self._import_maps[repo] = dict(kg._imports_map)
            stats[repo] = kg.get_stats()
            logger.info(
                "Graph built for %s: %d symbols, %d files",
                Path(repo).name,
                stats[repo].get("symbols", 0),
                stats[repo].get("files", 0),
            )

        return stats

    # -------------------------------------------------------------------
    # Cross-repo dependency detection
    # -------------------------------------------------------------------

    def find_cross_repo_deps(self) -> list[CrossRepoDependency]:
        """Scan import maps across repos, find shared package names.

        For each repo, look at its imports and check if any match a
        top-level package name defined in another repo.
        """
        # Build a map of package names -> repo that defines them
        package_to_repo: dict[str, str] = {}
        for repo in self.repos:
            repo_name = Path(repo).name
            # Top-level directories with __init__.py are packages
            for entry in Path(repo).iterdir():
                if entry.is_dir() and (entry / "__init__.py").exists():
                    package_to_repo[entry.name] = repo
            # Also check for top-level .py files as module names
            for entry in Path(repo).iterdir():
                if entry.is_file() and entry.suffix == ".py" and entry.stem != "__init__":
                    mod_name = entry.stem
                    if mod_name not in package_to_repo:
                        package_to_repo[mod_name] = repo

        deps: list[CrossRepoDependency] = []
        seen: set[tuple[str, str, str]] = set()

        for source_repo, import_map in self._import_maps.items():
            for source_file, imports in import_map.items():
                for imp in imports:
                    # Get the top-level package name from the import
                    top_package = imp.split(".")[0]
                    target_repo = package_to_repo.get(top_package)

                    if target_repo and target_repo != source_repo:
                        key = (source_repo, target_repo, imp)
                        if key not in seen:
                            seen.add(key)
                            deps.append(CrossRepoDependency(
                                source_repo=source_repo,
                                target_repo=target_repo,
                                import_path=imp,
                                source_file=source_file,
                            ))

        logger.info("Found %d cross-repo dependencies", len(deps))
        return deps

    # -------------------------------------------------------------------
    # Cross-repo query
    # -------------------------------------------------------------------

    def query_all(self, keywords: list[str], max_results: int = 30) -> list[dict]:
        """Query across all repo graphs, annotate results with repo name."""
        all_results: list[dict] = []

        for repo, kg in self._graphs.items():
            repo_name = Path(repo).name
            results = kg.query(keywords, max_results=max_results)
            for r in results:
                r["repo"] = repo_name
                r["repo_path"] = repo
                all_results.append(r)

        # Sort by score descending
        all_results.sort(key=lambda x: x.get("_score", 0), reverse=True)
        return all_results[:max_results]

    # -------------------------------------------------------------------
    # Cross-repo blast radius
    # -------------------------------------------------------------------

    def blast_radius_cross_repo(
        self, file_path: str, source_repo: str
    ) -> dict[str, list[str]]:
        """Find files affected by a change, including across repos.

        Returns {repo_path: [affected_files]}.
        """
        source_repo = os.path.abspath(source_repo)
        result: dict[str, list[str]] = {}

        # 1. In-repo blast radius
        if source_repo in self._graphs:
            kg = self._graphs[source_repo]
            affected = kg.blast_radius(file_path)
            if affected:
                result[source_repo] = affected

        # 2. Cross-repo: find which repos depend on symbols from the changed file
        rel_path = os.path.relpath(file_path, source_repo) if os.path.isabs(file_path) else file_path

        # Get the module name(s) for the changed file
        module_names: set[str] = set()
        mod = rel_path.replace(os.sep, ".").replace("/", ".")
        if mod.endswith(".py"):
            mod = mod[:-3]
        module_names.add(mod)
        # Also add the last component (e.g. "backend" from "code_agents.core.backend")
        parts = mod.split(".")
        if parts:
            module_names.add(parts[-1])
        # Add the top-level package
        if len(parts) > 1:
            module_names.add(parts[0])

        # Check other repos for imports matching these module names
        for other_repo, import_map in self._import_maps.items():
            if other_repo == source_repo:
                continue
            affected_files: list[str] = []
            for other_file, imports in import_map.items():
                for imp in imports:
                    imp_top = imp.split(".")[0]
                    if imp in module_names or imp_top in module_names:
                        affected_files.append(other_file)
                        break
            if affected_files:
                result[other_repo] = sorted(affected_files)

        return result
