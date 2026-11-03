"""Category B (build / add), batch 28 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 541
    B(541, provider="aws", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/resources.md#runtime-api", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: signup-app
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="I'm starting from zero. People sign up with their email on a form, a welcome email should go out in the background, and every night old signups that never confirmed get cleaned up. What do I need?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add a managed queue resource `welcome` (pskit creates the SQS queue)",
                                   "Write app/signup.py with three handlers: signup (POST /signup), send_welcome (reads the queue), cleanup (nightly)",
                                   "Add functions signup, send-welcome (queue via the resource) and cleanup (schedule 0 2 * * *)",
                                   "Validate for aws, run each one locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/signup.py", content=FUTURE + """from py_serverless_kit import BadRequest, resource


def signup(event, ctx):
    email = (event.http.json(default={}) or {}).get("email")
    if not email:
        raise BadRequest("email is required")
    queue = resource("welcome")
    # TODO: send {"email": email} to queue.url with boto3 (sqs.send_message)
    ctx.logger.info("signup", extra={"queue": queue.native_name})
    return {"email": email, "status": "pending"}, 202


def send_welcome(event, ctx):
    sent = []
    for record in event.records:
        email = (record.json(default={}) or {}).get("email")
        # TODO: send the email with your mail provider
        sent.append(email)
    return {"sent": sent}


def cleanup(event, ctx):
    # TODO: delete signups older than 7 days that never confirmed
    return {"removed": 0}
"""),
          S("set_config", path="functions.signup",
            value={"handler": "app.signup.signup", "events": [{"http": "POST /signup"}]}),
          S("set_config", path="resources.welcome", value={"type": "queue", "functions": ["signup"]}),
          S("set_config", path="functions.send-welcome",
            value={"handler": "app.signup.send_welcome", "events": [{"queue": {"resource": "welcome"}}]}),
          S("set_config", path="functions.cleanup",
            value={"handler": "app.signup.cleanup", "events": [{"schedule": "0 2 * * *"}]}),
          S("invoke_local", function="signup", method="POST", path="/signup", data={"email": "ada@example.com"}),
          S("invoke_local", function="send-welcome", type="queue", data=[{"email": "ada@example.com"}]),
      ],
      final="""Your project now has three functions that work together:

| Function | Trigger | Job |
|---|---|---|
| `signup` | `POST /signup` | checks the email, answers 202 |
| `send-welcome` | the `welcome` queue (pskit creates it) | sends the welcome emails in the background |
| `cleanup` | every night at 02:00 UTC | removes unconfirmed signups |

- `pskit validate` (aws): valid after every change.
- Local tests: `signup` → **202** `{"status": "pending"}`; `send-welcome` with one message → `{"sent": ["ada@example.com"]}`.

