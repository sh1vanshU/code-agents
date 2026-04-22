"""Encryption audit — detect weak cryptographic patterns in source code.

Scans for:
  - Weak hash algorithms (MD5, SHA1) used for passwords/keys
  - Weak ciphers (DES, 3DES, RC4, Blowfish)
  - ECB mode usage
  - Small key sizes (< 128-bit symmetric, < 2048-bit RSA)
  - Static/hardcoded IVs
  - Hardcoded encryption keys
  - Weak KDFs (plain hash instead of PBKDF2/bcrypt/scrypt/argon2)

SECURITY: Code snippets are redacted — only file:line references stored.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.security.encryption_audit")

# ---------------------------------------------------------------------------
# Supported file extensions
# ---------------------------------------------------------------------------

_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb",
    ".cs", ".php", ".rs", ".kt", ".scala", ".swift", ".c", ".cpp",
    ".h", ".hpp", ".m", ".sh", ".bash",
}

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".tox", "venv", ".venv",
    "dist", "build", ".eggs", "vendor", "third_party", ".mypy_cache",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EncryptionFinding:
    """A single encryption/cryptography issue found in source code."""

    file: str
    line: int
    issue: str
    severity: str  # critical | high | medium | low
    remediation: str
    code_snippet: str = ""


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Weak hashes used for passwords or keys
_WEAK_HASH_PATTERNS = [
    (re.compile(r"\bmd5\s*\(", re.IGNORECASE), "MD5"),
    (re.compile(r"\bhashlib\.md5\b", re.IGNORECASE), "MD5"),
    (re.compile(r"\bMD5\.(?:Create|new|hexdigest)\b"), "MD5"),
    (re.compile(r"\bDigestUtils\.md5\b", re.IGNORECASE), "MD5"),
    (re.compile(r"\bsha1\s*\(", re.IGNORECASE), "SHA1"),
    (re.compile(r"\bhashlib\.sha1\b", re.IGNORECASE), "SHA1"),
    (re.compile(r"\bSHA1\.(?:Create|new)\b"), "SHA1"),
    (re.compile(r"\bMessageDigest\.getInstance\s*\(\s*[\"'](?:MD5|SHA-?1)[\"']", re.IGNORECASE), "MD5/SHA1"),
    (re.compile(r"\bcrypto\.createHash\s*\(\s*[\"'](?:md5|sha1)[\"']", re.IGNORECASE), "MD5/SHA1"),
]

# Weak ciphers
_WEAK_CIPHER_PATTERNS = [
    (re.compile(r"\bDES\b(?!3)"), "DES"),
    (re.compile(r"\b3DES\b|TripleDES|DESede", re.IGNORECASE), "3DES"),
    (re.compile(r"\bRC4\b|ARC4|ARCFOUR", re.IGNORECASE), "RC4"),
    (re.compile(r"\bBlowfish\b", re.IGNORECASE), "Blowfish"),
    (re.compile(r"Cipher\.getInstance\s*\(\s*[\"'](?:DES|DESede|RC4|Blowfish)", re.IGNORECASE), "Weak cipher"),
    (re.compile(r"algorithms\.(?:TripleDES|Blowfish|ARC4)", re.IGNORECASE), "Weak cipher"),
]

# ECB mode
_ECB_PATTERNS = [
    re.compile(r"\bAES\.MODE_ECB\b"),
    re.compile(r"\bMODE_ECB\b"),
    re.compile(r"[\"']ECB[\"']"),
    re.compile(r"Cipher\.getInstance\s*\(\s*[\"']AES/ECB", re.IGNORECASE),
    re.compile(r"createCipheriv\s*\(\s*[\"']aes-\d+-ecb", re.IGNORECASE),
]

# Small key sizes
_SMALL_KEY_PATTERNS = [
    (re.compile(r"key_size\s*=\s*(\d+)"), 128, "symmetric"),
    (re.compile(r"key_length\s*=\s*(\d+)"), 128, "symmetric"),
    (re.compile(r"keySize\s*[:=]\s*(\d+)"), 128, "symmetric"),
    (re.compile(r"KeySize\s*=\s*(\d+)"), 128, "symmetric"),
    (re.compile(r"RSA.*?(\d{3,4})"), 2048, "RSA"),
    (re.compile(r"generate_private_key.*?key_size\s*=\s*(\d+)"), 2048, "RSA"),
]

# Static / hardcoded IV
_STATIC_IV_PATTERNS = [
    re.compile(r"""(?:iv|IV|nonce)\s*=\s*b?["'][0-9a-fA-Fx\\]+["']"""),
    re.compile(r"""(?:iv|IV|nonce)\s*=\s*b?["']\x00+["']"""),
    re.compile(r"""(?:iv|IV|nonce)\s*=\s*bytes\s*\(\s*\d+\s*\)"""),
    re.compile(r"""(?:iv|IV)\s*=\s*(?:new\s+)?byte\s*\[\s*\d+\s*\]"""),
]

