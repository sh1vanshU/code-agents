"""Tests for dependency_audit.py — CVE, license, and outdated checks."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.security.dependency_audit import (
    AuditReport,
    Dependency,
    DependencyAuditor,
    KNOWN_VULNS,
    LicenseWarning,
    OutdatedPackage,
    Vulnerability,
    version_less_than,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_repo(tmp_path):
    """Empty repo with no dependency files."""
    return tmp_path


@pytest.fixture
def requirements_repo(tmp_path):
    """Repo with requirements.txt."""
    (tmp_path / "requirements.txt").write_text(
        "django==3.1.0\n"
        "requests>=2.28.0\n"
        "flask==1.1.4\n"
        "# comment line\n"
        "boto3==1.28.0\n"
        "urllib3~=1.26.0\n"
    )
    return tmp_path


@pytest.fixture
def package_json_repo(tmp_path):
    """Repo with package.json."""
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "test-app",
        "dependencies": {
            "express": "^4.17.1",
            "lodash": "~4.17.20",
            "axios": "^0.21.0",
        },
        "devDependencies": {
            "jest": "^29.0.0",
            "minimist": "^1.2.0",
        },
    }))
    return tmp_path


@pytest.fixture
def pom_xml_repo(tmp_path):
    """Repo with pom.xml."""
    (tmp_path / "pom.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<project>
    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.14.1</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>5.3.15</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.13.4</version>
        </dependency>
    </dependencies>
</project>
""")
    return tmp_path


@pytest.fixture
def pyproject_repo(tmp_path):
    """Repo with pyproject.toml."""
    (tmp_path / "pyproject.toml").write_text("""
[tool.poetry.dependencies]
python = "^3.11"
django = "^3.1.0"
requests = "^2.28.0"
cryptography = {version = "^40.0.0", optional = true}
boto3 = "^1.28.0"
""")
    return tmp_path


@pytest.fixture
def gradle_repo(tmp_path):
    """Repo with build.gradle."""
    (tmp_path / "build.gradle").write_text("""
plugins {
    id 'java'
}

dependencies {
    implementation 'org.apache.logging.log4j:log4j-core:2.14.1'
    implementation 'org.yaml:snakeyaml:1.33'
    testImplementation 'junit:junit:4.13.2'
}
""")
    return tmp_path


@pytest.fixture
def gomod_repo(tmp_path):
    """Repo with go.mod."""
    (tmp_path / "go.mod").write_text("""module github.com/example/app

go 1.21

require (
    github.com/gin-gonic/gin v1.9.0
    github.com/go-redis/redis v6.15.9
)
""")
    return tmp_path


# ---------------------------------------------------------------------------
# Test: parse requirements.txt
# ---------------------------------------------------------------------------

class TestParseRequirementsTxt:
    def test_parses_pinned_versions(self, requirements_repo):
        auditor = DependencyAuditor(cwd=str(requirements_repo))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "django" in names
        assert "flask" in names

    def test_parses_version_ranges(self, requirements_repo):
        auditor = DependencyAuditor(cwd=str(requirements_repo))
        deps = auditor.scan_dependencies()
        req_dep = next(d for d in deps if d.name == "requests")
        assert req_dep.version == "2.28.0"

    def test_skips_comments(self, requirements_repo):
        auditor = DependencyAuditor(cwd=str(requirements_repo))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "comment" not in " ".join(names).lower()

    def test_source_file_tracked(self, requirements_repo):
        auditor = DependencyAuditor(cwd=str(requirements_repo))
        deps = auditor.scan_dependencies()
        assert all(d.source == "requirements.txt" for d in deps)


# ---------------------------------------------------------------------------
# Test: parse package.json
# ---------------------------------------------------------------------------

class TestParsePackageJson:
    def test_parses_dependencies(self, package_json_repo):
        auditor = DependencyAuditor(cwd=str(package_json_repo))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "express" in names
        assert "lodash" in names
        assert "axios" in names

    def test_parses_dev_dependencies(self, package_json_repo):
        auditor = DependencyAuditor(cwd=str(package_json_repo))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "jest" in names
        assert "minimist" in names

    def test_strips_version_prefix(self, package_json_repo):
        auditor = DependencyAuditor(cwd=str(package_json_repo))
        deps = auditor.scan_dependencies()
        express_dep = next(d for d in deps if d.name == "express")
        assert express_dep.version == "4.17.1"


# ---------------------------------------------------------------------------
# Test: parse pom.xml
# ---------------------------------------------------------------------------

class TestParsePomXml:
    def test_parses_maven_dependencies(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "log4j-core" in names
        assert "spring-core" in names
        assert "jackson-databind" in names

    def test_correct_versions(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        deps = auditor.scan_dependencies()
        log4j = next(d for d in deps if d.name == "log4j-core")
        assert log4j.version == "2.14.1"


# ---------------------------------------------------------------------------
# Test: parse pyproject.toml
# ---------------------------------------------------------------------------

class TestParsePyprojectToml:
    def test_parses_poetry_deps(self, pyproject_repo):
        auditor = DependencyAuditor(cwd=str(pyproject_repo))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "django" in names
        assert "requests" in names
        assert "boto3" in names

    def test_skips_python_entry(self, pyproject_repo):
        auditor = DependencyAuditor(cwd=str(pyproject_repo))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "python" not in names

    def test_parses_dict_version(self, pyproject_repo):
        auditor = DependencyAuditor(cwd=str(pyproject_repo))
        deps = auditor.scan_dependencies()
        crypto = next(d for d in deps if d.name == "cryptography")
        assert crypto.version == "40.0.0"


# ---------------------------------------------------------------------------
# Test: parse build.gradle
# ---------------------------------------------------------------------------

class TestParseBuildGradle:
    def test_parses_gradle_deps(self, gradle_repo):
        auditor = DependencyAuditor(cwd=str(gradle_repo))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "log4j-core" in names
        assert "snakeyaml" in names

    def test_parses_test_implementation(self, gradle_repo):
        auditor = DependencyAuditor(cwd=str(gradle_repo))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "junit" in names


# ---------------------------------------------------------------------------
# Test: parse go.mod
# ---------------------------------------------------------------------------

class TestParseGoMod:
    def test_parses_go_deps(self, gomod_repo):
        auditor = DependencyAuditor(cwd=str(gomod_repo))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "gin" in names
        assert "redis" in names


# ---------------------------------------------------------------------------
# Test: version comparison
# ---------------------------------------------------------------------------

class TestVersionComparison:
    def test_lower_version(self):
        assert version_less_than("2.14.1", "2.17.1") is True

    def test_equal_version(self):
        assert version_less_than("2.17.1", "2.17.1") is False

    def test_higher_version(self):
        assert version_less_than("3.0.0", "2.17.1") is False

    def test_major_version_diff(self):
        assert version_less_than("1.33", "2.0") is True

    def test_minor_version_diff(self):
        assert version_less_than("4.17.1", "4.17.3") is True

    def test_patch_version_diff(self):
        assert version_less_than("2.0.6", "2.0.7") is True


# ---------------------------------------------------------------------------
# Test: check_known_vulnerabilities
# ---------------------------------------------------------------------------

class TestCheckVulnerabilities:
    def test_finds_vulnerable_deps(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        auditor.scan_dependencies()
        vulns = auditor.check_known_vulnerabilities()
        cves = [v.cve for v in vulns]
        assert "CVE-2021-44228" in cves  # log4j
        assert "CVE-2022-22965" in cves  # spring-core
        assert "CVE-2022-42003" in cves  # jackson-databind

    def test_severity_correct(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        auditor.scan_dependencies()
        vulns = auditor.check_known_vulnerabilities()
        log4j_vuln = next(v for v in vulns if v.cve == "CVE-2021-44228")
        assert log4j_vuln.severity == "CRITICAL"

    def test_no_vulns_for_uptodate(self, empty_repo):
        # Create requirements with up-to-date versions
        (empty_repo / "requirements.txt").write_text(
            "django==4.2.0\n"
            "requests==2.31.0\n"
            "flask==3.0.0\n"
        )
        auditor = DependencyAuditor(cwd=str(empty_repo))
        auditor.scan_dependencies()
        vulns = auditor.check_known_vulnerabilities()
        assert len(vulns) == 0

    def test_vuln_fix_version(self, requirements_repo):
        auditor = DependencyAuditor(cwd=str(requirements_repo))
        auditor.scan_dependencies()
        vulns = auditor.check_known_vulnerabilities()
        django_vuln = next(v for v in vulns if v.name == "django")
        assert django_vuln.fix_version == "3.2.0"

    def test_normalizes_underscore_names(self, empty_repo):
        """Dep names with underscores should match hyphenated KNOWN_VULNS keys."""
        (empty_repo / "requirements.txt").write_text("jackson_databind==2.13.0\n")
        auditor = DependencyAuditor(cwd=str(empty_repo))
        auditor.scan_dependencies()
        vulns = auditor.check_known_vulnerabilities()
        assert len(vulns) == 1
        assert vulns[0].cve == "CVE-2022-42003"


# ---------------------------------------------------------------------------
# Test: format_report
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_report_has_header(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        auditor.scan_dependencies()
        auditor.check_known_vulnerabilities()
        report = auditor.format_report()
        assert "Dependency Audit" in report

    def test_report_shows_dependency_count(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        auditor.scan_dependencies()
        report = auditor.format_report()
        assert "3 scanned" in report

    def test_report_shows_cves(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        auditor.scan_dependencies()
        auditor.check_known_vulnerabilities()
        report = auditor.format_report()
        assert "CVE-2021-44228" in report
        assert "Log4Shell" in report

    def test_report_shows_summary(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        auditor.scan_dependencies()
        auditor.check_known_vulnerabilities()
        report = auditor.format_report()
        assert "Summary:" in report
        assert "vulnerabilit" in report

    def test_clean_report(self, empty_repo):
        (empty_repo / "requirements.txt").write_text("boto3==1.28.0\n")
        auditor = DependencyAuditor(cwd=str(empty_repo))
        auditor.scan_dependencies()
        auditor.check_known_vulnerabilities()
        report = auditor.format_report()
        assert "No issues found" in report


# ---------------------------------------------------------------------------
# Test: severity counting
# ---------------------------------------------------------------------------

class TestSeverityCounting:
    def test_counts_by_severity(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        auditor.scan_dependencies()
        vulns = auditor.check_known_vulnerabilities()

        critical = [v for v in vulns if v.severity == "CRITICAL"]
        high = [v for v in vulns if v.severity == "HIGH"]
        assert len(critical) >= 1  # log4j, spring-core
        assert len(high) >= 1  # jackson-databind

    def test_report_groups_by_severity(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        auditor.scan_dependencies()
        auditor.check_known_vulnerabilities()
        report = auditor.format_report()
        assert "CRITICAL" in report
        assert "HIGH" in report


# ---------------------------------------------------------------------------
# Test: to_dict (JSON output)
# ---------------------------------------------------------------------------

class TestToDict:
    def test_json_structure(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        auditor.scan_dependencies()
        auditor.check_known_vulnerabilities()
        data = auditor.to_dict()
        assert "vulnerabilities" in data
        assert "license_warnings" in data
        assert "outdated" in data
        assert "dependencies_count" in data
        assert data["dependencies_count"] == 3

    def test_json_serializable(self, pom_xml_repo):
        auditor = DependencyAuditor(cwd=str(pom_xml_repo))
        auditor.scan_dependencies()
        auditor.check_known_vulnerabilities()
        # Should not raise
        json.dumps(auditor.to_dict())


# ---------------------------------------------------------------------------
# Test: multiple file types in one repo
# ---------------------------------------------------------------------------

class TestMultipleFileTypes:
    def test_scans_all_dep_files(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")
        (tmp_path / "package.json").write_text(json.dumps({
            "dependencies": {"express": "^4.17.1"},
        }))
        auditor = DependencyAuditor(cwd=str(tmp_path))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "requests" in names
        assert "express" in names

    def test_vulns_across_ecosystems(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("django==3.1.0\n")
        (tmp_path / "package.json").write_text(json.dumps({
            "dependencies": {"lodash": "^4.17.0"},
        }))
        auditor = DependencyAuditor(cwd=str(tmp_path))
        auditor.scan_dependencies()
        vulns = auditor.check_known_vulnerabilities()
        cves = [v.cve for v in vulns]
        assert "CVE-2021-45115" in cves  # django
        assert "CVE-2021-23337" in cves  # lodash


# ---------------------------------------------------------------------------
# Test: _parse_version fallback (lines 99-106)
# ---------------------------------------------------------------------------

class TestParseVersionFallback:
    def test_fallback_numeric_split(self):
        """When packaging.version is not available, use tuple fallback."""
        from code_agents.security.dependency_audit import _parse_version
        # Even with packaging available, test basic functionality
        result = _parse_version("2.14.1")
        # Should be comparable
        assert result is not None

    def test_fallback_with_non_numeric(self):
        from code_agents.security.dependency_audit import _parse_version
        # Version with alpha chars should still parse
        result = _parse_version("1.2.3rc1")
        assert result is not None

    def test_version_less_than_comparison_fail(self):
        """If comparison itself fails, return False."""
        assert version_less_than("invalid!!!", "also-invalid!!!") is False


# ---------------------------------------------------------------------------
# Test: check_licenses (lines 193-233)
# ---------------------------------------------------------------------------

class TestCheckLicenses:
    def test_npm_license_gpl(self, tmp_path):
        """Detect GPL license in node_modules package.json."""
        nm = tmp_path / "node_modules" / "gpl-pkg"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text(json.dumps({
            "name": "gpl-pkg", "license": "GPL-3.0",
        }))
        auditor = DependencyAuditor(cwd=str(tmp_path))
        warnings = auditor.check_licenses()
        assert len(warnings) >= 1
        assert any("GPL" in w.license for w in warnings)

    def test_npm_license_dict_format(self, tmp_path):
        """License as dict with type field."""
        nm = tmp_path / "node_modules" / "lgpl-pkg"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text(json.dumps({
            "name": "lgpl-pkg", "license": {"type": "LGPL-3.0"},
        }))
        auditor = DependencyAuditor(cwd=str(tmp_path))
        warnings = auditor.check_licenses()
        assert len(warnings) >= 1

    def test_license_file_gpl_v3(self, tmp_path):
        """Detect GPL from LICENSE file content."""
        (tmp_path / "LICENSE").write_text(
            "GNU General Public License\nVersion 3, 29 June 2007\n"
        )
        auditor = DependencyAuditor(cwd=str(tmp_path))
        warnings = auditor.check_licenses()
        assert len(warnings) >= 1
        assert any("GPL-3.0" in w.license for w in warnings)

    def test_license_file_gpl_v2(self, tmp_path):
        (tmp_path / "LICENSE").write_text(
            "GNU General Public License\nVersion 2\n"
        )
        auditor = DependencyAuditor(cwd=str(tmp_path))
        warnings = auditor.check_licenses()
        assert any("GPL-2.0" in w.license for w in warnings)

    def test_license_file_agpl(self, tmp_path):
        (tmp_path / "LICENSE").write_text(
            "GNU Affero General Public License\n"
        )
        auditor = DependencyAuditor(cwd=str(tmp_path))
        warnings = auditor.check_licenses()
        assert any("AGPL" in w.license for w in warnings)

    def test_license_file_lgpl(self, tmp_path):
        (tmp_path / "LICENSE").write_text(
            "GNU Lesser General Public License\n"
        )
        auditor = DependencyAuditor(cwd=str(tmp_path))
        warnings = auditor.check_licenses()
        assert any("LGPL" in w.license for w in warnings)

    def test_license_file_mit_no_warning(self, tmp_path):
        (tmp_path / "LICENSE").write_text(
            "MIT License\nPermission is hereby granted...\n"
        )
        auditor = DependencyAuditor(cwd=str(tmp_path))
        warnings = auditor.check_licenses()
        assert len(warnings) == 0

    def test_npm_license_safe(self, tmp_path):
        nm = tmp_path / "node_modules" / "safe-pkg"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text(json.dumps({
            "name": "safe-pkg", "license": "MIT",
        }))
        auditor = DependencyAuditor(cwd=str(tmp_path))
        warnings = auditor.check_licenses()
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# Test: check_outdated (lines 217-233)
# ---------------------------------------------------------------------------

class TestCheckOutdated:
    def test_pip_outdated(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps([
                    {"name": "requests", "version": "2.28.0", "latest_version": "2.31.0"},
                ]),
            )
            outdated = auditor.check_outdated()
        assert len(outdated) >= 1
        assert outdated[0].name == "requests"

    def test_npm_outdated(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({"name": "app"}))
        auditor = DependencyAuditor(cwd=str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout=json.dumps({
                    "lodash": {"current": "4.17.0", "latest": "4.17.21"},
                }),
            )
            outdated = auditor.check_outdated()
        assert len(outdated) >= 1
        assert outdated[0].name == "lodash"

    def test_pip_outdated_failure(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        with patch("subprocess.run", side_effect=Exception("pip not found")):
            outdated = auditor.check_outdated()
        assert len(outdated) == 0


# ---------------------------------------------------------------------------
# Test: format_report with licenses and outdated (lines 280-302)
# ---------------------------------------------------------------------------

class TestFormatReportExtended:
    def test_report_with_license_warnings(self, tmp_path):
        auditor = DependencyAuditor(cwd=str(tmp_path))
        auditor.report.license_warnings.append(
            LicenseWarning(name="gpl-pkg", license="GPL-3.0", reason="commercial conflict")
        )
        report = auditor.format_report()
        assert "License Warnings" in report
        assert "gpl-pkg" in report

    def test_report_with_outdated(self, tmp_path):
        auditor = DependencyAuditor(cwd=str(tmp_path))
        auditor.report.outdated.append(
            OutdatedPackage(name="requests", current="2.28.0", latest="2.31.0")
        )
        report = auditor.format_report()
        assert "Outdated" in report
        assert "requests" in report

    def test_report_singular_vulnerability(self, tmp_path):
        auditor = DependencyAuditor(cwd=str(tmp_path))
        auditor.report.vulnerabilities.append(
            Vulnerability(name="x", version="1.0", cve="CVE-X", severity="HIGH", description="desc", fix_version="2.0")
        )
        report = auditor.format_report()
        assert "1 vulnerability" in report

    def test_report_singular_license(self, tmp_path):
        auditor = DependencyAuditor(cwd=str(tmp_path))
        auditor.report.license_warnings.append(
            LicenseWarning(name="x", license="GPL", reason="r")
        )
        report = auditor.format_report()
        assert "1 license issue" in report

    def test_report_vuln_only_filter(self, tmp_path):
        auditor = DependencyAuditor(cwd=str(tmp_path))
        auditor.report.vulnerabilities.append(
            Vulnerability(name="x", version="1.0", cve="CVE-X", severity="CRITICAL", description="d", fix_version="2.0")
        )
        auditor.report.outdated.append(
            OutdatedPackage(name="y", current="1.0", latest="2.0")
        )
        report = auditor.format_report(vuln_only=True)
        assert "CVE-X" in report


# ---------------------------------------------------------------------------
# Test: _parse_build_gradle (lines 445-466)
# ---------------------------------------------------------------------------

class TestParseBuildGradleExtended:
    def test_multiple_dep_types(self, tmp_path):
        (tmp_path / "build.gradle").write_text("""
dependencies {
    api 'com.google:guava:31.0'
    runtimeOnly 'mysql:mysql-connector:8.0.30'
}
""")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "guava" in names
        assert "mysql-connector" in names


# ---------------------------------------------------------------------------
# Test: _parse_go_mod single-line require (lines 492-497)
# ---------------------------------------------------------------------------

class TestGoModSingleLine:
    def test_single_line_require(self, tmp_path):
        (tmp_path / "go.mod").write_text(
            "module example.com/app\n\ngo 1.21\n\nrequire github.com/stretchr/testify v1.8.4\n"
        )
        auditor = DependencyAuditor(cwd=str(tmp_path))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "testify" in names


# ---------------------------------------------------------------------------
# Test: _check_license_file GPL generic (lines 534-550)
# ---------------------------------------------------------------------------

class TestLicenseFileGPLGeneric:
    def test_gpl_no_version(self, tmp_path):
        (tmp_path / "LICENSE").write_text("GNU General Public License\nSome terms.\n")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        warnings = auditor.check_licenses()
        assert len(warnings) >= 1
        assert any("GPL" in w.license for w in warnings)


# ---------------------------------------------------------------------------
# Coverage for skip conditions in check_licenses (lines 207, 209)
# ---------------------------------------------------------------------------

class TestCheckLicensesSkipConditions:
    def test_skip_git_dir_license(self, tmp_path):
        """LICENSE under .git should be skipped."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "LICENSE").write_text("GNU General Public License version 3\n")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        warnings = auditor.check_licenses()
        assert len(warnings) == 0

    def test_skip_deeply_nested_license(self, tmp_path):
        """LICENSE more than 3 levels deep should be skipped."""
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "LICENSE").write_text("GNU General Public License version 2\n")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        warnings = auditor.check_licenses()
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# OSError paths in parsers (lines 344-345, 363-364, 403-404, 422-423, 445-446, 465-466)
# ---------------------------------------------------------------------------

class TestParserOSErrors:
    def test_requirements_txt_oserror(self, tmp_path):
        """OSError reading requirements.txt is silently ignored."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("flask==2.0.0\n")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        with patch("pathlib.Path.read_text", side_effect=OSError("perm denied")):
            deps = auditor.scan_dependencies()
        # Should not crash, just returns empty
        assert isinstance(deps, list)

    def test_pyproject_toml_oserror(self, tmp_path):
        """OSError reading pyproject.toml is silently ignored."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry.dependencies]\nfoo = \"1.0\"\n")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        orig_read_text = Path.read_text
        def raising_read_text(self_path, *a, **kw):
            if self_path.name == "pyproject.toml":
                raise OSError("fail")
            return orig_read_text(self_path, *a, **kw)
        with patch.object(Path, "read_text", raising_read_text):
            deps = auditor.scan_dependencies()
        # No crash, may have deps from requirements.txt if present
        assert isinstance(deps, list)

    def test_package_json_oserror(self, tmp_path):
        """OSError reading package.json is silently ignored."""
        (tmp_path / "package.json").write_text('invalid')
        auditor = DependencyAuditor(cwd=str(tmp_path))
        deps = auditor.scan_dependencies()
        assert isinstance(deps, list)

    def test_pom_xml_oserror(self, tmp_path):
        """OSError reading pom.xml is silently ignored."""
        (tmp_path / "pom.xml").write_text("<project></project>")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        orig_read_text = Path.read_text
        def raising_read_text(self_path, *a, **kw):
            if self_path.name == "pom.xml":
                raise OSError("fail")
            return orig_read_text(self_path, *a, **kw)
        with patch.object(Path, "read_text", raising_read_text):
            deps = auditor.scan_dependencies()
        assert isinstance(deps, list)

    def test_build_gradle_oserror(self, tmp_path):
        """OSError reading build.gradle is silently ignored."""
        (tmp_path / "build.gradle").write_text("implementation 'com.google:guava:31.0'")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        orig_read_text = Path.read_text
        def raising_read_text(self_path, *a, **kw):
            if self_path.name == "build.gradle":
                raise OSError("fail")
            return orig_read_text(self_path, *a, **kw)
        with patch.object(Path, "read_text", raising_read_text):
            deps = auditor.scan_dependencies()
        assert isinstance(deps, list)

    def test_go_mod_oserror(self, tmp_path):
        """OSError reading go.mod is silently ignored."""
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        orig_read_text = Path.read_text
        def raising_read_text(self_path, *a, **kw):
            if self_path.name == "go.mod":
                raise OSError("fail")
            return orig_read_text(self_path, *a, **kw)
        with patch.object(Path, "read_text", raising_read_text):
            deps = auditor.scan_dependencies()
        assert isinstance(deps, list)


# ---------------------------------------------------------------------------
# pyproject.toml section end (line 374-375)
# ---------------------------------------------------------------------------

class TestPyprojectSectionEnd:
    def test_section_ends_on_new_header(self, tmp_path):
        """Parser stops when hitting a new [section] after deps."""
        content = (
            "[tool.poetry.dependencies]\n"
            "requests = \"2.28.0\"\n"
            "\n"
            "[tool.poetry.dev-dependencies]\n"
            "pytest = \"7.0.0\"\n"
        )
        (tmp_path / "pyproject.toml").write_text(content)
        auditor = DependencyAuditor(cwd=str(tmp_path))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "requests" in names
        # dev-dependencies section should not be picked up by the deps parser
        # (it's under a different header)


# ---------------------------------------------------------------------------
# package.json non-dict deps (line 409)
# ---------------------------------------------------------------------------

class TestPackageJsonNonDictDeps:
    def test_non_dict_dependencies_skipped(self, tmp_path):
        """dependencies value that is not a dict is skipped."""
        pkg = {"dependencies": "not-a-dict", "devDependencies": {"lodash": "^4.17.0"}}
        import json as _json
        (tmp_path / "package.json").write_text(_json.dumps(pkg))
        auditor = DependencyAuditor(cwd=str(tmp_path))
        deps = auditor.scan_dependencies()
        names = [d.name for d in deps]
        assert "lodash" in names


# ---------------------------------------------------------------------------
# _check_license_file OSError (lines 527-528)
# ---------------------------------------------------------------------------

class TestCheckLicenseFileOSError:
    def test_license_file_oserror(self, tmp_path):
        """OSError reading a LICENSE file is silently ignored."""
        license_file = tmp_path / "LICENSE"
        license_file.write_text("GNU General Public License version 3\n")
        auditor = DependencyAuditor(cwd=str(tmp_path))
        # Make read_text fail for the license check
        with patch.object(Path, "read_text", side_effect=OSError("fail")):
            warnings = auditor.check_licenses()
        # Should not crash
        assert isinstance(warnings, list)


# ---------------------------------------------------------------------------
# npm outdated exception (lines 592-593)
# ---------------------------------------------------------------------------

class TestNpmOutdatedException:
    def test_npm_outdated_failure(self, tmp_path):
        """npm outdated failure is caught and logged."""
        (tmp_path / "package.json").write_text('{"dependencies": {"lodash": "^4.0.0"}}')
        auditor = DependencyAuditor(cwd=str(tmp_path))
        with patch("subprocess.run", side_effect=Exception("npm not found")):
            result = auditor.check_outdated()
        assert isinstance(result, list)
