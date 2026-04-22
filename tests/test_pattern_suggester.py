"""Tests for the PatternSuggester module."""

import textwrap
import pytest
from code_agents.reviews.pattern_suggester import (
    PatternSuggester, PatternSuggesterConfig, PatternSuggesterReport, format_pattern_report,
)


class TestPatternSuggester:
    def test_detect_singleton_pattern(self, tmp_path):
        source = textwrap.dedent('''\
            class Database:
                _instance = None

                @classmethod
                def get_instance(cls):
                    if cls._instance is None:
                        cls._instance = cls()
                    return cls._instance
        ''')
        (tmp_path / "db.py").write_text(source)
        suggester = PatternSuggester(PatternSuggesterConfig(cwd=str(tmp_path)))
        report = suggester.analyze()
        assert any(s.pattern_name == "Singleton (caution)" for s in report.suggestions)

    def test_detect_template_method(self, tmp_path):
        source = textwrap.dedent('''\
            class BaseProcessor:
                def validate(self):
                    raise NotImplementedError
        ''')
        (tmp_path / "base.py").write_text(source)
        suggester = PatternSuggester(PatternSuggesterConfig(cwd=str(tmp_path)))
        report = suggester.analyze()
        assert any(s.pattern_name == "Template Method" for s in report.suggestions)

    def test_detect_builder_indicator(self, tmp_path):
        # A function with very long parameter list
        params = ", ".join([f"param{i}: str" for i in range(15)])
        source = f"def create_report({params}):\n    pass\n"
        (tmp_path / "builder.py").write_text(source)
        suggester = PatternSuggester(PatternSuggesterConfig(cwd=str(tmp_path)))
        report = suggester.analyze()
        assert any(s.pattern_name == "Builder" for s in report.suggestions)

    def test_suggestions_have_before_after(self, tmp_path):
        source = '_instance = None\n'
        (tmp_path / "single.py").write_text(source)
        suggester = PatternSuggester(PatternSuggesterConfig(cwd=str(tmp_path)))
        report = suggester.analyze()
        for s in report.suggestions:
            assert s.before_code != ""
            assert s.after_code != ""
            assert len(s.benefits) > 0

    def test_clean_code_no_suggestions(self, tmp_path):
        source = textwrap.dedent('''\
            def add(a: int, b: int) -> int:
                return a + b
        ''')
        (tmp_path / "clean.py").write_text(source)
        suggester = PatternSuggester(PatternSuggesterConfig(cwd=str(tmp_path)))
        report = suggester.analyze()
        assert len(report.suggestions) == 0

    def test_format_report(self):
        report = PatternSuggesterReport(
            files_scanned=10, indicators_found=3, summary="done",
        )
        output = format_pattern_report(report)
        assert "Pattern Suggester" in output
        assert "Indicators" in output
