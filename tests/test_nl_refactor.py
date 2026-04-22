"""Tests for nl_refactor.py — NL refactoring commands to transform plans."""

import pytest

from code_agents.reviews.nl_refactor import (
    NLRefactor,
    NLRefactorReport,
    RefactorPlan,
    format_report,
)


@pytest.fixture
def refactorer(tmp_path):
    return NLRefactor(str(tmp_path))


SAMPLE_FILES = {
    "payments/handler.py": """
def processPayment(amount):
    return amount * 1.1

def validateCard(cardNumber):
    return len(cardNumber) == 16

class PaymentProcessor:
    def handleRequest(self, request):
        return self.processPayment(request.amount)
""",
}


class TestParseIntent:
    def test_rename_camel_to_snake(self, refactorer):
        intent = refactorer._parse_intent("rename camelCase to snake_case in payments")
        assert intent.action in ("rename", "convert")
        assert intent.scope_filter == "payments"

    def test_extract_intent(self, refactorer):
        intent = refactorer._parse_intent("extract the validation logic into a separate module")
        assert intent.action == "extract"


class TestNamingConversion:
    def test_camel_to_snake(self, refactorer):
        assert refactorer._convert_name("processPayment", "snake_case") == "process_payment"

    def test_snake_to_camel(self, refactorer):
        assert refactorer._convert_name("process_payment", "camelCase") == "processPayment"

    def test_camel_to_pascal(self, refactorer):
        assert refactorer._convert_name("processPayment", "PascalCase") == "ProcessPayment"

    def test_matches_camel(self, refactorer):
        assert refactorer._matches_convention("processPayment", "camelCase") is True
        assert refactorer._matches_convention("process_payment", "camelCase") is False


class TestAnalyze:
    def test_generates_plan(self, refactorer):
        report = refactorer.analyze(
            "convert camelCase to snake_case in payments",
            file_contents=SAMPLE_FILES,
        )
        assert isinstance(report, NLRefactorReport)
        if report.plan:
            assert report.plan.total_changes >= 1

    def test_ambiguity_on_missing_target(self, refactorer):
        report = refactorer.analyze("convert everything")
        assert len(report.ambiguities) >= 1

    def test_format_report(self, refactorer):
        report = refactorer.analyze("rename camelCase to snake_case", file_contents=SAMPLE_FILES)
        text = format_report(report)
        assert "Refactor" in text
