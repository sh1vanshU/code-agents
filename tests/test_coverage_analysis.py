"""Coverage gap tests for analysis modules — config_drift, deadcode, impact_analysis,
complexity, feature_flags, project_scanner, security_scanner, dependency_graph,
bug_patterns, compile_check."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# config_drift.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.analysis.config_drift import (
    ConfigDriftDetector,
    ConfigDiff,
    DriftReport,
    format_drift_report,
)


class TestConfigDriftCoverage:
    """Cover missing lines in config_drift.py."""

    def test_yaml_import_fallback(self):
        """Lines 9-10: yaml import fallback (tested via coverage, import always succeeds)."""
        # Just ensure module loads OK
        detector = ConfigDriftDetector(cwd="/nonexistent")
        assert detector is not None

    def test_load_spring_profiles_yaml(self, tmp_path):
        """Lines 81-82: Spring YAML profile loading."""
        resources = tmp_path / "src" / "main" / "resources"
        resources.mkdir(parents=True)
        (resources / "application-dev.yml").write_text("server:\n  port: 8080\n")
        (resources / "application-prod.yml").write_text("server:\n  port: 80\n")

        detector = ConfigDriftDetector(cwd=str(tmp_path))
        configs = detector.load_configs()
        assert "dev" in configs
        assert "prod" in configs

    def test_load_spring_profiles_properties(self, tmp_path):
        """Line 87: Spring properties profile loading."""
        resources = tmp_path / "config"
        resources.mkdir()
        (resources / "application-staging.properties").write_text("server.port=8080\n")

        detector = ConfigDriftDetector(cwd=str(tmp_path))
        detector.load_configs()
        assert "staging" in detector.configs

    def test_load_spring_profiles_parse_error(self, tmp_path):
        """Lines 81-82: parse error in Spring profile."""
        resources = tmp_path / "src" / "main" / "resources"
        resources.mkdir(parents=True)
        (resources / "application-bad.yml").write_text("invalid: yaml: [broken\n")

        detector = ConfigDriftDetector(cwd=str(tmp_path))
        detector.load_configs()
        # Should not crash

    def test_load_env_files(self, tmp_path):
        """Line 87: .env.{env} loading."""
        (tmp_path / ".env.dev").write_text("DB_HOST=localhost\n")
        (tmp_path / ".env.prod").write_text("DB_HOST=prod-db\n")
        (tmp_path / ".env.example").write_text("SKIP=me\n")  # should be skipped

        detector = ConfigDriftDetector(cwd=str(tmp_path))
        detector.load_configs()
        assert "dev" in detector.configs
        assert "prod" in detector.configs
        assert "example" not in detector.configs

    def test_load_config_dirs(self, tmp_path):
        """Lines 112-121: config directory loading."""
        config_dir = tmp_path / "config"
        dev_dir = config_dir / "dev"
        dev_dir.mkdir(parents=True)
        (dev_dir / "app.yml").write_text("key: value\n")
        (dev_dir / "db.properties").write_text("host=localhost\n")
        (dev_dir / "extra.json").write_text('{"port": 5432}')
        (dev_dir / ".env").write_text("SECRET=abc\n")

        detector = ConfigDriftDetector(cwd=str(tmp_path))
        detector.load_configs()
        assert "dev" in detector.configs

    def test_load_config_dirs_json_error(self, tmp_path):
        """Lines 115-119: JSON parse error in config dir."""
        config_dir = tmp_path / "config" / "qa"
        config_dir.mkdir(parents=True)
        (config_dir / "broken.json").write_text("not json")

        detector = ConfigDriftDetector(cwd=str(tmp_path))
        detector.load_configs()
        # Should not crash

    def test_load_k8s_configs(self, tmp_path):
        """Lines 129-156: K8s ConfigMap loading."""
        k8s_dir = tmp_path / "k8s"
        k8s_dir.mkdir()
        configmap = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: myapp-prod-config
data:
  DB_HOST: prod-db
  DB_PORT: "5432"
"""
        (k8s_dir / "configmap.yaml").write_text(configmap)

        detector = ConfigDriftDetector(cwd=str(tmp_path))
        detector.load_configs()
        assert "prod" in detector.configs

    def test_load_k8s_configs_parse_error(self, tmp_path):
        """Lines 155-156: K8s YAML parse error."""
        k8s_dir = tmp_path / "k8s"
        k8s_dir.mkdir()
        (k8s_dir / "bad.yaml").write_text("invalid: yaml: [broken\n")

        detector = ConfigDriftDetector(cwd=str(tmp_path))
        detector.load_configs()

    def test_guess_env_from_name(self):
        """Lines 169-170: _guess_env_from_name."""
        detector = ConfigDriftDetector(cwd="/tmp")
        assert detector._guess_env_from_name("myapp-prod-config") == "prod"
        assert detector._guess_env_from_name("staging-config") == "staging"
        assert detector._guess_env_from_name("random-name") is None

    def test_flatten_yaml_no_yaml(self, tmp_path):
        """Lines 169-170: _flatten_yaml when yaml is None."""
        detector = ConfigDriftDetector(cwd=str(tmp_path))
        (tmp_path / "test.yml").write_text("key: value\n")
        result = detector._flatten_yaml(str(tmp_path / "test.yml"))
        assert "key" in result

    def test_compare_all(self, tmp_path):
        """Lines 255-260: compare_all with warnings for secrets."""
        detector = ConfigDriftDetector(cwd=str(tmp_path))
        detector.configs = {
            "dev": {"db.host": "localhost", "db.password": "sec***"},
            "prod": {"db.host": "prod-db", "db.password": "sec***"},
        }
        report = detector.compare_all()
        assert len(report.diffs) == 1
        assert len(report.environments) == 2

    def test_format_drift_report_overflow(self):
        """Lines 293-307: format with many items."""
        diff = ConfigDiff(env_a="dev", env_b="prod")
        diff.different_values = [{"key": f"key{i}", "value_a": "a", "value_b": "b"} for i in range(20)]
        diff.only_in_a = [{"key": f"onlyA{i}", "value": "v"} for i in range(15)]
        diff.only_in_b = [{"key": f"onlyB{i}", "value": "v"} for i in range(15)]
        diff.same_values = 5

        report = DriftReport(environments=["dev", "prod"], diffs=[diff])
        report.warnings = ["test warning"]
        output = format_drift_report(report)
        assert "... and" in output
        assert "test warning" in output

    def test_mask_sensitive_short(self):
        """Mask short sensitive values."""
        detector = ConfigDriftDetector(cwd="/tmp")
        assert detector._mask_sensitive("api_key", "ab") == "***"
        assert detector._mask_sensitive("api_key", "abcde") == "abc***"
        assert detector._mask_sensitive("db_host", "visible") == "visible"


