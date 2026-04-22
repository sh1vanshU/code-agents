"""Tests for the EdgeCaseSuggester module."""

import textwrap
import pytest
from code_agents.testing.edge_case_suggester import EdgeCaseSuggester, EdgeCaseConfig, EdgeCaseResult, format_edge_cases


class TestEdgeCaseSuggester:
    def test_suggest_for_string_arg(self, tmp_path):
        source = textwrap.dedent('''\
            def process_name(name: str) -> str:
                return name.upper()
        ''')
        (tmp_path / "app.py").write_text(source)
        result = EdgeCaseSuggester(EdgeCaseConfig(cwd=str(tmp_path))).suggest("app.py:process_name")
        categories = [e.category for e in result.edge_cases]
        assert "null" in categories
        assert "empty" in categories

    def test_suggest_for_numeric_arg(self, tmp_path):
        source = textwrap.dedent('''\
            def paginate(offset: int, limit: int):
                return data[offset:offset+limit]
        ''')
        (tmp_path / "app.py").write_text(source)
        result = EdgeCaseSuggester(EdgeCaseConfig(cwd=str(tmp_path))).suggest("app.py:paginate")
        categories = [e.category for e in result.edge_cases]
        assert "boundary" in categories  # 0, negative

    def test_suggest_from_json_parsing(self, tmp_path):
        source = textwrap.dedent('''\
            import json
            def parse(data):
                return json.loads(data)
        ''')
        (tmp_path / "app.py").write_text(source)
        result = EdgeCaseSuggester(EdgeCaseConfig(cwd=str(tmp_path))).suggest("app.py:parse")
        assert any("JSON" in e.description for e in result.edge_cases)

    def test_suggest_from_http_calls(self, tmp_path):
        source = textwrap.dedent('''\
            import requests
            def fetch(url):
                return requests.get(url).json()
        ''')
        (tmp_path / "app.py").write_text(source)
        result = EdgeCaseSuggester(EdgeCaseConfig(cwd=str(tmp_path))).suggest("app.py:fetch")
        assert any("timeout" in e.description.lower() for e in result.edge_cases)

    def test_detect_existing_checks(self, tmp_path):
        source = textwrap.dedent('''\
            def safe_divide(a, b):
                if b is None:
                    raise ValueError("b cannot be None")
                try:
                    return a / b
                except ZeroDivisionError:
                    return 0
        ''')
        (tmp_path / "app.py").write_text(source)
        result = EdgeCaseSuggester(EdgeCaseConfig(cwd=str(tmp_path))).suggest("app.py:safe_divide")
        assert "None/null checks" in result.existing_checks
        assert "Exception handling" in result.existing_checks

    def test_function_not_found(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1\n")
        result = EdgeCaseSuggester(EdgeCaseConfig(cwd=str(tmp_path))).suggest("app.py:nonexistent")
        assert "not found" in result.summary.lower()

    def test_format_output(self):
        result = EdgeCaseResult(target="app.py:foo", summary="5 edge cases")
        output = format_edge_cases(result)
        assert "Edge Case" in output
