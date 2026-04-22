"""Auto-Coverage Boost — one-button test coverage improvement pipeline."""

import logging
import os
import re
import subprocess
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.tools.auto_coverage")


@dataclass
class CoverageGap:
    """A single uncovered code unit."""
    file: str
    name: str  # class or method name
    line_start: int = 0
    line_end: int = 0
    coverage_pct: float = 0.0
    risk: str = "medium"  # critical, high, medium, low
    complexity: int = 0  # rough LOC count


@dataclass
class CoverageReport:
    """Full coverage analysis report."""
    repo_path: str
    language: str = ""
    test_framework: str = ""
    test_command: str = ""

    # Baseline
    total_lines: int = 0
    covered_lines: int = 0
    coverage_pct: float = 0.0
    target_pct: float = 80.0

    # Existing tests
    test_file_count: int = 0
    test_method_count: int = 0

    # Gaps
    gaps: list[CoverageGap] = field(default_factory=list)
    prioritized_gaps: list[CoverageGap] = field(default_factory=list)

    # Results after boost
    new_tests_written: list[dict] = field(default_factory=list)  # file, test_count
    final_coverage_pct: float = 0.0
    improvement_pct: float = 0.0


class AutoCoverageBoost:
    """Orchestrates the auto-coverage improvement pipeline."""

    def __init__(self, cwd: str, target_pct: float = 80.0):
        self.cwd = cwd
        self.target_pct = target_pct
        self.report = CoverageReport(repo_path=cwd, target_pct=target_pct)
        self._detect_stack()

    def _detect_stack(self):
        """Detect language, test framework, test command."""
        r = self.report
        if os.path.exists(os.path.join(self.cwd, "pyproject.toml")) or os.path.exists(os.path.join(self.cwd, "setup.py")):
            r.language = "python"
            r.test_framework = "pytest"
            r.test_command = "pytest --cov --cov-report=json --cov-report=term -q"
        elif os.path.exists(os.path.join(self.cwd, "pom.xml")):
            r.language = "java"
            r.test_framework = "junit"
            r.test_command = "mvn test jacoco:report"
        elif os.path.exists(os.path.join(self.cwd, "build.gradle")) or os.path.exists(os.path.join(self.cwd, "build.gradle.kts")):
            r.language = "java"
            r.test_framework = "junit"
            r.test_command = "./gradlew test jacocoTestReport"
        elif os.path.exists(os.path.join(self.cwd, "package.json")):
            r.language = "javascript"
            r.test_framework = "jest"
            r.test_command = "npx jest --coverage --coverageReporters=json-summary"
        elif os.path.exists(os.path.join(self.cwd, "go.mod")):
            r.language = "go"
            r.test_framework = "go test"
            r.test_command = "go test -coverprofile=coverage.out ./..."

        # Override from env
        env_cmd = os.getenv("CODE_AGENTS_TEST_CMD", "")
        if env_cmd:
            r.test_command = env_cmd

        logger.info("Stack detected: %s / %s / %s", r.language, r.test_framework, r.test_command)

    # ------------------------------------------------------------------
    # Step 1: Scan existing tests
    # ------------------------------------------------------------------

    def scan_existing_tests(self) -> dict:
        """Count existing test files and methods."""
        r = self.report
        test_files = 0
        test_methods = 0

        skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "target", "build", "dist"}

        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                is_test = False
                filepath = os.path.join(root, f)

                if r.language == "python" and (f.startswith("test_") or f.endswith("_test.py")):
                    is_test = True
                elif r.language == "java" and f.endswith("Test.java"):
                    is_test = True
                elif r.language == "javascript" and (".test." in f or ".spec." in f):
                    is_test = True
                elif r.language == "go" and f.endswith("_test.go"):
                    is_test = True

                if is_test:
                    test_files += 1
                    try:
                        with open(filepath) as fp:
                            content = fp.read()
                        if r.language == "python":
                            test_methods += len(re.findall(r'def test_\w+', content))
                        elif r.language == "java":
                            test_methods += len(re.findall(r'@Test', content))
                        elif r.language == "javascript":
                            test_methods += len(re.findall(r'(?:it|test)\s*\(', content))
                        elif r.language == "go":
                            test_methods += len(re.findall(r'func Test\w+', content))
                    except Exception:
                        pass

        r.test_file_count = test_files
        r.test_method_count = test_methods
        return {"files": test_files, "methods": test_methods}

    # ------------------------------------------------------------------
    # Step 2: Run coverage baseline
    # ------------------------------------------------------------------

    def run_coverage_baseline(self) -> dict:
        """Run tests with coverage and parse the results."""
        r = self.report
        if not r.test_command:
            logger.warning("No test command detected")
            return {"coverage": 0}

        logger.info("Running coverage baseline: %s", r.test_command)
        try:
            result = subprocess.run(
                r.test_command, shell=True,
                capture_output=True, text=True, timeout=300, cwd=self.cwd,
            )
        except subprocess.TimeoutExpired:
            logger.error("Coverage baseline timed out (5 min)")
            return {"coverage": 0, "error": "timeout"}

        # Parse coverage based on language
        if r.language == "python":
            self._parse_python_coverage()
        elif r.language == "java":
            self._parse_jacoco_coverage()
        elif r.language == "javascript":
            self._parse_jest_coverage()
        elif r.language == "go":
            self._parse_go_coverage(result.stdout)

        return {"coverage": r.coverage_pct, "lines": r.total_lines, "covered": r.covered_lines}

    def _parse_python_coverage(self):
        """Parse pytest-cov JSON report."""
        json_path = os.path.join(self.cwd, "coverage.json")
        if not os.path.exists(json_path):
            # Try .coverage file with coverage json
            try:
                subprocess.run(["coverage", "json"], capture_output=True, timeout=30, cwd=self.cwd)
            except Exception:
                pass

        if os.path.exists(json_path):
            try:
                with open(json_path) as f:
                    data = json.load(f)
                totals = data.get("totals", {})
                self.report.coverage_pct = totals.get("percent_covered", 0)
                self.report.total_lines = totals.get("num_statements", 0)
                self.report.covered_lines = totals.get("covered_lines", 0)

                # Extract per-file gaps
                for filepath, file_data in data.get("files", {}).items():
                    missing = file_data.get("missing_lines", [])
                    if missing:
                        pct = file_data.get("summary", {}).get("percent_covered", 0)
                        self.report.gaps.append(CoverageGap(
                            file=filepath,
                            name=os.path.basename(filepath).replace(".py", ""),
                            coverage_pct=pct,
                            complexity=len(missing),
                        ))
            except Exception as e:
                logger.warning("Failed to parse coverage.json: %s", e)

    def _parse_jacoco_coverage(self):
        """Parse JaCoCo XML report."""
        # Look for jacoco report
        for candidate in [
            "target/site/jacoco/jacoco.xml",
            "build/reports/jacoco/test/jacocoTestReport.xml",
        ]:
            xml_path = os.path.join(self.cwd, candidate)
            if os.path.exists(xml_path):
                try:
                    import xml.etree.ElementTree as ET
                    tree = ET.parse(xml_path)
                    root = tree.getroot()
                    for counter in root.findall(".//counter[@type='LINE']"):
                        missed = int(counter.get("missed", 0))
                        covered = int(counter.get("covered", 0))
                        total = missed + covered
                        if total > 0:
                            self.report.total_lines += total
                            self.report.covered_lines += covered
                    if self.report.total_lines > 0:
                        self.report.coverage_pct = round(
                            self.report.covered_lines / self.report.total_lines * 100, 1
                        )
                except Exception as e:
                    logger.warning("Failed to parse JaCoCo XML: %s", e)
                break

    def _parse_jest_coverage(self):
        """Parse Jest coverage JSON summary."""
        json_path = os.path.join(self.cwd, "coverage", "coverage-summary.json")
        if os.path.exists(json_path):
            try:
                with open(json_path) as f:
                    data = json.load(f)
                total = data.get("total", {}).get("lines", {})
                self.report.coverage_pct = total.get("pct", 0)
                self.report.total_lines = total.get("total", 0)
                self.report.covered_lines = total.get("covered", 0)

                for filepath, file_data in data.items():
                    if filepath == "total":
                        continue
                    pct = file_data.get("lines", {}).get("pct", 100)
                    if pct < self.target_pct:
                        self.report.gaps.append(CoverageGap(
                            file=filepath,
                            name=os.path.basename(filepath),
                            coverage_pct=pct,
                        ))
            except Exception as e:
                logger.warning("Failed to parse jest coverage: %s", e)

    def _parse_go_coverage(self, stdout: str):
        """Parse go test -cover output."""
        # Look for: coverage: 62.4% of statements
        match = re.search(r'coverage:\s+([\d.]+)%', stdout)
        if match:
            self.report.coverage_pct = float(match.group(1))

    # ------------------------------------------------------------------
    # Step 3: Identify and prioritize gaps
    # ------------------------------------------------------------------

    def identify_gaps(self) -> list[CoverageGap]:
        """Identify uncovered code units."""
        # If coverage parser already found gaps, use those
        if not self.report.gaps:
            self._find_uncovered_files()

        return self.report.gaps

    def _find_uncovered_files(self):
        """Fallback: find source files with no corresponding test file."""
        r = self.report
        skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "target", "build", "dist", "test", "tests"}

        test_names = set()
        # Walk ALL dirs (including test/tests) to collect test file names
        skip_dirs_for_tests = {".git", "node_modules", "__pycache__", "venv", ".venv", "target", "build", "dist"}
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in skip_dirs_for_tests]
            for f in files:
                if r.language == "python" and f.startswith("test_"):
                    test_names.add(f.replace("test_", "").replace(".py", ""))
                elif r.language == "java" and f.endswith("Test.java"):
                    test_names.add(f.replace("Test.java", ""))

        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                name = None
                if r.language == "python" and f.endswith(".py") and not f.startswith("test_") and not f.startswith("__"):
                    name = f.replace(".py", "")
                elif r.language == "java" and f.endswith(".java") and not f.endswith("Test.java"):
                    name = f.replace(".java", "")

                if name and name not in test_names:
                    rel = os.path.relpath(os.path.join(root, f), self.cwd)
                    self.report.gaps.append(CoverageGap(
                        file=rel, name=name, coverage_pct=0,
                        risk="high",
                    ))

    def prioritize_gaps(self) -> list[CoverageGap]:
        """Prioritize gaps by risk and complexity."""
        r = self.report

        # Assign risk based on file path patterns
        critical_patterns = ["payment", "transaction", "auth", "security", "billing", "order"]
        high_patterns = ["service", "controller", "handler", "processor", "api"]

        for gap in r.gaps:
            name_lower = (gap.file + gap.name).lower()
            if any(p in name_lower for p in critical_patterns):
                gap.risk = "critical"
            elif any(p in name_lower for p in high_patterns):
                gap.risk = "high"
            elif gap.coverage_pct == 0:
                gap.risk = "high"
            elif gap.coverage_pct < 30:
                gap.risk = "medium"
            else:
                gap.risk = "low"

        # Sort: critical first, then high, then by coverage (lowest first)
        risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        r.prioritized_gaps = sorted(
            r.gaps,
            key=lambda g: (risk_order.get(g.risk, 99), g.coverage_pct),
        )

        return r.prioritized_gaps

    # ------------------------------------------------------------------
    # Step 4: Build test generation prompts
    # ------------------------------------------------------------------

    def build_test_prompts(self, max_files: int = 10) -> list[dict]:
        """Build prompts for code-tester agent to write tests."""
        prompts = []
        gaps = self.report.prioritized_gaps[:max_files]

        for gap in gaps:
            source_path = os.path.join(self.cwd, gap.file)
            if not os.path.exists(source_path):
                continue

            try:
                with open(source_path) as f:
                    source = f.read()
            except Exception:
                continue

            # Determine test file path
            r = self.report
            if r.language == "python":
                test_path = f"tests/test_{os.path.basename(gap.file)}"
            elif r.language == "java":
                test_path = gap.file.replace("src/main/java", "src/test/java").replace(".java", "Test.java")
            elif r.language in ("javascript", "typescript"):
                base = os.path.splitext(gap.file)
                test_path = f"{base[0]}.test{base[1]}"
            elif r.language == "go":
                test_path = gap.file.replace(".go", "_test.go")
            else:
                test_path = f"tests/test_{os.path.basename(gap.file)}"

            prompt = {
                "source_file": gap.file,
                "test_file": test_path,
                "source_code": source[:5000],  # limit for token budget
                "language": r.language,
                "framework": r.test_framework,
                "gap_name": gap.name,
                "current_coverage": gap.coverage_pct,
                "risk": gap.risk,
            }
            prompts.append(prompt)

        return prompts

    def build_delegation_prompt(self, prompts: list[dict]) -> str:
        """Build a single prompt for delegating to code-tester."""
        parts = []
        parts.append("AUTO-COVERAGE BOOST: Write tests for the following uncovered files.")
        parts.append(f"Language: {self.report.language} | Framework: {self.report.test_framework}")
        parts.append(f"Current coverage: {self.report.coverage_pct}% | Target: {self.target_pct}%")
        parts.append("")

        for i, p in enumerate(prompts, 1):
            parts.append(f"--- FILE {i}: {p['source_file']} (coverage: {p['current_coverage']}%, risk: {p['risk']}) ---")
            parts.append(f"Test file: {p['test_file']}")
            parts.append(f"```{p['language']}")
            parts.append(p['source_code'][:3000])
            parts.append("```")
            parts.append("")

        parts.append("INSTRUCTIONS:")
        parts.append("1. Write comprehensive tests for each file above")
        parts.append("2. Include happy path, edge cases, error cases, boundary values")
        parts.append("3. Mock external dependencies (network, DB, filesystem)")
        parts.append(f"4. Use {self.report.test_framework} conventions")
        parts.append("5. Output each test file with its full path")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Step 5: Git operations (add, commit, branch — NOT push)
    # ------------------------------------------------------------------

    def git_create_branch(self, branch_name: str = "") -> bool:
        """Create a coverage improvement branch."""
        if not branch_name:
            from datetime import datetime
            branch_name = f"coverage/auto-boost-{datetime.now().strftime('%Y%m%d-%H%M')}"

        try:
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                capture_output=True, text=True, timeout=15, cwd=self.cwd,
            )
            if result.returncode == 0:
                logger.info("Created branch: %s", branch_name)
                return True
            logger.error("Failed to create branch: %s", result.stderr)
            return False
        except Exception as e:
            logger.error("Git branch error: %s", e)
            return False

    def git_add_and_commit(self, files: list[str], message: str = "") -> bool:
        """Stage files and commit."""
        if not files:
            return False

        if not message:
            message = f"test: auto-coverage boost -- {len(files)} test files added"

        try:
            # git add specific files
            result = subprocess.run(
                ["git", "add"] + files,
                capture_output=True, text=True, timeout=15, cwd=self.cwd,
            )
            if result.returncode != 0:
                logger.error("Git add failed: %s", result.stderr)
                return False

            # git commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True, text=True, timeout=30, cwd=self.cwd,
            )
            if result.returncode == 0:
                logger.info("Committed: %s", message)
                return True
            logger.error("Git commit failed: %s", result.stderr)
            return False
        except Exception as e:
            logger.error("Git commit error: %s", e)
            return False

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def run_pipeline(self, dry_run: bool = False) -> CoverageReport:
        """Run the full auto-coverage pipeline."""
        logger.info("Starting auto-coverage pipeline for %s", self.cwd)

        # Step 1: Scan
        self.scan_existing_tests()

        # Step 2: Baseline (skip in dry-run)
        if not dry_run:
            self.run_coverage_baseline()

        # Step 3: Identify gaps
        self.identify_gaps()

        # Step 4: Prioritize
        self.prioritize_gaps()

        # Step 5: Build prompts (actual test writing is done by the agent)
        prompts = self.build_test_prompts()

        logger.info(
            "Pipeline ready: %d existing tests, %.1f%% coverage, %d gaps, %d to fix",
            self.report.test_method_count,
            self.report.coverage_pct,
            len(self.report.gaps),
            len(prompts),
        )

        return self.report


