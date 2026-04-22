"""
Sanity Check — post-deployment health verification via Kibana logs.

Loads rules from .code-agents/sanity.yaml (per-repo), queries Kibana,
evaluates thresholds, generates pass/fail report.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("code_agents.sanity_checker")


@dataclass
class SanityRule:
    name: str
    query: str
    threshold: int = 0  # max allowed matches (0 = zero tolerance)
    time_window: str = "5m"
    severity: str = "critical"  # critical, warning, info


@dataclass
class CheckResult:
    rule: SanityRule
    passed: bool
    match_count: int
    samples: list[str] = field(default_factory=list)  # sample log lines

    @property
    def status(self) -> str:
        return "✅ PASS" if self.passed else "❌ FAIL"


def load_rules(repo_path: str) -> list[SanityRule]:
    """Load sanity check rules from .code-agents/sanity.yaml."""
    config_path = Path(repo_path) / ".code-agents" / "sanity.yaml"
    if not config_path.is_file():
        logger.debug("No sanity.yaml found at %s", config_path)
        return []

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.warning("Failed to parse sanity.yaml: %s", e)
        return []

    rules = []
    for r in raw.get("rules", []):
        rules.append(SanityRule(
            name=r.get("name", "Unnamed"),
            query=r.get("query", ""),
            threshold=int(r.get("threshold", 0)),
            time_window=r.get("time_window", "5m"),
            severity=r.get("severity", "critical"),
        ))

    logger.info("Loaded %d sanity rules from %s", len(rules), config_path)
    return rules


async def run_check(rule: SanityRule, kibana_client: Any, service: str = "", index: str = "logs-*") -> CheckResult:
    """Execute a single sanity rule against Kibana."""
    try:
        results = await kibana_client.search_logs(
            index=index,
            query=rule.query,
            service=service,
            time_range=rule.time_window,
            size=5,  # just get samples
        )
        match_count = len(results)
        samples = [r.get("message", "")[:200] for r in results[:3]]
        passed = match_count <= rule.threshold

        return CheckResult(
            rule=rule,
            passed=passed,
            match_count=match_count,
            samples=samples,
        )
    except Exception as e:
        logger.error("Sanity check '%s' failed: %s", rule.name, e)
        return CheckResult(
            rule=rule,
            passed=False,
            match_count=-1,
            samples=[f"Check failed: {e}"],
        )


async def run_all_checks(repo_path: str, service: str, kibana_client: Any, index: str = "logs-*") -> list[CheckResult]:
    """Run all sanity rules for a service."""
    rules = load_rules(repo_path)
    if not rules:
        return []

    results = []
    for rule in rules:
        result = await run_check(rule, kibana_client, service=service, index=index)
        results.append(result)
        logger.info("Sanity: %s — %s (count=%d, threshold=%d)",
                     rule.name, result.status, result.match_count, rule.threshold)

    return results


def format_report(results: list[CheckResult]) -> str:
    """Format sanity check results as a readable report."""
    if not results:
        return "No sanity rules configured. Create .code-agents/sanity.yaml to define rules."

    lines = ["", "┌─────────────────────────────────────────┐", "│        SANITY CHECK REPORT              │", "├─────────────────────────────────────────┤"]

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    for r in results:
        status = r.status
        count_str = f"({r.match_count}/{r.rule.threshold})" if r.match_count >= 0 else "(error)"
        lines.append(f"│  {status} {r.rule.name:<25} {count_str:<10} │")
        if not r.passed and r.samples:
            for sample in r.samples[:2]:
                lines.append(f"│    └ {sample[:50]:<44} │")

    lines.append("├─────────────────────────────────────────┤")
    verdict = "✅ ALL CHECKS PASSED" if failed == 0 else f"❌ {failed} CHECK(S) FAILED"
    lines.append(f"│  {verdict:<39} │")
    lines.append("└─────────────────────────────────────────┘")

    return "\n".join(lines)


# Default rules for common scenarios
DEFAULT_RULES = [
    SanityRule(name="No 5xx errors", query="level:ERROR AND status:5*", threshold=0, time_window="5m"),
    SanityRule(name="No OOM kills", query="OOMKilled OR OutOfMemory", threshold=0, time_window="10m"),
    SanityRule(name="No panic/fatal", query="level:FATAL OR panic", threshold=0, time_window="5m"),
    SanityRule(name="Startup complete", query="Started Application", threshold=1, time_window="5m", severity="warning"),
]


# ---------------------------------------------------------------------------
# Endpoint health checks — actually hit URLs post-deployment
# ---------------------------------------------------------------------------


@dataclass
class EndpointCheck:
    """Health endpoint to verify after deployment."""
    url: str
    expected_status: int = 200
    name: str = ""
    timeout: int = 10


async def run_endpoint_checks(checks: list[EndpointCheck]) -> list[CheckResult]:
    """Run HTTP health checks against actual endpoints."""
    import httpx

    results = []
    for check in checks:
        name = check.name or check.url
        # Create a synthetic SanityRule for the CheckResult
        rule = SanityRule(name=name, query=check.url, threshold=check.expected_status)
        try:
            async with httpx.AsyncClient(timeout=check.timeout, verify=False) as client:
                r = await client.get(check.url)
            passed = r.status_code == check.expected_status
            results.append(CheckResult(
                rule=rule,
                passed=passed,
                match_count=r.status_code,
                samples=[f"HTTP {r.status_code}" + (f" (expected {check.expected_status})" if not passed else "")],
            ))
        except Exception as e:
            logger.debug("Endpoint check failed for %s: %s", name, e)
            results.append(CheckResult(
                rule=rule,
                passed=False,
                match_count=0,
                samples=[str(e)[:200]],
            ))
    return results


def discover_health_endpoints(
    repo_path: str,
    base_url: str = "http://localhost:8080",
) -> list[EndpointCheck]:
    """Find health/actuator endpoints from endpoint cache."""
    health_patterns = ["/health", "/actuator/health", "/actuator/info", "/ping", "/status", "/ready", "/live"]
    checks: list[EndpointCheck] = []
    try:
        from .endpoint_scanner import load_cache
        cached = load_cache(repo_path)
        if cached:
            for ep in cached.rest_endpoints:
                path_lower = ep.path.lower()
                if any(path_lower.endswith(p) for p in health_patterns):
                    checks.append(EndpointCheck(
                        url=f"{base_url.rstrip('/')}{ep.path}",
                        name=f"Health: {ep.path}",
                    ))
    except Exception:
        pass
    # Always include a default actuator health if none found
    if not checks:
        checks.append(EndpointCheck(
            url=f"{base_url.rstrip('/')}/actuator/health",
            name="Actuator Health (default)",
        ))
    return checks
