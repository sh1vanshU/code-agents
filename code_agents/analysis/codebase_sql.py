"""Codebase SQL — SQL-like queries over AST structures."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Any

logger = logging.getLogger("code_agents.analysis.codebase_sql")


@dataclass
class CodeEntity:
    """A queryable code entity (function, class, variable, etc.)."""
    name: str = ""
    kind: str = ""  # function, class, method, variable, import
    file_path: str = ""
    line_number: int = 0
    end_line: int = 0
    complexity: int = 0
    lines_of_code: int = 0
    params: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""
    parent: str = ""  # parent class/module


@dataclass
class QueryResult:
    """Result of a codebase query."""
    query: str = ""
    entities: list[CodeEntity] = field(default_factory=list)
    total_matches: int = 0
    execution_time_ms: float = 0.0
    columns: list[str] = field(default_factory=list)


@dataclass
class CodebaseIndex:
    """Indexed codebase for querying."""
    entities: list[CodeEntity] = field(default_factory=list)
    files_indexed: int = 0
    total_entities: int = 0


FUNC_RE = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE)
CLASS_RE = re.compile(r"^(\s*)class\s+(\w+)(?:\(([^)]*)\))?:", re.MULTILINE)
DECORATOR_RE = re.compile(r"^(\s*)@(\w[\w.]*)", re.MULTILINE)
IMPORT_RE = re.compile(r"^(?:from\s+(\S+)\s+)?import\s+(.+)$", re.MULTILINE)
COMPLEXITY_KEYWORDS = re.compile(r"\b(if|elif|for|while|except|and|or)\b")

# Simple SQL-like parser
SELECT_RE = re.compile(
    r"SELECT\s+(.+?)\s+FROM\s+(\w+)"
    r"(?:\s+WHERE\s+(.+?))?"
    r"(?:\s+ORDER\s+BY\s+(\w+)(?:\s+(ASC|DESC))?)?"
    r"(?:\s+LIMIT\s+(\d+))?\s*$",
    re.IGNORECASE,
)

CONDITION_RE = re.compile(
    r"(\w+)\s*(=|!=|>|<|>=|<=|LIKE|IN|NOT IN)\s*(.+)",
    re.IGNORECASE,
)


class CodebaseSQL:
    """Execute SQL-like queries over codebase AST."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.index = CodebaseIndex()

    def build_index(self, file_contents: dict[str, str]) -> CodebaseIndex:
        """Index all source files for querying."""
        logger.info("Indexing %d files", len(file_contents))
        entities = []
        for fpath, content in file_contents.items():
            entities.extend(self._index_file(fpath, content))
        self.index = CodebaseIndex(
            entities=entities,
            files_indexed=len(file_contents),
            total_entities=len(entities),
        )
        logger.info("Indexed %d entities from %d files", len(entities), len(file_contents))
        return self.index

    def analyze(self, query: str, file_contents: Optional[dict[str, str]] = None) -> QueryResult:
        """Execute a SQL-like query. Builds index if needed."""
        import time
        start = time.time()
        logger.info("Executing query: %s", query[:100])

        if file_contents and not self.index.entities:
            self.build_index(file_contents)

        parsed = self._parse_query(query)
        if not parsed:
            return QueryResult(query=query, entities=[], total_matches=0)

        results = self._execute_query(parsed)
        elapsed = (time.time() - start) * 1000

        return QueryResult(
            query=query,
            entities=results,
            total_matches=len(results),
            execution_time_ms=round(elapsed, 2),
            columns=parsed.get("select", ["*"]),
        )

    def _index_file(self, fpath: str, content: str) -> list[CodeEntity]:
        """Index a single file."""
        entities = []
        lines = content.splitlines()

        # Index functions
        for m in FUNC_RE.finditer(content):
            indent = len(m.group(1))
            name = m.group(2)
            params = [p.strip().split(":")[0].strip()
                      for p in m.group(3).split(",") if p.strip()]
            line_num = content[:m.start()].count("\n") + 1
            body = self._get_body(lines, line_num - 1, indent)
            complexity = len(COMPLEXITY_KEYWORDS.findall(body))
            end_line = line_num + body.count("\n")

            entities.append(CodeEntity(
                name=name, kind="function", file_path=fpath,
                line_number=line_num, end_line=end_line,
                complexity=complexity + 1,
                lines_of_code=end_line - line_num + 1,
                params=[p for p in params if p not in ("self", "cls")],
                docstring=self._extract_docstring(lines, line_num),
            ))

        # Index classes
        for m in CLASS_RE.finditer(content):
            name = m.group(2)
            line_num = content[:m.start()].count("\n") + 1
            entities.append(CodeEntity(
                name=name, kind="class", file_path=fpath,
                line_number=line_num,
            ))

        return entities

    def _get_body(self, lines: list[str], start_idx: int, indent: int) -> str:
        """Get function body text."""
        body_lines = []
        for i in range(start_idx + 1, min(start_idx + 200, len(lines))):
            line = lines[i]
            if line.strip() and not line.strip().startswith("#"):
                line_indent = len(line) - len(line.lstrip())
                if line_indent <= indent:
                    break
            body_lines.append(line)
        return "\n".join(body_lines)

    def _extract_docstring(self, lines: list[str], func_line: int) -> str:
        """Extract docstring from function."""
        if func_line < len(lines):
            next_line = lines[func_line].strip() if func_line < len(lines) else ""
            if next_line.startswith('"""') or next_line.startswith("'''"):
                return next_line.strip("\"' ")
        return ""

    def _parse_query(self, query: str) -> Optional[dict]:
        """Parse SQL-like query."""
        m = SELECT_RE.match(query.strip())
        if not m:
            logger.warning("Failed to parse query: %s", query[:80])
            return None

        select_cols = [c.strip() for c in m.group(1).split(",")]
        from_table = m.group(2)
        where_clause = m.group(3)
        order_by = m.group(4)
        order_dir = (m.group(5) or "ASC").upper()
        limit = int(m.group(6)) if m.group(6) else None

        conditions = []
        if where_clause:
            # Split on AND
            parts = re.split(r"\s+AND\s+", where_clause, flags=re.IGNORECASE)
            for part in parts:
                cm = CONDITION_RE.match(part.strip())
                if cm:
                    conditions.append({
                        "field": cm.group(1),
                        "op": cm.group(2).upper(),
                        "value": cm.group(3).strip().strip("'\""),
                    })

        return {
            "select": select_cols,
            "from": from_table,
            "conditions": conditions,
            "order_by": order_by,
            "order_dir": order_dir,
            "limit": limit,
        }

    def _execute_query(self, parsed: dict) -> list[CodeEntity]:
        """Execute parsed query against index."""
        # Filter by table (kind)
        table = parsed["from"].lower()
        kind_map = {
            "functions": "function", "function": "function",
            "classes": "class", "class": "class",
            "methods": "function", "entities": None,
        }
        target_kind = kind_map.get(table)
        entities = self.index.entities
        if target_kind:
            entities = [e for e in entities if e.kind == target_kind]

        # Apply WHERE conditions
        for cond in parsed["conditions"]:
            entities = [e for e in entities if self._matches_condition(e, cond)]

        # Apply ORDER BY
        if parsed["order_by"]:
            field = parsed["order_by"]
            reverse = parsed["order_dir"] == "DESC"
            entities.sort(
                key=lambda e: getattr(e, field, 0) if hasattr(e, field) else 0,
                reverse=reverse,
            )

        # Apply LIMIT
        if parsed["limit"]:
            entities = entities[:parsed["limit"]]

        return entities

    def _matches_condition(self, entity: CodeEntity, cond: dict) -> bool:
        """Check if entity matches a condition."""
        field_val = getattr(entity, cond["field"], None)
        if field_val is None:
            return False
        target = cond["value"]
        op = cond["op"]

        try:
            if isinstance(field_val, int):
                target_num = int(target)
                if op == "=":
                    return field_val == target_num
                if op == "!=":
                    return field_val != target_num
                if op == ">":
                    return field_val > target_num
                if op == "<":
                    return field_val < target_num
                if op == ">=":
                    return field_val >= target_num
                if op == "<=":
                    return field_val <= target_num
        except ValueError:
            pass

        str_val = str(field_val)
        if op == "=":
            return str_val == target
        if op == "!=":
            return str_val != target
        if op == "LIKE":
            pattern = target.replace("%", ".*")
            return bool(re.match(pattern, str_val, re.IGNORECASE))
        return False


def format_result(result: QueryResult) -> str:
    """Format query result as text."""
    lines = [
        f"Query: {result.query}",
        f"Results: {result.total_matches} ({result.execution_time_ms}ms)",
        "",
    ]
    for e in result.entities[:50]:
        lines.append(f"  {e.kind} {e.name} ({e.file_path}:{e.line_number}) complexity={e.complexity} loc={e.lines_of_code}")
    return "\n".join(lines)
