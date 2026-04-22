"""Tests for code_agents.knowledge_graph — KnowledgeGraph class."""

import os
import shutil
import tempfile
import unittest

from code_agents.knowledge.knowledge_graph import KnowledgeGraph, _repo_hash


class TestRepoHash(unittest.TestCase):
    """Test the _repo_hash() utility function."""

    def test_deterministic(self):
        h1 = _repo_hash("/tmp/my-repo")
        h2 = _repo_hash("/tmp/my-repo")
        self.assertEqual(h1, h2)

    def test_different_paths_different_hashes(self):
        h1 = _repo_hash("/tmp/repo-a")
        h2 = _repo_hash("/tmp/repo-b")
        self.assertNotEqual(h1, h2)

    def test_returns_12_char_hex(self):
        h = _repo_hash("/tmp/some-repo")
        self.assertEqual(len(h), 12)
        # Should be valid hex
        int(h, 16)


class _TempRepoMixin:
    """Mixin that creates a temporary directory with Python files for testing."""

    def _create_temp_repo(self):
        """Create a temp directory with interconnected Python files."""
        tmpdir = tempfile.mkdtemp(prefix="kg_test_")

        # File A: imports B
        with open(os.path.join(tmpdir, "module_a.py"), "w") as f:
            f.write(
                '''import module_b


class ServiceA:
    """Main service."""

    def run(self):
        return module_b.helper()


def entry_point():
    """Start the app."""
    svc = ServiceA()
    return svc.run()
'''
            )

        # File B: standalone
        with open(os.path.join(tmpdir, "module_b.py"), "w") as f:
            f.write(
                '''def helper():
    """Help with things."""
    return 42


def utility(x: int) -> str:
    """Convert x to string."""
    return str(x)
'''
            )

        # File C: imports A
        with open(os.path.join(tmpdir, "module_c.py"), "w") as f:
            f.write(
                '''from module_a import ServiceA


def orchestrate():
    """Orchestrate services."""
    return ServiceA().run()
'''
            )

        return tmpdir

    def _cleanup_singleton(self, repo_path):
        """Remove a singleton instance to avoid cross-test pollution."""
        key = os.path.abspath(repo_path)
        KnowledgeGraph._instances.pop(key, None)


