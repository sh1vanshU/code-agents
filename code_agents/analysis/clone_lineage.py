"""Clone Lineage — track copy-pasted code evolution and propagate fixes."""

import logging
import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.analysis.clone_lineage")


@dataclass
class CodeClone:
    """A detected code clone."""
    clone_id: str = ""
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    content_hash: str = ""
    normalized_hash: str = ""
    lines_of_code: int = 0
    clone_type: int = 1  # Type 1: exact, Type 2: renamed, Type 3: modified


@dataclass
class CloneGroup:
    """A group of related clones."""
    group_id: str = ""
    clones: list[CodeClone] = field(default_factory=list)
    similarity: float = 1.0
    original_file: str = ""
    diverged: bool = False
    divergence_points: list[str] = field(default_factory=list)


@dataclass
class FixPropagation:
    """A suggested fix to propagate across clones."""
    source_file: str = ""
    source_lines: tuple[int, int] = (0, 0)
    target_file: str = ""
    target_lines: tuple[int, int] = (0, 0)
    description: str = ""
    confidence: float = 0.0


@dataclass
class LineageReport:
    """Complete clone lineage report."""
    clone_groups: list[CloneGroup] = field(default_factory=list)
    total_clones: int = 0
    total_clone_loc: int = 0
    clone_percentage: float = 0.0
    fix_propagations: list[FixPropagation] = field(default_factory=list)
    refactor_candidates: list[CloneGroup] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CloneLineage:
    """Tracks copy-pasted code, finds clones, suggests fix propagation."""

    def __init__(self, cwd: str, min_lines: int = 6):
        self.cwd = cwd
        self.min_lines = min_lines

    def analyze(self, file_contents: dict[str, str],
                recent_changes: Optional[dict[str, list[int]]] = None) -> LineageReport:
        """Analyze codebase for clones and propagation opportunities."""
        logger.info("Analyzing %d files for code clones (min_lines=%d)", len(file_contents), self.min_lines)
        recent_changes = recent_changes or {}

        # Phase 1: Extract code blocks
        all_blocks: list[CodeClone] = []
        total_loc = 0
        for fpath, content in file_contents.items():
            blocks = self._extract_blocks(fpath, content)
            all_blocks.extend(blocks)
            total_loc += len(content.splitlines())

        # Phase 2: Group by hash
        groups = self._find_clone_groups(all_blocks)
        logger.info("Found %d clone groups from %d blocks", len(groups), len(all_blocks))

        # Phase 3: Detect divergence
        for group in groups:
            self._detect_divergence(group, file_contents)

        # Phase 4: Suggest fix propagations
        propagations = []
        if recent_changes:
            propagations = self._suggest_propagations(groups, recent_changes, file_contents)

        # Phase 5: Identify refactor candidates
        refactor = [g for g in groups if len(g.clones) >= 3 and g.similarity > 0.7]

        clone_loc = sum(c.lines_of_code for g in groups for c in g.clones)
        report = LineageReport(
            clone_groups=groups,
            total_clones=sum(len(g.clones) for g in groups),
            total_clone_loc=clone_loc,
            clone_percentage=(clone_loc / total_loc * 100) if total_loc else 0.0,
            fix_propagations=propagations,
            refactor_candidates=refactor,
            warnings=self._generate_warnings(groups),
        )
        logger.info("Clone report: %d groups, %.1f%% cloned", len(groups), report.clone_percentage)
        return report

    def _extract_blocks(self, fpath: str, content: str) -> list[CodeClone]:
        """Extract code blocks from a file using sliding window."""
        lines = content.splitlines()
        blocks = []
        window = self.min_lines

        for i in range(len(lines) - window + 1):
            block = lines[i:i + window]
            # Skip blocks that are mostly blank/comments
            code_lines = [l for l in block if l.strip() and not l.strip().startswith("#")]
            if len(code_lines) < window // 2:
                continue

            raw = "\n".join(block)
            content_hash = hashlib.md5(raw.encode()).hexdigest()
            normalized = self._normalize(raw)
            norm_hash = hashlib.md5(normalized.encode()).hexdigest()

            blocks.append(CodeClone(
                clone_id=f"{fpath}:{i+1}",
                file_path=fpath,
                start_line=i + 1,
                end_line=i + window,
                content_hash=content_hash,
                normalized_hash=norm_hash,
                lines_of_code=window,
                clone_type=1,
            ))
        return blocks

    def _normalize(self, code: str) -> str:
        """Normalize code for Type-2 clone detection (rename-invariant)."""
        # Replace identifiers with placeholders
        normalized = re.sub(r'\b[a-z_]\w*\b', 'VAR', code)
        # Remove whitespace variations
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized.strip()

    def _find_clone_groups(self, blocks: list[CodeClone]) -> list[CloneGroup]:
        """Group blocks by their hash to find clones."""
        # Group by normalized hash for Type-2 clones
        hash_groups: dict[str, list[CodeClone]] = {}
        for block in blocks:
            hash_groups.setdefault(block.normalized_hash, []).append(block)

        groups = []
        seen_files: set[str] = set()
        for norm_hash, clones in hash_groups.items():
            if len(clones) < 2:
                continue
            # Deduplicate: only keep one clone per file for overlapping ranges
            deduped = self._deduplicate_overlaps(clones)
            if len(deduped) < 2:
                continue

            # Determine clone type
            exact = len(set(c.content_hash for c in deduped)) == 1
            for c in deduped:
                c.clone_type = 1 if exact else 2

            group = CloneGroup(
                group_id=f"grp_{norm_hash[:8]}",
                clones=deduped,
                similarity=1.0 if exact else 0.8,
                original_file=deduped[0].file_path,
            )
            groups.append(group)

        return groups

    def _deduplicate_overlaps(self, clones: list[CodeClone]) -> list[CodeClone]:
        """Remove overlapping clones from the same file."""
        result = []
        by_file: dict[str, list[CodeClone]] = {}
        for c in clones:
            by_file.setdefault(c.file_path, []).append(c)

        for fpath, file_clones in by_file.items():
            file_clones.sort(key=lambda c: c.start_line)
            kept = [file_clones[0]]
            for c in file_clones[1:]:
                if c.start_line >= kept[-1].end_line:
                    kept.append(c)
            result.extend(kept)
        return result

    def _detect_divergence(self, group: CloneGroup, file_contents: dict[str, str]):
        """Detect if clones have diverged."""
        hashes = set(c.content_hash for c in group.clones)
        if len(hashes) > 1:
            group.diverged = True
            group.similarity = 1.0 / len(hashes)
            group.divergence_points = [
                f"{c.file_path}:{c.start_line}" for c in group.clones
                if c.content_hash != group.clones[0].content_hash
            ]

    def _suggest_propagations(self, groups: list[CloneGroup],
                              changes: dict[str, list[int]],
                              file_contents: dict[str, str]) -> list[FixPropagation]:
        """Suggest fix propagations for recently changed clones."""
        propagations = []
        for group in groups:
            for clone in group.clones:
                changed_lines = changes.get(clone.file_path, [])
                clone_range = set(range(clone.start_line, clone.end_line + 1))
                if clone_range & set(changed_lines):
                    # This clone was recently changed — propagate to others
                    for other in group.clones:
                        if other.clone_id != clone.clone_id:
                            propagations.append(FixPropagation(
                                source_file=clone.file_path,
                                source_lines=(clone.start_line, clone.end_line),
                                target_file=other.file_path,
                                target_lines=(other.start_line, other.end_line),
                                description=f"Propagate change from {clone.file_path}:{clone.start_line}",
                                confidence=group.similarity,
                            ))
        return propagations

    def _generate_warnings(self, groups: list[CloneGroup]) -> list[str]:
        """Generate warnings."""
        warnings = []
        large = [g for g in groups if len(g.clones) >= 5]
        if large:
            warnings.append(f"{len(large)} clone groups with 5+ copies — strong refactor candidates")
        diverged = [g for g in groups if g.diverged]
        if diverged:
            warnings.append(f"{len(diverged)} clone groups have diverged — potential inconsistencies")
        return warnings


def format_report(report: LineageReport) -> str:
    """Format lineage report."""
    lines = [
        "# Clone Lineage Report",
        f"Clones: {report.total_clones} | LOC: {report.total_clone_loc} ({report.clone_percentage:.1f}%)",
        f"Groups: {len(report.clone_groups)} | Propagations: {len(report.fix_propagations)}",
        "",
    ]
    for g in report.clone_groups[:15]:
        status = "diverged" if g.diverged else "identical"
        lines.append(f"  Group {g.group_id}: {len(g.clones)} clones ({status})")
    return "\n".join(lines)
