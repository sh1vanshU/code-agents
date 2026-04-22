"""Tests for the InputValidatorGen module."""

import textwrap
import pytest
from code_agents.security.input_validator_gen import (
    InputValidatorGen, InputValidatorConfig, InputValidatorReport, format_validation_report,
)


class TestInputValidatorGen:
    def test_discover_fastapi_endpoints(self, tmp_path):
        source = textwrap.dedent('''\
            from fastapi import FastAPI
            app = FastAPI()

            @app.get("/users/{user_id}")
            def get_user(user_id: int):
                return {"id": user_id}

            @app.post("/users")
            def create_user(data: dict):
                return data
        ''')
        (tmp_path / "main.py").write_text(source)
        gen = InputValidatorGen(InputValidatorConfig(cwd=str(tmp_path)))
        report = gen.analyze()
        assert report.endpoints_scanned >= 2
        assert any(e.path == "/users/{user_id}" for e in report.endpoints)

    def test_detect_sql_injection_sink(self, tmp_path):
        source = textwrap.dedent('''\
            def search(query):
                cursor.execute(f"SELECT * FROM users WHERE name = '{query}'")
        ''')
        (tmp_path / "db.py").write_text(source)
        gen = InputValidatorGen(InputValidatorConfig(cwd=str(tmp_path)))
        report = gen.analyze()
        assert report.gaps_found >= 1
        assert any(g.vuln_type == "sqli" for g in report.gaps)

    def test_detect_command_injection(self, tmp_path):
        source = textwrap.dedent('''\
            import os
            def run(cmd):
                os.system(f"echo {cmd}")
        ''')
        (tmp_path / "runner.py").write_text(source)
        gen = InputValidatorGen(InputValidatorConfig(cwd=str(tmp_path)))
        report = gen.analyze()
        assert any(g.vuln_type == "command_injection" for g in report.gaps)

    def test_generates_validators_for_gaps(self, tmp_path):
        source = 'cursor.execute(f"DELETE FROM t WHERE id={uid}")\n'
        (tmp_path / "api.py").write_text(source)
        gen = InputValidatorGen(InputValidatorConfig(cwd=str(tmp_path)))
        report = gen.analyze()
        assert report.validators_generated >= 1
        assert any("sqli" in v.vuln_types_covered for v in report.validators)

    def test_clean_code_no_gaps(self, tmp_path):
        source = textwrap.dedent('''\
            def add(a: int, b: int) -> int:
                return a + b
        ''')
        (tmp_path / "math.py").write_text(source)
        gen = InputValidatorGen(InputValidatorConfig(cwd=str(tmp_path)))
        report = gen.analyze()
        assert report.gaps_found == 0

    def test_format_report(self):
        report = InputValidatorReport(endpoints_scanned=5, gaps_found=2, summary="done")
        output = format_validation_report(report)
        assert "Input Validation" in output
        assert "Endpoints scanned" in output
