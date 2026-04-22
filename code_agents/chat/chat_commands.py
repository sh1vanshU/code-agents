"""Chat command execution — extract, resolve placeholders, run, and offer commands."""

from __future__ import annotations

import fcntl
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_commands")

from .chat_ui import (
    bold, green, yellow, red, cyan, dim,
    _visible_len, _tab_selector, _amend_prompt,
)

# ---------------------------------------------------------------------------
# Command extraction from agent responses
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(
    r"```(?:bash|sh|shell|zsh|console)\s*\n(.*?)```",
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Secret masking — hide auth tokens in command display while executing with real values
# ---------------------------------------------------------------------------

# Patterns that indicate sensitive values in commands
_SECRET_PATTERNS = [
    # Authorization headers: -H "Authorization: Basic xxx" or -H "Authorization: Bearer xxx"
    (re.compile(r'(-H\s+["\']Authorization:\s*(?:Basic|Bearer)\s+)([^"\']+)(["\'])'), r'\1●●●●●●\3'),
    # Token headers: -H "X-Api-Key: xxx" or -H "Private-Token: xxx"
    (re.compile(r'(-H\s+["\'](?:X-Api-Key|Private-Token|X-Auth-Token|JENKINS-CRUMB):\s*)([^"\']+)(["\'])'), r'\1●●●●●●\3'),
    # --user user:password
    (re.compile(r'(--user\s+\S+?:)(\S+)'), r'\1●●●●●●'),
    # -u user:password
    (re.compile(r'(-u\s+\S+?:)(\S+)'), r'\1●●●●●●'),
    # Inline passwords in URLs: https://user:password@host
    (re.compile(r'(https?://[^:]+:)([^@]+)(@)'), r'\1●●●●●●\3'),
    # Environment variable values that look like tokens (already expanded)
    # e.g., -H "Authorization: Basic c2hpdmFuc2h1OjEyMzQ1" (base64-ish)
    (re.compile(r'(-H\s+["\'][^"\']*:\s*)([A-Za-z0-9+/=]{20,})(["\'])'), r'\1●●●●●●\3'),
]


def mask_secrets(cmd: str) -> str:
    """Mask auth tokens and secrets in a command for safe terminal display.

    The actual command is executed with real values — only the display is masked.
    Env var references like $JENKINS_TOKEN are NOT masked (they're already safe).
    """
    masked = cmd
    for pattern, replacement in _SECRET_PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked

# Matches [SKILL:name] or [SKILL:agent:name] tags for on-demand skill loading
_SKILL_TAG_RE = re.compile(r"\[SKILL:([a-z0-9_:-]+)\]")

# Matches [DELEGATE:agent-name] prompt for agent chaining.
# Must appear at start of line (not inside table rows or plan descriptions).
# Captures the agent name and the rest of that single line as the prompt.
_DELEGATE_TAG_RE = re.compile(r"^\[DELEGATE:([a-z0-9_-]+)\]\s*(.+)$", re.MULTILINE)


# Common English sentence starters that are NOT commands
_ENGLISH_STARTERS = {
    "i", "you", "we", "he", "she", "they", "it",
    "please", "can", "could", "would", "should", "will",
    "the", "this", "that", "these", "those",
    "let", "need", "want", "have", "has",
    "here", "there", "what", "how", "why", "when", "where", "who",
    "note", "remember", "also", "now", "next", "then", "first",
    "analysis", "summary", "step", "plan", "approach",
    "yes", "no", "ok", "sure", "great", "thanks",
}


def _is_valid_command(cmd: str) -> bool:
    """Check if a string looks like a real shell command, not English text.

    Returns False for obvious natural language accidentally in ```bash blocks.
    """
    if not cmd or not cmd.strip():
        return False

    stripped = cmd.strip()
    first_word = stripped.split()[0].lower().rstrip(".,!?:;")

    # If first word is a common English starter, probably not a command
    if first_word in _ENGLISH_STARTERS:
        return False

    # If the line has no shell metacharacters and is mostly words, probably English
    shell_chars = set('|&><;$`\\(){}[]!#*?~')
    has_shell_chars = any(c in shell_chars for c in stripped)
    has_flags = any(w.startswith('-') for w in stripped.split())
    has_path = '/' in stripped or '.' in stripped.split()[0]

    # If no shell chars, no flags, no paths, and > 5 words → likely English
    word_count = len(stripped.split())
    if word_count > 5 and not has_shell_chars and not has_flags and not has_path:
        return False

    # Known safe command prefixes
    safe_prefixes = (
        "curl", "git", "docker", "npm", "yarn", "mvn", "gradle",
        "python", "pip", "java", "go", "cargo", "make", "cmake",
        "kubectl", "helm", "terraform", "aws", "gcloud", "az",
        "cat", "ls", "cd", "cp", "mv", "rm", "mkdir", "touch",
        "grep", "find", "sed", "awk", "sort", "head", "tail",
        "echo", "export", "source", "chmod", "chown", "ssh", "scp",
        "wget", "tar", "unzip", "zip", "diff", "patch",
    )
    if first_word in safe_prefixes:
        return True

    return True  # Default: allow (don't over-block)


def _is_continuation_line(line: str, prev_line: str) -> bool:
    """Detect if a line is a continuation of the previous command, not a new command.

    A line is a continuation if:
    - It starts with a flag (- or --) — e.g. continuation of curl/docker args
    - It starts with a pipe (|) or logical operator (&& ||)
    - It is indented (leading whitespace) — common for wrapped command args
    - The previous line ends with an operator (| && || ; >) suggesting continuation
    """
    stripped = line.strip()
    raw_indent = len(line) - len(line.lstrip())

    # Lines starting with flags are continuations (e.g. -H, --name)
    if stripped.startswith("-"):
        return True

    # Lines starting with pipes, logical operators, or redirects
    if stripped.startswith(("|", "&&", "||", ">>", "> ")):
        return True

    # Previous line ends with operator suggesting continuation
    prev_stripped = prev_line.rstrip()
    if prev_stripped.endswith(("|", "&&", "||", "\\", ",", ">")):
        return True

    # Indented lines (2+ spaces or tab) are continuations of the previous command
    if raw_indent >= 2 and prev_line.strip():
        return True

    return False


def _extract_commands(text: str) -> list[str]:
    """Extract shell commands from markdown code blocks in agent response.

    Handles:
    - Backslash continuations (cmd \\ \\n  --flag)
    - Indented continuation lines (cmd \\n  --flag --value)
    - Multi-line scripts (if/then/fi, for/do/done) as temp file execution
    - Multiple independent commands separated by blank lines or comment lines
    """
    commands = []
    for match in _CODE_BLOCK_RE.finditer(text):
        block = match.group(1).strip()

        # Multi-line bash blocks: detect scripts that MUST run as one unit
        _block_lines = [l for l in block.splitlines() if l.strip() and not l.strip().startswith("#")]
        # Script control-flow keywords — match as whole first word to avoid
        # false positives ("docker" must not match "do", "download" ≠ "done")
        _script_keywords = {"if", "then", "else", "elif", "fi", "for", "while",
                            "do", "done", "case", "esac", "function"}
        _script_prefixes = ("set -", "export ")  # these use prefix matching
        def _is_script_line(line: str) -> bool:
            first = line.strip().split()[0] if line.strip() else ""
            return first in _script_keywords or any(line.strip().startswith(p) for p in _script_prefixes)
        _has_control = any(_is_script_line(l) for l in _block_lines)
        _has_vars = any(
            "=" in l and not l.strip().startswith(("curl", "echo", "git", "mvn", "npm", "cd "))
            for l in _block_lines[:3]
        )
        if _has_control or _has_vars:
            # Run entire block as single script via temp file (avoids arg length limits)
            import tempfile
            _tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False, prefix="code-agents-")
            script = "\n".join(l for l in block.splitlines() if l.strip())
            _tmp.write(script)
            _tmp.close()
            commands.append(f'bash {_tmp.name} && rm -f {_tmp.name}')
            continue

        lines = block.splitlines()
        joined_lines: list[str] = []
        current = ""
        prev_raw = ""  # raw (unstripped) previous line for indent detection
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                # Blank line or comment → finalize current command
                if current:
                    joined_lines.append(current)
                    current = ""
                    prev_raw = ""
                continue

            # Strip prompt prefixes
            if stripped.startswith("$ "):
                stripped = stripped[2:]
            elif stripped.startswith("> "):
                stripped = stripped[2:]

            if current:
                # Check if this is a continuation of the previous command
                if current.endswith("\\"):
                    # Explicit backslash continuation — always join
                    current = current[:-1].rstrip() + " " + stripped
                elif _is_continuation_line(line, prev_raw):
                    # Detected continuation (indented, starts with flag, etc.)
                    current += " " + stripped
                else:
                    # New independent command
                    joined_lines.append(current)
                    current = stripped
            else:
                current = stripped

            prev_raw = line

        if current:
            joined_lines.append(current)

        for cmd in joined_lines:
            if cmd:
                commands.append(cmd)
    # Filter out English text that was accidentally in bash blocks
    return [cmd for cmd in commands if _is_valid_command(cmd)]


