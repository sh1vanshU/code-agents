"""Language-aware source code parsers for the knowledge graph.

Each parser extracts symbols (functions, classes, methods, imports) from
source files and returns a common ``ModuleInfo`` structure.  The dispatcher
``parse_file()`` routes to the appropriate parser based on file extension.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.parsers")

# ---------------------------------------------------------------------------
# Common data structures
# ---------------------------------------------------------------------------


@dataclass
class SymbolInfo:
    """A single symbol (function, class, method, variable, import) in a file."""
    name: str
    kind: str           # "function", "class", "method", "variable", "import"
    file_path: str
    line_number: int
    signature: str = ""    # e.g. "def foo(bar: int) -> str"
    docstring: str = ""    # first line only


@dataclass
class ModuleInfo:
    """Parsed information about a single source file."""
    file_path: str
    language: str
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extension → language mapping
# ---------------------------------------------------------------------------

_EXT_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".php": "php",
}


def detect_language(file_path: str) -> str:
    """Detect language from file extension."""
    ext = Path(file_path).suffix.lower()
    return _EXT_LANGUAGE.get(ext, "unknown")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def parse_file(file_path: str, language: str = "") -> ModuleInfo:
    """Parse a source file and return its symbols and imports.

    Falls back to generic regex parser for unsupported languages.
    """
    if not language:
        language = detect_language(file_path)

    try:
        if language == "python":
            from .python_parser import parse_python
            return parse_python(file_path)
        elif language in ("javascript", "typescript"):
            from .javascript_parser import parse_javascript
            return parse_javascript(file_path, language)
        elif language == "java":
            from .java_parser import parse_java
            return parse_java(file_path)
        elif language == "go":
            from .go_parser import parse_go
            return parse_go(file_path)
        else:
            from .generic_parser import parse_generic
            return parse_generic(file_path, language)
    except Exception as e:
        logger.debug("Failed to parse %s: %s", file_path, e)
        return ModuleInfo(file_path=file_path, language=language)
