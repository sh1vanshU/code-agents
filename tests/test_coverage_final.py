"""
Targeted coverage tests — covers specific uncovered line ranges across multiple modules.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. env_loader.py — _safe_load parse error branches (lines 159-179)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnvLoaderSafeLoadErrors:
    """Test _safe_load parse warning handling inside load_all_env."""

    def test_safe_load_parse_warning_with_line_number(self, tmp_path, monkeypatch):
        """When dotenv emits a 'could not parse' warning with line number, it should log details."""
        env_file = tmp_path / "config.env"
        env_file.write_text("GOOD=ok\nBAD LINE HERE\nANOTHER=ok\n")

        monkeypatch.setattr("code_agents.core.env_loader.GLOBAL_ENV_PATH", env_file)
        monkeypatch.setattr("code_agents.core.env_loader.REPOS_DIR", tmp_path / "repos")

        def fake_load_dotenv(filepath, override=False):
            import sys
            sys.stderr.write("Python-dotenv could not parse statement starting at line 2\n")

        with patch("dotenv.load_dotenv", fake_load_dotenv):
            from code_agents.core.env_loader import load_all_env
            monkeypatch.delenv("TARGET_REPO_PATH", raising=False)
            load_all_env(str(tmp_path))

    def test_safe_load_parse_warning_no_line_number(self, tmp_path, monkeypatch):
        """When parse warning has no line number, falls back to simple warning."""
        env_file = tmp_path / "config.env"
        env_file.write_text("KEY=val\n")

        monkeypatch.setattr("code_agents.core.env_loader.GLOBAL_ENV_PATH", env_file)
        monkeypatch.setattr("code_agents.core.env_loader.REPOS_DIR", tmp_path / "repos")

        def fake_load_dotenv(filepath, override=False):
            import sys
            sys.stderr.write("could not parse some unknown issue\n")

        with patch("dotenv.load_dotenv", fake_load_dotenv):
            from code_agents.core.env_loader import load_all_env
            monkeypatch.delenv("TARGET_REPO_PATH", raising=False)
            load_all_env(str(tmp_path))

    def test_safe_load_parse_warning_line_out_of_range(self, tmp_path, monkeypatch):
        """When line number exceeds file length, prints simpler warning."""
        env_file = tmp_path / "config.env"
        env_file.write_text("ONLY=one\n")

        monkeypatch.setattr("code_agents.core.env_loader.GLOBAL_ENV_PATH", env_file)
        monkeypatch.setattr("code_agents.core.env_loader.REPOS_DIR", tmp_path / "repos")

        def fake_load_dotenv(filepath, override=False):
            import sys
            sys.stderr.write("could not parse statement starting at line 999\n")

        with patch("dotenv.load_dotenv", fake_load_dotenv):
            from code_agents.core.env_loader import load_all_env
            monkeypatch.delenv("TARGET_REPO_PATH", raising=False)
            load_all_env(str(tmp_path))

    def test_safe_load_parse_warning_exception_in_handler(self, tmp_path, monkeypatch):
        """When the error-handling code itself raises, falls back to simple print."""
        env_file = tmp_path / "config.env"
        env_file.write_text("KEY=val\n")

        monkeypatch.setattr("code_agents.core.env_loader.GLOBAL_ENV_PATH", env_file)
        monkeypatch.setattr("code_agents.core.env_loader.REPOS_DIR", tmp_path / "repos")

        def fake_load_dotenv(filepath, override=False):
            import sys
            sys.stderr.write("could not parse statement starting at line 1\n")

        with patch("dotenv.load_dotenv", fake_load_dotenv):
            # Make filepath.read_text() raise to trigger the except block
            with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
                from code_agents.core.env_loader import load_all_env
                monkeypatch.delenv("TARGET_REPO_PATH", raising=False)
                load_all_env(str(tmp_path))


# ═══════════════════════════════════════════════════════════════════════════════
# 2. knowledge_base.py — KnowledgeBase init + _load_index + _save_index (lines 28-52)
# ═══════════════════════════════════════════════════════════════════════════════

class TestKnowledgeBaseInit:
    """Test KnowledgeBase initialization, loading, and saving."""

    def test_init_no_index_file(self, monkeypatch):
        """When no KB index file exists, entries are empty."""
        monkeypatch.setattr("code_agents.knowledge.knowledge_base.KB_INDEX_PATH", Path("/nonexistent/kb.json"))
        from code_agents.knowledge.knowledge_base import KnowledgeBase
        kb = KnowledgeBase(cwd="/tmp")
        assert kb.entries == []

    def test_init_loads_existing_index(self, tmp_path, monkeypatch):
        """When index file exists with entries, they are loaded."""
        index_file = tmp_path / "kb_index.json"
        data = {
            "entries": [
                {"title": "Test Entry", "source": "manual", "file": "", "content": "hello",
                 "tags": ["test"], "timestamp": "2025-01-01", "relevance": 0.5},
            ],
            "updated": "2025-01-01T00:00:00",
        }
        index_file.write_text(json.dumps(data))
        monkeypatch.setattr("code_agents.knowledge.knowledge_base.KB_INDEX_PATH", index_file)

        from code_agents.knowledge.knowledge_base import KnowledgeBase
        kb = KnowledgeBase(cwd="/tmp")
        assert len(kb.entries) == 1
        assert kb.entries[0].title == "Test Entry"

    def test_init_corrupt_json_falls_back_empty(self, tmp_path, monkeypatch):
        """When index file has invalid JSON, entries default to empty."""
        index_file = tmp_path / "kb_index.json"
        index_file.write_text("not valid json{{{")
        monkeypatch.setattr("code_agents.knowledge.knowledge_base.KB_INDEX_PATH", index_file)

        from code_agents.knowledge.knowledge_base import KnowledgeBase
        kb = KnowledgeBase(cwd="/tmp")
        assert kb.entries == []

    def test_save_index_creates_file(self, tmp_path, monkeypatch):
        """_save_index writes entries to JSON file."""
        index_file = tmp_path / "sub" / "kb_index.json"
        monkeypatch.setattr("code_agents.knowledge.knowledge_base.KB_INDEX_PATH", index_file)

        from code_agents.knowledge.knowledge_base import KnowledgeBase, KBEntry
        kb = KnowledgeBase(cwd="/tmp")
        kb.entries = [KBEntry(title="Saved", source="manual", content="data", tags=["a"])]
        kb._save_index()

        assert index_file.exists()
        saved = json.loads(index_file.read_text())
        assert len(saved["entries"]) == 1
        assert saved["entries"][0]["title"] == "Saved"
        assert "updated" in saved


# ═══════════════════════════════════════════════════════════════════════════════
# 3. setup/setup_env.py — _write_env_to_path merge/backup/sections (lines 68-133)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSetupEnvWrite:
    """Test setup_env _write_env_to_path branching."""

    def test_write_env_new_file(self, tmp_path):
        """Writing to a non-existent path creates the file with sections."""
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / "test.env"
        env_vars = {"CURSOR_API_KEY": "abc123", "HOST": "localhost", "CUSTOM_VAR": "custom"}
        _write_env_to_path(env_path, env_vars, "Test Config")
        assert env_path.exists()
        content = env_path.read_text()
        assert "CURSOR_API_KEY=abc123" in content
        assert "HOST=localhost" in content
        assert "CUSTOM_VAR=custom" in content
        assert "# Core" in content
        assert "# Other" in content

    def test_write_env_with_special_chars(self, tmp_path):
        """Values with spaces, dollar signs, or double quotes are properly quoted."""
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / "test.env"
        env_vars = {
            "VAR_SPACES": "hello world",
            "VAR_DOLLAR": "cost=$100",
            "VAR_DQUOTE": 'say "hi"',
            "VAR_PAREN": "cmd(arg)",
        }
        _write_env_to_path(env_path, env_vars, "Special")
        content = env_path.read_text()
        assert 'VAR_SPACES="hello world"' in content
        assert 'VAR_DOLLAR="cost=$100"' in content
        assert "VAR_DQUOTE='say \"hi\"'" in content
        assert 'VAR_PAREN="cmd(arg)"' in content

    def test_write_env_auto_merge_preserves_existing(self, tmp_path):
        """Auto-merge preserves existing keys and adds new ones."""
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / "test.env"
        env_path.write_text("EXISTING=keep\nOLD=untouched\n")

        env_vars = {"NEW_KEY": "new_val"}
        _write_env_to_path(env_path, env_vars, "Merge Test")
        content = env_path.read_text()
        assert "EXISTING=keep" in content
        assert "OLD=untouched" in content
        assert "NEW_KEY=new_val" in content

    def test_write_env_auto_merge_updates_changed(self, tmp_path):
        """Auto-merge updates keys with new values."""
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / "test.env"
        env_path.write_text("EXISTING=old_val\n")

        env_vars = {"EXISTING": "new_val", "ADDED": "fresh"}
        _write_env_to_path(env_path, env_vars, "Update Test")
        content = env_path.read_text()
        assert "EXISTING=new_val" in content
        assert "ADDED=fresh" in content
        assert "old_val" not in content


# ═══════════════════════════════════════════════════════════════════════════════
# 4. routers/mcp.py — get_server_tools, invoke_tool, start/stop (lines 82-161)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMCPRouter:
    """Test MCP router handler functions."""

    def _make_server(self, name="test-server", is_stdio=True):
        mock = MagicMock()
        mock.name = name
        mock.is_stdio = is_stdio
        mock.command = "echo hello" if is_stdio else ""
        mock.url = "" if is_stdio else "http://localhost:9090"
        mock.agents = ["code-writer"]
        mock._process = None
        return mock

    def test_list_servers(self):
        from code_agents.routers.mcp import list_servers, _active_servers
        server = self._make_server()
        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"test-server": server}):
            with patch("code_agents.routers.mcp._repo_path", return_value="/tmp"):
                result = asyncio.run(list_servers())
        assert len(result) == 1
        assert result[0].name == "test-server"

    def test_get_server_tools_not_found(self):
        from code_agents.routers.mcp import get_server_tools
        with patch("code_agents.routers.mcp.load_mcp_config", return_value={}):
            with patch("code_agents.routers.mcp._repo_path", return_value="/tmp"):
                from fastapi import HTTPException
                with pytest.raises(HTTPException) as exc:
                    asyncio.run(get_server_tools("missing"))
                assert exc.value.status_code == 404

    def test_get_server_tools_auto_start_stdio(self):
        from code_agents.routers.mcp import get_server_tools, _active_servers
        _active_servers.clear()
        server = self._make_server()
        mock_tool = MagicMock()
        mock_tool.name = "tool1"
        mock_tool.description = "A tool"
        mock_tool.input_schema = {}
        mock_tool.server_name = "test-server"

        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"test-server": server}):
            with patch("code_agents.routers.mcp._repo_path", return_value="/tmp"):
                with patch("code_agents.routers.mcp.start_stdio_server", new_callable=AsyncMock):
                    with patch("code_agents.routers.mcp.list_tools", new_callable=AsyncMock, return_value=[mock_tool]):
                        result = asyncio.run(get_server_tools("test-server"))
        assert len(result) == 1
        assert result[0].name == "tool1"
        _active_servers.clear()

    def test_invoke_tool_not_configured(self):
        from code_agents.routers.mcp import invoke_tool, ToolCallRequest, _active_servers
        _active_servers.clear()
        with patch("code_agents.routers.mcp.load_mcp_config", return_value={}):
            with patch("code_agents.routers.mcp._repo_path", return_value="/tmp"):
                from fastapi import HTTPException
                with pytest.raises(HTTPException) as exc:
                    asyncio.run(invoke_tool("missing", "tool", ToolCallRequest(arguments={})))
                assert exc.value.status_code == 404
        _active_servers.clear()

    def test_invoke_tool_starts_stdio_server(self):
        from code_agents.routers.mcp import invoke_tool, ToolCallRequest, _active_servers
        _active_servers.clear()
        server = self._make_server()

        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"test-server": server}):
            with patch("code_agents.routers.mcp._repo_path", return_value="/tmp"):
                with patch("code_agents.routers.mcp.start_stdio_server", new_callable=AsyncMock):
                    with patch("code_agents.routers.mcp.call_tool", new_callable=AsyncMock, return_value={"ok": True}):
                        result = asyncio.run(invoke_tool("test-server", "mytool", ToolCallRequest(arguments={"a": 1})))
        assert result["result"]["ok"] is True
        _active_servers.clear()

    def test_invoke_tool_sse_server(self):
        from code_agents.routers.mcp import invoke_tool, ToolCallRequest, _active_servers
        _active_servers.clear()
        server = self._make_server(is_stdio=False)

        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"test-server": server}):
            with patch("code_agents.routers.mcp._repo_path", return_value="/tmp"):
                with patch("code_agents.routers.mcp.call_tool", new_callable=AsyncMock, return_value="result"):
                    result = asyncio.run(invoke_tool("test-server", "mytool", ToolCallRequest(arguments={})))
        assert result["result"] == "result"
        _active_servers.clear()

    def test_invoke_tool_null_result(self):
        from code_agents.routers.mcp import invoke_tool, ToolCallRequest, _active_servers
        _active_servers.clear()
        server = self._make_server()
        _active_servers["test-server"] = server

        with patch("code_agents.routers.mcp.call_tool", new_callable=AsyncMock, return_value=None):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                asyncio.run(invoke_tool("test-server", "tool", ToolCallRequest(arguments={})))
            assert exc.value.status_code == 502
        _active_servers.clear()

    def test_start_server_not_configured(self):
        from code_agents.routers.mcp import start_server
        with patch("code_agents.routers.mcp.load_mcp_config", return_value={}):
            with patch("code_agents.routers.mcp._repo_path", return_value="/tmp"):
                from fastapi import HTTPException
                with pytest.raises(HTTPException):
                    asyncio.run(start_server("missing"))

    def test_start_server_sse_noop(self):
        from code_agents.routers.mcp import start_server
        server = self._make_server(is_stdio=False)
        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"sse": server}):
            with patch("code_agents.routers.mcp._repo_path", return_value="/tmp"):
                result = asyncio.run(start_server("sse"))
        assert result["status"] == "ok"
        assert "does not need" in result["message"]

    def test_start_server_already_running(self):
        from code_agents.routers.mcp import start_server, _active_servers
        server = self._make_server()
        server._process = MagicMock()
        _active_servers["test-server"] = server
        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"test-server": server}):
            with patch("code_agents.routers.mcp._repo_path", return_value="/tmp"):
                result = asyncio.run(start_server("test-server"))
        assert "already running" in result["message"]
        _active_servers.clear()

    def test_start_server_success(self):
        from code_agents.routers.mcp import start_server, _active_servers
        _active_servers.clear()
        server = self._make_server()
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"test-server": server}):
            with patch("code_agents.routers.mcp._repo_path", return_value="/tmp"):
                with patch("code_agents.routers.mcp.start_stdio_server", new_callable=AsyncMock, return_value=mock_proc):
                    result = asyncio.run(start_server("test-server"))
        assert "12345" in result["message"]
        _active_servers.clear()

    def test_stop_server_not_running(self):
        from code_agents.routers.mcp import stop_server_endpoint, _active_servers
        _active_servers.clear()
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            asyncio.run(stop_server_endpoint("missing"))

    def test_stop_server_success(self):
        from code_agents.routers.mcp import stop_server_endpoint, _active_servers
        server = self._make_server()
        _active_servers["test-server"] = server
        with patch("code_agents.routers.mcp.stop_server") as mock_stop:
            result = asyncio.run(stop_server_endpoint("test-server"))
        assert result["status"] == "ok"
        mock_stop.assert_called_once_with(server)
        _active_servers.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. routers/jenkins.py — _get_client, trigger_build, build_and_wait (lines 20-170)
# ═══════════════════════════════════════════════════════════════════════════════

class TestJenkinsRouter:
    """Test Jenkins router handler functions."""

    def test_get_client_no_url(self, monkeypatch):
        monkeypatch.delenv("JENKINS_URL", raising=False)
        from code_agents.routers.jenkins import _get_client
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _get_client()
        assert exc.value.status_code == 503

    def test_get_client_no_credentials(self, monkeypatch):
        monkeypatch.setenv("JENKINS_URL", "http://jenkins.test")
        monkeypatch.delenv("JENKINS_USERNAME", raising=False)
        monkeypatch.delenv("JENKINS_API_TOKEN", raising=False)
        from code_agents.routers.jenkins import _get_client
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _get_client()
        assert exc.value.status_code == 503

    def test_get_client_success(self, monkeypatch):
        monkeypatch.setenv("JENKINS_URL", "http://jenkins.test")
        monkeypatch.setenv("JENKINS_USERNAME", "admin")
        monkeypatch.setenv("JENKINS_API_TOKEN", "token123")
        from code_agents.routers.jenkins import _get_client
        client = _get_client()
        assert client.base_url == "http://jenkins.test"

    def test_get_job_parameters_success(self, monkeypatch):
        monkeypatch.setenv("JENKINS_URL", "http://jenkins.test")
        monkeypatch.setenv("JENKINS_USERNAME", "admin")
        monkeypatch.setenv("JENKINS_API_TOKEN", "tok")
        from code_agents.routers.jenkins import get_job_parameters
        with patch("code_agents.routers.jenkins._get_client") as mc:
            mc.return_value.get_job_parameters = AsyncMock(return_value=[{"name": "branch"}])
            result = asyncio.run(get_job_parameters("job/path"))
        assert result["job_name"] == "job/path"
        assert len(result["parameters"]) == 1

    def test_get_job_parameters_error(self):
        from code_agents.routers.jenkins import get_job_parameters
        from code_agents.cicd.jenkins_client import JenkinsError
        with patch("code_agents.routers.jenkins._get_client") as mc:
            mc.return_value.get_job_parameters = AsyncMock(side_effect=JenkinsError("fail", 500))
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                asyncio.run(get_job_parameters("job/path"))
            assert exc.value.status_code == 502

    def test_trigger_build_with_branch(self):
        from code_agents.routers.jenkins import trigger_build, TriggerBuildRequest
        req = TriggerBuildRequest(job_name="my-job", branch="develop")
        with patch("code_agents.routers.jenkins._get_client") as mc:
            mc.return_value.trigger_build = AsyncMock(return_value={"queue_id": 42})
            mc.return_value.get_build_from_queue = AsyncMock(return_value=101)
            result = asyncio.run(trigger_build(req))
        assert result["queue_id"] == 42
        assert result["build_number"] == 101

    def test_trigger_build_error(self):
        from code_agents.routers.jenkins import trigger_build, TriggerBuildRequest
        from code_agents.cicd.jenkins_client import JenkinsError
        req = TriggerBuildRequest(job_name="my-job")
        with patch("code_agents.routers.jenkins._get_client") as mc:
            mc.return_value.trigger_build = AsyncMock(side_effect=JenkinsError("bad request", 400))
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                asyncio.run(trigger_build(req))
            assert exc.value.status_code == 422

    def test_build_and_wait(self):
        from code_agents.routers.jenkins import trigger_build_and_wait, TriggerBuildRequest
        from starlette.responses import StreamingResponse
        req = TriggerBuildRequest(job_name="job", branch="main")
        with patch("code_agents.routers.jenkins._get_client") as mc:
            mc.return_value.trigger_and_wait = AsyncMock(return_value={
                "number": 5, "result": "SUCCESS", "build_version": "1.2.3"
            })
            result = asyncio.run(trigger_build_and_wait(req))
        # trigger_build_and_wait returns a StreamingResponse (newline-delimited JSON)
        assert isinstance(result, StreamingResponse)

    def test_build_and_wait_error(self):
        from code_agents.routers.jenkins import trigger_build_and_wait, TriggerBuildRequest
        from code_agents.cicd.jenkins_client import JenkinsError
        req = TriggerBuildRequest(job_name="job")
        with patch("code_agents.routers.jenkins._get_client") as mc:
            mc.return_value.trigger_and_wait = AsyncMock(side_effect=JenkinsError("timeout", 504))
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                asyncio.run(trigger_build_and_wait(req))
            assert exc.value.status_code == 502


# ═══════════════════════════════════════════════════════════════════════════════
# 6. routers/git_ops.py — current_branch, diff, log, push, status, fetch,
#    checkout, stash (lines 90-194)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGitOpsRouter:
    """Test git_ops router handler functions."""

    def test_resolve_repo_path_invalid(self, monkeypatch):
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)
        from code_agents.routers.git_ops import _resolve_repo_path
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _resolve_repo_path("/nonexistent/path/abcxyz")
        assert exc.value.status_code == 422

    def test_current_branch_success(self):
        from code_agents.routers.git_ops import current_branch
        mock_client = MagicMock()
        mock_client.current_branch = AsyncMock(return_value="main")
        mock_client.repo_path = "/tmp/repo"
        with patch("code_agents.routers.git_ops._get_client", return_value=mock_client):
            result = asyncio.run(current_branch())
        assert result["branch"] == "main"

    def test_current_branch_error(self):
        from code_agents.routers.git_ops import current_branch
        from code_agents.cicd.git_client import GitOpsError
        mock_client = MagicMock()
        mock_client.current_branch = AsyncMock(side_effect=GitOpsError("fail"))
        with patch("code_agents.routers.git_ops._get_client", return_value=mock_client):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                asyncio.run(current_branch())
            assert exc.value.status_code == 502

    def test_get_diff_success(self):
        from code_agents.routers.git_ops import get_diff
        mock_client = MagicMock()
        mock_client.diff = AsyncMock(return_value={
            "files_changed": 3, "insertions": 10, "deletions": 5
        })
        mock_client.repo_path = "/tmp/repo"
        with patch("code_agents.routers.git_ops._get_client", return_value=mock_client):
            result = asyncio.run(get_diff("main", "HEAD"))
        assert result["files_changed"] == 3

    def test_get_diff_invalid_ref(self):
        from code_agents.routers.git_ops import get_diff
        from code_agents.cicd.git_client import GitOpsError
        mock_client = MagicMock()
        mock_client.diff = AsyncMock(side_effect=GitOpsError("Invalid ref"))
        with patch("code_agents.routers.git_ops._get_client", return_value=mock_client):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                asyncio.run(get_diff("bad", "ref"))
            assert exc.value.status_code == 422

    def test_get_log_success(self):
        from code_agents.routers.git_ops import get_log
        mock_client = MagicMock()
        mock_client.log = AsyncMock(return_value=[{"hash": "abc"}])
        mock_client.repo_path = "/tmp"
        with patch("code_agents.routers.git_ops._get_client", return_value=mock_client):
            result = asyncio.run(get_log("HEAD", 10))
        assert result["count"] == 1

    def test_push_success(self):
        from code_agents.routers.git_ops import push_branch, PushRequest
        mock_client = MagicMock()
        mock_client.push = AsyncMock(return_value={"status": "ok"})
        mock_client.repo_path = "/tmp"
        with patch("code_agents.routers.git_ops._get_client", return_value=mock_client):
            result = asyncio.run(push_branch(PushRequest(branch="main")))
        assert result["status"] == "ok"

    def test_get_status_success(self):
        from code_agents.routers.git_ops import get_status
        mock_client = MagicMock()
        mock_client.status = AsyncMock(return_value={"clean": True})
        mock_client.repo_path = "/tmp"
        with patch("code_agents.routers.git_ops._get_client", return_value=mock_client):
            result = asyncio.run(get_status())
        assert result["clean"] is True

    def test_fetch_remote_success(self):
        from code_agents.routers.git_ops import fetch_remote
        mock_client = MagicMock()
        mock_client.fetch = AsyncMock(return_value="fetched")
        mock_client.repo_path = "/tmp"
        with patch("code_agents.routers.git_ops._get_client", return_value=mock_client):
            result = asyncio.run(fetch_remote("origin"))
        assert result["remote"] == "origin"

    def test_checkout_success(self):
        from code_agents.routers.git_ops import checkout_branch, CheckoutRequest
        mock_client = MagicMock()
        mock_client.checkout = AsyncMock(return_value={"switched": True})
        mock_client.repo_path = "/tmp"
        with patch("code_agents.routers.git_ops._get_client", return_value=mock_client):
            result = asyncio.run(checkout_branch(CheckoutRequest(branch="dev")))
        assert result["switched"] is True

    def test_checkout_dirty_error(self):
        from code_agents.routers.git_ops import checkout_branch, CheckoutRequest
        from code_agents.cicd.git_client import GitOpsError
        mock_client = MagicMock()
        mock_client.checkout = AsyncMock(side_effect=GitOpsError("dirty working tree"))
        with patch("code_agents.routers.git_ops._get_client", return_value=mock_client):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                asyncio.run(checkout_branch(CheckoutRequest(branch="dev")))
            assert exc.value.status_code == 409

    def test_stash_success(self):
        from code_agents.routers.git_ops import stash_changes, StashRequest
        mock_client = MagicMock()
        mock_client.stash = AsyncMock(return_value={"action": "push"})
        mock_client.repo_path = "/tmp"
        with patch("code_agents.routers.git_ops._get_client", return_value=mock_client):
            result = asyncio.run(stash_changes(StashRequest(action="push")))
        assert result["action"] == "push"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. routers/argocd.py — _get_client, list_pods, pod_logs, sync, rollback, history
# ═══════════════════════════════════════════════════════════════════════════════

class TestArgoCDRouter:
    """Test ArgoCD router handler functions."""

    def test_get_client_no_url(self, monkeypatch):
        monkeypatch.delenv("ARGOCD_URL", raising=False)
        from code_agents.routers.argocd import _get_client
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _get_client()
        assert exc.value.status_code == 503

    def test_get_client_no_credentials(self, monkeypatch):
        monkeypatch.setenv("ARGOCD_URL", "https://argocd.test")
        monkeypatch.delenv("ARGOCD_USERNAME", raising=False)
        monkeypatch.delenv("ARGOCD_PASSWORD", raising=False)
        from code_agents.routers.argocd import _get_client
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _get_client()
        assert exc.value.status_code == 503

    def test_get_client_success(self, monkeypatch):
        monkeypatch.setenv("ARGOCD_URL", "https://argocd.test")
        monkeypatch.setenv("ARGOCD_USERNAME", "admin")
        monkeypatch.setenv("ARGOCD_PASSWORD", "secret")
        monkeypatch.setenv("ARGOCD_VERIFY_SSL", "false")
        from code_agents.routers.argocd import _get_client
        client = _get_client()
        assert client.base_url == "https://argocd.test"

    def test_list_pods_success(self):
        from code_agents.routers.argocd import list_pods
        with patch("code_agents.routers.argocd._get_client") as mc:
            mc.return_value.list_pods = AsyncMock(return_value=[{"name": "pod-1"}])
            result = asyncio.run(list_pods("myapp"))
        assert result["count"] == 1

    def test_list_pods_error(self):
        from code_agents.routers.argocd import list_pods
        from code_agents.cicd.argocd_client import ArgoCDError
        with patch("code_agents.routers.argocd._get_client") as mc:
            mc.return_value.list_pods = AsyncMock(side_effect=ArgoCDError("fail"))
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                asyncio.run(list_pods("myapp"))
            assert exc.value.status_code == 502

    def test_get_pod_logs_with_errors(self):
        from code_agents.routers.argocd import get_pod_logs
        with patch("code_agents.routers.argocd._get_client") as mc:
            mc.return_value.get_pod_logs = AsyncMock(return_value={
                "has_errors": True, "error_lines": ["ERROR: boom"], "logs": "line1\nERROR: boom"
            })
            result = asyncio.run(get_pod_logs("app", "pod-1", namespace="ns"))
        assert result["has_errors"] is True

    def test_get_pod_logs_error(self):
        from code_agents.routers.argocd import get_pod_logs
        from code_agents.cicd.argocd_client import ArgoCDError
        with patch("code_agents.routers.argocd._get_client") as mc:
            mc.return_value.get_pod_logs = AsyncMock(side_effect=ArgoCDError("fail"))
            from fastapi import HTTPException
            with pytest.raises(HTTPException):
                asyncio.run(get_pod_logs("app", "pod-1"))

    def test_sync_app_success(self):
        from code_agents.routers.argocd import sync_app
        with patch("code_agents.routers.argocd._get_client") as mc:
            mc.return_value.sync_app = AsyncMock(return_value={"status": "synced"})
            result = asyncio.run(sync_app("myapp"))
        assert result["status"] == "synced"

    def test_sync_app_error(self):
        from code_agents.routers.argocd import sync_app
        from code_agents.cicd.argocd_client import ArgoCDError
        with patch("code_agents.routers.argocd._get_client") as mc:
            mc.return_value.sync_app = AsyncMock(side_effect=ArgoCDError("fail"))
            from fastapi import HTTPException
            with pytest.raises(HTTPException):
                asyncio.run(sync_app("myapp"))

    def test_rollback_previous_success(self):
        from code_agents.routers.argocd import rollback_app, RollbackRequest
        with patch("code_agents.routers.argocd._get_client") as mc:
            mc.return_value.get_history = AsyncMock(return_value=[
                {"id": 1}, {"id": 2}, {"id": 3}
            ])
            mc.return_value.rollback = AsyncMock(return_value={"status": "rolled_back"})
            req = RollbackRequest(revision="previous")
            result = asyncio.run(rollback_app("myapp", req))
        assert result["status"] == "rolled_back"

    def test_rollback_previous_no_history(self):
        from code_agents.routers.argocd import rollback_app, RollbackRequest
        with patch("code_agents.routers.argocd._get_client") as mc:
            mc.return_value.get_history = AsyncMock(return_value=[{"id": 1}])
            req = RollbackRequest(revision="previous")
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                asyncio.run(rollback_app("myapp", req))
            assert exc.value.status_code == 422

    def test_rollback_numeric_revision(self):
        from code_agents.routers.argocd import rollback_app, RollbackRequest
        with patch("code_agents.routers.argocd._get_client") as mc:
            mc.return_value.rollback = AsyncMock(return_value={"status": "ok"})
            req = RollbackRequest(revision=5)
            result = asyncio.run(rollback_app("myapp", req))
        assert result["status"] == "ok"

    def test_get_history_success(self):
        from code_agents.routers.argocd import get_history
        with patch("code_agents.routers.argocd._get_client") as mc:
            mc.return_value.get_history = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
            result = asyncio.run(get_history("myapp"))
        assert result["count"] == 2

    def test_get_history_error(self):
        from code_agents.routers.argocd import get_history
        from code_agents.cicd.argocd_client import ArgoCDError
        with patch("code_agents.routers.argocd._get_client") as mc:
            mc.return_value.get_history = AsyncMock(side_effect=ArgoCDError("fail"))
            from fastapi import HTTPException
            with pytest.raises(HTTPException):
                asyncio.run(get_history("myapp"))


# ═══════════════════════════════════════════════════════════════════════════════
# 8. config.py — _expand_system_prompt_env, AgentLoader (lines 17-35, 74-167)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigExpand:
    """Test config.py env expansion and agent loading."""

    def test_expand_public_base_url_from_env(self, monkeypatch):
        monkeypatch.setenv("CODE_AGENTS_PUBLIC_BASE_URL", "https://api.test.com")
        from code_agents.core.config import _expand_system_prompt_env
        result = _expand_system_prompt_env("API: ${CODE_AGENTS_PUBLIC_BASE_URL}")
        assert result == "API: https://api.test.com"

    def test_expand_public_base_url_fallback(self, monkeypatch):
        monkeypatch.delenv("CODE_AGENTS_PUBLIC_BASE_URL", raising=False)
        monkeypatch.setenv("PORT", "9090")
        from code_agents.core.config import _expand_system_prompt_env
        result = _expand_system_prompt_env("URL: ${CODE_AGENTS_PUBLIC_BASE_URL}")
        assert result == "URL: http://127.0.0.1:9090"

    def test_expand_atlassian_url_set(self, monkeypatch):
        monkeypatch.setenv("ATLASSIAN_CLOUD_SITE_URL", "https://mysite.atlassian.net")
        from code_agents.core.config import _expand_system_prompt_env
        result = _expand_system_prompt_env("Site: ${ATLASSIAN_CLOUD_SITE_URL}")
        assert result == "Site: https://mysite.atlassian.net"

    def test_expand_atlassian_url_unset(self, monkeypatch):
        monkeypatch.delenv("ATLASSIAN_CLOUD_SITE_URL", raising=False)
        from code_agents.core.config import _expand_system_prompt_env
        result = _expand_system_prompt_env("Site: ${ATLASSIAN_CLOUD_SITE_URL}")
        assert "(set ATLASSIAN_CLOUD_SITE_URL in .env)" in result

    def test_expand_unknown_var_set(self, monkeypatch):
        monkeypatch.setenv("MY_CUSTOM_VAR", "hello")
        from code_agents.core.config import _expand_system_prompt_env
        result = _expand_system_prompt_env("Val: ${MY_CUSTOM_VAR}")
        assert result == "Val: hello"

    def test_expand_unknown_var_unset(self, monkeypatch):
        monkeypatch.delenv("MY_CUSTOM_VAR", raising=False)
        from code_agents.core.config import _expand_system_prompt_env
        result = _expand_system_prompt_env("Val: ${MY_CUSTOM_VAR}")
        assert result == "Val: ${MY_CUSTOM_VAR}"

    def test_agent_loader_load_file(self, tmp_path, monkeypatch):
        """AgentLoader._load_file parses YAML, expands env vars in backend/model."""
        monkeypatch.delenv("CODE_AGENTS_BACKEND", raising=False)
        monkeypatch.delenv("CODE_AGENTS_MODEL", raising=False)

        agent_yaml = tmp_path / "test-agent" / "test-agent.yaml"
        agent_yaml.parent.mkdir()
        agent_yaml.write_text("""
