"""Tests for gita_shlokas.py — Bhagavad Gita shloka utilities."""

import sys
from unittest.mock import patch

import pytest

from code_agents.domain.gita_shlokas import (
    SHLOKAS,
    random_shloka,
    format_shloka,
    format_shloka_oneline,
    rainbow_text,
    format_shloka_rainbow,
)


# ---------------------------------------------------------------------------
# SHLOKAS data
# ---------------------------------------------------------------------------

class TestShlokasData:
    def test_not_empty(self):
        assert len(SHLOKAS) > 0

    def test_all_have_required_keys(self):
        for s in SHLOKAS:
            assert "sanskrit" in s
            assert "hindi" in s
            assert "english" in s
            assert "ref" in s

    def test_refs_are_valid_format(self):
        for s in SHLOKAS:
            # refs like "2.47", "18.66"
            parts = s["ref"].split(".")
            assert len(parts) == 2
            assert parts[0].isdigit()
            assert parts[1].isdigit()


# ---------------------------------------------------------------------------
# random_shloka
# ---------------------------------------------------------------------------

class TestRandomShloka:
    def test_returns_dict(self):
        s = random_shloka()
        assert isinstance(s, dict)
        assert "sanskrit" in s

    def test_returns_from_collection(self):
        s = random_shloka()
        assert s in SHLOKAS


# ---------------------------------------------------------------------------
# format_shloka
# ---------------------------------------------------------------------------

class TestFormatShloka:
    def test_with_specific_shloka(self):
        s = SHLOKAS[0]
        result = format_shloka(s)
        assert s["sanskrit"] in result
        assert s["english"] in result
        assert s["ref"] in result
        assert s["hindi"] in result

    def test_with_none_uses_random(self):
        result = format_shloka(None)
        assert "Bhagavad Gita" in result

    def test_no_args_uses_random(self):
        result = format_shloka()
        assert "Bhagavad Gita" in result


# ---------------------------------------------------------------------------
# format_shloka_oneline
# ---------------------------------------------------------------------------

class TestFormatShlokaOneline:
    def test_with_specific(self):
        s = SHLOKAS[1]
        result = format_shloka_oneline(s)
        assert s["sanskrit"] in result
        assert s["english"] in result
        assert f"Gita {s['ref']}" in result
        assert "\n" not in result

    def test_with_none(self):
        result = format_shloka_oneline()
        assert "Gita" in result


# ---------------------------------------------------------------------------
# rainbow_text
# ---------------------------------------------------------------------------

class TestRainbowText:
    def test_non_tty_returns_plain(self):
        with patch.object(sys.stdout, "isatty", return_value=False):
            result = rainbow_text("hello world")
        assert result == "hello world"

    def test_tty_adds_colors(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            result = rainbow_text("hello world")
        assert "\033[" in result
        assert "hello" in result
        assert "world" in result

    def test_empty_string(self):
        with patch.object(sys.stdout, "isatty", return_value=True):
            result = rainbow_text("")
        assert result == ""


# ---------------------------------------------------------------------------
# format_shloka_rainbow
# ---------------------------------------------------------------------------

class TestFormatShlokaRainbow:
    def test_contains_english_and_ref(self):
        s = SHLOKAS[0]
        with patch.object(sys.stdout, "isatty", return_value=False):
            result = format_shloka_rainbow(s)
        assert s["english"] in result
        assert s["ref"] in result

    def test_with_none(self):
        with patch.object(sys.stdout, "isatty", return_value=False):
            result = format_shloka_rainbow()
        assert "Gita" in result
