"""How to call a deployed on-prem host from any program: the pskit client (Python, Node.js) and HTTP.

Built for one project: its endpoint, whether a token is needed, whether this machine can
reach the host right now, and code for each of its queues, buckets and topics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _fence(lang: str, text: str) -> str:
    return f"```{lang}\n{text.rstrip()}\n```\n"


def probe_host(endpoint: str, token: str = "", timeout: float = 4.0) -> Optional[str]:
    """None when ``/__pskit/health`` answers, else why not."""
    from ..client import PskitClient, PskitClientError

    try:
        PskitClient(endpoint, token, timeout=timeout).health()
    except PskitClientError as exc:
        return str(exc)
    return None


def python_example(endpoint: str, resources: List[Dict[str, str]]) -> str:
    lines = [
        "from py_serverless_kit.client import PskitClient",
        "",
        f'client = PskitClient("{endpoint}")          # token: PSKIT_ADMIN_TOKEN, or token="..."',
        "",
    ]
    for res in resources:
        key, kind = res["key"], res["type"]
        var = key.replace("-", "_")
        if kind == "queue":
            lines += [
                f'{var} = client.queue("{key}")',
                f'{var}.send({{"order_id": 1}}, attributes={{"kind": "new"}})      # add data',
                f"page = {var}.peek(limit=20)                                  # look, nothing consumed",
                "print(page.total, [m[\"body\"] for m in page.items])",
                f"# for msg in {var}.receive(batch=10): msg.ack()   # consume (only if no pskit trigger does)",
                "",
            ]
        elif kind == "storage":
            lines += [
                f'{var} = client.bucket("{key}")',
                f'{var}.put("in/hello.txt", "hello")',
                f'print({var}.get("in/hello.txt"))',
                f'print([o["key"] for o in {var}.list(prefix="in/").items])',
                f'{var}.delete("in/hello.txt")',
                "",
            ]
        elif kind == "topic":
            lines += [f'client.topic("{key}").publish({{"event": "created"}}, attributes={{"type": "order"}})', ""]
    if not resources:
        lines += ["print(client.resources())", ""]
    lines += ["print(client.health())"]
    return "\n".join(lines) + "\n"


def node_example(endpoint: str, resources: List[Dict[str, str]]) -> str:
    body: List[str] = []
    for res in resources:
        key, kind = res["key"], res["type"]
        var = "".join(p.capitalize() if i else p for i, p in enumerate(key.replace("_", "-").split("-")))
        if kind == "queue":
            body += [
                f'  const {var} = client.queue("{key}");',
                f'  await {var}.send({{ orderId: 1 }}, {{ kind: "new" }});              // add data',
                f"  const page = await {var}.peek({{ limit: 20 }});                    // look, nothing consumed",
                "  console.log(page.total, page.items.map((m) => m.body));",
                f"  // for (const msg of await {var}.receive({{ batch: 10 }})) await msg.ack();",
            ]
        elif kind == "storage":
            body += [
                f'  const {var} = client.bucket("{key}");',
                f'  await {var}.put("in/hello.txt", "hello");',
                f'  console.log((await {var}.get("in/hello.txt")).toString());',
                f'  console.log((await {var}.list({{ prefix: "in/" }})).items.map((o) => o.key));',
                f'  await {var}.delete("in/hello.txt");',
            ]
        elif kind == "topic":
            body += [f'  await client.topic("{key}").publish({{ event: "created" }}, {{ type: "order" }});']
    if not resources:
        body += ["  console.log(await client.resources());"]
    return (
        'const { PskitClient } = require("pskit");\n\n'
        f'const client = new PskitClient("{endpoint}");   // token: PSKIT_ADMIN_TOKEN, or {{ token: "..." }}\n\n'
        "async function main() {\n" + "\n".join(body) + "\n  console.log(await client.health());\n}\n\nmain();\n"
    )


def http_examples(endpoint: str, resources: List[Dict[str, str]], token: bool) -> List[str]:
    auth = ' -H "x-pskit-token: $PSKIT_ADMIN_TOKEN"' if token else ""
    out = [f"curl{auth} {endpoint}/__pskit/health", f"curl{auth} {endpoint}/__pskit/resources"]
    for res in resources:
        key, name, kind = res["key"], res["name"], res["type"]
        if kind == "queue":
            out += [
                f"curl{auth} -X POST {endpoint}/__pskit/queues/{name} -H 'content-type: application/json' -d '{{\"order_id\": 1}}'",
                f"curl{auth} '{endpoint}/__pskit/resources/{key}/data?offset=0&limit=20'",
                f"curl{auth} -X POST {endpoint}/__pskit/queues/{name}/lease -d '{{\"batch\": 10, \"visibility\": 60}}'",
            ]
        elif kind == "storage":
            out += [
                f"curl{auth} -X PUT --data-binary @report.csv {endpoint}/__pskit/storage/{name}/in/report.csv",
                f"curl{auth} '{endpoint}/__pskit/storage/{name}?prefix=in/&limit=50'",
                f"curl{auth} -o report.csv {endpoint}/__pskit/storage/{name}/in/report.csv",
            ]
        elif kind == "topic":
            out += [f"curl{auth} -X POST {endpoint}/__pskit/topics/{name} -d '{{\"message\": {{\"id\": 1}}, \"attributes\": {{\"type\": \"order\"}}}}'"]
    return out


def client_guide(project: Any, endpoint: str, token: bool, probe: bool = True) -> Dict[str, Any]:
    cfg = project.config
    resources = [
        {"key": k, "name": r.native_name(k), "type": r.type}
        for k, r in sorted(cfg.resources.items())
        if r.type in ("queue", "storage", "topic")
    ]
    problem = probe_host(endpoint) if probe else None
    stage = cfg.provider.stage
    md: List[str] = ["# Call the pskit host from any program\n"]
    md.append(
        f"Host: `{endpoint}` (`{cfg.service}`, stage `{stage}`). Every call goes through its `/__pskit` HTTP API, so "
        "only this port must be reachable; the queues and buckets behind it may use any driver (built-in, Redis, "
        "Kafka, SQS, MinIO, ...) and stay closed to the outside.\n"
    )
    if token:
        md.append("The host has an `admin_token`: export it as `PSKIT_ADMIN_TOKEN` (or pass `token=`).\n")
    if probe:
        if problem:
            md.append(
                f"**Not reachable from this machine right now.** {problem}\n\n"
                "Fix one of these, then run `pskit client info` again:\n\n"
                f"1. Open port `{endpoint.rsplit(':', 1)[-1]}` to your IP in the server's firewall (Azure: network "
                "security group inbound rule; AWS: security group; or `ufw allow`).\n"
                f"2. Or tunnel it: `pskit client tunnel -s {stage}` and use `http://127.0.0.1:"
                f"{endpoint.rsplit(':', 1)[-1]}` below.\n"
            )
        else:
            md.append("Reachable from this machine.\n")
    md.append("## Python\n")
    md.append(_fence("bash", "pip install py-serverless-kit        # the client has no other dependencies"))
    md.append(_fence("python", python_example(endpoint, resources)))
    md.append("## Node.js (18+)\n")
    md.append(
        _fence("bash", "pskit client install-node             # copies the pskit package into ./node_modules/pskit")
    )
    md.append(_fence("js", node_example(endpoint, resources)))
    md.append("## HTTP (any language)\n")
    md.append(_fence("bash", "\n".join(http_examples(endpoint, resources, token))))
    md.append(
        "Full API: `docs/client.md`. Talking to a service directly (its own library and port) is shown under "
        "*On-prem services > How to use*; when that port is firewalled, use `pskit resources onprem tunnel <key>`.\n"
    )
    return {"endpoint": endpoint, "reachable": problem is None if probe else None, "problem": problem,
            "markdown": "\n".join(md)}
