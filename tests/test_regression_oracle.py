"""Tests for the regression oracle module."""

from __future__ import annotations

import os
import pytest

from code_agents.testing.regression_oracle import (
    RegressionOracle, RegressionOracleResult, RegressionRisk,
    predict_regressions,
)


class TestRegressionOracle:
    """Test RegressionOracle methods."""

    def test_init(self, tmp_path):
        oracle = RegressionOracle(cwd=str(tmp_path))
        assert oracle.cwd == str(tmp_path)

    def test_predict_no_changes(self, tmp_path):
        oracle = RegressionOracle(cwd=str(tmp_path))
        result = oracle.predict(changed_files=[])
        assert isinstance(result, RegressionOracleResult)
        assert len(result.risks) == 0

    def test_predict_direct_change(self, tmp_path):
        (tmp_path / "auth.py").write_text(
            "def login(user, password):\n    return True\n"
        )
        oracle = RegressionOracle(cwd=str(tmp_path))
        result = oracle.predict(changed_files=["auth.py"])
        assert len(result.risks) >= 1
        auth_risk = next((r for r in result.risks if "auth" in r.file), None)
        assert auth_risk is not None
        assert auth_risk.risk_score >= 50  # direct change = high risk

    def test_predict_from_diff(self, tmp_path):
        (tmp_path / "service.py").write_text("def process():\n    pass\n")
        diff = """diff --git a/service.py b/service.py
--- a/service.py
+++ b/service.py
@@ -1,2 +1,3 @@
 def process():
-    pass
+    return True
"""
        oracle = RegressionOracle(cwd=str(tmp_path))
        result = oracle.predict(diff_content=diff)
        assert len(result.change_analysis.changed_files) >= 1

    def test_recommended_tests(self, tmp_path):
        (tmp_path / "payment.py").write_text("def charge(amount):\n    pass\n")
        oracle = RegressionOracle(cwd=str(tmp_path))
        result = oracle.predict(changed_files=["payment.py"])
        assert len(result.recommended_tests) >= 1
        assert any("test_payment" in t for t in result.recommended_tests)

    def test_safe_to_deploy(self, tmp_path):
        (tmp_path / "readme.py").write_text("# Simple helper\ndef noop():\n    pass\n")
        oracle = RegressionOracle(cwd=str(tmp_path))
        result = oracle.predict(changed_files=["readme.py"])
        assert isinstance(result.safe_to_deploy, bool)

    def test_convenience_function(self, tmp_path):
        result = predict_regressions(cwd=str(tmp_path), changed_files=["foo.py"])
        assert isinstance(result, dict)
        assert "safe_to_deploy" in result
        assert "risks" in result
        assert "recommended_tests" in result
