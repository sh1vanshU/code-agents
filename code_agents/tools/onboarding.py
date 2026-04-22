"""Onboarding Guide Generator — auto-generates project onboarding docs."""

from __future__ import annotations

import glob
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.tools.onboarding")


@dataclass
class ProjectProfile:
    """Detected project profile from repo scan."""

    name: str
    path: str
    language: str = ""
    framework: str = ""
    build_tool: str = ""
    test_framework: str = ""

    # Structure
    key_directories: list[dict] = field(default_factory=list)  # dir, description
    key_files: list[dict] = field(default_factory=list)  # file, description
    entry_points: list[str] = field(default_factory=list)

    # Build & Run
    build_command: str = ""
    test_command: str = ""
    run_command: str = ""

    # Dependencies
    dependency_count: int = 0
    key_dependencies: list[str] = field(default_factory=list)

    # Team
    top_contributors: list[dict] = field(default_factory=list)  # name, commits
    recent_activity: str = ""

    # Architecture
    api_endpoints: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)

    # CI/CD
    ci_tool: str = ""
    deploy_tool: str = ""

    # Conventions
    branch_pattern: str = ""
    commit_pattern: str = ""


class OnboardingGenerator:
    """Scans a repo and generates onboarding documentation."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.profile = ProjectProfile(
            name=os.path.basename(cwd),
            path=cwd,
        )

    def scan(self) -> ProjectProfile:
        """Run all scans and return the populated profile."""
        steps = [
            self._detect_stack,
            self._scan_structure,
            self._scan_dependencies,
            self._scan_build_run,
            self._scan_contributors,
            self._scan_architecture,
            self._scan_ci_cd,
            self._scan_conventions,
        ]
        for step in steps:
            try:
                step()
            except Exception as e:
                logger.debug("Onboarding scan step %s failed: %s", getattr(step, "__name__", step), e)
        return self.profile

    # ------------------------------------------------------------------
    # Stack detection
    # ------------------------------------------------------------------

    def _detect_stack(self):
        """Detect language, framework, build tool."""
        p = self.profile

        if os.path.exists(os.path.join(self.cwd, "pom.xml")):
            p.language = "Java"
            p.build_tool = "Maven"
            with open(os.path.join(self.cwd, "pom.xml")) as f:
                pom = f.read()
                if "spring-boot" in pom:
                    p.framework = "Spring Boot"
                elif "spring" in pom:
                    p.framework = "Spring"
                if "junit-jupiter" in pom:
                    p.test_framework = "JUnit 5"
                elif "junit" in pom:
                    p.test_framework = "JUnit 4"

        elif os.path.exists(os.path.join(self.cwd, "build.gradle")):
            p.language = "Java/Kotlin"
            p.build_tool = "Gradle"
            with open(os.path.join(self.cwd, "build.gradle")) as f:
                gradle = f.read()
                if "spring-boot" in gradle.lower() or "org.springframework.boot" in gradle:
                    p.framework = "Spring Boot"
                elif "spring" in gradle.lower():
                    p.framework = "Spring"
                if "jupiter" in gradle.lower():
                    p.test_framework = "JUnit 5"
                elif "junit" in gradle.lower():
                    p.test_framework = "JUnit 4"

        elif os.path.exists(os.path.join(self.cwd, "pyproject.toml")):
            p.language = "Python"
            p.build_tool = "Poetry"
            p.test_framework = "pytest"
            with open(os.path.join(self.cwd, "pyproject.toml")) as f:
                content = f.read().lower()
                if "fastapi" in content:
                    p.framework = "FastAPI"
                elif "django" in content:
                    p.framework = "Django"
                elif "flask" in content:
                    p.framework = "Flask"

        elif os.path.exists(os.path.join(self.cwd, "package.json")):
            p.language = "JavaScript/TypeScript"
            p.build_tool = "npm"
            with open(os.path.join(self.cwd, "package.json")) as f:
                pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "react" in deps:
                    p.framework = "React"
                elif "next" in deps:
                    p.framework = "Next.js"
                elif "express" in deps:
                    p.framework = "Express"
                if "jest" in deps:
                    p.test_framework = "Jest"

        elif os.path.exists(os.path.join(self.cwd, "go.mod")):
            p.language = "Go"
            p.build_tool = "go build"
            p.test_framework = "go test"

    # ------------------------------------------------------------------
    # Structure
    # ------------------------------------------------------------------

    def _scan_structure(self):
        """Scan directory structure for key directories and files."""
        p = self.profile

        # Key directories
        source_dirs = {"src", "lib", "app", "pkg", "internal", "cmd"}
        test_dirs = {"test", "tests", "spec", "__tests__"}
        doc_dirs = {"docs", "documentation"}
        config_dirs = {"config", "conf", "settings"}
        script_dirs = {"scripts", "bin", "tools"}
        infra_dirs = {"deploy", "k8s", "helm", "terraform", "infra"}

        dir_map = {
            "Source code": source_dirs,
            "Tests": test_dirs,
            "Documentation": doc_dirs,
            "Configuration": config_dirs,
            "Scripts/Tools": script_dirs,
            "Infrastructure/Deploy": infra_dirs,
        }

        for d in sorted(os.listdir(self.cwd)):
            full = os.path.join(self.cwd, d)
            if not os.path.isdir(full) or d.startswith("."):
                continue
            for description, names in dir_map.items():
                if d in names:
                    p.key_directories.append({"dir": d, "description": description})
                    break

        # Key files
        key_files_map = {
            "README.md": "Project documentation",
            "CONTRIBUTING.md": "Contribution guidelines",
            "Makefile": "Build automation",
            "Dockerfile": "Container definition",
            "docker-compose.yml": "Local development stack",
            "docker-compose.yaml": "Local development stack",
            ".env.example": "Environment variable template",
            "CHANGELOG.md": "Change history",
        }
        for f, desc in key_files_map.items():
            if os.path.exists(os.path.join(self.cwd, f)):
                p.key_files.append({"file": f, "description": desc})

        # Entry points
        entry_candidates = [
            "src/main/java/**/Application.java",
            "main.py", "app.py", "manage.py",
            "index.js", "index.ts", "server.js",
            "main.go", "cmd/main.go",
        ]
        for candidate in entry_candidates:
            if "*" in candidate:
                matches = glob.glob(os.path.join(self.cwd, candidate), recursive=True)
                p.entry_points.extend(
                    [os.path.relpath(m, self.cwd) for m in matches]
                )
            elif os.path.exists(os.path.join(self.cwd, candidate)):
                p.entry_points.append(candidate)

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------

    def _scan_dependencies(self):
        """Count and identify key dependencies."""
        p = self.profile

        if p.build_tool == "Maven":
            try:
                with open(os.path.join(self.cwd, "pom.xml")) as f:
                    content = f.read()
                deps = re.findall(r"<artifactId>([^<]+)</artifactId>", content)
                p.dependency_count = len(deps)
                key = [
                    d for d in deps
                    if any(k in d for k in [
                        "spring", "kafka", "redis", "postgres",
                        "mysql", "elastic", "flyway",
                    ])
                ]
                p.key_dependencies = key[:15]
            except Exception:
                pass

        elif p.build_tool == "Gradle":
            try:
                with open(os.path.join(self.cwd, "build.gradle")) as f:
                    content = f.read()
                # Match common dependency declarations like: implementation 'group:artifact:version'
                deps = re.findall(
                    r"(?:implementation|compile|api|runtimeOnly|testImplementation)\s+['\"]([^'\"]+)['\"]",
                    content,
                )
                p.dependency_count = len(deps)
                key = [
                    d for d in deps
                    if any(k in d for k in [
                        "spring", "kafka", "redis", "postgres",
                        "mysql", "elastic", "flyway",
                    ])
                ]
                p.key_dependencies = key[:15] if key else [d.split(":")[-2] if ":" in d else d for d in deps[:15]]
            except Exception:
                pass

        elif p.build_tool == "Poetry":
            try:
                with open(os.path.join(self.cwd, "pyproject.toml")) as f:
                    content = f.read()
                deps = re.findall(r"^(\w[\w-]+)\s*=", content, re.MULTILINE)
                p.dependency_count = len(deps)
                p.key_dependencies = deps[:15]
            except Exception:
                pass

        elif p.build_tool == "npm":
            try:
                with open(os.path.join(self.cwd, "package.json")) as f:
                    pkg = json.load(f)
                all_deps = {
                    **pkg.get("dependencies", {}),
                    **pkg.get("devDependencies", {}),
                }
                p.dependency_count = len(all_deps)
                p.key_dependencies = list(pkg.get("dependencies", {}).keys())[:15]
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Build & Run
    # ------------------------------------------------------------------

    def _scan_build_run(self):
        """Detect build, test, run commands."""
        p = self.profile

        if p.build_tool == "Maven":
            p.build_command = "mvn clean package -DskipTests"
            p.test_command = "mvn test"
            p.run_command = (
                "mvn spring-boot:run"
                if p.framework == "Spring Boot"
                else "java -jar target/*.jar"
            )
        elif p.build_tool == "Gradle":
            p.build_command = "./gradlew build -x test"
            p.test_command = "./gradlew test"
            p.run_command = (
                "./gradlew bootRun"
                if "Spring" in (p.framework or "")
                else "./gradlew run"
            )
        elif p.build_tool == "Poetry":
            p.build_command = "poetry install"
            p.test_command = "poetry run pytest"
            p.run_command = (
                "poetry run python main.py"
                if os.path.exists(os.path.join(self.cwd, "main.py"))
                else ""
            )
        elif p.build_tool == "npm":
            p.build_command = "npm install && npm run build"
            p.test_command = "npm test"
            p.run_command = "npm start"
        elif p.build_tool == "go build":
            p.build_command = "go build ./..."
            p.test_command = "go test ./..."
            p.run_command = "go run ."

        # Override from env
        env_build = os.getenv("CODE_AGENTS_BUILD_CMD", "")
        if env_build:
            p.build_command = env_build
        env_test = os.getenv("CODE_AGENTS_TEST_CMD", "")
        if env_test:
            p.test_command = env_test

    # ------------------------------------------------------------------
    # Contributors
    # ------------------------------------------------------------------

    def _scan_contributors(self):
        """Get top contributors and recent activity from git."""
        p = self.profile

        result = subprocess.run(
            ["git", "shortlog", "-sn", "--since=6 months ago"],
            capture_output=True, text=True, timeout=15, cwd=self.cwd,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n")[:10]:
                line = line.strip()
                if line:
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        p.top_contributors.append({
                            "name": parts[1],
                            "commits": int(parts[0]),
                        })

        # Recent activity
        result = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            capture_output=True, text=True, timeout=10, cwd=self.cwd,
        )
        if result.returncode == 0:
            p.recent_activity = result.stdout.strip()

    # ------------------------------------------------------------------
    # Architecture
    # ------------------------------------------------------------------

    def _scan_architecture(self):
        """Detect databases from config files."""
        p = self.profile

        db_indicators = {
            "postgres": ["postgresql", "postgres", "pg_"],
            "mysql": ["mysql", "mariadb"],
            "mongodb": ["mongo", "mongodb"],
            "redis": ["redis"],
            "elasticsearch": ["elastic", "elasticsearch"],
            "kafka": ["kafka"],
        }

        config_filenames = {
            "application.yml", "application.yaml", "application.properties",
            ".env.example", "docker-compose.yml", "docker-compose.yaml",
        }

        for root, dirs, files in os.walk(self.cwd):
            # Skip heavy/irrelevant directories
            dirs[:] = [
                d for d in dirs
                if d not in (".git", "node_modules", "target", "build", "__pycache__", ".tox", "venv")
            ]
            for f in files:
                if f in config_filenames:
                    filepath = os.path.join(root, f)
                    try:
                        with open(filepath) as fh:
                            content = fh.read().lower()
                            for db, keywords in db_indicators.items():
                                if any(kw in content for kw in keywords) and db not in p.databases:
                                    p.databases.append(db)
                    except Exception:
                        pass

    # ------------------------------------------------------------------
    # CI/CD
    # ------------------------------------------------------------------

    def _scan_ci_cd(self):
        """Detect CI/CD tools."""
        p = self.profile

        if os.path.exists(os.path.join(self.cwd, "Jenkinsfile")):
            p.ci_tool = "Jenkins"
        elif os.path.exists(os.path.join(self.cwd, ".github", "workflows")):
            p.ci_tool = "GitHub Actions"
        elif os.path.exists(os.path.join(self.cwd, ".gitlab-ci.yml")):
            p.ci_tool = "GitLab CI"
        elif os.path.exists(os.path.join(self.cwd, "bitbucket-pipelines.yml")):
            p.ci_tool = "Bitbucket Pipelines"

        if os.getenv("JENKINS_URL"):
            p.ci_tool = p.ci_tool or "Jenkins"
        if os.getenv("ARGOCD_URL"):
            p.deploy_tool = "ArgoCD"

    # ------------------------------------------------------------------
    # Conventions
    # ------------------------------------------------------------------

    def _scan_conventions(self):
        """Detect team conventions from git history."""
        p = self.profile

        # Branch naming
        result = subprocess.run(
            ["git", "branch", "-r", "--list", "origin/*"],
            capture_output=True, text=True, timeout=10, cwd=self.cwd,
        )
        if result.returncode == 0:
            branches = result.stdout.strip().split("\n")
            patterns: set[str] = set()
            for b in branches:
                b = b.strip().replace("origin/", "")
                if "/" in b:
                    patterns.add(b.split("/")[0])
            if patterns:
                p.branch_pattern = "Prefixes: " + ", ".join(sorted(patterns)[:5])

        # Commit conventions
        result = subprocess.run(
            ["git", "log", "--oneline", "-20"],
            capture_output=True, text=True, timeout=10, cwd=self.cwd,
        )
        if result.returncode == 0:
            msgs = result.stdout.strip().split("\n")
            conventional = sum(
                1 for m in msgs
                if re.match(
                    r"^[a-f0-9]+\s+(feat|fix|docs|style|refactor|test|chore|perf|ci|build)",
                    m,
                )
            )
            if conventional > len(msgs) * 0.5:
                p.commit_pattern = "Conventional Commits (feat:, fix:, docs:, etc.)"
            else:
                p.commit_pattern = "Free-form commit messages"


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def generate_onboarding_doc(profile: ProjectProfile) -> str:
    """Generate full markdown onboarding document."""
    p = profile
    today = datetime.now().strftime("%Y-%m-%d")

    dirs_block = "\n".join(
        f"  {d['dir']}/    -- {d['description']}" for d in p.key_directories
    )
    files_block = "\n".join(
        f"  {f['file']}  -- {f['description']}" for f in p.key_files
    )
    entry_block = (
        "\n".join(f"- `{ep}`" for ep in p.entry_points)
        or "- Not auto-detected"
    )
    deps_block = (
        "\n".join(f"- {dep}" for dep in p.key_dependencies[:10])
        or "- See build file for full list"
    )
    contributors_block = (
        "\n".join(
            f"- {c['name']}: {c['commits']} commits"
            for c in p.top_contributors[:5]
        )
        or "- No git history available"
    )

    run_line = ""
    if p.run_command:
        run_line = f"""
