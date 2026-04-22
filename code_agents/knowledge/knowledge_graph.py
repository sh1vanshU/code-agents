"""Knowledge Graph — project structure index for efficient AI context.

Builds a dependency graph of source files (functions, classes, imports,
call relationships) and provides minimal, relevant context to AI agents
instead of requiring full file reads.

The graph is built asynchronously on server startup / chat init and updated
incrementally when files change (detected via git diff).

Storage: ``~/.code-agents/knowledge_graph/{repo-hash}/``
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from code_agents.parsers import ModuleInfo, SymbolInfo, parse_file, detect_language

logger = logging.getLogger("code_agents.knowledge.knowledge_graph")

# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

_KG_BASE = Path.home() / ".code-agents" / "knowledge_graph"

# File extensions to parse
_PARSEABLE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
    ".rb", ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt",
    ".scala", ".php",
}

# Directories to skip
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    "target", "vendor", ".idea", ".vscode", ".next", "coverage",
}

# Max files to parse (safety limit)
_MAX_FILES = 5000


def _repo_hash(repo_path: str) -> str:
    """Deterministic short hash for a repo path."""
    return hashlib.sha256(os.path.abspath(repo_path).encode()).hexdigest()[:12]


def _kg_dir(repo_path: str) -> Path:
    """Return the knowledge graph storage directory for a repo."""
    return _KG_BASE / _repo_hash(repo_path)


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------

class KnowledgeGraph:
    """Project structure index — builds and queries a dependency graph."""

    _instances: dict[str, "KnowledgeGraph"] = {}
    _lock = threading.Lock()

    def __new__(cls, repo_path: str) -> "KnowledgeGraph":
        """Singleton per repo path."""
        key = os.path.abspath(repo_path)
        with cls._lock:
            if key not in cls._instances:
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instances[key] = inst
            return cls._instances[key]

    def __init__(self, repo_path: str):
        if self._initialized:
            return
        self.repo_path = os.path.abspath(repo_path)
        self._dir = _kg_dir(self.repo_path)
        self._graph_path = self._dir / "graph.json"
        self._file_index_path = self._dir / "file_index.json"
        self._meta_path = self._dir / "meta.json"

        # In-memory graph
        self._nodes: dict[str, dict] = {}      # symbol_id → {name, kind, file, line, signature, docstring}
        self._edges: list[dict] = []            # [{source, target, kind}]  kind: "imports", "calls", "inherits"
        self._file_index: dict[str, list[str]] = {}  # file_path → [symbol_ids]
        self._imports_map: dict[str, list[str]] = {}  # file → [imported modules]
        self._meta: dict = {}

        self._building = False
        self._build_lock = threading.Lock()
        self._initialized = True

        # Load cached graph if exists
        self._load_cache()

    # -------------------------------------------------------------------
    # Build
    # -------------------------------------------------------------------

    def build(self, force: bool = False) -> None:
        """Full build of the knowledge graph.  Thread-safe."""
        with self._build_lock:
            if self._building:
                return
            self._building = True

        try:
            t0 = time.monotonic()
            logger.info("Knowledge graph: building for %s", self.repo_path)

            self._nodes.clear()
            self._edges.clear()
            self._file_index.clear()
            self._imports_map.clear()

            files = self._discover_files()
            logger.info("Knowledge graph: discovered %d parseable files", len(files))

            for fpath in files:
                self._parse_and_index(fpath)

            # Build dependency edges from imports
            self._build_import_edges()

            # Save
            self._save_cache()

            elapsed = time.monotonic() - t0
            logger.info(
                "Knowledge graph: built in %.1fs — %d symbols, %d files, %d edges",
                elapsed, len(self._nodes), len(self._file_index), len(self._edges),
            )
        finally:
            self._building = False

    def update(self) -> None:
        """Incremental update — re-parse only files changed since last build."""
        old_commit = self._meta.get("git_commit", "")
        new_commit = self._git_head()

        if not new_commit or new_commit == old_commit:
            return  # Nothing changed

        changed = self._git_changed_files(old_commit, new_commit) if old_commit else []

        if not changed and old_commit:
            self._meta["git_commit"] = new_commit
            self._save_meta()
            return

        if not old_commit or len(changed) > 100:
            # Too many changes or first build — do full rebuild
            self.build()
            return

        t0 = time.monotonic()
        logger.info("Knowledge graph: incremental update (%d files)", len(changed))

        for fpath in changed:
            abs_path = os.path.join(self.repo_path, fpath)
            # Remove old symbols for this file
            self._remove_file(abs_path)
            # Re-parse if file still exists
            if os.path.exists(abs_path) and self._is_parseable(abs_path):
                self._parse_and_index(abs_path)

        # Rebuild edges
        self._edges.clear()
        self._build_import_edges()
        self._save_cache()

        elapsed = time.monotonic() - t0
        logger.info("Knowledge graph: updated in %.1fs", elapsed)

    def is_stale(self) -> bool:
        """Check if the graph needs an update (git HEAD changed)."""
        current = self._git_head()
        cached = self._meta.get("git_commit", "")
        if not cached:
            return True
        return current != cached

    @property
    def is_ready(self) -> bool:
        """True if the graph has been built at least once."""
        return bool(self._nodes)

    # -------------------------------------------------------------------
    # Query
    # -------------------------------------------------------------------

    def query(self, keywords: list[str], file_path: str | None = None, max_results: int = 30) -> list[dict]:
        """Find symbols matching keywords.  Returns list of node dicts."""
        results = []
        kw_lower = [k.lower() for k in keywords]

        candidates = self._nodes.values()
        if file_path:
            # Restrict to symbols in or related to this file
            rel = self._relative(file_path)
            symbol_ids = set(self._file_index.get(rel, []))
            # Also include symbols from files that import/are imported by this file
            for edge in self._edges:
                if edge.get("source") == rel:
                    symbol_ids.update(self._file_index.get(edge["target"], []))
                elif edge.get("target") == rel:
                    symbol_ids.update(self._file_index.get(edge["source"], []))
            candidates = [self._nodes[sid] for sid in symbol_ids if sid in self._nodes]

        for node in candidates:
            score = 0
            name_lower = node.get("name", "").lower()
            sig_lower = node.get("signature", "").lower()
            doc_lower = node.get("docstring", "").lower()
            for kw in kw_lower:
                if kw in name_lower:
                    score += 3
                elif kw in sig_lower:
                    score += 2
                elif kw in doc_lower:
                    score += 1
            if score > 0:
                results.append({**node, "_score": score})

        results.sort(key=lambda x: x["_score"], reverse=True)
        return results[:max_results]

    def blast_radius(self, file_path: str, depth: int = 2) -> list[str]:
        """Find all files potentially affected by a change to *file_path*.

        Returns relative file paths including the changed file itself.
        """
        rel = self._relative(file_path)
        affected: set[str] = {rel}

        frontier = {rel}
        for _ in range(depth):
            next_frontier: set[str] = set()
            for edge in self._edges:
                src, tgt = edge.get("source", ""), edge.get("target", "")
                if tgt in frontier and src not in affected:
                    next_frontier.add(src)
                    affected.add(src)
            frontier = next_frontier
            if not frontier:
                break

        return sorted(affected)

    def get_context_for_prompt(self, query_text: str, max_tokens: int = 1500) -> str:
        """Generate a compact context string for injection into the system prompt.

        Estimates ~4 chars per token.
        """
        if not self._nodes:
            return ""

        keywords = [w for w in query_text.lower().split() if len(w) > 2]
        if not keywords:
            return self._summary_context(max_tokens)

        results = self.query(keywords, max_results=20)
        if not results:
            return self._summary_context(max_tokens)

        max_chars = max_tokens * 4
        lines = ["--- Project Structure (auto-indexed) ---",
                 "Relevant modules for this request:", ""]

        current_file = ""
        chars = 150  # header overhead
        for node in results:
            fpath = node.get("file", "")
            if fpath != current_file:
                current_file = fpath
                file_line = f"{fpath}:"
                lines.append(file_line)
                chars += len(file_line) + 1

            sig = node.get("signature", node.get("name", ""))
            doc = f" -- {node['docstring']}" if node.get("docstring") else ""
            symbol_line = f"  - {sig} (line {node.get('line', '?')}){doc}"

            if chars + len(symbol_line) > max_chars:
                break
            lines.append(symbol_line)
            chars += len(symbol_line) + 1

        # Add import chain if space allows
        if chars < max_chars - 200:
            imports_section = self._format_imports_section(results, max_chars - chars)
            if imports_section:
                lines.append("")
                lines.append(imports_section)

        lines.append("--- End Project Structure ---")
        return "\n".join(lines)

    def get_stats(self) -> dict:
        """Return graph statistics."""
        return {
            "files": len(self._file_index),
            "symbols": len(self._nodes),
            "edges": len(self._edges),
            "git_commit": self._meta.get("git_commit", ""),
            "last_build": self._meta.get("last_build", ""),
        }

    # -------------------------------------------------------------------
    # Internal — file discovery
    # -------------------------------------------------------------------

    def _discover_files(self) -> list[str]:
        """Walk the repo and find parseable source files."""
        files = []
        ignore_patterns = self._load_ignore_patterns()

        for root, dirs, filenames in os.walk(self.repo_path):
            # Prune skipped directories
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]

            rel_root = os.path.relpath(root, self.repo_path)
            if any(p in rel_root for p in ignore_patterns):
                dirs.clear()
                continue

            for fname in filenames:
                if len(files) >= _MAX_FILES:
                    break
                fpath = os.path.join(root, fname)
                if self._is_parseable(fpath):
                    files.append(fpath)

        return files

    def _is_parseable(self, fpath: str) -> bool:
        """Check if a file should be parsed."""
        ext = Path(fpath).suffix.lower()
        if ext not in _PARSEABLE_EXTS:
            return False
        # Skip very large files (>500KB)
        try:
            if os.path.getsize(fpath) > 500_000:
                return False
        except OSError:
            return False
        return True

    def _load_ignore_patterns(self) -> list[str]:
        """Load custom ignore patterns from .code-agents/.ignore."""
        patterns = []
        ignore_file = os.path.join(self.repo_path, ".code-agents", ".ignore")
        if os.path.exists(ignore_file):
            try:
                with open(ignore_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            patterns.append(line)
            except OSError:
                pass
        return patterns

    # -------------------------------------------------------------------
    # Internal — parsing and indexing
    # -------------------------------------------------------------------

    def _parse_and_index(self, fpath: str) -> None:
        """Parse a file and add its symbols to the graph."""
        try:
            module = parse_file(fpath)
        except Exception as e:
            logger.debug("Parse failed for %s: %s", fpath, e)
            return

        rel = self._relative(fpath)
        symbol_ids = []

        for sym in module.symbols:
            sid = f"{rel}::{sym.name}:{sym.line_number}"
            self._nodes[sid] = {
                "name": sym.name,
                "kind": sym.kind,
                "file": rel,
                "line": sym.line_number,
                "signature": sym.signature,
                "docstring": sym.docstring,
            }
            symbol_ids.append(sid)

        self._file_index[rel] = symbol_ids
        self._imports_map[rel] = module.imports

    def _remove_file(self, fpath: str) -> None:
        """Remove all symbols for a file from the graph."""
        rel = self._relative(fpath)
        for sid in self._file_index.pop(rel, []):
            self._nodes.pop(sid, None)
        self._imports_map.pop(rel, None)

    def _build_import_edges(self) -> None:
        """Build 'imports' edges by matching import names to indexed files."""
        # Build a lookup: module_name → file_path
        name_to_file: dict[str, str] = {}
        for fpath in self._file_index:
            # e.g. "code_agents/backend.py" → "code_agents.core.backend"
            module_name = fpath.replace("/", ".").replace("\\", ".")
            if module_name.endswith(".py"):
                module_name = module_name[:-3]
            name_to_file[module_name] = fpath
            # Also index by last component
            parts = module_name.split(".")
            if len(parts) > 1:
                name_to_file[parts[-1]] = fpath

        for fpath, imports in self._imports_map.items():
            for imp in imports:
                # Try exact match, then partial
                target = name_to_file.get(imp)
                if not target:
                    # Try matching end of module path
                    for mod_name, mod_file in name_to_file.items():
                        if mod_name.endswith(f".{imp}") or mod_name == imp:
                            target = mod_file
                            break
                if target and target != fpath:
                    self._edges.append({
                        "source": fpath,
                        "target": target,
                        "kind": "imports",
                    })

    # -------------------------------------------------------------------
    # Internal — git operations
    # -------------------------------------------------------------------

    def _git_head(self) -> str:
        """Get current git HEAD commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=self.repo_path,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except Exception:
            return ""

    def _git_changed_files(self, old_commit: str, new_commit: str) -> list[str]:
        """Get files changed between two commits."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", old_commit, new_commit],
                capture_output=True, text=True, timeout=10,
                cwd=self.repo_path,
            )
            if result.returncode == 0:
                return [f for f in result.stdout.strip().split("\n") if f]
        except Exception:
            pass
        return []

    # -------------------------------------------------------------------
    # Internal — cache persistence
    # -------------------------------------------------------------------

    def _save_cache(self) -> None:
        """Persist graph to disk."""
        self._dir.mkdir(parents=True, exist_ok=True)

        self._meta["git_commit"] = self._git_head()
        self._meta["last_build"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._meta["repo_path"] = self.repo_path

        try:
            with open(self._graph_path, "w") as f:
                json.dump({"nodes": self._nodes, "edges": self._edges}, f, separators=(",", ":"))
            with open(self._file_index_path, "w") as f:
                json.dump({"file_index": self._file_index, "imports_map": self._imports_map}, f, separators=(",", ":"))
            self._save_meta()
        except OSError as e:
            logger.warning("Failed to save knowledge graph cache: %s", e)

    def _save_meta(self) -> None:
        """Save only meta.json."""
        try:
            with open(self._meta_path, "w") as f:
                json.dump(self._meta, f, indent=2)
        except OSError:
            pass

    def _load_cache(self) -> None:
        """Load graph from disk cache if available."""
        if not self._meta_path.exists():
            return
        try:
            with open(self._meta_path) as f:
                self._meta = json.load(f)
            if self._graph_path.exists():
                with open(self._graph_path) as f:
                    data = json.load(f)
                    self._nodes = data.get("nodes", {})
                    self._edges = data.get("edges", [])
            if self._file_index_path.exists():
                with open(self._file_index_path) as f:
                    data = json.load(f)
                    self._file_index = data.get("file_index", {})
                    self._imports_map = data.get("imports_map", {})
            logger.info(
                "Knowledge graph: loaded cache (%d symbols, %d files)",
                len(self._nodes), len(self._file_index),
            )
        except (OSError, json.JSONDecodeError) as e:
            logger.debug("Failed to load knowledge graph cache: %s", e)

    # -------------------------------------------------------------------
    # Internal — helpers
    # -------------------------------------------------------------------

    def _relative(self, fpath: str) -> str:
        """Convert absolute path to relative (from repo root)."""
        try:
            return os.path.relpath(fpath, self.repo_path)
        except ValueError:
            return fpath

    def _summary_context(self, max_tokens: int = 1500) -> str:
        """Generate a summary context when no specific query keywords match."""
        if not self._file_index:
            return ""
        max_chars = max_tokens * 4
        lines = ["--- Project Structure (auto-indexed) ---",
                 f"Indexed: {len(self._file_index)} files, {len(self._nodes)} symbols", ""]

        # Group by top-level directory
        dirs: dict[str, list[str]] = {}
        for fpath in sorted(self._file_index.keys()):
            parts = fpath.split("/")
            top = parts[0] if len(parts) > 1 else "."
            dirs.setdefault(top, []).append(fpath)

        chars = 200
        for d, files in sorted(dirs.items(), key=lambda x: -len(x[1])):
            dir_line = f"{d}/ ({len(files)} files)"
            if chars + len(dir_line) > max_chars:
                break
            lines.append(dir_line)
            chars += len(dir_line) + 1
            # Show top symbols from this directory
            for fpath in files[:3]:
                for sid in self._file_index.get(fpath, [])[:2]:
                    node = self._nodes.get(sid, {})
                    if node.get("kind") in ("class", "function"):
                        sym_line = f"  {node.get('signature', node.get('name', ''))}"
                        if chars + len(sym_line) > max_chars:
                            break
                        lines.append(sym_line)
                        chars += len(sym_line) + 1

        lines.append("--- End Project Structure ---")
        return "\n".join(lines)

    def _format_imports_section(self, results: list[dict], max_chars: int) -> str:
        """Format import chains for the context."""
        files_in_results = {r.get("file", "") for r in results}
        chains = []
        for fpath in files_in_results:
            deps = [e["target"] for e in self._edges if e.get("source") == fpath]
            if deps:
                chain = f"  {fpath} -> {', '.join(deps[:5])}"
                chains.append(chain)

        if not chains:
            return ""

        section = "Dependency chains:\n" + "\n".join(chains[:5])
        return section[:max_chars]
