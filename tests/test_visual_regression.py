"""Tests for the visual regression testing module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.testing.visual_regression import (
    VisualRegressionTester,
    VisualDiff,
)


class TestVisualDiff:
    """Test VisualDiff dataclass."""

    def test_summary_pass(self):
        diff = VisualDiff(name="home", baseline_path="/a", current_path="/b", diff_percentage=0.5, passed=True)
        summary = diff.summary()
        assert "PASS" in summary
        assert "0.50%" in summary

    def test_summary_fail(self):
        diff = VisualDiff(name="home", baseline_path="/a", current_path="/b", diff_percentage=15.0, passed=False)
        summary = diff.summary()
        assert "FAIL" in summary


class TestCapture:
    """Test baseline capture."""

    def test_capture_saves_baseline(self, tmp_path):
        tester = VisualRegressionTester(str(tmp_path))
        with patch.object(tester, "_fetch_page", return_value="<html><body>Hello</body></html>"):
            path = tester.capture("http://localhost:3000", name="home")
        assert os.path.isfile(path)
        assert "home.baseline.html" in path
        content = Path(path).read_text()
        assert "Hello" in content

    def test_capture_auto_name(self, tmp_path):
        tester = VisualRegressionTester(str(tmp_path))
        with patch.object(tester, "_fetch_page", return_value="<html></html>"):
            path = tester.capture("http://localhost:3000/dashboard")
        assert "localhost" in os.path.basename(path)

    def test_capture_saves_metadata(self, tmp_path):
        tester = VisualRegressionTester(str(tmp_path))
        with patch.object(tester, "_fetch_page", return_value="<html></html>"):
            tester.capture("http://localhost:3000", name="test")
        meta_path = os.path.join(tester.baselines_dir, "test.meta")
        assert os.path.isfile(meta_path)
        meta = Path(meta_path).read_text()
        assert "url=" in meta


class TestCompare:
    """Test comparison against baseline."""

    def test_compare_identical(self, tmp_path):
        tester = VisualRegressionTester(str(tmp_path))
        html = "<html><body>Same</body></html>"
        with patch.object(tester, "_fetch_page", return_value=html):
            tester.capture("http://localhost:3000", name="same")
            diff = tester.compare("http://localhost:3000", name="same")
        assert diff.passed
        assert diff.diff_percentage == 0.0

    def test_compare_different(self, tmp_path):
        tester = VisualRegressionTester(str(tmp_path))
        with patch.object(tester, "_fetch_page", side_effect=["<html>A</html>", "<html>B</html>"]):
            tester.capture("http://localhost:3000", name="diff")
        with patch.object(tester, "_fetch_page", return_value="<html>COMPLETELY DIFFERENT CONTENT HERE</html>"):
            diff = tester.compare("http://localhost:3000", name="diff")
        assert diff.diff_percentage > 0

    def test_compare_no_baseline(self, tmp_path):
        tester = VisualRegressionTester(str(tmp_path))
        with patch.object(tester, "_fetch_page", return_value="<html></html>"):
            diff = tester.compare("http://localhost:3000", name="missing")
        assert not diff.passed
        assert diff.diff_percentage == 100.0


class TestPixelDiff:
    """Test byte-level diff calculation."""

    def test_identical_files(self, tmp_path):
        a = tmp_path / "a.html"
        b = tmp_path / "b.html"
        a.write_text("same content")
        b.write_text("same content")
        tester = VisualRegressionTester(str(tmp_path))
        assert tester._pixel_diff(str(a), str(b)) == 0.0

    def test_different_files(self, tmp_path):
        a = tmp_path / "a.html"
        b = tmp_path / "b.html"
        a.write_text("aaaa")
        b.write_text("bbbb")
        tester = VisualRegressionTester(str(tmp_path))
        assert tester._pixel_diff(str(a), str(b)) > 0

    def test_missing_file(self, tmp_path):
        a = tmp_path / "a.html"
        a.write_text("content")
        tester = VisualRegressionTester(str(tmp_path))
        assert tester._pixel_diff(str(a), "/nonexistent") == 100.0


class TestListAndDelete:
    """Test baseline management."""

    def test_list_baselines(self, tmp_path):
        tester = VisualRegressionTester(str(tmp_path))
        with patch.object(tester, "_fetch_page", return_value="<html></html>"):
            tester.capture("http://localhost:3000", name="page1")
            tester.capture("http://localhost:3000", name="page2")
        baselines = tester.list_baselines()
        names = [b["name"] for b in baselines]
        assert "page1" in names
        assert "page2" in names

    def test_delete_baseline(self, tmp_path):
        tester = VisualRegressionTester(str(tmp_path))
        with patch.object(tester, "_fetch_page", return_value="<html></html>"):
            tester.capture("http://localhost:3000", name="todelete")
        assert tester.delete_baseline("todelete")
        assert not tester.delete_baseline("nonexistent")
        assert len(tester.list_baselines()) == 0
