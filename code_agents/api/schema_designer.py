"""Schema Designer — describe entities and relationships, get normalized schema.

Generates CREATE TABLE statements with proper types, constraints, indexes,
and foreign keys from a high-level entity description.

Usage:
    from code_agents.api.schema_designer import SchemaDesigner
    designer = SchemaDesigner()
    result = designer.design([
        {"name": "User", "fields": {"name": "str", "email": "str"}},
        {"name": "Order", "fields": {"user_id": "fk:User", "total": "decimal", "status": "enum:pending,paid,shipped"}},
    ])
    print(format_schema(result))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.api.schema_designer")


@dataclass
class SchemaDesignerConfig:
    dialect: str = "postgresql"  # postgresql, mysql, sqlite
    include_timestamps: bool = True
    include_soft_delete: bool = False


@dataclass
class TableColumn:
    name: str
    sql_type: str
    nullable: bool = True
    primary_key: bool = False
    unique: bool = False
    default: str = ""
    foreign_key: str = ""  # "table.column"
    index: bool = False


@dataclass
class TableDef:
    name: str
    columns: list[TableColumn] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)  # CREATE INDEX statements
    constraints: list[str] = field(default_factory=list)


@dataclass
class SchemaDesignResult:
    tables: list[TableDef] = field(default_factory=list)
    sql: str = ""
    migration_up: str = ""
    migration_down: str = ""
    summary: str = ""


TYPE_MAP = {
    "str": "VARCHAR(255)", "string": "VARCHAR(255)", "text": "TEXT",
    "int": "INTEGER", "integer": "INTEGER", "bigint": "BIGINT",
    "float": "REAL", "double": "DOUBLE PRECISION", "decimal": "DECIMAL(10,2)",
    "bool": "BOOLEAN", "boolean": "BOOLEAN",
    "date": "DATE", "datetime": "TIMESTAMP", "timestamp": "TIMESTAMP",
    "json": "JSONB", "uuid": "UUID",
    "email": "VARCHAR(320)", "url": "VARCHAR(2048)", "phone": "VARCHAR(20)",
}


class SchemaDesigner:
    """Design database schemas from entity descriptions."""

    def __init__(self, config: Optional[SchemaDesignerConfig] = None):
        self.config = config or SchemaDesignerConfig()

    def design(self, entities: list[dict]) -> SchemaDesignResult:
        logger.info("Designing schema for %d entities", len(entities))
        result = SchemaDesignResult()

        for entity in entities:
            table = self._build_table(entity)
            result.tables.append(table)

        result.sql = self._generate_sql(result.tables)
        result.migration_up = result.sql
        result.migration_down = self._generate_rollback(result.tables)
        result.summary = f"{len(result.tables)} tables, {sum(len(t.columns) for t in result.tables)} columns"
        return result

    def _build_table(self, entity: dict) -> TableDef:
        name = entity["name"].lower() + "s"  # pluralize
        fields = entity.get("fields", {})
        table = TableDef(name=name)

        # Primary key
        table.columns.append(TableColumn(
            name="id", sql_type="BIGSERIAL" if self.config.dialect == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT",
            primary_key=True, nullable=False,
        ))

        # User-defined fields
        for fname, ftype in fields.items():
            col = self._build_column(fname, ftype, name)
            table.columns.append(col)
            if col.foreign_key:
                table.indexes.append(f"CREATE INDEX idx_{name}_{fname} ON {name} ({fname});")
            if col.unique:
                table.indexes.append(f"CREATE UNIQUE INDEX idx_{name}_{fname}_uniq ON {name} ({fname});")

        # Timestamps
        if self.config.include_timestamps:
            table.columns.append(TableColumn(name="created_at", sql_type="TIMESTAMP", default="NOW()", nullable=False))
            table.columns.append(TableColumn(name="updated_at", sql_type="TIMESTAMP", default="NOW()", nullable=False))

        if self.config.include_soft_delete:
            table.columns.append(TableColumn(name="deleted_at", sql_type="TIMESTAMP", nullable=True))

        return table

    def _build_column(self, name: str, ftype: str, table_name: str) -> TableColumn:
        col = TableColumn(name=name, sql_type="VARCHAR(255)")

        # Foreign key
        if ftype.startswith("fk:"):
            ref_table = ftype[3:].lower() + "s"
            col.sql_type = "BIGINT"
            col.foreign_key = f"{ref_table}.id"
            col.index = True
            col.nullable = False
            return col

        # Enum
        if ftype.startswith("enum:"):
            values = ftype[5:].split(",")
            col.sql_type = f"VARCHAR(50)"
            col.default = f"'{values[0]}'"
            return col

        # Standard types
        base_type = ftype.lower().split(":")[0]
        col.sql_type = TYPE_MAP.get(base_type, "VARCHAR(255)")

        # Auto-detect unique fields
        if name in ("email", "username", "slug", "code"):
            col.unique = True
            col.nullable = False

        return col

    def _generate_sql(self, tables: list[TableDef]) -> str:
        lines = []
        for table in tables:
            lines.append(f"CREATE TABLE {table.name} (")
            col_defs = []
            for col in table.columns:
                parts = [f"    {col.name} {col.sql_type}"]
                if col.primary_key and "AUTOINCREMENT" not in col.sql_type:
                    parts.append("PRIMARY KEY")
                if not col.nullable and not col.primary_key:
                    parts.append("NOT NULL")
                if col.unique:
                    parts.append("UNIQUE")
                if col.default:
                    parts.append(f"DEFAULT {col.default}")
                if col.foreign_key:
                    parts.append(f"REFERENCES {col.foreign_key}")
                col_defs.append(" ".join(parts))
            lines.append(",\n".join(col_defs))
            lines.append(");")
            lines.append("")
            for idx in table.indexes:
                lines.append(idx)
            lines.append("")
        return "\n".join(lines)

    def _generate_rollback(self, tables: list[TableDef]) -> str:
        lines = []
        for table in reversed(tables):
            lines.append(f"DROP TABLE IF EXISTS {table.name} CASCADE;")
        return "\n".join(lines)


def format_schema(result: SchemaDesignResult) -> str:
    lines = [f"{'=' * 60}", f"  Schema Designer", f"{'=' * 60}"]
    lines.append(f"  {result.summary}")
    lines.append(f"\n  --- SQL ---")
    for line in result.sql.splitlines():
        lines.append(f"  {line}")
    lines.append(f"\n  --- Rollback ---")
    for line in result.migration_down.splitlines():
        lines.append(f"  {line}")
    lines.append("")
    return "\n".join(lines)
