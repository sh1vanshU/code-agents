"""Tests for the schema evolution simulator module."""

from __future__ import annotations

import os
import pytest

from code_agents.api.schema_evolution_sim import (
    SchemaEvolutionSimulator, SchemaEvolutionResult, SchemaChange,
    simulate_schema_evolution,
)


class TestSchemaEvolutionSimulator:
    """Test SchemaEvolutionSimulator methods."""

    def test_init(self, tmp_path):
        sim = SchemaEvolutionSimulator(cwd=str(tmp_path))
        assert sim.cwd == str(tmp_path)

    def test_simulate_no_changes(self, tmp_path):
        old = {"name": "str", "age": "int"}
        new = {"name": "str", "age": "int"}
        sim = SchemaEvolutionSimulator(cwd=str(tmp_path))
        result = sim.simulate(old_schema=old, new_schema=new)
        assert isinstance(result, SchemaEvolutionResult)
        assert len(result.changes) == 0
        assert result.compat_report.is_compatible is True

    def test_simulate_field_removed(self, tmp_path):
        old = {"name": "str", "age": "int", "email": "str"}
        new = {"name": "str", "age": "int"}
        sim = SchemaEvolutionSimulator(cwd=str(tmp_path))
        result = sim.simulate(old_schema=old, new_schema=new)
        removed = [c for c in result.changes if c.change_type == "field_removed"]
        assert len(removed) == 1
        assert removed[0].field_name == "email"
        assert removed[0].is_breaking is True

    def test_simulate_field_type_changed(self, tmp_path):
        old = {"count": "int", "name": "str"}
        new = {"count": "str", "name": "str"}
        sim = SchemaEvolutionSimulator(cwd=str(tmp_path))
        result = sim.simulate(old_schema=old, new_schema=new)
        type_changes = [c for c in result.changes if c.change_type == "field_type_changed"]
        assert len(type_changes) == 1
        assert type_changes[0].is_breaking is True

    def test_simulate_optional_field_added(self, tmp_path):
        old = {"name": "str"}
        new = {"name": "str", "bio": "Optional[str]"}
        sim = SchemaEvolutionSimulator(cwd=str(tmp_path))
        result = sim.simulate(old_schema=old, new_schema=new)
        safe = [c for c in result.changes if c.change_type == "optional_field_added"]
        assert len(safe) == 1
        assert safe[0].is_breaking is False
        assert result.compat_report.is_compatible is True

    def test_recommended_strategy(self, tmp_path):
        old = {"a": "int", "b": "str", "c": "float", "d": "bool"}
        new = {"a": "str", "b": "int", "c": "str", "d": "str"}  # 4 type changes
        sim = SchemaEvolutionSimulator(cwd=str(tmp_path))
        result = sim.simulate(old_schema=old, new_schema=new)
        assert result.recommended_strategy == "versioned"

    def test_convenience_function(self, tmp_path):
        result = simulate_schema_evolution(
            cwd=str(tmp_path),
            old_schema={"x": "int"},
            new_schema={"x": "int", "y": "str"},
        )
        assert isinstance(result, dict)
        assert "is_compatible" in result
        assert "changes" in result
        assert "recommended_strategy" in result
