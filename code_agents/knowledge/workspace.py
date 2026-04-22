"""Multi-Repo Workspace — manage and reason across multiple repositories.

Allows agents to access files and context from multiple repos in a single session.
Workspace config stored at .code-agents/workspace.json in the primary repo.

Usage:
    code-agents workspace add ../other-repo
    code-agents workspace remove ../other-repo
    code-agents workspace list
    code-agents workspace status
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.workspace")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class RepoInfo:
    """Information about a repo in the workspace."""
    path: str
    name: str = ""
    branch: str = ""
    remote_url: str = ""
    added_at: str = ""
    language: str = ""
    description: str = ""


@dataclass
class Workspace:
    """Multi-repo workspace configuration."""
    primary_repo: str = ""
    repos: list[RepoInfo] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Workspace manager
# ---------------------------------------------------------------------------


class WorkspaceManager:
    """Manages multi-repo workspace configuration."""

    def __init__(self, primary_repo: str | None = None):
        self.primary = primary_repo or os.getenv("TARGET_REPO_PATH", os.getcwd())
        self._config_dir = Path(self.primary) / ".code-agents"
        self._config_file = self._config_dir / "workspace.json"
        self._workspace: Optional[Workspace] = None

    def _load(self) -> Workspace:
        """Load workspace config from disk."""
        if self._workspace is not None:
            return self._workspace

        if self._config_file.exists():
            try:
                data = json.loads(self._config_file.read_text())
                repos = [RepoInfo(**r) for r in data.get("repos", [])]
                self._workspace = Workspace(
                    primary_repo=data.get("primary_repo", self.primary),
                    repos=repos,
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                )
            except (json.JSONDecodeError, OSError, TypeError) as e:
                logger.warning("Failed to load workspace config: %s", e)
                self._workspace = self._new_workspace()
        else:
            self._workspace = self._new_workspace()
        return self._workspace

    def _new_workspace(self) -> Workspace:
        """Create a new workspace with the primary repo."""
        return Workspace(
            primary_repo=self.primary,
            repos=[self._detect_repo_info(self.primary)],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

    def _save(self) -> None:
        """Persist workspace config to disk."""
        ws = self._load()
        ws.updated_at = datetime.now().isoformat()
        self._config_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "primary_repo": ws.primary_repo,
            "repos": [asdict(r) for r in ws.repos],
            "created_at": ws.created_at,
            "updated_at": ws.updated_at,
        }
        self._config_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.info("Workspace config saved: %s", self._config_file)

    def _detect_repo_info(self, path: str) -> RepoInfo:
        """Detect git info for a repo path."""
        abs_path = str(Path(path).resolve())
        info = RepoInfo(path=abs_path, added_at=datetime.now().isoformat())

        # Repo name from directory
        info.name = Path(abs_path).name

        try:
            # Current branch
            result = subprocess.run(
                ["git", "-C", abs_path, "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                info.branch = result.stdout.strip()

            # Remote URL
            result = subprocess.run(
                ["git", "-C", abs_path, "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                info.remote_url = result.stdout.strip()

            # Detect primary language
            info.language = self._detect_language(abs_path)

        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug("Git detection failed for %s: %s", abs_path, e)

        return info

    def _detect_language(self, path: str) -> str:
        """Detect primary language of a repo."""
        p = Path(path)
        indicators = {
            "Python": ["pyproject.toml", "setup.py", "requirements.txt"],
            "JavaScript": ["package.json"],
            "TypeScript": ["tsconfig.json"],
            "Java": ["pom.xml", "build.gradle"],
            "Go": ["go.mod"],
            "Rust": ["Cargo.toml"],
            "Ruby": ["Gemfile"],
            "C#": ["*.csproj", "*.sln"],
        }
        for lang, files in indicators.items():
            for f in files:
                if "*" in f:
                    if list(p.glob(f)):
                        return lang
                elif (p / f).exists():
                    return lang
        return "Unknown"

    def add_repo(self, path: str) -> RepoInfo:
        """Add a repo to the workspace."""
        abs_path = str(Path(path).resolve())

        # Verify it's a valid directory
        if not Path(abs_path).is_dir():
            raise ValueError(f"Not a directory: {abs_path}")

        # Check if it's a git repo
        git_dir = Path(abs_path) / ".git"
        if not git_dir.exists():
            raise ValueError(f"Not a git repository: {abs_path}")

        ws = self._load()

        # Check for duplicates
        for repo in ws.repos:
            if Path(repo.path).resolve() == Path(abs_path).resolve():
                raise ValueError(f"Repo already in workspace: {repo.name}")

        info = self._detect_repo_info(abs_path)
        ws.repos.append(info)
        self._save()
        logger.info("Added repo to workspace: %s (%s)", info.name, abs_path)
        return info

    def remove_repo(self, name_or_path: str) -> bool:
        """Remove a repo from the workspace by name or path."""
        ws = self._load()
        resolved = str(Path(name_or_path).resolve()) if os.path.exists(name_or_path) else ""

        for i, repo in enumerate(ws.repos):
            if repo.name == name_or_path or repo.path == resolved or repo.path == name_or_path:
                # Don't remove primary
                if repo.path == str(Path(ws.primary_repo).resolve()):
                    raise ValueError("Cannot remove the primary repo from workspace")
                ws.repos.pop(i)
                self._save()
                return True
        return False

    def list_repos(self) -> list[RepoInfo]:
        """List all repos in the workspace."""
        return self._load().repos

    def status(self) -> dict:
        """Get workspace status with git info for each repo."""
        ws = self._load()
        statuses = []

        for repo in ws.repos:
            info = {
                "name": repo.name,
                "path": repo.path,
                "language": repo.language,
                "branch": "",
                "clean": True,
                "ahead": 0,
                "behind": 0,
            }
            try:
                # Current branch
                result = subprocess.run(
                    ["git", "-C", repo.path, "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    info["branch"] = result.stdout.strip()

                # Working tree status
                result = subprocess.run(
                    ["git", "-C", repo.path, "status", "--porcelain"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    info["clean"] = len(result.stdout.strip()) == 0

                # Ahead/behind
                result = subprocess.run(
                    ["git", "-C", repo.path, "rev-list", "--left-right", "--count", "HEAD...@{u}"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split()
                    if len(parts) == 2:
                        info["ahead"] = int(parts[0])
                        info["behind"] = int(parts[1])

            except (subprocess.TimeoutExpired, OSError, ValueError):
                pass

            statuses.append(info)

        return {
            "primary": ws.primary_repo,
            "repo_count": len(ws.repos),
            "repos": statuses,
        }

    def build_context(self, max_files: int = 20) -> str:
        """Build a cross-repo context string for injection into agent prompts.

        Returns a markdown block with file trees and key files from each repo.
        """
        ws = self._load()
        if len(ws.repos) <= 1:
            return ""  # Single repo, no extra context needed

        lines = ["[Workspace Context — Multi-Repo]"]

        for repo in ws.repos:
            lines.append(f"\n## {repo.name} ({repo.language})")
            lines.append(f"Path: {repo.path}")
            lines.append(f"Branch: {repo.branch}")

            # List top-level structure
            try:
                result = subprocess.run(
                    ["git", "-C", repo.path, "ls-tree", "--name-only", "HEAD"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    files = result.stdout.strip().splitlines()[:max_files]
                    lines.append("Files: " + ", ".join(files))
            except (subprocess.TimeoutExpired, OSError):
                pass

        lines.append("\n[End Workspace Context]")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def cmd_workspace(args: list[str] | None = None):
    """CLI handler for `code-agents workspace`."""
    from code_agents.cli.cli_helpers import _colors, _load_env, _user_cwd
    _load_env()

    args = args or []
    bold, green, yellow, red, cyan, dim = _colors()
    subcmd = args[0] if args else "list"
    cwd = _user_cwd()

    wm = WorkspaceManager(cwd)

    if subcmd == "add":
        if len(args) < 2:
            print(f"  {red('Usage:')} code-agents workspace add <path>")
            return
        path = args[1]
        try:
            info = wm.add_repo(path)
            print(f"\n  {green('Added:')} {bold(info.name)}")
            print(f"    Path:     {info.path}")
            print(f"    Branch:   {info.branch}")
            print(f"    Language: {info.language}")
            print()
        except ValueError as e:
            print(f"\n  {red('Error:')} {e}\n")

    elif subcmd == "remove":
        if len(args) < 2:
            print(f"  {red('Usage:')} code-agents workspace remove <name|path>")
            return
        try:
            if wm.remove_repo(args[1]):
                print(f"\n  {green('Removed:')} {args[1]}\n")
            else:
                print(f"\n  {red('Not found:')} {args[1]}\n")
        except ValueError as e:
            print(f"\n  {red('Error:')} {e}\n")

    elif subcmd == "status":
        status = wm.status()
        print(f"\n  {bold('Workspace Status')}")
        print(f"  Primary: {status['primary']}")
        print(f"  Repos:   {status['repo_count']}")
        print()
        for r in status["repos"]:
            clean_icon = green("clean") if r["clean"] else yellow("dirty")
            ahead_behind = ""
            if r["ahead"] or r["behind"]:
                ahead_behind = f"  {cyan('ahead=' + str(r['ahead']))} {yellow('behind=' + str(r['behind']))}"
            print(f"    {bold(r['name']):<25} {r['branch']:<20} [{clean_icon}]{ahead_behind}")
            print(f"      {dim(r['path'])}")
        print()

    else:  # list
        repos = wm.list_repos()
        if not repos:
            print("  No repos in workspace.")
            return
        print(f"\n  {bold('Workspace Repos:')}")
        for r in repos:
            primary_marker = f" {green('(primary)')}" if r.path == str(Path(cwd).resolve()) else ""
            print(f"    {bold(r.name)}{primary_marker}")
            print(f"      {dim(r.path)}  [{cyan(r.language)}]  branch: {r.branch}")
        print()
