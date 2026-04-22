"""Smart Commit — AI-assisted commit message generation."""

import logging
import os
import re
import subprocess
from typing import Optional

logger = logging.getLogger("code_agents.tools.smart_commit")


class SmartCommit:
    """Generates conventional commit messages from staged diffs."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def get_staged_diff(self) -> str:
        """Get the staged diff (stat + full diff)."""
        result = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True, text=True, timeout=15, cwd=self.cwd,
        )
        stat = result.stdout.strip() if result.returncode == 0 else ""

        result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, timeout=30, cwd=self.cwd,
        )
        diff = result.stdout.strip() if result.returncode == 0 else ""

        return f"Stats:\n{stat}\n\nDiff:\n{diff}"

    def get_staged_files(self) -> list[str]:
        """Get list of staged files."""
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=10, cwd=self.cwd,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().split("\n") if f]
        return []

    def get_current_branch(self) -> str:
        """Get current branch name."""
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=self.cwd,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    def extract_jira_ticket(self, branch: str = "") -> Optional[str]:
        """Extract Jira ticket from branch name or env.

        Supports patterns like:
          feature/PROJ-123-description
          fix/PROJ-456
          PROJ-789
        """
        if not branch:
            branch = self.get_current_branch()

        # Common patterns: feature/PROJ-123-description, fix/PROJ-456, PROJ-789
        match = re.search(r"([A-Z]{2,10}-\d+)", branch)
        if match:
            return match.group(1)

        # Also check JIRA_PROJECT_KEY env
        project_key = os.getenv("JIRA_PROJECT_KEY", "")
        if project_key:
            match = re.search(rf"({project_key}-\d+)", branch, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return None

    def classify_change(self, files: list[str], diff: str) -> str:
        """Classify the change type based on files and diff content."""
        # Test files
        if all(("test" in f.lower() or "spec" in f.lower()) for f in files):
            return "test"

        # Docs
        if all(f.lower().endswith((".md", ".rst", ".txt", ".adoc")) for f in files):
            return "docs"

        # Config/CI
        config_exts = (
            ".yml", ".yaml", ".json", ".toml", ".cfg", ".ini",
            "dockerfile", ".github", "jenkinsfile", ".gitlab-ci",
        )
        if all(any(p in f.lower() for p in config_exts) for f in files):
            return "chore"

        # Check diff for patterns
        diff_lower = diff.lower()
        if "fix" in diff_lower and (
            "bug" in diff_lower or "error" in diff_lower or "issue" in diff_lower
        ):
            return "fix"

        # Refactoring signals
        if "rename" in diff_lower or "refactor" in diff_lower or "extract" in diff_lower:
            return "refactor"

        # New files
        result = subprocess.run(
            ["git", "diff", "--cached", "--diff-filter=A", "--name-only"],
            capture_output=True, text=True, timeout=10, cwd=self.cwd,
        )
        new_files = result.stdout.strip().split("\n") if result.returncode == 0 else []
        new_files = [f for f in new_files if f]
        if len(new_files) == len(files):
            return "feat"
        if len(new_files) > len(files) / 2:
            return "feat"

        # Default
        return "feat"

    def generate_scope(self, files: list[str]) -> str:
        """Generate scope from file paths."""
        if not files:
            return ""

        # Find common directory
        dirs = set()
        for f in files:
            parts = f.split("/")
            if len(parts) > 1:
                dirs.add(parts[0])
                if len(parts) > 2:
                    dirs.add(parts[1])

        if len(dirs) == 1:
            return list(dirs)[0]

        # Map common directories to scopes
        scope_map = {
            "tests": "tests",
            "test": "tests",
            "src": "",
            "lib": "",
            "docs": "docs",
            "doc": "docs",
            "config": "config",
            "agents": "agents",
            "code_agents": "",
        }

        for d in dirs:
            if d in scope_map and scope_map[d]:
                return scope_map[d]

        # Use first directory if only one meaningful one
        meaningful = [d for d in dirs if d not in ("src", "lib", "code_agents")]
        if len(meaningful) == 1:
            return meaningful[0]

        return ""

    def generate_description(self, files: list[str], diff: str, change_type: str) -> str:
        """Generate a human-readable description from the diff."""
        # Simple heuristic-based description
        if len(files) == 1:
            filename = os.path.basename(files[0])
            stem = os.path.splitext(filename)[0]
            if change_type == "test":
                return f"add tests for {stem}"
            elif change_type == "docs":
                return f"update {filename}"
            elif change_type == "fix":
                return f"fix issue in {stem}"
            elif change_type == "refactor":
                return f"refactor {stem}"
            else:
                return f"add {stem}"

        # Multiple files
        if change_type == "test":
            return f"add tests ({len(files)} files)"
        elif change_type == "docs":
            return f"update documentation ({len(files)} files)"
        elif change_type == "fix":
            return f"fix issues across {len(files)} files"
        elif change_type == "refactor":
            return f"refactor {len(files)} files"
        else:
            # Try to summarize from file patterns
            new_result = subprocess.run(
                ["git", "diff", "--cached", "--diff-filter=A", "--name-only"],
                capture_output=True, text=True, timeout=10, cwd=self.cwd,
            )
            new_files = [
                f
                for f in (
                    new_result.stdout.strip().split("\n")
                    if new_result.returncode == 0
                    else []
                )
                if f
            ]

            if new_files:
                base = os.path.splitext(os.path.basename(new_files[0]))[0]
                if len(files) > 1:
                    return f"add {base} and {len(files) - 1} more files"
                return f"add {base}"

            return f"update {len(files)} files"

    def generate_message(self) -> dict:
        """Generate the full commit message.

        Returns dict with: type, scope, description, body, ticket, full_message.
        On error returns dict with 'error' key.
        """
        files = self.get_staged_files()
        if not files:
            return {"error": "No staged files. Stage changes first: git add <files>"}

        diff = self.get_staged_diff()
        branch = self.get_current_branch()
        ticket = self.extract_jira_ticket(branch)
        change_type = self.classify_change(files, diff)
        scope = self.generate_scope(files)
        description = self.generate_description(files, diff, change_type)

        # Build conventional commit message
        header = change_type
        if scope:
            header += f"({scope})"
        header += f": {description}"

        # Body: list of files
        body_lines: list[str] = []
        if len(files) > 1:
            body_lines.append("")
            for f in files[:15]:
                body_lines.append(f"- {f}")
            if len(files) > 15:
                body_lines.append(f"- ... and {len(files) - 15} more")

        # Footer: Jira ticket
        footer = ""
        if ticket:
            footer = f"\nRefs: {ticket}"

        full_message = header
        if body_lines:
            full_message += "\n" + "\n".join(body_lines)
        if footer:
            full_message += "\n" + footer

        logger.info("Generated commit message: %s (type=%s, scope=%s, ticket=%s)",
                     header, change_type, scope, ticket)

        return {
            "type": change_type,
            "scope": scope,
            "description": description,
            "body": "\n".join(body_lines),
            "ticket": ticket,
            "files": files,
            "full_message": full_message,
        }

    def commit(self, message: str) -> bool:
        """Execute the git commit."""
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True, text=True, timeout=30, cwd=self.cwd,
        )
        if result.returncode == 0:
            logger.info("Committed: %s", message.split("\n")[0])
            # Auto-bump CLAUDE.md version if it was part of the commit
            self._bump_claude_md_version()
            return True
        else:
            logger.error("Commit failed: %s", result.stderr)
            return False

    def _bump_claude_md_version(self) -> None:
        """Bump CLAUDE.md version if it was modified in this commit."""
        try:
            # Check if CLAUDE.md was in the committed files
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
                capture_output=True, text=True, timeout=10, cwd=self.cwd,
            )
            if result.returncode != 0:
                return
            committed_files = result.stdout.strip().split("\n")
            claude_md_path = os.path.join(self.cwd, "CLAUDE.md")
            if not os.path.exists(claude_md_path):
                return

            if "CLAUDE.md" in committed_files:
                # Get CLAUDE.md diff to detect bump type
                diff_result = subprocess.run(
                    ["git", "diff", "HEAD~1", "HEAD", "--", "CLAUDE.md"],
                    capture_output=True, text=True, timeout=10, cwd=self.cwd,
                )
                diff_text = diff_result.stdout if diff_result.returncode == 0 else ""
                from code_agents.knowledge.claude_md_version import detect_bump_type, bump_version, get_current_version
                bump_type = detect_bump_type(diff_text)
                old_ver = get_current_version(claude_md_path)
                new_ver = bump_version(claude_md_path, bump_type)
                if new_ver != old_ver:
                    # Amend the commit to include the version bump
                    subprocess.run(
                        ["git", "add", "CLAUDE.md"],
                        capture_output=True, timeout=5, cwd=self.cwd,
                    )
                    subprocess.run(
                        ["git", "commit", "--amend", "--no-edit"],
                        capture_output=True, timeout=10, cwd=self.cwd,
                    )
                    logger.info("CLAUDE.md version bumped: %s → %s (%s)",
                                ".".join(map(str, old_ver)), ".".join(map(str, new_ver)), bump_type)
        except Exception as e:
            logger.debug("CLAUDE.md version bump skipped: %s", e)
