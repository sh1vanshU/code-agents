"""Tests for the smart snippet library."""

from __future__ import annotations

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch

from code_agents.ui.snippet_library import Snippet, SnippetLibrary


@pytest.fixture
def tmp_snippets(tmp_path, monkeypatch):
    """Redirect snippets dir to a temp directory."""
    snippets_dir = tmp_path / "snippets"
    snippets_dir.mkdir()
    monkeypatch.setattr("code_agents.ui.snippet_library._SNIPPETS_DIR", str(snippets_dir))
    return tmp_path


class TestSnippetSave:
    def test_save_basic(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        s = lib.save("retry-logic", "def retry(): pass", language="python", tags=["retry"])
        assert s.name == "retry-logic"
        assert s.language == "python"
        assert "retry" in s.tags

    def test_save_creates_json_file(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        lib.save("my-snippet", "print('hello')", language="python")
        path = Path(str(tmp_snippets)) / "snippets" / "my-snippet.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["name"] == "my-snippet"
        assert data["code"] == "print('hello')"

    def test_save_empty_name_raises(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        with pytest.raises(ValueError, match="name"):
            lib.save("", "code")

    def test_save_empty_code_raises(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        with pytest.raises(ValueError, match="code"):
            lib.save("test", "")

    def test_save_auto_detects_language(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        s = lib.save("pycode", "import os\ndef main(): pass")
        assert s.language == "python"

    def test_save_normalizes_tags(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        s = lib.save("test", "code", tags=["  Retry ", "ASYNC"])
        assert s.tags == ["retry", "async"]


class TestSnippetSearch:
    def test_search_by_name(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        lib.save("retry-backoff", "retry code", language="python", tags=["retry"])
        lib.save("hello-world", "print('hi')", language="python")
        results = lib.search("retry")
        assert len(results) >= 1
        assert results[0].name == "retry-backoff"

    def test_search_by_tag(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        lib.save("s1", "code1", tags=["database"])
        lib.save("s2", "code2", tags=["http"])
        results = lib.search("database")
        assert any(s.name == "s1" for s in results)

    def test_search_with_language_filter(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        lib.save("py-snip", "def x(): pass", language="python")
        lib.save("js-snip", "function x() {}", language="javascript")
        results = lib.search("snip", language="python")
        assert all(s.language == "python" for s in results)

    def test_search_empty_query_returns_all(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        lib.save("s1", "code1")
        lib.save("s2", "code2")
        results = lib.search("")
        assert len(results) == 2

    def test_search_no_results(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        lib.save("s1", "code1")
        results = lib.search("nonexistent_xyz_query")
        assert results == []


class TestSnippetList:
    def test_list_all(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        lib.save("a", "code_a")
        lib.save("b", "code_b")
        snippets = lib.list_snippets()
        assert len(snippets) == 2

    def test_list_by_tag(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        lib.save("s1", "code1", tags=["api"])
        lib.save("s2", "code2", tags=["db"])
        snippets = lib.list_snippets(tag="api")
        assert len(snippets) == 1
        assert snippets[0].name == "s1"

    def test_list_empty(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        assert lib.list_snippets() == []


class TestSnippetDelete:
    def test_delete_existing(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        lib.save("to-delete", "code")
        assert lib.delete("to-delete") is True
        assert lib.get("to-delete") is None

    def test_delete_nonexistent(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        assert lib.delete("does-not-exist") is False


class TestSnippetAdapt:
    def test_adapt_returns_code(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        snippet = Snippet(name="test", language="python", code="def x(): pass", tags=[])
        result = lib._adapt_to_project(snippet)
        assert "def x()" in result

    def test_adapt_with_no_project_files(self, tmp_snippets):
        lib = SnippetLibrary(cwd=str(tmp_snippets))
        snippet = Snippet(name="test", language="python", code="x = 1", tags=[])
        result = lib._adapt_to_project(snippet)
        assert result == "x = 1"


class TestSnippetHelpers:
    def test_safe_name(self):
        assert SnippetLibrary._safe_name("My Snippet!") == "my_snippet_"
        assert SnippetLibrary._safe_name("retry-logic") == "retry-logic"

    def test_detect_language_python(self):
        assert SnippetLibrary._detect_language("import os\ndef main(): pass") == "python"

    def test_detect_language_javascript(self):
        assert SnippetLibrary._detect_language("function hello() {}") == "javascript"

    def test_detect_language_fallback(self):
        assert SnippetLibrary._detect_language("random text") == "text"

    def test_score_match_exact_name(self):
        s = Snippet(name="retry", language="python", code="code", tags=["http"])
        assert SnippetLibrary._score_match(s, "retry") >= 100

    def test_score_match_partial(self):
        s = Snippet(name="retry-backoff", language="python", code="code", tags=[])
        score = SnippetLibrary._score_match(s, "retry")
        assert score > 0
