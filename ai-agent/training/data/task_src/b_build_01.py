"""Category B (build / add), batch 1. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 1
    B(1, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: ingest-svc
provider:
  name: aws
  region: eu-west-1
functions:
  ingest:
    handler: app.ingest.handle
    timeout: 60
""",
          "app/__init__.py": "",
          "app/ingest.py": FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            item = record.json()
            ctx.logger.info("ingested", extra={"id": item.get("id")})
        except Exception:
            result.fail(record)
    return result
""",
          "requirements.txt": ""}),
      user="add sqs trigger to ingest, batch 10, dlq",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add a queue trigger to `ingest`: queue `ingest`, batch_size 10",
                                   "Dead-letter queue `ingest-dlq` after 5 receives",
                                   "Validate for aws and run `ingest` locally with two messages"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest.events",
            value=[{"queue": {"name": "ingest", "batch_size": 10, "dead_letter": "ingest-dlq", "max_receive": 5}}]),
          S("invoke_local", function="ingest", type="queue", data=[{"id": 1}, {"id": 2}]),
      ],
      final="""Added to `ingest`:

```yaml
events:
  - queue: {name: ingest, batch_size: 10, dead_letter: ingest-dlq, max_receive: 5}
```

- `pskit validate` for aws: valid.
- Local run with two messages: both ingested, `batchItemFailures` is empty. Your handler already returns a `BatchResult`, so only failed messages go back to SQS.

Test again with `pskit invoke -f ingest -t queue -d '[{"id": 1}]'` (or **Test** > **▶ Run locally**). Deploy from the **Deploy** page or with `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 2
    B(2, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: greeter
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions: {}
""",
          "requirements.txt": ""}),
      user="i want a web address that says hello and my name",
      steps=[
          S("get_project"),
          S("search_docs", query="http GET route query string handler",
            docs=[D("docs/handlers.md", "httprequest", end="| `path_params`")]),
          S("propose_plan", steps=["Create `app/hello.py` with a `hello` handler that reads `?name=`",
                                   "Add function `hello` with the route GET /hello",
                                   "Validate for gcp and call it locally with ?name=Sam"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/hello.py", content=FUTURE + """

def hello(event, ctx):
    name = event.http.query.get("name", "there")
    return {"message": f"Hello, {name}!"}
"""),
          S("set_config", path="functions.hello",
            value={"handler": "app.hello.hello", "events": [{"http": "GET /hello"}]}),
          S("invoke_local", function="hello", method="GET", path="/hello?name=Sam"),
      ],
      final="""Done. You now have a function `hello` on `GET /hello`.

- `pskit validate` for gcp: valid.
- Local test with `/hello?name=Sam` returned status 200 and `{"message": "Hello, Sam!"}`.

Try it yourself on **Test** > **▶ Run locally**, or run `pskit invoke -f hello --path "/hello?name=Sam"`. When you're ready, deploy on the **Deploy** page (or `pskit deploy -s dev`). After that, `pskit info` shows the real URL."""),

    # ------------------------------------------------------------------ 3
    B(3, provider="onprem", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: saver
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8090
functions: {}
""",
          "requirements.txt": ""}),
      user="i want queue worker save file in folder when message come, onprem",
      steps=[
          S("get_project"),
          S("search_docs", query="onprem handler write object put_object queue",
            docs=[D("docs/providers.md", "onprem-on-premises", start="From a handler in that process",
                    end="From a handler in that process")]),
          S("propose_plan", steps=["Write `app/saver.py`: for each message, save it as `<id>.json` in bucket `saved` with put_object",
                                   "Add function `saver` with a queue trigger on `inbox`",
                                   "Validate for onprem and run it locally with one message"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/saver.py", content=FUTURE + """import json

from py_serverless_kit import BatchResult


def save(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            body = json.dumps(record.json()).encode("utf-8")
            if ctx.env.get("PSKIT_ONPREM_ROOT"):
                from py_serverless_kit.runtime.onprem_host import put_object

                put_object("saved", f"{record.id}.json", body)
            else:
                ctx.logger.info("would save", extra={"key": f"{record.id}.json", "bytes": len(body)})
        except Exception:
            result.fail(record)
    return result
"""),
          S("set_config", path="functions.saver",
            value={"handler": "app.saver.save", "events": [{"queue": "inbox"}]}),
          S("invoke_local", function="saver", type="queue", data=[{"order": 7}]),
      ],
      final="""Done. Function `saver` reads queue `inbox` and saves each message as `<message id>.json` in the on-prem bucket `saved` (a folder on the host).

- `pskit validate` for onprem: valid.
- Local run: no error, `batchItemFailures` empty. Locally there is no on-prem host, so it only logged "would save". The real save happens after deploy, when `PSKIT_ONPREM_ROOT` is set.

Test again: **Test** > **▶ Run locally**, or `pskit invoke -f saver -t queue -d '[{"order": 7}]'`. Deploy: **Deploy** page, or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 4
    B(4, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: housekeeping
provider:
  name: aws
  region: eu-central-1
functions:
  cleanup:
    handler: app.jobs.cleanup
    timeout: 300
""",
          "app/__init__.py": "",
          "app/jobs.py": FUTURE + """

def cleanup(event, ctx):
    days = int((event.data or {}).get("days", 7))
    ctx.logger.info("cleanup", extra={"older_than_days": days})
    return {"deleted_older_than_days": days}
""",
          "requirements.txt": ""}),
      user="The `cleanup` function should run every night at 02:00 Berlin time and get the input {\"days\": 30}. Please wire up the schedule; don't change the code.",
      steps=[
          S("get_project"),
          S("search_docs", query="schedule cron timezone input",
            docs=[D("docs/events.md", "schedule", end="The handler gets `event.type")]),
          S("propose_plan", steps=["Add a schedule trigger to `cleanup`: cron `0 2 * * *`, timezone Europe/Berlin, input {\"days\": 30}",
                                   "Validate for aws (stage prod) and run the schedule event locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.cleanup.events",
            value=[{"schedule": {"cron": "0 2 * * *", "timezone": "Europe/Berlin", "input": {"days": 30}}}]),
          S("invoke_local", function="cleanup", type="schedule"),
      ],
      final="""Added to `cleanup` (code unchanged):

```yaml
events:
  - schedule:
      cron: "0 2 * * *"
      timezone: Europe/Berlin
      input: {days: 30}
```

- `pskit validate` (aws, prod): valid. On AWS this becomes an EventBridge Scheduler rule, which honours the timezone [docs/events.md#schedule].
- Local schedule run: the handler got `days` = 30 and returned `{"deleted_older_than_days": 30}`.

Run it again with `pskit invoke -f cleanup -t schedule`, or **Test** > **▶ Run locally**. To deploy prod, use the **Deploy** page (it asks you to type a confirmation for `prod`) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 5
    B(5, provider="azure", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#storage", "docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition"],
      project=dict(files={
          "pskit.yml": """service: csv-import
