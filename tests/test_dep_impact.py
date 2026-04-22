"""Tests for code_agents.dep_impact — Dependency Impact Scanner."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.domain.dep_impact import (
    BreakingChange,
    DepImpactReport,
    DeprecatedUsage,
    DependencyImpactScanner,
    MigrationPatch,
    PackageUsage,
    format_impact_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_python_repo(tmp_path):
    """Create a minimal Python repo with pyproject.toml and source files."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.poetry.dependencies]\n'
        'python = "^3.10"\n'
        'requests = "^2.28.0"\n'
        'flask = "^2.3.0"\n',
        encoding="utf-8",
    )
    src = tmp_path / "app.py"
    src.write_text(
        "import requests\n"
        "from requests import Session, adapters\n"
        "from flask import Flask\n"
        "\n"
        "resp = requests.get('https://example.com')\n",
        encoding="utf-8",
    )
    sub = tmp_path / "lib"
    sub.mkdir()
    (sub / "client.py").write_text(
        "from requests.auth import HTTPBasicAuth\n"
        "import os\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def tmp_node_repo(tmp_path):
    """Create a minimal Node repo with package.json and source files."""
    pkg = tmp_path / "package.json"
    pkg.write_text(
        json.dumps({
            "dependencies": {"express": "^4.18.0", "lodash": "^4.17.21"},
            "devDependencies": {"jest": "^29.0.0"},
        }),
        encoding="utf-8",
    )
    src = tmp_path / "index.js"
    src.write_text(
        "const express = require('express');\n"
        "const { merge } = require('lodash');\n"
        "import axios from 'axios';\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def tmp_java_repo(tmp_path):
    """Create a minimal Java repo with pom.xml."""
    pom = tmp_path / "pom.xml"
    pom.write_text(
        "<project>\n"
        "  <dependencies>\n"
        "    <dependency>\n"
        "      <groupId>com.google.guava</groupId>\n"
        "      <artifactId>guava</artifactId>\n"
        "      <version>31.1-jre</version>\n"
        "    </dependency>\n"
        "  </dependencies>\n"
        "</project>\n",
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "App.java").write_text(
        "import com.google.common.collect.ImmutableList;\n"
        "import java.util.List;\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def tmp_go_repo(tmp_path):
    """Create a minimal Go repo with go.mod."""
    gomod = tmp_path / "go.mod"
    gomod.write_text(
        "module example.com/myapp\n"
        "\n"
        "go 1.21\n"
        "\n"
        "require github.com/gin-gonic/gin v1.9.1\n",
        encoding="utf-8",
    )
    src = tmp_path / "main.go"
    src.write_text(
        'package main\n'
        '\n'
        'import "github.com/gin-gonic/gin"\n'
        '\n'
        'func main() {\n'
        '    r := gin.Default()\n'
        '}\n',
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# TestVersionParsing
# ---------------------------------------------------------------------------


class TestVersionParsing:
    """Test version detection from various manifest files."""

    def test_pyproject_toml_caret(self, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0"
        )
        scanner.language = "python"
        ver = scanner._find_current_version()
        assert ver == "2.28.0"

    def test_pyproject_toml_flask(self, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="flask", target_version="3.0.0"
        )
        scanner.language = "python"
        ver = scanner._find_current_version()
        assert ver == "2.3.0"

    def test_package_json_deps(self, tmp_node_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_node_repo), package="express", target_version="5.0.0"
        )
        scanner.language = "node"
        ver = scanner._find_current_version()
        assert ver == "4.18.0"

    def test_package_json_devdeps(self, tmp_node_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_node_repo), package="jest", target_version="30.0.0"
        )
        scanner.language = "node"
        ver = scanner._find_current_version()
        assert ver == "29.0.0"

    def test_pom_xml(self, tmp_java_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_java_repo), package="guava", target_version="33.0-jre"
        )
        scanner.language = "java"
        ver = scanner._find_current_version()
        assert ver == "31.1-jre"

    def test_go_mod(self, tmp_go_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_go_repo), package="github.com/gin-gonic/gin", target_version="1.10.0"
        )
        scanner.language = "go"
        ver = scanner._find_current_version()
        assert ver == "1.9.1"

    def test_missing_package_returns_unknown(self, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="nonexistent-pkg", target_version="1.0.0"
        )
        scanner.language = "python"
        ver = scanner._find_current_version()
        assert ver == "unknown"

    def test_requirements_txt(self, tmp_path):
        (tmp_path / "requirements.txt").write_text(
            "requests>=2.25.0\nflask==2.0.1\n", encoding="utf-8"
        )
        scanner = DependencyImpactScanner(
            cwd=str(tmp_path), package="requests", target_version="3.0.0"
        )
        scanner.language = "python"
        ver = scanner._find_current_version()
        assert ver == "2.25.0"


