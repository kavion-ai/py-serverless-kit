"""Category B (build / add), batch 34 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 661
    B(661, provider="aws", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: star-ratings
provider:
  name: aws
  region: eu-west-2
functions: {}
""",
          "requirements.txt": ""}),
      user="customers should give my product 1 to 5 stars and see the average. keep it simple",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/ratings.py: POST /ratings {stars 1-5} and GET /ratings {count, average}, kept in memory for now",
                                   "Add function ratings with both routes",
                                   "Validate for aws, try a rating locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/ratings.py", content=FUTURE + """from py_serverless_kit import BadRequest

STARS = []  # in memory: lost on restart, separate per instance


def ratings(event, ctx):
    if event.http.method == "POST":
        stars = (event.http.json(default={}) or {}).get("stars")
        if not isinstance(stars, int) or not 1 <= stars <= 5:
            raise BadRequest("stars must be a whole number from 1 to 5")
        STARS.append(stars)
    count = len(STARS)
    average = round(sum(STARS) / count, 2) if count else None
    return {"count": count, "average": average}
"""),
          S("set_config", path="functions.ratings",
            value={"handler": "app.ratings.ratings", "events": [{"http": "GET /ratings"}, {"http": "POST /ratings"}]}),
          S("invoke_local", function="ratings", method="POST", path="/ratings", data={"stars": 4}),
      ],
      final="""Your rating function is ready:

- **POST /ratings** with `{"stars": 4}` saves a rating and answers with the new count and average. Anything other than 1–5 → 400.
- **GET /ratings** shows `{"count", "average"}`.

Checks: `pskit validate` (aws) valid; a 4-star rating returned `{"count": 1, "average": 4.0}`.

Simple on purpose: ratings live in memory, so they reset when the function restarts and each running copy counts on its own. When you want them kept for good, ask me to add a database (on AWS, for example DynamoDB). Try it on **Test** > **▶ Run locally**; publish with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 662
    B(662, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/events.md#events-backed-by-a-resource"],
      project=dict(files={
          "pskit.yml": """service: doc-index
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, doc-index-dev}
resources:
  manuals:
    type: storage
    name: doc-index-manuals-3301
functions: {}
""",
          "requirements.txt": ""}),
      user="Function `sync-index` keeps a search index of the `manuals` resource in step with the bucket: it must run for created AND deleted objects, only under `published/` and only for `.pdf`. Log 'add' or 'remove' with the key.",
      steps=[
          S("get_project"),
          S("search_docs", query="gcs storage created deleted prefix suffix",
            docs=[D("docs/events.md", "storage", start="| Provider | Service | Filters | Notes |", end="| gcp |")]),
          S("propose_plan", steps=["Write app/index.py: action created -> add, deleted -> remove",
                                   "functions.sync-index: storage {resource: manuals, events: [created, deleted], prefix: published/, suffix: .pdf}",
                                   "Validate for gcp, invoke a deleted record"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/index.py", content=FUTURE + """

def sync_index(event, ctx):
    changes = []
    for record in event.records:
        op = "add" if record.action == "created" else "remove"
        ctx.logger.info(op, extra={"key": record.key})
        changes.append({"op": op, "key": record.key})
    return {"changes": changes}
"""),
          S("set_config", path="functions.sync-index",
            value={"handler": "app.index.sync_index",
                   "events": [{"storage": {"resource": "manuals", "events": ["created", "deleted"],
                                           "prefix": "published/", "suffix": ".pdf"}}]}),
          S("invoke_local", function="sync-index", type="storage",
            data={"bucket": "doc-index-manuals-3301", "key": "published/pump-x2.pdf", "action": "deleted"}),
      ],
      final="""```yaml
functions:
  sync-index:
    handler: app.index.sync_index
    events:
      - storage:
          resource: manuals
          events: [created, deleted]
          prefix: published/
          suffix: .pdf
```

