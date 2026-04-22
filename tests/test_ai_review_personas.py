"""Tests for ai_review_personas.py — multiple code review perspectives."""

import pytest

from code_agents.reviews.ai_review_personas import (
    AIReviewPersonas,
    MultiPersonaReport,
    PersonaReport,
    ReviewComment,
    format_report,
)


@pytest.fixture
def reviewer():
    return AIReviewPersonas()


SAMPLE_CODE = {
    "app.py": '''
import *
def f(x):
    eval(x)
    password = "hardcoded123"
    except:
        pass
    for item in queryset.all():
        time.sleep(1)
        print(item)
'''
}


class TestSecurityHawk:
    def test_detects_eval(self):
        reviewer = AIReviewPersonas(personas=["security_hawk"])
        report = reviewer.analyze({"a.py": "result = eval(user_input)"})
        comments = report.persona_reports[0].comments
        assert any("eval" in c.message.lower() for c in comments)

    def test_detects_hardcoded_cred(self):
        reviewer = AIReviewPersonas(personas=["security_hawk"])
        report = reviewer.analyze({"a.py": 'password = "secret123"'})
        comments = report.persona_reports[0].comments
        assert any("credential" in c.message.lower() or "hardcoded" in c.message.lower() for c in comments)


class TestPerfPedant:
    def test_detects_sleep(self):
        reviewer = AIReviewPersonas(personas=["perf_pedant"])
        report = reviewer.analyze({"a.py": "time.sleep(5)"})
        assert len(report.persona_reports[0].comments) >= 1

    def test_detects_wildcard_import(self):
        reviewer = AIReviewPersonas(personas=["perf_pedant"])
        report = reviewer.analyze({"a.py": "import *"})
        assert len(report.persona_reports[0].comments) >= 1


class TestMultiPersona:
    def test_all_personas_run(self, reviewer):
        report = reviewer.analyze(SAMPLE_CODE)
        assert isinstance(report, MultiPersonaReport)
        assert len(report.persona_reports) == 4

    def test_consensus_score(self, reviewer):
        report = reviewer.analyze(SAMPLE_CODE)
        assert 1 <= report.consensus_score <= 10

    def test_clean_code_high_score(self):
        reviewer = AIReviewPersonas()
        report = reviewer.analyze({"clean.py": "def process(data):\n    return data\n"})
        assert report.consensus_score >= 7

    def test_format_report(self, reviewer):
        report = reviewer.analyze(SAMPLE_CODE)
        text = format_report(report)
        assert "Multi-Persona" in text
