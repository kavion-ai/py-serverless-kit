"""Shared scaffolding for the on-premises category C batches c_fix_11 .. c_fix_18 (helpers only; every
conversation is written by hand in the batch files)."""

import json

FUTURE = "from __future__ import annotations\n\n"
T0 = "2026-10-01T00:00:00+00:00"
SERVERS = {"app-1": "192.0.2.10", "app-2": "192.0.2.11", "db-1": "192.0.2.20", "gpu-box": "198.51.100.7"}


def C(n, **kw):
    return dict(id=f"c_fix-{n:04d}", category="c_fix", **kw)


def handlers(*names):
    body = FUTURE
    for name in names:
        body += f"\ndef {name}(event, ctx):\n    return {{\"ok\": True, \"fn\": \"{name}\"}}\n\n"
    return body.rstrip() + "\n"


def app(module, *names):
    return {"app/__init__.py": "", f"app/{module}.py": handlers(*names)}


def mods(**modules):
    """app/<module>.py per keyword (space-separated function names)."""
    out = {"app/__init__.py": ""}
    for module, names in modules.items():
        out[f"app/{module}.py"] = handlers(*names.split())
    return out


def saved(*names):
    """The project's saved SSH servers (.pskit/onprem-servers.json)."""
    body = {n: {"host": SERVERS[n], "user": "pskit", "port": 22, "sudo": True} for n in names}
    return {".pskit/onprem-servers.json": json.dumps({"servers": body}, indent=2, sort_keys=True) + "\n"}


def cluster(name, orchestrator, *names):
    """Saved servers plus one saved cluster whose first server is the master."""
    nodes = {n: {"role": "master" if i == 0 else "worker", "node": n, "address": SERVERS[n], "joined_at": T0}
             for i, n in enumerate(names)}
    item = {"orchestrator": orchestrator, "master": names[0], "advertise": SERVERS[names[0]], "nodes": nodes,
            "capacity": {}, "alert": {}, "created_at": T0, "master_serves": orchestrator != "nomad"}
    return {**saved(*names), ".pskit/onprem-clusters.json": json.dumps({"clusters": {name: item}}, indent=2) + "\n"}


def onprem(service, rest, port=8080, host="127.0.0.1", extra=""):
    """Header of an on-prem pskit.yml; `extra` = more provider.options lines (already indented 4 spaces)."""
    return f"""service: {service}
provider:
  name: onprem
  region: local
  options:
    host: {host}
    port: {port}
{extra}{rest}"""