provider:
  name: azure
  region: westeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions: {}
""",
          "requirements.txt": ""}),
      user="On Lambda I had an S3 trigger: bucket uploads, s3:ObjectCreated, prefix incoming/, suffix .csv. Recreate that here for Azure please.",
      steps=[
          S("get_project"),
          S("search_docs", query="storage trigger prefix suffix azure blob",
            docs=[D("docs/events.md", "storage", end="Each record has")]),
          S("propose_plan", steps=["Write `app/importer.py` that logs each new CSV (bucket, key, size)",
                                   "Add function `import-csv` with a storage trigger: container `uploads`, created, prefix incoming/, suffix .csv",
                                   "Validate for azure and run a storage event locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/importer.py", content=FUTURE + """

def import_csv(event, ctx):
    files = []
    for record in event.records:
        ctx.logger.info("new csv", extra={"bucket": record.bucket, "key": record.key, "size": record.size})
        files.append(record.key)
    return {"imported": files}
"""),
          S("set_config", path="functions.import-csv",
            value={"handler": "app.importer.import_csv",
                   "events": [{"storage": {"bucket": "uploads", "events": ["created"], "prefix": "incoming/",
                                           "suffix": ".csv"}}]}),
          S("invoke_local", function="import-csv", type="storage",
            data={"bucket": "uploads", "key": "incoming/2026-11.csv", "size": 2048}),
      ],
      final="""Added `import-csv`, the Azure version of your S3 trigger:

```yaml
functions:
  import-csv:
    handler: app.importer.import_csv
    events:
      - storage: {bucket: uploads, events: [created], prefix: incoming/, suffix: .csv}
```

On Azure this is a Blob container `uploads` with a blob trigger in the app's storage account. It fires on created and updated blobs only [docs/events.md#storage].

- `pskit validate` for azure: valid.
- Local storage event for `incoming/2026-11.csv`: returned `{"imported": ["incoming/2026-11.csv"]}`.

