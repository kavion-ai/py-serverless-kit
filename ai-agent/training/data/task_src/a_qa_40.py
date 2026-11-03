"""Category A (docs Q&A and how-to), batch 40: aws / gcp / azure. Event options in detail: http shorthands,
parameter names, CORS defaults and custom headers, preflights, path prefixes on GCP, JWT identity source; schedule
names, rate conversion on GCP, NCRONTAB on Azure, timezone on GCP, input on Azure; storage default events and
created buckets; invoke-only functions on GCP and Azure; managed topic names and Service Bus creation.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


EV = "docs/events.md"

CONVERSATIONS = [
    A(771, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=[f"{EV}#http"],
      user="shortest health route GET /health",
      steps=[S("search_docs", query="http shorthand method default GET",
               docs=[D(EV, "http", end="**Path templates**")])],
      final="""**In code**
```yaml
events:
  - http: /health
```
Without a method the shorthand means GET [docs/events.md#http]. `- http: GET /health` is the same."""),

    A(772, provider="gcp", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#http"],
      user="invalid path template '/users/{user-id}'; use /users/{id} or /files/{path+}",
      steps=[S("search_docs", query="path template parameter names identifiers",
               docs=[D(EV, "http", start="**Path templates**", end="Parameter names are identifiers")])],
      final="""Parameter names must be identifiers: `{user_id}` is fine, `{user-id}` is not [docs/events.md#http].

**In code**
```yaml
- http: GET /users/{user_id}
```
```python
user_id = event.http.path_params["user_id"]
```"""),

    A(773, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{EV}#http"],
      user="with cors: true which origins, methods and headers are allowed?",
      steps=[S("search_docs", query="cors defaults origins methods headers",
               docs=[D(EV, "http", start="**CORS**", end="AWS additionally configures CORS on the HTTP API.")])],
      final="""With `cors: true` you get the defaults [docs/events.md#http]:

- origins: `["*"]`
- methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
- headers: Content-Type, Authorization, X-Requested-With
- `allow_credentials: false`

The runtime answers `OPTIONS` preflights with 204 and adds the `Access-Control-*` headers, on Azure too. Use a `cors:` mapping to change any of them."""),

    A(774, provider="aws", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{EV}#http"],
      user="Our frontend sends an X-Api-Version header. With cors: true the browser blocks the request at the preflight. What do I change?",
      steps=[S("search_docs", query="cors custom header allowed headers preflight",
               docs=[D(EV, "http", start="**CORS**", end="AWS additionally configures CORS on the HTTP API.")])],
      final="""`X-Api-Version` isn't in the default allowed headers (Content-Type, Authorization, X-Requested-With) [docs/events.md#http]. List it with a `cors:` mapping; the list replaces the default, so keep the ones you still need.

**In code**
```yaml
- http:
    path: /orders
    method: POST
    cors:
      origins: ["https://app.example.com"]
      headers: [Content-Type, Authorization, X-Api-Version]
```

**In studio**
1. **Functions** → the function → its HTTP trigger → CORS.
2. Add `X-Api-Version` to the headers and click **Save**.

On AWS the HTTP API's CORS is configured from the same values, so deploy again afterwards."""),

    A(775, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=[f"{EV}#http"],
      user="gcp has no api gateway. must i write OPTIONS route for cors preflight myself?",
      steps=[S("search_docs", query="preflight options answered runtime gcp",
               docs=[D(EV, "http", start="The runtime answers `OPTIONS` preflights", end="The runtime answers `OPTIONS` preflights")])],
      final="""No. Add `cors: true` (or a `cors:` mapping) to the route; the pskit runtime answers `OPTIONS` preflights with 204 and adds the `Access-Control-*` headers on every cloud, GCP included [docs/events.md#http]."""),

    A(776, provider="gcp", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{EV}#http"],
      user="The deployed GCP URL has the function name in it, but our routes are /orders and /orders/{id}. Will path params and 405s still work on GCP?",
      steps=[S("search_docs", query="gcp routing path prefix runtime matches routes",
               docs=[D(EV, "http", start="pskit's runtime also matches routes itself", end="Two functions may not declare the same `METHOD /path`.")])],
      final="""Yes. pskit's runtime matches the routes itself, so path params and `405 Method Not Allowed` work the same on clouds without an API gateway like GCP, even when the platform adds or strips a path prefix [docs/events.md#http].

Call the URL that `pskit info` prints and append your route, for example `.../orders/7`."""),

    A(777, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{EV}#http", "docs/events.md#http"],
      user="Our clients send the JWT in an X-Auth-Token header instead of Authorization. Can the AWS JWT authorizer read it from there?",
      steps=[S("search_docs", query="jwt authorizer identity_source header",
               docs=[D(EV, "http", start="**Auth support**", end="| `jwt` |")])],
      final="""Yes. `auth: jwt` has an optional `identity_source` [docs/events.md#http]. Without it, pskit uses `$request.header.Authorization`.

**In code**
```yaml
- http:
    path: /account
    method: GET
    auth: jwt
    authorizer:
      issuer: https://auth.example.com/
      audience: [orders-api]
      identity_source: $request.header.X-Auth-Token
```
Use your real issuer and audience."""),

    A(778, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{EV}#schedule"],
      user="my report function has 2 schedules. in aws console they have ugly names. can i name them?",
      steps=[S("search_docs", query="schedule name option resource name",
               docs=[D(EV, "schedule", end="The handler gets `event.type == \"schedule\"`")])],
      final="""Yes, with `name`: it is used in the resource name [docs/events.md#schedule].

**In code**
```yaml
events:
  - schedule: {rate: 1 hour, name: hourly-report, input: {kind: short}}
  - schedule: {cron: "0 6 * * *", name: morning-report, input: {kind: full}}
```"""),

    A(779, provider="gcp", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=[f"{EV}#schedule"],
      user="rate 5 minutes on gcp ends up as what in cloud scheduler?",
      steps=[S("search_docs", query="gcp cloud scheduler rate converted cron",
               docs=[D(EV, "schedule", start="| Provider | Service | Expression |", end="| gcp |")])],
      final="""A 5-field cron: rates are converted, so `5 minutes` becomes `*/5 * * * *` [docs/events.md#schedule]. Pick rates that divide 60 minutes or 24 hours."""),

    A(780, provider="azure", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{EV}#schedule"],
      user="Azure timers use 6-field NCRONTAB. Do I have to write that format in pskit.yml?",
      steps=[S("search_docs", query="azure ncrontab schedule conversion",
               docs=[D(EV, "schedule", start="| Provider | Service | Expression |", end="| azure |")])],
      final="""No. Write the portable form (a rate or a standard 5-field cron); pskit converts it to Azure's 6-field NCRONTAB, e.g. `0 */5 * * * *` [docs/events.md#schedule].

```yaml
- schedule: "0 7 * * 1-5"
```
Azure timers on Linux Consumption always run in UTC, so `timezone` is ignored there."""),

    A(781, provider="gcp", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=[f"{EV}#schedule"],
      user="gcp scheduler use my timezone Europe/Madrid or utc?",
      steps=[S("search_docs", query="schedule timezone gcp honoured",
               docs=[D(EV, "schedule", start="A rate that can't be expressed as cron")])],
      final="""Your timezone. `timezone` is honoured on GCP (and AWS); the default is UTC [docs/events.md#schedule].

```yaml
- schedule: {cron: "0 9 * * *", timezone: Europe/Madrid}
```"""),

    A(782, provider="azure", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=[f"{EV}#schedule"],
      user="how my azure timer function gets parameters like report=weekly?",
      steps=[S("search_docs", query="schedule input event data",
               docs=[D(EV, "schedule", end="The handler gets `event.type == \"schedule\"` and `event.data == input`.")])],
      final="""Put them in the schedule's `input`; the handler gets them as `event.data` [docs/events.md#schedule].

**In code**
```yaml
- schedule: {cron: "0 6 * * 1", input: {report: weekly}}
```
```python
from __future__ import annotations


def report(event, ctx):
    kind = event.data["report"]
    ctx.logger.info("running", extra={"report": kind})
```
`pskit invoke -f report` runs it locally with that input."""),

    A(783, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=[f"{EV}#storage"],
      user="when i delete file in bucket my function not run. only new files. why",
      steps=[S("search_docs", query="storage events default created deleted",
               docs=[D(EV, "storage", end="Each record has `bucket`, `key`, `size` and `action`")])],
      final="""The default for `events` is `[created]`. Add `deleted` [docs/events.md#storage]:

**In code**
```yaml
- storage:
    bucket: uploads-bucket
    events: [created, deleted]
```
In the handler, `record.action` is `"created"` or `"deleted"`.

**In studio**
1. **Functions** → the function → its storage trigger.
2. Tick *deleted* as well, then click **Save**."""),

    A(784, provider="aws", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{EV}#storage"],
      user="if i write - storage: my-uploads, does pskit make the bucket or must it exist?",
      steps=[S("search_docs", query="storage shorthand existing bucket created",
               docs=[D(EV, "storage", end="Each record has `bucket`")]),
             S("search_docs", query="aws storage created buckets",
               docs=[D(EV, "storage", start="| aws | S3 notification |", end="| aws | S3 notification |")])],
      final="""pskit creates it: `existing` defaults to `false` [docs/events.md#storage]. Created S3 buckets block public access.

If the bucket already exists, say so:
```yaml
- storage: {bucket: my-uploads, existing: true}
```
Bucket names are global on AWS, so a managed bucket needs a unique name."""),

    A(785, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{EV}#events-triggers", f"{EV}#gcp-multi-trigger-functions-are-split-automatically"],
      user="We have a GCP function with no events at all that other functions call with invoke(). Does it still get deployed, and how?",
      steps=[S("search_docs", query="function without events invoke-only",
               docs=[D(EV, "events-triggers", start="A function with no events is *invoke-only*", end="A function with no events is *invoke-only*")]),
             S("search_docs", query="gcp http deployment no triggers",
               docs=[D(EV, "gcp-multi-trigger-functions-are-split-automatically", end="- `<name>-<kind><i>`")])],
      final="""Yes. A function with no events is *invoke-only*: workflows, `invoke()` or the provider's CLI call it [docs/events.md#events-triggers]. On GCP it is deployed as the `<name>` HTTP deployment, which exists for functions without triggers [docs/events.md#gcp-multi-trigger-functions-are-split-automatically].

`invoke("<name>", data)` on GCP then makes an authenticated HTTPS call to it."""),

    A(786, provider="azure", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=[f"{EV}#azure-one-function-app-per-service"],
      user="azure: invoke-only fn reachable how?",
      steps=[S("search_docs", query="azure invoke-only route function key",
               docs=[D(EV, "azure-one-function-app-per-service")])],
      final="""It gets a key-protected `POST /_pskit/invoke/<name>` route on the Function App [docs/events.md#azure-one-function-app-per-service]. For `invoke()` from other functions on Azure, set `PSKIT_ENDPOINT_<NAME>` to the target's URL from `pskit info`."""),

    A(787, provider="gcp", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#fields", "docs/resources.md#runtime-api"],
      user="pskit create pubsub topic for my topic resource. what name it has in gcp console? not same as my key?",
      steps=[S("search_docs", query="managed resource native name prefixed",
               docs=[D("docs/resources.md", "fields", start="| `name` |", end="| `name` |")]),
             S("search_docs", query="resource native_name runtime",
               docs=[D("docs/resources.md", "runtime-api", end="pskit does not ship a portable")])],
      final="""Not exactly the key: managed names are prefixed by the provider, like event names [docs/resources.md#fields]. For example a `jobs` resource of service `orders` on stage `dev` becomes something like `orders-dev-jobs` [docs/resources.md#runtime-api].

To be sure:
1. `pskit info` or `pskit resources list -s dev` shows the deployed names.
2. In code, use `resource("<key>").native_name` instead of hard-coding it.

Set `name:` on the resource if you need a fixed name."""),

    A(788, provider="azure", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/providers.md#azure-azure-functions", f"{EV}#topic"],
      user="we dont have service bus. if i add a topic trigger on azure, pskit make it?",
      steps=[S("search_docs", query="azure topic service bus created",
               docs=[D("docs/providers.md", "azure-azure-functions", start="| Trigger | Implementation |", end="| topic |")])],
      final="""Yes. For a managed topic pskit creates the Service Bus namespace and topic, plus one subscription per function [docs/providers.md#azure-azure-functions].

```yaml
- topic: order-events
```
`topic.filter` isn't applied on Azure, so filter in the handler. Only an `existing` topic needs `options.servicebus_namespace_id` and `options.servicebus_connection`."""),

    A(789, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{EV}#storage"],
      user="On Azure, are prefix and suffix on a blob trigger applied by Azure or by pskit, and can I use events: [deleted]?",
      steps=[S("search_docs", query="azure blob trigger filters path pattern deleted",
               docs=[D(EV, "storage", start="| Provider | Service | Filters | Notes |", end="| azure |")])],
      final="""On Azure the filters become the blob trigger's path pattern [docs/events.md#storage]. `deleted` isn't possible: Azure blob triggers fire on **created/updated** blobs only, and `events: [deleted]` is a validation error.

For deletions, consider a `schedule` function that compares the container with what you processed before."""),

    A(790, provider="gcp", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{EV}#topic"],
      user="On AWS our topic event has filter: {type: [created]}. After switching to GCP, will that still filter?",
      steps=[S("search_docs", query="topic filter gcp not applied",
               docs=[D(EV, "topic", start="| Provider | Service | `filter` |", end="| azure |")])],
      final="""No. On GCP `filter` is not applied (a warning): filter in the handler [docs/events.md#topic].

**In code**
```python
from __future__ import annotations


def notify(event, ctx):
    for record in event.records:
        if record.attributes.get("type") != "created":
            continue
        ...
```
You can leave `filter` in pskit.yml for AWS; GCP ignores it."""),
]
