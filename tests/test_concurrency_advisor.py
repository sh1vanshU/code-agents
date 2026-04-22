"""Tests for the ConcurrencyAdvisor module."""

import textwrap
import pytest
from code_agents.observability.concurrency_advisor import (
    ConcurrencyAdvisor, ConcurrencyAdvisorConfig, ConcurrencyReport, format_concurrency_report,
)


class TestConcurrencyAdvisor:
    def test_detect_io_bound_pattern(self, tmp_path):
        source = textwrap.dedent('''\
            import requests
            def fetch_data():
                r1 = requests.get("https://api1.com")
                r2 = requests.get("https://api2.com")
                r3 = requests.get("https://api3.com")
                return [r1, r2, r3]
        ''')
        (tmp_path / "fetcher.py").write_text(source)
        advisor = ConcurrencyAdvisor(ConcurrencyAdvisorConfig(cwd=str(tmp_path)))
        report = advisor.analyze()
        assert report.signals_found >= 3
        assert report.async_candidates >= 1
        rec = report.recommendations[0]
        assert rec.model == "asyncio"

    def test_detect_cpu_bound_pattern(self, tmp_path):
        source = textwrap.dedent('''\
            import numpy as np
            import hashlib
            import pandas as pd

            def compute():
                data = np.array([1, 2, 3])
                df = pd.DataFrame(data)
                h = hashlib.sha256(b"test")
                return df, h
        ''')
        (tmp_path / "compute.py").write_text(source)
        advisor = ConcurrencyAdvisor(ConcurrencyAdvisorConfig(cwd=str(tmp_path)))
        report = advisor.analyze()
        assert report.multiprocess_candidates >= 1

    def test_mixed_signals_recommend_threading(self, tmp_path):
        source = textwrap.dedent('''\
            import requests
            def light_fetch():
                return requests.get("https://api.com")
        ''')
        (tmp_path / "light.py").write_text(source)
        advisor = ConcurrencyAdvisor(ConcurrencyAdvisorConfig(cwd=str(tmp_path)))
        report = advisor.analyze()
        assert report.thread_candidates >= 1

    def test_clean_code_sequential(self, tmp_path):
        source = textwrap.dedent('''\
            def pure(x):
                return x * 2
        ''')
        (tmp_path / "pure.py").write_text(source)
        advisor = ConcurrencyAdvisor(ConcurrencyAdvisorConfig(cwd=str(tmp_path)))
        report = advisor.analyze()
        assert report.async_candidates == 0
        assert report.thread_candidates == 0
        assert report.multiprocess_candidates == 0

    def test_format_report(self):
        report = ConcurrencyReport(
            files_scanned=5, signals_found=10,
            async_candidates=2, thread_candidates=1,
            summary="done",
        )
        output = format_concurrency_report(report)
        assert "Concurrency Advisor" in output
        assert "Async candidates" in output
