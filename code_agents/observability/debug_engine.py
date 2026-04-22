"""Autonomous Debug Engine — reproduce, trace, root-cause, fix, verify loop.

Given a bug description, error log, or failing test, the debug engine:
1. Reproduces the issue (runs the failing test/command)
2. Traces through code using the knowledge graph to find root cause
3. Proposes a fix with blast-radius analysis
4. Implements the fix across files
5. Runs tests to verify, self-corrects if still failing
6. Creates a smart commit + optional PR

Usage:
    from code_agents.observability.debug_engine import DebugEngine
    engine = DebugEngine(cwd="/path/to/repo")
    result = await engine.run("test_login fails with AttributeError on line 42")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.observability.debug_engine")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class DebugTrace:
    """A single trace step in the debug investigation."""
    step: str  # reproduce, trace, root_cause, fix, verify
    description: str
    output: str = ""
    duration_ms: int = 0
    success: bool = False


@dataclass
class DebugFix:
    """A proposed fix for the bug."""
    file: str
    line: int
    original: str
    replacement: str
    explanation: str


@dataclass
class BlastRadius:
    """Impact analysis of the fix."""
    files_affected: list[str] = field(default_factory=list)
    tests_affected: list[str] = field(default_factory=list)
    risk_level: str = "low"  # low, medium, high
    notes: str = ""


@dataclass
class DebugResult:
    """Full result of a debug session."""
    bug_description: str
    status: str = "pending"  # pending, reproducing, tracing, fixing, verifying, resolved, failed
    error_type: str = ""
    error_message: str = ""
    error_file: str = ""
    error_line: int = 0
    root_cause: str = ""
    traces: list[DebugTrace] = field(default_factory=list)
    fixes: list[DebugFix] = field(default_factory=list)
    blast_radius: BlastRadius = field(default_factory=BlastRadius)
    verified: bool = False
    attempts: int = 0
    max_attempts: int = 3
    total_duration_ms: int = 0
    timestamp: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.status == "resolved" and self.verified


# ---------------------------------------------------------------------------
# Error parser — extracts structured info from error output
# ---------------------------------------------------------------------------


class ErrorParser:
    """Parse error output from tests/commands into structured data."""

    # Python traceback patterns
    _PY_TRACEBACK = re.compile(
        r'File "([^"]+)", line (\d+), in (\w+)'
    )
    _PY_ERROR = re.compile(
        r'^(\w+Error|\w+Exception|AssertionError): (.+)$', re.MULTILINE
    )

    # JavaScript/Node patterns
    _JS_ERROR = re.compile(
        r'at (?:Object\.|Module\.|)(\S+) \(([^:]+):(\d+):\d+\)'
    )
    _JS_ERR_MSG = re.compile(
        r'^(TypeError|ReferenceError|SyntaxError|RangeError|Error): (.+)$', re.MULTILINE
    )

    # Java patterns
    _JAVA_ERROR = re.compile(
        r'at (\S+)\(([^:]+):(\d+)\)'
    )

    # Go patterns
    _GO_ERROR = re.compile(
        r'(\S+\.go):(\d+):\d+: (.+)'
    )

    # Generic test failure patterns
    _TEST_FAIL = re.compile(
        r'(FAIL|FAILED|ERROR|FAILURE)\s*[:\-]?\s*(.+)', re.IGNORECASE
    )

    @classmethod
    def parse(cls, output: str) -> dict:
        """Parse error output and extract structured information."""
        result = {
            "error_type": "",
            "error_message": "",
            "error_file": "",
            "error_line": 0,
            "stack_frames": [],
            "language": "unknown",
        }

        # Try Python traceback
        py_frames = cls._PY_TRACEBACK.findall(output)
        py_error = cls._PY_ERROR.search(output)
        if py_frames:
            result["language"] = "python"
            result["stack_frames"] = [
                {"file": f, "line": int(l), "function": fn}
                for f, l, fn in py_frames
            ]
            if py_frames:
                last = py_frames[-1]
                result["error_file"] = last[0]
                result["error_line"] = int(last[1])
            if py_error:
                result["error_type"] = py_error.group(1)
                result["error_message"] = py_error.group(2)
            return result

        # Try JavaScript
        js_frames = cls._JS_ERROR.findall(output)
        js_error = cls._JS_ERR_MSG.search(output)
        if js_frames:
            result["language"] = "javascript"
            result["stack_frames"] = [
                {"file": f, "line": int(l), "function": fn}
                for fn, f, l in js_frames
            ]
            if js_frames:
                last = js_frames[0]
                result["error_file"] = last[1]
                result["error_line"] = int(last[2])
            if js_error:
                result["error_type"] = js_error.group(1)
                result["error_message"] = js_error.group(2)
            return result

        # Try Java
        java_frames = cls._JAVA_ERROR.findall(output)
        if java_frames:
            result["language"] = "java"
            result["stack_frames"] = [
                {"file": f, "line": int(l), "function": cls_name}
                for cls_name, f, l in java_frames
            ]
            if java_frames:
                last = java_frames[0]
                result["error_file"] = last[1]
                result["error_line"] = int(last[2])
            return result

        # Try Go
        go_matches = cls._GO_ERROR.findall(output)
        if go_matches:
            result["language"] = "go"
            if go_matches:
                first = go_matches[0]
                result["error_file"] = first[0]
                result["error_line"] = int(first[1])
                result["error_message"] = first[2]
            return result

        # Generic test failure
        test_fail = cls._TEST_FAIL.search(output)
        if test_fail:
            result["error_message"] = test_fail.group(2).strip()

        return result


# ---------------------------------------------------------------------------
# Debug Engine
# ---------------------------------------------------------------------------


class DebugEngine:
    """Autonomous debugging engine — reproduce, trace, fix, verify."""

    def __init__(
        self,
        cwd: str = "",
        server_url: str = "",
        max_attempts: int = 3,
        auto_fix: bool = True,
        auto_commit: bool = False,
    ):
        self.cwd = cwd or os.getenv("TARGET_REPO_PATH", os.getcwd())
        self.server_url = server_url or os.getenv(
            "CODE_AGENTS_PUBLIC_BASE_URL",
            f"http://127.0.0.1:{os.getenv('PORT', '8000')}"
        )
        self.max_attempts = max_attempts
        self.auto_fix = auto_fix
        self.auto_commit = auto_commit
        self.result: Optional[DebugResult] = None

    # --- Step 1: Reproduce ---

    def reproduce(self, bug_input: str) -> DebugTrace:
        """Try to reproduce the bug by running the failing test/command."""
        trace = DebugTrace(step="reproduce", description="Attempting to reproduce the issue")
        start = time.monotonic()

        # Detect if input is a test name, command, or error description
        test_cmd = self._detect_test_command(bug_input)

        if test_cmd:
            trace.description = f"Running: {test_cmd}"
            try:
                proc = subprocess.run(
                    test_cmd, shell=True, cwd=self.cwd,
                    capture_output=True, text=True, timeout=120,
                )
                trace.output = proc.stdout + "\n" + proc.stderr
                trace.success = proc.returncode != 0  # "success" means we reproduced the failure
                if not trace.success:
                    trace.description += " (test passed — cannot reproduce)"
            except subprocess.TimeoutExpired:
                trace.output = "Command timed out after 120s"
                trace.success = False
            except Exception as e:
                trace.output = str(e)
                trace.success = False
        else:
            # Input is an error description — parse it directly
            trace.description = "Parsing error description (no runnable command detected)"
            trace.output = bug_input
            trace.success = True

        trace.duration_ms = int((time.monotonic() - start) * 1000)
        return trace

    def _detect_test_command(self, bug_input: str) -> str:
        """Detect if the input is a runnable test command."""
        inp = bug_input.strip()

        # Direct command patterns
        if inp.startswith(("pytest ", "python ", "npm ", "yarn ", "go test", "mvn ", "gradle ", "cargo test")):
            return inp

        # Test file pattern: tests/test_foo.py or test_foo.py::test_bar
        if re.match(r'^tests?[\\/][\w\-/]+\.py', inp) or re.match(r'^[\w\-/]+\.py::[\w]+', inp):
            return f"python -m pytest {inp} -x -v"

        # Jest/Mocha pattern
        if re.match(r'^[\w\-/]+\.(test|spec)\.(js|ts|jsx|tsx)', inp):
            return f"npx jest {inp} --verbose"

        # Go test pattern
        if re.match(r'^[\w\-/]+_test\.go', inp):
            pkg_dir = str(Path(inp).parent) or "."
            return f"go test -v -run . ./{pkg_dir}"

        # Check if it looks like a command (starts with common tool names)
        if inp.startswith(("make ", "bash ", "sh ", "node ", "ruby ", "java ")):
            return inp

        return ""

    # --- Step 2: Trace ---

    def trace(self, error_output: str) -> DebugTrace:
        """Parse error output and trace through code to find root cause."""
        trace = DebugTrace(step="trace", description="Analyzing error and tracing through code")
        start = time.monotonic()

        parsed = ErrorParser.parse(error_output)
        trace.output = json.dumps(parsed, indent=2)

        # Read the error file for context
        error_file = parsed.get("error_file", "")
        error_line = parsed.get("error_line", 0)

        if error_file and error_line:
            file_context = self._read_file_context(error_file, error_line)
            if file_context:
                trace.output += f"\n\n--- File Context ({error_file}:{error_line}) ---\n{file_context}"

        # Try to get knowledge graph context
        kg_context = self._get_kg_context(error_file)
        if kg_context:
            trace.output += f"\n\n--- Knowledge Graph ---\n{kg_context}"

        trace.success = bool(error_file or parsed.get("error_message"))
        trace.duration_ms = int((time.monotonic() - start) * 1000)
        return trace

    def _read_file_context(self, filepath: str, line: int, context: int = 10) -> str:
        """Read lines around the error location."""
        # Resolve relative paths
        if not os.path.isabs(filepath):
            filepath = os.path.join(self.cwd, filepath)

        if not os.path.isfile(filepath):
            # Try to find in repo
            for root, dirs, files in os.walk(self.cwd):
                dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", ".venv")]
                base = os.path.basename(filepath)
                if base in files:
                    filepath = os.path.join(root, base)
                    break
            else:
                return ""

        try:
            with open(filepath) as f:
                lines = f.readlines()

            start = max(0, line - context - 1)
            end = min(len(lines), line + context)
            result_lines = []
            for i in range(start, end):
                marker = ">>>" if i + 1 == line else "   "
                result_lines.append(f"{marker} {i + 1:4d} | {lines[i].rstrip()}")
            return "\n".join(result_lines)
        except Exception:
            return ""

    def _get_kg_context(self, filepath: str) -> str:
        """Get knowledge graph context for a file."""
        try:
            from code_agents.knowledge.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph(self.cwd)
            kg.build()

            if not filepath:
                return ""

            basename = os.path.basename(filepath)
            # Find symbols in this file
            symbols = [s for s in kg.symbols if basename in s.get("file", "")]
            if symbols:
                return json.dumps(symbols[:10], indent=2)
        except Exception:
            pass
        return ""

    # --- Step 3: Root Cause Analysis (AI) ---

    async def analyze_root_cause(self, traces: list[DebugTrace]) -> DebugTrace:
        """Use AI to analyze the root cause from collected traces."""
        trace = DebugTrace(step="root_cause", description="AI analyzing root cause")
        start = time.monotonic()

        # Build context from all traces
        context_parts = []
        for t in traces:
            context_parts.append(f"## {t.step.upper()}\n{t.description}\n```\n{t.output[:3000]}\n```")

        prompt = (
            "You are debugging a software issue. Analyze the following debug traces and:\n"
            "1. Identify the ROOT CAUSE of the bug\n"
            "2. Explain WHY the error occurs\n"
            "3. Propose a CONCRETE FIX with exact file, line, and code changes\n\n"
            "Respond with JSON:\n"
            '{"root_cause": "...", "explanation": "...", "fixes": [{"file": "path", "line": N, '
            '"original": "old code", "replacement": "new code", "explanation": "why this fixes it"}]}\n\n'
            + "\n\n".join(context_parts)
        )

        ai_response = await self._call_agent(prompt, agent="code-reasoning")

        if ai_response:
            trace.output = ai_response
            # Parse the fix suggestions
            try:
                match = re.search(r'\{[\s\S]*\}', ai_response)
                if match:
                    data = json.loads(match.group())
                    trace.output = json.dumps(data, indent=2)
                    trace.success = True
            except (json.JSONDecodeError, AttributeError):
                trace.success = bool(ai_response)
        else:
            trace.output = "AI analysis unavailable — using static analysis only"
            trace.success = False

        trace.duration_ms = int((time.monotonic() - start) * 1000)
        return trace

    # --- Step 4: Apply Fix ---

    def apply_fixes(self, fixes: list[DebugFix]) -> DebugTrace:
        """Apply the proposed fixes to the codebase."""
        trace = DebugTrace(step="fix", description=f"Applying {len(fixes)} fix(es)")
        start = time.monotonic()

        applied = []
        for fix in fixes:
            filepath = fix.file
            if not os.path.isabs(filepath):
                filepath = os.path.join(self.cwd, filepath)

            if not os.path.isfile(filepath):
                trace.output += f"SKIP: File not found: {fix.file}\n"
                continue

            try:
                content = Path(filepath).read_text()
                if fix.original in content:
                    new_content = content.replace(fix.original, fix.replacement, 1)
                    Path(filepath).write_text(new_content)
                    applied.append(fix.file)
                    trace.output += f"APPLIED: {fix.file}:{fix.line} — {fix.explanation}\n"
                else:
                    trace.output += f"SKIP: Original code not found in {fix.file}\n"
            except Exception as e:
                trace.output += f"ERROR: {fix.file} — {e}\n"

        trace.success = len(applied) > 0
        trace.description = f"Applied {len(applied)}/{len(fixes)} fix(es)"
        trace.duration_ms = int((time.monotonic() - start) * 1000)
        return trace

    # --- Step 5: Verify ---

    def verify(self, test_cmd: str) -> DebugTrace:
        """Re-run the original test/command to verify the fix works."""
        trace = DebugTrace(step="verify", description=f"Verifying fix: {test_cmd}")
        start = time.monotonic()

        if not test_cmd:
            trace.output = "No test command to verify — manual verification needed"
            trace.success = False
            trace.duration_ms = int((time.monotonic() - start) * 1000)
            return trace

        try:
            proc = subprocess.run(
                test_cmd, shell=True, cwd=self.cwd,
                capture_output=True, text=True, timeout=120,
            )
            trace.output = proc.stdout + "\n" + proc.stderr
            trace.success = proc.returncode == 0
            if trace.success:
                trace.description = "Fix verified — test passes!"
            else:
                trace.description = "Fix did not resolve the issue"
        except subprocess.TimeoutExpired:
            trace.output = "Verification timed out after 120s"
            trace.success = False
        except Exception as e:
            trace.output = str(e)
            trace.success = False

        trace.duration_ms = int((time.monotonic() - start) * 1000)
        return trace

    # --- Step 6: Blast Radius ---

    def analyze_blast_radius(self, fixes: list[DebugFix]) -> BlastRadius:
        """Analyze the impact of the fixes."""
        br = BlastRadius()

        for fix in fixes:
            br.files_affected.append(fix.file)

            # Find tests that might be affected
            base = Path(fix.file).stem
            test_patterns = [f"test_{base}", f"{base}_test", f"{base}.test", f"{base}.spec"]
            for root, dirs, files in os.walk(self.cwd):
                dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", ".venv")]
                for f in files:
                    for pattern in test_patterns:
                        if pattern in f:
                            br.tests_affected.append(os.path.relpath(os.path.join(root, f), self.cwd))

        # Risk assessment
        if len(br.files_affected) > 5:
            br.risk_level = "high"
            br.notes = "Large number of files affected — review carefully"
        elif len(br.files_affected) > 2:
            br.risk_level = "medium"
            br.notes = "Multiple files affected — consider running full test suite"
        else:
            br.risk_level = "low"
            br.notes = "Focused change — low risk"

        return br

    # --- Main Run Loop ---

    async def run(self, bug_input: str, progress_callback=None) -> DebugResult:
        """Run the full autonomous debug loop."""
        self.result = DebugResult(
            bug_description=bug_input,
            max_attempts=self.max_attempts,
            timestamp=datetime.now().isoformat(),
        )
        overall_start = time.monotonic()

        def _progress(msg: str):
            if progress_callback:
                progress_callback(self.result.status, msg)

        # Step 1: Reproduce
        self.result.status = "reproducing"
        _progress("Reproducing the issue...")
        repro_trace = self.reproduce(bug_input)
        self.result.traces.append(repro_trace)

        # Parse error info from reproduction output
        parsed = ErrorParser.parse(repro_trace.output)
        self.result.error_type = parsed.get("error_type", "")
        self.result.error_message = parsed.get("error_message", "")
        self.result.error_file = parsed.get("error_file", "")
        self.result.error_line = parsed.get("error_line", 0)

        # Step 2: Trace
        self.result.status = "tracing"
        _progress("Tracing through code...")
        trace_result = self.trace(repro_trace.output)
        self.result.traces.append(trace_result)

        # Step 3: AI Root Cause Analysis
        _progress("Analyzing root cause with AI...")
        rca_trace = await self.analyze_root_cause(self.result.traces)
        self.result.traces.append(rca_trace)

        # Parse fixes from AI response
        fixes = self._parse_fixes(rca_trace.output)
        if rca_trace.success:
            try:
                data = json.loads(rca_trace.output)
                self.result.root_cause = data.get("root_cause", "")
            except (json.JSONDecodeError, TypeError):
                self.result.root_cause = "See AI analysis in traces"

        # Step 4: Apply Fix + Verify (with retry loop)
        test_cmd = self._detect_test_command(bug_input)

        if fixes and self.auto_fix:
            for attempt in range(1, self.max_attempts + 1):
                self.result.attempts = attempt
                self.result.status = "fixing"
                _progress(f"Applying fix (attempt {attempt}/{self.max_attempts})...")

                self.result.fixes = fixes
                fix_trace = self.apply_fixes(fixes)
                self.result.traces.append(fix_trace)

                if not fix_trace.success:
                    break

                # Blast radius
                self.result.blast_radius = self.analyze_blast_radius(fixes)

                # Step 5: Verify
                self.result.status = "verifying"
                _progress("Verifying fix...")
                verify_trace = self.verify(test_cmd)
                self.result.traces.append(verify_trace)

                if verify_trace.success:
                    self.result.verified = True
                    self.result.status = "resolved"
                    _progress("Bug fixed and verified!")
                    break
                elif attempt < self.max_attempts:
                    _progress(f"Fix failed — retrying with AI (attempt {attempt + 1})...")
                    # Get AI to suggest a different fix
                    retry_trace = await self.analyze_root_cause(self.result.traces)
                    self.result.traces.append(retry_trace)
                    fixes = self._parse_fixes(retry_trace.output)
                    if not fixes:
                        break
        else:
            if not fixes:
                self.result.status = "failed"
                _progress("Could not determine a fix")
            else:
                self.result.status = "pending"
                _progress("Fix proposed but auto-fix is disabled")

        if not self.result.verified and self.result.status != "pending":
            self.result.status = "failed"

        self.result.total_duration_ms = int((time.monotonic() - overall_start) * 1000)

        # Auto-commit if successful
        if self.result.is_resolved and self.auto_commit:
            self._create_commit()

        return self.result

    def _parse_fixes(self, ai_output: str) -> list[DebugFix]:
        """Parse DebugFix objects from AI output."""
        fixes = []
        try:
            data = json.loads(ai_output)
            for f in data.get("fixes", []):
                fixes.append(DebugFix(
                    file=f.get("file", ""),
                    line=f.get("line", 0),
                    original=f.get("original", ""),
                    replacement=f.get("replacement", ""),
                    explanation=f.get("explanation", ""),
                ))
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
        return fixes

    def _create_commit(self):
        """Create a smart commit for the fix."""
        try:
            # Stage changed files
            for fix in self.result.fixes:
                filepath = fix.file
                if not os.path.isabs(filepath):
                    filepath = os.path.join(self.cwd, filepath)
                subprocess.run(
                    ["git", "add", filepath],
                    cwd=self.cwd, capture_output=True, timeout=10,
                )

            msg = f"fix: {self.result.root_cause or self.result.bug_description}"
            if len(msg) > 72:
                msg = msg[:69] + "..."

            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=self.cwd, capture_output=True, timeout=30,
            )
            logger.info("Auto-committed debug fix: %s", msg)
        except Exception as e:
            logger.warning("Auto-commit failed: %s", e)

    async def _call_agent(self, prompt: str, agent: str = "code-reasoning") -> str:
        """Send a prompt to an agent and get the response."""
        try:
            import httpx

            payload = {
                "model": agent,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }

            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    f"{self.server_url}/v1/chat/completions",
                    json=payload,
                    headers={"X-Agent": agent},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.debug("Agent call failed (%s): %s", agent, e)
        return ""


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_debug_result(result: DebugResult) -> str:
    """Format debug result for terminal display."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.tree import Tree

        console = Console()
        lines = []

        # Status panel
        status_color = "green" if result.is_resolved else "red" if result.status == "failed" else "yellow"
        status_text = (
            f"[bold {status_color}]{result.status.upper()}[/bold {status_color}]  |  "
            f"Attempts: {result.attempts}/{result.max_attempts}  |  "
            f"Duration: {result.total_duration_ms:,}ms"
        )
        console.print(Panel(status_text, title="Debug Session", border_style=status_color))

        # Bug info
        console.print(f"\n  [bold]Bug:[/bold] {result.bug_description}")
        if result.error_type:
            console.print(f"  [bold]Error:[/bold] [red]{result.error_type}: {result.error_message}[/red]")
        if result.error_file:
            console.print(f"  [bold]Location:[/bold] {result.error_file}:{result.error_line}")
        if result.root_cause:
            console.print(f"  [bold]Root Cause:[/bold] {result.root_cause}")

        # Trace timeline
        console.print()
        tree = Tree("[bold]Debug Timeline[/bold]")
        for t in result.traces:
            icon = "[green]OK[/green]" if t.success else "[red]FAIL[/red]"
            node = tree.add(f"{icon} [{t.step}] {t.description} ({t.duration_ms}ms)")
            if t.output and len(t.output) < 200:
                node.add(f"[dim]{t.output[:200]}[/dim]")
        console.print(tree)

        # Fixes
        if result.fixes:
            console.print()
            table = Table(title="Applied Fixes", show_lines=True)
            table.add_column("File", style="bold")
            table.add_column("Line", justify="center")
            table.add_column("Fix", max_width=50)

            for fix in result.fixes:
                table.add_row(fix.file, str(fix.line), fix.explanation)
            console.print(table)

        # Blast radius
        if result.blast_radius.files_affected:
            br = result.blast_radius
            risk_color = {"low": "green", "medium": "yellow", "high": "red"}.get(br.risk_level, "white")
            console.print(f"\n  [bold]Blast Radius:[/bold] [{risk_color}]{br.risk_level.upper()}[/{risk_color}]")
            console.print(f"  Files: {', '.join(br.files_affected)}")
            if br.tests_affected:
                console.print(f"  Tests: {', '.join(br.tests_affected)}")
            if br.notes:
                console.print(f"  [dim]{br.notes}[/dim]")

        console.print()

    except ImportError:
        # Fallback without rich
        lines = []
        lines.append(f"\n  === Debug Session: {result.status.upper()} ===")
        lines.append(f"  Bug: {result.bug_description}")
        if result.error_type:
            lines.append(f"  Error: {result.error_type}: {result.error_message}")
        if result.error_file:
            lines.append(f"  Location: {result.error_file}:{result.error_line}")
        if result.root_cause:
            lines.append(f"  Root Cause: {result.root_cause}")
        lines.append(f"  Attempts: {result.attempts}/{result.max_attempts}")
        lines.append(f"  Duration: {result.total_duration_ms:,}ms")

        lines.append("\n  Timeline:")
        for t in result.traces:
            icon = "OK" if t.success else "FAIL"
            lines.append(f"    [{icon}] {t.step}: {t.description} ({t.duration_ms}ms)")

        if result.fixes:
            lines.append("\n  Fixes:")
            for fix in result.fixes:
                lines.append(f"    {fix.file}:{fix.line} — {fix.explanation}")

        lines.append("")
        print("\n".join(lines))

    return ""


