"""Import Optimizer — detect and fix import issues in Python/JS/TS codebases.

Finds: unused imports, circular dependencies, heavy top-level imports,
wildcard imports, duplicate imports, and shadowed imports.
"""

from __future__ import annotations

import ast
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.import_optimizer")

# Heavy modules that should be lazy-loaded in non-data files
HEAVY_MODULES = frozenset({
    "tensorflow", "torch", "pandas", "numpy", "scipy", "matplotlib",
    "sklearn", "keras", "transformers", "xgboost", "lightgbm",
    "plotly", "seaborn", "cv2", "PIL", "dask", "pyspark",
})

# File extensions we scan
PYTHON_EXTS = {".py"}
JS_TS_EXTS = {".js", ".ts", ".jsx", ".tsx", ".mjs"}


@dataclass
class ImportFinding:
    """A single import issue found in a file."""

    file: str
    line: int
    import_statement: str
    issue: str  # "unused", "circular", "heavy", "wildcard", "duplicate", "shadowed"
    severity: str  # "error", "warning", "info"
    suggestion: str


@dataclass
class _ImportInfo:
    """Internal representation of an import statement."""

    module: str
    names: list[str]  # imported names (empty for `import x`)
    alias: Optional[str] = None
    line: int = 0
    raw: str = ""
    is_from: bool = False
    is_wildcard: bool = False


