"""Tests for test_darwinism.py — test suite fitness scoring."""

import pytest

from code_agents.testing.test_darwinism import (
    TestDarwinism,
    DarwinismReport,
    TestCase,
    format_report,
)


@pytest.fixture
def darwin(tmp_path):
    return TestDarwinism(str(tmp_path))


SAMPLE_TESTS = {
    "tests/test_auth.py": """
def test_login_success():
    assert login("user", "pass") == True

def test_login_failure():
    assert login("user", "wrong") == False

def test_login_empty():
    assert login("", "") == False
""",
    "tests/test_utils.py": """
def test_helper():
    assert helper(1, 2) == 3

def test_helper_negative():
    assert helper(-1, 1) == 0
""",
}


class TestExtractTests:
    def test_finds_test_functions(self, darwin):
        tests = darwin._extract_tests("test_auth.py", SAMPLE_TESTS["tests/test_auth.py"])
        names = [t.name for t in tests]
        assert "test_login_success" in names
        assert len(tests) == 3

    def test_empty_file(self, darwin):
        tests = darwin._extract_tests("empty.py", "")
        assert tests == []


class TestFitness:
    def test_bug_catching_increases_fitness(self, darwin):
        t = TestCase(name="test_good", bugs_caught=5)
        score = darwin._compute_fitness(t)
        assert score >= 40

    def test_fast_test_bonus(self, darwin):
        fast = TestCase(name="fast", execution_time_ms=50)
        slow = TestCase(name="slow", execution_time_ms=5000)
        assert darwin._compute_fitness(fast) > darwin._compute_fitness(slow)


class TestRedundancy:
    def test_finds_redundant(self, darwin):
        tests = [
            TestCase(name="t1", code_covered={"a.py:1", "a.py:2"}, fitness_score=50),
            TestCase(name="t2", code_covered={"a.py:1", "a.py:2"}, fitness_score=30),
        ]
        darwin._find_redundancies(tests)
        assert tests[1].is_redundant is True
        assert tests[1].redundant_with == "t1"


class TestAnalyze:
    def test_full_analysis(self, darwin):
        report = darwin.analyze(SAMPLE_TESTS)
        assert isinstance(report, DarwinismReport)
        assert report.suite.total_tests >= 5

    def test_with_history(self, darwin):
        bug_history = {"test_login_success": 3}
        report = darwin.analyze(SAMPLE_TESTS, bug_history=bug_history)
        ranked = report.ranked_tests
        login_test = [t for t in ranked if t.name == "test_login_success"]
        assert login_test[0].bugs_caught == 3

    def test_format_report(self, darwin):
        report = darwin.analyze(SAMPLE_TESTS)
        text = format_report(report)
        assert "Darwinism" in text
