"""Tests for the CodebaseNavigator module."""

from unittest.mock import patch, MagicMock

import pytest

from code_agents.knowledge.codebase_nav import CodebaseNavigator, NavConfig, NavSearchResult, format_nav_results


class TestCodebaseNavigator:
    """Test CodebaseNavigator functionality."""

    def test_config_defaults(self):
        config = NavConfig()
        assert config.cwd == "."
        assert config.max_results == 30
        assert config.include_tests is False

    def test_expand_query_basic(self):
        config = NavConfig(cwd="/tmp")
        nav = CodebaseNavigator(config)
        keywords = nav._expand_query("authentication")
        assert "authentication" in keywords
        assert "auth" in keywords or "login" in keywords

    def test_expand_query_short_words_filtered(self):
        config = NavConfig(cwd="/tmp")
        nav = CodebaseNavigator(config)
        keywords = nav._expand_query("a b cd")
        # Words less than 3 chars should be filtered
        assert "a" not in keywords
        assert "b" not in keywords

    def test_match_concepts(self):
        config = NavConfig(cwd="/tmp")
        nav = CodebaseNavigator(config)
        concepts = nav._match_concepts("how does authentication work?")
        assert "authentication" in concepts

    def test_match_concepts_by_keyword(self):
        config = NavConfig(cwd="/tmp")
        nav = CodebaseNavigator(config)
        concepts = nav._match_concepts("where is the login token validated?")
        assert "authentication" in concepts

    def test_score_relevance(self):
        config = NavConfig(cwd="/tmp")
        nav = CodebaseNavigator(config)

        # Definition match should score higher
        score_def = nav._score_relevance("def authenticate_user():", ["auth"], "auth.py")
        score_ref = nav._score_relevance("# auth is important", ["auth"], "notes.txt")
        assert score_def > score_ref

    def test_classify_result(self):
        config = NavConfig(cwd="/tmp")
        nav = CodebaseNavigator(config)

        assert nav._classify_result("def foo():", "a.py") == "function"
        assert nav._classify_result("class Bar:", "a.py") == "class"
        assert nav._classify_result("from x import y", "a.py") == "import"
        assert nav._classify_result("key: value", "config.yaml") == "config"

    @patch("code_agents.tools._pattern_matchers.grep_codebase")
    def test_search_returns_results(self, mock_grep):
        from code_agents.tools._pattern_matchers import SearchMatch

        mock_grep.return_value = [
            SearchMatch(file="auth.py", line=10, content="def authenticate(user):"),
            SearchMatch(file="login.py", line=5, content="auth_token = create_token()"),
        ]

        config = NavConfig(cwd="/tmp")
        result = CodebaseNavigator(config).search("authentication")

        assert result.query == "authentication"
        assert len(result.results) >= 1

    def test_format_nav_results(self):
        result = NavSearchResult(
            query="auth",
            total_files_scanned=10,
            concepts_matched=["authentication"],
        )
        output = format_nav_results(result)
        assert "auth" in output
        assert "authentication" in output
