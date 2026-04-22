"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdDeadcode:
    """Test deadcode command."""

    def test_deadcode_default(self, capsys):
        from code_agents.cli.cli_analysis import cmd_deadcode
        mock_report = MagicMock()
        with patch("code_agents.analysis.deadcode.DeadCodeFinder") as MockFinder, \
             patch("code_agents.analysis.deadcode.format_deadcode_report", return_value="Deadcode report"):
            MockFinder.return_value.scan.return_value = mock_report
            cmd_deadcode([])
        output = capsys.readouterr().out
        assert "Dead Code Finder" in output
        assert "Deadcode report" in output

    def test_deadcode_json(self, capsys):
        from code_agents.cli.cli_analysis import cmd_deadcode
        from dataclasses import dataclass, field

        @dataclass
        class FakeReport:
            language: str = "python"
            unused_imports: list = field(default_factory=list)
            unused_functions: list = field(default_factory=list)
            orphan_endpoints: list = field(default_factory=list)

        with patch("code_agents.analysis.deadcode.DeadCodeFinder") as MockFinder:
            MockFinder.return_value.scan.return_value = FakeReport()
            cmd_deadcode(["--json"])
        output = capsys.readouterr().out
        assert '"language"' in output
        assert '"python"' in output

    def test_deadcode_language_override(self, capsys):
        from code_agents.cli.cli_analysis import cmd_deadcode
        mock_report = MagicMock()
        with patch("code_agents.analysis.deadcode.DeadCodeFinder") as MockFinder, \
             patch("code_agents.analysis.deadcode.format_deadcode_report", return_value="report"):
            MockFinder.return_value.scan.return_value = mock_report
            cmd_deadcode(["--language", "java"])
        MockFinder.assert_called_once()
        call_kwargs = MockFinder.call_args
        assert call_kwargs[1].get("language") == "java" or call_kwargs.kwargs.get("language") == "java"
class TestCmdFlags:
    """Test feature flags command."""

    def test_flags_no_flags_found(self, capsys):
        from code_agents.cli.cli_analysis import cmd_flags
        mock_report = MagicMock()
        mock_report.total_flags = 0
        with patch("code_agents.analysis.feature_flags.FeatureFlagScanner") as MockScanner:
            MockScanner.return_value.scan.return_value = mock_report
            cmd_flags([])
        output = capsys.readouterr().out
        assert "No feature flags detected" in output

    def test_flags_with_results(self, capsys):
        from code_agents.cli.cli_analysis import cmd_flags
        mock_report = MagicMock()
        mock_report.total_flags = 5
        mock_report.stale_flags = []
        with patch("code_agents.analysis.feature_flags.FeatureFlagScanner") as MockScanner, \
             patch("code_agents.analysis.feature_flags.format_flag_report", return_value="Flag Report"):
            MockScanner.return_value.scan.return_value = mock_report
            cmd_flags([])
        output = capsys.readouterr().out
        assert "Flag Report" in output

    def test_flags_stale_only(self, capsys):
        from code_agents.cli.cli_analysis import cmd_flags
        mock_flag = MagicMock()
        mock_flag.name = "OLD_FLAG"
        mock_flag.file = ".env"
        mock_flag.line = 10
        mock_report = MagicMock()
        mock_report.total_flags = 3
        mock_report.stale_flags = [mock_flag]
        with patch("code_agents.analysis.feature_flags.FeatureFlagScanner") as MockScanner:
            MockScanner.return_value.scan.return_value = mock_report
            cmd_flags(["--stale"])
        output = capsys.readouterr().out
        assert "Stale Flags" in output
        assert "OLD_FLAG" in output

    def test_flags_stale_none(self, capsys):
        from code_agents.cli.cli_analysis import cmd_flags
        mock_report = MagicMock()
        mock_report.total_flags = 3
        mock_report.stale_flags = []
        with patch("code_agents.analysis.feature_flags.FeatureFlagScanner") as MockScanner:
            MockScanner.return_value.scan.return_value = mock_report
            cmd_flags(["--stale"])
        output = capsys.readouterr().out
        assert "No stale flags" in output

    def test_flags_matrix(self, capsys):
        from code_agents.cli.cli_analysis import cmd_flags
        mock_report = MagicMock()
        mock_report.total_flags = 2
        mock_report.env_matrix = {
            "FEATURE_A": {"dev": "true", "prod": "false"},
            "FEATURE_B": {"dev": "true", "prod": "true"},
        }
        with patch("code_agents.analysis.feature_flags.FeatureFlagScanner") as MockScanner:
            MockScanner.return_value.scan.return_value = mock_report
            cmd_flags(["--matrix"])
        output = capsys.readouterr().out
        assert "FEATURE_A" in output
        assert "FEATURE_B" in output

    def test_flags_json(self, capsys):
        from code_agents.cli.cli_analysis import cmd_flags
        from dataclasses import dataclass, field

        @dataclass
        class FakeReport:
            total_flags: int = 1
            flags: list = field(default_factory=lambda: [{"name": "F1", "stale": False}])
            stale_flags: list = field(default_factory=list)
            env_matrix: dict = field(default_factory=dict)

        with patch("code_agents.analysis.feature_flags.FeatureFlagScanner") as MockScanner:
            MockScanner.return_value.scan.return_value = FakeReport()
            cmd_flags(["--json"])
        output = capsys.readouterr().out
        assert '"total_flags"' in output
