"""Tests for clone_lineage.py — copy-paste code tracking."""

import pytest

from code_agents.analysis.clone_lineage import (
    CloneLineage,
    LineageReport,
    CodeClone,
    format_report,
)


@pytest.fixture
def tracker(tmp_path):
    return CloneLineage(str(tmp_path), min_lines=3)


CLONE_FILES = {
    "a.py": "def process(data):\n    result = []\n    for item in data:\n        result.append(item)\n    return result\n",
    "b.py": "def process(data):\n    result = []\n    for item in data:\n        result.append(item)\n    return result\n",
    "c.py": "def unique_func():\n    return 42\n",
}


class TestExtractBlocks:
    def test_extracts_blocks(self, tracker):
        blocks = tracker._extract_blocks("a.py", CLONE_FILES["a.py"])
        assert len(blocks) >= 1

    def test_skips_blank_blocks(self, tracker):
        blocks = tracker._extract_blocks("e.py", "\n\n\n\n\n\n")
        assert len(blocks) == 0


class TestNormalize:
    def test_normalizes_identifiers(self, tracker):
        result = tracker._normalize("for item in data:\n    process(item)")
        assert "VAR" in result

    def test_normalizes_whitespace(self, tracker):
        r1 = tracker._normalize("x  =  1")
        r2 = tracker._normalize("x = 1")
        assert r1 == r2


class TestFindCloneGroups:
    def test_finds_clones(self, tracker):
        blocks_a = tracker._extract_blocks("a.py", CLONE_FILES["a.py"])
        blocks_b = tracker._extract_blocks("b.py", CLONE_FILES["b.py"])
        groups = tracker._find_clone_groups(blocks_a + blocks_b)
        assert len(groups) >= 1


class TestAnalyze:
    def test_full_analysis(self, tracker):
        report = tracker.analyze(CLONE_FILES)
        assert isinstance(report, LineageReport)
        assert report.total_clones >= 2

    def test_clone_percentage(self, tracker):
        report = tracker.analyze(CLONE_FILES)
        assert report.clone_percentage >= 0

    def test_with_recent_changes(self, tracker):
        changes = {"a.py": [1, 2, 3]}
        report = tracker.analyze(CLONE_FILES, recent_changes=changes)
        # Should suggest propagation if clones found
        assert isinstance(report, LineageReport)

    def test_format_report(self, tracker):
        report = tracker.analyze(CLONE_FILES)
        text = format_report(report)
        assert "Clone Lineage" in text
