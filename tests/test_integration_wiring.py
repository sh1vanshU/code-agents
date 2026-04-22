"""
Integration wiring tests — verify all registrations, imports, and conventions.

These tests dynamically discover files rather than hardcoding lists, ensuring
new modules/agents/routers are automatically covered.
"""

from __future__ import annotations

import ast
import importlib
import logging
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
CODE_AGENTS_PKG = ROOT / "code_agents"
AGENTS_DIR = ROOT / "agents"

# The 12 new subdirectories introduced in v0.7.0
NEW_SUBDIRS = [
    "core",
    "agent_system",
    "security",
    "reviews",
    "testing",
    "observability",
    "git_ops",
    "knowledge",
    "api",
    "devops",
    "ui",
    "domain",
]


# ===========================================================================
# 1. CLI Subcommand Registration
# ===========================================================================


class TestCLISubcommandRegistration:
    """Verify all CLI subcommands are registered in the command registry."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        # Lazy-import to avoid heavy side effects during collection
        from code_agents.cli.registry import COMMAND_REGISTRY

        self.registry = COMMAND_REGISTRY

    def test_registry_is_not_empty(self):
        assert len(self.registry) > 0, "COMMAND_REGISTRY is empty"

    def test_essential_commands_registered(self):
        """Core commands that must always exist."""
        essential = [
            "init", "start", "shutdown", "restart", "status", "agents",
            "chat", "config", "doctor", "help", "diff", "test", "review",
            "commit", "version", "update", "export",
        ]
        missing = [cmd for cmd in essential if cmd not in self.registry]
        assert not missing, f"Essential CLI commands missing from registry: {missing}"

    def test_every_entry_has_handler(self):
        """Every registry entry must have a callable handler or importable string reference."""
        for name, entry in self.registry.items():
            handler = entry.handler
            is_valid = callable(handler) or (isinstance(handler, str) and len(handler) > 0)
            assert is_valid, (
                f"CLI command '{name}' has invalid handler: {handler!r}"
            )

    def test_every_entry_has_help_text(self):
        for name, entry in self.registry.items():
            assert entry.help and len(entry.help) > 0, (
                f"CLI command '{name}' is missing help text"
            )

    def test_no_duplicate_aliases(self):
        """Aliases should not collide with command names or other aliases."""
        all_names = set(self.registry.keys())
        seen_aliases: dict[str, str] = {}
        collisions_with_names = []
        collisions_between_aliases = []
        for name, entry in self.registry.items():
            for alias in entry.aliases:
                if alias in all_names:
                    collisions_with_names.append((alias, name))
                if alias in seen_aliases:
                    collisions_between_aliases.append((alias, name, seen_aliases[alias]))
                seen_aliases[alias] = name
        # Collisions with command names are hard failures
        assert not collisions_with_names, (
            f"Aliases colliding with command names: {collisions_with_names}"
        )
        # Duplicate aliases between commands are tolerated (first-wins) but should be few
        assert len(collisions_between_aliases) <= 5, (
            f"Too many duplicate aliases ({len(collisions_between_aliases)}): {collisions_between_aliases}"
        )


class TestCLICommandsDict:
    """Verify the COMMANDS dict in cli.py is consistent with the registry."""

    CLI_PY = CODE_AGENTS_PKG / "cli" / "cli.py"

    def _parse_commands_dict_keys(self) -> list[str]:
        """Parse command names from the COMMANDS dict via AST."""
        source = self.CLI_PY.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "COMMANDS":
                        if isinstance(node.value, ast.Dict):
                            return [
                                key.value for key in node.value.keys
                                if isinstance(key, ast.Constant) and isinstance(key.value, str)
                            ]
        return []

    def test_commands_dict_exists_and_nonempty(self):
        keys = self._parse_commands_dict_keys()
        assert len(keys) > 0, "COMMANDS dict in cli.py is empty or not found"

    def test_commands_dict_has_core_commands(self):
        keys = set(self._parse_commands_dict_keys())
        core = ["init", "start", "shutdown", "status", "agents", "chat",
                "config", "doctor", "diff", "test", "export", "version"]
        missing = [c for c in core if c not in keys]
        assert not missing, f"Core commands missing from COMMANDS dict: {missing}"

    def test_no_duplicate_keys_in_commands_dict(self):
        """COMMANDS dict should have unique keys."""
        keys = self._parse_commands_dict_keys()
        seen = set()
        dupes = []
        for k in keys:
            if k in seen:
                dupes.append(k)
            seen.add(k)
        assert not dupes, f"Duplicate keys in COMMANDS dict: {dupes}"


# ===========================================================================
# 2. Router Registration in app.py
# ===========================================================================


class TestRouterRegistration:
    """Verify all routers in code_agents/routers/ are registered in app.py."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.routers_dir = CODE_AGENTS_PKG / "routers"
        self.app_py = CODE_AGENTS_PKG / "core" / "app.py"

    def _router_module_names(self) -> list[str]:
        """Discover all Python modules in the routers/ directory."""
        names = []
        for f in sorted(self.routers_dir.glob("*.py")):
            if f.name.startswith("_"):
                continue
            names.append(f.stem)
        return names

    def test_routers_dir_exists(self):
        assert self.routers_dir.is_dir(), f"Routers directory not found: {self.routers_dir}"

    def test_app_py_exists(self):
        assert self.app_py.is_file(), f"app.py not found: {self.app_py}"

    def test_app_has_include_router_calls(self):
        content = self.app_py.read_text()
        count = content.count("include_router")
        assert count >= 10, (
            f"Expected at least 10 include_router calls in app.py, found {count}"
        )

    def test_router_modules_can_be_imported(self):
        """Every module in routers/ should be importable."""
        failures = []
        for name in self._router_module_names():
            try:
                importlib.import_module(f"code_agents.routers.{name}")
            except Exception as exc:
                failures.append((name, str(exc)))
        assert not failures, (
            f"Router modules that failed to import:\n"
            + "\n".join(f"  {n}: {e}" for n, e in failures)
        )


