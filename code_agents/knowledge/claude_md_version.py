"""CLAUDE.md semantic versioning — auto-bumps version on commits.

Version format: ``<!-- version: X.Y.Z -->`` as the first line of CLAUDE.md.

Bump rules:
  major  — new agent added, architecture rewritten, breaking workflow change
  minor  — new section, new commands/env vars documented, feature docs
  patch  — typo fixes, wording updates, small corrections
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger("code_agents.knowledge.claude_md_version")

_VERSION_RE = re.compile(r"<!--\s*version:\s*(\d+)\.(\d+)\.(\d+)\s*-->")

# Patterns in diff that indicate a major bump
_MAJOR_PATTERNS = [
    r"^\+.*agents/\w+/\w+\.yaml",         # new agent YAML
    r"^\+##\s+Architecture",               # architecture section rewritten
    r"^\+.*## Architecture",
]

# Patterns in diff that indicate a minor bump
_MINOR_PATTERNS = [
    r"^\+##\s+",                           # new top-level section
    r"^\+\|\s*`[A-Z_]+`",                 # new env var in table
    r"^\+\s*-\s*\*\*.*\*\*.*—",           # new feature bullet
    r"^\+###\s+",                          # new subsection
]


def get_current_version(claude_md_path: str | Path) -> tuple[int, int, int]:
    """Parse the version from the first few lines of CLAUDE.md.

    Returns (0, 0, 0) if no version header found.
    """
    path = Path(claude_md_path)
    if not path.exists():
        return (0, 0, 0)
    try:
        # Only need to check first 3 lines
        with open(path, "r", encoding="utf-8") as f:
            for _ in range(3):
                line = f.readline()
                m = _VERSION_RE.search(line)
                if m:
                    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except (OSError, ValueError):
        pass
    return (0, 0, 0)


def format_version(major: int, minor: int, patch: int) -> str:
    """Format version tuple as string."""
    return f"{major}.{minor}.{patch}"


def ensure_version_header(claude_md_path: str | Path, version: tuple[int, int, int] = (1, 0, 0)) -> None:
    """Add version header to CLAUDE.md if not present."""
    path = Path(claude_md_path)
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8")
    if _VERSION_RE.search(content.split("\n", 1)[0]):
        return  # Already has version
    version_line = f"<!-- version: {format_version(*version)} -->\n"
    path.write_text(version_line + content, encoding="utf-8")


def bump_version(
    claude_md_path: str | Path,
    bump_type: str = "patch",
) -> tuple[int, int, int]:
    """Bump the version in CLAUDE.md and return the new version.

    If no version header exists, creates one at (1, 0, 0) then bumps.
    """
    path = Path(claude_md_path)
    if not path.exists():
        return (0, 0, 0)

    major, minor, patch = get_current_version(path)
    if (major, minor, patch) == (0, 0, 0):
        ensure_version_header(path, (1, 0, 0))
        major, minor, patch = 1, 0, 0

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    else:  # patch
        patch += 1

    content = path.read_text(encoding="utf-8")
    new_version_line = f"<!-- version: {format_version(major, minor, patch)} -->"

    if _VERSION_RE.search(content):
        content = _VERSION_RE.sub(new_version_line, content, count=1)
    else:
        content = new_version_line + "\n" + content

    path.write_text(content, encoding="utf-8")
    return (major, minor, patch)


def detect_bump_type(diff_text: str) -> str:
    """Analyze a git diff of CLAUDE.md to determine bump type.

    Returns "major", "minor", or "patch".
    """
    lines = diff_text.splitlines()

    for pattern in _MAJOR_PATTERNS:
        for line in lines:
            if re.search(pattern, line):
                return "major"

    for pattern in _MINOR_PATTERNS:
        for line in lines:
            if re.search(pattern, line):
                return "minor"

    return "patch"
