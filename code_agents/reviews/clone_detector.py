"""Code clone detector — find duplicated code blocks across a codebase.

Uses token-level rolling hashes to detect near-duplicate code fragments
(Type-1, Type-2, and partial Type-3 clones).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.reviews.clone_detector")

# File extensions to scan
SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rb", ".rs", ".c", ".cpp", ".h", ".hpp", ".cs",
    ".swift", ".kt", ".scala", ".php",
}

# Directories to skip
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "vendor", "target", ".next", ".nuxt",
}

# Common comment patterns (simplified)
COMMENT_RE = re.compile(
    r"(#.*?$|//.*?$|/\*.*?\*/)",
    re.MULTILINE | re.DOTALL,
)

# String literal pattern
STRING_RE = re.compile(r"""(['"])(?:(?!\1|\\).|\\.)*\1""")

# Identifier normalization — replace variable names with placeholder
IDENT_RE = re.compile(r"\b[a-zA-Z_]\w*\b")

# Common keywords that should NOT be normalized
KEYWORDS = {
    "if", "else", "for", "while", "return", "def", "class", "import",
    "from", "try", "except", "finally", "with", "as", "in", "not",
    "and", "or", "is", "True", "False", "None", "function", "const",
    "let", "var", "new", "this", "self", "public", "private",
    "protected", "static", "void", "int", "str", "float", "bool",
    "async", "await", "yield", "raise", "break", "continue",
    "switch", "case", "default", "do", "throw", "catch",
    "interface", "struct", "enum", "type", "extends", "implements",
}


@dataclass
class CloneGroup:
    """A group of code blocks that are near-duplicates of each other."""

    blocks: list[dict] = field(default_factory=list)
    # Each block: {file: str, start_line: int, end_line: int, content: str}
    similarity: float = 0.0
    token_count: int = 0


class CloneDetector:
    """Detect code clones (duplicated code blocks) across a codebase."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("CloneDetector initialized for %s", cwd)

    def detect(
        self,
        threshold: float = 0.8,
        min_tokens: int = 50,
        window: int = 20,
    ) -> list[CloneGroup]:
        """Detect code clones across the codebase.

        Args:
            threshold: Minimum Jaccard similarity to consider a clone (0.0-1.0).
            min_tokens: Minimum number of tokens in a block to consider.
            window: Rolling hash window size in tokens.

        Returns:
            List of CloneGroup instances, sorted by token count descending.
        """
        logger.info(
            "Detecting clones (threshold=%.2f, min_tokens=%d, window=%d)",
            threshold, min_tokens, window,
        )

        # Collect all source files
        files = self._collect_files()
        logger.info("Scanning %d source files", len(files))

        if not files:
            return []

        # Tokenize and hash all files
        all_hashes: dict[str, list[dict]] = {}
        for fpath in files:
            try:
                with open(fpath) as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            tokens = self._tokenize(content)
            if len(tokens) < min_tokens:
                continue

            rel_path = os.path.relpath(fpath, self.cwd)
            file_hashes = self._hash_blocks(tokens, window=window)
            for h, locations in file_hashes.items():
                if h not in all_hashes:
                    all_hashes[h] = []
                for loc in locations:
                    loc["file"] = rel_path
                    loc["content"] = content
                all_hashes[h].extend(locations)

        # Find matches
        groups = self._find_matches(all_hashes, threshold, min_tokens)

        # Sort by token count (larger clones first)
        groups.sort(key=lambda g: g.token_count, reverse=True)

        logger.info("Found %d clone groups", len(groups))
        return groups

    def _collect_files(self) -> list[str]:
        """Collect all source files in the project."""
        files: list[str] = []
        for root, dirs, filenames in os.walk(self.cwd):
            # Filter out skip directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    files.append(os.path.join(root, fname))

        return files

    def _tokenize(self, content: str) -> list[str]:
        """Normalize and tokenize source code.

        Strips comments, normalizes whitespace, and replaces identifiers
        with a placeholder to detect Type-2 clones (renamed variables).
        """
        # Remove comments
        normalized = COMMENT_RE.sub("", content)

        # Remove string literals (replace with placeholder)
        normalized = STRING_RE.sub('"S"', normalized)

        # Tokenize: split on non-word characters
        raw_tokens = re.findall(r"\S+", normalized)

        # Normalize identifiers
        result: list[str] = []
        for token in raw_tokens:
            # Replace identifiers (not keywords) with placeholder
            def _replace_ident(m: re.Match) -> str:
                word = m.group(0)
                if word in KEYWORDS:
                    return word
                return "$V"

            normalized_token = IDENT_RE.sub(_replace_ident, token)
            if normalized_token.strip():
                result.append(normalized_token)

        return result

    def _hash_blocks(
        self, tokens: list[str], window: int = 20
    ) -> dict[str, list[dict]]:
        """Create rolling hash fingerprints for token windows.

        Args:
            tokens: List of normalized tokens.
            window: Window size for the rolling hash.

        Returns:
            Dict mapping hash -> list of {start_token, end_token} locations.
        """
        hashes: dict[str, list[dict]] = defaultdict(list)

        if len(tokens) < window:
            return dict(hashes)

        for i in range(len(tokens) - window + 1):
            block = tokens[i:i + window]
            block_str = " ".join(block)
            h = hashlib.md5(block_str.encode()).hexdigest()
            hashes[h].append({
                "start_token": i,
                "end_token": i + window,
                "token_count": window,
            })

        return dict(hashes)

    def _find_matches(
        self,
        hashes: dict[str, list[dict]],
        threshold: float,
        min_tokens: int,
    ) -> list[CloneGroup]:
        """Find clone groups from hash matches.

        Groups locations that share the same hash and are in different
        files (or far apart in the same file).
        """
        groups: list[CloneGroup] = []
        seen_pairs: set[tuple[str, int, str, int]] = set()

        for h, locations in hashes.items():
            if len(locations) < 2:
                continue

            # Group by unique file+position
            unique_locs: list[dict] = []
            for loc in locations:
                key = (loc.get("file", ""), loc.get("start_token", 0))
                is_dup = False
                for ul in unique_locs:
                    if (ul.get("file") == loc.get("file")
                            and abs(ul.get("start_token", 0) - loc.get("start_token", 0)) < 5):
                        is_dup = True
                        break
                if not is_dup:
                    unique_locs.append(loc)

            if len(unique_locs) < 2:
                continue

            # Build clone blocks
            blocks: list[dict] = []
            for loc in unique_locs:
                content = loc.get("content", "")
                lines = content.split("\n")
                # Estimate line numbers from token position
                # Rough: assume ~5 tokens per line
                est_start = max(1, loc.get("start_token", 0) // 5 + 1)
                est_end = min(len(lines), loc.get("end_token", 0) // 5 + 1)

                # Extract the code snippet
                snippet_lines = lines[est_start - 1:est_end]
                snippet = "\n".join(snippet_lines)

                blocks.append({
                    "file": loc.get("file", ""),
                    "start_line": est_start,
                    "end_line": est_end,
                    "content": snippet,
                })

            # Deduplicate: check if this pair was already seen
            if len(blocks) >= 2:
                pair_key = (
                    blocks[0]["file"], blocks[0]["start_line"],
                    blocks[1]["file"], blocks[1]["start_line"],
                )
                reverse_key = (
                    blocks[1]["file"], blocks[1]["start_line"],
                    blocks[0]["file"], blocks[0]["start_line"],
                )
                if pair_key in seen_pairs or reverse_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

            # Calculate similarity between first two blocks
            if len(blocks) >= 2:
                sim = self._calculate_similarity(
                    blocks[0]["content"], blocks[1]["content"]
                )
                if sim < threshold:
                    continue
            else:
                sim = 1.0

            token_count = unique_locs[0].get("token_count", min_tokens)

            groups.append(CloneGroup(
                blocks=blocks,
                similarity=sim,
                token_count=token_count,
            ))

        return groups

    def _calculate_similarity(self, a: str, b: str) -> float:
        """Calculate Jaccard similarity on token sets.

        Args:
            a: First code block.
            b: Second code block.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        tokens_a = set(self._tokenize(a))
        tokens_b = set(self._tokenize(b))

        if not tokens_a and not tokens_b:
            return 1.0
        if not tokens_a or not tokens_b:
            return 0.0

        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b

        return len(intersection) / len(union) if union else 0.0


def format_clone_report(groups: list[CloneGroup]) -> str:
    """Format clone detection results as a terminal-friendly report."""
    if not groups:
        return "\n  No code clones detected.\n"

    lines = [
        "",
        f"  Found {len(groups)} clone group(s):",
        "",
    ]

    for i, group in enumerate(groups[:20], 1):  # Cap at 20
        lines.append(
            f"  Clone #{i}  "
            f"(similarity: {group.similarity:.0%}, "
            f"tokens: {group.token_count})"
        )
        for block in group.blocks:
            lines.append(
                f"    {block['file']}:{block['start_line']}-{block['end_line']}"
            )
        lines.append("")

    if len(groups) > 20:
        lines.append(f"  ... and {len(groups) - 20} more clone groups")
        lines.append("")

    return "\n".join(lines)
