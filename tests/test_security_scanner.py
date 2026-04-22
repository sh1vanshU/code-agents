"""Tests for security_scanner.py — OWASP top 10 static analysis."""

import os
import tempfile
from pathlib import Path

import pytest

from code_agents.analysis.security_scanner import (
    SecurityFinding,
    SecurityReport,
    SecurityScanner,
    format_security_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_repo(tmp_path):
    """Empty repo with no source files."""
    return tmp_path


@pytest.fixture
def secret_repo(tmp_path):
    """Repo with hardcoded secrets."""
    (tmp_path / "config.py").write_text(
        'DB_HOST = "localhost"\n'
        'password = "super_secret_123"\n'
        'api_key = "sk-abcdefghijklmnopqrstuvwxyz1234567890"\n'
        "SAFE_VAR = 42\n"
    )
    (tmp_path / "keys.yaml").write_text(
        "aws_access_key_id: AKIAIOSFODNN7EXAMPLE\n"
    )
    (tmp_path / "cert.py").write_text(
        "key = '''-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBA...'''\n"
    )
    # GitHub token
    (tmp_path / "deploy.py").write_text(
        'token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh"\n'
    )
    return tmp_path


@pytest.fixture
def sql_repo(tmp_path):
    """Repo with SQL injection vulnerabilities."""
    (tmp_path / "db.py").write_text(
        'def get_user(name):\n'
        '    cursor.execute("SELECT * FROM users WHERE name = \'%s\'" % name)\n'
    )
    (tmp_path / "query.py").write_text(
        'def search(term):\n'
        '    cursor.execute(f"SELECT * FROM items WHERE title = \'{term}\'")\n'
    )
    (tmp_path / "dao.py").write_text(
        'def find(id):\n'
        '    cursor.execute("SELECT * FROM orders WHERE id = " + str(id))\n'
    )
    return tmp_path


@pytest.fixture
def xss_repo(tmp_path):
    """Repo with XSS vulnerabilities."""
    (tmp_path / "app.js").write_text(
        'document.getElementById("out").innerHTML = userInput;\n'
        'document.write(data);\n'
    )
    (tmp_path / "component.tsx").write_text(
        '<div dangerouslySetInnerHTML={{__html: content}} />\n'
    )
    (tmp_path / "template.html").write_text(
        '<div v-html="rawHtml"></div>\n'
    )
    return tmp_path


@pytest.fixture
def crypto_repo(tmp_path):
    """Repo with insecure crypto."""
    (tmp_path / "hash.py").write_text(
        'import hashlib\n'
        'h = hashlib.MD5(data)\n'
    )
    (tmp_path / "cipher.java").write_text(
        'Cipher c = Cipher.getInstance("DES/ECB/PKCS5Padding");\n'
    )
    (tmp_path / "rand.js").write_text(
        'var token = Math.random().toString(36);\n'
    )
    return tmp_path


@pytest.fixture
def cmdi_repo(tmp_path):
    """Repo with command injection risks."""
    (tmp_path / "runner.py").write_text(
        'import os\n'
        'os.system("ls -la " + user_path)\n'
        'subprocess.run(cmd, shell=True)\n'
    )
    (tmp_path / "unsafe.js").write_text(
        'eval(user_input + ".method()");\n'
    )
    return tmp_path


@pytest.fixture
def path_repo(tmp_path):
    """Repo with path traversal risks."""
    (tmp_path / "serve.py").write_text(
        'f = open("/data/" + filename)\n'
    )
    return tmp_path


@pytest.fixture
def dep_repo(tmp_path):
    """Repo with insecure dependencies."""
    (tmp_path / "requirements.txt").write_text(
        'django==1.8\n'
        'flask==0.12\n'
        'requests==2.28.0\n'
    )
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"lodash": "^3.10.0", "express": "^3.0.0"}}\n'
    )
    return tmp_path


