"""Spec-to-Implementation Validator — reads PRD/Jira ticket, compares against
implementation, flags gaps and deviations.

Pure code scanning for evidence. Jira fetch optional (graceful fallback).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.testing.spec_validator")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SpecRequirement:
    """A single requirement extracted from a spec/PRD/Jira ticket."""
    id: str
    description: str
    category: str  # "functional", "nonfunctional", "edge_case"
    source: str  # "jira", "prd", "manual"


@dataclass
class ImplementationEvidence:
    """Evidence that a requirement is (partially) implemented."""
    requirement_id: str
    file: str
    line: int
    code_snippet: str
    confidence: float  # 0.0 – 1.0


@dataclass
class SpecGap:
    """Gap analysis result for a single requirement."""
    requirement: SpecRequirement
    status: str  # "implemented", "partial", "missing", "deviated"
    evidence: list[ImplementationEvidence] = field(default_factory=list)
    notes: str = ""


@dataclass
class SpecReport:
    """Full validation report."""
    requirements: list[SpecRequirement]
    gaps: list[SpecGap]
    coverage: float  # % of requirements implemented
    missing: list[str]  # requirement ids
    deviated: list[str]  # requirement ids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_STORY_RE = re.compile(
    r"[Aa]s\s+(?:a|an)\s+(.+?),?\s+I\s+want\s+(.+?)(?:\s+so\s+that\s+(.+))?$",
    re.MULTILINE,
)
_GIVEN_WHEN_THEN_RE = re.compile(
    r"(?:Given|When|Then)\s+(.+)",
    re.MULTILINE,
)
_NUMBERED_LIST_RE = re.compile(
    r"^\s*(?:\d+[\.\)]\s*|-\s*|\*\s*)(.+)$",
    re.MULTILINE,
)
_ACCEPTANCE_HEADER_RE = re.compile(
    r"(?:acceptance\s+criteria|requirements?|specification|acceptance|criteria)",
    re.IGNORECASE,
)
_KEYWORD_STOP = {"the", "a", "an", "is", "are", "to", "in", "of", "and", "or", "for", "with", "on", "at", "by", "it", "be", "as", "that", "this", "from"}


def _extract_keywords(text: str) -> list[str]:
    """Pull meaningful keywords from a requirement description."""
    words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text)
    seen: set[str] = set()
    keywords: list[str] = []
    for w in words:
        low = w.lower()
        if low not in _KEYWORD_STOP and low not in seen:
            seen.add(low)
            keywords.append(low)
    return keywords[:12]  # cap to avoid huge search space


def _to_snake(text: str) -> str:
    """Convert natural language phrase to snake_case for code matching."""
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", "", text)
    parts = cleaned.lower().split()
    parts = [p for p in parts if p not in _KEYWORD_STOP]
    return "_".join(parts[:5])


def _grep_cwd(pattern: str, cwd: str, max_results: int = 10) -> list[dict]:
    """Run a case-insensitive grep in the codebase directory and return matches."""
    hits: list[dict] = []
    if not pattern or len(pattern) < 3:
        return hits

    try:
        result = subprocess.run(
            ["grep", "-rin", "--include=*.py", "--include=*.js", "--include=*.ts",
             "--include=*.java", "--include=*.go", "--include=*.rb",
             "-l", pattern, cwd],
            capture_output=True, text=True, timeout=15, cwd=cwd,
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        for fpath in files[:max_results]:
            # Get the matching line
            try:
                line_result = subprocess.run(
                    ["grep", "-in", pattern, fpath],
                    capture_output=True, text=True, timeout=5, cwd=cwd,
                )
                for line_out in line_result.stdout.strip().split("\n")[:3]:
                    if ":" in line_out:
                        parts = line_out.split(":", 1)
                        try:
                            lineno = int(parts[0])
                        except ValueError:
                            lineno = 0
                        snippet = parts[1].strip() if len(parts) > 1 else ""
                        rel_path = os.path.relpath(fpath, cwd) if os.path.isabs(fpath) else fpath
                        hits.append({
                            "file": rel_path,
                            "line": lineno,
                            "snippet": snippet[:200],
                        })
            except (subprocess.TimeoutExpired, OSError):
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.debug("grep failed for pattern %r: %s", pattern, exc)

    return hits[:max_results]


# ---------------------------------------------------------------------------
# SpecValidator
# ---------------------------------------------------------------------------

class SpecValidator:
    """Validates spec requirements against the codebase implementation."""

    def __init__(self, cwd: str):
        self.cwd = os.path.abspath(cwd)
        logger.info("SpecValidator initialised for %s", self.cwd)

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def validate(
        self,
        spec_text: str = "",
        jira_key: str = "",
        prd_file: str = "",
    ) -> SpecReport:
        """Run full spec-to-implementation validation.

        1. Extract requirements from spec/Jira/PRD
        2. Search codebase for evidence of each requirement
        3. Classify: implemented, partial, missing, deviated
        """
        text = self._gather_text(spec_text, jira_key, prd_file)
        if not text.strip():
            logger.warning("No spec text provided or fetched.")
            return SpecReport(
                requirements=[], gaps=[], coverage=0.0, missing=[], deviated=[],
            )

        requirements = self._extract_requirements(text)
        logger.info("Extracted %d requirements", len(requirements))

        gaps: list[SpecGap] = []
        for req in requirements:
            evidence = self._search_implementation(req)
            gap = self._classify_gap(req, evidence)
            gaps.append(gap)

        implemented = sum(1 for g in gaps if g.status == "implemented")
        coverage = (implemented / len(requirements) * 100) if requirements else 0.0
        missing_ids = [g.requirement.id for g in gaps if g.status == "missing"]
        deviated_ids = [g.requirement.id for g in gaps if g.status == "deviated"]

        report = SpecReport(
            requirements=requirements,
            gaps=gaps,
            coverage=round(coverage, 1),
            missing=missing_ids,
            deviated=deviated_ids,
        )
        logger.info(
            "Validation complete: %.1f%% coverage, %d missing, %d deviated",
            report.coverage, len(missing_ids), len(deviated_ids),
        )
        return report

    # -------------------------------------------------------------------
    # Text gathering
    # -------------------------------------------------------------------

    def _gather_text(self, spec_text: str, jira_key: str, prd_file: str) -> str:
        """Collect spec text from all provided sources."""
        parts: list[str] = []
        if spec_text:
            parts.append(spec_text)
        if prd_file:
            parts.append(self._read_prd(prd_file))
        if jira_key:
            parts.append(self._fetch_jira_spec(jira_key))
        return "\n\n".join(parts)

    def _read_prd(self, prd_file: str) -> str:
        """Read a PRD file from disk."""
        path = Path(prd_file)
        if not path.is_absolute():
            path = Path(self.cwd) / prd_file
        try:
            text = path.read_text(encoding="utf-8")
            logger.info("Read PRD from %s (%d chars)", path, len(text))
            return text
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Failed to read PRD file %s: %s", path, exc)
            return ""

    def _fetch_jira_spec(self, key: str) -> str:
        """Fetch Jira ticket description + acceptance criteria.

        Uses JIRA_URL / JIRA_EMAIL / JIRA_TOKEN env vars.
        Gracefully returns empty string on failure.
        """
        jira_url = os.environ.get("JIRA_URL", "").rstrip("/")
        jira_email = os.environ.get("JIRA_EMAIL", "")
        jira_token = os.environ.get("JIRA_TOKEN", "")

        if not jira_url or not jira_email or not jira_token:
            logger.info("Jira env vars not set — skipping Jira fetch for %s", key)
            return ""

        import urllib.request
        import base64

        api_url = f"{jira_url}/rest/api/2/issue/{key}"
        auth = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
        }

        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            fields = data.get("fields", {})
            parts: list[str] = []
            summary = fields.get("summary", "")
            if summary:
                parts.append(f"Summary: {summary}")
            desc = fields.get("description", "") or ""
            if desc:
                parts.append(desc)
            # Acceptance criteria (custom field — varies by Jira instance)
            for fk, fv in fields.items():
                if isinstance(fv, str) and _ACCEPTANCE_HEADER_RE.search(fk):
                    parts.append(fv)
            text = "\n\n".join(parts)
            logger.info("Fetched Jira %s (%d chars)", key, len(text))
            return text
        except Exception as exc:
            logger.warning("Failed to fetch Jira ticket %s: %s", key, exc)
            return ""

    # -------------------------------------------------------------------
    # Requirement extraction
    # -------------------------------------------------------------------

    def _extract_requirements(self, text: str) -> list[SpecRequirement]:
        """Parse requirements from spec text.

        Handles:
        - User stories ("As a user, I want X so that Y")
        - BDD/Gherkin ("Given/When/Then")
        - Numbered lists and bullet points
        - Acceptance criteria sections
        """
        requirements: list[SpecRequirement] = []
        seen_desc: set[str] = set()
        req_counter = 0

        # 1) User stories
        for m in _USER_STORY_RE.finditer(text):
            desc = m.group(0).strip()
            if desc and desc not in seen_desc:
                seen_desc.add(desc)
                req_counter += 1
                requirements.append(SpecRequirement(
                    id=f"REQ-{req_counter}",
                    description=desc,
                    category="functional",
                    source="manual",
                ))

        # 2) Given/When/Then blocks
        gwt_lines: list[str] = []
        for m in _GIVEN_WHEN_THEN_RE.finditer(text):
            gwt_lines.append(m.group(0).strip())

        if gwt_lines:
            # Group consecutive GWT lines into scenarios
            current: list[str] = []
            for line in gwt_lines:
                current.append(line)
                if line.lower().startswith("then"):
                    desc = " ".join(current)
                    if desc not in seen_desc:
                        seen_desc.add(desc)
                        req_counter += 1
                        requirements.append(SpecRequirement(
                            id=f"REQ-{req_counter}",
                            description=desc,
                            category="functional",
                            source="manual",
                        ))
                    current = []
            # leftover
            if current:
                desc = " ".join(current)
                if desc not in seen_desc:
                    seen_desc.add(desc)
                    req_counter += 1
                    requirements.append(SpecRequirement(
                        id=f"REQ-{req_counter}",
                        description=desc,
                        category="edge_case",
                        source="manual",
                    ))

        # 3) Numbered / bullet lists
        in_acceptance = False
        for line in text.split("\n"):
            stripped = line.strip()
            if _ACCEPTANCE_HEADER_RE.search(stripped):
                in_acceptance = True
                continue
            if in_acceptance and not stripped:
                in_acceptance = False
                continue

            m = _NUMBERED_LIST_RE.match(line)
            if m:
                desc = m.group(1).strip()
                # Skip very short items or duplicates
                if len(desc) < 10 or desc in seen_desc:
                    continue
                # Skip items that were already captured as user stories
                if any(desc in r.description for r in requirements):
                    continue
                seen_desc.add(desc)
                req_counter += 1
                cat = "functional"
                desc_lower = desc.lower()
                if any(kw in desc_lower for kw in ("performance", "latency", "uptime", "sla", "security", "scalab")):
                    cat = "nonfunctional"
                elif any(kw in desc_lower for kw in ("edge", "error", "invalid", "empty", "null", "timeout", "fail")):
                    cat = "edge_case"
                requirements.append(SpecRequirement(
                    id=f"REQ-{req_counter}",
                    description=desc,
                    category=cat,
                    source="manual",
                ))

        logger.debug("Extracted %d requirements from text", len(requirements))
        return requirements

    # -------------------------------------------------------------------
    # Implementation search
    # -------------------------------------------------------------------

    def _search_implementation(self, req: SpecRequirement) -> list[ImplementationEvidence]:
        """Search the codebase for evidence of a requirement's implementation."""
        evidence: list[ImplementationEvidence] = []
        keywords = _extract_keywords(req.description)
        snake = _to_snake(req.description)

        # Strategy 1: keyword search (try pairs for precision)
        if len(keywords) >= 2:
            for i in range(min(len(keywords) - 1, 4)):
                pattern = keywords[i]
                hits = _grep_cwd(pattern, self.cwd, max_results=5)
                for hit in hits:
                    # Boost confidence if multiple keywords found in same snippet
                    snippet_lower = hit["snippet"].lower()
                    matches = sum(1 for kw in keywords if kw in snippet_lower)
                    conf = min(0.3 + 0.15 * matches, 0.95)
                    evidence.append(ImplementationEvidence(
                        requirement_id=req.id,
                        file=hit["file"],
                        line=hit["line"],
                        code_snippet=hit["snippet"],
                        confidence=round(conf, 2),
                    ))

        # Strategy 2: snake_case function name match
        if snake and len(snake) > 5:
            hits = _grep_cwd(snake, self.cwd, max_results=5)
            for hit in hits:
                evidence.append(ImplementationEvidence(
                    requirement_id=req.id,
                    file=hit["file"],
                    line=hit["line"],
                    code_snippet=hit["snippet"],
                    confidence=0.75,
                ))

        # Strategy 3: test name matching (test_should_X, test_X)
        test_pattern = f"test.*{'.*'.join(keywords[:3])}" if len(keywords) >= 2 else ""
        if test_pattern and len(test_pattern) > 8:
            # Search only in test files
            hits = _grep_cwd(test_pattern, self.cwd, max_results=3)
            for hit in hits:
                evidence.append(ImplementationEvidence(
                    requirement_id=req.id,
                    file=hit["file"],
                    line=hit["line"],
                    code_snippet=hit["snippet"],
                    confidence=0.7,
                ))

        # Deduplicate by file+line
        seen: set[tuple[str, int]] = set()
        unique: list[ImplementationEvidence] = []
        for ev in evidence:
            key = (ev.file, ev.line)
            if key not in seen:
                seen.add(key)
                unique.append(ev)

        # Sort by confidence descending
        unique.sort(key=lambda e: e.confidence, reverse=True)
        return unique[:15]  # cap total evidence per requirement

    # -------------------------------------------------------------------
    # Classification
    # -------------------------------------------------------------------

    def _classify_gap(
        self,
        req: SpecRequirement,
        evidence: list[ImplementationEvidence],
    ) -> SpecGap:
        """Classify a requirement as implemented / partial / missing / deviated."""
        if not evidence:
            return SpecGap(
                requirement=req,
                status="missing",
                evidence=[],
                notes="No matching code found in codebase",
            )

        max_conf = max(e.confidence for e in evidence)
        high_conf = [e for e in evidence if e.confidence >= 0.6]
        has_test = any("test" in e.file.lower() for e in evidence)

        # Deviation detection: check if code contradicts the requirement
        keywords = _extract_keywords(req.description)
        negation_keywords = {"not", "no", "never", "disable", "skip", "remove", "delete"}
        deviation_score = 0
        for ev in high_conf:
            snippet_words = set(ev.code_snippet.lower().split())
            if snippet_words & negation_keywords and any(kw in ev.code_snippet.lower() for kw in keywords[:3]):
                deviation_score += 1

        if deviation_score >= 2:
            return SpecGap(
                requirement=req,
                status="deviated",
                evidence=evidence,
                notes=f"Found {deviation_score} potential contradictions in code",
            )

        if max_conf >= 0.7 and len(high_conf) >= 2:
            status = "implemented"
            notes = f"{len(high_conf)} strong matches"
            if has_test:
                notes += " (with tests)"
            return SpecGap(
                requirement=req,
                status=status,
                evidence=evidence,
                notes=notes,
            )

        if max_conf >= 0.4 or len(evidence) >= 2:
            return SpecGap(
                requirement=req,
                status="partial",
                evidence=evidence,
                notes=f"Some evidence found (max confidence: {max_conf:.0%})",
            )

        return SpecGap(
            requirement=req,
            status="missing",
            evidence=evidence,
            notes="Only weak matches found",
        )


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_spec_report(report: SpecReport, fmt: str = "text") -> str:
    """Format a SpecReport for display.

    Args:
        report: The validation report.
        fmt: "text" for terminal output, "json" for machine-readable.
    """
    if fmt == "json":
        return _format_json(report)
    return _format_text(report)


