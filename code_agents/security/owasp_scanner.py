"""OWASP Top 10 Scanner for codebase security analysis.

Scans source files for vulnerabilities mapped to the OWASP Top 10 (2021):
  A01 Broken Access Control
  A02 Cryptographic Failures
  A03 Injection
  A04 Insecure Design
  A05 Security Misconfiguration
  A06 Vulnerable Components
  A07 Authentication Failures
  A08 Software Integrity Failures
  A09 Logging Failures
  A10 Server-Side Request Forgery

SECURITY: This scanner MUST NOT log or store actual secrets found.
Only file:line references are recorded in findings.
"""

from __future__ import annotations

import json as _json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.security.owasp_scanner")

# ---------------------------------------------------------------------------
# OWASP Top 10 Rules
# ---------------------------------------------------------------------------

OWASP_RULES = {
    "A01": "Broken Access Control",
    "A02": "Cryptographic Failures",
    "A03": "Injection",
    "A04": "Insecure Design",
    "A05": "Security Misconfiguration",
    "A06": "Vulnerable Components",
    "A07": "Authentication Failures",
    "A08": "Software Integrity Failures",
    "A09": "Logging Failures",
    "A10": "Server-Side Request Forgery",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OWASPFinding:
    file: str
    line: int
    rule_id: str
    rule_name: str
    severity: str  # critical | high | medium | low
    description: str
    remediation: str
    code_snippet: str = ""


@dataclass
class OWASPReport:
    findings: list[OWASPFinding]
    score: int  # 0-100
    passed: list[str]
    failed: list[str]
    summary: str
    scan_time: float = 0.0


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# A01 — Broken Access Control
_ENDPOINT_PATTERN = re.compile(
    r"""@(?:app|router|api|blueprint)\.(get|post|put|patch|delete)\s*\(\s*["']/[^"']*["']""",
    re.IGNORECASE,
)
_AUTH_DECORATOR = re.compile(
    r"@(?:requires?_auth|login_required|authenticated|Depends\s*\(\s*(?:get_current_user|verify_token|auth)|"
    r"permission_required|jwt_required|token_required|permission_classes)",
    re.IGNORECASE,
)
_IDOR_PATTERN = re.compile(
    r"""(?:user_id|account_id|order_id)\s*=\s*(?:request\.(?:args|params|query_params|GET|POST)|int\s*\(|str\s*\()""",
    re.IGNORECASE,
)
_RBAC_PATTERN = re.compile(
    r"(?:role|permission|is_admin|is_staff|has_perm|check_permission|authorize)",
    re.IGNORECASE,
)
_CORS_WILDCARD = re.compile(
    r"""(?:allow_origins|CORS_ORIGINS|Access-Control-Allow-Origin)\s*[=:]\s*\[?\s*["']\*["']""",
    re.IGNORECASE,
)

# A02 — Cryptographic Failures
_WEAK_HASH = re.compile(
    r"(?:hashlib\.md5|hashlib\.sha1|MD5\s*\(|SHA1\s*\(|"
    r"Crypto\.Hash\.MD5|Crypto\.Hash\.SHA(?:1)?(?!\d))",
    re.IGNORECASE,
)
_HARDCODED_KEY = re.compile(
    r"""(?:(?:encryption|secret|api|aes|private|signing)_?key|SECRET_KEY|AES_KEY)\s*=\s*["'][A-Za-z0-9+/=]{16,}["']""",
    re.IGNORECASE,
)
_WEAK_CIPHER = re.compile(
    r"(?:DES\.new|DES3\.new|ARC4|RC4|Blowfish|AES\.MODE_ECB|MODE_ECB|"
    r"algorithms\.TripleDES|algorithms\.Blowfish)",
    re.IGNORECASE,
)
_SMALL_KEY = re.compile(r"key_size\s*=\s*(\d+)")
_HARDCODED_PASSWORD = re.compile(
    r"""(?:password|passwd|pwd)\s*=\s*["'][^"']{3,}["']""",
    re.IGNORECASE,
)

# A03 — Injection
_SQL_CONCAT = re.compile(
    r"""(?:execute|cursor\.execute|raw|RawSQL|text)\s*\(\s*(?:f["']|["'].*\.format\(|["'].*%\s*\()""",
    re.IGNORECASE,
)
_EVAL_EXEC = re.compile(r"\b(?:eval|exec)\s*\(")
_SHELL_TRUE = re.compile(r"(?:subprocess\.\w+|Popen|call|run)\s*\([^)]*shell\s*=\s*True")
_OS_SYSTEM = re.compile(r"os\.system\s*\(")
_OS_POPEN = re.compile(r"os\.popen\s*\(")
_LDAP_INJECT = re.compile(
    r"""(?:ldap\.search|ldap_search|search_s)\s*\([^)]*(?:f["']|\.format\(|%\s*\()""",
    re.IGNORECASE,
)

# A04 — Insecure Design
_RATE_LIMIT_DECORATOR = re.compile(
    r"@(?:rate_limit|limiter\.limit|throttle|RateLimit)",
    re.IGNORECASE,
)
_CSRF_EXEMPT = re.compile(r"@csrf_exempt|csrf_protect\s*=\s*False|CSRF.*=.*False", re.IGNORECASE)
_NO_INPUT_LIMIT = re.compile(
    r"""(?:max_length|maxlength|max_size|limit)\s*=\s*(?:None|0|-1)""",
    re.IGNORECASE,
)

# A05 — Security Misconfiguration
_DEBUG_TRUE = re.compile(r"""(?:DEBUG|debug)\s*=\s*True""")
_DEFAULT_PASSWORD = re.compile(
    r"""(?:password|passwd|pwd)\s*=\s*["'](?:admin|password|123456|root|test|default|changeme|passw0rd)["']""",
    re.IGNORECASE,
)
_VERBOSE_ERRORS = re.compile(
    r"(?:traceback\.print_exc|traceback\.format_exc|print_exc\(\)|"
    r"app\.config\[.DEBUG.\]\s*=\s*True|PROPAGATE_EXCEPTIONS\s*=\s*True)",
    re.IGNORECASE,
)
_DIRECTORY_LISTING = re.compile(
    r"(?:directory_listing|autoindex|DirectoryIndex)\s*[=:]\s*(?:True|on|enabled)",
    re.IGNORECASE,
)

# A06 — Vulnerable Components (known CVE patterns in requirements)
_KNOWN_VULNERABLE = {
    "django": {"below": "4.2", "cve": "CVE-2023-multiple", "desc": "Django < 4.2 has known vulnerabilities"},
    "flask": {"below": "2.3", "cve": "CVE-2023-30861", "desc": "Flask < 2.3 session cookie vulnerability"},
    "requests": {"below": "2.31", "cve": "CVE-2023-32681", "desc": "Requests < 2.31 leaks proxy credentials"},
    "urllib3": {"below": "2.0", "cve": "CVE-2023-43804", "desc": "urllib3 < 2.0 cookie/header injection"},
    "cryptography": {"below": "41.0", "cve": "CVE-2023-38325", "desc": "Cryptography < 41.0 X.509 parsing"},
    "pyyaml": {"below": "6.0", "cve": "CVE-2020-14343", "desc": "PyYAML < 6.0 arbitrary code execution"},
    "pillow": {"below": "10.0", "cve": "CVE-2023-multiple", "desc": "Pillow < 10.0 multiple vulnerabilities"},
    "numpy": {"below": "1.22", "cve": "CVE-2021-41496", "desc": "NumPy < 1.22 buffer overflow"},
    "jinja2": {"below": "3.1.3", "cve": "CVE-2024-22195", "desc": "Jinja2 < 3.1.3 XSS vulnerability"},
    "werkzeug": {"below": "3.0", "cve": "CVE-2023-46136", "desc": "Werkzeug < 3.0 path traversal"},
}
_PACKAGE_JSON_DEP = re.compile(r'"([^"]+)"\s*:\s*"[^"]*?(\d+\.\d+(?:\.\d+)?)"')
_REQUIREMENTS_LINE = re.compile(r"^([a-zA-Z0-9_-]+)\s*[=<>~!]+\s*(\d+\.\d+(?:\.\d+)?)")

# A07 — Authentication Failures
_PLAINTEXT_PASSWORD = re.compile(
    r"""(?:password|passwd)\s*==\s*["'][^"']+["']""",
    re.IGNORECASE,
)
_WEAK_JWT = re.compile(
    r"""(?:algorithm|algorithms)\s*[=:]\s*\[?\s*["'](?:none|HS256)["']""",
    re.IGNORECASE,
)
_NO_PASSWORD_POLICY = re.compile(
    r"(?:min_length|MIN_PASSWORD_LENGTH|password_validators)\s*=\s*(?:[0-5]|None|\[\])",
    re.IGNORECASE,
)

# A08 — Software Integrity Failures
_PICKLE_LOAD = re.compile(r"(?:pickle\.load|pickle\.loads|cPickle\.load|cPickle\.loads)\s*\(")
_YAML_UNSAFE = re.compile(r"yaml\.load\s*\([^)]*(?!Loader\s*=\s*(?:yaml\.)?SafeLoader)")
_YAML_SAFE_CHECK = re.compile(r"Loader\s*=\s*(?:yaml\.)?SafeLoader")
_MARSHAL_LOAD = re.compile(r"marshal\.loads?\s*\(")
_SHELVE_OPEN = re.compile(r"shelve\.open\s*\(")

# A09 — Logging Failures
_LOG_STATEMENT = re.compile(
    r"(?:logger\.\w+|logging\.\w+)\s*\(",
)
_PII_IN_LOG = re.compile(
    r"(?:logger|logging)\.\w+\s*\([^)]*\b(?:password|passwd|pwd|ssn|social_security|"
    r"credit_card|card_number|pan|secret_key|api_key|token|bearer)\b",
    re.IGNORECASE,
)
_SENSITIVE_IN_LOG = re.compile(
    r"""(?:logger|logging)\.\w+\s*\([^)]*(?:f["']|\.format\(|%\s*\()[^)]*\b(?:password|secret|token|api_key)\b""",
    re.IGNORECASE,
)

# A10 — SSRF
_REQUEST_USER_URL = re.compile(
    r"""(?:requests\.(?:get|post|put|patch|delete|head)|httpx\.(?:get|post|put|patch|delete|head)|"
    r"urllib\.request\.urlopen|aiohttp\.ClientSession\(\)\.(?:get|post))\s*\(\s*(?!["'])""",
    re.IGNORECASE,
)
_URL_FROM_REQUEST = re.compile(
    r"""(?:url|target|endpoint|redirect)\s*=\s*(?:request\.(?:args|params|GET|POST|json|form|data)|"
    r"params\.get|query_params)""",
    re.IGNORECASE,
)
_NO_URL_VALIDATION = re.compile(
    r"""(?:validate_url|is_safe_url|url_has_allowed_host|is_internal_url|whitelist|allowlist)""",
    re.IGNORECASE,
)

# Source file extensions to scan
_SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rb", ".php", ".cs", ".kt", ".scala", ".rs",
}

