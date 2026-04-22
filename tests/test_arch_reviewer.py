"""Tests for the architecture reviewer module."""

from __future__ import annotations

import os
import pytest

from code_agents.reviews.arch_reviewer import (
    ArchReviewer, ArchReviewResult, ArchFinding, review_architecture,
)


class TestArchReviewer:
    """Test ArchReviewer methods."""

    def test_init(self, tmp_path):
        reviewer = ArchReviewer(cwd=str(tmp_path))
        assert reviewer.cwd == str(tmp_path)

    def test_review_empty_dir(self, tmp_path):
        reviewer = ArchReviewer(cwd=str(tmp_path))
        result = reviewer.review()
        assert isinstance(result, ArchReviewResult)
        assert result.files_analyzed == 0

    def test_review_detects_long_file(self, tmp_path):
        code = "x = 1\n" * 600
        (tmp_path / "long_module.py").write_text(code)
        reviewer = ArchReviewer(cwd=str(tmp_path))
        result = reviewer.review()
        sep_findings = [f for f in result.findings if f.category == "separation"]
        assert any("lines" in f.message for f in sep_findings)

    def test_review_detects_heavy_imports(self, tmp_path):
        code = "import torch\nimport pandas\n\ndef train():\n    pass\n"
        (tmp_path / "ml_module.py").write_text(code)
        reviewer = ArchReviewer(cwd=str(tmp_path))
        result = reviewer.review()
        lazy_findings = [f for f in result.findings if f.category == "lazy_loading"]
        assert len(lazy_findings) >= 1

    def test_review_detects_global_mutable(self, tmp_path):
        code = "registry = {}\n\ndef register(name, val):\n    registry[name] = val\n"
        (tmp_path / "globals.py").write_text(code)
        reviewer = ArchReviewer(cwd=str(tmp_path))
        result = reviewer.review()
        di_findings = [f for f in result.findings if f.category == "di"]
        assert len(di_findings) >= 1

    def test_coupling_score(self, tmp_path):
        (tmp_path / "a.py").write_text("def func_a():\n    pass\n")
        (tmp_path / "b.py").write_text("from a import func_a\ndef func_b():\n    func_a()\n")
        reviewer = ArchReviewer(cwd=str(tmp_path), package_name="a")
        result = reviewer.review()
        assert isinstance(result.coupling_score, float)

    def test_convenience_function(self, tmp_path):
        (tmp_path / "simple.py").write_text("def hello():\n    return 1\n")
        result = review_architecture(cwd=str(tmp_path))
        assert isinstance(result, dict)
        assert "coupling_score" in result
        assert "summary" in result
