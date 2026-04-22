"""Impact Analysis — shows what's affected when a file is modified.

Scans a repository for dependents, related tests, and affected endpoints
for a given file. Uses grep-based detection (fast, no AST parsing).

Usage:
    from code_agents.analysis.impact_analysis import ImpactAnalyzer
    analyzer = ImpactAnalyzer("/path/to/repo")
    report = analyzer.analyze("src/services/PaymentService.java")
    print(format_impact_report(report))

Lazy-loaded: no heavy imports at module level.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.analysis.impact_analysis")

# File extensions by language family
_PYTHON_EXTS = {".py"}
_JAVA_EXTS = {".java", ".kt", ".scala"}
_JS_TS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs"}
_GO_EXTS = {".go"}
_ALL_CODE_EXTS = _PYTHON_EXTS | _JAVA_EXTS | _JS_TS_EXTS | _GO_EXTS

# Directories to skip during scanning
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
    "target", ".gradle", ".idea", ".vscode", ".eggs", "*.egg-info",
    ".code-agents", "logs",
}

# Keywords that indicate critical/sensitive code
_CRITICAL_KEYWORDS = {
    "payment", "pay", "billing", "charge", "refund", "transaction",
    "auth", "authentication", "authorization", "login", "password",
    "token", "secret", "credential", "encrypt", "decrypt", "security",
    "key", "certificate", "oauth", "jwt", "session",
}

# Endpoint annotation/decorator patterns by language
_ENDPOINT_PATTERNS = [
    # Java Spring
    re.compile(r'@(?:Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']'),
    # Python Flask/FastAPI
    re.compile(r'@\w+\.(?:get|post|put|delete|patch|route|api_route)\s*\(\s*["\']([^"\']+)["\']'),
    # Express.js
    re.compile(r'(?:router|app)\.(?:get|post|put|delete|patch|all)\s*\(\s*["\']([^"\']+)["\']'),
    # Go net/http or gin
    re.compile(r'\.(?:GET|POST|PUT|DELETE|PATCH|Handle|HandleFunc)\s*\(\s*["\']([^"\']+)["\']'),
]

# HTTP method patterns for extracting the method alongside the route
_METHOD_ENDPOINT_PATTERNS = [
    # Java Spring @GetMapping etc.
    (re.compile(r'@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']'), None),
    # Java @RequestMapping with method
    (re.compile(r'@RequestMapping\s*\(.*?method\s*=\s*RequestMethod\.(\w+).*?value\s*=\s*["\']([^"\']+)["\']'), None),
    # Python decorators
    (re.compile(r'@\w+\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'), None),
    # Express.js
    (re.compile(r'(?:router|app)\.(get|post|put|delete|patch|all)\s*\(\s*["\']([^"\']+)["\']'), None),
    # Go
    (re.compile(r'\.(GET|POST|PUT|DELETE|PATCH)\s*\(\s*["\']([^"\']+)["\']'), None),
]


@dataclass
class ImpactReport:
    """Result of impact analysis for a single file."""

    file: str
    dependent_files: list[str] = field(default_factory=list)
    affected_tests: list[str] = field(default_factory=list)
    missing_tests: list[str] = field(default_factory=list)
    affected_endpoints: list[str] = field(default_factory=list)
    risk_level: str = "low"  # low, medium, high, critical
    risk_reasons: list[str] = field(default_factory=list)


class ImpactAnalyzer:
    """Analyze impact of modifying a file in a repository."""

    def __init__(self, cwd: str) -> None:
        self.cwd = Path(cwd)
        self._file_index: Optional[list[Path]] = None

    def _index_files(self) -> list[Path]:
        """Build index of all source files in the repo."""
        if self._file_index is not None:
            return self._file_index
        files: list[Path] = []
        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.endswith(".egg-info")]
            for fname in fnames:
                fpath = Path(root) / fname
                if fpath.suffix.lower() in _ALL_CODE_EXTS:
                    files.append(fpath)
        self._file_index = files
        return files

    def _resolve_path(self, filepath: str) -> Path:
        """Resolve a filepath relative to cwd."""
        p = Path(filepath)
        if not p.is_absolute():
            p = self.cwd / p
        return p

    def _module_name(self, filepath: str) -> str:
        """Extract the module/class name from a filepath for grep matching."""
        p = Path(filepath)
        return p.stem  # e.g. PaymentService from PaymentService.java

    def _import_patterns(self, filepath: str) -> list[re.Pattern]:
        """Build regex patterns to find files that import/use this module."""
        stem = self._module_name(filepath)
        ext = Path(filepath).suffix.lower()
        patterns = []

        if ext in _PYTHON_EXTS:
            # Python: from x.y.stem import ..., import x.y.stem
            # Match the module name as the last segment of an import path
            patterns.append(re.compile(
                rf'(?:from\s+[\w.]*{re.escape(stem)}\s+import|import\s+[\w.]*{re.escape(stem)})\b'
            ))
        elif ext in _JAVA_EXTS:
            # Java: import com.example.PaymentService;
            patterns.append(re.compile(
                rf'import\s+[\w.]*\.{re.escape(stem)}\s*;'
            ))
            # Also match class references: new PaymentService, @Autowired PaymentService
            patterns.append(re.compile(
                rf'\b{re.escape(stem)}\b'
            ))
        elif ext in _JS_TS_EXTS:
            # JS/TS: import ... from './PaymentService' or require('./PaymentService')
            patterns.append(re.compile(
                rf'''(?:from\s+['"].*{re.escape(stem)}['"]|require\s*\(\s*['"].*{re.escape(stem)}['"])'''
            ))
        elif ext in _GO_EXTS:
            # Go: package references are by package name, look for the stem
            patterns.append(re.compile(
                rf'\b{re.escape(stem)}\b'
            ))

        return patterns

    def find_dependents(self, filepath: str) -> list[str]:
        """Find files that import or reference the given file."""
        files = self._index_files()
        patterns = self._import_patterns(filepath)
        if not patterns:
            return []

        resolved = self._resolve_path(filepath)
        dependents: list[str] = []

        for fpath in files:
            # Don't match the file against itself
            if fpath.resolve() == resolved.resolve():
                continue
            # Only search files of the same language family for imports
            try:
                content = fpath.read_text(errors="replace")
            except (OSError, IOError):
                continue
            for pat in patterns:
                if pat.search(content):
                    rel = str(fpath.relative_to(self.cwd))
                    if rel not in dependents:
                        dependents.append(rel)
                    break

        return sorted(dependents)

    def find_tests(self, filepath: str) -> tuple[list[str], list[str]]:
        """Find existing test files and identify missing test files.

        Returns:
            (existing_tests, missing_tests)
        """
        files = self._index_files()
        stem = self._module_name(filepath)
        ext = Path(filepath).suffix.lower()

        # Build expected test file name patterns
        test_patterns: list[re.Pattern] = []
        if ext in _PYTHON_EXTS:
            # test_payment_service.py or test_PaymentService.py
            snake = _camel_to_snake(stem)
            test_patterns.append(re.compile(rf'^test_{re.escape(snake)}\.py$', re.IGNORECASE))
            test_patterns.append(re.compile(rf'^test_{re.escape(stem)}\.py$', re.IGNORECASE))
            test_patterns.append(re.compile(rf'^{re.escape(stem)}_test\.py$', re.IGNORECASE))
        elif ext in _JAVA_EXTS:
            # PaymentServiceTest.java or PaymentServiceSpec.java
            test_patterns.append(re.compile(rf'^{re.escape(stem)}(?:Test|Tests|Spec|IT)\.java$'))
        elif ext in _JS_TS_EXTS:
            # PaymentService.test.ts or PaymentService.spec.ts
            base_stem = stem.replace(".test", "").replace(".spec", "")
            test_patterns.append(re.compile(
                rf'^{re.escape(base_stem)}\.(?:test|spec)\.(?:js|jsx|ts|tsx)$'
            ))
            test_patterns.append(re.compile(
                rf'^{re.escape(base_stem)}[-_]test\.(?:js|jsx|ts|tsx)$'
            ))
        elif ext in _GO_EXTS:
            test_patterns.append(re.compile(rf'^{re.escape(stem)}_test\.go$'))

        existing: list[str] = []
        for fpath in files:
            fname = fpath.name
            for tp in test_patterns:
                if tp.search(fname):
                    rel = str(fpath.relative_to(self.cwd))
                    if rel not in existing:
                        existing.append(rel)
                    break

        # Also find tests that reference this module (grep-based)
        import_pats = self._import_patterns(filepath)
        for fpath in files:
            fname = fpath.name.lower()
            is_test = (
                fname.startswith("test_") or fname.endswith("_test.py")
                or "test" in fname.lower() and fpath.suffix.lower() in _ALL_CODE_EXTS
            )
            if not is_test:
                continue
            rel = str(fpath.relative_to(self.cwd))
            if rel in existing:
                continue
            try:
                content = fpath.read_text(errors="replace")
            except (OSError, IOError):
                continue
            for pat in import_pats:
                if pat.search(content):
                    existing.append(rel)
                    break

        # Determine expected test names that are missing
        missing: list[str] = []
        if not existing and test_patterns:
            if ext in _PYTHON_EXTS:
                snake = _camel_to_snake(stem)
                missing.append(f"test_{snake}.py")
            elif ext in _JAVA_EXTS:
                missing.append(f"{stem}Test.java")
            elif ext in _JS_TS_EXTS:
                base_stem = stem.replace(".test", "").replace(".spec", "")
                missing.append(f"{base_stem}.test{ext}")
            elif ext in _GO_EXTS:
                missing.append(f"{stem}_test.go")

        return sorted(existing), missing

    def find_endpoints(self, filepath: str) -> list[str]:
        """Find API endpoints defined in or affected by this file."""
        resolved = self._resolve_path(filepath)
        endpoints: list[str] = []

        # First check the file itself for endpoint definitions
        try:
            content = resolved.read_text(errors="replace")
        except (OSError, IOError):
            content = ""

        endpoints.extend(self._extract_endpoints(content))

        # Then check dependents that might be controllers/routers
        dependents = self.find_dependents(filepath)
        for dep in dependents:
            dep_path = self.cwd / dep
            dep_name = dep.lower()
            # Only scan files that look like controllers/routers/handlers
            if any(kw in dep_name for kw in ("controller", "router", "handler", "view", "endpoint", "route", "api")):
                try:
                    dep_content = dep_path.read_text(errors="replace")
                except (OSError, IOError):
                    continue
                endpoints.extend(self._extract_endpoints(dep_content))

        return sorted(set(endpoints))

    def _extract_endpoints(self, content: str) -> list[str]:
        """Extract endpoint definitions from file content."""
        endpoints: list[str] = []
        for pat, _ in _METHOD_ENDPOINT_PATTERNS:
            for match in pat.finditer(content):
                groups = match.groups()
                if len(groups) >= 2:
                    method = groups[0].upper()
                    route = groups[1]
                    endpoints.append(f"{method} {route}")
        # Fallback: simple endpoint patterns (without method)
        if not endpoints:
            for pat in _ENDPOINT_PATTERNS:
                for match in pat.finditer(content):
                    route = match.group(1)
                    endpoints.append(route)
        return endpoints

    def assess_risk(
        self,
        filepath: str,
        dependents: list[str],
        tests: list[str],
        missing_tests: list[str],
        endpoints: list[str],
    ) -> tuple[str, list[str]]:
        """Assess risk level of modifying a file.

        Returns:
            (risk_level, reasons)
        """
        reasons: list[str] = []
        score = 0

        # Check for critical keywords in the filename or path
        lower_path = filepath.lower()
        for kw in _CRITICAL_KEYWORDS:
            if kw in lower_path:
                score += 3
                reasons.append(f"File path contains sensitive keyword: {kw}")
                break  # Only count once

        # Number of dependents
        dep_count = len(dependents)
        if dep_count > 10:
            score += 4
            reasons.append(f"{dep_count} dependent files (very high coupling)")
        elif dep_count > 5:
            score += 3
            reasons.append(f"{dep_count} dependent files (high coupling)")
        elif dep_count > 2:
            score += 1
            reasons.append(f"{dep_count} dependent files")

        # Missing tests
        if missing_tests:
            score += 2
            reasons.append(f"Missing test coverage: {', '.join(missing_tests)}")
        elif not tests:
            score += 1
            reasons.append("No related tests found")

        # Exposed endpoints
        ep_count = len(endpoints)
        if ep_count > 3:
            score += 2
            reasons.append(f"{ep_count} API endpoints affected")
        elif ep_count > 0:
            score += 1
            reasons.append(f"{ep_count} API endpoint(s) affected")

        # Determine level
        if score >= 5:
            level = "critical"
        elif score >= 3:
            level = "high"
        elif score >= 2:
            level = "medium"
        else:
            level = "low"

        return level, reasons

    def analyze(self, filepath: str) -> ImpactReport:
        """Analyze the full impact of modifying a file."""
        logger.info("Analyzing impact of: %s", filepath)
        dependents = self.find_dependents(filepath)
        existing_tests, missing_tests = self.find_tests(filepath)
        endpoints = self.find_endpoints(filepath)
        risk_level, risk_reasons = self.assess_risk(
            filepath, dependents, existing_tests, missing_tests, endpoints
        )

        report = ImpactReport(
            file=filepath,
            dependent_files=dependents,
            affected_tests=existing_tests,
            missing_tests=missing_tests,
            affected_endpoints=endpoints,
            risk_level=risk_level,
            risk_reasons=risk_reasons,
        )
        logger.info(
            "Impact analysis complete: %s — risk=%s, dependents=%d, tests=%d, endpoints=%d",
            filepath, risk_level, len(dependents), len(existing_tests), len(endpoints),
        )
        return report


def format_impact_report(report: ImpactReport) -> str:
    """Format an ImpactReport as a readable terminal string."""
    lines: list[str] = []
    display_name = Path(report.file).name
    header = f"Impact Analysis: {display_name}"
    lines.append(f"  {header}")
    lines.append(f"  {'=' * len(header)}")

    # Risk level with color hint
    risk_upper = report.risk_level.upper()
    lines.append(f"  Risk: {risk_upper}")
    if report.risk_reasons:
        for reason in report.risk_reasons:
            lines.append(f"    - {reason}")
    lines.append("")

    # Dependents
    dep_count = len(report.dependent_files)
    if dep_count > 0:
        lines.append(f"  Dependents ({dep_count} file{'s' if dep_count != 1 else ''}):")
        for dep in report.dependent_files:
            lines.append(f"    * {dep}")
    else:
        lines.append("  Dependents: none")
    lines.append("")

    # Tests
    test_count = len(report.affected_tests) + len(report.missing_tests)
    if test_count > 0:
        lines.append(f"  Tests ({test_count} file{'s' if test_count != 1 else ''}):")
        for t in report.affected_tests:
            lines.append(f"    + {t}")
        for t in report.missing_tests:
            lines.append(f"    x {t} (MISSING)")
    else:
        lines.append("  Tests: none found")
    lines.append("")

    # Endpoints
    ep_count = len(report.affected_endpoints)
    if ep_count > 0:
        lines.append(f"  Endpoints ({ep_count}):")
        for ep in report.affected_endpoints:
            lines.append(f"    {ep}")
    else:
        lines.append("  Endpoints: none")

    return "\n".join(lines)


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
