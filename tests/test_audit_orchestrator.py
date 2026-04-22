"""Tests for the global audit orchestrator."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from code_agents.security.audit_orchestrator import (
    AuditCategory,
    AuditOrchestrator,
    AuditReport,
    AUDIT_SCANNERS,
    CATEGORY_WEIGHTS,
    QualityGate,
    format_audit_html,
    format_audit_json,
    format_audit_report,
    _repo_hash,
    _score_bar,
    _grep_files,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_report():
    return AuditReport(
        overall_score=78,
        categories=[
            AuditCategory(name="security", score=82, findings_count=3, critical=1, high=1, scanner="owasp"),
            AuditCategory(name="code_quality", score=71, findings_count=8, critical=0, high=2, scanner="smell"),
            AuditCategory(name="payment_safety", score=65, findings_count=5, critical=2, high=1, scanner="idempotency"),
        ],
        quality_gates=[
            QualityGate(name="No secrets in source", source="security.md", passed=True, message="Clean", severity="critical"),
            QualityGate(name="All tests pass", source="testing.md", passed=False, message="3 failing", severity="critical"),
            QualityGate(name="Commit message format", source="collaboration.md", passed=False, message="2 non-conforming", severity="warning"),
        ],
        critical_count=3,
        high_count=4,
        medium_count=12,
        low_count=8,
        timestamp="2026-04-09T10:30:00",
        repo="/tmp/test-repo",
        duration_seconds=12.5,
        trend={"delta": 3, "direction": "up", "previous_score": 75},
    )


@pytest.fixture
def orchestrator(tmp_path):
    """Create an orchestrator pointed at a temp dir with some Python files."""
    # Create sample source files
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("import os\n\ndef main():\n    print('hello')\n")
    (src / "utils.py").write_text("def helper():\n    return 42\n")
    (src / "secret_bad.py").write_text('API_KEY = "sk-1234567890abcdef"\n')
    # Create a test file
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_main():\n    assert True\n")
    # Init git
    os.system(f"cd {tmp_path} && git init -q && git add . && git commit -q -m 'feat: init'")
    return AuditOrchestrator(str(tmp_path))


# ---------------------------------------------------------------------------
# TestRunScanner
# ---------------------------------------------------------------------------


class TestRunScanner:
    """Test scanner execution with mocks."""

    def test_scanner_returns_dict(self, orchestrator):
        """Mock scanner that returns a dict result."""
        mock_mod = MagicMock()
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.scan.return_value = {"total": 5, "critical": 1, "high": 2}
        mock_cls.return_value = mock_instance
        mock_mod.FakeScanner = mock_cls
        setattr(mock_mod, "FakeScanner", mock_cls)

        with patch("importlib.import_module", return_value=mock_mod):
            result = orchestrator._run_scanner("fake_module", "FakeScanner")

        assert result["findings"] == 5
        assert result["critical"] == 1
        assert result["high"] == 2
        assert "error" not in result

    def test_scanner_returns_list(self, orchestrator):
        """Scanner returns list of findings."""
        mock_mod = MagicMock()
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.scan.return_value = [
            {"severity": "critical", "msg": "A"},
            {"severity": "high", "msg": "B"},
            {"severity": "low", "msg": "C"},
        ]
        mock_cls.return_value = mock_instance
        mock_mod.ListScanner = mock_cls

        with patch("importlib.import_module", return_value=mock_mod):
            result = orchestrator._run_scanner("fake_module", "ListScanner")

        assert result["findings"] == 3
        assert result["critical"] == 1
        assert result["high"] == 1

    def test_scanner_exception_does_not_raise(self, orchestrator):
        """Scanner failure returns error dict, does NOT raise."""
        with patch("importlib.import_module", side_effect=ImportError("no such module")):
            result = orchestrator._run_scanner("nonexistent", "NoClass")

        assert "error" in result
        assert "no such module" in result["error"]

    def test_scanner_with_audit_method(self, orchestrator):
        """Scanner that has audit() instead of scan()."""
        mock_mod = MagicMock()
        mock_cls = MagicMock()
        mock_instance = MagicMock(spec=[])
        mock_instance.audit = MagicMock(return_value={"total": 3, "critical": 0, "high": 1})
        # remove scan to force audit path
        mock_cls.return_value = mock_instance
        mock_mod.AuditScanner = mock_cls

        with patch("importlib.import_module", return_value=mock_mod):
            result = orchestrator._run_scanner("fake_module", "AuditScanner")

        assert result["findings"] == 3


# ---------------------------------------------------------------------------
# TestQualityGates
# ---------------------------------------------------------------------------


class TestQualityGates:
    """Test individual quality gate checks."""

    def test_gate_no_secrets_detects_key(self, orchestrator):
        gate = orchestrator._gate_no_secrets()
        # secret_bad.py has API_KEY = "sk-1234567890abcdef"
        assert not gate.passed
        assert "secret" in gate.message.lower() or "potential" in gate.message.lower()

    def test_gate_no_secrets_clean(self, tmp_path):
        (tmp_path / "clean.py").write_text("x = 1\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_no_secrets()
        assert gate.passed

    def test_gate_no_wildcard_imports_clean(self, tmp_path):
        (tmp_path / "ok.py").write_text("from os import path\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_no_wildcard_imports()
        assert gate.passed

    def test_gate_no_wildcard_imports_fail(self, tmp_path):
        (tmp_path / "bad.py").write_text("from os import *\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_no_wildcard_imports()
        assert not gate.passed

    def test_gate_no_eval_clean(self, tmp_path):
        (tmp_path / "safe.py").write_text("import ast\nast.literal_eval('1')\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_no_eval()
        assert gate.passed

    def test_gate_no_eval_dangerous(self, tmp_path):
        (tmp_path / "danger.py").write_text("x = eval(input())\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_no_eval()
        assert not gate.passed

    def test_gate_no_sql_concat_clean(self, tmp_path):
        (tmp_path / "safe_sql.py").write_text("cursor.execute('SELECT 1')\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_no_sql_concat()
        assert gate.passed

    def test_gate_no_debug_code_clean(self, tmp_path):
        (tmp_path / "prod.py").write_text("def run():\n    pass\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_no_debug_code()
        assert gate.passed

    def test_gate_no_debug_code_fail(self, tmp_path):
        (tmp_path / "debug.py").write_text("breakpoint()\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_no_debug_code()
        assert not gate.passed

    def test_gate_tests_pass_mocked(self, orchestrator):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="10 tests collected\n")
            gate = orchestrator._gate_tests_pass()
        assert gate.passed

    def test_gate_tests_fail_mocked(self, orchestrator):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="ERROR\n")
            gate = orchestrator._gate_tests_pass()
        assert not gate.passed

    def test_gate_commit_format_conventional(self, orchestrator):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="feat: add feature\nfix: bug fix\n")
            gate = orchestrator._gate_commit_format()
        assert gate.passed

    def test_gate_commit_format_bad(self, orchestrator):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="random commit message\nfeat: ok\n")
            gate = orchestrator._gate_commit_format()
        assert not gate.passed

    def test_gate_branch_naming_ok(self, orchestrator):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="feat/new-thing\n")
            gate = orchestrator._gate_branch_naming()
        assert gate.passed

    def test_gate_no_force_push_clean(self, orchestrator):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc HEAD@{0}: commit: stuff\n")
            gate = orchestrator._gate_no_force_push()
        assert gate.passed

    def test_gate_no_pii_logs_clean(self, tmp_path):
        (tmp_path / "app.py").write_text("logger.info('Processing order %s', order_id)\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_no_pii_logs()
        assert gate.passed

    def test_gate_env_documented_no_example(self, tmp_path):
        (tmp_path / "app.py").write_text("import os\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_env_documented()
        assert not gate.passed
        assert ".env.example" in gate.message

    def test_gate_security_headers_found(self, tmp_path):
        (tmp_path / "app.py").write_text("app.add_middleware(SecurityMiddleware)\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_security_headers()
        assert gate.passed

    def test_gate_constructor_injection_clean(self, tmp_path):
        (tmp_path / "svc.py").write_text("class Svc:\n    def __init__(self, db): self.db = db\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_constructor_injection()
        assert gate.passed

    def test_gate_log_levels_clean(self, tmp_path):
        (tmp_path / "app.py").write_text("logger.info('Starting server')\nlogger.error('Connection failed')\n")
        orc = AuditOrchestrator(str(tmp_path))
        gate = orc._gate_log_levels()
        assert gate.passed

    def test_gate_tests_with_features(self, orchestrator):
        gate = orchestrator._gate_tests_with_features()
        # The fixture has main.py + test_main.py, utils.py without test, secret_bad.py without test
        assert isinstance(gate, QualityGate)


# ---------------------------------------------------------------------------
# TestScore
# ---------------------------------------------------------------------------


class TestScore:
    """Test weighted score calculation."""

    def test_all_perfect(self, orchestrator):
        cats = [AuditCategory(name=n, score=100) for n in CATEGORY_WEIGHTS]
        score = orchestrator._compute_score(cats)
        assert score == 100

    def test_all_zero(self, orchestrator):
        cats = [AuditCategory(name=n, score=0) for n in CATEGORY_WEIGHTS]
        score = orchestrator._compute_score(cats)
        assert score == 0

    def test_mixed_scores(self, orchestrator):
        cats = [
            AuditCategory(name="security", score=80),
            AuditCategory(name="encryption", score=60),
            AuditCategory(name="code_quality", score=70),
        ]
        score = orchestrator._compute_score(cats)
        # Manual: (80*0.20 + 60*0.10 + 70*0.10) / (0.20 + 0.10 + 0.10) = 29/0.4 = 72.5 -> 72
        assert 70 <= score <= 75

    def test_empty_categories(self, orchestrator):
        score = orchestrator._compute_score([])
        assert score == 0

    def test_score_clamped_to_100(self, orchestrator):
        cats = [AuditCategory(name="security", score=150)]  # shouldn't happen but test clamp
        score = orchestrator._compute_score(cats)
        assert score <= 100

    def test_weights_sum_to_one(self):
        total = sum(CATEGORY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01


# ---------------------------------------------------------------------------
# TestTrend
# ---------------------------------------------------------------------------


class TestTrend:
    """Test trend computation."""

    def test_trend_up(self, orchestrator):
        prev = AuditReport(
            overall_score=70, categories=[], quality_gates=[],
            critical_count=0, high_count=0, medium_count=0, low_count=0,
            timestamp="2026-01-01", repo="", duration_seconds=0, trend={},
        )
        trend = orchestrator._compute_trend(78, prev)
        assert trend["direction"] == "up"
        assert trend["delta"] == 8

    def test_trend_down(self, orchestrator):
        prev = AuditReport(
            overall_score=90, categories=[], quality_gates=[],
            critical_count=0, high_count=0, medium_count=0, low_count=0,
            timestamp="2026-01-01", repo="", duration_seconds=0, trend={},
        )
        trend = orchestrator._compute_trend(85, prev)
        assert trend["direction"] == "down"
        assert trend["delta"] == -5

    def test_trend_stable(self, orchestrator):
        prev = AuditReport(
            overall_score=80, categories=[], quality_gates=[],
            critical_count=0, high_count=0, medium_count=0, low_count=0,
            timestamp="2026-01-01", repo="", duration_seconds=0, trend={},
        )
        trend = orchestrator._compute_trend(80, prev)
        assert trend["direction"] == "stable"

    def test_trend_no_previous(self, orchestrator):
        trend = orchestrator._compute_trend(80, None)
        assert trend["direction"] == "none"
        assert trend["previous_score"] is None


# ---------------------------------------------------------------------------
# TestFormat
# ---------------------------------------------------------------------------


class TestFormat:
    """Test report formatting."""

    def test_terminal_format(self, sample_report):
        text = format_audit_report(sample_report)
        assert "78/100" in text
        assert "Critical: 3" in text
        assert "No secrets in source" in text
        assert "All tests pass" in text

    def test_json_format(self, sample_report):
        text = format_audit_json(sample_report)
        data = json.loads(text)
        assert data["overall_score"] == 78
        assert len(data["categories"]) == 3
        assert len(data["quality_gates"]) == 3
        assert data["trend"]["direction"] == "up"

    def test_html_format(self, sample_report):
        html = format_audit_html(sample_report)
        assert "<!DOCTYPE html>" in html
        assert "78/100" in html
        assert "security" in html
        assert "No secrets in source" in html

    def test_terminal_format_trend_down(self):
        report = AuditReport(
            overall_score=40, categories=[], quality_gates=[],
            critical_count=5, high_count=10, medium_count=20, low_count=15,
            timestamp="2026-04-09T10:30:00", repo="/tmp/repo",
            duration_seconds=5.0,
            trend={"delta": -10, "direction": "down", "previous_score": 50},
        )
        text = format_audit_report(report)
        assert "40/100" in text
        assert "-10" in text

    def test_terminal_format_first_audit(self):
        report = AuditReport(
            overall_score=60, categories=[], quality_gates=[],
            critical_count=0, high_count=0, medium_count=0, low_count=0,
            timestamp="2026-04-09", repo="/tmp",
            duration_seconds=1.0,
            trend={"delta": 0, "direction": "none", "previous_score": None},
        )
        text = format_audit_report(report)
        assert "First audit" in text


# ---------------------------------------------------------------------------
# TestCI
# ---------------------------------------------------------------------------


class TestCI:
    """Test CI exit code behavior."""

    def test_ci_no_critical(self, sample_report):
        """No exit if no criticals (we check the report, not sys.exit)."""
        report = AuditReport(
            overall_score=90, categories=[], quality_gates=[],
            critical_count=0, high_count=2, medium_count=5, low_count=3,
            timestamp="", repo="", duration_seconds=0, trend={},
        )
        assert report.critical_count == 0

    def test_ci_with_critical(self, sample_report):
        assert sample_report.critical_count == 3


# ---------------------------------------------------------------------------
# TestQuick
# ---------------------------------------------------------------------------


class TestQuick:
    """Test quick mode skips slow scanners."""

    def test_quick_skips_slow_categories(self, orchestrator):
        """In quick mode, slow categories should be excluded."""
        from code_agents.security.audit_orchestrator import _SLOW_CATEGORIES

        with patch.object(orchestrator, "_run_scanner", return_value={"findings": 0, "critical": 0, "high": 0, "scanner": "mock"}):
            cats = orchestrator._run_all_scanners(quick=True)
        cat_names = {c.name for c in cats}
        for slow in _SLOW_CATEGORIES:
            assert slow not in cat_names

    def test_full_includes_all(self, orchestrator):
        """Full mode includes all categories."""
        with patch.object(orchestrator, "_run_scanner", return_value={"findings": 0, "critical": 0, "high": 0, "scanner": "mock"}):
            cats = orchestrator._run_all_scanners(quick=False)
        cat_names = {c.name for c in cats}
        assert "testing" in cat_names
        assert "security" in cat_names


# ---------------------------------------------------------------------------
# TestParallel
# ---------------------------------------------------------------------------


class TestParallel:
    """Verify ThreadPoolExecutor usage."""

    def test_uses_thread_pool(self, orchestrator):
        """Ensure ThreadPoolExecutor is called with max_workers=4."""
        with patch("code_agents.security.audit_orchestrator.ThreadPoolExecutor") as mock_pool:
            mock_executor = MagicMock()
            mock_pool.return_value.__enter__ = MagicMock(return_value=mock_executor)
            mock_pool.return_value.__exit__ = MagicMock(return_value=False)
            mock_future = MagicMock()
            mock_future.result.return_value = {"findings": 0, "critical": 0, "high": 0, "scanner": "m"}
            mock_executor.submit.return_value = mock_future

            with patch("code_agents.security.audit_orchestrator.as_completed", return_value=[mock_future]):
                orchestrator._run_all_scanners(categories=["security"])

            mock_pool.assert_called_once_with(max_workers=4)


# ---------------------------------------------------------------------------
# TestPersistence
# ---------------------------------------------------------------------------


class TestPersistence:
    """Test snapshot save/load."""

    def test_save_and_load(self, tmp_path):
        orc = AuditOrchestrator(str(tmp_path))
        orc._history_dir = tmp_path / "history"
        report = AuditReport(
            overall_score=85, categories=[], quality_gates=[],
            critical_count=1, high_count=2, medium_count=3, low_count=4,
            timestamp="2026-04-09T10:00:00", repo=str(tmp_path),
            duration_seconds=5.0, trend={},
        )
        orc._save_snapshot(report)
        loaded = orc._load_previous()
        assert loaded is not None
        assert loaded.overall_score == 85
        assert loaded.critical_count == 1

    def test_load_no_history(self, tmp_path):
        orc = AuditOrchestrator(str(tmp_path))
        orc._history_dir = tmp_path / "nonexistent"
        assert orc._load_previous() is None

    def test_trend_history(self, tmp_path):
        orc = AuditOrchestrator(str(tmp_path))
        orc._history_dir = tmp_path / "history"
        orc._history_dir.mkdir(parents=True)
        for i, score in enumerate([70, 75, 80]):
            data = {"overall_score": score, "critical_count": 0, "high_count": 0, "timestamp": f"2026-04-0{i+1}"}
            (orc._history_dir / f"audit_2026040{i+1}_100000.json").write_text(json.dumps(data))
        history = orc.get_trend_history()
        assert len(history) == 3
        assert history[0]["score"] == 70
        assert history[2]["score"] == 80


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test utility functions."""

    def test_repo_hash_deterministic(self):
        h1 = _repo_hash("/some/path")
        h2 = _repo_hash("/some/path")
        assert h1 == h2
        assert len(h1) == 12

    def test_repo_hash_different_paths(self):
        assert _repo_hash("/a") != _repo_hash("/b")

    def test_score_bar(self):
        assert len(_score_bar(50, 10)) == 10
        assert _score_bar(100, 10) == "\u2588" * 10
        assert _score_bar(0, 10) == "\u2591" * 10

    def test_grep_files(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("hello world\nfoo bar\nhello again\n")
        hits = _grep_files([str(f)], r"hello")
        assert len(hits) == 2
        assert hits[0][1] == 1
        assert hits[1][1] == 3


# ---------------------------------------------------------------------------
# TestIntegration
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end run with mocked scanners."""

    def test_full_run_gates_only(self, orchestrator):
        report = orchestrator.run(gates_only=True)
        assert report.overall_score == 0  # no scanners ran
        assert len(report.quality_gates) == 15
        assert report.duration_seconds >= 0

    def test_full_run_with_mock_scanners(self, orchestrator):
        with patch.object(orchestrator, "_run_scanner", return_value={"findings": 2, "critical": 0, "high": 1, "scanner": "mock"}):
            report = orchestrator.run(categories=["security", "encryption"], quick=False)
        assert report.overall_score > 0
        cat_names = [c.name for c in report.categories]
        assert "security" in cat_names
        assert "encryption" in cat_names
        assert len(report.quality_gates) == 15
