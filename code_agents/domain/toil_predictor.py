"""Toil Predictor — predict manual process time cost and propose automation ROI."""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.domain.toil_predictor")


@dataclass
class ToilProcess:
    """A manual process being analyzed."""
    name: str = ""
    description: str = ""
    frequency_per_week: float = 0.0
    duration_min: float = 0.0
    error_rate: float = 0.0
    people_involved: int = 1
    category: str = ""  # deploy, testing, monitoring, data, reporting, incident


@dataclass
class AutomationProposal:
    """A proposed automation for a toil process."""
    process_name: str = ""
    automation_approach: str = ""
    implementation_effort_days: float = 0.0
    annual_time_saved_hours: float = 0.0
    annual_cost_saved: float = 0.0
    roi_months: float = 0.0
    confidence: float = 0.0
    prerequisites: list[str] = field(default_factory=list)


@dataclass
class ToilReport:
    """Complete toil analysis report."""
    processes: list[ToilProcess] = field(default_factory=list)
    proposals: list[AutomationProposal] = field(default_factory=list)
    total_weekly_hours: float = 0.0
    total_annual_hours: float = 0.0
    automatable_pct: float = 0.0
    top_roi_proposals: list[AutomationProposal] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


AUTOMATION_APPROACHES = {
    "deploy": {"approach": "CI/CD pipeline automation", "effort_factor": 5, "savings_factor": 0.9},
    "testing": {"approach": "Automated test suite + CI integration", "effort_factor": 8, "savings_factor": 0.8},
    "monitoring": {"approach": "Alert rules + dashboard automation", "effort_factor": 3, "savings_factor": 0.85},
    "data": {"approach": "ETL pipeline or scheduled scripts", "effort_factor": 6, "savings_factor": 0.75},
    "reporting": {"approach": "Automated report generation + delivery", "effort_factor": 4, "savings_factor": 0.9},
    "incident": {"approach": "Runbook automation + self-healing", "effort_factor": 10, "savings_factor": 0.6},
}


class ToilPredictor:
    """Predicts toil costs and proposes automation ROI."""

    def __init__(self, hourly_rate: float = 75.0):
        self.hourly_rate = hourly_rate

    def analyze(self, processes: list[dict],
                hourly_rate: Optional[float] = None) -> ToilReport:
        """Analyze toil processes and generate automation proposals."""
        if hourly_rate:
            self.hourly_rate = hourly_rate
        logger.info("Analyzing %d manual processes", len(processes))

        toil_procs = [self._parse_process(p) for p in processes]

        # Compute totals
        weekly_hours = sum(p.frequency_per_week * p.duration_min / 60 * p.people_involved
                          for p in toil_procs)
        annual_hours = weekly_hours * 52

        # Generate proposals
        proposals = [self._generate_proposal(p) for p in toil_procs]
        proposals = [p for p in proposals if p is not None]
        proposals.sort(key=lambda p: p.roi_months)

        automatable = sum(1 for p in proposals if p.roi_months < 12)
        automatable_pct = (automatable / len(toil_procs) * 100) if toil_procs else 0

        report = ToilReport(
            processes=toil_procs,
            proposals=proposals,
            total_weekly_hours=round(weekly_hours, 1),
            total_annual_hours=round(annual_hours, 1),
            automatable_pct=round(automatable_pct, 1),
            top_roi_proposals=proposals[:5],
            warnings=self._generate_warnings(toil_procs, proposals),
        )
        logger.info("Toil: %.0f hrs/year, %d proposals, %.0f%% automatable",
                     annual_hours, len(proposals), automatable_pct)
        return report

    def _parse_process(self, raw: dict) -> ToilProcess:
        return ToilProcess(
            name=raw.get("name", ""),
            description=raw.get("description", ""),
            frequency_per_week=float(raw.get("frequency_per_week", raw.get("frequency", 1))),
            duration_min=float(raw.get("duration_min", raw.get("duration", 30))),
            error_rate=float(raw.get("error_rate", 0)),
            people_involved=int(raw.get("people", raw.get("people_involved", 1))),
            category=raw.get("category", "other"),
        )

    def _generate_proposal(self, process: ToilProcess) -> Optional[AutomationProposal]:
        """Generate automation proposal for a process."""
        config = AUTOMATION_APPROACHES.get(process.category, {
            "approach": "Custom automation script",
            "effort_factor": 7,
            "savings_factor": 0.7,
        })

        # Annual time in hours
        annual_hours = process.frequency_per_week * 52 * process.duration_min / 60 * process.people_involved
        saved_hours = annual_hours * config["savings_factor"]
        saved_cost = saved_hours * self.hourly_rate

        # Implementation cost
        effort_days = config["effort_factor"]
        impl_cost = effort_days * 8 * self.hourly_rate

        # ROI in months
        monthly_savings = saved_cost / 12
        roi_months = (impl_cost / monthly_savings) if monthly_savings > 0 else float("inf")

        return AutomationProposal(
            process_name=process.name,
            automation_approach=config["approach"],
            implementation_effort_days=effort_days,
            annual_time_saved_hours=round(saved_hours, 1),
            annual_cost_saved=round(saved_cost, 2),
            roi_months=round(roi_months, 1),
            confidence=min(0.9, 0.5 + process.frequency_per_week * 0.05),
        )

    def _generate_warnings(self, processes: list[ToilProcess],
                           proposals: list[AutomationProposal]) -> list[str]:
        warnings = []
        high_error = [p for p in processes if p.error_rate > 0.1]
        if high_error:
            warnings.append(f"{len(high_error)} processes have >10% error rate — automate for reliability")
        long_roi = [p for p in proposals if p.roi_months > 24]
        if long_roi:
            warnings.append(f"{len(long_roi)} proposals have >24 month ROI — deprioritize")
        return warnings


def format_report(report: ToilReport) -> str:
    lines = [
        "# Toil Prediction Report",
        f"Weekly: {report.total_weekly_hours:.0f}h | Annual: {report.total_annual_hours:.0f}h",
        f"Automatable: {report.automatable_pct:.0f}%",
        "",
    ]
    for p in report.top_roi_proposals:
        lines.append(f"  [{p.roi_months:.0f}mo ROI] {p.process_name}: {p.automation_approach}")
        lines.append(f"    Saves {p.annual_time_saved_hours:.0f}h/yr (${p.annual_cost_saved:,.0f})")
    return "\n".join(lines)
