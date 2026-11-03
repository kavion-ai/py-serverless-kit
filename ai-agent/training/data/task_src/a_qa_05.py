"""Category A (docs Q&A and how-to), batch 5: workflows and executions, e-mail triggers, overrides / stages /
extends / variables, hooks, migration and architecture. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(81, provider="aws", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#retry-and-catch"],
      user="The Charge step of our order workflow sometimes raises TimeoutError. It should retry 3 times with growing pauses, and if it still fails, go to a HandleError step that stores the error. How is that expressed?",
      steps=[S("search_docs", query="workflow retry backoff catch error state",
               docs=[D("docs/workflows.md", "retry-and-catch")])],
      final="""Give the task state a `retry` rule for `TimeoutError` and a `catch` rule that routes to `HandleError`. Error names are the Python exception class names your handler raises [docs/workflows.md#retry-and-catch].

**In code**
```yaml
workflows:
  order-pipeline:
    start_at: Charge
    states:
      Charge:
        type: task
        function: charge
        retry:
          - {errors: [TimeoutError], max_attempts: 3, interval_seconds: 1, backoff_rate: 2.0}
        catch:
          - {errors: ["*"], next: HandleError, result_path: "$.error"}
        end: true
      HandleError: {type: task, function: handle-error, end: true}
```
The pauses are 1 s, 2 s, 4 s. After the retries run out, the catcher stores `{"error", "cause"}` at `$.error` and moves on to `HandleError`.

**In studio**
1. Open **Workflows**, open the workflow and click the `Charge` state.
2. Under *Retry*, click **+ retry rule** and set the errors to `TimeoutError`, 3 attempts, interval 1, backoff 2.
3. Under *Catch*, click **+ catch rule** and pick `HandleError`.
4. Click **Save**.

**In the terminal**
```bash
pskit workflow run order-pipeline -i '{"order_id": 1}' --history
```
`--history` shows each attempt and where the run went."""),

    A(82, provider="gcp", stage="prod", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#compiler-notes-and-limits"],
      user="gcp workflows: two retry rules on one task, and retry on a parallel state. both honoured?",
      steps=[S("search_docs", query="gcp cloud workflows retry rules limits",
               docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="- **GCP:**", end="Task HTTP timeouts are capped at 1800 s.")])],
      final="""No to both. On Cloud Workflows [docs/workflows.md#compiler-notes-and-limits]:
- Only the **first** retry rule of a task is used, because Cloud Workflows allows one retry policy.
- `retry` / `catch` work on `task` states only. On `parallel` / `map` they're ignored, with a warning.
- Task HTTP timeouts are capped at 1800 s.

Workarounds: merge the two rules into one (list both error names in `errors`), and move the retry from the parallel state onto the task states inside its branches. Run `pskit workflow show <name> --format gcp` to see what gets deployed."""),

    A(83, provider="azure", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#compiler-notes-and-limits", "docs/workflows.md#engines"],
      user="We use engine: native on Azure. A workflow with a 5-minute report step fails. The caller gets no answer after about two minutes. What limits apply?",
      steps=[S("search_docs", query="azure logic apps workflow timeout two minutes",
               docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="- **Azure (Logic Apps):**", words=400)])],
      final="""Two Logic Apps limits hit you here [docs/workflows.md#compiler-notes-and-limits]:
1. A synchronous `Response` must come within about 2 minutes. For long workflows, set `options.sync: false`.
2. Task calls time out after 120 s, the Logic Apps limit for outbound HTTP. A 5-minute task can't run as one native task call, and `pskit validate` warns when a task function's timeout is longer.

**In code**
```yaml
workflows:
  monthly-report:
    engine: native
    options: {sync: false}
```

For the 5-minute step itself:
- Split it into steps that each finish within 120 s, or
- Use `engine: embedded`. The whole run then happens inside one orchestrator function and must fit within Azure's function timeout (600 s).

**In the terminal**
```bash
pskit validate -p azure -s staging
```
Check the warnings about task timeouts after the change."""),

    A(84, provider="alibaba", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#engines", "docs/workflows.md#embedded-orchestrator"],
      user="alibaba has no step functions. so where does my workflow run there?",
      steps=[S("search_docs", query="workflow engine alibaba embedded orchestrator",
               docs=[D("docs/workflows.md", "engines", end="calls task handlers **in-process** (same bundle) |"),
                     D("docs/workflows.md", "embedded-orchestrator", start="- The **whole run must fit in one function invocation**",
                       end="`pskit validate` warns about this.")])],
      final="""It runs on pskit's **embedded** engine. pskit adds one extra function, `<workflow>-orchestrator`, which runs the state machine and calls your task handlers in-process, from the same bundle [docs/workflows.md#engines].

Things to know:
- The whole run must fit in one function invocation: total time within the provider's max timeout. Long `wait` states don't fit, and `pskit validate` warns about this [docs/workflows.md#embedded-orchestrator].
- `engine: native` is an error on Alibaba. Leave `engine` at `auto` or set `embedded`.
- You start it with `POST /workflows/<workflow>`, or by invoking the orchestrator.

**In the terminal**
```bash
pskit validate -p alibaba
pskit workflow run my-flow -i '{"id": 1}'
```

**In studio**
1. Open **Workflows** and open the workflow.
2. Under *Settings*, set *Engine* to auto or embedded and click **Save**."""),

    A(85, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#commands"],
      user="on my server many workflow running. which command show me the stuck one and stop it?",
      steps=[S("search_docs", query="list running workflow executions cancel",
               docs=[D("docs/workflows.md", "commands", start="Deployed workflows:", words=300)])],
      final="""**In the terminal**
1. List the running ones:
```bash
pskit workflow executions order-pipeline --status RUNNING -s prod
```
2. See where one is stuck (its current state and history):
```bash
pskit workflow status <execution_id> --history -s prod
```
3. Stop it:
```bash
pskit workflow cancel <execution_id> -s prod
```
[docs/workflows.md#commands]"""),

    A(86, provider="onprem", stage="dev", mode="auto", page="Workflows", persona="pasted_error",
      sources=["docs/workflow-executions.md#on-premises-over-http"],
      user="after upgrade, POST /workflows/ping on-prem returns {\"execution_id\": \"019a...\", \"status\": \"RUNNING\", ...} and no output. our client expects output",
      steps=[S("search_docs", query="on-prem workflow http returns RUNNING no output wait",
               docs=[D("docs/workflow-executions.md", "on-premises-over-http", start="To wait for the result instead", words=300)])],
      final="""That's an intended change. On premises, `POST /workflows/<name>` now starts the run in the background and answers with the `execution_id` at once. Clients that expect `output` must ask to wait [docs/workflow-executions.md#on-premises-over-http].

Use any one of these:
- `?wait=true` on the URL: `POST /workflows/ping?wait=true`
- the header `Prefer: wait`
- the header `x-pskit-wait: true`

A waiting run answers `200` with `output`, or `500` with `error` and `cause` when it fails. Every run is still recorded, so you can look it up later with `pskit workflow status <execution_id>`."""),

    A(87, provider="aws", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#migrating-step-functions-asl"],
      user="Our Step Functions definition uses ResultSelector, OutputPath and States.Format. Can I translate that to a pskit workflow?",
      steps=[S("search_docs", query="migrate step functions asl ResultSelector intrinsic",
               docs=[D("docs/workflows.md", "migrating-step-functions-asl", start="Not supported:")]),
             S("search_docs", query="asl to pskit mapping table",
               docs=[D("docs/workflows.md", "migrating-step-functions-asl", start="| ASL | pskit |", end="| `InputPath` / `ResultPath` | `input_path` / `result_path` |")])],
      final="""Not directly. `Parameters`, `ResultSelector`, `OutputPath`, intrinsic functions such as `States.Format`, `.sync`/callback integrations and timestamp waits aren't supported. Do that shaping in a small task function instead [docs/workflows.md#migrating-step-functions-asl].

What does translate: `InputPath` / `ResultPath` become `input_path` / `result_path`, and `Retry` / `Catch` / `Choice` / `Map` / `Parallel` have direct equivalents.

**In code**
```yaml
states:
  Charge: {type: task, function: charge, result_path: "$.charge", next: Shape}
  Shape: {type: task, function: shape-receipt, end: true}
```
```python
from __future__ import annotations


def shape_receipt(event, ctx):
    data = event.data
    return {"message": "Order {} charged {}".format(data["order_id"], data["charge"]["amount"])}
```
On AWS, pskit still deploys this as a Step Functions state machine."""),

    A(88, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/cli.md#pskit-workflow", "docs/workflows.md#commands"],
      user="which command prints the Cloud Workflows definition pskit generates for order-pipeline?",
      steps=[S("search_docs", query="show compiled workflow definition gcp format",
               docs=[D("docs/workflows.md", "commands", words=20)])],
      final="""**In the terminal**
```bash
pskit workflow show order-pipeline --format gcp
```
Without `--format`, it compiles for the current provider (`auto`). The other formats are `asl` and `json` [docs/workflows.md#commands]."""),

    A(89, provider="aws", stage="staging", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#choice-rules"],
      user="in my workflow, orders over 100 should go to a review step, the others go straight to shipping. how?",
      steps=[S("search_docs", query="workflow choice rule amount greater than",
               docs=[D("docs/workflows.md", "choice-rules")])],
      final="""Add a `choice` state. A rule with `gt` on the amount picks the review step, and `default` handles all other orders [docs/workflows.md#choice-rules].

**In studio**
1. Open **Workflows** and open your workflow.
2. Use **Add state** to add a *choice* state, and point the step before it to the choice.
3. In the inspector, click **+ Add rule**: variable `$.amount`, operator `gt`, value `100`, next `Review`.
4. Set *Otherwise* to `Ship`, then click **Save**.

**In code**
```yaml
workflows:
  orders:
    start_at: CheckAmount
    states:
      CheckAmount:
        type: choice
        choices:
          - {variable: "$.amount", gt: 100, next: Review}
        default: Ship
      Review: {type: task, function: review, next: Ship}
      Ship: {type: task, function: ship, end: true}
```

**In the terminal**
```bash
pskit workflow run orders -i '{"amount": 150}' --history
pskit workflow run orders -i '{"amount": 20}' --history
```
If `$.amount` is missing, the rule is false, so the order goes to `Ship`."""),

    A(90, provider="onprem", stage="prod", mode="ask", page="Resources", persona="beginner",
      sources=["docs/smtp/README.md#e-mail-triggers-smtp-on-premises", "docs/smtp/README.md#create-it"],
      user="i want my function to run every time someone sends an email to support@inbound.example.com",
      steps=[S("search_docs", query="run function when email arrives smtp trigger",
               docs=[D("docs/smtp/README.md", "e-mail-triggers-smtp-on-premises", end="the right values.", words=200)])],
      final="""Use an e-mail (`smtp`) trigger. It takes three steps: create the SMTP server, attach the function, and add two DNS records [docs/smtp/README.md#e-mail-triggers-smtp-on-premises].

**In studio**
1. Open **Resources** and click **+ SMTP server**.
2. Set the resource key `inbound-mail` and the domain `inbound.example.com`, pick your functions' server, keep port 25, and tick the function to run.
3. Open the service's **DNS guide** and add the A and MX records it shows at your domain provider.
4. **Deploy** so the host knows the trigger.

**In the terminal**
```bash
pskit resources onprem create inbound-mail --service smtp --domains inbound.example.com --attach on-mail --ssh ubuntu@203.0.113.10
pskit deploy -s prod
```

**In code**
```yaml
functions:
  on-mail:
    handler: app.mail.on_mail
    events:
      - smtp: {resource: inbound-mail}
```
```python
from __future__ import annotations


def on_mail(event, ctx):
    mail = event.data
    ctx.logger.info("mail", extra={"from": mail["from"], "subject": mail["subject"]})
    return {"ok": True}
```
Any address at that domain runs the function. Open inbound TCP 25 in the server's firewall."""),

    A(91, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#events-triggers", "docs/smtp/README.md#e-mail-triggers-smtp-on-premises"],
      user="email trigger work on aws lambda also? i see smtp in trigger list",
      steps=[S("search_docs", query="smtp trigger provider support aws",
               docs=[D("docs/events.md", "events-triggers", start="| `smtp` |", end="[smtp/README.md](smtp/README.md).")])],
      final="""No. The `smtp` trigger exists only on premises. Every cloud provider, AWS included, shows it as unsupported [docs/events.md#events-triggers].

Options:
1. Run the mail function on premises: create the SMTP server under **Resources > + SMTP server** and deploy that function with `provider.name: onprem`. The rest of your API can stay on AWS.
2. The on-prem mail event also carries the Amazon SES receipt shape (`event.data["Records"]`), so SES-style code can read it unchanged [docs/smtp/README.md#e-mail-triggers-smtp-on-premises]."""),

    A(92, provider="onprem", stage="dev", mode="auto", page="Test", persona="terse_expert",
      sources=["docs/smtp/README.md#test-it"],
      user="test the smtp handler without DNS or a real mail?",
      steps=[S("search_docs", query="test smtp trigger without dns",
               docs=[D("docs/smtp/README.md", "test-it", end="turns that into the full event.")])],
      final="""Yes, two ways [docs/smtp/README.md#test-it]:

**In the terminal**
Locally, with a synthetic mail:
```bash
pskit invoke -f on-mail -t smtp -d '{"from": "a@example.org", "to": ["x@inbound.example.com"], "subject": "Hi", "text": "Hello"}'
```
pskit turns that into the full event, including the SES-style `Records`. Against the deployed host, as if the SMTP server had received it:
```bash
pskit trigger -f on-mail
```

**In studio**
1. Open **Test** and pick `on-mail` with its e-mail trigger.
2. Edit the payload and click **▶ Run locally**, or **☁ Send to onprem / dev** for the deployed host."""),

    A(93, provider="tencent", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides"],
      user="In pskit.yml, prod on Tencent needs 1024 MB for every function and reserved concurrency 50 for create-order. Dev must keep the defaults. Show me the config.",
      steps=[S("search_docs", query="per stage overrides memory concurrency",
               docs=[D("docs/configuration.md", "stages-per-stage-overrides")])],
      final="""**In code**
```yaml
stages:
  prod:
    provider: {memory: 1024}
    functions:
      create-order: {concurrency: 50}
```
The `stages.prod` block is merged only when the stage is `prod`, so dev keeps the defaults [docs/configuration.md#stages-per-stage-overrides]. 1024 is a multiple of 128, which Tencent SCF requires for memory."""),

    A(94, provider="huawei", stage="dev", mode="ask", page="none", persona="pasted_error",
      sources=["docs/configuration.md#variables"],
      user="Error: unresolved variables: self:custom.table",
      steps=[S("search_docs", query="unresolved variables self custom",
               docs=[D("docs/configuration.md", "variables", end="Variables can nest across passes; unresolved variables are reported together.")])],
      final="""Your pskit.yml uses `${self:custom.table}`, but the merged config has no `custom.table`. `${self:...}` reads any value of the merged config [docs/configuration.md#variables].

Fix it in one of two ways:
1. Add the value:
```yaml
custom:
  table: orders
```
2. Or fix the path if the value lives elsewhere, e.g. `${self:custom.tables.orders}`.

If `custom.table` is set only inside a `stages:` or `providers:` block, it exists only for that stage or provider. Run `pskit validate -p huawei` again after the fix."""),

    A(95, provider="azure", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#variables"],
      user="load the cors origins list from origins.json in pskit.yml?",
      steps=[S("search_docs", query="file variable json config value",
               docs=[D("docs/configuration.md", "variables", end="| `${file(path.json)}` |")])],
      final="""Yes, with `${file(...)}`. A `.json` or `.yml` file is parsed, and the path is relative to the config [docs/configuration.md#variables]. When the value is exactly one variable, its type is kept, so you get a list.

```yaml
functions:
  api:
    handler: app.api.handler
    events:
      - http:
          path: /orders
          method: GET
          cors:
            origins: ${file(origins.json)}
```
`origins.json`:
```json
["https://app.example.com", "https://admin.example.com"]
```"""),

    A(96, provider="gcp", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#precedence-later-wins", "docs/troubleshooting.md#configuration"],
      user="pskit.gcp.yml extends pskit.yml. The base file has providers.gcp.memory: 512 and the child sets provider memory 256. We expected 512 on GCP but get 256. Bug?",
      steps=[S("search_docs", query="extends precedence providers block child wins",
               docs=[D("docs/configuration.md", "precedence-later-wins")])],
      final="""No, that's the documented order. For each file in the `extends` chain, parents first, pskit applies that file's own values, then that file's `providers.<active provider>` block. So the parent's `providers.gcp` is applied before the child's values, and the child's explicit `memory: 256` wins [docs/configuration.md#precedence-later-wins].

To get 512 on GCP, do one of these:
1. Set it in the child, since it's already GCP-only:
```yaml
extends: pskit.yml
provider:
  name: gcp
  memory: 512
```
2. Or remove `memory` from the child, so the parent's `providers.gcp` value stays.

Also remember: dicts are deep-merged, lists are replaced, and `stages.<stage>` and CLI flags come after all files."""),

    A(97, provider="cloudflare", stage="dev", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-5-move-to-another-cloud", "docs/troubleshooting.md#provider-gotchas"],
      user="We've moved our Lambda app to pskit on AWS. Next we want to try the HTTP part on Cloudflare. What usually has to change?",
      steps=[S("search_docs", query="move from aws to another cloud what changes",
               docs=[D("docs/migrating-from-aws.md", "step-5-move-to-another-cloud")]),
             S("search_docs", query="cloudflare workers limits python packages",
               docs=[D("docs/troubleshooting.md", "provider-gotchas", start="| cloudflare |", end="| cloudflare |")])],
      final="""The handlers stay the same. The changes are all in YAML [docs/migrating-from-aws.md#step-5-move-to-another-cloud]:
- Add Cloudflare's required `options.account_id`, and set `CLOUDFLARE_API_TOKEN`.
- Replace `auth: jwt` (AWS only), or validate tokens in the handler.
- Remove AWS-only `functions.<fn>.options` and `terraform.extra`.
- Switch off what Cloudflare can't run (queue, storage, topic triggers) with `enabled: false` in a `providers.cloudflare` block.

Also check your dependencies: Workers run Python on Pyodide, so only the standard library and Pyodide packages are available [docs/troubleshooting.md#provider-gotchas].

**In code**
```yaml
providers:
  cloudflare:
    options: {account_id: "${env:CLOUDFLARE_ACCOUNT_ID}"}
    functions:
      worker: {enabled: false}
```

**In the terminal**
```bash
pskit validate --provider cloudflare
pskit deploy --provider cloudflare
```
`validate` lists everything that isn't portable before you deploy."""),

    A(98, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/local-development.md#on-premises-is-a-deploy-not-pskit-dev"],
      user="my schedule runs in pskit dev, but when i stop it the schedule stops too. how do i keep it running on my pc?",
      steps=[S("search_docs", query="keep schedule running after pskit dev on premises",
               docs=[D("docs/local-development.md", "on-premises-is-a-deploy-not-pskit-dev")])],
      final="""`pskit dev` is only for development. Its process ends when you stop it. For a durable run on your PC, **deploy** with the on-prem provider: `pskit deploy` starts a host process that keeps schedules, queues, storage, topics and workflows running after the command returns [docs/local-development.md#on-premises-is-a-deploy-not-pskit-dev].

**In code**
```yaml
provider:
  name: onprem
  options:
    port: 8080
    deploy: {method: local}
```
`method: local` (the default) runs it on this machine. `ssh` or `docker` run it on a server.

**In the terminal**
```bash
pskit deploy
pskit logs -f
```

**In studio**
1. Open **Deploy** with onprem in the top bar.
2. Click **Deploy**. Use **Logs** to watch the schedule.

`pskit remove` stops it later."""),

    A(99, provider="aws", stage="dev", mode="ask", page="none", persona="detailed_spec",
      sources=["docs/architecture.md#bundle-layout", "docs/architecture.md#deploy-pipeline"],
      user="Our security review asks what exactly goes into the zip pskit uploads to Lambda, and whether two builds of the same commit are identical.",
      steps=[S("search_docs", query="bundle layout artifact zip contents",
               docs=[D("docs/architecture.md", "bundle-layout", words=30)]),
             S("search_docs", query="reproducible artifact deterministic",
               docs=[D("docs/architecture.md", "deploy-pipeline", start="- **Reproducible artifacts.**", end="- **Reproducible artifacts.**")])],
      final="""On AWS, `artifact.zip` contains [docs/architecture.md#bundle-layout]:
- your code, filtered by `package.include` / `exclude` and the default excludes (`.env`, `tests/**`, `.git/**`, state files, `pskit*.yml`, ...)
- `py_serverless_kit/` with only the runtime: no CLI, pydantic, yaml or click
- `pskit_manifest.json`: functions, handlers, routes, CORS, timeouts and physical names
- the shim `pskit_entry.py`
- your dependencies from `requirements.txt`, pip-installed as Linux wheels

Yes, builds are reproducible. The zip is byte-identical for identical inputs (sorted entries, fixed timestamps), so unchanged code gives an unchanged hash and no redeploy [docs/architecture.md#deploy-pipeline].

**In the terminal**
To inspect it without deploying:
```bash
pskit package
```
The bundle sources are in `.pskit/aws-dev/build/` and the zip is `.pskit/aws-dev/artifact.zip`."""),

    A(100, provider="digitalocean", stage="staging", mode="ask", page="YAML", persona="beginner",
       sources=["docs/configuration.md#hooks"],
       user="i want to run my tests automatically before every deploy and stop if they fail",
       steps=[S("search_docs", query="run command before deploy hook",
                docs=[D("docs/configuration.md", "hooks")])],
       final="""Use a `before_deploy` hook. A command that exits non-zero aborts the deploy [docs/configuration.md#hooks].

**In code**
```yaml
hooks:
  before_deploy: ["python -m pytest -q"]
```
Commands run through the shell in the project root, with `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and `PSKIT_WORK_DIR` set. The allowed hooks are `before_package`, `after_package`, `before_deploy`, `after_deploy`, `before_remove` and `after_remove`.

**In the terminal**
```bash
pskit deploy -s staging
```
The tests run first. If they fail, nothing is deployed."""),
]
