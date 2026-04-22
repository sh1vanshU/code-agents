"""Security Scanner — OWASP top 10 static analysis."""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.analysis.security_scanner")


@dataclass
class SecurityFinding:
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    category: str  # sql-injection, xss, hardcoded-secret, insecure-dep, etc.
    file: str
    line: int
    description: str
    snippet: str = ""
    fix_suggestion: str = ""


@dataclass
class SecurityReport:
    repo_path: str
    findings: list[SecurityFinding] = field(default_factory=list)
    scanned_files: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0


class SecurityScanner:
    """OWASP top 10 static analysis scanner for source code."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.report = SecurityReport(repo_path=cwd)
        self._skip_dirs = {
            ".git", "node_modules", "__pycache__", "venv", ".venv",
            "target", "build", "dist", ".gradle", ".mvn",
        }
        logger.info("SecurityScanner initialized for %s", cwd)

    def scan(self) -> SecurityReport:
        """Run all security checks."""
        logger.info("Starting security scan of %s", self.cwd)

        self._scan_hardcoded_secrets()
        self._scan_sql_injection()
        self._scan_xss()
        self._scan_insecure_crypto()
        self._scan_path_traversal()
        self._scan_command_injection()
        self._scan_insecure_deps()
        self._scan_sensitive_data_exposure()

        # Count by severity
        for f in self.report.findings:
            if f.severity == "CRITICAL":
                self.report.critical_count += 1
            elif f.severity == "HIGH":
                self.report.high_count += 1
            elif f.severity == "MEDIUM":
                self.report.medium_count += 1
            elif f.severity == "LOW":
                self.report.low_count += 1

        logger.info(
            "Scan complete: %d files, %d findings (C:%d H:%d M:%d L:%d)",
            self.report.scanned_files, len(self.report.findings),
            self.report.critical_count, self.report.high_count,
            self.report.medium_count, self.report.low_count,
        )
        return self.report

    def _get_files(self, extensions: tuple) -> list[tuple[str, str]]:
        """Get files with content. Returns (rel_path, content) tuples."""
        files = []
        for root, dirs, filenames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in self._skip_dirs]
            for f in filenames:
                if f.endswith(extensions):
                    fpath = os.path.join(root, f)
                    rel = os.path.relpath(fpath, self.cwd)
                    try:
                        with open(fpath, errors="replace") as fp:
                            content = fp.read()
                        files.append((rel, content))
                        self.report.scanned_files += 1
                    except Exception:
                        logger.debug("Could not read %s", fpath)
        return files

    # ------------------------------------------------------------------
    # Hardcoded secrets
    # ------------------------------------------------------------------

    def _scan_hardcoded_secrets(self):
        """Find hardcoded passwords, API keys, tokens."""
        secret_patterns = [
            (r'(?:password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']', "Hardcoded password"),
            (r'(?:api[_-]?key|apikey)\s*=\s*["\'][^"\']{8,}["\']', "Hardcoded API key"),
            (r'(?:aws_access_key_id|aws_secret_access_key)\s*=\s*["\'][^"\']+["\']', "AWS credential"),
            (r'AKIA[0-9A-Z]{16}', "AWS Access Key ID"),
            (r'(?:sk-|pk_live_|sk_live_|rk_live_)[a-zA-Z0-9]{20,}', "API secret key"),
            (r'(?:ghp_|gho_|ghu_|ghs_|ghr_)[a-zA-Z0-9]{30,}', "GitHub token"),
            (r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', "Private key in source"),
            (r'(?:secret|token)\s*=\s*["\'][^"\']{8,}["\']', "Hardcoded secret/token"),
        ]

        exts = (
            ".py", ".java", ".js", ".ts", ".go", ".rb",
            ".yml", ".yaml", ".json", ".properties", ".xml", ".env",
        )
        for rel, content in self._get_files(exts):
            # Skip test files and examples
            if "test" in rel.lower() or "example" in rel.lower() or "mock" in rel.lower():
                continue
            for i, line in enumerate(content.split("\n"), 1):
                if line.strip().startswith("#") or line.strip().startswith("//"):
                    continue
                for pattern, desc in secret_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        self.report.findings.append(SecurityFinding(
                            severity="CRITICAL", category="hardcoded-secret",
                            file=rel, line=i, description=desc,
                            snippet=line.strip()[:100],
                            fix_suggestion="Use environment variables or a secrets manager",
                        ))
                        break  # one finding per line

    # ------------------------------------------------------------------
    # SQL injection
    # ------------------------------------------------------------------

    def _scan_sql_injection(self):
        """Find SQL injection vulnerabilities."""
        sql_patterns = [
            (r'(?:execute|cursor\.execute|query)\s*\(\s*["\'].*%s', "String format in SQL"),
            (r'(?:execute|cursor\.execute|query)\s*\(\s*f["\']', "f-string in SQL"),
            (r'(?:execute|cursor\.execute|query)\s*\(\s*["\'].*\+\s*', "Concatenation in SQL"),
            (r'(?:execute|cursor\.execute|query)\s*\(\s*["\'].*\.format\(', ".format() in SQL"),
            (r'Statement\s*\.\s*execute(?:Query|Update)\s*\(\s*["\'].*\+', "Java SQL concatenation"),
            (r'\$\{.*\}\s*(?:WHERE|AND|OR|SET|INSERT|UPDATE|DELETE)', "Template injection in SQL"),
        ]

        exts = (".py", ".java", ".js", ".ts", ".go", ".rb")
        for rel, content in self._get_files(exts):
            for i, line in enumerate(content.split("\n"), 1):
                for pattern, desc in sql_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        self.report.findings.append(SecurityFinding(
                            severity="HIGH", category="sql-injection",
                            file=rel, line=i, description=desc,
                            snippet=line.strip()[:100],
                            fix_suggestion="Use parameterized queries / prepared statements",
                        ))
                        break

    # ------------------------------------------------------------------
    # XSS
    # ------------------------------------------------------------------

    def _scan_xss(self):
        """Find XSS vulnerabilities."""
        xss_patterns = [
            (r'innerHTML\s*=', "Direct innerHTML assignment"),
            (r'document\.write\s*\(', "document.write usage"),
            (r'\.html\s*\(\s*[^)]*\+', "jQuery .html() with concatenation"),
            (r'dangerouslySetInnerHTML', "React dangerouslySetInnerHTML"),
            (r'v-html\s*=', "Vue v-html directive"),
            (r'\|\s*safe\b', "Django/Jinja |safe filter"),
            (r'@Html\.Raw\(', "ASP.NET Html.Raw"),
        ]

        exts = (".js", ".ts", ".jsx", ".tsx", ".html", ".vue", ".py", ".java")
        for rel, content in self._get_files(exts):
            for i, line in enumerate(content.split("\n"), 1):
                for pattern, desc in xss_patterns:
                    if re.search(pattern, line):
                        self.report.findings.append(SecurityFinding(
                            severity="HIGH", category="xss",
                            file=rel, line=i, description=desc,
                            snippet=line.strip()[:100],
                            fix_suggestion="Use text content or proper escaping/sanitization",
                        ))
                        break

    # ------------------------------------------------------------------
    # Insecure crypto
    # ------------------------------------------------------------------

    def _scan_insecure_crypto(self):
        """Find weak cryptography."""
        crypto_patterns = [
            (r'\bMD5\b', "MD5 hash (weak)", "MEDIUM"),
            (r'\bSHA1\b|\bSHA-1\b', "SHA-1 hash (weak)", "MEDIUM"),
            (r'DES\b|3DES\b|DESede', "DES/3DES encryption (weak)", "HIGH"),
            (r'ECB\b', "ECB mode (insecure)", "HIGH"),
            (r'Math\.random\(\)', "Math.random() for security (not cryptographic)", "MEDIUM"),
            (r'random\.random\(\)', "random.random() for security (not cryptographic)", "MEDIUM"),
        ]

        exts = (".py", ".java", ".js", ".ts", ".go")
        for rel, content in self._get_files(exts):
            for i, line in enumerate(content.split("\n"), 1):
                if line.strip().startswith("#") or line.strip().startswith("//"):
                    continue
                for pattern, desc, sev in crypto_patterns:
                    if re.search(pattern, line):
                        self.report.findings.append(SecurityFinding(
                            severity=sev, category="insecure-crypto",
                            file=rel, line=i, description=desc,
                            snippet=line.strip()[:100],
                            fix_suggestion="Use strong algorithms (SHA-256+, AES-GCM, secrets module)",
                        ))
                        break

    # ------------------------------------------------------------------
    # Path traversal
    # ------------------------------------------------------------------

    def _scan_path_traversal(self):
        """Find path traversal risks."""
        patterns = [
            (r'open\s*\(.*\+', "File open with concatenation"),
            (r'Path\s*\(.*\+', "Path construction with concatenation"),
            (r'os\.path\.join\s*\(.*request', "Path join with request data"),
            (r'new File\s*\(.*\+', "Java File with concatenation"),
        ]
        exts = (".py", ".java", ".js", ".ts")
        for rel, content in self._get_files(exts):
            for i, line in enumerate(content.split("\n"), 1):
                for pattern, desc in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        self.report.findings.append(SecurityFinding(
                            severity="MEDIUM", category="path-traversal",
                            file=rel, line=i, description=desc,
                            snippet=line.strip()[:100],
                            fix_suggestion="Validate and sanitize file paths, use Path.resolve()",
                        ))
                        break

    # ------------------------------------------------------------------
    # Command injection
    # ------------------------------------------------------------------

    def _scan_command_injection(self):
        """Find command injection risks."""
        patterns = [
            (r'os\.system\s*\(', "os.system() — use subprocess with list args"),
            (r'subprocess\.\w+\s*\(.*shell\s*=\s*True', "subprocess with shell=True"),
            (r'Runtime\.getRuntime\(\)\.exec\(.*\+', "Java Runtime.exec with concatenation"),
            (r'exec\s*\(.*\+', "exec() with dynamic input"),
            (r'eval\s*\(', "eval() usage"),
        ]
        exts = (".py", ".java", ".js", ".ts")
        for rel, content in self._get_files(exts):
            for i, line in enumerate(content.split("\n"), 1):
                if line.strip().startswith("#") or line.strip().startswith("//"):
                    continue
                for pattern, desc in patterns:
                    if re.search(pattern, line):
                        self.report.findings.append(SecurityFinding(
                            severity="HIGH", category="command-injection",
                            file=rel, line=i, description=desc,
                            snippet=line.strip()[:100],
                            fix_suggestion="Avoid shell=True, use parameterized subprocess calls",
                        ))
                        break

    # ------------------------------------------------------------------
    # Insecure dependencies
    # ------------------------------------------------------------------

    def _scan_insecure_deps(self):
        """Check for known insecure dependency patterns."""
        dep_checks = {
            "pom.xml": [
                (r'<version>1\.[0-5]\.</version>.*log4j', "log4j < 2.x (CVE-2021-44228)", "CRITICAL"),
                (r'struts.*1\.', "Struts 1.x (multiple CVEs)", "CRITICAL"),
            ],
            "package.json": [
                (r'"lodash"\s*:\s*"[<^~]?[0-3]\.', "lodash < 4 (prototype pollution)", "HIGH"),
                (r'"express"\s*:\s*"[<^~]?[0-3]\.', "express < 4 (multiple CVEs)", "HIGH"),
            ],
            "requirements.txt": [
                (r'django[<>=]=?[01]\.', "Django 0.x/1.x (end of life)", "HIGH"),
                (r'flask[<>=]=?0\.', "Flask 0.x (outdated)", "MEDIUM"),
            ],
        }

        for filename, checks in dep_checks.items():
            filepath = os.path.join(self.cwd, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, errors="replace") as f:
                        content = f.read()
                    for pattern, desc, sev in checks:
                        if re.search(pattern, content, re.IGNORECASE):
                            self.report.findings.append(SecurityFinding(
                                severity=sev, category="insecure-dep",
                                file=filename, line=0, description=desc,
                                fix_suggestion="Update to latest stable version",
                            ))
                except Exception:
                    logger.debug("Could not read %s", filepath)

    # ------------------------------------------------------------------
    # Sensitive data exposure
    # ------------------------------------------------------------------

    def _scan_sensitive_data_exposure(self):
        """Find sensitive data logging/exposure."""
        patterns = [
            (r'(?:log|print|console\.log).*(?:password|passwd|secret|token|api.?key)', "Logging sensitive data"),
            (r'(?:log|print|console\.log).*(?:credit.?card|ssn|social.?security)', "Logging PII"),
            (r'setHeader\s*\(\s*["\']Access-Control-Allow-Origin["\']\s*,\s*["\']\*["\']', "CORS wildcard origin"),
        ]
        exts = (".py", ".java", ".js", ".ts", ".go")
        for rel, content in self._get_files(exts):
            for i, line in enumerate(content.split("\n"), 1):
                for pattern, desc in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        self.report.findings.append(SecurityFinding(
                            severity="MEDIUM", category="data-exposure",
                            file=rel, line=i, description=desc,
                            snippet=line.strip()[:100],
                            fix_suggestion="Mask or remove sensitive data from logs",
                        ))
                        break


def format_security_report(report: SecurityReport) -> str:
    """Format for terminal display."""
    lines = []
    lines.append("  ╔══ SECURITY SCAN ══╗")
    lines.append(f"  ║ Repo: {os.path.basename(report.repo_path)}")
    lines.append(f"  ║ Files scanned: {report.scanned_files}")
    lines.append(f"  ║ Findings: {len(report.findings)}")
    lines.append("  ╚═══════════════════╝")

    if report.critical_count:
        lines.append(f"\n  🔴 CRITICAL: {report.critical_count}")
    if report.high_count:
        lines.append(f"  🟠 HIGH: {report.high_count}")
    if report.medium_count:
        lines.append(f"  🟡 MEDIUM: {report.medium_count}")
    if report.low_count:
        lines.append(f"  🟢 LOW: {report.low_count}")

    # Group by category
    categories: dict[str, list[SecurityFinding]] = {}
    for f in report.findings:
        categories.setdefault(f.category, []).append(f)

    severity_icons = {
        "CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡",
        "LOW": "🟢", "INFO": "ℹ️",
    }

    for cat, findings in sorted(categories.items()):
        lines.append(f"\n  {cat.replace('-', ' ').title()} ({len(findings)}):")
        for f in findings[:10]:
            icon = severity_icons.get(f.severity, "·")
            lines.append(f"    {icon} {f.file}:{f.line} — {f.description}")
            if f.snippet:
                lines.append(f"       {f.snippet[:80]}")
        if len(findings) > 10:
            lines.append(f"    ... and {len(findings) - 10} more")

    if not report.findings:
        lines.append("\n  ✓ No security issues found!")

    return "\n".join(lines)
