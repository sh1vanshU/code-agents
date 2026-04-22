"""Tests for onboarding.py — repo scan and onboarding guide generation."""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.tools.onboarding import (
    OnboardingGenerator,
    ProjectProfile,
    generate_onboarding_doc,
    format_onboarding_terminal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file(tmp_path: Path, name: str, content: str = ""):
    """Create a file inside tmp_path, creating parent dirs as needed."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _make_dir(tmp_path: Path, name: str):
    """Create a directory inside tmp_path."""
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return d


# ===========================================================================
# _detect_stack
# ===========================================================================


class TestDetectStack:
    """Test language/framework/build tool detection."""

    def test_python_poetry_fastapi(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "[tool.poetry]\nname = 'myapp'\nfastapi = '^0.100'")
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.language == "Python"
        assert gen.profile.build_tool == "Poetry"
        assert gen.profile.framework == "FastAPI"
        assert gen.profile.test_framework == "pytest"

    def test_python_poetry_django(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "[tool.poetry]\ndjango = '^4.0'")
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.framework == "Django"

    def test_python_poetry_flask(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "[tool.poetry]\nflask = '^3.0'")
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.framework == "Flask"

    def test_python_poetry_no_framework(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "[tool.poetry]\nname = 'cli-tool'")
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.language == "Python"
        assert gen.profile.framework == ""

    def test_java_maven_spring_boot(self, tmp_path):
        pom = "<project><artifactId>spring-boot-starter</artifactId><artifactId>junit-jupiter</artifactId></project>"
        _make_file(tmp_path, "pom.xml", pom)
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.language == "Java"
        assert gen.profile.build_tool == "Maven"
        assert gen.profile.framework == "Spring Boot"
        assert gen.profile.test_framework == "JUnit 5"

    def test_java_maven_spring(self, tmp_path):
        pom = "<project><artifactId>spring-context</artifactId><artifactId>junit</artifactId></project>"
        _make_file(tmp_path, "pom.xml", pom)
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.framework == "Spring"
        assert gen.profile.test_framework == "JUnit 4"

    def test_java_gradle(self, tmp_path):
        _make_file(tmp_path, "build.gradle", "apply plugin: 'java'")
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.language == "Java/Kotlin"
        assert gen.profile.build_tool == "Gradle"

    def test_javascript_npm_react(self, tmp_path):
        pkg = {"dependencies": {"react": "^18.0"}, "devDependencies": {"jest": "^29"}}
        _make_file(tmp_path, "package.json", json.dumps(pkg))
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.language == "JavaScript/TypeScript"
        assert gen.profile.build_tool == "npm"
        assert gen.profile.framework == "React"
        assert gen.profile.test_framework == "Jest"

    def test_javascript_npm_nextjs(self, tmp_path):
        pkg = {"dependencies": {"next": "^14.0"}}
        _make_file(tmp_path, "package.json", json.dumps(pkg))
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.framework == "Next.js"

    def test_javascript_npm_express(self, tmp_path):
        pkg = {"dependencies": {"express": "^4.0"}}
        _make_file(tmp_path, "package.json", json.dumps(pkg))
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.framework == "Express"

    def test_go(self, tmp_path):
        _make_file(tmp_path, "go.mod", "module github.com/user/repo\n\ngo 1.21")
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.language == "Go"
        assert gen.profile.build_tool == "go build"
        assert gen.profile.test_framework == "go test"

    def test_no_stack_detected(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.language == ""
        assert gen.profile.build_tool == ""


# ===========================================================================
# _scan_structure
# ===========================================================================


class TestScanStructure:
    """Test directory/file structure scanning."""

    def test_finds_key_directories(self, tmp_path):
        for d in ("src", "tests", "docs", "config", "scripts", "deploy"):
            _make_dir(tmp_path, d)
        # Also a non-key directory
        _make_dir(tmp_path, "random_stuff")

        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_structure()
        dir_names = [d["dir"] for d in gen.profile.key_directories]
        assert "src" in dir_names
        assert "tests" in dir_names
        assert "docs" in dir_names
        assert "config" in dir_names
        assert "scripts" in dir_names
        assert "deploy" in dir_names
        assert "random_stuff" not in dir_names

    def test_finds_key_files(self, tmp_path):
        _make_file(tmp_path, "README.md", "# Hello")
        _make_file(tmp_path, "Dockerfile", "FROM python:3.12")
        _make_file(tmp_path, ".env.example", "KEY=value")

        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_structure()
        file_names = [f["file"] for f in gen.profile.key_files]
        assert "README.md" in file_names
        assert "Dockerfile" in file_names
        assert ".env.example" in file_names

    def test_finds_entry_points(self, tmp_path):
        _make_file(tmp_path, "main.py", "print('hi')")
        _make_file(tmp_path, "app.py", "app = Flask(__name__)")

        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_structure()
        assert "main.py" in gen.profile.entry_points
        assert "app.py" in gen.profile.entry_points

    def test_ignores_hidden_dirs(self, tmp_path):
        _make_dir(tmp_path, ".git")
        _make_dir(tmp_path, ".venv")

        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_structure()
        dir_names = [d["dir"] for d in gen.profile.key_directories]
        assert ".git" not in dir_names
        assert ".venv" not in dir_names


# ===========================================================================
# _scan_build_run
# ===========================================================================


class TestScanBuildRun:
    """Test build/test/run command detection."""

    def test_maven_spring_boot(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "Maven"
        gen.profile.framework = "Spring Boot"
        gen._scan_build_run()
        assert gen.profile.build_command == "mvn clean package -DskipTests"
        assert gen.profile.test_command == "mvn test"
        assert gen.profile.run_command == "mvn spring-boot:run"

    def test_gradle_spring(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "Gradle"
        gen.profile.framework = "Spring Boot"
        gen._scan_build_run()
        assert gen.profile.build_command == "./gradlew build -x test"
        assert gen.profile.run_command == "./gradlew bootRun"

    def test_poetry_with_main_py(self, tmp_path):
        _make_file(tmp_path, "main.py", "")
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "Poetry"
        gen._scan_build_run()
        assert gen.profile.build_command == "poetry install"
        assert gen.profile.test_command == "poetry run pytest"
        assert gen.profile.run_command == "poetry run python main.py"

    def test_poetry_without_main_py(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "Poetry"
        gen._scan_build_run()
        assert gen.profile.run_command == ""

    def test_npm(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "npm"
        gen._scan_build_run()
        assert gen.profile.build_command == "npm install && npm run build"
        assert gen.profile.test_command == "npm test"
        assert gen.profile.run_command == "npm start"

    def test_go(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "go build"
        gen._scan_build_run()
        assert gen.profile.build_command == "go build ./..."
        assert gen.profile.test_command == "go test ./..."
        assert gen.profile.run_command == "go run ."

    def test_env_override_build_cmd(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "Poetry"
        with patch.dict(os.environ, {"CODE_AGENTS_BUILD_CMD": "make build"}):
            gen._scan_build_run()
        assert gen.profile.build_command == "make build"

    def test_env_override_test_cmd(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "npm"
        with patch.dict(os.environ, {"CODE_AGENTS_TEST_CMD": "make test"}):
            gen._scan_build_run()
        assert gen.profile.test_command == "make test"


# ===========================================================================
# _scan_dependencies
# ===========================================================================


class TestScanDependencies:
    """Test dependency scanning."""

    def test_maven_deps(self, tmp_path):
        pom = "<project><artifactId>spring-core</artifactId><artifactId>kafka-clients</artifactId><artifactId>my-util</artifactId></project>"
        _make_file(tmp_path, "pom.xml", pom)
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "Maven"
        gen._scan_dependencies()
        assert gen.profile.dependency_count == 3
        assert "spring-core" in gen.profile.key_dependencies
        assert "kafka-clients" in gen.profile.key_dependencies

    def test_npm_deps(self, tmp_path):
        pkg = {"dependencies": {"express": "^4", "pg": "^8"}, "devDependencies": {"jest": "^29"}}
        _make_file(tmp_path, "package.json", json.dumps(pkg))
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "npm"
        gen._scan_dependencies()
        assert gen.profile.dependency_count == 3
        assert "express" in gen.profile.key_dependencies

    def test_poetry_deps(self, tmp_path):
        toml = "fastapi = '^0.100'\nuvicorn = '^0.23'\nhttpx = '^0.24'"
        _make_file(tmp_path, "pyproject.toml", toml)
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "Poetry"
        gen._scan_dependencies()
        assert gen.profile.dependency_count >= 3


# ===========================================================================
# _scan_conventions
# ===========================================================================


class TestScanConventions:
    """Test convention detection from git history."""

    def test_conventional_commits_detected(self, tmp_path):
        git_log = "\n".join([
            "abc1234 feat: add new feature",
            "bcd2345 fix: resolve bug",
            "cde3456 docs: update readme",
            "def4567 chore: update deps",
            "efg5678 feat: another feature",
        ])
        gen = OnboardingGenerator(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            # Branch call
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout=""),  # git branch -r
                MagicMock(returncode=0, stdout=git_log),  # git log
            ]
            gen._scan_conventions()
        assert "Conventional Commits" in gen.profile.commit_pattern

    def test_freeform_commits_detected(self, tmp_path):
        git_log = "\n".join([
            "abc1234 updated the login page",
            "bcd2345 fixed some issue with auth",
            "cde3456 added tests for user model",
        ])
        gen = OnboardingGenerator(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout=""),
                MagicMock(returncode=0, stdout=git_log),
            ]
            gen._scan_conventions()
        assert gen.profile.commit_pattern == "Free-form commit messages"

    def test_branch_patterns(self, tmp_path):
        branches = "  origin/feature/add-auth\n  origin/feature/fix-login\n  origin/bugfix/crash\n  origin/main"
        gen = OnboardingGenerator(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=branches),  # git branch -r
                MagicMock(returncode=0, stdout="abc123 some commit"),  # git log
            ]
            gen._scan_conventions()
        assert "feature" in gen.profile.branch_pattern
        assert "bugfix" in gen.profile.branch_pattern


# ===========================================================================
# _scan_ci_cd
# ===========================================================================


class TestScanCiCd:
    """Test CI/CD tool detection."""

    def test_jenkinsfile(self, tmp_path):
        _make_file(tmp_path, "Jenkinsfile", "pipeline { }")
        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_ci_cd()
        assert gen.profile.ci_tool == "Jenkins"

    def test_github_actions(self, tmp_path):
        _make_dir(tmp_path, ".github/workflows")
        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_ci_cd()
        assert gen.profile.ci_tool == "GitHub Actions"

    def test_gitlab_ci(self, tmp_path):
        _make_file(tmp_path, ".gitlab-ci.yml", "stages: [build]")
        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_ci_cd()
        assert gen.profile.ci_tool == "GitLab CI"

    def test_bitbucket_pipelines(self, tmp_path):
        _make_file(tmp_path, "bitbucket-pipelines.yml", "pipelines:")
        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_ci_cd()
        assert gen.profile.ci_tool == "Bitbucket Pipelines"

    def test_argocd_from_env(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        with patch.dict(os.environ, {"ARGOCD_URL": "https://argocd.example.com"}):
            gen._scan_ci_cd()
        assert gen.profile.deploy_tool == "ArgoCD"

    def test_jenkins_from_env(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        with patch.dict(os.environ, {"JENKINS_URL": "https://jenkins.example.com"}):
            gen._scan_ci_cd()
        assert gen.profile.ci_tool == "Jenkins"


# ===========================================================================
# _scan_architecture
# ===========================================================================


class TestScanArchitecture:
    """Test database/service detection."""

    def test_detects_postgres_from_env_example(self, tmp_path):
        _make_file(tmp_path, ".env.example", "DATABASE_URL=postgresql://localhost:5432/mydb")
        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_architecture()
        assert "postgres" in gen.profile.databases

    def test_detects_redis_from_docker_compose(self, tmp_path):
        _make_file(tmp_path, "docker-compose.yml", "services:\n  redis:\n    image: redis:7")
        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_architecture()
        assert "redis" in gen.profile.databases

    def test_detects_kafka_from_application_yml(self, tmp_path):
        _make_dir(tmp_path, "src/main/resources")
        _make_file(tmp_path, "src/main/resources/application.yml", "spring:\n  kafka:\n    bootstrap-servers: localhost:9092")
        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_architecture()
        assert "kafka" in gen.profile.databases

    def test_no_databases(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        gen._scan_architecture()
        assert gen.profile.databases == []


# ===========================================================================
# _scan_contributors
# ===========================================================================


class TestScanContributors:
    """Test contributor scanning with mocked git."""

    def test_parses_shortlog(self, tmp_path):
        shortlog = "    10\tAlice\n     5\tBob\n     3\tCharlie"
        gen = OnboardingGenerator(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=shortlog),  # shortlog
                MagicMock(returncode=0, stdout="abc123 some commit"),  # log
            ]
            gen._scan_contributors()
        assert len(gen.profile.top_contributors) == 3
        assert gen.profile.top_contributors[0]["name"] == "Alice"
        assert gen.profile.top_contributors[0]["commits"] == 10

    def test_empty_shortlog(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout=""),
            ]
            gen._scan_contributors()
        assert gen.profile.top_contributors == []


# ===========================================================================
# Full scan
# ===========================================================================


class TestFullScan:
    """Test the full scan() orchestration."""

    def test_scan_handles_errors_gracefully(self, tmp_path):
        """scan() should not crash even if individual steps fail."""
        gen = OnboardingGenerator(str(tmp_path))
        with patch.object(gen, "_detect_stack", side_effect=Exception("boom")):
            profile = gen.scan()
        # Should still return a profile with defaults
        assert profile.name == tmp_path.name
        assert profile.language == ""

    def test_scan_populates_name(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="")):
            profile = gen.scan()
        assert profile.name == tmp_path.name
        assert profile.path == str(tmp_path)


# ===========================================================================
# generate_onboarding_doc
# ===========================================================================


class TestGenerateOnboardingDoc:
    """Test markdown document generation."""

    def test_contains_all_sections(self):
        p = ProjectProfile(
            name="my-project",
            path="/tmp/my-project",
            language="Python",
            framework="FastAPI",
            build_tool="Poetry",
            test_framework="pytest",
            build_command="poetry install",
            test_command="poetry run pytest",
            run_command="poetry run python main.py",
            key_directories=[{"dir": "src", "description": "Source code"}],
            key_files=[{"file": "README.md", "description": "Docs"}],
            entry_points=["main.py"],
            dependency_count=42,
            key_dependencies=["fastapi", "uvicorn"],
            top_contributors=[{"name": "Alice", "commits": 50}],
            recent_activity="abc123 feat: init",
            ci_tool="GitHub Actions",
            deploy_tool="ArgoCD",
            databases=["postgres", "redis"],
            branch_pattern="Prefixes: feature, bugfix",
            commit_pattern="Conventional Commits (feat:, fix:, docs:, etc.)",
        )
        doc = generate_onboarding_doc(p)

        assert "# Onboarding Guide -- my-project" in doc
        assert "## Quick Start" in doc
        assert "poetry install" in doc
        assert "poetry run pytest" in doc
        assert "poetry run python main.py" in doc
        assert "## Tech Stack" in doc
        assert "Python" in doc
        assert "FastAPI" in doc
        assert "## Project Structure" in doc
        assert "src/" in doc
        assert "## Entry Points" in doc
        assert "main.py" in doc
        assert "## Key Dependencies (42 total)" in doc
        assert "fastapi" in doc
        assert "## Team" in doc
        assert "Alice" in doc
        assert "## Conventions" in doc
        assert "Conventional Commits" in doc
        assert "GitHub Actions" in doc
        assert "ArgoCD" in doc
        assert "postgres" in doc
        assert "code-agents chat" in doc
        assert "Auto-generated by code-agents onboard" in doc

    def test_handles_empty_profile(self):
        p = ProjectProfile(name="empty", path="/tmp/empty")
        doc = generate_onboarding_doc(p)
        assert "# Onboarding Guide -- empty" in doc
        assert "N/A" in doc

    def test_no_run_command_omitted(self):
        p = ProjectProfile(
            name="lib",
            path="/tmp/lib",
            build_command="make",
            test_command="make test",
            run_command="",
        )
        doc = generate_onboarding_doc(p)
        assert "Run locally" not in doc


# ===========================================================================
# format_onboarding_terminal
# ===========================================================================


class TestFormatOnboardingTerminal:
    """Test terminal format output."""

    def test_contains_key_info(self):
        p = ProjectProfile(
            name="my-app",
            path="/tmp/my-app",
            language="Java",
            framework="Spring Boot",
            build_tool="Maven",
            test_framework="JUnit 5",
            build_command="mvn clean package -DskipTests",
            test_command="mvn test",
            run_command="mvn spring-boot:run",
            key_directories=[{"dir": "src", "description": "Source code"}],
            entry_points=["src/main/java/App.java"],
            dependency_count=30,
            databases=["postgres"],
            ci_tool="Jenkins",
            deploy_tool="ArgoCD",
            top_contributors=[{"name": "Bob", "commits": 20}],
            branch_pattern="Prefixes: feature",
            commit_pattern="Conventional Commits (feat:, fix:, docs:, etc.)",
        )
        out = format_onboarding_terminal(p)

        assert "my-app" in out
        assert "Java" in out
        assert "Spring Boot" in out
        assert "Maven" in out
        assert "mvn clean package" in out
        assert "mvn test" in out
        assert "src/" in out
        assert "Bob" in out
        assert "feature" in out

    def test_empty_profile(self):
        p = ProjectProfile(name="x", path="/tmp/x")
        out = format_onboarding_terminal(p)
        assert "x" in out
        assert "N/A" in out

    def test_no_run_command_skipped(self):
        p = ProjectProfile(
            name="lib",
            path="/tmp/lib",
            build_command="make",
            test_command="make test",
            run_command="",
        )
        out = format_onboarding_terminal(p)
        assert "3." not in out  # step 3 (run) should be absent


# ===========================================================================
# _detect_stack edge cases — Gradle Spring Boot detection (lines 119-125)
# ===========================================================================


class TestDetectStackGradleEdge:
    def test_gradle_spring_boot(self, tmp_path):
        _make_file(tmp_path, "build.gradle", "apply plugin: 'org.springframework.boot'\njupiter")
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.framework == "Spring Boot"
        assert gen.profile.test_framework == "JUnit 5"

    def test_gradle_spring(self, tmp_path):
        _make_file(tmp_path, "build.gradle", "compile 'org.spring'\njunit")
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.framework == "Spring"
        assert gen.profile.test_framework == "JUnit 4"

    def test_gradle_no_spring(self, tmp_path):
        _make_file(tmp_path, "build.gradle", "apply plugin: 'java'")
        gen = OnboardingGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.profile.language == "Java/Kotlin"
        assert gen.profile.framework == ""
        assert gen.profile.test_framework == ""


# ===========================================================================
# _scan_dependencies — Gradle (lines 247-268)
# ===========================================================================


class TestScanDependenciesGradle:
    def test_gradle_deps(self, tmp_path):
        _make_file(tmp_path, "build.gradle",
                   "implementation 'org.spring:spring-core:5.0'\n"
                   "implementation 'org.apache.kafka:kafka-clients:3.0'\n"
                   "testImplementation 'junit:junit:4.13'\n")
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "Gradle"
        gen._scan_dependencies()
        assert gen.profile.dependency_count == 3
        assert any("spring" in d for d in gen.profile.key_dependencies)

    def test_gradle_no_key_deps(self, tmp_path):
        _make_file(tmp_path, "build.gradle", "implementation 'some:lib:1.0'\n")
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "Gradle"
        gen._scan_dependencies()
        assert gen.profile.dependency_count == 1
        # Falls back to extracting from artifact string
        assert len(gen.profile.key_dependencies) >= 1


# ===========================================================================
# _scan_dependencies — Maven exception (lines 278-279)
# ===========================================================================


class TestScanDependenciesError:
    def test_maven_file_error(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "Maven"
        # No pom.xml exists, should not crash
        gen._scan_dependencies()
        assert gen.profile.dependency_count == 0

    def test_npm_file_error(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        gen.profile.build_tool = "npm"
        gen._scan_dependencies()
        assert gen.profile.dependency_count == 0


# ===========================================================================
# _scan_contributors edge (lines 291-292)
# ===========================================================================


class TestScanContributorsEdge:
    def test_git_failure_no_crash(self, tmp_path):
        gen = OnboardingGenerator(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout=""),  # shortlog fails
                MagicMock(returncode=1, stdout=""),  # log fails
            ]
            gen._scan_contributors()
        assert gen.profile.top_contributors == []
        assert gen.profile.recent_activity == ""


# ===========================================================================
# _scan_architecture exception (lines 411-412)
# ===========================================================================


class TestScanArchitectureEdge:
    def test_unreadable_config_file(self, tmp_path):
        _make_file(tmp_path, "application.yml", "spring:\n  redis:\n    host: localhost")
        gen = OnboardingGenerator(str(tmp_path))
        with patch("builtins.open", side_effect=Exception("read error")):
            gen._scan_architecture()
        assert gen.profile.databases == []
