"""Call Chain Visualizer — trace full call tree up and down for any function.

Given a function name, shows all callers (who calls it) and callees
(what it calls) as a tree with file:line links.

Usage:
    from code_agents.observability.call_chain import CallChainAnalyzer
    analyzer = CallChainAnalyzer("/path/to/repo")
    result = analyzer.analyze("build_prompt")
    print(format_call_chain(result))
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.observability.call_chain")


@dataclass
class CallChainConfig:
    """Configuration for call chain analysis."""
    cwd: str = "."
    max_depth: int = 3
    include_stdlib: bool = False
    include_tests: bool = False


@dataclass
class CallNode:
    """A node in the call tree."""
    name: str
    file: str = ""
    line: int = 0
    depth: int = 0
    children: list[CallNode] = field(default_factory=list)
    is_recursive: bool = False
    is_external: bool = False  # stdlib or third-party


@dataclass
class CallChainResult:
    """Result of call chain analysis."""
    target: str
    target_file: str = ""
    target_line: int = 0

    # Callers tree (who calls this function)
    callers_tree: Optional[CallNode] = None
    callers_count: int = 0

    # Callees tree (what this function calls)
    callees_tree: Optional[CallNode] = None
    callees_count: int = 0

    # Flat lists for easy access
    direct_callers: list[str] = field(default_factory=list)
    direct_callees: list[str] = field(default_factory=list)

    # Analysis
    is_entry_point: bool = False  # no callers
    is_leaf: bool = False  # no callees (pure computation)
    recursive_calls: list[str] = field(default_factory=list)


class CallChainAnalyzer:
    """Analyze call chains in a codebase."""

    def __init__(self, config: CallChainConfig):
        self.config = config
        self._call_graph: dict[str, set[str]] = {}
        self._reverse_graph: dict[str, set[str]] = defaultdict(set)
        self._locations: dict[str, tuple[str, int]] = {}  # name -> (file, line)
        self._built = False

    def analyze(self, target: str) -> CallChainResult:
        """Analyze call chain for a target function."""
        logger.info("Analyzing call chain for: %s", target)

        if not self._built:
            self._build_graphs()

        result = CallChainResult(target=target)

        # Find target location
        if target in self._locations:
            result.target_file, result.target_line = self._locations[target]

        # Build callers tree (upstream)
        result.callers_tree = self._build_callers_tree(target, depth=0, visited=set())
        result.callers_count = self._count_nodes(result.callers_tree) - 1 if result.callers_tree else 0
        result.direct_callers = sorted(self._reverse_graph.get(target, set()))

        # Build callees tree (downstream)
        result.callees_tree = self._build_callees_tree(target, depth=0, visited=set())
        result.callees_count = self._count_nodes(result.callees_tree) - 1 if result.callees_tree else 0
        result.direct_callees = sorted(self._call_graph.get(target, set()))

        # Analysis flags
        result.is_entry_point = result.callers_count == 0
        result.is_leaf = result.callees_count == 0

        # Detect recursion
        if target in self._call_graph.get(target, set()):
            result.recursive_calls.append(target)

        logger.info(
            "Call chain: %d callers, %d callees, entry=%s, leaf=%s",
            result.callers_count, result.callees_count,
            result.is_entry_point, result.is_leaf,
        )
        return result

    def _build_graphs(self):
        """Build call graph and reverse graph from codebase."""
        from code_agents.analysis._ast_helpers import (
            scan_python_files, parse_python_file, find_functions, find_calls,
        )

        for fpath in scan_python_files(self.config.cwd):
            if not self.config.include_tests and ("/test_" in os.path.basename(fpath) or "/tests/" in fpath):
                continue

            tree = parse_python_file(fpath)
            if tree is None:
                continue

            rel_path = os.path.relpath(fpath, self.config.cwd)

            # Record function locations
            for func in find_functions(tree, rel_path):
                self._locations[func.name] = (rel_path, func.line)

            # Record calls using simple function names (not file:function)
            for call in find_calls(tree, rel_path):
                self._call_graph.setdefault(call.caller, set()).add(call.callee)
                self._reverse_graph[call.callee].add(call.caller)
                # Also handle dotted callees (obj.method -> method)
                if "." in call.callee:
                    short = call.callee.rsplit(".", 1)[-1]
                    self._reverse_graph[short].add(call.caller)

        self._built = True
        logger.debug("Built call graph: %d functions, %d call edges",
                      len(self._locations), sum(len(v) for v in self._call_graph.values()))

    def _build_callers_tree(self, name: str, depth: int, visited: set) -> CallNode:
        """Build tree of who calls this function."""
        file, line = self._locations.get(name, ("", 0))
        node = CallNode(name=name, file=file, line=line, depth=depth)

        if depth >= self.config.max_depth or name in visited:
            node.is_recursive = name in visited
            return node

        visited = visited | {name}
        callers = self._reverse_graph.get(name, set())
        for caller in sorted(callers):
            child = self._build_callers_tree(caller, depth + 1, visited)
            node.children.append(child)

        return node

    def _build_callees_tree(self, name: str, depth: int, visited: set) -> CallNode:
        """Build tree of what this function calls."""
        file, line = self._locations.get(name, ("", 0))
        node = CallNode(name=name, file=file, line=line, depth=depth)

        if depth >= self.config.max_depth or name in visited:
            node.is_recursive = name in visited
            return node

        visited = visited | {name}
        callees = self._call_graph.get(name, set())
        for callee in sorted(callees):
            child = self._build_callees_tree(callee, depth + 1, visited)
            node.children.append(child)

        return node

    def _count_nodes(self, node: Optional[CallNode]) -> int:
        """Count total nodes in a tree."""
        if node is None:
            return 0
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count


def format_call_chain(result: CallChainResult) -> str:
    """Format call chain for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Call Chain: {result.target}")
    if result.target_file:
        lines.append(f"  Location: {result.target_file}:{result.target_line}")
    lines.append(f"{'=' * 60}")

    flags = []
    if result.is_entry_point:
        flags.append("ENTRY POINT (no callers)")
    if result.is_leaf:
        flags.append("LEAF (no callees)")
    if result.recursive_calls:
        flags.append("RECURSIVE")
    if flags:
        lines.append(f"  Flags: {', '.join(flags)}")

    # Callers (upstream)
    lines.append(f"\n  CALLERS ({result.callers_count}):")
    if result.callers_tree:
        _format_tree(result.callers_tree, lines, prefix="    ", is_caller=True)
    else:
        lines.append("    (none)")

    # Callees (downstream)
    lines.append(f"\n  CALLEES ({result.callees_count}):")
    if result.callees_tree:
        _format_tree(result.callees_tree, lines, prefix="    ", is_caller=False)
    else:
        lines.append("    (none)")

    lines.append("")
    return "\n".join(lines)


def _format_tree(node: CallNode, lines: list[str], prefix: str, is_caller: bool):
    """Recursively format a call tree."""
    loc = f" ({node.file}:{node.line})" if node.file else ""
    marker = "<-" if is_caller else "->"
    rec = " [RECURSIVE]" if node.is_recursive else ""
    lines.append(f"{prefix}{marker} {node.name}{loc}{rec}")
    for child in node.children:
        _format_tree(child, lines, prefix + "  ", is_caller)
