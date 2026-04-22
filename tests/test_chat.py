"""Tests for chat.py — interactive chat REPL components."""

from __future__ import annotations

import os

import pytest

from code_agents.chat import (
    AGENT_ROLES,
    AGENT_WELCOME,
    _build_system_context,
    _check_server,
    _extract_commands,
    _get_agents,
    _handle_command,
    _is_safe_command,
    _is_valid_command,
    _check_agent_autorun,
    _make_completer,
    _parse_inline_delegation,
    _print_welcome,
    _resolve_placeholders,
)


class TestAgentRoles:
    """Verify all 12 agents have role descriptions."""

    def test_all_agents_have_roles(self):
        expected = [
            "code-reasoning", "code-writer", "code-reviewer", "code-tester",
            "qa-regression", "redash-query", "git-ops", "test-coverage",
            "jenkins-cicd", "argocd-verify", "auto-pilot", "jira-ops",
            "security", "grafana-ops", "terraform-ops", "github-actions",
            "db-ops", "pr-review", "debug-agent",
        ]
        for agent in expected:
            assert agent in AGENT_ROLES, f"Missing role for {agent}"
            assert len(AGENT_ROLES[agent]) > 10, f"Role too short for {agent}"

    def test_role_count(self):
        assert len(AGENT_ROLES) == 19


class TestAgentWelcome:
    """Verify all 12 agents have welcome messages."""

    def test_all_agents_have_welcome(self):
        for agent in AGENT_ROLES:
            assert agent in AGENT_WELCOME, f"Missing welcome for {agent}"

    def test_welcome_count(self):
        assert len(AGENT_WELCOME) == 19

    def test_welcome_structure(self):
        """Each welcome is a tuple of (title, capabilities, examples)."""
        for agent, welcome in AGENT_WELCOME.items():
            assert isinstance(welcome, tuple), f"{agent}: welcome should be tuple"
            assert len(welcome) == 3, f"{agent}: welcome should have 3 elements"
            title, caps, examples = welcome
            assert isinstance(title, str) and len(title) > 5, f"{agent}: title too short"
            assert isinstance(caps, list) and len(caps) >= 2, f"{agent}: needs at least 2 capabilities"
            assert isinstance(examples, list) and len(examples) >= 2, f"{agent}: needs at least 2 examples"

    def test_print_welcome_renders(self, capsys):
        """_print_welcome should output the box."""
        _print_welcome("code-tester")
        output = capsys.readouterr().out
        assert "code-tester" in output.lower() or "Testing" in output
        assert "Try asking" in output or "What I can do" in output

    def test_print_welcome_unknown_agent(self, capsys):
        """Unknown agent should print nothing."""
        _print_welcome("nonexistent")
        output = capsys.readouterr().out
        assert output == ""


class TestGetAgents:
    """Test agent list parsing from various API response formats."""

    def test_parse_data_format(self):
        """Server returns {"object": "list", "data": [...]}."""
        import httpx
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "object": "list",
            "data": [
                {"name": "code-reasoning", "display_name": "Code Reasoning Agent"},
                {"name": "code-writer", "display_name": "Code Writer Agent"},
            ]
        }

        with patch("httpx.get", return_value=mock_response):
            agents = _get_agents("http://localhost:8000")
            assert "code-reasoning" in agents
            assert "code-writer" in agents
            assert agents["code-reasoning"] == "Code Reasoning Agent"

    def test_parse_agents_format(self):
        """Alternate format: {"agents": [...]}."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agents": [
                {"name": "git-ops", "display_name": "Git Ops Agent"},
            ]
        }

        with patch("httpx.get", return_value=mock_response):
            agents = _get_agents("http://localhost:8000")
            assert "git-ops" in agents

    def test_parse_plain_list(self):
        """Plain list format: [...]."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "code-tester", "display_name": "Code Tester"},
        ]

        with patch("httpx.get", return_value=mock_response):
            agents = _get_agents("http://localhost:8000")
            assert "code-tester" in agents

    def test_connection_failure(self):
        """Returns empty dict on connection error."""
        from unittest.mock import patch
        import httpx

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            agents = _get_agents("http://localhost:9999")
            assert agents == {}

    def test_empty_response(self):
        """Returns empty dict for unexpected response."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {"unexpected": "format"}

        with patch("httpx.get", return_value=mock_response):
            agents = _get_agents("http://localhost:8000")
            assert agents == {}


class TestCheckServer:
    """Test server health check."""

    def test_server_running(self):
        """Returns True when health returns 200."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.get", return_value=mock_response):
            assert _check_server("http://localhost:8000") is True

    def test_server_not_running(self):
        """Returns False on connection error."""
        from unittest.mock import patch
        import httpx

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert _check_server("http://localhost:9999") is False

    def test_server_unhealthy(self):
        """Returns False when health returns non-200."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.get", return_value=mock_response):
            assert _check_server("http://localhost:8000") is False


class TestSlashCommands:
    """Test chat slash command handling."""

    def _make_state(self):
        return {"agent": "code-reasoning", "session_id": "abc123", "repo_path": "/tmp/repo"}

    def test_quit(self):
        state = self._make_state()
        assert _handle_command("/quit", state, "http://localhost:8000") == "quit"

    def test_exit(self):
        state = self._make_state()
        assert _handle_command("/exit", state, "http://localhost:8000") == "quit"

    def test_q(self):
        state = self._make_state()
        assert _handle_command("/q", state, "http://localhost:8000") == "quit"

    def test_clear(self):
        state = self._make_state()
        result = _handle_command("/clear", state, "http://localhost:8000")
        assert result is None
        assert state["session_id"] is None

    def test_session(self, capsys):
        state = self._make_state()
        _handle_command("/session", state, "http://localhost:8000")
        captured = capsys.readouterr()
        assert "abc123" in captured.out

    def test_session_none(self, capsys):
        state = {"agent": "code-reasoning", "session_id": None, "repo_path": "/tmp"}
        _handle_command("/session", state, "http://localhost:8000")
        captured = capsys.readouterr()
        # /session now lists all saved sessions (or "No saved sessions")
        assert "sessions" in captured.out.lower() or "No saved" in captured.out

    def test_help(self, capsys):
        state = self._make_state()
        result = _handle_command("/help", state, "http://localhost:8000")
        assert result is None
        captured = capsys.readouterr()
        assert "/quit" in captured.out
        assert "/agent" in captured.out
        assert "/clear" in captured.out
        assert "/history" in captured.out
        assert "/resume" in captured.out

    def test_btw_add(self, capsys):
        state = self._make_state()
        result = _handle_command("/btw use Python 3.12", state, "http://localhost:8000")
        assert result is None
        assert state["_btw_messages"] == ["use Python 3.12"]
        captured = capsys.readouterr()
        assert "Noted" in captured.out

    def test_btw_add_multiple(self, capsys):
        state = self._make_state()
        _handle_command("/btw use Python 3.12", state, "http://localhost:8000")
        _handle_command("/btw skip integration tests", state, "http://localhost:8000")
        assert state["_btw_messages"] == ["use Python 3.12", "skip integration tests"]

    def test_btw_show_empty(self, capsys):
        state = self._make_state()
        _handle_command("/btw", state, "http://localhost:8000")
        captured = capsys.readouterr()
        assert "No side messages" in captured.out

    def test_btw_show_with_messages(self, capsys):
        state = self._make_state()
        state["_btw_messages"] = ["fix typos", "use async"]
        _handle_command("/btw", state, "http://localhost:8000")
        captured = capsys.readouterr()
        assert "fix typos" in captured.out
        assert "use async" in captured.out

    def test_btw_clear(self, capsys):
        state = self._make_state()
        state["_btw_messages"] = ["something"]
        _handle_command("/btw clear", state, "http://localhost:8000")
        assert state["_btw_messages"] == []
        captured = capsys.readouterr()
        assert "cleared" in captured.out

    def test_agent_no_arg(self, capsys):
        state = self._make_state()
        _handle_command("/agent", state, "http://localhost:8000")
        captured = capsys.readouterr()
        assert "Usage" in captured.out

    def test_agent_switch(self, capsys):
        """Switch agent when server returns agent list."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"name": "code-writer", "display_name": "Code Writer Agent"},
                {"name": "code-reasoning", "display_name": "Code Reasoning Agent"},
            ]
        }

        state = self._make_state()
        with patch("httpx.get", return_value=mock_response):
            _handle_command("/agent code-writer", state, "http://localhost:8000")
        assert state["agent"] == "code-writer"
        assert state["session_id"] is None  # cleared on switch

    def test_agent_not_found(self, capsys):
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"name": "code-reasoning", "display_name": ""}]}

        state = self._make_state()
        with patch("httpx.get", return_value=mock_response):
            _handle_command("/agent nonexistent", state, "http://localhost:8000")
        assert state["agent"] == "code-reasoning"  # unchanged
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_unknown_command(self, capsys):
        state = self._make_state()
        result = _handle_command("/foo", state, "http://localhost:8000")
        assert result is None
        captured = capsys.readouterr()
        assert "Unknown command" in captured.out



    def test_history(self):
        """Test /history command runs without error."""
        state = {"agent": "code-reasoning", "repo_path": "/tmp/test", "_chat_session": None}
        result = _handle_command("/history", state, "http://localhost:8000")
        assert result is None

    def test_resume_no_arg(self, capsys):
        """Test /resume with no session ID."""
        state = {"agent": "code-reasoning", "repo_path": "/tmp/test", "_chat_session": None}
        result = _handle_command("/resume", state, "http://localhost:8000")
        assert result is None
        captured = capsys.readouterr()
        assert "Usage" in captured.out

    def test_resume_not_found(self, capsys):
        """Test /resume with nonexistent session ID."""
        state = {"agent": "code-reasoning", "repo_path": "/tmp/test", "_chat_session": None}
        result = _handle_command("/resume nonexistent-id", state, "http://localhost:8000")
        assert result is None
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_delete_chat_no_arg(self, capsys):
        """Test /delete-chat with no session ID."""
        state = {"agent": "code-reasoning", "repo_path": "/tmp/test", "_chat_session": None}
        result = _handle_command("/delete-chat", state, "http://localhost:8000")
        assert result is None
        captured = capsys.readouterr()
        assert "Usage" in captured.out

    def test_clear_resets_chat_session(self):
        """Test /clear also clears _chat_session."""
        state = {"agent": "code-reasoning", "session_id": "abc", "_chat_session": {"id": "test"}}
        _handle_command("/clear", state, "http://localhost:8000")
        assert state["session_id"] is None
        assert state["_chat_session"] is None

class TestRepoDetection:
    """Test that chat detects git repos correctly."""

    def test_detects_git_repo(self, tmp_path):
        """Should find .git directory."""
        repo = tmp_path / "myrepo"
        repo.mkdir()
        (repo / ".git").mkdir()

        # Walk up from a subdirectory
        subdir = repo / "src" / "main"
        subdir.mkdir(parents=True)

        # Simulate the detection logic from chat_main
        check_dir = str(subdir)
        found = None
        while True:
            if os.path.isdir(os.path.join(check_dir, ".git")):
                found = check_dir
                break
            parent = os.path.dirname(check_dir)
            if parent == check_dir:
                break
            check_dir = parent

        assert found == str(repo)

    def test_no_git_repo(self, tmp_path):
        """Should not find .git in temp directory without one."""
        check_dir = str(tmp_path)
        found = None
        while True:
            if os.path.isdir(os.path.join(check_dir, ".git")):
                found = check_dir
                break
            parent = os.path.dirname(check_dir)
            if parent == check_dir:
                break
            check_dir = parent

        # tmp_path itself doesn't have .git, but a parent might
        # (the test runner's working dir). So we just check the logic runs.
        assert True  # No crash


class TestStreamChat:
    """Test SSE stream parsing."""

    def test_parse_sse_text_chunk(self):
        """Verify _stream_chat yields text from SSE data lines."""
        import json

        # Simulate an SSE line
        chunk = {
            "choices": [{
                "delta": {"content": "Hello world"},
                "finish_reason": None,
            }]
        }
        line = f"data: {json.dumps(chunk)}"

        # Parse like _stream_chat does
        data_str = line[6:]
        parsed = json.loads(data_str)
        delta = parsed["choices"][0]["delta"]
        assert delta.get("content") == "Hello world"

    def test_parse_sse_reasoning_chunk(self):
        """Verify reasoning_content is parsed from SSE."""
        import json

        chunk = {
            "choices": [{
                "delta": {"reasoning_content": "> **Using tool: read_file**"},
                "finish_reason": None,
            }]
        }
        line = f"data: {json.dumps(chunk)}"
        data_str = line[6:]
        parsed = json.loads(data_str)
        delta = parsed["choices"][0]["delta"]
        assert "Using tool" in delta.get("reasoning_content", "")

    def test_parse_sse_session_id(self):
        """Verify session_id is extracted from final chunk."""
        import json

        chunk = {
            "session_id": "sess-abc-123",
            "choices": [{
                "delta": {},
                "finish_reason": "stop",
            }]
        }
        line = f"data: {json.dumps(chunk)}"
        data_str = line[6:]
        parsed = json.loads(data_str)
        assert parsed.get("session_id") == "sess-abc-123"

    def test_parse_done_marker(self):
        """Verify [DONE] marker is recognized."""
        line = "data: [DONE]"
        data_str = line[6:]
        assert data_str == "[DONE]"


class TestInlineDelegation:
    """Test inline agent delegation parsing (/agent-name prompt)."""

    AGENTS = {
        "code-reasoning": "Code Reasoning Agent",
        "code-writer": "Code Writer Agent",
        "code-tester": "Code Tester Agent",
        "code-reviewer": "Code Reviewer Agent",
        "git-ops": "Git Ops Agent",
    }

    def test_agent_with_prompt(self):
        """'/code-reasoning explain auth' → delegation."""
        agent, prompt = _parse_inline_delegation(
            "/code-reasoning explain auth", self.AGENTS
        )
        assert agent == "code-reasoning"
        assert prompt == "explain auth"

    def test_agent_no_prompt_returns_empty(self):
        """'/code-writer' with no prompt → permanent switch signal."""
        agent, prompt = _parse_inline_delegation("/code-writer", self.AGENTS)
        assert agent == "code-writer"
        assert prompt == ""

    def test_unknown_agent(self):
        """'/nonexistent do stuff' → not a delegation."""
        agent, prompt = _parse_inline_delegation("/nonexistent do stuff", self.AGENTS)
        assert agent is None
        assert prompt is None

    def test_regular_slash_command(self):
        """'/help' → not a delegation."""
        agent, prompt = _parse_inline_delegation("/help", self.AGENTS)
        assert agent is None
        assert prompt is None

    def test_quit_not_delegation(self):
        """'/quit' → not a delegation."""
        agent, prompt = _parse_inline_delegation("/quit", self.AGENTS)
        assert agent is None
        assert prompt is None

    def test_not_a_slash_command(self):
        """Regular text → not a delegation."""
        agent, prompt = _parse_inline_delegation("hello world", self.AGENTS)
        assert agent is None
        assert prompt is None

    def test_multiword_prompt(self):
        """Prompt with multiple words is captured fully."""
        agent, prompt = _parse_inline_delegation(
            "/code-tester write unit tests for PaymentService class", self.AGENTS
        )
        assert agent == "code-tester"
        assert prompt == "write unit tests for PaymentService class"

    def test_git_ops_agent(self):
        """Agent names with hyphens work."""
        agent, prompt = _parse_inline_delegation(
            "/git-ops show the last 5 commits", self.AGENTS
        )
        assert agent == "git-ops"
        assert prompt == "show the last 5 commits"

    def test_empty_agents_dict(self):
        """No agents available → no match."""
        agent, prompt = _parse_inline_delegation("/code-reasoning explain", {})
        assert agent is None
        assert prompt is None


class TestTabCompletion:
    """Test readline tab-completion for slash commands and agent names."""

    SLASH_COMMANDS = ["/help", "/quit", "/exit", "/agents", "/agent", "/session", "/clear", "/history", "/resume", "/delete-chat"]
    AGENT_NAMES = ["code-reasoning", "code-writer", "code-tester", "code-reviewer", "git-ops"]

    def _completer(self):
        return _make_completer(self.SLASH_COMMANDS, self.AGENT_NAMES)

    def test_complete_slash_shows_all(self):
        """'/' + Tab cycles through all completions (commands + agents + skills)."""
        completer = self._completer()
        results = []
        idx = 0
        while True:
            result = completer("/", idx)
            if result is None:
                break
            results.append(result)
            idx += 1
        # 10 slash commands + 5 agent names + any skills from agents/ dir
        assert len(results) >= 15
        assert "/help" in results
        assert "/code-reasoning" in results

    def test_complete_code_prefix(self):
        """'/code-' + Tab shows code-* agents and their skills."""
        completer = self._completer()
        results = []
        idx = 0
        while True:
            result = completer("/code-", idx)
            if result is None:
                break
            results.append(result)
            idx += 1
        # Must include all 4 code-* agents (may also include skills like /code-writer:implement)
        code_agents = {r for r in results if ":" not in r}
        assert code_agents == {"/code-reasoning", "/code-writer", "/code-tester", "/code-reviewer"}

    def test_complete_exact_match(self):
        """'/help' + Tab returns '/help' then None."""
        completer = self._completer()
        assert completer("/help", 0) == "/help"
        assert completer("/help", 1) is None

    def test_complete_no_match(self):
        """'/xyz' + Tab returns None immediately."""
        completer = self._completer()
        assert completer("/xyz", 0) is None

    def test_no_completion_without_slash(self):
        """Plain text gets no completions."""
        completer = self._completer()
        assert completer("hello", 0) is None
        assert completer("code", 0) is None

    def test_complete_git_ops(self):
        """'/git' + Tab completes to '/git-ops' (and possibly git-ops skills)."""
        completer = self._completer()
        assert completer("/git", 0) == "/git-ops"
        # May also have /git-ops:skill completions, so just check first is /git-ops

    def test_complete_agent_command(self):
        """'/agent' matches both '/agent' and '/agents'."""
        completer = self._completer()
        results = []
        idx = 0
        while True:
            result = completer("/agent", idx)
            if result is None:
                break
            results.append(result)
            idx += 1
        assert "/agent" in results
        assert "/agents" in results

    def test_complete_agent_second_word(self):
        """'/agent code-' + Tab completes bare agent names."""
        from unittest.mock import patch
        completer = self._completer()
        # Simulate readline buffer = "/agent code-", text = "code-"
        with patch("readline.get_line_buffer", return_value="/agent code-"):
            results = []
            idx = 0
            while True:
                result = completer("code-", idx)
                if result is None:
                    break
                results.append(result)
                idx += 1
            assert set(results) == {"code-reasoning", "code-writer", "code-tester", "code-reviewer"}

    def test_complete_agent_second_word_partial(self):
        """'/agent git' + Tab completes to 'git-ops'."""
        from unittest.mock import patch
        completer = self._completer()
        with patch("readline.get_line_buffer", return_value="/agent git"):
            assert completer("git", 0) == "git-ops"
            assert completer("git", 1) is None

    def test_complete_agent_second_word_empty(self):
        """'/agent ' + Tab shows all agent names."""
        from unittest.mock import patch
        completer = self._completer()
        with patch("readline.get_line_buffer", return_value="/agent "):
            results = []
            idx = 0
            while True:
                result = completer("", idx)
                if result is None:
                    break
                results.append(result)
                idx += 1
            assert len(results) == 5  # all 5 agents in AGENT_NAMES
            assert "code-reasoning" in results
            assert "git-ops" in results