- `resource: manuals` uses the bucket `doc-index-manuals-3301` [docs/events.md#events-backed-by-a-resource].
- On GCP, `created` and `deleted` become separate Eventarc deployments, and prefix/suffix are applied by the pskit runtime [docs/events.md#storage]. Your handler just checks `record.action`.
- `pskit validate` (gcp): valid.
- Deleted `published/pump-x2.pdf` → log `remove`, `{"changes": [{"op": "remove", "key": "published/pump-x2.pdf"}]}`.

Test the other case on **Test** with `"action": "created"`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 663
    B(663, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: csv-drop
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="azure container `imports`, fn run when csv come in folder in/ and also when csv deleted",
      steps=[
          S("get_project"),
          S("search_docs", query="azure blob trigger deleted",
            docs=[D("docs/events.md", "storage", start="| azure |", end="| azure |")]),
          S("ask_user", say="Azure blob triggers only fire for created or updated blobs; there is no delete event.",
            question="Should I set it up for new/updated CSV files only?",
            options=["Yes, created only", "No, I need deletes, let's look at another way first"],
            answer="Yes, created only"),
          S("propose_plan", steps=["Write app/imports.py: log each new CSV (key, size)",
                                   "functions.import-csv: storage {bucket: imports, prefix: in/, suffix: .csv} (created)",
                                   "Validate for azure, invoke"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/imports.py", content=FUTURE + """

def import_csv(event, ctx):
    for record in event.records:
        ctx.logger.info("csv arrived", extra={"key": record.key, "size": record.size})
    return {"files": [r.key for r in event.records]}
"""),
          S("set_config", path="functions.import-csv",
            value={"handler": "app.imports.import_csv",
                   "events": [{"storage": {"bucket": "imports", "prefix": "in/", "suffix": ".csv"}}]}),
          S("invoke_local", function="import-csv", type="storage",
            data={"bucket": "imports", "key": "in/customers.csv", "size": 2048}),
      ],
      final="""Set up for new and updated CSVs only, as you chose:

```yaml
functions:
  import-csv:
    handler: app.imports.import_csv
    events:
      - storage: {bucket: imports, prefix: in/, suffix: .csv}
```

- pskit creates the container `imports`; the blob trigger fires on created/updated blobs only, so deletes can't trigger it on Azure [docs/events.md#storage]. Adding `deleted` would fail validation.
- `pskit validate` (azure): valid.
- Test with `in/customers.csv` → `csv arrived` log, `{"files": ["in/customers.csv"]}`.

If you later need deletes, the uploader could also send a message to a queue when it removes a file. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 664
    B(664, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#aws-aws-lambda", "docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: video-tools
provider:
  name: aws
  region: us-east-1
functions:
  stitch:
    handler: app.video.stitch
    memory: 3008
    timeout: 600
""",
          "app/__init__.py": "",
          "app/video.py": FUTURE + """

def stitch(event, ctx):
    return {"stitched": True}
""",
          "requirements.txt": ""}),
      user="In SAM, stitch had `EphemeralStorage: Size: 4096` because it writes big temp files to /tmp. How do I get the bigger /tmp in pskit?",
      steps=[
          S("get_project"),
          S("search_docs", query="aws function options merged lambda escape hatch",
            docs=[D("docs/providers.md", "aws-aws-lambda", start="**Options**", end="**Resources:**")]),
          S("propose_plan", steps=["functions.stitch.options: {ephemeral_storage: {size: 4096}} (merged into aws_lambda_function)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.stitch.options", value={"ephemeral_storage": {"size": 4096}}),
      ],
      final="""pskit has no portable key for `/tmp` size, but function `options` are merged into the `aws_lambda_function` resource [docs/providers.md#aws-aws-lambda], so the Terraform argument works:

```yaml
functions:
  stitch:
    handler: app.video.stitch
    memory: 3008
    timeout: 600
    options:
      ephemeral_storage: {size: 4096}
```

- `ephemeral_storage.size` is in MB, like SAM's `Size`.
- `pskit validate` (aws): valid. Validate doesn't check `options` contents [docs/configuration.md#functions]; the AWS provider checks the value at deploy.

This setting is AWS-only; keep it under `providers.aws` if the service also targets another cloud. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 665
    B(665, provider="gcp", stage="dev", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#fields", "docs/resources.md#secrets"],
      project=dict(files={
          "pskit.yml": """service: leaderboard
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, leaderboard-dev}
functions:
  top:
    handler: app.board.top
    events:
    - http: GET /top
  submit:
    handler: app.board.submit
    events:
    - http: POST /scores
  report:
    handler: app.board.report
    events:
    - schedule: 1 day
""",
          "app/__init__.py": "",
          "app/board.py": FUTURE + """

def top(event, ctx):
    return {"top": []}


def submit(event, ctx):
    return {"ok": True}, 201


def report(event, ctx):
    return {"sent": True}
""",
          "requirements.txt": ""}),
      user="memorystore redis exists: host env REDIS_HOST (default localhost for dev), port 6379, auth string in env REDIS_AUTH. bind to top + submit only. top returns redis host:port for now",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.scores-cache: type cache, external true, connection {host: ${env:REDIS_HOST, localhost}, port: 6379, auth_env: REDIS_AUTH}, functions [top, submit]",
                                   "app/board.py top: return host:port from resource(\"scores-cache\")",
                                   "Validate gcp, invoke GET /top"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources",
            value={"scores-cache": {"type": "cache", "external": True,
                                    "connection": {"host": "${env:REDIS_HOST, localhost}", "port": 6379, "auth_env": "REDIS_AUTH"},
                                    "functions": ["top", "submit"]}}),
          S("write_file", path="app/board.py", content=FUTURE + """from py_serverless_kit import resource


def top(event, ctx):
    cache = resource("scores-cache")
    return {"cache": f'{cache["host"]}:{cache["port"]}', "top": []}


def submit(event, ctx):
    return {"ok": True}, 201


def report(event, ctx):
    return {"sent": True}
"""),
          S("validate"),
          S("invoke_local", function="top", method="GET", path="/top"),
      ],
      final="""```yaml
resources:
  scores-cache:
    type: cache
    external: true
    connection:
      host: ${env:REDIS_HOST, localhost}
      port: 6379
      auth_env: REDIS_AUTH
    functions: [top, submit]
```

- `cache` resources are always external; pskit only passes the connection [docs/resources.md#fields]. `report` doesn't get it.
- The AUTH string stays out of the file: only its variable name `REDIS_AUTH` is stored; read it with `ctx.env[cache["auth_env"]]` [docs/resources.md#secrets].
- `pskit validate` (gcp): valid. GET /top → `{"cache": "localhost:6379", "top": []}`.

Memorystore has only a private IP, so the deployed functions also need VPC access to reach it. Deploy: **Deploy** or `pskit deploy -s dev` (with REDIS_HOST set)."""),

    # ------------------------------------------------------------------ 666
    B(666, provider="azure", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: newsletter-form
provider:
  name: azure
  region: westeurope
functions:
  thanks:
    handler: app.form.thanks
    events:
    - http: GET /thanks
""",
          "app/__init__.py": "",
          "app/form.py": FUTURE + """from py_serverless_kit import Response


def thanks(event, ctx):
    return Response.html("<h1>Thanks for subscribing!</h1>")
""",
          "requirements.txt": ""}),
      user="Our plain HTML form posts `email` (application/x-www-form-urlencoded) to POST /subscribe. After a valid submit the browser must be redirected to /thanks with a 303, so a page refresh doesn't resubmit. An invalid email should redirect to /?error=email.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/form.py: subscribe() reads event.http.form(), checks the email, Response.redirect(..., status=303)",
                                   "Add function subscribe on POST /subscribe",
                                   "Validate for azure, invoke with a form body"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/form.py", content=FUTURE + """from py_serverless_kit import Response


def thanks(event, ctx):
    return Response.html("<h1>Thanks for subscribing!</h1>")


def subscribe(event, ctx):
    email = (event.http.form().get("email") or "").strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        return Response.redirect("/?error=email", status=303)
    ctx.logger.info("new subscriber", extra={"domain": email.split("@")[-1]})
    # TODO: store the subscriber
    return Response.redirect("/thanks", status=303)
"""),
          S("set_config", path="functions.subscribe", value={"handler": "app.form.subscribe", "events": [{"http": "POST /subscribe"}]}),
          S("invoke_local", function="subscribe", method="POST", path="/subscribe", data="email=ana%40example.com"),
      ],
      final="""POST /subscribe is in place (Post/Redirect/Get):

- Reads the form with `event.http.form()` [docs/handlers.md#httprequest].
- Valid email → `303 See Other` to `/thanks`; invalid → 303 to `/?error=email`, via `Response.redirect(..., status=303)` [docs/handlers.md#returning-a-response].
- Only the email's domain is logged; storing the subscriber is a TODO.

Checks: `pskit validate` (azure) valid; a local POST with `email=ana%40example.com` → 303, `location: /thanks`.

Test again on **Test** (body `email=...`). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 667
    B(667, provider="aws", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: orders
provider:
  name: aws
  region: eu-west-1
functions:
  create:
    handler: app.orders.create
    environment:
      TABLE: orders-dev
    events:
    - http: POST /orders
  get:
    handler: app.orders.get
    environment:
      TABLE: orders-dev
    events:
    - http: GET /orders/{id}
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def create(event, ctx):
    return {"table": ctx.env["TABLE"]}, 201


def get(event, ctx):
    return {"table": ctx.env["TABLE"], "id": event.http.path_params["id"]}
""",
          "requirements.txt": ""}),
      user="rename env TABLE -> ORDERS_TABLE in both fns + code. TABLE clashes with a lib",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.create/get.environment: TABLE -> ORDERS_TABLE",
                                   "app/orders.py: ctx.env[\"ORDERS_TABLE\"]",
                                   "Validate aws, invoke both"]),
          S("set_config", path="functions.create.environment", value={"ORDERS_TABLE": "orders-dev"}),
          S("set_config", path="functions.get.environment", value={"ORDERS_TABLE": "orders-dev"}),
          S("write_file", path="app/orders.py", content=FUTURE + """

def create(event, ctx):
    return {"table": ctx.env["ORDERS_TABLE"]}, 201


def get(event, ctx):
    return {"table": ctx.env["ORDERS_TABLE"], "id": event.http.path_params["id"]}
"""),
          S("validate"),
          S("invoke_local", function="get", method="GET", path="/orders/7"),
          S("invoke_local", function="create", method="POST", path="/orders", data={"sku": "a"}),
      ],
      final="""Renamed in all three places:

```yaml
functions:
  create:
    environment: {ORDERS_TABLE: orders-dev}
  get:
    environment: {ORDERS_TABLE: orders-dev}
```

- app/orders.py reads `ctx.env["ORDERS_TABLE"]`.
- `pskit validate` (aws): valid. GET /orders/7 → `{"table": "orders-dev", "id": "7"}`; POST /orders → 201 `{"table": "orders-dev"}`.

Deploy: **Deploy** or `pskit deploy -s dev`; the old `TABLE` variable disappears from both Lambdas."""),

    # ------------------------------------------------------------------ 668
    B(668, provider="gcp", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#functions", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: ticketing
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, ticketing-1}
functions:
  checkout:
    handler: app.shop.checkout
    events:
    - http: POST /checkout
""",
          "app/__init__.py": "",
          "app/shop.py": FUTURE + """

def checkout(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="Concert sales open Friday. `checkout` may scale to at most 50 instances in prod (our database can't take more connections), and in dev and staging cap it at 2 so nobody burns money by load testing there.",
      steps=[
          S("get_project"),
          S("search_docs", query="concurrency max instances function",
            docs=[D("docs/configuration.md", "functions", start="| `concurrency` |", end="| `concurrency` |")]),
          S("propose_plan", steps=["functions.checkout.concurrency: 2 (dev/staging default)",
                                   "stages.prod.functions.checkout.concurrency: 50",
                                   "Validate for gcp in prod and dev"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.checkout.concurrency", value=2),
          S("set_config", path="stages", value={"prod": {"functions": {"checkout": {"concurrency": 50}}}}),
          S("validate", provider="gcp"),
      ],
      final="""```yaml
functions:
  checkout:
    handler: app.shop.checkout
    concurrency: 2
    events:
      - http: POST /checkout
stages:
  prod:
    functions:
      checkout:
        concurrency: 50
```

- On GCP `concurrency` is the max instance count [docs/configuration.md#functions]: 50 in prod, 2 everywhere else via the base value and the prod override [docs/configuration.md#stages-per-stage-overrides].
- `pskit validate` (gcp, prod): valid.

The cap protects the database from too many connections. Deploy prod before Friday: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 669
    B(669, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: photo-share
provider:
  name: azure
  region: westeurope
functions:
  upload:
    handler: app.photos.upload
    events:
    - http: POST /photos
""",
          "app/__init__.py": "",
          "app/photos.py": FUTURE + """

def upload(event, ctx):
    return {"stored": True}, 201
""",
          "requirements.txt": ""}),
      user="can you add a cleanup job that deletes old temporary files every night?",
      steps=[
          S("get_project"),
          S("ask_user", question="What time should the nightly cleanup run? (Azure timers run in UTC)",
            options=["01:00 UTC", "03:00 UTC", "05:00 UTC"], answer="03:00 UTC"),
          S("propose_plan", steps=["Add cleanup() to app/photos.py (stub that logs and returns a count)",
                                   "Add function nightly-cleanup with schedule \"0 3 * * *\"",
                                   "Validate for azure, run the schedule"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/photos.py", content=FUTURE + """

def upload(event, ctx):
    return {"stored": True}, 201


def cleanup(event, ctx):
    # TODO: list temporary files older than 24 hours and delete them
    ctx.logger.info("nightly cleanup started")
    return {"deleted": 0}
"""),
          S("set_config", path="functions.nightly-cleanup",
            value={"handler": "app.photos.cleanup", "events": [{"schedule": "0 3 * * *"}]}),
          S("invoke_local", function="nightly-cleanup", type="schedule"),
      ],
      final="""Added `nightly-cleanup`, running every night at 03:00 UTC:

```yaml
functions:
  nightly-cleanup:
    handler: app.photos.cleanup
    events:
      - schedule: "0 3 * * *"
```

- The five fields are minute, hour, day, month, weekday [docs/events.md#schedule]. Azure timers always use UTC.
- The deleting part is still a TODO in `cleanup()`; tell me where the temporary files are kept and I'll fill it in.
- `pskit validate` (azure): valid. A test run returned `{"deleted": 0}`.

Run it again on **Test** (schedule event) or with `pskit invoke -f nightly-cleanup -t schedule`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 670
    B(670, provider="aws", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: invoices-due
provider:
  name: aws
  region: eu-west-1
functions:
  remind:
    handler: app.dunning.remind
  escalate:
    handler: app.dunning.escalate
workflows:
  dunning:
    start_at: Remind
    states:
      Remind:
        type: task
        function: remind
        next: Escalate
      Escalate:
        type: task
        function: escalate
        end: true
""",
          "app/__init__.py": "",
          "app/dunning.py": FUTURE + """

def remind(event, ctx):
    return {**(event.data or {}), "reminded": True}


def escalate(event, ctx):
    return {**(event.data or {}), "escalated": True}
""",
          "requirements.txt": ""}),
      user="in dunning wf i want wait 2 hours between remind and escalate. now it go directly",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Insert wait state Wait2h (seconds 7200) between Remind and Escalate",
                                   "Remind.next -> Wait2h, Wait2h.next -> Escalate",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.dunning.states.Wait2h", value={"type": "wait", "seconds": 7200, "next": "Escalate"}),
          S("set_config", path="workflows.dunning.states.Remind.next", value="Wait2h"),
      ],
      final="""Added a 2-hour wait:

```yaml
workflows:
  dunning:
    start_at: Remind
    states:
      Remind: {type: task, function: remind, next: Wait2h}
      Wait2h: {type: wait, seconds: 7200, next: Escalate}
      Escalate: {type: task, function: escalate, end: true}
```

- A `wait` state just sleeps [docs/workflows.md#state-types]; in Step Functions the waiting time costs nothing.
- `pskit validate` (aws): valid.

Local runs skip wait states unless you pass `--sleep`, so `pskit workflow run dunning -i '{"invoice": "inv-4"}' --history` finishes at once. In studio this is **Workflows > Add state**. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 671
    B(671, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: click-counter
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, click-counter-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="on my page there's a big button. i want to count how many people click it and show the number",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/clicks.py: POST /click adds one, GET /clicks shows the total (in memory for now)",
                                   "Add function clicks with both routes",
                                   "Validate for gcp, click once locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/clicks.py", content=FUTURE + """
COUNT = {"clicks": 0}  # in memory: resets on restart, one count per instance


def clicks(event, ctx):
    if event.http.method == "POST":
        COUNT["clicks"] += 1
    return {"clicks": COUNT["clicks"]}
"""),
          S("set_config", path="functions.clicks",
            value={"handler": "app.clicks.clicks", "events": [{"http": "GET /clicks"}, {"http": "POST /click"}]}),
          S("invoke_local", function="clicks", method="POST", path="/click"),
      ],
      final="""Your counter is ready:

- Your button calls **POST /click**, which adds one and returns the new number.
- **GET /clicks** shows the number without counting.

Checks: `pskit validate` (gcp) valid; one test click returned `{"clicks": 1}`.

The count is kept in memory: it starts at 0 again when the function restarts, and Google may run several copies that each count separately. That's fine for trying it out; for a real total, ask me to store it in Firestore or a database. Try it on **Test** > **▶ Run locally**, then **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 672
    B(672, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#azure-one-function-app-per-service", "docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: claims-processing
provider:
  name: azure
  region: westeurope
functions:
  api:
    handler: app.claims.api
    events:
    - http: POST /claims
  worker:
    handler: app.claims.worker
    events:
    - queue: claims
""",
          "app/__init__.py": "",
          "app/claims.py": FUTURE + """

def api(event, ctx):
    return {"queued": True}, 202


def worker(event, ctx):
    ctx.logger.debug("batch", extra={"n": len(event.records)})
    return {"done": len(event.records)}
""",
          "requirements.txt": ""}),
      user="I want `worker` to log at DEBUG while `api` stays at INFO. Set LOG_LEVEL per function please.",
      steps=[
          S("get_project"),
          S("search_docs", query="azure environment app-wide function app",
            docs=[D("docs/events.md", "azure-one-function-app-per-service")]),
          S("propose_plan", steps=["Try functions.worker.environment.LOG_LEVEL DEBUG and functions.api.environment.LOG_LEVEL INFO",
                                   "Validate for azure and check for the app-wide conflict warning"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.worker.environment", value={"LOG_LEVEL": "DEBUG"}),
          S("set_config", path="functions.api.environment", value={"LOG_LEVEL": "INFO"}),
          S("set_config", say="Validate warns about the conflict, as expected on Azure. I'll keep only the worker setting.",
            path="functions.api.environment", value=None),
          S("invoke_local", function="worker", type="queue", data=[{"claim": 1}]),
      ],
      final="""Not possible per function on Azure: all functions live in **one Function App**, so `environment` is app-wide [docs/events.md#azure-one-function-app-per-service]. Validate printed a warning for the two different `LOG_LEVEL` values, so I removed the `api` one:

```yaml
functions:
  worker:
    handler: app.claims.worker
    environment: {LOG_LEVEL: DEBUG}
```

Result: on Azure **both** functions log at DEBUG (one app-wide value). `pskit validate` (azure): valid, no warning. A local worker run returned `{"done": 1}`.

If `api` must stay at INFO, a log level in one setting can't do that on Azure. The alternatives are to log at INFO in `api`'s code and accept the extra worker logs, or to put `worker` in its own pskit service. On AWS and GCP per-function `environment` works as you expected [docs/handlers.md#environment-variables]. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 673
    B(673, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: recipes
provider:
  name: aws
  region: eu-west-1
functions:
  recipes:
    handler: app.recipes.list_recipes
    events:
    - http: GET /recipes
""",
          "app/__init__.py": "",
          "app/recipes.py": FUTURE + """

def list_recipes(event, ctx):
    return [{"name": "pancakes"}]
""",
          "requirements.txt": ""}),
      user="my react app runs on http://localhost:3000 while I develop and it can't call my api (CORS error). later the real site is https://recipes.example.com. help?",
      steps=[
          S("get_project"),
          S("search_docs", query="cors origins", docs=[D("docs/events.md", "http", start="**CORS**", end="AWS additionally configures CORS on the HTTP API.")]),
          S("propose_plan", steps=["recipes event: cors origins [https://recipes.example.com] (staging/prod)",
                                   "stages.dev: same event with origins [http://localhost:3000]",
                                   "Validate for aws (dev and prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.recipes.events",
            value=[{"http": {"path": "/recipes", "method": "GET", "cors": {"origins": ["https://recipes.example.com"]}}}]),
          S("set_config", path="stages",
            value={"dev": {"functions": {"recipes": {"events": [
                {"http": {"path": "/recipes", "method": "GET", "cors": {"origins": ["http://localhost:3000"]}}}]}}}}),
          S("validate", provider="aws"),
      ],
      final="""Your browser blocks the call because the API didn't say "localhost:3000 may call me". Now it does, per stage:

```yaml
functions:
  recipes:
    handler: app.recipes.list_recipes
    events:
      - http:
          path: /recipes
          method: GET
          cors: {origins: ["https://recipes.example.com"]}
stages:
  dev:
    functions:
      recipes:
        events:
          - http:
              path: /recipes
              method: GET
              cors: {origins: ["http://localhost:3000"]}
```

- Your **dev** API allows `http://localhost:3000`; staging and prod allow only the real site [docs/events.md#http] [docs/configuration.md#stages-per-stage-overrides].
- `pskit validate` (aws, dev): valid.

The change counts once it's deployed: **Deploy** or `pskit deploy -s dev`, then reload your React app."""),

    # ------------------------------------------------------------------ 674
    B(674, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/configuration.md#functions", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: imports
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, imports-prod-9}
functions:
  fetch:
    handler: app.jobs.fetch
  load:
    handler: app.jobs.load
workflows:
  daily-import:
    start_at: Fetch
    states:
      Fetch: {type: task, function: fetch, next: Load}
      Load: {type: task, function: load, end: true}
  legacy-import:
    start_at: Fetch
    states:
      Fetch: {type: task, function: fetch, end: true}
""",
          "app/__init__.py": "",
          "app/jobs.py": FUTURE + """

def fetch(event, ctx):
    return {"rows": 0}


def load(event, ctx):
    return {"loaded": 0}
""",
          "requirements.txt": ""}),
      user="legacy-import off in prod only, keep definition. dev/staging keep it",
      steps=[
          S("get_project"),
          S("search_docs", query="enabled false workflow", docs=[D("docs/configuration.md", "functions", start="| `enabled` |", end="| `enabled` |")]),
          S("propose_plan", steps=["stages.prod.workflows.legacy-import.enabled: false",
                                   "Validate gcp prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages", value={"prod": {"workflows": {"legacy-import": {"enabled": False}}}}),
      ],
      final="""```yaml
stages:
  prod:
    workflows:
      legacy-import:
        enabled: false
```

- Workflows take `enabled` like functions [docs/configuration.md#functions]; the prod override skips it on deploy, the definition stays [docs/configuration.md#stages-per-stage-overrides].
- `pskit validate` (gcp, prod): valid, with the expected warning `disabled (enabled: false): not deployed`; prod now has 1 workflow, `daily-import`.

The next prod deploy removes the existing `legacy-import` Cloud Workflow: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 675
    B(675, provider="azure", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#hooks"],
      project=dict(files={
          "pskit.yml": """service: status-page
provider:
  name: azure
  region: westeurope
functions:
  version:
    handler: app.version.version
    events:
    - http: GET /version
""",
          "app/__init__.py": "",
          "app/version.py": FUTURE + """

def version(event, ctx):
    return {"version": "unknown"}
""",
          "requirements.txt": ""}),
      user="Before every package, run scripts/write_build_info.py, which writes app/build_info.json with the stage and build time. GET /version should return that file's content, or {\"version\": \"unknown\"} if the file is missing (e.g. local runs before packaging).",
      steps=[
          S("get_project"),
          S("search_docs", query="hooks before_package", docs=[D("docs/configuration.md", "hooks")]),
          S("propose_plan", steps=["Write scripts/write_build_info.py (uses PSKIT_STAGE set by pskit for hooks)",
                                   "hooks.before_package: [python scripts/write_build_info.py]",
                                   "app/version.py: read app/build_info.json next to the module, fallback unknown",
                                   "Validate for azure, invoke GET /version"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="scripts/write_build_info.py", content=FUTURE + """import json
import os
from datetime import datetime, timezone
from pathlib import Path

info = {
    "service": os.environ.get("PSKIT_SERVICE", "?"),
    "stage": os.environ.get("PSKIT_STAGE", "?"),
    "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
Path("app/build_info.json").write_bytes(json.dumps(info, indent=2).encode("utf-8"))
print("wrote app/build_info.json")
"""),
          S("set_config", path="hooks", value={"before_package": ["python scripts/write_build_info.py"]}),
          S("write_file", path="app/version.py", content=FUTURE + """import json
from pathlib import Path

INFO_FILE = Path(__file__).with_name("build_info.json")


def version(event, ctx):
    try:
        return json.loads(INFO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": "unknown"}
"""),
          S("validate"),
          S("invoke_local", function="version", method="GET", path="/version"),
      ],
      final="""```yaml
hooks:
  before_package: ["python scripts/write_build_info.py"]
```

- The hook runs in the project root with `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and `PSKIT_WORK_DIR` set; a non-zero exit stops the package [docs/configuration.md#hooks].
- scripts/write_build_info.py writes `app/build_info.json` (service, stage, build time), which is then bundled with `app/`.
- GET /version returns that file, or `{"version": "unknown"}` if it's missing.

Checks: `pskit validate` (azure) valid; local GET /version → `{"version": "unknown"}`, correct since nothing was packaged yet. After `pskit package` (or **Deploy > Package**) it returns the build info. Add `app/build_info.json` to .gitignore. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 676
    B(676, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: reporting
provider:
  name: aws
  region: eu-west-1
functions:
  dashboard:
    handler: app.reports.dashboard
    events:
    - http: GET /dashboard
  export:
    handler: app.reports.export
    events:
    - schedule: "0 1 * * *"
""",
          "app/__init__.py": "",
          "app/reports.py": FUTURE + """

def dashboard(event, ctx):
    return {"widgets": []}


def export(event, ctx):
    return {"exported": 0}
""",
          "requirements.txt": ""}),
      user="export needs s3:PutObject on arn:aws:s3:::reports-archive/exports/*. ONLY export, dashboard no",
      steps=[
          S("get_project"),
          S("search_docs", query="function iam statements dedicated role",
            docs=[D("docs/configuration.md", "functions", start="| `iam` |", end="| `iam` |")]),
          S("propose_plan", steps=["functions.export.iam.statements: [{actions: [s3:PutObject], resources: [arn:aws:s3:::reports-archive/exports/*]}]",
                                   "Validate aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.export.iam",
            value={"statements": [{"actions": ["s3:PutObject"], "resources": ["arn:aws:s3:::reports-archive/exports/*"]}]}),
      ],
      final="""```yaml
functions:
  export:
    handler: app.reports.export
    iam:
      statements:
        - {actions: ["s3:PutObject"], resources: ["arn:aws:s3:::reports-archive/exports/*"]}
```

- Function-level `iam` gives `export` a dedicated role with this statement added to the provider-level ones [docs/configuration.md#functions]. `dashboard` keeps its role without it.
- `pskit validate` (aws): valid.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 677
    B(677, provider="gcp", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: mobile-backend
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, mobile-backend-stg}
functions:
  profile:
    handler: app.profile.get
    events:
    - http: GET /profile
""",
          "app/__init__.py": "",
          "app/profile.py": FUTURE + """

def get(event, ctx):
    return {"name": "demo"}
""",
          "requirements.txt": ""}),
      user="add GET /version return service + stage, app team need it",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/meta.py: version() returns ctx.service and ctx.stage",
                                   "Add function version on GET /version",
                                   "Validate gcp staging, invoke"],
            result={"decision": "approved",
                    "note": "also give the git commit from env GIT_SHA, CI sets it. default unknown"}),
          S("write_file", say="Adding the git commit as you asked.", path="app/meta.py", content=FUTURE + """

def version(event, ctx):
    return {"service": ctx.service, "stage": ctx.stage, "commit": ctx.env.get("GIT_SHA", "unknown")}
"""),
          S("set_config", path="functions.version",
            value={"handler": "app.meta.version", "environment": {"GIT_SHA": "${env:GIT_SHA, unknown}"},
                   "events": [{"http": "GET /version"}]}),
          S("invoke_local", function="version", method="GET", path="/version"),
      ],
      final="""Added `GET /version`, with the commit from your note:

```yaml
functions:
  version:
    handler: app.meta.version
    environment:
      GIT_SHA: ${env:GIT_SHA, unknown}
    events:
      - http: GET /version
```

- `${env:GIT_SHA, unknown}` is read on the machine that runs the deploy, so CI's value is baked in; without it you get `unknown` [docs/configuration.md#variables].
- `pskit validate` (gcp, staging): valid.
- Local GET /version → `{"service": "mobile-backend", "stage": "staging", "commit": "unknown"}`.

In CI: set `GIT_SHA` before `pskit deploy -s staging` (or use **Deploy** locally)."""),

    # ------------------------------------------------------------------ 678
    B(678, provider="azure", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: greeter
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="""GET /greeting picks the language from the Accept-Language header:
- de -> "Hallo", fr -> "Bonjour", es -> "Hola", anything else or missing -> "Hello"
- only the first language in the header counts (e.g. "fr-CH, fr;q=0.9, en;q=0.8" -> fr)
- response {"greeting": ..., "lang": ...}""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/greet.py: read event.http.headers (case-insensitive), take the first tag's primary language",
                                   "Add function greeting on GET /greeting",
                                   "Validate for azure, invoke (no header -> en)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/greet.py", content=FUTURE + """
GREETINGS = {"de": "Hallo", "fr": "Bonjour", "es": "Hola"}


def first_language(header: str) -> str:
    first = header.split(",")[0].split(";")[0].strip()
    return first.split("-")[0].lower()


def greeting(event, ctx):
    lang = first_language(event.http.headers.get("accept-language", ""))
    if lang not in GREETINGS:
        lang = "en"
    return {"greeting": GREETINGS.get(lang, "Hello"), "lang": lang}
"""),
          S("set_config", path="functions.greeting", value={"handler": "app.greet.greeting", "events": [{"http": "GET /greeting"}]}),
          S("invoke_local", function="greeting", method="GET", path="/greeting"),
      ],
      final="""`GET /greeting` is added:

- Reads `Accept-Language` from `event.http.headers`, which is case-insensitive [docs/handlers.md#httprequest]; only the first entry counts, so `fr-CH, fr;q=0.9, en;q=0.8` → `fr` → "Bonjour".
- Unknown or missing → `{"greeting": "Hello", "lang": "en"}`.

Checks: `pskit validate` (azure) valid; a local GET without the header → `{"greeting": "Hello", "lang": "en"}`.

To try a language, send the header from the CLI: `pskit invoke -f greeting --method GET --path /greeting -H "Accept-Language: de-DE"`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 679
    B(679, provider="aws", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: club-app
provider:
  name: aws
  region: eu-west-1
functions:
  members:
    handler: app.club.members
    events:
    - http: GET /members
  join:
    handler: app.club.join
    events:
    - http: POST /members
  remind-fees:
    handler: app.club.remind_fees
    events:
    - schedule: "0 9 1 * *"
""",
          "app/__init__.py": "",
          "app/club.py": FUTURE + """

def members(event, ctx):
    return []


def join(event, ctx):
    return {"joined": True}, 201


def remind_fees(event, ctx):
    return {"reminded": 0}
""",
          "requirements.txt": ""}),
      user="a friend is taking over my project and doesn't understand what each function does. can you write a short description on each one?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Set description on members, join and remind-fees",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.members.description", value="Lists all club members"),
          S("set_config", path="functions.join.description", value="Adds a new member (sign-up form)"),
          S("set_config", path="functions.remind-fees.description", value="On the 1st of each month at 09:00 UTC, reminds members to pay their fee"),
      ],
      final="""Each function now has a description:

```yaml
functions:
  members:
    description: Lists all club members
  join:
    description: Adds a new member (sign-up form)
  remind-fees:
    description: On the 1st of each month at 09:00 UTC, reminds members to pay their fee
```

`description` is a normal function setting [docs/configuration.md#functions]; on AWS it also shows in the Lambda console. `pskit validate` (aws): valid. Nothing else changed.

Your friend can also open **Functions** in studio to see every function with its triggers. The descriptions reach AWS on the next **Deploy** (`pskit deploy -s dev`)."""),

    # ------------------------------------------------------------------ 680
    B(680, provider="gcp", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#provider", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: edge-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, edge-api-dev}
functions:
  lookup:
    handler: app.edge.lookup
    events:
    - http: GET /lookup/{key}
""",
          "app/__init__.py": "",
          "app/edge.py": FUTURE + """

def lookup(event, ctx):
    return {"key": event.http.path_params["key"]}
""",
          "requirements.txt": ""}),
      user="default timeout 10s for whole service. + /ping GET returns pong text",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.timeout: 10",
                                   "app/edge.py: ping() -> \"pong\"; functions.ping on `- http: /ping`",
                                   "Validate gcp, invoke /ping"]),
          S("set_config", path="provider.timeout", value=10),
          S("write_file", path="app/edge.py", content=FUTURE + """

def lookup(event, ctx):
    return {"key": event.http.path_params["key"]}


def ping(event, ctx):
    return "pong"
"""),
          S("set_config", path="functions.ping", value={"handler": "app.edge.ping", "events": [{"http": "/ping"}]}),
          S("invoke_local", function="ping", method="GET", path="/ping"),
      ],
      final="""```yaml
provider:
  timeout: 10
functions:
  ping:
    handler: app.edge.ping
    events:
      - http: /ping
```

- `provider.timeout` is the default for every function without its own [docs/configuration.md#provider].
- `- http: /ping` is the shorthand for GET [docs/events.md#http]; a `str` return is `text/plain`.
- `pskit validate` (gcp): valid; GET /ping → 200 `pong`.

Deploy: **Deploy** or `pskit deploy -s dev`."""),
]
