"""Tests for code_agents.requirement_confirm — requirement confirmation gate."""

import os
import unittest
from unittest.mock import patch


class TestIsSimpleConfirmation(unittest.TestCase):
    """Test is_simple_confirmation() — detects bypass inputs."""

    def test_exact_matches(self):
        from code_agents.agent_system.requirement_confirm import is_simple_confirmation
        for word in ("yes", "ok", "go ahead", "proceed", "lgtm", "sure",
                     "confirmed", "do it", "looks good", "approved", "yep",
                     "ship it", "execute", "go for it", "no changes"):
            self.assertTrue(is_simple_confirmation(word), f"Should match: {word!r}")

    def test_case_insensitive(self):
        from code_agents.agent_system.requirement_confirm import is_simple_confirmation
        self.assertTrue(is_simple_confirmation("YES"))
        self.assertTrue(is_simple_confirmation("Go Ahead"))
        self.assertTrue(is_simple_confirmation("LGTM"))

    def test_with_trailing_punctuation(self):
        from code_agents.agent_system.requirement_confirm import is_simple_confirmation
        self.assertTrue(is_simple_confirmation("yes!"))
        self.assertTrue(is_simple_confirmation("ok."))
        self.assertTrue(is_simple_confirmation("go ahead,"))

    def test_prefix_with_please(self):
        from code_agents.agent_system.requirement_confirm import is_simple_confirmation
        self.assertTrue(is_simple_confirmation("yes please"))
        self.assertTrue(is_simple_confirmation("ok, thanks"))
        self.assertTrue(is_simple_confirmation("go ahead, thank you"))

    def test_not_confirmation_with_edits(self):
        from code_agents.agent_system.requirement_confirm import is_simple_confirmation
        self.assertFalse(is_simple_confirmation("yes, but also add logging to the module"))
        self.assertFalse(is_simple_confirmation("ok change the DB schema too"))

    def test_not_confirmation_for_tasks(self):
        from code_agents.agent_system.requirement_confirm import is_simple_confirmation
        self.assertFalse(is_simple_confirmation("refactor the auth module to use JWT"))
        self.assertFalse(is_simple_confirmation("fix the bug in login.py"))
        self.assertFalse(is_simple_confirmation("add unit tests for the API endpoints"))

    def test_empty_and_whitespace(self):
        from code_agents.agent_system.requirement_confirm import is_simple_confirmation
        self.assertFalse(is_simple_confirmation(""))
        self.assertFalse(is_simple_confirmation("   "))

    def test_single_char_y(self):
        from code_agents.agent_system.requirement_confirm import is_simple_confirmation
        self.assertTrue(is_simple_confirmation("y"))


class TestShouldConfirm(unittest.TestCase):
    """Test should_confirm() — decides if input needs spec generation."""

    def test_task_with_action_verb(self):
        from code_agents.agent_system.requirement_confirm import should_confirm
        self.assertTrue(should_confirm("refactor the auth module to use JWT tokens"))
        self.assertTrue(should_confirm("fix the login bug in the dashboard"))
        self.assertTrue(should_confirm("add unit tests for the backend API"))

    def test_simple_confirmation_bypasses(self):
        from code_agents.agent_system.requirement_confirm import should_confirm
        self.assertFalse(should_confirm("yes"))
        self.assertFalse(should_confirm("go ahead"))
        self.assertFalse(should_confirm("ok"))

    def test_slash_commands_skip(self):
        from code_agents.agent_system.requirement_confirm import should_confirm
        self.assertFalse(should_confirm("/agent code-writer"))
        self.assertFalse(should_confirm("/plan"))
        self.assertFalse(should_confirm("/help"))

    def test_shell_escape_skip(self):
        from code_agents.agent_system.requirement_confirm import should_confirm
        self.assertFalse(should_confirm("! ls -la"))

    def test_short_input_skip(self):
        from code_agents.agent_system.requirement_confirm import should_confirm
        self.assertFalse(should_confirm("what's this?"))

    def test_no_action_verb_skip(self):
        from code_agents.agent_system.requirement_confirm import should_confirm
        self.assertFalse(should_confirm("what does this function do in the codebase?"))

    def test_disabled_via_env(self):
        from code_agents.agent_system.requirement_confirm import should_confirm
        with patch.dict(os.environ, {"CODE_AGENTS_REQUIRE_CONFIRM": "false"}):
            self.assertFalse(should_confirm("refactor the auth module to use JWT"))

    def test_disabled_via_state(self):
        from code_agents.agent_system.requirement_confirm import should_confirm
        state = {"_require_confirm_enabled": False}
        self.assertFalse(should_confirm("refactor the auth module to use JWT", state))

    def test_disabled_in_superpower(self):
        from code_agents.agent_system.requirement_confirm import should_confirm
        state = {"superpower": True}
        self.assertFalse(should_confirm("refactor the auth module to use JWT", state))


