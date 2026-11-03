"""Category A (docs Q&A and how-to), batch 30: aws / gcp / azure. Stages and names, memory / timeout / runtime
limits and overrides, existing IAM role, custom variables, info refresh, verbose errors, pskit dev on the LAN,
pytest for HTTP and workflows, context identity, redirects, JSON bodies and repeated query params.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(571, provider="aws", stage="staging", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/getting-started.md#7-deploy", "docs/architecture.md#deploy-pipeline"],
      user="i want a full copy of my app on aws for testing, separate from dev. how?",
      steps=[S("search_docs", query="deploy another stage separate copy",
               docs=[D("docs/getting-started.md", "7-deploy", end="After deploying, pskit prints")])],
      final="""Deploy another stage. Each stage is a separate copy of every resource, with its own Terraform state in `.pskit/aws-<stage>/` [docs/getting-started.md#7-deploy].

**In studio**
1. Type `staging` in the stage field of the top bar.
2. Open **Deploy** and click **Deploy**.

**In the terminal**
```bash
pskit deploy --stage staging
pskit info --stage staging
```
Deployed names include the stage (`<service>-staging-<function>`), so dev and staging never collide. Remove the copy later with `pskit remove --stage staging`."""),

    A(572, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/configuration.md#provider"],
      user="Error: pskit.yml is invalid:\n  - provider.stage: Value error, stage must be lowercase alphanumeric/dash, max 16 chars, e.g. dev, prod\n\ni ran pskit deploy -s Prod_1",
      steps=[S("search_docs", query="stage name rules lowercase",
               docs=[D("docs/configuration.md", "provider", start="| `stage` |", end="| `stage` |")])],
      final="""Stage names must match `[a-z][a-z0-9-]{0,15}`: lowercase letters, digits and dashes, starting with a letter, at most 16 characters [docs/configuration.md#provider]. `Prod_1` has an upper-case letter and an underscore.

**In the terminal**
```bash
pskit deploy -s prod-1
```
Stage names go into the deployed resource names, which is why the rule is strict."""),

    A(573, provider="azure", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/configuration.md#top-level"],
      user="Error: pskit.yml is invalid:\n  - service: Value error, service must be 2-32 chars of lowercase letters, digits and dashes",
      steps=[S("search_docs", query="service name rules",
               docs=[D("docs/configuration.md", "top-level", start="| `service` |", end="| `service` |")])],
      final="""`service` must be 2–32 characters of lowercase letters, digits and `-`, starting with a letter [docs/configuration.md#top-level]. Something like `My_Service` breaks the rule.

**In code**
```yaml
service: my-service
```

**In studio**
1. Open **Overview & provider**.
2. Change *Service name* to `my-service` and click **Save**.

Changing the service name of a deployed service creates new resources under the new name; remove the old deployment first if you don't need it."""),

    A(574, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      user="resize fn needs 2048 MB, everything else stays default",
      steps=[S("search_docs", query="function memory override",
               docs=[D("docs/configuration.md", "functions", start="| `runtime`, `memory`, `timeout`, `architecture` |", end="| `runtime`, `memory`, `timeout`, `architecture` |")])],
      final="""**In code**
```yaml
functions:
  resize:
    handler: app.images.resize
    memory: 2048
```
Function values override the provider's; the others keep `provider.memory` (default 256 MB). Range 64–32768 [docs/configuration.md#functions]. On Lambda more memory also gives more CPU.

**In studio**
1. Open **Functions** and click `resize`.
2. Set *Memory (MB)* to 2048 and click **Save**."""),

    A(575, provider="gcp", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#provider", "docs/configuration.md#functions"],
      user="Most of our GCP functions are quick, so we want a 15 s timeout as the default for all of them, but the export function needs 300 s. How do we set a default plus one exception?",
      steps=[S("search_docs", query="provider timeout default function override",
               docs=[D("docs/configuration.md", "provider", start="| `timeout` |", end="| `timeout` |"),
                     D("docs/configuration.md", "functions", start="| `runtime`, `memory`, `timeout`, `architecture` |", end="| `runtime`, `memory`, `timeout`, `architecture` |")])],
      final="""Set the default on `provider` and override it on the function [docs/configuration.md#provider] [docs/configuration.md#functions].

**In code**
```yaml
provider:
  name: gcp
  timeout: 15
functions:
  export:
    handler: app.export.run
    timeout: 300
```

**In studio**
1. Open **Overview & provider**, and under *Defaults for every function* set *Timeout (s)* to 15.
2. Open **Functions**, click `export`, set *Timeout (s)* to 300.
3. Click **Save**.

If `export` has an event trigger (queue, storage, topic), GCP allows at most 540 s; HTTP functions can go to 3600 s."""),

    A(576, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#providers"],
      user="can i make timeout 15 minutes on azure function?",
      steps=[S("search_docs", query="azure max timeout",
               docs=[D("docs/providers.md", "providers", start="| Provider | Tier |", end="| [`azure`]")])],
      final="""No. The max timeout on Azure Functions with pskit is 600 s (10 minutes) [docs/providers.md#providers]. With 900, `pskit validate` reports `timeout 900s exceeds Azure Functions max 600s`.

Options:
1. Set `timeout: 600` or less and make the job smaller.
2. Split the work into chunks on a queue, so each run fits in 10 minutes.
3. For a chain of steps, use a workflow with `engine: native` (Logic App), where each task is a separate function call."""),

    A(577, provider="aws", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/providers.md#providers", "docs/troubleshooting.md#configuration"],
      user="ERROR: [provider.runtime] AWS Lambda does not support python3.14; use one of: python3.10, python3.11, python3.12, python3.13, python3.9",
      steps=[S("search_docs", query="does not support python runtime pinned",
               docs=[D("docs/troubleshooting.md", "configuration", start="**`<provider> does not support python3.12`**", end="(`pskit providers --json`).")])],
      final="""You pinned `runtime: python3.14`, which Lambda doesn't offer; AWS supports 3.9–3.13 with pskit [docs/troubleshooting.md#configuration].

Fix: remove `runtime` so pskit picks python3.12, or pin a supported one:
```yaml
provider:
  name: aws
  runtime: python3.13
```
Then run `pskit validate`. Python 3.14 is available on the on-premises provider only."""),

    A(578, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#functions"],
      user="One legacy function depends on a library that only works on Python 3.11. The rest of the service should stay on the default runtime. Possible?",
      steps=[S("search_docs", query="function runtime override",
               docs=[D("docs/configuration.md", "functions", start="    runtime: python3.12", end="    runtime: python3.12")])],
      final="""Yes. `runtime` on a function overrides `provider.runtime` [docs/configuration.md#functions].

**In code**
```yaml
functions:
  legacy:
    handler: app.legacy.handle
    runtime: python3.11
```

**In studio**
1. Open **Functions** and click `legacy`.
2. Set *Runtime* to `python3.11` and click **Save**.

GCP supports 3.9–3.13, so both runtimes are fine. Keep the handler code Python 3.9 compatible anyway."""),

    A(579, provider="azure", stage="prod", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/providers.md#azure-azure-functions"],
      user="On AWS we'd use provisioned concurrency. On Azure the Consumption plan cold starts hurt us in prod. Can pskit deploy to a different plan?",
      steps=[S("search_docs", query="azure plan sku consumption",
               docs=[D("docs/providers.md", "azure-azure-functions", start="provider:", end="One **Linux Consumption Function App**")])],
      final="""pskit has `options.plan_sku`, the SKU of the App Service plan; the default is `Y1` (Consumption) [docs/providers.md#azure-azure-functions].

**In code**
```yaml
stages:
  prod:
    provider:
      options:
        plan_sku: EP1
```
In studio the *Plan SKU* provider option suggests `Y1`, `EP1`–`EP3`, `B1`–`B3`, `S1`, `S2`, `P1v3`, `P2v3`, with the hint "Y1 = consumption, EP* = elastic premium, B/S/P = dedicated". Only prod changes, dev keeps `Y1`.

**In the terminal**
```bash
pskit plan -s prod
```
Read the plan before deploying: changing the plan changes the hosting of the whole Function App, and premium plans cost more."""),

    A(580, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#provider", "docs/resources.md#aws-iam"],
      user="Our platform team gives us a pre-made Lambda execution role, arn:aws:iam::123456789012:role/orders-lambda. pskit must use it and not create roles. What changes, and what don't we get?",
      steps=[S("search_docs", query="iam role existing role",
               docs=[D("docs/configuration.md", "provider", start="| `iam.role` |", end="| `iam.role` |")]),
             S("search_docs", query="own role resources grants warning",
               docs=[D("docs/resources.md", "aws-iam", start="If you bring your own role")])],
      final="""Set `iam.role`; pskit uses that role instead of creating one [docs/configuration.md#provider].

**In code**
```yaml
provider:
  name: aws
  iam:
    role: arn:aws:iam::123456789012:role/orders-lambda
```

What you don't get: pskit can't change your role, so the grants it would add (the `pskit-resources` policy for bound buckets, queues and topics, and your `iam.statements`) aren't applied. The plan prints a warning, and granting access is up to the platform team [docs/resources.md#aws-iam].

**In the terminal**
```bash
pskit plan -s prod
```
Send the plan's warning to the platform team so they can add the permissions."""),

    A(581, provider="gcp", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#variables"],
      user="same bucket name used in 3 functions. i want write it one time in yml",
      steps=[S("search_docs", query="custom values self variable reuse",
               docs=[D("docs/configuration.md", "variables", end="When a value is exactly one variable")])],
      final="""Put it under `custom` and use `${self:custom.<key>}` [docs/configuration.md#variables].

**In code**
```yaml
custom:
  bucket: acme-uploads-${opt:stage}
functions:
  ingest:
    handler: app.ingest.handle
    events:
      - storage: ${self:custom.bucket}
  thumbs:
    handler: app.thumbs.handle
    environment: {BUCKET: "${self:custom.bucket}"}
  report:
    handler: app.report.run
    environment: {BUCKET: "${self:custom.bucket}"}
```
If the key doesn't exist, validate fails with `unresolved variables: self:custom.bucket`. A `resources:` entry is another way: bind the bucket once and read `resource("<key>").native_name` in the code."""),

    A(582, provider="azure", stage="staging", mode="ask", page="Overview", persona="beginner",
      sources=["docs/cli.md#pskit-info"],
      user="someone changed the app in the azure portal and now pskit info shows old url. how update it?",
      steps=[S("search_docs", query="info refresh terraform output",
               docs=[D("docs/cli.md", "pskit-info")])],
      final="""`pskit info` shows the saved record of the last deploy. Use `--refresh` to re-read `terraform output` instead [docs/cli.md#pskit-info]:

```bash
pskit info -s staging --refresh
```
If the portal change isn't in Terraform (state), `--refresh` can't see it either. Run `pskit plan -s staging` to see whether Terraform would undo the manual change on the next deploy; it's best to make changes through `pskit.yml`."""),

    A(583, provider="aws", stage="dev", mode="ask", page="Deploy", persona="terse_expert",
      sources=["docs/troubleshooting.md#troubleshooting-faq", "docs/cli.md#common-project-options"],
      user="pskit deploy prints one Error: line only. how to get the full traceback?",
      steps=[S("search_docs", query="verbose traceback error line",
               docs=[D("docs/troubleshooting.md", "troubleshooting-faq", end="Start with `pskit validate`"),
                     D("docs/cli.md", "common-project-options", start="Configuration, packaging, provider and Terraform errors")])],
      final="""**In the terminal**
```bash
pskit deploy -v
```
Add `-v` to any command to print the full traceback. Without it, configuration, packaging, provider and Terraform errors print a single `Error: …` line and exit with code 1 [docs/cli.md#common-project-options]. Start with `pskit validate`, which catches most provider limits before Terraform runs [docs/troubleshooting.md#troubleshooting-faq]."""),

    A(584, provider="gcp", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/local-development.md#pskit-dev-local-server"],
      user="cli only: run pskit dev so my phone on same wifi can open the api, port 8080",
      steps=[S("search_docs", query="pskit dev host port",
               docs=[D("docs/local-development.md", "pskit-dev-local-server", end="On startup it prints every route:")])],
      final="""**In the terminal**
```bash
pskit dev --host 0.0.0.0 --port 8080
```
Then open `http://<your laptop's LAN address>:8080/<route>` on the phone [docs/local-development.md#pskit-dev-local-server]. `0.0.0.0` makes it reachable from your network, so stop it when you're done."""),

    A(585, provider="azure", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/local-development.md#testing-with-pytest"],
      user="We want pytest tests for our create-item HTTP function: a valid POST should return 201 and an empty name 400. No Azure needed in CI. What does such a test look like?",
      steps=[S("search_docs", query="pytest LocalRunner http_event status",
               docs=[D("docs/local-development.md", "testing-with-pytest", end="| `runner.invoke(function, event)` |", words=320)])],
      final="""Use `LocalRunner` with `http_event`; HTTP calls return a `Response` with `status` [docs/local-development.md#testing-with-pytest]. It needs no cloud credentials or Terraform.

**In code**
```python
# tests/test_items.py
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, http_event

runner = LocalRunner(Project.load())


def test_create_item_ok():
    resp = runner.invoke("create-item", http_event("POST", "/items", body={"name": "lamp"}))
    assert resp.status == 201


def test_create_item_needs_name():
    resp = runner.invoke("create-item", http_event("POST", "/items", body={"name": ""}))
    assert resp.status == 400
```

**In the terminal**
```bash
pytest tests/test_items.py
```
The second test passes only if your handler raises `BadRequest` (or returns 400) for an empty name."""),

    A(586, provider="aws", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/local-development.md#testing-with-pytest"],
      user="pytest for a step functions workflow, check output, no aws",
      steps=[S("search_docs", query="pytest run_workflow output",
               docs=[D("docs/local-development.md", "testing-with-pytest", start="def test_workflow():", end="| `runner.run_workflow(name, data, sleep=False)` |"),
                     D("docs/local-development.md", "testing-with-pytest", start="| `runner.run_workflow(name, data, sleep=False)` |", end="| `runner.run_workflow(name, data, sleep=False)` |")])],
      final="""**In code**
```python
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner

runner = LocalRunner(Project.load())


def test_order_pipeline():
    out = runner.run_workflow("order-pipeline", {"amount": 5})
    assert out["output"]["charged"] is True
```
`run_workflow` runs it on the embedded engine with the real task handlers and returns `{"output", "history"}`; a failed run raises `WorkflowFailed` [docs/local-development.md#testing-with-pytest]. Use `sleep=True` to really wait in `wait` states. Adjust the assertion to your workflow's output."""),

    A(587, provider="gcp", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#context"],
      user="In the handler I need to know which stage and region I'm running in, to pick the right table names. What's the portable way?",
      steps=[S("search_docs", query="context stage region identity",
               docs=[D("docs/handlers.md", "context")])],
      final="""Use the context: `ctx.stage`, `ctx.region`, `ctx.service`, `ctx.provider` and `ctx.function` identify the deployment on every cloud [docs/handlers.md#context].

**In code**
```python
from __future__ import annotations


def handler(event, ctx):
    table = f"{ctx.service}-{ctx.stage}-orders"
    ctx.logger.info("using table", extra={"table": table, "region": ctx.region})
    return {"table": table}
```
Locally `ctx.provider` is `local` and the region is `local`, while the stage is the one you pass with `-s`. If the name doesn't follow a pattern, pass it in `environment` instead."""),

    A(588, provider="azure", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      user="after the form is sent i want to send the browser to /thanks page. how?",
      steps=[S("search_docs", query="redirect response",
               docs=[D("docs/handlers.md", "returning-a-response", start="Response.redirect", end="Response.redirect")])],
      final="""Return `Response.redirect` [docs/handlers.md#returning-a-response].

**In code**
```python
from __future__ import annotations

from py_serverless_kit import Response


def submit(event, ctx):
    fields = event.http.form()
    save(fields)
    return Response.redirect("/thanks", status=302)
```
`save` is your own function. Add a `GET /thanks` route (or a static page) for the browser to land on."""),

    A(589, provider="aws", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      user="{\"error\": \"Request body is empty, expected JSON\", \"status\": 400}\n\nmy webhook sometimes sends empty POST body and my function fails like this",
      steps=[S("search_docs", query="json body invalid empty BadRequest default",
               docs=[D("docs/handlers.md", "httprequest", start="| `json(default=...)` |", end="| `json(default=...)` |")])],
      final="""`event.http.json()` raises `BadRequest` (HTTP 400) when the body is empty or not valid JSON, unless you pass `default` [docs/handlers.md#httprequest].

**In code**
```python
from __future__ import annotations


def webhook(event, ctx):
    payload = event.http.json(default={})
    if not payload:
        return None                     # 204 No Content
    process(payload)
    return {"ok": True}
```
`process` is your own function.

**In the terminal**
```bash
pskit invoke -f webhook --method POST --path /webhook
```
With no `-d`, the request has no body, so you can check the empty case."""),

    A(590, provider="gcp", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#httprequest"],
      user="GET /items?tag=a&tag=b. query gives only b. all values?",
      steps=[S("search_docs", query="multi_query repeated query parameters",
               docs=[D("docs/handlers.md", "httprequest", start="| `query` |", end="| `multi_query` |")])],
      final="""`query` keeps the last value; use `multi_query` for all of them [docs/handlers.md#httprequest].

```python
tags = event.http.multi_query.get("tag", [])   # ["a", "b"]
```"""),
]