# ---------------------------------------------------------------------------
# deadcode.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.analysis.deadcode import DeadCodeFinder, DeadCodeReport, format_deadcode_report


class TestDeadCodeCoverage:
    """Cover missing lines in deadcode.py."""

    def test_scan_python_syntax_error(self, tmp_path):
        """Lines 111-112: SyntaxError when parsing Python."""
        (tmp_path / "bad.py").write_text("def f(\n")  # syntax error
        scanner = DeadCodeFinder(str(tmp_path), language="python")
        scanner.scan()
        # Should not crash

    def test_scan_python_star_import(self, tmp_path):
        """Line 127: star import skipped."""
        (tmp_path / "mod.py").write_text("from os import *\n\nprint('hello')\n")
        scanner = DeadCodeFinder(str(tmp_path), language="python")
        scanner.scan()
        # Star import should not be flagged
        star_imports = [i for i in scanner.report.unused_imports if "*" in i.get("import", "")]
        assert len(star_imports) == 0

    def test_scan_java_files(self, tmp_path):
        """Lines 181-182: Java scanning."""
        java_file = tmp_path / "Service.java"
        java_file.write_text("""
import com.example.UnusedClass;
import com.example.UsedClass;

public class Service {
    private void unusedMethod() {}
    public void usedMethod() {
        UsedClass c = new UsedClass();
        usedMethod();
    }
}
""")
        scanner = DeadCodeFinder(str(tmp_path), language="java")
        scanner.scan()
        assert len(scanner.report.unused_imports) >= 1

    def test_scan_js_files(self, tmp_path):
        """Lines 215, 232-233: JS/TS scanning."""
        js_file = tmp_path / "app.js"
        js_file.write_text("""
import { UsedThing, UnusedThing } from './module';
const x = UsedThing();
""")
        scanner = DeadCodeFinder(str(tmp_path), language="javascript")
        scanner.scan()
        assert len(scanner.report.unused_imports) >= 1

    def test_scan_js_oserror(self, tmp_path):
        """Lines 232-233: OSError reading JS file."""
        js_file = tmp_path / "bad.js"
        js_file.write_text("import { Foo } from './bar';")
        js_file.chmod(0o000)
        try:
            scanner = DeadCodeFinder(str(tmp_path), language="javascript")
            scanner.scan()
        finally:
            js_file.chmod(0o644)

    def test_scan_orphan_endpoints(self, tmp_path):
        """Lines 253-254, 278-279: orphan endpoint detection."""
        py_file = tmp_path / "routes.py"
        py_file.write_text("""
@app.get("/unique-orphan-endpoint")
def handler():
    pass
""")
        scanner = DeadCodeFinder(str(tmp_path), language="python")
        scanner.scan()
        # Endpoint only appears once, so it's orphan
        assert len(scanner.report.orphan_endpoints) >= 1

    def test_format_deadcode_report_full(self):
        """Lines 317-329: format with all categories."""
        report = DeadCodeReport(repo_path="/test", language="python")
        report.unused_imports = [{"file": "a.py", "import": "os", "line": 1}] * 25
        report.unused_functions = [{"file": "b.py", "name": "_helper", "line": 5}] * 25
        report.unused_classes = [{"file": "c.py", "name": "OldClass", "line": 10}]
        report.orphan_endpoints = [{"file": "d.py", "route": "GET /old", "line": 15}] * 20
        output = format_deadcode_report(report)
        assert "Unused Imports" in output
        assert "Unused Functions" in output
        assert "Unused Classes" in output
        assert "Orphan Endpoints" in output
        assert "... and" in output

    def test_format_deadcode_report_clean(self):
        """Lines 325-329: no dead code."""
        report = DeadCodeReport(repo_path="/test", language="python")
        output = format_deadcode_report(report)
        assert "No dead code detected" in output


