"""Migration Generator — plain English → DB migration + model updates."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.migration_gen")


@dataclass
class ColumnSpec:
    name: str
    data_type: str = "VARCHAR(255)"
    nullable: bool = True
    default: str = ""
    primary_key: bool = False
    foreign_key: str = ""  # table.column


@dataclass
class MigrationSpec:
    operation: str  # add_column, drop_column, create_table, rename_column, add_index
    table: str
    columns: list[ColumnSpec] = field(default_factory=list)
    old_name: str = ""  # for rename
    new_name: str = ""  # for rename
    index_columns: list[str] = field(default_factory=list)


@dataclass
class MigrationOutput:
    migration_sql: str = ""
    rollback_sql: str = ""
    migration_path: str = ""
    model_changes: list[str] = field(default_factory=list)
    blast_radius: list[str] = field(default_factory=list)
    preview: bool = True
    spec: MigrationSpec = field(default_factory=lambda: MigrationSpec(operation="", table=""))
    migration_type: str = "raw"  # raw, alembic, django, flyway
    detected_orm: str = ""


# Type mapping for common descriptions
_TYPE_MAP = {
    "string": "VARCHAR(255)",
    "str": "VARCHAR(255)",
    "text": "TEXT",
    "int": "INTEGER",
    "integer": "INTEGER",
    "bigint": "BIGINT",
    "float": "FLOAT",
    "double": "DOUBLE PRECISION",
    "decimal": "DECIMAL(10,2)",
    "bool": "BOOLEAN",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
    "timestamp": "TIMESTAMP",
    "time": "TIME",
    "json": "JSONB",
    "jsonb": "JSONB",
    "uuid": "UUID",
    "binary": "BYTEA",
    "blob": "BYTEA",
}

# Patterns for parsing natural language descriptions
_ADD_COLUMN_RE = re.compile(
    r"add\s+(?:column\s+)?(\w+)\s+(?:to\s+)?(\w+)(?:\s+(?:as|type|of)\s+(\w+))?",
    re.IGNORECASE,
)
_DROP_COLUMN_RE = re.compile(
    r"(?:drop|remove|delete)\s+(?:column\s+)?(\w+)\s+from\s+(\w+)",
    re.IGNORECASE,
)
_CREATE_TABLE_RE = re.compile(
    r"create\s+(?:table\s+)?(\w+)",
    re.IGNORECASE,
)
_RENAME_COLUMN_RE = re.compile(
    r"rename\s+(?:column\s+)?(\w+)\s+to\s+(\w+)\s+(?:in|on)\s+(\w+)",
    re.IGNORECASE,
)
_ADD_INDEX_RE = re.compile(
    r"(?:add\s+)?index\s+(?:on\s+)?(\w+)\s*\(([^)]+)\)",
    re.IGNORECASE,
)


class MigrationGenerator:
    """Generates DB migrations from plain English descriptions."""

    def __init__(self, cwd: str = ".", migration_type: str = "auto"):
        self.cwd = os.path.abspath(cwd)
        self.migration_type = migration_type if migration_type != "auto" else self._detect_type()
        self.detected_orm = self._detect_orm()

    def generate(self, description: str, preview: bool = True) -> MigrationOutput:
        """Generate migration from natural language description."""
        spec = self._parse_description(description)
        if not spec.table and not spec.operation:
            return MigrationOutput(
                migration_sql=f"-- Could not parse: {description}",
                rollback_sql="-- No rollback",
                preview=preview,
                spec=spec,
                migration_type=self.migration_type,
                detected_orm=self.detected_orm,
            )

        if self.migration_type == "alembic":
            sql, rollback = self._generate_alembic(spec)
        elif self.migration_type == "django":
            sql, rollback = self._generate_django(spec)
        else:
            sql, rollback = self._generate_raw_sql(spec)

        migration_path = self._get_migration_path(spec)
        model_changes = self._suggest_model_changes(spec)
        blast_radius = self._find_blast_radius(spec)

        return MigrationOutput(
            migration_sql=sql,
            rollback_sql=rollback,
            migration_path=migration_path,
            model_changes=model_changes,
            blast_radius=blast_radius,
            preview=preview,
            spec=spec,
            migration_type=self.migration_type,
            detected_orm=self.detected_orm,
        )

    def _detect_type(self) -> str:
        """Detect migration framework from project files."""
        if os.path.exists(os.path.join(self.cwd, "alembic.ini")):
            return "alembic"
        if os.path.exists(os.path.join(self.cwd, "manage.py")):
            return "django"
        for d in Path(self.cwd).rglob("flyway.conf"):
            return "flyway"
        return "raw"

    def _detect_orm(self) -> str:
        """Detect ORM from project files."""
        pyproject = os.path.join(self.cwd, "pyproject.toml")
        req = os.path.join(self.cwd, "requirements.txt")
        for f in [pyproject, req]:
            if os.path.exists(f):
                content = Path(f).read_text()
                if "sqlalchemy" in content.lower():
                    return "sqlalchemy"
                if "django" in content.lower():
                    return "django"
                if "tortoise" in content.lower():
                    return "tortoise"
                if "peewee" in content.lower():
                    return "peewee"
        pkg = os.path.join(self.cwd, "package.json")
        if os.path.exists(pkg):
            content = Path(pkg).read_text()
            if "prisma" in content.lower():
                return "prisma"
            if "sequelize" in content.lower():
                return "sequelize"
            if "typeorm" in content.lower():
                return "typeorm"
        return "unknown"

    def _parse_description(self, description: str) -> MigrationSpec:
        """Parse natural language into migration spec."""
        desc = description.strip()

        # Try add column
        m = _ADD_COLUMN_RE.search(desc)
        if m:
            col_name = m.group(1)
            table = m.group(2)
            col_type = _TYPE_MAP.get((m.group(3) or "string").lower(), "VARCHAR(255)")
            nullable = "not null" not in desc.lower()
            default = ""
            dm = re.search(r"default\s+(\S+)", desc, re.IGNORECASE)
            if dm:
                default = dm.group(1)
            return MigrationSpec(
                operation="add_column",
                table=table,
                columns=[ColumnSpec(name=col_name, data_type=col_type,
                                    nullable=nullable, default=default)],
            )

        # Try drop column
        m = _DROP_COLUMN_RE.search(desc)
        if m:
            return MigrationSpec(
                operation="drop_column",
                table=m.group(2),
                columns=[ColumnSpec(name=m.group(1))],
            )

        # Try rename column
        m = _RENAME_COLUMN_RE.search(desc)
        if m:
            return MigrationSpec(
                operation="rename_column",
                table=m.group(3),
                old_name=m.group(1),
                new_name=m.group(2),
            )

        # Try create table
        m = _CREATE_TABLE_RE.search(desc)
        if m:
            return MigrationSpec(
                operation="create_table",
                table=m.group(1),
                columns=[
                    ColumnSpec(name="id", data_type="BIGSERIAL", primary_key=True),
                    ColumnSpec(name="created_at", data_type="TIMESTAMP", default="NOW()"),
                    ColumnSpec(name="updated_at", data_type="TIMESTAMP", default="NOW()"),
                ],
            )

        # Try add index
        m = _ADD_INDEX_RE.search(desc)
        if m:
            cols = [c.strip() for c in m.group(2).split(",")]
            return MigrationSpec(
                operation="add_index",
                table=m.group(1),
                index_columns=cols,
            )

        return MigrationSpec(operation="", table="")

    def _generate_raw_sql(self, spec: MigrationSpec) -> tuple[str, str]:
        """Generate raw SQL migration."""
        up_lines = [f"-- Migration: {spec.operation} on {spec.table}",
                     f"-- Generated: {datetime.now().isoformat()}", ""]
        down_lines = [f"-- Rollback: {spec.operation} on {spec.table}", ""]

        if spec.operation == "add_column":
            for col in spec.columns:
                null = "" if col.nullable else " NOT NULL"
                default = f" DEFAULT {col.default}" if col.default else ""
                up_lines.append(
                    f"ALTER TABLE {spec.table} ADD COLUMN {col.name} {col.data_type}{null}{default};"
                )
                down_lines.append(f"ALTER TABLE {spec.table} DROP COLUMN {col.name};")

        elif spec.operation == "drop_column":
            for col in spec.columns:
                up_lines.append(f"ALTER TABLE {spec.table} DROP COLUMN {col.name};")
                down_lines.append(
                    f"-- ALTER TABLE {spec.table} ADD COLUMN {col.name} <type>; -- restore manually"
                )

        elif spec.operation == "rename_column":
            up_lines.append(
                f"ALTER TABLE {spec.table} RENAME COLUMN {spec.old_name} TO {spec.new_name};"
            )
            down_lines.append(
                f"ALTER TABLE {spec.table} RENAME COLUMN {spec.new_name} TO {spec.old_name};"
            )

        elif spec.operation == "create_table":
            col_defs = []
            for col in spec.columns:
                parts = [col.name, col.data_type]
                if col.primary_key:
                    parts.append("PRIMARY KEY")
                if not col.nullable and not col.primary_key:
                    parts.append("NOT NULL")
                if col.default:
                    parts.append(f"DEFAULT {col.default}")
                col_defs.append("    " + " ".join(parts))
            up_lines.append(f"CREATE TABLE {spec.table} (")
            up_lines.append(",\n".join(col_defs))
            up_lines.append(");")
            down_lines.append(f"DROP TABLE IF EXISTS {spec.table};")

        elif spec.operation == "add_index":
            idx_name = f"idx_{spec.table}_{'_'.join(spec.index_columns)}"
            cols = ", ".join(spec.index_columns)
            up_lines.append(f"CREATE INDEX {idx_name} ON {spec.table} ({cols});")
            down_lines.append(f"DROP INDEX IF EXISTS {idx_name};")

        return "\n".join(up_lines), "\n".join(down_lines)

    def _generate_alembic(self, spec: MigrationSpec) -> tuple[str, str]:
        """Generate Alembic migration."""
        ts = datetime.now().strftime("%Y%m%d%H%M")
        header = f'''"""migration: {spec.operation} on {spec.table}

