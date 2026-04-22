"""AI-Powered Test Generator — fully automated test generation pipeline.

Scans source files with AST parsers, uses the knowledge graph for dependency
context, auto-delegates to the code-tester agent via the backend dispatcher,
writes test files to disk, and optionally runs them in a fix loop.

Usage:
    code-agents gen-tests src/payments/       # directory
    code-agents gen-tests src/payments/api.py # single file
    code-agents gen-tests --all               # entire repo (gaps only)
    code-agents gen-tests --verify            # run generated tests after writing
    code-agents gen-tests --dry-run           # show plan, don't generate
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.generators.test_generator")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileAnalysis:
    """Analysis result for a single source file."""
    file_path: str          # relative path
    abs_path: str           # absolute path
    language: str
    functions: list[dict] = field(default_factory=list)   # name, signature, line, docstring
    classes: list[dict] = field(default_factory=list)      # name, methods, line
    imports: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # files that this file imports from
    existing_test_file: str = ""                           # path to existing test file if any
    existing_test_methods: list[str] = field(default_factory=list)
    missing_tests: list[str] = field(default_factory=list) # functions/methods without tests
    risk: str = "medium"
    loc: int = 0


@dataclass
class GenerationResult:
    """Result of generating tests for one file."""
    source_file: str
    test_file: str
    test_code: str = ""
    tests_written: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    error: str = ""
    retries: int = 0


@dataclass
class GenTestsReport:
    """Full pipeline report."""
    repo_path: str
    target_path: str
    files_analyzed: int = 0
    files_with_gaps: int = 0
    files_generated: int = 0
    total_tests_written: int = 0
    total_tests_passed: int = 0
    total_tests_failed: int = 0
    results: list[GenerationResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Skip patterns
# ---------------------------------------------------------------------------

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    "target", "vendor", ".idea", ".vscode", ".next", "coverage",
    "test", "tests", "spec", "specs", "__tests__",
}

_TEST_PATTERNS = {
    "python": (lambda f: f.startswith("test_") or f.endswith("_test.py")),
    "java": (lambda f: f.endswith("Test.java")),
    "javascript": (lambda f: ".test." in f or ".spec." in f),
    "typescript": (lambda f: ".test." in f or ".spec." in f),
    "go": (lambda f: f.endswith("_test.go")),
}

_SOURCE_EXTS = {
    "python": {".py"},
    "java": {".java"},
    "javascript": {".js", ".jsx"},
    "typescript": {".ts", ".tsx"},
    "go": {".go"},
}


# ---------------------------------------------------------------------------
# TestGenerator — the core engine
# ---------------------------------------------------------------------------

class AITestGenerator:  # noqa: pytest doesn't collect (has __init__)
    """Fully automated test generation pipeline with agent-to-agent delegation."""

    def __init__(
        self,
        repo_path: str,
        target_path: str = "",
        *,
        max_files: int = 10,
        verify: bool = False,
        dry_run: bool = False,
        max_retries: int = 3,
    ):
        self.repo_path = os.path.abspath(repo_path)
        self.target_path = target_path
        self.max_files = max_files
        self.verify = verify
        self.dry_run = dry_run
        self.max_retries = max_retries
        self.language = ""
        self.test_framework = ""
        self.report = GenTestsReport(repo_path=self.repo_path, target_path=target_path)
        self._detect_stack()

    # ------------------------------------------------------------------
    # Stack detection
    # ------------------------------------------------------------------

    def _detect_stack(self):
        """Detect project language and test framework."""
        if os.path.exists(os.path.join(self.repo_path, "pyproject.toml")) or \
           os.path.exists(os.path.join(self.repo_path, "setup.py")):
            self.language = "python"
            self.test_framework = "pytest"
        elif os.path.exists(os.path.join(self.repo_path, "pom.xml")):
            self.language = "java"
            self.test_framework = "junit"
        elif os.path.exists(os.path.join(self.repo_path, "build.gradle")) or \
             os.path.exists(os.path.join(self.repo_path, "build.gradle.kts")):
            self.language = "java"
            self.test_framework = "junit"
        elif os.path.exists(os.path.join(self.repo_path, "package.json")):
            self.language = "javascript"
            self.test_framework = "jest"
        elif os.path.exists(os.path.join(self.repo_path, "go.mod")):
            self.language = "go"
            self.test_framework = "go test"

        logger.info("Stack: %s / %s", self.language, self.test_framework)

    # ------------------------------------------------------------------
    # Step 1: Discover & analyze source files
    # ------------------------------------------------------------------

    def discover_files(self) -> list[str]:
        """Find source files in the target path."""
        target = os.path.join(self.repo_path, self.target_path) if self.target_path else self.repo_path

        if os.path.isfile(target):
            return [os.path.relpath(target, self.repo_path)]

        exts = _SOURCE_EXTS.get(self.language, {".py"})
        is_test = _TEST_PATTERNS.get(self.language, lambda f: f.startswith("test_"))
        files = []

        for root, dirs, filenames in os.walk(target):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in filenames:
                ext = os.path.splitext(f)[1]
                if ext in exts and not is_test(f) and not f.startswith("__"):
                    rel = os.path.relpath(os.path.join(root, f), self.repo_path)
                    files.append(rel)

        logger.info("Discovered %d source files in %s", len(files), target)
        return files

    def analyze_file(self, rel_path: str) -> FileAnalysis:
        """Parse a file with AST parsers and find test gaps."""
        from code_agents.parsers import parse_file, detect_language

        abs_path = os.path.join(self.repo_path, rel_path)
        lang = detect_language(abs_path)
        module_info = parse_file(abs_path, lang)

        analysis = FileAnalysis(
            file_path=rel_path,
            abs_path=abs_path,
            language=lang or self.language,
            imports=module_info.imports,
        )

        # Count lines
        try:
            with open(abs_path) as f:
                analysis.loc = sum(1 for _ in f)
        except Exception:
            pass

        # Extract functions and classes
        for sym in module_info.symbols:
            entry = {
                "name": sym.name,
                "signature": sym.signature,
                "line": sym.line_number,
                "docstring": sym.docstring,
            }
            if sym.kind == "function":
                analysis.functions.append(entry)
            elif sym.kind == "class":
                analysis.classes.append(entry)
            elif sym.kind == "method":
                # Group under parent class if possible
                analysis.functions.append(entry)

        # Find existing test file
        analysis.existing_test_file = self._find_test_file(rel_path)
        if analysis.existing_test_file:
            analysis.existing_test_methods = self._extract_test_methods(analysis.existing_test_file)

        # Identify missing tests
        all_names = {f["name"] for f in analysis.functions}
        tested_names = set()
        for method in analysis.existing_test_methods:
            # test_foo_bar → foo_bar, test_FooBar → FooBar
            clean = re.sub(r'^test_?', '', method, flags=re.IGNORECASE)
            tested_names.add(clean.lower())

        for name in all_names:
            if name.startswith("_"):
                continue  # skip private
            if name.lower() not in tested_names:
                analysis.missing_tests.append(name)

        # Risk scoring
        critical_patterns = ["payment", "transaction", "auth", "security", "billing", "order"]
        high_patterns = ["service", "controller", "handler", "processor", "api", "router"]
        name_lower = rel_path.lower()
        if any(p in name_lower for p in critical_patterns):
            analysis.risk = "critical"
        elif any(p in name_lower for p in high_patterns):
            analysis.risk = "high"
        elif not analysis.existing_test_file:
            analysis.risk = "high"

        return analysis

    def _find_test_file(self, rel_path: str) -> str:
        """Find the corresponding test file for a source file."""
        basename = os.path.basename(rel_path)
        name_no_ext = os.path.splitext(basename)[0]

        candidates = []
        if self.language == "python":
            candidates = [
                f"tests/test_{basename}",
                f"test/test_{basename}",
                os.path.join(os.path.dirname(rel_path), f"test_{basename}"),
            ]
        elif self.language == "java":
            candidates = [
                rel_path.replace("src/main/java", "src/test/java").replace(".java", "Test.java"),
            ]
        elif self.language in ("javascript", "typescript"):
            ext = os.path.splitext(basename)[1]
            candidates = [
                os.path.join(os.path.dirname(rel_path), f"{name_no_ext}.test{ext}"),
                os.path.join(os.path.dirname(rel_path), f"{name_no_ext}.spec{ext}"),
                f"__tests__/{name_no_ext}.test{ext}",
            ]
        elif self.language == "go":
            candidates = [
                rel_path.replace(".go", "_test.go"),
            ]

        for candidate in candidates:
            full = os.path.join(self.repo_path, candidate)
            if os.path.exists(full):
                return candidate
        return ""

    def _extract_test_methods(self, test_file: str) -> list[str]:
        """Extract test method names from an existing test file."""
        abs_path = os.path.join(self.repo_path, test_file)
        try:
            with open(abs_path) as f:
                content = f.read()
        except Exception:
            return []

        methods = []
        if self.language == "python":
            methods = re.findall(r'def (test_\w+)', content)
        elif self.language == "java":
            methods = re.findall(r'void\s+(test\w+)', content)
        elif self.language in ("javascript", "typescript"):
            methods = re.findall(r'(?:it|test)\s*\(\s*[\'"](.+?)[\'"]', content)
        elif self.language == "go":
            methods = re.findall(r'func (Test\w+)', content)

        return methods

    def analyze_all(self) -> list[FileAnalysis]:
        """Discover and analyze all target files, return those with gaps."""
        files = self.discover_files()
        analyses = []

        for rel_path in files:
            try:
                analysis = self.analyze_file(rel_path)
                if analysis.missing_tests or not analysis.existing_test_file:
                    analyses.append(analysis)
            except Exception as e:
                logger.warning("Failed to analyze %s: %s", rel_path, e)

        # Sort by risk (critical first), then by missing test count
        risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        analyses.sort(key=lambda a: (risk_order.get(a.risk, 99), -len(a.missing_tests)))

        self.report.files_analyzed = len(files)
        self.report.files_with_gaps = len(analyses)

        logger.info("Analyzed %d files, %d have test gaps", len(files), len(analyses))
        return analyses[:self.max_files]

    # ------------------------------------------------------------------
    # Step 2: Build context from knowledge graph
    # ------------------------------------------------------------------

    def get_dependency_context(self, analysis: FileAnalysis) -> str:
        """Use knowledge graph to get dependency context for a file."""
        try:
            from code_agents.knowledge.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph(self.repo_path)
            if not kg.is_built():
                return ""

            # Get symbols from dependent files
            context_parts = []
            result = kg.query(keywords=[os.path.basename(analysis.file_path)])
            if result:
                deps = result[:5]  # top 5 related files
                for dep in deps:
                    if dep.get("file") != analysis.file_path:
                        context_parts.append(f"  - {dep.get('file', '')}: {dep.get('name', '')} ({dep.get('kind', '')})")

            if context_parts:
                return "Related symbols in the codebase:\n" + "\n".join(context_parts)
        except Exception as e:
            logger.debug("Knowledge graph unavailable: %s", e)

        return ""

    # ------------------------------------------------------------------
    # Step 3: Scan existing test patterns for style matching
    # ------------------------------------------------------------------

    def scan_test_patterns(self) -> str:
        """Read an existing test file to extract the project's test style."""
        test_dirs = ["tests", "test", "spec"]
        for td in test_dirs:
            test_dir = os.path.join(self.repo_path, td)
            if os.path.isdir(test_dir):
                for f in sorted(os.listdir(test_dir))[:3]:
                    fpath = os.path.join(test_dir, f)
                    if os.path.isfile(fpath):
                        try:
                            with open(fpath) as fp:
                                content = fp.read()
                            if len(content) > 100:
                                # Return first 80 lines as style reference
                                lines = content.splitlines()[:80]
                                return "\n".join(lines)
                        except Exception:
                            pass
        return ""

    # ------------------------------------------------------------------
    # Step 4: Build prompt & delegate to code-tester agent
    # ------------------------------------------------------------------

    def _build_generation_prompt(self, analysis: FileAnalysis, source_code: str, dep_context: str, style_ref: str) -> str:
        """Build a rich prompt for the code-tester agent."""
        parts = []

        parts.append(f"Generate comprehensive tests for: {analysis.file_path}")
        parts.append(f"Language: {analysis.language} | Framework: {self.test_framework}")
        parts.append("")

        # Source code
        parts.append(f"## Source Code ({analysis.file_path})")
        parts.append(f"```{analysis.language}")
        parts.append(source_code[:8000])
        parts.append("```")
        parts.append("")

        # Functions that need tests
        if analysis.missing_tests:
            parts.append(f"## Functions/Methods Missing Tests ({len(analysis.missing_tests)})")
            for name in analysis.missing_tests:
                sig = ""
                for f in analysis.functions:
                    if f["name"] == name:
                        sig = f.get("signature", "")
                        break
                parts.append(f"  - `{sig or name}`")
            parts.append("")

        # Existing tests (so AI doesn't duplicate)
        if analysis.existing_test_methods:
            parts.append(f"## Existing Tests (DO NOT duplicate)")
            parts.append(f"Test file: {analysis.existing_test_file}")
            for m in analysis.existing_test_methods[:20]:
                parts.append(f"  - {m}")
            parts.append("")

        # Dependencies context
        if dep_context:
            parts.append(f"## Dependencies")
            parts.append(dep_context)
            parts.append("")

        # Imports
        if analysis.imports:
            parts.append(f"## Imports")
            for imp in analysis.imports[:15]:
                parts.append(f"  - {imp}")
            parts.append("")

        # Style reference
        if style_ref:
            parts.append(f"## Project Test Style (match this pattern)")
            parts.append(f"```{analysis.language}")
            parts.append(style_ref[:3000])
            parts.append("```")
            parts.append("")

        # Test file path
        test_path = self._get_test_path(analysis)
        parts.append(f"## Output")
        parts.append(f"Write the test file to: `{test_path}`")
        parts.append("")

        # Instructions
        parts.append("## Requirements")
        parts.append("1. Write ONLY the complete test file code — no explanations")
        parts.append("2. Include ALL necessary imports")
        parts.append("3. Test happy path, edge cases, error cases, boundary values")
        parts.append("4. Mock ALL external dependencies (network, DB, filesystem, subprocess)")
        parts.append("5. Use descriptive test names that explain the scenario")
        parts.append("6. Match the project's existing test style and conventions")
        parts.append("7. Ensure every test is independent — no shared mutable state")
        parts.append(f"8. Target 80%+ coverage of the source file")
        parts.append("")
        parts.append("Output ONLY the code. No markdown fences, no explanations.")

        return "\n".join(parts)

    def _get_test_path(self, analysis: FileAnalysis) -> str:
        """Determine the test file path."""
        if analysis.existing_test_file:
            return analysis.existing_test_file

        basename = os.path.basename(analysis.file_path)
        name_no_ext = os.path.splitext(basename)[0]
        ext = os.path.splitext(basename)[1]

        if self.language == "python":
            return f"tests/test_{basename}"
        elif self.language == "java":
            return analysis.file_path.replace("src/main/java", "src/test/java").replace(".java", "Test.java")
        elif self.language in ("javascript", "typescript"):
            return os.path.join(os.path.dirname(analysis.file_path), f"{name_no_ext}.test{ext}")
        elif self.language == "go":
            return analysis.file_path.replace(".go", "_test.go")
        return f"tests/test_{basename}"

    async def _delegate_to_agent(self, prompt: str) -> str:
        """Call the code-tester agent via the backend dispatcher and collect response."""
        from code_agents.core.config import agent_loader, settings
        from code_agents.core.backend import run_agent
        from code_agents.core.stream import _inject_context

        # Load agents if not already loaded
        if not agent_loader.list_agents():
            agent_loader.load()

        agent = agent_loader.get("code-tester")
        if not agent:
            raise RuntimeError("code-tester agent not found. Check agents/code_tester/code_tester.yaml")

        # Inject rules and context
        agent = _inject_context(agent, self.repo_path)

        logger.info("Delegating to code-tester agent (prompt=%d chars)", len(prompt))

        # Collect full response text
        response_parts = []
        async for message in run_agent(agent, prompt, cwd_override=self.repo_path):
            msg_type = type(message).__name__
            if msg_type == "AssistantMessage":
                for block in (message.content or []):
                    if hasattr(block, "text") and block.text:
                        response_parts.append(block.text)
            elif msg_type == "ResultMessage":
                if message.is_error:
                    logger.error("Agent returned error")

        full_response = "".join(response_parts)
        logger.info("Agent response: %d chars", len(full_response))
        return full_response

    def _extract_code(self, response: str) -> str:
        """Extract code from agent response, stripping markdown fences."""
        # Try to extract from code blocks first
        patterns = [
            r'```(?:python|java|javascript|typescript|go|jsx|tsx)\n(.*?)```',
            r'```\n(.*?)```',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, response, re.DOTALL)
            if matches:
                # Return the longest match (likely the full test file)
                return max(matches, key=len).strip()

        # If no code blocks, the response is likely raw code
        # Strip any leading/trailing explanation lines
        lines = response.strip().splitlines()
        code_lines = []
        in_code = False
        for line in lines:
            if not in_code:
                # Look for first import/package/from line
                if re.match(r'^(import |from |package |const |var |func |class |def |describe\(|#!)', line):
                    in_code = True
            if in_code:
                code_lines.append(line)

        if code_lines:
            return "\n".join(code_lines)

        return response.strip()

    # ------------------------------------------------------------------
    # Step 5: Write files & verify
    # ------------------------------------------------------------------

    def _write_test_file(self, test_path: str, code: str) -> bool:
        """Write test code to disk."""
        abs_path = os.path.join(self.repo_path, test_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        try:
            with open(abs_path, "w") as f:
                f.write(code)
            logger.info("Wrote test file: %s", test_path)
            return True
        except Exception as e:
            logger.error("Failed to write %s: %s", test_path, e)
            return False

    def _run_test_file(self, test_path: str) -> dict:
        """Run a single test file and return results."""
        abs_path = os.path.join(self.repo_path, test_path)

        if self.language == "python":
            cmd = ["python", "-m", "pytest", abs_path, "-v", "--tb=short", "--no-header", "-q"]
        elif self.language in ("javascript", "typescript"):
            cmd = ["npx", "jest", abs_path, "--no-coverage"]
        elif self.language == "go":
            pkg = os.path.dirname(test_path)
            cmd = ["go", "test", f"./{pkg}/...", "-v", "-run", "Test"]
        elif self.language == "java":
            cmd = ["mvn", "test", f"-Dtest={os.path.basename(test_path).replace('.java', '')}"]
        else:
            return {"passed": False, "output": "Unsupported language", "passed_count": 0, "failed_count": 0}

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120, cwd=self.repo_path,
            )
            output = result.stdout + "\n" + result.stderr
            passed = result.returncode == 0

            # Count tests
            passed_count = 0
            failed_count = 0
            if self.language == "python":
                m = re.search(r'(\d+) passed', output)
                if m:
                    passed_count = int(m.group(1))
                m = re.search(r'(\d+) failed', output)
                if m:
                    failed_count = int(m.group(1))

            return {
                "passed": passed,
                "output": output[-3000:],  # tail
                "passed_count": passed_count,
                "failed_count": failed_count,
            }
        except subprocess.TimeoutExpired:
            return {"passed": False, "output": "Test execution timed out (120s)", "passed_count": 0, "failed_count": 0}
        except Exception as e:
            return {"passed": False, "output": str(e), "passed_count": 0, "failed_count": 0}

    # ------------------------------------------------------------------
    # Fix loop: re-delegate with error context
    # ------------------------------------------------------------------

    async def _fix_loop(self, analysis: FileAnalysis, test_path: str, test_code: str, test_result: dict) -> GenerationResult:
        """If tests fail, re-delegate with error context for auto-fix."""
        result = GenerationResult(
            source_file=analysis.file_path,
            test_file=test_path,
            test_code=test_code,
            tests_passed=test_result.get("passed_count", 0),
            tests_failed=test_result.get("failed_count", 0),
        )

        for retry in range(self.max_retries):
            if test_result.get("passed"):
                result.tests_passed = test_result.get("passed_count", 0)
                result.tests_failed = 0
                result.test_code = test_code
                result.retries = retry
                break

            logger.info("Tests failed for %s, retry %d/%d", test_path, retry + 1, self.max_retries)

            fix_prompt = (
                f"The tests I wrote for {analysis.file_path} are FAILING. Fix them.\n\n"
                f"## Error Output\n```\n{test_result['output'][-2000:]}\n```\n\n"
                f"## Current Test Code ({test_path})\n```{analysis.language}\n{test_code[:6000]}\n```\n\n"
                f"## Source Code ({analysis.file_path})\n"
            )
            try:
                with open(analysis.abs_path) as f:
                    source = f.read()
                fix_prompt += f"```{analysis.language}\n{source[:5000]}\n```\n\n"
            except Exception:
                pass

            fix_prompt += (
                "Fix the failing tests. Output ONLY the complete corrected test file code.\n"
                "No explanations. No markdown fences."
            )

            response = await self._delegate_to_agent(fix_prompt)
            test_code = self._extract_code(response)

            if not test_code:
                result.error = "Agent returned empty response on fix attempt"
                break

            self._write_test_file(test_path, test_code)
            test_result = self._run_test_file(test_path)
            result.tests_passed = test_result.get("passed_count", 0)
            result.tests_failed = test_result.get("failed_count", 0)

        result.retries = min(retry + 1, self.max_retries) if not test_result.get("passed") else result.retries
        if not test_result.get("passed"):
            result.error = f"Tests still failing after {self.max_retries} retries"

        return result

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    async def generate_for_file(self, analysis: FileAnalysis, style_ref: str) -> GenerationResult:
        """Generate tests for a single file — full cycle."""
        test_path = self._get_test_path(analysis)
        result = GenerationResult(source_file=analysis.file_path, test_file=test_path)

        # Read source code
        try:
            with open(analysis.abs_path) as f:
                source_code = f.read()
        except Exception as e:
            result.error = f"Cannot read source: {e}"
            return result

        # Get dependency context
        dep_context = self.get_dependency_context(analysis)

        # Build prompt
        prompt = self._build_generation_prompt(analysis, source_code, dep_context, style_ref)

        # Delegate to code-tester agent
        try:
            response = await self._delegate_to_agent(prompt)
        except Exception as e:
            result.error = f"Agent delegation failed: {e}"
            return result

        # Extract code from response
        test_code = self._extract_code(response)
        if not test_code or len(test_code) < 50:
            result.error = "Agent returned insufficient code"
            return result

        result.test_code = test_code

        # Count generated tests
        if self.language == "python":
            result.tests_written = len(re.findall(r'def test_\w+', test_code))
        elif self.language == "java":
            result.tests_written = len(re.findall(r'@Test', test_code))
        elif self.language in ("javascript", "typescript"):
            result.tests_written = len(re.findall(r'(?:it|test)\s*\(', test_code))
        elif self.language == "go":
            result.tests_written = len(re.findall(r'func Test\w+', test_code))

        # Write test file
        if not self._write_test_file(test_path, test_code):
            result.error = "Failed to write test file"
            return result

        # Verify (run tests + fix loop)
        if self.verify:
            test_result = self._run_test_file(test_path)
            if test_result.get("passed"):
                result.tests_passed = test_result.get("passed_count", 0)
            else:
                # Enter fix loop
                result = await self._fix_loop(analysis, test_path, test_code, test_result)

        return result

    async def run(self, on_progress=None) -> GenTestsReport:
        """Run the full pipeline.

        Args:
            on_progress: Optional callback(step: str, detail: str) for CLI progress updates.
        """
        report = self.report

        # Step 1: Analyze
        if on_progress:
            on_progress("analyze", "Scanning source files with AST parsers...")
        analyses = self.analyze_all()

        if not analyses:
            if on_progress:
                on_progress("done", "No test gaps found — all files have tests!")
            return report

        if on_progress:
            on_progress("gaps", f"Found {len(analyses)} files with test gaps")

        # Dry run — just report
        if self.dry_run:
            for a in analyses:
                report.results.append(GenerationResult(
                    source_file=a.file_path,
                    test_file=self._get_test_path(a),
                    tests_written=len(a.missing_tests),
                ))
            report.files_generated = len(analyses)
            if on_progress:
                on_progress("done", f"Dry run: {len(analyses)} files would get tests")
            return report

        # Step 2: Scan test patterns for style reference
        if on_progress:
            on_progress("style", "Learning project test patterns...")
        style_ref = self.scan_test_patterns()

        # Step 3: Generate tests for each file
        for i, analysis in enumerate(analyses):
            if on_progress:
                on_progress(
                    "generate",
                    f"[{i + 1}/{len(analyses)}] Generating tests for {analysis.file_path} "
                    f"({len(analysis.missing_tests)} missing, risk={analysis.risk})"
                )

            result = await self.generate_for_file(analysis, style_ref)
            report.results.append(result)

            if result.error:
                report.errors.append(f"{analysis.file_path}: {result.error}")
            else:
                report.files_generated += 1
                report.total_tests_written += result.tests_written
                report.total_tests_passed += result.tests_passed
                report.total_tests_failed += result.tests_failed

        if on_progress:
            on_progress("done", f"Generated {report.total_tests_written} tests in {report.files_generated} files")

        return report


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

