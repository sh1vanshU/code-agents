"""Mutation testing to verify test quality.

Applies small mutations to source code (operator, boundary, return value, null check)
and runs the test suite to verify that tests catch each mutation.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.testing.mutation_tester")


@dataclass
class Mutation:
    """A single mutation applied to source code."""

    file: str
    line: int
    original: str
    mutated: str
    mutation_type: str  # operator, boundary, return_value, null_check
    killed: bool = False  # True if tests caught the mutation


@dataclass
class MutationReport:
    """Report from a mutation testing run."""

    source_file: str
    total: int = 0
    killed: int = 0
    survived: int = 0
    score: float = 0.0  # killed / total * 100
    mutations: list[Mutation] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mutation operators — regex (pattern, replacement, type)
# ---------------------------------------------------------------------------

MUTATIONS: dict[str, list[tuple[str, str]]] = {
    "operator": [
        (r"(\s)==(\s)", r"\1!=\2"),
        (r"(\s)!=(\s)", r"\1==\2"),
        (r"(\s)>=(\s)", r"\1<\2"),
        (r"(\s)<=(\s)", r"\1>\2"),
        (r"(\s)>(\s)", r"\1<\2"),
        (r"(\s)<(\s)", r"\1>\2"),
        (r"\s\+\s", " - "),
        (r"\s-\s", " + "),
        (r"\s\*\s", " / "),
    ],
    "boundary": [
        (r"(\s)>=(\s)", r"\1>\2"),
        (r"(\s)<=(\s)", r"\1<\2"),
        (r"(\s)>(\s)", r"\1>=\2"),
        (r"(\s)<(\s)", r"\1<=\2"),
    ],
    "return_value": [
        (r"return True", "return False"),
        (r"return False", "return True"),
        (r"return 0", "return 1"),
        (r"return 1", "return 0"),
        (r"return None", "return 0"),
        (r'return ""', 'return "mutated"'),
        (r"return \[\]", "return [None]"),
    ],
    "null_check": [
        (r"if (\w+) is None:", r"if \1 is not None:"),
        (r"if (\w+) is not None:", r"if \1 is None:"),
        (r"if not (\w+):", r"if \1:"),
        (r"if (\w+):", r"if not \1:"),
    ],
}


class MutationTester:
    """Apply mutations to source code and verify test quality."""

    def __init__(self, repo_path: str = ".", test_command: str = "pytest"):
        self.repo_path = repo_path
        self.test_command = test_command

    def generate_mutations(self, filepath: str) -> list[Mutation]:
        """Generate possible mutations for a source file.

        Args:
            filepath: Path to the source file.

        Returns:
            List of Mutation objects (not yet applied/tested).
        """
        full_path = os.path.join(self.repo_path, filepath) if not os.path.isabs(filepath) else filepath
        if not os.path.exists(full_path):
            logger.warning("File not found: %s", full_path)
            return []

        try:
            lines = Path(full_path).read_text().splitlines()
        except Exception as exc:
            logger.warning("Cannot read %s: %s", full_path, exc)
            return []

        mutations = []
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments and blank lines
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue

            for mutation_type, patterns in MUTATIONS.items():
                for pattern, replacement in patterns:
                    try:
                        if re.search(pattern, line):
                            mutated = re.sub(pattern, replacement, line, count=1)
                            if mutated != line:
                                mutations.append(Mutation(
                                    file=filepath,
                                    line=line_num,
                                    original=line.strip(),
                                    mutated=mutated.strip(),
                                    mutation_type=mutation_type,
                                ))
                    except re.error:
                        pass

        return mutations

    def run_mutation(self, mutation: Mutation) -> Mutation:
        """Apply a mutation, run tests, check if caught, restore original.

        Args:
            mutation: The mutation to test.

        Returns:
            The same Mutation with `killed` updated.
        """
        full_path = os.path.join(self.repo_path, mutation.file) if not os.path.isabs(mutation.file) else mutation.file
        if not os.path.exists(full_path):
            return mutation

        original_content = Path(full_path).read_text()
        lines = original_content.splitlines()

        if mutation.line < 1 or mutation.line > len(lines):
            return mutation

        # Apply mutation
        original_line = lines[mutation.line - 1]
        for pattern, replacement in MUTATIONS.get(mutation.mutation_type, []):
            try:
                mutated_line = re.sub(pattern, replacement, original_line, count=1)
                if mutated_line != original_line:
                    lines[mutation.line - 1] = mutated_line
                    break
            except re.error:
                pass

        try:
            Path(full_path).write_text("\n".join(lines))
            # Run tests
            result = subprocess.run(
                self.test_command.split(),
                capture_output=True, text=True,
                cwd=self.repo_path, timeout=120,
            )
            # If tests fail, mutation was killed (detected)
            mutation.killed = result.returncode != 0
        except (subprocess.TimeoutExpired, Exception) as exc:
            logger.warning("Mutation test error: %s", exc)
            mutation.killed = True  # timeout = tests noticed something
        finally:
            # Always restore original
            Path(full_path).write_text(original_content)

        return mutation

    def test_file(self, filepath: str, max_mutations: int = 50) -> MutationReport:
        """Generate mutations, test them, produce a report.

        Args:
            filepath: Source file to mutate.
            max_mutations: Maximum mutations to test (for speed).

        Returns:
            MutationReport with scores and details.
        """
        mutations = self.generate_mutations(filepath)[:max_mutations]
        report = MutationReport(source_file=filepath, total=len(mutations))

        for mutation in mutations:
            self.run_mutation(mutation)
            if mutation.killed:
                report.killed += 1
            else:
                report.survived += 1
            report.mutations.append(mutation)

        report.score = (report.killed / report.total * 100) if report.total > 0 else 0.0
        return report


def format_mutation_report(report: MutationReport) -> str:
    """Format mutation testing report for terminal display."""
    lines = []
    lines.append("  ╔══ MUTATION TESTING ══╗")
    lines.append(f"  ║ File: {report.source_file}")
    lines.append(f"  ║ Score: {report.score:.0f}% ({report.killed}/{report.total} killed)")
    lines.append("  ╚═══════════════════════╝")

    if report.score >= 80:
        lines.append("\n  Test quality: GOOD")
    elif report.score >= 50:
        lines.append("\n  Test quality: MODERATE — consider adding more assertions")
    else:
        lines.append("\n  Test quality: LOW — many mutations survive, tests need improvement")

    # Show survived mutations (these are the concerning ones)
    survived = [m for m in report.mutations if not m.killed]
    if survived:
        lines.append(f"\n  Survived mutations ({len(survived)}):")
        for m in survived[:10]:
            lines.append(f"    Line {m.line} [{m.mutation_type}]")
            lines.append(f"      - {m.original}")
            lines.append(f"      + {m.mutated}")

    return "\n".join(lines)