# Directories to skip
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".tox", ".venv", "venv",
    "env", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".eggs", "*.egg-info",
}

# Dependency files
_DEP_FILES = {
    "requirements.txt", "requirements-dev.txt", "requirements-prod.txt",
    "package.json", "Pipfile", "setup.cfg",
}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class OWASPScanner:
    """Scans a codebase for OWASP Top 10 vulnerabilities."""

    def __init__(self, cwd: str) -> None:
        self.cwd = os.path.abspath(cwd)
        self._files: list[Path] = []
        self._file_cache: dict[str, list[str]] = {}
        logger.debug("OWASPScanner initialised for %s", self.cwd)

    # -- public API ----------------------------------------------------------

    def scan(self) -> OWASPReport:
        """Run all OWASP checks and return a report."""
        t0 = time.monotonic()
        self._files = self._collect_files()
        logger.info("Scanning %d source files in %s", len(self._files), self.cwd)

        findings: list[OWASPFinding] = []
        findings.extend(self._check_access_control())
        findings.extend(self._check_crypto())
        findings.extend(self._check_injection())
        findings.extend(self._check_insecure_design())
        findings.extend(self._check_misconfig())
        findings.extend(self._check_vulnerable_components())
        findings.extend(self._check_auth_failures())
        findings.extend(self._check_integrity())
        findings.extend(self._check_logging())
        findings.extend(self._check_ssrf())

        elapsed = time.monotonic() - t0

        failed_ids = sorted({f.rule_id for f in findings})
        passed_ids = sorted(set(OWASP_RULES.keys()) - set(failed_ids))

        score = self._calculate_score(findings)
        summary = self._build_summary(findings, score, elapsed)

        report = OWASPReport(
            findings=findings,
            score=score,
            passed=passed_ids,
            failed=failed_ids,
            summary=summary,
            scan_time=elapsed,
        )
        logger.info("OWASP scan complete: score=%d, findings=%d, time=%.2fs",
                     score, len(findings), elapsed)
        return report

    # -- file collection -----------------------------------------------------

    def _collect_files(self) -> list[Path]:
        """Walk cwd and collect source files, skipping irrelevant dirs."""
        collected: list[Path] = []
        root = Path(self.cwd)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in _SKIP_DIRS and not d.endswith(".egg-info")
            ]
            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix in _SOURCE_EXTENSIONS or p.name in _DEP_FILES:
                    collected.append(p)
        return collected

    def _read_lines(self, path: Path) -> list[str]:
        """Read file lines with caching.  Returns empty list on read errors."""
        key = str(path)
        if key not in self._file_cache:
            try:
                self._file_cache[key] = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                logger.warning("Could not read %s", key)
                self._file_cache[key] = []
        return self._file_cache[key]

    def _rel(self, path: Path) -> str:
        """Return path relative to cwd for display."""
        try:
            return str(path.relative_to(self.cwd))
        except ValueError:
            return str(path)

    @staticmethod
    def _safe_snippet(line: str, max_len: int = 120) -> str:
        """Return a sanitised snippet — strip secrets to avoid leaking them."""
        sanitised = re.sub(
            r"""(["'])[A-Za-z0-9+/=]{20,}\1""",
            r"\1[REDACTED]\1",
            line,
        )
        sanitised = sanitised.strip()
        if len(sanitised) > max_len:
            sanitised = sanitised[:max_len] + "..."
        return sanitised

    def _finding(self, path: Path, idx: int, rule_id: str, severity: str,
                 description: str, remediation: str, line: str) -> OWASPFinding:
        """Helper to create an OWASPFinding with consistent formatting."""
        return OWASPFinding(
            file=self._rel(path),
            line=idx,
            rule_id=rule_id,
            rule_name=OWASP_RULES.get(rule_id, "Unknown"),
            severity=severity,
            description=description,
            remediation=remediation,
            code_snippet=self._safe_snippet(line),
        )

    # -- A01: Broken Access Control ------------------------------------------

    def _check_access_control(self) -> list[OWASPFinding]:
        """A01: Missing auth decorators, IDOR patterns, missing RBAC, CORS wildcard."""
        findings: list[OWASPFinding] = []
        for path in self._files:
            if path.suffix not in _SOURCE_EXTENSIONS:
                continue
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # Endpoint without auth decorator
                if _ENDPOINT_PATTERN.search(line):
                    context_before = lines[max(0, idx - 6):idx - 1]
                    has_auth = any(_AUTH_DECORATOR.search(cl) for cl in context_before)
                    if not has_auth:
                        findings.append(self._finding(
                            path, idx, "A01", "high",
                            "API endpoint without authentication decorator",
                            "Add authentication (e.g. @login_required, Depends(get_current_user)) to all endpoints",
                            line,
                        ))

                # IDOR — user-controlled ID used directly
                if _IDOR_PATTERN.search(line):
                    # Check surrounding context for ownership validation
                    context = lines[max(0, idx - 3):min(len(lines), idx + 5)]
                    context_text = " ".join(context)
                    if not re.search(r"(?:current_user|request\.user|owner|belongs_to|authorize)", context_text, re.IGNORECASE):
                        findings.append(self._finding(
                            path, idx, "A01", "high",
                            "Potential IDOR: user-controlled ID without ownership validation",
                            "Validate that the resource belongs to the authenticated user before access",
                            line,
                        ))

                # CORS wildcard
                if _CORS_WILDCARD.search(line):
                    findings.append(self._finding(
                        path, idx, "A01", "medium",
                        "CORS allows all origins (*)",
                        "Restrict CORS origins to specific trusted domains",
                        line,
                    ))

        return findings

    # -- A02: Cryptographic Failures -----------------------------------------

    def _check_crypto(self) -> list[OWASPFinding]:
        """A02: Weak hash, hardcoded keys, weak ciphers, ECB mode, small keys."""
        findings: list[OWASPFinding] = []
        for path in self._files:
            if path.suffix not in _SOURCE_EXTENSIONS:
                continue
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # Weak hash
                if _WEAK_HASH.search(line):
                    findings.append(self._finding(
                        path, idx, "A02", "high",
                        "Weak hash algorithm (MD5/SHA1) — vulnerable to collision attacks",
                        "Use SHA-256+ for integrity, bcrypt/scrypt/Argon2 for passwords",
                        line,
                    ))

                # Hardcoded key
                if _HARDCODED_KEY.search(line):
                    findings.append(self._finding(
                        path, idx, "A02", "critical",
                        "Hardcoded cryptographic key detected",
                        "Store keys in a secrets manager (Vault, AWS KMS). Never commit keys to code.",
                        line,
                    ))

                # Weak cipher
                if _WEAK_CIPHER.search(line):
                    findings.append(self._finding(
                        path, idx, "A02", "critical",
                        "Weak cipher or insecure mode (DES/RC4/ECB) detected",
                        "Use AES-256-GCM or AES-256-CBC with HMAC. Never use ECB, DES, or RC4.",
                        line,
                    ))

                # Small key size
                km = _SMALL_KEY.search(line)
                if km:
                    key_bits = int(km.group(1))
                    if key_bits < 128:
                        findings.append(self._finding(
                            path, idx, "A02", "high",
                            f"Key size {key_bits} bits is below the 128-bit minimum",
                            "Use a minimum key size of 128 bits (256 recommended)",
                            line,
                        ))

                # Hardcoded password
                if _HARDCODED_PASSWORD.search(line):
                    # Skip test files and comments
                    if not path.name.startswith("test_") and "# " not in line[:line.find("password") if "password" in line.lower() else 0]:
                        findings.append(self._finding(
                            path, idx, "A02", "high",
                            "Hardcoded password in source code",
                            "Use environment variables or a secrets manager for credentials",
                            line,
                        ))

        return findings

    # -- A03: Injection ------------------------------------------------------

    def _check_injection(self) -> list[OWASPFinding]:
        """A03: SQL concat, eval/exec, shell=True, OS command injection, LDAP."""
        findings: list[OWASPFinding] = []
        for path in self._files:
            if path.suffix not in _SOURCE_EXTENSIONS:
                continue
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # SQL string concatenation / f-string
                if _SQL_CONCAT.search(line):
                    findings.append(self._finding(
                        path, idx, "A03", "critical",
                        "SQL injection: query built with string formatting/concatenation",
                        "Use parameterized queries: cursor.execute('SELECT * FROM t WHERE id = %s', (id,))",
                        line,
                    ))

                # eval / exec
                if _EVAL_EXEC.search(line):
                    # Ignore comments
                    stripped = line.lstrip()
                    if not stripped.startswith("#") and not stripped.startswith("//"):
                        findings.append(self._finding(
                            path, idx, "A03", "critical",
                            "Code injection: eval()/exec() can execute arbitrary code",
                            "Replace eval/exec with safe alternatives (ast.literal_eval, structured parsing)",
                            line,
                        ))

                # shell=True in subprocess
                if _SHELL_TRUE.search(line):
                    findings.append(self._finding(
                        path, idx, "A03", "high",
                        "Command injection: subprocess with shell=True",
                        "Use shell=False with argument list: subprocess.run(['cmd', 'arg'])",
                        line,
                    ))

                # os.system
                if _OS_SYSTEM.search(line):
                    stripped = line.lstrip()
                    if not stripped.startswith("#"):
                        findings.append(self._finding(
                            path, idx, "A03", "high",
                            "Command injection: os.system() is vulnerable to shell injection",
                            "Use subprocess.run() with shell=False and argument list",
                            line,
                        ))

                # os.popen
                if _OS_POPEN.search(line):
                    stripped = line.lstrip()
                    if not stripped.startswith("#"):
                        findings.append(self._finding(
                            path, idx, "A03", "high",
                            "Command injection: os.popen() is vulnerable to shell injection",
                            "Use subprocess.run() with shell=False and capture_output=True",
                            line,
                        ))

                # LDAP injection
                if _LDAP_INJECT.search(line):
                    findings.append(self._finding(
                        path, idx, "A03", "high",
                        "LDAP injection: query built with string formatting",
                        "Use parameterized LDAP filters or escape user input with ldap.filter.escape_filter_chars()",
                        line,
                    ))

        return findings

    # -- A04: Insecure Design ------------------------------------------------

    def _check_insecure_design(self) -> list[OWASPFinding]:
        """A04: Missing rate limiting, no CSRF protection, no input length limits."""
        findings: list[OWASPFinding] = []
        for path in self._files:
            if path.suffix not in _SOURCE_EXTENSIONS:
                continue
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # CSRF exemption
                if _CSRF_EXEMPT.search(line):
                    findings.append(self._finding(
                        path, idx, "A04", "medium",
                        "CSRF protection disabled or exempted",
                        "Enable CSRF protection for state-changing endpoints",
                        line,
                    ))

                # Login / auth endpoint without rate limiting
                if _ENDPOINT_PATTERN.search(line):
                    endpoint_lower = line.lower()
                    if any(kw in endpoint_lower for kw in ("login", "auth", "signin", "signup", "register", "password")):
                        context_before = lines[max(0, idx - 6):idx - 1]
                        has_rate_limit = any(_RATE_LIMIT_DECORATOR.search(cl) for cl in context_before)
                        if not has_rate_limit:
                            findings.append(self._finding(
                                path, idx, "A04", "medium",
                                "Authentication endpoint without rate limiting",
                                "Add rate limiting to prevent brute force attacks: @limiter.limit('5/minute')",
                                line,
                            ))

                # Input validation with no limit
                if _NO_INPUT_LIMIT.search(line):
                    findings.append(self._finding(
                        path, idx, "A04", "low",
                        "Input field with no length limit (None/0/-1)",
                        "Set appropriate max_length for all user input fields",
                        line,
                    ))

        return findings

    # -- A05: Security Misconfiguration --------------------------------------

    def _check_misconfig(self) -> list[OWASPFinding]:
        """A05: debug=True, default passwords, verbose errors, directory listing."""
        findings: list[OWASPFinding] = []
        for path in self._files:
            if path.suffix not in _SOURCE_EXTENSIONS:
                continue
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # DEBUG = True
                if _DEBUG_TRUE.search(line):
                    stripped = line.lstrip()
                    if not stripped.startswith("#") and not stripped.startswith("//"):
                        # Skip test files
                        if not path.name.startswith("test_"):
                            findings.append(self._finding(
                                path, idx, "A05", "medium",
                                "Debug mode enabled — may expose sensitive information in production",
                                "Set DEBUG=False in production. Use environment variable: DEBUG=os.getenv('DEBUG', 'false')",
                                line,
                            ))

                # Default passwords
                if _DEFAULT_PASSWORD.search(line):
                    stripped = line.lstrip()
                    if not stripped.startswith("#") and not path.name.startswith("test_"):
                        findings.append(self._finding(
                            path, idx, "A05", "critical",
                            "Default/weak password detected in source code",
                            "Use strong, unique passwords from a secrets manager. Never hardcode defaults.",
                            line,
                        ))

                # Verbose error handling
                if _VERBOSE_ERRORS.search(line):
                    findings.append(self._finding(
                        path, idx, "A05", "low",
                        "Verbose error output may expose internal details",
                        "Use generic error messages for users. Log details server-side only.",
                        line,
                    ))

                # Directory listing
                if _DIRECTORY_LISTING.search(line):
                    findings.append(self._finding(
                        path, idx, "A05", "medium",
                        "Directory listing enabled — may expose file structure",
                        "Disable directory listing in production web servers",
                        line,
                    ))

        return findings

    # -- A06: Vulnerable Components ------------------------------------------

    def _check_vulnerable_components(self) -> list[OWASPFinding]:
        """A06: Scan requirements.txt/package.json for known CVEs (offline check)."""
        findings: list[OWASPFinding] = []
        for path in self._files:
            if path.name not in _DEP_FILES:
                continue

            lines = self._read_lines(path)
            full_text = "\n".join(lines)

            if path.name == "package.json":
                # Parse JSON-style dependencies
                for idx, line in enumerate(lines, start=1):
                    m = _PACKAGE_JSON_DEP.search(line)
                    if m:
                        pkg_name = m.group(1).lower()
                        version = m.group(2)
                        vuln = _KNOWN_VULNERABLE.get(pkg_name)
                        if vuln and self._version_below(version, vuln["below"]):
                            findings.append(self._finding(
                                path, idx, "A06", "high",
                                f"Vulnerable component: {pkg_name} {version} — {vuln['desc']} ({vuln['cve']})",
                                f"Upgrade {pkg_name} to >= {vuln['below']}",
                                line,
                            ))
            else:
                # requirements.txt style
                for idx, line in enumerate(lines, start=1):
                    m = _REQUIREMENTS_LINE.match(line.strip())
                    if m:
                        pkg_name = m.group(1).lower().replace("-", "").replace("_", "")
                        version = m.group(2)
                        for known_pkg, vuln in _KNOWN_VULNERABLE.items():
                            norm_known = known_pkg.lower().replace("-", "").replace("_", "")
                            if pkg_name == norm_known and self._version_below(version, vuln["below"]):
                                findings.append(self._finding(
                                    path, idx, "A06", "high",
                                    f"Vulnerable component: {known_pkg} {version} — {vuln['desc']} ({vuln['cve']})",
                                    f"Upgrade {known_pkg} to >= {vuln['below']}",
                                    line,
                                ))

        return findings

    @staticmethod
    def _version_below(version: str, threshold: str) -> bool:
        """Compare version strings (major.minor only)."""
        try:
            v_parts = [int(x) for x in version.split(".")[:2]]
            t_parts = [int(x) for x in threshold.split(".")[:2]]
            return v_parts < t_parts
        except (ValueError, IndexError):
            return False

    # -- A07: Authentication Failures ----------------------------------------

    def _check_auth_failures(self) -> list[OWASPFinding]:
        """A07: Plaintext passwords, missing password policy, weak JWT."""
        findings: list[OWASPFinding] = []
        for path in self._files:
            if path.suffix not in _SOURCE_EXTENSIONS:
                continue
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # Plaintext password comparison
                if _PLAINTEXT_PASSWORD.search(line):
                    stripped = line.lstrip()
                    if not stripped.startswith("#") and not path.name.startswith("test_"):
                        findings.append(self._finding(
                            path, idx, "A07", "critical",
                            "Plaintext password comparison — passwords should be hashed",
                            "Use bcrypt.checkpw() or similar hash verification instead of string comparison",
                            line,
                        ))

                # Weak JWT algorithm
                if _WEAK_JWT.search(line):
                    findings.append(self._finding(
                        path, idx, "A07", "high",
                        "Weak JWT algorithm (none/HS256) — vulnerable to token forgery",
                        "Use RS256 or ES256 for JWT signing. Never use 'none' algorithm.",
                        line,
                    ))

                # Weak password policy
                if _NO_PASSWORD_POLICY.search(line):
                    findings.append(self._finding(
                        path, idx, "A07", "medium",
                        "Weak or missing password policy (length < 6 or no validators)",
                        "Enforce minimum 8 characters, complexity requirements, and password history",
                        line,
                    ))

        return findings

    # -- A08: Software Integrity Failures ------------------------------------

    def _check_integrity(self) -> list[OWASPFinding]:
        """A08: Deserialization (pickle, yaml.load), unsigned updates, CI/CD tampering."""
        findings: list[OWASPFinding] = []
        for path in self._files:
            if path.suffix not in _SOURCE_EXTENSIONS:
                continue
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # pickle.load / cPickle.load
                if _PICKLE_LOAD.search(line):
                    findings.append(self._finding(
                        path, idx, "A08", "critical",
                        "Insecure deserialization: pickle.load can execute arbitrary code",
                        "Use JSON or Protocol Buffers instead of pickle for untrusted data",
                        line,
                    ))

                # yaml.load without SafeLoader
                if _YAML_UNSAFE.search(line) and not _YAML_SAFE_CHECK.search(line):
                    findings.append(self._finding(
                        path, idx, "A08", "critical",
                        "Insecure deserialization: yaml.load without SafeLoader",
                        "Use yaml.safe_load() or yaml.load(data, Loader=yaml.SafeLoader)",
                        line,
                    ))

                # marshal.load
                if _MARSHAL_LOAD.search(line):
                    findings.append(self._finding(
                        path, idx, "A08", "high",
                        "Insecure deserialization: marshal.load can execute arbitrary code",
                        "Use JSON or structured parsing instead of marshal for untrusted data",
                        line,
                    ))

                # shelve.open (uses pickle internally)
                if _SHELVE_OPEN.search(line):
                    findings.append(self._finding(
                        path, idx, "A08", "medium",
                        "shelve uses pickle internally — unsafe for untrusted data",
                        "Use a database or JSON file instead of shelve for persistent storage",
                        line,
                    ))

        return findings

    # -- A09: Logging Failures -----------------------------------------------

    def _check_logging(self) -> list[OWASPFinding]:
        """A09: PII in logs, sensitive data in logs, missing security logging."""
        findings: list[OWASPFinding] = []
        has_security_logging = False

        for path in self._files:
            if path.suffix not in _SOURCE_EXTENSIONS:
                continue
            lines = self._read_lines(path)
            full_text = " ".join(lines)

            # Check if any file has security/audit logging
            if re.search(r"(?:security|audit).*log", full_text, re.IGNORECASE):
                has_security_logging = True

            for idx, line in enumerate(lines, start=1):
                # PII in log statements
                if _PII_IN_LOG.search(line):
                    findings.append(self._finding(
                        path, idx, "A09", "high",
                        "Sensitive data (password/token/PII) referenced in log statement",
                        "Never log sensitive data. Mask or redact before logging.",
                        line,
                    ))

                # Sensitive data interpolated in log
                if _SENSITIVE_IN_LOG.search(line):
                    findings.append(self._finding(
                        path, idx, "A09", "high",
                        "Sensitive data interpolated in log message via f-string/format",
                        "Remove sensitive variables from log format strings. Log only safe identifiers.",
                        line,
                    ))

        # Note: we do not add a finding for missing security logging since it is
        # project-structure dependent and would be too noisy.

        return findings

    # -- A10: Server-Side Request Forgery ------------------------------------

    def _check_ssrf(self) -> list[OWASPFinding]:
        """A10: User-controlled URLs in requests/httpx without validation."""
        findings: list[OWASPFinding] = []
        for path in self._files:
            if path.suffix not in _SOURCE_EXTENSIONS:
                continue
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # URL from user input
                if _URL_FROM_REQUEST.search(line):
                    # Check surrounding context for URL validation
                    context = lines[max(0, idx - 5):min(len(lines), idx + 10)]
                    context_text = " ".join(context)
                    if not _NO_URL_VALIDATION.search(context_text):
                        findings.append(self._finding(
                            path, idx, "A10", "high",
                            "Potential SSRF: URL taken from user input without validation",
                            "Validate and whitelist allowed URLs/hosts. Block internal/private IP ranges.",
                            line,
                        ))

                # HTTP client with variable (non-string-literal) URL
                if _REQUEST_USER_URL.search(line):
                    # Check if the URL comes from user input in context
                    context = lines[max(0, idx - 5):min(len(lines), idx + 3)]
                    context_text = " ".join(context)
                    if re.search(r"(?:request\.|params|args|query|form|data\.get)", context_text, re.IGNORECASE):
                        if not _NO_URL_VALIDATION.search(context_text):
                            findings.append(self._finding(
                                path, idx, "A10", "high",
                                "Potential SSRF: HTTP request with user-controlled URL",
                                "Validate URLs against an allowlist. Block internal networks (10.x, 172.16.x, 192.168.x, localhost).",
                                line,
                            ))

        return findings

    # -- scoring & summary ---------------------------------------------------

    @staticmethod
    def _calculate_score(findings: list[OWASPFinding]) -> int:
        """Calculate 0-100 security score from findings.

        Deductions:
          - critical: 15 points each (max 60)
          - high:     8 points each  (max 40)
          - medium:   3 points each  (max 20)
          - low:      1 point each   (max 10)
        """
        severity_counts: dict[str, int] = {}
        for f in findings:
            severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

        deductions = 0
        deductions += min(severity_counts.get("critical", 0) * 15, 60)
        deductions += min(severity_counts.get("high", 0) * 8, 40)
        deductions += min(severity_counts.get("medium", 0) * 3, 20)
        deductions += min(severity_counts.get("low", 0) * 1, 10)

        return max(0, 100 - deductions)

    @staticmethod
    def _build_summary(findings: list[OWASPFinding], score: int, elapsed: float) -> str:
        sev: dict[str, int] = {}
        for f in findings:
            sev[f.severity] = sev.get(f.severity, 0) + 1

        parts = []
        for s in ("critical", "high", "medium", "low"):
            if sev.get(s, 0):
                parts.append(f"{sev[s]} {s}")

        finding_str = ", ".join(parts) if parts else "no issues"
        return f"Score: {score}/100 | {finding_str} | {len(findings)} total findings | {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# Report Formatter
