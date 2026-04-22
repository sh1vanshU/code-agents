"""Mock Builder — generate mock objects for external services.

Creates realistic mock implementations with configurable responses,
error scenarios, and latency simulation.

Usage:
    from code_agents.testing.mock_builder import MockBuilder
    builder = MockBuilder(MockBuilderConfig(cwd="/path/to/repo"))
    result = builder.build("code_agents/cicd/jenkins_client.py:JenkinsClient")
    print(format_mock(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.testing.mock_builder")


@dataclass
class MockBuilderConfig:
    cwd: str = "."
    include_error_scenarios: bool = True
    include_latency: bool = False


@dataclass
class MockMethod:
    """A method on the mock."""
    name: str
    args: list[str] = field(default_factory=list)
    return_type: str = ""
    return_value: str = ""  # Python code for return value
    is_async: bool = False
    side_effects: list[str] = field(default_factory=list)  # error scenarios


@dataclass
class MockDefinition:
    """A complete mock definition."""
    class_name: str
    original_class: str
    original_file: str
    methods: list[MockMethod] = field(default_factory=list)
    code: str = ""  # generated Python code
    test_code: str = ""  # example test using the mock


@dataclass
class MockBuildResult:
    """Result of building mocks."""
    target: str
    mocks: list[MockDefinition] = field(default_factory=list)
    summary: str = ""


class MockBuilder:
    """Generate mock implementations."""

    def __init__(self, config: MockBuilderConfig):
        self.config = config

    def build(self, target: str) -> MockBuildResult:
        """Build mocks for a target class."""
        logger.info("Building mocks for: %s", target)
        result = MockBuildResult(target=target)

        file_path, _, class_name = target.rpartition(":")
        if not file_path or not class_name:
            result.summary = "Use format: file.py:ClassName"
            return result

        full_path = os.path.join(self.config.cwd, file_path)

        from code_agents.analysis._ast_helpers import parse_python_file, find_classes, find_functions

        tree = parse_python_file(full_path)
        if tree is None:
            result.summary = f"Could not parse {file_path}"
            return result

        classes = find_classes(tree, file_path)
        funcs = find_functions(tree, file_path)

        target_class = next((c for c in classes if c.name == class_name), None)
        if not target_class:
            result.summary = f"Class '{class_name}' not found"
            return result

        # Get methods for this class
        class_methods = [f for f in funcs if f.class_name == class_name]

        mock_def = MockDefinition(
            class_name=f"Mock{class_name}",
            original_class=class_name,
            original_file=file_path,
        )

        for method in class_methods:
            if method.name.startswith("_") and method.name != "__init__":
                continue

            mock_method = MockMethod(
                name=method.name,
                args=[a for a in method.args if a != "self"],
                return_type=method.return_annotation,
                is_async=method.is_async,
            )

            # Generate return value
            mock_method.return_value = self._generate_return_value(method.return_annotation, method.name)

            # Generate error scenarios
            if self.config.include_error_scenarios:
                mock_method.side_effects = self._generate_error_scenarios(method.name)

            mock_def.methods.append(mock_method)

        # Generate code
        mock_def.code = self._generate_mock_code(mock_def)
        mock_def.test_code = self._generate_test_code(mock_def, file_path, class_name)

        result.mocks.append(mock_def)
        result.summary = f"Generated Mock{class_name} with {len(mock_def.methods)} methods"

        return result

    def _generate_return_value(self, return_type: str, method_name: str) -> str:
        """Generate a sensible return value based on type and method name."""
        if not return_type:
            if method_name == "__init__":
                return "None"
            if method_name.startswith("get"):
                return '{"id": 1, "name": "mock"}'
            if method_name.startswith("list"):
                return '[{"id": 1}, {"id": 2}]'
            if method_name.startswith(("is_", "has_", "can_", "should_")):
                return "True"
            if method_name.startswith(("create", "add", "insert")):
                return '{"id": 1, "created": True}'
            if method_name.startswith(("delete", "remove")):
                return "True"
            if method_name.startswith(("update", "set")):
                return '{"updated": True}'
            return "None"

        rt = return_type.lower()
        if "str" in rt:
            return '"mock_value"'
        if "int" in rt:
            return "42"
        if "float" in rt:
            return "3.14"
        if "bool" in rt:
            return "True"
        if "list" in rt:
            return "[]"
        if "dict" in rt:
            return "{}"
        if "none" in rt:
            return "None"
        if "optional" in rt:
            return "None"
        return "MagicMock()"

    def _generate_error_scenarios(self, method_name: str) -> list[str]:
        """Generate common error scenarios for a method."""
        scenarios = []
        if any(kw in method_name.lower() for kw in ("connect", "open", "fetch", "request", "call")):
            scenarios.extend(["ConnectionError('Service unavailable')", "TimeoutError('Request timed out')"])
        if any(kw in method_name.lower() for kw in ("get", "find", "fetch", "load", "read")):
            scenarios.append("KeyError('Not found')")
        if any(kw in method_name.lower() for kw in ("create", "insert", "add", "save", "write")):
            scenarios.append("ValueError('Invalid data')")
        if any(kw in method_name.lower() for kw in ("delete", "remove")):
            scenarios.append("PermissionError('Not authorized')")
        return scenarios

    def _generate_mock_code(self, mock_def: MockDefinition) -> str:
        """Generate Python mock class code."""
        lines = [
            f"class {mock_def.class_name}:",
            f'    """Mock for {mock_def.original_class}."""',
            "",
        ]

        for method in mock_def.methods:
            prefix = "async def" if method.is_async else "def"
            args_str = ", ".join(["self"] + method.args)
            lines.append(f"    {prefix} {method.name}({args_str}):")
            lines.append(f"        return {method.return_value}")
            lines.append("")

        return "\n".join(lines)

    def _generate_test_code(self, mock_def: MockDefinition, file_path: str, class_name: str) -> str:
        """Generate example test using the mock."""
        module = file_path.replace("/", ".").replace(".py", "")
        lines = [
            f"from unittest.mock import patch, MagicMock",
            f"",
            f"class Test{class_name}:",
            f"",
            f'    @patch("{module}.{class_name}")',
            f"    def test_with_mock(self, MockClass):",
            f"        mock = MockClass.return_value",
        ]

        for method in mock_def.methods[:3]:
            if method.name == "__init__":
                continue
            lines.append(f"        mock.{method.name}.return_value = {method.return_value}")

        lines.extend([
            f"        # Call the code under test",
            f"        # result = function_that_uses_{class_name.lower()}()",
            f"        # assert result is not None",
        ])

        return "\n".join(lines)


def format_mock(result: MockBuildResult) -> str:
    """Format mock build result for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Mock Builder: {result.target}")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {result.summary}")

    for mock_def in result.mocks:
        lines.append(f"\n  --- {mock_def.class_name} ---")
        lines.append(f"  Methods: {', '.join(m.name for m in mock_def.methods)}")
        lines.append(f"\n  Generated Code:")
        for code_line in mock_def.code.splitlines():
            lines.append(f"    {code_line}")
        lines.append(f"\n  Example Test:")
        for test_line in mock_def.test_code.splitlines():
            lines.append(f"    {test_line}")

    lines.append("")
    return "\n".join(lines)