name: test-agent
display_name: Test Agent
backend: "${CODE_AGENTS_BACKEND:cursor}"
model: "${CODE_AGENTS_MODEL:Composer 2 Fast}"
system_prompt: "Hello ${CODE_AGENTS_PUBLIC_BASE_URL}"
""")
        from code_agents.core.config import AgentLoader
        loader = AgentLoader(tmp_path)
        loader.load()
        cfg = loader.get("test-agent")
        assert cfg is not None
        assert cfg.backend == "cursor"
        assert cfg.model == "Composer 2 Fast"

    def test_agent_loader_per_agent_override(self, tmp_path, monkeypatch):
        """Per-agent env overrides CODE_AGENTS_MODEL_<AGENT> and CODE_AGENTS_BACKEND_<AGENT>."""
        monkeypatch.setenv("CODE_AGENTS_MODEL_TEST_AGENT", "gpt-4")
        monkeypatch.setenv("CODE_AGENTS_BACKEND_TEST_AGENT", "claude")
        monkeypatch.delenv("CODE_AGENTS_BACKEND", raising=False)
        monkeypatch.delenv("CODE_AGENTS_MODEL", raising=False)

        agent_yaml = tmp_path / "test-agent.yaml"
        agent_yaml.write_text("""
name: test-agent
display_name: Test Agent
""")
        from code_agents.core.config import AgentLoader
        loader = AgentLoader(tmp_path)
        loader.load()
        cfg = loader.get("test-agent")
        assert cfg.model == "gpt-4"
        assert cfg.backend == "claude"

    def test_agent_loader_api_key_env_expansion(self, tmp_path, monkeypatch):
        """api_key with ${VAR} syntax is expanded from env."""
        monkeypatch.setenv("MY_API_KEY", "secret123")
        agent_yaml = tmp_path / "key-agent.yaml"
        agent_yaml.write_text("""
