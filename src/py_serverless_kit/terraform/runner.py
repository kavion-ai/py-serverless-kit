"""Thin, testable wrapper around the ``terraform`` / ``tofu`` binary."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class TerraformError(Exception):
    pass


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

    def init(self, upgrade: bool = False, reconfigure: bool = False) -> None:
        args = ["init", "-input=false", "-no-color"]
        if upgrade:
            args.append("-upgrade")
        if reconfigure:
            args.append("-reconfigure")
        self._run(args)

    def validate(self) -> None:
        self._run(["validate", "-no-color"])

    def plan(self, destroy: bool = False, out: Optional[str] = "tfplan") -> bool:
        """Return ``True`` when the plan has changes."""
        args = ["plan", "-input=false", "-no-color", "-detailed-exitcode"]
        if destroy:
            args.append("-destroy")
        if out:
            args += ["-out", out]
        proc = self._run(args, check=False)
        if proc.returncode == 1:
            raise TerraformError("terraform plan failed")
        return proc.returncode == 2

    def apply(self, plan_file: Optional[str] = None, auto_approve: bool = True) -> None:
        args = ["apply", "-input=false", "-no-color"]
        if plan_file:
            args.append(plan_file)
        elif auto_approve:
            args.append("-auto-approve")
        self._run(args)

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
