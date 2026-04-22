"""Tests for the Dockerfile optimizer."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from code_agents.devops.dockerfile_optimizer import (
    DockerfileOptimizer, Finding, OptimizationResult, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW,
)


class TestFinding:
    """Test Finding dataclass."""

    def test_fields(self):
        f = Finding(rule="test", severity="high", line=10, message="msg", suggestion="fix")
        assert f.rule == "test"
        assert f.severity == "high"
        assert f.line == 10

    def test_suggestion(self):
        f = Finding(rule="r", severity="low", line=1, message="m", suggestion="do this")
        assert f.suggestion == "do this"


class TestOptimizationResult:
    """Test OptimizationResult dataclass."""

    def test_empty_result(self):
        r = OptimizationResult()
        assert r.score == 100
        assert r.stages == 1
        assert r.summary == "Score 100/100 | 0 high, 0 medium, 0 low findings"

    def test_summary_with_findings(self):
        r = OptimizationResult(findings=[
            Finding(rule="a", severity=SEVERITY_HIGH, line=1, message="m", suggestion="s"),
            Finding(rule="b", severity=SEVERITY_LOW, line=2, message="m", suggestion="s"),
        ])
        assert "1 high" in r.summary
        assert "1 low" in r.summary


class TestDockerfileOptimizer:
    """Test DockerfileOptimizer analysis."""

    def test_missing_dockerfile(self, tmp_path):
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        result = opt.analyze()
        assert result.score == 0
        assert any(f.rule == "missing-dockerfile" for f in result.findings)

    def test_no_user_instruction(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\nRUN pip install flask\nCMD python app.py\n")
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        result = opt.analyze()
        assert any(f.rule == "no-user" for f in result.findings)

    def test_user_root_flagged(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\nUSER root\nCMD python app.py\n")
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        result = opt.analyze()
        assert any(f.rule == "user-root" for f in result.findings)

    def test_add_vs_copy(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\nADD . /app\nUSER app\nCMD python app.py\n")
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        result = opt.analyze()
        assert any(f.rule == "prefer-copy" for f in result.findings)

    def test_add_with_url_ok(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\nADD https://example.com/file.tar.gz /tmp/\nUSER app\nCMD python app.py\n")
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        result = opt.analyze()
        assert not any(f.rule == "prefer-copy" for f in result.findings)

    def test_layer_ordering_bad(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\nCOPY . /app\nRUN pip install -r requirements.txt\nUSER app\nCMD python app.py\n")
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        result = opt.analyze()
        assert any(f.rule == "layer-ordering" for f in result.findings)

    def test_no_multi_stage_with_build_tools(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\nRUN apt-get install gcc && rm -rf /var/lib/apt/lists/*\nUSER app\nCMD python app.py\n")
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        result = opt.analyze()
        assert any(f.rule == "no-multi-stage" for f in result.findings)

    def test_dockerignore_present(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\nUSER app\nHEALTHCHECK CMD curl -f http://localhost/\nCMD python app.py\n")
        (tmp_path / ".dockerignore").write_text("node_modules\n.git\n")
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        result = opt.analyze()
        assert result.has_dockerignore is True
        assert not any(f.rule == "no-dockerignore" for f in result.findings)

    def test_unpinned_base_image(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python\nUSER app\nCMD python app.py\n")
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        result = opt.analyze()
        assert any(f.rule == "unpinned-base" for f in result.findings)

    def test_apt_no_cleanup(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\nRUN apt-get install -y curl\nUSER app\nCMD python app.py\n")
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        result = opt.analyze()
        assert any(f.rule == "apt-no-cleanup" for f in result.findings)

    def test_score_deductions(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python\nRUN apt-get install -y curl\nADD . /app\nCMD python app.py\n")
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        result = opt.analyze()
        assert result.score < 100

    def test_parse_layers(self, tmp_path):
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\n# comment\nCOPY . /app\nRUN echo hi\n")
        opt = DockerfileOptimizer(cwd=str(tmp_path))
        layers = opt._parse_layers(["FROM python:3.11", "# comment", "COPY . /app", "RUN echo hi"])
        assert len(layers) == 3
        assert layers[0].instruction == "FROM"
