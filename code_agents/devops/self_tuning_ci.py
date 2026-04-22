"""Self-Tuning CI — optimize CI pipeline by reordering tests and skipping irrelevant ones."""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.devops.self_tuning_ci")


@dataclass
class TestInfo:
    """Information about a test for scheduling."""
    name: str = ""
    file_path: str = ""
    avg_duration_ms: float = 0.0
    failure_rate: float = 0.0
    last_failure: str = ""
    dependencies: list[str] = field(default_factory=list)  # source files tested
    flaky: bool = False
    priority: float = 0.0  # computed priority


@dataclass
class PipelineStage:
    """A CI pipeline stage with its tests."""
    name: str = ""
    tests: list[TestInfo] = field(default_factory=list)
    estimated_duration_ms: float = 0.0
    parallelizable: bool = True


@dataclass
class OptimizationPlan:
    """An optimized CI pipeline plan."""
    stages: list[PipelineStage] = field(default_factory=list)
    original_duration_ms: float = 0.0
    optimized_duration_ms: float = 0.0
    tests_skipped: list[str] = field(default_factory=list)
    tests_reordered: bool = False
    savings_pct: float = 0.0


@dataclass
class CITuningReport:
    """Complete CI tuning report."""
    plan: OptimizationPlan = field(default_factory=OptimizationPlan)
    total_tests: int = 0
    relevant_tests: int = 0
    skipped_tests: int = 0
    flaky_tests: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SelfTuningCI:
    """Optimizes CI pipelines based on change context."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, changed_files: list[str],
                test_catalog: list[dict],
                history: Optional[list[dict]] = None) -> CITuningReport:
        """Analyze changes and optimize test execution plan."""
        logger.info("Tuning CI for %d changed files, %d tests", len(changed_files), len(test_catalog))
        history = history or []

        # Phase 1: Parse test catalog
        tests = [self._parse_test(t) for t in test_catalog]

        # Phase 2: Enrich with history
        self._enrich_with_history(tests, history)

        # Phase 3: Compute relevance and priority
        relevant = self._filter_relevant(tests, changed_files)
        for test in relevant:
            test.priority = self._compute_priority(test, changed_files)

        # Phase 4: Detect flaky tests
        flaky = [t for t in tests if t.flaky]

        # Phase 5: Build optimized plan
        plan = self._build_plan(relevant, tests)

        report = CITuningReport(
            plan=plan,
            total_tests=len(tests),
            relevant_tests=len(relevant),
            skipped_tests=len(tests) - len(relevant),
            flaky_tests=[t.name for t in flaky],
            recommendations=self._generate_recommendations(plan, flaky),
            warnings=self._generate_warnings(tests, relevant),
        )
        logger.info("CI tuning: %d/%d tests relevant, %.0f%% savings",
                     len(relevant), len(tests), plan.savings_pct)
        return report

    def _parse_test(self, raw: dict) -> TestInfo:
        """Parse raw test info."""
        return TestInfo(
            name=raw.get("name", ""),
            file_path=raw.get("file", raw.get("file_path", "")),
            avg_duration_ms=float(raw.get("avg_duration_ms", raw.get("duration", 100))),
            failure_rate=float(raw.get("failure_rate", 0)),
            dependencies=raw.get("dependencies", raw.get("tests_files", [])),
        )

    def _enrich_with_history(self, tests: list[TestInfo], history: list[dict]):
        """Enrich tests with historical data."""
        failure_counts: dict[str, int] = {}
        run_counts: dict[str, int] = {}
        for run in history:
            name = run.get("test", "")
            run_counts[name] = run_counts.get(name, 0) + 1
            if run.get("failed"):
                failure_counts[name] = failure_counts.get(name, 0) + 1

        for test in tests:
            runs = run_counts.get(test.name, 0)
            fails = failure_counts.get(test.name, 0)
            if runs > 0:
                test.failure_rate = fails / runs
                # Flaky if fails inconsistently
                test.flaky = 0.1 < test.failure_rate < 0.5

    def _filter_relevant(self, tests: list[TestInfo], changed: list[str]) -> list[TestInfo]:
        """Filter tests relevant to changed files."""
        changed_set = set(changed)
        relevant = []
        for test in tests:
            # Test is relevant if it tests any changed file
            dep_set = set(test.dependencies)
            if dep_set & changed_set:
                relevant.append(test)
            elif self._infer_relevance(test, changed):
                relevant.append(test)
        return relevant

    def _infer_relevance(self, test: TestInfo, changed: list[str]) -> bool:
        """Infer test relevance from naming patterns."""
        test_name = test.name.lower().replace("test_", "")
        for fpath in changed:
            module = fpath.split("/")[-1].replace(".py", "").lower()
            if module in test_name or test_name in module:
                return True
        return False

    def _compute_priority(self, test: TestInfo, changed: list[str]) -> float:
        """Compute execution priority (higher = run first)."""
        priority = 0.0
        # High failure rate = run first (fast feedback)
        priority += test.failure_rate * 40
        # Direct dependency = higher priority
        dep_overlap = len(set(test.dependencies) & set(changed))
        priority += dep_overlap * 20
        # Faster tests first
        if test.avg_duration_ms < 100:
            priority += 15
        elif test.avg_duration_ms < 500:
            priority += 10
        # Flaky tests lower priority
        if test.flaky:
            priority -= 10
        return round(priority, 1)

    def _build_plan(self, relevant: list[TestInfo],
                    all_tests: list[TestInfo]) -> OptimizationPlan:
        """Build optimized execution plan."""
        relevant.sort(key=lambda t: -t.priority)

        # Split into stages: fast (< 500ms), medium, slow
        fast = [t for t in relevant if t.avg_duration_ms < 500]
        medium = [t for t in relevant if 500 <= t.avg_duration_ms < 5000]
        slow = [t for t in relevant if t.avg_duration_ms >= 5000]

        stages = []
        if fast:
            stages.append(PipelineStage(
                name="fast_feedback", tests=fast,
                estimated_duration_ms=max(t.avg_duration_ms for t in fast),
            ))
        if medium:
            stages.append(PipelineStage(
                name="core_tests", tests=medium,
                estimated_duration_ms=max(t.avg_duration_ms for t in medium),
            ))
        if slow:
            stages.append(PipelineStage(
                name="integration", tests=slow,
                estimated_duration_ms=sum(t.avg_duration_ms for t in slow),
                parallelizable=False,
            ))

        original = sum(t.avg_duration_ms for t in all_tests)
        optimized = sum(s.estimated_duration_ms for s in stages)
        skipped = [t.name for t in all_tests if t not in relevant]

        return OptimizationPlan(
            stages=stages,
            original_duration_ms=original,
            optimized_duration_ms=optimized,
            tests_skipped=skipped,
            tests_reordered=True,
            savings_pct=((original - optimized) / original * 100) if original else 0,
        )

    def _generate_recommendations(self, plan: OptimizationPlan,
                                  flaky: list[TestInfo]) -> list[str]:
        """Generate recommendations."""
        recs = []
        if plan.savings_pct > 30:
            recs.append(f"Significant savings possible ({plan.savings_pct:.0f}%) by running only relevant tests")
        if flaky:
            recs.append(f"Quarantine {len(flaky)} flaky tests to separate pipeline stage")
        if plan.tests_skipped:
            recs.append(f"Skip {len(plan.tests_skipped)} irrelevant tests for this change")
        return recs

    def _generate_warnings(self, all_tests: list[TestInfo],
                           relevant: list[TestInfo]) -> list[str]:
        """Generate warnings."""
        warnings = []
        if not relevant:
            warnings.append("No tests mapped to changed files — run full suite as fallback")
        no_deps = [t for t in all_tests if not t.dependencies]
        if len(no_deps) > len(all_tests) * 0.5:
            warnings.append(f"{len(no_deps)} tests lack dependency mapping — CI tuning accuracy reduced")
        return warnings


def format_report(report: CITuningReport) -> str:
    """Format CI tuning report."""
    lines = [
        "# CI Tuning Report",
        f"Tests: {report.total_tests} total, {report.relevant_tests} relevant, {report.skipped_tests} skipped",
        f"Savings: {report.plan.savings_pct:.0f}%",
        "",
    ]
    for stage in report.plan.stages:
        lines.append(f"## Stage: {stage.name} ({len(stage.tests)} tests, {stage.estimated_duration_ms:.0f}ms)")
    for r in report.recommendations:
        lines.append(f"  * {r}")
    return "\n".join(lines)
