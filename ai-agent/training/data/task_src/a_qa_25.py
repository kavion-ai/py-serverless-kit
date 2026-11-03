"""Category A (docs Q&A and how-to), batch 25: aws / gcp / azure. Topics and filters, existing Service Bus,
Browse account, state backends, resources bound per cloud, responses (binary, cookies, errors), vendoring,
scaffolding, variables, studio saving and YAML page, Lambda migration, pskit dev endpoints.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(471, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic"],
      user="We publish all order events to one SNS topic order-events with a message attribute type. The invoicing function should only receive messages where type is paid or refunded. How do I subscribe it with a filter?",
      steps=[S("search_docs", query="topic filter sns filter policy",
               docs=[D("docs/events.md", "topic", end="| gcp | Pub/Sub |")])],
      final="""Use a `topic` event with `filter`. On AWS it becomes the SNS subscription's filter policy, so the function only gets matching messages [docs/events.md#topic].

**In code**
```yaml
functions:
  invoicing:
    handler: app.invoicing.handle
    events:
      - topic:
          name: order-events
          filter: {type: [paid, refunded]}
```
If the topic already exists outside this service, add `existing: true`.

**In studio**
1. Open **Functions** and click `invoicing`.
2. Under *Add a trigger*, pick **Topic** and choose `order-events`.
3. Set the filter to `{"type": ["paid", "refunded"]}` and click **Save**.

**In the terminal**
```bash
pskit validate
pskit trigger -f invoicing -e 0 -d '{"message": {"id": 1}, "attributes": {"type": "paid"}}'
```
The `trigger` line sends a real SNS message after you deploy."""),

    A(472, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#topic", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      user="topic filter work on gcp pub/sub? i want only type=paid messages to my function",
      steps=[S("search_docs", query="topic filter gcp pubsub",
               docs=[D("docs/events.md", "topic", start="| Provider | Service | `filter` |", end="| gcp | Pub/Sub |")])],
      final="""No. On GCP pskit doesn't apply `filter` to the Pub/Sub trigger; filter in the handler instead [docs/events.md#topic]. pskit prints a warning about it when it renders the Terraform (package/deploy).

