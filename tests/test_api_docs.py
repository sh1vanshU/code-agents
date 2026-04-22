"""Tests for code_agents.api_docs — Automated API Documentation Generator."""

from __future__ import annotations

import json
import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from code_agents.api.api_docs import (
    APIDocGenerator,
    APIDocResult,
    RouteInfo,
    format_api_summary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repo directory."""
    return tmp_path


def _write(repo: Path, relpath: str, content: str) -> Path:
    """Write a file inside the repo, creating subdirs as needed."""
    fpath = repo / relpath
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(textwrap.dedent(content), encoding="utf-8")
    return fpath


# ---------------------------------------------------------------------------
# RouteInfo and APIDocResult dataclass tests
# ---------------------------------------------------------------------------


class TestRouteInfo:
    def test_defaults(self):
        r = RouteInfo(method="GET", path="/health", handler="health_check", file="app.py", line=10)
        assert r.method == "GET"
        assert r.path == "/health"
        assert r.handler == "health_check"
        assert r.file == "app.py"
        assert r.line == 10
        assert r.params == []
        assert r.request_body == ""
        assert r.response_model == ""
        assert r.docstring == ""

    def test_with_params(self):
        r = RouteInfo(
            method="POST", path="/users", handler="create_user",
            file="routes.py", line=20,
            params=[{"name": "name", "type": "string", "required": True, "default": None}],
            request_body="UserCreate",
            response_model="UserResponse",
            docstring="Create a new user.",
        )
        assert len(r.params) == 1
        assert r.request_body == "UserCreate"
        assert r.response_model == "UserResponse"
        assert r.docstring == "Create a new user."


class TestAPIDocResult:
    def test_basic(self):
        result = APIDocResult(routes=[], framework="fastapi")
        assert result.routes == []
        assert result.framework == "fastapi"
        assert result.base_url == ""

    def test_with_base_url(self):
        result = APIDocResult(routes=[], framework="express", base_url="http://localhost:3000")
        assert result.base_url == "http://localhost:3000"


# ---------------------------------------------------------------------------
# FastAPI scanning
# ---------------------------------------------------------------------------


class TestScanFastAPI:
    def test_basic_routes(self, tmp_repo):
        _write(tmp_repo, "main.py", """\
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/health")
            def health_check():
                \"\"\"Health check endpoint.\"\"\"
                return {"status": "ok"}

            @app.post("/users")
            async def create_user(name: str, email: str):
                return {"id": 1}
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()

        assert result.framework == "fastapi"
        assert len(result.routes) == 2

        get_route = [r for r in result.routes if r.method == "GET"][0]
        assert get_route.path == "/health"
        assert get_route.handler == "health_check"
        assert "Health check" in get_route.docstring

        post_route = [r for r in result.routes if r.method == "POST"][0]
        assert post_route.path == "/users"
        assert post_route.handler == "create_user"

    def test_path_params(self, tmp_repo):
        _write(tmp_repo, "api.py", """\
            from fastapi import APIRouter

            router = APIRouter()

            @router.get("/users/{user_id}")
            def get_user(user_id: int):
                pass
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()

        assert len(result.routes) == 1
        route = result.routes[0]
        assert route.path == "/users/{user_id}"
        path_params = [p for p in route.params if p.get("location") == "path"]
        assert len(path_params) == 1
        assert path_params[0]["name"] == "user_id"
        assert path_params[0]["type"] == "integer"
        assert path_params[0]["required"] is True

    def test_response_model(self, tmp_repo):
        _write(tmp_repo, "api.py", """\
            from fastapi import APIRouter

            router = APIRouter()

            @router.get("/items/{item_id}", response_model=ItemResponse)
            def get_item(item_id: int):
                pass
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()

        assert len(result.routes) == 1
        assert result.routes[0].response_model == "ItemResponse"

    def test_empty_repo(self, tmp_repo):
        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()
        assert result.routes == []
        assert result.framework == "unknown"


# ---------------------------------------------------------------------------
# Flask scanning
# ---------------------------------------------------------------------------


class TestScanFlask:
    def test_basic_routes(self, tmp_repo):
        _write(tmp_repo, "app.py", """\
            from flask import Flask

            app = Flask(__name__)

            @app.route("/hello")
            def hello():
                \"\"\"Say hello.\"\"\"
                return "Hello!"

            @app.route("/users", methods=["GET", "POST"])
            def users():
                pass
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()

        assert "flask" in result.framework
        # /hello -> GET, /users -> GET + POST
        assert len(result.routes) >= 3

        hello_routes = [r for r in result.routes if r.path == "/hello"]
        assert len(hello_routes) == 1
        assert hello_routes[0].method == "GET"

        user_routes = [r for r in result.routes if r.path == "/users"]
        methods = {r.method for r in user_routes}
        assert "GET" in methods
        assert "POST" in methods

    def test_blueprint(self, tmp_repo):
        _write(tmp_repo, "views.py", """\
            from flask import Blueprint

            bp = Blueprint("main", __name__)

            @bp.route("/api/data", methods=["GET"])
            def get_data():
                pass
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()

        assert len(result.routes) == 1
        assert result.routes[0].path == "/api/data"


# ---------------------------------------------------------------------------
# Spring Boot scanning
# ---------------------------------------------------------------------------


class TestScanSpring:
    def test_basic_controller(self, tmp_repo):
        _write(tmp_repo, "src/main/java/com/example/UserController.java", """\
            @RestController
            @RequestMapping("/api/users")
            public class UserController {

                /** Get all users. */
                @GetMapping("")
                public List<User> listUsers() {
                    return userService.findAll();
                }

                @PostMapping("/create")
                public User createUser(@RequestBody UserDto dto) {
                    return userService.create(dto);
                }

                @GetMapping("/{id}")
                public User getUser(@PathVariable Long id) {
                    return userService.findById(id);
                }
            }
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()

        assert "spring" in result.framework
        assert len(result.routes) >= 2

        get_routes = [r for r in result.routes if r.method == "GET"]
        assert any("/api/users" in r.path for r in get_routes)

        post_routes = [r for r in result.routes if r.method == "POST"]
        assert any("/api/users/create" in r.path for r in post_routes)

    def test_path_variables(self, tmp_repo):
        _write(tmp_repo, "Controller.java", """\
            @RestController
            @RequestMapping("/items")
            public class ItemController {

                @GetMapping("/{itemId}")
                public Item getItem(@PathVariable Long itemId) {
                    return itemService.find(itemId);
                }
            }
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()

        assert len(result.routes) >= 1
        route = result.routes[0]
        path_params = [p for p in route.params if p.get("location") == "path"]
        assert len(path_params) == 1
        assert path_params[0]["name"] == "itemId"
        assert path_params[0]["type"] == "integer"


# ---------------------------------------------------------------------------
# Express scanning
# ---------------------------------------------------------------------------


class TestScanExpress:
    def test_basic_routes(self, tmp_repo):
        _write(tmp_repo, "routes/index.js", """\
            const express = require('express');
            const router = express.Router();

            /** List all products */
            router.get('/products', listProducts);

            router.post('/products', createProduct);

            router.delete('/products/:id', deleteProduct);
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()

        assert "express" in result.framework
        assert len(result.routes) == 3

        methods = {r.method for r in result.routes}
        assert methods == {"GET", "POST", "DELETE"}

    def test_app_routes(self, tmp_repo):
        _write(tmp_repo, "server.ts", """\
            import express from 'express';
            const app = express();

            app.get('/api/status', (req, res) => {
                res.json({ status: 'ok' });
            });

            app.post('/api/data', handleData);
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()

        assert len(result.routes) == 2
        paths = {r.path for r in result.routes}
        assert "/api/status" in paths
        assert "/api/data" in paths

    def test_skips_dts_and_min(self, tmp_repo):
        _write(tmp_repo, "types.d.ts", """\
            app.get('/should-not-match', handler);
        """)
        _write(tmp_repo, "bundle.min.js", """\
            app.get('/should-not-match-either', handler);
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()
        assert len(result.routes) == 0


# ---------------------------------------------------------------------------
# Multi-framework detection
# ---------------------------------------------------------------------------


class TestMultiFramework:
    def test_fastapi_and_express(self, tmp_repo):
        _write(tmp_repo, "backend/main.py", """\
            from fastapi import FastAPI
            app = FastAPI()

            @app.get("/api/py/health")
            def health():
                pass
        """)
        _write(tmp_repo, "frontend/server.js", """\
            const app = require('express')();
            app.get('/api/js/health', handler);
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()

        assert "fastapi" in result.framework
        assert "express" in result.framework
        assert len(result.routes) == 2


# ---------------------------------------------------------------------------
# OpenAPI generation
# ---------------------------------------------------------------------------


class TestGenerateOpenAPI:
    def test_basic_spec(self, tmp_repo):
        _write(tmp_repo, "app.py", """\
            from fastapi import FastAPI
            app = FastAPI()

            @app.get("/items/{item_id}")
            def get_item(item_id: int, q: str):
                pass

            @app.post("/items")
            def create_item(name: str):
                pass
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()
        spec = gen.generate_openapi(result)

        assert spec["openapi"] == "3.0.3"
        assert "paths" in spec
        assert "/items/{item_id}" in spec["paths"]
        assert "get" in spec["paths"]["/items/{item_id}"]
        assert "/items" in spec["paths"]
        assert "post" in spec["paths"]["/items"]

    def test_parameters_in_spec(self, tmp_repo):
        _write(tmp_repo, "app.py", """\
            from fastapi import FastAPI
            app = FastAPI()

            @app.get("/users/{user_id}")
            def get_user(user_id: int):
                pass
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()
        spec = gen.generate_openapi(result)

        op = spec["paths"]["/users/{user_id}"]["get"]
        assert "parameters" in op
        assert op["parameters"][0]["name"] == "user_id"
        assert op["parameters"][0]["in"] == "path"
        assert op["parameters"][0]["required"] is True

    def test_empty_routes(self):
        gen = APIDocGenerator(cwd="/nonexistent")
        result = APIDocResult(routes=[], framework="unknown")
        spec = gen.generate_openapi(result)
        assert spec["openapi"] == "3.0.3"
        assert spec["paths"] == {}

    def test_base_url_in_spec(self):
        gen = APIDocGenerator(cwd="/tmp")
        result = APIDocResult(
            routes=[RouteInfo(method="GET", path="/test", handler="t", file="a.py", line=1)],
            framework="fastapi",
            base_url="https://api.example.com",
        )
        spec = gen.generate_openapi(result)
        assert spec["servers"][0]["url"] == "https://api.example.com"


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


class TestGenerateMarkdown:
    def test_basic(self, tmp_repo):
        _write(tmp_repo, "app.py", """\
            from fastapi import FastAPI
            app = FastAPI()

            @app.get("/api/health")
            def health():
                \"\"\"Health check.\"\"\"
                pass
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()
        md = gen.generate_markdown(result)

        assert "# API Documentation" in md
        assert "GET" in md
        assert "/api/health" in md
        assert "Health check" in md

    def test_empty(self):
        gen = APIDocGenerator(cwd="/tmp")
        result = APIDocResult(routes=[], framework="unknown")
        md = gen.generate_markdown(result)
        assert "0 endpoints" in md


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------


class TestGenerateHTML:
    def test_basic(self, tmp_repo):
        _write(tmp_repo, "app.py", """\
            from fastapi import FastAPI
            app = FastAPI()

            @app.get("/test")
            def test_endpoint():
                pass
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()
        html = gen.generate_html(result)

        assert "<!DOCTYPE html>" in html
        assert "/test" in html
        assert "GET" in html
        assert "1 endpoints" in html

    def test_html_escaping(self):
        gen = APIDocGenerator(cwd="/tmp")
        r = RouteInfo(
            method="GET", path="/items/<id>", handler="get_item",
            file="app.py", line=1, docstring='Query with "special" chars & <tags>',
        )
        result = APIDocResult(routes=[r], framework="test")
        html = gen.generate_html(result)
        assert "&lt;id&gt;" in html
        assert "&amp;" in html
        assert "&quot;special&quot;" in html


# ---------------------------------------------------------------------------
# format_api_summary
# ---------------------------------------------------------------------------


class TestFormatAPISummary:
    def test_with_routes(self):
        routes = [
            RouteInfo(method="GET", path="/health", handler="health", file="app.py", line=5),
            RouteInfo(method="POST", path="/users", handler="create_user", file="routes.py", line=10),
        ]
        result = APIDocResult(routes=routes, framework="fastapi")
        text = format_api_summary(result)

        assert "fastapi" in text
        assert "GET" in text
        assert "/health" in text
        assert "POST" in text
        assert "/users" in text
        assert "2 endpoint(s)" in text

    def test_no_routes(self):
        result = APIDocResult(routes=[], framework="unknown")
        text = format_api_summary(result)
        assert "No API routes" in text


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_skips_node_modules(self, tmp_repo):
        (tmp_repo / "node_modules" / "express").mkdir(parents=True)
        _write(tmp_repo, "node_modules/express/index.js", """\
            app.get('/internal', handler);
        """)
        _write(tmp_repo, "src/app.js", """\
            app.get('/real', handler);
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()

        paths = {r.path for r in result.routes}
        assert "/internal" not in paths
        assert "/real" in paths

    def test_skips_pycache(self, tmp_repo):
        (tmp_repo / "__pycache__").mkdir()
        _write(tmp_repo, "__pycache__/cached.py", """\
            @app.get("/cached")
            def cached():
                pass
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()
        assert len(result.routes) == 0

    def test_unreadable_file(self, tmp_repo):
        """Generator should not crash on files it cannot read."""
        _write(tmp_repo, "good.py", """\
            from fastapi import FastAPI
            app = FastAPI()

            @app.get("/works")
            def works():
                pass
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()
        assert len(result.routes) == 1

    def test_sort_order(self, tmp_repo):
        _write(tmp_repo, "app.py", """\
            from fastapi import FastAPI
            app = FastAPI()

            @app.post("/z-last")
            def z():
                pass

            @app.get("/a-first")
            def a():
                pass
        """)

        gen = APIDocGenerator(cwd=str(tmp_repo))
        result = gen.scan()
        assert result.routes[0].path == "/a-first"
        assert result.routes[1].path == "/z-last"
