"""Tests for the codebase dialogue module."""

from __future__ import annotations

import os
import pytest

from code_agents.knowledge.codebase_dialogue import (
    CodebaseDialogue, DialogueResult, FileContext, ask_codebase,
)


class TestCodebaseDialogue:
    """Test CodebaseDialogue methods."""

    def test_init(self, tmp_path):
        dialogue = CodebaseDialogue(cwd=str(tmp_path))
        assert dialogue.cwd == str(tmp_path)

    def test_index_empty_dir(self, tmp_path):
        dialogue = CodebaseDialogue(cwd=str(tmp_path))
        count = dialogue.index()
        assert count == 0

    def test_index_files(self, tmp_path):
        (tmp_path / "app.py").write_text('"""Main application."""\ndef main():\n    pass\n')
        (tmp_path / "utils.py").write_text("# Utility functions\ndef helper():\n    pass\n")
        dialogue = CodebaseDialogue(cwd=str(tmp_path))
        count = dialogue.index()
        assert count == 2

    def test_ask_finds_relevant_files(self, tmp_path):
        (tmp_path / "auth.py").write_text('"""Authentication module."""\ndef login(user):\n    pass\n')
        (tmp_path / "payment.py").write_text('"""Payment processing."""\ndef charge(amount):\n    pass\n')

        dialogue = CodebaseDialogue(cwd=str(tmp_path))
        result = dialogue.ask("How does authentication work?")
        assert isinstance(result, DialogueResult)
        assert len(result.relevant_files) >= 1
        assert any("auth" in f for f in result.relevant_files)

    def test_ask_returns_follow_ups(self, tmp_path):
        (tmp_path / "service.py").write_text("def process():\n    pass\n")
        dialogue = CodebaseDialogue(cwd=str(tmp_path))
        result = dialogue.ask("What does the service do?")
        assert len(result.follow_up_questions) >= 1

    def test_history_persists(self, tmp_path):
        (tmp_path / "module.py").write_text("def func():\n    pass\n")
        dialogue = CodebaseDialogue(cwd=str(tmp_path))
        dialogue.ask("What is in module.py?")
        dialogue.ask("Tell me more about func")
        history = dialogue.get_history()
        assert len(history) == 2

    def test_convenience_function(self, tmp_path):
        (tmp_path / "app.py").write_text("def run():\n    pass\n")
        result = ask_codebase(cwd=str(tmp_path), question="What does app.py do?")
        assert isinstance(result, dict)
        assert "answer" in result
        assert "confidence" in result