class ImportOptimizer:
    """Scan and fix import issues across a codebase."""

    def __init__(self, cwd: str):
        self.cwd = os.path.abspath(cwd)
        logger.debug("ImportOptimizer initialized for %s", self.cwd)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, target: str = "") -> list[ImportFinding]:
        """Scan for all import issues. target can be a file or directory."""
        findings: list[ImportFinding] = []
        paths = self._resolve_paths(target)

        for path in paths:
            ext = Path(path).suffix
            if ext in PYTHON_EXTS:
                findings.extend(self._find_unused(path))
                findings.extend(self._find_heavy(path))
                findings.extend(self._find_wildcard(path))
                findings.extend(self._find_duplicate(path))
                findings.extend(self._find_shadowed(path))

        # Circular dependency detection is project-wide
        findings.extend(self._find_circular())

        # Sort by file then line
        findings.sort(key=lambda f: (f.file, f.line))
        logger.info("Scan complete: %d findings", len(findings))
        return findings

    def fix(self, target: str = "") -> int:
        """Auto-fix what we can (unused imports). Returns count of fixes."""
        paths = self._resolve_paths(target)
        total_fixed = 0
        for path in paths:
            ext = Path(path).suffix
            if ext in PYTHON_EXTS:
                unused = self._find_unused(path)
                if unused:
                    total_fixed += self._auto_fix_unused(path, unused)
        logger.info("Auto-fixed %d import(s)", total_fixed)
        return total_fixed

    # ------------------------------------------------------------------
    # Detectors
    # ------------------------------------------------------------------

    def _find_unused(self, path: str) -> list[ImportFinding]:
        """Parse imports via AST, grep file body for usage of each imported name."""
        findings: list[ImportFinding] = []
        try:
            source = Path(path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=path)
        except (SyntaxError, UnicodeDecodeError) as exc:
            logger.debug("Cannot parse %s: %s", path, exc)
            return findings

        lines = source.splitlines()
        imports = self._extract_python_imports(tree, lines)

        # Build body text excluding import lines for usage search
        import_lines = {imp.line for imp in imports}
        body_lines = [
            line for i, line in enumerate(lines, 1)
            if i not in import_lines
        ]
        body_text = "\n".join(body_lines)

        rel_path = self._rel(path)

        for imp in imports:
            if imp.is_wildcard:
                continue  # handled by _find_wildcard

            names_to_check = []
            if imp.alias:
                names_to_check.append(imp.alias)
            elif imp.names:
                names_to_check.extend(imp.names)
            else:
                # `import foo` -> check for `foo.`
                names_to_check.append(imp.module.split(".")[-1])

            for name in names_to_check:
                # Check if name appears in body as a word boundary
                pattern = r"\b" + re.escape(name) + r"\b"
                if not re.search(pattern, body_text):
                    findings.append(ImportFinding(
                        file=rel_path,
                        line=imp.line,
                        import_statement=imp.raw.strip(),
                        issue="unused",
                        severity="warning",
                        suggestion=f"Remove unused import: {name}",
                    ))

        return findings

    def _find_circular(self) -> list[ImportFinding]:
        """Build import graph, DFS for cycles: A -> B -> C -> A."""
        findings: list[ImportFinding] = []
        graph: dict[str, set[str]] = {}

        py_files = self._resolve_paths("")
        module_map: dict[str, str] = {}  # module dotted name -> file path

        for path in py_files:
            ext = Path(path).suffix
            if ext not in PYTHON_EXTS:
                continue

            mod_name = self._path_to_module(path)
            if not mod_name:
                continue
            module_map[mod_name] = path

            try:
                source = Path(path).read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=path)
            except (SyntaxError, UnicodeDecodeError):
                continue

            deps: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        deps.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        deps.add(node.module.split(".")[0])

            graph[mod_name] = deps

        # DFS for cycles
        visited: set[str] = set()
        rec_stack: set[str] = set()
        cycles_found: set[tuple[str, ...]] = set()

        def _dfs(node: str, path_stack: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path_stack.append(node)

            for neighbor in graph.get(node, set()):
                if neighbor not in graph:
                    continue
                if neighbor not in visited:
                    _dfs(neighbor, path_stack)
                elif neighbor in rec_stack:
                    # Found cycle
                    idx = path_stack.index(neighbor)
                    cycle = tuple(path_stack[idx:])
                    normalized = tuple(sorted(cycle))
                    if normalized not in cycles_found:
                        cycles_found.add(normalized)

            path_stack.pop()
            rec_stack.discard(node)

        for mod in graph:
            if mod not in visited:
                _dfs(mod, [])

        for cycle in cycles_found:
            cycle_str = " -> ".join(cycle) + " -> " + cycle[0]
            first_mod = cycle[0]
            fpath = module_map.get(first_mod, first_mod)
            findings.append(ImportFinding(
                file=self._rel(fpath),
                line=1,
                import_statement=cycle_str,
                issue="circular",
                severity="error",
                suggestion=f"Break circular dependency: {cycle_str}",
            ))

        return findings

    def _find_heavy(self, path: str) -> list[ImportFinding]:
        """Top-level imports of heavy modules that should be lazy."""
        findings: list[ImportFinding] = []
        try:
            source = Path(path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=path)
        except (SyntaxError, UnicodeDecodeError):
            return findings

        rel_path = self._rel(path)
        lines = source.splitlines()

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_root = alias.name.split(".")[0]
                    if mod_root in HEAVY_MODULES:
                        raw = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                        findings.append(ImportFinding(
                            file=rel_path,
                            line=node.lineno,
                            import_statement=raw.strip(),
                            issue="heavy",
                            severity="info",
                            suggestion=f"Move '{alias.name}' inside function for lazy loading",
                        ))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod_root = node.module.split(".")[0]
                    if mod_root in HEAVY_MODULES:
                        raw = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                        findings.append(ImportFinding(
                            file=rel_path,
                            line=node.lineno,
                            import_statement=raw.strip(),
                            issue="heavy",
                            severity="info",
                            suggestion=f"Move '{node.module}' import inside function for lazy loading",
                        ))

        return findings

    def _find_wildcard(self, path: str) -> list[ImportFinding]:
        """from x import * -> list specific imports."""
        findings: list[ImportFinding] = []
        try:
            source = Path(path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=path)
        except (SyntaxError, UnicodeDecodeError):
            return findings

        rel_path = self._rel(path)
        lines = source.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.names:
                for alias in node.names:
                    if alias.name == "*":
                        raw = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                        findings.append(ImportFinding(
                            file=rel_path,
                            line=node.lineno,
                            import_statement=raw.strip(),
                            issue="wildcard",
                            severity="warning",
                            suggestion=f"Replace 'from {node.module} import *' with explicit imports",
                        ))

        return findings

    def _find_duplicate(self, path: str) -> list[ImportFinding]:
        """Same module imported twice, or import x and from x import y."""
        findings: list[ImportFinding] = []
        try:
            source = Path(path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=path)
        except (SyntaxError, UnicodeDecodeError):
            return findings

        rel_path = self._rel(path)
        lines = source.splitlines()

        seen_modules: dict[str, int] = {}  # module -> first line
        seen_names: dict[str, int] = {}  # imported name -> first line

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                raw = lines[node.lineno - 1] if node.lineno <= len(lines) else ""

                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod = alias.name
                        name = alias.asname or alias.name.split(".")[-1]
                        if mod in seen_modules:
                            findings.append(ImportFinding(
                                file=rel_path,
                                line=node.lineno,
                                import_statement=raw.strip(),
                                issue="duplicate",
                                severity="warning",
                                suggestion=f"'{mod}' already imported at line {seen_modules[mod]}",
                            ))
                        else:
                            seen_modules[mod] = node.lineno

                        if name in seen_names and seen_names[name] != node.lineno:
                            findings.append(ImportFinding(
                                file=rel_path,
                                line=node.lineno,
                                import_statement=raw.strip(),
                                issue="duplicate",
                                severity="warning",
                                suggestion=f"Name '{name}' already imported at line {seen_names[name]}",
                            ))
                        else:
                            seen_names[name] = node.lineno

                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        name = alias.asname or alias.name
                        if name in seen_names and seen_names[name] != node.lineno:
                            findings.append(ImportFinding(
                                file=rel_path,
                                line=node.lineno,
                                import_statement=raw.strip(),
                                issue="duplicate",
                                severity="warning",
                                suggestion=f"Name '{name}' already imported at line {seen_names[name]}",
                            ))
                        else:
                            seen_names[name] = node.lineno

        return findings

    def _find_shadowed(self, path: str) -> list[ImportFinding]:
        """Detect imports that are shadowed by local assignments."""
        findings: list[ImportFinding] = []
        try:
            source = Path(path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=path)
        except (SyntaxError, UnicodeDecodeError):
            return findings

        rel_path = self._rel(path)
        lines = source.splitlines()

        # Collect top-level imported names
        imported_names: dict[str, int] = {}  # name -> line
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[-1]
                    imported_names[name] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name != "*":
                        name = alias.asname or alias.name
                        imported_names[name] = node.lineno

        # Scan top-level assignments that shadow imports
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in imported_names:
                        imp_line = imported_names[target.id]
                        if node.lineno > imp_line:
                            raw = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                            findings.append(ImportFinding(
                                file=rel_path,
                                line=node.lineno,
                                import_statement=raw.strip(),
                                issue="shadowed",
                                severity="warning",
                                suggestion=f"Assignment shadows import '{target.id}' from line {imp_line}",
                            ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in imported_names:
                    imp_line = imported_names[node.name]
                    if node.lineno > imp_line:
                        findings.append(ImportFinding(
                            file=rel_path,
                            line=node.lineno,
                            import_statement=f"def {node.name}(...)",
                            issue="shadowed",
                            severity="warning",
                            suggestion=f"Function '{node.name}' shadows import from line {imp_line}",
                        ))

        return findings

    # ------------------------------------------------------------------
    # Auto-fix
    # ------------------------------------------------------------------

    def _auto_fix_unused(self, path: str, findings: list[ImportFinding]) -> int:
        """Remove unused import lines. Atomic write with backup."""
        unused_lines = {f.line for f in findings if f.issue == "unused"}
        if not unused_lines:
            return 0

        try:
            source = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return 0

        lines = source.splitlines(keepends=True)
        new_lines = []
        removed = 0

        for i, line in enumerate(lines, 1):
            if i in unused_lines:
                removed += 1
                logger.debug("Removed line %d from %s: %s", i, path, line.rstrip())
            else:
                new_lines.append(line)

        if removed == 0:
            return 0

        # Atomic write: write to temp, then rename
        fd, tmp_path = tempfile.mkstemp(
            suffix=Path(path).suffix,
            dir=os.path.dirname(path),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            # Create backup
            backup = path + ".bak"
            shutil.copy2(path, backup)

            # Atomic replace
            os.replace(tmp_path, path)

            # Remove backup on success
            try:
                os.unlink(backup)
            except OSError:
                pass

            logger.info("Fixed %d unused import(s) in %s", removed, self._rel(path))
        except OSError:
            # Clean up temp on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return 0

        return removed

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_paths(self, target: str) -> list[str]:
        """Resolve target to a list of Python files."""
        if target:
            full = os.path.join(self.cwd, target) if not os.path.isabs(target) else target
            if os.path.isfile(full):
                return [full]
            elif os.path.isdir(full):
                return self._collect_files(full)
            else:
                logger.warning("Target not found: %s", full)
                return []
        return self._collect_files(self.cwd)

    def _collect_files(self, directory: str) -> list[str]:
        """Collect scannable files from directory."""
        results: list[str] = []
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
            ".eggs", "*.egg-info",
        }
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.endswith(".egg-info")]
            for fname in files:
                ext = Path(fname).suffix
                if ext in PYTHON_EXTS or ext in JS_TS_EXTS:
                    results.append(os.path.join(root, fname))
        return results

    def _extract_python_imports(self, tree: ast.AST, lines: list[str]) -> list[_ImportInfo]:
        """Extract all imports from a Python AST."""
        imports: list[_ImportInfo] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    raw = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                    imports.append(_ImportInfo(
                        module=alias.name,
                        names=[],
                        alias=alias.asname,
                        line=node.lineno,
                        raw=raw,
                        is_from=False,
                    ))
            elif isinstance(node, ast.ImportFrom):
                raw = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                names = []
                is_wildcard = False
                for alias in (node.names or []):
                    if alias.name == "*":
                        is_wildcard = True
                    else:
                        names.append(alias.asname or alias.name)
                imports.append(_ImportInfo(
                    module=node.module or "",
                    names=names,
                    alias=None,
                    line=node.lineno,
                    raw=raw,
                    is_from=True,
                    is_wildcard=is_wildcard,
                ))
        return imports

    def _path_to_module(self, path: str) -> str:
        """Convert a file path to a dotted module name relative to cwd."""
        try:
            rel = os.path.relpath(path, self.cwd)
        except ValueError:
            return ""
        if rel.startswith(".."):
            return ""
        parts = Path(rel).with_suffix("").parts
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            return ""
        return ".".join(parts)

    def _rel(self, path: str) -> str:
        """Get relative path from cwd."""
        try:
            return os.path.relpath(path, self.cwd)
        except ValueError:
            return path


def format_import_report(findings: list[ImportFinding]) -> str:
    """Format findings into a readable terminal report."""
    if not findings:
        return "  No import issues found."

    lines: list[str] = []
    lines.append("")
    lines.append("  Import Optimizer Report")
    lines.append("  " + "=" * 40)
    lines.append("")

    # Group by issue type
    by_issue: dict[str, list[ImportFinding]] = {}
    for f in findings:
        by_issue.setdefault(f.issue, []).append(f)

    severity_icon = {
        "error": "[!]",
        "warning": "[~]",
        "info": "[i]",
    }

    issue_labels = {
        "unused": "Unused Imports",
        "circular": "Circular Dependencies",
        "heavy": "Heavy Top-Level Imports",
        "wildcard": "Wildcard Imports",
        "duplicate": "Duplicate Imports",
        "shadowed": "Shadowed Imports",
    }

    for issue_type in ["circular", "unused", "wildcard", "duplicate", "heavy", "shadowed"]:
        group = by_issue.get(issue_type, [])
        if not group:
            continue

        label = issue_labels.get(issue_type, issue_type)
        lines.append(f"  {label} ({len(group)})")
        lines.append("  " + "-" * 30)

        for f in group:
            icon = severity_icon.get(f.severity, "[-]")
            lines.append(f"    {icon} {f.file}:{f.line}")
            lines.append(f"        {f.import_statement}")
            lines.append(f"        -> {f.suggestion}")
        lines.append("")

    # Summary
    total = len(findings)
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    infos = sum(1 for f in findings if f.severity == "info")

    lines.append(f"  Total: {total} issue(s) — {errors} error(s), {warnings} warning(s), {infos} info")
    lines.append("")

    return "\n".join(lines)
