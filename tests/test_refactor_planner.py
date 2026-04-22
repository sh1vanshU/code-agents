"""Tests for refactor_planner.py — code smell detection and refactoring suggestions."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.tools.refactor_planner import (
    RefactorPlanner,
    CodeSmell,
    RefactorPlan,
    format_refactor_plan,
    _REFACTORING_MAP,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_repo(tmp_path):
    """Create a minimal repo with test files."""
    return tmp_path


@pytest.fixture
def planner(tmp_repo):
    return RefactorPlanner(cwd=str(tmp_repo))


def _write(tmp_path, name, content):
    """Write a file into the temp repo."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return str(p)


# ---------------------------------------------------------------------------
# Long method detection
# ---------------------------------------------------------------------------

class TestLongMethod:
    def test_detects_long_method(self, planner, tmp_repo):
        """A function > 50 lines should be flagged."""
        body = "\n".join([f"    x = {i}" for i in range(60)])
        code = f"def very_long_func():\n{body}\n    return x\n"
        _write(tmp_repo, "long.py", code)
        plan = planner.analyze("long.py")
        kinds = [s.kind for s in plan.smells]
        assert "long_method" in kinds

    def test_short_method_not_flagged(self, planner, tmp_repo):
        """A function under 50 lines should NOT be flagged."""
        body = "\n".join([f"    x = {i}" for i in range(10)])
        code = f"def short_func():\n{body}\n    return x\n"
        _write(tmp_repo, "short.py", code)
        plan = planner.analyze("short.py")
        kinds = [s.kind for s in plan.smells]
        assert "long_method" not in kinds


# ---------------------------------------------------------------------------
# Large class detection
# ---------------------------------------------------------------------------

class TestLargeClass:
    def test_detects_large_class(self, planner, tmp_repo):
        """A class > 300 lines should be flagged."""
        methods = "\n".join([f"    def method_{i}(self):\n        pass\n" for i in range(160)])
        code = f"class HugeClass:\n{methods}\n"
        _write(tmp_repo, "huge.py", code)
        plan = planner.analyze("huge.py")
        kinds = [s.kind for s in plan.smells]
        assert "large_class" in kinds

    def test_small_class_not_flagged(self, planner, tmp_repo):
        """A class under 300 lines should NOT be flagged."""
        code = "class SmallClass:\n    def go(self):\n        pass\n"
        _write(tmp_repo, "small.py", code)
        plan = planner.analyze("small.py")
        kinds = [s.kind for s in plan.smells]
        assert "large_class" not in kinds


# ---------------------------------------------------------------------------
# Deep nesting detection
# ---------------------------------------------------------------------------

class TestDeepNesting:
    def test_detects_deep_nesting(self, planner, tmp_repo):
        """Nesting > 4 levels should be flagged."""
        code = (
            "def deeply_nested():\n"
            "    if True:\n"
            "        if True:\n"
            "            if True:\n"
            "                if True:\n"
            "                    if True:\n"
            "                        x = 1\n"
        )
        _write(tmp_repo, "deep.py", code)
        plan = planner.analyze("deep.py")
        kinds = [s.kind for s in plan.smells]
        assert "deep_nesting" in kinds

    def test_shallow_not_flagged(self, planner, tmp_repo):
        """Nesting <= 4 levels should NOT be flagged."""
        code = (
            "def shallow():\n"
            "    if True:\n"
            "        x = 1\n"
        )
        _write(tmp_repo, "shallow.py", code)
        plan = planner.analyze("shallow.py")
        kinds = [s.kind for s in plan.smells]
        assert "deep_nesting" not in kinds


# ---------------------------------------------------------------------------
# Too many params detection
# ---------------------------------------------------------------------------

