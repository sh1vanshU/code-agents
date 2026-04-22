"""Tests for pr_review_client.py — unit tests with mocked HTTP."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.cicd.pr_review_client import PRReviewClient, PRReviewError


class TestPRReviewClientInit:
    def test_defaults(self):
        c = PRReviewClient()
        assert c.token == ""
        assert c.repo == ""
        assert c.api_url == "https://api.github.com"
        assert c.timeout == 30.0

    def test_custom_init(self):
        c = PRReviewClient(token="ghp_test", repo="owner/repo", timeout=60.0)
        assert c.token == "ghp_test"
        assert c.repo == "owner/repo"


def _mock_client(mock_resp):
    mock_c = AsyncMock()
    mock_c.get = AsyncMock(return_value=mock_resp)
    mock_c.post = AsyncMock(return_value=mock_resp)
    mock_c.__aenter__ = AsyncMock(return_value=mock_c)
    mock_c.__aexit__ = AsyncMock(return_value=False)
    return mock_c


class TestListPulls:
    def test_success(self):
        c = PRReviewClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "number": 1, "title": "Fix bug", "state": "open",
                "user": {"login": "alice"}, "head": {"ref": "fix-bug", "sha": "abc"},
                "base": {"ref": "main"}, "additions": 10, "deletions": 5,
                "changed_files": 2, "mergeable": True, "draft": False,
                "html_url": "", "created_at": "", "updated_at": "",
            }
        ]
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.list_pulls())
            assert len(result) == 1
            assert result[0]["number"] == 1
            assert result[0]["author"] == "alice"

    def test_failure(self):
        c = PRReviewClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            with pytest.raises(PRReviewError):
                asyncio.run(c.list_pulls())


class TestGetPull:
    def test_success(self):
        c = PRReviewClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "number": 42, "title": "Add feature", "state": "open",
            "user": {"login": "bob"}, "head": {"ref": "feature", "sha": "def"},
            "base": {"ref": "main"}, "additions": 100, "deletions": 20,
            "changed_files": 5, "mergeable": True, "draft": False,
            "html_url": "", "created_at": "", "updated_at": "",
        }
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.get_pull(42))
            assert result["number"] == 42
            assert result["title"] == "Add feature"


class TestGetPullDiff:
    def test_success(self):
        c = PRReviewClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "diff --git a/file.py b/file.py\n+added line\n"
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.get_pull_diff(42))
            assert "diff --git" in result


class TestGetPullFiles:
    def test_success(self):
        c = PRReviewClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"filename": "src/main.py", "status": "modified", "additions": 5, "deletions": 2, "changes": 7, "patch": "..."},
            {"filename": "tests/test_main.py", "status": "added", "additions": 20, "deletions": 0, "changes": 20, "patch": "..."},
        ]
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.get_pull_files(42))
            assert len(result) == 2
            assert result[0]["filename"] == "src/main.py"


class TestPostReview:
    def test_success(self):
        c = PRReviewClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 999}
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.post_review(42, event="COMMENT", body="LGTM"))
            assert result["status"] == "posted"
            assert result["state"] == "COMMENT"

    def test_failure(self):
        c = PRReviewClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.text = "Validation Failed"
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            with pytest.raises(PRReviewError):
                asyncio.run(c.post_review(42, event="APPROVE"))


class TestGetComments:
    def test_success(self):
        c = PRReviewClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": 1, "user": {"login": "alice"}, "body": "Fix this", "path": "main.py", "line": 10, "created_at": ""},
        ]
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.get_comments(42))
            assert len(result) == 1
            assert result[0]["user"] == "alice"


class TestFormatPR:
    def test_format(self):
        c = PRReviewClient()
        pr = {
            "number": 1, "title": "Fix", "state": "open", "user": {"login": "alice"},
            "head": {"ref": "fix", "sha": "abc"}, "base": {"ref": "main"},
            "additions": 10, "deletions": 5, "changed_files": 2,
            "mergeable": True, "draft": False, "html_url": "", "created_at": "", "updated_at": "",
        }
        result = c._format_pr(pr)
        assert result["number"] == 1
        assert result["author"] == "alice"
        assert result["head_branch"] == "fix"