# ---------------------------------------------------------------------------
# CLI / Slash entry points
# ---------------------------------------------------------------------------


def cmd_debug(args: list[str] | None = None):
    """CLI entry point for `code-agents debug`."""
    args = args or []

    if not args or "--help" in args:
        print()
        print("  Autonomous Debug Engine")
        print("  " + "=" * 40)
        print()
        print("  Usage:")
        print("    code-agents debug <test-or-error>       # debug a failing test or error")
        print("    code-agents debug tests/test_foo.py      # debug a test file")
        print('    code-agents debug "AttributeError in login()"  # debug from error description')
        print("    code-agents debug --no-fix <test>        # analyze only, don't auto-fix")
        print("    code-agents debug --commit <test>        # auto-commit if fix verified")
        print()
        print("  Options:")
        print("    --no-fix      Analyze only, don't apply fixes")
        print("    --commit      Auto-commit the fix if verified")
        print("    --attempts N  Max fix attempts (default: 3)")
        print("    --json        Output as JSON")
        print()
        return

    # Parse flags
    auto_fix = "--no-fix" not in args
    auto_commit = "--commit" in args
    json_output = "--json" in args
    max_attempts = 3

    if "--attempts" in args:
        idx = args.index("--attempts")
        if idx + 1 < len(args):
            try:
                max_attempts = int(args[idx + 1])
            except ValueError:
                pass

    # Bug input is everything that's not a flag
    flag_args = {"--no-fix", "--commit", "--json", "--help", "--attempts"}
    bug_parts = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in flag_args:
            if a == "--attempts":
                skip_next = True
            continue
        bug_parts.append(a)

    bug_input = " ".join(bug_parts)
    if not bug_input:
        print("  Error: No bug description or test command provided")
        print("  Run 'code-agents debug --help' for usage")
        return

    from code_agents.cli.cli_helpers import _load_env, _server_url
    _load_env()
    url = _server_url()

    engine = DebugEngine(
        server_url=url,
        max_attempts=max_attempts,
        auto_fix=auto_fix,
        auto_commit=auto_commit,
    )

    print()
    print("  Autonomous Debug Engine")
    print("  " + "=" * 40)
    print(f"  Input: {bug_input}")
    print(f"  Auto-fix: {'ON' if auto_fix else 'OFF'}")
    print(f"  Max attempts: {max_attempts}")
    print()

    def progress(status, msg):
        print(f"  [{status.upper():>12}] {msg}")

    result = asyncio.run(engine.run(bug_input, progress_callback=progress))

    if json_output:
        print(json.dumps(asdict(result), indent=2))
    else:
        format_debug_result(result)