def _extract_skill_requests(text: str) -> list[str]:
    """Extract [SKILL:name] tags from agent response.

    Returns list of skill names the agent wants loaded.
    """
    return _SKILL_TAG_RE.findall(text)


def _extract_delegations(text: str) -> list[tuple[str, str]]:
    """Extract [DELEGATE:agent] prompt pairs from response."""
    return _DELEGATE_TAG_RE.findall(text)


# ---------------------------------------------------------------------------
# Placeholder resolution
# ---------------------------------------------------------------------------

_PLACEHOLDER_ANGLE_RE = re.compile(r"<([A-Z][A-Z0-9_]+)>")
_PLACEHOLDER_CURLY_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")

# Context from previous command outputs — auto-fills known placeholders
_command_context: dict[str, str] = {}


def _extract_context_from_output(output: str) -> None:
    """Extract known values from command output for auto-filling future placeholders."""
    try:
        import json as _j
        data = _j.loads(output.strip())
        if isinstance(data, dict):
            # Build version from build-and-wait response
            if data.get("build_version"):
                _command_context["BUILD_VERSION"] = str(data["build_version"])
                _command_context["build_version"] = str(data["build_version"])
                _command_context["image_tag"] = str(data["build_version"])
            # Build number
            if data.get("number"):
                _command_context["BUILD_NUMBER"] = str(data["number"])
                _command_context["build_number"] = str(data["number"])
            # Job name
            if data.get("job_name"):
                _command_context["job_name"] = str(data["job_name"])
    except (ValueError, TypeError) as e:
        logger.debug("Failed to parse command context: %s", e)