class TestCmdSecurity:
    """Test security scan command."""

    def test_security_default(self, capsys):
        from code_agents.cli.cli_analysis import cmd_security
        mock_report = MagicMock()
        mock_report.findings = []
        with patch("code_agents.analysis.security_scanner.SecurityScanner") as MockScanner, \
             patch("code_agents.analysis.security_scanner.format_security_report", return_value="Security Report"):
            MockScanner.return_value.scan.return_value = mock_report
            cmd_security([])
        output = capsys.readouterr().out
        assert "Security Scanner" in output
        assert "Security Report" in output

    def test_security_with_category(self, capsys):
        from code_agents.cli.cli_analysis import cmd_security
        mock_finding = MagicMock()
        mock_finding.category = "sql-injection"
        mock_report = MagicMock()
        mock_report.findings = [mock_finding, MagicMock(category="xss")]
        with patch("code_agents.analysis.security_scanner.SecurityScanner") as MockScanner, \
             patch("code_agents.analysis.security_scanner.format_security_report", return_value="Filtered Report"):
            MockScanner.return_value.scan.return_value = mock_report
            cmd_security(["--category", "sql-injection"])
        # Only sql-injection findings should remain
        assert len(mock_report.findings) == 1
        assert mock_report.findings[0].category == "sql-injection"

    def test_security_json(self, capsys):
        from code_agents.cli.cli_analysis import cmd_security
        from dataclasses import dataclass, field

        @dataclass
        class FakeReport:
            findings: list = field(default_factory=list)
            total_files: int = 10
            scan_time: float = 1.5

        with patch("code_agents.analysis.security_scanner.SecurityScanner") as MockScanner:
            MockScanner.return_value.scan.return_value = FakeReport()
            cmd_security(["--json"])
        output = capsys.readouterr().out
        assert '"findings"' in output
class TestCmdComplexity:
    """Test complexity analysis command."""

    def test_complexity_default(self, capsys):
        from code_agents.cli.cli_analysis import cmd_complexity
        mock_report = MagicMock()
        with patch("code_agents.analysis.complexity.ComplexityAnalyzer") as MockAnalyzer, \
             patch("code_agents.analysis.complexity.format_complexity_report", return_value="Complexity Report"):
            MockAnalyzer.return_value.analyze.return_value = mock_report
            cmd_complexity([])
        output = capsys.readouterr().out
        assert "Code Complexity Report" in output
        assert "Complexity Report" in output

    def test_complexity_json(self, capsys):
        from code_agents.cli.cli_analysis import cmd_complexity
        from dataclasses import dataclass, field

        @dataclass
        class FakeReport:
            files: list = field(default_factory=list)
            total_complexity: int = 42

        with patch("code_agents.analysis.complexity.ComplexityAnalyzer") as MockAnalyzer:
            MockAnalyzer.return_value.analyze.return_value = FakeReport()
            cmd_complexity(["--json"])
        output = capsys.readouterr().out
        assert '"total_complexity"' in output

    def test_complexity_with_language(self, capsys):
        from code_agents.cli.cli_analysis import cmd_complexity
        mock_report = MagicMock()
        with patch("code_agents.analysis.complexity.ComplexityAnalyzer") as MockAnalyzer, \
             patch("code_agents.analysis.complexity.format_complexity_report", return_value="Report"):
            MockAnalyzer.return_value.analyze.return_value = mock_report
            cmd_complexity(["--language", "python"])
        MockAnalyzer.assert_called_once()
