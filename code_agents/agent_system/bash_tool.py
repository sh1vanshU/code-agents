"""Bash tool execution — Claude Code style command runner with safety checks.

Provides a BashTool class that:
- Validates commands against a blocklist of dangerous patterns
- Auto-approves read-only commands
- Shows Claude Code style output with box-drawn borders
- Tracks execution time and exit codes
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.bash_tool")


@dataclass
class BashResult:
    """Result of a bash command execution."""
    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def output(self) -> str:
        """Combined stdout + stderr for display."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts)


# Commands that must NEVER be executed
BLOCKED_COMMANDS = [
    r"rm\s+-rf\s+/\s*$",     # rm -rf /
    r"rm\s+-rf\s+/\*",       # rm -rf /*
    r"rm\s+-rf\s+~",         # rm -rf ~
    r"mkfs\b",               # format disk
    r"dd\s+if=",             # disk write
    r":\(\)\{\s*:\|",        # fork bomb
    r"chmod\s+-R\s+777\s+/", # open everything
    r"chown\s+-R\s+.*\s+/$", # chown root
    r">(\/dev\/sda|\/dev\/hda|\/dev\/nvme)", # write to disk device
    r"curl.*\|\s*bash",      # pipe to bash (download + execute)
    r"wget.*\|\s*bash",      # pipe to bash (download + execute)
    r"shutdown\b",           # system shutdown
    r"reboot\b",             # system reboot
    r"init\s+0",             # halt system
    r"halt\b",               # halt system
    r"poweroff\b",           # power off
]

# Commands that are safe to auto-approve (read-only)
READ_ONLY_PREFIXES = [
    "cat ", "head ", "tail ", "less ", "more ",
    "ls", "ll ", "dir ",
    "find ", "locate ",
    "grep ", "rg ", "ag ", "ack ",
    "wc ", "file ", "stat ",
    "pwd", "whoami", "hostname", "uname",
    "echo ", "printf ",
    "git log", "git diff", "git show", "git status",
    "git branch", "git tag", "git remote",
    "git rev-parse", "git describe",
    "git blame", "git shortlog",
    "tree ",
    "which ", "type ", "command -v",
    "env", "printenv",
    "date", "cal",
    "df ", "du ",
    "ps ", "top -l 1",
    "curl -s", "curl --silent", "curl -I", "curl --head",
    "python --version", "python3 --version",
    "java -version", "javac -version",
    "node --version", "npm --version",
    "go version", "rustc --version", "cargo --version",
    "mvn --version", "gradle --version",
    "docker ps", "docker images", "docker version",
    "kubectl get", "kubectl describe", "kubectl logs",
]

_BLOCKED_RES = [re.compile(p) for p in BLOCKED_COMMANDS]


class BashTool:
    """Safe bash command executor with Claude Code style output."""

    def __init__(self, cwd: Optional[str] = None, default_timeout: int = 120):
        self.cwd = cwd or os.getcwd()
        self.default_timeout = default_timeout

    def is_blocked(self, command: str) -> bool:
        """Check if a command matches any blocked pattern."""
        for pattern in _BLOCKED_RES:
            if pattern.search(command):
                return True
        return False

    def is_read_only(self, command: str) -> bool:
        """Check if a command is read-only (safe to auto-approve)."""
        stripped = command.strip()
        # Handle leading env vars: VAR=val cmd ...
        clean = re.sub(r'^(\w+=\S+\s+)+', '', stripped)
        for prefix in READ_ONLY_PREFIXES:
            if clean.startswith(prefix) or clean == prefix.strip():
                return True
        return False

    def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
    ) -> BashResult:
        """Execute a bash command with safety checks.

        Returns BashResult with stdout, stderr, exit_code, duration_ms.
        """
        if self.is_blocked(command):
            return BashResult(
                command=command,
                stdout="",
                stderr="",
                exit_code=-1,
                duration_ms=0,
                error="BLOCKED: Command matches safety blocklist",
            )

        work_dir = cwd or self.cwd
        effective_timeout = timeout or self.default_timeout

        # Sandbox wrapping — restrict filesystem writes to cwd + /tmp
        from code_agents.devops.sandbox import is_sandbox_enabled, wrap_command as _sandbox_wrap
        effective_command = command
        if is_sandbox_enabled():
            effective_command = _sandbox_wrap(command, work_dir)

        start = time.monotonic()
        try:
            result = subprocess.run(
                effective_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=work_dir,
                env={**os.environ, "TERM": "dumb"},
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)

            return BashResult(
                command=command,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=elapsed_ms,
            )

        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return BashResult(
                command=command,
                stdout="",
                stderr="",
                exit_code=-1,
                duration_ms=elapsed_ms,
                error=f"Timeout after {effective_timeout}s",
            )
        except OSError as e:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return BashResult(
                command=command,
                stdout="",
                stderr="",
                exit_code=-1,
                duration_ms=elapsed_ms,
                error=str(e),
            )


