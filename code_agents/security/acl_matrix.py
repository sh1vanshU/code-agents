"""ACL Matrix Generator — scan codebase for roles, permissions, and access control.

Discovers role definitions, endpoint permission requirements, and builds a
role-to-endpoint access matrix. Flags overly broad permissions and potential
escalation paths.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.security.acl_matrix")

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".tox", "venv", ".venv",
    "dist", "build", ".eggs", "vendor", "third_party", ".mypy_cache",
    ".pytest_cache", "htmlcov", "site-packages",
}

_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb",
    ".cs", ".php", ".kt", ".scala",
}

# ---------------------------------------------------------------------------
# Role detection patterns
# ---------------------------------------------------------------------------

_ROLE_PATTERNS = [
    # Python enums/constants
    re.compile(r"""(?:ROLE|Role|role)[_.](\w+)\s*=\s*['"]([\w-]+)['"]"""),
    re.compile(r"""['"](\w+)['"]\s*:\s*.*?(?:role|permission)""", re.IGNORECASE),
    # Common role names in strings
    re.compile(r"""['"](admin|superadmin|user|viewer|editor|moderator|manager|operator|readonly|read[_-]only|write|owner|member|guest|staff|support|developer|analyst|auditor)['"]""", re.IGNORECASE),
    # Java/TS enums
    re.compile(r"""(?:enum\s+Role|enum\s+UserRole)\s*\{([^}]+)\}""", re.DOTALL),
    # Decorator roles
    re.compile(r"""@(?:requires?_role|has_role|role_required)\s*\(\s*['"](\w+)['"]"""),
]

# Permission / auth patterns on endpoints
_PERMISSION_PATTERNS = [
    # Python decorators
    re.compile(r"""@(?:requires?_role|has_role|role_required|permission_required|requires?_permission|login_required|auth_required|authenticated|authorize)\s*\(\s*['"]([\w,\s]+)['"]"""),
    re.compile(r"""@(?:requires?_role|has_role|role_required|permission_required)\s*\(\s*\[(.*?)\]"""),
    # Spring Security
    re.compile(r"""@(?:PreAuthorize|Secured|RolesAllowed)\s*\(\s*['"](.*?)['"]"""),
    re.compile(r"""hasRole\(['"](\w+)['"]\)"""),
    re.compile(r"""hasAuthority\(['"](\w+)['"]\)"""),
    # Express/Node middleware
    re.compile(r"""(?:requireRole|checkRole|authorize)\s*\(\s*['"](\w+)['"]"""),
    re.compile(r"""(?:requireRole|checkRole|authorize)\s*\(\s*\[(.*?)\]"""),
    # Go middleware
    re.compile(r"""RequireRole\s*\(\s*"(\w+)"\s*\)"""),
    # Generic role checks in code
    re.compile(r"""(?:user\.role|currentUser\.role|req\.user\.role)\s*===?\s*['"](\w+)['"]"""),
    re.compile(r"""(?:role|user_role)\s*(?:==|in)\s*['"\[]?([\w,\s'"]+)"""),
]

