"""Project context scanner — generates lean repo summary for agent system prompts.

On `code-agents init` or chat start, scans the repo to build a compact
project fingerprint:
  - Language/framework detected
  - Key files found (README, Dockerfile, CI config, etc.)
  - Directory structure (top-level + src layout)
  - Ignore patterns from .code-agents/.ignore

The summary is ~200-400 tokens — enough for agents to navigate without
needing to `ls` and `cat` everything from scratch each session.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.domain.project_context")

# Directories always skipped (not configurable — these are never useful)
_ALWAYS_SKIP = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
    "target", ".gradle", ".idea", ".vscode", ".eggs", "*.egg-info",
    ".code-agents", "logs", ".cache", ".turbo", "coverage",
}

# Key files that reveal project structure
_KEY_FILES = [
    "README.md", "README.rst", "README.txt",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", "Justfile",
    ".github/workflows", "Jenkinsfile", ".gitlab-ci.yml",
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile",
    "package.json", "tsconfig.json", "yarn.lock", "pnpm-lock.yaml",
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    "go.mod", "go.sum",
    "Cargo.toml", "Cargo.lock",
    "CLAUDE.md", ".cursorrules",
]

# Language detection by file extension
_LANG_MARKERS = {
    ".py": "Python",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".js": "JavaScript",
    ".jsx": "JavaScript (React)",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".swift": "Swift",
    ".scala": "Scala",
}

# Framework detection by dependency files
_FRAMEWORK_MARKERS = {
    "pyproject.toml": {"fastapi": "FastAPI", "django": "Django", "flask": "Flask", "poetry": "Poetry"},
    "package.json": {"react": "React", "next": "Next.js", "vue": "Vue", "express": "Express", "angular": "Angular"},
    "pom.xml": {"spring-boot": "Spring Boot", "quarkus": "Quarkus"},
    "build.gradle": {"spring-boot": "Spring Boot", "micronaut": "Micronaut"},
    "Cargo.toml": {"actix": "Actix", "axum": "Axum", "rocket": "Rocket"},
}


def load_ignore_patterns(repo_path: str) -> list[str]:
    """Load ignore patterns from .code-agents/.ignore file.

    Supports gitignore-style patterns:
      - *.log          (extension match)
      - /vendor/       (directory match)
      - secret*.json   (glob match)
      - # comment      (ignored)
      - !important.log (negation — force include)

    Returns list of patterns (negations start with !).
    """
    ignore_file = Path(repo_path) / ".code-agents" / ".ignore"
    if not ignore_file.is_file():
        return []

    patterns = []
    try:
        for line in ignore_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
        logger.debug("Loaded %d ignore patterns from %s", len(patterns), ignore_file)
    except OSError:
        pass
    return patterns


def _should_ignore(path: str, name: str, ignore_patterns: list[str]) -> bool:
    """Check if a file/dir should be ignored based on patterns.

    Like gitignore: last matching pattern wins. Negation (!) overrides.
    """
    import fnmatch

    # Always skip hardcoded dirs
    if name in _ALWAYS_SKIP:
        return True

    # Process all patterns — last match wins (gitignore semantics)
    result = False
    for pattern in ignore_patterns:
        if pattern.startswith("!"):
            if fnmatch.fnmatch(name, pattern[1:]) or fnmatch.fnmatch(path, pattern[1:]):
                result = False  # negation: force include
        else:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(path, pattern):
                result = True  # match: ignore

    return result


def scan_project(repo_path: str) -> dict:
    """Scan repository and return a structured project summary.

    Returns dict with:
      - languages: list of detected languages
      - frameworks: list of detected frameworks
      - key_files: list of important files found
      - structure: top-level directory listing
      - file_count: total file count (approx)
      - ignore_patterns: loaded from .code-agents/.ignore
    """
    repo = Path(repo_path)
    if not repo.is_dir():
        return {}

    ignore_patterns = load_ignore_patterns(repo_path)

    # Top-level directory structure
    top_dirs = []
    top_files = []
    try:
        for entry in sorted(repo.iterdir()):
            name = entry.name
            if name.startswith(".") and name not in (".github", ".gitlab-ci.yml"):
                continue
            if _should_ignore(str(entry.relative_to(repo)), name, ignore_patterns):
                continue
            if entry.is_dir():
                top_dirs.append(name + "/")
            else:
                top_files.append(name)
    except OSError:
        pass

    # Key files detection
    found_key_files = []
    for kf in _KEY_FILES:
        kf_path = repo / kf
        if kf_path.exists():
            found_key_files.append(kf)

    # Language detection (sample first 500 files)
    lang_counts: dict[str, int] = {}
    file_count = 0
    for root, dirs, files in os.walk(repo):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if not _should_ignore(
            os.path.relpath(os.path.join(root, d), repo), d, ignore_patterns
        ) and d not in _ALWAYS_SKIP]

        for f in files:
            if file_count > 500:
                break
            file_count += 1
            ext = Path(f).suffix
            if ext in _LANG_MARKERS:
                lang = _LANG_MARKERS[ext]
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
        if file_count > 500:
            break

    # Sort languages by count
    languages = sorted(lang_counts.keys(), key=lambda l: lang_counts[l], reverse=True)[:5]

    # Framework detection
    frameworks = []
    for dep_file, markers in _FRAMEWORK_MARKERS.items():
        dep_path = repo / dep_file
        if dep_path.is_file():
            try:
                content = dep_path.read_text(errors="ignore").lower()
                for keyword, framework in markers.items():
                    if keyword in content and framework not in frameworks:
                        frameworks.append(framework)
            except OSError:
                pass

    return {
        "languages": languages,
        "frameworks": frameworks,
        "key_files": found_key_files,
        "structure": top_dirs + top_files[:10],
        "file_count": file_count,
        "ignore_patterns": ignore_patterns,
    }


def build_project_summary(repo_path: str) -> str:
    """Build a lean text summary of the project for injection into system prompts.

    Target: ~200-400 tokens. Just enough for agents to navigate.
    """
    info = scan_project(repo_path)
    if not info:
        return ""

    lines = []

    # Languages & frameworks
    if info["languages"]:
        lang_str = ", ".join(info["languages"])
        if info["frameworks"]:
            lang_str += f" ({', '.join(info['frameworks'])})"
        lines.append(f"Stack: {lang_str}")

    # Key files
    if info["key_files"]:
        lines.append(f"Key files: {', '.join(info['key_files'][:8])}")

    # Directory structure
    if info["structure"]:
        dirs_str = "  ".join(info["structure"][:12])
        lines.append(f"Structure: {dirs_str}")

    # File count
    if info["file_count"]:
        count_label = f"{info['file_count']}+" if info["file_count"] >= 500 else str(info["file_count"])
        lines.append(f"Files: ~{count_label}")

    # Ignore patterns
    if info["ignore_patterns"]:
        lines.append(f"Ignored: {len(info['ignore_patterns'])} patterns from .code-agents/.ignore")

    if not lines:
        return ""

    return "\n".join(lines)
