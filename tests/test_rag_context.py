"""Tests for code_agents.rag_context — RAG vector store and context injection."""

from __future__ import annotations

import os
import tempfile
import textwrap
from unittest.mock import patch, MagicMock

import pytest

from code_agents.knowledge.rag_context import (
    CodeChunk,
    RAGContextInjector,
    VectorStore,
    _tokenize,
    _repo_hash,
    VECTOR_STORE_DIR,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_repo(tmp_path):
    """Create a minimal temporary repo with Python files."""
    # Create a .git dir so it's recognized as a repo
    (tmp_path / ".git").mkdir()

    # Create Python files
    (tmp_path / "app.py").write_text(textwrap.dedent("""\
        \"\"\"Main application module.\"\"\"

        import os
        import sys


        class Application:
            \"\"\"Core application class.\"\"\"

            def __init__(self, name: str):
                self.name = name

            def run(self):
                \"\"\"Run the application.\"\"\"
                print(f"Running {self.name}")

            def shutdown(self):
                \"\"\"Shutdown the application gracefully.\"\"\"
                print("Shutting down")


        def create_app(name: str = "default") -> Application:
            \"\"\"Factory function to create an application.\"\"\"
            return Application(name)


        def main():
            app = create_app("my-app")
            app.run()
    """))

    (tmp_path / "utils.py").write_text(textwrap.dedent("""\
        \"\"\"Utility functions.\"\"\"

        import hashlib
        from pathlib import Path


        def compute_hash(data: str) -> str:
            \"\"\"Compute SHA256 hash of a string.\"\"\"
            return hashlib.sha256(data.encode()).hexdigest()


        def read_file(path: str) -> str:
            \"\"\"Read file contents safely.\"\"\"
            try:
                return Path(path).read_text()
            except OSError:
                return ""


        class FileProcessor:
            \"\"\"Process files in a directory.\"\"\"

            def __init__(self, directory: str):
                self.directory = directory

            def process_all(self):
                \"\"\"Process all files in the directory.\"\"\"
                for f in Path(self.directory).iterdir():
                    if f.is_file():
                        self.process_one(f)

            def process_one(self, path: Path):
                \"\"\"Process a single file.\"\"\"
                content = path.read_text()
                return compute_hash(content)
    """))

    # A non-Python file that should still be indexed
    (tmp_path / "config.js").write_text(textwrap.dedent("""\
        // Configuration module
        const DEFAULT_PORT = 8080;

        function getConfig() {
            return {
                port: DEFAULT_PORT,
                host: "localhost",
            };
        }

        function validateConfig(config) {
            if (!config.port) throw new Error("port required");
            return true;
        }

        module.exports = { getConfig, validateConfig };
    """))

    # A directory that should be skipped
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.py").write_text("should_skip = True")

    return tmp_path


@pytest.fixture
def store(tmp_repo):
    """Create a VectorStore for the tmp repo."""
    return VectorStore(str(tmp_repo))


# ---------------------------------------------------------------------------
# TestChunking
# ---------------------------------------------------------------------------

class TestChunking:
    """Verify function/class boundary splitting."""

    def test_chunk_file_python(self, store, tmp_repo):
        """Python files should be chunked by function/class boundaries."""
        chunks = store._chunk_file(str(tmp_repo / "app.py"))
        assert len(chunks) > 0
        # Should find Application class, create_app, main, etc.
        symbol_names = [c.symbol_name for c in chunks if c.symbol_name]
        assert any("Application" in s or "create_app" in s or "main" in s for s in symbol_names)

    def test_chunk_file_has_content(self, store, tmp_repo):
        """Each chunk should have non-empty content."""
        chunks = store._chunk_file(str(tmp_repo / "app.py"))
        for chunk in chunks:
            assert chunk.content.strip()
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line

    def test_chunk_file_language(self, store, tmp_repo):
        """Chunks should have the correct language tag."""
        py_chunks = store._chunk_file(str(tmp_repo / "app.py"))
        for c in py_chunks:
            assert c.language == "python"

        js_chunks = store._chunk_file(str(tmp_repo / "config.js"))
        for c in js_chunks:
            assert c.language == "javascript"

    def test_sliding_window_fallback(self, store, tmp_repo):
        """If parser fails, sliding window should be used."""
        # Create a file that the parser can't handle well
        big_file = tmp_repo / "data.py"
        big_file.write_text("\n".join(f"line_{i} = {i}" for i in range(100)))

        chunks = store._chunk_sliding_window(
            str(big_file),
            [f"line_{i} = {i}" for i in range(100)],
            "data.py",
            "python",
        )
        assert len(chunks) >= 2  # 100 lines / 50 window = at least 2

    def test_empty_file_no_chunks(self, store, tmp_repo):
        """Empty files should return no chunks."""
        empty = tmp_path = tmp_repo / "empty.py"
        empty.write_text("")
        chunks = store._chunk_file(str(empty))
        assert chunks == []

    def test_skips_node_modules(self, store, tmp_repo):
        """Files in node_modules should not be discovered."""
        files = store._discover_files()
        for f in files:
            # Check that no file is under a node_modules directory
            rel = os.path.relpath(f, str(tmp_repo))
            assert not rel.startswith("node_modules")


# ---------------------------------------------------------------------------
# TestTfIdf
# ---------------------------------------------------------------------------

class TestTfIdf:
    """Test TF-IDF index building and querying."""

    def test_tokenize_camel_case(self):
        """camelCase should be split into tokens."""
        tokens = _tokenize("computeHash")
        assert "compute" in tokens
        assert "hash" in tokens

    def test_tokenize_snake_case(self):
        """snake_case should be split into tokens."""
        tokens = _tokenize("compute_hash")
        assert "compute" in tokens
        assert "hash" in tokens

    def test_tokenize_filters_stop_words(self):
        """Stop words should be filtered out."""
        tokens = _tokenize("def create_app(name: str) -> Application")
        assert "def" not in tokens
        assert "str" not in tokens
        assert "create" in tokens
        assert "app" in tokens

    def test_build_tfidf_index(self, store):
        """TF-IDF index should be built from chunks."""
        chunks = [
            CodeChunk("a.py", 1, 10, "def compute_hash(data): return hash(data)", "compute_hash", "python"),
            CodeChunk("b.py", 1, 10, "class Application: pass", "Application", "python"),
            CodeChunk("c.py", 1, 10, "def read_file(path): return open(path).read()", "read_file", "python"),
        ]
        store._build_tfidf_index(chunks)

        assert len(store._idf) > 0
        assert len(store._chunk_tfs) == 3
        assert len(store._chunk_norms) == 3

    def test_tfidf_query_returns_relevant(self, store):
        """Query should return the most relevant chunk."""
        chunks = [
            CodeChunk("a.py", 1, 10, "def compute_hash(data): return hashlib.sha256(data).hexdigest()", "compute_hash", "python"),
            CodeChunk("b.py", 1, 10, "class UserInterface: def render(self): pass", "UserInterface", "python"),
            CodeChunk("c.py", 1, 10, "def read_config(path): return json.load(open(path))", "read_config", "python"),
        ]
        store._chunks = chunks
        store._build_tfidf_index(chunks)

        results = store._tfidf_query("hash computation sha256", top_k=3)
        assert len(results) > 0
        # The hash-related chunk should score highest
        best_chunk, best_score = results[0]
        assert "hash" in best_chunk.content.lower() or "hash" in best_chunk.symbol_name.lower()
        assert best_score > 0

    def test_tfidf_query_empty_returns_empty(self, store):
        """Empty query or empty index should return empty list."""
        assert store._tfidf_query("", top_k=5) == []
        assert store._tfidf_query("anything", top_k=5) == []


# ---------------------------------------------------------------------------
# TestVectorStore
# ---------------------------------------------------------------------------

class TestVectorStore:
    """Build + query roundtrip with a temp repo."""

    def test_build_and_query(self, store, tmp_repo):
        """Full build + query should return relevant results."""
        with patch.object(store, '_git_head', return_value="abc123"):
            chunk_count = store.build(force=True)

        assert chunk_count > 0
        assert store.is_ready()

        results = store.query("compute hash sha256")
        assert len(results) > 0
        # Should find the utils.py compute_hash function
        found_hash = any("hash" in c.content.lower() or "hash" in c.symbol_name.lower()
                         for c, _ in results)
        assert found_hash

    def test_build_returns_chunk_count(self, store, tmp_repo):
        """Build should return the total number of chunks."""
        with patch.object(store, '_git_head', return_value="abc123"):
            count = store.build(force=True)
        assert isinstance(count, int)
        assert count > 0

    def test_query_application(self, store, tmp_repo):
        """Should find Application class when queried."""
        with patch.object(store, '_git_head', return_value="abc123"):
            store.build(force=True)

        results = store.query("Application class run shutdown")
        assert len(results) > 0
        found_app = any("Application" in c.symbol_name or "Application" in c.content
                        for c, _ in results)
        assert found_app

    def test_not_ready_before_build(self, tmp_repo):
        """Store should not be ready before build."""
        s = VectorStore(str(tmp_repo))
        # Clear any loaded cache
        s._chunks = []
        assert not s.is_ready()

    def test_skips_hidden_and_vendor_dirs(self, store, tmp_repo):
        """Should not index files in hidden/vendor directories."""
        with patch.object(store, '_git_head', return_value="abc123"):
            store.build(force=True)
        for chunk in store._chunks:
            assert "node_modules" not in chunk.file_path
            assert "__pycache__" not in chunk.file_path


# ---------------------------------------------------------------------------
# TestRAGInjector
# ---------------------------------------------------------------------------

class TestRAGInjector:
    """Test RAGContextInjector formatting."""

    def test_format_chunks_respects_max_chars(self):
        """Formatted output should not exceed max_chars."""
        injector = RAGContextInjector("/tmp/fake")

        chunks = [
            (CodeChunk("/tmp/fake/a.py", 1, 20, "x" * 500, "func_a", "python"), 0.9),
            (CodeChunk("/tmp/fake/b.py", 1, 20, "y" * 500, "func_b", "python"), 0.8),
            (CodeChunk("/tmp/fake/c.py", 1, 20, "z" * 500, "func_c", "python"), 0.7),
        ]

        result = injector.format_chunks(chunks, max_chars=600)
        assert len(result) <= 700  # some overhead is OK
        assert "--- Relevant Code ---" in result
        assert "--- End Relevant Code ---" in result

    def test_format_chunks_includes_metadata(self):
        """Output should include file path, lines, score."""
        injector = RAGContextInjector("/tmp/fake")

        chunks = [
            (CodeChunk("/tmp/fake/utils.py", 10, 30, "def compute_hash(): pass", "compute_hash", "python"), 0.85),
        ]

        result = injector.format_chunks(chunks, max_chars=5000)
        assert "utils.py" in result
        assert "lines 10-30" in result
        assert "0.85" in result
        assert "compute_hash" in result

    def test_format_chunks_empty(self):
        """Empty chunk list should return empty string."""
        injector = RAGContextInjector("/tmp/fake")
        assert injector.format_chunks([], max_chars=1000) == ""

    def test_get_context_not_ready(self):
        """get_context should return empty when store not built."""
        injector = RAGContextInjector("/tmp/fake")
        assert injector.get_context("test query") == ""


# ---------------------------------------------------------------------------
# TestStats
# ---------------------------------------------------------------------------

class TestStats:
    """Verify stats dict."""

    def test_stats_empty(self, tmp_repo):
        """Stats on empty store should have zero counts."""
        s = VectorStore(str(tmp_repo))
        s._chunks = []
        st = s.stats()
        assert st["chunk_count"] == 0
        assert st["file_count"] == 0
        assert st["has_embeddings"] is False

    def test_stats_after_build(self, store, tmp_repo):
        """Stats after build should reflect indexed data."""
        with patch.object(store, '_git_head', return_value="abc123"):
            store.build(force=True)

        st = store.stats()
        assert st["chunk_count"] > 0
        assert st["file_count"] > 0
        assert st["vocab_size"] > 0
        assert st["git_commit"] == "abc123"[:8]
        assert isinstance(st["has_embeddings"], bool)

    def test_stats_keys(self, store):
        """Stats should contain all expected keys."""
        st = store.stats()
        expected_keys = {"chunk_count", "file_count", "last_updated",
                         "has_embeddings", "git_commit", "vocab_size", "repo_path"}
        assert expected_keys.issubset(set(st.keys()))


# ---------------------------------------------------------------------------
# TestUpdate
# ---------------------------------------------------------------------------

class TestUpdate:
    """Verify incremental update only re-indexes changed files."""

    def test_update_no_changes(self, store, tmp_repo):
        """Update with no git changes should return 0."""
        with patch.object(store, '_git_head', return_value="abc123"):
            store.build(force=True)

        # Same commit → no changes
        with patch.object(store, '_git_head', return_value="abc123"):
            result = store.update()
        assert result == 0

    def test_update_with_changes(self, store, tmp_repo):
        """Update should re-index only changed files."""
        with patch.object(store, '_git_head', return_value="commit1"):
            store.build(force=True)

        original_count = len(store._chunks)

        # Simulate a change
        (tmp_repo / "utils.py").write_text("def new_function(): pass\n")

        with patch.object(store, '_git_head', return_value="commit2"), \
             patch.object(store, '_git_changed_files', return_value=["utils.py"]):
            result = store.update()

        assert result > 0
        # Chunks should have been updated
        assert store.is_ready()

    def test_update_triggers_full_build_if_not_ready(self, tmp_repo):
        """Update on empty store should trigger full build."""
        s = VectorStore(str(tmp_repo))
        s._chunks = []
        with patch.object(s, '_git_head', return_value="abc123"):
            result = s.update()
        assert result > 0
        assert s.is_ready()


# ---------------------------------------------------------------------------
# TestRepoHash
# ---------------------------------------------------------------------------

class TestRepoHash:
    """Test repo path hashing."""

    def test_deterministic(self):
        """Same path should produce same hash."""
        h1 = _repo_hash("/tmp/my-repo")
        h2 = _repo_hash("/tmp/my-repo")
        assert h1 == h2

    def test_different_paths(self):
        """Different paths should produce different hashes."""
        h1 = _repo_hash("/tmp/repo-a")
        h2 = _repo_hash("/tmp/repo-b")
        assert h1 != h2

    def test_hash_length(self):
        """Hash should be 12 characters."""
        h = _repo_hash("/tmp/repo")
        assert len(h) == 12
