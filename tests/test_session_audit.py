"""Tests for code_agents.session_audit — Session Management Auditor."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from code_agents.security.session_audit import (
    SessionAuditor,
    SessionFinding,
    SessionAuditReport,
    format_session_report,
    session_report_to_json,
)


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repo with session-related code."""
    src = tmp_path / "src"
    src.mkdir()

    # JWT without expiry
    (src / "auth.py").write_text(textwrap.dedent("""\
        import jwt

        def create_token(user_id):
            payload = {"sub": user_id, "name": user_id}
            return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

        def login(username, password):
            user = authenticate(username, password)
            if user:
                token = create_token(user.id)
                return {"token": token}
    """))

    # Cookie without flags
    (src / "cookies.py").write_text(textwrap.dedent("""\
        def set_session(response, session_id):
            response.set_cookie(
                "session_id",
                session_id,
            )
    """))

    # JWT with expiry (should not trigger)
    (src / "good_auth.py").write_text(textwrap.dedent("""\
        import jwt
        from datetime import datetime, timedelta

        def create_token(user_id):
            payload = {
                "sub": user_id,
                "exp": datetime.utcnow() + timedelta(hours=1),
            }
            return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    """))

    # Cookie with all flags (should not trigger)
    (src / "good_cookies.py").write_text(textwrap.dedent("""\
        def set_session(response, session_id):
            response.set_cookie(
                "session_id",
                session_id,
                httponly=True,
                secure=True,
                samesite="Strict",
            )
    """))

    # Express-style with login but no session regen
    (src / "express.js").write_text(textwrap.dedent("""\
        const express = require('express');
        const app = express();

        app.post('/login', (req, res) => {
            const user = authenticate(req.body);
            if (user) {
                req.session.userId = user.id;
                res.json({ success: true });
            }
        });
    """))

    return tmp_path


class TestSessionAuditor:
    def test_finds_jwt_without_expiry(self, tmp_repo):
        auditor = SessionAuditor(cwd=str(tmp_repo))
        report = auditor.audit()
        token_findings = [f for f in report.findings if f.category == "token_expiry"]
        assert len(token_findings) >= 1
        assert token_findings[0].severity == "critical"

    def test_finds_insecure_cookies(self, tmp_repo):
        auditor = SessionAuditor(cwd=str(tmp_repo))
        report = auditor.audit()
        cookie_findings = [f for f in report.findings if f.category == "cookie_flags"]
        assert len(cookie_findings) >= 1
        # Should mention missing flags
        assert any("httponly" in f.message.lower() or "secure" in f.message.lower()
                    for f in cookie_findings)

    def test_good_jwt_not_flagged(self, tmp_repo):
        auditor = SessionAuditor(cwd=str(tmp_repo))
        report = auditor.audit()
        token_findings = [f for f in report.findings if f.category == "token_expiry"]
        # good_auth.py should not be flagged
        flagged_files = [f.file for f in token_findings]
        assert not any("good_auth" in f for f in flagged_files)

    def test_finds_session_fixation(self, tmp_repo):
        auditor = SessionAuditor(cwd=str(tmp_repo))
        report = auditor.audit()
        fixation = [f for f in report.findings if f.category == "session_fixation"]
        assert len(fixation) >= 1

    def test_files_scanned(self, tmp_repo):
        auditor = SessionAuditor(cwd=str(tmp_repo))
        report = auditor.audit()
        assert report.files_scanned >= 4


class TestCheckTokenExpiry:
    def test_no_jwt_code(self, tmp_path):
        (tmp_path / "app.py").write_text("def foo():\n    pass\n")
        auditor = SessionAuditor(cwd=str(tmp_path))
        report = auditor.audit()
        token_findings = [f for f in report.findings if f.category == "token_expiry"]
        assert len(token_findings) == 0


