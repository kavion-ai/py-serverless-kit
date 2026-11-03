"""Category A (docs Q&A and how-to), batch 38: aws / gcp / azure. Scenarios (verify an HTTP API, external queue
plan, managed queue grants, default stage), escape hatches (X-Ray tracing), stage overrides, hooks around remove,
kept resources on Azure, CLI flags (deploy --confirm / --no-dashboard, logs -q / --source invocation, tf state list,
validate in CI), config file names, event shorthands, resource-backed events, ${opt:stage} and ${file(...)}.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


SC = "docs/scenarios.md"
CF = "docs/configuration.md"
CL = "docs/cli.md"

CONVERSATIONS = [
    A(731, provider="aws", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{SC}#a-http-api-on-aws"],
      user="i deployed my orders api with GET /orders/{id} and POST /orders. how do i check it really works now?",
      steps=[S("search_docs", query="verify http api after deploy aws",
               docs=[D(SC, "a-http-api-on-aws", start="```bash", end="**Verify:**")])],
      final="""**In the terminal**
```bash
pskit info
curl https://<api-id>.execute-api.eu-west-1.amazonaws.com/orders/1
```
`pskit info` lists both routes with their URLs; use the one it prints. A missing id should return `404 {"error": ...}` if your handler raises `NotFound` [docs/scenarios.md#a-http-api-on-aws].

**In studio**
1. Open **Test** with aws / dev in the top bar.
2. Pick `get-order` and its HTTP trigger, set the path to `/orders/1`.
3. Click **☁ Send to aws / dev**."""),

    A(732, provider="aws", stage="prod", mode="ask", page="Deploy", persona="terse_expert",
      sources=[f"{CL}#pskit-deploy"],
      user="deploy should apply exactly the reviewed plan, no auto-approve",
      steps=[S("search_docs", query="deploy confirm plan apply",
               docs=[D(CL, "pskit-deploy")])],
      final="""**In the terminal**
```bash
pskit deploy -s prod --confirm
```
`--confirm` runs `terraform plan -out tfplan`, then applies that plan instead of `-auto-approve` [docs/cli.md#pskit-deploy]. To only look first, `pskit plan -s prod`."""),

    A(733, provider="aws", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{SC}#c-attach-an-existing-queue-or-bucket"],
      user="Before the first deploy I want proof that pskit won't create a second SQS queue or S3 bucket next to our existing external ones. How do I check?",
      steps=[S("search_docs", query="external queue bucket plan no new resources",
               docs=[D(SC, "c-attach-an-existing-queue-or-bucket", start="Without `connection.arn`")])],
      final="""Run a plan. For external resources it shows only the event source mapping / bucket notification: no `aws_sqs_queue` or `aws_s3_bucket` is created [docs/scenarios.md#c-attach-an-existing-queue-or-bucket].

**In the terminal**
```bash
pskit plan
```

**In studio**
1. Open **Deploy**.
2. Click **Plan** and read the live log for `aws_sqs_queue` / `aws_s3_bucket`.

If one shows up, the resource isn't marked `external: true`."""),

    A(734, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{CF}#escape-hatches"],
      user="In SAM we had Tracing: Active on create-order. pskit has no tracing key. How do I turn on X-Ray?",
      steps=[S("search_docs", query="lambda argument not modelled tracing escape hatch",
               docs=[D(CF, "escape-hatches", end="| Reference those resources |")])],
      final="""Use the escape hatch `functions.<fn>.options`: it is merged into the `aws_lambda_function` resource [docs/configuration.md#escape-hatches].

**In code**
```yaml
functions:
  create-order:
    handler: app.orders.create
    options:
      tracing_config: {mode: Active}
```

**In studio**
1. Open **Functions** and click `create-order`.
2. Under *Provider-specific options*, add `tracing_config` with `{mode: Active}`, then click **Save**."""),

    A(735, provider="azure", stage="prod", mode="ask", page="YAML", persona="informal_non_native",
      sources=[f"{CF}#stages-per-stage-overrides"],
      user="yaml only: in prod LOG_LEVEL WARNING and memory 1024, dev stay like now",
      steps=[S("search_docs", query="per stage overrides environment memory prod",
               docs=[D(CF, "stages-per-stage-overrides")])],
      final="""**In code**
```yaml
stages:
  prod:
    provider:
      memory: 1024
      environment:
        LOG_LEVEL: WARNING
```
Only `pskit deploy -s prod` uses these; other stages keep the base values [docs/configuration.md#stages-per-stage-overrides]. On Azure `environment` is app-wide, so it applies to every function."""),

    A(736, provider="gcp", stage="staging", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{CF}#hooks"],
      user="Before anyone removes the GCP staging stage, a script should export the test data to a file. If the export fails, the remove must not run. Can pskit do that?",
      steps=[S("search_docs", query="hooks before remove abort",
               docs=[D(CF, "hooks")])],
      final="""Yes, with a `before_remove` hook. A non-zero exit aborts the command [docs/configuration.md#hooks].

**In code**
```yaml
hooks:
  before_remove: ["python scripts/export_data.py"]
```
Hooks run through the shell in the project root with `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and `PSKIT_WORK_DIR` set, so the script can check `PSKIT_STAGE` and only export for `staging`.

**In the terminal**
```bash
pskit remove -s staging
```"""),

    A(737, provider="azure", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{CL}#pskit-remove"],
      user="If I remove our Azure dev stage with --keep-resources, what exactly survives besides the queues and containers?",
      steps=[S("search_docs", query="remove keep resources azure kept storage account",
               docs=[D(CL, "pskit-remove", start="With `--keep-resources`")])],
      final="""On Azure the storage account, Service Bus namespace and resource group that hold the kept queues, containers or topics are kept as well [docs/cli.md#pskit-remove]. Functions, triggers and gateways are destroyed, and the code-upload bucket is not kept.

The kept resources leave the Terraform state, so pskit no longer manages them. They are remembered in `.pskit/azure-dev/kept/`, so you can delete them later:
```bash
pskit remove -s dev --keep-resources
pskit resources list -s dev
pskit resources delete --all-kept -s dev --yes
```"""),

    A(738, provider="aws", stage="prod", mode="ask", page="Logs", persona="terse_expert",
      sources=[f"{CL}#pskit-logs"],
      user="logs of api in prod containing order-4711, last 500",
      steps=[S("search_docs", query="pskit logs grep text lines",
               docs=[D(CL, "pskit-logs", start="| `-n, --lines`", end="| `-q, --grep TEXT` |")])],
      final="""**In the terminal**
```bash
pskit logs -s prod --function api -q order-4711 -n 500
```
`-q` matches case-insensitively; on AWS it becomes a CloudWatch filter pattern [docs/cli.md#pskit-logs]."""),

    A(739, provider="aws", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=[f"{CL}#pskit-logs"],
      user="I want the durations of recent invocations of our prod Lambdas as numbers I can pipe into a script. Is there a machine-readable form of pskit logs?",
      steps=[S("search_docs", query="pskit logs json invocation duration",
               docs=[D(CL, "pskit-logs", start="```bash", end="`-f` polls every 3 seconds on clouds.")])],
      final="""Yes: `--json` prints one JSON object per line, and `--source invocation` keeps only the invocation entries (Lambda `START` / `END` / `REPORT` lines) [docs/cli.md#pskit-logs].

**In the terminal**
```bash
pskit logs --stage prod --source invocation --json | jq .fields.duration_ms
```
Add `--function <name>` for one function, and `-n 500` for more entries."""),

    A(740, provider="gcp", stage="dev", mode="ask", page="none", persona="detailed_spec",
      sources=[f"{CL}#pskit-validate"],
      user="We want CI to fail the merge request when pskit.yml has a problem for GCP. Does pskit validate set an exit code, and do warnings fail it too?",
      steps=[S("search_docs", query="pskit validate exit code errors warnings",
               docs=[D(CL, "pskit-validate")])],
      final="""`pskit validate` prints errors and warnings and exits 1 on **errors**; warnings alone don't fail it [docs/cli.md#pskit-validate].

**In the terminal** (CI step)
```bash
pskit validate --provider gcp --stage dev
```
It needs no cloud credentials or Terraform. Run one line per provider you deploy to."""),

    A(741, provider="azure", stage="dev", mode="ask", page="Deploy", persona="terse_expert",
      sources=[f"{CL}#pskit-tf----args"],
      user="list every terraform resource in the azure dev state",
      steps=[S("search_docs", query="pskit tf state list",
               docs=[D(CL, "pskit-tf----args")])],
      final="""**In the terminal**
```bash
pskit tf -p azure -s dev -- state list
```
`pskit tf -- ARGS` runs any Terraform command in the generated workspace, after `package` or `deploy` [docs/cli.md#pskit-tf----args]."""),

    A(742, provider="aws", stage="staging", mode="ask", page="Deploy", persona="terse_expert",
      sources=[f"{CL}#pskit-deploy"],
      user="ci deploy: skip regenerating the html dashboard",
      steps=[S("search_docs", query="deploy no dashboard flag",
               docs=[D(CL, "pskit-deploy", start="| `--no-dashboard` |", end="| `--no-dashboard` |")])],
      final="""**In the terminal**
```bash
pskit deploy -s staging --no-dashboard
```
`--no-dashboard` doesn't regenerate `.pskit/dashboard/index.html` [docs/cli.md#pskit-deploy]. `pskit info --json` still gives the deployed record."""),

    A(743, provider="gcp", stage="dev", mode="ask", page="none", persona="informal_non_native",
      sources=[f"{CL}#common-project-options"],
      user="my old project file is named serverless_kit.yml not pskit.yml. pskit find it or must rename?",
      steps=[S("search_docs", query="config file names default",
               docs=[D(CL, "common-project-options", end="| `-c, --config FILE` |")])],
      final="""pskit finds it. The default config names are `pskit.yml`, `pskit.yaml`, `serverless_kit.yml` and `serverless_kit.yaml` [docs/cli.md#common-project-options]. For any other name use `-c`:

```bash
pskit validate -c my-config.yml
```"""),

    A(744, provider="azure", stage="prod", mode="ask", page="Overview", persona="beginner",
      sources=[f"{CL}#pskit-validate"],
      user="what does pskit validate check? does it talk to azure?",
      steps=[S("search_docs", query="pskit validate what it checks",
               docs=[D(CL, "pskit-validate")])],
      final="""It checks the config for the selected provider: the schema, triggers and options the provider can't run, the runtime, timeouts, required provider options, and that handler modules exist [docs/cli.md#pskit-validate]. It doesn't call Azure.

**In the terminal**
```bash
pskit validate --provider azure --stage prod
```

**In studio**
The same checks run as you type; see the Problems button in the top bar, or click **Validate**."""),

    A(745, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#events-triggers"],
      user="shortest yaml for http POST /jobs + every 15 min + sqs jobs queue on one fn",
      steps=[S("search_docs", query="event shorthand single-key mapping",
               docs=[D("docs/events.md", "events-triggers", end="A function with no events is *invoke-only*")])],
      final="""**In code**
```yaml
functions:
  worker:
    handler: app.jobs.process
    events:
      - http: POST /jobs
      - schedule: 15 minutes
      - queue: jobs
```
Each entry is a single-key mapping; the key is the trigger type [docs/events.md#events-triggers]. Use the long form when you need options like `batch_size`."""),

    A(746, provider="gcp", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/resources.md#using-a-resource-from-an-event"],
      user="validate fails after i wrote - queue: {resource: uploads}. uploads is my storage resource. i want the function on new files",
      steps=[S("search_docs", query="event resource different type validation",
               docs=[D("docs/resources.md", "using-a-resource-from-an-event")])],
      final="""The event type must match the resource type. Validation fails if the resource has a different `type` [docs/resources.md#using-a-resource-from-an-event]. For new files in a bucket, use a `storage` event:

**In code**
```yaml
events:
  - storage: {resource: uploads, events: [created]}
```

**In the terminal**
```bash
pskit validate -p gcp
```"""),

    A(747, provider="gcp", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{CF}#variables"],
      user="Our managed GCS bucket name must contain the stage (acme-exports-dev, acme-exports-prod) because names are global. How do I write that once?",
      steps=[S("search_docs", query="variables opt stage in names",
               docs=[D(CF, "variables", end="When a value is exactly one variable")])],
      final="""Use `${opt:stage}`: it resolves to the effective stage from the CLI [docs/configuration.md#variables].

**In code**
```yaml
resources:
  exports:
    type: storage
    name: acme-exports-${opt:stage}
```
`pskit deploy -s prod` then uses `acme-exports-prod`."""),

    A(748, provider="aws", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{SC}#b-queue-worker-with-a-managed-queue"],
      user="pskit make my jobs sqs queue. my enqueue function send to it. do i need write iam permission for that?",
      steps=[S("search_docs", query="managed queue send permission enqueue role",
               docs=[D(SC, "b-queue-worker-with-a-managed-queue", start="pskit gives the `enqueue` role", end="pskit gives the `enqueue` role")])],
      final="""No. For a managed (or external) queue resource, pskit gives the function's role `sqs:SendMessage` on that queue automatically [docs/scenarios.md#b-queue-worker-with-a-managed-queue].

In the handler, send with boto3 to `resource("jobs").url`. Only services that aren't buckets, queues or topics (DynamoDB, Secrets Manager, ...) need `iam.statements`."""),

    A(749, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=[f"{SC}#h-stages-and-several-clouds", f"{CF}#provider"],
      user="if i run pskit deploy without -s, which stage it use?",
      steps=[S("search_docs", query="default stage deploy without stage",
               docs=[D(CF, "provider", start="| `stage` |", end="| `stage` |")])],
      final="""`provider.stage` from pskit.yml, which defaults to `dev` [docs/configuration.md#provider]. Pass `-s prod` (or `--stage prod`) for another stage; each one has its own state and resources."""),

    A(750, provider="azure", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{CF}#variables"],
      user="Our company keeps the standard Azure tags in a shared tags.json file. Can pskit.yml load that file instead of repeating the tags?",
      steps=[S("search_docs", query="variables file json load",
               docs=[D(CF, "variables", end="When a value is exactly one variable")])],
      final="""Yes, with `${file(path.json)}`: the path is relative to the config, and `.json` / `.yml` files are parsed [docs/configuration.md#variables].

**In code**
```yaml
provider:
  name: azure
  tags: ${file(tags.json)}
```
Because the value is exactly one variable, it stays a mapping."""),
]
