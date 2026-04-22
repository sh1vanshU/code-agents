"""Tests for the TeachMode module."""

import textwrap
import pytest
from code_agents.knowledge.teach_mode import (
    TeachMode, TeachModeConfig, TeachModeReport, format_teach_report,
)


class TestTeachMode:
    def test_explain_dependency_injection(self):
        teacher = TeachMode(TeachModeConfig())
        report = teacher.explain("dependency injection")
        assert report.explanation is not None
        assert report.explanation.concept == "dependency injection"
        assert len(report.explanation.examples) >= 1
        assert len(report.explanation.alternatives) >= 1

    def test_explain_with_alias(self):
        teacher = TeachMode(TeachModeConfig())
        report = teacher.explain("di")
        assert report.explanation is not None
        assert report.explanation.concept == "dependency injection"

    def test_explain_factory_pattern(self):
        teacher = TeachMode(TeachModeConfig())
        report = teacher.explain("factory pattern")
        assert report.explanation is not None
        assert len(report.explanation.learning_path) >= 1
        assert len(report.explanation.common_mistakes) >= 1

    def test_unknown_concept(self):
        teacher = TeachMode(TeachModeConfig())
        report = teacher.explain("quantum flux capacitor")
        assert "not found" in report.summary.lower() or "not found" in report.explanation.summary.lower()

    def test_respects_config_no_examples(self):
        teacher = TeachMode(TeachModeConfig(include_examples=False))
        report = teacher.explain("strategy pattern")
        assert report.explanation is not None
        assert len(report.explanation.examples) == 0

    def test_format_report(self):
        teacher = TeachMode(TeachModeConfig())
        report = teacher.explain("dependency injection")
        output = format_teach_report(report)
        assert "Teach Mode" in output
        assert "dependency injection" in output
        assert "Examples" in output
