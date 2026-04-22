"""
Project Scanner — auto-detect project type, build tools, frameworks, and config.

Scans the repo to pre-fill defaults for code-agents init.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.analysis.project_scanner")


@dataclass
class ProjectInfo:
    """Detected project information."""
    language: str = ""          # Java, Python, Node, Go, Rust
    framework: str = ""         # Spring Boot, Django, Express, etc.
    build_tool: str = ""        # Maven, Gradle, npm, pip, go
    java_version: str = ""      # 17, 21, etc.
    spring_version: str = ""    # 3.2.4, etc.
    build_cmd: str = ""         # mvn clean install, gradle build, etc.
    test_cmd: str = ""          # mvn test, pytest, npm test, etc.
    has_docker: bool = False
    has_flyway: bool = False
    has_liquibase: bool = False
    has_jacoco: bool = False
    has_testcontainers: bool = False
    has_git: bool = False
    rest_count: int = 0
    grpc_count: int = 0
    kafka_count: int = 0
    db_query_count: int = 0
    detected: list[str] = field(default_factory=list)  # human-readable detections


def scan_project(repo_path: str) -> ProjectInfo:
    """Scan a repository and detect project type, tools, and frameworks."""
    logger.info("Scanning project at %s", repo_path)
    repo = Path(repo_path)
    info = ProjectInfo()

    # Git
    if (repo / ".git").is_dir():
        info.has_git = True
        info.detected.append("Git repository")

    # Docker
    for df in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]:
        if (repo / df).is_file():
            info.has_docker = True
            info.detected.append(f"Docker ({df})")
            break

    # === Java / Maven ===
    pom = repo / "pom.xml"
    if pom.is_file():
        info.language = "Java"
        info.build_tool = "Maven"
        info.build_cmd = "mvn clean install -DskipTests"
        info.test_cmd = "mvn test"
        info.detected.append("Maven (pom.xml)")

        try:
            pom_content = pom.read_text(encoding="utf-8", errors="ignore")

            # Java version
            java_match = re.search(r"<java\.version>(\d+)</java\.version>", pom_content)
            if not java_match:
                java_match = re.search(r"<maven\.compiler\.source>(\d+)", pom_content)
            if java_match:
                info.java_version = java_match.group(1)
                info.detected.append(f"Java {info.java_version}")

            # Spring Boot version
            spring_match = re.search(r"<version>(\d+\.\d+\.\d+)</version>.*spring-boot", pom_content, re.DOTALL)
            if not spring_match:
                spring_match = re.search(r"spring-boot.*<version>(\d+\.\d+\.\d+)", pom_content, re.DOTALL)
            if not spring_match:
                spring_match = re.search(r"<spring-boot\.version>(\d+\.\d+\.\d+)", pom_content)
            if spring_match:
                info.framework = f"Spring Boot {spring_match.group(1)}"
                info.spring_version = spring_match.group(1)
                info.detected.append(info.framework)
            elif "spring-boot" in pom_content.lower():
                info.framework = "Spring Boot"
                info.detected.append("Spring Boot (version not parsed)")

            # JaCoCo
            if "jacoco" in pom_content.lower():
                info.has_jacoco = True
                info.detected.append("JaCoCo coverage plugin")

            # Flyway
            if "flyway" in pom_content.lower():
                info.has_flyway = True
                info.detected.append("Flyway migrations")

            # Liquibase
            if "liquibase" in pom_content.lower():
                info.has_liquibase = True
                info.detected.append("Liquibase migrations")

            # Testcontainers
            if "testcontainers" in pom_content.lower():
                info.has_testcontainers = True
                info.detected.append("Testcontainers")

        except OSError as e:
            logger.debug("Project scan step skipped: %s", e)

    # === Java / Gradle ===
    for gradle_file in ["build.gradle", "build.gradle.kts"]:
        gf = repo / gradle_file
        if gf.is_file() and not info.build_tool:
            info.language = "Java"
            info.build_tool = "Gradle"
            info.build_cmd = "./gradlew clean build -x test"
            info.test_cmd = "./gradlew test"
            info.detected.append(f"Gradle ({gradle_file})")
            try:
                gc = gf.read_text(encoding="utf-8", errors="ignore")
                if "spring-boot" in gc.lower() or "org.springframework.boot" in gc:
                    info.framework = "Spring Boot"
                    info.detected.append("Spring Boot")
                if "jacoco" in gc.lower():
                    info.has_jacoco = True
                    info.detected.append("JaCoCo coverage")
            except OSError as e:
                logger.debug("Project scan step skipped: %s", e)

    # === Python ===
    if (repo / "pyproject.toml").is_file() and not info.language:
        info.language = "Python"
        info.build_tool = "Poetry/pip"
        info.build_cmd = "poetry install"
        info.test_cmd = "poetry run pytest --cov --cov-report=xml"
        info.detected.append("Python (pyproject.toml)")
        try:
            pyp = (repo / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
            if "fastapi" in pyp.lower():
                info.framework = "FastAPI"
                info.detected.append("FastAPI")
            elif "django" in pyp.lower():
                info.framework = "Django"
                info.detected.append("Django")
            elif "flask" in pyp.lower():
                info.framework = "Flask"
                info.detected.append("Flask")
        except OSError as e:
            logger.debug("Project scan step skipped: %s", e)
    elif (repo / "requirements.txt").is_file() and not info.language:
        info.language = "Python"
        info.build_tool = "pip"
        info.build_cmd = "pip install -r requirements.txt"
        info.test_cmd = "pytest"
        info.detected.append("Python (requirements.txt)")

    # === Node.js ===
    pkg = repo / "package.json"
    if pkg.is_file() and not info.language:
        info.language = "Node.js"
        info.build_tool = "npm"
        info.build_cmd = "npm run build"
        info.test_cmd = "npm test"
        info.detected.append("Node.js (package.json)")
        try:
            pc = pkg.read_text(encoding="utf-8", errors="ignore")
            if "express" in pc.lower():
                info.framework = "Express"
                info.detected.append("Express")
            elif "next" in pc.lower():
                info.framework = "Next.js"
                info.detected.append("Next.js")
            elif "react" in pc.lower():
                info.framework = "React"
                info.detected.append("React")
        except OSError as e:
            logger.debug("Project scan step skipped: %s", e)

    # === Go ===
    if (repo / "go.mod").is_file() and not info.language:
        info.language = "Go"
        info.build_tool = "go"
        info.build_cmd = "go build ./..."
        info.test_cmd = "go test -cover ./..."
        info.detected.append("Go (go.mod)")

    # === Endpoint counts (quick scan) ===
    try:
        from code_agents.cicd.endpoint_scanner import scan_all
        result = scan_all(repo_path)
        info.rest_count = len(result.rest_endpoints)
        info.grpc_count = sum(len(s.methods) for s in result.grpc_services)
        info.kafka_count = len(result.kafka_listeners)
        info.db_query_count = len(result.db_queries)
        if info.rest_count:
            info.detected.append(f"{info.rest_count} REST endpoints")
        if info.grpc_count:
            info.detected.append(f"{info.grpc_count} gRPC methods")
        if info.kafka_count:
            info.detected.append(f"{info.kafka_count} Kafka listeners")
        if info.db_query_count:
            info.detected.append(f"{info.db_query_count} DB queries")
    except Exception as e:
        logger.debug("Project scan step skipped: %s", e)

    logger.info("Scan complete: %d detections (%s)", len(info.detected), info.language or "unknown language")
    return info


def format_scan_report(info: ProjectInfo) -> str:
    """Format project scan results for display."""
    if not info.detected:
        return "  No project files detected."

    lines = []
    for item in info.detected:
        lines.append(f"  \u2713 {item}")
    return "\n".join(lines)
