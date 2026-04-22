"""Tests for the ExampleFinder module."""

from unittest.mock import patch

import pytest

from code_agents.knowledge.code_example import (
    ExampleFinder, ExampleConfig, CodeExample, ExampleSearchResult, format_examples,
)


class TestExampleFinder:
    """Test ExampleFinder functionality."""

    def test_config_defaults(self):
        config = ExampleConfig()
        assert config.cwd == "."
        assert config.max_examples == 20
        assert config.context_lines == 5

    def test_classify_pattern_import(self):
        config = ExampleConfig(cwd="/tmp")
        finder = ExampleFinder(config)
        pattern = finder._classify_pattern("from redis import Redis", "redis")
        assert pattern == "import"

    def test_classify_pattern_definition(self):
        config = ExampleConfig(cwd="/tmp")
        finder = ExampleFinder(config)
        pattern = finder._classify_pattern("def create_redis_pool():", "redis")
        assert pattern == "definition"

    def test_classify_pattern_call(self):
        config = ExampleConfig(cwd="/tmp")
        finder = ExampleFinder(config)
        pattern = finder._classify_pattern("    client = redis(host='localhost')", "redis")
        assert pattern == "function_call"

    def test_classify_pattern_context_manager(self):
        config = ExampleConfig(cwd="/tmp")
        finder = ExampleFinder(config)
        pattern = finder._classify_pattern("with redis.pipeline() as pipe:", "redis")
        assert pattern == "context_manager"

    def test_score_example_prefers_definitions(self):
        config = ExampleConfig(cwd="/tmp")
        finder = ExampleFinder(config)
        score_def = finder._score_example("def process_redis():\n    pass", "redis", False)
        score_ref = finder._score_example("# redis is used here", "redis", False)
        assert score_def > score_ref

    def test_score_example_penalizes_long_code(self):
        config = ExampleConfig(cwd="/tmp")
        finder = ExampleFinder(config)
        short = "x = redis()\n"
        long_code = "x = redis()\n" + "line\n" * 40
        score_short = finder._score_example(short, "redis", False)
        score_long = finder._score_example(long_code, "redis", False)
        assert score_short >= score_long

    def test_detect_language(self):
        config = ExampleConfig(cwd="/tmp")
        finder = ExampleFinder(config)
        assert finder._detect_language("app.py") == "python"
        assert finder._detect_language("index.ts") == "typescript"
        assert finder._detect_language("main.go") == "go"

    @patch("code_agents.tools._pattern_matchers.grep_codebase")
    def test_find_returns_examples(self, mock_grep, tmp_path):
        from code_agents.tools._pattern_matchers import SearchMatch

        source = "from redis import Redis\nclient = Redis()\n"
        (tmp_path / "cache.py").write_text(source)

        mock_grep.return_value = [
            SearchMatch(file="cache.py", line=1, content="from redis import Redis"),
        ]

        config = ExampleConfig(cwd=str(tmp_path))
        result = ExampleFinder(config).find("redis")

        assert result.query == "redis"
        assert result.total_matches >= 1

    def test_format_examples(self):
        result = ExampleSearchResult(
            query="redis",
            total_matches=5,
            patterns_found=["import", "function_call"],
            examples=[
                CodeExample(
                    file="cache.py", start_line=1, end_line=3,
                    code="from redis import Redis\nclient = Redis()\n",
                    pattern="import",
                ),
            ],
        )
        output = format_examples(result)
        assert "redis" in output
        assert "import" in output
        assert "cache.py" in output
