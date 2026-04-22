"""Tests for the onboarding agent module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.knowledge.onboarding_agent import OnboardingAgent


class TestStartTour:
    """Test onboarding tour generation."""

    def test_generates_tour(self, tmp_path):
        # Create minimal project structure
        (tmp_path / "README.md").write_text("# My Project\nA test project for testing.\n")
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'\n")
        (tmp_path / ".git").mkdir()
        agent = OnboardingAgent(str(tmp_path))
        tour = agent.start_tour()
        assert "Welcome" in tour
        assert "Project Overview" in tour
        assert "Setup Checklist" in tour
        assert "First Task" in tour

    def test_tour_with_empty_dir(self, tmp_path):
        agent = OnboardingAgent(str(tmp_path))
        tour = agent.start_tour()
        assert "Welcome" in tour
        # Should handle missing README gracefully
        assert "No README" in tour or "Project Overview" in tour


class TestProjectOverview:
    """Test README-based overview extraction."""

    def test_extracts_description(self, tmp_path):
        (tmp_path / "README.md").write_text("# Project\n\nThis is a great project for doing things.\n")
        agent = OnboardingAgent(str(tmp_path))
        overview = agent._project_overview()
        assert "great project" in overview

    def test_no_readme(self, tmp_path):
        agent = OnboardingAgent(str(tmp_path))
        overview = agent._project_overview()
        assert "No README" in overview

    def test_readme_with_badges(self, tmp_path):
        (tmp_path / "README.md").write_text("# Project\n![badge](url)\n\nActual description.\n")
        agent = OnboardingAgent(str(tmp_path))
        overview = agent._project_overview()
        assert "Actual description" in overview


class TestKeyFiles:
    """Test key file detection."""

    def test_detects_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n")
        agent = OnboardingAgent(str(tmp_path))
        key_files = agent._key_files()
        paths = [kf["path"] for kf in key_files]
        assert "pyproject.toml" in paths

    def test_detects_dockerfile(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("FROM python:3.10\n")
        agent = OnboardingAgent(str(tmp_path))
        key_files = agent._key_files()
        paths = [kf["path"] for kf in key_files]
        assert "Dockerfile" in paths

    def test_no_key_files(self, tmp_path):
        agent = OnboardingAgent(str(tmp_path))
        assert agent._key_files() == []


class TestSetupChecklist:
    """Test setup checklist generation."""

    def test_git_check(self, tmp_path):
        (tmp_path / ".git").mkdir()
        agent = OnboardingAgent(str(tmp_path))
        checklist = agent._setup_checklist()
        git_item = next(i for i in checklist if "Git" in i["description"])
        assert git_item["exists"] is True

    def test_poetry_check(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool]\n")
        agent = OnboardingAgent(str(tmp_path))
        checklist = agent._setup_checklist()
        poetry_items = [i for i in checklist if "Poetry" in i["description"]]
        assert len(poetry_items) == 1

    def test_env_check(self, tmp_path):
        (tmp_path / ".env.example").write_text("API_KEY=xxx\n")
        agent = OnboardingAgent(str(tmp_path))
        checklist = agent._setup_checklist()
        env_items = [i for i in checklist if "Environment" in i["description"]]
        assert len(env_items) == 1


class TestFirstTask:
    """Test first task suggestion."""

    def test_with_contributing(self, tmp_path):
        (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\n")
        agent = OnboardingAgent(str(tmp_path))
        task = agent._first_task()
        assert "CONTRIBUTING" in task or "good-first-issue" in task

    def test_default_suggestion(self, tmp_path):
        agent = OnboardingAgent(str(tmp_path))
        task = agent._first_task()
        assert len(task) > 0


class TestProjectStructure:
    """Test project structure rendering."""

    def test_renders_dirs_and_files(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("# main\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "README.md").write_text("# readme\n")
        agent = OnboardingAgent(str(tmp_path))
        structure = agent._project_structure()
        assert "src/" in structure
        assert "tests/" in structure
        assert "README.md" in structure

    def test_empty_dir(self, tmp_path):
        agent = OnboardingAgent(str(tmp_path))
        structure = agent._project_structure()
        # Either shows nothing or "empty directory"
        assert structure is not None
