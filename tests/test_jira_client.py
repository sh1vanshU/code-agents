"""Tests for jira_client.py — unit tests with mocked HTTP."""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.cicd.jira_client import JiraClient, JiraError


class TestJiraClientInit:
    def test_init(self):
        c = JiraClient(
            base_url="https://jira.example.com/",
            email="user@test.com",
            api_token="token123",
        )
        assert c.base_url == "https://jira.example.com"
        assert c.email == "user@test.com"
        assert c.api_token == "token123"
        assert c.timeout == 30.0

    def test_init_strips_trailing_slash(self):
        c = JiraClient(base_url="https://jira.example.com/", email="e", api_token="t")
        assert c.base_url == "https://jira.example.com"

    def test_init_auth_header(self):
        c = JiraClient(base_url="https://jira.example.com", email="user@test.com", api_token="token123")
        expected = base64.b64encode(b"user@test.com:token123").decode()
        assert c._auth_header == f"Basic {expected}"

    def test_init_custom_timeout(self):
        c = JiraClient(base_url="https://jira.example.com", email="e", api_token="t", timeout=60.0)
        assert c.timeout == 60.0


def _make_client():
    return JiraClient(
        base_url="https://jira.example.com",
        email="user@test.com",
        api_token="token123",
    )


class TestJiraRequest:
    def test_request_success(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"key": "PROJ-123"}
        mock_resp.text = '{"key": "PROJ-123"}'

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c._request("GET", "/rest/api/3/issue/PROJ-123"))
            assert result == {"key": "PROJ-123"}

    def test_request_empty_response(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.text = "   "

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c._request("POST", "/some/path"))
            assert result == {}

    def test_request_error(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(JiraError, match="returned 404"):
                asyncio.run(c._request("GET", "/rest/api/3/issue/MISSING"))


class TestJiraGetIssue:
    def test_get_issue(self):
        c = _make_client()
        response_data = {
            "key": "PROJ-123",
            "fields": {
                "summary": "Fix login bug",
                "description": None,
                "status": {"name": "In Progress"},
                "assignee": {"displayName": "Alice"},
                "subtasks": [
                    {"key": "PROJ-124", "fields": {"summary": "Sub task", "status": {"name": "Done"}}}
                ],
                "labels": ["bug", "urgent"],
                "priority": {"name": "High"},
                "issuetype": {"name": "Bug"},
                "project": {"key": "PROJ"},
            },
        }

        with patch.object(c, "_request", new_callable=AsyncMock, return_value=response_data):
            result = asyncio.run(c.get_issue("PROJ-123"))
            assert result["key"] == "PROJ-123"
            assert result["summary"] == "Fix login bug"
            assert result["status"] == "In Progress"
            assert result["assignee"] == "Alice"
            assert result["labels"] == ["bug", "urgent"]
            assert result["priority"] == "High"
            assert result["issue_type"] == "Bug"
            assert result["project"] == "PROJ"
            assert len(result["subtasks"]) == 1
            assert result["subtasks"][0]["key"] == "PROJ-124"

    def test_get_issue_no_assignee(self):
        c = _make_client()
        response_data = {
            "key": "PROJ-456",
            "fields": {
                "summary": "Unassigned task",
                "description": None,
                "status": {"name": "Open"},
                "assignee": None,
                "subtasks": [],
                "labels": [],
                "priority": {"name": "Medium"},
                "issuetype": {"name": "Task"},
                "project": {"key": "PROJ"},
            },
        }
        with patch.object(c, "_request", new_callable=AsyncMock, return_value=response_data):
            result = asyncio.run(c.get_issue("PROJ-456"))
            assert result["assignee"] is None

    def test_get_issue_with_acceptance_criteria(self):
        c = _make_client()
        response_data = {
            "key": "PROJ-789",
            "fields": {
                "summary": "New feature",
                "description": {
                    "type": "doc",
                    "content": [
                        {"type": "heading", "content": [{"type": "text", "text": "Acceptance Criteria"}]},
                        {"type": "paragraph", "content": [{"type": "text", "text": "Given X, when Y, then Z"}]},
                        {"type": "heading", "content": [{"type": "text", "text": "Notes"}]},
                    ],
                },
                "status": {"name": "Open"},
                "assignee": None,
                "subtasks": [],
                "labels": [],
                "priority": {"name": "Medium"},
                "issuetype": {"name": "Story"},
                "project": {"key": "PROJ"},
            },
        }
        with patch.object(c, "_request", new_callable=AsyncMock, return_value=response_data):
            result = asyncio.run(c.get_issue("PROJ-789"))
            assert result["acceptance_criteria"] == "Given X, when Y, then Z"


class TestJiraADFHelpers:
    def test_adf_to_text_simple(self):
        c = _make_client()
        node = {"type": "text", "text": "Hello World"}
        assert c._adf_to_text(node) == "Hello World"

    def test_adf_to_text_nested(self):
        c = _make_client()
        node = {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Hello "},
                {"type": "text", "text": "World"},
            ],
        }
        assert c._adf_to_text(node) == "Hello World"

    def test_extract_acceptance_criteria_found(self):
        c = _make_client()
        adf = {
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Description here"}]},
                {"type": "heading", "content": [{"type": "text", "text": "Acceptance Criteria"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "- Criterion 1"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "- Criterion 2"}]},
                {"type": "heading", "content": [{"type": "text", "text": "Other"}]},
            ],
        }
        result = c._extract_acceptance_criteria(adf)
        assert "- Criterion 1" in result
        assert "- Criterion 2" in result

    def test_extract_acceptance_criteria_not_found(self):
        c = _make_client()
        adf = {
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Just a description"}]},
            ],
        }
        result = c._extract_acceptance_criteria(adf)
        assert result is None

    def test_extract_acceptance_criteria_empty(self):
        c = _make_client()
        adf = {
            "content": [
                {"type": "heading", "content": [{"type": "text", "text": "Acceptance Criteria"}]},
                {"type": "heading", "content": [{"type": "text", "text": "Next Section"}]},
            ],
        }
        result = c._extract_acceptance_criteria(adf)
        assert result is None  # empty string becomes None


