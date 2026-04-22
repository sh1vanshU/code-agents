"""Prompt Evolver — track user corrections and evolve agent prompts over time."""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.prompt_evolver")


@dataclass
class Correction:
    """A user correction to agent output."""
    timestamp: float = 0.0
    agent_name: str = ""
    original_output: str = ""
    corrected_output: str = ""
    correction_type: str = ""  # style, accuracy, format, scope, tone
    context: str = ""


@dataclass
class PromptPatch:
    """A suggested patch to an agent prompt."""
    agent_name: str = ""
    section: str = ""  # instruction, example, constraint, persona
    original_text: str = ""
    patched_text: str = ""
    reason: str = ""
    confidence: float = 0.0
    based_on_corrections: int = 0


@dataclass
class EvolutionReport:
    """Report of prompt evolution analysis."""
    agent_name: str = ""
    corrections_analyzed: int = 0
    patterns_found: list[dict] = field(default_factory=list)
    patches: list[PromptPatch] = field(default_factory=list)
    effectiveness_score: float = 0.0  # 0-1 how well current prompt handles corrections
    drift_areas: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


CORRECTION_CATEGORIES = {
    "style": ["formatting", "style", "format", "layout", "markdown", "indentation"],
    "accuracy": ["wrong", "incorrect", "error", "mistake", "inaccurate", "fix"],
    "scope": ["too much", "too little", "missing", "extra", "scope", "irrelevant"],
    "tone": ["too formal", "too casual", "tone", "voice", "friendly", "professional"],
    "format": ["json", "yaml", "table", "list", "code block", "structured"],
}


