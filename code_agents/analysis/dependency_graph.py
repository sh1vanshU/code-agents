"""Dependency graph builder — visual dependency tree for classes/modules.

Scans source files (Python, Java, JS/TS) to build import/dependency
relationships. Detects circular dependencies.

Usage:
    from code_agents.analysis.dependency_graph import DependencyGraph
    dg = DependencyGraph("/path/to/repo")
    dg.build_graph()
    print(dg.format_tree("PaymentService"))

Lazy-loaded: no heavy imports at module level.
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.analysis.dependency_graph")

# File extensions by language
_PYTHON_EXTS = {".py"}
_JAVA_EXTS = {".java"}
_JS_TS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs"}

# Directories to skip
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
    "target", ".gradle", ".idea", ".vscode", ".eggs", "*.egg-info",
}


class DependencyGraph:
    """Build and query a dependency graph from source files."""

    def __init__(self, cwd: str) -> None:
        self.cwd = Path(cwd)
        # module/class -> set of modules/classes it imports
        self.outgoing: dict[str, set[str]] = defaultdict(set)
        # module/class -> set of modules/classes that import it
        self.incoming: dict[str, set[str]] = defaultdict(set)
        # all known names
        self.all_names: set[str] = set()
        self._built = False

    def build_graph(self) -> None:
        """Scan all source files and build the dependency graph."""
        for root, dirs, files in os.walk(self.cwd):
            # Prune skipped directories
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.endswith(".egg-info")]

            for fname in files:
                fpath = Path(root) / fname
                ext = fpath.suffix.lower()

                if ext in _PYTHON_EXTS:
                    self._parse_python(fpath)
                elif ext in _JAVA_EXTS:
                    self._parse_java(fpath)
                elif ext in _JS_TS_EXTS:
                    self._parse_js_ts(fpath)

        self._built = True
        logger.info("Dependency graph built: %d nodes, %d edges",
                     len(self.all_names),
                     sum(len(v) for v in self.outgoing.values()))

    def _module_name_from_path(self, fpath: Path) -> str:
        """Derive a short module name from a file path."""
        try:
            rel = fpath.relative_to(self.cwd)
        except ValueError:
            rel = fpath
        # Remove extension, convert path separators to dots
        name = str(rel).replace(os.sep, ".").replace("/", ".")
        for ext in (".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".mjs"):
            if name.endswith(ext):
                name = name[: -len(ext)]
                break
        # Remove __init__ suffix
        if name.endswith(".__init__"):
            name = name[: -len(".__init__")]
        return name

    def _parse_python(self, fpath: Path) -> None:
        """Parse Python imports using the ast module (lazy-loaded)."""
        import ast

        try:
            source = fpath.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(fpath))
        except (SyntaxError, UnicodeDecodeError):
            return

        module_name = self._module_name_from_path(fpath)
        self.all_names.add(module_name)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dep = alias.name
                    self.outgoing[module_name].add(dep)
                    self.incoming[dep].add(module_name)
                    self.all_names.add(dep)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    dep = node.module
                    self.outgoing[module_name].add(dep)
                    self.incoming[dep].add(module_name)
                    self.all_names.add(dep)
                    # Also track individual imported names
                    for alias in (node.names or []):
                        if alias.name != "*":
                            full = f"{dep}.{alias.name}"
                            self.outgoing[module_name].add(full)
                            self.incoming[full].add(module_name)
                            self.all_names.add(full)

    def _parse_java(self, fpath: Path) -> None:
        """Parse Java imports and @Autowired / constructor injection."""
        try:
            source = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        module_name = self._module_name_from_path(fpath)
        self.all_names.add(module_name)

        # Extract class name from file
        class_match = re.search(r"(?:public\s+)?class\s+(\w+)", source)
        class_name = class_match.group(1) if class_match else None
        if class_name:
            self.all_names.add(class_name)

        # Standard import statements
        for m in re.finditer(r"^import\s+([\w.]+)\s*;", source, re.MULTILINE):
            dep = m.group(1)
            short_dep = dep.rsplit(".", 1)[-1]  # e.g. com.foo.Bar -> Bar
            src = class_name or module_name
            self.outgoing[src].add(short_dep)
            self.incoming[short_dep].add(src)
            self.all_names.add(short_dep)

        # @Autowired field injection
        for m in re.finditer(
            r"@Autowired\s+(?:private\s+|protected\s+)?(\w+)\s+\w+",
            source,
        ):
            dep = m.group(1)
            src = class_name or module_name
            self.outgoing[src].add(dep)
            self.incoming[dep].add(src)
            self.all_names.add(dep)

        # Constructor injection: public ClassName(TypeA a, TypeB b)
        if class_name:
            ctor_pat = rf"(?:public\s+)?{re.escape(class_name)}\s*\(([^)]+)\)"
            ctor_match = re.search(ctor_pat, source)
            if ctor_match:
                params = ctor_match.group(1)
                for param_type in re.findall(r"(\w+)\s+\w+", params):
                    if param_type[0].isupper() and param_type not in ("String", "int", "long", "boolean", "double", "float", "void", "Integer", "Long", "Boolean", "Double", "Float", "List", "Map", "Set", "Optional"):
                        self.outgoing[class_name].add(param_type)
                        self.incoming[param_type].add(class_name)
                        self.all_names.add(param_type)

    def _parse_js_ts(self, fpath: Path) -> None:
        """Parse JS/TS import/require statements."""
        try:
            source = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        module_name = self._module_name_from_path(fpath)
        self.all_names.add(module_name)

        # ES6 imports: import X from 'Y', import { X } from 'Y'
        for m in re.finditer(
            r"""import\s+(?:(?:\{[^}]*\}|\w+|\*\s+as\s+\w+)\s*,?\s*)*from\s+['"]([^'"]+)['"]""",
            source,
        ):
            dep = m.group(1)
            dep = self._normalize_js_path(dep)
            self.outgoing[module_name].add(dep)
            self.incoming[dep].add(module_name)
            self.all_names.add(dep)

        # require() calls
        for m in re.finditer(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", source):
            dep = m.group(1)
            dep = self._normalize_js_path(dep)
            self.outgoing[module_name].add(dep)
            self.incoming[dep].add(module_name)
            self.all_names.add(dep)

    @staticmethod
    def _normalize_js_path(dep: str) -> str:
        """Normalize a JS/TS import path to a short name."""
        # Remove leading ./ or ../
        dep = re.sub(r"^\.+/", "", dep)
        # Remove file extension
        dep = re.sub(r"\.(js|jsx|ts|tsx|mjs)$", "", dep)
        # Convert slashes to dots for consistency
        dep = dep.replace("/", ".")
        return dep

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_dependencies(self, name: str) -> set[str]:
        """Return what this module/class imports (outgoing edges)."""
        matches = self._resolve_name(name)
        result: set[str] = set()
        for m in matches:
            result.update(self.outgoing.get(m, set()))
        return result

    def get_dependents(self, name: str) -> set[str]:
        """Return who imports this module/class (incoming edges)."""
        matches = self._resolve_name(name)
        result: set[str] = set()
        for m in matches:
            result.update(self.incoming.get(m, set()))
        return result

    def _resolve_name(self, name: str) -> list[str]:
        """Fuzzy-match a name against all known names.

        Tries exact match first, then suffix match, then substring.
        """
        if name in self.all_names:
            return [name]

        # Suffix match (e.g. "PaymentService" matches "com.foo.PaymentService")
        suffix = [n for n in self.all_names if n.endswith(f".{name}") or n.rsplit(".", 1)[-1] == name]
        if suffix:
            return suffix

        # Case-insensitive match
        lower = name.lower()
        case_matches = [n for n in self.all_names if n.lower() == lower or n.rsplit(".", 1)[-1].lower() == lower]
        if case_matches:
            return case_matches

        return []

    def find_circular_deps(self) -> list[list[str]]:
        """Detect circular dependency chains using DFS."""
        visited: set[str] = set()
        on_stack: set[str] = set()
        stack: list[str] = []
        cycles: list[list[str]] = []
        seen_cycles: set[frozenset[str]] = set()

        def _dfs(node: str) -> None:
            visited.add(node)
            on_stack.add(node)
            stack.append(node)

            for neighbor in self.outgoing.get(node, set()):
                if neighbor not in visited:
                    _dfs(neighbor)
                elif neighbor in on_stack:
                    # Found a cycle — extract it
                    idx = stack.index(neighbor)
                    cycle = stack[idx:] + [neighbor]
                    key = frozenset(cycle[:-1])
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        cycles.append(cycle)

            stack.pop()
            on_stack.discard(node)

        for node in list(self.all_names):
            if node not in visited:
                _dfs(node)

        return cycles

    def get_tree(self, name: str, direction: str = "both", depth: int = 3) -> dict:
        """Build a dependency tree dict up to a given depth.

        Args:
            name: Module/class name to root the tree at.
            direction: "out" (uses), "in" (used by), or "both".
            depth: Maximum depth to traverse.

        Returns:
            Dict with keys "name", "uses", "used_by", "circular".
        """
        result: dict = {"name": name, "uses": {}, "used_by": {}, "circular": []}

        if direction in ("out", "both"):
            result["uses"] = self._build_subtree(name, "out", depth, set())
        if direction in ("in", "both"):
            result["used_by"] = self._build_subtree(name, "in", depth, set())

        result["circular"] = self.find_circular_deps()
        return result

    def _build_subtree(
        self, name: str, direction: str, depth: int, visited: set[str]
    ) -> dict[str, dict]:
        """Recursively build a subtree."""
        if depth <= 0 or name in visited:
            return {}

        visited = visited | {name}
        edges = self.outgoing if direction == "out" else self.incoming
        matches = self._resolve_name(name)

        children: set[str] = set()
        for m in matches:
            children.update(edges.get(m, set()))

        subtree: dict[str, dict] = {}
        for child in sorted(children):
            subtree[child] = self._build_subtree(child, direction, depth - 1, visited)

        return subtree

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_tree(self, name: str, depth: int = 3) -> str:
        """Format a full dependency tree as an ASCII string."""
        tree = self.get_tree(name, depth=depth)
        lines: list[str] = []

        lines.append(f"  Dependency Graph: {name}")
        lines.append("  " + "=" * (len(name) + 20))
        lines.append("")

        # Uses (outgoing)
        uses = tree.get("uses", {})
        if uses:
            lines.append("  Uses (outgoing):")
            lines.append(f"    {name}")
            self._format_subtree(uses, lines, prefix="    ")
        else:
            lines.append("  Uses (outgoing): (none)")
        lines.append("")

        # Used by (incoming)
        used_by = tree.get("used_by", {})
        if used_by:
            lines.append("  Used by (incoming):")
            lines.append(f"    {name}")
            self._format_subtree(used_by, lines, prefix="    ")
        else:
            lines.append("  Used by (incoming): (none)")
        lines.append("")

        # Circular deps
        circular = tree.get("circular", [])
        # Filter to cycles involving the queried name
        relevant = [c for c in circular if any(name in node or node.endswith(f".{name}") for node in c)]
        if relevant:
            lines.append("  \u26a0 Circular dependency detected:")
            for cycle in relevant[:5]:  # limit to 5
                lines.append(f"    {' -> '.join(cycle)}")
        elif circular:
            lines.append(f"  \u2713 No circular dependencies involving {name}")
            lines.append(f"    ({len(circular)} cycle(s) found elsewhere in codebase)")

        return "\n".join(lines)

    def _format_subtree(
        self, subtree: dict[str, dict], lines: list[str], prefix: str = ""
    ) -> None:
        """Recursively format a subtree with box-drawing characters."""
        items = list(subtree.items())
        for i, (child, children) in enumerate(items):
            is_last = i == len(items) - 1
            connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
            lines.append(f"{prefix}{connector}{child}")
            if children:
                extension = "    " if is_last else "\u2502   "
                self._format_subtree(children, lines, prefix=prefix + extension)

    def format_mermaid(self, name: str, depth: int = 3) -> str:
        """Format dependency graph as a Mermaid diagram."""
        tree = self.get_tree(name, depth=depth)
        lines: list[str] = ["graph TD"]

        # Sanitize node names for Mermaid (replace dots with underscores)
        def _mermaid_id(n: str) -> str:
            return n.replace(".", "_").replace("-", "_").replace("/", "_")

        def _add_edges(subtree: dict[str, dict], parent: str, direction: str) -> None:
            for child, children in subtree.items():
                pid = _mermaid_id(parent)
                cid = _mermaid_id(child)
                if direction == "out":
                    lines.append(f"    {pid}[\"{parent}\"] --> {cid}[\"{child}\"]")
                else:
                    lines.append(f"    {cid}[\"{child}\"] --> {pid}[\"{parent}\"]")
                if children:
                    _add_edges(children, child, direction)

        uses = tree.get("uses", {})
        _add_edges(uses, name, "out")

        used_by = tree.get("used_by", {})
        _add_edges(used_by, name, "in")

        if len(lines) == 1:
            lines.append(f"    {_mermaid_id(name)}[\"{name}\"]")

        return "\n".join(lines)

    def format_dot(self, name: str, depth: int = 3) -> str:
        """Format dependency graph as Graphviz DOT."""
        tree = self.get_tree(name, depth=depth)
        lines: list[str] = [
            "digraph deps {",
            "    rankdir=LR;",
            f'    node [shape=box, style=filled, fillcolor=lightblue];',
        ]

        def _add_edges(subtree: dict[str, dict], parent: str, direction: str) -> None:
            for child, children in subtree.items():
                if direction == "out":
                    lines.append(f'    "{parent}" -> "{child}";')
                else:
                    lines.append(f'    "{child}" -> "{parent}";')
                if children:
                    _add_edges(children, child, direction)

        uses = tree.get("uses", {})
        _add_edges(uses, name, "out")

        used_by = tree.get("used_by", {})
        _add_edges(used_by, name, "in")

        lines.append("}")
        return "\n".join(lines)
