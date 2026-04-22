#!/usr/bin/env python3
"""Quick smoke test for the Jenkins API — list jobs, fetch parameters, check builds."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from code_agents.cicd.jenkins_client import JenkinsClient, JenkinsError


async def main():
    base_url = os.getenv("JENKINS_URL")
    username = os.getenv("JENKINS_USERNAME")
    api_token = os.getenv("JENKINS_API_TOKEN")
    build_job = os.getenv("JENKINS_BUILD_JOB")
    deploy_job = os.getenv("JENKINS_DEPLOY_JOB")

    if not base_url:
        print("JENKINS_URL not set in .env")
        sys.exit(1)
    if not username or not api_token:
        print("JENKINS_USERNAME and JENKINS_API_TOKEN must be set in .env")
        sys.exit(1)

    print(f"Connecting to Jenkins: {base_url}")
    print(f"User: {username}")
    print(f"Build job: {build_job or '(not set)'}")
    print(f"Deploy job: {deploy_job or '(not set)'}")
    print()

    client = JenkinsClient(
        base_url=base_url,
        username=username,
        api_token=api_token,
    )

    # Step 1: List root jobs
    print("=" * 60)
    print("Step 1: Listing root Jenkins jobs...")
    try:
        jobs = await client.list_jobs()
        print(f"Found {len(jobs)} top-level job(s):\n")
        for j in jobs[:20]:
            marker = "📁" if j["type"] == "folder" else "🔧"
            print(f"  {marker} {j['name']:<40} ({j['type']})")
        if len(jobs) > 20:
            print(f"  ... and {len(jobs) - 20} more")
        print()
    except JenkinsError as e:
        print(f"Failed to list jobs: {e}")
        sys.exit(1)

    # Step 2: List jobs in build job folder (if configured)
    if build_job and "/" in build_job:
        folder = "/".join(build_job.split("/")[:-1])
        print("=" * 60)
        print(f"Step 2: Listing jobs in folder: {folder}")
        try:
            folder_jobs = await client.list_jobs(folder)
            print(f"Found {len(folder_jobs)} job(s):\n")
            for j in folder_jobs:
                marker = "📁" if j["type"] == "folder" else "🔧"
                color = j.get("color", "")
                status = ""
                if "blue" in color:
                    status = "✅"
                elif "red" in color:
                    status = "❌"
                elif "anime" in color:
                    status = "🔄"
                elif "disabled" in color:
                    status = "⏸️"
                print(f"  {marker} {j['name']:<40} {status} ({j['type']})")
            print()
        except JenkinsError as e:
            print(f"Failed to list folder jobs: {e}")

    # Step 3: Fetch build job parameters
    if build_job:
        print("=" * 60)
        print(f"Step 3: Fetching parameters for: {build_job}")
        try:
            params = await client.get_job_parameters(build_job)
            if params:
                print(f"Found {len(params)} parameter(s):\n")
                for p in params:
                    default = p.get("default", "")
                    choices = p.get("choices", [])
                    desc = p.get("description", "")[:60]
                    line = f"  {p['name']:<25} type={p['type']:<12}"
                    if choices:
                        line += f" choices={choices}"
                    elif default:
                        line += f" default={default!r}"
                    if desc:
                        line += f"  — {desc}"
                    print(line)
            else:
                print("  No parameters (non-parameterized job)")
            print()
        except JenkinsError as e:
            print(f"Failed to get parameters: {e}")

    # Step 4: Fetch deploy job parameters (if different)
    if deploy_job and deploy_job != build_job:
        print("=" * 60)
        print(f"Step 4: Fetching parameters for deploy job: {deploy_job}")
        try:
            params = await client.get_job_parameters(deploy_job)
            if params:
                print(f"Found {len(params)} parameter(s):\n")
                for p in params:
                    default = p.get("default", "")
                    choices = p.get("choices", [])
                    line = f"  {p['name']:<25} type={p['type']:<12}"
                    if choices:
                        line += f" choices={choices}"
                    elif default:
                        line += f" default={default!r}"
                    print(line)
            else:
                print("  No parameters")
            print()
        except JenkinsError as e:
            print(f"Failed to get deploy parameters: {e}")

    # Step 5: Check last build (if build job configured)
    if build_job:
        print("=" * 60)
        print(f"Step 5: Checking last build for: {build_job}")
        try:
            last = await client.get_last_build(build_job)
            result_emoji = {"SUCCESS": "✅", "FAILURE": "❌", "UNSTABLE": "⚠️", "ABORTED": "🚫"}.get(
                last.get("result", ""), "🔄" if last.get("building") else "❓"
            )
            print(f"  Build #{last.get('number')} {result_emoji} {last.get('result') or 'BUILDING'}")
            print(f"  URL: {last.get('url', 'N/A')}")
            print()
        except JenkinsError as e:
            print(f"Failed to get last build: {e}")

    print("=" * 60)
    print("Jenkins connectivity test complete!")


if __name__ == "__main__":
    asyncio.run(main())
