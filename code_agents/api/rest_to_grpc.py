"""REST to gRPC Converter — generate .proto + gRPC server from REST endpoints.

Reads REST endpoint definitions (FastAPI, Flask, Express) and generates
equivalent Protocol Buffer definitions and gRPC service stubs.

Usage:
    from code_agents.api.rest_to_grpc import RestToGrpcConverter
    converter = RestToGrpcConverter(RestToGrpcConfig(cwd="/path/to/repo"))
    result = converter.convert()
    print(format_grpc_output(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.api.rest_to_grpc")


@dataclass
class RestToGrpcConfig:
    cwd: str = "."
    package_name: str = "api"
    go_package: str = ""


@dataclass
class ProtoMessage:
    name: str
    fields: list[tuple[str, str, int]] = field(default_factory=list)  # (type, name, number)


@dataclass
class ProtoRpc:
    name: str
    request_type: str
    response_type: str
    http_method: str = ""
    http_path: str = ""


@dataclass
class ProtoService:
    name: str
    rpcs: list[ProtoRpc] = field(default_factory=list)


@dataclass
class GrpcConvertResult:
    proto_content: str = ""
    server_stub: str = ""
    client_stub: str = ""
    endpoints_converted: int = 0
    messages: list[ProtoMessage] = field(default_factory=list)
    services: list[ProtoService] = field(default_factory=list)
    summary: str = ""


class RestToGrpcConverter:
    """Convert REST endpoints to gRPC."""

    def __init__(self, config: RestToGrpcConfig):
        self.config = config

    def convert(self) -> GrpcConvertResult:
        logger.info("Converting REST to gRPC in %s", self.config.cwd)
        result = GrpcConvertResult()

        # Scan for REST endpoints
        endpoints = self._find_endpoints()
        result.endpoints_converted = len(endpoints)

        # Group by resource
        resources: dict[str, list] = {}
        for ep in endpoints:
            resource = self._extract_resource(ep["path"])
            resources.setdefault(resource, []).append(ep)

        # Generate proto messages and services
        for resource, eps in resources.items():
            service = ProtoService(name=f"{resource.title()}Service")
            for ep in eps:
                rpc_name = self._make_rpc_name(ep["method"], ep["path"])
                req_msg = ProtoMessage(name=f"{rpc_name}Request")
                resp_msg = ProtoMessage(name=f"{rpc_name}Response")

                # Add fields based on path params
                field_num = 1
                for param in re.findall(r"\{(\w+)\}", ep["path"]):
                    req_msg.fields.append(("string", param, field_num))
                    field_num += 1

                result.messages.extend([req_msg, resp_msg])
                service.rpcs.append(ProtoRpc(
                    name=rpc_name,
                    request_type=req_msg.name,
                    response_type=resp_msg.name,
                    http_method=ep["method"],
                    http_path=ep["path"],
                ))
            result.services.append(service)

        result.proto_content = self._generate_proto(result)
        result.server_stub = self._generate_server_stub(result)
        result.summary = f"Converted {result.endpoints_converted} endpoints into {len(result.services)} gRPC services"
        return result

    def _find_endpoints(self) -> list[dict]:
        from code_agents.tools._pattern_matchers import grep_codebase
        endpoints = []
        matches = grep_codebase(self.config.cwd, r"@(?:router|app)\.(get|post|put|delete|patch)\([\"']([^\"']+)", max_results=100)
        for match in matches:
            m = re.search(r"\.(get|post|put|delete|patch)\([\"']([^\"']+)", match.content)
            if m:
                endpoints.append({"method": m.group(1).upper(), "path": m.group(2), "file": match.file})
        return endpoints

    def _extract_resource(self, path: str) -> str:
        parts = path.strip("/").split("/")
        return parts[0] if parts else "default"

    def _make_rpc_name(self, method: str, path: str) -> str:
        parts = path.strip("/").split("/")
        resource = parts[0].title() if parts else "Resource"
        method_map = {"GET": "Get", "POST": "Create", "PUT": "Update", "DELETE": "Delete", "PATCH": "Patch"}
        prefix = method_map.get(method, method.title())
        has_id = any("{" in p for p in parts)
        if method == "GET" and not has_id:
            prefix = "List"
        return f"{prefix}{resource}"

    def _generate_proto(self, result: GrpcConvertResult) -> str:
        lines = [
            'syntax = "proto3";',
            f"package {self.config.package_name};",
            "",
        ]
        if self.config.go_package:
            lines.append(f'option go_package = "{self.config.go_package}";')
            lines.append("")

        for msg in result.messages:
            lines.append(f"message {msg.name} {{")
            for ftype, fname, fnum in msg.fields:
                lines.append(f"  {ftype} {fname} = {fnum};")
            lines.append("}")
            lines.append("")

        for svc in result.services:
            lines.append(f"service {svc.name} {{")
            for rpc in svc.rpcs:
                lines.append(f"  rpc {rpc.name}({rpc.request_type}) returns ({rpc.response_type});")
            lines.append("}")
            lines.append("")

        return "\n".join(lines)

    def _generate_server_stub(self, result: GrpcConvertResult) -> str:
        lines = [
            f'"""gRPC server stub — auto-generated from REST endpoints."""',
            "",
        ]
        for svc in result.services:
            lines.append(f"class {svc.name}Servicer:")
            for rpc in svc.rpcs:
                lines.append(f"    def {rpc.name}(self, request, context):")
                lines.append(f'        """Originally: {rpc.http_method} {rpc.http_path}"""')
                lines.append(f"        raise NotImplementedError")
                lines.append("")
        return "\n".join(lines)


def format_grpc_output(result: GrpcConvertResult) -> str:
    lines = [f"{'=' * 60}", f"  REST to gRPC Converter", f"{'=' * 60}"]
    lines.append(f"  {result.summary}")
    lines.append(f"\n  --- .proto ---")
    for line in result.proto_content.splitlines():
        lines.append(f"  {line}")
    lines.append(f"\n  --- server stub ---")
    for line in result.server_stub.splitlines()[:20]:
        lines.append(f"  {line}")
    lines.append("")
    return "\n".join(lines)
