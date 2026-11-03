"""Category A (docs Q&A and how-to), batch 34: aws / gcp / azure. Resource usage guides and libraries, how
dependencies reach each cloud, <name>_env values, local .env vs deployed secrets, the dashboard (static vs live,
log sources per cloud, sharing, LAN access, JSON API, several clouds), migrating from Lambda (SAM cron, AWS SDK
calls, intrinsics, side-by-side stage, base64 bodies, the worked example). Hand-written; assembled by
tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


RU = "docs/resource-usage.md"
DB = "docs/dashboard.md"
MG = "docs/migrating-from-aws.md"

CONVERSATIONS = [
    A(651, provider="aws", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{RU}#using-resources-from-code-libraries-code-and-tests", "docs/cli.md#pskit-resources"],
      user="is there a guide made for my own jobs queue, with the library and code for my project? not the general docs",
      steps=[S("search_docs", query="guide for one resource how to use library code",
               docs=[D(RU, "using-resources-from-code-libraries-code-and-tests", end="pskit resources usage orders-db -p onprem > docs/orders-db.md")])],
      final="""Yes. Studio and the CLI generate the guide per resource, with your keys and provider filled in [docs/resource-usage.md#using-resources-from-code-libraries-code-and-tests].

**In studio**
1. Open **Resources**.
2. Click **How to use** on the `jobs` row. It shows the library, the pskit.yml, handler code and the tests.

**In the terminal**
```bash
pskit resources usage jobs
pskit resources usage jobs > docs/jobs.md
```
The second line saves it as Markdown."""),

    A(652, provider="azure", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=[f"{RU}#how-dependencies-reach-the-function"],
      user="on azure who install my requirements.txt? pskit on my pc or azure? i see oryx in deploy log",
      steps=[S("search_docs", query="how dependencies installed azure requirements",
               docs=[D(RU, "how-dependencies-reach-the-function", end="| azure |")])],
      final="""Azure does. On Azure your `requirements.txt` is installed by the remote (Oryx) build, so that's what you see in the log [docs/resource-usage.md#how-dependencies-reach-the-function]. Node.js `package.json` dependencies are installed by the remote build too.

Locally, still run `pip install -r requirements.txt` so `pskit invoke` and `pskit dev` can import them. Don't add `py_serverless_kit` itself; it is bundled with every deployment."""),

    A(653, provider="aws", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=[f"{RU}#how-dependencies-reach-the-function"],
      user="add py-serverless-kit to requirements.txt for the lambda build?",
      steps=[S("search_docs", query="py_serverless_kit bundled requirements",
               docs=[D(RU, "how-dependencies-reach-the-function")])],
      final="""No. `py_serverless_kit` (and `pskit` for Node.js) is bundled with every deployment; never add it yourself [docs/resource-usage.md#how-dependencies-reach-the-function].

On AWS, `pskit deploy` pip-installs the rest of `requirements.txt` into the zip as Linux wheels."""),

    A(654, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=[f"{RU}#queues-buckets-and-topics"],
      user="Our GCP service is in Node.js. Which npm packages do I use to publish to a queue, write to a bucket and publish to a topic?",
      steps=[S("search_docs", query="nodejs library gcp queue bucket topic publish",
               docs=[D(RU, "queues-buckets-and-topics", end="| azure |")])],
      final="""On GCP [docs/resource-usage.md#queues-buckets-and-topics]:

| Resource | npm package |
|---|---|
| queue | `@google-cloud/pubsub` |
| storage | `@google-cloud/storage` |
| topic | `@google-cloud/pubsub` |

A queue is also a Pub/Sub topic on GCP, which is why the package is the same. Add them to `package.json`; Cloud Build installs them on deploy. Consuming needs no library: a function with a trigger receives `event.records`."""),

    A(655, provider="azure", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=[f"{RU}#testing-checklist"],
      user="Before we deploy to Azure I want to unit-test the queue worker and the blob function on my laptop without any cloud. What are the exact commands?",
      steps=[S("search_docs", query="test consumer locally without cloud invoke queue storage",
               docs=[D(RU, "testing-checklist")])],
      final="""**In the terminal**
```bash
pskit invoke -f worker -t queue -d '[{"id": 1}]'
pskit invoke -f on-invoice -t storage -d '{"bucket": "b", "key": "in/a.csv"}'
```
Use your function names; `-d` is the fake event [docs/resource-usage.md#testing-checklist].

**In studio**
1. Open **Test** and pick the function and its trigger.
2. Edit the payload and click **▶ Run locally**.

After deploying, `pskit resources send <key> -d '{...}'` sends a real message or object, and `pskit logs -f --function worker` shows the run."""),

    A(656, provider="aws", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{RU}#the-five-steps-for-any-resource", "docs/resources.md#secrets"],
      user="in the resource there is password_env: DB_PASSWORD. do i put my password there?",
      steps=[S("search_docs", query="password_env name of variable resource connection",
               docs=[D(RU, "the-five-steps-for-any-resource", start="3. **Read** it in the handler", end="`ctx.env[r[\"password_env\"]]`.")])],
      final="""No. A `<name>_env` value is the **name** of an environment variable, not the password [docs/resource-usage.md#the-five-steps-for-any-resource].

**In code**
```yaml
provider:
  environment:
    DB_PASSWORD: ${env:DB_PASSWORD}
resources:
  orders-db:
    type: database
    external: true
    connection:
      host: db.example.com
      password_env: DB_PASSWORD
```
```python
db_pw = ctx.env[resource("orders-db")["password_env"]]
```
Set `DB_PASSWORD` in the shell that runs `pskit deploy`; pskit reads it from there."""),

    A(657, provider="gcp", stage="staging", mode="ask", page="Setup", persona="informal_non_native",
      sources=[f"{RU}#secrets"],
      user="i have .env file with API_KEY for local. when i deploy to gcp, is .env uploaded too?",
      steps=[S("search_docs", query="env file local runs secrets deployed clouds",
               docs=[D(RU, "secrets")])],
      final="""No. `.env` is loaded only by local runs (`pskit invoke` and `pskit dev`). For a cloud, declare the variable in pskit.yml; `${env:...}` is resolved when you deploy [docs/resource-usage.md#secrets].

**In code**
```yaml
provider:
  environment:
    API_KEY: ${env:API_KEY}
```

**In the terminal**
```bash
export API_KEY='<value>'
pskit deploy -s staging
```
The handler reads it with `ctx.env["API_KEY"]` both locally and on GCP."""),

    A(658, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=[f"{DB}#dashboard", "docs/cli.md#pskit-dashboard"],
      user="i opened .pskit/dashboard/index.html and the Executions tab says live data needs something. how to see my step functions runs there",
      steps=[S("search_docs", query="dashboard executions tab live data serve",
               docs=[D(DB, "dashboard", end="The **Executions** and **Logs** tabs in a static page")])],
      final="""The file is the static page; it only shows what was deployed. Executions and logs need the live dashboard [docs/dashboard.md#dashboard].

**In the terminal**
```bash
pip install "py-serverless-kit[aws]"
pskit dashboard --serve --open
```
It runs on http://127.0.0.1:8765/ and uses your local AWS credentials. The Executions tab then lists, starts, follows and cancels Step Functions runs."""),

    A(659, provider="gcp", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{DB}#log-sources"],
      user="dashboard --serve, Logs tab for gcp-dev says it can't read logs. what does it need?",
      steps=[S("search_docs", query="dashboard logs gcp needs",
               docs=[D(DB, "log-sources", end="| Azure |")])],
      final="""For GCP the live dashboard reads the function's Cloud Logging entries, and that needs two things on your machine [docs/dashboard.md#log-sources]:

**In the terminal**
```bash
pip install google-cloud-logging
gcloud auth application-default login
pskit dashboard --serve
```
GCP logs are read-only there: deleting isn't available, so set retention on the log bucket instead."""),

    A(660, provider="azure", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=[f"{DB}#log-sources"],
      user="We'd like to see our Azure function logs in pskit's live dashboard. What has to be set up?",
      steps=[S("search_docs", query="dashboard azure logs log analytics workspace",
               docs=[D(DB, "log-sources", end="| Others |")])],
      final="""On Azure the dashboard reads `AppTraces` from Log Analytics. It needs [docs/dashboard.md#log-sources]:

1. A Terraform output named `log_analytics_workspace_id`, added with `provider.terraform.extra`.
2. On your machine:
```bash
pip install azure-monitor-query azure-identity
az login
pskit dashboard --serve
```
Logs are read-only there; retention is set on the workspace. The same applies to the studio **Logs** page, which works on Azure with a Log Analytics workspace."""),

    A(661, provider="aws", stage="staging", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{DB}#where-the-data-comes-from"],
      user="Our deploys run in CI, so the .pskit folder on my laptop doesn't know about them. How can the team see the deployed URLs and functions?",
      steps=[S("search_docs", query="share dashboard ci artifact",
               docs=[D(DB, "where-the-data-comes-from", start="Because `.pskit/` is git-ignored", end="The page contains resource names")])],
      final="""Each machine has its own `.pskit/` records, so share the page CI generates [docs/dashboard.md#where-the-data-comes-from]:

1. Upload `.pskit/dashboard/index.html` from the CI job as a build artifact (`examples/15-ci-cd-deploy` does this).
2. Or publish it to a private static site or bucket.

The page contains resource names, URLs and ids, so keep it internal. In CI, `pskit info --json` prints the same record if a later step needs it."""),

    A(662, provider="gcp", stage="dev", mode="ask", page="none", persona="informal_non_native",
      sources=[f"{DB}#security"],
      user="can i run dashboard --serve with host 0.0.0.0 so my team see it on our network?",
      steps=[S("search_docs", query="dashboard host 0.0.0.0 security",
               docs=[D(DB, "security")])],
      final="""You can, but pskit prints a warning: anyone who can reach the port can read logs and start or cancel workflow runs, and it has no login [docs/dashboard.md#security].

```bash
pskit dashboard --serve --host 0.0.0.0 --port 8765
```
Only do this behind your own authentication (for example a reverse proxy with login). Your cloud credentials stay on the server; they never reach the browser."""),

    A(663, provider="aws", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=[f"{DB}#live-mode"],
      user="script against the live dashboard api: list failed runs of order-pipeline on aws-prod",
      steps=[S("search_docs", query="dashboard api executions workflow status",
               docs=[D(DB, "live-mode", end="| `POST /api/deployments/<key>/executions/<id>/cancel?workflow=` | cancel a run |")])],
      final="""With `pskit dashboard --serve` running, the deployment key is `aws-prod` [docs/dashboard.md#live-mode]:

```bash
curl 'http://127.0.0.1:8765/api/deployments/aws-prod/executions?workflow=order-pipeline&status=FAILED&limit=20'
```
It returns `{"items", "total", "next_token", "supported", "reason"}`; pass `token=` with `next_token` for the next page. One run with its history: `GET /api/deployments/aws-prod/executions/<id>?workflow=order-pipeline`.

Without the server, `pskit workflow executions` does the same from the CLI."""),

    A(664, provider="azure", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=[f"{DB}#where-the-data-comes-from"],
      user="i deployed same project to aws and azure. one dashboard show both or two?",
      steps=[S("search_docs", query="dashboard several providers stages one page",
               docs=[D(DB, "where-the-data-comes-from", end="It includes `key` and `resources`")])],
      final="""One. Each deploy writes `.pskit/<provider>-<stage>/deployment.json`, and the dashboard reads all of them, so `aws-dev` and `azure-dev` appear on the same page [docs/dashboard.md#where-the-data-comes-from].

```bash
pskit dashboard --open
```
Only deploys made from this machine are included."""),

    A(665, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{MG}#step-2-translate-the-sam-serverless-cdk-definition"],
      user="SAM has Schedule: cron(0 12 * * ? *) on our report function. What's that in pskit.yml?",
      steps=[S("search_docs", query="sam schedule cron translate",
               docs=[D(MG, "step-2-translate-the-sam-serverless-cdk-definition", end="| `Type: SQS`, `BatchSize: 10` |")])],
      final="""pskit uses standard 5-field cron, without the `?` and the year field [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition].

**In code**
```yaml
functions:
  report:
    handler: app.report.run
    events:
      - schedule: "0 12 * * *"
```
Quote the string. `rate(5 minutes)` becomes `- schedule: 5 minutes`."""),

    A(666, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=[f"{MG}#step-1-separate-business-logic-from-aws-event-parsing"],
      user="Our Lambdas call DynamoDB with boto3 everywhere. Do I have to rewrite those calls for pskit?",
      steps=[S("search_docs", query="aws sdk calls dynamodb migrating",
               docs=[D(MG, "step-1-separate-business-logic-from-aws-event-parsing", start="Calls to other AWS services")])],
      final="""No. Calls to other AWS services stay as they are; you only rewrite the event parsing and the return value [docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing].

They do tie those functions to AWS. If you plan to move clouds, put them behind a small interface of your own (for example an `OrdersStore` class), so only that class changes later. Grant the DynamoDB actions under `provider.iam.statements`."""),

    A(667, provider="aws", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=[f"{MG}#step-3-translate-step-functions"],
      user="Our ASL uses Parameters with States.Format and a ResultSelector. Can I keep those in a pskit workflow?",
      steps=[S("search_docs", query="step functions parameters intrinsic functions resultselector",
               docs=[D(MG, "step-3-translate-step-functions")])],
      final="""No. `Parameters`, `ResultSelector` and intrinsic functions aren't supported [docs/migrating-from-aws.md#step-3-translate-step-functions].

Instead:
1. Move that shaping into a small task function (for example `format-message`) and put it as a task state before the one that needs it.
2. Check the result locally and compare with your old ASL:
```bash
pskit workflow run order-pipeline -i @events/order.json --history
pskit workflow show order-pipeline --format asl
```
Error names in `Retry` / `Catch` become your Python exception class names."""),

    A(668, provider="aws", stage="dev", mode="ask", page="Deploy", persona="aws_migrator",
      sources=[f"{MG}#step-4-deploy-to-aws-side-by-side"],
      user="We can't cut over in one go. How do I run the pskit version next to our old SAM stack first?",
      steps=[S("search_docs", query="deploy side by side old stack migration stage",
               docs=[D(MG, "step-4-deploy-to-aws-side-by-side")])],
      final="""Deploy it as its own stage and run both stacks in parallel [docs/migrating-from-aws.md#step-4-deploy-to-aws-side-by-side].

**In the terminal**
```bash
pskit deploy --stage migration
pskit info --stage migration
```

**In studio**
1. Type `migration` as the stage in the top bar.
2. Open **Deploy** and click **Deploy**, then **Info** for the new endpoints and ARNs.

Then switch traffic (DNS, API mapping or event source) and remove the old stack. While the old stack still owns queues, buckets and topics, mark them `existing: true` in pskit."""),

    A(669, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=[f"{MG}#step-1-separate-business-logic-from-aws-event-parsing"],
      user="our lambda checks isBase64Encoded and decodes the body for file uploads. how is that in pskit?",
      steps=[S("search_docs", query="isBase64Encoded body lambda pskit",
               docs=[D(MG, "step-1-separate-business-logic-from-aws-event-parsing", start="| Lambda | pskit |", end="| `event[\"queryStringParameters\"]` |")])],
      final="""You don't decode it yourself. pskit gives you the body ready to use [docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing]:

- `event.http.body`: the raw body
- `event.http.text()`: the body as text
- `event.http.json()`: parsed JSON

**In code**
```python
from __future__ import annotations


def upload(event, ctx):
    data = event.http.body
    return {"size": len(data)}
```"""),

    A(670, provider="aws", stage="dev", mode="ask", page="none", persona="beginner",
      sources=[f"{MG}#migrating-from-aws-lambda-and-step-functions"],
      user="is there an example that shows a lambda before and after moving to pskit?",
      steps=[S("search_docs", query="migrate example before after lambda",
               docs=[D(MG, "migrating-from-aws-lambda-and-step-functions", end="and `after/` holds the pskit version.")])],
      final="""Yes: `examples/13-migrate-from-aws-lambda`. `before/` has a raw Lambda, a SAM template and an ASL file; `after/` has the pskit version [docs/migrating-from-aws.md#migrating-from-aws-lambda-and-step-functions].

**In the terminal**
```bash
cd examples/13-migrate-from-aws-lambda/after
pskit validate
```
The guide walks through it in five steps: event parsing, the SAM definition, Step Functions, a side-by-side deploy, then another cloud."""),
]
