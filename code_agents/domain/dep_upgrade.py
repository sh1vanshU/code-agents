"""Dependency Upgrade Pilot — scan, bump, test, rollback outdated dependencies."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.domain.dep_upgrade")


@dataclass
class UpgradeCandidate:
    name: str
    current_version: str
    latest_version: str
    source_file: str  # pyproject.toml, package.json, etc.
    changelog_url: str = ""
    breaking_changes: list[str] = field(default_factory=list)
    cve_fixes: list[str] = field(default_factory=list)
    is_major: bool = False


@dataclass
class UpgradeResult:
    candidate: UpgradeCandidate
    status: str = "pending"  # success, test_failed, build_failed, skipped, pending
    test_output: str = ""
    error: str = ""
    rollback_applied: bool = False


@dataclass
class UpgradeReport:
    repo_path: str = ""
    package_manager: str = ""
    candidates: list[UpgradeCandidate] = field(default_factory=list)
    results: list[UpgradeResult] = field(default_factory=list)

    @property
    def total_outdated(self) -> int:
        return len(self.candidates)

    @property
    def upgraded(self) -> int:
        return sum(1 for r in self.results if r.status == "success")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status in ("test_failed", "build_failed"))

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")


_PYPI_VERSION_RE = re.compile(r'"version"\s*:\s*"([^"]+)"')
_SEMVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class DependencyUpgradePilot:
    """Scans, upgrades, tests, and rolls back dependencies."""

    def __init__(self, cwd: str = ".", dry_run: bool = True):
        self.cwd = os.path.abspath(cwd)
        self.dry_run = dry_run
        self.package_manager = self._detect_package_manager()

    def scan(self) -> list[UpgradeCandidate]:
        """Scan for outdated dependencies."""
        if self.package_manager == "poetry":
            return self._scan_poetry()
        elif self.package_manager == "npm":
            return self._scan_npm()
        elif self.package_manager == "pip":
            return self._scan_pip()
        logger.warning("No supported package manager detected")
        return []

    def upgrade(self, package: str = "", all_packages: bool = False) -> UpgradeReport:
        """Upgrade one or all packages."""
        candidates = self.scan()
        report = UpgradeReport(
            repo_path=self.cwd,
            package_manager=self.package_manager,
            candidates=candidates,
        )

        if not candidates:
            return report

        targets = candidates
        if package:
            targets = [c for c in candidates if c.name == package]
            if not targets:
                logger.warning("Package %s not found in outdated list", package)
                return report
        elif not all_packages:
            # Default: only patch/minor upgrades
            targets = [c for c in candidates if not c.is_major]

        for candidate in targets:
            result = self._try_upgrade_one(candidate)
            report.results.append(result)

        return report

    def _run(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(
            list(args), cwd=self.cwd, capture_output=True, text=True, timeout=timeout,
        )

    def _detect_package_manager(self) -> str:
        """Detect the package manager used in the repo."""
        if os.path.exists(os.path.join(self.cwd, "pyproject.toml")):
            pyproject = Path(os.path.join(self.cwd, "pyproject.toml")).read_text()
            if "[tool.poetry]" in pyproject:
                return "poetry"
            return "pip"
        if os.path.exists(os.path.join(self.cwd, "package.json")):
            if os.path.exists(os.path.join(self.cwd, "yarn.lock")):
                return "yarn"
            return "npm"
        if os.path.exists(os.path.join(self.cwd, "requirements.txt")):
            return "pip"
        return "unknown"

    def _scan_poetry(self) -> list[UpgradeCandidate]:
        """Scan poetry dependencies for outdated packages."""
        try:
            result = self._run("poetry", "show", "--outdated", "--no-ansi")
            if result.returncode != 0:
                logger.warning("poetry show --outdated failed: %s", result.stderr)
                return []
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        candidates = []
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 3:
                name, current, _, latest = parts[0], parts[1], parts[2] if len(parts) > 2 else "", parts[-1]
                is_major = self._is_major_bump(current, latest)
                candidates.append(UpgradeCandidate(
                    name=name,
                    current_version=current,
                    latest_version=latest,
                    source_file="pyproject.toml",
                    is_major=is_major,
                ))
        return candidates

    def _scan_npm(self) -> list[UpgradeCandidate]:
        """Scan npm dependencies for outdated packages."""
        try:
            result = self._run("npm", "outdated", "--json")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        candidates = []
        try:
            data = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            return []

        for name, info in data.items():
            current = info.get("current", "")
            latest = info.get("latest", "")
            if current and latest and current != latest:
                candidates.append(UpgradeCandidate(
                    name=name,
                    current_version=current,
                    latest_version=latest,
                    source_file="package.json",
                    is_major=self._is_major_bump(current, latest),
                ))
        return candidates

    def _scan_pip(self) -> list[UpgradeCandidate]:
        """Scan pip dependencies for outdated packages."""
        try:
            result = self._run("pip", "list", "--outdated", "--format=json")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        candidates = []
        try:
            data = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            return []

        for pkg in data:
            name = pkg.get("name", "")
            current = pkg.get("version", "")
            latest = pkg.get("latest_version", "")
            if name and current and latest:
                candidates.append(UpgradeCandidate(
                    name=name,
                    current_version=current,
                    latest_version=latest,
                    source_file="requirements.txt",
                    is_major=self._is_major_bump(current, latest),
                ))
        return candidates

    def _is_major_bump(self, current: str, latest: str) -> bool:
        """Check if upgrade is a major version bump."""
        cm = _SEMVER_RE.search(current)
        lm = _SEMVER_RE.search(latest)
        if cm and lm:
            return int(lm.group(1)) > int(cm.group(1))
        return False

    def _try_upgrade_one(self, candidate: UpgradeCandidate) -> UpgradeResult:
        """Attempt to upgrade a single package."""
        result = UpgradeResult(candidate=candidate)

        if self.dry_run:
            result.status = "skipped"
            result.test_output = "Dry run — no changes made"
            return result

        # Backup lock files
        backup = self._backup_lock_files()

        try:
            # Perform the upgrade
            if self.package_manager == "poetry":
                up = self._run("poetry", "add", f"{candidate.name}@^{candidate.latest_version}")
            elif self.package_manager == "npm":
                up = self._run("npm", "install", f"{candidate.name}@{candidate.latest_version}")
            elif self.package_manager == "pip":
                up = self._run("pip", "install", f"{candidate.name}=={candidate.latest_version}")
            else:
                result.status = "skipped"
                return result

            if up.returncode != 0:
                result.status = "build_failed"
                result.error = up.stderr[:500]
                self._restore_lock_files(backup)
                result.rollback_applied = True
                return result

            # Run tests
            test_ok, test_output = self._run_tests()
            result.test_output = test_output[:1000]

            if test_ok:
                result.status = "success"
            else:
                result.status = "test_failed"
                self._restore_lock_files(backup)
                result.rollback_applied = True

        except Exception as exc:
            result.status = "build_failed"
            result.error = str(exc)[:500]
            self._restore_lock_files(backup)
            result.rollback_applied = True

        return result

    def _run_tests(self) -> tuple[bool, str]:
        """Run the project's test suite."""
        try:
            if self.package_manager == "poetry":
                r = self._run("poetry", "run", "pytest", "--tb=short", "-q", timeout=300)
            elif self.package_manager in ("npm", "yarn"):
                r = self._run("npm", "test", timeout=300)
            else:
                r = self._run("pytest", "--tb=short", "-q", timeout=300)
            return r.returncode == 0, r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            return False, "Tests timed out"

    def _backup_lock_files(self) -> dict[str, str]:
        """Backup lock files for rollback."""
        backup = {}
        lock_files = ["poetry.lock", "package-lock.json", "yarn.lock", "Pipfile.lock"]
        for lf in lock_files:
            path = os.path.join(self.cwd, lf)
            if os.path.exists(path):
                backup_path = path + ".bak"
                shutil.copy2(path, backup_path)
                backup[path] = backup_path
        return backup

    def _restore_lock_files(self, backup: dict[str, str]) -> None:
        """Restore lock files from backup."""
        for original, bak in backup.items():
            if os.path.exists(bak):
                shutil.move(bak, original)


