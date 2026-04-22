"""Tests for techdebt_interest.py — compound cost calculator for tech debt."""

import pytest

from code_agents.domain.techdebt_interest import (
    TechDebtInterest,
    DebtPortfolio,
    DebtProjection,
    format_report,
)


@pytest.fixture
def calculator():
    return TechDebtInterest(team_capacity_hours_per_month=160, hourly_rate=100)


SAMPLE_DEBT = [
    {"name": "Legacy auth module", "category": "code", "monthly_cost": 10,
     "fix_cost": 40, "growth_rate": 0.1, "severity": "high", "teams": 2},
    {"name": "Missing test coverage", "category": "test", "monthly_cost": 5,
     "fix_cost": 80, "growth_rate": 0.03, "severity": "medium"},
    {"name": "Outdated docs", "category": "docs", "monthly_cost": 2,
     "fix_cost": 16, "growth_rate": 0.02, "severity": "low"},
]


class TestProjection:
    def test_costs_increase(self, calculator):
        from code_agents.domain.techdebt_interest import DebtItem
        item = DebtItem(name="test", current_cost_hours_per_month=10,
                        fix_cost_hours=40, growth_rate=0.1, affected_teams=1)
        proj = calculator._project(item, 24)
        assert proj.month_12_cost > proj.month_0_cost

    def test_break_even(self, calculator):
        from code_agents.domain.techdebt_interest import DebtItem
        item = DebtItem(name="quick_fix", current_cost_hours_per_month=20,
                        fix_cost_hours=20, growth_rate=0.1, affected_teams=1)
        proj = calculator._project(item, 24)
        assert proj.break_even_months <= 3

    def test_recommendation_fix_now(self, calculator):
        from code_agents.domain.techdebt_interest import DebtItem
        item = DebtItem(name="urgent", current_cost_hours_per_month=50,
                        fix_cost_hours=10, growth_rate=0.1, affected_teams=1)
        proj = calculator._project(item, 24)
        assert proj.recommendation == "fix_now"


class TestAnalyze:
    def test_full_analysis(self, calculator):
        portfolio = calculator.analyze(SAMPLE_DEBT)
        assert isinstance(portfolio, DebtPortfolio)
        assert portfolio.total_monthly_cost > 0
        assert portfolio.total_fix_cost > 0

    def test_debt_ratio(self, calculator):
        portfolio = calculator.analyze(SAMPLE_DEBT)
        assert portfolio.debt_ratio > 0

    def test_priority_queue(self, calculator):
        portfolio = calculator.analyze(SAMPLE_DEBT)
        assert len(portfolio.priority_queue) >= 1

    def test_12mo_interest(self, calculator):
        portfolio = calculator.analyze(SAMPLE_DEBT)
        assert portfolio.total_12mo_interest > 0

    def test_format_report(self, calculator):
        portfolio = calculator.analyze(SAMPLE_DEBT)
        text = format_report(portfolio)
        assert "Tech Debt" in text

    def test_empty_debt(self, calculator):
        portfolio = calculator.analyze([])
        assert portfolio.total_monthly_cost == 0
