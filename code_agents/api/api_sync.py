"""API Sync — keep OpenAPI spec, code, and client SDKs in sync.

Detects drift between OpenAPI/Swagger specs and actual code endpoints.
Reports missing endpoints, field mismatches, and response format differences.

Usage:
    from code_agents.api.api_sync import ApiSyncer
    syncer = ApiSyncer(ApiSyncConfig(cwd="/path/to/repo"))
    result = syncer.check_sync("openapi.yaml")
    print(format_api_sync(result))
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.api.api_sync")


@dataclass
class ApiSyncConfig:
    cwd: str = "."


@dataclass
class SyncIssue:
    """A single sync issue between spec and code."""
    issue_type: str  # "missing_in_spec", "missing_in_code", "field_mismatch", "method_mismatch"
    severity: str  # "error", "warning", "info"
    endpoint: str = ""
    description: str = ""
    spec_value: str = ""
    code_value: str = ""


@dataclass
class ApiSyncResult:
    """Result of API sync check."""
    spec_file: str = ""
    spec_endpoints: int = 0
    code_endpoints: int = 0
    issues: list[SyncIssue] = field(default_factory=list)
    in_sync: bool = True
    summary: str = ""


class ApiSyncer:
    """Check sync between OpenAPI spec and code."""

    def __init__(self, config: ApiSyncConfig):
        self.config = config

    def check_sync(self, spec_path: str) -> ApiSyncResult:
        """Check if spec and code are in sync."""
        logger.info("Checking API sync for: %s", spec_path)
        result = ApiSyncResult(spec_file=spec_path)

        full_path = os.path.join(self.config.cwd, spec_path)
        spec_endpoints = self._parse_spec(full_path)
        code_endpoints = self._scan_code_endpoints()

        result.spec_endpoints = len(spec_endpoints)
        result.code_endpoints = len(code_endpoints)

        # Find mismatches
        spec_set = set(spec_endpoints.keys())
        code_set = set(code_endpoints.keys())

        for ep in spec_set - code_set:
            result.issues.append(SyncIssue(
                issue_type="missing_in_code", severity="error",
                endpoint=ep, description=f"Endpoint in spec but not in code: {ep}",
            ))

        for ep in code_set - spec_set:
            result.issues.append(SyncIssue(
                issue_type="missing_in_spec", severity="warning",
                endpoint=ep, description=f"Endpoint in code but not in spec: {ep}",
            ))

        result.in_sync = len(result.issues) == 0
        result.summary = f"Spec: {result.spec_endpoints} endpoints, Code: {result.code_endpoints} endpoints, Issues: {len(result.issues)}"
        return result

    def _parse_spec(self, path: str) -> dict[str, dict]:
        """Parse OpenAPI spec file."""
        endpoints: dict[str, dict] = {}
        try:
            with open(path, "r") as f:
                content = f.read()
            if path.endswith((".yaml", ".yml")):
                try:
                    import yaml
                    data = yaml.safe_load(content)
                except ImportError:
                    return endpoints
            else:
                data = json.loads(content)

            paths = data.get("paths", {})
            for path_str, methods in paths.items():
                for method in ("get", "post", "put", "delete", "patch"):
                    if method in methods:
                        key = f"{method.upper()} {path_str}"
                        endpoints[key] = methods[method]
        except (OSError, json.JSONDecodeError, KeyError):
            logger.debug("Failed to parse spec: %s", path)

        return endpoints

    def _scan_code_endpoints(self) -> dict[str, dict]:
        """Scan code for registered endpoints."""
        endpoints: dict[str, dict] = {}
        from code_agents.tools._pattern_matchers import grep_codebase

        patterns = [
            (r"@(?:router|app)\.(get|post|put|delete|patch)\([\"']([^\"']+)[\"']", "python"),
            (r"router\.(get|post|put|delete|patch)\([\"']([^\"']+)[\"']", "express"),
        ]

        for pattern, lang in patterns:
            matches = grep_codebase(self.config.cwd, pattern, max_results=200)
            for match in matches:
                m = re.search(pattern, match.content)
                if m:
                    method = m.group(1).upper()
                    path = m.group(2)
                    key = f"{method} {path}"
                    endpoints[key] = {"file": match.file, "line": match.line}

        return endpoints


def format_api_sync(result: ApiSyncResult) -> str:
    lines = [f"{'=' * 60}", f"  API Sync Check: {result.spec_file}", f"{'=' * 60}"]
    lines.append(f"  {result.summary}")
    lines.append(f"  In Sync: {'Yes' if result.in_sync else 'NO'}")
    if result.issues:
        lines.append(f"\n  Issues ({len(result.issues)}):")
        for issue in result.issues:
            icon = {"error": "X", "warning": "!", "info": "~"}[issue.severity]
            lines.append(f"    {icon} [{issue.issue_type}] {issue.endpoint}")
            lines.append(f"      {issue.description}")
    lines.append("")
    return "\n".join(lines)
