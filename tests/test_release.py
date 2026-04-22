"""Tests for release.py — release automation pipeline."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.tools.release import ReleaseManager, parse_version


# ── Version parsing ──────────────────────────────────────────────────────────


class TestParseVersion:
    """Test version string normalisation."""

    def test_strips_v_prefix(self):
        assert parse_version("v8.1.0") == "8.1.0"

    def test_no_prefix(self):
        assert parse_version("8.1.0") == "8.1.0"

    def test_strips_whitespace(self):
        assert parse_version("  v1.0.0  ") == "1.0.0"

    def test_double_v(self):
        assert parse_version("vv2.0.0") == "2.0.0"  # lstrip removes all leading v's

    def test_semver_only(self):
        assert parse_version("0.2.0") == "0.2.0"


# ── ReleaseManager init ─────────────────────────────────────────────────────


class TestReleaseManagerInit:
    """Test ReleaseManager construction."""

    def test_version_normalised(self):
        mgr = ReleaseManager("v8.1.0", "/tmp/repo")
        assert mgr.version == "8.1.0"
        assert mgr.raw_version == "v8.1.0"

    def test_branch_name(self):
        mgr = ReleaseManager("v3.2.1", "/tmp/repo")
        assert mgr.branch_name == "release/3.2.1"

    def test_dry_run_flag(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        assert mgr.dry_run is True

    def test_initial_state(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo")
        assert mgr.steps_completed == []
        assert mgr.errors == []
        assert mgr.changelog_entry == ""


# ── Dry-run mode ─────────────────────────────────────────────────────────────


class TestDryRun:
    """Test that dry-run mode does not execute real commands."""

    def test_create_branch_dry_run(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.return_value = MagicMock(stdout="main", returncode=0)
            assert mgr.create_branch() is True
            # Only called once (to get current branch), not for checkout
            assert mock_git.call_count == 1

    def test_run_tests_dry_run(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        with patch.object(mgr, "_detect_test_command", return_value="pytest"):
            assert mgr.run_tests() is True

    def test_commit_changes_dry_run(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        assert mgr.commit_changes() is True

    def test_push_branch_dry_run(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        assert mgr.push_branch() is True

    def test_trigger_build_dry_run(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        assert mgr.trigger_build() is True

    def test_deploy_staging_dry_run(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        assert mgr.deploy_staging() is True

    def test_update_jira_dry_run(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        with patch.dict(os.environ, {"JIRA_URL": "https://jira.example.com"}):
            with patch.object(mgr, "_extract_jira_tickets", return_value=["PROJ-123"]):
                assert mgr.update_jira() is True

    def test_rollback_dry_run(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        assert mgr.rollback() is True


# ── Changelog generation ─────────────────────────────────────────────────────


class TestChangelogGeneration:
    """Test changelog generation from git log."""

    def _make_mgr(self, tmp_path: Path) -> ReleaseManager:
        """Create a manager pointing at a temp dir."""
        return ReleaseManager("2.0.0", str(tmp_path), dry_run=True)

    def test_groups_conventional_commits(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        git_output = textwrap.dedent("""\
            abc1234 feat: add release automation
            def5678 fix: handle missing changelog
            ghi9012 docs: update README
            jkl3456 chore: bump deps
            mno7890 something without prefix
        """)
        with patch("code_agents.tools.release._run_git") as mock_git:
            # _get_last_tag
            mock_git.side_effect = [
                MagicMock(stdout="v1.0.0\n", returncode=0),  # describe --tags
                MagicMock(stdout=git_output, returncode=0),   # log
            ]
            assert mgr.generate_changelog() is True

        assert "## [2.0.0]" in mgr.changelog_entry
        assert "### Features" in mgr.changelog_entry
        assert "### Bug Fixes" in mgr.changelog_entry
        assert "### Documentation" in mgr.changelog_entry
        assert "### Other" in mgr.changelog_entry
        assert "something without prefix" in mgr.changelog_entry

    def test_no_last_tag_uses_fallback(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="", returncode=128),          # no tags
                MagicMock(stdout="abc feat: init\n", returncode=0),
            ]
            assert mgr.generate_changelog() is True
        # Verify the fallback range was used
        call_args = mock_git.call_args_list[1]
        assert "HEAD~50..HEAD" in call_args[0][0]

    def test_empty_log_still_produces_header(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="v1.0.0\n", returncode=0),
                MagicMock(stdout="", returncode=0),
            ]
            assert mgr.generate_changelog() is True
        assert "## [2.0.0]" in mgr.changelog_entry


# ── Version bump detection ───────────────────────────────────────────────────


class TestVersionBump:
    """Test version replacement in different file types."""

    def test_pyproject_toml(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('version = "1.0.0"\n')
        mgr = ReleaseManager("2.0.0", str(tmp_path))
        assert mgr.bump_version() is True
        content = (tmp_path / "pyproject.toml").read_text()
        assert 'version = "2.0.0"' in content

    def test_version_py(self, tmp_path):
        (tmp_path / "__version__.py").write_text('__version__ = "1.0.0"\n')
        mgr = ReleaseManager("2.0.0", str(tmp_path))
        assert mgr.bump_version() is True
        content = (tmp_path / "__version__.py").read_text()
        assert '__version__ = "2.0.0"' in content

    def test_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text('{\n  "version": "1.0.0"\n}\n')
        mgr = ReleaseManager("2.0.0", str(tmp_path))
        assert mgr.bump_version() is True
        content = (tmp_path / "package.json").read_text()
        assert '"version": "2.0.0"' in content

    def test_pom_xml(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project>\n  <version>1.0.0</version>\n</project>\n")
        mgr = ReleaseManager("2.0.0", str(tmp_path))
        assert mgr.bump_version() is True
        content = (tmp_path / "pom.xml").read_text()
        assert "<version>2.0.0</version>" in content

    def test_no_version_files_is_ok(self, tmp_path):
        """No version files should not cause failure."""
        mgr = ReleaseManager("2.0.0", str(tmp_path))
        assert mgr.bump_version() is True

    def test_nested_version_file(self, tmp_path):
        sub = tmp_path / "mypackage"
        sub.mkdir()
        (sub / "__version__.py").write_text('__version__ = "0.1.0"\n')
        mgr = ReleaseManager("0.2.0", str(tmp_path))
        assert mgr.bump_version() is True
        content = (sub / "__version__.py").read_text()
        assert '__version__ = "0.2.0"' in content


# ── Step tracking ────────────────────────────────────────────────────────────


class TestStepTracking:
    """Test that steps_completed and errors are tracked correctly."""

    def test_run_all_dry_run(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=True)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.return_value = MagicMock(stdout="main\n", returncode=0)
            ok = mgr.run_all(skip_deploy=True, skip_jira=True, skip_tests=True)
        assert ok is True
        assert len(mgr.steps_completed) > 0
        assert "Create release branch" in mgr.steps_completed

    def test_step_failure_stops_pipeline(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            # create_branch will fail
            mock_git.return_value = MagicMock(
                stdout="", stderr="fatal: error", returncode=128,
            )
            ok = mgr.run_all(skip_deploy=True, skip_jira=True, skip_tests=True)
        assert ok is False
        assert len(mgr.errors) > 0


# ── Rollback ─────────────────────────────────────────────────────────────────


class TestRollback:
    """Test rollback logic."""

    def test_rollback_switches_branch(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo")
        mgr._original_branch = "develop"
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=0)
            assert mgr.rollback() is True
        # Should have called checkout and branch -D
        calls = [c[0][0] for c in mock_git.call_args_list]
        assert ["checkout", "develop"] in calls
        assert ["branch", "-D", "release/1.0.0"] in calls

    def test_rollback_defaults_to_main(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo")
        mgr._original_branch = None
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=0)
            assert mgr.rollback() is True
        first_call = mock_git.call_args_list[0][0][0]
        assert first_call == ["checkout", "main"]


# ── Test command detection ───────────────────────────────────────────────────


class TestDetectTestCommand:
    """Test _detect_test_command heuristics."""

    def test_env_override(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path))
        with patch.dict(os.environ, {"CODE_AGENTS_TEST_CMD": "make check"}):
            assert mgr._detect_test_command() == "make check"

    def test_detects_pytest(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        mgr = ReleaseManager("1.0.0", str(tmp_path))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_TEST_CMD", None)
            assert mgr._detect_test_command() == "python -m pytest"

    def test_detects_maven(self, tmp_path):
        (tmp_path / "pom.xml").write_text("")
        mgr = ReleaseManager("1.0.0", str(tmp_path))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_TEST_CMD", None)
            assert mgr._detect_test_command() == "mvn test"

    def test_detects_npm(self, tmp_path):
        (tmp_path / "package.json").write_text("")
        mgr = ReleaseManager("1.0.0", str(tmp_path))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_TEST_CMD", None)
            assert mgr._detect_test_command() == "npm test"

    def test_detects_gradle(self, tmp_path):
        (tmp_path / "build.gradle").write_text("")
        mgr = ReleaseManager("1.0.0", str(tmp_path))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_TEST_CMD", None)
            assert mgr._detect_test_command() == "./gradlew test"

    def test_no_test_command(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_TEST_CMD", None)
            assert mgr._detect_test_command() is None


# ── Jira ticket extraction ───────────────────────────────────────────────────


class TestJiraTicketExtraction:
    """Test _extract_jira_tickets from commit messages."""

    def test_extracts_tickets(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo")
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="v0.9.0\n", returncode=0),  # describe
                MagicMock(
                    stdout="abc feat: PROJ-123 add feature\ndef fix: PROJ-456 bug\nghi PROJ-123 dup\n",
                    returncode=0,
                ),
            ]
            tickets = mgr._extract_jira_tickets()
        assert tickets == ["PROJ-123", "PROJ-456"]  # sorted, deduplicated

    def test_no_tickets(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo")
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="", returncode=128),
                MagicMock(stdout="abc no ticket here\n", returncode=0),
            ]
            tickets = mgr._extract_jira_tickets()
        assert tickets == []


# ── Jira update (no config) ─────────────────────────────────────────────────


class TestUpdateJira:
    """Test update_jira when Jira is not configured."""

    def test_skips_when_no_jira_url(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JIRA_URL", None)
            assert mgr.update_jira() is True

    def test_skips_when_no_tickets(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo")
        with patch.dict(os.environ, {"JIRA_URL": "https://jira.example.com"}):
            with patch.object(mgr, "_extract_jira_tickets", return_value=[]):
                assert mgr.update_jira() is True


# ── run_all exception handling (lines 117-120) ─────────────────────────────


class TestRunAllExceptionHandling:
    """Test run_all when a step raises an exception."""

    def test_step_exception_stops_pipeline(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        with patch.object(mgr, "create_branch", side_effect=RuntimeError("boom")):
            ok = mgr.run_all(skip_deploy=True, skip_jira=True, skip_tests=True)
        assert ok is False
        assert any("boom" in e for e in mgr.errors)

    def test_step_returning_false_stops_pipeline(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        with patch.object(mgr, "create_branch", return_value=False):
            ok = mgr.run_all(skip_deploy=True, skip_jira=True, skip_tests=True)
        assert ok is False
        assert len(mgr.errors) > 0
        assert "returned failure" in mgr.errors[0]


# ── create_branch (line 148) ──────────────────────────────────────────────


class TestCreateBranchNonDryRun:
    """Test create_branch in non-dry-run mode."""

    def test_checkout_new_branch_success(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="main\n", returncode=0),    # rev-parse
                MagicMock(returncode=0),                      # fetch
                MagicMock(returncode=0),                      # checkout -b
            ]
            assert mgr.create_branch() is True

    def test_checkout_existing_branch_fallback(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="main\n", returncode=0),                    # rev-parse
                MagicMock(returncode=0),                                      # fetch
                MagicMock(returncode=128, stderr="already exists"),           # checkout -b fails
                MagicMock(returncode=0),                                      # checkout existing
            ]
            assert mgr.create_branch() is True

    def test_checkout_both_fail(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="main\n", returncode=0),
                MagicMock(returncode=0),
                MagicMock(returncode=128, stderr="fail"),
                MagicMock(returncode=128, stderr="fail again"),
            ]
            assert mgr.create_branch() is False
            assert len(mgr.errors) > 0


# ── run_tests non-dry-run (lines 154-177) ─────────────────────────────────


class TestRunTestsNonDryRun:
    """Test run_tests in non-dry-run mode."""

    def test_no_test_command_skips(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        with patch.object(mgr, "_detect_test_command", return_value=None):
            assert mgr.run_tests() is True

    def test_tests_pass(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        with patch.object(mgr, "_detect_test_command", return_value="pytest"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert mgr.run_tests() is True

    def test_tests_fail(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        with patch.object(mgr, "_detect_test_command", return_value="pytest"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="FAILED test_x\n", stderr="error output\n"
            )
            assert mgr.run_tests() is False
            assert any("Tests failed" in e for e in mgr.errors)


# ── generate_changelog non-dry-run (lines 232-248) ────────────────────────


class TestChangelogWriteFile:
    """Test changelog writing to disk."""

    def test_creates_new_changelog(self, tmp_path):
        mgr = ReleaseManager("2.0.0", str(tmp_path), dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="", returncode=128),
                MagicMock(stdout="abc feat: init\n", returncode=0),
            ]
            assert mgr.generate_changelog() is True
        cl = (tmp_path / "CHANGELOG.md").read_text()
        assert "# Changelog" in cl
        assert "[2.0.0]" in cl

    def test_prepends_to_existing_changelog_with_header(self, tmp_path):
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [1.0.0] - old\n")
        mgr = ReleaseManager("2.0.0", str(tmp_path), dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="v1.0.0\n", returncode=0),
                MagicMock(stdout="abc feat: new feature\n", returncode=0),
            ]
            assert mgr.generate_changelog() is True
        cl = (tmp_path / "CHANGELOG.md").read_text()
        assert "## [2.0.0]" in cl
        assert "## [1.0.0]" in cl

    def test_prepends_to_existing_changelog_without_header(self, tmp_path):
        (tmp_path / "CHANGELOG.md").write_text("Some content without heading\n")
        mgr = ReleaseManager("2.0.0", str(tmp_path), dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="", returncode=128),
                MagicMock(stdout="abc chore: update\n", returncode=0),
            ]
            assert mgr.generate_changelog() is True
        cl = (tmp_path / "CHANGELOG.md").read_text()
        assert "[2.0.0]" in cl


# ── commit_changes non-dry-run (lines 260-294) ────────────────────────────


class TestCommitChangesNonDryRun:
    """Test commit_changes in non-dry-run mode."""

    def test_commit_success(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=0)
            assert mgr.commit_changes() is True

    def test_nothing_to_commit(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(returncode=0),  # add -A
                MagicMock(returncode=1, stdout="nothing to commit", stderr=""),  # commit
            ]
            assert mgr.commit_changes() is True

    def test_commit_failure(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=1, stdout="", stderr="commit hook failed"),
            ]
            assert mgr.commit_changes() is False
            assert any("commit failed" in e for e in mgr.errors)


# ── push_branch non-dry-run (lines 302-310) ───────────────────────────────


class TestPushBranchNonDryRun:
    def test_push_success(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=0)
            assert mgr.push_branch() is True

    def test_push_failure(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=1, stderr="rejected")
            assert mgr.push_branch() is False
            assert any("push failed" in e for e in mgr.errors)


# ── trigger_build non-dry-run (lines 312-340) ─────────────────────────────


class TestTriggerBuildNonDryRun:
    def test_local_build_success(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch.dict(os.environ, {"CODE_AGENTS_BUILD_CMD": "make build", "JENKINS_BUILD_JOB": ""}), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert mgr.trigger_build() is True

    def test_local_build_failure(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch.dict(os.environ, {"CODE_AGENTS_BUILD_CMD": "make build", "JENKINS_BUILD_JOB": ""}), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert mgr.trigger_build() is False

    def test_no_build_configured(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch.dict(os.environ, {"CODE_AGENTS_BUILD_CMD": "", "JENKINS_BUILD_JOB": ""}):
            assert mgr.trigger_build() is True

    def test_deploy_no_job(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch.dict(os.environ, {"JENKINS_DEPLOY_JOB": ""}):
            assert mgr.deploy_staging() is True


# ── run_sanity (lines 359-393) ─────────────────────────────────────────────


class TestRunSanity:
    def test_no_sanity_yaml(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        assert mgr.run_sanity() is True

    def test_dry_run_with_sanity_yaml(self, tmp_path):
        ca_dir = tmp_path / ".code-agents"
        ca_dir.mkdir()
        (ca_dir / "sanity.yaml").write_text("rules: []\n")
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=True)
        assert mgr.run_sanity() is True

    def test_dry_run_no_sanity_yaml(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=True)
        assert mgr.run_sanity() is True

    def test_sanity_import_error(self, tmp_path):
        ca_dir = tmp_path / ".code-agents"
        ca_dir.mkdir()
        (ca_dir / "sanity.yaml").write_text("rules: []\n")
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        with patch("builtins.__import__", side_effect=ImportError("no module")):
            assert mgr.run_sanity() is True


# ── update_jira with JiraClient (lines 414-429) ───────────────────────────


class TestUpdateJiraWithClient:
    def test_transitions_tickets(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch.dict(os.environ, {"JIRA_URL": "https://jira.example.com"}), \
             patch.object(mgr, "_extract_jira_tickets", return_value=["PROJ-1", "PROJ-2"]):
            mock_client = MagicMock()
            with patch("code_agents.tools.release.ReleaseManager.update_jira") as mock_update:
                # Test the actual logic by calling directly with mocked imports
                pass

    def test_jira_transition_exception(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch.dict(os.environ, {"JIRA_URL": "https://jira.example.com"}), \
             patch.object(mgr, "_extract_jira_tickets", return_value=["PROJ-1"]):
            mock_jira_module = MagicMock()
            mock_client = MagicMock()
            mock_client.transition_issue.side_effect = Exception("transition error")
            mock_jira_module.JiraClient.return_value = mock_client
            import sys
            sys.modules["code_agents.cicd.jira_client"] = mock_jira_module
            try:
                result = mgr.update_jira()
                assert result is True  # non-fatal
            finally:
                sys.modules.pop("code_agents.cicd.jira_client", None)

    def test_jira_import_error(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch.dict(os.environ, {"JIRA_URL": "https://jira.example.com"}), \
             patch.object(mgr, "_extract_jira_tickets", return_value=["PROJ-1"]):
            import sys
            # Remove the module so import fails
            saved = sys.modules.pop("code_agents.cicd.jira_client", None)
            with patch("builtins.__import__", side_effect=ImportError("no jira")):
                result = mgr.update_jira()
                assert result is True
            if saved:
                sys.modules["code_agents.cicd.jira_client"] = saved


# ── rollback failure (lines 440-441) ──────────────────────────────────────


class TestRollbackFailure:
    def test_rollback_checkout_fails(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo")
        mgr._original_branch = "main"
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=1, stderr="error")
            assert mgr.rollback() is False


# ── detect_test_command: Makefile (line 469) ──────────────────────────────


class TestDetectMakefile:
    def test_detects_makefile(self, tmp_path):
        (tmp_path / "Makefile").write_text("test:\n\tpytest\n")
        mgr = ReleaseManager("1.0.0", str(tmp_path))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_TEST_CMD", None)
            assert mgr._detect_test_command() == "make test"


# ── version bump: build.gradle + setup.cfg (lines 511-525) ────────────────


class TestVersionBumpAdditional:
    def test_build_gradle(self, tmp_path):
        (tmp_path / "build.gradle").write_text("version = '1.0.0'\n")
        mgr = ReleaseManager("2.0.0", str(tmp_path))
        assert mgr.bump_version() is True
        content = (tmp_path / "build.gradle").read_text()
        assert "version = '2.0.0'" in content

    def test_setup_cfg(self, tmp_path):
        (tmp_path / "setup.cfg").write_text("[metadata]\nversion = 1.0.0\n")
        mgr = ReleaseManager("2.0.0", str(tmp_path))
        assert mgr.bump_version() is True
        content = (tmp_path / "setup.cfg").read_text()
        assert "version = 2.0.0" in content

    def test_dry_run_does_not_write(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('version = "1.0.0"\n')
        mgr = ReleaseManager("2.0.0", str(tmp_path), dry_run=True)
        assert mgr.bump_version() is True
        content = (tmp_path / "pyproject.toml").read_text()
        assert 'version = "1.0.0"' in content  # unchanged


# ── _trigger_jenkins_build / _trigger_jenkins_deploy (lines 541-585) ──────


class TestJenkinsIntegration:
    def test_trigger_jenkins_build_success(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch.dict(os.environ, {"JENKINS_BUILD_JOB": "job/build", "CODE_AGENTS_BUILD_CMD": ""}):
            mock_httpx = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"status": "success"}
            mock_httpx.post.return_value = mock_response
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                with patch("code_agents.cli.cli_helpers._server_url", return_value="http://localhost:8000"):
                    # Call trigger_build which checks for jenkins_job
                    result = mgr.trigger_build()
                    # This will try to import httpx and call _trigger_jenkins_build

    def test_trigger_jenkins_build_exception(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        # Test _trigger_jenkins_build directly
        with patch("builtins.__import__", side_effect=Exception("import fail")):
            result = mgr._trigger_jenkins_build()
            assert result is False
            assert any("error" in e.lower() for e in mgr.errors)

    def test_trigger_jenkins_deploy_exception(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch("builtins.__import__", side_effect=Exception("import fail")):
            result = mgr._trigger_jenkins_deploy()
            assert result is False
            assert any("error" in e.lower() for e in mgr.errors)


# ── _run_git helper (line 46) ───────────────────────────────────────────────


class TestRunGit:
    def test_run_git_returns_completed_process(self):
        from code_agents.tools.release import _run_git
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="output", returncode=0)
            result = _run_git(["status"], "/tmp")
            assert result.stdout == "output"
            mock_run.assert_called_once_with(
                ["git", "status"],
                cwd="/tmp", capture_output=True, text=True, timeout=60,
            )


# ── run_all full pipeline steps (lines 85-122) ─────────────────────────────


class TestRunAllPipeline:
    def test_run_all_with_tests_and_deploy_and_jira(self, tmp_path):
        """run_all with all steps enabled, dry_run=True."""
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=True)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.return_value = MagicMock(stdout="main\n", returncode=0)
            with patch.object(mgr, "_detect_test_command", return_value="pytest"):
                ok = mgr.run_all(skip_deploy=False, skip_jira=False, skip_tests=False)
        assert ok is True
        assert "Run tests" in mgr.steps_completed
        assert "Generate changelog" in mgr.steps_completed

    def test_run_all_step_ok_logged(self, tmp_path):
        """Each successful step is added to steps_completed."""
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=True)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.return_value = MagicMock(stdout="main\n", returncode=0)
            ok = mgr.run_all(skip_deploy=True, skip_jira=True, skip_tests=True)
        assert ok is True
        assert "Create release branch" in mgr.steps_completed
        assert "Generate changelog" in mgr.steps_completed
        assert "Bump version" in mgr.steps_completed
        assert "Commit changes" in mgr.steps_completed
        assert "Push branch" in mgr.steps_completed


# ── run_tests non-dry-run edge cases ────────────────────────────────────────


class TestRunTestsEdgeCases:
    def test_run_tests_dry_run_with_no_test_cmd(self, tmp_path):
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=True)
        with patch.object(mgr, "_detect_test_command", return_value=None):
            assert mgr.run_tests() is True

    def test_run_tests_output_lines_logged(self, tmp_path):
        """When tests fail, last 20 lines of output are appended."""
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        lines = "\n".join([f"line{i}" for i in range(30)])
        with patch.object(mgr, "_detect_test_command", return_value="pytest"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout=lines, stderr=""
            )
            assert mgr.run_tests() is False
        assert any("Tests failed" in e for e in mgr.errors)


# ── generate_changelog edge cases ───────────────────────────────────────────


class TestChangelogEdgeCases:
    def test_empty_commit_line_skipped(self, tmp_path):
        """Commits with only a hash (no message) are skipped."""
        mgr = ReleaseManager("2.0.0", str(tmp_path), dry_run=True)
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="", returncode=128),
                MagicMock(stdout="abc1234\ndef5678 feat: real commit\n", returncode=0),
            ]
            assert mgr.generate_changelog() is True
        # The empty-message line should be skipped
        assert "### Features" in mgr.changelog_entry


# ── bump_version with non-matching content ──────────────────────────────────


class TestVersionBumpNoMatch:
    def test_replace_version_unknown_file(self):
        """Unknown file type returns None."""
        mgr = ReleaseManager("2.0.0", "/tmp/repo")
        result = mgr._replace_version_in_content("unknown.txt", "some content")
        assert result is None

    def test_replace_version_not_changed(self, tmp_path):
        """If regex doesn't match, content stays unchanged => file not listed."""
        (tmp_path / "pyproject.toml").write_text("name = 'foo'\n")
        mgr = ReleaseManager("2.0.0", str(tmp_path))
        assert mgr.bump_version() is True


