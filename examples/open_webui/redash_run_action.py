"""
title: Run SQL Query
description: Adds a "Run" button to assistant messages containing SQL queries. Click to execute the query via Redash and get results summarized by the agent.
author: code-agents
version: 0.2.0
license: MIT
"""

import re
import time
import requests
from pydantic import BaseModel, Field
from typing import Optional


class Action:
    class Valves(BaseModel):
        CODE_AGENTS_URL: str = Field(
            default="http://localhost:8000",
            description="Code Agents server URL (Redash endpoints under /redash/)",
        )
        REDASH_BASE_URL: str = Field(
            default="",
            description="Direct Redash URL (fallback if Code Agents is not running)",
        )
        REDASH_API_KEY: str = Field(
            default="",
            description="Redash API key (for direct mode)",
        )
        REDASH_USERNAME: str = Field(
            default="",
            description="Redash username (for direct mode)",
        )
        REDASH_PASSWORD: str = Field(
            default="",
            description="Redash password (for direct mode)",
        )
        DEFAULT_DATA_SOURCE_ID: int = Field(
            default=70,
            description="Default data source ID when not specified in the query context",
        )

    def __init__(self):
        self.valves = self.Valves()
        self._session = None

    def _get_direct_session(self) -> requests.Session:
        if self._session is not None:
            return self._session
        self._session = requests.Session()
        if self.valves.REDASH_API_KEY:
            self._session.headers["Authorization"] = f"Key {self.valves.REDASH_API_KEY}"
        elif self.valves.REDASH_USERNAME and self.valves.REDASH_PASSWORD:
            resp = self._session.post(
                f"{self.valves.REDASH_BASE_URL.rstrip('/')}/login",
                data={"email": self.valves.REDASH_USERNAME, "password": self.valves.REDASH_PASSWORD},
                allow_redirects=True,
                timeout=15,
            )
            if resp.status_code != 200 or "/login" in resp.url:
                raise Exception("Redash login failed")
        return self._session

    def _execute_query(self, data_source_id: int, query: str) -> dict:
        """Execute query, trying Code Agents server first, then direct Redash."""
        # Try Code Agents server
        if self.valves.CODE_AGENTS_URL:
            try:
                resp = requests.post(
                    f"{self.valves.CODE_AGENTS_URL.rstrip('/')}/redash/run-query",
                    json={"data_source_id": data_source_id, "query": query, "max_age": 0},
                    timeout=120,
                )
                resp.raise_for_status()
                return resp.json()
            except requests.ConnectionError:
                pass

        # Direct Redash fallback — must submit, poll job, then fetch result
        if self.valves.REDASH_BASE_URL:
            session = self._get_direct_session()
            base = self.valves.REDASH_BASE_URL.rstrip("/")
            session.headers["Content-Type"] = "application/json"

            # Submit query
            resp = session.post(
                f"{base}/api/query_results",
                json={"data_source_id": data_source_id, "query": query, "max_age": 0},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            job = data.get("job")
            if not job or not job.get("id"):
                raise Exception("No job in Redash response")

            # Poll until done
            job_id = job["id"]
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                jr = session.get(f"{base}/api/jobs/{job_id}", timeout=30)
                jr.raise_for_status()
                j = jr.json().get("job", {})
                if j.get("status") == 3:  # SUCCESS
                    qr_id = j.get("query_result_id")
                    break
                if j.get("status") == 4:  # FAILURE
                    raise Exception(f"Query failed: {j.get('error', 'unknown')}")
                time.sleep(1)
            else:
                raise Exception("Query timed out")

            # Fetch result
            rr = session.get(f"{base}/api/query_results/{qr_id}.json", timeout=30)
            rr.raise_for_status()
            result = rr.json()
            qr = result.get("query_result", result)
            db = qr.get("data", qr)
            return {
                "columns": db.get("columns", []) if isinstance(db, dict) else [],
                "rows": db.get("rows", []) if isinstance(db, dict) else [],
                "metadata": {"runtime": qr.get("runtime"), "row_count": len(db.get("rows", []) if isinstance(db, dict) else [])},
            }

        raise Exception("No Redash connection configured in Action Valves")

    def _extract_sql(self, text: str) -> Optional[str]:
        """Extract SQL query from assistant message text."""
        # Try ```sql code blocks first
        sql_blocks = re.findall(r"```sql\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if sql_blocks:
            return sql_blocks[-1].strip()

        # Try generic ``` code blocks that look like SQL
        code_blocks = re.findall(r"```\s*\n(.*?)```", text, re.DOTALL)
        for block in reversed(code_blocks):
            block = block.strip()
            if block.upper().startswith(("SELECT", "SHOW", "DESCRIBE", "EXPLAIN")):
                return block

        # Try inline SQL — look for SELECT statements anywhere in a line
        for line in reversed(text.split("\n")):
            line = line.strip()
            # Line starts with SELECT
            if line.upper().startswith("SELECT") and len(line) > 15:
                return line
            # SELECT embedded after a prefix like "run: SELECT ..." or ": SELECT ..."
            m = re.search(r"(?:^|[:\-\s])(SELECT\s.{15,})", line, re.IGNORECASE)
            if m:
                return m.group(1).strip()

        return None

    def _extract_data_source_id(self, text: str) -> int:
        """Try to extract data_source_id from context, fall back to default."""
        patterns = [
            r"data_source_id[:\s=]+(\d+)",
            r"data source (?:id[:\s=]+)?(\d+)",
            r"id=(\d+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return self.valves.DEFAULT_DATA_SOURCE_ID

    def _format_results(self, result: dict) -> str:
        """Format query results as readable markdown."""
        columns = result.get("columns", [])
        rows = result.get("rows", [])
        metadata = result.get("metadata", {})

        if not columns and not rows:
            return "Query executed successfully. No rows returned."

        col_names = [c.get("name", c) if isinstance(c, dict) else str(c) for c in columns]

        lines = [
            f"**Query Results** ({metadata.get('row_count', len(rows))} rows, "
            f"runtime: {metadata.get('runtime', '?')}s)\n",
            "| " + " | ".join(col_names) + " |",
            "| " + " | ".join(["---"] * len(col_names)) + " |",
        ]

        for row in rows[:200]:
            vals = []
            for c in col_names:
                v = str(row.get(c, "")) if isinstance(row, dict) else str(row)
                if len(v) > 60:
                    v = v[:60] + "..."
                vals.append(v)
            lines.append("| " + " | ".join(vals) + " |")

        if len(rows) > 200:
            lines.append(f"\n*... {len(rows) - 200} more rows truncated*")

        return "\n".join(lines)

    async def action(
        self,
        body: dict,
        __user__: dict = None,
        __event_emitter__=None,
    ) -> Optional[dict]:
        """
        Run button action: extracts SQL from the last assistant message,
        executes it via Redash, and sends results back to the conversation.
        """
        if __event_emitter__ is None:
            return None

        messages = body.get("messages", [])

        # Find the last assistant message
        assistant_msg = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                assistant_msg = msg.get("content", "")
                break

        if not assistant_msg:
            await __event_emitter__(
                {"type": "status", "data": {"description": "No assistant message found", "done": True}}
            )
            return None

        # Extract SQL
        sql = self._extract_sql(assistant_msg)
        if not sql:
            await __event_emitter__(
                {"type": "status", "data": {"description": "No SQL query found in the message", "done": True}}
            )
            return None

        # Safety check
        q_upper = sql.strip().upper()
        if not q_upper.startswith(("SELECT", "SHOW", "DESCRIBE", "EXPLAIN")):
            await __event_emitter__(
                {"type": "status", "data": {"description": "Only SELECT/SHOW/DESCRIBE/EXPLAIN allowed", "done": True}}
            )
            return None

        for kw in ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE "]:
            if kw in q_upper:
                await __event_emitter__(
                    {"type": "status", "data": {"description": f"Blocked: contains {kw.strip()}", "done": True}}
                )
                return None

        # Add LIMIT if missing
        if "LIMIT" not in q_upper:
            sql = f"{sql.rstrip().rstrip(';')} LIMIT 100"

        # Get data source ID
        full_context = " ".join(m.get("content", "") for m in messages)
        ds_id = self._extract_data_source_id(full_context)

        # Execute
        await __event_emitter__(
            {"type": "status", "data": {"description": f"Running query on data source {ds_id}...", "done": False}}
        )

        try:
            result = self._execute_query(ds_id, sql)
            formatted = self._format_results(result)

            await __event_emitter__(
                {"type": "status", "data": {"description": "Query complete", "done": True}}
            )

            await __event_emitter__(
                {
                    "type": "message",
                    "data": {
                        "content": f"\n\n---\n**Executed SQL:**\n```sql\n{sql}\n```\n\n{formatted}\n\n---\n*Please summarize these results.*\n"
                    },
                }
            )

        except Exception as e:
            await __event_emitter__(
                {"type": "status", "data": {"description": f"Query failed: {e}", "done": True}}
            )
            await __event_emitter__(
                {
                    "type": "message",
                    "data": {"content": f"\n\n---\n**Query failed:**\n```\n{e}\n```\n\nPlease fix the query and suggest a corrected version.\n"},
                }
            )

        return None