# Endpoint detection
_ENDPOINT_PATTERNS = [
    # FastAPI/Flask
    re.compile(r"""@(?:app|router|bp|blueprint)\.(?:get|post|put|delete|patch)\s*\(\s*['"](.*?)['"]"""),
    # Express
    re.compile(r"""(?:router|app)\.(?:get|post|put|delete|patch)\s*\(\s*['"](.*?)['"]"""),
    # Spring
    re.compile(r"""@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)\s*\(\s*(?:value\s*=\s*)?['"](.*?)['"]"""),
    # Go
    re.compile(r"""\.(?:GET|POST|PUT|DELETE|PATCH|Handle|HandleFunc)\s*\(\s*"(.*?)".*"""),
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EndpointPermission:
    """An endpoint with its required roles."""
    file: str
    line: int
    method: str  # GET, POST, etc.
    path: str
    roles: list[str] = field(default_factory=list)
    is_public: bool = False


@dataclass
class EscalationPath:
    """A potential privilege escalation issue."""
    description: str
    severity: str  # "critical", "high", "medium"
    role: str
    endpoints: list[str] = field(default_factory=list)


@dataclass
class ACLMatrix:
    """Full ACL matrix."""
    roles: list[str] = field(default_factory=list)
    permissions: list[EndpointPermission] = field(default_factory=list)
    matrix: dict[str, list[str]] = field(default_factory=dict)  # role -> [endpoints]
    escalation_paths: list[EscalationPath] = field(default_factory=list)
    unprotected: list[EndpointPermission] = field(default_factory=list)


class ACLMatrixGenerator:
    """Generate access control matrix from codebase analysis."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.info("ACLMatrixGenerator initialized for %s", cwd)

    def generate(self) -> ACLMatrix:
        """Generate the complete ACL matrix."""
        roles = self._scan_roles()
        permissions = self._scan_permissions()
        matrix_data = self._build_matrix(roles, permissions)
        escalations = self._find_escalation_paths(roles, permissions, matrix_data)

        unprotected = [p for p in permissions if not p.roles and not p.is_public]

        result = ACLMatrix(
            roles=roles,
            permissions=permissions,
            matrix=matrix_data,
            escalation_paths=escalations,
            unprotected=unprotected,
        )

        logger.info(
            "ACL matrix: %d roles, %d endpoints, %d escalation warnings",
            len(roles), len(permissions), len(escalations),
        )
        return result

    def _scan_roles(self) -> list[str]:
        """Find role definitions in the codebase."""
        roles: set[str] = set()
        root = Path(self.cwd)

        for fpath in self._collect_files(root):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for pat in _ROLE_PATTERNS:
                for match in pat.finditer(content):
                    # Extract role names from match groups
                    for grp in match.groups():
                        if grp:
                            # Handle comma-separated lists or enum bodies
                            for role in re.split(r"[,\s]+", grp):
                                cleaned = role.strip().strip("'\"").strip()
                                if cleaned and len(cleaned) > 1 and cleaned.isidentifier():
                                    roles.add(cleaned.lower())

        # Always include common defaults
        for default in ("admin", "user"):
            if any(r for r in roles if default in r.lower()):
                continue

        logger.info("Found %d unique roles", len(roles))
        return sorted(roles)

    def _scan_permissions(self) -> list[EndpointPermission]:
        """Scan for endpoint -> required role mappings."""
        permissions: list[EndpointPermission] = []
        root = Path(self.cwd)

        for fpath in self._collect_files(root):
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            rel = str(fpath.relative_to(self.cwd))
            lines = content.split("\n")

            for i, line in enumerate(lines):
                # Detect endpoints
                for ep_pat in _ENDPOINT_PATTERNS:
                    m = ep_pat.search(line)
                    if not m:
                        continue

                    path = m.group(1)
                    method = self._detect_method(line)
                    roles_found = self._find_roles_near_line(lines, i)

                    perm = EndpointPermission(
                        file=rel, line=i + 1,
                        method=method, path=path,
                        roles=roles_found,
                    )
                    permissions.append(perm)

        logger.info("Found %d endpoint permissions", len(permissions))
        return permissions

    def _build_matrix(
        self, roles: list[str], permissions: list[EndpointPermission],
    ) -> dict[str, list[str]]:
        """Build role -> [endpoints] mapping."""
        matrix: dict[str, list[str]] = {role: [] for role in roles}

        for perm in permissions:
            ep = f"{perm.method} {perm.path}"
            if not perm.roles:
                # No explicit role — accessible by all?
                for role in roles:
                    if ep not in matrix.get(role, []):
                        matrix.setdefault(role, []).append(ep)
            else:
                for role in perm.roles:
                    role_lower = role.lower()
                    if role_lower in matrix:
                        if ep not in matrix[role_lower]:
                            matrix[role_lower].append(ep)
                    else:
                        matrix[role_lower] = [ep]

        return matrix

    def _find_escalation_paths(
        self,
        roles: list[str],
        permissions: list[EndpointPermission],
        matrix: dict[str, list[str]],
    ) -> list[EscalationPath]:
        """Detect overly broad permissions and escalation risks."""
        escalations: list[EscalationPath] = []

        # Check for non-admin roles with admin-like access
        admin_keywords = {"admin", "superadmin", "super_admin"}
        admin_roles = [r for r in roles if r in admin_keywords]
        non_admin = [r for r in roles if r not in admin_keywords]

        for role in non_admin:
            endpoints = matrix.get(role, [])
            # Check if non-admin can access user management endpoints
            sensitive_eps = [
                ep for ep in endpoints
                if any(kw in ep.lower() for kw in [
                    "/admin", "/users", "/roles", "/permissions",
                    "/config", "/settings", "/secrets", "/keys",
                    "/deploy", "/migration", "/backup",
                ])
            ]
            if sensitive_eps:
                escalations.append(EscalationPath(
                    description=f"Role '{role}' has access to {len(sensitive_eps)} sensitive endpoints",
                    severity="high",
                    role=role,
                    endpoints=sensitive_eps[:5],
                ))

        # Check for roles with too many endpoints
        if roles:
            avg = sum(len(matrix.get(r, [])) for r in roles) / len(roles) if roles else 0
            for role in non_admin:
                count = len(matrix.get(role, []))
                if count > avg * 2 and count > 10:
                    escalations.append(EscalationPath(
                        description=f"Role '{role}' has {count} endpoints (avg: {avg:.0f}) — overly broad",
                        severity="medium",
                        role=role,
                        endpoints=matrix.get(role, [])[:5],
                    ))

        # Check for endpoints with no auth
        unprotected_sensitive = [
            p for p in permissions
            if not p.roles and any(
                kw in p.path.lower() for kw in [
                    "/api/", "/v1/", "/v2/", "/internal/",
                ]
            )
        ]
        if unprotected_sensitive:
            escalations.append(EscalationPath(
                description=f"{len(unprotected_sensitive)} API endpoints have no role requirement",
                severity="critical",
                role="anonymous",
                endpoints=[f"{p.method} {p.path}" for p in unprotected_sensitive[:5]],
            ))

        return escalations

    def format_matrix(self, matrix: ACLMatrix) -> str:
        """Format matrix as a terminal-friendly table."""
        parts = [
            "  ACL Matrix Report",
            f"  Roles: {len(matrix.roles)}  |  Endpoints: {len(matrix.permissions)}",
            "",
        ]

        # Escalation warnings first
        if matrix.escalation_paths:
            parts.append("  ESCALATION WARNINGS:")
            for esc in matrix.escalation_paths:
                sev_icon = {"critical": "[!!]", "high": "[!]", "medium": "[~]"}.get(esc.severity, "[ ]")
                parts.append(f"    {sev_icon} {esc.description}")
                for ep in esc.endpoints:
                    parts.append(f"        {ep}")
            parts.append("")

        # Unprotected endpoints
        if matrix.unprotected:
            parts.append("  UNPROTECTED ENDPOINTS:")
            for ep in matrix.unprotected[:20]:
                parts.append(f"    [?] {ep.method} {ep.path} ({ep.file}:{ep.line})")
            parts.append("")

        # Matrix table
        if matrix.roles:
            parts.append("  ROLE -> ENDPOINT MATRIX:")
            for role in matrix.roles:
                endpoints = matrix.matrix.get(role, [])
                parts.append(f"    {role} ({len(endpoints)} endpoints)")
                for ep in endpoints[:10]:
                    parts.append(f"      {ep}")
                if len(endpoints) > 10:
                    parts.append(f"      ... and {len(endpoints) - 10} more")
            parts.append("")

        return "\n".join(parts)

    # ----- helpers -----

    def _collect_files(self, target: Path) -> list[Path]:
        """Collect source code files."""
        files: list[Path] = []
        for root, dirs, fnames in os.walk(target):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fn in fnames:
                if Path(fn).suffix in _CODE_EXTENSIONS:
                    files.append(Path(root) / fn)
        return sorted(files)

    def _detect_method(self, line: str) -> str:
        """Detect HTTP method from a route/endpoint line."""
        lower = line.lower()
        for method in ("get", "post", "put", "delete", "patch"):
            if f".{method}" in lower or f"@{method}" in lower or f"{method}mapping" in lower:
                return method.upper()
        return "ANY"

    def _find_roles_near_line(self, lines: list[str], line_idx: int) -> list[str]:
        """Find role requirements near an endpoint definition (decorators, middleware)."""
        roles: list[str] = []
        # Look at surrounding lines (decorators above, middleware in same line)
        start = max(0, line_idx - 5)
        end = min(len(lines), line_idx + 3)

        context = "\n".join(lines[start:end])
        for pat in _PERMISSION_PATTERNS:
            for match in pat.finditer(context):
                for grp in match.groups():
                    if grp:
                        for role in re.split(r"[,\s]+", grp):
                            cleaned = role.strip().strip("'\"").strip()
                            if cleaned and len(cleaned) > 1:
                                roles.append(cleaned.lower())

        return list(dict.fromkeys(roles))  # dedupe preserving order


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


def acl_matrix_to_json(matrix: ACLMatrix) -> dict:
    """Convert ACL matrix to JSON-serializable dict."""
    return {
        "roles": matrix.roles,
        "total_endpoints": len(matrix.permissions),
        "unprotected_count": len(matrix.unprotected),
        "escalation_warnings": len(matrix.escalation_paths),
        "matrix": matrix.matrix,
        "escalation_paths": [
            {
                "description": e.description,
                "severity": e.severity,
                "role": e.role,
                "endpoints": e.endpoints,
            }
            for e in matrix.escalation_paths
        ],
        "unprotected": [
            {
                "method": p.method, "path": p.path,
                "file": p.file, "line": p.line,
            }
            for p in matrix.unprotected
        ],
        "permissions": [
            {
                "method": p.method, "path": p.path,
                "roles": p.roles, "file": p.file, "line": p.line,
            }
            for p in matrix.permissions
        ],
    }


def format_acl_markdown(matrix: ACLMatrix) -> str:
    """Format matrix as Markdown table."""
    parts = ["# ACL Matrix\n"]

    if matrix.escalation_paths:
        parts.append("## Escalation Warnings\n")
        for esc in matrix.escalation_paths:
            parts.append(f"- **[{esc.severity.upper()}]** {esc.description}")
        parts.append("")

    if matrix.roles and matrix.permissions:
        # Build table header
        all_eps = sorted(set(f"{p.method} {p.path}" for p in matrix.permissions))
        header = "| Role |" + "|".join(f" {ep} " for ep in all_eps[:20]) + "|"
        separator = "|------|" + "|".join("------" for _ in all_eps[:20]) + "|"
        parts.append(header)
        parts.append(separator)

        for role in matrix.roles:
            role_eps = set(matrix.matrix.get(role, []))
            cells = []
            for ep in all_eps[:20]:
                cells.append(" Y " if ep in role_eps else " - ")
            parts.append(f"| {role} |" + "|".join(cells) + "|")
        parts.append("")

    return "\n".join(parts)