@pytest.fixture
def exposure_repo(tmp_path):
    """Repo with sensitive data exposure."""
    (tmp_path / "auth.py").write_text(
        'logger.info("User login with password: " + password)\n'
    )
    (tmp_path / "cors.java").write_text(
        'response.setHeader("Access-Control-Allow-Origin", "*");\n'
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Hardcoded secret detection
# ---------------------------------------------------------------------------

class TestHardcodedSecrets:
    def test_detects_password(self, secret_repo):
        scanner = SecurityScanner(str(secret_repo))
        report = scanner.scan()
        pwd_findings = [f for f in report.findings if "password" in f.description.lower()]
        assert len(pwd_findings) >= 1
        assert pwd_findings[0].severity == "CRITICAL"
        assert pwd_findings[0].category == "hardcoded-secret"

    def test_detects_api_key(self, secret_repo):
        scanner = SecurityScanner(str(secret_repo))
        report = scanner.scan()
        key_findings = [f for f in report.findings if "API" in f.description]
        assert len(key_findings) >= 1

    def test_detects_aws_key(self, secret_repo):
        scanner = SecurityScanner(str(secret_repo))
        report = scanner.scan()
        aws_findings = [f for f in report.findings if "AWS" in f.description]
        assert len(aws_findings) >= 1

    def test_detects_private_key(self, secret_repo):
        scanner = SecurityScanner(str(secret_repo))
        report = scanner.scan()
        pk_findings = [f for f in report.findings if "Private key" in f.description]
        assert len(pk_findings) >= 1

    def test_detects_github_token(self, secret_repo):
        scanner = SecurityScanner(str(secret_repo))
        report = scanner.scan()
        gh_findings = [f for f in report.findings if "GitHub" in f.description]
        assert len(gh_findings) >= 1


# ---------------------------------------------------------------------------
# SQL injection detection
# ---------------------------------------------------------------------------

class TestSQLInjection:
    def test_detects_string_format(self, sql_repo):
        scanner = SecurityScanner(str(sql_repo))
        report = scanner.scan()
        sql_findings = [f for f in report.findings if f.category == "sql-injection"]
        assert len(sql_findings) >= 1

    def test_detects_fstring(self, sql_repo):
        scanner = SecurityScanner(str(sql_repo))
        report = scanner.scan()
        fstr = [f for f in report.findings if "f-string" in f.description]
        assert len(fstr) >= 1

    def test_detects_concatenation(self, sql_repo):
        scanner = SecurityScanner(str(sql_repo))
        report = scanner.scan()
        concat = [f for f in report.findings if "Concatenation" in f.description]
        assert len(concat) >= 1

    def test_severity_is_high(self, sql_repo):
        scanner = SecurityScanner(str(sql_repo))
        report = scanner.scan()
        sql_findings = [f for f in report.findings if f.category == "sql-injection"]
        for f in sql_findings:
            assert f.severity == "HIGH"


# ---------------------------------------------------------------------------
# XSS detection
# ---------------------------------------------------------------------------

class TestXSS:
    def test_detects_innerhtml(self, xss_repo):
        scanner = SecurityScanner(str(xss_repo))
        report = scanner.scan()
        xss = [f for f in report.findings if f.category == "xss" and "innerHTML" in f.description]
        assert len(xss) >= 1

    def test_detects_document_write(self, xss_repo):
        scanner = SecurityScanner(str(xss_repo))
        report = scanner.scan()
        dw = [f for f in report.findings if "document.write" in f.description]
        assert len(dw) >= 1

    def test_detects_dangerously_set(self, xss_repo):
        scanner = SecurityScanner(str(xss_repo))
        report = scanner.scan()
        ds = [f for f in report.findings if "dangerouslySetInnerHTML" in f.description]
        assert len(ds) >= 1

    def test_detects_v_html(self, xss_repo):
        scanner = SecurityScanner(str(xss_repo))
        report = scanner.scan()
        vh = [f for f in report.findings if "v-html" in f.description.lower() or "Vue" in f.description]
        assert len(vh) >= 1


# ---------------------------------------------------------------------------
# Insecure crypto detection
# ---------------------------------------------------------------------------

class TestInsecureCrypto:
    def test_detects_md5(self, crypto_repo):
        scanner = SecurityScanner(str(crypto_repo))
        report = scanner.scan()
        md5 = [f for f in report.findings if "MD5" in f.description]
        assert len(md5) >= 1
        assert md5[0].severity == "MEDIUM"

    def test_detects_des_ecb(self, crypto_repo):
        scanner = SecurityScanner(str(crypto_repo))
        report = scanner.scan()
        des = [f for f in report.findings if "DES" in f.description or "ECB" in f.description]
        assert len(des) >= 1

    def test_detects_math_random(self, crypto_repo):
        scanner = SecurityScanner(str(crypto_repo))
        report = scanner.scan()
        mr = [f for f in report.findings if "Math.random" in f.description]
        assert len(mr) >= 1


# ---------------------------------------------------------------------------
# Command injection detection
# ---------------------------------------------------------------------------

class TestCommandInjection:
    def test_detects_os_system(self, cmdi_repo):
        scanner = SecurityScanner(str(cmdi_repo))
        report = scanner.scan()
        osys = [f for f in report.findings if "os.system" in f.description]
        assert len(osys) >= 1
        assert osys[0].severity == "HIGH"

    def test_detects_eval(self, cmdi_repo):
        scanner = SecurityScanner(str(cmdi_repo))
        report = scanner.scan()
        ev = [f for f in report.findings if "eval" in f.description.lower()]
        assert len(ev) >= 1

    def test_detects_shell_true(self, cmdi_repo):
        scanner = SecurityScanner(str(cmdi_repo))
        report = scanner.scan()
        sh = [f for f in report.findings if "shell=True" in f.description]
        assert len(sh) >= 1


# ---------------------------------------------------------------------------
# Path traversal detection
# ---------------------------------------------------------------------------

class TestPathTraversal:
    def test_detects_open_concat(self, path_repo):
        scanner = SecurityScanner(str(path_repo))
        report = scanner.scan()
        pt = [f for f in report.findings if f.category == "path-traversal"]
        assert len(pt) >= 1
        assert pt[0].severity == "MEDIUM"


# ---------------------------------------------------------------------------
# Insecure deps detection
# ---------------------------------------------------------------------------

class TestInsecureDeps:
    def test_detects_old_django(self, dep_repo):
        scanner = SecurityScanner(str(dep_repo))
        report = scanner.scan()
        dj = [f for f in report.findings if "Django" in f.description]
        assert len(dj) >= 1

    def test_detects_old_flask(self, dep_repo):
        scanner = SecurityScanner(str(dep_repo))
        report = scanner.scan()
        fl = [f for f in report.findings if "Flask" in f.description]
        assert len(fl) >= 1

    def test_detects_old_lodash(self, dep_repo):
        scanner = SecurityScanner(str(dep_repo))
        report = scanner.scan()
        lo = [f for f in report.findings if "lodash" in f.description]
        assert len(lo) >= 1

    def test_detects_old_express(self, dep_repo):
        scanner = SecurityScanner(str(dep_repo))
        report = scanner.scan()
        ex = [f for f in report.findings if "express" in f.description]
        assert len(ex) >= 1


# ---------------------------------------------------------------------------
# Sensitive data exposure
# ---------------------------------------------------------------------------

class TestSensitiveDataExposure:
    def test_detects_logging_password(self, exposure_repo):
        scanner = SecurityScanner(str(exposure_repo))
        report = scanner.scan()
        lp = [f for f in report.findings if f.category == "data-exposure" and "Logging" in f.description]
        assert len(lp) >= 1

    def test_detects_cors_wildcard(self, exposure_repo):
        scanner = SecurityScanner(str(exposure_repo))
        report = scanner.scan()
        cors = [f for f in report.findings if "CORS" in f.description]
        assert len(cors) >= 1


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_format_empty_report(self, empty_repo):
        scanner = SecurityScanner(str(empty_repo))
        report = scanner.scan()
        output = format_security_report(report)
        assert "SECURITY SCAN" in output
        assert "No security issues found" in output

    def test_format_with_findings(self, secret_repo):
        scanner = SecurityScanner(str(secret_repo))
        report = scanner.scan()
        output = format_security_report(report)
        assert "SECURITY SCAN" in output
        assert "CRITICAL" in output
        assert "Hardcoded Secret" in output

    def test_format_shows_file_and_line(self, sql_repo):
        scanner = SecurityScanner(str(sql_repo))
        report = scanner.scan()
        output = format_security_report(report)
        assert "db.py:" in output or "query.py:" in output

    def test_format_truncates_long_lists(self, tmp_path):
        """Report truncates categories with > 10 findings."""
        report = SecurityReport(repo_path=str(tmp_path))
        for i in range(15):
            report.findings.append(SecurityFinding(
                severity="LOW", category="test-cat",
                file=f"file{i}.py", line=i, description="test",
            ))
        output = format_security_report(report)
        assert "... and 5 more" in output


# ---------------------------------------------------------------------------
# Scan behavior
# ---------------------------------------------------------------------------

class TestScanBehavior:
    def test_skips_test_files(self, tmp_path):
        """Secrets in test files should not be flagged."""
        (tmp_path / "test_config.py").write_text(
            'password = "test_password_123"\n'
        )
        scanner = SecurityScanner(str(tmp_path))
        report = scanner.scan()
        secret_findings = [f for f in report.findings if f.category == "hardcoded-secret"]
        assert len(secret_findings) == 0

    def test_skips_comments(self, tmp_path):
        """Commented-out secrets should not be flagged."""
        (tmp_path / "config.py").write_text(
            '# password = "old_password_here"\n'
            'host = "localhost"\n'
        )
        scanner = SecurityScanner(str(tmp_path))
        report = scanner.scan()
        secret_findings = [f for f in report.findings if f.category == "hardcoded-secret"]
        assert len(secret_findings) == 0

    def test_skips_excluded_dirs(self, tmp_path):
        """Files in node_modules etc. should be skipped."""
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "config.js").write_text(
            'var password = "hardcoded_pass";\n'
        )
        scanner = SecurityScanner(str(tmp_path))
        report = scanner.scan()
        assert report.scanned_files == 0

    def test_counts_scanned_files(self, secret_repo):
        scanner = SecurityScanner(str(secret_repo))
        report = scanner.scan()
        assert report.scanned_files > 0

    def test_severity_counts(self, secret_repo):
        scanner = SecurityScanner(str(secret_repo))
        report = scanner.scan()
        total = report.critical_count + report.high_count + report.medium_count + report.low_count
        assert total == len(report.findings)

    def test_empty_repo_no_findings(self, empty_repo):
        scanner = SecurityScanner(str(empty_repo))
        report = scanner.scan()
        assert len(report.findings) == 0
        assert report.scanned_files == 0
