"""Input validation coverage auditor — find endpoints missing validation.

Scans source code for HTTP endpoints (POST/PUT/PATCH) and checks for:
  - Missing request body validation
  - No length/max_length limits on string inputs
  - User text not sanitized (HTML/JS injection)
  - String concatenation in SQL queries (injection risk)
  - Missing type validation on inputs

SECURITY: No actual user data is processed — static analysis only.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.security.input_audit")

# ---------------------------------------------------------------------------
# Supported extensions & skip dirs
# ---------------------------------------------------------------------------

_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb",
    ".cs", ".php", ".rs", ".kt", ".scala",
}

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".tox", "venv", ".venv",
    "dist", "build", ".eggs", "vendor", "third_party", ".mypy_cache",
    "test", "tests", "__tests__", "spec",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class InputFinding:
    """A single input validation issue."""

    file: str
    line: int
    endpoint: str
    issue: str
    severity: str  # critical | high | medium | low
    suggestion: str


# ---------------------------------------------------------------------------
# Endpoint detection patterns
# ---------------------------------------------------------------------------

# Python (Flask, FastAPI, Django)
_PY_ENDPOINT_PATTERNS = [
    re.compile(r"""@\w+\.(?:route|api_route)\s*\(\s*["'][^"']+["']\s*,.*methods\s*=\s*\[.*(?:POST|PUT|PATCH)""", re.IGNORECASE),
    re.compile(r"""@\w+\.(?:post|put|patch)\s*\(\s*["']([^"']+)["']""", re.IGNORECASE),
    re.compile(r"""@api_view\s*\(\s*\[.*(?:POST|PUT|PATCH)""", re.IGNORECASE),
]

# JavaScript/TypeScript (Express, Koa, NestJS)
_JS_ENDPOINT_PATTERNS = [
    re.compile(r"""(?:app|router)\.\s*(?:post|put|patch)\s*\(\s*["']([^"']+)["']""", re.IGNORECASE),
    re.compile(r"""@(?:Post|Put|Patch)\s*\(\s*["']?([^"')]*?)["']?\s*\)"""),
]

# Java (Spring)
_JAVA_ENDPOINT_PATTERNS = [
    re.compile(r"""@(?:PostMapping|PutMapping|PatchMapping)\s*\(\s*(?:value\s*=\s*)?["']?([^"')]*?)["']?\s*\)"""),
    re.compile(r"""@RequestMapping\s*\(.*method\s*=\s*.*(?:POST|PUT|PATCH)""", re.IGNORECASE),
]

# Go (net/http, Gin, Echo)
_GO_ENDPOINT_PATTERNS = [
    re.compile(r"""(?:r|router|e|g|group)\.\s*(?:POST|PUT|PATCH)\s*\(\s*["']([^"']+)["']"""),
    re.compile(r"""HandleFunc\s*\(\s*["']([^"']+)["']"""),
]

# ---------------------------------------------------------------------------
# Validation check patterns
# ---------------------------------------------------------------------------

# Body validation patterns (presence means body IS validated)
_BODY_VALIDATION_PATTERNS = [
    re.compile(r"\bBaseModel\b"),           # Pydantic
    re.compile(r"\b(?:Body|Field)\s*\("),   # FastAPI Body/Field
    re.compile(r"\bSerializer\b"),          # DRF
    re.compile(r"\bforms?\.\w+Field\b"),    # Django forms
    re.compile(r"\bvalidate\s*\("),         # generic validate()
    re.compile(r"\bschema\.validate\b"),    # schema validation
    re.compile(r"\bJoi\.object\b"),         # Joi (JS)
    re.compile(r"\bzod\.object\b"),         # Zod (TS)
    re.compile(r"\bajv\.compile\b"),        # AJV (JS)
    re.compile(r"\byup\.object\b"),         # Yup (JS)
    re.compile(r"@Valid\b"),                 # Java Bean Validation
    re.compile(r"@Validated\b"),            # Spring
    re.compile(r"\bBindJSON\b"),            # Go Gin
    re.compile(r"\bShouldBindJSON\b"),      # Go Gin
    re.compile(r"\bDecoder\b.*\bDecode\b"), # Go json
]

# Length limit patterns
_LENGTH_LIMIT_PATTERNS = [
    re.compile(r"\bmax_length\s*=", re.IGNORECASE),
    re.compile(r"\bmaxLength\b", re.IGNORECASE),
    re.compile(r"\bmax_len\b", re.IGNORECASE),
    re.compile(r"\bMaxLen\b"),
    re.compile(r"\blt\s*=\s*\d+"),          # Pydantic Field(lt=...)
    re.compile(r"\ble\s*=\s*\d+"),          # Pydantic Field(le=...)
    re.compile(r"\.max\s*\(\s*\d+\s*\)"),   # Joi/Yup .max()
    re.compile(r"\bSize\s*\(.*max\s*="),    # Java @Size
    re.compile(r"\bLength\s*\(.*max\s*="),  # Hibernate @Length
]

# Sanitization patterns
_SANITIZATION_PATTERNS = [
    re.compile(r"\bescape\s*\(", re.IGNORECASE),
    re.compile(r"\bsanitize\b", re.IGNORECASE),
    re.compile(r"\bbleach\b", re.IGNORECASE),
    re.compile(r"\bhtml\.escape\b"),
    re.compile(r"\bmarkup_safe\b", re.IGNORECASE),
    re.compile(r"\bDOMPurify\b"),
    re.compile(r"\bxss\b", re.IGNORECASE),
    re.compile(r"\bstrip_tags\b", re.IGNORECASE),
    re.compile(r"\bhtmlspecialchars\b"),
    re.compile(r"\bStringEscapeUtils\b"),
    re.compile(r"\btemplate\.HTMLEscapeString\b"),
]

# SQL injection patterns (string concatenation in queries)
_SQL_INJECTION_PATTERNS = [
    re.compile(r"""(?:execute|query|raw)\s*\(\s*["']?\s*(?:SELECT|INSERT|UPDATE|DELETE).*?\+""", re.IGNORECASE),
    re.compile(r"""(?:execute|query|raw)\s*\(\s*f["']""", re.IGNORECASE),
    re.compile(r"""(?:execute|query|raw)\s*\(\s*["'].*?%s.*?["']\s*%""", re.IGNORECASE),
    re.compile(r"""\.format\s*\(.*?\).*?(?:execute|query|raw)""", re.IGNORECASE),
    re.compile(r"""(?:execute|query)\s*\(\s*.*?\$\{""", re.IGNORECASE),
    re.compile(r"""String\.format\s*\(\s*["'].*(?:SELECT|INSERT|UPDATE|DELETE)""", re.IGNORECASE),
]

# Type validation patterns
_TYPE_VALIDATION_PATTERNS = [
    re.compile(r"""\b(?:int|float|str|bool)\s*\("""),       # Python type casting
    re.compile(r"""\bisinstance\s*\("""),                     # Python isinstance
    re.compile(r"""\bparseInt\b"""),                          # JS
    re.compile(r"""\bparseFloat\b"""),                        # JS
    re.compile(r"""\btypeof\b"""),                            # JS typeof
    re.compile(r"""\bNumber\s*\("""),                         # JS
    re.compile(r"""\b@IsInt\b"""),                            # class-validator
    re.compile(r"""\b@IsString\b"""),                         # class-validator
    re.compile(r"""\b@IsEmail\b"""),                          # class-validator
    re.compile(r"""\bInteger\.parseInt\b"""),                 # Java
    re.compile(r"""\b(?:constr|conint|confloat)\s*\("""),    # Pydantic constrained types
    re.compile(r"""\bField\s*\("""),                          # Pydantic Field
    re.compile(r"""\bstrconv\.Atoi\b"""),                     # Go
]


# ---------------------------------------------------------------------------
# Main auditor
# ---------------------------------------------------------------------------


class InputAuditor:
    """Audit endpoints for input validation coverage."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.info("InputAuditor initialised for %s", cwd)

    def audit(self) -> list[InputFinding]:
        """Run input validation audit. Returns list of findings."""
        start = time.time()
        files = self._collect_files()
        logger.info("Scanning %d files for input validation issues", len(files))

        all_findings: list[InputFinding] = []
        for fpath in files:
            try:
                all_findings.extend(self._scan_file(fpath))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error scanning %s: %s", fpath, exc)

        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_findings.sort(key=lambda f: (sev_order.get(f.severity, 9), f.file, f.line))

        elapsed = time.time() - start
        logger.info("Input audit complete: %d findings in %.2fs", len(all_findings), elapsed)
        return all_findings

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

    # -- endpoint finding --

    def _find_endpoints(self, rel_path: str, lines: list[str]) -> list[dict]:
        """Find POST/PUT/PATCH endpoints in source code."""
        endpoints: list[dict] = []
        suffix = Path(rel_path).suffix

        patterns: list[re.Pattern] = []
        if suffix == ".py":
            patterns = _PY_ENDPOINT_PATTERNS
        elif suffix in (".js", ".ts", ".jsx", ".tsx"):
            patterns = _JS_ENDPOINT_PATTERNS
        elif suffix == ".java":
            patterns = _JAVA_ENDPOINT_PATTERNS
        elif suffix == ".go":
            patterns = _GO_ENDPOINT_PATTERNS

        full_text = "\n".join(lines)
        for i, line in enumerate(lines):
            for pat in patterns:
                m = pat.search(line)
                if m:
                    route = m.group(1) if m.lastindex and m.lastindex >= 1 else "<detected>"
                    # Use full file text as context so imports/models above are visible
                    body_end = min(i + 50, len(lines))
                    func_body = "\n".join(lines[i:body_end])
                    # Prepend file-level context (imports, class defs) for validation checks
                    file_context = "\n".join(lines[:i]) + "\n" + func_body
                    endpoints.append({
                        "line": i + 1,
                        "route": route,
                        "func_body": file_context,
                    })
                    break
        return endpoints

    # -- file scanning --

    def _scan_file(self, path: Path) -> list[InputFinding]:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            return []

        lines = content.splitlines()
        rel = str(path.relative_to(self.cwd))
        endpoints = self._find_endpoints(rel, lines)

        findings: list[InputFinding] = []
        for ep in endpoints:
            body = ep["func_body"]
            findings.extend(self._check_body_validation(rel, ep["line"], ep["route"], body))
            findings.extend(self._check_length_limits(rel, ep["line"], ep["route"], body))
            findings.extend(self._check_sanitization(rel, ep["line"], ep["route"], body))
            findings.extend(self._check_sql_params(rel, ep["line"], ep["route"], body))
            findings.extend(self._check_type_validation(rel, ep["line"], ep["route"], body))
        return findings

    # -- validation checks --

    def _check_body_validation(self, file: str, line: int, endpoint: str, func_body: str) -> list[InputFinding]:
        for pat in _BODY_VALIDATION_PATTERNS:
            if pat.search(func_body):
                return []
        return [InputFinding(
            file=file, line=line, endpoint=endpoint,
            issue="No request body validation — endpoint accepts unvalidated input",
            severity="high",
            suggestion="Add Pydantic model, Joi schema, or Bean Validation to validate request body",
        )]

    def _check_length_limits(self, file: str, line: int, endpoint: str, func_body: str) -> list[InputFinding]:
        for pat in _LENGTH_LIMIT_PATTERNS:
            if pat.search(func_body):
                return []
        return [InputFinding(
            file=file, line=line, endpoint=endpoint,
            issue="No length limits on input fields — potential DoS or buffer abuse",
            severity="medium",
            suggestion="Add max_length / maxLength constraints on string fields",
        )]

    def _check_sanitization(self, file: str, line: int, endpoint: str, func_body: str) -> list[InputFinding]:
        # Only flag if there are string inputs being used in responses or templates
        has_string_use = bool(re.search(r"(?:render|template|response|html|json_response)", func_body, re.IGNORECASE))
        if not has_string_use:
            return []
        for pat in _SANITIZATION_PATTERNS:
            if pat.search(func_body):
                return []
        return [InputFinding(
            file=file, line=line, endpoint=endpoint,
            issue="User input not sanitized before output — potential XSS",
            severity="high",
            suggestion="Sanitize user text with bleach/DOMPurify/html.escape before rendering",
        )]

    def _check_sql_params(self, file: str, line: int, endpoint: str, func_body: str) -> list[InputFinding]:
        findings: list[InputFinding] = []
        for pat in _SQL_INJECTION_PATTERNS:
            if pat.search(func_body):
                findings.append(InputFinding(
                    file=file, line=line, endpoint=endpoint,
                    issue="String concatenation/interpolation in SQL query — SQL injection risk",
                    severity="critical",
                    suggestion="Use parameterized queries (?, %s placeholders) or ORM query builders",
                ))
                break
        return findings

    def _check_type_validation(self, file: str, line: int, endpoint: str, func_body: str) -> list[InputFinding]:
        for pat in _TYPE_VALIDATION_PATTERNS:
            if pat.search(func_body):
                return []
        return [InputFinding(
            file=file, line=line, endpoint=endpoint,
            issue="No type validation on inputs — may accept unexpected types",
            severity="low",
            suggestion="Add explicit type checks or use typed schema validation (Pydantic, Zod, etc.)",
        )]


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def format_input_report(findings: list[InputFinding]) -> str:
    """Format findings as a human-readable text report."""
    if not findings:
        return "  No input validation issues found."

    sev_icons = {"critical": "[!]", "high": "[H]", "medium": "[M]", "low": "[L]"}
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    lines: list[str] = []
    lines.append(f"  Input Validation Audit — {len(findings)} finding(s)\n")

    by_sev: dict[str, int] = {}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    parts = [f"{s}: {c}" for s, c in sorted(by_sev.items(), key=lambda x: sev_order.get(x[0], 9))]
    lines.append(f"  Summary: {', '.join(parts)}\n")

    for f in findings:
        icon = sev_icons.get(f.severity, "[?]")
        lines.append(f"  {icon} {f.severity.upper():8s} {f.file}:{f.line}  {f.endpoint}")
        lines.append(f"           {f.issue}")
        lines.append(f"           Suggestion: {f.suggestion}")
        lines.append("")

    return "\n".join(lines)


def input_report_to_json(findings: list[InputFinding]) -> dict:
    """Convert findings to JSON-serializable dict."""
    return {
        "total": len(findings),
        "by_severity": _count_by_severity(findings),
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "endpoint": f.endpoint,
                "issue": f.issue,
                "severity": f.severity,
                "suggestion": f.suggestion,
            }
            for f in findings
        ],
    }


def _count_by_severity(findings: list[InputFinding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts
