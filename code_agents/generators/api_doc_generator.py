"""
API Documentation Generator — scan source code and generate OpenAPI/Markdown docs.

Discovers REST endpoints from Java Spring, Python FastAPI/Flask, and JS Express
source files. Extracts parameters, request bodies, response types, and docstrings.

Lazy-loaded: no heavy imports at module level.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.generators.api_doc_generator")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class EndpointParam:
    name: str
    type: str = "string"
    required: bool = True
    location: str = "path"  # path, query, body, header
    description: str = ""


@dataclass
class EndpointInfo:
    method: str  # GET, POST, PUT, DELETE, PATCH
    path: str
    handler: str = ""
    description: str = ""
    parameters: list[EndpointParam] = field(default_factory=list)
    request_body_type: str = ""
    response_type: str = ""
    file: str = ""
    line: int = 0
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns — Spring
# ---------------------------------------------------------------------------

_SPRING_MAPPING_RE = re.compile(
    r'@(Get|Post|Put|Delete|Patch)Mapping\s*\('
    r'(?:[^)]*?(?:value|path)\s*=\s*)?["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_SPRING_MAPPING_NO_PATH_RE = re.compile(
    r'@(Get|Post|Put|Delete|Patch)Mapping\s*(?:\(\s*\)|\s*$)',
)
_SPRING_CLASS_MAPPING_RE = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']'
)
_SPRING_CONTROLLER_RE = re.compile(r'@(?:Rest)?Controller')
_SPRING_PATH_VAR_RE = re.compile(
    r'@PathVariable\s*(?:\([^)]*\)\s+)?(\w+)\s+(\w+)'
)
_SPRING_REQ_PARAM_RE = re.compile(
    r'@RequestParam\s*(?:\([^)]*\)\s+)?(\w+)\s+(\w+)'
)
_SPRING_REQ_BODY_RE = re.compile(r'@RequestBody\s+(\w+)\s+(\w+)')
_SPRING_METHOD_RE = re.compile(r'(?:public|private|protected)\s+\w+(?:<[^>]+>)?\s+(\w+)\s*\(')

# ---------------------------------------------------------------------------
# Regex patterns — FastAPI
# ---------------------------------------------------------------------------

_FASTAPI_ROUTE_RE = re.compile(
    r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'
)
_FASTAPI_DEF_RE = re.compile(r'(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)')

# ---------------------------------------------------------------------------
# Regex patterns — Flask
# ---------------------------------------------------------------------------

_FLASK_ROUTE_RE = re.compile(
    r'@(?:app|blueprint|bp)\s*\.\s*route\s*\(\s*["\']([^"\']+)["\']'
    r'(?:\s*,\s*methods\s*=\s*\[([^\]]+)\])?'
)

# ---------------------------------------------------------------------------
# Regex patterns — Express (JS/TS)
# ---------------------------------------------------------------------------

_EXPRESS_ROUTE_RE = re.compile(
    r'(?:app|router)\.(get|post|put|delete|patch|all)\s*\(\s*["\']([^"\']+)["\']'
)


# ---------------------------------------------------------------------------
# Scanner class
# ---------------------------------------------------------------------------


class APIDocGenerator:
    """Scan source code for API endpoints and generate documentation."""

    def __init__(self, cwd: str | None = None):
        self.cwd = cwd or os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
        self.repo_name = Path(self.cwd).name
        self.endpoints: list[EndpointInfo] = []

    # ── Discovery ──────────────────────────────────────────────────────────

    def scan_endpoints(self) -> list[EndpointInfo]:
        """Discover all API endpoints in the repo."""
        self.endpoints = []
        repo = Path(self.cwd)

        skip_dirs = {".git", "node_modules", "target", "build", "dist",
                     "__pycache__", ".venv", "venv", ".tox", ".mypy_cache"}

        for root, dirs, files in os.walk(repo):
            # Prune skip dirs
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for fname in files:
                fpath = Path(root) / fname
                if fname.endswith(".java"):
                    self._scan_spring_file(fpath, repo)
                elif fname.endswith(".py"):
                    self._scan_python_file(fpath, repo)
                elif fname.endswith((".js", ".ts")) and not fname.endswith((".d.ts", ".min.js")):
                    self._scan_express_file(fpath, repo)

        # Sort by path then method
        self.endpoints.sort(key=lambda e: (e.path, e.method))
        logger.info("Discovered %d endpoints in %s", len(self.endpoints), self.cwd)
        return self.endpoints

    def _scan_spring_file(self, fpath: Path, repo: Path) -> None:
        """Scan a Java/Spring file for REST endpoints."""
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        if not _SPRING_CONTROLLER_RE.search(content):
            return

        # Class-level prefix
        class_prefix = ""
        cm = _SPRING_CLASS_MAPPING_RE.search(content)
        if cm:
            class_prefix = cm.group(1).rstrip("/")

        lines = content.splitlines()
        rel_file = str(fpath.relative_to(repo))

        # Find the line index of the class-level @RequestMapping so we skip it
        class_mapping_line = -1
        if cm:
            for ci, cl in enumerate(lines):
                if _SPRING_CLASS_MAPPING_RE.search(cl):
                    class_mapping_line = ci
                    break

        for i, line in enumerate(lines):
            # Skip the class-level @RequestMapping line
            if i == class_mapping_line:
                continue

            match = _SPRING_MAPPING_RE.search(line)
            endpoint_path = ""
            method_type = ""

            if match:
                method_type = match.group(1).upper()
                if method_type == "REQUEST":
                    method_type = "GET"
                endpoint_path = match.group(2)
            else:
                no_path = _SPRING_MAPPING_NO_PATH_RE.search(line)
                if no_path:
                    method_type = no_path.group(1).upper()
                    endpoint_path = ""
                else:
                    continue

            if endpoint_path:
                full_path = class_prefix + "/" + endpoint_path.lstrip("/")
            else:
                full_path = class_prefix or "/"
            full_path = "/" + full_path.lstrip("/")

            # Extract handler name and params from method signature
            handler = ""
            params = []
            body_type = ""
            # Look at next few lines until we hit another annotation or closing brace
            end_idx = min(i + 8, len(lines))
            for j in range(i + 1, end_idx):
                stripped = lines[j].strip()
                if stripped.startswith("@") and not stripped.startswith("@Path") and not stripped.startswith("@Request"):
                    end_idx = j
                    break
            chunk = "\n".join(lines[i:end_idx])

            meth_match = _SPRING_METHOD_RE.search(chunk)
            if meth_match:
                handler = meth_match.group(1)

            # Path variables — deduplicate by name
            seen_params = set()
            for pv in _SPRING_PATH_VAR_RE.finditer(chunk):
                ptype = pv.group(1) or "String"
                pname = pv.group(2) or "id"
                if pname not in seen_params:
                    seen_params.add(pname)
                    params.append(EndpointParam(
                        name=pname, type=_java_type_to_str(ptype),
                        location="path", required=True,
                    ))

            # Query params
            for rp in _SPRING_REQ_PARAM_RE.finditer(chunk):
                ptype = rp.group(1) or "String"
                pname = rp.group(2) or "param"
                params.append(EndpointParam(
                    name=pname, type=_java_type_to_str(ptype),
                    location="query", required=False,
                ))

            # Request body
            rb = _SPRING_REQ_BODY_RE.search(chunk)
            if rb:
                body_type = rb.group(1)

            # Extract description from Javadoc above the annotation
            description = _extract_javadoc(lines, i)

            self.endpoints.append(EndpointInfo(
                method=method_type,
                path=full_path,
                handler=handler,
                description=description,
                parameters=params,
                request_body_type=body_type,
                file=rel_file,
                line=i + 1,
            ))

    def _scan_python_file(self, fpath: Path, repo: Path) -> None:
        """Scan a Python file for FastAPI/Flask endpoints."""
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        lines = content.splitlines()
        rel_file = str(fpath.relative_to(repo))

        # FastAPI routes
        for i, line in enumerate(lines):
            match = _FASTAPI_ROUTE_RE.search(line)
            if match:
                method = match.group(1).upper()
                path = match.group(2)

                # Get the def on next lines
                handler = ""
                params = []
                for j in range(i + 1, min(i + 5, len(lines))):
                    def_match = _FASTAPI_DEF_RE.search(lines[j])
                    if def_match:
                        handler = def_match.group(1)
                        raw_params = def_match.group(2)
                        params = _parse_python_params(raw_params, path)
                        break

                description = _extract_python_docstring(lines, i)

                self.endpoints.append(EndpointInfo(
                    method=method, path=path, handler=handler,
                    description=description, parameters=params,
                    file=rel_file, line=i + 1,
                ))

        # Flask routes
        for i, line in enumerate(lines):
            match = _FLASK_ROUTE_RE.search(line)
            if match:
                path = match.group(1)
                methods_str = match.group(2)
                if methods_str:
                    methods = [m.strip().strip("'\"").upper() for m in methods_str.split(",")]
                else:
                    methods = ["GET"]

                handler = ""
                for j in range(i + 1, min(i + 5, len(lines))):
                    def_match = _FASTAPI_DEF_RE.search(lines[j])
                    if def_match:
                        handler = def_match.group(1)
                        break

                description = _extract_python_docstring(lines, i)

                for method in methods:
                    self.endpoints.append(EndpointInfo(
                        method=method, path=path, handler=handler,
                        description=description, file=rel_file, line=i + 1,
                    ))

    def _scan_express_file(self, fpath: Path, repo: Path) -> None:
        """Scan a JS/TS file for Express endpoints."""
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        lines = content.splitlines()
        rel_file = str(fpath.relative_to(repo))

        for i, line in enumerate(lines):
            match = _EXPRESS_ROUTE_RE.search(line)
            if match:
                method = match.group(1).upper()
                path = match.group(2)

                # Try to extract handler name from next function/arrow
                handler = _extract_express_handler(lines, i)
                description = _extract_js_jsdoc(lines, i)

                self.endpoints.append(EndpointInfo(
                    method=method, path=path, handler=handler,
                    description=description, file=rel_file, line=i + 1,
                ))

    # ── Grouping ──────────────────────────────────────────────────────────

    def group_by_prefix(self) -> dict[str, list[EndpointInfo]]:
        """Group endpoints by common path prefix (first 2 segments)."""
        groups: dict[str, list[EndpointInfo]] = {}
        for ep in self.endpoints:
            parts = [p for p in ep.path.split("/") if p]
            if len(parts) >= 2:
                prefix = parts[0] + "/" + parts[1]
            elif parts:
                prefix = parts[0]
            else:
                prefix = "root"
            key = prefix.replace("-", " ").replace("_", " ").title()
            groups.setdefault(key, []).append(ep)
        return groups

    # ── OpenAPI generation ─────────────────────────────────────────────────

    def generate_openapi(self) -> dict:
        """Generate an OpenAPI 3.0 spec from discovered endpoints."""
        if not self.endpoints:
            self.scan_endpoints()

        spec: dict = {
            "openapi": "3.0.3",
            "info": {
                "title": f"{self.repo_name} API",
                "version": "1.0.0",
                "description": f"Auto-generated API documentation for {self.repo_name}",
            },
            "paths": {},
        }

        for ep in self.endpoints:
            path_key = ep.path
            if path_key not in spec["paths"]:
                spec["paths"][path_key] = {}

            operation: dict = {
                "summary": ep.description or ep.handler or f"{ep.method} {ep.path}",
                "operationId": ep.handler or f"{ep.method.lower()}_{ep.path.replace('/', '_')}",
                "responses": {
                    "200": {"description": "Successful response"},
                },
            }

            # Parameters
            params = []
            for p in ep.parameters:
                if p.location in ("path", "query", "header"):
                    params.append({
                        "name": p.name,
                        "in": p.location,
                        "required": p.required,
                        "schema": {"type": p.type},
                        "description": p.description,
                    })
            if params:
                operation["parameters"] = params

            # Request body
            body_params = [p for p in ep.parameters if p.location == "body"]
            if body_params or ep.request_body_type:
                properties = {}
                required_fields = []
                for bp in body_params:
                    properties[bp.name] = {"type": bp.type}
                    if bp.required:
                        required_fields.append(bp.name)

                schema: dict = {"type": "object"}
                if properties:
                    schema["properties"] = properties
                if required_fields:
                    schema["required"] = required_fields

                operation["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": schema,
                        },
                    },
                }
                if ep.request_body_type:
                    operation["requestBody"]["description"] = ep.request_body_type

            if ep.response_type:
                operation["responses"]["200"]["content"] = {
                    "application/json": {
                        "schema": {"type": "object", "description": ep.response_type},
                    },
                }

            spec["paths"][path_key][ep.method.lower()] = operation

        return spec

    # ── Markdown generation ────────────────────────────────────────────────

    def generate_markdown(self) -> str:
        """Generate markdown API documentation."""
        if not self.endpoints:
            self.scan_endpoints()

        lines = [f"# API Documentation -- {self.repo_name}", ""]
        lines.append(f"> {len(self.endpoints)} endpoints discovered")
        lines.append("")

        groups = self.group_by_prefix()
        for group_name, endpoints in sorted(groups.items()):
            lines.append(f"## {group_name}")
            lines.append("")

            for ep in endpoints:
                lines.append(f"### {ep.method} {ep.path}")
                if ep.description:
                    lines.append(ep.description)
                elif ep.handler:
                    lines.append(f"Handler: `{ep.handler}()`")
                lines.append("")

                # Path/query params
                path_query_params = [p for p in ep.parameters if p.location in ("path", "query")]
                if path_query_params:
                    param_label = "Path Parameters" if any(p.location == "path" for p in path_query_params) else "Query Parameters"
                    if any(p.location == "path" for p in path_query_params) and any(p.location == "query" for p in path_query_params):
                        param_label = "Parameters"
                    lines.append(f"**{param_label}:**")
                    lines.append("| Parameter | Type | Location | Required | Description |")
                    lines.append("|-----------|------|----------|----------|-------------|")
                    for p in path_query_params:
                        req = "yes" if p.required else "no"
                        lines.append(f"| {p.name} | {p.type} | {p.location} | {req} | {p.description} |")
                    lines.append("")

                # Request body
                if ep.request_body_type:
                    lines.append(f"**Request Body:** `{ep.request_body_type}`")
                    lines.append("")

                # File reference
                if ep.file:
                    lines.append(f"*Source: `{ep.file}:{ep.line}`*")
                    lines.append("")

        return "\n".join(lines)

    # ── Terminal display ──────────────────────────────────────────────────

    def format_terminal(self) -> str:
        """Compact terminal display of endpoints."""
        if not self.endpoints:
            self.scan_endpoints()

        lines = [
            "",
            f"  API Documentation -- {self.repo_name}",
            "  " + "=" * (22 + len(self.repo_name)),
            "",
            f"  {len(self.endpoints)} endpoints discovered",
            "",
        ]

        groups = self.group_by_prefix()
        for group_name, endpoints in sorted(groups.items()):
            lines.append(f"  {group_name} ({len(endpoints)} endpoints):")
            for ep in endpoints:
                handler_str = f"-> {ep.handler}()" if ep.handler else ""
                lines.append(f"    {ep.method:<7} {ep.path:<40} {handler_str}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper functions (module-level, private)
# ---------------------------------------------------------------------------


def _java_type_to_str(t: str) -> str:
    """Convert Java types to JSON schema type strings."""
    mapping = {
        "String": "string", "string": "string",
        "Long": "integer", "long": "integer",
        "Integer": "integer", "int": "integer",
        "Double": "number", "double": "number",
        "Float": "number", "float": "number",
        "Boolean": "boolean", "boolean": "boolean",
        "BigDecimal": "number",
    }
    return mapping.get(t, "string")


def _extract_javadoc(lines: list[str], annotation_line: int) -> str:
    """Extract Javadoc comment above an annotation line."""
    # Walk backwards from annotation to find /** ... */
    desc = ""
    for j in range(annotation_line - 1, max(annotation_line - 20, -1), -1):
        stripped = lines[j].strip()
        if stripped.startswith("*/"):
            continue
        if stripped.startswith("/**"):
            # Collect description lines
            parts = []
            for k in range(j, annotation_line):
                s = lines[k].strip().lstrip("/*").strip()
                if s and not s.startswith("@"):
                    parts.append(s)
            desc = " ".join(parts)
            break
        if stripped and not stripped.startswith("*") and not stripped.startswith("@"):
            break
    return desc


def _extract_python_docstring(lines: list[str], decorator_line: int) -> str:
    """Extract docstring from the function after a decorator."""
    for j in range(decorator_line + 1, min(decorator_line + 10, len(lines))):
        stripped = lines[j].strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            if stripped.count(quote) >= 2:
                # Single-line docstring
                return stripped.strip(quote[0]).strip()
            # Multi-line: collect until closing
            parts = [stripped.lstrip(quote[0]).strip()]
            for k in range(j + 1, min(j + 20, len(lines))):
                if quote in lines[k]:
                    parts.append(lines[k].strip().rstrip(quote[0]).strip())
                    break
                parts.append(lines[k].strip())
            return " ".join(p for p in parts if p)
        if stripped.startswith("def ") or stripped.startswith("async def"):
            continue
        if stripped and not stripped.startswith("@"):
            break
    return ""


def _parse_python_params(raw: str, path: str) -> list[EndpointParam]:
    """Parse Python function parameters into EndpointParam list."""
    params = []
    # Extract path params from route pattern {param}
    path_params = set(re.findall(r'\{(\w+)\}', path))

    for part in raw.split(","):
        part = part.strip()
        if not part or part in ("self", "request", "db", "session"):
            continue
        # Skip dependency injection
        if "Depends(" in part or "=" in part and "Query(" not in part and "Path(" not in part:
            continue

        name = part.split(":")[0].strip()
        type_hint = "string"
        if ":" in part:
            raw_type = part.split(":")[1].strip().split("=")[0].strip()
            type_hint = _python_type_to_str(raw_type)

        location = "path" if name in path_params else "query"
        params.append(EndpointParam(
            name=name, type=type_hint,
            location=location, required=name in path_params,
        ))
    return params


def _python_type_to_str(t: str) -> str:
    """Convert Python type hints to JSON schema type strings."""
    t_lower = t.lower()
    if "int" in t_lower:
        return "integer"
    if "float" in t_lower or "decimal" in t_lower:
        return "number"
    if "bool" in t_lower:
        return "boolean"
    if "list" in t_lower or "array" in t_lower:
        return "array"
    if "dict" in t_lower or "map" in t_lower:
        return "object"
    return "string"


def _extract_express_handler(lines: list[str], route_line: int) -> str:
    """Extract Express handler name from route definition."""
    line = lines[route_line]
    # app.get('/path', handlerName)  or  router.get('/path', handlerName);
    parts = line.split(",")
    if len(parts) >= 2:
        handler = parts[-1].strip().rstrip(";").rstrip(")").strip()
        if handler.isidentifier():
            return handler
    # Inline: app.get('/path', (req, res) => { ... })  or function name
    func_match = re.search(r'function\s+(\w+)', line)
    if func_match:
        return func_match.group(1)
    return ""


def _extract_js_jsdoc(lines: list[str], route_line: int) -> str:
    """Extract JSDoc comment above a route definition."""
    desc = ""
    for j in range(route_line - 1, max(route_line - 15, -1), -1):
        stripped = lines[j].strip()
        if stripped == "*/":
            continue
        if stripped.startswith("/**"):
            parts = []
            for k in range(j, route_line):
                s = lines[k].strip().lstrip("/*").strip()
                if s and not s.startswith("@"):
                    parts.append(s)
            desc = " ".join(parts)
            break
        if stripped and not stripped.startswith("*") and not stripped.startswith("//"):
            break
    return desc
