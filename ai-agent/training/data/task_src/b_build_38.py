"""Category B (build / add), batch 38 (aws / gcp / azure): pasted errors, informal requests, AWS migrators. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


LOGO = """<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <circle cx="32" cy="32" r="28" fill="#2b7a78"/>
  <text x="32" y="40" font-size="22" text-anchor="middle" fill="#ffffff">BB</text>
</svg>
"""

CONVERSATIONS = [
    # ------------------------------------------------------------------ 741
    B(741, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: report-intake
provider:
  name: aws
  region: eu-west-1
functions:
  ingest-pdf:
    handler: app.intake.ingest
    events:
    - storage:
        bucket: reports-in-5120
        existing: true
        prefix: incoming/
        suffix: .pdf
""",
          "app/__init__.py": "",
          "app/intake.py": FUTURE + """

def ingest(event, ctx):
    keys = [r.key for r in event.records]
    ctx.logger.info("ingest", extra={"keys": keys})
    return {"ingested": keys}
""",
          "requirements.txt": ""}),
      user="""$ aws s3 ls s3://reports-in-5120/incoming/
2026-10-31 09:12:44      48213 Q3-Report.PDF
2026-10-31 09:13:02      51022 q3-summary.pdf

only q3-summary.pdf shows up in Logs, the .PDF one never trigger. make it pick both""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["storage event: drop suffix .pdf (S3 matches it exactly, so .PDF is skipped), keep prefix incoming/",
                                   "app/intake.py: keep only keys whose lower-case name ends with .pdf",
                                   "Validate for aws, invoke with Q3-Report.PDF and a .txt"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest-pdf.events.0",
            value={"storage": {"bucket": "reports-in-5120", "existing": True, "prefix": "incoming/"}}),
          S("write_file", path="app/intake.py", content=FUTURE + """

def ingest(event, ctx):
    keys = [r.key for r in event.records if r.key.lower().endswith(".pdf")]
    ctx.logger.info("ingest", extra={"keys": keys})
    return {"ingested": keys}
"""),
          S("validate"),
          S("invoke_local", function="ingest-pdf", type="storage",
            data={"bucket": "reports-in-5120", "key": "incoming/Q3-Report.PDF", "size": 48213}),
      ],
      final="""Cause: the trigger had `suffix: .pdf`, and the S3 notification compares the end of the key exactly, so `Q3-Report.PDF` never matched.

Change:

```yaml
functions:
  ingest-pdf:
    handler: app.intake.ingest
    events:
      - storage: {bucket: reports-in-5120, existing: true, prefix: incoming/}
```

and `app/intake.py` keeps only keys ending in `.pdf` in any case (`key.lower().endswith(".pdf")`); other files under `incoming/` still start the function but are skipped [docs/events.md#storage].

- `pskit validate` (aws): valid.
- `incoming/Q3-Report.PDF` → `{"ingested": ["incoming/Q3-Report.PDF"]}`.

Deploy: **Deploy** or `pskit deploy -s dev`. Files already in the bucket don't fire again; re-upload Q3-Report.PDF to process it."""),

    # ------------------------------------------------------------------ 742
    B(742, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: hello-world
provider:
  name: aws
  region: eu-west-1
functions:
  hello:
    handler: app.hello.hello
    events:
    - http: GET /hello
""",
          "app/__init__.py": "",
          "app/hello.py": FUTURE + """

def hello(event, ctx):
    return {"message": "hello"}
""",
          "requirements.txt": ""}),
      user="add ?lang= to /hello. de fr es, default en. unknown lang also en",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/hello.py: GREETINGS map, lang from event.http.query, fallback en",
                                   "Validate for aws, invoke ?lang=de and ?lang=xx"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/hello.py", content=FUTURE + """
GREETINGS = {"en": "hello", "de": "hallo", "fr": "bonjour", "es": "hola"}


def hello(event, ctx):
    lang = event.http.query.get("lang", "en").lower()
    if lang not in GREETINGS:
        lang = "en"
    return {"message": GREETINGS[lang], "lang": lang}
"""),
          S("validate"),
          S("invoke_local", function="hello", method="GET", path="/hello?lang=de"),
          S("invoke_local", function="hello", method="GET", path="/hello?lang=xx"),
      ],
      final="""Done, `/hello` now speaks 4 languages.

- `lang` comes from `event.http.query` [docs/handlers.md#httprequest]; no `lang` or an unknown one → English.
- `pskit validate` (aws): valid.
- `?lang=de` → `{"message": "hallo", "lang": "de"}`; `?lang=xx` → `{"message": "hello", "lang": "en"}`.

No pskit.yml change was needed (query strings don't need a route change). Test again: `pskit invoke -f hello --method GET --path "/hello?lang=fr"`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 743
    B(743, provider="gcp", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: partner-feed
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, partner-feed-prod}
functions:
  load-export:
    handler: app.feed.load
    events:
    - storage:
        bucket: partner-feed-3371
        existing: true
""",
          "app/__init__.py": "",
          "app/feed.py": FUTURE + """

def load(event, ctx):
    for record in event.records:
        ctx.logger.info("processing " + record.key)
    return {"loaded": [r.key for r in event.records]}
""",
          "requirements.txt": ""}),
      user="""2026-10-31T08:00:01Z  load-export  processing tmp/upload-7f3a.part
2026-10-31T08:00:01Z  load-export  processing tmp/upload-7f3a.part
2026-10-31T08:00:03Z  load-export  processing exports/2026-10-31.csv
2026-10-31T08:00:04Z  load-export  processing thumbs/x.png

load-export runs for every file in the bucket. should be only exports/*.csv""",
      steps=[
          S("get_project"),
          S("search_docs", query="storage prefix suffix gcp", docs=[D("docs/events.md", "storage", start="Each record has", end="| gcp | Cloud Storage via Eventarc | applied by the runtime | `created` and `deleted` become separate deployments |")]),
          S("propose_plan", steps=["load-export storage event: add prefix exports/ and suffix .csv",
                                   "Validate for gcp (prod), invoke with exports/2026-10-31.csv"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.load-export.events.0",
            value={"storage": {"bucket": "partner-feed-3371", "existing": True, "prefix": "exports/", "suffix": ".csv"}}),
          S("invoke_local", function="load-export", type="storage",
            data={"bucket": "partner-feed-3371", "key": "exports/2026-10-31.csv", "size": 1200}),
      ],
      final="""Cause: the trigger had no `prefix`/`suffix`, so every object in `partner-feed-3371` was passed to the handler.

Change:

```yaml
functions:
  load-export:
    handler: app.feed.load
    events:
      - storage:
          bucket: partner-feed-3371
          existing: true
          prefix: exports/
          suffix: .csv
```

- On GCP the filters are applied by the pskit runtime [docs/events.md#storage]: Eventarc still starts the function for `tmp/` and `thumbs/` files, but your code only gets `exports/*.csv`.
- `pskit validate` (gcp, prod): valid; `exports/2026-10-31.csv` → `{"loaded": ["exports/2026-10-31.csv"]}`.

Deploy with **Deploy** (typed confirmation for prod) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 744
    B(744, provider="azure", stage="dev", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: bakery-site
provider:
  name: azure
  region: westeurope
functions:
  home:
    handler: app.site.home
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/site.py": FUTURE + """from py_serverless_kit import Response


def home(event, ctx):
    return Response.html("<h1>Bakery</h1><img src='/logo.svg'>")
""",
          "app/static/logo.svg": LOGO,
          "requirements.txt": ""}),
      user="my logo is in app/static/logo.svg. i want GET /logo.svg show it in browser as image, home page use it",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/site.py: logo() reads app/static/logo.svg next to the code, returns Response.binary(..., image/svg+xml)",
                                   "functions.logo on GET /logo.svg", "Validate azure, invoke GET /logo.svg"]),
          S("write_file", path="app/site.py", content=FUTURE + """from pathlib import Path

from py_serverless_kit import Response

LOGO = Path(__file__).parent / "static" / "logo.svg"


def home(event, ctx):
    return Response.html("<h1>Bakery</h1><img src='/logo.svg'>")


def logo(event, ctx):
    return Response.binary(LOGO.read_bytes(), "image/svg+xml")
"""),
          S("set_config", path="functions.logo", value={"handler": "app.site.logo", "events": [{"http": "GET /logo.svg"}]}),
          S("invoke_local", function="logo", method="GET", path="/logo.svg"),
      ],
      final="""Done: `GET /logo.svg` serves the file with `Content-Type: image/svg+xml`, so the browser shows it as an image and your home page's `<img src='/logo.svg'>` works.

```yaml
functions:
  logo:
    handler: app.site.logo
    events:
      - http: GET /logo.svg
```

- The file is read next to the code (`Path(__file__).parent / "static"`), and `app/static/` is packed with the bundle. `Response.binary` is base64-encoded for gateways automatically [docs/handlers.md#returning-a-response].
- `pskit validate` (azure): valid; local GET /logo.svg → 200 `image/svg+xml`.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 745
    B(745, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: visit-tracker
provider:
  name: aws
  region: eu-west-1
functions:
  track:
    handler: app.track.handler
    events:
    - http: POST /track
""",
          "app/__init__.py": "",
          "app/track.py": FUTURE + """

def handler(event, context):
    ip = event["requestContext"]["http"]["sourceIp"]
    agent = event["headers"].get("user-agent", "")
    print(f"visit {ip} {agent}")
    return {"statusCode": 204}
""",
          "requirements.txt": ""}),
      user="app/track.py is our old Lambda proxy code, it reads requestContext.http.sourceIp and headers user-agent. port it to pskit so it isn't tied to API Gateway's event",
      steps=[
          S("get_project"),
          S("read_file", path="app/track.py"),
          S("propose_plan", steps=["event.http.source_ip / event.http.headers.get(\"user-agent\") instead of the API Gateway dict",
                                   "ctx.logger instead of print; return None (204)",
                                   "Validate for aws, invoke POST /track"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/track.py", content=FUTURE + """

def handler(event, ctx):
    ctx.logger.info("visit", extra={
        "source_ip": event.http.source_ip,
        "user_agent": event.http.headers.get("user-agent", ""),
    })
    return None
"""),
          S("validate"),
          S("invoke_local", function="track", method="POST", path="/track", data={"page": "/pricing"}),
      ],
      final="""Ported. `app/track.py` reads only the portable request:

| Lambda proxy v2 | pskit |
|---|---|
| `event["requestContext"]["http"]["sourceIp"]` | `event.http.source_ip` |
| `event["headers"].get("user-agent")` | `event.http.headers.get("user-agent")` (case-insensitive) |
| `{"statusCode": 204}` | `return None` → 204 |

[docs/handlers.md#httprequest] [docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing]

- `pskit validate` (aws): valid; local POST /track → 204 and a `visit` log line.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 746
    B(746, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": """service: onboarding
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, onboarding-dev}
functions:
  verify-id:
    handler: app.kyc.verify
  approve:
    handler: app.kyc.approve
  manual-review:
    handler: app.kyc.review
  reject:
    handler: app.kyc.reject
""",
          "app/__init__.py": "",
          "app/kyc.py": FUTURE + """

def verify(event, ctx):
    return {**(event.data or {}), "score": 72}


def approve(event, ctx):
    return {**(event.data or {}), "result": "approved"}


def review(event, ctx):
    return {**(event.data or {}), "result": "review"}


def reject(event, ctx):
    return {**(event.data or {}), "result": "rejected"}
""",
          "requirements.txt": ""}),
      user="wf `kyc`: verify-id first. then if $.score >= 80 approve, 50 to 79 manual-review, under 50 reject",
      steps=[
          S("get_project"),
          S("search_docs", query="choice gte numeric rules order", docs=[D("docs/workflows.md", "choice-rules", start="| Operator |", end="A rule whose variable is missing or of the wrong type evaluates to false instead of failing.")]),
          S("propose_plan", steps=["workflows.kyc: Verify (verify-id) -> Decide (choice)",
                                   "Decide: score gte 80 -> Approve, score gte 50 -> Review, default Reject",
                                   "Validate for gcp, invoke verify-id"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.kyc",
            value={"start_at": "Verify",
                   "states": {"Verify": {"type": "task", "function": "verify-id", "next": "Decide"},
                              "Decide": {"type": "choice",
                                         "choices": [{"variable": "$.score", "gte": 80, "next": "Approve"},
                                                     {"variable": "$.score", "gte": 50, "next": "Review"}],
                                         "default": "Reject"},
                              "Approve": {"type": "task", "function": "approve", "end": True},
                              "Review": {"type": "task", "function": "manual-review", "end": True},
                              "Reject": {"type": "task", "function": "reject", "end": True}}}),
          S("invoke_local", function="verify-id", type="workflow", data={"customer": "c-19"}),
      ],
      final="""```yaml
workflows:
  kyc:
    start_at: Verify
    states:
      Verify: {type: task, function: verify-id, next: Decide}
      Decide:
        type: choice
        choices:
          - {variable: $.score, gte: 80, next: Approve}
          - {variable: $.score, gte: 50, next: Review}
        default: Reject
      Approve: {type: task, function: approve, end: true}
      Review: {type: task, function: manual-review, end: true}
      Reject: {type: task, function: reject, end: true}
```

- Rules are checked in order, so the second one only sees scores under 80 (50–79). Under 50, or no score at all, goes to `default` [docs/workflows.md#choice-rules].
- `pskit validate` (gcp): valid (Cloud Workflows). verify-id → `score: 72`, which would go to Review.

Run it end to end: `pskit workflow run kyc -i '{"customer": "c-19"}' --history`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 747
    B(747, provider="azure", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: reports
provider:
  name: azure
  region: germanywestcentral
functions:
  weekly-report:
    handler: app.reports.weekly
    events:
    - schedule:
        cron: "0 7 * * 1"
        timezone: Europe/Berlin
""",
          "app/__init__.py": "",
          "app/reports.py": FUTURE + """

def weekly(event, ctx):
    return {"sent": True}
""",
          "requirements.txt": ""}),
      user="""2026-10-26T07:00:00.012Z [Information] Executing 'Functions.weekly_report' (Reason='Timer fired at 2026-10-26T07:00:00.0029911+00:00', Id=3f1c2a77-5d0e-4b8a-9e61-2a7c4d9b0e15)

thats 08:00 in Berlin now (winter time). i set timezone Europe/Berlin, want 07:00 Berlin""",
      steps=[
          S("get_project"),
          S("get_validation"),
          S("propose_plan", steps=["Azure timers run in UTC and ignore timezone: drop it",
                                   "cron \"0 6 * * 1\" = 07:00 Berlin in winter (CET, UTC+1)",
                                   "Validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.weekly-report.events.0", value={"schedule": "0 6 * * 1"}),
      ],
      final="""Cause: on Azure (Linux Consumption) timers always run in UTC and `timezone` is ignored; validate already warned about it [docs/events.md#schedule]. So `0 7 * * 1` fired at 07:00 UTC = 08:00 Berlin.

Change:

```yaml
functions:
  weekly-report:
    handler: app.reports.weekly
    events:
      - schedule: "0 6 * * 1"
```

- 06:00 UTC = 07:00 Berlin while winter time lasts (CET).
- `pskit validate` (azure, prod): valid, no warning.
- After the switch to summer time (end of March) it'll be 08:00 Berlin again; change it to `0 5 * * 1` then (or ask me).

Deploy with **Deploy** (typed confirmation for prod) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 748
    B(748, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage", "docs/resources.md#aws-iam"],
      project=dict(files={
          "pskit.yml": """service: sales
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="fn `sales-import` when csv come in existing bucket `sales-drop-7781` (dont create it). and also make sns topic `sales-ready` (pskit make it) that only this fn can publish",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/sales.py: per .csv record log the key; return the topic it will publish to",
                                   "functions.sales-import: storage {bucket: sales-drop-7781, existing: true, suffix: .csv}",
                                   "resources.sales-ready: {type: topic, functions: [sales-import]}",
                                   "Validate for aws, invoke with a csv"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/sales.py", content=FUTURE + """from py_serverless_kit import resource


def sales_import(event, ctx):
    topic = resource("sales-ready")
    keys = [r.key for r in event.records]
    ctx.logger.info("sales files", extra={"keys": keys, "topic": topic.native_name})
    # next step: boto3.client("sns").publish(TopicArn=topic.arn, Message=...)
    return {"files": keys, "topic": topic.native_name}
"""),
          S("set_config", path="functions.sales-import",
            value={"handler": "app.sales.sales_import",
                   "events": [{"storage": {"bucket": "sales-drop-7781", "existing": True, "suffix": ".csv"}}]}),
          S("set_config", path="resources", value={"sales-ready": {"type": "topic", "functions": ["sales-import"]}}),
          S("invoke_local", function="sales-import", type="storage",
            data={"bucket": "sales-drop-7781", "key": "2026-10-31.csv", "size": 900}),
      ],
      final="""Both parts are in:

```yaml
resources:
  sales-ready:
    type: topic
    functions: [sales-import]
functions:
  sales-import:
    handler: app.sales.sales_import
    events:
      - storage: {bucket: sales-drop-7781, existing: true, suffix: .csv}
```

- `existing: true`: pskit only adds the notification, the bucket stays as it is [docs/events.md#storage].
- pskit creates the SNS topic; only `sales-import`'s role gets `sns:Publish` on it [docs/resources.md#aws-iam]. In code, `resource("sales-ready").arn` is the topic ARN once deployed (locally only the name is known).
- `pskit validate` (aws): valid; a new `2026-10-31.csv` → `{"files": ["2026-10-31.csv"], "topic": "sales-ready"}`.

Publishing is a TODO in the code (add `boto3` to requirements.txt when you write it). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 749
    B(749, provider="gcp", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition", "docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: thumbs
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, thumbs-dev}
functions: {}
""",
          "app/__init__.py": "",
          "app/thumb.py": FUTURE + """

def handler(event, ctx):
    size = int(ctx.env.get("THUMB_SIZE", "128"))
    return {"thumbs": [r.key for r in event.records], "size": size}
""",
          "requirements.txt": ""}),
      user="""our CDK stack had this:

const thumb = new lambda.Function(this, 'Thumb', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'app.thumb.handler',
  memorySize: 1024,
  timeout: Duration.minutes(2),
  environment: { THUMB_SIZE: '256' },
});
const bucket = new s3.Bucket(this, 'In', { bucketName: 'thumbs-in-5531' });
bucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(thumb));

now on GCP, pskit should create the bucket too""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.thumb: handler app.thumb.handler, runtime python3.12, memory 1024, timeout 120",
                                   "environment THUMB_SIZE \"256\"; storage event on thumbs-in-5531 (created, pskit creates the bucket)",
                                   "Validate for gcp, invoke a created object"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.thumb",
            value={"handler": "app.thumb.handler", "runtime": "python3.12", "memory": 1024, "timeout": 120,
                   "environment": {"THUMB_SIZE": "256"}, "events": [{"storage": "thumbs-in-5531"}]}),
          S("invoke_local", function="thumb", type="storage", data={"bucket": "thumbs-in-5531", "key": "cat.jpg", "size": 34000}),
      ],
      final="""```yaml
functions:
  thumb:
    handler: app.thumb.handler
    runtime: python3.12
    memory: 1024
    timeout: 120
    environment:
      THUMB_SIZE: "256"
    events:
      - storage: thumbs-in-5531
```

- `memorySize`, `Duration.minutes(2)`, `environment` → `memory`, `timeout: 120`, `environment` [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition].
- `bucket` + `OBJECT_CREATED` → `- storage: thumbs-in-5531`: pskit creates the Cloud Storage bucket and the default event is `created` [docs/events.md#storage]. Bucket names are global on GCP, so the S3 name must not be taken there.
- `pskit validate` (gcp): valid; a created `cat.jpg` → `{"thumbs": ["cat.jpg"], "size": 256}`.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 750
    B(750, provider="azure", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule", "docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: uptime
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="fn ping-sites every 10 min. list of urls in env SITES, comma sep. for now only log each url, no real request yet",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/ping.py: split ctx.env SITES on commas, log each url",
                                   "functions.ping-sites: schedule 10 minutes, environment SITES (two example.com urls)",
                                   "Validate azure, run the schedule"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/ping.py", content=FUTURE + """

def ping(event, ctx):
    sites = [s.strip() for s in ctx.env.get("SITES", "").split(",") if s.strip()]
    for url in sites:
        ctx.logger.info("would ping", extra={"url": url})
    return {"sites": len(sites)}
"""),
          S("set_config", path="functions.ping-sites",
            value={"handler": "app.ping.ping", "events": [{"schedule": "10 minutes"}],
                   "environment": {"SITES": "https://www.example.com,https://shop.example.com"}}),
          S("invoke_local", function="ping-sites", type="schedule"),
      ],
      final="""Done:

```yaml
functions:
  ping-sites:
    handler: app.ping.ping
    environment:
      SITES: "https://www.example.com,https://shop.example.com"
    events:
      - schedule: 10 minutes
```

- Every 10 minutes (Azure timer `0 */10 * * * *`, UTC) [docs/events.md#schedule]; the code reads `ctx.env["SITES"]` and logs each URL [docs/handlers.md#environment-variables].
- `pskit validate` (azure): valid. Test run → 2 `would ping` lines, `{"sites": 2}`.

Put your real URLs in `SITES`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 751
    B(751, provider="aws", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: invoices
provider:
  name: aws
  region: eu-west-1
functions:
  render:
    handler: app.render.render
    events:
    - queue: render-jobs
""",
          "app/__init__.py": "",
          "app/render.py": FUTURE + """

def render(event, ctx):
    return {"rendered": len(event.records)}
""",
          "requirements.txt": ""}),
      user="""[ERROR] ClientError: An error occurred (AccessDenied) when calling the GetObject operation: User: arn:aws:sts::123456789012:assumed-role/invoices-dev-render/invoices-dev-render is not authorized to perform: s3:GetObject on resource: "arn:aws:s3:::report-templates-2207/invoice.html"

that bucket is from the design team, render only reads templates from it""",
      steps=[
          S("get_project"),
          S("search_docs", query="aws iam statements function permissions", docs=[D("docs/configuration.md", "functions", start="| `runtime`, `memory`, `timeout`, `architecture` |", end="a dedicated role is created (AWS) |")]),
          S("propose_plan", steps=["functions.render.iam.statements: s3:GetObject on arn:aws:s3:::report-templates-2207/* (read only, render only)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.render.iam",
            value={"statements": [{"actions": ["s3:GetObject"], "resources": ["arn:aws:s3:::report-templates-2207/*"]}]}),
      ],
      final="""Cause: `render`'s role only has what pskit grants for its own trigger (the queue); nothing allows reading the design team's bucket.

Change, on `render` only:

```yaml
functions:
  render:
    iam:
      statements:
        - actions: ["s3:GetObject"]
          resources: ["arn:aws:s3:::report-templates-2207/*"]
```

- Read-only, objects only, this one function [docs/configuration.md#functions]. (A `resources:` entry with `external: true` would also work, but it grants Put/Delete too.)
- `pskit validate` (aws): valid.

Deploy with **Deploy** or `pskit deploy -s dev`. If the bucket is in another account or uses KMS encryption, the design team must also allow your role in their bucket/key policy."""),

    # ------------------------------------------------------------------ 752
    B(752, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: date-tools
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, date-tools-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="GET /age?born=1990-05-01 give me the age in years. wrong date or future date = 400",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/age.py: date.fromisoformat(born), compare with today (UTC); BadRequest for bad or future dates",
                                   "functions.age on GET /age", "Validate gcp, invoke a good date and a bad one"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/age.py", content=FUTURE + """from datetime import date

from py_serverless_kit import BadRequest


def age(event, ctx):
    try:
        born = date.fromisoformat(event.http.query.get("born", ""))
    except ValueError:
        raise BadRequest("born must be a date like 1990-05-01")
    today = event.time.date()
    if born > today:
        raise BadRequest("born is in the future")
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return {"born": born.isoformat(), "age": years}
"""),
          S("set_config", path="functions.age", value={"handler": "app.age.age", "events": [{"http": "GET /age"}]}),
          S("invoke_local", function="age", method="GET", path="/age?born=1990-05-01"),
          S("invoke_local", function="age", method="GET", path="/age?born=1990-13-01"),
      ],
      final="""Done: `GET /age?born=YYYY-MM-DD`.

- `born` from `event.http.query` [docs/handlers.md#httprequest]; today is the UTC date of the request. One year is subtracted when the birthday hasn't come yet this year.
- Not a real date or in the future → `BadRequest` (400) [docs/handlers.md#errors].
- `pskit validate` (gcp): valid. `born=1990-05-01` → `{"born": "1990-05-01", "age": 36}`; `born=1990-13-01` → 400.

Test again: `pskit invoke -f age --method GET --path "/age?born=2000-02-29"`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 753
    B(753, provider="azure", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: shop-auth
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "app/__init__.py": "",
          "app/login.py": FUTURE + """

def handler(event, context):
    return {"statusCode": 302, "headers": {"Location": "https://login.example.com/authorize?client=shop"}}
""",
          "requirements.txt": ""}),
      user="app/login.py is Lambda proxy code that sends people to our login page with a 302. on Azure with pskit it should do the same on GET /login",
      steps=[
          S("get_project"),
          S("read_file", path="app/login.py"),
          S("propose_plan", steps=["app/login.py: return Response.redirect(<login url>, status=302) instead of the statusCode dict",
                                   "functions.login on GET /login", "Validate for azure, invoke GET /login"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/login.py", content=FUTURE + """from py_serverless_kit import Response

LOGIN_URL = "https://login.example.com/authorize?client=shop"


def handler(event, ctx):
    return Response.redirect(LOGIN_URL, status=302)
"""),
          S("set_config", path="functions.login", value={"handler": "app.login.handler", "events": [{"http": "GET /login"}]}),
          S("invoke_local", function="login", method="GET", path="/login"),
      ],
      final="""Ported. A `{"statusCode": 302, ...}` dict would be sent as a JSON body by pskit; `Response.redirect(url, status=302)` sets the status and the `Location` header on every cloud [docs/handlers.md#returning-a-response].

```yaml
functions:
  login:
    handler: app.login.handler
    events:
      - http: GET /login
```

- `pskit validate` (azure): valid; local GET /login → 302 with `location: https://login.example.com/authorize?client=shop`.

Deploy: **Deploy** or `pskit deploy -s dev`. On Azure the path stays `/login` (no `/api` prefix)."""),

    # ------------------------------------------------------------------ 754
    B(754, provider="aws", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: gallery
provider:
  name: aws
  region: eu-west-1
functions:
  api:
    handler: app.gallery.api
    events:
    - http: GET /photos
  thumbs:
    handler: app.gallery.thumbs
    events:
    - queue: thumb-jobs
""",
          "app/__init__.py": "",
          "app/gallery.py": FUTURE + """

def api(event, ctx):
    return {"photos": []}


def thumbs(event, ctx):
    width = int(ctx.env.get("THUMB_WIDTH", "100"))
    return {"done": len(event.records), "width": width}
""",
          "requirements.txt": ""}),
      user="thumbs worker: timeout 60, memory 1024, and env THUMB_WIDTH 200 only for this fn. api dont touch",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.thumbs: timeout 60, memory 1024, environment THUMB_WIDTH \"200\"",
                                   "Validate aws, invoke thumbs"]),
          S("set_config", path="functions.thumbs.timeout", value=60),
          S("set_config", path="functions.thumbs.memory", value=1024),
          S("set_config", path="functions.thumbs.environment", value={"THUMB_WIDTH": "200"}),
          S("invoke_local", function="thumbs", type="queue", data={"photo": "p-1.jpg"}),
      ],
      final="""```yaml
functions:
  thumbs:
    handler: app.gallery.thumbs
    timeout: 60
    memory: 1024
    environment:
      THUMB_WIDTH: "200"
    events:
      - queue: thumb-jobs
```

- All three are function-level keys, so `api` keeps the defaults [docs/configuration.md#functions].
- `pskit validate` (aws): valid. One message → `{"done": 1, "width": 200}`, so the code sees the new variable.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 755
    B(755, provider="gcp", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, catalog-staging}
functions:
  products:
    handler: app.products.list_products
    events:
    - http: GET /products
""",
          "app/__init__.py": "",
          "app/products.py": FUTURE + """
PRODUCTS = [{"id": i, "name": f"product {i}"} for i in range(1, 251)]


def list_products(event, ctx):
    limit = int(event.http.query.get("limit", "20"))
    return {"products": PRODUCTS[:limit], "limit": limit}
""",
          "requirements.txt": ""}),
      user="""ValueError: invalid literal for int() with base 10: 'ten'
  File "/workspace/app/products.py", line 7, in list_products
    limit = int(event.http.query.get("limit", "20"))

client got 500 for GET /products?limit=ten. give 400, and limit max 100""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/products.py: not a number or < 1 -> BadRequest (400); above 100 -> use 100",
                                   "Validate for gcp (staging), invoke ?limit=ten and ?limit=500"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/products.py", content=FUTURE + """from py_serverless_kit import BadRequest

