"""Tests for db_client.py — unit tests with mocked asyncpg."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.cicd.db_client import DBClient, DBError, _WRITE_KEYWORDS


class TestDBClientInit:
    def test_defaults(self):
        c = DBClient()
        assert c.database_url == ""
        assert c.host == "localhost"
        assert c.port == 5432
        assert c.timeout == 30.0

    def test_with_url(self):
        c = DBClient(database_url="postgresql://user:pass@host:5432/db")
        assert c.database_url == "postgresql://user:pass@host:5432/db"

    def test_with_components(self):
        c = DBClient(host="db.example.com", port=5433, user="admin", password="secret", database="mydb")
        assert c.host == "db.example.com"
        assert c.port == 5433
        assert c.database == "mydb"


class TestDBClientDSN:
    def test_dsn_from_url(self):
        c = DBClient(database_url="postgresql://user:pass@host:5432/db")
        assert c._dsn() == "postgresql://user:pass@host:5432/db"

    def test_dsn_from_url_with_override(self):
        c = DBClient(database_url="postgresql://user:pass@host:5432/db")
        assert c._dsn("other_db") == "postgresql://user:pass@host:5432/other_db"

    def test_dsn_from_components(self):
        c = DBClient(host="localhost", port=5432, user="u", password="p", database="mydb")
        assert c._dsn() == "postgresql://u:p@localhost:5432/mydb"


class TestWriteKeywords:
    def test_detects_insert(self):
        assert _WRITE_KEYWORDS.match("INSERT INTO users VALUES (1)")

    def test_detects_update(self):
        assert _WRITE_KEYWORDS.match("UPDATE users SET name = 'x'")

    def test_detects_delete(self):
        assert _WRITE_KEYWORDS.match("DELETE FROM users WHERE id = 1")

    def test_detects_drop(self):
        assert _WRITE_KEYWORDS.match("DROP TABLE users")

    def test_detects_alter(self):
        assert _WRITE_KEYWORDS.match("ALTER TABLE users ADD COLUMN email TEXT")

    def test_allows_select(self):
        assert _WRITE_KEYWORDS.match("SELECT * FROM users") is None

    def test_case_insensitive(self):
        assert _WRITE_KEYWORDS.match("  insert into users values (1)")

    def test_allows_explain(self):
        assert _WRITE_KEYWORDS.match("EXPLAIN SELECT * FROM users") is None


class TestExecuteQuery:
    def _make_client(self):
        return DBClient(database_url="postgresql://u:p@localhost:5432/test")

    def test_write_blocked(self):
        c = self._make_client()
        with pytest.raises(DBError, match="Write operations"):
            asyncio.run(c.execute_query("DELETE FROM users WHERE id = 1"))

    def test_adds_limit(self):
        c = self._make_client()
        # Mock asyncpg connect
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.close = AsyncMock()
        with patch.object(c, "_connect", return_value=mock_conn):
            result = asyncio.run(c.execute_query("SELECT * FROM users"))
            # Check that LIMIT was added
            call_args = mock_conn.fetch.call_args[0][0]
            assert "LIMIT" in call_args
            assert result["row_count"] == 0

    def test_preserves_existing_limit(self):
        c = self._make_client()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.close = AsyncMock()
        with patch.object(c, "_connect", return_value=mock_conn):
            asyncio.run(c.execute_query("SELECT * FROM users LIMIT 50"))
            call_args = mock_conn.fetch.call_args[0][0]
            assert call_args.count("LIMIT") == 1


class TestExplain:
    def test_explain_no_analyze(self):
        c = DBClient(database_url="postgresql://u:p@localhost:5432/test")
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[MagicMock(__getitem__=lambda self, k: [{"Plan": {}}])])
        mock_conn.close = AsyncMock()
        with patch.object(c, "_connect", return_value=mock_conn):
            result = asyncio.run(c.explain("SELECT 1"))
            assert result["analyzed"] is False
            call_args = mock_conn.fetch.call_args[0][0]
            assert "ANALYZE" not in call_args

    def test_explain_with_analyze(self):
        c = DBClient(database_url="postgresql://u:p@localhost:5432/test")
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[MagicMock(__getitem__=lambda self, k: [{"Plan": {}}])])
        mock_conn.close = AsyncMock()
        with patch.object(c, "_connect", return_value=mock_conn):
            result = asyncio.run(c.explain("SELECT 1", analyze=True))
            assert result["analyzed"] is True
            call_args = mock_conn.fetch.call_args[0][0]
            assert "ANALYZE" in call_args


class TestListDatabases:
    def test_success(self):
        c = DBClient(database_url="postgresql://u:p@localhost:5432/test")
        mock_conn = AsyncMock()
        mock_rows = [
            {"datname": "app_db", "size_bytes": 1000000},
            {"datname": "analytics", "size_bytes": 5000000},
        ]
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_conn.close = AsyncMock()
        with patch.object(c, "_connect", return_value=mock_conn):
            result = asyncio.run(c.list_databases())
            assert len(result) == 2
            assert result[0]["name"] == "app_db"


class TestTableInfo:
    def test_success(self):
        c = DBClient(database_url="postgresql://u:p@localhost:5432/test")
        mock_conn = AsyncMock()
        mock_cols = [
            {"column_name": "id", "data_type": "integer", "is_nullable": "NO", "column_default": None, "character_maximum_length": None},
            {"column_name": "name", "data_type": "character varying", "is_nullable": "YES", "column_default": None, "character_maximum_length": 255},
        ]
        mock_conn.fetch = AsyncMock(return_value=mock_cols)
        mock_conn.close = AsyncMock()
        with patch.object(c, "_connect", return_value=mock_conn):
            result = asyncio.run(c.table_info("users"))
            assert result["table"] == "users"
            assert len(result["columns"]) == 2
            assert result["columns"][0]["name"] == "id"
            assert result["columns"][0]["nullable"] is False
            assert result["columns"][1]["nullable"] is True
