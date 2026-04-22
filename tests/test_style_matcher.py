"""Tests for style_matcher.py — code style detection and prompt generation."""

from __future__ import annotations

import os
import textwrap

import pytest

from code_agents.reviews.style_matcher import (
    StyleMatcher,
    StyleProfile,
    _detect_docstring_style,
    _detect_indent,
    _detect_max_line_length,
    _detect_naming,
    _detect_quotes,
    _detect_semicolons,
    _detect_trailing_comma,
    _detect_type_hints,
    _detect_import_style,
    _find_source_files,
    _cache,
    clear_cache,
    get_style_prompt,
)


# ── Indent detection ────────────────────────────────────────────────────────


class TestDetectIndent:
    def test_spaces_4(self):
        lines = [
            "def foo():",
            "    return 1",
            "    if True:",
            "        pass",
        ]
        style, size = _detect_indent(lines)
        assert style == "spaces"
        assert size == 4

    def test_spaces_2(self):
        lines = [
            "function foo() {",
            "  const x = 1;",
            "  if (true) {",
            "    return x;",
            "  }",
            "}",
        ]
        style, size = _detect_indent(lines)
        assert style == "spaces"
        assert size == 2

    def test_tabs(self):
        lines = [
            "func main() {",
            "\tfmt.Println()",
            "\tif true {",
            "\t\treturn",
            "\t}",
            "}",
        ]
        style, size = _detect_indent(lines)
        assert style == "tabs"

    def test_empty_lines_ignored(self):
        lines = ["", "  ", "def foo():", "    pass"]
        style, size = _detect_indent(lines)
        assert style == "spaces"
        assert size == 4


# ── Quote detection ─────────────────────────────────────────────────────────


class TestDetectQuotes:
    def test_single_quotes_python(self):
        content = "x = 'hello'\ny = 'world'\nz = 'test'"
        assert _detect_quotes(content, "python") == "single"

    def test_double_quotes_python(self):
        content = 'x = "hello"\ny = "world"\nz = "test"'
        assert _detect_quotes(content, "python") == "double"

    def test_double_quotes_js(self):
        content = 'const x = "hello";\nconst y = "world";'
        assert _detect_quotes(content, "javascript") == "double"


# ── Naming convention detection ─────────────────────────────────────────────


class TestDetectNaming:
    def test_snake_case_python(self):
        content = "def get_user():\n    pass\ndef save_data():\n    pass"
        assert _detect_naming(content, "python") == "snake_case"

    def test_camel_case_js(self):
        content = "function getUserData() {}\nconst saveItem = () => {}"
        assert _detect_naming(content, "javascript") == "camelCase"

    def test_pascal_case_go(self):
        content = "func GetUser() {}\nfunc SaveData() {}\nfunc HandleRequest() {}"
        assert _detect_naming(content, "go") == "PascalCase"

    def test_no_funcs_defaults_snake(self):
        content = "x = 1\ny = 2"
        assert _detect_naming(content, "python") == "snake_case"


# ── Line length detection ──────────────────────────────────────────────────


class TestDetectMaxLineLength:
    def test_short_lines(self):
        lines = ["x = 1"] * 100
        assert _detect_max_line_length(lines) == 80

    def test_long_lines(self):
        lines = ["x" * 115] * 100
        assert _detect_max_line_length(lines) == 120

    def test_empty_lines(self):
        assert _detect_max_line_length([]) == 120


# ── Import style detection ──────────────────────────────────────────────────


class TestDetectImportStyle:
    def test_grouped_python(self):
        content = "from os import path\nfrom sys import argv\nfrom typing import List"
        assert _detect_import_style(content, "python") == "grouped"

    def test_individual_python(self):
        content = "import os\nimport sys\nimport json"
        assert _detect_import_style(content, "python") == "individual"

    def test_grouped_js(self):
        content = "import { useState, useEffect } from 'react';\nimport { Router } from 'express';"
        assert _detect_import_style(content, "javascript") == "grouped"


# ── Trailing comma detection ───────────────────────────────────────────────


class TestDetectTrailingComma:
    def test_trailing_commas_present(self):
        content = "[\n  1,\n  2,\n  3,\n]"
        assert _detect_trailing_comma(content) is True

    def test_no_trailing_commas(self):
        content = "[\n  1,\n  2,\n  3\n]"
        assert _detect_trailing_comma(content) is False


# ── Semicolons detection ───────────────────────────────────────────────────


class TestDetectSemicolons:
    def test_with_semicolons(self):
        content = "const x = 1;\nconst y = 2;\nreturn x + y;"
        assert _detect_semicolons(content) is True

    def test_without_semicolons(self):
        content = "const x = 1\nconst y = 2\nreturn x + y"
        assert _detect_semicolons(content) is False


# ── Type hints detection ───────────────────────────────────────────────────


class TestDetectTypeHints:
    def test_with_type_hints(self):
        content = "def foo(x: int, y: str) -> bool:\n    pass\ndef bar(z: float) -> None:\n    pass"
        assert _detect_type_hints(content) is True

    def test_without_type_hints(self):
        content = "def foo(x, y):\n    pass\ndef bar(z):\n    pass"
        assert _detect_type_hints(content) is False


# ── Docstring style detection ──────────────────────────────────────────────


class TestDetectDocstringStyle:
    def test_google_style(self):
        content = '"""Get user.\n    Args:\n        name: The name.\n    """'
        assert _detect_docstring_style(content, "python") == "google"

    def test_numpy_style(self):
        content = '"""Get user.\n    Parameters\n    ----------\n    name : str\n    """'
        assert _detect_docstring_style(content, "python") == "numpy"

    def test_sphinx_style(self):
        content = '"""Get user.\n    :param name: The name.\n    """'
        assert _detect_docstring_style(content, "python") == "sphinx"

    def test_javadoc(self):
        content = "/**\n * Get user.\n * @param name the name\n */"
        assert _detect_docstring_style(content, "java") == "javadoc"