def _display_command(cmd: str) -> str:
    """Return a display-friendly version of a command.

    Replaces temp-script invocations like
      bash /tmp/code-agents-xxx.sh && rm -f /tmp/code-agents-xxx.sh
    with the actual script content (if the file still exists) or a clean label.
    """
    import re
    m = re.match(r'^bash\s+(/\S*code-agents-\S+\.sh)\s*&&\s*rm\s+-f\s+\1$', cmd)
    if m:
        path = m.group(1)
        try:
            with open(path) as f:
                script = f.read().strip()
            return script
        except OSError:
            return "(script)"
    return cmd


def format_command_output(result: BashResult, use_color: bool = True) -> str:
    """Format command execution result in Claude Code style.

    Bash(git log --oneline -5)
      ⎿  a1b2c3d feat: add explore agent
         d4e5f6g fix: toolbar white background
      ✓ exit 0 (23ms)
    """
    def _c(code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if use_color else text

    lines = []

    # Header — Bash(command) with word wrap
    import shutil, textwrap
    term_width = shutil.get_terminal_size((80, 24)).columns
    cmd_full = _display_command(result.command)
    prefix_len = len("  Bash(")
    suffix_len = len(")")
    wrap_width = max(40, term_width - prefix_len - suffix_len)
    cmd_wrapped = textwrap.wrap(cmd_full, width=wrap_width)
    if len(cmd_wrapped) <= 1:
        lines.append(f"  {_c('1', f'Bash({cmd_full})')}")
    else:
        indent = " " * prefix_len
        lines.append(f"  {_c('1', f'Bash({cmd_wrapped[0]}')}")
        for wl in cmd_wrapped[1:-1]:
            lines.append(f"{indent}{_c('1', wl)}")
        lines.append(f"{indent}{_c('1', f'{cmd_wrapped[-1]})')}")

    # Body — output lines with ⎿ prefix
    output = result.output.rstrip()
    if result.error:
        output = result.error

    if output:
        # Pretty-print JSON output for readability
        display_output = output
        try:
            import json
            parsed = json.loads(output)
            display_output = json.dumps(parsed, indent=2)
        except (json.JSONDecodeError, ValueError):
            # Multiple JSON objects (e.g. chained curl commands) — try line-by-line
            import json as _json
            formatted_lines = []
            any_formatted = False
            for raw_line in output.splitlines():
                stripped = raw_line.strip()
                if stripped.startswith(("{", "[")):
                    try:
                        parsed = _json.loads(stripped)
                        formatted_lines.append(_json.dumps(parsed, indent=2))
                        any_formatted = True
                        continue
                    except (_json.JSONDecodeError, ValueError):
                        pass
                formatted_lines.append(raw_line)
            if any_formatted:
                display_output = "\n".join(formatted_lines)
        out_lines = display_output.splitlines()
        for i, line in enumerate(out_lines):
            if i == 0:
                lines.append(f"  {_c('2', '⎿')}  {line}")
            else:
                lines.append(f"     {line}")
    else:
        lines.append(f"  {_c('2', '⎿')}  {_c('2', '(no output)')}")

    # Status line
    duration = f"({result.duration_ms}ms)" if result.duration_ms < 1000 else f"({result.duration_ms / 1000:.1f}s)"
    if result.success:
        lines.append(f"  {_c('32', f'✓ exit {result.exit_code}')} {_c('2', duration)}")
    elif result.error:
        lines.append(f"  {_c('31', f'✗ {result.error}')} {_c('2', duration)}")
    else:
        lines.append(f"  {_c('31', f'✗ exit {result.exit_code}')} {_c('2', duration)}")

    return "\n".join(lines)


def print_command_output(result: BashResult, auto_run: bool = False) -> None:
    """Print formatted command output to stdout.

    For outputs longer than 10 lines, shows a collapsed view with the
    first 5 and last 5 lines. Press Ctrl+O to expand/collapse, any other
    key to continue. Skips interactive toggle for auto_run commands.
    """
    import sys
    use_color = sys.stdout.isatty()
    full_formatted = format_command_output(result, use_color=use_color)

    output = result.output.rstrip()
    if result.error:
        output = result.error
    output_lines = output.splitlines() if output else []

    # Short output — just print
    if len(output_lines) <= 10:
        print(full_formatted)
        return

    # Long output — collapse/expand
    def _c(code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if use_color else text

    import shutil, textwrap
    term_width = shutil.get_terminal_size((80, 24)).columns
    cmd_full = _display_command(result.command)
    prefix_len = len("  Bash(")
    suffix_len = len(")")
    wrap_width = max(40, term_width - prefix_len - suffix_len)
    cmd_wrapped = textwrap.wrap(cmd_full, width=wrap_width)
    if len(cmd_wrapped) <= 1:
        header_line = f"  {_c('1', f'Bash({cmd_full})')}"
    else:
        # First line with "Bash(" prefix, continuation lines indented
        indent = " " * prefix_len
        lines = [f"  {_c('1', f'Bash({cmd_wrapped[0]}')}"]
        for wl in cmd_wrapped[1:-1]:
            lines.append(f"{indent}{_c('1', wl)}")
        lines.append(f"{indent}{_c('1', f'{cmd_wrapped[-1]})')}")
        header_line = "\n".join(lines)

    if result.success:
        status = _c('32', f"✓ exit {result.exit_code}")
    elif result.error:
        status = _c('31', f"✗ {result.error}")
    else:
        status = _c('31', f"✗ exit {result.exit_code}")
    duration = f"({result.duration_ms}ms)" if result.duration_ms < 1000 else f"({result.duration_ms / 1000:.1f}s)"
    status_line = f"  {status} {_c('2', duration)}"

    # Track line counts for clearing on toggle
    hidden = len(output_lines) - 10
    header_lines_count = header_line.count('\n') + 1
    _collapsed_lines = header_lines_count + 5 + 1 + 5 + 1 + 1  # header + head(5) + hidden(1) + tail(5) + status(1) + hint(1)

    def _count_expanded_lines():
        """Count lines in full formatted output (includes header) + hint line."""
        return full_formatted.count('\n') + 1 + 1  # output (with header) + hint

    def _clear_lines(n: int):
        """Move cursor up n lines and clear each one."""
        for _ in range(n):
            sys.stdout.write('\033[A\033[2K')
        sys.stdout.flush()

    def _print_collapsed():
        print(header_line)
        for i, line in enumerate(output_lines[:5]):
            prefix = f"  {_c('2', '⎿')}  " if i == 0 else "     "
            print(f"{prefix}{line}")
        print(f"     {_c('2', f'··· {hidden} lines hidden ···')}")
        for line in output_lines[-5:]:
            print(f"     {line}")
        print(status_line)

    def _print_expanded():
        print(full_formatted)

    _print_collapsed()
    if auto_run:
        # Auto-run: don't block waiting for keypress
        return
    print(f"  {_c('2', f'({len(output_lines)} lines) Ctrl+O=expand · Enter=continue')}")

    # Single-keypress toggle
    if not sys.stdout.isatty():
        return
    try:
        import tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            is_collapsed = True
            prev_line_count = _collapsed_lines
            while True:
                ch = os.read(fd, 1)
                if not ch:
                    break
                b = ch[0]
                if b == 0x0f:  # Ctrl+O
                    _clear_lines(prev_line_count)
                    is_collapsed = not is_collapsed
                    if is_collapsed:
                        _print_collapsed()
                        print(f"  {_c('2', f'({len(output_lines)} lines) Ctrl+O=expand · Enter=continue')}")
                        prev_line_count = _collapsed_lines
                    else:
                        _print_expanded()
                        print(f"  {_c('2', f'({len(output_lines)} lines) Ctrl+O=collapse · Enter=continue')}")
                        prev_line_count = _count_expanded_lines()
                else:
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old_settings)
    except (ImportError, OSError, ValueError, EOFError):
        pass
