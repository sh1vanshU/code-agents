"""Tests for knowledge_base.py — searchable team knowledge base."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.knowledge.knowledge_base import (
    KBEntry,
    KnowledgeBase,
    format_kb_results,
)


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temp repo directory with sample files."""
    # Python file with code comments
    py_file = tmp_path / "main.py"
    py_file.write_text(
        "# TODO: refactor the payment module\n"
        "def process():\n"
        "    # FIXME: handle edge case for null amount\n"
        "    pass\n"
        "# NOTE: auth token expires every 24h\n"
    )

    # Java file with comments
    java_dir = tmp_path / "src"
    java_dir.mkdir()
    java_file = java_dir / "App.java"
    java_file.write_text(
        "// TODO: add retry logic for API calls\n"
        "public class App {\n"
        "    // HACK: temporary workaround for race condition\n"
        "}\n"
    )

    # Markdown doc
    doc = tmp_path / "ARCHITECTURE.md"
    doc.write_text(
        "# Architecture\n\n"
        "The system uses event-driven architecture.\n\n"
        "## Database Layer\n\n"
        "PostgreSQL with read replicas.\n\n"
        "## Auth Module\n\n"
        "JWT-based authentication with refresh tokens.\n"
    )

    return tmp_path


@pytest.fixture
def kb(tmp_repo):
    """Create a KnowledgeBase with no cached index."""
    with patch.object(KnowledgeBase, "_load_index"):
        kb = KnowledgeBase(cwd=str(tmp_repo))
        kb.entries = []
    return kb


class TestExtractTags:
    def test_extracts_known_keywords(self, kb):
        tags = kb._extract_tags("The API uses JWT auth with Redis caching")
        assert "api" in tags
        assert "auth" in tags
        assert "redis" in tags

    def test_no_tags_for_unrelated_text(self, kb):
        tags = kb._extract_tags("Hello world this is a simple string")
        assert tags == []

    def test_limits_to_five_tags(self, kb):
        text = "api database auth deploy test bug feature jenkins jira kafka"
        tags = kb._extract_tags(text)
        assert len(tags) <= 5


class TestSearch:
    def test_finds_matching_entries(self, kb):
        kb.entries = [
            KBEntry(title="Payment API docs", source="doc", content="REST endpoints for payments", tags=["api", "payment"]),
            KBEntry(title="Auth module", source="doc", content="JWT authentication flow", tags=["auth"]),
            KBEntry(title="Deploy guide", source="doc", content="How to deploy to production", tags=["deploy"]),
        ]
        results = kb.search("payment")
        assert len(results) >= 1
        assert results[0].title == "Payment API docs"

    def test_title_match_scores_higher(self, kb):
        kb.entries = [
            KBEntry(title="Redis caching", source="doc", content="Uses redis for session cache", tags=["redis"]),
            KBEntry(title="API guide", source="doc", content="redis is used for rate limiting", tags=[]),
        ]
        results = kb.search("redis")
        assert results[0].title == "Redis caching"

    def test_no_results(self, kb):
        kb.entries = [
            KBEntry(title="Payment API", source="doc", content="REST endpoints", tags=["api"]),
        ]
        results = kb.search("kubernetes")
        assert results == []

    def test_limit_parameter(self, kb):
        kb.entries = [
            KBEntry(title=f"Entry {i}", source="doc", content="test content", tags=["test"])
            for i in range(20)
        ]
        results = kb.search("test", limit=5)
        assert len(results) == 5

    def test_multi_word_query(self, kb):
        kb.entries = [
            KBEntry(title="Jenkins deploy", source="doc", content="CI/CD pipeline", tags=["jenkins", "deploy"]),
            KBEntry(title="Local build", source="doc", content="Build locally", tags=["build"]),
        ]
        results = kb.search("jenkins deploy")
        assert results[0].title == "Jenkins deploy"