PRODUCTS = [{"id": i, "name": f"product {i}"} for i in range(1, 251)]
MAX_LIMIT = 100


def list_products(event, ctx):
    raw = event.http.query.get("limit", "20")
    if not raw.isdigit() or int(raw) < 1:
        raise BadRequest("limit must be a whole number from 1 to 100")
    limit = min(int(raw), MAX_LIMIT)
    return {"products": PRODUCTS[:limit], "limit": limit}
"""),
          S("validate"),
          S("invoke_local", function="products", method="GET", path="/products?limit=ten"),
          S("invoke_local", function="products", method="GET", path="/products?limit=500"),
      ],
      final="""Cause: `int("ten")` raised `ValueError`, and any exception that isn't an `HttpError` becomes a 500 [docs/handlers.md#errors].

Change in `app/products.py`:
- not a whole number, or below 1 → `BadRequest` → 400 `limit must be a whole number from 1 to 100`;
- above 100 → capped at 100 (the response's `limit` shows what was used).

Checks: `pskit validate` (gcp, staging) valid; `?limit=ten` → 400; `?limit=500` → 200 with 100 products and `"limit": 100`.

If you'd rather reject 500 with a 400 too, say so. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 756
    B(756, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: video-tools
provider:
  name: azure
  region: westeurope
functions:
  resize:
    handler: app.video.resize
    timeout: 300
    events:
    - queue: resize-jobs
""",
          "app/__init__.py": "",
          "app/video.py": FUTURE + """

def resize(event, ctx):
    return {"resized": len(event.records)}
""",
          "requirements.txt": ""}),
      user="resize need 15 minutes sometime, now it stop at 5. set timeout 15 min",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.resize.timeout: 900", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.resize.timeout", value=900),
          S("ask_user", question="Azure Functions (Consumption) allows at most 600 s (10 min), so 900 is rejected. What should I do?",
            options=["Set 600, the maximum", "Keep 300, I will split the work into smaller jobs"],
            answer="600 then"),
          S("set_config", path="functions.resize.timeout", value=600),
      ],
      final="""`resize` now has `timeout: 600`, the most Azure allows here. 15 minutes isn't possible: validate rejected 900 with `timeout 900s exceeds Azure Functions max 600s`.

```yaml
functions:
  resize:
    handler: app.video.resize
    timeout: 600
    events:
      - queue: resize-jobs
```

- `timeout` is per function, in seconds [docs/configuration.md#functions]; pskit writes it to the Function App's `host.json`.
- `pskit validate` (azure): valid.

Jobs over 10 minutes will still be stopped. Split them into smaller queue messages (e.g. one per part). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 757
    B(757, provider="azure", stage="staging", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/configuration.md#provider"],
      project=dict(files={
          "pskit.yml": """service: booking
provider:
  name: azure
  region: westeurope
functions:
  api:
    handler: app.booking.api
    events:
    - http: GET /slots
  reminder:
    handler: app.booking.reminder
    events:
    - schedule: "0 8 * * *"
""",
          "app/__init__.py": "",
          "app/booking.py": FUTURE + """

def api(event, ctx):
    return {"slots": []}


def reminder(event, ctx):
    return {"sent": 0}
""",
          "requirements.txt": ""}),
      user="in staging all functions 512mb please. dev keep default",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["stages.staging.provider.memory: 512 (applies to every function in staging)",
                                   "Validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages", value={"staging": {"provider": {"memory": 512}}}),
      ],
      final="""```yaml
stages:
  staging:
    provider:
      memory: 512
```

- `provider.memory` is the default for every function (256 otherwise) [docs/configuration.md#provider]; under `stages.staging` it only applies when you deploy staging [docs/configuration.md#stages-per-stage-overrides]. dev keeps 256.
- `pskit validate` (azure, staging): valid.

Deploy staging: **Deploy** (stage `staging`) or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 758
    B(758, provider="gcp", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions", "docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: billing
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, billing-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="POST /invoice with {net}. currency EUR and tax rate 0.19 should be env vars not in code. give back net, tax, total, currency",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/invoice.py: CURRENCY / TAX_RATE from ctx.env, BadRequest when net isn't a number",
                                   "functions.invoice: POST /invoice, environment CURRENCY EUR, TAX_RATE \"0.19\"",
                                   "Validate gcp, invoke with net 100"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/invoice.py", content=FUTURE + """from py_serverless_kit import BadRequest


def invoice(event, ctx):
    body = event.http.json(default={}) or {}
    net = body.get("net")
    if not isinstance(net, (int, float)) or isinstance(net, bool):
        raise BadRequest("net must be a number")
    rate = float(ctx.env.get("TAX_RATE", "0"))
    tax = round(net * rate, 2)
    return {"net": net, "tax": tax, "total": round(net + tax, 2), "currency": ctx.env.get("CURRENCY", "EUR")}
"""),
          S("set_config", path="functions.invoice",
            value={"handler": "app.invoice.invoice", "events": [{"http": "POST /invoice"}],
                   "environment": {"CURRENCY": "EUR", "TAX_RATE": "0.19"}}),
          S("invoke_local", function="invoice", method="POST", path="/invoice", data={"net": 100}),
      ],
      final="""Done:

```yaml
functions:
  invoice:
    handler: app.invoice.invoice
    environment:
      CURRENCY: EUR
      TAX_RATE: "0.19"
    events:
      - http: POST /invoice
```

- Environment values are strings, so the code converts `TAX_RATE` with `float()` [docs/handlers.md#environment-variables]. Non-number `net` → 400.
- `pskit validate` (gcp): valid. `{"net": 100}` → `{"net": 100, "tax": 19.0, "total": 119.0, "currency": "EUR"}`.

Change the rate per stage later with `stages.<stage>.functions.invoice.environment`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 759
    B(759, provider="azure", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: cafe-menu
provider:
  name: azure
  region: westeurope
functions:
  menu:
    handler: app.menu.menu
    events:
    - http: GET /menu
""",
          "app/__init__.py": "",
          "app/menu.py": FUTURE + """
ITEMS = [("Espresso", 2.2), ("Cappuccino", 3.1)]


def menu(event, ctx):
    rows = "".join(f"<li>{name}: {price:.2f} EUR</li>" for name, price in ITEMS)
    return f"<html><body><h1>Menu</h1><ul>{rows}</ul></body></html>"
""",
          "requirements.txt": ""}),
      user="""▶ Run locally gives:
  "status": 200,
  "headers": {"content-type": "text/plain; charset=utf-8"},
  "body": "<html><body><h1>Menu</h1><ul><li>Espresso: 2.20 EUR</li>...

browser show the tags as text, not a page. fix""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/menu.py: return Response.html(...) instead of a plain str (str = text/plain)",
                                   "Validate for azure, invoke GET /menu"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/menu.py", content=FUTURE + """from py_serverless_kit import Response

ITEMS = [("Espresso", 2.2), ("Cappuccino", 3.1)]


def menu(event, ctx):
    rows = "".join(f"<li>{name}: {price:.2f} EUR</li>" for name, price in ITEMS)
    return Response.html(f"<html><body><h1>Menu</h1><ul>{rows}</ul></body></html>")
"""),
          S("validate"),
          S("invoke_local", function="menu", method="GET", path="/menu"),
      ],
      final="""Cause: a returned `str` is sent as `text/plain`, so the browser shows the tags [docs/handlers.md#returning-a-response].

Change: `menu` now returns `Response.html(...)`, which sends `text/html`.

- `pskit validate` (azure): valid.
- GET /menu → 200, `content-type: text/html; charset=utf-8`, same page.

Run it again on **Test** > **▶ Run locally**; deploy with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 760
    B(760, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: waitlist
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="POST /signup {email} keep in memory is ok. and also GET /signup/count how many signed up",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["One function `signup` with both routes (in-memory data is per function, so they must share it)",
                                   "app/signup.py: branch on event.http.route; POST adds the email to a set (400 without email)",
                                   "Validate for aws, invoke POST then GET"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/signup.py", content=FUTURE + """from py_serverless_kit import BadRequest

EMAILS = set()


def signup(event, ctx):
    if event.http.route == "/signup/count":
        return {"count": len(EMAILS)}
    email = str((event.http.json(default={}) or {}).get("email", "")).strip().lower()
    if "@" not in email:
        raise BadRequest("email is required")
    EMAILS.add(email)
    return {"signed_up": email}, 201
"""),
          S("set_config", path="functions.signup",
            value={"handler": "app.signup.signup", "events": [{"http": "POST /signup"}, {"http": "GET /signup/count"}]}),
          S("invoke_local", function="signup", method="POST", path="/signup", data={"email": "ana@example.com"}),
          S("invoke_local", function="signup", method="GET", path="/signup/count"),
      ],
      final="""Done, one function `signup` with two routes:

```yaml
functions:
  signup:
    handler: app.signup.signup
    events:
      - http: POST /signup
      - http: GET /signup/count
```

- The code picks the route with `event.http.route` [docs/handlers.md#httprequest]. Same email twice counts once (it's a set).
- `pskit validate` (aws): valid. POST `{"email": "ana@example.com"}` → 201; GET /signup/count → `{"count": 0}`, because each local invoke is a new process. Inside one running Lambda instance the count adds up.

In-memory data is lost on cold starts and isn't shared between instances; for real numbers you need a database. Deploy: **Deploy** or `pskit deploy -s dev`."""),
]
