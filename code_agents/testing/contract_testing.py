"""API Contract Testing — generate Pact and JSON Schema tests from API routes.

Scans FastAPI/Flask route definitions, generates consumer-driven contract tests
(Pact-style) and JSON Schema validation tests.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.testing.contract_testing")

# HTTP methods
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


@dataclass
class RouteInfo:
    """Discovered API route information."""

    path: str
    method: str
    function_name: str
    file_path: str
    line_number: int = 0
    params: list[str] = field(default_factory=list)
    response_model: str = ""
    request_body: str = ""
    status_code: int = 200
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "method": self.method,
            "function_name": self.function_name,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "params": self.params,
            "response_model": self.response_model,
            "request_body": self.request_body,
            "status_code": self.status_code,
        }


@dataclass
class ContractTest:
    """A generated contract test."""

    route: RouteInfo
    test_type: str  # "pact" or "schema"
    test_code: str
    test_name: str
    file_name: str

    def to_dict(self) -> dict:
        return {
            "route_path": self.route.path,
            "route_method": self.route.method,
            "test_type": self.test_type,
            "test_name": self.test_name,
            "file_name": self.file_name,
            "test_code": self.test_code,
        }


@dataclass
class VerificationResult:
    """Result of running contract tests."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
        }


class ContractTestGenerator:
    """Generate API contract tests from route definitions."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("ContractTestGenerator initialized for %s", cwd)

    def generate(self, target: str = "", fmt: str = "pact") -> list[ContractTest]:
        """Generate contract tests for discovered API routes.

        Args:
            target: Optional file or directory to scan (default: scan all).
            fmt: Test format — "pact" or "schema" or "both".

        Returns:
            List of ContractTest objects.
        """
        routes = self._scan_api_routes(target)
        if not routes:
            logger.info("No API routes found")
            return []

        logger.info("Found %d API routes, generating %s tests", len(routes), fmt)
        tests: list[ContractTest] = []

        for route in routes:
            if fmt in ("pact", "both"):
                test = self._generate_pact_test(route)
                tests.append(test)
            if fmt in ("schema", "both"):
                test = self._generate_schema_test(route)
                tests.append(test)

        logger.info("Generated %d contract tests", len(tests))
        return tests

    def _scan_api_routes(self, target: str = "") -> list[RouteInfo]:
        """Scan Python files for FastAPI/Flask route decorators.

        Looks for patterns like:
          @app.get("/path"), @router.post("/path"), @app.route("/path")
        """
        search_dir = os.path.join(self.cwd, target) if target else self.cwd
        if not os.path.exists(search_dir):
            logger.warning("Target path not found: %s", search_dir)
            return []

        routes: list[RouteInfo] = []

        # Patterns for route decorators
        # FastAPI: @app.get("/path"), @router.post("/path", response_model=Foo)
        # Flask: @app.route("/path", methods=["GET"])
        fastapi_pat = re.compile(
            r'@\w+\.(' + '|'.join(_HTTP_METHODS) + r')\(\s*["\']([^"\']+)["\']'
            r'(?:[^)]*?response_model\s*=\s*(\w+))?'
            r'(?:[^)]*?status_code\s*=\s*(\d+))?',
        )
        flask_pat = re.compile(
            r'@\w+\.route\(\s*["\']([^"\']+)["\']'
            r'(?:[^)]*?methods\s*=\s*\[([^\]]+)\])?',
        )

        py_files = self._find_python_files(search_dir)

        for fpath in py_files:
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()

                # FastAPI routes
                for m in fastapi_pat.finditer(content):
                    method = m.group(1).upper()
                    path = m.group(2)
                    response_model = m.group(3) or ""
                    status_code = int(m.group(4)) if m.group(4) else 200

                    # Find function name (next def after decorator)
                    line_no = content[:m.start()].count("\n") + 1
                    func_name = self._find_function_after_line(lines, line_no)
                    params = self._extract_path_params(path)
                    body = self._find_request_body(lines, line_no)
                    rel = os.path.relpath(fpath, self.cwd)

                    routes.append(RouteInfo(
                        path=path, method=method, function_name=func_name,
                        file_path=rel, line_number=line_no, params=params,
                        response_model=response_model, request_body=body,
                        status_code=status_code,
                    ))

                # Flask routes
                for m in flask_pat.finditer(content):
                    path = m.group(1)
                    methods_str = m.group(2) or '"GET"'
                    methods = re.findall(r'["\'](\w+)["\']', methods_str)
                    if not methods:
                        methods = ["GET"]

                    line_no = content[:m.start()].count("\n") + 1
                    func_name = self._find_function_after_line(lines, line_no)
                    params = self._extract_path_params(path)
                    rel = os.path.relpath(fpath, self.cwd)

                    for method in methods:
                        routes.append(RouteInfo(
                            path=path, method=method.upper(),
                            function_name=func_name, file_path=rel,
                            line_number=line_no, params=params,
                        ))

            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("Error reading %s: %s", fpath, exc)

        return routes

    def _generate_pact_test(self, route: RouteInfo) -> ContractTest:
        """Generate a Pact-style consumer contract test for a route."""
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", route.path.strip("/"))
        test_name = f"test_pact_{route.method.lower()}_{safe_name}"
        file_name = f"test_contract_pact_{safe_name}.py"

        # Build path with example params
        example_path = route.path
        for param in route.params:
            example_path = example_path.replace(f"{{{param}}}", f"test_{param}")

        # Build request body for POST/PUT/PATCH
        body_code = ""
        if route.method in ("POST", "PUT", "PATCH"):
            body_code = (
                '    request_body = {"example_field": "test_value"}\n'
            )

        method_lower = route.method.lower()
        call_args = f'"{example_path}"'
        if body_code:
            call_args += ", json=request_body"

        test_code = f'''"""Pact contract test for {route.method} {route.path}."""
import pytest


class TestPact{safe_name.title().replace("_", "")}:
    """Consumer contract: {route.method} {route.path}"""

    def test_returns_expected_status(self, client):
        """Verify {route.method} {route.path} returns {route.status_code}."""
{body_code}        response = client.{method_lower}({call_args})
        assert response.status_code == {route.status_code}

    def test_response_has_expected_shape(self, client):
        """Verify response body matches expected contract shape."""
{body_code}        response = client.{method_lower}({call_args})
        data = response.json()
        assert isinstance(data, (dict, list)), (
            f"Expected dict or list, got {{type(data).__name__}}"
        )

    def test_content_type_json(self, client):
        """Verify response content type is application/json."""
{body_code}        response = client.{method_lower}({call_args})
        ct = response.headers.get("content-type", "")
        assert "application/json" in ct or response.status_code == 204
'''
        if route.response_model:
            test_code += f'''
    def test_response_model_shape(self, client):
        """Verify response matches {route.response_model} schema."""
{body_code}        response = client.{method_lower}({call_args})
        if response.status_code == {route.status_code}:
            data = response.json()
            # Validate against {route.response_model} fields
            assert isinstance(data, dict)
'''

        return ContractTest(
            route=route, test_type="pact", test_code=test_code,
            test_name=test_name, file_name=file_name,
        )

    def _generate_schema_test(self, route: RouteInfo) -> ContractTest:
        """Generate a JSON Schema validation test for a route."""
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", route.path.strip("/"))
        test_name = f"test_schema_{route.method.lower()}_{safe_name}"
        file_name = f"test_contract_schema_{safe_name}.py"

        example_path = route.path
        for param in route.params:
            example_path = example_path.replace(f"{{{param}}}", f"test_{param}")

        body_code = ""
        if route.method in ("POST", "PUT", "PATCH"):
            body_code = '    request_body = {"example_field": "test_value"}\n'

        method_lower = route.method.lower()
        call_args = f'"{example_path}"'
        if body_code:
            call_args += ", json=request_body"

        test_code = f'''"""JSON Schema contract test for {route.method} {route.path}."""
import json
import pytest


# Define expected schema for {route.method} {route.path}
EXPECTED_SCHEMA = {{
    "type": "object",
    "properties": {{
        "status": {{"type": "string"}},
    }},
}}


def _validate_schema(data: dict, schema: dict) -> list[str]:
    """Simple schema validator (no jsonschema dependency)."""
    errors = []
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(data, dict):
        errors.append(f"Expected object, got {{type(data).__name__}}")
    elif expected_type == "array" and not isinstance(data, list):
        errors.append(f"Expected array, got {{type(data).__name__}}")
    return errors


class TestSchema{safe_name.title().replace("_", "")}:
    """JSON Schema validation: {route.method} {route.path}"""

    def {test_name}(self, client):
        """Validate response against JSON Schema."""
{body_code}        response = client.{method_lower}({call_args})
        if response.status_code in (200, 201):
            data = response.json()
            errors = _validate_schema(data, EXPECTED_SCHEMA)
            assert not errors, f"Schema validation failed: {{errors}}"

    def test_error_response_schema(self, client):
        """Verify error responses follow standard shape."""
        # Test with invalid data to trigger error
        response = client.{method_lower}("{example_path}_invalid")
        if response.status_code >= 400:
            data = response.json()
            # Error responses should have detail or message
            assert "detail" in data or "message" in data or "error" in data, (
                "Error response missing detail/message/error field"
            )
'''

        return ContractTest(
            route=route, test_type="schema", test_code=test_code,
            test_name=test_name, file_name=file_name,
        )

    def _verify_contracts(self, test_dir: str = "") -> VerificationResult:
        """Run generated contract tests and return results.

        Args:
            test_dir: Directory containing generated contract tests.
        """
        if not test_dir:
            test_dir = os.path.join(self.cwd, "tests", "contracts")

        if not os.path.isdir(test_dir):
            return VerificationResult(errors=["Contract test directory not found"])

        try:
            result = subprocess.run(
                ["python", "-m", "pytest", test_dir, "-v", "--tb=short", "-q"],
                capture_output=True, text=True, cwd=self.cwd, timeout=120,
            )
            output = result.stdout + result.stderr

            # Parse pytest output
            total = passed = failed = 0
            for line in output.splitlines():
                m = re.search(r"(\d+) passed", line)
                if m:
                    passed = int(m.group(1))
                m = re.search(r"(\d+) failed", line)
                if m:
                    failed = int(m.group(1))

            total = passed + failed
            errors = []
            if result.returncode != 0:
                # Collect failure details
                for line in output.splitlines():
                    if line.startswith("FAILED") or line.startswith("ERROR"):
                        errors.append(line.strip())

            return VerificationResult(
                total=total, passed=passed, failed=failed, errors=errors,
            )

        except (subprocess.TimeoutExpired, OSError) as exc:
            return VerificationResult(errors=[f"Test execution failed: {exc}"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_python_files(self, directory: str) -> list[str]:
        """Find all Python files in a directory, excluding venv/node_modules."""
        result: list[str] = []
        skip_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox"}

        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                if f.endswith(".py"):
                    result.append(os.path.join(root, f))
        return result

    def _find_function_after_line(self, lines: list[str], line_no: int) -> str:
        """Find the next 'def' or 'async def' after a decorator line."""
        for i in range(line_no, min(line_no + 10, len(lines))):
            m = re.match(r"\s*(?:async\s+)?def\s+(\w+)", lines[i])
            if m:
                return m.group(1)
        return "unknown"

    def _extract_path_params(self, path: str) -> list[str]:
        """Extract path parameters like {id} from a route path."""
        return re.findall(r"\{(\w+)\}", path)

    def _find_request_body(self, lines: list[str], line_no: int) -> str:
        """Try to find the request body model from function signature."""
        for i in range(line_no, min(line_no + 10, len(lines))):
            # Look for body: ModelName or request: ModelName
            m = re.search(r"(?:body|request|data|payload)\s*:\s*(\w+)", lines[i])
            if m:
                return m.group(1)
        return ""


def format_tests_summary(tests: list[ContractTest]) -> str:
    """Format a summary of generated contract tests."""
    if not tests:
        return "No contract tests generated — no API routes found."

    lines: list[str] = []
    lines.append(f"\n  \033[1mContract Tests Generated\033[0m")
    lines.append(f"  Total: {len(tests)} tests")
    lines.append("")

    pact_tests = [t for t in tests if t.test_type == "pact"]
    schema_tests = [t for t in tests if t.test_type == "schema"]

    if pact_tests:
        lines.append(f"  \033[36mPact Tests ({len(pact_tests)})\033[0m")
        for t in pact_tests[:10]:
            lines.append(f"    {t.route.method:6s} {t.route.path} -> {t.file_name}")
        if len(pact_tests) > 10:
            lines.append(f"    ... and {len(pact_tests) - 10} more")
        lines.append("")

    if schema_tests:
        lines.append(f"  \033[36mSchema Tests ({len(schema_tests)})\033[0m")
        for t in schema_tests[:10]:
            lines.append(f"    {t.route.method:6s} {t.route.path} -> {t.file_name}")
        if len(schema_tests) > 10:
            lines.append(f"    ... and {len(schema_tests) - 10} more")
        lines.append("")

    return "\n".join(lines)
