"""Agent Replay / Time Travel Debugging — record, replay, and fork agent sessions.

Records agent sessions as replayable traces. Users can replay step-by-step
and fork at any point to explore alternative paths.

Storage: ~/.code-agents/traces/<trace_id>.json
Format: Pretty-printed JSON for debuggability.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("code_agents.agent_system.agent_replay")

TRACES_DIR = Path.home() / ".code-agents" / "traces"


@dataclass
class TraceStep:
    """A single step in an agent session trace."""

    step_id: int
    timestamp: float
    role: str  # "user" | "assistant" | "system"
    content: str
    agent: str
    metadata: dict = field(default_factory=dict)


@dataclass
class SessionTrace:
    """A complete recorded session trace, optionally forked from another."""

    trace_id: str
    session_id: str
    agent: str
    repo: str
    created_at: float
    steps: list[TraceStep] = field(default_factory=list)
    forked_from: str | None = None
    fork_point: int | None = None


def _generate_trace_id() -> str:
    """Generate a short trace ID (UUID hex, first 12 chars)."""
    return uuid.uuid4().hex[:12]


def _trace_path(trace_id: str) -> Path:
    """Return the file path for a trace."""
    return TRACES_DIR / f"{trace_id}.json"


def _serialize_trace(trace: SessionTrace) -> dict:
    """Convert a SessionTrace to a JSON-serializable dict."""
    data = {
        "trace_id": trace.trace_id,
        "session_id": trace.session_id,
        "agent": trace.agent,
        "repo": trace.repo,
        "created_at": trace.created_at,
        "forked_from": trace.forked_from,
        "fork_point": trace.fork_point,
        "steps": [asdict(s) for s in trace.steps],
    }
    return data


def _deserialize_trace(data: dict) -> SessionTrace:
    """Reconstruct a SessionTrace from a dict."""
    steps = [TraceStep(**s) for s in data.get("steps", [])]
    return SessionTrace(
        trace_id=data["trace_id"],
        session_id=data["session_id"],
        agent=data["agent"],
        repo=data["repo"],
        created_at=data["created_at"],
        steps=steps,
        forked_from=data.get("forked_from"),
        fork_point=data.get("fork_point"),
    )


class TraceRecorder:
    """Records agent interactions as replayable trace steps."""

    def __init__(self, session_id: str, agent: str, repo: str) -> None:
        self._trace = SessionTrace(
            trace_id=_generate_trace_id(),
            session_id=session_id,
            agent=agent,
            repo=repo,
            created_at=time.time(),
        )
        self._next_step_id = 0
        logger.debug(
            "TraceRecorder created: trace_id=%s session=%s agent=%s",
            self._trace.trace_id,
            session_id,
            agent,
        )

    def record_step(
        self, role: str, content: str, metadata: dict | None = None
    ) -> TraceStep:
        """Record a single step and return it."""
        step = TraceStep(
            step_id=self._next_step_id,
            timestamp=time.time(),
            role=role,
            content=content,
            agent=self._trace.agent,
            metadata=metadata or {},
        )
        self._trace.steps.append(step)
        self._next_step_id += 1
        logger.debug(
            "Recorded step %d (role=%s) in trace %s",
            step.step_id,
            role,
            self._trace.trace_id,
        )
        return step

    def save(self) -> Path:
        """Persist the trace to disk as pretty-printed JSON."""
        TRACES_DIR.mkdir(parents=True, exist_ok=True)
        path = _trace_path(self._trace.trace_id)
        data = _serialize_trace(self._trace)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.info("Trace saved: %s (%d steps)", path, len(self._trace.steps))
        return path

    def get_trace(self) -> SessionTrace:
        """Return the current in-memory trace."""
        return self._trace


class TracePlayer:
    """Loads and replays a previously recorded trace."""

    def __init__(self, trace_id: str) -> None:
        self._trace_id = trace_id
        self._trace: SessionTrace | None = None

    def load(self) -> SessionTrace:
        """Load the trace from disk."""
        path = _trace_path(self._trace_id)
        if not path.exists():
            raise FileNotFoundError(f"Trace not found: {self._trace_id}")
        data = json.loads(path.read_text())
        self._trace = _deserialize_trace(data)
        logger.info(
            "Trace loaded: %s (%d steps)", self._trace_id, len(self._trace.steps)
        )
        return self._trace

    def play(
        self,
        step_callback: Callable[[TraceStep], None],
        delay: float = 0.5,
    ) -> None:
        """Replay all steps, calling step_callback for each with optional delay."""
        if self._trace is None:
            self.load()
        assert self._trace is not None
        import time as _time

        for i, step in enumerate(self._trace.steps):
            step_callback(step)
            if delay > 0 and i < len(self._trace.steps) - 1:
                _time.sleep(delay)
        logger.info("Replay complete: %s (%d steps)", self._trace_id, len(self._trace.steps))

    def play_to(self, step_id: int) -> list[TraceStep]:
        """Return steps from the beginning up to and including step_id."""
        if self._trace is None:
            self.load()
        assert self._trace is not None
        result = [s for s in self._trace.steps if s.step_id <= step_id]
        logger.debug(
            "play_to(%d) returned %d steps from trace %s",
            step_id,
            len(result),
            self._trace_id,
        )
        return result


class TraceFork:
    """Fork a trace at a given step to explore alternative paths."""

    @staticmethod
    def fork_at(trace_id: str, step_id: int) -> SessionTrace:
        """Create a new trace containing steps[0:step_id] from the parent.

        The new trace has forked_from and fork_point set for provenance.
        """
        path = _trace_path(trace_id)
        if not path.exists():
            raise FileNotFoundError(f"Trace not found: {trace_id}")
        data = json.loads(path.read_text())
        parent = _deserialize_trace(data)

        # Keep steps up to (but not including) the fork point
        kept_steps = [s for s in parent.steps if s.step_id < step_id]

        new_trace = SessionTrace(
            trace_id=_generate_trace_id(),
            session_id=parent.session_id,
            agent=parent.agent,
            repo=parent.repo,
            created_at=time.time(),
            steps=kept_steps,
            forked_from=trace_id,
            fork_point=step_id,
        )

        # Auto-save the fork
        TRACES_DIR.mkdir(parents=True, exist_ok=True)
        fork_path = _trace_path(new_trace.trace_id)
        fork_data = _serialize_trace(new_trace)
        fork_path.write_text(json.dumps(fork_data, indent=2, ensure_ascii=False))
        logger.info(
            "Forked trace %s at step %d -> new trace %s (%d steps kept)",
            trace_id,
            step_id,
            new_trace.trace_id,
            len(kept_steps),
        )
        return new_trace


def list_traces(limit: int = 20) -> list[dict]:
    """List recent traces sorted by creation date (newest first).

    Returns a list of summary dicts with trace_id, agent, repo, created_at, step_count.
    """
    if not TRACES_DIR.exists():
        return []

    traces: list[dict] = []
    for path in TRACES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            traces.append(
                {
                    "trace_id": data["trace_id"],
                    "agent": data.get("agent", "unknown"),
                    "repo": data.get("repo", ""),
                    "created_at": data.get("created_at", 0),
                    "step_count": len(data.get("steps", [])),
                    "forked_from": data.get("forked_from"),
                }
            )
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Skipping corrupt trace file %s: %s", path, exc)
            continue

    traces.sort(key=lambda t: t["created_at"], reverse=True)
    return traces[:limit]


def delete_trace(trace_id: str) -> bool:
    """Delete a trace file. Returns True if deleted, False if not found."""
    path = _trace_path(trace_id)
    if path.exists():
        path.unlink()
        logger.info("Deleted trace: %s", trace_id)
        return True
    logger.warning("Trace not found for deletion: %s", trace_id)
    return False


def search_traces(query: str) -> list[dict]:
    """Search traces by agent name or content keywords.

    Returns matching trace summaries sorted by relevance (match count).
    """
    if not TRACES_DIR.exists():
        return []

    query_lower = query.lower()
    results: list[dict] = []

    for path in TRACES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, KeyError):
            continue

        # Score: check agent name, repo, and step content
        score = 0
        agent = data.get("agent", "")
        repo = data.get("repo", "")

        if query_lower in agent.lower():
            score += 10
        if query_lower in repo.lower():
            score += 5

        for step in data.get("steps", []):
            content = step.get("content", "")
            if query_lower in content.lower():
                score += 1

        if score > 0:
            results.append(
                {
                    "trace_id": data["trace_id"],
                    "agent": agent,
                    "repo": repo,
                    "created_at": data.get("created_at", 0),
                    "step_count": len(data.get("steps", [])),
                    "forked_from": data.get("forked_from"),
                    "score": score,
                }
            )

    results.sort(key=lambda t: t["score"], reverse=True)
    return results
