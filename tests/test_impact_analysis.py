"""Tests for impact_analysis.py — file impact detection: dependents, tests, endpoints, risk."""

import os
import tempfile
from pathlib import Path

import pytest

from code_agents.analysis.impact_analysis import (
    ImpactAnalyzer,
    ImpactReport,
    format_impact_report,
)
from code_agents.analysis.impact_analysis import _camel_to_snake


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_repo(tmp_path):
    """Create a minimal repo with test files."""
    return tmp_path


@pytest.fixture
def analyzer(tmp_repo):
    return ImpactAnalyzer(cwd=str(tmp_repo))


def _write(tmp_path, name, content):
    """Write a file into the temp repo."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return str(p)


# ---------------------------------------------------------------------------
# CamelCase to snake_case
# ---------------------------------------------------------------------------

class TestCamelToSnake:
    def test_simple(self):
        assert _camel_to_snake("PaymentService") == "payment_service"

    def test_already_snake(self):
        assert _camel_to_snake("payment_service") == "payment_service"

    def test_single_word(self):
        assert _camel_to_snake("Service") == "service"

    def test_acronym(self):
        assert _camel_to_snake("HTTPServer") == "http_server"


# ---------------------------------------------------------------------------
# Python dependents
# ---------------------------------------------------------------------------

class TestPythonDependents:
    def test_finds_direct_import(self, analyzer, tmp_repo):
        """A file that imports the target should be found."""
        _write(tmp_repo, "services/payment.py", "class PaymentService:\n    pass\n")
        _write(tmp_repo, "controllers/api.py", "from services.payment import PaymentService\n")
        deps = analyzer.find_dependents("services/payment.py")
        assert "controllers/api.py" in deps

    def test_finds_import_module(self, analyzer, tmp_repo):
        """Import of the module (not from ... import) should be found."""
        _write(tmp_repo, "utils/helper.py", "def help(): pass\n")
        _write(tmp_repo, "main.py", "import utils.helper\n")
        deps = analyzer.find_dependents("utils/helper.py")
        assert "main.py" in deps

    def test_does_not_include_self(self, analyzer, tmp_repo):
        """The target file should not be in its own dependents."""
        _write(tmp_repo, "service.py", "import service\n")
        deps = analyzer.find_dependents("service.py")
        assert "service.py" not in deps

    def test_no_dependents(self, analyzer, tmp_repo):
        """A file with no imports should have zero dependents."""
        _write(tmp_repo, "isolated.py", "x = 1\n")
        _write(tmp_repo, "other.py", "y = 2\n")
        deps = analyzer.find_dependents("isolated.py")
        assert deps == []


# ---------------------------------------------------------------------------
# Java dependents
# ---------------------------------------------------------------------------

class TestJavaDependents:
    def test_finds_java_import(self, analyzer, tmp_repo):
        _write(tmp_repo, "src/PaymentService.java", "public class PaymentService {}\n")
        _write(tmp_repo, "src/PaymentController.java",
               "import com.example.PaymentService;\npublic class PaymentController {}\n")
        deps = analyzer.find_dependents("src/PaymentService.java")
        assert "src/PaymentController.java" in deps

    def test_finds_java_class_reference(self, analyzer, tmp_repo):
        _write(tmp_repo, "src/PaymentService.java", "public class PaymentService {}\n")
        _write(tmp_repo, "src/BatchProcessor.java",
               "public class BatchProcessor {\n  PaymentService svc;\n}\n")
        deps = analyzer.find_dependents("src/PaymentService.java")
        assert "src/BatchProcessor.java" in deps


# ---------------------------------------------------------------------------
# JS/TS dependents
# ---------------------------------------------------------------------------

class TestJsTsDependents:
    def test_finds_es_import(self, analyzer, tmp_repo):
        _write(tmp_repo, "src/PaymentService.ts", "export class PaymentService {}\n")
        _write(tmp_repo, "src/api.ts", "import { PaymentService } from './PaymentService'\n")
        deps = analyzer.find_dependents("src/PaymentService.ts")
        assert "src/api.ts" in deps

    def test_finds_require(self, analyzer, tmp_repo):
        _write(tmp_repo, "lib/utils.js", "module.exports = {}\n")
        _write(tmp_repo, "index.js", "const u = require('./utils')\n")
        deps = analyzer.find_dependents("lib/utils.js")
        assert "index.js" in deps


# ---------------------------------------------------------------------------
# Test discovery
# ---------------------------------------------------------------------------

class TestFindTests:
    def test_finds_python_test(self, analyzer, tmp_repo):
        _write(tmp_repo, "services/payment.py", "class PaymentService: pass\n")
        _write(tmp_repo, "tests/test_payment.py", "from services.payment import PaymentService\n")
        existing, missing = analyzer.find_tests("services/payment.py")
        assert any("test_payment.py" in t for t in existing)

    def test_finds_java_test(self, analyzer, tmp_repo):
        _write(tmp_repo, "src/PaymentService.java", "public class PaymentService {}\n")
        _write(tmp_repo, "src/PaymentServiceTest.java", "public class PaymentServiceTest {}\n")
        existing, missing = analyzer.find_tests("src/PaymentService.java")
        assert any("PaymentServiceTest.java" in t for t in existing)

    def test_missing_test_reported(self, analyzer, tmp_repo):
        _write(tmp_repo, "services/payment.py", "class PaymentService: pass\n")
        existing, missing = analyzer.find_tests("services/payment.py")
        assert len(existing) == 0
        assert len(missing) > 0
        assert any("test_payment" in m for m in missing)

    def test_js_spec_test(self, analyzer, tmp_repo):
        _write(tmp_repo, "src/Cart.ts", "export class Cart {}\n")
        _write(tmp_repo, "src/Cart.test.ts", "import { Cart } from './Cart'\n")
        existing, missing = analyzer.find_tests("src/Cart.ts")
        assert any("Cart.test.ts" in t for t in existing)

    def test_go_test(self, analyzer, tmp_repo):
        _write(tmp_repo, "handler.go", "package main\n")
        _write(tmp_repo, "handler_test.go", "package main\nfunc TestHandler(t *testing.T) {}\n")
        existing, missing = analyzer.find_tests("handler.go")
        assert any("handler_test.go" in t for t in existing)


# ---------------------------------------------------------------------------
# Endpoint discovery
# ---------------------------------------------------------------------------

class TestFindEndpoints:
    def test_spring_get_mapping(self, analyzer, tmp_repo):
        _write(tmp_repo, "src/PaymentController.java", '''
@RestController
public class PaymentController {
    @GetMapping("/api/v1/payment")
    public Response getPayment() { return null; }
}
''')
        eps = analyzer.find_endpoints("src/PaymentController.java")
        assert any("/api/v1/payment" in ep for ep in eps)

    def test_spring_post_mapping(self, analyzer, tmp_repo):
        _write(tmp_repo, "src/PaymentController.java", '''
@RestController
public class PaymentController {
    @PostMapping("/api/v1/payment")
    public Response create() { return null; }
}
''')
        eps = analyzer.find_endpoints("src/PaymentController.java")
        assert any("POST" in ep and "/api/v1/payment" in ep for ep in eps)

    def test_fastapi_endpoint(self, analyzer, tmp_repo):
        _write(tmp_repo, "routers/payment.py", '''
from fastapi import APIRouter
router = APIRouter()

@router.post("/api/v1/payment")
def create_payment():
    pass
''')
        eps = analyzer.find_endpoints("routers/payment.py")
        assert any("/api/v1/payment" in ep for ep in eps)

    def test_express_endpoint(self, analyzer, tmp_repo):
        _write(tmp_repo, "routes/payment.js", '''
const router = require('express').Router();
router.post('/api/v1/payment', (req, res) => {});
''')
        eps = analyzer.find_endpoints("routes/payment.js")
        assert any("/api/v1/payment" in ep for ep in eps)

    def test_endpoints_from_dependent_controller(self, analyzer, tmp_repo):
        """If a service file is used by a controller, find endpoints in that controller."""
        _write(tmp_repo, "services/payment.py", "class PaymentService: pass\n")
        _write(tmp_repo, "controllers/payment_controller.py", '''
from services.payment import PaymentService
from fastapi import APIRouter
router = APIRouter()

@router.post("/api/v1/payment")
def create():
    svc = PaymentService()
''')
        eps = analyzer.find_endpoints("services/payment.py")
        assert any("/api/v1/payment" in ep for ep in eps)

    def test_no_endpoints(self, analyzer, tmp_repo):
        _write(tmp_repo, "utils.py", "def add(a, b): return a + b\n")
        eps = analyzer.find_endpoints("utils.py")
        assert eps == []


# ---------------------------------------------------------------------------
# Risk assessment
# ---------------------------------------------------------------------------

class TestRiskAssessment:
    def test_low_risk(self, analyzer, tmp_repo):
        level, reasons = analyzer.assess_risk("utils.py", [], ["test_utils.py"], [], [])
        assert level == "low"

    def test_high_risk_many_dependents(self, analyzer, tmp_repo):
        deps = [f"file{i}.py" for i in range(6)]
        level, reasons = analyzer.assess_risk("service.py", deps, ["test_service.py"], [], [])
        assert level in ("high", "critical")

    def test_critical_payment_keyword(self, analyzer, tmp_repo):
        deps = [f"file{i}.py" for i in range(6)]
        level, reasons = analyzer.assess_risk(
            "services/payment_service.py", deps, [], ["test_payment_service.py"], ["/api/pay"]
        )
        assert level == "critical"

    def test_medium_risk_missing_tests(self, analyzer, tmp_repo):
        level, reasons = analyzer.assess_risk(
            "service.py", ["a.py", "b.py", "c.py"], [], ["test_service.py"], []
        )
        assert level in ("medium", "high")

    def test_risk_reasons_populated(self, analyzer, tmp_repo):
        level, reasons = analyzer.assess_risk(
            "auth/login.py", ["a.py"], [], ["test_login.py"], ["/api/login"]
        )
        assert len(reasons) > 0
        assert any("sensitive" in r.lower() or "keyword" in r.lower() for r in reasons)


# ---------------------------------------------------------------------------
# Full analysis
# ---------------------------------------------------------------------------

class TestAnalyze:
    def test_full_analysis(self, analyzer, tmp_repo):
        _write(tmp_repo, "services/payment.py", "class PaymentService: pass\n")
        _write(tmp_repo, "controllers/payment_controller.py",
               "from services.payment import PaymentService\n"
               "from fastapi import APIRouter\n"
               "router = APIRouter()\n"
               "@router.post('/api/v1/payment')\n"
               "def create(): pass\n")
        _write(tmp_repo, "tests/test_payment.py",
               "from services.payment import PaymentService\n"
               "def test_pay(): pass\n")
        report = analyzer.analyze("services/payment.py")
        assert isinstance(report, ImpactReport)
        assert report.file == "services/payment.py"
        assert len(report.dependent_files) >= 1
        assert len(report.affected_tests) >= 1
        assert report.risk_level in ("low", "medium", "high", "critical")


# ---------------------------------------------------------------------------
# Format output
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_format_with_all_sections(self):
        report = ImpactReport(
            file="src/PaymentService.java",
            dependent_files=["PaymentController.java", "RefundController.java"],
            affected_tests=["PaymentServiceTest.java"],
            missing_tests=["RefundControllerTest.java"],
            affected_endpoints=["POST /api/v1/payment", "POST /api/v1/refund"],
            risk_level="high",
            risk_reasons=["File path contains sensitive keyword: payment"],
        )
        output = format_impact_report(report)
        assert "PaymentService.java" in output
        assert "HIGH" in output
        assert "PaymentController.java" in output
        assert "RefundController.java" in output
        assert "PaymentServiceTest.java" in output
        assert "MISSING" in output
        assert "POST /api/v1/payment" in output

    def test_format_empty_report(self):
        report = ImpactReport(file="utils.py")
        output = format_impact_report(report)
        assert "utils.py" in output
        assert "LOW" in output
        assert "none" in output.lower()

    def test_format_risk_reasons_shown(self):
        report = ImpactReport(
            file="auth.py",
            risk_level="critical",
            risk_reasons=["10 dependent files (very high coupling)", "Missing test coverage: test_auth.py"],
        )
        output = format_impact_report(report)
        assert "CRITICAL" in output
        assert "10 dependent" in output
        assert "Missing test" in output


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_nonexistent_file(self, analyzer, tmp_repo):
        """Analyzing a file that doesn't exist should not crash."""
        report = analyzer.analyze("does_not_exist.py")
        assert report.file == "does_not_exist.py"
        assert report.dependent_files == []

    def test_binary_file_skipped(self, analyzer, tmp_repo):
        """Binary files in repo should not crash the scanner."""
        _write(tmp_repo, "service.py", "class Svc: pass\n")
        # Write some binary-ish content
        bin_path = tmp_repo / "image.py"
        bin_path.write_bytes(b"\x00\x01\x02class Svc\x03\x04")
        deps = analyzer.find_dependents("service.py")
        # Should not crash; binary file might match but that's okay
        assert isinstance(deps, list)

    def test_empty_repo(self, analyzer, tmp_repo):
        """Empty repo should return empty results without crashing."""
        report = analyzer.analyze("anything.py")
        assert report.dependent_files == []
        assert report.affected_tests == []
        assert report.affected_endpoints == []

    def test_skips_node_modules(self, analyzer, tmp_repo):
        """Files inside node_modules should be ignored."""
        _write(tmp_repo, "src/service.ts", "export class Service {}\n")
        _write(tmp_repo, "node_modules/lib/index.ts", "import { Service } from '../../src/service'\n")
        deps = analyzer.find_dependents("src/service.ts")
        assert not any("node_modules" in d for d in deps)
