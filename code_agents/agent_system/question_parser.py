"""Question parser — detect numbered/lettered questions in agent responses.

Extracts structured questions from free-form response text so they can be
presented in an interactive tabbed questionnaire UI instead of requiring
plain-text answers.

Patterns detected:
  - ``Q1: question text`` / ``Question 1: text``
  - Numbered options: ``1. option`` / ``1) option`` / ``1 — option``
  - Lettered options: ``a) option`` / ``a. option``
  - Fallback: paragraph ending with ``?`` followed by a numbered list
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("code_agents.agent_system.question_parser")

# --- Regex patterns ---

# Strip fenced code blocks to avoid false positives
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

# Q1: / Q2: / Question 1: headers (handles ▎ prefix, > prefix, bold markers)
_Q_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(?:[▎│\|]\s*)?(?:>\s*)?(?:\*{0,2})(?:Q|Question)\s*(\d+)\s*[:.]\s*(.+?)(?=\n|$)",
    re.IGNORECASE,
)

# Numbered options: 1. / 1) / 1 — / 1 - / - 1 — / • 1 → / • 1 —
_NUMBERED_OPT_RE = re.compile(
    r"^\s*(?:[▎│\|•·●]\s*)?(?:-\s*)?(\d+)\s*[.)\u2014\-—→←]+\s*(.+?)$",
    re.MULTILINE,
)

# Lettered options: a) / a. / a — / A → / • A →
_LETTERED_OPT_RE = re.compile(
    r"^\s*(?:[▎│\|•·●]\s*)?([a-zA-Z])\s*[.)\u2014\-—→←]+\s*(.+?)$",
    re.MULTILINE,
)

# Fallback: line ending with ? (potential question without Qn: prefix)
_QUESTION_LINE_RE = re.compile(
    r"(?:^|\n)\s*(.+?\?)\s*$",
    re.MULTILINE,
)


def parse_questions(response_text: str) -> list[dict]:
    """Extract structured questions from agent response text.

    Returns:
        List of ``{"question": str, "options": list[str], "default": 0}`` dicts.
        Empty list if no interactive questions detected.
    """
    if not response_text:
        return []

    # Strip code blocks to avoid false positives
    cleaned = _CODE_BLOCK_RE.sub("", response_text)

    # Try Qn: header pattern first
    questions = _extract_q_header_questions(cleaned)
    if questions:
        logger.debug("Detected %d Q-header questions", len(questions))
        return questions

    # Fallback: question lines followed by option lists
    questions = _extract_freeform_questions(cleaned)
    if questions:
        logger.debug("Detected %d freeform questions", len(questions))
        return questions

    return []


def _extract_q_header_questions(text: str) -> list[dict]:
    """Extract questions using Q1:/Question 1: headers."""
    headers = list(_Q_HEADER_RE.finditer(text))
    if not headers:
        return []

    questions = []
    for i, match in enumerate(headers):
        q_text = match.group(2).strip()
        # Get text between this header and the next (or end)
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end]

        options = _extract_options(body)
        if len(options) >= 2:
            questions.append({
                "question": q_text,
                "options": options,
                "default": 0,
            })

    return questions


def _extract_freeform_questions(text: str) -> list[dict]:
    """Fallback: find lines ending with ? followed by numbered/lettered options."""
    q_lines = list(_QUESTION_LINE_RE.finditer(text))
    if not q_lines:
        return []

    questions = []
    for i, match in enumerate(q_lines):
        q_text = match.group(1).strip()
        # Skip very short questions (likely not real questions)
        if len(q_text) < 10:
            continue

        # Look for options in the text after the question line
        start = match.end()
        # Limit to next 500 chars or next question line
        end = q_lines[i + 1].start() if i + 1 < len(q_lines) else min(start + 500, len(text))
        body = text[start:end]

        options = _extract_options(body)
        if len(options) >= 2:
            questions.append({
                "question": q_text,
                "options": options,
                "default": 0,
            })

    return questions


def _extract_options(text_block: str) -> list[str]:
    """Extract numbered or lettered options from a text block."""
    # Try numbered first (more common)
    numbered = list(_NUMBERED_OPT_RE.finditer(text_block))
    if len(numbered) >= 2:
        return [m.group(2).strip() for m in numbered]

    # Try lettered
    lettered = list(_LETTERED_OPT_RE.finditer(text_block))
    if len(lettered) >= 2:
        return [m.group(2).strip() for m in lettered]

    return []
