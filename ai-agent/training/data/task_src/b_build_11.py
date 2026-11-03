"""Category B (build / add), batch 11: on-premises only. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
CLUSTERS = json.dumps({"clusters": {"prod": {"orchestrator": "swarm", "master": "app-1", "servers": ["app-2", "app-3"]}}},
                      indent=2)


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", provider="onprem", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 201
    B(201, stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: notes-api
provider:
  name: onprem
  region: local
  options:
    port: 8201
functions: {}
""",
          "requirements.txt": ""}),
      user="ANY /notes/{id}: GET returns note, PUT replaces, everything else 405",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/notes.py`: branch on event.http.method, MethodNotAllowed otherwise, NotFound for unknown ids on GET",
                                   "Add `note` on ANY /notes/{id}", "Validate, invoke PUT then DELETE"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/notes.py", content=FUTURE + """from py_serverless_kit import MethodNotAllowed, NotFound

NOTES = {"1": {"id": "1", "text": "first"}}


def note(event, ctx):
    note_id = event.http.path_params.get("id", "")
    method = event.http.method
    if method == "GET":
        if note_id not in NOTES:
            raise NotFound(f"note {note_id} not found")
        return NOTES[note_id]
    if method == "PUT":
        NOTES[note_id] = {"id": note_id, "text": (event.http.json(default={}) or {}).get("text", "")}
        return NOTES[note_id]
    raise MethodNotAllowed(f"{method} is not allowed on /notes/{{id}}")
"""),
          S("set_config", path="functions.note", value={"handler": "app.notes.note", "events": [{"http": "ANY /notes/{id}"}]}),
          S("invoke_local", function="note", method="PUT", path="/notes/2", data={"text": "second"}),
          S("invoke_local", function="note", method="DELETE", path="/notes/2"),
      ],
      final="""Added `note` on `ANY /notes/{id}`. The handler branches on `event.http.method`, and anything other than GET/PUT raises `MethodNotAllowed` (405) [docs/handlers.md#errors].

- validate (onprem, staging): valid.
- `PUT /notes/2 {"text": "second"}`: 200, `{"id": "2", "text": "second"}`.
- `DELETE /notes/2`: 405.

Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 202
    B(202, stage="prod", mode="ask", page="Load balancers", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response", "docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: storefront
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8202
functions:
  home:
    handler: app.store.home
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/store.py": FUTURE + """

def home(event, ctx):
    return "welcome"
""",
          "requirements.txt": ""}),
      user="need /healthz for our load balancer monitor. normally 200 ok, but when i set MAINTENANCE=1 at deploy it must give 503 so traffic goes away",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/health.py`: (body, 503) when MAINTENANCE is 1, else {status: ok}",
                                   "Add `healthz` on GET /healthz with MAINTENANCE: ${env:MAINTENANCE, 0}",
                                   "Validate (onprem, prod), call /healthz"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/health.py", content=FUTURE + """

def healthz(event, ctx):
    if ctx.env.get("MAINTENANCE", "0") == "1":
        return {"status": "maintenance"}, 503
    return {"status": "ok"}
"""),
          S("set_config", path="functions.healthz",
            value={"handler": "app.health.healthz", "environment": {"MAINTENANCE": "${env:MAINTENANCE, 0}"},
                   "events": [{"http": "GET /healthz"}]}),
          S("invoke_local", function="healthz", method="GET", path="/healthz"),
      ],
      final="""Done. `healthz` on `GET /healthz`:

