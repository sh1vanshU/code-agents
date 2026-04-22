"""Tests for the _ast_helpers shared utility."""

import textwrap

import pytest

from code_agents.analysis._ast_helpers import (
    parse_python_file, find_functions, find_classes,
    find_imports, find_calls, scan_python_files,
    FunctionInfo, ClassInfo, ImportInfo, CallInfo,
)


class TestParsePythonFile:
    """Test AST parsing."""

    def test_parse_valid_file(self, tmp_path):
        f = tmp_path / "valid.py"
        f.write_text("x = 1\n")
        tree = parse_python_file(str(f))
        assert tree is not None

    def test_parse_syntax_error(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def foo(\n")
        tree = parse_python_file(str(f))
        assert tree is None

    def test_parse_missing_file(self):
        tree = parse_python_file("/nonexistent/file.py")
        assert tree is None


class TestFindFunctions:
    """Test function extraction from AST."""

    def test_find_simple_function(self, tmp_path):
        source = textwrap.dedent('''\
            def add(a: int, b: int) -> int:
                """Add two numbers."""
                return a + b
        ''')
        f = tmp_path / "funcs.py"
        f.write_text(source)
        tree = parse_python_file(str(f))
        funcs = find_functions(tree, str(f))

        assert len(funcs) == 1
        assert funcs[0].name == "add"
        assert funcs[0].args == ["a", "b"]
        assert funcs[0].return_annotation == "int"
        assert funcs[0].docstring == "Add two numbers."
        assert funcs[0].is_async is False

    def test_find_async_function(self, tmp_path):
        source = "async def fetch(url): pass\n"
        f = tmp_path / "async_func.py"
        f.write_text(source)
        tree = parse_python_file(str(f))
        funcs = find_functions(tree, str(f))

        assert len(funcs) == 1
        assert funcs[0].is_async is True

    def test_complexity_estimate(self, tmp_path):
        source = textwrap.dedent('''\
            def complex_func(x):
                if x > 0:
                    for i in range(x):
                        if i % 2 == 0:
                            pass
                while x > 0:
                    x -= 1
        ''')
        f = tmp_path / "complex.py"
        f.write_text(source)
        tree = parse_python_file(str(f))
        funcs = find_functions(tree, str(f))

        assert funcs[0].complexity >= 4  # base 1 + if + for + if + while


class TestFindClasses:
    """Test class extraction from AST."""

    def test_find_class(self, tmp_path):
        source = textwrap.dedent('''\
            class Animal:
                """A base animal."""
                def speak(self):
                    pass
                def eat(self):
                    pass
        ''')
        f = tmp_path / "cls.py"
        f.write_text(source)
        tree = parse_python_file(str(f))
        classes = find_classes(tree, str(f))

        assert len(classes) == 1
        assert classes[0].name == "Animal"
        assert "speak" in classes[0].methods
        assert "eat" in classes[0].methods

    def test_find_class_with_bases(self, tmp_path):
        source = "class Dog(Animal, Serializable): pass\n"
        f = tmp_path / "dog.py"
        f.write_text(source)
        tree = parse_python_file(str(f))
        classes = find_classes(tree, str(f))

        assert classes[0].bases == ["Animal", "Serializable"]


class TestFindImports:
    """Test import extraction from AST."""

    def test_find_import(self, tmp_path):
        source = "import os\nfrom pathlib import Path\n"
        f = tmp_path / "imp.py"
        f.write_text(source)
        tree = parse_python_file(str(f))
        imports = find_imports(tree, str(f))

        assert len(imports) == 2
        assert imports[0].module == "os"
        assert imports[0].is_from is False
        assert imports[1].module == "pathlib"
        assert imports[1].names == ["Path"]
        assert imports[1].is_from is True


class TestFindCalls:
    """Test call extraction from AST."""

    def test_find_simple_call(self, tmp_path):
        source = textwrap.dedent('''\
            def main():
                print("hello")
                result = process(data)
        ''')
        f = tmp_path / "calls.py"
        f.write_text(source)
        tree = parse_python_file(str(f))
        calls = find_calls(tree, str(f))

        callee_names = [c.callee for c in calls]
        assert "print" in callee_names
        assert "process" in callee_names
        assert all(c.caller == "main" for c in calls)

    def test_find_method_call(self, tmp_path):
        source = textwrap.dedent('''\
            def run():
                client.send("data")
        ''')
        f = tmp_path / "method.py"
        f.write_text(source)
        tree = parse_python_file(str(f))
        calls = find_calls(tree, str(f))

        assert any(c.callee == "client.send" for c in calls)


class TestScanPythonFiles:
    """Test file scanning."""

    def test_scan_finds_python_files(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.py").write_text("y = 2\n")
        (tmp_path / "c.txt").write_text("not python\n")

        files = scan_python_files(str(tmp_path))
        assert len(files) == 2
        assert all(f.endswith(".py") for f in files)

    def test_scan_skips_pycache(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "cached.py").write_text("cached\n")

        files = scan_python_files(str(tmp_path))
        assert len(files) == 1