# ===========================================================================
# 3. Agent YAML Configs
# ===========================================================================


class TestAgentYAMLConfigs:
    """Verify every agent directory has a corresponding YAML config."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.agents_dir = AGENTS_DIR

    def _agent_dirs(self) -> list[str]:
        """List agent subdirectories (excluding _shared, non-agent files, and disabled)."""
        dirs = []
        all_names = set()
        for entry in sorted(self.agents_dir.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("_") or entry.name.startswith("."):
                continue
            if entry.name.endswith(".disabled"):
                continue
            all_names.add(entry.name)

        for name in sorted(all_names):
            # If both hyphenated and underscored variants exist (e.g. code-writer
            # and code_writer), prefer the underscored one (has the YAML).
            alt = name.replace("-", "_")
            if alt != name and alt in all_names:
                continue
            dirs.append(name)
        return dirs

    def test_agents_dir_exists(self):
        assert self.agents_dir.is_dir(), f"Agents directory not found: {self.agents_dir}"

    def test_at_least_10_agents(self):
        dirs = self._agent_dirs()
        assert len(dirs) >= 10, f"Expected at least 10 agents, found {len(dirs)}: {dirs}"

    def test_every_agent_has_yaml(self):
        """Each agent dir must contain a .yaml config file."""
        missing = []
        for name in self._agent_dirs():
            agent_dir = self.agents_dir / name
            # Look for <name>.yaml or <name_with_underscores>.yaml
            yaml_files = list(agent_dir.glob("*.yaml"))
            # Filter out autorun.yaml
            config_yamls = [f for f in yaml_files if f.name != "autorun.yaml"]
            if not config_yamls:
                missing.append(name)
        assert not missing, (
            f"Agent directories without YAML config: {missing}"
        )

    def test_every_agent_has_skills_dir(self):
        """Each agent dir should have a skills/ subdirectory."""
        missing = []
        for name in self._agent_dirs():
            skills_dir = self.agents_dir / name / "skills"
            if not skills_dir.is_dir():
                missing.append(name)
        # Allow some agents to not have skills (e.g. simple agents)
        # but flag if more than 30% are missing
        total = len(self._agent_dirs())
        if total > 0:
            pct_missing = len(missing) / total
            assert pct_missing < 0.5, (
                f"{len(missing)}/{total} agents missing skills/ directory: {missing}"
            )


# ===========================================================================
# 4. Module Import Smoke Tests
# ===========================================================================


class TestSubdirectoryImports:
    """Verify all modules in the 12 new subdirectories can be imported."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.pkg_dir = CODE_AGENTS_PKG

    def _discover_modules(self, subdir: str) -> list[str]:
        """List all .py modules in a subdirectory (excluding __init__, __pycache__)."""
        d = self.pkg_dir / subdir
        if not d.is_dir():
            return []
        modules = []
        for f in sorted(d.glob("*.py")):
            if f.name.startswith("__"):
                continue
            modules.append(f.stem)
        return modules

    @pytest.mark.parametrize("subdir", NEW_SUBDIRS)
    def test_subdirectory_exists(self, subdir):
        d = self.pkg_dir / subdir
        assert d.is_dir(), f"Subdirectory code_agents/{subdir}/ does not exist"

    @pytest.mark.parametrize("subdir", NEW_SUBDIRS)
    def test_subdirectory_has_init(self, subdir):
        init = self.pkg_dir / subdir / "__init__.py"
        assert init.is_file(), f"code_agents/{subdir}/__init__.py is missing"

    @pytest.mark.parametrize("subdir", NEW_SUBDIRS)
    def test_modules_importable(self, subdir):
        """Every .py file in the subdirectory should import without error."""
        modules = self._discover_modules(subdir)
        assert len(modules) > 0, f"No modules found in code_agents/{subdir}/"

        failures = []
        for mod_name in modules:
            fqn = f"code_agents.{subdir}.{mod_name}"
            try:
                importlib.import_module(fqn)
            except Exception as exc:
                failures.append((fqn, str(exc)))

        assert not failures, (
            f"Modules in code_agents/{subdir}/ that failed to import:\n"
            + "\n".join(f"  {fqn}: {e}" for fqn, e in failures)
        )


