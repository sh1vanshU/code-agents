"""Tests for rate_limiter.py — per-user token budgets and request throttling."""

import time
from unittest.mock import patch

import pytest

from code_agents.core.rate_limiter import UserBudget, RateLimiter


# ---------------------------------------------------------------------------
# UserBudget
# ---------------------------------------------------------------------------

class TestUserBudget:
    def test_default_fields(self):
        b = UserBudget()
        assert b.requests == []
        assert b.tokens_today == 0
        assert b.day_start > 0

    def test_add_request_increments_tokens(self):
        b = UserBudget()
        b.add_request(tokens=100)
        assert b.tokens_today == 100
        assert len(b.requests) == 1

    def test_add_request_multiple(self):
        b = UserBudget()
        b.add_request(50)
        b.add_request(30)
        assert b.tokens_today == 80
        assert len(b.requests) == 2

    def test_add_request_resets_daily(self):
        b = UserBudget()
        b.add_request(500)
        # Simulate day_start was more than 24h ago
        b.day_start = time.time() - 90000
        b.add_request(100)
        # After reset, tokens_today should be just the new 100
        assert b.tokens_today == 100

    def test_requests_in_window_filters_old(self):
        b = UserBudget()
        now = time.time()
        b.requests = [now - 120, now - 90, now - 30, now - 5]
        count = b.requests_in_window(60)
        assert count == 2  # only last two within 60s window

    def test_requests_in_window_empty(self):
        b = UserBudget()
        assert b.requests_in_window(60) == 0


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_default_limits(self):
        with patch.dict("os.environ", {}, clear=False):
            rl = RateLimiter()
        assert rl.rpm_limit == 60
        assert rl.tpd_limit == 1_000_000

    def test_custom_limits_from_env(self):
        with patch.dict("os.environ", {
            "CODE_AGENTS_RATE_LIMIT_RPM": "10",
            "CODE_AGENTS_RATE_LIMIT_TPD": "5000",
        }):
            rl = RateLimiter()
        assert rl.rpm_limit == 10
        assert rl.tpd_limit == 5000

    def test_check_allows_fresh_user(self):
        rl = RateLimiter()
        allowed, reason = rl.check("user1")
        assert allowed is True
        assert reason == "ok"

    def test_check_superpower_always_allowed(self):
        rl = RateLimiter()
        # Fill up to exceed limits
        rl.budgets["user1"].tokens_today = 99_999_999
        allowed, reason = rl.check("user1", superpower=True)
        assert allowed is True
        assert reason == "superpower"

    def test_check_rpm_exceeded(self):
        with patch.dict("os.environ", {"CODE_AGENTS_RATE_LIMIT_RPM": "3", "CODE_AGENTS_RATE_LIMIT_TPD": "1000000"}):
            rl = RateLimiter()
        now = time.time()
        rl.budgets["u"].requests = [now - 10, now - 5, now - 1]
        allowed, reason = rl.check("u")
        assert allowed is False
        assert "Rate limit exceeded" in reason

    def test_check_tpd_exceeded(self):
        with patch.dict("os.environ", {"CODE_AGENTS_RATE_LIMIT_RPM": "60", "CODE_AGENTS_RATE_LIMIT_TPD": "100"}):
            rl = RateLimiter()
        rl.budgets["u"].tokens_today = 200
        allowed, reason = rl.check("u")
        assert allowed is False
        assert "Daily token budget exceeded" in reason

    def test_record_adds_to_budget(self):
        rl = RateLimiter()
        rl.record("u1", tokens=50)
        assert rl.budgets["u1"].tokens_today == 50
        assert len(rl.budgets["u1"].requests) == 1

    def test_record_default_user(self):
        rl = RateLimiter()
        rl.record(tokens=10)
        assert rl.budgets["default"].tokens_today == 10

    def test_get_usage_returns_dict(self):
        rl = RateLimiter()
        rl.record("u1", tokens=75)
        usage = rl.get_usage("u1")
        assert usage["tokens_today"] == 75
        assert usage["rpm_limit"] == rl.rpm_limit
        assert usage["tpd_limit"] == rl.tpd_limit
        assert "rpm" in usage

    def test_get_usage_default_user(self):
        rl = RateLimiter()
        usage = rl.get_usage()
        assert usage["tokens_today"] == 0
        assert usage["rpm"] == 0

    def test_separate_users_isolated(self):
        rl = RateLimiter()
        rl.record("alice", tokens=100)
        rl.record("bob", tokens=200)
        assert rl.get_usage("alice")["tokens_today"] == 100
        assert rl.get_usage("bob")["tokens_today"] == 200
