"""Tests for the comment generator."""

from __future__ import annotations

import os
import pytest

from code_agents.reviews.comment_generator import (
    CommentGenerator, CommentSuggestion, CommentResult,
)


class TestCommentSuggestion:
    """Test CommentSuggestion dataclass."""

    def test_fields(self):
        s = CommentSuggestion(
            file_path="a.py", line_number=10, comment="Explain this",
            reason="pattern", complexity_type="nested_condition", confidence=0.8,
        )
        assert s.confidence == 0.8
        assert s.complexity_type == "nested_condition"


class TestCommentResult:
    """Test CommentResult dataclass."""

    def test_summary(self):
        r = CommentResult(
            suggestions=[
                CommentSuggestion(file_path="a.py", line_number=1, comment="c",
                                  reason="r", complexity_type="t"),
            ],
            files_analyzed=3,
        )
        assert "1 suggestions" in r.summary
        assert "3 files" in r.summary


class TestCommentGenerator:
    """Test CommentGenerator analysis."""

    def _write_file(self, tmp_path, name, content):
        f = tmp_path / name
        f.write_text(content)
        return str(f)

    def test_detect_nested_condition(self, tmp_path):
        path = self._write_file(tmp_path, "test.py",
            "if x > 0 and y < 10 and z == 5:\n    pass\n")
        gen = CommentGenerator(cwd=str(tmp_path), min_confidence=0.0)
        suggestions = gen.analyze_file(path)
        assert any(s.complexity_type == "nested_condition" for s in suggestions)

    def test_detect_bitwise_ops(self, tmp_path):
        path = self._write_file(tmp_path, "test.py",
            "flags = value & 0xFF\nresult = flags << 2\n")
        gen = CommentGenerator(cwd=str(tmp_path), min_confidence=0.0)
        suggestions = gen.analyze_file(path)
        assert any(s.complexity_type == "bitwise_ops" for s in suggestions)

    def test_detect_regex(self, tmp_path):
        path = self._write_file(tmp_path, "test.py",
            "import re\npattern = re.compile(r'^[a-z]+_\\d+$')\n")
        gen = CommentGenerator(cwd=str(tmp_path), min_confidence=0.0)
        suggestions = gen.analyze_file(path)
        assert any(s.complexity_type == "regex_literal" for s in suggestions)

    def test_detect_broad_except(self, tmp_path):
        path = self._write_file(tmp_path, "test.py",
            "try:\n    do_something()\nexcept Exception:\n    pass\n")
        gen = CommentGenerator(cwd=str(tmp_path), min_confidence=0.0)
        suggestions = gen.analyze_file(path)
        assert any(s.complexity_type == "exception_catch_broad" for s in suggestions)

    def test_skip_commented_lines(self, tmp_path):
        path = self._write_file(tmp_path, "test.py",
            "# if x > 0 and y < 10 and z == 5:\n")
        gen = CommentGenerator(cwd=str(tmp_path), min_confidence=0.0)
        suggestions = gen.analyze_file(path)
        assert len(suggestions) == 0

    def test_confidence_filtering(self, tmp_path):
        path = self._write_file(tmp_path, "test.py",
            "flags = value & 0xFF\n")
        gen = CommentGenerator(cwd=str(tmp_path), min_confidence=0.95)
        result = gen.analyze(file_paths=[path])
        # bitwise has confidence 0.9, should be filtered at 0.95
        assert len(result.suggestions) == 0

    def test_analyze_multiple_files(self, tmp_path):
        p1 = self._write_file(tmp_path, "a.py", "x = value & 0xFF\n")
        p2 = self._write_file(tmp_path, "b.py", "try:\n    x()\nexcept Exception:\n    pass\n")
        gen = CommentGenerator(cwd=str(tmp_path), min_confidence=0.0)
        result = gen.analyze(file_paths=[p1, p2])
        assert result.files_analyzed == 2
        assert len(result.suggestions) >= 2

    def test_has_inline_comment(self):
        assert CommentGenerator._has_inline_comment("x = 1  # comment", "#") is True
        assert CommentGenerator._has_inline_comment("x = 1", "#") is False
        assert CommentGenerator._has_inline_comment('x = "# not a comment"', "#") is False

    def test_nesting_detection(self, tmp_path):
        code = "\n".join([
            "def f():",
            "    if True:",
            "        for x in y:",
            "            while z:",
            "                if a:",
            "                    do_something()",
        ])
        path = self._write_file(tmp_path, "deep.py", code)
        gen = CommentGenerator(cwd=str(tmp_path), min_confidence=0.0)
        suggestions = gen.analyze_file(path)
        assert any(s.complexity_type == "deep_nesting" for s in suggestions)

    def test_nonexistent_file(self, tmp_path):
        gen = CommentGenerator(cwd=str(tmp_path))
        suggestions = gen.analyze_file("/nonexistent/file.py")
        assert suggestions == []
