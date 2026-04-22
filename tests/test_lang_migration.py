"""Tests for the multi-language migration system."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from code_agents.knowledge.lang_migration import (
    LanguageMigrator,
    MigrationResult,
    _to_class_name,
    format_migration_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_source_tree(tmp: Path) -> Path:
    """Create a minimal Python source tree for testing."""
    src = tmp / "src"
    src.mkdir()
    (src / "utils.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    (src / "models.py").write_text(
        "class User:\n    def __init__(self, name):\n        self.name = name\n",
        encoding="utf-8",
    )
    return src


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestToClassName:
    def test_simple(self):
        assert _to_class_name("utils") == "Utils"

    def test_underscored(self):
        assert _to_class_name("my_module") == "MyModule"

    def test_hyphenated(self):
        assert _to_class_name("some-file") == "SomeFile"

    def test_empty(self):
        assert _to_class_name("") == ""


class TestMigrationResult:
    def test_total_files(self):
        r = MigrationResult(
            source_dir="/a",
            target_dir="/b",
            target_lang="go",
            translated_files=["f1", "f2"],
            test_files=["t1"],
            scaffold_files=["s1"],
        )
        assert r.total_files == 4

    def test_empty(self):
        r = MigrationResult(source_dir="/a", target_dir="/b", target_lang="go")
        assert r.total_files == 0


class TestLanguageMigrator:
    def test_missing_source_dir(self, tmp_path):
        m = LanguageMigrator(cwd=str(tmp_path))
        result = m.migrate_module("nonexistent", "go")
        assert len(result.errors) >= 1
        assert "not found" in result.errors[0].lower()

    def test_unsupported_language(self, tmp_path):
        src = _create_source_tree(tmp_path)
        m = LanguageMigrator(cwd=str(tmp_path))
        result = m.migrate_module("src", "cobol")
        assert len(result.errors) >= 1
        assert "unsupported" in result.errors[0].lower()

    def test_empty_directory(self, tmp_path):
        (tmp_path / "empty").mkdir()
        m = LanguageMigrator(cwd=str(tmp_path))
        result = m.migrate_module("empty", "go")
        assert len(result.warnings) >= 1

    def test_migrate_to_go(self, tmp_path):
        _create_source_tree(tmp_path)
        out = tmp_path / "output"
        m = LanguageMigrator(cwd=str(tmp_path))
        result = m.migrate_module("src", "go", output_dir=str(out))

        assert result.target_lang == "go"
        assert len(result.translated_files) >= 1
        assert len(result.test_files) >= 1
        # go.mod should be scaffolded
        assert any("go.mod" in f for f in result.scaffold_files)

    def test_migrate_to_javascript(self, tmp_path):
        _create_source_tree(tmp_path)
        out = tmp_path / "js_output"
        m = LanguageMigrator(cwd=str(tmp_path))
        result = m.migrate_module("src", "javascript", output_dir=str(out))

        assert result.target_lang == "javascript"
        assert any("package.json" in f for f in result.scaffold_files)

    def test_lang_alias(self, tmp_path):
        _create_source_tree(tmp_path)
        out = tmp_path / "ts_out"
        m = LanguageMigrator(cwd=str(tmp_path))
        result = m.migrate_module("src", "ts", output_dir=str(out))
        assert result.target_lang == "typescript"


class TestFormatMigrationResult:
    def test_format_success(self):
        r = MigrationResult(
            source_dir="/src",
            target_dir="/out",
            target_lang="go",
            translated_files=["/out/utils.go"],
            test_files=["/out/utils_test.go"],
            scaffold_files=["/out/go.mod"],
        )
        output = format_migration_result(r)
        assert "go" in output
        assert "utils.go" in output
        assert "3 files" in output

    def test_format_errors(self):
        r = MigrationResult(
            source_dir="/src",
            target_dir="/out",
            target_lang="go",
            errors=["Something failed"],
        )
        output = format_migration_result(r)
        assert "Something failed" in output
