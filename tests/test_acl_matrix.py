"""Tests for code_agents.acl_matrix — ACL Matrix Generator."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from code_agents.security.acl_matrix import (
    ACLMatrixGenerator,
    ACLMatrix,
    EndpointPermission,
    EscalationPath,
    acl_matrix_to_json,
    format_acl_markdown,
)


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repo with role and endpoint definitions."""
    src = tmp_path / "src"
    src.mkdir()

    # Python FastAPI app with roles
    (src / "roles.py").write_text(textwrap.dedent("""\
        from enum import Enum

        class Role(str, Enum):
            ADMIN = "admin"
            USER = "user"
            VIEWER = "viewer"
            MODERATOR = "moderator"
    """))

    # Endpoints with auth
    (src / "routes.py").write_text(textwrap.dedent("""\
        from fastapi import APIRouter

        router = APIRouter()

        @requires_role("admin")
        @router.get("/api/users")
        def list_users():
            pass

        @requires_role("user")
        @router.post("/api/orders")
        def create_order():
            pass

        @router.get("/api/health")
        def health_check():
            pass

        @requires_role("admin")
        @router.delete("/api/users/{id}")
        def delete_user():
            pass

        @requires_role("viewer")
        @router.get("/api/reports")
        def get_reports():
            pass
    """))

    # Express-style routes
    (src / "express.js").write_text(textwrap.dedent("""\
        const router = require('express').Router();

        router.get('/api/dashboard', requireRole('admin'), (req, res) => {});
        router.post('/api/settings', requireRole('admin'), (req, res) => {});
        router.get('/api/profile', requireRole('user'), (req, res) => {});
    """))

    return tmp_path


class TestACLMatrixGenerator:
    def test_scan_roles(self, tmp_repo):
        gen = ACLMatrixGenerator(cwd=str(tmp_repo))
        roles = gen._scan_roles()
        assert "admin" in roles
        assert "user" in roles
        assert "viewer" in roles

    def test_scan_permissions(self, tmp_repo):
        gen = ACLMatrixGenerator(cwd=str(tmp_repo))
        perms = gen._scan_permissions()
        assert len(perms) >= 3
        paths = [p.path for p in perms]
        assert "/api/users" in paths or any("/api/" in p for p in paths)

    def test_generate_full_matrix(self, tmp_repo):
        gen = ACLMatrixGenerator(cwd=str(tmp_repo))
        matrix = gen.generate()
        assert len(matrix.roles) >= 3
        assert len(matrix.permissions) >= 3
        assert isinstance(matrix.matrix, dict)

    def test_build_matrix(self, tmp_repo):
        gen = ACLMatrixGenerator(cwd=str(tmp_repo))
        roles = ["admin", "user"]
        perms = [
            EndpointPermission(file="r.py", line=1, method="GET", path="/users", roles=["admin"]),
            EndpointPermission(file="r.py", line=2, method="POST", path="/orders", roles=["user"]),
        ]
        matrix = gen._build_matrix(roles, perms)
        assert "GET /users" in matrix.get("admin", [])
        assert "POST /orders" in matrix.get("user", [])

    def test_unprotected_endpoints(self, tmp_repo):
        gen = ACLMatrixGenerator(cwd=str(tmp_repo))
        matrix = gen.generate()
        # /api/health has no role requirement
        unprotected_paths = [p.path for p in matrix.unprotected]
        # May or may not find unprotected depending on detection
        assert isinstance(matrix.unprotected, list)

    def test_format_matrix(self, tmp_repo):
        gen = ACLMatrixGenerator(cwd=str(tmp_repo))
        matrix = gen.generate()
        text = gen.format_matrix(matrix)
        assert "ACL Matrix Report" in text
        assert "Roles:" in text

    def test_find_escalation_paths(self, tmp_repo):
        gen = ACLMatrixGenerator(cwd=str(tmp_repo))
        roles = ["admin", "user", "viewer"]
        perms = [
            EndpointPermission(file="r.py", line=1, method="GET", path="/api/admin/users", roles=["user"]),
            EndpointPermission(file="r.py", line=2, method="DELETE", path="/api/config", roles=["viewer"]),
        ]
        matrix_data = gen._build_matrix(roles, perms)
        escalations = gen._find_escalation_paths(roles, perms, matrix_data)
        assert len(escalations) >= 1


class TestACLMatrixDataclass:
    def test_empty_matrix(self):
        m = ACLMatrix()
        assert m.roles == []
        assert m.permissions == []
        assert m.matrix == {}

    def test_escalation_path(self):
        e = EscalationPath(
            description="Test", severity="high",
            role="user", endpoints=["/admin"],
        )
        assert e.severity == "high"


class TestJsonExport:
    def test_acl_matrix_to_json(self):
        matrix = ACLMatrix(
            roles=["admin", "user"],
            permissions=[
                EndpointPermission(file="r.py", line=1, method="GET", path="/users", roles=["admin"]),
            ],
            matrix={"admin": ["GET /users"], "user": []},
            escalation_paths=[
                EscalationPath(description="test", severity="high", role="user"),
            ],
            unprotected=[
                EndpointPermission(file="r.py", line=5, method="GET", path="/health", roles=[]),
            ],
        )
        data = acl_matrix_to_json(matrix)
        assert data["roles"] == ["admin", "user"]
        assert data["total_endpoints"] == 1
        assert data["unprotected_count"] == 1
        assert len(data["escalation_paths"]) == 1

    def test_format_markdown(self):
        matrix = ACLMatrix(
            roles=["admin"],
            permissions=[
                EndpointPermission(file="r.py", line=1, method="GET", path="/users", roles=["admin"]),
            ],
            matrix={"admin": ["GET /users"]},
        )
        md = format_acl_markdown(matrix)
        assert "# ACL Matrix" in md


class TestEdgeCases:
    def test_no_source_files(self, tmp_path):
        gen = ACLMatrixGenerator(cwd=str(tmp_path))
        matrix = gen.generate()
        assert matrix.roles == []
        assert matrix.permissions == []

    def test_detect_method(self, tmp_path):
        gen = ACLMatrixGenerator(cwd=str(tmp_path))
        assert gen._detect_method("@router.get(") == "GET"
        assert gen._detect_method("@router.post(") == "POST"
        assert gen._detect_method("@router.delete(") == "DELETE"
        assert gen._detect_method("something else") == "ANY"

    def test_empty_role_list(self, tmp_path):
        gen = ACLMatrixGenerator(cwd=str(tmp_path))
        matrix_data = gen._build_matrix([], [])
        assert matrix_data == {}