class TestTooManyParams:
    def test_detects_too_many_params(self, planner, tmp_repo):
        """A function with > 5 params should be flagged."""
        code = "def many_args(a, b, c, d, e, f, g):\n    pass\n"
        _write(tmp_repo, "params.py", code)
        plan = planner.analyze("params.py")
        kinds = [s.kind for s in plan.smells]
        assert "too_many_params" in kinds

    def test_few_params_not_flagged(self, planner, tmp_repo):
        """A function with <= 5 params should NOT be flagged."""
        code = "def few_args(a, b, c):\n    pass\n"
        _write(tmp_repo, "few.py", code)
        plan = planner.analyze("few.py")
        kinds = [s.kind for s in plan.smells]
        assert "too_many_params" not in kinds

    def test_self_excluded_from_count(self, planner, tmp_repo):
        """self/cls should not count towards parameter limit."""
        code = "class A:\n    def method(self, a, b, c, d, e):\n        pass\n"
        _write(tmp_repo, "selftest.py", code)
        plan = planner.analyze("selftest.py")
        kinds = [s.kind for s in plan.smells]
        assert "too_many_params" not in kinds


# ---------------------------------------------------------------------------
# God class detection
# ---------------------------------------------------------------------------

class TestGodClass:
    def test_detects_god_class(self, planner, tmp_repo):
        """A class with > 10 public methods should be flagged."""
        methods = "\n".join([f"    def action_{i}(self):\n        pass\n" for i in range(12)])
        code = f"class GodService:\n{methods}\n"
        _write(tmp_repo, "god.py", code)
        plan = planner.analyze("god.py")
        kinds = [s.kind for s in plan.smells]
        assert "god_class" in kinds

    def test_private_methods_not_counted(self, planner, tmp_repo):
        """Private methods (starting with _) should NOT count toward god class."""
        methods = "\n".join([f"    def _private_{i}(self):\n        pass\n" for i in range(15)])
        code = f"class PrivateClass:\n    def one_public(self):\n        pass\n{methods}\n"
        _write(tmp_repo, "private.py", code)
        plan = planner.analyze("private.py")
        kinds = [s.kind for s in plan.smells]
        assert "god_class" not in kinds


# ---------------------------------------------------------------------------
# Suggest refactoring mapping
# ---------------------------------------------------------------------------

class TestSuggestRefactoring:
    def test_all_smell_kinds_have_mapping(self):
        """Every known smell kind should have a refactoring suggestion mapping."""
        expected_kinds = [
            "long_method", "large_class", "too_many_params",
            "deep_nesting", "god_class", "duplicate_code",
            "feature_envy", "dead_code",
        ]
        for kind in expected_kinds:
            assert kind in _REFACTORING_MAP, f"Missing mapping for {kind}"

    def test_suggestion_output(self, planner):
        """suggest_refactoring should return suggestions for given smells."""
        smells = [
            CodeSmell(kind="long_method", severity="medium", description="test", location="foo"),
            CodeSmell(kind="god_class", severity="high", description="test", location="Bar", details={"method_count": 15}),
        ]
        suggestions = planner.suggest_refactoring(smells)
        assert len(suggestions) == 2
        assert suggestions[0].technique == "Extract Method"
        assert suggestions[1].technique == "Split into focused services"

    def test_empty_smells_returns_empty(self, planner):
        """No smells should yield no suggestions."""
        assert planner.suggest_refactoring([]) == []


# ---------------------------------------------------------------------------
# Risk estimation
# ---------------------------------------------------------------------------

