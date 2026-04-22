"""Tests for session_scratchpad — per-session key-value store in /tmp."""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.agent_system.session_scratchpad import (
    REMEMBER_RE,
    SessionScratchpad,
    extract_remember_tags,
    strip_remember_tags,
)


@pytest.fixture
def tmp_base(tmp_path):
    """Override SCRATCHPAD_BASE to use pytest tmp_path."""
    with patch("code_agents.agent_system.session_scratchpad.SCRATCHPAD_BASE", tmp_path):
        yield tmp_path


class TestSessionScratchpad:
    """Tests for SessionScratchpad class."""

    def test_set_and_get(self, tmp_base):
        sp = SessionScratchpad("sess-001", "jenkins-cicd")
        sp.set("branch", "main")
        assert sp.get("branch") == "main"

    def test_get_missing_key(self, tmp_base):
        sp = SessionScratchpad("sess-002", "jenkins-cicd")
        assert sp.get("nonexistent") is None

    def test_overwrite_semantics(self, tmp_base):
        sp = SessionScratchpad("sess-003", "jenkins-cicd")
        sp.set("branch", "dev")
        sp.set("branch", "main")
        assert sp.get("branch") == "main"

    def test_get_all(self, tmp_base):
        sp = SessionScratchpad("sess-004", "jenkins-cicd")
        sp.set("branch", "main")
        sp.set("repo", "pg-acquiring-biz")
        sp.set("build_job", "pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz")
        facts = sp.get_all()
        assert facts == {
            "branch": "main",
            "repo": "pg-acquiring-biz",
            "build_job": "pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz",
        }

    def test_clear(self, tmp_base):
        sp = SessionScratchpad("sess-005", "jenkins-cicd")
        sp.set("branch", "main")
        sp.set("repo", "pg-acquiring-biz")
        sp.clear()
        assert sp.get_all() == {}
        assert sp.get("branch") is None

    def test_persistence_across_instances(self, tmp_base):
        """Data survives creating a new SessionScratchpad with same session_id."""
        sp1 = SessionScratchpad("sess-006", "jenkins-cicd")
        sp1.set("branch", "main")
        sp1.set("image_tag", "1.2.3-abc")

        sp2 = SessionScratchpad("sess-006", "jenkins-cicd")
        assert sp2.get("branch") == "main"
        assert sp2.get("image_tag") == "1.2.3-abc"

    def test_format_for_prompt_empty(self, tmp_base):
        sp = SessionScratchpad("sess-007", "jenkins-cicd")
        assert sp.format_for_prompt() == ""

    def test_format_for_prompt_with_facts(self, tmp_base):
        sp = SessionScratchpad("sess-008", "jenkins-cicd")
        sp.set("branch", "main")
        sp.set("repo", "pg-acquiring-biz")

        prompt = sp.format_for_prompt()
        assert "[Session Memory" in prompt
        assert "branch: main" in prompt
        assert "repo: pg-acquiring-biz" in prompt
        assert "do NOT re-fetch" in prompt
        assert "[REMEMBER:key=value]" in prompt

    def test_strip_whitespace_on_set(self, tmp_base):
        sp = SessionScratchpad("sess-009", "jenkins-cicd")
        sp.set("branch", "  main  ")
        assert sp.get("branch") == "main"

    def test_json_file_structure(self, tmp_base):
        sp = SessionScratchpad("sess-010", "jenkins-cicd")
        sp.set("branch", "main")

        state_file = tmp_base / "sess-010" / "state.json"
        assert state_file.exists()

        data = json.loads(state_file.read_text())
        assert data["agent"] == "jenkins-cicd"
        assert data["facts"]["branch"] == "main"
        assert "updated" in data


class TestCleanupStale:
    """Tests for cleanup_stale()."""

    def test_cleanup_old_sessions(self, tmp_base):
        # Create a stale session (updated 2 hours ago)
        stale_dir = tmp_base / "stale-sess"
        stale_dir.mkdir()
        (stale_dir / "state.json").write_text(json.dumps({
            "agent": "jenkins-cicd",
            "updated": time.time() - 7200,  # 2 hours ago
            "facts": {"branch": "old"},
        }))

        # Create a fresh session
        fresh_dir = tmp_base / "fresh-sess"
        fresh_dir.mkdir()
        (fresh_dir / "state.json").write_text(json.dumps({
            "agent": "jenkins-cicd",
            "updated": time.time(),
            "facts": {"branch": "new"},
        }))

        cleaned = SessionScratchpad.cleanup_stale(max_age=3600)
        assert cleaned == 1
        assert not stale_dir.exists()
        assert fresh_dir.exists()

    def test_cleanup_corrupted_sessions(self, tmp_base):
        bad_dir = tmp_base / "bad-sess"
        bad_dir.mkdir()
        (bad_dir / "state.json").write_text("not json")

        cleaned = SessionScratchpad.cleanup_stale()
        assert cleaned == 1
        assert not bad_dir.exists()

    def test_cleanup_empty_dirs(self, tmp_base):
        empty_dir = tmp_base / "empty-sess"
        empty_dir.mkdir()

        cleaned = SessionScratchpad.cleanup_stale()
        assert cleaned == 1
        assert not empty_dir.exists()

    def test_cleanup_no_base_dir(self):
        with patch("code_agents.agent_system.session_scratchpad.SCRATCHPAD_BASE", Path("/tmp/nonexistent-path-xyz")):
            cleaned = SessionScratchpad.cleanup_stale()
            assert cleaned == 0


