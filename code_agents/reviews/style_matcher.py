"""Style Matcher — detects code style patterns in a repo and generates style rules.

Scans a sample of source files to detect indentation, quoting, naming conventions,
line length, import style, and docstring format. Generates a concise (<100 token)
style guide for injection into agent prompts.

Results are cached per repo path so the scan only runs once per session.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Data model ──────────────────────────────────────────────────────────────

@dataclass
class StyleProfile:
    """Detected code style for a repository."""

    language: str = "unknown"
    indent_style: str = "spaces"        # "spaces" or "tabs"
    indent_size: int = 4                # 2 or 4
    quote_style: str = "double"         # "single" or "double"
    naming_convention: str = "snake_case"  # "snake_case", "camelCase", "PascalCase"
    max_line_length: int = 120
    import_style: str = "grouped"       # "grouped" or "individual"
    trailing_comma: bool = False
    semicolons: bool = False            # JS/TS
    type_hints: bool = False            # Python
    docstring_style: str = "google"     # "google", "numpy", "sphinx", "javadoc"


# ── File discovery ──────────────────────────────────────────────────────────

_LANG_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".kt": "kotlin",
    ".scala": "scala",
    ".rs": "rust",
}

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "target", ".gradle", ".idea", ".vscode",
}

_MAX_SAMPLE = 20  # max files to sample


def _find_source_files(cwd: str, limit: int = _MAX_SAMPLE) -> list[str]:
    """Walk *cwd* and return up to *limit* source files, preferring the dominant language."""
    candidates: dict[str, list[str]] = {}  # ext -> [paths]
    root = Path(cwd)

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped dirs in-place
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext in _LANG_EXTENSIONS:
                full = os.path.join(dirpath, fname)
                candidates.setdefault(ext, []).append(full)
        # Early exit if we already have plenty
        total = sum(len(v) for v in candidates.values())
        if total >= limit * 3:
            break

    if not candidates:
        return []

    # Pick dominant language
    dominant_ext = max(candidates, key=lambda e: len(candidates[e]))
    files = candidates[dominant_ext]

    # Sort by path length (prefer shallow files) and take limit
    files.sort(key=lambda p: (len(p), p))
    return files[:limit]


# ── Analysis helpers ────────────────────────────────────────────────────────

def _detect_indent(lines: list[str]) -> tuple[str, int]:
    """Return (style, size) by majority vote on leading whitespace."""
    tab_count = 0
    space_counts: dict[int, int] = {}

    for line in lines:
        if not line or not line[0] in (" ", "\t"):
            continue
        stripped = line.lstrip()
        if not stripped:
            continue
        leading = line[: len(line) - len(stripped)]
        if "\t" in leading:
            tab_count += 1
        else:
            n = len(leading)
            if n > 0:
                space_counts[n] = space_counts.get(n, 0) + 1

    if tab_count > sum(space_counts.values()):
        return ("tabs", 4)

    # Guess size: find the GCD of most common indent levels, then pick nearest standard
    if space_counts:
        # Find the minimum non-zero indent level that appears frequently
        total = sum(space_counts.values())
        # Sort by indent level
        sorted_levels = sorted(space_counts.keys())
        if sorted_levels:
            min_indent = sorted_levels[0]
            # Check if 4 divides all common levels
            for size in (4, 2, 8):
                matching = sum(v for k, v in space_counts.items() if k % size == 0)
                if matching >= total * 0.7:
                    return ("spaces", size)
            # Fall back to smallest indent seen
            if min_indent in (2, 4, 8):
                return ("spaces", min_indent)
    return ("spaces", 4)


def _detect_quotes(content: str, language: str) -> str:
    """Detect dominant quote style."""
    if language in ("python", "ruby"):
        singles = len(re.findall(r"(?<!['\"])('[^'\\]*(?:\\.[^'\\]*)*')(?!['\"])", content))
        doubles = len(re.findall(r'(?<![\'"])("[^"\\]*(?:\\.[^"\\]*)*")(?![\'"])', content))
    else:
        singles = content.count("'")
        doubles = content.count('"')
    return "single" if singles > doubles else "double"


def _detect_naming(content: str, language: str) -> str:
    """Detect dominant naming convention from function/variable definitions."""
    if language == "python":
        funcs = re.findall(r"def\s+([a-zA-Z_]\w*)", content)
    elif language in ("javascript", "typescript"):
        funcs = re.findall(r"(?:function|const|let|var)\s+([a-zA-Z_]\w*)", content)
    elif language == "java":
        funcs = re.findall(r"(?:public|private|protected|static)\s+\w+\s+([a-zA-Z_]\w*)\s*\(", content)
    elif language == "go":
        funcs = re.findall(r"func\s+(?:\([^)]+\)\s+)?([a-zA-Z_]\w*)", content)
    else:
        funcs = re.findall(r"def\s+([a-zA-Z_]\w*)", content)

    if not funcs:
        return "snake_case"

    snake = sum(1 for f in funcs if "_" in f and f == f.lower())
    camel = sum(1 for f in funcs if f[0].islower() and any(c.isupper() for c in f) and "_" not in f)
    pascal = sum(1 for f in funcs if f[0].isupper() and "_" not in f)

    if pascal > snake and pascal > camel:
        return "PascalCase"
    if camel > snake:
        return "camelCase"
    return "snake_case"


def _detect_max_line_length(lines: list[str]) -> int:
    """Return the p95 line length, rounded to nearest 10."""
    lengths = sorted(len(line.rstrip()) for line in lines if line.strip())
    if not lengths:
        return 120
    idx = int(len(lengths) * 0.95)
    p95 = lengths[min(idx, len(lengths) - 1)]
    # Round to nearest standard: 80, 100, 120, 150
    for std in (80, 100, 120, 150, 200):
        if p95 <= std + 10:
            return std
    return 120


def _detect_import_style(content: str, language: str) -> str:
    """Detect grouped vs individual imports."""
    if language == "python":
        from_imports = len(re.findall(r"^from\s+\S+\s+import\s+", content, re.MULTILINE))
        plain_imports = len(re.findall(r"^import\s+\S+", content, re.MULTILINE))
        return "grouped" if from_imports > plain_imports else "individual"
    if language in ("javascript", "typescript"):
        destructured = len(re.findall(r"import\s*\{", content))
        default_imports = len(re.findall(r"import\s+\w+\s+from", content))
        return "grouped" if destructured > default_imports else "individual"
    return "grouped"


def _detect_trailing_comma(content: str) -> bool:
    """Check for trailing commas before closing brackets."""
    # Match comma followed by optional whitespace/newlines then a closing bracket
    trailing = len(re.findall(r",\s*[\]\)}]", content))
    total_close = len(re.findall(r"[\]\)}]", content))
    return trailing > total_close * 0.3 if total_close else False


def _detect_semicolons(content: str) -> bool:
    """Detect semicolons at end of lines (JS/TS)."""
    lines_with = len(re.findall(r";\s*$", content, re.MULTILINE))
    non_empty = len([l for l in content.splitlines() if l.strip()])
    return lines_with > non_empty * 0.3 if non_empty else False


def _detect_type_hints(content: str) -> bool:
    """Detect Python type hints."""
    hints = len(re.findall(r"def\s+\w+\([^)]*:\s*\w+", content))
    arrow = len(re.findall(r"\)\s*->\s*\w+", content))
    total_defs = len(re.findall(r"def\s+\w+", content))
    return (hints + arrow) > total_defs * 0.3 if total_defs else False


def _detect_docstring_style(content: str, language: str) -> str:
    """Detect docstring/comment style."""
    if language == "python":
        if re.search(r'""".*\n\s+Args:', content):
            return "google"
        if re.search(r'""".*\n\s+Parameters\n\s+-+', content):
            return "numpy"
        if re.search(r'""".*\n\s+:param\s', content):
            return "sphinx"
        return "google"
    if language in ("java", "kotlin", "scala"):
        if re.search(r"/\*\*.*@param", content, re.DOTALL):
            return "javadoc"
    return "google"


