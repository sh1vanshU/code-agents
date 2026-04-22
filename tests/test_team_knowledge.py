"""Tests for the team knowledge base module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.knowledge.team_knowledge import TeamKnowledgeBase


class TestAdd:
    """Test adding knowledge entries."""

    def test_add_new_entry(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        result = kb.add("deployment", "Always deploy to dev first", author="alice")
        assert result["action"] == "added"
        assert result["topic"] == "deployment"
        assert os.path.isfile(result["path"])

    def test_add_updates_existing(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        kb.add("deployment", "v1 content")
        result = kb.add("deployment", "v2 content", author="bob")
        assert result["action"] == "updated"
        entry = kb.get("deployment")
        assert "v2 content" in entry["content"]

    def test_add_with_author(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        kb.add("testing", "Run pytest", author="charlie")
        entry = kb.get("testing")
        assert entry["author"] == "charlie"

    def test_add_invalid_topic(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        result = kb.add("", "content")
        assert "error" in result


class TestSearch:
    """Test knowledge base search."""

    def test_search_by_topic(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        kb.add("deployment-process", "Deploy to dev first")
        kb.add("testing-guide", "Always run tests")
        results = kb.search("deploy")
        assert len(results) >= 1
        assert results[0]["topic"] == "deployment-process"

    def test_search_by_content(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        kb.add("onboarding", "New developers should read the README and run tests")
        results = kb.search("README")
        assert len(results) == 1

    def test_search_no_results(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        kb.add("deployment", "Deploy to dev first")
        results = kb.search("xyznonexistent")
        assert len(results) == 0

    def test_search_ranking(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        kb.add("deploy", "Deploy instructions")
        kb.add("monitoring", "Monitor deploys in Grafana")
        results = kb.search("deploy")
        # Exact topic match should rank higher
        assert results[0]["topic"] == "deploy"


class TestListTopics:
    """Test listing topics."""

    def test_list_empty(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        assert kb.list_topics() == []

    def test_list_topics_sorted(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        kb.add("zebra", "Z content")
        kb.add("alpha", "A content")
        kb.add("middle", "M content")
        topics = kb.list_topics()
        assert topics == ["alpha", "middle", "zebra"]


class TestGet:
    """Test getting specific entries."""

    def test_get_existing(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        kb.add("my-topic", "The content", author="dev")
        entry = kb.get("my-topic")
        assert entry is not None
        assert entry["topic"] == "my-topic"
        assert "The content" in entry["content"]

    def test_get_nonexistent(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        assert kb.get("nonexistent") is None

    def test_get_case_insensitive(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        kb.add("My Topic", "Content")
        # Slug is "my-topic", but search by original should also work
        entry = kb.get("my topic")
        assert entry is not None


class TestDelete:
    """Test deleting entries."""

    def test_delete_existing(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        kb.add("temp", "Temporary content")
        assert kb.delete("temp")
        assert kb.get("temp") is None

    def test_delete_nonexistent(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        assert not kb.delete("nonexistent")

    def test_delete_removes_file(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        result = kb.add("removeme", "Content")
        path = result["path"]
        assert os.path.isfile(path)
        kb.delete("removeme")
        assert not os.path.isfile(path)


class TestSlugify:
    """Test topic name slugification."""

    def test_simple_slug(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        assert kb._slugify("deployment") == "deployment"

    def test_spaces_to_dashes(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        assert kb._slugify("my topic name") == "my-topic-name"

    def test_special_chars(self, tmp_path):
        kb = TeamKnowledgeBase(str(tmp_path))
        slug = kb._slugify("Deploy: Best Practices!")
        assert ":" not in slug
        assert "!" not in slug
