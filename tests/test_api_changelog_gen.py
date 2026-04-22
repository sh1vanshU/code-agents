"""Tests for code_agents.api_changelog_gen."""

import json
import pytest
from code_agents.api.api_changelog_gen import ApiChangelogGenerator, ApiChangelogResult, format_api_changelog


class TestApiChangelogGenerator:
    def test_diff_added_endpoints(self):
        old = {"GET /users": {}}
        new = {"GET /users": {}, "POST /users": {}}
        result = ApiChangelogGenerator().diff_dicts(old, new)
        assert result.added_count == 1
        assert any(c.change_type == "added" for c in result.changes)

    def test_diff_removed_endpoints(self):
        old = {"GET /users": {}, "DELETE /users/{id}": {}}
        new = {"GET /users": {}}
        result = ApiChangelogGenerator().diff_dicts(old, new)
        assert result.removed_count == 1
        assert any(c.breaking for c in result.changes)

    def test_diff_no_changes(self):
        endpoints = {"GET /users": {}, "POST /users": {}}
        result = ApiChangelogGenerator().diff_dicts(endpoints, endpoints)
        assert len(result.changes) == 0

    def test_diff_specs_from_files(self, tmp_path):
        old_spec = {"paths": {"/users": {"get": {}}}}
        new_spec = {"paths": {"/users": {"get": {}, "post": {}}}}
        (tmp_path / "v1.json").write_text(json.dumps(old_spec))
        (tmp_path / "v2.json").write_text(json.dumps(new_spec))

        gen = ApiChangelogGenerator()
        gen.config.cwd = str(tmp_path)
        result = gen.diff_specs("v1.json", "v2.json")
        assert result.added_count == 1

    def test_removed_is_breaking(self):
        old = {"GET /api": {}, "DELETE /api": {}}
        new = {}
        result = ApiChangelogGenerator().diff_dicts(old, new)
        assert result.breaking_count == 2

    def test_format_output(self):
        result = ApiChangelogResult(summary="3 changes")
        output = format_api_changelog(result)
        assert "Changelog" in output
