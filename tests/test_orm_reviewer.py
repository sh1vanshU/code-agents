"""Tests for code_agents.orm_reviewer."""

import textwrap
import pytest
from code_agents.api.orm_reviewer import OrmReviewer, OrmReviewConfig, OrmReviewResult, format_orm_review


class TestOrmReviewer:
    def test_detect_raw_sql(self, tmp_path):
        source = textwrap.dedent('''\
            from sqlalchemy import text
            def get_users(session):
                result = session.execute("SELECT * FROM users WHERE id = 1")
                return result
        ''')
        (tmp_path / "repo.py").write_text(source)
        result = OrmReviewer(OrmReviewConfig(cwd=str(tmp_path))).scan()
        assert any(f.pattern == "raw_sql" for f in result.findings)

    def test_detect_orm_type(self, tmp_path):
        source = "from sqlalchemy import Column\nclass User: pass\n"
        (tmp_path / "models.py").write_text(source)
        result = OrmReviewer(OrmReviewConfig(cwd=str(tmp_path))).scan()
        assert result.orm_detected == "sqlalchemy"

    def test_no_findings_on_non_orm(self, tmp_path):
        source = "def hello(): return 'world'\n"
        (tmp_path / "app.py").write_text(source)
        result = OrmReviewer(OrmReviewConfig(cwd=str(tmp_path))).scan()
        assert result.files_scanned == 0

    def test_empty_codebase(self, tmp_path):
        result = OrmReviewer(OrmReviewConfig(cwd=str(tmp_path))).scan()
        assert len(result.findings) == 0

    def test_format_output(self):
        result = OrmReviewResult(summary="2 issues in 5 files")
        output = format_orm_review(result)
        assert "ORM Reviewer" in output