- normally 200 `{"status": "ok"}`;
- with `MAINTENANCE=1` it returns `({"status": "maintenance"}, 503)`, the tuple form for a status code [docs/handlers.md#returning-a-response].

`MAINTENANCE: ${env:MAINTENANCE, 0}` takes the value from your shell when you deploy, with `0` as the default [docs/configuration.md#variables].

- `pskit validate` (onprem, prod): valid.
- Local `GET /healthz`: 200, `{"status": "ok"}`.

Maintenance mode: run `MAINTENANCE=1 pskit deploy -s prod`, then deploy again without it to come back. (pskit's own `/__pskit/health` stays as it is.) Point your load balancer monitor at `/healthz`."""),

    # ------------------------------------------------------------------ 203
    B(203, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: products
provider:
  name: onprem
  region: local
  options:
    port: 8203
functions: {}
""",
          "requirements.txt": ""}),
      user="i have 95 products and the list is too long. can the list come in pages, like 20 at a time?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/products.py`: read ?page (default 1) and ?size (default 20, max 100) from the query, return that slice plus totals",
                                   "Add function `list-products` on GET /products",
                                   "Validate for onprem and ask for page 5"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/products.py", content=FUTURE + """from py_serverless_kit import BadRequest

PRODUCTS = [{"id": i, "name": f"Product {i}"} for i in range(1, 96)]


def list_products(event, ctx):
    q = event.http.query
    try:
        page = int(q.get("page", "1"))
        size = int(q.get("size", "20"))
    except ValueError:
        raise BadRequest("page and size must be numbers")
    if page < 1 or not 1 <= size <= 100:
        raise BadRequest("page must be >= 1 and size 1-100")
    start = (page - 1) * size
    pages = (len(PRODUCTS) + size - 1) // size
    return {"page": page, "pages": pages, "total": len(PRODUCTS), "items": PRODUCTS[start:start + size]}
"""),
          S("set_config", path="functions.list-products",
            value={"handler": "app.products.list_products", "events": [{"http": "GET /products"}]}),
          S("invoke_local", function="list-products", method="GET", path="/products?page=5"),
      ],
      final="""Yes. `GET /products` now returns one page at a time:

- `?page=1` (default) gives products 1-20, `?page=2` gives 21-40, and so on;
- `?size=` changes the page size (1-100). Bad values give 400 [docs/handlers.md#errors];
- every answer also says how many `pages` and products (`total`) there are.

Checks:
- `pskit validate` (onprem): valid.
- `/products?page=5`: 200, `"page": 5, "pages": 5, "total": 95`, with products 81-95 (the last page has 15).

The 95 products are sample data. Test another page: `pskit invoke -f list-products --method GET --path "/products?page=2&size=50"`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 204
    B(204, stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#record", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: support-jobs
provider:
  name: onprem
  region: local
  options:
    port: 8204
functions: {}
""",
          "requirements.txt": ""}),
      user="We have two built-in queues, `jobs-urgent` and `jobs-normal`. One function `handle-job` should consume both: urgent with batch 1 so it reacts immediately, normal with batch 25. In the logs I want to see which queue a record came from.",
      steps=[
          S("get_project"),
          S("search_docs", query="record source which queue attributes",
            docs=[D("docs/handlers.md", "record", words=120)]),
          S("propose_plan", steps=["Write `app/jobs.py`: log record.source and the job id for every record",
                                   "Add `handle-job` with two queue events: {name: jobs-urgent, batch_size: 1} and {name: jobs-normal, batch_size: 25}",
                                   "Validate (onprem, prod) and invoke with a record"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/jobs.py", content=FUTURE + """

def handle_job(event, ctx):
    for record in event.records:
        job = record.json(default={}) or {}
        ctx.logger.info("job", extra={"queue": record.source, "job": job.get("id")})
    return {"handled": len(event.records)}
"""),
          S("set_config", path="functions.handle-job",
            value={"handler": "app.jobs.handle_job",
                   "events": [{"queue": {"name": "jobs-urgent", "batch_size": 1}},
                              {"queue": {"name": "jobs-normal", "batch_size": 25}}]}),
          S("invoke_local", function="handle-job", type="queue", data=[{"id": "J-1"}]),
      ],
      final="""Added `handle-job` with one queue event per queue:

```yaml
functions:
  handle-job:
    handler: app.jobs.handle_job
    events:
      - queue: {name: jobs-urgent, batch_size: 1}
      - queue: {name: jobs-normal, batch_size: 25}
```

Each record's `source` is logged, so you can see where it came from [docs/handlers.md#record].

- `pskit validate` (onprem, prod): valid.
- Local invoke with one job: `{"handled": 1}`. The local test event has no real queue behind it, so check the `queue` field in **Logs** after deploy to confirm the value you get there.

Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. Then enqueue with `POST /__pskit/queues/jobs-urgent`."""),

    # ------------------------------------------------------------------ 205
    B(205, stage="staging", mode="auto", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: transcode
provider:
  name: onprem
  region: local
  options:
    port: 8205
functions: {}
""",
          "requirements.txt": ""}),
      user="On SQS we set VisibilityTimeout 600 because a transcode takes up to 2 minutes and we got duplicates otherwise. Lambda timeout was 120. Same for `transcode` on the built-in queue `videos`, one video per call.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/transcode.py` (logs the video id)",
                                   "Add `transcode` (timeout 120) with queue {name: videos, batch_size: 1, visibility_timeout: 600}",
                                   "Validate (onprem, staging), invoke"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/transcode.py", content=FUTURE + """

def transcode(event, ctx):
    for record in event.records:
        video = record.json(default={}) or {}
        ctx.logger.info("transcode", extra={"video": video.get("video_id"),
                                            "remaining_ms": ctx.remaining_time_ms()})
    return {"done": len(event.records)}
"""),
          S("set_config", path="functions.transcode",
            value={"handler": "app.transcode.transcode", "timeout": 120,
                   "events": [{"queue": {"name": "videos", "batch_size": 1, "visibility_timeout": 600}}]}),
          S("invoke_local", function="transcode", type="queue", data=[{"video_id": "v-77"}]),
      ],
      final="""Same settings, pskit names:

```yaml
functions:
  transcode:
    handler: app.transcode.transcode
    timeout: 120
    events:
      - queue: {name: videos, batch_size: 1, visibility_timeout: 600}
```

The built-in queue honours `visibility_timeout` (without it, the default would be `max(30, 6 x timeout)` = 720) [docs/providers.md#onprem-on-premises].

One difference from Lambda: the host does not kill a handler at `timeout`. `ctx.remaining_time_ms()` still counts down, so check it yourself if you need to stop early.

- validate (onprem, staging): valid.
- invoke with one video: `{"done": 1}`.

Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 206
    B(206, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: feeds
provider:
  name: onprem
  region: local
  options:
    port: 8206
functions:
  refresh-feeds:
    handler: app.feeds.refresh
""",
          "app/__init__.py": "",
          "app/feeds.py": FUTURE + """

def refresh(event, ctx):
    ctx.logger.info("refresh feeds")
    return {"refreshed": True}
""",
          "requirements.txt": ""}),
      user="refresh-feeds every 90 minutes. cron cant do 90 min right? is it possible here",
      steps=[
          S("get_project"),
          S("search_docs", query="schedule rate not cron on premises minutes",
            docs=[D("docs/providers.md", "onprem-on-premises", start="| schedule |", end="evaluated in UTC |")]),
          S("propose_plan", steps=["Add `- schedule: 90 minutes` to refresh-feeds", "Validate for onprem, run schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.refresh-feeds.events", value=[{"schedule": "90 minutes"}]),
          S("invoke_local", function="refresh-feeds", type="schedule"),
      ],
      final="""Right, a 5-field cron can't say "every 90 minutes", but a **rate** can, and on premises any positive number of minutes, hours or days works, including values that cron can't express [docs/providers.md#onprem-on-premises]:

```yaml
functions:
  refresh-feeds:
    events:
      - schedule: 90 minutes
```

- `pskit validate` (onprem): valid.
- Local schedule run: `{"refreshed": true}`.

The count starts when the host starts. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 207
    B(207, stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: billing-ny
provider:
  name: onprem
  region: local
  options:
    port: 8207
functions:
  monthly-invoices:
    handler: app.billing.monthly
""",
          "app/__init__.py": "",
          "app/billing.py": FUTURE + """

def monthly(event, ctx):
    ctx.logger.info("monthly invoices")
    return {"invoices": "created"}
""",
          "requirements.txt": ""}),
      user="our office is in new york. monthly-invoices should run on the 1st of every month at 9 in the morning, new york time",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add schedule cron `0 9 1 * *` with timezone America/New_York",
                                   "Validate for onprem (prod) and run it once locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.monthly-invoices.events",
            value=[{"schedule": {"cron": "0 9 1 * *", "timezone": "America/New_York"}}]),
          S("invoke_local", function="monthly-invoices", type="schedule"),
      ],
      final="""Done. `monthly-invoices` runs at 09:00 New York time on the 1st of every month:

```yaml
- schedule: {cron: "0 9 1 * *", timezone: America/New_York}
```

The five fields mean minute 0, hour 9, day 1, every month, any weekday [docs/events.md#schedule].

- `pskit validate` (onprem, prod): valid, with one warning: this computer has no timezone database, so it would use UTC for now. `pskit deploy` adds `tzdata` to the host, so the deployed schedule uses New York time [docs/providers.md#onprem-on-premises].
- Run once locally: `{"invoices": "created"}`.

Deploy: **Deploy** page (prod asks you to type a confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 208
    B(208, stage="staging", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={
          "pskit.yml": """service: clickstream
provider:
  name: onprem
  region: local
  options:
    port: 8208
functions: {}
""",
          "requirements.txt": ""}),
      user="consume redis stream `clicks` (consumer group analytics) from CLICKS_REDIS_URL, fn `aggregate-clicks` batch 100, trim ~100k",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.clicks: queue, external, options {driver: redis_stream, url_env: CLICKS_REDIS_URL, key: clicks, group: analytics, maxlen: 100000}",
                                   "Write `app/clicks.py`; add `aggregate-clicks` with queue {resource: clicks, batch_size: 100}", "Validate, invoke"]),
          S("set_config", path="resources.clicks",
            value={"type": "queue", "external": True,
                   "options": {"driver": "redis_stream", "url_env": "CLICKS_REDIS_URL", "key": "clicks",
                               "group": "analytics", "maxlen": 100000}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/clicks.py", content=FUTURE + """from collections import Counter


def aggregate(event, ctx):
    pages = Counter((r.json(default={}) or {}).get("page") for r in event.records)
    ctx.logger.info("clicks", extra={"pages": dict(pages)})
    return {"pages": dict(pages)}
"""),
          S("set_config", path="functions.aggregate-clicks",
            value={"handler": "app.clicks.aggregate", "events": [{"queue": {"resource": "clicks", "batch_size": 100}}]}),
          S("invoke_local", function="aggregate-clicks", type="queue", data=[{"page": "/"}, {"page": "/pricing"}, {"page": "/"}]),
      ],
      final="""Done:

```yaml
resources:
  clicks:
    type: queue
    external: true
    options: {driver: redis_stream, url_env: CLICKS_REDIS_URL, key: clicks, group: analytics, maxlen: 100000}
functions:
  aggregate-clicks:
    handler: app.clicks.aggregate
    events:
      - queue: {resource: clicks, batch_size: 100}
```

Entries stay pending in the group until settled. One idle longer than `visibility_timeout` is taken over with `XAUTOCLAIM`. `maxlen` is an approximate trim. Needs Redis 6.2+ or Valkey [docs/resources.md#queue-drivers].

- validate (onprem, staging): valid.
- invoke with 3 clicks: `{"pages": {"/": 2, "/pricing": 1}}`.

Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 209
    B(209, stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#topic", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: catalog-events
provider:
  name: onprem
  region: local
  options:
    port: 8209
functions: {}
""",
          "requirements.txt": ""}),
      user="messages on topic `products` look like this:\n\n{\"event_type\": \"product.updated\", \"sku\": \"SKU-19\", \"price\": 12.5}\n{\"event_type\": \"product.deleted\", \"sku\": \"SKU-20\"}\n\nI need a `search-index` subscriber only for product.created and product.updated, not deletes.",
      steps=[
          S("get_project"),
          S("search_docs", query="topic filter list of values json body fields",
            docs=[D("docs/providers.md", "onprem-on-premises", start="| topic |", end="JSON body fields |")]),
          S("propose_plan", steps=["Write `app/search_index.py`: log sku + event_type per record",
                                   "Add `search-index` with topic {name: products, filter: {event_type: [product.created, product.updated]}}",
                                   "Validate for onprem, invoke with your updated message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/search_index.py", content=FUTURE + """

def index(event, ctx):
    skus = []
    for record in event.records:
        msg = record.json(default={}) or {}
        ctx.logger.info("reindex", extra={"sku": msg.get("sku"), "event": msg.get("event_type")})
        skus.append(msg.get("sku"))
    return {"reindexed": skus}
"""),
          S("set_config", path="functions.search-index",
            value={"handler": "app.search_index.index",
                   "events": [{"topic": {"name": "products",
                                         "filter": {"event_type": ["product.created", "product.updated"]}}}]}),
          S("invoke_local", function="search-index", type="topic",
            data=[{"event_type": "product.updated", "sku": "SKU-19", "price": 12.5}]),
      ],
      final="""Added `search-index`:

```yaml
- topic: {name: products, filter: {event_type: [product.created, product.updated]}}
```

Your messages carry `event_type` in the JSON body. On premises the filter is checked on the attributes first, then on the JSON body fields, so `product.deleted` never reaches this function [docs/providers.md#onprem-on-premises].

- `pskit validate` (onprem): valid.
- Local invoke with your `product.updated` message: `{"reindexed": ["SKU-19"]}`.

(A local invoke calls the function directly and skips the filter. The host applies it after deploy.) Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 210
    B(210, stage="staging", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": """service: newsletter-in
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8210
resources:
  replies-mail:
    type: smtp
    external: true
    connection: {host: 203.0.113.70, port: 25, domains: replies.example.com, hostname: mail.replies.example.com}
functions: {}
""",
          "requirements.txt": ""}),
      user="replies to our newsletter come to replies.example.com. many are html only. function save-reply must give plain text always (strip html), with sender and subject",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/replies.py`: use mail text, else strip tags from html with html.parser (stdlib)",
                                   "Add `save-reply` with `- smtp: {resource: replies-mail}`",
                                   "Validate (onprem, staging), run an html-only test mail"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/replies.py", content=FUTURE + """from html.parser import HTMLParser


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _plain(html):
    parser = _Text()
    parser.feed(html or "")
    return " ".join(" ".join(parser.parts).split())


def save_reply(event, ctx):
    mail = event.data or {}
    text = (mail.get("text") or "").strip() or _plain(mail.get("html"))
    return {"from": mail.get("from"), "subject": mail.get("subject"), "text": text}
"""),
          S("set_config", path="functions.save-reply",
            value={"handler": "app.replies.save_reply", "events": [{"smtp": {"resource": "replies-mail"}}]}),
          S("invoke_local", function="save-reply", type="smtp",
            data={"from": "reader@example.org", "to": ["news@replies.example.com"], "subject": "Re: November news",
                  "text": "", "html": "<p>Thanks!</p><p>Please <b>unsubscribe</b> me.</p>"}),
      ],
      final="""Added `save-reply` on `replies-mail`. It uses `text` when the mail has one, and otherwise strips the tags from `html` with Python's built-in `html.parser`, so nothing extra is needed in requirements.txt. A mail without a text part has `text: ""` [docs/smtp/README.md#what-the-handler-receives].

- `pskit validate` (onprem, staging): valid.
- HTML-only test mail: `{"from": "reader@example.org", "subject": "Re: November news", "text": "Thanks! Please unsubscribe me."}`.

Deploy: **Deploy** page or `pskit deploy -s staging`. Then the host knows the trigger, and you can test with **Test** or a real reply."""),

    # ------------------------------------------------------------------ 211
    B(211, stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": """service: onboarding
provider:
  name: onprem
  region: local
  options:
    port: 8211
functions:
  create-account:
    handler: app.onboard.create_account
    events:
    - http: POST /accounts
  send-welcome-kit:
    handler: app.onboard.send_kit
""",
          "app/__init__.py": "",
          "app/onboard.py": FUTURE + """

def create_account(event, ctx):
    body = event.http.json(default={}) if event.is_http else dict(event.data or {})
    return {"account": (body or {}).get("email"), "created": True}


def send_kit(event, ctx):
    return {**(event.data or {}), "kit": "sent"}
""",
          "requirements.txt": ""}),
      user="Workflow `onboard` = create-account then send-welcome-kit, 10-minute limit, with a description. Important: POST /accounts is also used by our admin tool to create test accounts, and those must NOT start the workflow. Only explicit starts.",
      steps=[
          S("get_project"),
          S("search_docs", query="start_on_entry false workflow first task http",
            docs=[D("docs/workflows.md", "workflow-keys", start="| `options.start_on_entry` |", end="(see below) |"),
                  D("docs/workflows.md", "embedded-orchestrator", start="- On premises, a workflow whose first state is a `task`", end="Other clouds don't do this: start the workflow itself there.")]),
          S("propose_plan", steps=["Add workflow `onboard`: description, timeout 600, options.start_on_entry: false; Create (create-account) -> Kit (send-welcome-kit, end)",
                                   "Validate (onprem, prod), invoke send-welcome-kit as a task"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.onboard",
            value={"description": "New customer: account, then welcome kit", "timeout": 600,
                   "options": {"start_on_entry": False}, "start_at": "Create",
                   "states": {"Create": {"type": "task", "function": "create-account", "next": "Kit"},
                              "Kit": {"type": "task", "function": "send-welcome-kit", "end": True}}}),
          S("invoke_local", function="send-welcome-kit", type="workflow", data={"account": "new@example.com", "created": True}),
      ],
      final="""Added `onboard`:

```yaml
workflows:
  onboard:
    description: "New customer: account, then welcome kit"
    timeout: 600
    options: {start_on_entry: false}
    start_at: Create
    states:
      Create: {type: task, function: create-account, next: Kit}
      Kit:    {type: task, function: send-welcome-kit, end: true}
```

`start_on_entry: false` matters here. On premises a workflow whose first task is `create-account` would otherwise also start every time `POST /accounts` is called on its own [docs/workflows.md#embedded-orchestrator]. Now the admin tool's test accounts don't start it. `timeout: 600` is also enforced by the engine (the run ends `TIMED_OUT`) [docs/workflows.md#workflow-keys].

- `pskit validate` (onprem, prod): valid (embedded engine).
- `send-welcome-kit` as a task: `"kit": "sent"`.

Start it explicitly with `POST /workflows/onboard` (body = the account data). Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 212
    B(212, stage="staging", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: lab-portal
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8212
functions:
  home:
    handler: app.portal.home
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/portal.py": FUTURE + """

def home(event, ctx):
    return "lab portal"
""",
          "requirements.txt": ""}),
      user="our lab server 198.51.100.7 (user labadmin) only lets me log in with a password, no key. I'm on Linux. How can pskit deploy there? I don't want the password in the yml",
      steps=[
          S("get_project"),
          S("search_docs", query="ssh password login sshpass password_file",
            docs=[D("docs/providers.md", "onprem-on-premises", start="SSH login options, for `ssh`, `scp` and remote `docker`", end="sshpass is not available on Windows")]),
          S("propose_plan", steps=["provider.options.deploy: {method: ssh, host: 198.51.100.7, user labadmin, password_file /etc/pskit/lab.pass, python bundle}",
                                   "Validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy",
            value={"method": "ssh", "host": "198.51.100.7", "user": "labadmin", "password_file": "/etc/pskit/lab.pass",
                   "python": "bundle"}),
      ],
      final="""pskit can log in with a password through **sshpass**, with the password in a file, not in pskit.yml. I set `provider.options.deploy` to `method: ssh`, `host: 198.51.100.7`, `user: labadmin`, `python: bundle`, and `password_file` to `/etc/pskit/lab.pass`.

The password never appears on a command line, in `pskit_host.json` or in Terraform state [docs/providers.md#onprem-on-premises]. `python: bundle` ships Python with the app, in case the server has none.

`pskit validate` (onprem, staging): valid, with one warning: `/etc/pskit/lab.pass` doesn't exist yet, and it is needed at deploy.

What you do once:
1. Install `sshpass` (for example `sudo apt install sshpass`).
2. Put the password alone in `/etc/pskit/lab.pass`, readable only by the user that runs pskit (`chmod 600`).

Then deploy: **Deploy** page or `pskit deploy -s staging`. (Alternatively, `auth: password` plus the `SSHPASS` variable works too.)"""),

    # ------------------------------------------------------------------ 213
    B(213, stage="prod", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: edge-proxy
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8213
functions:
  ping:
    handler: app.proxy.ping
    events:
    - http: GET /ping
""",
          "app/__init__.py": "",
          "app/proxy.py": FUTURE + """

def ping(event, ctx):
    return "pong"
""",
          "requirements.txt": ""}),
      user="ssh deploy to 203.0.113.80 port 2222 user ops, strict host keys from ./known_hosts.prod, path /srv/edge-proxy, systemd w/ sudo, bundled python",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["deploy: {method: ssh, host: 203.0.113.80, port: 2222, user: ops, known_hosts: ./known_hosts.prod, path: /srv/edge-proxy, python: bundle, install: systemd, sudo: true}",
                                   "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.deploy",
            value={"method": "ssh", "host": "203.0.113.80", "port": 2222, "user": "ops", "known_hosts": "./known_hosts.prod",
                   "path": "/srv/edge-proxy", "python": "bundle", "install": "systemd", "sudo": True}),
      ],
      final="""Set:

```yaml
provider:
  options:
    deploy:
      method: ssh
      host: 203.0.113.80
      port: 2222
      user: ops
      known_hosts: ./known_hosts.prod
      path: /srv/edge-proxy
      python: bundle
      install: systemd
      sudo: true
```

`known_hosts` takes `accept-new`, `ignore` or a path to a known_hosts file. With a path, a changed host key fails the deploy [docs/providers.md#onprem-on-premises]. No key is set, so the SSH agent / default key is used.

validate (onprem, prod): valid.

Make sure `known_hosts.prod` has the server's `[203.0.113.80]:2222` entry. Deploy: `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 214
    B(214, stage="prod", mode="ask", page="Cluster", persona="informal_non_native",
      sources=["docs/cluster.md#set-up", "docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    cluster: {name: prod, replicas: 2}
functions:
  web:
    handler: app.web.home
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/web.py": FUTURE + """

def home(event, ctx):
    return {"shop": "open"}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="black friday next week!! shop need more copies, make 6 web replicas",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.cluster.replicas: 2 -> 6", "Validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.cluster.replicas", value=6),
      ],
      final="""Done: `cluster: {name: prod, replicas: 6}`. That is 6 web replicas plus the main replica, each reserving the default 0.25 CPU and 256 MB [docs/cluster.md#set-up].

`pskit validate` (onprem, prod): valid.

It changes on the next deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. Before Black Friday, check that the 3 servers have room: `pskit cluster status prod` shows CPU, memory and any replica that "cannot be placed". If they're full, add a server with `pskit cluster join prod SERVER` [docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full]. Remember to go back to 2 replicas afterwards."""),

    # ------------------------------------------------------------------ 215
    B(215, stage="prod", mode="ask", page="Cluster", persona="pasted_error",
      sources=["docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    cluster: {name: prod, replicas: 6, cpu: 0.5, memory: 512}
functions:
  web:
    handler: app.web.home
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/web.py": FUTURE + """

def home(event, ctx):
    return {"shop": "open"}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="  workload pskit-shop-prod_web: 4/6 running\n  pending  pskit-shop-prod_web.5: no suitable node (insufficient resources on 3 nodes)\nFULL: all 3 server(s) are over a capacity limit; 2 replica(s) cannot be placed. Add a server: pskit cluster join prod SERVER\n\nnew server comes only next month. make it fit for now",
      steps=[
          S("get_project"),
          S("search_docs", query="cluster full replicas cannot be placed",
            docs=[D("docs/cluster.md", "monitor-scale-and-add-servers-when-it-is-full", words=160)]),
          S("ask_user", question="4 of 6 web replicas fit. Should I lower replicas to 4 (same size each), or keep 6 but make each smaller (0.25 CPU, 256 MB)?",
            options=["replicas 4, same size", "keep 6, smaller replicas"], answer="replicas 4, same size"),
          S("propose_plan", steps=["provider.options.cluster.replicas: 6 -> 4 (cpu 0.5 / memory 512 unchanged)", "Validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.cluster.replicas", value=4),
      ],
      final="""Set `replicas: 4` and kept 0.5 CPU and 512 MB each. The status showed exactly 4 running, so after the next deploy nothing stays pending.

`pskit validate` (onprem, prod): valid.

Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`, then check with `pskit cluster status prod`. When the new server arrives: `pskit cluster join prod <server>` (save it first in **Resources** > **+ On-prem service** > Servers), then set `replicas` back to 6 [docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full]."""),

    # ------------------------------------------------------------------ 216
    B(216, stage="prod", mode="auto", page="Load balancers", persona="terse_expert",
      sources=["docs/placement.md#deploy-urls-and-load-balancers", "docs/load-balancers.md#create-one-and-put-projects-on-it"],
      project=dict(files={
          "pskit.yml": """service: docscan
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-1}
        vision: {server: app-3, functions: [ocr]}
functions:
  api:
    handler: app.api.submit
    events:
    - http: POST /scan
  ocr:
    handler: functions.ocr.handler.main
    events:
    - http: POST /ocr
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def submit(event, ctx):
    return {"queued": True}
""",
          "functions/__init__.py": "",
          "functions/ocr/__init__.py": "",
          "functions/ocr/handler.py": FUTURE + """

def main(event, ctx):
    return {"text": ""}
""",
          "functions/ocr/requirements.txt": "",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="one url for docscan on lb edge, path docscan; both groups behind it",
      steps=[
          S("get_project"),
          S("search_docs", query="balancer placement gateway groups one route",
            docs=[D("docs/placement.md", "deploy-urls-and-load-balancers", start="With `options.balancer: edge`", end="passed on to the right group.")]),
          S("propose_plan", steps=["provider.options.balancer: {name: edge, path: docscan}", "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.balancer", value={"name": "edge", "path": "docscan"}),
      ],
      final="""Set `balancer: {name: edge, path: docscan}`. With a balancer, `placement.gateway` is on by default: edge gets one route, `/docscan/`, to the servers of **both** groups, and a request that lands on the wrong group is passed on [docs/placement.md#deploy-urls-and-load-balancers]. So `http://edge/docscan/ocr` works from either server.

validate (onprem, prod): valid.

The groups need an address edge can reach. If app-1/app-3's saved address isn't it, set `advertise` per group. Deploy: `pskit deploy -s prod`, then `pskit lb status edge`."""),

    # ------------------------------------------------------------------ 217
    B(217, stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/configuration.md#variables", "docs/resources.md#fields"],
      project=dict(files={
          "pskit.yml": """service: timesheets
provider:
  name: onprem
  region: local
  options:
    port: 8217
functions:
  entries:
    handler: app.ts.entries
    events:
    - http: GET /entries
""",
          "app/__init__.py": "",
          "app/ts.py": FUTURE + """

def entries(event, ctx):
    return []
""",
          "requirements.txt": ""}),
      user="db host is different on every pc of the team (TS_DB_HOST env), if not set use localhost. port 5432 db timesheets, password TS_DB_PASSWORD. connect it to entries",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add resources.ts-db: database, external, connection {host: ${env:TS_DB_HOST, localhost}, port 5432, database timesheets, password_env TS_DB_PASSWORD}, functions [entries]",
                                   "`entries` returns the db it uses", "Validate for onprem, call GET /entries"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.ts-db",
            value={"type": "database", "external": True,
                   "connection": {"host": "${env:TS_DB_HOST, localhost}", "port": 5432, "database": "timesheets",
                                  "password_env": "TS_DB_PASSWORD"},
                   "functions": ["entries"]}),
          S("write_file", path="app/ts.py", content=FUTURE + """from py_serverless_kit import resource


def entries(event, ctx):
    db = resource("ts-db")
    return {"db": f'{db["host"]}:{db["port"]}/{db["database"]}', "entries": []}
"""),
          S("validate"),
          S("invoke_local", function="entries", method="GET", path="/entries"),
      ],
      final="""Done:

```yaml
resources:
  ts-db:
    type: database
    external: true
    connection:
      host: ${env:TS_DB_HOST, localhost}
      port: 5432
      database: timesheets
      password_env: TS_DB_PASSWORD
    functions: [entries]
```

`${env:TS_DB_HOST, localhost}` takes each person's `TS_DB_HOST`, or `localhost` when it isn't set [docs/configuration.md#variables]. The password is only named (`password_env`), never written in the file.

- `pskit validate` (onprem): valid.
- `GET /entries`: 200, `{"db": "localhost:5432/timesheets", "entries": []}`, because `TS_DB_HOST` is not set here.

Deploy: **Deploy** page or `pskit deploy -s dev`. The host value is taken on the machine that deploys."""),

    # ------------------------------------------------------------------ 218
    B(218, stage="staging", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#storage-drivers"],
      project=dict(files={
          "pskit.yml": """service: assets
provider:
  name: onprem
  region: local
  options:
    port: 8218
functions: {}
""",
          "requirements.txt": ""}),
      user="we use Ceph with an S3 address http://ceph.example.com:7480, bucket `assets`. when someone uploads, a function should log it. keys are in CEPH_KEY and CEPH_SECRET",
      steps=[
          S("get_project"),
          S("search_docs", query="ceph s3 driver endpoint path style",
            docs=[D("docs/resources.md", "storage-drivers", start="Ceph RGW, SeaweedFS", end="(path-style by default).")]),
          S("propose_plan", steps=["Add resources.assets: storage, external, name assets, options {driver: s3, endpoint: http://ceph.example.com:7480, access_key_env: CEPH_KEY, secret_key_env: CEPH_SECRET}",
                                   "Write `app/assets.py`; add `on-asset` with storage {resource: assets, events: [created]}",
                                   "Validate (onprem, staging), invoke"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.assets",
            value={"type": "storage", "external": True, "name": "assets",
                   "options": {"driver": "s3", "endpoint": "http://ceph.example.com:7480",
                               "access_key_env": "CEPH_KEY", "secret_key_env": "CEPH_SECRET"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/assets.py", content=FUTURE + """

def on_asset(event, ctx):
    for record in event.records:
        ctx.logger.info("asset uploaded", extra={"key": record.key, "size": record.size})
    return {"assets": [r.key for r in event.records]}
"""),
          S("set_config", path="functions.on-asset",
            value={"handler": "app.assets.on_asset", "events": [{"storage": {"resource": "assets", "events": ["created"]}}]}),
          S("invoke_local", function="on-asset", type="storage",
            data={"bucket": "assets", "key": "logos/new-logo.svg", "size": 5120, "action": "created"}),
      ],
      final="""Done. Ceph speaks S3, so it uses the `s3` driver with your endpoint (path-style by default) [docs/resources.md#storage-drivers]:

```yaml
resources:
  assets:
    type: storage
    external: true
    name: assets
    options:
      driver: s3
      endpoint: http://ceph.example.com:7480
      access_key_env: CEPH_KEY
      secret_key_env: CEPH_SECRET
functions:
  on-asset:
    handler: app.assets.on_asset
    events:
      - storage: {resource: assets, events: [created]}
```

The host checks the bucket regularly and runs `on-asset` for each new file. The keys are read from `CEPH_KEY` / `CEPH_SECRET` on the server.

- `pskit validate` (onprem, staging): valid.
- Test upload: `{"assets": ["logos/new-logo.svg"]}`.

If the bucket is big, add `prefix` to watch one folder only. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 219
    B(219, stage="prod", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: reports
provider:
  name: onprem
  region: local
  options:
    port: 8219
functions:
  on-report:
    handler: app.reports.on_report
    events:
    - storage: reports
""",
          "app/__init__.py": "",
          "app/reports.py": FUTURE + """

def on_report(event, ctx):
    return {"bucket": event.records[0].bucket if event.records else None}
""",
          "requirements.txt": ""}),
      user="bucket per stage: reports-<stage> via ${opt:stage}",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.on-report.events.0.storage: reports-${opt:stage}", "Validate (onprem, prod)"]),
          S("set_config", path="functions.on-report.events.0.storage", value="reports-${opt:stage}"),
      ],
      final="""Set `- storage: reports-${opt:stage}`. `${opt:stage}` is the effective stage, so prod watches `reports-prod`, staging `reports-staging`, and so on [docs/configuration.md#variables].

validate (onprem, prod): valid.

Deploy: `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 220
    B(220, stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: tickets-gate
provider:
  name: onprem
functions: {}
""",
          "requirements.txt": ""}),
      user="New on-prem project for the event entrance on a laptop at the door (port 8220, scanners on the same Wi-Fi): GET /tickets/{code} says whether a ticket is valid and unused; POST /tickets/{code}/use marks it used, 404 for unknown codes, 409 when already used.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider: region local, options host 0.0.0.0, port 8220",
                                   "Write `app/gate.py` with `check` and `use` (NotFound / Conflict)",
                                   "Add `check-ticket` on GET /tickets/{code} and `use-ticket` on POST /tickets/{code}/use",
                                   "Validate for onprem, use a ticket locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.region", value="local"),
          S("set_config", path="provider.options", value={"host": "0.0.0.0", "port": 8220}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/gate.py", content=FUTURE + """from py_serverless_kit import Conflict, NotFound

TICKETS = {"A1B2": {"used": False}, "C3D4": {"used": False}}


def _ticket(event):
    code = event.http.path_params.get("code", "").upper()
    if code not in TICKETS:
        raise NotFound(f"unknown ticket {code}")
    return code, TICKETS[code]


def check(event, ctx):
    code, ticket = _ticket(event)
    return {"code": code, "valid": not ticket["used"]}


def use(event, ctx):
    code, ticket = _ticket(event)
    if ticket["used"]:
        raise Conflict(f"ticket {code} was already used")
    ticket["used"] = True
    return {"code": code, "admitted": True}
"""),
          S("set_config", path="functions",
            value={"check-ticket": {"handler": "app.gate.check", "events": [{"http": "GET /tickets/{code}"}]},
                   "use-ticket": {"handler": "app.gate.use", "events": [{"http": "POST /tickets/{code}/use"}]}}),
          S("invoke_local", function="use-ticket", method="POST", path="/tickets/a1b2/use"),
      ],
      final="""The entrance project is set up on this laptop:

```yaml
provider:
  name: onprem
  region: local
  options: {host: 0.0.0.0, port: 8220}
functions:
  check-ticket:
    handler: app.gate.check
    events:
      - http: GET /tickets/{code}
  use-ticket:
    handler: app.gate.use
    events:
      - http: POST /tickets/{code}/use
```

- `pskit validate` (onprem): valid.
- Local `POST /tickets/a1b2/use`: 200, `{"code": "A1B2", "admitted": true}`. Codes are upper-cased.
- Unknown code gives 404, a second use gives 409 [docs/handlers.md#errors].

`host: 0.0.0.0` lets the scanners on the Wi-Fi reach port 8220. The two tickets are sample data, and "used" is kept in memory only, so a restart re-opens tickets. Load real tickets and persist them before the event.

Start it: **Deploy** page or `pskit deploy -s dev`."""),
]
