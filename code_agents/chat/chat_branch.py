"""Conversation Branching — fork, switch, and merge conversation branches.

Allows users to explore multiple approaches from any point in a conversation
and merge the best branch back as canonical.

Slash commands:
    /branch [name]   — Fork current conversation at this point
    /branches        — List all branches in current session
    /switch <name>   — Switch to a different branch
    /merge <name>    — Merge a branch back as the canonical conversation
"""

from __future__ import annotations

import copy
import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_branch")


# ---------------------------------------------------------------------------
# Branch manager
# ---------------------------------------------------------------------------


class BranchManager:
    """Manages conversation branches within a chat session."""

    def __init__(self, session: dict):
        """Initialize from a session dict (from chat_history)."""
        self._session = session
        # Branches stored in session["branches"] = {name: {messages, created_at, parent, fork_index}}
        if "branches" not in self._session:
            self._session["branches"] = {}
        if "active_branch" not in self._session:
            self._session["active_branch"] = "main"

        # Ensure "main" branch exists (it's the original conversation)
        if "main" not in self._session["branches"]:
            self._session["branches"]["main"] = {
                "messages": self._session.get("messages", []),
                "created_at": self._session.get("created_at", time.time()),
                "parent": None,
                "fork_index": 0,
            }

    @property
    def active_branch(self) -> str:
        return self._session.get("active_branch", "main")

    @property
    def messages(self) -> list[dict]:
        """Get messages for the active branch."""
        branch = self._session["branches"].get(self.active_branch)
        if branch:
            return branch["messages"]
        return self._session.get("messages", [])

    @messages.setter
    def messages(self, value: list[dict]):
        """Set messages for the active branch."""
        branch = self._session["branches"].get(self.active_branch)
        if branch:
            branch["messages"] = value
        # Also sync to session messages if on main
        if self.active_branch == "main":
            self._session["messages"] = value

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the active branch."""
        msg = {"role": role, "content": content, "timestamp": time.time()}
        branch = self._session["branches"].get(self.active_branch)
        if branch:
            branch["messages"].append(msg)
        if self.active_branch == "main":
            self._session["messages"] = branch["messages"] if branch else []

    def create_branch(self, name: str | None = None) -> str:
        """Fork the active branch at the current point.

        Returns the new branch name.
        """
        if not name:
            # Auto-generate name
            idx = len(self._session["branches"])
            name = f"branch-{idx}"

        if name in self._session["branches"]:
            raise ValueError(f"Branch '{name}' already exists")

        current = self._session["branches"].get(self.active_branch)
        if not current:
            raise ValueError(f"Active branch '{self.active_branch}' not found")

        # Deep copy messages up to current point
        forked_messages = copy.deepcopy(current["messages"])

        self._session["branches"][name] = {
            "messages": forked_messages,
            "created_at": time.time(),
            "parent": self.active_branch,
            "fork_index": len(forked_messages),
        }

        # Switch to new branch
        self._session["active_branch"] = name
        logger.info("Created branch '%s' from '%s' at message %d", name, self.active_branch, len(forked_messages))
        return name

    def switch_branch(self, name: str) -> bool:
        """Switch to an existing branch. Returns True on success."""
        if name not in self._session["branches"]:
            return False
        self._session["active_branch"] = name
        # Sync session messages
        self._session["messages"] = self._session["branches"][name]["messages"]
        logger.info("Switched to branch '%s'", name)
        return True

    def merge_branch(self, name: str) -> bool:
        """Merge a branch into main, making it the canonical conversation.

        The merged branch's messages replace main's messages.
        Returns True on success.
        """
        if name not in self._session["branches"]:
            return False
        if name == "main":
            return True  # Already main

        branch = self._session["branches"][name]

        # Replace main with branch messages
        self._session["branches"]["main"]["messages"] = copy.deepcopy(branch["messages"])
        self._session["messages"] = self._session["branches"]["main"]["messages"]

        # Switch to main
        self._session["active_branch"] = "main"

        # Remove the merged branch
        del self._session["branches"][name]

        logger.info("Merged branch '%s' into main", name)
        return True

    def delete_branch(self, name: str) -> bool:
        """Delete a branch. Cannot delete main or the active branch."""
        if name == "main":
            return False
        if name == self.active_branch:
            return False
        if name not in self._session["branches"]:
            return False

        del self._session["branches"][name]
        logger.info("Deleted branch '%s'", name)
        return True

    def list_branches(self) -> list[dict]:
        """List all branches with metadata."""
        branches = []
        for name, data in self._session["branches"].items():
            branches.append({
                "name": name,
                "active": name == self.active_branch,
                "messages": len(data["messages"]),
                "parent": data.get("parent"),
                "fork_index": data.get("fork_index", 0),
                "created_at": data.get("created_at", 0),
            })
        return sorted(branches, key=lambda b: b["created_at"])

    def get_session(self) -> dict:
        """Return the session dict (with branch data included)."""
        return self._session


# ---------------------------------------------------------------------------
# Slash command handler
# ---------------------------------------------------------------------------


def _handle_branch(command: str, arg: str, state: dict, url: str) -> Optional[str]:
    """Handle /branch, /branches, /switch, /merge slash commands."""

    # Lazily init branch manager on the session
    session = state.get("session", {})
    bm = BranchManager(session)
    state["session"] = bm.get_session()  # write back

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        use_rich = True
    except ImportError:
        use_rich = False

    if command == "/branch":
        try:
            name = bm.create_branch(arg.strip() if arg.strip() else None)
            if use_rich:
                console.print(f"  [green]Created and switched to branch:[/green] [bold]{name}[/bold]")
                console.print(f"  [dim]Forked from '{bm.get_session().get('branches', {}).get(name, {}).get('parent', '?')}' with {len(bm.messages)} messages[/dim]")
            else:
                print(f"  Created branch: {name}")
        except ValueError as e:
            msg = str(e)
            if use_rich:
                console.print(f"  [red]{msg}[/red]")
            else:
                print(f"  Error: {msg}")
        return None

    elif command == "/branches":
        branches = bm.list_branches()
        if not branches:
            print("  No branches.")
            return None

        if use_rich:
            table = Table(title="Conversation Branches")
            table.add_column("Branch", style="bold")
            table.add_column("Messages", justify="center")
            table.add_column("Parent")
            table.add_column("Active", justify="center")

            for b in branches:
                active = "[green]***[/green]" if b["active"] else ""
                style = "bold green" if b["active"] else ""
                table.add_row(
                    f"[{style}]{b['name']}[/{style}]" if style else b["name"],
                    str(b["messages"]),
                    b["parent"] or "—",
                    active,
                )
            console.print(table)
        else:
            print("\n  Branches:")
            for b in branches:
                marker = " ***" if b["active"] else ""
                print(f"    {b['name']}{marker} ({b['messages']} msgs, parent: {b['parent'] or '—'})")
            print()
        return None

    elif command == "/switch":
        name = arg.strip()
        if not name:
            print("  Usage: /switch <branch-name>")
            return None
        if bm.switch_branch(name):
            if use_rich:
                console.print(f"  [green]Switched to branch:[/green] [bold]{name}[/bold] ({len(bm.messages)} messages)")
            else:
                print(f"  Switched to: {name}")
            # Update state messages for chat loop
            state["messages"] = bm.messages
        else:
            msg = f"Branch '{name}' not found"
            if use_rich:
                console.print(f"  [red]{msg}[/red]")
            else:
                print(f"  Error: {msg}")
        return None

    elif command == "/merge":
        name = arg.strip()
        if not name:
            print("  Usage: /merge <branch-name>")
            return None
        if bm.merge_branch(name):
            if use_rich:
                console.print(f"  [green]Merged '{name}' into main.[/green] Now on branch: [bold]main[/bold]")
            else:
                print(f"  Merged '{name}' into main.")
            state["messages"] = bm.messages
        else:
            msg = f"Cannot merge '{name}' — not found or is main"
            if use_rich:
                console.print(f"  [red]{msg}[/red]")
            else:
                print(f"  Error: {msg}")
        return None

    return None
