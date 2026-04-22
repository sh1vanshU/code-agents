"""Tests for Codebase Q&A."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.knowledge.codebase_qa import (
    CodebaseQA,
    QAAnswer,
    QAContext,
    QASource,
    format_qa_answer,
)


class TestCodebaseQA:
    """Tests for CodebaseQA."""

    def test_init(self):
        qa = CodebaseQA()
        assert os.path.isabs(qa.cwd)

    def test_parse_question_locate(self):
        qa = CodebaseQA()
        parsed = qa._parse_question("where is the database config?")
        assert parsed["intent"] == "locate"
        assert "database" in parsed["terms"] or "config" in parsed["terms"]

    def test_parse_question_explain(self):
        qa = CodebaseQA()
        parsed = qa._parse_question("how does authentication work?")
        assert parsed["intent"] == "explain"

    def test_parse_question_enumerate(self):
        qa = CodebaseQA()
        parsed = qa._parse_question("list all API endpoints")
        assert parsed["intent"] == "enumerate"

    def test_parse_question_rationale(self):
        qa = CodebaseQA()
        parsed = qa._parse_question("why do we use Redis for caching?")
        assert parsed["intent"] == "rationale"

    def test_parse_question_concepts(self):
        qa = CodebaseQA()
        parsed = qa._parse_question("how does the auth login flow work?")
        assert "auth" in parsed["concepts"]

    def test_parse_question_symbols(self):
        qa = CodebaseQA()
        parsed = qa._parse_question("what does UserManager do?")
        assert "UserManager" in parsed["symbols"]

    def test_parse_question_snake_case(self):
        qa = CodebaseQA()
        parsed = qa._parse_question("where is create_user defined?")
        assert "create_user" in parsed["symbols"]

    def test_parse_question_file_ref(self):
        qa = CodebaseQA()
        parsed = qa._parse_question("explain src/auth.py")
        assert "src/auth.py" in parsed["files"]

    @patch.object(CodebaseQA, "_grep_code")
    def test_gather_context_with_symbols(self, mock_grep):
        mock_grep.return_value = [
            {"file": "src/auth.py", "line": 10, "match": "class AuthManager:"},
        ]
        qa = CodebaseQA()
        parsed = {"terms": ["auth"], "concepts": ["auth"], "symbols": ["AuthManager"], "files": [], "intent": "explain"}
        context = qa._gather_context(parsed)
        assert "src/auth.py" in context.relevant_files

    def test_compose_answer_locate(self):
        qa = CodebaseQA()
        parsed = {"intent": "locate", "terms": [], "concepts": [], "symbols": [], "files": []}
        context = QAContext(relevant_files=["src/config.py", "src/settings.py"])
        answer = qa._compose_answer("where is config?", parsed, context)
        assert "src/config.py" in answer

    def test_compose_answer_empty(self):
        qa = CodebaseQA()
        parsed = {"intent": "explain", "terms": [], "concepts": [], "symbols": [], "files": []}
        context = QAContext()
        answer = qa._compose_answer("random question", parsed, context)
        assert "could not find" in answer.lower()

    def test_estimate_confidence_full(self):
        qa = CodebaseQA()
        context = QAContext(
            relevant_files=["a.py", "b.py", "c.py"],
            relevant_symbols=[{"file": "a.py", "line": 1, "match": "x"}] * 3,
            related_docs=["README.md"],
            architecture_notes=["Note 1"],
        )
        conf = qa._estimate_confidence(context)
        assert conf >= 0.5

    def test_estimate_confidence_empty(self):
        qa = CodebaseQA()
        context = QAContext()
        assert qa._estimate_confidence(context) == 0.0

    def test_extract_sources(self):
        qa = CodebaseQA()
        context = QAContext(
            relevant_symbols=[
                {"file": "auth.py", "line": 10, "match": "class Auth"},
            ],
            relevant_files=["auth.py", "config.py"],
        )
        sources = qa._extract_sources(context)
        assert len(sources) >= 2
        assert sources[0].file == "auth.py"

    def test_search_docs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "README.md")).write_text("# Auth\nAuthentication docs")
            Path(os.path.join(tmpdir, "CHANGELOG.md")).write_text("# Changes\nBug fixes")
            qa = CodebaseQA(cwd=tmpdir)
            docs = qa._search_docs(["auth"])
            assert any("README" in d for d in docs)

    def test_analyze_architecture(self):
        qa = CodebaseQA()
        notes = qa._analyze_architecture(
            ["src/routers/auth.py", "tests/test_auth.py"],
            ["auth"],
        )
        assert any("router" in n.lower() for n in notes)
        assert any("test" in n.lower() for n in notes)

    @patch.object(CodebaseQA, "_grep_code", return_value=[])
    def test_ask_full_pipeline(self, mock_grep):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "README.md")).write_text("# Project\nTest project")
            qa = CodebaseQA(cwd=tmpdir)
            answer = qa.ask("what is this project?")
            assert answer.question == "what is this project?"
            assert isinstance(answer.confidence, float)


class TestFormatQAAnswer:
    """Tests for format_qa_answer."""

    def test_format_with_sources(self):
        answer = QAAnswer(
            question="how does auth work?",
            answer="Auth is handled in src/auth.py",
            confidence=0.8,
            sources=[QASource(file="src/auth.py", line_start=10, snippet="class Auth")],
        )
        output = format_qa_answer(answer)
        assert "how does auth work?" in output
        assert "80%" in output
        assert "src/auth.py" in output

    def test_format_empty(self):
        answer = QAAnswer(question="test", answer="No info", confidence=0.0)
        output = format_qa_answer(answer)
        assert "test" in output
        assert "0%" in output
