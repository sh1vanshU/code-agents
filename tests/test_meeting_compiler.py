"""Tests for meeting_compiler.py — meeting transcript to actionable artifacts."""

import pytest

from code_agents.knowledge.meeting_compiler import (
    MeetingCompiler,
    MeetingReport,
    ActionItem,
    JiraTicketDraft,
    format_report,
)


@pytest.fixture
def compiler():
    return MeetingCompiler()


SAMPLE_TRANSCRIPT = """
Alice: Let's discuss the API migration.
Bob: I think we should go with GraphQL.
Alice: Decided: we will use GraphQL for the new API.
Bob: Action item: Alice will create the schema by Friday.
Charlie: I disagree, REST is simpler for our use case.
Alice: TODO: Bob needs to benchmark latency.
# Topic: Database Migration
Bob: We should also consider the database migration approach.
"""


class TestExtractParticipants:
    def test_extracts_speakers(self, compiler):
        compiler._extract_participants(SAMPLE_TRANSCRIPT.splitlines())
        assert "Alice" in compiler.participants
        assert "Bob" in compiler.participants

    def test_ignores_keywords(self, compiler):
        compiler._extract_participants(["Action: something"])
        assert "Action" not in compiler.participants

    def test_empty_transcript(self, compiler):
        compiler._extract_participants([])
        assert len(compiler.participants) == 0


class TestExtractActionItems:
    def test_finds_action_items(self, compiler):
        items = compiler._extract_action_items(SAMPLE_TRANSCRIPT.splitlines())
        assert len(items) >= 1
        assert any("schema" in ai.description.lower() or "benchmark" in ai.description.lower() for ai in items)

    def test_finds_todo(self, compiler):
        items = compiler._extract_action_items(["TODO: fix the tests"])
        assert len(items) >= 1


class TestExtractDecisions:
    def test_finds_decisions(self, compiler):
        decisions = compiler._extract_decisions(SAMPLE_TRANSCRIPT.splitlines())
        assert len(decisions) >= 1
        assert any("GraphQL" in d for d in decisions)


class TestAnalyze:
    def test_full_analysis(self, compiler):
        report = compiler.analyze(SAMPLE_TRANSCRIPT)
        assert isinstance(report, MeetingReport)
        assert len(report.participants) >= 2
        assert len(report.action_items) >= 1
        assert len(report.decisions) >= 1

    def test_generates_jira_tickets(self, compiler):
        report = compiler.analyze(SAMPLE_TRANSCRIPT)
        assert len(report.jira_tickets) >= 1
        assert all(isinstance(t, JiraTicketDraft) for t in report.jira_tickets)

    def test_format_report(self, compiler):
        report = compiler.analyze(SAMPLE_TRANSCRIPT)
        text = format_report(report)
        assert "Meeting Summary" in text
