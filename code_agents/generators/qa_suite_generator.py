"""QA Regression Suite Generator — creates full test automation framework from scratch."""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.generators.qa_suite_generator")


@dataclass
class DiscoveredEndpoint:
    method: str  # GET, POST, PUT, DELETE
    path: str
    file: str
    line: int
    handler: str = ""  # function/method name
    params: list[str] = field(default_factory=list)
    request_body: bool = False


@dataclass
class DiscoveredService:
    name: str
    file: str
    methods: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # injected deps
    is_critical: bool = False  # payment, auth, etc.


@dataclass
class DiscoveredRepository:
    name: str
    file: str
    entity: str = ""
    methods: list[str] = field(default_factory=list)


@dataclass
class ProjectAnalysis:
    language: str = ""
    framework: str = ""
    build_tool: str = ""

    endpoints: list[DiscoveredEndpoint] = field(default_factory=list)
    services: list[DiscoveredService] = field(default_factory=list)
    repositories: list[DiscoveredRepository] = field(default_factory=list)

    has_existing_tests: bool = False
    existing_test_count: int = 0

    # Generated
    test_structure: dict = field(default_factory=dict)  # dir -> [files]
    generated_files: list[dict] = field(default_factory=list)  # path, content


class QASuiteGenerator:
    """Analyzes a repo and generates a complete test automation suite."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.analysis = ProjectAnalysis()
        self._skip = {".git", "node_modules", "__pycache__", "venv", ".venv", "target", "build", "dist"}

    def analyze(self) -> ProjectAnalysis:
        """Full project analysis."""
        self._detect_stack()
        self._check_existing_tests()
        self._discover_endpoints()
        self._discover_services()
        self._discover_repositories()
        logger.info(
            "Project analysis: lang=%s framework=%s endpoints=%d services=%d repos=%d existing_tests=%d",
            self.analysis.language, self.analysis.framework,
            len(self.analysis.endpoints), len(self.analysis.services),
            len(self.analysis.repositories), self.analysis.existing_test_count,
        )
        return self.analysis

    def _detect_stack(self):
        a = self.analysis
        if os.path.exists(os.path.join(self.cwd, "pom.xml")):
            a.language = "java"
            a.build_tool = "maven"
            try:
                with open(os.path.join(self.cwd, "pom.xml"), errors="replace") as f:
                    pom = f.read()
                if "spring-boot" in pom:
                    a.framework = "spring-boot"
                elif "spring" in pom:
                    a.framework = "spring"
            except OSError as e:
                logger.debug("QA suite detection: %s", e)
        elif os.path.exists(os.path.join(self.cwd, "build.gradle")) or os.path.exists(os.path.join(self.cwd, "build.gradle.kts")):
            a.language = "java"
            a.build_tool = "gradle"
            a.framework = "spring-boot"  # assume
        elif os.path.exists(os.path.join(self.cwd, "pyproject.toml")):
            a.language = "python"
            a.build_tool = "poetry"
            try:
                with open(os.path.join(self.cwd, "pyproject.toml"), errors="replace") as f:
                    content = f.read().lower()
                if "fastapi" in content:
                    a.framework = "fastapi"
                elif "django" in content:
                    a.framework = "django"
                elif "flask" in content:
                    a.framework = "flask"
            except OSError as e:
                logger.debug("QA suite detection: %s", e)
        elif os.path.exists(os.path.join(self.cwd, "requirements.txt")):
            a.language = "python"
            a.build_tool = "pip"
            try:
                with open(os.path.join(self.cwd, "requirements.txt"), errors="replace") as f:
                    content = f.read().lower()
                if "fastapi" in content:
                    a.framework = "fastapi"
                elif "django" in content:
                    a.framework = "django"
                elif "flask" in content:
                    a.framework = "flask"
            except OSError as e:
                logger.debug("QA suite detection: %s", e)
        elif os.path.exists(os.path.join(self.cwd, "package.json")):
            a.language = "javascript"
            a.build_tool = "npm"
        elif os.path.exists(os.path.join(self.cwd, "go.mod")):
            a.language = "go"
            a.build_tool = "go"

    def _check_existing_tests(self):
        a = self.analysis
        count = 0
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in self._skip]
            for f in files:
                if a.language == "python" and (f.startswith("test_") or f.endswith("_test.py")):
                    count += 1
                elif a.language == "java" and f.endswith("Test.java"):
                    count += 1
                elif a.language == "javascript" and (".test." in f or ".spec." in f):
                    count += 1
                elif a.language == "go" and f.endswith("_test.go"):
                    count += 1
        a.existing_test_count = count
        a.has_existing_tests = count > 0

    def _discover_endpoints(self):
        """Find all API endpoints."""
        a = self.analysis
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in self._skip]
            for f in files:
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, self.cwd)
                try:
                    with open(fpath, errors="replace") as fp:
                        content = fp.read()
                except (OSError, UnicodeDecodeError):
                    continue

                if a.language == "java" and f.endswith(".java"):
                    # Spring @RequestMapping, @GetMapping, etc.
                    class_prefix = ""
                    cm = re.search(r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)', content)
                    if cm:
                        class_prefix = cm.group(1)

                    for m in re.finditer(
                        r'@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']*)["\']',
                        content,
                    ):
                        method = m.group(1).upper()
                        path = class_prefix + m.group(2)
                        line = content[: m.start()].count("\n") + 1
                        handler_match = re.search(
                            r'(?:public|private)\s+\w+\s+(\w+)\s*\(',
                            content[m.end() : m.end() + 200],
                        )
                        handler = handler_match.group(1) if handler_match else ""
                        has_body = "@RequestBody" in content[m.end() : m.end() + 300]
                        a.endpoints.append(DiscoveredEndpoint(
                            method=method, path=path, file=rel, line=line,
                            handler=handler, request_body=has_body,
                        ))

                    # Also @RequestMapping with method=
                    for m in re.finditer(
                        r'@RequestMapping\s*\(.*?method\s*=\s*RequestMethod\.(\w+).*?value\s*=\s*["\']([^"\']+)',
                        content,
                        re.DOTALL,
                    ):
                        a.endpoints.append(DiscoveredEndpoint(
                            method=m.group(1).upper(),
                            path=class_prefix + m.group(2),
                            file=rel,
                            line=content[: m.start()].count("\n") + 1,
                        ))

                elif a.language == "python" and f.endswith(".py"):
                    # FastAPI/Flask decorators
                    for m in re.finditer(
                        r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(["\']([^"\']+)',
                        content,
                    ):
                        line = content[: m.start()].count("\n") + 1
                        handler_match = re.search(
                            r'(?:async\s+)?def\s+(\w+)', content[m.end() : m.end() + 200]
                        )
                        handler = handler_match.group(1) if handler_match else ""
                        a.endpoints.append(DiscoveredEndpoint(
                            method=m.group(1).upper(), path=m.group(2),
                            file=rel, line=line, handler=handler,
                        ))

    def _discover_services(self):
        """Find service classes."""
        a = self.analysis
        critical_names = {"payment", "transaction", "auth", "security", "billing", "order", "acquiring"}

        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in self._skip]
            for f in files:
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, self.cwd)

                if a.language == "java" and f.endswith("Service.java"):
                    try:
                        with open(fpath, errors="replace") as fp:
                            content = fp.read()
                        name = f.replace(".java", "")
                        methods = re.findall(r'(?:public|protected)\s+\w+\s+(\w+)\s*\(', content)
                        deps = re.findall(r'@Autowired\s+(?:private\s+)?(\w+)', content)
                        if not deps:
                            deps = re.findall(r'private\s+final\s+(\w+)', content)
                        is_crit = any(c in name.lower() for c in critical_names)
                        a.services.append(DiscoveredService(
                            name=name, file=rel, methods=methods,
                            dependencies=deps, is_critical=is_crit,
                        ))
                    except (OSError, UnicodeDecodeError) as e:
                        logger.debug("QA suite detection: %s", e)

                elif a.language == "python" and f.endswith(".py") and "service" in f.lower():
                    try:
                        with open(fpath, errors="replace") as fp:
                            content = fp.read()
                        for cm in re.finditer(r'class\s+(\w+Service)', content):
                            name = cm.group(1)
                            class_body = content[cm.end() :]
                            methods = re.findall(r'def\s+(\w+)\s*\(self', class_body[:3000])
                            is_crit = any(c in name.lower() for c in critical_names)
                            a.services.append(DiscoveredService(
                                name=name, file=rel, methods=methods, is_critical=is_crit,
                            ))
                    except (OSError, UnicodeDecodeError) as e:
                        logger.debug("QA suite detection: %s", e)

    def _discover_repositories(self):
        """Find repository/DAO classes."""
        a = self.analysis
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in self._skip]
            for f in files:
                if a.language == "java" and (f.endswith("Repository.java") or f.endswith("Dao.java")):
                    fpath = os.path.join(root, f)
                    rel = os.path.relpath(fpath, self.cwd)
                    try:
                        with open(fpath, errors="replace") as fp:
                            content = fp.read()
                        name = f.replace(".java", "")
                        entity_match = re.search(r'extends\s+\w+Repository\s*<\s*(\w+)', content)
                        entity = entity_match.group(1) if entity_match else ""
                        methods = re.findall(r'(?:public\s+)?\w+\s+(\w+)\s*\(', content)
                        a.repositories.append(DiscoveredRepository(
                            name=name, file=rel, entity=entity, methods=methods,
                        ))
                    except (OSError, UnicodeDecodeError):
                        pass

    # ------------------------------------------------------------------
    # Test Suite Generation
    # ------------------------------------------------------------------

    def generate_suite(self) -> list[dict]:
        """Generate full test suite based on analysis."""
        a = self.analysis
        generated: list[dict] = []

        if a.language == "java" and a.framework == "spring-boot":
            generated.extend(self._gen_java_spring_suite())
        elif a.language == "python" and a.framework == "fastapi":
            generated.extend(self._gen_python_fastapi_suite())
        elif a.language == "python":
            generated.extend(self._gen_python_suite())
        elif a.language == "javascript":
            generated.extend(self._gen_js_suite())

        a.generated_files = generated
        logger.info("Generated %d test files for %s/%s", len(generated), a.language, a.framework)
        return generated

    def _gen_java_spring_suite(self) -> list[dict]:
        """Generate Spring Boot test suite."""
        files: list[dict] = []

        # 1. Base test config
        files.append({
            "path": "src/test/java/com/app/BaseIntegrationTest.java",
            "description": "Base integration test with Spring context",
            "content": self._java_base_test_template(),
        })

        # 2. Controller tests (for each endpoint)
        controllers: dict[str, list[DiscoveredEndpoint]] = {}
        for ep in self.analysis.endpoints:
            controllers.setdefault(ep.file, []).append(ep)

        for file, endpoints in controllers.items():
            class_name = Path(file).stem + "Test"
            pkg = self._java_package_from_path(file)
            test_path = file.replace("src/main/java", "src/test/java").replace(".java", "Test.java")

            content = self._java_controller_test_template(class_name, pkg, Path(file).stem, endpoints)
            files.append({
                "path": test_path,
                "description": f"Controller test for {Path(file).stem} ({len(endpoints)} endpoints)",
                "content": content,
            })

        # 3. Service tests
        for svc in self.analysis.services:
            class_name = svc.name + "Test"
            test_path = svc.file.replace("src/main/java", "src/test/java").replace(".java", "Test.java")
            content = self._java_service_test_template(class_name, svc)
            files.append({
                "path": test_path,
                "description": f"Service test for {svc.name} ({len(svc.methods)} methods)",
                "content": content,
            })

        # 4. Repository tests
        for repo in self.analysis.repositories:
            class_name = repo.name + "Test"
            test_path = repo.file.replace("src/main/java", "src/test/java").replace(".java", "Test.java")
            content = self._java_repo_test_template(class_name, repo)
            files.append({
                "path": test_path,
                "description": f"Repository test for {repo.name}",
                "content": content,
            })

        return files

    def _java_base_test_template(self) -> str:
        return '''package com.app;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MockMvc;
import com.fasterxml.jackson.databind.ObjectMapper;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
public abstract class BaseIntegrationTest {

    @Autowired
    protected MockMvc mockMvc;

    @Autowired
    protected ObjectMapper objectMapper;

    protected String toJson(Object obj) throws Exception {
        return objectMapper.writeValueAsString(obj);
    }
}
'''

    def _java_package_from_path(self, filepath: str) -> str:
        """Extract Java package from file path."""
        match = re.search(r'src/(?:main|test)/java/(.+)/\w+\.java', filepath)
        if match:
            return match.group(1).replace("/", ".")
        return "com.app"

    def _java_controller_test_template(
        self, class_name: str, pkg: str, controller: str, endpoints: list[DiscoveredEndpoint],
    ) -> str:
        imports = f'''package {pkg};

import com.app.BaseIntegrationTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.DisplayName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class {class_name} extends BaseIntegrationTest {{
'''
        tests = []
        for ep in endpoints:
            method_lower = ep.method.lower()
            test_name = f"test_{ep.handler or method_lower}_{ep.path.replace('/', '_').strip('_')}"
            test_name = re.sub(r'[^a-zA-Z0-9_]', '_', test_name)

            tests.append(f'''
    @Test
    @DisplayName("{ep.method} {ep.path}")
    void {test_name}() throws Exception {{
        mockMvc.perform({method_lower}("{ep.path}")
                .contentType("application/json"))
                .andExpect(status().isOk());
    }}

    @Test
    @DisplayName("{ep.method} {ep.path} — not found")
    void {test_name}_notFound() throws Exception {{
        mockMvc.perform({method_lower}("{ep.path}/nonexistent")
                .contentType("application/json"))
                .andExpect(status().isNotFound());
    }}
''')

        return imports + "\n".join(tests) + "\n}\n"

    def _java_service_test_template(self, class_name: str, svc: DiscoveredService) -> str:
        pkg = self._java_package_from_path(svc.file)
        deps_mock = "\n".join(
            f"    @Mock\n    private {d} {d[0].lower()}{d[1:]};" for d in svc.dependencies
        )

        content = f'''package {pkg};

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class {class_name} {{

{deps_mock}

    @InjectMocks
    private {svc.name} service;

'''
        for method in svc.methods:
            if method.startswith("_") or method in ("toString", "hashCode", "equals"):
                continue
            content += f'''    @Test
    @DisplayName("{svc.name}.{method}() — happy path")
    void test_{method}_success() {{
        // TODO: Setup mocks
        // TODO: Call service.{method}(...)
        // TODO: Assert result
        assertNotNull(service);
    }}

    @Test
    @DisplayName("{svc.name}.{method}() — error case")
    void test_{method}_error() {{
        // TODO: Setup mocks to throw
        // TODO: Assert exception or error handling
        assertNotNull(service);
    }}

'''
        content += "}\n"
        return content

    def _java_repo_test_template(self, class_name: str, repo: DiscoveredRepository) -> str:
        pkg = self._java_package_from_path(repo.file)
        return f'''package {pkg};

import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.DisplayName;
import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
class {class_name} {{

    @Autowired
    private {repo.name} repository;

    @Test
    @DisplayName("Repository should be injected")
    void testRepositoryLoads() {{
        assertNotNull(repository);
    }}

    @Test
    @DisplayName("Save and find {repo.entity or 'entity'}")
    void testSaveAndFind() {{
        // TODO: Create entity, save, find by ID, assert
    }}
}}
'''

    def _gen_python_fastapi_suite(self) -> list[dict]:
        """Generate FastAPI test suite."""
        files: list[dict] = []

        # conftest.py
        files.append({
            "path": "tests/conftest.py",
            "description": "Shared fixtures — test client, DB session",
            "content": '''"""Shared test fixtures."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    from app import app  # adjust import
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Auth headers for protected endpoints."""
    return {"Authorization": "Bearer test-token"}
''',
        })

        # Endpoint tests
        seen_files: set[str] = set()
        for ep in self.analysis.endpoints:
            test_file = f"tests/test_{ep.handler or ep.path.strip('/').replace('/', '_')}.py"
            if test_file in seen_files:
                continue
            seen_files.add(test_file)
            method = ep.method.lower()
            files.append({
                "path": test_file,
                "description": f"Test {ep.method} {ep.path}",
                "content": f'''"""Tests for {ep.method} {ep.path}."""
import pytest


def test_{ep.handler or 'endpoint'}_success(client):
    response = client.{method}("{ep.path}")
    assert response.status_code == 200


def test_{ep.handler or 'endpoint'}_not_found(client):
    response = client.{method}("{ep.path}/nonexistent")
    assert response.status_code in (404, 405)
''',
            })

        # Service tests
        for svc in self.analysis.services:
            test_file = f"tests/test_{svc.name.lower()}.py"
            test_methods = []
            for m in svc.methods:
                if m.startswith("_"):
                    continue
                test_methods.append(f'''
def test_{m}_success():
    """Test {svc.name}.{m}() happy path."""
    # TODO: mock dependencies, call method, assert
    pass


def test_{m}_error():
    """Test {svc.name}.{m}() error handling."""
    # TODO: mock to raise, assert exception
    pass
''')

            files.append({
                "path": test_file,
                "description": f"Tests for {svc.name}",
                "content": f'"""Tests for {svc.name}."""\nimport pytest\n\n' + "\n".join(test_methods),
            })

        return files

    def _gen_python_suite(self) -> list[dict]:
        """Generate generic Python test suite."""
        return self._gen_python_fastapi_suite()  # similar structure

    def _gen_js_suite(self) -> list[dict]:
        """Generate JavaScript/Jest test suite."""
        files: list[dict] = []
        for ep in self.analysis.endpoints:
            test_file = f"__tests__/{ep.handler or ep.path.strip('/').replace('/', '_')}.test.js"
            method = ep.method.lower()
            files.append({
                "path": test_file,
                "description": f"Test {ep.method} {ep.path}",
                "content": f'''const request = require('supertest');
const app = require('../app');

describe('{ep.method} {ep.path}', () => {{
  it('should return 200', async () => {{
    const res = await request(app).{method}('{ep.path}');
    expect(res.status).toBe(200);
  }});

  it('should handle not found', async () => {{
    const res = await request(app).{method}('{ep.path}/nonexistent');
    expect(res.status).toBe(404);
  }});
}});
''',
            })
        return files

    # ------------------------------------------------------------------
    # Build delegation prompt for the agent
    # ------------------------------------------------------------------

    def build_agent_prompt(self) -> str:
        """Build a comprehensive prompt for qa-regression agent."""
        a = self.analysis
        parts = []
        parts.append("QA REGRESSION SUITE GENERATION")
        parts.append(f"Language: {a.language} | Framework: {a.framework} | Build: {a.build_tool}")
        parts.append(f"Existing tests: {a.existing_test_count}")
        parts.append(f"Endpoints: {len(a.endpoints)} | Services: {len(a.services)} | Repositories: {len(a.repositories)}")
        parts.append("")

        if a.endpoints:
            parts.append("DISCOVERED ENDPOINTS:")
            for ep in a.endpoints:
                parts.append(f"  {ep.method} {ep.path} → {ep.handler}() [{ep.file}:{ep.line}]")
            parts.append("")

        if a.services:
            parts.append("DISCOVERED SERVICES:")
            for svc in a.services:
                crit = " [CRITICAL]" if svc.is_critical else ""
                parts.append(f"  {svc.name}{crit} — {len(svc.methods)} methods, deps: {', '.join(svc.dependencies)}")
            parts.append("")

        if a.repositories:
            parts.append("DISCOVERED REPOSITORIES:")
            for repo in a.repositories:
                parts.append(f"  {repo.name} ({repo.entity}) — {len(repo.methods)} methods")
            parts.append("")

        parts.append("GENERATED TEST FILES:")
        for f in a.generated_files:
            parts.append(f"  {f['path']} — {f['description']}")
        parts.append("")

        parts.append("INSTRUCTIONS:")
        parts.append("1. Review and complete the generated test skeleton files")
        parts.append("2. Fill in TODO sections with actual test logic")
        parts.append("3. Add edge cases, boundary tests, error scenarios")
        parts.append("4. Ensure critical services (payment, auth) have thorough coverage")
        parts.append("5. Use [DELEGATE:code-tester] for writing individual complex test files")
        parts.append("6. After writing, run tests to verify they pass")
        parts.append("7. Git: create branch, add files, commit (do NOT push)")

        return "\n".join(parts)

    def get_completion_prompts(self) -> list[dict]:
        """Return completion prompts for each generated file that contains TODOs.

        Returns a list of dicts: ``[{"file": path, "prompt": prompt}]``.
        """
        prompts: list[dict] = []
        a = self.analysis
        context = {
            "language": a.language,
            "framework": a.framework,
        }
        for gen_file in a.generated_files:
            content = gen_file.get("content", "")
            if "TODO" not in content:
                continue
            # Try to infer the source file being tested
            source_file = None
            path = gen_file["path"]
            if a.language == "java":
                source_file = path.replace("src/test/java", "src/main/java").replace("Test.java", ".java")
            elif a.language == "python" and path.startswith("tests/test_"):
                source_file = path.replace("tests/test_", "").replace(".py", "") + ".py"

            file_context = dict(context)
            if source_file:
                file_context["source_file"] = source_file
            # Attach relevant endpoints
            ep_paths = [ep.path for ep in a.endpoints]
            if ep_paths:
                file_context["endpoints"] = ep_paths

            prompt = build_test_completion_prompt(path, content, file_context)
            prompts.append({"file": path, "prompt": prompt})
        return prompts


def build_test_completion_prompt(file_path: str, skeleton_code: str, context: dict) -> str:
    """Build a prompt for code-tester agent to complete TODO stubs in generated tests."""
    language = context.get("language", "unknown")
    framework = context.get("framework", "unknown")

    prompt = f"""Complete the TODO placeholders in this {language} test file.

