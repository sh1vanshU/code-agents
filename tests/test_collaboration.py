"""Tests for collaboration — live session sharing and WebSocket communication."""

import json
import time
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.domain.collaboration import (
    CollabMessage,
    CollabSession,
    CollabStore,
    Participant,
    _generate_join_code,
    broadcast,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_store():
    """Reset the CollabStore between tests."""
    CollabStore._sessions.clear()
    CollabStore._connections.clear()
    yield
    CollabStore._sessions.clear()
    CollabStore._connections.clear()


# ---------------------------------------------------------------------------
# Join code generation
# ---------------------------------------------------------------------------


class TestJoinCodeGeneration:
    """Tests for join code generation."""

    def test_format(self):
        code = _generate_join_code()
        parts = code.split("-")
        assert len(parts) == 3
        assert parts[0].isalpha()
        assert parts[1].isalpha()
        assert parts[2].isdigit()

    def test_uniqueness(self):
        codes = {_generate_join_code() for _ in range(50)}
        # With 24*24*90 = 51840 combos, 50 should be mostly unique
        assert len(codes) >= 30


# ---------------------------------------------------------------------------
# Participant
# ---------------------------------------------------------------------------


class TestParticipant:
    """Tests for Participant dataclass."""

    def test_defaults(self):
        p = Participant(id="p1")
        assert p.name == "Anonymous"
        assert p.role == "viewer"
        assert p.is_typing is False

    def test_custom(self):
        p = Participant(id="h1", name="Alice", role="host")
        assert p.name == "Alice"
        assert p.role == "host"


# ---------------------------------------------------------------------------
# CollabMessage
# ---------------------------------------------------------------------------


class TestCollabMessage:
    """Tests for CollabMessage dataclass."""

    def test_defaults(self):
        m = CollabMessage(type="chat")
        assert m.sender_id == ""
        assert m.content == ""
        assert m.timestamp == 0.0

    def test_with_content(self):
        m = CollabMessage(type="chat", sender_id="p1", content="Hello", timestamp=time.time())
        assert m.content == "Hello"

    def test_serializable(self):
        m = CollabMessage(type="system", content="test")
        data = asdict(m)
        assert json.dumps(data)  # should not raise


# ---------------------------------------------------------------------------
# CollabStore — create
# ---------------------------------------------------------------------------


class TestCollabStoreCreate:
    """Tests for creating collaboration sessions."""

    def test_create_session(self):
        session = CollabStore.create_session("Alice")
        assert session.join_code
        assert session.host_id
        assert len(session.participants) == 1
        assert session.participants[0].name == "Alice"
        assert session.participants[0].role == "host"
        assert session.status == "active"

    def test_create_with_metadata(self):
        session = CollabStore.create_session(
            "Bob", session_id="s123", agent="code-writer", repo_path="/tmp/repo"
        )
        assert session.session_id == "s123"
        assert session.agent == "code-writer"
        assert session.repo_path == "/tmp/repo"

    def test_unique_join_codes(self):
        codes = set()
        for i in range(20):
            session = CollabStore.create_session(f"User{i}")
            codes.add(session.join_code)
        assert len(codes) == 20


# ---------------------------------------------------------------------------
# CollabStore — get
# ---------------------------------------------------------------------------


class TestCollabStoreGet:
    """Tests for getting collaboration sessions."""

    def test_get_existing(self):
        session = CollabStore.create_session("Alice")
        found = CollabStore.get_session(session.join_code)
        assert found is not None
        assert found.join_code == session.join_code

    def test_get_nonexistent(self):
        assert CollabStore.get_session("nope-code-99") is None


# ---------------------------------------------------------------------------
# CollabStore — join
# ---------------------------------------------------------------------------


class TestCollabStoreJoin:
    """Tests for joining sessions."""

    def test_join_session(self):
        session = CollabStore.create_session("Host")
        participant = CollabStore.join_session(session.join_code, "Peer")
        assert participant is not None
        assert participant.name == "Peer"
        assert participant.role == "editor"
        assert len(session.participants) == 2

    def test_join_nonexistent(self):
        assert CollabStore.join_session("nope-nope-99") is None

    def test_join_ended_session(self):
        session = CollabStore.create_session("Host")
        CollabStore.end_session(session.join_code)
        assert CollabStore.join_session(session.join_code) is None

    def test_multiple_joins(self):
        session = CollabStore.create_session("Host")
        CollabStore.join_session(session.join_code, "Peer1")
        CollabStore.join_session(session.join_code, "Peer2")
        assert len(session.participants) == 3


# ---------------------------------------------------------------------------
# CollabStore — leave
# ---------------------------------------------------------------------------


class TestCollabStoreLeave:
    """Tests for leaving sessions."""

    def test_leave_peer(self):
        session = CollabStore.create_session("Host")
        peer = CollabStore.join_session(session.join_code, "Peer")
        assert CollabStore.leave_session(session.join_code, peer.id) is True
        assert len(session.participants) == 1

    def test_leave_host_ends_session(self):
        session = CollabStore.create_session("Host")
        CollabStore.leave_session(session.join_code, session.host_id)
        assert session.status == "ended"

    def test_leave_nonexistent(self):
        assert CollabStore.leave_session("nope-nope-99", "p1") is False


# ---------------------------------------------------------------------------
# CollabStore — end
# ---------------------------------------------------------------------------


class TestCollabStoreEnd:
    """Tests for ending sessions."""

    def test_end_session(self):
        session = CollabStore.create_session("Host")
        assert CollabStore.end_session(session.join_code) is True
        assert session.status == "ended"

    def test_end_nonexistent(self):
        assert CollabStore.end_session("nope-nope-99") is False

    def test_end_clears_connections(self):
        session = CollabStore.create_session("Host")
        ws = MagicMock()
        CollabStore.add_connection(session.join_code, ws)
        CollabStore.end_session(session.join_code)
        assert CollabStore.get_connections(session.join_code) == []


# ---------------------------------------------------------------------------
# CollabStore — connections
# ---------------------------------------------------------------------------


class TestCollabStoreConnections:
    """Tests for WebSocket connection management."""

    def test_add_connection(self):
        session = CollabStore.create_session("Host")
        ws = MagicMock()
        CollabStore.add_connection(session.join_code, ws)
        assert ws in CollabStore.get_connections(session.join_code)

    def test_remove_connection(self):
        session = CollabStore.create_session("Host")
        ws = MagicMock()
        CollabStore.add_connection(session.join_code, ws)
        CollabStore.remove_connection(session.join_code, ws)
        assert ws not in CollabStore.get_connections(session.join_code)

    def test_get_empty_connections(self):
        assert CollabStore.get_connections("nonexistent") == []

    def test_multiple_connections(self):
        session = CollabStore.create_session("Host")
        ws1, ws2 = MagicMock(), MagicMock()
        CollabStore.add_connection(session.join_code, ws1)
        CollabStore.add_connection(session.join_code, ws2)
        conns = CollabStore.get_connections(session.join_code)
        assert len(conns) == 2


# ---------------------------------------------------------------------------
# CollabStore — messages
# ---------------------------------------------------------------------------


class TestCollabStoreMessages:
    """Tests for message storage."""

    def test_add_message(self):
        session = CollabStore.create_session("Host")
        msg = CollabMessage(type="chat", content="Hello")
        CollabStore.add_message(session.join_code, msg)
        assert len(session.messages) == 1

    def test_add_multiple_messages(self):
        session = CollabStore.create_session("Host")
        for i in range(5):
            CollabStore.add_message(session.join_code, CollabMessage(type="chat", content=f"msg{i}"))
        assert len(session.messages) == 5

    def test_add_to_nonexistent(self):
        # Should not raise
        CollabStore.add_message("nope", CollabMessage(type="chat"))


# ---------------------------------------------------------------------------
# CollabStore — list active
# ---------------------------------------------------------------------------


class TestCollabStoreListActive:
    """Tests for listing active sessions."""

    def test_list_empty(self):
        assert CollabStore.list_active() == []

    def test_list_active(self):
        CollabStore.create_session("A")
        CollabStore.create_session("B")
        assert len(CollabStore.list_active()) == 2

    def test_list_excludes_ended(self):
        s = CollabStore.create_session("A")
        CollabStore.create_session("B")
        CollabStore.end_session(s.join_code)
        assert len(CollabStore.list_active()) == 1


# ---------------------------------------------------------------------------
# CollabStore — cleanup
# ---------------------------------------------------------------------------


class TestCollabStoreCleanup:
    """Tests for stale session cleanup."""

    def test_cleanup_fresh(self):
        CollabStore.create_session("A")
        removed = CollabStore.cleanup_stale(max_age=7200)
        assert removed == 0

    def test_cleanup_stale(self):
        session = CollabStore.create_session("A")
        # Backdate
        session.created_at = "2020-01-01T00:00:00"
        removed = CollabStore.cleanup_stale(max_age=1)
        assert removed == 1
        assert CollabStore.get_session(session.join_code) is None


# ---------------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------------


class TestBroadcast:
    """Tests for broadcast function."""

    @pytest.mark.asyncio
    async def test_broadcast_to_connections(self):
        session = CollabStore.create_session("Host")
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        CollabStore.add_connection(session.join_code, ws1)
        CollabStore.add_connection(session.join_code, ws2)

        msg = CollabMessage(type="chat", content="Hello all")
        sent = await broadcast(session.join_code, msg)
        assert sent == 2
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_stores_message(self):
        session = CollabStore.create_session("Host")
        msg = CollabMessage(type="system", content="test")
        await broadcast(session.join_code, msg)
        assert len(session.messages) == 1

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        session = CollabStore.create_session("Host")
        dead_ws = AsyncMock()
        dead_ws.send_text.side_effect = Exception("connection closed")
        live_ws = AsyncMock()

        CollabStore.add_connection(session.join_code, dead_ws)
        CollabStore.add_connection(session.join_code, live_ws)

        msg = CollabMessage(type="chat", content="test")
        sent = await broadcast(session.join_code, msg)
        assert sent == 1
        # Dead connection should be removed
        assert dead_ws not in CollabStore.get_connections(session.join_code)

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self):
        session = CollabStore.create_session("Host")
        msg = CollabMessage(type="chat", content="echo")
        sent = await broadcast(session.join_code, msg)
        assert sent == 0


# ---------------------------------------------------------------------------
# Router creation
# ---------------------------------------------------------------------------


class TestCollabRouter:
    """Tests for router factory."""

    def test_create_router(self):
        from code_agents.domain.collaboration import create_collab_router
        router = create_collab_router()
        assert router is not None
        # Check routes exist
        paths = [r.path for r in router.routes]
        assert "/ws/collab/{join_code}" in paths
        assert "/api/collab/create" in paths
        assert "/api/collab/{join_code}" in paths
        assert "/api/collab" in paths