def _format_text(report: SpecReport) -> str:
    """Rich terminal box format."""
    if not report.requirements:
        return "  No requirements found in spec text."

    total = len(report.requirements)
    impl = sum(1 for g in report.gaps if g.status == "implemented")
    partial = sum(1 for g in report.gaps if g.status == "partial")
    missing = sum(1 for g in report.gaps if g.status == "missing")
    deviated = sum(1 for g in report.gaps if g.status == "deviated")

    width = 50
    lines: list[str] = []
    lines.append(f"  +-- Spec Validation {'─' * (width - 21)}+")
    lines.append(f"  | Coverage: {report.coverage:.0f}% ({impl}/{total} requirements){' ' * max(0, width - 35 - len(str(impl)) - len(str(total)))}|")

    status_parts: list[str] = []
    if impl:
        status_parts.append(f"[ok] {impl} implemented")
    if partial:
        status_parts.append(f"[~] {partial} partial")
    if missing:
        status_parts.append(f"[x] {missing} missing")
    if deviated:
        status_parts.append(f"[!] {deviated} deviated")
    status_line = "  ".join(status_parts)
    lines.append(f"  | {status_line}{' ' * max(0, width - len(status_line) - 1)}|")
    lines.append(f"  +{'─' * width}+")

    _STATUS_ICON = {
        "implemented": "[ok]",
        "partial": "[~] ",
        "missing": "[x] ",
        "deviated": "[!] ",
    }

    for gap in report.gaps:
        icon = _STATUS_ICON.get(gap.status, "   ")
        desc = gap.requirement.description[:60]
        suffix = ""
        if gap.status == "partial":
            suffix = " (partial)"
        elif gap.status == "missing":
            suffix = " (missing)"
        elif gap.status == "deviated":
            suffix = " (deviated)"
        line = f"  | {icon} {gap.requirement.id}: {desc}{suffix}"
        lines.append(line)
        if gap.notes:
            lines.append(f"  |      {gap.notes}")

    lines.append(f"  +{'─' * width}+")
    return "\n".join(lines)


def _format_json(report: SpecReport) -> str:
    """JSON format for machine consumption."""
    data = {
        "coverage": report.coverage,
        "total_requirements": len(report.requirements),
        "missing": report.missing,
        "deviated": report.deviated,
        "requirements": [],
    }
    for gap in report.gaps:
        req_data = {
            "id": gap.requirement.id,
            "description": gap.requirement.description,
            "category": gap.requirement.category,
            "source": gap.requirement.source,
            "status": gap.status,
            "notes": gap.notes,
            "evidence": [
                {
                    "file": e.file,
                    "line": e.line,
                    "snippet": e.code_snippet,
                    "confidence": e.confidence,
                }
                for e in gap.evidence[:5]
            ],
        }
        data["requirements"].append(req_data)
    return json.dumps(data, indent=2)
