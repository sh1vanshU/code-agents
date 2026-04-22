"""
Redash API client for running database queries.

Supports authentication via:
- API key (recommended): set REDASH_API_KEY or pass api_key to RedashClient.
- Username + password: session-based login; pass username and password to RedashClient.
  The client will POST to /login and reuse the session cookie for API calls.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

logger = logging.getLogger("code_agents.integrations.redash_client")


class RedashError(Exception):
    """Raised when a Redash API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class RedashClient:
    """
    Client for the Redash API.

    Authenticate with either:
    - api_key: use Authorization header (recommended).
    - username + password: session login; uses session cookie for subsequent requests.
    """

    JOB_STATUS_PENDING = 1
    JOB_STATUS_STARTED = 2
    JOB_STATUS_SUCCESS = 3
    JOB_STATUS_FAILURE = 4
    JOB_TERMINAL_STATUSES = (JOB_STATUS_SUCCESS, JOB_STATUS_FAILURE)

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 30.0,
        poll_interval: float = 1.0,
        poll_timeout: float = 300.0,
    ):
        """
        Args:
            base_url: Redash base URL (e.g. https://redash.example.com).
            api_key: User or query API key. If set, used for all requests.
            username: Login email/username for session auth (use with password).
            password: Login password for session auth (use with username).
            timeout: HTTP request timeout in seconds.
            poll_interval: Seconds between job status polls.
            poll_timeout: Max seconds to wait for a query job to complete.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.username = username
        self.password = password
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        self._query_cache: dict[str, tuple[float, Any]] = {}  # key -> (expires_at, value)
        if api_key:
            self._session.headers.update({"Authorization": f"Key {api_key}"})
        elif username and password:
            self._login()

    def _login(self) -> None:
        """Authenticate with username/password via session login."""
        login_url = f"{self.base_url}/login"
        # Redash login form uses 'email' and 'password' — must be sent as
        # form-encoded data (not JSON).  Temporarily drop Content-Type so
        # requests sends the correct application/x-www-form-urlencoded header.
        payload = {"email": self.username, "password": self.password}
        ct = self._session.headers.pop("Content-Type", None)
        try:
            resp = self._session.post(
                login_url,
                data=payload,
                allow_redirects=True,
                timeout=self.timeout,
            )
        finally:
            if ct:
                self._session.headers["Content-Type"] = ct
        if resp.status_code != 200:
            raise RedashError(
                f"Login failed: HTTP {resp.status_code}",
                status_code=resp.status_code,
                response_text=resp.text[:500],
            )
        # Check we're not still on login page (e.g. wrong credentials)
        if "/login" in resp.url:
            raise RedashError("Login failed: invalid username or password")

    def _cache_get(self, key: str) -> Optional[Any]:
        """Return cached value if present and not expired, else None."""
        entry = self._query_cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._query_cache[key]
            return None
        return value

    def _cache_set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Store a value in the cache with a TTL in seconds."""
        self._query_cache[key] = (time.monotonic() + ttl, value)

    def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)
        resp = self._session.request(method, url, json=json, **kwargs)
        return resp

    def list_data_sources(self) -> list[dict[str, Any]]:
        """List all data sources (for resolving data_source_id by name)."""
        r = self._request("GET", "/api/data_sources")
        if r.status_code != 200:
            raise RedashError(
                f"Failed to list data sources: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        return r.json()

    def get_schema(self, data_source_id: int) -> list[dict[str, Any]]:
        """
        Fetch the schema (tables + columns) for a data source.

        Returns a list of dicts like:
            [{"name": "table_name", "columns": ["col1", "col2", ...]}, ...]

        Columns may be strings or dicts depending on Redash version.
        """
        r = self._request("GET", f"/api/data_sources/{data_source_id}/schema")
        if r.status_code != 200:
            raise RedashError(
                f"Failed to get schema: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        data = r.json()
        tables = data.get("schema", data) if isinstance(data, dict) else data
        # Normalize: ensure each table entry is a dict with name + columns list
        result = []
        for t in tables:
            if isinstance(t, dict):
                cols = t.get("columns", [])
                # Columns may be strings or {"name": ..., "type": ...} dicts
                normalized_cols = []
                for c in cols:
                    if isinstance(c, str):
                        normalized_cols.append(c)
                    elif isinstance(c, dict):
                        normalized_cols.append(c.get("name", str(c)))
                    else:
                        normalized_cols.append(str(c))
                result.append({"name": t.get("name", "?"), "columns": normalized_cols})
        return result

    def run_query(
        self,
        data_source_id: int,
        query: str,
        max_age: int = 0,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Execute an ad-hoc SQL (or data source) query and return the result.

        Args:
            data_source_id: Redash data source ID (see list_data_sources()).
            query: Query text to execute.
            max_age: Use cached result if younger than this many seconds; 0 = always run fresh.
            parameters: Optional query parameters (for parameterized queries).

        Returns:
            Dict with keys: columns, rows, metadata (e.g. runtime). Same shape as Redash query_result.data.
        """
        # Check cache first
        cache_key = f"run_query:{data_source_id}:{query}:{parameters}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for query on ds=%d", data_source_id)
            return cached

        body = {
            "data_source_id": data_source_id,
            "query": query,
            "max_age": max_age,
        }
        if parameters is not None:
            body["parameters"] = parameters

        r = self._request("POST", "/api/query_results", json=body)
        if r.status_code not in (200, 201):
            raise RedashError(
                f"Failed to run query: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        data = r.json()
        job = data.get("job")
        if not job:
            raise RedashError("Invalid response: no job in response", response_text=r.text[:500])

        query_result_id = self._poll_job(job)
        if query_result_id is None:
            error_msg = job.get("error") or "Query execution failed"
            raise RedashError(error_msg)

        result = self._get_query_result_by_id(query_result_id)
        self._cache_set(cache_key, result)
        return result

    def run_saved_query(
        self,
        query_id: int,
        max_age: int = 0,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Execute a saved query by ID and return the result.

        Args:
            query_id: Redash query ID.
            max_age: Use cached result if younger than this many seconds; 0 = always run fresh.
            parameters: Optional query parameters.

        Returns:
            Dict with columns, rows, metadata.
        """
        body = {"max_age": max_age}
        if parameters:
            body["parameters"] = parameters

        r = self._request("POST", f"/api/queries/{query_id}/results", json=body)
        if r.status_code not in (200, 201):
            raise RedashError(
                f"Failed to run saved query: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        data = r.json()
        job = data.get("job")
        if not job:
            raise RedashError("Invalid response: no job in response", response_text=r.text[:500])

        query_result_id = self._poll_job(job)
        if query_result_id is None:
            error_msg = job.get("error") or "Query execution failed"
            raise RedashError(error_msg)

        r2 = self._request("GET", f"/api/queries/{query_id}/results/{query_result_id}.json")
        if r2.status_code != 200:
            raise RedashError(
                f"Failed to get query result: HTTP {r2.status_code}",
                status_code=r2.status_code,
                response_text=r2.text[:500],
            )
        result = r2.json()
        qr = result.get("query_result", {})
        data_block = qr.get("data", {})
        return {
            "columns": data_block.get("columns", []),
            "rows": data_block.get("rows", []),
            "metadata": {
                "runtime": qr.get("runtime"),
                "row_count": len(data_block.get("rows", [])),
            },
        }

    def _poll_job(self, job: dict[str, Any]) -> Optional[int]:
        """Poll job until terminal status; return query_result_id on success, None on failure."""
        job_id = job.get("id")
        if not job_id:
            return None
        deadline = time.monotonic() + self.poll_timeout
        while time.monotonic() < deadline:
            r = self._request("GET", f"/api/jobs/{job_id}")
            if r.status_code != 200:
                raise RedashError(
                    f"Failed to get job status: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            data = r.json()
            job = data.get("job", {})
            status = job.get("status")
            if status == self.JOB_STATUS_SUCCESS:
                return job.get("query_result_id")
            if status == self.JOB_STATUS_FAILURE:
                return None
            time.sleep(self.poll_interval)
        raise RedashError(f"Job {job_id} did not complete within {self.poll_timeout}s")

    def _get_query_result_by_id(self, query_result_id: int) -> dict[str, Any]:
        """Fetch query result by ID (used for ad-hoc query_results)."""
        r = self._request("GET", f"/api/query_results/{query_result_id}.json")
        if r.status_code != 200:
            raise RedashError(
                f"Failed to get query result: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        result = r.json()
        # Response shape may be { "query_result": { "data": { "columns", "rows" }, "runtime" } }
        qr = result.get("query_result", result)
        data_block = qr.get("data", qr)
        if isinstance(data_block, dict):
            columns = data_block.get("columns", [])
            rows = data_block.get("rows", [])
        else:
            columns = []
            rows = []
        return {
            "columns": columns,
            "rows": rows,
            "metadata": {
                "runtime": qr.get("runtime"),
                "row_count": len(rows),
            },
        }
