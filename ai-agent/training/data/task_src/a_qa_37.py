"""Category A (docs Q&A and how-to), batch 37: aws / gcp / azure. Handler API details: signatures and handler
strings, event.time / to_dict / json(), repeated headers, content type, record.action, remaining time, JSON
serialisation, HTML responses, PSKIT_DEBUG, failures of non-HTTP calls on GCP, BatchResult forms and Azure
behaviour, asynchronous invoke, logger key renaming; resources API (scalar connection values, resources(),
orchestrator bindings). Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


H = "docs/handlers.md"
R = "docs/resources.md"

CONVERSATIONS = [
    A(711, provider="aws", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=[f"{H}#handler-signatures"],
      user="handler without ctx param, just def ping(event): ok?",
      steps=[S("search_docs", query="handler signature one argument",
               docs=[D(H, "handler-signatures")])],
      final="""Yes. One argument works, as do `(event, ctx)` and `async def` handlers, which are awaited [docs/handlers.md#handler-signatures]."""),

    A(712, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{H}#handler-signatures"],
      user="my function create is in app/api/orders.py. what i write in handler?",
      steps=[S("search_docs", query="handler string module function path",
               docs=[D(H, "handler-signatures", start="`handler:` in `pskit.yml`")])],
      final="""Write the module path with dots, then the function: `app.api.orders.create` (or `app.api.orders:create`). It is relative to `package.source` [docs/handlers.md#handler-signatures].

**In code**
```yaml
functions:
  create-order:
    handler: app.api.orders.create
```

**In studio**
1. Open **Functions** and click the function.
2. Set *Handler* to `app.api.orders.create` and click **Save**."""),

    A(713, provider="azure", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{H}#event"],
      user="event.time is local time of azure region or utc?",
      steps=[S("search_docs", query="event time utc",
               docs=[D(H, "event", end="| `raw` | Any |")])],
      final="""UTC. `event.time` is a UTC `datetime`: the event time if the platform provides it, otherwise the current time [docs/handlers.md#event]."""),

    A(714, provider="aws", stage="staging", mode="ask", page="Code", persona="detailed_spec",
      sources=[f"{H}#event"],
      user="For debugging I'd like to log the incoming event in our worker, but not dump the huge raw Lambda payload. Is there a helper?",
      steps=[S("search_docs", query="event to_dict safe to log",
               docs=[D(H, "event", start="Helpers:")])],
      final="""Yes: `event.to_dict()` gives a summary that is safe to log [docs/handlers.md#event].

**In code**
```python
from __future__ import annotations


def worker(event, ctx):
    ctx.logger.info("event received", extra={"event": event.to_dict()})
    for record in event:
        ...
```
`for record in event:` iterates `event.records`. Avoid logging `event.raw`; it is the untouched native payload."""),

    A(715, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=[f"{H}#event"],
      user="Our ingest function has both an HTTP route and a queue trigger. If I call event.json() in it, what do I get in each case?",
      steps=[S("search_docs", query="event json helper http queue",
               docs=[D(H, "event", start="Helpers:")])],
      final="""`event.json()` depends on the event type [docs/handlers.md#event]:

- HTTP: the parsed request body
- queue (and topic, storage): the **first** record's body
- schedule, invoke, workflow: `event.data`

For a batch, loop over the records instead, so you don't miss any:
```python
for record in event.records:
    item = record.json()
```
On GCP this function is split into two Cloud Functions (HTTP and queue) that share the handler."""),

    A(716, provider="azure", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{H}#httprequest"],
      user="client send header X-Tag two times. event.http.headers['x-tag'] give me what?",
      steps=[S("search_docs", query="repeated headers joined",
               docs=[D(H, "httprequest", start="| `headers` |", end="| `headers` |")])],
      final="""Both values in one string, joined with `", "`, for example `"a, b"`. `headers` is case-insensitive, so `x-tag` and `X-Tag` both work [docs/handlers.md#httprequest].

```python
tags = [t.strip() for t in event.http.headers.get("x-tag", "").split(",") if t.strip()]
```"""),

    A(717, provider="aws", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=[f"{H}#httprequest"],
      user="content_type includes '; charset=utf-8'?",
      steps=[S("search_docs", query="http content_type parameters",
               docs=[D(H, "httprequest", start="| `content_type` |", end="| `content_type` |")])],
      final="""No. `event.http.content_type` is the type without parameters, e.g. `application/json` [docs/handlers.md#httprequest]. Read `event.http.headers["content-type"]` if you need the charset."""),

    A(718, provider="gcp", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=[f"{H}#record", "docs/events.md#storage"],
      user="one function for my bucket, created and deleted files. in code how i know which one happened?",
      steps=[S("search_docs", query="storage record action created deleted",
               docs=[D(H, "record")])],
      final="""Use `record.action`: it is `"created"` or `"deleted"` [docs/handlers.md#record].

**In code**
```yaml
events:
  - storage: {bucket: acme-files, events: [created, deleted]}
```
```python
from __future__ import annotations


def on_file(event, ctx):
    for record in event.records:
        if record.action == "deleted":
            ctx.logger.info("removed", extra={"key": record.key})
        else:
            ctx.logger.info("added", extra={"key": record.key, "size": record.size})
```
On GCP, `deleted` events get a second Cloud Function behind the scenes; the handler stays the same."""),

    A(719, provider="azure", stage="prod", mode="ask", page="Code", persona="pasted_error",
      sources=[f"{H}#context"],
      user="TypeError: '<' not supported between instances of 'NoneType' and 'int'\n\nline: if ctx.remaining_time_ms() < 5000: ... works on aws, crashes here",
      steps=[S("search_docs", query="remaining_time_ms none",
               docs=[D(H, "context")])],
      final="""`ctx.remaining_time_ms()` returns the ms until timeout, or `None` when the platform doesn't report it [docs/handlers.md#context]. Guard for `None`:

```python
left = ctx.remaining_time_ms()
if left is not None and left < 5000:
    ...
```
If you need a deadline everywhere, keep your own from the start time and the function's `timeout`."""),

    A(720, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=[f"{H}#returning-a-response"],
      user="DynamoDB returns Decimal values and we add a datetime. In Lambda we had a custom JSON encoder. Can I just return the dict from a pskit handler?",
      steps=[S("search_docs", query="json serialisation decimal datetime return",
               docs=[D(H, "returning-a-response", end="JSON serialisation handles")])],
      final="""Yes. Return the dict; pskit's JSON serialisation handles `datetime`/`date` (ISO 8601), `Decimal`, `UUID`, `set` and anything with `model_dump()` or `to_dict()` [docs/handlers.md#returning-a-response]. You can drop the custom encoder.

```python
from __future__ import annotations


def get_order(event, ctx):
    item = table.get_item(Key={"id": event.http.path_params["id"]})["Item"]
    return item
```"""),

    A(721, provider="gcp", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{H}#returning-a-response"],
      user="code only: return a small html page from GET /",
      steps=[S("search_docs", query="return html response",
               docs=[D(H, "returning-a-response", start="Response.json({\"id\": 1}", end="Response.no_content()")])],
      final="""**In code**
```yaml
functions:
  home:
    handler: app.web.home
    events:
      - http: GET /
```
```python
from __future__ import annotations

from py_serverless_kit import Response


def home(event, ctx):
    return Response.html("<h1>Hi</h1>")
```
[docs/handlers.md#returning-a-response]"""),

    A(722, provider="azure", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=[f"{H}#errors"],
      user="my function answer {\"error\": \"Internal Server Error\", \"status\": 500} and nothing else. how i see the real error?",
      steps=[S("search_docs", query="internal server error details debug",
               docs=[D(H, "errors", start="Any other exception in an HTTP handler")])],
      final="""Any unexpected exception becomes that 500 response, and the traceback goes to the logs [docs/handlers.md#errors].

1. Read the logs:
```bash
pskit logs --function api --level ERROR
```
2. Or, in dev only, set `PSKIT_DEBUG=1` to include the exception text in the body:
```yaml
stages:
  dev:
    provider:
      environment:
        PSKIT_DEBUG: "1"
```
Never set it in production. For errors you expect, raise `BadRequest`, `NotFound`, ... instead."""),

    A(723, provider="gcp", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=[f"{H}#errors", "docs/events.md#schedule-invoke-envelope"],
      user="On GCP, what happens when our scheduled function raises an exception? Does Cloud Scheduler see a failure?",
      steps=[S("search_docs", query="gcp schedule invoke failure 500 errorType",
               docs=[D(H, "errors", start="For **non-HTTP** events")])],
      final="""Yes. On GCP every call arrives over HTTP, so a failing schedule, workflow or invoke call returns `500 {"errorType": "<ExceptionClass>", "cause": "<message>"}` [docs/handlers.md#errors]. The caller sees an error response.

The traceback is in the logs:
```bash
pskit logs -s prod --function nightly --level ERROR
```
Workflow `retry` / `catch` rules match on that `errorType` class name."""),

    A(724, provider="aws", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=[f"{H}#batchresult"],
      user="BatchResult: can i fail by id or build it from a list?",
      steps=[S("search_docs", query="BatchResult fail id of",
               docs=[D(H, "batchresult", end="| Provider | Behaviour |")])],
      final="""Both. `result.fail(record)` or `result.fail(record.id)`, and `BatchResult.of(failed_records)` builds one from a list [docs/handlers.md#batchresult]. On SQS it becomes `batchItemFailures`, so only those messages are retried."""),

    A(725, provider="azure", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=[f"{H}#batchresult"],
      user="On AWS our queue worker returns BatchResult so only bad messages come back. We're adding an Azure deployment. Does that work the same there?",
      steps=[S("search_docs", query="BatchResult providers behaviour",
               docs=[D(H, "batchresult", start="| Provider | Behaviour |")])],
      final="""No. Partial batch failures are an AWS (SQS) and on-premises feature. On Azure any failure in the result raises `BatchFailure`, so the whole delivery is retried [docs/handlers.md#batchresult].

What to do:
1. Keep returning `BatchResult`; the code stays portable.
2. Make the handler idempotent, so reprocessing records that already succeeded is harmless (redelivery is normal on every cloud).
3. On Azure a message that keeps failing ends up in the `<queue>-poison` queue."""),

    A(726, provider="aws", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=[f"{H}#invoke-calling-another-function"],
      user="After an order is created I want to call the audit function without waiting for it. Is there a fire-and-forget invoke on AWS?",
      steps=[S("search_docs", query="invoke asynchronous fire and forget",
               docs=[D(H, "invoke-calling-another-function", end="3. `aws`:")])],
      final="""Yes: `asynchronous=True` (AWS) [docs/handlers.md#invoke-calling-another-function].

**In code**
```python
from __future__ import annotations

from py_serverless_kit import invoke


def create_order(event, ctx):
    order = event.http.json()
    invoke("audit", {"order_id": order["id"]}, asynchronous=True)
    return {"created": True}
```
```yaml
provider:
  iam:
    statements:
      - actions: [lambda:InvokeFunction]
        resources: ["*"]
```
On AWS `invoke()` uses boto3, so add `boto3` to `requirements.txt` and grant `lambda:InvokeFunction`. Locally the call runs in-process and finishes before `invoke()` returns."""),

    A(727, provider="gcp", stage="dev", mode="ask", page="Logs", persona="informal_non_native",
      sources=[f"{H}#logging"],
      user="i log extra={'name': customer} and in cloud logging the field is name_ . why underscore?",
      steps=[S("search_docs", query="logger extra key renamed underscore",
               docs=[D(H, "logging", start="`extra` keys that collide")])],
      final="""`name` collides with a Python `LogRecord` attribute, so pskit renames it with a trailing underscore. That way a log call can never crash your handler [docs/handlers.md#logging]. The same happens to `message`, `msg`, `args` and others.

Use a different key:
```python
ctx.logger.info("order", extra={"customer_name": customer})
```"""),

    A(728, provider="aws", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{R}#fields"],
      user="Our external search cluster has three node hosts. Can I put a YAML list of hosts in the resource's connection?",
      steps=[S("search_docs", query="resource connection values scalars list",
               docs=[D(R, "fields", start="| `connection` |", end="| `connection` |")])],
      final="""No. `connection` values must be scalars (strings, numbers, booleans) [docs/resources.md#fields].

Use one string and split it in the handler:
```yaml
resources:
  search:
    type: custom
    external: true
    connection:
      hosts: node1.example.com,node2.example.com,node3.example.com
```
```python
hosts = resource("search")["hosts"].split(",")
```"""),

    A(729, provider="gcp", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=[f"{R}#runtime-api"],
      user="list every resource bound to the current function at runtime",
      steps=[S("search_docs", query="resources() runtime api bound",
               docs=[D(R, "runtime-api", end="pskit does not ship a portable")])],
      final="""`resources()` returns `{"jobs": Resource(...), ...}` for the current function [docs/resources.md#runtime-api].

```python
from py_serverless_kit import resources

for key, r in resources().items():
    ctx.logger.info("bound", extra={"key": key, "type": r.type, "native": r.native_name})
```
`resource("x")` raises a `KeyError` that lists the bound names when `x` isn't bound to this function."""),

    A(730, provider="aws", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{R}#fields"],
      user="Our workflow uses engine: embedded on AWS, and a step in it needs the jobs queue resource. The task functions get PSKIT_RESOURCE_JOBS_*, but the orchestrator doesn't. Why?",
      steps=[S("search_docs", query="resource functions list orchestrator binding",
               docs=[D(R, "fields", start="| `functions` |", end="| `functions` |")])],
      final="""Without a `functions:` list, every function you wrote gets the binding, but generated `<workflow>-orchestrator` functions don't. List the orchestrator explicitly if it needs it [docs/resources.md#fields].

**In code**
```yaml
resources:
  jobs:
    type: queue
    functions: [worker, api, order-pipeline-orchestrator]
```
Use your workflow's name in `<workflow>-orchestrator`. Usually the task functions are the right place to use the queue, though: the orchestrator only runs the states."""),
]
