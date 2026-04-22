"""Tests for code_agents.pci_scanner — PCI-DSS compliance scanner."""

from __future__ import annotations

import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from code_agents.security.pci_scanner import (
    PCIComplianceScanner,
    PCIFinding,
    PCIReport,
    PCI_RULES,
    format_pci_report,
    pci_report_to_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_project(tmp_path: Path, files: dict[str, str]) -> str:
    """Create a temporary project with given files and return root path."""
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(tmp_path)


def _scan(tmp_path: Path, files: dict[str, str]) -> list[PCIFinding]:
    """Create project, scan, return findings."""
    root = _create_project(tmp_path, files)
    scanner = PCIComplianceScanner(cwd=root)
    report = scanner.scan()
    return report.findings


# ---------------------------------------------------------------------------
# TestPANDetection
# ---------------------------------------------------------------------------

class TestPANDetection:
    """Card number patterns in logs and print statements."""

    def test_card_var_in_logger(self, tmp_path):
        findings = _scan(tmp_path, {
            "payment.py": """
                import logging
                logger = logging.getLogger(__name__)
                def process(card_number):
                    logger.info(f"Processing card {card_number}")
            """,
        })
        assert any(f.rule_id == "PCI-3.4" and f.severity == "critical" for f in findings)

    def test_card_var_in_print(self, tmp_path):
        findings = _scan(tmp_path, {
            "pay.py": """
                def show(pan):
                    print(f"PAN is {pan}")
            """,
        })
        assert any(f.rule_id == "PCI-3.4" for f in findings)

    def test_pan_literal_in_log(self, tmp_path):
        findings = _scan(tmp_path, {
            "test_pay.py": """
                import logging
                logger = logging.getLogger(__name__)
                logger.info("card 4111111111111111 processed")
            """,
        })
        assert any(f.rule_id == "PCI-3.4" for f in findings)

    def test_safe_logging_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "safe.py": """
                import logging
                logger = logging.getLogger(__name__)
                logger.info("Payment processed for order %s", order_id)
            """,
        })
        pci34 = [f for f in findings if f.rule_id == "PCI-3.4"]
        assert len(pci34) == 0

    def test_snippet_redacts_pan(self, tmp_path):
        """Ensure the code_snippet field never contains actual card numbers."""
        findings = _scan(tmp_path, {
            "log_pan.py": """
                import logging
                logger = logging.getLogger(__name__)
                logger.info("card 4111111111111111 done")
            """,
        })
        for f in findings:
            assert "4111111111111111" not in f.code_snippet


# ---------------------------------------------------------------------------
# TestEncryption
# ---------------------------------------------------------------------------

class TestEncryption:
    """Weak cryptographic algorithms."""

    def test_md5_for_password(self, tmp_path):
        findings = _scan(tmp_path, {
            "auth.py": """
                import hashlib
                def hash_password(password):
                    return hashlib.md5(password.encode()).hexdigest()
            """,
        })
        assert any(f.rule_id in ("PCI-8.2.1", "PCI-6.5.3") for f in findings)

    def test_sha1_detected(self, tmp_path):
        findings = _scan(tmp_path, {
            "crypto.py": """
                import hashlib
                h = hashlib.sha1(data)
            """,
        })
        assert any(f.rule_id == "PCI-6.5.3" for f in findings)

    def test_des_cipher(self, tmp_path):
        findings = _scan(tmp_path, {
            "enc.py": """
                from Crypto.Cipher import DES
                cipher = DES.new(key, DES.MODE_CBC)
            """,
        })
        assert any(f.rule_id == "PCI-6.5.3" and f.severity == "critical" for f in findings)

    def test_ecb_mode(self, tmp_path):
        findings = _scan(tmp_path, {
            "aes_bad.py": """
                from Crypto.Cipher import AES
                cipher = AES.new(key, AES.MODE_ECB)
            """,
        })
        assert any(f.rule_id == "PCI-6.5.3" for f in findings)

    def test_aes256_gcm_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "aes_good.py": """
                from Crypto.Cipher import AES
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            """,
        })
        crypto_findings = [f for f in findings if f.rule_id == "PCI-6.5.3"]
        assert len(crypto_findings) == 0

    def test_small_key_size(self, tmp_path):
        findings = _scan(tmp_path, {
            "small_key.py": """
                from cryptography.hazmat.primitives.ciphers import algorithms
                algo = algorithms.AES(key_size=64)
            """,
        })
        assert any(f.rule_id == "PCI-6.5.3" and "64" in f.description for f in findings)


