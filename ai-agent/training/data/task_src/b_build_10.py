"""Category B (build / add), batch 10: on-premises only. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

SERVERS = json.dumps({"servers": {
    "app-1": {"host": "192.0.2.10", "user": "pskit", "port": 22},
    "app-2": {"host": "192.0.2.11", "user": "pskit", "port": 22},
    "db-1": {"host": "192.0.2.40", "user": "pskit", "port": 22},
    "gpu-box": {"host": "192.0.2.20", "user": "pskit", "port": 22}}}, indent=2)
CLUSTERS = json.dumps({"clusters": {"batch": {"orchestrator": "nomad", "master": "app-1", "servers": ["app-2", "gpu-box"]}}},
                      indent=2)


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", provider="onprem", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 181
    B(181, stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: docs-site
provider:
  name: onprem
  region: local
  options:
    port: 8181
functions: {}
""",
          "requirements.txt": ""}),
      user="GET /docs/{path+} -> serve from PAGES dict by full sub-path, 404 otherwise, text/markdown",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/docs.py`: path_params[\"path\"] lookup in PAGES, NotFound, return (text, 200, content-type)",
                                   "Add `docs` on GET /docs/{path+}", "Validate, invoke /docs/guides/setup.md"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/docs.py", content=FUTURE + """from py_serverless_kit import NotFound

PAGES = {
    "index.md": "# Docs\\n",
    "guides/setup.md": "# Setup\\nRun the installer.\\n",
}


def docs(event, ctx):
    path = event.http.path_params.get("path", "")
    if path not in PAGES:
        raise NotFound(f"no page {path}")
    return PAGES[path], 200, {"content-type": "text/markdown; charset=utf-8"}
"""),
          S("set_config", path="functions.docs", value={"handler": "app.docs.docs", "events": [{"http": "GET /docs/{path+}"}]}),
          S("invoke_local", function="docs", method="GET", path="/docs/guides/setup.md"),
      ],
      final="""Added `docs` on `GET /docs/{path+}`. `{path+}` is greedy, so `path_params["path"]` is the whole rest of the path (`guides/setup.md`) [docs/events.md#http].

- validate (onprem): valid.
- `/docs/guides/setup.md`: 200, `# Setup ...` with `content-type: text/markdown; charset=utf-8`.

