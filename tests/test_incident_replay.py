"""Tests for the incident replay module."""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock
import pytest

from code_agents.observability.incident_replay import (
    IncidentReplayer, IncidentReplayResult, TimelineEvent,
    RootCauseAnalysis, replay_incident,
)


class TestIncidentReplayer:
    """Test IncidentReplayer methods."""

    def test_init(self, tmp_path):
        replayer = IncidentReplayer(cwd=str(tmp_path))
        assert replayer.cwd == str(tmp_path)

    @patch("code_agents.observability.incident_replay.subprocess.run")
    def test_replay_basic(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        replayer = IncidentReplayer(cwd=str(tmp_path))
        result = replayer.replay(start_time="2026-04-01 10:00:00")
        assert isinstance(result, IncidentReplayResult)
        assert result.duration_minutes == 120.0  # default 2-hour window

    @patch("code_agents.observability.incident_replay.subprocess.run")
    def test_replay_with_git_events(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            stdout="abc123|2026-04-01 10:30:00|fix: critical bug in auth|dev\n"
                   "def456|2026-04-01 10:15:00|feat: add caching|dev\n",
            returncode=0,
        )
        replayer = IncidentReplayer(cwd=str(tmp_path))
        result = replayer.replay(
            start_time="2026-04-01 10:00:00",
            end_time="2026-04-01 12:00:00",
        )
        assert len(result.timeline) >= 2
        assert any(e.event_type == "recovery" for e in result.timeline)

    def test_replay_with_log_file(self, tmp_path):
        log_content = """2026-04-01 10:05:00 ERROR Connection refused to database
2026-04-01 10:06:00 CRITICAL Service unavailable
2026-04-01 10:10:00 WARNING High latency detected
2026-04-01 10:30:00 INFO Service recovered
"""
        log_file = tmp_path / "app.log"
        log_file.write_text(log_content)

        with patch("code_agents.observability.incident_replay.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            replayer = IncidentReplayer(cwd=str(tmp_path))
            result = replayer.replay(
                start_time="2026-04-01 10:00:00",
                end_time="2026-04-01 11:00:00",
                log_file=str(log_file),
            )
            log_events = [e for e in result.timeline if e.source == "log"]
            assert len(log_events) >= 2  # ERROR + CRITICAL

    def test_root_cause_analysis(self, tmp_path):
        replayer = IncidentReplayer(cwd=str(tmp_path))
        timeline = [
            TimelineEvent(timestamp="10:00", event_type="deploy",
                          description="Deploy v2.0", severity="info"),
            TimelineEvent(timestamp="10:05", event_type="error",
                          description="NullPointerException in AuthService",
                          severity="error"),
        ]
        rca = replayer._analyze_root_cause(timeline)
        assert isinstance(rca, RootCauseAnalysis)
        assert rca.category == "code_bug"
        assert "Deploy" in rca.primary_cause

    def test_convenience_function(self, tmp_path):
        with patch("code_agents.observability.incident_replay.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            result = replay_incident(
                cwd=str(tmp_path), start_time="2026-04-01 10:00:00",
            )
            assert isinstance(result, dict)
            assert "timeline" in result
            assert "root_cause" in result
            assert "recommendations" in result
