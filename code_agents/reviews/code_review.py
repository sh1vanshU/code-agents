"""AI Code Review with Inline Terminal Diff.

Pattern-based code analysis that annotates unified diffs with inline findings.
Detects security, performance, correctness, and style issues in changed code.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.reviews.code_review")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

CATEGORY_EMOJIS = {
    "security": "\U0001f512",      # lock
    "performance": "\u26a1",       # lightning
    "correctness": "\u26a0\ufe0f", # warning
    "style": "\U0001f3a8",         # palette
}

SEVERITY_COLORS = {
    "critical": "\033[91m",  # bright red
    "warning": "\033[93m",   # bright yellow
    "suggestion": "\033[96m",  # bright cyan
}

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_YELLOW = "\033[43m"


@dataclass
class InlineFinding:
    """A single code review finding attached to a diff line."""

    file: str
    line: int
    category: str  # "security", "performance", "correctness", "style"
    severity: str  # "critical", "warning", "suggestion"
    message: str
    emoji: str  # computed from category
    suggestion: str = ""
    accepted: bool | None = None

    @staticmethod
    def make_emoji(category: str) -> str:
        return CATEGORY_EMOJIS.get(category, "\u2753")


@dataclass
class AnnotatedDiffLine:
    """A single line in a diff, optionally annotated with a finding."""

    content: str
    line_type: str  # "+", "-", " ", "@@", "file"
    finding: InlineFinding | None = None


@dataclass
class CodeReviewResult:
    """Full result of an inline code review."""

    base: str
    head: str
    files: list[str]
    diff_lines: list[AnnotatedDiffLine]
    findings: list[InlineFinding]
    summary: dict  # counts by category/severity


# ---------------------------------------------------------------------------
# Security patterns
# ---------------------------------------------------------------------------

_SECURITY_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"\beval\s*\("), "Use of eval() is a code injection risk", "critical"),
    (re.compile(r"\bexec\s*\("), "Use of exec() is a code injection risk", "critical"),
    (re.compile(r"shell\s*=\s*True"), "subprocess with shell=True enables shell injection", "critical"),
    (re.compile(r"os\.system\s*\("), "os.system() is vulnerable to shell injection; use subprocess", "critical"),
    (re.compile(r"os\.popen\s*\("), "os.popen() is vulnerable to shell injection; use subprocess", "critical"),
    (
        re.compile(r"""(?:password|secret|api_key|token|auth)\s*=\s*['"][^'"]{4,}['"]""", re.IGNORECASE),
        "Possible hardcoded secret/credential",
        "critical",
    ),
    (
        re.compile(r"""f['\"].*(?:SELECT|INSERT|UPDATE|DELETE)\s.*\{""", re.IGNORECASE),
        "SQL query built with f-string — use parameterized queries",
        "critical",
    ),
    (
        re.compile(r"""['\"].*(?:SELECT|INSERT|UPDATE|DELETE)\s.*['\"].*%\s""", re.IGNORECASE),
        "SQL query built with string formatting — use parameterized queries",
        "critical",
    ),
    (
        re.compile(r"""\.format\(.*(?:SELECT|INSERT|UPDATE|DELETE)""", re.IGNORECASE),
        "SQL query built with .format() — use parameterized queries",
        "warning",
    ),
    (
        re.compile(r"""\+\s*['\"].*(?:SELECT|INSERT|UPDATE|DELETE)""", re.IGNORECASE),
        "SQL query built with string concatenation — use parameterized queries",
        "warning",
    ),
    (re.compile(r"pickle\.loads?\s*\("), "pickle.load is unsafe with untrusted data", "warning"),
    (re.compile(r"yaml\.load\s*\([^)]*\)(?!.*Loader)"), "yaml.load without Loader param is unsafe; use safe_load", "warning"),
    (re.compile(r"marshal\.loads?\s*\("), "marshal.load is unsafe with untrusted data", "warning"),
    (re.compile(r"verify\s*=\s*False"), "SSL verification disabled", "warning"),
    (re.compile(r"CORS\s*\(\s*\*"), "Wildcard CORS allows any origin", "warning"),
    (re.compile(r"DEBUG\s*=\s*True"), "DEBUG mode enabled — ensure this is dev only", "suggestion"),
]

