"""Tests for code_agents.compliance_report — compliance report generator."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from code_agents.security.compliance_report import (
    ComplianceControl,
    ComplianceReport,
    ComplianceReportGenerator,
    compliance_report_to_json,
    PCI_CONTROLS,
    SOC2_CONTROLS,
    GDPR_CONTROLS,
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


def _generate(tmp_path: Path, files: dict[str, str], standard: str = "pci") -> ComplianceReport:
    root = _create_project(tmp_path, files)
    gen = ComplianceReportGenerator(cwd=root)
    return gen.generate(standard=standard)


# ---------------------------------------------------------------------------
# TestPCIReport
# ---------------------------------------------------------------------------

class TestPCIReport:
    """PCI-DSS compliance report generation."""

    def test_basic_pci_report(self, tmp_path):
        report = _generate(tmp_path, {
            "app.py": '''
                import logging
                from cryptography.fernet import Fernet
                logger = logging.getLogger(__name__)
                SSL_CERT = "/etc/ssl/certs/server.pem"
            ''',
        })
        assert report.standard == "PCI"
        assert report.date
        assert 0 <= report.score <= 100
        assert len(report.controls) == len(PCI_CONTROLS)

    def test_pci_encryption_pass(self, tmp_path):
        report = _generate(tmp_path, {
            "crypto.py": '''
                from cryptography.fernet import Fernet
                def encrypt_card(data):
                    return Fernet(key).encrypt(data)
            ''',
        })
        pci3 = next(c for c in report.controls if c.id == "PCI-3")
        assert pci3.status == "pass"

    def test_pci_no_encryption_fail(self, tmp_path):
        report = _generate(tmp_path, {
            "plain.py": '''
                def store_data(card):
                    db.save(card)
            ''',
        })
        pci3 = next(c for c in report.controls if c.id == "PCI-3")
        assert pci3.status == "fail"

    def test_pci_logging_pass(self, tmp_path):
        report = _generate(tmp_path, {
            "app.py": '''
                import logging
                logger = logging.getLogger(__name__)
                logger.info("Request processed")
            ''',
        })
        pci10 = next(c for c in report.controls if c.id == "PCI-10")
        assert pci10.status == "pass"

    def test_pci_physical_na(self, tmp_path):
        report = _generate(tmp_path, {
            "app.py": "x = 1\n",
        })
        pci9 = next(c for c in report.controls if c.id == "PCI-9")
        assert pci9.status == "not_applicable"

    def test_pci_auth_pass(self, tmp_path):
        report = _generate(tmp_path, {
            "auth.py": '''
                import jwt
                def authenticate(token):
                    return jwt.decode(token, key, algorithms=["HS256"])
            ''',
        })
        pci8 = next(c for c in report.controls if c.id == "PCI-8")
        assert pci8.status == "pass"


# ---------------------------------------------------------------------------
# TestSOC2Report
# ---------------------------------------------------------------------------

class TestSOC2Report:
    """SOC2 compliance report generation."""

    def test_basic_soc2_report(self, tmp_path):
        report = _generate(tmp_path, {
            "app.py": "x = 1\n",
        }, standard="soc2")
        assert report.standard == "SOC2"
        assert len(report.controls) == len(SOC2_CONTROLS)

    def test_soc2_monitoring_pass(self, tmp_path):
        report = _generate(tmp_path, {
            "monitor.py": '''
                from prometheus_client import Counter
                requests_total = Counter("requests_total", "Total requests")
            ''',
        }, standard="soc2")
        cc4 = next(c for c in report.controls if c.id == "CC4")
        assert cc4.status == "pass"

    def test_soc2_access_control(self, tmp_path):
        report = _generate(tmp_path, {
            "auth.py": '''
                def authorize(user, role):
                    if role not in user.permissions:
                        raise Forbidden()
            ''',
        }, standard="soc2")
        cc6 = next(c for c in report.controls if c.id == "CC6")
        assert cc6.status == "pass"

    def test_soc2_privacy_consent(self, tmp_path):
        report = _generate(tmp_path, {
            "consent.py": '''
                def check_consent(user):
                    if not user.gdpr_consent:
                        raise ValueError("Consent required")
            ''',
        }, standard="soc2")
        p1 = next(c for c in report.controls if c.id == "P1")
        assert p1.status == "pass"


# ---------------------------------------------------------------------------
# TestGDPRReport
# ---------------------------------------------------------------------------

class TestGDPRReport:
    """GDPR compliance report generation."""

    def test_basic_gdpr_report(self, tmp_path):
        report = _generate(tmp_path, {
            "app.py": "x = 1\n",
        }, standard="gdpr")
        assert report.standard == "GDPR"
        assert len(report.controls) == len(GDPR_CONTROLS)

    def test_gdpr_consent_pass(self, tmp_path):
        report = _generate(tmp_path, {
            "consent.py": '''
                def get_consent(user):
                    return user.gdpr_consent
            ''',
        }, standard="gdpr")
        gdpr6 = next(c for c in report.controls if c.id == "GDPR-6")
        assert gdpr6.status == "pass"

    def test_gdpr_deletion_pass(self, tmp_path):
        report = _generate(tmp_path, {
            "routes.py": '''
                from fastapi import FastAPI
                app = FastAPI()
                @app.delete("/users/{id}")
                def delete_user(id):
                    pass
            ''',
        }, standard="gdpr")
        gdpr17 = next(c for c in report.controls if c.id == "GDPR-17")
        assert gdpr17.status == "pass"

    def test_gdpr_deletion_fail(self, tmp_path):
        report = _generate(tmp_path, {
            "app.py": "x = 1\n",
        }, standard="gdpr")
        gdpr17 = next(c for c in report.controls if c.id == "GDPR-17")
        assert gdpr17.status == "fail"

    def test_gdpr_encryption_pass(self, tmp_path):
        report = _generate(tmp_path, {
            "security.py": '''
                import hashlib
                def hash_data(data):
                    return hashlib.sha256(data.encode()).hexdigest()
            ''',
        }, standard="gdpr")
        gdpr32 = next(c for c in report.controls if c.id == "GDPR-32")
        assert gdpr32.status == "pass"


# ---------------------------------------------------------------------------
# TestFormatting
# ---------------------------------------------------------------------------

class TestFormatting:
    """Report formatting."""

    def test_terminal_format(self, tmp_path):
        root = _create_project(tmp_path, {"app.py": "x = 1\n"})
        gen = ComplianceReportGenerator(cwd=root)
        report = gen.generate("pci")
        text = gen.format_terminal(report)
        assert "PCI Compliance Report" in text
        assert "Score:" in text

    def test_markdown_format(self, tmp_path):
        root = _create_project(tmp_path, {"app.py": "x = 1\n"})
        gen = ComplianceReportGenerator(cwd=root)
        report = gen.generate("pci")
        md = gen.format_markdown(report)
        assert "# PCI Compliance Report" in md
        assert "| Control |" in md

    def test_json_format(self, tmp_path):
        root = _create_project(tmp_path, {"app.py": "x = 1\n"})
        gen = ComplianceReportGenerator(cwd=root)
        report = gen.generate("pci")
        json_str = gen.format_json(report)
        data = json.loads(json_str)
        assert data["standard"] == "PCI"
        assert "controls" in data

    def test_json_helper(self, tmp_path):
        report = _generate(tmp_path, {"app.py": "x = 1\n"})
        data = compliance_report_to_json(report)
        assert "standard" in data
        assert "controls" in data
        assert isinstance(data["controls"], list)


# ---------------------------------------------------------------------------
# TestInvalidStandard
# ---------------------------------------------------------------------------

class TestInvalidStandard:
    """Invalid standard should raise ValueError."""

    def test_unknown_standard(self, tmp_path):
        root = _create_project(tmp_path, {"app.py": "x = 1\n"})
        gen = ComplianceReportGenerator(cwd=root)
        with pytest.raises(ValueError, match="Unknown standard"):
            gen.generate("hipaa")


# ---------------------------------------------------------------------------
# TestDataclass
# ---------------------------------------------------------------------------

class TestDataclass:
    """ComplianceControl dataclass fields."""

    def test_control_fields(self):
        c = ComplianceControl(
            id="PCI-1", name="Network security",
            status="pass", evidence=["tls.py"],
            notes="TLS configured",
        )
        assert c.id == "PCI-1"
        assert c.status == "pass"

    def test_report_fields(self):
        r = ComplianceReport(
            standard="PCI", date="2026-04-09",
            score=85.0, controls=[], summary="test",
        )
        assert r.standard == "PCI"
        assert r.score == 85.0
