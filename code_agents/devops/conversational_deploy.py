"""Conversational Deploy — natural language deploy commands to execution plans."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.devops.conversational_deploy")


@dataclass
class DeployIntent:
    """Parsed intent from natural language deploy command."""
    action: str = ""  # deploy, rollback, promote, canary, scale
    target_env: str = ""  # staging, production, dev
    service: str = ""
    version: str = ""  # SHA, tag, or description
    conditions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    raw_command: str = ""


@dataclass
class DeployStep:
    """A single step in the deploy plan."""
    order: int = 0
    action: str = ""
    command: str = ""
    description: str = ""
    requires_approval: bool = False
    estimated_duration_s: int = 0
    rollback_command: str = ""


@dataclass
class DeployPlan:
    """Complete deploy execution plan."""
    intent: DeployIntent = field(default_factory=DeployIntent)
    steps: list[DeployStep] = field(default_factory=list)
    pre_checks: list[str] = field(default_factory=list)
    post_checks: list[str] = field(default_factory=list)
    total_estimated_s: int = 0
    requires_approval: bool = True
    risk_level: str = "medium"


@dataclass
class ConversationalDeployReport:
    """Report from conversational deploy analysis."""
    plan: Optional[DeployPlan] = None
    parsed_intent: Optional[DeployIntent] = None
    ambiguities: list[str] = field(default_factory=list)
    resolved_refs: dict = field(default_factory=dict)  # "yesterday's fix" -> SHA
    warnings: list[str] = field(default_factory=list)
    success: bool = True


# Intent parsing patterns
ACTION_PATTERNS = {
    "deploy": re.compile(r"\b(deploy|push|ship|release|send)\b", re.IGNORECASE),
    "rollback": re.compile(r"\b(rollback|revert|undo|restore)\b", re.IGNORECASE),
    "promote": re.compile(r"\b(promote|move|advance)\b", re.IGNORECASE),
    "canary": re.compile(r"\b(canary|gradual|percentage|phased)\b", re.IGNORECASE),
    "scale": re.compile(r"\b(scale|resize|replicas)\b", re.IGNORECASE),
}

ENV_PATTERNS = {
    "production": re.compile(r"\b(prod(?:uction)?|live)\b", re.IGNORECASE),
    "staging": re.compile(r"\b(stag(?:ing)?|preprod|pre-prod)\b", re.IGNORECASE),
    "dev": re.compile(r"\b(dev(?:elopment)?|sandbox)\b", re.IGNORECASE),
}

TIME_REFS = {
    "yesterday": re.compile(r"\byesterday'?s?\b", re.IGNORECASE),
    "today": re.compile(r"\btoday'?s?\b", re.IGNORECASE),
    "latest": re.compile(r"\b(latest|newest|recent|last)\b", re.IGNORECASE),
    "previous": re.compile(r"\b(previous|prior|before)\b", re.IGNORECASE),
}


class ConversationalDeploy:
    """Translates natural language deploy commands into execution plans."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, command: str,
                git_log: Optional[list[dict]] = None,
                services: Optional[list[str]] = None) -> ConversationalDeployReport:
        """Parse NL command and generate deploy plan."""
        logger.info("Parsing deploy command: %s", command[:80])
        git_log = git_log or []
        services = services or []

        # Phase 1: Parse intent
        intent = self._parse_intent(command, services)

        # Phase 2: Resolve references
        resolved = self._resolve_references(command, git_log)

        # Phase 3: Fill in intent from resolved refs
        if not intent.version and resolved:
            intent.version = list(resolved.values())[0]

        # Phase 4: Check for ambiguities
        ambiguities = self._check_ambiguities(intent)

        # Phase 5: Generate plan
        plan = None
        if intent.action and intent.target_env and not ambiguities:
            plan = self._generate_plan(intent)
        elif ambiguities:
            logger.warning("Ambiguities found: %s", ambiguities)

        report = ConversationalDeployReport(
            plan=plan,
            parsed_intent=intent,
            ambiguities=ambiguities,
            resolved_refs=resolved,
            warnings=self._generate_warnings(intent, plan),
            success=plan is not None,
        )
        logger.info("Deploy parse: action=%s, env=%s, success=%s",
                     intent.action, intent.target_env, report.success)
        return report

    def _parse_intent(self, command: str, services: list[str]) -> DeployIntent:
        """Parse natural language into DeployIntent."""
        intent = DeployIntent(raw_command=command)
        confidence = 0.0

        # Detect action
        for action, pattern in ACTION_PATTERNS.items():
            if pattern.search(command):
                intent.action = action
                confidence += 0.3
                break

        # Detect environment
        for env, pattern in ENV_PATTERNS.items():
            if pattern.search(command):
                intent.target_env = env
                confidence += 0.3
                break

        # Detect service
        for svc in services:
            if svc.lower() in command.lower():
                intent.service = svc
                confidence += 0.2
                break

        # Detect version/SHA
        sha_match = re.search(r"\b([0-9a-f]{7,40})\b", command)
        if sha_match:
            intent.version = sha_match.group(1)
            confidence += 0.2

        tag_match = re.search(r"\bv?\d+\.\d+(?:\.\d+)?\b", command)
        if tag_match:
            intent.version = tag_match.group(0)
            confidence += 0.2

        intent.confidence = min(1.0, confidence)
        return intent

    def _resolve_references(self, command: str, git_log: list[dict]) -> dict:
        """Resolve time references to actual SHAs."""
        resolved = {}
        for ref_name, pattern in TIME_REFS.items():
            if pattern.search(command):
                sha = self._find_commit(ref_name, git_log)
                if sha:
                    resolved[ref_name] = sha
        return resolved

    def _find_commit(self, ref: str, git_log: list[dict]) -> Optional[str]:
        """Find a commit matching a time reference."""
        if not git_log:
            return None
        if ref == "latest" or ref == "today":
            return git_log[0].get("sha", "")
        if ref == "yesterday":
            for entry in git_log:
                date = entry.get("date", "")
                if "yesterday" in str(date) or len(git_log) > 1:
                    return entry.get("sha", "")
            return git_log[-1].get("sha", "") if git_log else None
        if ref == "previous":
            return git_log[1].get("sha", "") if len(git_log) > 1 else None
        return None

    def _check_ambiguities(self, intent: DeployIntent) -> list[str]:
        """Check for ambiguities in the parsed intent."""
        ambiguities = []
        if not intent.action:
            ambiguities.append("Could not determine action (deploy, rollback, etc.)")
        if not intent.target_env:
            ambiguities.append("Target environment not specified")
        if intent.action == "deploy" and not intent.version:
            ambiguities.append("No version/SHA specified — which version to deploy?")
        return ambiguities

    def _generate_plan(self, intent: DeployIntent) -> DeployPlan:
        """Generate deploy execution plan."""
        steps = []
        pre_checks = ["Verify CI/CD pipeline passed", "Check target environment health"]
        post_checks = ["Verify deployment health", "Run smoke tests"]
        risk = "medium"

        if intent.action == "deploy":
            steps = self._deploy_steps(intent)
            if intent.target_env == "production":
                risk = "high"
                pre_checks.append("Get production deploy approval")
        elif intent.action == "rollback":
            steps = self._rollback_steps(intent)
            risk = "high"
        elif intent.action == "promote":
            steps = self._promote_steps(intent)
        elif intent.action == "canary":
            steps = self._canary_steps(intent)
            post_checks.append("Monitor canary metrics for 15 min")

        total = sum(s.estimated_duration_s for s in steps)
        return DeployPlan(
            intent=intent,
            steps=steps,
            pre_checks=pre_checks,
            post_checks=post_checks,
            total_estimated_s=total,
            requires_approval=intent.target_env == "production",
            risk_level=risk,
        )

    def _deploy_steps(self, intent: DeployIntent) -> list[DeployStep]:
        """Generate deploy steps."""
        svc = intent.service or "service"
        return [
            DeployStep(order=1, action="build", command=f"docker build -t {svc}:{intent.version} .",
                       description="Build image", estimated_duration_s=120),
            DeployStep(order=2, action="push", command=f"docker push {svc}:{intent.version}",
                       description="Push to registry", estimated_duration_s=60),
            DeployStep(order=3, action="deploy", command=f"kubectl set image deployment/{svc} {svc}={svc}:{intent.version}",
                       description=f"Deploy to {intent.target_env}", estimated_duration_s=90,
                       requires_approval=intent.target_env == "production",
                       rollback_command=f"kubectl rollout undo deployment/{svc}"),
            DeployStep(order=4, action="verify", command=f"kubectl rollout status deployment/{svc}",
                       description="Verify rollout", estimated_duration_s=60),
        ]

    def _rollback_steps(self, intent: DeployIntent) -> list[DeployStep]:
        svc = intent.service or "service"
        return [
            DeployStep(order=1, action="rollback", command=f"kubectl rollout undo deployment/{svc}",
                       description=f"Rollback {svc} in {intent.target_env}", estimated_duration_s=30,
                       requires_approval=True),
            DeployStep(order=2, action="verify", command=f"kubectl rollout status deployment/{svc}",
                       description="Verify rollback", estimated_duration_s=60),
        ]

    def _promote_steps(self, intent: DeployIntent) -> list[DeployStep]:
        svc = intent.service or "service"
        return [
            DeployStep(order=1, action="tag", command=f"docker tag {svc}:staging {svc}:{intent.target_env}",
                       description="Tag for promotion", estimated_duration_s=10),
            DeployStep(order=2, action="deploy", command=f"kubectl set image deployment/{svc} {svc}={svc}:{intent.target_env}",
                       description=f"Promote to {intent.target_env}", estimated_duration_s=90,
                       requires_approval=True),
        ]

    def _canary_steps(self, intent: DeployIntent) -> list[DeployStep]:
        svc = intent.service or "service"
        return [
            DeployStep(order=1, action="canary", command=f"kubectl apply -f canary-{svc}.yaml",
                       description="Deploy canary (10%)", estimated_duration_s=60),
            DeployStep(order=2, action="monitor", command="sleep 900 && check-canary-metrics",
                       description="Monitor canary for 15 min", estimated_duration_s=900),
            DeployStep(order=3, action="promote", command=f"kubectl apply -f {svc}-full.yaml",
                       description="Promote canary to full", estimated_duration_s=60,
                       requires_approval=True),
        ]

    def _generate_warnings(self, intent: DeployIntent,
                           plan: Optional[DeployPlan]) -> list[str]:
        warnings = []
        if intent.target_env == "production" and intent.confidence < 0.7:
            warnings.append("Low confidence parse for production deploy — verify intent carefully")
        if plan and plan.risk_level == "high":
            warnings.append("High-risk operation — ensure rollback plan is ready")
        return warnings


def format_report(report: ConversationalDeployReport) -> str:
    lines = ["# Conversational Deploy"]
    if report.parsed_intent:
        i = report.parsed_intent
        lines.append(f"Intent: {i.action} to {i.target_env} (confidence: {i.confidence:.0%})")
    if report.plan:
        lines.append(f"Risk: {report.plan.risk_level} | Steps: {len(report.plan.steps)}")
        for s in report.plan.steps:
            lines.append(f"  {s.order}. {s.description}: {s.command}")
    if report.ambiguities:
        lines.append("\n## Ambiguities")
        for a in report.ambiguities:
            lines.append(f"  ? {a}")
    return "\n".join(lines)
