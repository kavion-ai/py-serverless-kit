"""High level package / deploy / remove orchestration used by the CLI."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..packaging.builder import build_artifact
from ..providers.base import Artifact, Issue, RenderContext
from ..providers.container import PackagePlan, package_summary, plan_package
from ..terraform.runner import TerraformError, TerraformRunner
from . import partial
from .describe import RECORD_FILE, build_record
from .partial import NotDeployed
from .project import Project

Echo = Callable[[str], None]


class DeployError(Exception):
    pass


@dataclass
class PackageResult:
    artifact: Artifact
    tf_file: Path
    resource_count: int
    warnings: List[str] = field(default_factory=list)
    package: Optional[PackagePlan] = None  # zip or image, and the size notes printed
    resources: List[Dict[str, Any]] = field(default_factory=list)  # what Terraform manages, described


class Deployer:
    def __init__(
        self,
        project: Project,
        echo: Echo = print,
        runner: Optional[TerraformRunner] = None,
        package_type: Optional[str] = None,
        keep_going: bool = False,
    ) -> None:
        """``package_type`` (``--package-type``) overrides ``package.type`` of pskit.yml for this run.

        ``keep_going`` (``pskit deploy`` without ``--all-or-nothing``): a function that cannot be deployed is skipped
        or reported, and the others are deployed (core/partial.py). ``not_deployed`` lists them afterwards.
        """
        if package_type:
            project.use_package_type(package_type)
        self.project = project
        self.echo = echo
        self._runner = runner
        self.keep_going = keep_going
        self.not_deployed: List[NotDeployed] = []
        self._all_functions: List[str] = sorted(project.config.functions)

    # ---------------------------------------------------------------- helpers
    @property
    def runner(self) -> TerraformRunner:
        if self._runner is None:
            tf = self.project.config.provider.terraform
            self._runner = TerraformRunner(self.project.work_dir, binary=tf.binary, echo=self.echo)
        return self._runner

    def check(self) -> List[Issue]:
        issues = self.project.validate()
        if self.keep_going:
            issues = self._skip_function_errors(issues)
        errors = [i for i in issues if i.level == "error"]
        for issue in issues:
            self.echo(f"  {issue}")
        if errors:
            raise DeployError(f"{len(errors)} configuration error(s); fix them and retry")
        return issues

    def _skip(self, name: str, step: str, reason: str) -> None:
        self.not_deployed.append(NotDeployed(name, step, reason))
        self.echo(f"  SKIP: functions.{name} is not deployed ({step}): {reason}")
        self.project.drop_functions([name])

    def _skip_function_errors(self, issues: List[Issue]) -> List[Issue]:
        """Partial deploy: skip the functions whose own configuration is wrong, until the rest validates."""
        for _round in range(len(self.project.config.functions) + 1):
            scoped = partial.function_errors(issues, self.project.config.functions)
            if not scoped or len(scoped) >= len(self.project.config.functions):
                break  # nothing to skip, or nothing would be left: report every error as usual
            for name, messages in sorted(scoped.items()):
                self._skip(name, partial.CONFIG, "; ".join(messages))
            issues = self.project.validate()
        return issues

    def run_hook(self, name: str) -> None:
        commands = self.project.config.hooks.get(name) or []
        for cmd in commands:
            self.echo(f"  hook {name}: {cmd}")
            env = dict(os.environ)
            env.update(
                {
                    "PSKIT_SERVICE": self.project.config.service,
                    "PSKIT_STAGE": self.project.config.provider.stage,
                    "PSKIT_PROVIDER": self.project.config.provider.name,
                    "PSKIT_WORK_DIR": str(self.project.work_dir),
                }
            )
            proc = subprocess.run(cmd, shell=True, cwd=self.project.root, env=env)  # noqa: S602 - user hook
            if proc.returncode != 0:
                raise DeployError(f"hook {name} failed ({proc.returncode}): {cmd}")

    # ---------------------------------------------------------------- steps
    def package(self, *, skip_deps: bool = False, strict: bool = False) -> PackageResult:
        """Build the bundle and Terraform. ``strict`` (deploy) stops when the zip is over the provider's size limit."""
        project = self.project
        self.check()
        project.work_dir.mkdir(parents=True, exist_ok=True)
        _write_gitignore(project.root / ".pskit")
        self.run_hook("before_package")
        self.echo(
            f"Packaging {project.config.service} for {project.provider.display_name} ({project.config.provider.stage})"
        )
        artifact = build_artifact(project, skip_deps=skip_deps, log=self.echo)
        plan = self.package_plan(artifact, strict=strict and not skip_deps)
        image = None
        if plan.needs_image:
            from ..packaging.image import prepare_image

            image = prepare_image(project.provider, project.config, artifact)
            self.echo(f"  image: {image.base_image} -> tag {image.tag} ({image.platform}), "
                      f"{image.context}/{image.dockerfile}")
        ctx = RenderContext(
            config=project.config,
            provider=project.provider,
            root=project.root,
            work_dir=project.work_dir,
            artifact=artifact,
            region=project.region,
            workflow_engines=dict(project.engines),
            package_type=plan.type,
            image=image,
            function_packages=dict(plan.functions),
        )
        doc = project.provider.render(ctx)
        tf_file = project.work_dir / "main.tf.json"
        tf_file.write_text(doc.to_json(), "utf-8")
        warnings = list(getattr(doc, "warnings", []))
        for w in warnings:
            self.echo(f"  WARNING: {w}")
        resources = self.describe_resources(doc.to_dict(), plan)
        self.echo(f"  terraform: {doc.count()} resource(s) -> {tf_file.relative_to(project.root)}")
        self.run_hook("after_package")
        return PackageResult(artifact=artifact, tf_file=tf_file, resource_count=doc.count(), warnings=warnings,
                             package=plan, resources=resources)

    def describe_resources(self, tf: Dict[str, Any], plan: PackagePlan) -> List[Dict[str, Any]]:
        """Print what each generated resource is for and save it as resources.json (studio's Deploy page)."""
        from ..providers import descriptions

        summary = descriptions.summarize(tf)
        for line in descriptions.lines(summary):
            self.echo(f"  {line}")
        cfg = self.project.config
        prov = self.project.provider
        descriptions.save(self.project.work_dir, summary, {
            "provider": cfg.provider.name,
            "provider_display": prov.display_name,
            "stage": cfg.provider.stage,
            "package_type": plan.type,
            "monitoring": {
                name: {"logs": cfg.logs_of(fn), "metrics": cfg.metrics_of(fn)} for name, fn in sorted(cfg.functions.items())
            },
            "monitoring_text": {"logs": prov.monitoring_text("logs"), "metrics": prov.monitoring_text("metrics")},
        })
        return summary

    def package_plan(self, artifact: Artifact, *, strict: bool = False) -> PackagePlan:
        """Zip or image for this deploy, with the size notes (see providers/container.py)."""
        plan = plan_package(self.project.provider, self.project.config, artifact)
        for note in plan.notes:
            self.echo(f"  NOTE: {note}" if note.level == "info" else f"  {note}")
        if strict and self.keep_going and plan.too_big and len(plan.too_big) < len(plan.functions):
            # Partial deploy: the zip functions cannot go, the image functions can.
            for name, reason in sorted(plan.too_big.items()):
                self._skip(name, partial.SIZE, reason)
                plan.functions.pop(name, None)
            plan.too_big = {}
            plan.type = package_summary(plan.functions)
            plan.notes = [n for n in plan.notes if n.level != "error"]
        if strict and plan.errors:
            raise DeployError(
                f"the bundle is too big for a zip deploy on {self.project.provider.display_name}; see the notes above"
            )
        return plan

    def plan(self, *, skip_deps: bool = False, destroy: bool = False) -> bool:
        self.package(skip_deps=skip_deps)
        self.runner.init()
        return self.runner.plan(destroy=destroy, out=None)

    def deploy(self, *, skip_deps: bool = False, auto_approve: bool = True, upgrade: bool = False) -> Dict[str, Any]:
        if self.project.config.provider.name == "onprem":
            self._onprem_services_follow()  # before packaging: the env file shipped has the new addresses
        previous = self.load_record() or {}
        result = self.package(skip_deps=skip_deps, strict=True)
        self.run_hook("before_deploy")
        self.echo("Running terraform init")
        self.runner.init(upgrade=upgrade)
        # Functions skipped before Terraform keep what was deployed before: apply only what was rendered.
        targets = partial.resource_addresses(json.loads(result.tf_file.read_text("utf-8"))) if self.not_deployed \
            else None
        if targets:
            self.echo(f"  applying {len(targets)} resource(s) only, so the skipped functions are left as they are")
        try:
            if auto_approve:
                self.echo("Running terraform apply")
                self.runner.apply(auto_approve=True, targets=targets)
            else:
                changed = self.runner.plan(out="tfplan", targets=targets)
                if not changed:
                    self.echo("No changes.")
                else:
                    self.runner.apply(plan_file="tfplan")
        except TerraformError as exc:
            self._apply_failed(exc, result)
        try:
            outputs = self.runner.output()
        except TerraformError:
            if not self.not_deployed:
                raise
            outputs = {}  # a failed first apply writes no outputs
        record = build_record(
            self.project,
            outputs,
            artifact=_artifact_record(result),
            status="partial" if self.not_deployed else "deployed",
        )
        self._record_not_deployed(record, previous)
        if self.project.config.provider.name == "onprem":
            self._remember_onprem(record)
            self._onprem_balancers(record)
            self._onprem_smtp()
        self.save_record(record)
        if self.project.config.provider.name == "onprem":
            from . import onprem_network as network

            network.emit_rules(self.echo, f"{self.project.config.service} ({self.project.config.provider.stage})",
                               network.deployment(self.project.root, self.project.work_dir))
        self.run_hook("after_deploy")
        return record

    def _apply_failed(self, exc: TerraformError, result: PackageResult) -> None:
        """Partial deploy: which functions the failed apply did not deploy, and why. Re-raises when unknown."""
        if not self.keep_going or not exc.output:
            raise exc
        tf = json.loads(result.tf_file.read_text("utf-8"))
        functions = sorted(self.project.config.functions)
        failed = partial.failed_functions(tf, functions, partial.parse_errors(exc.output))
        if not failed:
            raise exc  # nothing attributable to a function (e.g. a workflow or a shared resource only)
        for name, reason in sorted(failed.items()):
            self.not_deployed.append(NotDeployed(
                name, partial.TERRAFORM, reason,
                "Terraform kept everything that does not depend on it; the failed part is retried on the next deploy",
            ))
        if len(failed) == len(functions):
            raise DeployError("no function was deployed:\n" + "\n".join(partial.report_lines(self.not_deployed,
                                                                                            len(self._all_functions))))

    def _record_not_deployed(self, record: Dict[str, Any], previous: Dict[str, Any]) -> None:
        """deployment.json: ``not_deployed`` with the reasons; skipped functions keep their previous entry."""
        if not self.not_deployed:
            return
        before = {f.get("name"): f for f in previous.get("functions") or [] if isinstance(f, dict)}
        shared = self.project.provider.shared_function_host
        host = self.project.provider.display_name
        listed = {f["name"] for f in record["functions"]}
        for item in self.not_deployed:
            if item.step != partial.TERRAFORM:
                if item.function not in before:
                    item.previous = "it has never been deployed on this stage"
                elif shared:
                    item.previous = f"its previous version left {host}: one host runs every function"
                else:
                    item.previous = "the version deployed before is still running, unchanged"
                    if item.function not in listed:
                        record["functions"].append({**before[item.function], "status": "not_updated"})
            for entry in record["functions"]:
                if entry.get("name") == item.function and item.step == partial.TERRAFORM:
                    entry["status"] = "not_deployed"
        record["functions"].sort(key=lambda f: str(f.get("name")))
        record["not_deployed"] = {n.function: n.as_dict() for n in sorted(self.not_deployed, key=lambda n: n.function)}

    def report(self) -> List[str]:
        """The "Not deployed" lines printed at the end of a partial deploy."""
        return partial.report_lines(self.not_deployed, len(self._all_functions))

    def remove(self, *, auto_approve: bool = True, keep_resources: bool = False) -> List[str]:
        """Destroy the stage. With ``keep_resources`` managed buckets, queues and topics stay in the
        cloud (they are dropped from the Terraform state first). Returns the kept addresses."""
        from .retain import kept_addresses, save_kept, supports

        project = self.project
        if not (project.work_dir / "main.tf.json").is_file():
            # Re-render so terraform knows the provider configuration.
            self.package(skip_deps=True)
        self.run_hook("before_remove")
        self.runner.init()
        kept: List[str] = []
        if keep_resources:
            provider = project.config.provider.name
            if not supports(provider):
                self.echo(f"  {project.provider.display_name}: no managed buckets, queues or topics to keep")
            else:
                kept = kept_addresses(provider, self.runner.state_list())
                if kept:
                    # Remember them in .pskit/<p>-<s>/kept/ so `pskit resources delete` can remove them later.
                    save_kept(project.work_dir, self.runner.state_pull(), kept)
                for address in kept:
                    self.echo(f"  keeping {address} (delete later with `pskit resources delete`)")
                self.runner.state_rm(kept)
        self.runner.destroy(auto_approve=auto_approve)
        if project.config.provider.name == "onprem":
            self._drop_routes()
        record_path = project.work_dir / RECORD_FILE
        if record_path.is_file():
            record = json.loads(record_path.read_text("utf-8"))
            record["status"] = "removed"
            if kept:
                record["kept_resources"] = kept
            record_path.write_text(json.dumps(record, indent=2), "utf-8")
        self.run_hook("after_remove")
        return kept

    def _drop_routes(self) -> None:
        """``pskit remove``: this deployment's routes leave the load balancers it was on."""
        from .onprem_balancers import BalancerError, load_balancers, remove_owner

        known = load_balancers(self.project.root)
        for route in self._remembered_routes():
            if route.get("name") in known and route.get("owner"):
                try:
                    remove_owner(self.project.root, str(route["name"]), str(route["owner"]), self.echo)
                except BalancerError as exc:
                    self.echo(f"  WARNING: {exc}")

    # ---------------------------------------------------------------- data resources
    def cloud_resources(self) -> Dict[str, List[Dict[str, Any]]]:
        """Buckets, queues and topics pskit created: still deployed, and kept by ``remove --keep-resources``."""
        from .retain import data_resources, list_kept

        provider = self.project.config.provider.name
        deployed: List[Dict[str, Any]] = []
        if (self.project.work_dir / "main.tf.json").is_file():
            self.runner.init()
            deployed = data_resources(provider, self.runner.state_pull())
        return {"deployed": deployed, "kept": list_kept(self.project.work_dir, provider)}

    def delete_resources(self, addresses: List[str]) -> List[str]:
        """Delete buckets, queues or topics by Terraform address (kept ones or deployed ones). Returns deleted."""
        from .retain import delete_kept

        found = self.cloud_resources()
        kept = {r["address"] for r in found["kept"]}
        deployed = {r["address"] for r in found["deployed"]}
        unknown = [a for a in addresses if a not in kept and a not in deployed]
        if unknown:
            raise DeployError(
                f"not a bucket, queue or topic of this deployment: {', '.join(unknown)} (see `pskit resources list`)"
            )
        done: List[str] = []
        from_kept = [a for a in addresses if a in kept]
        if from_kept:
            tf = self.project.config.provider.terraform
            delete_kept(self.project.work_dir, from_kept, binary=tf.binary, echo=self.echo)
            done += from_kept
        targets = [a for a in addresses if a in deployed and a not in kept]
        if targets:
            self.runner.destroy(auto_approve=True, targets=targets)
            done += targets
            self.echo(
                "  Deleted from the cloud. If it is still in pskit.yml, the next deploy creates it again: "
                "remove it from `resources:` / the trigger first."
            )
        return done

    def refresh_info(self) -> Dict[str, Any]:
        outputs = self.runner.output()
        previous = self.load_record() or {}
        record = build_record(self.project, outputs, artifact=previous.get("artifact"))
        self.save_record(record)
        return record

    # ---------------------------------------------------------------- record
    def save_record(self, record: Dict[str, Any]) -> Path:
        path = self.project.work_dir / RECORD_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, default=str), "utf-8")
        return path

    def _remember_onprem(self, record: Dict[str, Any]) -> None:
        """Keep the machine this stage now runs on: trigger, logs, test and the next deploy default to it."""
        from .onprem_control import deployed_on, remember_deploy

        options = self.project.config.provider.options
        deploy = options.get("deploy")
        server = str(deploy.get("server") or "") if isinstance(deploy, dict) else ""
        cluster = options.get("cluster")
        name = str(cluster.get("name") or "") if isinstance(cluster, dict) else ""
        data = remember_deploy(self.project.work_dir, server or None, name or None)
        if data is not None:
            record["deployed_on"] = deployed_on(data["spec"], data["server"], data.get("cluster"))
        groups = (record.get("outputs") or {}).get("groups") if isinstance(record.get("outputs"), dict) else None
        if isinstance(groups, dict) and groups:
            record["groups"] = groups  # provider.options.placement: where each group of functions runs

    def _onprem_raw(self) -> Dict[str, Any]:
        cfg = self.project.config
        return {"service": cfg.service,
                "provider": {"name": "onprem", "stage": cfg.provider.stage, "options": cfg.provider.options}}

    def _onprem_services_follow(self) -> None:
        """Before an on-prem deploy: the services the functions use are reachable from where they will run."""
        from . import onprem_follow

        try:
            onprem_follow.follow(self.project.root, self._onprem_raw(), list(self.project.config.resources),
                                 self.echo)
        except Exception as exc:  # noqa: BLE001 - only a check; the deploy goes on
            self.echo(f"  WARNING: services not checked: {exc}")

    def _onprem_smtp(self) -> None:
        """After an on-prem deploy: the SMTP servers the functions have triggers on send mail to where they run now,
        and the firewall rules the function servers need to reach every service they use."""
        from . import onprem_follow, onprem_smtp

        cfg = self.project.config
        keys = [k for k in cfg.event_resources() if k in cfg.resources and cfg.resources[k].type == "smtp"]
        try:
            if keys:
                onprem_smtp.retarget(self.project.root, self._onprem_raw(), keys, self.echo)
            onprem_follow.firewall(self.project.root, list(cfg.resources), self.echo,
                                   f"{cfg.service} ({cfg.provider.stage}): services the functions use")
        except Exception as exc:  # noqa: BLE001 - the deploy itself succeeded
            self.echo(f"  WARNING: services not updated: {exc}")

    def _onprem_balancers(self, record: Dict[str, Any]) -> None:
        """After an on-prem deploy: this deployment's routes on the load balancers in provider.options.balancer."""
        from .onprem_control import deployed_host

        data = deployed_host(self.project.root, self.project.config.provider.stage)
        groups = record.get("groups") if isinstance(record.get("groups"), dict) else None
        routes = self._sync_balancers(self.project.config.provider.options, data, groups)
        if routes is not None:
            record["balancers"] = routes
            self._remember_routes(routes)

    def _sync_balancers(self, options: Dict[str, Any], data: Optional[Dict[str, Any]],
                        groups: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """``provider.options.balancer``: this deployment's route on each named load balancer (only warns)."""
        from .onprem_balancers import BalancerError, parse_option, sync_project
        from .onprem_cluster import scripts as cluster_scripts

        try:
            wanted = parse_option(options.get("balancer"))
        except ValueError as exc:
            self.echo(f"  WARNING: provider.options.balancer: {exc}")
            return None
        previous = self._remembered_routes()
        if not wanted and not previous:
            return None
        cfg = self.project.config
        owner = cluster_scripts.stack_name(cfg.service, cfg.provider.stage)
        try:
            backends = self._backends(data, groups)
            return sync_project(self.project.root, wanted, owner, cfg.service, cfg.provider.stage, backends,
                                self.echo, previous=previous)
        except (BalancerError, ValueError) as exc:
            self.echo(f"  WARNING: load balancer not updated: {exc}")
            return None

    def _backends(self, data: Optional[Dict[str, Any]], groups: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Where the load balancer sends this deployment's HTTP: a cluster's servers, or each host serving HTTP
        (with placement, the default group's host: it passes a route on to the group that has it)."""
        from urllib.parse import urlsplit

        from .onprem_balancers import cluster_backends, owner_backends
        from .onprem_cluster import _ip, get_cluster, load_clusters
        from .onprem_cluster import scripts as cluster_scripts

        spec = (data or {}).get("spec") or {}
        cluster = (data or {}).get("cluster")
        port = int(spec.get("port") or 8080)
        if cluster:
            # Placement groups on other clusters too: every group's host passes the others' routes on.
            names = {str(cluster)} | {str(g.get("cluster")) for g in (groups or {}).values()
                                      if isinstance(g, dict) and g.get("cluster")}
            clusters = {n: c for n, c in load_clusters(self.project.root).items() if n in names}
            cfg = self.project.config
            found = owner_backends(clusters, cluster_scripts.stack_name(cfg.service, cfg.provider.stage))
            return found or cluster_backends(get_cluster(self.project.root, str(cluster)), port)
        # With placement only the default group passes routes on (placement.gateway): it is the entry point.
        endpoints = [spec.get("endpoint")]
        out = []
        for endpoint in endpoints:
            url = urlsplit(str(endpoint or ""))
            host = url.hostname or ""
            if not host or host in ("127.0.0.1", "localhost", "::1"):
                raise ValueError(f"the host answers on {endpoint}, which the load balancer server cannot reach:"
                                 " set provider.options.advertise (and host: 0.0.0.0)")
            out.append({"address": _ip(host), "port": int(url.port or port), "server": host})
        return out

    def _remembered_routes(self) -> List[Dict[str, Any]]:
        try:
            data = json.loads((self.project.work_dir / "onprem_deployed.json").read_text("utf-8"))
        except (OSError, ValueError):
            return []
        return [r for r in data.get("balancers") or [] if isinstance(r, dict)]

    def _remember_routes(self, routes: List[Dict[str, Any]]) -> None:
        path = self.project.work_dir / "onprem_deployed.json"
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return
        data["balancers"] = routes
        path.write_bytes((json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    def load_record(self) -> Optional[Dict[str, Any]]:
        path = self.project.work_dir / RECORD_FILE
        if path.is_file():
            return json.loads(path.read_text("utf-8"))
        return None


def _artifact_record(result: PackageResult) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "sha256": result.artifact.sha256,
        "size": result.artifact.size,
        "unpacked_size": result.artifact.unpacked_size,
        "files": result.artifact.file_count,
        "package_type": result.package.type if result.package else "zip",
    }
    return out


def _write_gitignore(pskit_dir: Path) -> None:
    pskit_dir.mkdir(parents=True, exist_ok=True)
    gi = pskit_dir / ".gitignore"
    if not gi.exists():
        gi.write_text(
            "# Generated by py-serverless-kit. Keep terraform state out of git -\n"
            "# configure a remote backend (provider.state) for team use.\n*\n",
            "utf-8",
        )
