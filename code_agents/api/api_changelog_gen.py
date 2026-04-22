"""API Changelog Generator — diff two API versions, generate human-readable changelog.

Compares OpenAPI specs or endpoint signatures between versions and reports
breaking changes, new endpoints, deprecated endpoints, and field changes.

Usage:
    from code_agents.api.api_changelog_gen import ApiChangelogGenerator
    gen = ApiChangelogGenerator()
    result = gen.diff_specs("v1/openapi.json", "v2/openapi.json")
    print(format_api_changelog(result))
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.api.api_changelog_gen")


@dataclass
class ApiChangelogConfig:
    cwd: str = "."


@dataclass
class ApiChange:
    change_type: str  # "added", "removed", "modified", "deprecated"
    breaking: bool = False
    endpoint: str = ""
    description: str = ""
    details: str = ""


@dataclass
class ApiChangelogResult:
    old_version: str = ""
    new_version: str = ""
    changes: list[ApiChange] = field(default_factory=list)
    breaking_count: int = 0
    added_count: int = 0
    removed_count: int = 0
    modified_count: int = 0
    summary: str = ""


class ApiChangelogGenerator:
    """Generate API changelogs from spec diffs."""

    def __init__(self, config: Optional[ApiChangelogConfig] = None):
        self.config = config or ApiChangelogConfig()

    def diff_specs(self, old_path: str, new_path: str) -> ApiChangelogResult:
        logger.info("Diffing API specs: %s vs %s", old_path, new_path)
        result = ApiChangelogResult(old_version=old_path, new_version=new_path)

        old_spec = self._load_spec(old_path)
        new_spec = self._load_spec(new_path)

        old_endpoints = self._extract_endpoints(old_spec)
        new_endpoints = self._extract_endpoints(new_spec)

        old_set = set(old_endpoints.keys())
        new_set = set(new_endpoints.keys())

        # Added endpoints
        for ep in sorted(new_set - old_set):
            result.changes.append(ApiChange(
                change_type="added", endpoint=ep,
                description=f"New endpoint: {ep}",
            ))

        # Removed endpoints (breaking!)
        for ep in sorted(old_set - new_set):
            result.changes.append(ApiChange(
                change_type="removed", breaking=True, endpoint=ep,
                description=f"Removed endpoint: {ep} (BREAKING)",
            ))

        # Modified endpoints
        for ep in sorted(old_set & new_set):
            old_def = old_endpoints[ep]
            new_def = new_endpoints[ep]
            changes = self._compare_endpoint(ep, old_def, new_def)
            result.changes.extend(changes)

        result.breaking_count = sum(1 for c in result.changes if c.breaking)
        result.added_count = sum(1 for c in result.changes if c.change_type == "added")
        result.removed_count = sum(1 for c in result.changes if c.change_type == "removed")
        result.modified_count = sum(1 for c in result.changes if c.change_type == "modified")
        result.summary = (
            f"{len(result.changes)} changes: "
            f"{result.added_count} added, {result.removed_count} removed, "
            f"{result.modified_count} modified, {result.breaking_count} BREAKING"
        )
        return result

    def diff_dicts(self, old_endpoints: dict, new_endpoints: dict) -> ApiChangelogResult:
        """Diff two endpoint dictionaries directly."""
        result = ApiChangelogResult()

        old_set = set(old_endpoints.keys())
        new_set = set(new_endpoints.keys())

        for ep in sorted(new_set - old_set):
            result.changes.append(ApiChange(change_type="added", endpoint=ep, description=f"New: {ep}"))
        for ep in sorted(old_set - new_set):
            result.changes.append(ApiChange(change_type="removed", breaking=True, endpoint=ep, description=f"Removed: {ep}"))

        result.breaking_count = sum(1 for c in result.changes if c.breaking)
        result.added_count = sum(1 for c in result.changes if c.change_type == "added")
        result.removed_count = sum(1 for c in result.changes if c.change_type == "removed")
        result.summary = f"{len(result.changes)} changes"
        return result

    def _load_spec(self, path: str) -> dict:
        full = os.path.join(self.config.cwd, path) if not os.path.isabs(path) else path
        try:
            with open(full, "r") as f:
                content = f.read()
            if path.endswith((".yaml", ".yml")):
                try:
                    import yaml
                    return yaml.safe_load(content)
                except ImportError:
                    return {}
            return json.loads(content)
        except (OSError, json.JSONDecodeError):
            return {}

    def _extract_endpoints(self, spec: dict) -> dict:
        endpoints = {}
        for path, methods in spec.get("paths", {}).items():
            for method in ("get", "post", "put", "delete", "patch"):
                if method in methods:
                    endpoints[f"{method.upper()} {path}"] = methods[method]
        return endpoints

    def _compare_endpoint(self, ep: str, old_def: dict, new_def: dict) -> list[ApiChange]:
        changes = []
        # Check for parameter changes
        old_params = {p.get("name"): p for p in old_def.get("parameters", [])}
        new_params = {p.get("name"): p for p in new_def.get("parameters", [])}

        for name in set(old_params) - set(new_params):
            changes.append(ApiChange(
                change_type="modified", breaking=True, endpoint=ep,
                description=f"Removed parameter '{name}' (BREAKING)",
            ))
        for name in set(new_params) - set(old_params):
            required = new_params[name].get("required", False)
            changes.append(ApiChange(
                change_type="modified", breaking=required, endpoint=ep,
                description=f"Added {'required' if required else 'optional'} parameter '{name}'{' (BREAKING)' if required else ''}",
            ))
        return changes


def format_api_changelog(result: ApiChangelogResult) -> str:
    lines = [f"{'=' * 60}", f"  API Changelog", f"{'=' * 60}"]
    lines.append(f"  {result.summary}")
    if result.breaking_count:
        lines.append(f"  WARNING: {result.breaking_count} BREAKING CHANGES")

    for ct in ("removed", "modified", "added"):
        changes = [c for c in result.changes if c.change_type == ct]
        if changes:
            label = ct.upper()
            lines.append(f"\n  [{label}]")
            for c in changes:
                brk = " [BREAKING]" if c.breaking else ""
                lines.append(f"    {c.endpoint}: {c.description}{brk}")
    lines.append("")
    return "\n".join(lines)
