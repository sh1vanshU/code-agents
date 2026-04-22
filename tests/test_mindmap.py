"""Tests for code_agents.mindmap — Repo Mindmap Generator."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from code_agents.ui.mindmap import (
    MindmapNode,
    MindmapResult,
    RepoMindmap,
    format_html,
    format_mermaid,
    format_terminal,
)


# ---------------------------------------------------------------------------
# TestMindmapNode
# ---------------------------------------------------------------------------

class TestMindmapNode:
    """Test MindmapNode dataclass."""

    def test_construction(self):
        node = MindmapNode(name="src", kind="directory")
        assert node.name == "src"
        assert node.kind == "directory"
        assert node.children == []
        assert node.file == ""
        assert node.metadata == {}

    def test_construction_with_metadata(self):
        node = MindmapNode(
            name="app.py",
            kind="entrypoint",
            file="/repo/app.py",
            metadata={"type": "flask"},
        )
        assert node.file == "/repo/app.py"
        assert node.metadata["type"] == "flask"

    def test_add_child(self):
        parent = MindmapNode(name="src", kind="directory")
        child = parent.add_child(MindmapNode(name="main.py", kind="module"))
        assert len(parent.children) == 1
        assert parent.children[0] is child
        assert child.name == "main.py"

    def test_child_count(self):
        root = MindmapNode(name="root", kind="directory")
        child1 = root.add_child(MindmapNode(name="a", kind="directory"))
        child1.add_child(MindmapNode(name="b", kind="module"))
        child1.add_child(MindmapNode(name="c", kind="module"))
        root.add_child(MindmapNode(name="d", kind="module"))
        # root has 2 direct children; child1 has 2 children => total descendants = 4
        assert root.child_count() == 4

    def test_child_count_empty(self):
        node = MindmapNode(name="leaf", kind="module")
        assert node.child_count() == 0


# ---------------------------------------------------------------------------
# TestRepoMindmap
# ---------------------------------------------------------------------------

class TestRepoMindmap:
    """Test RepoMindmap builder with tmp_path repos."""

    def _create_mini_repo(self, tmp_path: Path) -> Path:
        """Create a small test repository structure."""
        repo = tmp_path / "test-repo"
        repo.mkdir()

        # Source files
        src = repo / "src"
        src.mkdir()
        (src / "main.py").write_text("def main(): pass\n")
        (src / "utils.py").write_text("def helper(): pass\n")

        # Nested dir
        lib = src / "lib"
        lib.mkdir()
        (lib / "core.py").write_text("class Core: pass\n")

        # Entry point
        (repo / "app.py").write_text("from src.main import main\n")

        # Config
        (repo / "pyproject.toml").write_text(
            "[tool.poetry]\nname = 'test'\n[tool.poetry.scripts]\ncli = 'src.main:main'\n"
        )

        return repo

    def test_build_basic(self, tmp_path):
        repo = self._create_mini_repo(tmp_path)
        mindmap = RepoMindmap(repo_path=str(repo), depth=3)
        result = mindmap.build()

        assert isinstance(result, MindmapResult)
        assert result.root.name == "test-repo"
        assert result.root.kind == "directory"
        assert len(result.root.children) > 0
        assert result.stats["repo_name"] == "test-repo"
        assert result.stats["directories"] > 0

    def test_build_with_focus(self, tmp_path):
        repo = self._create_mini_repo(tmp_path)
        mindmap = RepoMindmap(repo_path=str(repo), depth=3, focus="src")
        result = mindmap.build()

        # Root should contain focused subtree
        child_names = [c.name for c in result.root.children]
        assert "lib" in child_names or "main.py" in child_names

    def test_build_focus_file(self, tmp_path):
        repo = self._create_mini_repo(tmp_path)
        mindmap = RepoMindmap(repo_path=str(repo), depth=3, focus="app.py")
        result = mindmap.build()

        assert any(c.name == "app.py" for c in result.root.children)

    def test_invalid_repo_path(self):
        with pytest.raises(ValueError, match="Not a valid directory"):
            RepoMindmap(repo_path="/nonexistent/path/xyz")

    def test_focus_path_traversal(self, tmp_path):
        repo = self._create_mini_repo(tmp_path)
        mindmap = RepoMindmap(repo_path=str(repo), depth=3, focus="../../etc/passwd")
        with pytest.raises(ValueError, match="escapes repo"):
            mindmap.build()

    def test_depth_clamped(self, tmp_path):
        repo = self._create_mini_repo(tmp_path)
        m1 = RepoMindmap(repo_path=str(repo), depth=0)
        assert m1.depth == 1  # clamped to min 1
        m2 = RepoMindmap(repo_path=str(repo), depth=100)
        assert m2.depth == 10  # clamped to max 10

    def test_entry_points_detected(self, tmp_path):
        repo = self._create_mini_repo(tmp_path)
        mindmap = RepoMindmap(repo_path=str(repo), depth=3)
        result = mindmap.build()

        ep_names = [ep.name for ep in result.entry_points]
        # Should detect app.py and pyproject.toml scripts
        assert any("app.py" in n for n in ep_names)
        assert any("pyproject.toml" in n for n in ep_names)

    def test_agents_detected(self, tmp_path):
        repo = self._create_mini_repo(tmp_path)

        # Create agents dir
        agents_dir = repo / "agents"
        agents_dir.mkdir()
        writer = agents_dir / "code-writer"
        writer.mkdir()
        (writer / "code-writer.yaml").write_text("name: code-writer\n")
        skills = writer / "skills"
        skills.mkdir()
        (skills / "refactor.md").write_text("# Refactor\n")

        mindmap = RepoMindmap(repo_path=str(repo), depth=3)
        result = mindmap.build()

        assert len(result.agents) == 1
        assert result.agents[0].name == "code-writer"
        assert result.agents[0].metadata["skill_count"] == 1

    def test_integrations_from_config_files(self, tmp_path):
        repo = self._create_mini_repo(tmp_path)
        (repo / "Dockerfile").write_text("FROM python:3.10\n")
        (repo / "Jenkinsfile").write_text("pipeline {}\n")

        mindmap = RepoMindmap(repo_path=str(repo), depth=3)
        result = mindmap.build()

        integ_names = [i.name for i in result.integrations]
        assert "Docker" in integ_names
        assert "Jenkins CI" in integ_names

    def test_skips_hidden_dirs(self, tmp_path):
        repo = self._create_mini_repo(tmp_path)
        git_dir = repo / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("gitconfig\n")

        mindmap = RepoMindmap(repo_path=str(repo), depth=3)
        result = mindmap.build()

        child_names = [c.name for c in result.root.children]
        assert ".git" not in child_names


# ---------------------------------------------------------------------------
# TestFormatTerminal
# ---------------------------------------------------------------------------

class TestFormatTerminal:
    """Test terminal (ANSI) formatter."""

    def test_contains_tree_markers(self):
        root = MindmapNode(name="repo", kind="directory")
        root.add_child(MindmapNode(name="src", kind="directory"))
        root.add_child(MindmapNode(name="README.md", kind="module"))
        result = MindmapResult(root=root, stats={"repo_name": "repo", "language": "Python",
                                                   "framework": "FastAPI", "build_tool": "Poetry",
                                                   "directories": 1, "modules": 1,
                                                   "entry_points": 0, "agents": 0, "integrations": 0})
        output = format_terminal(result, depth=3)

        assert "├──" in output or "└──" in output
        assert "repo" in output
        assert "src" in output

    def test_contains_ansi_codes(self):
        root = MindmapNode(name="repo", kind="directory")
        result = MindmapResult(root=root, stats={"repo_name": "repo", "language": "?",
                                                   "framework": "?", "build_tool": "?",
                                                   "directories": 0, "modules": 0,
                                                   "entry_points": 0, "agents": 0, "integrations": 0})
        output = format_terminal(result)
        assert "\033[" in output

    def test_shows_entry_points(self):
        root = MindmapNode(name="repo", kind="directory")
        eps = [MindmapNode(name="app.py", kind="entrypoint")]
        result = MindmapResult(root=root, entry_points=eps,
                               stats={"repo_name": "repo", "language": "?",
                                       "framework": "?", "build_tool": "?",
                                       "directories": 0, "modules": 0,
                                       "entry_points": 1, "agents": 0, "integrations": 0})
        output = format_terminal(result)
        assert "Entry Points" in output
        assert "app.py" in output

    def test_shows_agents(self):
        root = MindmapNode(name="repo", kind="directory")
        agents = [MindmapNode(name="code-writer", kind="agent", metadata={"skill_count": 5})]
        result = MindmapResult(root=root, agents=agents,
                               stats={"repo_name": "repo", "language": "?",
                                       "framework": "?", "build_tool": "?",
                                       "directories": 0, "modules": 0,
                                       "entry_points": 0, "agents": 1, "integrations": 0})
        output = format_terminal(result)
        assert "Agents" in output
        assert "code-writer" in output
        assert "5 skills" in output


# ---------------------------------------------------------------------------
# TestFormatMermaid
# ---------------------------------------------------------------------------

class TestFormatMermaid:
    """Test Mermaid mindmap formatter."""

    def test_starts_with_mindmap(self):
        root = MindmapNode(name="repo", kind="directory")
        result = MindmapResult(root=root, stats={"repo_name": "repo"})
        output = format_mermaid(result)
        assert output.startswith("mindmap")

    def test_contains_root_node(self):
        root = MindmapNode(name="repo", kind="directory")
        result = MindmapResult(root=root, stats={"repo_name": "my-project"})
        output = format_mermaid(result)
        assert "my-project" in output

    def test_contains_child_names(self):
        root = MindmapNode(name="repo", kind="directory")
        root.add_child(MindmapNode(name="src", kind="directory"))
        root.add_child(MindmapNode(name="tests", kind="directory"))
        result = MindmapResult(root=root, stats={"repo_name": "repo"})
        output = format_mermaid(result)
        assert "src" in output
        assert "tests" in output
        assert "Structure" in output

    def test_shows_agents_section(self):
        root = MindmapNode(name="repo", kind="directory")
        agents = [MindmapNode(name="writer", kind="agent", metadata={"skill_count": 3})]
        result = MindmapResult(root=root, agents=agents, stats={"repo_name": "repo"})
        output = format_mermaid(result)
        assert "Agents" in output
        assert "writer" in output


# ---------------------------------------------------------------------------
# TestFormatHtml
# ---------------------------------------------------------------------------

class TestFormatHtml:
    """Test HTML (D3.js) formatter."""

    def test_contains_html_structure(self):
        root = MindmapNode(name="repo", kind="directory")
        result = MindmapResult(root=root, stats={"repo_name": "repo", "language": "Python",
                                                   "framework": "FastAPI", "build_tool": "Poetry",
                                                   "directories": 1, "modules": 0,
                                                   "agents": 0, "integrations": 0})
        output = format_html(result)
        assert "<html" in output
        assert "</html>" in output

    def test_contains_d3_script(self):
        root = MindmapNode(name="repo", kind="directory")
        result = MindmapResult(root=root, stats={"repo_name": "repo", "language": "?",
                                                   "framework": "?", "build_tool": "?",
                                                   "directories": 0, "modules": 0,
                                                   "agents": 0, "integrations": 0})
        output = format_html(result)
        assert "d3js.org" in output or "d3.v7" in output
        assert "<script>" in output

    def test_contains_repo_name(self):
        root = MindmapNode(name="repo", kind="directory")
        result = MindmapResult(root=root, stats={"repo_name": "awesome-app", "language": "?",
                                                   "framework": "?", "build_tool": "?",
                                                   "directories": 0, "modules": 0,
                                                   "agents": 0, "integrations": 0})
        output = format_html(result)
        assert "awesome-app" in output

    def test_contains_json_data(self):
        root = MindmapNode(name="repo", kind="directory")
        root.add_child(MindmapNode(name="src", kind="directory"))
        result = MindmapResult(root=root, stats={"repo_name": "repo", "language": "?",
                                                   "framework": "?", "build_tool": "?",
                                                   "directories": 1, "modules": 0,
                                                   "agents": 0, "integrations": 0})
        output = format_html(result)
        # The JSON data should be embedded in the page
        assert '"name"' in output
        assert '"kind"' in output

    def test_html_output_to_file(self, tmp_path):
        root = MindmapNode(name="repo", kind="directory")
        result = MindmapResult(root=root, stats={"repo_name": "repo", "language": "?",
                                                   "framework": "?", "build_tool": "?",
                                                   "directories": 0, "modules": 0,
                                                   "agents": 0, "integrations": 0})
        output = format_html(result)
        out_file = tmp_path / "mindmap.html"
        out_file.write_text(output, encoding="utf-8")
        assert out_file.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
