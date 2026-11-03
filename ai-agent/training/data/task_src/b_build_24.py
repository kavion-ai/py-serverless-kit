"""Category B (build / add), batch 24 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 461
    B(461, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: internal-pricing
provider:
  name: aws
  region: eu-west-1
functions:
  price:
    handler: app.price.get_price
    events:
    - http: GET /price/{sku}
""",
          "app/__init__.py": "",
          "app/price.py": FUTURE + """

def get_price(event, ctx):
    return {"sku": event.http.path_params["sku"], "price": 9.99}
""",
          "requirements.txt": ""}),
      user="`GET /price/{sku}` is only called by our other AWS services, which sign their requests with SigV4 using their IAM roles. Configure the route so API Gateway rejects unsigned requests. No code change.",
      steps=[
          S("get_project"),
          S("search_docs", query="aws http auth iam AWS_IAM",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `jwt` |")]),
          S("propose_plan", steps=["Change the event to {path: /price/{sku}, method: GET, auth: iam}",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.price.events.0",
            value={"http": {"path": "/price/{sku}", "method": "GET", "auth": "iam"}}),
      ],
      final="""Done:

```yaml
functions:
  price:
    events:
      - http: {path: "/price/{sku}", method: GET, auth: iam}
```

- On AWS `auth: iam` becomes the `AWS_IAM` authorizer on the HTTP API route, so unsigned calls are rejected before Lambda runs [docs/events.md#http].
- `pskit validate` (aws): valid. The handler is unchanged.

The calling roles need `execute-api:Invoke` on this API, which you grant in their own policies. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 462
    B(462, provider="gcp", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: data-lake
provider:
  name: gcp
  region: europe-west4
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, data-lake-staging}
functions: {}
""",
          "requirements.txt": ""}),
      user="gcs bucket data-lake-raw, run fn only for .parquet in landing/ folder. pskit make bucket",
      steps=[
          S("get_project"),
          S("search_docs", query="storage prefix suffix gcp filter",
            docs=[D("docs/events.md", "storage", start="| Provider | Service | Filters | Notes |", end="| azure |")]),
          S("propose_plan", steps=["Write `app/lake.py`: log key and size per file, return the keys",
                                   "Add function `land-parquet` with storage {bucket: data-lake-raw, prefix: landing/, suffix: .parquet}",
                                   "Validate gcp (staging), invoke one file"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/lake.py", content=FUTURE + """

def land_parquet(event, ctx):
    keys = []
    for record in event.records:
        ctx.logger.info("landed", extra={"key": record.key, "size": record.size})
        keys.append(record.key)
    return {"landed": keys}
"""),
          S("set_config", path="functions.land-parquet",
            value={"handler": "app.lake.land_parquet",
                   "events": [{"storage": {"bucket": "data-lake-raw", "prefix": "landing/", "suffix": ".parquet"}}]}),
          S("invoke_local", function="land-parquet", type="storage",
            data={"bucket": "data-lake-raw", "key": "landing/sales-2026-11.parquet", "size": 1048576}),
      ],
      final="""Done:

```yaml
functions:
  land-parquet:
    handler: app.lake.land_parquet
    events:
      - storage: {bucket: data-lake-raw, prefix: landing/, suffix: .parquet}
```

- On GCP the Eventarc trigger fires for every new object; the pskit runtime applies `prefix` and `suffix` before calling your code [docs/events.md#storage].
- validate (gcp, staging): valid.
- invoke: `{"landed": ["landing/sales-2026-11.parquet"]}`.

pskit creates the bucket on deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 463
    B(463, provider="azure", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: order-processing
provider:
  name: azure
  region: westeurope
functions:
  process-order:
    handler: app.orders.process
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def process(event, ctx):
    return {"processed": [(r.json(default={}) or {}).get("id") for r in event.records]}
""",
          "requirements.txt": ""}),
      user="On AWS process-order was triggered by the SQS queue `OrderQueue`. Same trigger on Azure please, pskit can create the queue.",
      steps=[
          S("get_project"),
          S("search_docs", query="azure storage queue name rules",
            docs=[D("docs/events.md", "queue", start="On GCP a \"queue\" is a Pub/Sub topic")]),
          S("propose_plan", steps=["Azure queue names must be 3-63 lowercase letters, digits and dashes, so `OrderQueue` becomes `order-queue`",
                                   "Add `- queue: order-queue` to process-order",
                                   "Validate for azure (staging), invoke one message"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.process-order.events", value=[{"queue": "order-queue"}]),
          S("invoke_local", function="process-order", type="queue", data=[{"id": 501}]),
      ],
      final="""Added, with one rename: Azure Storage Queue names must be 3-63 **lowercase** letters, digits and dashes, so `OrderQueue` would fail validation [docs/events.md#queue]. I used `order-queue`:

```yaml
functions:
  process-order:
    events:
      - queue: order-queue
```

- `pskit validate` (azure, staging): valid.
- invoke: `{"processed": [501]}`.

Differences from SQS: no `batch_size`/`batch_window`, failed messages go to `order-queue-poison`, and a failure retries the whole delivery. Update producers to the new name. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 464
    B(464, provider="aws", stage="prod", mode="auto", page="Overview", persona="terse_expert",
      sources=["docs/configuration.md#provider"],
      project=dict(files={
          "pskit.yml": """service: audit-trail
provider:
  name: aws
  region: eu-west-1
functions:
  write:
    handler: app.audit.write
    events:
    - http: POST /audit
""",
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """

def write(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="log retention 90 days, tag owner=platform-team on everything",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.log_retention_days = 90", "provider.tags = {owner: platform-team}", "Validate aws (prod)"]),
          S("set_config", path="provider.log_retention_days", value=90),
          S("set_config", path="provider.tags", value={"owner": "platform-team"}),
      ],
      final="""```yaml
provider:
  log_retention_days: 90
  tags: {owner: platform-team}
```

validate (aws, prod) passed after both. `log_retention_days` sets the CloudWatch log group retention (default 14); provider tags are merged with `pskit-service`, `pskit-stage` and `managed-by` on every resource [docs/configuration.md#provider]. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 465
    B(465, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": """service: payments-router
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, payments-router-dev}
functions:
  handle-sale:
    handler: app.router.sale
  handle-refund:
    handler: app.router.refund
""",
          "app/__init__.py": "",
          "app/router.py": FUTURE + """

def sale(event, ctx):
    return {**(event.data or {}), "handled": "sale"}


def refund(event, ctx):
    return {**(event.data or {}), "handled": "refund"}
""",
          "requirements.txt": ""}),
      user="I get payments with a type field. If the type is refund it should go to handle-refund, everything else to handle-sale. Can you make that?",
      steps=[
          S("get_project"),
          S("search_docs", query="choice equals default branch",
            docs=[D("docs/workflows.md", "choice-rules", end="next: AskEmail")]),
          S("propose_plan", steps=["Add workflow `route-payment`: a choice state CheckType ($.type equals refund -> Refund, default Sale)",
                                   "Refund runs handle-refund, Sale runs handle-sale",
                                   "Validate for gcp and run handle-refund locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.route-payment",
            value={"start_at": "CheckType",
                   "states": {"CheckType": {"type": "choice",
                                            "choices": [{"variable": "$.type", "equals": "refund", "next": "Refund"}],
                                            "default": "Sale"},
                              "Refund": {"type": "task", "function": "handle-refund", "end": True},
                              "Sale": {"type": "task", "function": "handle-sale", "end": True}}}),
          S("invoke_local", function="handle-refund", type="workflow", data={"type": "refund", "amount": 20}),
      ],
      final="""Done. The workflow `route-payment` looks at `type` first:

```yaml
workflows:
  route-payment:
    start_at: CheckType
    states:
      CheckType:
        type: choice
        choices: [{variable: $.type, equals: refund, next: Refund}]
        default: Sale
      Refund: {type: task, function: handle-refund, end: true}
      Sale:   {type: task, function: handle-sale, end: true}
```

- `default: Sale` catches every other type, and also payments without a `type` field [docs/workflows.md#choice-rules].
- `pskit validate` (gcp): valid. On GCP it runs as Cloud Workflows.
- `handle-refund` locally: `"handled": "refund"`.

Try both ways: `pskit workflow run route-payment -i '{"type": "refund", "amount": 20}'` and the same with `"type": "sale"`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 466
    B(466, provider="azure", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#azure-one-function-app-per-service", "docs/handlers.md#invoke-calling-another-function"],
      project=dict(files={
          "pskit.yml": """service: docgen
provider:
  name: azure
  region: westeurope
functions:
  api:
    handler: app.docs.api
    events:
    - http: POST /documents
""",
          "app/__init__.py": "",
          "app/docs.py": FUTURE + """

def api(event, ctx):
    return {"queued": True}, 202
""",
          "requirements.txt": ""}),
      user="add invoke-only fn `render-pdf` (no trigger), input {doc_id}, returns {doc_id, pages}",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `render_pdf` to app/docs.py", "functions.render-pdf with no events",
                                   "Validate azure, invoke -t invoke"]),
          S("write_file", path="app/docs.py", content=FUTURE + """

def api(event, ctx):
    return {"queued": True}, 202


def render_pdf(event, ctx):
    req = dict(event.data or {})
    return {"doc_id": req.get("doc_id"), "pages": 1}
"""),
          S("set_config", path="functions.render-pdf", value={"handler": "app.docs.render_pdf"}),
          S("invoke_local", function="render-pdf", type="invoke", data={"doc_id": "d-42"}),
      ],
      final="""```yaml
functions:
  render-pdf:
    handler: app.docs.render_pdf
```

- validate (azure): valid. invoke: `{"doc_id": "d-42", "pages": 1}`.
- No events = invoke-only. On Azure it gets a key-protected `POST /_pskit/invoke/render-pdf` route [docs/events.md#azure-one-function-app-per-service].

To call it from `api` with `invoke("render-pdf", ...)`, set `PSKIT_ENDPOINT_RENDER_PDF` to that URL; otherwise `invoke()` raises `InvokeError` on Azure [docs/handlers.md#invoke-calling-another-function]. Deploy: `pskit deploy -s dev` or **Deploy**."""),

    # ------------------------------------------------------------------ 467
    B(467, provider="aws", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: photo-tools
provider:
  name: aws
  region: us-east-1
functions:
  thumbnail:
    handler: app.tools.thumbnail
    events:
    - http: POST /thumbnail
  health:
    handler: app.tools.health
    events:
    - http: GET /health
""",
          "app/__init__.py": "",
          "app/tools.py": FUTURE + """

def thumbnail(event, ctx):
    return {"ok": True}


def health(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="my function is slow, can you make it faster?",
      steps=[
          S("get_project"),
          S("ask_user", question="You have two functions. Which one is slow?", options=["thumbnail", "health"],
            answer="thumbnail, resizing big photos takes forever"),
          S("propose_plan", steps=["Raise thumbnail's memory from the default 256 MB to 1024 MB (on Lambda, more memory also means more CPU)",
                                   "Validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.thumbnail.memory", value=1024),
      ],
      final="""I gave `thumbnail` more memory:

```yaml
functions:
  thumbnail:
    memory: 1024
```

- Before, it used the default 256 MB [docs/configuration.md#functions]. On Lambda, CPU grows with memory, so image resizing usually gets faster.
- `pskit validate` (aws, staging): valid.

Memory costs more per second, so compare the times on the **Logs** page after deploy and lower it again if it doesn't help. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 468
    B(468, provider="gcp", stage="prod", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/events.md#events-backed-by-a-resource", "docs/resources.md#fields"],
      project=dict(files={
          "pskit.yml": """service: exports
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, exports-prod}
functions: {}
""",
          "requirements.txt": ""}),
      user="Like an imported S3 bucket in CDK: the GCS bucket `legacy-exports` already exists and another team owns it. Register it as a resource `exports` and add a function `on-export` for new files under `in/`, using the resource.",
      steps=[
          S("get_project"),
          S("search_docs", query="external storage resource event resource prefix",
            docs=[D("docs/events.md", "events-backed-by-a-resource", end="The event uses the resource's native name")]),
          S("propose_plan", steps=["resources.exports: {type: storage, external: true, name: legacy-exports}",
                                   "Write app/exports.py; function on-export with storage {resource: exports, prefix: in/}",
                                   "Validate gcp (prod), invoke one file"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.exports", value={"type": "storage", "external": True, "name": "legacy-exports"}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/exports.py", content=FUTURE + """

def on_export(event, ctx):
    return {"files": [record.key for record in event.records]}
"""),
          S("set_config", path="functions.on-export",
            value={"handler": "app.exports.on_export", "events": [{"storage": {"resource": "exports", "prefix": "in/"}}]}),
          S("invoke_local", function="on-export", type="storage", data={"bucket": "legacy-exports", "key": "in/q3.csv"}),
      ],
      final="""Registered and wired:

```yaml
resources:
  exports:
    type: storage
    external: true
    name: legacy-exports
functions:
  on-export:
    handler: app.exports.on_export
    events:
      - storage: {resource: exports, prefix: in/}
```

- `external: true` is the import: pskit never creates, changes or deletes `legacy-exports` [docs/resources.md#fields]. The event uses its native name with `existing: true`.
- `pskit validate` (gcp, prod): valid.
- invoke: `{"files": ["in/q3.csv"]}`.

The other team must let pskit's trigger read events from their bucket. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 469
    B(469, provider="azure", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#compiler-notes-and-limits"],
      project=dict(files={
          "pskit.yml": """service: kyc-checks
provider:
  name: azure
  region: westeurope
functions:
  check-id:
    handler: app.kyc.check_id
    timeout: 60
  open-account:
    handler: app.kyc.open_account
""",
          "app/__init__.py": "",
          "app/kyc.py": FUTURE + """

def check_id(event, ctx):
    return {**(event.data or {}), "id_ok": True}


def open_account(event, ctx):
    return {**(event.data or {}), "account": "ACC-1"}
""",
          "requirements.txt": ""}),
      user="As a Logic App: CheckId (check-id) then OpenAccount (open-account). check-id calls a flaky ID provider, so retry it up to 4 times starting at 10 seconds. I know Logic Apps retries differently, tell me what actually applies.",
      steps=[
          S("get_project"),
          S("search_docs", query="logic apps retry policy limits",
            docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="- **Azure (Logic Apps):**", words=200)]),
          S("propose_plan", steps=["Add workflow `onboard` with engine: native: CheckId (check-id, retry [{errors: [\"*\"], max_attempts: 4, interval_seconds: 10}]) -> OpenAccount (end)",
                                   "Validate for azure (staging), run check-id locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.onboard",
            value={"engine": "native", "start_at": "CheckId",
                   "states": {"CheckId": {"type": "task", "function": "check-id", "next": "OpenAccount",
                                          "retry": [{"errors": ["*"], "max_attempts": 4, "interval_seconds": 10}]},
                              "OpenAccount": {"type": "task", "function": "open-account", "end": True}}}),
          S("invoke_local", function="check-id", type="workflow", data={"customer": "c-9"}),
      ],
      final="""Added as a Logic App:

```yaml
workflows:
  onboard:
    engine: native
    start_at: CheckId
    states:
      CheckId:
        type: task
        function: check-id
        retry: [{errors: ["*"], max_attempts: 4, interval_seconds: 10}]
        next: OpenAccount
      OpenAccount: {type: task, function: open-account, end: true}
```

What actually applies on Logic Apps [docs/workflows.md#compiler-notes-and-limits]:
- Only the first retry rule is used, as an exponential retry policy that retries 408/429/5xx responses. The `errors` filter and `backoff_rate` are ignored, so I used `"*"`.
- Intervals are 5 s to 1 day, so 10 s is accepted.
- Each task call times out after 120 s. `check-id` has `timeout: 60`, so no warning.

`pskit validate` (azure, staging): valid. `check-id` locally: `"id_ok": true`. Deploy: **Deploy** or `pskit deploy -s staging`; `pskit info` then shows the trigger URL (keep it secret)."""),

    # ------------------------------------------------------------------ 470
    B(470, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: short-links
provider:
  name: aws
  region: eu-central-1
functions: {}
""",
          "requirements.txt": ""}),
      user="short link service: GET /go/{code} redirect to real url. few links fixed in code ok. unknown code 404",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/links.py`: LINKS dict, Response.redirect(url, 302), NotFound otherwise",
                                   "Add function `go` on GET /go/{code}",
                                   "Validate aws, invoke a known code"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/links.py", content=FUTURE + """from py_serverless_kit import NotFound, Response

LINKS = {
    "docs": "https://docs.example.com/",
    "blog": "https://blog.example.com/latest",
}


def go(event, ctx):
    code = event.http.path_params["code"]
    url = LINKS.get(code)
    if url is None:
        raise NotFound(f"no link '{code}'")
    return Response.redirect(url, status=302)
"""),
          S("set_config", path="functions.go", value={"handler": "app.links.go", "events": [{"http": "GET /go/{code}"}]}),
          S("invoke_local", function="go", method="GET", path="/go/docs"),
      ],
      final="""Done. `go` on `GET /go/{code}`:

- known code → **302** redirect with a `location` header; unknown code → 404 (`NotFound`). `Response.redirect(...)` is in [docs/handlers.md#returning-a-response].
- validate (aws): valid.
- invoke `/go/docs`: 302 to `https://docs.example.com/`.

Add links in `LINKS` in `app/links.py`. Retest: `pskit invoke -f go --method GET --path /go/blog`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 471
    B(471, provider="gcp", stage="staging", mode="auto", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: ingest
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, ingest-staging}
functions:
  load:
    handler: app.load.run
""",
          "app/__init__.py": "",
          "app/load.py": FUTURE + """

def run(event, ctx):
    return {"bucket_env": ctx.env.get("RAW_BUCKET"), "files": [r.key for r in event.records]}
""",
          "requirements.txt": ""}),
      user="Put the bucket name `ingest-raw-files` once under `custom.raw_bucket`, and use it both as `load`'s storage trigger bucket and as its RAW_BUCKET environment variable, so it's never typed twice.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["custom.raw_bucket = ingest-raw-files",
                                   "load.events = [storage: ${self:custom.raw_bucket}]; load.environment.RAW_BUCKET = ${self:custom.raw_bucket}",
                                   "Validate gcp (staging), invoke one file"]),
          S("set_config", path="custom", value={"raw_bucket": "ingest-raw-files"}),
          S("set_config", path="functions.load.events", value=[{"storage": "${self:custom.raw_bucket}"}]),
          S("set_config", path="functions.load.environment", value={"RAW_BUCKET": "${self:custom.raw_bucket}"}),
          S("invoke_local", function="load", type="storage", data={"bucket": "ingest-raw-files", "key": "a.json"}),
      ],
      final="""Done:

```yaml
custom:
  raw_bucket: ingest-raw-files
functions:
  load:
    environment:
      RAW_BUCKET: ${self:custom.raw_bucket}
    events:
      - storage: ${self:custom.raw_bucket}
```

- `${self:...}` reads any value of the merged config [docs/configuration.md#variables].
- validate (gcp, staging) passed after each of the three changes.
- invoke: `{"bucket_env": "ingest-raw-files", "files": ["a.json"]}`, so the variable resolved.

Change the name in one place from now on. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 472
    B(472, provider="azure", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: inventory-api
provider:
  name: azure
  region: westeurope
functions:
  items:
    handler: app.items.list_items
    events:
    - http: GET /items
""",
          "app/__init__.py": "",
          "app/items.py": FUTURE + """

def list_items(event, ctx):
    return [{"id": "1", "name": "chair"}]
""",
          "requirements.txt": ""}),
      user="I also need a way to delete an item by its id. What do I add?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `delete_item` to app/items.py: log the id and return nothing (204 No Content)",
                                   "Add function `delete-item` on DELETE /items/{id}",
                                   "Validate for azure (prod), test deleting item 1"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/items.py", content=FUTURE + """

def list_items(event, ctx):
    return [{"id": "1", "name": "chair"}]


def delete_item(event, ctx):
    item_id = event.http.path_params["id"]
    ctx.logger.info("delete item", extra={"item_id": item_id})
    return None
"""),
          S("set_config", path="functions.delete-item",
            value={"handler": "app.items.delete_item", "events": [{"http": "DELETE /items/{id}"}]}),
          S("invoke_local", function="delete-item", method="DELETE", path="/items/1"),
      ],
      final="""I added a new function `delete-item` on `DELETE /items/{id}`:

- It reads the id from the path and answers **204 No Content**, which is what returning `None` does [docs/handlers.md#returning-a-response].
- `pskit validate` (azure, prod): valid.
- Test delete of item 1: status 204.

Right now it only logs the id. Once you have a database, delete the row there. Try it on **Test** > **▶ Run locally** (method DELETE, path `/items/1`) or `pskit invoke -f delete-item --method DELETE --path /items/1`. Deploy prod: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 473
    B(473, provider="aws", stage="staging", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#migrating-step-functions-asl", "docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: loans
provider:
  name: aws
  region: us-east-1
functions:
  score-loan:
    handler: app.loans.score
  approve-loan:
    handler: app.loans.approve
""",
          "app/__init__.py": "",
          "app/loans.py": FUTURE + """

def score(event, ctx):
    app = dict(event.data or {})
    return {**app, "score": 720 if app.get("income", 0) > 50000 else 540}


def approve(event, ctx):
    return {**(event.data or {}), "approved": True}
""",
          "requirements.txt": ""}),
      user="""Translate my ASL: Score (Task score-loan) -> CheckScore (Choice: Variable $.score NumericGreaterThanEquals 650 -> Approve, Default -> Declined). Approve is Task approve-loan, End. Declined is {"Type": "Fail", "Error": "LoanDeclined", "Cause": "score too low"}. Name it loan-decision.""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add workflow `loan-decision`: Score (score-loan) -> CheckScore (choice $.score gte 650 -> Approve, default Declined)",
                                   "Approve: task approve-loan, end; Declined: fail, error LoanDeclined, cause \"score too low\"",
                                   "Validate for aws (staging), run score-loan locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.loan-decision",
            value={"start_at": "Score",
                   "states": {"Score": {"type": "task", "function": "score-loan", "next": "CheckScore"},
                              "CheckScore": {"type": "choice",
                                             "choices": [{"variable": "$.score", "gte": 650, "next": "Approve"}],
                                             "default": "Declined"},
                              "Approve": {"type": "task", "function": "approve-loan", "end": True},
                              "Declined": {"type": "fail", "error": "LoanDeclined", "cause": "score too low"}}}),
          S("invoke_local", function="score-loan", type="workflow", data={"applicant": "a-1", "income": 30000}),
      ],
      final="""Translated:

```yaml
workflows:
  loan-decision:
    start_at: Score
    states:
      Score: {type: task, function: score-loan, next: CheckScore}
      CheckScore:
        type: choice
        choices: [{variable: $.score, gte: 650, next: Approve}]
        default: Declined
      Approve: {type: task, function: approve-loan, end: true}
      Declined: {type: fail, error: LoanDeclined, cause: score too low}
```

`NumericGreaterThanEquals` → `gte`, `Default` → `default`, `Fail` keeps `error`/`cause` [docs/workflows.md#migrating-step-functions-asl].

- `pskit validate` (aws, staging): valid; it compiles back to a Step Functions state machine.
- `score-loan` locally with income 30000: `"score": 540`, so this applicant ends in Declined.

Compare: `pskit workflow show loan-decision --format asl`. Run: `pskit workflow run loan-decision -i '{"income": 30000}' --history` (exits with code 2 for the Fail). Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 474
    B(474, provider="gcp", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: alerts
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, alerts-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="fn `page-oncall` on pubsub `monitoring`, only severity=critical",
      steps=[
          S("get_project"),
          S("search_docs", query="topic filter gcp pubsub",
            docs=[D("docs/events.md", "topic", start="| Provider | Service | `filter` |", end="| gcp |")]),
          S("propose_plan", steps=["Pub/Sub triggers don't apply `filter`, so filter in the handler: skip messages whose severity isn't critical",
                                   "Write app/oncall.py; function page-oncall with `- topic: monitoring`",
                                   "Validate gcp, invoke one critical + one warning"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/oncall.py", content=FUTURE + """

def page_oncall(event, ctx):
    paged = []
    for record in event.records:
        alert = record.json(default={}) or {}
        if alert.get("severity") != "critical":
            continue
        ctx.logger.warning("paging on-call", extra={"alert": alert.get("name")})
        paged.append(alert.get("name"))
    return {"paged": paged}
"""),
          S("set_config", path="functions.page-oncall",
            value={"handler": "app.oncall.page_oncall", "events": [{"topic": "monitoring"}]}),
          S("invoke_local", function="page-oncall", type="topic",
            data=[{"name": "db-down", "severity": "critical"}, {"name": "disk-80", "severity": "warning"}]),
      ],
      final="""```yaml
functions:
  page-oncall:
    handler: app.oncall.page_oncall
    events:
      - topic: monitoring
```

`topic.filter` isn't applied on Pub/Sub, so the severity check is in the handler [docs/events.md#topic].

- validate (gcp): valid.
- invoke (critical + warning): `{"paged": ["db-down"]}`.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 475
    B(475, provider="azure", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: booking
provider:
  name: azure
  region: westeurope
  environment:
    LOG_LEVEL: DEBUG
functions:
  book:
    handler: app.booking.book
    events:
    - http: POST /book
""",
          "app/__init__.py": "",
          "app/booking.py": FUTURE + """

def book(event, ctx):
    return {"booked": True, "log_level": ctx.env.get("LOG_LEVEL")}
""",
          "requirements.txt": ""}),
      user="in dev i want DEBUG logs but in prod only WARNING. now is DEBUG everywhere",
      steps=[
          S("get_project"),
          S("search_docs", query="per stage overrides stages prod",
            docs=[D("docs/configuration.md", "stages-per-stage-overrides")]),
          S("propose_plan", steps=["Keep provider.environment.LOG_LEVEL = DEBUG (dev and others)",
                                   "Add stages.prod.provider.environment.LOG_LEVEL = WARNING",
                                   "Validate for azure (dev) and invoke to check dev still logs DEBUG"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages", value={"prod": {"provider": {"environment": {"LOG_LEVEL": "WARNING"}}}}),
          S("invoke_local", function="book", method="POST", path="/book", data={"room": 4}),
      ],
      final="""Done. Prod gets its own value:

```yaml
provider:
  environment:
    LOG_LEVEL: DEBUG
stages:
  prod:
    provider:
      environment:
        LOG_LEVEL: WARNING
```

- `stages.prod` is merged only when the stage is `prod` [docs/configuration.md#stages-per-stage-overrides]. `LOG_LEVEL` sets the runtime's log level [docs/handlers.md#environment-variables].
- validate (azure, dev): valid.
- invoke in dev: `"log_level": "DEBUG"`.

Check prod with `pskit validate -s prod`. Deploy: **Deploy** or `pskit deploy -s dev` (and `-s prod` for prod)."""),

    # ------------------------------------------------------------------ 476
    B(476, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: orders-api
provider:
  name: aws
  region: eu-west-1
functions:
  create-order:
    handler: app.orders.create
    events:
    - http:
        path: /orders
        method: POST
        auth: jwt
        authorizer:
          issuer: https://auth.example.com/
          audience: [orders-api]
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def create(event, ctx):
    return {"ok": True}, 201
""",
          "requirements.txt": ""}),
      user="POST /orders already uses our JWT authorizer. Additionally require the scope `orders:write`, so read-only tokens get rejected by API Gateway.",
      steps=[
          S("get_project"),
          S("search_docs", query="jwt authorizer scopes identity_source",
            docs=[D("docs/events.md", "http", start="| `jwt` |", end="| `jwt` |")]),
          S("propose_plan", steps=["Add scopes: [orders:write] to functions.create-order.events.0.http.authorizer",
                                   "Validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.create-order.events.0.http.authorizer.scopes", value=["orders:write"]),
      ],
      final="""Added the scope:

```yaml
functions:
  create-order:
    events:
      - http:
          path: /orders
          method: POST
          auth: jwt
          authorizer:
            issuer: https://auth.example.com/
            audience: [orders-api]
            scopes: ["orders:write"]
```

- `scopes` is an optional authorizer field for `auth: jwt` on AWS [docs/events.md#http].
- `pskit validate` (aws, prod): valid.

Tokens without `orders:write` are rejected by API Gateway before Lambda runs. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 477
    B(477, provider="gcp", stage="staging", mode="ask", page="Code", persona="beginner",
      sources=["docs/configuration.md#package"],
      project=dict(files={
          "pskit.yml": """service: book-shelf
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, book-shelf-staging}
functions: {}
""",
          "requirements.txt": ""}),
      user="I have a list of my books and want a web address that shows them. No database please, a file in the project is fine.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `data/books.json` with your books (pskit bundles every project file by default)",
                                   "Write `app/books.py` that reads that file and returns it",
                                   "Add function `books` on GET /books; validate for gcp and test it"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="data/books.json",
            content='[\n  {"title": "Dune", "author": "Frank Herbert"},\n  {"title": "Emma", "author": "Jane Austen"}\n]\n'),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/books.py", content=FUTURE + """import json
from pathlib import Path

BOOKS_FILE = Path(__file__).resolve().parent.parent / "data" / "books.json"


def books(event, ctx):
    return {"books": json.loads(BOOKS_FILE.read_text(encoding="utf-8"))}
"""),
          S("set_config", path="functions.books", value={"handler": "app.books.books", "events": [{"http": "GET /books"}]}),
          S("invoke_local", function="books", method="GET", path="/books"),
      ],
      final="""Done. Your books live in `data/books.json`, and the function `books` shows them at `/books`.

- `package.include` defaults to every file (`**/*`), so `data/books.json` is shipped with the code [docs/configuration.md#package].
- `pskit validate` (gcp, staging): valid.
- Local test: 200 with Dune and Emma.

To add a book, edit `data/books.json` on the **Code** page and deploy again. Try it on **Test** > **▶ Run locally**. Put it online: **Deploy** page or `pskit deploy -s staging`; `pskit info` shows the address."""),

    # ------------------------------------------------------------------ 478
    B(478, provider="azure", stage="staging", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#provider-support"],
      project=dict(files={
          "pskit.yml": """service: notifier
provider:
  name: azure
  region: westeurope
functions:
  api:
    handler: app.notify.api
    events:
    - http: POST /alerts
""",
          "app/__init__.py": "",
          "app/notify.py": FUTURE + """from py_serverless_kit import resource


def api(event, ctx):
    return {"topic": resource("alerts").native_name}
""",
          "requirements.txt": ""}),
      user="managed service bus topic resource `alerts`, standalone. api already reads it",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.alerts: {type: topic}", "Validate azure (staging), invoke api"]),
          S("set_config", path="resources.alerts", value={"type": "topic"}),
          S("invoke_local", function="api", method="POST", path="/alerts", data={"msg": "disk full"}),
      ],
      final="""```yaml
resources:
  alerts:
    type: topic
```

- Azure creates standalone managed topics as a Service Bus topic [docs/resources.md#provider-support].
- validate (azure, staging): valid. invoke api: `{"topic": "alerts"}` locally (the real name after deploy may carry the provider prefix).

Publish with `azure-servicebus` (add to requirements.txt). Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 479
    B(479, provider="aws", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/configuration.md#functions", "docs/resources.md#aws-iam"],
      project=dict(files={
          "pskit.yml": """service: thumbs
provider:
  name: aws
  region: us-east-1
functions:
  save-thumb:
    handler: app.thumbs.save
    events:
    - http: POST /thumbs
""",
          "app/__init__.py": "",
          "app/thumbs.py": FUTURE + """

def save(event, ctx):
    return {"saved": True}
""",
          "requirements.txt": "boto3\n"}),
      user="""botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling the PutObject operation: User: arn:aws:sts::123456789012:assumed-role/thumbs-dev-save-thumb/thumbs-dev-save-thumb is not authorized to perform: s3:PutObject on resource: "arn:aws:s3:::acme-thumbnails-0007/small/x.png"
the bucket is ours but not made by pskit""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add functions.save-thumb.iam.statements: Allow s3:PutObject on arn:aws:s3:::acme-thumbnails-0007/*",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.save-thumb.iam",
            value={"statements": [{"actions": ["s3:PutObject"], "resources": ["arn:aws:s3:::acme-thumbnails-0007/*"]}]}),
      ],
      final="""The function's role had no permission on that bucket. I added exactly what the error asks for:

```yaml
functions:
  save-thumb:
    iam:
      statements:
        - actions: ["s3:PutObject"]
          resources: ["arn:aws:s3:::acme-thumbnails-0007/*"]
```

- `pskit validate` (aws): valid. Function-level `iam` gets a dedicated role [docs/configuration.md#functions].
- The new permission applies after you deploy: **Deploy** or `pskit deploy -s dev`.

Alternative: register the bucket as `resources: {thumbs: {type: storage, external: true, name: acme-thumbnails-0007, functions: [save-thumb]}}`. Then pskit grants Get/Put/Delete/List itself [docs/resources.md#aws-iam]."""),

    # ------------------------------------------------------------------ 480
    B(480, provider="gcp", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: crawler
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, crawler-dev}
functions:
  fetch-page:
    handler: app.crawl.fetch
    events:
    - queue: crawl-urls
""",
          "app/__init__.py": "",
          "app/crawl.py": FUTURE + """

def fetch(event, ctx):
    return {"fetched": len(event.records)}
""",
          "requirements.txt": ""}),
      user="fetch-page is hitting the site too hard. max 3 instance at same time pls",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.fetch-page.concurrency = 3 (max instances on GCP)", "Validate gcp"]),
          S("set_config", path="functions.fetch-page.concurrency", value=3),
      ],
      final="""```yaml
functions:
  fetch-page:
    concurrency: 3
```

validate (gcp): valid. `concurrency` is the reserved concurrency / max instances where the cloud supports it [docs/configuration.md#functions], so at most 3 copies of `fetch-page` run at once. Extra messages wait in the Pub/Sub queue and are retried. Deploy: **Deploy** or `pskit deploy -s dev`."""),
]
