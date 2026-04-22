"""Tests for dependency_graph.py — dependency tree builder."""

import os
import tempfile
from pathlib import Path

import pytest

from code_agents.analysis.dependency_graph import DependencyGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def python_repo(tmp_path):
    """Create a minimal Python repo with imports."""
    (tmp_path / "app.py").write_text(
        "import os\n"
        "from utils import helper_func\n"
        "from models import User\n"
        "\n"
        "def main():\n"
        "    path = os.getcwd()\n"
        "    helper_func()\n"
    )

    (tmp_path / "utils.py").write_text(
        "from models import User\n"
        "\n"
        "def helper_func():\n"
        "    return User()\n"
    )

    (tmp_path / "models.py").write_text(
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class User:\n"
        "    name: str = ''\n"
    )

    return tmp_path


@pytest.fixture
def python_circular_repo(tmp_path):
    """Create a Python repo with circular dependencies."""
    (tmp_path / "service_a.py").write_text(
        "from service_b import ServiceB\n"
        "\n"
        "class ServiceA:\n"
        "    pass\n"
    )

    (tmp_path / "service_b.py").write_text(
        "from service_a import ServiceA\n"
        "\n"
        "class ServiceB:\n"
        "    pass\n"
    )

    return tmp_path


@pytest.fixture
def java_repo(tmp_path):
    """Create a minimal Java repo."""
    src = tmp_path / "src" / "main" / "java"
    src.mkdir(parents=True)

    (src / "PaymentService.java").write_text(
        "import com.example.TransactionRepository;\n"
        "import com.example.NotificationService;\n"
        "\n"
        "public class PaymentService {\n"
        "    @Autowired private TransactionRepository txnRepo;\n"
        "\n"
        "    public PaymentService(NotificationService notifService) {\n"
        "    }\n"
        "}\n"
    )

    (src / "PaymentController.java").write_text(
        "import com.example.PaymentService;\n"
        "\n"
        "public class PaymentController {\n"
        "    @Autowired private PaymentService paymentService;\n"
        "}\n"
    )

    return tmp_path


