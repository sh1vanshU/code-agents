"""Tests for terraform_client.py — unit tests with mocked subprocess."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.cicd.terraform_client import TerraformClient, TerraformError


class TestTerraformClientInit:
    def test_defaults(self):
        c = TerraformClient()
        assert c.binary in ("terraform", "")  # depends on PATH
        assert c.timeout == 300.0

    def test_custom_init(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="/usr/local/bin/terraform", timeout=600.0)
        assert "/tmp/tf" in c.working_dir
        assert c.binary == "/usr/local/bin/terraform"
        assert c.timeout == 600.0


def _mock_run(stdout: str = "", stderr: str = "", rc: int = 0):
    """Patch TerraformClient._run to return predefined output."""
    async def _fake_run(*args, **kwargs):
        return stdout, stderr, rc
    return _fake_run


class TestTerraformInit:
    def test_success(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        with patch.object(c, "_run", side_effect=_mock_run("Terraform has been successfully initialized!", "", 0)):
            result = asyncio.run(c.init())
            assert result["status"] == "initialized"

    def test_failure(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        with patch.object(c, "_run", side_effect=_mock_run("", "Error: Failed to initialize", 1)):
            with pytest.raises(TerraformError):
                asyncio.run(c.init())


class TestTerraformValidate:
    def test_valid(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        valid_json = json.dumps({"valid": True, "error_count": 0, "warning_count": 0})
        with patch.object(c, "_run", side_effect=_mock_run(valid_json, "", 0)):
            result = asyncio.run(c.validate())
            assert result["valid"] is True

    def test_invalid(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        invalid_json = json.dumps({"valid": False, "error_count": 2})
        with patch.object(c, "_run", side_effect=_mock_run(invalid_json, "Errors found", 1)):
            result = asyncio.run(c.validate())
            assert result["valid"] is False


class TestTerraformPlan:
    def test_no_changes(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        with patch.object(c, "_run", side_effect=_mock_run("No changes. Your infrastructure matches the configuration.", "", 0)):
            result = asyncio.run(c.plan())
            assert result["no_changes"] is True

    def test_changes(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        output = "Plan: 3 to add, 1 to change, 0 to destroy."
        with patch.object(c, "_run", side_effect=_mock_run(output, "", 2)):
            result = asyncio.run(c.plan())
            assert result["add"] == 3
            assert result["change"] == 1
            assert result["destroy"] == 0

    def test_failure(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        with patch.object(c, "_run", side_effect=_mock_run("", "Error: Invalid reference", 1)):
            with pytest.raises(TerraformError):
                asyncio.run(c.plan())


class TestTerraformApply:
    def test_success(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        output = "Apply complete! Resources: 3 added, 1 changed, 0 destroyed."
        with patch.object(c, "_run", side_effect=_mock_run(output, "", 0)):
            result = asyncio.run(c.apply(auto_approve=True))
            assert result["status"] == "applied"

    def test_failure(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        with patch.object(c, "_run", side_effect=_mock_run("", "Error: creating resource", 1)):
            with pytest.raises(TerraformError):
                asyncio.run(c.apply(auto_approve=True))


class TestTerraformStateList:
    def test_success(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        output = "aws_s3_bucket.logs\naws_ecs_service.app\naws_rds_instance.main\n"
        with patch.object(c, "_run", side_effect=_mock_run(output, "", 0)):
            result = asyncio.run(c.state_list())
            assert len(result) == 3
            assert "aws_s3_bucket.logs" in result


class TestTerraformStateShow:
    def test_success(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        with patch.object(c, "_run", side_effect=_mock_run("resource details here", "", 0)):
            result = asyncio.run(c.state_show("aws_s3_bucket.logs"))
            assert result["address"] == "aws_s3_bucket.logs"


class TestTerraformOutput:
    def test_success(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        output_json = json.dumps({"vpc_id": {"value": "vpc-123", "type": "string"}})
        with patch.object(c, "_run", side_effect=_mock_run(output_json, "", 0)):
            result = asyncio.run(c.output())
            assert "vpc_id" in result


class TestTerraformFmt:
    def test_check_clean(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        with patch.object(c, "_run", side_effect=_mock_run("", "", 0)):
            result = asyncio.run(c.fmt(check=True))
            assert result["formatted"] is True

    def test_check_dirty(self):
        c = TerraformClient(working_dir="/tmp/tf", binary="terraform")
        with patch.object(c, "_run", side_effect=_mock_run("--- main.tf\n+++ main.tf", "", 3)):
            result = asyncio.run(c.fmt(check=True))
            assert result["formatted"] is False


class TestParsePlanSummary:
    def test_with_changes(self):
        c = TerraformClient()
        summary = c._parse_plan_summary("Plan: 2 to add, 1 to change, 3 to destroy.")
        assert summary["add"] == 2
        assert summary["change"] == 1
        assert summary["destroy"] == 3

    def test_no_changes(self):
        c = TerraformClient()
        summary = c._parse_plan_summary("No changes. Your infrastructure matches the configuration.")
        assert summary["no_changes"] is True

    def test_empty(self):
        c = TerraformClient()
        summary = c._parse_plan_summary("")
        assert summary["add"] == 0
        assert summary["no_changes"] is False
