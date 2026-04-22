"""Tests for code_agents.parsers — language detection, file parsing, dataclasses."""

import os
import tempfile
import unittest

from code_agents.parsers import ModuleInfo, SymbolInfo, detect_language, parse_file


class TestDetectLanguage(unittest.TestCase):
    """Test detect_language() for various file extensions."""

    def test_python(self):
        self.assertEqual(detect_language("app.py"), "python")

    def test_javascript(self):
        self.assertEqual(detect_language("index.js"), "javascript")

    def test_typescript(self):
        self.assertEqual(detect_language("main.ts"), "typescript")

    def test_java(self):
        self.assertEqual(detect_language("Main.java"), "java")

    def test_go(self):
        self.assertEqual(detect_language("main.go"), "go")

    def test_unknown_extension(self):
        self.assertEqual(detect_language("data.unknown"), "unknown")

    def test_no_extension(self):
        self.assertEqual(detect_language("Makefile"), "unknown")

    def test_tsx(self):
        self.assertEqual(detect_language("Component.tsx"), "typescript")

    def test_jsx(self):
        self.assertEqual(detect_language("Component.jsx"), "javascript")

    def test_case_insensitive_via_path(self):
        # detect_language lowercases the suffix
        self.assertEqual(detect_language("script.PY"), "python")


class TestParseFilePython(unittest.TestCase):
    """Test parse_file() with a Python source file."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        )
        self.tmp.write(
            '''import os
from pathlib import Path


class MyClass:
    """A sample class."""

    def method_one(self, x: int) -> str:
        """Do something."""
        return str(x)


def top_level_func(a, b):
    """Add two numbers."""
    return a + b
'''
        )
        self.tmp.flush()
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_returns_module_info(self):
        result = parse_file(self.tmp.name)
        self.assertIsInstance(result, ModuleInfo)
        self.assertEqual(result.language, "python")

    def test_imports_extracted(self):
        result = parse_file(self.tmp.name)
        self.assertIn("os", result.imports)
        self.assertIn("pathlib", result.imports)

    def test_class_extracted(self):
        result = parse_file(self.tmp.name)
        class_syms = [s for s in result.symbols if s.kind == "class"]
        self.assertEqual(len(class_syms), 1)
        self.assertEqual(class_syms[0].name, "MyClass")
        self.assertIn("class MyClass", class_syms[0].signature)

    def test_method_extracted(self):
        result = parse_file(self.tmp.name)
        method_syms = [s for s in result.symbols if s.kind == "method"]
        self.assertEqual(len(method_syms), 1)
        self.assertEqual(method_syms[0].name, "MyClass.method_one")

    def test_function_extracted(self):
        result = parse_file(self.tmp.name)
        func_syms = [s for s in result.symbols if s.kind == "function"]
        self.assertEqual(len(func_syms), 1)
        self.assertEqual(func_syms[0].name, "top_level_func")
        self.assertIn("def top_level_func", func_syms[0].signature)

    def test_docstrings_extracted(self):
        result = parse_file(self.tmp.name)
        class_sym = [s for s in result.symbols if s.kind == "class"][0]
        self.assertEqual(class_sym.docstring, "A sample class.")

    def test_symbol_line_numbers(self):
        result = parse_file(self.tmp.name)
        func_sym = [s for s in result.symbols if s.kind == "function"][0]
        self.assertGreater(func_sym.line_number, 0)


class TestParseFileJavaScript(unittest.TestCase):
    """Test parse_file() with a JavaScript source file."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            suffix=".js", mode="w", delete=False, encoding="utf-8"
        )
        self.tmp.write(
            '''import express from 'express';
const axios = require('axios');

function handleRequest(req, res) {
    return res.send('ok');
}

class Router {
    constructor() {
        this.routes = [];
    }

    addRoute(path) {
        this.routes.push(path);
    }
}

export default Router;
'''
        )
        self.tmp.flush()
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_returns_module_info(self):
        result = parse_file(self.tmp.name)
        self.assertIsInstance(result, ModuleInfo)
        self.assertEqual(result.language, "javascript")

    def test_imports_extracted(self):
        result = parse_file(self.tmp.name)
        self.assertIn("express", result.imports)
        self.assertIn("axios", result.imports)

    def test_function_extracted(self):
        result = parse_file(self.tmp.name)
        func_syms = [s for s in result.symbols if s.kind == "function"]
        names = [s.name for s in func_syms]
        self.assertIn("handleRequest", names)

    def test_class_extracted(self):
        result = parse_file(self.tmp.name)
        class_syms = [s for s in result.symbols if s.kind == "class"]
        self.assertEqual(len(class_syms), 1)
        self.assertEqual(class_syms[0].name, "Router")

    def test_methods_extracted(self):
        result = parse_file(self.tmp.name)
        method_syms = [s for s in result.symbols if s.kind == "method"]
        method_names = [s.name for s in method_syms]
        self.assertIn("Router.constructor", method_names)
        self.assertIn("Router.addRoute", method_names)

    def test_exports_extracted(self):
        result = parse_file(self.tmp.name)
        self.assertIn("default", result.exports)