def format_coverage_report(report: CoverageReport) -> str:
    """Format for terminal display."""
    lines = []
    lines.append("  === AUTO-COVERAGE BOOST ===")
    lines.append(f"  Repo: {os.path.basename(report.repo_path)}")
    lines.append(f"  Stack: {report.language} / {report.test_framework}")

    lines.append(f"\n  Existing Tests:")
    lines.append(f"    Files: {report.test_file_count} | Methods: {report.test_method_count}")

    lines.append(f"\n  Coverage Baseline:")
    bar_len = 30
    filled = int(report.coverage_pct / 100 * bar_len)
    bar = "#" * filled + "." * (bar_len - filled)
    lines.append(f"    [{bar}] {report.coverage_pct}% (target: {report.target_pct}%)")
    if report.total_lines > 0:
        lines.append(f"    {report.covered_lines}/{report.total_lines} lines covered")

    gap_pct = report.target_pct - report.coverage_pct
    if gap_pct > 0:
        lines.append(f"    Gap: {gap_pct:.1f}% to target")
    else:
        lines.append(f"    Target met!")

    if report.prioritized_gaps:
        lines.append(f"\n  Priority Gaps ({len(report.prioritized_gaps)}):")
        risk_icons = {"critical": "[!!]", "high": "[!]", "medium": "[~]", "low": "[.]"}
        for gap in report.prioritized_gaps[:15]:
            icon = risk_icons.get(gap.risk, "  ")
            cov = f"{gap.coverage_pct:.0f}%" if gap.coverage_pct > 0 else "0%"
            lines.append(f"    {icon} {gap.name} ({gap.file}) -- {cov} covered [{gap.risk}]")
        if len(report.prioritized_gaps) > 15:
            lines.append(f"    ... and {len(report.prioritized_gaps) - 15} more")

    if report.new_tests_written:
        lines.append(f"\n  Tests Written:")
        for t in report.new_tests_written:
            lines.append(f"    + {t['file']} -- {t.get('test_count', '?')} tests")

    if report.final_coverage_pct > 0:
        lines.append(f"\n  Final Coverage:")
        filled2 = int(report.final_coverage_pct / 100 * bar_len)
        bar2 = "#" * filled2 + "." * (bar_len - filled2)
        lines.append(f"    [{bar2}] {report.final_coverage_pct}% (+{report.improvement_pct:.1f}%)")

    return "\n".join(lines)
