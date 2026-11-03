"""Category B (build / add), batch 26 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 501
    B(501, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#variables", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: payments-hooks
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="need webhook POST /hooks/payment. provider sign body with hmac sha256 in header x-signature. secret must not be in yml, it come from env WEBHOOK_SECRET",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/hooks.py`: HMAC-SHA256 of the raw body with WEBHOOK_SECRET, compare with x-signature, 401 if wrong",
                                   "Add function `payment-hook` on POST /hooks/payment with environment WEBHOOK_SECRET: ${env:WEBHOOK_SECRET, change-me}",
                                   "Validate for aws, invoke without a signature (expect 401)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/hooks.py", content=FUTURE + """import hashlib
import hmac

from py_serverless_kit import Unauthorized


def payment_hook(event, ctx):
    signing_key = ctx.env.get("WEBHOOK_SECRET", "").encode()
    body = event.http.text().encode()
    expected = hmac.new(signing_key, body, hashlib.sha256).hexdigest()
    given = event.http.headers.get("x-signature", "")
    if not hmac.compare_digest(expected, given):
        raise Unauthorized("bad signature")
    payment = event.http.json(default={}) or {}
    ctx.logger.info("payment webhook", extra={"id": payment.get("id")})
    return {"received": True}
"""),
          S("set_config", path="functions.payment-hook",
            value={"handler": "app.hooks.payment_hook",
                   "environment": {"WEBHOOK_SECRET": "${env:WEBHOOK_SECRET, change-me}"},
                   "events": [{"http": "POST /hooks/payment"}]}),
          S("invoke_local", function="payment-hook", method="POST", path="/hooks/payment", data={"id": "pay_1"}),
      ],
      final="""Done. `payment-hook` on `POST /hooks/payment` checks the HMAC-SHA256 signature before doing anything:

```yaml
functions:
  payment-hook:
    handler: app.hooks.payment_hook
    environment:
      WEBHOOK_SECRET: ${env:WEBHOOK_SECRET, change-me}
    events:
      - http: POST /hooks/payment
```