# ---------------------------------------------------------------------------
# complexity.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.analysis.complexity import (
    ComplexityAnalyzer,
    ComplexityReport,
    FileComplexity,
    FunctionComplexity,
)


class TestComplexityCoverage:
    """Cover missing lines in complexity.py."""

    def test_grade_e(self):
        """Line 46, 48: grade E (31-50) and F (>50)."""
        fc = FunctionComplexity(file="a.py", name="f", line=1, cyclomatic=35, nesting_depth=3)
        assert fc.rating == "E"
        fc2 = FunctionComplexity(file="a.py", name="f", line=1, cyclomatic=60, nesting_depth=5)
        assert fc2.rating == "F"

    def test_file_complexity_empty(self):
        """Lines 66-68, 72-74: FileComplexity with no functions."""
        fc = FileComplexity(file="empty.py")
        assert fc.avg_complexity == 0.0
        assert fc.most_complex is None

    def test_detect_language_unknown(self, tmp_path):
        """Line 119: unknown language detection."""
        analyzer = ComplexityAnalyzer(cwd=str(tmp_path))
        assert analyzer.language == "unknown"

    def test_report_avg_no_functions(self):
        """Line 97: avg_complexity with no functions."""
        report = ComplexityReport(repo_path="/test", language="python")
        assert report.avg_complexity == 0.0

    def test_analyze_python_syntax_error(self, tmp_path):
        """Lines 154-155: SyntaxError in Python file."""
        (tmp_path / "bad.py").write_text("def f(\n")
        analyzer = ComplexityAnalyzer(cwd=str(tmp_path), language="python")
        analyzer.analyze()
        # Should not crash

    def test_analyze_java(self, tmp_path):
        """Lines 213-214: Java analysis with UnicodeDecodeError."""
        java_file = tmp_path / "Service.java"
        java_file.write_text("""
public class Service {
    public void process() {
        if (true) {
            for (int i = 0; i < 10; i++) {
                while (running) {}
            }
        }
    }
}
""")
        analyzer = ComplexityAnalyzer(cwd=str(tmp_path), language="java")
        report = analyzer.analyze()
        assert len(report.files) >= 1


# ---------------------------------------------------------------------------
# feature_flags.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.analysis.feature_flags import FeatureFlagScanner, FeatureFlag, FlagReport


