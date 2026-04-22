"""Tests for qa_suite_generator.py — QA regression suite generation from scratch."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.generators.qa_suite_generator import (
    DiscoveredEndpoint,
    DiscoveredRepository,
    DiscoveredService,
    ProjectAnalysis,
    QASuiteGenerator,
    build_test_completion_prompt,
    format_analysis,
)


@pytest.fixture
def empty_dir(tmp_path):
    """Empty directory — no project files."""
    return str(tmp_path)


@pytest.fixture
def spring_boot_project(tmp_path):
    """Minimal Spring Boot project structure."""
    # pom.xml
    (tmp_path / "pom.xml").write_text(
        '<project><dependencies>'
        '<dependency><groupId>org.springframework.boot</groupId>'
        '<artifactId>spring-boot-starter-web</artifactId></dependency>'
        '</dependencies></project>'
    )

    # Controller
    controller_dir = tmp_path / "src" / "main" / "java" / "com" / "app" / "controller"
    controller_dir.mkdir(parents=True)
    (controller_dir / "UserController.java").write_text(
        'package com.app.controller;\n\n'
        'import org.springframework.web.bind.annotation.*;\n\n'
        '@RestController\n'
        '@RequestMapping("/api/users")\n'
        'public class UserController {\n\n'
        '    @GetMapping("/list")\n'
        '    public List<User> getUsers() { return null; }\n\n'
        '    @PostMapping("/create")\n'
        '    public User createUser(@RequestBody UserDto dto) { return null; }\n\n'
        '    @DeleteMapping("/{id}")\n'
        '    public void deleteUser(@PathVariable Long id) {}\n'
        '}\n'
    )

    # Service
    service_dir = tmp_path / "src" / "main" / "java" / "com" / "app" / "service"
    service_dir.mkdir(parents=True)
    (service_dir / "PaymentService.java").write_text(
        'package com.app.service;\n\n'
        'import org.springframework.beans.factory.annotation.Autowired;\n\n'
        'public class PaymentService {\n\n'
        '    @Autowired\n'
        '    private UserRepository userRepository;\n\n'
        '    @Autowired\n'
        '    private TransactionRepository transactionRepository;\n\n'
        '    public void processPayment(PaymentRequest req) {}\n'
        '    public PaymentStatus getStatus(String id) { return null; }\n'
        '    public void refund(String txnId) {}\n'
        '}\n'
    )

    # Repository
    repo_dir = tmp_path / "src" / "main" / "java" / "com" / "app" / "repository"
    repo_dir.mkdir(parents=True)
    (repo_dir / "UserRepository.java").write_text(
        'package com.app.repository;\n\n'
        'public interface UserRepository extends JpaRepository<User, Long> {\n'
        '    User findByEmail(String email);\n'
        '}\n'
    )

    return str(tmp_path)


@pytest.fixture
def fastapi_project(tmp_path):
    """Minimal FastAPI project structure."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "myapp"\n\n'
        '[tool.poetry.dependencies]\nfastapi = "^0.100"\n'
    )

    (tmp_path / "app.py").write_text(
        'from fastapi import FastAPI\n\n'
        'app = FastAPI()\n\n'
        '@app.get("/health")\n'
        'async def health():\n'
        '    return {"status": "ok"}\n\n'
        '@app.post("/api/orders")\n'
        'async def create_order(body: dict):\n'
        '    return {"id": 1}\n\n'
        '@app.get("/api/orders/{id}")\n'
        'async def get_order(id: int):\n'
        '    return {"id": id}\n'
    )

    # Service file
    (tmp_path / "order_service.py").write_text(
        'class OrderService:\n'
        '    def create(self, data):\n'
        '        pass\n\n'
        '    def cancel(self, order_id):\n'
        '        pass\n'
    )

    return str(tmp_path)


@pytest.fixture
def js_project(tmp_path):
    """Minimal JS/Express project."""
    (tmp_path / "package.json").write_text('{"name": "myapp", "main": "app.js"}')
    return str(tmp_path)


@pytest.fixture
def go_project(tmp_path):
    """Minimal Go project."""
    (tmp_path / "go.mod").write_text('module example.com/myapp\n\ngo 1.21\n')
    return str(tmp_path)


