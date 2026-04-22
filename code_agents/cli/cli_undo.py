"""CLI undo command — revert the last agent action."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_undo")


def cmd_undo():
    """Undo the last agent action (file edits, git commits).

    Usage:
      code-agents undo              # undo last action (with confirmation)
      code-agents undo --list       # show recent undoable actions
      code-agents undo --all        # undo all actions in session
      code-agents undo --dry-run    # show what would be undone
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    mode = "last"
    dry_run = False

    for a in args:
        if a in ("--list", "-l"):
            mode = "list"
        elif a == "--all":
            mode = "all"
        elif a == "--dry-run":
            dry_run = True
        elif a in ("--help", "-h"):
            print(cmd_undo.__doc__)
            return

    # Find the most recent session
    from code_agents.git_ops.action_log import ActionLog, undo_action, SESSIONS_DIR

    if not SESSIONS_DIR.exists():
        print(yellow("  No action history found. Start a chat session first."))
        return

    # Get latest session
    sessions = sorted(
        [d for d in SESSIONS_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not sessions:
        print(yellow("  No action history found."))
        return

    session_dir = sessions[0]
    session_id = session_dir.name
    log = ActionLog(session_id)
    actions = log.get_undoable()

    if not actions:
        print(yellow("  No undoable actions in the current session."))
        return

    if mode == "list":
        print()
        print(bold(f"  Undoable actions (session: {session_id[:12]}...)"))
        print()
        for i, action in enumerate(actions, 1):
            from datetime import datetime
            ts = datetime.fromtimestamp(action.timestamp).strftime("%H:%M:%S")
            icon = _action_icon(action.action_type)
            print(f"  {dim(f'{i}.')} {icon} {action.description}  {dim(ts)}")
        print()
        print(dim(f"  Total: {len(actions)} undoable action(s)"))
        print(dim(f"  Run 'code-agents undo' to revert the most recent."))
        print()
        return

    if mode == "all":
        print()
        print(bold("  Undoing ALL actions in session:"))
        print()
        undone = 0
        for action in actions:
            ok, msg = undo_action(action, dry_run=dry_run)
            icon = green("✓") if ok else red("✗")
            prefix = dim("[dry-run] ") if dry_run else ""
            print(f"  {icon} {prefix}{msg}")
            if ok:
                undone += 1
                if not dry_run:
                    log.pop_last()
        print()
        print(f"  {bold(f'{undone}/{len(actions)}')} actions {'would be ' if dry_run else ''}undone.")
        print()
        return

    # Default: undo last action
    action = actions[0]
    print()
    icon = _action_icon(action.action_type)
    print(f"  Last action: {icon} {bold(action.description)}")

    if dry_run:
        ok, msg = undo_action(action, dry_run=True)
        print(f"  {dim('[dry-run]')} {msg}")
        print()
        return

    # Confirm
    try:
        answer = input(f"  Undo this? {dim('[y/N]')} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if answer not in ("y", "yes"):
        print(dim("  Cancelled."))
        return

    ok, msg = undo_action(action)
    if ok:
        log.pop_last()
        print(f"  {green('✓')} {msg}")
    else:
        print(f"  {red('✗')} {msg}")
    print()


def _action_icon(action_type: str) -> str:
    """Return an icon for the action type."""
    icons = {
        "file_create": "📄",
        "file_edit": "✏️",
        "file_delete": "🗑️",
        "git_commit": "📦",
        "command_run": "⚡",
    }
    return icons.get(action_type, "•")