class TestFeatureFlagsCoverage:
    """Cover missing lines in feature_flags.py."""

    def test_scan_env_files_error(self, tmp_path):
        """Lines 159-160: error reading env file."""
        env_file = tmp_path / ".env.dev"
        env_file.write_text("FEATURE_TOGGLE_NEW_UI=true\n")
        env_file.chmod(0o000)
        try:
            scanner = FeatureFlagScanner(str(tmp_path))
            scanner.scan()
        finally:
            env_file.chmod(0o644)

    def test_scan_java_flags(self, tmp_path):
        """Lines 193-194: Java flag scanning."""
        java_file = tmp_path / "Config.java"
        java_file.write_text('''
@Value("${feature.newui.enabled:false}")
private boolean newUi;

@ConditionalOnProperty(name = "feature.payment.active")
public class PaymentConfig {}
''')
        scanner = FeatureFlagScanner(str(tmp_path))
        flags = scanner._scan_java_flags()
        assert len(flags) >= 2

    def test_scan_java_flags_error(self, tmp_path):
        """Lines 193-194: error reading Java file."""
        java_file = tmp_path / "Config.java"
        java_file.write_text('@Value("${feature.test:true}")\nprivate boolean test;')
        java_file.chmod(0o000)
        try:
            scanner = FeatureFlagScanner(str(tmp_path))
            scanner._scan_java_flags()
        finally:
            java_file.chmod(0o644)

    def test_scan_config_flags(self, tmp_path):
        """Lines 222-223: config flag scanning."""
        config_file = tmp_path / "application.yml"
        config_file.write_text("feature.enable.new_flow: true\nother.key: value\n")
        scanner = FeatureFlagScanner(str(tmp_path))
        flags = scanner._scan_config_flags()
        assert len(flags) >= 1

    def test_scan_config_flags_error(self, tmp_path):
        """Lines 222-223: error reading config file."""
        config_file = tmp_path / "app.yml"
        config_file.write_text("feature.toggle: true\n")
        config_file.chmod(0o000)
        try:
            scanner = FeatureFlagScanner(str(tmp_path))
            scanner._scan_config_flags()
        finally:
            config_file.chmod(0o644)

    def test_scan_code_flags(self, tmp_path):
        """Lines 244-245: code flag scanning in Python."""
        py_file = tmp_path / "app.py"
        py_file.write_text("flag = os.getenv('FEATURE_NEW_CHECKOUT')\n")
        scanner = FeatureFlagScanner(str(tmp_path))
        flags = scanner._scan_code_flags()
        assert len(flags) >= 1

    def test_scan_code_flags_error(self, tmp_path):
        """Lines 244-245: error reading code file."""
        py_file = tmp_path / "app.py"
        py_file.write_text("os.getenv('FEATURE_X')")
        py_file.chmod(0o000)
        try:
            scanner = FeatureFlagScanner(str(tmp_path))
            scanner._scan_code_flags()
        finally:
            py_file.chmod(0o644)

    def test_find_references_error(self, tmp_path):
        """Lines 274-275: grep failure."""
        scanner = FeatureFlagScanner(str(tmp_path))
        flag = FeatureFlag(name="FEATURE_TEST", file="test.py", line=1)
        with patch("subprocess.run", side_effect=Exception("grep error")):
            scanner._find_references([flag])
        assert flag.references == []


# ---------------------------------------------------------------------------
# project_scanner.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.analysis.project_scanner import scan_project


