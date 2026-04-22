"""Tests for the dependency license auditor."""

from __future__ import annotations

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from code_agents.security.license_audit import (
    LicenseAuditor, DepLicense, format_license_report,
)


class TestDepLicense:
    """Test DepLicense dataclass."""

    def test_fields(self):
        d = DepLicense(package="requests", version="2.31.0", license="Apache-2.0", risk="ok")
        assert d.package == "requests"
        assert d.risk == "ok"


class TestCheckCompatibility:
    """Test license compatibility checking."""

    def _auditor(self, tmp_path):
        return LicenseAuditor(cwd=str(tmp_path))

    def test_permissive_ok(self, tmp_path):
        a = self._auditor(tmp_path)
        assert a._check_compatibility("MIT", "MIT") == "ok"
        assert a._check_compatibility("MIT", "Apache-2.0") == "ok"
        assert a._check_compatibility("MIT", "BSD-3-Clause") == "ok"
        assert a._check_compatibility("MIT", "ISC") == "ok"

    def test_unknown_warning(self, tmp_path):
        a = self._auditor(tmp_path)
        assert a._check_compatibility("MIT", "unknown") == "warning"
        assert a._check_compatibility("MIT", "") == "warning"

    def test_agpl_critical(self, tmp_path):
        a = self._auditor(tmp_path)
        assert a._check_compatibility("MIT", "AGPL-3.0") == "critical"
        assert a._check_compatibility("Apache-2.0", "GNU Affero General Public License") == "critical"

    def test_gpl_in_mit_critical(self, tmp_path):
        a = self._auditor(tmp_path)
        assert a._check_compatibility("MIT", "GPL-3.0") == "critical"
        assert a._check_compatibility("BSD", "GPL-2.0") == "critical"

    def test_lgpl_warning(self, tmp_path):
        a = self._auditor(tmp_path)
        assert a._check_compatibility("MIT", "LGPL-2.1") == "warning"

    def test_unrecognized_license(self, tmp_path):
        a = self._auditor(tmp_path)
        assert a._check_compatibility("MIT", "Some Custom License v42") == "warning"


class TestScanPythonDeps:
    """Test Python dependency scanning."""

    def test_no_pyproject(self, tmp_path):
        a = LicenseAuditor(cwd=str(tmp_path))
        deps = a._scan_python_deps()
        assert deps == []

    def test_with_pyproject(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[tool.poetry.dependencies]\n"
            'python = "^3.10"\n'
            'requests = "^2.31"\n'
            'click = "^8.0"\n'
        )
        a = LicenseAuditor(cwd=str(tmp_path))
        with patch.object(a, "_pip_show", return_value=("requests", "2.31.0", "Apache-2.0")):
            deps = a._scan_python_deps()
            # Should find requests and click (not python)
            assert len(deps) >= 1

    def test_with_requirements_txt(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("flask==2.3.0\ngunicorn>=21.0\n")
        a = LicenseAuditor(cwd=str(tmp_path))
        with patch.object(a, "_pip_show", return_value=("flask", "2.3.0", "BSD-3-Clause")):
            deps = a._scan_python_deps()
            assert len(deps) >= 1


class TestScanNodeDeps:
    """Test Node dependency scanning."""

    def test_no_package_json(self, tmp_path):
        a = LicenseAuditor(cwd=str(tmp_path))
        deps = a._scan_node_deps()
        assert deps == []

    def test_with_package_json(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({
            "license": "MIT",
            "dependencies": {"express": "^4.18.0"},
            "devDependencies": {"jest": "^29.0"},
        }))
        a = LicenseAuditor(cwd=str(tmp_path))
        deps = a._scan_node_deps()
        assert len(deps) == 2
        assert deps[0].package in ("express", "jest")

    def test_with_node_modules(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"license": "MIT", "dependencies": {"lodash": "^4.17"}}))
        nm = tmp_path / "node_modules" / "lodash"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text(json.dumps({"name": "lodash", "version": "4.17.21", "license": "MIT"}))
        a = LicenseAuditor(cwd=str(tmp_path))
        deps = a._scan_node_deps()
        assert len(deps) == 1
        assert deps[0].license == "MIT"
        assert deps[0].version == "4.17.21"


class TestGenerateSbom:
    """Test SBOM generation."""

    def test_sbom_format(self, tmp_path):
        a = LicenseAuditor(cwd=str(tmp_path))
        with patch.object(a, "audit", return_value=[
            DepLicense(package="requests", version="2.31", license="Apache-2.0", risk="ok"),
            DepLicense(package="mystery", version="1.0", license="unknown", risk="warning"),
        ]):
            sbom_str = a.generate_sbom()
            sbom = json.loads(sbom_str)
            assert sbom["sbom_version"] == "1.0"
            assert len(sbom["components"]) == 2
            assert sbom["summary"]["ok"] == 1
            assert sbom["summary"]["warning"] == 1


class TestFormatLicenseReport:
    """Test report formatting."""

    def test_empty(self):
        report = format_license_report([])
        assert "No dependencies" in report

    def test_with_findings(self):
        deps = [
            DepLicense(package="safe", version="1.0", license="MIT", risk="ok"),
            DepLicense(package="risky", version="2.0", license="GPL-3.0", risk="critical"),
            DepLicense(package="unknown-lib", version="0.1", license="unknown", risk="warning"),
        ]
        report = format_license_report(deps)
        assert "CRITICAL" in report
        assert "risky" in report
        assert "WARNINGS" in report
        assert "Summary" in report
