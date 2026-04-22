"""Tests for auto_observability.py — auto-inject logging, tracing, metrics."""

import pytest

from code_agents.observability.auto_observability import (
    AutoObservability,
    ObservabilityPlan,
    InjectionPoint,
    format_plan,
)


@pytest.fixture
def analyzer(tmp_path):
    return AutoObservability(str(tmp_path))


SAMPLE_CODE = '''
def process_request(user_id, data):
    result = validate(data)
    if result:
        return save(user_id, data)
    return None

def _helper():
    pass

class UserService:
    def handle_query(self, query):
        for item in query.items:
            db.execute(item)
        return True
'''


class TestFindFunctions:
    def test_finds_functions(self, analyzer):
        funcs = analyzer._find_functions(SAMPLE_CODE)
        names = [f["name"] for f in funcs]
        assert "process_request" in names
        assert "_helper" in names

    def test_detects_private(self, analyzer):
        funcs = analyzer._find_functions(SAMPLE_CODE)
        helper = [f for f in funcs if f["name"] == "_helper"][0]
        assert helper["is_private"] is True

    def test_empty_code(self, analyzer):
        funcs = analyzer._find_functions("")
        assert funcs == []


class TestAnalyze:
    def test_generates_plan(self, analyzer):
        plan = analyzer.analyze({"app.py": SAMPLE_CODE})
        assert isinstance(plan, ObservabilityPlan)
        assert plan.functions_found >= 2
        assert len(plan.injections) >= 1

    def test_logging_injections(self, analyzer):
        plan = analyzer.analyze({"app.py": SAMPLE_CODE}, include_tracing=False, include_metrics=False)
        log_inj = [i for i in plan.injections if i.kind == "logging"]
        assert len(log_inj) >= 1

    def test_tracing_injections(self, analyzer):
        plan = analyzer.analyze({"app.py": SAMPLE_CODE}, include_logging=False, include_metrics=False)
        trace_inj = [i for i in plan.injections if i.kind == "tracing"]
        assert len(trace_inj) >= 1

    def test_skips_private_for_tracing(self, analyzer):
        plan = analyzer.analyze({"app.py": "def _private(): pass"}, include_logging=False, include_metrics=False)
        assert len(plan.injections) == 0

    def test_format_plan(self, analyzer):
        plan = analyzer.analyze({"app.py": SAMPLE_CODE})
        text = format_plan(plan)
        assert "Auto-Observability" in text

    def test_coverage_calculation(self, analyzer):
        code_with_logging = 'def foo():\n    logger.info("hi")\n'
        plan = analyzer.analyze({"a.py": code_with_logging})
        assert plan.already_instrumented >= 1