def format_upgrade_report(report: UpgradeReport) -> str:
    """Format upgrade report for display."""
    lines = [
        "## Dependency Upgrade Report",
        "",
        f"**Package Manager:** {report.package_manager}",
        f"**Outdated:** {report.total_outdated} | "
        f"**Upgraded:** {report.upgraded} | "
        f"**Failed:** {report.failed} | "
        f"**Skipped:** {report.skipped}",
        "",
    ]

    if report.candidates:
        lines.extend(["### Outdated Packages", ""])
        lines.append("| Package | Current | Latest | Major? |")
        lines.append("|---------|---------|--------|--------|")
        for c in report.candidates:
            major = "Yes" if c.is_major else "No"
            lines.append(f"| {c.name} | {c.current_version} | {c.latest_version} | {major} |")
        lines.append("")

    if report.results:
        lines.extend(["### Upgrade Results", ""])
        for r in report.results:
            icon = {
                "success": "✅", "test_failed": "❌", "build_failed": "💥",
                "skipped": "⏭️", "pending": "⏳",
            }.get(r.status, "❓")
            c = r.candidate
            lines.append(f"- {icon} **{c.name}** {c.current_version} → {c.latest_version}: {r.status}")
            if r.error:
                lines.append(f"  Error: {r.error[:200]}")
        lines.append("")

    return "\n".join(lines)
