"""API compatibility checker — compare endpoints between git refs to detect breaking changes.

Lazy-loaded: no heavy imports at module level.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.api.api_compat")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EndpointInfo:
    """A single API endpoint."""
    method: str  # GET, POST, PUT, DELETE, PATCH
    path: str    # e.g. /v1/chat/completions
    params: list[str] = field(default_factory=list)  # known parameters
    source_file: str = ""

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    def __hash__(self):
        return hash(self.key)

    def __eq__(self, other):
        if not isinstance(other, EndpointInfo):
            return NotImplemented
        return self.key == other.key


@dataclass
class APICompatReport:
    """Result of comparing two sets of endpoints."""
    base_ref: str
    head_ref: str
    base_endpoints: list[EndpointInfo] = field(default_factory=list)
    head_endpoints: list[EndpointInfo] = field(default_factory=list)
    added_endpoints: list[EndpointInfo] = field(default_factory=list)
    removed_endpoints: list[EndpointInfo] = field(default_factory=list)
    changed_endpoints: list[dict] = field(default_factory=list)
    parameter_changes: list[dict] = field(default_factory=list)

    @property
    def breaking_count(self) -> int:
        """Count of breaking changes."""
        count = len(self.removed_endpoints)
        count += len(self.changed_endpoints)
        count += sum(1 for p in self.parameter_changes if p.get("breaking"))
        return count

    @property
    def non_breaking_count(self) -> int:
        """Count of non-breaking changes."""
        count = len(self.added_endpoints)
        count += sum(1 for p in self.parameter_changes if not p.get("breaking"))
        return count


# ---------------------------------------------------------------------------
# Scanner patterns
# ---------------------------------------------------------------------------

# FastAPI decorator patterns
_DECORATOR_RE = re.compile(
    r'@(?:router|app)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# APIRouter prefix pattern
_PREFIX_RE = re.compile(
    r'APIRouter\([^)]*prefix\s*=\s*["\']([^"\']+)["\']',
)

# Function parameter patterns (for detecting required vs optional params)
_PARAM_RE = re.compile(
    r'(?:Query|Path|Body|Header)\(\s*(?:\.\.\.|(None|default))',
)


# ---------------------------------------------------------------------------
# APICompatChecker
# ---------------------------------------------------------------------------

class APICompatChecker:
    """Compare API endpoints between git refs."""

    def __init__(self, cwd: str = "", base_ref: str = ""):
        self.cwd = cwd or os.getcwd()
        self.base_ref = base_ref or self._detect_last_tag()

    def _detect_last_tag(self) -> str:
        """Find last git tag using git describe."""
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=self.cwd, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return "HEAD~10"  # fallback: compare against 10 commits ago

    def _find_router_files(self) -> list[str]:
        """Find all Python files that likely define API routes."""
        router_files = []
        code_dir = Path(self.cwd)

        # Search for files containing route decorators
        for pattern in ["**/routers/*.py", "**/router.py", "**/app.py", "**/routes/*.py"]:
            for p in code_dir.glob(pattern):
                if p.is_file() and "__pycache__" not in str(p):
                    router_files.append(str(p.relative_to(code_dir)))

        return sorted(set(router_files))

    def _parse_endpoints_from_source(self, source: str, filepath: str = "") -> list[EndpointInfo]:
        """Parse API endpoints from Python source code."""
        endpoints = []

        # Detect router prefix
        prefix = ""
        prefix_match = _PREFIX_RE.search(source)
        if prefix_match:
            prefix = prefix_match.group(1).rstrip("/")

        # Find all route decorators
        for match in _DECORATOR_RE.finditer(source):
            method = match.group(1).upper()
            path = match.group(2)

            # Apply prefix
            if prefix and not path.startswith(prefix):
                full_path = prefix + ("" if path.startswith("/") else "/") + path
            else:
                full_path = path

            # Extract parameters from the function following the decorator
            pos = match.end()
            func_block = source[pos:pos + 500]  # look ahead for params
            params = []
            for pm in re.finditer(r'(\w+)\s*:\s*(?:str|int|float|bool)(?:\s*=\s*(\S+))?', func_block):
                param_name = pm.group(1)
                has_default = pm.group(2) is not None
                if param_name not in ("self", "request", "response", "db", "session"):
                    params.append(f"{param_name}{'?' if has_default else ''}")

            endpoints.append(EndpointInfo(
                method=method,
                path=full_path,
                params=params,
                source_file=filepath,
            ))

        return endpoints

    def scan_current_api(self) -> list[EndpointInfo]:
        """Discover all API endpoints in HEAD (current working tree)."""
        endpoints = []
        router_files = self._find_router_files()

        for filepath in router_files:
            full_path = os.path.join(self.cwd, filepath)
            try:
                with open(full_path) as f:
                    source = f.read()
                endpoints.extend(self._parse_endpoints_from_source(source, filepath))
            except (OSError, UnicodeDecodeError):
                logger.debug("Could not read %s", filepath)

        return endpoints

    def scan_base_api(self, ref: str = "") -> list[EndpointInfo]:
        """Discover API endpoints in a git ref using git show (no checkout)."""
        ref = ref or self.base_ref
        endpoints = []
        router_files = self._find_router_files()

        for filepath in router_files:
            try:
                result = subprocess.run(
                    ["git", "show", f"{ref}:{filepath}"],
                    cwd=self.cwd, capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    source = result.stdout
                    endpoints.extend(self._parse_endpoints_from_source(source, filepath))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                logger.debug("Could not read %s at ref %s", filepath, ref)

        return endpoints

    def compare(self, base_ref: str = "") -> APICompatReport:
        """Compare endpoints between base ref and HEAD."""
        ref = base_ref or self.base_ref

        head_endpoints = self.scan_current_api()
        base_endpoints = self.scan_base_api(ref)

        # Build lookup dicts
        base_map = {ep.key: ep for ep in base_endpoints}
        head_map = {ep.key: ep for ep in head_endpoints}

        base_keys = set(base_map.keys())
        head_keys = set(head_map.keys())

        # Added endpoints (non-breaking)
        added = [head_map[k] for k in sorted(head_keys - base_keys)]

        # Removed endpoints (BREAKING)
        removed = [base_map[k] for k in sorted(base_keys - head_keys)]

        # Check for method changes on same path (BREAKING)
        changed = []
        base_paths = {ep.path: ep for ep in base_endpoints}
        head_paths = {ep.path: ep for ep in head_endpoints}
        for path in set(base_paths.keys()) & set(head_paths.keys()):
            b = base_paths[path]
            h = head_paths[path]
            if b.method != h.method and b.key not in head_keys:
                changed.append({
                    "path": path,
                    "old_method": b.method,
                    "new_method": h.method,
                    "breaking": True,
                })

        # Parameter changes
        param_changes = []
        for key in base_keys & head_keys:
            b = base_map[key]
            h = head_map[key]
            base_params = set(b.params)
            head_params = set(h.params)

            # New required params = BREAKING
            for p in sorted(head_params - base_params):
                is_optional = p.endswith("?")
                param_changes.append({
                    "endpoint": key,
                    "param": p.rstrip("?"),
                    "change": "added optional" if is_optional else "added required",
                    "breaking": not is_optional,
                })

            # Removed params (likely breaking)
            for p in sorted(base_params - head_params):
                param_changes.append({
                    "endpoint": key,
                    "param": p.rstrip("?"),
                    "change": "removed",
                    "breaking": True,
                })

        return APICompatReport(
            base_ref=ref,
            head_ref="HEAD",
            base_endpoints=base_endpoints,
            head_endpoints=head_endpoints,
            added_endpoints=added,
            removed_endpoints=removed,
            changed_endpoints=changed,
            parameter_changes=param_changes,
        )

    def format_report(self, report: APICompatReport | None = None) -> str:
        """Format the compatibility report for terminal display."""
        if report is None:
            report = self.compare()

        lines: list[str] = []
        a = lines.append

        a("")
        a(f"  API Compatibility Check: {report.base_ref} -> HEAD")
        a("  " + "=" * 50)
        a("")

        # Non-breaking changes
        non_breaking = []
        for ep in report.added_endpoints:
            non_breaking.append(f"    + {ep.key} -- new endpoint")
        for pc in report.parameter_changes:
            if not pc["breaking"]:
                non_breaking.append(f"    ~ {pc['endpoint']} -- {pc['change']} param: {pc['param']}")

        if non_breaking:
            a(f"  Non-Breaking Changes ({len(non_breaking)}):")
            for line in non_breaking:
                a(line)
            a("")

        # Breaking changes
        breaking = []
        for ep in report.removed_endpoints:
            breaking.append(f"    - {ep.key} -- endpoint removed")
        for ch in report.changed_endpoints:
            breaking.append(f"    ~ {ch['old_method']} -> {ch['new_method']} {ch['path']} -- method changed")
        for pc in report.parameter_changes:
            if pc["breaking"]:
                breaking.append(f"    ~ {pc['endpoint']} -- {pc['change']} param: {pc['param']}")

        if breaking:
            a(f"  Breaking Changes ({len(breaking)}):")
            for line in breaking:
                a(line)
            a("")

        if not non_breaking and not breaking:
            a("  No API changes detected.")
            a("")

        # Summary
        a("  Summary:")
        a(f"    Total endpoints: {len(report.head_endpoints)} (was {len(report.base_endpoints)})")
        a(f"    Added: {len(report.added_endpoints)} | Removed: {len(report.removed_endpoints)} | Changed: {len(report.changed_endpoints)}")
        a(f"    Breaking changes: {report.breaking_count}")
        a("")

        if report.breaking_count > 0:
            a("  Verdict: BREAKING -- bump major version")
        else:
            a("  Verdict: COMPATIBLE -- safe to release")
        a("")

        return "\n".join(lines)
