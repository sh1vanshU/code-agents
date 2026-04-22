"""
Postgres/DB: safe query execution, schema inspection, explain plans.

Requires DATABASE_URL or DB_HOST/DB_PORT/DB_USER/DB_PASSWORD to be set.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..cicd.db_client import DBClient, DBError

logger = logging.getLogger("code_agents.routers.db")
router = APIRouter(prefix="/db", tags=["database"])


def _get_client() -> DBClient:
    """Build DBClient from environment variables."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return DBClient(database_url=database_url)
    host = os.getenv("DB_HOST")
    if not host:
        raise HTTPException(status_code=503, detail="DATABASE_URL or DB_HOST is not set.")
    return DBClient(
        host=host,
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", ""),
    )


# ── Models ────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    database: str = Field(default="", description="Database name")
    query: str = Field(description="SQL query to execute")
    limit: int = Field(default=100, ge=1, le=1000, description="Row limit")


class ExplainRequest(BaseModel):
    database: str = Field(default="", description="Database name")
    query: str = Field(description="SQL query to explain")
    analyze: bool = Field(default=False, description="Run EXPLAIN ANALYZE (actually executes the query)")


class WriteQueryRequest(BaseModel):
    database: str = Field(default="", description="Database name")
    query: str = Field(description="SQL write query")


class MigrationRequest(BaseModel):
    database: str = Field(default="", description="Database name")
    description: str = Field(description="Migration description in natural language")
    changes: list[str] = Field(default_factory=list, description="List of SQL statements for the migration")


class SchemaDiffRequest(BaseModel):
    database: str = Field(default="", description="Database name")
    schema_a: str = Field(default="public", description="First schema to compare")
    schema_b: str = Field(description="Second schema to compare")


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("/databases")
async def list_databases():
    """List all databases."""
    client = _get_client()
    try:
        dbs = await client.list_databases()
        return {"total": len(dbs), "databases": dbs}
    except DBError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/schemas")
async def list_schemas(database: str = Query(default="", description="Database name")):
    """List schemas in a database."""
    client = _get_client()
    try:
        schemas = await client.list_schemas(database=database)
        return {"total": len(schemas), "schemas": schemas}
    except DBError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tables")
async def list_tables(
    database: str = Query(default="", description="Database name"),
    schema: str = Query(default="public", description="Schema name"),
):
    """List tables in a schema."""
    client = _get_client()
    try:
        tables = await client.list_tables(database=database, schema=schema)
        return {"total": len(tables), "tables": tables}
    except DBError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tables/{table_name}")
async def get_table_info(
    table_name: str,
    database: str = Query(default="", description="Database name"),
    schema: str = Query(default="public", description="Schema name"),
):
    """Get detailed table info: columns, types, defaults."""
    client = _get_client()
    try:
        return await client.table_info(table_name, database=database, schema=schema)
    except DBError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tables/{table_name}/indexes")
async def get_table_indexes(
    table_name: str,
    database: str = Query(default="", description="Database name"),
):
    """List indexes on a table."""
    client = _get_client()
    try:
        indexes = await client.table_indexes(table_name, database=database)
        return {"total": len(indexes), "indexes": indexes}
    except DBError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tables/{table_name}/constraints")
async def get_table_constraints(
    table_name: str,
    database: str = Query(default="", description="Database name"),
):
    """List constraints on a table."""
    client = _get_client()
    try:
        constraints = await client.table_constraints(table_name, database=database)
        return {"total": len(constraints), "constraints": constraints}
    except DBError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tables/{table_name}/size")
async def get_table_size(
    table_name: str,
    database: str = Query(default="", description="Database name"),
    schema: str = Query(default="public", description="Schema name"),
):
    """Get table size details."""
    client = _get_client()
    try:
        return await client.table_size(table_name, database=database, schema=schema)
    except DBError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/query")
async def execute_query(req: QueryRequest):
    """Execute a read-only SQL query."""
    logger.info("DB query: database=%s, query_length=%d", req.database, len(req.query))
    client = _get_client()
    try:
        return await client.execute_query(query=req.query, database=req.database, limit=req.limit)
    except DBError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/query/write")
async def execute_write_query(req: WriteQueryRequest):
    """Execute a write SQL query (INSERT/UPDATE/DELETE/DDL). Use with caution."""
    logger.warning("DB write query: database=%s, query_length=%d", req.database, len(req.query))
    client = _get_client()
    try:
        return await client.write_query(query=req.query, database=req.database)
    except DBError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/explain")
async def explain_query(req: ExplainRequest):
    """Run EXPLAIN on a SQL query."""
    client = _get_client()
    try:
        return await client.explain(query=req.query, database=req.database, analyze=req.analyze)
    except DBError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/activity")
async def active_queries(database: str = Query(default="", description="Database name")):
    """List active queries (pg_stat_activity)."""
    client = _get_client()
    try:
        queries = await client.active_queries(database=database)
        return {"total": len(queries), "queries": queries}
    except DBError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/schema-diff")
async def schema_diff(req: SchemaDiffRequest):
    """Compare two schemas and report differences."""
    client = _get_client()
    try:
        tables_a = await client.list_tables(database=req.database, schema=req.schema_a)
        tables_b = await client.list_tables(database=req.database, schema=req.schema_b)

        names_a = {t["name"] for t in tables_a}
        names_b = {t["name"] for t in tables_b}

        return {
            "schema_a": req.schema_a,
            "schema_b": req.schema_b,
            "only_in_a": sorted(names_a - names_b),
            "only_in_b": sorted(names_b - names_a),
            "in_both": sorted(names_a & names_b),
            "tables_a_count": len(tables_a),
            "tables_b_count": len(tables_b),
        }
    except DBError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
