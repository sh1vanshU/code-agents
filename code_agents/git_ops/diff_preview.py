"""Diff Preview — rich side-by-side diff with per-hunk accept/reject.

Used before applying file edits in TUI or terminal mode.
Shows hunks with accept/reject controls, applies only accepted hunks.
"""

from __future__ import annotations

import difflib
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.diff_preview")


class HunkState(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass
class DiffHunk:
    """A single diff hunk with accept/reject state."""
    index: int
    header: str  # @@ line
    original_lines: list[str]
    modified_lines: list[str]
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)
    state: HunkState = HunkState.PENDING
    start_line: int = 0  # 1-based line number in original

    @property
    def additions(self) -> int:
        return sum(1 for l in self.modified_lines if l.startswith("+"))

    @property
    def deletions(self) -> int:
        return sum(1 for l in self.original_lines if l.startswith("-"))


@dataclass
class DiffPreview:
    """Manages a file diff with per-hunk accept/reject."""
    file_path: str
    original: str
    modified: str
    hunks: list[DiffHunk] = field(default_factory=list)

    def __post_init__(self):
        if not self.hunks:
            self.hunks = parse_hunks(self.original, self.modified)

    @property
    def total_hunks(self) -> int:
        return len(self.hunks)

    @property
    def accepted_count(self) -> int:
        return sum(1 for h in self.hunks if h.state == HunkState.ACCEPTED)

    @property
    def rejected_count(self) -> int:
        return sum(1 for h in self.hunks if h.state == HunkState.REJECTED)

    @property
    def pending_count(self) -> int:
        return sum(1 for h in self.hunks if h.state == HunkState.PENDING)

    def accept_hunk(self, index: int) -> None:
        if 0 <= index < len(self.hunks):
            self.hunks[index].state = HunkState.ACCEPTED

    def reject_hunk(self, index: int) -> None:
        if 0 <= index < len(self.hunks):
            self.hunks[index].state = HunkState.REJECTED

    def accept_all(self) -> None:
        for h in self.hunks:
            h.state = HunkState.ACCEPTED

    def reject_all(self) -> None:
        for h in self.hunks:
            h.state = HunkState.REJECTED

    def apply_accepted(self) -> str:
        """Reconstruct file content applying only accepted hunks."""
        if not self.hunks:
            return self.original

        # If all accepted, return modified
        if all(h.state == HunkState.ACCEPTED for h in self.hunks):
            return self.modified

        # If all rejected, return original
        if all(h.state == HunkState.REJECTED for h in self.hunks):
            return self.original

        # Partial accept: apply accepted hunks using patch logic
        return _apply_partial_hunks(self.original, self.modified, self.hunks)

    def get_unified_diff(self) -> str:
        """Generate unified diff string."""
        orig_lines = self.original.splitlines(keepends=True)
        mod_lines = self.modified.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines, mod_lines,
            fromfile=f"a/{self.file_path}",
            tofile=f"b/{self.file_path}",
            lineterm="",
        )
        return "".join(diff)