class TestIsConfirmEnabled(unittest.TestCase):
    """Test is_confirm_enabled() — feature toggle."""

    def test_enabled_by_default(self):
        from code_agents.agent_system.requirement_confirm import is_confirm_enabled
        self.assertTrue(is_confirm_enabled())

    def test_disabled_by_env(self):
        from code_agents.agent_system.requirement_confirm import is_confirm_enabled
        for val in ("false", "0", "no", "off"):
            with patch.dict(os.environ, {"CODE_AGENTS_REQUIRE_CONFIRM": val}):
                self.assertFalse(is_confirm_enabled(), f"Should be disabled for: {val}")

    def test_disabled_by_state(self):
        from code_agents.agent_system.requirement_confirm import is_confirm_enabled
        self.assertFalse(is_confirm_enabled({"_require_confirm_enabled": False}))

    def test_disabled_by_superpower(self):
        from code_agents.agent_system.requirement_confirm import is_confirm_enabled
        self.assertFalse(is_confirm_enabled({"superpower": True}))


class TestPromptBuilders(unittest.TestCase):
    """Test build_spec_prompt() and format_confirmed_spec()."""

    def test_build_spec_prompt_contains_key_phrases(self):
        from code_agents.agent_system.requirement_confirm import build_spec_prompt
        prompt = build_spec_prompt()
        self.assertIn("REQUIREMENT SPECIFICATION", prompt)
        self.assertIn("Do NOT execute", prompt)
        self.assertIn("Objective", prompt)
        self.assertIn("Scope", prompt)
        self.assertIn("Go ahead", prompt)

    def test_format_confirmed_spec(self):
        from code_agents.agent_system.requirement_confirm import format_confirmed_spec
        spec = "**Objective:** Refactor auth\n**Scope:** 1. Replace sessions with JWT"
        result = format_confirmed_spec(spec)
        self.assertIn("Confirmed Requirement", result)
        self.assertIn("Refactor auth", result)
        self.assertIn("Proceed with implementation", result)

    def test_format_confirmed_spec_strips_whitespace(self):
        from code_agents.agent_system.requirement_confirm import format_confirmed_spec
        result = format_confirmed_spec("  some spec  \n\n")
        self.assertIn("some spec", result)


class TestRequirementStatus(unittest.TestCase):
    """Test RequirementStatus enum."""

    def test_values(self):
        from code_agents.agent_system.requirement_confirm import RequirementStatus
        self.assertEqual(RequirementStatus.NONE, "none")
        self.assertEqual(RequirementStatus.PENDING, "pending")
        self.assertEqual(RequirementStatus.CONFIRMED, "confirmed")

    def test_str_comparison(self):
        from code_agents.agent_system.requirement_confirm import RequirementStatus
        self.assertEqual(RequirementStatus.PENDING, RequirementStatus("pending"))


if __name__ == "__main__":
    unittest.main()