Unknown pages raise `NotFound`, which gives a 404. Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 182
    B(182, stage="staging", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: prefs
provider:
  name: onprem
  region: local
  options:
    port: 8182
functions: {}
""",
          "requirements.txt": ""}),
      user="user choose language with POST /lang {lang: de}. remember it in a cookie 30 days, and GET /lang read the cookie back (default en)",
      steps=[
          S("get_project"),
          S("search_docs", query="set_cookie response cookies request",
            docs=[D("docs/handlers.md", "returning-a-response", start="```python", end="same_site=\"Lax\")")]),
          S("propose_plan", steps=["Write `app/lang.py`: set_lang returns Response.json(...).set_cookie(\"lang\", ..., max_age=30 days); get_lang reads event.http.cookies",
                                   "Add `set-lang` on POST /lang and `get-lang` on GET /lang",
                                   "Validate (onprem, staging), POST /lang locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/lang.py", content=FUTURE + """from py_serverless_kit import BadRequest, Response

ALLOWED = {"en", "de", "fr", "es"}
THIRTY_DAYS = 30 * 24 * 3600


def set_lang(event, ctx):
    lang = ((event.http.json(default={}) or {}).get("lang") or "").lower()
    if lang not in ALLOWED:
        raise BadRequest(f"lang must be one of {sorted(ALLOWED)}")
    return Response.json({"lang": lang}).set_cookie("lang", lang, max_age=THIRTY_DAYS, path="/",
                                                   http_only=True, same_site="Lax")


def get_lang(event, ctx):
    return {"lang": event.http.cookies.get("lang", "en")}
"""),
          S("set_config", path="functions",
            value={"set-lang": {"handler": "app.lang.set_lang", "events": [{"http": "POST /lang"}]},
                   "get-lang": {"handler": "app.lang.get_lang", "events": [{"http": "GET /lang"}]}}),
          S("invoke_local", function="set-lang", method="POST", path="/lang", data={"lang": "de"}),
      ],
      final="""Done:

- `set-lang` (`POST /lang`) answers `{"lang": "de"}` and sets the cookie `lang=de` for 30 days with `Response.json(...).set_cookie(...)` [docs/handlers.md#returning-a-response]. Unknown languages give 400.
- `get-lang` (`GET /lang`) reads `event.http.cookies["lang"]` and falls back to `en` [docs/handlers.md#httprequest].

Checks:
- `pskit validate` (onprem, staging): valid.
- Local `POST /lang {"lang": "de"}`: 200, `{"lang": "de"}`. The local output lists only the status, the content type and the body, so it doesn't show the cookie. After deploy, check the `Set-Cookie` header in the browser's developer tools.

Test the read: `pskit invoke -f get-lang --method GET --path /lang -H "cookie: lang=fr"`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 183
    B(183, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: badges
provider:
  name: onprem
  region: local
  options:
    port: 8183
functions: {}
""",
          "requirements.txt": ""}),
      user="can my function send back a picture? i want /badge.png to give a tiny green square image for our build screen",
      steps=[
          S("get_project"),
          S("search_docs", query="return image binary png response",
            docs=[D("docs/handlers.md", "returning-a-response", start="Response.binary", end="# base64-encoded for gateways automatically")]),
          S("propose_plan", steps=["Write `app/badge.py`: return Response.binary(png_bytes, \"image/png\") for a 1x1 green PNG",
                                   "Add function `badge` on GET /badge.png",
                                   "Validate for onprem and call it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/badge.py", content=FUTURE + """import base64

from py_serverless_kit import Response

# a 1x1 green PNG
GREEN = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def badge(event, ctx):
    return Response.binary(GREEN, "image/png")
"""),
          S("set_config", path="functions.badge", value={"handler": "app.badge.badge", "events": [{"http": "GET /badge.png"}]}),
          S("invoke_local", function="badge", method="GET", path="/badge.png"),
      ],
      final="""Yes. Return `Response.binary(data, "image/png")` and the browser gets a real image [docs/handlers.md#returning-a-response]. I added a function `badge` on `GET /badge.png` that sends a tiny green square.

- `pskit validate` (onprem): valid.
- Local call: 200 with `content-type: image/png`. The local output shows the image bytes base64-encoded, which is how pskit prints binary bodies.

On your build screen use `<img src="http://<server>:8183/badge.png">` after a deploy: **Deploy** page or `pskit deploy -s dev`. If you want red for failed builds later, tell me and I'll add a second color."""),

    # ------------------------------------------------------------------ 184
    B(184, stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#batchresult", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: webhooks-out
provider:
  name: onprem
  region: local
  options:
    port: 8184
functions: {}
""",
          "requirements.txt": ""}),
      user="A worker `deliver-webhook` on queue `outbound-hooks` (5 per batch, give up after 8 tries into outbound-hooks-dlq). A message without a `url` is a permanent problem: mark just that one failed. Everything else is a fake delivery for now that just logs.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/hooks.py`: BatchResult; fail(record) when url is missing, otherwise log the delivery",
                                   "Add `deliver-webhook` with queue {name: outbound-hooks, batch_size: 5, max_receive: 8, dead_letter: outbound-hooks-dlq}",
                                   "Validate (onprem, prod), invoke with a good and a bad message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/hooks.py", content=FUTURE + """from py_serverless_kit import BatchResult


def deliver(event, ctx):
    result = BatchResult()
    for record in event.records:
        hook = record.json(default={}) or {}
        if not hook.get("url"):
            ctx.logger.error("webhook without url", extra={"message_id": record.id})
            result.fail(record)
            continue
        ctx.logger.info("deliver webhook", extra={"url": hook["url"], "event": hook.get("event")})
    return result
"""),
          S("set_config", path="functions.deliver-webhook",
            value={"handler": "app.hooks.deliver",
                   "events": [{"queue": {"name": "outbound-hooks", "batch_size": 5, "max_receive": 8,
                                         "dead_letter": "outbound-hooks-dlq"}}]}),
          S("invoke_local", function="deliver-webhook", type="queue",
            data=[{"url": "https://hooks.example.com/a", "event": "paid"}, {"event": "paid"}]),
      ],
      final="""Added `deliver-webhook`:

```yaml
events:
  - queue: {name: outbound-hooks, batch_size: 5, max_receive: 8, dead_letter: outbound-hooks-dlq}
```

- `pskit validate` (onprem, prod): valid.
- Local invoke with 2 messages: the one without `url` is the only entry in `batchItemFailures`.

The host retries only that message id, and moves it to `outbound-hooks-dlq` after 8 receives [docs/handlers.md#batchresult]. That is the right choice for a permanent problem. When you add the real HTTP call, either `fail(record)` on a timeout too, or raise. An exception makes the host retry the whole batch, because non-HTTP errors are re-raised [docs/handlers.md#errors].

Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 185
    B(185, stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: media-index
provider:
  name: onprem
  region: local
  options:
    port: 8185
functions: {}
""",
          "requirements.txt": ""}),
      user="keep a index of videos in bucket media under videos/. new file -> add, file deleted -> remove. one function for both",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/index.py`: add on record.action created, remove on deleted",
                                   "Add `index-videos` with storage {bucket: media, prefix: videos/, events: [created, deleted]}",
                                   "Validate, invoke a created and a deleted event"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/index.py", content=FUTURE + """
INDEX = set()


def index_videos(event, ctx):
    for record in event.records:
        if record.action == "deleted":
            INDEX.discard(record.key)
        else:
            INDEX.add(record.key)
        ctx.logger.info("index", extra={"key": record.key, "action": record.action})
    return {"videos": sorted(INDEX)}
"""),
          S("set_config", path="functions.index-videos",
            value={"handler": "app.index.index_videos",
                   "events": [{"storage": {"bucket": "media", "prefix": "videos/", "events": ["created", "deleted"]}}]}),
          S("invoke_local", function="index-videos", type="storage",
            data={"bucket": "media", "key": "videos/launch.mp4", "size": 52428800, "action": "created"}),
          S("invoke_local", function="index-videos", type="storage",
            data={"bucket": "media", "key": "videos/launch.mp4", "size": 0, "action": "deleted"}),
      ],
      final="""Done. `index-videos` gets both kinds of event, and `record.action` tells which one:

```yaml
- storage: {bucket: media, prefix: videos/, events: [created, deleted]}
```

- validate (onprem): valid.
- created event: `{"videos": ["videos/launch.mp4"]}`.
- deleted event (a separate run): `{"videos": []}`.

The index is in memory, so it starts empty after a restart. Keep it in a database or a file for real use. On premises the bucket is the folder `media` under the data directory [docs/events.md#storage]. Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 186
    B(186, stage="staging", mode="auto", page="Overview", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: events-hub
provider:
  name: onprem
  region: local
  options:
    port: 8186
functions: {}
""",
          "requirements.txt": ""}),
      user="topics as dirs under /srv/pskit/topics. subscriber `audit` on topic `domain-events`, logs each message",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.services.topic: {use: directory, path: /srv/pskit/topics}",
                                   "Write `app/audit.py`; add `audit` on topic domain-events", "Validate, invoke"]),
          S("set_config", path="provider.options.services", value={"topic": {"use": "directory", "path": "/srv/pskit/topics"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/audit.py", content=FUTURE + """

def audit(event, ctx):
    for record in event.records:
        ctx.logger.info("domain event", extra={"body": record.json(default=record.text()),
                                               "attributes": record.attributes})
    return {"audited": len(event.records)}
"""),
          S("set_config", path="functions.audit", value={"handler": "app.audit.audit", "events": [{"topic": "domain-events"}]}),
          S("invoke_local", function="audit", type="topic", data=[{"type": "order.created", "id": 9}]),
      ],
      final="""Done:

```yaml
provider:
  options:
    services:
      topic: {use: directory, path: /srv/pskit/topics}
functions:
  audit:
    handler: app.audit.audit
    events:
      - topic: domain-events
```

Topics support only `builtin` and `directory` on premises [docs/providers.md#onprem-on-premises]. The host's user needs write access to `/srv/pskit/topics` on the target.

- validate (onprem, staging): valid.
- invoke: `{"audited": 1}`.

Deploy: `pskit deploy -s staging`. Publish: `POST /__pskit/topics/domain-events`."""),

    # ------------------------------------------------------------------ 187
    B(187, stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": """service: expense-mail
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8187
resources:
  receipts-mail:
    type: smtp
    external: true
    connection: {host: 203.0.113.60, port: 25, domains: receipts.example.com, hostname: mail.receipts.example.com}
functions: {}
""",
          "requirements.txt": ""}),
      user="Employees mail receipts to receipts.example.com. A function `collect-receipts` on that SMTP server should decode each attachment, keep only PDFs and images, and return sender + a list of {filename, content_type, bytes} where bytes is the real decoded size.",
      steps=[
          S("get_project"),
          S("search_docs", query="smtp attachments base64 content filename content_type",
            docs=[D("docs/smtp/README.md", "what-the-handler-receives", start="| `attachments` |", end="`content` is base64 |")]),
          S("propose_plan", steps=["Write `app/receipts.py`: base64-decode attachment content, keep application/pdf and image/*",
                                   "Add `collect-receipts` with `- smtp: {resource: receipts-mail}`",
                                   "Validate (onprem, prod) and run a test mail with a PDF and a .txt attachment"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/receipts.py", content=FUTURE + """import base64


def _wanted(content_type):
    return content_type == "application/pdf" or content_type.startswith("image/")


def collect(event, ctx):
    mail = event.data or {}
    kept = []
    for att in mail.get("attachments") or []:
        ctype = (att.get("content_type") or "").lower()
        if not _wanted(ctype):
            continue
        data = base64.b64decode(att.get("content") or "")
        kept.append({"filename": att.get("filename"), "content_type": ctype, "bytes": len(data)})
    ctx.logger.info("receipts", extra={"from": mail.get("from"), "count": len(kept)})
    return {"sender": mail.get("from"), "receipts": kept}
"""),
          S("set_config", path="functions.collect-receipts",
            value={"handler": "app.receipts.collect", "events": [{"smtp": {"resource": "receipts-mail"}}]}),
          S("invoke_local", function="collect-receipts", type="smtp",
            data={"from": "jo@example.com", "to": ["in@receipts.example.com"], "subject": "Taxi",
                  "text": "see attached",
                  "attachments": [{"filename": "taxi.pdf", "content_type": "application/pdf", "content": "JVBERi0xLjQK"},
                                  {"filename": "notes.txt", "content_type": "text/plain", "content": "aGk="}]}),
      ],
      final="""Added `collect-receipts` on `receipts-mail`. Attachment `content` is base64 [docs/smtp/README.md#what-the-handler-receives], so the handler decodes it to get the real size, and keeps only `application/pdf` and `image/*`.

- `pskit validate` (onprem, prod): valid.
- Test mail with `taxi.pdf` and `notes.txt`: `{"sender": "jo@example.com", "receipts": [{"filename": "taxi.pdf", "content_type": "application/pdf", "bytes": 12}]}`. The `.txt` was dropped, and 12 is the decoded size of the test content.

Deploy so the host knows the trigger: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. Then mail a receipt, or use **Test**. Store the decoded bytes (for example in a bucket) when you're ready. Tell me where."""),

    # ------------------------------------------------------------------ 188
    B(188, stage="staging", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#retry-and-catch"],
      project=dict(files={
          "pskit.yml": """service: sync-crm
provider:
  name: onprem
  region: local
  options:
    port: 8188
functions:
  push-crm:
    handler: app.crm.push
  queue-for-later:
    handler: app.crm.later
""",
          "app/__init__.py": "",
          "app/crm.py": FUTURE + """

def push(event, ctx):
    return {**(event.data or {}), "pushed": True}


def later(event, ctx):
    return {**(event.data or {}), "deferred": True}
""",
          "requirements.txt": ""}),
      user="wf `crm-sync`: push-crm, retry ConnectionError+TimeoutError 5x, 2s, backoff 2, cap 30s. still failing -> queue-for-later",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Workflow `crm-sync`: Push (push-crm; retry [ConnectionError, TimeoutError] max 5, 2 s, x2, max_delay 30; catch * -> Later) ; Later (queue-for-later, end)",
                                   "Validate, invoke push-crm"]),
          S("set_config", path="workflows.crm-sync",
            value={"start_at": "Push",
                   "states": {"Push": {"type": "task", "function": "push-crm", "end": True,
                                       "retry": [{"errors": ["ConnectionError", "TimeoutError"], "max_attempts": 5,
                                                  "interval_seconds": 2, "backoff_rate": 2, "max_delay_seconds": 30}],
                                       "catch": [{"errors": ["*"], "next": "Later"}]},
                              "Later": {"type": "task", "function": "queue-for-later", "end": True}}}),
          S("invoke_local", function="push-crm", type="workflow", data={"contact": "c-9"}),
      ],
      final="""Added:

```yaml
workflows:
  crm-sync:
    start_at: Push
    states:
      Push:
        type: task
        function: push-crm
        end: true
        retry:
          - {errors: [ConnectionError, TimeoutError], max_attempts: 5, interval_seconds: 2, backoff_rate: 2, max_delay_seconds: 30}
        catch:
          - {errors: ["*"], next: Later}
      Later: {type: task, function: queue-for-later, end: true}
```

Waits are 2, 4, 8, 16 s (capped at 30). When the retries are used up, or on any other error, the catcher moves to `Later`, with the error stored under `$.error` by default [docs/workflows.md#retry-and-catch].

- validate (onprem, staging): valid (embedded engine).
- `push-crm`: `{"contact": "c-9", "pushed": true}`.

Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 189
    B(189, stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#data-flow"],
      project=dict(files={
          "pskit.yml": """service: loans
provider:
  name: onprem
  region: local
  options:
    port: 8189
functions:
  check-customer:
    handler: app.loans.check_customer
  approve-loan:
    handler: app.loans.approve
""",
          "app/__init__.py": "",
          "app/loans.py": FUTURE + """

def check_customer(event, ctx):
    customer = dict(event.data or {})
    return {"customer_id": customer.get("id"), "ok": customer.get("age", 0) >= 18}


def approve(event, ctx):
    data = dict(event.data or {})
    return {"loan": data.get("loan"), "approved": bool((data.get("customer_check") or {}).get("ok"))}
""",
          "requirements.txt": ""}),
      user="Input is {customer: {...}, loan: {...}}. check-customer must only see the customer object, and its answer must be stored under $.customer_check without losing the loan. Then approve-loan gets everything.",
      steps=[
          S("get_project"),
          S("search_docs", query="input_path result_path task",
            docs=[D("docs/workflows.md", "data-flow")]),
          S("propose_plan", steps=["Workflow `loan-flow`: Check (check-customer, input_path $.customer, result_path $.customer_check) -> Approve (approve-loan, end)",
                                   "Validate for onprem and invoke check-customer with only a customer"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.loan-flow",
            value={"start_at": "Check",
                   "states": {"Check": {"type": "task", "function": "check-customer", "input_path": "$.customer",
                                        "result_path": "$.customer_check", "next": "Approve"},
                              "Approve": {"type": "task", "function": "approve-loan", "end": True}}}),
          S("invoke_local", function="check-customer", type="workflow", data={"id": "cu-4", "age": 34}),
      ],
      final="""Added `loan-flow`:

```yaml
workflows:
  loan-flow:
    start_at: Check
    states:
      Check:
        type: task
        function: check-customer
        input_path: $.customer
        result_path: $.customer_check
        next: Approve
      Approve: {type: task, function: approve-loan, end: true}
```

`input_path` hands only `customer` to the task, and `result_path` puts the answer under `customer_check` while keeping `customer` and `loan` [docs/workflows.md#data-flow].

- `pskit validate` (onprem): valid (embedded engine).
- `check-customer` with just a customer: `{"customer_id": "cu-4", "ok": true}`.

End to end: `pskit workflow run loan-flow -i '{"customer": {"id": "cu-4", "age": 34}, "loan": {"amount": 5000}}' --history`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 190
    B(190, stage="staging", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: trials
provider:
  name: onprem
  region: local
  options:
    port: 8190
functions:
  start-trial:
    handler: app.trials.start
  end-trial:
    handler: app.trials.end
""",
          "app/__init__.py": "",
          "app/trials.py": FUTURE + """

def start(event, ctx):
    data = dict(event.data or {})
    return {**data, "trial": "started"}


def end(event, ctx):
    return {**(event.data or {}), "trial": "ended"}
""",
          "requirements.txt": ""}),
      user="trial length is different per customer, it come in input as trial_seconds. start-trial, wait that long, then end-trial",
      steps=[
          S("get_project"),
          S("search_docs", query="wait seconds_path from input",
            docs=[D("docs/workflows.md", "state-types", start="| `wait` |", end="| sleep |")]),
          S("propose_plan", steps=["Workflow `trial`: Start (start-trial) -> Wait (wait, seconds_path $.trial_seconds) -> End (end-trial, end)",
                                   "Validate (onprem, staging), invoke start-trial"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.trial",
            value={"start_at": "Start",
                   "states": {"Start": {"type": "task", "function": "start-trial", "next": "Wait"},
                              "Wait": {"type": "wait", "seconds_path": "$.trial_seconds", "next": "End"},
                              "End": {"type": "task", "function": "end-trial", "end": True}}}),
          S("invoke_local", function="start-trial", type="workflow", data={"customer": "k-2", "trial_seconds": 1209600}),
      ],
      final="""Done. `seconds_path` reads the wait time from the data, so each customer waits their own `trial_seconds` [docs/workflows.md#state-types]:

```yaml
workflows:
  trial:
    start_at: Start
    states:
      Start: {type: task, function: start-trial, next: Wait}
      Wait:  {type: wait, seconds_path: $.trial_seconds, next: End}
      End:   {type: task, function: end-trial, end: true}
```

`start-trial` returns its input plus `trial`, so `trial_seconds` is still there for the wait.

- `pskit validate` (onprem, staging): valid.
- `start-trial` with 14 days (1209600 s): `{"customer": "k-2", "trial_seconds": 1209600, "trial": "started"}`.

On premises the wait runs in the host's engine, not inside a function, so long waits are fine. Deploy: **Deploy** page or `pskit deploy -s staging`. Watch the run on the **Workflows** page."""),

    # ------------------------------------------------------------------ 191
    B(191, stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises", "docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine"],
      project=dict(files={
          "pskit.yml": """service: pos-api
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8191
functions:
  sale:
    handler: app.pos.sale
    events:
    - http: POST /sale
""",
          "app/__init__.py": "",
          "app/pos.py": FUTURE + """

def sale(event, ctx):
    return {"ok": True}, 201
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="$ pskit resources onprem servers test app-2\n  os=Ubuntu 24.04 LTS  arch=x86_64  cpus=4  memory_mb=7940\n  docker=  docker_access=no  sudo=yes  python=  node=\n\nput prod on app-2 so it comes back after reboot",
      steps=[
          S("get_project"),
          S("search_docs", query="ssh systemd python bundle saved server",
            docs=[D("docs/providers.md", "onprem-on-premises", start="When the server has **no Python**", end="(internal mirror of an `install_only` tarball).")]),
          S("propose_plan", steps=["provider.options.deploy: {server: app-2, python: bundle, install: systemd, sudo: true}",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy",
            value={"server": "app-2", "python": "bundle", "install": "systemd", "sudo": True}),
      ],
      final="""Your test shows no Python and no Docker on app-2, but `sudo=yes`. So:

```yaml
provider:
  options:
    deploy: {server: app-2, python: bundle, install: systemd, sudo: true}
```

- `python: bundle`: a portable CPython is shipped with the app, so app-2 needs no Python [docs/providers.md#onprem-on-premises].
- `install: systemd` + `sudo: true`: a systemd unit, so the host starts again after a reboot. Your passwordless sudo covers writing `/etc/systemd/system`.
- `server: app-2`: host, user and login come from the saved server [docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine].

validate (onprem, prod): valid.

Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. The first apply downloads the Python bundle, so this machine needs internet. Open port 8191 on app-2 for the POS clients."""),

    # ------------------------------------------------------------------ 192
    B(192, stage="prod", mode="auto", page="Cluster", persona="terse_expert",
      sources=["docs/cluster.md", "docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": """service: renderer
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8192
functions:
  render:
    handler: app.render.render
    events:
    - http: POST /render
""",
          "app/__init__.py": "",
          "app/render.py": FUTURE + """

def render(event, ctx):
    return {"rendered": True}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="renderer -> nomad cluster `batch`, 2 web replicas, 1 cpu + 1024 MB each",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.cluster: {name: batch, replicas: 2, cpu: 1, memory: 1024}", "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.cluster", value={"name": "batch", "replicas": 2, "cpu": 1, "memory": 1024}),
      ],
      final="""Set `cluster: {name: batch, replicas: 2, cpu: 1, memory: 1024}`, so 2 web replicas plus the main replica, each reserving 1 core and 1024 MB [docs/cluster.md#set-up].

validate (onprem, prod): valid.

`batch` is Nomad. There is no load balancing: the main replica answers on the master's 8192, and each web replica on its own server's 8192 [docs/cluster.md]. For one URL, add a load balancer (`pskit cluster balancer set batch SERVER`). Deploy: `pskit deploy -s prod` (Docker needed here to build the image)."""),

    # ------------------------------------------------------------------ 193
    B(193, stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#fields", "docs/resource-guides/onprem/database.md#3-declare-it-in-pskityml"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: onprem
  region: local
  options:
    port: 8193
functions:
  search:
    handler: app.catalog.search
    events:
    - http: GET /search
  update-price:
    handler: app.catalog.update_price
    events:
    - http: PUT /prices/{sku}
""",
          "app/__init__.py": "",
          "app/catalog.py": FUTURE + """

def search(event, ctx):
    return []


def update_price(event, ctx):
    return {"updated": True}
""",
          "requirements.txt": ""}),
      user="We have MySQL with a primary (db-1.example.com) and a read replica (db-2.example.com), both port 3306, database `catalog`, user `catalog_app`, same password in CATALOG_DB_PASSWORD. Reads (search) must use the replica only, writes (update-price) the primary only. Both handlers should report which host they got.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add resources.catalog-primary (database, external, db-1, functions [update-price]) and catalog-replica (database, external, db-2, functions [search]), both with password_env CATALOG_DB_PASSWORD",
                                   "Handlers read resource(\"catalog-replica\") / resource(\"catalog-primary\") and return the host",
                                   "Validate (onprem, staging) and call both locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.catalog-primary",
            value={"type": "database", "external": True,
                   "connection": {"host": "db-1.example.com", "port": 3306, "database": "catalog",
                                  "user": "catalog_app", "password_env": "CATALOG_DB_PASSWORD"},
                   "functions": ["update-price"]}),
          S("set_config", path="resources.catalog-replica",
            value={"type": "database", "external": True,
                   "connection": {"host": "db-2.example.com", "port": 3306, "database": "catalog",
                                  "user": "catalog_app", "password_env": "CATALOG_DB_PASSWORD"},
                   "functions": ["search"]}),
          S("write_file", path="app/catalog.py", content=FUTURE + """from py_serverless_kit import resource


def search(event, ctx):
    db = resource("catalog-replica")
    return {"db_host": db["host"], "results": []}


def update_price(event, ctx):
    db = resource("catalog-primary")
    return {"db_host": db["host"], "sku": event.http.path_params.get("sku"), "updated": True}
"""),
          S("validate"),
          S("invoke_local", function="search", method="GET", path="/search?q=tea"),
          S("invoke_local", function="update-price", method="PUT", path="/prices/TEA-1", data={"price": 4.2}),
      ],
      final="""Two database resources, each bound to one function:

```yaml
resources:
  catalog-primary:
    type: database
    external: true
    connection: {host: db-1.example.com, port: 3306, database: catalog, user: catalog_app, password_env: CATALOG_DB_PASSWORD}
    functions: [update-price]
  catalog-replica:
    type: database
    external: true
    connection: {host: db-2.example.com, port: 3306, database: catalog, user: catalog_app, password_env: CATALOG_DB_PASSWORD}
    functions: [search]
```

Because of `functions:`, `search` cannot even see the primary, and `update-price` cannot see the replica [docs/resources.md#fields].

- `pskit validate` (onprem, staging): valid.
- `GET /search?q=tea`: `"db_host": "db-2.example.com"`.
- `PUT /prices/TEA-1`: `"db_host": "db-1.example.com"`, `"sku": "TEA-1"`.

Add `pymysql` to requirements.txt when you connect [docs/resource-guides/onprem/database.md#3-declare-it-in-pskityml]. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 194
    B(194, stage="prod", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#queue-drivers", "docs/resources.md#examples"],
      project=dict(files={
          "pskit.yml": """service: dc-worker
provider:
  name: onprem
  region: local
  options:
    port: 8194
functions: {}
""",
          "requirements.txt": ""}),
      user="We're moving the consumer of our SQS queue https://sqs.eu-west-1.amazonaws.com/123456789012/orders out of Lambda into our data centre, but the queue stays in AWS. Same batch size 10, long polling 10 s. The IAM user keys are DC_SQS_KEY_ID and DC_SQS_SECRET on the host.",
      steps=[
          S("get_project"),
          S("search_docs", query="sqs driver queue_url wait_seconds access_key_env",
            docs=[D("docs/resources.md", "examples", end="wait_seconds: 10")]),
          S("propose_plan", steps=["Add resources.orders: queue, external, options {driver: sqs, queue_url, wait_seconds: 10, access_key_env: DC_SQS_KEY_ID, secret_key_env: DC_SQS_SECRET}",
                                   "Write `app/orders.py`; add `process-orders` with queue {resource: orders, batch_size: 10}",
                                   "Validate (onprem, prod) and invoke with two orders"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.orders",
            value={"type": "queue", "external": True,
                   "options": {"driver": "sqs", "queue_url": "https://sqs.eu-west-1.amazonaws.com/123456789012/orders",
                               "wait_seconds": 10, "access_key_env": "DC_SQS_KEY_ID", "secret_key_env": "DC_SQS_SECRET"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/orders.py", content=FUTURE + """from py_serverless_kit import BatchResult


def process(event, ctx):
    result = BatchResult()
    for record in event.records:
        order = record.json(default=None)
        if not isinstance(order, dict) or "order_id" not in order:
            result.fail(record)
            continue
        ctx.logger.info("order", extra={"order_id": order["order_id"]})
    return result
"""),
          S("set_config", path="functions.process-orders",
            value={"handler": "app.orders.process", "events": [{"queue": {"resource": "orders", "batch_size": 10}}]}),
          S("invoke_local", function="process-orders", type="queue", data=[{"order_id": 1}, {"order_id": 2}]),
      ],
      final="""The queue stays in AWS, and the on-prem host polls it with the `sqs` driver:

```yaml
resources:
  orders:
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/orders
      wait_seconds: 10
      access_key_env: DC_SQS_KEY_ID
      secret_key_env: DC_SQS_SECRET
functions:
  process-orders:
    handler: app.orders.process
    events:
      - queue: {resource: orders, batch_size: 10}
```

The SQS visibility timeout is set to the event's `visibility_timeout`, failed messages become visible again at once, and `receives` comes from `ApproximateReceiveCount` [docs/resources.md#queue-drivers]. The code returns a `BatchResult` like your Lambda's `batchItemFailures`.

- `pskit validate` (onprem, prod): valid.
- Local invoke with 2 orders: no failures.

Disable the Lambda's event source mapping first, so only one consumer reads the queue. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 195
    B(195, stage="dev", mode="auto", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#storage-drivers", "docs/resources.md#examples"],
      project=dict(files={
          "pskit.yml": """service: scan-sync
provider:
  name: onprem
  region: local
  options:
    port: 8195
functions: {}
""",
          "requirements.txt": ""}),
      user="azure blob container `scans` (prefix incoming/) must trigger function on our local server when new file. connection string is AZ_SCANS_CONN on host",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add resources.scans: storage, external, options {driver: azure_blob, container: scans, prefix: incoming/, connection_string_env: AZ_SCANS_CONN}",
                                   "Write `app/scans.py`; add `on-scan` with storage {resource: scans, events: [created]}", "Validate, invoke"]),
          S("set_config", path="resources.scans",
            value={"type": "storage", "external": True,
                   "options": {"driver": "azure_blob", "container": "scans", "prefix": "incoming/",
                               "connection_string_env": "AZ_SCANS_CONN"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/scans.py", content=FUTURE + """

def on_scan(event, ctx):
    keys = [r.key for r in event.records]
    ctx.logger.info("new scans", extra={"keys": keys})
    return {"scans": keys}
"""),
          S("set_config", path="functions.on-scan",
            value={"handler": "app.scans.on_scan", "events": [{"storage": {"resource": "scans", "events": ["created"]}}]}),
          S("invoke_local", function="on-scan", type="storage",
            data={"bucket": "scans", "key": "contract-17.pdf", "size": 120400, "action": "created"}),
      ],
      final="""Done. Your local host watches the Azure container:

```yaml
resources:
  scans:
    type: storage
    external: true
    options: {driver: azure_blob, container: scans, prefix: incoming/, connection_string_env: AZ_SCANS_CONN}
functions:
  on-scan:
    handler: app.scans.on_scan
    events:
      - storage: {resource: scans, events: [created]}
```

The host lists the container every `poll_seconds`, and a new or changed blob gives `created`. Blobs already there at the first start are not sent. `prefix` is stripped from `record.key` [docs/resources.md#storage-drivers]. The connection string is read from `AZ_SCANS_CONN` on the host, never from pskit.yml.

- validate (onprem): valid.
- invoke: `{"scans": ["contract-17.pdf"]}`.

Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 196
    B(196, stage="staging", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={
          "pskit.yml": """service: telemetry-dc
provider:
  name: onprem
  region: local
  options:
    port: 8196
functions: {}
""",
          "requirements.txt": ""}),
      user="consume pubsub sub projects/acme-iot/subscriptions/dc-telemetry on-prem, token via gcloud, fn `store-telemetry` batch 50",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add resources.telemetry: queue, external, options {driver: pubsub, subscription: projects/acme-iot/subscriptions/dc-telemetry, token_command: [\"gcloud\", \"auth\", \"print-access-token\"]}",
                                   "Write `app/telemetry.py`; add `store-telemetry` with queue {resource: telemetry, batch_size: 50}", "Validate, invoke"]),
          S("set_config", path="resources.telemetry",
            value={"type": "queue", "external": True,
                   "options": {"driver": "pubsub", "subscription": "projects/acme-iot/subscriptions/dc-telemetry",
                               "token_command": ["gcloud", "auth", "print-access-token"]}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/telemetry.py", content=FUTURE + """

def store(event, ctx):
    points = [r.json(default={}) for r in event.records]
    ctx.logger.info("telemetry batch", extra={"points": len(points)})
    return {"stored": len(points)}
"""),
          S("set_config", path="functions.store-telemetry",
            value={"handler": "app.telemetry.store", "events": [{"queue": {"resource": "telemetry", "batch_size": 50}}]}),
          S("invoke_local", function="store-telemetry", type="queue", data=[{"device": "t1", "v": 3.3}, {"device": "t2", "v": 3.1}]),
      ],
      final="""Done:

```yaml
resources:
  telemetry:
    type: queue
    external: true
    options:
      driver: pubsub
      subscription: projects/acme-iot/subscriptions/dc-telemetry
      token_command: ["gcloud", "auth", "print-access-token"]
functions:
  store-telemetry:
    handler: app.telemetry.store
    events:
      - queue: {resource: telemetry, batch_size: 50}
```

The token is cached for 45 min. The ack deadline follows the event's `visibility_timeout`. Without a dead-letter policy, Pub/Sub doesn't report attempts, so the host counts them itself (reset on restart) [docs/resources.md#queue-drivers].

- validate (onprem, staging): valid.
- invoke with 2 points: `{"stored": 2}`.

`gcloud` must be installed and logged in on the host. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 197
    B(197, stage="staging", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/configuration.md#precedence-later-wins"],
      project=dict(files={
          "pskit.yml": """service: payments
provider:
  name: onprem
  region: local
  options:
    port: 8197
functions:
  charge:
    handler: app.pay.charge
    environment:
      PSP_URL: https://sandbox.psp.example.com
    events:
    - http: POST /charge
""",
          "app/__init__.py": "",
          "app/pay.py": FUTURE + """

def charge(event, ctx):
    return {"psp": ctx.env.get("PSP_URL")}
""",
          "requirements.txt": ""}),
      user="dev and staging must keep the sandbox PSP, but prod must use https://api.psp.example.com. Same pskit.yml, no if/else in code. Show me it works for staging.",
      steps=[
          S("get_project"),
          S("search_docs", query="stages override function environment",
            docs=[D("docs/configuration.md", "stages-per-stage-overrides")]),
          S("propose_plan", steps=["Add stages.prod.functions.charge.environment.PSP_URL: https://api.psp.example.com",
                                   "Validate (onprem, staging) and call POST /charge to see the staging URL"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages",
            value={"prod": {"functions": {"charge": {"environment": {"PSP_URL": "https://api.psp.example.com"}}}}}),
          S("invoke_local", function="charge", method="POST", path="/charge", data={"amount": 10}),
      ],
      final="""Added a prod-only override:

```yaml
stages:
  prod:
    functions:
      charge:
        environment:
          PSP_URL: https://api.psp.example.com
```

`stages.<stage>` is merged over the rest when you run with that stage, so dev and staging keep the sandbox URL and prod gets the real one [docs/configuration.md#precedence-later-wins]. The code just reads `ctx.env["PSP_URL"]`.

- `pskit validate` (onprem, staging): valid.
- Local `POST /charge` as staging: `{"psp": "https://sandbox.psp.example.com"}`.

Check prod without deploying: `pskit invoke -f charge -s prod --method POST --path /charge -d '{"amount": 10}'` should show the api URL. Deploy staging: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 198
    B(198, stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: quota
provider:
  name: onprem
  region: local
  options:
    port: 8198
functions:
  check-quota:
    handler: app.quota.check
    events:
    - http: GET /quota
""",
          "app/__init__.py": "",
          "app/quota.py": FUTURE + """

def check(event, ctx):
    return {"max_items": None}
""",
          "requirements.txt": ""}),
      user="our ops team keeps limits in a json file and doesn't want to touch pskit.yml. can check-quota get max_items from a file called limits.json?",
      steps=[
          S("get_project"),
          S("search_docs", query="file variable json config",
            docs=[D("docs/configuration.md", "variables", start="| `${file(path.json)}` |", end="Variables can nest across passes; unresolved variables are reported together.")]),
          S("propose_plan", steps=["Create `limits.json` with {\"max_items\": 500}",
                                   "Add custom.limits: ${file(limits.json)} and functions.check-quota.environment.MAX_ITEMS: ${self:custom.limits.max_items}",
                                   "Return MAX_ITEMS from the handler, validate and call /quota"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="limits.json", content='{"max_items": 500}\n'),
          S("set_config", path="custom", value={"limits": "${file(limits.json)}"}),
          S("set_config", path="functions.check-quota.environment", value={"MAX_ITEMS": "${self:custom.limits.max_items}"}),
          S("write_file", path="app/quota.py", content=FUTURE + """

def check(event, ctx):
    return {"max_items": int(ctx.env.get("MAX_ITEMS", "0"))}
"""),
          S("validate"),
          S("invoke_local", function="check-quota", method="GET", path="/quota"),
      ],
      final="""Yes. pskit can read a JSON file into the config with `${file(...)}`:

```yaml
custom:
  limits: ${file(limits.json)}
functions:
  check-quota:
    environment:
      MAX_ITEMS: ${self:custom.limits.max_items}
```

`limits.json` (next to pskit.yml) now has `{"max_items": 500}`. `${file(limits.json)}` parses it, and `${self:custom.limits.max_items}` picks the value [docs/configuration.md#variables].

- `pskit validate` (onprem): valid.
- Local call `/quota`: 200, `{"max_items": 500}`.

Your ops team only edits `limits.json`. The value is read when you run or deploy, so redeploy after a change: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 199
    B(199, stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/events.md#storage", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: csv-import
provider:
  name: onprem
functions: {}
""",
          "requirements.txt": ""}),
      user="new project. people drop csv files in a folder (bucket imports). each new csv: log it and remember last 20 names. and a GET /imports to see them. local machine",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider: region local, options host 127.0.0.1, port 8199",
                                   "Write `app/imports.py` with `on_csv` (storage) and `recent` (http) sharing a 20-item list",
                                   "Add `on-csv` with storage {bucket: imports, suffix: .csv, events: [created]} and `recent-imports` on GET /imports",
                                   "Validate for onprem, invoke on-csv"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.region", value="local"),
          S("set_config", path="provider.options", value={"host": "127.0.0.1", "port": 8199}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/imports.py", content=FUTURE + """from collections import deque

RECENT = deque(maxlen=20)


def on_csv(event, ctx):
    for record in event.records:
        RECENT.appendleft({"file": record.key, "size": record.size})
        ctx.logger.info("csv dropped", extra={"file": record.key})
    return {"recent": len(RECENT)}


def recent(event, ctx):
    return {"imports": list(RECENT)}
"""),
          S("set_config", path="functions",
            value={"on-csv": {"handler": "app.imports.on_csv",
                              "events": [{"storage": {"bucket": "imports", "suffix": ".csv", "events": ["created"]}}]},
                   "recent-imports": {"handler": "app.imports.recent", "events": [{"http": "GET /imports"}]}}),
          S("invoke_local", function="on-csv", type="storage",
            data={"bucket": "imports", "key": "customers-2026-11.csv", "size": 20480, "action": "created"}),
      ],
      final="""New project ready, running on this machine:

```yaml
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8199}
functions:
  on-csv:
    handler: app.imports.on_csv
    events:
      - storage: {bucket: imports, suffix: .csv, events: [created]}
  recent-imports:
    handler: app.imports.recent
    events:
      - http: GET /imports
```

- `pskit validate` (onprem): valid.
- `on-csv` with a test file: `{"recent": 1}`, and it logged `customers-2026-11.csv`.

On premises the bucket is a folder named `imports` inside the host's data directory (by default under `.pskit/onprem-data/csv-import-dev`) [docs/providers.md#onprem-on-premises]. Files already there at the first start are not sent. Both functions run in the same host, so `GET /imports` sees the list, but the list is lost on restart.

Start it: **Deploy** page or `pskit deploy -s dev`, then drop a `.csv` into that folder (or `PUT /__pskit/storage/imports/<name>.csv`) and open `http://127.0.0.1:8199/imports`."""),

    # ------------------------------------------------------------------ 200
    B(200, stage="prod", mode="ask", page="Setup", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: archive
provider:
  name: onprem
  region: local
  options:
    port: 8200
functions:
  store:
    handler: app.archive.store
    events:
    - queue: archive-jobs
""",
          "app/__init__.py": "",
          "app/archive.py": FUTURE + """

def store(event, ctx):
    return None
""",
          "requirements.txt": ""}),
      user="our server has a big disk at /mnt/bigdisk. the system disk is small. can all the queue files and logs go to the big disk?",
      steps=[
          S("get_project"),
          S("search_docs", query="data_dir queues buckets logs on premises",
            docs=[D("docs/providers.md", "onprem-on-premises", start="    data_dir:", end="# default .pskit/onprem-data/<service>-<stage> (local); <path>/data on SSH")]),
          S("propose_plan", steps=["provider.options.data_dir: /mnt/bigdisk/pskit/archive-prod", "Validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.data_dir", value="/mnt/bigdisk/pskit/archive-prod"),
      ],
      final="""Yes. `data_dir` is where the host keeps its data, so I set it to the big disk:

```yaml
provider:
  options:
    data_dir: /mnt/bigdisk/pskit/archive-prod
```

The built-in queues (one file per message), buckets, workflow executions and the log file (`<data_dir>/logs/host.jsonl`) all live there [docs/providers.md#onprem-on-premises].

`pskit validate` (onprem, prod): valid.

The user that runs the host must be allowed to write to `/mnt/bigdisk/pskit`. Messages already queued in the old place are not moved. Let the queue empty before you deploy, or copy the folder. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),
]
