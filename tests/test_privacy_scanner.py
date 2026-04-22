"""Tests for code_agents.privacy_scanner — data privacy scanner."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from code_agents.security.privacy_scanner import (
    PrivacyFinding,
    PrivacyReport,
    PrivacyScanner,
    format_privacy_report,
    privacy_report_to_json,
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


def _scan(tmp_path: Path, files: dict[str, str], regulation: str = "all") -> PrivacyReport:
    root = _create_project(tmp_path, files)
    scanner = PrivacyScanner(cwd=root, regulation=regulation)
    return scanner.scan()


# ---------------------------------------------------------------------------
# TestPIIInLogs
# ---------------------------------------------------------------------------

class TestPIIInLogs:
    """PII variables in log statements."""

    def test_email_in_logger(self, tmp_path):
        report = _scan(tmp_path, {
            "user.py": '''
                import logging
                logger = logging.getLogger(__name__)
                def create(email):
                    logger.info(f"Creating user with email {email}")
            ''',
        })
        assert any(f.data_type == "email" and "log" in f.issue.lower() for f in report.findings)

    def test_phone_in_print(self, tmp_path):
        report = _scan(tmp_path, {
            "notify.py": '''
                def send_sms(phone_number):
                    print(f"Sending to {phone_number}")
            ''',
        })
        assert any(f.data_type == "phone" for f in report.findings)

    def test_name_in_console_log(self, tmp_path):
        report = _scan(tmp_path, {
            "app.js": '''
                function greet(full_name) {
                    console.log(`Hello ${full_name}`);
                }
            ''',
        })
        assert any(f.data_type == "name" for f in report.findings)

    def test_no_pii_in_logs(self, tmp_path):
        report = _scan(tmp_path, {
            "app.py": '''
                import logging
                logger = logging.getLogger(__name__)
                logger.info("Server started on port 8000")
            ''',
        })
        log_findings = [f for f in report.findings if "log" in f.issue.lower()]
        assert len(log_findings) == 0


# ---------------------------------------------------------------------------
# TestPIIStorage
# ---------------------------------------------------------------------------

class TestPIIStorage:
    """PII stored without encryption."""

    def test_email_stored_no_encryption(self, tmp_path):
        report = _scan(tmp_path, {
            "repo.py": '''
                def save_user(db, email):
                    db.insert({"email": email})
            ''',
        })
        storage_findings = [f for f in report.findings if "stored" in f.issue.lower()]
        assert len(storage_findings) >= 1

    def test_pii_stored_with_encryption(self, tmp_path):
        report = _scan(tmp_path, {
            "repo.py": '''
                from cryptography.fernet import Fernet
                def save_user(db, email):
                    encrypted = encrypt(email)
                    db.insert({"email": encrypted})
            ''',
        })
        storage_findings = [f for f in report.findings if "stored without" in f.issue.lower()]
        assert len(storage_findings) == 0


# ---------------------------------------------------------------------------
# TestConsentTracking
# ---------------------------------------------------------------------------

class TestConsentTracking:
    """User data collected without consent."""

    def test_no_consent(self, tmp_path):
        report = _scan(tmp_path, {
            "repo.py": '''
                def register(db, email, phone):
                    db.insert({"email": email, "phone": phone})
            ''',
        })
        consent_findings = [f for f in report.findings if f.data_type == "consent"]
        assert len(consent_findings) >= 1

    def test_has_consent(self, tmp_path):
        report = _scan(tmp_path, {
            "repo.py": '''
                def register(db, email, phone, gdpr_consent):
                    if not gdpr_consent:
                        raise ValueError("Consent required")
                    db.insert({"email": email, "consent": gdpr_consent})
            ''',
        })
        consent_findings = [f for f in report.findings if f.data_type == "consent"]
        assert len(consent_findings) == 0


# ---------------------------------------------------------------------------
# TestDataDeletion
# ---------------------------------------------------------------------------

class TestDataDeletion:
    """Missing data deletion endpoint (right to erasure)."""

    def test_no_delete_endpoint(self, tmp_path):
        report = _scan(tmp_path, {
            "models.py": '''
                class User:
                    def __init__(self, name, email):
                        self.name = name
                        self.email = email
            ''',
        })
        deletion_findings = [f for f in report.findings if f.data_type == "deletion"]
        assert len(deletion_findings) >= 1

    def test_has_delete_endpoint(self, tmp_path):
        report = _scan(tmp_path, {
            "models.py": '''
                class User:
                    def __init__(self, name, email):
                        self.name = name
                        self.email = email
            ''',
            "routes.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.delete("/users/{user_id}")
                def delete_user(user_id):
                    pass
            ''',
        })
        deletion_findings = [f for f in report.findings if f.data_type == "deletion"]
        assert len(deletion_findings) == 0


# ---------------------------------------------------------------------------
# TestAadhaarPAN (DPDP Act)
# ---------------------------------------------------------------------------

class TestAadhaarPAN:
    """Indian ID patterns per DPDP Act."""

    def test_aadhaar_in_logs(self, tmp_path):
        report = _scan(tmp_path, {
            "kyc.py": '''
                import logging
                logger = logging.getLogger(__name__)
                def verify(aadhaar_number):
                    logger.info(f"Verifying aadhaar {aadhaar_number}")
            ''',
        })
        aadhaar_findings = [f for f in report.findings if f.data_type == "aadhaar"]
        assert len(aadhaar_findings) >= 1
        assert any(f.severity == "critical" for f in aadhaar_findings)

    def test_pan_in_logs(self, tmp_path):
        report = _scan(tmp_path, {
            "kyc.py": '''
                import logging
                logger = logging.getLogger(__name__)
                def verify(pan_number):
                    logger.info(f"PAN: {pan_number}")
            ''',
        })
        pan_findings = [f for f in report.findings if f.data_type == "pan"]
        assert len(pan_findings) >= 1
        assert any(f.severity == "critical" for f in pan_findings)

    def test_aadhaar_stored_unencrypted(self, tmp_path):
        report = _scan(tmp_path, {
            "repo.py": '''
                def save_kyc(db, aadhaar_number):
                    db.insert({"aadhaar": aadhaar_number})
            ''',
        })
        findings = [f for f in report.findings if f.data_type == "aadhaar" and "stored" in f.issue.lower()]
        assert len(findings) >= 1


# ---------------------------------------------------------------------------
# TestRegulationFilter
# ---------------------------------------------------------------------------

class TestRegulationFilter:
    """Regulation-specific scanning."""

    def test_gdpr_skips_aadhaar(self, tmp_path):
        report = _scan(tmp_path, {
            "kyc.py": '''
                import logging
                logger = logging.getLogger(__name__)
                def verify(aadhaar_number):
                    logger.info(f"Verifying {aadhaar_number}")
            ''',
        }, regulation="gdpr")
        aadhaar_findings = [f for f in report.findings if f.data_type == "aadhaar"]
        assert len(aadhaar_findings) == 0

    def test_dpdp_includes_aadhaar(self, tmp_path):
        report = _scan(tmp_path, {
            "kyc.py": '''
                import logging
                logger = logging.getLogger(__name__)
                def verify(aadhaar_number):
                    logger.info(f"Verifying {aadhaar_number}")
            ''',
        }, regulation="dpdp")
        aadhaar_findings = [f for f in report.findings if f.data_type == "aadhaar"]
        assert len(aadhaar_findings) >= 1


# ---------------------------------------------------------------------------
# TestFormatting
# ---------------------------------------------------------------------------

class TestFormatting:
    """Report formatting."""

    def test_text_format(self, tmp_path):
        report = _scan(tmp_path, {
            "app.py": '''
                import logging
                logger = logging.getLogger(__name__)
                def process(email):
                    logger.info(f"Processing {email}")
            ''',
        })
        text = format_privacy_report(report)
        assert "Privacy Scan Report" in text

    def test_json_format(self, tmp_path):
        report = _scan(tmp_path, {
            "app.py": "x = 1\n",
        })
        data = privacy_report_to_json(report)
        assert "regulation" in data
        assert "findings" in data
        assert isinstance(data["findings"], list)

    def test_empty_report(self, tmp_path):
        report = _scan(tmp_path, {
            "util.py": "x = 1\n",
        })
        text = format_privacy_report(report)
        assert "No privacy findings" in text


# ---------------------------------------------------------------------------
# TestDataclass
# ---------------------------------------------------------------------------

class TestDataclass:
    """PrivacyFinding dataclass fields."""

    def test_finding_fields(self):
        f = PrivacyFinding(
            file="user.py", line=5, data_type="email",
            issue="Email in logs", severity="high", regulation="GDPR",
        )
        assert f.file == "user.py"
        assert f.regulation == "GDPR"