# ---------------------------------------------------------------------------
# TestTransportSecurity
# ---------------------------------------------------------------------------

class TestTransportSecurity:
    """HTTP vs HTTPS and SSL verification."""

    def test_http_payment_url(self, tmp_path):
        findings = _scan(tmp_path, {
            "client.py": """
                import requests
                url = "http://api.example.com/payment/charge"
                resp = requests.post(url, json=data)
            """,
        })
        assert any(f.rule_id == "PCI-4.1" for f in findings)

    def test_https_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "client_ok.py": """
                import requests
                url = "https://api.example.com/payment/charge"
                resp = requests.post(url, json=data)
            """,
        })
        transport = [f for f in findings if f.rule_id == "PCI-4.1"]
        assert len(transport) == 0

    def test_verify_false(self, tmp_path):
        findings = _scan(tmp_path, {
            "insecure.py": """
                import requests
                resp = requests.post(url, verify=False)
            """,
        })
        assert any(f.rule_id == "PCI-4.1" and "verify" in f.description.lower() for f in findings)

    def test_ssl_disabled(self, tmp_path):
        findings = _scan(tmp_path, {
            "ssl_off.py": """
                import ssl
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
            """,
        })
        assert any(f.rule_id == "PCI-4.1" for f in findings)


# ---------------------------------------------------------------------------
# TestKeyManagement
# ---------------------------------------------------------------------------

class TestKeyManagement:
    """Hardcoded keys and weak KDF."""

    def test_hardcoded_key(self, tmp_path):
        findings = _scan(tmp_path, {
            "config.py": """
                AES_KEY = "0123456789abcdef0123456789abcdef"
            """,
        })
        assert any(f.rule_id == "PCI-6.5.3" and "hardcoded" in f.description.lower() for f in findings)

    def test_weak_kdf(self, tmp_path):
        findings = _scan(tmp_path, {
            "derive.py": """
                import hashlib
                key = hashlib.sha256(password.encode()).digest()
            """,
        })
        assert any(f.rule_id == "PCI-8.2.1" for f in findings)

    def test_no_hardcoded_key_for_safe_code(self, tmp_path):
        findings = _scan(tmp_path, {
            "safe_config.py": """
                import os
                AES_KEY = os.environ["AES_KEY"]
            """,
        })
        key_findings = [f for f in findings if "hardcoded" in f.description.lower()]
        assert len(key_findings) == 0


# ---------------------------------------------------------------------------
# TestErrorMessages
# ---------------------------------------------------------------------------

class TestErrorMessages:
    """Card data in exceptions and error responses."""

    def test_card_in_exception(self, tmp_path):
        findings = _scan(tmp_path, {
            "handler.py": """
                def process(card_number):
                    raise ValueError(f"Invalid card: {card_number}")
            """,
        })
        assert any(f.rule_id == "PCI-3.4" and "exception" in f.description.lower() for f in findings)

    def test_safe_exception_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "handler_ok.py": """
                def process(order_id):
                    raise ValueError(f"Invalid order: {order_id}")
            """,
        })
        error_findings = [f for f in findings if "exception" in f.description.lower()]
        assert len(error_findings) == 0


# ---------------------------------------------------------------------------
# TestAccessControl
# ---------------------------------------------------------------------------

