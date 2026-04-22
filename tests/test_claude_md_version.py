"""Tests for code_agents.claude_md_version — CLAUDE.md semantic versioning."""

import os
import tempfile
import unittest


class TestGetCurrentVersion(unittest.TestCase):
    """Test get_current_version() — parses version from CLAUDE.md."""

    def test_version_present(self):
        from code_agents.knowledge.claude_md_version import get_current_version
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("<!-- version: 2.3.4 -->\n# Title\n")
            f.flush()
            self.assertEqual(get_current_version(f.name), (2, 3, 4))
            os.unlink(f.name)

    def test_no_version(self):
        from code_agents.knowledge.claude_md_version import get_current_version
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Title\nNo version here\n")
            f.flush()
            self.assertEqual(get_current_version(f.name), (0, 0, 0))
            os.unlink(f.name)

    def test_file_not_found(self):
        from code_agents.knowledge.claude_md_version import get_current_version
        self.assertEqual(get_current_version("/nonexistent/CLAUDE.md"), (0, 0, 0))

    def test_version_with_spaces(self):
        from code_agents.knowledge.claude_md_version import get_current_version
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("<!--  version:  1.0.0  -->\n# Title\n")
            f.flush()
            self.assertEqual(get_current_version(f.name), (1, 0, 0))
            os.unlink(f.name)


class TestBumpVersion(unittest.TestCase):
    """Test bump_version() — increments version in file."""

    def _make_file(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_patch_bump(self):
        from code_agents.knowledge.claude_md_version import bump_version
        path = self._make_file("<!-- version: 1.0.0 -->\n# Title\n")
        result = bump_version(path, "patch")
        self.assertEqual(result, (1, 0, 1))
        with open(path) as f:
            self.assertIn("1.0.1", f.read())
        os.unlink(path)

    def test_minor_bump(self):
        from code_agents.knowledge.claude_md_version import bump_version
        path = self._make_file("<!-- version: 1.2.3 -->\n# Title\n")
        result = bump_version(path, "minor")
        self.assertEqual(result, (1, 3, 0))
        os.unlink(path)

    def test_major_bump(self):
        from code_agents.knowledge.claude_md_version import bump_version
        path = self._make_file("<!-- version: 1.2.3 -->\n# Title\n")
        result = bump_version(path, "major")
        self.assertEqual(result, (2, 0, 0))
        os.unlink(path)

    def test_no_version_creates_header(self):
        from code_agents.knowledge.claude_md_version import bump_version
        path = self._make_file("# Title\nContent\n")
        result = bump_version(path, "patch")
        self.assertEqual(result, (1, 0, 1))
        with open(path) as f:
            content = f.read()
            self.assertIn("1.0.1", content)
            self.assertIn("# Title", content)
        os.unlink(path)

    def test_nonexistent_file(self):
        from code_agents.knowledge.claude_md_version import bump_version
        result = bump_version("/nonexistent/CLAUDE.md")
        self.assertEqual(result, (0, 0, 0))


class TestEnsureVersionHeader(unittest.TestCase):
    """Test ensure_version_header()."""

    def test_adds_header(self):
        from code_agents.knowledge.claude_md_version import ensure_version_header, get_current_version
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
        f.write("# Title\n")
        f.close()
        ensure_version_header(f.name)
        self.assertEqual(get_current_version(f.name), (1, 0, 0))
        os.unlink(f.name)

    def test_does_not_duplicate(self):
        from code_agents.knowledge.claude_md_version import ensure_version_header
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
        f.write("<!-- version: 2.0.0 -->\n# Title\n")
        f.close()
        ensure_version_header(f.name)
        with open(f.name) as fh:
            content = fh.read()
            self.assertEqual(content.count("version:"), 1)
        os.unlink(f.name)


class TestDetectBumpType(unittest.TestCase):
    """Test detect_bump_type() — diff analysis."""

    def test_major_new_agent(self):
        from code_agents.knowledge.claude_md_version import detect_bump_type
        diff = "+agents/new_agent/new_agent.yaml"
        self.assertEqual(detect_bump_type(diff), "major")

    def test_minor_new_section(self):
        from code_agents.knowledge.claude_md_version import detect_bump_type
        diff = "+## New Feature Section"
        self.assertEqual(detect_bump_type(diff), "minor")

    def test_minor_new_env_var(self):
        from code_agents.knowledge.claude_md_version import detect_bump_type
        diff = "+| `NEW_ENV_VAR` | purpose | default |"
        self.assertEqual(detect_bump_type(diff), "minor")

    def test_patch_default(self):
        from code_agents.knowledge.claude_md_version import detect_bump_type
        diff = "+Fixed a typo in the docs"
        self.assertEqual(detect_bump_type(diff), "patch")

    def test_empty_diff(self):
        from code_agents.knowledge.claude_md_version import detect_bump_type
        self.assertEqual(detect_bump_type(""), "patch")


class TestFormatVersion(unittest.TestCase):
    """Test format_version()."""

    def test_format(self):
        from code_agents.knowledge.claude_md_version import format_version
        self.assertEqual(format_version(1, 2, 3), "1.2.3")
        self.assertEqual(format_version(0, 0, 0), "0.0.0")


if __name__ == "__main__":
    unittest.main()