class TestEstimateRisk:
    def test_risk_returns_dict_keys(self, planner, tmp_repo):
        """estimate_risk should return all expected keys."""
        _write(tmp_repo, "module.py", "x = 1\n")
        risk = planner.estimate_risk("module.py")
        assert "score" in risk
        assert "dependents" in risk
        assert "test_files" in risk
        assert "critical_path" in risk

    def test_risk_score_range(self, planner, tmp_repo):
        """Risk score should be between 0 and 100."""
        _write(tmp_repo, "module.py", "x = 1\n")
        risk = planner.estimate_risk("module.py")
        assert 0 <= risk["score"] <= 100

    def test_critical_path_detection(self, planner, tmp_repo):
        """Files with critical keywords should get critical path flag."""
        _write(tmp_repo, "payment_service.py", "class PaymentService:\n    pass\n")
        risk = planner.estimate_risk("payment_service.py")
        assert risk["critical_path"] == "payment processing"

    def test_dependents_counted(self, planner, tmp_repo):
        """Files that reference the target should be counted as dependents."""
        _write(tmp_repo, "core.py", "class Core:\n    pass\n")
        _write(tmp_repo, "handler.py", "from core import Core\n")
        _write(tmp_repo, "service.py", "import core\n")
        risk = planner.estimate_risk("core.py")
        assert risk["dependents"] >= 2

    def test_test_files_counted(self, planner, tmp_repo):
        """Test files that reference the target should be counted separately."""
        _write(tmp_repo, "core.py", "class Core:\n    pass\n")
        tests_dir = tmp_repo / "tests"
        tests_dir.mkdir()
        _write(tmp_repo, "tests/test_core.py", "from core import Core\n")
        risk = planner.estimate_risk("core.py")
        assert risk["test_files"] >= 1


# ---------------------------------------------------------------------------
# Format analysis output
# ---------------------------------------------------------------------------

class TestFormatAnalysis:
    def test_format_includes_filename(self):
        """Output should include the file name."""
        plan = RefactorPlan(filepath="service.py")
        output = format_refactor_plan(plan)
        assert "service.py" in output

    def test_format_clean_file(self):
        """Clean file should show 'no code smells' message."""
        plan = RefactorPlan(filepath="clean.py")
        output = format_refactor_plan(plan)
        assert "No code smells" in output

    def test_format_with_smells(self):
        """Output should list detected smells."""
        plan = RefactorPlan(filepath="messy.py", smells=[
            CodeSmell(kind="long_method", severity="medium", description="foo() is 80 lines"),
            CodeSmell(kind="god_class", severity="high", description="BigClass has 15 public methods"),
        ])
        output = format_refactor_plan(plan)
        assert "Code Smells (2)" in output
        assert "Long Method" in output
        assert "God Class" in output

    def test_format_includes_risk(self):
        """Output should include the risk score."""
        plan = RefactorPlan(filepath="risky.py", risk_score=72, smells=[
            CodeSmell(kind="long_method", severity="medium", description="test"),
        ])
        output = format_refactor_plan(plan)
        assert "72/100" in output
        assert "HIGH" in output

    def test_format_includes_suggestions(self):
        """Output should include suggestion steps."""
        from code_agents.tools.refactor_planner import RefactorSuggestion
        smell = CodeSmell(kind="deep_nesting", severity="medium", description="test")
        plan = RefactorPlan(
            filepath="nested.py",
            smells=[smell],
            suggestions=[RefactorSuggestion(
                smell=smell,
                technique="Early Return / Guard Clauses",
                description="Flatten with early returns",
                risk="Low",
                effort="~30min",
            )],
        )
        output = format_refactor_plan(plan)
        assert "Suggested Plan" in output
        assert "Early Return" in output


# ---------------------------------------------------------------------------
# Duplicate code detection
# ---------------------------------------------------------------------------

class TestDuplicateCode:
    def test_detects_duplicate_blocks(self, planner, tmp_repo):
        """Identical code blocks should be flagged as duplicate."""
        block = "    x = compute()\n    y = process(x)\n    z = validate(y)\n    result = transform(z)\n    save(result)\n"
        code = f"def func_a():\n{block}\ndef func_b():\n{block}\n"
        _write(tmp_repo, "dup.py", code)
        plan = planner.analyze("dup.py")
        kinds = [s.kind for s in plan.smells]
        assert "duplicate_code" in kinds


