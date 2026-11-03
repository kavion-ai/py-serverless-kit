"""Category B (build / add), batch 13: on-premises only. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

SERVERS = json.dumps({"servers": {
    "app-1": {"host": "192.0.2.10", "user": "pskit", "port": 22},
    "app-2": {"host": "192.0.2.11", "user": "pskit", "port": 22},
    "app-3": {"host": "192.0.2.12", "user": "pskit", "port": 22}}}, indent=2)


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", provider="onprem", **kw)


def hello_project(service, port, extra_opts="", files=None):
    f = {
        "pskit.yml": f"""service: {service}
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: {port}
{extra_opts}functions:
  api:
    handler: app.api.api
    events:
    - http: GET /
""",
        "app/__init__.py": "",
        "app/api.py": FUTURE + """

def api(event, ctx):
    return {"service": ctx.service, "stage": ctx.stage}
""",
        "requirements.txt": ""}
    f.update(files or {})
    return dict(files=f)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 241
    B(241, stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: docs-index
provider:
  name: onprem
  region: local
  options:
    port: 8241
functions:
  add-doc:
    handler: app.docs.add_doc
    events:
    - http: POST /docs
""",
          "app/__init__.py": "",
          "app/docs.py": FUTURE + """from py_serverless_kit.runtime.onprem_host import submit_queue


def add_doc(event, ctx):
    doc = event.http.json(default={}) or {}
    return {"queued": submit_queue("index-jobs", doc)}, 202
""",
          "requirements.txt": ""}),
      user="""Run locally on the Test page:

RuntimeError: not running inside an on-premises host (PSKIT_ONPREM_ROOT is unset)

I want to test add-doc on my laptop. Also nothing reads index-jobs yet, add a worker `index-doc` for it.""",
      steps=[
          S("read_file", path="app/docs.py"),
          S("search_docs", query="submit_queue from a handler PSKIT_ONPREM_ROOT",
            docs=[D("docs/providers.md", "onprem-on-premises", start="From a handler in that process", end="From a handler in that process")]),
          S("propose_plan", steps=["In add_doc: call submit_queue only when PSKIT_ONPREM_ROOT is set, otherwise log what would be queued",
                                   "Add `index_doc` and function `index-doc` on queue `index-jobs`",
                                   "Validate, invoke add-doc and index-doc"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/docs.py", content=FUTURE + """

def add_doc(event, ctx):
    doc = event.http.json(default={}) or {}
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        from py_serverless_kit.runtime.onprem_host import submit_queue

        return {"queued": submit_queue("index-jobs", doc)}, 202
    ctx.logger.info("not in a host: would queue", extra={"title": doc.get("title")})
    return {"queued": None}, 202


def index_doc(event, ctx):
    for record in event.records:
        doc = record.json(default={}) or {}
        ctx.logger.info("index", extra={"title": doc.get("title")})
    return {"indexed": len(event.records)}
"""),
          S("set_config", path="functions.index-doc",
            value={"handler": "app.docs.index_doc", "events": [{"queue": "index-jobs"}]}),
          S("invoke_local", function="add-doc", method="POST", path="/docs", data={"title": "Holiday policy"}),
          S("invoke_local", function="index-doc", type="queue", data=[{"title": "Holiday policy"}]),
      ],
      final="""Cause: `submit_queue` only works inside a running on-prem host, where `PSKIT_ONPREM_ROOT` is set [docs/providers.md#onprem-on-premises]. `pskit invoke` and **Test > ▶ Run locally** have no host, so the call failed.

Changes:
- `add_doc` calls `submit_queue` only when `PSKIT_ONPREM_ROOT` is set. Otherwise it logs what it would queue.
- New function `index-doc` reads `index-jobs` (`- queue: index-jobs`).

Checks:
- validate (onprem): valid.
- `POST /docs {"title": "Holiday policy"}`: 202, `{"queued": null}` (local run, logged only).
- `index-doc` with one doc: `{"indexed": 1}`.

After `pskit deploy -s dev`, the real queue is used: `pskit trigger -f add-doc -d '{"title": "x"}'`, then check `index-doc` in **Logs**."""),

    # ------------------------------------------------------------------ 242
    B(242, stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition", "docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: imports
provider:
  name: onprem
  region: local
  options:
    port: 8242
functions: {}
""",
          "requirements.txt": ""}),
      user="""Lambda, S3 trigger on bucket `imports`, ObjectCreated only, suffix `.csv`:

```python
def handler(event, context):
    for rec in event["Records"]:
        key = urllib.parse.unquote_plus(rec["s3"]["object"]["key"])
        size = rec["s3"]["object"]["size"]
        print(f"new csv {key} {size}")
```

Same on our on-prem host, built-in bucket.""",
      steps=[
          S("get_project"),
          S("search_docs", query="S3 trigger translate storage event suffix",
            docs=[D("docs/migrating-from-aws.md", "step-2-translate-the-sam-serverless-cdk-definition",
                    start="| SAM `Events` |", end="| `Type: S3`")]),
          S("propose_plan", steps=["Write `app/imports.py`: loop event.records, use record.key and record.size",
                                   "Add `new-csv` with storage {bucket: imports, events: [created], suffix: .csv}",
                                   "Validate (onprem, staging), invoke with a sample record"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/imports.py", content=FUTURE + """

def new_csv(event, ctx):
    files = []
    for record in event.records:
        ctx.logger.info("new csv", extra={"key": record.key, "size": record.size})
        files.append({"key": record.key, "size": record.size})
    return {"files": files}
"""),
          S("set_config", path="functions.new-csv",
            value={"handler": "app.imports.new_csv",
                   "events": [{"storage": {"bucket": "imports", "events": ["created"], "suffix": ".csv"}}]}),
          S("invoke_local", function="new-csv", type="storage", data=[{"key": "2026/11/sales.csv", "size": 2048}]),
      ],
      final="""Ported:

```yaml
functions:
  new-csv:
    handler: app.imports.new_csv
    events:
      - storage: {bucket: imports, events: [created], suffix: .csv}
```

| Lambda | pskit |
|---|---|
| `rec["s3"]["object"]["key"]` + `unquote_plus` | `record.key` (already decoded) |
| `rec["s3"]["object"]["size"]` | `record.size` |
| `print(...)` | `ctx.logger.info(..., extra={...})` |

[docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition], [docs/handlers.md#record]

- validate (onprem, staging): valid.
- invoke with `2026/11/sales.csv`: `{"files": [{"key": "2026/11/sales.csv", "size": 2048}]}`.

On premises, `imports` is a folder on the host, and files already there at first start are not emitted. Upload after deploy: `PUT /__pskit/storage/imports/<key>`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 243
    B(243, stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response", "docs/resource-guides/onprem/services.md"],
      project=dict(files={
          "pskit.yml": """service: checkout
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8243
functions:
  pay:
    handler: app.checkout.pay
    events:
    - http: POST /pay
""",
          "app/__init__.py": "",
          "app/checkout.py": FUTURE + """

def pay(event, ctx):
    return {"paid": True}
""",
          "requirements.txt": ""}),
      user="We started Prometheus as a one-click service. I want a GET /metrics in the Prometheus text format with two counters: checkout_payments_total (incremented by pay) and checkout_payment_errors_total. No extra library please.",
      steps=[
          S("get_project"),
          S("search_docs", query="return text with custom content type",
            docs=[D("docs/handlers.md", "returning-a-response", words=170)]),
          S("propose_plan", steps=["Rewrite `app/checkout.py`: module-level counters, pay increments them, `metrics` returns the text format with Content-Type text/plain; version=0.0.4",
                                   "Add function `metrics` on GET /metrics",
                                   "Validate (onprem, prod), invoke /metrics"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/checkout.py", content=FUTURE + """from py_serverless_kit import Response

COUNTERS = {"checkout_payments_total": 0, "checkout_payment_errors_total": 0}


def pay(event, ctx):
    COUNTERS["checkout_payments_total"] += 1
    try:
        body = event.http.json(default={}) or {}
        return {"paid": True, "amount": body.get("amount")}
    except Exception:
        COUNTERS["checkout_payment_errors_total"] += 1
        raise


def metrics(event, ctx):
    lines = []
    for name, value in COUNTERS.items():
        lines += [f"# TYPE {name} counter", f"{name} {value}"]
    return Response(body="\\n".join(lines) + "\\n", status=200,
                    headers={"Content-Type": "text/plain; version=0.0.4"})
"""),
          S("set_config", path="functions.metrics",
            value={"handler": "app.checkout.metrics", "events": [{"http": "GET /metrics"}]}),
          S("invoke_local", function="metrics", method="GET", path="/metrics"),
      ],
      final="""Added `GET /metrics` with no extra library:

```text
# TYPE checkout_payments_total counter
checkout_payments_total 0
# TYPE checkout_payment_errors_total counter
checkout_payment_errors_total 0
```

`pay` counts every call, and every error it raises. `metrics` returns a `Response` with `Content-Type: text/plain; version=0.0.4` [docs/handlers.md#returning-a-response].

- `pskit validate` (onprem, prod): valid.
- Local `GET /metrics`: 200 with the text above.

Limits: the counters live in the host's memory. They reset on restart, and each server or replica counts on its own, so let Prometheus scrape every server. Add a scrape job for `http://<server>:8243/metrics` in your Prometheus config. Deploy: **Deploy** page or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 244
    B(244, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: newsletter
provider:
  name: onprem
  region: local
  options:
    port: 8244
functions: {}
""",
          "requirements.txt": ""}),
      user="our old html page has <form method=post action=/signup> with name and email fields. not json, normal form. make the /signup for it, email required",
      steps=[
          S("get_project"),
          S("search_docs", query="read form fields urlencoded body",
            docs=[D("docs/handlers.md", "httprequest", words=150)]),
          S("propose_plan", steps=["Write `app/signup.py`: event.http.form(), 400 without email, return a small thank-you page",
                                   "Add function `signup` on POST /signup",
                                   "Validate for onprem and test with a form body"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/signup.py", content=FUTURE + """import html

from py_serverless_kit import BadRequest, Response


def signup(event, ctx):
    form = event.http.form()
    email = form.get("email", "").strip()
    if not email:
        raise BadRequest("email is required")
    name = form.get("name", "").strip() or "friend"
    ctx.logger.info("signup", extra={"email": email})
    page = f"<html><body><p>Thanks, {html.escape(name)}! We will write to {html.escape(email)}.</p></body></html>"
    return Response(body=page, status=200, headers={"Content-Type": "text/html; charset=utf-8"})
"""),
          S("set_config", path="functions.signup",
            value={"handler": "app.signup.signup", "events": [{"http": "POST /signup"}]}),
          S("invoke_local", function="signup", method="POST", path="/signup", data="name=Ana&email=ana%40example.com"),
      ],
      final="""Done. `POST /signup` reads the normal form fields with `event.http.form()` [docs/handlers.md#httprequest]:

- no `email` -> 400 "email is required";
- otherwise a small HTML thank-you page. The name and email are escaped, so nobody can put HTML in it.

Checks:
- `pskit validate` (onprem): valid.
- Test with `name=Ana&email=ana%40example.com`: 200, page "Thanks, Ana! We will write to ana@example.com."

Your page keeps `<form method="post" action="/signup">`. If the page is not served from the same host and port, use the full URL `http://<server>:8244/signup` in `action`. Test again: `pskit invoke -f signup --method POST --path /signup -d '"name=Ana&email=ana%40example.com"'`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 245
    B(245, stage="prod", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: notify-js
provider:
  name: onprem
  region: local
  runtime: nodejs20
  options:
    host: 0.0.0.0
    port: 8245
functions:
  ping:
    handler: src.ping.ping
    events:
    - http: GET /ping
""",
          "src/ping.js": "exports.ping = async () => ({ pong: true });\n",
          "package.json": json.dumps({"name": "notify-js", "version": "1.0.0", "private": True}, indent=2) + "\n",
          ".pskit/onprem-servers.json": SERVERS}),
      user="prod -> saved server app-1, /opt/pskit/notify. box has neither node nor python. ship both",
      steps=[
          S("get_project"),
          S("search_docs", query="node bundle server without node python bundle",
            docs=[D("docs/providers.md", "onprem-on-premises", start="**Node.js / TypeScript services**", end="host_python: python3.12")]),
          S("propose_plan", steps=["provider.options.deploy: {server: app-1, path: /opt/pskit/notify, python: bundle, node: bundle}",
                                   "Validate (onprem, prod), invoke ping"]),
          S("set_config", path="provider.options.deploy",
            value={"server": "app-1", "path": "/opt/pskit/notify", "python": "bundle", "node": "bundle"}),
          S("invoke_local", function="ping", method="GET", path="/ping"),
      ],
      final="""Set:

```yaml
provider:
  options:
    deploy:
      server: app-1
      path: /opt/pskit/notify
      python: bundle     # portable CPython for the host process
      node: bundle       # official Node.js build for target_os/arch, only bin/node
```

The host process is Python even for a Node.js service, so the server needs both. With `bundle`, both are downloaded at apply and copied with the release [docs/providers.md#onprem-on-premises].

- validate (onprem, prod): valid.
- local `GET /ping`: 200 `{"pong": true}`.

The first deploy needs internet on this machine (downloads are cached under `~/.cache/pskit`). Deploy: `pskit deploy -s prod` (typed confirmation on the **Deploy** page)."""),

    # ------------------------------------------------------------------ 246
    B(246, stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=hello_project("vault-gw", 8246, files={".pskit/onprem-servers.json": SERVERS}),
      user="Prod goes to saved server app-2 under /opt/pskit/vault-gw. Neither app-2 nor this build machine may download from the internet. Our internal mirror has the python-build-standalone archive at https://mirror.example.com/python/cpython-3.12.7-x86_64-unknown-linux-gnu-install_only.tar.gz with sha256 4f3c2a1b0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b. Use that, and install it as a systemd service.",
      steps=[
          S("get_project"),
          S("search_docs", query="air-gapped python bundle mirror python_url sha256",
            docs=[D("docs/providers.md", "onprem-on-premises", start="When the server has **no Python**", end="Air-gapped:")]),
          S("propose_plan", steps=["provider.options.deploy: {server: app-2, path: /opt/pskit/vault-gw, python: bundle, python_url, python_sha256, install: systemd, sudo: true}",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy",
            value={"server": "app-2", "path": "/opt/pskit/vault-gw", "python": "bundle",
                   "python_url": "https://mirror.example.com/python/cpython-3.12.7-x86_64-unknown-linux-gnu-install_only.tar.gz",
                   "python_sha256": "4f3c2a1b0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b",
                   "install": "systemd", "sudo": True}),
          S("invoke_local", function="api", method="GET", path="/"),
      ],
      final="""Done:

```yaml
provider:
  options:
    deploy:
      server: app-2
      path: /opt/pskit/vault-gw
      python: bundle
      python_url: https://mirror.example.com/python/cpython-3.12.7-x86_64-unknown-linux-gnu-install_only.tar.gz
      python_sha256: 4f3c2a1b0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b
      install: systemd
      sudo: true
```

`python_url` + `python_sha256` is the air-gapped way to get the portable CPython: it comes from your mirror instead of GitHub [docs/providers.md#onprem-on-premises]. `install: systemd` with `sudo: true` writes the unit to `/etc/systemd/system`. The sudo must not ask for a password (`sudo -n`).

- `pskit validate` (onprem, prod): valid.
- Local `GET /`: 200 `{"service": "vault-gw", "stage": "prod"}`.

One more offline need: Python packages from `requirements.txt` come from PyPI while packaging. Point pip at your mirror with `package.pip_args` (for example `[--index-url, https://mirror.example.com/pypi/simple]`). This project has no requirements yet. Deploy: `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 247
    B(247, stage="prod", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/configuration.md#providers-per-cloud-overrides", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: orders
provider:
  name: aws
  region: eu-west-1
  state:
    backend: s3
    config: {bucket: acme-tf-state, key: orders.tfstate, region: eu-west-1}
  terraform:
    extra:
      resource:
        aws_dynamodb_table:
          orders: {name: orders, billing_mode: PAY_PER_REQUEST, hash_key: id, attribute: [{name: id, type: S}]}
functions:
  api:
    handler: app.orders.api
    environment: {TABLE: orders}
    events:
    - http: GET /orders
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def api(event, ctx):
    return {"orders": [], "provider": ctx.provider}
""",
          "requirements.txt": ""}),
      user="This project runs on AWS today. Keep it like that, but also make it deployable to our own server with -p onprem (port 8247, LAN). State for onprem must stay local, not in the S3 bucket.",
      steps=[
          S("get_project"),
          S("validate", provider="onprem"),
          S("search_docs", query="providers override block per cloud",
            docs=[D("docs/configuration.md", "providers-per-cloud-overrides", end="may be written directly as shorthand for `provider: {...}`.")]),
          S("propose_plan", steps=["Add `providers.onprem`: region local, state.backend empty, options {host: 0.0.0.0, port: 8247}",
                                   "Validate with -p onprem and -p aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.onprem",
            value={"region": "local", "state": {"backend": ""}, "options": {"host": "0.0.0.0", "port": 8247}}),
          S("validate", provider="aws"),
          S("invoke_local", function="api", method="GET", path="/orders"),
      ],
      final="""Added an on-prem block. AWS stays the default:

```yaml
providers:
  onprem:
    region: local
    state: {backend: ""}          # local state for onprem only
    options: {host: 0.0.0.0, port: 8247}
```

The block is merged only when the active provider is onprem [docs/configuration.md#providers-per-cloud-overrides].

Checks:
- `-p onprem`: valid. The state-backend warning is gone. One warning stays: the `aws_dynamodb_table` in `terraform.extra` is left out on premises [docs/providers.md#onprem-on-premises].
- `-p aws`: valid, unchanged.
- Local `GET /orders`: 200.

About that warning: on-prem, `api` gets no DynamoDB table. If the code uses DynamoDB, it either keeps calling AWS (with credentials on the server), or you give on-prem a database resource under `providers.onprem`.

Deploy: `pskit deploy -p onprem -s prod`. Plain `pskit deploy -s prod` still goes to AWS."""),

    # ------------------------------------------------------------------ 248
    B(248, stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#hooks"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: onprem
  region: local
  options:
    port: 8248
functions:
  api:
    handler: app.api.api
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def api(event, ctx):
    return {"shop": "open"}
""",
          "tests/test_api.py": "from app.api import api\n\n\ndef test_api():\n    assert api(None, None) == {\"shop\": \"open\"}\n",
          "requirements.txt": ""}),
      user="sometimes i deploy and forget to run the tests. can pskit run pytest first and stop the deploy when a test fails?",
      steps=[
          S("get_project"),
          S("search_docs", query="run command before deploy hook",
            docs=[D("docs/configuration.md", "hooks")]),
          S("propose_plan", steps=["Add `hooks.before_deploy: [python -m pytest -q]`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="hooks", value={"before_deploy": ["python -m pytest -q"]}),
      ],
      final="""Yes, with a hook:

```yaml
hooks:
  before_deploy: ["python -m pytest -q"]
```

pskit runs the command in the project folder before every `pskit deploy`. If a test fails, pytest exits with an error and the deploy stops [docs/configuration.md#hooks].

`pskit validate` (onprem): valid.

The hook runs on your machine, with the Python that is first on your PATH, so pytest must be installed there (`pip install pytest`). Your `tests/` folder is not copied to the server, because pskit always leaves `tests/**` out of the bundle. Try it: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 249
    B(249, stage="staging", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#package"],
      project=hello_project("ml-api", 8249, files={"data/sample.csv": "a,b\n1,2\n", "notebooks/explore.ipynb": "{}\n"}),
      user="bundle is huge. dont ship data/ and notebooks/",
      steps=[
          S("get_project"),
          S("search_docs", query="package exclude globs", docs=[D("docs/configuration.md", "package", words=200)]),
          S("propose_plan", steps=["package.exclude: [data/**, notebooks/**]", "Validate (onprem, staging), invoke api"]),
          S("set_config", path="package", value={"exclude": ["data/**", "notebooks/**"]}),
          S("invoke_local", function="api", method="GET", path="/"),
      ],
      final="""Done:

```yaml
package:
  exclude: [data/**, notebooks/**]
```

These globs are added to the default excludes (`.git`, `.venv`, `tests/**`, `.env*`, `node_modules/**`, ...) [docs/configuration.md#package].

- validate (onprem, staging): valid.
- `GET /`: 200, the handler doesn't need those folders.

Check the size with `pskit package -s staging` (it builds the bundle, deploys nothing). Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 250
    B(250, stage="prod", mode="ask", page="Setup", persona="pasted_error",
      sources=["docs/resources.md#on-premises-drivers", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: payments
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8250
    env_file: .env.onprem
functions:
  charge:
    handler: app.pay.charge
    events:
    - http: POST /charge
""",
          "app/__init__.py": "",
          "app/pay.py": FUTURE + """

def charge(event, ctx):
    return {"configured": bool(ctx.env.get("PSP_API_KEY"))}
""",
          "requirements.txt": ""}),
      user="""validate:

  WARNING: [provider.options.env_file] options.env_file .env.onprem does not exist yet; the host starts without it

create that file for me with the names we need (PSP_API_KEY, PSP_WEBHOOK_SECRET) but no values, I fill them in. and make sure it doesn't end up in git""",
      steps=[
          S("get_validation"),
          S("search_docs", query="env_file host.env secrets",
            docs=[D("docs/resources.md", "on-premises-drivers", start="**Secrets.**", end="**Secrets.**")]),
          S("propose_plan", steps=["Write `.env.onprem` with PSP_API_KEY and PSP_WEBHOOK_SECRET as <fill in> placeholders",
                                   "Write `.gitignore` with .env.onprem", "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path=".env.onprem", content="# filled in by hand on this machine, never committed\nPSP_API_KEY=<fill in>\nPSP_WEBHOOK_SECRET=<fill in>\n"),
          S("write_file", path=".gitignore", content=".env.onprem\n"),
          S("validate"),
          S("invoke_local", function="charge", method="POST", path="/charge"),
      ],
      final="""Done:

- `.env.onprem` lists `PSP_API_KEY` and `PSP_WEBHOOK_SECRET` with the placeholder `<fill in>`. Replace both in an editor; don't paste the real values here.
- `.gitignore` now ignores `.env.onprem`.

`pskit validate` (onprem, prod): valid. The warning is gone because the file exists.

How it works: on deploy, the file is copied next to the host as `host.env` and loaded when the host starts. Only its digest is recorded, so the values never reach Terraform state [docs/resources.md#on-premises-drivers]. Handlers read them with `ctx.env["PSP_API_KEY"]`.

Local test of `POST /charge`: `{"configured": false}`. Local runs don't load `.env.onprem`, only the deployed host does. The file is also never put in the code bundle, because `.env.*` is always excluded. Deploy after filling it in: **Deploy** page or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 251
    B(251, stage="prod", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=hello_project("scale-reader", 8251),
      user="our weighing scale software only runs on windows server 192.0.2.80 (user Administrator, ssh works). can pskit run there too? no python on it",
      steps=[
          S("get_project"),
          S("search_docs", query="deploy windows server ssh target_os python bundle",
            docs=[D("docs/providers.md", "onprem-on-premises", start="- **Dependencies:**", end="- **Dependencies:**"), D("docs/providers.md", "onprem-on-premises", start="When the server has **no Python**", end="Air-gapped:")]),
          S("propose_plan", steps=["provider.options.deploy: {method: ssh, host: 192.0.2.80, user: Administrator, path: C:/pskit/scale-reader, target_os: windows, python: bundle, install: process}",
                                   "Validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy",
            value={"method": "ssh", "host": "192.0.2.80", "user": "Administrator", "path": "C:/pskit/scale-reader",
                   "target_os": "windows", "python": "bundle", "install": "process"}),
      ],
      final="""Yes. I set an SSH deploy for Windows:

```yaml
provider:
  options:
    deploy:
      method: ssh
      host: 192.0.2.80
      user: Administrator
      path: C:/pskit/scale-reader
      target_os: windows     # Windows wheels and a Windows Python
      python: bundle         # portable CPython is copied, no install needed
      install: process       # systemd is Linux only
```

[docs/providers.md#onprem-on-premises]

`pskit validate` (onprem, prod): valid.

Before deploy:
- SSH uses your SSH agent or default key. Add `pem:` if you log in with a key file.
- Open port 8251 in the Windows firewall for the machines that call it (`host: 0.0.0.0` is already set).

`install: process` starts the host as a normal process, not as a Windows service, so start it again after a reboot with `pskit deploy -s prod`. Deploy: **Deploy** page or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 252
    B(252, stage="staging", mode="ask", page="Deploy", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=hello_project("badges", 8252),
      user="staging as container on the docker daemon at tcp://192.0.2.70:2376 (no ssh on that box). image pskit/badges:staging",
      steps=[
          S("get_project"),
          S("search_docs", query="docker_host tcp daemon without ssh",
            docs=[D("docs/providers.md", "onprem-on-premises", start="- **Credentials:**", end="- **Dependencies:**")]),
          S("propose_plan", steps=["provider.options.deploy: {method: docker, docker_host: tcp://192.0.2.70:2376, image: pskit/badges:staging}",
                                   "Validate (onprem, staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy",
            value={"method": "docker", "docker_host": "tcp://192.0.2.70:2376", "image": "pskit/badges:staging"}),
      ],
      final="""Set:

```yaml
provider:
  options:
    deploy:
      method: docker
      docker_host: tcp://192.0.2.70:2376
      image: pskit/badges:staging
```

With `docker_host: tcp://...`, pskit talks to that daemon directly, without SSH and without a `.pem` [docs/providers.md#onprem-on-premises]. `host: 0.0.0.0` is already set, so the container port answers from outside.

validate (onprem, staging): valid.

Needs: a Docker CLI on this machine that can reach port 2376 of 192.0.2.70. Use TLS on that port, because an open Docker API gives full control of the box. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 253
    B(253, stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=hello_project("reports", 8253, files={".pskit/onprem-servers.json": SERVERS}),
      user="Prod should run as a Docker container on saved server app-3, image pskit/reports:prod, restart unless-stopped. Our ops team manages Docker on that box themselves: pskit must never install Docker there; if it is missing, the deploy should fail instead.",
      steps=[
          S("get_project"),
          S("search_docs", query="docker deploy install_docker false",
            docs=[D("docs/providers.md", "onprem-on-premises", start="Set `install_docker: false`", end="Set `install_docker: false`")]),
          S("propose_plan", steps=["provider.options.deploy: {server: app-3, method: docker, image: pskit/reports:prod, restart: unless-stopped, install_docker: false}",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy",
            value={"server": "app-3", "method": "docker", "image": "pskit/reports:prod", "restart": "unless-stopped",
                   "install_docker": False}),
      ],
      final="""Set:

```yaml
provider:
  options:
    deploy:
      server: app-3
      method: docker
      image: pskit/reports:prod
      restart: unless-stopped
      install_docker: false     # refuse a server without Docker
```

The default (`install_docker: true`) installs Docker when it is missing. `false` makes the deploy refuse the server instead [docs/providers.md#onprem-on-premises]. The image is built on this machine and copied over SSH, so app-3 needs no registry.

`pskit validate` (onprem, prod): valid.

The SSH user still needs access to the Docker daemon (or passwordless `sudo`). Check app-3 first with `pskit resources onprem servers test app-3` (it shows `docker_access`). Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 254
    B(254, stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/resources.md#runtime-api", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: clinic
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8254
resources:
  clinic-db:
    type: database
    external: true
    connection: {host: db-1.example.com, port: 5432, database: clinic, password_env: CLINIC_DB_PASSWORD}
functions:
  patients:
    handler: app.clinic.patients
    events:
    - http: GET /patients
""",
          "app/__init__.py": "",
          "app/clinic.py": FUTURE + """

def patients(event, ctx):
    return {"patients": []}
""",
          "requirements.txt": ""}),
      user="our uptime monitor only checks if the page answers. can i have a /health that also says if the database can be reached, and gives an error status if not?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/health.py`: open a TCP connection to clinic-db host:port (2 s timeout); 200 if it works, 503 if not",
                                   "Add function `health` on GET /health (gets the clinic-db binding)",
                                   "Validate for onprem (prod) and call /health"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/health.py", content=FUTURE + """import socket

from py_serverless_kit import resource


def health(event, ctx):
    db = resource("clinic-db")
    try:
        with socket.create_connection((db["host"], int(db["port"])), timeout=2):
            pass
    except OSError as exc:
        ctx.logger.warning("database unreachable", extra={"error": str(exc)})
        return {"status": "degraded", "database": "unreachable"}, 503
    return {"status": "ok", "database": "reachable"}
"""),
          S("set_config", path="functions.health",
            value={"handler": "app.health.health", "events": [{"http": "GET /health"}]}),
          S("invoke_local", function="health", method="GET", path="/health"),
      ],
      final="""Done. `GET /health` tries to reach the database (host and port from `resource("clinic-db")` [docs/resources.md#runtime-api]):

- reachable: **200** `{"status": "ok", "database": "reachable"}`
- not reachable within 2 s: **503** `{"status": "degraded", "database": "unreachable"}`. Monitors treat that as down [docs/handlers.md#returning-a-response].

Checks:
- `pskit validate` (onprem, prod): valid.
- Called here: **503**. `db-1.example.com` can't be reached from this computer, so this was the error case. On the server it should give 200.

It checks that the database port answers. It does not log in. Point your monitor at `http://<server>:8254/health`. Deploy: **Deploy** page (prod asks you to type a confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 255
    B(255, stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#batchresult", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: crm
provider:
  name: onprem
  region: local
  options:
    port: 8255
functions:
  sync-contact:
    handler: app.crm.sync_contact
    events:
    - queue: {name: contacts, batch_size: 10}
""",
          "app/__init__.py": "",
          "app/crm.py": FUTURE + """

def sync_contact(event, ctx):
    for record in event.records:
        contact = record.json(default={}) or {}
        if "customer_id" not in contact:
            ctx.logger.warning("record without customer_id")
            continue
        ctx.logger.info("synced", extra={"customer_id": contact["customer_id"]})
    return None
""",
          "requirements.txt": ""}),
      user="""pskit logs --function sync-contact shows a lot of

  WARNING  sync-contact  record without customer_id

these messages are just lost. retry them 3 times and then park them in a queue contacts-dlq so we can look at them later""",
      steps=[
          S("read_file", path="app/crm.py"),
          S("propose_plan", steps=["Return a BatchResult and fail() the records without customer_id instead of skipping them",
                                   "Queue event: max_receive 3, dead_letter contacts-dlq",
                                   "Validate (onprem, staging), invoke with a good and a bad record"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/crm.py", content=FUTURE + """from py_serverless_kit import BatchResult


def sync_contact(event, ctx):
    result = BatchResult()
    for record in event.records:
        contact = record.json(default={}) or {}
        if "customer_id" not in contact:
            ctx.logger.warning("record without customer_id", extra={"record_id": record.id})
            result.fail(record)
            continue
        ctx.logger.info("synced", extra={"customer_id": contact["customer_id"]})
    return result
"""),
          S("set_config", path="functions.sync-contact.events",
            value=[{"queue": {"name": "contacts", "batch_size": 10, "max_receive": 3, "dead_letter": "contacts-dlq"}}]),
          S("invoke_local", function="sync-contact", type="queue", data=[{"customer_id": "C-1"}, {"email": "x@example.com"}]),
      ],
      final="""Done. Those records were dropped because the handler only logged them and returned normally. Now it marks them failed:

- `sync_contact` returns a `BatchResult` and calls `result.fail(record)` for records without `customer_id`. The good records in the same batch still count as done [docs/handlers.md#batchresult].
- `- queue: {name: contacts, batch_size: 10, max_receive: 3, dead_letter: contacts-dlq}`: after 3 tries, a failed message moves to `contacts-dlq`.

Checks:
- validate (onprem, staging): valid.
- invoke with one good and one bad record: only the bad one is in `batchItemFailures`.

After deploy, look at parked messages on **Resources > Data** or with `GET /__pskit/queues/contacts-dlq` (depth). Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 256
    B(256, stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resource-guides/onprem/services.md", "docs/resources.md#custom-drivers"],
      project=dict(files={
          "pskit.yml": """service: telemetry
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8256
resources:
  events:
    type: queue
    external: true
    options:
      driver: custom
      class: pskit_drivers.kafka_queue:KafkaQueue
      bootstrap_servers: 192.0.2.11:9092
      topic: events
      group_id: telemetry-events
functions: {}
""",
          "pskit_drivers/__init__.py": "",
          "pskit_drivers/kafka_queue.py": "# Kafka queue driver (copied by pskit resources onprem create)\n",
          "requirements.txt": "kafka-python\n"}),
      user="The Kafka (Redpanda) one-click service `events` is in pskit.yml now. Add a consumer `store-event` that takes up to 50 messages per call and logs the device id and the metric of each. If a message is not JSON, fail only that one.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/telemetry.py`: BatchResult; record.json() per message, fail on BadRequest (not JSON)",
                                   "Add `store-event` with queue {resource: events, batch_size: 50}",
                                   "Validate (onprem, prod), invoke with one JSON and one broken message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/telemetry.py", content=FUTURE + """from py_serverless_kit import BadRequest, BatchResult


def store_event(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            msg = record.json()
        except BadRequest:
            ctx.logger.warning("not json", extra={"record_id": record.id})
            result.fail(record)
            continue
        ctx.logger.info("event", extra={"device": msg.get("device_id"), "metric": msg.get("metric")})
    return result
"""),
          S("set_config", path="functions.store-event",
            value={"handler": "app.telemetry.store_event", "events": [{"queue": {"resource": "events", "batch_size": 50}}]}),
          S("invoke_local", function="store-event", type="queue",
            data=[{"device_id": "d-17", "metric": "temp", "value": 21.5}, "not json {"]),
      ],
      final="""Added `store-event` on the Kafka resource:

```yaml
functions:
  store-event:
    handler: app.telemetry.store_event
    events:
      - queue: {resource: events, batch_size: 50}
```

Each message is parsed with `record.json()`, which raises `BadRequest` for a body that isn't JSON. That message is logged and failed on its own with `BatchResult`, and the rest of the batch is settled normally. The `custom` driver class (`pskit_drivers.kafka_queue:KafkaQueue`, consumer group `telemetry-events`) does the leasing [docs/resources.md#custom-drivers].

- `pskit validate` (onprem, prod): valid.
- invoke with one good and one broken message: only the broken one is in `batchItemFailures`.

Redpanda runs without authentication in this setup, so keep port 9092 on a private network [docs/resource-guides/onprem/services.md]. Deploy: **Deploy** page or `pskit deploy -s prod`. Test with **Resources > Test** or `pskit resources send events`."""),

    # ------------------------------------------------------------------ 257
    B(257, stage="dev", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#queue-drivers", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: billing
provider:
  name: onprem
  region: local
  options:
    port: 8257
resources:
  invoices:
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/invoices
      access_key_env: AWS_ACCESS_KEY_ID_INVOICES
      secret_key_env: AWS_SECRET_ACCESS_KEY_INVOICES
functions:
  bill:
    handler: app.billing.bill
    events:
    - queue: {resource: invoices, batch_size: 10}
""",
          "app/__init__.py": "",
          "app/billing.py": FUTURE + """

def bill(event, ctx):
    return {"billed": len(event.records)}
""",
          "requirements.txt": ""}),
      user="Prod and staging consume the real SQS queue in AWS, that stays. But in dev I don't want to touch AWS at all: use the LocalStack one-click service on this laptop (http://127.0.0.1:4566), queue `invoices`, test keys.",
      steps=[
          S("get_project"),
          S("search_docs", query="sqs driver endpoint localstack create_queue",
            docs=[D("docs/resources.md", "queue-drivers", start="| `sqs` |", end="| `sqs` |")]),
          S("propose_plan", steps=["Add `stages.dev.resources.invoices.options`: endpoint http://127.0.0.1:4566, queue_url http://127.0.0.1:4566/000000000000/invoices, region eu-west-1, keys from LOCALSTACK_ACCESS_KEY / LOCALSTACK_SECRET_KEY",
                                   "Validate for onprem in dev"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.dev.resources.invoices.options",
            value={"endpoint": "http://127.0.0.1:4566", "queue_url": "http://127.0.0.1:4566/000000000000/invoices",
                   "region": "eu-west-1", "access_key_env": "LOCALSTACK_ACCESS_KEY", "secret_key_env": "LOCALSTACK_SECRET_KEY"}),
          S("invoke_local", function="bill", type="queue", data=[{"invoice": "INV-1"}]),
      ],
      final="""Done. Only stage `dev` is changed:

```yaml
stages:
  dev:
    resources:
      invoices:
        options:
          endpoint: http://127.0.0.1:4566
          queue_url: http://127.0.0.1:4566/000000000000/invoices
          region: eu-west-1
          access_key_env: LOCALSTACK_ACCESS_KEY
          secret_key_env: LOCALSTACK_SECRET_KEY
```

The `sqs` driver accepts an `endpoint`. Since `127.0.0.1` is not an `amazonaws.com` host, `create_queue` defaults to `true`, so the queue is created in LocalStack on first use [docs/resources.md#queue-drivers]. Staging and prod keep the real queue URL and the `*_env` keys [docs/configuration.md#stages-per-stage-overrides]. LocalStack accepts any keys, so export both variables with its dummy value `test` before you start the dev host.

- `pskit validate` (onprem, dev): valid.
- invoke with one invoice: `{"billed": 1}`.

Deploy dev locally: **Deploy** page or `pskit deploy -s dev`. Send a test message with `pskit resources send invoices`."""),

    # ------------------------------------------------------------------ 258
    B(258, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule", "docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: printers
provider:
  name: onprem
  region: local
  options:
    port: 8258
functions: {}
""",
          "requirements.txt": ""}),
      user="new small project: we have 3 network printers (printer-1.example.com, printer-2..., printer-3...). every 5 minutes check if they answer on port 9100, and a page /printers that shows the last result",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/printers.py`: `check` tries TCP 9100 on each printer and keeps the result in memory; `status` returns it",
                                   "Add `check-printers` (schedule 5 minutes, PRINTERS env list) and `printers` (GET /printers)",
                                   "Validate for onprem, run the check once and call /printers"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/printers.py", content=FUTURE + """import socket
import time

LAST = {"checked_at": None, "printers": {}}


def check(event, ctx):
    names = [p.strip() for p in ctx.env.get("PRINTERS", "").split(",") if p.strip()]
    status = {}
    for name in names:
        try:
            with socket.create_connection((name, 9100), timeout=2):
                status[name] = "online"
        except OSError:
            status[name] = "offline"
    LAST["checked_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    LAST["printers"] = status
    ctx.logger.info("printers checked", extra=status)
    return LAST


def status(event, ctx):
    return LAST
"""),
          S("set_config", path="functions.check-printers",
            value={"handler": "app.printers.check",
                   "environment": {"PRINTERS": "printer-1.example.com,printer-2.example.com,printer-3.example.com"},
                   "events": [{"schedule": "5 minutes"}]}),
          S("set_config", path="functions.printers",
            value={"handler": "app.printers.status", "events": [{"http": "GET /printers"}]}),
          S("invoke_local", function="check-printers", type="schedule"),
      ],
      final="""Done. Two functions:

- `check-printers` runs every 5 minutes and tries port 9100 on each printer in `PRINTERS` (2 s each).
- `printers` on `GET /printers` shows the last result: `checked_at` and `online`/`offline` per printer.

Checks:
- `pskit validate` (onprem): valid.
- One check from this computer: all three `offline`. The example names can't be reached from here; on the office network the real printers will answer.

Both functions run in the same host, so `/printers` sees the last check. The result is kept in memory: after a restart it is empty until the next check, at most 5 minutes later. To add a printer, edit `PRINTERS` on **Functions > check-printers > Environment variables**. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 259
    B(259, stage="staging", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      project=dict(files={
          "pskit.yml": """service: quotes
provider:
  name: onprem
  region: local
  options:
    port: 8259
functions:
  tax:
    handler: app.quotes.tax
""",
          "app/__init__.py": "",
          "app/quotes.py": FUTURE + """

def tax(event, ctx):
    amount = float((event.data or {}).get("amount", 0))
    return {"tax": round(amount * 0.2, 2)}
""",
          "requirements.txt": ""}),
      user="i need POST /quote {amount} that give amount + tax, but tax must come from tax function (it change often), not copy",
      steps=[
          S("get_project"),
          S("search_docs", query="call another function invoke",
            docs=[D("docs/handlers.md", "invoke-calling-another-function", words=160)]),
          S("propose_plan", steps=["Add `quote` in app/quotes.py: BadRequest without amount, invoke('tax', {amount}), return amount, tax, total",
                                   "Add function `quote` on POST /quote", "Validate, invoke"]),
          S("write_file", path="app/quotes.py", content=FUTURE + """from py_serverless_kit import BadRequest, invoke


def tax(event, ctx):
    amount = float((event.data or {}).get("amount", 0))
    return {"tax": round(amount * 0.2, 2)}


def quote(event, ctx):
    body = event.http.json(default={}) or {}
    if "amount" not in body:
        raise BadRequest("amount is required")
    amount = float(body["amount"])
    tax_part = invoke("tax", {"amount": amount})["tax"]
    return {"amount": amount, "tax": tax_part, "total": round(amount + tax_part, 2)}
"""),
          S("set_config", path="functions.quote",
            value={"handler": "app.quotes.quote", "events": [{"http": "POST /quote"}]}),
          S("invoke_local", function="quote", method="POST", path="/quote", data={"amount": 50}),
      ],
      final="""Done. `quote` calls `tax` with `invoke("tax", {"amount": ...})`, so the tax logic stays in one place [docs/handlers.md#invoke-calling-another-function].

- validate (onprem, staging): valid.
- `POST /quote {"amount": 50}`: 200 `{"amount": 50.0, "tax": 10.0, "total": 60.0}`.

When the tax rule changes, edit only `tax`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 260
    B(260, stage="prod", mode="ask", page="Network map", persona="terse_expert",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it", "docs/onprem-network.md"],
      project=dict(files={
          "pskit.yml": """service: wiki
provider:
  name: onprem
  region: local
  options:
    port: 8260
    deploy:
      server: app-2
      path: /opt/pskit/wiki
      python: bundle
functions:
  page:
    handler: app.wiki.page
    events:
    - http: GET /pages/{slug}
""",
          "app/__init__.py": "",
          "app/wiki.py": FUTURE + """

def page(event, ctx):
    return {"slug": event.http.path_params["slug"]}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="put wiki behind lb `edge` at /wiki. lb must reach app-2 at 192.0.2.11:8260",
      steps=[
          S("get_project"),
          S("search_docs", query="project balancer advertise host 0.0.0.0",
            docs=[D("docs/load-balancers.md", "create-one-and-put-projects-on-it", start="The path prefix is removed", end="sent in `X-Forwarded-Prefix: /shop`."), D("docs/load-balancers.md", "notes", start="* The load balancer server must reach", end="set `host: 0.0.0.0` and `advertise`.")]),
          S("propose_plan", steps=["options.host: 0.0.0.0, advertise: http://192.0.2.11:8260",
                                   "options.balancer: {name: edge, path: wiki}", "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
          S("set_config", path="provider.options.advertise", value="http://192.0.2.11:8260"),
          S("set_config", path="provider.options.balancer", value={"name": "edge", "path": "wiki"}),
      ],
      final="""Set:

```yaml
provider:
  options:
    host: 0.0.0.0
    advertise: http://192.0.2.11:8260
    balancer: {name: edge, path: wiki}
```

`host: 0.0.0.0` lets the load balancer connect, and `advertise` is the address it calls. `/wiki/pages/x` arrives at the function as `/pages/x`, with `X-Forwarded-Prefix: /wiki` [docs/load-balancers.md#create-one-and-put-projects-on-it].

validate (onprem, prod): valid.

Firewall: the edge server must reach app-2 on TCP 8260. The **Network map** page draws it, and `pskit firewall --server app-2` prints the rule. Deploy updates the route: `pskit deploy -s prod`. Then check with `pskit lb status edge`."""),
]
