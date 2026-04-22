"""Tests for code_agents.vuln_chain — vulnerability dependency chain scanner."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from code_agents.security.vuln_chain import (
    VulnChainScanner,
    VulnDep,
    _parse_version,
    _version_lt,
    format_vuln_report,
    vuln_report_to_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp: str, name: str, content: str) -> Path:
    p = Path(tmp) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


class TestVersionParsing:
    def test_simple_version(self):
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_two_part(self):
        assert _parse_version("2.0") == (2, 0)

    def test_with_suffix(self):
        assert _parse_version("1.2.3rc1") == (1, 2, 31)

    def test_empty_string(self):
        assert _parse_version("") == (0,)

    def test_lt_basic(self):
        assert _version_lt("1.0.0", "2.0.0")

    def test_lt_patch(self):
        assert _version_lt("1.2.3", "1.2.4")

    def test_not_lt_equal(self):
        assert not _version_lt("1.0.0", "1.0.0")

    def test_not_lt_greater(self):
        assert not _version_lt("2.0.0", "1.0.0")

    def test_lt_minor(self):
        assert _version_lt("1.1.0", "1.2.0")


# ---------------------------------------------------------------------------
# VulnDep dataclass
# ---------------------------------------------------------------------------


class TestVulnDep:
    def test_basic_creation(self):
        v = VulnDep(
            package="lodash", version="4.17.20",
            cve="CVE-2021-23337", severity="critical",
            description="Command injection",
        )
        assert v.package == "lodash"
        assert v.dep_chain == []
        assert v.upgrade_to == ""

    def test_with_chain(self):
        v = VulnDep(
            package="log4j", version="2.14.0",
            cve="CVE-2021-44228", severity="critical",
            description="Log4Shell",
            dep_chain=["myapp -> spring-boot -> log4j"],
        )
        assert len(v.dep_chain) == 1


# ---------------------------------------------------------------------------
# Requirements.txt parsing
# ---------------------------------------------------------------------------


class TestRequirementsParsing:
    def test_pinned_versions(self, tmp_path):
        _write(str(tmp_path), "requirements.txt",
               "flask==2.0.0\nrequests==2.28.0\npyyaml==5.3\n")
        scanner = VulnChainScanner(cwd=str(tmp_path))
        deps = scanner._parse_dependencies()
        assert deps["flask"] == "2.0.0"
        assert deps["requests"] == "2.28.0"
        assert deps["pyyaml"] == "5.3"

    def test_gte_versions(self, tmp_path):
        _write(str(tmp_path), "requirements.txt", "django>=3.2.0\n")
        scanner = VulnChainScanner(cwd=str(tmp_path))
        deps = scanner._parse_dependencies()
        assert deps["django"] == "3.2.0"

    def test_comments_and_blanks(self, tmp_path):
        _write(str(tmp_path), "requirements.txt",
               "# comment\n\nflask==2.0.0\n  \n")
        scanner = VulnChainScanner(cwd=str(tmp_path))
        deps = scanner._parse_dependencies()
        assert "flask" in deps

    def test_bare_package(self, tmp_path):
        _write(str(tmp_path), "requirements.txt", "requests\n")
        scanner = VulnChainScanner(cwd=str(tmp_path))
        deps = scanner._parse_dependencies()
        assert deps["requests"] == "0.0.0"


# ---------------------------------------------------------------------------
# package.json parsing
# ---------------------------------------------------------------------------


class TestPackageJsonParsing:
    def test_npm_deps(self, tmp_path):
        pkg = {
            "dependencies": {"lodash": "^4.17.20", "express": "~4.18.0"},
            "devDependencies": {"jest": "^29.0.0"},
        }
        _write(str(tmp_path), "package.json", json.dumps(pkg))
        scanner = VulnChainScanner(cwd=str(tmp_path))
        deps = scanner._parse_dependencies()
        assert deps["lodash"] == "4.17.20"
        assert deps["express"] == "4.18.0"
        assert deps["jest"] == "29.0.0"


# ---------------------------------------------------------------------------
# pom.xml parsing
# ---------------------------------------------------------------------------


class TestPomParsing:
    def test_maven_deps(self, tmp_path):
        pom = """<project>
  <dependencies>
    <dependency>
      <groupId>org.apache.logging.log4j</groupId>
      <artifactId>log4j-core</artifactId>
      <version>2.14.0</version>
    </dependency>
  </dependencies>
</project>"""
        _write(str(tmp_path), "pom.xml", pom)
        scanner = VulnChainScanner(cwd=str(tmp_path))
        deps = scanner._parse_dependencies()
        assert deps["log4j-core"] == "2.14.0"


# ---------------------------------------------------------------------------
# go.mod parsing
# ---------------------------------------------------------------------------


class TestGoModParsing:
    def test_go_deps(self, tmp_path):
        gomod = """module example.com/myapp

go 1.21

