"""Tests for code_agents.agent_corrections — correction store and similarity matching."""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.agent_system.agent_corrections import (
    CorrectionEntry,
    CorrectionStore,
    inject_corrections,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path, agent="code-writer", project=None):
    """Create a CorrectionStore with storage redirected to tmp_path."""
    store = CorrectionStore(agent, project_path=project)
    # Override global dir to tmp_path
    store._global_dir = tmp_path / "global" / "corrections"
    store._global_file = store._global_dir / f"{agent}.jsonl"
    if project:
        proj_dir = Path(project) / ".code-agents" / "corrections"
        store._project_file = proj_dir / f"{agent}.jsonl"
    else:
        store._project_file = None
    return store


# ---------------------------------------------------------------------------
# TestCorrectionStore
# ---------------------------------------------------------------------------

class TestCorrectionStore:
    """Core store operations: record, list, clear."""

    def test_record_writes_valid_jsonl(self, tmp_path):
        store = _make_store(tmp_path)
        entry = store.record("def foo():", "def foo() -> None:", context="refactor.py")

        assert entry.agent == "code-writer"
        assert entry.original == "def foo():"
        assert entry.expected == "def foo() -> None:"
        assert entry.context == "refactor.py"
        assert entry.similarity_key  # not empty

        # Verify JSONL file
        lines = store._global_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["agent"] == "code-writer"
        assert data["original"] == "def foo():"

    def test_record_multiple_entries(self, tmp_path):
        store = _make_store(tmp_path)
        store.record("a", "b")
        store.record("c", "d")
        store.record("e", "f")

        entries = store.list_all()
        assert len(entries) == 3
        assert entries[0].original == "a"
        assert entries[2].original == "e"

    def test_record_writes_to_project_store(self, tmp_path):
        proj = tmp_path / "myproject"
        proj.mkdir()
        store = _make_store(tmp_path, project=str(proj))
        store.record("x", "y", context="main.py")

        # Global file exists
        assert store._global_file.is_file()
        # Project file exists
        assert store._project_file.is_file()

        proj_lines = store._project_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(proj_lines) == 1

    def test_list_all_empty(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.list_all() == []

    def test_clear_returns_count(self, tmp_path):
        store = _make_store(tmp_path)
        store.record("a", "b")
        store.record("c", "d")

        count = store.clear()
        assert count == 2
        assert store.list_all() == []
        assert not store._global_file.exists()

    def test_clear_empty_returns_zero(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.clear() == 0

    def test_clear_both_stores(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        store = _make_store(tmp_path, project=str(proj))
        store.record("a", "b")

        count = store.clear()
        # Both global and project had 1 entry each
        assert count == 2
        assert not store._global_file.exists()
        assert not store._project_file.exists()

    def test_invalid_jsonl_line_skipped(self, tmp_path):
        store = _make_store(tmp_path)
        store.record("valid", "entry")
        # Append invalid line
        with open(store._global_file, "a", encoding="utf-8") as f:
            f.write("not-valid-json\n")

        entries = store.list_all()
        assert len(entries) == 1
        assert entries[0].original == "valid"


# ---------------------------------------------------------------------------
# TestSimilarity
# ---------------------------------------------------------------------------

class TestSimilarity:
    """Jaccard similarity matching."""

    def test_exact_match(self, tmp_path):
        store = _make_store(tmp_path)
        store.record("add logging to function", "add structured logging to function", context="utils.py")

        results = store.find_similar("add logging to function")
        assert len(results) == 1
        assert results[0].original == "add logging to function"

    def test_partial_match(self, tmp_path):
        store = _make_store(tmp_path)
        store.record(
            "write unit test for parser",
            "write pytest unit test for AST parser",
            context="tests/",
        )

        results = store.find_similar("write unit test for the new parser module")
        assert len(results) >= 1
        assert results[0].original == "write unit test for parser"

    def test_no_match_below_threshold(self, tmp_path):
        store = _make_store(tmp_path)
        store.record("deploy kubernetes pods", "deploy k8s pods with resource limits")

        results = store.find_similar("refactor database migrations")
        assert len(results) == 0

    def test_max_results_respected(self, tmp_path):
        store = _make_store(tmp_path)
        for i in range(10):
            store.record(f"fix bug in module {i}", f"fix bug in module {i} with tests")

        results = store.find_similar("fix bug in module", max_results=3)
        assert len(results) == 3

    def test_empty_query(self, tmp_path):
        store = _make_store(tmp_path)
        store.record("something", "something else")
        assert store.find_similar("") == []

    def test_custom_threshold(self, tmp_path):
        store = CorrectionStore("test-agent", similarity_threshold=0.8)
        store._global_dir = tmp_path / "global" / "corrections"
        store._global_file = store._global_dir / "test-agent.jsonl"
        store._project_file = None

        store.record("alpha beta gamma", "alpha beta gamma delta")
        # Low overlap query should not match with high threshold
        results = store.find_similar("alpha zeta omega")
        assert len(results) == 0


# ---------------------------------------------------------------------------
# TestNormalize
# ---------------------------------------------------------------------------

class TestNormalize:
    """Text normalization for similarity keys."""

    def test_lowercase(self, tmp_path):
        store = _make_store(tmp_path)
        assert store._normalize("Hello World") == "hello world"

    def test_strip_whitespace(self, tmp_path):
        store = _make_store(tmp_path)
        assert store._normalize("  hello  ") == "hello"

    def test_collapse_multiline(self, tmp_path):
        store = _make_store(tmp_path)
        result = store._normalize("line one\nline two\nline three")
        assert "\n" not in result
        assert result == "line one line two line three"

    def test_remove_punctuation(self, tmp_path):
        store = _make_store(tmp_path)
        result = store._normalize("hello, world! how's it going?")
        assert "," not in result
        assert "!" not in result
        assert "'" not in result
        assert "?" not in result

    def test_collapse_whitespace(self, tmp_path):
        store = _make_store(tmp_path)
        result = store._normalize("too   many    spaces")
        assert result == "too many spaces"


# ---------------------------------------------------------------------------
# TestFormatForPrompt
# ---------------------------------------------------------------------------

class TestFormatForPrompt:
    """Prompt formatting with char limits."""

    def test_no_corrections_returns_empty(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.format_for_prompt("anything") == ""

    def test_includes_relevant_corrections(self, tmp_path):
        store = _make_store(tmp_path)
        store.record("use print for logging output", "use logger.info instead of print", context="app.py")

        result = store.format_for_prompt("use print for logging in the module")
        assert "--- Past Corrections ---" in result
        assert "--- End Corrections ---" in result
        assert "use print for logging output" in result
        assert "use logger.info instead of print" in result

    def test_respects_max_chars(self, tmp_path):
        store = _make_store(tmp_path)
        for i in range(20):
            store.record(
                f"original text number {i} with some padding words",
                f"expected text number {i} with different padding words",
                context=f"file_{i}.py",
            )

        result = store.format_for_prompt("original text number", max_chars=300)
        assert len(result) <= 400  # some overhead for header/footer
        assert "--- Past Corrections ---" in result

    def test_format_includes_context(self, tmp_path):
        store = _make_store(tmp_path)
        store.record("old code", "new code", context="models.py")

        result = store.format_for_prompt("old code pattern")
        assert "models.py" in result


# ---------------------------------------------------------------------------
# TestInjectCorrections
# ---------------------------------------------------------------------------

class TestInjectCorrections:
    """Top-level inject_corrections function."""

    def test_returns_formatted_string(self, tmp_path):
        with patch("code_agents.agent_system.agent_corrections.GLOBAL_CORRECTIONS_DIR", tmp_path / "corrections"):
            store = CorrectionStore("test-agent")
            store._global_dir = tmp_path / "corrections"
            store._global_file = store._global_dir / "test-agent.jsonl"
            store.record("bad pattern", "good pattern", context="test.py")

            # Now inject_corrections uses global dir
            with patch("code_agents.agent_system.agent_corrections.CorrectionStore") as mock_cls:
                mock_instance = _make_store(tmp_path, agent="test-agent")
                mock_instance.record("bad pattern", "good pattern", context="test.py")
                mock_cls.return_value = mock_instance
                result = inject_corrections("test-agent", "bad pattern")
                assert "Past Corrections" in result

    def test_returns_empty_when_no_matches(self, tmp_path):
        with patch("code_agents.agent_system.agent_corrections.CorrectionStore") as mock_cls:
            mock_instance = _make_store(tmp_path, agent="empty-agent")
            mock_cls.return_value = mock_instance
            result = inject_corrections("empty-agent", "some query")
            assert result == ""

    def test_handles_exceptions_gracefully(self):
        with patch("code_agents.agent_system.agent_corrections.CorrectionStore", side_effect=RuntimeError("boom")):
            result = inject_corrections("broken", "query")
            assert result == ""