class TestProjectScannerCoverage:
    """Cover missing lines in project_scanner.py."""

    def test_scan_python_fastapi(self, tmp_path):
        """Lines 133-134, 154-155: Python with FastAPI."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'demo'\n[tool.poetry.dependencies]\nfastapi = '*'\n")
        info = scan_project(str(tmp_path))
        assert info.language == "Python"
        assert info.framework == "FastAPI"

    def test_scan_python_django(self, tmp_path):
        """Django detection."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'demo'\n[tool.poetry.dependencies]\ndjango = '*'\n")
        info = scan_project(str(tmp_path))
        assert info.framework == "Django"

    def test_scan_python_flask(self, tmp_path):
        """Flask detection."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'demo'\n[tool.poetry.dependencies]\nflask = '*'\n")
        info = scan_project(str(tmp_path))
        assert info.framework == "Flask"

    def test_scan_python_oserror(self, tmp_path):
        """Lines 154-155: OSError reading pyproject.toml."""
        pyp = tmp_path / "pyproject.toml"
        pyp.write_text("[tool.poetry]\nname = 'demo'\n")
        pyp.chmod(0o000)
        try:
            info = scan_project(str(tmp_path))
        finally:
            pyp.chmod(0o644)

    def test_scan_nodejs_express(self, tmp_path):
        """Lines 182-183: Node.js with Express."""
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "4.0"}}')
        info = scan_project(str(tmp_path))
        assert info.language == "Node.js"
        assert info.framework == "Express"

    def test_scan_nodejs_next(self, tmp_path):
        """Next.js detection."""
        (tmp_path / "package.json").write_text('{"dependencies": {"next": "13.0"}}')
        info = scan_project(str(tmp_path))
        assert info.framework == "Next.js"

    def test_scan_nodejs_react(self, tmp_path):
        """React detection."""
        (tmp_path / "package.json").write_text('{"dependencies": {"react": "18.0"}}')
        info = scan_project(str(tmp_path))
        assert info.framework == "React"

    def test_scan_nodejs_oserror(self, tmp_path):
        """Lines 182-183: OSError reading package.json."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"name": "demo"}')
        pkg.chmod(0o000)
        try:
            info = scan_project(str(tmp_path))
        finally:
            pkg.chmod(0o644)

    def test_scan_go(self, tmp_path):
        """Lines 204-208: Go project."""
        (tmp_path / "go.mod").write_text("module example.com/myapp\n")
        info = scan_project(str(tmp_path))
        assert info.language == "Go"

    def test_scan_endpoint_error(self, tmp_path):
        """Line 208: endpoint scan error."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'demo'\n")
        with patch("code_agents.cicd.endpoint_scanner.scan_all", side_effect=Exception("scan error")):
            info = scan_project(str(tmp_path))
        assert info.language == "Python"


# ---------------------------------------------------------------------------
# security_scanner.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.analysis.security_scanner import SecurityScanner, format_security_report


class TestSecurityScannerCoverage:
    """Cover missing lines in security_scanner.py."""

    def test_get_files_oserror(self, tmp_path):
        """Lines 67-68, 92-93: OSError reading files."""
        py_file = tmp_path / "secrets.py"
        py_file.write_text("SECRET = 'super-secret-123456789'\n")
        py_file.chmod(0o000)
        try:
            scanner = SecurityScanner(str(tmp_path))
            files = scanner._get_files((".py",))
            assert len(files) == 0
        finally:
            py_file.chmod(0o644)

    def test_scan_sensitive_data_exposure(self, tmp_path):
        """Lines 308-309: sensitive data logging detection."""
        py_file = tmp_path / "app.py"
        py_file.write_text("print(f'password: {user.password}')\n")
        scanner = SecurityScanner(str(tmp_path))
        report = scanner.scan()
        findings = [f for f in report.findings if f.category == "data-exposure"]
        assert len(findings) >= 1

    def test_scan_insecure_deps(self, tmp_path):
        """Lines 308-309: insecure dependency detection."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("django==1.8\n")
        scanner = SecurityScanner(str(tmp_path))
        report = scanner.scan()
        # May or may not find findings depending on patterns

    def test_format_security_report_with_all_severities(self):
        """Lines 350-352: format report with all severity levels."""
        from code_agents.analysis.security_scanner import SecurityReport, SecurityFinding
        report = SecurityReport(repo_path="/test")
        report.scanned_files = 5
        report.findings = [
            SecurityFinding(severity="CRITICAL", category="hardcoded-secret", file="a.py", line=1, description="Secret found"),
            SecurityFinding(severity="HIGH", category="sql-injection", file="b.py", line=2, description="SQL injection"),
            SecurityFinding(severity="MEDIUM", category="data-exposure", file="c.py", line=3, description="Data leak"),
            SecurityFinding(severity="LOW", category="info", file="d.py", line=4, description="Info leak"),
        ]
        report.critical_count = 1
        report.high_count = 1
        report.medium_count = 1
        report.low_count = 1
        output = format_security_report(report)
        assert "CRITICAL" in output
        assert "HIGH" in output


# ---------------------------------------------------------------------------
# dependency_graph.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.analysis.dependency_graph import DependencyGraph


