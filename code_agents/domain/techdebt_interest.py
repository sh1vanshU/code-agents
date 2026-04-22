"""Tech Debt Interest — compound cost calculator for refactor now vs later."""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.domain.techdebt_interest")


@dataclass
class DebtItem:
    """A single tech debt item."""
    name: str = ""
    description: str = ""
    category: str = ""  # code, architecture, test, docs, infra, dependency
    current_cost_hours_per_month: float = 0.0  # ongoing maintenance cost
    fix_cost_hours: float = 0.0  # one-time fix cost
    growth_rate: float = 0.05  # monthly interest rate (5% default)
    age_months: int = 0
    severity: str = "medium"  # low, medium, high, critical
    affected_teams: int = 1


@dataclass
class DebtProjection:
    """Projected cost of a debt item over time."""
    item_name: str = ""
    month_0_cost: float = 0.0
    month_6_cost: float = 0.0
    month_12_cost: float = 0.0
    month_24_cost: float = 0.0
    break_even_months: float = 0.0  # when fix cost < accumulated interest
    total_interest_12mo: float = 0.0
    recommendation: str = ""  # fix_now, fix_soon, monitor, accept


@dataclass
class DebtPortfolio:
    """Complete tech debt portfolio analysis."""
    items: list[DebtItem] = field(default_factory=list)
    projections: list[DebtProjection] = field(default_factory=list)
    total_monthly_cost: float = 0.0
    total_fix_cost: float = 0.0
    total_12mo_interest: float = 0.0
    debt_ratio: float = 0.0  # monthly debt cost / monthly capacity
    priority_queue: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class TechDebtInterest:
    """Calculates compound interest on tech debt."""

    def __init__(self, team_capacity_hours_per_month: float = 160.0,
                 hourly_rate: float = 75.0):
        self.capacity = team_capacity_hours_per_month
        self.hourly_rate = hourly_rate

    def analyze(self, debt_items: list[dict],
                planning_horizon_months: int = 24) -> DebtPortfolio:
        """Analyze tech debt portfolio with interest projections."""
        logger.info("Analyzing %d debt items over %d months",
                     len(debt_items), planning_horizon_months)

        items = [self._parse_item(d) for d in debt_items]

        # Generate projections
        projections = []
        for item in items:
            proj = self._project(item, planning_horizon_months)
            projections.append(proj)

        projections.sort(key=lambda p: -p.total_interest_12mo)

        total_monthly = sum(i.current_cost_hours_per_month * i.affected_teams for i in items)
        total_fix = sum(i.fix_cost_hours for i in items)
        total_12mo = sum(p.total_interest_12mo for p in projections)
        debt_ratio = total_monthly / self.capacity if self.capacity > 0 else 0

        priority = [p.item_name for p in projections if p.recommendation in ("fix_now", "fix_soon")]

        portfolio = DebtPortfolio(
            items=items,
            projections=projections,
            total_monthly_cost=round(total_monthly, 1),
            total_fix_cost=round(total_fix, 1),
            total_12mo_interest=round(total_12mo, 1),
            debt_ratio=round(debt_ratio, 3),
            priority_queue=priority,
            warnings=self._generate_warnings(items, debt_ratio, projections),
        )
        logger.info("Debt portfolio: %.0fh/mo cost, %.0fh fix, %.1f%% ratio",
                     total_monthly, total_fix, debt_ratio * 100)
        return portfolio

    def _parse_item(self, raw: dict) -> DebtItem:
        return DebtItem(
            name=raw.get("name", ""),
            description=raw.get("description", ""),
            category=raw.get("category", "code"),
            current_cost_hours_per_month=float(raw.get("monthly_cost", raw.get("cost_hours_per_month", 2))),
            fix_cost_hours=float(raw.get("fix_cost", raw.get("fix_cost_hours", 16))),
            growth_rate=float(raw.get("growth_rate", 0.05)),
            age_months=int(raw.get("age_months", raw.get("age", 0))),
            severity=raw.get("severity", "medium"),
            affected_teams=int(raw.get("affected_teams", raw.get("teams", 1))),
        )

    def _project(self, item: DebtItem, horizon: int) -> DebtProjection:
        """Project debt costs over time with compound interest."""
        base = item.current_cost_hours_per_month * item.affected_teams
        rate = item.growth_rate

        # Compound monthly costs
        month_costs = []
        for m in range(horizon + 1):
            cost = base * math.pow(1 + rate, m)
            month_costs.append(cost)

        # Cumulative interest (total cost over time minus fix cost)
        cumulative = [sum(month_costs[:m + 1]) for m in range(len(month_costs))]

        # Break-even: when cumulative cost > fix cost
        break_even = float("inf")
        for m, cum in enumerate(cumulative):
            if cum >= item.fix_cost_hours:
                break_even = m
                break

        # 12-month interest
        interest_12 = cumulative[min(12, len(cumulative) - 1)]

        # Recommendation
        if break_even <= 3:
            rec = "fix_now"
        elif break_even <= 6:
            rec = "fix_soon"
        elif break_even <= 12:
            rec = "monitor"
        else:
            rec = "accept"

        return DebtProjection(
            item_name=item.name,
            month_0_cost=round(month_costs[0], 1),
            month_6_cost=round(month_costs[min(6, len(month_costs) - 1)], 1),
            month_12_cost=round(month_costs[min(12, len(month_costs) - 1)], 1),
            month_24_cost=round(month_costs[min(24, len(month_costs) - 1)], 1),
            break_even_months=round(break_even, 1) if break_even != float("inf") else -1,
            total_interest_12mo=round(interest_12, 1),
            recommendation=rec,
        )

    def _generate_warnings(self, items: list[DebtItem], ratio: float,
                           projections: list[DebtProjection]) -> list[str]:
        warnings = []
        if ratio > 0.2:
            warnings.append(f"Debt ratio {ratio:.0%} — over 20% of capacity on maintenance")
        fix_now = [p for p in projections if p.recommendation == "fix_now"]
        if fix_now:
            warnings.append(f"{len(fix_now)} items should be fixed immediately (break-even < 3 months)")
        critical = [i for i in items if i.severity == "critical"]
        if critical:
            warnings.append(f"{len(critical)} critical debt items")
        return warnings


def format_report(portfolio: DebtPortfolio) -> str:
    lines = [
        "# Tech Debt Interest Report",
        f"Monthly cost: {portfolio.total_monthly_cost:.0f}h | Fix cost: {portfolio.total_fix_cost:.0f}h",
        f"12mo interest: {portfolio.total_12mo_interest:.0f}h | Ratio: {portfolio.debt_ratio:.0%}",
        "",
    ]
    for p in portfolio.projections:
        lines.append(
            f"  [{p.recommendation}] {p.item_name}: "
            f"{p.month_0_cost:.0f}h/mo -> {p.month_12_cost:.0f}h/mo "
            f"(break-even: {p.break_even_months:.0f}mo)"
        )
    if portfolio.priority_queue:
        lines.append(f"\nPriority: {', '.join(portfolio.priority_queue)}")
    return "\n".join(lines)
