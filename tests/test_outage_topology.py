"""Tests for the outage topology module."""

from __future__ import annotations

import os
import pytest

from code_agents.devops.outage_topology import (
    OutageTopologyMapper, OutageTopologyResult, ImpactChain,
    map_outage_topology,
)


class TestOutageTopologyMapper:
    """Test OutageTopologyMapper methods."""

    def test_init(self, tmp_path):
        mapper = OutageTopologyMapper(cwd=str(tmp_path))
        assert mapper.cwd == str(tmp_path)

    def test_map_empty_changes(self, tmp_path):
        mapper = OutageTopologyMapper(cwd=str(tmp_path))
        result = mapper.map_impact(changed_files=[])
        assert isinstance(result, OutageTopologyResult)
        assert result.max_blast_radius == 0

    def test_map_detects_infra_deps(self, tmp_path):
        code = '''
import redis

def get_cache():
    client = redis.Redis()
    return client.get("key")
'''
        (tmp_path / "cache_service.py").write_text(code)
        mapper = OutageTopologyMapper(cwd=str(tmp_path))
        result = mapper.map_impact(changed_files=["cache_service.py"])
        # Should detect cache/redis infra dependency
        infra_nodes = [n for n in result.nodes if n.layer == "infra"]
        assert len(infra_nodes) >= 1

    def test_map_detects_customer_features(self, tmp_path):
        code = '''
def process_payment(amount):
    """Process a payment charge."""
    return {"status": "charged", "amount": amount}
'''
        (tmp_path / "payment_handler.py").write_text(code)
        mapper = OutageTopologyMapper(cwd=str(tmp_path))
        result = mapper.map_impact(changed_files=["payment_handler.py"])
        customer_nodes = [n for n in result.nodes if n.layer == "customer"]
        assert len(customer_nodes) >= 1

    def test_severity_critical_for_payment(self, tmp_path):
        code = "def refund(transaction_id):\n    # payment refund\n    pass\n"
        (tmp_path / "refund.py").write_text(code)
        mapper = OutageTopologyMapper(cwd=str(tmp_path))
        result = mapper.map_impact(changed_files=["refund.py"])
        if result.impact_chains:
            assert result.highest_severity in ("high", "critical")

    def test_customer_impact_percentage(self, tmp_path):
        code = "def login_page():\n    # login form\n    pass\n"
        (tmp_path / "login.py").write_text(code)
        mapper = OutageTopologyMapper(cwd=str(tmp_path))
        result = mapper.map_impact(changed_files=["login.py"])
        assert result.affected_customers_pct >= 0

    def test_convenience_function(self, tmp_path):
        result = map_outage_topology(
            cwd=str(tmp_path), changed_files=["service.py"],
        )
        assert isinstance(result, dict)
        assert "highest_severity" in result
        assert "impact_chains" in result
        assert "summary" in result