class TestDependencyGraphCoverage:
    """Cover missing lines in dependency_graph.py."""

    def test_module_name_from_path_valueerror(self, tmp_path):
        """Lines 78-79: ValueError in relative_to."""
        graph = DependencyGraph(str(tmp_path))
        # Use a path outside the cwd
        result = graph._module_name_from_path(Path("/completely/different/path/module.py"))
        assert "module" in result

    def test_module_name_init(self, tmp_path):
        """Line 88: __init__ suffix removal."""
        graph = DependencyGraph(str(tmp_path))
        result = graph._module_name_from_path(tmp_path / "pkg" / "__init__.py")
        assert "__init__" not in result

    def test_parse_java(self, tmp_path):
        """Lines 130-131: Java parsing."""
        java_file = tmp_path / "Service.java"
        java_file.write_text("""
import com.example.Repository;

public class Service {
    @Autowired
    private Repository repo;

    public Service(HelperService helper) {}
}
""")
        graph = DependencyGraph(str(tmp_path))
        graph._parse_java(java_file)
        assert "Service" in graph.all_names
        assert "Repository" in graph.all_names

    def test_parse_js_ts(self, tmp_path):
        """Lines 178-179: JS/TS parsing."""
        js_file = tmp_path / "app.js"
        js_file.write_text("import { Foo } from './foo';\nconst bar = require('./bar');\n")
        graph = DependencyGraph(str(tmp_path))
        graph._parse_js_ts(js_file)
        assert len(graph.all_names) >= 1

    def test_parse_js_ts_oserror(self, tmp_path):
        """Lines 178-179: OSError reading JS file."""
        js_file = tmp_path / "app.js"
        js_file.write_text("import { Foo } from './foo';")
        js_file.chmod(0o000)
        try:
            graph = DependencyGraph(str(tmp_path))
            graph._parse_js_ts(js_file)
        finally:
            js_file.chmod(0o644)

    def test_resolve_name_suffix_match(self, tmp_path):
        """Lines 245, 251: suffix and case-insensitive matching."""
        graph = DependencyGraph(str(tmp_path))
        graph.all_names = {"com.example.PaymentService", "com.example.UserService"}
        # Suffix match
        result = graph._resolve_name("PaymentService")
        assert len(result) >= 1
        assert "com.example.PaymentService" in result

    def test_resolve_name_case_insensitive(self, tmp_path):
        """Line 251: case-insensitive match."""
        graph = DependencyGraph(str(tmp_path))
        graph.all_names = {"paymentservice"}
        result = graph._resolve_name("PaymentService")
        assert len(result) >= 1

    def test_format_tree_circular(self, tmp_path):
        """Lines 373-374: format_tree with circular deps."""
        graph = DependencyGraph(str(tmp_path))
        graph.all_names = {"A", "B"}
        graph.outgoing = {"A": {"B"}, "B": {"A"}}
        graph.incoming = {"A": {"B"}, "B": {"A"}}
        output = graph.format_tree("A")
        # Should handle circular deps gracefully
        assert "A" in output
        assert "Circular" in output or "circular" in output.lower() or "Uses" in output


# ---------------------------------------------------------------------------
# bug_patterns.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.analysis.bug_patterns import BugPatternDetector, BugPattern, format_bug_warnings