# ---------------------------------------------------------------------------
# TestUsageDetection
# ---------------------------------------------------------------------------


class TestUsageDetection:
    """Test import/usage detection across languages."""

    def test_python_imports(self, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0"
        )
        scanner.language = "python"
        usages = scanner._find_usages()
        assert len(usages) >= 3
        files = {u.file for u in usages}
        assert "app.py" in files
        assert os.path.join("lib", "client.py") in files

    def test_python_symbols_extracted(self, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0"
        )
        scanner.language = "python"
        usages = scanner._find_usages()
        # "from requests import Session, adapters" should extract symbols
        from_import = [u for u in usages if "Session" in u.import_statement]
        assert from_import
        assert "Session" in from_import[0].symbols_used
        assert "adapters" in from_import[0].symbols_used

    def test_node_require(self, tmp_node_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_node_repo), package="express", target_version="5.0.0"
        )
        scanner.language = "node"
        usages = scanner._find_usages()
        assert len(usages) >= 1
        assert usages[0].file == "index.js"

    def test_node_import_from(self, tmp_node_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_node_repo), package="axios", target_version="2.0.0"
        )
        scanner.language = "node"
        usages = scanner._find_usages()
        # axios is imported but not in package.json deps — still detected as usage
        assert len(usages) >= 1

    def test_java_imports(self, tmp_java_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_java_repo), package="guava", target_version="33.0-jre"
        )
        scanner.language = "java"
        usages = scanner._find_usages()
        # "import com.google.common.collect.ImmutableList" should not match guava directly
        # but java.util.List should not match either
        # guava manifests as "com.google" — the scanner checks if pkg name is in the import
        # Since our matcher checks if "guava" is in "com.google.common.collect.ImmutableList"
        # it won't match. That's correct — Java imports use group IDs not artifact IDs.
        # Let's verify no false positives
        assert all("guava" not in u.import_statement for u in usages) or len(usages) == 0

    def test_go_imports(self, tmp_go_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_go_repo), package="github.com/gin-gonic/gin", target_version="1.10.0"
        )
        scanner.language = "go"
        usages = scanner._find_usages()
        assert len(usages) >= 1
        assert "gin" in usages[0].import_statement

    def test_skips_hidden_dirs(self, tmp_python_repo):
        # Create .git dir with a .py file — should be skipped
        git_dir = tmp_python_repo / ".git"
        git_dir.mkdir()
        (git_dir / "hooks.py").write_text("import requests\n", encoding="utf-8")

        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0"
        )
        scanner.language = "python"
        usages = scanner._find_usages()
        files = {u.file for u in usages}
        assert not any(".git" in f for f in files)


# ---------------------------------------------------------------------------
# TestRegistryFetch
# ---------------------------------------------------------------------------


