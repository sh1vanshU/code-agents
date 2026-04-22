"""Stack Decoder — paste a stack trace, get mapped code locations + root cause + fix.

Parses Python, Java, JS/TS, Go stack traces. Maps frames to local files,
explains the error, and suggests likely fixes.

Usage:
    from code_agents.observability.stack_decoder import StackDecoder
    decoder = StackDecoder("/path/to/repo")
    result = decoder.decode(stack_trace_text)
    print(format_stack_decode(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.observability.stack_decoder")


@dataclass
class StackFrame:
    """A single frame in a stack trace."""
    file: str = ""
    line: int = 0
    function: str = ""
    code: str = ""
    is_local: bool = False  # True if file exists in the repo
    local_path: str = ""  # resolved local path


@dataclass
class StackDecodeConfig:
    cwd: str = "."


@dataclass
class StackDecodeResult:
    """Result of decoding a stack trace."""
    raw_trace: str = ""
    language: str = ""  # python, java, javascript, go
    error_type: str = ""
    error_message: str = ""
    frames: list[StackFrame] = field(default_factory=list)
    root_cause_frame: Optional[StackFrame] = None
    explanation: str = ""
    suggested_fix: str = ""
    related_files: list[str] = field(default_factory=list)


class StackDecoder:
    """Decode and analyze stack traces."""

    def __init__(self, config: StackDecodeConfig):
        self.config = config

    def decode(self, trace: str) -> StackDecodeResult:
        """Decode a stack trace."""
        logger.info("Decoding stack trace (%d chars)", len(trace))
        result = StackDecodeResult(raw_trace=trace)

        # Detect language
        result.language = self._detect_language(trace)

        # Parse frames
        if result.language == "python":
            self._parse_python(trace, result)
        elif result.language == "java":
            self._parse_java(trace, result)
        elif result.language == "javascript":
            self._parse_javascript(trace, result)
        elif result.language == "go":
            self._parse_go(trace, result)

        # Resolve local files
        self._resolve_local_files(result)

        # Identify root cause
        self._identify_root_cause(result)

        # Generate explanation and fix
        self._explain(result)

        return result

    def _detect_language(self, trace: str) -> str:
        if "Traceback (most recent call last)" in trace or "File \"" in trace:
            return "python"
        if "at " in trace and ".java:" in trace:
            return "java"
        if "goroutine" in trace or ".go:" in trace:
            return "go"
        if "at " in trace and (".js:" in trace or ".ts:" in trace):
            return "javascript"
        if "Error:" in trace or "TypeError" in trace or "SyntaxError" in trace:
            return "python"  # default fallback
        return "unknown"

    def _parse_python(self, trace: str, result: StackDecodeResult):
        # Extract error type and message
        lines = trace.strip().splitlines()
        for line in reversed(lines):
            err_match = re.match(r"^(\w+(?:\.\w+)*Error|\w+Exception|KeyError|ValueError|TypeError|AttributeError|ImportError|IndexError|RuntimeError|FileNotFoundError|OSError|IOError|StopIteration|AssertionError|NotImplementedError|ZeroDivisionError)\s*:\s*(.*)", line)
            if err_match:
                result.error_type = err_match.group(1)
                result.error_message = err_match.group(2)
                break
            # Bare exception name
            if re.match(r"^(\w+Error|\w+Exception)$", line.strip()):
                result.error_type = line.strip()
                break

        # Extract frames
        frame_pattern = re.compile(r'File "([^"]+)", line (\d+), in (.+)')
        for i, line in enumerate(lines):
            match = frame_pattern.search(line)
            if match:
                code = lines[i + 1].strip() if i + 1 < len(lines) else ""
                result.frames.append(StackFrame(
                    file=match.group(1),
                    line=int(match.group(2)),
                    function=match.group(3),
                    code=code,
                ))

    def _parse_java(self, trace: str, result: StackDecodeResult):
        lines = trace.strip().splitlines()
        if lines:
            err_match = re.match(r"^([\w.]+(?:Exception|Error)):\s*(.*)", lines[0])
            if err_match:
                result.error_type = err_match.group(1)
                result.error_message = err_match.group(2)

        frame_pattern = re.compile(r"\s+at\s+([\w.$]+)\(([\w.]+):(\d+)\)")
        for line in lines:
            match = frame_pattern.search(line)
            if match:
                result.frames.append(StackFrame(
                    function=match.group(1),
                    file=match.group(2),
                    line=int(match.group(3)),
                ))

    def _parse_javascript(self, trace: str, result: StackDecodeResult):
        lines = trace.strip().splitlines()
        if lines:
            err_match = re.match(r"^(\w+Error):\s*(.*)", lines[0])
            if err_match:
                result.error_type = err_match.group(1)
                result.error_message = err_match.group(2)

        frame_pattern = re.compile(r"\s+at\s+(?:(\S+)\s+)?\(?(.+?):(\d+):\d+\)?")
        for line in lines:
            match = frame_pattern.search(line)
            if match:
                result.frames.append(StackFrame(
                    function=match.group(1) or "<anonymous>",
                    file=match.group(2),
                    line=int(match.group(3)),
                ))

    def _parse_go(self, trace: str, result: StackDecodeResult):
        lines = trace.strip().splitlines()
        for line in lines:
            if "panic:" in line:
                result.error_type = "panic"
                result.error_message = line.split("panic:", 1)[1].strip()

        frame_pattern = re.compile(r"^\s*([\w/.-]+\.go):(\d+)")
        func_pattern = re.compile(r"^([\w/.-]+)\(")
        current_func = ""
        for line in lines:
            func_match = func_pattern.match(line)
            if func_match:
                current_func = func_match.group(1)
                continue
            match = frame_pattern.match(line)
            if match:
                result.frames.append(StackFrame(
                    file=match.group(1),
                    line=int(match.group(2)),
                    function=current_func,
                ))

    def _resolve_local_files(self, result: StackDecodeResult):
        """Check if frame files exist in the local repo."""
        for frame in result.frames:
            candidates = [
                os.path.join(self.config.cwd, frame.file),
                os.path.join(self.config.cwd, os.path.basename(frame.file)),
            ]
            # Try stripping common prefixes
            for prefix in ["/app/", "/src/", "/home/", "/opt/"]:
                if frame.file.startswith(prefix):
                    candidates.append(os.path.join(self.config.cwd, frame.file[len(prefix):]))

            for candidate in candidates:
                if os.path.exists(candidate):
                    frame.is_local = True
                    frame.local_path = candidate
                    result.related_files.append(candidate)
                    break

    def _identify_root_cause(self, result: StackDecodeResult):
        """Find the most likely root cause frame."""
        # Prefer local frames (user code, not library code)
        local_frames = [f for f in result.frames if f.is_local]
        if local_frames:
            result.root_cause_frame = local_frames[-1]  # deepest local frame
        elif result.frames:
            result.root_cause_frame = result.frames[-1]

    def _explain(self, result: StackDecodeResult):
        """Generate explanation and fix suggestion."""
        explanations = {
            "TypeError": "A function received an argument of the wrong type, or an operation was applied to an incompatible type.",
            "AttributeError": "Tried to access an attribute that doesn't exist on the object. Common when the object is None or the wrong type.",
            "KeyError": "Tried to access a dictionary key that doesn't exist. Use .get() with a default value.",
            "IndexError": "List/tuple index out of range. Check the collection length before accessing.",
            "ValueError": "A function received an argument with the right type but wrong value.",
            "ImportError": "Failed to import a module. Check the module name, installation, and Python path.",
            "FileNotFoundError": "Tried to open a file that doesn't exist. Check the path and working directory.",
            "ConnectionError": "Failed to connect to a remote service. Check the URL, port, and network.",
            "TimeoutError": "An operation timed out. Increase the timeout or check the remote service.",
            "ZeroDivisionError": "Division or modulo by zero. Add a guard check before the operation.",
            "RuntimeError": "A generic runtime error. Check the error message for specifics.",
            "AssertionError": "An assert statement failed. Check the condition being asserted.",
            "NotImplementedError": "A method is not yet implemented. Check the abstract base class.",
            "StopIteration": "An iterator was exhausted. Use next() with a default or check for empty.",
            "PermissionError": "Insufficient permissions to access a file or resource.",
            "OSError": "An OS-level error occurred (file, network, process).",
        }

        # Base explanation from error type
        base = explanations.get(result.error_type, f"A {result.error_type} occurred.")
        result.explanation = f"{base}"
        if result.error_message:
            result.explanation += f" Message: {result.error_message}"

        # Suggest fix based on error type
        fixes = {
            "TypeError": "Check argument types. Add type validation or use isinstance() guards.",
            "AttributeError": "Add a None check before accessing the attribute, or verify the object type.",
            "KeyError": "Use dict.get(key, default) instead of dict[key], or check 'key in dict' first.",
            "IndexError": "Check 'if len(collection) > index' before accessing, or use try/except.",
            "ImportError": "Run 'pip install <module>' or check the module path in sys.path.",
            "FileNotFoundError": "Verify the file path exists. Use pathlib.Path.exists() before opening.",
            "ConnectionError": "Add retry logic with exponential backoff. Check service health.",
            "TimeoutError": "Increase timeout value or add circuit breaker pattern.",
            "ZeroDivisionError": "Add 'if divisor != 0' check before the division.",
        }
        result.suggested_fix = fixes.get(result.error_type, "Review the error message and the failing code line.")


def format_stack_decode(result: StackDecodeResult) -> str:
    """Format decoded stack trace for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Stack Trace Decoder [{result.language}]")
    lines.append(f"{'=' * 60}")

    if result.error_type:
        lines.append(f"\n  Error: {result.error_type}: {result.error_message}")

    lines.append(f"\n  Frames ({len(result.frames)}):")
    for i, frame in enumerate(result.frames):
        local = " [LOCAL]" if frame.is_local else ""
        root = " << ROOT CAUSE" if frame is result.root_cause_frame else ""
        lines.append(f"    {i+1}. {frame.file}:{frame.line} in {frame.function}{local}{root}")
        if frame.code:
            lines.append(f"       > {frame.code}")

    if result.explanation:
        lines.append(f"\n  Explanation: {result.explanation}")
    if result.suggested_fix:
        lines.append(f"  Suggested Fix: {result.suggested_fix}")
    if result.related_files:
        lines.append(f"  Related Files: {', '.join(result.related_files[:5])}")

    lines.append("")
    return "\n".join(lines)