class TestAccessControl:
    """Payment endpoints without auth/rate limiting."""

    def test_payment_endpoint_no_auth(self, tmp_path):
        findings = _scan(tmp_path, {
            "routes.py": """
                from fastapi import APIRouter
                router = APIRouter()

                @router.post("/api/v1/payment/charge")
                def charge(data: dict):
                    pass
            """,
        })
        assert any(f.rule_id == "PCI-6.5.10" and "authentication" in f.description.lower() for f in findings)

    def test_payment_endpoint_with_auth(self, tmp_path):
        findings = _scan(tmp_path, {
            "routes_ok.py": """
                from fastapi import APIRouter, Depends
                router = APIRouter()

                @requires_auth
                @router.post("/api/v1/payment/charge")
                def charge(data: dict):
                    pass
            """,
        })
        auth_findings = [f for f in findings if f.rule_id == "PCI-6.5.10" and "authentication" in f.description.lower()]
        assert len(auth_findings) == 0

    def test_payment_endpoint_no_rate_limit(self, tmp_path):
        findings = _scan(tmp_path, {
            "routes_nrl.py": """
                from fastapi import APIRouter
                router = APIRouter()

                @requires_auth
                @router.post("/api/v1/checkout/validate")
                def validate(data: dict):
                    pass
            """,
        })
        rl = [f for f in findings if "rate limit" in f.description.lower()]
        assert len(rl) > 0


# ---------------------------------------------------------------------------
# TestTokenization
# ---------------------------------------------------------------------------

class TestTokenization:
    """Raw PAN storage detection."""

    def test_db_column_raw_pan(self, tmp_path):
        findings = _scan(tmp_path, {
            "models.py": """
                from sqlalchemy import Column, String
                class Payment(Base):
                    card_number = Column('card_number', String(19))
            """,
        })
        assert any(f.rule_id == "PCI-3.4" and "database" in f.description.lower() for f in findings)

    def test_pan_literal_assignment(self, tmp_path):
        findings = _scan(tmp_path, {
            "test_data.py": """
                card_number = "4111111111111111"
            """,
        })
        assert any(f.rule_id == "PCI-3.4" and "literal" in f.description.lower() for f in findings)


# ---------------------------------------------------------------------------
# TestScore
# ---------------------------------------------------------------------------

class TestScore:
    """Score calculation from findings."""

    def test_perfect_score(self):
        score = PCIComplianceScanner._calculate_score([])
        assert score == 100

    def test_critical_deduction(self):
        findings = [
            PCIFinding("f.py", 1, "PCI-3.4", "critical", "desc", "fix")
            for _ in range(2)
        ]
        score = PCIComplianceScanner._calculate_score(findings)
        assert score == 100 - (2 * 15)  # 70

    def test_mixed_deduction(self):
        findings = [
            PCIFinding("f.py", 1, "PCI-3.4", "critical", "d", "f"),
            PCIFinding("f.py", 2, "PCI-4.1", "high", "d", "f"),
            PCIFinding("f.py", 3, "PCI-6.5.3", "medium", "d", "f"),
        ]
        score = PCIComplianceScanner._calculate_score(findings)
        assert score == 100 - 15 - 8 - 3  # 74

    def test_score_floor_at_zero(self):
        # Max deductions: critical=60, high=40 => total 100 => score 0
        findings = [
            PCIFinding("f.py", i, "PCI-3.4", "critical", "d", "f")
            for i in range(5)
        ] + [
            PCIFinding("f.py", i, "PCI-4.1", "high", "d", "f")
            for i in range(6)
        ]
        score = PCIComplianceScanner._calculate_score(findings)
        assert score == 0


# ---------------------------------------------------------------------------
# TestFormatReport
# ---------------------------------------------------------------------------

