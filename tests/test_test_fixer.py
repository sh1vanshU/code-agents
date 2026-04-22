"""Tests for the TestFixer module."""

import pytest
from code_agents.testing.test_fixer import TestFixer, TestFixerConfig, TestFixResult, format_test_fix


class TestTestFixer:
    def test_parse_failures(self):
        output = """FAILED tests/test_api.py::TestApi::test_login - AssertionError
FAILED tests/test_db.py::test_query - TypeError
"""
        fixer = TestFixer(TestFixerConfig())
        failures = fixer._parse_failures(output)
        assert len(failures) == 2
        assert failures[0].test_file == "tests/test_api.py"
        assert failures[0].test_class == "TestApi"
        assert failures[0].test_name == "test_login"

    def test_parse_simple_failures(self):
        output = "FAILED tests/test_utils.py::test_parse - ValueError\n"
        fixer = TestFixer(TestFixerConfig())
        failures = fixer._parse_failures(output)
        assert len(failures) == 1
        assert failures[0].test_name == "test_parse"

    def test_diagnose_assertion_errors(self):
        output = """FAILED tests/test_api.py::test_status
E   AssertionError: assert 200 == 404
FAILED tests/test_api.py::test_login
E   AssertionError: assert 'ok' == 'error'
"""
        fixer = TestFixer(TestFixerConfig())
        result = fixer.diagnose(output)
        assert "behavior_changed" in result.diagnosis or "assertion" in result.diagnosis.lower()

    def test_diagnose_import_errors(self):
        output = """FAILED tests/test_a.py::test_1
E   ImportError: cannot import name 'foo' from 'bar'
FAILED tests/test_b.py::test_2
E   ImportError: No module named 'baz'
"""
        fixer = TestFixer(TestFixerConfig())
        result = fixer.diagnose(output)
        assert "refactored" in result.diagnosis or "import" in result.diagnosis.lower()

    def test_suggest_fixes(self):
        from code_agents.testing.test_fixer import TestFailure
        fixer = TestFixer(TestFixerConfig())
        failure = TestFailure(
            test_file="tests/test_x.py",
            test_name="test_foo",
            error_type="AttributeError",
            error_message="Mock object has no attribute 'bar'",
        )
        suggestions = fixer._suggest_fixes(failure)
        assert len(suggestions) > 0
        assert suggestions[0].fix_type == "update_mock"

    def test_empty_output(self):
        result = TestFixer(TestFixerConfig()).diagnose("")
        assert result.diagnosis == "no_failures"

    def test_format_output(self):
        result = TestFixResult(summary="2 failures", diagnosis="code_changed")
        output = format_test_fix(result)
        assert "Test Fixer" in output
