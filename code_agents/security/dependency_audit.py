"""Dependency Audit — check for known CVEs, license issues, outdated versions."""

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.security.dependency_audit")


# ---------------------------------------------------------------------------
# Built-in vulnerability database (no external API needed)
# ---------------------------------------------------------------------------

KNOWN_VULNS = {
    # Python
    "django": [{"below": "3.2.0", "cve": "CVE-2021-45115", "severity": "HIGH", "desc": "DoS via UserAgent header"}],
    "flask": [{"below": "2.0.0", "cve": "CVE-2023-30861", "severity": "HIGH", "desc": "Session cookie vulnerability"}],
    "requests": [{"below": "2.31.0", "cve": "CVE-2023-32681", "severity": "MEDIUM", "desc": "Proxy-Authorization header leak"}],
    "urllib3": [{"below": "2.0.7", "cve": "CVE-2023-45803", "severity": "MEDIUM", "desc": "Request body not stripped on redirect"}],
    "pillow": [{"below": "10.0.1", "cve": "CVE-2023-44271", "severity": "HIGH", "desc": "DoS via crafted image"}],
    "cryptography": [{"below": "41.0.0", "cve": "CVE-2023-38325", "severity": "HIGH", "desc": "NULL dereference"}],
    # Java
    "log4j-core": [{"below": "2.17.1", "cve": "CVE-2021-44228", "severity": "CRITICAL", "desc": "Log4Shell RCE"}],
    "spring-core": [{"below": "5.3.18", "cve": "CVE-2022-22965", "severity": "CRITICAL", "desc": "Spring4Shell RCE"}],
    "jackson-databind": [{"below": "2.14.0", "cve": "CVE-2022-42003", "severity": "HIGH", "desc": "Deserialization gadgets"}],
    "commons-text": [{"below": "1.10.0", "cve": "CVE-2022-42889", "severity": "CRITICAL", "desc": "Text4Shell RCE"}],
    "snakeyaml": [{"below": "2.0", "cve": "CVE-2022-1471", "severity": "CRITICAL", "desc": "Arbitrary code execution"}],
    # JavaScript
    "lodash": [{"below": "4.17.21", "cve": "CVE-2021-23337", "severity": "HIGH", "desc": "Command injection"}],
    "express": [{"below": "4.17.3", "cve": "CVE-2022-24999", "severity": "HIGH", "desc": "Prototype pollution via qs"}],
    "axios": [{"below": "1.6.0", "cve": "CVE-2023-45857", "severity": "MEDIUM", "desc": "SSRF via proxy"}],
    "jsonwebtoken": [{"below": "9.0.0", "cve": "CVE-2022-23529", "severity": "HIGH", "desc": "Secret key bypass"}],
    "minimist": [{"below": "1.2.6", "cve": "CVE-2021-44906", "severity": "CRITICAL", "desc": "Prototype pollution"}],
}

