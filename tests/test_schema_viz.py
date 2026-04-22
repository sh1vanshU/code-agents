"""Tests for code_agents.schema_viz — database schema visualizer."""

from __future__ import annotations

import pytest

from code_agents.api.schema_viz import (
    ColumnInfo,
    ForeignKey,
    SchemaResult,
    SchemaVisualizer,
    TableSchema,
    format_schema_summary,
)


# ── Fixtures ────────────────────────────────────────────────────────────


SIMPLE_SQL = """
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(100) DEFAULT 'anonymous',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'pending',
    amount DECIMAL(10, 2),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    quantity INTEGER DEFAULT 1,
    price DECIMAL(10, 2),
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
"""

QUOTED_SQL = """
CREATE TABLE IF NOT EXISTS "public"."payments" (
    "id" BIGSERIAL PRIMARY KEY,
    "order_id" INTEGER NOT NULL REFERENCES orders(id),
    "amount" DECIMAL(12, 2) NOT NULL,
    "currency" VARCHAR(3) DEFAULT 'INR'
);
"""

COMPOSITE_PK_SQL = """
CREATE TABLE user_roles (
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    granted_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""


@pytest.fixture
def viz():
    return SchemaVisualizer()


@pytest.fixture
def simple_result(viz):
    return viz.scan_from_sql(SIMPLE_SQL)


@pytest.fixture
def sample_result():
    """Hand-built SchemaResult for output tests."""
    users = TableSchema(
        name="users",
        columns=[
            ColumnInfo("id", "integer", nullable=False, primary_key=True),
            ColumnInfo("email", "varchar(255)", nullable=False),
            ColumnInfo("name", "varchar(100)", nullable=True, default="'anonymous'"),
        ],
        primary_key=["id"],
        foreign_keys=[],
        indexes=["users_pkey", "users_email_idx"],
        row_count=15000,
        size_bytes=2048000,
    )
    orders = TableSchema(
        name="orders",
        columns=[
            ColumnInfo("id", "integer", nullable=False, primary_key=True),
            ColumnInfo("user_id", "integer", nullable=False),
            ColumnInfo("status", "varchar(20)", nullable=True, default="'pending'"),
            ColumnInfo("amount", "decimal(10,2)", nullable=True),
        ],
        primary_key=["id"],
        foreign_keys=[ForeignKey("user_id", "users", "id")],
        indexes=["orders_pkey"],
        row_count=50000,
        size_bytes=8192000,
    )
    fks = [ForeignKey("user_id", "users", "id")]
    return SchemaResult(tables=[users, orders], relationships=fks, database="testdb", schema="public")


# ── TestParseSql ────────────────────────────────────────────────────────


class TestParseSql:
    """CREATE TABLE parsing tests."""

    def test_parses_correct_number_of_tables(self, simple_result):
        assert len(simple_result.tables) == 3

    def test_table_names(self, simple_result):
        names = [t.name for t in simple_result.tables]
        assert "users" in names
        assert "orders" in names
        assert "order_items" in names

    def test_column_count(self, simple_result):
        users = next(t for t in simple_result.tables if t.name == "users")
        assert len(users.columns) == 4

    def test_column_types(self, simple_result):
        users = next(t for t in simple_result.tables if t.name == "users")
        email_col = next(c for c in users.columns if c.name == "email")
        assert "VARCHAR" in email_col.data_type.upper() or "varchar" in email_col.data_type.lower()

    def test_primary_key_detected(self, simple_result):
        users = next(t for t in simple_result.tables if t.name == "users")
        id_col = next(c for c in users.columns if c.name == "id")
        assert id_col.primary_key is True

    def test_not_null_detected(self, simple_result):
        users = next(t for t in simple_result.tables if t.name == "users")
        email_col = next(c for c in users.columns if c.name == "email")
        assert email_col.nullable is False

    def test_nullable_detected(self, simple_result):
        orders = next(t for t in simple_result.tables if t.name == "orders")
        amount_col = next(c for c in orders.columns if c.name == "amount")
        assert amount_col.nullable is True

    def test_default_value(self, simple_result):
        orders = next(t for t in simple_result.tables if t.name == "orders")
        status_col = next(c for c in orders.columns if c.name == "status")
        assert "pending" in status_col.default

    def test_quoted_identifiers(self, viz):
        result = viz.scan_from_sql(QUOTED_SQL)
        assert len(result.tables) == 1
        assert result.tables[0].name == "payments"

    def test_if_not_exists(self, viz):
        result = viz.scan_from_sql(QUOTED_SQL)
        assert result.tables[0].name == "payments"
        assert len(result.tables[0].columns) == 4

    def test_composite_primary_key(self, viz):
        result = viz.scan_from_sql(COMPOSITE_PK_SQL)
        tbl = result.tables[0]
        assert "user_id" in tbl.primary_key
        assert "role_id" in tbl.primary_key

    def test_empty_sql(self, viz):
        result = viz.scan_from_sql("")
        assert result.tables == []
        assert result.relationships == []

    def test_database_label_for_sql(self, simple_result):
        assert simple_result.database == "(sql-file)"


# ── TestForeignKeys ─────────────────────────────────────────────────────


class TestForeignKeys:
    """Relationship extraction tests."""

    def test_inline_references_detected(self, simple_result):
        orders = next(t for t in simple_result.tables if t.name == "orders")
        assert len(orders.foreign_keys) == 1
        fk = orders.foreign_keys[0]
        assert fk.column == "user_id"
        assert fk.references_table == "users"
        assert fk.references_column == "id"

    def test_table_level_foreign_key(self, simple_result):
        items = next(t for t in simple_result.tables if t.name == "order_items")
        assert len(items.foreign_keys) == 1
        fk = items.foreign_keys[0]
        assert fk.column == "order_id"
        assert fk.references_table == "orders"
        assert fk.references_column == "id"

    def test_all_relationships_collected(self, simple_result):
        assert len(simple_result.relationships) == 2

    def test_composite_pk_with_fk(self, viz):
        result = viz.scan_from_sql(COMPOSITE_PK_SQL)
        tbl = result.tables[0]
        assert len(tbl.foreign_keys) == 1
        assert tbl.foreign_keys[0].column == "user_id"

    def test_quoted_fk(self, viz):
        result = viz.scan_from_sql(QUOTED_SQL)
        tbl = result.tables[0]
        assert len(tbl.foreign_keys) == 1
        assert tbl.foreign_keys[0].references_table == "orders"


# ── TestMermaid ─────────────────────────────────────────────────────────


class TestMermaid:
    """Mermaid erDiagram output tests."""

    def test_starts_with_erdiagram(self, viz, sample_result):
        mermaid = viz.generate_mermaid(sample_result)
        assert mermaid.startswith("erDiagram")

    def test_contains_table_definitions(self, viz, sample_result):
        mermaid = viz.generate_mermaid(sample_result)
        assert "users {" in mermaid
        assert "orders {" in mermaid

    def test_contains_pk_tag(self, viz, sample_result):
        mermaid = viz.generate_mermaid(sample_result)
        assert "PK" in mermaid

    def test_contains_fk_tag(self, viz, sample_result):
        mermaid = viz.generate_mermaid(sample_result)
        assert "FK" in mermaid

    def test_contains_relationship(self, viz, sample_result):
        mermaid = viz.generate_mermaid(sample_result)
        assert "||--o{" in mermaid

    def test_contains_column_types(self, viz, sample_result):
        mermaid = viz.generate_mermaid(sample_result)
        # Types should appear (underscored for spaces)
        assert "integer" in mermaid or "varchar" in mermaid

    def test_relationship_label(self, viz, sample_result):
        mermaid = viz.generate_mermaid(sample_result)
        assert "user_id" in mermaid

    def test_empty_schema(self, viz):
        empty = SchemaResult(tables=[], relationships=[], database="empty", schema="public")
        mermaid = viz.generate_mermaid(empty)
        assert mermaid.strip() == "erDiagram"


# ── TestTerminal ────────────────────────────────────────────────────────


class TestTerminal:
    """ASCII table output tests."""

    def test_contains_database_name(self, viz, sample_result):
        term = viz.generate_terminal(sample_result)
        assert "testdb" in term

    def test_contains_table_names(self, viz, sample_result):
        term = viz.generate_terminal(sample_result)
        assert "users" in term
        assert "orders" in term

    def test_contains_column_header(self, viz, sample_result):
        term = viz.generate_terminal(sample_result)
        assert "Column" in term
        assert "Type" in term

    def test_contains_row_count(self, viz, sample_result):
        term = viz.generate_terminal(sample_result)
        assert "15,000" in term

    def test_contains_pk_marker(self, viz, sample_result):
        term = viz.generate_terminal(sample_result)
        assert "PK" in term

    def test_contains_fk_marker(self, viz, sample_result):
        term = viz.generate_terminal(sample_result)
        assert "FK" in term

    def test_contains_fk_reference(self, viz, sample_result):
        term = viz.generate_terminal(sample_result)
        assert "user_id -> users(id)" in term

    def test_contains_indexes(self, viz, sample_result):
        term = viz.generate_terminal(sample_result)
        assert "users_email_idx" in term

    def test_contains_separator(self, viz, sample_result):
        term = viz.generate_terminal(sample_result)
        assert "---" in term

    def test_empty_schema(self, viz):
        empty = SchemaResult(tables=[], relationships=[], database="empty", schema="public")
        term = viz.generate_terminal(empty)
        assert "Tables: 0" in term


# ── TestHtml ────────────────────────────────────────────────────────────


class TestHtml:
    """HTML output tests."""

    def test_contains_doctype(self, viz, sample_result):
        html_out = viz.generate_html(sample_result)
        assert "<!DOCTYPE html>" in html_out

    def test_contains_d3_script(self, viz, sample_result):
        html_out = viz.generate_html(sample_result)
        assert "d3.v7.min.js" in html_out

    def test_contains_title(self, viz, sample_result):
        html_out = viz.generate_html(sample_result)
        assert "ER Diagram" in html_out

    def test_contains_table_names(self, viz, sample_result):
        html_out = viz.generate_html(sample_result)
        assert "users" in html_out
        assert "orders" in html_out

    def test_contains_svg(self, viz, sample_result):
        html_out = viz.generate_html(sample_result)
        assert "<svg>" in html_out

    def test_contains_force_simulation(self, viz, sample_result):
        html_out = viz.generate_html(sample_result)
        assert "forceSimulation" in html_out

    def test_contains_nodes_and_links(self, viz, sample_result):
        html_out = viz.generate_html(sample_result)
        assert "const nodes" in html_out
        assert "const links" in html_out

    def test_contains_column_info(self, viz, sample_result):
        html_out = viz.generate_html(sample_result)
        assert "email" in html_out
        assert "varchar" in html_out


# ── TestFormatSummary ───────────────────────────────────────────────────


class TestFormatSummary:
    """format_schema_summary tests."""

    def test_contains_table_count(self, sample_result):
        summary = format_schema_summary(sample_result)
        assert "2 tables" in summary

    def test_contains_column_count(self, sample_result):
        summary = format_schema_summary(sample_result)
        assert "7 columns" in summary

    def test_contains_fk_count(self, sample_result):
        summary = format_schema_summary(sample_result)
        assert "1 foreign keys" in summary

    def test_contains_database_name(self, sample_result):
        summary = format_schema_summary(sample_result)
        assert "testdb" in summary