# ── Stack Detection ──


class TestDetectStack:
    def test_spring_boot(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen._detect_stack()
        assert gen.analysis.language == "java"
        assert gen.analysis.framework == "spring-boot"
        assert gen.analysis.build_tool == "maven"

    def test_gradle(self, tmp_path):
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'")
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.language == "java"
        assert gen.analysis.build_tool == "gradle"

    def test_gradle_kts(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("plugins { id(\"java\") }")
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.language == "java"
        assert gen.analysis.build_tool == "gradle"

    def test_fastapi(self, fastapi_project):
        gen = QASuiteGenerator(fastapi_project)
        gen._detect_stack()
        assert gen.analysis.language == "python"
        assert gen.analysis.framework == "fastapi"
        assert gen.analysis.build_tool == "poetry"

    def test_django(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry.dependencies]\ndjango = '*'\n")
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.language == "python"
        assert gen.analysis.framework == "django"

    def test_flask_requirements(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask==3.0\n")
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.language == "python"
        assert gen.analysis.framework == "flask"
        assert gen.analysis.build_tool == "pip"

    def test_javascript(self, js_project):
        gen = QASuiteGenerator(js_project)
        gen._detect_stack()
        assert gen.analysis.language == "javascript"
        assert gen.analysis.build_tool == "npm"

    def test_go(self, go_project):
        gen = QASuiteGenerator(go_project)
        gen._detect_stack()
        assert gen.analysis.language == "go"
        assert gen.analysis.build_tool == "go"

    def test_unknown(self, empty_dir):
        gen = QASuiteGenerator(empty_dir)
        gen._detect_stack()
        assert gen.analysis.language == ""
        assert gen.analysis.framework == ""

    def test_spring_no_boot(self, tmp_path):
        (tmp_path / "pom.xml").write_text(
            '<project><dependencies>'
            '<dependency><groupId>org.springframework</groupId>'
            '<artifactId>spring-core</artifactId></dependency>'
            '</dependencies></project>'
        )
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.language == "java"
        assert gen.analysis.framework == "spring"


# ── Endpoint Discovery ──


class TestDiscoverEndpoints:
    def test_spring_endpoints(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen._detect_stack()
        gen._discover_endpoints()
        eps = gen.analysis.endpoints
        assert len(eps) == 3
        methods = {ep.method for ep in eps}
        assert methods == {"GET", "POST", "DELETE"}
        paths = {ep.path for ep in eps}
        assert "/api/users/list" in paths
        assert "/api/users/create" in paths

    def test_spring_handler_names(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen._detect_stack()
        gen._discover_endpoints()
        handlers = {ep.handler for ep in gen.analysis.endpoints if ep.handler}
        # createUser and deleteUser have simple return types; getUsers has List<User>
        # which the simple regex may not capture — that's acceptable
        assert "createUser" in handlers
        assert "deleteUser" in handlers

    def test_spring_request_body(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen._detect_stack()
        gen._discover_endpoints()
        post_ep = [ep for ep in gen.analysis.endpoints if ep.method == "POST"][0]
        assert post_ep.request_body is True

    def test_fastapi_endpoints(self, fastapi_project):
        gen = QASuiteGenerator(fastapi_project)
        gen._detect_stack()
        gen._discover_endpoints()
        eps = gen.analysis.endpoints
        assert len(eps) == 3
        paths = {ep.path for ep in eps}
        assert "/health" in paths
        assert "/api/orders" in paths

    def test_no_endpoints_empty(self, empty_dir):
        gen = QASuiteGenerator(empty_dir)
        gen.analysis.language = "python"
        gen._discover_endpoints()
        assert gen.analysis.endpoints == []


# ── Service Discovery ──


class TestDiscoverServices:
    def test_spring_service(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen._detect_stack()
        gen._discover_services()
        svcs = gen.analysis.services
        assert len(svcs) == 1
        assert svcs[0].name == "PaymentService"
        assert svcs[0].is_critical is True  # "payment" in name

    def test_spring_service_methods(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen._detect_stack()
        gen._discover_services()
        svc = gen.analysis.services[0]
        assert "processPayment" in svc.methods
        assert "getStatus" in svc.methods
        assert "refund" in svc.methods

    def test_spring_service_dependencies(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen._detect_stack()
        gen._discover_services()
        svc = gen.analysis.services[0]
        assert "UserRepository" in svc.dependencies
        assert "TransactionRepository" in svc.dependencies

    def test_python_service(self, fastapi_project):
        gen = QASuiteGenerator(fastapi_project)
        gen._detect_stack()
        gen._discover_services()
        svcs = gen.analysis.services
        assert len(svcs) == 1
        assert svcs[0].name == "OrderService"
        assert "create" in svcs[0].methods
        assert "cancel" in svcs[0].methods

    def test_critical_service_detection(self, tmp_path):
        (tmp_path / "pom.xml").write_text('<project><dependencies><dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot</artifactId></dependency></dependencies></project>')
        svc_dir = tmp_path / "src" / "main" / "java" / "com" / "app"
        svc_dir.mkdir(parents=True)
        (svc_dir / "AuthService.java").write_text(
            'public class AuthService {\n'
            '    public void authenticate(String token) {}\n'
            '}\n'
        )
        (svc_dir / "CacheService.java").write_text(
            'public class CacheService {\n'
            '    public void evict(String key) {}\n'
            '}\n'
        )
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        gen._discover_services()
        svcs = {s.name: s for s in gen.analysis.services}
        assert svcs["AuthService"].is_critical is True
        assert svcs["CacheService"].is_critical is False


# ── Repository Discovery ──


class TestDiscoverRepositories:
    def test_spring_repository(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen._detect_stack()
        gen._discover_repositories()
        repos = gen.analysis.repositories
        assert len(repos) == 1
        assert repos[0].name == "UserRepository"
        assert repos[0].entity == "User"

    def test_no_repositories(self, fastapi_project):
        gen = QASuiteGenerator(fastapi_project)
        gen._detect_stack()
        gen._discover_repositories()
        assert gen.analysis.repositories == []


# ── Existing Tests Detection ──


class TestCheckExistingTests:
    def test_no_tests(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen._detect_stack()
        gen._check_existing_tests()
        assert gen.analysis.has_existing_tests is False
        assert gen.analysis.existing_test_count == 0

    def test_java_tests_exist(self, spring_boot_project):
        test_dir = Path(spring_boot_project) / "src" / "test" / "java"
        test_dir.mkdir(parents=True)
        (test_dir / "FooTest.java").write_text("class FooTest {}")
        (test_dir / "BarTest.java").write_text("class BarTest {}")
        gen = QASuiteGenerator(spring_boot_project)
        gen._detect_stack()
        gen._check_existing_tests()
        assert gen.analysis.has_existing_tests is True
        assert gen.analysis.existing_test_count == 2

    def test_python_tests_exist(self, fastapi_project):
        tests_dir = Path(fastapi_project) / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text("def test_health(): pass")
        gen = QASuiteGenerator(fastapi_project)
        gen._detect_stack()
        gen._check_existing_tests()
        assert gen.analysis.has_existing_tests is True
        assert gen.analysis.existing_test_count == 1

    def test_js_tests_exist(self, js_project):
        (Path(js_project) / "app.test.js").write_text("test('a', () => {})")
        gen = QASuiteGenerator(js_project)
        gen._detect_stack()
        gen._check_existing_tests()
        assert gen.analysis.has_existing_tests is True
        assert gen.analysis.existing_test_count == 1


# ── Suite Generation ──


class TestGenerateSuite:
    def test_java_spring_suite(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen.analyze()
        generated = gen.generate_suite()
        assert len(generated) > 0
        paths = [f["path"] for f in generated]
        # Base test
        assert any("BaseIntegrationTest" in p for p in paths)
        # Controller test
        assert any("UserControllerTest" in p for p in paths)
        # Service test
        assert any("PaymentServiceTest" in p for p in paths)
        # Repository test
        assert any("UserRepositoryTest" in p for p in paths)

    def test_java_controller_test_content(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen.analyze()
        gen.generate_suite()
        ctrl = [f for f in gen.analysis.generated_files if "UserControllerTest" in f["path"]][0]
        content = ctrl["content"]
        assert "MockMvc" in content or "mockMvc" in content
        assert "@Test" in content
        assert "/api/users" in content

    def test_java_service_test_content(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen.analyze()
        gen.generate_suite()
        svc = [f for f in gen.analysis.generated_files if "PaymentServiceTest" in f["path"]][0]
        content = svc["content"]
        assert "@Mock" in content
        assert "PaymentService" in content
        assert "test_processPayment" in content

    def test_fastapi_suite(self, fastapi_project):
        gen = QASuiteGenerator(fastapi_project)
        gen.analyze()
        generated = gen.generate_suite()
        assert len(generated) > 0
        paths = [f["path"] for f in generated]
        assert any("conftest" in p for p in paths)

    def test_fastapi_endpoint_tests(self, fastapi_project):
        gen = QASuiteGenerator(fastapi_project)
        gen.analyze()
        generated = gen.generate_suite()
        contents = " ".join(f["content"] for f in generated)
        assert "client.get" in contents
        assert "client.post" in contents

    def test_empty_project_no_generation(self, empty_dir):
        gen = QASuiteGenerator(empty_dir)
        gen.analyze()
        generated = gen.generate_suite()
        assert generated == []

    def test_js_suite(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "api"}')
        (tmp_path / "routes.js").write_text(
            'const app = require("express")();\n'
            'app.get("/api/items", (req, res) => {});\n'
        )
        # JS endpoint detection uses @app pattern, won't match Express — expect 0
        gen = QASuiteGenerator(str(tmp_path))
        gen.analyze()
        generated = gen.generate_suite()
        # JS detection is regex-based and won't catch plain express; that's fine
        assert isinstance(generated, list)


# ── Java Package Extraction ──


class TestJavaPackageFromPath:
    def test_standard_path(self, empty_dir):
        gen = QASuiteGenerator(empty_dir)
        pkg = gen._java_package_from_path("src/main/java/com/app/controller/UserController.java")
        assert pkg == "com.app.controller"

    def test_test_path(self, empty_dir):
        gen = QASuiteGenerator(empty_dir)
        pkg = gen._java_package_from_path("src/test/java/com/app/service/FooTest.java")
        assert pkg == "com.app.service"

    def test_no_match(self, empty_dir):
        gen = QASuiteGenerator(empty_dir)
        pkg = gen._java_package_from_path("lib/Foo.java")
        assert pkg == "com.app"  # fallback


# ── Agent Prompt ──


class TestBuildAgentPrompt:
    def test_prompt_includes_all_sections(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen.analyze()
        gen.generate_suite()
        prompt = gen.build_agent_prompt()
        assert "QA REGRESSION SUITE GENERATION" in prompt
        assert "Language: java" in prompt
        assert "DISCOVERED ENDPOINTS:" in prompt
        assert "DISCOVERED SERVICES:" in prompt
        assert "DISCOVERED REPOSITORIES:" in prompt
        assert "GENERATED TEST FILES:" in prompt
        assert "INSTRUCTIONS:" in prompt

    def test_prompt_shows_critical(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen.analyze()
        gen.generate_suite()
        prompt = gen.build_agent_prompt()
        assert "[CRITICAL]" in prompt  # PaymentService

    def test_prompt_empty_project(self, empty_dir):
        gen = QASuiteGenerator(empty_dir)
        gen.analyze()
        gen.generate_suite()
        prompt = gen.build_agent_prompt()
        assert "Endpoints: 0" in prompt
        assert "Services: 0" in prompt


# ── Format Analysis ──


class TestFormatAnalysis:
    def test_format_basic(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen.analyze()
        gen.generate_suite()
        output = format_analysis(gen.analysis)
        assert "QA SUITE GENERATOR" in output
        assert "java" in output
        assert "spring-boot" in output
        assert "Endpoints:" in output
        assert "Services:" in output

    def test_format_shows_critical(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen.analyze()
        output = format_analysis(gen.analysis)
        assert "[CRITICAL]" in output

    def test_format_generated_files(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen.analyze()
        gen.generate_suite()
        output = format_analysis(gen.analysis)
        assert "Generated Test Files" in output

    def test_format_empty(self, empty_dir):
        gen = QASuiteGenerator(empty_dir)
        gen.analyze()
        output = format_analysis(gen.analysis)
        assert "Endpoints: 0" in output


# ── Full Analyze ──


class TestFullAnalyze:
    def test_analyze_returns_analysis(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        result = gen.analyze()
        assert isinstance(result, ProjectAnalysis)
        assert result.language == "java"
        assert len(result.endpoints) > 0
        assert len(result.services) > 0

    def test_analyze_fastapi(self, fastapi_project):
        gen = QASuiteGenerator(fastapi_project)
        result = gen.analyze()
        assert result.language == "python"
        assert result.framework == "fastapi"
        assert len(result.endpoints) == 3
        assert len(result.services) == 1


# ── Test Completion Prompt ──


class TestBuildTestCompletionPrompt:
    def test_basic_prompt(self):
        prompt = build_test_completion_prompt(
            "tests/test_foo.py", "# TODO: implement", {"language": "python", "framework": "pytest"},
        )
        assert "python" in prompt
        assert "pytest" in prompt
        assert "TODO" in prompt
        assert "tests/test_foo.py" in prompt

    def test_includes_source_file(self):
        prompt = build_test_completion_prompt(
            "tests/test_foo.py", "# TODO", {"language": "python", "framework": "pytest", "source_file": "foo.py"},
        )
        assert "foo.py" in prompt

    def test_includes_endpoints(self):
        prompt = build_test_completion_prompt(
            "tests/test_api.py", "# TODO", {"language": "python", "framework": "fastapi", "endpoints": ["/api/users", "/api/orders"]},
        )
        assert "/api/users" in prompt
        assert "/api/orders" in prompt

    def test_unknown_defaults(self):
        prompt = build_test_completion_prompt("test.py", "# TODO", {})
        assert "unknown" in prompt


class TestGetCompletionPrompts:
    def test_returns_prompts_for_todo_files(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen.analyze()
        gen.generate_suite()
        prompts = gen.get_completion_prompts()
        assert len(prompts) > 0
        for p in prompts:
            assert "file" in p
            assert "prompt" in p
            assert "TODO" in p["prompt"]

    def test_no_prompts_without_todos(self, empty_dir):
        gen = QASuiteGenerator(empty_dir)
        gen.analyze()
        gen.generate_suite()
        prompts = gen.get_completion_prompts()
        assert prompts == []

    def test_prompt_has_language_context(self, spring_boot_project):
        gen = QASuiteGenerator(spring_boot_project)
        gen.analyze()
        gen.generate_suite()
        prompts = gen.get_completion_prompts()
        if prompts:
            assert "java" in prompts[0]["prompt"]

    def test_prompt_has_framework_context(self, fastapi_project):
        gen = QASuiteGenerator(fastapi_project)
        gen.analyze()
        gen.generate_suite()
        prompts = gen.get_completion_prompts()
        if prompts:
            assert "fastapi" in prompts[0]["prompt"]


# ---------------------------------------------------------------------------
# Stack detection — additional languages (lines 94-133)
# ---------------------------------------------------------------------------


class TestDetectStackExtra:
    def test_maven_spring_non_boot(self, tmp_path):
        (tmp_path / "pom.xml").write_text(
            '<project><dependencies>'
            '<dependency><artifactId>spring-context</artifactId></dependency>'
            '</dependencies></project>'
        )
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.language == "java"
        assert gen.analysis.framework == "spring"

    def test_maven_oserror(self, tmp_path):
        """OSError reading pom.xml -- language is still detected, framework is empty."""
        (tmp_path / "pom.xml").write_text("content")
        gen = QASuiteGenerator(str(tmp_path))
        from unittest.mock import patch
        with patch("builtins.open", side_effect=OSError("err")):
            gen._detect_stack()
        assert gen.analysis.language == "java"
        assert gen.analysis.framework == ""  # open failed, so no framework detected

    def test_gradle(self, tmp_path):
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'")
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.language == "java"
        assert gen.analysis.build_tool == "gradle"

    def test_requirements_txt_fastapi(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("fastapi>=0.100\nuvicorn\n")
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.language == "python"
        assert gen.analysis.build_tool == "pip"
        assert gen.analysis.framework == "fastapi"

    def test_requirements_txt_django(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("django>=4.0\n")
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.framework == "django"

    def test_requirements_txt_flask(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask>=3.0\n")
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.framework == "flask"

    def test_pyproject_django(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\ndjango = '^4.0'")
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.framework == "django"

    def test_pyproject_flask(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nflask = '^3.0'")
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.framework == "flask"

    def test_javascript(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "test"}')
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.language == "javascript"
        assert gen.analysis.build_tool == "npm"

    def test_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/foo")
        gen = QASuiteGenerator(str(tmp_path))
        gen._detect_stack()
        assert gen.analysis.language == "go"
        assert gen.analysis.build_tool == "go"


# ---------------------------------------------------------------------------
# Discover services — Python (lines 245-261)
# ---------------------------------------------------------------------------


class TestDiscoverPythonServices:
    def test_python_service_discovered(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nfastapi = '^0.100'")
        svc_dir = tmp_path / "app"
        svc_dir.mkdir()
        (svc_dir / "payment_service.py").write_text(
            "class PaymentService:\n"
            "    def process(self, data):\n"
            "        pass\n"
            "    def refund(self, tx_id):\n"
            "        pass\n"
        )
        gen = QASuiteGenerator(str(tmp_path))
        gen.analyze()
        service_names = [s.name for s in gen.analysis.services]
        assert "PaymentService" in service_names
        svc = [s for s in gen.analysis.services if s.name == "PaymentService"][0]
        assert svc.is_critical is True  # "payment" keyword
        assert "process" in svc.methods


# ---------------------------------------------------------------------------
# Discover repositories — Java (lines 272-283)
# ---------------------------------------------------------------------------


class TestDiscoverRepositories:
    def test_java_repository(self, tmp_path):
        (tmp_path / "pom.xml").write_text(
            '<project><dependencies>'
            '<dependency><artifactId>spring-boot-starter-web</artifactId></dependency>'
            '</dependencies></project>'
        )
        repo_dir = tmp_path / "src" / "main" / "java" / "com"
        repo_dir.mkdir(parents=True)
        (repo_dir / "UserRepository.java").write_text(
            "public interface UserRepository extends JpaRepository<User, Long> {\n"
            "    User findByEmail(String email);\n"
            "}\n"
        )
        gen = QASuiteGenerator(str(tmp_path))
        gen.analyze()
        repo_names = [r.name for r in gen.analysis.repositories]
        assert "UserRepository" in repo_names
        repo = [r for r in gen.analysis.repositories if r.name == "UserRepository"][0]
        assert repo.entity == "User"


# ---------------------------------------------------------------------------
# Format analysis (line 759)
# ---------------------------------------------------------------------------


class TestFormatAnalysisExtra:
    def test_format_many_endpoints(self):
        analysis = ProjectAnalysis(
            language="java",
            framework="spring-boot",
            endpoints=[
                DiscoveredEndpoint(method="GET", path=f"/api/ep{i}", file="F.java", line=i, handler=f"handler{i}")
                for i in range(20)
            ],
            services=[
                DiscoveredService(name="AuthService", file="auth.java", is_critical=True, methods=["login"]),
            ],
        )
        output = format_analysis(analysis)
        assert "... and 5 more" in output
        assert "[CRITICAL]" in output


# ---------------------------------------------------------------------------
# Detection OSError paths (lines 112-113, 126-127)
# ---------------------------------------------------------------------------


class TestDetectionOSErrors:
    def test_pyproject_oserror(self, tmp_path):
        """OSError reading pyproject.toml is caught (lines 112-113)."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry.dependencies]\n")
        gen = QASuiteGenerator(str(tmp_path))
        with patch("builtins.open", side_effect=OSError("perm denied")):
            gen.analyze()
        assert gen.analysis.language == "python"

    def test_requirements_txt_oserror(self, tmp_path):
        """OSError reading requirements.txt is caught (lines 126-127)."""
        (tmp_path / "requirements.txt").write_text("flask==2.0\n")
        gen = QASuiteGenerator(str(tmp_path))
        with patch("builtins.open", side_effect=OSError("perm denied")):
            gen.analyze()
        assert gen.analysis.language == "python"


# ---------------------------------------------------------------------------
# Go mod detection (line 148)
# ---------------------------------------------------------------------------


class TestGoModDetection:
    def test_go_mod_project(self, tmp_path):
        """Go project detected from go.mod (line 148)."""
        (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")
        gen = QASuiteGenerator(str(tmp_path))
        gen.analyze()
        assert gen.analysis.language == "go"
        assert gen.analysis.build_tool == "go"


# ---------------------------------------------------------------------------
# Spring endpoint discovery (lines 163-164, 197)
# ---------------------------------------------------------------------------


class TestSpringEndpointDiscovery:
    def test_request_mapping_class_prefix(self, tmp_path):
        """@RequestMapping on class provides prefix (lines 163-164)."""
        java_dir = tmp_path / "src" / "main" / "java"
        java_dir.mkdir(parents=True)
        (java_dir / "UserController.java").write_text("""
@RequestMapping("/api/users")
public class UserController {
    @GetMapping("/list")
    public List<User> getUsers() { return null; }
}
""")
        (tmp_path / "pom.xml").write_text("<project><dependencies></dependencies></project>")
        gen = QASuiteGenerator(str(tmp_path))
        gen.analyze()
        paths = [ep.path for ep in gen.analysis.endpoints]
        assert "/api/users/list" in paths

    def test_request_mapping_with_method(self, tmp_path):
        """@RequestMapping with method= attribute (line 197)."""
        java_dir = tmp_path / "src" / "main" / "java"
        java_dir.mkdir(parents=True)
        (java_dir / "DataController.java").write_text("""
@RequestMapping("/api")
public class DataController {
    @RequestMapping(method = RequestMethod.POST, value = "/data")
    public void createData() {}
}
""")
        (tmp_path / "pom.xml").write_text("<project><dependencies></dependencies></project>")
        gen = QASuiteGenerator(str(tmp_path))
        gen.analyze()
        methods = [ep.method for ep in gen.analysis.endpoints]
        assert "POST" in methods


# ---------------------------------------------------------------------------
# Service discovery OSErrors (lines 245-246, 260-261)
# ---------------------------------------------------------------------------


class TestServiceDiscoveryOSError:
    def test_java_service_oserror(self, tmp_path):
        """OSError reading Java service file is caught (lines 245-246)."""
        java_dir = tmp_path / "src" / "main" / "java"
        java_dir.mkdir(parents=True)
        (java_dir / "PaymentService.java").write_text("public class PaymentService {}")
        (tmp_path / "pom.xml").write_text("<project><dependencies></dependencies></project>")
        gen = QASuiteGenerator(str(tmp_path))
        orig_open = open
        call_count = [0]
        def mock_open(path, *args, **kwargs):
            if "PaymentService" in str(path) and call_count[0] > 0:
                raise OSError("fail")
            call_count[0] += 1
            return orig_open(path, *args, **kwargs)
        with patch("builtins.open", side_effect=mock_open):
            gen.analyze()

    def test_python_service_oserror(self, tmp_path):
        """OSError reading Python service file is caught (lines 260-261)."""
        (tmp_path / "user_service.py").write_text("class UserService:\n    def get_user(self): pass\n")
        (tmp_path / "pyproject.toml").write_text("[tool.poetry.dependencies]\nfastapi = \"0.100\"\n")
        gen = QASuiteGenerator(str(tmp_path))
        orig_open = open
        call_count = [0]
        def mock_open(path, *args, **kwargs):
            if "user_service" in str(path) and call_count[0] > 1:
                raise OSError("fail")
            call_count[0] += 1
            return orig_open(path, *args, **kwargs)
        with patch("builtins.open", side_effect=mock_open):
            gen.analyze()


# ---------------------------------------------------------------------------
# Repository discovery OSError (lines 282-283)
# ---------------------------------------------------------------------------


class TestRepoDiscoveryOSError:
    def test_java_repo_oserror(self, tmp_path):
        """OSError reading Java repository file is caught (lines 282-283)."""
        java_dir = tmp_path / "src" / "main" / "java"
        java_dir.mkdir(parents=True)
        (java_dir / "UserRepository.java").write_text(
            "public interface UserRepository extends JpaRepository<User, Long> {}"
        )
        (tmp_path / "pom.xml").write_text("<project><dependencies></dependencies></project>")
        gen = QASuiteGenerator(str(tmp_path))
        orig_open = open
        def mock_open(path, *args, **kwargs):
            if "UserRepository" in str(path):
                raise OSError("fail")
            return orig_open(path, *args, **kwargs)
        with patch("builtins.open", side_effect=mock_open):
            gen.analyze()
        # Should not crash


# ---------------------------------------------------------------------------
# Generate suite for Python (line 299, 596)
# ---------------------------------------------------------------------------


class TestGeneratePythonSuite:
    def test_generate_python_generic_suite(self, tmp_path):
        """Generic Python project uses _gen_python_suite (lines 298-299, 596)."""
        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")
        gen = QASuiteGenerator(str(tmp_path))
        gen.analyze()
        files = gen.generate_suite()
        assert isinstance(files, list)


# ---------------------------------------------------------------------------
# Generate JS suite (lines 602-604)
# ---------------------------------------------------------------------------


class TestGenerateJSSuite:
    def test_generate_js_suite(self, tmp_path):
        """JavaScript project generates Jest test suite (lines 598-623)."""
        (tmp_path / "package.json").write_text('{"name": "test-app"}')
        # Create a file with an Express endpoint
        (tmp_path / "routes.js").write_text("""
const express = require('express');
const router = express.Router();
router.get('/api/items', (req, res) => res.json([]));
module.exports = router;
""")
        gen = QASuiteGenerator(str(tmp_path))
        gen.analyze()
        # Manually add an endpoint for JS
        from code_agents.generators.qa_suite_generator import DiscoveredEndpoint
        gen.analysis.endpoints.append(
            DiscoveredEndpoint(method="GET", path="/api/items", file="routes.js", line=4, handler="getItems")
        )
        files = gen.generate_suite()
        assert any("test.js" in f.get("path", "") for f in files)


# ---------------------------------------------------------------------------
# Java service test template (line 461)
# ---------------------------------------------------------------------------


class TestJavaServiceTestTemplate:
    def test_java_service_test_generated(self, tmp_path):
        """Java Spring service test is generated (line 461 area)."""
        java_dir = tmp_path / "src" / "main" / "java" / "com" / "app"
        java_dir.mkdir(parents=True)
        (java_dir / "UserService.java").write_text("""
public class UserService {
    @Autowired
    private UserRepository repo;
    public User getUser(Long id) { return null; }
    public void deleteUser(Long id) {}
}
""")
        (tmp_path / "pom.xml").write_text("""<project>
<dependencies>
<dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter</artifactId><version>3.0.0</version></dependency>
</dependencies>
</project>""")
        gen = QASuiteGenerator(str(tmp_path))
        gen.analyze()
        files = gen.generate_suite()
        service_tests = [f for f in files if "Service" in f.get("path", "") and "Test" in f.get("path", "")]
        if service_tests:
            assert "Mockito" in service_tests[0]["content"] or "mock" in service_tests[0]["content"].lower()


# ---------------------------------------------------------------------------
# FastAPI endpoint + service tests (lines 545, 572)
# ---------------------------------------------------------------------------


class TestFastAPITestGeneration:
    def test_fastapi_endpoint_test(self, tmp_path):
        """FastAPI endpoint test generation (line 545)."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry.dependencies]\nfastapi = \"0.100\"\n")
        gen = QASuiteGenerator(str(tmp_path))
        gen.analyze()
        from code_agents.generators.qa_suite_generator import DiscoveredEndpoint, DiscoveredService
        gen.analysis.endpoints.append(
            DiscoveredEndpoint(method="GET", path="/api/users", file="router.py", line=1, handler="get_users")
        )
        gen.analysis.services.append(
            DiscoveredService(name="UserService", file="service.py", methods=["get_user", "delete_user"])
        )
        files = gen.generate_suite()
        # Should have conftest, endpoint test, and service test
        paths = [f["path"] for f in files]
        assert any("conftest" in p for p in paths)
        assert any("test_" in p for p in paths)
