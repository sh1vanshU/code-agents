"""Tests for the inverse coder module."""

from __future__ import annotations

import os
import pytest

from code_agents.knowledge.inverse_coder import (
    InverseCoder, InverseResult, ImplementationComponent, inverse_code,
)


class TestInverseCoder:
    """Test InverseCoder methods."""

    def test_init(self, tmp_path):
        coder = InverseCoder(cwd=str(tmp_path))
        assert coder.cwd == str(tmp_path)

    def test_reverse_engineer_api_output(self, tmp_path):
        (tmp_path / "app.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
        coder = InverseCoder(cwd=str(tmp_path))
        result = coder.reverse_engineer("JSON API response for user profile data")
        assert isinstance(result, InverseResult)
        assert result.output_type == "json_response"
        assert len(result.components) >= 2  # service + handler + tests at minimum

    def test_reverse_engineer_cli_output(self, tmp_path):
        coder = InverseCoder(cwd=str(tmp_path))
        result = coder.reverse_engineer("CLI command that prints a report to the terminal")
        assert result.output_type == "cli_output"

    def test_components_include_tests(self, tmp_path):
        coder = InverseCoder(cwd=str(tmp_path))
        result = coder.reverse_engineer("Transform CSV data into JSON format")
        test_components = [c for c in result.components if c.component_type == "test"]
        assert len(test_components) >= 1

    def test_detects_tech_stack(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'myapp'\n")
        coder = InverseCoder(cwd=str(tmp_path))
        result = coder.reverse_engineer("API endpoint for data processing")
        assert "Python/Poetry" in result.tech_stack

    def test_data_flow_ordering(self, tmp_path):
        coder = InverseCoder(cwd=str(tmp_path))
        result = coder.reverse_engineer(
            "Store user data in database and return JSON response via API endpoint"
        )
        assert len(result.data_flow) >= 1
        assert isinstance(result.data_flow, list)

    def test_convenience_function(self, tmp_path):
        result = inverse_code(
            cwd=str(tmp_path),
            desired_output="Generate a PDF report from database records",
        )
        assert isinstance(result, dict)
        assert "components" in result
        assert "output_type" in result
        assert "estimated_complexity" in result
