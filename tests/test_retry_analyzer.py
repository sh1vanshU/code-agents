"""Tests for code_agents.retry_analyzer — Payment Retry Strategy Analyzer."""

from __future__ import annotations

import os
import tempfile
import textwrap

import pytest

from code_agents.domain.retry_analyzer import (
    RetryAnalyzer,
    RetryFinding,
    RetryPattern,
    format_retry_report,
)


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory."""
    return tmp_path


def _write_file(tmp_path, name: str, content: str):
    """Helper to write a file in the temp project."""
    fpath = tmp_path / name
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(textwrap.dedent(content))
    return fpath


# ---------------------------------------------------------------------------
# Pattern detection tests
# ---------------------------------------------------------------------------

class TestFindRetryPatterns:
    def test_decorator_retry(self, tmp_project):
        _write_file(tmp_project, "service.py", """\
            import tenacity

            @retry(max_retries=3)
            def call_api():
                pass
        """)
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        patterns = analyzer._find_retry_patterns()
        assert len(patterns) >= 1
        assert patterns[0].file == "service.py"

    def test_while_loop_retry(self, tmp_project):
        _write_file(tmp_project, "client.py", """\
            def fetch():
                retry_count = 0
                while retry_count < 5:
                    try:
                        return requests.get(url)
                    except Exception:
                        retry_count += 1
                        time.sleep(2)
        """)
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        patterns = analyzer._find_retry_patterns()
        assert len(patterns) >= 1
        assert patterns[0].strategy == "fixed"

    def test_for_loop_retry(self, tmp_project):
        _write_file(tmp_project, "api.py", """\
            def send_request():
                for i in range(max_retries):
                    try:
                        resp = http.post(url)
                    except TimeoutError:
                        time.sleep(2 ** i)
        """)
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        patterns = analyzer._find_retry_patterns()
        assert len(patterns) >= 1
        assert patterns[0].strategy == "exponential"

    def test_js_retry_pattern(self, tmp_project):
        _write_file(tmp_project, "client.ts", """\
            import axiosRetry from 'axios-retry';
            axiosRetry(client, { retries: 3, retryDelay: axiosRetry.exponentialDelay });
        """)
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        patterns = analyzer._find_retry_patterns()
        assert len(patterns) >= 1

    def test_no_retry_patterns(self, tmp_project):
        _write_file(tmp_project, "clean.py", """\
            def hello():
                return "world"
        """)
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        patterns = analyzer._find_retry_patterns()
        assert len(patterns) == 0

    def test_skips_node_modules(self, tmp_project):
        _write_file(tmp_project, "node_modules/lib/retry.py", """\
            @retry(max_retries=3)
            def call(): pass
        """)
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        patterns = analyzer._find_retry_patterns()
        assert len(patterns) == 0

    def test_skips_non_code_files(self, tmp_project):
        _write_file(tmp_project, "readme.md", """\
            We use retry logic with max_retries=3
        """)
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        patterns = analyzer._find_retry_patterns()
        assert len(patterns) == 0


# ---------------------------------------------------------------------------
# Check tests
# ---------------------------------------------------------------------------

class TestCheckBackoff:
    def test_no_backoff_warns(self, tmp_project):
        p = RetryPattern(
            file="svc.py", line=10, strategy="none",
            max_retries=3, backoff="none",
            has_jitter=False, has_circuit_breaker=True,
        )
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer._check_backoff(p)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert "no backoff" in findings[0].issue.lower()

    def test_fixed_without_jitter_info(self, tmp_project):
        p = RetryPattern(
            file="svc.py", line=10, strategy="fixed",
            max_retries=3, backoff="2s fixed",
            has_jitter=False, has_circuit_breaker=True,
        )
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer._check_backoff(p)
        assert len(findings) == 1
        assert findings[0].severity == "info"

    def test_exponential_with_jitter_ok(self, tmp_project):
        p = RetryPattern(
            file="svc.py", line=10, strategy="exponential",
            max_retries=3, backoff="exponential base=2s",
            has_jitter=True, has_circuit_breaker=True,
        )
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer._check_backoff(p)
        assert len(findings) == 0


class TestCheckNonRetriable:
    def test_retrying_4xx_is_critical(self, tmp_project):
        _write_file(tmp_project, "bad_retry.py", """\
            def call():
                for i in range(max_retries):
                    resp = requests.post(url)
                    if resp.status_code == 400:
                        retry again
        """)
        p = RetryPattern(
            file="bad_retry.py", line=2, strategy="fixed",
            max_retries=3, backoff="1s fixed",
            has_jitter=False, has_circuit_breaker=False,
        )
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer._check_non_retriable(p)
        assert len(findings) == 1
        assert findings[0].severity == "critical"

    def test_no_4xx_retry_clean(self, tmp_project):
        _write_file(tmp_project, "good_retry.py", """\
            def call():
                for i in range(max_retries):
                    resp = requests.post(url)
                    if resp.status_code >= 500:
                        time.sleep(2 ** i)
        """)
        p = RetryPattern(
            file="good_retry.py", line=2, strategy="exponential",
            max_retries=3, backoff="exponential",
            has_jitter=False, has_circuit_breaker=False,
        )
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer._check_non_retriable(p)
        assert len(findings) == 0


class TestCheckCircuitBreaker:
    def test_payment_without_cb_warns(self, tmp_project):
        _write_file(tmp_project, "payment_client.py", """\
            def charge_card():
                for i in range(max_retries):
                    payment_gateway.charge()
        """)
        p = RetryPattern(
            file="payment_client.py", line=2, strategy="fixed",
            max_retries=3, backoff="1s fixed",
            has_jitter=False, has_circuit_breaker=False,
        )
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer._check_circuit_breaker(p)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert "circuit breaker" in findings[0].issue.lower()

    def test_payment_with_cb_ok(self, tmp_project):
        p = RetryPattern(
            file="payment_client.py", line=2, strategy="exponential",
            max_retries=3, backoff="exponential",
            has_jitter=True, has_circuit_breaker=True,
        )
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer._check_circuit_breaker(p)
        assert len(findings) == 0

    def test_non_payment_without_cb_ok(self, tmp_project):
        _write_file(tmp_project, "email_sender.py", """\
            def send_email():
                pass
        """)
        p = RetryPattern(
            file="email_sender.py", line=1, strategy="fixed",
            max_retries=3, backoff="1s fixed",
            has_jitter=False, has_circuit_breaker=False,
        )
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer._check_circuit_breaker(p)
        assert len(findings) == 0


class TestCheckUnbounded:
    def test_unbounded_retries_critical(self, tmp_project):
        p = RetryPattern(
            file="svc.py", line=10, strategy="fixed",
            max_retries=-1, backoff="1s fixed",
            has_jitter=False, has_circuit_breaker=True,
        )
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer._check_unbounded(p)
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert "unbounded" in findings[0].issue.lower()

    def test_excessive_retries_critical(self, tmp_project):
        p = RetryPattern(
            file="svc.py", line=10, strategy="exponential",
            max_retries=50, backoff="exponential",
            has_jitter=True, has_circuit_breaker=True,
        )
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer._check_unbounded(p)
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert "50" in findings[0].issue

    def test_reasonable_retries_ok(self, tmp_project):
        p = RetryPattern(
            file="svc.py", line=10, strategy="exponential",
            max_retries=3, backoff="exponential",
            has_jitter=True, has_circuit_breaker=True,
        )
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer._check_unbounded(p)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# Full analysis integration test
# ---------------------------------------------------------------------------

class TestAnalyzeIntegration:
    def test_full_analysis(self, tmp_project):
        _write_file(tmp_project, "payment_service.py", """\
            import time

            MAX_RETRIES = 20

            def process_payment():
                for attempt in range(MAX_RETRIES):
                    try:
                        resp = gateway.charge(amount)
                        if resp.status_code == 400:
                            retry
                    except TimeoutError:
                        time.sleep(1)
        """)
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer.analyze()
        # Should find multiple issues: excessive retries, no jitter, payment w/o CB
        assert len(findings) >= 1
        severities = {f.severity for f in findings}
        assert "critical" in severities or "warning" in severities

    def test_clean_project(self, tmp_project):
        _write_file(tmp_project, "main.py", """\
            def main():
                print("Hello, world!")
        """)
        analyzer = RetryAnalyzer(cwd=str(tmp_project))
        findings = analyzer.analyze()
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# Report formatting tests
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_empty_findings(self):
        report = format_retry_report([])
        assert "No retry issues" in report

    def test_findings_sorted_by_severity(self):
        findings = [
            RetryFinding("a.py", 1, "info issue", "info", "fix info"),
            RetryFinding("b.py", 2, "critical issue", "critical", "fix critical"),
            RetryFinding("c.py", 3, "warning issue", "warning", "fix warning"),
        ]
        report = format_retry_report(findings)
        # Critical should appear before warning and info
        crit_pos = report.index("[CRITICAL]")
        warn_pos = report.index("[WARNING]")
        info_pos = report.index("[INFO]")
        assert crit_pos < warn_pos < info_pos

    def test_summary_counts(self):
        findings = [
            RetryFinding("a.py", 1, "issue1", "critical", "fix1"),
            RetryFinding("b.py", 2, "issue2", "critical", "fix2"),
            RetryFinding("c.py", 3, "issue3", "warning", "fix3"),
        ]
        report = format_retry_report(findings)
        assert "2 critical" in report
        assert "1 warnings" in report
