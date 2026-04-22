"""Tests for agent_replay — trace recording, playback, forking, listing, search."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.agent_system.agent_replay import (
    TRACES_DIR,
    SessionTrace,
    TraceFork,
    TracePlayer,
    TraceRecorder,
    TraceStep,
    delete_trace,
    list_traces,
    search_traces,
)


@pytest.fixture(autouse=True)
def _use_tmp_traces_dir(tmp_path, monkeypatch):
    """Redirect TRACES_DIR to a temporary directory for every test."""
    monkeypatch.setattr("code_agents.agent_system.agent_replay.TRACES_DIR", tmp_path)


class TestTraceRecorder:
    def test_record_steps_incrementing_ids(self):
        rec = TraceRecorder("sess-1", "auto-pilot", "/repo")
        s0 = rec.record_step("user", "hello")
        s1 = rec.record_step("assistant", "hi there")
        s2 = rec.record_step("user", "do something")

        assert s0.step_id == 0
        assert s1.step_id == 1
        assert s2.step_id == 2
        assert s0.role == "user"
        assert s1.role == "assistant"

    def test_record_step_with_metadata(self):
        rec = TraceRecorder("sess-2", "code-writer", "/repo")
        meta = {"tokens": 150, "model": "gpt-4"}
        step = rec.record_step("assistant", "response", metadata=meta)
        assert step.metadata == meta

    def test_save_creates_json(self, tmp_path):
        rec = TraceRecorder("sess-3", "git-ops", "/my/repo")
        rec.record_step("user", "show branches")
        rec.record_step("assistant", "here are branches")
        path = rec.save()

        assert path.exists()
        assert path.suffix == ".json"

        data = json.loads(path.read_text())
        assert data["session_id"] == "sess-3"
        assert data["agent"] == "git-ops"
        assert data["repo"] == "/my/repo"
        assert len(data["steps"]) == 2
        assert data["steps"][0]["step_id"] == 0
        assert data["steps"][1]["step_id"] == 1

    def test_save_pretty_printed(self, tmp_path):
        rec = TraceRecorder("sess-4", "auto-pilot", "/repo")
        rec.record_step("user", "hi")
        path = rec.save()
        text = path.read_text()
        # Pretty-printed JSON has newlines and indentation
        assert "\n" in text
        assert "  " in text

    def test_get_trace_returns_session_trace(self):
        rec = TraceRecorder("sess-5", "code-reviewer", "/repo")
        rec.record_step("system", "init")
        trace = rec.get_trace()
        assert isinstance(trace, SessionTrace)
        assert trace.session_id == "sess-5"
        assert len(trace.steps) == 1

    def test_trace_id_is_12_hex_chars(self):
        rec = TraceRecorder("sess-6", "auto-pilot", "/repo")
        trace = rec.get_trace()
        assert len(trace.trace_id) == 12
        # Should be valid hex
        int(trace.trace_id, 16)


class TestTracePlayer:
    def _create_trace(self, tmp_path, trace_id="abc123def456", steps=3):
        """Helper to write a trace file."""
        data = {
            "trace_id": trace_id,
            "session_id": "sess-play",
            "agent": "auto-pilot",
            "repo": "/test/repo",
            "created_at": time.time(),
            "forked_from": None,
            "fork_point": None,
            "steps": [
                {
                    "step_id": i,
                    "timestamp": time.time() + i,
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"step {i} content",
                    "agent": "auto-pilot",
                    "metadata": {},
                }
                for i in range(steps)
            ],
        }
        path = tmp_path / f"{trace_id}.json"
        path.write_text(json.dumps(data, indent=2))
        return trace_id

    def test_load_trace(self, tmp_path):
        tid = self._create_trace(tmp_path)
        player = TracePlayer(tid)
        trace = player.load()
        assert trace.trace_id == tid
        assert len(trace.steps) == 3

    def test_load_missing_trace(self, tmp_path):
        player = TracePlayer("nonexistent123")
        with pytest.raises(FileNotFoundError):
            player.load()

    def test_play_to_subset(self, tmp_path):
        tid = self._create_trace(tmp_path, steps=5)
        player = TracePlayer(tid)
        player.load()
        subset = player.play_to(2)
        assert len(subset) == 3  # steps 0, 1, 2
        assert subset[-1].step_id == 2

    def test_play_to_auto_loads(self, tmp_path):
        tid = self._create_trace(tmp_path, steps=4)
        player = TracePlayer(tid)
        # Don't call load() explicitly
        subset = player.play_to(1)
        assert len(subset) == 2

    def test_play_calls_callback(self, tmp_path):
        tid = self._create_trace(tmp_path, steps=3)
        player = TracePlayer(tid)
        player.load()
        collected = []
        player.play(lambda s: collected.append(s.step_id), delay=0)
        assert collected == [0, 1, 2]


class TestTraceFork:
    def _save_trace(self, tmp_path, trace_id="parent123456", steps=5):
        data = {
            "trace_id": trace_id,
            "session_id": "sess-fork",
            "agent": "code-writer",
            "repo": "/fork/repo",
            "created_at": time.time(),
            "forked_from": None,
            "fork_point": None,
            "steps": [
                {
                    "step_id": i,
                    "timestamp": time.time() + i,
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"parent step {i}",
                    "agent": "code-writer",
                    "metadata": {},
                }
                for i in range(steps)
            ],
        }
        path = tmp_path / f"{trace_id}.json"
        path.write_text(json.dumps(data, indent=2))
        return trace_id

    def test_fork_creates_new_trace(self, tmp_path):
        tid = self._save_trace(tmp_path)
        forked = TraceFork.fork_at(tid, step_id=3)

        assert forked.trace_id != tid
        assert forked.forked_from == tid
        assert forked.fork_point == 3
        assert len(forked.steps) == 3  # steps 0, 1, 2
        assert forked.agent == "code-writer"
        assert forked.repo == "/fork/repo"

    def test_fork_saves_to_disk(self, tmp_path):
        tid = self._save_trace(tmp_path)
        forked = TraceFork.fork_at(tid, step_id=2)
        fork_path = tmp_path / f"{forked.trace_id}.json"
        assert fork_path.exists()

    def test_fork_missing_trace(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TraceFork.fork_at("doesnotexist1", step_id=0)

    def test_fork_at_zero_gives_empty(self, tmp_path):
        tid = self._save_trace(tmp_path)
        forked = TraceFork.fork_at(tid, step_id=0)
        assert len(forked.steps) == 0
        assert forked.fork_point == 0


class TestListTraces:
    def _write_trace(self, tmp_path, trace_id, agent="auto-pilot", created_at=None):
        data = {
            "trace_id": trace_id,
            "session_id": "s",
            "agent": agent,
            "repo": "/r",
            "created_at": created_at or time.time(),
            "forked_from": None,
            "fork_point": None,
            "steps": [{"step_id": 0, "timestamp": 0, "role": "user", "content": "hi", "agent": agent, "metadata": {}}],
        }
        (tmp_path / f"{trace_id}.json").write_text(json.dumps(data))

    def test_list_sorted_by_date(self, tmp_path):
        self._write_trace(tmp_path, "older1234567", created_at=1000)
        self._write_trace(tmp_path, "newer1234567", created_at=2000)
        result = list_traces(limit=10)
        assert len(result) == 2
        assert result[0]["trace_id"] == "newer1234567"
        assert result[1]["trace_id"] == "older1234567"

    def test_list_respects_limit(self, tmp_path):
        for i in range(5):
            self._write_trace(tmp_path, f"trace{i:07d}x", created_at=1000 + i)
        result = list_traces(limit=3)
        assert len(result) == 3

    def test_list_empty_dir(self, tmp_path):
        result = list_traces()
        assert result == []

    def test_list_nonexistent_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("code_agents.agent_system.agent_replay.TRACES_DIR", tmp_path / "nope")
        result = list_traces()
        assert result == []


class TestDeleteTrace:
    def test_delete_existing(self, tmp_path):
        path = tmp_path / "del123456789.json"
        path.write_text("{}")
        assert delete_trace("del123456789") is True
        assert not path.exists()

    def test_delete_missing(self, tmp_path):
        assert delete_trace("nope12345678") is False


class TestSearchTraces:
    def _write_trace(self, tmp_path, trace_id, agent, content_words=None):
        steps = []
        for i, word in enumerate(content_words or []):
            steps.append({
                "step_id": i, "timestamp": 0, "role": "user",
                "content": word, "agent": agent, "metadata": {},
            })
        data = {
            "trace_id": trace_id, "session_id": "s", "agent": agent,
            "repo": "/repo", "created_at": time.time(),
            "forked_from": None, "fork_point": None, "steps": steps,
        }
        (tmp_path / f"{trace_id}.json").write_text(json.dumps(data))

    def test_search_by_agent(self, tmp_path):
        self._write_trace(tmp_path, "t1_agent_hit", "code-writer", ["hello"])
        self._write_trace(tmp_path, "t2_agent_mis", "git-ops", ["hello"])
        results = search_traces("code-writer")
        assert any(r["trace_id"] == "t1_agent_hit" for r in results)

    def test_search_by_content(self, tmp_path):
        self._write_trace(tmp_path, "t3_content__", "auto-pilot", ["fix the payment bug"])
        self._write_trace(tmp_path, "t4_content__", "auto-pilot", ["deploy service"])
        results = search_traces("payment")
        assert len(results) == 1
        assert results[0]["trace_id"] == "t3_content__"

    def test_search_no_results(self, tmp_path):
        self._write_trace(tmp_path, "t5_no_match_", "auto-pilot", ["nothing here"])
        results = search_traces("zzzznotfound")
        assert results == []

    def test_search_empty_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("code_agents.agent_system.agent_replay.TRACES_DIR", tmp_path / "nope")
        assert search_traces("anything") == []