class PromptEvolver:
    """Evolves agent prompts based on user correction patterns."""

    def __init__(self, agent_name: str = ""):
        self.agent_name = agent_name
        self.corrections: list[Correction] = []

    def analyze(self, corrections: list[dict],
                current_prompt: str = "") -> EvolutionReport:
        """Analyze corrections and suggest prompt improvements."""
        logger.info("Analyzing %d corrections for agent '%s'", len(corrections), self.agent_name)

        self.corrections = [self._parse_correction(c) for c in corrections]
        self.corrections = [c for c in self.corrections if c.correction_type]

        # Phase 1: Identify patterns
        patterns = self._identify_patterns()
        logger.info("Found %d correction patterns", len(patterns))

        # Phase 2: Generate patches
        patches = self._generate_patches(patterns, current_prompt)

        # Phase 3: Score effectiveness
        effectiveness = self._score_effectiveness(patterns)

        # Phase 4: Identify drift areas
        drift = self._identify_drift(patterns)

        report = EvolutionReport(
            agent_name=self.agent_name,
            corrections_analyzed=len(self.corrections),
            patterns_found=patterns,
            patches=patches,
            effectiveness_score=round(effectiveness, 2),
            drift_areas=drift,
            warnings=self._generate_warnings(patterns, effectiveness),
        )
        logger.info("Evolution report: %d patches, effectiveness=%.2f", len(patches), effectiveness)
        return report

    def _parse_correction(self, raw: dict) -> Correction:
        """Parse raw correction dict."""
        correction = Correction(
            timestamp=raw.get("timestamp", time.time()),
            agent_name=raw.get("agent", self.agent_name),
            original_output=raw.get("original", ""),
            corrected_output=raw.get("corrected", ""),
            context=raw.get("context", ""),
        )
        correction.correction_type = self._classify_correction(correction)
        return correction

    def _classify_correction(self, correction: Correction) -> str:
        """Classify the type of correction."""
        text = f"{correction.original_output} {correction.corrected_output} {correction.context}".lower()
        best_cat = ""
        best_score = 0
        for category, keywords in CORRECTION_CATEGORIES.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_cat = category
        return best_cat or "accuracy"

    def _identify_patterns(self) -> list[dict]:
        """Identify recurring correction patterns."""
        type_counts: dict[str, int] = {}
        for c in self.corrections:
            type_counts[c.correction_type] = type_counts.get(c.correction_type, 0) + 1

        patterns = []
        for ctype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            if count >= 2:
                examples = [c for c in self.corrections if c.correction_type == ctype][:3]
                patterns.append({
                    "type": ctype,
                    "count": count,
                    "frequency": count / len(self.corrections) if self.corrections else 0,
                    "examples": [{"original": e.original_output[:100],
                                  "corrected": e.corrected_output[:100]} for e in examples],
                })
        return patterns

    def _generate_patches(self, patterns: list[dict], prompt: str) -> list[PromptPatch]:
        """Generate prompt patches from patterns."""
        patches = []
        for pattern in patterns:
            patch = self._pattern_to_patch(pattern, prompt)
            if patch:
                patches.append(patch)
        return patches

    def _pattern_to_patch(self, pattern: dict, prompt: str) -> Optional[PromptPatch]:
        """Convert a pattern into a prompt patch."""
        ptype = pattern["type"]
        count = pattern["count"]
        freq = pattern["frequency"]

        patch_templates = {
            "style": PromptPatch(
                section="instruction",
                patched_text="Follow the user's preferred formatting style consistently.",
                reason=f"Users corrected style {count} times ({freq:.0%} of corrections)",
                confidence=min(0.9, freq + 0.3),
            ),
            "accuracy": PromptPatch(
                section="constraint",
                patched_text="Verify all factual claims. When uncertain, state assumptions explicitly.",
                reason=f"Users corrected accuracy {count} times",
                confidence=min(0.9, freq + 0.2),
            ),
            "scope": PromptPatch(
                section="constraint",
                patched_text="Match response scope exactly to the question. Ask for clarification if scope is ambiguous.",
                reason=f"Users corrected scope {count} times",
                confidence=min(0.9, freq + 0.2),
            ),
            "tone": PromptPatch(
                section="persona",
                patched_text="Adjust tone to match user preference. Default to professional but approachable.",
                reason=f"Users corrected tone {count} times",
                confidence=min(0.8, freq + 0.2),
            ),
            "format": PromptPatch(
                section="instruction",
                patched_text="Use structured output formats (JSON, tables, lists) when appropriate.",
                reason=f"Users corrected format {count} times",
                confidence=min(0.9, freq + 0.3),
            ),
        }

        patch = patch_templates.get(ptype)
        if patch:
            patch.agent_name = self.agent_name
            patch.based_on_corrections = count
        return patch

    def _score_effectiveness(self, patterns: list[dict]) -> float:
        """Score how effective the current prompt is (0-1)."""
        if not self.corrections:
            return 1.0
        # Fewer repeated correction types = more effective
        pattern_count = len(patterns)
        if pattern_count == 0:
            return 0.9
        total = len(self.corrections)
        repeated = sum(p["count"] for p in patterns if p["count"] > 1)
        return max(0.0, 1.0 - (repeated / total))

    def _identify_drift(self, patterns: list[dict]) -> list[str]:
        """Identify areas where the prompt is drifting from user expectations."""
        drift = []
        for p in patterns:
            if p["frequency"] > 0.3:
                drift.append(f"{p['type']} corrections are {p['frequency']:.0%} of all corrections")
        return drift

    def _generate_warnings(self, patterns: list[dict], effectiveness: float) -> list[str]:
        """Generate warnings."""
        warnings = []
        if effectiveness < 0.5:
            warnings.append("Low effectiveness — prompt needs significant revision")
        high_freq = [p for p in patterns if p["frequency"] > 0.4]
        if high_freq:
            warnings.append(f"Dominant correction type: {high_freq[0]['type']} ({high_freq[0]['frequency']:.0%})")
        return warnings


def format_report(report: EvolutionReport) -> str:
    """Format evolution report."""
    lines = [
        "# Prompt Evolution Report",
        f"Agent: {report.agent_name}",
        f"Corrections: {report.corrections_analyzed} | Effectiveness: {report.effectiveness_score:.0%}",
        "",
    ]
    if report.patches:
        lines.append("## Suggested Patches")
        for p in report.patches:
            lines.append(f"  [{p.section}] {p.patched_text}")
            lines.append(f"    Reason: {p.reason}")
    return "\n".join(lines)