class TestKnowledgeGraphSingleton(unittest.TestCase, _TempRepoMixin):
    """Test KnowledgeGraph singleton behaviour."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="kg_singleton_")
        # Write at least one file so the dir exists
        with open(os.path.join(self.tmpdir, "dummy.py"), "w") as f:
            f.write("x = 1\n")

    def tearDown(self):
        self._cleanup_singleton(self.tmpdir)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_same_path_returns_same_instance(self):
        kg1 = KnowledgeGraph(self.tmpdir)
        kg2 = KnowledgeGraph(self.tmpdir)
        self.assertIs(kg1, kg2)

    def test_different_path_returns_different_instance(self):
        tmpdir2 = tempfile.mkdtemp(prefix="kg_singleton2_")
        try:
            kg1 = KnowledgeGraph(self.tmpdir)
            kg2 = KnowledgeGraph(tmpdir2)
            self.assertIsNot(kg1, kg2)
        finally:
            self._cleanup_singleton(tmpdir2)
            shutil.rmtree(tmpdir2, ignore_errors=True)


class TestKnowledgeGraphBuild(unittest.TestCase, _TempRepoMixin):
    """Test KnowledgeGraph.build()."""

    def setUp(self):
        self.tmpdir = self._create_temp_repo()

    def tearDown(self):
        self._cleanup_singleton(self.tmpdir)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_build_populates_graph(self):
        kg = KnowledgeGraph(self.tmpdir)
        kg.build()
        stats = kg.get_stats()
        self.assertGreater(stats["files"], 0)
        self.assertGreater(stats["symbols"], 0)

    def test_build_finds_all_files(self):
        kg = KnowledgeGraph(self.tmpdir)
        kg.build()
        stats = kg.get_stats()
        self.assertEqual(stats["files"], 3)

    def test_is_ready_after_build(self):
        kg = KnowledgeGraph(self.tmpdir)
        self.assertFalse(kg.is_ready)
        kg.build()
        self.assertTrue(kg.is_ready)

    def test_build_creates_edges(self):
        kg = KnowledgeGraph(self.tmpdir)
        kg.build()
        stats = kg.get_stats()
        # module_a imports module_b, module_c imports module_a
        self.assertGreater(stats["edges"], 0)


class TestKnowledgeGraphQuery(unittest.TestCase, _TempRepoMixin):
    """Test KnowledgeGraph.query()."""

    def setUp(self):
        self.tmpdir = self._create_temp_repo()
        self.kg = KnowledgeGraph(self.tmpdir)
        self.kg.build()

    def tearDown(self):
        self._cleanup_singleton(self.tmpdir)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_query_finds_symbols(self):
        results = self.kg.query(["helper"])
        self.assertGreater(len(results), 0)
        names = [r["name"] for r in results]
        self.assertIn("helper", names)

    def test_query_finds_class(self):
        results = self.kg.query(["ServiceA"])
        self.assertGreater(len(results), 0)
        names = [r["name"] for r in results]
        self.assertIn("ServiceA", names)

    def test_query_no_match(self):
        results = self.kg.query(["nonexistent_symbol_xyz"])
        self.assertEqual(len(results), 0)

    def test_query_respects_max_results(self):
        results = self.kg.query(["e"], max_results=2)  # broad keyword
        self.assertLessEqual(len(results), 2)


class TestKnowledgeGraphBlastRadius(unittest.TestCase, _TempRepoMixin):
    """Test KnowledgeGraph.blast_radius()."""

    def setUp(self):
        self.tmpdir = self._create_temp_repo()
        self.kg = KnowledgeGraph(self.tmpdir)
        self.kg.build()

    def tearDown(self):
        self._cleanup_singleton(self.tmpdir)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_blast_radius_includes_self(self):
        module_b_path = os.path.join(self.tmpdir, "module_b.py")
        affected = self.kg.blast_radius(module_b_path)
        self.assertIn("module_b.py", affected)

    def test_blast_radius_includes_importers(self):
        # module_a imports module_b, so changing module_b affects module_a
        module_b_path = os.path.join(self.tmpdir, "module_b.py")
        affected = self.kg.blast_radius(module_b_path)
        self.assertIn("module_a.py", affected)

    def test_blast_radius_transitive(self):
        # module_c imports module_a imports module_b
        # With depth=2, changing module_b should reach module_c
        module_b_path = os.path.join(self.tmpdir, "module_b.py")
        affected = self.kg.blast_radius(module_b_path, depth=2)
        self.assertIn("module_c.py", affected)


class TestGetContextForPrompt(unittest.TestCase, _TempRepoMixin):
    """Test KnowledgeGraph.get_context_for_prompt()."""

    def setUp(self):
        self.tmpdir = self._create_temp_repo()
        self.kg = KnowledgeGraph(self.tmpdir)
        self.kg.build()

    def tearDown(self):
        self._cleanup_singleton(self.tmpdir)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_nonempty_string(self):
        ctx = self.kg.get_context_for_prompt("helper function")
        self.assertIsInstance(ctx, str)
        self.assertGreater(len(ctx), 0)

    def test_contains_markers(self):
        ctx = self.kg.get_context_for_prompt("ServiceA")
        self.assertIn("--- Project Structure (auto-indexed) ---", ctx)
        self.assertIn("--- End Project Structure ---", ctx)

    def test_summary_fallback_for_no_keywords(self):
        # Very short words (<=2 chars) are filtered out; falls back to summary
        ctx = self.kg.get_context_for_prompt("a b c")
        self.assertIn("--- Project Structure (auto-indexed) ---", ctx)

    def test_empty_when_no_nodes(self):
        tmpdir2 = tempfile.mkdtemp(prefix="kg_empty_")
        try:
            kg2 = KnowledgeGraph(tmpdir2)
            ctx = kg2.get_context_for_prompt("anything")
            self.assertEqual(ctx, "")
        finally:
            self._cleanup_singleton(tmpdir2)
            shutil.rmtree(tmpdir2, ignore_errors=True)


class TestIsStale(unittest.TestCase, _TempRepoMixin):
    """Test KnowledgeGraph.is_stale()."""

    def setUp(self):
        # Use a non-git temp directory so git HEAD returns empty string
        self.tmpdir = tempfile.mkdtemp(prefix="kg_stale_")
        with open(os.path.join(self.tmpdir, "f.py"), "w") as f:
            f.write("x = 1\n")

    def tearDown(self):
        self._cleanup_singleton(self.tmpdir)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_stale_without_git(self):
        kg = KnowledgeGraph(self.tmpdir)
        # No cached commit and git HEAD returns "" — should be stale
        self.assertTrue(kg.is_stale())


class TestGetStats(unittest.TestCase, _TempRepoMixin):
    """Test KnowledgeGraph.get_stats()."""

    def setUp(self):
        self.tmpdir = self._create_temp_repo()
        self.kg = KnowledgeGraph(self.tmpdir)
        self.kg.build()

    def tearDown(self):
        self._cleanup_singleton(self.tmpdir)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_stats_structure(self):
        stats = self.kg.get_stats()
        self.assertIn("files", stats)
        self.assertIn("symbols", stats)
        self.assertIn("edges", stats)
        self.assertIn("git_commit", stats)
        self.assertIn("last_build", stats)

    def test_stats_types(self):
        stats = self.kg.get_stats()
        self.assertIsInstance(stats["files"], int)
        self.assertIsInstance(stats["symbols"], int)
        self.assertIsInstance(stats["edges"], int)
        self.assertIsInstance(stats["git_commit"], str)
        self.assertIsInstance(stats["last_build"], str)


if __name__ == "__main__":
    unittest.main()
