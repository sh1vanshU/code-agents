"""Tests for api_doc_generator.py — endpoint discovery and doc generation."""

import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.generators.api_doc_generator import (
    APIDocGenerator,
    EndpointInfo,
    EndpointParam,
    _java_type_to_str,
    _python_type_to_str,
    _extract_javadoc,
    _extract_python_docstring,
    _parse_python_params,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def spring_repo(tmp_path):
    """Create a temp repo with Spring controller files."""
    src = tmp_path / "src" / "main" / "java" / "com" / "example"
    src.mkdir(parents=True)

    (src / "PaymentController.java").write_text(
        'package com.example;\n'
        '\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '\n'
        '@RestController\n'
        '@RequestMapping("/api/v1/payment")\n'
        'public class PaymentController {\n'
        '\n'
        '    /**\n'
        '     * Process a payment transaction.\n'
        '     */\n'
        '    @PostMapping("")\n'
        '    public PaymentResponse processPayment(@RequestBody PaymentRequest request) {\n'
        '        return null;\n'
        '    }\n'
        '\n'
        '    @GetMapping("/{id}")\n'
        '    public PaymentResponse getPayment(@PathVariable String id) {\n'
        '        return null;\n'
        '    }\n'
        '\n'
        '    @PutMapping("/{id}")\n'
        '    public PaymentResponse updatePayment(\n'
        '        @PathVariable String id,\n'
        '        @RequestBody PaymentRequest request) {\n'
        '        return null;\n'
        '    }\n'
        '\n'
        '    @DeleteMapping("/{id}")\n'
        '    public void cancelPayment(@PathVariable String id) {\n'
        '    }\n'
        '\n'
        '    @GetMapping("/search")\n'
        '    public List<PaymentResponse> searchPayments(\n'
        '        @RequestParam String merchantId,\n'
        '        @RequestParam Integer limit) {\n'
        '        return null;\n'
        '    }\n'
        '}\n'
    )
    return tmp_path


@pytest.fixture
def fastapi_repo(tmp_path):
    """Create a temp repo with FastAPI route files."""
    (tmp_path / "routes.py").write_text(
        'from fastapi import APIRouter\n'
        '\n'
        'router = APIRouter()\n'
        '\n'
        '@router.get("/api/users/{user_id}")\n'
        'async def get_user(user_id: int):\n'
        '    """Get a user by ID."""\n'
        '    pass\n'
        '\n'
        '@router.post("/api/users")\n'
        'async def create_user(name: str, email: str):\n'
        '    """Create a new user."""\n'
        '    pass\n'
        '\n'
        '@router.delete("/api/users/{user_id}")\n'
        'async def delete_user(user_id: int):\n'
        '    pass\n'
    )
    return tmp_path


@pytest.fixture
def flask_repo(tmp_path):
    """Create a temp repo with Flask route files."""
    (tmp_path / "app.py").write_text(
        'from flask import Flask\n'
        '\n'
        'app = Flask(__name__)\n'
        '\n'
        '@app.route("/health")\n'
        'def health():\n'
        '    """Health check endpoint."""\n'
        '    return {"status": "ok"}\n'
        '\n'
        '@app.route("/api/items", methods=["GET", "POST"])\n'
        'def items():\n'
        '    pass\n'
    )
    return tmp_path


@pytest.fixture
def express_repo(tmp_path):
    """Create a temp repo with Express route files."""
    (tmp_path / "routes.js").write_text(
        'const express = require("express");\n'
        'const router = express.Router();\n'
        '\n'
        '/**\n'
        ' * Get all products.\n'
        ' */\n'
        'router.get("/api/products", getProducts);\n'
        '\n'
        'router.post("/api/products", createProduct);\n'
        '\n'
        'router.get("/api/products/:id", getProductById);\n'
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Test: Spring endpoint discovery
# ---------------------------------------------------------------------------


class TestSpringDiscovery:

    def test_discovers_spring_endpoints(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        endpoints = gen.scan_endpoints()
        assert len(endpoints) == 5

    def test_discovers_post_mapping(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        endpoints = gen.scan_endpoints()
        post_eps = [e for e in endpoints if e.method == "POST"]
        assert len(post_eps) == 1
        assert post_eps[0].path == "/api/v1/payment"

    def test_discovers_get_with_path_variable(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        endpoints = gen.scan_endpoints()
        get_eps = [e for e in endpoints if e.method == "GET" and "{id}" in e.path]
        assert len(get_eps) == 1
        assert get_eps[0].path == "/api/v1/payment/{id}"

    def test_discovers_delete_mapping(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        endpoints = gen.scan_endpoints()
        delete_eps = [e for e in endpoints if e.method == "DELETE"]
        assert len(delete_eps) == 1

    def test_discovers_put_mapping(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        endpoints = gen.scan_endpoints()
        put_eps = [e for e in endpoints if e.method == "PUT"]
        assert len(put_eps) == 1

    def test_extracts_request_body(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        endpoints = gen.scan_endpoints()
        post_ep = [e for e in endpoints if e.method == "POST"][0]
        assert post_ep.request_body_type == "PaymentRequest"

    def test_extracts_handler_name(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        endpoints = gen.scan_endpoints()
        handlers = {e.handler for e in endpoints if e.handler}
        assert "processPayment" in handlers
        assert "getPayment" in handlers

    def test_extracts_javadoc_description(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        endpoints = gen.scan_endpoints()
        post_ep = [e for e in endpoints if e.method == "POST"][0]
        assert "Process a payment" in post_ep.description


# ---------------------------------------------------------------------------
# Test: FastAPI endpoint discovery
# ---------------------------------------------------------------------------


class TestFastAPIDiscovery:

    def test_discovers_fastapi_endpoints(self, fastapi_repo):
        gen = APIDocGenerator(cwd=str(fastapi_repo))
        endpoints = gen.scan_endpoints()
        assert len(endpoints) == 3

    def test_discovers_get_route(self, fastapi_repo):
        gen = APIDocGenerator(cwd=str(fastapi_repo))
        endpoints = gen.scan_endpoints()
        get_eps = [e for e in endpoints if e.method == "GET"]
        assert len(get_eps) == 1
        assert "/api/users/{user_id}" in get_eps[0].path

    def test_discovers_post_route(self, fastapi_repo):
        gen = APIDocGenerator(cwd=str(fastapi_repo))
        endpoints = gen.scan_endpoints()
        post_eps = [e for e in endpoints if e.method == "POST"]
        assert len(post_eps) == 1

    def test_extracts_handler_name(self, fastapi_repo):
        gen = APIDocGenerator(cwd=str(fastapi_repo))
        endpoints = gen.scan_endpoints()
        handlers = {e.handler for e in endpoints}
        assert "get_user" in handlers
        assert "create_user" in handlers

    def test_extracts_docstring(self, fastapi_repo):
        gen = APIDocGenerator(cwd=str(fastapi_repo))
        endpoints = gen.scan_endpoints()
        get_ep = [e for e in endpoints if e.method == "GET"][0]
        assert "Get a user by ID" in get_ep.description


# ---------------------------------------------------------------------------
# Test: Flask endpoint discovery
# ---------------------------------------------------------------------------


class TestFlaskDiscovery:

    def test_discovers_flask_routes(self, flask_repo):
        gen = APIDocGenerator(cwd=str(flask_repo))
        endpoints = gen.scan_endpoints()
        # /health (GET) + /api/items (GET, POST)
        assert len(endpoints) == 3

    def test_discovers_multi_method_route(self, flask_repo):
        gen = APIDocGenerator(cwd=str(flask_repo))
        endpoints = gen.scan_endpoints()
        item_eps = [e for e in endpoints if "/api/items" in e.path]
        methods = {e.method for e in item_eps}
        assert methods == {"GET", "POST"}


# ---------------------------------------------------------------------------
# Test: Express endpoint discovery
# ---------------------------------------------------------------------------


class TestExpressDiscovery:

    def test_discovers_express_routes(self, express_repo):
        gen = APIDocGenerator(cwd=str(express_repo))
        endpoints = gen.scan_endpoints()
        assert len(endpoints) == 3

    def test_extracts_express_handler(self, express_repo):
        gen = APIDocGenerator(cwd=str(express_repo))
        endpoints = gen.scan_endpoints()
        handlers = {e.handler for e in endpoints if e.handler}
        assert "getProducts" in handlers

    def test_extracts_jsdoc(self, express_repo):
        gen = APIDocGenerator(cwd=str(express_repo))
        endpoints = gen.scan_endpoints()
        get_all = [e for e in endpoints if e.path == "/api/products" and e.method == "GET"][0]
        assert "Get all products" in get_all.description


# ---------------------------------------------------------------------------
# Test: Parameter extraction
# ---------------------------------------------------------------------------


class TestParameterExtraction:

    def test_spring_path_variable(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        endpoints = gen.scan_endpoints()
        get_ep = [e for e in endpoints if e.method == "GET" and "{id}" in e.path][0]
        path_params = [p for p in get_ep.parameters if p.location == "path"]
        assert len(path_params) == 1
        assert path_params[0].name == "id"

    def test_spring_request_param(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        endpoints = gen.scan_endpoints()
        search_ep = [e for e in endpoints if "search" in e.path][0]
        query_params = [p for p in search_ep.parameters if p.location == "query"]
        assert len(query_params) >= 1

    def test_spring_request_body(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        endpoints = gen.scan_endpoints()
        post_ep = [e for e in endpoints if e.method == "POST"][0]
        assert post_ep.request_body_type == "PaymentRequest"

    def test_python_params(self):
        params = _parse_python_params("user_id: int, name: str", "/api/users/{user_id}")
        assert len(params) == 2
        path_p = [p for p in params if p.name == "user_id"][0]
        assert path_p.location == "path"
        assert path_p.type == "integer"
        query_p = [p for p in params if p.name == "name"][0]
        assert query_p.location == "query"

    def test_python_params_skips_self_request(self):
        params = _parse_python_params("self, request, user_id: int", "/api/{user_id}")
        assert len(params) == 1
        assert params[0].name == "user_id"


# ---------------------------------------------------------------------------
# Test: Markdown generation
# ---------------------------------------------------------------------------


class TestMarkdownGeneration:

    def test_markdown_has_title(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        md = gen.generate_markdown()
        assert "# API Documentation" in md
        assert gen.repo_name in md

    def test_markdown_has_endpoints(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        md = gen.generate_markdown()
        assert "### POST" in md
        assert "### GET" in md

    def test_markdown_has_endpoint_count(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        md = gen.generate_markdown()
        assert "5 endpoints discovered" in md

    def test_markdown_has_request_body(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        md = gen.generate_markdown()
        assert "PaymentRequest" in md

    def test_markdown_has_source_reference(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        md = gen.generate_markdown()
        assert "PaymentController.java" in md


# ---------------------------------------------------------------------------
# Test: OpenAPI generation
# ---------------------------------------------------------------------------


class TestOpenAPIGeneration:

    def test_openapi_structure(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        spec = gen.generate_openapi()
        assert spec["openapi"] == "3.0.3"
        assert "info" in spec
        assert "paths" in spec

    def test_openapi_has_paths(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        spec = gen.generate_openapi()
        assert len(spec["paths"]) > 0

    def test_openapi_has_methods(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        spec = gen.generate_openapi()
        # Find a path with post method
        found_post = False
        for path_obj in spec["paths"].values():
            if "post" in path_obj:
                found_post = True
                break
        assert found_post

    def test_openapi_has_parameters(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        spec = gen.generate_openapi()
        # The GET /{id} endpoint should have path parameter
        id_path = "/api/v1/payment/{id}"
        assert id_path in spec["paths"]
        get_op = spec["paths"][id_path].get("get", {})
        assert "parameters" in get_op

    def test_openapi_info(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        spec = gen.generate_openapi()
        assert gen.repo_name in spec["info"]["title"]


# ---------------------------------------------------------------------------
# Test: Terminal format
# ---------------------------------------------------------------------------


class TestTerminalFormat:

    def test_terminal_has_title(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        output = gen.format_terminal()
        assert "API Documentation" in output
        assert gen.repo_name in output

    def test_terminal_has_endpoint_count(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        output = gen.format_terminal()
        assert "5 endpoints discovered" in output

    def test_terminal_has_methods(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        output = gen.format_terminal()
        assert "POST" in output
        assert "GET" in output
        assert "DELETE" in output

    def test_terminal_has_handler_names(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        output = gen.format_terminal()
        assert "processPayment()" in output

    def test_empty_repo(self, tmp_path):
        gen = APIDocGenerator(cwd=str(tmp_path))
        gen.scan_endpoints()
        output = gen.format_terminal()
        assert "0 endpoints discovered" in output


# ---------------------------------------------------------------------------
# Test: Group by prefix
# ---------------------------------------------------------------------------


class TestGroupByPrefix:

    def test_groups_by_common_prefix(self, spring_repo):
        gen = APIDocGenerator(cwd=str(spring_repo))
        gen.scan_endpoints()
        groups = gen.group_by_prefix()
        assert len(groups) >= 1
        # All Spring endpoints share /api/v1 prefix
        for key, eps in groups.items():
            assert len(eps) > 0

    def test_mixed_repo_groups(self, tmp_path):
        """Test grouping with endpoints from different prefixes."""
        gen = APIDocGenerator(cwd=str(tmp_path))
        gen.endpoints = [
            EndpointInfo(method="GET", path="/api/v1/users", handler="getUsers"),
            EndpointInfo(method="GET", path="/api/v1/users/1", handler="getUser"),
            EndpointInfo(method="GET", path="/api/v2/items", handler="getItems"),
            EndpointInfo(method="GET", path="/health", handler="health"),
        ]
        groups = gen.group_by_prefix()
        assert len(groups) >= 2  # at least api/v1 and api/v2, possibly health


# ---------------------------------------------------------------------------
# Test: Type conversion helpers
# ---------------------------------------------------------------------------


class TestTypeConversion:

    def test_java_type_to_str(self):
        assert _java_type_to_str("String") == "string"
        assert _java_type_to_str("Long") == "integer"
        assert _java_type_to_str("Integer") == "integer"
        assert _java_type_to_str("Double") == "number"
        assert _java_type_to_str("Boolean") == "boolean"
        assert _java_type_to_str("BigDecimal") == "number"
        assert _java_type_to_str("CustomType") == "string"  # fallback

    def test_python_type_to_str(self):
        assert _python_type_to_str("int") == "integer"
        assert _python_type_to_str("float") == "number"
        assert _python_type_to_str("bool") == "boolean"
        assert _python_type_to_str("list") == "array"
        assert _python_type_to_str("dict") == "object"
        assert _python_type_to_str("str") == "string"


# ---------------------------------------------------------------------------
# Test: Javadoc / docstring extraction
# ---------------------------------------------------------------------------


class TestDocExtraction:

    def test_extract_javadoc(self):
        lines = [
            "    /**",
            "     * Process a payment.",
            "     */",
            "    @PostMapping",
        ]
        desc = _extract_javadoc(lines, 3)
        assert "Process a payment" in desc

    def test_extract_javadoc_no_doc(self):
        lines = [
            "    @PostMapping",
        ]
        desc = _extract_javadoc(lines, 0)
        assert desc == ""

    def test_extract_python_docstring_single_line(self):
        lines = [
            '@router.get("/test")',
            'async def test():',
            '    """Test endpoint."""',
            '    pass',
        ]
        desc = _extract_python_docstring(lines, 0)
        assert "Test endpoint" in desc

    def test_extract_python_docstring_missing(self):
        lines = [
            '@router.get("/test")',
            'async def test():',
            '    pass',
        ]
        desc = _extract_python_docstring(lines, 0)
        assert desc == ""

    def test_extract_python_docstring_multiline(self):
        lines = [
            '@router.get("/test")',
            'async def test():',
            '    """',
            '    Multi-line docstring.',
            '    With more details.',
            '    """',
            '    pass',
        ]
        desc = _extract_python_docstring(lines, 0)
        assert "Multi-line docstring" in desc

    def test_extract_javadoc_skips_annotation_lines(self):
        """Non-javadoc content above annotation should return empty."""
        lines = [
            "    // some comment",
            "    private int x = 5;",
            "    @PostMapping",
        ]
        desc = _extract_javadoc(lines, 2)
        assert desc == ""

    def test_extract_javadoc_at_annotation_continuation(self):
        """Javadoc with @param should not include @param in description."""
        lines = [
            "    /**",
            "     * Create a user.",
            "     * @param name the user name",
            "     */",
            "    @PostMapping",
        ]
        desc = _extract_javadoc(lines, 4)
        assert "Create a user" in desc
        assert "@param" not in desc


# ---------------------------------------------------------------------------
# Test: _extract_express_handler
# ---------------------------------------------------------------------------


class TestExtractExpressHandler:

    def test_function_keyword_handler(self, tmp_path):
        (tmp_path / "app.js").write_text(
            'router.get("/api/test", function handleTest(req, res) { });\n'
        )
        gen = APIDocGenerator(cwd=str(tmp_path))
        endpoints = gen.scan_endpoints()
        assert len(endpoints) == 1
        assert endpoints[0].handler == "handleTest"

    def test_no_handler_inline_arrow(self, tmp_path):
        (tmp_path / "app.js").write_text(
            'app.get("/api/test", (req, res) => { });\n'
        )
        gen = APIDocGenerator(cwd=str(tmp_path))
        endpoints = gen.scan_endpoints()
        assert len(endpoints) == 1
        # Arrow functions without identifier return ""
        assert endpoints[0].handler == ""


# ---------------------------------------------------------------------------
# Test: _extract_js_jsdoc
# ---------------------------------------------------------------------------


class TestExtractJsJsdoc:

    def test_jsdoc_extracted(self, tmp_path):
        from code_agents.generators.api_doc_generator import _extract_js_jsdoc
        lines = [
            "/**",
            " * List all items.",
            " */",
            'router.get("/items", listItems);',
        ]
        desc = _extract_js_jsdoc(lines, 3)
        assert "List all items" in desc

    def test_no_jsdoc(self):
        from code_agents.generators.api_doc_generator import _extract_js_jsdoc
        lines = [
            'router.get("/items", listItems);',
        ]
        desc = _extract_js_jsdoc(lines, 0)
        assert desc == ""


# ---------------------------------------------------------------------------
# Test: _parse_python_params edge cases
# ---------------------------------------------------------------------------


class TestParsePythonParamsEdge:

    def test_skips_depends(self):
        params = _parse_python_params("db: Session = Depends(get_db)", "/api/users")
        assert len(params) == 0

    def test_skips_default_values(self):
        params = _parse_python_params("limit: int = 10", "/api/items")
        # Has default but not Query/Path, so skipped
        assert len(params) == 0


# ---------------------------------------------------------------------------
# Test: scan_endpoints with OSError
# ---------------------------------------------------------------------------


class TestScanEndpointsErrors:

    def test_scan_spring_file_oserror(self, tmp_path):
        """OSError reading a .java file should be silently handled."""
        src = tmp_path / "Bad.java"
        src.write_text("@RestController\npublic class Bad {}")
        gen = APIDocGenerator(cwd=str(tmp_path))
        with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
            endpoints = gen.scan_endpoints()
        assert endpoints == []

    def test_scan_python_file_oserror(self, tmp_path):
        src = tmp_path / "bad.py"
        src.write_text('@app.get("/test")\ndef test(): pass')
        gen = APIDocGenerator(cwd=str(tmp_path))
        with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
            endpoints = gen.scan_endpoints()
        assert endpoints == []

    def test_scan_express_file_oserror(self, tmp_path):
        src = tmp_path / "bad.js"
        src.write_text('router.get("/test", handler);')
        gen = APIDocGenerator(cwd=str(tmp_path))
        with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
            endpoints = gen.scan_endpoints()
        assert endpoints == []


# ---------------------------------------------------------------------------
# Test: Spring no-path mapping
# ---------------------------------------------------------------------------


class TestSpringRequestMappingMethod:

    def test_request_mapping_method_defaults_to_get(self, tmp_path):
        """When the captured method group is 'Request', it should default to GET."""
        import code_agents.generators.api_doc_generator as mod
        # Temporarily patch the regex to also match @RequestMapping at method level
        original_re = mod._SPRING_MAPPING_RE
        patched_re = re.compile(
            r'@(Request|Get|Post|Put|Delete|Patch)Mapping\s*\('
            r'(?:[^)]*?(?:value|path)\s*=\s*)?["\']([^"\']*)["\']',
            re.IGNORECASE,
        )
        mod._SPRING_MAPPING_RE = patched_re
        try:
            src = tmp_path / "ReqController.java"
            # Class-level @RequestMapping on its own line, method-level on a different line
            src.write_text(
                '@RestController\n'
                '@RequestMapping("/api")\n'
                'public class ReqController {\n'
                '    @RequestMapping("/test")\n'
                '    public String test() { return "ok"; }\n'
                '}\n'
            )
            gen = APIDocGenerator(cwd=str(tmp_path))
            endpoints = gen.scan_endpoints()
            assert len(endpoints) == 1
            assert endpoints[0].method == "GET"
            assert endpoints[0].path == "/api/test"
        finally:
            mod._SPRING_MAPPING_RE = original_re


class TestSpringNonControllerSkipped:

    def test_java_file_without_controller_annotation_skipped(self, tmp_path):
        """A .java file without @RestController or @Controller is ignored."""
        src = tmp_path / "NotAController.java"
        src.write_text(
            'package com.example;\n'
            'public class NotAController {\n'
            '    @GetMapping("/nope")\n'
            '    public String nope() { return "nope"; }\n'
            '}\n'
        )
        gen = APIDocGenerator(cwd=str(tmp_path))
        endpoints = gen.scan_endpoints()
        assert endpoints == []


class TestSpringNoPathMapping:

    def test_spring_mapping_no_path(self, tmp_path):
        src = tmp_path / "SimpleController.java"
        src.write_text(
            '@RestController\n'
            '@RequestMapping("/api")\n'
            'public class SimpleController {\n'
            '    @GetMapping()\n'
            '    public String index() { return "ok"; }\n'
            '}\n'
        )
        gen = APIDocGenerator(cwd=str(tmp_path))
        endpoints = gen.scan_endpoints()
        assert len(endpoints) == 1
        assert endpoints[0].path == "/api"

    def test_spring_no_class_mapping(self, tmp_path):
        src = tmp_path / "NoPrefix.java"
        src.write_text(
            '@RestController\n'
            'public class NoPrefix {\n'
            '    @GetMapping("/health")\n'
            '    public String health() { return "ok"; }\n'
            '}\n'
        )
        gen = APIDocGenerator(cwd=str(tmp_path))
        endpoints = gen.scan_endpoints()
        assert len(endpoints) == 1
        assert endpoints[0].path == "/health"


# ---------------------------------------------------------------------------
# Test: OpenAPI with body params and response type
# ---------------------------------------------------------------------------


class TestOpenAPIRequestBody:

    def test_openapi_request_body_from_params(self):
        gen = APIDocGenerator(cwd="/tmp")
        gen.endpoints = [
            EndpointInfo(
                method="POST", path="/api/users",
                handler="createUser",
                parameters=[
                    EndpointParam(name="name", type="string", location="body", required=True),
                    EndpointParam(name="email", type="string", location="body", required=False),
                ],
                request_body_type="UserRequest",
            ),
        ]
        spec = gen.generate_openapi()
        post_op = spec["paths"]["/api/users"]["post"]
        assert "requestBody" in post_op
        assert post_op["requestBody"]["description"] == "UserRequest"
        schema = post_op["requestBody"]["content"]["application/json"]["schema"]
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "required" in schema
        assert "name" in schema["required"]

    def test_openapi_response_type(self):
        gen = APIDocGenerator(cwd="/tmp")
        gen.endpoints = [
            EndpointInfo(
                method="GET", path="/api/users",
                handler="getUsers",
                response_type="UserListResponse",
            ),
        ]
        spec = gen.generate_openapi()
        get_op = spec["paths"]["/api/users"]["get"]
        assert "content" in get_op["responses"]["200"]
        assert "UserListResponse" in get_op["responses"]["200"]["content"]["application/json"]["schema"]["description"]

    def test_openapi_auto_scans_if_empty(self, tmp_path):
        gen = APIDocGenerator(cwd=str(tmp_path))
        spec = gen.generate_openapi()
        assert spec["openapi"] == "3.0.3"
        assert spec["paths"] == {}


# ---------------------------------------------------------------------------
# Test: Markdown generation edge cases
# ---------------------------------------------------------------------------


class TestMarkdownEdgeCases:

    def test_markdown_with_handler_no_description(self):
        gen = APIDocGenerator(cwd="/tmp")
        gen.endpoints = [
            EndpointInfo(method="GET", path="/api/test", handler="testHandler"),
        ]
        md = gen.generate_markdown()
        assert "Handler: `testHandler()`" in md

    def test_markdown_with_path_and_query_params(self):
        gen = APIDocGenerator(cwd="/tmp")
        gen.endpoints = [
            EndpointInfo(
                method="GET", path="/api/users/{id}",
                handler="getUser",
                parameters=[
                    EndpointParam(name="id", type="integer", location="path", required=True),
                    EndpointParam(name="fields", type="string", location="query", required=False),
                ],
            ),
        ]
        md = gen.generate_markdown()
        assert "**Parameters:**" in md  # mixed path+query
        assert "| id |" in md
        assert "| fields |" in md

    def test_markdown_query_only_params(self):
        gen = APIDocGenerator(cwd="/tmp")
        gen.endpoints = [
            EndpointInfo(
                method="GET", path="/api/search",
                parameters=[
                    EndpointParam(name="q", type="string", location="query", required=False),
                ],
            ),
        ]
        md = gen.generate_markdown()
        assert "**Query Parameters:**" in md

    def test_markdown_auto_scans_if_empty(self, tmp_path):
        gen = APIDocGenerator(cwd=str(tmp_path))
        md = gen.generate_markdown()
        assert "0 endpoints discovered" in md

    def test_terminal_auto_scans_if_empty(self, tmp_path):
        gen = APIDocGenerator(cwd=str(tmp_path))
        output = gen.format_terminal()
        assert "0 endpoints discovered" in output


# ---------------------------------------------------------------------------
# Test: group_by_prefix edge cases
# ---------------------------------------------------------------------------


class TestGroupByPrefixEdge:

    def test_single_segment_path(self):
        gen = APIDocGenerator(cwd="/tmp")
        gen.endpoints = [
            EndpointInfo(method="GET", path="/health"),
        ]
        groups = gen.group_by_prefix()
        assert len(groups) == 1
        assert "Health" in list(groups.keys())[0]

    def test_root_path(self):
        gen = APIDocGenerator(cwd="/tmp")
        gen.endpoints = [
            EndpointInfo(method="GET", path="/"),
        ]
        groups = gen.group_by_prefix()
        assert "Root" in list(groups.keys())[0]


# ---------------------------------------------------------------------------
# Test: Python type conversion edge cases
# ---------------------------------------------------------------------------


class TestPythonTypeConversionEdge:

    def test_list_type(self):
        assert _python_type_to_str("List[str]") == "array"

    def test_dict_type(self):
        assert _python_type_to_str("Dict[str, str]") == "object"

    def test_decimal_type(self):
        assert _python_type_to_str("Decimal") == "number"

    def test_unknown_type(self):
        assert _python_type_to_str("CustomClass") == "string"

    def test_map_type(self):
        assert _python_type_to_str("Mapping") == "object"


# ---------------------------------------------------------------------------
# Test: Flask route with no methods specified
# ---------------------------------------------------------------------------


class TestFlaskNoMethods:

    def test_flask_default_get(self, tmp_path):
        (tmp_path / "views.py").write_text(
            'from flask import Flask\n'
            'app = Flask(__name__)\n'
            '@app.route("/status")\n'
            'def status():\n'
            '    return "ok"\n'
        )
        gen = APIDocGenerator(cwd=str(tmp_path))
        endpoints = gen.scan_endpoints()
        get_eps = [e for e in endpoints if e.path == "/status"]
        assert len(get_eps) == 1
        assert get_eps[0].method == "GET"


# ---------------------------------------------------------------------------
# Test: Terminal format with grouped endpoints
# ---------------------------------------------------------------------------


class TestTerminalFormatGrouped:

    def test_shows_handler_and_count(self):
        gen = APIDocGenerator(cwd="/tmp")
        gen.endpoints = [
            EndpointInfo(method="GET", path="/api/v1/users", handler="getUsers"),
            EndpointInfo(method="POST", path="/api/v1/users", handler="createUser"),
        ]
        output = gen.format_terminal()
        assert "2 endpoints discovered" in output
        assert "getUsers()" in output
        assert "createUser()" in output

    def test_no_handler_displayed(self):
        gen = APIDocGenerator(cwd="/tmp")
        gen.endpoints = [
            EndpointInfo(method="GET", path="/api/test"),
        ]
        output = gen.format_terminal()
        assert "1 endpoints discovered" in output
