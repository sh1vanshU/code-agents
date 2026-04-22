"""AI Pair Programming Mode — file watcher that detects edits and proactively suggests improvements.

Watches source files for changes, analyzes diffs using pattern-based heuristics,
and renders non-blocking terminal suggestions for common issues.

Usage:
    code-agents pair                       # watch cwd, default patterns
    code-agents pair --watch-path src/     # watch specific directory
    code-agents pair --interval 2          # poll every 2s (default: 1s)
    code-agents pair --quiet               # suppress info messages
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.domain.pair_mode")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    "target", "vendor", ".idea", ".vscode", ".next", "coverage",
}

_DEFAULT_PATTERNS = ["*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.java", "*.go"]

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Suggestion:
    """A single improvement suggestion for a file change."""
    file: str
    line: int
    message: str
    severity: str  # "improvement", "warning", "bug"
    code_fix: str = ""


@dataclass
class FileChange:
    """Represents a single file change detected by pair mode."""
    file: str
    change_type: str  # "modified", "created", "deleted"
    diff_lines: list[str] = field(default_factory=list)
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Analysis patterns
# ---------------------------------------------------------------------------

# Each tuple: (regex_on_added_lines, severity, message)

_PYTHON_PATTERNS: list[tuple[str, str, str]] = [
    # Bug patterns
    (r"except\s*:", "bug", "Bare except — catches SystemExit/KeyboardInterrupt. Use 'except Exception:'"),
    (r"==\s*None", "bug", "Use 'is None' instead of '== None'"),
    (r"!=\s*None", "bug", "Use 'is not None' instead of '!= None'"),
    (r"def\s+\w+\([^)]*=\s*(\[\]|\{\}|\bset\(\))", "bug", "Mutable default argument — use None and assign inside function"),
    # Warning patterns
    (r"^\s*print\(", "warning", "Debug print() left in code"),
    (r"^\s*breakpoint\(\)", "warning", "Debugger breakpoint() left in code"),
    (r"^\s*import\s+pdb", "warning", "Debug import pdb left in code"),
    (r"^\s*# ?TODO", "warning", "TODO comment added — track or file ticket"),
    (r"^\s*# ?FIXME", "warning", "FIXME comment added — resolve before merging"),
    (r"^\s*# ?HACK", "warning", "HACK comment added — consider proper solution"),
    # Improvement patterns
    (r"def\s+\w+\([^)]*\)\s*:", "improvement", "Missing return type hint on function"),
    (r"^\s*pass\s*$", "improvement", "Empty pass block — is this intentional?"),
    (r"\.format\(", "improvement", "Consider using f-strings instead of .format()"),
]

_JS_TS_PATTERNS: list[tuple[str, str, str]] = [
    (r"console\.log\(", "warning", "Debug console.log() left in code"),
    (r"console\.debug\(", "warning", "Debug console.debug() left in code"),
    (r"debugger\s*;?", "warning", "Debugger statement left in code"),
    (r"==\s", "bug", "Use === instead of == for strict equality"),
    (r"!=\s", "bug", "Use !== instead of != for strict inequality"),
    (r"var\s+", "improvement", "Use 'const' or 'let' instead of 'var'"),
    (r"// ?TODO", "warning", "TODO comment added — track or file ticket"),
    (r"// ?FIXME", "warning", "FIXME comment added — resolve before merging"),
]

_JAVA_PATTERNS: list[tuple[str, str, str]] = [
    (r"System\.out\.print", "warning", "Debug System.out.println left in code — use a logger"),
    (r"e\.printStackTrace\(\)", "warning", "Use logger.error() instead of printStackTrace()"),
    (r"catch\s*\(\s*Exception\s+", "bug", "Catching generic Exception — catch specific exceptions"),
    (r"// ?TODO", "warning", "TODO comment added — track or file ticket"),
]

_GO_PATTERNS: list[tuple[str, str, str]] = [
    (r"fmt\.Print", "warning", "Debug fmt.Print left in code — use structured logging"),
    (r"//\s*TODO", "warning", "TODO comment added — track or file ticket"),
    (r"panic\(", "bug", "Direct panic() — consider returning an error instead"),
]

_GENERIC_PATTERNS: list[tuple[str, str, str]] = [
    (r"password\s*=\s*[\"']", "bug", "Hardcoded password detected — use environment variable"),
    (r"api[_-]?key\s*=\s*[\"']", "bug", "Hardcoded API key detected — use environment variable"),
    (r"secret\s*=\s*[\"']", "bug", "Hardcoded secret detected — use environment variable"),
]


def _get_patterns_for_file(filepath: str) -> list[tuple[str, str, str]]:
    """Return analysis patterns based on file extension."""
    ext = os.path.splitext(filepath)[1].lower()
    patterns = list(_GENERIC_PATTERNS)
    if ext == ".py":
        patterns.extend(_PYTHON_PATTERNS)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        patterns.extend(_JS_TS_PATTERNS)
    elif ext == ".java":
        patterns.extend(_JAVA_PATTERNS)
    elif ext == ".go":
        patterns.extend(_GO_PATTERNS)
    return patterns


def _check_unused_imports(filepath: str, diff: str) -> list[Suggestion]:
    """Check for potentially unused imports in added lines of a Python diff."""
    if not filepath.endswith(".py"):
        return []

    suggestions = []
    added_imports: list[tuple[str, str]] = []  # (name, full_line)

    for line_text in diff.splitlines():
        if not line_text.startswith("+"):
            continue
        clean = line_text[1:].strip()
        m = re.match(r"^import\s+(\w+)", clean)
        if m:
            added_imports.append((m.group(1), clean))
            continue
        m = re.match(r"^from\s+\S+\s+import\s+(.+)", clean)
        if m:
            names = [n.strip().split(" as ")[-1].strip() for n in m.group(1).split(",")]
            for name in names:
                if name and name != "*":
                    added_imports.append((name, clean))

    # Check if import names appear elsewhere in added non-import lines
    added_code = "\n".join(
        line[1:] for line in diff.splitlines()
        if line.startswith("+") and not re.match(r"^\+\s*(import |from )", line)
    )

    for name, _full_line in added_imports:
        if name not in added_code:
            suggestions.append(Suggestion(
                file=filepath,
                line=0,
                message=f"Potentially unused import: '{name}'",
                severity="warning",
            ))

    return suggestions


def _check_missing_error_handling(filepath: str, diff: str) -> list[Suggestion]:
    """Check if new functions lack input validation."""
    if not filepath.endswith(".py"):
        return []

    suggestions = []
    added_lines = [line[1:] for line in diff.splitlines() if line.startswith("+")]
    added_block = "\n".join(added_lines)

    func_pattern = re.compile(r"def\s+(\w+)\s*\(([^)]*)\)")
    for match in func_pattern.finditer(added_block):
        func_name = match.group(1)
        params = match.group(2)
        if func_name.startswith("_") or func_name.startswith("test"):
            continue
        if not params:
            continue
        param_names = [p.strip().split(":")[0].strip() for p in params.split(",") if p.strip()]
        for pname in param_names:
            if pname in ("self", "cls", "*args", "**kwargs"):
                continue
            func_body = added_block[match.end():match.end() + 500]
            if f"if {pname}" not in func_body and f"if not {pname}" not in func_body:
                suggestions.append(Suggestion(
                    file=filepath,
                    line=0,
                    message=f"Missing error handling for '{pname}' input in {func_name}()",
                    severity="improvement",
                ))
                break  # One suggestion per function

    return suggestions


# ---------------------------------------------------------------------------
# ANSI formatting
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_MAGENTA = "\033[35m"
_RESET = "\033[0m"

_SEVERITY_STYLE = {
    "bug": (_RED, "BUG"),
    "warning": (_YELLOW, "WARN"),
    "improvement": (_CYAN, "IMPROVE"),
}


# ---------------------------------------------------------------------------
# PairSession — the core engine
# ---------------------------------------------------------------------------


class PairSession:
    """File watcher that detects edits and proactively suggests improvements."""

    def __init__(
        self,
        repo_path: str,
        watch_path: str = "",
        patterns: list[str] | None = None,
    ):
        self.repo_path = os.path.abspath(repo_path)
        self.watch_path = watch_path
        self.patterns = patterns or list(_DEFAULT_PATTERNS)
        self.active = False
        self.suggestions: list[Suggestion] = []

        self._file_hashes: dict[str, str] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._debounce_delay: float = 0.5  # 500ms debounce
        self._last_change_time: float = 0.0
        self._quiet = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start file watcher loop in background thread."""
        if self.active:
            logger.warning("Pair session already active")
            return

        self.active = True
        self._stop_event.clear()
        self._snapshot()

        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(1.0,),
            daemon=True,
            name="pair-mode",
        )
        self._thread.start()
        logger.info("Pair session started: watching %d files", len(self._file_hashes))

    def stop(self) -> None:
        """Stop the file watcher loop."""
        self.active = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        logger.info("Pair session stopped")

    # ------------------------------------------------------------------
    # File watching
    # ------------------------------------------------------------------

    def _get_watch_root(self) -> str:
        """Get the directory to watch."""
        if self.watch_path:
            from pathlib import Path
            resolved = str(Path(os.path.join(self.repo_path, self.watch_path)).resolve())
            repo_resolved = str(Path(self.repo_path).resolve())
            if not resolved.startswith(repo_resolved):
                logger.warning("watch_path escapes repo: %s", self.watch_path)
                return self.repo_path
            return resolved
        return self.repo_path

    def _match_pattern(self, filename: str) -> bool:
        """Check if filename matches any watch pattern."""
        for pattern in self.patterns:
            if pattern.startswith("*."):
                if filename.endswith(pattern[1:]):
                    return True
            elif filename == pattern:
                return True
        return False

    def _get_watched_files(self) -> list[str]:
        """Get all files matching watch patterns."""
        root = self._get_watch_root()
        if not os.path.isdir(root):
            return []

        files = []
        for dirpath, dirs, filenames in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in filenames:
                if self._match_pattern(f):
                    files.append(os.path.join(dirpath, f))
        return files

    def _hash_file(self, filepath: str) -> str:
        """Get MD5 hash of file content."""
        try:
            with open(filepath, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except (OSError, PermissionError) as exc:
            logger.debug("Cannot hash file %s: %s", filepath, exc)
            return ""

    def _snapshot(self) -> None:
        """Take initial snapshot of all watched files."""
        self._file_hashes.clear()
        for fpath in self._get_watched_files():
            h = self._hash_file(fpath)
            if h:
                self._file_hashes[fpath] = h
        logger.info("Snapshot: %d files", len(self._file_hashes))

    def _detect_changes(self) -> list[tuple[str, str]]:
        """Detect file changes since last snapshot.

        Returns:
            List of (filepath, change_type) where change_type is
            "modified", "created", or "deleted".
        """
        changes: list[tuple[str, str]] = []
        current_files = set()

        for fpath in self._get_watched_files():
            current_files.add(fpath)
            new_hash = self._hash_file(fpath)
            if not new_hash:
                continue

            old_hash = self._file_hashes.get(fpath)
            if old_hash is None:
                changes.append((fpath, "created"))
                self._file_hashes[fpath] = new_hash
            elif old_hash != new_hash:
                changes.append((fpath, "modified"))
                self._file_hashes[fpath] = new_hash

        # Check for deleted files
        for fpath in list(self._file_hashes.keys()):
            if fpath not in current_files:
                changes.append((fpath, "deleted"))
                del self._file_hashes[fpath]

        return changes

    # ------------------------------------------------------------------
    # Diff and analysis
    # ------------------------------------------------------------------

    def _get_file_diff(self, filepath: str) -> str:
        """Get git diff for a modified file, or full content for new files."""
        rel_path = os.path.relpath(filepath, self.repo_path)
        try:
            result = subprocess.run(
                ["git", "diff", "--", rel_path],
                capture_output=True, text=True, timeout=10,
                cwd=self.repo_path,
            )
            if result.stdout.strip():
                return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        # Fall back to reading full file content (new file or not in git)
        try:
            with open(filepath, "r", errors="replace") as f:
                content = f.read()
            lines = [f"+{line}" for line in content.splitlines()]
            return "\n".join(lines)
        except (OSError, PermissionError):
            return ""

    def _analyze_change(self, filepath: str, diff: str) -> list[Suggestion]:
        """Analyze a file change and return suggestions.

        Pattern-based analysis for:
        - Missing error handling on new functions
        - Unused imports added
        - Debug statements left in
        - Missing type hints on new functions
        - Potential bugs: bare except, == None, mutable defaults
        """
        if not diff:
            return []

        suggestions: list[Suggestion] = []
        rel_path = os.path.relpath(filepath, self.repo_path)
        patterns = _get_patterns_for_file(filepath)

        # Extract added lines with line numbers
        added_lines: list[tuple[int, str]] = []
        current_line = 0
        for raw_line in diff.splitlines():
            hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", raw_line)
            if hunk_match:
                current_line = int(hunk_match.group(1)) - 1
                continue
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                current_line += 1
                added_lines.append((current_line, raw_line[1:]))
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                pass  # removed lines don't advance line counter
            else:
                current_line += 1

        # Run pattern matching on added lines
        for line_num, line_text in added_lines:
            for pattern, severity, message in patterns:
                if re.search(pattern, line_text):
                    if "Missing return type hint" in message:
                        if "->" in line_text:
                            continue
                        if not re.match(r"\s*def\s+", line_text):
                            continue
                    suggestions.append(Suggestion(
                        file=rel_path,
                        line=line_num,
                        message=message,
                        severity=severity,
                    ))

        # Run structural checks
        suggestions.extend(_check_unused_imports(rel_path, diff))
        suggestions.extend(_check_missing_error_handling(rel_path, diff))

        return suggestions

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_suggestion(self, suggestion: Suggestion) -> str:
        """Format a suggestion as a non-blocking terminal notification."""
        color, label = _SEVERITY_STYLE.get(suggestion.severity, (_DIM, "INFO"))
        location = f"{suggestion.file}"
        if suggestion.line > 0:
            location += f":{suggestion.line}"

        line = f"  {_MAGENTA}pair:{_RESET} {_BOLD}{location}{_RESET} {color}[{label}]{_RESET} {suggestion.message}"
        if suggestion.code_fix:
            line += f"\n         {_DIM}fix: {suggestion.code_fix}{_RESET}"
        return line

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    def _poll_loop(self, interval: float = 1.0) -> None:
        """Main loop: snapshot -> detect changes -> analyze -> render.

        Uses threading.Event for shutdown.
        """
        logger.info("Poll loop started (interval=%.1fs)", interval)
        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=interval)
                if self._stop_event.is_set():
                    break

                changes = self._detect_changes()
                if not changes:
                    continue

                # Debounce: wait for rapid edits to settle (500ms)
                self._last_change_time = time.time()
                deadline = self._last_change_time + self._debounce_delay
                while time.time() < deadline:
                    self._stop_event.wait(timeout=0.1)
                    if self._stop_event.is_set():
                        return
                    more = self._detect_changes()
                    if more:
                        changes.extend(more)
                        deadline = time.time() + self._debounce_delay

                # Analyze changes
                cycle_suggestions: list[Suggestion] = []
                for filepath, change_type in changes:
                    if change_type == "deleted":
                        continue
                    diff = self._get_file_diff(filepath)
                    file_suggestions = self._analyze_change(filepath, diff)
                    cycle_suggestions.extend(file_suggestions)

                self.suggestions.extend(cycle_suggestions)

                # Render
                if cycle_suggestions and not self._quiet:
                    file_count = len({s.file for s in cycle_suggestions})
                    print(f"\n  {_MAGENTA}pair:{_RESET} {_DIM}{len(cycle_suggestions)} suggestion(s) in {file_count} file(s){_RESET}")
                    for s in cycle_suggestions:
                        print(self._render_suggestion(s))
                    print()

        except Exception as exc:
            logger.error("Pair poll loop error: %s", exc)
        finally:
            self.active = False
            logger.info("Poll loop ended")


