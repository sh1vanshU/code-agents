"""Tests for code_agents.code_explainer — Code Explanation Engine."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.knowledge.code_explainer import (
    CodeExplainer,
    Explanation,
    format_explanation,
    _COMPLEXITY_KEYWORDS,
    _SIDE_EFFECT_RES,
    _resolve_path,
    _grep_callers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_project(tmp_path):
    """Create a tiny project with a few Python files."""
    src = tmp_path / "src"
    src.mkdir()

    (src / "payment.py").write_text(textwrap.dedent("""\
        import requests
        import logging

        logger = logging.getLogger(__name__)


        def validate_amount(amount):
            if amount <= 0:
                raise ValueError("Amount must be positive")
            if amount > 100000:
                raise ValueError("Amount exceeds limit")
            return True


        def process_payment(order_id, amount):
            validate_amount(amount)
            response = requests.post("https://api.acquirer.com/charge", json={
                "order_id": order_id,
                "amount": amount,
            })
            if response.status_code != 200:
                logger.error("Payment failed for %s", order_id)
                return False
            logger.info("Payment succeeded for %s", order_id)
            return True


        class PaymentProcessor:
            def __init__(self, config):
                self.config = config

            def charge(self, order_id, amount):
                return process_payment(order_id, amount)
    """))

    (src / "api.py").write_text(textwrap.dedent("""\
        from src.payment import process_payment


        def api_handler(request):
            order_id = request.get("order_id")
            amount = request.get("amount")
            result = process_payment(order_id, amount)
            return {"success": result}
    """))

    (src / "utils.py").write_text(textwrap.dedent("""\
        import os
        import subprocess


        def run_command(cmd):
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout


        def write_file(path, content):
            with open(path, "w") as f:
                f.write(content)


        def complex_function(data):
            if not data:
                return None
            for item in data:
                if item.get("type") == "a":
                    if item.get("status") == "active":
                        for sub in item.get("subs", []):
                            if sub > 0:
                                try:
                                    result = sub * 2
                                    if result > 100:
                                        while result > 100:
                                            result = result // 2
                                    elif result < 0:
                                        raise ValueError("negative")
                                except ValueError:
                                    pass
                elif item.get("type") == "b":
                    if item.get("status") == "active" or item.get("status") == "pending":
                        pass
            return data
    """))

    return tmp_path


@pytest.fixture
def explainer(tmp_project):
    return CodeExplainer(cwd=str(tmp_project))


# ---------------------------------------------------------------------------
# Tests: _resolve_path
# ---------------------------------------------------------------------------

class TestResolvePath:
    def test_absolute_path(self, tmp_path):
        p = _resolve_path(str(tmp_path / "foo.py"), str(tmp_path))
        assert p == tmp_path / "foo.py"

    def test_relative_path(self, tmp_path):
        p = _resolve_path("foo.py", str(tmp_path))
        assert p == tmp_path / "foo.py"


# ---------------------------------------------------------------------------
# Tests: CodeExplainer._extract_code_block
# ---------------------------------------------------------------------------

class TestExtractCodeBlock:
    def test_whole_file(self, explainer):
        lines = ["line1", "line2", "line3"]
        result = explainer._extract_code_block(lines, 0, 0)
        assert result == "line1\nline2\nline3"

    def test_specific_range(self, explainer):
        lines = ["line1", "line2", "line3", "line4", "line5"]
        result = explainer._extract_code_block(lines, 2, 4)
        assert result == "line2\nline3\nline4"

    def test_start_only(self, explainer):
        lines = ["line1", "line2", "line3"]
        result = explainer._extract_code_block(lines, 2, 3)
        assert result == "line2\nline3"

    def test_out_of_bounds(self, explainer):
        lines = ["line1", "line2"]
        result = explainer._extract_code_block(lines, 1, 100)
        assert result == "line1\nline2"


# ---------------------------------------------------------------------------
# Tests: CodeExplainer._find_function_range
# ---------------------------------------------------------------------------

class TestFindFunctionRange:
    def test_simple_function(self, explainer):
        lines = [
            "def foo():",
            "    return 42",
            "",
            "def bar():",
            "    return 99",
        ]
        start, end = explainer._find_function_range(lines, "foo")
        assert start == 1
        assert end == 3  # Ends before bar

    def test_async_function(self, explainer):
        lines = [
            "async def fetch():",
            "    return await get()",
            "",
            "def other():",
            "    pass",
        ]
        start, end = explainer._find_function_range(lines, "fetch")
        assert start == 1

    def test_not_found(self, explainer):
        lines = ["def foo():", "    pass"]
        start, end = explainer._find_function_range(lines, "nonexistent")
        assert start == 0
        assert end == 0

    def test_last_function_in_file(self, explainer):
        lines = [
            "def foo():",
            "    return 1",
            "",
            "def bar():",
            "    x = 1",
            "    return x",
        ]
        start, end = explainer._find_function_range(lines, "bar")
        assert start == 4
        assert end == 6  # last line of file


# ---------------------------------------------------------------------------
# Tests: CodeExplainer._identify_side_effects
# ---------------------------------------------------------------------------

class TestIdentifySideEffects:
    def test_db_write(self, explainer):
        code = "db.execute('INSERT INTO ...')"
        effects = explainer._identify_side_effects(code)
        assert any("DB write" in e for e in effects)

    def test_api_call(self, explainer):
        code = "requests.post('https://api.example.com', json=data)"
        effects = explainer._identify_side_effects(code)
        assert any("API call" in e for e in effects)

    def test_file_io(self, explainer):
        code = "with open('file.txt', 'w') as f:\n    f.write('data')"
        effects = explainer._identify_side_effects(code)
        assert any("File I/O" in e for e in effects)

    def test_subprocess(self, explainer):
        code = "subprocess.run(['ls', '-la'])"
        effects = explainer._identify_side_effects(code)
        assert any("Subprocess" in e for e in effects)

    def test_logging(self, explainer):
        code = "logger.info('something happened')"
        effects = explainer._identify_side_effects(code)
        assert any("Logging" in e for e in effects)

    def test_console_output(self, explainer):
        code = "print('hello world')"
        effects = explainer._identify_side_effects(code)
        assert any("Console output" in e for e in effects)

    def test_no_side_effects(self, explainer):
        code = "x = 1 + 2\nreturn x"
        effects = explainer._identify_side_effects(code)
        assert effects == []

    def test_cache_write(self, explainer):
        code = "cache.set('key', 'value')"
        effects = explainer._identify_side_effects(code)
        assert any("Cache write" in e for e in effects)

    def test_event(self, explainer):
        code = "publish_event('order.completed', data)"
        effects = explainer._identify_side_effects(code)
        assert any("Event/message" in e for e in effects)


# ---------------------------------------------------------------------------
# Tests: CodeExplainer._assess_complexity
# ---------------------------------------------------------------------------

class TestAssessComplexity:
    def test_simple(self, explainer):
        code = "x = 1\nreturn x"
        assert explainer._assess_complexity(code) == "simple"

    def test_moderate(self, explainer):
        code = "\n".join([
            "if a:", "  for b in c:", "    if d:", "      while e:",
            "        try:", "          if f:", "            pass",
            "        except:", "          if g or h:", "            pass",
        ])
        assert explainer._assess_complexity(code) == "moderate"

    def test_complex(self, tmp_project, explainer):
        # Read the complex_function from utils.py
        code = (tmp_project / "src" / "utils.py").read_text()
        # The whole file has many branches
        assert explainer._assess_complexity(code) in ("moderate", "complex")

    def test_thresholds(self, explainer):
        # Exactly 4 keywords = simple
        code = "if a:\n  for b in c:\n    if d:\n      while e:\n        pass"
        assert explainer._assess_complexity(code) == "simple"


# ---------------------------------------------------------------------------
# Tests: CodeExplainer._detect_primary_function
# ---------------------------------------------------------------------------

class TestDetectPrimaryFunction:
    def test_detects_function(self, explainer):
        code = "def process_payment(order_id, amount):\n    pass"
        assert explainer._detect_primary_function(code) == "process_payment"

    def test_detects_class(self, explainer):
        code = "class PaymentProcessor:\n    pass"
        assert explainer._detect_primary_function(code) == "PaymentProcessor"

    def test_empty(self, explainer):
        code = "x = 1"
        assert explainer._detect_primary_function(code) == ""


# ---------------------------------------------------------------------------
# Tests: CodeExplainer.explain (integration)
# ---------------------------------------------------------------------------

class TestExplain:
    def test_explain_whole_file(self, tmp_project, explainer):
        exp = explainer.explain("src/payment.py")
        assert exp.file.endswith("payment.py")
        assert exp.start_line == 1
        assert "process_payment" in exp.summary or "validate_amount" in exp.summary
        assert exp.complexity in ("simple", "moderate", "complex")

    def test_explain_line_range(self, tmp_project, explainer):
        exp = explainer.explain("src/payment.py", start_line=15, end_line=26)
        assert "process_payment" in exp.code
        assert exp.start_line == 15
        assert exp.end_line == 26

    def test_explain_function_by_name(self, tmp_project, explainer):
        exp = explainer.explain("src/payment.py", function_name="validate_amount")
        assert "validate_amount" in exp.code
        assert exp.start_line > 0

    def test_explain_function_not_found(self, tmp_project, explainer):
        exp = explainer.explain("src/payment.py", function_name="nonexistent")
        assert "not found" in exp.summary.lower()

    def test_explain_file_not_found(self, tmp_project, explainer):
        exp = explainer.explain("nonexistent.py")
        assert "not found" in exp.summary.lower()

    def test_side_effects_detected(self, tmp_project, explainer):
        exp = explainer.explain("src/payment.py", function_name="process_payment")
        assert len(exp.side_effects) > 0
        labels = [e.split(":")[0] for e in exp.side_effects]
        assert "API call" in labels or "Logging" in labels

    def test_explain_utils_subprocess(self, tmp_project, explainer):
        exp = explainer.explain("src/utils.py", function_name="run_command")
        assert any("Subprocess" in e for e in exp.side_effects)

    def test_explain_complex_function(self, tmp_project, explainer):
        exp = explainer.explain("src/utils.py", function_name="complex_function")
        assert exp.complexity in ("moderate", "complex")


# ---------------------------------------------------------------------------
# Tests: format_explanation
# ---------------------------------------------------------------------------

class TestFormatExplanation:
    def test_basic_format(self):
        exp = Explanation(
            file="/tmp/test.py",
            start_line=1,
            end_line=10,
            code="def foo():\n    return 42",
            summary="Simple function that returns 42.",
            call_chain=["main() -> foo()"],
            side_effects=["Console output: print('hello')"],
            complexity="simple",
        )
        output = format_explanation(exp)
        assert "Explanation:" in output
        assert "test.py" in output
        assert "Simple function" in output
        assert "Call chain:" in output
        assert "main() -> foo()" in output
        assert "Side effects:" in output
        assert "simple" in output

    def test_empty_call_chain(self):
        exp = Explanation(
            file="/tmp/test.py",
            start_line=1,
            end_line=5,
            code="x = 1",
            summary="Assignment.",
            call_chain=[],
            side_effects=[],
            complexity="simple",
        )
        output = format_explanation(exp)
        assert "Call chain:" not in output
        assert "Side effects:" not in output

    def test_long_call_chain_truncated(self):
        exp = Explanation(
            file="/tmp/test.py",
            start_line=1,
            end_line=5,
            code="x = 1",
            summary="Test.",
            call_chain=[f"func_{i}() -> func_{i+1}()" for i in range(15)],
            side_effects=[],
            complexity="moderate",
        )
        output = format_explanation(exp)
        assert "... and 5 more" in output

    def test_complexity_branch_count(self):
        exp = Explanation(
            file="/tmp/test.py",
            start_line=1,
            end_line=5,
            code="if a:\n  for b in c:\n    if d:\n      pass",
            summary="Test.",
            complexity="simple",
        )
        output = format_explanation(exp)
        assert "branches" in output

    def test_multiple_side_effect_types(self):
        exp = Explanation(
            file="/tmp/test.py",
            start_line=1,
            end_line=5,
            code="x = 1",
            summary="Test.",
            side_effects=[
                "DB write: db.execute('INSERT')",
                "API call: requests.post('url')",
                "File I/O: open('file.txt')",
            ],
            complexity="moderate",
        )
        output = format_explanation(exp)
        assert "[DB]" in output
        assert "[API]" in output
        assert "[File]" in output


# ---------------------------------------------------------------------------
# Tests: _grep_callers (mocked)
# ---------------------------------------------------------------------------

class TestGrepCallers:
    @patch("code_agents.knowledge.code_explainer.subprocess.run")
    def test_grep_callers_basic(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="src/api.py:5:    result = process_payment(order_id, amount)\n",
            returncode=0,
        )
        callers = _grep_callers("process_payment", "/tmp/project")
        assert len(callers) == 1
        assert "process_payment" in callers[0]

    @patch("code_agents.knowledge.code_explainer.subprocess.run")
    def test_grep_callers_skips_definitions(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="src/payment.py:15:def process_payment(order_id):\nsrc/api.py:5:    process_payment(oid)\n",
            returncode=0,
        )
        callers = _grep_callers("process_payment", "/tmp/project")
        # Should skip the def line
        assert not any("def process_payment" in c for c in callers)

    @patch("code_agents.knowledge.code_explainer.subprocess.run")
    def test_grep_callers_timeout(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired("grep", 10)
        callers = _grep_callers("process_payment", "/tmp/project")
        assert callers == []

    @patch("code_agents.knowledge.code_explainer.subprocess.run")
    def test_grep_callers_max_20(self, mock_run):
        lines = "\n".join(
            f"file{i}.py:{i}:    process_payment()" for i in range(30)
        )
        mock_run.return_value = MagicMock(stdout=lines, returncode=0)
        callers = _grep_callers("process_payment", "/tmp/project")
        assert len(callers) <= 20


# ---------------------------------------------------------------------------
# Tests: CLI handler (cmd_explain_code)
# ---------------------------------------------------------------------------

class TestCmdExplainCode:
    @patch("code_agents.cli.cli_explain._user_cwd")
    @patch("code_agents.knowledge.code_explainer.CodeExplainer.explain")
    def test_no_args_shows_usage(self, mock_explain, mock_cwd, capsys):
        from code_agents.cli.cli_explain import cmd_explain_code
        cmd_explain_code([])
        captured = capsys.readouterr()
        assert "Usage" in captured.out
        mock_explain.assert_not_called()

    @patch("code_agents.cli.cli_explain._user_cwd", return_value="/tmp")
    @patch("code_agents.knowledge.code_explainer.CodeExplainer.explain")
    def test_file_with_line_range(self, mock_explain, mock_cwd, capsys):
        from code_agents.cli.cli_explain import cmd_explain_code
        mock_explain.return_value = Explanation(
            file="/tmp/api.py", start_line=10, end_line=20,
            code="def foo(): pass", summary="Test.", complexity="simple",
        )
        cmd_explain_code(["src/api.py:10-20"])
        mock_explain.assert_called_once_with(
            file_path="src/api.py", start_line=10, end_line=20, function_name="",
        )

    @patch("code_agents.cli.cli_explain._user_cwd", return_value="/tmp")
    @patch("code_agents.knowledge.code_explainer.CodeExplainer.explain")
    def test_function_flag(self, mock_explain, mock_cwd, capsys):
        from code_agents.cli.cli_explain import cmd_explain_code
        mock_explain.return_value = Explanation(
            file="/tmp/api.py", start_line=5, end_line=15,
            code="def process(): pass", summary="Test.", complexity="simple",
        )
        cmd_explain_code(["src/api.py", "--function", "process"])
        mock_explain.assert_called_once_with(
            file_path="src/api.py", start_line=0, end_line=0, function_name="process",
        )
