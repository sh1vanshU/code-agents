"""Tests for the intent compiler module."""

from __future__ import annotations

import os
import pytest

from code_agents.knowledge.intent_compiler import (
    IntentCompiler, IntentResult, PlanStep, compile_intent,
)


class TestIntentCompiler:
    """Test IntentCompiler methods."""

    def test_init(self, tmp_path):
        compiler = IntentCompiler(cwd=str(tmp_path))
        assert compiler.cwd == str(tmp_path)

    def test_compile_simple_feature(self, tmp_path):
        (tmp_path / "services").mkdir()
        (tmp_path / "services" / "user_service.py").write_text("class UserService:\n    pass\n")

        compiler = IntentCompiler(cwd=str(tmp_path))
        result = compiler.compile("Add a new endpoint to create users with validation")
        assert isinstance(result, IntentResult)
        assert "api" in result.layers_affected
        assert len(result.steps) >= 2
        assert result.estimated_effort in ("small", "medium", "large", "epic")

    def test_compile_identifies_layers(self, tmp_path):
        compiler = IntentCompiler(cwd=str(tmp_path))
        result = compiler.compile(
            "Create a database model for products with a REST endpoint and React component"
        )
        assert "data" in result.layers_affected
        assert "api" in result.layers_affected
        assert "ui" in result.layers_affected
        assert "test" in result.layers_affected

    def test_compile_includes_tests_always(self, tmp_path):
        compiler = IntentCompiler(cwd=str(tmp_path))
        result = compiler.compile("Add a utility function for string formatting")
        assert "test" in result.layers_affected

    def test_compile_risk_assessment(self, tmp_path):
        compiler = IntentCompiler(cwd=str(tmp_path))
        result = compiler.compile("Migrate the database schema and update authentication")
        assert len(result.risks) >= 1
        assert any("migration" in r.lower() or "security" in r.lower() for r in result.risks)

    def test_compile_finds_affected_files(self, tmp_path):
        (tmp_path / "user_service.py").write_text("class UserService:\n    pass\n")
        (tmp_path / "user_model.py").write_text("class User:\n    pass\n")

        compiler = IntentCompiler(cwd=str(tmp_path))
        result = compiler.compile("Update the user service to add email validation")
        assert isinstance(result.affected_files, list)

    def test_convenience_function(self, tmp_path):
        result = compile_intent(cwd=str(tmp_path), description="Add logging to all modules")
        assert isinstance(result, dict)
        assert "steps" in result
        assert "layers_affected" in result
        assert "estimated_effort" in result