- The secret comes from the environment variable when you deploy; `change-me` is only a local default [docs/configuration.md#variables].
- `pskit validate` (aws): valid.
- Local test without `x-signature`: **401** `bad signature`, as expected [docs/handlers.md#errors].

Before deploy, set `WEBHOOK_SECRET` (CI secret, or **Setup & credentials** > Environment variables > **Set for this session**). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 502
    B(502, provider="gcp", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      project=dict(files={
          "pskit.yml": """service: catalog-indexer
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, catalog-staging}
functions:
  index:
    handler: app.indexer.index
""",
          "app/__init__.py": "",
          "app/indexer.py": FUTURE + """

def index(event, ctx):
    if event.type == "storage":
        return {"indexed_files": [r.key for r in event.records]}
    return {"indexed_messages": len(event.records)}
""",
          "requirements.txt": ""}),
      user="`index` should run for new files in the bucket `catalog-feeds` and for messages on the queue `reindex-requests`. Same handler, it already branches on event.type. What will GCP actually deploy?",
      steps=[
          S("get_project"),
          S("search_docs", query="gcp one event trigger per function split",
            docs=[D("docs/events.md", "gcp-multi-trigger-functions-are-split-automatically")]),
          S("propose_plan", steps=["index.events = [storage: catalog-feeds, queue: reindex-requests]",
                                   "Validate for gcp (staging), invoke as storage and as queue"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.index.events", value=[{"storage": "catalog-feeds"}, {"queue": "reindex-requests"}]),
          S("invoke_local", function="index", type="storage", data={"bucket": "catalog-feeds", "key": "feed-77.xml"}),
          S("invoke_local", function="index", type="queue", data=[{"sku": "A"}, {"sku": "B"}]),
      ],
      final="""Added both triggers:

```yaml
functions:
  index:
    events:
      - storage: catalog-feeds
      - queue: reindex-requests
```

What GCP gets: a Cloud Function has at most one event trigger, so pskit deploys `index-storage0` (Cloud Storage via Eventarc) and `index-queue0` (Pub/Sub), both with your code and handler. There's no plain `index` deployment, because it has no HTTP event and isn't a workflow task. `pskit info` still shows one function, with the extra deployments under `extra` [docs/events.md#gcp-multi-trigger-functions-are-split-automatically].

- validate (gcp, staging): valid.
- invoke storage: `{"indexed_files": ["feed-77.xml"]}`; invoke queue: `{"indexed_messages": 2}`.

Both are event deployments, limited to 540 s. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 503
    B(503, provider="azure", stage="staging", mode="ask", page="Resources", persona="beginner",
      sources=["docs/events.md#events-backed-by-a-resource"],
      project=dict(files={
          "pskit.yml": """service: photo-booth
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="I want a storage place for photos, and when a photo is put in the originals folder, my code should run. Can you set that up?",
      steps=[
          S("get_project"),
          S("search_docs", query="storage resource used by event prefix",
            docs=[D("docs/events.md", "events-backed-by-a-resource", end="The event uses the resource's native name")]),
          S("propose_plan", steps=["Add a storage resource `photos` (pskit creates the blob container)",
                                   "Write `app/photos.py` and add function `new-photo` with storage {resource: photos, prefix: originals/}",
                                   "Validate for azure (staging) and test one photo"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.photos", value={"type": "storage"}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/photos.py", content=FUTURE + """

def new_photo(event, ctx):
    names = []
    for record in event.records:
        ctx.logger.info("new photo", extra={"key": record.key, "size": record.size})
        names.append(record.key)
    return {"photos": names}
"""),
          S("set_config", path="functions.new-photo",
            value={"handler": "app.photos.new_photo", "events": [{"storage": {"resource": "photos", "prefix": "originals/"}}]}),
          S("invoke_local", function="new-photo", type="storage", data={"bucket": "photos", "key": "originals/party.jpg", "size": 300000}),
      ],
      final="""All set:

```yaml
resources:
  photos:
    type: storage
functions:
  new-photo:
    handler: app.photos.new_photo
    events:
      - storage: {resource: photos, prefix: originals/}
```

- `photos` is your storage place: pskit creates it as a blob container when you deploy. The function points at the resource instead of repeating the name [docs/events.md#events-backed-by-a-resource].
- `new-photo` runs when a photo is added (or replaced) under `originals/`.
- `pskit validate` (azure, staging): valid.
- Test photo: `{"photos": ["originals/party.jpg"]}`.

Try it on **Test** > **▶ Run locally** with a storage event. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 504
    B(504, provider="aws", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#workflow-keys"],
      project=dict(files={
          "pskit.yml": """service: video-pipeline
provider:
  name: aws
  region: us-east-1
functions:
  start-encode:
    handler: app.video.start
  check-encode:
    handler: app.video.check
  publish:
    handler: app.video.publish
""",
          "app/__init__.py": "",
          "app/video.py": FUTURE + """

def start(event, ctx):
    return {**(event.data or {}), "job_id": "enc-1", "done": False}


def check(event, ctx):
    data = dict(event.data or {})
    return {**data, "done": data.get("polls", 0) >= 2, "polls": data.get("polls", 0) + 1}


def publish(event, ctx):
    return {**(event.data or {}), "published": True}
""",
          "requirements.txt": ""}),
      user="Polling workflow `encode-video`: StartEncode, then CheckEncode; if $.done is true go to Publish, otherwise wait 60 seconds and check again. Cap the whole execution at 2 hours.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add workflow `encode-video` (timeout 7200): Start (start-encode) -> Check (check-encode) -> IsDone (choice $.done equals true -> Publish, default Wait)",
                                   "Wait: 60 s -> Check (loop); Publish: publish, end",
                                   "Validate for aws (prod), run check-encode locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.encode-video",
            value={"timeout": 7200, "start_at": "Start",
                   "states": {"Start": {"type": "task", "function": "start-encode", "next": "Check"},
                              "Check": {"type": "task", "function": "check-encode", "next": "IsDone"},
                              "IsDone": {"type": "choice",
                                         "choices": [{"variable": "$.done", "equals": True, "next": "Publish"}],
                                         "default": "Wait"},
                              "Wait": {"type": "wait", "seconds": 60, "next": "Check"},
                              "Publish": {"type": "task", "function": "publish", "end": True}}}),
          S("invoke_local", function="check-encode", type="workflow", data={"job_id": "enc-1", "polls": 2}),
      ],
      final="""Added the polling loop:

```yaml
workflows:
  encode-video:
    timeout: 7200
    start_at: Start
    states:
      Start: {type: task, function: start-encode, next: Check}
      Check: {type: task, function: check-encode, next: IsDone}
      IsDone:
        type: choice
        choices: [{variable: $.done, equals: true, next: Publish}]
        default: Wait
      Wait: {type: wait, seconds: 60, next: Check}
      Publish: {type: task, function: publish, end: true}
```

- `timeout: 7200` becomes Step Functions `TimeoutSeconds` [docs/workflows.md#workflow-keys]. On a STANDARD state machine the 60 s waits aren't Lambda time.
- `pskit validate` (aws, prod): valid.
- `check-encode` locally with `polls: 2`: `"done": true`, so that run goes to Publish.

Run the loop locally (waits skipped): `pskit workflow run encode-video -i '{}' --history`. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 505
    B(505, provider="gcp", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: inventory
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, inventory-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="PATCH /stock/{sku} {delta:int}. unknown sku 404, stock below zero 409",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/stock.py: in-memory STOCK, NotFound / Conflict", "function `adjust-stock` on PATCH /stock/{sku}",
                                   "Validate gcp, invoke ok + conflict"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/stock.py", content=FUTURE + """from py_serverless_kit import Conflict, NotFound

STOCK = {"A1": 5, "B2": 0}


def adjust_stock(event, ctx):
    sku = event.http.path_params["sku"]
    if sku not in STOCK:
        raise NotFound(f"unknown sku {sku}")
    delta = int((event.http.json(default={}) or {}).get("delta", 0))
    if STOCK[sku] + delta < 0:
        raise Conflict("stock would go below zero")
    STOCK[sku] += delta
    return {"sku": sku, "stock": STOCK[sku]}
"""),
          S("set_config", path="functions.adjust-stock",
            value={"handler": "app.stock.adjust_stock", "events": [{"http": "PATCH /stock/{sku}"}]}),
          S("invoke_local", function="adjust-stock", method="PATCH", path="/stock/A1", data={"delta": -2}),
          S("invoke_local", function="adjust-stock", method="PATCH", path="/stock/B2", data={"delta": -1}),
      ],
      final="""Added `adjust-stock` on `PATCH /stock/{sku}`.

- validate (gcp): valid.
- `A1` delta -2: 200 `{"sku": "A1", "stock": 3}`. `B2` delta -1: **409** `stock would go below zero`. Unknown sku: 404 [docs/handlers.md#errors].

`STOCK` is in memory per instance; swap in a database before real use. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 506
    B(506, provider="azure", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: hr-portal
provider:
  name: azure
  region: westeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions:
  api:
    handler: app.hr.api
    events:
    - http: GET /employees
""",
          "app/__init__.py": "",
          "app/hr.py": FUTURE + """

def api(event, ctx):
    return []
""",
          "requirements.txt": ""}),
      user="Corporate policy: everything must go into the existing resource group `rg-hr-prod` (pskit must not create one), and we use our own central monitoring, so no Application Insights.",
      steps=[
          S("get_project"),
          S("search_docs", query="azure options resource_group app_insights",
            docs=[D("docs/providers.md", "azure-azure-functions", start="```yaml", end="servicebus_connection")]),
          S("propose_plan", steps=["provider.options.resource_group = rg-hr-prod",
                                   "provider.options.app_insights = false",
                                   "Validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.resource_group", value="rg-hr-prod"),
          S("set_config", path="provider.options.app_insights", value=False),
      ],
      final="""Set both options:

```yaml
provider:
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
    resource_group: rg-hr-prod
    app_insights: false
```

- `resource_group` makes pskit use the existing group instead of creating one; `app_insights` defaults to `true` [docs/providers.md#azure-azure-functions].
- `pskit validate` (azure, prod) passed after both changes.

The deploying identity needs rights in `rg-hr-prod`. Without Application Insights, the **Logs** page has less to show for Azure; use your central monitoring. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 507
    B(507, provider="aws", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: image-proxy
provider:
  name: aws
  region: us-east-1
functions:
  proxy:
    handler: app.proxy.handle
    timeout: 60
""",
          "app/__init__.py": "",
          "app/proxy.py": FUTURE + """

def handle(event, ctx):
    return {"path": event.http.path}
""",
          "requirements.txt": ""}),
      user="This Lambda used a Function URL (AuthType NONE) for GET /img/{key+}, and some requests take 45 seconds. Recreate the endpoint with pskit.",
      steps=[
          S("get_project"),
          S("search_docs", query="aws http api gateway integration timeout",
            docs=[D("docs/providers.md", "aws-aws-lambda", start="**Limits:**")]),
          S("ask_user", question="pskit puts HTTP functions behind an API Gateway HTTP API, which caps the integration timeout at 30 s. Requests over 30 s will get a gateway timeout even with timeout: 60. Continue, or shorten the slow path first?",
            options=["Continue, we'll make it faster", "Stop"], answer="Continue, we'll make it faster"),
          S("propose_plan", steps=["Add `- http: GET /img/{key+}` to proxy (public, auth none by default)",
                                   "Validate for aws (staging), invoke /img/a/b.png"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.proxy.events", value=[{"http": "GET /img/{key+}"}]),
          S("invoke_local", function="proxy", method="GET", path="/img/a/b.png"),
      ],
      final="""Recreated as a public route:

```yaml
functions:
  proxy:
    timeout: 60
    events:
      - http: GET /img/{key+}
```

- `pskit validate` (aws, staging): valid. invoke `/img/a/b.png`: 200 `{"path": "/img/a/b.png"}`.
- pskit uses an API Gateway HTTP API rather than a Function URL. Its integration timeout is capped at 30 s [docs/providers.md#aws-aws-lambda], so the 45 s requests must get faster, as you said. `timeout: 60` still applies to non-HTTP calls.

Deploy: **Deploy** or `pskit deploy -s staging`; `pskit info` shows the new URL to replace the Function URL."""),

    # ------------------------------------------------------------------ 508
    B(508, provider="gcp", stage="prod", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#what-handlers-receive", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: mailer
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, mailer-prod}
functions:
  enqueue:
    handler: app.mail.enqueue
    events:
    - http: POST /mail
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """from py_serverless_kit import resource


def enqueue(event, ctx):
    return {"queue": resource("outbox").native_name}, 202
""",
          "requirements.txt": ""}),
      user="queue resource `outbox`; consumer fn `send-mail` via resource. enqueue already reads it",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.outbox: {type: queue}",
                                   "app/mail.py: add send_mail; function send-mail with queue {resource: outbox}",
                                   "Validate gcp (prod), invoke enqueue + send-mail"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.outbox", value={"type": "queue"}),
          S("write_file", path="app/mail.py", content=FUTURE + """from py_serverless_kit import resource


def enqueue(event, ctx):
    return {"queue": resource("outbox").native_name}, 202


def send_mail(event, ctx):
    sent = [(r.json(default={}) or {}).get("to") for r in event.records]
    return {"sent": sent}
"""),
          S("set_config", path="functions.send-mail",
            value={"handler": "app.mail.send_mail", "events": [{"queue": {"resource": "outbox"}}]}),
          S("invoke_local", function="enqueue", method="POST", path="/mail", data={"to": "a@example.com"}),
          S("invoke_local", function="send-mail", type="queue", data=[{"to": "a@example.com"}]),
      ],
      final="""```yaml
resources:
  outbox:
    type: queue
functions:
  send-mail:
    handler: app.mail.send_mail
    events:
      - queue: {resource: outbox}
```

- On GCP the queue is a Pub/Sub topic with a push trigger [docs/events.md#queue]; bound functions also get its `ID` for publishing [docs/resources.md#what-handlers-receive].
- validate (gcp, prod): valid.
- enqueue: 202 `{"queue": "outbox"}` (local name); send-mail: `{"sent": ["a@example.com"]}`.

Publish from `enqueue` with `google-cloud-pubsub` and `resource("outbox").id`. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 509
    B(509, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: support-desk
provider:
  name: azure
  region: westeurope
functions:
  tickets:
    handler: app.desk.tickets
    events:
    - http: GET /tickets
""",
          "app/__init__.py": "",
          "app/desk.py": FUTURE + """

def tickets(event, ctx):
    return []
""",
          "requirements.txt": ""}),
      user="add GET /about that show service name, stage and which function answered. for debug which deploy i hit",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `about` to app/desk.py using ctx.service, ctx.stage, ctx.function",
                                   "Add function `about` on GET /about",
                                   "Validate azure, invoke"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/desk.py", content=FUTURE + """

def tickets(event, ctx):
    return []


def about(event, ctx):
    return {"service": ctx.service, "stage": ctx.stage, "function": ctx.function}
"""),
          S("set_config", path="functions.about", value={"handler": "app.desk.about", "events": [{"http": "GET /about"}]}),
          S("invoke_local", function="about", method="GET", path="/about"),
      ],
      final="""Done. `GET /about` returns who answered, from the context object [docs/handlers.md#context]:

- validate (azure): valid.
- invoke: `{"service": "support-desk", "stage": "dev", "function": "about"}`.

After deploy the same call tells you which stage you hit. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 510
    B(510, provider="aws", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/configuration.md#package"],
      project=dict(files={
          "pskit.yml": """service: pricing
provider:
  name: aws
  region: eu-west-1
functions:
  quote:
    handler: app.quote.quote
    events:
    - http: POST /quote
  invoice:
    handler: app.invoice.invoice
    events:
    - http: POST /invoice
""",
          "app/__init__.py": "",
          "app/quote.py": FUTURE + """

def quote(event, ctx):
    amount = float((event.http.json(default={}) or {}).get("amount", 0))
    return {"total": round(amount * 1.2, 2)}
""",
          "app/invoice.py": FUTURE + """

def invoice(event, ctx):
    amount = float((event.http.json(default={}) or {}).get("amount", 0))
    return {"total": round(amount * 1.2, 2), "invoice": True}
""",
          "requirements.txt": ""}),
      user="dedupe the VAT calc into app/common.py, both fns use it",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/common.py: with_vat(amount)", "quote.py / invoice.py import it",
                                   "Validate aws, invoke both"]),
          S("write_file", path="app/common.py", content=FUTURE + """VAT_RATE = 0.2


def with_vat(amount: float) -> float:
    return round(amount * (1 + VAT_RATE), 2)
"""),
          S("write_file", path="app/quote.py", content=FUTURE + """from app.common import with_vat


def quote(event, ctx):
    amount = float((event.http.json(default={}) or {}).get("amount", 0))
    return {"total": with_vat(amount)}
"""),
          S("write_file", path="app/invoice.py", content=FUTURE + """from app.common import with_vat


def invoice(event, ctx):
    amount = float((event.http.json(default={}) or {}).get("amount", 0))
    return {"total": with_vat(amount), "invoice": True}
"""),
          S("validate"),
          S("invoke_local", function="quote", method="POST", path="/quote", data={"amount": 100}),
          S("invoke_local", function="invoice", method="POST", path="/invoice", data={"amount": 50}),
      ],
      final="""Done: `app/common.py` has `with_vat()`, and both handlers import it.

- validate (aws): valid.
- quote 100 → `{"total": 120.0}`; invoice 50 → `{"total": 60.0, "invoice": true}`.

The whole project is bundled once (`package.include` defaults to `**/*`), so every function has `app/common.py` [docs/configuration.md#package]. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 511
    B(511, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#engines"],
      project=dict(files={
          "pskit.yml": """service: onboarding
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, onboarding-staging}
functions:
  welcome-email:
    handler: app.mails.welcome
  follow-up-email:
    handler: app.mails.follow_up
""",
          "app/__init__.py": "",
          "app/mails.py": FUTURE + """

def welcome(event, ctx):
    return {**(event.data or {}), "welcome": "sent"}


def follow_up(event, ctx):
    return {**(event.data or {}), "follow_up": "sent"}
""",
          "requirements.txt": ""}),
      user="when someone signs up I send a welcome email. one day later I want to send a follow up email. is that possible?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add workflow `new-user`: Welcome (welcome-email) -> WaitOneDay (wait 86400 s) -> FollowUp (follow-up-email, end)",
                                   "Validate for gcp (staging) and run welcome-email locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.new-user",
            value={"start_at": "Welcome",
                   "states": {"Welcome": {"type": "task", "function": "welcome-email", "next": "WaitOneDay"},
                              "WaitOneDay": {"type": "wait", "seconds": 86400, "next": "FollowUp"},
                              "FollowUp": {"type": "task", "function": "follow-up-email", "end": True}}}),
          S("invoke_local", function="welcome-email", type="workflow", data={"email": "new@example.com"}),
      ],
      final="""Yes. I made a workflow `new-user` that sends the welcome email, waits one day (86400 seconds), then sends the follow-up:

```yaml
workflows:
  new-user:
    start_at: Welcome
    states:
      Welcome:    {type: task, function: welcome-email, next: WaitOneDay}
      WaitOneDay: {type: wait, seconds: 86400, next: FollowUp}
      FollowUp:   {type: task, function: follow-up-email, end: true}
```

- On GCP this runs in Google Cloud Workflows, so waiting a day doesn't keep a function running [docs/workflows.md#engines].
- `pskit validate` (gcp, staging): valid.
- `welcome-email` locally: `"welcome": "sent"`.

Try the whole flow without waiting a day: `pskit workflow run new-user -i '{"email": "new@example.com"}'` (wait states are skipped locally). Start one run per signup. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 512
    B(512, provider="azure", stage="staging", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#retry-and-catch", "docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: imports
provider:
  name: azure
  region: westeurope
functions:
  parse-file:
    handler: app.imp.parse
  save-rows:
    handler: app.imp.save
""",
          "app/__init__.py": "",
          "app/imp.py": FUTURE + """

def parse(event, ctx):
    data = dict(event.data or {})
    if not data.get("file", "").endswith(".csv"):
        raise ValueError("only csv files")
    return {**data, "rows": 10}


def save(event, ctx):
    return {**(event.data or {}), "saved": True}
""",
          "requirements.txt": ""}),
      user="wf `import`: parse-file -> save-rows. ValueError from parse -> fail state BadFile (error BadFile, cause from message not needed)",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["workflows.import: Parse (parse-file, catch [ValueError] -> BadFile) -> Save (save-rows, end); BadFile: fail, error BadFile",
                                   "Validate azure (staging), invoke parse-file"]),
          S("set_config", path="workflows.import",
            value={"start_at": "Parse",
                   "states": {"Parse": {"type": "task", "function": "parse-file", "next": "Save",
                                        "catch": [{"errors": ["ValueError"], "next": "BadFile"}]},
                              "Save": {"type": "task", "function": "save-rows", "end": True},
                              "BadFile": {"type": "fail", "error": "BadFile", "cause": "unsupported file"}}}),
          S("invoke_local", function="parse-file", type="workflow", data={"file": "orders.csv"}),
      ],
      final="""```yaml
workflows:
  import:
    start_at: Parse
    states:
      Parse:
        type: task
        function: parse-file
        catch: [{errors: [ValueError], next: BadFile}]
        next: Save
      Save: {type: task, function: save-rows, end: true}
      BadFile: {type: fail, error: BadFile, cause: unsupported file}
```

- validate (azure, staging): valid (embedded engine, with the usual 600 s warning).
- invoke parse-file `orders.csv`: `"rows": 10`.

`errors` matches the Python class name [docs/workflows.md#retry-and-catch]. Check the fail path: `pskit workflow run import -i '{"file": "a.txt"}' --history` (exit code 2). Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 513
    B(513, provider="aws", stage="prod", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: recipes
provider:
  name: aws
  region: eu-west-1
functions:
  search:
    handler: app.recipes.search
    events:
    - http: GET /search
""",
          "app/__init__.py": "",
          "app/recipes.py": FUTURE + """

def search(event, ctx):
    return {"results": [], "memory": ctx.memory_mb}
""",
          "requirements.txt": ""}),
      user="search is slow only in prod because there are many more users. can prod get more memory but dev stay cheap?",
      steps=[
          S("get_project"),
          S("search_docs", query="different settings per stage",
            docs=[D("docs/configuration.md", "stages-per-stage-overrides")]),
          S("propose_plan", steps=["Add stages.prod.functions.search.memory = 1024 (other stages keep the default 256 MB)",
                                   "Validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages", value={"prod": {"functions": {"search": {"memory": 1024}}}}),
      ],
      final="""Yes. Only prod gets more memory:

```yaml
stages:
  prod:
    functions:
      search: {memory: 1024}
```

- The `stages.prod` block is used only when you deploy with stage `prod`; dev keeps the default 256 MB [docs/configuration.md#stages-per-stage-overrides].
- `pskit validate` (aws, prod): valid.

You can see the effect after deploy: on Lambda more memory also gives more CPU. Deploy prod: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 514
    B(514, provider="gcp", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing"],
      project=dict(files={
          "pskit.yml": """service: notifications
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, notifications-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="""Port this SQS consumer to a pskit function `notify` on the queue `push-jobs`:

def handler(event, context):
    failures = []
    for r in event["Records"]:
        msg = json.loads(r["body"])
        if "device" not in msg:
            failures.append({"itemIdentifier": r["messageId"]})
    return {"batchItemFailures": failures}""",
      steps=[
          S("get_project"),
          S("search_docs", query="Records body batchItemFailures BatchResult",
            docs=[D("docs/migrating-from-aws.md", "step-1-separate-business-logic-from-aws-event-parsing", start="| `for r in event[\"Records\"]`", end="| `{\"batchItemFailures\": [...]}`")]),
          S("propose_plan", steps=["Write `app/notify.py`: event.records, record.json(), BatchResult().fail(record)",
                                   "Add function `notify` with `- queue: push-jobs`",
                                   "Validate for gcp, invoke one good and one bad message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/notify.py", content=FUTURE + """from py_serverless_kit import BatchResult


def notify(event, ctx):
    result = BatchResult()
    for record in event.records:
        msg = record.json(default={}) or {}
        if "device" not in msg:
            result.fail(record)
    return result
"""),
          S("set_config", path="functions.notify", value={"handler": "app.notify.notify", "events": [{"queue": "push-jobs"}]}),
          S("invoke_local", function="notify", type="queue", data=[{"device": "d-1"}, {"text": "no device"}]),
      ],
      final="""Ported:

```python
def notify(event, ctx):
    result = BatchResult()
    for record in event.records:
        msg = record.json(default={}) or {}
        if "device" not in msg:
            result.fail(record)
    return result
```

`event["Records"]` + `json.loads(r["body"])` → `event.records` + `record.json()`; the `batchItemFailures` dict → `BatchResult` [docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing].

- validate (gcp): valid.
- invoke: `batchItemFailures` lists only the message without `device`.

On GCP (Pub/Sub) a failure retries the whole delivery instead of single messages, so keep it idempotent. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 515
    B(515, provider="azure", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#azure-azure-functions", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: erp-bridge
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="The ERP team writes jobs to an existing Storage Queue `erp-outbound` in THEIR storage account; its connection string will be in the app setting ERP_STORAGE. Add `consume-erp` for that queue. pskit must not create the queue.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.storage_connection = ERP_STORAGE",
                                   "Write app/erp.py; function consume-erp with queue {name: erp-outbound, existing: true}",
                                   "Validate for azure (staging), invoke one job"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.storage_connection", value="ERP_STORAGE"),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/erp.py", content=FUTURE + """

def consume_erp(event, ctx):
    jobs = [(r.json(default={}) or {}).get("job") for r in event.records]
    ctx.logger.info("erp jobs", extra={"count": len(jobs)})
    return {"jobs": jobs}
"""),
          S("set_config", path="functions.consume-erp",
            value={"handler": "app.erp.consume_erp", "events": [{"queue": {"name": "erp-outbound", "existing": True}}]}),
          S("invoke_local", function="consume-erp", type="queue", data=[{"job": "sync-prices"}]),
      ],
      final="""Added:

```yaml
provider:
  options:
    storage_connection: ERP_STORAGE
functions:
  consume-erp:
    handler: app.erp.consume_erp
    events:
      - queue: {name: erp-outbound, existing: true}
```

- `storage_connection` names the app setting for `existing` queues/buckets in another account [docs/providers.md#azure-azure-functions]. `existing: true` means pskit only adds the trigger.
- `pskit validate` (azure, staging): valid.
- invoke: `{"jobs": ["sync-prices"]}`.

Create the `ERP_STORAGE` app setting with the ERP account's connection string. Poison messages go to `erp-outbound-poison` in their account. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 516
    B(516, provider="aws", stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#using-a-resource-from-an-event", "docs/resources.md#aws-iam"],
      project=dict(files={
          "pskit.yml": """service: docs-vault
provider:
  name: aws
  region: eu-west-1
functions:
  upload-api:
    handler: app.vault.upload
    events:
    - http: POST /documents
""",
          "app/__init__.py": "",
          "app/vault.py": FUTURE + """from py_serverless_kit import resource


def upload(event, ctx):
    return {"bucket": resource("documents").native_name}, 202
""",
          "requirements.txt": ""}),
      user="Create one managed bucket `documents` (name docs-vault-documents-0042). `upload-api` writes to it, and a new `scan-document` function must run for every new PDF in it. Only those two functions should get access.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.documents: {type: storage, name: docs-vault-documents-0042, functions: [upload-api, scan-document]}",
                                   "Add scan_document to app/vault.py; function scan-document with storage {resource: documents, suffix: .pdf}",
                                   "Validate for aws (staging), invoke both"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.documents",
            value={"type": "storage", "name": "docs-vault-documents-0042", "functions": ["upload-api", "scan-document"]}),
          S("write_file", path="app/vault.py", content=FUTURE + """from py_serverless_kit import resource


def upload(event, ctx):
    return {"bucket": resource("documents").native_name}, 202


def scan_document(event, ctx):
    scanned = [record.key for record in event.records]
    ctx.logger.info("scan", extra={"count": len(scanned)})
    return {"scanned": scanned}
"""),
          S("set_config", path="functions.scan-document",
            value={"handler": "app.vault.scan_document", "events": [{"storage": {"resource": "documents", "suffix": ".pdf"}}]},
            say="validate complains that the resource lists `scan-document`, which doesn't exist yet. Adding the function now fixes that."),
          S("invoke_local", function="upload-api", method="POST", path="/documents", data={"name": "contract.pdf"}),
          S("invoke_local", function="scan-document", type="storage", data={"bucket": "docs-vault-documents-0042", "key": "contract.pdf"}),
      ],
      final="""One bucket, used by an event and by a binding:

```yaml
resources:
  documents:
    type: storage
    name: docs-vault-documents-0042
    functions: [upload-api, scan-document]
functions:
  scan-document:
    handler: app.vault.scan_document
    events:
      - storage: {resource: documents, suffix: .pdf}
```

- The event uses the resource's native name [docs/resources.md#using-a-resource-from-an-event]. Only the two listed functions get the `pskit-resources` S3 policy (Get/Put/Delete/List) [docs/resources.md#aws-iam].
- `pskit validate` (aws, staging): valid once `scan-document` existed (the first check failed only because the resource named it before it was added).
- upload-api: 202 `{"bucket": "docs-vault-documents-0042"}`; scan-document: `{"scanned": ["contract.pdf"]}`.

Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 517
    B(517, provider="gcp", stage="prod", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: currency
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, currency-prod}
functions:
  refresh-rates:
    handler: app.rates.refresh
""",
          "app/__init__.py": "",
          "app/rates.py": FUTURE + """

def refresh(event, ctx):
    base = (event.data or {}).get("base", "USD")
    return {"base": base, "refreshed": True}
""",
          "requirements.txt": ""}),
      user="refresh-rates every hour, base EUR",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["refresh-rates.events = [schedule {rate: 1 hour, input: {base: EUR}}]", "Validate gcp (prod), invoke schedule"]),
          S("set_config", path="functions.refresh-rates.events", value=[{"schedule": {"rate": "1 hour", "input": {"base": "EUR"}}}]),
          S("invoke_local", function="refresh-rates", type="schedule"),
      ],
      final="""```yaml
functions:
  refresh-rates:
    events:
      - schedule: {rate: 1 hour, input: {base: EUR}}
```

- validate (gcp, prod): valid. Cloud Scheduler gets it as cron (`0 * * * *`-style), since GCP uses 5-field cron [docs/events.md#schedule].
- invoke: `{"base": "EUR", "refreshed": true}`.

Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 518
    B(518, provider="azure", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/events.md#queue", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: order-intake
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="New project. Customers send orders to an API, and the slow work (like making the invoice) should happen in the background so the API answers fast. How would that look?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add queue resource `orders` (a Storage Queue pskit creates)",
                                   "Function `submit-order` on POST /orders: answers 202 at once (sending to the queue comes with azure-storage-queue later)",
                                   "Function `process-order` on queue {resource: orders}: the background work",
                                   "Validate for azure, test both locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.orders", value={"type": "queue"}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/orders.py", content=FUTURE + """from py_serverless_kit import resource


def submit_order(event, ctx):
    order = event.http.json(default={}) or {}
    queue = resource("orders").native_name
    # TODO: send `order` to `queue` with azure-storage-queue
    ctx.logger.info("order accepted", extra={"queue": queue, "item": order.get("item")})
    return {"accepted": True}, 202


def process_order(event, ctx):
    done = []
    for record in event.records:
        order = record.json(default={}) or {}
        ctx.logger.info("making invoice", extra={"item": order.get("item")})
        done.append(order.get("item"))
    return {"processed": done}
"""),
          S("set_config", path="functions.submit-order",
            value={"handler": "app.orders.submit_order", "events": [{"http": "POST /orders"}]}),
          S("set_config", path="functions.process-order",
            value={"handler": "app.orders.process_order", "events": [{"queue": {"resource": "orders"}}]}),
          S("invoke_local", function="submit-order", method="POST", path="/orders", data={"item": "desk"}),
          S("invoke_local", function="process-order", type="queue", data=[{"item": "desk"}]),
      ],
      final="""Here's the shape: an API that answers right away, and a background worker behind a queue.

```yaml
resources:
  orders:
    type: queue
functions:
  submit-order:
    handler: app.orders.submit_order
    events:
      - http: POST /orders
  process-order:
    handler: app.orders.process_order
    events:
      - queue: {resource: orders}
```

- `submit-order` answers **202** at once. `process-order` runs for every message on the `orders` queue (an Azure Storage Queue) [docs/events.md#queue].
- `pskit validate` (azure): valid.
- Local tests: submit → 202 `{"accepted": true}`; process → `{"processed": ["desk"]}`.

One TODO is left: pskit has no portable "send to queue" helper, so `submit-order` must send the order with `azure-storage-queue` and the queue name from `resource("orders")` [docs/resources.md#runtime-api]. Want me to add that? Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 519
    B(519, provider="aws", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": """service: quiz
provider:
  name: aws
  region: eu-west-1
functions:
  grade:
    handler: app.quiz.grade
  certify:
    handler: app.quiz.certify
""",
          "app/__init__.py": "",
          "app/quiz.py": FUTURE + """

def grade(event, ctx):
    answers = (event.data or {}).get("answers", [])
    return {"score": sum(1 for a in answers if a == "ok")}


def certify(event, ctx):
    return {**(event.data or {}), "certificate": True}
""",
          "requirements.txt": ""}),
      user="workflow grade then certify. very small and fast, i dont want step functions for it, run it inside lambda",
      steps=[
          S("get_project"),
          S("search_docs", query="engine embedded orchestrator",
            docs=[D("docs/workflows.md", "workflow-keys", start="| `engine` |", end="| `engine` |"),
                  D("docs/workflows.md", "embedded-orchestrator", end="- Every run has an")]),
          S("propose_plan", steps=["Add workflow `exam` with engine: embedded: Grade (grade) -> Certify (certify, end)",
                                   "Validate for aws, run grade locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.exam",
            value={"engine": "embedded", "start_at": "Grade",
                   "states": {"Grade": {"type": "task", "function": "grade", "next": "Certify"},
                              "Certify": {"type": "task", "function": "certify", "end": True}}}),
          S("invoke_local", function="grade", type="workflow", data={"answers": ["ok", "no", "ok"]}),
      ],
      final="""Done. `engine: embedded` runs the workflow inside a generated Lambda `exam-orchestrator` instead of Step Functions [docs/workflows.md#workflow-keys]:

```yaml
workflows:
  exam:
    engine: embedded
    start_at: Grade
    states:
      Grade:   {type: task, function: grade, next: Certify}
      Certify: {type: task, function: certify, end: true}
```

- validate (aws): valid, with a warning that the whole run is capped by the function timeout (900 s max on Lambda).
- grade locally: `{"score": 2}`.

Start it with `POST /workflows/exam` and the JSON input as the body; the answer comes back in the same call [docs/workflows.md#embedded-orchestrator]. That route is public like your other HTTP routes; set `options.http: false` if it shouldn't be. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 520
    B(520, provider="gcp", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: landing
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, landing-staging}
functions:
  hello:
    handler: app.hello.hello
    events:
    - http:
        path: /hello
        method: GET
        auth: iam
""",
          "app/__init__.py": "",
          "app/hello.py": FUTURE + """

def hello(event, ctx):
    return {"hello": "world"}
""",
          "requirements.txt": ""}),
      user="""Error: Forbidden
Your client does not have permission to get URL /hello from this server.
this page is for the public, everyone should open it""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["`hello` has auth: iam, which removes public access on GCP; change it to the shorthand `GET /hello` (auth none = public)",
                                   "Validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.hello.events", value=[{"http": "GET /hello"}]),
      ],
      final="""The 403 came from `auth: iam`: on GCP it means no public (`allUsers`) invoker binding, so only allowed Google identities can call it [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. I made it public again:

```yaml
functions:
  hello:
    events:
      - http: GET /hello
```

- The shorthand means `auth: none`, which adds the public invoker binding on deploy [docs/events.md#http].
- `pskit validate` (gcp, staging): valid.

The page opens for everyone after you deploy: **Deploy** or `pskit deploy -s staging`."""),
]
