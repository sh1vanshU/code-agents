"""Tests for chat_branch — conversation branching (fork, switch, merge)."""

import copy
import time
from unittest.mock import patch

import pytest

from code_agents.chat.chat_branch import BranchManager, _handle_branch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session():
    """Create a fresh session dict."""
    return {
        "id": "sess-001",
        "agent": "code-writer",
        "repo_path": "/tmp/test-repo",
        "title": "Test session",
        "created_at": time.time(),
        "updated_at": time.time(),
        "messages": [
            {"role": "user", "content": "Hello", "timestamp": time.time()},
            {"role": "assistant", "content": "Hi there!", "timestamp": time.time()},
            {"role": "user", "content": "Write code", "timestamp": time.time()},
            {"role": "assistant", "content": "def foo(): pass", "timestamp": time.time()},
        ],
    }


@pytest.fixture
def bm(session):
    """Create a BranchManager from a session."""
    return BranchManager(session)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestBranchManagerInit:
    """Tests for BranchManager initialization."""

    def test_creates_main_branch(self, session):
        bm = BranchManager(session)
        assert "main" in session["branches"]
        assert session["active_branch"] == "main"

    def test_main_branch_has_messages(self, bm, session):
        main = session["branches"]["main"]
        assert len(main["messages"]) == 4

    def test_idempotent_init(self, session):
        bm1 = BranchManager(session)
        bm2 = BranchManager(session)
        assert len(session["branches"]) == 1  # still just main

    def test_preserves_existing_branches(self, session):
        session["branches"] = {"main": {"messages": [], "created_at": 0, "parent": None, "fork_index": 0}}
        session["active_branch"] = "main"
        bm = BranchManager(session)
        assert len(session["branches"]) == 1


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestBranchProperties:
    """Tests for branch properties."""

    def test_active_branch_default(self, bm):
        assert bm.active_branch == "main"

    def test_messages_returns_active_branch(self, bm):
        assert len(bm.messages) == 4

    def test_set_messages(self, bm):
        bm.messages = [{"role": "user", "content": "new"}]
        assert len(bm.messages) == 1


# ---------------------------------------------------------------------------
# Create branch
# ---------------------------------------------------------------------------


class TestCreateBranch:
    """Tests for creating branches."""

    def test_create_named_branch(self, bm, session):
        name = bm.create_branch("experiment")
        assert name == "experiment"
        assert "experiment" in session["branches"]

    def test_create_auto_named_branch(self, bm, session):
        name = bm.create_branch()
        assert name.startswith("branch-")

    def test_branch_copies_messages(self, bm, session):
        bm.create_branch("copy-test")
        branch_msgs = session["branches"]["copy-test"]["messages"]
        assert len(branch_msgs) == 4
        # Ensure it's a deep copy
        branch_msgs.append({"role": "user", "content": "extra"})
        assert len(session["branches"]["main"]["messages"]) == 4

    def test_branch_records_parent(self, bm, session):
        bm.create_branch("child")
        assert session["branches"]["child"]["parent"] == "main"

    def test_branch_records_fork_index(self, bm, session):
        bm.create_branch("fork-test")
        assert session["branches"]["fork-test"]["fork_index"] == 4

    def test_switches_to_new_branch(self, bm):
        bm.create_branch("auto-switch")
        assert bm.active_branch == "auto-switch"

    def test_duplicate_name_raises(self, bm):
        bm.create_branch("dup")
        with pytest.raises(ValueError, match="already exists"):
            bm.create_branch("dup")

    def test_nested_branching(self, bm, session):
        bm.create_branch("level1")
        bm.add_message("user", "level1 msg")
        bm.create_branch("level2")
        assert session["branches"]["level2"]["parent"] == "level1"
        assert session["branches"]["level2"]["fork_index"] == 5  # 4 original + 1 added


# ---------------------------------------------------------------------------
# Add message
# ---------------------------------------------------------------------------


class TestAddMessage:
    """Tests for adding messages to branches."""

    def test_add_to_main(self, bm):
        bm.add_message("user", "new question")
        assert len(bm.messages) == 5
        assert bm.messages[-1]["content"] == "new question"

    def test_add_to_branch(self, bm):
        bm.create_branch("test-add")
        bm.add_message("user", "branch msg")
        assert len(bm.messages) == 5  # 4 from fork + 1 new
        # Main should still have 4
        bm.switch_branch("main")
        assert len(bm.messages) == 4

    def test_message_has_timestamp(self, bm):
        bm.add_message("user", "timed")
        assert "timestamp" in bm.messages[-1]


# ---------------------------------------------------------------------------
# Switch branch
# ---------------------------------------------------------------------------


class TestSwitchBranch:
    """Tests for switching branches."""

    def test_switch_success(self, bm):
        bm.create_branch("other")
        bm.switch_branch("main")
        assert bm.active_branch == "main"

    def test_switch_nonexistent(self, bm):
        assert bm.switch_branch("nope") is False
        assert bm.active_branch == "main"

    def test_switch_preserves_messages(self, bm):
        bm.create_branch("branch-a")
        bm.add_message("user", "A message")
        bm.switch_branch("main")
        assert len(bm.messages) == 4
        bm.switch_branch("branch-a")
        assert len(bm.messages) == 5


