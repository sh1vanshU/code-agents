"""Coordinated PR creation across multiple repos in a workspace.

Creates linked PRs across repos that have uncommitted changes,
with cross-references in the PR body for traceability.

Usage:
    from code_agents.knowledge.workspace_pr import CoordinatedPRCreator

    creator = CoordinatedPRCreator(["/path/to/repo-a", "/path/to/repo-b"])
    results = creator.create_linked_prs("feature/my-change", "My PR", "Description")
    statuses = creator.status()
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.knowledge.workspace_pr")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PRResult:
    """Result of creating a PR in a single repo."""
    repo: str
    branch: str
    pr_url: str
    success: bool
    error: str = ""


# ---------------------------------------------------------------------------
# CoordinatedPRCreator
# ---------------------------------------------------------------------------


class CoordinatedPRCreator:
    """Creates linked PRs across multiple repos in a workspace."""

    def __init__(self, repos: list[str]) -> None:
        self.repos = [os.path.abspath(r) for r in repos]

    # -------------------------------------------------------------------
    # Coordinated PR creation
    # -------------------------------------------------------------------

    def create_linked_prs(
        self, branch_name: str, title: str, body: str
    ) -> list[PRResult]:
        """For each repo with uncommitted changes: create branch, commit, push, create PR.

        Adds cross-references in PR body linking all related PRs.
        """
        # Phase 1: identify repos with changes
        repos_with_changes: list[str] = []
        for repo in self.repos:
            if self._has_changes(repo):
                repos_with_changes.append(repo)
                logger.info("Repo has changes: %s", Path(repo).name)
            else:
                logger.debug("No changes in %s, skipping", Path(repo).name)

        if not repos_with_changes:
            logger.info("No repos have uncommitted changes")
            return []

        # Phase 2: create branch, commit, push in each repo
        results: list[PRResult] = []
        for repo in repos_with_changes:
            result = self._prepare_repo(repo, branch_name)
            if result:
                results.append(result)

        # Phase 3: create PRs with cross-references
        successful = [r for r in results if r.success]
        if not successful:
            return results

        # Build cross-reference section
        cross_ref_lines = ["## Linked PRs"]
        for r in successful:
            repo_name = Path(r.repo).name
            cross_ref_lines.append(f"- **{repo_name}**: branch `{r.branch}`")

        cross_ref = "\n".join(cross_ref_lines)
        full_body = f"{body}\n\n{cross_ref}"

        # Create actual PRs
        final_results: list[PRResult] = []
        for r in results:
            if not r.success:
                final_results.append(r)
                continue
            pr_result = self._create_pr(r.repo, branch_name, title, full_body)
            final_results.append(pr_result)

        return final_results

    # -------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------

    def status(self) -> list[dict]:
        """Check open PRs across repos via gh pr list."""
        statuses: list[dict] = []
        for repo in self.repos:
            info: dict[str, Any] = {
                "repo": Path(repo).name,
                "path": repo,
                "open_prs": [],
            }
            try:
                result = subprocess.run(
                    ["gh", "pr", "list", "--json", "number,title,url,state,headRefName"],
                    capture_output=True, text=True, timeout=15,
                    cwd=repo,
                )
                if result.returncode == 0:
                    import json
                    prs = json.loads(result.stdout) if result.stdout.strip() else []
                    info["open_prs"] = prs
            except (subprocess.TimeoutExpired, OSError) as e:
                logger.debug("Failed to list PRs for %s: %s", repo, e)
                info["error"] = str(e)
            statuses.append(info)
        return statuses

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _has_changes(self, repo: str) -> bool:
        """Check if a repo has uncommitted changes (staged or unstaged)."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, timeout=5,
                cwd=repo,
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except (subprocess.TimeoutExpired, OSError):
            return False

    def _prepare_repo(self, repo: str, branch_name: str) -> PRResult | None:
        """Create branch, stage, commit, and push for a repo."""
        repo_name = Path(repo).name

        try:
            # Create and checkout branch
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                capture_output=True, text=True, timeout=10,
                cwd=repo,
            )
            if result.returncode != 0:
                # Branch might already exist, try switching
                result = subprocess.run(
                    ["git", "checkout", branch_name],
                    capture_output=True, text=True, timeout=10,
                    cwd=repo,
                )
                if result.returncode != 0:
                    return PRResult(
                        repo=repo, branch=branch_name, pr_url="",
                        success=False, error=f"Branch checkout failed: {result.stderr.strip()}",
                    )

            # Stage all changes
            result = subprocess.run(
                ["git", "add", "-A"],
                capture_output=True, text=True, timeout=10,
                cwd=repo,
            )
            if result.returncode != 0:
                return PRResult(
                    repo=repo, branch=branch_name, pr_url="",
                    success=False, error=f"git add failed: {result.stderr.strip()}",
                )

            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", f"chore: coordinated change ({branch_name})"],
                capture_output=True, text=True, timeout=15,
                cwd=repo,
            )
            if result.returncode != 0:
                return PRResult(
                    repo=repo, branch=branch_name, pr_url="",
                    success=False, error=f"commit failed: {result.stderr.strip()}",
                )

            # Push
            result = subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                capture_output=True, text=True, timeout=30,
                cwd=repo,
            )
            if result.returncode != 0:
                return PRResult(
                    repo=repo, branch=branch_name, pr_url="",
                    success=False, error=f"push failed: {result.stderr.strip()}",
                )

            logger.info("Prepared %s: branch=%s", repo_name, branch_name)
            return PRResult(repo=repo, branch=branch_name, pr_url="", success=True)

        except (subprocess.TimeoutExpired, OSError) as e:
            return PRResult(
                repo=repo, branch=branch_name, pr_url="",
                success=False, error=str(e),
            )

    def _create_pr(self, repo: str, branch_name: str, title: str, body: str) -> PRResult:
        """Create a PR via gh CLI."""
        repo_name = Path(repo).name
        try:
            result = subprocess.run(
                ["gh", "pr", "create", "--title", title, "--body", body],
                capture_output=True, text=True, timeout=30,
                cwd=repo,
            )
            if result.returncode == 0:
                pr_url = result.stdout.strip()
                logger.info("PR created for %s: %s", repo_name, pr_url)
                return PRResult(repo=repo, branch=branch_name, pr_url=pr_url, success=True)
            else:
                return PRResult(
                    repo=repo, branch=branch_name, pr_url="",
                    success=False, error=f"gh pr create failed: {result.stderr.strip()}",
                )
        except (subprocess.TimeoutExpired, OSError) as e:
            return PRResult(
                repo=repo, branch=branch_name, pr_url="",
                success=False, error=str(e),
            )