class TestJiraSearchIssues:
    def test_search_issues(self):
        c = _make_client()
        response_data = {
            "issues": [
                {
                    "key": "PROJ-1",
                    "fields": {
                        "summary": "First issue",
                        "status": {"name": "Open"},
                        "assignee": {"displayName": "Bob"},
                        "priority": {"name": "High"},
                        "issuetype": {"name": "Bug"},
                        "labels": ["critical"],
                        "created": "2025-01-01",
                        "updated": "2025-01-02",
                    },
                },
                {
                    "key": "PROJ-2",
                    "fields": {
                        "summary": "Second issue",
                        "status": {"name": "Done"},
                        "assignee": None,
                        "priority": {"name": "Low"},
                        "issuetype": {"name": "Task"},
                        "labels": [],
                        "created": "2025-01-03",
                        "updated": "2025-01-04",
                    },
                },
            ]
        }
        with patch.object(c, "_request", new_callable=AsyncMock, return_value=response_data):
            result = asyncio.run(
                c.search_issues("project = PROJ ORDER BY created DESC")
            )
            assert len(result) == 2
            assert result[0]["key"] == "PROJ-1"
            assert result[0]["assignee"] == "Bob"
            assert result[1]["assignee"] is None


class TestJiraAddComment:
    def test_add_comment(self):
        c = _make_client()
        with patch.object(c, "_request", new_callable=AsyncMock, return_value={"id": "10001"}) as mock_req:
            result = asyncio.run(
                c.add_comment("PROJ-123", "This is a comment")
            )
            assert result == {"id": "10001"}
            call_args = mock_req.call_args
            assert call_args[0][0] == "POST"
            assert "PROJ-123/comment" in call_args[0][1]
            body = call_args[1]["json"]
            assert body["body"]["type"] == "doc"


