"""
Database Schema Visualizer — generates ER diagrams from database schema.

Supports live database scanning (via DBClient) and offline SQL file parsing.
Output formats: Mermaid erDiagram, ASCII terminal, interactive HTML (D3.js).
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.api.schema_viz")


# ── Data models ─────────────────────────────────────────────────────────


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool = True
    primary_key: bool = False
    default: str = ""


@dataclass
class ForeignKey:
    column: str
    references_table: str
    references_column: str


@dataclass
class TableSchema:
    name: str
    columns: list[ColumnInfo]
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)
    row_count: int = 0
    size_bytes: int = 0


@dataclass
class SchemaResult:
    tables: list[TableSchema]
    relationships: list[ForeignKey]
    database: str
    schema: str = "public"


# ── Visualizer ──────────────────────────────────────────────────────────


class SchemaVisualizer:
    """Generate ER diagrams from database schema or SQL files."""

    def __init__(self, database_url: str = ""):
        self.database_url = database_url

    # ── Live database scanning ──────────────────────────────────────────

    async def scan(self, database: str = "", schema: str = "public") -> SchemaResult:
        """Scan a live database via DBClient and return SchemaResult."""
        from code_agents.cicd.db_client import DBClient  # lazy import

        client = DBClient(database_url=self.database_url)
        db_name = database or ""

        logger.info("Scanning schema %s.%s", db_name or "(default)", schema)

        # 1. List tables
        tables_raw = await client.list_tables(database=db_name, schema=schema)
        tables: list[TableSchema] = []

        for tbl in tables_raw:
            tbl_name = tbl["name"]

            # 2. Column info
            info = await client.table_info(tbl_name, database=db_name, schema=schema)
            columns: list[ColumnInfo] = []
            for col in info.get("columns", []):
                columns.append(ColumnInfo(
                    name=col["name"],
                    data_type=col["type"],
                    nullable=col.get("nullable", True),
                    primary_key=False,
                    default=col.get("default") or "",
                ))

            # 3. Constraints — identify PKs
            constraints = await client.table_constraints(tbl_name, database=db_name)
            pk_cols: list[str] = []
            for c in constraints:
                if c["type"] == "PRIMARY KEY":
                    pk_cols.append(c["name"])

            # Mark PK columns (heuristic: column named 'id' or constraint name contains column)
            for col in columns:
                if col.name in pk_cols or any(col.name in pk for pk in pk_cols):
                    col.primary_key = True

            # 4. Indexes
            indexes_raw = await client.table_indexes(tbl_name, database=db_name)
            idx_names = [idx["name"] for idx in indexes_raw]

            tables.append(TableSchema(
                name=tbl_name,
                columns=columns,
                primary_key=pk_cols,
                foreign_keys=[],
                indexes=idx_names,
                row_count=tbl.get("estimated_rows", 0),
                size_bytes=tbl.get("size_bytes", 0),
            ))

        # 5. Foreign keys via information_schema
        all_fks = await self._fetch_foreign_keys(client, db_name, schema)

        # Assign FKs to tables
        for fk in all_fks:
            for t in tables:
                if any(col.name == fk.column for col in t.columns):
                    t.foreign_keys.append(fk)
                    break

        logger.info("Found %d tables with %d foreign keys", len(tables), len(all_fks))

        return SchemaResult(
            tables=tables,
            relationships=all_fks,
            database=db_name or "(default)",
            schema=schema,
        )

    async def _fetch_foreign_keys(
        self, client, database: str, schema: str
    ) -> list[ForeignKey]:
        """Fetch all foreign keys from information_schema."""
        from code_agents.cicd.db_client import DBClient  # lazy import

        query = (
            "SELECT kcu.column_name, ccu.table_name AS references_table, "
            "  ccu.column_name AS references_column "
            "FROM information_schema.key_column_usage kcu "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON kcu.constraint_name = ccu.constraint_name "
            "JOIN information_schema.table_constraints tc "
            "  ON tc.constraint_name = kcu.constraint_name "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "  AND kcu.table_schema = $1"
        )
        try:
            result = await client.execute_query(query, database=database, params=[schema], limit=1000)
            fks = []
            for row in result.get("rows", []):
                fks.append(ForeignKey(
                    column=row["column_name"],
                    references_table=row["references_table"],
                    references_column=row["references_column"],
                ))
            return fks
        except Exception as exc:
            logger.warning("Could not fetch foreign keys: %s", exc)
            return []

    # ── Offline SQL parsing ─────────────────────────────────────────────

    def scan_from_sql(self, sql_content: str) -> SchemaResult:
        """Parse CREATE TABLE statements from SQL content (offline mode)."""
        logger.info("Parsing SQL content (%d chars)", len(sql_content))
        tables = self._parse_create_table(sql_content)
        all_fks = self._extract_foreign_keys(tables)

        return SchemaResult(
            tables=tables,
            relationships=all_fks,
            database="(sql-file)",
            schema="public",
        )

    def _parse_create_table(self, sql: str) -> list[TableSchema]:
        """Regex-based CREATE TABLE parser for PostgreSQL syntax."""
        tables: list[TableSchema] = []

        # Match CREATE TABLE name (...) blocks
        pattern = re.compile(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"(?:\"?(\w+)\"?\.)?\"?(\w+)\"?\s*\((.*?)\)\s*;",
            re.IGNORECASE | re.DOTALL,
        )

        for match in pattern.finditer(sql):
            _schema_name = match.group(1) or "public"
            table_name = match.group(2)
            body = match.group(3)

            columns: list[ColumnInfo] = []
            foreign_keys: list[ForeignKey] = []
            primary_key: list[str] = []

            # Split body on commas, but respect parentheses
            parts = self._split_body(body)

            for part in parts:
                part = part.strip()
                if not part:
                    continue

                # Table-level PRIMARY KEY
                pk_match = re.match(
                    r"PRIMARY\s+KEY\s*\(([^)]+)\)", part, re.IGNORECASE
                )
                if pk_match:
                    pk_cols = [c.strip().strip('"') for c in pk_match.group(1).split(",")]
                    primary_key.extend(pk_cols)
                    continue

                # Table-level FOREIGN KEY
                fk_match = re.match(
                    r"(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY\s*\(\"?(\w+)\"?\)\s*"
                    r"REFERENCES\s+\"?(\w+)\"?\s*\(\"?(\w+)\"?\)",
                    part, re.IGNORECASE,
                )
                if fk_match:
                    foreign_keys.append(ForeignKey(
                        column=fk_match.group(1),
                        references_table=fk_match.group(2),
                        references_column=fk_match.group(3),
                    ))
                    continue

                # CONSTRAINT ... UNIQUE / CHECK — skip
                if re.match(r"(?:CONSTRAINT|UNIQUE|CHECK)\b", part, re.IGNORECASE):
                    continue

                # Column definition
                col = self._parse_column(part)
                if col:
                    columns.append(col)

                    # Inline REFERENCES
                    ref_match = re.search(
                        r"REFERENCES\s+\"?(\w+)\"?\s*\(\"?(\w+)\"?\)",
                        part, re.IGNORECASE,
                    )
                    if ref_match:
                        foreign_keys.append(ForeignKey(
                            column=col.name,
                            references_table=ref_match.group(1),
                            references_column=ref_match.group(2),
                        ))

            # Apply table-level PK to columns
            for col in columns:
                if col.name in primary_key:
                    col.primary_key = True

            # If no explicit table-level PK, check inline PKs
            if not primary_key:
                primary_key = [c.name for c in columns if c.primary_key]

            tables.append(TableSchema(
                name=table_name,
                columns=columns,
                primary_key=primary_key,
                foreign_keys=foreign_keys,
                indexes=[],
                row_count=0,
                size_bytes=0,
            ))

        logger.info("Parsed %d tables from SQL", len(tables))
        return tables

    def _split_body(self, body: str) -> list[str]:
        """Split CREATE TABLE body on commas, respecting parentheses."""
        parts: list[str] = []
        depth = 0
        current: list[str] = []
        for ch in body:
            if ch == "(":
                depth += 1
                current.append(ch)
            elif ch == ")":
                depth -= 1
                current.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(current))
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current))
        return parts

    def _parse_column(self, part: str) -> Optional[ColumnInfo]:
        """Parse a single column definition."""
        # column_name DATA_TYPE(...) [constraints]
        col_match = re.match(
            r"\"?(\w+)\"?\s+"
            r"([\w]+(?:\s*\([^)]*\))?(?:\s+(?:VARYING|PRECISION|WITHOUT|WITH|TIME|ZONE|CHARACTER)[\w\s]*(?:\([^)]*\))?)?)",
            part, re.IGNORECASE,
        )
        if not col_match:
            return None

        name = col_match.group(1)
        data_type = col_match.group(2).strip()

        # Skip SQL keywords that aren't column names
        if name.upper() in ("PRIMARY", "FOREIGN", "CONSTRAINT", "UNIQUE", "CHECK", "INDEX"):
            return None

        nullable = "NOT NULL" not in part.upper()
        is_pk = "PRIMARY KEY" in part.upper()

        default = ""
        def_match = re.search(r"DEFAULT\s+(.+?)(?:\s+(?:NOT|NULL|PRIMARY|REFERENCES|UNIQUE|CHECK|CONSTRAINT)|$)", part, re.IGNORECASE)
        if def_match:
            default = def_match.group(1).strip().rstrip(",")

        return ColumnInfo(
            name=name,
            data_type=data_type,
            nullable=nullable,
            primary_key=is_pk,
            default=default,
        )

    def _extract_foreign_keys(self, tables: list[TableSchema]) -> list[ForeignKey]:
        """Collect all foreign keys from parsed tables."""
        all_fks: list[ForeignKey] = []
        for table in tables:
            all_fks.extend(table.foreign_keys)
        return all_fks

    # ── Output: Mermaid ─────────────────────────────────────────────────

    def generate_mermaid(self, result: SchemaResult) -> str:
        """Generate Mermaid erDiagram syntax."""
        lines: list[str] = ["erDiagram"]

        # Relationships
        rendered_rels: set[str] = set()
        for fk in result.relationships:
            # Find which table owns this FK
            src_table = ""
            for t in result.tables:
                if any(c.name == fk.column for c in t.columns):
                    src_table = t.name
                    break
            if not src_table:
                continue
            rel_key = f"{fk.references_table}--{src_table}"
            if rel_key not in rendered_rels:
                rendered_rels.add(rel_key)
                lines.append(
                    f"    {fk.references_table} ||--o{{ {src_table} : \"{fk.column}\""
                )

        # Table definitions
        for table in result.tables:
            lines.append(f"    {table.name} {{")
            for col in table.columns:
                pk_tag = " PK" if col.primary_key else ""
                fk_tag = ""
                if any(fk.column == col.name for fk in table.foreign_keys):
                    fk_tag = " FK"
                dtype = col.data_type.replace(" ", "_")
                lines.append(f"        {dtype} {col.name}{pk_tag}{fk_tag}")
            lines.append("    }")

        return "\n".join(lines)

    # ── Output: Terminal ASCII ──────────────────────────────────────────

    def generate_terminal(self, result: SchemaResult) -> str:
        """Generate ASCII table with columns, types, keys."""
        output: list[str] = []
        output.append(f"Database: {result.database}  Schema: {result.schema}")
        output.append(f"Tables: {len(result.tables)}  Relationships: {len(result.relationships)}")
        output.append("")

        for table in result.tables:
            # Table header
            size_info = ""
            if table.row_count > 0:
                size_info = f"  (~{table.row_count:,} rows)"
            if table.size_bytes > 0:
                size_info += f"  [{_format_bytes(table.size_bytes)}]"
            output.append(f"  {table.name}{size_info}")

            # Column widths
            if not table.columns:
                output.append("    (no columns)")
                output.append("")
                continue

            name_w = max(len(c.name) for c in table.columns)
            type_w = max(len(c.data_type) for c in table.columns)
            name_w = max(name_w, 6)  # min width
            type_w = max(type_w, 4)

            header = f"    {'Column':<{name_w}}  {'Type':<{type_w}}  Null  Key  Default"
            sep = f"    {'-' * name_w}  {'-' * type_w}  ----  ---  -------"
            output.append(header)
            output.append(sep)

            for col in table.columns:
                null_str = "YES " if col.nullable else "NO  "
                key_str = "PK " if col.primary_key else "   "
                if any(fk.column == col.name for fk in table.foreign_keys):
                    key_str = "FK " if not col.primary_key else "PFK"
                default_str = col.default if col.default else ""
                output.append(
                    f"    {col.name:<{name_w}}  {col.data_type:<{type_w}}  {null_str}  {key_str}  {default_str}"
                )

            # Foreign keys
            if table.foreign_keys:
                output.append(f"    Foreign Keys:")
                for fk in table.foreign_keys:
                    output.append(f"      {fk.column} -> {fk.references_table}({fk.references_column})")

            # Indexes
            if table.indexes:
                output.append(f"    Indexes: {', '.join(table.indexes)}")

            output.append("")

        return "\n".join(output)

    # ── Output: HTML (D3.js) ────────────────────────────────────────────

    def generate_html(self, result: SchemaResult) -> str:
        """Generate interactive ER diagram with D3.js."""
        nodes_js = []
        for i, table in enumerate(result.tables):
            cols_html = ""
            for col in table.columns:
                pk = " [PK]" if col.primary_key else ""
                fk = " [FK]" if any(fk.column == col.name for fk in table.foreign_keys) else ""
                cols_html += f"<tr><td>{html.escape(col.name)}{pk}{fk}</td><td>{html.escape(col.data_type)}</td></tr>"
            nodes_js.append(
                f'{{id:"{html.escape(table.name)}",cols:`<table class="cols">{cols_html}</table>`}}'
            )

        links_js = []
        for fk in result.relationships:
            src = ""
            for t in result.tables:
                if any(c.name == fk.column for c in t.columns):
                    src = t.name
                    break
            if src:
                links_js.append(
                    f'{{source:"{html.escape(src)}",target:"{html.escape(fk.references_table)}",label:"{html.escape(fk.column)}"}}'
                )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ER Diagram — {html.escape(result.database)}.{html.escape(result.schema)}</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; background: #1e1e2e; color: #cdd6f4; }}
h1 {{ text-align: center; padding: 1rem; margin: 0; font-size: 1.2rem; }}
svg {{ width: 100vw; height: calc(100vh - 3rem); display: block; }}
.node rect {{ fill: #313244; stroke: #89b4fa; stroke-width: 2; rx: 6; }}
.node text.title {{ fill: #89b4fa; font-weight: bold; font-size: 14px; }}
.node foreignObject table.cols {{ color: #cdd6f4; font-size: 11px; width: 100%; border-collapse: collapse; }}
.node foreignObject table.cols td {{ padding: 1px 4px; border-bottom: 1px solid #45475a; }}
.link {{ stroke: #f38ba8; stroke-width: 1.5; fill: none; marker-end: url(#arrow); }}
.link-label {{ fill: #a6adc8; font-size: 10px; }}
</style>
</head>
<body>
<h1>ER Diagram: {html.escape(result.database)} / {html.escape(result.schema)} ({len(result.tables)} tables, {len(result.relationships)} relationships)</h1>
<svg>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#f38ba8"/></marker></defs>
</svg>
<script>
const nodes = [{",".join(nodes_js)}];
const links = [{",".join(links_js)}];
const svg = d3.select("svg");
const width = window.innerWidth, height = window.innerHeight - 48;
const g = svg.append("g");
svg.call(d3.zoom().on("zoom", e => g.attr("transform", e.transform)));
const sim = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(links).id(d=>d.id).distance(200))
  .force("charge", d3.forceManyBody().strength(-400))
  .force("center", d3.forceCenter(width/2, height/2));
const link = g.selectAll(".link").data(links).join("line").attr("class","link");
const linkLabel = g.selectAll(".link-label").data(links).join("text").attr("class","link-label").text(d=>d.label);
const node = g.selectAll(".node").data(nodes).join("g").attr("class","node").call(d3.drag().on("start",ds).on("drag",dd).on("end",de));
node.append("rect").attr("width",180).attr("height",d=>60+d.cols.split("<tr>").length*16).attr("x",-90).attr("y",-20);
node.append("text").attr("class","title").attr("text-anchor","middle").attr("y",-4).text(d=>d.id);
node.append("foreignObject").attr("x",-86).attr("y",10).attr("width",172).attr("height",d=>d.cols.split("<tr>").length*16+8).html(d=>d.cols);
sim.on("tick",()=>{{
  link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y).attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
  linkLabel.attr("x",d=>(d.source.x+d.target.x)/2).attr("y",d=>(d.source.y+d.target.y)/2);
  node.attr("transform",d=>`translate(${{d.x}},${{d.y}})`);
}});
function ds(e,d){{if(!e.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y;}}
function dd(e,d){{d.fx=e.x;d.fy=e.y;}}
function de(e,d){{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}}
</script>
</body>
</html>"""


# ── Helpers ─────────────────────────────────────────────────────────────


def _format_bytes(n: int) -> str:
    """Format bytes into human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} PB"


def format_schema_summary(result: SchemaResult) -> str:
    """One-line summary of a SchemaResult."""
    total_cols = sum(len(t.columns) for t in result.tables)
    total_fks = len(result.relationships)
    return (
        f"Schema {result.database}.{result.schema}: "
        f"{len(result.tables)} tables, {total_cols} columns, {total_fks} foreign keys"
    )