class TestCmdTechDebt:
    """Test techdebt command."""

    def test_techdebt_default(self, capsys):
        from code_agents.cli.cli_analysis import cmd_techdebt
        mock_report = MagicMock()
        with patch("code_agents.reviews.tech_debt.TechDebtScanner") as MockScanner, \
             patch("code_agents.reviews.tech_debt.format_debt_report", return_value="Debt Report"):
            MockScanner.return_value.scan.return_value = mock_report
            cmd_techdebt([])
        output = capsys.readouterr().out
        assert "Tech Debt Tracker" in output
        assert "Debt Report" in output

    def test_techdebt_json(self, capsys):
        from code_agents.cli.cli_analysis import cmd_techdebt
        from dataclasses import dataclass, field

        @dataclass
        class FakeReport:
            items: list = field(default_factory=list)
            total_items: int = 0

        with patch("code_agents.reviews.tech_debt.TechDebtScanner") as MockScanner:
            MockScanner.return_value.scan.return_value = FakeReport()
            cmd_techdebt(["--json"])
        output = capsys.readouterr().out
        assert '"total_items"' in output
class TestCmdConfigDiff:
    """Test config-diff command."""

    def test_config_diff_no_configs(self, capsys):
        from code_agents.cli.cli_analysis import cmd_config_diff
        with patch("code_agents.cli.cli_analysis._load_env"), \
             patch("code_agents.analysis.config_drift.ConfigDriftDetector") as MockDetector:
            MockDetector.return_value.load_configs.return_value = {}
            cmd_config_diff([])
        output = capsys.readouterr().out
        assert "No environment configs detected" in output

    def test_config_diff_compare_all(self, capsys):
        from code_agents.cli.cli_analysis import cmd_config_diff
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_analysis._load_env"), \
             patch("code_agents.analysis.config_drift.ConfigDriftDetector") as MockDetector, \
             patch("code_agents.analysis.config_drift.format_drift_report", return_value="Drift Report"):
            MockDetector.return_value.load_configs.return_value = {"dev": {"k": "v"}, "prod": {"k": "v2"}}
            MockDetector.return_value.compare_all.return_value = mock_report
            cmd_config_diff([])
        output = capsys.readouterr().out
        assert "Drift Report" in output

    def test_config_diff_specific_envs(self, capsys):
        from code_agents.cli.cli_analysis import cmd_config_diff
        mock_diff = MagicMock()
        with patch("code_agents.cli.cli_analysis._load_env"), \
             patch("code_agents.analysis.config_drift.ConfigDriftDetector") as MockDetector, \
             patch("code_agents.analysis.config_drift.format_drift_report", return_value="Diff Output"), \
             patch("code_agents.analysis.config_drift.DriftReport") as MockDriftReport:
            MockDetector.return_value.load_configs.return_value = {"staging": {}, "prod": {}}
            MockDetector.return_value.compare.return_value = mock_diff
            cmd_config_diff(["staging", "prod"])
        output = capsys.readouterr().out
        assert "Diff Output" in output

    def test_config_diff_env_not_found(self, capsys):
        from code_agents.cli.cli_analysis import cmd_config_diff
        with patch("code_agents.cli.cli_analysis._load_env"), \
             patch("code_agents.analysis.config_drift.ConfigDriftDetector") as MockDetector:
            MockDetector.return_value.load_configs.return_value = {"dev": {}, "prod": {}}
            cmd_config_diff(["staging", "prod"])
        output = capsys.readouterr().out
        assert "not found" in output