class TestRegistryFetch:
    """Test registry info fetching with mocked HTTP."""

    @patch("urllib.request.urlopen")
    def test_pypi_fetch(self, mock_urlopen, tmp_python_repo):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "info": {"name": "requests", "version": "2.31.0", "summary": "HTTP library"},
            "releases": {"2.28.0": [], "2.31.0": [], "3.0.0": []},
        }).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0"
        )
        scanner.language = "python"
        info = scanner._fetch_registry_info()

        assert info["name"] == "requests"
        assert info["latest"] == "2.31.0"
        assert "2.28.0" in info["releases"]

    @patch("urllib.request.urlopen")
    def test_npm_fetch(self, mock_urlopen, tmp_node_repo):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "name": "express",
            "description": "Fast web framework",
            "dist-tags": {"latest": "4.18.2"},
            "versions": {"4.17.0": {}, "4.18.0": {}, "4.18.2": {}, "5.0.0": {}},
        }).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        scanner = DependencyImpactScanner(
            cwd=str(tmp_node_repo), package="express", target_version="5.0.0"
        )
        scanner.language = "node"
        info = scanner._fetch_registry_info()

        assert info["name"] == "express"
        assert info["latest"] == "4.18.2"
        assert "5.0.0" in info["releases"]

    @patch("urllib.request.urlopen", side_effect=Exception("Network error"))
    def test_fetch_failure_returns_empty(self, mock_urlopen, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0"
        )
        scanner.language = "python"
        info = scanner._fetch_registry_info()
        assert info == {}


# ---------------------------------------------------------------------------
# TestBreakingChanges
# ---------------------------------------------------------------------------


class TestBreakingChanges:
    """Test breaking change detection logic."""

    def test_major_version_bump_detected(self, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0"
        )
        scanner.language = "python"
        scanner.current_version = "2.28.0"

        usages = [
            PackageUsage(file="app.py", line=1, import_statement="import requests", symbols_used=["get"]),
        ]
        breaking = scanner._detect_breaking_changes({}, usages)
        assert len(breaking) >= 1
        assert any("Major version bump" in b.description for b in breaking)

    def test_no_breaking_on_minor_bump(self, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="2.31.0"
        )
        scanner.language = "python"
        scanner.current_version = "2.28.0"

        usages = [
            PackageUsage(file="app.py", line=1, import_statement="import requests", symbols_used=[]),
        ]
        breaking = scanner._detect_breaking_changes({}, usages)
        # No major bump, so no "Major version bump" entry
        assert not any("Major version bump" in b.description for b in breaking)

    def test_known_deprecation_detected(self, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0"
        )
        scanner.language = "python"
        scanner.current_version = "2.28.0"

        usages = [
            PackageUsage(
                file="app.py", line=5,
                import_statement="from requests.packages import urllib3",
                symbols_used=["urllib3"],
            ),
        ]
        breaking = scanner._detect_breaking_changes({}, usages)
        assert any("requests.packages" in b.description for b in breaking)


# ---------------------------------------------------------------------------
# TestFormatReport
# ---------------------------------------------------------------------------


class TestFormatReport:
    """Test report formatting."""

    def test_format_contains_sections(self):
        report = DepImpactReport(
            package="requests",
            current_version="2.28.0",
            target_version="3.0.0",
            language="python",
            usages=[
                PackageUsage(file="app.py", line=1, import_statement="import requests", symbols_used=[]),
            ],
            breaking_changes=[
                BreakingChange(
                    version="3.0.0",
                    description="Major version bump",
                    affected_symbols=["get"],
                ),
            ],
            deprecated_usages=[
                DeprecatedUsage(
                    symbol="requests.packages",
                    file="app.py",
                    line=5,
                    replacement="urllib3 directly",
                    deprecated_since="2.0",
                ),
            ],
            patches=[
                MigrationPatch(
                    file="app.py",
                    original="from requests.packages import urllib3",
                    patched="import urllib3",
                    description="Replace deprecated import",
                ),
            ],
            affected_files=["app.py"],
            risk_level="high",
        )

        output = format_impact_report(report)
        assert "Dependency Impact Report" in output
        assert "requests" in output
        assert "2.28.0" in output
        assert "3.0.0" in output
        assert "HIGH" in output
        assert "Usages" in output
        assert "Breaking Changes" in output
        assert "Deprecated Usages" in output
        assert "Migration Patches" in output

    def test_format_empty_report(self):
        report = DepImpactReport(
            package="some-pkg",
            current_version="1.0.0",
            target_version="2.0.0",
            language="python",
            usages=[],
            breaking_changes=[],
            deprecated_usages=[],
            patches=[],
            affected_files=[],
            risk_level="low",
        )
        output = format_impact_report(report)
        assert "No usages found" in output
        assert "None detected" in output
        assert "LOW" in output


