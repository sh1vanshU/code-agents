"""Pattern matchers — shared utilities for codebase search.

Used by: usage_tracer, codebase_nav, code_example, vuln_fixer,
         secret_scanner, techdebt_scanner, code_audit, etc.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.tools._pattern_matchers")

# Directories to skip
SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
    "target", ".gradle", ".idea", ".vscode", ".eggs",
})

# Common code extensions
CODE_EXTS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".cs", ".swift",
    ".kt", ".scala", ".sh", ".yaml", ".yml", ".json", ".toml",
    ".sql", ".graphql", ".proto", ".tf", ".hcl",
})


@dataclass
class SearchMatch:
    """A single search match in a file."""
    file: str
    line: int
    content: str
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)


@dataclass
class UsageSite:
    """Where a symbol is used."""
    file: str
    line: int
    usage_type: str  # "import", "call", "assignment", "reference", "config", "test"
    content: str = ""
    function_context: str = ""  # enclosing function name


@dataclass
class FileMatch:
    """A file matching a pattern."""
    path: str
    relative_path: str = ""
    size: int = 0
    language: str = ""


def grep_codebase(
    cwd: str,
    pattern: str,
    extensions: Optional[frozenset[str]] = None,
    max_results: int = 200,
    context_lines: int = 2,
    case_sensitive: bool = True,
) -> list[SearchMatch]:
    """Search codebase using ripgrep (rg) or grep fallback."""
    exts = extensions or CODE_EXTS
    matches: list[SearchMatch] = []

    # Try ripgrep first
    rg_available = _check_tool("rg")
    if rg_available:
        args = ["rg", "--line-number", f"--max-count={max_results}",
                f"-C{context_lines}", "--no-heading"]
        if not case_sensitive:
            args.append("-i")
        for ext in exts:
            args.extend(["--glob", f"*{ext}"])
        args.append(pattern)
        matches = _parse_rg_output(cwd, args)
    else:
        # Fallback to Python-based search
        matches = _python_grep(cwd, pattern, exts, max_results, context_lines, case_sensitive)

    return matches[:max_results]


def find_usage_sites(
    cwd: str,
    symbol_name: str,
    max_results: int = 100,
) -> list[UsageSite]:
    """Find all usage sites of a symbol across the codebase."""
    sites: list[UsageSite] = []
    raw_matches = grep_codebase(cwd, re.escape(symbol_name), max_results=max_results * 2)

    for match in raw_matches:
        content = match.content.strip()
        usage_type = _classify_usage(content, symbol_name, match.file)
        sites.append(UsageSite(
            file=match.file,
            line=match.line,
            usage_type=usage_type,
            content=content,
        ))

    # Deduplicate and limit
    seen = set()
    unique: list[UsageSite] = []
    for site in sites:
        key = (site.file, site.line)
        if key not in seen:
            seen.add(key)
            unique.append(site)
    return unique[:max_results]


def find_files_by_pattern(
    cwd: str,
    glob_pattern: str = "**/*.py",
    max_results: int = 500,
) -> list[FileMatch]:
    """Find files matching a glob pattern."""
    results: list[FileMatch] = []
    base = Path(cwd)
    for fpath in base.glob(glob_pattern):
        if any(part in SKIP_DIRS for part in fpath.parts):
            continue
        if fpath.is_file():
            results.append(FileMatch(
                path=str(fpath),
                relative_path=str(fpath.relative_to(base)),
                size=fpath.stat().st_size if fpath.exists() else 0,
                language=_ext_to_language(fpath.suffix),
            ))
            if len(results) >= max_results:
                break
    return results


def find_definitions(cwd: str, symbol_name: str) -> list[SearchMatch]:
    """Find where a symbol is defined (function def, class def, assignment)."""
    patterns = [
        rf"(def|class)\s+{re.escape(symbol_name)}\s*[\(:]",  # Python
        rf"(function|const|let|var)\s+{re.escape(symbol_name)}\s*[=(]",  # JS/TS
        rf"(func)\s+{re.escape(symbol_name)}\s*\(",  # Go
        rf"(public|private|protected)?\s+\w+\s+{re.escape(symbol_name)}\s*\(",  # Java
    ]
    all_matches: list[SearchMatch] = []
    for pat in patterns:
        all_matches.extend(grep_codebase(cwd, pat, max_results=20))
    return all_matches


# --- Internal helpers ---

def _check_tool(name: str) -> bool:
    """Check if a CLI tool is available."""
    try:
        subprocess.run([name, "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _parse_rg_output(cwd: str, args: list[str]) -> list[SearchMatch]:
    """Parse ripgrep output into SearchMatch objects."""
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)
        output = result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return []

    matches: list[SearchMatch] = []
    for line in output.splitlines():
        # Format: file:line:content or file-line-content (context)
        sep_match = re.match(r"^(.+?)[:-](\d+)[:-](.*)$", line)
        if sep_match:
            matches.append(SearchMatch(
                file=sep_match.group(1),
                line=int(sep_match.group(2)),
                content=sep_match.group(3),
            ))
    return matches


def _python_grep(
    cwd: str, pattern: str, extensions: frozenset[str],
    max_results: int, context_lines: int, case_sensitive: bool,
) -> list[SearchMatch]:
    """Pure Python grep fallback."""
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error:
        return []

    matches: list[SearchMatch] = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if Path(fname).suffix not in extensions:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                for i, line in enumerate(lines, 1):
                    if regex.search(line):
                        before = [l.rstrip() for l in lines[max(0, i-1-context_lines):i-1]]
                        after = [l.rstrip() for l in lines[i:i+context_lines]]
                        matches.append(SearchMatch(
                            file=os.path.relpath(fpath, cwd),
                            line=i,
                            content=line.rstrip(),
                            context_before=before,
                            context_after=after,
                        ))
                        if len(matches) >= max_results:
                            return matches
            except (OSError, UnicodeDecodeError):
                continue
    return matches


def _classify_usage(content: str, symbol: str, file_path: str) -> str:
    """Classify what kind of usage a line represents."""
    stripped = content.strip()
    if re.match(r"^(from|import)\s+", stripped):
        return "import"
    if re.match(rf"^(def|class)\s+{re.escape(symbol)}", stripped):
        return "definition"
    if "test" in file_path.lower() or "test" in stripped.lower()[:30]:
        return "test"
    if re.search(rf"{re.escape(symbol)}\s*=", stripped):
        return "assignment"
    if re.search(rf"{re.escape(symbol)}\s*\(", stripped):
        return "call"
    if ".yaml" in file_path or ".yml" in file_path or ".json" in file_path or ".toml" in file_path:
        return "config"
    return "reference"


def _ext_to_language(ext: str) -> str:
    """Map file extension to language name."""
    mapping = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "react", ".tsx": "react-ts", ".java": "java",
        ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
        ".c": "c", ".cpp": "cpp", ".cs": "csharp", ".swift": "swift",
        ".kt": "kotlin", ".scala": "scala", ".sh": "shell",
        ".yaml": "yaml", ".yml": "yaml", ".json": "json",
        ".toml": "toml", ".sql": "sql", ".proto": "protobuf",
        ".tf": "terraform", ".hcl": "hcl", ".graphql": "graphql",
    }
    return mapping.get(ext, ext.lstrip("."))