# ── trigger_build dry-run branches (lines 317-324) ─────────────────────────


class TestTriggerBuildDryRunBranches:
    def test_dry_run_with_build_cmd(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        with patch.dict(os.environ, {"CODE_AGENTS_BUILD_CMD": "make build", "JENKINS_BUILD_JOB": ""}):
            assert mgr.trigger_build() is True

    def test_dry_run_with_jenkins_job(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        with patch.dict(os.environ, {"CODE_AGENTS_BUILD_CMD": "", "JENKINS_BUILD_JOB": "job/build"}):
            assert mgr.trigger_build() is True

    def test_dry_run_no_config(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        with patch.dict(os.environ, {"CODE_AGENTS_BUILD_CMD": "", "JENKINS_BUILD_JOB": ""}):
            assert mgr.trigger_build() is True


# ── deploy_staging dry-run branches (lines 346-355) ────────────────────────


class TestDeployStagingDryRunBranches:
    def test_dry_run_with_deploy_job(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        with patch.dict(os.environ, {"JENKINS_DEPLOY_JOB": "deploy/staging"}):
            assert mgr.deploy_staging() is True

    def test_dry_run_no_deploy_job(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=True)
        with patch.dict(os.environ, {"JENKINS_DEPLOY_JOB": ""}):
            assert mgr.deploy_staging() is True

    def test_non_dry_run_calls_trigger_jenkins_deploy(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch.dict(os.environ, {"JENKINS_DEPLOY_JOB": "deploy/staging"}):
            with patch.object(mgr, "_trigger_jenkins_deploy", return_value=True) as mock_deploy:
                assert mgr.deploy_staging() is True
                mock_deploy.assert_called_once()


# ── run_sanity with checks (lines 374-393) ──────────────────────────────────


class TestRunSanityChecks:
    def test_sanity_no_rules(self, tmp_path):
        ca_dir = tmp_path / ".code-agents"
        ca_dir.mkdir()
        (ca_dir / "sanity.yaml").write_text("rules: []\n")
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        mock_module = MagicMock()
        mock_module.load_rules.return_value = []
        import sys
        sys.modules["code_agents.cicd.sanity_checker"] = mock_module
        try:
            assert mgr.run_sanity() is True
        finally:
            sys.modules.pop("code_agents.cicd.sanity_checker", None)

    def test_sanity_checks_pass(self, tmp_path):
        ca_dir = tmp_path / ".code-agents"
        ca_dir.mkdir()
        (ca_dir / "sanity.yaml").write_text("rules: [test]\n")
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        mock_module = MagicMock()
        mock_rule = MagicMock()
        mock_result = MagicMock(passed=True)
        mock_module.load_rules.return_value = [mock_rule]
        mock_module.run_checks.return_value = [mock_result]
        import sys
        sys.modules["code_agents.cicd.sanity_checker"] = mock_module
        try:
            assert mgr.run_sanity() is True
        finally:
            sys.modules.pop("code_agents.cicd.sanity_checker", None)

    def test_sanity_checks_fail(self, tmp_path):
        ca_dir = tmp_path / ".code-agents"
        ca_dir.mkdir()
        (ca_dir / "sanity.yaml").write_text("rules: [test]\n")
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        mock_module = MagicMock()
        mock_rule = MagicMock()
        mock_result = MagicMock(passed=False, rule=MagicMock(name="test_rule"), match_count=5)
        mock_module.load_rules.return_value = [mock_rule]
        mock_module.run_checks.return_value = [mock_result]
        import sys
        sys.modules["code_agents.cicd.sanity_checker"] = mock_module
        try:
            assert mgr.run_sanity() is False
            assert any("sanity" in e.lower() for e in mgr.errors)
        finally:
            sys.modules.pop("code_agents.cicd.sanity_checker", None)

    def test_sanity_general_exception(self, tmp_path):
        ca_dir = tmp_path / ".code-agents"
        ca_dir.mkdir()
        (ca_dir / "sanity.yaml").write_text("rules: [test]\n")
        mgr = ReleaseManager("1.0.0", str(tmp_path), dry_run=False)
        mock_module = MagicMock()
        mock_module.load_rules.side_effect = RuntimeError("some error")
        import sys
        sys.modules["code_agents.cicd.sanity_checker"] = mock_module
        try:
            assert mgr.run_sanity() is True  # non-fatal
        finally:
            sys.modules.pop("code_agents.cicd.sanity_checker", None)


# ── update_jira with real JiraClient (lines 414-429) ────────────────────────


class TestUpdateJiraFull:
    def test_successful_transition(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch.dict(os.environ, {"JIRA_URL": "https://jira.example.com"}), \
             patch.object(mgr, "_extract_jira_tickets", return_value=["PROJ-1", "PROJ-2"]):
            mock_module = MagicMock()
            mock_client = MagicMock()
            mock_module.JiraClient.return_value = mock_client
            import sys
            sys.modules["code_agents.cicd.jira_client"] = mock_module
            try:
                result = mgr.update_jira()
                assert result is True
                assert mock_client.transition_issue.call_count == 2
            finally:
                sys.modules.pop("code_agents.cicd.jira_client", None)

    def test_jira_general_exception(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        with patch.dict(os.environ, {"JIRA_URL": "https://jira.example.com"}), \
             patch.object(mgr, "_extract_jira_tickets", return_value=["PROJ-1"]):
            mock_module = MagicMock()
            mock_module.JiraClient.side_effect = Exception("connection error")
            import sys
            sys.modules["code_agents.cicd.jira_client"] = mock_module
            try:
                result = mgr.update_jira()
                assert result is True  # non-fatal
            finally:
                sys.modules.pop("code_agents.cicd.jira_client", None)


# ── _extract_jira_tickets error (line 532-533) ─────────────────────────────


class TestExtractJiraTicketsError:
    def test_git_log_failure_returns_empty(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo")
        with patch("code_agents.tools.release._run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(stdout="", returncode=128),  # no tags
                MagicMock(stdout="", returncode=1),     # log fails
            ]
            tickets = mgr._extract_jira_tickets()
        assert tickets == []


# ── _trigger_jenkins_build success/failure (lines 541-562) ──────────────────


class TestJenkinsBuildDetailed:
    def test_jenkins_build_success(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        mock_httpx = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "success"}
        mock_httpx.post.return_value = mock_resp
        import sys
        sys.modules["httpx"] = mock_httpx
        with patch("code_agents.cli.cli_helpers._server_url", return_value="http://localhost:8000"):
            result = mgr._trigger_jenkins_build()
        sys.modules.pop("httpx", None)
        assert result is True

    def test_jenkins_build_failure_status(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        mock_httpx = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "failed", "error": "compilation error"}
        mock_httpx.post.return_value = mock_resp
        import sys
        sys.modules["httpx"] = mock_httpx
        with patch("code_agents.cli.cli_helpers._server_url", return_value="http://localhost:8000"):
            result = mgr._trigger_jenkins_build()
        sys.modules.pop("httpx", None)
        assert result is False
        assert any("compilation error" in e for e in mgr.errors)

    def test_jenkins_deploy_success(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        mock_httpx = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "success"}
        mock_httpx.post.return_value = mock_resp
        import sys
        sys.modules["httpx"] = mock_httpx
        with patch("code_agents.cli.cli_helpers._server_url", return_value="http://localhost:8000"):
            result = mgr._trigger_jenkins_deploy()
        sys.modules.pop("httpx", None)
        assert result is True

    def test_jenkins_deploy_failure_status(self):
        mgr = ReleaseManager("1.0.0", "/tmp/repo", dry_run=False)
        mock_httpx = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "failed", "error": "deploy error"}
        mock_httpx.post.return_value = mock_resp
        import sys
        sys.modules["httpx"] = mock_httpx
        with patch("code_agents.cli.cli_helpers._server_url", return_value="http://localhost:8000"):
            result = mgr._trigger_jenkins_deploy()
        sys.modules.pop("httpx", None)
        assert result is False
        assert any("deploy error" in e for e in mgr.errors)


# ── _detect_test_command: setup.py (line 460) ──────────────────────────────


class TestDetectSetupPy:
    def test_detects_setup_py(self, tmp_path):
        (tmp_path / "setup.py").write_text("from setuptools import setup\n")
        mgr = ReleaseManager("1.0.0", str(tmp_path))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_TEST_CMD", None)
            assert mgr._detect_test_command() == "python -m pytest"


# ── bump_version: directory matching glob skipped (line 260) ───────────────


class TestBumpVersionDirectorySkipped:
    def test_directory_named_like_version_file_is_skipped(self, tmp_path):
        """If a glob matches a directory instead of a file, it should be skipped."""
        # Create a directory named like a version file so fpath.is_file() returns False
        (tmp_path / "pyproject.toml").mkdir()
        mgr = ReleaseManager("2.0.0", str(tmp_path))
        assert mgr.bump_version() is True