# Alias so pytest doesn't try to collect it as a test class
TestGenerator = AITestGenerator


def format_gen_tests_report(report: GenTestsReport) -> str:
    """Format report for terminal display."""
    lines = []
    lines.append("  === AI TEST GENERATOR ===")
    lines.append(f"  Target: {report.target_path or 'entire repo'}")
    lines.append(f"  Files scanned: {report.files_analyzed}")
    lines.append(f"  Files with gaps: {report.files_with_gaps}")
    lines.append("")

    if report.results:
        lines.append("  Results:")
        risk_icons = {"critical": "[!!]", "high": "[!]", "medium": "[~]", "low": "[.]"}
        for r in report.results:
            status = "OK" if not r.error else "FAIL"
            icon = "+" if not r.error else "x"
            verify_info = ""
            if r.tests_passed or r.tests_failed:
                verify_info = f" | {r.tests_passed} passed, {r.tests_failed} failed"
                if r.retries:
                    verify_info += f" ({r.retries} retries)"
            lines.append(
                f"    [{icon}] {r.source_file} -> {r.test_file}"
                f" ({r.tests_written} tests){verify_info}"
            )
            if r.error:
                lines.append(f"        Error: {r.error}")

    lines.append("")
    lines.append(f"  Total: {report.total_tests_written} tests in {report.files_generated} files")
    if report.total_tests_passed or report.total_tests_failed:
        lines.append(f"  Verified: {report.total_tests_passed} passed, {report.total_tests_failed} failed")
    if report.errors:
        lines.append(f"  Errors: {len(report.errors)}")

    return "\n".join(lines)
