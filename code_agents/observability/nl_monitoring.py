"""NL Monitoring — define alerts in natural language with exception handling."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.observability.nl_monitoring")


@dataclass
class AlertRule:
    """A structured alert rule generated from NL."""
    name: str = ""
    metric: str = ""
    condition: str = ""  # gt, lt, gte, lte, eq
    threshold: float = 0.0
    duration_min: int = 5
    severity: str = "warning"  # info, warning, critical
    notification_channels: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    description: str = ""
    promql: str = ""  # generated PromQL or equivalent


@dataclass
class AlertException:
    """An exception to an alert rule."""
    condition: str = ""
    description: str = ""
    time_window: str = ""  # "weekends", "maintenance window", etc.


@dataclass
class MonitoringConfig:
    """Complete monitoring configuration."""
    rules: list[AlertRule] = field(default_factory=list)
    dashboards: list[dict] = field(default_factory=list)
    total_rules: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class NLMonitoringReport:
    """Report from NL monitoring analysis."""
    config: MonitoringConfig = field(default_factory=MonitoringConfig)
    parsed_intents: list[dict] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    success: bool = True


METRIC_PATTERNS = {
    "error_rate": re.compile(r"\b(error\s*rate|failure\s*rate|5xx|errors?\s*per)\b", re.IGNORECASE),
    "latency": re.compile(r"\b(latency|response\s*time|p\d{2}|duration|slow)\b", re.IGNORECASE),
    "cpu": re.compile(r"\b(cpu|processor|compute)\b", re.IGNORECASE),
    "memory": re.compile(r"\b(memory|ram|heap|oom)\b", re.IGNORECASE),
    "throughput": re.compile(r"\b(throughput|requests?\s*per|rps|qps|tps)\b", re.IGNORECASE),
    "disk": re.compile(r"\b(disk|storage|volume|filesystem)\b", re.IGNORECASE),
    "queue": re.compile(r"\b(queue\s*(?:depth|length|size)|backlog|pending)\b", re.IGNORECASE),
    "availability": re.compile(r"\b(uptime|availability|health|down)\b", re.IGNORECASE),
}

CONDITION_PATTERNS = {
    "gt": re.compile(r"\b(above|over|exceeds?|greater\s+than|more\s+than|higher\s+than|>\s*)\b", re.IGNORECASE),
    "lt": re.compile(r"\b(below|under|less\s+than|lower\s+than|drops?\s+below|<\s*)\b", re.IGNORECASE),
    "eq": re.compile(r"\b(equals?|exactly|is\s+)\b", re.IGNORECASE),
}

SEVERITY_PATTERNS = {
    "critical": re.compile(r"\b(critical|urgent|page|emergency|severe)\b", re.IGNORECASE),
    "warning": re.compile(r"\b(warn(?:ing)?|alert|notify|attention)\b", re.IGNORECASE),
    "info": re.compile(r"\b(info|informational|fyi|log)\b", re.IGNORECASE),
}

EXCEPTION_PATTERNS = [
    re.compile(r"\b(?:except|unless|ignore|exclude|skip)\s+(?:during|when|if)\s+(.+?)(?:\.|$)", re.IGNORECASE),
    re.compile(r"\b(?:not\s+during|outside\s+of)\s+(.+?)(?:\.|$)", re.IGNORECASE),
]

CHANNEL_PATTERNS = {
    "slack": re.compile(r"\b(slack|channel|#\w+)\b", re.IGNORECASE),
    "email": re.compile(r"\b(email|mail)\b", re.IGNORECASE),
    "pagerduty": re.compile(r"\b(pager\s*duty|page|oncall|on-call)\b", re.IGNORECASE),
}

NUMBER_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent|ms|seconds?|minutes?|s|m)?")
DURATION_PATTERN = re.compile(r"(?:for|lasting|over)\s+(\d+)\s*(min(?:ute)?s?|hours?|seconds?)", re.IGNORECASE)


class NLMonitoring:
    """Parses natural language alert definitions into monitoring configs."""

    def __init__(self):
        pass

    def analyze(self, descriptions: list[str]) -> NLMonitoringReport:
        """Parse NL alert descriptions into structured config."""
        logger.info("Parsing %d alert descriptions", len(descriptions))

        rules = []
        intents = []
        ambiguities = []

        for desc in descriptions:
            rule, intent, ambs = self._parse_alert(desc)
            if rule:
                rules.append(rule)
            intents.append(intent)
            ambiguities.extend(ambs)

        config = MonitoringConfig(
            rules=rules,
            total_rules=len(rules),
            warnings=self._generate_warnings(rules, ambiguities),
        )

        report = NLMonitoringReport(
            config=config,
            parsed_intents=intents,
            ambiguities=ambiguities,
            success=len(rules) > 0,
        )
        logger.info("Parsed %d rules from %d descriptions", len(rules), len(descriptions))
        return report

    def _parse_alert(self, description: str) -> tuple[Optional[AlertRule], dict, list[str]]:
        """Parse a single alert description."""
        intent = {"raw": description}
        ambiguities = []

        # Detect metric
        metric = self._detect_metric(description)
        intent["metric"] = metric
        if not metric:
            ambiguities.append(f"Could not identify metric in: {description[:60]}")

        # Detect condition and threshold
        condition = self._detect_condition(description)
        threshold = self._detect_threshold(description)
        intent["condition"] = condition
        intent["threshold"] = threshold

        if threshold is None:
            ambiguities.append("No threshold value found")

        # Detect severity
        severity = self._detect_severity(description)
        intent["severity"] = severity

        # Detect duration
        duration = self._detect_duration(description)

        # Detect exceptions
        exceptions = self._detect_exceptions(description)

        # Detect channels
        channels = self._detect_channels(description)

        # Generate PromQL
        promql = self._generate_promql(metric, condition, threshold, duration)

        if not metric or threshold is None:
            return None, intent, ambiguities

        rule = AlertRule(
            name=self._generate_name(metric, condition, threshold),
            metric=metric,
            condition=condition,
            threshold=threshold,
            duration_min=duration,
            severity=severity,
            notification_channels=channels,
            exceptions=exceptions,
            description=description,
            promql=promql,
        )
        return rule, intent, ambiguities

    def _detect_metric(self, desc: str) -> str:
        """Detect which metric is being monitored."""
        for metric, pattern in METRIC_PATTERNS.items():
            if pattern.search(desc):
                return metric
        return ""

    def _detect_condition(self, desc: str) -> str:
        """Detect the comparison condition."""
        for cond, pattern in CONDITION_PATTERNS.items():
            if pattern.search(desc):
                return cond
        return "gt"  # default

    def _detect_threshold(self, desc: str) -> Optional[float]:
        """Detect numeric threshold."""
        m = NUMBER_PATTERN.search(desc)
        if m:
            value = float(m.group(1))
            unit = m.group(2) or ""
            if "%" in unit or "percent" in unit:
                return value / 100 if value > 1 else value
            return value
        return None

    def _detect_severity(self, desc: str) -> str:
        for sev, pattern in SEVERITY_PATTERNS.items():
            if pattern.search(desc):
                return sev
        return "warning"

    def _detect_duration(self, desc: str) -> int:
        """Detect alert duration threshold."""
        m = DURATION_PATTERN.search(desc)
        if m:
            value = int(m.group(1))
            unit = m.group(2).lower()
            if "hour" in unit:
                return value * 60
            if "second" in unit:
                return max(1, value // 60)
            return value
        return 5

    def _detect_exceptions(self, desc: str) -> list[str]:
        exceptions = []
        for pattern in EXCEPTION_PATTERNS:
            for m in pattern.finditer(desc):
                exceptions.append(m.group(1).strip())
        return exceptions

    def _detect_channels(self, desc: str) -> list[str]:
        channels = []
        for channel, pattern in CHANNEL_PATTERNS.items():
            if pattern.search(desc):
                channels.append(channel)
        return channels or ["slack"]

    def _generate_promql(self, metric: str, condition: str,
                         threshold: Optional[float], duration: int) -> str:
        metric_map = {
            "error_rate": "rate(http_requests_total{status=~'5..'}[5m]) / rate(http_requests_total[5m])",
            "latency": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
            "cpu": "rate(process_cpu_seconds_total[5m]) * 100",
            "memory": "process_resident_memory_bytes / 1024 / 1024",
            "throughput": "rate(http_requests_total[5m])",
        }
        expr = metric_map.get(metric, f"{metric}_value")
        op = {"gt": ">", "lt": "<", "gte": ">=", "lte": "<=", "eq": "=="}.get(condition, ">")
        if threshold is not None:
            return f"{expr} {op} {threshold}"
        return expr

    def _generate_name(self, metric: str, condition: str, threshold: Optional[float]) -> str:
        return f"{metric}_{condition}_{threshold}" if threshold else f"{metric}_alert"

    def _generate_warnings(self, rules: list[AlertRule], ambiguities: list[str]) -> list[str]:
        warnings = []
        if ambiguities:
            warnings.append(f"{len(ambiguities)} parsing ambiguities — review generated rules")
        no_exceptions = [r for r in rules if not r.exceptions]
        if no_exceptions:
            warnings.append(f"{len(no_exceptions)} rules have no exceptions — consider maintenance windows")
        return warnings


def format_report(report: NLMonitoringReport) -> str:
    lines = ["# NL Monitoring Config", f"Rules: {report.config.total_rules}", ""]
    for r in report.config.rules:
        lines.append(f"## {r.name} [{r.severity}]")
        lines.append(f"  {r.description}")
        lines.append(f"  PromQL: {r.promql}")
        if r.exceptions:
            lines.append(f"  Exceptions: {', '.join(r.exceptions)}")
    return "\n".join(lines)
