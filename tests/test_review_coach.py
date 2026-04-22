"""Tests for the ReviewCoach module."""

import textwrap
import pytest
from code_agents.reviews.review_coach import (
    ReviewCoach, ReviewCoachConfig, ReviewCoachReport, format_coach_report,
)


class TestReviewCoach:
    def test_detect_broad_except(self, tmp_path):
        source = textwrap.dedent('''\
            try:
                do_something()
            except Exception:
                pass
        ''')
        (tmp_path / "handler.py").write_text(source)
        coach = ReviewCoach(ReviewCoachConfig(cwd=str(tmp_path)))
        report = coach.review(files=["handler.py"])
        assert report.total_findings >= 1
        assert any(f.category == "error_handling" for f in report.findings)

    def test_detect_global_state(self, tmp_path):
        source = 'global counter\ncounter = 0\n'
        (tmp_path / "state.py").write_text(source)
        coach = ReviewCoach(ReviewCoachConfig(cwd=str(tmp_path)))
        report = coach.review(files=["state.py"])
        assert any(f.category == "patterns" for f in report.findings)

    def test_detect_tech_debt_marker(self, tmp_path):
        source = '# TODO refactor this later\ndef hack(): pass\n'
        (tmp_path / "todo.py").write_text(source)
        coach = ReviewCoach(ReviewCoachConfig(cwd=str(tmp_path)))
        report = coach.review(files=["todo.py"])
        assert any(f.category == "tradeoffs" for f in report.findings)

    def test_review_diff(self):
        diff = textwrap.dedent('''\
            --- a/app.py
            +++ b/app.py
            @@ -1,3 +1,5 @@
            +global shared_state
            +# HACK quick fix
             def main():
                 pass
        ''')
        coach = ReviewCoach(ReviewCoachConfig())
        report = coach.review(diff=diff)
        assert report.files_reviewed >= 1
        assert report.total_findings >= 1

    def test_clean_code_strengths(self, tmp_path):
        source = textwrap.dedent('''\
            def calculate_total(prices: list[float]) -> float:
                return sum(prices)
        ''')
        (tmp_path / "calc.py").write_text(source)
        coach = ReviewCoach(ReviewCoachConfig(cwd=str(tmp_path)))
        report = coach.review(files=["calc.py"])
        assert len(report.strengths) > 0
        assert "Clean code" in report.overall_assessment or report.total_findings == 0

    def test_format_report(self):
        report = ReviewCoachReport(
            files_reviewed=3, total_findings=2,
            strengths=["Good naming"], growth_areas=["error_handling: 2"],
            overall_assessment="Good code", summary="done",
        )
        output = format_coach_report(report)
        assert "Review Coach" in output
        assert "Strengths" in output
