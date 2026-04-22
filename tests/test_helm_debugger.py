"""Tests for the Helm chart debugger."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from code_agents.devops.helm_debugger import (
    HelmDebugger, DebugResult, RenderError, ValueMismatch,
)


class TestDebugResult:
    """Test DebugResult dataclass."""

    def test_defaults(self):
        r = DebugResult()
        assert r.success is True
        assert r.rendered_templates == {}
        assert r.summary == "0 templates, 0 errors, 0 mismatches"

    def test_summary(self):
        r = DebugResult(
            rendered_templates={"a.yaml": "content"},
            render_errors=[RenderError(template="b", line=1, message="err", suggestion="fix")],
        )
        assert "1 templates" in r.summary
        assert "1 errors" in r.summary


class TestHelmDebugger:
    """Test HelmDebugger methods."""

    def test_render_helm_not_found(self, tmp_path):
        debugger = HelmDebugger(cwd=str(tmp_path))
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = debugger.render("./chart")
        assert result.success is False
        assert any("helm CLI not found" in e.message for e in result.render_errors)

    def test_render_timeout(self, tmp_path):
        import subprocess
        debugger = HelmDebugger(cwd=str(tmp_path))
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            result = debugger.render("./chart")
        assert result.success is False
        assert any("timed out" in w for w in result.warnings)

    def test_render_success(self, tmp_path):
        debugger = HelmDebugger(cwd=str(tmp_path))
        rendered = "---\n# Source: mychart/templates/deployment.yaml\napiVersion: apps/v1\nkind: Deployment\n---\n# Source: mychart/templates/service.yaml\napiVersion: v1\nkind: Service"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=rendered, stderr="")
            result = debugger.render("./chart")
        assert result.success is True
        assert len(result.rendered_templates) == 2

    def test_render_error_parsing(self, tmp_path):
        debugger = HelmDebugger(cwd=str(tmp_path))
        stderr = 'Error: template: mychart/templates/deploy.yaml:15:3: executing "mychart/templates/deploy.yaml" at <.Values.missing>: nil pointer evaluating'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr=stderr)
            result = debugger.render("./chart")
        assert result.success is False
        assert len(result.render_errors) >= 1
        assert result.render_errors[0].line == 15

    def test_diff_values_with_yaml(self, tmp_path):
        left = tmp_path / "values-dev.yaml"
        right = tmp_path / "values-prod.yaml"
        left.write_text("replicas: 1\nimage: app:dev\n")
        right.write_text("replicas: 3\nimage: app:prod\n")

        debugger = HelmDebugger(cwd=str(tmp_path))
        # Use regex fallback
        mismatches = debugger.diff_values(str(left), str(right))
        assert len(mismatches) >= 1

    def test_mismatch_severity_sensitive(self):
        assert HelmDebugger._mismatch_severity("db.password", "a", "b") == "error"
        assert HelmDebugger._mismatch_severity("api.token", "a", "b") == "error"

    def test_mismatch_severity_resource(self):
        assert HelmDebugger._mismatch_severity("app.replicas", "1", "3") == "warning"
        assert HelmDebugger._mismatch_severity("resources.cpu.limit", "100m", "500m") == "warning"

    def test_mismatch_severity_info(self):
        assert HelmDebugger._mismatch_severity("app.name", "a", "b") == "info"

    def test_suggest_fix_nil_pointer(self):
        assert "nil check" in HelmDebugger._suggest_fix("nil pointer evaluating")

    def test_suggest_fix_not_defined(self):
        assert "defined" in HelmDebugger._suggest_fix("variable not defined")

    def test_lint_not_found(self, tmp_path):
        debugger = HelmDebugger(cwd=str(tmp_path))
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = debugger.lint("./chart")
        assert result.success is False

    def test_check_rendered_nil(self, tmp_path):
        debugger = HelmDebugger(cwd=str(tmp_path))
        warnings = debugger._check_rendered({"deploy.yaml": "replicas: <nil>"})
        assert any("<nil>" in w for w in warnings)

    def test_split_templates(self, tmp_path):
        debugger = HelmDebugger(cwd=str(tmp_path))
        output = "---\n# Source: chart/templates/a.yaml\napiVersion: v1\n---\n# Source: chart/templates/b.yaml\nkind: Service"
        templates = debugger._split_templates(output)
        assert len(templates) == 2