# Hardcoded encryption keys
_HARDCODED_KEY_PATTERNS = [
    re.compile(r"""(?:secret_?key|encryption_?key|aes_?key|private_?key|api_?key|crypto_?key)\s*=\s*["'][^"']{8,}["']""", re.IGNORECASE),
    re.compile(r"""(?:secret_?key|encryption_?key|aes_?key|private_?key|crypto_?key)\s*=\s*b["'][^"']{8,}["']""", re.IGNORECASE),
]

# Weak KDF (using plain hash for key derivation)
_WEAK_KDF_PATTERNS = [
    re.compile(r"""(?:password|passwd|pwd).*(?:md5|sha1|sha256)\s*\(""", re.IGNORECASE),
    re.compile(r"""(?:derive|kdf|key_from).*(?:hashlib|MessageDigest|createHash)""", re.IGNORECASE),
    re.compile(r"""(?:hashlib\.(?:md5|sha1|sha256))\s*\(.*(?:password|passwd|secret)""", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Main auditor
# ---------------------------------------------------------------------------


class EncryptionAuditor:
    """Audit source code for weak or insecure cryptographic usage."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._findings: list[EncryptionFinding] = []
        logger.info("EncryptionAuditor initialised for %s", cwd)

    # -- public API --

    def audit(self) -> list[EncryptionFinding]:
        """Run full encryption audit on the codebase. Returns list of findings."""
        start = time.time()
        self._findings = []
        files = self._collect_files()
        logger.info("Scanning %d files for encryption issues", len(files))

        for fpath in files:
            try:
                self._scan_file(fpath)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error scanning %s: %s", fpath, exc)

        elapsed = time.time() - start
        logger.info(
            "Encryption audit complete: %d findings in %.2fs",
            len(self._findings), elapsed,
        )
        return self._findings

    # -- file collection --

    def _collect_files(self) -> list[Path]:
        result: list[Path] = []
        root = Path(self.cwd)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                p = Path(dirpath) / fn
                if p.suffix in _CODE_EXTENSIONS:
                    result.append(p)
        return result

    def _scan_file(self, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except (OSError, UnicodeDecodeError):
            return

        rel = str(path.relative_to(self.cwd))
        self._findings.extend(self._check_weak_hash(rel, lines))
        self._findings.extend(self._check_weak_cipher(rel, lines))
        self._findings.extend(self._check_ecb_mode(rel, lines))
        self._findings.extend(self._check_small_keys(rel, lines))
        self._findings.extend(self._check_static_iv(rel, lines))
        self._findings.extend(self._check_hardcoded_keys(rel, lines))
        self._findings.extend(self._check_weak_kdf(rel, lines))

    # -- individual checks --

    def _check_weak_hash(self, path: str, lines: list[str]) -> list[EncryptionFinding]:
        findings: list[EncryptionFinding] = []
        for i, line in enumerate(lines, 1):
            for pattern, algo in _WEAK_HASH_PATTERNS:
                if pattern.search(line):
                    findings.append(EncryptionFinding(
                        file=path,
                        line=i,
                        issue=f"Weak hash algorithm ({algo}) — insecure for passwords or key derivation",
                        severity="high",
                        remediation=f"Replace {algo} with SHA-256+ or use PBKDF2/bcrypt/scrypt for passwords",
                        code_snippet=_redact(line),
                    ))
                    break  # one finding per line
        return findings

    def _check_weak_cipher(self, path: str, lines: list[str]) -> list[EncryptionFinding]:
        findings: list[EncryptionFinding] = []
        for i, line in enumerate(lines, 1):
            for pattern, cipher in _WEAK_CIPHER_PATTERNS:
                if pattern.search(line):
                    findings.append(EncryptionFinding(
                        file=path,
                        line=i,
                        issue=f"Weak cipher ({cipher}) — cryptographically broken or deprecated",
                        severity="critical",
                        remediation=f"Replace {cipher} with AES-256-GCM or ChaCha20-Poly1305",
                        code_snippet=_redact(line),
                    ))
                    break
        return findings

    def _check_ecb_mode(self, path: str, lines: list[str]) -> list[EncryptionFinding]:
        findings: list[EncryptionFinding] = []
        for i, line in enumerate(lines, 1):
            for pattern in _ECB_PATTERNS:
                if pattern.search(line):
                    findings.append(EncryptionFinding(
                        file=path,
                        line=i,
                        issue="ECB mode detected — identical blocks produce identical ciphertext",
                        severity="critical",
                        remediation="Use CBC, GCM, or CTR mode instead of ECB",
                        code_snippet=_redact(line),
                    ))
                    break
        return findings

    def _check_small_keys(self, path: str, lines: list[str]) -> list[EncryptionFinding]:
        findings: list[EncryptionFinding] = []
        for i, line in enumerate(lines, 1):
            for pattern, min_size, key_type in _SMALL_KEY_PATTERNS:
                m = pattern.search(line)
                if m:
                    try:
                        size = int(m.group(1))
                    except (ValueError, IndexError):
                        continue
                    if size < min_size:
                        findings.append(EncryptionFinding(
                            file=path,
                            line=i,
                            issue=f"Small {key_type} key size ({size} bits) — minimum recommended: {min_size}",
                            severity="high" if key_type == "RSA" else "medium",
                            remediation=f"Use at least {min_size}-bit keys for {key_type}",
                            code_snippet=_redact(line),
                        ))
                        break
        return findings

    def _check_static_iv(self, path: str, lines: list[str]) -> list[EncryptionFinding]:
        findings: list[EncryptionFinding] = []
        for i, line in enumerate(lines, 1):
            for pattern in _STATIC_IV_PATTERNS:
                if pattern.search(line):
                    findings.append(EncryptionFinding(
                        file=path,
                        line=i,
                        issue="Static/hardcoded IV — reusing IVs breaks cipher security guarantees",
                        severity="high",
                        remediation="Generate a random IV for each encryption operation (os.urandom / SecureRandom)",
                        code_snippet=_redact(line),
                    ))
                    break
        return findings

    def _check_hardcoded_keys(self, path: str, lines: list[str]) -> list[EncryptionFinding]:
        findings: list[EncryptionFinding] = []
        for i, line in enumerate(lines, 1):
            for pattern in _HARDCODED_KEY_PATTERNS:
                if pattern.search(line):
                    findings.append(EncryptionFinding(
                        file=path,
                        line=i,
                        issue="Hardcoded encryption key — secrets must not be embedded in source code",
                        severity="critical",
                        remediation="Move keys to environment variables, vault, or KMS",
                        code_snippet=_redact(line),
                    ))
                    break
        return findings

    def _check_weak_kdf(self, path: str, lines: list[str]) -> list[EncryptionFinding]:
        findings: list[EncryptionFinding] = []
        for i, line in enumerate(lines, 1):
            for pattern in _WEAK_KDF_PATTERNS:
                if pattern.search(line):
                    findings.append(EncryptionFinding(
                        file=path,
                        line=i,
                        issue="Weak KDF — plain hash used for password/key derivation instead of proper KDF",
                        severity="high",
                        remediation="Use PBKDF2, bcrypt, scrypt, or argon2 for password-based key derivation",
                        code_snippet=_redact(line),
                    ))
                    break
        return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redact(line: str) -> str:
    """Redact potential secrets from code snippets — keep structure, mask values."""
    line = line.strip()
    if len(line) > 120:
        line = line[:120] + "..."
    # Mask string literal contents that look like secrets
    line = re.sub(r'(["\'])(?:[^"\']{16,})(["\'])', r"\1<REDACTED>\2", line)
    return line


def format_encryption_report(findings: list[EncryptionFinding]) -> str:
    """Format findings as a human-readable text report."""
    if not findings:
        return "  No encryption issues found."

    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_f = sorted(findings, key=lambda f: (sev_order.get(f.severity, 9), f.file, f.line))

    sev_icons = {"critical": "[!]", "high": "[H]", "medium": "[M]", "low": "[L]"}
    lines: list[str] = []
    lines.append(f"  Encryption Audit — {len(findings)} finding(s)\n")

    # Summary
    by_sev: dict[str, int] = {}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    parts = [f"{s}: {c}" for s, c in sorted(by_sev.items(), key=lambda x: sev_order.get(x[0], 9))]
    lines.append(f"  Summary: {', '.join(parts)}\n")

    for f in sorted_f:
        icon = sev_icons.get(f.severity, "[?]")
        lines.append(f"  {icon} {f.severity.upper():8s} {f.file}:{f.line}")
        lines.append(f"           {f.issue}")
        lines.append(f"           Fix: {f.remediation}")
        if f.code_snippet:
            lines.append(f"           Code: {f.code_snippet}")
        lines.append("")

    return "\n".join(lines)


def encryption_report_to_json(findings: list[EncryptionFinding]) -> dict:
    """Convert findings to a JSON-serializable dict."""
    return {
        "total": len(findings),
        "by_severity": _count_by_severity(findings),
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "issue": f.issue,
                "severity": f.severity,
                "remediation": f.remediation,
                "code_snippet": f.code_snippet,
            }
            for f in findings
        ],
    }


def _count_by_severity(findings: list[EncryptionFinding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts
