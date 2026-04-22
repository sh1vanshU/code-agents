"""Tests for project_scanner.py — project type detection and scanning."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.analysis.project_scanner import ProjectInfo, scan_project, format_scan_report


# ---------------------------------------------------------------------------
# ProjectInfo dataclass
# ---------------------------------------------------------------------------


class TestProjectInfo:
    def test_defaults(self):
        info = ProjectInfo()
        assert info.language == ""
        assert info.framework == ""
        assert info.build_tool == ""
        assert info.java_version == ""
        assert info.has_docker is False
        assert info.has_git is False
        assert info.detected == []
        assert info.rest_count == 0

    def test_custom_values(self):
        info = ProjectInfo(language="Java", framework="Spring Boot", has_git=True)
        assert info.language == "Java"
        assert info.framework == "Spring Boot"
        assert info.has_git is True


# ---------------------------------------------------------------------------
# scan_project
# ---------------------------------------------------------------------------


class TestScanProjectGit:
    def test_detects_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        info = scan_project(str(tmp_path))
        assert info.has_git is True
        assert "Git repository" in info.detected

    def test_no_git(self, tmp_path):
        info = scan_project(str(tmp_path))
        assert info.has_git is False


class TestScanProjectDocker:
    def test_detects_dockerfile(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("FROM python:3.10\n")
        info = scan_project(str(tmp_path))
        assert info.has_docker is True
        assert any("Docker" in d for d in info.detected)

    def test_detects_compose(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")
        info = scan_project(str(tmp_path))
        assert info.has_docker is True


class TestScanProjectMaven:
    def test_detects_maven(self, tmp_path):
        pom_content = """<project>
            <java.version>21</java.version>
            <spring-boot.version>3.2.4</spring-boot.version>
            <dependency>jacoco</dependency>
            <dependency>flyway</dependency>
            <dependency>testcontainers</dependency>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom_content)
        info = scan_project(str(tmp_path))
        assert info.language == "Java"
        assert info.build_tool == "Maven"
        assert info.java_version == "21"
        assert "3.2.4" in info.spring_version
        assert info.has_jacoco is True
        assert info.has_flyway is True
        assert info.has_testcontainers is True
        assert info.build_cmd == "mvn clean install -DskipTests"
        assert info.test_cmd == "mvn test"

    def test_maven_spring_boot_without_version(self, tmp_path):
        pom_content = """<project>
            <dependency>spring-boot-starter</dependency>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom_content)
        info = scan_project(str(tmp_path))
        assert info.framework == "Spring Boot"
        assert any("version not parsed" in d for d in info.detected)

    def test_maven_liquibase(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project><dependency>liquibase-core</dependency></project>")
        info = scan_project(str(tmp_path))
        assert info.has_liquibase is True

    def test_maven_read_error(self, tmp_path):
        (tmp_path / "pom.xml").write_text("content")
        with patch.object(Path, "read_text", side_effect=OSError("perm denied")):
            # Should not crash, just detect Maven
            info = scan_project(str(tmp_path))
        assert info.build_tool == "Maven"


class TestScanProjectGradle:
    def test_detects_gradle(self, tmp_path):
        gradle_content = """
        plugins { id 'org.springframework.boot' }
        dependencies { implementation 'jacoco' }
        """
        (tmp_path / "build.gradle").write_text(gradle_content)
        info = scan_project(str(tmp_path))
        assert info.language == "Java"
        assert info.build_tool == "Gradle"
        assert info.framework == "Spring Boot"
        assert info.has_jacoco is True

    def test_gradle_kts(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("plugins { }")
        info = scan_project(str(tmp_path))
        assert info.build_tool == "Gradle"

    def test_gradle_skipped_when_maven_present(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project></project>")
        (tmp_path / "build.gradle").write_text("plugins { }")
        info = scan_project(str(tmp_path))
        assert info.build_tool == "Maven"


class TestScanProjectPython:
    def test_detects_pyproject_toml(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[tool.poetry]\nname = "myapp"\n')
        info = scan_project(str(tmp_path))
        assert info.language == "Python"
        assert info.build_tool == "Poetry/pip"

    def test_detects_fastapi(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('dependencies = ["fastapi"]\n')
        info = scan_project(str(tmp_path))
        assert info.framework == "FastAPI"

    def test_detects_django(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('dependencies = ["django"]\n')
        info = scan_project(str(tmp_path))
        assert info.framework == "Django"

    def test_detects_flask(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('dependencies = ["flask"]\n')
        info = scan_project(str(tmp_path))
        assert info.framework == "Flask"

    def test_detects_requirements_txt(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests\nflask\n")
        info = scan_project(str(tmp_path))
        assert info.language == "Python"
        assert info.build_tool == "pip"
        assert info.test_cmd == "pytest"

    def test_python_skipped_when_java_present(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project></project>")
        (tmp_path / "pyproject.toml").write_text('[tool.poetry]\nname = "x"\n')
        info = scan_project(str(tmp_path))
        assert info.language == "Java"


class TestScanProjectNode:
    def test_detects_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "app"}\n')
        info = scan_project(str(tmp_path))
        assert info.language == "Node.js"
        assert info.build_tool == "npm"

    def test_detects_express(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.0"}}\n')
        info = scan_project(str(tmp_path))
        assert info.framework == "Express"

    def test_detects_nextjs(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"next": "^13"}}\n')
        info = scan_project(str(tmp_path))
        assert info.framework == "Next.js"

    def test_detects_react(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"react": "^18"}}\n')
        info = scan_project(str(tmp_path))
        assert info.framework == "React"

    def test_node_skipped_when_java_present(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project></project>")
        (tmp_path / "package.json").write_text('{"name": "app"}\n')
        info = scan_project(str(tmp_path))
        assert info.language == "Java"


class TestScanProjectGo:
    def test_detects_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/myapp\n")
        info = scan_project(str(tmp_path))
        assert info.language == "Go"
        assert info.build_tool == "go"
        assert info.test_cmd == "go test -cover ./..."

    def test_go_skipped_when_python_present(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[tool.poetry]\nname = "x"\n')
        (tmp_path / "go.mod").write_text("module x\n")
        info = scan_project(str(tmp_path))
        assert info.language == "Python"


class TestScanProjectEndpoints:
    def test_endpoint_scan_success(self, tmp_path):
        mock_result = MagicMock()
        mock_result.rest_endpoints = [MagicMock() for _ in range(5)]
        mock_result.grpc_services = []
        mock_result.kafka_listeners = [MagicMock()]
        mock_result.db_queries = []
        with patch("code_agents.cicd.endpoint_scanner.scan_all", return_value=mock_result):
            info = scan_project(str(tmp_path))
        assert info.rest_count == 5
        assert info.kafka_count == 1

    def test_endpoint_scan_failure(self, tmp_path):
        with patch("code_agents.cicd.endpoint_scanner.scan_all", side_effect=Exception("fail")):
            info = scan_project(str(tmp_path))
        assert info.rest_count == 0


# ---------------------------------------------------------------------------
# format_scan_report
# ---------------------------------------------------------------------------


class TestFormatScanReport:
    def test_empty_detected(self):
        info = ProjectInfo()
        result = format_scan_report(info)
        assert "No project files detected" in result

    def test_with_detections(self):
        info = ProjectInfo(detected=["Git repository", "Python (pyproject.toml)", "FastAPI"])
        result = format_scan_report(info)
        assert "Git repository" in result
        assert "FastAPI" in result
        assert "\u2713" in result  # checkmark

    def test_single_detection(self):
        info = ProjectInfo(detected=["Docker (Dockerfile)"])
        result = format_scan_report(info)
        assert "Docker" in result