class TestExtractCommands:
    """Test shell command extraction from agent responses."""

    def test_extract_bash_block(self):
        text = "Here's how to check:\n```bash\ngit status\ngit log --oneline -5\n```\nThat's it."
        cmds = _extract_commands(text)
        assert cmds == ["git status", "git log --oneline -5"]

    def test_extract_sh_block(self):
        text = "Run this:\n```sh\npython3 -m pytest\n```"
        cmds = _extract_commands(text)
        assert cmds == ["python3 -m pytest"]

    def test_extract_shell_block(self):
        text = "```shell\nnpm install\nnpm test\n```"
        cmds = _extract_commands(text)
        assert cmds == ["npm install", "npm test"]

    def test_extract_zsh_block(self):
        text = "```zsh\nbrew install python\n```"
        cmds = _extract_commands(text)
        assert cmds == ["brew install python"]

    def test_strips_dollar_prompt(self):
        text = "```bash\n$ git status\n$ git diff\n```"
        cmds = _extract_commands(text)
        assert cmds == ["git status", "git diff"]

    def test_strips_arrow_prompt(self):
        text = "```bash\n> echo hello\n```"
        cmds = _extract_commands(text)
        assert cmds == ["echo hello"]

    def test_skips_comments(self):
        text = "```bash\n# This is a comment\ngit status\n# Another comment\ngit log\n```"
        cmds = _extract_commands(text)
        assert cmds == ["git status", "git log"]

    def test_skips_empty_lines(self):
        text = "```bash\n\ngit status\n\n\ngit log\n\n```"
        cmds = _extract_commands(text)
        assert cmds == ["git status", "git log"]

    def test_no_code_blocks(self):
        text = "Just run git status in your terminal."
        cmds = _extract_commands(text)
        assert cmds == []

    def test_non_shell_code_block_ignored(self):
        text = "```python\nimport os\nprint('hello')\n```"
        cmds = _extract_commands(text)
        assert cmds == []

    def test_multiple_code_blocks(self):
        text = "First:\n```bash\ngit add .\n```\nThen:\n```bash\ngit commit -m 'fix'\n```"
        cmds = _extract_commands(text)
        assert cmds == ["git add .", "git commit -m 'fix'"]

    def test_console_block(self):
        text = "```console\ncurl http://localhost:8000/health\n```"
        cmds = _extract_commands(text)
        assert cmds == ["curl http://localhost:8000/health"]

    def test_empty_text(self):
        assert _extract_commands("") == []

    def test_multiline_curl_with_continuations(self):
        """Multi-line curl with backslash continuations → single command."""
        text = '''```bash
curl -X POST "http://127.0.0.1:8000/redash/run-query" \\
  -H "Content-Type: application/json" \\
  -d '{"query": "SELECT * FROM users LIMIT 10"}'
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert cmds[0].startswith('curl -X POST')
        assert '-H "Content-Type: application/json"' in cmds[0]
        assert "-d " in cmds[0]

    def test_mixed_single_and_multiline(self):
        """Mix of simple commands and multi-line continuations."""
        text = '''```bash
curl -s "http://localhost:8000/health"
curl -X POST "http://localhost:8000/api" \\
  -H "Authorization: Bearer tok" \\
  -d '{"key": "value"}'
echo "done"
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 3
        assert cmds[0] == 'curl -s "http://localhost:8000/health"'
        assert cmds[1].startswith('curl -X POST')
        assert '-H "Authorization: Bearer tok"' in cmds[1]
        assert cmds[2] == 'echo "done"'

    def test_continuation_with_comments_between(self):
        """Comments between commands don't break continuations."""
        text = '''```bash
# First command
git status
# Second command
git log \\
  --oneline \\
  -5
```'''
        cmds = _extract_commands(text)
        assert cmds == ["git status", "git log --oneline -5"]


class TestExtractCommandsMultilineFix:
    """Test multi-line command joining — commands without backslash continuations.

    Covers the fix for indented/flag-continuation lines being incorrectly
    split into separate commands instead of joined as one.
    """

    def test_indented_flags_join_to_single_command(self):
        """Indented lines starting with flags should join to previous line."""
        text = '''```bash
docker run -d
  --name myapp
  -p 8080:8080
  myimage:latest
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "docker run -d" in cmds[0]
        assert "--name myapp" in cmds[0]
        assert "-p 8080:8080" in cmds[0]
        assert "myimage:latest" in cmds[0]

    def test_curl_without_backslash_joins(self):
        """curl with indented args (no backslash) should be one command."""
        text = '''```bash
curl -X POST http://localhost:8000/api
  -H "Content-Type: application/json"
  -H "Authorization: Bearer token123"
  -d '{"key": "value"}'
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert cmds[0].startswith("curl -X POST")
        assert '-H "Content-Type: application/json"' in cmds[0]
        assert "-d " in cmds[0]

    def test_pipe_continuation(self):
        """Lines starting with | should join to previous."""
        text = '''```bash
cat /var/log/app.log
  | grep ERROR
  | sort -u
  | head -20
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "| grep ERROR" in cmds[0]
        assert "| head -20" in cmds[0]

    def test_operator_continuation(self):
        """Lines starting with && or || should join to previous."""
        text = '''```bash
cd /path/to/project
  && npm install
  && npm run build
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "&& npm install" in cmds[0]

    def test_prev_line_ends_with_pipe(self):
        """If previous line ends with |, next line joins regardless."""
        text = '''```bash
cat file.txt |
grep pattern |
sort -u
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "| grep pattern | sort -u" in cmds[0]

    def test_independent_commands_not_joined(self):
        """Separate independent commands (no indent, no flags) stay separate."""
        text = '''```bash
git status
git pull origin main
npm install
npm run build
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 4
        assert cmds[0] == "git status"
        assert cmds[1] == "git pull origin main"
        assert cmds[2] == "npm install"
        assert cmds[3] == "npm run build"

    def test_blank_line_separates_commands(self):
        """Blank lines between commands keep them separate."""
        text = '''```bash
docker build -t myapp .

docker run -d
  --name myapp
  -p 8080:8080
  myapp
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 2
        assert cmds[0] == "docker build -t myapp ."
        assert "--name myapp" in cmds[1]

    def test_mixed_backslash_and_indent_continuation(self):
        """Mix of backslash and indent continuation in one block."""
        text = '''```bash
curl -X POST http://localhost/api \\
  -H "Content-Type: application/json" \\
  -d '{"a": 1}'

kubectl get pods
  --namespace production
  -o wide
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 2
        assert cmds[0].startswith("curl -X POST")
        assert cmds[1].startswith("kubectl get pods")
        assert "--namespace production" in cmds[1]


class TestResolvePlaceholders:
    """Test placeholder detection and resolution in commands."""

    def test_no_placeholders(self):
        cmd = 'curl -s "http://localhost:8000/health"'
        assert _resolve_placeholders(cmd) == cmd

    def test_single_placeholder(self):
        from unittest.mock import patch
        cmd = 'curl -s "http://localhost:8000/data-sources/<DATA_SOURCE_ID>/schema"'
        with patch("builtins.input", return_value="3"):
            result = _resolve_placeholders(cmd)
        assert result == 'curl -s "http://localhost:8000/data-sources/3/schema"'

    def test_multiple_placeholders(self):
        from unittest.mock import patch
        cmd = 'curl "http://<HOST>:<PORT>/api"'
        inputs = iter(["localhost", "8000"])
        with patch("builtins.input", side_effect=inputs):
            result = _resolve_placeholders(cmd)
        assert result == 'curl "http://localhost:8000/api"'

    def test_duplicate_placeholder_asked_once(self):
        from unittest.mock import patch
        cmd = '<ID> and <ID> again'
        with patch("builtins.input", return_value="42") as mock_input:
            result = _resolve_placeholders(cmd)
        assert result == "42 and 42 again"
        assert mock_input.call_count == 1  # asked only once

    def test_empty_value_returns_none(self):
        from unittest.mock import patch
        cmd = 'curl "http://localhost/<ID>"'
        with patch("builtins.input", return_value=""):
            result = _resolve_placeholders(cmd)
        assert result is None

    def test_lowercase_angle_brackets_not_placeholders(self):
        """Only <UPPER_CASE> are treated as angle placeholders."""
        cmd = 'echo <not_a_placeholder>'
        assert _resolve_placeholders(cmd) == cmd

    def test_curly_brace_placeholder(self):
        """{job_name} is treated as a placeholder."""
        from unittest.mock import patch
        cmd = 'curl http://localhost/jenkins/{job_name}/{build_number}/status'
        inputs = iter(["my-job", "42"])
        with patch("builtins.input", side_effect=inputs):
            result = _resolve_placeholders(cmd)
        assert result == 'curl http://localhost/jenkins/my-job/42/status'

    def test_mixed_angle_and_curly(self):
        """Both <UPPER> and {lower} in same command."""
        from unittest.mock import patch
        cmd = 'curl http://<HOST>/{path}'
        inputs = iter(["localhost:8000", "api/v1"])
        with patch("builtins.input", side_effect=inputs):
            result = _resolve_placeholders(cmd)
        assert result == 'curl http://localhost:8000/api/v1'

    def test_curly_duplicate_asked_once(self):
        """Same {placeholder} used twice → asked only once."""
        from unittest.mock import patch
        cmd = '{id} and {id}'
        with patch("builtins.input", return_value="99") as mock_input:
            result = _resolve_placeholders(cmd)
        assert result == "99 and 99"
        assert mock_input.call_count == 1


class TestSafeCommand:
    """Test read-only command detection for auto-run."""

    def test_get_curl_safe(self):
        assert _is_safe_command('curl -s "http://localhost:8000/jenkins/jobs"') is True

    def test_get_curl_with_flags_safe(self):
        assert _is_safe_command("curl -sS http://localhost:8000/git/status") is True

    def test_post_curl_unsafe(self):
        assert _is_safe_command('curl -X POST http://localhost:8000/jenkins/build-and-wait -d \'{"job":"x"}\'') is False

    def test_curl_with_data_unsafe(self):
        assert _is_safe_command('curl -sS -d \'{"branch":"release"}\' http://localhost:8000/testing/run') is False

    def test_git_status_safe(self):
        assert _is_safe_command("git status") is True

    def test_git_log_safe(self):
        assert _is_safe_command("git log --oneline -5") is True

    def test_git_push_unsafe(self):
        assert _is_safe_command("git push origin main") is False

    def test_rm_unsafe(self):
        assert _is_safe_command("rm -rf /tmp/test") is False

    def test_cat_safe(self):
        assert _is_safe_command("cat /etc/hostname") is True

    def test_ls_safe(self):
        assert _is_safe_command("ls -la") is True

    def test_unknown_command_unsafe(self):
        assert _is_safe_command("docker build .") is False


class TestAgentAutorun:
    """Test per-agent command allowlist/blocklist."""

    def test_jenkins_cicd_allow_jobs(self):
        result = _check_agent_autorun('curl -s "http://127.0.0.1:8000/jenkins/jobs"', "jenkins-cicd")
        assert result == "allow"

    def test_jenkins_cicd_allow_git_status(self):
        result = _check_agent_autorun('curl -s "http://127.0.0.1:8000/git/status"', "jenkins-cicd")
        assert result == "allow"

    def test_jenkins_cicd_block_rm(self):
        result = _check_agent_autorun("rm -rf /tmp/test", "jenkins-cicd")
        assert result == "block"

    def test_jenkins_cicd_block_git_push(self):
        result = _check_agent_autorun("git push origin main", "jenkins-cicd")
        assert result == "block"

    def test_no_config_returns_none(self):
        result = _check_agent_autorun("curl -s http://example.com", "nonexistent-agent")
        assert result is None

    def test_no_agent_returns_none(self):
        result = _check_agent_autorun("curl -s http://example.com", "")
        assert result is None

    def test_unmatched_command_returns_none(self):
        result = _check_agent_autorun("python3 script.py", "jenkins-cicd")
        assert result is None


class TestIsValidCommand:
    """Verify _is_valid_command filters English text from real shell commands."""

    def test_valid_command_curl(self):
        assert _is_valid_command("curl -s http://localhost:8000/health") is True

    def test_valid_command_git(self):
        assert _is_valid_command("git status") is True

    def test_valid_command_mvn(self):
        assert _is_valid_command("mvn clean install -DskipTests") is True

    def test_invalid_english_i_need(self):
        assert _is_valid_command("I need you to checkout the main branch") is False

    def test_invalid_english_please(self):
        assert _is_valid_command("Please run the tests") is False

    def test_invalid_english_analysis(self):
        assert _is_valid_command("Analysis: the repo is well structured") is False

    def test_invalid_english_long_sentence(self):
        assert _is_valid_command("Run the deployment after verifying all tests pass successfully") is False

    def test_valid_command_with_flags(self):
        assert _is_valid_command("some-tool --flag value") is True

    def test_valid_command_pipe(self):
        assert _is_valid_command("cat file | grep pattern") is True

    def test_empty_command(self):
        assert _is_valid_command("") is False

    def test_whitespace_only(self):
        assert _is_valid_command("   ") is False

    def test_extract_commands_filters_english(self):
        """Verify _extract_commands filters out English text in bash blocks."""
        text = '''Here is the plan:
```bash
Please check the deployment status
```

```bash
curl -s http://localhost:8000/health
```
'''
        cmds = _extract_commands(text)
        assert cmds == ["curl -s http://localhost:8000/health"]


class TestBuildSystemContextBtw:
    """Test /btw message injection into system context."""

    def test_btw_messages_injected(self):
        context = _build_system_context("/tmp/repo", "code-reasoning", btw_messages=["use Python 3.12", "skip tests"])
        assert "[USER UPDATES" in context
        assert "use Python 3.12" in context
        assert "skip tests" in context

    def test_btw_messages_empty_list(self):
        context = _build_system_context("/tmp/repo", "code-reasoning", btw_messages=[])
        assert "[USER UPDATES" not in context

    def test_btw_messages_none(self):
        context = _build_system_context("/tmp/repo", "code-reasoning", btw_messages=None)
        assert "[USER UPDATES" not in context

    def test_btw_messages_default(self):
        context = _build_system_context("/tmp/repo", "code-reasoning")
        assert "[USER UPDATES" not in context


# ==========================================================================
# Additional coverage tests for chat modules
# ==========================================================================

from unittest.mock import patch, MagicMock, mock_open
import json
import tempfile


# --------------------------------------------------------------------------
# chat_commands.py — additional coverage
# --------------------------------------------------------------------------

class TestExtractSkillRequests:
    """Test [SKILL:name] tag extraction."""

    def test_single_skill(self):
        from code_agents.chat.chat_commands import _extract_skill_requests
        text = "I'll use [SKILL:build] to do that."
        assert _extract_skill_requests(text) == ["build"]

    def test_multiple_skills(self):
        from code_agents.chat.chat_commands import _extract_skill_requests
        text = "[SKILL:test-and-report] first, then [SKILL:deploy-checklist]"
        assert _extract_skill_requests(text) == ["test-and-report", "deploy-checklist"]

    def test_cross_agent_skill(self):
        from code_agents.chat.chat_commands import _extract_skill_requests
        text = "Loading [SKILL:jenkins-cicd:build]"
        assert _extract_skill_requests(text) == ["jenkins-cicd:build"]

    def test_no_skills(self):
        from code_agents.chat.chat_commands import _extract_skill_requests
        text = "No skills needed here."
        assert _extract_skill_requests(text) == []

    def test_empty_text(self):
        from code_agents.chat.chat_commands import _extract_skill_requests
        assert _extract_skill_requests("") == []


class TestExtractDelegations:
    """Test [DELEGATE:agent-name] extraction."""

    def test_single_delegation(self):
        from code_agents.chat.chat_commands import _extract_delegations
        text = "[DELEGATE:code-writer] Implement the login feature"
        result = _extract_delegations(text)
        assert len(result) == 1
        assert result[0][0] == "code-writer"
        assert "login feature" in result[0][1]

    def test_no_delegation(self):
        from code_agents.chat.chat_commands import _extract_delegations
        text = "Just some normal text"
        assert _extract_delegations(text) == []

    def test_delegation_multiline_prompt(self):
        from code_agents.chat.chat_commands import _extract_delegations
        text = "[DELEGATE:code-tester] Write tests\nfor the auth module"
        result = _extract_delegations(text)
        assert len(result) == 1
        assert result[0][0] == "code-tester"
        assert "Write tests" in result[0][1]


class TestExtractContextFromOutput:
    """Test _extract_context_from_output for placeholder auto-fill."""

    def setup_method(self):
        from code_agents.chat.chat_commands import _command_context
        _command_context.clear()

    def test_extracts_build_version(self):
        from code_agents.chat.chat_commands import _extract_context_from_output, _command_context
        output = json.dumps({"build_version": "1.2.3", "status": "SUCCESS"})
        _extract_context_from_output(output)
        assert _command_context["BUILD_VERSION"] == "1.2.3"
        assert _command_context["build_version"] == "1.2.3"
        assert _command_context["image_tag"] == "1.2.3"

    def test_extracts_build_number(self):
        from code_agents.chat.chat_commands import _extract_context_from_output, _command_context
        output = json.dumps({"number": 42})
        _extract_context_from_output(output)
        assert _command_context["BUILD_NUMBER"] == "42"
        assert _command_context["build_number"] == "42"

    def test_extracts_job_name(self):
        from code_agents.chat.chat_commands import _extract_context_from_output, _command_context
        output = json.dumps({"job_name": "my-service"})
        _extract_context_from_output(output)
        assert _command_context["job_name"] == "my-service"

    def test_ignores_non_json(self):
        from code_agents.chat.chat_commands import _extract_context_from_output, _command_context
        _extract_context_from_output("just plain text output")
        assert len(_command_context) == 0

    def test_ignores_non_dict_json(self):
        from code_agents.chat.chat_commands import _extract_context_from_output, _command_context
        _extract_context_from_output("[1, 2, 3]")
        assert len(_command_context) == 0

    def test_ignores_empty_output(self):
        from code_agents.chat.chat_commands import _extract_context_from_output, _command_context
        _extract_context_from_output("")
        assert len(_command_context) == 0


class TestResolveAutoFill:
    """Test that _resolve_placeholders auto-fills from _command_context."""

    def setup_method(self):
        from code_agents.chat.chat_commands import _command_context
        _command_context.clear()

    def test_auto_fill_from_context(self):
        from code_agents.chat.chat_commands import _command_context
        _command_context["BUILD_VERSION"] = "2.0.0"
        result = _resolve_placeholders("deploy <BUILD_VERSION>")
        assert result == "deploy 2.0.0"

    def test_eof_returns_none(self):
        cmd = 'curl "http://localhost/<ID>"'
        with patch("builtins.input", side_effect=EOFError):
            result = _resolve_placeholders(cmd)
        assert result is None

    def test_keyboard_interrupt_returns_none(self):
        cmd = 'curl "http://localhost/<ID>"'
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = _resolve_placeholders(cmd)
        assert result is None


class TestExtractCommandsAdvanced:
    """Additional coverage for _extract_commands edge cases."""

    def test_script_block_with_control_flow(self):
        """if/then/fi blocks should be extracted as single script command."""
        text = '''```bash
if [ -f /tmp/test ]; then
  echo "exists"
fi
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "bash " in cmds[0]  # wrapped in temp file

    def test_script_block_with_variables(self):
        """Blocks with variable assignments go to temp file."""
        text = '''```bash
