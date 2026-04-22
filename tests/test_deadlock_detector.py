"""Tests for the DeadlockDetector module."""

import textwrap
import pytest
from code_agents.observability.deadlock_detector import DeadlockDetector, DeadlockDetectorConfig, DeadlockReport, format_deadlock_report


class TestDeadlockDetector:
    def test_detect_time_sleep_in_async(self, tmp_path):
        source = textwrap.dedent('''\
            import asyncio
            import time

            async def handler():
                time.sleep(5)
        ''')
        (tmp_path / "app.py").write_text(source)
        result = DeadlockDetector(DeadlockDetectorConfig(cwd=str(tmp_path))).scan()
        assert result.async_usage is True
        assert any(f.pattern == "time_sleep_in_async" for f in result.findings)

    def test_detect_fire_and_forget(self, tmp_path):
        source = textwrap.dedent('''\
            import asyncio

            async def handler():
                asyncio.create_task(do_work())
        ''')
        (tmp_path / "app.py").write_text(source)
        result = DeadlockDetector(DeadlockDetectorConfig(cwd=str(tmp_path))).scan()
        assert any(f.pattern == "fire_and_forget_task" for f in result.findings)

    def test_detect_thread_usage(self, tmp_path):
        source = textwrap.dedent('''\
            import threading

            def worker():
                pass

            t = threading.Thread(target=worker)
        ''')
        (tmp_path / "app.py").write_text(source)
        result = DeadlockDetector(DeadlockDetectorConfig(cwd=str(tmp_path))).scan()
        assert result.thread_usage is True

    def test_no_findings_clean_code(self, tmp_path):
        source = textwrap.dedent('''\
            def pure_function(x):
                return x * 2
        ''')
        (tmp_path / "app.py").write_text(source)
        result = DeadlockDetector(DeadlockDetectorConfig(cwd=str(tmp_path))).scan()
        assert len(result.findings) == 0

    def test_format_output(self):
        report = DeadlockReport(summary="3 hazards", files_scanned=5)
        output = format_deadlock_report(report)
        assert "Concurrency" in output
