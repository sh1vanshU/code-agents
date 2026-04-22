"""Smart Context Injection via RAG — vector-based code search for AI context.

Builds a searchable index of code chunks (functions, classes, blocks) and
provides relevant context to AI agents via TF-IDF similarity (always available)
or sentence-transformer embeddings (optional enhancement).

Storage: ``~/.code-agents/vector-store/{repo-hash}/``
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import subprocess
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.rag_context")

# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

VECTOR_STORE_DIR = Path.home() / ".code-agents" / "vector-store"

# Reuse parseable extensions from knowledge_graph
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

# Max files to index (safety limit)
_MAX_FILES = 5000

# Sliding window defaults
_WINDOW_SIZE = 50   # lines per chunk
_WINDOW_OVERLAP = 10  # overlap between chunks


def _repo_hash(repo_path: str) -> str:
    """Deterministic short hash for a repo path."""
    return hashlib.sha256(os.path.abspath(repo_path).encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CodeChunk:
    """A single chunk of code from a source file."""
    file_path: str
    start_line: int
    end_line: int
    content: str
    symbol_name: str = ""
    language: str = ""


# ---------------------------------------------------------------------------
# TF-IDF tokenizer
# ---------------------------------------------------------------------------

# Pattern to split camelCase and snake_case
_SPLIT_RE = re.compile(r"[A-Z][a-z]+|[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[A-Z]+|\d+")
_TOKEN_RE = re.compile(r"[a-zA-Z_]\w*")

# Common stop words to filter out
_STOP_WORDS = frozenset({
    "the", "is", "at", "which", "on", "a", "an", "and", "or", "not",
    "in", "to", "for", "of", "with", "it", "this", "that", "from",
    "by", "be", "as", "are", "was", "were", "been", "has", "have",
    "had", "do", "does", "did", "but", "if", "else", "elif", "def",
    "class", "return", "import", "self", "true", "false", "none",
    "int", "str", "bool", "float", "list", "dict", "set", "tuple",
    "var", "let", "const", "function", "new", "null", "undefined",
    "void", "public", "private", "static", "final", "string",
})


def _tokenize(text: str) -> list[str]:
    """Tokenize text by splitting on whitespace, camelCase, and snake_case.

    Returns lowercased tokens with stop words filtered.
    """
    tokens = []
    # First extract identifiers
    for match in _TOKEN_RE.finditer(text):
        word = match.group()
        # Split camelCase / PascalCase
        parts = _SPLIT_RE.findall(word)
        if parts:
            for p in parts:
                low = p.lower()
                if low not in _STOP_WORDS and len(low) > 1:
                    tokens.append(low)
        else:
            low = word.lower()
            if low not in _STOP_WORDS and len(low) > 1:
                tokens.append(low)
    return tokens


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

class VectorStore:
    """Code chunk index with TF-IDF search (and optional embeddings)."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self._dir = VECTOR_STORE_DIR / _repo_hash(self.repo_path)
        self._chunks_path = self._dir / "chunks.json"
        self._tfidf_path = self._dir / "tfidf.json"
        self._meta_path = self._dir / "meta.json"
        self._embeddings_path = self._dir / "embeddings.bin"

        # In-memory state
        self._chunks: list[CodeChunk] = []
        self._meta: dict = {}

        # TF-IDF state
        self._idf: dict[str, float] = {}           # term -> IDF score
        self._chunk_tfs: list[dict[str, float]] = []  # per-chunk TF vectors
        self._chunk_norms: list[float] = []         # precomputed norms

        # Embeddings (optional)
        self._embeddings: Optional[list] = None
        self._embed_model = None

        # Load cached data
        self._load_cache()

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def build(self, force: bool = False) -> int:
        """Build the full index from scratch.

        1. Walk repo files (parseable extensions, skip hidden/vendor dirs)
        2. Chunk by function/class boundaries using parsers, fallback sliding window
        3. Build TF-IDF index (always available, no deps)
        4. Optionally build embeddings if sentence-transformers available

        Returns the total chunk count.
        """
        if not force and self.is_ready():
            cached_commit = self._meta.get("git_commit", "")
            current = self._git_head()
            if cached_commit and cached_commit == current:
                logger.info("Vector store: index is up to date (commit %s)", cached_commit[:8])
                return len(self._chunks)

        t0 = time.monotonic()
        logger.info("Vector store: building index for %s", self.repo_path)

        self._chunks.clear()
        files = self._discover_files()
        logger.info("Vector store: discovered %d parseable files", len(files))

        for fpath in files:
            chunks = self._chunk_file(fpath)
            self._chunks.extend(chunks)

        logger.info("Vector store: created %d chunks from %d files", len(self._chunks), len(files))

        # Build TF-IDF index (always works, pure Python)
        self._build_tfidf_index(self._chunks)

        # Optionally build embeddings
        self._try_build_embeddings()

        # Save to disk
        self._save_cache(len(files))

        elapsed = time.monotonic() - t0
        logger.info("Vector store: built in %.1fs — %d chunks", elapsed, len(self._chunks))
        return len(self._chunks)

    def update(self) -> int:
        """Incremental update — only re-index files changed since last build.

        Uses git diff if available, otherwise falls back to mtime comparison.
        Returns the number of re-indexed chunks.
        """
        if not self.is_ready():
            return self.build()

        old_commit = self._meta.get("git_commit", "")
        new_commit = self._git_head()

        if not new_commit or new_commit == old_commit:
            logger.debug("Vector store: no changes detected")
            return 0

        changed_files = self._git_changed_files(old_commit, new_commit) if old_commit else []

        if not changed_files and old_commit:
            self._meta["git_commit"] = new_commit
            self._save_meta()
            return 0

        # Too many changes — full rebuild
        if not old_commit or len(changed_files) > 200:
            return self.build(force=True)

        t0 = time.monotonic()
        logger.info("Vector store: incremental update (%d files)", len(changed_files))

        # Remove old chunks for changed files
        changed_abs = set()
        for f in changed_files:
            abs_path = os.path.join(self.repo_path, f)
            changed_abs.add(abs_path)

        self._chunks = [c for c in self._chunks if c.file_path not in changed_abs]

        # Re-chunk changed files
        new_chunk_count = 0
        for f in changed_files:
            abs_path = os.path.join(self.repo_path, f)
            if os.path.exists(abs_path) and self._is_parseable(abs_path):
                new_chunks = self._chunk_file(abs_path)
                self._chunks.extend(new_chunks)
                new_chunk_count += len(new_chunks)

        # Rebuild TF-IDF
        self._build_tfidf_index(self._chunks)
        self._try_build_embeddings()

        file_count = len(set(c.file_path for c in self._chunks))
        self._save_cache(file_count)

        elapsed = time.monotonic() - t0
        logger.info("Vector store: updated in %.1fs (%d new chunks)", elapsed, new_chunk_count)
        return new_chunk_count

    def query(self, text: str, top_k: int = 10) -> list[tuple[CodeChunk, float]]:
        """Search for chunks relevant to the query text.

        If embeddings are available, uses cosine similarity on embeddings.
        Falls back to TF-IDF cosine similarity (always works, no deps).

        Returns list of (chunk, score) tuples sorted by relevance.
        """
        if not self._chunks:
            return []

        # Try embeddings first
        if self._embeddings is not None and self._embed_model is not None:
            try:
                results = self._embedding_query(text, top_k)
                if results:
                    return results
            except Exception as e:
                logger.debug("Embedding query failed, falling back to TF-IDF: %s", e)

        # TF-IDF fallback (always available)
        return self._tfidf_query(text, top_k)

    def is_ready(self) -> bool:
        """True if the index has been built and has chunks."""
        return bool(self._chunks)

    def stats(self) -> dict:
        """Return index statistics."""
        file_set = set(c.file_path for c in self._chunks) if self._chunks else set()
        return {
            "chunk_count": len(self._chunks),
            "file_count": len(file_set),
            "last_updated": self._meta.get("last_updated", ""),
            "has_embeddings": self._embeddings is not None,
            "git_commit": self._meta.get("git_commit", "")[:8] if self._meta.get("git_commit") else "",
            "vocab_size": len(self._idf),
            "repo_path": self.repo_path,
        }

    # -------------------------------------------------------------------
    # Chunking
    # -------------------------------------------------------------------

    def _chunk_file(self, file_path: str) -> list[CodeChunk]:
        """Chunk a file by function/class boundaries, fallback to sliding window."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            return []

        if not content.strip():
            return []

        lines = content.splitlines()
        rel_path = self._relative(file_path)

        # Detect language
        ext = Path(file_path).suffix.lower()
        lang = self._ext_to_lang(ext)

        # Try parser-based chunking first
        chunks = self._chunk_by_symbols(file_path, lines, rel_path, lang)
        if chunks:
            return chunks

        # Fallback: sliding window
        return self._chunk_sliding_window(file_path, lines, rel_path, lang)

    def _chunk_by_symbols(
        self, file_path: str, lines: list[str], rel_path: str, lang: str
    ) -> list[CodeChunk]:
        """Try to chunk by function/class boundaries using the parser."""
        try:
            from code_agents.parsers import parse_file
            module = parse_file(file_path)
        except Exception:
            return []

        if not module.symbols:
            return []

        chunks: list[CodeChunk] = []
        # Sort symbols by line number
        symbols = sorted(module.symbols, key=lambda s: s.line_number)

        for i, sym in enumerate(symbols):
            if sym.kind not in ("function", "class", "method"):
                continue

            start = max(0, sym.line_number - 1)  # 0-indexed
            # End = next symbol's start or end of file
            if i + 1 < len(symbols):
                end = symbols[i + 1].line_number - 1
            else:
                end = len(lines)

            # Limit chunk size to 100 lines
            end = min(end, start + 100)

            chunk_content = "\n".join(lines[start:end])
            if chunk_content.strip():
                chunks.append(CodeChunk(
                    file_path=file_path,
                    start_line=start + 1,
                    end_line=end,
                    content=chunk_content,
                    symbol_name=sym.name,
                    language=lang,
                ))

        # If we got very few symbols, also include file-level context
        if len(chunks) < 2 and len(lines) > 10:
            # Add the top of the file (imports, module docstring)
            top_end = min(30, len(lines))
            top_content = "\n".join(lines[:top_end])
            if top_content.strip():
                chunks.insert(0, CodeChunk(
                    file_path=file_path,
                    start_line=1,
                    end_line=top_end,
                    content=top_content,
                    symbol_name="<module>",
                    language=lang,
                ))

        return chunks

    def _chunk_sliding_window(
        self, file_path: str, lines: list[str], rel_path: str, lang: str
    ) -> list[CodeChunk]:
        """Chunk a file using a sliding window approach."""
        chunks: list[CodeChunk] = []
        total = len(lines)

        if total <= _WINDOW_SIZE:
            content = "\n".join(lines)
            if content.strip():
                chunks.append(CodeChunk(
                    file_path=file_path,
                    start_line=1,
                    end_line=total,
                    content=content,
                    language=lang,
                ))
            return chunks

        start = 0
        while start < total:
            end = min(start + _WINDOW_SIZE, total)
            content = "\n".join(lines[start:end])
            if content.strip():
                chunks.append(CodeChunk(
                    file_path=file_path,
                    start_line=start + 1,
                    end_line=end,
                    content=content,
                    language=lang,
                ))
            start += _WINDOW_SIZE - _WINDOW_OVERLAP
            if start >= total:
                break

        return chunks

    # -------------------------------------------------------------------
    # TF-IDF engine (pure Python, no external deps)
    # -------------------------------------------------------------------

    def _build_tfidf_index(self, chunks: list[CodeChunk]) -> None:
        """Build TF-IDF index from chunks.

        Pure Python implementation — no numpy/sklearn needed.
        - Tokenize: split on whitespace + camelCase + snake_case boundaries
        - IDF: log(N / df) where df = number of chunks containing term
        - TF: term frequency in chunk
        """
        if not chunks:
            self._idf = {}
            self._chunk_tfs = []
            self._chunk_norms = []
            return

        n = len(chunks)
        doc_freq: Counter = Counter()
        chunk_tokens: list[list[str]] = []

        # Tokenize all chunks and compute document frequency
        for chunk in chunks:
            # Include file path and symbol name in the token set for better matching
            text = f"{chunk.file_path} {chunk.symbol_name} {chunk.content}"
            tokens = _tokenize(text)
            chunk_tokens.append(tokens)
            # Count unique terms per document
            unique = set(tokens)
            for term in unique:
                doc_freq[term] += 1

        # Compute IDF
        self._idf = {}
        for term, df in doc_freq.items():
            self._idf[term] = math.log(n / df) if df > 0 else 0.0

        # Compute TF vectors and norms
        self._chunk_tfs = []
        self._chunk_norms = []
        for tokens in chunk_tokens:
            tf_counts = Counter(tokens)
            total = len(tokens) if tokens else 1
            tf_vec: dict[str, float] = {}
            for term, count in tf_counts.items():
                tf = count / total
                idf = self._idf.get(term, 0.0)
                tf_vec[term] = tf * idf

            # Precompute norm
            norm = math.sqrt(sum(v * v for v in tf_vec.values())) if tf_vec else 0.0
            self._chunk_tfs.append(tf_vec)
            self._chunk_norms.append(norm)

        logger.debug("TF-IDF index built: %d chunks, %d terms", n, len(self._idf))

    def _tfidf_query(self, text: str, top_k: int) -> list[tuple[CodeChunk, float]]:
        """Query using TF-IDF cosine similarity.

        Returns list of (chunk, score) sorted by descending score.
        """
        if not self._chunk_tfs or not self._idf:
            return []

        # Tokenize query
        query_tokens = _tokenize(text)
        if not query_tokens:
            return []

        # Build query TF-IDF vector
        q_counts = Counter(query_tokens)
        q_total = len(query_tokens)
        q_vec: dict[str, float] = {}
        for term, count in q_counts.items():
            tf = count / q_total
            idf = self._idf.get(term, 0.0)
            if idf > 0:
                q_vec[term] = tf * idf

        if not q_vec:
            return []

        q_norm = math.sqrt(sum(v * v for v in q_vec.values()))
        if q_norm == 0:
            return []

        # Compute cosine similarity with each chunk
        scores: list[tuple[int, float]] = []
        for idx, (chunk_tf, chunk_norm) in enumerate(zip(self._chunk_tfs, self._chunk_norms)):
            if chunk_norm == 0:
                continue
            # Dot product (only iterate query terms for efficiency)
            dot = sum(q_vec[t] * chunk_tf.get(t, 0.0) for t in q_vec)
            if dot > 0:
                sim = dot / (q_norm * chunk_norm)
                scores.append((idx, sim))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scores[:top_k]:
            results.append((self._chunks[idx], score))
        return results

    # -------------------------------------------------------------------
    # Embeddings (optional — requires sentence-transformers)
    # -------------------------------------------------------------------

    def _try_build_embeddings(self) -> None:
        """Try to build embeddings if sentence-transformers is available."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.debug("sentence-transformers not available; using TF-IDF only")
            self._embeddings = None
            self._embed_model = None
            return

        try:
            if self._embed_model is None:
                self._embed_model = SentenceTransformer("all-MiniLM-L6-v2")

            texts = [
                f"{c.symbol_name} {c.content[:500]}" for c in self._chunks
            ]
            self._embeddings = self._embed_model.encode(texts, show_progress_bar=False)
            logger.info("Vector store: built embeddings for %d chunks", len(self._chunks))
        except Exception as e:
            logger.warning("Failed to build embeddings: %s", e)
            self._embeddings = None

    def _embedding_query(self, text: str, top_k: int) -> list[tuple[CodeChunk, float]]:
        """Query using sentence-transformer embeddings + cosine similarity."""
        if self._embeddings is None or self._embed_model is None:
            return []

        try:
            import numpy as np
            q_emb = self._embed_model.encode([text], show_progress_bar=False)[0]
            # Cosine similarity
            norms = np.linalg.norm(self._embeddings, axis=1)
            q_norm = np.linalg.norm(q_emb)
            if q_norm == 0:
                return []
            similarities = np.dot(self._embeddings, q_emb) / (norms * q_norm + 1e-10)
            top_indices = np.argsort(similarities)[-top_k:][::-1]

            results = []
            for idx in top_indices:
                score = float(similarities[idx])
                if score > 0:
                    results.append((self._chunks[idx], score))
            return results
        except Exception as e:
            logger.debug("Embedding query error: %s", e)
            return []

    # -------------------------------------------------------------------
    # File discovery
    # -------------------------------------------------------------------

    def _discover_files(self) -> list[str]:
        """Walk the repo and find parseable source files."""
        files: list[str] = []
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
        """Check if a file should be indexed."""
        ext = Path(fpath).suffix.lower()
        if ext not in _PARSEABLE_EXTS:
            return False
        try:
            if os.path.getsize(fpath) > 500_000:
                return False
        except OSError:
            return False
        return True

    def _load_ignore_patterns(self) -> list[str]:
        """Load custom ignore patterns from .code-agents/.ignore."""
        patterns: list[str] = []
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
    # Git helpers
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
    # Cache persistence
    # -------------------------------------------------------------------

    def _save_cache(self, file_count: int = 0) -> None:
        """Persist index to disk."""
        self._dir.mkdir(parents=True, exist_ok=True)

        self._meta["git_commit"] = self._git_head()
        self._meta["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._meta["repo_path"] = self.repo_path
        self._meta["chunk_count"] = len(self._chunks)
        self._meta["file_count"] = file_count

        try:
            # Save chunks
            chunks_data = [asdict(c) for c in self._chunks]
            with open(self._chunks_path, "w") as f:
                json.dump(chunks_data, f, separators=(",", ":"))

            # Save TF-IDF index
            tfidf_data = {
                "idf": self._idf,
                "chunk_tfs": self._chunk_tfs,
                "chunk_norms": self._chunk_norms,
            }
            with open(self._tfidf_path, "w") as f:
                json.dump(tfidf_data, f, separators=(",", ":"))

            self._save_meta()
            logger.debug("Vector store: cache saved to %s", self._dir)
        except OSError as e:
            logger.warning("Failed to save vector store cache: %s", e)

    def _save_meta(self) -> None:
        """Save only meta.json."""
        try:
            with open(self._meta_path, "w") as f:
                json.dump(self._meta, f, indent=2)
        except OSError:
            pass

    def _load_cache(self) -> None:
        """Load index from disk cache if available."""
        if not self._meta_path.exists():
            return

        try:
            with open(self._meta_path) as f:
                self._meta = json.load(f)

            if self._chunks_path.exists():
                with open(self._chunks_path) as f:
                    chunks_data = json.load(f)
                    self._chunks = [CodeChunk(**d) for d in chunks_data]

            if self._tfidf_path.exists():
                with open(self._tfidf_path) as f:
                    tfidf_data = json.load(f)
                    self._idf = tfidf_data.get("idf", {})
                    self._chunk_tfs = tfidf_data.get("chunk_tfs", [])
                    self._chunk_norms = tfidf_data.get("chunk_norms", [])

            logger.info(
                "Vector store: loaded cache (%d chunks, %d terms)",
                len(self._chunks), len(self._idf),
            )
        except (OSError, json.JSONDecodeError, TypeError) as e:
            logger.debug("Failed to load vector store cache: %s", e)

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _relative(self, fpath: str) -> str:
        """Convert absolute path to relative (from repo root)."""
        try:
            return os.path.relpath(fpath, self.repo_path)
        except ValueError:
            return fpath

    @staticmethod
    def _ext_to_lang(ext: str) -> str:
        """Map file extension to language name."""
        mapping = {
            ".py": "python", ".js": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "typescript", ".java": "java",
            ".go": "go", ".rs": "rust", ".rb": "ruby", ".c": "c",
            ".cpp": "cpp", ".h": "c", ".hpp": "cpp", ".cs": "csharp",
            ".swift": "swift", ".kt": "kotlin", ".scala": "scala",
            ".php": "php",
        }
        return mapping.get(ext, "")


# ---------------------------------------------------------------------------
# RAG Context Injector
# ---------------------------------------------------------------------------

class RAGContextInjector:
    """High-level interface for injecting RAG context into AI prompts."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self._store = VectorStore(repo_path)

    @property
    def store(self) -> VectorStore:
        """Access the underlying VectorStore."""
        return self._store

    def get_context(self, user_message: str, max_tokens: int = 1500) -> str:
        """Query the vector store and format relevant chunks for prompt injection.

        Returns a formatted block like:
            --- Relevant Code ---
            file.py (lines 10-30, score: 0.85):
            <code>
            --- End Relevant Code ---

        Returns empty string if the store is not ready or no results found.
        """
        if not self._store.is_ready():
            return ""

        results = self._store.query(user_message, top_k=10)
        if not results:
            return ""

        max_chars = max_tokens * 4  # ~4 chars per token estimate
        return self.format_chunks(results, max_chars)

    def format_chunks(self, chunks: list[tuple[CodeChunk, float]], max_chars: int) -> str:
        """Format search results into a context block respecting max_chars.

        Each chunk is formatted as:
            file_path (lines N-M, score: X.XX):
            ```language
            <content>
            ```
        """
        if not chunks:
            return ""

        lines: list[str] = ["--- Relevant Code ---"]
        chars = 30  # header + footer overhead

        for chunk, score in chunks:
            rel_path = os.path.relpath(chunk.file_path, self.repo_path) \
                if os.path.isabs(chunk.file_path) else chunk.file_path

            header = f"{rel_path} (lines {chunk.start_line}-{chunk.end_line}"
            if chunk.symbol_name:
                header += f", {chunk.symbol_name}"
            header += f", score: {score:.2f}):"

            lang_tag = chunk.language or ""
            block = f"{header}\n```{lang_tag}\n{chunk.content}\n```"

            if chars + len(block) + 1 > max_chars:
                # Try to fit a truncated version
                remaining = max_chars - chars - len(header) - 20
                if remaining > 100:
                    truncated_content = chunk.content[:remaining] + "\n... (truncated)"
                    block = f"{header}\n```{lang_tag}\n{truncated_content}\n```"
                else:
                    break

            lines.append(block)
            chars += len(block) + 1

        lines.append("--- End Relevant Code ---")
        return "\n".join(lines)
