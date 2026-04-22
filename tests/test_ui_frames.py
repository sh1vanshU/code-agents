"""Tests for ui_frames.py — unified UI frame system."""

import pytest
from code_agents.ui.ui_frames import (
    frame_header, frame_section, frame_status, frame_kv,
    frame_table, frame_list, frame_bar, frame_box, frame_footer,
    frame_empty, _visible_len,
)


class TestFrameHeader:
    def test_contains_title(self):
        out = frame_header("Test Title")
        assert "Test Title" in out

    def test_contains_subtitle(self):
        out = frame_header("Title", subtitle="Sub")
        assert "Sub" in out

    def test_has_borders(self):
        out = frame_header("Title")
        assert "╔" in out
        assert "╚" in out


class TestFrameSection:
    def test_contains_title(self):
        out = frame_section("Section")
        assert "Section" in out

    def test_has_dashes(self):
        out = frame_section("Title")
        assert "──" in out


class TestFrameStatus:
    def test_ok_status(self):
        out = frame_status("ok", "All good")
        assert "All good" in out

    def test_error_status(self):
        out = frame_status("error", "Failed")
        assert "Failed" in out

    def test_with_detail(self):
        out = frame_status("ok", "Server", detail="port 8000")
        assert "Server" in out
        assert "port 8000" in out


class TestFrameKV:
    def test_key_value(self):
        out = frame_kv("Name", "Shivanshu")
        assert "Name" in out
        assert "Shivanshu" in out


class TestFrameTable:
    def test_basic_table(self):
        out = frame_table(["Name", "Age"], [["Alice", "30"], ["Bob", "25"]])
        assert "Name" in out
        assert "Alice" in out
        assert "Bob" in out
        assert "|" in out

    def test_empty_table(self):
        assert frame_table([], []) == ""

    def test_separator_line(self):
        out = frame_table(["A"], [["1"]])
        assert "---" in out


class TestFrameList:
    def test_basic_list(self):
        out = frame_list(["item1", "item2"])
        assert "item1" in out
        assert "item2" in out
        assert "•" in out

    def test_max_items(self):
        items = [f"item{i}" for i in range(20)]
        out = frame_list(items, max_items=5)
        assert "item4" in out
        assert "15 more" in out

    def test_custom_bullet(self):
        out = frame_list(["test"], bullet="→")
        assert "→" in out


class TestFrameBar:
    def test_full_bar(self):
        out = frame_bar(100, 100)
        assert "100%" in out

    def test_half_bar(self):
        out = frame_bar(50, 100)
        assert "50%" in out

    def test_with_label(self):
        out = frame_bar(75, 100, label="coverage")
        assert "coverage" in out


class TestFrameBox:
    def test_contains_content(self):
        out = frame_box("Hello World")
        assert "Hello World" in out

    def test_has_borders(self):
        out = frame_box("Test")
        assert "┌" in out
        assert "└" in out

    def test_with_title(self):
        out = frame_box("Content", title="Box Title")
        assert "Box Title" in out


class TestFrameFooter:
    def test_basic_footer(self):
        out = frame_footer()
        assert "─" in out

    def test_with_message(self):
        out = frame_footer("Done")
        assert "Done" in out


class TestVisibleLen:
    def test_plain_text(self):
        assert _visible_len("hello") == 5

    def test_with_ansi(self):
        assert _visible_len("\x1b[32mhello\x1b[0m") == 5