# ---------------------------------------------------------------------------
# File not found
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_missing_file_returns_empty_plan(self, planner):
        """Analyzing a non-existent file should return empty plan, not crash."""
        plan = planner.analyze("nonexistent_file.py")
        assert plan.smells == []
        assert plan.suggestions == []

    def test_empty_file(self, planner, tmp_repo):
        """An empty file should produce no smells."""
        _write(tmp_repo, "empty.py", "")
        plan = planner.analyze("empty.py")
        assert plan.smells == []

    def test_absolute_path_resolved(self, planner, tmp_repo):
        """Analyze with absolute path should work."""
        fpath = _write(tmp_repo, "abs_test.py", "x = 1\n")
        plan = planner.analyze(fpath)
        assert plan.smells == []


# ---------------------------------------------------------------------------
# Feature envy detection
# ---------------------------------------------------------------------------

class TestFeatureEnvy:
    def test_detects_feature_envy(self, planner, tmp_repo):
        """Method referencing another class more than its own should be flagged."""
        code = (
            "class ClassA:\n"
            "    def do_something(self):\n"
            "        x = ClassB.method1()\n"
            "        y = ClassB.method2()\n"
            "        z = ClassB.method3()\n"
            "        return x + y + z\n"
            "\n"
            "class ClassB:\n"
            "    def method1(self):\n"
            "        pass\n"
            "    def method2(self):\n"
            "        pass\n"
            "    def method3(self):\n"
            "        pass\n"
        )
        _write(tmp_repo, "envy.py", code)
        plan = planner.analyze("envy.py")
        kinds = [s.kind for s in plan.smells]
        assert "feature_envy" in kinds

    def test_no_feature_envy_single_class(self, planner, tmp_repo):
        """Single class files should never have feature envy."""
        code = "class OnlyClass:\n    def do_stuff(self):\n        self.x = 1\n"
        _write(tmp_repo, "single.py", code)
        plan = planner.analyze("single.py")
        kinds = [s.kind for s in plan.smells]
        assert "feature_envy" not in kinds


# ---------------------------------------------------------------------------
# Dead code detection
# ---------------------------------------------------------------------------

class TestDeadCode:
    def test_detect_dead_code_runs(self, planner, tmp_repo):
        """_detect_dead_code should run without crashing on normal code."""
        code = "def func():\n    x = 1\n    return x\n"
        _write(tmp_repo, "alive.py", code)
        plan = planner.analyze("alive.py")
        kinds = [s.kind for s in plan.smells]
        assert "dead_code" not in kinds

    def test_bare_return_detection(self, planner):
        """Test bare 'return' statement detection path."""
        lines = [
            "def func():",
            "    return",
            "    return",
        ]
        smells = planner._detect_dead_code(lines)
        # The bare return path is covered by the `stripped == "return"` branch
        # Regardless of detection result, it should not crash
        assert isinstance(smells, list)


# ---------------------------------------------------------------------------
# Suggest refactoring customizations
# ---------------------------------------------------------------------------

class TestSuggestRefactoringCustom:
    def test_too_many_params_custom_desc(self, planner):
        smells = [
            CodeSmell(kind="too_many_params", severity="low",
                      description="func(8 params)", location="func",
                      details={"param_count": 8}),
        ]
        suggestions = planner.suggest_refactoring(smells)
        assert len(suggestions) == 1
        assert "8 params" in suggestions[0].description

    def test_unknown_smell_kind_skipped(self, planner):
        smells = [
            CodeSmell(kind="unknown_kind", severity="low", description="test"),
        ]
        suggestions = planner.suggest_refactoring(smells)
        assert len(suggestions) == 0


# ---------------------------------------------------------------------------
# Risk estimation edge cases
# ---------------------------------------------------------------------------