# ── File discovery ──────────────────────────────────────────────────────────


class TestFindSourceFiles:
    def test_finds_python_files(self, tmp_path):
        (tmp_path / "foo.py").write_text("x = 1")
        (tmp_path / "bar.py").write_text("y = 2")
        files = _find_source_files(str(tmp_path))
        assert len(files) == 2

    def test_skips_venv(self, tmp_path):
        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "lib.py").write_text("x = 1")
        (tmp_path / "main.py").write_text("y = 2")
        files = _find_source_files(str(tmp_path))
        assert len(files) == 1
        assert "main.py" in files[0]

    def test_empty_dir(self, tmp_path):
        files = _find_source_files(str(tmp_path))
        assert files == []

    def test_limit(self, tmp_path):
        for i in range(30):
            (tmp_path / f"f{i}.py").write_text(f"x = {i}")
        files = _find_source_files(str(tmp_path), limit=5)
        assert len(files) == 5


# ── StyleMatcher integration ───────────────────────────────────────────────


class TestStyleMatcher:
    def setup_method(self):
        clear_cache()

    def test_analyze_python_repo(self, tmp_path):
        code = textwrap.dedent("""\
            from os import path
            from sys import argv


            def get_user_name(user_id: int) -> str:
                \"\"\"Get user name.

                Args:
                    user_id: The user ID.
                \"\"\"
                return "hello"


            def save_data(data: dict) -> None:
                x = "world"
                return None
        """)
        (tmp_path / "main.py").write_text(code)
        (tmp_path / "utils.py").write_text('def helper_func():\n    return "ok"\n')

        matcher = StyleMatcher(str(tmp_path))
        profile = matcher.analyze()

        assert profile.language == "python"
        assert profile.indent_style == "spaces"
        assert profile.indent_size == 4
        assert profile.quote_style == "double"
        assert profile.naming_convention == "snake_case"
        assert profile.docstring_style == "google"

    def test_analyze_js_repo(self, tmp_path):
        code = textwrap.dedent("""\
            const getUserData = () => {
              return 'hello';
            };

            function saveItem(item) {
              const result = 'world';
              return result;
            }
        """)
        (tmp_path / "app.js").write_text(code)

        matcher = StyleMatcher(str(tmp_path))
        profile = matcher.analyze()

        assert profile.language == "javascript"
        assert profile.indent_size == 2

    def test_caching(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1")
        matcher = StyleMatcher(str(tmp_path))
        p1 = matcher.analyze()
        p2 = matcher.analyze()
        assert p1 is p2  # same object from cache

    def test_clear_cache(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1")
        matcher = StyleMatcher(str(tmp_path))
        matcher.analyze()
        assert str(tmp_path) in _cache
        clear_cache(str(tmp_path))
        assert str(tmp_path) not in _cache

    def test_clear_all_cache(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1")
        StyleMatcher(str(tmp_path)).analyze()
        clear_cache()
        assert len(_cache) == 0

    def test_empty_repo(self, tmp_path):
        matcher = StyleMatcher(str(tmp_path))
        profile = matcher.analyze()
        assert profile.language == "unknown"


# ── Prompt generation ──────────────────────────────────────────────────────


class TestGenerateStylePrompt:
    def test_python_prompt(self):
        profile = StyleProfile(
            language="python",
            indent_style="spaces",
            indent_size=4,
            quote_style="double",
            naming_convention="snake_case",
            max_line_length=120,
            import_style="grouped",
            trailing_comma=False,
            type_hints=True,
            docstring_style="google",
        )
        prompt = StyleMatcher.generate_style_prompt(profile)
        assert "python" in prompt.lower()
        assert "4-spaces" in prompt
        assert "double quotes" in prompt
        assert "snake_case" in prompt
        assert "google docstrings" in prompt
        assert "type hints" in prompt
        # Must be concise
        assert len(prompt.split()) < 100

    def test_js_prompt_with_semicolons(self):
        profile = StyleProfile(
            language="javascript",
            indent_size=2,
            quote_style="single",
            naming_convention="camelCase",
            semicolons=True,
        )
        prompt = StyleMatcher.generate_style_prompt(profile)
        assert "semicolons" in prompt
        assert "camelCase" in prompt

    def test_js_prompt_no_semicolons(self):
        profile = StyleProfile(
            language="javascript",
            semicolons=False,
        )
        prompt = StyleMatcher.generate_style_prompt(profile)
        assert "no semicolons" in prompt


# ── Display format ──────────────────────────────────────────────────────────


class TestFormatDisplay:
    def test_display_python(self):
        profile = StyleProfile(language="python", type_hints=True)
        output = StyleMatcher.format_display(profile)
        assert "python" in output
        assert "Type hints" in output

    def test_display_js(self):
        profile = StyleProfile(language="javascript", semicolons=True)
        output = StyleMatcher.format_display(profile)
        assert "javascript" in output
        assert "Semicolons" in output


# ── Convenience function ───────────────────────────────────────────────────


class TestGetStylePrompt:
    def setup_method(self):
        clear_cache()

    def test_returns_prompt_for_repo(self, tmp_path):
        (tmp_path / "main.py").write_text("def foo():\n    pass\n")
        prompt = get_style_prompt(str(tmp_path))
        assert "python" in prompt.lower()

    def test_returns_empty_for_empty_repo(self, tmp_path):
        prompt = get_style_prompt(str(tmp_path))
        assert prompt == ""
