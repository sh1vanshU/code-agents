"""Swarm Debugger — coordinate multiple debug hypotheses in parallel."""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.swarm_debugger")


@dataclass
class Hypothesis:
    """A debug hypothesis to investigate."""
    id: str = ""
    description: str = ""
    category: str = ""  # logic, data, concurrency, config, dependency, env
    confidence: float = 0.5
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    investigation_steps: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, investigating, confirmed, rejected
    root_cause: bool = False


@dataclass
class DebugFinding:
    """A finding from investigating a hypothesis."""
    hypothesis_id: str = ""
    finding: str = ""
    evidence_type: str = "observation"  # observation, reproduction, trace, log
    supports_hypothesis: bool = True
    file_path: str = ""
    line_number: int = 0
    details: str = ""


@dataclass
class SwarmReport:
    """Complete swarm debugging report."""
    bug_description: str = ""
    hypotheses: list[Hypothesis] = field(default_factory=list)
    findings: list[DebugFinding] = field(default_factory=list)
    root_cause: Optional[Hypothesis] = None
    suggested_fix: str = ""
    investigation_summary: str = ""
    confidence: float = 0.0
    duration_ms: float = 0.0


CATEGORY_HEURISTICS = {
    "logic": ["if", "else", "return", "condition", "wrong", "incorrect", "unexpected"],
    "data": ["null", "none", "empty", "missing", "corrupt", "invalid", "format"],
    "concurrency": ["race", "deadlock", "timeout", "concurrent", "thread", "async", "lock"],
    "config": ["config", "setting", "environment", "variable", "flag", "parameter"],
    "dependency": ["import", "version", "library", "package", "module", "dependency"],
    "env": ["path", "permission", "disk", "memory", "network", "connection"],
}


