"""Schema evolution simulator — simulate schema changes, backward compat, migration effort.

Analyzes proposed schema modifications and predicts backward compatibility
issues, required data migrations, and downstream impact.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.api.schema_evolution_sim")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}

# Breaking change types
BREAKING_CHANGES = {
    "field_removed": "high",
    "field_type_changed": "high",
    "field_renamed": "medium",
    "required_field_added": "medium",
    "enum_value_removed": "high",
    "constraint_tightened": "medium",
}

SAFE_CHANGES = {
    "optional_field_added", "field_deprecated",
    "enum_value_added", "constraint_relaxed",
    "default_added", "description_changed",
}


@dataclass
class SchemaField:
    """A field in a schema."""

    name: str = ""
    field_type: str = ""
    required: bool = False
    default: str | None = None
    description: str = ""
    constraints: list[str] = field(default_factory=list)


@dataclass
class SchemaChange:
    """A single schema change."""

    field_name: str = ""
    change_type: str = ""  # field_removed | field_type_changed | etc.
    old_value: str = ""
    new_value: str = ""
    is_breaking: bool = False
    severity: str = "low"  # low | medium | high
    migration_needed: bool = False
    migration_hint: str = ""


@dataclass
class CompatReport:
    """Backward compatibility report."""

    is_compatible: bool = True
    breaking_changes: list[SchemaChange] = field(default_factory=list)
    safe_changes: list[SchemaChange] = field(default_factory=list)
    migration_steps: list[str] = field(default_factory=list)
    effort_hours: float = 0.0
    affected_consumers: list[str] = field(default_factory=list)


@dataclass
class SchemaEvolutionResult:
    """Result of schema evolution simulation."""

    schemas_analyzed: int = 0
    changes: list[SchemaChange] = field(default_factory=list)
    compat_report: CompatReport = field(default_factory=CompatReport)
    data_impact: dict[str, str] = field(default_factory=dict)
    recommended_strategy: str = ""  # in_place | versioned | dual_write
    summary: dict[str, int] = field(default_factory=dict)


class SchemaEvolutionSimulator:
    """Simulate schema evolution and assess impact."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("SchemaEvolutionSimulator initialized for %s", cwd)

    def simulate(
        self,
        old_schema: dict | None = None,
        new_schema: dict | None = None,
        schema_file: str | None = None,
    ) -> SchemaEvolutionResult:
        """Simulate schema evolution.

        Args:
            old_schema: Current schema as dict of field_name -> field_type.
            new_schema: Proposed schema as dict of field_name -> field_type.
            schema_file: Path to schema file for auto-detection.

        Returns:
            SchemaEvolutionResult with changes and compatibility report.
        """
        result = SchemaEvolutionResult()

        if old_schema is None or new_schema is None:
            if schema_file:
                old_schema, new_schema = self._load_schemas(schema_file)
            else:
                schemas = self._auto_detect_schemas()
                if schemas:
                    old_schema = schemas.get("current", {})
                    new_schema = schemas.get("proposed", old_schema)

        if not old_schema and not new_schema:
            logger.warning("No schemas to analyze")
            return result

        old_schema = old_schema or {}
        new_schema = new_schema or {}
        result.schemas_analyzed = 2

        # Detect changes
        result.changes = self._detect_changes(old_schema, new_schema)
        logger.info("Detected %d schema changes", len(result.changes))

        # Build compat report
        result.compat_report = self._assess_compatibility(result.changes)

        # Analyze data impact
        result.data_impact = self._analyze_data_impact(result.changes)

        # Recommend strategy
        result.recommended_strategy = self._recommend_strategy(result.compat_report)

        result.summary = {
            "total_changes": len(result.changes),
            "breaking_changes": len(result.compat_report.breaking_changes),
            "safe_changes": len(result.compat_report.safe_changes),
            "migration_steps": len(result.compat_report.migration_steps),
            "effort_hours": result.compat_report.effort_hours,
            "is_compatible": int(result.compat_report.is_compatible),
        }
        return result

    def _load_schemas(self, schema_file: str) -> tuple[dict, dict]:
        """Load schema from file."""
        try:
            content = Path(schema_file).read_text(errors="replace")
        except OSError:
            return {}, {}

        # Try JSON
        if schema_file.endswith(".json"):
            try:
                import json
                data = json.loads(content)
                props = data.get("properties", data)
                return props, props
            except (ImportError, ValueError):
                pass

        # Try YAML
        if schema_file.endswith((".yaml", ".yml")):
            try:
                import yaml  # lazy import
                data = yaml.safe_load(content)
                if isinstance(data, dict):
                    return data.get("properties", data), data.get("properties", data)
            except (ImportError, Exception):
                pass

        # Try to extract Pydantic/dataclass models from Python
        if schema_file.endswith(".py"):
            return self._parse_python_schema(content)

        return {}, {}

    def _parse_python_schema(self, content: str) -> tuple[dict, dict]:
        """Extract schema from Pydantic model or dataclass."""
        schema: dict[str, str] = {}
        # Match field definitions like `name: str = "default"`
        field_re = re.compile(r"^\s+(\w+)\s*:\s*(\w[\w\[\], |]*?)(?:\s*=.*)?$", re.MULTILINE)
        for match in field_re.finditer(content):
            name, ftype = match.group(1), match.group(2)
            if name not in ("self", "cls", "Meta"):
                schema[name] = ftype
        return schema, schema

    def _auto_detect_schemas(self) -> dict[str, dict]:
        """Auto-detect schema files in the project."""
        schemas: dict[str, dict] = {}
        model_files: list[str] = []

        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                if fname in ("models.py", "schemas.py", "schema.py"):
                    model_files.append(os.path.join(root, fname))
                elif fname.endswith((".schema.json", ".schema.yaml")):
                    model_files.append(os.path.join(root, fname))

        if model_files:
            first = model_files[0]
            current, proposed = self._load_schemas(first)
            schemas["current"] = current
            schemas["proposed"] = proposed

        return schemas

    def _detect_changes(
        self, old: dict[str, str], new: dict[str, str],
    ) -> list[SchemaChange]:
        """Detect changes between two schemas."""
        changes: list[SchemaChange] = []

        old_fields = set(old.keys())
        new_fields = set(new.keys())

        # Removed fields
        for field_name in old_fields - new_fields:
            changes.append(SchemaChange(
                field_name=field_name,
                change_type="field_removed",
                old_value=str(old[field_name]),
                is_breaking=True,
                severity="high",
                migration_needed=True,
                migration_hint=f"Remove references to '{field_name}' in all consumers",
            ))

        # Added fields
        for field_name in new_fields - old_fields:
            new_type = str(new[field_name])
            is_optional = "Optional" in new_type or "None" in new_type or "| None" in new_type
            if is_optional:
                changes.append(SchemaChange(
                    field_name=field_name,
                    change_type="optional_field_added",
                    new_value=new_type,
                    is_breaking=False,
                    severity="low",
                ))
            else:
                changes.append(SchemaChange(
                    field_name=field_name,
                    change_type="required_field_added",
                    new_value=new_type,
                    is_breaking=True,
                    severity="medium",
                    migration_needed=True,
                    migration_hint=f"Add default value for '{field_name}' or backfill data",
                ))

        # Changed fields
        for field_name in old_fields & new_fields:
            old_type = str(old[field_name])
            new_type = str(new[field_name])
            if old_type != new_type:
                changes.append(SchemaChange(
                    field_name=field_name,
                    change_type="field_type_changed",
                    old_value=old_type,
                    new_value=new_type,
                    is_breaking=True,
                    severity="high",
                    migration_needed=True,
                    migration_hint=f"Migrate '{field_name}' from {old_type} to {new_type}",
                ))

        return changes

    def _assess_compatibility(self, changes: list[SchemaChange]) -> CompatReport:
        """Assess backward compatibility."""
        report = CompatReport()

        for change in changes:
            if change.is_breaking:
                report.breaking_changes.append(change)
                report.is_compatible = False
            else:
                report.safe_changes.append(change)

        # Generate migration steps
        for bc in report.breaking_changes:
            if bc.migration_hint:
                report.migration_steps.append(bc.migration_hint)

        # Estimate effort
        report.effort_hours = (
            len(report.breaking_changes) * 4.0
            + len([c for c in changes if c.migration_needed]) * 2.0
        )

        # Find affected consumers
        report.affected_consumers = self._find_consumers(
            [c.field_name for c in report.breaking_changes],
        )

        return report

    def _find_consumers(self, field_names: list[str]) -> list[str]:
        """Find files that reference the changed fields."""
        consumers: list[str] = []
        if not field_names:
            return consumers

        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                if not fname.endswith((".py", ".js", ".ts")):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    content = Path(fpath).read_text(errors="replace")
                except OSError:
                    continue
                for field_name in field_names:
                    if field_name in content:
                        consumers.append(os.path.relpath(fpath, self.cwd))
                        break

            if len(consumers) >= 20:
                break

        return consumers

    def _analyze_data_impact(self, changes: list[SchemaChange]) -> dict[str, str]:
        """Analyze impact on existing data."""
        impact: dict[str, str] = {}
        for change in changes:
            if change.change_type == "field_removed":
                impact[change.field_name] = "Data in this field will be orphaned"
            elif change.change_type == "field_type_changed":
                impact[change.field_name] = (
                    f"Data needs conversion from {change.old_value} to {change.new_value}"
                )
            elif change.change_type == "required_field_added":
                impact[change.field_name] = "Existing records need backfill for new required field"
        return impact

    def _recommend_strategy(self, compat: CompatReport) -> str:
        """Recommend migration strategy."""
        if not compat.breaking_changes:
            return "in_place"
        if len(compat.breaking_changes) > 3 or compat.effort_hours > 16:
            return "versioned"
        return "dual_write"


def simulate_schema_evolution(
    cwd: str,
    old_schema: dict | None = None,
    new_schema: dict | None = None,
    schema_file: str | None = None,
) -> dict:
    """Convenience function for schema evolution simulation.

    Returns:
        Dict with changes, compatibility report, and recommendation.
    """
    sim = SchemaEvolutionSimulator(cwd)
    result = sim.simulate(old_schema=old_schema, new_schema=new_schema, schema_file=schema_file)
    return {
        "is_compatible": result.compat_report.is_compatible,
        "changes": [
            {"field": c.field_name, "type": c.change_type, "breaking": c.is_breaking,
             "severity": c.severity, "migration_hint": c.migration_hint}
            for c in result.changes
        ],
        "migration_steps": result.compat_report.migration_steps,
        "effort_hours": result.compat_report.effort_hours,
        "data_impact": result.data_impact,
        "recommended_strategy": result.recommended_strategy,
        "summary": result.summary,
    }
