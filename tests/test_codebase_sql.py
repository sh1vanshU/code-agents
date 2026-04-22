"""Tests for codebase_sql.py — SQL-like queries over AST."""

import pytest

from code_agents.analysis.codebase_sql import (
    CodebaseSQL,
    QueryResult,
    CodeEntity,
    format_result,
)


@pytest.fixture
def engine(tmp_path):
    return CodebaseSQL(str(tmp_path))


SAMPLE_FILES = {
    "app.py": '''def process_data(items):
    for item in items:
        if item.valid:
            if item.active:
                yield item

def simple_func():
    return 42

class UserService:
    def get_user(self, user_id):
        return db.find(user_id)
''',
    "utils.py": '''def helper(x, y):
    return x + y

def complex_validator(data, schema, strict):
    if data:
        if schema:
            for rule in schema.rules:
                if not rule.check(data):
                    return False
    return True
''',
}


class TestBuildIndex:
    def test_indexes_functions(self, engine):
        index = engine.build_index(SAMPLE_FILES)
        funcs = [e for e in index.entities if e.kind == "function"]
        names = [f.name for f in funcs]
        assert "process_data" in names
        assert "simple_func" in names

    def test_indexes_classes(self, engine):
        index = engine.build_index(SAMPLE_FILES)
        classes = [e for e in index.entities if e.kind == "class"]
        assert any(c.name == "UserService" for c in classes)

    def test_computes_complexity(self, engine):
        index = engine.build_index(SAMPLE_FILES)
        funcs = {e.name: e for e in index.entities if e.kind == "function"}
        assert funcs["process_data"].complexity > funcs["simple_func"].complexity


class TestQuery:
    def test_select_all_functions(self, engine):
        engine.build_index(SAMPLE_FILES)
        result = engine.analyze("SELECT * FROM functions")
        assert isinstance(result, QueryResult)
        assert result.total_matches >= 4

    def test_where_complexity(self, engine):
        engine.build_index(SAMPLE_FILES)
        result = engine.analyze("SELECT * FROM functions WHERE complexity > 2")
        assert all(e.complexity > 2 for e in result.entities)

    def test_order_by(self, engine):
        engine.build_index(SAMPLE_FILES)
        result = engine.analyze("SELECT * FROM functions ORDER BY complexity DESC")
        if len(result.entities) >= 2:
            assert result.entities[0].complexity >= result.entities[1].complexity

    def test_limit(self, engine):
        engine.build_index(SAMPLE_FILES)
        result = engine.analyze("SELECT * FROM functions LIMIT 2")
        assert len(result.entities) <= 2

    def test_where_name_like(self, engine):
        engine.build_index(SAMPLE_FILES)
        result = engine.analyze("SELECT * FROM functions WHERE name LIKE %helper%")
        assert all("helper" in e.name for e in result.entities)

    def test_format_result(self, engine):
        engine.build_index(SAMPLE_FILES)
        result = engine.analyze("SELECT * FROM functions")
        text = format_result(result)
        assert "Results:" in text
