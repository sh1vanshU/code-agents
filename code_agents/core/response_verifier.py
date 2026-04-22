"""Response Verifier — auto-verify code-writer output via code-reviewer.

When enabled, code-writer responses containing code blocks are automatically
sent to code-reviewer for a quick review. Off by default, toggle with /verify.

Environment:
    CODE_AGENTS_AUTO_VERIFY=true   — enable at startup (default: false)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re

logger = logging.getLogger("code_agents.core.response_verifier")


class ResponseVerifier:
    """Auto-delegates code-writer responses to code-reviewer for verification."""

    def __init__(self):
        self.enabled = os.getenv("CODE_AGENTS_AUTO_VERIFY", "false").lower() == "true"
        self._cache: dict[str, str] = {}
        logger.info("ResponseVerifier initialized (enabled=%s)", self.enabled)

    def should_verify(self, agent_name: str, response: str) -> bool:
        """Check if response should be verified.

        Conditions:
        - Verifier is enabled
        - Agent is code-writer
        - Response contains code blocks (```)
        """
        if not self.enabled:
            return False
        if agent_name != "code-writer":
            return False
        if "```" not in response:
            return False
        logger.info("Response from %s qualifies for verification", agent_name)
        return True

    def build_verify_prompt(self, original_query: str, code_response: str) -> dict:
        """Build a review prompt for code-reviewer with cache key.

        Truncates inputs to keep the verification request concise.

        Returns dict with keys: ``prompt``, ``delegate_to``, ``cache_key``.
        """
        # Extract code blocks for cache key
        code_blocks = re.findall(r'```[\s\S]*?```', code_response)
        cache_key = (
            hashlib.md5("".join(code_blocks).encode()).hexdigest()
            if code_blocks
            else None
        )

        prompt = (
            "VERIFY this code written by code-writer agent:\n\n"
            f"User asked: {original_query[:500]}\n\n"
            f"Code written:\n{code_response[:3000]}\n\n"
            "Review for: bugs, security issues, edge cases, missing error handling.\n"
            "Be concise — 2-3 bullet points only. Say \"LGTM\" if no issues."
        )

        return {
            "prompt": prompt,
            "delegate_to": "code-reviewer",
            "cache_key": cache_key,
        }

    def get_cached_result(self, cache_key: str) -> str | None:
        """Return cached verification result if available."""
        return self._cache.get(cache_key)

    def cache_result(self, cache_key: str, result: str) -> None:
        """Store a verification result in the cache (bounded to 100 entries)."""
        self._cache[cache_key] = result
        # Keep cache bounded
        if len(self._cache) > 100:
            oldest = next(iter(self._cache))
            del self._cache[oldest]

    def toggle(self, on: bool | None = None) -> bool:
        """Toggle verification on/off. Returns new state."""
        if on is None:
            self.enabled = not self.enabled
        else:
            self.enabled = on
        logger.info("ResponseVerifier toggled to enabled=%s", self.enabled)
        return self.enabled


# Module-level lazy singleton
_verifier: ResponseVerifier | None = None


def get_verifier() -> ResponseVerifier:
    """Get or create the singleton ResponseVerifier (lazy)."""
    global _verifier
    if _verifier is None:
        _verifier = ResponseVerifier()
    return _verifier
