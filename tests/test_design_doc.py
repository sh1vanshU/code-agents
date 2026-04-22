"""Tests for the design document generator."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from code_agents.knowledge.design_doc import (
    DesignDocGenerator, DesignDoc, Option,
)


class TestOption:
    """Test Option dataclass."""

    def test_defaults(self):
        opt = Option(name="A", description="Option A")
        assert opt.effort == "medium"
        assert opt.risk == "low"
        assert opt.recommended is False

    def test_custom(self):
        opt = Option(name="B", description="B", pros=["fast"], cons=["risky"], effort="high", recommended=True)
        assert opt.recommended is True
        assert len(opt.pros) == 1


class TestDesignDoc:
    """Test DesignDoc rendering."""

    def test_to_markdown_basic(self):
        doc = DesignDoc(
            title="Test Design",
            author="Test User",
            date="2026-01-01",
            problem_statement="We need a solution",
        )
        md = doc.to_markdown()
        assert "# Test Design" in md
        assert "Test User" in md
        assert "Problem Statement" in md

    def test_to_markdown_with_options(self):
        doc = DesignDoc(
            title="Test", problem_statement="problem",
            options=[
                Option(name="A", description="Option A", pros=["good"], cons=["bad"], recommended=True),
                Option(name="B", description="Option B"),
            ],
        )
        md = doc.to_markdown()
        assert "Option 1: A (Recommended)" in md
        assert "Option 2: B" in md
        assert "**Pros:**" in md

    def test_to_markdown_with_risks(self):
        doc = DesignDoc(title="T", problem_statement="p", risks=["Data loss risk"])
        md = doc.to_markdown()
        assert "Risks" in md
        assert "Data loss risk" in md

    def test_to_markdown_with_plan(self):
        doc = DesignDoc(title="T", problem_statement="p", implementation_plan=["Step 1", "Step 2"])
        md = doc.to_markdown()
        assert "1. Step 1" in md
        assert "2. Step 2" in md


class TestDesignDocGenerator:
    """Test DesignDocGenerator."""

    def test_generate_basic(self, tmp_path):
        gen = DesignDocGenerator(cwd=str(tmp_path))
        with patch.object(gen, "_get_git_author", return_value="Test User"):
            doc = gen.generate(
                title="Cache Strategy",
                problem="API is slow, need caching",
            )
        assert doc.title == "Cache Strategy"
        assert doc.author == "Test User"
        assert doc.status == "draft"
        assert len(doc.options) > 0

    def test_generate_with_custom_options(self, tmp_path):
        gen = DesignDocGenerator(cwd=str(tmp_path))
        with patch.object(gen, "_get_git_author", return_value="User"):
            doc = gen.generate(
                title="DB Choice",
                problem="Need a database",
                options=[
                    {"name": "PostgreSQL", "description": "Relational DB", "pros": ["mature"], "recommended": True},
                    {"name": "MongoDB", "description": "Document DB", "cons": ["no joins"]},
                ],
            )
        assert len(doc.options) == 2
        assert doc.options[0].recommended is True
        assert "PostgreSQL" in doc.decision

    def test_generate_with_goals(self, tmp_path):
        gen = DesignDocGenerator(cwd=str(tmp_path))
        with patch.object(gen, "_get_git_author", return_value="User"):
            doc = gen.generate(
                title="T", problem="P",
                goals=["Reduce latency"], non_goals=["Rewrite everything"],
            )
        assert "Reduce latency" in doc.goals
        assert "Rewrite everything" in doc.non_goals

    def test_infer_goals_performance(self, tmp_path):
        gen = DesignDocGenerator(cwd=str(tmp_path))
        goals = gen._infer_goals("The API is slow and needs performance improvement")
        assert any("performance" in g.lower() for g in goals)

    def test_infer_goals_security(self, tmp_path):
        gen = DesignDocGenerator(cwd=str(tmp_path))
        goals = gen._infer_goals("We have a security vulnerability in auth")
        assert any("security" in g.lower() for g in goals)

    def test_save(self, tmp_path):
        gen = DesignDocGenerator(cwd=str(tmp_path))
        doc = DesignDoc(title="Test Doc", date="2026-01-01", problem_statement="p")
        path = gen.save(doc, output_dir=str(tmp_path / "docs"))
        assert os.path.isfile(path)
        assert "test-doc" in path

    def test_identify_risks_with_data(self, tmp_path):
        gen = DesignDocGenerator(cwd=str(tmp_path))
        options = [Option(name="A", description="A", risk="high")]
        risks = gen._identify_risks(options, "We need to migrate data")
        assert any("data" in r.lower() for r in risks)
