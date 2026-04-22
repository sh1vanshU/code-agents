"""Auto plan-mode detection — detect complex tasks and suggest plan mode."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("code_agents.chat.chat_complexity")

# Patterns that indicate a complex, multi-step task
_COMPLEXITY_PATTERNS: list[tuple[str, int]] = [
    # Multi-file / large-scope keywords (weight)
    (r"\brefactor\b", 3),
    (r"\bmigrat(e|ion)\b", 3),
    (r"\brewrite\b", 3),
    (r"\bredesign\b", 3),
    (r"\brearchitect\b", 4),
    (r"\boverhaul\b", 3),
    (r"\bconvert all\b", 3),
    (r"\bimplement(?:\s+all|\s+the\s+following|\s+these)\b", 3),
    (r"\badd support for\b", 2),
    (r"\bupgrade\b", 2),
    (r"\breplace\b.*\bwith\b", 2),
    # Multi-step indicators
    (r"\bstep[s]?\s*[:\d]", 2),
    (r"\b(?:first|then|next|finally|after that)\b", 1),
    (r"\band\s+(?:also|then)\b", 1),
    # Scope indicators
    (r"\bacross\s+(?:all|the|every)\b", 2),
    (r"\bevery\s+(?:file|module|component|test|endpoint)\b", 2),
    (r"\ball\s+(?:files|modules|components|tests|endpoints|agents)\b", 2),
    (r"\bmultiple\s+(?:files|modules|components)\b", 2),
    # Explicit complexity markers
    (r"\bcomplete\s+(?:rewrite|overhaul|redesign)\b", 4),
    (r"\bfull\s+(?:rewrite|pipeline|stack|implementation)\b", 3),
    (r"\bend.to.end\b", 2),
    (r"\bfrom\s+scratch\b", 3),
    # CI/CD multi-step pipelines
    (r"\bbuild\s+and\s+deploy\b", 4),
    (r"\bdeploy\b.*\bverify\b", 4),
    (r"\bbuild.*deploy.*verify\b", 5),
    (r"\bbuild.*deploy.*argocd\b", 5),
    (r"\bpipeline\b", 2),
    (r"\brollback\b", 2),
    # File count mentions
    (r"\b\d{2,}\s+files?\b", 2),  # "15 files", "20 files"
]

# Compiled once at module load
_COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), w) for p, w in _COMPLEXITY_PATTERNS]

# Threshold: sum of matched weights must exceed this to suggest plan mode
COMPLEXITY_THRESHOLD = 4


def estimate_complexity(user_input: str) -> tuple[int, list[str]]:
    """Score the complexity of a user message.

    Returns (score, list_of_matched_reasons).
    """
    score = 0
    reasons: list[str] = []
    for pattern, weight in _COMPILED_PATTERNS:
        m = pattern.search(user_input)
        if m:
            score += weight
            reasons.append(m.group(0))
    # Long messages (>300 chars) get a bonus — likely detailed multi-step request
    if len(user_input) > 300:
        score += 1
    if len(user_input) > 600:
        score += 1
    return score, reasons


def should_suggest_plan_mode(user_input: str) -> tuple[bool, int, list[str]]:
    """Check if a user message is complex enough to suggest plan mode.

    Returns (should_suggest, score, reasons).
    """
    score, reasons = estimate_complexity(user_input)
    return score >= COMPLEXITY_THRESHOLD, score, reasons
