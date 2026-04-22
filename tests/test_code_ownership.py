"""Tests for the code ownership mapper."""

from __future__ import annotations

import pytest
from collections import Counter
from unittest.mock import patch, MagicMock

from code_agents.knowledge.code_ownership import CodeOwnershipMapper, OwnershipInfo


class TestOwnershipInfo:
    def test_basic_creation(self):
        info = OwnershipInfo(
            path="src/",
            primary_owner="Alice",
            contributors=["Alice", "Bob"],
            bus_factor=2,
        )
        assert info.path == "src/"
        assert info.primary_owner == "Alice"
        assert info.bus_factor == 2

    def test_default_values(self):
        info = OwnershipInfo(path=".", primary_owner="Alice")
        assert info.contributors == []
        assert info.bus_factor == 0


class TestStatsToOwnership:
    def test_single_author(self):
        stats = Counter({"Alice": 100})
        info = CodeOwnershipMapper._stats_to_ownership("src/", stats)
        assert info.primary_owner == "Alice"
        assert info.bus_factor == 1
        assert "Alice" in info.contributors

    def test_multiple_authors(self):
        stats = Counter({"Alice": 60, "Bob": 30, "Charlie": 10})
        info = CodeOwnershipMapper._stats_to_ownership("src/", stats)
        assert info.primary_owner == "Alice"
        assert info.bus_factor >= 1
        assert "Alice" in info.contributors
        assert "Bob" in info.contributors

    def test_empty_stats(self):
        stats = Counter()
        info = CodeOwnershipMapper._stats_to_ownership("src/", stats)
        assert info.primary_owner == ""
        assert info.bus_factor == 0

    def test_equal_contributors(self):
        stats = Counter({"Alice": 50, "Bob": 50})
        info = CodeOwnershipMapper._stats_to_ownership("src/", stats)
        assert info.bus_factor == 1  # one person gets to 50%
        assert len(info.contributors) == 2

    def test_small_contributor_excluded(self):
        # Charlie has less than 5% so should be excluded from contributors
        stats = Counter({"Alice": 90, "Bob": 8, "Charlie": 2})
        info = CodeOwnershipMapper._stats_to_ownership("src/", stats)
        assert "Charlie" not in info.contributors

    def test_bus_factor_three(self):
        stats = Counter({"Alice": 35, "Bob": 33, "Charlie": 32})
        info = CodeOwnershipMapper._stats_to_ownership("src/", stats)
        assert info.bus_factor == 2  # Alice + Bob >= 50%


class TestFormatOwner:
    def test_simple_name(self):
        assert CodeOwnershipMapper._format_owner("Alice Smith") == "@alice-smith"

    def test_special_chars(self):
        assert CodeOwnershipMapper._format_owner("Alice O'Brien") == "@alice-obrien"

    def test_empty_name(self):
        assert CodeOwnershipMapper._format_owner("") == "@unknown"


class TestAnalyze:
    @patch.object(CodeOwnershipMapper, "_get_tracked_files")
    @patch.object(CodeOwnershipMapper, "_git_blame_stats")
    def test_analyze_groups_by_directory(self, mock_blame, mock_files):
        mock_files.return_value = ["src/main.py", "src/utils.py", "tests/test_main.py"]
        mock_blame.side_effect = lambda path: {
            "src/main.py": {"Alice": 50, "Bob": 20},
            "src/utils.py": {"Alice": 30},
            "tests/test_main.py": {"Bob": 40},
        }.get(path, {})

        mapper = CodeOwnershipMapper(cwd="/fake")
        results = mapper.analyze()

        paths = [r.path for r in results]
        assert "src" in paths
        assert "tests" in paths

    @patch.object(CodeOwnershipMapper, "_get_tracked_files")
    def test_analyze_empty_repo(self, mock_files):
        mock_files.return_value = []
        mapper = CodeOwnershipMapper(cwd="/fake")
        results = mapper.analyze()
        assert results == []

    @patch.object(CodeOwnershipMapper, "_get_tracked_files")
    @patch.object(CodeOwnershipMapper, "_git_blame_stats")
    def test_analyze_skips_lock_files(self, mock_blame, mock_files):
        mock_files.return_value = ["package-lock.json", "src/main.py"]
        mock_blame.side_effect = lambda path: {"Alice": 10} if path == "src/main.py" else {}
        mapper = CodeOwnershipMapper(cwd="/fake")
        results = mapper.analyze()
        paths = [r.path for r in results]
        assert "src" in paths


class TestGenerateCodeowners:
    @patch.object(CodeOwnershipMapper, "analyze")
    def test_generate_basic(self, mock_analyze):
        mock_analyze.return_value = [
            OwnershipInfo(path="src", primary_owner="Alice", contributors=["Alice"], bus_factor=1),
            OwnershipInfo(path="tests", primary_owner="Bob", contributors=["Bob", "Alice"], bus_factor=2),
        ]
        mapper = CodeOwnershipMapper(cwd="/fake")
        content = mapper.generate_codeowners()
        assert "CODEOWNERS" in content
        assert "@alice" in content
        assert "@bob" in content
        assert "bus_factor=" in content

    @patch.object(CodeOwnershipMapper, "analyze")
    def test_generate_empty(self, mock_analyze):
        mock_analyze.return_value = []
        mapper = CodeOwnershipMapper(cwd="/fake")
        content = mapper.generate_codeowners()
        assert "CODEOWNERS" in content


class TestFindKnowledgeSilos:
    @patch.object(CodeOwnershipMapper, "analyze")
    def test_finds_silos(self, mock_analyze):
        mock_analyze.return_value = [
            OwnershipInfo(path="src", primary_owner="Alice", bus_factor=1),
            OwnershipInfo(path="tests", primary_owner="Bob", bus_factor=2),
        ]
        mapper = CodeOwnershipMapper(cwd="/fake")
        silos = mapper._find_knowledge_silos()
        assert silos == ["src"]

    @patch.object(CodeOwnershipMapper, "analyze")
    def test_no_silos(self, mock_analyze):
        mock_analyze.return_value = [
            OwnershipInfo(path="src", primary_owner="Alice", bus_factor=2),
        ]
        mapper = CodeOwnershipMapper(cwd="/fake")
        silos = mapper._find_knowledge_silos()
        assert silos == []