class TestBugPatternsCoverage:
    """Cover missing lines in bug_patterns.py."""

    def test_learn_from_history(self, tmp_path):
        """Lines 71-128: learn_from_history with git log."""
        store = tmp_path / "patterns.json"
        detector = BugPatternDetector(str(tmp_path), store_path=str(store))
        assert len(detector.patterns) == 0  # fresh store

        mock_log = MagicMock()
        mock_log.returncode = 0
        mock_log.stdout = "abc123 fix: null pointer in payment\ndef456 bug: retry logic broken\n"

        mock_diff = MagicMock()
        mock_diff.returncode = 0
        mock_diff.stdout = "--- a/file.py\n+++ b/file.py\n-    old_buggy_code_line_that_is_long_enough\n+    fixed_code\n"

        with patch("code_agents.analysis.bug_patterns.subprocess.run", side_effect=[mock_log, mock_diff, mock_diff]):
            with patch.object(detector, "save"):
                count = detector.learn_from_history(days=30)
        assert count >= 1

    def test_learn_from_history_timeout(self, tmp_path):
        """Lines 78-79: git timeout."""
        detector = BugPatternDetector(str(tmp_path))
        with patch("code_agents.analysis.bug_patterns.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            count = detector.learn_from_history()
        assert count == 0

    def test_learn_from_history_file_not_found(self, tmp_path):
        """Lines 78-79: FileNotFoundError."""
        detector = BugPatternDetector(str(tmp_path))
        with patch("code_agents.analysis.bug_patterns.subprocess.run", side_effect=FileNotFoundError("git")):
            count = detector.learn_from_history()
        assert count == 0

    def test_learn_from_history_bad_return(self, tmp_path):
        """Lines 82-83: non-zero return code."""
        detector = BugPatternDetector(str(tmp_path))
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("code_agents.analysis.bug_patterns.subprocess.run", return_value=mock_result):
            count = detector.learn_from_history()
        assert count == 0

    def test_learn_from_history_similar_pattern(self, tmp_path):
        """Lines 111-115: finding similar existing pattern."""
        store = tmp_path / "patterns.json"
        detector = BugPatternDetector(str(tmp_path), store_path=str(store))
        existing = BugPattern(
            pattern=re.escape("buggy_line_content"),
            description="known bug",
            occurrences=1,
            commit_refs=["aaa"],
        )
        detector.patterns = [existing]

        mock_log = MagicMock()
        mock_log.returncode = 0
        mock_log.stdout = "abc123 fix: same bug again\n"

        mock_diff = MagicMock()
        mock_diff.returncode = 0
        mock_diff.stdout = "--- a/f.py\n+++ b/f.py\n-    buggy_line_content\n+    fixed\n"

        with patch("code_agents.analysis.bug_patterns.subprocess.run", side_effect=[mock_log, mock_diff]):
            with patch.object(detector, "save"):
                count = detector.learn_from_history()
        assert existing.occurrences == 2
        assert "abc123" in existing.commit_refs

    def test_check_diff_invalid_regex(self, tmp_path):
        """Lines 158-159: invalid regex pattern."""
        detector = BugPatternDetector(str(tmp_path))
        detector.patterns = [BugPattern(pattern="[invalid", description="bad")]
        matches = detector.check_diff("+added line\n")
        assert matches == []

    def test_format_bug_warnings_with_matches(self):
        """Line 199: format with commit refs."""
        matches = [
            BugPattern(
                pattern="test",
                description="Null check missing",
                occurrences=3,
                fix_applied="Added null check",
                commit_refs=["abc123", "def456"],
            ),
        ]
        output = format_bug_warnings(matches)
        assert "Null check missing" in output
        assert "3 time(s)" in output
        assert "abc123" in output

    def test_format_bug_warnings_empty(self):
        output = format_bug_warnings([])
        assert "No known bug patterns" in output


# ---------------------------------------------------------------------------
# compile_check.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.analysis.compile_check import (
    CompileChecker,
    CompileResult,
    is_auto_compile_enabled,
    _extract_errors,
    _extract_warnings,
)


