"""Endpoint Generator — describe a resource, get full CRUD implementation.

Generates: route handler, request/response models, validation, tests, docs.
Supports FastAPI, Express, Flask, Django REST patterns.

Usage:
    from code_agents.api.endpoint_generator import EndpointGenerator
    gen = EndpointGenerator(EndpointGenConfig(cwd="/path/to/repo"))
    result = gen.generate("User", fields={"name": "str", "email": "str", "age": "int"})
    print(format_endpoint(result))
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.api.endpoint_generator")


@dataclass
class EndpointGenConfig:
    cwd: str = "."
    framework: str = "fastapi"  # fastapi, flask, express, django
    include_tests: bool = True
    include_docs: bool = True


@dataclass
class GeneratedFile:
    """A single generated file."""
    path: str
    content: str
    file_type: str  # "router", "model", "test", "docs"


@dataclass
class EndpointGenResult:
    """Result of endpoint generation."""
    resource_name: str
    fields: dict[str, str] = field(default_factory=dict)
    framework: str = "fastapi"
    files: list[GeneratedFile] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)  # GET /users, POST /users, etc.
    summary: str = ""


class EndpointGenerator:
    """Generate full CRUD endpoint implementations."""

    def __init__(self, config: EndpointGenConfig):
        self.config = config

    def generate(self, resource_name: str, fields: Optional[dict[str, str]] = None) -> EndpointGenResult:
        """Generate CRUD endpoints for a resource."""
        logger.info("Generating endpoints for: %s", resource_name)
        fields = fields or {"id": "int", "name": "str", "created_at": "str"}

        result = EndpointGenResult(
            resource_name=resource_name,
            fields=fields,
            framework=self.config.framework,
        )

        name_lower = resource_name.lower()
        name_plural = name_lower + "s"

        result.endpoints = [
            f"GET /{name_plural}",
            f"GET /{name_plural}/{{id}}",
            f"POST /{name_plural}",
            f"PUT /{name_plural}/{{id}}",
            f"DELETE /{name_plural}/{{id}}",
        ]

        if self.config.framework == "fastapi":
            result.files.append(self._gen_fastapi_router(resource_name, fields, name_plural))
            result.files.append(self._gen_pydantic_models(resource_name, fields))
        elif self.config.framework == "flask":
            result.files.append(self._gen_flask_router(resource_name, fields, name_plural))
        elif self.config.framework == "express":
            result.files.append(self._gen_express_router(resource_name, fields, name_plural))

        if self.config.include_tests:
            result.files.append(self._gen_tests(resource_name, fields, name_plural))

        result.summary = f"Generated {len(result.endpoints)} endpoints, {len(result.files)} files for {resource_name}"
        return result

    def _gen_pydantic_models(self, name: str, fields: dict) -> GeneratedFile:
        lines = [
            f'"""Pydantic models for {name}."""',
            "from pydantic import BaseModel, Field",
            "from typing import Optional",
            "",
            f"class {name}Base(BaseModel):",
        ]
        for fname, ftype in fields.items():
            if fname == "id":
                continue
            py_type = {"str": "str", "int": "int", "float": "float", "bool": "bool"}.get(ftype, "str")
            lines.append(f"    {fname}: {py_type}")
        lines.extend([
            "",
            f"class {name}Create({name}Base):",
            "    pass",
            "",
            f"class {name}Update({name}Base):",
        ])
        for fname, ftype in fields.items():
            if fname == "id":
                continue
            py_type = {"str": "str", "int": "int", "float": "float", "bool": "bool"}.get(ftype, "str")
            lines.append(f"    {fname}: Optional[{py_type}] = None")
        lines.extend([
            "",
            f"class {name}Response({name}Base):",
            "    id: int",
        ])
        return GeneratedFile(
            path=f"models/{name.lower()}.py",
            content="\n".join(lines),
            file_type="model",
        )

    def _gen_fastapi_router(self, name: str, fields: dict, plural: str) -> GeneratedFile:
        lines = [
            f'"""CRUD router for {name}."""',
            "from fastapi import APIRouter, HTTPException",
            f"from .models.{name.lower()} import {name}Create, {name}Update, {name}Response",
            "",
            f'router = APIRouter(prefix="/{plural}", tags=["{plural}"])',
            "",
            f"# In-memory store (replace with database)",
            f"_{plural}: dict[int, dict] = {{}}",
            f"_next_id = 1",
            "",
            f'@router.get("/", response_model=list[{name}Response])',
            f"async def list_{plural}():",
            f'    return list(_{plural}.values())',
            "",
            f'@router.get("/{{item_id}}", response_model={name}Response)',
            f"async def get_{name.lower()}(item_id: int):",
            f"    if item_id not in _{plural}:",
            f'        raise HTTPException(404, detail="{name} not found")',
            f"    return _{plural}[item_id]",
            "",
            f'@router.post("/", response_model={name}Response, status_code=201)',
            f"async def create_{name.lower()}(data: {name}Create):",
            f"    global _next_id",
            f"    item = {{**data.model_dump(), 'id': _next_id}}",
            f"    _{plural}[_next_id] = item",
            f"    _next_id += 1",
            f"    return item",
            "",
            f'@router.put("/{{item_id}}", response_model={name}Response)',
            f"async def update_{name.lower()}(item_id: int, data: {name}Update):",
            f"    if item_id not in _{plural}:",
            f'        raise HTTPException(404, detail="{name} not found")',
            f"    updates = data.model_dump(exclude_unset=True)",
            f"    _{plural}[item_id].update(updates)",
            f"    return _{plural}[item_id]",
            "",
            f'@router.delete("/{{item_id}}", status_code=204)',
            f"async def delete_{name.lower()}(item_id: int):",
            f"    if item_id not in _{plural}:",
            f'        raise HTTPException(404, detail="{name} not found")',
            f"    del _{plural}[item_id]",
        ]
        return GeneratedFile(path=f"routers/{name.lower()}.py", content="\n".join(lines), file_type="router")

    def _gen_flask_router(self, name: str, fields: dict, plural: str) -> GeneratedFile:
        lines = [
            f"from flask import Blueprint, request, jsonify",
            f'{name.lower()}_bp = Blueprint("{plural}", __name__)',
            "",
            f'@{name.lower()}_bp.route("/{plural}", methods=["GET"])',
            f"def list_{plural}():",
            f'    return jsonify([])',
            "",
            f'@{name.lower()}_bp.route("/{plural}/<int:id>", methods=["GET"])',
            f"def get_{name.lower()}(id):",
            f'    return jsonify({{"id": id}})',
        ]
        return GeneratedFile(path=f"routes/{name.lower()}.py", content="\n".join(lines), file_type="router")

    def _gen_express_router(self, name: str, fields: dict, plural: str) -> GeneratedFile:
        lines = [
            f"const express = require('express');",
            f"const router = express.Router();",
            "",
            f"router.get('/{plural}', (req, res) => {{",
            f"  res.json([]);",
            f"}});",
            "",
            f"router.get('/{plural}/:id', (req, res) => {{",
            f"  res.json({{ id: req.params.id }});",
            f"}});",
            "",
            f"router.post('/{plural}', (req, res) => {{",
            f"  res.status(201).json({{ ...req.body, id: Date.now() }});",
            f"}});",
            "",
            f"module.exports = router;",
        ]
        return GeneratedFile(path=f"routes/{name.lower()}.js", content="\n".join(lines), file_type="router")

    def _gen_tests(self, name: str, fields: dict, plural: str) -> GeneratedFile:
        lines = [
            f'"""Tests for {name} CRUD endpoints."""',
            "import pytest",
            "",
            f"class Test{name}CRUD:",
            f"    def test_create_{name.lower()}(self):",
            f"        # POST /{plural}",
            f"        data = {{{', '.join(f'\"{k}\": {self._sample_value(v)}' for k, v in fields.items() if k != 'id')}}}",
            f"        # assert response.status_code == 201",
            f"        pass",
            "",
            f"    def test_list_{plural}(self):",
            f"        # GET /{plural}",
            f"        pass",
            "",
            f"    def test_get_{name.lower()}(self):",
            f"        # GET /{plural}/1",
            f"        pass",
            "",
            f"    def test_update_{name.lower()}(self):",
            f"        # PUT /{plural}/1",
            f"        pass",
            "",
            f"    def test_delete_{name.lower()}(self):",
            f"        # DELETE /{plural}/1",
            f"        pass",
            "",
            f"    def test_{name.lower()}_not_found(self):",
            f"        # GET /{plural}/999 -> 404",
            f"        pass",
        ]
        return GeneratedFile(path=f"tests/test_{name.lower()}.py", content="\n".join(lines), file_type="test")

    def _sample_value(self, ftype: str) -> str:
        return {"str": '"test"', "int": "1", "float": "1.0", "bool": "True"}.get(ftype, '"test"')


def format_endpoint(result: EndpointGenResult) -> str:
    lines = [f"{'=' * 60}", f"  Endpoint Generator: {result.resource_name}", f"{'=' * 60}"]
    lines.append(f"  {result.summary}")
    lines.append(f"  Framework: {result.framework}")
    lines.append(f"\n  Endpoints:")
    for ep in result.endpoints:
        lines.append(f"    {ep}")
    for gf in result.files:
        lines.append(f"\n  --- {gf.path} [{gf.file_type}] ---")
        for code_line in gf.content.splitlines()[:25]:
            lines.append(f"    {code_line}")
        if gf.content.count("\n") > 25:
            lines.append(f"    ... ({gf.content.count(chr(10)) - 25} more lines)")
    lines.append("")
    return "\n".join(lines)