# License patterns considered problematic in commercial projects
GPL_LICENSES = {"GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Dependency:
    name: str
    version: str
    source: str  # file where it was found


@dataclass
class Vulnerability:
    name: str
    version: str
    cve: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    description: str
    fix_version: str  # "upgrade to >= X"


@dataclass
class LicenseWarning:
    name: str
    license: str
    reason: str


@dataclass
class OutdatedPackage:
    name: str
    current: str
    latest: str


@dataclass
class AuditReport:
    repo_path: str
    dependencies: list[Dependency] = field(default_factory=list)
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    license_warnings: list[LicenseWarning] = field(default_factory=list)
    outdated: list[OutdatedPackage] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------

def _parse_version(v: str) -> tuple:
    """Parse version string into comparable tuple.

    Uses packaging.version if available, else simple numeric split.
    """
    try:
        from packaging.version import Version
        return Version(v)
    except Exception:
        pass
    # Fallback: split on dots and convert to ints where possible
    parts = []
    for p in v.split("."):
        p = re.sub(r"[^0-9]", "", p)
        parts.append(int(p) if p else 0)
    return tuple(parts)


def version_less_than(current: str, threshold: str) -> bool:
    """Return True if current < threshold."""
    try:
        return _parse_version(current) < _parse_version(threshold)
    except Exception:
        # If comparison fails, assume not vulnerable
        return False


# ---------------------------------------------------------------------------
# Dependency Auditor
# ---------------------------------------------------------------------------

class DependencyAuditor:
    """Audit project dependencies for CVEs, licenses, and outdated versions."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.report = AuditReport(repo_path=cwd)
        logger.info("DependencyAuditor initialized for %s", cwd)

    # -- Scanning entry point -----------------------------------------------

    def scan_dependencies(self) -> list[Dependency]:
        """Parse all recognized dependency files and return list of deps."""
        path = Path(self.cwd)

        # requirements.txt (and variants)
        for req_file in path.glob("requirements*.txt"):
            self._parse_requirements_txt(req_file)

        # pyproject.toml
        pyproject = path / "pyproject.toml"
        if pyproject.exists():
            self._parse_pyproject_toml(pyproject)

        # package.json
        pkg_json = path / "package.json"
        if pkg_json.exists():
            self._parse_package_json(pkg_json)

        # pom.xml
        pom = path / "pom.xml"
        if pom.exists():
            self._parse_pom_xml(pom)

        # build.gradle
        gradle = path / "build.gradle"
        if gradle.exists():
            self._parse_build_gradle(gradle)

        # go.mod
        gomod = path / "go.mod"
        if gomod.exists():
            self._parse_go_mod(gomod)

        logger.info("Scanned %d dependencies", len(self.report.dependencies))
        return self.report.dependencies

    # -- Vulnerability check ------------------------------------------------

    def check_known_vulnerabilities(self) -> list[Vulnerability]:
        """Check scanned dependencies against built-in KNOWN_VULNS database."""
        for dep in self.report.dependencies:
            # Normalize name: underscores to hyphens, lowercase
            norm_name = dep.name.lower().replace("_", "-")
            vulns = KNOWN_VULNS.get(norm_name, [])
            for v in vulns:
                if version_less_than(dep.version, v["below"]):
                    self.report.vulnerabilities.append(Vulnerability(
                        name=dep.name,
                        version=dep.version,
                        cve=v["cve"],
                        severity=v["severity"],
                        description=v["desc"],
                        fix_version=v["below"],
                    ))
        logger.info("Found %d vulnerabilities", len(self.report.vulnerabilities))
        return self.report.vulnerabilities

    # -- License check ------------------------------------------------------

    def check_licenses(self) -> list[LicenseWarning]:
        """Detect GPL-family licenses from common patterns in dependency files."""
        path = Path(self.cwd)

        # Check node_modules for license fields in package.json files
        node_modules = path / "node_modules"
        if node_modules.is_dir():
            for pkg_json in node_modules.glob("*/package.json"):
                self._check_npm_license(pkg_json)

        # Check for LICENSE files in common locations
        for license_file in path.glob("**/LICENSE*"):
            # Skip deep nesting and common vendored dirs
            rel = license_file.relative_to(path)
            parts = rel.parts
            if any(d in parts for d in (".git", "__pycache__", "venv", ".venv")):
                continue
            if len(parts) > 3:
                continue
            self._check_license_file(license_file)

        logger.info("Found %d license warnings", len(self.report.license_warnings))
        return self.report.license_warnings

    # -- Outdated check -----------------------------------------------------

    def check_outdated(self) -> list[OutdatedPackage]:
        """Check for outdated packages using native package managers.

        Uses subprocess: pip list --outdated, npm outdated, mvn versions:display-dependency-updates.
        """
        path = Path(self.cwd)

        # Python (pip)
        if (path / "requirements.txt").exists() or (path / "pyproject.toml").exists():
            self._check_pip_outdated()

        # Node (npm)
        if (path / "package.json").exists():
            self._check_npm_outdated()

        logger.info("Found %d outdated packages", len(self.report.outdated))
        return self.report.outdated

    # -- Report formatter ---------------------------------------------------

    def format_report(self, vuln_only: bool = False, licenses_only: bool = False,
                      outdated_only: bool = False) -> str:
        """Format audit report for terminal display."""
        lines = []
        repo_name = Path(self.cwd).name

        lines.append("")
        lines.append(f"  Dependency Audit \u2014 {repo_name}")
        lines.append("  " + "\u2550" * (len(f"Dependency Audit \u2014 {repo_name}") + 2))
        lines.append("")
        lines.append(f"  Dependencies: {len(self.report.dependencies)} scanned")
        lines.append("")

        if not vuln_only and not licenses_only and not outdated_only:
            # Show everything
            vuln_only = licenses_only = outdated_only = True

        # -- Vulnerabilities --
        if vuln_only and self.report.vulnerabilities:
            by_sev = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}
            for v in self.report.vulnerabilities:
                by_sev.get(v.severity, by_sev["LOW"]).append(v)

            sev_icons = {
                "CRITICAL": "\U0001f534",  # red circle
                "HIGH": "\U0001f7e0",      # orange circle
                "MEDIUM": "\U0001f7e1",    # yellow circle
                "LOW": "\U0001f535",        # blue circle
            }

            for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                items = by_sev[sev]
                if not items:
                    continue
                icon = sev_icons[sev]
                lines.append(f"  {icon} {sev} ({len(items)}):")
                for v in items:
                    lines.append(f"    {v.name} {v.version} \u2014 {v.cve} ({v.description})")
                    lines.append(f"      Fix: upgrade to >= {v.fix_version}")
                lines.append("")

        # -- License warnings --
        if licenses_only and self.report.license_warnings:
            lines.append("  \u26a0 License Warnings:")
            for lw in self.report.license_warnings:
                lines.append(f"    {lw.license}: {lw.name} ({lw.reason})")
            lines.append("")

        # -- Outdated --
        if outdated_only and self.report.outdated:
            lines.append(f"  \U0001f4e6 Outdated ({len(self.report.outdated)}):")
            for o in self.report.outdated:
                lines.append(f"    {o.name} {o.current} \u2192 {o.latest}")
            lines.append("")

        # -- Summary --
        vuln_count = len(self.report.vulnerabilities)
        license_count = len(self.report.license_warnings)
        outdated_count = len(self.report.outdated)
        parts = []
        if vuln_count:
            parts.append(f"{vuln_count} vulnerabilit{'y' if vuln_count == 1 else 'ies'}")
        if license_count:
            parts.append(f"{license_count} license issue{'s' if license_count != 1 else ''}")
        if outdated_count:
            parts.append(f"{outdated_count} outdated")
        if parts:
            lines.append(f"  Summary: {', '.join(parts)}")
        else:
            lines.append("  Summary: No issues found \u2714")
        lines.append("")

        return "\n".join(lines)

    # -- JSON output --------------------------------------------------------

    def to_dict(self) -> dict:
        """Return audit report as a JSON-serializable dict."""
        return {
            "repo_path": self.report.repo_path,
            "dependencies_count": len(self.report.dependencies),
            "vulnerabilities": [
                {
                    "name": v.name, "version": v.version, "cve": v.cve,
                    "severity": v.severity, "description": v.description,
                    "fix_version": v.fix_version,
                }
                for v in self.report.vulnerabilities
            ],
            "license_warnings": [
                {"name": lw.name, "license": lw.license, "reason": lw.reason}
                for lw in self.report.license_warnings
            ],
            "outdated": [
                {"name": o.name, "current": o.current, "latest": o.latest}
                for o in self.report.outdated
            ],
        }

    # -----------------------------------------------------------------------
    # Parsers (private)
    # -----------------------------------------------------------------------

    def _parse_requirements_txt(self, filepath: Path):
        """Parse requirements.txt: package==version, package>=version."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Match: package==1.2.3 or package>=1.2.3 or package~=1.2.3
            m = re.match(r'^([a-zA-Z0-9_\-\.]+)\s*[=~>!<]+\s*([0-9][0-9a-zA-Z\.\-]*)', line)
            if m:
                name, version = m.group(1), m.group(2)
                self.report.dependencies.append(Dependency(
                    name=name, version=version, source=filepath.name,
                ))

    def _parse_pyproject_toml(self, filepath: Path):
        """Parse pyproject.toml [tool.poetry.dependencies] or [project.dependencies]."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        # Simple pattern: key = "^version" or key = ">=version" or key = {version = "..."}
        in_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if re.match(r'\[(tool\.poetry\.dependencies|project\.dependencies)\]', stripped):
                in_deps = True
                continue
            if stripped.startswith("[") and in_deps:
                in_deps = False
                continue
            if not in_deps:
                continue

            # key = "^1.2.3" or key = ">=1.2.3"
            m = re.match(r'^([a-zA-Z0-9_\-]+)\s*=\s*"[\^~>=<]*([0-9][0-9a-zA-Z\.\-]*)"', stripped)
            if m:
                name, version = m.group(1), m.group(2)
                if name == "python":
                    continue
                self.report.dependencies.append(Dependency(
                    name=name, version=version, source=filepath.name,
                ))
                continue

            # key = {version = "^1.2.3", ...}
            m = re.match(r'^([a-zA-Z0-9_\-]+)\s*=\s*\{.*version\s*=\s*"[\^~>=<]*([0-9][0-9a-zA-Z\.\-]*)"', stripped)
            if m:
                name, version = m.group(1), m.group(2)
                self.report.dependencies.append(Dependency(
                    name=name, version=version, source=filepath.name,
                ))

    def _parse_package_json(self, filepath: Path):
        """Parse package.json dependencies + devDependencies."""
        import json as _json
        try:
            data = _json.loads(filepath.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, _json.JSONDecodeError):
            return

        for section in ("dependencies", "devDependencies"):
            deps = data.get(section, {})
            if not isinstance(deps, dict):
                continue
            for name, version_spec in deps.items():
                # Extract version: "^1.2.3" -> "1.2.3", "~1.0.0" -> "1.0.0"
                version = re.sub(r'^[\^~>=<\s]+', '', str(version_spec))
                if version and version[0].isdigit():
                    self.report.dependencies.append(Dependency(
                        name=name, version=version, source=filepath.name,
                    ))

    def _parse_pom_xml(self, filepath: Path):
        """Parse pom.xml <dependency> blocks for artifactId + version."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        # Simple regex to extract artifact + version from dependency blocks
        dep_pattern = re.compile(
            r'<dependency>\s*'
            r'<groupId>[^<]+</groupId>\s*'
            r'<artifactId>([^<]+)</artifactId>\s*'
            r'<version>([^<$]+)</version>',
            re.DOTALL,
        )
        for m in dep_pattern.finditer(content):
            artifact_id = m.group(1).strip()
            version = m.group(2).strip()
            if version and version[0].isdigit():
                self.report.dependencies.append(Dependency(
                    name=artifact_id, version=version, source=filepath.name,
                ))

    def _parse_build_gradle(self, filepath: Path):
        """Parse build.gradle: implementation 'group:artifact:version'."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        # Match: implementation 'group:artifact:version' or "group:artifact:version"
        pattern = re.compile(
            r"(?:implementation|api|compile|testImplementation|runtimeOnly)\s+"
            r"['\"]([^:]+):([^:]+):([^'\"]+)['\"]"
        )
        for m in pattern.finditer(content):
            artifact = m.group(2).strip()
            version = m.group(3).strip()
            if version and version[0].isdigit():
                self.report.dependencies.append(Dependency(
                    name=artifact, version=version, source=filepath.name,
                ))

    def _parse_go_mod(self, filepath: Path):
        """Parse go.mod require blocks."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        in_require = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("require ("):
                in_require = True
                continue
            if stripped == ")" and in_require:
                in_require = False
                continue
            if in_require:
                # module v1.2.3
                m = re.match(r'^([^\s]+)\s+v?([0-9][0-9a-zA-Z\.\-]*)', stripped)
                if m:
                    module_path = m.group(1)
                    version = m.group(2)
                    # Use last path segment as name
                    name = module_path.rsplit("/", 1)[-1]
                    self.report.dependencies.append(Dependency(
                        name=name, version=version, source=filepath.name,
                    ))

            # Single-line require
            m = re.match(r'^require\s+([^\s]+)\s+v?([0-9][0-9a-zA-Z\.\-]*)', stripped)
            if m:
                module_path = m.group(1)
                version = m.group(2)
                name = module_path.rsplit("/", 1)[-1]
                self.report.dependencies.append(Dependency(
                    name=name, version=version, source=filepath.name,
                ))

    # -- License helpers ----------------------------------------------------

    def _check_npm_license(self, pkg_json: Path):
        """Check an npm package.json for GPL-family license."""
        import json as _json
        try:
            data = _json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return

        license_str = data.get("license", "")
        if isinstance(license_str, dict):
            license_str = license_str.get("type", "")
        name = data.get("name", pkg_json.parent.name)

        if isinstance(license_str, str):
            for gpl in GPL_LICENSES:
                if gpl.lower() in license_str.lower():
                    self.report.license_warnings.append(LicenseWarning(
                        name=name, license=license_str,
                        reason="may conflict with commercial use",
                    ))
                    break

    def _check_license_file(self, license_file: Path):
        """Check a LICENSE file for GPL-family patterns."""
        try:
            content = license_file.read_text(encoding="utf-8", errors="ignore")[:2000]
        except OSError:
            return

        # Detect license type from content
        content_lower = content.lower()
        detected = None
        if "gnu general public license" in content_lower:
            if "version 3" in content_lower:
                detected = "GPL-3.0"
            elif "version 2" in content_lower:
                detected = "GPL-2.0"
            else:
                detected = "GPL"
        elif "gnu affero general public license" in content_lower:
            detected = "AGPL-3.0"
        elif "gnu lesser general public license" in content_lower:
            detected = "LGPL"

        if detected:
            rel_path = str(license_file.relative_to(self.cwd))
            self.report.license_warnings.append(LicenseWarning(
                name=rel_path, license=detected,
                reason="may conflict with commercial use",
            ))

    # -- Outdated helpers ---------------------------------------------------

    def _check_pip_outdated(self):
        """Run pip list --outdated and parse results."""
        try:
            result = subprocess.run(
                ["pip", "list", "--outdated", "--format=json"],
                capture_output=True, text=True, timeout=30,
                cwd=self.cwd,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json as _json
                for pkg in _json.loads(result.stdout):
                    self.report.outdated.append(OutdatedPackage(
                        name=pkg.get("name", ""),
                        current=pkg.get("version", ""),
                        latest=pkg.get("latest_version", ""),
                    ))
        except Exception as e:
            logger.debug("pip outdated check failed: %s", e)

    def _check_npm_outdated(self):
        """Run npm outdated --json and parse results."""
        try:
            result = subprocess.run(
                ["npm", "outdated", "--json"],
                capture_output=True, text=True, timeout=30,
                cwd=self.cwd,
            )
            # npm outdated exits with code 1 when outdated packages exist
            if result.stdout.strip():
                import json as _json
                data = _json.loads(result.stdout)
                for name, info in data.items():
                    if isinstance(info, dict):
                        self.report.outdated.append(OutdatedPackage(
                            name=name,
                            current=info.get("current", ""),
                            latest=info.get("latest", ""),
                        ))
        except Exception as e:
            logger.debug("npm outdated check failed: %s", e)
