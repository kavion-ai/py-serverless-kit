"""Category B (build / add), batch 3. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 41
    B(41, provider="aws", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: oncall
provider:
  name: aws
  region: us-west-2
functions:
  page:
    handler: app.page.page
""",
          "app/__init__.py": "",
          "app/page.py": FUTURE + """

def page(event, ctx):
    alerts = [r.json(default={}) for r in event.records]
    for a in alerts:
        ctx.logger.warning("paging on-call", extra={"alert": a.get("title"), "severity": a.get("severity")})
    return {"paged": len(alerts)}
""",
          "requirements.txt": ""}),
      user="page: sns topic alerts, filter severity in [high, critical]",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add topic event to `page`: name alerts, filter {severity: [high, critical]} (SNS filter policy)",
                                   "Validate for aws (prod), invoke with one alert"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.page.events",
            value=[{"topic": {"name": "alerts", "filter": {"severity": ["high", "critical"]}}}]),
          S("invoke_local", function="page", type="topic", data=[{"title": "db down", "severity": "critical"}]),
      ],
      final="""Added: `- topic: {name: alerts, filter: {severity: [high, critical]}}` on `page`. On AWS the filter becomes the SNS subscription's filter policy [docs/events.md#topic].

- validate (aws, prod): valid.
- invoke: `{"paged": 1}`. A local invoke doesn't apply the filter. SNS does that after deploy.

Retest: `pskit invoke -f page -t topic -d '[{"title": "x", "severity": "high"}]'`. Deploy: **Deploy** (typed confirmation for prod) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 42
    B(42, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#queue-drivers", "docs/resources.md#on-premises-drivers"],
      project=dict(files={
          "pskit.yml": """service: thumbs
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8100
functions: {}
""",
          "requirements.txt": ""}),
      user="we already have a redis server (redis.example.com). can my function get jobs from it instead of the normal folder queue? the redis password is secret",
      steps=[
          S("get_project"),
          S("search_docs", query="onprem redis queue driver url",
            docs=[D("docs/resources.md", "queue-drivers", end="| `redis_stream` |"),
                  D("docs/resources.md", "on-premises-drivers", start="**Secrets.**", end="**Secrets.**")]),
          S("propose_plan", steps=["Add resource `jobs`: type queue, external, driver redis, URL read from the variable REDIS_URL on the host (url_env), so the password is not in pskit.yml",
                                   "Write `app/thumbs.py` with a worker that logs each job",
                                   "Add function `make-thumb` with `- queue: {resource: jobs}`",
                                   "Validate for onprem and run one job locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.jobs",
            value={"type": "queue", "external": True, "options": {"driver": "redis", "url_env": "REDIS_URL"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/thumbs.py", content=FUTURE + """from py_serverless_kit import BatchResult


def make_thumb(event, ctx):
    result = BatchResult()
    for record in event.records:
        job = record.json(default={}) or {}
        if not job.get("image"):
            result.fail(record)
            continue
        ctx.logger.info("thumbnail", extra={"image": job["image"]})
    return result
"""),
          S("set_config", path="functions.make-thumb",
            value={"handler": "app.thumbs.make_thumb", "events": [{"queue": {"resource": "jobs"}}]}),
          S("invoke_local", function="make-thumb", type="queue", data=[{"image": "photos/beach.jpg"}]),
      ],
      final="""Yes. Your function `make-thumb` now takes its jobs from Redis instead of the folder queue:

```yaml
resources:
  jobs:
    type: queue
    external: true
    options: {driver: redis, url_env: REDIS_URL}
functions:
  make-thumb:
    handler: app.thumbs.make_thumb
    events:
      - queue: {resource: jobs}
```