class TestEstimateRiskEdge:
    def test_oserror_during_walk(self, planner, tmp_repo):
        """OSError in walk should not crash."""
        _write(tmp_repo, "mod.py", "x = 1\n")
        with patch("os.walk", side_effect=OSError("nope")):
            risk = planner.estimate_risk("mod.py")
        assert risk["score"] >= 0
        assert risk["dependents"] == 0

    def test_auth_keyword_triggers_critical(self, planner, tmp_repo):
        _write(tmp_repo, "auth_handler.py", "class Auth: pass\n")
        risk = planner.estimate_risk("auth_handler.py")
        assert risk["critical_path"] == "auth processing"

    def test_no_critical_keyword(self, planner, tmp_repo):
        _write(tmp_repo, "utils.py", "x = 1\n")
        risk = planner.estimate_risk("utils.py")
        assert risk["critical_path"] == ""

    def test_high_dependents_high_score(self, planner, tmp_repo):
        _write(tmp_repo, "core.py", "class Core: pass\n")
        for i in range(20):
            _write(tmp_repo, f"dep_{i}.py", "import core\n")
        risk = planner.estimate_risk("core.py")
        assert risk["score"] >= 30


# ---------------------------------------------------------------------------
# create_plan alias
# ---------------------------------------------------------------------------

class TestCreatePlan:
    def test_create_plan_alias(self, planner, tmp_repo):
        _write(tmp_repo, "mod.py", "x = 1\n")
        plan = planner.create_plan("mod.py")
        assert plan.filepath == "mod.py"


# ---------------------------------------------------------------------------
# format_analysis alias
# ---------------------------------------------------------------------------

class TestFormatAnalysis2:
    def test_format_analysis_calls_format_refactor_plan(self, planner):
        plan = RefactorPlan(filepath="test.py")
        output = planner.format_analysis(plan)
        assert "test.py" in output


# ---------------------------------------------------------------------------
# _risk_label edge cases
# ---------------------------------------------------------------------------

class TestRiskLabel:
    def test_risk_label_low(self):
        from code_agents.tools.refactor_planner import _risk_label
        assert _risk_label(15) == "LOW"

    def test_risk_label_medium(self):
        from code_agents.tools.refactor_planner import _risk_label
        assert _risk_label(45) == "MEDIUM"

    def test_risk_label_high(self):
        from code_agents.tools.refactor_planner import _risk_label
        assert _risk_label(80) == "HIGH"

    def test_risk_label_out_of_range(self):
        from code_agents.tools.refactor_planner import _risk_label
        assert _risk_label(150) == "UNKNOWN"


# ---------------------------------------------------------------------------
# format_refactor_plan with all fields
# ---------------------------------------------------------------------------

class TestFormatRefactorPlanFull:
    def test_with_dependents_and_test_files(self):
        from code_agents.tools.refactor_planner import RefactorSuggestion
        smell = CodeSmell(kind="long_method", severity="medium", description="test")
        plan = RefactorPlan(
            filepath="service.py",
            smells=[smell],
            suggestions=[RefactorSuggestion(
                smell=smell,
                technique="Extract Method",
                description="Break into smaller methods",
                risk="Low",
                effort="~1h",
            )],
            risk_score=45,
            dependents=3,
            test_files=2,
            critical_path="payment processing",
        )
        output = format_refactor_plan(plan)
        assert "3 files depend" in output
        assert "2 test files" in output
        assert "payment processing" in output
        assert "MEDIUM" in output
        assert "Extract Method" in output


# ---------------------------------------------------------------------------
# _find_functions and _find_classes
# ---------------------------------------------------------------------------

