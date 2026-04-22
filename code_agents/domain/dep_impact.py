"""Interactive Dependency Impact Scanner.

Scans a project for usage of a specific package, detects breaking changes
between current and target versions, finds deprecated usages, and generates
migration patches.

Usage:
    scanner = DependencyImpactScanner(cwd="/path/to/repo", package="requests", target_version="3.0.0")
    report = scanner.scan()
    print(format_impact_report(report))
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.domain.dep_impact")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PackageUsage:
    file: str
    line: int
    import_statement: str
    symbols_used: list[str]


@dataclass
class BreakingChange:
    version: str
    description: str
    affected_symbols: list[str]
    migration_hint: str = ""


@dataclass
class DeprecatedUsage:
    symbol: str
    file: str
    line: int
    replacement: str = ""
    deprecated_since: str = ""


@dataclass
class MigrationPatch:
    file: str
    original: str
    patched: str
    description: str


@dataclass
class DepImpactReport:
    package: str
    current_version: str
    target_version: str
    language: str
    usages: list[PackageUsage]
    breaking_changes: list[BreakingChange]
    deprecated_usages: list[DeprecatedUsage]
    patches: list[MigrationPatch]
    affected_files: list[str]
    risk_level: str  # "low", "medium", "high", "critical"


# ---------------------------------------------------------------------------
# Known deprecation / breaking-change databases (heuristic)
# ---------------------------------------------------------------------------

_PYTHON_KNOWN_DEPRECATIONS: dict[str, list[dict[str, str]]] = {
    "requests": [
        {"symbol": "requests.packages", "replacement": "urllib3 directly", "since": "2.0"},
        {"symbol": "requests.utils.get_environ_proxies", "replacement": "urllib.request.getproxies", "since": "2.28"},
    ],
    "flask": [
        {"symbol": "flask.ext", "replacement": "flask_<extension>", "since": "0.11"},
        {"symbol": "Flask.before_first_request", "replacement": "app startup hooks", "since": "2.3"},
    ],
    "django": [
        {"symbol": "django.utils.encoding.force_text", "replacement": "force_str", "since": "4.0"},
        {"symbol": "django.conf.urls.url", "replacement": "django.urls.re_path", "since": "4.0"},
    ],
    "urllib3": [
        {"symbol": "urllib3.contrib.pyopenssl", "replacement": "built-in SSL", "since": "2.0"},
    ],
    "pytest": [
        {"symbol": "pytest.yield_fixture", "replacement": "pytest.fixture", "since": "4.0"},
    ],
    "sqlalchemy": [
        {"symbol": "sqlalchemy.orm.mapper", "replacement": "registry.map_imperatively", "since": "1.4"},
    ],
}

_NODE_KNOWN_DEPRECATIONS: dict[str, list[dict[str, str]]] = {
    "express": [
        {"symbol": "res.sendfile", "replacement": "res.sendFile", "since": "4.8"},
        {"symbol": "app.del", "replacement": "app.delete", "since": "5.0"},
    ],
    "lodash": [
        {"symbol": "_.pluck", "replacement": "_.map with property shorthand", "since": "4.0"},
    ],
    "webpack": [
        {"symbol": "module.loaders", "replacement": "module.rules", "since": "2.0"},
    ],
}

# ---------------------------------------------------------------------------
# Import patterns
# ---------------------------------------------------------------------------

_PYTHON_IMPORT_PATTERNS = [
    # import package
    re.compile(r"^\s*import\s+(\w[\w.]*)"),
    # from package import ...
    re.compile(r"^\s*from\s+(\w[\w.]*)\s+import\s+(.+)"),
]

_NODE_IMPORT_PATTERNS = [
    # const x = require('package')
    re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    # import ... from 'package'
    re.compile(r"""import\s+.+\s+from\s+['"]([^'"]+)['"]"""),
    # import 'package'
    re.compile(r"""import\s+['"]([^'"]+)['"]"""),
]

_JAVA_IMPORT_PATTERNS = [
    re.compile(r"^\s*import\s+([\w.]+);"),
]

_GO_IMPORT_PATTERNS = [
    re.compile(r'"([\w./\-]+)"'),
]

# File extensions by language
_LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "node": [".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"],
    "java": [".java"],
    "go": [".go"],
}

# Dirs to skip
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "env", ".tox", ".mypy_cache", ".pytest_cache", "dist",
    "build", ".eggs", "target", "vendor", ".gradle",
}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class DependencyImpactScanner:
    """Scan a project for dependency upgrade impact."""

    def __init__(
        self,
        cwd: str,
        package: str,
        target_version: str,
        dry_run: bool = True,
    ) -> None:
        self.cwd = os.path.abspath(cwd)
        self.package = package
        self.target_version = target_version
        self.dry_run = dry_run
        self.language = ""
        self.current_version = ""
        logger.info(
            "DependencyImpactScanner init: pkg=%s target=%s cwd=%s",
            package, target_version, cwd,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> DepImpactReport:
        """Run the full impact scan and return a report."""
        self.language = self._detect_language()
        logger.info("Detected language: %s", self.language)

        self.current_version = self._find_current_version()
        logger.info("Current version of %s: %s", self.package, self.current_version)

        usages = self._find_usages()
        logger.info("Found %d usages of %s", len(usages), self.package)

        registry_info = self._fetch_registry_info()

        breaking = self._detect_breaking_changes(registry_info, usages)
        deprecated = self._find_deprecated_usages(usages)
        patches = self._generate_patches(breaking, deprecated)

        affected_files = sorted(set(u.file for u in usages))
        risk = self._calculate_risk(usages, breaking, deprecated)

        report = DepImpactReport(
            package=self.package,
            current_version=self.current_version,
            target_version=self.target_version,
            language=self.language,
            usages=usages,
            breaking_changes=breaking,
            deprecated_usages=deprecated,
            patches=patches,
            affected_files=affected_files,
            risk_level=risk,
        )
        logger.info("Scan complete: risk=%s files=%d breaking=%d", risk, len(affected_files), len(breaking))
        return report

    def apply_patches(self) -> int:
        """Apply generated migration patches. Returns number of files patched."""
        report = self.scan()
        if not report.patches:
            logger.info("No patches to apply.")
            return 0

        applied = 0
        for patch in report.patches:
            fpath = os.path.join(self.cwd, patch.file)
            if not os.path.isfile(fpath):
                logger.warning("Patch target not found: %s", fpath)
                continue

            try:
                content = Path(fpath).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Cannot read %s: %s", fpath, exc)
                continue

            if patch.original in content:
                new_content = content.replace(patch.original, patch.patched, 1)
                if not self.dry_run:
                    Path(fpath).write_text(new_content, encoding="utf-8")
                    logger.info("Patched: %s — %s", patch.file, patch.description)
                else:
                    logger.info("Dry-run patch: %s — %s", patch.file, patch.description)
                applied += 1

        return applied

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def _detect_language(self) -> str:
        """Detect primary language using project_scanner if available, else heuristics."""
        try:
            from code_agents.analysis.project_scanner import scan_project
            info = scan_project(self.cwd)
            if info.language:
                lang = info.language.lower()
                if lang in ("python", "javascript", "typescript", "node"):
                    return "python" if lang == "python" else "node"
                if lang == "java":
                    return "java"
                if lang in ("go", "golang"):
                    return "go"
        except Exception:
            logger.debug("project_scanner unavailable, using heuristic")

        root = Path(self.cwd)
        if (root / "pyproject.toml").exists() or (root / "setup.py").exists() or (root / "requirements.txt").exists():
            return "python"
        if (root / "package.json").exists():
            return "node"
        if (root / "pom.xml").exists() or (root / "build.gradle").exists():
            return "java"
        if (root / "go.mod").exists():
            return "go"
        return "python"

    # ------------------------------------------------------------------
    # Version parsing
    # ------------------------------------------------------------------

    def _find_current_version(self) -> str:
        """Find the current installed version of the package."""
        root = Path(self.cwd)

        if self.language == "python":
            return self._parse_python_version(root)
        elif self.language == "node":
            return self._parse_node_version(root)
        elif self.language == "java":
            return self._parse_java_version(root)
        elif self.language == "go":
            return self._parse_go_version(root)
        return "unknown"

    def _parse_python_version(self, root: Path) -> str:
        """Parse version from pyproject.toml, setup.py, or requirements.txt."""
        # pyproject.toml
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            try:
                text = pyproject.read_text(encoding="utf-8")
                # Match: package = "^1.2.3" or package = ">=1.2.3" or package = "1.2.3"
                patterns = [
                    rf'{re.escape(self.package)}\s*=\s*"[\^~>=<]*(\d+[\d.]*[^"]*)"',
                    rf'{re.escape(self.package)}\s*=\s*\{{\s*version\s*=\s*"[\^~>=<]*(\d+[\d.]*[^"]*)"',
                ]
                for pat in patterns:
                    m = re.search(pat, text)
                    if m:
                        return m.group(1).strip()
            except (OSError, UnicodeDecodeError):
                pass

        # requirements.txt
        reqs = root / "requirements.txt"
        if reqs.exists():
            try:
                for line in reqs.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.lower().startswith(self.package.lower()):
                        m = re.search(r"[=><]+\s*(\d+[\d.]*\S*)", line)
                        if m:
                            return m.group(1)
            except (OSError, UnicodeDecodeError):
                pass

        # pip show fallback
        try:
            result = subprocess.run(
                ["pip", "show", self.package],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass

        return "unknown"

    def _parse_node_version(self, root: Path) -> str:
        """Parse version from package.json."""
        pkg_json = root / "package.json"
        if not pkg_json.exists():
            return "unknown"
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                deps = data.get(section, {})
                if self.package in deps:
                    ver = deps[self.package]
                    # Strip range operators
                    return re.sub(r"^[\^~>=<\s]+", "", ver)
            return "unknown"
        except (OSError, json.JSONDecodeError):
            return "unknown"

    def _parse_java_version(self, root: Path) -> str:
        """Parse version from pom.xml."""
        pom = root / "pom.xml"
        if not pom.exists():
            return "unknown"
        try:
            text = pom.read_text(encoding="utf-8")
            # Look for <artifactId>package</artifactId> followed by <version>
            pattern = (
                rf"<artifactId>\s*{re.escape(self.package)}\s*</artifactId>"
                r"\s*<version>\s*([^<]+?)\s*</version>"
            )
            m = re.search(pattern, text, re.DOTALL)
            if m:
                return m.group(1).strip()
        except (OSError, UnicodeDecodeError):
            pass
        return "unknown"

    def _parse_go_version(self, root: Path) -> str:
        """Parse version from go.mod."""
        gomod = root / "go.mod"
        if not gomod.exists():
            return "unknown"
        try:
            text = gomod.read_text(encoding="utf-8")
            # e.g. github.com/gin-gonic/gin v1.9.1
            for line in text.splitlines():
                if self.package in line:
                    m = re.search(r"v?([\d]+\.[\d]+\.[\d]+\S*)", line)
                    if m:
                        return m.group(1)
        except (OSError, UnicodeDecodeError):
            pass
        return "unknown"

    # ------------------------------------------------------------------
    # Usage detection
    # ------------------------------------------------------------------

    def _find_usages(self) -> list[PackageUsage]:
        """Grep for import statements of the package across the project."""
        usages: list[PackageUsage] = []
        extensions = _LANGUAGE_EXTENSIONS.get(self.language, [".py"])

        for dirpath, dirnames, filenames in os.walk(self.cwd):
            # Prune skip dirs
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

            for fname in filenames:
                if not any(fname.endswith(ext) for ext in extensions):
                    continue
                fpath = os.path.join(dirpath, fname)
                rel = os.path.relpath(fpath, self.cwd)
                try:
                    lines = Path(fpath).read_text(encoding="utf-8").splitlines()
                except (OSError, UnicodeDecodeError):
                    continue

                for lineno, line_text in enumerate(lines, 1):
                    usage = self._match_import(line_text, lineno, rel)
                    if usage:
                        usages.append(usage)

        return usages

    def _match_import(self, line: str, lineno: int, relpath: str) -> PackageUsage | None:
        """Check if a line contains an import of self.package."""
        pkg = self.package

        if self.language == "python":
            for pat in _PYTHON_IMPORT_PATTERNS:
                m = pat.match(line)
                if not m:
                    continue
                module = m.group(1)
                # Check if the import references our package
                if module == pkg or module.startswith(pkg + "."):
                    symbols = []
                    if m.lastindex and m.lastindex >= 2:
                        symbols = [s.strip().split(" as ")[0].strip() for s in m.group(2).split(",")]
                    return PackageUsage(
                        file=relpath, line=lineno,
                        import_statement=line.strip(), symbols_used=symbols,
                    )

        elif self.language == "node":
            for pat in _NODE_IMPORT_PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                mod_name = m.group(1)
                if mod_name == pkg or mod_name.startswith(pkg + "/"):
                    symbols: list[str] = []
                    # Extract destructured imports
                    brace_m = re.search(r"\{\s*(.+?)\s*\}", line)
                    if brace_m:
                        symbols = [s.strip().split(" as ")[0].strip() for s in brace_m.group(1).split(",")]
                    return PackageUsage(
                        file=relpath, line=lineno,
                        import_statement=line.strip(), symbols_used=symbols,
                    )

        elif self.language == "java":
            for pat in _JAVA_IMPORT_PATTERNS:
                m = pat.match(line)
                if m:
                    imp = m.group(1)
                    # Java packages use dots — check if our artifactId appears
                    if pkg.replace("-", ".") in imp or pkg in imp:
                        symbol = imp.rsplit(".", 1)[-1]
                        return PackageUsage(
                            file=relpath, line=lineno,
                            import_statement=line.strip(),
                            symbols_used=[symbol] if symbol != "*" else [],
                        )

        elif self.language == "go":
            for pat in _GO_IMPORT_PATTERNS:
                m = pat.search(line)
                if m:
                    mod = m.group(1)
                    if pkg in mod:
                        return PackageUsage(
                            file=relpath, line=lineno,
                            import_statement=line.strip(), symbols_used=[],
                        )

        return None

    # ------------------------------------------------------------------
    # Registry fetch
    # ------------------------------------------------------------------

    def _fetch_registry_info(self) -> dict[str, Any]:
        """Fetch package info from the upstream registry (PyPI / npm)."""
        if self.language == "python":
            return self._fetch_pypi()
        elif self.language == "node":
            return self._fetch_npm()
        return {}

    def _fetch_pypi(self) -> dict[str, Any]:
        """Fetch package metadata from PyPI JSON API."""
        import urllib.request

        url = f"https://pypi.org/pypi/{self.package}/json"
        logger.info("Fetching PyPI info: %s", url)
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            releases = sorted(data.get("releases", {}).keys())
            info = data.get("info", {})
            return {
                "name": info.get("name", self.package),
                "latest": info.get("version", ""),
                "summary": info.get("summary", ""),
                "releases": releases,
                "info": info,
            }
        except Exception as exc:
            logger.warning("PyPI fetch failed for %s: %s", self.package, exc)
            return {}

    def _fetch_npm(self) -> dict[str, Any]:
        """Fetch package metadata from npm registry."""
        import urllib.request

        url = f"https://registry.npmjs.org/{self.package}"
        logger.info("Fetching npm info: %s", url)
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            versions = sorted(data.get("versions", {}).keys())
            dist_tags = data.get("dist-tags", {})
            return {
                "name": data.get("name", self.package),
                "latest": dist_tags.get("latest", ""),
                "description": data.get("description", ""),
                "releases": versions,
            }
        except Exception as exc:
            logger.warning("npm fetch failed for %s: %s", self.package, exc)
            return {}

    # ------------------------------------------------------------------
    # Breaking change detection
    # ------------------------------------------------------------------

    def _detect_breaking_changes(
        self,
        registry_info: dict[str, Any],
        usages: list[PackageUsage],
    ) -> list[BreakingChange]:
        """Detect potential breaking changes between current and target version."""
        breaking: list[BreakingChange] = []

        # Heuristic: major version bump is likely breaking
        cur_major = self._major_version(self.current_version)
        tgt_major = self._major_version(self.target_version)

        if cur_major is not None and tgt_major is not None and tgt_major > cur_major:
            # Collect all used symbols
            all_symbols = []
            for u in usages:
                all_symbols.extend(u.symbols_used)
            all_symbols = list(set(all_symbols)) or [self.package]

            breaking.append(BreakingChange(
                version=self.target_version,
                description=f"Major version bump ({cur_major}.x -> {tgt_major}.x) — API surface may change",
                affected_symbols=all_symbols[:20],
                migration_hint=f"Review the {self.package} {self.target_version} changelog for breaking changes",
            ))

        # Check known deprecation database for items deprecated *before* target
        known = self._get_known_deprecations()
        for entry in known:
            dep_since = entry.get("since", "")
            symbol = entry.get("symbol", "")
            # Check if any usage references this symbol
            for u in usages:
                if symbol in u.import_statement or any(symbol.endswith(s) for s in u.symbols_used):
                    breaking.append(BreakingChange(
                        version=dep_since,
                        description=f"'{symbol}' deprecated since {dep_since}",
                        affected_symbols=[symbol],
                        migration_hint=f"Replace with: {entry.get('replacement', 'see docs')}",
                    ))
                    break

        return breaking

    def _find_deprecated_usages(self, usages: list[PackageUsage]) -> list[DeprecatedUsage]:
        """Find usages of symbols known to be deprecated."""
        deprecated: list[DeprecatedUsage] = []
        known = self._get_known_deprecations()

        for entry in known:
            symbol = entry.get("symbol", "")
            replacement = entry.get("replacement", "")
            since = entry.get("since", "")

            for u in usages:
                if symbol in u.import_statement or any(symbol.endswith(s) for s in u.symbols_used):
                    deprecated.append(DeprecatedUsage(
                        symbol=symbol,
                        file=u.file,
                        line=u.line,
                        replacement=replacement,
                        deprecated_since=since,
                    ))

        return deprecated

    def _get_known_deprecations(self) -> list[dict[str, str]]:
        """Get known deprecations for the current package."""
        if self.language == "python":
            return _PYTHON_KNOWN_DEPRECATIONS.get(self.package, [])
        elif self.language == "node":
            return _NODE_KNOWN_DEPRECATIONS.get(self.package, [])
        return []

    # ------------------------------------------------------------------
    # Patch generation
    # ------------------------------------------------------------------

    def _generate_patches(
        self,
        breaking: list[BreakingChange],
        deprecated: list[DeprecatedUsage],
    ) -> list[MigrationPatch]:
        """Generate migration patches based on breaking changes and deprecations."""
        patches: list[MigrationPatch] = []

        for dep in deprecated:
            if not dep.replacement:
                continue
            # Read the source file to build a patch
            fpath = os.path.join(self.cwd, dep.file)
            try:
                lines = Path(fpath).read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue

            if dep.line < 1 or dep.line > len(lines):
                continue

            original_line = lines[dep.line - 1]
            # Simple symbol replacement
            short_symbol = dep.symbol.rsplit(".", 1)[-1]
            if short_symbol in original_line:
                patched_line = original_line.replace(short_symbol, dep.replacement.rsplit(".", 1)[-1], 1)
                if patched_line != original_line:
                    patches.append(MigrationPatch(
                        file=dep.file,
                        original=original_line,
                        patched=patched_line,
                        description=f"Replace deprecated '{dep.symbol}' with '{dep.replacement}'",
                    ))

        return patches

    # ------------------------------------------------------------------
    # Risk calculation
    # ------------------------------------------------------------------

    def _calculate_risk(
        self,
        usages: list[PackageUsage],
        breaking: list[BreakingChange],
        deprecated: list[DeprecatedUsage],
    ) -> str:
        """Calculate risk level: low, medium, high, critical."""
        score = 0
        file_count = len(set(u.file for u in usages))

        # File spread
        if file_count > 20:
            score += 3
        elif file_count > 10:
            score += 2
        elif file_count > 3:
            score += 1

        # Breaking changes
        score += len(breaking) * 2

        # Deprecated usages
        score += len(deprecated)

        # Major version jump
        cur = self._major_version(self.current_version)
        tgt = self._major_version(self.target_version)
        if cur is not None and tgt is not None:
            diff = tgt - cur
            if diff >= 2:
                score += 3
            elif diff >= 1:
                score += 1

        if score >= 8:
            return "critical"
        elif score >= 5:
            return "high"
        elif score >= 2:
            return "medium"
        return "low"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _major_version(ver: str) -> int | None:
        """Extract major version number."""
        m = re.match(r"(\d+)", ver)
        if m:
            return int(m.group(1))
        return None


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_impact_report(report: DepImpactReport) -> str:
    """Format a DepImpactReport for rich terminal output."""
    lines: list[str] = []

    risk_colors = {
        "low": "\033[32m",       # green
        "medium": "\033[33m",    # yellow
        "high": "\033[91m",      # red
        "critical": "\033[1;91m",  # bold red
    }
    reset = "\033[0m"
    bold = "\033[1m"
    dim_c = "\033[2m"
    cyan_c = "\033[36m"

    risk_color = risk_colors.get(report.risk_level, "")

    lines.append("")
    lines.append(f"  {bold}Dependency Impact Report{reset}")
    lines.append(f"  {dim_c}{'=' * 50}{reset}")
    lines.append(f"  Package:  {cyan_c}{report.package}{reset}")
    lines.append(f"  Current:  {report.current_version}")
    lines.append(f"  Target:   {report.target_version}")
    lines.append(f"  Language: {report.language}")
    lines.append(f"  Risk:     {risk_color}{report.risk_level.upper()}{reset}")
    lines.append("")

    # --- Usages ---
    lines.append(f"  {bold}Usages ({len(report.usages)} imports across {len(report.affected_files)} files){reset}")
    if report.affected_files:
        for f in report.affected_files[:15]:
            count = sum(1 for u in report.usages if u.file == f)
            lines.append(f"    {f} ({count} import{'s' if count > 1 else ''})")
        if len(report.affected_files) > 15:
            lines.append(f"    {dim_c}... and {len(report.affected_files) - 15} more files{reset}")
    else:
        lines.append(f"    {dim_c}No usages found{reset}")
    lines.append("")

    # --- Breaking Changes ---
    lines.append(f"  {bold}Breaking Changes ({len(report.breaking_changes)}){reset}")
    if report.breaking_changes:
        for bc in report.breaking_changes:
            lines.append(f"    \033[91m!\033[0m {bc.description}")
            if bc.affected_symbols:
                syms = ", ".join(bc.affected_symbols[:5])
                extra = f" +{len(bc.affected_symbols) - 5} more" if len(bc.affected_symbols) > 5 else ""
                lines.append(f"      Symbols: {syms}{extra}")
            if bc.migration_hint:
                lines.append(f"      {dim_c}Hint: {bc.migration_hint}{reset}")
    else:
        lines.append(f"    {dim_c}None detected{reset}")
    lines.append("")

    # --- Deprecated Usages ---
    lines.append(f"  {bold}Deprecated Usages ({len(report.deprecated_usages)}){reset}")
    if report.deprecated_usages:
        for du in report.deprecated_usages:
            lines.append(f"    \033[33m~\033[0m {du.symbol} @ {du.file}:{du.line}")
            if du.replacement:
                lines.append(f"      Replace with: {du.replacement}")
            if du.deprecated_since:
                lines.append(f"      {dim_c}Deprecated since: {du.deprecated_since}{reset}")
    else:
        lines.append(f"    {dim_c}None detected{reset}")
    lines.append("")

    # --- Migration Patches ---
    lines.append(f"  {bold}Migration Patches ({len(report.patches)}){reset}")
    if report.patches:
        for patch in report.patches:
            lines.append(f"    {cyan_c}{patch.file}{reset}: {patch.description}")
            lines.append(f"      {dim_c}- {patch.original.strip()}{reset}")
            lines.append(f"      \033[32m+ {patch.patched.strip()}{reset}")
    else:
        lines.append(f"    {dim_c}No auto-patches generated{reset}")
    lines.append("")

    return "\n".join(lines)