- `url_env: REDIS_URL` means the host reads the address, password included, from the variable `REDIS_URL` when it starts. The password never goes into pskit.yml or Terraform state [docs/resources.md#on-premises-drivers].
- `pskit validate` for onprem: valid.
- Local test with one job: no errors and an empty `batchItemFailures`.

Before deploying, set `REDIS_URL` on the server where the host runs, for example `redis://:<password>@redis.example.com:6379/0`. If it is missing, the host stops with an error that names it. Deploy on the **Deploy** page or with `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 43
    B(43, provider="gcp", stage="prod", mode="auto", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: search
provider:
  name: gcp
  region: asia-northeast1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  query:
    handler: app.search.query
    events:
    - http: GET /search
""",
          "app/__init__.py": "",
          "app/search.py": FUTURE + """

def query(event, ctx):
    return {"hits": []}
""",
          "requirements.txt": ""}),
      user="Add `POST /internal/reindex` that only our other GCP services can call (no public invoker). It takes {\"index\": \"products\"} and answers 202 with {\"queued\": \"products\"}. Keep /search public.",
      steps=[
          S("get_project"),
          S("search_docs", query="auth iam gcp public invoker",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("propose_plan", steps=["Add `reindex` to `app/search.py`: read `index`, return ({queued}, 202)",
                                   "Add function `reindex` on POST /internal/reindex with auth: iam",
                                   "Validate for gcp (prod) and post {\"index\": \"products\"} locally"]),
          S("write_file", path="app/search.py", content=FUTURE + """from py_serverless_kit import BadRequest


def query(event, ctx):
    return {"hits": []}


def reindex(event, ctx):
    body = event.http.json(default={}) or {}
    index = body.get("index")
    if not index:
        raise BadRequest("index is required")
    ctx.logger.info("reindex requested", extra={"index": index})
    return {"queued": index}, 202
"""),
          S("set_config", path="functions.reindex",
            value={"handler": "app.search.reindex",
                   "events": [{"http": {"path": "/internal/reindex", "method": "POST", "auth": "iam"}}]}),
          S("invoke_local", function="reindex", method="POST", path="/internal/reindex", data={"index": "products"}),
      ],
      final="""Added `reindex` on `POST /internal/reindex` with `auth: iam`:

```yaml
functions:
  reindex:
    handler: app.search.reindex
    events:
      - http: {path: /internal/reindex, method: POST, auth: iam}
```

- On GCP, `auth: iam` means no `allUsers` invoker binding. Only identities that you grant the invoker role can call it. `/search` keeps `auth: none` and stays public [docs/providers.md#gcp-google-cloud-functions-2nd-gen].
- `pskit validate` (gcp, prod): valid.
- Local POST `{"index": "products"}`: 202, `{"queued": "products"}`. Locally there is no IAM check.

After deploy, grant your calling services' identities permission to invoke this function; nobody else can. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 44
    B(44, provider="azure", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/events.md#schedule", "docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition"],
      project=dict(files={
          "pskit.yml": """service: fx-rates
provider:
  name: azure
  region: uksouth
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions:
  fetch-rates:
    handler: app.rates.fetch
""",
          "app/__init__.py": "",
          "app/rates.py": FUTURE + """

def fetch(event, ctx):
    base = (event.data or {}).get("base", "EUR")
    ctx.logger.info("fetch rates", extra={"base": base})
    return {"base": base}
""",
          "requirements.txt": ""}),
      user="serverless.yml had this on the function:\n  events:\n    - schedule:\n        rate: rate(1 hour)\n        input: {base: USD}\nport it to the azure project",
      steps=[
          S("get_project"),
          S("search_docs", query="schedule rate input azure timer",
            docs=[D("docs/events.md", "schedule", end="The handler gets `event.type")]),
          S("propose_plan", steps=["Add to `fetch-rates`: schedule rate `1 hour` (pskit's form of rate(1 hour)), input {base: USD}",
                                   "Validate for azure and run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.fetch-rates.events", value=[{"schedule": {"rate": "1 hour", "input": {"base": "USD"}}}]),
          S("invoke_local", function="fetch-rates", type="schedule"),
      ],
      final="""Ported. pskit writes the rate without the `rate(...)` wrapper:

```yaml
functions:
  fetch-rates:
    events:
      - schedule:
          rate: 1 hour
          input: {base: USD}
```

On Azure, pskit turns this into a timer trigger with a 6-field NCRONTAB, and timers run in UTC [docs/events.md#schedule].

- `pskit validate` for azure: valid.
- Local schedule run: the handler got `base` = `USD` and returned `{"base": "USD"}`.

Retest: `pskit invoke -f fetch-rates -t schedule`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 45
    B(45, provider="huawei", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: doc-scan
provider:
  name: huawei
  region: cn-north-4
functions: {}
""",
          "requirements.txt": ""}),
      user="when pdf come in obs bucket scan-in, function must log name and size. other file ignore",
      steps=[
          S("get_project"),
          S("search_docs", query="huawei obs storage trigger suffix",
            docs=[D("docs/events.md", "storage", start="| Provider | Service |", end="| huawei |")]),
          S("propose_plan", steps=["Write `app/scan.py` that logs key and size of each new file",
                                   "Add function `on-pdf` with storage trigger: bucket scan-in, suffix .pdf",
                                   "Validate for huawei and run one PDF locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/scan.py", content=FUTURE + """

def on_pdf(event, ctx):
    names = []
    for record in event.records:
        ctx.logger.info("pdf arrived", extra={"key": record.key, "size": record.size})
        names.append(record.key)
    return {"pdfs": names}
"""),
          S("set_config", path="functions.on-pdf",
            value={"handler": "app.scan.on_pdf", "events": [{"storage": {"bucket": "scan-in", "suffix": ".pdf"}}]}),
          S("invoke_local", function="on-pdf", type="storage", data={"bucket": "scan-in", "key": "contract-7.pdf", "size": 88120}),
      ],
      final="""Done. Function `on-pdf` runs when a `.pdf` arrives in the OBS bucket `scan-in`. Other files don't trigger it, because OBS applies the suffix filter natively [docs/events.md#storage].

- `pskit validate` for huawei: valid. No API Gateway is needed, because there is no HTTP trigger.
- Local run with `contract-7.pdf`: logged name and size, returned `{"pdfs": ["contract-7.pdf"]}`.

Test again: `pskit invoke -f on-pdf -t storage -d '{"bucket": "scan-in", "key": "a.pdf", "size": 10}'`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 46
    B(46, provider="onprem", stage="staging", mode="auto", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": """service: media
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8101
functions:
  resize:
    handler: app.media.resize
  thumbnail:
    handler: app.media.thumbnail
  publish:
    handler: app.media.publish
""",
          "app/__init__.py": "",
          "app/media.py": FUTURE + """

def resize(event, ctx):
    return {"large": f"{event.data['key']}@1600"}


def thumbnail(event, ctx):
    return {"thumb": f"{event.data['key']}@200"}


def publish(event, ctx):
    parts = event.data or []
    merged = {}
    for p in parts:
        merged.update(p)
    return {"published": merged}
""",
          "requirements.txt": ""}),
      user="Workflow `process-image` for the on-prem host: run `resize` and `thumbnail` at the same time on the input ({\"key\": ...}), then pass both results to `publish`.",
      steps=[
          S("get_project"),
          S("search_docs", query="parallel state branches result list",
            docs=[D("docs/workflows.md", "state-types", start="| `parallel` |", end="| `parallel` |")]),
          S("propose_plan", steps=["Add workflow `process-image`: Both (parallel: branch Resize -> task resize, branch Thumb -> task thumbnail) -> Publish (task publish, end)",
                                   "Validate for onprem (staging) and run `publish` locally with a two-item list like the parallel result"]),
          S("set_config", path="workflows.process-image",
            value={"start_at": "Both",
                   "states": {"Both": {"type": "parallel", "next": "Publish",
                                       "branches": [
                                           {"start_at": "Resize", "states": {"Resize": {"type": "task", "function": "resize", "end": True}}},
                                           {"start_at": "Thumb", "states": {"Thumb": {"type": "task", "function": "thumbnail", "end": True}}}]},
                              "Publish": {"type": "task", "function": "publish", "end": True}}}),
          S("invoke_local", function="publish", type="workflow",
            data=[{"large": "cat.jpg@1600"}, {"thumb": "cat.jpg@200"}]),
      ],
      final="""Added `process-image`:

```yaml
workflows:
  process-image:
    start_at: Both
    states:
      Both:
        type: parallel
        branches:
          - {start_at: Resize, states: {Resize: {type: task, function: resize, end: true}}}
          - {start_at: Thumb,  states: {Thumb:  {type: task, function: thumbnail, end: true}}}
        next: Publish
      Publish: {type: task, function: publish, end: true}
```

- validate (onprem, staging): valid. It runs on the embedded engine inside the host.
- A parallel state's result is a list with one item per branch [docs/workflows.md#state-types]. `publish` run locally with such a list returned `{"published": {"large": "cat.jpg@1600", "thumb": "cat.jpg@200"}}`.

Full local run: `pskit workflow run process-image -i '{"key": "cat.jpg"}' --history`. After deploy, `POST /workflows/process-image` on the host answers 202 with an `execution_id` [docs/workflows.md#embedded-orchestrator]. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 47
    B(47, provider="aws", stage="dev", mode="auto", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: team-report
provider:
  name: aws
  region: eu-west-2
functions:
  weekly-summary:
    handler: app.report.weekly
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """

def weekly(event, ctx):
    team = (event.data or {}).get("team", "everyone")
    ctx.logger.info("weekly summary", extra={"team": team})
    return {"team": team, "sent": True}
""",
          "requirements.txt": ""}),
      user="can the weekly summary go out on its own every monday at 9 in the morning? we're in London",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add a schedule to `weekly-summary`: cron `0 9 * * 1` (Mondays 09:00), timezone Europe/London, input {team: platform}",
                                   "Validate for aws and run the scheduled start locally"]),
          S("set_config", path="functions.weekly-summary.events",
            value=[{"schedule": {"cron": "0 9 * * 1", "timezone": "Europe/London", "input": {"team": "platform"}}}]),
          S("invoke_local", function="weekly-summary", type="schedule"),
      ],
      final="""Yes. It will now run by itself every Monday at 09:00 London time, summer time included, because the timezone is set:

```yaml
events:
  - schedule:
      cron: "0 9 * * 1"
      timezone: Europe/London
      input: {team: platform}
```

I set the team to `platform` as an example input. Change it on **Functions** (or in the YAML) if your team has another name.

- `pskit validate` for aws: valid.
- Local scheduled run: returned `{"team": "platform", "sent": true}`.

Test it any time on **Test** > **▶ Run locally**, or with `pskit invoke -f weekly-summary -t schedule`. It runs by itself after you deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 48
    B(48, provider="alibaba", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: loyalty
provider:
  name: alibaba
  region: cn-beijing
functions:
  vip-perks:
    handler: app.perks.grant
""",
          "app/__init__.py": "",
          "app/perks.py": FUTURE + """

def grant(event, ctx):
    users = [r.json(default={}).get("user_id") for r in event.records]
    return {"granted": users}
""",
          "requirements.txt": ""}),
      user="vip-perks <- MNS topic member-events, only tag vip",
      steps=[
          S("get_project"),
          S("search_docs", query="alibaba mns topic filter tag",
            docs=[D("docs/events.md", "topic", start="| Provider |", end="| alibaba |")]),
          S("propose_plan", steps=["Add topic event: name member-events, filter {tag: vip}",
                                   "Validate for alibaba (staging), invoke with one message"]),
          S("set_config", path="functions.vip-perks.events",
            value=[{"topic": {"name": "member-events", "filter": {"tag": "vip"}}}]),
          S("invoke_local", function="vip-perks", type="topic", data=[{"user_id": "u-301"}]),
      ],
      final="""Added: `- topic: {name: member-events, filter: {tag: vip}}`. On Alibaba MNS, only `filter.tag` (a string) is supported [docs/events.md#topic].

- validate (alibaba, staging): valid.
- invoke: `{"granted": ["u-301"]}`. The tag filter is applied by MNS after deploy, not by a local invoke.

Retest: `pskit invoke -f vip-perks -t topic -d '[{"user_id": "u-1"}]'`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 49
    B(49, provider="gcp", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#queue", "docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: geo
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions: {}
""",
          "requirements.txt": ""}),
      user="$ gcloud pubsub topics publish geocode-requests --message='{\"address\": \"1 Main St, Springfield\"}'\nmessageIds:\n- '4401189'\nnothing consumes it yet. build the consumer, log the address",
      steps=[
          S("get_project"),
          S("search_docs", query="gcp queue pubsub push trigger",
            docs=[D("docs/events.md", "queue", start="On GCP a \"queue\" is a Pub/Sub topic", end="On GCP a \"queue\" is a Pub/Sub topic")]),
          S("propose_plan", steps=["Write `app/geocode.py`: log `address` from each message",
                                   "Add function `geocode` with `- queue: geocode-requests` (a Pub/Sub topic on GCP)",
                                   "Validate for gcp and run your sample message locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/geocode.py", content=FUTURE + """

def geocode(event, ctx):
    addresses = []
    for record in event.records:
        msg = record.json(default={}) or {}
        ctx.logger.info("geocode request", extra={"address": msg.get("address"), "message_id": record.id})
        addresses.append(msg.get("address"))
    return {"addresses": addresses}
"""),
          S("set_config", path="functions.geocode",
            value={"handler": "app.geocode.geocode", "events": [{"queue": "geocode-requests"}]}),
          S("invoke_local", function="geocode", type="queue", data=[{"address": "1 Main St, Springfield"}]),
      ],
      final="""Added the consumer `geocode` with `- queue: geocode-requests`. On GCP a pskit queue is a Pub/Sub topic with a push trigger, so your `gcloud pubsub topics publish` command is the right way to feed it [docs/events.md#queue].

- `pskit validate` for gcp: valid.
- Local run with your message: logged `1 Main St, Springfield` and returned it in `addresses`.

One thing to check: pskit **creates** the topic `geocode-requests` on deploy. Your topic already exists, so set `existing: true` on the event (`- queue: {name: geocode-requests, existing: true}`) unless you want pskit to own it. Tell me and I'll change it.

Test: `pskit invoke -f geocode -t queue -d '[{"address": "2 Elm St"}]'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 50
    B(50, provider="onprem", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      project=dict(files={
          "pskit.yml": """service: shopfront
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8102
functions:
  checkout:
    handler: app.shop.checkout
    events:
    - http: POST /checkout
""",
          "app/__init__.py": "",
          "app/shop.py": FUTURE + """

def checkout(event, ctx):
    cart = event.http.json()
    total = sum(i["price"] * i["qty"] for i in cart.get("items", []))
    return {"total": total}
""",
          "requirements.txt": ""}),
      user="I want a separate invoke-only function `price-check` that applies a 10% discount when the total is above 100. `checkout` should call it with invoke() and return its answer. No HTTP route for price-check.",
      steps=[
          S("get_project"),
          S("search_docs", query="invoke another function onprem in-process",
            docs=[D("docs/handlers.md", "invoke-calling-another-function", end="2. `local` (CLI, tests)")]),
          S("propose_plan", steps=["Add `price_check` to `app/shop.py` (10% off above 100) and make `checkout` call invoke(\"price-check\", {total})",
                                   "Add function `price-check` with no events (invoke-only)",
                                   "Validate for onprem and POST a cart to checkout locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/shop.py", content=FUTURE + """from py_serverless_kit import invoke


def checkout(event, ctx):
    cart = event.http.json()
    total = sum(i["price"] * i["qty"] for i in cart.get("items", []))
    return invoke("price-check", {"total": total})


def price_check(event, ctx):
    total = float((event.data or {}).get("total", 0))
    discount = round(total * 0.10, 2) if total > 100 else 0.0
    return {"total": total, "discount": discount, "to_pay": round(total - discount, 2)}
"""),
          S("set_config", path="functions.price-check", value={"handler": "app.shop.price_check"}),
          S("invoke_local", function="checkout", method="POST", path="/checkout",
            data={"items": [{"price": 45, "qty": 2}, {"price": 30, "qty": 1}]}),
      ],
      final="""Done:

- `price-check` is a new invoke-only function (no `events`), so it has no HTTP route.
- `checkout` now returns `invoke("price-check", {"total": total})`.

Checks:
- `pskit validate` for onprem: valid.
- Local POST with a cart of 2 x 45 + 1 x 30: status 200, `{"total": 120.0, "discount": 12.0, "to_pay": 108.0}`. So the call to `price-check` worked.

On the on-prem host and under the CLI, `invoke()` runs the target in-process [docs/handlers.md#invoke-calling-another-function]. If you move this to another cloud later, check that provider's row there (AWS needs `lambda:InvokeFunction`, for example).

Test: **Test** > **▶ Run locally**, or `pskit invoke -f checkout -d '{"items": [{"price": 50, "qty": 1}]}'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 51
    B(51, provider="azure", stage="staging", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: cms
provider:
  name: azure
  region: francecentral
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions:
  pages:
    handler: app.cms.pages
    events:
    - http: GET /pages
""",
          "app/__init__.py": "",
          "app/cms.py": FUTURE + """

def pages(event, ctx):
    return [{"slug": "home"}]
""",
          "requirements.txt": ""}),
      user="need admin endpoint POST /admin/cache/flush, not public, only who has function key. azure",
      steps=[
          S("get_project"),
          S("search_docs", query="azure auth key function key",
            docs=[D("docs/events.md", "http", start="| `auth` | Supported on |", end="| `key` |")]),
          S("propose_plan", steps=["Add `flush_cache` to `app/cms.py` (returns flushed: true)",
                                   "Add function `flush-cache` on POST /admin/cache/flush with auth: key",
                                   "Validate for azure (staging) and call it locally"]),
          S("write_file", path="app/cms.py", content=FUTURE + """

def pages(event, ctx):
    return [{"slug": "home"}]


def flush_cache(event, ctx):
    ctx.logger.info("cache flush requested")
    return {"flushed": True}
"""),
          S("set_config", path="functions.flush-cache",
            value={"handler": "app.cms.flush_cache",
                   "events": [{"http": {"path": "/admin/cache/flush", "method": "POST", "auth": "key"}}]}),
          S("invoke_local", function="flush-cache", method="POST", path="/admin/cache/flush"),
      ],
      final="""Added `flush-cache` on `POST /admin/cache/flush` with `auth: key`. On Azure that means a function key (`AuthLevel.FUNCTION`), so calls without the key are refused [docs/events.md#http].

- validate (azure, staging): valid.
- local call: 200, `{"flushed": true}`. Locally there is no key check.

After deploy, callers send the function key in the `x-functions-key` header. You find the keys in the Azure portal under the Function App. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 52
    B(52, provider="tencent", stage="dev", mode="auto", page="Functions", persona="beginner",
      sources=["docs/events.md#storage", "docs/providers.md#tencent-serverless-cloud-function-scf"],
      project=dict(files={
          "pskit.yml": """service: profile-pics
provider:
  name: tencent
  region: ap-guangzhou
functions: {}
""",
          "requirements.txt": ""}),
      user="when people upload a new avatar to my COS bucket avatars-1250000000 I want to know about it",
      steps=[
          S("get_project"),
          S("search_docs", query="tencent cos bucket name appid storage trigger",
            docs=[D("docs/events.md", "storage", start="| tencent |", end="| tencent |")]),
          S("propose_plan", steps=["Write `app/avatars.py` that logs each new avatar",
                                   "Add function `on-avatar` with a storage trigger on bucket `avatars-1250000000`",
                                   "Validate for tencent and run a fake upload locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/avatars.py", content=FUTURE + """

def on_avatar(event, ctx):
    uploaded = []
    for record in event.records:
        ctx.logger.info("new avatar", extra={"key": record.key, "size": record.size})
        uploaded.append(record.key)
    return {"avatars": uploaded}
"""),
          S("set_config", path="functions.on-avatar",
            value={"handler": "app.avatars.on_avatar", "events": [{"storage": "avatars-1250000000"}]}),
          S("invoke_local", function="on-avatar", type="storage", data={"bucket": "avatars-1250000000", "key": "users/42.png"}),
      ],
      final="""Done. A new function `on-avatar` runs whenever a file is uploaded to `avatars-1250000000`. Your bucket name already has the `-<APPID>` ending that Tencent COS needs [docs/events.md#storage].

- `pskit validate` for tencent: valid.
- A fake upload of `users/42.png` run locally: it logged "new avatar" and returned `{"avatars": ["users/42.png"]}`.

For now it only writes a log line. Tell me what should happen next (make a small version, check the size, ...).

Try it: **Test** > **▶ Run locally**, or `pskit invoke -f on-avatar -t storage -d '{"bucket": "avatars-1250000000", "key": "a.png"}'`. Turn it on for real with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 53
    B(53, provider="aws", stage="staging", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#resources-storage-queues-topics-databases-any-service", "docs/resources.md#using-a-resource-from-an-event"],
      project=dict(files={
          "pskit.yml": """service: revenue
provider:
  name: aws
  region: us-east-1
functions: {}
""",
          "requirements.txt": ""}),
      user="The billing team owns an SNS topic in their own CloudFormation stack: arn:aws:sns:us-east-1:123456789012:billing-events. I need a Lambda that subscribes to it without pskit creating or deleting the topic.",
      steps=[
          S("get_project"),
          S("search_docs", query="external topic arn resource event",
            docs=[D("docs/resources.md", "using-a-resource-from-an-event")]),
          S("propose_plan", steps=["Add resource `billing-events`: type topic, external, connection.arn = the billing team's ARN",
                                   "Write `app/revenue.py` that logs each billing event",
                                   "Add function `record-revenue` with `- topic: {resource: billing-events}`",
                                   "Validate for aws (staging) and run one event locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.billing-events",
            value={"type": "topic", "external": True,
                   "connection": {"arn": "arn:aws:sns:us-east-1:123456789012:billing-events"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/revenue.py", content=FUTURE + """

def record(event, ctx):
    amounts = []
    for r in event.records:
        msg = r.json(default={}) or {}
        ctx.logger.info("billing event", extra={"kind": msg.get("kind"), "amount": msg.get("amount")})
        amounts.append(msg.get("amount", 0))
    return {"events": len(amounts), "sum": sum(amounts)}
"""),
          S("set_config", path="functions.record-revenue",
            value={"handler": "app.revenue.record", "events": [{"topic": {"resource": "billing-events"}}]}),
          S("invoke_local", function="record-revenue", type="topic", data=[{"kind": "paid", "amount": 49}]),
      ],
      final="""Added. pskit will subscribe to the billing team's topic but never create, change or delete it:

```yaml
resources:
  billing-events:
    type: topic
    external: true
    connection:
      arn: arn:aws:sns:us-east-1:123456789012:billing-events
functions:
  record-revenue:
    handler: app.revenue.record
    events:
      - topic: {resource: billing-events}
```

A resource-backed event behaves like `name: <native name>` plus `existing: true` [docs/resources.md#using-a-resource-from-an-event]. Without `name`, the native name comes from the last `:` part of the ARN.

- `pskit validate` (aws, staging): valid.
- Local run with `{"kind": "paid", "amount": 49}`: `{"events": 1, "sum": 49}`.

The billing team may need to allow your account to subscribe, if their topic policy is strict. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 54
    B(54, provider="digitalocean", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: backups
provider:
  name: digitalocean
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE, fn-00000000-0000-0000-0000-000000000000}
functions:
  snapshot:
    handler: app.backup.snapshot
    timeout: 60
""",
          "app/__init__.py": "",
          "app/backup.py": FUTURE + """

def snapshot(event, ctx):
    target = (event.data or {}).get("target", "all")
    ctx.logger.info("snapshot", extra={"target": target})
    return {"target": target}
""",
          "requirements.txt": ""}),
      user="snapshot: cron 30 2 * * *, input target=db",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add schedule to `snapshot`: cron `30 2 * * *`, input {target: db}",
                                   "Validate for digitalocean (prod), invoke schedule"]),
          S("set_config", path="functions.snapshot.events",
            value=[{"schedule": {"cron": "30 2 * * *", "input": {"target": "db"}}}]),
          S("invoke_local", function="snapshot", type="schedule"),
      ],
      final="""Added: `- schedule: {cron: "30 2 * * *", input: {target: db}}`. It runs daily at 02:30 UTC as a `project.yml` scheduled trigger [docs/events.md#schedule].

- validate (digitalocean, prod): valid, plus the usual `doctl` warning (doctl is not on PATH here, and deploy needs it).
- invoke: `{"target": "db"}`.

Retest: `pskit invoke -f snapshot -t schedule`. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 55
    B(55, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/smtp/README.md#create-it", "docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": """service: orders-mail
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8103
functions: {}
""",
          "requirements.txt": ""}),
      user="customer send order by email to orders@shop.example.com, i want function read subject and body. we not have mail server yet",
      steps=[
          S("get_project"),
          S("search_docs", query="smtp server create resource trigger functions",
            docs=[D("docs/smtp/README.md", "create-it", end="| Advanced |")]),
          S("propose_plan", steps=["Write `app/orders_mail.py`: read subject, text body and sender from the mail",
                                   "Add function `order-mail` (no trigger yet: the SMTP server must exist first)",
                                   "Validate for onprem and run a test mail locally",
                                   "You then create the SMTP server under Resources > + SMTP server and tick `order-mail`"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/orders_mail.py", content=FUTURE + """

def order_mail(event, ctx):
    mail = event.data or {}
    order = {"from": mail.get("from"), "subject": mail.get("subject"), "body": mail.get("text") or ""}
    ctx.logger.info("order mail", extra={"from_addr": order["from"], "subject": order["subject"]})
    return order
"""),
          S("set_config", path="functions.order-mail", value={"handler": "app.orders_mail.order_mail"}),
          S("invoke_local", function="order-mail", type="smtp",
            data={"from": "buyer@example.org", "to": ["orders@shop.example.com"], "subject": "Order: 3 chairs",
                  "text": "Please send 3 chairs to Main St 5."}),
      ],
      final="""The function is ready: `order-mail` reads the sender, subject and body of each mail.

- `pskit validate` for onprem: valid.
- A local test mail ("Order: 3 chairs") came back with sender, subject and body.

It has no trigger yet, because you don't have a mail server. An `smtp` trigger needs one. Next steps:

1. **Resources** > **+ SMTP server**. Use resource key e.g. `inbound-mail` and domain `shop.example.com`. Under *Trigger functions*, tick `order-mail`. This adds `- smtp: {resource: inbound-mail}` to the function [docs/smtp/README.md#create-it].
2. Add the A and MX records that the server's **DNS guide** shows, and open port 25.
3. Deploy: **Deploy** page or `pskit deploy -s dev`.

If your company already gets mail on `shop.example.com` (Microsoft 365, Google), use a subdomain like `orders.shop.example.com` instead, so the normal mailboxes keep working.

Test again without a server: `pskit invoke -f order-mail -t smtp -d '{"from": "a@example.org", "subject": "Order", "text": "2 tables"}'`."""),

    # ------------------------------------------------------------------ 56
    B(56, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: plant-shop
provider:
  name: gcp
  region: us-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions: {}
""",
          "requirements.txt": ""}),
      user="I have a list of plants with a category (indoor or outdoor). How can people see only indoor ones from a link?",
      steps=[
          S("get_project"),
          S("search_docs", query="query string parameters handler",
            docs=[D("docs/handlers.md", "httprequest", end="| `path_params`")]),
          S("propose_plan", steps=["Write `app/plants.py` with a small plant list and a handler that filters by ?category=",
                                   "Add function `plants` on GET /plants",
                                   "Validate for gcp and call /plants?category=indoor locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/plants.py", content=FUTURE + """
PLANTS = [
    {"name": "Monstera", "category": "indoor"},
    {"name": "Lavender", "category": "outdoor"},
    {"name": "Snake plant", "category": "indoor"},
]


def list_plants(event, ctx):
    category = event.http.query.get("category")
    if category:
        return [p for p in PLANTS if p["category"] == category.lower()]
    return PLANTS
"""),
          S("set_config", path="functions.plants",
            value={"handler": "app.plants.list_plants", "events": [{"http": "GET /plants"}]}),
          S("invoke_local", function="plants", method="GET", path="/plants?category=indoor"),
      ],
      final="""Done. You have a link `/plants`. Add `?category=indoor` to it and you get only the indoor plants.

- `/plants` shows all plants.
- `/plants?category=indoor` shows Monstera and Snake plant. I checked this locally: status 200 with exactly those two.
- `pskit validate` for gcp: valid.

The plants are a short list inside `app/plants.py` for now. Swap in your real list, or tell me where it lives.

Try it on **Test** > **▶ Run locally** with the path `/plants?category=outdoor`, or run `pskit invoke -f plants --path "/plants?category=outdoor"`. To get a public link, deploy on the **Deploy** page (or `pskit deploy -s dev`), then run `pskit info` to see the URL."""),

    # ------------------------------------------------------------------ 57
    B(57, provider="aws", stage="dev", mode="auto", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: data-lake
provider:
  name: aws
  region: ap-southeast-2
functions: {}
""",
          "requirements.txt": ""}),
      user="Create `ingest-json`: S3 bucket `lake-landing` (pskit may create it), only keys under `uploads/` ending in `.json`, created events. The function needs 512 MB and 120 s. For each record, log bucket/key/size and return the list of keys.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/ingest.py` (log bucket, key, size; return keys)",
                                   "Add `ingest-json`: memory 512, timeout 120, storage {bucket: lake-landing, events: [created], prefix: uploads/, suffix: .json}",
                                   "Validate for aws and run one record locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/ingest.py", content=FUTURE + """

def ingest(event, ctx):
    keys = []
    for record in event.records:
        ctx.logger.info("landing file", extra={"bucket": record.bucket, "key": record.key, "size": record.size})
        keys.append(record.key)
    return {"keys": keys}
"""),
          S("set_config", path="functions.ingest-json",
            value={"handler": "app.ingest.ingest", "memory": 512, "timeout": 120,
                   "events": [{"storage": {"bucket": "lake-landing", "events": ["created"], "prefix": "uploads/",
                                           "suffix": ".json"}}]}),
          S("invoke_local", function="ingest-json", type="storage",
            data={"bucket": "lake-landing", "key": "uploads/2026/11/01/batch-1.json", "size": 4096}),
      ],
      final="""Created `ingest-json`:

```yaml
functions:
  ingest-json:
    handler: app.ingest.ingest
    memory: 512
    timeout: 120
    events:
      - storage: {bucket: lake-landing, events: [created], prefix: uploads/, suffix: .json}
```

- `pskit validate` for aws: valid. pskit creates the S3 bucket `lake-landing`, blocks public access on it, and adds the bucket notification with the prefix/suffix filter.
- Local run with `uploads/2026/11/01/batch-1.json`: returned `{"keys": ["uploads/2026/11/01/batch-1.json"]}`.

Retest: `pskit invoke -f ingest-json -t storage -d '{"bucket": "lake-landing", "key": "uploads/x.json"}'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 58
    B(58, provider="ibm", stage="staging", mode="auto", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#provider", "docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: quotes
provider:
  name: ibm
  region: us-south
  runtime: python3.11
functions:
  quote:
    handler: app.quotes.quote
    events:
    - http: GET /quote
""",
          "app/__init__.py": "",
          "app/quotes.py": FUTURE + """

def quote(event, ctx):
    return {"quote": "Simplicity is prerequisite for reliability."}
""",
          "requirements.txt": ""}),
      user="add /version endpoint show APP_VERSION 1.4.2 and stage. version must be one place for all function",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Set provider.environment.APP_VERSION = \"1.4.2\" (all functions get it)",
                                   "Add `version` to `app/quotes.py` returning APP_VERSION and ctx.stage; function `version` on GET /version",
                                   "Validate for ibm (staging), call /version locally"]),
          S("set_config", path="provider.environment.APP_VERSION", value="1.4.2"),
          S("write_file", path="app/quotes.py", content=FUTURE + """

def quote(event, ctx):
    return {"quote": "Simplicity is prerequisite for reliability."}


def version(event, ctx):
    return {"version": ctx.env.get("APP_VERSION", "unknown"), "stage": ctx.stage}
"""),
          S("set_config", path="functions.version",
            value={"handler": "app.quotes.version", "events": [{"http": "GET /version"}]}),
          S("invoke_local", function="version", method="GET", path="/version"),
      ],
      final="""Done. The version is in one place, `provider.environment`, so every function gets it:

```yaml
provider:
  environment:
    APP_VERSION: "1.4.2"
```

- New `GET /version` returns `APP_VERSION` and the stage.
- validate (ibm, staging): valid.
- local call: 200, `{"version": "1.4.2", "stage": "staging"}`.

Next release: change only `APP_VERSION`. In studio it is **Overview & provider** > *Environment variables*. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 59
    B(59, provider="oracle", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#variables", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: repo-hooks
provider:
  name: oracle
  region: us-ashburn-1
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID, ocid1.compartment.oc1..aaaa}
    subnet_ids:
    - ${env:OCI_SUBNET_ID, ocid1.subnet.oc1..aaaa}
    image_repository: ${env:OCI_IMAGE_REPO, iad.ocir.io/mytenancy/repo-hooks}
functions: {}
""",
          "requirements.txt": ""}),
      user="We need a GitHub webhook receiver on OCI: POST /hooks/github. Verify the X-Hub-Signature-256 header (HMAC-SHA256 of the raw body, \"sha256=<hex>\") against a shared secret from GITHUB_WEBHOOK_SECRET, answer 401 when it doesn't match, otherwise log the X-GitHub-Event header and return 204.",
      steps=[
          S("get_project"),
          S("search_docs", query="environment variable secret env default",
            docs=[D("docs/configuration.md", "variables", end="| `${env:NAME, default}`")]),
          S("propose_plan", steps=["Write `app/github.py`: HMAC-SHA256 over the raw body with GITHUB_WEBHOOK_SECRET, compare_digest with the header, 401 on mismatch, else log the event and return None (204)",
                                   "Add function `github-hook` on POST /hooks/github with GITHUB_WEBHOOK_SECRET: ${env:GITHUB_WEBHOOK_SECRET, }",
                                   "Validate for oracle (prod) and post an unsigned body locally (expect 401)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/github.py", content=FUTURE + """import hashlib
import hmac

from py_serverless_kit import Unauthorized


def receive(event, ctx):
    key = ctx.env.get("GITHUB_WEBHOOK_SECRET", "").encode("utf-8")
    body = event.http.body or b""
    if isinstance(body, str):
        body = body.encode("utf-8")
    expected = "sha256=" + hmac.new(key, body, hashlib.sha256).hexdigest()
    given = event.http.headers.get("x-hub-signature-256", "")
    if not key or not hmac.compare_digest(given, expected):
        raise Unauthorized("bad signature")
    ctx.logger.info("github event", extra={"event": event.http.headers.get("x-github-event")})
    return None
"""),
          S("set_config", path="functions.github-hook",
            value={"handler": "app.github.receive",
                   "environment": {"GITHUB_WEBHOOK_SECRET": "${env:GITHUB_WEBHOOK_SECRET, }"},
                   "events": [{"http": "POST /hooks/github"}]}),
          S("invoke_local", function="github-hook", method="POST", path="/hooks/github", data={"zen": "Keep it simple."}),
      ],
      final="""Added `github-hook` on `POST /hooks/github`. It computes `sha256=<hex>` over the raw body with `GITHUB_WEBHOOK_SECRET`, compares it in constant time, and answers 401 on a mismatch, or 204 after logging `X-GitHub-Event`.

- `pskit validate` (oracle, prod): valid, with OCI's reminder that API Gateway needs an IAM policy to call functions.
- Local POST without a signature: 401 `bad signature`, as expected. The empty secret also makes it refuse every call, so it fails closed.

The secret is not in pskit.yml, only `${env:GITHUB_WEBHOOK_SECRET, }` [docs/configuration.md#variables]. Export it before deploying. To test a valid call locally, put it in `.env` and use `pskit invoke -f github-hook --env-file .env -H "X-Hub-Signature-256: sha256=<hex>" -d '...'`. Deploy prod from **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 60
    B(60, provider="onprem", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#topic", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: fulfilment
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8104
functions:
  ship:
    handler: app.flow.ship
  refund:
    handler: app.flow.refund
""",
          "app/__init__.py": "",
          "app/flow.py": FUTURE + """

def ship(event, ctx):
    return {"shipped": [r.json(default={}).get("order_id") for r in event.records]}


def refund(event, ctx):
    return {"refunded": [r.json(default={}).get("order_id") for r in event.records]}
""",
          "requirements.txt": ""}),
      user="topic orders fan-out: ship gets status=paid, refund gets status=cancelled",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["ship: topic {name: orders, filter: {status: [paid]}}",
                                   "refund: topic {name: orders, filter: {status: [cancelled]}}",
                                   "Validate for onprem, invoke refund"]),
          S("set_config", path="functions.ship.events",
            value=[{"topic": {"name": "orders", "filter": {"status": ["paid"]}}}]),
          S("set_config", path="functions.refund.events",
            value=[{"topic": {"name": "orders", "filter": {"status": ["cancelled"]}}}]),
          S("invoke_local", function="refund", type="topic", data=[{"order_id": 77, "status": "cancelled"}]),
      ],
      final="""Both subscribed to `orders`:

```yaml
functions:
  ship:
    events: [{topic: {name: orders, filter: {status: [paid]}}}]
  refund:
    events: [{topic: {name: orders, filter: {status: [cancelled]}}}]
```

- validate (onprem): valid after both changes. The on-prem file topic fans out to both. Each `filter` is an exact match on attributes, then on JSON body fields [docs/events.md#topic].
- invoke refund: `{"refunded": [77]}`.

Publish after deploy: `POST /__pskit/topics/orders` on the host. Deploy: `pskit deploy -s dev` or **Deploy**."""),
]
