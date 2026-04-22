"""Tests for the CacheDesigner module."""

import textwrap
import pytest
from code_agents.observability.cache_designer import (
    CacheDesigner, CacheDesignerConfig, CacheDesignerReport, format_cache_report,
)


class TestCacheDesigner:
    def test_detect_db_read_pattern(self, tmp_path):
        source = textwrap.dedent('''\
            def get_user(user_id):
                return db.query(User).filter(id=user_id).first()
        ''')
        (tmp_path / "repo.py").write_text(source)
        designer = CacheDesigner(CacheDesignerConfig(cwd=str(tmp_path)))
        report = designer.analyze()
        assert report.access_patterns_found >= 1
        assert any(p.access_type == "db_read" for p in report.patterns)

    def test_detect_api_call_pattern(self, tmp_path):
        source = textwrap.dedent('''\
            import requests
            def fetch_weather(city):
                return requests.get(f"https://api.weather.com/{city}")
        ''')
        (tmp_path / "weather.py").write_text(source)
        designer = CacheDesigner(CacheDesignerConfig(cwd=str(tmp_path)))
        report = designer.analyze()
        assert any(p.access_type == "api_call" for p in report.patterns)

    def test_generates_cache_strategy(self, tmp_path):
        source = textwrap.dedent('''\
            def get_config():
                return os.getenv("APP_MODE")

            def get_user(uid):
                return db.query(User).filter(id=uid).first()
        ''')
        (tmp_path / "service.py").write_text(source)
        designer = CacheDesigner(CacheDesignerConfig(cwd=str(tmp_path)))
        report = designer.analyze()
        assert len(report.strategies) >= 1
        assert any(s.backend in ("in_memory", "redis", "lru_cache") for s in report.strategies)

    def test_read_write_ratio(self, tmp_path):
        source = textwrap.dedent('''\
            def read(): return db.query(User).all()
            def write(): db.insert(User(name="x"))
        ''')
        (tmp_path / "ops.py").write_text(source)
        designer = CacheDesigner(CacheDesignerConfig(cwd=str(tmp_path)))
        report = designer.analyze()
        assert "reads" in report.read_write_ratio

    def test_empty_codebase(self, tmp_path):
        designer = CacheDesigner(CacheDesignerConfig(cwd=str(tmp_path)))
        report = designer.analyze()
        assert report.access_patterns_found == 0
        assert len(report.strategies) == 0

    def test_format_report(self):
        report = CacheDesignerReport(
            files_scanned=10, access_patterns_found=5,
            read_write_ratio="80% reads / 20% writes", summary="done",
        )
        output = format_cache_report(report)
        assert "Cache Designer" in output
        assert "Read/write ratio" in output
