"""Tests for the cost dashboard CLI and token tracker extensions."""

from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Token tracker aggregation tests
# ---------------------------------------------------------------------------


class TestAgentBreakdown:
    """Test get_agent_breakdown()."""

    def _write_csv(self, tmp_path: Path, rows: list[dict]) -> Path:
        from code_agents.core.token_tracker import CSV_HEADERS
        csv_path = tmp_path / "token_usage.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            for row in rows:
                full = {h: "" for h in CSV_HEADERS}
                full.update(row)
                writer.writerow(full)
        return csv_path

    def test_agent_breakdown_groups_by_agent(self, tmp_path):
        from code_agents.core.token_tracker import get_agent_breakdown
        csv_path = self._write_csv(tmp_path, [
            {"date": "2026-04-09", "agent": "auto-pilot", "input_tokens": "100", "output_tokens": "50", "total_tokens": "150", "cost_usd": "0.001"},
            {"date": "2026-04-09", "agent": "auto-pilot", "input_tokens": "200", "output_tokens": "100", "total_tokens": "300", "cost_usd": "0.002"},
            {"date": "2026-04-09", "agent": "code-writer", "input_tokens": "500", "output_tokens": "200", "total_tokens": "700", "cost_usd": "0.005"},
        ])
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_agent_breakdown(date="2026-04-09")
        assert len(result) == 2
        # Sorted by total_tokens descending
        assert result[0]["agent"] == "code-writer"
        assert result[0]["total_tokens"] == 700
        assert result[1]["agent"] == "auto-pilot"
        assert result[1]["total_tokens"] == 450
        assert result[1]["messages"] == 2

    def test_agent_breakdown_filter(self, tmp_path):
        from code_agents.core.token_tracker import get_agent_breakdown
        csv_path = self._write_csv(tmp_path, [
            {"date": "2026-04-09", "agent": "auto-pilot", "total_tokens": "100"},
            {"date": "2026-04-09", "agent": "code-writer", "total_tokens": "200"},
        ])
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_agent_breakdown(date="2026-04-09", agent_filter="code-writer")
        assert len(result) == 1
        assert result[0]["agent"] == "code-writer"

    def test_agent_breakdown_no_file(self, tmp_path):
        from code_agents.core.token_tracker import get_agent_breakdown
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", tmp_path / "nope.csv"):
            assert get_agent_breakdown() == []


class TestDailyHistory:
    """Test get_daily_history()."""

    def _write_csv(self, tmp_path: Path, rows: list[dict]) -> Path:
        from code_agents.core.token_tracker import CSV_HEADERS
        csv_path = tmp_path / "token_usage.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            for row in rows:
                full = {h: "" for h in CSV_HEADERS}
                full.update(row)
                writer.writerow(full)
        return csv_path

    def test_daily_history_groups_and_limits(self, tmp_path):
        from code_agents.core.token_tracker import get_daily_history
        csv_path = self._write_csv(tmp_path, [
            {"date": "2026-04-07", "total_tokens": "100", "cost_usd": "0.01"},
            {"date": "2026-04-08", "total_tokens": "200", "cost_usd": "0.02"},
            {"date": "2026-04-08", "total_tokens": "150", "cost_usd": "0.015"},
            {"date": "2026-04-09", "total_tokens": "300", "cost_usd": "0.03"},
        ])
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_daily_history(limit=2)
        assert len(result) == 2
        assert result[0]["date"] == "2026-04-09"
        assert result[1]["date"] == "2026-04-08"
        assert result[1]["total_tokens"] == 350  # aggregated

    def test_daily_history_no_file(self, tmp_path):
        from code_agents.core.token_tracker import get_daily_history
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", tmp_path / "nope.csv"):
            assert get_daily_history() == []


# ---------------------------------------------------------------------------
# CLI cost command tests
# ---------------------------------------------------------------------------


class TestCmdCost:
    """Test the CLI cost command."""

    @patch("code_agents.core.token_tracker.USAGE_CSV_PATH")
    def test_cost_no_data(self, mock_path, capsys):
        mock_path.is_file.return_value = False
        from code_agents.cli.cli_cost import _display_cost
        _display_cost("today")
        captured = capsys.readouterr()
        assert "No usage data" in captured.out

    @patch("code_agents.core.token_tracker.get_session_summary")
    @patch("code_agents.core.token_tracker.USAGE_CSV_PATH")
    def test_cost_session_mode(self, mock_path, mock_session, capsys):
        mock_path.is_file.return_value = True
        mock_session.return_value = {
            "messages": 5, "input_tokens": 1000, "output_tokens": 500,
            "cache_read_tokens": 200, "cache_write_tokens": 100,
            "total_tokens": 1500, "cost_usd": 0.05,
            "duration_ms": 3000, "agent": "auto-pilot", "model": "gpt-4",
        }
        from code_agents.cli.cli_cost import _display_cost
        _display_cost("session")
        # Should not error — output depends on Rich availability

    def test_format_cost(self):
        from code_agents.cli.cli_cost import _format_cost
        assert _format_cost(0) == "$0.00"
        assert _format_cost(0.005) == "$0.0050"
        assert _format_cost(1.23) == "$1.23"
        assert _format_cost(15.678) == "$15.68"

    def test_cost_color_bar(self):
        from code_agents.cli.cli_cost import _cost_color_bar
        assert _cost_color_bar(0.5, 5) == "[green]█████[/green]"
        assert _cost_color_bar(5.0, 3) == "[yellow]███[/yellow]"
        assert _cost_color_bar(15.0, 2) == "[red]██[/red]"
        assert _cost_color_bar(1.0, 0) == ""
