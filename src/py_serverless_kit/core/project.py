"""A loaded project: config + provider + working directory, ready to build/deploy."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config.loader import LoadedConfig, load_config
from ..config.schema import EventSpec, FunctionConfig, HttpEvent, ServiceConfig, is_generated_handler
from ..providers.base import HTTP, Issue, Provider, orchestrator_handler
from ..providers.registry import get_provider
from ..workflows import definition_dict

WORK_DIR = ".pskit"


def _apply_saved_server(options: Dict[str, Any], root: Path, stage: str) -> None:
    """``--server`` / ``--cluster`` / ``deploy: {server: NAME}`` / ``cluster: NAME`` / the last deploy's target becomes
    the deploy target."""
    import os

    from ..config.loader import ConfigError
    from .onprem_placement import PlacementError, configured
    from .onprem_placement import resolve as resolve_placement
    from .onprem_servers import CLUSTER_ENV, SERVER_ENV, ServerError, resolve_deploy

    server, cluster = os.environ.get(SERVER_ENV) or None, os.environ.get(CLUSTER_ENV) or None
    try:
        if configured(options):  # functions on several servers: every group's target (core/onprem_placement.py)
            resolve_placement(options, root, stage, server, cluster)
        else:
            resolve_deploy(options, root, stage, server, cluster)
    except (ServerError, PlacementError) as exc:
        raise ConfigError(str(exc)) from None


def shadowed_provider_settings(path: Path, provider: str) -> List[Issue]:
    """Warn when ``providers.<provider>`` overrides a different value under ``provider:`` for that same provider.

    The override wins, so a value edited under ``provider:`` (the studio's Overview) silently does nothing. Seen
    with a copy left there by switching providers in the studio, e.g. ``providers.onprem.options.host: 127.0.0.1``.
    """
    from ..config.loader import _provider_override, _read_layers

    issues: List[Issue] = []

    def leaves(value: Any, prefix: str) -> List[Tuple[str, Any]]:
        if isinstance(value, dict) and value:
            return [leaf for k, v in value.items() for leaf in leaves(v, f"{prefix}.{k}")]
        return [(prefix, value)]

    def lookup(data: Any, dotted: str) -> Any:
        for part in dotted.split(".")[1:]:
            if not isinstance(data, dict) or part not in data:
                return _MISSING
            data = data[part]
        return data

    try:
        layers = _read_layers(Path(path).resolve())
    except Exception:  # noqa: BLE001 - loading already reported it
        return issues
    for layer in layers:
        top: Dict[str, Any] = layer["provider"] if isinstance(layer.get("provider"), dict) else {}
        if top.get("name") != provider:
            continue
        block = ((layer.get("providers") or {}).get(provider)) or {}
        shadow = _provider_override(block).get("provider") if isinstance(block, dict) else None
        for dotted, value in leaves(shadow or {}, "provider"):
            mine = lookup(top, dotted)
            if mine is not _MISSING and mine != value and not isinstance(mine, dict):
                issues.append(Issue(
                    "warning",
                    f"providers.{provider} sets {dotted.split('.', 1)[1]} to {value!r}, which overrides {mine!r} under "
                    f"provider: (the override wins). Remove it from providers.{provider}, or use the studio's "
                    "Overview -> 'Use the values shown here'",
                    f"providers.{provider}.{dotted.split('.', 1)[1]}",
                ))
    return issues


_MISSING = object()


def orchestrator_name(workflow: str) -> str:
    return f"{workflow}-orchestrator"


@dataclass
class Project:
    loaded: LoadedConfig
    provider: Provider
    config: ServiceConfig
    engines: Dict[str, str] = field(default_factory=dict)

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(
        cls,
        config_path: Optional[str] = None,
        *,
        provider: Optional[str] = None,
        stage: Optional[str] = None,
        region: Optional[str] = None,
        cwd: Optional[Path] = None,
    ) -> Project:
        loaded = load_config(config_path, provider=provider, stage=stage, region=region, cwd=cwd)
        return cls.from_loaded(loaded)

    @classmethod
    def from_loaded(cls, loaded: LoadedConfig) -> Project:
        prov = get_provider(loaded.config.provider.name)
        config = loaded.config
        if config.provider.name == "onprem":
            _apply_saved_server(config.provider.options, loaded.root, config.provider.stage)
        if "runtime" not in (loaded.raw.get("provider") or {}):
            # Not pinned by the user: pick what this cloud supports.
            provider_cfg = config.provider.model_copy(update={"runtime": prov.default_runtime})
            config = config.model_copy(update={"provider": provider_cfg})
        config, engines = expand(config, prov)
        return cls(loaded=loaded, provider=prov, config=config, engines=engines)

    # ---------------------------------------------------------------- paths
    @property
    def root(self) -> Path:
        return self.loaded.root

    @property
    def work_dir(self) -> Path:
        return self.root / WORK_DIR / f"{self.config.provider.name}-{self.config.provider.stage}"

    @property
    def region(self) -> str:
        return self.provider.region(self.config)

    # ---------------------------------------------------------------- checks
    def validate(self) -> List[Issue]:
        issues = self.provider.validate(self.config)
        issues.extend(self.provider.validate_files(self.config, self.root))
        issues.extend(shadowed_provider_settings(self.loaded.path, self.config.provider.name))
        for kind, names in self.config.disabled.items():
            for name in names:
                issues.append(Issue("warning", "disabled (enabled: false): not deployed", f"{kind}.{name}"))
        source =(self.root / self.config.package.source).resolve()
        if not source.is_dir():
            issues.append(Issue("error", f"package.source {source} is not a directory", "package.source"))
        for name, fn in self.config.functions.items():
            if is_generated_handler(fn.handler):
                continue
            module = fn.handler.replace(":", ".").rsplit(".", 1)[0]
            rel = Path(*module.split("."))
            if self.config.language == "node":
                exts = (".ts", ".mts", ".js", ".mjs", ".cjs")
                found = any((source / rel).with_suffix(e).is_file() or (source / rel / f"index{e}").is_file() for e in exts)
            else:
                found = (source / rel).with_suffix(".py").is_file() or (source / rel / "__init__.py").is_file()
            if not found:
                issues.append(
                    Issue("warning", f"handler module {module!r} not found under {source}", f"functions.{name}.handler")
                )
        return issues

    # ---------------------------------------------------------------- bundle manifest
    def bundle_manifest(self) -> Dict[str, Any]:
        functions: Dict[str, Any] = {}
        for name, fn in sorted(self.config.functions.items()):
            routes = []
            for ev in fn.events_of("http"):
                cors = ev.cors_config
                routes.append(
                    {
                        "method": ev.method,
                        "path": ev.path,
                        "cors": cors.model_dump() if cors is not None else None,
                    }
                )
            functions[name] = {
                "handler": fn.handler,
                "routes": routes,
                "timeout": self.config.timeout_of(fn),
                "memory": self.config.memory_of(fn),
                "resource_name": self.provider.physical_name(self.config.service, self.config.provider.stage, name),
            }
        workflows: Dict[str, Any] = {}
        for name, wf in sorted(self.config.workflows.items()):
            if self.engines.get(name) != "embedded":
                continue
            workflows[name] = {"orchestrator": orchestrator_name(name), "definition": definition_dict(wf)}
            if wf.timeout:
                # Enforced by the embedded engine (the on-prem host has no function timeout above it).
                workflows[name]["timeout"] = wf.timeout
            if wf.options.get("start_on_entry") is False:
                # On premises: running the first task's function on its own does not start the workflow.
                workflows[name]["start_on_entry"] = False
        return {
            "service": self.config.service,
            "stage": self.config.provider.stage,
            "provider": self.config.provider.name,
            "region": self.region,
            "functions": functions,
            "workflows": workflows,
        }


def expand(config: ServiceConfig, provider: Provider) -> tuple[ServiceConfig, Dict[str, str]]:
    """Add generated functions (embedded workflow orchestrators) to the config."""
    engines: Dict[str, str] = {}
    functions = dict(config.functions)
    for name, wf in config.workflows.items():
        try:
            engine = provider.workflow_engine(wf)
        except Exception:  # noqa: BLE001 - reported properly by Provider.validate
            engine = "embedded"
        engines[name] = engine
        if engine != "embedded":
            continue
        orch = orchestrator_name(name)
        if orch in functions:
            continue
        events: List[EventSpec] = []
        if HTTP in provider.capabilities and wf.options.get("http", True):
            events.append(EventSpec(type="http", config=HttpEvent(method="POST", path=f"/workflows/{name}")))
        functions[orch] = FunctionConfig(
            handler=orchestrator_handler(config.language),
            description=f"Embedded orchestrator for workflow {name}",
            timeout=min(wf.timeout or provider.max_timeout, provider.max_timeout),
            events=events,
            tags={"pskit-workflow": name},
        )
    if functions == config.functions:
        return config, engines
    return config.model_copy(update={"functions": functions}), engines