class TestJiraTransitions:
    def test_get_transitions(self):
        c = _make_client()
        response_data = {
            "transitions": [
                {"id": "11", "name": "Start Progress", "to": {"name": "In Progress"}},
                {"id": "21", "name": "Done", "to": {"name": "Done"}},
            ]
        }
        with patch.object(c, "_request", new_callable=AsyncMock, return_value=response_data):
            result = asyncio.run(c.get_transitions("PROJ-123"))
            assert len(result) == 2
            assert result[0]["id"] == "11"
            assert result[0]["name"] == "Start Progress"
            assert result[0]["to"] == "In Progress"

    def test_transition_issue_without_comment(self):
        c = _make_client()
        with patch.object(c, "_request", new_callable=AsyncMock, return_value={}) as mock_req:
            asyncio.run(c.transition_issue("PROJ-123", "21"))
            body = mock_req.call_args[1]["json"]
            assert body["transition"]["id"] == "21"
            assert "update" not in body

    def test_transition_issue_with_comment(self):
        c = _make_client()
        with patch.object(c, "_request", new_callable=AsyncMock, return_value={}) as mock_req:
            asyncio.run(
                c.transition_issue("PROJ-123", "21", comment="Moved to done")
            )
            body = mock_req.call_args[1]["json"]
            assert "update" in body
            assert body["update"]["comment"][0]["add"]["body"]["type"] == "doc"


class TestJiraCreateIssue:
    def test_create_issue(self):
        c = _make_client()
        response_data = {"key": "PROJ-999", "id": "10099", "self": "https://jira.example.com/rest/api/3/issue/10099"}
        with patch.object(c, "_request", new_callable=AsyncMock, return_value=response_data) as mock_req:
            result = asyncio.run(
                c.create_issue("PROJ", "New issue", "Description text", issue_type="Bug")
            )
            assert result["key"] == "PROJ-999"
            body = mock_req.call_args[1]["json"]
            assert body["fields"]["project"]["key"] == "PROJ"
            assert body["fields"]["summary"] == "New issue"
            assert body["fields"]["issuetype"]["name"] == "Bug"


class TestJiraConfluence:
    def test_get_confluence_page(self):
        c = _make_client()
        response_data = {
            "id": "12345",
            "title": "API Documentation",
            "body": {"storage": {"value": "<h1>API Docs</h1>"}},
            "status": "current",
            "spaceId": "TEAM",
            "_links": {"webui": "/wiki/spaces/TEAM/pages/12345"},
        }
        with patch.object(c, "_request", new_callable=AsyncMock, return_value=response_data):
            result = asyncio.run(c.get_confluence_page("12345"))
            assert result["id"] == "12345"
            assert result["title"] == "API Documentation"
            assert "<h1>API Docs</h1>" in result["body"]

    def test_search_confluence(self):
        c = _make_client()
        response_data = {
            "results": [
                {
                    "id": "111",
                    "title": "Page One",
                    "type": "page",
                    "status": "current",
                    "space": {"key": "TEAM"},
                    "_links": {},
                },
                {
                    "id": "222",
                    "title": "Page Two",
                    "type": "page",
                    "status": "current",
                    "space": None,
                    "_links": {},
                },
            ]
        }
        with patch.object(c, "_request", new_callable=AsyncMock, return_value=response_data):
            result = asyncio.run(
                c.search_confluence('text ~ "deployment"')
            )
            assert len(result) == 2
            assert result[0]["title"] == "Page One"
            assert result[0]["space"] == "TEAM"
            assert result[1]["space"] is None


class TestJiraError:
    def test_error_attrs(self):
        err = JiraError("test error", status_code=400, response_text="Bad Request")
        assert str(err) == "test error"
        assert err.status_code == 400
        assert err.response_text == "Bad Request"

    def test_error_defaults(self):
        err = JiraError("oops")
        assert err.status_code is None
        assert err.response_text is None
