"""Tests for the test style matching module."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.testing.test_style import (
    TestStyleAnalyzer,
    TestStyleProfile,
)


class TestTestStyleProfile:
    """Test TestStyleProfile dataclass."""

    def test_default_values(self):
        profile = TestStyleProfile()
        assert profile.pattern == "AAA"
        assert profile.assertion_style == "assert"
        assert profile.fixture_style == "@pytest.fixture"

    def test_summary_format(self):
        profile = TestStyleProfile(pattern="BDD", assertion_style="expect")
        summary = profile.summary()
        assert "BDD" in summary
        assert "expect" in summary
        assert "Pattern:" in summary


class TestDetectPattern:
    """Test pattern detection."""

    def test_detect_unittest(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_example.py").write_text(textwrap.dedent("""\
            import unittest
            class TestFoo(unittest.TestCase):
                def test_bar(self):
                    self.assertEqual(1, 1)
                    self.assertTrue(True)
                    self.assertIsNotNone("x")
        """))
        analyzer = TestStyleAnalyzer(str(tmp_path))
        profile = analyzer.analyze()
        assert profile.pattern == "unittest-class"
        assert profile.assertion_style == "assertEqual"

    def test_detect_pytest_fixtures(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_example.py").write_text(textwrap.dedent("""\
            import pytest
            @pytest.fixture
            def client():
                return {}
            @pytest.fixture
            def db():
                return {}
            def test_foo(client):
                assert client is not None
            def test_bar(db):
                assert db is not None
        """))
        analyzer = TestStyleAnalyzer(str(tmp_path))
        profile = analyzer.analyze()
        assert profile.fixture_style == "@pytest.fixture"
        assert profile.assertion_style == "assert"

    def test_detect_plain_assert(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_simple.py").write_text(textwrap.dedent("""\
            def test_add():
                assert 1 + 1 == 2
            def test_sub():
                assert 3 - 1 == 2
        """))
        analyzer = TestStyleAnalyzer(str(tmp_path))
        profile = analyzer.analyze()
        assert profile.assertion_style == "assert"


class TestDetectNaming:
    """Test naming convention detection."""

    def test_detect_should_pattern(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_naming.py").write_text(textwrap.dedent("""\
            def test_should_return_true():
                assert True
            def test_should_handle_none():
                assert True
            def test_should_validate_input():
                assert True
        """))
        analyzer = TestStyleAnalyzer(str(tmp_path))
        profile = analyzer.analyze()
        assert profile.naming == "test_should_X"

    def test_detect_when_pattern(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_when.py").write_text(textwrap.dedent("""\
            def test_add_when_positive():
                assert True
            def test_add_when_negative():
                assert True
            def test_divide_when_zero():
                assert True
        """))
        analyzer = TestStyleAnalyzer(str(tmp_path))
        profile = analyzer.analyze()
        assert profile.naming == "test_X_when_Y"


class TestDetectMockStyle:
    """Test mock style detection."""

    def test_detect_unittest_mock(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_mocks.py").write_text(textwrap.dedent("""\
            from unittest.mock import patch, MagicMock
            @patch("module.func")
            def test_thing(mock_func):
                mock_func.return_value = 42
                assert True
        """))
        analyzer = TestStyleAnalyzer(str(tmp_path))
        profile = analyzer.analyze()
        assert profile.mock_style == "unittest.mock"


class TestGenerateMatching:
    """Test test generation matching detected style."""

    def test_generate_pytest_style(self, tmp_path):
        # Create test files for style detection
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_existing.py").write_text("def test_foo():\n    assert True\n")

        # Create source file
        src = tmp_path / "utils.py"
        src.write_text("def calculate(x, y):\n    return x + y\n")

        analyzer = TestStyleAnalyzer(str(tmp_path))
        result = analyzer.generate_matching(str(src))
        assert "def test_" in result
        assert "assert" in result

    def test_generate_missing_file(self, tmp_path):
        analyzer = TestStyleAnalyzer(str(tmp_path))
        result = analyzer.generate_matching("/nonexistent.py")
        assert "Error" in result

    def test_generate_no_functions(self, tmp_path):
        src = tmp_path / "empty.py"
        src.write_text("# just a comment\nX = 42\n")
        analyzer = TestStyleAnalyzer(str(tmp_path))
        result = analyzer.generate_matching(str(src))
        assert "No functions" in result

    def test_no_test_files_returns_default(self, tmp_path):
        analyzer = TestStyleAnalyzer(str(tmp_path))
        profile = analyzer.analyze()
        assert profile.pattern == "AAA"  # default

    def test_uses_classes_detection(self, tmp_path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_cls.py").write_text(textwrap.dedent("""\
            class TestFoo:
                def test_a(self):
                    assert True
            class TestBar:
                def test_b(self):
                    assert True
        """))
        analyzer = TestStyleAnalyzer(str(tmp_path))
        profile = analyzer.analyze()
        assert profile.uses_classes is True