The records have the same fields as on AWS (`record.bucket`, `record.key`, `record.size`), so the handler is not Azure-specific. Test with `pskit invoke -f import-csv -t storage -d '{"bucket": "uploads", "key": "incoming/a.csv"}'`. Deploy with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 6
    B(6, provider="gcp", stage="staging", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#retry-and-catch", "docs/workflows.md#compiler-notes-and-limits"],
      project=dict(files={
          "pskit.yml": """service: orders
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  validate:
    handler: app.orders.validate
  charge:
    handler: app.orders.charge
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def validate(event, ctx):
    order = dict(event.data or {})
    if order.get("amount", 0) <= 0:
        raise ValueError("amount must be positive")
    return {**order, "valid": True}


def charge(event, ctx):
    order = dict(event.data or {})
    return {**order, "charged": True}
""",
          "requirements.txt": ""}),
      user="workflow order-flow: validate -> charge. retry charge on TimeoutError x3",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow retry TimeoutError max_attempts",
            docs=[D("docs/workflows.md", "retry-and-catch", end="max_delay_seconds")]),
          S("propose_plan", steps=["Add workflow `order-flow`: Validate (task validate) -> Charge (task charge, end)",
                                   "Retry on Charge: errors [TimeoutError], max_attempts 3",
                                   "Validate for gcp and run the validate task locally"]),
          S("set_config", path="workflows.order-flow",
            value={"start_at": "Validate",
                   "states": {"Validate": {"type": "task", "function": "validate", "next": "Charge"},
                              "Charge": {"type": "task", "function": "charge", "end": True,
                                         "retry": [{"errors": ["TimeoutError"], "max_attempts": 3}]}}}),
          S("invoke_local", function="validate", type="workflow", data={"order_id": 5, "amount": 40}),
      ],
      final="""Added `order-flow`:

```yaml
workflows:
  order-flow:
    start_at: Validate
    states:
      Validate: {type: task, function: validate, next: Charge}
      Charge:
        type: task
        function: charge
        end: true
        retry: [{errors: [TimeoutError], max_attempts: 3}]
```

- `pskit validate` (gcp, staging): valid. On GCP it deploys as Cloud Workflows. Only the first retry rule of a task is used there [docs/workflows.md#compiler-notes-and-limits].
- `validate` run locally as a workflow task: returned the order with `"valid": true`.

Run the whole flow locally with `pskit workflow run order-flow -i '{"order_id": 5, "amount": 40}' --history`. Deploy with **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 7
    B(7, provider="tencent", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: tencent
  region: ap-guangzhou
functions: {}
""",
          "requirements.txt": ""}),
      user="add api get item by id for tencent, if no item give 404",
      steps=[
          S("get_project"),
          S("search_docs", query="path parameter NotFound 404 handler",
            docs=[D("docs/handlers.md", "errors", end="| `NotFound` | 404 |")]),
          S("propose_plan", steps=["Write `app/items.py` with `get_item`: read `id` from the path, raise NotFound if unknown",
                                   "Add function `get-item` on GET /items/{id}",
                                   "Validate for tencent and call /items/1 locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/items.py", content=FUTURE + """from py_serverless_kit import NotFound

ITEMS = {"1": {"id": "1", "name": "lamp"}, "2": {"id": "2", "name": "desk"}}


def get_item(event, ctx):
    item_id = event.http.path_params["id"]
    item = ITEMS.get(item_id)
    if item is None:
        raise NotFound(f"item {item_id} not found")
    return item
"""),
          S("set_config", path="functions.get-item",
            value={"handler": "app.items.get_item", "events": [{"http": "GET /items/{id}"}]}),
          S("invoke_local", function="get-item", method="GET", path="/items/1"),
      ],
      final="""Added `get-item` on `GET /items/{id}`. An unknown id raises `NotFound`, which pskit turns into a 404 JSON error [docs/handlers.md#errors].

- `pskit validate` for tencent: valid.
- Local call `/items/1`: status 200 with `{"id": "1", "name": "lamp"}`.

Replace `ITEMS` with your real data store. Test a missing id with `pskit invoke -f get-item --path /items/99`, or on **Test**. Deploy with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 8
    B(8, provider="alibaba", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#storage", "docs/providers.md#alibaba-function-compute-30"],
      project=dict(files={
          "pskit.yml": """service: photos
provider:
  name: alibaba
  region: cn-shanghai
functions: {}
""",
          "requirements.txt": ""}),
      user="can you make something that runs when someone uploads a picture?",
      steps=[
          S("get_project"),
          S("ask_user", question="Which OSS bucket do the pictures go to, and should I only react to certain files (e.g. .jpg)?",
            answer="bucket is photo-inbox, only .jpg"),
          S("propose_plan", steps=["Write `app/pictures.py` that logs each new picture",
                                   "Add function `on-picture` with a storage trigger on bucket `photo-inbox`, suffix .jpg",
                                   "Validate for alibaba and run a fake upload locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/pictures.py", content=FUTURE + """

def on_picture(event, ctx):
    seen = []
    for record in event.records:
        ctx.logger.info("new picture", extra={"key": record.key, "size": record.size})
        seen.append(record.key)
    return {"pictures": seen}
"""),
          S("set_config", path="functions.on-picture",
            value={"handler": "app.pictures.on_picture",
                   "events": [{"storage": {"bucket": "photo-inbox", "suffix": ".jpg"}}]}),
          S("invoke_local", function="on-picture", type="storage", data={"bucket": "photo-inbox", "key": "cat.jpg"}),
      ],
      final="""Done. The new function `on-picture` runs when a `.jpg` file is uploaded to the OSS bucket `photo-inbox`.

- `pskit validate` for alibaba: valid.
- Fake upload of `cat.jpg` run locally: it returned `{"pictures": ["cat.jpg"]}`.

Right now it only logs the file name and size. Tell me what it should do with the picture (resize it, save details, ...) and I'll add that.

Test again: **Test** > pick `on-picture` > **▶ Run locally**, or `pskit invoke -f on-picture -t storage -d '{"bucket": "photo-inbox", "key": "cat.jpg"}'`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 9
    B(9, provider="huawei", stage="dev", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: order-audit
provider:
  name: huawei
  region: cn-north-4
functions: {}
""",
          "requirements.txt": ""}),
      user="messages on our SMN topic order-events look like this:\n{\"order_id\": 981, \"status\": \"paid\"}\nneed a subscriber that logs order_id and status",
      steps=[
          S("get_project"),
          S("search_docs", query="topic trigger subscriber",
            docs=[D("docs/events.md", "topic", end="| huawei | SMN topic | – |")]),
          S("propose_plan", steps=["Write `app/audit.py` that logs order_id and status for each message",
                                   "Add function `audit` with a topic trigger on `order-events`",
                                   "Validate for huawei and run your sample message locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/audit.py", content=FUTURE + """

def audit(event, ctx):
    for record in event.records:
        msg = record.json(default={})
        ctx.logger.info("order event", extra={"order_id": msg.get("order_id"), "status": msg.get("status")})
"""),
          S("set_config", path="functions.audit",
            value={"handler": "app.audit.audit", "events": [{"topic": "order-events"}]}),
          S("invoke_local", function="audit", type="topic", data=[{"order_id": 981, "status": "paid"}]),
      ],
      final="""Added `audit`, subscribed to the SMN topic `order-events`. It logs `order_id` and `status` from each message.

- `pskit validate` for huawei: valid. No API Gateway is needed, because there is no HTTP trigger.
- Local run with your sample message: logged "order event" without errors.

Repeat with `pskit invoke -f audit -t topic -d '[{"order_id": 981, "status": "paid"}]'`. Deploy from **Deploy** or with `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 10
    B(10, provider="ibm", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: ibm
  region: us-south
functions:
  list:
    handler: app.api.list_products
    events:
    - http: GET /products
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def list_products(event, ctx):
    return [{"id": 1, "name": "lamp"}]
""",
          "requirements.txt": ""}),
      user="GET https://<our-ibm-url>/status -> 404\nmonitoring wants this to exist. return service name and stage",
      steps=[
          S("get_project"),
          S("search_docs", query="context service stage handler",
            docs=[D("docs/handlers.md", "context", end="| `logger`")]),
          S("propose_plan", steps=["Add `status` to `app/api.py`: return ctx.service and ctx.stage",
                                   "Add function `status` on GET /status",
                                   "Validate for ibm (prod) and call /status locally"],
            result={"decision": "approved", "note": "also return the provider name"}),
          S("write_file", path="app/api.py", content=FUTURE + """

def list_products(event, ctx):
    return [{"id": 1, "name": "lamp"}]


def status(event, ctx):
    return {"service": ctx.service, "stage": ctx.stage, "provider": ctx.provider}
"""),
          S("set_config", path="functions.status",
            value={"handler": "app.api.status", "events": [{"http": "GET /status"}]}, say="Adding the provider too, as you asked."),
          S("invoke_local", function="status", method="GET", path="/status"),
      ],
      final="""`GET /status` now exists. As you asked in the plan note, it returns service, stage and provider.

- `pskit validate` (ibm, prod): valid.
- Local call: status 200. Locally the provider shows as `local`; after deploy it will be `ibm`.

The 404 stays until you deploy. Use **Deploy** (it asks for a typed confirmation on `prod`) or `pskit deploy -s prod`. Test locally with `pskit invoke -f status`."""),

    # ------------------------------------------------------------------ 11
    B(11, provider="digitalocean", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule", "docs/providers.md#digitalocean-functions"],
      project=dict(files={
          "pskit.yml": """service: tidy
provider:
  name: digitalocean
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE, fn-00000000-0000-0000-0000-000000000000}
functions:
  cleanup:
    handler: app.tidy.cleanup
""",
          "app/__init__.py": "",
          "app/tidy.py": FUTURE + """

def cleanup(event, ctx):
    ctx.logger.info("tidy run")
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="need cleanup run every 15 min on digitalocean pls",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `schedule: 15 minutes` to `cleanup`",
                                   "Validate for digitalocean and run the schedule event locally"]),
          S("set_config", path="functions.cleanup.events", value=[{"schedule": "15 minutes"}]),
          S("invoke_local", function="cleanup", type="schedule"),
      ],
      final="""Done: `cleanup` now has `- schedule: 15 minutes`. On DigitalOcean it becomes a scheduled trigger in `project.yml` [docs/events.md#schedule].

- `pskit validate` for digitalocean: valid, with one warning: `doctl` is not on PATH on this machine. Deploy needs it installed and logged in (`doctl auth init`).
- Local schedule run: returned `{"ok": true}`.

Test: `pskit invoke -f cleanup -t schedule`. Deploy: **Deploy** page or `pskit deploy -s dev` (after installing doctl)."""),

    # ------------------------------------------------------------------ 12
    B(12, provider="oracle", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#oracle-oci-functions", "docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: invoices
provider:
  name: oracle
  region: eu-frankfurt-1
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID, ocid1.compartment.oc1..aaaa}
    subnet_ids:
    - ${env:OCI_SUBNET_ID, ocid1.subnet.oc1..aaaa}
    image_repository: ${env:OCI_IMAGE_REPO, fra.ocir.io/mytenancy/invoices}
functions: {}
""",
          "requirements.txt": ""}),
      user="We need a function on OCI that runs for every new object in the Object Storage bucket `invoices` and only handles PDFs. Note that Oracle can't filter by suffix as far as I know, so do the filtering in code.",
      steps=[
          S("get_project"),
          S("search_docs", query="oracle object storage trigger filter suffix",
            docs=[D("docs/events.md", "storage", start="| oracle |", end="| oracle |")]),
          S("search_docs", query="oracle functions limits IAM policies events",
            docs=[D("docs/providers.md", "oracle-oci-functions", start="**Limits:**")]),
          S("propose_plan", steps=["Write `app/invoices.py`: skip keys that don't end with .pdf, log the rest",
                                   "Add function `on-invoice` with a storage trigger on bucket `invoices` (created)",
                                   "Validate for oracle and run a PDF and a non-PDF locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/invoices.py", content=FUTURE + """

def on_invoice(event, ctx):
    handled, skipped = [], []
    for record in event.records:
        if not record.key.lower().endswith(".pdf"):
            skipped.append(record.key)
            continue
        ctx.logger.info("invoice", extra={"key": record.key, "size": record.size})
        handled.append(record.key)
    return {"handled": handled, "skipped": skipped}
"""),
          S("set_config", path="functions.on-invoice",
            value={"handler": "app.invoices.on_invoice", "events": [{"storage": {"bucket": "invoices"}}]}),
          S("invoke_local", function="on-invoice", type="storage", data={"bucket": "invoices", "key": "2026/inv-17.pdf"}),
      ],
      final="""You're right: OCI Events rules can't filter by prefix or suffix, so `on-invoice` checks for `.pdf` in the handler [docs/events.md#storage].

- `pskit validate` (oracle, staging): valid.
- Before deploying: the bucket must have "Emit Object Events" enabled, and you must add IAM policies that let Events invoke functions [docs/providers.md#oracle-oci-functions].
- Local run with `2026/inv-17.pdf`: handled, nothing skipped.

Test a non-PDF with `pskit invoke -f on-invoice -t storage -d '{"bucket": "invoices", "key": "a.txt"}'`. Deploy with **Deploy** or `pskit deploy -s staging`. pskit builds and pushes the image to `image_repository`, so Docker must be logged in to OCIR."""),

    # ------------------------------------------------------------------ 13
    B(13, provider="cloudflare", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#variables", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: hooks
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, 0123456789abcdef0123456789abcdef}
functions: {}
""",
          "requirements.txt": ""}),
      user="i need a webhook url that only accepts calls with our secret token",
      steps=[
          S("get_project"),
          S("search_docs", query="secret environment variable env default",
            docs=[D("docs/configuration.md", "variables", end="| `${env:NAME, default}`")]),
          S("propose_plan", steps=["Write `app/webhook.py`: compare the `X-Webhook-Token` header with env WEBHOOK_TOKEN, else 401",
                                   "Add function `webhook` on POST /webhook with WEBHOOK_TOKEN: ${env:WEBHOOK_TOKEN, } (the value stays out of pskit.yml)",
                                   "Validate for cloudflare and call it locally without a token (should be 401)"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/webhook.py", content=FUTURE + """import hmac

from py_serverless_kit import Unauthorized


def receive(event, ctx):
    expected = ctx.env.get("WEBHOOK_TOKEN", "")
    given = event.http.headers.get("x-webhook-token", "")
    if not expected or not hmac.compare_digest(given, expected):
        raise Unauthorized("bad token")
    return {"received": True}
"""),
          S("set_config", path="functions.webhook",
            value={"handler": "app.webhook.receive", "environment": {"WEBHOOK_TOKEN": "${env:WEBHOOK_TOKEN, }"},
                   "events": [{"http": "POST /webhook"}]}),
          S("invoke_local", function="webhook", method="POST", path="/webhook", data={"event": "ping"}),
      ],
      final="""Done. `POST /webhook` accepts a call only when the `X-Webhook-Token` header matches `WEBHOOK_TOKEN`. Otherwise it answers 401.

- `pskit validate` for cloudflare: valid, with one warning: Python Workers only get the standard library and Pyodide's packages. That's fine here, because the handler only uses `hmac` from the stdlib.
- Local call without a token: 401 `bad token`, as expected.

The token itself is not in pskit.yml. Set `WEBHOOK_TOKEN` in your environment before deploying, or in `.env` for local tests (`.env` is git-ignored and never bundled). Test with `pskit invoke -f webhook -H "X-Webhook-Token: <your token>" -d '{"event": "ping"}'`. Deploy from **Deploy** or with `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 14
    B(14, provider="onprem", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#topic", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: orders
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8091
functions:
  audit:
    handler: app.audit.record
""",
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """

def record(event, ctx):
    for r in event.records:
        ctx.logger.info("audit", extra={"attributes": r.attributes, "body": r.text()[:200]})
    return {"count": len(event.records)}
""",
          "requirements.txt": ""}),
      user="sub audit to topic order-events, only type=created",
      steps=[
          S("get_project"),
          S("search_docs", query="topic filter onprem",
            docs=[D("docs/events.md", "topic", end="| onprem | file topic")]),
          S("propose_plan", steps=["Add topic trigger to `audit`: order-events, filter {type: [created]}",
                                   "Validate for onprem, invoke with one message"]),
          S("set_config", path="functions.audit.events",
            value=[{"topic": {"name": "order-events", "filter": {"type": ["created"]}}}]),
          S("invoke_local", function="audit", type="topic", data=[{"type": "created", "id": 3}]),
      ],
      final="""Added: `- topic: {name: order-events, filter: {type: [created]}}` on `audit`.

- validate (onprem): valid. On premises, `filter` is an exact match on message attributes, then on JSON body fields [docs/events.md#topic].
- invoke: `{"count": 1}`. A local invoke does not apply the filter. The host does that after deploy.

Retest: `pskit invoke -f audit -t topic -d '[{"type": "created"}]'`. Deploy: `pskit deploy -s dev` or **Deploy**."""),

    # ------------------------------------------------------------------ 15
    B(15, provider="aws", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#errors", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: shop-api
provider:
  name: aws
  region: us-east-1
functions:
  list-orders:
    handler: app.orders.list_orders
    events:
    - http: GET /orders
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def list_orders(event, ctx):
    return []
""",
          "requirements.txt": ""}),
      user="frontend says: POST /orders -> 405 Method Not Allowed\nwe need create order. amount must be > 0 else 422, success 201",
      steps=[
          S("get_project"),
          S("search_docs", query="UnprocessableEntity 422 return status 201",
            docs=[D("docs/handlers.md", "errors", start="```python", end="# -> 422")]),
          S("propose_plan", steps=["Add `create_order` to `app/orders.py`: 422 when amount <= 0, else 201",
                                   "Add function `create-order` on POST /orders",
                                   "Validate for aws and post a valid order locally"],
            result={"decision": "approved", "note": "use /v1/orders for the new route"}),
          S("write_file", path="app/orders.py", content=FUTURE + """import uuid

from py_serverless_kit import UnprocessableEntity


def list_orders(event, ctx):
    return []


def create_order(event, ctx):
    order = event.http.json()
    amount = order.get("amount", 0)
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise UnprocessableEntity("invalid order", details={"field": "amount"})
    return {"id": str(uuid.uuid4()), **order}, 201
"""),
          S("set_config", path="functions.create-order",
            value={"handler": "app.orders.create_order", "events": [{"http": "POST /v1/orders"}]},
            say="Using /v1/orders as you noted."),
          S("invoke_local", function="create-order", method="POST", path="/v1/orders", data={"amount": 25}),
      ],
      final="""Added `create-order` on **POST /v1/orders** (not /orders, per your note). The 405 came from `/orders` only having GET.

- `pskit validate` for aws: valid.
- Local POST with `{"amount": 25}`: status 201 with a new `id`. With `amount` <= 0 it raises `UnprocessableEntity`, which returns 422 `{"error": "invalid order", ...}` [docs/handlers.md#errors].

Tell the frontend to use `/v1/orders`. Test on **Test** > **▶ Run locally**, or with `pskit invoke -f create-order -d '{"amount": 0}'` for the 422 case. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 16
    B(16, provider="gcp", stage="prod", mode="auto", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#provider"],
      project=dict(files={
          "pskit.yml": """service: portal
provider:
  name: gcp
  region: europe-west3
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  api:
    handler: app.api.handler
    events:
    - http: GET /
  sync:
    handler: app.api.sync
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def handler(event, ctx):
    return {"base": ctx.env.get("API_BASE_URL")}


def sync(event, ctx):
    return {"base": ctx.env.get("API_BASE_URL")}
""",
          "requirements.txt": ""}),
      user="all functions need API_BASE_URL = https://api.example.com , put it one place",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Set provider.environment.API_BASE_URL to https://api.example.com (applies to every function)",
                                   "Validate for gcp prod and check it in `api` locally"]),
          S("set_config", path="provider.environment.API_BASE_URL", value="https://api.example.com"),
          S("invoke_local", function="api", method="GET", path="/"),
      ],
      final="""Set once under `provider.environment`, so both `api` and `sync` get it:

```yaml
provider:
  environment:
    API_BASE_URL: https://api.example.com
```

- validate (gcp, prod): valid.
- local call to `api`: body `{"base": "https://api.example.com"}`.

A function's own `environment` can still override it. In studio this is **Overview & provider** > *Environment variables*. Deploy prod from **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 17
    B(17, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: todo
provider:
  name: azure
  region: eastus
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions:
  add-todo:
    handler: app.todos.add
    events:
    - http: POST /todos
""",
          "app/__init__.py": "",
          "app/todos.py": FUTURE + """
TODOS = [{"id": 1, "title": "buy milk", "done": False}]


def add(event, ctx):
    item = event.http.json()
    item["id"] = len(TODOS) + 1
    TODOS.append(item)
    return item, 201
""",
          "requirements.txt": ""}),
      user="my todo app can add todos but i also want to see the list of them",
      steps=[
          S("get_project"),
          S("read_file", path="app/todos.py"),
          S("propose_plan", steps=["Add `list_todos` to `app/todos.py` (returns the list)",
                                   "Add function `list-todos` on GET /todos",
                                   "Validate for azure and call GET /todos locally"]),
          S("write_file", path="app/todos.py", content=FUTURE + """
TODOS = [{"id": 1, "title": "buy milk", "done": False}]


def add(event, ctx):
    item = event.http.json()
    item["id"] = len(TODOS) + 1
    TODOS.append(item)
    return item, 201


def list_todos(event, ctx):
    return TODOS
"""),
          S("set_config", path="functions.list-todos",
            value={"handler": "app.todos.list_todos", "events": [{"http": "GET /todos"}]}),
          S("invoke_local", function="list-todos", method="GET", path="/todos"),
      ],
      final="""Done. `GET /todos` now returns the list.

- `pskit validate` for azure: valid.
- Local call: status 200 with `[{"id": 1, "title": "buy milk", "done": false}]`.

One thing to know: `TODOS` lives in memory, so the list resets when the function restarts, and two instances won't share it. For real use you'll want a database. I can help set one up under **Resources**.

Try it on **Test** > **▶ Run locally**, or with `pskit invoke -f list-todos`. Deploy on **Deploy** or with `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 18
    B(18, provider="aws", stage="staging", mode="auto", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: billing
provider:
  name: aws
  region: us-west-2
functions:
  worker:
    handler: app.worker.run
    events:
    - queue: invoices
""",
          "app/__init__.py": "",
          "app/worker.py": FUTURE + """

def run(event, ctx):
    return None
""",
          "requirements.txt": ""}),
      user="In Lambda this worker had ReservedConcurrentExecutions: 5 and MemorySize: 512. Same here please.",
      steps=[
          S("get_project"),
          S("search_docs", query="function concurrency memory reserved",
            docs=[D("docs/configuration.md", "functions", start="| `handler`", end="| `concurrency`")]),
          S("propose_plan", steps=["Set functions.worker.concurrency = 5", "Set functions.worker.memory = 512",
                                   "Validate for aws (staging)"]),
          S("set_config", path="functions.worker.concurrency", value=5),
          S("set_config", path="functions.worker.memory", value=512),
      ],
      final="""Set on `worker`:

```yaml
functions:
  worker:
    concurrency: 5    # reserved concurrency on AWS
    memory: 512
```

`pskit validate` (aws, staging) is valid after both changes. `concurrency` is reserved concurrency / max instances where the provider supports it [docs/configuration.md#functions]. No code changed, so no local run was needed. Deploy with **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 19
    B(19, provider="onprem", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": """service: reports
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8092
functions:
  fetch:
    handler: app.report.fetch
  report:
    handler: app.report.build
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """

def fetch(event, ctx):
    return {"rows": [1, 2, 3]}


def build(event, ctx):
    rows = (event.data or {}).get("rows", [])
    return {"total": sum(rows)}
""",
          "requirements.txt": ""}),
      user="On our on-prem host we want a workflow `daily-report`: run `fetch`, wait 10 seconds so the upstream system settles, then run `report` with fetch's output.",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow wait state seconds",
            docs=[D("docs/workflows.md", "state-types", end="| `wait` |")]),
          S("propose_plan", steps=["Add workflow `daily-report`: Fetch (task fetch) -> Settle (wait 10 s) -> Report (task report, end)",
                                   "Validate for onprem (staging) and run `report` locally as a workflow task"]),
          S("set_config", path="workflows.daily-report",
            value={"start_at": "Fetch",
                   "states": {"Fetch": {"type": "task", "function": "fetch", "next": "Settle"},
                              "Settle": {"type": "wait", "seconds": 10, "next": "Report"},
                              "Report": {"type": "task", "function": "report", "end": True}}}),
          S("invoke_local", function="report", type="workflow", data={"rows": [1, 2, 3]}),
      ],
      final="""Added `daily-report`:

```yaml
workflows:
  daily-report:
    start_at: Fetch
    states:
      Fetch:  {type: task, function: fetch, next: Settle}
      Settle: {type: wait, seconds: 10, next: Report}
      Report: {type: task, function: report, end: true}
```

- `pskit validate` (onprem, staging): valid. It runs on the embedded engine inside the host, so the wait doesn't count against a function timeout [docs/workflows.md#embedded-orchestrator].
- `report` run locally with fetch's output `{"rows": [1, 2, 3]}`: returned `{"total": 6}`.

Run the whole flow locally with `pskit workflow run daily-report --sleep --history`. Wait states are skipped unless you pass `--sleep`. Deploy with **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 20
    B(20, provider="aws", stage="dev", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: notes-api
provider:
  name: aws
  region: ap-south-1
functions:
  notes:
    handler: app.notes.list_notes
    events:
    - http: GET /notes
""",
          "app/__init__.py": "",
          "app/notes.py": FUTURE + """

def list_notes(event, ctx):
    return []
""",
          "requirements.txt": ""}),
      user="add health check url give ok text",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/health.py` returning the text \"ok\"", "Add function `health` on GET /health",
                                   "Validate for aws and call /health locally"]),
          S("write_file", path="app/health.py", content=FUTURE + """

def health(event, ctx):
    return "ok"
"""),
          S("set_config", path="functions.health",
            value={"handler": "app.health.health", "events": [{"http": "GET /health"}]}),
          S("invoke_local", function="health", method="GET", path="/health"),
      ],
      final="""Added `GET /health`. It returns plain text `ok`, because a `str` return value becomes `text/plain` with status 200.

- validate (aws): valid
- local call: status 200, body `ok`

Test: `pskit invoke -f health`. Deploy: **Deploy** or `pskit deploy -s dev`."""),
]
