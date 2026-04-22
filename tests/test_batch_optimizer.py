"""Tests for the BatchOptimizer module."""

import textwrap
import pytest
from code_agents.observability.batch_optimizer import (
    BatchOptimizer, BatchOptimizerConfig, BatchOptimizerReport, format_batch_report,
)


class TestBatchOptimizer:
    def test_detect_db_query_in_loop(self, tmp_path):
        source = textwrap.dedent('''\
            def process_users(user_ids):
                for uid in user_ids:
                    user = db.get(uid)
                    print(user)
        ''')
        (tmp_path / "service.py").write_text(source)
        optimizer = BatchOptimizer(BatchOptimizerConfig(cwd=str(tmp_path)))
        report = optimizer.analyze()
        assert report.loop_ops_found >= 1
        assert any(s.op_type == "db_query" for s in report.suggestions)

    def test_detect_api_call_in_loop(self, tmp_path):
        source = textwrap.dedent('''\
            import requests
            def fetch_all(urls):
                for url in urls:
                    requests.get(url)
        ''')
        (tmp_path / "fetcher.py").write_text(source)
        optimizer = BatchOptimizer(BatchOptimizerConfig(cwd=str(tmp_path)))
        report = optimizer.analyze()
        assert any(s.op_type == "api_call" for s in report.suggestions)
        assert any("concurrent" in s.batch_alternative.lower() or "batch" in s.batch_alternative.lower()
                    for s in report.suggestions)

    def test_detect_cache_op_in_loop(self, tmp_path):
        source = textwrap.dedent('''\
            def warm_cache(keys):
                for key in keys:
                    redis.get(key)
        ''')
        (tmp_path / "cache.py").write_text(source)
        optimizer = BatchOptimizer(BatchOptimizerConfig(cwd=str(tmp_path)))
        report = optimizer.analyze()
        assert any(s.op_type == "cache_op" for s in report.suggestions)

    def test_clean_loop_no_findings(self, tmp_path):
        source = textwrap.dedent('''\
            def sum_list(items):
                total = 0
                for item in items:
                    total += item
                return total
        ''')
        (tmp_path / "math.py").write_text(source)
        optimizer = BatchOptimizer(BatchOptimizerConfig(cwd=str(tmp_path)))
        report = optimizer.analyze()
        assert report.loop_ops_found == 0

    def test_suggestions_have_implementation(self, tmp_path):
        source = textwrap.dedent('''\
            def sync_all(ids):
                for id in ids:
                    db.save(id)
        ''')
        (tmp_path / "sync.py").write_text(source)
        optimizer = BatchOptimizer(BatchOptimizerConfig(cwd=str(tmp_path)))
        report = optimizer.analyze()
        for s in report.suggestions:
            assert s.estimated_speedup != ""

    def test_format_report(self):
        report = BatchOptimizerReport(
            files_scanned=5, loop_ops_found=3, summary="done",
        )
        output = format_batch_report(report)
        assert "Batch Optimizer" in output
        assert "Loop operations" in output
