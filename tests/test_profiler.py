"""Tests for code_agents.profiler — Performance Profiler Agent."""

from __future__ import annotations

import json
import os
import pstats
import tempfile
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from code_agents.observability.profiler import (
    HotSpot,
    Optimization,
    ProfileResult,
    ProfilerAgent,
    format_profile_json,
    format_profile_result,
)


# ---------------------------------------------------------------------------
# TestHotSpot
# ---------------------------------------------------------------------------

class TestHotSpot:
    """Test HotSpot dataclass construction."""

    def test_basic_construction(self):
        hs = HotSpot(
            function="execute_query",
            file="/app/db.py",
            line=42,
            total_time=1.23,
            calls=450,
            per_call=0.00273,
        )
        assert hs.function == "execute_query"
        assert hs.file == "/app/db.py"
        assert hs.line == 42
        assert hs.total_time == 1.23
        assert hs.calls == 450
        assert hs.per_call == pytest.approx(0.00273)

    def test_zero_calls(self):
        hs = HotSpot(function="noop", file="x.py", line=1, total_time=0.0, calls=0, per_call=0.0)
        assert hs.calls == 0
        assert hs.per_call == 0.0

    def test_high_volume(self):
        hs = HotSpot(
            function="json.loads",
            file="/usr/lib/json/__init__.py",
            line=100,
            total_time=0.8,
            calls=12000,
            per_call=0.8 / 12000,
        )
        assert hs.calls == 12000
        assert hs.per_call < 0.001


# ---------------------------------------------------------------------------
# TestOptimization
# ---------------------------------------------------------------------------

class TestOptimization:
    """Test Optimization dataclass."""

    def test_with_code_fix(self):
        opt = Optimization(
            function="execute_query",
            file="/app/db.py",
            suggestion="Batch queries",
            estimated_impact="60% faster",
            code_fix="SELECT ... WHERE id IN (...)",
        )
        assert opt.code_fix == "SELECT ... WHERE id IN (...)"

    def test_without_code_fix(self):
        opt = Optimization(
            function="process",
            file="app.py",
            suggestion="Review for optimization",
            estimated_impact="varies",
        )
        assert opt.code_fix == ""


# ---------------------------------------------------------------------------
# TestProfileResult
# ---------------------------------------------------------------------------

class TestProfileResult:
    """Test ProfileResult dataclass."""

    def test_empty(self):
        result = ProfileResult(
            hotspots=[], optimizations=[], total_time=0.0, command="pytest"
        )
        assert result.hotspots == []
        assert result.summary == ""

    def test_with_data(self):
        hs = HotSpot("f", "a.py", 1, 1.0, 10, 0.1)
        opt = Optimization("f", "a.py", "cache it", "50% faster")
        result = ProfileResult(
            hotspots=[hs], optimizations=[opt],
            total_time=1.0, command="pytest",
            summary="1 hotspot",
        )
        assert len(result.hotspots) == 1
        assert len(result.optimizations) == 1


# ---------------------------------------------------------------------------
# TestParseStats
# ---------------------------------------------------------------------------

class TestParseStats:
    """Test _parse_stats with a real cProfile stats file."""

    def _create_stats_file(self) -> str:
        """Create a real pstats file by profiling a trivial snippet."""
        import cProfile
        fd, path = tempfile.mkstemp(suffix=".prof")
        os.close(fd)
        profiler = cProfile.Profile()
        profiler.enable()
        # Do some work to produce stats
        total = sum(range(1000))
        _ = [str(i) for i in range(100)]
        profiler.disable()
        profiler.dump_stats(path)
        return path

    def test_parse_produces_hotspots(self):
        stats_path = self._create_stats_file()
        try:
            agent = ProfilerAgent(cwd="/tmp", command="dummy")
            hotspots = agent._parse_stats(stats_path)
            # Should find at least some non-builtin hotspots
            assert isinstance(hotspots, list)
            for hs in hotspots:
                assert isinstance(hs, HotSpot)
                assert hs.calls >= 0
                assert hs.total_time >= 0
        finally:
            os.unlink(stats_path)

    def test_parse_bad_file_returns_empty(self):
        agent = ProfilerAgent(cwd="/tmp", command="dummy")
        result = agent._parse_stats("/nonexistent/file.prof")
        assert result == []

    def test_parse_respects_top(self):
        stats_path = self._create_stats_file()
        try:
            agent = ProfilerAgent(cwd="/tmp", command="dummy")
            hotspots = agent._parse_stats(stats_path, top=3)
            assert len(hotspots) <= 3
        finally:
            os.unlink(stats_path)


# ---------------------------------------------------------------------------
# TestOptimizations — pattern matching
# ---------------------------------------------------------------------------

