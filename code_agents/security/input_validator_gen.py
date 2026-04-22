"""Input Validator Generator — analyze endpoints, generate validation code.

Scans API endpoint handlers for missing input validation and generates
protective code against XSS, SQL injection, path traversal, and more.

Usage:
    from code_agents.security.input_validator_gen import InputValidatorGen, InputValidatorConfig
    gen = InputValidatorGen(InputValidatorConfig(cwd="/path/to/repo"))
    result = gen.analyze()
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.security.input_validator_gen")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class InputValidatorConfig:
    cwd: str = "."
    max_files: int = 500
    frameworks: list[str] = field(default_factory=lambda: ["fastapi", "flask", "express", "django"])


@dataclass
class EndpointInfo:
    """A discovered API endpoint."""
    file: str
    line: int
    method: str  # GET, POST, etc.
    path: str
    handler: str = ""
    parameters: list[str] = field(default_factory=list)


@dataclass
class ValidationGap:
    """A missing or weak input validation."""
    file: str
    line: int
    parameter: str
    vuln_type: str  # "xss", "sqli", "path_traversal", "command_injection", "ssrf"
    severity: str = "high"
    description: str = ""
    current_validation: str = "none"


@dataclass
class GeneratedValidator:
    """Generated validation code for an endpoint."""
    file: str
    endpoint: str
    language: str = "python"
    validation_code: str = ""
    import_code: str = ""
    vuln_types_covered: list[str] = field(default_factory=list)


@dataclass
class InputValidatorReport:
    """Full input validation analysis."""
    endpoints_scanned: int = 0
    gaps_found: int = 0
    validators_generated: int = 0
    endpoints: list[EndpointInfo] = field(default_factory=list)
    gaps: list[ValidationGap] = field(default_factory=list)
    validators: list[GeneratedValidator] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

FASTAPI_ROUTE_RE = re.compile(
    r'@(?:app|router)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']'
)
FLASK_ROUTE_RE = re.compile(
    r'@(?:app|bp|blueprint)\.(route)\(\s*["\']([^"\']+)["\']'
)
EXPRESS_ROUTE_RE = re.compile(
    r'(?:app|router)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']'
)
DJANGO_URL_RE = re.compile(
    r"path\(\s*['\"]([^'\"]+)['\"]"
)

# Dangerous sinks that need input validation
SQLI_SINKS = re.compile(
    r'(?:execute|raw|cursor\.execute|query)\s*\(\s*[f"\'].*\{|'
    r'(?:execute|raw|cursor\.execute|query)\s*\(\s*["\'].*%\s*[(\w]|'
    r'\.format\s*\(',
    re.IGNORECASE,
)
XSS_SINKS = re.compile(
    r'(?:innerHTML|outerHTML|document\.write|\.html\(|render_template_string)\s*\(',
    re.IGNORECASE,
)
PATH_TRAVERSAL_SINKS = re.compile(
    r'(?:open|read_file|send_file|send_from_directory)\s*\(\s*(?:request\.|params\.|req\.)',
    re.IGNORECASE,
)
CMD_INJECTION_SINKS = re.compile(
    r'(?:os\.system|subprocess\.(?:call|run|Popen)|exec|eval)\s*\(\s*(?:f["\']|.*\+|.*format)',
    re.IGNORECASE,
)

VULN_PATTERNS = [
    ("sqli", SQLI_SINKS, "SQL injection via string interpolation"),
    ("xss", XSS_SINKS, "Cross-site scripting via unsafe DOM/template rendering"),
    ("path_traversal", PATH_TRAVERSAL_SINKS, "Path traversal via unvalidated file path"),
    ("command_injection", CMD_INJECTION_SINKS, "Command injection via unsanitised input"),
]

# ---------------------------------------------------------------------------
# Validator templates
# ---------------------------------------------------------------------------

PYTHON_VALIDATORS = {
    "sqli": '''def validate_sql_param(value: str) -> str:
    """Reject SQL injection patterns."""
    dangerous = ["'", '"', ";", "--", "/*", "*/", "DROP", "UNION", "SELECT"]
    upper = value.upper()
    for token in dangerous:
        if token.upper() in upper:
            raise ValueError(f"Invalid input: suspicious SQL token")
    return value''',

    "xss": '''import html
def sanitize_html(value: str) -> str:
    """Escape HTML entities to prevent XSS."""
    return html.escape(value, quote=True)''',

    "path_traversal": '''import os
def validate_path(value: str, base_dir: str) -> str:
    """Prevent path traversal attacks."""
    resolved = os.path.realpath(os.path.join(base_dir, value))
    if not resolved.startswith(os.path.realpath(base_dir)):
        raise ValueError("Path traversal detected")
    return resolved''',

    "command_injection": '''import shlex
def sanitize_command_arg(value: str) -> str:
    """Escape shell metacharacters."""
    return shlex.quote(value)''',
}


# ---------------------------------------------------------------------------
# InputValidatorGen
# ---------------------------------------------------------------------------


class InputValidatorGen:
    """Analyze endpoints and generate input validation code."""

    def __init__(self, config: Optional[InputValidatorConfig] = None):
        self.config = config or InputValidatorConfig()

    def analyze(self) -> InputValidatorReport:
        """Scan endpoints, find validation gaps, generate validators."""
        logger.info("Scanning endpoints in %s", self.config.cwd)
        report = InputValidatorReport()

        root = Path(self.config.cwd)
        endpoints = self._discover_endpoints(root)
        report.endpoints = endpoints
        report.endpoints_scanned = len(endpoints)

        gaps = self._find_gaps(root)
        report.gaps = gaps
        report.gaps_found = len(gaps)

        validators = self._generate_validators(gaps)
        report.validators = validators
        report.validators_generated = len(validators)

        report.summary = (
            f"{report.endpoints_scanned} endpoints scanned, "
            f"{report.gaps_found} validation gaps, "
            f"{report.validators_generated} validators generated."
        )
        logger.info("Input validation analysis complete: %s", report.summary)
        return report

    def _discover_endpoints(self, root: Path) -> list[EndpointInfo]:
        """Find API endpoints in the codebase."""
        endpoints: list[EndpointInfo] = []
        count = 0
        for ext in ("*.py", "*.js", "*.ts"):
            for fpath in root.rglob(ext):
                if count >= self.config.max_files:
                    break
                count += 1
                if any(p.startswith(".") or p == "node_modules" for p in fpath.parts):
                    continue
                rel = str(fpath.relative_to(root))
                try:
                    content = fpath.read_text(errors="replace")
                except Exception:
                    continue
                for line_no, line in enumerate(content.splitlines(), 1):
                    for rx in (FASTAPI_ROUTE_RE, FLASK_ROUTE_RE, EXPRESS_ROUTE_RE):
                        m = rx.search(line)
                        if m:
                            endpoints.append(EndpointInfo(
                                file=rel, line=line_no,
                                method=m.group(1).upper(), path=m.group(2),
                            ))
                    dm = DJANGO_URL_RE.search(line)
                    if dm:
                        endpoints.append(EndpointInfo(
                            file=rel, line=line_no, method="ANY", path=dm.group(1),
                        ))
        return endpoints

    def _find_gaps(self, root: Path) -> list[ValidationGap]:
        """Find dangerous sinks without prior validation."""
        gaps: list[ValidationGap] = []
        count = 0
        for ext in ("*.py", "*.js", "*.ts"):
            for fpath in root.rglob(ext):
                if count >= self.config.max_files:
                    break
                count += 1
                if any(p.startswith(".") or p == "node_modules" for p in fpath.parts):
                    continue
                rel = str(fpath.relative_to(root))
                try:
                    lines = fpath.read_text(errors="replace").splitlines()
                except Exception:
                    continue
                for idx, line in enumerate(lines, 1):
                    for vuln_type, pattern, desc in VULN_PATTERNS:
                        if pattern.search(line):
                            gaps.append(ValidationGap(
                                file=rel, line=idx,
                                parameter="user_input",
                                vuln_type=vuln_type,
                                description=desc,
                            ))
        return gaps

    def _generate_validators(self, gaps: list[ValidationGap]) -> list[GeneratedValidator]:
        """Generate validation code for each gap type."""
        seen_types: set[str] = set()
        validators: list[GeneratedValidator] = []
        for gap in gaps:
            if gap.vuln_type in seen_types:
                continue
            seen_types.add(gap.vuln_type)
            code = PYTHON_VALIDATORS.get(gap.vuln_type, "# No template available")
            validators.append(GeneratedValidator(
                file=gap.file,
                endpoint=f"{gap.file}:{gap.line}",
                validation_code=code,
                vuln_types_covered=[gap.vuln_type],
            ))
        return validators


def format_validation_report(report: InputValidatorReport) -> str:
    """Render a human-readable validation report."""
    lines = ["=== Input Validation Report ===", ""]
    lines.append(f"Endpoints scanned:     {report.endpoints_scanned}")
    lines.append(f"Validation gaps:       {report.gaps_found}")
    lines.append(f"Validators generated:  {report.validators_generated}")
    lines.append("")

    for gap in report.gaps:
        lines.append(f"  [{gap.vuln_type.upper()}] {gap.file}:{gap.line} - {gap.description}")

    if report.validators:
        lines.append("")
        lines.append("--- Generated Validators ---")
        for v in report.validators:
            lines.append(f"\n  # {', '.join(v.vuln_types_covered)}")
            lines.append(v.validation_code)

    lines.append("")
    lines.append(report.summary)
    return "\n".join(lines)
