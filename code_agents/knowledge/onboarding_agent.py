"""Onboarding Agent — guided tour for new developers joining a project.

Analyzes the project structure, README, configuration files, and dependencies
to generate a comprehensive onboarding guide with setup checklist and first-task
suggestions.

Usage::

    from code_agents.knowledge.onboarding_agent import OnboardingAgent

    agent = OnboardingAgent("/path/to/repo")
    tour = agent.start_tour()
    print(tour)
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.knowledge.onboarding_agent")

# Common entry points by language/framework
_ENTRY_POINTS = {
    "app.py": "FastAPI/Flask application entry point",
    "main.py": "Main application entry point",
    "manage.py": "Django management script",
    "index.js": "Node.js entry point",
    "index.ts": "TypeScript entry point",
    "server.py": "Server entry point",
    "cli.py": "CLI entry point",
    "setup.py": "Package setup script",
    "pyproject.toml": "Python project config (Poetry/setuptools)",
    "package.json": "Node.js project config",
    "Cargo.toml": "Rust project config",
    "go.mod": "Go module config",
    "Makefile": "Build automation",
    "Dockerfile": "Container build config",
    "docker-compose.yml": "Container orchestration",
    "docker-compose.yaml": "Container orchestration",
    ".env.example": "Environment variable template",
}

# Config files
_CONFIG_FILES = (
    "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml",
    "build.gradle", "Gemfile", "requirements.txt", "setup.cfg",
    ".env.example", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", "Dockerfile", "Jenkinsfile", ".gitlab-ci.yml",
    ".github/workflows", "tsconfig.json", "jest.config.js",
    "pytest.ini", "tox.ini",
)


class OnboardingAgent:
    """Generate project onboarding tour for new developers."""

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        logger.debug("OnboardingAgent initialized for %s", cwd)

    def start_tour(self) -> str:
        """Generate a complete onboarding tour.

        Returns:
            Formatted tour text with sections: overview, key files,
            setup checklist, and first task suggestion.
        """
        logger.info("Generating onboarding tour for %s", self.cwd)

        sections: list[str] = []

        # Header
        project_name = os.path.basename(os.path.abspath(self.cwd))
        sections.append(f"{'=' * 60}")
        sections.append(f"  Welcome to {project_name}!")
        sections.append(f"  Onboarding Tour")
        sections.append(f"{'=' * 60}")
        sections.append("")

        # 1. Project Overview
        sections.append("## Project Overview")
        sections.append("")
        overview = self._project_overview()
        sections.append(overview)
        sections.append("")

        # 2. Key Files
        sections.append("## Key Files & Entry Points")
        sections.append("")
        key_files = self._key_files()
        if key_files:
            for kf in key_files:
                sections.append(f"  {kf['path']}")
                sections.append(f"    -> {kf['description']}")
        else:
            sections.append("  (no standard entry points detected)")
        sections.append("")

        # 3. Setup Checklist
        sections.append("## Setup Checklist")
        sections.append("")
        checklist = self._setup_checklist()
        for i, item in enumerate(checklist, 1):
            status = "[x]" if item.get("exists") else "[ ]"
            sections.append(f"  {status} {item['description']}")
            if item.get("command"):
                sections.append(f"      $ {item['command']}")
        sections.append("")

        # 4. Project Structure
        sections.append("## Project Structure")
        sections.append("")
        structure = self._project_structure()
        sections.append(structure)
        sections.append("")

        # 5. First Task
        sections.append("## Suggested First Task")
        sections.append("")
        first_task = self._first_task()
        sections.append(f"  {first_task}")
        sections.append("")

        # 6. Useful Commands
        sections.append("## Useful Commands")
        sections.append("")
        commands = self._useful_commands()
        for cmd in commands:
            sections.append(f"  $ {cmd['command']}")
            sections.append(f"    {cmd['description']}")
        sections.append("")

        sections.append(f"{'=' * 60}")
        sections.append("  Happy coding! Run 'code-agents chat' for AI assistance.")
        sections.append(f"{'=' * 60}")

        tour = "\n".join(sections)
        logger.info("Tour generated: %d lines", len(sections))
        return tour

    def _project_overview(self) -> str:
        """Extract project overview from README."""
        readme_path = self._find_readme()
        if not readme_path:
            return "  No README found. Consider adding one to describe the project."

        try:
            content = Path(readme_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return "  Could not read README."

        # Extract first non-heading paragraph
        lines = content.splitlines()
        overview_lines: list[str] = []
        found_content = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if found_content and overview_lines:
                    break
                continue
            if stripped.startswith("#"):
                if overview_lines:
                    break
                continue
            if stripped.startswith(("![", "[![", "---", "===")):
                continue
            found_content = True
            overview_lines.append(f"  {stripped}")
            if len(overview_lines) >= 5:
                break

        if overview_lines:
            return "\n".join(overview_lines)
        return "  (README found but no description paragraph detected)"

    def _key_files(self) -> list[dict[str, str]]:
        """Identify key entry points and config files."""
        key: list[dict[str, str]] = []

        for filename, desc in _ENTRY_POINTS.items():
            # Check root level
            path = os.path.join(self.cwd, filename)
            if os.path.exists(path):
                key.append({"path": filename, "description": desc})
            # Check src/ subdirectory
            src_path = os.path.join(self.cwd, "src", filename)
            if os.path.exists(src_path):
                key.append({"path": f"src/{filename}", "description": desc})

        return key

    def _setup_checklist(self) -> list[dict[str, Any]]:
        """Generate setup checklist based on detected project type."""
        checklist: list[dict[str, Any]] = []

        # Git
        checklist.append({
            "description": "Git repository initialized",
            "exists": os.path.isdir(os.path.join(self.cwd, ".git")),
            "command": "git clone <repo-url>",
        })

        # Python / Poetry
        if os.path.isfile(os.path.join(self.cwd, "pyproject.toml")):
            checklist.append({
                "description": "Python dependencies installed (Poetry)",
                "exists": os.path.isdir(os.path.join(self.cwd, ".venv")),
                "command": "poetry install",
            })

        # Python / pip
        if os.path.isfile(os.path.join(self.cwd, "requirements.txt")):
            checklist.append({
                "description": "Python dependencies installed (pip)",
                "exists": os.path.isdir(os.path.join(self.cwd, ".venv")),
                "command": "pip install -r requirements.txt",
            })

        # Node.js
        if os.path.isfile(os.path.join(self.cwd, "package.json")):
            checklist.append({
                "description": "Node.js dependencies installed",
                "exists": os.path.isdir(os.path.join(self.cwd, "node_modules")),
                "command": "npm install",
            })

        # Docker
        if os.path.isfile(os.path.join(self.cwd, "Dockerfile")):
            checklist.append({
                "description": "Docker available for containerized development",
                "exists": True,  # Can't easily check
                "command": "docker build -t project .",
            })

        # Environment
        env_example = os.path.join(self.cwd, ".env.example")
        env_file = os.path.join(self.cwd, ".env")
        if os.path.isfile(env_example):
            checklist.append({
                "description": "Environment variables configured (.env from .env.example)",
                "exists": os.path.isfile(env_file),
                "command": "cp .env.example .env && vim .env",
            })

        # Tests
        tests_dir = os.path.join(self.cwd, "tests")
        if os.path.isdir(tests_dir):
            checklist.append({
                "description": "Tests directory found — run tests to verify setup",
                "exists": True,
                "command": "poetry run pytest" if os.path.isfile(os.path.join(self.cwd, "pyproject.toml")) else "npm test",
            })

        return checklist

    def _first_task(self) -> str:
        """Suggest a good first task for a new developer."""
        suggestions: list[str] = []

        # Check for CONTRIBUTING.md
        contrib = os.path.join(self.cwd, "CONTRIBUTING.md")
        if os.path.isfile(contrib):
            suggestions.append("Read CONTRIBUTING.md for guidelines, then pick a 'good-first-issue' from the issue tracker.")

        # Check for TODO/FIXME
        todo_count = self._count_todos()
        if todo_count > 0:
            suggestions.append(f"Fix one of the {todo_count} TODO/FIXME comments in the codebase.")

        # Check for tests
        tests_dir = os.path.join(self.cwd, "tests")
        if os.path.isdir(tests_dir):
            suggestions.append("Add a test for an untested function (run 'code-agents coverage' to find gaps).")

        # Default
        suggestions.append("Run the project locally, explore the main entry point, and add a small improvement (typo fix, docstring, log message).")

        return suggestions[0] if suggestions else "Explore the codebase and run the tests!"

    def _project_structure(self) -> str:
        """Generate a quick project structure tree (depth 2)."""
        lines: list[str] = []
        root = self.cwd

        entries = sorted(os.listdir(root))
        dirs = [e for e in entries if os.path.isdir(os.path.join(root, e)) and not e.startswith(".") and e not in ("node_modules", "__pycache__", ".venv", "venv")]
        files = [e for e in entries if os.path.isfile(os.path.join(root, e)) and not e.startswith(".")]

        for d in dirs[:15]:
            lines.append(f"  {d}/")
            sub_path = os.path.join(root, d)
            try:
                sub_entries = sorted(os.listdir(sub_path))[:8]
                for s in sub_entries:
                    if s.startswith(".") or s == "__pycache__":
                        continue
                    suffix = "/" if os.path.isdir(os.path.join(sub_path, s)) else ""
                    lines.append(f"    {s}{suffix}")
                if len(os.listdir(sub_path)) > 8:
                    lines.append(f"    ... ({len(os.listdir(sub_path)) - 8} more)")
            except OSError:
                pass

        for f in files[:10]:
            lines.append(f"  {f}")
        if len(files) > 10:
            lines.append(f"  ... ({len(files) - 10} more files)")

        return "\n".join(lines) if lines else "  (empty directory)"

    def _useful_commands(self) -> list[dict[str, str]]:
        """Detect and suggest useful commands."""
        commands: list[dict[str, str]] = []

        if os.path.isfile(os.path.join(self.cwd, "pyproject.toml")):
            commands.append({"command": "poetry run pytest", "description": "Run tests"})
            commands.append({"command": "poetry run python -m code_agents.cli", "description": "Run CLI"})

        if os.path.isfile(os.path.join(self.cwd, "package.json")):
            commands.append({"command": "npm test", "description": "Run tests"})
            commands.append({"command": "npm start", "description": "Start the application"})

        if os.path.isfile(os.path.join(self.cwd, "Makefile")):
            commands.append({"command": "make", "description": "Run default make target"})
            commands.append({"command": "make help", "description": "Show available make targets"})

        commands.append({"command": "code-agents chat", "description": "Start AI chat for help"})
        commands.append({"command": "code-agents doctor", "description": "Diagnose environment issues"})

        return commands

    # --- Helpers ---

    def _find_readme(self) -> str | None:
        """Find README file (case-insensitive)."""
        for name in ("README.md", "readme.md", "README.rst", "README.txt", "README"):
            path = os.path.join(self.cwd, name)
            if os.path.isfile(path):
                return path
        return None

    def _count_todos(self) -> int:
        """Count TODO/FIXME comments (quick scan)."""
        count = 0
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv", ".venv", "__pycache__")]
            for f in files:
                if not f.endswith((".py", ".js", ".ts", ".java", ".go", ".rs")):
                    continue
                try:
                    text = Path(os.path.join(root, f)).read_text(encoding="utf-8", errors="ignore")
                    count += len(re.findall(r"\b(TODO|FIXME|HACK|XXX)\b", text))
                except OSError:
                    pass
                if count > 100:  # Cap scan
                    return count
        return count
