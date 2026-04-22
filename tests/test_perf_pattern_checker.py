"""Tests for the performance pattern checker module."""

from __future__ import annotations

import os
import pytest

from code_agents.observability.perf_pattern_checker import (
    PerfPatternChecker, PerfCheckResult, PerfFinding, check_perf_patterns,
)


class TestPerfPatternChecker:
    """Test PerfPatternChecker methods."""

    def test_init(self, tmp_path):
        checker = PerfPatternChecker(cwd=str(tmp_path))
        assert checker.cwd == str(tmp_path)

    def test_check_empty_dir(self, tmp_path):
        checker = PerfPatternChecker(cwd=str(tmp_path))
        result = checker.check()
        assert isinstance(result, PerfCheckResult)
        assert result.files_scanned == 0

    def test_check_sync_in_async(self, tmp_path):
        code = '''
import time

async def slow_handler():
    time.sleep(5)
    return {"status": "done"}
'''
        (tmp_path / "handler.py").write_text(code)
        checker = PerfPatternChecker(cwd=str(tmp_path))
        result = checker.check(categories=["async_sync_mix"])
        sync_findings = [f for f in result.findings if f.category == "async_sync_mix"]
        assert len(sync_findings) >= 1
        assert any("time.sleep" in f.message for f in sync_findings)

    def test_check_heavy_startup_import(self, tmp_path):
        code = '''import pandas
import torch

def process():
    pass
'''
        (tmp_path / "ml.py").write_text(code)
        checker = PerfPatternChecker(cwd=str(tmp_path))
        result = checker.check(categories=["startup"])
        startup_findings = [f for f in result.findings if f.category == "startup"]
        assert len(startup_findings) >= 2
        assert result.startup_imports >= 2

    def test_check_connection_per_call(self, tmp_path):
        code = '''
def get_data():
    session = requests.Session()
    return session.get("http://example.com")
'''
        (tmp_path / "client.py").write_text(code)
        checker = PerfPatternChecker(cwd=str(tmp_path))
        result = checker.check(categories=["connection"])
        conn_findings = [f for f in result.findings if f.category == "connection"]
        assert len(conn_findings) >= 1

    def test_perf_score(self, tmp_path):
        code = "def clean():\n    return 42\n"
        (tmp_path / "clean.py").write_text(code)
        checker = PerfPatternChecker(cwd=str(tmp_path))
        result = checker.check()
        assert isinstance(result.perf_score, float)
        assert result.perf_score >= 0

    def test_convenience_function(self, tmp_path):
        result = check_perf_patterns(cwd=str(tmp_path))
        assert isinstance(result, dict)
        assert "perf_score" in result
        assert "findings" in result