# ---------------------------------------------------------------------------
# Performance patterns
# ---------------------------------------------------------------------------

_PERFORMANCE_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"for\s+\w+\s+in\s+.*:\s*\n\s+.*\.(?:query|execute|fetch|find|get)\s*\("),
        "Possible N+1 query pattern — DB call inside loop",
        "warning",
    ),
    (
        re.compile(r"time\.sleep\s*\("),
        "Blocking sleep — consider async alternative in async context",
        "suggestion",
    ),
    (
        re.compile(r"\.readlines\s*\(\s*\)"),
        "readlines() loads entire file into memory — consider iterating",
        "suggestion",
    ),
    (
        re.compile(r"json\.loads?\s*\(.*\.read\s*\(\s*\)\s*\)"),
        "Reading entire file into memory for JSON — consider streaming",
        "suggestion",
    ),
    (
        re.compile(r"requests\.get\s*\("),
        "Synchronous HTTP in potentially async context — consider httpx/aiohttp",
        "suggestion",
    ),
    (
        re.compile(r"open\s*\([^)]+\)\.read\s*\(\s*\)"),
        "Reading entire file at once without context manager",
        "suggestion",
    ),
    (
        re.compile(r"\bsorted\s*\(.*sorted\s*\("),
        "Nested sorted() calls — consider single sort with key",
        "suggestion",
    ),
    (
        re.compile(r"(?:list|dict)\s*\(\s*(?:list|dict)\s*\("),
        "Redundant collection conversion",
        "suggestion",
    ),
]

# ---------------------------------------------------------------------------
# Correctness patterns
# ---------------------------------------------------------------------------

_CORRECTNESS_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"except\s*:"), "Bare except catches SystemExit/KeyboardInterrupt — use except Exception", "warning"),
    (re.compile(r"except\s+Exception\s*:\s*\n\s+pass"), "Silently swallowing exceptions — at minimum log them", "warning"),
    (
        re.compile(r"except\s+\w+.*:\s*\n\s+pass"),
        "Exception caught and ignored — consider logging or re-raising",
        "suggestion",
    ),
    (
        re.compile(r"==\s*None"),
        "Use 'is None' instead of '== None' for identity check",
        "suggestion",
    ),
    (
        re.compile(r"!=\s*None"),
        "Use 'is not None' instead of '!= None' for identity check",
        "suggestion",
    ),
    (
        re.compile(r"type\s*\(\s*\w+\s*\)\s*=="),
        "Use isinstance() instead of type() comparison",
        "suggestion",
    ),
    (
        re.compile(r"def\s+\w+\s*\([^)]*\bdict\b\s*=\s*\{"),
        "Mutable default argument (dict) — use None and assign inside",
        "warning",
    ),
    (
        re.compile(r"def\s+\w+\s*\([^)]*\blist\b\s*=\s*\["),
        "Mutable default argument (list) — use None and assign inside",
        "warning",
    ),
    (
        re.compile(r"assert\s+\w"),
        "Assert statements are stripped with -O flag — don't use for validation",
        "suggestion",
    ),
    (
        re.compile(r"global\s+\w+"),
        "Global variable mutation — consider passing as parameter",
        "suggestion",
    ),
    (
        re.compile(r"import\s+\*"),
        "Wildcard import pollutes namespace — import specific names",
        "warning",
    ),
]

# ---------------------------------------------------------------------------
# Style patterns (line-level)
# ---------------------------------------------------------------------------

_STYLE_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"#\s*TODO", re.IGNORECASE),
        "TODO comment left in code",
        "suggestion",
    ),
    (
        re.compile(r"#\s*FIXME", re.IGNORECASE),
        "FIXME comment — known issue not addressed",
        "suggestion",
    ),
    (
        re.compile(r"#\s*HACK", re.IGNORECASE),
        "HACK comment — code needs cleanup",
        "suggestion",
    ),
    (
        re.compile(r"print\s*\("),
        "Print statement — use logging in production code",
        "suggestion",
    ),
]

