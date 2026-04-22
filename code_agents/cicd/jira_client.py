"""
Jira & Confluence REST API client.

Uses httpx for async HTTP. Authenticates via HTTP Basic (email + API token).
Base URL from JIRA_URL env var (e.g. https://acme.atlassian.net).
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger("code_agents.jira_client")


class JiraError(Exception):
    """Raised when a Jira/Confluence API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class JiraClient:
    """Async client for the Jira & Confluence REST APIs."""

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.timeout = timeout
        # Basic auth header: base64(email:token)
        credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._auth_header = f"Basic {credentials}"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": self._auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self.timeout,
            follow_redirects=True,
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated request and return parsed JSON."""
        logger.debug("Jira API request: %s %s", method, path)
        async with self._client() as client:
            r = await client.request(method, path, **kwargs)
            if r.status_code >= 400:
                logger.error("Jira API error: %s %s returned %d", method, path, r.status_code)
                raise JiraError(
                    f"Jira API {method} {path} returned {r.status_code}: {r.text[:500]}",
                    status_code=r.status_code,
                    response_text=r.text[:2000],
                )
            return r.json() if r.text.strip() else {}

    # ------------------------------------------------------------------
    # Jira Issue APIs
    # ------------------------------------------------------------------

    async def get_issue(self, key: str) -> dict[str, Any]:
        """GET /rest/api/3/issue/{key} — returns summary, description, status, assignee, acceptance criteria, subtasks, labels, priority."""
        data = await self._request("GET", f"/rest/api/3/issue/{key}")
        fields = data.get("fields", {})

        # Extract acceptance criteria from description (ADF format)
        acceptance_criteria = None
        description = fields.get("description")
        if description and isinstance(description, dict):
            # Walk ADF nodes looking for "Acceptance Criteria" heading
            acceptance_criteria = self._extract_acceptance_criteria(description)

        assignee = fields.get("assignee")
        subtasks = fields.get("subtasks", [])

        return {
            "key": data.get("key"),
            "summary": fields.get("summary"),
            "description": description,
            "status": fields.get("status", {}).get("name"),
            "assignee": assignee.get("displayName") if assignee else None,
            "acceptance_criteria": acceptance_criteria,
            "subtasks": [
                {"key": s.get("key"), "summary": s.get("fields", {}).get("summary"), "status": s.get("fields", {}).get("status", {}).get("name")}
                for s in subtasks
            ],
            "labels": fields.get("labels", []),
            "priority": fields.get("priority", {}).get("name"),
            "issue_type": fields.get("issuetype", {}).get("name"),
            "project": fields.get("project", {}).get("key"),
        }

    def _extract_acceptance_criteria(self, adf: dict) -> Optional[str]:
        """Walk ADF document to find content after an 'Acceptance Criteria' heading."""
        content = adf.get("content", [])
        found = False
        criteria_parts: list[str] = []
        for node in content:
            if node.get("type") == "heading":
                text = self._adf_to_text(node)
                if "acceptance criteria" in text.lower():
                    found = True
                    continue
                elif found:
                    break  # next heading — stop collecting
            if found:
                criteria_parts.append(self._adf_to_text(node))
        return "\n".join(criteria_parts).strip() or None

    def _adf_to_text(self, node: dict) -> str:
        """Recursively extract plain text from an ADF node."""
        if node.get("type") == "text":
            return node.get("text", "")
        parts = []
        for child in node.get("content", []):
            parts.append(self._adf_to_text(child))
        return "".join(parts)

    async def search_issues(self, jql: str, max_results: int = 50) -> list[dict[str, Any]]:
        """POST /rest/api/3/search — JQL search."""
        data = await self._request("POST", "/rest/api/3/search", json={
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "status", "assignee", "priority", "issuetype", "labels", "created", "updated"],
        })
        issues = []
        for item in data.get("issues", []):
            fields = item.get("fields", {})
            assignee = fields.get("assignee")
            issues.append({
                "key": item.get("key"),
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "assignee": assignee.get("displayName") if assignee else None,
                "priority": fields.get("priority", {}).get("name"),
                "issue_type": fields.get("issuetype", {}).get("name"),
                "labels": fields.get("labels", []),
                "created": fields.get("created"),
                "updated": fields.get("updated"),
            })
        return issues

    async def add_comment(self, key: str, body: str) -> dict[str, Any]:
        """POST /rest/api/3/issue/{key}/comment — ADF format body."""
        adf_body = {
            "body": {
                "version": 1,
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": body}
                        ],
                    }
                ],
            }
        }
        return await self._request("POST", f"/rest/api/3/issue/{key}/comment", json=adf_body)

    async def get_transitions(self, key: str) -> list[dict[str, Any]]:
        """GET /rest/api/3/issue/{key}/transitions — available transitions."""
        data = await self._request("GET", f"/rest/api/3/issue/{key}/transitions")
        return [
            {"id": t.get("id"), "name": t.get("name"), "to": t.get("to", {}).get("name")}
            for t in data.get("transitions", [])
        ]

    async def transition_issue(self, key: str, transition_id: str, comment: Optional[str] = None) -> dict[str, Any]:
        """POST /rest/api/3/issue/{key}/transitions — move ticket to a new status."""
        payload: dict[str, Any] = {
            "transition": {"id": transition_id},
        }
        if comment:
            payload["update"] = {
                "comment": [
                    {
                        "add": {
                            "body": {
                                "version": 1,
                                "type": "doc",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": comment}],
                                    }
                                ],
                            }
                        }
                    }
                ]
            }
        return await self._request("POST", f"/rest/api/3/issue/{key}/transitions", json=payload)

    async def create_issue(
        self,
        project: str,
        summary: str,
        description: str,
        issue_type: str = "Task",
    ) -> dict[str, Any]:
        """POST /rest/api/3/issue — create a new issue."""
        logger.info("Creating Jira issue: project=%s, type=%s, summary=%s", project, issue_type, summary[:80])
        payload = {
            "fields": {
                "project": {"key": project},
                "summary": summary,
                "description": {
                    "version": 1,
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}],
                        }
                    ],
                },
                "issuetype": {"name": issue_type},
            }
        }
        data = await self._request("POST", "/rest/api/3/issue", json=payload)
        return {"key": data.get("key"), "id": data.get("id"), "self": data.get("self")}

    async def bulk_transition(self, issue_keys: list[str], transition_name: str) -> list[dict]:
        """Transition multiple issues to a new status by transition name.

        For each issue, fetches available transitions, finds the one matching
        *transition_name* (case-insensitive), and executes it.

        Returns a list of result dicts: [{"key": str, "status": "ok"|"error", "message": str}].
        """
        results: list[dict[str, Any]] = []
        for key in issue_keys:
            try:
                transitions = await self.get_transitions(key)
                match = None
                for t in transitions:
                    if t.get("name", "").lower() == transition_name.lower():
                        match = t
                        break
                if not match:
                    available = [t.get("name") for t in transitions]
                    results.append({
                        "key": key,
                        "status": "error",
                        "message": f"Transition '{transition_name}' not found. Available: {available}",
                    })
                    continue
                await self.transition_issue(key, match["id"])
                results.append({"key": key, "status": "ok", "message": f"Transitioned to {match.get('to', transition_name)}"})
            except Exception as e:
                results.append({"key": key, "status": "error", "message": str(e)})
        return results

    # ------------------------------------------------------------------
    # Confluence APIs
    # ------------------------------------------------------------------

    async def get_confluence_page(self, page_id: str) -> dict[str, Any]:
        """GET /wiki/api/v2/pages/{id}?body-format=storage — returns title + body."""
        data = await self._request("GET", f"/wiki/api/v2/pages/{page_id}?body-format=storage")
        body = data.get("body", {}).get("storage", {}).get("value", "")
        return {
            "id": data.get("id"),
            "title": data.get("title"),
            "body": body,
            "status": data.get("status"),
            "space_id": data.get("spaceId"),
            "_links": data.get("_links", {}),
        }

    async def search_confluence(self, cql: str) -> list[dict[str, Any]]:
        """GET /wiki/rest/api/content/search?cql={cql} — search Confluence pages."""
        import urllib.parse
        encoded_cql = urllib.parse.quote(cql)
        data = await self._request("GET", f"/wiki/rest/api/content/search?cql={encoded_cql}")
        results = []
        for item in data.get("results", []):
            results.append({
                "id": item.get("id"),
                "title": item.get("title"),
                "type": item.get("type"),
                "status": item.get("status"),
                "space": item.get("space", {}).get("key") if item.get("space") else None,
                "_links": item.get("_links", {}),
            })
        return results
