"""
title: Redash Query Tool
description: Execute SQL queries, list data sources, and explore schemas via Redash API. Works through the Code Agents server or directly against Redash.
author: code-agents
version: 0.2.0
license: MIT
"""

import time
import requests
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        CODE_AGENTS_URL: str = Field(
            default="http://localhost:8000",
            description="Code Agents server base URL (Redash endpoints are under /redash/)",
        )
        REDASH_BASE_URL: str = Field(
            default="",
            description="Direct Redash URL (fallback if Code Agents server is not running)",
        )
        REDASH_API_KEY: str = Field(
            default="",
            description="Redash API key (for direct mode)",
        )
        REDASH_USERNAME: str = Field(
            default="",
            description="Redash username/email (for direct mode with password)",
        )
        REDASH_PASSWORD: str = Field(
            default="",
            description="Redash password (for direct mode with username)",
        )
        DEFAULT_DATA_SOURCE_ID: int = Field(
            default=0,
            description="Default data source ID to use when not specified (0 = must specify)",
        )
        QUERY_ROW_LIMIT: int = Field(
            default=100,
            description="Maximum rows to return from a query result",
        )

    def __init__(self):
        self.valves = self.Valves()
        self._direct_session = None
        self._direct_logged_in = False

    # ── Direct Redash helpers ──────────────────────────────────────────

    def _get_direct_session(self) -> requests.Session:
        """Authenticated requests.Session for direct Redash API calls."""
        if self._direct_session is not None and self._direct_logged_in:
            return self._direct_session

        self._direct_session = requests.Session()
        base = self.valves.REDASH_BASE_URL.rstrip("/")

        if self.valves.REDASH_API_KEY:
            self._direct_session.headers["Authorization"] = f"Key {self.valves.REDASH_API_KEY}"
        elif self.valves.REDASH_USERNAME and self.valves.REDASH_PASSWORD:
            resp = self._direct_session.post(
                f"{base}/login",
                data={"email": self.valves.REDASH_USERNAME, "password": self.valves.REDASH_PASSWORD},
                allow_redirects=True,
                timeout=15,
            )
            if resp.status_code != 200 or "/login" in resp.url:
                raise Exception("Redash login failed — check username/password in Valves")

        self._direct_logged_in = True
        return self._direct_session

    def _direct_get(self, path: str) -> dict:
        s = self._get_direct_session()
        r = s.get(f"{self.valves.REDASH_BASE_URL.rstrip('/')}{path}", timeout=30)
        r.raise_for_status()
        return r.json()

    def _direct_post(self, path: str, body: dict) -> dict:
        s = self._get_direct_session()
        s.headers["Content-Type"] = "application/json"
        r = s.post(f"{self.valves.REDASH_BASE_URL.rstrip('/')}{path}", json=body, timeout=120)
        r.raise_for_status()
        return r.json()

    def _direct_poll_job(self, job: dict) -> int | None:
        """Poll a Redash job until it completes. Returns query_result_id or None."""
        job_id = job.get("id")
        if not job_id:
            return None
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            data = self._direct_get(f"/api/jobs/{job_id}")
            j = data.get("job", {})
            if j.get("status") == 3:  # SUCCESS
                return j.get("query_result_id")
            if j.get("status") == 4:  # FAILURE
                raise Exception(f"Query failed: {j.get('error', 'unknown error')}")
            time.sleep(1)
        raise Exception(f"Job {job_id} timed out")

    def _direct_run_query(self, data_source_id: int, query: str) -> dict:
        """Execute query via native Redash API and return {columns, rows, metadata}."""
        data = self._direct_post("/api/query_results", {
            "data_source_id": data_source_id,
            "query": query,
            "max_age": 0,
        })
        job = data.get("job")
        if not job:
            raise Exception("No job in Redash response")
        qr_id = self._direct_poll_job(job)
        if qr_id is None:
            raise Exception("Query execution failed")
        # Fetch result
        result = self._direct_get(f"/api/query_results/{qr_id}.json")
        qr = result.get("query_result", result)
        data_block = qr.get("data", qr)
        if isinstance(data_block, dict):
            columns = data_block.get("columns", [])
            rows = data_block.get("rows", [])
        else:
            columns, rows = [], []
        return {
            "columns": columns,
            "rows": rows,
            "metadata": {"runtime": qr.get("runtime"), "row_count": len(rows)},
        }

    def _direct_list_data_sources(self) -> list:
        return self._direct_get("/api/data_sources")

    def _direct_get_schema(self, data_source_id: int) -> list:
        data = self._direct_get(f"/api/data_sources/{data_source_id}/schema")
        tables = data.get("schema", data) if isinstance(data, dict) else data
        result = []
        for t in tables:
            if isinstance(t, dict):
                cols = t.get("columns", [])
                normalized = [c if isinstance(c, str) else (c.get("name", str(c)) if isinstance(c, dict) else str(c)) for c in cols]
                result.append({"name": t.get("name", "?"), "columns": normalized})
        return result

    # ── Code Agents server helpers ─────────────────────────────────────

    def _ca_get(self, path: str) -> dict:
        r = requests.get(f"{self.valves.CODE_AGENTS_URL.rstrip('/')}{path}", timeout=30)
        r.raise_for_status()
        return r.json()

    def _ca_post(self, path: str, body: dict) -> dict:
        r = requests.post(f"{self.valves.CODE_AGENTS_URL.rstrip('/')}{path}", json=body, timeout=120)
        r.raise_for_status()
        return r.json()

    # ── Unified dispatch ───────────────────────────────────────────────

    def _use_code_agents(self) -> bool:
        """Check if Code Agents server is reachable."""
        if not self.valves.CODE_AGENTS_URL:
            return False
        try:
            requests.get(f"{self.valves.CODE_AGENTS_URL.rstrip('/')}/health", timeout=3)
            return True
        except Exception:
            return False

    # ── Public tool methods (called by the LLM) ───────────────────────

    def list_data_sources(self) -> str:
        """
        List all available Redash data sources (databases).
        Returns data source IDs, names, and types so you can pick the right one for queries.
        Call this first if the user hasn't specified which database to query.

        :return: List of data sources with id, name, and type
        """
        try:
            if self._use_code_agents():
                sources = self._ca_get("/redash/data-sources")
            else:
                sources = self._direct_list_data_sources()

            lines = ["| ID | Name | Type |", "|-----|------|------|"]
            for s in sources:
                lines.append(f"| {s.get('id', '?')} | {s.get('name', '?')} | {s.get('type', '?')} |")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing data sources: {e}"

    def get_schema(self, data_source_id: int) -> str:
        """
        Get the schema (tables and columns) for a specific Redash data source.
        Use this to understand what tables and columns are available before writing SQL.

        :param data_source_id: The Redash data source ID (get from list_data_sources)
        :return: List of tables with their column names
        """
        try:
            if self._use_code_agents():
                tables = self._ca_get(f"/redash/data-sources/{data_source_id}/schema")
            else:
                tables = self._direct_get_schema(data_source_id)

            lines = []
            for t in tables[:50]:
                name = t.get("name", "?") if isinstance(t, dict) else str(t)
                cols = t.get("columns", []) if isinstance(t, dict) else []
                col_str = ", ".join(str(c) for c in cols[:15])
                if len(cols) > 15:
                    col_str += f", ... (+{len(cols) - 15} more)"
                lines.append(f"**{name}**: {col_str}")
            if len(tables) > 50:
                lines.append(f"\n... and {len(tables) - 50} more tables")
            return "\n".join(lines)
        except Exception as e:
            return f"Error fetching schema: {e}"

    def run_query(self, data_source_id: int, query: str) -> str:
        """
        Execute a SQL query against a Redash data source and return the results.
        IMPORTANT: Only SELECT queries are allowed. Always include a LIMIT clause.

        :param data_source_id: The Redash data source ID to query
        :param query: The SQL SELECT query to execute (must include LIMIT)
        :return: Query results as a formatted table with columns and rows
        """
        # Safety check
        q_upper = query.strip().upper()
        if not q_upper.startswith(("SELECT", "SHOW", "DESCRIBE", "EXPLAIN")):
            return "ERROR: Only SELECT, SHOW, DESCRIBE, and EXPLAIN queries are allowed."

        for kw in ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE ", "CREATE ", "GRANT ", "REVOKE "]:
            if kw in q_upper:
                return f"ERROR: Query contains '{kw.strip()}' — only read-only queries allowed."

        # Add LIMIT if missing
        if "LIMIT" not in q_upper:
            query = f"{query.rstrip().rstrip(';')} LIMIT {self.valves.QUERY_ROW_LIMIT}"

        try:
            if self._use_code_agents():
                result = self._ca_post("/redash/run-query", {
                    "data_source_id": data_source_id,
                    "query": query,
                    "max_age": 0,
                })
            else:
                result = self._direct_run_query(data_source_id, query)

            return self._format_result(result)
        except Exception as e:
            return f"Query execution failed: {e}"

    def run_saved_query(self, query_id: int) -> str:
        """
        Execute a saved Redash query by its ID and return results.
        Use this when the user references a specific Redash query number.

        :param query_id: The saved Redash query ID
        :return: Query results as a formatted table
        """
        try:
            if self._use_code_agents():
                result = self._ca_post("/redash/run-saved-query", {
                    "query_id": query_id,
                    "max_age": 0,
                })
            else:
                # Direct: trigger saved query, poll, fetch
                data = self._direct_post(f"/api/queries/{query_id}/results", {"max_age": 0})
                job = data.get("job")
                if not job:
                    raise Exception("No job in response")
                qr_id = self._direct_poll_job(job)
                r = self._direct_get(f"/api/queries/{query_id}/results/{qr_id}.json")
                qr = r.get("query_result", {})
                db = qr.get("data", {})
                result = {
                    "columns": db.get("columns", []),
                    "rows": db.get("rows", []),
                    "metadata": {"runtime": qr.get("runtime"), "row_count": len(db.get("rows", []))},
                }

            return self._format_result(result)
        except Exception as e:
            return f"Saved query execution failed: {e}"

    # ── Formatting ─────────────────────────────────────────────────────

    def _format_result(self, result: dict) -> str:
        columns = result.get("columns", [])
        rows = result.get("rows", [])
        metadata = result.get("metadata", {})

        if not columns or not rows:
            rt = metadata.get("runtime", "?")
            return f"Query executed successfully. No rows returned. (runtime: {rt}s)"

        col_names = [c.get("name", c) if isinstance(c, dict) else str(c) for c in columns]
        lines = [
            f"**Results** ({metadata.get('row_count', len(rows))} rows, {metadata.get('runtime', '?')}s)\n",
            "| " + " | ".join(col_names) + " |",
            "| " + " | ".join(["---"] * len(col_names)) + " |",
        ]

        limit = self.valves.QUERY_ROW_LIMIT
        for row in rows[:limit]:
            vals = [str(row.get(c, "")) if isinstance(row, dict) else str(row) for c in col_names]
            vals = [v[:80] + "..." if len(v) > 80 else v for v in vals]
            lines.append("| " + " | ".join(vals) + " |")

        if len(rows) > limit:
            lines.append(f"\n*... {len(rows) - limit} more rows truncated*")

        return "\n".join(lines)