# Run locally
{p.run_command}
"""

    run_row = ""
    if p.run_command:
        run_row = f"| `{p.run_command}` | Run locally |\n"

    doc = f"""# Onboarding Guide -- {p.name}

## Quick Start

```bash
# Clone
git clone <repo-url>
cd {p.name}

# Install dependencies
{p.build_command}

# Run tests
{p.test_command}
{run_line}```

## Tech Stack
| | |
|---|---|
| Language | {p.language} |
| Framework | {p.framework or 'N/A'} |
| Build Tool | {p.build_tool} |
| Test Framework | {p.test_framework or 'N/A'} |
| CI | {p.ci_tool or 'N/A'} |
| Deploy | {p.deploy_tool or 'N/A'} |
| Databases | {', '.join(p.databases) or 'N/A'} |

## Project Structure
```
{p.name}/
{dirs_block}
{files_block}
```

## Entry Points
{entry_block}

## Key Dependencies ({p.dependency_count} total)
{deps_block}

## Team
### Top Contributors (last 6 months)
{contributors_block}

### Recent Activity
```
{p.recent_activity or 'No recent commits'}
```

## Conventions
- **Branch naming**: {p.branch_pattern or 'Not detected'}
- **Commit messages**: {p.commit_pattern or 'Not detected'}

