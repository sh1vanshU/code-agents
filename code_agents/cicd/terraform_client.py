"""
Terraform client — plan, apply, and manage infrastructure via terraform CLI.

Wraps the terraform CLI with async subprocess execution.
Config: TERRAFORM_BINARY (default: terraform), TERRAFORM_WORKING_DIR
"""
from __future__ import annotations

import asyncio
import json
import os
import logging
import os
import shutil
from typing import Any, Optional

logger = logging.getLogger("code_agents.terraform_client")


class TerraformError(Exception):
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class TerraformClient:
    def __init__(
        self,
        working_dir: str = ".",
        binary: str = "",
        timeout: float = 300.0,
    ):
        self.working_dir = os.path.abspath(working_dir)
        self.binary = binary or shutil.which("terraform") or "terraform"
        self.timeout = timeout

    async def _run(self, *args: str, input_data: str = "") -> tuple[str, str, int]:
        """Run a terraform command and return (stdout, stderr, returncode)."""
        cmd = [self.binary] + list(args)
        logger.info("terraform %s (cwd=%s)", " ".join(args), self.working_dir)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if input_data else asyncio.subprocess.DEVNULL,
            env={**os.environ, "TF_IN_AUTOMATION": "1", "TF_INPUT": "0"},
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_data.encode() if input_data else None),
            timeout=self.timeout,
        )
        return stdout.decode(), stderr.decode(), proc.returncode or 0

    # ── Init ─────────────────────────────────────────────────────────────

    async def init(self, backend_config: dict[str, str] | None = None) -> dict:
        """Run terraform init."""
        args = ["init", "-no-color"]
        if backend_config:
            for k, v in backend_config.items():
                args.append(f"-backend-config={k}={v}")
        stdout, stderr, rc = await self._run(*args)
        if rc != 0:
            raise TerraformError(f"terraform init failed:\n{stderr or stdout}", rc)
        return {"status": "initialized", "output": stdout[-2000:]}

    # ── Validate ─────────────────────────────────────────────────────────

    async def validate(self) -> dict:
        """Run terraform validate."""
        stdout, stderr, rc = await self._run("validate", "-json", "-no-color")
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError:
            result = {"valid": rc == 0, "raw": stdout[-2000:]}
        if rc != 0:
            result["error"] = stderr[-1000:]
        return result

    # ── Plan ─────────────────────────────────────────────────────────────

    async def plan(
        self,
        targets: list[str] | None = None,
        var_file: str = "",
        refresh_only: bool = False,
        destroy: bool = False,
    ) -> dict:
        """Run terraform plan and return summary."""
        args = ["plan", "-no-color", "-input=false"]
        if targets:
            for t in targets:
                args.append(f"-target={t}")
        if var_file:
            if ".." in var_file or os.path.isabs(var_file):
                raise TerraformError("var_file must be a relative path without '..'")
            args.append(f"-var-file={var_file}")
        if refresh_only:
            args.append("-refresh-only")
        if destroy:
            args.append("-destroy")

        stdout, stderr, rc = await self._run(*args)
        output = stdout + stderr

        # Parse plan summary
        summary = self._parse_plan_summary(output)
        summary["exit_code"] = rc
        summary["output"] = output[-5000:]

        if rc not in (0, 2):  # 2 = changes present
            raise TerraformError(f"terraform plan failed:\n{output[-3000:]}", rc)

        return summary

    # ── Apply ────────────────────────────────────────────────────────────

    async def apply(
        self,
        auto_approve: bool = False,
        targets: list[str] | None = None,
        var_file: str = "",
    ) -> dict:
        """Run terraform apply."""
        args = ["apply", "-no-color", "-input=false"]
        if auto_approve:
            args.append("-auto-approve")
        if targets:
            for t in targets:
                args.append(f"-target={t}")
        if var_file:
            if ".." in var_file or os.path.isabs(var_file):
                raise TerraformError("var_file must be a relative path without '..'")
            args.append(f"-var-file={var_file}")

        stdout, stderr, rc = await self._run(*args)
        output = stdout + stderr

        if rc != 0:
            raise TerraformError(f"terraform apply failed:\n{output[-3000:]}", rc)

        summary = self._parse_plan_summary(output)
        summary["status"] = "applied"
        summary["output"] = output[-5000:]
        return summary

    # ── Destroy ──────────────────────────────────────────────────────────

    async def destroy(
        self,
        targets: list[str] | None = None,
        auto_approve: bool = False,
    ) -> dict:
        """Run terraform destroy."""
        args = ["destroy", "-no-color", "-input=false"]
        if auto_approve:
            args.append("-auto-approve")
        if targets:
            for t in targets:
                args.append(f"-target={t}")

        stdout, stderr, rc = await self._run(*args)
        output = stdout + stderr

        if rc != 0:
            raise TerraformError(f"terraform destroy failed:\n{output[-3000:]}", rc)

        return {"status": "destroyed", "output": output[-3000:]}

    # ── State ────────────────────────────────────────────────────────────

    async def state_list(self) -> list[str]:
        """List resources in terraform state."""
        stdout, stderr, rc = await self._run("state", "list")
        if rc != 0:
            raise TerraformError(f"state list failed:\n{stderr or stdout}", rc)
        return [line.strip() for line in stdout.strip().split("\n") if line.strip()]

    async def state_show(self, address: str) -> dict:
        """Show a specific resource in state."""
        stdout, stderr, rc = await self._run("state", "show", address, "-no-color")
        if rc != 0:
            raise TerraformError(f"state show failed:\n{stderr or stdout}", rc)
        return {"address": address, "details": stdout[-5000:]}

    # ── Output ───────────────────────────────────────────────────────────

    async def output(self) -> dict:
        """Get terraform outputs."""
        stdout, stderr, rc = await self._run("output", "-json", "-no-color")
        if rc != 0:
            raise TerraformError(f"output failed:\n{stderr or stdout}", rc)
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"raw": stdout[-2000:]}

    # ── Providers ────────────────────────────────────────────────────────

    async def providers(self) -> dict:
        """List providers used."""
        stdout, stderr, rc = await self._run("providers", "-no-color")
        if rc != 0:
            raise TerraformError(f"providers failed:\n{stderr or stdout}", rc)
        return {"providers": stdout[-2000:]}

    # ── Fmt ───────────────────────────────────────────────────────────────

    async def fmt(self, check: bool = False) -> dict:
        """Format terraform files."""
        args = ["fmt", "-no-color"]
        if check:
            args.append("-check")
            args.append("-diff")
        stdout, stderr, rc = await self._run(*args)
        return {
            "formatted": rc == 0,
            "diff": stdout[-3000:] if check else "",
            "files": stdout.strip().split("\n") if stdout.strip() and not check else [],
        }

    # ── Helpers ──────────────────────────────────────────────────────────

    def _parse_plan_summary(self, output: str) -> dict:
        """Parse terraform plan output for add/change/destroy counts."""
        import re
        summary: dict[str, Any] = {"add": 0, "change": 0, "destroy": 0, "no_changes": False}

        m = re.search(r"(\d+) to add, (\d+) to change, (\d+) to destroy", output)
        if m:
            summary["add"] = int(m.group(1))
            summary["change"] = int(m.group(2))
            summary["destroy"] = int(m.group(3))
        elif "No changes" in output or "no changes" in output.lower():
            summary["no_changes"] = True

        return summary
