"""Provider plug-in contract.

A provider turns a validated :class:`ServiceConfig` plus a built artifact into
a :class:`TerraformDoc`, and supplies the small *shim* files that sit at the
root of the bundle and forward the platform's native entrypoint to
``py_serverless_kit.runtime.adapters.<provider>``.

Adding a new cloud = subclass :class:`Provider`, write an adapter module, and
register it in ``providers/registry.py``. See CONTRIBUTING.md.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Dict, FrozenSet, List, Optional, Tuple

from ..config.schema import EVENT_RESOURCE_TYPES, FunctionConfig, ResourceConfig, ServiceConfig, WorkflowConfig
from .terraform_doc import TerraformDoc

# Capability flags ------------------------------------------------------------
HTTP = "http"
SCHEDULE = "schedule"
QUEUE = "queue"
STORAGE = "storage"
TOPIC = "topic"
WORKFLOW_NATIVE = "workflow_native"
ALL_CAPABILITIES = (HTTP, SCHEDULE, QUEUE, STORAGE, TOPIC, WORKFLOW_NATIVE)
SMTP = "smtp"  # mail received by the host's SMTP server (on premises only)
EVENT_CAPABILITIES = frozenset({HTTP, SCHEDULE, QUEUE, STORAGE, TOPIC, SMTP})

ORCHESTRATOR_HANDLER = "py_serverless_kit.runtime.workflow.orchestrate"
# The Node.js runtime is vendored at the bundle root as ``pskit_runtime/`` (see deploy_docs/NODE_RUNTIME.md).
ORCHESTRATOR_HANDLER_NODE = "pskit_runtime.workflow.orchestrate"
PREFERRED_RUNTIME = "python3.12"
PREFERRED_NODE_RUNTIME = "nodejs20"


def orchestrator_handler(language: str) -> str:
    return ORCHESTRATOR_HANDLER_NODE if language == "node" else ORCHESTRATOR_HANDLER


class ProviderError(Exception):
    pass


@dataclass
class Artifact:
    path: Path
    sha256: str
    sha256_b64: str
    size: int
    file_count: int = 0
    build_dir: Optional[Path] = None
    skip_deps: bool = False  # built without installing dependencies (pskit package --skip-deps, tests)


@dataclass
class Issue:
    level: str  # "error" | "warning"
    message: str
    where: str = ""

    def __str__(self) -> str:
        loc = f"[{self.where}] " if self.where else ""
        return f"{self.level.upper()}: {loc}{self.message}"


@dataclass
class RenderContext:
    config: ServiceConfig
    provider: Provider
    root: Path
    work_dir: Path
    artifact: Artifact
    region: str
    workflow_engines: Dict[str, str] = field(default_factory=dict)

    @property
    def service(self) -> str:
        return self.config.service

    @property
    def stage(self) -> str:
        return self.config.provider.stage

    @property
    def options(self) -> Dict[str, Any]:
        return self.config.provider.options

    def opt(self, key: str, default: Any = None) -> Any:
        return self.config.provider.options.get(key, default)

    def physical_name(self, logical: str) -> str:
        return self.provider.physical_name(self.service, self.stage, logical)

    @property
    def prefix(self) -> str:
        return self.provider.physical_name(self.service, self.stage, "")

    def tags(self, fn: Optional[FunctionConfig] = None) -> Dict[str, str]:
        base = {
            "pskit-service": self.service,
            "pskit-stage": self.stage,
            "managed-by": "py-serverless-kit",
        }
        base.update(self.config.provider.tags)
        if fn is not None:
            base.update(fn.tags)
        return base

    def environment(self, name: str, fn: FunctionConfig) -> Dict[str, str]:
        env = {
            "PSKIT_PROVIDER": self.provider.name,
            "PSKIT_SERVICE": self.service,
            "PSKIT_STAGE": self.stage,
            "PSKIT_REGION": self.region,
            "PSKIT_FUNCTION": name,
            "PSKIT_HANDLER": fn.handler,
        }
        env.update(self.resource_environment(name))
        env.update(self.config.provider.environment)
        env.update(fn.environment)
        return env

    def resource_environment(self, name: str) -> Dict[str, str]:
        """``PSKIT_RESOURCE_<KEY>_*`` variables for the resources bound to function ``name``.

        Values are plain strings (providers escape them). Terraform references a
        provider adds through :meth:`Provider.resource_refs` use the ``${tf:...}``
        form, which :func:`escape` turns into a live reference.
        """
        return self.config.binding_environment(name, lambda key, res: self.provider.resource_refs(self, key, res))

    def function_items(self) -> List[tuple]:
        return sorted(self.config.functions.items())


def stable_suffix(*parts: str, length: int = 6) -> str:
    # Naming only, not security: keeps generated names short, stable and unique.
    return hashlib.sha1("/".join(parts).encode(), usedforsecurity=False).hexdigest()[:length]


class Provider(ABC):
    name: ClassVar[str]
    display_name: ClassVar[str]
    tier: ClassVar[str] = "beta"  # stable | beta | experimental
    terraform_source: ClassVar[str]
    terraform_version: ClassVar[Optional[str]] = None
    terraform_local_name: ClassVar[Optional[str]] = None
    default_region: ClassVar[str] = ""
    capabilities: ClassVar[FrozenSet[str]] = frozenset({HTTP})
    max_name_length: ClassVar[int] = 64
    name_pattern: ClassVar[str] = r"[^a-z0-9-]"
    runtimes: ClassVar[Dict[str, str]] = {}
    # Node.js runtimes: ``nodejs20`` -> the platform's id (e.g. ``nodejs20.x``). Empty = no Node.js support.
    node_runtimes: ClassVar[Dict[str, str]] = {}
    vendor_dependencies: ClassVar[bool] = True
    # Node.js: npm-install production dependencies into the bundle (False when the platform builds remotely).
    node_vendor_dependencies: ClassVar[bool] = True
    # Node.js: the platform needs one bundled file per entry (esbuild), e.g. Cloudflare Workers.
    node_bundle: ClassVar[bool] = False
    extra_requirements: ClassVar[List[str]] = []
    max_timeout: ClassVar[int] = 900
    # Managed storage/queue/topic resources that no event uses are created by this provider.
    standalone_resources: ClassVar[bool] = False
    # A storage event may name a storage resource (the service) and another bucket on it.
    storage_service_buckets: ClassVar[bool] = False
    # Embedded workflows on a cloud function are capped by that function's timeout.
    # A long-running host (on-premises) sets this to False.
    warn_on_embedded_workflow: ClassVar[bool] = True
    notes: ClassVar[str] = ""

    # ------------------------------------------------------------ naming
    def physical_name(self, service: str, stage: str, logical: str) -> str:
        raw = "-".join(p for p in (service, stage, logical) if p)
        name = re.sub(self.name_pattern, "-", raw.lower()).strip("-")
        name = re.sub(r"-{2,}", "-", name)
        if len(name) > self.max_name_length:
            digest = stable_suffix(raw)
            name = name[: self.max_name_length - len(digest) - 1].rstrip("-") + "-" + digest
        return name

    @property
    def default_runtime(self) -> str:
        """Runtime used when the config does not pin one: python3.12, or the newest
        version this provider supports below it (so switching clouds just works)."""
        if not self.runtimes or PREFERRED_RUNTIME in self.runtimes:
            return PREFERRED_RUNTIME

        def minor(rt: str) -> int:
            return int(rt.split(".")[1])

        older = [rt for rt in self.runtimes if minor(rt) <= minor(PREFERRED_RUNTIME)]
        return max(older or list(self.runtimes), key=minor)

    def default_runtime_for(self, language: str) -> str:
        """Default runtime for ``language``: :attr:`default_runtime` for Python, nodejs20 (or nearest) for Node.js."""
        if language != "node":
            return self.default_runtime
        if not self.node_runtimes or PREFERRED_NODE_RUNTIME in self.node_runtimes:
            return PREFERRED_NODE_RUNTIME
        major = int(PREFERRED_NODE_RUNTIME[6:])
        older = [rt for rt in self.node_runtimes if int(rt[6:]) <= major]
        return max(older or list(self.node_runtimes), key=lambda rt: int(rt[6:]))

    def runtime_id(self, runtime: str) -> str:
        from ..config.schema import runtime_language

        if runtime_language(runtime) == "node":
            if not self.node_runtimes:
                raise ProviderError(f"{self.display_name} does not support Node.js functions in pskit yet")
            if runtime not in self.node_runtimes:
                supported = ", ".join(sorted(self.node_runtimes))
                raise ProviderError(f"{self.display_name} does not support {runtime}; use one of: {supported}")
            return self.node_runtimes[runtime]
        if self.runtimes and runtime not in self.runtimes:
            supported = ", ".join(sorted(self.runtimes))
            raise ProviderError(f"{self.display_name} does not support {runtime}; use one of: {supported}")
        return self.runtimes.get(runtime, runtime)

    def region(self, config: ServiceConfig) -> str:
        return config.provider.region or self.default_region

    def pip_platform(self, runtime: str, architecture: str) -> List[str]:
        """pip flags that download Linux wheels matching the target runtime."""
        version = runtime.replace("python", "")
        machine = "aarch64" if architecture == "arm64" else "x86_64"
        return [
            "--platform",
            f"manylinux2014_{machine}",
            "--implementation",
            "cp",
            "--python-version",
            version,
            "--only-binary=:all:",
        ]

    def pip_platform_for(self, config: ServiceConfig) -> List[str]:
        return self.pip_platform(config.provider.runtime, config.provider.architecture)

    # ------------------------------------------------------------ validation
    def workflow_engine(self, wf: WorkflowConfig) -> str:
        if wf.engine == "native":
            if WORKFLOW_NATIVE not in self.capabilities:
                raise ProviderError(
                    f"{self.display_name} has no native workflow service supported by pskit; "
                    "use `engine: embedded` or `auto`"
                )
            return "native"
        if wf.engine == "embedded":
            return "embedded"
        return "native" if WORKFLOW_NATIVE in self.capabilities else "embedded"

    def validate(self, config: ServiceConfig) -> List[Issue]:
        issues: List[Issue] = []
        try:
            self.runtime_id(config.provider.runtime)
        except ProviderError as exc:
            issues.append(Issue("error", str(exc), "provider.runtime"))
        for name, fn in config.functions.items():
            where = f"functions.{name}"
            if fn.runtime:
                try:
                    self.runtime_id(fn.runtime)
                except ProviderError as exc:
                    issues.append(Issue("error", str(exc), where + ".runtime"))
            for ev in fn.events:
                if ev.type not in self.capabilities:
                    issues.append(
                        Issue(
                            "error",
                            f"{self.display_name} does not support `{ev.type}` events in pskit "
                            f"(supported: {', '.join(sorted(self.capabilities & EVENT_CAPABILITIES))})",
                            where,
                        )
                    )
            if not self.storage_service_buckets:
                for sev in fn.events_of("storage"):
                    res = config.resources.get(sev.resource or "")
                    if res is not None and sev.bucket != res.native_name(str(sev.resource)):
                        issues.append(
                            Issue(
                                "error",
                                f"storage event sets both `resource: {sev.resource}` and `bucket: {sev.bucket}`; "
                                f"another bucket on a resource's service is on-premises only. On "
                                f"{self.display_name} use one of them",
                                where,
                            )
                        )
            if config.timeout_of(fn) > self.max_timeout:
                issues.append(
                    Issue(
                        "error",
                        f"timeout {config.timeout_of(fn)}s exceeds {self.display_name} max {self.max_timeout}s",
                        where,
                    )
                )
        for name, wf in config.workflows.items():
            try:
                engine = self.workflow_engine(wf)
            except ProviderError as exc:
                issues.append(Issue("error", str(exc), f"workflows.{name}"))
                continue
            if engine == "embedded" and self.warn_on_embedded_workflow:
                issues.append(
                    Issue(
                        "warning",
                        "runs on the embedded engine inside one function: total runtime is capped by the "
                        f"function timeout ({self.max_timeout}s max on {self.display_name})",
                        f"workflows.{name}",
                    )
                )
        issues.extend(self.resource_validation(config))
        issues.extend(self.extra_validation(config))
        return issues

    def resource_validation(self, config: ServiceConfig) -> List[Issue]:
        issues: List[Issue] = []
        used = config.event_resources()
        for key, res in sorted(config.resources.items()):
            where = f"resources.{key}"
            if res.external or res.type not in EVENT_RESOURCE_TYPES or key in used:
                continue
            if not self.standalone_resources:
                issues.append(
                    Issue(
                        "error",
                        f"managed {res.type} resources that no event uses are not supported on {self.display_name} "
                        "yet; create it outside pskit and set `external: true`",
                        where,
                    )
                )
            elif res.type not in self.capabilities:
                issues.append(
                    Issue("error", f"{self.display_name} does not support {res.type} resources in pskit", where)
                )
        return issues

    def resource_refs(self, ctx: RenderContext, key: str, res: ResourceConfig) -> Dict[str, str]:
        """Extra binding values the provider knows (``{"ARN": "${tf:...}", "URL": ...}``).

        Use the ``${tf:<expression>}`` form; only providers that escape environment
        values may return references.
        """
        return {}

    def standalone(self, config: ServiceConfig) -> List[Tuple[str, ResourceConfig]]:
        """Managed storage/queue/topic resources no event creates: the provider must create them."""
        used = config.event_resources()
        return [
            (key, res)
            for key, res in sorted(config.resources.items())
            if not res.external and res.type in EVENT_RESOURCE_TYPES and key not in used
        ]

    def extra_validation(self, config: ServiceConfig) -> List[Issue]:
        return []

    def validate_files(self, config: ServiceConfig, root: Path) -> List[Issue]:
        """Checks that need the project directory (files the config points at)."""
        del config, root
        return []

    # ------------------------------------------------------------ terraform
    def init_doc(self, ctx: RenderContext) -> TerraformDoc:
        doc = TerraformDoc()
        tf = ctx.config.provider.terraform
        doc.required_version(tf.required_version)
        local = self.terraform_local_name or self.name
        doc.required_provider(local, self.terraform_source, tf.provider_version or self.terraform_version)
        state = ctx.config.provider.state
        if state.backend:
            doc.backend(state.backend, state.config)
        block = self.provider_block(ctx)
        if block is not None:
            doc.provider(local, block)
        return doc

    def provider_block(self, ctx: RenderContext) -> Optional[Dict[str, Any]]:
        return {"region": ctx.region} if ctx.region else {}

    def render(self, ctx: RenderContext) -> TerraformDoc:
        doc = self.init_doc(ctx)
        self.render_resources(doc, ctx)
        extra = ctx.config.provider.terraform.extra
        if extra:
            doc.merge(extra)
        return doc

    @abstractmethod
    def render_resources(self, doc: TerraformDoc, ctx: RenderContext) -> None:
        """Add every resource for functions, triggers and workflows to ``doc``.

        Must emit an output named ``pskit`` shaped like::

            {"functions": {"<name>": {"id": ..., "url": ...}}, "workflows": {...}, "endpoint": ...}
        """

    # ------------------------------------------------------------ bundle
    @abstractmethod
    def shim_files(self, config: ServiceConfig) -> Dict[str, str]:
        """Files written at the bundle root that forward to the adapter."""

    def bundle_requirements(self, user_requirements: List[str]) -> List[str]:
        return list(user_requirements) + [r for r in self.extra_requirements if r not in user_requirements]

    def bundle_function_requirements(self, config: ServiceConfig) -> bool:
        """Whether the bundle gets the requirements of every function sub-project (``functions/<name>/
        requirements.txt``). On premises with functions placed on several servers each server gets only its own."""
        del config
        return True

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "tier": self.tier,
            "default_region": self.default_region,
            "capabilities": sorted(self.capabilities),
            "runtimes": sorted(self.runtimes),
            "node_runtimes": sorted(self.node_runtimes, key=lambda rt: int(rt[6:])),
            "max_timeout": self.max_timeout,
            "storage_service_buckets": self.storage_service_buckets,
            "terraform_provider": self.terraform_source,
            "notes": self.notes,
        }