# ---------------------------------------------------------------------------
# PairMode — compatibility wrapper used by slash commands
# ---------------------------------------------------------------------------


class PairMode(PairSession):
    """Alias with cwd-based constructor for slash command compatibility.

    The /pair slash handler creates ``PairMode(cwd=repo, watch_patterns=...)``.
    This thin subclass translates those kwargs into PairSession's interface and
    keeps backward-compatible attributes (``watch_patterns``, ``cwd``).
    """

    def __init__(self, cwd: str = ".", watch_patterns: list[str] | None = None):
        super().__init__(repo_path=cwd, patterns=watch_patterns)
        self.cwd = cwd

    @property
    def watch_patterns(self) -> list[str]:
        return self.patterns

    @watch_patterns.setter
    def watch_patterns(self, value: list[str]) -> None:
        self.patterns = value


# ---------------------------------------------------------------------------
# Summary formatting
# ---------------------------------------------------------------------------


def format_pair_summary(suggestions: list[Suggestion]) -> str:
    """Summary of session suggestions grouped by file."""
    if not suggestions:
        return "  No suggestions during this session."

    by_file: dict[str, list[Suggestion]] = {}
    for s in suggestions:
        by_file.setdefault(s.file, []).append(s)

    lines: list[str] = []
    lines.append(f"  {_BOLD}Pair Session Summary{_RESET}")
    lines.append(f"  {len(suggestions)} suggestion(s) across {len(by_file)} file(s)")
    lines.append("")

    bug_count = sum(1 for s in suggestions if s.severity == "bug")
    warn_count = sum(1 for s in suggestions if s.severity == "warning")
    imp_count = sum(1 for s in suggestions if s.severity == "improvement")

    if bug_count:
        lines.append(f"  {_RED}Bugs: {bug_count}{_RESET}")
    if warn_count:
        lines.append(f"  {_YELLOW}Warnings: {warn_count}{_RESET}")
    if imp_count:
        lines.append(f"  {_CYAN}Improvements: {imp_count}{_RESET}")
    lines.append("")

    for filepath, file_suggestions in sorted(by_file.items()):
        lines.append(f"  {_BOLD}{filepath}{_RESET}")
        for s in file_suggestions:
            color, label = _SEVERITY_STYLE.get(s.severity, (_DIM, "INFO"))
            loc = f":{s.line}" if s.line > 0 else ""
            lines.append(f"    {color}[{label}]{_RESET} {loc} {s.message}")
        lines.append("")

    return "\n".join(lines)