class TestIndexCodeComments:
    def test_indexes_python_comments(self, kb, tmp_repo):
        kb.cwd = str(tmp_repo)
        kb._index_code_comments()
        titles = [e.title for e in kb.entries]
        assert any("refactor the payment module" in t for t in titles)
        assert any("handle edge case for null amount" in t for t in titles)
        assert any("auth token expires every 24h" in t for t in titles)

    def test_indexes_java_comments(self, kb, tmp_repo):
        kb.cwd = str(tmp_repo)
        kb._index_code_comments()
        titles = [e.title for e in kb.entries]
        assert any("add retry logic for API calls" in t for t in titles)
        assert any("temporary workaround for race condition" in t for t in titles)

    def test_source_is_code_comment(self, kb, tmp_repo):
        kb.cwd = str(tmp_repo)
        kb._index_code_comments()
        for e in kb.entries:
            assert e.source == "code-comment"

    def test_file_has_line_number(self, kb, tmp_repo):
        kb.cwd = str(tmp_repo)
        kb._index_code_comments()
        for e in kb.entries:
            assert ":" in e.file  # e.g. "main.py:1"


class TestIndexDocs:
    def test_indexes_markdown_headers(self, kb, tmp_repo):
        kb.cwd = str(tmp_repo)
        kb._index_docs()
        titles = [e.title for e in kb.entries]
        assert "Architecture" in titles
        assert "Database Layer" in titles
        assert "Auth Module" in titles

    def test_captures_content_snippet(self, kb, tmp_repo):
        kb.cwd = str(tmp_repo)
        kb._index_docs()
        arch_entry = next(e for e in kb.entries if e.title == "Architecture")
        assert "event-driven" in arch_entry.content

    def test_source_is_doc(self, kb, tmp_repo):
        kb.cwd = str(tmp_repo)
        kb._index_docs()
        for e in kb.entries:
            assert e.source == "doc"


class TestAddEntry:
    def test_adds_manual_entry(self, kb):
        with patch.object(kb, "_save_index"):
            kb.add_entry("Team standup notes", "We decided to use Kafka for events", tags=["kafka"])
        assert len(kb.entries) == 1
        assert kb.entries[0].title == "Team standup notes"
        assert kb.entries[0].source == "manual"
        assert "kafka" in kb.entries[0].tags


class TestSaveLoadIndex:
    def test_round_trip(self, kb, tmp_path):
        index_path = tmp_path / "kb_index.json"
        with patch("code_agents.knowledge.knowledge_base.KB_INDEX_PATH", index_path):
            kb.entries = [
                KBEntry(title="Test entry", source="manual", content="Some content", tags=["test"]),
            ]
            kb._save_index()

            # Load into a new instance
            with patch.object(KnowledgeBase, "_load_index"):
                kb2 = KnowledgeBase(cwd=str(tmp_path))
                kb2.entries = []

            # Now load manually
            with open(index_path) as f:
                data = json.load(f)
            assert len(data["entries"]) == 1
            assert data["entries"][0]["title"] == "Test entry"
            assert "updated" in data


class TestFormatKBResults:
    def test_formats_results(self):
        results = [
            KBEntry(title="Payment API", source="doc", file="api.md", content="REST endpoints", tags=["api"]),
        ]
        output = format_kb_results(results, "payment")
        assert "payment" in output
        assert "1 results" in output
        assert "Payment API" in output
        assert "api.md" in output

    def test_no_results_message(self):
        output = format_kb_results([], "nonexistent")
        assert "No results found" in output
        assert "--rebuild" in output

    def test_shows_tags(self):
        results = [
            KBEntry(title="Test", source="manual", content="content", tags=["api", "auth"]),
        ]
        output = format_kb_results(results, "test")
        assert "api, auth" in output


class TestRebuildIndex:
    def test_rebuilds_and_returns_count(self, kb, tmp_repo):
        kb.cwd = str(tmp_repo)
        with patch.object(kb, "_save_index"):
            count = kb.rebuild_index()
        assert count > 0
        assert len(kb.entries) == count

    def test_clears_old_entries(self, kb, tmp_repo):
        kb.cwd = str(tmp_repo)
        kb.entries = [KBEntry(title="Old", source="manual", content="stale")]
        with patch.object(kb, "_save_index"):
            kb.rebuild_index()
        assert not any(e.title == "Old" for e in kb.entries)
