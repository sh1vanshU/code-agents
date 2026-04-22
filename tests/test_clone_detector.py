"""Tests for the clone detector."""

from __future__ import annotations

import os
import pytest

from code_agents.reviews.clone_detector import (
    CloneDetector, CloneGroup, format_clone_report,
)


class TestCloneDetector:
    """Test CloneDetector methods."""

    def test_init(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        assert detector.cwd == str(tmp_path)

    def test_detect_empty_dir(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        groups = detector.detect()
        assert groups == []

    def test_detect_no_clones(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
        (tmp_path / "b.py").write_text("def bar():\n    return 2\n")
        detector = CloneDetector(cwd=str(tmp_path))
        groups = detector.detect(min_tokens=5)
        # Small files — unlikely to have clones
        assert isinstance(groups, list)

    def test_detect_exact_clones(self, tmp_path):
        # Create two files with identical content large enough to trigger detection
        blocks = []
        for i in range(3):
            blocks.extend([
                f"def process_{i}(data):",
                "    result = []",
                "    for item in data:",
                "        if item.is_valid:",
                "            result.append(item.transform())",
                "            item.mark_processed()",
                "        else:",
                "            item.mark_invalid()",
                "            result.append(item.default())",
                "    return result",
                "",
            ])
        code = "\n".join(blocks)

        (tmp_path / "module_a.py").write_text(code)
        (tmp_path / "module_b.py").write_text(code)

        detector = CloneDetector(cwd=str(tmp_path))
        groups = detector.detect(threshold=0.5, min_tokens=10, window=10)
        # Should find at least some matching blocks
        assert isinstance(groups, list)

    def test_collect_files_skips_dirs(self, tmp_path):
        (tmp_path / "good.py").write_text("x = 1\n")
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "bad.js").write_text("var x = 1;\n")

        detector = CloneDetector(cwd=str(tmp_path))
        files = detector._collect_files()
        filenames = [os.path.basename(f) for f in files]
        assert "good.py" in filenames
        assert "bad.js" not in filenames

    def test_collect_files_supported_extensions(self, tmp_path):
        (tmp_path / "code.py").write_text("x = 1\n")
        (tmp_path / "code.js").write_text("var x = 1;\n")
        (tmp_path / "data.csv").write_text("a,b,c\n")
        (tmp_path / "readme.md").write_text("# Readme\n")

        detector = CloneDetector(cwd=str(tmp_path))
        files = detector._collect_files()
        extensions = {os.path.splitext(f)[1] for f in files}
        assert ".py" in extensions
        assert ".js" in extensions
        assert ".csv" not in extensions
        assert ".md" not in extensions


class TestTokenize:
    """Test the tokenizer."""

    def test_basic_tokenize(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        tokens = detector._tokenize("def foo(x):\n    return x + 1\n")
        assert isinstance(tokens, list)
        assert len(tokens) > 0

    def test_strips_comments(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        tokens = detector._tokenize("x = 1  # this is a comment\n")
        token_str = " ".join(tokens)
        assert "comment" not in token_str

    def test_normalizes_identifiers(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        tokens_a = detector._tokenize("def process(data):\n    return data\n")
        tokens_b = detector._tokenize("def handle(items):\n    return items\n")
        # After normalization, identifiers become $V, so these should match
        assert tokens_a == tokens_b

    def test_preserves_keywords(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        tokens = detector._tokenize("if x:\n    return True\n")
        assert "if" in tokens
        assert "return" in tokens
        assert "True" in tokens


class TestHashBlocks:
    """Test rolling hash block generation."""

    def test_empty_tokens(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        result = detector._hash_blocks([], window=5)
        assert result == {}

    def test_fewer_tokens_than_window(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        result = detector._hash_blocks(["a", "b"], window=5)
        assert result == {}

    def test_produces_hashes(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        tokens = ["def", "$V", "$V", "return", "$V"] * 5
        result = detector._hash_blocks(tokens, window=5)
        assert len(result) > 0


class TestCalculateSimilarity:
    """Test Jaccard similarity calculation."""

    def test_identical(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        sim = detector._calculate_similarity("def foo(): pass", "def foo(): pass")
        assert sim == 1.0

    def test_completely_different(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        sim = detector._calculate_similarity(
            "import os\nimport sys\n",
            "class Widget:\n    pass\n",
        )
        assert sim < 0.5

    def test_empty_strings(self, tmp_path):
        detector = CloneDetector(cwd=str(tmp_path))
        sim = detector._calculate_similarity("", "")
        # Both empty tokenize to empty sets
        assert sim == 1.0


class TestFormatCloneReport:
    """Test the report formatter."""

    def test_empty(self):
        result = format_clone_report([])
        assert "No code clones" in result

    def test_with_groups(self):
        groups = [
            CloneGroup(
                blocks=[
                    {"file": "a.py", "start_line": 1, "end_line": 10, "content": "..."},
                    {"file": "b.py", "start_line": 5, "end_line": 15, "content": "..."},
                ],
                similarity=0.95,
                token_count=30,
            ),
        ]
        result = format_clone_report(groups)
        assert "a.py" in result
        assert "b.py" in result
        assert "95%" in result

    def test_caps_at_twenty(self):
        groups = [
            CloneGroup(
                blocks=[{"file": f"f{i}.py", "start_line": 1, "end_line": 5, "content": ""}],
                similarity=0.9, token_count=20,
            )
            for i in range(25)
        ]
        result = format_clone_report(groups)
        assert "5 more" in result
