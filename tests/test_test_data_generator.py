"""Tests for test_data_generator.py — domain-specific test data generation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.generators.test_data_generator import (
    DOMAIN_DATA,
    TestDataGenerator,
    format_test_data,
    _random_amount,
    _random_email,
    _random_phone,
)


# ---------------------------------------------------------------------------
# Domain data generators — sanity checks
# ---------------------------------------------------------------------------

class TestDomainData:
    def test_payment_domain_exists(self):
        assert "payment" in DOMAIN_DATA
        assert "amount" in DOMAIN_DATA["payment"]
        assert "currency" in DOMAIN_DATA["payment"]
        assert "merchant_id" in DOMAIN_DATA["payment"]
        assert "status" in DOMAIN_DATA["payment"]

    def test_user_domain_exists(self):
        assert "user" in DOMAIN_DATA
        assert "name" in DOMAIN_DATA["user"]
        assert "email" in DOMAIN_DATA["user"]

    def test_api_domain_exists(self):
        assert "api" in DOMAIN_DATA
        assert "request_id" in DOMAIN_DATA["api"]
        assert "timestamp" in DOMAIN_DATA["api"]

    def test_all_generators_callable(self):
        for domain, generators in DOMAIN_DATA.items():
            for field_name, gen in generators.items():
                result = gen()
                assert result is not None, f"{domain}.{field_name} returned None"


# ---------------------------------------------------------------------------
# Helper generators
# ---------------------------------------------------------------------------

class TestHelperGenerators:
    def test_random_amount_range(self):
        for _ in range(20):
            amount = _random_amount()
            assert 1.0 <= amount <= 9999.99

    def test_random_email_format(self):
        email = _random_email("test")
        assert "@" in email
        assert "." in email

    def test_random_phone_format(self):
        phone = _random_phone()
        assert phone.startswith("+91")
        assert len(phone) == 13


# ---------------------------------------------------------------------------
# TestDataGenerator.detect_domain
# ---------------------------------------------------------------------------

class TestDetectDomain:
    def test_detects_payment_domain(self, tmp_path):
        (tmp_path / "payment_service.py").write_text("class PaymentService: pass")
        gen = TestDataGenerator(repo_path=str(tmp_path))
        domains = gen.detect_domain()
        assert "payment" in domains

    def test_detects_user_domain(self, tmp_path):
        (tmp_path / "user_auth.py").write_text("class UserAuth: pass")
        gen = TestDataGenerator(repo_path=str(tmp_path))
        domains = gen.detect_domain()
        assert "user" in domains

    def test_empty_repo_defaults_to_api(self, tmp_path):
        gen = TestDataGenerator(repo_path=str(tmp_path))
        domains = gen.detect_domain()
        assert domains == ["api"]


# ---------------------------------------------------------------------------
# TestDataGenerator.generate
# ---------------------------------------------------------------------------

class TestGenerate:
    def test_generate_count(self):
        gen = TestDataGenerator()
        records = gen.generate(domains=["payment"], count=3)
        assert len(records) == 3

    def test_generate_has_payment_fields(self):
        gen = TestDataGenerator()
        records = gen.generate(domains=["payment"], count=1)
        assert len(records) == 1
        r = records[0]
        assert "amount" in r
        assert "currency" in r
        assert "merchant_id" in r

    def test_generate_multiple_domains(self):
        gen = TestDataGenerator()
        records = gen.generate(domains=["payment", "user"], count=1)
        r = records[0]
        assert "amount" in r
        assert "name" in r

    def test_generate_unknown_domain_returns_empty(self):
        gen = TestDataGenerator()
        records = gen.generate(domains=["nonexistent"], count=5)
        assert records == []


# ---------------------------------------------------------------------------
# format_test_data
# ---------------------------------------------------------------------------

class TestFormatTestData:
    def test_json_format(self):
        records = [{"amount": 100.0, "currency": "INR"}]
        output = format_test_data(records, language="json")
        parsed = json.loads(output)
        assert parsed[0]["amount"] == 100.0

    def test_python_format(self):
        records = [{"name": "Alice"}]
        output = format_test_data(records, language="python")
        assert "test_data" in output
        assert "'Alice'" in output

    def test_java_format(self):
        records = [{"user_id": "USR123", "amount": 99.5}]
        output = format_test_data(records, language="java")
        assert "String userId" in output
        assert "double amount" in output

    def test_empty_records(self):
        output = format_test_data([], language="json")
        assert "No test data" in output

    def test_unknown_language_defaults_to_json(self):
        records = [{"x": 1}]
        output = format_test_data(records, language="unknown")
        parsed = json.loads(output)
        assert parsed[0]["x"] == 1

    def test_java_int_field(self):
        records = [{"count": 42}]
        output = format_test_data(records, language="java")
        assert "int count" in output

    def test_java_multiple_records(self):
        records = [{"name": "A"}, {"name": "B"}]
        output = format_test_data(records, language="java")
        assert "Record 1" in output
        assert "Record 2" in output


# ---------------------------------------------------------------------------
# Helper generators — additional coverage
# ---------------------------------------------------------------------------

class TestHelperGeneratorsExtended:
    def test_random_string(self):
        from code_agents.generators.test_data_generator import _random_string
        result = _random_string(10)
        assert len(result) == 10
        assert result.isalpha()

    def test_random_email_no_name(self):
        from code_agents.generators.test_data_generator import _random_email
        email = _random_email()
        assert "@" in email

    def test_random_timestamp(self):
        from code_agents.generators.test_data_generator import _random_timestamp
        ts = _random_timestamp()
        assert ts.endswith("Z")
        assert "T" in ts

    def test_random_date(self):
        from code_agents.generators.test_data_generator import _random_date
        d = _random_date()
        assert len(d) == 10  # YYYY-MM-DD


# ---------------------------------------------------------------------------
# TestDataGenerator.generate auto-detect domains
# ---------------------------------------------------------------------------

class TestGenerateAutoDetect:
    def test_auto_detect_domains(self, tmp_path):
        (tmp_path / "user_service.py").write_text("class UserService: pass")
        gen = TestDataGenerator(repo_path=str(tmp_path))
        records = gen.generate(count=2)
        assert len(records) == 2
        # Should have user domain fields
        assert "name" in records[0] or "email" in records[0]

    def test_generate_for_class_missing_file(self):
        gen = TestDataGenerator(repo_path="/tmp")
        result = gen.generate_for_class("nonexistent.py")
        assert result == []

    def test_generate_for_class_no_fields(self, tmp_path):
        (tmp_path / "empty.py").write_text("# no fields here\n")
        gen = TestDataGenerator(repo_path=str(tmp_path))
        result = gen.generate_for_class("empty.py")
        assert result == []

    def test_generate_for_class_matches_fields(self, tmp_path):
        (tmp_path / "model.py").write_text(
            "class Payment:\n"
            "    def __init__(self):\n"
            "        self.amount = 0\n"
            "        self.status = ''\n"
            "        self.merchant_id = ''\n"
        )
        gen = TestDataGenerator(repo_path=str(tmp_path))
        result = gen.generate_for_class("model.py")
        assert len(result) == 5
        assert "amount" in result[0] or "status" in result[0]

    def test_generate_for_class_java_fields(self, tmp_path):
        (tmp_path / "User.java").write_text(
            "public class User {\n"
            "    private String email;\n"
            "    private String name;\n"
            "}\n"
        )
        gen = TestDataGenerator(repo_path=str(tmp_path))
        result = gen.generate_for_class("User.java")
        assert len(result) == 5
        # Should match email/name generators
        assert any("email" in r for r in result)

    def test_generate_for_class_no_matching_generators(self, tmp_path):
        (tmp_path / "widget.py").write_text(
            "class Widget:\n"
            "    def __init__(self):\n"
            "        self.foobar_xyz = 0\n"
        )
        gen = TestDataGenerator(repo_path=str(tmp_path))
        result = gen.generate_for_class("widget.py")
        assert result == []

    def test_generate_for_class_read_error(self, tmp_path):
        (tmp_path / "bad.py").write_text("x = 1")
        gen = TestDataGenerator(repo_path=str(tmp_path))
        with patch("pathlib.Path.read_text", side_effect=Exception("read error")):
            result = gen.generate_for_class("bad.py")
        assert result == []

    def test_detect_domain_multiple(self, tmp_path):
        (tmp_path / "payment_handler.py").write_text("")
        (tmp_path / "user_auth.py").write_text("")
        (tmp_path / "api_controller.py").write_text("")
        gen = TestDataGenerator(repo_path=str(tmp_path))
        domains = gen.detect_domain()
        assert "payment" in domains
        assert "user" in domains
        assert "api" in domains

    def test_detect_domain_exception_returns_default(self, tmp_path):
        """When rglob raises an exception, detect_domain returns default ['api']."""
        gen = TestDataGenerator(repo_path=str(tmp_path))
        with patch.object(Path, "rglob", side_effect=PermissionError("no access")):
            domains = gen.detect_domain()
        assert domains == ["api"]