require (
\tgolang.org/x/crypto v0.14.0
\tgolang.org/x/net v0.15.0
)"""
        _write(str(tmp_path), "go.mod", gomod)
        scanner = VulnChainScanner(cwd=str(tmp_path))
        deps = scanner._parse_dependencies()
        assert deps["golang.org/x/crypto"] == "0.14.0"
        assert deps["golang.org/x/net"] == "0.15.0"


# ---------------------------------------------------------------------------
# Vulnerability detection
# ---------------------------------------------------------------------------


class TestVulnDetection:
    def test_vulnerable_pyyaml(self, tmp_path):
        _write(str(tmp_path), "requirements.txt", "pyyaml==5.3\n")
        scanner = VulnChainScanner(cwd=str(tmp_path))
        vulns = scanner.scan()
        assert any(v.cve == "CVE-2020-14343" for v in vulns)

    def test_safe_pyyaml(self, tmp_path):
        _write(str(tmp_path), "requirements.txt", "pyyaml==6.0.1\n")
        scanner = VulnChainScanner(cwd=str(tmp_path))
        vulns = scanner.scan()
        assert not any(v.package == "pyyaml" for v in vulns)

    def test_vulnerable_lodash(self, tmp_path):
        pkg = {"dependencies": {"lodash": "^4.17.20"}}
        _write(str(tmp_path), "package.json", json.dumps(pkg))
        scanner = VulnChainScanner(cwd=str(tmp_path))
        vulns = scanner.scan()
        assert any(v.cve == "CVE-2021-23337" for v in vulns)

    def test_log4j_from_pom(self, tmp_path):
        pom = """<project><dependencies>
        <dependency><artifactId>log4j-core</artifactId><version>2.14.0</version></dependency>
        </dependencies></project>"""
        _write(str(tmp_path), "pom.xml", pom)
        scanner = VulnChainScanner(cwd=str(tmp_path))
        vulns = scanner.scan()
        assert any(v.cve == "CVE-2021-44228" for v in vulns)

    def test_multiple_vulns_same_package(self, tmp_path):
        # requests 2.28.0 is below 2.31.0
        _write(str(tmp_path), "requirements.txt", "requests==2.28.0\n")
        scanner = VulnChainScanner(cwd=str(tmp_path))
        vulns = scanner.scan()
        assert any(v.package == "requests" for v in vulns)

    def test_sorted_by_severity(self, tmp_path):
        _write(str(tmp_path), "requirements.txt",
               "pyyaml==5.3\nrequests==2.28.0\n")
        scanner = VulnChainScanner(cwd=str(tmp_path))
        vulns = scanner.scan()
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        severities = [sev_order.get(v.severity, 9) for v in vulns]
        assert severities == sorted(severities)


# ---------------------------------------------------------------------------
# Chain tracing
# ---------------------------------------------------------------------------


class TestChainTracing:
    def test_chain_includes_project_name(self, tmp_path):
        _write(str(tmp_path), "requirements.txt", "pyyaml==5.3\n")
        scanner = VulnChainScanner(cwd=str(tmp_path))
        vulns = scanner.scan()
        for v in vulns:
            assert len(v.dep_chain) > 0
            assert "pyyaml" in v.dep_chain[0]


# ---------------------------------------------------------------------------
# Upgrade path
# ---------------------------------------------------------------------------


class TestUpgradePath:
    def test_upgrade_suggested(self, tmp_path):
        _write(str(tmp_path), "requirements.txt", "pyyaml==5.3\n")
        scanner = VulnChainScanner(cwd=str(tmp_path))
        vulns = scanner.scan()
        yaml_vulns = [v for v in vulns if v.package == "pyyaml"]
        assert yaml_vulns
        assert yaml_vulns[0].upgrade_to.startswith(">=")


# ---------------------------------------------------------------------------
# Empty / no manifest
# ---------------------------------------------------------------------------


class TestEmptyProject:
    def test_no_manifests(self, tmp_path):
        scanner = VulnChainScanner(cwd=str(tmp_path))
        vulns = scanner.scan()
        assert vulns == []

    def test_empty_requirements(self, tmp_path):
        _write(str(tmp_path), "requirements.txt", "# nothing\n")
        scanner = VulnChainScanner(cwd=str(tmp_path))
        vulns = scanner.scan()
        assert vulns == []


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


class TestFormatters:
    def test_text_report_empty(self):
        report = format_vuln_report([])
        assert "No known vulnerabilities" in report

    def test_text_report_with_findings(self):
        vulns = [
            VulnDep("lodash", "4.17.20", "CVE-2021-23337", "critical",
                     "Command injection", ["app -> lodash"], ">= 4.17.21"),
        ]
        report = format_vuln_report(vulns)
        assert "1 finding" in report
        assert "lodash" in report
        assert "CVE-2021-23337" in report

    def test_json_report_structure(self):
        vulns = [
            VulnDep("flask", "2.0.0", "CVE-X", "high", "desc",
                     ["a -> flask"], ">= 2.2.5"),
        ]
        data = vuln_report_to_json(vulns)
        assert data["total"] == 1
        assert "high" in data["by_severity"]
        assert data["vulnerabilities"][0]["cve"] == "CVE-X"

    def test_json_report_empty(self):
        data = vuln_report_to_json([])
        assert data["total"] == 0
        assert data["vulnerabilities"] == []
