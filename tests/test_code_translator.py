"""Tests for code_agents.code_translator — regex-based code translation."""

from __future__ import annotations

import os
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from code_agents.knowledge.code_translator import (
    CodeTranslator,
    TranslationResult,
    LANG_ALIASES,
    format_translation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def translator(tmp_path):
    return CodeTranslator(cwd=str(tmp_path))


@pytest.fixture
def py_file(tmp_path):
    src = tmp_path / "example.py"
    src.write_text(textwrap.dedent("""\
        # A simple example
        import os

        class Calculator:
            def __init__(self, value: int = 0):
                self.value = value

            def add(self, x: int) -> int:
                self.value = self.value + x
                return self.value

        def greet(name: str) -> None:
            print(f"Hello, {name}")

        flag = True
        empty = None
    """))
    return str(src)


@pytest.fixture
def js_file(tmp_path):
    src = tmp_path / "example.js"
    src.write_text(textwrap.dedent("""\
        // A simple example
        const greeting = "hello";

        function add(a, b) {
            return a + b;
        }

        const multiply = (x, y) => {
            return x * y;
        };

        console.log(null);
        let flag = true;
    """))
    return str(src)


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

class TestLanguageDetection:
    def test_detect_python(self, translator):
        assert translator._detect_language("foo.py") == "python"

    def test_detect_javascript(self, translator):
        assert translator._detect_language("bar.js") == "javascript"

    def test_detect_typescript(self, translator):
        assert translator._detect_language("baz.ts") == "typescript"

    def test_detect_java(self, translator):
        assert translator._detect_language("Main.java") == "java"

    def test_detect_go(self, translator):
        assert translator._detect_language("main.go") == "go"

    def test_detect_ruby(self, translator):
        assert translator._detect_language("app.rb") == "ruby"

    def test_detect_rust(self, translator):
        assert translator._detect_language("lib.rs") == "rust"

    def test_detect_unknown(self, translator):
        assert translator._detect_language("readme.md") == "unknown"

    def test_detect_jsx(self, translator):
        assert translator._detect_language("App.jsx") == "javascript"

    def test_detect_tsx(self, translator):
        assert translator._detect_language("App.tsx") == "typescript"


# ---------------------------------------------------------------------------
# LANG_ALIASES
# ---------------------------------------------------------------------------

class TestLangAliases:
    def test_py_alias(self):
        assert LANG_ALIASES["py"] == "python"

    def test_js_alias(self):
        assert LANG_ALIASES["js"] == "javascript"

    def test_ts_alias(self):
        assert LANG_ALIASES["ts"] == "typescript"

    def test_rb_alias(self):
        assert LANG_ALIASES["rb"] == "ruby"

    def test_rs_alias(self):
        assert LANG_ALIASES["rs"] == "rust"


# ---------------------------------------------------------------------------
# Target path generation
# ---------------------------------------------------------------------------

class TestTargetPath:
    def test_python_to_js(self, translator):
        result = translator._generate_target_path("src/utils.py", "javascript")
        assert result.endswith("utils.js")

    def test_js_to_python(self, translator):
        result = translator._generate_target_path("lib/helper.js", "python")
        assert result.endswith("helper.py")

    def test_py_to_java(self, translator):
        result = translator._generate_target_path("app.py", "java")
        assert result.endswith("app.java")

    def test_py_to_go(self, translator):
        result = translator._generate_target_path("app.py", "go")
        assert result.endswith("app.go")

    def test_unknown_lang_txt(self, translator):
        result = translator._generate_target_path("app.py", "haskell")
        assert result.endswith(".txt")


# ---------------------------------------------------------------------------
# Python -> JavaScript
# ---------------------------------------------------------------------------

class TestPythonToJavaScript:
    def test_translate_file(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert isinstance(result, TranslationResult)
        assert result.source_lang == "python"
        assert result.target_lang == "javascript"
        assert result.code  # non-empty

    def test_def_to_function(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert "function greet(" in result.code

    def test_self_to_this(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert "this.value" in result.code

    def test_print_to_console_log(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert "console.log" in result.code

    def test_none_to_null(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert "null" in result.code

    def test_true_to_true(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert "true" in result.code

    def test_comment_conversion(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert "//" in result.code

    def test_class_converted(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert "class Calculator" in result.code

    def test_type_hints_stripped(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        # "name: str" should not appear; just "name"
        assert ": str" not in result.code
        assert ": int" not in result.code


# ---------------------------------------------------------------------------
# Python -> Java
# ---------------------------------------------------------------------------

class TestPythonToJava:
    def test_translate_file(self, translator, py_file):
        result = translator.translate_file(py_file, "java")
        assert result.target_lang == "java"
        assert "public class" in result.code

    def test_print_to_sysout(self, translator, py_file):
        result = translator.translate_file(py_file, "java")
        assert "System.out.println" in result.code

    def test_self_to_this(self, translator, py_file):
        result = translator.translate_file(py_file, "java")
        assert "this.value" in result.code

    def test_none_to_null(self, translator, py_file):
        result = translator.translate_file(py_file, "java")
        assert "null" in result.code

    def test_comment_conversion(self, translator, py_file):
        result = translator.translate_file(py_file, "java")
        assert "//" in result.code


# ---------------------------------------------------------------------------
# Python -> Go
# ---------------------------------------------------------------------------

class TestPythonToGo:
    def test_translate_file(self, translator, py_file):
        result = translator.translate_file(py_file, "go")
        assert result.target_lang == "go"
        assert "package main" in result.code

    def test_struct_generated(self, translator, py_file):
        result = translator.translate_file(py_file, "go")
        assert "type Calculator struct" in result.code

    def test_func_keyword(self, translator, py_file):
        result = translator.translate_file(py_file, "go")
        assert "func " in result.code

    def test_fmt_println(self, translator, py_file):
        result = translator.translate_file(py_file, "go")
        assert "fmt.Println" in result.code

    def test_none_to_nil(self, translator, py_file):
        result = translator.translate_file(py_file, "go")
        assert "nil" in result.code

    def test_import_fmt(self, translator, py_file):
        result = translator.translate_file(py_file, "go")
        assert 'import "fmt"' in result.code


# ---------------------------------------------------------------------------
# JavaScript -> Python
# ---------------------------------------------------------------------------

class TestJavaScriptToPython:
    def test_translate_file(self, translator, js_file):
        result = translator.translate_file(js_file, "python")
        assert result.source_lang == "javascript"
        assert result.target_lang == "python"

    def test_function_to_def(self, translator, js_file):
        result = translator.translate_file(js_file, "python")
        assert "def add(" in result.code

    def test_console_log_to_print(self, translator, js_file):
        result = translator.translate_file(js_file, "python")
        assert "print(" in result.code

    def test_null_to_none(self, translator, js_file):
        result = translator.translate_file(js_file, "python")
        assert "None" in result.code

    def test_true_to_True(self, translator, js_file):
        result = translator.translate_file(js_file, "python")
        assert "True" in result.code

    def test_comment_conversion(self, translator, js_file):
        result = translator.translate_file(js_file, "python")
        assert "# " in result.code

    def test_const_to_variable(self, translator, js_file):
        result = translator.translate_file(js_file, "python")
        assert 'greeting = "hello"' in result.code


# ---------------------------------------------------------------------------
# JavaScript -> TypeScript
# ---------------------------------------------------------------------------

class TestJavaScriptToTypeScript:
    def test_translate_file(self, translator, js_file):
        result = translator.translate_file(js_file, "typescript")
        assert result.target_lang == "typescript"
        assert result.code

    def test_any_types_added(self, translator, js_file):
        result = translator.translate_file(js_file, "typescript")
        assert ": any" in result.code


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unknown_source_language(self, translator, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Hello")
        result = translator.translate_file(str(f), "python")
        assert result.source_lang == "unknown"
        assert result.warnings

    def test_same_language_warning(self, translator, py_file):
        result = translator.translate_file(py_file, "python")
        assert any("same" in w.lower() for w in result.warnings)

    def test_unsupported_pair_scaffold(self, translator, py_file):
        result = translator.translate_file(py_file, "ruby")
        assert "scaffold" in result.code.lower() or "Translated from" in result.code
        assert result.warnings

    def test_alias_resolution(self, translator, py_file):
        result = translator.translate_file(py_file, "js")
        assert result.target_lang == "javascript"

    def test_empty_file(self, translator, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        result = translator.translate_file(str(f), "javascript")
        assert result.source_lang == "python"

    def test_target_path_in_result(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert result.target_path.endswith(".js")


# ---------------------------------------------------------------------------
# Symbol preservation
# ---------------------------------------------------------------------------

class TestSymbolPreservation:
    def test_class_name_preserved_py_to_js(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert "Calculator" in result.code

    def test_function_name_preserved_py_to_js(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert "greet" in result.code

    def test_method_name_preserved_py_to_js(self, translator, py_file):
        result = translator.translate_file(py_file, "javascript")
        assert "add" in result.code

    def test_class_name_preserved_py_to_java(self, translator, py_file):
        result = translator.translate_file(py_file, "java")
        assert "Calculator" in result.code

    def test_class_name_preserved_py_to_go(self, translator, py_file):
        result = translator.translate_file(py_file, "go")
        assert "Calculator" in result.code

    def test_function_names_preserved_js_to_py(self, translator, js_file):
        result = translator.translate_file(js_file, "python")
        assert "add" in result.code


# ---------------------------------------------------------------------------
# format_translation
# ---------------------------------------------------------------------------

class TestFormatTranslation:
    def test_basic_format(self):
        result = TranslationResult(
            source_path="test.py",
            target_path="test.js",
            source_lang="python",
            target_lang="javascript",
            code="function hello() {\n  console.log('hi');\n}",
            warnings=["test warning"],
        )
        output = format_translation(result)
        assert "python -> javascript" in output
        assert "test.py" in output
        assert "test.js" in output
        assert "test warning" in output
        assert "translated code" in output

    def test_no_warnings(self):
        result = TranslationResult(
            source_path="a.py",
            target_path="a.js",
            source_lang="python",
            target_lang="javascript",
            code="// empty",
        )
        output = format_translation(result)
        assert "Warnings" not in output


# ---------------------------------------------------------------------------
# Type mapping helpers
# ---------------------------------------------------------------------------

class TestTypeHelpers:
    def test_py_type_to_java(self, translator):
        assert translator._py_type_to_java("str") == "String"
        assert translator._py_type_to_java("int") == "int"
        assert translator._py_type_to_java("float") == "double"
        assert translator._py_type_to_java("bool") == "boolean"
        assert translator._py_type_to_java("list") == "List<Object>"
        assert translator._py_type_to_java("dict") == "Map<String, Object>"
        assert translator._py_type_to_java("None") == "void"
        assert translator._py_type_to_java("SomeCustom") == "Object"

    def test_py_type_to_go(self, translator):
        assert translator._py_type_to_go("str") == "string"
        assert translator._py_type_to_go("int") == "int"
        assert translator._py_type_to_go("float") == "float64"
        assert translator._py_type_to_go("bool") == "bool"
        assert translator._py_type_to_go("list") == "[]interface{}"
        assert translator._py_type_to_go("dict") == "map[string]interface{}"

    def test_strip_py_type_hints(self, translator):
        assert translator._strip_py_type_hints("x: int, y: str") == "x, y"
        assert translator._strip_py_type_hints("name: str = 'test'") == "name='test'"
        assert translator._strip_py_type_hints("") == ""

    def test_strip_ts_types(self, translator):
        assert translator._strip_ts_types("a: number, b: string") == "a, b"
        assert translator._strip_ts_types("x") == "x"

    def test_add_any_types(self, translator):
        assert "any" in translator._add_any_types("a, b")
        assert translator._add_any_types("") == ""
        # Already typed params should pass through
        result = translator._add_any_types("x: number")
        assert "x: number" in result
