"""Tests for dead_code_reaper.py — find truly unreachable code."""

import pytest

from code_agents.analysis.dead_code_reaper import (
    DeadCodeReaper,
    ReaperReport,
    ReaperCandidate,
    format_report,
)


@pytest.fixture
def reaper(tmp_path):
    return DeadCodeReaper(str(tmp_path))


SAMPLE_FILES = {
    "main.py": "def active_func():\n    return 42\n\ndef _unused_helper():\n    pass\n",
    "utils.py": "def shared_util():\n    return True\n\nclass OldHandler:\n    pass\n",
}


class TestExtractSegments:
    def test_finds_functions(self, reaper):
        segs = reaper._extract_segments("main.py", SAMPLE_FILES["main.py"])
        names = [s.name for s in segs]
        assert "active_func" in names
        assert "_unused_helper" in names

    def test_finds_classes(self, reaper):
        segs = reaper._extract_segments("utils.py", SAMPLE_FILES["utils.py"])
        classes = [s for s in segs if s.kind == "class"]
        assert len(classes) >= 1

    def test_empty_file(self, reaper):
        segs = reaper._extract_segments("empty.py", "")
        assert segs == []


class TestScoreSegment:
    def test_no_references_increases_confidence(self, reaper):
        from code_agents.analysis.dead_code_reaper import CodeSegment
        seg = CodeSegment(name="orphan_func", kind="function", file_path="a.py",
                          start_line=1, end_line=5, lines_of_code=5)
        candidate = reaper._score_segment(seg, {}, {}, {})
        assert candidate.confidence > 0.3

    def test_private_gets_bonus(self, reaper):
        from code_agents.analysis.dead_code_reaper import CodeSegment
        seg = CodeSegment(name="_private", kind="function", file_path="a.py",
                          start_line=1, end_line=3, lines_of_code=3)
        candidate = reaper._score_segment(seg, {}, {}, {})
        assert candidate.confidence > 0.4


class TestAnalyze:
    def test_full_analysis(self, reaper):
        report = reaper.analyze(SAMPLE_FILES)
        assert isinstance(report, ReaperReport)
        assert report.total_loc_analyzed > 0
        assert len(report.candidates) >= 1

    def test_with_coverage_data(self, reaper):
        coverage = {"main.py": {"covered": [1, 2]}}
        report = reaper.analyze(SAMPLE_FILES, coverage_data=coverage)
        assert report.total_loc_analyzed > 0

    def test_with_feature_flags(self, reaper):
        files = {"app.py": "def old_feature():\n    pass\n"}
        flags = {"old_feature": False}
        report = reaper.analyze(files, feature_flags=flags)
        assert len(report.candidates) >= 1

    def test_format_report(self, reaper):
        report = reaper.analyze(SAMPLE_FILES)
        text = format_report(report)
        assert "Dead Code Reaper" in text