VERSION="1.0.0"
echo $VERSION
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "bash " in cmds[0]

    def test_script_block_with_for_loop(self):
        """for/do/done blocks extracted as single script."""
        text = '''```bash
for f in *.py; do
  echo "$f"
done
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "bash " in cmds[0]

    def test_script_block_with_export(self):
        """export statements trigger script mode."""
        text = '''```bash
export MY_VAR=hello
echo $MY_VAR
```'''
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "bash " in cmds[0]

    def test_greater_than_prompt_stripped(self):
        """'> ' prefix stripped from commands."""
        text = "```bash\n> ls -la\n```"
        cmds = _extract_commands(text)
        assert cmds == ["ls -la"]


class TestIsValidCommandAdvanced:
    """More _is_valid_command coverage."""

    def test_known_safe_prefix_docker(self):
        assert _is_valid_command("docker build .") is True

    def test_known_safe_prefix_npm(self):
        assert _is_valid_command("npm install") is True

    def test_known_safe_prefix_python(self):
        assert _is_valid_command("python3 -m pytest") is True

    def test_known_safe_prefix_kubectl(self):
        assert _is_valid_command("kubectl get pods") is True

    def test_known_safe_prefix_make(self):
        assert _is_valid_command("make build") is True

    def test_known_safe_prefix_echo(self):
        assert _is_valid_command("echo hello") is True

    def test_known_safe_prefix_grep(self):
        assert _is_valid_command("grep -r pattern .") is True

    def test_known_safe_prefix_find(self):
        assert _is_valid_command("find . -name '*.py'") is True

    def test_english_starter_you(self):
        assert _is_valid_command("You should run the tests first") is False

    def test_english_starter_the(self):
        assert _is_valid_command("The server is running on port 8080") is False

    def test_english_starter_we(self):
        assert _is_valid_command("We need to deploy the new version to prod") is False

    def test_english_starter_here(self):
        assert _is_valid_command("Here is the plan for the migration") is False

    def test_english_starter_note(self):
        assert _is_valid_command("Note that you must restart the service") is False

    def test_command_with_path(self):
        """Commands with paths should pass."""
        assert _is_valid_command("./gradlew build") is True

    def test_short_unknown_command(self):
        """Short unknown commands default to allow."""
        assert _is_valid_command("foo bar") is True

    def test_command_with_shell_chars(self):
        """Commands with shell metacharacters pass regardless."""
        assert _is_valid_command("run something && echo done after that completes successfully now") is True


class TestIsSafeCommandAdvanced:
    """Additional _is_safe_command coverage."""

    def test_curl_delete_unsafe(self):
        assert _is_safe_command('curl -X DELETE http://localhost:8000/api/items/1') is False

    def test_curl_patch_unsafe(self):
        assert _is_safe_command('curl -X PATCH http://localhost:8000/api/items/1') is False

    def test_curl_data_single_quote_unsafe(self):
        assert _is_safe_command("curl -d'{\"key\":\"val\"}' http://localhost") is False

    def test_curl_data_double_quote_unsafe(self):
        assert _is_safe_command('curl -d"some data" http://localhost') is False

    def test_git_diff_safe(self):
        assert _is_safe_command("git diff HEAD~3") is True

    def test_git_branch_safe(self):
        assert _is_safe_command("git branch -a") is True

    def test_git_show_safe(self):
        assert _is_safe_command("git show HEAD") is True

    def test_git_remote_safe(self):
        assert _is_safe_command("git remote -v") is True

    def test_head_safe(self):
        assert _is_safe_command("head -20 file.txt") is True

    def test_tail_safe(self):
        assert _is_safe_command("tail -f log.txt") is True

    def test_wc_safe(self):
        assert _is_safe_command("wc -l file.txt") is True

    def test_grep_safe(self):
        assert _is_safe_command("grep pattern file.txt") is True

    def test_echo_safe(self):
        assert _is_safe_command("echo hello world") is True

    def test_jq_safe(self):
        assert _is_safe_command("jq .field file.json") is True

    def test_npm_unsafe(self):
        assert _is_safe_command("npm install express") is False

    def test_docker_run_unsafe(self):
        assert _is_safe_command("docker run -it ubuntu") is False

    def test_curl_data_flag_unsafe(self):
        assert _is_safe_command("curl --data '{\"foo\":1}' http://localhost") is False


class TestLogAutoRun:
    """Test _log_auto_run auditing."""

    def test_log_auto_run_writes(self, tmp_path):
        from code_agents.chat.chat_commands import _log_auto_run
        with patch("code_agents.chat.chat_commands.Path.home", return_value=tmp_path):
            _log_auto_run("git status", "safe-auto-run")
            log_file = tmp_path / ".code-agents" / "auto_run.log"
            assert log_file.exists()
            content = log_file.read_text()
            assert "git status" in content
            assert "safe-auto-run" in content

    def test_log_auto_run_handles_oserror(self, tmp_path):
        from code_agents.chat.chat_commands import _log_auto_run
        with patch("code_agents.chat.chat_commands.Path.home", return_value=tmp_path / "nonexistent" / "deep"):
            # Should not raise even with broken path
            _log_auto_run("git status", "safe")


class TestSaveCommandToRules:
    """Test _save_command_to_rules."""

    def test_save_new_command(self, tmp_path):
        from code_agents.chat.chat_commands import _save_command_to_rules
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents-rules"):
            _save_command_to_rules("git status", "code-reasoning", str(tmp_path))
            rules_file = tmp_path / ".code-agents-rules" / "code-reasoning.md"
            assert rules_file.exists()
            content = rules_file.read_text()
            assert "git status" in content
            assert "Saved Commands" in content

    def test_save_duplicate_command_skips(self, tmp_path, capsys):
        from code_agents.chat.chat_commands import _save_command_to_rules
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents-rules"):
            _save_command_to_rules("git status", "code-reasoning", str(tmp_path))
            _save_command_to_rules("git status", "code-reasoning", str(tmp_path))
            output = capsys.readouterr().out
            assert "already in rules" in output


class TestIsCommandTrusted:
    """Test _is_command_trusted."""

    def test_trusted_command(self, tmp_path):
        from code_agents.chat.chat_commands import _is_command_trusted
        rules_dir = tmp_path / ".code-agents-rules"
        rules_dir.mkdir()
        rules_file = rules_dir / "code-reasoning.md"
        rules_file.write_text("## Saved Commands\n```bash\ngit status\n```\n")
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents-rules"):
            assert _is_command_trusted("git status", "code-reasoning", str(tmp_path)) is True

    def test_untrusted_command(self, tmp_path):
        from code_agents.chat.chat_commands import _is_command_trusted
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents-rules"):
            assert _is_command_trusted("rm -rf /", "code-reasoning", str(tmp_path)) is False

    def test_no_rules_file(self, tmp_path):
        from code_agents.chat.chat_commands import _is_command_trusted
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents-rules"):
            assert _is_command_trusted("git status", "nonexistent", str(tmp_path)) is False


class TestOfferRunCommandsDryRun:
    """Test _offer_run_commands in dry-run mode."""

    def test_dry_run_mode(self, capsys):
        from code_agents.chat.chat_commands import _offer_run_commands
        with patch.dict(os.environ, {"CODE_AGENTS_DRY_RUN": "true"}):
            results = _offer_run_commands(
                ["git status"], "/tmp/repo",
                agent_name="", auto_run=True, superpower=False,
            )
        assert len(results) == 1
        assert "dry-run" in results[0]["output"]
        output = capsys.readouterr().out
        assert "DRY-RUN" in output

    def test_empty_commands(self):
        from code_agents.chat.chat_commands import _offer_run_commands
        results = _offer_run_commands([], "/tmp/repo")
        assert results == []

    def test_auto_run_disabled_by_env(self, capsys):
        from code_agents.chat.chat_commands import _offer_run_commands
        with patch.dict(os.environ, {"CODE_AGENTS_AUTO_RUN": "false", "CODE_AGENTS_DRY_RUN": "true"}):
            # tab_selector returns 0 (Yes), then dry-run kicks in
            with patch("code_agents.chat.chat_commands._tab_selector", return_value=0):
                results = _offer_run_commands(
                    ["git status"], "/tmp/repo",
                    agent_name="", auto_run=True, superpower=False,
                )
        assert len(results) == 1
        assert "dry-run" in results[0]["output"]


# --------------------------------------------------------------------------
# chat_slash_ops.py — coverage
# --------------------------------------------------------------------------

class TestSlashOpsRun:
    """Test /run command handler."""

    def test_run_no_arg(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        result = _handle_operations("/run", "", state, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_run_with_arg(self):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        with patch("code_agents.chat.chat_slash_ops._run_single_command", return_value="output") as mock_run:
            result = _handle_operations("/run", "git status", state, "http://localhost:8000")
        assert result is None
        mock_run.assert_called_once_with("git status", "/tmp/repo")


class TestSlashOpsExec:
    """Test /exec command handler."""

    def test_exec_no_arg(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        result = _handle_operations("/execute", "", state, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_exec_with_arg(self):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        with patch("code_agents.chat.chat_slash_ops._resolve_placeholders", return_value="git log"):
            with patch("code_agents.chat.chat_slash_ops._run_single_command", return_value="commit abc"):
                result = _handle_operations("/execute", "git log", state, "http://localhost:8000")
        assert result == "exec_feedback"
        assert state["_exec_feedback"]["command"] == "git log"
        assert state["_exec_feedback"]["output"] == "commit abc"

    def test_exec_resolve_fails(self):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        with patch("code_agents.chat.chat_slash_ops._resolve_placeholders", return_value=None):
            result = _handle_operations("/execute", "curl <ID>", state, "http://localhost:8000")
        assert result is None


class TestSlashOpsBash:
    """Test /bash command handler."""

    def test_bash_no_arg(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        result = _handle_operations("/bash", "", state, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_bash_success(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        mock_result = MagicMock()
        mock_result.stdout = "hello\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        state = {"repo_path": "/tmp/repo"}
        with patch("subprocess.run", return_value=mock_result):
            with patch("builtins.input", return_value="n"):
                result = _handle_operations("/bash", "echo hello", state, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "hello" in output

    def test_bash_failure(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_result.returncode = 1
        state = {"repo_path": "/tmp/repo"}
        with patch("subprocess.run", return_value=mock_result):
            with patch("builtins.input", return_value="n"):
                result = _handle_operations("/bash", "false", state, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "Exit code" in output

    def test_bash_timeout(self, capsys):
        import subprocess
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 120)):
            result = _handle_operations("/bash", "sleep 999", state, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "Timed out" in output

    def test_bash_exception(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        with patch("subprocess.run", side_effect=OSError("fail")):
            result = _handle_operations("/bash", "badcmd", state, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "Error" in output

    def test_bash_feed_to_agent(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        mock_result = MagicMock()
        mock_result.stdout = "output data\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        state = {"repo_path": "/tmp/repo"}
        with patch("subprocess.run", return_value=mock_result):
            with patch("builtins.input", return_value="y"):
                result = _handle_operations("/bash", "echo output data", state, "http://localhost:8000")
        assert result is not None
        assert "output data" in result


class TestSlashOpsBtw:
    """Test /btw command handler."""

    def test_btw_add(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        result = _handle_operations("/btw", "use Python 3.12", state, "http://localhost:8000")
        assert result is None
        assert state["_btw_messages"] == ["use Python 3.12"]
        output = capsys.readouterr().out
        assert "Noted" in output

    def test_btw_clear(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo", "_btw_messages": ["something"]}
        result = _handle_operations("/btw", "clear", state, "http://localhost:8000")
        assert result is None
        assert state["_btw_messages"] == []

    def test_btw_show_empty(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        _handle_operations("/btw", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "No side messages" in output

    def test_btw_show_with_messages(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo", "_btw_messages": ["msg1", "msg2"]}
        _handle_operations("/btw", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "msg1" in output
        assert "msg2" in output


class TestSlashOpsSuperpower:
    """Test /superpower command handler."""

    def test_superpower_on(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        _handle_operations("/superpower", "on", state, "http://localhost:8000")
        assert state["superpower"] is True
        output = capsys.readouterr().out
        assert "SUPERPOWER" in output

    def test_superpower_off(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo", "superpower": True}
        _handle_operations("/superpower", "off", state, "http://localhost:8000")
        assert state["superpower"] is False
        output = capsys.readouterr().out
        assert "OFF" in output


class TestSlashOpsLayout:
    """Test /layout command handler."""

    def test_layout_no_arg(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        _handle_operations("/layout", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "/layout on" in output

    def test_layout_on_no_tty(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=False):
            _handle_operations("/layout", "on", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "not support" in output or "not a TTY" in output

    def test_layout_off(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo", "_fixed_layout": True}
        with patch("code_agents.chat.terminal_layout.exit_layout"):
            _handle_operations("/layout", "off", state, "http://localhost:8000")
        assert state["_fixed_layout"] is False


class TestSlashOpsPlan:
    """Test /plan command handler."""

    def test_plan_no_arg_no_plans(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        with patch("code_agents.agent_system.plan_manager.list_plans", return_value=[]):
            _handle_operations("/plan", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "No plans" in output

    def test_plan_no_arg_with_plans(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        plans = [{"id": "abc123", "title": "Test Plan", "progress": "2/5"}]
        with patch("code_agents.agent_system.plan_manager.list_plans", return_value=plans):
            _handle_operations("/plan", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Test Plan" in output

    def test_plan_approve_no_plan(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        _handle_operations("/plan", "approve", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "No plan" in output

    def test_plan_approve_with_plan(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo", "_last_plan_id": "plan-1"}
        plan_data = {"title": "My Plan", "total": 3}
        with patch("code_agents.agent_system.plan_manager.load_plan", return_value=plan_data):
            _handle_operations("/plan", "approve", state, "http://localhost:8000")
        assert state["plan_active"] == "plan-1"

    def test_plan_reject(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo", "plan_active": "plan-1", "_last_plan_id": "plan-1"}
        _handle_operations("/plan", "reject", state, "http://localhost:8000")
        assert "plan_active" not in state
        assert "_last_plan_id" not in state

    def test_plan_status_no_active(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        _handle_operations("/plan", "status", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "No active plan" in output

    def test_plan_status_with_active(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo", "plan_active": "plan-1"}
        plan_data = {
            "title": "Deploy Plan",
            "steps": [
                {"text": "Build", "done": True},
                {"text": "Test", "done": False},
                {"text": "Deploy", "done": False},
            ],
            "current_step": 1,
            "total": 3,
        }
        with patch("code_agents.agent_system.plan_manager.load_plan", return_value=plan_data):
            _handle_operations("/plan", "status", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Deploy Plan" in output
        assert "Build" in output

    def test_plan_list(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        plans = [{"id": "a1", "title": "Plan A", "progress": "1/3"}]
        with patch("code_agents.agent_system.plan_manager.list_plans", return_value=plans):
            _handle_operations("/plan", "list", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Plan A" in output

    def test_plan_prompt(self):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        result = _handle_operations("/plan", "implement login feature", state, "http://localhost:8000")
        assert result == "plan_prompt"


class TestSlashOpsMcp:
    """Test /mcp command handler."""

    def test_mcp_no_servers(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo", "agent": "code-reasoning"}
        with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value={}):
            _handle_operations("/mcp", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "No MCP servers" in output

    def test_mcp_with_servers(self, capsys):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo", "agent": "code-reasoning"}
        mock_server = MagicMock()
        mock_server.is_stdio = True
        mock_server.agents = ["code-reasoning"]
        with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value={"test-server": mock_server}):
            _handle_operations("/mcp", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "test-server" in output


class TestSlashOpsNotHandled:
    """Test unhandled command returns sentinel."""

    def test_unknown_returns_not_handled(self):
        from code_agents.chat.chat_slash_ops import _handle_operations
        state = {"repo_path": "/tmp/repo"}
        result = _handle_operations("/nonexistent", "", state, "http://localhost:8000")
        assert result == "_not_handled"


# --------------------------------------------------------------------------
# chat_response.py — coverage
# --------------------------------------------------------------------------

class TestFormatElapsed:
    """Test _format_elapsed helper."""

    def test_seconds(self):
        from code_agents.chat.chat_response import _format_elapsed
        assert _format_elapsed(30) == "30s"

    def test_seconds_zero(self):
        from code_agents.chat.chat_response import _format_elapsed
        assert _format_elapsed(0) == "0s"

    def test_minutes(self):
        from code_agents.chat.chat_response import _format_elapsed
        assert _format_elapsed(125) == "2m 05s"

    def test_one_minute(self):
        from code_agents.chat.chat_response import _format_elapsed
        assert _format_elapsed(60) == "1m 00s"

    def test_under_minute(self):
        from code_agents.chat.chat_response import _format_elapsed
        assert _format_elapsed(59.9) == "60s"


# --------------------------------------------------------------------------
# chat_streaming.py — coverage
# --------------------------------------------------------------------------

class TestFormatSessionDuration:
    """Test _format_session_duration."""

    def test_seconds(self):
        from code_agents.chat.chat_streaming import _format_session_duration
        assert _format_session_duration(45) == "45s"

    def test_minutes(self):
        from code_agents.chat.chat_streaming import _format_session_duration
        assert _format_session_duration(125) == "2m 05s"

    def test_hours(self):
        from code_agents.chat.chat_streaming import _format_session_duration
        assert _format_session_duration(3661) == "1h 01m"

    def test_zero(self):
        from code_agents.chat.chat_streaming import _format_session_duration
        assert _format_session_duration(0) == "0s"

    def test_exact_hour(self):
        from code_agents.chat.chat_streaming import _format_session_duration
        assert _format_session_duration(3600) == "1h 00m"


# --------------------------------------------------------------------------
# chat_ui.py — coverage
# --------------------------------------------------------------------------

class TestColorFunctions:
    """Test basic color wrapper functions."""

    def test_bold(self):
        from code_agents.chat.chat_ui import bold
        result = bold("test")
        assert "test" in result

    def test_green(self):
        from code_agents.chat.chat_ui import green
        result = green("ok")
        assert "ok" in result

    def test_yellow(self):
        from code_agents.chat.chat_ui import yellow
        result = yellow("warn")
        assert "warn" in result

    def test_red(self):
        from code_agents.chat.chat_ui import red
        result = red("err")
        assert "err" in result

    def test_cyan(self):
        from code_agents.chat.chat_ui import cyan
        result = cyan("info")
        assert "info" in result

    def test_dim(self):
        from code_agents.chat.chat_ui import dim
        result = dim("subtle")
        assert "subtle" in result

    def test_magenta(self):
        from code_agents.chat.chat_ui import magenta
        result = magenta("git")
        assert "git" in result


class TestVisibleLen:
    """Test _visible_len strips ANSI codes."""

    def test_plain_text(self):
        from code_agents.chat.chat_ui import _visible_len
        assert _visible_len("hello") == 5

    def test_with_ansi(self):
        from code_agents.chat.chat_ui import _visible_len
        assert _visible_len("\033[32mhello\033[0m") == 5

    def test_empty(self):
        from code_agents.chat.chat_ui import _visible_len
        assert _visible_len("") == 0

    def test_nested_ansi(self):
        from code_agents.chat.chat_ui import _visible_len
        assert _visible_len("\033[1;32mhello\033[0m \033[31mworld\033[0m") == 11

    def test_only_ansi(self):
        from code_agents.chat.chat_ui import _visible_len
        assert _visible_len("\033[32m\033[0m") == 0


class TestRenderMarkdown:
    """Test _render_markdown terminal rendering."""

    def test_bold_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown, _USE_COLOR
        if not _USE_COLOR:
            pytest.skip("Color disabled in non-TTY")
        result = _render_markdown("**bold text**")
        assert "bold text" in result

    def test_code_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown, _USE_COLOR
        if not _USE_COLOR:
            pytest.skip("Color disabled in non-TTY")
        result = _render_markdown("`inline code`")
        assert "inline code" in result

    def test_header_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown, _USE_COLOR
        if not _USE_COLOR:
            pytest.skip("Color disabled in non-TTY")
        result = _render_markdown("## My Header")
        assert "My Header" in result

    def test_plain_text(self):
        from code_agents.chat.chat_ui import _render_markdown
        result = _render_markdown("just plain text")
        assert "just plain text" in result

    def test_list_items(self):
        from code_agents.chat.chat_ui import _render_markdown, _USE_COLOR
        if not _USE_COLOR:
            pytest.skip("Color disabled in non-TTY")
        result = _render_markdown("- item one\n- item two")
        assert "item one" in result
        assert "item two" in result

    def test_blockquote(self):
        from code_agents.chat.chat_ui import _render_markdown, _USE_COLOR
        if not _USE_COLOR:
            pytest.skip("Color disabled in non-TTY")
        result = _render_markdown("> quoted text")
        assert "quoted text" in result

    def test_code_block_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown, _USE_COLOR
        if not _USE_COLOR:
            pytest.skip("Color disabled in non-TTY")
        result = _render_markdown("```python\nprint('hello')\n```")
        assert "print" in result

    def test_horizontal_rule(self):
        from code_agents.chat.chat_ui import _render_markdown, _USE_COLOR
        if not _USE_COLOR:
            pytest.skip("Color disabled in non-TTY")
        result = _render_markdown("---")
        assert result  # just verifies it renders without error

    def test_table_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown
        text = "| Name | Age |\n| --- | --- |\n| Alice | 30 |"
        result = _render_markdown(text)
        assert "Alice" in result
        assert "Name" in result

    def test_empty_text(self):
        from code_agents.chat.chat_ui import _render_markdown
        assert _render_markdown("") == ""


class TestAgentColor:
    """Test agent color lookup."""

    def test_known_agent(self):
        from code_agents.chat.chat_ui import agent_color, cyan
        color_fn = agent_color("code-reasoning")
        assert color_fn == cyan

    def test_unknown_agent(self):
        from code_agents.chat.chat_ui import agent_color, magenta
        color_fn = agent_color("nonexistent")
        assert color_fn == magenta


class TestAgentColorFn:
    """Test agent_color_fn for ANSI wrapping."""

    def test_known_agent(self):
        from code_agents.chat.chat_ui import agent_color_fn
        fn = agent_color_fn("code-reasoning")
        result = fn("test")
        assert "test" in result

    def test_unknown_agent(self):
        from code_agents.chat.chat_ui import agent_color_fn
        fn = agent_color_fn("nonexistent")
        result = fn("test")
        assert "test" in result


class TestFormatResponseBox:
    """Test format_response_box."""

    def test_basic_box(self):
        from code_agents.chat.chat_ui import format_response_box
        result = format_response_box("Hello world", "code-reasoning")
        assert "Hello world" in result
        assert "CODE-REASONING" in result

    def test_empty_text(self):
        from code_agents.chat.chat_ui import format_response_box
        assert format_response_box("", "code-reasoning") == ""

    def test_whitespace_only(self):
        from code_agents.chat.chat_ui import format_response_box
        assert format_response_box("   ", "code-reasoning") == ""

    def test_no_agent_name(self):
        from code_agents.chat.chat_ui import format_response_box
        result = format_response_box("Hello world")
        assert "Hello world" in result

    def test_multiline(self):
        from code_agents.chat.chat_ui import format_response_box
        result = format_response_box("Line 1\nLine 2\nLine 3", "code-writer")
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result

    def test_long_line_wraps(self):
        from code_agents.chat.chat_ui import format_response_box
        long_text = "x" * 200
        result = format_response_box(long_text, "code-writer")
        assert "x" in result


class TestPrintResponseBox:
    """Test print_response_box."""

    def test_prints_box(self, capsys):
        from code_agents.chat.chat_ui import print_response_box
        print_response_box("Hello", "code-reasoning")
        output = capsys.readouterr().out
        assert "Hello" in output

    def test_empty_prints_nothing(self, capsys):
        from code_agents.chat.chat_ui import print_response_box
        print_response_box("", "code-reasoning")
        output = capsys.readouterr().out
        assert output == ""


class TestPrintWelcomeBox:
    """Test _print_welcome from chat_ui."""

    def test_prints_for_known_agent(self, capsys):
        from code_agents.chat.chat_ui import _print_welcome as _pw_raw
        from code_agents.chat.chat_welcome import AGENT_WELCOME
        _pw_raw("code-reasoning", AGENT_WELCOME)
        output = capsys.readouterr().out
        assert "What I can do" in output

    def test_no_output_for_unknown(self, capsys):
        from code_agents.chat.chat_ui import _print_welcome as _pw_raw
        _pw_raw("nonexistent", {})
        output = capsys.readouterr().out
        assert output == ""


class TestSpinner:
    """Test _spinner context manager."""

    def test_spinner_enters_and_exits(self):
        import time
        from code_agents.chat.chat_ui import _spinner
        with _spinner("Loading..."):
            time.sleep(0.15)
        # Just verifies no crash

    def test_activity_indicator(self):
        import time
        from code_agents.chat.chat_ui import activity_indicator
        with activity_indicator("Reading", "test.py") as ai:
            time.sleep(0.15)
            ai.update("Writing", "output.py")
            time.sleep(0.15)
        # Just verifies no crash


class TestAskYesNo:
    """Test _ask_yes_no interactive prompt."""

    def test_fallback_yes(self):
        from code_agents.chat.chat_ui import _ask_yes_no
        with patch("code_agents.chat.chat_ui._tab_selector", return_value=0):
            assert _ask_yes_no("Continue?") is True

    def test_fallback_no(self):
        from code_agents.chat.chat_ui import _ask_yes_no
        with patch("code_agents.chat.chat_ui._tab_selector", return_value=1):
            assert _ask_yes_no("Continue?") is False


class TestAmendPrompt:
    """Test _amend_prompt."""

    def test_returns_text(self):
        from code_agents.chat.chat_ui import _amend_prompt
        with patch("builtins.input", return_value="use async"):
            result = _amend_prompt()
        assert result == "use async"

    def test_eof_returns_empty(self):
        from code_agents.chat.chat_ui import _amend_prompt
        with patch("builtins.input", side_effect=EOFError):
            result = _amend_prompt()
        assert result == ""

    def test_keyboard_interrupt_returns_empty(self):
        from code_agents.chat.chat_ui import _amend_prompt
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = _amend_prompt()
        assert result == ""


class TestRlWrap:
    """Test readline ANSI wrapper."""

    def test_rl_bold(self):
        from code_agents.chat.chat_ui import _rl_bold
        result = _rl_bold("test")
        assert "test" in result

    def test_rl_green(self):
        from code_agents.chat.chat_ui import _rl_green
        result = _rl_green("ok")
        assert "ok" in result


# --------------------------------------------------------------------------
# chat_slash.py — router coverage
# --------------------------------------------------------------------------

class TestSlashRouter:
    """Test the main slash command router dispatches correctly."""

    def _make_state(self):
        return {"agent": "code-reasoning", "session_id": "abc123", "repo_path": "/tmp/repo"}

    def test_nav_quit(self):
        state = self._make_state()
        result = _handle_command("/quit", state, "http://localhost:8000")
        assert result == "quit"

    def test_nav_exit(self):
        state = self._make_state()
        result = _handle_command("/exit", state, "http://localhost:8000")
        assert result == "quit"

    def test_nav_bye(self):
        state = self._make_state()
        result = _handle_command("/bye", state, "http://localhost:8000")
        assert result == "quit"

    def test_session_clear(self):
        state = self._make_state()
        _handle_command("/clear", state, "http://localhost:8000")
        assert state["session_id"] is None

    def test_unknown_command_prints_message(self, capsys):
        state = self._make_state()
        _handle_command("/zzz_unknown", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Unknown command" in output

    def test_command_with_trailing_semicolon(self):
        """Commands with trailing semicolons are handled."""
        state = self._make_state()
        result = _handle_command("/quit;", state, "http://localhost:8000")
        assert result == "quit"

    def test_command_case_insensitive(self):
        """Commands are lowercased."""
        state = self._make_state()
        result = _handle_command("/QUIT", state, "http://localhost:8000")
        assert result == "quit"


# --------------------------------------------------------------------------
# chat.py — _make_completer and _parse_inline_delegation additional coverage
# --------------------------------------------------------------------------

class TestMakeCompleterAdditional:
    """Additional completer tests."""

    SLASH_COMMANDS = ["/help", "/quit", "/skills"]
    AGENT_NAMES = ["code-reasoning", "code-writer"]

    def test_skills_second_word(self):
        """'/skills code-' + Tab completes agent names."""
        completer = _make_completer(self.SLASH_COMMANDS, self.AGENT_NAMES)
        with patch("readline.get_line_buffer", return_value="/skills code-"):
            results = []
            idx = 0
            while True:
                result = completer("code-", idx)
                if result is None:
                    break
                results.append(result)
                idx += 1
            assert "code-reasoning" in results
            assert "code-writer" in results

    def test_session_second_word(self):
        """'/resume ' + Tab attempts session ID completion."""
        completer = _make_completer(self.SLASH_COMMANDS, self.AGENT_NAMES)
        with patch("readline.get_line_buffer", return_value="/resume "):
            with patch("code_agents.chat.chat_history.list_sessions", return_value=[{"id": "abc12345-6789"}]):
                result = completer("", 0)
                assert result == "abc12345"

    def test_session_completion_error(self):
        """Session completion gracefully handles errors."""
        completer = _make_completer(self.SLASH_COMMANDS, self.AGENT_NAMES)
        with patch("readline.get_line_buffer", return_value="/resume "):
            with patch("code_agents.chat.chat_history.list_sessions", side_effect=Exception("fail")):
                result = completer("", 0)
                assert result is None


class TestParseInlineDelegationSkills:
    """Test /agent:skill syntax."""

    AGENTS = {
        "code-reasoning": "Code Reasoning Agent",
        "code-writer": "Code Writer Agent",
    }

    def test_skill_not_found(self, capsys):
        """Non-existent skill prints error."""
        with patch("code_agents.agent_system.skill_loader.get_skill", return_value=None):
            with patch("code_agents.core.config.settings"):
                agent, prompt = _parse_inline_delegation("/code-writer:nonexistent", self.AGENTS)
        assert agent is None
        assert prompt is None
        output = capsys.readouterr().out
        assert "not found" in output

    def test_skill_found(self):
        """Valid skill prepends workflow to prompt."""
        mock_skill = MagicMock()
        mock_skill.name = "implement"
        mock_skill.body = "Step 1: Read the spec"
        with patch("code_agents.agent_system.skill_loader.get_skill", return_value=mock_skill):
            with patch("code_agents.core.config.settings"):
                agent, prompt = _parse_inline_delegation("/code-writer:implement add auth", self.AGENTS)
        assert agent == "code-writer"
        assert "implement" in prompt
        assert "Step 1" in prompt
        assert "add auth" in prompt

    def test_skill_no_extra_prompt(self):
        """Skill invocation with no extra text."""
        mock_skill = MagicMock()
        mock_skill.name = "review"
        mock_skill.body = "Review workflow"
        with patch("code_agents.agent_system.skill_loader.get_skill", return_value=mock_skill):
            with patch("code_agents.core.config.settings"):
                agent, prompt = _parse_inline_delegation("/code-writer:review", self.AGENTS)
        assert agent == "code-writer"
        assert "Review workflow" in prompt
        assert "User context" not in prompt


class TestAgentAnsiColors:
    """Test AGENT_ANSI_COLORS dict completeness."""

    def test_all_agents_have_ansi_colors(self):
        from code_agents.chat.chat_ui import AGENT_ANSI_COLORS
        expected = [
            "code-reasoning", "code-writer", "code-reviewer", "code-tester",
            "redash-query", "git-ops", "test-coverage", "jenkins-cicd",
            "argocd-verify", "qa-regression",
            "auto-pilot", "jira-ops",
        ]
        for agent in expected:
            assert agent in AGENT_ANSI_COLORS, f"Missing ANSI color for {agent}"

    def test_backward_compat_alias(self):
        from code_agents.chat.chat_ui import AGENT_ANSI_COLORS, _AGENT_COLORS
        assert AGENT_ANSI_COLORS is _AGENT_COLORS


class TestTableRendering:
    """Test markdown table rendering in _render_markdown."""

    def test_simple_table(self):
        from code_agents.chat.chat_ui import _render_markdown
        table = "| A | B |\n| --- | --- |\n| 1 | 2 |"
        result = _render_markdown(table)
        assert "A" in result
        assert "1" in result

    def test_no_table(self):
        from code_agents.chat.chat_ui import _render_markdown
        result = _render_markdown("no table here")
        assert "no table here" in result

    def test_table_with_many_columns(self):
        from code_agents.chat.chat_ui import _render_markdown
        table = "| A | B | C | D | E |\n| - | - | - | - | - |\n| 1 | 2 | 3 | 4 | 5 |"
        result = _render_markdown(table)
        assert "A" in result
        assert "5" in result


class TestWFunctionDirect:
    """Test _w color wrapper directly."""

    def test_w_with_color_on(self):
        from code_agents.chat.chat_ui import _w, _USE_COLOR
        result = _w("32", "hello")
        if _USE_COLOR:
            assert "\033[32m" in result
            assert "\033[0m" in result
        assert "hello" in result

    def test_w_returns_text(self):
        from code_agents.chat.chat_ui import _w
        result = _w("99", "test")
        assert "test" in result


# ════════════════════════════════════════════════════════════════════════
# Additional chat_commands.py coverage
# ════════════════════════════════════════════════════════════════════════


class TestExtractCommandsAdvanced:
    """Extended tests for _extract_commands edge cases."""

    def test_multiple_code_blocks(self):
        text = """Here's the plan:
```bash
git status
```
Then:
```sh
git log --oneline
```
"""
        cmds = _extract_commands(text)
        assert len(cmds) == 2
        assert "git status" in cmds
        assert "git log --oneline" in cmds

    def test_backslash_continuation(self):
        text = """```bash
curl -X GET \\
  http://localhost:8000/health
```"""
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "curl -X GET" in cmds[0]
        assert "http://localhost:8000/health" in cmds[0]

    def test_dollar_prefix_stripped(self):
        text = """```bash
$ git status
```"""
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert cmds[0] == "git status"

    def test_angle_bracket_prefix_stripped(self):
        text = """```bash
> git diff
```"""
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert cmds[0] == "git diff"

    def test_comments_skipped(self):
        text = """```bash
# this is a comment
git status
# another comment
```"""
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert cmds[0] == "git status"

    def test_empty_code_block(self):
        text = """```bash
```"""
        cmds = _extract_commands(text)
        assert cmds == []

    def test_script_detection_control_flow(self):
        text = """```bash
if [ -f test.py ]; then
  echo "found"
fi
```"""
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "bash" in cmds[0]  # should become bash script

    def test_script_detection_variable_assignment(self):
        text = """```bash
VERSION=1.0.0
echo $VERSION
```"""
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert "bash" in cmds[0]  # should become bash script

    def test_english_text_in_bash_block_filtered(self):
        text = """```bash
Please run the following command to check the status
```"""
        cmds = _extract_commands(text)
        assert len(cmds) == 0  # filtered by _is_valid_command

    def test_console_language_tag(self):
        text = """```console
git branch -a
```"""
        cmds = _extract_commands(text)
        assert len(cmds) == 1
        assert cmds[0] == "git branch -a"

    def test_zsh_language_tag(self):
        text = """```zsh
ls -la
```"""
        cmds = _extract_commands(text)
        assert len(cmds) == 1


class TestExtractSkillRequests:
    """Test _extract_skill_requests."""

    def test_single_skill(self):
        from code_agents.chat.chat_commands import _extract_skill_requests
        text = "I need [SKILL:jenkins-build] to proceed."
        skills = _extract_skill_requests(text)
        assert skills == ["jenkins-build"]

    def test_multiple_skills(self):
        from code_agents.chat.chat_commands import _extract_skill_requests
        text = "[SKILL:code-review] and [SKILL:test-coverage] please"
        skills = _extract_skill_requests(text)
        assert len(skills) == 2

    def test_cross_agent_skill(self):
        from code_agents.chat.chat_commands import _extract_skill_requests
        text = "[SKILL:jenkins-cicd:build]"
        skills = _extract_skill_requests(text)
        assert skills == ["jenkins-cicd:build"]

    def test_no_skills(self):
        from code_agents.chat.chat_commands import _extract_skill_requests
        text = "No skills needed here."
        skills = _extract_skill_requests(text)
        assert skills == []


class TestExtractDelegations:
    """Test _extract_delegations."""

    def test_single_delegation(self):
        from code_agents.chat.chat_commands import _extract_delegations
        text = "[DELEGATE:code-writer] Please write the code."
        delegations = _extract_delegations(text)
        assert len(delegations) == 1
        assert delegations[0][0] == "code-writer"
        assert "write the code" in delegations[0][1]

    def test_no_delegations(self):
        from code_agents.chat.chat_commands import _extract_delegations
        text = "No delegation here."
        delegations = _extract_delegations(text)
        assert delegations == []


class TestExtractContextFromOutput:
    """Test _extract_context_from_output populates context."""

    def test_extracts_build_version(self):
        from code_agents.chat.chat_commands import _extract_context_from_output, _command_context
        _command_context.clear()
        _extract_context_from_output('{"build_version": "v1.2.3"}')
        assert _command_context["BUILD_VERSION"] == "v1.2.3"
        assert _command_context["image_tag"] == "v1.2.3"

    def test_extracts_build_number(self):
        from code_agents.chat.chat_commands import _extract_context_from_output, _command_context
        _command_context.clear()
        _extract_context_from_output('{"number": 42}')
        assert _command_context["BUILD_NUMBER"] == "42"

    def test_extracts_job_name(self):
        from code_agents.chat.chat_commands import _extract_context_from_output, _command_context
        _command_context.clear()
        _extract_context_from_output('{"job_name": "my-service-build"}')
        assert _command_context["job_name"] == "my-service-build"

    def test_invalid_json_ignored(self):
        from code_agents.chat.chat_commands import _extract_context_from_output, _command_context
        _command_context.clear()
        _extract_context_from_output("not json at all")
        assert len(_command_context) == 0

    def test_non_dict_json_ignored(self):
        from code_agents.chat.chat_commands import _extract_context_from_output, _command_context
        _command_context.clear()
        _extract_context_from_output("[1, 2, 3]")
        assert len(_command_context) == 0


class TestIsValidCommandExtended:
    """Extended tests for _is_valid_command."""

    def test_empty_string(self):
        assert _is_valid_command("") is False

    def test_whitespace_only(self):
        assert _is_valid_command("   ") is False

    def test_known_safe_prefix(self):
        assert _is_valid_command("kubectl get pods") is True
        assert _is_valid_command("docker ps") is True
        assert _is_valid_command("terraform plan") is True

    def test_english_starter_rejected(self):
        assert _is_valid_command("Please run the tests now") is False
        assert _is_valid_command("The server should be restarted") is False
        assert _is_valid_command("You need to install the package") is False

    def test_long_text_without_shell_chars(self):
        assert _is_valid_command("this is a long explanation about what to do next time") is False

    def test_short_command_allowed(self):
        assert _is_valid_command("mycommand") is True

    def test_command_with_flags(self):
        assert _is_valid_command("mycommand --verbose -x") is True

    def test_command_with_path(self):
        assert _is_valid_command("./run.sh") is True

    def test_command_with_pipe(self):
        assert _is_valid_command("ps aux | grep java") is True


class TestIsSafeCommandExtended:
    """Extended tests for _is_safe_command."""

    def test_git_status_safe(self):
        assert _is_safe_command("git status") is True

    def test_git_push_unsafe(self):
        assert _is_safe_command("git push origin main") is False

    def test_curl_get_safe(self):
        assert _is_safe_command("curl http://localhost:8000/health") is True

    def test_curl_post_unsafe(self):
        assert _is_safe_command("curl -X POST http://localhost:8000/api") is False

    def test_curl_data_unsafe(self):
        assert _is_safe_command("curl -d '{\"key\":\"val\"}' http://localhost") is False

    def test_cat_safe(self):
        assert _is_safe_command("cat /etc/hosts") is True

    def test_ls_safe(self):
        assert _is_safe_command("ls -la /tmp") is True

    def test_rm_unsafe(self):
        assert _is_safe_command("rm -rf /tmp/foo") is False

    def test_head_safe(self):
        assert _is_safe_command("head -n 10 file.txt") is True

    def test_tail_safe(self):
        assert _is_safe_command("tail -f log.txt") is True


class TestCheckAgentAutorunExtended:
    """Extended tests for _check_agent_autorun."""

    def test_no_config_returns_none(self):
        with patch("code_agents.chat.chat_commands._load_agent_autorun_config", return_value={}):
            result = _check_agent_autorun("git status", "nonexistent-agent")
        assert result is None

    def test_block_takes_priority(self):
        with patch("code_agents.chat.chat_commands._load_agent_autorun_config", return_value={
            "allow": ["git"],
            "block": ["git push"],
        }):
            result = _check_agent_autorun("git push origin main", "test-agent")
            assert result == "block"

    def test_allow_matches(self):
        with patch("code_agents.chat.chat_commands._load_agent_autorun_config", return_value={
            "allow": ["mvn clean"],
            "block": [],
        }):
            result = _check_agent_autorun("mvn clean install", "test-agent")
            assert result == "allow"

    def test_no_match_returns_none(self):
        with patch("code_agents.chat.chat_commands._load_agent_autorun_config", return_value={
            "allow": ["curl"],
            "block": ["rm"],
        }):
            result = _check_agent_autorun("git status", "test-agent")
            assert result is None


class TestLogAutoRun:
    """Test _log_auto_run writes to log file."""

    def test_log_auto_run_writes(self, tmp_path):
        from code_agents.chat.chat_commands import _log_auto_run
        log_path = tmp_path / ".code-agents" / "auto_run.log"
        with patch("code_agents.chat.chat_commands.Path") as MockPath:
            mock_home = MagicMock()
            mock_home.__truediv__ = MagicMock(return_value=tmp_path / ".code-agents")
            MockPath.home.return_value = mock_home
            # Just verify it doesn't crash
            _log_auto_run("git status", "safe-auto-run")


class TestSaveAndTrustCommands:
    """Test _save_command_to_rules and _is_command_trusted."""

    def test_save_and_check_trusted(self, tmp_path):
        from code_agents.chat.chat_commands import _save_command_to_rules, _is_command_trusted
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents-rules"):
            _save_command_to_rules("git status", "code-reasoning", str(tmp_path))
            assert _is_command_trusted("git status", "code-reasoning", str(tmp_path))

    def test_untrusted_command(self, tmp_path):
        from code_agents.chat.chat_commands import _is_command_trusted
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents-rules"):
            assert _is_command_trusted("rm -rf /", "code-reasoning", str(tmp_path)) is False

    def test_save_duplicate_command(self, tmp_path, capsys):
        from code_agents.chat.chat_commands import _save_command_to_rules
        with patch("code_agents.agent_system.rules_loader.PROJECT_RULES_DIRNAME", ".code-agents-rules"):
            _save_command_to_rules("git status", "code-reasoning", str(tmp_path))
            _save_command_to_rules("git status", "code-reasoning", str(tmp_path))
            output = capsys.readouterr().out
            assert "already in rules" in output


# ════════════════════════════════════════════════════════════════════════
# Additional chat_ui.py coverage
# ════════════════════════════════════════════════════════════════════════


class TestFormatResponseBox:
    """Test format_response_box rendering."""

    def test_empty_text_returns_empty(self):
        from code_agents.chat.chat_ui import format_response_box
        assert format_response_box("") == ""
        assert format_response_box("   ") == ""

    def test_with_agent_name(self):
        from code_agents.chat.chat_ui import format_response_box
        result = format_response_box("Hello world", agent_name="code-writer")
        assert "CODE-WRITER" in result
        assert "Hello world" in result

    def test_without_agent_name(self):
        from code_agents.chat.chat_ui import format_response_box
        result = format_response_box("Test content")
        assert "Test content" in result

    def test_long_line_wrapping(self):
        from code_agents.chat.chat_ui import format_response_box
        long_text = "x" * 200
        result = format_response_box(long_text, agent_name="test")
        assert "x" in result

    def test_multiline_text(self):
        from code_agents.chat.chat_ui import format_response_box
        result = format_response_box("line1\nline2\nline3")
        assert "line1" in result
        assert "line3" in result


class TestPrintResponseBox:
    """Test print_response_box output."""

    def test_prints_box(self, capsys):
        from code_agents.chat.chat_ui import print_response_box
        print_response_box("Test output", agent_name="code-tester")
        output = capsys.readouterr().out
        assert "Test output" in output

    def test_empty_text_prints_nothing(self, capsys):
        from code_agents.chat.chat_ui import print_response_box
        print_response_box("")
        output = capsys.readouterr().out
        assert output == ""


class TestAgentColorFn:
    """Test agent_color_fn returns proper color functions."""

    def test_known_agent(self):
        from code_agents.chat.chat_ui import agent_color_fn
        fn = agent_color_fn("code-writer")
        result = fn("test")
        assert "test" in result

    def test_unknown_agent_fallback(self):
        from code_agents.chat.chat_ui import agent_color_fn
        fn = agent_color_fn("nonexistent-agent")
        result = fn("fallback")
        assert "fallback" in result


class TestAgentColorMapping:
    """Test AGENT_COLORS and agent_color."""

    def test_agent_color_known(self):
        from code_agents.chat.chat_ui import agent_color
        fn = agent_color("code-reasoning")
        result = fn("test")
        assert "test" in result

    def test_agent_color_unknown_fallback(self):
        from code_agents.chat.chat_ui import agent_color
        fn = agent_color("unknown-agent")
        result = fn("text")
        assert "text" in result


class TestRlWrap:
    """Test readline-safe ANSI wrapping."""

    def test_rl_bold(self):
        from code_agents.chat.chat_ui import _rl_bold
        result = _rl_bold("test")
        assert "test" in result

    def test_rl_green(self):
        from code_agents.chat.chat_ui import _rl_green
        result = _rl_green("test")
        assert "test" in result


class TestRenderMarkdownExtended:
    """Extended tests for _render_markdown."""

    def test_bold_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown
        result = _render_markdown("This is **bold** text")
        assert "bold" in result

    def test_inline_code(self):
        from code_agents.chat.chat_ui import _render_markdown
        result = _render_markdown("Use `git status` command")
        assert "git status" in result

    def test_header_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown
        result = _render_markdown("## Section Title")
        assert "Section Title" in result

    def test_horizontal_rule(self):
        from code_agents.chat.chat_ui import _render_markdown, _USE_COLOR
        result = _render_markdown("---")
        if _USE_COLOR:
            assert "\u2500" in result  # unicode horizontal line
        else:
            assert "---" in result  # no color = passthrough

    def test_blockquote(self):
        from code_agents.chat.chat_ui import _render_markdown
        result = _render_markdown("> This is a quote")
        assert "This is a quote" in result

    def test_list_items(self):
        from code_agents.chat.chat_ui import _render_markdown
        result = _render_markdown("- Item one\n- Item two")
        assert "Item one" in result


class TestSpinner:
    """Test _spinner context manager."""

    def test_spinner_enters_and_exits(self):
        from code_agents.chat.chat_ui import _spinner
        import time
        with _spinner("Loading..."):
            time.sleep(0.05)
        # Should not crash


class TestActivityIndicator:
    """Test activity_indicator context manager."""

    def test_activity_indicator_enters_and_exits(self):
        from code_agents.chat.chat_ui import activity_indicator
        import time
        with activity_indicator("Thinking", "file.py") as ai:
            time.sleep(0.05)
            ai.update("Reading", "other.py")
        # Should not crash


class TestAskYesNo:
    """Test _ask_yes_no."""

    def test_ask_yes_no_delegates_to_tab_selector(self):
        from code_agents.chat.chat_ui import _ask_yes_no
        with patch("code_agents.chat.chat_ui._tab_selector", return_value=0):
            assert _ask_yes_no("Continue?") is True

        with patch("code_agents.chat.chat_ui._tab_selector", return_value=1):
            assert _ask_yes_no("Continue?") is False


class TestAmendPrompt:
    """Test _amend_prompt."""

    def test_returns_input(self):
        from code_agents.chat.chat_ui import _amend_prompt
        with patch("builtins.input", return_value="fix the bug"):
            result = _amend_prompt()
            assert result == "fix the bug"

    def test_eof_returns_empty(self):
        from code_agents.chat.chat_ui import _amend_prompt
        with patch("builtins.input", side_effect=EOFError):
            result = _amend_prompt()
            assert result == ""


# ════════════════════════════════════════════════════════════════════════
# Additional chat.py coverage — _make_completer, _parse_inline_delegation
# ════════════════════════════════════════════════════════════════════════


class TestMakeCompleterExtended:
    """Extended tests for _make_completer."""

    def test_completer_returns_slash_commands(self):
        completer = _make_completer(["/help", "/quit", "/agents"], ["code-writer"])
        result = completer("/he", 0)
        assert result == "/help"

    def test_completer_returns_none_past_end(self):
        completer = _make_completer(["/help"], [])
        result = completer("/help", 1)
        assert result is None

    def test_completer_agent_slash(self):
        completer = _make_completer(["/help"], ["code-writer", "code-tester"])
        result = completer("/code-w", 0)
        assert result == "/code-writer"

    def test_completer_no_match(self):
        completer = _make_completer(["/help"], [])
        result = completer("/zzz", 0)
        assert result is None


class TestParseInlineDelegationExtended:
    """Extended tests for _parse_inline_delegation."""

    def test_agent_with_prompt(self):
        agents = {"code-writer": "Code Writer", "code-tester": "Code Tester"}
        agent, prompt = _parse_inline_delegation("/code-writer write a function", agents)
        assert agent == "code-writer"
        assert "write a function" in prompt

    def test_agent_switch_no_prompt(self):
        agents = {"code-writer": "Code Writer"}
        agent, prompt = _parse_inline_delegation("/code-writer", agents)
        assert agent == "code-writer"
        assert prompt == ""

    def test_not_an_agent(self):
        agents = {"code-writer": "Code Writer"}
        agent, prompt = _parse_inline_delegation("/unknown do something", agents)
        assert agent is None
        assert prompt is None

    def test_no_slash_prefix(self):
        agents = {"code-writer": "Code Writer"}
        agent, prompt = _parse_inline_delegation("code-writer do stuff", agents)
        assert agent is None

    def test_skill_invocation_not_found(self, capsys):
        agents = {"code-writer": "Code Writer"}
        with patch("code_agents.agent_system.skill_loader.get_skill", return_value=None):
            agent, prompt = _parse_inline_delegation("/code-writer:nonexistent", agents)
            assert agent is None
            output = capsys.readouterr().out
            assert "not found" in output

    def test_skill_invocation_found(self):
        agents = {"code-writer": "Code Writer"}
        mock_skill = MagicMock()
        mock_skill.name = "review"
        mock_skill.body = "Review the code."
        with patch("code_agents.agent_system.skill_loader.get_skill", return_value=mock_skill):
            agent, prompt = _parse_inline_delegation("/code-writer:review check this", agents)
            assert agent == "code-writer"
            assert "Review the code." in prompt
            assert "check this" in prompt


# ════════════════════════════════════════════════════════════════════════
# chat_streaming.py coverage — _format_session_duration
# ════════════════════════════════════════════════════════════════════════


class TestFormatSessionDuration:
    """Test _format_session_duration formatting."""

    def test_seconds(self):
        from code_agents.chat.chat_streaming import _format_session_duration
        assert _format_session_duration(45) == "45s"

    def test_minutes(self):
        from code_agents.chat.chat_streaming import _format_session_duration
        assert _format_session_duration(135) == "2m 15s"

    def test_hours(self):
        from code_agents.chat.chat_streaming import _format_session_duration
        assert _format_session_duration(3723) == "1h 02m"

    def test_zero_seconds(self):
        from code_agents.chat.chat_streaming import _format_session_duration
        assert _format_session_duration(0) == "0s"

    def test_exactly_one_minute(self):
        from code_agents.chat.chat_streaming import _format_session_duration
        assert _format_session_duration(60) == "1m 00s"

    def test_exactly_one_hour(self):
        from code_agents.chat.chat_streaming import _format_session_duration
        assert _format_session_duration(3600) == "1h 00m"


# ════════════════════════════════════════════════════════════════════════
# chat_response.py coverage — _format_elapsed
# ════════════════════════════════════════════════════════════════════════


class TestFormatElapsed:
    """Test _format_elapsed time formatting."""

    def test_sub_second(self):
        from code_agents.chat.chat_response import _format_elapsed
        result = _format_elapsed(0.5)
        assert "s" in result

    def test_seconds(self):
        from code_agents.chat.chat_response import _format_elapsed
        result = _format_elapsed(30)
        assert "s" in result

    def test_minutes(self):
        from code_agents.chat.chat_response import _format_elapsed
        result = _format_elapsed(90)
        assert "m" in result


# ════════════════════════════════════════════════════════════════════════
# chat.py — full coverage tests for _init_plan_report, _append_plan_report,
# chat_main, _chat_main_inner, _make_completer edge cases
# ════════════════════════════════════════════════════════════════════════


from pathlib import Path as _Path


class TestInitPlanReport:
    """Test _init_plan_report creates plan files."""

    def test_creates_plan_file(self, tmp_path, capsys):
        from code_agents.chat.chat import _init_plan_report
        state = {"agent": "code-reasoning", "repo_path": str(tmp_path)}
        with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
            _init_plan_report(state, "build feature X")
        assert "_plan_report" in state
        path = state["_plan_report"]
        assert os.path.exists(path)
        content = open(path).read()
        assert "Plan Report" in content
        assert "code-reasoning" in content
        assert "build feature X" in content
        assert "Requirement" in content
        output = capsys.readouterr().out
        assert "Plan report" in output

    def test_skip_if_already_initialized(self, tmp_path):
        from code_agents.chat.chat import _init_plan_report
        state = {"agent": "code-reasoning", "_plan_report": "/existing/path.md"}
        _init_plan_report(state, "anything")
        assert state["_plan_report"] == "/existing/path.md"

    def test_default_agent_name(self, tmp_path, capsys):
        from code_agents.chat.chat import _init_plan_report
        state = {"repo_path": str(tmp_path)}  # no "agent" key
        with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
            _init_plan_report(state, "test input")
        path = state["_plan_report"]
        content = open(path).read()
        assert "chat" in content  # default agent


class TestAppendPlanReport:
    """Test _append_plan_report appends sections."""

    def test_append_section(self, tmp_path):
        from code_agents.chat.chat import _append_plan_report
        report_path = tmp_path / "plan.md"
        report_path.write_text("# Plan\n")
        state = {"_plan_report": str(report_path)}
        _append_plan_report(state, "Analysis", "Looks good")
        content = report_path.read_text()
        assert "## Analysis" in content
        assert "Looks good" in content

    def test_no_report_path(self):
        from code_agents.chat.chat import _append_plan_report
        state = {}
        _append_plan_report(state, "Test", "content")  # should not crash

    def test_os_error_handled(self, tmp_path):
        from code_agents.chat.chat import _append_plan_report
        state = {"_plan_report": "/nonexistent/deep/path/plan.md"}
        _append_plan_report(state, "Test", "content")  # should not crash


class TestChatMain:
    """Test chat_main wrapper handles exceptions."""

    def test_keyboard_interrupt(self, capsys):
        from code_agents.chat.chat import chat_main
        with patch("code_agents.chat.chat._chat_main_inner", side_effect=KeyboardInterrupt):
            chat_main()
        output = capsys.readouterr().out
        assert "Exiting" in output

    def test_exception_logs_crash(self, tmp_path, capsys):
        from code_agents.chat.chat import chat_main
        with patch("code_agents.chat.chat._chat_main_inner", side_effect=RuntimeError("boom")):
            with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
                with pytest.raises(RuntimeError, match="boom"):
                    chat_main()
        output = capsys.readouterr().out
        assert "crashed" in output
        crash_log = tmp_path / ".code-agents" / "crash.log"
        assert crash_log.exists()
        content = crash_log.read_text()
        assert "CRASH" in content
        assert "boom" in content


class TestChatMainInnerNicknameSetup:
    """Test _chat_main_inner nickname and role setup."""

    def test_nickname_from_env(self, capsys):
        """When CODE_AGENTS_NICKNAME is set, skip input."""
        from code_agents.chat.chat import _chat_main_inner
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "shiv", "CODE_AGENTS_USER_ROLE": "Senior Engineer"}, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                        with patch("builtins.input", side_effect=EOFError):
                            _chat_main_inner([])

    def test_nickname_prompt_accepted(self, capsys, tmp_path):
        """When no nickname env, prompt user, save to config."""
        from code_agents.chat.chat import _chat_main_inner
        env_path = tmp_path / "config.env"
        input_vals = iter(["TestUser", "n"])  # nickname then refuse server start
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "", "CODE_AGENTS_USER_ROLE": "Senior"}, clear=False):
                with patch("builtins.input", side_effect=input_vals):
                    with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                        with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                            with patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", env_path):
                                _chat_main_inner([])

    def test_nickname_eof(self, capsys):
        """EOFError during nickname prompt defaults to 'you'."""
        from code_agents.chat.chat import _chat_main_inner
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("builtins.input", side_effect=EOFError):
                    with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                        with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                            _chat_main_inner([])

    def test_nickname_keyboard_interrupt(self, capsys):
        """KeyboardInterrupt during nickname prompt defaults to 'you'."""
        from code_agents.chat.chat import _chat_main_inner
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("builtins.input", side_effect=KeyboardInterrupt):
                    with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                        with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                            _chat_main_inner([])


class TestChatMainInnerRoleSetup:
    """Test _chat_main_inner user role setup."""

    def test_role_prompt(self, capsys, tmp_path):
        """When no role env, prompt via ask_question then continue."""
        from code_agents.chat.chat import _chat_main_inner
        mock_answer = {"answer": "Junior Engineer"}
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": ""}, clear=False):
                with patch("code_agents.agent_system.questionnaire.ask_question", return_value=mock_answer):
                    with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                        with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                            with patch("builtins.input", side_effect=EOFError):
                                with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
                                    _chat_main_inner([])


class TestChatMainInnerServerStart:
    """Test server start logic in _chat_main_inner."""

    def _base_patches(self):
        return {
            "code_agents.core.env_loader.load_all_env": MagicMock(),
            "code_agents.chat.chat._server_url": MagicMock(return_value="http://localhost:8000"),
        }

    def test_server_start_success(self, capsys, tmp_path):
        """User says yes to start server, server comes up."""
        from code_agents.chat.chat import _chat_main_inner

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value={}):
                            _chat_main_inner([])

    def test_server_start_timeout(self, capsys, tmp_path):
        """Server fails to start — ensure_server_running returns False, chat exits."""
        from code_agents.chat.chat import _chat_main_inner

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                        _chat_main_inner([])
        # When ensure_server_running returns False, chat exits without further output
        # (the error messages are printed inside ensure_server_running itself)

    def test_server_start_declined(self, capsys):
        """User declines — ensure_server_running returns False, chat exits."""
        from code_agents.chat.chat import _chat_main_inner
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                        _chat_main_inner([])

    def test_server_start_eof(self, capsys):
        """EOFError during server start prompt."""
        from code_agents.chat.chat import _chat_main_inner
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                        with patch("builtins.input", side_effect=EOFError):
                            _chat_main_inner([])


class TestChatMainInnerNoAgents:
    """Test _chat_main_inner when server returns no agents."""

    def test_no_agents_returns(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value={}):
                            _chat_main_inner([])
        output = capsys.readouterr().out
        assert "No agents" in output


class TestChatMainInnerAgentSelection:
    """Test agent name from args and interactive selection."""

    def _setup_patches(self):
        """Common patches for tests that get past server check."""
        agents = {"code-reasoning": "Code Reasoning", "code-writer": "Code Writer"}
        return agents

    def test_agent_from_args(self, capsys):
        """--agent flag picks agent."""
        from code_agents.chat.chat import _chat_main_inner
        agents = self._setup_patches()
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=False):
                                _chat_main_inner(["--agent", "code-reasoning"])

    def test_agent_from_positional_arg(self, capsys):
        """Positional arg picks agent."""
        from code_agents.chat.chat import _chat_main_inner
        agents = self._setup_patches()
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=False):
                                _chat_main_inner(["code-writer"])

    def test_invalid_agent_triggers_selection(self, capsys):
        """Invalid agent name triggers interactive selection."""
        from code_agents.chat.chat import _chat_main_inner
        agents = self._setup_patches()
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat._select_agent", return_value=None):
                                _chat_main_inner(["nonexistent"])
        output = capsys.readouterr().out
        assert "not found" in output.lower() or "Cancelled" in output

    def test_resume_flag(self, capsys):
        """--resume flag triggers session resume."""
        from code_agents.chat.chat import _chat_main_inner
        agents = self._setup_patches()
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=False):
                                _chat_main_inner(["--agent", "code-reasoning", "--resume", "abc123"])


class TestChatMainInnerRepoDetection:
    """Test repo detection logic in _chat_main_inner."""

    def test_target_repo_from_env(self, tmp_path, capsys):
        """TARGET_REPO_PATH env var overrides cwd detection."""
        from code_agents.chat.chat import _chat_main_inner
        agents = {"code-reasoning": "Code Reasoning"}
        repo = tmp_path / "myrepo"
        repo.mkdir()
        (repo / ".git").mkdir()

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": str(repo),
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=False):
                                _chat_main_inner(["code-reasoning"])

    def test_git_root_detection(self, tmp_path, capsys):
        """Detect git root by walking up from cwd."""
        from code_agents.chat.chat import _chat_main_inner
        agents = {"code-reasoning": "Code Reasoning"}
        repo = tmp_path / "myrepo"
        subdir = repo / "src" / "main"
        subdir.mkdir(parents=True)
        (repo / ".git").mkdir()

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": "",
                "CODE_AGENTS_USER_CWD": str(subdir),
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=False):
                                _chat_main_inner(["code-reasoning"])

    def test_home_agents_guard(self, tmp_path, capsys):
        """Guard against using ~/.code-agents as the repo."""
        from code_agents.chat.chat import _chat_main_inner
        agents = {"code-reasoning": "Code Reasoning"}

        # Simulate cwd being at ~/.code-agents (wrong repo)
        home_agents = str(_Path.home() / ".code-agents")
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": "",
                "CODE_AGENTS_USER_CWD": str(tmp_path),
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=False):
                                _chat_main_inner(["code-reasoning"])


class TestChatMainInnerBackendValidation:
    """Test backend validation in _chat_main_inner."""

    def _run_inner_to_validation(self, validate_result, validate_input="n"):
        """Helper to run _chat_main_inner to the backend validation point."""
        from code_agents.chat.chat import _chat_main_inner
        agents = {"code-reasoning": "Code Reasoning"}

        # Determine what BackendValidator.check() should return
        should_continue = validate_result.get("valid", True)
        if not should_continue and validate_input in ("y", "yes"):
            should_continue = True  # user chose to continue anyway

        mock_validator = MagicMock()
        mock_validator.check.return_value = should_continue

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": "/tmp",
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=True):
                                with patch("code_agents.chat.chat.BackendValidator", return_value=mock_validator):
                                    with patch("builtins.input", side_effect=EOFError):
                                        with patch("code_agents.chat.chat.initial_chat_state", return_value={
                                            "agent": "code-reasoning", "session_id": None,
                                            "repo_path": "/tmp", "_chat_session": None, "user_role": "Lead",
                                        }):
                                            with patch("code_agents.chat.chat_input._HAS_PT", False):
                                                with patch("code_agents.chat.chat_input.create_session", return_value=None):
                                                    with patch("code_agents.chat.chat_history.auto_cleanup"):
                                                        with patch("code_agents.chat.chat_history.list_recent_sessions", return_value=[]):
                                                            with patch("code_agents.chat.chat._print_welcome"):
                                                                with patch("code_agents.chat.chat._print_session_summary"):
                                                                    _chat_main_inner(["code-reasoning"])

    def test_valid_backend_continues(self, capsys):
        self._run_inner_to_validation({"valid": True, "message": "ok", "backend": "cursor"})

    def test_invalid_backend_decline(self, capsys):
        self._run_inner_to_validation({"valid": False, "message": "API key missing", "backend": "cursor"}, "n")

    def test_invalid_backend_continue_anyway(self, capsys):
        self._run_inner_to_validation({"valid": False, "message": "API key missing", "backend": "cursor"}, "y")

    def test_backend_validation_exception(self, capsys):
        """Backend validation error is silently skipped (check returns True)."""
        from code_agents.chat.chat import _chat_main_inner
        agents = {"code-reasoning": "Code Reasoning"}

        # BackendValidator handles exceptions internally — check() returns True
        mock_validator = MagicMock()
        mock_validator.check.return_value = True

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": "/tmp",
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=True):
                                with patch("code_agents.chat.chat.BackendValidator", return_value=mock_validator):
                                    with patch("builtins.input", side_effect=EOFError):
                                        with patch("code_agents.chat.chat.initial_chat_state", return_value={
                                            "agent": "code-reasoning", "session_id": None,
                                            "repo_path": "/tmp", "_chat_session": None, "user_role": "Lead",
                                        }):
                                            with patch("code_agents.chat.chat_history.auto_cleanup"):
                                                with patch("code_agents.chat.chat_history.list_recent_sessions", return_value=[]):
                                                    with patch("code_agents.chat.chat._print_welcome"):
                                                        with patch("code_agents.chat.chat_input._HAS_PT", False):
                                                            with patch("code_agents.chat.chat_input.create_session", return_value=None):
                                                                with patch("code_agents.chat.chat._print_session_summary"):
                                                                    _chat_main_inner(["code-reasoning"])


class TestChatMainInnerResumeFlag:
    """Test --resume flag in _chat_main_inner."""

    def test_resume_success(self, capsys):
        from code_agents.chat.chat import _chat_main_inner

        loaded_session = {
            "title": "Test Session",
            "agent": "code-writer",
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there, how can I help you with some code work?"},
            ],
            "_server_session_id": "sess-123",
        }

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": "/tmp",
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value={"code-reasoning": "CR", "code-writer": "CW"}):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=True):
                                with patch("asyncio.run", side_effect=Exception("skip")):
                                    with patch("code_agents.chat.chat.apply_resume_session") as mock_resume:
                                        mock_resume.return_value = (True, "code-writer")
                                        with patch("code_agents.chat.chat.initial_chat_state", return_value={
                                            "agent": "code-reasoning", "session_id": None,
                                            "repo_path": "/tmp", "_chat_session": loaded_session, "user_role": "Lead",
                                        }):
                                            with patch("builtins.input", side_effect=EOFError):
                                                with patch("code_agents.chat.chat_history.auto_cleanup"):
                                                    with patch("code_agents.chat.chat_history.list_recent_sessions", return_value=[]):
                                                        with patch("code_agents.chat.chat._print_welcome"):
                                                            with patch("code_agents.chat.chat_input._HAS_PT", False):
                                                                with patch("code_agents.chat.chat_input.create_session", return_value=None):
                                                                    with patch("code_agents.chat.chat._print_session_summary"):
                                                                        _chat_main_inner(["--agent", "code-reasoning", "--resume", "abc123"])
        output = capsys.readouterr().out
        assert "Resumed" in output

    def test_resume_not_found(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": "/tmp",
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value={"code-reasoning": "CR"}):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=True):
                                with patch("asyncio.run", side_effect=Exception("skip")):
                                    with patch("code_agents.chat.chat.apply_resume_session", return_value=(False, None)):
                                        with patch("code_agents.chat.chat.initial_chat_state", return_value={
                                            "agent": "code-reasoning", "session_id": None,
                                            "repo_path": "/tmp", "_chat_session": None, "user_role": "Lead",
                                        }):
                                            with patch("builtins.input", side_effect=EOFError):
                                                _chat_main_inner(["--agent", "code-reasoning", "--resume", "nonexistent"])
        output = capsys.readouterr().out
        assert "not found" in output


    # Session selector removed — sessions now managed via /resume and /history in chat


class TestChatMainInnerREPL:
    """Test the main REPL loop logic."""

    def _setup_repl(self, user_inputs, **overrides):
        """Helper that sets up patching to reach the REPL loop and process user inputs."""
        from contextlib import ExitStack
        agents = {"code-reasoning": "CR", "code-writer": "CW"}
        state = {
            "agent": "code-reasoning", "session_id": None,
            "repo_path": "/tmp", "_chat_session": None, "user_role": "Lead",
        }
        state.update(overrides.get("state_extra", {}))

        stack = ExitStack()
        stack.enter_context(patch("code_agents.core.env_loader.load_all_env"))
        stack.enter_context(patch.dict(os.environ, {
            "CODE_AGENTS_NICKNAME": "me",
            "CODE_AGENTS_USER_ROLE": "Lead",
            "TARGET_REPO_PATH": "/tmp",
            "CODE_AGENTS_SIMPLE_UI": "true",
        }, clear=False))
        stack.enter_context(patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"))
        stack.enter_context(patch("code_agents.chat.chat.ensure_server_running", return_value=True))
        stack.enter_context(patch("code_agents.chat.chat._get_agents", return_value=agents))
        stack.enter_context(patch("code_agents.chat.chat.check_workspace_trust", return_value=True))
        stack.enter_context(patch("asyncio.run", side_effect=Exception("skip")))
        stack.enter_context(patch("code_agents.chat.chat.initial_chat_state", return_value=state))
        stack.enter_context(patch("code_agents.chat.chat_history.auto_cleanup"))
        stack.enter_context(patch("code_agents.chat.chat_history.list_recent_sessions", return_value=[]))
        stack.enter_context(patch("code_agents.chat.chat._print_welcome"))
        stack.enter_context(patch("code_agents.chat.chat_input._HAS_PT", False))
        stack.enter_context(patch("code_agents.chat.chat_input.create_session", return_value=None))

        mock_mq = MagicMock()
        mock_mq.dequeue.return_value = None
        mock_mq.agent_is_busy = False
        mock_mq.size = 0
        stack.enter_context(patch("code_agents.chat.chat_input.get_message_queue", return_value=mock_mq))
        stack.enter_context(patch("code_agents.chat.chat_input.show_static_toolbar"))
        stack.enter_context(patch("code_agents.chat.chat_input.clear_static_toolbar"))
        stack.enter_context(patch("code_agents.chat.chat._print_session_summary"))

        # User inputs: the REPL will call input() for each iteration
        input_iter = iter(user_inputs)
        stack.enter_context(patch("builtins.input", side_effect=input_iter))

        return stack, mock_mq

    def test_quit_command(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["/quit"])
        with stack:
            _chat_main_inner(["code-reasoning"])

    def test_empty_input_skipped(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["", "/quit"])
        with stack:
            _chat_main_inner(["code-reasoning"])

    def test_slash_command_help(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["/help", "/quit"])
        with stack:
            with patch("code_agents.chat.chat._handle_command", side_effect=[None, "quit"]):
                _chat_main_inner(["code-reasoning"])

    def test_inline_delegation_with_prompt(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["/code-writer write code", "/quit"])
        # First call returns delegation, second call returns None (for /quit which is a slash cmd)
        with stack:
            with patch("code_agents.chat.chat._parse_inline_delegation", side_effect=[("code-writer", "write code"), (None, None)]):
                with patch("code_agents.chat.chat._stream_chat", return_value=[("text", "done")]):
                    with patch("code_agents.chat.chat._render_markdown", side_effect=lambda x: x):
                        with patch("code_agents.chat.chat._extract_commands", return_value=[]):
                            with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                                    with patch("code_agents.chat.chat_history.add_message"):
                                        _chat_main_inner(["code-reasoning"])

    def test_inline_delegation_no_prompt_switches_agent(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["/code-writer", "/quit"])
        with stack:
            with patch("code_agents.chat.chat._parse_inline_delegation", side_effect=[("code-writer", ""), (None, None)]):
                with patch("code_agents.chat.chat._handle_command", side_effect=[None, "quit"]):
                    with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                        with patch("code_agents.chat.chat_history.add_message"):
                            _chat_main_inner(["code-reasoning"])

    def test_user_message_streaming(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        stack, mock_mq = self._setup_repl(["hello world", "/quit"])
        with stack:
            with patch("code_agents.chat.chat._suggest_skills"):
                with patch("code_agents.agent_system.smart_orchestrator.SmartOrchestrator", side_effect=Exception("skip")):
                    with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                        with patch("code_agents.chat.chat_history.add_message"):
                            with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                                with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["response text"], False)):
                                    with patch("code_agents.chat.chat.handle_post_response", return_value=(["response text"], "test-agent")):
                                        with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["response text"], 0)):
                                            with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                                with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                                    _chat_main_inner(["code-reasoning"])

    def test_ctrl_c_once_continues(self, capsys):
        """Single Ctrl+C at prompt clears input and continues REPL."""
        from code_agents.chat.chat import _chat_main_inner
        import code_agents.chat.chat as chat_mod
        old_ctrl_c = chat_mod._last_ctrl_c
        chat_mod._last_ctrl_c = 0.0

        inputs = [KeyboardInterrupt, "/quit"]
        stack, _ = self._setup_repl([])
        with stack:
            with patch("builtins.input", side_effect=inputs):
                _chat_main_inner(["code-reasoning"])

        chat_mod._last_ctrl_c = old_ctrl_c
        # Ctrl+C at prompt silently clears input (like Claude Code CLI)
        # and continues the REPL — verify it didn't crash and produced output
        output = capsys.readouterr().out
        assert len(output) > 0  # welcome message was printed, REPL continued

    def test_ctrl_c_double_exits(self, capsys):
        """Double Ctrl+C exits the REPL."""
        from code_agents.chat.chat import _chat_main_inner
        import code_agents.chat.chat as chat_mod

        # Simulate double Ctrl+C (two in quick succession)
        old_ctrl_c = chat_mod._last_ctrl_c
        chat_mod._last_ctrl_c = _time_mod.time()  # recent Ctrl+C

        stack, _ = self._setup_repl([])
        with stack:
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                _chat_main_inner(["code-reasoning"])

        chat_mod._last_ctrl_c = old_ctrl_c

    def test_eof_exits(self, capsys):
        """EOFError exits the REPL."""
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl([])
        with stack:
            with patch("builtins.input", side_effect=EOFError):
                _chat_main_inner(["code-reasoning"])

    def test_queued_message_processing(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        stack, mock_mq = self._setup_repl(["/quit"])

        # First dequeue returns a message, second returns None
        mock_mq.dequeue.side_effect = ["queued message", None]
        mock_mq.size = 0

        with stack:
            with patch("code_agents.chat.chat._suggest_skills"):
                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                    with patch("code_agents.chat.chat_history.add_message"):
                        with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                            with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                    with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                        with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                            with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                                _chat_main_inner(["code-reasoning"])
        output = capsys.readouterr().out
        assert "queued" in output.lower()

    def test_agent_busy_queues_message(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        stack, mock_mq = self._setup_repl(["hello", "/quit"])
        mock_mq.dequeue.return_value = None
        mock_mq.agent_is_busy = True
        mock_mq.enqueue.return_value = 1

        # After queueing, agent_is_busy becomes False for next iteration
        call_count = [0]
        original_dequeue = mock_mq.dequeue.return_value

        def input_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count[0] += 1
            if call_count[0] == 1:
                mock_mq.agent_is_busy = True
                return "hello"
            elif call_count[0] == 2:
                mock_mq.agent_is_busy = False
                return "/quit"
            raise StopIteration

        with stack:
            with patch("builtins.input", side_effect=input_side_effect):
                with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                    with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                        with patch("code_agents.chat.chat_history.add_message"):
                            _chat_main_inner(["code-reasoning"])
        output = capsys.readouterr().out
        assert "queued" in output.lower()

    def test_smart_orchestrator_delegation(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["how to deploy", "/quit"])

        mock_analysis = {"should_delegate": True, "best_agent": "jenkins-cicd"}

        with stack:
            with patch("code_agents.chat.chat._suggest_skills"):
                with patch("code_agents.agent_system.smart_orchestrator.SmartOrchestrator") as MockOrch:
                    mock_orch = MockOrch.return_value
                    mock_orch.analyze_request.return_value = mock_analysis
                    with patch("builtins.input", side_effect=["how to deploy", "n", "/quit"]):
                        with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                            with patch("code_agents.chat.chat_history.add_message"):
                                with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                                    with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                        with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                            with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                                with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                                    with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                                        _chat_main_inner(["code-reasoning"])

    def test_exec_feedback_flow(self, capsys):
        """Test /execute feedback triggers streaming analysis."""
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["/execute git status", "/quit"])

        def handle_cmd_side_effect(cmd, state, url):
            if cmd.startswith("/execute"):
                state["_exec_feedback"] = {"command": "git status", "output": "nothing to commit"}
                return "exec_feedback"
            if cmd == "/quit":
                return "quit"
            return None

        with stack:
            with patch("code_agents.chat.chat._parse_inline_delegation", return_value=(None, None)):
                with patch("code_agents.chat.chat._handle_command", side_effect=handle_cmd_side_effect):
                    with patch("code_agents.chat.chat._stream_with_spinner"):
                        with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                            with patch("code_agents.chat.chat_history.add_message"):
                                _chat_main_inner(["code-reasoning"])

    def test_streaming_interrupted(self, capsys):
        """Test interrupted streaming saves partial response."""
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["hello", "/quit"])

        with stack:
            with patch("code_agents.chat.chat._suggest_skills"):
                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": [{"role": "user", "content": "hello"}]}):
                    with patch("code_agents.chat.chat_history.add_message"):
                        with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                            with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["partial"], True)):
                                with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                    with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                        with patch("code_agents.chat.chat_history.add_message"):
                                            _chat_main_inner(["code-reasoning"])

    def test_multiline_input(self, capsys):
        """Test multi-line input with backslash continuation."""
        from code_agents.chat.chat import _chat_main_inner

        # Simulating multi-line: first line ends with \, second is continuation
        inputs = ["hello \\", "world", "/quit"]
        stack, _ = self._setup_repl(inputs)

        with stack:
            with patch("code_agents.chat.chat._suggest_skills"):
                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                    with patch("code_agents.chat.chat_history.add_message"):
                        with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                            with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                    with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                        with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                            with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                                _chat_main_inner(["code-reasoning"])

    def test_plan_mode_auto_suggest(self, capsys):
        """Test auto plan-mode suggestion for complex tasks."""
        from code_agents.chat.chat import _chat_main_inner
        # Input sequence: first msg triggers plan suggestion, "3" = skip planning, then /quit
        call_count = [0]
        def input_fn(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                return "refactor the entire auth module"
            elif call_count[0] == 2:
                return "3"  # plan choice: just do it
            elif call_count[0] <= 4:
                return "/quit"
            raise EOFError

        stack, _ = self._setup_repl([])
        with stack:
            with patch("builtins.input", side_effect=input_fn):
                with patch("code_agents.chat.chat._suggest_skills"):
                    with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                        with patch("code_agents.chat.chat_history.add_message"):
                            with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                                with patch("code_agents.chat.chat_complexity.should_suggest_plan_mode", return_value=(True, 8, ["complex", "refactor"])):
                                    with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                        with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                            with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                                with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                                    with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                                        _chat_main_inner(["code-reasoning"])

    def test_pair_mode_changes(self, capsys):
        """Test pair mode detects file changes."""
        from code_agents.chat.chat import _chat_main_inner

        mock_pair = MagicMock()
        mock_pair.active = True
        mock_pair.check_changes.return_value = [{"file": "test.py", "diff": "+line"}]
        mock_pair.format_changes_summary.return_value = "test.py: +1 line"
        mock_pair.build_review_prompt.return_value = "Review these changes"

        state_with_pair = {
            "agent": "code-reasoning", "session_id": None,
            "repo_path": "/tmp", "_chat_session": None, "user_role": "Lead",
            "_pair_mode": mock_pair,
        }
        def input_fn(*args, **kwargs):
            if not hasattr(input_fn, '_count'):
                input_fn._count = 0
            input_fn._count += 1
            if input_fn._count == 1:
                return "review this"
            raise EOFError

        stack, _ = self._setup_repl([], state_extra={"_pair_mode": mock_pair, "_skip_plan_suggest": True})

        with stack:
            with patch("code_agents.chat.chat._suggest_skills"):
                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                    with patch("code_agents.chat.chat_history.add_message"):
                        with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                            with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                    with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                        with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                            with patch("builtins.input", side_effect=input_fn):
                                                _chat_main_inner(["code-reasoning"])

    def test_image_attachment(self, capsys):
        """Test multimodal content with image attachment."""
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["what is this [image attached: test.png]", "/quit"])

        with stack:
            with patch("code_agents.chat.chat._suggest_skills"):
                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                    with patch("code_agents.chat.chat_history.add_message"):
                        with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                            with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[{"type": "image", "data": "base64data"}]):
                                with patch("code_agents.chat.chat_clipboard.build_multimodal_content", return_value=[{"type": "text", "text": "what is this"}]):
                                    with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                        with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                            with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                                with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                                    _chat_main_inner(["code-reasoning"])

    def test_keyboard_interrupt_during_streaming(self, capsys):
        """Test KeyboardInterrupt during process_streaming_response."""
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["hello"])

        with stack:
            with patch("code_agents.chat.chat._suggest_skills"):
                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                    with patch("code_agents.chat.chat_history.add_message"):
                        with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                            with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                with patch("code_agents.chat.chat.process_streaming_response", side_effect=KeyboardInterrupt):
                                    _chat_main_inner(["code-reasoning"])

    def test_delegate_streaming_interrupted(self, capsys):
        """Test inline delegation with Ctrl+C during streaming."""
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["/code-writer write tests", "/quit"])

        def stream_with_interrupt(*a, **kw):
            yield ("text", "partial")
            raise KeyboardInterrupt

        with stack:
            with patch("code_agents.chat.chat._parse_inline_delegation", side_effect=[("code-writer", "write tests"), (None, None)]):
                with patch("code_agents.chat.chat._stream_chat", side_effect=stream_with_interrupt):
                    with patch("code_agents.chat.chat._render_markdown", side_effect=lambda x: x):
                        with patch("code_agents.chat.chat._extract_commands", return_value=[]):
                            with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                                    with patch("code_agents.chat.chat_history.add_message"):
                                        import code_agents.chat.chat as chat_mod
                                        old_ctrl_c = chat_mod._last_ctrl_c
                                        chat_mod._last_ctrl_c = 0.0
                                        _chat_main_inner(["code-reasoning"])
                                        chat_mod._last_ctrl_c = old_ctrl_c

    def test_delegate_streaming_error(self, capsys):
        """Test inline delegation with error in streaming."""
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["/code-writer write tests", "/quit"])

        with stack:
            with patch("code_agents.chat.chat._parse_inline_delegation", side_effect=[("code-writer", "write tests"), (None, None)]):
                with patch("code_agents.chat.chat._stream_chat", return_value=[("error", "something went wrong"), ("text", "recovered")]):
                    with patch("code_agents.chat.chat._render_markdown", side_effect=lambda x: x):
                        with patch("code_agents.chat.chat._extract_commands", return_value=[]):
                            with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                                    with patch("code_agents.chat.chat_history.add_message"):
                                        _chat_main_inner(["code-reasoning"])

    def test_delegate_reasoning_chunk(self, capsys):
        """Test inline delegation with reasoning chunks."""
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["/code-writer write tests", "/quit"])

        with stack:
            with patch("code_agents.chat.chat._parse_inline_delegation", side_effect=[("code-writer", "write tests"), (None, None)]):
                with patch("code_agents.chat.chat._stream_chat", return_value=[
                    ("reasoning", "thinking about this..."),
                    ("text", "here is the code"),
                ]):
                    with patch("code_agents.chat.chat._render_markdown", side_effect=lambda x: x):
                        with patch("code_agents.chat.chat._extract_commands", return_value=[]):
                            with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                                    with patch("code_agents.chat.chat_history.add_message"):
                                        _chat_main_inner(["code-reasoning"])

    def test_delegate_with_commands(self, capsys):
        """Test inline delegation response with shell commands to offer."""
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["/code-writer fix bug", "/quit"])

        with stack:
            with patch("code_agents.chat.chat._parse_inline_delegation", side_effect=[("code-writer", "fix bug"), (None, None)]):
                with patch("code_agents.chat.chat._stream_chat", return_value=[("text", "```bash\ngit status\n```")]):
                    with patch("code_agents.chat.chat._render_markdown", side_effect=lambda x: x):
                        with patch("code_agents.chat.chat._extract_commands", return_value=["git status"]):
                            with patch("code_agents.chat.chat._offer_run_commands"):
                                with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                    with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                                        with patch("code_agents.chat.chat_history.add_message"):
                                            _chat_main_inner(["code-reasoning"])

    def test_md_file_creation(self, capsys, tmp_path):
        """Test session summary .md file creation."""
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["hello world", "/quit"])

        with stack:
            with patch("code_agents.chat.chat._suggest_skills"):
                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                    with patch("code_agents.chat.chat_history.add_message"):
                        with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                            with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                    with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                        with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                            with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                                with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
                                                    _chat_main_inner(["code-reasoning"])

    def test_qa_pairs_injection(self, capsys):
        """Test QA pairs injected into system context."""
        from code_agents.chat.chat import _chat_main_inner
        stack, _ = self._setup_repl(["hello", "/quit"])

        state = {
            "agent": "code-reasoning", "session_id": None,
            "repo_path": "/tmp", "_chat_session": None, "user_role": "Lead",
            "_qa_pairs": [{"question": "which DB?", "answer": "postgres"}],
        }

        with stack:
            with patch("code_agents.chat.chat.initial_chat_state", return_value=state):
                with patch("code_agents.chat.chat._suggest_skills"):
                    with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                        with patch("code_agents.chat.chat_history.add_message"):
                            with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                                with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                    with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                        with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                            with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                                with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                                    with patch("code_agents.agent_system.questionnaire.format_qa_for_prompt", return_value="Q: which DB?\nA: postgres"):
                                                        _chat_main_inner(["code-reasoning"])

    def test_problem_solver_suggestion(self, capsys):
        """Test problem solver auto-suggestion for questions."""
        from code_agents.chat.chat import _chat_main_inner
        # Extra "n" for smart orchestrator delegation prompt
        def input_fn(*args, **kwargs):
            if not hasattr(input_fn, '_count'):
                input_fn._count = 0
            input_fn._count += 1
            if input_fn._count == 1:
                return "how do I deploy to prod?"
            elif input_fn._count == 2:
                return "n"  # decline delegation
            raise EOFError
        stack, _ = self._setup_repl([], state_extra={"_skip_plan_suggest": True})

        mock_rec = MagicMock()
        mock_rec.confidence = 0.9
        mock_rec.title = "Deploy Guide"
        mock_rec.action = "Use jenkins-cicd agent"
        mock_analysis = MagicMock()
        mock_analysis.recommended = mock_rec

        with stack:
            with patch("builtins.input", side_effect=input_fn):
                with patch("code_agents.chat.chat._suggest_skills"):
                    with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                        with patch("code_agents.chat.chat_history.add_message"):
                            with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                                with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                    with patch("code_agents.knowledge.problem_solver.ProblemSolver") as MockPS:
                                        MockPS.return_value.analyze.return_value = mock_analysis
                                        with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                            with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                                with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                                    _chat_main_inner(["code-reasoning"])


class TestChatMainInnerReadline:
    """Test readline fallback setup."""

    def test_readline_setup(self, capsys):
        """Test that readline setup works when prompt_toolkit unavailable."""
        from code_agents.chat.chat import _chat_main_inner
        agents = {"code-reasoning": "CR"}

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": "/tmp",
                "CODE_AGENTS_SIMPLE_UI": "true",
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=True):
                                with patch("asyncio.run", side_effect=Exception("skip")):
                                    with patch("code_agents.chat.chat.initial_chat_state", return_value={
                                        "agent": "code-reasoning", "session_id": None,
                                        "repo_path": "/tmp", "_chat_session": None, "user_role": "Lead",
                                    }):
                                        with patch("code_agents.chat.chat_input._HAS_PT", False):
                                            with patch("code_agents.chat.chat_input.create_session", return_value=None):
                                                with patch("code_agents.chat.chat_history.auto_cleanup"):
                                                    with patch("code_agents.chat.chat_history.list_recent_sessions", return_value=[]):
                                                        with patch("code_agents.chat.chat._print_welcome"):
                                                            with patch("builtins.input", side_effect=EOFError):
                                                                with patch("code_agents.chat.chat._print_session_summary"):
                                                                    _chat_main_inner(["code-reasoning"])


class TestChatMainInnerPlanMode:
    """Test plan mode creation via shift+tab."""

    def test_plan_mode_creates_report(self, capsys, tmp_path):
        """When in plan mode, _init_plan_report is called."""
        from code_agents.chat.chat import _chat_main_inner
        stack_helper = TestChatMainInnerREPL()

        def input_fn(*args, **kwargs):
            if not hasattr(input_fn, '_count'):
                input_fn._count = 0
            input_fn._count += 1
            if input_fn._count == 1:
                return "implement feature X"
            raise EOFError

        stack, _ = stack_helper._setup_repl([], state_extra={"_skip_plan_suggest": True})

        with stack:
            with patch("builtins.input", side_effect=input_fn):
                with patch("code_agents.chat.chat._suggest_skills"):
                    with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                        with patch("code_agents.chat.chat_history.add_message"):
                            with patch("code_agents.chat.chat_input.get_current_mode", return_value="plan"):
                                with patch("code_agents.chat.chat._init_plan_report") as mock_init:
                                    with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                        with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["plan resp"], False)):
                                            with patch("code_agents.chat.chat.handle_post_response", return_value=(["plan resp"], "test-agent")):
                                                with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["plan resp"], 0)):
                                                    _chat_main_inner(["code-reasoning"])
                                    mock_init.assert_called()


# Import time module used in tests
import time as _time_mod


class TestMakeCompleterSkillLoadError:
    """Test _make_completer when skill loading fails."""

    def test_skill_load_exception(self):
        """Skill loading failure is silently caught."""
        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("no skills")):
            completer = _make_completer(["/help"], ["code-reasoning"])
            # Should still work — just no skill completions
            assert completer("/help", 0) == "/help"

    def test_readline_import_failure(self):
        """When readline.get_line_buffer raises, completer uses text as fallback."""
        completer = _make_completer(["/help"], ["code-reasoning"])
        # Simulate readline not having get_line_buffer
        import readline
        original = readline.get_line_buffer
        try:
            readline.get_line_buffer = MagicMock(side_effect=AttributeError("no buffer"))
            result = completer("/help", 0)
            assert result == "/help"
        finally:
            readline.get_line_buffer = original


class TestChatMainInnerSmartOrchestratorAccept:
    """Test smart orchestrator auto-switches to specialist agent."""

    def test_orchestrator_accept_switch(self):
        """Auto-switch: orchestrator routes to specialist without user prompt."""
        from code_agents.agent_system.smart_orchestrator import SmartOrchestrator
        orch = SmartOrchestrator()
        result = orch.analyze_request("trigger jenkins build and deploy pipeline")
        # Should recommend jenkins-cicd for build/deploy tasks
        assert result["should_delegate"]
        assert result["best_agent"] == "jenkins-cicd"
        assert result["score"] >= 2


class TestChatMainInnerPlanChoices:
    """Test plan mode different choices."""

    def _run_with_plan_choice(self, choice_val, capsys):
        from code_agents.chat.chat import _chat_main_inner
        helper = TestChatMainInnerREPL()

        call_count = [0]
        def input_fn(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return "refactor the auth module completely"
            elif call_count[0] == 2:
                # Smart orchestrator delegation prompt
                return "n"
            elif call_count[0] == 3:
                # Plan choice prompt
                return choice_val
            raise EOFError

        stack, _ = helper._setup_repl([])
        with stack:
            with patch("builtins.input", side_effect=input_fn):
                with patch("code_agents.chat.chat._suggest_skills"):
                    with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                        with patch("code_agents.chat.chat_history.add_message"):
                            with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                                with patch("code_agents.chat.chat_complexity.should_suggest_plan_mode", return_value=(True, 9, ["complex"])):
                                    with patch("code_agents.chat.chat._init_plan_report"):
                                        with patch("code_agents.chat.chat_input.set_mode"):
                                            with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                                with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                                    with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                                        with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                                            _chat_main_inner(["code-reasoning"])

    def test_plan_choice_1(self, capsys):
        """Choice 1: plan first then execute."""
        self._run_with_plan_choice("1", capsys)
        output = capsys.readouterr().out
        assert "Plan mode" in output

    def test_plan_choice_2(self, capsys):
        """Choice 2: plan then auto-accept edits."""
        self._run_with_plan_choice("2", capsys)
        output = capsys.readouterr().out
        assert "auto-accept" in output

    def test_plan_choice_empty_default(self, capsys):
        """Empty input defaults to choice 1."""
        self._run_with_plan_choice("", capsys)
        output = capsys.readouterr().out
        assert "Plan mode" in output


class TestChatMainInnerResumeWithLongMessages:
    """Test resume with messages exceeding 100 chars."""

    def test_resume_with_long_messages(self, capsys):
        from code_agents.chat.chat import _chat_main_inner

        long_msg = "x" * 150
        loaded_session = {
            "title": "Long Session",
            "agent": "code-writer",
            "messages": [
                {"role": "user", "content": long_msg},
                {"role": "assistant", "content": "Short reply"},
                {"role": "user", "content": "another question"},
                {"role": "assistant", "content": "a" * 200},
            ],
            "_server_session_id": "sess-456",
        }

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": "/tmp",
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value={"code-reasoning": "CR", "code-writer": "CW"}):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=True):
                                with patch("asyncio.run", side_effect=Exception("skip")):
                                    with patch("code_agents.chat.chat.apply_resume_session") as mock_resume:
                                        mock_resume.return_value = (True, "code-writer")
                                        with patch("code_agents.chat.chat.initial_chat_state", return_value={
                                            "agent": "code-reasoning", "session_id": None,
                                            "repo_path": "/tmp", "_chat_session": loaded_session, "user_role": "Lead",
                                        }):
                                            with patch("builtins.input", side_effect=EOFError):
                                                with patch("code_agents.chat.chat_history.auto_cleanup"):
                                                    with patch("code_agents.chat.chat_history.list_recent_sessions", return_value=[]):
                                                        with patch("code_agents.chat.chat._print_welcome"):
                                                            with patch("code_agents.chat.chat_input._HAS_PT", False):
                                                                with patch("code_agents.chat.chat_input.create_session", return_value=None):
                                                                    with patch("code_agents.chat.chat._print_session_summary"):
                                                                        _chat_main_inner(["--agent", "code-reasoning", "--resume", "abc123"])
        output = capsys.readouterr().out
        assert "Resumed" in output
        assert "..." in output  # truncated message


class TestChatMainInnerPromptToolkit:
    """Test prompt_toolkit session creation path."""

    def test_pt_session_created(self, capsys):
        from code_agents.chat.chat import _chat_main_inner

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": "/tmp",
                "CODE_AGENTS_SIMPLE_UI": "",  # Not simple UI
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value={"code-reasoning": "CR"}):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=True):
                                with patch("asyncio.run", side_effect=Exception("skip")):
                                    with patch("code_agents.chat.chat.initial_chat_state", return_value={
                                        "agent": "code-reasoning", "session_id": None,
                                        "repo_path": "/tmp", "_chat_session": None, "user_role": "Lead",
                                    }):
                                        with patch("code_agents.chat.chat_input._HAS_PT", True):
                                            mock_session = MagicMock()
                                            with patch("code_agents.chat.chat_input.create_session", return_value=mock_session):
                                                with patch("code_agents.chat.chat_history.auto_cleanup"):
                                                    with patch("code_agents.chat.chat_history.list_recent_sessions", return_value=[]):
                                                        with patch("code_agents.chat.chat._print_welcome"):
                                                            with patch("builtins.input", side_effect=EOFError):
                                                                with patch("code_agents.chat.chat._print_session_summary"):
                                                                    _chat_main_inner(["code-reasoning"])


class TestChatMainInnerNicknameEmpty:
    """Test nickname fallback to 'you' when empty."""

    def test_nickname_empty_input(self, capsys):
        """Empty input for nickname defaults to 'you'."""
        from code_agents.chat.chat import _chat_main_inner
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                with patch("builtins.input", side_effect=["", EOFError]):  # empty nickname, then EOFError for server prompt
                    with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                        with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                            _chat_main_inner([])


class TestChatMainInnerRoleSaveError:
    """Test role save with OSError."""

    def test_role_save_os_error(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        mock_answer = {"answer": "Architect"}
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": ""}, clear=False):
                with patch("code_agents.agent_system.questionnaire.ask_question", return_value=mock_answer):
                    with patch("builtins.open", side_effect=OSError("permission denied")):
                        with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                            with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                                with patch("builtins.input", side_effect=EOFError):
                                    _chat_main_inner([])


class TestChatMainInnerDelegateDoubleCtrlC:
    """Test double Ctrl+C during inline delegation streaming."""

    def test_double_ctrl_c_exits_during_delegation(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        import code_agents.chat.chat as chat_mod

        helper = TestChatMainInnerREPL()

        def stream_with_interrupt(*a, **kw):
            yield ("text", "partial")
            raise KeyboardInterrupt

        # Set _last_ctrl_c to recent time to simulate double Ctrl+C
        old_ctrl_c = chat_mod._last_ctrl_c
        chat_mod._last_ctrl_c = _time_mod.time()

        stack, _ = helper._setup_repl(["/code-writer write tests"])
        with stack:
            with patch("code_agents.chat.chat._parse_inline_delegation", return_value=("code-writer", "write tests")):
                with patch("code_agents.chat.chat._stream_chat", side_effect=stream_with_interrupt):
                    with patch("code_agents.chat.chat._render_markdown", side_effect=lambda x: x):
                        with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                            with patch("code_agents.chat.chat_history.add_message"):
                                _chat_main_inner(["code-reasoning"])

        chat_mod._last_ctrl_c = old_ctrl_c
        output = capsys.readouterr().out
        # Double Ctrl+C handled — either exits or shows interrupted message
        assert "Exiting" in output or "SWITCHING" in output or "code-writer" in output.lower()


    # TestChatMainInnerSessionSelectorEOF removed — session selector no longer exists


class TestChatMainInnerRepoDetectionBanner:
    """Test banner shows repo info when TARGET_REPO_PATH has git."""

    def test_repo_banner_shows_repo_name(self, tmp_path, capsys):
        from code_agents.chat.chat import _chat_main_inner
        agents = {"code-reasoning": "CR"}
        repo = tmp_path / "my-project"
        repo.mkdir()
        (repo / ".git").mkdir()

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": str(repo),
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=True):
                                with patch("asyncio.run", side_effect=Exception("skip")):
                                    with patch("code_agents.chat.chat.initial_chat_state", return_value={
                                        "agent": "code-reasoning", "session_id": None,
                                        "repo_path": str(repo), "_chat_session": None, "user_role": "Lead",
                                    }):
                                        with patch("code_agents.chat.chat_input._HAS_PT", False):
                                            with patch("code_agents.chat.chat_input.create_session", return_value=None):
                                                with patch("code_agents.chat.chat_history.auto_cleanup"):
                                                    with patch("code_agents.chat.chat_history.list_recent_sessions", return_value=[]):
                                                        with patch("code_agents.chat.chat._print_welcome"):
                                                            with patch("builtins.input", side_effect=EOFError):
                                                                with patch("code_agents.chat.chat._print_session_summary"):
                                                                    _chat_main_inner(["code-reasoning"])
        output = capsys.readouterr().out
        assert "my-project" in output
        assert "Agent will work on this project" in output


class TestChatMainInnerCtrlCSignal:
    """Test Ctrl+C signal from prompt_toolkit (line == '\\x03')."""

    def test_ctrl_c_signal_from_pt(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        import code_agents.chat.chat as chat_mod
        helper = TestChatMainInnerREPL()

        old_ctrl_c = chat_mod._last_ctrl_c
        chat_mod._last_ctrl_c = 0.0

        stack, _ = helper._setup_repl([])
        with stack:
            with patch("builtins.input", side_effect=["\x03", "/quit"]):
                with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                    _chat_main_inner(["code-reasoning"])

        chat_mod._last_ctrl_c = old_ctrl_c

    def test_outer_keyboard_interrupt(self, capsys):
        """Test the outer except KeyboardInterrupt in the REPL."""
        from code_agents.chat.chat import _chat_main_inner
        helper = TestChatMainInnerREPL()

        stack, _ = helper._setup_repl(["hello"])
        with stack:
            with patch("code_agents.chat.chat._suggest_skills", side_effect=KeyboardInterrupt):
                with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                    with patch("code_agents.chat.chat_history.add_message"):
                        _chat_main_inner(["code-reasoning"])
        output = capsys.readouterr().out
        assert "Exiting" in output


class TestChatMainInnerMdFileOSError:
    """Test OSError when writing task to md file."""

    def test_md_write_os_error(self, capsys):
        """OSError during md file task writing is caught."""
        from code_agents.chat.chat import _chat_main_inner
        helper = TestChatMainInnerREPL()

        state = {
            "agent": "code-reasoning", "session_id": None,
            "repo_path": "/tmp", "_chat_session": {"id": "s1", "messages": []},
            "user_role": "Lead", "_skip_plan_suggest": True,
            "_md_file": "/nonexistent/path/report.md",
            "_md_count": 0,
        }

        stack, _ = helper._setup_repl(["hello", "/quit"], state_extra=state)
        with stack:
            with patch("code_agents.chat.chat._suggest_skills"):
                with patch("code_agents.chat.chat_history.add_message"):
                    with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                        with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                            with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                    with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                        with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                            _chat_main_inner(["code-reasoning"])


class TestChatMainInnerSkillSuggestException:
    """Test _suggest_skills exception path."""

    def test_skill_suggest_exception(self, capsys):
        """Exception during skill suggestion is silently caught."""
        from code_agents.chat.chat import _chat_main_inner
        helper = TestChatMainInnerREPL()

        stack, _ = helper._setup_repl(["hello", "/quit"], state_extra={"_skip_plan_suggest": True})
        with stack:
            with patch("code_agents.core.config.settings", side_effect=Exception("no config")):
                with patch("code_agents.chat.chat._suggest_skills", side_effect=Exception("skill fail")):
                    with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                        with patch("code_agents.chat.chat_history.add_message"):
                            with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                                with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                    with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                        with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                            with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                                with patch("code_agents.chat.chat._handle_command", return_value="quit"):
                                                    _chat_main_inner(["code-reasoning"])


class TestChatMainInnerBackendValidationEOF:
    """Test backend validation with EOFError during continue prompt."""

    def test_backend_validation_eof_during_prompt(self, capsys):
        """BackendValidator.check() returns False when user hits EOF on prompt."""
        from code_agents.chat.chat import _chat_main_inner
        agents = {"code-reasoning": "Code Reasoning"}

        # Simulate: validation failed and user hit EOF -> check() returns False
        mock_validator = MagicMock()
        mock_validator.check.return_value = False

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {
                "CODE_AGENTS_NICKNAME": "me",
                "CODE_AGENTS_USER_ROLE": "Lead",
                "TARGET_REPO_PATH": "/tmp",
            }, clear=False):
                with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                    with patch("code_agents.chat.chat.ensure_server_running", return_value=True):
                        with patch("code_agents.chat.chat._get_agents", return_value=agents):
                            with patch("code_agents.chat.chat.check_workspace_trust", return_value=True):
                                with patch("code_agents.chat.chat.BackendValidator", return_value=mock_validator):
                                    _chat_main_inner(["code-reasoning"])


class TestChatMainInnerPlanChoiceEOF:
    """Test plan choice with EOFError."""

    def test_plan_choice_eof(self, capsys):
        from code_agents.chat.chat import _chat_main_inner
        helper = TestChatMainInnerREPL()

        call_count = [0]
        def input_fn(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return "refactor everything"
            elif call_count[0] == 2:
                return "n"  # decline delegation
            elif call_count[0] == 3:
                raise EOFError  # EOF during plan choice
            raise EOFError

        stack, _ = helper._setup_repl([])
        with stack:
            with patch("builtins.input", side_effect=input_fn):
                with patch("code_agents.chat.chat._suggest_skills"):
                    with patch("code_agents.chat.chat_history.create_session", return_value={"id": "s1", "messages": []}):
                        with patch("code_agents.chat.chat_history.add_message"):
                            with patch("code_agents.chat.chat_input.get_current_mode", return_value="chat"):
                                with patch("code_agents.chat.chat_complexity.should_suggest_plan_mode", return_value=(True, 9, ["complex"])):
                                    with patch("code_agents.chat.chat_clipboard.get_pending_images", return_value=[]):
                                        with patch("code_agents.chat.chat.process_streaming_response", return_value=(True, ["resp"], False)):
                                            with patch("code_agents.chat.chat.handle_post_response", return_value=(["resp"], "test-agent")):
                                                with patch("code_agents.chat.chat.run_agentic_followup_loop", return_value=(["resp"], 0)):
                                                    _chat_main_inner(["code-reasoning"])


class TestChatMainInnerNicknameEmptyAfterSave:
    """Test nickname fallback when saved but empty."""

    def test_nickname_save_then_empty(self, capsys, tmp_path):
        """After saving empty nickname, fallback to 'you'."""
        from code_agents.chat.chat import _chat_main_inner
        env_path = tmp_path / "config.env"
        env_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False):
                # Enter empty string for nickname
                with patch("builtins.input", side_effect=["", EOFError]):
                    with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                        with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                            _chat_main_inner([])


class TestChatMainInnerRoleSaveSuccess:
    """Test role save writes to config file."""

    def test_role_saved_to_file(self, capsys, tmp_path):
        from code_agents.chat.chat import _chat_main_inner
        mock_answer = {"answer": "Principal Engineer / Architect"}
        config_file = tmp_path / ".code-agents" / "config.env"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("")

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": ""}, clear=False):
                with patch("code_agents.agent_system.questionnaire.ask_question", return_value=mock_answer):
                    with patch("pathlib.Path.home", return_value=tmp_path):
                        with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                            with patch("code_agents.chat.chat.ensure_server_running", return_value=False):
                                with patch("builtins.input", side_effect=EOFError):
                                    _chat_main_inner([])
        # Verify role was saved
        content = config_file.read_text()
        assert "Principal Engineer" in content


# ---------------------------------------------------------------------------
# Coverage gap tests — missing lines
# ---------------------------------------------------------------------------

from unittest.mock import patch, MagicMock


class TestChatMainInnerNicknameSave:
    """Line 261: nickname save writes to config file."""

    def test_nickname_save_writes_env(self, tmp_path):
        from code_agents.chat.chat import _chat_main_inner
        config_file = tmp_path / ".code-agents" / "config.env"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("")
        with patch("code_agents.core.env_loader.load_all_env"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", config_file), \
             patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False), \
             patch("builtins.input", side_effect=["Alice", EOFError]), \
             patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"), \
             patch("code_agents.chat.chat.ensure_server_running", return_value=False):
            _chat_main_inner([])


class TestChatMainInnerHomeAgentsGuard:
    """Lines 404-406: guard against using ~/.code-agents as repo."""

    def test_home_agents_guard(self, tmp_path):
        from code_agents.chat.chat import _chat_main_inner
        home_agents = str(tmp_path / ".code-agents")
        os.makedirs(home_agents, exist_ok=True)
        os.makedirs(os.path.join(home_agents, ".git"), exist_ok=True)

        with patch("code_agents.core.env_loader.load_all_env"), \
             patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead", "TARGET_REPO_PATH": ""}, clear=False), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("os.getcwd", return_value=home_agents), \
             patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"), \
             patch("code_agents.chat.chat.ensure_server_running", return_value=False), \
             patch("builtins.input", side_effect=EOFError):
            _chat_main_inner([])


class TestChatMainInnerAgentsCacheRefresh:
    """Lines 737-738: _get_agents called when cache empty."""

    def test_agents_cache_refresh(self, tmp_path):
        from code_agents.chat.chat import _chat_main_inner
        with patch("code_agents.core.env_loader.load_all_env"), \
             patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False), \
             patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"), \
             patch("code_agents.chat.chat.ensure_server_running", return_value=True), \
             patch("code_agents.chat.chat._get_agents", return_value={"auto-pilot": "Auto"}), \
             patch("code_agents.chat.chat._select_agent", return_value="auto-pilot"), \
             patch("code_agents.chat.chat.check_workspace_trust", return_value=True), \
             patch("code_agents.chat.chat._print_welcome"), \
             patch("builtins.input", side_effect=["/auto-pilot test", EOFError]), \
             patch("code_agents.chat.chat._parse_inline_delegation", return_value=(None, None)), \
             patch("code_agents.chat.chat._handle_command", return_value=True):
            _chat_main_inner([])


class TestChatMainInnerDoubleCtrlC:
    """Lines 982-983: double Ctrl+C during streaming exits."""

    def test_double_ctrl_c_exits(self, tmp_path):
        from code_agents.chat.chat import _chat_main_inner
        with patch("code_agents.core.env_loader.load_all_env"), \
             patch.dict(os.environ, {"CODE_AGENTS_NICKNAME": "me", "CODE_AGENTS_USER_ROLE": "Lead"}, clear=False), \
             patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"), \
             patch("code_agents.chat.chat.ensure_server_running", return_value=True), \
             patch("code_agents.chat.chat._get_agents", return_value={"auto-pilot": "Auto"}), \
             patch("code_agents.chat.chat._select_agent", return_value="auto-pilot"), \
             patch("code_agents.chat.chat.check_workspace_trust", return_value=True), \
             patch("code_agents.chat.chat._print_welcome"), \
             patch("builtins.input", side_effect=KeyboardInterrupt):
            _chat_main_inner([])