class TestCmdApiCheck:
    """Test api-check command."""

    def test_api_check_default(self, capsys):
        from code_agents.cli.cli_analysis import cmd_api_check
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_analysis._load_env"), \
             patch("code_agents.cli.cli_analysis._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.api.api_compat.APICompatChecker") as MockChecker:
            MockChecker.return_value.base_ref = "v1.0.0"
            MockChecker.return_value.compare.return_value = mock_report
            MockChecker.return_value.format_report.return_value = "  + POST /new\n  - GET /old\n  COMPATIBLE"
            cmd_api_check([])
        output = capsys.readouterr().out
        assert "API Compatibility Check" in output

    def test_api_check_specific_ref(self, capsys):
        from code_agents.cli.cli_analysis import cmd_api_check
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_analysis._load_env"), \
             patch("code_agents.cli.cli_analysis._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.api.api_compat.APICompatChecker") as MockChecker:
            MockChecker.return_value.base_ref = "v8.0.0"
            MockChecker.return_value.compare.return_value = mock_report
            MockChecker.return_value.format_report.return_value = "All good"
            cmd_api_check(["v8.0.0"])
        output = capsys.readouterr().out
        assert "API Compatibility Check" in output
class TestCmdApidoc:
    """Test apidoc command."""

    def test_apidoc_no_endpoints(self, capsys):
        from code_agents.cli.cli_analysis import cmd_apidoc
        with patch("code_agents.generators.api_doc_generator.APIDocGenerator") as MockGen:
            MockGen.return_value.endpoints = []
            cmd_apidoc([])
        output = capsys.readouterr().out
        assert "No API endpoints discovered" in output

    def test_apidoc_terminal(self, capsys):
        from code_agents.cli.cli_analysis import cmd_apidoc
        with patch("code_agents.generators.api_doc_generator.APIDocGenerator") as MockGen:
            MockGen.return_value.endpoints = [{"method": "GET", "path": "/health"}]
            MockGen.return_value.format_terminal.return_value = "API Terminal Output"
            cmd_apidoc([])
        output = capsys.readouterr().out
        assert "API Terminal Output" in output

    def test_apidoc_json(self, capsys):
        from code_agents.cli.cli_analysis import cmd_apidoc
        with patch("code_agents.generators.api_doc_generator.APIDocGenerator") as MockGen:
            MockGen.return_value.endpoints = [{"method": "GET", "path": "/health"}]
            MockGen.return_value.generate_openapi.return_value = {"openapi": "3.0.0", "paths": {}}
            cmd_apidoc(["--json"])
        output = capsys.readouterr().out
        assert '"openapi"' in output

    def test_apidoc_markdown(self, capsys, tmp_path):
        from code_agents.cli.cli_analysis import cmd_apidoc
        with patch("code_agents.generators.api_doc_generator.APIDocGenerator") as MockGen, \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": str(tmp_path)}):
            MockGen.return_value.endpoints = [{"method": "GET", "path": "/health"}]
            MockGen.return_value.generate_markdown.return_value = "# API Docs"
            cmd_apidoc(["--markdown"])
        output = capsys.readouterr().out
        assert "Saved" in output

    def test_apidoc_openapi(self, capsys, tmp_path):
        from code_agents.cli.cli_analysis import cmd_apidoc
        with patch("code_agents.generators.api_doc_generator.APIDocGenerator") as MockGen, \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": str(tmp_path)}):
            MockGen.return_value.endpoints = [{"method": "GET", "path": "/health"}]
            MockGen.return_value.generate_openapi.return_value = {"openapi": "3.0.0"}
            cmd_apidoc(["--openapi"])
        output = capsys.readouterr().out
        assert "Saved" in output
