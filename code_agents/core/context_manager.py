"""
Smart Context Window — trims conversation context to prevent hallucination.

Auto-trims messages to keep last N user+assistant pairs plus system prompt,
first user message (task context), and any messages containing code blocks.
Configurable via CODE_AGENTS_CONTEXT_WINDOW env var (default: 5 pairs).
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from typing import Optional

logger = logging.getLogger("code_agents.core.context_manager")

# Words to ignore when extracting topic keywords
_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her",
    "us", "them", "my", "your", "his", "its", "our", "their",
    "this", "that", "these", "those", "what", "which", "who", "whom",
    "how", "when", "where", "why", "if", "then", "else", "so", "but",
    "and", "or", "not", "no", "yes", "just", "also", "very", "too",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "about", "like", "after", "before", "between", "through", "over",
    "please", "thanks", "thank", "ok", "okay", "sure", "right",
    "here", "there", "now", "then", "some", "any", "all", "each",
    "get", "got", "make", "made", "let", "know", "think", "want",
    "see", "look", "use", "try", "give", "tell", "say", "said",
})

# Minimum word length for topic keywords
_MIN_WORD_LEN = 3

# Pattern to detect code blocks in message content
_CODE_BLOCK_RE = re.compile(r"```")

# Pattern to detect skill-loaded messages (ephemeral — should be trimmed aggressively)
_SKILL_LOADED_RE = re.compile(r"^\[Skill loaded: ")

# Pattern to extract words (alphanumeric + underscores, for identifiers)
_WORD_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def _get_max_pairs() -> int:
    """Read max pairs from env, defaulting to 10.

    Multi-step CI/CD workflows need 8-10 turns of context to remember
    discovered job paths, branch names, build results, and user confirmations.
    """
    raw = os.getenv("CODE_AGENTS_CONTEXT_WINDOW", "10")
    try:
        val = int(raw)
        return max(val, 1)  # at least 1 pair
    except (ValueError, TypeError):
        return 10


def _has_code_block(msg: dict) -> bool:
    """Check if a message contains code blocks (```).

    Skill-loaded messages are excluded — they contain example ```bash blocks
    but should not be preserved since the skill body is ephemeral.
    """
    content = msg.get("content") or ""
    if isinstance(content, str) and _SKILL_LOADED_RE.search(content):
        return False  # skill bodies are ephemeral, don't preserve
    return bool(_CODE_BLOCK_RE.search(content))


class ContextManager:
    """Trims conversation context to keep context window manageable."""

    def __init__(self, max_pairs: Optional[int] = None):
        self.max_pairs = max_pairs if max_pairs is not None else _get_max_pairs()

    def trim_messages(self, messages: list[dict]) -> list[dict]:
        """Trim messages to keep context window manageable.

        Strategy:
        1. Always keep system messages
        2. Always keep the first user message (establishes task context)
        3. Always keep messages containing code blocks (```)
        4. Keep the last N user+assistant message pairs
        5. If trimming occurred, insert a summary of trimmed topics
        """
        if not messages:
            return messages

        # Filter out stale error responses
        _error_patterns = ["cursor-agent failed", "Claude CLI error", "[Error:", "Security command failed"]
        cleaned = []
        for m in messages:
            content = m.get("content", "") if isinstance(m.get("content"), str) else ""
            if m.get("role") == "assistant" and any(ep in content for ep in _error_patterns):
                cleaned.append({"role": "assistant", "content": "(previous response had an error — retrying)"})
                logger.debug("Stripped stale error from context: %s", content[:80])
            else:
                cleaned.append(m)
        messages = cleaned

        # Separate system messages from conversation messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        if not non_system:
            return messages

        # If within the window, no trimming needed
        # Count pairs: each user message starts a new pair
        user_count = sum(1 for m in non_system if m.get("role") == "user")
        if user_count <= self.max_pairs:
            return messages

        # Identify the first user message
        first_user_idx = None
        for i, m in enumerate(non_system):
            if m.get("role") == "user":
                first_user_idx = i
                break

        # Find the cut point: keep last N pairs from the end
        # Walk backwards to find where the Nth-from-last user message starts
        pair_count = 0
        keep_from_idx = len(non_system)
        for i in range(len(non_system) - 1, -1, -1):
            if non_system[i].get("role") == "user":
                pair_count += 1
                if pair_count >= self.max_pairs:
                    keep_from_idx = i
                    break

        # Messages to keep from the tail
        tail_msgs = non_system[keep_from_idx:]

        # Messages being trimmed (between first user msg and the tail)
        if first_user_idx is not None:
            trim_start = first_user_idx + 1
            # Also keep assistant response right after first user if exists
            if trim_start < len(non_system) and non_system[trim_start].get("role") == "assistant":
                first_pair_end = trim_start + 1
            else:
                first_pair_end = trim_start
        else:
            trim_start = 0
            first_pair_end = 0

        trimmed_msgs = non_system[first_pair_end:keep_from_idx]

        # Compact skill bodies in trimmed section (save ~1,500 tokens per skill)
        for i, m in enumerate(trimmed_msgs):
            content = m.get("content", "") if isinstance(m.get("content"), str) else ""
            if m.get("role") == "user" and _SKILL_LOADED_RE.search(content):
                skill_name = content.split("]")[0].split(": ")[-1] if "]" in content else "unknown"
                trimmed_msgs[i] = {"role": "user", "content": f"(Skill '{skill_name}' was loaded and executed)"}
                logger.debug("Compacted trimmed skill body: %s", skill_name)

        # Collect messages with code blocks from the trimmed section
        code_msgs = [m for m in trimmed_msgs if _has_code_block(m)]

        # Build the result
        result: list[dict] = list(system_msgs)

        # Add first user message (+ its assistant reply)
        if first_user_idx is not None:
            first_pair = non_system[first_user_idx:first_pair_end]
            # Only add if not already in the tail
            if keep_from_idx > first_user_idx:
                result.extend(first_pair)

        # Insert summary of trimmed content if there were trimmed messages
        if trimmed_msgs:
            topics = self._extract_topics(trimmed_msgs)
            summary_content = self._build_summary(len(trimmed_msgs), topics)
            result.append({"role": "system", "content": summary_content})

        # Add code-block messages from trimmed section (not already in tail)
        for cm in code_msgs:
            if cm not in tail_msgs:
                result.append(cm)

        # Add the tail (last N pairs)
        result.extend(tail_msgs)

        trimmed_count = len(messages) - len(result)
        if trimmed_count > 0:
            logger.info(
                "Context trimmed: %d messages removed, %d kept (max_pairs=%d, code_preserved=%d)",
                trimmed_count, len(result), self.max_pairs, len(code_msgs),
            )

        return result

    def _extract_topics(self, messages: list[dict]) -> list[str]:
        """Extract key topic keywords from messages for summary.

        Uses word frequency analysis, filtering out stop words and very
        short words. Returns up to 8 most common meaningful terms.
        """
        counter: Counter[str] = Counter()

        for msg in messages:
            content = msg.get("content") or ""
            # Remove code blocks to focus on natural language
            cleaned = re.sub(r"```[\s\S]*?```", "", content)
            words = _WORD_RE.findall(cleaned.lower())
            for w in words:
                if len(w) >= _MIN_WORD_LEN and w not in _STOP_WORDS:
                    counter[w] += 1

        # Return top keywords
        return [word for word, _ in counter.most_common(8)]

    def _build_summary(self, trimmed_count: int, topics: list[str]) -> str:
        """Build a summary message for trimmed context."""
        topic_str = ", ".join(topics) if topics else "general discussion"
        return (
            f"[Context trimmed: {trimmed_count} earlier messages removed to stay within context window. "
            f"Key topics discussed: {topic_str}]"
        )
