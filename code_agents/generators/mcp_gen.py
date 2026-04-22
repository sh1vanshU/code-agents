"""MCP server code generator — read REST/gRPC specs and generate MCP server code.

Parses OpenAPI/Swagger or gRPC proto definitions and produces MCP server
boilerplate including tools, resources, and prompt definitions.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.generators.mcp_gen")

# Supported spec formats
OPENAPI_EXTENSIONS = {".yaml", ".yml", ".json"}
PROTO_EXTENSIONS = {".proto"}

# HTTP methods that map to MCP tools
TOOL_METHODS = {"post", "put", "patch", "delete"}
RESOURCE_METHODS = {"get"}

# Template fragments
MCP_TOOL_TEMPLATE = '''
class {class_name}Tool:
    """MCP tool: {description}"""

    name = "{tool_name}"
    description = "{description}"

    input_schema = {{
        "type": "object",
        "properties": {properties},
        "required": {required},
    }}

    async def run(self, arguments: dict) -> list[dict]:
        """Execute {tool_name}."""
        # TODO: implement API call to {method} {path}
        return [{{"type": "text", "text": "Not implemented"}}]
'''

MCP_RESOURCE_TEMPLATE = '''
class {class_name}Resource:
    """MCP resource: {description}"""

    uri = "{uri}"
    name = "{resource_name}"
    description = "{description}"
    mime_type = "application/json"

    async def read(self) -> str:
        """Read {resource_name}."""
        # TODO: implement API call to GET {path}
        return '{{}}'
'''

MCP_PROMPT_TEMPLATE = '''
class {class_name}Prompt:
    """MCP prompt: {description}"""

    name = "{prompt_name}"
    description = "{description}"
    arguments = {arguments}

    async def get(self, arguments: dict) -> list[dict]:
        """Generate prompt for {prompt_name}."""
        return [{{"role": "user", "content": {{"type": "text", "text": "Prompt: {prompt_name}"}}}}]
'''

MCP_SERVER_TEMPLATE = '''"""Auto-generated MCP server for {api_title}."""

from __future__ import annotations

import asyncio
import json
import sys

{tool_imports}
{resource_imports}
{prompt_imports}

class {server_class}:
    """MCP server wrapping {api_title}."""

    def __init__(self):
        self.tools = [{tool_instances}]
        self.resources = [{resource_instances}]
        self.prompts = [{prompt_instances}]

    async def handle_request(self, method: str, params: dict) -> dict:
        """Route JSON-RPC requests."""
        if method == "tools/list":
            return {{"tools": [t.input_schema for t in self.tools]}}
        if method == "resources/list":
            return {{"resources": [{{"uri": r.uri, "name": r.name}} for r in self.resources]}}
        if method == "prompts/list":
            return {{"prompts": [{{"name": p.name}} for p in self.prompts]}}
        return {{"error": f"Unknown method: {{method}}"}}
'''


@dataclass
class EndpointInfo:
    """Parsed API endpoint information."""

    path: str = ""
    method: str = "get"
    operation_id: str = ""
    summary: str = ""
    description: str = ""
    parameters: list[dict] = field(default_factory=list)
    request_body: dict = field(default_factory=dict)
    responses: dict = field(default_factory=dict)


@dataclass
class MCPGeneratorResult:
    """Result of MCP code generation."""

    server_code: str = ""
    tool_count: int = 0
    resource_count: int = 0
    prompt_count: int = 0
    endpoints_parsed: int = 0
    warnings: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)


class MCPGenerator:
    """Generate MCP server code from REST/gRPC specifications."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("MCPGenerator initialized for %s", cwd)

    def generate(
        self,
        spec_path: str | None = None,
        output_dir: str | None = None,
        api_title: str = "API",
    ) -> MCPGeneratorResult:
        """Generate MCP server code from a spec file.

        Args:
            spec_path: Path to OpenAPI/proto spec. Auto-detected if None.
            output_dir: Where to write generated code. Defaults to cwd/mcp_server.
            api_title: Human name for the API.

        Returns:
            MCPGeneratorResult with generated code and stats.
        """
        result = MCPGeneratorResult()

        if spec_path is None:
            spec_path = self._auto_detect_spec()
            if spec_path is None:
                result.warnings.append("No API spec file found")
                logger.warning("No API spec found in %s", self.cwd)
                return result

        spec_file = Path(spec_path)
        if not spec_file.exists():
            result.warnings.append(f"Spec file not found: {spec_path}")
            logger.error("Spec file not found: %s", spec_path)
            return result

        logger.info("Parsing spec: %s", spec_path)
        endpoints = self._parse_spec(spec_file)
        result.endpoints_parsed = len(endpoints)
        logger.info("Parsed %d endpoints", len(endpoints))

        tools, resources, prompts = self._classify_endpoints(endpoints)
        result.tool_count = len(tools)
        result.resource_count = len(resources)
        result.prompt_count = len(prompts)

        tool_code = [self._generate_tool(ep) for ep in tools]
        resource_code = [self._generate_resource(ep) for ep in resources]
        prompt_code = [self._generate_prompt(ep) for ep in prompts]

        server_code = self._assemble_server(
            api_title, tool_code, resource_code, prompt_code,
        )
        result.server_code = server_code

        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            server_file = out / "server.py"
            server_file.write_text(server_code)
            result.output_files.append(str(server_file))
            logger.info("Wrote server to %s", server_file)

        return result

    def _auto_detect_spec(self) -> str | None:
        """Find an API spec file in the working directory."""
        candidates = [
            "openapi.yaml", "openapi.yml", "openapi.json",
            "swagger.yaml", "swagger.yml", "swagger.json",
            "api.yaml", "api.yml", "api.json",
            "service.proto",
        ]
        for name in candidates:
            path = os.path.join(self.cwd, name)
            if os.path.isfile(path):
                logger.debug("Auto-detected spec: %s", path)
                return path
        return None

    def _parse_spec(self, spec_file: Path) -> list[EndpointInfo]:
        """Parse an API specification file into endpoint info."""
        suffix = spec_file.suffix.lower()
        if suffix in PROTO_EXTENSIONS:
            return self._parse_proto(spec_file)
        return self._parse_openapi(spec_file)

    def _parse_openapi(self, spec_file: Path) -> list[EndpointInfo]:
        """Parse an OpenAPI/Swagger spec."""
        content = spec_file.read_text()
        endpoints: list[EndpointInfo] = []

        try:
            if spec_file.suffix == ".json":
                import json
                spec = json.loads(content)
            else:
                import yaml  # lazy import
                spec = yaml.safe_load(content)
        except Exception as exc:
            logger.error("Failed to parse %s: %s", spec_file, exc)
            return endpoints

        paths = spec.get("paths", {})
        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, details in methods.items():
                if method.startswith("x-") or not isinstance(details, dict):
                    continue
                ep = EndpointInfo(
                    path=path,
                    method=method.lower(),
                    operation_id=details.get("operationId", ""),
                    summary=details.get("summary", ""),
                    description=details.get("description", ""),
                    parameters=details.get("parameters", []),
                    request_body=details.get("requestBody", {}),
                    responses=details.get("responses", {}),
                )
                endpoints.append(ep)
        return endpoints

    def _parse_proto(self, spec_file: Path) -> list[EndpointInfo]:
        """Parse a gRPC .proto file (simplified extraction)."""
        content = spec_file.read_text()
        endpoints: list[EndpointInfo] = []
        rpc_pattern = re.compile(
            r"rpc\s+(\w+)\s*\(\s*(\w+)\s*\)\s*returns\s*\(\s*(\w+)\s*\)",
        )
        for match in rpc_pattern.finditer(content):
            ep = EndpointInfo(
                path=f"/{match.group(1)}",
                method="post",
                operation_id=match.group(1),
                summary=f"gRPC: {match.group(1)}",
                description=f"Request: {match.group(2)}, Response: {match.group(3)}",
            )
            endpoints.append(ep)
        return endpoints

    def _classify_endpoints(
        self, endpoints: list[EndpointInfo],
    ) -> tuple[list[EndpointInfo], list[EndpointInfo], list[EndpointInfo]]:
        """Classify endpoints into tools, resources, and prompts."""
        tools: list[EndpointInfo] = []
        resources: list[EndpointInfo] = []
        prompts: list[EndpointInfo] = []

        for ep in endpoints:
            if ep.method in TOOL_METHODS:
                tools.append(ep)
            elif ep.method in RESOURCE_METHODS:
                resources.append(ep)
                # Also generate a prompt for complex GET endpoints
                if len(ep.parameters) >= 2:
                    prompts.append(ep)
            else:
                tools.append(ep)

        return tools, resources, prompts

    def _make_class_name(self, ep: EndpointInfo) -> str:
        """Convert endpoint to a CamelCase class name."""
        name = ep.operation_id or ep.path.strip("/").replace("/", "_")
        parts = re.split(r"[_\-/\s]+", name)
        return "".join(p.capitalize() for p in parts if p)

    def _extract_properties(self, ep: EndpointInfo) -> tuple[str, str]:
        """Extract JSON schema properties from endpoint params."""
        props: dict[str, Any] = {}
        required: list[str] = []
        for param in ep.parameters:
            pname = param.get("name", "param")
            props[pname] = {"type": "string", "description": param.get("description", "")}
            if param.get("required"):
                required.append(pname)
        return repr(props), repr(required)

    def _generate_tool(self, ep: EndpointInfo) -> str:
        """Generate code for an MCP tool."""
        class_name = self._make_class_name(ep)
        properties, required = self._extract_properties(ep)
        return MCP_TOOL_TEMPLATE.format(
            class_name=class_name,
            tool_name=ep.operation_id or ep.path,
            description=ep.summary or ep.description or ep.path,
            properties=properties,
            required=required,
            method=ep.method.upper(),
            path=ep.path,
        )

    def _generate_resource(self, ep: EndpointInfo) -> str:
        """Generate code for an MCP resource."""
        class_name = self._make_class_name(ep)
        return MCP_RESOURCE_TEMPLATE.format(
            class_name=class_name,
            uri=f"api://{ep.path.strip('/')}",
            resource_name=ep.operation_id or ep.path,
            description=ep.summary or ep.description or ep.path,
            path=ep.path,
        )

    def _generate_prompt(self, ep: EndpointInfo) -> str:
        """Generate code for an MCP prompt."""
        class_name = self._make_class_name(ep)
        args = [{"name": p.get("name", ""), "required": True} for p in ep.parameters[:3]]
        return MCP_PROMPT_TEMPLATE.format(
            class_name=class_name,
            prompt_name=ep.operation_id or ep.path,
            description=ep.summary or ep.description or ep.path,
            arguments=repr(args),
        )

    def _assemble_server(
        self,
        api_title: str,
        tool_code: list[str],
        resource_code: list[str],
        prompt_code: list[str],
    ) -> str:
        """Assemble the full MCP server source."""
        class_name = re.sub(r"[^a-zA-Z0-9]", "", api_title) + "MCPServer"
        all_code = "\n".join(tool_code + resource_code + prompt_code)
        server = MCP_SERVER_TEMPLATE.format(
            api_title=api_title,
            server_class=class_name,
            tool_imports="# Tool classes defined above",
            resource_imports="# Resource classes defined above",
            prompt_imports="# Prompt classes defined above",
            tool_instances=", ".join(f"t{i}()" for i in range(len(tool_code))) if tool_code else "",
            resource_instances=", ".join(f"r{i}()" for i in range(len(resource_code))) if resource_code else "",
            prompt_instances=", ".join(f"p{i}()" for i in range(len(prompt_code))) if prompt_code else "",
        )
        return all_code + "\n" + server


def generate_mcp(
    cwd: str,
    spec_path: str | None = None,
    output_dir: str | None = None,
    api_title: str = "API",
) -> dict:
    """Convenience function to generate MCP server code.

    Returns:
        Dict with server_code, counts, and warnings.
    """
    gen = MCPGenerator(cwd)
    result = gen.generate(spec_path=spec_path, output_dir=output_dir, api_title=api_title)
    return {
        "server_code": result.server_code,
        "tool_count": result.tool_count,
        "resource_count": result.resource_count,
        "prompt_count": result.prompt_count,
        "endpoints_parsed": result.endpoints_parsed,
        "warnings": result.warnings,
        "output_files": result.output_files,
    }