def _resolve_placeholders(cmd: str) -> Optional[str]:
    """Detect placeholder tokens, auto-fill from context, prompt for unknown."""
    found: list[tuple[str, str]] = []
    for m in _PLACEHOLDER_ANGLE_RE.finditer(cmd):
        found.append((m.group(0), m.group(1)))
    for m in _PLACEHOLDER_CURLY_RE.finditer(cmd):
        found.append((m.group(0), m.group(1)))

    if not found:
        return cmd

    seen = set()
    unique: list[tuple[str, str]] = []
    for token, name in found:
        if token not in seen:
            seen.add(token)
            unique.append((token, name))

    replacements = {}
    needs_input = []

    # Auto-fill from context first
    for token, name in unique:
        if name in _command_context:
            replacements[token] = _command_context[name]
            print(f"    {green('✓')} {bold(token)} = {cyan(_command_context[name])} {dim('(from previous build)')}")
        else:
            needs_input.append((token, name))

    # Prompt for remaining unknowns
    if needs_input:
        print(f"    {yellow('Placeholders — fill in values:')}")
        for token, name in needs_input:
            try:
                value = input(f"    {bold(token)}: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return None
            if not value:
                print(dim(f"    Skipped (no value for {token})."))
                return None
            replacements[token] = value

    for token, value in replacements.items():
        cmd = cmd.replace(token, value)

    return cmd


# ---------------------------------------------------------------------------
# Command trust (saved in rules)
# ---------------------------------------------------------------------------

def _save_command_to_rules(cmd: str, agent_name: str, repo_path: str) -> None:
    """Save an executed command to the agent's project rules file (file-locked)."""
    from code_agents.agent_system.rules_loader import PROJECT_RULES_DIRNAME
    rules_dir = Path(repo_path) / PROJECT_RULES_DIRNAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / f"{agent_name}.md"

    try:
        with open(str(rules_file), "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                existing = f.read()
                if cmd in existing:
                    print(dim("  (command already in rules)"))
                    return
                if "## Saved Commands" not in existing:
                    f.write("\n\n## Saved Commands\nThese commands have been approved and can be auto-run.\n")
                f.write(f"\n```bash\n{cmd}\n```\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        print(green(f"  ✓ Saved to {rules_file}"))
    except OSError as e:
        print(yellow(f"  ! Could not save to rules: {e}"))


def _is_command_trusted(cmd: str, agent_name: str, repo_path: str) -> bool:
    """Check if a command is in the agent's saved/trusted commands (file-locked)."""
    from code_agents.agent_system.rules_loader import PROJECT_RULES_DIRNAME
    rules_file = Path(repo_path) / PROJECT_RULES_DIRNAME / f"{agent_name}.md"
    if not rules_file.is_file():
        return False
    try:
        with open(str(rules_file), "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                content = f.read()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return cmd in content
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Run a single command
# ---------------------------------------------------------------------------

def _run_single_command(cmd: str, cwd: str, auto_run: bool = False) -> str:
    """Run a single shell command, display output, and return raw output."""
    from code_agents.agent_system.bash_tool import BashTool, print_command_output

    _CHAT_CMD_TIMEOUT = 600

    logger.info("Executing command in %s", cwd)
    logger.debug("Command: %s", cmd[:200])

    tool = BashTool(cwd=cwd, default_timeout=_CHAT_CMD_TIMEOUT)

    if tool.is_blocked(cmd):
        print(red(f"  ✗ BLOCKED: {cmd}"))
        print(dim("    This command matches a safety blocklist pattern."))
        return "BLOCKED"

    # Streaming path for build-and-wait — show live polling progress
    if "build-and-wait" in cmd:
        return _run_streaming_build(cmd, cwd, _CHAT_CMD_TIMEOUT)

    # Show spinning dot while command runs
    import threading
    import time as _time

    _cmd_display = mask_secrets(cmd) if len(cmd) <= 80 else mask_secrets(cmd[:77]) + "..."
    _stop_spin = threading.Event()
    _spin_start = _time.monotonic()

    def _spin():
        colors = ["\033[1;36m", "\033[1;34m", "\033[1;35m", "\033[1;32m"]  # cyan, blue, magenta, green
        i = 0
        while not _stop_spin.is_set():
            elapsed = _time.monotonic() - _spin_start
            e_str = f"{elapsed:.0f}s" if elapsed < 60 else f"{int(elapsed)//60}m {int(elapsed)%60:02d}s"
            dot = f"{colors[i % len(colors)]}⏺\033[0m"
            sys.stdout.write(f"\r  {dot} \033[2mRunning({_cmd_display}) {e_str}\033[0m  ")
            sys.stdout.flush()
            i += 1
            _stop_spin.wait(0.5)
        sys.stdout.write(f"\r{' ' * 120}\r")
        sys.stdout.flush()

    spin_t = threading.Thread(target=_spin, daemon=True)
    spin_t.start()

    result = tool.execute(cmd, timeout=_CHAT_CMD_TIMEOUT)

    _stop_spin.set()
    spin_t.join(timeout=1)

    print_command_output(result, auto_run=auto_run)

    out = result.output.rstrip()
    if result.error:
        if out:
            out = f"{out}\n{result.error}"
        else:
            out = result.error
    if not result.success and result.exit_code > 0:
        suffix = f"[exit code: {result.exit_code}]"
        out = f"{out}\n{suffix}" if out else suffix
    return out


def _run_streaming_build(cmd: str, cwd: str, timeout: int) -> str:
    """Run build-and-wait with live progress display.

    The endpoint streams NDJSON lines:
      {"status":"triggered","build_number":909,...}
      {"status":"polling","build_number":909,"poll":1,"elapsed":"5s"}
      {"status":"done","build_number":909,"result":"SUCCESS","build_version":"..."}

    We parse each line and show a live progress indicator.
    """
    import json
    import subprocess
    import time

    start = time.monotonic()
    final_output = ""

    try:
        # Force curl to flush output immediately (--no-buffer / -N)
        _streaming_cmd = cmd
        if "curl " in _streaming_cmd and " -N" not in _streaming_cmd and "--no-buffer" not in _streaming_cmd:
            _streaming_cmd = _streaming_cmd.replace("curl ", "curl -N ", 1)

        # Auto-quote unquoted URLs with ? or & (shell glob/backgrounding issues)
        if "curl " in _streaming_cmd:
            _streaming_cmd = re.sub(
                r"""(?<!['"]) (https?://\S*[?&]\S*)""",
                r" '\1'",
                _streaming_cmd,
            )

        proc = subprocess.Popen(
            _streaming_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=cwd, bufsize=1,  # line-buffered
            env={**__import__("os").environ, "TERM": "dumb"},
        )

        lines = []
        # Use readline() instead of iterator — iterator buffers internally
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            line = line.strip()
            if not line:
                continue
            lines.append(line)

            # Try to parse as JSON progress
            try:
                data = json.loads(line)
                status = data.get("status", "")

                if status == "triggered":
                    build_num = data.get("build_number", "?")
                    job = data.get("job_name", "")
                    _short_job = job.rsplit("/", 1)[-1] if "/" in job else job
                    print(f"  {dim('⟳')} Build #{build_num} triggered ({_short_job})")
                    import sys; sys.stdout.flush()

                elif status == "polling":
                    build_num = data.get("build_number", "?")
                    elapsed = data.get("elapsed", "?")
                    poll = data.get("poll", 0)
                    # Overwrite same line for clean progress
                    print(f"\r  {dim('⟳')} Build #{build_num} building... {dim(elapsed)} (poll {poll})", end="", flush=True)

                elif status == "done":
                    print()  # newline after polling progress
                    build_num = data.get("build_number", "?")
                    result_str = data.get("result", "UNKNOWN")
                    version = data.get("build_version", "")
                    duration = data.get("duration_display", "")
                    _icon = "✓" if result_str == "SUCCESS" else "✗"
                    _color = green if result_str == "SUCCESS" else red
                    print(f"  {_color(f'{_icon} Build #{build_num} {result_str}')} {dim(duration)}")
                    if version:
                        print(f"  {dim('Image tag:')} {bold(version)}")
                    # Final output is the full JSON for agent to parse
                    final_output = line

                elif status == "error":
                    print()
                    err = data.get("error", "Unknown error")
                    print(f"  {red('✗')} {err}")
                    final_output = line

            except json.JSONDecodeError:
                # Not JSON — raw output, just accumulate
                final_output = line

        proc.wait(timeout=timeout)
        stderr = proc.stderr.read()

        elapsed_ms = int((time.monotonic() - start) * 1000)
        _exit_icon = "✓" if proc.returncode == 0 else "✗"
        _exit_color = green if proc.returncode == 0 else red
        print(f"  {_exit_color(_exit_icon)} exit {proc.returncode} ({elapsed_ms / 1000:.1f}s)")

        if not final_output:
            final_output = "\n".join(lines)
        if stderr:
            final_output = f"{final_output}\n{stderr}" if final_output else stderr
        if proc.returncode != 0:
            final_output = f"{final_output}\n[exit code: {proc.returncode}]"

        return final_output

    except subprocess.TimeoutExpired:
        proc.kill()
        return f"Timeout after {timeout}s"
    except Exception as e:
        return f"Error: {e}"

# ---------------------------------------------------------------------------
# Per-agent command allowlist/blocklist
# ---------------------------------------------------------------------------

_global_autorun_cache: dict | None = None


def _load_global_autorun_config() -> dict:
    """Load global autorun config from agents/_shared/autorun.yaml.

    Cached after first load — applies to all agents.
    """
    global _global_autorun_cache
    if _global_autorun_cache is not None:
        return _global_autorun_cache

    from code_agents.core.config import settings
    config_path = Path(settings.agents_dir) / "_shared" / "autorun.yaml"
    if not config_path.is_file():
        _global_autorun_cache = {}
        return _global_autorun_cache

    try:
        import yaml
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        _global_autorun_cache = {
            "allow": [str(p).lower() for p in (data.get("allow") or [])],
            "block": [str(p).lower() for p in (data.get("block") or [])],
        }
    except Exception:
        _global_autorun_cache = {}
    return _global_autorun_cache


def _load_agent_autorun_config(agent_name: str) -> dict:
    """
    Load merged autorun config: global (_shared) + per-agent.

    Reads from:
      1. agents/_shared/autorun.yaml   — global safe commands for ALL agents
      2. agents/<agent>/autorun.yaml   — per-agent overrides

    Merged: global allow + agent allow, global block + agent block.
    Block always takes priority over allow.
    """
    global_config = _load_global_autorun_config()

    if not agent_name:
        return global_config

    from code_agents.core.config import settings
    folder_name = agent_name.replace("-", "_")
    config_path = Path(settings.agents_dir) / folder_name / "autorun.yaml"

    agent_config: dict = {}
    if config_path.is_file():
        try:
            import yaml
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            agent_config = {
                "allow": [str(p).lower() for p in (data.get("allow") or [])],
                "block": [str(p).lower() for p in (data.get("block") or [])],
            }
        except Exception:
            pass

    # Merge: global + agent (deduplicate)
    merged_allow = list(dict.fromkeys(global_config.get("allow", []) + agent_config.get("allow", [])))
    merged_block = list(dict.fromkeys(global_config.get("block", []) + agent_config.get("block", [])))
    return {"allow": merged_allow, "block": merged_block}


def _resolve_temp_script_content(cmd: str) -> str:
    """If cmd is a temp-script invocation (bash /tmp/code-agents-xxx.sh && rm ...),
    read the script file and return its content for autorun matching.
    Returns original cmd if not a temp-script."""
    import re
    m = re.match(r'^bash\s+(/\S*code-agents-\S+\.sh)\s*&&\s*rm\s+-f\s+\1$', cmd)
    if m:
        path = m.group(1)
        try:
            with open(path) as f:
                return f.read()
        except Exception:
            pass
    return cmd


def _check_agent_autorun(cmd: str, agent_name: str) -> str | None:
    """
    Check per-agent allowlist/blocklist for a command.

    Returns:
      "allow" — command matches agent allowlist → auto-run
      "block" — command matches agent blocklist → always ask
      None    — no match, fall through to default safe check
    """
    config = _load_agent_autorun_config(agent_name)
    if not config:
        return None

    cmd_lower = cmd.strip().lower()

    # For temp-script commands, also check the script content against patterns
    script_content = _resolve_temp_script_content(cmd)
    check_targets = [cmd_lower]
    if script_content != cmd:
        # Check each line of the script independently
        for line in script_content.splitlines():
            stripped = line.strip().lower()
            if stripped and not stripped.startswith("#"):
                check_targets.append(stripped)

    # Find longest matching pattern across all targets
    best_allow = 0
    best_block = 0
    for target in check_targets:
        best_allow = max(best_allow, max((len(p) for p in config.get("allow", []) if p in target), default=0))
        best_block = max(best_block, max((len(p) for p in config.get("block", []) if p in target), default=0))

    if best_allow == 0 and best_block == 0:
        return None
    # More specific (longer) pattern wins; on tie, allow wins
    # Block takes priority if ANY line in the script matches a block pattern
    if best_block > 0 and best_block >= best_allow:
        return "block"
    if best_allow > 0:
        return "allow"
    return None


# ---------------------------------------------------------------------------
# Safe command detection
# ---------------------------------------------------------------------------

def _is_safe_command(cmd: str) -> bool:
    """
    Check if a command is read-only / safe to auto-run.

    Safe: GET curls (no -X POST, no -d, no --data), read-only git commands.
    Unsafe: POST/PUT/DELETE curls, rm, git push, anything destructive.
    """
    cmd_lower = cmd.strip().lower()

    # curl commands — safe if GET (no -X POST, no -d/--data body)
    if cmd_lower.startswith("curl"):
        unsafe_flags = ["-x post", "-x put", "-x delete", "-x patch", "--data", "-d ", "-d'", '-d"']
        for flag in unsafe_flags:
            if flag in cmd_lower:
                return False
        return True  # GET curl is safe

    # Read-only git commands
    safe_git = ["git status", "git log", "git diff", "git branch", "git show", "git remote -v"]
    for safe in safe_git:
        if cmd_lower.startswith(safe):
            return True

    # cat, ls, echo, jq — read-only
    safe_prefixes = ["cat ", "ls ", "echo ", "jq ", "head ", "tail ", "wc ", "grep "]
    for prefix in safe_prefixes:
        if cmd_lower.startswith(prefix):
            return True

    return False


# ---------------------------------------------------------------------------
# Block-to-delegate mapping: when a blocked command should delegate to another agent
# ---------------------------------------------------------------------------

# Maps (agent_name, url_pattern) → delegate_agent
# Empty: jenkins-cicd now handles basic ArgoCD verification directly.
_BLOCK_DELEGATE_RULES: list[tuple[str, str, str]] = []


def _get_block_delegate(cmd: str, agent_name: str) -> str | None:
    """Check if a blocked command has a known delegate agent.

    Returns the delegate agent name, or None if no delegation rule matches.
    """
    cmd_lower = cmd.lower()
    for rule_agent, pattern, delegate in _BLOCK_DELEGATE_RULES:
        if agent_name == rule_agent and pattern in cmd_lower:
            return delegate
    return None


# ---------------------------------------------------------------------------
# Curl-to-local rewriter: run git/file commands directly without server proxy
# ---------------------------------------------------------------------------

_CURL_LOCAL_REWRITES: list[tuple[str, str]] = [
    ("/git/current-branch", "git rev-parse --abbrev-ref HEAD"),
    ("/git/status", "git status"),
    ("/git/branches", "git branch -a"),
    ("/git/log", "git log --oneline -20"),
    ("/git/diff", "git diff"),
    ("/git/remote", "git remote -v"),
]


def _rewrite_curl_to_local(cmd: str) -> str | None:
    """Rewrite a curl to the local API server to a direct local command.

    Returns the direct command string, or None if no rewrite applies.
    Only rewrites safe, read-only git commands that don't need the server proxy.
    """
    cmd_stripped = cmd.strip()
    if not cmd_stripped.startswith("curl "):
        return None

    # Extract URL from curl command
    import re
    url_match = re.search(r"http://(?:127\.0\.0\.1|localhost):\d+(/\S+)", cmd_stripped)
    if not url_match:
        return None

    path = url_match.group(1).rstrip("'\"")
    # Strip query params for matching
    path_base = path.split("?")[0]

    for pattern, replacement in _CURL_LOCAL_REWRITES:
        if path_base == pattern:
            return replacement

    # /git/diff/{a}..{b} → git diff {a}..{b}
    if path_base.startswith("/git/diff/"):
        diff_args = path_base[len("/git/diff/"):]
        if diff_args:
            return f"git diff {diff_args}"

    return None


# ---------------------------------------------------------------------------
# Offer to run commands
# ---------------------------------------------------------------------------

def _log_auto_run(cmd: str, reason: str) -> None:
    """Log auto-executed commands for auditing."""
    from datetime import datetime
    log_path = Path.home() / ".code-agents" / "auto_run.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"{datetime.now().isoformat()} | {reason} | {cmd}\n")
    except OSError as e:
        logger.warning("Failed to write auto-run audit log: %s", e)


def _handle_edit(cmd: str) -> str | None:
    """Handle Edit option — prompt user for feedback to send to agent.

    Returns the feedback text, or None if cancelled.
    """
    try:
        print(f"  {dim('Tell the agent what to change (or press Enter to skip):')}")
        feedback = input(f"  {bold('>')} ").strip()
        if feedback:
            return feedback
    except (EOFError, KeyboardInterrupt):
        pass
    return None


def _offer_run_commands(
    commands: list[str], cwd: str,
    agent_name: str = "",
    auto_run: bool = False,
    superpower: bool = False,
) -> list[dict[str, str]]:
    """
    Offer to run detected shell commands one at a time.

    auto_run=True: auto-execute safe (read-only) commands without asking.
    superpower=True: auto-execute ALL commands (except blocklisted in autorun.yaml).
    """
    # Feature 1: global env toggle to disable auto-run
    if auto_run and os.getenv("CODE_AGENTS_AUTO_RUN", "true").strip().lower() in ("0", "false", "no"):
        auto_run = False  # user disabled auto-run globally

    dry_run = os.getenv("CODE_AGENTS_DRY_RUN", "").strip().lower() in ("1", "true", "yes")

    results: list[dict[str, str]] = []

    if not commands:
        return results

    for cmd in commands:
        # Rewrite curl to local API → direct command (git, file ops)
        _rewritten = _rewrite_curl_to_local(cmd)
        if _rewritten:
            print(f"  {green('● Direct')} {dim(f'({_rewritten})')}")
            cmd = _rewritten

        import shutil
        import textwrap
        term_width = shutil.get_terminal_size((80, 24)).columns
        box_width = term_width - 4
        inner = box_width - 2

        trusted = _is_command_trusted(cmd, agent_name, cwd) if agent_name else False
        safe = _is_safe_command(cmd)

        # Per-agent allowlist/blocklist override
        agent_autorun = _check_agent_autorun(cmd, agent_name) if agent_name else None
        if agent_autorun == "block":
            safe = False  # blocked commands never auto-run
            trusted = False
            # Hard enforcement: if blocked command should delegate, silently skip
            _block_delegate = _get_block_delegate(cmd, agent_name)
            if _block_delegate:
                print(f"  {yellow(f'⚠ Blocked')} {dim(f'— {agent_name} must delegate to {_block_delegate}')}")
                print()
                results.append({
                    "command": cmd,
                    "output": f"[BLOCKED] This command is not allowed for {agent_name}. "
                              f"You MUST use [DELEGATE:{_block_delegate}] instead. "
                              f"Do NOT call /argocd/ endpoints directly.",
                    "exit_code": "blocked",
                })
                continue
        elif agent_autorun == "allow":
            safe = True  # allowed commands auto-run even if not in default safe list
            auto_run = True  # force auto-run for agent-allowed commands

        # Show the command (resolve temp script paths, mask auth tokens)
        from code_agents.agent_system.bash_tool import _display_command
        cmd_display = mask_secrets(_display_command(cmd))
        print(red(f"  ┌{'─' * box_width}┐"))
        cmd_lines = textwrap.wrap(cmd_display, width=inner - 3)
        for idx, line in enumerate(cmd_lines):
            if idx == 0:
                prefix = f" {bold('$')} {cyan(line)}"
                vis_len = len(f" $ {line}")
            else:
                prefix = f"   {cyan(line)}"
                vis_len = len(f"   {line}")
            pad = max(0, inner - vis_len)
            print(red(f"  │") + prefix + " " * pad + red("│"))
        print(red(f"  └{'─' * box_width}┘"))
        print()  # blank line after command box for readability

        # Skip commands that look like English text, not real shell commands
        if not _is_valid_command(cmd):
            print(f"  {yellow('⚠ Skipped')} — looks like English text, not a command.")
            print(f"  {dim('If this IS a command, use: /run ' + cmd[:60])}")
            print()
            continue

        save_after = False
        was_auto = False
        if trusted:
            from code_agents.agent_system.rules_loader import PROJECT_RULES_DIRNAME
            rules_path = os.path.join(cwd, PROJECT_RULES_DIRNAME, f"{agent_name}.md") if agent_name else ""
            print(f"  {green('● Auto-approved')} {dim(f'(saved in rules)')}")
            _log_auto_run(cmd, "trusted")
            was_auto = True
        elif superpower and agent_autorun != "block":
            # Superpower or edit-mode: auto-run everything except blocklisted
            from .chat_ui import yellow as _yellow
            from .chat_input import is_edit_mode as _is_edit
            if _is_edit():
                print(f"  {green('✓ Accept edits on')} {dim('(auto-execute)')}")
                _log_auto_run(cmd, "edit-mode")
                was_auto = True
            else:
                print(f"  {_yellow('⚡ SUPERPOWER')} {dim('(auto-execute)')}")
                _log_auto_run(cmd, "superpower")
                was_auto = True
        elif superpower and agent_autorun == "block":
            # Superpower but blocklisted — still ask, with save option
            from .chat_ui import yellow as _yellow
            print(f"  {_yellow('⚡ BLOCKED')} {dim('(blocklist override)')}")
            if agent_name and cwd:
                from code_agents.agent_system.rules_loader import PROJECT_RULES_DIRNAME
                save_label = f"Yes & Save to {agent_name} rules"
                options = ["Yes", save_label, "Edit", "No"]
            else:
                options = ["Yes", "Edit", "No"]
            choice = _tab_selector("Blocked command — run anyway?", options, default=2)
            if choice == -2:  # Tab to amend
                amendment = _amend_prompt()
                if amendment:
                    results.append({"command": cmd, "output": f"[USER AMENDMENT]: {amendment}", "exit_code": "amend"})
                    print(f"  {dim(f'Amendment sent to agent: {amendment}')}")
                    print()
                    continue
            choice_text = options[choice]
            if choice_text == "No":
                print(dim("  Skipped."))
                print()
                continue
            elif choice_text == "Edit":
                feedback = _handle_edit(cmd)
                if feedback is not None:
                    results.append({"command": cmd, "output": f"[USER EDIT FEEDBACK]: {feedback}", "exit_code": "feedback"})
                    print(f"  {dim(f'Feedback sent to agent: {feedback}')}")
                    print()
                    continue
                print(dim("  Skipped."))
                print()
                continue
            elif choice_text != "Yes":
                # "Yes & Save to <agent> rules"
                save_after = True
        elif auto_run and safe:
            print(f"  {green('● Auto-run')} {dim('(read-only command)')}")
            _log_auto_run(cmd, "safe-auto-run")
            was_auto = True
        elif auto_run and not safe:
            # Unsafe command in auto-run mode — still ask, with save option
            if agent_name and cwd:
                from code_agents.agent_system.rules_loader import PROJECT_RULES_DIRNAME
                save_label = f"Yes & Save to {agent_name} rules"
                options = ["Yes", save_label, "Edit", "No"]
            else:
                options = ["Yes", "Edit", "No"]
            choice = _tab_selector("Run this command?", options, default=0)
            if choice == -2:  # Tab to amend
                amendment = _amend_prompt()
                if amendment:
                    results.append({"command": cmd, "output": f"[USER AMENDMENT]: {amendment}", "exit_code": "amend"})
                    print(f"  {dim(f'Amendment sent to agent: {amendment}')}")
                    print()
                    continue
            choice_text = options[choice]
            if choice_text == "No":
                print(dim("  Skipped."))
                print()
                continue
            elif choice_text == "Edit":
                feedback = _handle_edit(cmd)
                if feedback is not None:
                    results.append({"command": cmd, "output": f"[USER EDIT FEEDBACK]: {feedback}", "exit_code": "feedback"})
                    print(f"  {dim(f'Feedback sent to agent: {feedback}')}")
                    print()
                    continue
                print(dim("  Skipped."))
                print()
                continue
            elif choice_text != "Yes":
                # "Yes & Save to <agent> rules"
                save_after = True
        else:
            if agent_name and cwd:
                from code_agents.agent_system.rules_loader import PROJECT_RULES_DIRNAME
                save_label = f"Yes & Save to {agent_name} rules"
                options = ["Yes", save_label, "Edit", "No"]
                choice = _tab_selector("Run this command?", options, default=0)
            else:
                options = ["Yes", "Edit", "No"]
                choice = _tab_selector("Run this command?", options, default=0)

            if choice == -2:  # Tab to amend
                amendment = _amend_prompt()
                if amendment:
                    results.append({"command": cmd, "output": f"[USER AMENDMENT]: {amendment}", "exit_code": "amend"})
                    print(f"  {dim(f'Amendment sent to agent: {amendment}')}")
                    print()
                    continue

            choice_text = options[choice]

            if choice_text == "No":
                print(dim("  Skipped."))
                print()
                continue
            elif choice_text == "Edit":
                feedback = _handle_edit(cmd)
                if feedback is not None:
                    results.append({"command": cmd, "output": f"[USER EDIT FEEDBACK]: {feedback}", "exit_code": "feedback"})
                    print(f"  {dim(f'Feedback sent to agent: {feedback}')}")
                    print()
                    continue
                print(dim("  Skipped."))
                print()
                continue
            elif choice_text == "Yes":
                save_after = False
            else:
                # "Yes & Save to <agent> rules"
                save_after = True

        try:
            resolved = _resolve_placeholders(cmd)
        except (EOFError, KeyboardInterrupt):
            print()
            continue
        if not resolved:
            continue

        if dry_run:
            print(f"  {yellow('● DRY-RUN')} {dim('(would execute — CODE_AGENTS_DRY_RUN=true)')}")
            results.append({"command": resolved, "output": "[dry-run: command not executed]"})
            continue

        try:
            output = _run_single_command(resolved, cwd, auto_run=was_auto)
            results.append({"command": resolved, "output": output})
            # Extract context for future placeholder auto-fill
            _extract_context_from_output(output)
        except (EOFError, KeyboardInterrupt):
            print(dim("\n  Command interrupted."))
            continue
        except Exception as e:
            print(red(f"\n  Command failed: {e}"))
            continue

        if save_after and agent_name and cwd:
            try:
                _save_command_to_rules(resolved, agent_name, cwd)
            except Exception as e:
                print(yellow(f"  ! Could not save to rules: {e}"))

    return results
