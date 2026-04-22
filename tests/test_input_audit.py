"""Tests for code_agents.input_audit — input validation coverage auditor."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from code_agents.security.input_audit import (
    InputAuditor,
    InputFinding,
    format_input_report,
    input_report_to_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp: str, name: str, content: str) -> Path:
    p = Path(tmp) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# InputFinding dataclass
# ---------------------------------------------------------------------------


class TestInputFinding:
    def test_basic_creation(self):
        f = InputFinding(
            file="api.py", line=5, endpoint="/users",
            issue="No validation", severity="high",
            suggestion="Add Pydantic model",
        )
        assert f.file == "api.py"
        assert f.endpoint == "/users"


# ---------------------------------------------------------------------------
# Endpoint detection — Python
# ---------------------------------------------------------------------------


class TestPythonEndpoints:
    def test_fastapi_post(self, tmp_path):
        code = '''
from fastapi import FastAPI
app = FastAPI()

@app.post("/users")
def create_user(request):
    name = request.json["name"]
    return {"ok": True}
'''
        _write(str(tmp_path), "main.py", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert any("/users" in f.endpoint for f in findings)

    def test_fastapi_with_pydantic_no_body_finding(self, tmp_path):
        code = '''
from fastapi import FastAPI
from pydantic import BaseModel
app = FastAPI()

class UserCreate(BaseModel):
    name: str

@app.post("/users")
def create_user(user: UserCreate):
    return {"ok": True}
'''
        _write(str(tmp_path), "main.py", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        body_findings = [f for f in findings if "body validation" in f.issue.lower()]
        assert len(body_findings) == 0

    def test_flask_put(self, tmp_path):
        code = '''
from flask import Flask
app = Flask(__name__)

@app.put("/items")
def update_item():
    data = request.get_json()
    return {"ok": True}
'''
        _write(str(tmp_path), "app.py", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert len(findings) > 0


# ---------------------------------------------------------------------------
# Endpoint detection — JavaScript
# ---------------------------------------------------------------------------


class TestJSEndpoints:
    def test_express_post(self, tmp_path):
        code = '''
const express = require('express');
const app = express();

app.post('/api/users', (req, res) => {
    const name = req.body.name;
    res.json({ ok: true });
});
'''
        _write(str(tmp_path), "server.js", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert len(findings) > 0

    def test_express_with_joi_validation(self, tmp_path):
        code = '''
const Joi = require('joi');
app.post('/api/users', (req, res) => {
    const schema = Joi.object({ name: Joi.string().required() });
    const result = schema.validate(req.body);
    res.json({ ok: true });
});
'''
        _write(str(tmp_path), "server.js", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        body_findings = [f for f in findings if "body validation" in f.issue.lower()]
        assert len(body_findings) == 0


# ---------------------------------------------------------------------------
# Endpoint detection — Java
# ---------------------------------------------------------------------------


class TestJavaEndpoints:
    def test_spring_post(self, tmp_path):
        code = '''
@PostMapping("/api/orders")
public ResponseEntity<Order> createOrder(@RequestBody Map<String, Object> data) {
    String item = (String) data.get("item");
    return ResponseEntity.ok(new Order());
}
'''
        _write(str(tmp_path), "OrderController.java", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert len(findings) > 0

    def test_spring_with_valid_annotation(self, tmp_path):
        code = '''
@PostMapping("/api/orders")
public ResponseEntity<Order> createOrder(@Valid @RequestBody OrderRequest data) {
    return ResponseEntity.ok(new Order());
}
'''
        _write(str(tmp_path), "OrderController.java", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        body_findings = [f for f in findings if "body validation" in f.issue.lower()]
        assert len(body_findings) == 0


# ---------------------------------------------------------------------------
# SQL injection detection
# ---------------------------------------------------------------------------


class TestSQLInjection:
    def test_string_concat_in_query(self, tmp_path):
        code = '''
@app.post("/search")
def search():
    db.execute("SELECT * FROM users WHERE name = '" + request.form["name"] + "'")
    return {"ok": True}
'''
        _write(str(tmp_path), "search.py", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        sql_findings = [f for f in findings if "SQL" in f.issue]
        assert len(sql_findings) > 0

    def test_fstring_in_query(self, tmp_path):
        code = '''
@app.post("/users")
def find_user():
    db.execute(f"SELECT * FROM users WHERE id = {user_id}")
    return {"ok": True}
'''
        _write(str(tmp_path), "api.py", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        sql_findings = [f for f in findings if "SQL" in f.issue]
        assert len(sql_findings) > 0

    def test_parameterized_query_no_finding(self, tmp_path):
        code = '''
@app.post("/users")
def find_user():
    from pydantic import BaseModel
    db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return {"ok": True}
'''
        _write(str(tmp_path), "api.py", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        sql_findings = [f for f in findings if "SQL" in f.issue]
        assert len(sql_findings) == 0


# ---------------------------------------------------------------------------
# Length limits
# ---------------------------------------------------------------------------


class TestLengthLimits:
    def test_no_max_length(self, tmp_path):
        code = '''
@app.post("/comments")
def add_comment():
    text = request.json["text"]
    return {"ok": True}
'''
        _write(str(tmp_path), "comments.py", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        length_findings = [f for f in findings if "length" in f.issue.lower()]
        assert len(length_findings) > 0

    def test_with_max_length(self, tmp_path):
        code = '''
@app.post("/comments")
def add_comment():
    text = Field(max_length=500)
    return {"ok": True}
'''
        _write(str(tmp_path), "comments.py", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        length_findings = [f for f in findings if "length" in f.issue.lower()]
        assert len(length_findings) == 0


# ---------------------------------------------------------------------------
# Empty project / test dirs skipped
# ---------------------------------------------------------------------------


class TestEmptyProject:
    def test_no_findings_empty_dir(self, tmp_path):
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert findings == []

    def test_test_dirs_skipped(self, tmp_path):
        code = '@app.post("/test")\ndef test_endpoint():\n    pass\n'
        _write(str(tmp_path), "tests/test_api.py", code)
        auditor = InputAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert findings == []


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


class TestFormatters:
    def test_text_report_empty(self):
        report = format_input_report([])
        assert "No input validation issues" in report

    def test_text_report_with_findings(self):
        findings = [
            InputFinding("api.py", 5, "/users", "No validation",
                         "high", "Add Pydantic"),
        ]
        report = format_input_report(findings)
        assert "1 finding" in report
        assert "api.py:5" in report
        assert "/users" in report

    def test_json_report_structure(self):
        findings = [
            InputFinding("x.py", 10, "/ep", "issue", "critical", "fix"),
        ]
        data = input_report_to_json(findings)
        assert data["total"] == 1
        assert "critical" in data["by_severity"]
        assert data["findings"][0]["endpoint"] == "/ep"

    def test_json_report_empty(self):
        data = input_report_to_json([])
        assert data["total"] == 0
        assert data["findings"] == []

    def test_severity_counts(self):
        findings = [
            InputFinding("a.py", 1, "/a", "i1", "critical", "s"),
            InputFinding("b.py", 2, "/b", "i2", "high", "s"),
            InputFinding("c.py", 3, "/c", "i3", "critical", "s"),
        ]
        data = input_report_to_json(findings)
        assert data["by_severity"]["critical"] == 2
        assert data["by_severity"]["high"] == 1
