"""Tests for code_agents.schema_designer."""

import pytest
from code_agents.api.schema_designer import SchemaDesigner, SchemaDesignerConfig, SchemaDesignResult, format_schema


class TestSchemaDesigner:
    def test_generates_table(self):
        result = SchemaDesigner().design([
            {"name": "User", "fields": {"name": "str", "email": "str"}}
        ])
        assert len(result.tables) == 1
        assert result.tables[0].name == "users"

    def test_auto_adds_primary_key(self):
        result = SchemaDesigner().design([{"name": "Item", "fields": {"title": "str"}}])
        col_names = [c.name for c in result.tables[0].columns]
        assert "id" in col_names

    def test_auto_adds_timestamps(self):
        result = SchemaDesigner(SchemaDesignerConfig(include_timestamps=True)).design([
            {"name": "Log", "fields": {"message": "text"}}
        ])
        col_names = [c.name for c in result.tables[0].columns]
        assert "created_at" in col_names
        assert "updated_at" in col_names

    def test_foreign_key(self):
        result = SchemaDesigner().design([
            {"name": "User", "fields": {"name": "str"}},
            {"name": "Order", "fields": {"user_id": "fk:User", "total": "decimal"}},
        ])
        order_table = next(t for t in result.tables if t.name == "orders")
        fk_col = next(c for c in order_table.columns if c.name == "user_id")
        assert fk_col.foreign_key == "users.id"
        assert fk_col.sql_type == "BIGINT"

    def test_enum_field(self):
        result = SchemaDesigner().design([
            {"name": "Task", "fields": {"status": "enum:pending,done,cancelled"}}
        ])
        status_col = next(c for c in result.tables[0].columns if c.name == "status")
        assert "VARCHAR" in status_col.sql_type
        assert status_col.default == "'pending'"

    def test_unique_email(self):
        result = SchemaDesigner().design([
            {"name": "Account", "fields": {"email": "str"}}
        ])
        email_col = next(c for c in result.tables[0].columns if c.name == "email")
        assert email_col.unique is True

    def test_generates_sql(self):
        result = SchemaDesigner().design([{"name": "User", "fields": {"name": "str"}}])
        assert "CREATE TABLE" in result.sql
        assert "users" in result.sql

    def test_generates_rollback(self):
        result = SchemaDesigner().design([{"name": "User", "fields": {"name": "str"}}])
        assert "DROP TABLE" in result.migration_down

    def test_soft_delete(self):
        result = SchemaDesigner(SchemaDesignerConfig(include_soft_delete=True)).design([
            {"name": "Post", "fields": {"title": "str"}}
        ])
        col_names = [c.name for c in result.tables[0].columns]
        assert "deleted_at" in col_names

    def test_format_output(self):
        result = SchemaDesignResult(summary="1 table")
        output = format_schema(result)
        assert "Schema Designer" in output