File: {file_path}
Framework: {framework}

Current skeleton:
```{language.lower()}
{skeleton_code}
```

Instructions:
- Replace every // TODO or # TODO comment with actual test logic
- Replace `pass` statements with real assertions
- Add proper mocking for dependencies
- Include edge cases (null inputs, empty collections, error conditions)
- Follow {framework} testing conventions
- Keep the existing test structure and class names
"""

    if context.get("source_file"):
        prompt += f"\nSource file being tested: {context['source_file']}\n"
    if context.get("endpoints"):
        prompt += f"\nEndpoints: {', '.join(context['endpoints'][:10])}\n"

    return prompt


def format_analysis(analysis: ProjectAnalysis) -> str:
    """Format project analysis for terminal display."""
    lines = []
    lines.append("  ══ QA SUITE GENERATOR ══")
    lines.append(f"  Stack: {analysis.language} / {analysis.framework} / {analysis.build_tool}")
    lines.append(f"  Existing tests: {analysis.existing_test_count}")

    lines.append(f"\n  Discovered:")
    lines.append(f"    Endpoints: {len(analysis.endpoints)}")
    lines.append(f"    Services: {len(analysis.services)}")
    lines.append(f"    Repositories: {len(analysis.repositories)}")

    if analysis.endpoints:
        lines.append(f"\n  Endpoints:")
        for ep in analysis.endpoints[:15]:
            lines.append(f"    {ep.method:6} {ep.path} → {ep.handler}()")
        if len(analysis.endpoints) > 15:
            lines.append(f"    ... and {len(analysis.endpoints) - 15} more")

    if analysis.services:
        lines.append(f"\n  Services:")
        for svc in analysis.services:
            crit = " [CRITICAL]" if svc.is_critical else ""
            lines.append(f"    {svc.name}{crit} — {len(svc.methods)} methods")

    if analysis.generated_files:
        lines.append(f"\n  Generated Test Files ({len(analysis.generated_files)}):")
        for f in analysis.generated_files:
            lines.append(f"    {f['path']} — {f['description']}")

    return "\n".join(lines)
