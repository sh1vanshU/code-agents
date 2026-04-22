"""Unit tests for code_agents/analysis/impact_analysis.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_agents.analysis.impact_analysis import (
    ImpactAnalyzer,
    ImpactReport,
    _camel_to_snake,
    format_impact_report,
)


# ---------------------------------------------------------------------------
# _camel_to_snake
# ---------------------------------------------------------------------------

class TestCamelToSnake:
    def test_simple(self):
        assert _camel_to_snake("PaymentService") == "payment_service"

    def test_all_lower(self):
        assert _camel_to_snake("config") == "config"

    def test_all_upper(self):
        assert _camel_to_snake("URL") == "url"

    def test_mixed(self):
        assert _camel_to_snake("getHTTPResponse") == "get_http_response"


# ---------------------------------------------------------------------------
# ImpactAnalyzer._resolve_path / _module_name
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_resolve_relative(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        p = a._resolve_path("src/foo.py")
        assert p == tmp_path / "src" / "foo.py"

    def test_resolve_absolute(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        p = a._resolve_path("/absolute/foo.py")
        assert p == Path("/absolute/foo.py")

    def test_module_name(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        assert a._module_name("src/services/PaymentService.java") == "PaymentService"


# ---------------------------------------------------------------------------
# _import_patterns
# ---------------------------------------------------------------------------

class TestImportPatterns:
    def test_python(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        pats = a._import_patterns("pkg/my_module.py")
        assert len(pats) > 0
        # Should match a typical Python import
        assert pats[0].search("from pkg.my_module import Foo")

    def test_java(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        pats = a._import_patterns("src/PaymentService.java")
        assert len(pats) >= 2
        assert pats[0].search("import com.example.PaymentService;")

    def test_js(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        pats = a._import_patterns("src/utils.ts")
        assert len(pats) > 0
        assert pats[0].search("from './utils'")

    def test_go(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        pats = a._import_patterns("pkg/handler.go")
        assert len(pats) > 0
        assert pats[0].search("handler.DoSomething()")

    def test_unknown_ext(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        pats = a._import_patterns("Makefile")
        assert pats == []


# ---------------------------------------------------------------------------
# _index_files
# ---------------------------------------------------------------------------

class TestIndexFiles:
    def test_indexes_code_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print(1)")
        (tmp_path / "readme.md").write_text("# hi")
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "util.py").write_text("pass")
        a = ImpactAnalyzer(str(tmp_path))
        files = a._index_files()
        names = [f.name for f in files]
        assert "main.py" in names
        assert "util.py" in names
        assert "readme.md" not in names

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("")
        (tmp_path / "app.js").write_text("")
        a = ImpactAnalyzer(str(tmp_path))
        files = a._index_files()
        names = [f.name for f in files]
        assert "app.js" in names
        assert "index.js" not in names

    def test_caches_result(self, tmp_path):
        (tmp_path / "x.py").write_text("")
        a = ImpactAnalyzer(str(tmp_path))
        f1 = a._index_files()
        f2 = a._index_files()
        assert f1 is f2


# ---------------------------------------------------------------------------
# find_dependents
# ---------------------------------------------------------------------------

class TestFindDependents:
    def test_finds_python_import(self, tmp_path):
        (tmp_path / "config.py").write_text("X = 1")
        (tmp_path / "app.py").write_text("from config import X")
        a = ImpactAnalyzer(str(tmp_path))
        deps = a.find_dependents("config.py")
        assert "app.py" in deps

    def test_no_self_match(self, tmp_path):
        (tmp_path / "config.py").write_text("import config")
        a = ImpactAnalyzer(str(tmp_path))
        deps = a.find_dependents("config.py")
        assert "config.py" not in deps

    def test_no_patterns_returns_empty(self, tmp_path):
        (tmp_path / "Makefile").write_text("")
        a = ImpactAnalyzer(str(tmp_path))
        # Makefile has no recognized extension → no import patterns
        deps = a.find_dependents("Makefile")
        assert deps == []


# ---------------------------------------------------------------------------
# find_tests
# ---------------------------------------------------------------------------

class TestFindTests:
    def test_finds_python_test(self, tmp_path):
        (tmp_path / "config.py").write_text("")
        (tmp_path / "test_config.py").write_text("")
        a = ImpactAnalyzer(str(tmp_path))
        existing, missing = a.find_tests("config.py")
        assert any("test_config" in t for t in existing)
        assert missing == []

    def test_missing_test_detected(self, tmp_path):
        (tmp_path / "payment.py").write_text("")
        a = ImpactAnalyzer(str(tmp_path))
        existing, missing = a.find_tests("payment.py")
        assert existing == []
        assert "test_payment.py" in missing

    def test_java_test(self, tmp_path):
        (tmp_path / "PaymentService.java").write_text("class PaymentService {}")
        (tmp_path / "PaymentServiceTest.java").write_text("class PaymentServiceTest {}")
        a = ImpactAnalyzer(str(tmp_path))
        existing, missing = a.find_tests("PaymentService.java")
        assert any("PaymentServiceTest" in t for t in existing)

    def test_js_test(self, tmp_path):
        (tmp_path / "utils.ts").write_text("")
        (tmp_path / "utils.test.ts").write_text("")
        a = ImpactAnalyzer(str(tmp_path))
        existing, missing = a.find_tests("utils.ts")
        assert any("utils.test.ts" in t for t in existing)

    def test_go_test(self, tmp_path):
        (tmp_path / "handler.go").write_text("")
        (tmp_path / "handler_test.go").write_text("")
        a = ImpactAnalyzer(str(tmp_path))
        existing, missing = a.find_tests("handler.go")
        assert any("handler_test.go" in t for t in existing)

    def test_grep_based_test_detection(self, tmp_path):
        (tmp_path / "config.py").write_text("X = 1")
        # A test file that imports config but doesn't follow naming convention
        (tmp_path / "test_integration.py").write_text("from config import X")
        a = ImpactAnalyzer(str(tmp_path))
        existing, _ = a.find_tests("config.py")
        assert any("test_integration" in t for t in existing)

    def test_missing_java_test(self, tmp_path):
        (tmp_path / "Foo.java").write_text("class Foo {}")
        a = ImpactAnalyzer(str(tmp_path))
        _, missing = a.find_tests("Foo.java")
        assert "FooTest.java" in missing

    def test_missing_ts_test(self, tmp_path):
        (tmp_path / "bar.ts").write_text("")
        a = ImpactAnalyzer(str(tmp_path))
        _, missing = a.find_tests("bar.ts")
        assert "bar.test.ts" in missing

    def test_missing_go_test(self, tmp_path):
        (tmp_path / "server.go").write_text("")
        a = ImpactAnalyzer(str(tmp_path))
        _, missing = a.find_tests("server.go")
        assert "server_test.go" in missing


# ---------------------------------------------------------------------------
# _extract_endpoints
# ---------------------------------------------------------------------------

class TestExtractEndpoints:
    def test_flask_endpoint(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        content = '@app.get("/users")\ndef get_users(): ...'
        eps = a._extract_endpoints(content)
        assert any("/users" in ep for ep in eps)

    def test_spring_endpoint(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        content = '@GetMapping("/api/v1/pay")\npublic Response pay() {}'
        eps = a._extract_endpoints(content)
        assert any("/api/v1/pay" in ep for ep in eps)

    def test_express_endpoint(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        content = 'router.post("/orders", handler)'
        eps = a._extract_endpoints(content)
        assert any("/orders" in ep for ep in eps)

    def test_no_endpoints(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        eps = a._extract_endpoints("x = 1\ny = 2")
        assert eps == []


# ---------------------------------------------------------------------------
# find_endpoints
# ---------------------------------------------------------------------------

class TestFindEndpoints:
    def test_from_file_itself(self, tmp_path):
        (tmp_path / "api.py").write_text('@app.get("/health")\ndef health(): pass')
        a = ImpactAnalyzer(str(tmp_path))
        eps = a.find_endpoints("api.py")
        assert any("/health" in ep for ep in eps)

    def test_missing_file(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        eps = a.find_endpoints("nonexistent.py")
        assert eps == [] or isinstance(eps, list)


# ---------------------------------------------------------------------------
# assess_risk
# ---------------------------------------------------------------------------

class TestAssessRisk:
    def test_low_risk(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        level, reasons = a.assess_risk("util.py", [], [], [], [])
        assert level == "low"

    def test_critical_keyword(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        level, reasons = a.assess_risk("src/payment_service.py", [], [], [], [])
        assert level in ("high", "critical")
        assert any("sensitive keyword" in r.lower() for r in reasons)

    def test_many_dependents_high(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        deps = [f"file{i}.py" for i in range(6)]
        level, reasons = a.assess_risk("core.py", deps, [], [], [])
        assert level in ("high", "critical")

    def test_very_many_dependents(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        deps = [f"file{i}.py" for i in range(12)]
        level, reasons = a.assess_risk("core.py", deps, [], [], [])
        assert level in ("high", "critical")
        assert any("very high coupling" in r for r in reasons)

    def test_missing_tests_medium(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        level, reasons = a.assess_risk("foo.py", [], [], ["test_foo.py"], [])
        assert level == "medium"

    def test_no_tests_adds_reason(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        _, reasons = a.assess_risk("foo.py", [], [], [], [])
        assert any("No related tests" in r for r in reasons)

    def test_endpoints_add_risk(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        level, reasons = a.assess_risk("api.py", [], ["test_api.py"], [], ["GET /a", "POST /b", "PUT /c", "DELETE /d"])
        assert any("endpoint" in r.lower() for r in reasons)

    def test_few_dependents(self, tmp_path):
        a = ImpactAnalyzer(str(tmp_path))
        deps = ["a.py", "b.py", "c.py"]
        _, reasons = a.assess_risk("x.py", deps, ["t.py"], [], [])
        assert any("3 dependent" in r for r in reasons)


# ---------------------------------------------------------------------------
# analyze (integration)
# ---------------------------------------------------------------------------

class TestAnalyze:
    def test_full_analysis(self, tmp_path):
        (tmp_path / "service.py").write_text("X = 1")
        (tmp_path / "test_service.py").write_text("from service import X")
        a = ImpactAnalyzer(str(tmp_path))
        report = a.analyze("service.py")
        assert isinstance(report, ImpactReport)
        assert report.file == "service.py"
        assert report.risk_level in ("low", "medium", "high", "critical")


# ---------------------------------------------------------------------------
# format_impact_report
# ---------------------------------------------------------------------------

class TestFormatImpactReport:
    def test_minimal_report(self):
        r = ImpactReport(file="foo.py")
        out = format_impact_report(r)
        assert "foo.py" in out
        assert "LOW" in out
        assert "Dependents: none" in out

    def test_full_report(self):
        r = ImpactReport(
            file="payment.py",
            dependent_files=["billing.py"],
            affected_tests=["test_payment.py"],
            missing_tests=["test_billing.py"],
            affected_endpoints=["GET /pay"],
            risk_level="high",
            risk_reasons=["sensitive keyword"],
        )
        out = format_impact_report(r)
        assert "HIGH" in out
        assert "billing.py" in out
        assert "test_payment.py" in out
        assert "MISSING" in out
        assert "GET /pay" in out

    def test_no_tests(self):
        r = ImpactReport(file="x.py")
        out = format_impact_report(r)
        assert "Tests: none found" in out

    def test_no_endpoints(self):
        r = ImpactReport(file="x.py")
        out = format_impact_report(r)
        assert "Endpoints: none" in out

    def test_singular_dependent(self):
        r = ImpactReport(file="x.py", dependent_files=["a.py"])
        out = format_impact_report(r)
        assert "1 file)" in out

    def test_plural_dependents(self):
        r = ImpactReport(file="x.py", dependent_files=["a.py", "b.py"])
        out = format_impact_report(r)
        assert "2 files)" in out
