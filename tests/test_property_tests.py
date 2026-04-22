"""Tests for the property-based test synthesis module."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.testing.property_tests import (
    PropertyTestGenerator,
    FuncInfo,
    FuncParam,
)


class TestPropertyTestGenerator:
    """Test PropertyTestGenerator core functionality."""

    def test_generate_simple_function(self, tmp_path):
        src = tmp_path / "utils.py"
        src.write_text(textwrap.dedent("""\
            def add(a: int, b: int) -> int:
                return a + b
        """))
        gen = PropertyTestGenerator(str(tmp_path))
        result = gen.generate(str(src))
        assert "from hypothesis" in result
        assert "test_add_no_crash" in result
        assert "st.integers()" in result

    def test_generate_specific_function(self, tmp_path):
        src = tmp_path / "math.py"
        src.write_text(textwrap.dedent("""\
            def multiply(x: float, y: float) -> float:
                return x * y

            def divide(x: float, y: float) -> float:
                return x / y
        """))
        gen = PropertyTestGenerator(str(tmp_path))
        result = gen.generate(str(src), function="multiply")
        assert "test_multiply" in result
        assert "test_divide" not in result

    def test_generate_no_params(self, tmp_path):
        src = tmp_path / "simple.py"
        src.write_text("def hello() -> str:\n    return 'hi'\n")
        gen = PropertyTestGenerator(str(tmp_path))
        result = gen.generate(str(src))
        assert "test_hello_no_crash" in result

    def test_generate_string_params(self, tmp_path):
        src = tmp_path / "text.py"
        src.write_text("def normalize(text: str) -> str:\n    return text.strip()\n")
        gen = PropertyTestGenerator(str(tmp_path))
        result = gen.generate(str(src))
        assert "st.text(" in result
        # Idempotent property should be generated for 'normalize'
        assert "idempotent" in result

    def test_generate_missing_file(self, tmp_path):
        gen = PropertyTestGenerator(str(tmp_path))
        result = gen.generate("/nonexistent/file.py")
        assert "Error" in result

    def test_generate_missing_function(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def foo(): pass\n")
        gen = PropertyTestGenerator(str(tmp_path))
        result = gen.generate(str(src), function="bar")
        assert "not found" in result

    def test_generate_skips_methods(self, tmp_path):
        src = tmp_path / "cls.py"
        src.write_text(textwrap.dedent("""\
            class MyClass:
                def do_thing(self, x: int) -> int:
                    return x
        """))
        gen = PropertyTestGenerator(str(tmp_path))
        result = gen.generate(str(src))
        assert "Skipping method" in result

    def test_generate_encode_roundtrip_hint(self, tmp_path):
        src = tmp_path / "codec.py"
        src.write_text("def encode(data: str) -> bytes:\n    return data.encode()\n")
        gen = PropertyTestGenerator(str(tmp_path))
        result = gen.generate(str(src))
        assert "roundtrip" in result.lower() or "Roundtrip" in result


class TestInferStrategies:
    """Test strategy inference from types."""

    def test_int_strategy(self):
        gen = PropertyTestGenerator("/tmp")
        strats = gen._infer_strategies([FuncParam("x", "int")])
        assert strats["x"] == "st.integers()"

    def test_str_strategy(self):
        gen = PropertyTestGenerator("/tmp")
        strats = gen._infer_strategies([FuncParam("name", "str")])
        assert "st.text(" in strats["name"]

    def test_list_strategy(self):
        gen = PropertyTestGenerator("/tmp")
        strats = gen._infer_strategies([FuncParam("items", "list[int]")])
        assert "st.lists(" in strats["items"]

    def test_optional_strategy(self):
        gen = PropertyTestGenerator("/tmp")
        strats = gen._infer_strategies([FuncParam("val", "Optional[str]")])
        assert "st.one_of(st.none()" in strats["val"]

    def test_no_annotation_strategy(self):
        gen = PropertyTestGenerator("/tmp")
        strats = gen._infer_strategies([FuncParam("x", "")])
        assert "st.one_of(" in strats["x"]

    def test_skips_self(self):
        gen = PropertyTestGenerator("/tmp")
        strats = gen._infer_strategies([FuncParam("self"), FuncParam("x", "int")])
        assert "self" not in strats
        assert "x" in strats


class TestCommonProperties:
    """Test common property detection."""

    def test_normalize_idempotent(self):
        gen = PropertyTestGenerator("/tmp")
        props = gen._common_properties("normalize_text")
        assert any("idempotent" in p for p in props)

    def test_encode_roundtrip(self):
        gen = PropertyTestGenerator("/tmp")
        props = gen._common_properties("encode")
        assert any("roundtrip" in p.lower() or "Roundtrip" in p for p in props)

    def test_no_special_properties(self):
        gen = PropertyTestGenerator("/tmp")
        props = gen._common_properties("calculate_tax")
        assert len(props) == 0
