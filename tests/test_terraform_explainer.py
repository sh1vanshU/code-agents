"""Tests for the Terraform plan explainer."""

from __future__ import annotations

import json
import os
import pytest

from code_agents.devops.terraform_explainer import (
    TerraformExplainer, ResourceChange, ExplanationResult,
)


class TestResourceChange:
    """Test ResourceChange dataclass."""

    def test_defaults(self):
        rc = ResourceChange(address="aws_s3_bucket.main", resource_type="aws_s3_bucket", action="create")
        assert rc.risk == "low"
        assert rc.changed_attributes == []

    def test_custom_risk(self):
        rc = ResourceChange(address="a", resource_type="aws_db_instance", action="delete", risk="critical")
        assert rc.risk == "critical"


class TestExplanationResult:
    """Test ExplanationResult."""

    def test_counts(self):
        r = ExplanationResult(changes=[
            ResourceChange(address="a", resource_type="t", action="create"),
            ResourceChange(address="b", resource_type="t", action="create"),
            ResourceChange(address="c", resource_type="t", action="delete"),
        ])
        assert r.counts == {"create": 2, "delete": 1}

    def test_empty(self):
        r = ExplanationResult()
        assert r.counts == {}


class TestTerraformExplainer:
    """Test TerraformExplainer."""

    def _make_plan(self, resource_changes):
        return {"resource_changes": resource_changes}

    def _make_rc(self, address="aws_s3_bucket.main", rtype="aws_s3_bucket",
                 actions=None, before=None, after=None):
        return {
            "address": address,
            "type": rtype,
            "change": {
                "actions": actions or ["create"],
                "before": before,
                "after": after or {"bucket": "my-bucket"},
            },
        }

    def test_explain_create(self, tmp_path):
        explainer = TerraformExplainer(cwd=str(tmp_path))
        plan = self._make_plan([self._make_rc()])
        result = explainer.explain(plan)
        assert len(result.changes) == 1
        assert result.changes[0].action == "create"
        assert "Create" in result.plain_english[0]

    def test_explain_delete(self, tmp_path):
        explainer = TerraformExplainer(cwd=str(tmp_path))
        plan = self._make_plan([self._make_rc(actions=["delete"], before={"bucket": "old"})])
        result = explainer.explain(plan)
        assert result.changes[0].action == "delete"
        assert any("destroyed" in w or "destroy" in w.lower() for w in result.warnings)

    def test_explain_replace(self, tmp_path):
        explainer = TerraformExplainer(cwd=str(tmp_path))
        plan = self._make_plan([self._make_rc(actions=["delete", "create"])])
        result = explainer.explain(plan)
        assert result.changes[0].action == "replace"

    def test_explain_noop_filtered(self, tmp_path):
        explainer = TerraformExplainer(cwd=str(tmp_path))
        plan = self._make_plan([self._make_rc(actions=["no-op"])])
        result = explainer.explain(plan)
        assert len(result.changes) == 0

    def test_risk_critical_for_db_delete(self, tmp_path):
        explainer = TerraformExplainer(cwd=str(tmp_path))
        plan = self._make_plan([
            self._make_rc(address="aws_db_instance.main", rtype="aws_db_instance",
                          actions=["delete"], before={"engine": "postgres"}),
        ])
        result = explainer.explain(plan)
        assert result.changes[0].risk == "critical"
        assert result.risk_level == "critical"

    def test_risk_high_for_iam(self, tmp_path):
        explainer = TerraformExplainer(cwd=str(tmp_path))
        plan = self._make_plan([
            self._make_rc(address="aws_iam_role.admin", rtype="aws_iam_role", actions=["update"]),
        ])
        result = explainer.explain(plan)
        assert result.changes[0].risk == "high"

    def test_explain_from_json_string(self, tmp_path):
        explainer = TerraformExplainer(cwd=str(tmp_path))
        plan = self._make_plan([self._make_rc()])
        result = explainer.explain(json.dumps(plan))
        assert len(result.changes) == 1

    def test_explain_from_file(self, tmp_path):
        explainer = TerraformExplainer(cwd=str(tmp_path))
        plan = self._make_plan([self._make_rc()])
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))
        result = explainer.explain_file(str(plan_file))
        assert len(result.changes) == 1

    def test_invalid_json(self, tmp_path):
        explainer = TerraformExplainer(cwd=str(tmp_path))
        result = explainer.explain("not valid json")
        assert "Failed" in result.summary

    def test_summary_format(self, tmp_path):
        explainer = TerraformExplainer(cwd=str(tmp_path))
        plan = self._make_plan([
            self._make_rc(address="a", actions=["create"]),
            self._make_rc(address="b", actions=["update"], before={"x": "1"}, after={"x": "2"}),
        ])
        result = explainer.explain(plan)
        assert "Plan:" in result.summary
        assert "risk" in result.summary.lower()

    def test_iam_warnings(self, tmp_path):
        explainer = TerraformExplainer(cwd=str(tmp_path))
        plan = self._make_plan([
            self._make_rc(address="aws_iam_policy.x", rtype="aws_iam_policy", actions=["update"]),
        ])
        result = explainer.explain(plan)
        assert any("IAM" in w for w in result.warnings)