## Useful Commands
| Command | What it does |
|---------|-------------|
| `{p.build_command}` | Build the project |
| `{p.test_command}` | Run tests |
{run_row}| `code-agents chat` | AI-assisted development |
| `code-agents doctor` | Check project health |
| `code-agents review` | AI code review |

---
*Auto-generated by code-agents onboard on {today}*
"""
    return doc


def format_onboarding_terminal(profile: ProjectProfile) -> str:
    """Format for terminal display (shorter version)."""
    p = profile
    lines = []
    lines.append(f"  Onboarding Guide -- {p.name}")
    lines.append(f"  {'=' * 50}")
    lines.append(f"\n  Stack: {p.language} / {p.framework or 'N/A'} / {p.build_tool}")
    lines.append(
        f"  Tests: {p.test_framework or 'N/A'}"
        f" | CI: {p.ci_tool or 'N/A'}"
        f" | Deploy: {p.deploy_tool or 'N/A'}"
    )
    lines.append(
        f"  Dependencies: {p.dependency_count}"
        f" | Databases: {', '.join(p.databases) or 'none'}"
    )

    lines.append(f"\n  Quick Start:")
    lines.append(f"    1. {p.build_command}")
    lines.append(f"    2. {p.test_command}")
    if p.run_command:
        lines.append(f"    3. {p.run_command}")

    lines.append(f"\n  Key Directories:")
    for d in p.key_directories:
        lines.append(f"    {d['dir']}/  -- {d['description']}")

    if p.entry_points:
        lines.append(f"\n  Entry Points:")
        for ep in p.entry_points:
            lines.append(f"    {ep}")

    if p.top_contributors:
        lines.append(f"\n  Top Contributors:")
        for c in p.top_contributors[:5]:
            lines.append(f"    {c['name']}: {c['commits']} commits")

    if p.branch_pattern:
        lines.append(f"\n  Branch Pattern: {p.branch_pattern}")
    if p.commit_pattern:
        lines.append(f"  Commit Pattern: {p.commit_pattern}")

    return "\n".join(lines)
