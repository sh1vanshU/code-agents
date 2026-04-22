"""Terraform Plan Explainer — parse plan JSON and produce plain-English summary.

Reads `terraform show -json <plan>` output and explains each resource change,
highlights risks, and summarizes the blast radius.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.devops.terraform_explainer")

# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------
_HIGH_RISK_TYPES = {
    "aws_db_instance", "aws_rds_cluster", "aws_elasticache_cluster",
    "google_sql_database_instance", "azurerm_sql_server",
    "aws_iam_role", "aws_iam_policy", "google_project_iam_binding",
    "aws_security_group", "aws_vpc", "google_compute_firewall",
    "aws_route53_record", "google_dns_record_set",
}

_DESTRUCTIVE_ACTIONS = {"delete", "replace"}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ResourceChange:
    """A single resource change from the plan."""

    address: str
    resource_type: str
    action: str  # "create" | "update" | "delete" | "replace" | "no-op"
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    changed_attributes: list[str] = field(default_factory=list)
    risk: str = "low"  # "low" | "medium" | "high" | "critical"


@dataclass
class ExplanationResult:
    """Full explanation of a Terraform plan."""

    changes: list[ResourceChange] = field(default_factory=list)
    summary: str = ""
    risk_level: str = "low"
    warnings: list[str] = field(default_factory=list)
    plain_english: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return _count_actions(self.changes)


def _count_actions(changes: list[ResourceChange]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in changes:
        counts[c.action] = counts.get(c.action, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Explainer
# ---------------------------------------------------------------------------


class TerraformExplainer:
    """Parse Terraform plan JSON and produce plain-English explanation."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()

    # ── Public API ────────────────────────────────────────────────────────

    def explain(self, plan_json: str | dict) -> ExplanationResult:
        """Explain a Terraform plan.

        Args:
            plan_json: Either a path to a JSON file, a JSON string, or a dict.
        """
        data = self._load_plan(plan_json)
        if data is None:
            return ExplanationResult(
                summary="Failed to load plan",
                warnings=["Could not parse Terraform plan JSON"],
            )

        result = ExplanationResult()
        resource_changes = data.get("resource_changes", [])

        for rc in resource_changes:
            change = self._parse_resource_change(rc)
            if change.action == "no-op":
                continue
            result.changes.append(change)

        # Build explanations
        result.plain_english = [self._explain_change(c) for c in result.changes]
        result.warnings = self._identify_risks(result.changes)
        result.risk_level = self._overall_risk(result.changes)
        result.summary = self._build_summary(result)

        logger.info("Explained %d changes, risk=%s", len(result.changes), result.risk_level)
        return result

    def explain_file(self, filepath: str) -> ExplanationResult:
        """Convenience: explain a plan JSON file."""
        return self.explain(filepath)

    # ── Parsing ───────────────────────────────────────────────────────────

    def _load_plan(self, plan_json: str | dict) -> Optional[dict]:
        """Load plan from file, string, or dict."""
        if isinstance(plan_json, dict):
            return plan_json

        # Try as file path
        if isinstance(plan_json, str):
            path = Path(plan_json)
            if path.is_file():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as exc:
                    logger.error("Failed to read plan file: %s", exc)
                    return None
            # Try as JSON string
            try:
                return json.loads(plan_json)
            except json.JSONDecodeError:
                logger.error("Input is not valid JSON")
                return None
        return None

    def _parse_resource_change(self, rc: dict) -> ResourceChange:
        """Parse a resource_changes entry into ResourceChange."""
        change_block = rc.get("change", {})
        actions = change_block.get("actions", ["no-op"])

        # Determine consolidated action
        if actions == ["no-op"]:
            action = "no-op"
        elif "delete" in actions and "create" in actions:
            action = "replace"
        elif "delete" in actions:
            action = "delete"
        elif "create" in actions:
            action = "create"
        elif "update" in actions:
            action = "update"
        else:
            action = actions[0] if actions else "no-op"

        before = change_block.get("before") or {}
        after = change_block.get("after") or {}
        address = rc.get("address", "unknown")
        resource_type = rc.get("type", address.split(".")[0] if "." in address else "unknown")

        # Find changed attributes
        changed_attrs = self._diff_attributes(before, after)

        # Classify risk
        risk = self._classify_risk(resource_type, action, changed_attrs)

        return ResourceChange(
            address=address,
            resource_type=resource_type,
            action=action,
            before=before,
            after=after,
            changed_attributes=changed_attrs,
            risk=risk,
        )

    def _diff_attributes(self, before: dict, after: dict) -> list[str]:
        """Find attributes that changed between before/after."""
        changed = []
        all_keys = set(list(before.keys()) + list(after.keys()))
        for k in sorted(all_keys):
            bv = before.get(k)
            av = after.get(k)
            if bv != av:
                changed.append(k)
        return changed

    # ── Risk classification ───────────────────────────────────────────────

    def _classify_risk(self, resource_type: str, action: str, changed_attrs: list[str]) -> str:
        """Classify the risk level of a change."""
        if action in _DESTRUCTIVE_ACTIONS and resource_type in _HIGH_RISK_TYPES:
            return "critical"
        if resource_type in _HIGH_RISK_TYPES:
            return "high"
        if action in _DESTRUCTIVE_ACTIONS:
            return "high"
        sensitive_attrs = {"cidr_block", "ingress", "egress", "policy", "iam", "password", "engine_version"}
        if any(attr in sensitive_attrs for attr in changed_attrs):
            return "medium"
        return "low"

    def _overall_risk(self, changes: list[ResourceChange]) -> str:
        """Determine the overall risk level across all changes."""
        levels = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        max_risk = max((levels.get(c.risk, 1) for c in changes), default=1)
        return {4: "critical", 3: "high", 2: "medium", 1: "low"}[max_risk]

    # ── Explanation generation ────────────────────────────────────────────

    def _explain_change(self, change: ResourceChange) -> str:
        """Generate a plain-English explanation for a single change."""
        action_verb = {
            "create": "Create",
            "update": "Update",
            "delete": "Destroy",
            "replace": "Replace (destroy + recreate)",
        }.get(change.action, change.action.title())

        explanation = f"{action_verb} {change.resource_type} '{change.address}'"

        if change.changed_attributes:
            attrs = ", ".join(change.changed_attributes[:5])
            if len(change.changed_attributes) > 5:
                attrs += f" (+{len(change.changed_attributes) - 5} more)"
            explanation += f" — changing: {attrs}"

        if change.risk in ("high", "critical"):
            explanation += f" [RISK: {change.risk.upper()}]"

        return explanation

    def _identify_risks(self, changes: list[ResourceChange]) -> list[str]:
        """Identify specific risks in the plan."""
        warnings = []

        # Check for destructive changes
        deletes = [c for c in changes if c.action in _DESTRUCTIVE_ACTIONS]
        if deletes:
            warnings.append(
                f"{len(deletes)} resource(s) will be destroyed or replaced — verify this is intentional"
            )

        # Check for IAM changes
        iam_changes = [c for c in changes if "iam" in c.resource_type.lower()]
        if iam_changes:
            warnings.append(
                f"{len(iam_changes)} IAM change(s) detected — review permissions carefully"
            )

        # Check for network changes
        net_changes = [c for c in changes if any(kw in c.resource_type.lower()
                       for kw in ("security_group", "firewall", "vpc", "subnet", "route"))]
        if net_changes:
            warnings.append(
                f"{len(net_changes)} network change(s) — may affect connectivity"
            )

        # Check for data store changes
        data_changes = [c for c in changes if c.risk == "critical"]
        if data_changes:
            warnings.append(
                f"{len(data_changes)} critical change(s) to data stores — risk of data loss"
            )

        return warnings

    def _build_summary(self, result: ExplanationResult) -> str:
        """Build a human-readable summary."""
        counts = result.counts
        parts = []
        for action in ("create", "update", "delete", "replace"):
            n = counts.get(action, 0)
            if n:
                parts.append(f"{n} to {action}")
        changes_str = ", ".join(parts) if parts else "no changes"
        return f"Plan: {changes_str}. Overall risk: {result.risk_level}."