class TestParseFileUnknownExtension(unittest.TestCase):
    """Test parse_file() with an unrecognized file extension."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            suffix=".xyz", mode="w", delete=False, encoding="utf-8"
        )
        self.tmp.write("some content\ndef foo():\n  pass\n")
        self.tmp.flush()
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_returns_module_info_with_unknown_language(self):
        result = parse_file(self.tmp.name)
        self.assertIsInstance(result, ModuleInfo)
        self.assertEqual(result.language, "unknown")

    def test_symbols_may_be_empty_or_generic(self):
        result = parse_file(self.tmp.name)
        # Generic parser may or may not extract symbols; it should not crash
        self.assertIsInstance(result.symbols, list)


class TestParseFileNonexistent(unittest.TestCase):
    """Test parse_file() with a file that does not exist."""

    def test_returns_empty_module_info(self):
        result = parse_file("/tmp/nonexistent_file_for_test_12345.py")
        self.assertIsInstance(result, ModuleInfo)
        self.assertEqual(result.language, "python")
        self.assertEqual(result.symbols, [])
        self.assertEqual(result.imports, [])


class TestDataclasses(unittest.TestCase):
    """Test SymbolInfo and ModuleInfo dataclass creation."""

    def test_symbol_info_creation(self):
        sym = SymbolInfo(
            name="my_func",
            kind="function",
            file_path="/tmp/test.py",
            line_number=10,
            signature="def my_func(x: int) -> str",
            docstring="Does stuff.",
        )
        self.assertEqual(sym.name, "my_func")
        self.assertEqual(sym.kind, "function")
        self.assertEqual(sym.line_number, 10)

    def test_symbol_info_defaults(self):
        sym = SymbolInfo(
            name="x", kind="variable", file_path="/tmp/t.py", line_number=1
        )
        self.assertEqual(sym.signature, "")
        self.assertEqual(sym.docstring, "")

    def test_module_info_creation(self):
        mod = ModuleInfo(file_path="/tmp/test.py", language="python")
        self.assertEqual(mod.file_path, "/tmp/test.py")
        self.assertEqual(mod.language, "python")
        self.assertEqual(mod.symbols, [])
        self.assertEqual(mod.imports, [])
        self.assertEqual(mod.exports, [])

    def test_module_info_with_symbols(self):
        sym = SymbolInfo(
            name="f", kind="function", file_path="/tmp/t.py", line_number=1
        )
        mod = ModuleInfo(
            file_path="/tmp/t.py",
            language="python",
            symbols=[sym],
            imports=["os"],
        )
        self.assertEqual(len(mod.symbols), 1)
        self.assertEqual(mod.imports, ["os"])


if __name__ == "__main__":
    unittest.main()