# ---------------------------------------------------------------------------
# Merge branch
# ---------------------------------------------------------------------------


class TestMergeBranch:
    """Tests for merging branches."""

    def test_merge_replaces_main(self, bm, session):
        bm.create_branch("better")
        bm.add_message("user", "extra in better")
        bm.add_message("assistant", "response in better")
        bm.merge_branch("better")
        assert bm.active_branch == "main"
        assert len(bm.messages) == 6  # 4 + 2

    def test_merge_removes_branch(self, bm, session):
        bm.create_branch("temp")
        bm.merge_branch("temp")
        assert "temp" not in session["branches"]

    def test_merge_nonexistent(self, bm):
        assert bm.merge_branch("nope") is False

    def test_merge_main_is_noop(self, bm):
        assert bm.merge_branch("main") is True

    def test_merge_syncs_session_messages(self, bm, session):
        bm.create_branch("sync-test")
        bm.add_message("user", "synced")
        bm.merge_branch("sync-test")
        assert session["messages"][-1]["content"] == "synced"


# ---------------------------------------------------------------------------
# Delete branch
# ---------------------------------------------------------------------------


class TestDeleteBranch:
    """Tests for deleting branches."""

    def test_delete_branch(self, bm, session):
        bm.create_branch("deleteme")
        bm.switch_branch("main")
        assert bm.delete_branch("deleteme") is True
        assert "deleteme" not in session["branches"]

    def test_cannot_delete_main(self, bm):
        assert bm.delete_branch("main") is False

    def test_cannot_delete_active(self, bm):
        bm.create_branch("active")
        assert bm.delete_branch("active") is False

    def test_delete_nonexistent(self, bm):
        assert bm.delete_branch("ghost") is False


# ---------------------------------------------------------------------------
# List branches
# ---------------------------------------------------------------------------


class TestListBranches:
    """Tests for listing branches."""

    def test_list_initial(self, bm):
        branches = bm.list_branches()
        assert len(branches) == 1
        assert branches[0]["name"] == "main"
        assert branches[0]["active"] is True

    def test_list_multiple(self, bm):
        bm.create_branch("a")
        bm.create_branch("b")
        branches = bm.list_branches()
        assert len(branches) == 3
        names = {b["name"] for b in branches}
        assert names == {"main", "a", "b"}

    def test_list_shows_active(self, bm):
        bm.create_branch("x")
        branches = bm.list_branches()
        active = [b for b in branches if b["active"]]
        assert len(active) == 1
        assert active[0]["name"] == "x"

    def test_list_includes_metadata(self, bm):
        bm.create_branch("meta")
        branches = bm.list_branches()
        meta = next(b for b in branches if b["name"] == "meta")
        assert "messages" in meta
        assert "parent" in meta
        assert "fork_index" in meta
        assert "created_at" in meta


# ---------------------------------------------------------------------------
# Get session
# ---------------------------------------------------------------------------


class TestGetSession:
    """Tests for getting session back."""

    def test_returns_session_dict(self, bm, session):
        result = bm.get_session()
        assert result is session
        assert "branches" in result
        assert "active_branch" in result


# ---------------------------------------------------------------------------
# Slash command handler
# ---------------------------------------------------------------------------


class TestHandleBranch:
    """Tests for the /branch slash command handler."""

    def test_create_branch_via_slash(self, session, capsys):
        state = {"session": session}
        result = _handle_branch("/branch", "test-slash", state, "http://localhost")
        assert result is None
        assert "test-slash" in state["session"]["branches"]

    def test_list_branches_via_slash(self, session, capsys):
        state = {"session": session}
        _handle_branch("/branch", "x", state, "http://localhost")
        _handle_branch("/branches", "", state, "http://localhost")
        out = capsys.readouterr().out
        assert "x" in out or "main" in out

    def test_switch_branch_via_slash(self, session):
        state = {"session": session, "messages": []}
        _handle_branch("/branch", "sw", state, "http://localhost")
        _handle_branch("/switch", "main", state, "http://localhost")
        assert state["session"]["active_branch"] == "main"

    def test_merge_branch_via_slash(self, session):
        state = {"session": session, "messages": []}
        _handle_branch("/branch", "mrg", state, "http://localhost")
        _handle_branch("/merge", "mrg", state, "http://localhost")
        assert state["session"]["active_branch"] == "main"

    def test_switch_missing_arg(self, session, capsys):
        state = {"session": session}
        _handle_branch("/switch", "", state, "http://localhost")
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_merge_missing_arg(self, session, capsys):
        state = {"session": session}
        _handle_branch("/merge", "", state, "http://localhost")
        out = capsys.readouterr().out
        assert "Usage" in out
