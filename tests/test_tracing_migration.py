"""Tests for code_agents.tracing_migration — OpenTelemetry migration tool."""

from __future__ import annotations

import os
import textwrap

import pytest

from code_agents.observability.tracing_migration import (
    ConfigChange,
    DependencyChange,
    MigrationPlan,
    MigrationResult,
    TracingMigrator,
    TracingPattern,
    format_migration_plan,
    format_migration_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


# ---------------------------------------------------------------------------
# TestDetection
# ---------------------------------------------------------------------------


class TestDetection:
    """Detect tracing frameworks from source files."""

    def test_detect_jaeger_python(self, tmp_path):
        _write(tmp_path / "app.py", """\
            from jaeger_client import Config
            config = Config(config={}, service_name='svc')
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "jaeger"
        assert plan.language == "python"

    def test_detect_datadog_python(self, tmp_path):
        _write(tmp_path / "main.py", """\
            from ddtrace import tracer
            tracer.trace('op')
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "datadog"

    def test_detect_zipkin_python(self, tmp_path):
        _write(tmp_path / "tracing.py", """\
            from py_zipkin.zipkin import zipkin_span
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "zipkin"

    def test_detect_newrelic_python(self, tmp_path):
        _write(tmp_path / "start.py", """\
            import newrelic.agent
            newrelic.agent.initialize('newrelic.ini')
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "newrelic"

    def test_detect_none_empty_repo(self, tmp_path):
        _write(tmp_path / "hello.py", """\
            print("hello world")
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "none"

    def test_detect_opentracing_python(self, tmp_path):
        _write(tmp_path / "trace.py", """\
            import opentracing
            tracer = opentracing.global_tracer()
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "opentracing"

    def test_detect_print_tracing(self, tmp_path):
        _write(tmp_path / "handler.py", """\
            print(f"TRACE: request started")
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "print"

    def test_detect_java_jaeger(self, tmp_path):
        src = tmp_path / "src" / "Main.java"
        _write(src, """\
            import io.jaegertracing.Configuration;
            public class Main {}
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "jaeger"
        assert plan.language == "java"

    def test_detect_node_datadog(self, tmp_path):
        _write(tmp_path / "index.js", """\
            const tracer = require('dd-trace');
            tracer.init();
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "datadog"
        assert plan.language == "node"

    def test_detect_go_jaeger(self, tmp_path):
        _write(tmp_path / "main.go", """\
            package main
            import "github.com/uber/jaeger-client-go"
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "jaeger"
        assert plan.language == "go"


# ---------------------------------------------------------------------------
# TestPythonReplacement
# ---------------------------------------------------------------------------


class TestPythonReplacement:
    """Verify each Python pattern generates correct OTel code."""

    def test_jaeger_import_replaced(self, tmp_path):
        _write(tmp_path / "svc.py", """\
            from jaeger_client import Config
            cfg = Config(config={}, service_name='x')
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        jaeger_patterns = [p for p in plan.patterns_found if p.old_pattern == "jaeger"]
        assert len(jaeger_patterns) >= 1
        p = jaeger_patterns[0]
        assert "opentelemetry" in p.new_code

    def test_datadog_import_replaced(self, tmp_path):
        _write(tmp_path / "app.py", """\
            from ddtrace import tracer
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        dd_patterns = [p for p in plan.patterns_found if p.old_pattern == "datadog"]
        assert len(dd_patterns) >= 1
        assert "opentelemetry" in dd_patterns[0].new_code

    def test_zipkin_import_replaced(self, tmp_path):
        _write(tmp_path / "trace.py", """\
            from py_zipkin.zipkin import zipkin_span
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        zp = [p for p in plan.patterns_found if p.old_pattern == "zipkin"]
        assert len(zp) >= 1
        assert "opentelemetry" in zp[0].new_code

    def test_newrelic_import_replaced(self, tmp_path):
        _write(tmp_path / "nr.py", """\
            import newrelic.agent
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        nr = [p for p in plan.patterns_found if p.old_pattern == "newrelic"]
        assert len(nr) >= 1
        assert "opentelemetry" in nr[0].new_code

    def test_print_trace_replaced(self, tmp_path):
        _write(tmp_path / "debug.py", """\
            print(f"TRACE: incoming request")
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        pr = [p for p in plan.patterns_found if p.old_pattern == "print"]
        assert len(pr) >= 1
        assert "otel" in pr[0].new_code.lower() or "OTel" in pr[0].new_code

    def test_confidence_above_threshold(self, tmp_path):
        _write(tmp_path / "x.py", """\
            from jaeger_client import Config
        """)
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        for p in plan.patterns_found:
            assert 0.0 < p.confidence <= 1.0


# ---------------------------------------------------------------------------
# TestDependencyChanges
# ---------------------------------------------------------------------------


class TestDependencyChanges:
    """Verify dependency add/remove for each framework."""

    def test_python_jaeger_deps(self, tmp_path):
        _write(tmp_path / "app.py", "from jaeger_client import Config\n")
        _write(tmp_path / "pyproject.toml", "[tool.poetry]\nname = 'x'\n")
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        removes = [d for d in plan.dependency_changes if d.action == "remove"]
        adds = [d for d in plan.dependency_changes if d.action == "add"]
        assert any("jaeger" in d.package for d in removes)
        assert any("opentelemetry-api" in d.package for d in adds)
        assert any("opentelemetry-sdk" in d.package for d in adds)

    def test_python_datadog_deps(self, tmp_path):
        _write(tmp_path / "app.py", "from ddtrace import tracer\n")
        _write(tmp_path / "pyproject.toml", "[tool.poetry]\nname = 'x'\n")
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        removes = [d for d in plan.dependency_changes if d.action == "remove"]
        assert any("ddtrace" in d.package for d in removes)

    def test_node_jaeger_deps(self, tmp_path):
        _write(tmp_path / "index.js", "const j = require('jaeger-client');\n")
        _write(tmp_path / "package.json", '{"name": "x"}\n')
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        removes = [d for d in plan.dependency_changes if d.action == "remove"]
        adds = [d for d in plan.dependency_changes if d.action == "add"]
        assert any("jaeger" in d.package for d in removes)
        assert any("@opentelemetry/api" in d.package for d in adds)

    def test_java_jaeger_deps(self, tmp_path):
        _write(tmp_path / "App.java", "import io.jaegertracing.Configuration;\n")
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        removes = [d for d in plan.dependency_changes if d.action == "remove"]
        adds = [d for d in plan.dependency_changes if d.action == "add"]
        assert any("jaeger" in d.package for d in removes)
        assert any("opentelemetry" in d.package for d in adds)

    def test_zipkin_adds_zipkin_exporter(self, tmp_path):
        _write(tmp_path / "z.py", "from py_zipkin.zipkin import zipkin_span\n")
        _write(tmp_path / "pyproject.toml", "[tool.poetry]\nname = 'x'\n")
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        adds = [d for d in plan.dependency_changes if d.action == "add"]
        assert any("zipkin" in d.package for d in adds)


# ---------------------------------------------------------------------------
# TestConfigGeneration
# ---------------------------------------------------------------------------


class TestConfigGeneration:
    """Verify generated OTel collector config and init files."""

    def test_collector_config_valid_yaml(self, tmp_path):
        _write(tmp_path / "app.py", "from jaeger_client import Config\n")
        m = TracingMigrator(str(tmp_path))
        content = m._generate_collector_config()
        assert "receivers:" in content
        assert "exporters:" in content
        assert "processors:" in content
        assert "service:" in content
        assert "otlp" in content

    def test_python_init_is_complete(self, tmp_path):
        _write(tmp_path / "app.py", "from jaeger_client import Config\n")
        m = TracingMigrator(str(tmp_path))
        init = m._generate_otel_init_python()
        assert "TracerProvider" in init
        assert "BatchSpanProcessor" in init
        assert "OTLPSpanExporter" in init
        assert "get_tracer" in init
        assert "shutdown" in init
        assert "OTEL_SERVICE_NAME" in init

    def test_node_init_has_sdk(self, tmp_path):
        _write(tmp_path / "app.js", "const t = require('jaeger-client');\n")
        m = TracingMigrator(str(tmp_path))
        init = m._generate_otel_init_node()
        assert "NodeSDK" in init
        assert "OTLPTraceExporter" in init
        assert "OTEL_SERVICE_NAME" in init

    def test_java_init_has_setup(self, tmp_path):
        _write(tmp_path / "Main.java", "import io.jaegertracing.Configuration;\n")
        m = TracingMigrator(str(tmp_path))
        init = m._generate_otel_init_java()
        assert "OtelSetup" in init
        assert "SdkTracerProvider" in init
        assert "BatchSpanProcessor" in init


# ---------------------------------------------------------------------------
# TestDryRun
# ---------------------------------------------------------------------------


class TestDryRun:
    """Verify dry-run mode does not modify files."""

    def test_dry_run_no_file_changes(self, tmp_path):
        src = tmp_path / "app.py"
        _write(src, """\
            from jaeger_client import Config
            config = Config(config={}, service_name='svc')
        """)
        original = src.read_text()

        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        result = m.apply(plan, dry_run=True)

        assert result.success is True
        assert result.files_modified > 0
        # File unchanged
        assert src.read_text() == original
        # No backup dir created
        backup = tmp_path / ".code-agents" / "migration-backup"
        assert not backup.exists()
        # No generated files
        assert not (tmp_path / "otel_setup.py").exists()
        assert not (tmp_path / "otel-collector-config.yaml").exists()


# ---------------------------------------------------------------------------
# TestApplyAndRollback
# ---------------------------------------------------------------------------


class TestApplyAndRollback:
    """Apply changes, verify files changed, rollback, verify restored."""

    def test_apply_modifies_files(self, tmp_path):
        src = tmp_path / "app.py"
        _write(src, """\
            from jaeger_client import Config
            config = Config(config={}, service_name='svc')
        """)

        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        result = m.apply(plan, dry_run=False)

        assert result.success is True
        assert result.files_modified >= 1
        assert result.files_created >= 1

        # Source file changed
        new_content = src.read_text()
        assert "jaeger_client" not in new_content
        assert "opentelemetry" in new_content

        # Init file created
        assert (tmp_path / "otel_setup.py").is_file()
        # Collector config created
        assert (tmp_path / "otel-collector-config.yaml").is_file()

        # Backup exists
        backup = tmp_path / ".code-agents" / "migration-backup"
        assert backup.is_dir()

    def test_rollback_restores_files(self, tmp_path):
        src = tmp_path / "app.py"
        original = "from jaeger_client import Config\nconfig = Config(config={}, service_name='svc')\n"
        src.write_text(original)

        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        m.apply(plan, dry_run=False)

        # Verify changed
        assert "opentelemetry" in src.read_text()

        # Rollback
        ok = m.rollback()
        assert ok is True

        # Verify restored
        assert src.read_text() == original

        # Generated files removed
        assert not (tmp_path / "otel_setup.py").exists()
        assert not (tmp_path / "otel-collector-config.yaml").exists()

        # Backup dir cleaned up
        assert not (tmp_path / ".code-agents" / "migration-backup").exists()

    def test_rollback_no_backup_returns_false(self, tmp_path):
        _write(tmp_path / "app.py", "x = 1\n")
        m = TracingMigrator(str(tmp_path))
        assert m.rollback() is False

    def test_apply_creates_backup(self, tmp_path):
        src = tmp_path / "svc.py"
        _write(src, "from ddtrace import tracer\n")

        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        result = m.apply(plan, dry_run=False)

        assert result.backup_dir
        backup_dir = tmp_path / ".code-agents" / "migration-backup"
        assert backup_dir.is_dir()
        # Original file backed up
        backed = list(backup_dir.rglob("*.py"))
        assert len(backed) >= 1


# ---------------------------------------------------------------------------
# TestRiskLevel
# ---------------------------------------------------------------------------


class TestRiskLevel:
    """Verify risk level calculation."""

    def test_low_risk_few_patterns(self, tmp_path):
        _write(tmp_path / "app.py", "from jaeger_client import Config\n")
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.risk_level == "low"

    def test_medium_risk_many_patterns(self, tmp_path):
        lines = "\n".join(
            f"from jaeger_client import Config  # line {i}" for i in range(8)
        )
        _write(tmp_path / "big.py", lines + "\n")
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.risk_level in ("medium", "high")


# ---------------------------------------------------------------------------
# TestFormatting
# ---------------------------------------------------------------------------


class TestFormatting:
    """Verify format functions produce readable output."""

    def test_format_migration_plan(self):
        plan = MigrationPlan(
            detected_framework="jaeger",
            language="python",
            patterns_found=[
                TracingPattern(
                    file="app.py", line=1, old_pattern="jaeger",
                    old_code="from jaeger_client import Config",
                    new_code="from opentelemetry import trace",
                    confidence=0.95,
                ),
            ],
            dependency_changes=[
                DependencyChange(action="remove", package="jaeger-client", version="", file="pyproject.toml"),
                DependencyChange(action="add", package="opentelemetry-api", version="1.24.0", file="pyproject.toml"),
            ],
            config_changes=[
                ConfigChange(file=".env", old_content="", new_content="", description="Update env vars"),
            ],
            risk_level="low",
        )
        output = format_migration_plan(plan)
        assert "jaeger" in output
        assert "python" in output
        assert "opentelemetry" in output.lower()
        assert "low" in output

    def test_format_migration_result(self):
        result = MigrationResult(
            files_modified=3, files_created=2,
            dependencies_changed=4, backup_dir="/tmp/backup",
            success=True,
        )
        output = format_migration_result(result)
        assert "SUCCESS" in output
        assert "3" in output
        assert "/tmp/backup" in output

    def test_format_failed_result(self):
        result = MigrationResult(success=False)
        output = format_migration_result(result)
        assert "FAILED" in output


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_nonexistent_repo_raises(self):
        with pytest.raises(FileNotFoundError):
            TracingMigrator("/nonexistent/path/abc123")

    def test_empty_repo(self, tmp_path):
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "none"
        assert plan.patterns_found == []

    def test_skips_hidden_dirs(self, tmp_path):
        # File in hidden dir should be ignored
        _write(tmp_path / ".hidden" / "trace.py", "from jaeger_client import Config\n")
        _write(tmp_path / "app.py", "x = 1\n")
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "none"

    def test_multiple_frameworks_picks_dominant(self, tmp_path):
        # More jaeger than datadog
        _write(tmp_path / "a.py", "from jaeger_client import Config\n")
        _write(tmp_path / "b.py", "from jaeger_client import Config\n")
        _write(tmp_path / "c.py", "from ddtrace import tracer\n")
        m = TracingMigrator(str(tmp_path))
        plan = m.scan()
        assert plan.detected_framework == "jaeger"
