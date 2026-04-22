"""Tests for redash_client.py — unit tests with mocked HTTP."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from code_agents.integrations.redash_client import RedashClient, RedashError


class TestRedashClientInit:
    def test_init_with_api_key(self):
        c = RedashClient(base_url="https://redash.example.com", api_key="my-key")
        assert c.base_url == "https://redash.example.com"
        assert c.api_key == "my-key"
        assert c._session.headers.get("Authorization") == "Key my-key"

    def test_init_strips_trailing_slash(self):
        c = RedashClient(base_url="https://redash.example.com/", api_key="k")
        assert c.base_url == "https://redash.example.com"

    def test_init_defaults(self):
        c = RedashClient(base_url="https://redash.example.com", api_key="k")
        assert c.timeout == 30.0
        assert c.poll_interval == 1.0
        assert c.poll_timeout == 300.0

    @patch.object(RedashClient, "_login")
    def test_init_with_username_password_calls_login(self, mock_login):
        c = RedashClient(
            base_url="https://redash.example.com",
            username="user@example.com",
            password="secret",
        )
        mock_login.assert_called_once()
        assert c.username == "user@example.com"
        assert c.password == "secret"

    def test_init_no_auth(self):
        c = RedashClient(base_url="https://redash.example.com")
        assert "Authorization" not in c._session.headers


class TestRedashClientLogin:
    def test_login_success(self):
        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.url = "https://redash.example.com/"
            mock_session.post.return_value = mock_resp
            mock_session.headers = {"Content-Type": "application/json"}
            MockSession.return_value = mock_session

            c = RedashClient.__new__(RedashClient)
            c.base_url = "https://redash.example.com"
            c.username = "user@test.com"
            c.password = "pass"
            c.timeout = 30.0
            c._session = mock_session
            c._login()

            mock_session.post.assert_called_once()
            call_kwargs = mock_session.post.call_args
            assert call_kwargs[1]["data"]["email"] == "user@test.com"

    def test_login_failure_http_error(self):
        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.text = "Unauthorized"
            mock_session.post.return_value = mock_resp
            mock_session.headers = {"Content-Type": "application/json"}
            MockSession.return_value = mock_session

            c = RedashClient.__new__(RedashClient)
            c.base_url = "https://redash.example.com"
            c.username = "user"
            c.password = "wrong"
            c.timeout = 30.0
            c._session = mock_session

            with pytest.raises(RedashError, match="Login failed"):
                c._login()

    def test_login_failure_redirect_to_login(self):
        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.url = "https://redash.example.com/login"
            mock_session.post.return_value = mock_resp
            mock_session.headers = {"Content-Type": "application/json"}
            MockSession.return_value = mock_session

            c = RedashClient.__new__(RedashClient)
            c.base_url = "https://redash.example.com"
            c.username = "user"
            c.password = "wrong"
            c.timeout = 30.0
            c._session = mock_session

            with pytest.raises(RedashError, match="invalid username or password"):
                c._login()


class TestRedashClientListDataSources:
    def _make_client(self):
        return RedashClient(base_url="https://redash.example.com", api_key="test-key")

    def test_list_data_sources_success(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": 1, "name": "Production DB", "type": "pg"},
            {"id": 2, "name": "Analytics", "type": "bigquery"},
        ]
        with patch.object(c, "_request", return_value=mock_resp):
            result = c.list_data_sources()
            assert len(result) == 2
            assert result[0]["name"] == "Production DB"

    def test_list_data_sources_error(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        with patch.object(c, "_request", return_value=mock_resp):
            with pytest.raises(RedashError, match="Failed to list data sources"):
                c.list_data_sources()


class TestRedashClientGetSchema:
    def _make_client(self):
        return RedashClient(base_url="https://redash.example.com", api_key="test-key")

    def test_get_schema_dict_response(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "schema": [
                {"name": "users", "columns": ["id", "name", "email"]},
                {"name": "orders", "columns": [{"name": "id", "type": "int"}, {"name": "total", "type": "decimal"}]},
            ]
        }
        with patch.object(c, "_request", return_value=mock_resp):
            result = c.get_schema(1)
            assert len(result) == 2
            assert result[0]["name"] == "users"
            assert result[0]["columns"] == ["id", "name", "email"]
            assert result[1]["columns"] == ["id", "total"]

    def test_get_schema_error(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        with patch.object(c, "_request", return_value=mock_resp):
            with pytest.raises(RedashError, match="Failed to get schema"):
                c.get_schema(999)

    def test_get_schema_list_response(self):
        """When Redash returns a list directly (older versions)."""
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"name": "users", "columns": ["id", "name"]},
        ]
        with patch.object(c, "_request", return_value=mock_resp):
            result = c.get_schema(1)
            assert len(result) == 1
            assert result[0]["name"] == "users"


class TestRedashClientRunQuery:
    def _make_client(self):
        c = RedashClient(base_url="https://redash.example.com", api_key="test-key", poll_interval=0.01, poll_timeout=1.0)
        return c

    def test_run_query_success(self):
        c = self._make_client()

        # POST /api/query_results returns a job
        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {"job": {"id": "job-123", "status": 1}}
        post_resp.text = '{"job": {"id": "job-123", "status": 1}}'

        # GET /api/jobs/job-123 returns success
        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"job": {"id": "job-123", "status": 3, "query_result_id": 42}}

        # GET /api/query_results/42.json returns data
        result_resp = MagicMock()
        result_resp.status_code = 200
        result_resp.json.return_value = {
            "query_result": {
                "data": {
                    "columns": [{"name": "id"}, {"name": "name"}],
                    "rows": [{"id": 1, "name": "Alice"}],
                },
                "runtime": 0.5,
            }
        }

        with patch.object(c, "_request", side_effect=[post_resp, poll_resp, result_resp]):
            result = c.run_query(1, "SELECT * FROM users LIMIT 1")
            assert result["columns"] == [{"name": "id"}, {"name": "name"}]
            assert result["rows"] == [{"id": 1, "name": "Alice"}]
            assert result["metadata"]["runtime"] == 0.5

    def test_run_query_http_error(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch.object(c, "_request", return_value=mock_resp):
            with pytest.raises(RedashError, match="Failed to run query"):
                c.run_query(1, "SELECT 1")

    def test_run_query_no_job_in_response(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mock_resp.text = "{}"
        with patch.object(c, "_request", return_value=mock_resp):
            with pytest.raises(RedashError, match="no job in response"):
                c.run_query(1, "SELECT 1")

    def test_run_query_job_failure(self):
        c = self._make_client()

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {"job": {"id": "job-fail", "status": 1, "error": "Syntax error"}}
        post_resp.text = '{"job": {"id": "job-fail"}}'

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"job": {"id": "job-fail", "status": 4, "error": "Syntax error"}}

        with patch.object(c, "_request", side_effect=[post_resp, poll_resp]):
            with pytest.raises(RedashError, match="Syntax error"):
                c.run_query(1, "SELECT * FORM users")


class TestRedashClientRunSavedQuery:
    def _make_client(self):
        return RedashClient(base_url="https://redash.example.com", api_key="test-key", poll_interval=0.01, poll_timeout=1.0)

    def test_run_saved_query_success(self):
        c = self._make_client()

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {"job": {"id": "job-456", "status": 1}}
        post_resp.text = '{"job": {"id": "job-456"}}'

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"job": {"id": "job-456", "status": 3, "query_result_id": 99}}

        result_resp = MagicMock()
        result_resp.status_code = 200
        result_resp.json.return_value = {
            "query_result": {
                "data": {
                    "columns": [{"name": "count"}],
                    "rows": [{"count": 42}],
                },
                "runtime": 1.2,
            }
        }

        with patch.object(c, "_request", side_effect=[post_resp, poll_resp, result_resp]):
            result = c.run_saved_query(10)
            assert result["rows"] == [{"count": 42}]
            assert result["metadata"]["row_count"] == 1

    def test_run_saved_query_http_error(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        with patch.object(c, "_request", return_value=mock_resp):
            with pytest.raises(RedashError, match="Failed to run saved query"):
                c.run_saved_query(999)

    def test_run_saved_query_result_fetch_error(self):
        c = self._make_client()

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {"job": {"id": "j1", "status": 1}}
        post_resp.text = '{"job": {"id": "j1"}}'

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"job": {"id": "j1", "status": 3, "query_result_id": 55}}

        result_resp = MagicMock()
        result_resp.status_code = 500
        result_resp.text = "Server Error"

        with patch.object(c, "_request", side_effect=[post_resp, poll_resp, result_resp]):
            with pytest.raises(RedashError, match="Failed to get query result"):
                c.run_saved_query(10)


class TestRedashClientPollJob:
    def _make_client(self):
        return RedashClient(base_url="https://redash.example.com", api_key="k", poll_interval=0.01, poll_timeout=0.1)

    def test_poll_job_success(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"job": {"id": "j1", "status": 3, "query_result_id": 42}}
        with patch.object(c, "_request", return_value=mock_resp):
            result = c._poll_job({"id": "j1", "status": 1})
            assert result == 42

    def test_poll_job_failure(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"job": {"id": "j1", "status": 4, "error": "bad query"}}
        with patch.object(c, "_request", return_value=mock_resp):
            result = c._poll_job({"id": "j1", "status": 1})
            assert result is None

    def test_poll_job_no_id(self):
        c = self._make_client()
        result = c._poll_job({})
        assert result is None

    def test_poll_job_timeout(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"job": {"id": "j1", "status": 2}}  # always "started"
        with patch.object(c, "_request", return_value=mock_resp):
            with pytest.raises(RedashError, match="did not complete"):
                c._poll_job({"id": "j1", "status": 1})

    def test_poll_job_http_error(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Error"
        with patch.object(c, "_request", return_value=mock_resp):
            with pytest.raises(RedashError, match="Failed to get job status"):
                c._poll_job({"id": "j1", "status": 1})


class TestRedashClientGetQueryResultById:
    def _make_client(self):
        return RedashClient(base_url="https://redash.example.com", api_key="k")

    def test_get_result_nested(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "query_result": {
                "data": {"columns": [{"name": "a"}], "rows": [{"a": 1}]},
                "runtime": 0.3,
            }
        }
        with patch.object(c, "_request", return_value=mock_resp):
            result = c._get_query_result_by_id(42)
            assert result["columns"] == [{"name": "a"}]
            assert result["rows"] == [{"a": 1}]
            assert result["metadata"]["runtime"] == 0.3

    def test_get_result_flat(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "columns": [{"name": "x"}],
            "rows": [{"x": 10}],
            "runtime": 0.1,
        }
        with patch.object(c, "_request", return_value=mock_resp):
            result = c._get_query_result_by_id(1)
            assert result["columns"] == [{"name": "x"}]
            assert result["rows"] == [{"x": 10}]

    def test_get_result_error(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        with patch.object(c, "_request", return_value=mock_resp):
            with pytest.raises(RedashError, match="Failed to get query result"):
                c._get_query_result_by_id(999)

    def test_get_result_non_dict_data(self):
        """When data_block is not a dict."""
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"query_result": {"data": "invalid"}}
        with patch.object(c, "_request", return_value=mock_resp):
            result = c._get_query_result_by_id(1)
            assert result["columns"] == []
            assert result["rows"] == []


class TestRedashError:
    def test_error_attrs(self):
        err = RedashError("test error", status_code=500, response_text="Internal Server Error")
        assert str(err) == "test error"
        assert err.status_code == 500
        assert err.response_text == "Internal Server Error"

    def test_error_defaults(self):
        err = RedashError("oops")
        assert err.status_code is None
        assert err.response_text is None


class TestRedashClientJobConstants:
    def test_job_status_constants(self):
        assert RedashClient.JOB_STATUS_PENDING == 1
        assert RedashClient.JOB_STATUS_STARTED == 2
        assert RedashClient.JOB_STATUS_SUCCESS == 3
        assert RedashClient.JOB_STATUS_FAILURE == 4
        assert RedashClient.JOB_TERMINAL_STATUSES == (3, 4)