# ── Main class ──────────────────────────────────────────────────────────────

# Module-level cache: repo_path -> StyleProfile
_cache: dict[str, StyleProfile] = {}


class StyleMatcher:
    """Analyze a repository's code style and generate prompt-ready style rules."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self) -> StyleProfile:
        """Analyze repo source files and return a StyleProfile. Uses cache."""
        if self.cwd in _cache:
            return _cache[self.cwd]

        files = _find_source_files(self.cwd)
        if not files:
            profile = StyleProfile()
            _cache[self.cwd] = profile
            return profile

        # Determine dominant language
        ext = Path(files[0]).suffix.lower()
        language = _LANG_EXTENSIONS.get(ext, "unknown")

        all_lines: list[str] = []
        all_content = ""

        for fpath in files:
            try:
                text = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                all_content += text + "\n"
                all_lines.extend(text.splitlines())
            except OSError:
                continue

        if not all_lines:
            profile = StyleProfile(language=language)
            _cache[self.cwd] = profile
            return profile

        indent_style, indent_size = _detect_indent(all_lines)

        profile = StyleProfile(
            language=language,
            indent_style=indent_style,
            indent_size=indent_size,
            quote_style=_detect_quotes(all_content, language),
            naming_convention=_detect_naming(all_content, language),
            max_line_length=_detect_max_line_length(all_lines),
            import_style=_detect_import_style(all_content, language),
            trailing_comma=_detect_trailing_comma(all_content),
            semicolons=_detect_semicolons(all_content) if language in ("javascript", "typescript") else False,
            type_hints=_detect_type_hints(all_content) if language == "python" else False,
            docstring_style=_detect_docstring_style(all_content, language),
        )

        logger.info(
            "StyleMatcher: repo=%s lang=%s indent=%s/%d quotes=%s naming=%s lines=%d files=%d",
            self.cwd, language, indent_style, indent_size,
            profile.quote_style, profile.naming_convention,
            profile.max_line_length, len(files),
        )

        _cache[self.cwd] = profile
        return profile

    @staticmethod
    def generate_style_prompt(profile: StyleProfile) -> str:
        """Generate a concise style guide string (<100 tokens) for agent prompt injection."""
        parts = [f"Code Style ({profile.language}):"]
        parts.append(f"{profile.indent_size}-{profile.indent_style} indent")
        parts.append(f"{profile.quote_style} quotes")
        parts.append(profile.naming_convention)
        parts.append(f"{profile.docstring_style} docstrings")
        parts.append(f"max {profile.max_line_length} chars/line")
        parts.append(f"{profile.import_style} imports")

        if profile.trailing_comma:
            parts.append("trailing commas")
        if profile.language in ("javascript", "typescript"):
            parts.append("semicolons" if profile.semicolons else "no semicolons")
        if profile.language == "python" and profile.type_hints:
            parts.append("type hints")

        return ", ".join(parts) + "."

    @staticmethod
    def format_display(profile: StyleProfile) -> str:
        """Human-readable style report for /style command."""
        lines = [
            f"  Language:       {profile.language}",
            f"  Indentation:    {profile.indent_size} {profile.indent_style}",
            f"  Quotes:         {profile.quote_style}",
            f"  Naming:         {profile.naming_convention}",
            f"  Max line:       {profile.max_line_length} chars",
            f"  Imports:        {profile.import_style}",
            f"  Trailing comma: {'yes' if profile.trailing_comma else 'no'}",
            f"  Docstrings:     {profile.docstring_style}",
        ]
        if profile.language in ("javascript", "typescript"):
            lines.append(f"  Semicolons:     {'yes' if profile.semicolons else 'no'}")
        if profile.language == "python":
            lines.append(f"  Type hints:     {'yes' if profile.type_hints else 'no'}")
        return "\n".join(lines)


def get_style_prompt(cwd: str) -> str:
    """Convenience: analyze repo and return the style prompt string. Cached."""
    matcher = StyleMatcher(cwd)
    profile = matcher.analyze()
    if profile.language == "unknown":
        return ""
    return StyleMatcher.generate_style_prompt(profile)


def clear_cache(cwd: Optional[str] = None) -> None:
    """Clear cached StyleProfile(s). If cwd is None, clear all."""
    if cwd is None:
        _cache.clear()
    else:
        _cache.pop(cwd, None)
