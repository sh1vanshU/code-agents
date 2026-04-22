"""Tests for code_agents.query_optimizer."""

import pytest
from code_agents.api.query_optimizer import QueryOptimizer, QueryAnalysisResult, format_query_report


class TestQueryOptimizer:
    def test_detects_select_star(self):
        result = QueryOptimizer().analyze("SELECT * FROM users")
        assert any(i.issue_type == "select_star" for i in result.issues)

    def test_no_select_star_for_specific_columns(self):
        result = QueryOptimizer().analyze("SELECT id, name FROM users")
        assert not any(i.issue_type == "select_star" for i in result.issues)

    def test_detects_no_limit(self):
        result = QueryOptimizer().analyze("SELECT id FROM users WHERE active = true")
        assert any(i.issue_type == "no_limit" for i in result.issues)

    def test_no_limit_ok_with_limit(self):
        result = QueryOptimizer().analyze("SELECT id FROM users LIMIT 10")
        assert not any(i.issue_type == "no_limit" for i in result.issues)

    def test_detects_leading_wildcard(self):
        result = QueryOptimizer().analyze("SELECT * FROM users WHERE name LIKE '%test'")
        assert any(i.issue_type == "like_wildcard" for i in result.issues)

    def test_trailing_wildcard_ok(self):
        result = QueryOptimizer().analyze("SELECT * FROM users WHERE name LIKE 'test%'")
        assert not any(i.issue_type == "like_wildcard" for i in result.issues)

    def test_detects_missing_index(self):
        result = QueryOptimizer().analyze("SELECT * FROM users WHERE email = 'test@test.com'")
        assert any(i.issue_type == "missing_index" for i in result.issues)

    def test_extracts_tables(self):
        result = QueryOptimizer().analyze("SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id")
        assert "users" in result.tables
        assert "orders" in result.tables

    def test_detects_subquery(self):
        result = QueryOptimizer().analyze("SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)")
        assert any(i.issue_type == "subquery" for i in result.issues)

    def test_dangerous_update_without_where(self):
        result = QueryOptimizer().analyze("UPDATE users SET active = false")
        assert any(i.issue_type == "full_scan" and i.severity == "high" for i in result.issues)

    def test_format_output(self):
        result = QueryAnalysisResult(query="SELECT 1", summary="0 issues")
        output = format_query_report(result)
        assert "Query Optimizer" in output