def parse_hunks(original: str, modified: str) -> list[DiffHunk]:
    """Parse a diff into individual hunks."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        orig_lines, mod_lines,
        fromfile="original", tofile="modified",
        lineterm="",
    ))

    if not diff_lines:
        return []

    hunks: list[DiffHunk] = []
    current_header = ""
    current_orig: list[str] = []
    current_mod: list[str] = []
    current_context: list[str] = []
    hunk_idx = 0
    start_line = 0

    for line in diff_lines:
        if line.startswith("@@"):
            # Save previous hunk
            if current_header:
                hunks.append(DiffHunk(
                    index=hunk_idx,
                    header=current_header,
                    original_lines=current_orig,
                    modified_lines=current_mod,
                    context_before=current_context,
                    start_line=start_line,
                ))
                hunk_idx += 1
            current_header = line
            current_orig = []
            current_mod = []
            current_context = []
            # Parse start line from @@ -N,M +N,M @@
            m = re.match(r"@@ -(\d+)", line)
            start_line = int(m.group(1)) if m else 0

        elif line.startswith("---") or line.startswith("+++"):
            continue
        elif line.startswith("-"):
            current_orig.append(line)
        elif line.startswith("+"):
            current_mod.append(line)
        elif line.startswith(" "):
            # Context line — part of current hunk
            if not current_orig and not current_mod:
                current_context.append(line)
            else:
                current_orig.append(line)
                current_mod.append(line)

    # Save last hunk
    if current_header:
        hunks.append(DiffHunk(
            index=hunk_idx,
            header=current_header,
            original_lines=current_orig,
            modified_lines=current_mod,
            context_before=current_context,
            start_line=start_line,
        ))

    return hunks


def _apply_partial_hunks(original: str, modified: str, hunks: list[DiffHunk]) -> str:
    """Apply only accepted hunks to the original content.

    Strategy: generate a new unified diff with only accepted hunks,
    then apply it. This is simpler than line-by-line patching.
    """
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    # Use difflib's SequenceMatcher to build accepted output
    matcher = difflib.SequenceMatcher(None, orig_lines, mod_lines)
    result: list[str] = []
    hunk_idx = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result.extend(orig_lines[i1:i2])
        elif tag in ("replace", "insert", "delete"):
            # Find which hunk this corresponds to
            if hunk_idx < len(hunks) and hunks[hunk_idx].state == HunkState.ACCEPTED:
                # Apply the modification
                if tag == "delete":
                    pass  # skip original lines (they're deleted)
                elif tag == "insert":
                    result.extend(mod_lines[j1:j2])
                else:  # replace
                    result.extend(mod_lines[j1:j2])
            else:
                # Keep original
                if tag == "insert":
                    pass  # don't add new lines
                else:
                    result.extend(orig_lines[i1:i2])
            hunk_idx += 1

    return "".join(result)


def format_diff_rich(preview: DiffPreview) -> str:
    """Format diff for Rich terminal display."""
    lines: list[str] = []
    lines.append(f"[bold cyan]File:[/bold cyan] {preview.file_path}")
    lines.append(f"[dim]Hunks: {preview.total_hunks} | "
                 f"Accepted: {preview.accepted_count} | "
                 f"Rejected: {preview.rejected_count} | "
                 f"Pending: {preview.pending_count}[/dim]")
    lines.append("")

    for hunk in preview.hunks:
        state_icon = {
            HunkState.PENDING: "[yellow]?[/yellow]",
            HunkState.ACCEPTED: "[green]✓[/green]",
            HunkState.REJECTED: "[red]✗[/red]",
        }[hunk.state]
        lines.append(f"{state_icon} [bold]Hunk {hunk.index + 1}[/bold] {hunk.header}")

        for line in hunk.original_lines:
            if line.startswith("-"):
                lines.append(f"  [red]{_escape_markup(line)}[/red]")
            elif line.startswith(" "):
                lines.append(f"  [dim]{_escape_markup(line)}[/dim]")

        for line in hunk.modified_lines:
            if line.startswith("+"):
                lines.append(f"  [green]{_escape_markup(line)}[/green]")
            elif line.startswith(" "):
                pass  # already shown in original

        lines.append("")

    return "\n".join(lines)


def format_diff_plain(preview: DiffPreview) -> str:
    """Format diff for plain terminal display (no Rich)."""
    lines: list[str] = []
    lines.append(f"  File: {preview.file_path}")
    lines.append(f"  Hunks: {preview.total_hunks} total")
    lines.append("")

    for hunk in preview.hunks:
        state = {
            HunkState.PENDING: "?",
            HunkState.ACCEPTED: "✓",
            HunkState.REJECTED: "✗",
        }[hunk.state]
        lines.append(f"  [{state}] Hunk {hunk.index + 1}: {hunk.header}")
        for line in hunk.original_lines:
            if line.startswith("-"):
                lines.append(f"    {line}")
        for line in hunk.modified_lines:
            if line.startswith("+"):
                lines.append(f"    {line}")
        lines.append("")

    return "\n".join(lines)


def interactive_review(preview: DiffPreview) -> DiffPreview:
    """Interactive terminal review: accept/reject each hunk.

    Returns the preview with hunk states set.
    Keyboard: a=accept, r=reject, A=accept all, R=reject all, s=skip, q=quit
    """
    try:
        from rich.console import Console
        console = Console()
        use_rich = True
    except ImportError:
        console = None
        use_rich = False

    print()
    if use_rich:
        console.print(format_diff_rich(preview))
    else:
        print(format_diff_plain(preview))

    print(f"  Review {preview.total_hunks} hunk(s): "
          f"[a]ccept  [r]eject  [A]ccept all  [R]eject all  [s]kip  [q]uit")
    print()

    for hunk in preview.hunks:
        if use_rich:
            console.print(f"  [bold]Hunk {hunk.index + 1}/{preview.total_hunks}[/bold] "
                         f"(+{hunk.additions}/-{hunk.deletions}) {hunk.header}")
        else:
            print(f"  Hunk {hunk.index + 1}/{preview.total_hunks} "
                  f"(+{hunk.additions}/-{hunk.deletions}) {hunk.header}")

        try:
            choice = input("  [a/r/A/R/s/q]: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "q"

        if choice == "a":
            hunk.state = HunkState.ACCEPTED
            print("  ✓ Accepted")
        elif choice == "r":
            hunk.state = HunkState.REJECTED
            print("  ✗ Rejected")
        elif choice == "A":
            preview.accept_all()
            print("  ✓ All hunks accepted")
            break
        elif choice == "R":
            preview.reject_all()
            print("  ✗ All hunks rejected")
            break
        elif choice == "q":
            # Reject remaining
            for h in preview.hunks:
                if h.state == HunkState.PENDING:
                    h.state = HunkState.REJECTED
            break
        else:
            # Skip = leave as pending (will be rejected on apply)
            hunk.state = HunkState.REJECTED

    return preview


def is_enabled(state: dict | None = None) -> bool:
    """Check if diff preview mode is enabled."""
    if state and "diff_preview" in state:
        return state["diff_preview"]
    return os.getenv("CODE_AGENTS_DIFF_PREVIEW", "false").lower() == "true"


def _escape_markup(text: str) -> str:
    """Escape Rich markup characters."""
    return text.replace("[", "\\[").replace("]", "\\]")
