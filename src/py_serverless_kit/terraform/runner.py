"""Thin, testable wrapper around the ``terraform`` / ``tofu`` binary."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class TerraformError(Exception):
    def __init__(self, message: str, output: str = "") -> None:
        super().__init__(message)
        self.output = output  # what terraform printed (apply), for error attribution


def find_binary(preferred: Optional[str] = None) -> str:
    candidates = [c for c in (preferred, os.environ.get("PSKIT_TERRAFORM_BIN"), "terraform", "tofu") if c]
    for cand in candidates:
        found = shutil.which(cand)
        if found:
            return found
    raise TerraformError(
        "Neither `terraform` nor `tofu` was found on PATH. Install Terraform >= 1.5 "
        "(https://developer.hashicorp.com/terraform/install) or OpenTofu, "
        "or set PSKIT_TERRAFORM_BIN."
    )


@dataclass
class TerraformRunner:
    work_dir: Path
    binary: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    echo: Callable[[str], None] = print

    def _bin(self) -> str:
        if self.binary is None or not Path(self.binary).is_file():
            self.binary = find_binary(self.binary)
        return self.binary

    def _run(self, args: List[str], *, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.setdefault("TF_IN_AUTOMATION", "1")
        env.setdefault("TF_INPUT", "0")
        env.update(self.env or {})
        cmd = [self._bin(), *args]
        if capture:
            proc = subprocess.run(cmd, cwd=self.work_dir, env=env, capture_output=True, text=True)
        else:
            proc = subprocess.run(cmd, cwd=self.work_dir, env=env, text=True)
        if check and proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "")[-6000:] if capture else ""
            raise TerraformError(f"`{' '.join(cmd[1:3])}` failed with exit code {proc.returncode}\n{detail}".rstrip())
        return proc

    def _run_tee(self, args: List[str]) -> Tuple[int, str]:
        """Run terraform with its output streamed as usual, and also return it (errors are parsed from it)."""
        env = dict(os.environ)
        env.setdefault("TF_IN_AUTOMATION", "1")
        env.setdefault("TF_INPUT", "0")
        env.update(self.env or {})
        proc = subprocess.Popen(
            [self._bin(), *args], cwd=self.work_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        lines: List[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            sys.stdout.write(line)
            sys.stdout.flush()
        return proc.wait(), "".join(lines)

    def init(self, upgrade: bool = False, reconfigure: bool = False) -> None:
        args = ["init", "-input=false", "-no-color"]
        if upgrade:
            args.append("-upgrade")
        if reconfigure:
            args.append("-reconfigure")
        if upgrade:
            self._run(args)
            return
        code, output = self._run_tee(args)
        if code == 0:
            return
        # A pskit upgrade raised a provider's minimum version (e.g. kreuzwerker/docker >= 4.3.0) above the one in
        # .terraform.lock.hcl: let terraform select the newer version instead of failing.
        if "does not match configured version constraint" in output:
            self.echo("  a provider's required version changed; running terraform init -upgrade")
            self._run([*args, "-upgrade"])
            return
        raise TerraformError(f"`init -input=false` failed with exit code {code}", output)

    def validate(self) -> None:
        self._run(["validate", "-no-color"])

    def plan(self, destroy: bool = False, out: Optional[str] = "tfplan", targets: Optional[List[str]] = None) -> bool:
        """Return ``True`` when the plan has changes."""
        args = ["plan", "-input=false", "-no-color", "-detailed-exitcode"]
        if destroy:
            args.append("-destroy")
        if out:
            args += ["-out", out]
        args += [f"-target={t}" for t in targets or []]
        proc = self._run(args, check=False)
        if proc.returncode == 1:
            raise TerraformError("terraform plan failed")
        return proc.returncode == 2

    def apply(
        self, plan_file: Optional[str] = None, auto_approve: bool = True, targets: Optional[List[str]] = None
    ) -> str:
        """Apply; returns terraform's output. A failure raises :class:`TerraformError` carrying that output."""
        args = ["apply", "-input=false", "-no-color"]
        if plan_file:
            args.append(plan_file)
        else:
            if auto_approve:
                args.append("-auto-approve")
            args += [f"-target={t}" for t in targets or []]
        code, output = self._run_tee(args)
        if code != 0:
            raise TerraformError(f"`apply` failed with exit code {code}", output=output)
        return output

    def destroy(self, auto_approve: bool = True, targets: Optional[List[str]] = None) -> None:
        args = ["destroy", "-input=false", "-no-color"]
        if auto_approve:
            args.append("-auto-approve")
        args += [f"-target={t}" for t in targets or []]
        self._run(args)

    def state_pull(self) -> Dict[str, Any]:
        """The whole state as JSON (any backend); ``{}`` when there is none."""
        proc = self._run(["state", "pull"], capture=True, check=False)
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            return {}
        try:
            data = json.loads(proc.stdout)
        except ValueError as exc:
            raise TerraformError(f"could not parse terraform state: {exc}") from exc
        return data if isinstance(data, dict) else {}

    def state_list(self) -> List[str]:
        """Resource addresses in the state (empty when there is no state yet)."""
        proc = self._run(["state", "list", "-no-color"], capture=True, check=False)
        if proc.returncode != 0:
            return []
        return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]

    def state_rm(self, addresses: List[str]) -> None:
        """Forget resources without destroying them."""
        if addresses:
            self._run(["state", "rm", "-no-color", *addresses], capture=True)

    def output(self) -> Dict[str, Any]:
        proc = self._run(["output", "-json", "-no-color"], capture=True)
        try:
            raw = json.loads(proc.stdout or "{}")
        except ValueError as exc:
            raise TerraformError(f"could not parse terraform output: {exc}") from exc
        return {k: v.get("value") for k, v in raw.items()}

    def passthrough(self, args: List[str]) -> int:
        return self._run(args, check=False).returncode