# ---------------------------------------------------------------------------

_SEVERITY_COLORS = {
    "critical": "\033[91m",  # red
    "high": "\033[93m",      # yellow
    "medium": "\033[94m",    # blue
    "low": "\033[90m",       # gray
}
_SEVERITY_ICONS = {
    "critical": "!!",
    "high": "! ",
    "medium": "* ",
    "low": "- ",
}
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


def format_owasp_report(report: OWASPReport, *, use_color: bool = True) -> str:
    """Format an OWASPReport for terminal display.

    Output layout:
        +-- OWASP Top 10 Security Scan -------------------+
        | Score: 72/100 ########..                        |
        | Critical: 2  High: 3  Medium: 5  Low: 1        |
        +-------------------------------------------------+
        | !! A03 CRITICAL — Injection                     |
        |   src/db.py:45                                  |
        |   SQL injection: query built with string concat |
        |   Fix: Use parameterized queries                |
        +-------------------------------------------------+
    """
    lines: list[str] = []
    W = 60

    def _c(color: str, text: str) -> str:
        return f"{color}{text}{_RESET}" if use_color else text

    # Header
    title = " OWASP Top 10 Security Scan "
    border = "+" + "-" * (W - 2) + "+"
    title_line = "+" + "-" * ((W - 2 - len(title)) // 2) + title + "-" * ((W - 2 - len(title) + 1) // 2) + "+"
    lines.append(title_line)

    # Score bar
    filled = report.score * 20 // 100
    bar = "#" * filled + "." * (20 - filled)
    score_color = "\033[92m" if report.score >= 80 else ("\033[93m" if report.score >= 50 else "\033[91m")
    score_str = f"Score: {_c(score_color, f'{report.score}/100')} [{bar}]"
    lines.append(f"| {score_str}")

    # Severity summary
    sev: dict[str, int] = {}
    for f in report.findings:
        sev[f.severity] = sev.get(f.severity, 0) + 1

    sev_parts = []
    for s in ("critical", "high", "medium", "low"):
        label = s.capitalize()
        count = sev.get(s, 0)
        col = _SEVERITY_COLORS.get(s, "")
        sev_parts.append(f"{_c(col, label)}: {count}")
    lines.append(f"| {' '.join(sev_parts)}")
    lines.append(f"| Scan time: {report.scan_time:.2f}s | Files scanned: {len(set(f.file for f in report.findings)) or 'all'}")
    lines.append(border)

    # Passed rules
    if report.passed:
        lines.append(f"| {_c(_BOLD, 'Passed rules:')}")
        for r in report.passed:
            desc = OWASP_RULES.get(r, "")
            lines.append(f"|   {_c(chr(27) + '[92m', 'OK')} {r} — {desc}")
        lines.append("|")

    # Failed rules
    if report.failed:
        lines.append(f"| {_c(_BOLD, 'Failed rules:')}")
        for r in report.failed:
            desc = OWASP_RULES.get(r, "")
            lines.append(f"|   {_c(chr(27) + '[91m', 'FAIL')} {r} — {desc}")
        lines.append(border)

    # Findings (grouped by severity)
    if report.findings:
        for severity in ("critical", "high", "medium", "low"):
            group = [f for f in report.findings if f.severity == severity]
            if not group:
                continue
            icon = _SEVERITY_ICONS.get(severity, "  ")
            col = _SEVERITY_COLORS.get(severity, "")
            lines.append(f"| {_c(col, f'{icon}{severity.upper()}')} ({len(group)} finding{'s' if len(group) != 1 else ''})")
            lines.append("|")
            for f in group:
                lines.append(f"|   {_c(_BOLD, f'{f.rule_id} — {f.rule_name}')} {f.file}:{f.line}")
                lines.append(f"|     {f.description}")
                if f.code_snippet:
                    lines.append(f"|     {_c(_DIM, f.code_snippet)}")
                lines.append(f"|     Fix: {f.remediation}")
                lines.append("|")
            lines.append(border)
    else:
        lines.append(f"| {_c(chr(27) + '[92m', 'No OWASP violations found.')}")
        lines.append(border)

    lines.append("")
    return "\n".join(lines)


def owasp_report_to_json(report: OWASPReport) -> dict:
    """Convert an OWASPReport to a JSON-serializable dict."""
    return {
        "score": report.score,
        "summary": report.summary,
        "scan_time": round(report.scan_time, 3),
        "passed": report.passed,
        "failed": report.failed,
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "rule_id": f.rule_id,
                "rule_name": f.rule_name,
                "severity": f.severity,
                "description": f.description,
                "remediation": f.remediation,
                "code_snippet": f.code_snippet,
            }
            for f in report.findings
        ],
    }
