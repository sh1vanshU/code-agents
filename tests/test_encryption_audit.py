"""Tests for code_agents.encryption_audit — encryption pattern auditor."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from code_agents.security.encryption_audit import (
    EncryptionAuditor,
    EncryptionFinding,
    _redact,
    format_encryption_report,
    encryption_report_to_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp: str, name: str, content: str) -> Path:
    p = Path(tmp) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# EncryptionFinding dataclass
# ---------------------------------------------------------------------------


class TestEncryptionFinding:
    def test_basic_creation(self):
        f = EncryptionFinding(
            file="app.py", line=10, issue="Weak hash",
            severity="high", remediation="Use SHA-256",
        )
        assert f.file == "app.py"
        assert f.line == 10
        assert f.severity == "high"
        assert f.code_snippet == ""

    def test_with_snippet(self):
        f = EncryptionFinding(
            file="x.py", line=1, issue="test", severity="low",
            remediation="fix", code_snippet="hashlib.md5(data)",
        )
        assert f.code_snippet == "hashlib.md5(data)"


# ---------------------------------------------------------------------------
# Weak hash detection
# ---------------------------------------------------------------------------


class TestWeakHash:
    def test_md5_python(self, tmp_path):
        _write(str(tmp_path), "auth.py", "import hashlib\nhash = hashlib.md5(password.encode())\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("MD5" in f.issue for f in findings)

    def test_sha1_python(self, tmp_path):
        _write(str(tmp_path), "util.py", "digest = hashlib.sha1(key)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("SHA1" in f.issue for f in findings)

    def test_md5_java(self, tmp_path):
        _write(str(tmp_path), "Auth.java",
               'MessageDigest md = MessageDigest.getInstance("MD5");\n')
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("MD5" in f.issue for f in findings)

    def test_crypto_createhash_js(self, tmp_path):
        _write(str(tmp_path), "hash.js",
               "const hash = crypto.createHash('sha1');\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("SHA1" in f.issue for f in findings)

    def test_no_false_positive_sha256(self, tmp_path):
        _write(str(tmp_path), "safe.py", "digest = hashlib.sha256(data)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert not any("Weak hash" in f.issue for f in findings)


# ---------------------------------------------------------------------------
# Weak cipher detection
# ---------------------------------------------------------------------------


class TestWeakCipher:
    def test_des_detected(self, tmp_path):
        _write(str(tmp_path), "crypto.py", "from Crypto.Cipher import DES\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("DES" in f.issue for f in findings)

    def test_3des_detected(self, tmp_path):
        _write(str(tmp_path), "crypto.py", "cipher = TripleDES.new(key)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("3DES" in f.issue for f in findings)

    def test_rc4_detected(self, tmp_path):
        _write(str(tmp_path), "stream.py", "cipher = ARC4.new(key)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("RC4" in f.issue for f in findings)

    def test_blowfish_detected(self, tmp_path):
        _write(str(tmp_path), "old.py", "cipher = Blowfish.new(key)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("Blowfish" in f.issue for f in findings)

    def test_severity_is_critical(self, tmp_path):
        _write(str(tmp_path), "weak.py", "cipher = DES.new(key)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        cipher_findings = [f for f in findings if "cipher" in f.issue.lower()]
        assert all(f.severity == "critical" for f in cipher_findings)


# ---------------------------------------------------------------------------
# ECB mode detection
# ---------------------------------------------------------------------------


class TestECBMode:
    def test_python_ecb(self, tmp_path):
        _write(str(tmp_path), "enc.py", "cipher = AES.new(key, AES.MODE_ECB)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("ECB" in f.issue for f in findings)

    def test_java_ecb(self, tmp_path):
        _write(str(tmp_path), "Enc.java",
               'Cipher cipher = Cipher.getInstance("AES/ECB/PKCS5Padding");\n')
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("ECB" in f.issue for f in findings)

    def test_ecb_severity_critical(self, tmp_path):
        _write(str(tmp_path), "ecb.py", "mode = AES.MODE_ECB\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        ecb_findings = [f for f in findings if "ECB" in f.issue]
        assert all(f.severity == "critical" for f in ecb_findings)


# ---------------------------------------------------------------------------
# Small key sizes
# ---------------------------------------------------------------------------


class TestSmallKeys:
    def test_small_symmetric_key(self, tmp_path):
        _write(str(tmp_path), "gen.py", "cipher = AES(key_size=64)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("key size" in f.issue.lower() for f in findings)

    def test_small_rsa_key(self, tmp_path):
        _write(str(tmp_path), "rsa.py",
               "key = rsa.generate_private_key(public_exponent=65537, key_size=1024)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("1024" in f.issue for f in findings)

    def test_adequate_key_no_finding(self, tmp_path):
        _write(str(tmp_path), "safe.py", "cipher = AES(key_size=256)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert not any("key size" in f.issue.lower() for f in findings)


# ---------------------------------------------------------------------------
# Static IV
# ---------------------------------------------------------------------------


class TestStaticIV:
    def test_hardcoded_iv_string(self, tmp_path):
        _write(str(tmp_path), "enc.py", 'iv = b"0000000000000000"\n')
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("IV" in f.issue or "iv" in f.issue.lower() for f in findings)

    def test_zero_bytes_iv(self, tmp_path):
        _write(str(tmp_path), "enc.py", "iv = bytes(16)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("Static" in f.issue or "IV" in f.issue for f in findings)


# ---------------------------------------------------------------------------
# Hardcoded keys
# ---------------------------------------------------------------------------


class TestHardcodedKeys:
    def test_hardcoded_secret_key(self, tmp_path):
        _write(str(tmp_path), "config.py",
               'secret_key = "my_super_secret_encryption_key_12345"\n')
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("Hardcoded" in f.issue for f in findings)

    def test_hardcoded_bytes_key(self, tmp_path):
        _write(str(tmp_path), "config.py",
               'encryption_key = b"abcdef1234567890abcdef"\n')
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("Hardcoded" in f.issue for f in findings)

    def test_severity_is_critical(self, tmp_path):
        _write(str(tmp_path), "bad.py",
               'aes_key = "hardcoded_key_that_is_long_enough"\n')
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        key_findings = [f for f in findings if "Hardcoded" in f.issue]
        assert all(f.severity == "critical" for f in key_findings)


# ---------------------------------------------------------------------------
# Weak KDF
# ---------------------------------------------------------------------------


class TestWeakKDF:
    def test_md5_password_hash(self, tmp_path):
        _write(str(tmp_path), "auth.py",
               "hashed = password_md5(user_password)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("KDF" in f.issue for f in findings)

    def test_sha256_password(self, tmp_path):
        _write(str(tmp_path), "auth.py",
               "h = hashlib.sha256(password.encode()).hexdigest()\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("KDF" in f.issue or "SHA" in f.issue for f in findings)


# ---------------------------------------------------------------------------
# Empty project
# ---------------------------------------------------------------------------


class TestEmptyProject:
    def test_no_findings_empty_dir(self, tmp_path):
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert findings == []

    def test_safe_code_no_findings(self, tmp_path):
        _write(str(tmp_path), "safe.py", "print('hello world')\nx = 42\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert findings == []


# ---------------------------------------------------------------------------
# Skip directories
# ---------------------------------------------------------------------------


class TestSkipDirs:
    def test_node_modules_skipped(self, tmp_path):
        _write(str(tmp_path), "node_modules/dep/bad.js",
               "var h = crypto.createHash('md5');\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert findings == []

    def test_git_dir_skipped(self, tmp_path):
        _write(str(tmp_path), ".git/hooks/pre-commit.py",
               "hashlib.md5(data)\n")
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert findings == []


# ---------------------------------------------------------------------------
# Redact helper
# ---------------------------------------------------------------------------


class TestRedact:
    def test_redacts_long_strings(self):
        line = 'secret_key = "abcdefghijklmnopqrstuvwxyz1234567890"'
        redacted = _redact(line)
        assert "<REDACTED>" in redacted

    def test_short_strings_preserved(self):
        line = 'x = "short"'
        redacted = _redact(line)
        assert "short" in redacted

    def test_long_lines_truncated(self):
        line = "x = " + "a" * 200
        redacted = _redact(line)
        assert len(redacted) <= 130  # 120 + "..."


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


class TestFormatters:
    def test_text_report_empty(self):
        report = format_encryption_report([])
        assert "No encryption issues" in report

    def test_text_report_with_findings(self):
        findings = [
            EncryptionFinding("a.py", 1, "Weak hash (MD5)", "high", "Use SHA-256"),
            EncryptionFinding("b.py", 5, "ECB mode", "critical", "Use GCM"),
        ]
        report = format_encryption_report(findings)
        assert "2 finding" in report
        assert "a.py:1" in report
        assert "b.py:5" in report

    def test_json_report_structure(self):
        findings = [
            EncryptionFinding("x.py", 10, "issue", "medium", "fix", "code"),
        ]
        data = encryption_report_to_json(findings)
        assert data["total"] == 1
        assert "medium" in data["by_severity"]
        assert data["findings"][0]["file"] == "x.py"
        assert data["findings"][0]["line"] == 10
        assert data["findings"][0]["code_snippet"] == "code"

    def test_json_report_empty(self):
        data = encryption_report_to_json([])
        assert data["total"] == 0
        assert data["findings"] == []

    def test_severity_summary_in_text(self):
        findings = [
            EncryptionFinding("a.py", 1, "issue1", "critical", "fix"),
            EncryptionFinding("b.py", 2, "issue2", "critical", "fix"),
            EncryptionFinding("c.py", 3, "issue3", "high", "fix"),
        ]
        report = format_encryption_report(findings)
        assert "critical: 2" in report
        assert "high: 1" in report


# ---------------------------------------------------------------------------
# Multiple findings in one file
# ---------------------------------------------------------------------------


class TestMultipleFindings:
    def test_multiple_issues_same_file(self, tmp_path):
        code = (
            "import hashlib\n"
            "h = hashlib.md5(data)\n"
            "cipher = AES.new(key, AES.MODE_ECB)\n"
            'secret_key = "hardcoded_secret_key_abcdef1234"\n'
        )
        _write(str(tmp_path), "multi.py", code)
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert len(findings) >= 3

    def test_findings_have_correct_lines(self, tmp_path):
        code = "line1\nhashlib.md5(x)\nline3\nAES.MODE_ECB\n"
        _write(str(tmp_path), "lines.py", code)
        auditor = EncryptionAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        lines_found = {f.line for f in findings}
        assert 2 in lines_found
        assert 4 in lines_found
