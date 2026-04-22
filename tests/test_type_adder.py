"""Tests for code_agents.type_adder — Type Annotation Adder."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.reviews.type_adder import TypeAdder, UntypedFunction, format_type_report


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repo with Python files."""
    src = tmp_path / "src"
    src.mkdir()

    # File with untyped functions
    (src / "untyped.py").write_text(textwrap.dedent("""\
        def greet(name):
            return f"Hello, {name}"

        def add(a, b):
            return a + b

        def get_items(data):
            result = []
            for k in data.keys():
                result.append(k)
            return result

        def process(enabled, count):
            if not enabled:
                return None
            return count * 2
    """))

    # File with typed functions
    (src / "typed.py").write_text(textwrap.dedent("""\
        def greet(name: str) -> str:
            return f"Hello, {name}"

        def add(a: int, b: int) -> int:
            return a + b
    """))

    # File with mixed
    (src / "mixed.py").write_text(textwrap.dedent("""\
        def typed_func(x: int) -> str:
            return str(x)

        def untyped_func(path):
            return path.strip()

        class Foo:
            def method(self, items):
                items.append("x")
                return items
    """))

    return tmp_path


class TestTypeAdder:
    def test_scan_finds_untyped(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        results = adder.scan(path="src/untyped.py")
        assert len(results) > 0
        names = [r.name for r in results]
        assert "greet" in names
        assert "add" in names

    def test_scan_skips_typed(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        results = adder.scan(path="src/typed.py")
        assert len(results) == 0

    def test_scan_mixed_file(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        results = adder.scan(path="src/mixed.py")
        names = [r.name for r in results]
        assert "typed_func" not in names
        assert "untyped_func" in names

    def test_scan_whole_directory(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        results = adder.scan(path="src")
        assert len(results) >= 4  # At least from untyped.py + mixed.py

    def test_scan_empty_path(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        results = adder.scan()
        assert len(results) >= 4

    def test_infer_return_str(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        body = 'def foo(x):\n    return f"hello {x}"'
        assert adder._infer_return_type(body) == "str"

    def test_infer_return_bool(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        body = "def foo(x):\n    return True"
        assert adder._infer_return_type(body) == "bool"

    def test_infer_return_list(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        body = "def foo():\n    return []"
        assert adder._infer_return_type(body) == "list"

    def test_infer_return_dict(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        body = "def foo():\n    return {}"
        assert adder._infer_return_type(body) == "dict"

    def test_infer_return_none(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        body = "def foo():\n    return\n"
        assert adder._infer_return_type(body) == "None"

    def test_infer_return_optional(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        body = "def foo(x):\n    if not x:\n        return None\n    return str(x)"
        result = adder._infer_return_type(body)
        assert "Optional" in result or result == "str"

    def test_infer_param_types_by_name(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        body = "def foo(name, count, enabled):\n    pass"
        params = adder._infer_param_types("foo", body)
        assert params.get("name") == "str"
        assert params.get("count") == "int"
        assert params.get("enabled") == "bool"

    def test_infer_param_types_by_usage(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        body = "def foo(x, y):\n    x.strip()\n    y.append(1)"
        params = adder._infer_param_types("foo", body)
        assert params.get("x") == "str"
        assert params.get("y") == "list"

    def test_infer_skips_self_cls(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        body = "def foo(self, name):\n    pass"
        params = adder._infer_param_types("foo", body)
        assert "self" not in params

    def test_add_types_dry_run(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        count = adder.add_types(path="src/untyped.py", dry_run=True)
        assert count >= 1
        # File should not be modified
        content = (tmp_repo / "src" / "untyped.py").read_text()
        assert "-> str" not in content

    def test_add_types_writes(self, tmp_repo):
        adder = TypeAdder(cwd=str(tmp_repo))
        count = adder.add_types(path="src/untyped.py", dry_run=False)
        assert count >= 1

    def test_untyped_function_dataclass(self):
        f = UntypedFunction(
            file="test.py", line=1, name="foo",
            params=["a", "b"],
        )
        assert f.file == "test.py"
        assert f.inferred_return == ""
        assert f.inferred_params == {}


class TestFormatTypeReport:
    def test_empty_report(self):
        result = format_type_report([])
        assert "All functions have type annotations" in result

    def test_report_with_findings(self):
        funcs = [
            UntypedFunction(
                file="foo.py", line=10, name="bar",
                inferred_return="str",
            ),
            UntypedFunction(
                file="foo.py", line=20, name="baz",
                inferred_params={"x": "int"},
            ),
        ]
        result = format_type_report(funcs)
        assert "foo.py" in result
        assert "bar" in result
        assert "baz" in result
        assert "str" in result


class TestEdgeCases:
    def test_syntax_error_file(self, tmp_path):
        bad = tmp_path / "bad.py"
        bad.write_text("def foo(:\n    pass")
        adder = TypeAdder(cwd=str(tmp_path))
        results = adder.scan()
        # Should not crash, just skip bad file
        assert isinstance(results, list)

    def test_empty_directory(self, tmp_path):
        adder = TypeAdder(cwd=str(tmp_path))
        results = adder.scan()
        assert results == []

    def test_nonexistent_path(self, tmp_path):
        adder = TypeAdder(cwd=str(tmp_path))
        results = adder.scan(path="does_not_exist")
        assert results == []