# Magic numbers: standalone integers > 1 and not 0, 1, 2, 100, 200, etc.
_MAGIC_NUMBER_PATTERN = re.compile(r"(?<!=)\s(?<!\w)(\d{2,})(?!\w)(?!\s*[=:)])(?!.*#)")


# ---------------------------------------------------------------------------
# InlineCodeReview — main engine
# ---------------------------------------------------------------------------


class InlineCodeReview:
    """Run an inline code review on git diff output."""

    def __init__(
        self,
        cwd: str,
        base: str = "main",
        files: list[str] | None = None,
        category_filter: str = "all",
    ):
        self.cwd = cwd
        self.base = base
        self.files = files
        self.category_filter = category_filter
        logger.debug("InlineCodeReview init cwd=%s base=%s filter=%s", cwd, base, category_filter)

    def run(self) -> CodeReviewResult:
        """Execute full review pipeline: diff -> parse -> analyze -> annotate."""
        raw_diff = self._get_diff()
        if not raw_diff.strip():
            logger.info("No diff found between %s and HEAD", self.base)
            return CodeReviewResult(
                base=self.base,
                head="HEAD",
                files=[],
                diff_lines=[],
                findings=[],
                summary={"total": 0},
            )

        hunks = self._parse_diff(raw_diff)
        findings = self._analyze_hunks(hunks)

        # Apply category filter
        if self.category_filter != "all":
            cats = {c.strip().lower() for c in self.category_filter.split(",")}
            findings = [f for f in findings if f.category in cats]

        # Build annotated diff lines
        diff_lines = self._build_diff_lines(raw_diff)
        annotated = self._annotate_diff(diff_lines, findings)

        # Gather file list
        files = sorted({h["file"] for h in hunks})

        summary = self._build_summary(findings)

        return CodeReviewResult(
            base=self.base,
            head="HEAD",
            files=files,
            diff_lines=annotated,
            findings=findings,
            summary=summary,
        )

    def _get_diff(self) -> str:
        """Run git diff base...HEAD and return raw unified diff."""
        cmd = ["git", "diff", f"{self.base}...HEAD"]
        if self.files:
            cmd.append("--")
            cmd.extend(self.files)

        logger.debug("Running: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.cwd,
            )
            if result.returncode != 0:
                logger.warning("git diff returned %d: %s", result.returncode, result.stderr.strip())
                # Fallback: try git diff base HEAD (no triple-dot)
                cmd_fallback = ["git", "diff", self.base, "HEAD"]
                if self.files:
                    cmd_fallback.append("--")
                    cmd_fallback.extend(self.files)
                result = subprocess.run(
                    cmd_fallback,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=self.cwd,
                )
            return result.stdout
        except subprocess.TimeoutExpired:
            logger.error("git diff timed out")
            return ""
        except FileNotFoundError:
            logger.error("git not found in PATH")
            return ""

    def _parse_diff(self, raw: str) -> list[dict]:
        """Parse unified diff into file hunks with line metadata."""
        hunks: list[dict] = []
        current_file: str = ""
        current_hunk_lines: list[dict] = []
        new_line_no = 0

        for line in raw.splitlines():
            # New file header
            if line.startswith("diff --git"):
                if current_file and current_hunk_lines:
                    hunks.append({"file": current_file, "lines": current_hunk_lines})
                    current_hunk_lines = []
                # Extract filename from "diff --git a/path b/path"
                parts = line.split(" b/", 1)
                current_file = parts[1] if len(parts) > 1 else ""
                continue

            # Hunk header
            match = re.match(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@", line)
            if match:
                if current_hunk_lines:
                    hunks.append({"file": current_file, "lines": current_hunk_lines})
                    current_hunk_lines = []
                new_line_no = int(match.group(1))
                continue

            # Skip binary / metadata lines
            if line.startswith("---") or line.startswith("+++") or line.startswith("index "):
                continue
            if line.startswith("Binary files"):
                continue

            # Content lines
            if line.startswith("+"):
                current_hunk_lines.append({
                    "content": line[1:],
                    "type": "+",
                    "line_no": new_line_no,
                    "file": current_file,
                })
                new_line_no += 1
            elif line.startswith("-"):
                current_hunk_lines.append({
                    "content": line[1:],
                    "type": "-",
                    "line_no": None,
                    "file": current_file,
                })
            else:
                # Context line
                current_hunk_lines.append({
                    "content": line[1:] if line.startswith(" ") else line,
                    "type": " ",
                    "line_no": new_line_no,
                    "file": current_file,
                })
                new_line_no += 1

        # Flush last hunk
        if current_file and current_hunk_lines:
            hunks.append({"file": current_file, "lines": current_hunk_lines})

        return hunks

    def _analyze_hunks(self, hunks: list[dict]) -> list[InlineFinding]:
        """Analyze parsed hunks for security, performance, correctness, and style issues."""
        findings: list[InlineFinding] = []

        for hunk in hunks:
            file_path = hunk["file"]
            added_lines = [l for l in hunk["lines"] if l["type"] == "+"]

            # Track function lengths and nesting for style checks
            func_start: int | None = None
            func_name: str = ""
            func_lines: int = 0

            for line_info in added_lines:
                content = line_info["content"]
                line_no = line_info["line_no"] or 0

                # --- Security ---
                for pattern, message, severity in _SECURITY_PATTERNS:
                    if pattern.search(content):
                        findings.append(InlineFinding(
                            file=file_path,
                            line=line_no,
                            category="security",
                            severity=severity,
                            message=message,
                            emoji=InlineFinding.make_emoji("security"),
                        ))

                # --- Performance ---
                for pattern, message, severity in _PERFORMANCE_PATTERNS:
                    if pattern.search(content):
                        findings.append(InlineFinding(
                            file=file_path,
                            line=line_no,
                            category="performance",
                            severity=severity,
                            message=message,
                            emoji=InlineFinding.make_emoji("performance"),
                        ))

                # --- Correctness ---
                for pattern, message, severity in _CORRECTNESS_PATTERNS:
                    if pattern.search(content):
                        findings.append(InlineFinding(
                            file=file_path,
                            line=line_no,
                            category="correctness",
                            severity=severity,
                            message=message,
                            emoji=InlineFinding.make_emoji("correctness"),
                        ))

                # --- Style ---
                for pattern, message, severity in _STYLE_PATTERNS:
                    if pattern.search(content):
                        findings.append(InlineFinding(
                            file=file_path,
                            line=line_no,
                            category="style",
                            severity=severity,
                            message=message,
                            emoji=InlineFinding.make_emoji("style"),
                        ))

                # Magic numbers in non-import, non-comment lines
                stripped = content.strip()
                if (
                    not stripped.startswith("#")
                    and not stripped.startswith("import")
                    and not stripped.startswith("from")
                ):
                    magic_match = _MAGIC_NUMBER_PATTERN.search(content)
                    if magic_match:
                        num = int(magic_match.group(1))
                        # Ignore common non-magic numbers
                        if num not in {10, 100, 200, 201, 204, 301, 302, 400, 401, 403, 404, 500, 1000, 1024, 2048, 4096, 8080, 8000, 3000, 443, 80, 0}:
                            findings.append(InlineFinding(
                                file=file_path,
                                line=line_no,
                                category="style",
                                severity="suggestion",
                                message=f"Magic number {num} — consider named constant",
                                emoji=InlineFinding.make_emoji("style"),
                            ))

                # Track function length
                func_match = re.match(r"\s*def\s+(\w+)\s*\(", content)
                if func_match:
                    if func_start is not None and func_lines > 50:
                        findings.append(InlineFinding(
                            file=file_path,
                            line=func_start,
                            category="style",
                            severity="suggestion",
                            message=f"Function '{func_name}' is {func_lines} lines — consider splitting",
                            emoji=InlineFinding.make_emoji("style"),
                        ))
                    func_start = line_no
                    func_name = func_match.group(1)
                    func_lines = 0
                func_lines += 1

                # Deep nesting detection (>4 levels)
                if stripped and not stripped.startswith("#"):
                    indent = len(content) - len(content.lstrip())
                    # Assume 4-space indentation; >4 levels = >16 spaces
                    if indent >= 20:
                        findings.append(InlineFinding(
                            file=file_path,
                            line=line_no,
                            category="style",
                            severity="suggestion",
                            message="Deep nesting (>4 levels) — consider early return or extraction",
                            emoji=InlineFinding.make_emoji("style"),
                        ))

            # Check last function length
            if func_start is not None and func_lines > 50:
                findings.append(InlineFinding(
                    file=file_path,
                    line=func_start,
                    category="style",
                    severity="suggestion",
                    message=f"Function '{func_name}' is {func_lines} lines — consider splitting",
                    emoji=InlineFinding.make_emoji("style"),
                ))

        return findings

    def _build_diff_lines(self, raw: str) -> list[AnnotatedDiffLine]:
        """Convert raw diff text into AnnotatedDiffLine objects."""
        lines: list[AnnotatedDiffLine] = []
        for text in raw.splitlines():
            if text.startswith("diff --git"):
                lines.append(AnnotatedDiffLine(content=text, line_type="file"))
            elif text.startswith("@@"):
                lines.append(AnnotatedDiffLine(content=text, line_type="@@"))
            elif text.startswith("+"):
                lines.append(AnnotatedDiffLine(content=text, line_type="+"))
            elif text.startswith("-"):
                lines.append(AnnotatedDiffLine(content=text, line_type="-"))
            else:
                lines.append(AnnotatedDiffLine(content=text, line_type=" "))
        return lines

    def _annotate_diff(
        self,
        diff_lines: list[AnnotatedDiffLine],
        findings: list[InlineFinding],
    ) -> list[AnnotatedDiffLine]:
        """Attach findings to their corresponding diff lines."""
        # Build lookup: (file, approximate position) -> finding
        # Since diff lines don't carry absolute line numbers directly,
        # we match by tracking current file and line counter
        finding_map: dict[tuple[str, int], InlineFinding] = {}
        for f in findings:
            key = (f.file, f.line)
            # Keep highest severity finding per line
            existing = finding_map.get(key)
            if existing is None or _severity_rank(f.severity) > _severity_rank(existing.severity):
                finding_map[key] = f

        current_file = ""
        new_line_no = 0

        for dl in diff_lines:
            if dl.line_type == "file":
                parts = dl.content.split(" b/", 1)
                current_file = parts[1] if len(parts) > 1 else ""
                continue

            if dl.line_type == "@@":
                match = re.match(r"@@\s+-\d+(?:,\d+)?\s+\+(\d+)", dl.content)
                if match:
                    new_line_no = int(match.group(1))
                continue

            if dl.line_type == "+":
                key = (current_file, new_line_no)
                if key in finding_map:
                    dl.finding = finding_map[key]
                new_line_no += 1
            elif dl.line_type == " ":
                new_line_no += 1
            # "-" lines don't advance new_line_no

        return diff_lines

    def _build_summary(self, findings: list[InlineFinding]) -> dict:
        """Build summary counts by category and severity."""
        summary: dict = {
            "total": len(findings),
            "by_category": {},
            "by_severity": {},
        }
        for f in findings:
            summary["by_category"][f.category] = summary["by_category"].get(f.category, 0) + 1
            summary["by_severity"][f.severity] = summary["by_severity"].get(f.severity, 0) + 1
        return summary


def _severity_rank(severity: str) -> int:
    """Return numeric rank for severity ordering."""
    return {"critical": 3, "warning": 2, "suggestion": 1}.get(severity, 0)


# ---------------------------------------------------------------------------
# Terminal formatting
# ---------------------------------------------------------------------------


def format_annotated_diff(result: CodeReviewResult) -> str:
    """Format the annotated diff with ANSI colors and inline emoji markers."""
    if not result.diff_lines:
        return f"{DIM}  No changes found.{RESET}"

    lines: list[str] = []

    # Header
    lines.append("")
    lines.append(f"  {BOLD}{CYAN}Code Review: {result.base} -> HEAD{RESET}")
    lines.append(f"  {DIM}Files: {len(result.files)} | Findings: {result.summary['total']}{RESET}")

    # Summary bar
    if result.summary["total"] > 0:
        parts = []
        for cat in ("security", "performance", "correctness", "style"):
            count = result.summary.get("by_category", {}).get(cat, 0)
            if count:
                emoji = CATEGORY_EMOJIS.get(cat, "")
                parts.append(f"{emoji} {cat}:{count}")
        lines.append(f"  {' | '.join(parts)}")

    lines.append(f"  {'=' * 70}")
    lines.append("")

    # Diff with inline annotations
    current_file = ""
    for dl in result.diff_lines:
        if dl.line_type == "file":
            parts = dl.content.split(" b/", 1)
            fname = parts[1] if len(parts) > 1 else dl.content
            if fname != current_file:
                current_file = fname
                lines.append(f"  {BOLD}{MAGENTA}{fname}{RESET}")
                lines.append(f"  {DIM}{'-' * 68}{RESET}")
            continue

        if dl.line_type == "@@":
            lines.append(f"  {CYAN}{dl.content}{RESET}")
            continue

        # Format line content
        prefix = "  "
        if dl.line_type == "+":
            formatted = f"{prefix}{GREEN}{dl.content}{RESET}"
        elif dl.line_type == "-":
            formatted = f"{prefix}{RED}{dl.content}{RESET}"
        else:
            formatted = f"{prefix}{DIM}{dl.content}{RESET}"

        lines.append(formatted)

        # Inline finding annotation
        if dl.finding:
            f = dl.finding
            sev_color = SEVERITY_COLORS.get(f.severity, "")
            marker = f"  {sev_color}{BOLD}  {f.emoji} [{f.severity.upper()}] {f.message}{RESET}"
            lines.append(marker)
            if f.suggestion:
                lines.append(f"  {DIM}     Suggestion: {f.suggestion}{RESET}")

    # Footer summary
    lines.append("")
    lines.append(f"  {'=' * 70}")
    _render_summary_footer(result.summary, lines)
    lines.append("")

    return "\n".join(lines)


def _render_summary_footer(summary: dict, lines: list[str]) -> None:
    """Append summary footer lines."""
    total = summary.get("total", 0)
    if total == 0:
        lines.append(f"  {GREEN}{BOLD}No issues found.{RESET}")
        return

    crit = summary.get("by_severity", {}).get("critical", 0)
    warn = summary.get("by_severity", {}).get("warning", 0)
    sugg = summary.get("by_severity", {}).get("suggestion", 0)

    parts = []
    if crit:
        parts.append(f"{SEVERITY_COLORS['critical']}{crit} critical{RESET}")
    if warn:
        parts.append(f"{SEVERITY_COLORS['warning']}{warn} warning{RESET}")
    if sugg:
        parts.append(f"{SEVERITY_COLORS['suggestion']}{sugg} suggestion{RESET}")

    lines.append(f"  {BOLD}Findings: {total}{RESET} ({', '.join(parts)})")


# ---------------------------------------------------------------------------
# Interactive review loop
# ---------------------------------------------------------------------------


def interactive_review(result: CodeReviewResult) -> CodeReviewResult:
    """Interactive accept/dismiss loop for each finding.

    Prompts user for each finding:
      [a]ccept  — mark as valid (accepted=True)
      [d]ismiss — mark as false positive (accepted=False)
      [s]kip    — leave unresolved (accepted=None)
      [q]uit    — stop reviewing remaining
    """
    if not result.findings:
        print(f"  {DIM}No findings to review.{RESET}")
        return result

    print()
    print(f"  {BOLD}Interactive Review — {len(result.findings)} finding(s){RESET}")
    print(f"  {DIM}[a]ccept  [d]ismiss  [s]kip  [q]uit{RESET}")
    print()

    for i, finding in enumerate(result.findings, 1):
        sev_color = SEVERITY_COLORS.get(finding.severity, "")
        print(f"  {BOLD}[{i}/{len(result.findings)}]{RESET} {finding.emoji} {sev_color}[{finding.severity.upper()}]{RESET}")
        print(f"  {finding.file}:{finding.line}")
        print(f"  {finding.message}")
        if finding.suggestion:
            print(f"  {DIM}Suggestion: {finding.suggestion}{RESET}")

        try:
            choice = input(f"  {CYAN}> {RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice in ("a", "accept"):
            finding.accepted = True
            print(f"  {GREEN}Accepted{RESET}")
        elif choice in ("d", "dismiss"):
            finding.accepted = False
            print(f"  {YELLOW}Dismissed{RESET}")
        elif choice in ("q", "quit"):
            print(f"  {DIM}Stopped.{RESET}")
            break
        else:
            # Skip
            pass
        print()

    accepted = sum(1 for f in result.findings if f.accepted is True)
    dismissed = sum(1 for f in result.findings if f.accepted is False)
    skipped = sum(1 for f in result.findings if f.accepted is None)
    print(f"  {BOLD}Result:{RESET} {GREEN}{accepted} accepted{RESET}, {YELLOW}{dismissed} dismissed{RESET}, {DIM}{skipped} skipped{RESET}")

    return result


# ---------------------------------------------------------------------------
# Auto-fix mode
# ---------------------------------------------------------------------------

# Simple auto-fixable patterns: (pattern, replacement_func, description)
_AUTO_FIXES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"except\s*:"), "except Exception:", "Bare except -> except Exception"),
    (re.compile(r"==\s*None"), "is None", "'== None' -> 'is None'"),
    (re.compile(r"!=\s*None"), "is not None", "'!= None' -> 'is not None'"),
]


