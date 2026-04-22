"""Implicit API Docs — generate docs from actual API usage patterns and traffic."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.api.implicit_api_docs")


@dataclass
class APIEndpoint:
    """An API endpoint discovered from usage patterns."""
    method: str = "GET"
    path: str = ""
    path_params: list[str] = field(default_factory=list)
    query_params: list[dict] = field(default_factory=list)
    request_body_schema: dict = field(default_factory=dict)
    response_schema: dict = field(default_factory=dict)
    status_codes: list[int] = field(default_factory=list)
    avg_latency_ms: float = 0.0
    call_count: int = 0
    error_rate: float = 0.0
    sample_requests: list[dict] = field(default_factory=list)


@dataclass
class APIGroup:
    """A group of related endpoints (resource-based)."""
    name: str = ""
    base_path: str = ""
    endpoints: list[APIEndpoint] = field(default_factory=list)
    description: str = ""


@dataclass
class ImplicitDocsReport:
    """Complete implicit API documentation."""
    groups: list[APIGroup] = field(default_factory=list)
    total_endpoints: int = 0
    undocumented_endpoints: list[str] = field(default_factory=list)
    deprecated_candidates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TrafficEntry:
    """A single API traffic log entry."""
    method: str = "GET"
    path: str = ""
    status_code: int = 200
    latency_ms: float = 0.0
    request_body: Optional[dict] = None
    response_body: Optional[dict] = None
    query_params: Optional[dict] = None
    timestamp: str = ""


# Pattern to extract path parameters
PATH_PARAM_PATTERN = re.compile(r"/([0-9a-f-]{8,}|[0-9]+)(?=/|$)")


class ImplicitAPIDocs:
    """Generates API documentation from actual usage/traffic patterns."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, traffic: list[dict],
                existing_docs: Optional[dict] = None) -> ImplicitDocsReport:
        """Analyze traffic data and generate implicit API documentation."""
        logger.info("Analyzing %d traffic entries", len(traffic))

        entries = [self._parse_entry(t) for t in traffic]
        entries = [e for e in entries if e is not None]

        # Group by normalized path
        path_groups = self._group_by_path(entries)
        logger.info("Found %d unique endpoint patterns", len(path_groups))

        # Build endpoint objects
        endpoints = []
        for path_pattern, group_entries in path_groups.items():
            endpoint = self._build_endpoint(path_pattern, group_entries)
            endpoints.append(endpoint)

        # Organize into groups
        groups = self._organize_groups(endpoints)

        # Find undocumented and deprecated
        undocumented = []
        deprecated = []
        if existing_docs:
            documented_paths = set(existing_docs.get("paths", {}).keys())
            for ep in endpoints:
                if ep.path not in documented_paths:
                    undocumented.append(f"{ep.method} {ep.path}")
        for ep in endpoints:
            if ep.call_count < 2 and ep.error_rate > 0.5:
                deprecated.append(f"{ep.method} {ep.path}")

        report = ImplicitDocsReport(
            groups=groups,
            total_endpoints=len(endpoints),
            undocumented_endpoints=undocumented,
            deprecated_candidates=deprecated,
            warnings=self._generate_warnings(endpoints),
        )
        logger.info("Generated docs: %d groups, %d endpoints", len(groups), len(endpoints))
        return report

    def _parse_entry(self, raw: dict) -> Optional[TrafficEntry]:
        """Parse a raw traffic dict into TrafficEntry."""
        try:
            return TrafficEntry(
                method=raw.get("method", "GET").upper(),
                path=raw.get("path", ""),
                status_code=int(raw.get("status_code", raw.get("status", 200))),
                latency_ms=float(raw.get("latency_ms", raw.get("duration", 0))),
                request_body=raw.get("request_body"),
                response_body=raw.get("response_body"),
                query_params=raw.get("query_params"),
                timestamp=raw.get("timestamp", ""),
            )
        except (ValueError, TypeError):
            return None

    def _normalize_path(self, path: str) -> str:
        """Normalize a path by replacing IDs with parameters."""
        normalized = PATH_PARAM_PATTERN.sub("/{id}", path)
        return normalized

    def _group_by_path(self, entries: list[TrafficEntry]) -> dict[str, list[TrafficEntry]]:
        """Group traffic entries by normalized path + method."""
        groups: dict[str, list[TrafficEntry]] = {}
        for entry in entries:
            key = f"{entry.method} {self._normalize_path(entry.path)}"
            groups.setdefault(key, []).append(entry)
        return groups

    def _build_endpoint(self, path_key: str, entries: list[TrafficEntry]) -> APIEndpoint:
        """Build an endpoint from grouped traffic entries."""
        parts = path_key.split(" ", 1)
        method = parts[0]
        path = parts[1] if len(parts) > 1 else ""

        path_params = re.findall(r"\{(\w+)\}", path)
        status_codes = sorted(set(e.status_code for e in entries))
        latencies = [e.latency_ms for e in entries if e.latency_ms > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        errors = sum(1 for e in entries if e.status_code >= 400)
        error_rate = errors / len(entries) if entries else 0.0

        # Infer schemas from samples
        request_schema = self._infer_schema(
            [e.request_body for e in entries if e.request_body]
        )
        response_schema = self._infer_schema(
            [e.response_body for e in entries if e.response_body]
        )
        query_params = self._infer_query_params(entries)

        return APIEndpoint(
            method=method,
            path=path,
            path_params=path_params,
            query_params=query_params,
            request_body_schema=request_schema,
            response_schema=response_schema,
            status_codes=status_codes,
            avg_latency_ms=round(avg_latency, 2),
            call_count=len(entries),
            error_rate=round(error_rate, 4),
            sample_requests=[e.request_body for e in entries[:3] if e.request_body],
        )

    def _infer_schema(self, samples: list[dict]) -> dict:
        """Infer a JSON schema from sample data."""
        if not samples:
            return {}
        schema: dict = {"type": "object", "properties": {}}
        for sample in samples[:10]:
            if isinstance(sample, dict):
                for key, value in sample.items():
                    if key not in schema["properties"]:
                        schema["properties"][key] = {"type": self._json_type(value)}
        return schema

    def _json_type(self, value) -> str:
        """Get JSON type string for a value."""
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return "string"

    def _infer_query_params(self, entries: list[TrafficEntry]) -> list[dict]:
        """Infer query parameters from traffic."""
        params: dict[str, set] = {}
        for entry in entries:
            if entry.query_params:
                for key, value in entry.query_params.items():
                    params.setdefault(key, set()).add(type(value).__name__)
        return [{"name": k, "type": list(v)[0] if v else "string"} for k, v in params.items()]

    def _organize_groups(self, endpoints: list[APIEndpoint]) -> list[APIGroup]:
        """Organize endpoints into resource-based groups."""
        groups: dict[str, list[APIEndpoint]] = {}
        for ep in endpoints:
            parts = ep.path.strip("/").split("/")
            group_name = parts[0] if parts else "root"
            groups.setdefault(group_name, []).append(ep)

        return [
            APIGroup(
                name=name,
                base_path=f"/{name}",
                endpoints=eps,
                description=f"Endpoints under /{name}",
            )
            for name, eps in sorted(groups.items())
        ]

    def _generate_warnings(self, endpoints: list[APIEndpoint]) -> list[str]:
        """Generate warnings about API issues."""
        warnings = []
        for ep in endpoints:
            if ep.error_rate > 0.1:
                warnings.append(
                    f"{ep.method} {ep.path}: high error rate ({ep.error_rate:.1%})"
                )
            if ep.avg_latency_ms > 1000:
                warnings.append(
                    f"{ep.method} {ep.path}: high latency ({ep.avg_latency_ms:.0f}ms)"
                )
        return warnings


def format_report(report: ImplicitDocsReport) -> str:
    """Format as human-readable API documentation."""
    lines = ["# Implicit API Documentation", ""]
    for group in report.groups:
        lines.append(f"## {group.name}")
        for ep in group.endpoints:
            lines.append(f"### {ep.method} {ep.path}")
            lines.append(f"Calls: {ep.call_count} | Latency: {ep.avg_latency_ms}ms | Errors: {ep.error_rate:.1%}")
            if ep.query_params:
                lines.append(f"Query params: {', '.join(p['name'] for p in ep.query_params)}")
            lines.append("")
    return "\n".join(lines)
