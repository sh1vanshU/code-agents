"""Sandbox execution — macOS sandbox-exec wrapper for agent command isolation.

Restricts agent-executed commands to only write within the project directory
and /tmp, using macOS Seatbelt (sandbox-exec). Graceful fallback on other
platforms — warns and runs unsandboxed.

Toggle via:
  - ``/sandbox on|off`` slash command in chat
  - ``CODE_AGENTS_SANDBOX=1`` environment variable
"""
from __future__ import annotations

import logging
import os
import platform
import shlex

logger = logging.getLogger("code_agents.devops.sandbox")


def is_sandbox_available() -> bool:
    """Return True if sandbox-exec is available (macOS only)."""
    return platform.system() == "Darwin" and os.path.exists("/usr/bin/sandbox-exec")


def is_sandbox_enabled() -> bool:
    """Check whether sandbox mode is active via env var."""
    return os.getenv("CODE_AGENTS_SANDBOX", "").strip().lower() in ("1", "true", "yes")


def generate_sandbox_profile(
    cwd: str,
    allow_network: bool = True,
) -> str:
    """Generate a sandbox-exec SBPL profile string.

    Allows:
      - Read: broadly (system dirs, python envs, project files)
      - Write: only to *cwd* and ``/tmp`` (+ macOS private tmp paths)
      - Process: fork/exec (needed for git, python, node, etc.)
      - Network: configurable (allowed by default)
    """
    cwd_real = os.path.realpath(cwd)

    if allow_network:
        network_rule = "(allow network*)"
    else:
        network_rule = (
            "(deny network*)\n"
            "(allow network-outbound (to unix-socket))\n"
            "(allow network-inbound (from unix-socket))"
        )

    return f"""\
(version 1)
(deny default)

;; --- Filesystem ---------------------------------------------------------
(allow file-read*)

(allow file-write*
    (subpath "{cwd_real}")
    (subpath "/tmp")
    (subpath "/private/tmp")
    (subpath "/private/var/folders")
)

;; --- Process ------------------------------------------------------------
(allow process*)

;; --- System services ----------------------------------------------------
(allow sysctl-read)
(allow mach-lookup)
(allow mach-register)

;; --- IPC ----------------------------------------------------------------
(allow ipc-posix*)
(allow ipc-sysv*)

;; --- Network ------------------------------------------------------------
{network_rule}

;; --- Misc ---------------------------------------------------------------
(allow pseudo-tty)
(allow signal)
"""


def wrap_command(command: str, cwd: str, allow_network: bool = True) -> str:
    """Wrap *command* with ``sandbox-exec`` if sandbox is available and enabled.

    Returns the original command unchanged when sandbox is unavailable or
    disabled.
    """
    if not is_sandbox_enabled():
        return command

    if not is_sandbox_available():
        logger.warning(
            "Sandbox enabled but sandbox-exec not available (non-macOS). "
            "Running unsandboxed."
        )
        return command

    profile = generate_sandbox_profile(cwd, allow_network=allow_network)
    escaped_profile = profile.replace("'", "'\\''")
    quoted_cmd = shlex.quote(command)
    return f"sandbox-exec -p '{escaped_profile}' /bin/bash -c {quoted_cmd}"
