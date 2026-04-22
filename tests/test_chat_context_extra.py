"""Extra tests for chat_context.py — covers MCP context, user profile injection,
plan mode context, btw messages, skill suggestions."""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest

from code_agents.chat.chat_context import _build_system_context, _suggest_skills


# ---------------------------------------------------------------------------
# Shared fixture — mocks all lazy-loaded dependencies at their source modules
# ---------------------------------------------------------------------------

def _base_mocks():
    """Return a context manager stack that mocks all lazy imports used by _build_system_context."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch("code_agents.agent_system.rules_loader.load_rules", return_value=""))
    stack.enter_context(patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={}))
    stack.enter_context(patch("code_agents.agent_system.agent_memory.load_memory", return_value=""))
    stack.enter_context(patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value=[]))
    stack.enter_context(patch("code_agents.integrations.mcp_client.get_smart_mcp_context", return_value=""))
    mock_pm = MagicMock()
    mock_pm.is_plan_mode = False
    mock_pm.format_plan.return_value = "  No active plan."
    stack.enter_context(patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=mock_pm))
    stack.enter_context(patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"))
    return stack, mock_pm


# ---------------------------------------------------------------------------
# _build_system_context — basic
# ---------------------------------------------------------------------------


class TestBuildSystemContext:
    def test_basic_context_contains_repo(self):
        stack, _ = _base_mocks()
        with stack:
            ctx = _build_system_context("/tmp/myrepo", "code-writer")
            assert "/tmp/myrepo" in ctx
            assert "myrepo" in ctx

    def test_contains_bash_tool_section(self):
        stack, _ = _base_mocks()
        with stack:
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "Bash Tool" in ctx
            assert "```bash" in ctx

    def test_contains_requirement_protocol(self):
        stack, _ = _base_mocks()
        with stack:
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "Requirement Protocol" in ctx

    def test_contains_questionnaire_hint(self):
        stack, _ = _base_mocks()
        with stack:
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "[QUESTION:" in ctx


# ---------------------------------------------------------------------------
# User profile / role injection
# ---------------------------------------------------------------------------


class TestUserRoleInjection:
    def test_junior_engineer_role(self):
        stack, _ = _base_mocks()
        with stack, patch.dict(os.environ, {"CODE_AGENTS_USER_ROLE": "Junior Engineer"}):
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "Junior Engineer" in ctx
            assert "step by step" in ctx

    def test_senior_engineer_role(self):
        stack, _ = _base_mocks()
        with stack, patch.dict(os.environ, {"CODE_AGENTS_USER_ROLE": "Senior Engineer"}):
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "Be concise" in ctx

    def test_lead_engineer_role(self):
        stack, _ = _base_mocks()
        with stack, patch.dict(os.environ, {"CODE_AGENTS_USER_ROLE": "Lead Engineer"}):
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "architecture" in ctx

    def test_principal_architect_role(self):
        stack, _ = _base_mocks()
        with stack, patch.dict(os.environ, {"CODE_AGENTS_USER_ROLE": "Principal Engineer / Architect"}):
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "Strategic" in ctx

    def test_engineering_manager_role(self):
        stack, _ = _base_mocks()
        with stack, patch.dict(os.environ, {"CODE_AGENTS_USER_ROLE": "Engineering Manager"}):
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "Status summaries" in ctx

    def test_custom_role(self):
        stack, _ = _base_mocks()
        with stack, patch.dict(os.environ, {"CODE_AGENTS_USER_ROLE": "DevOps"}):
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "DevOps" in ctx

    def test_no_role(self):
        stack, _ = _base_mocks()
        env = os.environ.copy()
        env.pop("CODE_AGENTS_USER_ROLE", None)
        with stack, patch.dict(os.environ, env, clear=True):
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "User role:" not in ctx


# ---------------------------------------------------------------------------
# BTW messages
# ---------------------------------------------------------------------------


class TestBtwMessages:
    def test_btw_messages_injected(self):
        stack, _ = _base_mocks()
        with stack:
            ctx = _build_system_context("/tmp/repo", "code-writer", btw_messages=["use Python 3.12", "skip tests"])
            assert "USER UPDATES" in ctx
            assert "use Python 3.12" in ctx
            assert "skip tests" in ctx

    def test_no_btw_messages(self):
        stack, _ = _base_mocks()
        with stack:
            ctx = _build_system_context("/tmp/repo", "code-writer", btw_messages=None)
            assert "USER UPDATES" not in ctx

    def test_empty_btw_messages(self):
        stack, _ = _base_mocks()
        with stack:
            ctx = _build_system_context("/tmp/repo", "code-writer", btw_messages=[])
            assert "USER UPDATES" not in ctx


# ---------------------------------------------------------------------------
# MCP context injection
# ---------------------------------------------------------------------------


class TestMCPContext:
    def test_mcp_context_added(self):
        stack, _ = _base_mocks()
        mcp_text = "--- MCP Tools ---\nTool: my-tool\n--- End MCP ---"
        with stack:
            with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value=["server1"]), \
                 patch("code_agents.integrations.mcp_client.get_smart_mcp_context", return_value=mcp_text):
                ctx = _build_system_context("/tmp/repo", "code-writer")
                assert "MCP Tools" in ctx

    def test_mcp_exception_handled(self):
        stack, _ = _base_mocks()
        with stack:
            with patch("code_agents.integrations.mcp_client.get_servers_for_agent", side_effect=Exception("fail")):
                ctx = _build_system_context("/tmp/repo", "code-writer")
                assert "MCP Tools" not in ctx


# ---------------------------------------------------------------------------
# Plan mode context
# ---------------------------------------------------------------------------


class TestPlanModeContext:
    def test_plan_mode_active(self):
        stack, mock_pm = _base_mocks()
        mock_pm.is_plan_mode = True
        mock_pm.format_plan.return_value = "Step 1: Do thing"
        with stack:
            with patch("code_agents.chat.chat_input.get_current_mode", return_value="plan"):
                ctx = _build_system_context("/tmp/repo", "code-writer")
                assert "Plan Mode" in ctx
                assert "STRUCTURED PLAN" in ctx
                assert "Current Plan" in ctx
                assert "Step 1: Do thing" in ctx

    def test_plan_mode_no_active_plan(self):
        stack, mock_pm = _base_mocks()
        mock_pm.is_plan_mode = True
        mock_pm.format_plan.return_value = "  No active plan."
        with stack:
            with patch("code_agents.chat.chat_input.get_current_mode", return_value="plan"):
                ctx = _build_system_context("/tmp/repo", "code-writer")
                assert "Plan Mode" in ctx
                assert "Current Plan" not in ctx


# ---------------------------------------------------------------------------
# Agent chaining / auto-pilot
# ---------------------------------------------------------------------------


class TestAutoPilotContext:
    def test_auto_pilot_delegation_hint(self):
        stack, _ = _base_mocks()
        with stack:
            ctx = _build_system_context("/tmp/repo", "auto-pilot")
            assert "[DELEGATE:" in ctx

    def test_non_auto_pilot_no_delegation(self):
        stack, _ = _base_mocks()
        with stack:
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "[DELEGATE:" not in ctx


# ---------------------------------------------------------------------------
# Superpower mode
# ---------------------------------------------------------------------------


class TestSuperpowerContext:
    def test_superpower_includes_catalog(self):
        stack, _ = _base_mocks()
        mock_skill = MagicMock()
        mock_skill.name = "test-skill"
        mock_skill.description = "A test skill"
        with stack:
            with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={"code-writer": [mock_skill]}), \
                 patch("code_agents.agent_system.skill_loader.get_all_agents_with_skills", return_value="Agent catalog here"):
                ctx = _build_system_context("/tmp/repo", "code-writer", superpower=True)
                assert "SUPERPOWER" in ctx
                assert "Agent catalog here" in ctx


# ---------------------------------------------------------------------------
# Skills injection
# ---------------------------------------------------------------------------


class TestSkillsInjection:
    def test_skills_section_added(self):
        stack, _ = _base_mocks()
        mock_skill = MagicMock()
        mock_skill.name = "debug"
        mock_skill.description = "Debug workflows"
        with stack:
            with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={"code-writer": [mock_skill], "_shared": []}):
                ctx = _build_system_context("/tmp/repo", "code-writer")
                assert "Skills (on-demand)" in ctx
                assert "debug" in ctx

    def test_skills_exception_handled(self):
        stack, _ = _base_mocks()
        with stack:
            with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("fail")):
                ctx = _build_system_context("/tmp/repo", "code-writer")
                # Should not crash; skills section won't appear
                assert "IMPORTANT" in ctx  # basic context is still there


# ---------------------------------------------------------------------------
# Rules injection
# ---------------------------------------------------------------------------


class TestRulesInjection:
    def test_rules_injected(self):
        stack, _ = _base_mocks()
        with stack:
            with patch("code_agents.agent_system.rules_loader.load_rules", return_value="Rule: always test"):
                ctx = _build_system_context("/tmp/repo", "code-writer")
                assert "Rules" in ctx
                assert "Rule: always test" in ctx

    def test_no_rules(self):
        stack, _ = _base_mocks()
        with stack:
            ctx = _build_system_context("/tmp/repo", "code-writer")
            assert "--- Rules ---" not in ctx


# ---------------------------------------------------------------------------
# _suggest_skills
# ---------------------------------------------------------------------------


class TestSuggestSkills:
    def test_suggest_test_skills(self, capsys):
        mock_skill = MagicMock()
        mock_skill.name = "test-and-report"
        with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={"code-writer": [mock_skill], "_shared": []}):
            _suggest_skills("run tests", "code-writer", "/agents")
            captured = capsys.readouterr()
            assert "test-and-report" in captured.out

    def test_no_suggest_when_invoking_skill(self, capsys):
        _suggest_skills("/code-writer:debug", "code-writer", "/agents")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_matching_keywords(self, capsys):
        with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={"code-writer": [], "_shared": []}):
            _suggest_skills("xyzzy", "code-writer", "/agents")
            captured = capsys.readouterr()
            assert captured.out == ""

    def test_exception_handled(self, capsys):
        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("fail")):
            _suggest_skills("test", "code-writer", "/agents")
            # Should not raise