def apply_fixes(result: CodeReviewResult, cwd: str) -> int:
    """Apply auto-fixes for accepted or all fixable findings.

    Returns the number of fixes applied.
    """
    # Gather fixable findings (accepted ones, or all if none reviewed)
    has_reviewed = any(f.accepted is not None for f in result.findings)
    fixable = [
        f for f in result.findings
        if (not has_reviewed or f.accepted is True)
        and f.category in ("correctness",)
    ]

    if not fixable:
        logger.info("No fixable findings")
        return 0

    fixes_applied = 0
    files_modified: dict[str, list[str]] = {}

    for finding in fixable:
        file_path = os.path.join(cwd, finding.file)
        if not os.path.isfile(file_path):
            continue

        if finding.file not in files_modified:
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    files_modified[finding.file] = fh.readlines()
            except (OSError, UnicodeDecodeError):
                continue

        file_lines = files_modified[finding.file]
        idx = finding.line - 1
        if 0 <= idx < len(file_lines):
            original = file_lines[idx]
            modified = original
            for pattern, replacement, _desc in _AUTO_FIXES:
                if pattern.search(modified):
                    modified = pattern.sub(replacement, modified)
            if modified != original:
                file_lines[idx] = modified
                fixes_applied += 1
                logger.info("Fixed %s:%d", finding.file, finding.line)

    # Write back modified files
    for rel_path, file_lines in files_modified.items():
        abs_path = os.path.join(cwd, rel_path)
        try:
            with open(abs_path, "w", encoding="utf-8") as fh:
                fh.writelines(file_lines)
            logger.info("Wrote fixes to %s", abs_path)
        except OSError as e:
            logger.error("Failed to write %s: %s", abs_path, e)

    return fixes_applied


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


def to_json(result: CodeReviewResult) -> dict:
    """Convert review result to JSON-serializable dict."""
    return {
        "base": result.base,
        "head": result.head,
        "files": result.files,
        "summary": result.summary,
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "category": f.category,
                "severity": f.severity,
                "message": f.message,
                "suggestion": f.suggestion,
                "accepted": f.accepted,
            }
            for f in result.findings
        ],
    }