class TestCmdAudit:
    """Test audit command."""

    def test_audit_default(self, capsys):
        from code_agents.cli.cli_analysis import cmd_audit
        with patch("code_agents.security.dependency_audit.DependencyAuditor") as MockAuditor:
            mock_inst = MockAuditor.return_value
            mock_inst.format_report.return_value = "Audit Report"
            cmd_audit([])
        output = capsys.readouterr().out
        assert "Dependency Audit" in output
        assert "Audit Report" in output

    def test_audit_vuln_only(self, capsys):
        from code_agents.cli.cli_analysis import cmd_audit
        with patch("code_agents.security.dependency_audit.DependencyAuditor") as MockAuditor:
            mock_inst = MockAuditor.return_value
            mock_inst.format_report.return_value = "Vuln Report"
            cmd_audit(["--vuln"])
        output = capsys.readouterr().out
        assert "Vuln Report" in output
        mock_inst.check_licenses.assert_not_called()

    def test_audit_json(self, capsys):
        from code_agents.cli.cli_analysis import cmd_audit
        with patch("code_agents.security.dependency_audit.DependencyAuditor") as MockAuditor:
            mock_inst = MockAuditor.return_value
            mock_inst.to_dict.return_value = {"vulnerabilities": [], "licenses": []}
            cmd_audit(["--json"])
        output = capsys.readouterr().out
        assert '"vulnerabilities"' in output
class TestCmdConfigDiffExtended:
    """Additional config-diff tests."""

    def test_config_diff_json_all(self, capsys):
        from code_agents.cli.cli_analysis import cmd_config_diff
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_analysis._load_env"), \
             patch("code_agents.analysis.config_drift.ConfigDriftDetector") as MockDetector, \
             patch("dataclasses.asdict", return_value={"environments": ["dev", "prod"], "diffs": []}):
            MockDetector.return_value.load_configs.return_value = {"dev": {"k": "v"}, "prod": {"k": "v2"}}
            MockDetector.return_value.compare_all.return_value = mock_report
            cmd_config_diff(["--json"])
        output = capsys.readouterr().out
        assert '"environments"' in output

    def test_config_diff_specific_envs_json(self, capsys):
        from code_agents.cli.cli_analysis import cmd_config_diff
        mock_diff = MagicMock()
        with patch("code_agents.cli.cli_analysis._load_env"), \
             patch("code_agents.analysis.config_drift.ConfigDriftDetector") as MockDetector, \
             patch("dataclasses.asdict", return_value={"added": [], "removed": []}):
            MockDetector.return_value.load_configs.return_value = {"dev": {}, "prod": {}}
            MockDetector.return_value.compare.return_value = mock_diff
            cmd_config_diff(["dev", "prod", "--json"])
        output = capsys.readouterr().out
        assert '"added"' in output

    def test_config_diff_second_env_not_found(self, capsys):
        from code_agents.cli.cli_analysis import cmd_config_diff
        with patch("code_agents.cli.cli_analysis._load_env"), \
             patch("code_agents.analysis.config_drift.ConfigDriftDetector") as MockDetector:
            MockDetector.return_value.load_configs.return_value = {"dev": {}, "staging": {}}
            cmd_config_diff(["dev", "prod"])
        output = capsys.readouterr().out
        assert "not found" in output
class TestCmdAuditLicensesOnly:
    """Test audit --licenses flag."""

    def test_audit_licenses_only(self, capsys):
        from code_agents.cli.cli_analysis import cmd_audit
        with patch("code_agents.security.dependency_audit.DependencyAuditor") as MockAuditor:
            mock_inst = MockAuditor.return_value
            mock_inst.format_report.return_value = "License Report"
            cmd_audit(["--licenses"])
        output = capsys.readouterr().out
        # Should skip outdated check
        mock_inst.check_outdated.assert_not_called()

    def test_audit_outdated_only(self, capsys):
        from code_agents.cli.cli_analysis import cmd_audit
        with patch("code_agents.security.dependency_audit.DependencyAuditor") as MockAuditor:
            mock_inst = MockAuditor.return_value
            mock_inst.format_report.return_value = "Outdated Report"
            cmd_audit(["--outdated"])
        output = capsys.readouterr().out
        assert "Outdated Report" in output