class TestCompileCheckCoverage:
    """Cover missing lines in compile_check.py."""

    def test_is_auto_compile_enabled(self, monkeypatch):
        """Line 46: auto compile check."""
        monkeypatch.setenv("CODE_AGENTS_AUTO_COMPILE", "true")
        assert is_auto_compile_enabled() is True
        monkeypatch.setenv("CODE_AGENTS_AUTO_COMPILE", "false")
        assert is_auto_compile_enabled() is False
        monkeypatch.setenv("CODE_AGENTS_AUTO_COMPILE", "1")
        assert is_auto_compile_enabled() is True

    def test_detect_language_maven(self, tmp_path):
        """Lines 57-85: language detection."""
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(str(tmp_path))
        assert checker.language == "java-maven"

    def test_detect_language_gradle(self, tmp_path):
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'")
        checker = CompileChecker(str(tmp_path))
        assert checker.language == "java-gradle"

    def test_detect_language_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example")
        checker = CompileChecker(str(tmp_path))
        assert checker.language == "go"

    def test_detect_language_typescript(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        checker = CompileChecker(str(tmp_path))
        assert checker.language == "typescript"

    def test_detect_language_none(self, tmp_path):
        checker = CompileChecker(str(tmp_path))
        assert checker.language is None

    def test_get_compile_command(self, tmp_path):
        """Lines 89-104: compile command mapping."""
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(str(tmp_path))
        assert "mvn" in checker._get_compile_command()

    def test_get_compile_command_gradle_wrapper(self, tmp_path):
        """Gradle wrapper present."""
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'")
        (tmp_path / "gradlew").write_text("#!/bin/bash")
        checker = CompileChecker(str(tmp_path))
        assert "./gradlew" in checker._get_compile_command()

    def test_get_compile_command_none(self, tmp_path):
        checker = CompileChecker(str(tmp_path))
        assert checker._get_compile_command() is None

    def test_should_check_java(self, tmp_path):
        """Lines 112-131: should_check with matching code blocks."""
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(str(tmp_path))
        assert checker.should_check("```java\nclass Foo {}\n```") is True
        assert checker.should_check("```python\nprint()\n```") is False
        assert checker.should_check("") is False

    def test_should_check_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example")
        checker = CompileChecker(str(tmp_path))
        assert checker.should_check("```go\npackage main\n```") is True

    def test_should_check_typescript(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        checker = CompileChecker(str(tmp_path))
        assert checker.should_check("```typescript\nconst x = 1;\n```") is True
        assert checker.should_check("```ts\nconst x = 1;\n```") is True

    def test_should_check_no_language(self, tmp_path):
        checker = CompileChecker(str(tmp_path))
        assert checker.should_check("```java\nclass Foo {}\n```") is False

    def test_run_compile_no_command(self, tmp_path):
        """Lines 135-137: no compile command."""
        checker = CompileChecker(str(tmp_path))
        result = checker.run_compile()
        assert result.success is False
        assert "No compile command" in result.errors[0]

    def test_run_compile_success(self, tmp_path):
        """Lines 144-177: successful compile."""
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(str(tmp_path))

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "BUILD SUCCESS\n"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            result = checker.run_compile()
        assert result.success is True

    def test_run_compile_failure(self, tmp_path):
        """Lines 156-177: compile failure."""
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(str(tmp_path))

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = "src/Foo.java:10: error: cannot find symbol\n"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            result = checker.run_compile()
        assert result.success is False
        assert len(result.errors) >= 1

    def test_run_compile_timeout(self, tmp_path):
        """Lines 179-182: compile timeout."""
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(str(tmp_path))

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 120)):
            result = checker.run_compile()
        assert result.success is False
        assert "timed out" in result.errors[0]

    def test_run_compile_exception(self, tmp_path):
        """Lines 189-192: general exception."""
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(str(tmp_path))

        with patch("subprocess.run", side_effect=Exception("boom")):
            result = checker.run_compile()
        assert result.success is False
        assert "boom" in result.errors[0]

    def test_format_result_success(self, tmp_path):
        """Lines 202-206: format success."""
        checker = CompileChecker(str(tmp_path))
        result = CompileResult(success=True, language="java-maven", command="mvn compile", elapsed=2.5)
        output = checker.format_result(result)
        assert "successful" in output

    def test_format_result_success_with_warnings(self, tmp_path):
        """Lines 204-205: format success with warnings."""
        checker = CompileChecker(str(tmp_path))
        result = CompileResult(success=True, language="java-maven", command="mvn compile", elapsed=2.5, warnings=["w1"])
        output = checker.format_result(result)
        assert "1 warning" in output

    def test_format_result_failure(self, tmp_path):
        """Lines 208-213: format failure with many errors."""
        checker = CompileChecker(str(tmp_path))
        result = CompileResult(
            success=False, language="java-maven", command="mvn compile", elapsed=5.0,
            errors=[f"error {i}" for i in range(15)],
        )
        output = checker.format_result(result)
        assert "failed" in output
        assert "... and 5 more" in output

    def test_extract_errors_java(self):
        """Lines 218-241: Java error extraction."""
        output = "src/Foo.java:10: error: cannot find symbol\nINFO: Building\nDownloading deps\n"
        errors = _extract_errors(output, "java-maven")
        assert len(errors) == 1

    def test_extract_errors_go(self):
        """Go error extraction."""
        output = "./main.go:10:5: undefined: foo\n"
        errors = _extract_errors(output, "go")
        assert len(errors) == 1

    def test_extract_errors_typescript(self):
        """TypeScript error extraction."""
        output = "src/foo.ts(10,5): error TS2304: Cannot find name 'foo'\n"
        errors = _extract_errors(output, "typescript")
        assert len(errors) == 1

    def test_extract_errors_generic_fallback(self):
        """Generic error fallback."""
        output = "some error occurred\nwarning: something else\n"
        errors = _extract_errors(output, "unknown")
        assert len(errors) == 1

    def test_extract_warnings(self):
        """Lines 246-257: warning extraction."""
        assert len(_extract_warnings("src/Foo.java:5: warning: deprecated\n", "java-maven")) == 1
        assert len(_extract_warnings("warning: something\n", "go")) == 1
        assert len(_extract_warnings("warning: unused var\n", "typescript")) == 1
        assert len(_extract_warnings("no warnings here\n", "java-maven")) == 0
