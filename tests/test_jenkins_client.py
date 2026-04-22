"""Tests for jenkins_client.py — unit tests with mocked HTTP."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.cicd.jenkins_client import JenkinsClient, JenkinsError


class TestJenkinsClient:
    def _make_client(self):
        return JenkinsClient(
            base_url="https://jenkins.example.com",
            username="testuser",
            api_token="testtoken",
            poll_interval=0.1,
            poll_timeout=1.0,
        )

    def test_init(self):
        c = self._make_client()
        assert c.base_url == "https://jenkins.example.com"
        assert c.auth == ("testuser", "testtoken")

    def test_init_strips_trailing_slash(self):
        c = JenkinsClient(
            base_url="https://jenkins.example.com/",
            username="u", api_token="t",
        )
        assert c.base_url == "https://jenkins.example.com"

    def test_job_path_simple(self):
        """Simple job name."""
        c = self._make_client()
        assert c._job_path("my-job") == "/job/my-job"

    def test_job_path_folder(self):
        """Two-level folder job."""
        c = self._make_client()
        assert c._job_path("pg2/my-job") == "/job/pg2/job/my-job"

    def test_job_path_deep_folder(self):
        """Three-level folder job (like pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz)."""
        c = self._make_client()
        assert c._job_path("pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz") == \
            "/job/pg2/job/pg2-dev-build-jobs/job/pg2-dev-pg-acquiring-biz"

    def test_job_path_strips_job_prefix(self):
        """Handles misconfigured input with 'job/' prefixes (copy-pasted from Jenkins URL)."""
        c = self._make_client()
        assert c._job_path("job/pg2/job/pg2-dev-build-jobs/") == \
            "/job/pg2/job/pg2-dev-build-jobs"

    def test_job_path_strips_trailing_slash(self):
        """Trailing slashes are stripped."""
        c = self._make_client()
        assert c._job_path("pg2/pg2-dev-build-jobs/") == \
            "/job/pg2/job/pg2-dev-build-jobs"


class TestExtractBuildVersion:
    """Test build version extraction from console logs."""

    def test_docker_tag(self):
        log = "Building image...\nPushing repo/my-service:1.2.3-42\nDone."
        assert JenkinsClient.extract_build_version(log) == "1.2.3-42"

    def test_build_version_env(self):
        log = "Compiling...\nBUILD_VERSION=2.5.0-SNAPSHOT\nUpload complete."
        assert JenkinsClient.extract_build_version(log) == "2.5.0-SNAPSHOT"

    def test_version_equals(self):
        log = "Setting version=3.1.0\nBuild success."
        assert JenkinsClient.extract_build_version(log) == "3.1.0"

    def test_build_tag_number(self):
        log = "Starting...\nbuild tag: 157\nFinished: SUCCESS"
        assert JenkinsClient.extract_build_version(log) == "157"

    def test_build_hash_number(self):
        log = "Build #42 completed\nFinished: SUCCESS"
        assert JenkinsClient.extract_build_version(log) == "42"

    def test_artifact_upload(self):
        log = "Uploading my-service-1.5.2.jar to nexus\nDone."
        assert JenkinsClient.extract_build_version(log) == "1.5.2"

    def test_docker_v_prefix(self):
        log = "Successfully built image:v2.0.1\nPush complete."
        assert JenkinsClient.extract_build_version(log) == "v2.0.1"

    def test_no_version_found(self):
        log = "Compiling...\nAll tests passed.\nFinished: SUCCESS"
        assert JenkinsClient.extract_build_version(log) is None

    def test_empty_log(self):
        assert JenkinsClient.extract_build_version("") is None

    def test_last_match_wins(self):
        """Multiple versions — last one (final artifact) should be returned."""
        log = "version=1.0.0\nRebuilding...\nversion=2.0.0\nDone."
        assert JenkinsClient.extract_build_version(log) == "2.0.0"

    def test_version_in_last_200_lines(self):
        """Only scans last 200 lines."""
        early = "BUILD_VERSION=1.0.0\n" + ("noise\n" * 300)
        late = "BUILD_VERSION=2.0.0\nDone."
        assert JenkinsClient.extract_build_version(early + late) == "2.0.0"

    def test_ecr_pushing_manifest_grv(self):
        """Extract tag from ECR pushing manifest line (dev/feature branch)."""
        log = (
            "#27 pushing layers 8.2s done\n"
            "#27 pushing manifest for 233815244996.dkr.ecr.ap-south-1.amazonaws.com/"
            "acquiring-biz-service:924-grv@sha256:9a038e4998dc07a634ee4bcf8ca425508a283fb3e29e22e59c66526bc93a3142\n"
            "#27 DONE 21.7s\nFinished: SUCCESS"
        )
        assert JenkinsClient.extract_build_version(log) == "924-grv"

    def test_ecr_pushing_manifest_grv_prod(self):
        """Extract tag from ECR pushing manifest line (release branch)."""
        log = (
            "#27 pushing manifest for 233815244996.dkr.ecr.ap-south-1.amazonaws.com/"
            "acquiring-biz-service:924-grv-prod@sha256:abcdef1234567890\n"
            "#27 DONE 21.7s\nFinished: SUCCESS"
        )
        assert JenkinsClient.extract_build_version(log) == "924-grv-prod"


class TestArgoCDClient:
    """Tests for argocd_client.py — unit tests."""

    def test_init(self):
        from code_agents.cicd.argocd_client import ArgoCDClient
        c = ArgoCDClient(
            base_url="https://argocd.example.com/",
            auth_token="test-token",
            verify_ssl=False,
        )
        assert c.base_url == "https://argocd.example.com"
        assert c.auth_token == "test-token"
        assert c.verify_ssl is False

    def test_init_defaults(self):
        from code_agents.cicd.argocd_client import ArgoCDClient
        c = ArgoCDClient(
            base_url="https://argocd.example.com",
            auth_token="token",
        )
        assert c.verify_ssl is True
        assert c.timeout == 30.0
        assert c.poll_timeout == 300.0


# ── Additional JenkinsClient async method tests ──────────────────────


class TestJenkinsClientAsync:
    """Tests for async methods with mocked httpx."""

    def _make_client(self):
        return JenkinsClient(
            base_url="https://jenkins.example.com",
            username="testuser",
            api_token="testtoken",
            poll_interval=0.01,
            poll_timeout=0.1,
        )

    def test_get_crumb_cached(self):
        c = self._make_client()
        c._crumb = {"Jenkins-Crumb": "abc123"}

        async def run():
            mock_client = AsyncMock()
            return await c._get_crumb(mock_client)

        result = asyncio.run(run())
        assert result == {"Jenkins-Crumb": "abc123"}

    def test_get_crumb_fetch(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "crumbRequestField": "Jenkins-Crumb",
                "crumb": "xyz789",
            }
            mock_client.get.return_value = mock_resp
            return await c._get_crumb(mock_client)

        result = asyncio.run(run())
        assert result == {"Jenkins-Crumb": "xyz789"}
        assert c._crumb == {"Jenkins-Crumb": "xyz789"}

    def test_get_crumb_not_required(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_client.get.return_value = mock_resp
            return await c._get_crumb(mock_client)

        result = asyncio.run(run())
        assert result == {}

    def test_list_jobs(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "jobs": [
                    {"name": "build", "_class": "WorkflowJob", "url": "http://x", "color": "blue"},
                    {"name": "folder", "_class": "Folder", "url": "http://y", "color": ""},
                ],
            }
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.list_jobs()

        result = asyncio.run(run())
        assert len(result) == 2
        assert result[0]["type"] == "job"
        assert result[1]["type"] == "folder"

    def test_list_jobs_error(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 403
            mock_resp.text = "Forbidden"
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.list_jobs()

        with pytest.raises(JenkinsError):
            asyncio.run(run())

    def test_trigger_build_with_params(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.headers = {"Location": "https://jenkins.example.com/queue/item/42/"}
            mock_resp.text = ""
            mock_client.post.return_value = mock_resp
            mock_client.get.return_value = MagicMock(status_code=200,
                                                      json=MagicMock(return_value={"crumbRequestField": "X", "crumb": "Y"}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            c._crumb = None
            with patch.object(c, "_client", return_value=mock_client):
                return await c.trigger_build("my-job", parameters={"branch": "main"})

        result = asyncio.run(run())
        assert result["queue_id"] == 42
        assert result["status"] == "queued"

    def test_trigger_build_no_params(self):
        c = self._make_client()
        c._crumb = {}

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.headers = {"Location": ""}
            mock_resp.text = ""
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.trigger_build("my-job")

        result = asyncio.run(run())
        assert result["queue_id"] is None

    def test_get_build_status(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "number": 5, "result": "SUCCESS", "building": False,
                "duration": 30000, "estimatedDuration": 25000,
                "timestamp": 1234567890, "url": "http://x/5",
                "displayName": "#5",
            }
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_status("my-job", 5)

        result = asyncio.run(run())
        assert result["result"] == "SUCCESS"
        assert result["building"] is False
        assert result["number"] == 5

    def test_get_build_log(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "Build started...\nDone."
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_log("my-job", 5)

        result = asyncio.run(run())
        assert "Build started" in result

    def test_get_build_log_truncation(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "x" * 60000
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_log("my-job", 5)

        result = asyncio.run(run())
        assert "truncated" in result

    def test_get_job_parameters(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "property": [
                    {
                        "parameterDefinitions": [
                            {
                                "name": "branch",
                                "type": "StringParameterDefinition",
                                "description": "Branch to build",
                                "defaultParameterValue": {"value": "main"},
                                "choices": None,
                            },
                            {
                                "name": "env",
                                "type": "ChoiceParameterDefinition",
                                "description": "Environment",
                                "defaultParameterValue": {"value": "dev"},
                                "choices": ["dev", "staging", "prod"],
                            },
                        ],
                    },
                ],
            }
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_job_parameters("my-job")

        result = asyncio.run(run())
        assert len(result) == 2
        assert result[0]["name"] == "branch"
        assert result[0]["default"] == "main"
        assert result[1]["choices"] == ["dev", "staging", "prod"]

    def test_wait_for_build_finished_immediately(self):
        c = self._make_client()

        async def run():
            with patch.object(c, "get_build_status", new_callable=AsyncMock) as mock_status:
                mock_status.return_value = {
                    "building": False, "result": "SUCCESS", "duration": 5000,
                }
                return await c.wait_for_build("my-job", 5)

        result = asyncio.run(run())
        assert result["result"] == "SUCCESS"

    def test_wait_for_build_timeout(self):
        c = self._make_client()

        async def run():
            with patch.object(c, "get_build_status", new_callable=AsyncMock) as mock_status:
                mock_status.return_value = {"building": True, "result": None}
                return await c.wait_for_build("my-job", 5)

        with pytest.raises(JenkinsError, match="did not complete"):
            asyncio.run(run())

    def test_get_build_from_queue_success(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"executable": {"number": 7}}
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_from_queue(42)

        result = asyncio.run(run())
        assert result == 7

    def test_get_build_from_queue_cancelled(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"cancelled": True}
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_from_queue(42)

        result = asyncio.run(run())
        assert result is None


class TestJenkinsError:
    def test_error_with_status(self):
        err = JenkinsError("fail", status_code=500, response_text="Internal Server Error")
        assert err.status_code == 500
        assert err.response_text == "Internal Server Error"
        assert str(err) == "fail"

    def test_error_defaults(self):
        err = JenkinsError("message")
        assert err.status_code is None
        assert err.response_text is None