Revision ID: {ts}
"""
from alembic import op
import sqlalchemy as sa

revision = "{ts}"
down_revision = None
'''
        up_lines = ["def upgrade():", f'    # {spec.operation} on {spec.table}']
        down_lines = ["def downgrade():", f'    # rollback {spec.operation} on {spec.table}']

        if spec.operation == "add_column":
            for col in spec.columns:
                sa_type = self._sql_to_sa_type(col.data_type)
                up_lines.append(f"    op.add_column('{spec.table}', sa.Column('{col.name}', {sa_type}))")
                down_lines.append(f"    op.drop_column('{spec.table}', '{col.name}')")

        elif spec.operation == "drop_column":
            for col in spec.columns:
                up_lines.append(f"    op.drop_column('{spec.table}', '{col.name}')")
                down_lines.append(f"    # op.add_column('{spec.table}', sa.Column('{col.name}', ...))")

        elif spec.operation == "create_table":
            up_lines.append(f"    op.create_table('{spec.table}',")
            for col in spec.columns:
                sa_type = self._sql_to_sa_type(col.data_type)
                pk = ", primary_key=True" if col.primary_key else ""
                up_lines.append(f"        sa.Column('{col.name}', {sa_type}{pk}),")
            up_lines.append("    )")
            down_lines.append(f"    op.drop_table('{spec.table}')")

        elif spec.operation == "rename_column":
            up_lines.append(
                f"    op.alter_column('{spec.table}', '{spec.old_name}', new_column_name='{spec.new_name}')"
            )
            down_lines.append(
                f"    op.alter_column('{spec.table}', '{spec.new_name}', new_column_name='{spec.old_name}')"
            )

        return header + "\n".join(up_lines) + "\n\n" + "\n".join(down_lines), ""

    def _generate_django(self, spec: MigrationSpec) -> tuple[str, str]:
        """Generate Django migration stub."""
        lines = [
            "from django.db import migrations, models",
            "",
            "class Migration(migrations.Migration):",
            "    dependencies = []",
            "    operations = [",
        ]
        if spec.operation == "add_column":
            for col in spec.columns:
                dj_type = self._sql_to_django_type(col.data_type)
                lines.append(f"        migrations.AddField(")
                lines.append(f"            model_name='{spec.table}',")
                lines.append(f"            name='{col.name}',")
                lines.append(f"            field={dj_type},")
                lines.append(f"        ),")
        elif spec.operation == "create_table":
            lines.append(f"        migrations.CreateModel(")
            lines.append(f"            name='{spec.table.title()}',")
            lines.append(f"            fields=[")
            for col in spec.columns:
                dj_type = self._sql_to_django_type(col.data_type)
                lines.append(f"                ('{col.name}', {dj_type}),")
            lines.append(f"            ],")
            lines.append(f"        ),")
        lines.append("    ]")
        return "\n".join(lines), ""

    def _sql_to_sa_type(self, sql_type: str) -> str:
        """Map SQL type to SQLAlchemy type."""
        mapping = {
            "VARCHAR(255)": "sa.String(255)",
            "TEXT": "sa.Text()",
            "INTEGER": "sa.Integer()",
            "BIGINT": "sa.BigInteger()",
            "BIGSERIAL": "sa.BigInteger()",
            "FLOAT": "sa.Float()",
            "BOOLEAN": "sa.Boolean()",
            "TIMESTAMP": "sa.DateTime()",
            "DATE": "sa.Date()",
            "JSONB": "sa.JSON()",
            "UUID": "sa.String(36)",
        }
        return mapping.get(sql_type, f"sa.String(255)")

    def _sql_to_django_type(self, sql_type: str) -> str:
        """Map SQL type to Django model field."""
        mapping = {
            "VARCHAR(255)": "models.CharField(max_length=255)",
            "TEXT": "models.TextField()",
            "INTEGER": "models.IntegerField()",
            "BIGINT": "models.BigIntegerField()",
            "BIGSERIAL": "models.BigAutoField(primary_key=True)",
            "FLOAT": "models.FloatField()",
            "BOOLEAN": "models.BooleanField(default=False)",
            "TIMESTAMP": "models.DateTimeField(auto_now_add=True)",
            "DATE": "models.DateField()",
            "JSONB": "models.JSONField(default=dict)",
            "UUID": "models.UUIDField()",
        }
        return mapping.get(sql_type, "models.CharField(max_length=255)")

    def _get_migration_path(self, spec: MigrationSpec) -> str:
        """Get the output path for the migration file."""
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        if self.migration_type == "alembic":
            return os.path.join("alembic", "versions", f"{ts}_{spec.operation}_{spec.table}.py")
        elif self.migration_type == "django":
            return os.path.join("migrations", f"{ts}_{spec.operation}_{spec.table}.py")
        return os.path.join("migrations", f"{ts}_{spec.operation}_{spec.table}.sql")

    def _suggest_model_changes(self, spec: MigrationSpec) -> list[str]:
        """Suggest model file changes based on migration."""
        suggestions = []
        if spec.operation == "add_column":
            for col in spec.columns:
                suggestions.append(
                    f"Add field '{col.name}' ({col.data_type}) to {spec.table} model"
                )
        elif spec.operation == "drop_column":
            for col in spec.columns:
                suggestions.append(
                    f"Remove field '{col.name}' from {spec.table} model"
                )
        elif spec.operation == "create_table":
            suggestions.append(f"Create new model class for '{spec.table}'")
        elif spec.operation == "rename_column":
            suggestions.append(
                f"Rename field '{spec.old_name}' to '{spec.new_name}' in {spec.table} model"
            )
        return suggestions

    def _find_blast_radius(self, spec: MigrationSpec) -> list[str]:
        """Find files that reference the table/column."""
        affected = []
        table = spec.table
        if not table:
            return affected

        # Search for table name references in code files
        for ext in ("*.py", "*.js", "*.ts", "*.java", "*.go"):
            for p in Path(self.cwd).rglob(ext):
                try:
                    content = p.read_text(errors="replace")
                    if table in content:
                        rel = str(p.relative_to(self.cwd))
                        if not any(skip in rel for skip in ("node_modules", ".git", "__pycache__")):
                            affected.append(rel)
                except OSError:
                    continue

        return affected[:30]  # Limit results


def format_migration(output: MigrationOutput) -> str:
    """Format migration output for display."""
    lines = [
        "## Migration Generator",
        "",
        f"**Type:** {output.migration_type}",
        f"**ORM:** {output.detected_orm}",
        f"**Operation:** {output.spec.operation}",
        f"**Table:** {output.spec.table}",
        "",
    ]

    if output.migration_sql:
        lang = "python" if output.migration_type in ("alembic", "django") else "sql"
        lines.extend([
            "### Migration", "",
            f"```{lang}", output.migration_sql, "```", "",
        ])

    if output.rollback_sql:
        lines.extend([
            "### Rollback", "",
            f"```sql", output.rollback_sql, "```", "",
        ])

    if output.migration_path:
        lines.extend([f"**Output path:** `{output.migration_path}`", ""])

    if output.model_changes:
        lines.extend(["### Model Changes Needed", ""])
        for mc in output.model_changes:
            lines.append(f"- {mc}")
        lines.append("")

    if output.blast_radius:
        lines.extend(["### Blast Radius", ""])
        for f in output.blast_radius:
            lines.append(f"- `{f}`")
        lines.append("")

    return "\n".join(lines)