@pytest.fixture
def js_repo(tmp_path):
    """Create a minimal JS/TS repo."""
    (tmp_path / "app.js").write_text(
        "import express from 'express';\n"
        "import { UserService } from './services/user';\n"
        "const db = require('./db');\n"
    )

    services = tmp_path / "services"
    services.mkdir()
    (services / "user.js").write_text(
        "import { Database } from '../db';\n"
        "\n"
        "export class UserService {\n"
        "    constructor(db) { this.db = db; }\n"
        "}\n"
    )

    (tmp_path / "db.js").write_text(
        "export class Database {\n"
        "    connect() {}\n"
        "}\n"
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Python import parsing
# ---------------------------------------------------------------------------

class TestPythonParsing:
    def test_parse_python_imports(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        deps = dg.get_dependencies("app")
        assert "os" in deps
        assert "utils" in deps or "utils.helper_func" in deps
        assert "models" in deps or "models.User" in deps

    def test_parse_python_from_import(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        deps = dg.get_dependencies("utils")
        assert "models" in deps or "models.User" in deps

    def test_all_names_populated(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        assert "app" in dg.all_names
        assert "utils" in dg.all_names
        assert "models" in dg.all_names

    def test_build_sets_built_flag(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        assert not dg._built
        dg.build_graph()
        assert dg._built


# ---------------------------------------------------------------------------
# Java import parsing
# ---------------------------------------------------------------------------

class TestJavaParsing:
    def test_parse_java_imports(self, java_repo):
        dg = DependencyGraph(str(java_repo))
        dg.build_graph()

        deps = dg.get_dependencies("PaymentService")
        assert "TransactionRepository" in deps
        assert "NotificationService" in deps

    def test_parse_java_autowired(self, java_repo):
        dg = DependencyGraph(str(java_repo))
        dg.build_graph()

        deps = dg.get_dependencies("PaymentController")
        assert "PaymentService" in deps

    def test_java_class_names_in_all_names(self, java_repo):
        dg = DependencyGraph(str(java_repo))
        dg.build_graph()

        assert "PaymentService" in dg.all_names
        assert "PaymentController" in dg.all_names


# ---------------------------------------------------------------------------
# JS/TS import parsing
# ---------------------------------------------------------------------------

class TestJsTsParsing:
    def test_parse_es6_import(self, js_repo):
        dg = DependencyGraph(str(js_repo))
        dg.build_graph()

        deps = dg.get_dependencies("app")
        assert "express" in deps

    def test_parse_require(self, js_repo):
        dg = DependencyGraph(str(js_repo))
        dg.build_graph()

        deps = dg.get_dependencies("app")
        assert "db" in deps

    def test_parse_relative_import(self, js_repo):
        dg = DependencyGraph(str(js_repo))
        dg.build_graph()

        deps = dg.get_dependencies("app")
        assert "services.user" in deps or "services/user" in deps


# ---------------------------------------------------------------------------
# get_dependencies / get_dependents
# ---------------------------------------------------------------------------

class TestDependencyQueries:
    def test_get_dependencies_returns_correct(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        deps = dg.get_dependencies("app")
        # app imports os, utils, models
        assert len(deps) >= 3

    def test_get_dependents_returns_correct(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        dependents = dg.get_dependents("models")
        # app and utils both import models
        assert "app" in dependents
        assert "utils" in dependents

    def test_get_dependencies_unknown_name(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        deps = dg.get_dependencies("nonexistent_module_xyz")
        assert deps == set()

    def test_get_dependents_unknown_name(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        dependents = dg.get_dependents("nonexistent_module_xyz")
        assert dependents == set()

    def test_resolve_name_fuzzy(self, java_repo):
        dg = DependencyGraph(str(java_repo))
        dg.build_graph()

        # Should resolve short name to full path
        matches = dg._resolve_name("PaymentService")
        assert len(matches) >= 1


# ---------------------------------------------------------------------------
# Circular dependency detection
# ---------------------------------------------------------------------------

class TestCircularDeps:
    def test_find_circular_deps_detects_cycle(self, python_circular_repo):
        dg = DependencyGraph(str(python_circular_repo))
        dg.build_graph()

        cycles = dg.find_circular_deps()
        assert len(cycles) >= 1

        # Verify the cycle involves service_a and service_b
        cycle_nodes = set()
        for cycle in cycles:
            cycle_nodes.update(cycle)
        assert any("service_a" in n for n in cycle_nodes)
        assert any("service_b" in n for n in cycle_nodes)

    def test_no_circular_deps_in_clean_repo(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        cycles = dg.find_circular_deps()
        # No circular deps in our simple test repo
        assert len(cycles) == 0

    def test_circular_in_get_tree(self, python_circular_repo):
        dg = DependencyGraph(str(python_circular_repo))
        dg.build_graph()

        tree = dg.get_tree("service_a", depth=3)
        assert "circular" in tree
        assert len(tree["circular"]) >= 1


# ---------------------------------------------------------------------------
# Tree formatting
# ---------------------------------------------------------------------------

class TestFormatTree:
    def test_format_tree_output(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        output = dg.format_tree("app")
        assert "Dependency Graph: app" in output
        assert "Uses (outgoing):" in output

    def test_format_tree_contains_deps(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        output = dg.format_tree("models")
        assert "Used by (incoming):" in output
        # app and utils use models
        assert "app" in output
        assert "utils" in output

    def test_format_tree_unknown_name(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        output = dg.format_tree("nonexistent")
        assert "Uses (outgoing): (none)" in output
        assert "Used by (incoming): (none)" in output

    def test_format_tree_circular_warning(self, python_circular_repo):
        dg = DependencyGraph(str(python_circular_repo))
        dg.build_graph()

        output = dg.format_tree("service_a")
        assert "Circular dependency detected" in output or "cycle" in output.lower()


# ---------------------------------------------------------------------------
# Depth limiting
# ---------------------------------------------------------------------------

class TestDepthLimiting:
    def test_depth_zero(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        tree = dg.get_tree("app", depth=0)
        assert tree["uses"] == {}
        assert tree["used_by"] == {}

    def test_depth_one_limits_recursion(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        tree = dg.get_tree("app", direction="out", depth=1)
        # Depth 1: app -> its deps, but deps don't expand further
        for child_tree in tree["uses"].values():
            assert child_tree == {}

    def test_depth_three_default(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        tree = dg.get_tree("app", depth=3)
        # Should have expanded at least one level
        assert isinstance(tree["uses"], dict)

    def test_get_tree_direction_out(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        tree = dg.get_tree("app", direction="out", depth=2)
        assert tree["used_by"] == {}

    def test_get_tree_direction_in(self, python_repo):
        dg = DependencyGraph(str(python_repo))
        dg.build_graph()

        tree = dg.get_tree("models", direction="in", depth=2)
        assert tree["uses"] == {}
        assert len(tree["used_by"]) >= 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_repo(self, tmp_path):
        dg = DependencyGraph(str(tmp_path))
        dg.build_graph()

        assert len(dg.all_names) == 0
        assert dg.find_circular_deps() == []

    def test_syntax_error_file_skipped(self, tmp_path):
        (tmp_path / "bad.py").write_text("def foo(\n")  # syntax error
        (tmp_path / "good.py").write_text("import os\n")

        dg = DependencyGraph(str(tmp_path))
        dg.build_graph()

        assert "good" in dg.all_names

    def test_skip_dirs(self, tmp_path):
        node_modules = tmp_path / "node_modules" / "pkg"
        node_modules.mkdir(parents=True)
        (node_modules / "index.js").write_text("import foo from 'bar';")

        (tmp_path / "app.js").write_text("import foo from 'bar';")

        dg = DependencyGraph(str(tmp_path))
        dg.build_graph()

        # Should only have app, not node_modules content
        assert not any("node_modules" in n for n in dg.all_names)