**In code**
```python
from __future__ import annotations


def handle(event, ctx):
    for record in event.records:
        if record.attributes.get("type") != "paid":
            continue
        process(record.json())
```
Replace `process` with your own code. Remove `filter` from the GCP event (or put it only under `providers.aws`) if you don't want the warning."""),

    A(473, provider="azure", stage="staging", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/events.md#topic", "docs/providers.md#azure-azure-functions"],
      user="ERROR: [functions.billing] existing topics need options.servicebus_namespace_id and options.servicebus_connection (name of an app setting)\n\nthe topic is in our shared service bus, not created by pskit",
      steps=[S("search_docs", query="azure existing topic servicebus namespace connection",
               docs=[D("docs/providers.md", "azure-azure-functions", start="provider:", end="One **Linux Consumption Function App**")])],
      final="""For an `existing: true` topic on Azure, pskit must know which Service Bus namespace holds it and which app setting has the connection string [docs/providers.md#azure-azure-functions].

**In code**
```yaml
provider:
  name: azure
  options:
    servicebus_namespace_id: /subscriptions/<subscription id>/resourceGroups/rg-shared/providers/Microsoft.ServiceBus/namespaces/shared-bus
    servicebus_connection: SB_CONNECTION
  environment:
    SB_CONNECTION: ${env:SB_CONNECTION}
functions:
  billing:
    handler: app.billing.handle
    events:
      - topic: {name: billing-events, existing: true}
```
`servicebus_connection` is the *name* of the app setting, and `SB_CONNECTION` comes from your environment at deploy time, so the connection string isn't written in the file.

**In studio**
1. Open **Overview & provider**, fill in the provider options *servicebus_namespace_id* and *servicebus_connection*.
2. Add `SB_CONNECTION` under *Environment variables* as `${env:SB_CONNECTION}` and click **Save**.

**In the terminal**
```bash
export SB_CONNECTION='<connection string>'
pskit validate -s staging
```"""),

    A(474, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/studio.md#browse-account"],
      user="in the studio how can i pick my existing sqs queue from a list instead of typing the name? just the clicks",
      steps=[S("search_docs", query="studio browse account existing queues aws",
               docs=[D("docs/studio.md", "browse-account", end="| Azure |")])],
      final="""**In studio**
1. Open **Functions** and click your function (or **+ Create function** and go to *Triggers*).
2. Under *Add a trigger*, pick **Queue**.
3. Choose **Browse account**. It lists the SQS queues your machine's AWS credentials can see.
4. Pick the queue and click **Save**.

The list needs `pip install "py-serverless-kit[aws]"` and AWS credentials on the machine running studio. If something is missing, the picker shows a message and you can type the name instead [docs/studio.md#browse-account]."""),

    A(475, provider="gcp", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/studio.md#browse-account"],
      user="Browse account on GCP shows a message instead of my buckets. what does it need?",
      steps=[S("search_docs", query="browse account gcp needs",
               docs=[D("docs/studio.md", "browse-account")])],
      final="""On GCP, **Browse account** lists Pub/Sub topics and subscriptions and Cloud Storage buckets. It needs [docs/studio.md#browse-account]:
1. The SDKs on the machine running studio:
```bash
pip install google-cloud-pubsub google-cloud-storage
```
2. The project: `provider.options.project`, or `GOOGLE_CLOUD_PROJECT`.
3. Credentials on that machine, for example `gcloud auth application-default login`.

Restart studio after installing the packages if it still shows the message. You can always type the bucket name instead."""),

    A(476, provider="azure", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#state-remote-terraform-backend", "docs/troubleshooting.md#deploy-and-state"],
      user="Our CI pipeline and two developers deploy the Azure prod stage. Where should the Terraform state live, and how do we move the current local state there?",
      steps=[S("search_docs", query="remote backend azurerm state",
               docs=[D("docs/configuration.md", "state-remote-terraform-backend")]),
             S("search_docs", query="migrate state remote backend",
               docs=[D("docs/troubleshooting.md", "deploy-and-state", end="via `pskit tf -- init -migrate-state`.")])],
      final="""Put it in a remote backend that everyone uses. For Azure that's `azurerm` (any Terraform backend type works) [docs/configuration.md#state-remote-terraform-backend].

**In code**
```yaml
stages:
  prod:
    provider:
      state:
        backend: azurerm
        config:
          resource_group_name: rg-tfstate
          storage_account_name: tfstateorders
          container_name: tfstate
          key: orders-prod.tfstate
```
The storage account and container must exist before you run Terraform. The `config` keys are the `azurerm` backend's own settings.

**In the terminal**
On the machine whose `.pskit/azure-prod/` state matches what's deployed:
```bash
pskit tf -s prod -- init -migrate-state
```
[docs/troubleshooting.md#deploy-and-state]. After that, CI and both developers use the shared state; nobody needs the local file any more."""),

    A(477, provider="aws", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/configuration.md#state-remote-terraform-backend", "docs/getting-started.md#7-deploy"],
      user="what is the .pskit folder? should i commit it to git?",
      steps=[S("search_docs", query=".pskit folder state git-ignored",
               docs=[D("docs/configuration.md", "state-remote-terraform-backend", end="By default Terraform state lives in")]),
             S("search_docs", query="deploy writes deployment.json .pskit",
               docs=[D("docs/getting-started.md", "7-deploy", start="After deploying, pskit prints")])],
      final="""No, don't commit it. `.pskit/` is pskit's work folder and is git-ignored. Per provider and stage (`.pskit/aws-dev/`) it holds the build, `artifact.zip`, `main.tf.json`, `deployment.json` and, by default, the Terraform state `terraform.tfstate` [docs/configuration.md#state-remote-terraform-backend] [docs/getting-started.md#7-deploy].

The state is the important part: if you lose it, Terraform no longer knows what it deployed. When more than one person or CI deploys, move the state to a remote backend:
```yaml
provider:
  state:
    backend: s3
    config:
      bucket: my-tf-state
      key: orders/${opt:stage}.tfstate
      region: us-east-1
      dynamodb_table: tf-locks
```"""),

    A(478, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/resources.md#what-handlers-receive", "docs/resources.md#runtime-api"],
      user="Our api function on GCP should publish a message to the managed Pub/Sub topic resource billing-events after each order. pskit has no publish helper for clouds, right? What do I get in the handler to do it myself?",
      steps=[S("search_docs", query="resource binding gcp topic id environment",
               docs=[D("docs/resources.md", "what-handlers-receive", start="| Provider | Values added |", end="| others |")]),
             S("search_docs", query="resource runtime api publish sdk",
               docs=[D("docs/resources.md", "runtime-api", start="pskit does not ship a portable")])],
      final="""Right, there's no portable send helper for the clouds: use the cloud SDK with the binding values [docs/resources.md#runtime-api]. On GCP a managed topic resource also gets its Pub/Sub topic id as `ID` [docs/resources.md#what-handlers-receive].

**In code**
```python
from __future__ import annotations

import json

from google.cloud import pubsub_v1
from py_serverless_kit import resource

publisher = pubsub_v1.PublisherClient()


def api(event, ctx):
    order = event.http.json()
    topic = resource("billing-events")
    path = publisher.topic_path(ctx.env["PSKIT_GCP_PROJECT"], topic.native_name)
    publisher.publish(path, json.dumps(order).encode("utf-8")).result()
    return {"ok": True}
```
Add `google-cloud-pubsub` to `requirements.txt`. `PSKIT_GCP_PROJECT` is set by pskit on GCP. The runtime service account needs permission to publish to the topic.

Locally, `pskit invoke` sets the same `PSKIT_RESOURCE_*` variables, but the real publish needs Google credentials."""),

    A(479, provider="azure", stage="dev", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#provider-support"],
      user="azure: resource has functions: [api] but worker also sees PSKIT_RESOURCE_UPLOADS_*. bug?",
      steps=[S("search_docs", query="azure resource binding all functions app settings",
               docs=[D("docs/resources.md", "provider-support", start="On Azure, app settings belong")])],
      final="""Not a bug. On Azure, app settings belong to the whole Function App, so every function sees every binding [docs/resources.md#provider-support]. `functions:` still limits the binding on the other providers.

If `worker` must not use `uploads`, enforce it in code: only `resource("uploads")` in the functions that should use it."""),

    A(480, provider="aws", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#returning-a-response"],
      user="handler only: return a generated png from GET /chart",
      steps=[S("search_docs", query="return binary image response",
               docs=[D("docs/handlers.md", "returning-a-response", start='Response.json({"id": 1}', end="Response.no_content()")])],
      final="""**In code**
```python
from __future__ import annotations

from py_serverless_kit import Response


def chart(event, ctx):
    png_bytes = render_chart(event.http.query.get("range", "7d"))
    return Response.binary(png_bytes, "image/png")
```
`Response.binary` is base64-encoded for API Gateway automatically [docs/handlers.md#returning-a-response]. `render_chart` is your own function returning `bytes`."""),

    A(481, provider="gcp", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response", "docs/handlers.md#httprequest"],
      user="how set session cookie in response after login and read it again next request?",
      steps=[S("search_docs", query="set cookie response read cookies",
               docs=[D("docs/handlers.md", "returning-a-response", start="Response.json(user).set_cookie", end="Response.json(user).set_cookie"),
                     D("docs/handlers.md", "httprequest", start="| `cookies` |", end="| `cookies` |")])],
      final="""Set it with `set_cookie` on the response, and read it from `event.http.cookies` [docs/handlers.md#returning-a-response] [docs/handlers.md#httprequest].

**In code**
```python
from __future__ import annotations

from py_serverless_kit import Response, Unauthorized


def login(event, ctx):
    user, session_id = check_login(event.http.json())
    return Response.json(user).set_cookie("sid", session_id, max_age=3600, path="/",
                                          http_only=True, secure=True, same_site="Lax")


def me(event, ctx):
    sid = event.http.cookies.get("sid")
    if not sid:
        raise Unauthorized("not logged in")
    return load_user(sid)
```
`check_login` and `load_user` are your own functions.

**In the terminal**
```bash
pskit invoke -f me --path /me -H "Cookie: sid=abc"
```"""),

    A(482, provider="azure", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#errors"],
      user="when the amount in the request is wrong i want to send back an error with code 422 and say which field. how?",
      steps=[S("search_docs", query="return 422 error details field",
               docs=[D("docs/handlers.md", "errors", end="`TooManyRequests` | 429 |"),
                     D("docs/handlers.md", "errors", start='raise UnprocessableEntity("invalid order"', end="# -> 422")])],
      final="""Raise `UnprocessableEntity` with `details`. pskit turns it into a JSON 422 response [docs/handlers.md#errors].

**In code**
```python
from __future__ import annotations

from py_serverless_kit import UnprocessableEntity


def create(event, ctx):
    order = event.http.json()
    if not isinstance(order.get("amount"), (int, float)) or order["amount"] <= 0:
        raise UnprocessableEntity("invalid order", details={"field": "amount"})
    return {"ok": True}
```
The caller gets `422 {"error": "invalid order", "status": 422, "details": {"field": "amount"}}`.

**In the terminal**
```bash
pskit invoke -f create -d '{"amount": -5}'
```

**In studio**
1. Open **Test**, pick the function and its HTTP trigger.
2. Put `{"amount": -5}` in the payload and click **▶ Run locally**."""),

    A(483, provider="aws", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/troubleshooting.md#installation-and-tooling"],
      user="Error: pip install failed while vendoring dependencies\n\nhappens on package, we use a private lib mylib==0.3 that is only an sdist",
      steps=[S("search_docs", query="pip install failed while vendoring dependencies",
               docs=[D("docs/troubleshooting.md", "installation-and-tooling", start="**`pip install failed while vendoring dependencies`**", end="`pskit package --skip-deps` lets you test packaging without dependencies.")])],
      final="""For AWS, pskit downloads **Linux** wheels (`manylinux2014_<arch>`, `--only-binary=:all:`) for the target Python version. A package that is only an sdist has no such wheel, so pip fails [docs/troubleshooting.md#installation-and-tooling].

Fixes:
1. Publish a wheel for `mylib` (a pure-Python wheel works on every platform) to your package index, then pin that version.
2. Or vendor the code: copy `mylib` into your source folder so it's bundled with your code, and remove it from `requirements.txt`.
3. Extra pip flags (for example your private index) go in `package.pip_args`:
```yaml
package:
  pip_args: ["--extra-index-url", "https://pypi.example.com/simple"]
```

**In the terminal**
```bash
pskit package --skip-deps
pskit package
```
The first checks that everything else packages fine; the second shows whether the dependency problem is gone."""),

    A(484, provider="azure", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/cli.md#pskit-init-directory", "docs/studio.md#what-you-can-do"],
      user="new project for azure with queue and timer example, how to make it fast?",
      steps=[S("search_docs", query="init template events provider azure",
               docs=[D("docs/cli.md", "pskit-init-directory")])],
      final="""Use the `events` template: it adds schedule, queue and storage examples [docs/cli.md#pskit-init-directory].

**In the terminal**
```bash
pskit init orders -p azure -t events
cd orders
pskit validate
pskit invoke -f <function name> -t queue -d '[{"id": 1}]'
```
`-p azure` fills in the region and the Azure options. Use a function name from the generated `pskit.yml`.

**In studio**
1. Run `pskit studio --open` in an empty folder. The **New project** page opens.
2. Enter the service name, pick Azure and a starter template with events.
3. Open **Overview & provider** and check the region and *subscription_id* (deploy needs it).

Before deploying, sign in with `az login` and set `ARM_SUBSCRIPTION_ID`."""),

    A(485, provider="gcp", stage="staging", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#variables"],
      user="bucket name per stage in pskit.yml + region from env with default europe-west1",
      steps=[S("search_docs", query="variables opt stage env default",
               docs=[D("docs/configuration.md", "variables", end="When a value is exactly one variable")])],
      final="""**In code**
```yaml
provider:
  name: gcp
  region: ${env:GCP_REGION, europe-west1}
  options: {project: my-gcp-project}
functions:
  ingest:
    handler: app.ingest.handle
    events:
      - storage: uploads-${opt:stage}
```
`${opt:stage}` is the effective stage (`-s staging` gives `uploads-staging`), and `${env:NAME, default}` falls back to the default when the variable is unset [docs/configuration.md#variables]. Bucket names are global on GCP, so add a prefix that's unique to you."""),

    A(486, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/studio.md#saving-what-changes-in-pskityml", "docs/studio.md#what-you-can-do"],
      user="the studio shows 3 errors at the top but i want to stop for today. can i still save?",
      steps=[S("search_docs", query="studio save with validation errors",
               docs=[D("docs/studio.md", "saving-what-changes-in-pskityml")])],
      final="""Yes. A config that fails validation can still be saved, so you can stop half-way. The problems stay listed [docs/studio.md#saving-what-changes-in-pskityml].

**In studio**
1. Click **Save** (or Ctrl+S).
2. Next time, click the Problems button at the top ("3 errors · ..."); each problem links to the field it concerns.

Before each save, the previous file is copied to `.pskit/studio/backups/`. `pskit validate` and deploys will fail until the errors are fixed."""),

    A(487, provider="gcp", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/studio.md#saving-what-changes-in-pskityml"],
      user="after I clicked Save in studio, all my comments in pskit.yml are gone and the keys are in another order!! can i get the old file back?",
      steps=[S("search_docs", query="studio save comments removed backup",
               docs=[D("docs/studio.md", "saving-what-changes-in-pskityml")])],
      final="""Yes. Studio doesn't keep comments, and key order follows its layout. But before every save it copies the previous file to `.pskit/studio/backups/pskit.<timestamp>.yml`; the last 20 are kept [docs/studio.md#saving-what-changes-in-pskityml].

To get the old file back:
1. Open `.pskit/studio/backups/` and find the backup from before your save.
2. Copy it over `pskit.yml` (or copy the comments back from it).
3. In studio, choose reload when it says the file changed on disk.

Values such as `${env:API_KEY}` and `${self:custom.x}` are kept as written, never resolved. If comments matter to you, edit those parts in the **YAML** page's raw mode or in your editor."""),

    A(488, provider="azure", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/studio.md#what-you-can-do"],
      user="studio only: where do i see the yaml studio will write and the diff against the file on disk",
      steps=[S("search_docs", query="studio yaml page diff raw editing",
               docs=[D("docs/studio.md", "what-you-can-do", start="| **YAML** |", end="asks first.")])],
      final="""**In studio**
1. Open **YAML**. It shows the generated `pskit.yml` from your draft.
2. Switch to the diff to compare it with the file on disk.
3. Use the raw-YAML editing mode if you want to type YAML directly.
4. Click **Save** (Ctrl+S) to write it. Nothing touches disk before that [docs/studio.md#what-you-can-do]."""),

    A(489, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing"],
      user="porting a lambda that uses event['pathParameters'], event['queryStringParameters'], context.aws_request_id and returns statusCode/body. what are the pskit equivalents? code please",
      steps=[S("search_docs", query="lambda event pathParameters equivalent pskit",
               docs=[D("docs/migrating-from-aws.md", "step-1-separate-business-logic-from-aws-event-parsing", start="| Lambda | pskit |")])],
      final="""**In code**
```python
from __future__ import annotations

from py_serverless_kit import Context, Event, NotFound, Response


def get_order(event: Event, ctx: Context):
    order_id = event.http.path_params["id"]            # event["pathParameters"]
    verbose = event.http.query.get("verbose") == "1"    # event["queryStringParameters"]
    ctx.logger.info("get order", extra={"order_id": order_id, "req": ctx.request_id})  # context.aws_request_id
    order = load(order_id)
    if order is None:
        raise NotFound(f"order {order_id} not found")
    return Response.json(order if verbose else {"id": order_id})   # instead of statusCode/body
```
Returning a plain dict also gives JSON 200. Headers are `event.http.headers` (case-insensitive) and the body is `event.http.json()` [docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing]. `load` is your own function."""),

    A(490, provider="gcp", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/local-development.md#pskit-dev-local-server"],
      user="I run pskit dev for our HTTP routes. Can I also push a couple of queue messages to the process-jobs worker through the same dev server with curl, without a real Pub/Sub?",
      steps=[S("search_docs", query="pskit dev invoke queue function curl",
               docs=[D("docs/local-development.md", "pskit-dev-local-server", start="| Endpoint | What it does |")])],
      final="""Yes. `pskit dev` has `POST /__pskit/invoke/<function>?type=...`. With `type=queue`, the JSON list in the body becomes the records [docs/local-development.md#pskit-dev-local-server].

**In the terminal**
```bash
pskit dev
curl -X POST "localhost:3000/__pskit/invoke/process-jobs?type=queue" -d '[{"job": 1}, {"job": 2}]'
```
The response is `{"result": ...}`, or 500 with `{"errorType", "cause"}` if the handler raises. Code changes are picked up before each request (hot reload), so you don't need to restart."""),
]
