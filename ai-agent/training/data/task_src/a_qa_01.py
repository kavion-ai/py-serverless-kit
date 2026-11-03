"""Category A (docs Q&A and how-to), batch 1. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(1, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule", "docs/studio.md#what-you-can-do"],
      user="how do i make my function run by itself every morning?",
      steps=[S("search_docs", query="schedule trigger cron every morning",
               docs=[D("docs/events.md", "schedule", words=200)])],
      final="""Give the function a `schedule` trigger with a cron expression. pskit uses standard 5-field cron and converts it for each cloud [docs/events.md#schedule].

**In studio**
1. Open **Functions** and click the function (or **+ Create function** for a new one).
2. In the **Triggers** step, under *Add a trigger*, pick the schedule trigger.
3. Use the cron editor, for example `0 7 * * *`. The plain-English preview should say every day at 07:00.
4. Click **Save**.

**In the terminal**
```bash
pskit validate
pskit invoke -f my-function -t schedule
```
`pskit invoke` runs the handler locally with a schedule event, so you can check it before deploying.

**In code**
```yaml
functions:
  my-function:
    handler: app.jobs.morning
    events:
      - schedule:
          cron: "0 7 * * *"
          timezone: Europe/Berlin   # default UTC
```
The handler gets `event.type == "schedule"`. Without a `timezone` the time is UTC."""),

    A(2, provider="cloudflare", stage="dev", mode="auto", page="Overview", persona="informal_non_native",
      sources=["docs/providers.md#cloudflare-workers", "docs/configuration.md#switch-something-off-on-one-cloud"],
      user="cloudflare can run my queue worker?? i use same yml like aws",
      steps=[S("search_docs", query="cloudflare workers queue trigger support",
               docs=[D("docs/providers.md", "cloudflare-workers", start="| Trigger |", words=120)]),
             S("search_docs", query="disable function on one provider",
               docs=[D("docs/configuration.md", "switch-something-off-on-one-cloud")])],
      final="""No. Cloudflare Workers in pskit only run `http` and `schedule` triggers, so a `queue` trigger fails `pskit validate` there [docs/providers.md#cloudflare-workers].

You have two options:
1. Keep the worker on a provider with queues: aws (SQS), gcp (Pub/Sub), azure (Storage Queue) or onprem.
2. Keep one pskit.yml and switch the worker off only on Cloudflare [docs/configuration.md#switch-something-off-on-one-cloud]:

```yaml
providers:
  cloudflare:
    functions:
      worker: {enabled: false}
```

Then `pskit validate -p cloudflare` shows it as a warning instead of an error, and your HTTP functions still deploy to Cloudflare."""),

    A(3, provider="aws", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      user="sqs trigger: max batch_size, max batch_window, dlq keys?",
      steps=[S("search_docs", query="queue batch_size batch_window dead_letter",
               docs=[D("docs/events.md", "queue", words=200)])],
      final="""From [docs/events.md#queue]:
- `batch_size`: 1-10000 (default 10)
- `batch_window`: 0-300 seconds
- DLQ: `dead_letter: <queue name>` plus `max_receive` (default 5), which becomes the SQS redrive policy

```yaml
events:
  - queue:
      name: jobs
      batch_size: 10
      batch_window: 5
      dead_letter: jobs-dlq
      max_receive: 5
```
Return a `BatchResult` so that only the failed messages are retried."""),

    A(4, provider="gcp", stage="dev", mode="ask", page="none", persona="pasted_error",
      sources=["docs/troubleshooting.md#configuration", "docs/configuration.md#variables"],
      user="Error: unresolved variables: env:DB_URL\n\ngot this from pskit validate",
      steps=[S("search_docs", query="unresolved variables env",
               docs=[D("docs/troubleshooting.md", "configuration", end="Set the variable, or give a default"),
                     D("docs/configuration.md", "variables", end="| `${opt:stage}`")])],
      final="""Your pskit.yml uses `${env:DB_URL}`, and `DB_URL` is not set in the environment where pskit runs. `${env:NAME}` without a default is an error when the variable is unset [docs/configuration.md#variables].

Fix it in one of two ways [docs/troubleshooting.md#configuration]:
1. Set the variable before you run pskit, e.g. `export DB_URL=...` in bash (`$env:DB_URL = "..."` in PowerShell), then run `pskit validate` again.
2. Give it a fallback for local work: `${env:DB_URL, postgres://localhost/dev}`.

If the URL holds a password, keep it in the environment (option 1). Don't write it into pskit.yml."""),

    A(5, provider="aws", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition"],
      user="In serverless.yml I had `events: - sqs: arn:...:orders-queue, batchSize: 10` on a queue that already exists. What's the pskit version of that?",
      steps=[S("search_docs", query="migrate serverless.yml sqs event batchSize existing queue",
               docs=[D("docs/migrating-from-aws.md", "step-2-translate-the-sam-serverless-cdk-definition")])],
      final="""Use a `queue` event with the queue's name and `existing: true`, so pskit uses your queue instead of creating one [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition]:

```yaml
functions:
  process-orders:
    handler: app.orders.process
    events:
      - queue: {name: orders-queue, batch_size: 10, existing: true}
```

Keep `existing: true` while the queue still belongs to your old stack. In the handler, the messages are in `event.records`, one `Record` per message. You don't parse the SQS event yourself."""),

    A(6, provider="onprem", stage="dev", mode="auto", page="Test", persona="beginner",
      sources=["docs/studio.md#test-functions", "docs/local-development.md#pskit-dev-local-server"],
      user="can i try my function before i deploy it anywhere?",
      steps=[S("search_docs", query="test function locally without deploy",
               docs=[D("docs/studio.md", "test-functions", end="**Run locally**"),
                     D("docs/local-development.md", "local-development", end="Only the cloud-specific adapter is skipped.")])],
      final="""Yes. Local runs need no cloud credentials and no Terraform [docs/local-development.md#local-development].

**In studio**
1. Open **Test**.
2. Pick the function and the event (one of its triggers, or **Direct invoke**).
3. Edit the payload. It starts from a sample for that trigger type.
4. Click **▶ Run locally**. The result and the logs appear below [docs/studio.md#test-functions].

**In the terminal**
```bash
pskit invoke -f hello
pskit dev
```
`pskit invoke` runs one function once. `pskit dev` starts a local server on http://127.0.0.1:3000 for your HTTP routes and reloads when you change code.

**In code**
```python
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, http_event

runner = LocalRunner(Project.load())

def test_hello():
    assert runner.invoke("hello", http_event("GET", "/hello")).status == 200
```"""),

    A(7, provider="azure", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/providers.md#azure-azure-functions"],
      user="We are moving our API from AWS to Azure. On AWS the gateway checked JWTs for /admin routes with auth: jwt. Does that work the same on Azure, and if not, what is the supported way to protect those routes?",
      steps=[S("search_docs", query="http auth jwt azure support",
               docs=[D("docs/events.md", "http", start="**Auth support**", end="Example of AWS JWT auth")])],
      final="""No. `auth: jwt` is AWS only. On Azure, `pskit validate` reports it as an error. Azure supports `auth: none` and `auth: key` (function key, `AuthLevel.FUNCTION`) [docs/events.md#http].

Your options on Azure:
1. **Function key**: set `auth: key` on the admin routes. Callers then need the function key.
2. **Check the token in the handler**: keep the route `auth: none` and validate the `Authorization` header in your code.

Keep the JWT setting on AWS and override only the Azure block, as `examples/02-rest-api` does. Lists are replaced, so restate the whole `events` list:

```yaml
providers:
  azure:
    functions:
      admin-stats:
        events: [{http: {path: /admin/stats, auth: key}}]
```"""),

    A(8, provider="gcp", stage="dev", mode="auto", page="none", persona="informal_non_native",
      sources=["docs/cli.md#pskit-providers", "docs/providers.md#providers"],
      user="which command show me all clouds and what each one support? only cli pls",
      steps=[S("search_docs", query="command list providers capabilities",
               docs=[D("docs/cli.md", "pskit-providers")])],
      final="""**In the terminal**
1. Print the capability matrix of the installed version:
```bash
pskit providers
```
2. For details (regions, runtimes, max timeout, Terraform provider, notes):
```bash
pskit providers --json
```
[docs/cli.md#pskit-providers]"""),

    A(9, provider="alibaba", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/configuration.md#provider"],
      user="if i dont write memory and timeout, what do i get?",
      steps=[S("search_docs", query="default memory timeout provider",
               docs=[D("docs/configuration.md", "provider", end="| `architecture`")])],
      final="""You get **256 MB** of memory and a **30 second** timeout [docs/configuration.md#provider].

Memory can be 64-32768 MB. Timeout can be 1-3600 seconds, and no more than your provider's own maximum (Alibaba allows up to 3600 s). Set them under `provider:` for every function, or on one function to override:

```yaml
provider:
  name: alibaba
  memory: 512
  timeout: 60
functions:
  report:
    handler: app.report.run
    timeout: 300
```"""),

    A(10, provider="tencent", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http", "docs/troubleshooting.md#provider-gotchas"],
      user="PATCH route on tencent ok?",
      steps=[S("search_docs", query="tencent http PATCH method",
               docs=[D("docs/events.md", "http", start="Provider notes:", end="Provider notes:")])],
      final="""No. Tencent's API Gateway has no `PATCH`, so `pskit validate -p tencent` fails on a PATCH route. Use `ANY` instead [docs/events.md#http]:

```yaml
- http: {method: ANY, path: "/orders/{id}"}
```
pskit's runtime still sees the real method in `event.http.method`, so check for `PATCH` in the handler. Also on Tencent, `{path+}` becomes a prefix route."""),

    A(11, provider="cloudflare", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/studio.md#setup-logs-and-provider-differences"],
      user="where i click to turn off one function only for cloudflare? studio only",
      steps=[S("search_docs", query="studio disable function on one provider",
               docs=[D("docs/studio.md", "setup-logs-and-provider-differences", start="- **Enable / disable**",
                       end="- **Enable / disable**")])],
      final="""**In studio**
1. In the top bar, under *validate & deploy as*, pick **Cloudflare**.
2. Open **Deploy**. It lists everything that won't run on Cloudflare and offers to disable it there.
3. Disable the function only for the current provider. Studio writes `providers.cloudflare...enabled: false` and keeps the function for the other clouds.
4. Click **Save**.

[docs/studio.md#setup-logs-and-provider-differences]"""),

    A(12, provider="oracle", stage="dev", mode="auto", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#configuration-reference-pskityml", "docs/configuration.md#functions"],
      user="Error: pskit.yml is invalid:\n  - functions.api.evnets: Extra inputs are not permitted",
      steps=[S("search_docs", query="Extra inputs are not permitted unknown key",
               docs=[D("docs/configuration.md", "configuration-reference-pskityml", end="Unknown keys are rejected")])],
      final="""It's a typo. `evnets` is not a pskit.yml key, and unknown keys are rejected so typos fail fast [docs/configuration.md#configuration-reference-pskityml]. Rename it to `events`:

```yaml
functions:
  api:
    handler: app.api.handler
    events:
      - http: GET /orders
```

Then run `pskit validate -p oracle` again. Oracle may report more problems after this one, such as its required options."""),

    A(13, provider="gcp", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      user="One of our functions has an HTTP route and a queue trigger. When we deploy to GCP, does it stay one Cloud Function? What names should we expect in the console?",
      steps=[S("search_docs", query="gcp function with http and queue trigger split",
               docs=[D("docs/events.md", "gcp-multi-trigger-functions-are-split-automatically")])],
      final="""It becomes more than one Cloud Function. A gen2 function has at most one event trigger and can't mix HTTP with events, so pskit splits it [docs/events.md#gcp-multi-trigger-functions-are-split-automatically]:

- `<name>`: the HTTP deployment
- `<name>-queue0`: the queue (Pub/Sub) trigger

They share the same code and handler. `pskit info` and the dashboard still show one function, and the extra deployment appears in its `extra` output. The event-triggered deployment is limited to a 540 s timeout."""),

    A(14, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#workflows-state-machines", "docs/studio.md#what-you-can-do"],
      user="how do I make a workflow that runs 3 of my functions one after another?",
      steps=[S("search_docs", query="workflow chain functions task states next",
               docs=[D("docs/workflows.md", "workflows-state-machines", end="- **locally**"),
                     D("docs/workflows.md", "state-types", end="| `choice`")])],
      final="""Make a workflow with three `task` states, each pointing to the next one. On AWS it runs as Step Functions [docs/workflows.md#workflows-state-machines].

**In studio**
1. Open **Workflows** and click **+ Create workflow**.
2. Use **Add state** three times and choose *task* each time.
3. For each state, pick its **Function** in the inspector, and set **Then** to the next state. The last one ends.
4. Click **Save**.

**In the terminal**
```bash
pskit validate
pskit workflow run my-flow -i '{"order_id": 1}' --history
```
`workflow run` executes it locally on the embedded engine.

**In code**
```yaml
workflows:
  my-flow:
    start_at: First
    states:
      First:  {type: task, function: step-one, next: Second}
      Second: {type: task, function: step-two, next: Third}
      Third:  {type: task, function: step-three, end: true}
```
Each function gets the state input in `event.data`, and its return value goes to the next state [docs/workflows.md#state-types]."""),

    A(15, provider="aws", stage="prod", mode="auto", page="Code", persona="aws_migrator",
      sources=["docs/troubleshooting.md#faq"],
      user="With Lambda I shipped my helper lib as a layer. Do I have to add py-serverless-kit to requirements.txt so the runtime is there?",
      steps=[S("search_docs", query="py-serverless-kit in requirements.txt runtime vendored",
               docs=[D("docs/troubleshooting.md", "faq", end="No. The runtime is vendored")])],
      final="""No. The pskit runtime is vendored into every bundle automatically, and `py-serverless-kit` lines in requirements.txt are stripped [docs/troubleshooting.md#faq].

Put only your own dependencies in requirements.txt. On AWS they are pip-installed into the zip as Linux wheels. If you still want an existing layer, add it with `functions.<fn>.options.layers`."""),

    A(16, provider="ibm", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#ibm-code-engine-functions"],
      user="ibm can do cron job? i need run every 1 hour",
      steps=[S("search_docs", query="ibm code engine schedule trigger",
               docs=[D("docs/providers.md", "ibm-code-engine-functions", start="**Limits:**")])],
      final="""No. On IBM Code Engine pskit supports HTTP only: no schedule, queue, storage or topic triggers [docs/providers.md#ibm-code-engine-functions]. A `schedule` trigger fails `pskit validate -p ibm`.

What you can do:
1. Run the hourly job on a provider that has schedules: aws, gcp, azure, alibaba, tencent, huawei, digitalocean, cloudflare or onprem (`- schedule: 1 hour`).
2. Keep the API on IBM and disable only that function there:
```yaml
providers:
  ibm:
    functions:
      hourly-job: {enabled: false}
```"""),

    A(17, provider="onprem", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/events.md#http"],
      user="yaml only: GET /users/{id} with cors limited to https://app.example.com",
      steps=[S("search_docs", query="http path parameter cors origins",
               docs=[D("docs/events.md", "http", words=210)])],
      final="""**In code**
```yaml
functions:
  get-user:
    handler: app.users.get
    events:
      - http:
          method: GET
          path: /users/{id}
          cors:
            origins: ["https://app.example.com"]
```
`{id}` lands in `event.http.path_params["id"]` [docs/events.md#http]."""),

    A(18, provider="digitalocean", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=["docs/providers.md#digitalocean-functions", "docs/troubleshooting.md#provider-gotchas"],
      user="what i need before i can deploy to digitalocean?",
      steps=[S("search_docs", query="digitalocean deploy requirements doctl namespace",
               docs=[D("docs/providers.md", "digitalocean-functions", start="- **Credentials:**", end="**Limits:**")])],
      final="""You need `doctl` installed and logged in, and your Functions namespace in pskit.yml [docs/providers.md#digitalocean-functions].

**In studio**
1. In the top bar, pick **DigitalOcean**.
2. Open **Setup & credentials**. It runs the same checks as `pskit doctor` and shows how to fix each problem.
3. In **Overview & provider**, fill in the provider option *namespace*.

**In the terminal**
```bash
doctl auth init
doctl serverless namespaces list
pskit doctor -p digitalocean
pskit validate -p digitalocean
```

**In code**
```yaml
provider:
  name: digitalocean
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE}
```
DigitalOcean runs HTTP and schedule triggers only."""),

    A(19, provider="azure", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/troubleshooting.md#http", "docs/handlers.md#errors"],
      user="In prod on Azure one route returns 500 and the body only has a request_id. How do we find the actual exception, and can we see the message when we run it locally?",
      steps=[S("search_docs", query="500 only request id exception details",
               docs=[D("docs/troubleshooting.md", "http", start="**500 with only a request id**",
                       end="set `PSKIT_DEBUG=1`")]),
             S("search_docs", query="pskit logs azure",
               docs=[D("docs/cli.md", "pskit-logs", end="Requirements per provider")])],
      final="""The 500 body hides the error on purpose. Search the provider's logs for that `request_id`. Locally, set `PSKIT_DEBUG=1` to include the exception text [docs/troubleshooting.md#http]. On Azure, pskit can read logs only when the deployment has a Log Analytics workspace [docs/cli.md#pskit-logs].

**In studio**
1. Open **Logs** with provider azure and stage prod in the top bar.
2. Filter by the function and look for the `request_id` from the response.

**In the terminal**
```bash
pskit logs --provider azure --stage prod --function my-api --level error
```
Locally, put `PSKIT_DEBUG=1` in `.env`, then run:
```bash
pskit invoke -f my-api
```

**In code**
Log the context you need before the failing call:
```python
ctx.logger.info("loading order", extra={"order_id": order_id})
```
Never set `PSKIT_DEBUG` in production."""),

    A(20, provider="huawei", stage="dev", mode="auto", page="Overview", persona="pasted_error",
      sources=["docs/providers.md#huawei-functiongraph"],
      user="ERROR: [provider.options] HTTP events need a dedicated API Gateway instance: set provider.options.apig_instance_id\nwhat is this id",
      steps=[S("search_docs", query="huawei apig_instance_id http events",
               docs=[D("docs/providers.md", "huawei-functiongraph", end="| topic |")])],
      final="""On Huawei FunctionGraph, pskit serves `http` events through a **dedicated API Gateway (APIG) instance**. `apig_instance_id` is the ID of that instance in your Huawei account [docs/providers.md#huawei-functiongraph].

**In studio**
1. Open **Overview & provider** with Huawei selected.
2. Fill in the provider option `apig_instance_id` and click **Save**.

**In code**
```yaml
provider:
  name: huawei
  options:
    apig_instance_id: ${env:HUAWEI_APIG_INSTANCE_ID}
```

**In the terminal**
```bash
pskit validate -p huawei
```
If you don't have a dedicated APIG instance, use only schedule, storage or topic triggers on Huawei."""),
]
