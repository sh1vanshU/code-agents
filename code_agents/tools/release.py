"""Release automation — end-to-end release pipeline.

Orchestrates: branch creation, tests, changelog, version bump,
commit, push, build, deploy, sanity checks, and Jira updates.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.tools.release")

# Conventional-commit prefixes for changelog grouping
_COMMIT_GROUPS = {
    "feat": "Features",
    "fix": "Bug Fixes",
    "docs": "Documentation",
    "refactor": "Refactoring",
    "test": "Tests",
    "chore": "Chores",
    "perf": "Performance",
    "ci": "CI/CD",
    "style": "Style",
    "build": "Build",
}

# Files where a version string may live
_VERSION_FILES = [
    "__version__.py",
    "pyproject.toml",
    "pom.xml",
    "package.json",
    "build.gradle",
    "setup.cfg",
]


def _run_git(args: list[str], cwd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a git command with timeout."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def parse_version(version: str) -> str:
    """Normalise version string — strip leading 'v' if present."""
    return version.strip().lstrip("v").strip()


class ReleaseManager:
    """Orchestrates the release process step by step."""

    def __init__(self, version: str, cwd: str, dry_run: bool = False):
        self.raw_version = version
        self.version = parse_version(version)  # e.g., "8.1.0"
        self.cwd = cwd
        self.dry_run = dry_run
        self.branch_name = f"release/{self.version}"
        self.steps_completed: list[str] = []
        self.errors: list[str] = []
        self.changelog_entry: str = ""
        self._original_branch: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_all(
        self,
        skip_deploy: bool = False,
        skip_jira: bool = False,
        skip_tests: bool = False,
    ) -> bool:
        """Run entire release pipeline. Returns True if all steps pass."""
        steps: list[tuple[str, callable]] = [
            ("Create release branch", self.create_branch),
        ]
        if not skip_tests:
            steps.append(("Run tests", self.run_tests))
        steps.extend([
            ("Generate changelog", self.generate_changelog),
            ("Bump version", self.bump_version),
            ("Commit changes", self.commit_changes),
            ("Push branch", self.push_branch),
        ])
        if not skip_deploy:
            steps.extend([
                ("Build", self.trigger_build),
                ("Deploy to staging", self.deploy_staging),
                ("Run sanity checks", self.run_sanity),
            ])
        if not skip_jira:
            steps.append(("Update Jira tickets", self.update_jira))

        total = len(steps)
        for idx, (step_name, step_fn) in enumerate(steps, 1):
            logger.info("[%d/%d] %s", idx, total, step_name)
            try:
                ok = step_fn()
                if ok:
                    self.steps_completed.append(step_name)
                    logger.info("  -> OK")
                else:
                    self.errors.append(f"{step_name}: returned failure")
                    logger.error("  -> FAILED")
                    return False
            except Exception as exc:
                self.errors.append(f"{step_name}: {exc}")
                logger.exception("  -> EXCEPTION in %s", step_name)
                return False

        return True

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def create_branch(self) -> bool:
        """Create release branch from main."""
        # Remember current branch for rollback
        result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], self.cwd)
        self._original_branch = result.stdout.strip() or "main"

        if self.dry_run:
            logger.info("[dry-run] Would create branch %s from main", self.branch_name)
            return True

        # Ensure main is up-to-date
        _run_git(["fetch", "origin", "main"], self.cwd, timeout=30)

        result = _run_git(["checkout", "-b", self.branch_name, "main"], self.cwd)
        if result.returncode != 0:
            # Branch may already exist — try switching
            result = _run_git(["checkout", self.branch_name], self.cwd)
            if result.returncode != 0:
                self.errors.append(f"git checkout failed: {result.stderr.strip()}")
                return False
        return True

    def run_tests(self) -> bool:
        """Run project tests using detected or configured test command."""
        test_cmd = self._detect_test_command()
        if not test_cmd:
            logger.warning("No test command detected — skipping tests")
            return True  # non-fatal if no tests found

        if self.dry_run:
            logger.info("[dry-run] Would run: %s", test_cmd)
            return True

        logger.info("Running: %s", test_cmd)
        result = subprocess.run(
            test_cmd,
            shell=True,
            cwd=self.cwd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            self.errors.append(f"Tests failed (exit {result.returncode})")
            # Include last 20 lines of output for diagnostics
            lines = (result.stdout + result.stderr).strip().splitlines()[-20:]
            for line in lines:
                logger.error("  %s", line)
            return False
        return True

    def generate_changelog(self) -> bool:
        """Generate changelog entry from git log since last tag."""
        last_tag = self._get_last_tag()
        if last_tag:
            log_range = f"{last_tag}..HEAD"
        else:
            log_range = "HEAD~50..HEAD"  # fallback: last 50 commits

        result = _run_git(
            ["log", log_range, "--oneline", "--no-merges"],
            self.cwd,
        )
        raw_lines = result.stdout.strip().splitlines() if result.stdout.strip() else []

        # Group commits by conventional-commit prefix
        groups: dict[str, list[str]] = {}
        ungrouped: list[str] = []
        for line in raw_lines:
            # Remove the short hash prefix
            parts = line.split(" ", 1)
            if len(parts) < 2:
                continue
            msg = parts[1]
            matched = False
            for prefix, group_name in _COMMIT_GROUPS.items():
                if msg.lower().startswith(prefix + ":") or msg.lower().startswith(prefix + "("):
                    groups.setdefault(group_name, []).append(msg)
                    matched = True
                    break
            if not matched:
                ungrouped.append(msg)

        # Build markdown
        today = datetime.now().strftime("%Y-%m-%d")
        entry_lines = [f"## [{self.version}] - {today}", ""]
        for group_name, msgs in sorted(groups.items()):
            entry_lines.append(f"### {group_name}")
            for m in msgs:
                entry_lines.append(f"- {m}")
            entry_lines.append("")
        if ungrouped:
            entry_lines.append("### Other")
            for m in ungrouped:
                entry_lines.append(f"- {m}")
            entry_lines.append("")

        self.changelog_entry = "\n".join(entry_lines)

        if self.dry_run:
            logger.info("[dry-run] Changelog entry:\n%s", self.changelog_entry)
            return True

        # Prepend to CHANGELOG.md
        changelog_path = Path(self.cwd) / "CHANGELOG.md"
        if changelog_path.is_file():
            existing = changelog_path.read_text(encoding="utf-8")
            # Insert after the first heading line (# Changelog)
            header_match = re.match(r"(#[^\n]*\n\n?)", existing)
            if header_match:
                insert_pos = header_match.end()
                new_content = existing[:insert_pos] + self.changelog_entry + "\n" + existing[insert_pos:]
            else:
                new_content = self.changelog_entry + "\n" + existing
            changelog_path.write_text(new_content, encoding="utf-8")
        else:
            changelog_path.write_text(
                f"# Changelog\n\n{self.changelog_entry}\n",
                encoding="utf-8",
            )
        return True

    def bump_version(self) -> bool:
        """Detect and update version in project files."""
        files_updated = []
        cwd_path = Path(self.cwd)

        for vfile in _VERSION_FILES:
            # Search recursively but limited depth
            candidates = list(cwd_path.glob(vfile)) + list(cwd_path.glob(f"*/{vfile}"))
            for fpath in candidates:
                if not fpath.is_file():
                    continue
                content = fpath.read_text(encoding="utf-8")
                new_content = self._replace_version_in_content(fpath.name, content)
                if new_content and new_content != content:
                    if self.dry_run:
                        logger.info("[dry-run] Would update version in %s", fpath)
                    else:
                        fpath.write_text(new_content, encoding="utf-8")
                    files_updated.append(str(fpath))

        if files_updated:
            logger.info("Version bumped to %s in: %s", self.version, ", ".join(files_updated))
        else:
            logger.warning("No version files found to update")
        return True  # non-fatal if no version files found

    def commit_changes(self) -> bool:
        """Stage and commit all release changes."""
        if self.dry_run:
            logger.info("[dry-run] Would commit release changes")
            return True

        _run_git(["add", "-A"], self.cwd)
        result = _run_git(
            ["commit", "-m", f"chore: release {self.version}"],
            self.cwd,
        )
        if result.returncode != 0:
            # Nothing to commit is OK
            if "nothing to commit" in result.stdout + result.stderr:
                logger.info("Nothing to commit — all clean")
                return True
            self.errors.append(f"git commit failed: {result.stderr.strip()}")
            return False
        return True

    def push_branch(self) -> bool:
        """Push release branch to origin."""
        if self.dry_run:
            logger.info("[dry-run] Would push branch %s", self.branch_name)
            return True

        result = _run_git(
            ["push", "-u", "origin", self.branch_name],
            self.cwd,
            timeout=120,
        )
        if result.returncode != 0:
            self.errors.append(f"git push failed: {result.stderr.strip()}")
            return False
        return True

    def trigger_build(self) -> bool:
        """Trigger build via Jenkins API or local build command."""
        build_cmd = os.getenv("CODE_AGENTS_BUILD_CMD", "").strip()
        jenkins_job = os.getenv("JENKINS_BUILD_JOB", "").strip()

        if self.dry_run:
            if build_cmd:
                logger.info("[dry-run] Would run local build: %s", build_cmd)
            elif jenkins_job:
                logger.info("[dry-run] Would trigger Jenkins build job: %s", jenkins_job)
            else:
                logger.info("[dry-run] No build configured — skipping")
            return True

        if build_cmd:
            result = subprocess.run(
                build_cmd, shell=True, cwd=self.cwd,
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                self.errors.append(f"Build failed (exit {result.returncode})")
                return False
            return True

        if jenkins_job:
            return self._trigger_jenkins_build()

        logger.info("No build command or Jenkins job configured — skipping build step")
        return True

    def deploy_staging(self) -> bool:
        """Deploy to staging via Jenkins deploy job."""
        deploy_job = os.getenv("JENKINS_DEPLOY_JOB", "").strip()

        if self.dry_run:
            if deploy_job:
                logger.info("[dry-run] Would trigger Jenkins deploy job: %s", deploy_job)
            else:
                logger.info("[dry-run] No deploy job configured — skipping")
            return True

        if not deploy_job:
            logger.info("No JENKINS_DEPLOY_JOB configured — skipping deploy step")
            return True

        return self._trigger_jenkins_deploy()

    def run_sanity(self) -> bool:
        """Run sanity checks if sanity.yaml exists."""
        sanity_path = Path(self.cwd) / ".code-agents" / "sanity.yaml"

        if self.dry_run:
            if sanity_path.is_file():
                logger.info("[dry-run] Would run sanity checks from %s", sanity_path)
            else:
                logger.info("[dry-run] No sanity.yaml found — skipping")
            return True

        if not sanity_path.is_file():
            logger.info("No sanity.yaml found — skipping sanity checks")
            return True

        try:
            from code_agents.cicd.sanity_checker import load_rules, run_checks
            rules = load_rules(self.cwd)
            if not rules:
                logger.info("No sanity rules defined — skipping")
                return True
            results = run_checks(rules, self.cwd)
            failed = [r for r in results if not r.passed]
            if failed:
                for r in failed:
                    logger.error("Sanity FAIL: %s (%d matches)", r.rule.name, r.match_count)
                self.errors.append(f"{len(failed)} sanity check(s) failed")
                return False
            return True
        except ImportError:
            logger.warning("sanity_checker not available — skipping")
            return True
        except Exception as exc:
            logger.warning("Sanity check error: %s", exc)
            return True  # non-fatal

    def update_jira(self) -> bool:
        """Find Jira ticket IDs from commits and transition them to Done."""
        jira_url = os.getenv("JIRA_URL", "").strip()
        jira_project = os.getenv("JIRA_PROJECT_KEY", "").strip()

        if not jira_url:
            logger.info("No JIRA_URL configured — skipping Jira updates")
            return True

        # Extract ticket IDs from commits on this branch
        ticket_ids = self._extract_jira_tickets()
        if not ticket_ids:
            logger.info("No Jira ticket IDs found in commit messages")
            return True

        if self.dry_run:
            logger.info("[dry-run] Would transition tickets to Done: %s", ", ".join(ticket_ids))
            return True

        try:
            from code_agents.cicd.jira_client import JiraClient
            client = JiraClient()
            for ticket_id in ticket_ids:
                try:
                    client.transition_issue(ticket_id, "Done")
                    logger.info("Transitioned %s to Done", ticket_id)
                except Exception as exc:
                    logger.warning("Failed to transition %s: %s", ticket_id, exc)
            return True
        except ImportError:
            logger.warning("JiraClient not available — skipping Jira updates")
            return True
        except Exception as exc:
            logger.warning("Jira update error: %s", exc)
            return True  # non-fatal

    def rollback(self) -> bool:
        """Undo release changes — switch back to original branch."""
        if self.dry_run:
            logger.info("[dry-run] Would rollback to branch %s", self._original_branch)
            return True

        target = self._original_branch or "main"
        result = _run_git(["checkout", target], self.cwd)
        if result.returncode != 0:
            logger.error("Rollback checkout failed: %s", result.stderr.strip())
            return False

        # Delete the release branch locally
        _run_git(["branch", "-D", self.branch_name], self.cwd)
        logger.info("Rolled back to %s, deleted local branch %s", target, self.branch_name)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_test_command(self) -> Optional[str]:
        """Detect the project test command."""
        # Env override
        configured = os.getenv("CODE_AGENTS_TEST_CMD", "").strip()
        if configured:
            return configured

        cwd_path = Path(self.cwd)
        if (cwd_path / "pyproject.toml").is_file() or (cwd_path / "setup.py").is_file():
            return "python -m pytest"
        if (cwd_path / "pom.xml").is_file():
            return "mvn test"
        if (cwd_path / "build.gradle").is_file():
            return "./gradlew test"
        if (cwd_path / "package.json").is_file():
            return "npm test"
        if (cwd_path / "Makefile").is_file():
            return "make test"
        return None

    def _get_last_tag(self) -> Optional[str]:
        """Get the most recent git tag."""
        result = _run_git(["describe", "--tags", "--abbrev=0"], self.cwd)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None

    def _replace_version_in_content(self, filename: str, content: str) -> Optional[str]:
        """Replace version string in file content based on file type."""
        v = self.version

        if filename == "__version__.py":
            return re.sub(
                r'__version__\s*=\s*["\'][^"\']*["\']',
                f'__version__ = "{v}"',
                content,
            )
        if filename == "pyproject.toml":
            return re.sub(
                r'version\s*=\s*"[^"]*"',
                f'version = "{v}"',
                content,
                count=1,
            )
        if filename == "package.json":
            return re.sub(
                r'"version"\s*:\s*"[^"]*"',
                f'"version": "{v}"',
                content,
                count=1,
            )
        if filename == "pom.xml":
            # Replace only the first <version> (project version, not dependency)
            return re.sub(
                r"<version>[^<]*</version>",
                f"<version>{v}</version>",
                content,
                count=1,
            )
        if filename == "build.gradle":
            return re.sub(
                r"version\s*=\s*['\"][^'\"]*['\"]",
                f"version = '{v}'",
                content,
                count=1,
            )
        if filename == "setup.cfg":
            return re.sub(
                r"version\s*=\s*\S+",
                f"version = {v}",
                content,
                count=1,
            )
        return None

    def _extract_jira_tickets(self) -> list[str]:
        """Extract Jira ticket IDs (e.g., PROJ-123) from recent commit messages."""
        last_tag = self._get_last_tag()
        log_range = f"{last_tag}..HEAD" if last_tag else "HEAD~50..HEAD"
        result = _run_git(["log", log_range, "--oneline", "--no-merges"], self.cwd)
        if result.returncode != 0:
            return []

        ticket_pattern = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
        tickets: set[str] = set()
        for line in result.stdout.strip().splitlines():
            tickets.update(ticket_pattern.findall(line))
        return sorted(tickets)

    def _trigger_jenkins_build(self) -> bool:
        """Trigger Jenkins build via the server API."""
        try:
            import httpx
            from code_agents.cli.cli_helpers import _server_url
            url = _server_url()
            r = httpx.post(
                f"{url}/jenkins/build-and-wait",
                json={
                    "job_name": os.getenv("JENKINS_BUILD_JOB", ""),
                    "parameters": {"branch": self.branch_name},
                },
                timeout=600.0,
            )
            data = r.json()
            if data.get("status") == "success":
                return True
            self.errors.append(f"Jenkins build failed: {data.get('error', 'unknown')}")
            return False
        except Exception as exc:
            self.errors.append(f"Jenkins build error: {exc}")
            return False

    def _trigger_jenkins_deploy(self) -> bool:
        """Trigger Jenkins deploy via the server API."""
        try:
            import httpx
            from code_agents.cli.cli_helpers import _server_url
            url = _server_url()
            r = httpx.post(
                f"{url}/jenkins/build-and-wait",
                json={
                    "job_name": os.getenv("JENKINS_DEPLOY_JOB", ""),
                    "parameters": {"branch": self.branch_name, "env_name": "staging"},
                },
                timeout=600.0,
            )
            data = r.json()
            if data.get("status") == "success":
                return True
            self.errors.append(f"Jenkins deploy failed: {data.get('error', 'unknown')}")
            return False
        except Exception as exc:
            self.errors.append(f"Jenkins deploy error: {exc}")
            return False
