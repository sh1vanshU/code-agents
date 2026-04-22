"""Extra tests for jenkins_client.py — covers get_last_build, get_build_artifacts,
trigger_and_wait, error paths, and edge cases."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.cicd.jenkins_client import JenkinsClient, JenkinsError


class TestJenkinsClientExtra:
    def _make_client(self):
        return JenkinsClient(
            base_url="https://jenkins.example.com",
            username="testuser",
            api_token="testtoken",
            poll_interval=0.01,
            poll_timeout=0.1,
        )

    # ── get_last_build ──────────────────────────────────────────────

    def test_get_last_build_finished(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            # First call: lastBuild API
            build_resp = MagicMock()
            build_resp.status_code = 200
            build_resp.json.return_value = {
                "number": 10, "result": "SUCCESS", "building": False,
                "url": "http://x/10",
            }
            # Second call: console log
            log_resp = MagicMock()
            log_resp.status_code = 200
            log_resp.text = "Building...\nBUILD_VERSION=3.2.1\nFinished: SUCCESS"

            mock_client.get.side_effect = [build_resp, log_resp]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_last_build("my-job")

        result = asyncio.run(run())
        assert result["number"] == 10
        assert result["build_version"] == "3.2.1"
        assert result["log_tail"] is not None

    def test_get_last_build_still_building(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            build_resp = MagicMock()
            build_resp.status_code = 200
            build_resp.json.return_value = {
                "number": 11, "result": None, "building": True,
                "url": "http://x/11",
            }
            mock_client.get.return_value = build_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_last_build("my-job")

        result = asyncio.run(run())
        assert result["building"] is True
        assert result["build_version"] is None  # Not extracted when building

    def test_get_last_build_log_fetch_fails(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            build_resp = MagicMock()
            build_resp.status_code = 200
            build_resp.json.return_value = {
                "number": 10, "result": "SUCCESS", "building": False,
                "url": "http://x/10",
            }
            log_resp = MagicMock()
            log_resp.status_code = 500
            mock_client.get.side_effect = [build_resp, Exception("network error")]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_last_build("my-job")

        result = asyncio.run(run())
        assert result["build_version"] is None

    def test_get_last_build_error(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_resp.text = "Not Found"
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_last_build("nonexistent")

        with pytest.raises(JenkinsError, match="HTTP 404"):
            asyncio.run(run())

    # ── get_build_artifacts ─────────────────────────────────────────

    def test_get_build_artifacts(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "artifacts": [
                    {"fileName": "app.jar", "relativePath": "target/app.jar"},
                    {"fileName": "app.war", "relativePath": "target/app.war"},
                ],
            }
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_artifacts("my-job", 5)

        result = asyncio.run(run())
        assert len(result) == 2
        assert result[0]["fileName"] == "app.jar"

    def test_get_build_artifacts_error(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_resp.text = "Not Found"
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_artifacts("my-job", 999)

        with pytest.raises(JenkinsError):
            asyncio.run(run())

    def test_get_build_artifacts_empty(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"artifacts": []}
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_artifacts("my-job", 5)

        result = asyncio.run(run())
        assert result == []

    # ── trigger_and_wait ────────────────────────────────────────────

    def test_trigger_and_wait_success(self):
        c = self._make_client()

        async def run():
            with patch.object(c, "trigger_build", new_callable=AsyncMock) as mock_trigger, \
                 patch.object(c, "get_build_from_queue", new_callable=AsyncMock) as mock_queue, \
                 patch.object(c, "wait_for_build", new_callable=AsyncMock) as mock_wait, \
                 patch.object(c, "get_build_log", new_callable=AsyncMock) as mock_log:
                mock_trigger.return_value = {"queue_id": 42, "build_number": None}
                mock_queue.return_value = 7
                mock_wait.return_value = {
                    "number": 7, "result": "SUCCESS", "building": False, "duration": 5000,
                }
                mock_log.return_value = "Building...\nBUILD_VERSION=1.0.0\nDone."
                return await c.trigger_and_wait("my-job", {"branch": "main"})

        result = asyncio.run(run())
        assert result["result"] == "SUCCESS"
        assert result["build_version"] == "1.0.0"
        assert "log_tail" in result

    def test_trigger_and_wait_no_build_number(self):
        c = self._make_client()

        async def run():
            with patch.object(c, "trigger_build", new_callable=AsyncMock) as mock_trigger, \
                 patch.object(c, "get_build_from_queue", new_callable=AsyncMock) as mock_queue:
                mock_trigger.return_value = {"queue_id": 42, "build_number": None}
                mock_queue.return_value = None  # build cancelled
                return await c.trigger_and_wait("my-job")

        result = asyncio.run(run())
        assert result["status"] == "failed"
        assert result["error"] is not None

    def test_trigger_and_wait_log_fetch_error(self):
        c = self._make_client()

        async def run():
            with patch.object(c, "trigger_build", new_callable=AsyncMock) as mock_trigger, \
                 patch.object(c, "get_build_from_queue", new_callable=AsyncMock) as mock_queue, \
                 patch.object(c, "wait_for_build", new_callable=AsyncMock) as mock_wait, \
                 patch.object(c, "get_build_log", new_callable=AsyncMock) as mock_log:
                mock_trigger.return_value = {"queue_id": 42, "build_number": None}
                mock_queue.return_value = 7
                mock_wait.return_value = {
                    "number": 7, "result": "FAILURE", "building": False, "duration": 3000,
                }
                mock_log.side_effect = Exception("log fetch failed")
                return await c.trigger_and_wait("my-job")

        result = asyncio.run(run())
        assert result["result"] == "FAILURE"
        assert result["build_version"] is None
        assert result["log_tail"] == ""

    # ── trigger_build error ─────────────────────────────────────────

    def test_trigger_build_error(self):
        c = self._make_client()
        c._crumb = {}

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = "Internal Server Error"
            mock_resp.headers = {}
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.trigger_build("bad-job")

        with pytest.raises(JenkinsError, match="HTTP 500"):
            asyncio.run(run())

    # ── get_build_status error ──────────────────────────────────────

    def test_get_build_status_error(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_resp.text = "Not Found"
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_status("my-job", 999)

        with pytest.raises(JenkinsError):
            asyncio.run(run())

    # ── get_build_log error ─────────────────────────────────────────

    def test_get_build_log_error(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_log("my-job", 999)

        with pytest.raises(JenkinsError):
            asyncio.run(run())

    # ── get_build_from_queue error ──────────────────────────────────

    def test_get_build_from_queue_error(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_from_queue(42)

        with pytest.raises(JenkinsError):
            asyncio.run(run())

    def test_get_build_from_queue_timeout(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {}  # no executable, no cancelled
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.get_build_from_queue(42)

        with pytest.raises(JenkinsError, match="did not start"):
            asyncio.run(run())

    # ── get_job_parameters error ────────────────────────────────────

    def test_get_job_parameters_error(self):
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
                return await c.get_job_parameters("my-job")

        with pytest.raises(JenkinsError):
            asyncio.run(run())

    # ── list_jobs in folder ─────────────────────────────────────────

    def test_list_jobs_in_folder(self):
        c = self._make_client()

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "jobs": [
                    {"name": "svc", "_class": "FreeStyleProject", "url": "http://x", "color": "blue"},
                ],
            }
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            with patch.object(c, "_client", return_value=mock_client):
                return await c.list_jobs(folder_name="pg2/builds")

        result = asyncio.run(run())
        assert len(result) == 1
        assert result[0]["type"] == "job"

    # ── _job_path edge cases ────────────────────────────────────────

    def test_job_path_single_job_named_job(self):
        """Edge case: a folder literally named 'job' at the end."""
        c = self._make_client()
        # "job" as a final segment should be kept
        result = c._job_path("my-folder/job")
        assert result == "/job/my-folder/job/job"

    # ── extract_build_version edge cases ────────────────────────────

    def test_extract_docker_push_manifest(self):
        log = "pushing manifest for registry.example.com/my-service:1.5.0-rc1@sha256:abc123"
        result = JenkinsClient.extract_build_version(log)
        assert result == "1.5.0-rc1"

    def test_extract_successfully_built(self):
        log = "Successfully built v2.3.4-beta\nDone."
        result = JenkinsClient.extract_build_version(log)
        assert result == "v2.3.4-beta"

    def test_extract_image_tag_env(self):
        log = "IMAGE_TAG=4.0.0-snapshot\nDeploying..."
        result = JenkinsClient.extract_build_version(log)
        assert result == "4.0.0-snapshot"

    # ── wait_for_build polls ────────────────────────────────────────

    def test_wait_for_build_polls_then_succeeds(self):
        c = self._make_client()
        call_count = [0]

        async def mock_status(job, build):
            call_count[0] += 1
            if call_count[0] < 3:
                return {"building": True, "result": None, "duration": 0}
            return {"building": False, "result": "SUCCESS", "duration": 5000}

        async def run():
            with patch.object(c, "get_build_status", side_effect=mock_status):
                return await c.wait_for_build("my-job", 5)

        result = asyncio.run(run())
        assert result["result"] == "SUCCESS"
        assert call_count[0] == 3


class TestExtractBuildVersionExtra:
    """Additional version extraction patterns."""

    def test_tagging_docker(self):
        log = "tagging registry.io/svc:v3.0.0\nDone"
        assert JenkinsClient.extract_build_version(log) == "v3.0.0"

    def test_deploying_artifact(self):
        log = "deploying my-service-2.1.0.jar to nexus"
        assert JenkinsClient.extract_build_version(log) == "2.1.0"

    def test_artifact_version_env(self):
        log = "ARTIFACT_VERSION=5.0.0\nDone."
        assert JenkinsClient.extract_build_version(log) == "5.0.0"

    def test_digest_pattern(self):
        log = "digest: v1.2.3-rc1\nPush complete"
        assert JenkinsClient.extract_build_version(log) == "v1.2.3-rc1"

    def test_finished_success_pattern(self):
        log = "#99 SUCCESS"
        assert JenkinsClient.extract_build_version(log) == "99"

    def test_pushing_manifest(self):
        log = "pushing manifest for registry.example.com/svc:1.5.0-rc1@sha256:abc"
        assert JenkinsClient.extract_build_version(log) == "1.5.0-rc1"

    def test_image_tag_var(self):
        log = "IMAGE_TAG=4.0.0-snapshot\nDone."
        assert JenkinsClient.extract_build_version(log) == "4.0.0-snapshot"
