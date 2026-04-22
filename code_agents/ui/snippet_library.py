"""Smart Snippet Library — save, search, and reuse code snippets.

Stores snippets as JSON files in ~/.code-agents/snippets/.
Supports tagging, language filtering, and project-specific adaptation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.ui.snippet_library")

_SNIPPETS_DIR = os.path.join(os.path.expanduser("~"), ".code-agents", "snippets")


@dataclass
class Snippet:
    """A reusable code snippet with metadata."""

    name: str
    language: str
    code: str
    tags: list[str]
    description: str = ""


class SnippetLibrary:
    """Manage a personal library of reusable code snippets."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.snippets_dir = Path(_SNIPPETS_DIR)
        self.snippets_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("SnippetLibrary initialized, dir=%s cwd=%s", self.snippets_dir, cwd)

    # ── Public API ──────────────────────────────────────────────

    def save(
        self,
        name: str,
        code: str,
        language: str = "",
        tags: list[str] | None = None,
        description: str = "",
    ) -> Snippet:
        """Save a snippet to the library.

        Args:
            name: Unique snippet name (used as filename).
            code: The code content.
            language: Programming language (e.g. python, javascript).
            tags: Optional list of tags for categorization.
            description: Human-readable description.

        Returns:
            The saved Snippet dataclass.
        """
        if not name or not name.strip():
            raise ValueError("Snippet name cannot be empty")
        if not code or not code.strip():
            raise ValueError("Snippet code cannot be empty")

        safe_name = self._safe_name(name)
        snippet = Snippet(
            name=safe_name,
            language=language.lower().strip() if language else self._detect_language(code),
            code=code,
            tags=[t.lower().strip() for t in (tags or [])],
            description=description.strip(),
        )

        path = self.snippets_dir / f"{safe_name}.json"
        path.write_text(json.dumps(asdict(snippet), indent=2), encoding="utf-8")
        logger.info("Saved snippet '%s' → %s", safe_name, path)
        return snippet

    def search(self, query: str, language: str = "") -> list[Snippet]:
        """Search snippets by query string (matches name, tags, description, code).

        Args:
            query: Search query — matched against all fields.
            language: Optional language filter.

        Returns:
            List of matching Snippet objects, best matches first.
        """
        query_lower = query.lower().strip()
        if not query_lower:
            return self.list_snippets(language=language)

        results: list[tuple[int, Snippet]] = []
        for snippet in self._load_all():
            if language and snippet.language != language.lower().strip():
                continue
            score = self._score_match(snippet, query_lower)
            if score > 0:
                results.append((score, snippet))

        results.sort(key=lambda x: x[0], reverse=True)
        found = [s for _, s in results]
        logger.debug("Search '%s' (lang=%s) → %d results", query, language, len(found))
        return found

    def list_snippets(self, tag: str = "", language: str = "") -> list[Snippet]:
        """List all snippets, optionally filtered by tag or language.

        Args:
            tag: Optional tag filter.
            language: Optional language filter.

        Returns:
            List of Snippet objects matching filters.
        """
        tag_lower = tag.lower().strip() if tag else ""
        lang_lower = language.lower().strip() if language else ""
        snippets = self._load_all()

        if tag_lower:
            snippets = [s for s in snippets if tag_lower in s.tags]
        if lang_lower:
            snippets = [s for s in snippets if s.language == lang_lower]

        snippets.sort(key=lambda s: s.name)
        logger.debug("list_snippets(tag=%s, lang=%s) → %d", tag, language, len(snippets))
        return snippets

    def delete(self, name: str) -> bool:
        """Delete a snippet by name.

        Args:
            name: The snippet name to delete.

        Returns:
            True if deleted, False if not found.
        """
        safe_name = self._safe_name(name)
        path = self.snippets_dir / f"{safe_name}.json"
        if path.exists():
            path.unlink()
            logger.info("Deleted snippet '%s'", safe_name)
            return True
        logger.warning("Snippet '%s' not found for deletion", safe_name)
        return False

    def get(self, name: str) -> Snippet | None:
        """Get a single snippet by name.

        Args:
            name: The snippet name.

        Returns:
            Snippet or None if not found.
        """
        safe_name = self._safe_name(name)
        path = self.snippets_dir / f"{safe_name}.json"
        if not path.exists():
            return None
        return self._load_snippet(path)

    def _adapt_to_project(self, snippet: Snippet) -> str:
        """Adapt snippet code to match local project conventions.

        Inspects the cwd for common patterns (indent style, quote style, etc.)
        and adjusts the snippet code accordingly.

        Args:
            snippet: The snippet to adapt.

        Returns:
            Adapted code string.
        """
        code = snippet.code

        # Detect project indent style from a sample file
        indent = self._detect_project_indent()
        if indent == "tabs":
            code = re.sub(r"^( {4})", "\t", code, flags=re.MULTILINE)
        elif indent == "2spaces":
            code = re.sub(r"^( {4})", "  ", code, flags=re.MULTILINE)

        # Detect quote style for Python/JS
        quote_style = self._detect_project_quotes(snippet.language)
        if quote_style == "single" and snippet.language in ("python", "javascript", "typescript"):
            code = self._convert_quotes(code, to_single=True)
        elif quote_style == "double" and snippet.language in ("python", "javascript", "typescript"):
            code = self._convert_quotes(code, to_single=False)

        logger.debug("Adapted snippet '%s' for project conventions", snippet.name)
        return code

    # ── Private helpers ─────────────────────────────────────────

    def _load_all(self) -> list[Snippet]:
        """Load all snippets from disk."""
        snippets: list[Snippet] = []
        if not self.snippets_dir.exists():
            return snippets
        for path in sorted(self.snippets_dir.glob("*.json")):
            s = self._load_snippet(path)
            if s:
                snippets.append(s)
        return snippets

    def _load_snippet(self, path: Path) -> Snippet | None:
        """Load a single snippet from a JSON file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Snippet(
                name=data.get("name", path.stem),
                language=data.get("language", ""),
                code=data.get("code", ""),
                tags=data.get("tags", []),
                description=data.get("description", ""),
            )
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to load snippet %s: %s", path, exc)
            return None

    @staticmethod
    def _safe_name(name: str) -> str:
        """Sanitize snippet name for use as a filename."""
        safe = re.sub(r"[^\w\-]", "_", name.strip().lower())
        return safe or "unnamed"

    @staticmethod
    def _detect_language(code: str) -> str:
        """Best-effort language detection from code content."""
        if "def " in code and "import " in code:
            return "python"
        if "function " in code or "const " in code or "=>" in code:
            return "javascript"
        if "func " in code and "package " in code:
            return "go"
        if "public class " in code or "private " in code:
            return "java"
        if re.search(r"<[a-zA-Z][^>]*>", code) and ("class=" in code or "className=" in code):
            return "html"
        return "text"

    @staticmethod
    def _score_match(snippet: Snippet, query: str) -> int:
        """Score how well a snippet matches a query. Higher = better."""
        score = 0
        # Exact name match
        if query == snippet.name:
            score += 100
        elif query in snippet.name:
            score += 50
        # Tag match
        for tag in snippet.tags:
            if query == tag:
                score += 40
            elif query in tag:
                score += 20
        # Description match
        if query in snippet.description.lower():
            score += 30
        # Code content match
        if query in snippet.code.lower():
            score += 10
        # Multi-word: check each word
        words = query.split()
        if len(words) > 1:
            all_text = f"{snippet.name} {snippet.description} {' '.join(snippet.tags)} {snippet.code}".lower()
            matching_words = sum(1 for w in words if w in all_text)
            score += matching_words * 15
        return score

    def _detect_project_indent(self) -> str:
        """Detect indentation style in the project."""
        sample_files = list(Path(self.cwd).glob("*.py"))[:5]
        if not sample_files:
            sample_files = list(Path(self.cwd).glob("*.js"))[:5]
        tabs = 0
        spaces2 = 0
        spaces4 = 0
        for fpath in sample_files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines()[:100]:
                    if line.startswith("\t"):
                        tabs += 1
                    elif line.startswith("  ") and not line.startswith("    "):
                        spaces2 += 1
                    elif line.startswith("    "):
                        spaces4 += 1
            except OSError:
                continue
        if tabs > spaces2 and tabs > spaces4:
            return "tabs"
        if spaces2 > spaces4:
            return "2spaces"
        return "4spaces"

    def _detect_project_quotes(self, language: str) -> str:
        """Detect quote style preference in project files."""
        ext = {"python": "*.py", "javascript": "*.js", "typescript": "*.ts"}.get(language, "")
        if not ext:
            return ""
        sample_files = list(Path(self.cwd).glob(ext))[:5]
        single = 0
        double = 0
        for fpath in sample_files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                single += content.count("'")
                double += content.count('"')
            except OSError:
                continue
        if single > double * 1.5:
            return "single"
        if double > single * 1.5:
            return "double"
        return ""

    @staticmethod
    def _convert_quotes(code: str, to_single: bool) -> str:
        """Convert string quotes in code (simple heuristic, not a parser)."""
        if to_single:
            return re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', r"'\1'", code)
        return re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', code)