Two TODOs are left for you: putting the message on the queue (with `boto3`, using `resource("welcome").url` [docs/resources.md#runtime-api]) and the real email sending. Test again on **Test** > **▶ Run locally**, then deploy with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 542
    B(542, provider="gcp", stage="dev", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": """service: clock-api
provider:
  name: gcp
  region: europe-west1
  runtime: nodejs20
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, clock-api-dev}
functions:
  hello:
    handler: src.http.hello
    events:
    - http: GET /hello
""",
          "src/http.js": """exports.hello = async function (event, ctx) {
  return { message: "hello" };
};
""",
          "package.json": "{\n  \"name\": \"clock-api\",\n  \"private\": true\n}\n"}),
      user="my project is javascript not python. add GET /time give server time in iso and the timezone name, js please",
      steps=[
          S("get_project"),
          S("search_docs", query="node.js handler export",
            docs=[D("docs/nodejs.md", "handlers", end="`src/handlers/index.js`). Handlers can be sync or `async`.")]),
          S("propose_plan", steps=["Add export `time` to src/http.js (keep hello)",
                                   "Add function `time` with handler src.http.time on GET /time",
                                   "Validate gcp, invoke GET /time"]),
          S("write_file", path="src/http.js", content="""exports.hello = async function (event, ctx) {
  return { message: "hello" };
};

exports.time = async function (event, ctx) {
  return {
    now: new Date().toISOString(),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  };
};
"""),
          S("set_config", path="functions.time", value={"handler": "src.http.time", "events": [{"http": "GET /time"}]}),
          S("invoke_local", function="time", method="GET", path="/time"),
      ],
      final="""Done, in JavaScript. `src/http.js` now also exports `time`, and pskit.yml has:

```yaml
functions:
  time:
    handler: src.http.time
    events:
      - http: GET /time
```

The handler string works like Python: `src.http.time` = export `time` of `src/http.js` [docs/nodejs.md#handlers].

- validate (gcp): valid.
- invoke GET /time: 200 with `now` (ISO time) and `timezone` (locally it shows your machine's zone; in the cloud it is usually UTC).

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 543
    B(543, provider="azure", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: news-feed
provider:
  name: azure
  region: northeurope
functions: {}
""",
          "app/__init__.py": "",
          "app/feed.py": FUTURE + """

def list_items(event, ctx):
    return {"items": []}


def refresh(event, ctx):
    return {"refreshed": True, "source": (event.data or {}).get("source")}
""",
          "requirements.txt": ""}),
      user="""Port this serverless.yml to pskit on Azure. Code is already in app/feed.py.

functions:
  listItems:
    handler: app/feed.list_items
    memorySize: 512
    events:
      - httpApi: {path: /items, method: get}
  refresh:
    handler: app/feed.refresh
    timeout: 120
    events:
      - schedule: {rate: rate(15 minutes), input: {source: rss}}""",
      steps=[
          S("get_project"),
          S("search_docs", query="translate serverless schedule rate http",
            docs=[D("docs/migrating-from-aws.md", "step-2-translate-the-sam-serverless-cdk-definition", end="`- schedule: \"0 12 * * *\"`")]),
          S("propose_plan", steps=["functions.list-items: handler app.feed.list_items, http GET /items (memorySize dropped: pskit's Azure provider doesn't apply memory)",
                                   "functions.refresh: handler app.feed.refresh, timeout 120, schedule {rate: 15 minutes, input: {source: rss}}",
                                   "Validate for azure, invoke both"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.list-items",
            value={"handler": "app.feed.list_items", "events": [{"http": "GET /items"}]}),
          S("set_config", path="functions.refresh",
            value={"handler": "app.feed.refresh", "timeout": 120,
                   "events": [{"schedule": {"rate": "15 minutes", "input": {"source": "rss"}}}]}),
          S("invoke_local", function="list-items", method="GET", path="/items"),
          S("invoke_local", function="refresh", type="schedule"),
      ],
      final="""Ported:

```yaml
functions:
  list-items:
    handler: app.feed.list_items
    events:
      - http: GET /items
  refresh:
    handler: app.feed.refresh
    timeout: 120
    events:
      - schedule: {rate: 15 minutes, input: {source: rss}}
```

What changed [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition]:
- `app/feed.list_items` → `app.feed.list_items` (dots, not slashes); function names are lowercase with dashes.
- `rate(15 minutes)` → `15 minutes`; `input` becomes `event.data`.
- `memorySize: 512` is left out: on the Consumption plan Azure doesn't take a per-function memory size.

Checks: validate (azure) valid; `list-items` → 200 `{"items": []}`; `refresh` → `{"refreshed": true, "source": "rss"}`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 544
    B(544, provider="aws", stage="staging", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: payments
provider:
  name: aws
  region: eu-west-1
functions:
  capture:
    handler: app.capture.handle
    events:
    - queue:
        name: payment-captures
        batch_size: 10
""",
          "app/__init__.py": "",
          "app/capture.py": FUTURE + """

def handle(event, ctx):
    done = []
    for record in event.records:
        msg = record.json()
        done.append(msg["payment_id"])
    return {"captured": done}
""",
          "requirements.txt": ""}),
      user="capture: make it idempotent (SQS redelivers), skip dup payment_id, bad msgs -> partial batch failure",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Rewrite app/capture.py: skip payment_ids already seen (module-level set; durable store later), BatchResult.fail for messages without payment_id or invalid JSON",
                                   "Validate aws (staging), invoke with a duplicate and a bad message"]),
          S("write_file", path="app/capture.py", content=FUTURE + """from py_serverless_kit import BatchResult

# Per-instance memory only. For real idempotency use a durable store
# (e.g. a DynamoDB conditional put on payment_id).
_SEEN = set()


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        msg = record.json(default=None)
        if not isinstance(msg, dict) or not msg.get("payment_id"):
            result.fail(record)
            continue
        pid = msg["payment_id"]
        if pid in _SEEN:
            ctx.logger.info("duplicate skipped", extra={"payment_id": pid})
            continue
        # capture the payment here
        _SEEN.add(pid)
    return result
"""),
          S("validate"),
          S("invoke_local", function="capture", type="queue",
            data=[{"payment_id": "p-1"}, {"payment_id": "p-1"}, {"amount": 5}]),
      ],
      final="""app/capture.py now:
- skips a `payment_id` it has already handled (log `duplicate skipped`);
- calls `result.fail(record)` for messages without `payment_id` or with invalid JSON, so only those are retried; on SQS that becomes `batchItemFailures` [docs/handlers.md#batchresult].

Checks: validate (aws, staging) valid. invoke with `p-1`, `p-1` again and `{amount: 5}`: one duplicate logged, only the third message in `batchItemFailures`.

The `_SEEN` set only lives in one Lambda instance. For real exactly-once capture, record `payment_id` in a durable store (for example a DynamoDB conditional write) before capturing. Re-test: `pskit invoke -f capture -t queue -d '[{"payment_id": "p-1"}]'`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 545
    B(545, provider="gcp", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#extends-inherit-files", "docs/configuration.md#precedence-later-wins"],
      project=dict(files={
          "pskit.yml": """service: geo-api
provider:
  name: gcp
  region: europe-west1
  runtime: python3.11
  log_retention_days: 30
  tags:
    team: geo
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, geo-api-dev}
functions:
  lookup:
    handler: app.geo.lookup
    events:
    - http: GET /lookup
""",
          "app/__init__.py": "",
          "app/geo.py": FUTURE + """

def lookup(event, ctx):
    return {"team": ctx.env.get("TEAM", "unknown")}
""",
          "requirements.txt": ""}),
      user="Our team has five services that all repeat runtime python3.11, log_retention_days 30, tag team=geo and env TEAM=geo. Move those into a shared `team.yml` this service extends, and keep only service-specific things in pskit.yml.",
      steps=[
          S("get_project"),
          S("search_docs", query="extends inherit files",
            docs=[D("docs/configuration.md", "extends-inherit-files"),
                  D("docs/configuration.md", "precedence-later-wins", words=120)]),
          S("propose_plan", steps=["Write team.yml with provider.runtime, log_retention_days, tags.team and environment.TEAM",
                                   "Rewrite pskit.yml: extends: team.yml, keep service, name, region, options.project and the function",
                                   "Validate for gcp and invoke lookup (should see TEAM=geo from team.yml)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="team.yml", content="""# Shared settings for all geo team services
provider:
  runtime: python3.11
  log_retention_days: 30
  tags:
    team: geo
  environment:
    TEAM: geo
"""),
          S("write_file", path="pskit.yml", content="""extends: team.yml
service: geo-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, geo-api-dev}
functions:
  lookup:
    handler: app.geo.lookup
    events:
    - http: GET /lookup
"""),
          S("validate"),
          S("invoke_local", function="lookup", method="GET", path="/lookup"),
      ],
      final="""Done. The shared settings are in `team.yml`, and pskit.yml starts with `extends: team.yml` and keeps only what belongs to this service.

- Relative paths resolve from the extending file; dicts are deep-merged and a value in pskit.yml wins over the parent [docs/configuration.md#extends-inherit-files] [docs/configuration.md#precedence-later-wins].
- `pskit validate` (gcp): valid.
- invoke `GET /lookup`: `{"team": "geo"}`, so the environment really comes from team.yml.

For the other four services, copy `team.yml` to a shared place (for example `../team.yml`) and use `extends: ../team.yml`. `pskit*.yml` files are never bundled, but `team.yml` would be, so add it to `package.exclude` if you don't want it in the zip. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 546
    B(546, provider="azure", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: crm-sync
provider:
  name: azure
  region: westeurope
functions:
  sync-contacts:
    handler: app.sync.contacts
    events:
    - schedule: 30 minutes
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """

def contacts(event, ctx):
    return {"synced": 0, "stage": ctx.stage}
""",
          "requirements.txt": ""}),
      user="sync-contacts timer off in dev only, keep staging/prod running",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["stages.dev.functions.sync-contacts.events = [schedule {rate: 30 minutes, enabled: false}] (lists replace)",
                                   "Validate azure dev, invoke the schedule once by hand"]),
          S("set_config", path="stages.dev.functions.sync-contacts.events",
            value=[{"schedule": {"rate": "30 minutes", "enabled": False}}]),
          S("validate", provider="azure"),
          S("invoke_local", function="sync-contacts", type="schedule"),
      ],
      final="""```yaml
stages:
  dev:
    functions:
      sync-contacts:
        events:
          - schedule: {rate: 30 minutes, enabled: false}
```

- Only `--stage dev` gets this override; staging and prod keep the enabled 30-minute timer [docs/configuration.md#stages-per-stage-overrides]. Lists are replaced, so the whole `events` list is repeated.
- validate (azure, dev): valid.
- A manual run still works in dev: `{"synced": 0, "stage": "dev"}`.

Run it by hand any time: `pskit invoke -f sync-contacts -t schedule`. Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 547
    B(547, provider="aws", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#variables", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: pricing
provider:
  name: aws
  region: eu-west-1
  memory: 256
functions:
  quote:
    handler: app.quote.quote
    events:
    - http: POST /quote
""",
          "app/__init__.py": "",
          "app/quote.py": FUTURE + """

def quote(event, ctx):
    return {"price": 10}
""",
          "config/sizes.json": "{\n  \"dev\": {\"memory\": 256, \"timeout\": 10},\n  \"prod\": {\"memory\": 1024, \"timeout\": 29}\n}\n",
          "requirements.txt": ""}),
      user="Our capacity team maintains config/sizes.json with memory and timeout per stage. pskit.yml should read the values from that file (dev for the default, prod in a prod override) instead of hardcoding 256.",
      steps=[
          S("get_project"),
          S("read_file", path="config/sizes.json"),
          S("search_docs", query="file variable json",
            docs=[D("docs/configuration.md", "variables", end="When a value is exactly one variable")]),
          S("propose_plan", steps=["custom.sizes = ${file(config/sizes.json)}",
                                   "provider.memory/timeout = ${self:custom.sizes.dev.memory} / .timeout",
                                   "stages.prod.provider memory/timeout from custom.sizes.prod",
                                   "Validate for aws in prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="custom", value={"sizes": "${file(config/sizes.json)}"}),
          S("set_config", path="provider.memory", value="${self:custom.sizes.dev.memory}"),
          S("set_config", path="provider.timeout", value="${self:custom.sizes.dev.timeout}"),
          S("set_config", path="stages",
            value={"prod": {"provider": {"memory": "${self:custom.sizes.prod.memory}",
                                         "timeout": "${self:custom.sizes.prod.timeout}"}}}),
      ],
      final="""pskit.yml now reads the sizes from the capacity team's file:

```yaml
custom:
  sizes: ${file(config/sizes.json)}
provider:
  memory: ${self:custom.sizes.dev.memory}
  timeout: ${self:custom.sizes.dev.timeout}
stages:
  prod:
    provider:
      memory: ${self:custom.sizes.prod.memory}
      timeout: ${self:custom.sizes.prod.timeout}
```

- `${file(...)}` parses JSON relative to pskit.yml, and a value that is exactly one variable keeps its type, so memory stays a number [docs/configuration.md#variables].
- `pskit validate` (aws, prod): valid after each change, so prod resolves to 1024 MB / 29 s.

When the team edits sizes.json, the next deploy picks it up. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 548
    B(548, provider="gcp", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      project=dict(files={
          "pskit.yml": """service: shop-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, shop-api-staging}
functions:
  cart:
    handler: app.shop.cart
    events:
    - http: POST /cart
  shipping-cost:
    handler: app.shop.shipping_cost
""",
          "app/__init__.py": "",
          "app/shop.py": FUTURE + """

def cart(event, ctx):
    items = (event.http.json(default={}) or {}).get("items", [])
    total = sum(i["price"] for i in items)
    return {"total": total}


def shipping_cost(event, ctx):
    weight = (event.data or {}).get("weight", 0)
    return {"shipping": 4.9 if weight < 5 else 9.9}
""",
          "requirements.txt": ""}),
      user="I have a cart function and a shipping-cost function. Can cart ask shipping-cost for the price and add it to the total?",
      steps=[
          S("get_project"),
          S("search_docs", query="call another function invoke",
            docs=[D("docs/handlers.md", "invoke-calling-another-function", end="Other providers raise")]),
          S("propose_plan", steps=["In cart, call invoke(\"shipping-cost\", {\"weight\": ...}) and add the result to the total",
                                   "No YAML change needed: shipping-cost stays invoke-only",
                                   "Validate for gcp (staging), invoke cart locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/shop.py", content=FUTURE + """from py_serverless_kit import invoke


def cart(event, ctx):
    items = (event.http.json(default={}) or {}).get("items", [])
    subtotal = sum(i["price"] for i in items)
    weight = sum(i.get("weight", 0) for i in items)
    shipping = invoke("shipping-cost", {"weight": weight})["shipping"]
    return {"subtotal": subtotal, "shipping": shipping, "total": round(subtotal + shipping, 2)}


def shipping_cost(event, ctx):
    weight = (event.data or {}).get("weight", 0)
    return {"shipping": 4.9 if weight < 5 else 9.9}
"""),
          S("validate"),
          S("invoke_local", function="cart", method="POST", path="/cart",
            data={"items": [{"price": 20, "weight": 2}, {"price": 15, "weight": 4}]}),
      ],
      final="""Yes. `cart` now calls `invoke("shipping-cost", {"weight": ...})` and adds the answer to the total.

- On GCP, `invoke()` makes an authenticated HTTPS call to the shipping-cost function; locally it calls the handler directly [docs/handlers.md#invoke-calling-another-function].
- `pskit validate` (gcp, staging): valid.
- Local test with two items (6 kg): `{"subtotal": 35, "shipping": 9.9, "total": 44.9}`.

Try other carts on **Test** > **▶ Run locally**. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 549
    B(549, provider="azure", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#queue", "docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: loyalty
provider:
  name: azure
  region: westeurope
functions:
  award-points:
    handler: app.points.award
    events:
    - queue: points-awards
""",
          "app/__init__.py": "",
          "app/points.py": FUTURE + """

def award(event, ctx):
    return {"awarded": len(event.records)}
""",
          "requirements.txt": ""}),
      user="award-points reads the Storage Queue `points-awards`. Messages are {\"award_id\", \"customer\", \"points\"}. The same award can arrive twice, and it must only count once. Messages with points <= 0 are invalid. Return the totals per customer.",
      steps=[
          S("get_project"),
          S("search_docs", query="azure storage queue partial batch failure retry",
            docs=[D("docs/events.md", "queue", start="| Option |", end="| partial batch failure |")]),
          S("propose_plan", steps=["Rewrite app/points.py: ignore an award_id already processed in the delivery or before (in-memory set + note about a durable store)",
                                   "Invalid points (<= 0 or missing) are logged and skipped, not retried: on Azure a failure retries the whole delivery",
                                   "Return {totals: {customer: points}, skipped: [...]}; validate azure (staging), invoke with a duplicate and an invalid message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/points.py", content=FUTURE + """# In-memory only; use a durable store (e.g. a Table Storage row per award_id) in production.
_PROCESSED = set()


def award(event, ctx):
    totals = {}
    skipped = []
    for record in event.records:
        msg = record.json(default={}) or {}
        award_id = msg.get("award_id")
        points = msg.get("points") or 0
        if not award_id or points <= 0:
            ctx.logger.warning("invalid award", extra={"award_id": award_id})
            skipped.append(award_id)
            continue
        if award_id in _PROCESSED:
            continue
        _PROCESSED.add(award_id)
        totals[msg["customer"]] = totals.get(msg["customer"], 0) + points
    return {"totals": totals, "skipped": skipped}
"""),
          S("validate"),
          S("invoke_local", function="award-points", type="queue",
            data=[{"award_id": "a1", "customer": "c-7", "points": 50},
                  {"award_id": "a1", "customer": "c-7", "points": 50},
                  {"award_id": "a2", "customer": "c-7", "points": 0}]),
      ],
      final="""`award-points` now counts each `award_id` once and skips invalid awards.

- On Azure Storage Queues a failure retries the whole delivery (no partial batch failure) [docs/events.md#queue], so invalid messages are logged and skipped instead of `BatchResult.fail`, which would replay the good ones too.
- `pskit validate` (azure, staging): valid.
- invoke with a1, a1 again and a2 with 0 points: `{"totals": {"c-7": 50}, "skipped": ["a2"]}` and an `invalid award` warning.

The processed-id set only lives in one instance. For a guarantee across restarts and scale-out, store `award_id` durably (for example one Table Storage row per award) before adding points. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 550
    B(550, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/configuration.md#package", "docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: birthday-bot
provider:
  name: aws
  region: eu-central-1
functions:
  next-birthday:
    handler: app.bday.next_birthday
    events:
    - http: GET /next/{date}
""",
          "app/__init__.py": "",
          "app/bday.py": FUTURE + """

def next_birthday(event, ctx):
    return {"date": event.http.path_params["date"]}
""",
          "requirements.txt": ""}),
      user="i want use python-dateutil library for parse date in next-birthday, how many days until next birthday. how i add library?",
      steps=[
          S("get_project"),
          S("search_docs", query="requirements dependencies package",
            docs=[D("docs/configuration.md", "package", end="| `vendor` |")]),
          S("propose_plan", steps=["Add `python-dateutil` to requirements.txt (pskit installs it into the Lambda zip)",
                                   "Use dateutil.parser in app/bday.py: days until the next birthday, 400 for a bad date",
                                   "Validate for aws, invoke GET /next/1990-03-14"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="requirements.txt", content="python-dateutil>=2.8\n"),
          S("write_file", path="app/bday.py", content=FUTURE + """import datetime

from dateutil import parser

from py_serverless_kit import BadRequest


def next_birthday(event, ctx):
    raw = event.http.path_params["date"]
    try:
        born = parser.parse(raw).date()
    except (ValueError, OverflowError):
        raise BadRequest(f"cannot read date {raw!r}")
    today = datetime.date.today()
    nxt = born.replace(year=today.year)
    if nxt < today:
        nxt = nxt.replace(year=today.year + 1)
    return {"born": born.isoformat(), "next": nxt.isoformat(), "days": (nxt - today).days}
"""),
          S("validate"),
          S("invoke_local", function="next-birthday", method="GET", path="/next/1990-03-14"),
      ],
      final="""Done. Add libraries in `requirements.txt`; I put `python-dateutil>=2.8` there [docs/configuration.md#package]. On AWS, pskit pip-installs it into the zip as Linux wheels when you package or deploy [docs/providers.md#aws-aws-lambda].

`next-birthday` now parses the date with `dateutil` and returns the days until the next birthday (400 if the date can't be read).

- `pskit validate` (aws): valid.
- Local test `GET /next/1990-03-14`: 200 with `next` and `days`.

For local runs, the library must be in your project environment too (`pip install python-dateutil` in the .venv). Deploy: **Deploy** or `pskit deploy -s dev`. (A 29 February birthday needs extra care in non-leap years.)"""),

    # ------------------------------------------------------------------ 551
    B(551, provider="azure", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/events.md#queue", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: salon-booking
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="create a new project for my hair salon: customers book a time online, they get a confirmation after, and every morning at 8 I want a list of today's bookings",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/salon.py with book (HTTP), confirm (queue worker) and daily_list (timer)",
                                   "book: POST /bookings, needs name and time, answers 201",
                                   "confirm: Storage Queue `booking-confirmations`; daily-list: schedule 0 8 * * * (UTC on Azure)",
                                   "Validate for azure, run each one locally"],
            result={"decision": "approved", "note": "Make the daily list 07:30 instead of 8: we open at 8 and I want to read it before."}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/salon.py", content=FUTURE + """from py_serverless_kit import BadRequest


def book(event, ctx):
    body = event.http.json(default={}) or {}
    if not body.get("name") or not body.get("time"):
        raise BadRequest("name and time are required")
    # TODO: save the booking and put a message on booking-confirmations
    return {"booked": body["name"], "time": body["time"]}, 201


def confirm(event, ctx):
    names = [(r.json(default={}) or {}).get("name") for r in event.records]
    # TODO: send the confirmation email or SMS
    return {"confirmed": names}


def daily_list(event, ctx):
    # TODO: read today's bookings from where book() saves them
    return {"bookings_today": []}
"""),
          S("set_config", path="functions.book", value={"handler": "app.salon.book", "events": [{"http": "POST /bookings"}]}),
          S("set_config", path="functions.confirm",
            value={"handler": "app.salon.confirm", "events": [{"queue": "booking-confirmations"}]}),
          S("set_config", path="functions.daily-list",
            value={"handler": "app.salon.daily_list", "events": [{"schedule": "30 7 * * *"}]}),
          S("invoke_local", function="book", method="POST", path="/bookings", data={"name": "Sam", "time": "2026-11-03T10:00"}),
          S("invoke_local", function="confirm", type="queue", data=[{"name": "Sam"}]),
      ],
      final="""Your salon project is set up with three functions:

- `book`: `POST /bookings`, needs `name` and `time`, answers **201**.
- `confirm`: runs for each message on the Storage Queue `booking-confirmations` (pskit creates it).
- `daily-list`: every day at **07:30 UTC**, as you asked in your note. Azure timers always run in UTC [docs/events.md#schedule], so that is 07:30 in London in winter and 08:30 in summer time.

Checks: `pskit validate` (azure) valid; `book` → 201 `{"booked": "Sam", ...}`; `confirm` → `{"confirmed": ["Sam"]}`.

Still to do (marked TODO in app/salon.py): saving bookings somewhere, putting the message on the queue, and sending the confirmation. Try it on **Test** > **▶ Run locally**, and deploy with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 552
    B(552, provider="aws", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": """service: ts-jobs
provider:
  name: aws
  region: us-east-1
  runtime: nodejs20
functions:
  ping:
    handler: src.http.ping
    events:
    - http: GET /ping
""",
          "src/http.js": """exports.ping = async function () {
  return { ok: true };
};
""",
          "package.json": "{\n  \"name\": \"ts-jobs\",\n  \"private\": true\n}\n"}),
      user="node service. add sqs worker `thumbs` on queue thumb-jobs, batch 20, JS, BatchResult for msgs missing `key`",
      steps=[
          S("get_project"),
          S("search_docs", query="nodejs BatchResult worker",
            docs=[D("docs/nodejs.md", "handlers", start="```ts", end="The API mirrors")]),
          S("propose_plan", steps=["Write src/jobs.js: export thumbs, BatchResult.fail(record) when record.json().key is missing",
                                   "functions.thumbs: handler src.jobs.thumbs, queue {name: thumb-jobs, batch_size: 20}",
                                   "Validate aws, invoke with one good and one bad message"]),
          S("write_file", path="src/jobs.js", content="""const { BatchResult } = require("pskit");

exports.thumbs = async function (event, ctx) {
  const result = new BatchResult();
  for (const record of event.records) {
    const msg = record.json();
    if (!msg || !msg.key) {
      result.fail(record);
      continue;
    }
    ctx.logger.info("thumbnail", { key: msg.key });
  }
  return result;
};
"""),
          S("set_config", path="functions.thumbs",
            value={"handler": "src.jobs.thumbs", "events": [{"queue": {"name": "thumb-jobs", "batch_size": 20}}]}),
          S("invoke_local", function="thumbs", type="queue", data=[{"key": "img/1.png"}, {"size": 3}]),
      ],
      final="""```yaml
functions:
  thumbs:
    handler: src.jobs.thumbs
    events:
      - queue: {name: thumb-jobs, batch_size: 20}
```

`src/jobs.js` uses `BatchResult` from `pskit` (same API as Python, camelCase) [docs/nodejs.md#handlers].

- validate (aws): valid.
- invoke `[{key}, {size}]`: one `thumbnail` log, the second message in `batchItemFailures`, so SQS retries only that one.

Re-test: `pskit invoke -f thumbs -t queue -d '[{"key": "a.png"}]'`. Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 553
    B(553, provider="gcp", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: ledger-api
provider:
  name: gcp
  region: europe-west3
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, ledger-api-prod}
functions:
  entries:
    handler: app.ledger.entries
    events:
    - http: GET /entries
""",
          "app/__init__.py": "",
          "app/ledger.py": FUTURE + """

def entries(event, ctx):
    return {"entries": []}
""",
          "requirements.txt": ""}),
      user="""uptime checker keeps alerting:

  Check "ledger-health" failed: GET https://ledger.example.com/healthz -> 404 Not Found (3 of 3 regions)

we never had that route. add it, it should just say ok and the version (env APP_VERSION, CI sets it)""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/health.py: return {status: ok, version: APP_VERSION or 'unknown'}",
                                   "Add function `healthz` on GET /healthz with environment APP_VERSION: ${env:APP_VERSION, unknown}",
                                   "Validate gcp (prod), invoke GET /healthz"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/health.py", content=FUTURE + """

def healthz(event, ctx):
    return {"status": "ok", "version": ctx.env.get("APP_VERSION", "unknown")}
"""),
          S("set_config", path="functions.healthz",
            value={"handler": "app.health.healthz", "environment": {"APP_VERSION": "${env:APP_VERSION, unknown}"},
                   "events": [{"http": "GET /healthz"}]}),
          S("invoke_local", function="healthz", method="GET", path="/healthz"),
      ],
      final="""The 404 is right: no function served `/healthz`. Now `healthz` does:

```yaml
functions:
  healthz:
    handler: app.health.healthz
    environment:
      APP_VERSION: ${env:APP_VERSION, unknown}
    events:
      - http: GET /healthz
```

- `pskit validate` (gcp, prod): valid.
- invoke `GET /healthz`: 200 `{"status": "ok", "version": "unknown"}` (APP_VERSION isn't set here; CI's value is used at deploy).

On GCP each function gets its own URL, so after deploy check that the uptime check (or your `ledger.example.com` routing) points at the healthz URL from `pskit info`. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 554
    B(554, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#variables", "docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: repo-hooks
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="Add POST /github for GitHub webhooks. GitHub signs the raw body with HMAC-SHA256 and sends `X-Hub-Signature-256: sha256=<hex>`. The shared key comes from the environment variable GITHUB_WEBHOOK_KEY, never in pskit.yml. Wrong or missing signature -> 401. For push events return the branch.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/github.py: compare sha256=<hmac of the raw body> with hmac.compare_digest, 401 on mismatch",
                                   "Add function `github` on POST /github (auth none: GitHub can't send a function key header) with GITHUB_WEBHOOK_KEY: ${env:GITHUB_WEBHOOK_KEY, not-set}",
                                   "Validate for azure, invoke once without a signature (expect 401)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/github.py", content=FUTURE + """import hashlib
import hmac

from py_serverless_kit import Unauthorized


def github(event, ctx):
    key = ctx.env.get("GITHUB_WEBHOOK_KEY", "").encode()
    raw = event.http.body or b""
    if isinstance(raw, str):
        raw = raw.encode()
    expected = "sha256=" + hmac.new(key, raw, hashlib.sha256).hexdigest()
    sent = event.http.headers.get("x-hub-signature-256", "")
    if not key or not hmac.compare_digest(expected, sent):
        raise Unauthorized("bad signature")
    payload = event.http.json(default={}) or {}
    if event.http.headers.get("x-github-event") == "push":
        return {"branch": payload.get("ref", "").replace("refs/heads/", "")}
    return {"ignored": True}
"""),
          S("set_config", path="functions.github",
            value={"handler": "app.github.github",
                   "environment": {"GITHUB_WEBHOOK_KEY": "${env:GITHUB_WEBHOOK_KEY, not-set}"},
                   "events": [{"http": "POST /github"}]}),
          S("invoke_local", function="github", method="POST", path="/github", data={"ref": "refs/heads/main"}),
      ],
      final="""Added `github` on `POST /github`:

- The handler computes `sha256=` + HMAC-SHA256 of the raw body and compares it with `X-Hub-Signature-256` using `hmac.compare_digest`; mismatch → **401**. Push events return the branch.
- The key is `GITHUB_WEBHOOK_KEY: ${env:GITHUB_WEBHOOK_KEY, not-set}`: pskit.yml only holds the variable name [docs/configuration.md#variables].
- `pskit validate` (azure): valid.
- Local POST without a signature: **401** `bad signature`.

Before deploying, set the real `GITHUB_WEBHOOK_KEY` where you deploy (for example **Setup & credentials** > Environment variables > **Set for this session**, or a CI secret); the same value goes into the GitHub webhook settings. Deploy: **Deploy** or `pskit deploy -s dev`, then use the URL from `pskit info`."""),

    # ------------------------------------------------------------------ 555
    B(555, provider="aws", stage="staging", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition"],
      project=dict(files={
          "pskit.yml": """service: inventory
provider:
  name: aws
  region: us-east-2
functions: {}
""",
          "app/__init__.py": "",
          "app/stock.py": FUTURE + """

def get_stock(event, ctx):
    return {"sku": event.http.path_params["sku"], "qty": 0}


def import_stock(event, ctx):
    return {"imported": len(event.records)}
""",
          "requirements.txt": ""}),
      user="""Moving this serverless.yml over. The queue stock-updates stays in the old stack for now.

provider:
  name: aws
  runtime: python3.11
  memorySize: 512
  environment:
    TABLE: inventory-staging
functions:
  getStock:
    handler: app/stock.get_stock
    events:
      - httpApi: 'GET /stock/{sku}'
  importStock:
    handler: app/stock.import_stock
    timeout: 60
    events:
      - sqs:
          arn: arn:aws:sqs:us-east-2:123456789012:stock-updates
          batchSize: 25""",
      steps=[
          S("get_project"),
          S("search_docs", query="serverless sqs existing queue batch size",
            docs=[D("docs/migrating-from-aws.md", "step-2-translate-the-sam-serverless-cdk-definition")]),
          S("propose_plan", steps=["provider: runtime python3.11, memory 512, environment TABLE=inventory-staging",
                                   "get-stock: app.stock.get_stock on GET /stock/{sku}",
                                   "import-stock: app.stock.import_stock, timeout 60, queue {name: stock-updates, existing: true, batch_size: 25}",
                                   "Validate aws (staging), invoke both"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider",
            value={"name": "aws", "region": "us-east-2", "runtime": "python3.11", "memory": 512,
                   "environment": {"TABLE": "inventory-staging"}}),
          S("set_config", path="functions.get-stock",
            value={"handler": "app.stock.get_stock", "events": [{"http": "GET /stock/{sku}"}]}),
          S("set_config", path="functions.import-stock",
            value={"handler": "app.stock.import_stock", "timeout": 60,
                   "events": [{"queue": {"name": "stock-updates", "existing": True, "batch_size": 25}}]}),
          S("invoke_local", function="get-stock", method="GET", path="/stock/AB-12"),
          S("invoke_local", function="import-stock", type="queue", data=[{"sku": "AB-12", "qty": 4}]),
      ],
      final="""Translated:

```yaml
provider:
  name: aws
  region: us-east-2
  runtime: python3.11
  memory: 512
  environment: {TABLE: inventory-staging}
functions:
  get-stock:
    handler: app.stock.get_stock
    events:
      - http: GET /stock/{sku}
  import-stock:
    handler: app.stock.import_stock
    timeout: 60
    events:
      - queue: {name: stock-updates, existing: true, batch_size: 25}
```

- `existing: true` means pskit only adds the event source mapping and never creates or deletes `stock-updates` [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition]. The ARN isn't needed: the name is enough in the same account and region.
- validate (aws, staging): valid. invoke: get-stock → 200 `{"sku": "AB-12", "qty": 0}`; import-stock → `{"imported": 1}`.

Deploy side by side with the old stack: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 556
    B(556, provider="gcp", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: scan-inbox
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, scan-inbox-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="New project: scanned documents land in the bucket `scan-inbox-uploads-7731` (pskit creates it). Function `on-scan` runs for new .pdf files. Separately, `notify` listens on Pub/Sub topic `scan-done` and logs the file name. Plus GET /status for monitoring.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/scan.py with on_scan, notify and status",
                                   "on-scan: storage {bucket: scan-inbox-uploads-7731, events: [created], suffix: .pdf}",
                                   "notify: topic scan-done; status: GET /status",
                                   "Validate gcp, invoke on-scan and notify"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/scan.py", content=FUTURE + """

def on_scan(event, ctx):
    files = [r.key for r in event.records]
    ctx.logger.info("new scans", extra={"files": files})
    # TODO: publish {"file": ...} to the scan-done topic with google-cloud-pubsub
    return {"files": files}


def notify(event, ctx):
    for r in event.records:
        ctx.logger.info("scan done", extra={"file": (r.json(default={}) or {}).get("file")})
    return None


def status(event, ctx):
    return {"status": "ok"}
"""),
          S("set_config", path="functions.on-scan",
            value={"handler": "app.scan.on_scan",
                   "events": [{"storage": {"bucket": "scan-inbox-uploads-7731", "events": ["created"], "suffix": ".pdf"}}]}),
          S("set_config", path="functions.notify", value={"handler": "app.scan.notify", "events": [{"topic": "scan-done"}]}),
          S("set_config", path="functions.status", value={"handler": "app.scan.status", "events": [{"http": "GET /status"}]}),
          S("invoke_local", function="on-scan", type="storage", data={"bucket": "scan-inbox-uploads-7731", "key": "2026/invoice-1.pdf"}),
          S("invoke_local", function="notify", type="topic", data={"file": "2026/invoice-1.pdf"}),
      ],
      final="""Created the three functions:

| Function | Trigger |
|---|---|
| `on-scan` | bucket `scan-inbox-uploads-7731`, `created`, suffix `.pdf` (pskit creates the bucket) |
| `notify` | Pub/Sub topic `scan-done` (pskit creates it) |
| `status` | `GET /status` |

- On GCP the prefix/suffix filter is applied by the pskit runtime, so the function is also started for other files but returns early [docs/events.md#storage].
- `pskit validate` (gcp): valid after each function.
- invoke: on-scan → `{"files": ["2026/invoice-1.pdf"]}`; notify → logs `scan done`, returns `null`.

Left for you: publishing to `scan-done` from on-scan (TODO, with `google-cloud-pubsub` in requirements.txt). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 557
    B(557, provider="azure", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/nodejs.md#choosing-the-runtime", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: kiosk
provider:
  name: azure
  region: westeurope
  runtime: nodejs20
functions:
  menu:
    handler: src.menu.today
    events:
    - http: GET /menu
""",
          "src/menu.js": """exports.today = async function () {
  return { dishes: ["soup", "pasta"] };
};
""",
          "package.json": "{\n  \"name\": \"kiosk\",\n  \"private\": true\n}\n"}),
      user="we are node on azure. need job every monday 6:00 utc clear the old menu, write in javascript also",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write src/jobs.js with export clearMenu (logs and returns what it cleared)",
                                   "Add function `clear-menu`: handler src.jobs.clearMenu, schedule \"0 6 * * 1\"",
                                   "Validate for azure (staging), run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/jobs.js", content="""exports.clearMenu = async function (event, ctx) {
  // TODO: delete last week's menu from your storage
  ctx.logger.info("clearing old menu", { stage: ctx.stage });
  return { cleared: true };
};
"""),
          S("set_config", path="functions.clear-menu",
            value={"handler": "src.jobs.clearMenu", "events": [{"schedule": "0 6 * * 1"}]}),
          S("invoke_local", function="clear-menu", type="schedule"),
      ],
      final="""Done, in JavaScript like the rest:

```yaml
functions:
  clear-menu:
    handler: src.jobs.clearMenu
    events:
      - schedule: "0 6 * * 1"
```

- `src.jobs.clearMenu` = the `clearMenu` export of `src/jobs.js`; the whole service stays on `nodejs20` [docs/nodejs.md#choosing-the-runtime].
- Azure timers run in UTC, so this is exactly Monday 06:00 UTC [docs/events.md#schedule].
- validate (azure, staging): valid. Local run: `{"cleared": true}`.

Run it again by hand: `pskit invoke -f clear-menu -t schedule`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 558
    B(558, provider="aws", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: aws
  region: eu-west-1
functions:
  search:
    handler: app.catalog.search
    events:
    - http: GET /search
  rebuild-index:
    handler: app.catalog.rebuild
    events:
    - schedule: 15 minutes
""",
          "app/__init__.py": "",
          "app/catalog.py": FUTURE + """

def search(event, ctx):
    return {"results": []}


def rebuild(event, ctx):
    return {"rebuilt": True}
""",
          "requirements.txt": ""}),
      user="Stage settings: in prod, search gets 1024 MB and reserved concurrency 20, and rebuild-index runs every 15 minutes. In dev and staging, rebuild-index should only run once an hour to save money. Keep the base config as the dev values.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Base: rebuild-index schedule 1 hour (dev/staging value)",
                                   "stages.prod.functions.search: {memory: 1024, concurrency: 20}",
                                   "stages.prod.functions.rebuild-index.events: [schedule 15 minutes]",
                                   "Validate for aws in prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.rebuild-index.events", value=[{"schedule": "1 hour"}]),
          S("set_config", path="stages",
            value={"prod": {"functions": {"search": {"memory": 1024, "concurrency": 20},
                                          "rebuild-index": {"events": [{"schedule": "15 minutes"}]}}}}),
      ],
      final="""```yaml
functions:
  rebuild-index:
    events:
      - schedule: 1 hour          # dev and staging
stages:
  prod:
    functions:
      search: {memory: 1024, concurrency: 20}
      rebuild-index:
        events:
          - schedule: 15 minutes
```

- `stages.prod` is merged only for `--stage prod`; the `events` list is replaced, not appended [docs/configuration.md#stages-per-stage-overrides].
- `pskit validate` (aws, prod): valid after both changes.

Check another stage with the stage box in the top bar (or `pskit validate -s dev`). Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 559
    B(559, provider="gcp", stage="staging", mode="auto", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: notes-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, notes-api-staging}
functions:
  notes:
    handler: app.notes.notes
    environment:
      COLLECTION: notes-dev
      PUBLIC_URL: https://api-dev.example.com
    events:
    - http: GET /notes
""",
          "app/__init__.py": "",
          "app/notes.py": FUTURE + """

def notes(event, ctx):
    return {"collection": ctx.env.get("COLLECTION"), "url": ctx.env.get("PUBLIC_URL")}
""",
          "requirements.txt": ""}),
      user="COLLECTION and PUBLIC_URL have dev hardcoded, so staging deploy use dev data. make them follow the stage automatic",
      steps=[
          S("get_project"),
          S("search_docs", query="opt stage variable",
            docs=[D("docs/configuration.md", "variables", end="| `${self:dotted.path}` |")]),
          S("propose_plan", steps=["COLLECTION = notes-${opt:stage}, PUBLIC_URL = https://api-${opt:stage}.example.com",
                                   "Validate gcp (staging), invoke to see the staging values"]),
          S("set_config", path="functions.notes.environment",
            value={"COLLECTION": "notes-${opt:stage}", "PUBLIC_URL": "https://api-${opt:stage}.example.com"}),
          S("invoke_local", function="notes", method="GET", path="/notes"),
      ],
      final="""Fixed. Both values now use `${opt:stage}`, the effective stage of the command [docs/configuration.md#variables]:

```yaml
environment:
  COLLECTION: notes-${opt:stage}
  PUBLIC_URL: https://api-${opt:stage}.example.com
```

- validate (gcp, staging): valid.
- invoke with stage staging: `{"collection": "notes-staging", "url": "https://api-staging.example.com"}`.

If prod should use `https://api.example.com` without a stage, put that one value under `stages.prod`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 560
    B(560, provider="aws", stage="staging", mode="ask", page="Deploy", persona="terse_expert",
      sources=["docs/configuration.md#hooks"],
      project=dict(files={
          "pskit.yml": """service: orders-api
provider:
  name: aws
  region: eu-west-1
functions:
  health:
    handler: app.api.health
    events:
    - http: GET /health
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def health(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="after every deploy run scripts/smoke_test.py, fail loud if it fails",
      steps=[
          S("get_project"),
          S("search_docs", query="after_deploy hook",
            docs=[D("docs/configuration.md", "hooks")]),
          S("propose_plan", steps=["Write scripts/smoke_test.py: print the stage, exit non-zero on failure (placeholder check for now)",
                                   "hooks.after_deploy = [\"python scripts/smoke_test.py\"]",
                                   "Validate aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="scripts/smoke_test.py", content=FUTURE + """import os
import sys


def main() -> int:
    stage = os.environ.get("PSKIT_STAGE", "?")
    print(f"smoke test for {os.environ.get('PSKIT_SERVICE', '?')} on stage {stage}")
    # TODO: call GET /health (URL from `pskit info`) and return 1 when it isn't 200
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""),
          S("set_config", path="hooks", value={"after_deploy": ["python scripts/smoke_test.py"]}),
          S("invoke_local", function="health", method="GET", path="/health"),
      ],
      final="""```yaml
hooks:
  after_deploy: ["python scripts/smoke_test.py"]
```

- Hooks run through the shell in the project root with `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and `PSKIT_WORK_DIR` set; a non-zero exit aborts the command, so a failing smoke test makes the deploy fail loudly [docs/configuration.md#hooks].
- `scripts/smoke_test.py` is a placeholder: fill in the TODO (call `/health`, return 1 on a bad status).
- validate (aws, staging): valid. `GET /health` (what the smoke test will call) answers 200 `{"ok": true}` locally.

It runs on the next **Deploy** or `pskit deploy -s staging`."""),
]
