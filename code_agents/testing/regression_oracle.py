"""Regression oracle — predict which features will break from a code change.

Goes beyond test coverage to analyze code dependencies, call graphs, and
change blast radius to predict regression risk areas.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.testing.regression_oracle")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}


@dataclass
class RegressionRisk:
    """A predicted regression risk."""

    feature: str = ""
    file: str = ""
    risk_score: float = 0.0  # 0-100
    risk_level: str = "low"  # low | medium | high | critical
    reason: str = ""
    affected_tests: list[str] = field(default_factory=list)
    mitigation: str = ""


@dataclass
class ChangeAnalysis:
    """Analysis of a code change."""

    changed_files: list[str] = field(default_factory=list)
    changed_functions: list[str] = field(default_factory=list)
    changed_classes: list[str] = field(default_factory=list)
    import_chain: list[str] = field(default_factory=list)
    blast_radius: int = 0


@dataclass
class RegressionOracleResult:
    """Result of regression prediction."""

    risks: list[RegressionRisk] = field(default_factory=list)
    change_analysis: ChangeAnalysis = field(default_factory=ChangeAnalysis)
    safe_to_deploy: bool = True
    confidence: float = 0.0
    recommended_tests: list[str] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)


class RegressionOracle:
    """Predict regression risks from code changes."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._dep_graph: dict[str, set[str]] | None = None
        self._reverse_deps: dict[str, set[str]] | None = None
        logger.debug("RegressionOracle initialized for %s", cwd)

    def predict(
        self,
        changed_files: list[str] | None = None,
        diff_content: str | None = None,
    ) -> RegressionOracleResult:
        """Predict regression risks from code changes.

        Args:
            changed_files: List of changed file paths (relative).
            diff_content: Raw diff content to parse.

        Returns:
            RegressionOracleResult with risks and recommendations.
        """
        result = RegressionOracleResult()

        if changed_files is None and diff_content:
            changed_files = self._extract_files_from_diff(diff_content)
        if not changed_files:
            logger.warning("No changed files to analyze")
            return result

        logger.info("Predicting regressions for %d changed files", len(changed_files))

        # Build dependency graph
        if self._dep_graph is None:
            self._build_dep_graph()

        # Analyze the change
        result.change_analysis = self._analyze_change(changed_files)

        # Find impacted modules
        impacted = self._find_impacted_modules(changed_files)

        # Predict risks
        for module in impacted:
            risk = self._assess_module_risk(module, changed_files)
            if risk.risk_score > 10:
                result.risks.append(risk)

        # Sort by risk
        result.risks.sort(key=lambda r: r.risk_score, reverse=True)

        # Determine safety
        critical = sum(1 for r in result.risks if r.risk_level == "critical")
        high = sum(1 for r in result.risks if r.risk_level == "high")
        result.safe_to_deploy = critical == 0 and high <= 1

        # Confidence based on graph coverage
        total_files = len(self._dep_graph or {})
        if total_files > 0:
            result.confidence = min(0.95, 0.5 + len(impacted) / total_files)

        # Recommend tests
        result.recommended_tests = self._recommend_tests(result.risks, changed_files)

        result.summary = {
            "changed_files": len(changed_files),
            "impacted_modules": len(impacted),
            "total_risks": len(result.risks),
            "critical_risks": critical,
            "high_risks": high,
            "safe_to_deploy": int(result.safe_to_deploy),
        }
        logger.info(
            "Regression prediction: %d risks, safe=%s",
            len(result.risks), result.safe_to_deploy,
        )
        return result

    def _build_dep_graph(self) -> None:
        """Build module dependency graph."""
        self._dep_graph = defaultdict(set)
        self._reverse_deps = defaultdict(set)

        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                if not fname.endswith(".py") or fname.startswith("test_"):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, self.cwd)

                try:
                    content = Path(fpath).read_text(errors="replace")
                    tree = ast.parse(content)
                except (OSError, SyntaxError):
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        self._dep_graph[rel].add(node.module)
                        # Reverse: module -> files that import it
                        self._reverse_deps[node.module].add(rel)
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            self._dep_graph[rel].add(alias.name)
                            self._reverse_deps[alias.name].add(rel)

    def _extract_files_from_diff(self, diff: str) -> list[str]:
        """Extract file paths from diff content."""
        files: list[str] = []
        for match in re.finditer(r"^(?:diff --git a/|---|\+\+\+) (?:a/|b/)?(\S+)", diff, re.MULTILINE):
            fpath = match.group(1)
            if fpath not in files and not fpath.startswith("/dev/null"):
                files.append(fpath)
        return files

    def _analyze_change(self, changed_files: list[str]) -> ChangeAnalysis:
        """Analyze what changed in the modified files."""
        analysis = ChangeAnalysis(changed_files=changed_files)

        for rel in changed_files:
            fpath = os.path.join(self.cwd, rel)
            try:
                content = Path(fpath).read_text(errors="replace")
                tree = ast.parse(content)
            except (OSError, SyntaxError):
                continue

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    analysis.changed_functions.append(f"{rel}:{node.name}")
                elif isinstance(node, ast.ClassDef):
                    analysis.changed_classes.append(f"{rel}:{node.name}")

        # Import chain
        for rel in changed_files:
            deps = self._dep_graph.get(rel, set()) if self._dep_graph else set()
            analysis.import_chain.extend(deps)

        analysis.blast_radius = len(self._find_impacted_modules(changed_files))
        return analysis

    def _find_impacted_modules(self, changed_files: list[str]) -> list[str]:
        """Find all modules transitively impacted by changes."""
        if not self._reverse_deps:
            return changed_files

        visited: set[str] = set()
        queue = list(changed_files)

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            # Find modules that depend on current
            module_name = current.replace("/", ".").replace(".py", "")
            for dependent in self._reverse_deps.get(module_name, set()):
                if dependent not in visited:
                    queue.append(dependent)

            # Also check partial module matches
            parts = module_name.split(".")
            for i in range(len(parts)):
                partial = ".".join(parts[:i + 1])
                for dependent in self._reverse_deps.get(partial, set()):
                    if dependent not in visited:
                        queue.append(dependent)

        return list(visited)

    def _assess_module_risk(
        self, module: str, changed_files: list[str],
    ) -> RegressionRisk:
        """Assess regression risk for a specific module."""
        risk = RegressionRisk(file=module)

        # Base score: how far from the change
        if module in changed_files:
            risk.risk_score = 80.0
            risk.reason = "Directly modified file"
        else:
            # Distance heuristic
            risk.risk_score = 40.0
            risk.reason = "Transitively depends on changed module"

        # Boost for critical files
        if any(kw in module for kw in ("auth", "payment", "security", "config")):
            risk.risk_score += 20
            risk.reason += " (critical module)"

        # Boost for files with many dependents
        module_name = module.replace("/", ".").replace(".py", "")
        dependents = self._reverse_deps.get(module_name, set()) if self._reverse_deps else set()
        if len(dependents) > 5:
            risk.risk_score += 10
            risk.reason += f" ({len(dependents)} dependents)"

        risk.risk_score = min(100, risk.risk_score)

        # Classify
        if risk.risk_score >= 80:
            risk.risk_level = "critical"
        elif risk.risk_score >= 60:
            risk.risk_level = "high"
        elif risk.risk_score >= 30:
            risk.risk_level = "medium"
        else:
            risk.risk_level = "low"

        # Feature name from path
        parts = module.replace(".py", "").split("/")
        risk.feature = parts[-1] if parts else module

        # Suggest test file
        stem = Path(module).stem
        risk.affected_tests = [f"tests/test_{stem}.py"]
        risk.mitigation = f"Run test_{stem}.py and verify {risk.feature} behavior"

        return risk

    def _recommend_tests(
        self, risks: list[RegressionRisk], changed_files: list[str],
    ) -> list[str]:
        """Recommend tests to run based on risks."""
        tests: list[str] = []

        # Tests for changed files
        for f in changed_files:
            stem = Path(f).stem
            tests.append(f"tests/test_{stem}.py")

        # Tests for high-risk modules
        for risk in risks:
            if risk.risk_level in ("high", "critical"):
                tests.extend(risk.affected_tests)

        return list(dict.fromkeys(tests))[:20]  # Dedupe, limit


def predict_regressions(
    cwd: str,
    changed_files: list[str] | None = None,
    diff_content: str | None = None,
) -> dict:
    """Convenience function to predict regressions.

    Returns:
        Dict with risks, safety assessment, and recommended tests.
    """
    oracle = RegressionOracle(cwd)
    result = oracle.predict(changed_files=changed_files, diff_content=diff_content)
    return {
        "safe_to_deploy": result.safe_to_deploy,
        "risks": [
            {"feature": r.feature, "file": r.file, "risk_score": r.risk_score,
             "risk_level": r.risk_level, "reason": r.reason, "mitigation": r.mitigation}
            for r in result.risks
        ],
        "recommended_tests": result.recommended_tests,
        "change_analysis": {
            "changed_files": result.change_analysis.changed_files,
            "blast_radius": result.change_analysis.blast_radius,
        },
        "confidence": result.confidence,
        "summary": result.summary,
    }