class TestFormatReport:
    """Terminal report formatting."""

    def test_report_contains_title(self):
        report = PCIReport(
            findings=[],
            score=100,
            passed_rules=list(PCI_RULES.keys()),
            failed_rules=[],
            summary="Score: 100/100",
            scan_time=0.5,
        )
        output = format_pci_report(report, use_color=False)
        assert "PCI-DSS Compliance Scan" in output

    def test_report_contains_score(self):
        report = PCIReport(
            findings=[
                PCIFinding("x.py", 1, "PCI-3.4", "critical", "test desc", "test fix", "snippet"),
            ],
            score=85,
            passed_rules=["PCI-4.1"],
            failed_rules=["PCI-3.4"],
            summary="Score: 85/100",
            scan_time=0.1,
        )
        output = format_pci_report(report, use_color=False)
        assert "85/100" in output
        assert "PCI-3.4" in output
        assert "test desc" in output
        assert "test fix" in output

    def test_report_no_findings(self):
        report = PCIReport(
            findings=[],
            score=100,
            passed_rules=list(PCI_RULES.keys()),
            failed_rules=[],
            summary="Score: 100/100",
            scan_time=0.05,
        )
        output = format_pci_report(report, use_color=False)
        assert "No PCI-DSS violations found" in output

    def test_report_passed_and_failed_rules(self):
        report = PCIReport(
            findings=[
                PCIFinding("a.py", 1, "PCI-4.1", "high", "insecure", "fix"),
            ],
            score=92,
            passed_rules=["PCI-3.4", "PCI-6.5.1"],
            failed_rules=["PCI-4.1"],
            summary="",
            scan_time=0.01,
        )
        output = format_pci_report(report, use_color=False)
        assert "OK" in output
        assert "FAIL" in output

    def test_json_serialization(self):
        report = PCIReport(
            findings=[
                PCIFinding("a.py", 10, "PCI-3.4", "critical", "desc", "fix", "snip"),
            ],
            score=85,
            passed_rules=["PCI-4.1"],
            failed_rules=["PCI-3.4"],
            summary="Score: 85/100",
            scan_time=0.1,
        )
        data = pci_report_to_json(report)
        assert data["score"] == 85
        assert len(data["findings"]) == 1
        assert data["findings"][0]["rule_id"] == "PCI-3.4"
        assert data["findings"][0]["file"] == "a.py"


# ---------------------------------------------------------------------------
# TestFullScan
# ---------------------------------------------------------------------------

class TestFullScan:
    """End-to-end scan with multiple violation types."""

    def test_multi_violation_project(self, tmp_path):
        root = _create_project(tmp_path, {
            "payment/handler.py": """
                import hashlib
                import logging
                import requests

                logger = logging.getLogger(__name__)

                AES_KEY = "abcdef0123456789abcdef0123456789"

                def charge(card_number):
                    logger.info(f"Charging card {card_number}")
                    h = hashlib.md5(card_number.encode())
                    resp = requests.post("http://gateway.internal/payment/charge", verify=False)
                    return resp
            """,
        })
        scanner = PCIComplianceScanner(cwd=root)
        report = scanner.scan()

        assert report.score < 80
        rule_ids = {f.rule_id for f in report.findings}
        assert "PCI-3.4" in rule_ids      # PAN in logs
        assert "PCI-4.1" in rule_ids      # HTTP + verify=False
        assert "PCI-6.5.3" in rule_ids    # hardcoded key

    def test_clean_project(self, tmp_path):
        root = _create_project(tmp_path, {
            "app.py": """
                import os
                import logging

                logger = logging.getLogger(__name__)

                def process_order(order_id: str):
                    logger.info("Processing order %s", order_id)
                    return {"status": "ok"}
            """,
        })
        scanner = PCIComplianceScanner(cwd=root)
        report = scanner.scan()
        assert report.score == 100
        assert len(report.findings) == 0

    def test_scan_skips_node_modules(self, tmp_path):
        root = _create_project(tmp_path, {
            "node_modules/pkg/bad.py": """
                import hashlib
                h = hashlib.md5(password)
            """,
            "src/clean.py": """
                x = 1
            """,
        })
        scanner = PCIComplianceScanner(cwd=root)
        report = scanner.scan()
        # Should not scan node_modules
        assert all("node_modules" not in f.file for f in report.findings)
