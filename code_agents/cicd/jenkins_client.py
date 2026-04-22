"""
Jenkins REST API client for triggering and monitoring build/deploy jobs.

Uses httpx for async HTTP. Authenticates via HTTP Basic (username + API token).
Handles CSRF crumb for Jenkins instances that require it.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger("code_agents.jenkins_client")


class JenkinsError(Exception):
    """Raised when a Jenkins API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class JenkinsClient:
    """Async client for the Jenkins REST API."""

    def __init__(
        self,
        base_url: str,
        username: str,
        api_token: str,
        timeout: float = 30.0,
        poll_interval: float = 5.0,
        poll_timeout: float = 600.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, api_token)
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self._crumb: Optional[dict[str, str]] = None

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            auth=self.auth,
            timeout=self.timeout,
            follow_redirects=True,
        )

    async def _get_crumb(self, client: httpx.AsyncClient) -> dict[str, str]:
        """Fetch CSRF crumb if Jenkins requires it. Cached per instance."""
        if self._crumb is not None:
            return self._crumb
        try:
            r = await client.get("/crumbIssuer/api/json")
            if r.status_code == 200:
                data = r.json()
                self._crumb = {data["crumbRequestField"]: data["crumb"]}
                return self._crumb
        except Exception as e:
            logger.debug("Failed to fetch Jenkins crumb: %s", e)
        self._crumb = {}
        return self._crumb

    def _job_path(self, job_name: str) -> str:
        """Convert a slash-separated job name to Jenkins API path.

        Input: 'pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz'
        Output: '/job/pg2/job/pg2-dev-build-jobs/job/pg2-dev-pg-acquiring-biz'

        Also handles misconfigured input with 'job/' prefix:
        Input: 'job/pg2/job/pg2-dev-build-jobs/'
        Output: '/job/pg2/job/pg2-dev-build-jobs'
        """
        # Strip 'job' segments that alternate with real folder names
        # Pattern from Jenkins URL: job/pg2/job/builds/job/my-svc
        # We strip 'job' only when it appears BEFORE a real name (every other position)
        raw_parts = [p for p in job_name.strip("/").split("/") if p]
        parts = []
        for i, p in enumerate(raw_parts):
            if p == "job" and i + 1 < len(raw_parts):
                continue  # skip 'job' if followed by another segment
            elif p == "job" and i + 1 == len(raw_parts):
                parts.append(p)  # keep 'job' as a legitimate final folder name
            else:
                parts.append(p)
        return "/job/" + "/job/".join(parts)

    async def list_jobs(self, folder_name: str | None = None) -> list[dict]:
        """
        List jobs in a folder (or root if folder_name is None).

        Returns list of dicts: [{name, url, color, fullName, type}]
        """
        async with self._client() as client:
            if folder_name:
                path = self._job_path(folder_name) + "/api/json"
            else:
                path = "/api/json"

            r = await client.get(
                path,
                params={"tree": "jobs[name,url,color,fullName,_class]"},
            )
            if r.status_code != 200:
                raise JenkinsError(
                    f"Failed to list jobs: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            data = r.json()
            jobs = data.get("jobs", [])
            result = []
            for job in jobs:
                cls = job.get("_class", "")
                if "Folder" in cls or "OrganizationFolder" in cls:
                    job_type = "folder"
                elif "WorkflowJob" in cls or "FreeStyleProject" in cls:
                    job_type = "job"
                else:
                    job_type = "other"
                result.append({
                    "name": job.get("name", ""),
                    "full_name": job.get("fullName", job.get("name", "")),
                    "url": job.get("url", ""),
                    "color": job.get("color", ""),
                    "type": job_type,
                })
            return result

    async def get_job_parameters(self, job_name: str) -> list[dict]:
        """
        Fetch the parameter definitions for a parameterized job.

        Returns list of dicts: [{name, type, default, description, choices}]
        """
        job_path = self._job_path(job_name)
        async with self._client() as client:
            r = await client.get(
                f"{job_path}/api/json",
                params={"tree": "property[parameterDefinitions[name,type,defaultParameterValue[value],description,choices]]"},
            )
            if r.status_code != 200:
                raise JenkinsError(
                    f"Failed to get job parameters: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            data = r.json()

            params = []
            for prop in data.get("property", []):
                for pd in prop.get("parameterDefinitions", []):
                    param = {
                        "name": pd.get("name", ""),
                        "type": pd.get("type", "").replace("ParameterDefinition", ""),
                        "description": pd.get("description", ""),
                    }
                    default = pd.get("defaultParameterValue", {})
                    if default:
                        param["default"] = default.get("value", "")
                    choices = pd.get("choices")
                    if choices:
                        param["choices"] = choices
                    params.append(param)
            return params

    async def trigger_build(
        self,
        job_name: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict:
        """
        Trigger a Jenkins build job.

        Returns dict with queue_id for tracking.
        """
        async with self._client() as client:
            crumb = await self._get_crumb(client)
            headers = dict(crumb) if crumb else {}

            job_path = self._job_path(job_name)

            if parameters:
                url = f"{job_path}/buildWithParameters"
                logger.info("jenkins trigger_build: POST %s params=%s", url, list(parameters.keys()))
                r = await client.post(url, data=parameters, headers=headers)
            else:
                url = f"{job_path}/build"
                logger.info("jenkins trigger_build: POST %s (no params)", url)
                r = await client.post(url, headers=headers)

            logger.info("jenkins trigger_build response: status=%d location=%s", r.status_code, r.headers.get("Location", "-"))
            if r.status_code not in (200, 201, 302):
                raise JenkinsError(
                    f"Failed to trigger build: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )

            # Extract queue ID from Location header
            location = r.headers.get("Location", "")
            queue_id = None
            if "/queue/item/" in location:
                try:
                    queue_id = int(location.rstrip("/").split("/")[-1])
                except ValueError as e:
                    logger.debug("Failed to parse queue ID from location header: %s", e)

            logger.info("Triggered build for %s, queue_id=%s", job_name, queue_id)
            return {
                "job_name": job_name,
                "queue_id": queue_id,
                "status": "queued",
            }

    async def get_build_from_queue(self, queue_id: int) -> Optional[int]:
        """Poll queue item until it gets a build number. Returns build number or None."""
        async with self._client() as client:
            deadline = time.monotonic() + self.poll_timeout
            while time.monotonic() < deadline:
                r = await client.get(f"/queue/item/{queue_id}/api/json")
                if r.status_code != 200:
                    raise JenkinsError(
                        f"Failed to get queue item: HTTP {r.status_code}",
                        status_code=r.status_code,
                    )
                data = r.json()
                executable = data.get("executable")
                if executable and executable.get("number"):
                    return executable["number"]
                if data.get("cancelled"):
                    return None
                await asyncio.sleep(self.poll_interval)
            raise JenkinsError(f"Queue item {queue_id} did not start within {self.poll_timeout}s")

    async def get_build_status(self, job_name: str, build_number: int) -> dict:
        """Get build status and details."""
        job_path = self._job_path(job_name)
        async with self._client() as client:
            r = await client.get(f"{job_path}/{build_number}/api/json")
            if r.status_code != 200:
                raise JenkinsError(
                    f"Failed to get build status: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            data = r.json()
            return {
                "job_name": job_name,
                "number": data.get("number"),
                "result": data.get("result"),  # SUCCESS, FAILURE, UNSTABLE, ABORTED, None (building)
                "building": data.get("building", False),
                "duration": data.get("duration", 0),
                "estimated_duration": data.get("estimatedDuration", 0),
                "timestamp": data.get("timestamp"),
                "url": data.get("url"),
                "display_name": data.get("displayName"),
            }

    async def get_build_log(self, job_name: str, build_number: int) -> str:
        """Get console output for a build."""
        job_path = self._job_path(job_name)
        async with self._client() as client:
            r = await client.get(f"{job_path}/{build_number}/consoleText")
            if r.status_code != 200:
                raise JenkinsError(
                    f"Failed to get build log: HTTP {r.status_code}",
                    status_code=r.status_code,
                )
            text = r.text
            # Truncate very long logs
            max_len = 50000
            if len(text) > max_len:
                text = text[-max_len:]
                text = "... (truncated, showing last 50KB)\n" + text
            return text

    async def get_last_build(self, job_name: str) -> dict:
        """Get info about the last build of a job, including build_version from console log."""
        job_path = self._job_path(job_name)
        async with self._client() as client:
            r = await client.get(f"{job_path}/lastBuild/api/json")
            if r.status_code != 200:
                raise JenkinsError(
                    f"Failed to get last build: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            data = r.json()
            build_number = data.get("number")
            result = {
                "job_name": job_name,
                "number": build_number,
                "result": data.get("result"),
                "building": data.get("building", False),
                "url": data.get("url"),
                "build_version": None,
            }

            # Extract build_version from console log (if build finished)
            if not data.get("building", False) and build_number:
                try:
                    log_r = await client.get(f"{job_path}/{build_number}/consoleText")
                    if log_r.status_code == 200:
                        log_text = log_r.text
                        result["build_version"] = self.extract_build_version(log_text)
                        # Include last 100 lines for agent analysis
                        result["log_tail"] = "\n".join(log_text.strip().splitlines()[-100:])
                except Exception as e:
                    logger.debug("Could not fetch console log for version extraction: %s", e)

            return result

    async def wait_for_build(self, job_name: str, build_number: int) -> dict:
        """Poll build status until it finishes. Returns final status."""
        logger.info("jenkins wait_for_build: %s #%d (poll_interval=%.0fs timeout=%.0fs)",
                     job_name, build_number, self.poll_interval, self.poll_timeout)
        deadline = time.monotonic() + self.poll_timeout
        poll_count = 0
        while time.monotonic() < deadline:
            poll_count += 1
            status = await self.get_build_status(job_name, build_number)
            if not status["building"]:
                logger.info(
                    "jenkins build %s #%d finished: result=%s duration=%dms polls=%d",
                    job_name, build_number, status["result"], status.get("duration", 0), poll_count,
                )
                return status
            logger.debug("jenkins build %s #%d still building (poll %d)", job_name, build_number, poll_count)
            await asyncio.sleep(self.poll_interval)
        logger.error("jenkins build %s #%d TIMEOUT after %.0fs (%d polls)",
                      job_name, build_number, self.poll_timeout, poll_count)
        raise JenkinsError(
            f"Build {job_name} #{build_number} did not complete within {self.poll_timeout}s"
        )

    @staticmethod
    def extract_build_version(log_text: str) -> Optional[str]:
        """
        Extract build/artifact version from Jenkins console output.

        Scans for common patterns:
          - Docker tag: image:1.2.3-42, image:v1.2.3
          - Maven/Gradle: BUILD_VERSION=1.2.3, version=1.2.3-SNAPSHOT
          - Generic: build tag: 42, Build #42 SUCCESS
          - Artifact upload lines containing version numbers
        """
        patterns = [
            # Docker push manifest: pushing manifest for registry/service:TAG@sha256:...
            r"pushing manifest for\s+\S+/[^:]+:([^\s@]+)",
            # Docker: naming to registry.com/service:tag or tagging image:tag
            r"(?:naming|tagging|pushing|pushed)\s+\S+:([^\s@\"']+)",
            # Docker image tag: image:1.2.3-42
            r"(?:image|tag|built)[:\s]+\S+:([v]?[\d]+[\d._-]+[^\s@]*)",
            # BUILD_VERSION=xxx or version=xxx or IMAGE_TAG=xxx
            r"(?:BUILD_VERSION|ARTIFACT_VERSION|IMAGE_TAG|version|VERSION)\s*[=:]\s*([v]?[\d]+[\w._-]*)",
            # Build tag: NNN or Build #NNN
            r"(?:build\s*(?:tag|number|no|#))\s*[=:#]?\s*(\d+)",
            # Uploading/deploying artifact-1.2.3.jar
            r"(?:upload|deploy|publish)\S*\s+\S*?-(\d+[\d._-]+\S*?)(?:\.jar|\.war|\.zip|\.tar)",
            # Successfully built / digest
            r"(?:Successfully built|digest:)\s+\S*?([v]?[\d]+[\d._-]+\S*)",
            # Finished: SUCCESS with build display name #NNN
            r"#(\d+)\s+(?:SUCCESS|Finished)",
        ]

        # Search last 200 lines (build version usually near the end)
        lines = log_text.strip().splitlines()[-200:]
        text = "\n".join(lines)

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Strip @sha256: digest suffix if present
                version = matches[-1].split("@")[0]
                return version

        return None

    async def get_build_artifacts(self, job_name: str, build_number: int) -> list[dict]:
        """Get the list of artifacts produced by a build.

        Returns list of dicts with artifact metadata (fileName, relativePath, etc.).
        """
        job_path = self._job_path(job_name)
        async with self._client() as client:
            r = await client.get(f"{job_path}/{build_number}/api/json")
            if r.status_code != 200:
                raise JenkinsError(
                    f"Failed to get build info: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            data = r.json()
            return data.get("artifacts", [])

    async def trigger_and_wait(
        self,
        job_name: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict:
        """
        Trigger a build, poll until complete, extract build version from logs.

        Returns full result dict with: job_name, build_number, result, duration,
        build_version (extracted from console output), log_tail (last 30 lines).
        """
        # 1. Trigger
        trigger_result = await self.trigger_build(job_name, parameters)
        build_number = trigger_result.get("build_number")

        # If no build number from queue, wait and check
        if not build_number and trigger_result.get("queue_id"):
            build_number = await self.get_build_from_queue(trigger_result["queue_id"])

        if not build_number:
            return {
                "job_name": job_name,
                "queue_id": trigger_result.get("queue_id"),
                "status": "failed",
                "result": None,
                "error": "Could not determine build number from queue (build may have been cancelled)",
            }

        # 2. Poll until complete
        logger.info("trigger_and_wait: polling %s #%d", job_name, build_number)
        final_status = await self.wait_for_build(job_name, build_number)

        # 3. Extract build version from logs
        build_version = None
        log_tail = ""
        try:
            log_text = await self.get_build_log(job_name, build_number)
            build_version = self.extract_build_version(log_text)
            log_lines = log_text.strip().splitlines()
            log_tail = "\n".join(log_lines[-100:])
            logger.info(
                "trigger_and_wait: %s #%d version=%s log_lines=%d",
                job_name, build_number, build_version, len(log_lines),
            )
        except Exception as e:
            logger.error("trigger_and_wait: failed to fetch logs for %s #%d: %s", job_name, build_number, e)

        return {
            **final_status,
            "build_version": build_version,
            "log_tail": log_tail,
        }
