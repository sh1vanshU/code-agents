"""Tests for the config file validator."""

from __future__ import annotations

import json
import os
import pytest

from code_agents.devops.config_validator import (
    ConfigValidator, ConfigFinding, format_config_report, _levenshtein,
)


class TestLevenshtein:
    """Test Levenshtein distance calculation."""

    def test_identical(self):
        assert _levenshtein("abc", "abc") == 0

    def test_one_edit(self):
        assert _levenshtein("abc", "abd") == 1
        assert _levenshtein("abc", "abcd") == 1

    def test_empty(self):
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "") == 3

    def test_symmetric(self):
        assert _levenshtein("kitten", "sitting") == _levenshtein("sitting", "kitten")


class TestValidateYaml:
    """Test YAML validation."""

    def test_valid_yaml(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("key: value\nlist:\n  - item1\n  - item2\n")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_yaml("config.yaml")
        errors = [f for f in findings if f.severity == "error"]
        assert len(errors) == 0

    def test_tab_indentation(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("key:\n\tvalue: 1\n")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_yaml("bad.yaml")
        tab_findings = [f for f in findings if "tab" in f.issue.lower() or "Tab" in f.issue]
        assert len(tab_findings) >= 1

    def test_empty_yaml(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_yaml("empty.yaml")
        # Should warn about empty file
        assert any("empty" in f.issue.lower() for f in findings)

    def test_invalid_yaml_syntax(self, tmp_path):
        f = tmp_path / "broken.yaml"
        f.write_text("key: [unclosed\n")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_yaml("broken.yaml")
        errors = [f for f in findings if f.severity == "error"]
        assert len(errors) >= 1


class TestValidateJson:
    """Test JSON validation."""

    def test_valid_json(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text('{"key": "value", "num": 42}')
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_json("config.json")
        errors = [f for f in findings if f.severity == "error"]
        assert len(errors) == 0

    def test_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text('{"key": value}')
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_json("bad.json")
        assert any(f.severity == "error" for f in findings)

    def test_empty_json(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_json("empty.json")
        assert any("empty" in f.issue.lower() for f in findings)

    def test_null_values(self, tmp_path):
        f = tmp_path / "nulls.json"
        f.write_text('{"key": null, "other": ""}')
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_json("nulls.json")
        # Should have info-level findings for null and empty
        assert any("null" in f.issue.lower() for f in findings)


class TestValidateToml:
    """Test TOML validation."""

    def test_valid_toml(self, tmp_path):
        f = tmp_path / "config.toml"
        f.write_text('[section]\nkey = "value"\nnum = 42\n')
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_toml("config.toml")
        errors = [f for f in findings if f.severity == "error"]
        assert len(errors) == 0

    def test_empty_toml(self, tmp_path):
        f = tmp_path / "empty.toml"
        f.write_text("")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_toml("empty.toml")
        assert any("empty" in f.issue.lower() for f in findings)


class TestValidateEnv:
    """Test .env validation."""

    def test_valid_env(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("DEBUG=true\nPORT=8000\n")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_env(".env")
        errors = [f for f in findings if f.severity == "error"]
        assert len(errors) == 0

    def test_empty_values(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("API_KEY=\nSECRET_KEY=''\n")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_env(".env")
        assert any("empty" in f.issue.lower() for f in findings)

    def test_duplicate_keys(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("PORT=8000\nDEBUG=true\nPORT=9000\n")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_env(".env")
        assert any("duplicate" in f.issue.lower() for f in findings)

    def test_no_equals(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("BADLINE\nGOOD=value\n")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_env(".env")
        assert any("no '='" in f.issue.lower() or "separator" in f.issue.lower() for f in findings)

    def test_typo_detection(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("DEUBG=true\n")  # typo for DEBUG
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v._validate_env(".env")
        assert any("typo" in f.issue.lower() or "did you mean" in f.suggestion.lower() for f in findings)


class TestValidateFull:
    """Test full validation scan."""

    def test_scan_project(self, tmp_path):
        (tmp_path / "config.yaml").write_text("key: value\n")
        (tmp_path / "settings.json").write_text('{"a": 1}')
        (tmp_path / ".env").write_text("X=1\n")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v.validate()
        # Should run without errors
        assert isinstance(findings, list)

    def test_skips_hidden_dirs(self, tmp_path):
        hidden = tmp_path / ".git"
        hidden.mkdir()
        (hidden / "config").write_text("bad yaml: [")
        v = ConfigValidator(cwd=str(tmp_path))
        findings = v.validate()
        assert all(".git" not in f.file for f in findings)


class TestFormatConfigReport:
    """Test report formatting."""

    def test_empty(self):
        report = format_config_report([])
        assert "no issues" in report.lower()

    def test_with_findings(self):
        findings = [
            ConfigFinding(file=".env", line=1, issue="Empty value", severity="warning", suggestion="Set a value"),
            ConfigFinding(file="config.yaml", line=5, issue="Tab indent", severity="error", suggestion="Use spaces"),
        ]
        report = format_config_report(findings)
        assert ".env" in report
        assert "config.yaml" in report
        assert "Summary" in report
