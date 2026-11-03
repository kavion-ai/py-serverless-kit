"""Category A (docs Q&A and how-to), batch 29: aws / gcp / azure. Node.js and TypeScript, architecture (Terraform
JSON, bundle shims), dependencies per cloud, cloud SDKs for publishing, reproducible artifacts, CI plugin cache,
OpenTofu, invoke() resolution per cloud, event fields, Azure env specifics. Hand-written; assembled by
tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(551, provider="aws", stage="dev", mode="ask", page="none", persona="terse_expert",
      sources=["docs/nodejs.md#nodejs-and-typescript", "docs/nodejs.md#typescript"],
      user="new typescript service on lambda, node 20. scaffold + run locally",
      steps=[S("search_docs", query="init typescript nodejs project",
               docs=[D("docs/nodejs.md", "nodejs-and-typescript", end="## Choosing the runtime")])],
      final="""**In the terminal**
```bash
pskit init my-api -p aws --typescript
cd my-api
pskit dev
pskit invoke -f hello --path "/hello?name=Ada"
```
`--typescript` gives Node.js 20 + TypeScript [docs/nodejs.md#nodejs-and-typescript]. pskit compiles the `.ts` files with `tsc` when it packages or runs the service; type errors fail the build. Run `npm install` first if you add dependencies. Use the function names from the generated `pskit.yml`."""),

    A(552, provider="aws", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/nodejs.md#choosing-the-runtime"],
      user="nodejs24 can use for aws lambda in pskit?",
      steps=[S("search_docs", query="nodejs runtimes aws lambda",
               docs=[D("docs/nodejs.md", "choosing-the-runtime", start="| Provider | Node.js runtimes | Dependencies |", end="| Azure Functions |")])],
      final="""No. On AWS Lambda pskit supports `nodejs18`, `nodejs20` and `nodejs22` [docs/nodejs.md#choosing-the-runtime]. `nodejs24` is only listed for on-premises.

**In code**
```yaml
provider:
  name: aws
  runtime: nodejs22
```
Then run `pskit validate`."""),

    A(553, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/resource-usage.md#how-dependencies-reach-the-function", "docs/nodejs.md#local-development"],
      user="my node functions use axios. do i need to run npm install before deploying to google cloud?",
      steps=[S("search_docs", query="node dependencies gcp cloud build package.json",
               docs=[D("docs/resource-usage.md", "how-dependencies-reach-the-function")])],
      final="""Not for the deploy. On GCP, Node.js dependencies are installed by Cloud Build from your `package.json` [docs/resource-usage.md#how-dependencies-reach-the-function]. Just list `axios` under `dependencies` there.

For local runs (`pskit dev`, `pskit invoke`), dependencies resolve from the project's `node_modules`, so run `npm install` once on your machine [docs/nodejs.md#local-development]. Don't add `pskit` itself to `package.json`; it's bundled with every deployment."""),

    A(554, provider="azure", stage="dev", mode="ask", page="Code", persona="pasted_error",
      sources=["docs/nodejs.md#typescript"],
      user="Cannot find module 'pskit' or its corresponding type declarations.\n\nvs code shows this in my handlers.ts, and there is no pskit package on npm we can install?",
      steps=[S("search_docs", query="typescript types for pskit cannot find module",
               docs=[D("docs/nodejs.md", "typescript", start="* **Types for `pskit`**", end="Run `pskit package` once (or `pskit init`) if your editor can't resolve `pskit` yet.")])],
      final="""Right, the types need no npm package. `pskit init`, `pskit package` and `pskit dev` write `.pskit/types/pskit/index.d.ts`, and the generated `tsconfig.json` maps `pskit` to it [docs/nodejs.md#typescript].

**In the terminal**
```bash
pskit package
```
Then check `tsconfig.json` has the mapping:
```json
{ "compilerOptions": { "paths": { "pskit": ["./.pskit/types/pskit/index.d.ts"] } } }
```
Leave out `baseUrl` and `moduleResolution: "node"`. Reload the VS Code window afterwards."""),

    A(555, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/nodejs.md#dependencies-and-packaging"],
      user="Our Node.js code base is all ES modules with import/export. Does pskit handle that, or do we have to compile to CommonJS for GCP?",
      steps=[S("search_docs", query="es modules type module mjs",
               docs=[D("docs/nodejs.md", "dependencies-and-packaging", start="Node.js 18+ and npm must be on `PATH`")])],
      final="""ES modules work. Set `"type": "module"` in `package.json` or use `.mjs` files; pskit loads handlers with `import()` [docs/nodejs.md#dependencies-and-packaging]. No CommonJS step needed.

Node.js 18+ and npm must be on `PATH` on the machine where you package. Check it locally first:
```bash
pskit invoke -f hello
```"""),

    A(556, provider="aws", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/nodejs.md#dependencies-and-packaging"],
      user="We already have an npm build script (esbuild) that writes to dist/. Can pskit use our build and bundle dist/ instead of running tsc itself? yaml please",
      steps=[S("search_docs", query="package node build out_dir own build step",
               docs=[D("docs/nodejs.md", "dependencies-and-packaging", end="Node.js 18+ and npm must be on `PATH`")])],
      final="""**In code**
```yaml
package:
  source: .
  node:
    build: [npm, run, build]
    out_dir: dist
```
`build` replaces pskit's `tsc` step, and `out_dir` is the folder that gets bundled instead of `source` [docs/nodejs.md#dependencies-and-packaging]. Point the handlers at the built files' module paths."""),

    A(557, provider="azure", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/architecture.md#bundle-layout", "docs/providers.md#azure-azure-functions"],
      user="I unzipped .pskit/azure-dev/artifact.zip and found a function_app.py and host.json I never wrote. What are they, and should I edit them?",
      steps=[S("search_docs", query="bundle layout shim function_app host.json",
               docs=[D("docs/architecture.md", "bundle-layout", end="On-premises also writes")])],
      final="""They're pskit's Azure shim. Every bundle contains your code, the vendored runtime `py_serverless_kit/`, `pskit_manifest.json` and a provider shim; on Azure the shim is `function_app.py` + `host.json` [docs/architecture.md#bundle-layout]. pskit generates them with the Python v2 programming model, one trigger per function, and `routePrefix` empty [docs/providers.md#azure-azure-functions].

Don't edit them: they're regenerated on every `pskit package` / `pskit deploy`. Change `pskit.yml` instead; for settings pskit doesn't model use `functions.<fn>.options` or `provider.terraform.extra`."""),

    A(558, provider="aws", stage="dev", mode="ask", page="none", persona="aws_migrator",
      sources=["docs/architecture.md#deploy-pipeline"],
      user="Does pskit call the Lambda / API Gateway APIs itself like the Serverless Framework does with CloudFormation, or what exactly happens on deploy?",
      steps=[S("search_docs", query="deploy pipeline terraform json architecture",
               docs=[D("docs/architecture.md", "deploy-pipeline", start="Key properties:")])],
      final="""Neither: pskit doesn't call the cloud APIs for the deploy. It turns `pskit.yml` into a deterministic zip plus **Terraform JSON** (`main.tf.json`) and runs Terraform, which creates the Lambda functions, API Gateway and the rest [docs/architecture.md#deploy-pipeline].

What that means for you:
- Everything lands in `.pskit/aws-<stage>/`: the build, `artifact.zip`, `main.tf.json` and the Terraform state.
- Each provider and stage has its own Terraform workspace and state.
- Unchanged code gives a byte-identical zip, so there's no redeploy.

**In the terminal**
```bash
pskit package
pskit plan
```
`package` writes the zip and `main.tf.json` without contacting AWS; `plan` shows what Terraform would change."""),

    A(559, provider="gcp", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      user="gcp schedule on a function that only has a queue trigger: scheduler calls what?",
      steps=[S("search_docs", query="gcp cloud scheduler event-only function pubsub",
               docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="| schedule | Cloud Scheduler", end="| schedule | Cloud Scheduler")])],
      final="""For an event-only function, Cloud Scheduler publishes to Pub/Sub instead of making an OIDC POST to an HTTP URL [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. The handler still sees `event.type == "schedule"` and `event.data` = the schedule's `input`, because pskit wraps scheduled payloads in an envelope that the adapter unwraps. `timezone` is supported."""),

    A(560, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/resource-usage.md#which-library-for-which-resource", "docs/resources.md#what-handlers-receive"],
      user="i want send message to my sqs queue resource from api function. which library and where is the queue url?",
      steps=[S("search_docs", query="aws send sqs message library resource url",
               docs=[D("docs/resource-usage.md", "queues-buckets-and-topics", start="| Provider | queue | storage | topic |", end="| azure |")])],
      final="""Use `boto3`; the queue URL is `resource("jobs").url` [docs/resource-usage.md#queues-buckets-and-topics]. On AWS, queue resources get `ARN` and `URL` [docs/resources.md#what-handlers-receive].

**In code**
```python
from __future__ import annotations

import json

import boto3
from py_serverless_kit import resource

sqs = boto3.client("sqs")


def api(event, ctx):
    jobs = resource("jobs")
    sqs.send_message(QueueUrl=jobs.url, MessageBody=json.dumps(event.http.json()))
    return ("", 202)
```
Add `boto3` to `requirements.txt`. The role already gets `sqs:SendMessage` for the bound queue (`pskit-resources` policy). Use your resource key instead of `jobs`."""),

    A(561, provider="azure", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/resource-usage.md#queues-buckets-and-topics"],
      user="which python library do i use on azure to put a message on a queue, upload a blob, and send to a topic?",
      steps=[S("search_docs", query="azure library queue blob topic python",
               docs=[D("docs/resource-usage.md", "queues-buckets-and-topics", start="| Provider | queue | storage | topic |", end="| azure |")])],
      final="""On Azure [docs/resource-usage.md#queues-buckets-and-topics]:
- queue: `azure-storage-queue`
- storage (blobs): `azure-storage-blob`
- topic (Service Bus): `azure-servicebus`

Add the ones you use to `requirements.txt`; on Azure they're installed by the remote (Oryx) build. Read the resource's name with `resource("<key>").native_name`. Receiving is the same on every cloud: a function with a trigger gets `event.records`."""),

    A(562, provider="gcp", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/troubleshooting.md#deploy-and-state"],
      user="I changed nothing in the code, but pskit plan on GCP prod shows the function source object will be replaced. Why would that happen?",
      steps=[S("search_docs", query="changed nothing terraform wants update function",
               docs=[D("docs/troubleshooting.md", "deploy-and-state", start="**Changed nothing but Terraform wants to update the function**", end="Inspect `.pskit/<provider>-<stage>/build/`.")])],
      final="""The artifact is deterministic, so a real diff means something in it changed: a source file, a dependency, or `pskit_manifest.json` [docs/troubleshooting.md#deploy-and-state]. The manifest changes when routes, CORS, timeouts or function names change in `pskit.yml`.

Find it:
1. Run `pskit package -s prod` and look at `.pskit/gcp-prod/build/`.
2. Compare it with a previous build (or check `git status` for files under `package.source`, including data files that aren't excluded).
3. Check `requirements.txt` and `pskit.yml` changes since the last deploy.

Unchanged inputs hash identically, so once the extra file is excluded or the change is committed, the plan stops showing it."""),

    A(563, provider="aws", stage="dev", mode="ask", page="none", persona="terse_expert",
      sources=["docs/troubleshooting.md#deploy-and-state"],
      user="ci spends minutes downloading the aws terraform provider on every pskit deploy. fix?",
      steps=[S("search_docs", query="provider plugin downloads slow ci cache",
               docs=[D("docs/troubleshooting.md", "deploy-and-state", start="**Provider plugin downloads are slow in CI**", end="Set `TF_PLUGIN_CACHE_DIR` and cache that directory.")])],
      final="""Set `TF_PLUGIN_CACHE_DIR` and cache that directory between CI runs [docs/troubleshooting.md#deploy-and-state].

```bash
export TF_PLUGIN_CACHE_DIR="$HOME/.terraform.d/plugin-cache"
mkdir -p "$TF_PLUGIN_CACHE_DIR"
pskit deploy -s dev
```
Point your CI's cache step at that folder."""),

    A(564, provider="azure", stage="dev", mode="ask", page="Setup", persona="informal_non_native",
      sources=["docs/troubleshooting.md#faq", "docs/configuration.md#terraform"],
      user="our company use opentofu not terraform. pskit work with it for azure?",
      steps=[S("search_docs", query="opentofu tofu binary",
               docs=[D("docs/troubleshooting.md", "faq", start="**Can I use OpenTofu?**")])],
      final="""Yes. pskit finds `terraform`, then `tofu`, on `PATH`. To pick it explicitly use `PSKIT_TERRAFORM_BIN=tofu` or `provider.terraform.binary: tofu` [docs/troubleshooting.md#faq].

**In code**
```yaml
provider:
  name: azure
  terraform:
    binary: tofu
```

**In the terminal**
```bash
export PSKIT_TERRAFORM_BIN=tofu
pskit doctor -p azure
```
`doctor` shows which binary it found."""),

    A(565, provider="gcp", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      user="For Cloud Functions I always add functions-framework to requirements.txt. Needed with pskit?",
      steps=[S("search_docs", query="gcp requirements functions-framework added",
               docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="- **Dependencies:**", end="- **Dependencies:**")])],
      final="""No. On GCP pskit adds `functions-framework` automatically, and the dependencies are built remotely from your `requirements.txt` [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. List only what your own code imports. Don't add `py-serverless-kit` either; the runtime is bundled."""),

    A(566, provider="aws", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      user="Our orders service needs to call the pricing function, which lives in a different pskit service with an HTTP route. Can invoke('pricing') reach it?",
      steps=[S("search_docs", query="invoke endpoint environment variable other service",
               docs=[D("docs/handlers.md", "invoke-calling-another-function", start="How the target is resolved:", end="2. `local` (CLI, tests)")])],
      final="""Yes, with `PSKIT_ENDPOINT_PRICING`. If that variable is set, `invoke("pricing", ...)` POSTs to that http(s) URL instead of calling a function of the same service; this works on any provider [docs/handlers.md#invoke-calling-another-function].

**In code**
```yaml
functions:
  orders:
    handler: app.orders.create
    environment:
      PSKIT_ENDPOINT_PRICING: https://pricing.example.com/price
```
```python
from __future__ import annotations

from py_serverless_kit import invoke


def create(event, ctx):
    price = invoke("pricing", {"sku": event.http.json()["sku"]})
    return {"price": price}
```
Use the pricing function's URL from `pskit info` in the other service. Non-alphanumeric characters in the name become `_` (`price-v2` → `PSKIT_ENDPOINT_PRICE_V2`)."""),

    A(567, provider="azure", stage="staging", mode="ask", page="Code", persona="pasted_error",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      user="py_serverless_kit.runtime.invoke.InvokeError raised by invoke('billing', ...) on Azure staging. locally it works",
      steps=[S("search_docs", query="InvokeError azure invoke endpoint",
               docs=[D("docs/handlers.md", "invoke-calling-another-function", start="How the target is resolved:", end="Example: [`examples/09-function-invoke`]")])],
      final="""Locally `invoke()` runs the other handler in-process. In the cloud, only AWS and GCP have a built-in way; on Azure it raises `InvokeError` unless `PSKIT_ENDPOINT_BILLING` is set [docs/handlers.md#invoke-calling-another-function].

Fix: set the endpoint to billing's URL. If `billing` is invoke-only, Azure gives it `POST /_pskit/invoke/billing`, which needs the function key.

**In code**
```yaml
stages:
  staging:
    functions:
      orders:
        environment:
          PSKIT_ENDPOINT_BILLING: ${env:BILLING_URL}
```
Set `BILLING_URL` from `pskit info -s staging` when you deploy. If the route needs the function key, include it the way Azure accepts it (for example a `code` query parameter in the URL), and treat that URL as a secret."""),

    A(568, provider="gcp", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      user="on gcp, invoke('billing') needs some url or setting from me?",
      steps=[S("search_docs", query="invoke gcp authenticated https id token",
               docs=[D("docs/handlers.md", "invoke-calling-another-function", start="4. `gcp`:", end="4. `gcp`:")])],
      final="""No setting needed. On GCP, `invoke()` makes an authenticated HTTPS call to `https://<region>-<project>.cloudfunctions.net/<service>-<stage>-<name>` with an ID token from the metadata server [docs/handlers.md#invoke-calling-another-function].

Two things to keep in mind:
1. The calling function's service account must be allowed to invoke the target if the target uses `auth: iam`.
2. Locally it runs the other handler in-process, so test with `pskit invoke` without any GCP setup."""),

    A(569, provider="aws", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#event", "docs/handlers.md#record"],
      user="code: in an sqs handler, log queue arn, message id, attributes and event time",
      steps=[S("search_docs", query="event source time record attributes id",
               docs=[D("docs/handlers.md", "event", end="| `raw` |"),
                     D("docs/handlers.md", "record", end="| `source` |")])],
      final="""**In code**
```python
from __future__ import annotations


def worker(event, ctx):
    for record in event.records:
        ctx.logger.info("message", extra={
            "queue": record.source or event.source,
            "id": record.id,
            "attrs": record.attributes,
            "at": event.time.isoformat(),
        })
```
`event.source` / `record.source` is the queue identifier (the ARN on SQS), `record.id` the message id, `record.attributes` the message attributes, and `event.time` a UTC datetime (event time, or now if the platform doesn't give one) [docs/handlers.md#event] [docs/handlers.md#record]."""),

    A(570, provider="azure", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#environment-variables", "docs/handlers.md#context"],
      user="Our shared helper reads os.environ['PSKIT_FUNCTION'] to tag metrics. On Azure it seems to be missing. Is that expected?",
      steps=[S("search_docs", query="PSKIT_FUNCTION azure app settings",
               docs=[D("docs/handlers.md", "environment-variables", end="| `PSKIT_GCP_PROJECT` |")])],
      final="""Yes. `PSKIT_FUNCTION` and `PSKIT_HANDLER` aren't app settings on Azure, because all functions share one Function App; pskit passes them explicitly instead [docs/handlers.md#environment-variables].

Read the function name from the context, which works on every cloud:

**In code**
```python
from __future__ import annotations


def handler(event, ctx):
    tags = {"function": ctx.function, "stage": ctx.stage, "provider": ctx.provider}
    record_metric("calls", 1, tags)
    return {"ok": True}
```
Pass `ctx` (or `ctx.function`) to your helper instead of reading the environment [docs/handlers.md#context]. `record_metric` is your own function."""),
]
