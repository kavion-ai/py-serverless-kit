"""Category A (docs Q&A and how-to), batch 27: aws / gcp / azure. Handler details (async, logging, forms),
schedule input / pause / timezone, HTTP paths, 405 and duplicate routes, storage filters, visibility timeout,
tags, extends files, deployed names, plan --destroy, trigger --list, Setup page (AWS profile, .venv), kept
resources, provider plugin upgrades. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(511, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#handler-signatures"],
      user="Lambda's Python runtime doesn't await coroutines, so we always wrapped async code in asyncio.run(). Can a pskit handler just be async def?",
      steps=[S("search_docs", query="async handler coroutine awaited",
               docs=[D("docs/handlers.md", "handler-signatures")])],
      final="""Yes. pskit awaits coroutine handlers for you, on every cloud and locally [docs/handlers.md#handler-signatures].

**In code**
```python
from __future__ import annotations

import asyncio


async def handler(event, ctx):
    a, b = await asyncio.gather(fetch_prices(), fetch_stock())
    return {"prices": a, "stock": b}
```
`fetch_prices` and `fetch_stock` are your own coroutines. The `handler:` line in pskit.yml stays the same (`app.module.handler`).

**In the terminal**
```bash
pskit invoke -f handler-name
```"""),

    A(512, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#logging", "docs/handlers.md#environment-variables"],
      user="We want searchable logs in Cloud Logging: each order log line should carry order_id and amount as fields, and the worker function should log at DEBUG while the others stay at INFO. How?",
      steps=[S("search_docs", query="structured logging extra fields",
               docs=[D("docs/handlers.md", "logging", end="`extra` keys that collide")]),
             S("search_docs", query="log level environment variable",
               docs=[D("docs/handlers.md", "environment-variables", start="Runtime switches you can set:")])],
      final="""Use `ctx.logger` with `extra`: each call becomes one JSON object per line with your fields, which Cloud Logging can index [docs/handlers.md#logging]. The level comes from `PSKIT_LOG_LEVEL` (default `INFO`) [docs/handlers.md#environment-variables].

**In code**
```python
ctx.logger.info("order created", extra={"order_id": order["id"], "amount": order["amount"]})
```
```yaml
functions:
  worker:
    handler: app.worker.handle
    environment:
      PSKIT_LOG_LEVEL: DEBUG
```

**In studio**
1. Open **Functions** and click `worker`.
2. In the *Logging* section, set *Log level* to `DEBUG`.
3. Click **Save**.

The other functions keep the default `INFO`."""),

    A(513, provider="azure", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      user="my html page posts a normal form (not json) with name and email to my function. how i read the fields?",
      steps=[S("search_docs", query="read form urlencoded body",
               docs=[D("docs/handlers.md", "httprequest", start="| `content_type` |", end="| `form()` |")])],
      final="""Use `event.http.form()`. It parses `application/x-www-form-urlencoded` bodies [docs/handlers.md#httprequest].

**In code**
```python
from __future__ import annotations

from py_serverless_kit import BadRequest


def signup(event, ctx):
    fields = event.http.form()
    name, email = fields.get("name"), fields.get("email")
    if not email:
        raise BadRequest("email is required")
    return {"name": name, "email": email}
```
Check `event.http.content_type` first if the same route also accepts JSON (`event.http.json()`)."""),

    A(514, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      user="One report function should run hourly with {\"kind\": \"short\"} and daily at 6:00 with {\"kind\": \"full\"}. Can one function have two schedules with different payloads, and how does the handler tell them apart?",
      steps=[S("search_docs", query="schedule input event.data multiple schedules",
               docs=[D("docs/events.md", "schedule", end="The handler gets `event.type == \"schedule\"` and `event.data == input`.")])],
      final="""Yes. Give each schedule its own `input`; the handler gets it as `event.data` [docs/events.md#schedule].

**In code**
```yaml
functions:
  report:
    handler: app.report.run
    events:
      - schedule: {rate: 1 hour, input: {kind: short}, name: hourly}
      - schedule: {cron: "0 6 * * *", input: {kind: full}, name: daily}
```
```python
from __future__ import annotations


def run(event, ctx):
    kind = (event.data or {}).get("kind", "short")
    ctx.logger.info("report", extra={"kind": kind})
    return {"kind": kind}
```

**In the terminal**
```bash
pskit invoke -f report -t schedule -d '{"kind": "full"}'
```
Without `-d`, invoke uses the configured `input`."""),

    A(515, provider="gcp", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      user="how stop my nightly job in prod for some days but not delete the schedule?",
      steps=[S("search_docs", query="schedule enabled false pause",
               docs=[D("docs/events.md", "schedule", end="The handler gets `event.type == \"schedule\"` and `event.data == input`.")])],
      final="""Set `enabled: false` on the schedule and deploy. The schedule stays in the file, and you turn it back on later with `true` [docs/events.md#schedule].

**In code**
```yaml
stages:
  prod:
    functions:
      nightly:
        events:
          - schedule: {cron: "0 2 * * *", enabled: false}
```
Lists replace, so write the whole schedule here, as it is in the base file. Or set `enabled: false` directly on the schedule if it should stop on every stage.

**In studio**
1. Open **Functions** with stage `prod` in the top bar and click `nightly`.
2. On its schedule trigger, turn off *Enabled*.
3. Click **Save**.

**In the terminal**
```bash
pskit deploy -s prod
```"""),

    A(516, provider="azure", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#schedule", "docs/providers.md#azure-azure-functions"],
      user="WARNING: [functions.report] Linux Consumption timers run in UTC; timezone is ignored\n\nmy job must run 7:00 Berlin time",
      steps=[S("search_docs", query="azure timer timezone ignored UTC",
               docs=[D("docs/events.md", "schedule", start="| azure | timer trigger |", end="| azure | timer trigger |"),
                     D("docs/events.md", "schedule", start="A rate that can't be expressed")])],
      final="""Azure timers on Linux Consumption always run in UTC, so pskit ignores `timezone` there [docs/events.md#schedule]. Write the cron in UTC instead:

- Berlin winter time (UTC+1): 7:00 = 6:00 UTC → `"0 6 * * *"`
- Berlin summer time (UTC+2): 7:00 = 5:00 UTC → `"0 5 * * *"`

**In code**
```yaml
functions:
  report:
    handler: app.report.run
    events:
      - schedule: "0 6 * * *"
```
A fixed UTC cron is one hour off for half the year. If that matters, schedule it hourly and let the handler check the Berlin time with `zoneinfo` before doing the work. AWS and GCP honour `timezone`."""),

    A(517, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      user="one function for every method under /files/<anything/with/slashes>. path?",
      steps=[S("search_docs", query="greedy path parameter any method",
               docs=[D("docs/events.md", "http", end="Two functions may not declare the same `METHOD /path`.")])],
      final="""**In code**
```yaml
functions:
  files:
    handler: app.files.handle
    events:
      - http: {path: "/files/{path+}", method: ANY}
```
```python
def handle(event, ctx):
    key = event.http.path_params["path"]     # e.g. "reports/2026/q3.pdf"
    return {"method": event.http.method, "key": key}
```
`{name+}` matches the rest of the path and must be the last segment; `ANY` accepts every method [docs/events.md#http]. Note `/files` itself (no trailing part) is a different route."""),

    A(518, provider="gcp", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/troubleshooting.md#http"],
      user="my function answer 405 Method Not Allowed when i send PUT. GET works",
      steps=[S("search_docs", query="405 method not allowed",
               docs=[D("docs/troubleshooting.md", "http", start="**405 Method Not Allowed**", end="Use `method: ANY` to accept everything.")])],
      final="""The path matched a route, but not with that method: the route only allows `GET`. The `allow` header in the response lists the valid methods [docs/troubleshooting.md#http].

Add a `PUT` route (or use `ANY`):

**In code**
```yaml
functions:
  items:
    handler: app.items.handle
    events:
      - http: GET /items/{id}
      - http: PUT /items/{id}
```
In the handler, check `event.http.method` to tell them apart.

**In studio**
1. Open **Functions**, click the function and add an HTTP trigger with method `PUT` and the same path.
2. Click **Save**, then test it on **Test** with **▶ Run locally**.

pskit's runtime matches routes itself on GCP, so you get the same 405 locally and in the cloud."""),

    A(519, provider="azure", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/troubleshooting.md#configuration"],
      user="route GET /health is used by both 'api' and 'status'",
      steps=[S("search_docs", query="route used by both",
               docs=[D("docs/troubleshooting.md", "configuration", start="**`route GET /x is used by both 'a' and 'b'`**", end="(`/x` and `/x/` count as the same path).")])],
      final="""Each `METHOD /path` may belong to one function only, and `/health` and `/health/` count as the same path [docs/troubleshooting.md#configuration]. Both `api` and `status` declare `GET /health`.

Fix: keep the route on one function and remove it from the other (or give one a different path, such as `/status`).

**In studio**
1. Open **Functions**, click `status` (or `api`).
2. Remove the duplicate HTTP trigger and click **Save**. The problem leaves the Problems list.

**In the terminal**
```bash
pskit validate
```"""),

    A(520, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage"],
      user="On GCP our ingest function has a storage trigger with prefix incoming/ and suffix .csv on a busy bucket. Does the filter stop the function from being called for the other files, like S3 notifications do?",
      steps=[S("search_docs", query="storage prefix suffix gcp runtime filter",
               docs=[D("docs/events.md", "storage", start="| Provider | Service | Filters | Notes |", end="| azure | Blob trigger")])],
      final="""No. On GCP the Cloud Storage trigger (Eventarc) fires for every object in the bucket, and pskit's runtime applies `prefix` and `suffix`. Other files are dropped before your handler runs, but the function is still invoked for them. On AWS the S3 notification filters natively [docs/events.md#storage].

If that cost matters on a busy bucket, put the incoming files in a bucket of their own:
```yaml
functions:
  ingest:
    handler: app.ingest.handle
    events:
      - storage: {bucket: acme-incoming-csv, suffix: .csv}
```
Also note that on GCP `created` and `deleted` become separate deployments."""),

    A(521, provider="aws", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      user="sqs visibility_timeout default? worker timeout is 60",
      steps=[S("search_docs", query="queue visibility_timeout default aws",
               docs=[D("docs/events.md", "queue", end="| partial batch failure |")])],
      final="""On AWS the default is `max(30, 6 x function timeout)`, so with `timeout: 60` it's 360 s [docs/events.md#queue]. Set `visibility_timeout` on the queue event to override it:
```yaml
functions:
  worker:
    handler: app.worker.handle
    timeout: 60
    events:
      - queue: {name: jobs, visibility_timeout: 120}
```
Keep it above the function timeout, or a message can be delivered again while it's still being processed."""),

    A(522, provider="azure", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#provider", "docs/providers.md#providers"],
      user="Finance needs every Azure resource of our service tagged with cost-center=4711 and owner=payments. Can pskit tag them, and are there tags it adds itself?",
      steps=[S("search_docs", query="provider tags merged pskit-service",
               docs=[D("docs/configuration.md", "provider", start="| `tags` |", end="| `tags` |")]),
             S("search_docs", query="resources tagged pskit-service managed-by",
               docs=[D("docs/providers.md", "providers", start="- Resources are tagged", end="- Resources are tagged")])],
      final="""Yes. Set `provider.tags`; they're merged with the tags pskit adds itself: `pskit-service`, `pskit-stage` and `managed-by: py-serverless-kit` [docs/configuration.md#provider] [docs/providers.md#providers].

**In code**
```yaml
provider:
  name: azure
  tags:
    cost-center: "4711"
    owner: payments
```
Quote numbers so they stay strings. A function's own `tags` are merged over these.

**In studio**
1. Open **Overview & provider**.
2. Under *Tags*, click *Add tag* for each pair and click **Save**.

**In the terminal**
```bash
pskit plan -s prod
```
The plan shows the tag changes before you deploy."""),

    A(523, provider="gcp", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#extends-inherit-files", "docs/studio.md#saving-what-changes-in-pskityml"],
      user="I'd like pskit.yml to stay cloud-neutral and keep the GCP-specific settings (project, region, memory) in a separate file. How does that work with deploy and with the studio?",
      steps=[S("search_docs", query="extends separate file per cloud",
               docs=[D("docs/configuration.md", "extends-inherit-files")]),
             S("search_docs", query="studio extends notice main file",
               docs=[D("docs/studio.md", "saving-what-changes-in-pskityml", start="- A file that uses `extends:`", end="- A file that uses `extends:`")])],
      final="""Use a small `pskit.gcp.yml` that `extends` the base file. Relative paths resolve from the extending file [docs/configuration.md#extends-inherit-files].

**In code**
```yaml
# pskit.gcp.yml
extends: pskit.yml
provider:
  name: gcp
  region: europe-west1
  memory: 512
  options: {project: my-gcp-project}
```

**In the terminal**
```bash
pskit validate -c pskit.gcp.yml
pskit deploy -c pskit.gcp.yml
```

**In studio**
Studio shows a file that uses `extends:` with a notice, and only the main file is edited [docs/studio.md#saving-what-changes-in-pskityml]. Start it on the folder and edit the shared parts in `pskit.yml`; change the GCP file in **Code** or your editor."""),

    A(524, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      user="i deployed function create-order but i can't find it by that name in the lambda console. what name does it get?",
      steps=[S("search_docs", query="deployed function name service stage",
               docs=[D("docs/configuration.md", "functions", start="Event syntax is in", end="Deployed functions are named")])],
      final="""Deployed functions are named `<service>-<stage>-<function>`, in lower case, with invalid characters replaced and long names shortened with a stable hash [docs/configuration.md#functions]. With `service: shop` and stage `dev`, look for `shop-dev-create-order` in the region of your `provider.region`.

`pskit info` lists each function with its id and a console link."""),

    A(525, provider="azure", stage="staging", mode="ask", page="Deploy", persona="terse_expert",
      sources=["docs/cli.md#pskit-plan"],
      user="terminal only: preview what remove would delete on azure staging, without deleting",
      steps=[S("search_docs", query="plan destroy preview remove",
               docs=[D("docs/cli.md", "pskit-plan")])],
      final="""**In the terminal**
```bash
pskit plan -s staging --destroy
```
It packages, runs `terraform init` and plans a destroy, so you see every resource that `pskit remove` would delete. Nothing is changed [docs/cli.md#pskit-plan]."""),

    A(526, provider="gcp", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/cli.md#pskit-trigger"],
      user="before deploy i want see how i will test each trigger later on gcp, payload and gcloud command. possible?",
      steps=[S("search_docs", query="trigger list how to test each trigger",
               docs=[D("docs/cli.md", "pskit-trigger", end="| `--json` | JSON output |", words=320)])],
      final="""Yes. `pskit trigger --list` works before deploying, too [docs/cli.md#pskit-trigger].

**In the terminal**
```bash
pskit trigger --list
```
For every function and trigger it prints the sample payload, the local command (`pskit invoke`), the pskit command for the deployed function, the cloud CLI command (for GCP `gcloud`) and the console steps.

**In studio**
1. Open **Test** and pick the function and trigger.
2. Open *How to test this*: it shows the same per trigger, with Copy buttons."""),

    A(527, provider="aws", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=["docs/studio.md#setup-logs-and-provider-differences"],
      user="i got an access key from my admin. in the studio where do i put it? only studio",
      steps=[S("search_docs", query="studio save aws access key profile",
               docs=[D("docs/studio.md", "setup-logs-and-provider-differences", end="- test the SSH connection of an on-prem deploy.")])],
      final="""**In studio**
1. Open **Setup & credentials** with AWS selected in the top bar.
2. Go to *AWS credentials (aws configure)*.
3. Enter the *Access key ID*, the *Secret access key* and a *Default region*. *Session token* is only for temporary credentials (STS / SSO).
4. Give it a *Profile* name and click **Save profile**. It's saved as a profile in `~/.aws` [docs/studio.md#setup-logs-and-provider-differences].
5. Click *Check again*: the AWS credentials check should turn green."""),

    A(528, provider="gcp", stage="dev", mode="ask", page="Setup", persona="detailed_spec",
      sources=["docs/studio.md#project-environment-trigger-resources-and-remove"],
      user="New team members open the project in studio on Windows. They need a virtualenv with our requirements so Run locally works. Can studio set that up for them?",
      steps=[S("search_docs", query="studio project environment venv requirements",
               docs=[D("docs/studio.md", "project-environment-trigger-resources-and-remove", end="page.")])],
      final="""Yes. **Setup & credentials** has *Project environment* [docs/studio.md#project-environment-trigger-resources-and-remove].

**In studio**
1. Open **Setup & credentials** and go to *Project environment*.
2. Pick a Python from the list (every interpreter found on the machine, including the Windows `py` launcher's).
3. Click *Create .venv and install*. It creates `.venv` and installs `requirements.txt`; the output streams in the page.
4. Use *Recreate* later to build it again from scratch.

`.venv` is never bundled into deployments."""),

    A(529, provider="azure", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/cli.md#pskit-remove", "docs/studio.md#project-environment-trigger-resources-and-remove"],
      user="We ran remove with the keep-resources switch on Azure dev two months ago. Now we want to delete those kept queues and containers for good. Where are they and how do we delete them?",
      steps=[S("search_docs", query="kept resources azure storage account delete later",
               docs=[D("docs/cli.md", "pskit-remove", start="With `--keep-resources`", end="so they can be deleted later with `pskit resources delete`.")]),
             S("search_docs", query="studio in the cloud delete all kept",
               docs=[D("docs/studio.md", "project-environment-trigger-resources-and-remove", start="- **Resources → In the cloud**")])],
      final="""On Azure, the storage account, Service Bus namespace and resource group that hold kept queues, containers or topics were kept too. pskit remembers them in `.pskit/azure-dev/kept/`, so it can still delete them [docs/cli.md#pskit-remove].

**In studio**
1. Open **Resources** with azure / dev in the top bar and go to *In the cloud*.
2. Select the kept resources, or click **Delete all kept**.
3. Type the confirmation. They're deleted with their data [docs/studio.md#project-environment-trigger-resources-and-remove].

**In the terminal**
```bash
pskit resources delete --all-kept
```
This deletes the data in the queues and containers. Copy anything you still need first."""),

    A(530, provider="aws", stage="dev", mode="ask", page="Overview", persona="terse_expert",
      sources=["docs/configuration.md#terraform", "docs/cli.md#pskit-deploy"],
      user="pin hashicorp/aws to ~> 5.70 and make the next deploy pick up the new plugin",
      steps=[S("search_docs", query="terraform provider_version pin",
               docs=[D("docs/configuration.md", "terraform")]),
             S("search_docs", query="deploy upgrade provider plugins",
               docs=[D("docs/cli.md", "pskit-deploy", start="| `--upgrade` |", end="| `--upgrade` |")])],
      final="""**In code**
```yaml
provider:
  name: aws
  terraform:
    provider_version: "~> 5.70"
```
`provider_version` replaces the built-in constraint for `hashicorp/aws` [docs/configuration.md#terraform].

**In the terminal**
```bash
pskit deploy --upgrade
```
`--upgrade` runs `terraform init -upgrade`, so the plugin is updated to the newest version that matches [docs/cli.md#pskit-deploy]."""),
]