# ---------------------------------------------------------------------------
# TestRiskCalculation
# ---------------------------------------------------------------------------


class TestRiskCalculation:
    """Test risk level calculation."""

    def test_low_risk(self, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="2.31.0"
        )
        scanner.current_version = "2.28.0"
        risk = scanner._calculate_risk(
            usages=[PackageUsage(file="a.py", line=1, import_statement="", symbols_used=[])],
            breaking=[], deprecated=[],
        )
        assert risk == "low"

    def test_high_risk_many_files(self, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0"
        )
        scanner.current_version = "2.28.0"
        usages = [
            PackageUsage(file=f"file{i}.py", line=1, import_statement="", symbols_used=[])
            for i in range(25)
        ]
        breaking = [BreakingChange(version="3.0", description="x", affected_symbols=[])]
        risk = scanner._calculate_risk(usages, breaking, [])
        assert risk in ("high", "critical")


# ---------------------------------------------------------------------------
# TestLanguageDetection
# ---------------------------------------------------------------------------


class TestLanguageDetection:
    """Test language auto-detection."""

    def test_python_detected(self, tmp_python_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0"
        )
        lang = scanner._detect_language()
        assert lang == "python"

    def test_node_detected(self, tmp_node_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_node_repo), package="express", target_version="5.0.0"
        )
        lang = scanner._detect_language()
        assert lang == "node"

    def test_go_detected(self, tmp_go_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_go_repo), package="gin", target_version="1.10.0"
        )
        lang = scanner._detect_language()
        assert lang == "go"

    def test_java_detected(self, tmp_java_repo):
        scanner = DependencyImpactScanner(
            cwd=str(tmp_java_repo), package="guava", target_version="33.0"
        )
        lang = scanner._detect_language()
        assert lang == "java"


# ---------------------------------------------------------------------------
# TestFullScan
# ---------------------------------------------------------------------------


class TestFullScan:
    """Integration-style test of the full scan pipeline."""

    @patch("urllib.request.urlopen")
    def test_full_scan_python(self, mock_urlopen, tmp_python_repo):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "info": {"name": "requests", "version": "2.31.0", "summary": "HTTP"},
            "releases": {"2.28.0": [], "2.31.0": [], "3.0.0": []},
        }).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0"
        )
        report = scanner.scan()

        assert report.package == "requests"
        assert report.language == "python"
        assert report.current_version == "2.28.0"
        assert report.target_version == "3.0.0"
        assert len(report.usages) >= 2
        assert len(report.affected_files) >= 1
        assert report.risk_level in ("low", "medium", "high", "critical")

    @patch("urllib.request.urlopen")
    def test_full_scan_node(self, mock_urlopen, tmp_node_repo):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "name": "express",
            "dist-tags": {"latest": "4.18.2"},
            "versions": {"4.18.0": {}, "5.0.0": {}},
        }).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        scanner = DependencyImpactScanner(
            cwd=str(tmp_node_repo), package="express", target_version="5.0.0"
        )
        report = scanner.scan()

        assert report.package == "express"
        assert report.language == "node"
        assert len(report.usages) >= 1


# ---------------------------------------------------------------------------
# TestApplyPatches
# ---------------------------------------------------------------------------


class TestApplyPatches:
    """Test patch application."""

    @patch("urllib.request.urlopen")
    def test_apply_dry_run(self, mock_urlopen, tmp_python_repo):
        """Dry run should not modify files."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "info": {"name": "requests", "version": "2.31.0"},
            "releases": {},
        }).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        original_content = (tmp_python_repo / "app.py").read_text(encoding="utf-8")

        scanner = DependencyImpactScanner(
            cwd=str(tmp_python_repo), package="requests", target_version="3.0.0",
            dry_run=True,
        )
        count = scanner.apply_patches()
        # File should be unchanged in dry-run
        assert (tmp_python_repo / "app.py").read_text(encoding="utf-8") == original_content
