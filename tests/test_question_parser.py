"""Tests for code_agents.question_parser — detect questions in agent responses."""
from __future__ import annotations

import pytest

from code_agents.agent_system.question_parser import parse_questions


class TestQHeaderDetection:
    """Detect Q1:/Q2: header format."""

    def test_basic_q_headers(self):
        text = """
Q1: Do you want to build from branch dev_qa4?
  1 — Yes
  2 — No, use main

Q2: Which region?
  1 — IDN
  2 — ARE
  3 — pg2-dev
"""
        qs = parse_questions(text)
        assert len(qs) == 2
        assert "build from branch" in qs[0]["question"]
        assert len(qs[0]["options"]) == 2
        assert "IDN" in qs[1]["options"][0]
        assert len(qs[1]["options"]) == 3

    def test_question_prefix(self):
        text = """
Question 1: Which environment?
  1. Dev
  2. QA
  3. Staging
"""
        qs = parse_questions(text)
        assert len(qs) == 1
        assert "environment" in qs[0]["question"].lower()
        assert len(qs[0]["options"]) == 3

    def test_case_insensitive(self):
        text = """
q1: Pick a service
  1) alpha
  2) beta
"""
        qs = parse_questions(text)
        assert len(qs) == 1

    def test_with_dash_options(self):
        text = """
Q1: Select region
  1 - IDN
  2 - ARE
  3 - pg2
"""
        qs = parse_questions(text)
        assert len(qs) == 1
        assert len(qs[0]["options"]) == 3

    def test_skips_single_option(self):
        text = """
Q1: Confirm?
  1. Yes
"""
        qs = parse_questions(text)
        assert len(qs) == 0  # need ≥2 options


class TestFreeformDetection:
    """Detect question lines ending with ? followed by options."""

    def test_question_with_numbered_list(self):
        text = """
Which region are we targeting?
  1. IDN
  2. ARE
  3. pg2-dev-build-jobs
"""
        qs = parse_questions(text)
        assert len(qs) == 1
        assert "region" in qs[0]["question"].lower()
        assert len(qs[0]["options"]) == 3

    def test_question_with_lettered_options(self):
        text = """
What should we do next?
  a) Build
  b) Deploy
  c) Cancel
"""
        qs = parse_questions(text)
        assert len(qs) == 1
        assert len(qs[0]["options"]) == 3

    def test_short_question_skipped(self):
        text = """
Why?
  1. A
  2. B
"""
        qs = parse_questions(text)
        assert len(qs) == 0  # "Why?" is too short (<10 chars)


class TestCodeBlockStripping:
    """Code blocks should not trigger false positives."""

    def test_numbered_list_in_code_block(self):
        text = """
Here's what to do:
```bash
1. Run tests
2. Build
3. Deploy
```
"""
        qs = parse_questions(text)
        assert len(qs) == 0

    def test_question_outside_code_block(self):
        text = """
```bash
echo hello
```

Which option do you prefer?
  1. Fast build
  2. Full build
"""
        qs = parse_questions(text)
        assert len(qs) == 1


class TestEdgeCases:
    def test_empty_text(self):
        assert parse_questions("") == []

    def test_no_questions(self):
        assert parse_questions("This is just a response with no questions.") == []

    def test_mixed_q_headers_and_freeform(self):
        # Q headers take priority
        text = """
Q1: Build from this branch?
  1. Yes
  2. No

Which region?
  1. IDN
  2. ARE
"""
        qs = parse_questions(text)
        # Q-header detection should find Q1 only
        assert len(qs) >= 1
        assert "branch" in qs[0]["question"].lower()

    def test_real_world_jenkins_response(self):
        text = """
▎ Q1: Do you want me to build pg-acquiring-biz from branch dev_integration_foundry_v2_qa4?
▎ > Q2: Which region are we targeting?
▎ - 1 — IDN (IDN-PGP-BUILD-JOBS-V2 or IDN-PGP-Build-Jobs)
▎ - 2 — ARE (ARE-PGP-Build-Jobs)
▎ - 3 — pg2-dev-build-jobs (generic dev/QA)

Pick a number and I'll drill into that folder's jobs right away.
"""
        qs = parse_questions(text)
        assert len(qs) >= 1
