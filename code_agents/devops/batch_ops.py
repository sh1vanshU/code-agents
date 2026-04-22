"""Batch operations — process multiple files in parallel with a single instruction."""

from __future__ import annotations

import ast
import difflib
import glob as _glob
import logging
import os
import re
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.devops.batch_ops")

# Source file extensions to consider when no explicit files or pattern given
_SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".scala",
    ".sh", ".bash", ".zsh", ".yaml", ".yml", ".json", ".toml",
}

# Directories to always skip
_SKIP_DIRS = {
    "__pycache__", ".git", ".hg", ".svn", "node_modules", ".tox",
    ".venv", "venv", ".eggs", "dist", "build", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "htmlcov", ".coverage",
}


@dataclass
class BatchFileResult:
    """Result of processing a single file."""

    file: str
    success: bool
    changes_made: bool
    diff: str = ""
    error: str = ""


@dataclass
class BatchResult:
    """Aggregated result of a batch operation."""

    instruction: str
    total_files: int
    changed: int
    skipped: int
    failed: int
    results: list[BatchFileResult] = field(default_factory=list)
    duration_seconds: float = 0.0


class BatchOperator:
    """Process multiple files in parallel with a single instruction."""

    def __init__(self, cwd: str) -> None:
        self._cwd = Path(cwd).resolve()
        if not self._cwd.is_dir():
            raise ValueError(f"Working directory does not exist: {self._cwd}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        instruction: str,
        files: Optional[list[str]] = None,
        pattern: str = "",
        max_parallel: int = 4,
        dry_run: bool = False,
    ) -> BatchResult:
        """Run *instruction* across the selected files.

        1. Select target files (explicit list, glob *pattern*, or all source files).
        2. Process each file: read -> apply instruction -> generate diff.
        3. Apply changes in parallel via :class:`~concurrent.futures.ThreadPoolExecutor`.
        4. Return a :class:`BatchResult` summary.
        """
        t0 = time.monotonic()
        logger.info("batch run: instruction=%r files=%s pattern=%r dry_run=%s",
                     instruction, files, pattern, dry_run)

        targets = self._select_files(files, pattern)
        logger.info("selected %d target files", len(targets))

        results: list[BatchFileResult] = []
        max_workers = max(1, min(max_parallel, 16))

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self._process_file, f, instruction, dry_run): f
                for f in targets
            }
            for fut in as_completed(futures):
                results.append(fut.result())

        changed = sum(1 for r in results if r.changes_made)
        skipped = sum(1 for r in results if r.success and not r.changes_made)
        failed = sum(1 for r in results if not r.success)

        return BatchResult(
            instruction=instruction,
            total_files=len(targets),
            changed=changed,
            skipped=skipped,
            failed=failed,
            results=results,
            duration_seconds=round(time.monotonic() - t0, 2),
        )

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------

    def _select_files(self, files: Optional[list[str]], pattern: str) -> list[str]:
        """Resolve target files, validating all paths stay within *cwd*."""

        if files:
            resolved: list[str] = []
            for f in files:
                p = Path(f) if Path(f).is_absolute() else (self._cwd / f)
                p = p.resolve()
                self._validate_path(p)
                if p.is_file():
                    resolved.append(str(p))
                else:
                    logger.warning("skipping non-file: %s", p)
            return resolved

        if pattern:
            matches = _glob.glob(str(self._cwd / pattern), recursive=True)
            out: list[str] = []
            for m in sorted(matches):
                mp = Path(m).resolve()
                if mp.is_file():
                    try:
                        self._validate_path(mp)
                        out.append(str(mp))
                    except ValueError:
                        logger.warning("glob match outside cwd, skipping: %s", mp)
            return out

        # Default: all source files under cwd
        return self._all_source_files()

    def _all_source_files(self) -> list[str]:
        found: list[str] = []
        for root, dirs, filenames in os.walk(self._cwd):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fn in filenames:
                if Path(fn).suffix in _SOURCE_EXTENSIONS:
                    found.append(os.path.join(root, fn))
        return sorted(found)

    def _validate_path(self, p: Path) -> None:
        """Ensure *p* is within *self._cwd*."""
        try:
            p.resolve().relative_to(self._cwd)
        except ValueError:
            raise ValueError(
                f"Path escapes working directory: {p} is not inside {self._cwd}"
            )

    # ------------------------------------------------------------------
    # Single-file processing
    # ------------------------------------------------------------------

    def _process_file(self, filepath: str, instruction: str, dry_run: bool) -> BatchFileResult:
        """Apply *instruction* to a single file.  Returns a :class:`BatchFileResult`."""
        try:
            content = Path(filepath).read_text(encoding="utf-8")
        except Exception as exc:
            return BatchFileResult(file=filepath, success=False, changes_made=False,
                                   error=f"read error: {exc}")

        try:
            new_content = self._apply_instruction(content, instruction, filepath)
        except Exception as exc:
            return BatchFileResult(file=filepath, success=False, changes_made=False,
                                   error=f"transform error: {exc}")

        if new_content == content:
            return BatchFileResult(file=filepath, success=True, changes_made=False)

        # Compute unified diff
        rel = str(Path(filepath).relative_to(self._cwd))
        diff = "".join(
            difflib.unified_diff(
                content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )

        if dry_run:
            return BatchFileResult(file=filepath, success=True, changes_made=True,
                                   diff=diff)

        # Atomic write: write to temp, then replace
        try:
            self._atomic_write(filepath, content, new_content)
        except Exception as exc:
            return BatchFileResult(file=filepath, success=False, changes_made=False,
                                   error=f"write error: {exc}")

        return BatchFileResult(file=filepath, success=True, changes_made=True,
                               diff=diff)

    def _atomic_write(self, filepath: str, original: str, new_content: str) -> None:
        """Write *new_content* atomically: backup original, write via tempfile + rename."""
        target = Path(filepath)
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(str(target), str(backup))

        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            os.write(fd, new_content.encode("utf-8"))
            os.close(fd)
            shutil.move(tmp, str(target))
        except Exception:
            os.close(fd) if not os.get_inheritable(fd) else None  # pragma: no cover
            if os.path.exists(tmp):
                os.unlink(tmp)
            # Restore backup
            if backup.exists():
                shutil.move(str(backup), str(target))
            raise
        finally:
            if backup.exists():
                backup.unlink()

    # ------------------------------------------------------------------
    # Instruction dispatch
    # ------------------------------------------------------------------

    def _apply_instruction(self, content: str, instruction: str, filepath: str) -> str:
        """Pattern-match *instruction* and delegate to specialised transforms."""
        lower = instruction.lower().strip()

        if re.search(r"(add|wrap).*(error.?handl|try.?except|try.?catch)", lower):
            return self._add_error_handling(content)

        if re.search(r"add.*(type.?hint|annotation|typing)", lower):
            return self._add_type_hints(content)

        if re.search(r"add.*log", lower):
            module_name = Path(filepath).stem
            return self._add_logging(content, module_name)

        if re.search(r"(remove|replace|delete).*print", lower):
            module_name = Path(filepath).stem
            return self._remove_prints(content, module_name)

        if re.search(r"add.*docstring", lower):
            return self._add_docstrings(content)

        # Generic: no recognised pattern — return unchanged
        logger.debug("no pattern matched for instruction %r on %s", instruction, filepath)
        return content

    # ------------------------------------------------------------------
    # Transform: add error handling
    # ------------------------------------------------------------------

    def _add_error_handling(self, content: str) -> str:
        """Wrap top-level function bodies in try/except where not already wrapped."""
        if not content.strip():
            return content

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return content

        lines = content.splitlines(keepends=True)
        insertions: list[tuple[int, str, str]] = []  # (line_no, indent, func_name)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.body:
                continue
            # Skip if first statement is already a try
            first = node.body[0]
            if isinstance(first, ast.Try):
                continue
            # Determine indent of function body
            body_line = first.lineno  # 1-based
            if body_line <= len(lines):
                raw = lines[body_line - 1]
                indent = raw[: len(raw) - len(raw.lstrip())]
            else:
                indent = "        "
            insertions.append((body_line, indent, node.name))

        if not insertions:
            return content

        # Apply insertions bottom-up to avoid line-number shifts
        insertions.sort(key=lambda t: t[0], reverse=True)
        for body_start, indent, func_name in insertions:
            # Find extent of function body (next node at same or lesser indent)
            end = body_start
            for i in range(body_start, len(lines)):
                ln = lines[i]
                if ln.strip() == "":
                    continue
                cur_indent = len(ln) - len(ln.lstrip())
                if cur_indent < len(indent) and ln.strip():
                    break
                end = i + 1

            body_lines = lines[body_start - 1 : end]
            extra_indent = "    "
            wrapped = [f"{indent}try:\n"]
            for bl in body_lines:
                if bl.strip():
                    wrapped.append(f"{extra_indent}{bl}")
                else:
                    wrapped.append(bl)
            wrapped.append(f"{indent}except Exception as exc:\n")
            wrapped.append(f"{indent}    raise\n")

            lines[body_start - 1 : end] = wrapped

        return "".join(lines)

    # ------------------------------------------------------------------
    # Transform: add type hints
    # ------------------------------------------------------------------

    def _add_type_hints(self, content: str) -> str:
        """Add ``-> None`` return type to functions that lack return annotation."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return content

        lines = content.splitlines(keepends=True)
        offsets: list[int] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.returns is None:
                    offsets.append(node.lineno)

        if not offsets:
            return content

        for lineno in sorted(offsets, reverse=True):
            idx = lineno - 1
            if idx < len(lines):
                line = lines[idx]
                # Add -> None before the trailing colon
                line = re.sub(r"\)\s*:", ") -> None:", line, count=1)
                lines[idx] = line

        return "".join(lines)

    # ------------------------------------------------------------------
    # Transform: add logging
    # ------------------------------------------------------------------

    def _add_logging(self, content: str, module_name: str) -> str:
        """Add a module-level logger and ``logger.debug`` calls at function entry."""
        if "import logging" in content:
            return content  # already has logging

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return content

        lines = content.splitlines(keepends=True)

        # Find insertion point: after last top-level import
        insert_after = 0
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                insert_after = node.end_lineno or node.lineno

        logger_lines = [
            "import logging\n",
            f'logger = logging.getLogger("{module_name}")\n',
            "\n",
        ]
        lines[insert_after:insert_after] = logger_lines
        offset = len(logger_lines)

        # Re-parse to get updated line numbers
        new_src = "".join(lines)
        try:
            tree2 = ast.parse(new_src)
        except SyntaxError:
            return new_src

        lines2 = new_src.splitlines(keepends=True)
        inserts: list[tuple[int, str, str]] = []
        for node in ast.walk(tree2):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.body:
                    continue
                first = node.body[0]
                body_line = first.lineno
                raw = lines2[body_line - 1]
                indent = raw[: len(raw) - len(raw.lstrip())]
                inserts.append((body_line, indent, node.name))

        for body_line, indent, fname in sorted(inserts, key=lambda t: t[0], reverse=True):
            log_stmt = f'{indent}logger.debug("entering {fname}")\n'
            lines2.insert(body_line - 1, log_stmt)

        return "".join(lines2)

    # ------------------------------------------------------------------
    # Transform: remove print statements
    # ------------------------------------------------------------------

    def _remove_prints(self, content: str, module_name: str) -> str:
        """Replace bare ``print(...)`` calls with ``logger.info(...)``."""
        if "print(" not in content:
            return content

        lines = content.splitlines(keepends=True)
        changed = False
        new_lines: list[str] = []

        for line in lines:
            m = re.match(r"^(\s*)print\((.+)\)\s*$", line)
            if m:
                indent, args = m.group(1), m.group(2)
                new_lines.append(f"{indent}logger.info({args})\n")
                changed = True
            else:
                new_lines.append(line)

        if not changed:
            return content

        result = "".join(new_lines)
        # Ensure logging import exists
        if "import logging" not in result:
            result = (
                "import logging\n"
                f'logger = logging.getLogger("{module_name}")\n\n'
                + result
            )
        return result

    # ------------------------------------------------------------------
    # Transform: add docstrings
    # ------------------------------------------------------------------

    def _add_docstrings(self, content: str) -> str:
        """Add placeholder docstrings to functions/classes that lack one."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return content

        lines = content.splitlines(keepends=True)
        insertions: list[tuple[int, str, str]] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if not node.body:
                continue
            first = node.body[0]
            # Already has a docstring
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                continue
            body_line = first.lineno
            raw = lines[body_line - 1]
            indent = raw[: len(raw) - len(raw.lstrip())]
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            insertions.append((body_line, indent, f"{node.name} {kind}"))

        if not insertions:
            return content

        for body_line, indent, desc in sorted(insertions, key=lambda t: t[0], reverse=True):
            doc_line = f'{indent}"""TODO: document {desc}."""\n'
            lines.insert(body_line - 1, doc_line)

        return "".join(lines)


# ------------------------------------------------------------------
# Formatting
# ------------------------------------------------------------------


def format_batch_result(result: BatchResult) -> str:
    """Format a :class:`BatchResult` as a Rich-compatible box summary."""
    width = 56
    hr = "─" * (width - 2)
    lines: list[str] = []
    lines.append(f"╭─ Batch Operation {hr[18:]}╮")
    lines.append(f"│ Instruction: {_trunc(result.instruction, width - 17):<{width - 4}} │")
    stats = (
        f"Files: {result.total_files} total, "
        f"{result.changed} changed, "
        f"{result.skipped} skipped, "
        f"{result.failed} failed"
    )
    lines.append(f"│ {stats:<{width - 4}} │")
    lines.append(f"│ Duration: {result.duration_seconds}s{' ' * (width - 15 - len(str(result.duration_seconds)))} │")
    lines.append(f"├{hr}┤")

    for r in result.results:
        rel = _short_path(r.file)
        if r.success and r.changes_made:
            marker = "✓"
            note = "changed"
        elif r.success:
            marker = "–"
            note = "no changes"
        else:
            marker = "✗"
            note = r.error[:30] if r.error else "failed"
        entry = f"{marker} {rel} — {note}"
        lines.append(f"│ {entry:<{width - 4}} │")

    lines.append(f"╰{hr}╯")
    return "\n".join(lines)


def _trunc(s: str, maxlen: int) -> str:
    return s if len(s) <= maxlen else s[: maxlen - 1] + "…"


def _short_path(filepath: str, maxlen: int = 35) -> str:
    parts = Path(filepath).parts
    if len(parts) <= 3:
        return str(Path(filepath).name)
    return str(Path(*parts[-3:]))
