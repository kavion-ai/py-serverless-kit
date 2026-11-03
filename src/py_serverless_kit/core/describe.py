"""Builds the deployment record that powers ``pskit info`` and the dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .._version import __version__
from ..config.schema import EventSpec, FunctionConfig, is_generated_handler
from .project import Project

RECORD_FILE = "deployment.json"


def event_summary(ev: EventSpec) -> Dict[str, Any]:
    c = ev.config
    if ev.type == "http":
        text = f"{c.method} {c.path}"
        extra = {"method": c.method, "path": c.path, "auth": c.auth, "cors": bool(c.cors)}
    elif ev.type == "schedule":
        text = f"rate({c.rate})" if c.rate else f"cron({c.cron})"
        extra = {"rate": c.rate, "cron": c.cron, "enabled": c.enabled}
    elif ev.type == "queue":
        text = f"queue {c.name} (batch {c.batch_size})"
        extra = {"name": c.name, "batch_size": c.batch_size, "existing": c.existing}
    elif ev.type == "storage":
        filt = "".join(f" {k}={v}" for k, v in (("prefix", c.prefix), ("suffix", c.suffix)) if v)
        text = f"bucket {c.bucket} [{', '.join(c.events)}]{filt}"
        extra = {"bucket": c.bucket, "events": list(c.events), "prefix": c.prefix, "suffix": c.suffix}
    elif ev.type == "smtp":
        text = f"smtp {c.name or c.resource}"
        extra = {"name": c.name, "resource": c.resource}
    else:
        text = f"topic {c.name}"
        extra = {"name": c.name, "existing": c.existing}
    if ev.type in ("queue", "storage", "topic") and c.resource:
        text += f" <- resource {c.resource}" + (" (external)" if c.existing else "")
        extra["resource"] = c.resource
    return {"type": ev.type, "summary": text, **extra}


def resource_records(project: Project) -> List[Dict[str, Any]]:
    """Bound resources, without connection values (they may hold secrets)."""
    cfg = project.config
    return [
        {
            "name": key,
            "type": res.type,
            "external": res.external,
            "native_name": res.native_name(key),
            "functions": cfg.resource_functions(key),
            "connection_keys": sorted(res.connection),
        }
        for key, res in sorted(cfg.resources.items())
    ]


def function_record(project: Project, name: str, fn: FunctionConfig, out: Dict[str, Any]) -> Dict[str, Any]:
    cfg = project.config
    events = [event_summary(e) for e in fn.events]
    url = out.get("url")
    urls = []
    for e in events:
        if e["type"] == "http" and out.get("base_url"):
            urls.append({"method": e["method"], "url": out["base_url"].rstrip("/") + e["path"]})
    return {
        "name": name,
        "resource_name": project.provider.physical_name(cfg.service, cfg.provider.stage, name),
        "handler": fn.handler,
        "description": fn.description,
        "kind": fn.kind,
        "generated": is_generated_handler(fn.handler),
        "runtime": cfg.runtime_of(fn),
        "memory": cfg.memory_of(fn),
        "timeout": cfg.timeout_of(fn),
        "architecture": cfg.architecture_of(fn),
        "events": events,
        "environment_keys": sorted(set(cfg.provider.environment) | set(fn.environment)),
        "id": out.get("id"),
        "arn": out.get("arn"),
        "url": url,
        "urls": urls,
        "console": out.get("console"),
    }


def build_record(
    project: Project,
    outputs: Optional[Dict[str, Any]] = None,
    artifact: Optional[Dict[str, Any]] = None,
    status: str = "deployed",
) -> Dict[str, Any]:
    outputs = outputs or {}
    pskit_out = outputs.get("pskit") or {}
    fn_out: Dict[str, Any] = pskit_out.get("functions") or {}
    wf_out: Dict[str, Any] = pskit_out.get("workflows") or {}
    cfg = project.config
    functions: List[Dict[str, Any]] = []
    for name, fn in sorted(cfg.functions.items()):
        functions.append(function_record(project, name, fn, dict(fn_out.get(name) or {})))
    workflows = []
    for name, wf in sorted(cfg.workflows.items()):
        out = dict(wf_out.get(name) or {})
        workflows.append(
            {
                "name": name,
                "description": wf.description,
                "engine": project.engines.get(name, "native"),
                "start_at": wf.start_at,
                "states": {k: v.type for k, v in wf.states.items()},
                "functions": sorted(set(wf.task_functions())),
                "id": out.get("id"),
                "url": out.get("url"),
                "console": out.get("console"),
            }
        )
    return {
        "schema": 1,
        "key": f"{cfg.provider.name}-{cfg.provider.stage}",
        "status": status,
        "service": cfg.service,
        "stage": cfg.provider.stage,
        "provider": cfg.provider.name,
        "provider_display": project.provider.display_name,
        "provider_tier": project.provider.tier,
        "region": project.region,
        "endpoint": pskit_out.get("endpoint"),
        "deployed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pskit_version": __version__,
        "config_file": str(project.loaded.path.name),
        "artifact": artifact or {},
        "functions": functions,
        "workflows": workflows,
        "resources": resource_records(project),
        "outputs": {k: v for k, v in outputs.items() if k != "pskit"},
    }
