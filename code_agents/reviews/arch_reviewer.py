"""Architecture reviewer — check separation of concerns, DI, lazy loading, coupling.

Analyzes Python codebase structure for architectural quality including
module coupling, dependency injection patterns, and lazy loading adherence.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.reviews.arch_reviewer")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}


@dataclass
class ArchFinding:
    """A single architecture finding."""

    file: str = ""
    line: int = 0
    category: str = ""  # coupling | separation | lazy_loading | di
    severity: str = "warning"
    message: str = ""
    suggestion: str = ""


@dataclass
class ModuleDependency:
    """Dependency between two modules."""

    source: str = ""
    target: str = ""
    import_count: int = 0
    is_circular: bool = False


@dataclass
class ArchReviewResult:
    """Result of architecture review."""

    files_analyzed: int = 0
    findings: list[ArchFinding] = field(default_factory=list)
    dependencies: list[ModuleDependency] = field(default_factory=list)
    coupling_score: float = 0.0  # 0 = perfect decoupling, 100 = spaghetti
    layer_violations: list[dict] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)


# Layer definitions — lower layers should not import higher layers
DEFAULT_LAYERS = {
    "models": 0,
    "utils": 0,
    "core": 1,
    "parsers": 1,
    "services": 2,
    "routers": 3,
    "cli": 4,
    "chat": 4,
    "ui": 4,
}


class ArchReviewer:
    """Review codebase architecture for quality patterns."""

    def __init__(self, cwd: str, package_name: str = "code_agents"):
        self.cwd = cwd
        self.package_name = package_name
        logger.debug("ArchReviewer initialized for %s", cwd)

    def review(
        self,
        layers: dict[str, int] | None = None,
        max_coupling: int = 10,
    ) -> ArchReviewResult:
        """Run architecture review.

        Args:
            layers: Module layer hierarchy. Lower numbers = lower layer.
            max_coupling: Max imports from one module to another before flagging.

        Returns:
            ArchReviewResult with findings, dependencies, scores.
        """
        layer_map = layers or DEFAULT_LAYERS
        result = ArchReviewResult()

        files = self._collect_files()
        result.files_analyzed = len(files)
        logger.info("Reviewing architecture of %d files", len(files))

        # Build dependency graph
        dep_graph: dict[str, set[str]] = defaultdict(set)
        import_map: dict[str, list[tuple[str, int]]] = defaultdict(list)

        for fpath in files:
            try:
                content = Path(fpath).read_text(errors="replace")
            except OSError:
                continue

            rel = os.path.relpath(fpath, self.cwd)
            module = self._path_to_module(rel)

            imports = self._extract_imports(content, rel)
            for imp_module, lineno in imports:
                dep_graph[module].add(imp_module)
                import_map[module].append((imp_module, lineno))

            # Check lazy loading
            result.findings.extend(self._check_lazy_loading(content, rel))

            # Check separation of concerns
            result.findings.extend(self._check_separation(content, rel))

            # Check dependency injection
            result.findings.extend(self._check_di_patterns(content, rel))

        # Analyze coupling
        for src, targets in dep_graph.items():
            for tgt in targets:
                count = sum(1 for m, _ in import_map[src] if m == tgt)
                is_circular = src in dep_graph.get(tgt, set())
                dep = ModuleDependency(
                    source=src, target=tgt,
                    import_count=count, is_circular=is_circular,
                )
                result.dependencies.append(dep)

                if count > max_coupling:
                    result.findings.append(ArchFinding(
                        file=src, category="coupling", severity="warning",
                        message=f"High coupling: {src} imports {count} items from {tgt}",
                        suggestion="Consider consolidating or using a facade",
                    ))

                if is_circular:
                    result.findings.append(ArchFinding(
                        file=src, category="coupling", severity="error",
                        message=f"Circular dependency: {src} <-> {tgt}",
                        suggestion="Break cycle with dependency inversion or lazy imports",
                    ))

        # Check layer violations
        result.layer_violations = self._check_layer_violations(dep_graph, layer_map)
        for violation in result.layer_violations:
            result.findings.append(ArchFinding(
                file=violation["source"], category="separation",
                severity="warning",
                message=f"Layer violation: {violation['source']} (L{violation['source_layer']}) "
                        f"imports {violation['target']} (L{violation['target_layer']})",
                suggestion="Lower layers should not depend on higher layers",
            ))

        # Coupling score
        total_deps = len(result.dependencies)
        circular = sum(1 for d in result.dependencies if d.is_circular)
        if total_deps > 0:
            result.coupling_score = round(
                (circular * 50 + total_deps) / max(result.files_analyzed, 1) * 10, 1,
            )
        result.coupling_score = min(result.coupling_score, 100.0)

        result.summary = {
            "total_findings": len(result.findings),
            "circular_deps": circular,
            "layer_violations": len(result.layer_violations),
            "total_dependencies": total_deps,
            "coupling_score": result.coupling_score,
        }
        logger.info("Architecture review complete: coupling=%.1f", result.coupling_score)
        return result

    def _collect_files(self) -> list[str]:
        """Collect Python files."""
        files: list[str] = []
        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                if fname.endswith(".py"):
                    files.append(os.path.join(root, fname))
        return files

    def _path_to_module(self, rel_path: str) -> str:
        """Convert relative path to module name."""
        parts = rel_path.replace(os.sep, "/").split("/")
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        elif parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        return ".".join(parts)

    def _extract_imports(self, content: str, rel_path: str) -> list[tuple[str, int]]:
        """Extract internal imports from source."""
        imports: list[tuple[str, int]] = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return imports

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(self.package_name):
                        imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith(self.package_name):
                    imports.append((node.module, node.lineno))

        return imports

    def _check_lazy_loading(self, content: str, rel_path: str) -> list[ArchFinding]:
        """Check for heavy top-level imports that should be lazy."""
        findings: list[ArchFinding] = []
        heavy_modules = {
            "torch", "tensorflow", "pandas", "numpy", "scipy",
            "matplotlib", "sklearn", "transformers", "openai",
        }
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            for mod in heavy_modules:
                if mod in stripped and i < 30:  # top-level imports
                    findings.append(ArchFinding(
                        file=rel_path, line=i, category="lazy_loading",
                        severity="warning",
                        message=f"Heavy module '{mod}' imported at top level",
                        suggestion=f"Move 'import {mod}' inside the function that uses it",
                    ))
        return findings

    def _check_separation(self, content: str, rel_path: str) -> list[ArchFinding]:
        """Check separation of concerns."""
        findings: list[ArchFinding] = []
        # Flag files mixing HTTP handling and business logic
        has_route = bool(re.search(r"@(app|router)\.(get|post|put|delete|patch)", content))
        has_db = bool(re.search(r"\b(session\.query|cursor\.execute|\.filter\()", content))

        if has_route and has_db:
            findings.append(ArchFinding(
                file=rel_path, category="separation", severity="warning",
                message="File mixes HTTP routing and database queries",
                suggestion="Extract DB logic to a service/repository layer",
            ))

        # Flag files that are too long
        lines = content.count("\n")
        if lines > 500:
            findings.append(ArchFinding(
                file=rel_path, category="separation", severity="info",
                message=f"File has {lines} lines — consider splitting",
                suggestion="Extract related functions into sub-modules",
            ))

        return findings

    def _check_di_patterns(self, content: str, rel_path: str) -> list[ArchFinding]:
        """Check for dependency injection patterns."""
        findings: list[ArchFinding] = []
        # Flag global mutable state
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        # Global mutable containers
                        if isinstance(node.value, (ast.Dict, ast.List, ast.Set)):
                            name = target.id
                            if not name.isupper() and not name.startswith("_"):
                                findings.append(ArchFinding(
                                    file=rel_path, line=node.lineno,
                                    category="di", severity="info",
                                    message=f"Global mutable '{name}' — "
                                            "prefer passing as parameter",
                                    suggestion="Use dependency injection or module-level constants",
                                ))
        return findings

    def _check_layer_violations(
        self,
        dep_graph: dict[str, set[str]],
        layer_map: dict[str, int],
    ) -> list[dict]:
        """Check for layer boundary violations."""
        violations: list[dict] = []
        for src, targets in dep_graph.items():
            src_layer = self._get_layer(src, layer_map)
            for tgt in targets:
                tgt_layer = self._get_layer(tgt, layer_map)
                if src_layer is not None and tgt_layer is not None:
                    if src_layer < tgt_layer:
                        violations.append({
                            "source": src, "target": tgt,
                            "source_layer": src_layer, "target_layer": tgt_layer,
                        })
        return violations

    def _get_layer(self, module: str, layer_map: dict[str, int]) -> int | None:
        """Get the layer number for a module."""
        parts = module.split(".")
        for part in parts:
            if part in layer_map:
                return layer_map[part]
        return None


def review_architecture(
    cwd: str,
    layers: dict[str, int] | None = None,
    max_coupling: int = 10,
) -> dict:
    """Convenience function to review architecture.

    Returns:
        Dict with findings, dependencies, coupling score.
    """
    reviewer = ArchReviewer(cwd)
    result = reviewer.review(layers=layers, max_coupling=max_coupling)
    return {
        "files_analyzed": result.files_analyzed,
        "coupling_score": result.coupling_score,
        "findings": [
            {"file": f.file, "line": f.line, "category": f.category,
             "severity": f.severity, "message": f.message}
            for f in result.findings
        ],
        "layer_violations": result.layer_violations,
        "summary": result.summary,
    }