class TestRememberTagExtraction:
    """Tests for [REMEMBER:key=value] regex and helpers."""

    def test_basic_extraction(self):
        text = "Found branch [REMEMBER:branch=main] on repo"
        pairs = extract_remember_tags(text)
        assert pairs == [("branch", "main")]

    def test_multiple_tags(self):
        text = "[REMEMBER:branch=dev_integration] [REMEMBER:repo=pg-acquiring-biz]"
        pairs = extract_remember_tags(text)
        assert pairs == [("branch", "dev_integration"), ("repo", "pg-acquiring-biz")]

    def test_complex_values(self):
        text = "[REMEMBER:build_job=pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz]"
        pairs = extract_remember_tags(text)
        assert pairs == [("build_job", "pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz")]

    def test_image_tag_value(self):
        text = "[REMEMBER:image_tag=1.2.3-abc123]"
        pairs = extract_remember_tags(text)
        assert pairs == [("image_tag", "1.2.3-abc123")]

    def test_build_number(self):
        text = "[REMEMBER:build_number=#854]"
        pairs = extract_remember_tags(text)
        assert pairs == [("build_number", "#854")]

    def test_no_tags(self):
        text = "Just a normal response with no tags"
        pairs = extract_remember_tags(text)
        assert pairs == []

    def test_strip_tags(self):
        text = "Branch: main [REMEMBER:branch=main] — found it"
        stripped = strip_remember_tags(text)
        assert stripped == "Branch: main  — found it"

    def test_strip_multiple_tags(self):
        text = "[REMEMBER:branch=main] Repo [REMEMBER:repo=pg-acq] done"
        stripped = strip_remember_tags(text)
        assert stripped == " Repo  done"

    def test_strip_no_tags(self):
        text = "No tags here"
        assert strip_remember_tags(text) == text

    def test_regex_rejects_invalid_keys(self):
        """Keys must start with letter or underscore."""
        text = "[REMEMBER:123bad=value]"
        pairs = extract_remember_tags(text)
        assert pairs == []

    def test_regex_allows_underscores(self):
        text = "[REMEMBER:build_params=branch (String), java_version (Choice)]"
        pairs = extract_remember_tags(text)
        assert pairs == [("build_params", "branch (String), java_version (Choice)")]

    def test_tag_in_multiline_response(self):
        text = """Fetching branch and searching for job.

```bash
curl -sS http://127.0.0.1:8000/git/current-branch
```

Branch: dev_integration_foundry_v2_qa4 [REMEMBER:branch=dev_integration_foundry_v2_qa4]
Repo: pg-acquiring-biz [REMEMBER:repo=pg-acquiring-biz]"""
        pairs = extract_remember_tags(text)
        assert len(pairs) == 2
        assert ("branch", "dev_integration_foundry_v2_qa4") in pairs
        assert ("repo", "pg-acquiring-biz") in pairs


class TestIntegrationFlow:
    """Test the full flow: set values, format prompt, read back."""

    def test_build_then_deploy_flow(self, tmp_base):
        session_id = "flow-001"

        # Turn 1: agent discovers branch and repo
        sp = SessionScratchpad(session_id, "jenkins-cicd")
        response1 = "Branch: main [REMEMBER:branch=main] Repo: pg-acq [REMEMBER:repo=pg-acquiring-biz]"
        for key, val in extract_remember_tags(response1):
            sp.set(key, val)

        # Turn 2: agent discovers build job
        sp2 = SessionScratchpad(session_id, "jenkins-cicd")
        assert sp2.get("branch") == "main"  # persisted from turn 1
        response2 = "Found job [REMEMBER:build_job=pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz]"
        for key, val in extract_remember_tags(response2):
            sp2.set(key, val)

        # Turn 3: prompt should include all facts
        sp3 = SessionScratchpad(session_id, "jenkins-cicd")
        prompt = sp3.format_for_prompt()
        assert "branch: main" in prompt
        assert "repo: pg-acquiring-biz" in prompt
        assert "build_job: pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz" in prompt

        # Turn 4: build succeeds, add results
        sp3.set("build_number", "#854")
        sp3.set("build_result", "SUCCESS")
        sp3.set("image_tag", "1.2.3-abc123")

        # Turn 5: deploy — all values available
        sp4 = SessionScratchpad(session_id, "jenkins-cicd")
        all_facts = sp4.get_all()
        assert all_facts["image_tag"] == "1.2.3-abc123"
        assert all_facts["branch"] == "main"
        assert all_facts["build_result"] == "SUCCESS"

    def test_user_changes_branch(self, tmp_base):
        """User says 'build on main' when scratchpad has different branch."""
        session_id = "flow-002"

        sp = SessionScratchpad(session_id, "jenkins-cicd")
        sp.set("branch", "dev_integration")
        sp.set("repo", "pg-acquiring-biz")
        sp.set("build_job", "pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz")

        # Agent confirms and overwrites branch
        sp.set("branch", "main")
        assert sp.get("branch") == "main"
        # Other facts unchanged
        assert sp.get("repo") == "pg-acquiring-biz"
        assert sp.get("build_job") == "pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz"

    def test_agent_switch_clears(self, tmp_base):
        """Switching agent clears the scratchpad."""
        session_id = "flow-003"

        sp = SessionScratchpad(session_id, "jenkins-cicd")
        sp.set("branch", "main")
        sp.set("build_job", "some-job")

        # Switch to code-writer
        sp_new = SessionScratchpad(session_id, "code-writer")
        sp_new.clear()

        # Verify cleared
        sp_check = SessionScratchpad(session_id, "code-writer")
        assert sp_check.get_all() == {}
