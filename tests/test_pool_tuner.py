"""Tests for the PoolTuner module."""

import textwrap
import pytest
from code_agents.observability.pool_tuner import (
    PoolTuner, PoolTunerConfig, PoolTunerReport, format_pool_report,
)


class TestPoolTuner:
    def test_detect_db_pool(self, tmp_path):
        source = textwrap.dedent('''\
            from sqlalchemy import create_engine
            engine = create_engine("postgresql://localhost/db", pool_size=5)
        ''')
        (tmp_path / "db.py").write_text(source)
        tuner = PoolTuner(PoolTunerConfig(cwd=str(tmp_path)))
        report = tuner.analyze()
        assert report.pools_found >= 1
        assert any(u.pool_type == "db" for u in report.usages)

    def test_detect_thread_pool(self, tmp_path):
        source = 'executor = ThreadPoolExecutor(max_workers=8)\n'
        (tmp_path / "worker.py").write_text(source)
        tuner = PoolTuner(PoolTunerConfig(cwd=str(tmp_path)))
        report = tuner.analyze()
        assert any(u.pool_type == "thread" for u in report.usages)
        assert any(u.current_size == 8 for u in report.usages)

    def test_detect_redis_pool(self, tmp_path):
        source = 'pool = redis.ConnectionPool(max_connections=20)\n'
        (tmp_path / "cache.py").write_text(source)
        tuner = PoolTuner(PoolTunerConfig(cwd=str(tmp_path)))
        report = tuner.analyze()
        assert any(u.pool_type == "redis" for u in report.usages)

    def test_generates_recommendations(self, tmp_path):
        source = textwrap.dedent('''\
            from sqlalchemy import create_engine
            engine = create_engine("postgresql://localhost/db")
        ''')
        (tmp_path / "db.py").write_text(source)
        tuner = PoolTuner(PoolTunerConfig(cwd=str(tmp_path), target_concurrency=200))
        report = tuner.analyze()
        assert len(report.recommendations) >= 1
        rec = report.recommendations[0]
        assert rec.recommended_size > 0
        assert rec.config_snippet != ""

    def test_empty_codebase(self, tmp_path):
        tuner = PoolTuner(PoolTunerConfig(cwd=str(tmp_path)))
        report = tuner.analyze()
        assert report.pools_found == 0

    def test_format_report(self):
        report = PoolTunerReport(files_scanned=10, pools_found=3, summary="done")
        output = format_pool_report(report)
        assert "Pool Tuner" in output
        assert "Pools found" in output
