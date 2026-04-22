"""
Postgres/DB client — safe query execution, schema inspection, migration generation.

Uses asyncpg for async PostgreSQL connections.
Config: DATABASE_URL or DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger("code_agents.db_client")


class DBError(Exception):
    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


# Write-operation keywords — used for safety gating
_WRITE_KEYWORDS = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


class DBClient:
    """Async PostgreSQL client with safety gates."""

    def __init__(
        self,
        database_url: str = "",
        host: str = "localhost",
        port: int = 5432,
        user: str = "",
        password: str = "",
        database: str = "",
        timeout: float = 30.0,
    ):
        self.database_url = database_url
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.timeout = timeout

    def _dsn(self, database: str = "") -> str:
        """Build connection DSN."""
        db = database or self.database
        if self.database_url:
            if database and "/" in self.database_url:
                # Replace database in URL
                base = self.database_url.rsplit("/", 1)[0]
                return f"{base}/{db}"
            return self.database_url
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{db}"

    async def _connect(self, database: str = ""):
        """Get an asyncpg connection."""
        try:
            import asyncpg
        except ImportError:
            raise DBError("asyncpg is not installed. Run: pip install asyncpg")
        dsn = self._dsn(database)
        try:
            return await asyncpg.connect(dsn, timeout=self.timeout)
        except Exception as e:
            raise DBError(f"Connection failed: {e}")

    # ── Database / Schema Discovery ──────────────────────────────────────

    async def list_databases(self) -> list[dict]:
        """List all databases."""
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT datname, pg_database_size(datname) as size_bytes "
                "FROM pg_database WHERE datistemplate = false ORDER BY datname"
            )
            return [{"name": r["datname"], "size_bytes": r["size_bytes"]} for r in rows]
        finally:
            await conn.close()

    async def list_schemas(self, database: str = "") -> list[dict]:
        """List schemas in a database."""
        conn = await self._connect(database)
        try:
            rows = await conn.fetch(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast') "
                "ORDER BY schema_name"
            )
            return [{"name": r["schema_name"]} for r in rows]
        finally:
            await conn.close()

    async def list_tables(self, database: str = "", schema: str = "public") -> list[dict]:
        """List tables in a schema with row estimates."""
        conn = await self._connect(database)
        try:
            rows = await conn.fetch(
                "SELECT t.table_name, "
                "  c.reltuples::bigint AS estimated_rows, "
                "  pg_total_relation_size(quote_ident(t.table_schema) || '.' || quote_ident(t.table_name)) AS size_bytes "
                "FROM information_schema.tables t "
                "JOIN pg_class c ON c.relname = t.table_name "
                "JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = t.table_schema "
                "WHERE t.table_schema = $1 AND t.table_type = 'BASE TABLE' "
                "ORDER BY t.table_name",
                schema,
            )
            return [
                {"name": r["table_name"], "estimated_rows": r["estimated_rows"], "size_bytes": r["size_bytes"]}
                for r in rows
            ]
        finally:
            await conn.close()

    async def table_info(self, table_name: str, database: str = "", schema: str = "public") -> dict:
        """Get detailed table info: columns, types, nullability, defaults."""
        conn = await self._connect(database)
        try:
            cols = await conn.fetch(
                "SELECT column_name, data_type, is_nullable, column_default, character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_schema = $1 AND table_name = $2 "
                "ORDER BY ordinal_position",
                schema, table_name,
            )
            return {
                "table": table_name,
                "schema": schema,
                "columns": [
                    {
                        "name": c["column_name"],
                        "type": c["data_type"],
                        "nullable": c["is_nullable"] == "YES",
                        "default": c["column_default"],
                        "max_length": c["character_maximum_length"],
                    }
                    for c in cols
                ],
            }
        finally:
            await conn.close()

    async def table_indexes(self, table_name: str, database: str = "") -> list[dict]:
        """List indexes on a table."""
        conn = await self._connect(database)
        try:
            rows = await conn.fetch(
                "SELECT indexname, indexdef, pg_relation_size(quote_ident(indexname)::regclass) AS size_bytes "
                "FROM pg_indexes WHERE tablename = $1 ORDER BY indexname",
                table_name,
            )
            return [
                {"name": r["indexname"], "definition": r["indexdef"], "size_bytes": r.get("size_bytes", 0)}
                for r in rows
            ]
        except Exception:
            # pg_relation_size may fail — close stale connection and get a fresh one
            await conn.close()
            conn = await self._connect(database)
            rows = await conn.fetch(
                "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = $1 ORDER BY indexname",
                table_name,
            )
            return [{"name": r["indexname"], "definition": r["indexdef"]} for r in rows]
        finally:
            await conn.close()

    async def table_constraints(self, table_name: str, database: str = "") -> list[dict]:
        """List constraints on a table."""
        conn = await self._connect(database)
        try:
            rows = await conn.fetch(
                "SELECT constraint_name, constraint_type "
                "FROM information_schema.table_constraints "
                "WHERE table_name = $1 ORDER BY constraint_name",
                table_name,
            )
            return [{"name": r["constraint_name"], "type": r["constraint_type"]} for r in rows]
        finally:
            await conn.close()

    async def table_size(self, table_name: str, database: str = "", schema: str = "public") -> dict:
        """Get table size details."""
        conn = await self._connect(database)
        try:
            fqn = f"{schema}.{table_name}"
            row = await conn.fetchrow(
                "SELECT "
                "  pg_total_relation_size($1) AS total_bytes, "
                "  pg_relation_size($1) AS table_bytes, "
                "  pg_indexes_size($1) AS indexes_bytes, "
                "  (SELECT reltuples::bigint FROM pg_class WHERE relname = $2) AS estimated_rows",
                fqn, table_name,
            )
            return {
                "table": table_name,
                "total_bytes": row["total_bytes"],
                "table_bytes": row["table_bytes"],
                "indexes_bytes": row["indexes_bytes"],
                "estimated_rows": row["estimated_rows"],
            }
        finally:
            await conn.close()

    # ── Query Execution ──────────────────────────────────────────────────

    async def execute_query(
        self, query: str, database: str = "", limit: int = 100, params: list | None = None
    ) -> dict:
        """Execute a SQL query with safety checks."""
        if _WRITE_KEYWORDS.match(query):
            raise DBError("Write operations require explicit approval. Use the write_query method.")

        # Ensure LIMIT — use parameterized value to prevent injection
        if limit and "LIMIT" not in query.upper():
            query = f"{query.rstrip(';')} LIMIT ${len(params or []) + 1}"
            params = list(params or []) + [limit]

        conn = await self._connect(database)
        try:
            rows = await conn.fetch(query, *(params or []))
            columns = list(rows[0].keys()) if rows else []
            data = [dict(r) for r in rows]
            # Convert non-serializable types to strings
            for row in data:
                for k, v in row.items():
                    if not isinstance(v, (str, int, float, bool, type(None), list, dict)):
                        row[k] = str(v)
            return {
                "columns": columns,
                "rows": data,
                "row_count": len(data),
                "truncated": len(data) == limit,
            }
        finally:
            await conn.close()

    async def write_query(self, query: str, database: str = "", params: list | None = None) -> dict:
        """Execute a write query (INSERT/UPDATE/DELETE/DDL). Caller must gate approval."""
        conn = await self._connect(database)
        try:
            result = await conn.execute(query, *(params or []))
            return {"status": "executed", "result": result}
        finally:
            await conn.close()

    # ── Explain ──────────────────────────────────────────────────────────

    async def explain(self, query: str, database: str = "", analyze: bool = False) -> dict:
        """Run EXPLAIN on a query."""
        explain_prefix = "EXPLAIN (FORMAT JSON, ANALYZE)" if analyze else "EXPLAIN (FORMAT JSON)"
        conn = await self._connect(database)
        try:
            rows = await conn.fetch(f"{explain_prefix} {query}")
            plan = rows[0][0] if rows else {}
            return {"query": query, "plan": plan, "analyzed": analyze}
        finally:
            await conn.close()

    # ── Activity ─────────────────────────────────────────────────────────

    async def active_queries(self, database: str = "") -> list[dict]:
        """List active queries (pg_stat_activity)."""
        conn = await self._connect(database)
        try:
            rows = await conn.fetch(
                "SELECT pid, usename, application_name, state, query, "
                "  now() - query_start AS duration, wait_event_type, wait_event "
                "FROM pg_stat_activity "
                "WHERE state != 'idle' AND pid != pg_backend_pid() "
                "ORDER BY query_start"
            )
            return [
                {
                    "pid": r["pid"],
                    "user": r["usename"],
                    "app": r["application_name"],
                    "state": r["state"],
                    "query": r["query"][:500] if r["query"] else "",
                    "duration": str(r["duration"]),
                    "wait_event": r["wait_event"],
                }
                for r in rows
            ]
        finally:
            await conn.close()
