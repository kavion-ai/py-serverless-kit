"""Category B (build / add), batch 2. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 21
    B(21, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: bakery-site
provider:
  name: aws
  region: eu-west-2
functions: {}
""",
          "requirements.txt": ""}),
      user="my website www.example.com has a contact form. can you make the thing that receives it? it has name, email and message",
      steps=[
          S("get_project"),
          S("search_docs", query="http POST cors origins browser",
            docs=[D("docs/events.md", "http", start="**CORS**", end="AWS additionally configures CORS")]),
          S("propose_plan", steps=["Write `app/contact.py`: read name, email and message from the JSON body; 400 if one is missing or the email has no @",
                                   "Add function `contact` on POST /contact with CORS allowed only for https://www.example.com",
                                   "Validate for aws and send a test message locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/contact.py", content=FUTURE + """from py_serverless_kit import BadRequest


def receive(event, ctx):
    form = event.http.json(default={}) or {}
    missing = [k for k in ("name", "email", "message") if not str(form.get(k, "")).strip()]
    if missing:
        raise BadRequest("missing fields", details={"fields": missing})
    if "@" not in form["email"]:
        raise BadRequest("email looks wrong", details={"field": "email"})
    ctx.logger.info("contact form", extra={"email": form["email"], "length": len(form["message"])})
    return {"received": True}, 201
"""),
          S("set_config", path="functions.contact",
            value={"handler": "app.contact.receive",
                   "events": [{"http": {"path": "/contact", "method": "POST",
                                        "cors": {"origins": ["https://www.example.com"], "methods": ["POST"]}}}]}),
          S("invoke_local", function="contact", method="POST", path="/contact",
            data={"name": "Mia", "email": "mia@example.org", "message": "Do you bake rye bread?"}),
      ],
      final="""Done. The new function `contact` receives your form on `POST /contact`.

- Only your site `https://www.example.com` may call it from a browser (CORS) [docs/events.md#http].
- If name, email or message is missing, it answers 400 with the list of missing fields.
- `pskit validate` for aws: valid.
- Local test with a filled-in form: status 201, `{"received": true}`.

Right now it only logs the message. Tell me if it should e-mail you or save it somewhere.

Test it again on **Test** > **▶ Run locally**, or with `pskit invoke -f contact -d '{"name": "Mia", "email": "mia@example.org", "message": "Hi"}'`. To put it online, use the **Deploy** page or `pskit deploy -s dev`. Then point the form at the URL that `pskit info` shows."""),

    # ------------------------------------------------------------------ 22
    B(22, provider="gcp", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#storage", "docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      project=dict(files={
          "pskit.yml": """service: imgsync
provider:
  name: gcp
  region: europe-west4
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  index:
    handler: app.index.on_change
""",
          "app/__init__.py": "",
          "app/index.py": FUTURE + """

def on_change(event, ctx):
    changes = [{"key": r.key, "action": r.action} for r in event.records]
    for c in changes:
        ctx.logger.info("image change", extra=c)
    return {"changes": changes}
""",
          "requirements.txt": ""}),
      user="index: gcs trigger on raw-images, created+deleted, .png only",
      steps=[
          S("get_project"),
          S("search_docs", query="gcs storage trigger created deleted suffix gcp",
            docs=[D("docs/events.md", "storage", start="| gcp |", end="| gcp |")]),
          S("propose_plan", steps=["Add storage event to `index`: bucket raw-images, events [created, deleted], suffix .png",
                                   "Validate for gcp, invoke with a storage record"]),
          S("set_config", path="functions.index.events",
            value=[{"storage": {"bucket": "raw-images", "events": ["created", "deleted"], "suffix": ".png"}}]),
          S("invoke_local", function="index", type="storage", data={"bucket": "raw-images", "key": "cat.png"}),
      ],
      final="""Added to `index`:

```yaml
events:
  - storage: {bucket: raw-images, events: [created, deleted], suffix: .png}
```

- validate (gcp): valid. On GCP the suffix is applied by the runtime, and `created` / `deleted` become separate deployments (`index-storage0`, ...) behind one logical function [docs/events.md#storage].
- invoke: `{"changes": [{"key": "cat.png", "action": "created"}]}`.

Retest: `pskit invoke -f index -t storage -d '{"bucket": "raw-images", "key": "cat.png"}'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 23
    B(23, provider="azure", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue", "docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: newsletter
provider:
  name: azure
  region: northeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions: {}
""",
          "requirements.txt": ""}),
      user="hi, need worker that take email jobs from azure queue and send. queue name EmailJobs. message have to and subject",
      steps=[
          S("get_project"),
          S("search_docs", query="azure storage queue name rules worker",
            docs=[D("docs/events.md", "queue", start="| Option |", end="On GCP a \"queue\" is a Pub/Sub topic")]),
          S("propose_plan", steps=["Use queue name `email-jobs`: Azure queue names must be lowercase (EmailJobs is not allowed)",
                                   "Write `app/mailer.py`: for each message check `to` and `subject`, log the send",
                                   "Add function `send-email` with a queue trigger on `email-jobs`",
                                   "Validate for azure (staging) and run one message locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/mailer.py", content=FUTURE + """

def send(event, ctx):
    sent = []
    for record in event.records:
        job = record.json(default={}) or {}
        if not job.get("to") or not job.get("subject"):
            raise ValueError(f"message {record.id} needs 'to' and 'subject'")
        # call your mail service here (SMTP, SendGrid, ...)
        ctx.logger.info("send email", extra={"to": job["to"], "subject": job["subject"]})
        sent.append(job["to"])
    return {"sent": sent}
"""),
          S("set_config", path="functions.send-email",
            value={"handler": "app.mailer.send", "events": [{"queue": "email-jobs"}]}),
          S("invoke_local", function="send-email", type="queue",
            data=[{"to": "anna@example.com", "subject": "Welcome"}]),
      ],
      final="""Done. Function `send-email` reads the Azure Storage Queue **`email-jobs`**. I could not use `EmailJobs`, because Azure queue names must be lowercase letters, digits and dashes [docs/events.md#queue].

- `pskit validate` (azure, staging): valid.
- Local run with one message: `{"sent": ["anna@example.com"]}`.

A message without `to` or `subject` raises an error. On Azure the message is then retried, and after too many tries it goes to `email-jobs-poison`. The real sending is still a comment in `app/mailer.py`. Tell me which mail service you use and I'll add it.

Test: **Test** > **▶ Run locally**, or `pskit invoke -f send-email -t queue -d '[{"to": "anna@example.com", "subject": "Hi"}]'`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 24
    B(24, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/smtp/README.md#what-the-handler-receives", "docs/smtp/README.md#test-it"],
      project=dict(files={
          "pskit.yml": """service: helpdesk
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
resources:
  support-mail:
    type: smtp
    external: true
    connection: {host: 203.0.113.20, port: 25, domains: support.example.com, hostname: mail.support.example.com}
functions:
  tickets:
    handler: app.tickets.list_tickets
    events:
    - http: GET /tickets
""",
          "app/__init__.py": "",
          "app/tickets.py": FUTURE + """

def list_tickets(event, ctx):
    return []
""",
          "requirements.txt": ""}),
      user="The SMTP server `support-mail` is already running for support.example.com. Add a function `on-support-mail` that turns each incoming mail into a ticket dict: sender, subject, first 500 characters of the text body, and the attachment file names. Logging the ticket is enough for now.",
      steps=[
          S("get_project"),
          S("search_docs", query="smtp trigger handler mail fields attachments",
            docs=[D("docs/smtp/README.md", "what-the-handler-receives", start="| Field |", end="| `attachments` |")]),
          S("propose_plan", steps=["Add `on_support_mail` to `app/tickets.py`: build {sender, subject, body (500 chars), attachments} from event.data and log it",
                                   "Add function `on-support-mail` with `- smtp: {resource: support-mail}`",
                                   "Validate for onprem (prod) and run a test mail locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tickets.py", content=FUTURE + """

def list_tickets(event, ctx):
    return []


def on_support_mail(event, ctx):
    mail = event.data or {}
    ticket = {
        "sender": mail.get("from"),
        "subject": mail.get("subject") or "(no subject)",
        "body": (mail.get("text") or mail.get("html") or "")[:500],
        "attachments": [a.get("filename") for a in mail.get("attachments") or []],
    }
    ctx.logger.info("new ticket", extra={"ticket": ticket})
    return ticket
"""),
          S("set_config", path="functions.on-support-mail",
            value={"handler": "app.tickets.on_support_mail", "events": [{"smtp": {"resource": "support-mail"}}]}),
          S("invoke_local", function="on-support-mail", type="smtp",
            data={"from": "customer@example.org", "to": ["help@support.example.com"], "subject": "Printer broken",
                  "text": "The printer on floor 2 shows error E5."}),
      ],
      final="""Added `on-support-mail`, attached to the SMTP server `support-mail`:

```yaml
functions:
  on-support-mail:
    handler: app.tickets.on_support_mail
    events:
      - smtp: {resource: support-mail}
```

- `pskit validate` (onprem, prod): valid.
- Local test mail: the ticket came back with sender `customer@example.org`, subject `Printer broken`, the body text and an empty attachment list.

The SMTP server itself does not change. The host learns about the new trigger only after a deploy: **Deploy** page (typed confirmation for `prod`) or `pskit deploy -s prod`. Until then, mail for this function gets a temporary `451` and the sender retries [docs/smtp/README.md#troubleshooting].

Test again without DNS: `pskit invoke -f on-support-mail -t smtp -d '{"from": "a@example.org", "subject": "Hi", "text": "Hello"}'`. After deploy, `pskit trigger -f on-support-mail` sends a test mail to the running host [docs/smtp/README.md#test-it]."""),

    # ------------------------------------------------------------------ 25
    B(25, provider="aws", stage="staging", mode="auto", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#choice-rules", "docs/migrating-from-aws.md#step-3-translate-step-functions"],
      project=dict(files={
          "pskit.yml": """service: refunds
provider:
  name: aws
  region: us-east-2
functions:
  auto-approve:
    handler: app.refunds.auto_approve
  manual-review:
    handler: app.refunds.manual_review
""",
          "app/__init__.py": "",
          "app/refunds.py": FUTURE + """

def auto_approve(event, ctx):
    return {**(event.data or {}), "approved": True, "by": "auto"}


def manual_review(event, ctx):
    return {**(event.data or {}), "approved": None, "by": "queue-for-human"}
""",
          "requirements.txt": ""}),
      user="In Step Functions we had a Choice state: if $.amount > 500 go to ManualReview, otherwise AutoApprove. Both are Lambda tasks that end the execution. Rebuild it as a pskit workflow `refund-flow`.",
      steps=[
          S("get_project"),
          S("search_docs", query="choice state gt default next",
            docs=[D("docs/workflows.md", "choice-rules", end="| `gt`, `gte`, `lt`, `lte` |")]),
          S("propose_plan", steps=["Add workflow `refund-flow`: Route (choice: $.amount gt 500 -> ManualReview, default AutoApprove)",
                                   "ManualReview and AutoApprove are task states that end",
                                   "Validate for aws (staging) and run the manual-review task locally"]),
          S("set_config", path="workflows.refund-flow",
            value={"start_at": "Route",
                   "states": {"Route": {"type": "choice",
                                        "choices": [{"variable": "$.amount", "gt": 500, "next": "ManualReview"}],
                                        "default": "AutoApprove"},
                              "ManualReview": {"type": "task", "function": "manual-review", "end": True},
                              "AutoApprove": {"type": "task", "function": "auto-approve", "end": True}}}),
          S("invoke_local", function="manual-review", type="workflow", data={"refund_id": "r-17", "amount": 900}),
      ],
      final="""`refund-flow` is in place. On AWS it compiles to a Step Functions state machine again:

```yaml
workflows:
  refund-flow:
    start_at: Route
    states:
      Route:
        type: choice
        choices:
          - {variable: "$.amount", gt: 500, next: ManualReview}
        default: AutoApprove
      ManualReview: {type: task, function: manual-review, end: true}
      AutoApprove:  {type: task, function: auto-approve, end: true}
```

- `pskit validate` (aws, staging): valid.
- `manual-review` run locally as a workflow task with amount 900: returned the refund with `"by": "queue-for-human"`.

Compare with your old ASL: `pskit workflow show refund-flow --format asl`. Run the whole flow locally: `pskit workflow run refund-flow -i '{"refund_id": "r-17", "amount": 120}' --history`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 26
    B(26, provider="onprem", stage="dev", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#fields", "docs/resources.md#secrets"],
      project=dict(files={
          "pskit.yml": """service: ledger
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8093
functions:
  api:
    handler: app.api.health
    events:
    - http: GET /health
  nightly:
    handler: app.api.nightly
    events:
    - schedule: 0 1 * * *
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def health(event, ctx):
    return {"ok": True}


def nightly(event, ctx):
    return {"ran": True}
""",
          "requirements.txt": ""}),
      user="add external postgres `ledger-db` (db-1.example.com:5432, db ledger, password from LEDGER_DB_PASSWORD), bind to api only. /health should report db host",
      steps=[
          S("get_project"),
          S("search_docs", query="database resource external password_env functions binding",
            docs=[D("docs/resources.md", "secrets", end="(`ctx.env[db[\"password_env\"]]`)")]),
          S("propose_plan", steps=["Add resources.ledger-db: type database, external, connection host/port/database + password_env LEDGER_DB_PASSWORD, functions [api]",
                                   "Change `health` to return the bound db host and whether the password is set",
                                   "Validate for onprem, invoke /health"]),
          S("set_config", path="resources.ledger-db",
            value={"type": "database", "external": True,
                   "connection": {"host": "db-1.example.com", "port": 5432, "database": "ledger",
                                  "password_env": "LEDGER_DB_PASSWORD"},
                   "functions": ["api"]}),
          S("write_file", path="app/api.py", content=FUTURE + """from py_serverless_kit import resource


def health(event, ctx):
    db = resource("ledger-db")
    return {"ok": True, "db": f'{db["host"]}:{db["port"]}', "password_set": bool(ctx.env.get(db["password_env"]))}


def nightly(event, ctx):
    return {"ran": True}
"""),
          S("validate"),
          S("invoke_local", function="api", method="GET", path="/health"),
      ],
      final="""Added:

```yaml
resources:
  ledger-db:
    type: database
    external: true
    connection: {host: db-1.example.com, port: 5432, database: ledger, password_env: LEDGER_DB_PASSWORD}
    functions: [api]
```

- validate (onprem): valid.
- invoke `/health`: 200, `{"ok": true, "db": "db-1.example.com:5432", "password_set": false}`. The password is false because `LEDGER_DB_PASSWORD` isn't set in this shell.

Only the variable *name* is in pskit.yml. Set the secret where the host runs, or ship it with `provider.options.env_file` [docs/resources.md#secrets]. `nightly` doesn't get the binding (`functions: [api]`). Deploy: `pskit deploy -s dev` or **Deploy**."""),

    # ------------------------------------------------------------------ 27
    B(27, provider="gcp", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#topic", "docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: release-bot
provider:
  name: gcp
  region: us-east1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions: {}
""",
          "requirements.txt": ""}),
      user="this is what CI publishes to pub/sub topic `deploys`:\n{\"service\": \"checkout\", \"version\": \"4.2.0\", \"status\": \"succeeded\"}\nwe want a slack message per event. webhook url is secret, don't commit it",
      steps=[
          S("get_project"),
          S("search_docs", query="env variable secret default value",
            docs=[D("docs/configuration.md", "variables", end="| `${env:NAME, default}`")]),
          S("propose_plan", steps=["Write `app/notify.py`: build the Slack text per message and POST it to SLACK_WEBHOOK_URL (skip with a log line when it is empty)",
                                   "Add function `notify-slack` with a topic trigger on `deploys` and SLACK_WEBHOOK_URL: ${env:SLACK_WEBHOOK_URL, }",
                                   "Validate for gcp (prod) and run your sample message locally (no URL set, so nothing is sent)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/notify.py", content=FUTURE + """import json
import urllib.request


def notify(event, ctx):
    url = ctx.env.get("SLACK_WEBHOOK_URL", "")
    texts = []
    for record in event.records:
        msg = record.json(default={}) or {}
        texts.append(f"{msg.get('service')} {msg.get('version')}: {msg.get('status')}")
    for text in texts:
        if not url:
            ctx.logger.info("no SLACK_WEBHOOK_URL, not sent", extra={"text": text})
            continue
        req = urllib.request.Request(url, data=json.dumps({"text": text}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    return {"messages": texts}
"""),
          S("set_config", path="functions.notify-slack",
            value={"handler": "app.notify.notify",
                   "environment": {"SLACK_WEBHOOK_URL": "${env:SLACK_WEBHOOK_URL, }"},
                   "events": [{"topic": "deploys"}]}),
          S("invoke_local", function="notify-slack", type="topic",
            data=[{"service": "checkout", "version": "4.2.0", "status": "succeeded"}]),
      ],
      final="""Added `notify-slack`, subscribed to the Pub/Sub topic `deploys`. It posts one Slack line per event, e.g. `checkout 4.2.0: succeeded`.

- `pskit validate` (gcp, prod): valid.
- Local run with your sample: it built `checkout 4.2.0: succeeded` and logged "not sent", because `SLACK_WEBHOOK_URL` is empty here.

The URL is not in the repo. pskit.yml only has `${env:SLACK_WEBHOOK_URL, }`, which is filled from your shell when you deploy [docs/configuration.md#variables]. So export `SLACK_WEBHOOK_URL` before deploying (in studio: **Setup & credentials** > *Environment variables* > **Set for this session**).

Test: `pskit invoke -f notify-slack -t topic -d '[{"service": "checkout", "version": "4.2.0", "status": "succeeded"}]'`. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 28
    B(28, provider="alibaba", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: morning-news
provider:
  name: alibaba
  region: cn-hangzhou
functions:
  digest:
    handler: app.digest.build
""",
          "app/__init__.py": "",
          "app/digest.py": FUTURE + """

def build(event, ctx):
    topics = (event.data or {}).get("topics", [])
    ctx.logger.info("building digest", extra={"topics": topics})
    return {"topics": topics, "items": 0}
""",
          "requirements.txt": ""}),
      user="I want my digest thing to start by itself every morning at 8 o'clock China time",
      steps=[
          S("get_project"),
          S("search_docs", query="schedule cron timezone alibaba",
            docs=[D("docs/events.md", "schedule", start="| alibaba |", end="| alibaba |"),
                  D("docs/events.md", "schedule", start="A rate that can't be expressed")]),
          S("ask_user", question="Should the digest get any input when it starts on its own? It reads a `topics` list. For example [\"tech\", \"sport\"], or nothing.",
            answer="yes tech and business"),
          S("propose_plan", steps=["Add a schedule to `digest`: cron `0 8 * * *`, timezone Asia/Shanghai, input {topics: [tech, business]}",
                                   "Validate for alibaba and run the scheduled start locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.digest.events",
            value=[{"schedule": {"cron": "0 8 * * *", "timezone": "Asia/Shanghai",
                                 "input": {"topics": ["tech", "business"]}}}]),
          S("invoke_local", function="digest", type="schedule"),
      ],
      final="""Done. `digest` now starts by itself every day at 08:00 China time, with the topics tech and business:

```yaml
events:
  - schedule:
      cron: "0 8 * * *"
      timezone: Asia/Shanghai
      input: {topics: [tech, business]}
```

Alibaba honours the timezone in the cron form [docs/events.md#schedule].

- `pskit validate` for alibaba: valid.
- A local scheduled start returned `{"topics": ["tech", "business"], "items": 0}`.

Try it again on **Test** > **▶ Run locally** (pick the schedule event), or with `pskit invoke -f digest -t schedule`. It runs by itself only after you deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 29
    B(29, provider="huawei", stage="staging", mode="auto", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#huawei-functiongraph", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: parcel-track
provider:
  name: huawei
  region: ap-southeast-1
functions:
  ingest:
    handler: app.track.ingest
    events:
    - topic: parcel-scans
""",
          "app/__init__.py": "",
          "app/track.py": FUTURE + """

def ingest(event, ctx):
    return {"scans": len(event.records)}
""",
          "requirements.txt": ""}),
      user="We need a public `GET /parcels/{parcel_id}` on FunctionGraph that returns the parcel id and a status of \"in_transit\" for now. Our ops team gave us the dedicated APIG instance id; it lives in the HUAWEI_APIG_INSTANCE_ID variable on the deploy machine. Don't hard-code it.",
      steps=[
          S("get_project"),
          S("search_docs", query="huawei apig_instance_id http",
            docs=[D("docs/events.md", "events-triggers", start="¹ Huawei HTTP", end="¹ Huawei HTTP")]),
          S("propose_plan", steps=["Set provider.options.apig_instance_id to ${env:HUAWEI_APIG_INSTANCE_ID}",
                                   "Add `get_parcel` to `app/track.py` and function `get-parcel` on GET /parcels/{parcel_id}",
                                   "Validate for huawei (staging) and call /parcels/PX-1 locally"]),
          S("set_config", path="provider.options.apig_instance_id",
            value="${env:HUAWEI_APIG_INSTANCE_ID, 00000000000000000000000000000000}"),
          S("write_file", path="app/track.py", content=FUTURE + """

def ingest(event, ctx):
    return {"scans": len(event.records)}


def get_parcel(event, ctx):
    parcel_id = event.http.path_params["parcel_id"]
    return {"parcel_id": parcel_id, "status": "in_transit"}
"""),
          S("set_config", path="functions.get-parcel",
            value={"handler": "app.track.get_parcel", "events": [{"http": "GET /parcels/{parcel_id}"}]}),
          S("invoke_local", function="get-parcel", method="GET", path="/parcels/PX-1"),
      ],
      final="""Added `get-parcel` on `GET /parcels/{parcel_id}`, plus the API Gateway setting that Huawei HTTP events need:

```yaml
provider:
  options:
    apig_instance_id: ${env:HUAWEI_APIG_INSTANCE_ID, 00000000000000000000000000000000}
functions:
  get-parcel:
    handler: app.track.get_parcel
    events:
      - http: GET /parcels/{parcel_id}
```

- `pskit validate` (huawei, staging): valid.
- Local call `/parcels/PX-1`: 200, `{"parcel_id": "PX-1", "status": "in_transit"}`.

The zeros after the comma are only a placeholder so validate works on machines without the variable. On the deploy machine the real `HUAWEI_APIG_INSTANCE_ID` wins. If you'd rather have deploy fail when it's missing, drop the default. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 30
    B(30, provider="azure", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#topic", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: accounting
provider:
  name: azure
  region: westeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions: {}
""",
          "requirements.txt": ""}),
      user="service bus topic invoices -> fn book-invoice, log invoice_no + total",
      steps=[
          S("get_project"),
          S("search_docs", query="azure service bus topic subscription",
            docs=[D("docs/events.md", "topic", start="| Provider |", end="| azure |")]),
          S("propose_plan", steps=["Write `app/booking.py` (log invoice_no, total per message)",
                                   "Add `book-invoice` with `- topic: invoices`",
                                   "Validate for azure, invoke with one message"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/booking.py", content=FUTURE + """

def book(event, ctx):
    booked = []
    for record in event.records:
        inv = record.json(default={}) or {}
        ctx.logger.info("book invoice", extra={"invoice_no": inv.get("invoice_no"), "total": inv.get("total")})
        booked.append(inv.get("invoice_no"))
    return {"booked": booked}
"""),
          S("set_config", path="functions.book-invoice",
            value={"handler": "app.booking.book", "events": [{"topic": "invoices"}]}),
          S("invoke_local", function="book-invoice", type="topic", data=[{"invoice_no": "INV-2026-0042", "total": 199.0}]),
      ],
      final="""Added `book-invoice` with `- topic: invoices`. On Azure this is a Service Bus topic with one subscription for the function [docs/events.md#topic].

- validate (azure): valid.
- invoke: `{"booked": ["INV-2026-0042"]}`.

Note: if you add a `filter` later, it won't be applied on Service Bus, so filter in the handler. Retest: `pskit invoke -f book-invoice -t topic -d '[{"invoice_no": "INV-1", "total": 5}]'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 31
    B(31, provider="onprem", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: sensors
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8097
functions:
  poll:
    handler: app.poll.read_sensors
""",
          "app/__init__.py": "",
          "app/poll.py": FUTURE + """

def read_sensors(event, ctx):
    ctx.logger.info("polling sensors")
    return {"read": 0}
""",
          "requirements.txt": ""}),
      user="poll function must run each 7 minute on our server. on cloud i read 7 not working, onprem ok?",
      steps=[
          S("get_project"),
          S("search_docs", query="schedule 7 minutes rate onprem",
            docs=[D("docs/events.md", "schedule", start="| onprem |")]),
          S("propose_plan", steps=["Add `schedule: 7 minutes` to `poll`",
                                   "Validate for onprem and run the schedule event locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.poll.events", value=[{"schedule": "7 minutes"}]),
          S("invoke_local", function="poll", type="schedule"),
      ],
      final="""Yes, on-prem is ok with 7 minutes. The on-prem host has its own scheduler, and a rate like `7 minutes` is valid there [docs/events.md#schedule]. Cloud providers that only know cron cannot do 7, because it does not divide 60.

Added to `poll`:

```yaml
events:
  - schedule: 7 minutes
```

- `pskit validate` for onprem: valid.
- Local schedule run: logged "polling sensors" and returned `{"read": 0}`.

Test again: `pskit invoke -f poll -t schedule`. Start it on the server: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 32
    B(32, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#queue", "docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: payments
provider:
  name: aws
  region: eu-central-1
functions: {}
""",
          "requirements.txt": ""}),
      user="Payments for the same customer must be processed in order. Create a function `settle` behind a FIFO SQS queue `settlements`, batch size 5, with a dead-letter queue `settlements-dlq`. Report partial failures so one bad payment doesn't block the batch. A message looks like {\"payment_id\": \"p1\", \"amount_cents\": 1200}.",
      steps=[
          S("get_project"),
          S("search_docs", query="fifo queue dead_letter max_receive sqs",
            docs=[D("docs/events.md", "queue", start="| Option |", end="| partial batch failure |")]),
          S("propose_plan", steps=["Write `app/settle.py`: settle each payment, fail only records with a missing or non-positive amount (BatchResult)",
                                   "Add `settle` with queue `settlements`: fifo, batch_size 5, dead_letter settlements-dlq",
                                   "Validate for aws (prod) and run a good and a bad message locally"],
            result={"decision": "approved", "note": "max_receive 3, not the default"}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/settle.py", content=FUTURE + """from py_serverless_kit import BatchResult


def settle(event, ctx):
    result = BatchResult()
    for record in event.records:
        payment = record.json(default={}) or {}
        amount = payment.get("amount_cents")
        if not isinstance(amount, int) or amount <= 0:
            ctx.logger.warning("bad payment", extra={"payment_id": payment.get("payment_id")})
            result.fail(record)
            continue
        ctx.logger.info("settled", extra={"payment_id": payment["payment_id"], "amount_cents": amount})
    return result
"""),
          S("set_config", path="functions.settle",
            value={"handler": "app.settle.settle",
                   "events": [{"queue": {"name": "settlements", "fifo": True, "batch_size": 5,
                                         "dead_letter": "settlements-dlq", "max_receive": 3}}]},
            say="Setting max_receive to 3 as you noted."),
          S("invoke_local", function="settle", type="queue",
            data=[{"payment_id": "p1", "amount_cents": 1200}, {"payment_id": "p2", "amount_cents": 0}]),
      ],
      final="""Added `settle` behind the FIFO queue (with `max_receive: 3`, per your note):

```yaml
functions:
  settle:
    handler: app.settle.settle
    events:
      - queue: {name: settlements, fifo: true, batch_size: 5, dead_letter: settlements-dlq, max_receive: 3}
```

- `pskit validate` (aws, prod): valid. On AWS `fifo` adds the `.fifo` suffix with content-based dedup, and the redrive policy sends a message to `settlements-dlq` after 3 receives [docs/events.md#queue].
- Local run with `p1` (1200) and `p2` (0): `p1` settled, `p2` reported in `batchItemFailures`. Only `p2` goes back to SQS.

Retest: `pskit invoke -f settle -t queue -d '[{"payment_id": "p3", "amount_cents": 500}]'`. Deploy prod from **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 33
    B(33, provider="tencent", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: assets
provider:
  name: tencent
  region: ap-shanghai
functions: {}
""",
          "requirements.txt": ""}),
      user="catch-all route under /files/ on scf, any method, return the matched sub-path + method",
      steps=[
          S("get_project"),
          S("search_docs", query="greedy path parameter tencent prefix route ANY",
            docs=[D("docs/events.md", "http", start="**Path templates**", end="Two functions may not declare"),
                  D("docs/events.md", "http", start="Provider notes:")]),
          S("propose_plan", steps=["Write `app/files.py` returning path_params['path'] and the method",
                                   "Add `files` on ANY /files/{path+}",
                                   "Validate for tencent, invoke GET /files/a/b.txt"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/files.py", content=FUTURE + """

def serve(event, ctx):
    return {"path": event.http.path_params.get("path", ""), "method": event.http.method}
"""),
          S("set_config", path="functions.files",
            value={"handler": "app.files.serve", "events": [{"http": "ANY /files/{path+}"}]}),
          S("invoke_local", function="files", method="GET", path="/files/a/b.txt"),
      ],
      final="""Added `files` on `ANY /files/{path+}`. On Tencent, `{path+}` becomes a prefix route. pskit's runtime still fills `path_params["path"]` [docs/events.md#http].

- validate (tencent): valid.
- invoke `GET /files/a/b.txt`: 200, `{"path": "a/b.txt", "method": "GET"}`.

Retest with another method: `pskit invoke -f files --method DELETE --path /files/x/y`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 34
    B(34, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#compiler-notes-and-limits"],
      project=dict(files={
          "pskit.yml": """service: transcode
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  convert:
    handler: app.media.convert
    timeout: 300
""",
          "app/__init__.py": "",
          "app/media.py": FUTURE + """

def convert(event, ctx):
    item = event.data or {}
    return {"source": item.get("key"), "target": str(item.get("key", "")).rsplit(".", 1)[0] + ".mp4"}
""",
          "requirements.txt": ""}),
      user="In Step Functions I used a Map state with MaxConcurrency 5 over $.files to call a convert Lambda per file. How does that look in pskit on GCP? Please add it as workflow `convert-all`.",
      steps=[
          S("get_project"),
          S("search_docs", query="map state items_path iterator max_concurrency",
            docs=[D("docs/workflows.md", "state-types", start="| `parallel` |", end="| `map` |")]),
          S("propose_plan", steps=["Add workflow `convert-all` with one map state EachFile: items_path $.files, max_concurrency 5, iterator = task `convert`",
                                   "Validate for gcp (staging) and run `convert` locally on one file item"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.convert-all",
            value={"start_at": "EachFile",
                   "states": {"EachFile": {"type": "map", "items_path": "$.files", "max_concurrency": 5,
                                           "iterator": {"start_at": "Convert",
                                                        "states": {"Convert": {"type": "task", "function": "convert",
                                                                               "end": True}}},
                                           "end": True}}}),
          S("invoke_local", function="convert", type="workflow", data={"key": "talks/keynote.mov"}),
      ],
      final="""Your Map state maps almost 1:1. `ItemsPath` -> `items_path`, `MaxConcurrency` -> `max_concurrency`, `Iterator` -> `iterator`:

```yaml
workflows:
  convert-all:
    start_at: EachFile
    states:
      EachFile:
        type: map
        items_path: $.files
        max_concurrency: 5
        iterator:
          start_at: Convert
          states:
            Convert: {type: task, function: convert, end: true}
        end: true
```

- `pskit validate` (gcp, staging): valid. On GCP this deploys as Cloud Workflows. The result is a list with one item per file [docs/workflows.md#state-types].
- `convert` run locally on one item: `{"source": "talks/keynote.mov", "target": "talks/keynote.mp4"}`.

One GCP difference: `retry`/`catch` work on `task` states only, so put them on `Convert`, not on the map [docs/workflows.md#compiler-notes-and-limits]. Run it locally: `pskit workflow run convert-all -i '{"files": [{"key": "a.mov"}, {"key": "b.mov"}]}'`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 35
    B(35, provider="cloudflare", stage="prod", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule", "docs/providers.md#cloudflare-workers"],
      project=dict(files={
          "pskit.yml": """service: price-cache
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, 0123456789abcdef0123456789abcdef}
functions:
  prices:
    handler: app.prices.get_prices
    events:
    - http: GET /prices
""",
          "app/__init__.py": "",
          "app/prices.py": FUTURE + """

def get_prices(event, ctx):
    return {"prices": []}
""",
          "requirements.txt": ""}),
      user="want refresh function every 6 hour at 0 min, on the worker. it just log 'refresh' for now",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `refresh` to `app/prices.py` that logs 'refresh'",
                                   "Add function `refresh` with schedule cron `0 */6 * * *` (Cloudflare Cron Trigger)",
                                   "Validate for cloudflare (prod) and run the schedule locally"]),
          S("write_file", path="app/prices.py", content=FUTURE + """

def get_prices(event, ctx):
    return {"prices": []}


def refresh(event, ctx):
    ctx.logger.info("refresh")
    return {"refreshed": True}
"""),
          S("set_config", path="functions.refresh",
            value={"handler": "app.prices.refresh", "events": [{"schedule": "0 */6 * * *"}]}),
          S("invoke_local", function="refresh", type="schedule"),
      ],
      final="""Done. New function `refresh` with `- schedule: "0 */6 * * *"`, so it runs at minute 0 every 6 hours. On Cloudflare this is a Cron Trigger [docs/events.md#schedule].

- validate (cloudflare, prod): valid. The Pyodide warning is only a reminder that Python Workers get the stdlib and Pyodide packages. This handler needs nothing else.
- local schedule run: logged "refresh", returned `{"refreshed": true}`.

Test: `pskit invoke -f refresh -t schedule`. Deploy prod: **Deploy** page (it asks you to type a confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 36
    B(36, provider="digitalocean", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#httprequest", "docs/providers.md#digitalocean-functions"],
      project=dict(files={
          "pskit.yml": """service: world-clock
provider:
  name: digitalocean
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE, fn-00000000-0000-0000-0000-000000000000}
functions: {}
""",
          "requirements.txt": ""}),
      user="can i have a link that tells me what time it is in some city? like ?city=Tokyo",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/clock.py`: look up the time zone for ?city= (a small list: Tokyo, London, New_York, Berlin), 404 for other cities",
                                   "Add function `clock` on GET /time",
                                   "Validate for digitalocean and call /time?city=Tokyo locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/clock.py", content=FUTURE + """from datetime import datetime, timedelta, timezone

from py_serverless_kit import NotFound

# fixed offsets (no daylight saving) keep this stdlib-only and identical on every machine
OFFSETS = {"tokyo": 9, "london": 0, "new_york": -5, "berlin": 1}


def now(event, ctx):
    city = event.http.query.get("city", "London").strip().lower().replace(" ", "_")
    if city not in OFFSETS:
        raise NotFound(f"unknown city {city}", details={"known": sorted(OFFSETS)})
    tz = timezone(timedelta(hours=OFFSETS[city]))
    return {"city": city, "time": datetime.now(tz).strftime("%H:%M"), "utc_offset": OFFSETS[city]}
"""),
          S("set_config", path="functions.clock",
            value={"handler": "app.clock.now", "events": [{"http": "GET /time"}]}),
          S("invoke_local", function="clock", method="GET", path="/time?city=Tokyo"),
      ],
      final="""Done. You now have `GET /time?city=Tokyo`.

- It knows Tokyo, London, New York (`?city=new york`) and Berlin. Any other city gives a 404 that lists the known ones. The offsets are fixed, so summer time is not counted.
- `pskit validate` for digitalocean: valid. There is one warning: `doctl` is not installed on this machine, and deploy will need it.
- Local test with `?city=Tokyo`: status 200 with the Tokyo time and `"utc_offset": 9`.

Try it on **Test** > **▶ Run locally**, or with `pskit invoke -f clock --path "/time?city=Berlin"`. To put it online, install and log in to doctl (`doctl auth init`), then use the **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 37
    B(37, provider="onprem", stage="staging", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#storage", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: scanner
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8098
    services:
      storage: {use: directory, path: /srv/scans}
functions: {}
""",
          "requirements.txt": ""}),
      user="$ ls /srv/scans/inbox\nscan_0001.pdf  scan_0002.pdf  notes.txt\nthe scanner drops files there. run something for every new pdf and when one is deleted",
      steps=[
          S("get_project"),
          S("search_docs", query="onprem storage directory prefix suffix deleted first start",
            docs=[D("docs/events.md", "storage", start="| onprem |", end="| onprem |")]),
          S("propose_plan", steps=["Write `app/scans.py` that logs each created/deleted PDF",
                                   "Add `on-scan` with storage trigger: bucket inbox, events [created, deleted], suffix .pdf",
                                   "Validate for onprem (staging) and run a created record locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/scans.py", content=FUTURE + """

def on_scan(event, ctx):
    seen = []
    for record in event.records:
        ctx.logger.info("scan", extra={"key": record.key, "action": record.action, "size": record.size})
        seen.append({"key": record.key, "action": record.action})
    return {"scans": seen}
"""),
          S("set_config", path="functions.on-scan",
            value={"handler": "app.scans.on_scan",
                   "events": [{"storage": {"bucket": "inbox", "events": ["created", "deleted"], "suffix": ".pdf"}}]}),
          S("invoke_local", function="on-scan", type="storage", data={"bucket": "inbox", "key": "scan_0003.pdf", "size": 52011}),
      ],
      final="""Added `on-scan`. Your project already maps storage to `/srv/scans`, so bucket `inbox` is the folder `/srv/scans/inbox`:

```yaml
- storage: {bucket: inbox, events: [created, deleted], suffix: .pdf}
```

- validate (onprem, staging): valid.
- local run: `{"scans": [{"key": "scan_0003.pdf", "action": "created"}]}`. `notes.txt` is skipped by the suffix.

Note: on the first start the host records the files that are already there (`scan_0001.pdf`, `scan_0002.pdf`) and does not emit them [docs/events.md#storage]. Only new files and deletions after that run the function. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 38
    B(38, provider="ibm", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#httprequest", "docs/providers.md#ibm-code-engine-functions"],
      project=dict(files={
          "pskit.yml": """service: echo-test
provider:
  name: ibm
  region: eu-de
  runtime: python3.11
functions: {}
""",
          "requirements.txt": ""}),
      user="I'm learning. can you make the simplest possible thing that sends back whatever I post to it?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/echo.py`: return the posted JSON body (or the text if it isn't JSON)",
                                   "Add function `echo` on POST /echo",
                                   "Validate for ibm and post a small JSON locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/echo.py", content=FUTURE + """

def echo(event, ctx):
    body = event.http.json(default=None)
    if body is None:
        return {"you_sent": event.http.text()}
    return {"you_sent": body}
"""),
          S("set_config", path="functions.echo",
            value={"handler": "app.echo.echo", "events": [{"http": "POST /echo"}]}),
          S("invoke_local", function="echo", method="POST", path="/echo", data={"hello": "world"}),
      ],
      final="""Here it is: a function `echo` on `POST /echo` that sends back what you post.

```python
def echo(event, ctx):
    body = event.http.json(default=None)     # the posted JSON, or None
    if body is None:
        return {"you_sent": event.http.text()}
    return {"you_sent": body}                # a dict becomes a JSON response
```

- `pskit validate` for ibm: valid.
- Local test with `{"hello": "world"}`: status 200, `{"you_sent": {"hello": "world"}}`.

Play with it on **Test**: edit the payload, then **▶ Run locally**. Or run `pskit invoke -f echo -d '{"any": "thing"}'`. When you want it online, use **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 39
    B(39, provider="oracle", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#oracle-oci-functions", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: billing-api
provider:
  name: oracle
  region: uk-london-1
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID, ocid1.compartment.oc1..aaaa}
    subnet_ids:
    - ${env:OCI_SUBNET_ID, ocid1.subnet.oc1..aaaa}
    image_repository: ${env:OCI_IMAGE_REPO, lhr.ocir.io/mytenancy/billing-api}
functions: {}
""",
          "requirements.txt": ""}),
      user="oci: GET /invoices/{invoice_id} + DELETE same path, separate fns, 204 on delete",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/invoices.py` with get_invoice (returns id) and delete_invoice (returns None -> 204)",
                                   "Add `get-invoice` (GET) and `delete-invoice` (DELETE) on /invoices/{invoice_id}",
                                   "Validate for oracle, invoke both"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/invoices.py", content=FUTURE + """

def get_invoice(event, ctx):
    return {"invoice_id": event.http.path_params["invoice_id"]}


def delete_invoice(event, ctx):
    ctx.logger.info("delete invoice", extra={"invoice_id": event.http.path_params["invoice_id"]})
    return None
"""),
          S("set_config", path="functions.get-invoice",
            value={"handler": "app.invoices.get_invoice", "events": [{"http": "GET /invoices/{invoice_id}"}]}),
          S("set_config", path="functions.delete-invoice",
            value={"handler": "app.invoices.delete_invoice", "events": [{"http": "DELETE /invoices/{invoice_id}"}]}),
          S("invoke_local", function="delete-invoice", method="DELETE", path="/invoices/INV-9"),
      ],
      final="""Added `get-invoice` (GET) and `delete-invoice` (DELETE), both on `/invoices/{invoice_id}`. Same path, different methods, so no route clash.

- validate (oracle): valid, plus the API Gateway IAM policy warning that OCI prints for http events. The gateway needs that policy before deploy [docs/providers.md#oracle-oci-functions].
- invoke `DELETE /invoices/INV-9`: 204, empty body (a `None` return).

Retest the GET: `pskit invoke -f get-invoice --path /invoices/INV-9`. Deploy: **Deploy** or `pskit deploy -s dev`. It pushes the image to `image_repository`, so Docker must be logged in to OCIR."""),

    # ------------------------------------------------------------------ 40
    B(40, provider="azure", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#retry-and-catch", "docs/workflows.md#engines"],
      project=dict(files={
          "pskit.yml": """service: onboarding
provider:
  name: azure
  region: swedencentral
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions:
  check-id:
    handler: app.onboard.check_id
  create-account:
    handler: app.onboard.create_account
""",
          "app/__init__.py": "",
          "app/onboard.py": FUTURE + """

def check_id(event, ctx):
    person = dict(event.data or {})
    if not person.get("document_no"):
        raise ValueError("document_no missing")
    return {**person, "id_checked": True}


def create_account(event, ctx):
    person = dict(event.data or {})
    return {**person, "account": "acc-" + str(person.get("document_no"))}
""",
          "requirements.txt": ""}),
      user="Add a workflow `onboard` on Azure: CheckId (function check-id) then CreateAccount (create-account). If check-id raises ValueError, end the run as a failure with error IdRejected and cause \"identity check failed\". Keep the default engine.",
      steps=[
          S("get_project"),
          S("search_docs", query="catch ValueError fail state error cause",
            docs=[D("docs/workflows.md", "retry-and-catch", start="catch:", end="Error names are")]),
          S("propose_plan", steps=["Add workflow `onboard`: CheckId (task check-id, catch [ValueError] -> Rejected) -> CreateAccount (task, end)",
                                   "Rejected: fail state, error IdRejected, cause \"identity check failed\"",
                                   "No engine key: on Azure `auto` means the embedded engine",
                                   "Validate for azure (prod) and run check-id locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.onboard",
            value={"start_at": "CheckId",
                   "states": {"CheckId": {"type": "task", "function": "check-id", "next": "CreateAccount",
                                          "catch": [{"errors": ["ValueError"], "next": "Rejected"}]},
                              "CreateAccount": {"type": "task", "function": "create-account", "end": True},
                              "Rejected": {"type": "fail", "error": "IdRejected", "cause": "identity check failed"}}}),
          S("invoke_local", function="check-id", type="workflow", data={"name": "Lena", "document_no": "X123"}),
      ],
      final="""Added `onboard`:

```yaml
workflows:
  onboard:
    start_at: CheckId
    states:
      CheckId:
        type: task
        function: check-id
        catch: [{errors: [ValueError], next: Rejected}]
        next: CreateAccount
      CreateAccount: {type: task, function: create-account, end: true}
      Rejected: {type: fail, error: IdRejected, cause: identity check failed}
```

- `pskit validate` (azure, prod): valid, with one warning. With the default engine (`auto`) Azure uses the **embedded** engine, so pskit adds an `onboard-orchestrator` function, and the whole run is capped by that function's timeout (600 s max on Azure) [docs/workflows.md#embedded-orchestrator].
- `check-id` run locally with a document number: returned the person with `"id_checked": true`.

Run the flow locally, including the failure path: `pskit workflow run onboard -i '{"name": "Lena"}' --history`. Deploy prod from **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),
]