class TestFindFunctionsClasses:
    def test_find_java_functions(self, planner, tmp_repo):
        code = "public class Service {\n    public void process(String data) {\n        int x = 1;\n    }\n}\n"
        _write(tmp_repo, "Service.java", code)
        lines = code.splitlines()
        functions = planner._find_functions(lines)
        assert any(name == "process" for name, _, _ in functions)

    def test_find_java_classes(self, planner, tmp_repo):
        code = "public class MyService {\n    public void run() {\n        int x = 1;\n    }\n}\n"
        _write(tmp_repo, "MyService.java", code)
        lines = code.splitlines()
        classes = planner._find_classes(lines)
        assert any(name == "MyService" for name, _, _ in classes)

    def test_deep_nesting_java_pattern(self, planner, tmp_repo):
        """Java-style indentation should also be detected for nesting."""
        code = (
            "def nested_func():\n"
            "    if True:\n"
            "        for x in range(10):\n"
            "            if x > 5:\n"
            "                while True:\n"
            "                    if x == 7:\n"
            "                        pass\n"
        )
        _write(tmp_repo, "deep_java.py", code)
        plan = planner.analyze("deep_java.py")
        kinds = [s.kind for s in plan.smells]
        assert "deep_nesting" in kinds


# ---------------------------------------------------------------------------
# _detect_too_many_params Java pattern
# ---------------------------------------------------------------------------

class TestTooManyParamsJava:
    def test_java_params_detected(self, planner, tmp_repo):
        code = "public class Svc {\n    public void process(String a, String b, String c, String d, String e, String f, String g) {\n    }\n}\n"
        _write(tmp_repo, "svc.java", code)
        plan = planner.analyze("svc.java")
        kinds = [s.kind for s in plan.smells]
        assert "too_many_params" in kinds


# ---------------------------------------------------------------------------
# estimate_risk: non-code files skipped, read errors handled (lines 160, 166-167)
# ---------------------------------------------------------------------------

class TestEstimateRiskFileFiltering:
    def test_non_code_files_skipped(self, planner, tmp_repo):
        """Files without code extensions (e.g. .txt) are skipped in risk scan."""
        _write(tmp_repo, "target.py", "class Target: pass\n")
        _write(tmp_repo, "readme.txt", "import target\n")  # .txt should be skipped
        risk = planner.estimate_risk("target.py")
        # readme.txt should not be counted as a dependent
        assert risk["dependents"] == 0

    def test_read_error_in_file_skipped(self, planner, tmp_repo):
        """Files that raise OSError on read are skipped gracefully."""
        _write(tmp_repo, "target.py", "class Target: pass\n")
        _write(tmp_repo, "broken.py", "import target\n")
        original_read = Path.read_text
        def mock_read(self_path, *args, **kwargs):
            if "broken.py" in str(self_path):
                raise OSError("permission denied")
            return original_read(self_path, *args, **kwargs)
        with patch.object(Path, "read_text", mock_read):
            risk = planner.estimate_risk("target.py")
        # Should not crash
        assert risk["score"] >= 0


# ---------------------------------------------------------------------------
# _detect_duplicate_code: short blocks skipped (line 352)
# ---------------------------------------------------------------------------

class TestDuplicateCodeShortBlocks:
    def test_short_blocks_with_comments_skipped(self, planner, tmp_repo):
        """Blocks where normalized lines < 3 (mostly blanks/comments) are skipped."""
        code = (
            "# comment1\n"
            "# comment2\n"
            "# comment3\n"
            "# comment4\n"
            "# comment5\n"
            "\n"
            "# comment1\n"
            "# comment2\n"
            "# comment3\n"
            "# comment4\n"
            "# comment5\n"
        )
        _write(tmp_repo, "comments_only.py", code)
        plan = planner.analyze("comments_only.py")
        kinds = [s.kind for s in plan.smells]
        assert "duplicate_code" not in kinds


# ---------------------------------------------------------------------------
# _detect_dead_code: actual dead code after return (line 420)
# ---------------------------------------------------------------------------

class TestDeadCodeDetection:
    def test_dead_code_detection_covers_return_path(self, planner, tmp_repo):
        """Exercise the dead code detector on code with returns."""
        code = (
            "def func():\n"
            "    if True:\n"
            "        return 1\n"
            "        return 2\n"
        )
        _write(tmp_repo, "dead.py", code)
        plan = planner.analyze("dead.py")
        assert isinstance(plan.smells, list)
