"""Tests for the ADR generator."""

from __future__ import annotations

import os
import pytest

from code_agents.knowledge.adr_generator import ADR, ADRGenerator, format_adr_table


class TestADR:
    """Test the ADR dataclass."""

    def test_valid_statuses(self):
        for status in ("proposed", "accepted", "deprecated"):
            adr = ADR(id=1, title="Test", date="2026-01-01", status=status,
                      context="ctx", decision="dec")
            assert adr.status == status

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="Invalid ADR status"):
            ADR(id=1, title="Test", date="2026-01-01", status="invalid",
                context="ctx", decision="dec")

    def test_defaults(self):
        adr = ADR(id=1, title="T", date="2026-01-01", status="proposed",
                  context="c", decision="d")
        assert adr.alternatives == []
        assert adr.consequences == []


class TestADRGenerator:
    """Test ADRGenerator methods."""

    def test_generate_basic(self, tmp_path):
        gen = ADRGenerator(cwd=str(tmp_path))
        adr = gen.generate(decision="Use PostgreSQL for the data layer")
        assert adr.id == 1
        assert adr.status == "proposed"
        assert "PostgreSQL" in adr.title
        assert adr.decision == "Use PostgreSQL for the data layer"
        assert adr.date  # non-empty

    def test_generate_with_alternatives(self, tmp_path):
        gen = ADRGenerator(cwd=str(tmp_path))
        adr = gen.generate(
            decision="Use Redis for caching",
            alternatives="Memcached, In-memory dict",
        )
        assert len(adr.alternatives) == 2
        assert "Memcached" in adr.alternatives
        assert "In-memory dict" in adr.alternatives

    def test_generate_with_context(self, tmp_path):
        gen = ADRGenerator(cwd=str(tmp_path))
        adr = gen.generate(
            decision="Adopt FastAPI",
            context="We need an async web framework",
        )
        assert adr.context == "We need an async web framework"

    def test_generate_increments_id(self, tmp_path):
        adr_dir = tmp_path / "docs" / "decisions"
        adr_dir.mkdir(parents=True)
        (adr_dir / "DECISION_first.md").write_text(
            "# ADR-0001: First\n\n**Status**: proposed\n**Date**: 2026-01-01\n"
        )

        gen = ADRGenerator(cwd=str(tmp_path))
        adr = gen.generate(decision="Second decision")
        assert adr.id == 2

    def test_save_creates_file(self, tmp_path):
        gen = ADRGenerator(cwd=str(tmp_path))
        adr = gen.generate(decision="Use Docker for deployments")
        filepath = gen.save(adr)

        assert os.path.exists(filepath)
        content = open(filepath).read()
        assert "ADR-0001" in content
        assert "Docker" in content
        assert "**Status**: proposed" in content

    def test_list_adrs_empty(self, tmp_path):
        gen = ADRGenerator(cwd=str(tmp_path))
        assert gen.list_adrs() == []

    def test_list_adrs_finds_files(self, tmp_path):
        adr_dir = tmp_path / "docs" / "decisions"
        adr_dir.mkdir(parents=True)
        (adr_dir / "DECISION_use_postgres.md").write_text(
            "# ADR-0001: Use Postgres\n\n**Date**: 2026-04-01\n**Status**: accepted\n"
        )
        (adr_dir / "DECISION_use_redis.md").write_text(
            "# ADR-0002: Use Redis\n\n**Date**: 2026-04-02\n**Status**: proposed\n"
        )

        gen = ADRGenerator(cwd=str(tmp_path))
        adrs = gen.list_adrs()
        assert len(adrs) == 2
        assert adrs[0]["id"] == 1
        assert adrs[1]["id"] == 2

    def test_template_has_sections(self, tmp_path):
        gen = ADRGenerator(cwd=str(tmp_path))
        adr = gen.generate(
            decision="Use gRPC for inter-service communication",
            alternatives="REST, GraphQL",
        )
        content = gen._template(adr)
        assert "## Context" in content
        assert "## Decision" in content
        assert "## Alternatives Considered" in content
        assert "## Consequences" in content
        assert "REST" in content
        assert "GraphQL" in content

    def test_adr_dir_detection(self, tmp_path):
        # Create docs/adr/ directory (alternative convention)
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)

        gen = ADRGenerator(cwd=str(tmp_path))
        assert gen.adr_dir == str(adr_dir)


class TestFormatAdrTable:
    """Test the format_adr_table helper."""

    def test_empty(self):
        result = format_adr_table([])
        assert "No ADRs found" in result

    def test_with_entries(self):
        entries = [
            {"id": 1, "title": "Use Postgres", "status": "accepted", "date": "2026-01-01"},
            {"id": 2, "title": "Use Redis", "status": "proposed", "date": "2026-01-02"},
        ]
        result = format_adr_table(entries)
        assert "Use Postgres" in result
        assert "Use Redis" in result
        assert "accepted" in result
