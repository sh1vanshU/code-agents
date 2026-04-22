"""Tests for the code audit module."""

from __future__ import annotations

import os
import pytest

from code_agents.reviews.code_audit import (
    CodeAuditor, AuditResult, AuditFinding, run_code_audit,
)


class TestCodeAuditor:
    """Test CodeAuditor methods."""

    def test_init(self, tmp_path):
        auditor = CodeAuditor(cwd=str(tmp_path))
        assert auditor.cwd == str(tmp_path)

    def test_audit_empty_dir(self, tmp_path):
        auditor = CodeAuditor(cwd=str(tmp_path))
        result = auditor.audit()
        assert isinstance(result, AuditResult)
        assert result.files_scanned == 0

    def test_audit_bare_except(self, tmp_path):
        code = '''
def risky():
    try:
        do_something()
    except:
        pass
'''
        (tmp_path / "bad.py").write_text(code)
        auditor = CodeAuditor(cwd=str(tmp_path))
        result = auditor.audit(categories=["error_handling"])
        error_findings = [f for f in result.findings if f.category == "error_handling"]
        assert len(error_findings) >= 1
        assert any("Bare except" in f.message for f in error_findings)

    def test_audit_logging_patterns(self, tmp_path):
        code = '''
import logging
logger = logging.getLogger(__name__)

def foo():
    logger.info(f"Processing {item}")
    print("debug output")
'''
        (tmp_path / "log_issues.py").write_text(code)
        auditor = CodeAuditor(cwd=str(tmp_path))
        result = auditor.audit(categories=["logging"])
        log_findings = [f for f in result.findings if f.category == "logging"]
        assert len(log_findings) >= 1

    def test_audit_type_hints(self, tmp_path):
        code = '''
def add(a, b):
    return a + b

def typed_func(x: int) -> int:
    return x + 1
'''
        (tmp_path / "hints.py").write_text(code)
        auditor = CodeAuditor(cwd=str(tmp_path))
        result = auditor.audit(categories=["type_hints"])
        hint_findings = [f for f in result.findings if f.category == "type_hints"]
        # 'add' is missing return type and param types
        assert len(hint_findings) >= 1

    def test_audit_imports(self, tmp_path):
        code = '''
from os import *
import json
import json
'''
        (tmp_path / "imports.py").write_text(code)
        auditor = CodeAuditor(cwd=str(tmp_path))
        result = auditor.audit(categories=["imports"])
        import_findings = [f for f in result.findings if f.category == "imports"]
        assert any("Wildcard" in f.message for f in import_findings)
        assert any("Duplicate" in f.message for f in import_findings)

    def test_convenience_function(self, tmp_path):
        (tmp_path / "simple.py").write_text("def hello():\n    return 'hi'\n")
        result = run_code_audit(cwd=str(tmp_path))
        assert isinstance(result, dict)
        assert "files_scanned" in result
        assert "scores" in result
