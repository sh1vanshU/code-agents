"""Tests for the dependency decay forecast module."""

from __future__ import annotations

import json
import os
import pytest

from code_agents.domain.dep_decay_forecast import (
    DepDecayForecaster, DepDecayResult, DependencyRisk, forecast_dep_decay,
)


class TestDepDecayForecaster:
    """Test DepDecayForecaster methods."""

    def test_init(self, tmp_path):
        forecaster = DepDecayForecaster(cwd=str(tmp_path))
        assert forecaster.cwd == str(tmp_path)

    def test_analyze_no_dep_file(self, tmp_path):
        forecaster = DepDecayForecaster(cwd=str(tmp_path))
        result = forecaster.analyze()
        assert isinstance(result, DepDecayResult)
        assert result.dependencies_analyzed == 0

    def test_analyze_requirements_txt(self, tmp_path):
        (tmp_path / "requirements.txt").write_text(
            "fastapi>=0.100.0\nrequests==2.31.0\npydantic>=2.0\n"
        )
        forecaster = DepDecayForecaster(cwd=str(tmp_path))
        result = forecaster.analyze()
        assert result.dependencies_analyzed == 3
        assert len(result.risks) == 3
        assert len(result.forecasts) == 3

    def test_analyze_pyproject_toml(self, tmp_path):
        content = """[tool.poetry.dependencies]
python = "^3.10"
fastapi = "^0.100"
requests = "^2.31"

[tool.poetry.group.dev.dependencies]
pytest = "^7.0"
"""
        (tmp_path / "pyproject.toml").write_text(content)
        forecaster = DepDecayForecaster(cwd=str(tmp_path))
        result = forecaster.analyze(include_dev=False)
        assert result.dependencies_analyzed == 2  # python excluded

    def test_risk_levels(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("urllib3==1.26.0\nfastapi>=0.100\n")
        forecaster = DepDecayForecaster(cwd=str(tmp_path))
        result = forecaster.analyze()
        # urllib3 has known CVEs, should be higher risk
        urllib_risk = next((r for r in result.risks if r.name == "urllib3"), None)
        assert urllib_risk is not None
        assert urllib_risk.cve_count > 0

    def test_overall_health(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("fastapi>=0.100\npydantic>=2.0\n")
        forecaster = DepDecayForecaster(cwd=str(tmp_path))
        result = forecaster.analyze()
        assert 0 <= result.overall_health <= 100

    def test_convenience_function(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
        result = forecast_dep_decay(cwd=str(tmp_path))
        assert isinstance(result, dict)
        assert "overall_health" in result
        assert "risks" in result
        assert "forecasts" in result
