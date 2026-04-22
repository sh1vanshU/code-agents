"""Dependency License Auditor — scan Python/Node deps for license compliance."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.security.license_audit")

# ── License classification ───────────────────────────────────────────────────
_PERMISSIVE = {
    "mit", "apache-2.0", "apache 2.0", "apache license 2.0", "apache software license",
    "bsd", "bsd-2-clause", "bsd-3-clause", "bsd license", "isc", "unlicense",
    "cc0", "public domain", "python software foundation license", "psf",
    "mozilla public license 2.0", "mpl-2.0", "artistic-2.0", "zlib",
}
_COPYLEFT = {
    "gpl", "gpl-2.0", "gpl-3.0", "gnu general public license",
    "lgpl", "lgpl-2.1", "lgpl-3.0",
    "agpl", "agpl-3.0", "gnu affero general public license",
}
_RISKY_IN_COMMERCIAL = {"agpl", "agpl-3.0", "gnu affero general public license"}


@dataclass
class DepLicense:
    """A single dependency with its detected license."""

    package: str
    version: str
    license: str
    risk: str  # "ok" | "warning" | "critical"


class LicenseAuditor:
    """Audit dependency licenses in a project."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    # ── Public API ───────────────────────────────────────────────────────

    def audit(self) -> list[DepLicense]:
        """Scan all detected dependency ecosystems and return licenses."""
        results: list[DepLicense] = []
        results.extend(self._scan_python_deps())
        results.extend(self._scan_node_deps())
        logger.info("Audited %d dependencies", len(results))
        return results

    def generate_sbom(self) -> str:
        """Generate a simple SBOM (Software Bill of Materials) in JSON."""
        deps = self.audit()
        sbom = {
            "sbom_version": "1.0",
            "project": os.path.basename(self.cwd),
            "components": [
                {
                    "name": d.package,
                    "version": d.version,
                    "license": d.license,
                    "risk": d.risk,
                }
                for d in deps
            ],
            "summary": {
                "total": len(deps),
                "ok": sum(1 for d in deps if d.risk == "ok"),
                "warning": sum(1 for d in deps if d.risk == "warning"),
                "critical": sum(1 for d in deps if d.risk == "critical"),
            },
        }
        return json.dumps(sbom, indent=2)

    # ── Python scanning ──────────────────────────────────────────────────

    def _scan_python_deps(self) -> list[DepLicense]:
        """Parse pyproject.toml / requirements.txt and check licenses via pip show."""
        deps: list[DepLicense] = []
        packages = self._extract_python_packages()
        if not packages:
            return deps

        for pkg in packages:
            name, version, lic = self._pip_show(pkg)
            if name:
                risk = self._check_compatibility("MIT", lic)
                deps.append(DepLicense(package=name, version=version, license=lic, risk=risk))

        return deps

    def _extract_python_packages(self) -> list[str]:
        """Extract package names from pyproject.toml or requirements.txt."""
        packages: list[str] = []

        # Try pyproject.toml
        pyproject = os.path.join(self.cwd, "pyproject.toml")
        if os.path.isfile(pyproject):
            try:
                with open(pyproject, "r") as f:
                    in_deps = False
                    for line in f:
                        stripped = line.strip()
                        if stripped.startswith("[tool.poetry.dependencies]") or stripped.startswith("[project.dependencies]"):
                            in_deps = True
                            continue
                        if in_deps:
                            if stripped.startswith("["):
                                in_deps = False
                                continue
                            if "=" in stripped and not stripped.startswith("#"):
                                pkg = stripped.split("=")[0].strip().strip('"').strip("'")
                                if pkg and pkg != "python":
                                    packages.append(pkg)
                            elif stripped and not stripped.startswith("#"):
                                # PEP 621 style: "requests>=2.0"
                                pkg = stripped.strip('"').strip("'").split(">=")[0].split("<=")[0].split("==")[0].split("~=")[0].split(">")[0].split("<")[0].split("!")[0].strip()
                                if pkg and pkg != "python":
                                    packages.append(pkg)
            except OSError:
                pass

        # Try requirements.txt
        req_txt = os.path.join(self.cwd, "requirements.txt")
        if os.path.isfile(req_txt) and not packages:
            try:
                with open(req_txt, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and not line.startswith("-"):
                            pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
                            if pkg:
                                packages.append(pkg)
            except OSError:
                pass

        return packages[:100]  # cap to avoid runaway

    def _pip_show(self, package: str) -> tuple[str, str, str]:
        """Run pip show to get version and license for a package."""
        try:
            result = subprocess.run(
                ["pip", "show", package],
                capture_output=True,
                text=True,
                cwd=self.cwd,
                timeout=15,
            )
            if result.returncode != 0:
                return (package, "unknown", "unknown")

            name = package
            version = "unknown"
            lic = "unknown"
            for line in result.stdout.splitlines():
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
                elif line.startswith("License:"):
                    lic = line.split(":", 1)[1].strip() or "unknown"
            return (name, version, lic)
        except Exception:  # noqa: BLE001
            return (package, "unknown", "unknown")

    # ── Node scanning ────────────────────────────────────────────────────

    def _scan_node_deps(self) -> list[DepLicense]:
        """Parse package.json for dependency licenses."""
        deps: list[DepLicense] = []
        pkg_json = os.path.join(self.cwd, "package.json")
        if not os.path.isfile(pkg_json):
            return deps

        try:
            with open(pkg_json, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return deps

        project_license = data.get("license", "MIT")
        all_deps: dict[str, str] = {}
        for key in ("dependencies", "devDependencies"):
            all_deps.update(data.get(key, {}))

        # Check node_modules for license info
        node_modules = os.path.join(self.cwd, "node_modules")
        for pkg_name, ver_spec in list(all_deps.items())[:100]:
            lic = "unknown"
            version = ver_spec.lstrip("^~>=<")
            # Try reading package.json from node_modules
            mod_pkg = os.path.join(node_modules, pkg_name, "package.json")
            if os.path.isfile(mod_pkg):
                try:
                    with open(mod_pkg, "r") as f:
                        mod_data = json.load(f)
                    lic = mod_data.get("license", "unknown")
                    if isinstance(lic, dict):
                        lic = lic.get("type", "unknown")
                    version = mod_data.get("version", version)
                except (OSError, json.JSONDecodeError):
                    pass

            risk = self._check_compatibility(project_license, lic)
            deps.append(DepLicense(package=pkg_name, version=version, license=str(lic), risk=risk))

        return deps

    # ── Compatibility check ──────────────────────────────────────────────

    def _check_compatibility(self, project_license: str, dep_license: str) -> str:
        """Check if dep_license is compatible with project_license.

        Returns "ok", "warning", or "critical".
        """
        dep_lower = dep_license.lower().strip()

        if dep_lower in ("unknown", "", "none", "unlicensed"):
            return "warning"

        # AGPL is risky in any commercial context
        if any(r in dep_lower for r in _RISKY_IN_COMMERCIAL):
            return "critical"

        # GPL in an MIT/Apache/BSD project
        proj_lower = project_license.lower()
        if any(p in proj_lower for p in ("mit", "apache", "bsd", "isc")):
            if any(g in dep_lower for g in ("gpl", "gnu general public")):
                if "lgpl" not in dep_lower:
                    return "critical"
                return "warning"

        # Known permissive — all good
        if any(p in dep_lower for p in _PERMISSIVE):
            return "ok"

        # Copyleft that isn't GPL (handled above) — warning
        if any(c in dep_lower for c in _COPYLEFT):
            return "warning"

        # Unknown/unrecognized license string
        return "warning"


# ── Formatting helpers ───────────────────────────────────────────────────────


def format_license_report(deps: list[DepLicense]) -> str:
    """Return a human-readable license audit report."""
    if not deps:
        return "  No dependencies found."

    risk_icon = {"ok": ".", "warning": "~", "critical": "!"}
    lines: list[str] = ["", "  License Audit Report", "  " + "-" * 50]

    ok = [d for d in deps if d.risk == "ok"]
    warn = [d for d in deps if d.risk == "warning"]
    crit = [d for d in deps if d.risk == "critical"]

    if crit:
        lines.append("")
        lines.append("  CRITICAL:")
        for d in crit:
            lines.append(f"    [!] {d.package}=={d.version}  ({d.license})")

    if warn:
        lines.append("")
        lines.append("  WARNINGS:")
        for d in warn:
            lines.append(f"    [~] {d.package}=={d.version}  ({d.license})")

    lines.append("")
    lines.append(f"  Summary: {len(ok)} ok, {len(warn)} warnings, {len(crit)} critical")
    lines.append(f"  Total dependencies scanned: {len(deps)}")
    lines.append("")
    return "\n".join(lines)