class SwarmDebugger:
    """Coordinates multiple debug hypotheses in parallel."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, bug_description: str,
                error_logs: Optional[str] = None,
                code_context: Optional[dict[str, str]] = None,
                stack_trace: Optional[str] = None) -> SwarmReport:
        """Main entry: analyze a bug with parallel hypotheses."""
        start = time.time()
        logger.info("Starting swarm debug for: %s", bug_description[:80])

        code_context = code_context or {}

        # Phase 1: Generate hypotheses
        hypotheses = self._generate_hypotheses(
            bug_description, error_logs, stack_trace
        )
        logger.info("Generated %d hypotheses", len(hypotheses))

        # Phase 2: Investigate each hypothesis
        all_findings: list[DebugFinding] = []
        for hyp in hypotheses:
            findings = self._investigate(hyp, code_context, error_logs, stack_trace)
            all_findings.extend(findings)
            self._update_confidence(hyp, findings)

        # Phase 3: Synthesize — find root cause
        hypotheses.sort(key=lambda h: -h.confidence)
        root = None
        for h in hypotheses:
            if h.confidence >= 0.7:
                h.status = "confirmed"
                h.root_cause = True
                root = h
                break
            elif h.confidence < 0.2:
                h.status = "rejected"
            else:
                h.status = "investigating"

        # Phase 4: Generate fix suggestion
        fix = self._suggest_fix(root, all_findings) if root else ""

        duration = (time.time() - start) * 1000
        report = SwarmReport(
            bug_description=bug_description,
            hypotheses=hypotheses,
            findings=all_findings,
            root_cause=root,
            suggested_fix=fix,
            investigation_summary=self._summarize(hypotheses, all_findings),
            confidence=root.confidence if root else 0.0,
            duration_ms=round(duration, 2),
        )
        logger.info("Swarm debug complete: root_cause=%s, confidence=%.2f",
                     root.description[:40] if root else "none", report.confidence)
        return report

    def _generate_hypotheses(self, description: str,
                             error_logs: Optional[str],
                             stack_trace: Optional[str]) -> list[Hypothesis]:
        """Generate debug hypotheses from available information."""
        hypotheses = []
        text = f"{description} {error_logs or ''} {stack_trace or ''}".lower()

        for category, keywords in CATEGORY_HEURISTICS.items():
            matching = [kw for kw in keywords if kw in text]
            if matching:
                confidence = min(0.3 + len(matching) * 0.1, 0.6)
                hyp = Hypothesis(
                    id=f"hyp_{category}",
                    description=f"Bug caused by {category} issue (keywords: {', '.join(matching)})",
                    category=category,
                    confidence=confidence,
                    investigation_steps=self._steps_for_category(category),
                )
                hypotheses.append(hyp)

        # Always add a generic hypothesis
        if not hypotheses:
            hypotheses.append(Hypothesis(
                id="hyp_generic",
                description="Investigate based on available context",
                category="logic",
                confidence=0.3,
                investigation_steps=["Review error logs", "Check recent changes", "Add debug logging"],
            ))

        return hypotheses

    def _steps_for_category(self, category: str) -> list[str]:
        """Get investigation steps for a category."""
        steps_map = {
            "logic": ["Trace execution path", "Check conditional branches", "Verify return values"],
            "data": ["Validate input data", "Check for null/empty values", "Verify data format"],
            "concurrency": ["Check for shared state", "Review locking", "Look for race conditions"],
            "config": ["Compare config values", "Check env variables", "Verify defaults"],
            "dependency": ["Check versions", "Review imports", "Test with pinned versions"],
            "env": ["Check permissions", "Verify paths exist", "Check resources"],
        }
        return steps_map.get(category, ["General investigation"])

    def _investigate(self, hypothesis: Hypothesis,
                     code_context: dict[str, str],
                     error_logs: Optional[str],
                     stack_trace: Optional[str]) -> list[DebugFinding]:
        """Investigate a single hypothesis."""
        findings = []

        # Check error logs for evidence
        if error_logs:
            for keyword in CATEGORY_HEURISTICS.get(hypothesis.category, []):
                if keyword in error_logs.lower():
                    findings.append(DebugFinding(
                        hypothesis_id=hypothesis.id,
                        finding=f"Keyword '{keyword}' found in error logs",
                        evidence_type="log",
                        supports_hypothesis=True,
                    ))

        # Check stack trace
        if stack_trace and hypothesis.category in ("logic", "data"):
            if "Traceback" in stack_trace or "Error" in stack_trace:
                findings.append(DebugFinding(
                    hypothesis_id=hypothesis.id,
                    finding="Stack trace present — supports error hypothesis",
                    evidence_type="trace",
                    supports_hypothesis=True,
                ))

        # Check code context
        for fpath, content in code_context.items():
            content_lower = content.lower()
            for keyword in CATEGORY_HEURISTICS.get(hypothesis.category, []):
                if keyword in content_lower:
                    findings.append(DebugFinding(
                        hypothesis_id=hypothesis.id,
                        finding=f"Related pattern '{keyword}' in {fpath}",
                        evidence_type="observation",
                        supports_hypothesis=True,
                        file_path=fpath,
                    ))
                    break

        return findings

    def _update_confidence(self, hypothesis: Hypothesis, findings: list[DebugFinding]):
        """Update hypothesis confidence based on findings."""
        for finding in findings:
            if finding.supports_hypothesis:
                hypothesis.confidence = min(1.0, hypothesis.confidence + 0.1)
                hypothesis.evidence_for.append(finding.finding)
            else:
                hypothesis.confidence = max(0.0, hypothesis.confidence - 0.15)
                hypothesis.evidence_against.append(finding.finding)

    def _suggest_fix(self, root: Hypothesis, findings: list[DebugFinding]) -> str:
        """Suggest a fix based on root cause."""
        fix_templates = {
            "logic": "Review and correct the conditional logic in the identified code path",
            "data": "Add input validation and null checks at the entry points",
            "concurrency": "Add proper synchronization or use atomic operations",
            "config": "Verify and fix configuration values; add config validation",
            "dependency": "Update dependency versions and verify compatibility",
            "env": "Fix environment setup (paths, permissions, resources)",
        }
        return fix_templates.get(root.category, "Review the identified code and apply fix")

    def _summarize(self, hypotheses: list[Hypothesis],
                   findings: list[DebugFinding]) -> str:
        """Summarize the investigation."""
        confirmed = [h for h in hypotheses if h.status == "confirmed"]
        rejected = [h for h in hypotheses if h.status == "rejected"]
        return (
            f"Investigated {len(hypotheses)} hypotheses with {len(findings)} findings. "
            f"Confirmed: {len(confirmed)}, Rejected: {len(rejected)}, "
            f"Remaining: {len(hypotheses) - len(confirmed) - len(rejected)}"
        )


def format_report(report: SwarmReport) -> str:
    """Format swarm report."""
    lines = [
        "# Swarm Debug Report",
        f"Bug: {report.bug_description[:100]}",
        f"Confidence: {report.confidence:.0%}",
        "",
    ]
    if report.root_cause:
        lines.append(f"## Root Cause\n{report.root_cause.description}")
        lines.append(f"\n## Suggested Fix\n{report.suggested_fix}")
    lines.append(f"\n## Hypotheses ({len(report.hypotheses)})")
    for h in report.hypotheses:
        lines.append(f"  [{h.status}] {h.description} ({h.confidence:.0%})")
    return "\n".join(lines)
