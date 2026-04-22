"""
Rate limiter — per-user token budgets and request throttling.

Uses in-memory sliding window. Resets on server restart.
Config: CODE_AGENTS_RATE_LIMIT_RPM (requests per minute, default: 60)
        CODE_AGENTS_RATE_LIMIT_TPD (tokens per day, default: 1000000)
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger("code_agents.core.rate_limiter")


@dataclass
class UserBudget:
    """Track usage for a single user/session."""
    requests: list[float] = field(default_factory=list)
    tokens_today: int = 0
    day_start: float = field(default_factory=time.time)

    def add_request(self, tokens: int = 0) -> None:
        now = time.time()
        self.requests.append(now)
        if now - self.day_start > 86400:
            self.tokens_today = 0
            self.day_start = now
        self.tokens_today += tokens

    def requests_in_window(self, window_seconds: int = 60) -> int:
        now = time.time()
        cutoff = now - window_seconds
        self.requests = [t for t in self.requests if t > cutoff]
        return len(self.requests)


class RateLimiter:
    """In-memory rate limiter with per-user budgets."""

    def __init__(self) -> None:
        self.budgets: dict[str, UserBudget] = defaultdict(UserBudget)
        self.rpm_limit = int(os.getenv("CODE_AGENTS_RATE_LIMIT_RPM", "60"))
        self.tpd_limit = int(os.getenv("CODE_AGENTS_RATE_LIMIT_TPD", "1000000"))

    def check(self, user_id: str = "default", superpower: bool = False) -> tuple[bool, str]:
        """Check if request is allowed. Returns (allowed, reason).

        superpower=True bypasses all rate limits.
        """
        if superpower:
            return True, "superpower"
        budget = self.budgets[user_id]
        rpm = budget.requests_in_window(60)
        if rpm >= self.rpm_limit:
            logger.warning("Rate limit hit for user=%s: %d/%d RPM", user_id, rpm, self.rpm_limit)
            return False, f"Rate limit exceeded: {rpm}/{self.rpm_limit} requests per minute"
        if budget.tokens_today >= self.tpd_limit:
            logger.warning("Daily token budget exceeded for user=%s: %d/%d", user_id, budget.tokens_today, self.tpd_limit)
            return False, f"Daily token budget exceeded: {budget.tokens_today:,}/{self.tpd_limit:,}"
        return True, "ok"

    def record(self, user_id: str = "default", tokens: int = 0) -> None:
        """Record a request."""
        self.budgets[user_id].add_request(tokens)

    def get_usage(self, user_id: str = "default") -> dict:
        """Get current usage stats."""
        budget = self.budgets[user_id]
        logger.debug("Usage stats for user=%s: rpm=%d, tokens_today=%d", user_id, budget.requests_in_window(60), budget.tokens_today)
        return {
            "rpm": budget.requests_in_window(60),
            "rpm_limit": self.rpm_limit,
            "tokens_today": budget.tokens_today,
            "tpd_limit": self.tpd_limit,
        }
