"""
Automated API Documentation Generator — scan repos for API routes, generate OpenAPI/Markdown/HTML.

Supports FastAPI, Flask, Spring Boot, and Express via pure regex scanning.
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

logger = logging.getLogger("code_agents.api.api_docs")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class RouteInfo:
    method: str
    path: str
    handler: str
    file: str
    line: int
    params: list[dict] = field(default_factory=list)  # [{name, type, required, default}]
    request_body: str = ""
    response_model: str = ""
    docstring: str = ""


@dataclass
class APIDocResult:
    routes: list[RouteInfo]
    framework: str
    base_url: str = ""


# ---------------------------------------------------------------------------
# Regex patterns — FastAPI
# ---------------------------------------------------------------------------

_FASTAPI_ROUTE_RE = re.compile(
    r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'
)
_FASTAPI_DEF_RE = re.compile(r'(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)')
_FASTAPI_RESPONSE_MODEL_RE = re.compile(r'response_model\s*=\s*(\w+)')

# ---------------------------------------------------------------------------
# Regex patterns — Flask
# ---------------------------------------------------------------------------

_FLASK_ROUTE_RE = re.compile(
    r'@(?:app|blueprint|bp)\s*\.\s*route\s*\(\s*["\']([^"\']+)["\']'
    r'(?:\s*,\s*methods\s*=\s*\[([^\]]+)\])?'
)

# ---------------------------------------------------------------------------
# Regex patterns — Spring Boot
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
_SPRING_METHOD_RE = re.compile(r'(?:public|private|protected)\s+(\w+(?:<[^>]+>)?)\s+(\w+)\s*\(')

# ---------------------------------------------------------------------------
# Regex patterns — Express (JS/TS)
# ---------------------------------------------------------------------------

_EXPRESS_ROUTE_RE = re.compile(
    r'(?:app|router)\.(get|post|put|delete|patch|all)\s*\(\s*["\']([^"\']+)["\']'
)

# ---------------------------------------------------------------------------
# Skip directories
# ---------------------------------------------------------------------------

_SKIP_DIRS = {
    ".git", "node_modules", "target", "build", "dist",
    "__pycache__", ".venv", "venv", ".tox", ".mypy_cache",
    ".eggs", ".pytest_cache", "vendor", "bower_components",
}


# ---------------------------------------------------------------------------
# APIDocGenerator
# ---------------------------------------------------------------------------


class APIDocGenerator:
    """Scan source code for API routes across frameworks, generate OpenAPI/Markdown/HTML."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.repo_name = Path(cwd).name
        self._routes: list[RouteInfo] = []
        self._framework: str = ""

    # ── Main entry point ─────────────────────────────────────────────────

    def scan(self) -> APIDocResult:
        """Scan the repo for API routes. Auto-detects framework."""
        self._routes = []
        self._framework = ""

        fastapi_routes = self._scan_fastapi()
        flask_routes = self._scan_flask()
        spring_routes = self._scan_spring()
        express_routes = self._scan_express()

        # Pick the framework with most routes, or combine
        all_routes: list[RouteInfo] = []
        frameworks: list[str] = []

        if fastapi_routes:
            all_routes.extend(fastapi_routes)
            frameworks.append("fastapi")
        if flask_routes:
            all_routes.extend(flask_routes)
            frameworks.append("flask")
        if spring_routes:
            all_routes.extend(spring_routes)
            frameworks.append("spring")
        if express_routes:
            all_routes.extend(express_routes)
            frameworks.append("express")

        self._framework = "+".join(frameworks) if frameworks else "unknown"
        all_routes.sort(key=lambda r: (r.path, r.method))
        self._routes = all_routes

        logger.info("Scanned %d routes (%s) in %s", len(all_routes), self._framework, self.cwd)

        return APIDocResult(
            routes=all_routes,
            framework=self._framework,
            base_url="",
        )

    # ── OpenAPI generation ───────────────────────────────────────────────

    def generate_openapi(self, result: APIDocResult) -> dict:
        """Generate an OpenAPI 3.0.3 spec dict from scan results."""
        spec: dict = {
            "openapi": "3.0.3",
            "info": {
                "title": f"{self.repo_name} API",
                "version": "1.0.0",
                "description": f"Auto-generated API documentation for {self.repo_name}",
            },
            "paths": {},
        }

        if result.base_url:
            spec["servers"] = [{"url": result.base_url}]

        for route in result.routes:
            path_key = route.path or "/"
            if path_key not in spec["paths"]:
                spec["paths"][path_key] = {}

            operation: dict = {
                "summary": route.docstring or route.handler or f"{route.method} {route.path}",
                "operationId": route.handler or f"{route.method.lower()}_{route.path.replace('/', '_').strip('_')}",
                "responses": {
                    "200": {"description": "Successful response"},
                },
            }

            # Parameters
            params = []
            for p in route.params:
                loc = p.get("location", "query")
                if loc in ("path", "query", "header"):
                    param_entry: dict = {
                        "name": p["name"],
                        "in": loc,
                        "required": p.get("required", False),
                        "schema": {"type": p.get("type", "string")},
                    }
                    if p.get("default") is not None:
                        param_entry["schema"]["default"] = p["default"]
                    params.append(param_entry)
            if params:
                operation["parameters"] = params

            # Request body
            body_params = [p for p in route.params if p.get("location") == "body"]
            if body_params or route.request_body:
                properties = {}
                required_fields = []
                for bp in body_params:
                    properties[bp["name"]] = {"type": bp.get("type", "string")}
                    if bp.get("required"):
                        required_fields.append(bp["name"])

                schema: dict = {"type": "object"}
                if properties:
                    schema["properties"] = properties
                if required_fields:
                    schema["required"] = required_fields

                operation["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {"schema": schema},
                    },
                }
                if route.request_body:
                    operation["requestBody"]["description"] = route.request_body

            # Response model
            if route.response_model:
                operation["responses"]["200"]["content"] = {
                    "application/json": {
                        "schema": {"type": "object", "description": route.response_model},
                    },
                }

            spec["paths"][path_key][route.method.lower()] = operation

        return spec

    # ── Markdown generation ──────────────────────────────────────────────

    def generate_markdown(self, result: APIDocResult) -> str:
        """Generate Markdown documentation from scan results."""
        lines = [
            f"# API Documentation -- {self.repo_name}",
            "",
            f"> {len(result.routes)} endpoints discovered | Framework: {result.framework}",
            "",
        ]

        groups = self._group_routes(result.routes)
        for group_name, routes in sorted(groups.items()):
            lines.append(f"## {group_name}")
            lines.append("")

            for r in routes:
                lines.append(f"### {r.method} `{r.path}`")
                if r.docstring:
                    lines.append(f"\n{r.docstring}")
                elif r.handler:
                    lines.append(f"\nHandler: `{r.handler}()`")
                lines.append("")

                pq_params = [p for p in r.params if p.get("location") in ("path", "query")]
                if pq_params:
                    lines.append("| Parameter | Type | Location | Required | Default |")
                    lines.append("|-----------|------|----------|----------|---------|")
                    for p in pq_params:
                        req = "yes" if p.get("required") else "no"
                        default = p.get("default", "-") or "-"
                        lines.append(
                            f"| {p['name']} | {p.get('type', 'string')} "
                            f"| {p.get('location', 'query')} | {req} | {default} |"
                        )
                    lines.append("")

                if r.request_body:
                    lines.append(f"**Request Body:** `{r.request_body}`")
                    lines.append("")
                if r.response_model:
                    lines.append(f"**Response:** `{r.response_model}`")
                    lines.append("")

                if r.file:
                    lines.append(f"*Source: `{r.file}:{r.line}`*")
                    lines.append("")

        return "\n".join(lines)

    # ── HTML generation (Swagger-like) ───────────────────────────────────

    def generate_html(self, result: APIDocResult) -> str:
        """Generate a self-contained Swagger-like HTML page from scan results."""
        method_colors = {
            "GET": "#61affe",
            "POST": "#49cc90",
            "PUT": "#fca130",
            "DELETE": "#f93e3e",
            "PATCH": "#50e3c2",
        }

        endpoint_rows = []
        for r in result.routes:
            color = method_colors.get(r.method.upper(), "#999")
            params_html = ""
            if r.params:
                param_items = []
                for p in r.params:
                    req_badge = '<span style="color:red">*</span>' if p.get("required") else ""
                    param_items.append(
                        f'<li><code>{p["name"]}</code> ({p.get("type", "string")}, '
                        f'{p.get("location", "query")}) {req_badge}</li>'
                    )
                params_html = f'<ul>{"".join(param_items)}</ul>'

            body_html = ""
            if r.request_body:
                body_html = f'<div class="body">Request Body: <code>{_html_escape(r.request_body)}</code></div>'

            resp_html = ""
            if r.response_model:
                resp_html = f'<div class="resp">Response: <code>{_html_escape(r.response_model)}</code></div>'

            doc_html = ""
            if r.docstring:
                doc_html = f'<p class="doc">{_html_escape(r.docstring)}</p>'

            source_html = ""
            if r.file:
                source_html = f'<span class="source">{_html_escape(r.file)}:{r.line}</span>'

            endpoint_rows.append(f"""
        <div class="endpoint">
          <div class="method" style="background:{color}">{r.method.upper()}</div>
          <div class="path">{_html_escape(r.path)}</div>
          <div class="handler">{_html_escape(r.handler)}</div>
          {source_html}
          {doc_html}
          {params_html}
          {body_html}
          {resp_html}
        </div>""")

        endpoints_html = "\n".join(endpoint_rows)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html_escape(self.repo_name)} API Documentation</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         margin: 0; padding: 20px 40px; background: #fafafa; color: #333; }}
  h1 {{ border-bottom: 2px solid #3b4151; padding-bottom: 10px; }}
  .meta {{ color: #888; margin-bottom: 24px; }}
  .endpoint {{ display: flex; flex-wrap: wrap; align-items: flex-start; gap: 10px;
               background: #fff; border: 1px solid #ddd; border-radius: 4px;
               padding: 12px 16px; margin-bottom: 8px; }}
  .method {{ font-weight: bold; color: #fff; padding: 4px 10px; border-radius: 3px;
             font-size: 13px; min-width: 60px; text-align: center; flex-shrink: 0; }}
  .path {{ font-family: monospace; font-size: 15px; font-weight: 600; flex: 1; }}
  .handler {{ color: #666; font-size: 13px; }}
  .source {{ font-size: 12px; color: #aaa; width: 100%; }}
  .doc {{ font-size: 13px; color: #555; width: 100%; margin: 4px 0 0; }}
  ul {{ font-size: 13px; padding-left: 20px; margin: 4px 0; width: 100%; }}
  .body, .resp {{ font-size: 13px; color: #555; width: 100%; }}
  code {{ background: #f0f0f0; padding: 1px 4px; border-radius: 2px; }}
</style>
</head>
<body>
<h1>{_html_escape(self.repo_name)} API Documentation</h1>
<div class="meta">{len(result.routes)} endpoints | Framework: {_html_escape(result.framework)}</div>
{endpoints_html}
</body>
</html>"""

    # ── Framework scanners ───────────────────────────────────────────────

    def _scan_fastapi(self) -> list[RouteInfo]:
        """Scan for FastAPI @app.get / @router.post patterns."""
        routes: list[RouteInfo] = []
        repo = Path(self.cwd)

        for fpath in self._iter_files(".py"):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            lines = content.splitlines()
            rel_file = str(fpath.relative_to(repo))

            for i, line in enumerate(lines):
                match = _FASTAPI_ROUTE_RE.search(line)
                if not match:
                    continue

                method = match.group(1).upper()
                path = match.group(2)

                # Response model from decorator
                response_model = ""
                rm_match = _FASTAPI_RESPONSE_MODEL_RE.search(line)
                if rm_match:
                    response_model = rm_match.group(1)

                # Find the def on next lines
                handler = ""
                params: list[dict] = []
                for j in range(i + 1, min(i + 6, len(lines))):
                    def_match = _FASTAPI_DEF_RE.search(lines[j])
                    if def_match:
                        handler = def_match.group(1)
                        raw_params = def_match.group(2)
                        params = _parse_python_params(raw_params, path)
                        break

                docstring = _extract_python_docstring(lines, i)

                routes.append(RouteInfo(
                    method=method, path=path, handler=handler,
                    file=rel_file, line=i + 1,
                    params=params, request_body="",
                    response_model=response_model, docstring=docstring,
                ))

        return routes

    def _scan_flask(self) -> list[RouteInfo]:
        """Scan for Flask @app.route patterns."""
        routes: list[RouteInfo] = []
        repo = Path(self.cwd)

        for fpath in self._iter_files(".py"):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            lines = content.splitlines()
            rel_file = str(fpath.relative_to(repo))

            for i, line in enumerate(lines):
                match = _FLASK_ROUTE_RE.search(line)
                if not match:
                    continue

                path = match.group(1)
                methods_str = match.group(2)
                if methods_str:
                    methods = [m.strip().strip("'\"").upper() for m in methods_str.split(",")]
                else:
                    methods = ["GET"]

                handler = ""
                for j in range(i + 1, min(i + 6, len(lines))):
                    def_match = _FASTAPI_DEF_RE.search(lines[j])
                    if def_match:
                        handler = def_match.group(1)
                        break

                docstring = _extract_python_docstring(lines, i)

                for method in methods:
                    routes.append(RouteInfo(
                        method=method, path=path, handler=handler,
                        file=rel_file, line=i + 1,
                        params=[], request_body="",
                        response_model="", docstring=docstring,
                    ))

        return routes

    def _scan_spring(self) -> list[RouteInfo]:
        """Scan for Spring Boot @GetMapping / @PostMapping patterns."""
        routes: list[RouteInfo] = []
        repo = Path(self.cwd)

        for fpath in self._iter_files(".java"):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if not _SPRING_CONTROLLER_RE.search(content):
                continue

            lines = content.splitlines()
            rel_file = str(fpath.relative_to(repo))

            # Class-level prefix
            class_prefix = ""
            cm = _SPRING_CLASS_MAPPING_RE.search(content)
            if cm:
                class_prefix = cm.group(1).rstrip("/")

            for i, line in enumerate(lines):
                match = _SPRING_MAPPING_RE.search(line)
                endpoint_path = ""
                method_type = ""

                if match:
                    method_type = match.group(1).upper()
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

                # Extract handler, params, body from method signature
                handler = ""
                params: list[dict] = []
                request_body = ""
                response_model = ""

                end_idx = min(i + 8, len(lines))
                chunk = "\n".join(lines[i:end_idx])

                meth_match = _SPRING_METHOD_RE.search(chunk)
                if meth_match:
                    response_model = meth_match.group(1)
                    handler = meth_match.group(2)

                # Path variables
                seen = set()
                for pv in _SPRING_PATH_VAR_RE.finditer(chunk):
                    ptype = pv.group(1) or "String"
                    pname = pv.group(2) or "id"
                    if pname not in seen:
                        seen.add(pname)
                        params.append({
                            "name": pname,
                            "type": _java_type_to_str(ptype),
                            "required": True,
                            "default": None,
                            "location": "path",
                        })

                # Query params
                for rp in _SPRING_REQ_PARAM_RE.finditer(chunk):
                    ptype = rp.group(1) or "String"
                    pname = rp.group(2) or "param"
                    params.append({
                        "name": pname,
                        "type": _java_type_to_str(ptype),
                        "required": False,
                        "default": None,
                        "location": "query",
                    })

                # Request body
                rb = _SPRING_REQ_BODY_RE.search(chunk)
                if rb:
                    request_body = rb.group(1)

                docstring = _extract_javadoc(lines, i)

                routes.append(RouteInfo(
                    method=method_type, path=full_path, handler=handler,
                    file=rel_file, line=i + 1,
                    params=params, request_body=request_body,
                    response_model=response_model, docstring=docstring,
                ))

        return routes

    def _scan_express(self) -> list[RouteInfo]:
        """Scan for Express app.get() / router.post() patterns."""
        routes: list[RouteInfo] = []
        repo = Path(self.cwd)

        for fpath in self._iter_files(".js", ".ts"):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            lines = content.splitlines()
            rel_file = str(fpath.relative_to(repo))

            for i, line in enumerate(lines):
                match = _EXPRESS_ROUTE_RE.search(line)
                if not match:
                    continue

                method = match.group(1).upper()
                path = match.group(2)
                handler = _extract_express_handler(lines, i)
                docstring = _extract_js_jsdoc(lines, i)

                routes.append(RouteInfo(
                    method=method, path=path, handler=handler,
                    file=rel_file, line=i + 1,
                    params=[], request_body="",
                    response_model="", docstring=docstring,
                ))

        return routes

    # ── Helpers ──────────────────────────────────────────────────────────

    def _iter_files(self, *extensions: str):
        """Yield files with given extensions, skipping common non-source dirs."""
        repo = Path(self.cwd)
        for root, dirs, files in os.walk(repo):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fname in files:
                if any(fname.endswith(ext) for ext in extensions):
                    if not fname.endswith((".d.ts", ".min.js")):
                        yield Path(root) / fname

    def _group_routes(self, routes: list[RouteInfo]) -> dict[str, list[RouteInfo]]:
        """Group routes by first two path segments."""
        groups: dict[str, list[RouteInfo]] = {}
        for r in routes:
            parts = [p for p in r.path.split("/") if p]
            if len(parts) >= 2:
                prefix = parts[0] + "/" + parts[1]
            elif parts:
                prefix = parts[0]
            else:
                prefix = "root"
            key = prefix.replace("-", " ").replace("_", " ").title()
            groups.setdefault(key, []).append(r)
        return groups


# ---------------------------------------------------------------------------
# format_api_summary — terminal table
# ---------------------------------------------------------------------------


def format_api_summary(result: APIDocResult) -> str:
    """Format scan results as a compact terminal table."""
    if not result.routes:
        return "  No API routes discovered."

    lines = [
        "",
        f"  API Routes — {result.framework}",
        f"  {'=' * 50}",
        "",
        f"  {'METHOD':<8} {'PATH':<42} {'HANDLER':<20} {'FILE'}",
        f"  {'------':<8} {'----':<42} {'-------':<20} {'----'}",
    ]

    for r in result.routes:
        handler_str = r.handler or "-"
        file_str = f"{r.file}:{r.line}" if r.file else "-"
        lines.append(f"  {r.method:<8} {r.path:<42} {handler_str:<20} {file_str}")

    lines.append("")
    lines.append(f"  Total: {len(result.routes)} endpoint(s)")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private helpers
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


def _parse_python_params(raw: str, path: str) -> list[dict]:
    """Parse Python function parameters into param dicts."""
    params: list[dict] = []
    path_params = set(re.findall(r'\{(\w+)\}', path))

    for part in raw.split(","):
        part = part.strip()
        if not part or part in ("self", "request", "db", "session"):
            continue
        if "Depends(" in part:
            continue

        name = part.split(":")[0].strip()
        type_hint = "string"
        default = None

        if ":" in part:
            rest = part.split(":", 1)[1].strip()
            if "=" in rest:
                type_hint = _python_type_to_str(rest.split("=")[0].strip())
                default = rest.split("=", 1)[1].strip()
            else:
                type_hint = _python_type_to_str(rest)
        elif "=" in part:
            default = part.split("=", 1)[1].strip()

        location = "path" if name in path_params else "query"
        params.append({
            "name": name,
            "type": type_hint,
            "required": name in path_params,
            "default": default,
            "location": location,
        })
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


def _extract_python_docstring(lines: list[str], decorator_line: int) -> str:
    """Extract docstring from the function after a decorator."""
    for j in range(decorator_line + 1, min(decorator_line + 10, len(lines))):
        stripped = lines[j].strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            if stripped.count(quote) >= 2:
                return stripped.strip(quote[0]).strip()
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


def _extract_javadoc(lines: list[str], annotation_line: int) -> str:
    """Extract Javadoc comment above an annotation line."""
    for j in range(annotation_line - 1, max(annotation_line - 20, -1), -1):
        stripped = lines[j].strip()
        if stripped.startswith("*/"):
            continue
        if stripped.startswith("/**"):
            parts = []
            for k in range(j, annotation_line):
                s = lines[k].strip().lstrip("/*").strip()
                if s and not s.startswith("@"):
                    parts.append(s)
            return " ".join(parts)
        if stripped and not stripped.startswith("*") and not stripped.startswith("@"):
            break
    return ""


def _extract_express_handler(lines: list[str], route_line: int) -> str:
    """Extract Express handler name from route definition."""
    line = lines[route_line]
    parts = line.split(",")
    if len(parts) >= 2:
        handler = parts[-1].strip().rstrip(";").rstrip(")").strip()
        if handler.isidentifier():
            return handler
    func_match = re.search(r'function\s+(\w+)', line)
    if func_match:
        return func_match.group(1)
    return ""


def _extract_js_jsdoc(lines: list[str], route_line: int) -> str:
    """Extract JSDoc comment above a route definition."""
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
            return " ".join(parts)
        if stripped and not stripped.startswith("*") and not stripped.startswith("//"):
            break
    return ""


def _html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
