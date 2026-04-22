"""Tests for code_agents.api_sync."""

import json
import pytest
from code_agents.api.api_sync import ApiSyncer, ApiSyncConfig, ApiSyncResult, format_api_sync


class TestApiSyncer:
    def test_parse_openapi_json(self, tmp_path):
        spec = {"paths": {"/users": {"get": {}, "post": {}}, "/users/{id}": {"get": {}}}}
        (tmp_path / "api.json").write_text(json.dumps(spec))
        syncer = ApiSyncer(ApiSyncConfig(cwd=str(tmp_path)))
        endpoints = syncer._parse_spec(str(tmp_path / "api.json"))
        assert "GET /users" in endpoints
        assert "POST /users" in endpoints
        assert len(endpoints) == 3

    def test_parse_empty_spec(self, tmp_path):
        (tmp_path / "empty.json").write_text("{}")
        syncer = ApiSyncer(ApiSyncConfig(cwd=str(tmp_path)))
        endpoints = syncer._parse_spec(str(tmp_path / "empty.json"))
        assert len(endpoints) == 0

    def test_parse_missing_file(self):
        syncer = ApiSyncer(ApiSyncConfig())
        endpoints = syncer._parse_spec("/nonexistent/api.json")
        assert len(endpoints) == 0

    def test_check_sync_result(self, tmp_path):
        spec = {"paths": {"/users": {"get": {}}}}
        (tmp_path / "api.json").write_text(json.dumps(spec))
        syncer = ApiSyncer(ApiSyncConfig(cwd=str(tmp_path)))
        result = syncer.check_sync("api.json")
        assert result.spec_endpoints == 1
        assert isinstance(result.issues, list)

    def test_format_output(self):
        result = ApiSyncResult(spec_file="api.json", summary="1 endpoint", in_sync=True)
        output = format_api_sync(result)
        assert "API Sync" in output
        assert "Yes" in output