class TestOptimizations:
    """Test _generate_optimizations pattern matching."""

    def test_cache_suggestion_for_high_calls(self):
        agent = ProfilerAgent(cwd="/tmp", command="dummy")
        hs = HotSpot("compute_hash", "/app/util.py", 10, 0.05, 500, 0.0001)
        opts = agent._analyze_hotspot(hs)
        suggestions = [o.suggestion for o in opts]
        assert any("caching" in s or "memoization" in s for s in suggestions)

    def test_io_suggestion(self):
        agent = ProfilerAgent(cwd="/tmp", command="dummy")
        hs = HotSpot("send_request", "/app/client.py", 20, 2.0, 50, 0.04)
        opts = agent._analyze_hotspot(hs)
        suggestions = [o.suggestion for o in opts]
        assert any("I/O" in s or "async" in s or "batch" in s for s in suggestions)

    def test_db_n_plus_one(self):
        agent = ProfilerAgent(cwd="/tmp", command="dummy")
        hs = HotSpot("execute_query", "/app/db.py", 30, 1.5, 200, 0.0075)
        opts = agent._analyze_hotspot(hs)
        suggestions = [o.suggestion for o in opts]
        assert any("N+1" in s or "DB" in s for s in suggestions)

    def test_json_suggestion(self):
        agent = ProfilerAgent(cwd="/tmp", command="dummy")
        hs = HotSpot("json_loads", "/app/parse.py", 5, 0.5, 1000, 0.0005)
        opts = agent._analyze_hotspot(hs)
        suggestions = [o.suggestion for o in opts]
        assert any("JSON" in s or "orjson" in s for s in suggestions)

    def test_generic_hotspot(self):
        agent = ProfilerAgent(cwd="/tmp", command="dummy")
        hs = HotSpot("mystery_func", "/app/core.py", 1, 2.0, 5, 0.4)
        opts = agent._analyze_hotspot(hs)
        assert len(opts) >= 1
        assert any("Hotspot" in o.suggestion or "optimization" in o.suggestion for o in opts)

    def test_no_suggestions_for_fast_simple(self):
        agent = ProfilerAgent(cwd="/tmp", command="dummy")
        hs = HotSpot("tiny", "/app/x.py", 1, 0.001, 2, 0.0005)
        opts = agent._analyze_hotspot(hs)
        assert opts == []


# ---------------------------------------------------------------------------
# TestFormat — terminal output
# ---------------------------------------------------------------------------

class TestFormat:
    """Test format_profile_result output."""

    def test_empty_result(self):
        result = ProfileResult(
            hotspots=[], optimizations=[], total_time=0.0, command="pytest"
        )
        output = format_profile_result(result)
        assert "No hotspots" in output
        assert "Profile" in output

    def test_with_hotspots(self):
        hs1 = HotSpot("db.execute_query", "/app/db.py", 42, 1.2, 450, 0.00267)
        hs2 = HotSpot("json.loads", "/app/api.py", 10, 0.8, 1200, 0.000667)
        opt = Optimization(
            "db.execute_query", "/app/db.py",
            "batch queries instead of per-item",
            "est. 60% faster",
        )
        result = ProfileResult(
            hotspots=[hs1, hs2],
            optimizations=[opt],
            total_time=2.0,
            command="pytest test_api.py",
            summary="Profiled in 2.00s.",
        )
        output = format_profile_result(result)
        assert "db.execute_query" in output
        assert "json.loads" in output
        assert "450" in output
        assert "Optimizations:" in output
        assert "batch queries" in output

    def test_json_format(self):
        hs = HotSpot("f", "a.py", 1, 1.0, 10, 0.1)
        opt = Optimization("f", "a.py", "fix it", "50%", "code here")
        result = ProfileResult(
            hotspots=[hs], optimizations=[opt],
            total_time=1.0, command="pytest",
        )
        data = format_profile_json(result)
        assert data["command"] == "pytest"
        assert len(data["hotspots"]) == 1
        assert data["hotspots"][0]["function"] == "f"
        assert len(data["optimizations"]) == 1
        assert data["optimizations"][0]["code_fix"] == "code here"
        # Verify it's JSON-serializable
        json.dumps(data)

    def test_long_command_truncated(self):
        result = ProfileResult(
            hotspots=[], optimizations=[], total_time=0.0,
            command="a" * 100,
        )
        output = format_profile_result(result)
        assert "..." in output

    def test_top_parameter(self):
        hotspots = [
            HotSpot(f"func_{i}", "a.py", i, float(20 - i), 10, 0.1)
            for i in range(15)
        ]
        result = ProfileResult(
            hotspots=hotspots, optimizations=[],
            total_time=100.0, command="pytest",
        )
        output = format_profile_result(result, top=5)
        # Only top 5 should appear
        assert "func_0" in output
        assert "func_4" in output
        assert "func_10" not in output


# ---------------------------------------------------------------------------
# TestProfilerAgent — run (mocked subprocess)
# ---------------------------------------------------------------------------

class TestProfilerAgentRun:
    """Test ProfilerAgent.run with mocked subprocess."""

    @patch("code_agents.observability.profiler.ProfilerAgent._run_with_cprofile")
    def test_run_no_stats(self, mock_cprofile):
        mock_cprofile.return_value = None
        agent = ProfilerAgent(cwd="/tmp", command="pytest")
        result = agent.run()
        assert result.total_time == 0.0
        assert "failed" in result.summary.lower()

    @patch("code_agents.observability.profiler.ProfilerAgent._parse_stats")
    @patch("code_agents.observability.profiler.ProfilerAgent._run_with_cprofile")
    def test_run_success(self, mock_cprofile, mock_parse):
        mock_cprofile.return_value = "/tmp/fake.prof"
        mock_parse.return_value = [
            HotSpot("main", "app.py", 1, 2.0, 5, 0.4),
        ]
        with patch("os.unlink"):
            agent = ProfilerAgent(cwd="/tmp", command="python app.py")
            result = agent.run()
        assert len(result.hotspots) == 1
        assert result.total_time == 2.0
        assert result.command == "python app.py"
