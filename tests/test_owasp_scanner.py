"""Tests for code_agents.owasp_scanner — OWASP Top 10 security scanner."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from code_agents.security.owasp_scanner import (
    OWASPScanner,
    OWASPFinding,
    OWASPReport,
    OWASP_RULES,
    format_owasp_report,
    owasp_report_to_json,
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


def _scan(tmp_path: Path, files: dict[str, str]) -> list[OWASPFinding]:
    """Create project, scan, return findings."""
    root = _create_project(tmp_path, files)
    scanner = OWASPScanner(cwd=root)
    report = scanner.scan()
    return report.findings


# ---------------------------------------------------------------------------
# A01 — Broken Access Control
# ---------------------------------------------------------------------------

class TestAccessControl:
    """A01: Missing auth, IDOR, CORS wildcard."""

    def test_endpoint_without_auth(self, tmp_path):
        findings = _scan(tmp_path, {
            "api.py": """
                from fastapi import FastAPI
                app = FastAPI()
                @app.get("/users")
                def list_users():
                    return []
            """,
        })
        assert any(f.rule_id == "A01" and "authentication" in f.description.lower() for f in findings)

    def test_endpoint_with_auth_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "api.py": """
                from fastapi import FastAPI, Depends
                app = FastAPI()
                @Depends(get_current_user)
                @app.get("/users")
                def list_users():
                    return []
            """,
        })
        auth_findings = [f for f in findings if f.rule_id == "A01" and "authentication" in f.description.lower()]
        assert len(auth_findings) == 0

    def test_idor_pattern(self, tmp_path):
        findings = _scan(tmp_path, {
            "views.py": """
                def get_order(request):
                    order_id = request.args.get('id')
                    return Order.query.get(order_id)
            """,
        })
        assert any(f.rule_id == "A01" and "IDOR" in f.description for f in findings)

    def test_cors_wildcard(self, tmp_path):
        findings = _scan(tmp_path, {
            "config.py": """
                allow_origins = ["*"]
            """,
        })
        assert any(f.rule_id == "A01" and "CORS" in f.description for f in findings)


# ---------------------------------------------------------------------------
# A02 — Cryptographic Failures
# ---------------------------------------------------------------------------

class TestCryptoFailures:
    """A02: Weak hash, hardcoded keys, weak ciphers."""

    def test_md5_detected(self, tmp_path):
        findings = _scan(tmp_path, {
            "crypto.py": """
                import hashlib
                h = hashlib.md5(data)
            """,
        })
        assert any(f.rule_id == "A02" and "MD5" in f.description for f in findings)

    def test_sha1_detected(self, tmp_path):
        findings = _scan(tmp_path, {
            "hash.py": """
                import hashlib
                h = hashlib.sha1(data)
            """,
        })
        assert any(f.rule_id == "A02" and "SHA1" in f.description for f in findings)

    def test_hardcoded_key(self, tmp_path):
        findings = _scan(tmp_path, {
            "config.py": """
                SECRET_KEY = "abcdefghijklmnopqrstuvwxyz123456"
            """,
        })
        assert any(f.rule_id == "A02" and "Hardcoded" in f.description for f in findings)

    def test_ecb_mode(self, tmp_path):
        findings = _scan(tmp_path, {
            "enc.py": """
                from Crypto.Cipher import AES
                cipher = AES.new(key, AES.MODE_ECB)
            """,
        })
        assert any(f.rule_id == "A02" and "ECB" in f.description for f in findings)

    def test_small_key_size(self, tmp_path):
        findings = _scan(tmp_path, {
            "keys.py": """
                key = generate_key(key_size=64)
            """,
        })
        assert any(f.rule_id == "A02" and "key size" in f.description.lower() for f in findings)

    def test_strong_cipher_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "enc.py": """
                from Crypto.Cipher import AES
                cipher = AES.new(key, AES.MODE_GCM)
            """,
        })
        crypto_findings = [f for f in findings if f.rule_id == "A02"]
        assert len(crypto_findings) == 0


# ---------------------------------------------------------------------------
# A03 — Injection
# ---------------------------------------------------------------------------

class TestInjection:
    """A03: SQL concat, eval/exec, shell=True, os.system."""

    def test_sql_fstring(self, tmp_path):
        findings = _scan(tmp_path, {
            "db.py": """
                def get_user(name):
                    cursor.execute(f"SELECT * FROM users WHERE name = '{name}'")
            """,
        })
        assert any(f.rule_id == "A03" and "SQL" in f.description for f in findings)

    def test_eval_detected(self, tmp_path):
        findings = _scan(tmp_path, {
            "handler.py": """
                def run(code):
                    result = eval(code)
            """,
        })
        assert any(f.rule_id == "A03" and "eval" in f.description for f in findings)

    def test_exec_detected(self, tmp_path):
        findings = _scan(tmp_path, {
            "run.py": """
                def execute(code):
                    exec(code)
            """,
        })
        assert any(f.rule_id == "A03" and "eval" in f.description.lower() or "exec" in f.description.lower() for f in findings)

    def test_shell_true(self, tmp_path):
        findings = _scan(tmp_path, {
            "cmd.py": """
                import subprocess
                subprocess.run(cmd, shell=True)
            """,
        })
        assert any(f.rule_id == "A03" and "shell" in f.description.lower() for f in findings)

    def test_os_system(self, tmp_path):
        findings = _scan(tmp_path, {
            "cmd.py": """
                import os
                os.system(user_input)
            """,
        })
        assert any(f.rule_id == "A03" and "os.system" in f.description for f in findings)

    def test_parameterized_query_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "db.py": """
                def get_user(name):
                    cursor.execute("SELECT * FROM users WHERE name = %s", (name,))
            """,
        })
        sql_findings = [f for f in findings if f.rule_id == "A03" and "SQL" in f.description]
        assert len(sql_findings) == 0


# ---------------------------------------------------------------------------
# A04 — Insecure Design
# ---------------------------------------------------------------------------

class TestInsecureDesign:
    """A04: CSRF exempt, missing rate limit on auth endpoints."""

    def test_csrf_exempt(self, tmp_path):
        findings = _scan(tmp_path, {
            "views.py": """
                @csrf_exempt
                def submit(request):
                    pass
            """,
        })
        assert any(f.rule_id == "A04" and "CSRF" in f.description for f in findings)

    def test_auth_endpoint_no_rate_limit(self, tmp_path):
        findings = _scan(tmp_path, {
            "auth.py": """
                from fastapi import FastAPI
                app = FastAPI()
                @app.post("/login")
                def login():
                    pass
            """,
        })
        assert any(f.rule_id == "A04" and "rate limit" in f.description.lower() for f in findings)


# ---------------------------------------------------------------------------
# A05 — Security Misconfiguration
# ---------------------------------------------------------------------------

class TestMisconfig:
    """A05: DEBUG=True, default passwords, verbose errors."""

    def test_debug_true(self, tmp_path):
        findings = _scan(tmp_path, {
            "settings.py": """
                DEBUG = True
            """,
        })
        assert any(f.rule_id == "A05" and "Debug" in f.description for f in findings)

    def test_default_password(self, tmp_path):
        findings = _scan(tmp_path, {
            "config.py": """
                password = "admin"
            """,
        })
        assert any(f.rule_id == "A05" and "Default" in f.description for f in findings)

    def test_debug_in_test_file_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "test_settings.py": """
                DEBUG = True
            """,
        })
        debug_findings = [f for f in findings if f.rule_id == "A05" and "Debug" in f.description]
        assert len(debug_findings) == 0


# ---------------------------------------------------------------------------
# A06 — Vulnerable Components
# ---------------------------------------------------------------------------

class TestVulnerableComponents:
    """A06: Known vulnerable versions in requirements."""

    def test_old_django(self, tmp_path):
        findings = _scan(tmp_path, {
            "requirements.txt": """
                django==3.2.0
                requests==2.28.0
            """,
        })
        assert any(f.rule_id == "A06" and "django" in f.description.lower() for f in findings)

    def test_old_requests(self, tmp_path):
        findings = _scan(tmp_path, {
            "requirements.txt": """
                requests==2.20.0
            """,
        })
        assert any(f.rule_id == "A06" and "requests" in f.description.lower() for f in findings)

    def test_safe_versions_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "requirements.txt": """
                django==5.0.0
                requests==2.32.0
            """,
        })
        vuln_findings = [f for f in findings if f.rule_id == "A06"]
        assert len(vuln_findings) == 0


# ---------------------------------------------------------------------------
# A07 — Authentication Failures
# ---------------------------------------------------------------------------

class TestAuthFailures:
    """A07: Plaintext password comparison, weak JWT."""

    def test_plaintext_password_comparison(self, tmp_path):
        findings = _scan(tmp_path, {
            "auth.py": """
                def check(user, pw):
                    if password == "secret123":
                        return True
            """,
        })
        assert any(f.rule_id == "A07" and "Plaintext" in f.description for f in findings)

    def test_weak_jwt_none(self, tmp_path):
        findings = _scan(tmp_path, {
            "jwt_util.py": """
                import jwt
                token = jwt.encode(payload, key, algorithm="none")
            """,
        })
        assert any(f.rule_id == "A07" and "JWT" in f.description for f in findings)


# ---------------------------------------------------------------------------
# A08 — Software Integrity Failures
# ---------------------------------------------------------------------------

class TestIntegrity:
    """A08: pickle.load, yaml.load without SafeLoader."""

    def test_pickle_load(self, tmp_path):
        findings = _scan(tmp_path, {
            "data.py": """
                import pickle
                obj = pickle.load(f)
            """,
        })
        assert any(f.rule_id == "A08" and "pickle" in f.description for f in findings)

    def test_pickle_loads(self, tmp_path):
        findings = _scan(tmp_path, {
            "data.py": """
                import pickle
                obj = pickle.loads(data)
            """,
        })
        assert any(f.rule_id == "A08" and "pickle" in f.description for f in findings)

    def test_yaml_load_unsafe(self, tmp_path):
        findings = _scan(tmp_path, {
            "config.py": """
                import yaml
                data = yaml.load(open("config.yml"))
            """,
        })
        assert any(f.rule_id == "A08" and "yaml" in f.description.lower() for f in findings)

    def test_yaml_safe_load_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "config.py": """
                import yaml
                data = yaml.safe_load(open("config.yml"))
            """,
        })
        yaml_findings = [f for f in findings if f.rule_id == "A08" and "yaml" in f.description.lower()]
        assert len(yaml_findings) == 0


# ---------------------------------------------------------------------------
# A09 — Logging Failures
# ---------------------------------------------------------------------------

class TestLoggingFailures:
    """A09: PII in logs, sensitive data in logs."""

    def test_password_in_log(self, tmp_path):
        findings = _scan(tmp_path, {
            "auth.py": """
                import logging
                logger = logging.getLogger(__name__)
                def login(user, password):
                    logger.info("Login attempt with password %s", password)
            """,
        })
        assert any(f.rule_id == "A09" for f in findings)

    def test_token_in_log(self, tmp_path):
        findings = _scan(tmp_path, {
            "api.py": """
                import logging
                logger = logging.getLogger(__name__)
                def refresh(token):
                    logger.debug("Refreshing token %s", token)
            """,
        })
        assert any(f.rule_id == "A09" for f in findings)

    def test_safe_logging_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "app.py": """
                import logging
                logger = logging.getLogger(__name__)
                def process(order_id):
                    logger.info("Processing order %s", order_id)
            """,
        })
        log_findings = [f for f in findings if f.rule_id == "A09"]
        assert len(log_findings) == 0


# ---------------------------------------------------------------------------
# A10 — SSRF
# ---------------------------------------------------------------------------

class TestSSRF:
    """A10: User-controlled URLs without validation."""

    def test_url_from_request(self, tmp_path):
        findings = _scan(tmp_path, {
            "proxy.py": """
                def fetch(request):
                    url = request.args.get('url')
                    return requests.get(url)
            """,
        })
        assert any(f.rule_id == "A10" for f in findings)

    def test_url_with_validation_no_finding(self, tmp_path):
        findings = _scan(tmp_path, {
            "proxy.py": """
                def fetch(request):
                    url = request.args.get('url')
                    if not is_safe_url(url):
                        return error()
                    return requests.get(url)
            """,
        })
        ssrf_findings = [f for f in findings if f.rule_id == "A10"]
        assert len(ssrf_findings) == 0


# ---------------------------------------------------------------------------
# Report / Score
# ---------------------------------------------------------------------------

class TestReportAndScore:
    """Report formatting and scoring logic."""

    def test_clean_project_score_100(self, tmp_path):
        root = _create_project(tmp_path, {
            "app.py": """
                import logging
                logger = logging.getLogger(__name__)
                def hello():
                    logger.info("Hello world")
            """,
        })
        scanner = OWASPScanner(cwd=root)
        report = scanner.scan()
        assert report.score == 100
        assert len(report.findings) == 0
        assert len(report.passed) == 10

    def test_score_decreases_with_findings(self, tmp_path):
        root = _create_project(tmp_path, {
            "bad.py": """
                import hashlib
                h = hashlib.md5(data)
                result = eval(user_input)
            """,
        })
        scanner = OWASPScanner(cwd=root)
        report = scanner.scan()
        assert report.score < 100
        assert len(report.findings) > 0

    def test_format_report_text(self, tmp_path):
        root = _create_project(tmp_path, {
            "bad.py": """
                result = eval(code)
            """,
        })
        scanner = OWASPScanner(cwd=root)
        report = scanner.scan()
        text = format_owasp_report(report)
        assert "OWASP Top 10" in text
        assert "Score:" in text

    def test_format_report_no_color(self, tmp_path):
        root = _create_project(tmp_path, {
            "clean.py": """
                x = 1 + 2
            """,
        })
        scanner = OWASPScanner(cwd=root)
        report = scanner.scan()
        text = format_owasp_report(report, use_color=False)
        assert "\033[" not in text

    def test_report_to_json(self, tmp_path):
        root = _create_project(tmp_path, {
            "bad.py": """
                result = eval(code)
            """,
        })
        scanner = OWASPScanner(cwd=root)
        report = scanner.scan()
        data = owasp_report_to_json(report)
        assert "score" in data
        assert "findings" in data
        assert "passed" in data
        assert "failed" in data
        assert isinstance(data["findings"], list)

    def test_summary_format(self, tmp_path):
        root = _create_project(tmp_path, {"clean.py": "x = 1"})
        scanner = OWASPScanner(cwd=root)
        report = scanner.scan()
        assert "Score:" in report.summary
        assert "100/100" in report.summary

    def test_owasp_rules_has_10(self):
        assert len(OWASP_RULES) == 10
        assert "A01" in OWASP_RULES
        assert "A10" in OWASP_RULES

    def test_skip_dirs(self, tmp_path):
        """node_modules and .git should be skipped."""
        root = _create_project(tmp_path, {
            "node_modules/bad.py": """
                result = eval(code)
            """,
            "src/good.py": """
                x = 1
            """,
        })
        scanner = OWASPScanner(cwd=root)
        report = scanner.scan()
        # Should NOT find anything in node_modules
        assert not any("node_modules" in f.file for f in report.findings)

    def test_version_below_comparison(self):
        assert OWASPScanner._version_below("3.2", "4.2") is True
        assert OWASPScanner._version_below("5.0", "4.2") is False
        assert OWASPScanner._version_below("4.2", "4.2") is False
        assert OWASPScanner._version_below("4.1", "4.2") is True