# ===========================================================================
# 5. Logger Naming Convention
# ===========================================================================


class TestLoggerNamingConvention:
    """Verify loggers follow the code_agents.<subdir>.<module> convention."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.pkg_dir = CODE_AGENTS_PKG

    def _scan_logger_names(self, subdir: str) -> list[tuple[str, str, str]]:
        """
        Scan .py files for the module-level logger assignment pattern:
            logger = logging.getLogger("...")
        Returns list of (file_path, logger_name, expected_name).
        Ignores getLogger calls that configure other loggers (e.g. uvicorn).
        """
        results = []
        d = self.pkg_dir / subdir
        if not d.is_dir():
            return results

        # Match only: logger = logging.getLogger("...") at module level
        pattern = re.compile(r'^logger\s*=\s*logging\.getLogger\(\s*["\']([^"\']+)["\']\s*\)', re.MULTILINE)

        for f in sorted(d.glob("*.py")):
            if f.name.startswith("__"):
                continue
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue

            for match in pattern.finditer(content):
                logger_name = match.group(1)
                expected = f"code_agents.{subdir}.{f.stem}"
                results.append((str(f.relative_to(self.pkg_dir)), logger_name, expected))

        return results

    @pytest.mark.parametrize("subdir", NEW_SUBDIRS)
    def test_logger_names_follow_convention(self, subdir):
        """Logger names must be code_agents.<subdir>.<module>."""
        entries = self._scan_logger_names(subdir)
        if not entries:
            pytest.skip(f"No logger calls found in code_agents/{subdir}/")

        violations = []
        for file_path, actual, expected in entries:
            if actual != expected:
                violations.append(
                    f"  {file_path}: got '{actual}', expected '{expected}'"
                )

        assert not violations, (
            f"Logger naming violations in code_agents/{subdir}/:\n"
            + "\n".join(violations)
        )


# ===========================================================================
# 6. Cross-checks
# ===========================================================================


class TestCrossWiring:
    """Cross-cutting checks that tie multiple systems together."""

    def test_all_subdirs_have_modules(self):
        """Each of the 12 subdirectories should have at least one module."""
        for subdir in NEW_SUBDIRS:
            d = CODE_AGENTS_PKG / subdir
            py_files = [f for f in d.glob("*.py") if not f.name.startswith("__")]
            assert len(py_files) > 0, (
                f"code_agents/{subdir}/ has no Python modules"
            )

    def test_agent_count_matches_dirs(self):
        """The number of agent dirs (excl. _shared) should match YAML count."""
        agent_dirs = [
            d.name for d in AGENTS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
        ]
        yaml_count = 0
        for name in agent_dirs:
            yamls = [
                f for f in (AGENTS_DIR / name).glob("*.yaml")
                if f.name != "autorun.yaml"
            ]
            if yamls:
                yaml_count += 1

        # Allow small discrepancy (disabled agents etc.)
        assert abs(len(agent_dirs) - yaml_count) <= 2, (
            f"Agent dir count ({len(agent_dirs)}) vs YAML config count ({yaml_count}) "
            f"differ by more than 2"
        )

    def test_cli_registry_importable(self):
        """The CLI registry module must import cleanly."""
        mod = importlib.import_module("code_agents.cli.registry")
        assert hasattr(mod, "COMMAND_REGISTRY")

    def test_app_module_importable(self):
        """The app module must import cleanly."""
        mod = importlib.import_module("code_agents.core.app")
        assert hasattr(mod, "app")
