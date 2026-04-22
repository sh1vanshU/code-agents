"""Tests for Migration Generator."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.knowledge.migration_gen import (
    ColumnSpec,
    MigrationGenerator,
    MigrationOutput,
    MigrationSpec,
    format_migration,
)


class TestMigrationGenerator:
    """Tests for MigrationGenerator."""

    def test_init_defaults(self):
        gen = MigrationGenerator()
        assert gen.migration_type in ("raw", "alembic", "django", "flyway")

    def test_detect_type_raw(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = MigrationGenerator(cwd=tmpdir)
            assert gen.migration_type == "raw"

    def test_detect_type_alembic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "alembic.ini")).write_text("[alembic]")
            gen = MigrationGenerator(cwd=tmpdir, migration_type="auto")
            assert gen.migration_type == "alembic"

    def test_detect_type_django(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "manage.py")).write_text("#!/usr/bin/env python")
            gen = MigrationGenerator(cwd=tmpdir, migration_type="auto")
            assert gen.migration_type == "django"

    def test_parse_add_column(self):
        gen = MigrationGenerator()
        spec = gen._parse_description("add expires_at to sessions as timestamp")
        assert spec.operation == "add_column"
        assert spec.table == "sessions"
        assert spec.columns[0].name == "expires_at"
        assert spec.columns[0].data_type == "TIMESTAMP"

    def test_parse_add_column_default_type(self):
        gen = MigrationGenerator()
        spec = gen._parse_description("add email to users")
        assert spec.operation == "add_column"
        assert spec.table == "users"
        assert spec.columns[0].data_type == "VARCHAR(255)"

    def test_parse_drop_column(self):
        gen = MigrationGenerator()
        spec = gen._parse_description("drop column temp_flag from users")
        assert spec.operation == "drop_column"
        assert spec.table == "users"
        assert spec.columns[0].name == "temp_flag"

    def test_parse_rename_column(self):
        gen = MigrationGenerator()
        spec = gen._parse_description("rename name to full_name in users")
        assert spec.operation == "rename_column"
        assert spec.table == "users"
        assert spec.old_name == "name"
        assert spec.new_name == "full_name"

    def test_parse_create_table(self):
        gen = MigrationGenerator()
        spec = gen._parse_description("create table payments")
        assert spec.operation == "create_table"
        assert spec.table == "payments"
        assert len(spec.columns) >= 3  # id, created_at, updated_at

    def test_parse_add_index(self):
        gen = MigrationGenerator()
        spec = gen._parse_description("index on users(email, name)")
        assert spec.operation == "add_index"
        assert spec.table == "users"
        assert "email" in spec.index_columns
        assert "name" in spec.index_columns

    def test_parse_unparseable(self):
        gen = MigrationGenerator()
        spec = gen._parse_description("something random")
        assert spec.operation == ""

    def test_generate_raw_add_column(self):
        gen = MigrationGenerator(migration_type="raw")
        output = gen.generate("add email to users as string")
        assert "ALTER TABLE" in output.migration_sql
        assert "ADD COLUMN email" in output.migration_sql
        assert "DROP COLUMN email" in output.rollback_sql

    def test_generate_raw_create_table(self):
        gen = MigrationGenerator(migration_type="raw")
        output = gen.generate("create table orders")
        assert "CREATE TABLE orders" in output.migration_sql
        assert "DROP TABLE" in output.rollback_sql

    def test_generate_raw_rename(self):
        gen = MigrationGenerator(migration_type="raw")
        output = gen.generate("rename name to full_name in users")
        assert "RENAME COLUMN" in output.migration_sql

    def test_generate_alembic(self):
        gen = MigrationGenerator(migration_type="alembic")
        output = gen.generate("add email to users")
        assert "op.add_column" in output.migration_sql
        assert "op.drop_column" in output.migration_sql  # In downgrade

    def test_generate_django(self):
        gen = MigrationGenerator(migration_type="django")
        output = gen.generate("add email to users")
        assert "migrations.AddField" in output.migration_sql

    def test_generate_unparseable(self):
        gen = MigrationGenerator(migration_type="raw")
        output = gen.generate("blah blah blah")
        assert "Could not parse" in output.migration_sql

    def test_suggest_model_changes(self):
        gen = MigrationGenerator()
        spec = MigrationSpec(operation="add_column", table="users",
                             columns=[ColumnSpec(name="email", data_type="VARCHAR(255)")])
        changes = gen._suggest_model_changes(spec)
        assert any("email" in c for c in changes)

    def test_migration_path(self):
        gen = MigrationGenerator(migration_type="raw")
        spec = MigrationSpec(operation="add_column", table="users")
        path = gen._get_migration_path(spec)
        assert "migrations" in path
        assert "add_column_users" in path


class TestFormatMigration:
    """Tests for format_migration."""

    def test_format_output(self):
        output = MigrationOutput(
            migration_sql="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
            rollback_sql="ALTER TABLE users DROP COLUMN email;",
            migration_path="migrations/001.sql",
            model_changes=["Add email to User model"],
            blast_radius=["src/models.py"],
            migration_type="raw",
            detected_orm="sqlalchemy",
            spec=MigrationSpec(operation="add_column", table="users"),
        )
        text = format_migration(output)
        assert "ALTER TABLE" in text
        assert "Model Changes" in text
        assert "Blast Radius" in text
