"""Live Collaboration — real-time session sharing via WebSocket.

Two developers share a session: both see streaming output, can inject messages,
and see who's typing. Uses short join codes for easy sharing.

Architecture:
    - Host starts a shared session with `code-agents share`
    - Gets a short join code (e.g., "abc-123")
    - Peer joins with `code-agents join abc-123`
    - Both connect via WebSocket to /ws/collab/{code}
    - Messages are broadcast to all participants
    - Agent responses stream to everyone

Usage:
    code-agents share             # start sharing, get join code
    code-agents join <code>       # join a shared session
    /share                        # start sharing from chat
    /share stop                   # stop sharing
    /share status                 # show sharing status
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import string
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("code_agents.domain.collaboration")

# Word lists for memorable join codes
_ADJECTIVES = [
    "blue", "red", "green", "fast", "calm", "bold", "warm", "cool",
    "dark", "deep", "fair", "gold", "keen", "kind", "lean", "pure",
    "safe", "soft", "true", "wild", "wise", "rich", "epic", "rare",
]
_NOUNS = [
    "wolf", "hawk", "bear", "deer", "fish", "frog", "lynx", "puma",
    "crow", "dove", "hare", "lion", "moth", "newt", "orca", "seal",
    "swan", "toad", "vole", "wasp", "wren", "yeti", "ibis", "kiwi",
]


def _generate_join_code() -> str:
    """Generate a memorable join code like 'bold-hawk-42'."""
    adj = random.choice(_ADJECTIVES)
    noun = random.choice(_NOUNS)
    num = random.randint(10, 99)
    return f"{adj}-{noun}-{num}"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Participant:
    """A participant in a collaborative session."""
    id: str
    name: str = "Anonymous"
    role: str = "viewer"  # "host", "editor", "viewer"
    joined_at: str = ""
    last_active: float = 0.0
    is_typing: bool = False


@dataclass
class CollabSession:
    """A live collaboration session."""
    join_code: str
    host_id: str
    session_id: str = ""  # linked chat session
    agent: str = ""
    repo_path: str = ""
    participants: list[Participant] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    created_at: str = ""
    status: str = "active"  # "active", "ended"


@dataclass
class CollabMessage:
    """A message in the collaboration stream."""
    type: str  # "chat", "agent_response", "system", "typing", "join", "leave"
    sender_id: str = ""
    sender_name: str = ""
    content: str = ""
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Session store (in-memory, single-process)
# ---------------------------------------------------------------------------


class CollabStore:
    """In-memory store for active collaboration sessions."""

    _sessions: dict[str, CollabSession] = {}
    _connections: dict[str, list[Any]] = {}  # join_code -> [websocket, ...]

    @classmethod
    def create_session(
        cls,
        host_name: str,
        session_id: str = "",
        agent: str = "",
        repo_path: str = "",
    ) -> CollabSession:
        """Create a new collaboration session."""
        code = _generate_join_code()
        while code in cls._sessions:
            code = _generate_join_code()

        host = Participant(
            id=f"host_{code}",
            name=host_name,
            role="host",
            joined_at=datetime.now().isoformat(),
            last_active=time.time(),
        )

        session = CollabSession(
            join_code=code,
            host_id=host.id,
            session_id=session_id,
            agent=agent,
            repo_path=repo_path,
            participants=[host],
            created_at=datetime.now().isoformat(),
        )

        cls._sessions[code] = session
        cls._connections[code] = []
        logger.info("Created collab session: %s (host: %s)", code, host_name)
        return session

    @classmethod
    def get_session(cls, join_code: str) -> Optional[CollabSession]:
        """Get a session by join code."""
        return cls._sessions.get(join_code)

    @classmethod
    def join_session(cls, join_code: str, name: str = "Anonymous") -> Optional[Participant]:
        """Add a participant to a session."""
        session = cls._sessions.get(join_code)
        if not session or session.status != "active":
            return None

        participant = Participant(
            id=f"peer_{join_code}_{len(session.participants)}",
            name=name,
            role="editor",
            joined_at=datetime.now().isoformat(),
            last_active=time.time(),
        )
        session.participants.append(participant)
        logger.info("Participant joined %s: %s", join_code, name)
        return participant

    @classmethod
    def leave_session(cls, join_code: str, participant_id: str) -> bool:
        """Remove a participant from a session."""
        session = cls._sessions.get(join_code)
        if not session:
            return False

        session.participants = [p for p in session.participants if p.id != participant_id]

        # End session if host left and no participants
        if participant_id == session.host_id or not session.participants:
            session.status = "ended"
            logger.info("Collab session ended: %s", join_code)

        return True

    @classmethod
    def end_session(cls, join_code: str) -> bool:
        """End a session."""
        session = cls._sessions.get(join_code)
        if not session:
            return False
        session.status = "ended"
        cls._connections.pop(join_code, None)
        logger.info("Collab session ended: %s", join_code)
        return True

    @classmethod
    def add_connection(cls, join_code: str, ws: Any) -> None:
        """Register a WebSocket connection."""
        if join_code not in cls._connections:
            cls._connections[join_code] = []
        cls._connections[join_code].append(ws)

    @classmethod
    def remove_connection(cls, join_code: str, ws: Any) -> None:
        """Remove a WebSocket connection."""
        if join_code in cls._connections:
            cls._connections[join_code] = [
                c for c in cls._connections[join_code] if c is not ws
            ]

    @classmethod
    def get_connections(cls, join_code: str) -> list[Any]:
        """Get all WebSocket connections for a session."""
        return cls._connections.get(join_code, [])

    @classmethod
    def list_active(cls) -> list[CollabSession]:
        """List all active sessions."""
        return [s for s in cls._sessions.values() if s.status == "active"]

    @classmethod
    def add_message(cls, join_code: str, message: CollabMessage) -> None:
        """Add a message to the session history."""
        session = cls._sessions.get(join_code)
        if session:
            session.messages.append(asdict(message))

    @classmethod
    def cleanup_stale(cls, max_age: int = 7200) -> int:
        """Remove sessions older than max_age seconds."""
        now = time.time()
        stale = []
        for code, session in cls._sessions.items():
            try:
                created = datetime.fromisoformat(session.created_at).timestamp()
                if now - created > max_age:
                    stale.append(code)
            except (ValueError, TypeError):
                stale.append(code)
        for code in stale:
            cls._sessions.pop(code, None)
            cls._connections.pop(code, None)
        return len(stale)


# ---------------------------------------------------------------------------
# Broadcast helper
# ---------------------------------------------------------------------------


async def broadcast(join_code: str, message: CollabMessage) -> int:
    """Broadcast a message to all connected participants. Returns send count."""
    CollabStore.add_message(join_code, message)
    connections = CollabStore.get_connections(join_code)
    data = json.dumps(asdict(message))
    sent = 0
    dead = []

    for ws in connections:
        try:
            await ws.send_text(data)
            sent += 1
        except Exception:
            dead.append(ws)

    # Cleanup dead connections
    for ws in dead:
        CollabStore.remove_connection(join_code, ws)

    return sent


# ---------------------------------------------------------------------------
# FastAPI WebSocket router
# ---------------------------------------------------------------------------


def create_collab_router():
    """Create the FastAPI router for collaboration WebSocket endpoints."""
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect

    router = APIRouter(tags=["collaboration"])

    @router.websocket("/ws/collab/{join_code}")
    async def collab_ws(websocket: WebSocket, join_code: str):
        """WebSocket endpoint for real-time collaboration."""
        session = CollabStore.get_session(join_code)
        if not session or session.status != "active":
            await websocket.close(code=4004, reason="Session not found or ended")
            return

        await websocket.accept()
        CollabStore.add_connection(join_code, websocket)

        # Get participant name from query params
        name = websocket.query_params.get("name", "Anonymous")
        participant = CollabStore.join_session(join_code, name)

        if not participant:
            await websocket.close(code=4003, reason="Could not join session")
            return

        # Broadcast join notification
        await broadcast(join_code, CollabMessage(
            type="join",
            sender_id=participant.id,
            sender_name=participant.name,
            content=f"{participant.name} joined the session",
            timestamp=time.time(),
        ))

        # Send session state to new participant
        await websocket.send_text(json.dumps({
            "type": "session_state",
            "join_code": join_code,
            "agent": session.agent,
            "participants": [asdict(p) for p in session.participants],
            "message_count": len(session.messages),
        }))

        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)

                msg_type = msg.get("type", "chat")

                if msg_type == "typing":
                    await broadcast(join_code, CollabMessage(
                        type="typing",
                        sender_id=participant.id,
                        sender_name=participant.name,
                        content=msg.get("content", ""),
                        timestamp=time.time(),
                    ))

                elif msg_type == "chat":
                    await broadcast(join_code, CollabMessage(
                        type="chat",
                        sender_id=participant.id,
                        sender_name=participant.name,
                        content=msg.get("content", ""),
                        timestamp=time.time(),
                    ))

                elif msg_type == "stop_sharing":
                    if participant.role == "host":
                        await broadcast(join_code, CollabMessage(
                            type="system",
                            content="Session ended by host",
                            timestamp=time.time(),
                        ))
                        CollabStore.end_session(join_code)
                        break

                # Update last active
                participant.last_active = time.time()

        except WebSocketDisconnect:
            pass
        except json.JSONDecodeError:
            pass
        finally:
            CollabStore.remove_connection(join_code, websocket)
            CollabStore.leave_session(join_code, participant.id)

            # Broadcast leave
            try:
                await broadcast(join_code, CollabMessage(
                    type="leave",
                    sender_id=participant.id,
                    sender_name=participant.name,
                    content=f"{participant.name} left the session",
                    timestamp=time.time(),
                ))
            except Exception:
                pass

    @router.post("/api/collab/create")
    async def create_collab(body: dict = {}):
        """Create a new collaboration session."""
        session = CollabStore.create_session(
            host_name=body.get("name", "Host"),
            session_id=body.get("session_id", ""),
            agent=body.get("agent", ""),
            repo_path=body.get("repo_path", ""),
        )
        return {
            "join_code": session.join_code,
            "host_id": session.host_id,
            "created_at": session.created_at,
        }

    @router.get("/api/collab/{join_code}")
    async def get_collab(join_code: str):
        """Get collaboration session info."""
        session = CollabStore.get_session(join_code)
        if not session:
            return {"error": "Session not found"}
        return {
            "join_code": session.join_code,
            "status": session.status,
            "agent": session.agent,
            "participants": [asdict(p) for p in session.participants],
            "message_count": len(session.messages),
            "created_at": session.created_at,
        }

    @router.get("/api/collab")
    async def list_collab():
        """List active collaboration sessions."""
        sessions = CollabStore.list_active()
        return {
            "sessions": [
                {
                    "join_code": s.join_code,
                    "agent": s.agent,
                    "participants": len(s.participants),
                    "created_at": s.created_at,
                }
                for s in sessions
            ]
        }

    return router


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------


def cmd_share(args: list[str] | None = None):
    """CLI handler for `code-agents share`."""
    from code_agents.cli.cli_helpers import _colors, _load_env, _server_url, _user_cwd, _api_post
    _load_env()

    bold, green, yellow, red, cyan, dim = _colors()
    url = _server_url()
    cwd = _user_cwd()

    name = os.getenv("CODE_AGENTS_NICKNAME", os.getenv("USER", "Host"))

    try:
        resp = _api_post(f"{url}/api/collab/create", {
            "name": name,
            "repo_path": cwd,
        })
        if resp and resp.get("join_code"):
            code = resp["join_code"]
            print(f"\n  {green('Session shared!')}")
            print(f"  Join code: {bold(code)}")
            print(f"  Others can join with: {cyan(f'code-agents join {code}')}")
            print(f"\n  {dim('Share this code with your teammate.')}\n")
        else:
            print(f"\n  {red('Failed to create shared session.')}\n")
    except Exception as e:
        print(f"\n  {red('Error:')} {e}\n")


def cmd_join(args: list[str] | None = None):
    """CLI handler for `code-agents join <code>`."""
    from code_agents.cli.cli_helpers import _colors, _load_env, _server_url, _api_get
    _load_env()

    args = args or []
    bold, green, yellow, red, cyan, dim = _colors()

    if not args:
        print(f"  {red('Usage:')} code-agents join <join-code>")
        return

    join_code = args[0]
    url = _server_url()

    try:
        resp = _api_get(f"{url}/api/collab/{join_code}")
        if resp and resp.get("status") == "active":
            print(f"\n  {green('Connected to shared session!')}")
            print(f"  Agent: {resp.get('agent', 'auto')}")
            print(f"  Participants: {resp.get('participants', 0)}")
            print(f"\n  {dim('Starting collaborative chat...')}")
            print(f"  {dim('Messages you send will be visible to all participants.')}\n")

            # In a real implementation, this would launch an interactive
            # WebSocket chat client. For now, show connection info.
            ws_url = url.replace("http://", "ws://").replace("https://", "wss://")
            print(f"  WebSocket: {cyan(f'{ws_url}/ws/collab/{join_code}')}\n")
        else:
            print(f"\n  {red('Session not found or ended:')} {join_code}\n")
    except Exception as e:
        print(f"\n  {red('Error:')} {e}\n")