name: key-agent
display_name: Key Agent
api_key: "${MY_API_KEY}"
""")
        from code_agents.core.config import AgentLoader
        loader = AgentLoader(tmp_path)
        loader.load()
        cfg = loader.get("key-agent")
        assert cfg.api_key == "secret123"

    def test_agent_loader_missing_dir(self, tmp_path):
        """AgentLoader.load raises when dir doesn't exist."""
        from code_agents.core.config import AgentLoader
        loader = AgentLoader(tmp_path / "nonexistent")
        with pytest.raises(FileNotFoundError):
            loader.load()

    def test_agent_loader_extra_args_env_expansion(self, tmp_path, monkeypatch):
        """extra_args with ${VAR} syntax are expanded."""
        monkeypatch.setenv("MY_EXTRA", "expanded_val")
        agent_yaml = tmp_path / "extra-agent.yaml"
        agent_yaml.write_text("""
name: extra-agent
display_name: Extra Agent
extra_args:
  key1: "${MY_EXTRA}"
  key2: literal
""")
        from code_agents.core.config import AgentLoader
        loader = AgentLoader(tmp_path)
        loader.load()
        cfg = loader.get("extra-agent")
        assert cfg.extra_args["key1"] == "expanded_val"
        assert cfg.extra_args["key2"] == "literal"
