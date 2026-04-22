"""Tests for code_agents.rate_limit_audit — API rate limit auditor."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from code_agents.security.rate_limit_audit import (
    RateLimitAuditor,
    RateLimitFinding,
    RateLimitReport,
    format_rate_limit_report,
    rate_limit_report_to_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_project(tmp_path: Path, files: dict[str, str]) -> str:
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(tmp_path)


def _audit(tmp_path: Path, files: dict[str, str]) -> RateLimitReport:
    root = _create_project(tmp_path, files)
    auditor = RateLimitAuditor(cwd=root)
    return auditor.audit()


# ---------------------------------------------------------------------------
# TestEndpointDiscovery
# ---------------------------------------------------------------------------

class TestEndpointDiscovery:
    """Detect HTTP endpoints from FastAPI, Flask, Django."""

    def test_fastapi_get(self, tmp_path):
        report = _audit(tmp_path, {
            "app.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.get("/health")
                def health():
                    return {"ok": True}
            ''',
        })
        assert report.total_endpoints == 1

    def test_fastapi_post(self, tmp_path):
        report = _audit(tmp_path, {
            "app.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.post("/users")
                def create_user():
                    pass
            ''',
        })
        assert report.total_endpoints == 1

    def test_flask_route(self, tmp_path):
        report = _audit(tmp_path, {
            "app.py": '''
                from flask import Flask
                app = Flask(__name__)
                @app.route("/items", methods=["GET", "POST"])
                def items():
                    pass
            ''',
        })
        assert report.total_endpoints == 1

    def test_django_path(self, tmp_path):
        report = _audit(tmp_path, {
            "urls.py": '''
                from django.urls import path
                urlpatterns = [
                    path("api/users/", views.users),
                ]
            ''',
        })
        assert report.total_endpoints == 1

    def test_multiple_endpoints(self, tmp_path):
        report = _audit(tmp_path, {
            "app.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.get("/health")
                def health(): pass
                @app.post("/users")
                def create(): pass
                @app.delete("/users/{id}")
                def delete(): pass
            ''',
        })
        assert report.total_endpoints == 3

    def test_no_endpoints(self, tmp_path):
        report = _audit(tmp_path, {
            "utils.py": '''
                def helper():
                    return 42
            ''',
        })
        assert report.total_endpoints == 0
        assert report.score == 100


# ---------------------------------------------------------------------------
# TestRateLimitDetection
# ---------------------------------------------------------------------------

class TestRateLimitDetection:
    """Detect presence/absence of rate limiting."""

    def test_unprotected_endpoint(self, tmp_path):
        report = _audit(tmp_path, {
            "app.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.post("/api/data")
                def data(): pass
            ''',
        })
        assert report.unprotected_endpoints == 1
        assert any(f.severity == "medium" for f in report.findings)

    def test_protected_endpoint(self, tmp_path):
        report = _audit(tmp_path, {
            "app.py": '''
                from fastapi import FastAPI
                from slowapi import Limiter
                app = FastAPI()
                limiter = Limiter(key_func=get_remote_address)
                @app.post("/api/data")
                @limiter.limit("10/minute")
                def data(): pass
            ''',
        })
        assert report.protected_endpoints == 1
        # No "missing rate limit" finding for this endpoint
        missing = [f for f in report.findings if "no rate limiting" in f.issue.lower()]
        assert len(missing) == 0


# ---------------------------------------------------------------------------
# TestAuthEndpoints
# ---------------------------------------------------------------------------

class TestAuthEndpoints:
    """Auth endpoints without rate limits should be critical."""

    def test_login_without_limit(self, tmp_path):
        report = _audit(tmp_path, {
            "auth.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.post("/login")
                def login(): pass
            ''',
        })
        critical = [f for f in report.findings if f.severity == "critical"]
        assert len(critical) >= 1
        assert any("brute force" in f.issue.lower() for f in critical)

    def test_register_without_limit(self, tmp_path):
        report = _audit(tmp_path, {
            "auth.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.post("/register")
                def register(): pass
            ''',
        })
        critical = [f for f in report.findings if f.severity == "critical"]
        assert len(critical) >= 1

    def test_password_reset_without_limit(self, tmp_path):
        report = _audit(tmp_path, {
            "auth.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.post("/reset-password")
                def reset(): pass
            ''',
        })
        critical = [f for f in report.findings if f.severity == "critical"]
        assert len(critical) >= 1


# ---------------------------------------------------------------------------
# TestPaymentEndpoints
# ---------------------------------------------------------------------------

class TestPaymentEndpoints:
    """Payment endpoints without rate limits should be critical."""

    def test_pay_without_limit(self, tmp_path):
        report = _audit(tmp_path, {
            "payment.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.post("/pay")
                def pay(): pass
            ''',
        })
        critical = [f for f in report.findings if f.severity == "critical"]
        assert any("payment" in f.issue.lower() or "financial" in f.issue.lower() for f in critical)

    def test_charge_without_limit(self, tmp_path):
        report = _audit(tmp_path, {
            "payment.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.post("/charge")
                def charge(): pass
            ''',
        })
        critical = [f for f in report.findings if f.severity == "critical"]
        assert len(critical) >= 1


# ---------------------------------------------------------------------------
# TestConsistency
# ---------------------------------------------------------------------------

class TestConsistency:
    """Inconsistent rate limiting on similar endpoints."""

    def test_inconsistent_group(self, tmp_path):
        report = _audit(tmp_path, {
            "app.py": '''
                from fastapi import FastAPI
                from slowapi import Limiter
                app = FastAPI()
                limiter = Limiter(key_func=get_remote_address)
                @app.get("/api/users")
                @limiter.limit("100/minute")
                def list_users(): pass
                @app.post("/api/users")
                def create_user(): pass
            ''',
        })
        warnings = [f for f in report.findings if f.severity == "warning"]
        assert len(warnings) >= 1


# ---------------------------------------------------------------------------
# TestFormatting
# ---------------------------------------------------------------------------

class TestFormatting:
    """Report formatting."""

    def test_text_format(self, tmp_path):
        report = _audit(tmp_path, {
            "app.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.post("/login")
                def login(): pass
            ''',
        })
        text = format_rate_limit_report(report)
        assert "Rate Limit Audit Report" in text
        assert "CRITICAL" in text

    def test_json_format(self, tmp_path):
        report = _audit(tmp_path, {
            "app.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.get("/health")
                def health(): pass
            ''',
        })
        data = rate_limit_report_to_json(report)
        assert "total_endpoints" in data
        assert "findings" in data
        assert isinstance(data["findings"], list)

    def test_empty_report(self, tmp_path):
        report = _audit(tmp_path, {
            "util.py": "x = 1\n",
        })
        text = format_rate_limit_report(report)
        assert "No findings" in text


# ---------------------------------------------------------------------------
# TestDataclass
# ---------------------------------------------------------------------------

class TestDataclass:
    """RateLimitFinding dataclass fields."""

    def test_finding_fields(self):
        f = RateLimitFinding(
            file="app.py", line=10, endpoint="POST /login",
            issue="No limit", severity="critical", suggestion="Add limit",
        )
        assert f.file == "app.py"
        assert f.line == 10
        assert f.severity == "critical"
