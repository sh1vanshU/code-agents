"""Tests for the naming convention auditor."""

from __future__ import annotations

import os
import pytest

from code_agents.reviews.naming_audit import (
    NamingAuditor, NamingFinding, format_naming_report,
)


class TestNamingAuditor:
    """Test NamingAuditor methods."""

    def test_init(self, tmp_path):
        auditor = NamingAuditor(cwd=str(tmp_path))
        assert auditor.cwd == str(tmp_path)

    def test_audit_empty_dir(self, tmp_path):
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        assert findings == []

    def test_audit_clean_file(self, tmp_path):
        (tmp_path / "clean.py").write_text(
            "def process_data(items):\n"
            "    result = []\n"
            "    for item in items:\n"
            "        result.append(item)\n"
            "    return result\n"
        )
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor.audit()
        # All snake_case, no abbreviations, no single-char outside loops
        camel_findings = [f for f in findings if "camelCase" in f.issue]
        assert len(camel_findings) == 0

    def test_audit_specific_file(self, tmp_path):
        (tmp_path / "target.py").write_text("def processData():\n    pass\n")
        (tmp_path / "other.py").write_text("def handleRequest():\n    pass\n")
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor.audit(target="target.py")
        files = {f.file for f in findings}
        assert "other.py" not in files


class TestCheckConsistency:
    """Test naming style consistency checks."""

    def test_camel_case_function_in_python(self, tmp_path):
        (tmp_path / "mixed.py").write_text(
            "def processData(inputVal):\n"
            "    return inputVal\n"
        )
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor._check_consistency(str(tmp_path / "mixed.py"))
        camel_findings = [f for f in findings if "camelCase" in f.issue]
        assert len(camel_findings) >= 1

    def test_snake_case_class_in_python(self, tmp_path):
        (tmp_path / "cls.py").write_text("class my_data_class:\n    pass\n")
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor._check_consistency(str(tmp_path / "cls.py"))
        class_findings = [f for f in findings if "Class" in f.issue]
        assert len(class_findings) >= 1

    def test_pure_snake_case_ok(self, tmp_path):
        (tmp_path / "ok.py").write_text(
            "def get_user():\n    pass\n\n"
            "def set_value():\n    pass\n"
        )
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor._check_consistency(str(tmp_path / "ok.py"))
        assert len(findings) == 0

    def test_js_mixed_styles(self, tmp_path):
        (tmp_path / "mixed.js").write_text(
            "const getUserData = () => {};\n"
            "const set_value = () => {};\n"
            "const fetchItems = () => {};\n"
        )
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor._check_consistency(str(tmp_path / "mixed.js"))
        mixed_findings = [f for f in findings if "Mixed" in f.issue]
        assert len(mixed_findings) >= 1


class TestCheckAbbreviations:
    """Test abbreviation detection."""

    def test_detects_abbreviations(self, tmp_path):
        (tmp_path / "abbr.py").write_text(
            "cfg = load_config()\n"
            "mgr = get_manager()\n"
        )
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor._check_abbreviations(str(tmp_path / "abbr.py"))
        names = [f.name for f in findings]
        assert "cfg" in names or "mgr" in names

    def test_ignores_comments(self, tmp_path):
        (tmp_path / "commented.py").write_text(
            "# cfg = old config\n"
            "config = load_config()\n"
        )
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor._check_abbreviations(str(tmp_path / "commented.py"))
        names = [f.name for f in findings]
        assert "cfg" not in names


class TestCheckSingleChar:
    """Test single-character variable detection."""

    def test_detects_single_char_outside_loop(self, tmp_path):
        (tmp_path / "single.py").write_text(
            "x = compute_value()\n"
            "y = transform(x)\n"
        )
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor._check_single_char(str(tmp_path / "single.py"))
        names = [f.name for f in findings]
        assert "x" in names or "y" in names

    def test_allows_loop_variables(self, tmp_path):
        (tmp_path / "loop.py").write_text(
            "for i in range(10):\n"
            "    print(i)\n"
        )
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor._check_single_char(str(tmp_path / "loop.py"))
        loop_findings = [f for f in findings if f.name == "i"]
        assert len(loop_findings) == 0

    def test_ignores_underscore(self, tmp_path):
        (tmp_path / "ignore.py").write_text("_ = unused_value()\n")
        auditor = NamingAuditor(cwd=str(tmp_path))
        findings = auditor._check_single_char(str(tmp_path / "ignore.py"))
        assert all(f.name != "_" for f in findings)


class TestDetectStyle:
    """Test dominant style detection."""

    def test_snake_case_dominant(self, tmp_path):
        (tmp_path / "snake.py").write_text(
            "def get_user():\n    pass\n"
            "def set_value():\n    pass\n"
            "def load_config():\n    pass\n"
        )
        auditor = NamingAuditor(cwd=str(tmp_path))
        style = auditor._detect_style()
        assert style == "snake_case"


class TestNameConversions:
    """Test static name conversion helpers."""

    def test_is_camel_case(self):
        assert NamingAuditor._is_camel_case("processData")
        assert NamingAuditor._is_camel_case("getValue")
        assert not NamingAuditor._is_camel_case("process_data")
        assert not NamingAuditor._is_camel_case("ProcessData")  # PascalCase
        assert not NamingAuditor._is_camel_case("x")

    def test_to_snake_case(self):
        assert NamingAuditor._to_snake_case("processData") == "process_data"
        assert NamingAuditor._to_snake_case("getValue") == "get_value"
        assert NamingAuditor._to_snake_case("HTMLParser") == "html_parser"

    def test_to_camel_case(self):
        assert NamingAuditor._to_camel_case("process_data") == "processData"
        assert NamingAuditor._to_camel_case("get_value") == "getValue"

    def test_to_pascal_case(self):
        assert NamingAuditor._to_pascal_case("my_class") == "MyClass"
        assert NamingAuditor._to_pascal_case("data_handler") == "DataHandler"


class TestFormatNamingReport:
    """Test the report formatter."""

    def test_empty(self):
        result = format_naming_report([])
        assert "No naming issues" in result

    def test_with_findings(self):
        findings = [
            NamingFinding(
                file="test.py", line=1, name="processData",
                issue="camelCase", suggestion="process_data", severity="warning",
            ),
        ]
        result = format_naming_report(findings)
        assert "processData" in result
        assert "process_data" in result
        assert "1 naming issue" in result

    def test_severity_summary(self):
        findings = [
            NamingFinding(file="a.py", line=1, name="x", issue="single char",
                         suggestion="value", severity="warning"),
            NamingFinding(file="b.py", line=2, name="cfg", issue="abbrev",
                         suggestion="config", severity="info"),
        ]
        result = format_naming_report(findings)
        assert "1 warnings" in result
        assert "1 info" in result
