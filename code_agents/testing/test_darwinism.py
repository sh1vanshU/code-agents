"""Test Darwinism — score tests by bug-catching ability, prune redundant tests."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.testing.test_darwinism")


@dataclass
class TestCase:
    """A single test case with fitness metrics."""
    name: str = ""
    file_path: str = ""
    line_number: int = 0
    bugs_caught: int = 0
    mutation_kills: int = 0
    execution_time_ms: float = 0.0
    code_covered: set = field(default_factory=set)
    last_failed: str = ""
    fitness_score: float = 0.0
    is_redundant: bool = False
    redundant_with: str = ""


@dataclass
class TestSuite:
    """A collection of test cases with population metrics."""
    tests: list[TestCase] = field(default_factory=list)
    total_tests: int = 0
    redundant_count: int = 0
    essential_count: int = 0
    avg_fitness: float = 0.0
    total_coverage: float = 0.0
    time_savings_ms: float = 0.0


@dataclass
class DarwinismReport:
    """Complete test darwinism analysis."""
    suite: TestSuite = field(default_factory=TestSuite)
    ranked_tests: list[TestCase] = field(default_factory=list)
    redundant_tests: list[TestCase] = field(default_factory=list)
    essential_tests: list[TestCase] = field(default_factory=list)
    prune_suggestions: list[str] = field(default_factory=list)
    breed_suggestions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


ASSERT_PATTERN = re.compile(r"(?:assert|self\.assert\w+|pytest\.\w+)\s*\(", re.MULTILINE)
TEST_FUNC_PATTERN = re.compile(r"^\s*def\s+(test_\w+)\s*\(", re.MULTILINE)


class TestDarwinism:
    """Applies evolutionary fitness to test suites."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, test_files: dict[str, str],
                coverage_data: Optional[dict] = None,
                bug_history: Optional[dict] = None,
                execution_times: Optional[dict] = None) -> DarwinismReport:
        """Analyze test suite fitness and identify redundancies."""
        logger.info("Analyzing %d test files", len(test_files))

        coverage_data = coverage_data or {}
        bug_history = bug_history or {}
        execution_times = execution_times or {}

        # Phase 1: Extract test cases
        tests = []
        for fpath, content in test_files.items():
            tests.extend(self._extract_tests(fpath, content))
        logger.info("Found %d test cases", len(tests))

        # Phase 2: Score fitness
        for test in tests:
            test.bugs_caught = bug_history.get(test.name, 0)
            test.execution_time_ms = execution_times.get(test.name, 100.0)
            test.code_covered = set(coverage_data.get(test.name, []))
            test.fitness_score = self._compute_fitness(test)

        # Phase 3: Find redundancies
        self._find_redundancies(tests)

        # Phase 4: Build report
        tests.sort(key=lambda t: -t.fitness_score)
        redundant = [t for t in tests if t.is_redundant]
        essential = [t for t in tests if not t.is_redundant]

        suite = TestSuite(
            tests=tests,
            total_tests=len(tests),
            redundant_count=len(redundant),
            essential_count=len(essential),
            avg_fitness=sum(t.fitness_score for t in tests) / len(tests) if tests else 0,
            time_savings_ms=sum(t.execution_time_ms for t in redundant),
        )

        report = DarwinismReport(
            suite=suite,
            ranked_tests=tests,
            redundant_tests=redundant,
            essential_tests=essential,
            prune_suggestions=self._prune_suggestions(redundant),
            breed_suggestions=self._breed_suggestions(tests, coverage_data),
            warnings=self._generate_warnings(tests, redundant),
        )
        logger.info("Darwinism: %d essential, %d redundant, avg fitness %.2f",
                     len(essential), len(redundant), suite.avg_fitness)
        return report

    def _extract_tests(self, fpath: str, content: str) -> list[TestCase]:
        """Extract test cases from a file."""
        tests = []
        for m in TEST_FUNC_PATTERN.finditer(content):
            name = m.group(1)
            line_num = content[:m.start()].count("\n") + 1
            tests.append(TestCase(
                name=name,
                file_path=fpath,
                line_number=line_num,
            ))
        return tests

    def _compute_fitness(self, test: TestCase) -> float:
        """Compute fitness score for a test."""
        score = 0.0
        # Bug-catching ability (most important)
        score += min(40, test.bugs_caught * 10)
        # Coverage breadth
        score += min(30, len(test.code_covered) * 0.5)
        # Mutation kills
        score += min(20, test.mutation_kills * 5)
        # Speed bonus (faster = better)
        if test.execution_time_ms < 100:
            score += 10
        elif test.execution_time_ms < 500:
            score += 5
        return round(min(100, score), 1)

    def _find_redundancies(self, tests: list[TestCase]):
        """Find tests that are redundant (same coverage set)."""
        coverage_groups: dict[str, list[TestCase]] = {}
        for test in tests:
            key = str(sorted(test.code_covered)) if test.code_covered else f"_empty_{test.name}"
            coverage_groups.setdefault(key, []).append(test)

        for key, group in coverage_groups.items():
            if len(group) > 1 and key != f"_empty_{group[0].name}":
                # Keep the one with highest fitness
                group.sort(key=lambda t: -t.fitness_score)
                for t in group[1:]:
                    t.is_redundant = True
                    t.redundant_with = group[0].name

    def _prune_suggestions(self, redundant: list[TestCase]) -> list[str]:
        """Generate prune suggestions."""
        suggestions = []
        for t in redundant[:10]:
            suggestions.append(
                f"Remove {t.name} (redundant with {t.redundant_with}, saves {t.execution_time_ms:.0f}ms)"
            )
        return suggestions

    def _breed_suggestions(self, tests: list[TestCase], coverage: dict) -> list[str]:
        """Suggest new tests to breed (coverage gaps)."""
        all_covered = set()
        for t in tests:
            all_covered |= t.code_covered

        suggestions = []
        # If we have coverage data, find gaps
        if coverage:
            all_lines = set()
            for lines in coverage.values():
                all_lines |= set(lines)
            uncovered = all_lines - all_covered
            if uncovered:
                suggestions.append(f"Create tests covering {len(uncovered)} uncovered lines")

        # Suggest mutation-resistant tests
        low_mutation = [t for t in tests if t.mutation_kills == 0 and t.fitness_score > 0]
        if low_mutation:
            suggestions.append(
                f"Strengthen {len(low_mutation)} tests with mutation-resistant assertions"
            )
        return suggestions

    def _generate_warnings(self, tests: list[TestCase],
                           redundant: list[TestCase]) -> list[str]:
        """Generate warnings."""
        warnings = []
        if len(redundant) > len(tests) * 0.3:
            warnings.append(f"Over 30% of tests are redundant ({len(redundant)}/{len(tests)})")
        zero_fitness = [t for t in tests if t.fitness_score == 0]
        if zero_fitness:
            warnings.append(f"{len(zero_fitness)} tests have zero fitness — review value")
        return warnings


def format_report(report: DarwinismReport) -> str:
    """Format darwinism report."""
    lines = [
        "# Test Darwinism Report",
        f"Tests: {report.suite.total_tests} | Essential: {report.suite.essential_count} | Redundant: {report.suite.redundant_count}",
        f"Avg Fitness: {report.suite.avg_fitness:.1f} | Time Savings: {report.suite.time_savings_ms:.0f}ms",
        "",
    ]
    if report.prune_suggestions:
        lines.append("## Prune")
        for s in report.prune_suggestions:
            lines.append(f"  - {s}")
    if report.breed_suggestions:
        lines.append("\n## Breed")
        for s in report.breed_suggestions:
            lines.append(f"  + {s}")
    return "\n".join(lines)
