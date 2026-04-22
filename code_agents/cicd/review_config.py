"""
Review configuration — per-repo review rules.

Loads from .code-agents/review.yaml. Controls strictness,
ignore patterns, focus areas, and auto-approve paths.
"""
from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("code_agents.review_config")


@dataclass
class ReviewConfig:
    strictness: str = "standard"  # strict, standard, lenient
    ignore_patterns: list[str] = field(default_factory=list)
    focus_areas: list[str] = field(default_factory=list)
    max_findings: int = 20
    auto_approve: list[str] = field(default_factory=list)
    block_severity: str = "HIGH"


def load_review_config(repo_path: str) -> ReviewConfig:
    config_path = Path(repo_path) / ".code-agents" / "review.yaml"
    if not config_path.is_file():
        return ReviewConfig()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return ReviewConfig(
            strictness=raw.get("strictness", "standard"),
            ignore_patterns=raw.get("ignore_patterns", []),
            focus_areas=raw.get("focus_areas", []),
            max_findings=int(raw.get("max_findings", 20)),
            auto_approve=raw.get("auto_approve", []),
            block_severity=raw.get("block_severity", "HIGH"),
        )
    except Exception as e:
        logger.warning("Failed to load review.yaml: %s", e)
        return ReviewConfig()


def should_skip_file(file_path: str, config: ReviewConfig) -> bool:
    for pattern in config.ignore_patterns:
        if fnmatch.fnmatch(file_path, pattern):
            return True
    return False


def is_auto_approve(changed_files: list[str], config: ReviewConfig) -> bool:
    if not config.auto_approve:
        return False
    for f in changed_files:
        matched = any(fnmatch.fnmatch(f, p) for p in config.auto_approve)
        if not matched:
            return False
    return True


def format_config_for_prompt(config: ReviewConfig) -> str:
    if config.strictness == "standard" and not config.focus_areas:
        return ""
    lines = ["Review config:"]
    lines.append(f"  Strictness: {config.strictness}")
    if config.focus_areas:
        lines.append(f"  Focus: {', '.join(config.focus_areas)}")
    if config.ignore_patterns:
        lines.append(f"  Ignore: {', '.join(config.ignore_patterns[:5])}")
    lines.append(f"  Max findings: {config.max_findings}")
    lines.append(f"  Block severity: {config.block_severity}")
    return "\n".join(lines)