class TestCheckSecureCookies:
    def test_partial_flags(self, tmp_path):
        (tmp_path / "app.py").write_text(textwrap.dedent("""\
            def set_cookie(response):
                response.set_cookie(
                    "session",
                    "value",
                    httponly=True,
                )
        """))
        auditor = SessionAuditor(cwd=str(tmp_path))
        report = auditor.audit()
        cookie_findings = [f for f in report.findings if f.category == "cookie_flags"]
        assert len(cookie_findings) >= 1
        # Should flag missing secure and samesite
        assert any("secure" in f.message.lower() or "samesite" in f.message.lower()
                    for f in cookie_findings)


class TestCheckLogout:
    def test_login_without_logout(self, tmp_path):
        (tmp_path / "auth.py").write_text(textwrap.dedent("""\
            def login(username, password):
                user = authenticate(username, password)
                return create_session(user)
        """))
        auditor = SessionAuditor(cwd=str(tmp_path))
        report = auditor.audit()
        logout_findings = [f for f in report.findings if f.category == "logout"]
        assert len(logout_findings) >= 1

    def test_login_with_logout(self, tmp_path):
        (tmp_path / "auth.py").write_text(textwrap.dedent("""\
            def login(username, password):
                user = authenticate(username, password)
                return create_session(user)

            def logout(session_id):
                session.destroy(session_id)
        """))
        auditor = SessionAuditor(cwd=str(tmp_path))
        report = auditor.audit()
        logout_findings = [f for f in report.findings if f.category == "logout"]
        assert len(logout_findings) == 0


class TestSessionAuditReport:
    def test_by_category(self):
        report = SessionAuditReport(findings=[
            SessionFinding(file="a.py", line=1, category="token_expiry", severity="critical", message="t"),
            SessionFinding(file="a.py", line=2, category="cookie_flags", severity="high", message="t"),
            SessionFinding(file="a.py", line=3, category="cookie_flags", severity="medium", message="t"),
        ])
        assert report.by_category == {"token_expiry": 1, "cookie_flags": 2}

    def test_by_severity(self):
        report = SessionAuditReport(findings=[
            SessionFinding(file="a.py", line=1, category="token_expiry", severity="critical", message="t"),
            SessionFinding(file="a.py", line=2, category="cookie_flags", severity="high", message="t"),
        ])
        assert report.by_severity == {"critical": 1, "high": 1}


class TestFormatting:
    def test_empty_report(self):
        report = SessionAuditReport()
        result = format_session_report(report)
        assert "No session management issues" in result

    def test_report_with_findings(self):
        report = SessionAuditReport(
            findings=[
                SessionFinding(
                    file="auth.py", line=5, category="token_expiry",
                    severity="critical", message="JWT without expiry",
                    code_snippet="jwt.encode(payload, key)",
                ),
            ],
            files_scanned=10,
        )
        result = format_session_report(report)
        assert "auth.py" in result
        assert "CRITICAL" in result
        assert "jwt.encode" in result

    def test_json_export(self):
        report = SessionAuditReport(
            findings=[
                SessionFinding(
                    file="auth.py", line=5, category="token_expiry",
                    severity="critical", message="test",
                ),
            ],
            files_scanned=5,
        )
        data = session_report_to_json(report)
        assert data["files_scanned"] == 5
        assert data["total_findings"] == 1
        assert data["findings"][0]["category"] == "token_expiry"


class TestEdgeCases:
    def test_no_source_files(self, tmp_path):
        auditor = SessionAuditor(cwd=str(tmp_path))
        report = auditor.audit()
        assert report.files_scanned == 0
        assert len(report.findings) == 0

    def test_comments_skipped(self, tmp_path):
        (tmp_path / "app.py").write_text("# jwt.encode(payload, key)\n")
        auditor = SessionAuditor(cwd=str(tmp_path))
        report = auditor.audit()
        token_findings = [f for f in report.findings if f.category == "token_expiry"]
        assert len(token_findings) == 0
