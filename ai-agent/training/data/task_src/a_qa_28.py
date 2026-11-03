"""Category A (docs Q&A and how-to), batch 28: aws / gcp / azure. Existing queues and buckets through resources
and options, GCP invoker account, AWS resource IAM grants, workflow engines and compiler limits, error names,
fail/wait states, local and deployed workflow commands, studio Test / Deploy / Functions wizard / Code / Full VS
Code / Resources test. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(531, provider="aws", stage="dev", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#resources-storage-queues-topics-databases-any-service", "docs/resources.md#using-a-resource-from-an-event"],
      user="Our billing team owns the SQS queue arn:aws:sqs:us-east-1:123456789012:billing-jobs in their stack. My worker should consume it, and pskit must never touch the queue itself. What's the cleanest config?",
      steps=[S("search_docs", query="external resource connection arn queue event",
               docs=[D("docs/resources.md", "resources-storage-queues-topics-databases-any-service", start="  billing-events:", end="      arn: arn:aws:sns"),
                     D("docs/resources.md", "using-a-resource-from-an-event", start="The event then behaves")])],
      final="""Declare it as an external resource with its ARN, and point the queue event at the resource. pskit never creates, changes or destroys an external resource, and the event behaves like `existing: true` [docs/resources.md#using-a-resource-from-an-event].

**In code**
```yaml
resources:
  billing-jobs:
    type: queue
    external: true
    connection:
      arn: arn:aws:sqs:us-east-1:123456789012:billing-jobs
functions:
  worker:
    handler: app.worker.handle
    events:
      - queue: {resource: billing-jobs, batch_size: 10}
```
Without `name`, the native name is the last `:` segment of the ARN (`billing-jobs`).

**In studio**
1. Open **Resources**, click **+ Add resource**, pick queue, mark it external and enter the ARN (or use **Browse account**).
2. Open **Functions**, click `worker`, add a **Queue** trigger and pick the resource.
3. Click **Save**."""),

    A(532, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      user="after deploy to gcp i see a new service account i did not make. what is it for?",
      steps=[S("search_docs", query="gcp service account created invoker scheduler eventarc",
               docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="Functions with several triggers are **split", end="A dedicated invoker service account")])],
      final="""pskit creates a dedicated invoker service account on GCP. Cloud Scheduler, Eventarc and Cloud Workflows use it to call your functions [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. Keep it: without it schedules, event triggers and workflows can't reach the functions.

It isn't the identity your code runs as. For that, set `provider.options.service_account`."""),

    A(533, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/providers.md#azure-azure-functions"],
      user="The blob container invoices already exists in a different storage account (not the Function App's). How do I make a storage trigger on it?",
      steps=[S("search_docs", query="azure existing container other storage account",
               docs=[D("docs/events.md", "storage", start="| azure | Blob trigger", end="| azure | Blob trigger")]),
             S("search_docs", query="azure storage_connection option",
               docs=[D("docs/providers.md", "azure-azure-functions", start="provider:", end="One **Linux Consumption Function App**")])],
      final="""Use `existing: true` on the trigger and set `options.storage_connection` to the name of an app setting that holds that account's connection string [docs/events.md#storage] [docs/providers.md#azure-azure-functions].

**In code**
```yaml
provider:
  name: azure
  options:
    storage_connection: INVOICES_STORAGE
  environment:
    INVOICES_STORAGE: ${env:INVOICES_STORAGE}
functions:
  on-invoice:
    handler: app.invoices.handle
    events:
      - storage: {bucket: invoices, existing: true}
```
`INVOICES_STORAGE` comes from your environment when you deploy, so the connection string isn't in the file.

**In the terminal**
```bash
export INVOICES_STORAGE='<connection string of the other account>'
pskit validate
```
Only created/updated blobs trigger the function on Azure."""),

    A(534, provider="aws", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#aws-iam"],
      user="Security asks which IAM permissions our Lambdas get for the managed uploads bucket and jobs queue resources, and whether every function gets them.",
      steps=[S("search_docs", query="aws iam resources policy actions",
               docs=[D("docs/resources.md", "aws-iam")])],
      final="""Each role pskit creates gets a `pskit-resources` policy for the storage, queue and topic resources bound to its functions [docs/resources.md#aws-iam]:

| Type | Actions |
|---|---|
| storage | `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket` |
| queue | `sqs:SendMessage`, `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`, `GetQueueAttributes`, `GetQueueUrl` |
| topic | `sns:Publish` |

By default every function you wrote is bound to every resource. Narrow it with `functions:` on the resource:

**In code**
```yaml
resources:
  uploads: {type: storage, functions: [api]}
  jobs: {type: queue, functions: [api, worker]}
```
With your own role (`iam.role`) pskit can't change it: the plan prints a warning and the grants are up to you."""),

    A(535, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#engines"],
      user="force embedded engine instead of cloud workflows on gcp for one workflow. tradeoff?",
      steps=[S("search_docs", query="engine embedded native auto",
               docs=[D("docs/workflows.md", "workflow-keys", start="| `engine` |", end="| `engine` |"),
                     D("docs/workflows.md", "engines", end="| all others (or `engine: embedded`) |")])],
      final="""**In code**
```yaml
workflows:
  sync:
    engine: embedded
    start_at: Fetch
    states:
      Fetch: {type: task, function: fetch, end: true}
```
`embedded` forces pskit's engine: an extra `<workflow>-orchestrator` function that runs the state machine and calls the task handlers in-process [docs/workflows.md#engines].

Tradeoff: the whole run must fit in one invocation of that function (its timeout), so long `wait` states don't fit, and there's no execution history to list. Cloud Workflows (`auto` on GCP) has neither limit, but follows its own compiler rules (one retry rule per task, task HTTP timeouts capped at 1800 s)."""),

    A(536, provider="azure", stage="dev", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#compiler-notes-and-limits"],
      user="our choice rule uses matches: \"ord-??-*\" and with engine native on azure validate fails, on aws it was fine. why",
      steps=[S("search_docs", query="azure logic apps matches glob limits",
               docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="- **Azure (Logic Apps):**")])],
      final="""On Azure's Logic Apps engine, `matches` only accepts `abc`, `abc*`, `*abc`, `*abc*` and `*`; other globs (such as `?`) are a validation error [docs/workflows.md#compiler-notes-and-limits].

Options:
1. Use a simpler pattern, for example `matches: "ord-*"`.
2. Move the check into a small task function that returns a flag, then branch on it with `equals`.
3. Keep the pattern and use the default engine on Azure (remove `engine: native`); the embedded engine supports `?`."""),

    A(537, provider="aws", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#commands", "docs/migrating-from-aws.md#step-3-translate-step-functions"],
      user="I converted our ASL by hand into pskit.yml. How can I see the ASL pskit will deploy so I can diff it against the original state machine?",
      steps=[S("search_docs", query="workflow show format asl compare",
               docs=[D("docs/migrating-from-aws.md", "step-3-translate-step-functions")])],
      final="""Print the compiled definition with `pskit workflow show --format asl` [docs/migrating-from-aws.md#step-3-translate-step-functions].

**In the terminal**
```bash
pskit workflow show order-pipeline --format asl > new.asl.json
pskit workflow run order-pipeline -i @events/order.json --history
```
Diff `new.asl.json` against your old file. The `run` line runs the workflow locally with the same engine semantics, so you can check the path before deploying. Error names in `retry`/`catch` are now your Python exception class names."""),

    A(538, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#state-types"],
      user="wait state seconds come from my data, like $.delay. possible?",
      steps=[S("search_docs", query="wait seconds_path",
               docs=[D("docs/workflows.md", "state-types", start="| `wait` |", end="| `wait` |")])],
      final="""Yes, use `seconds_path` instead of `seconds` [docs/workflows.md#state-types].

**In code**
```yaml
workflows:
  remind:
    start_at: Wait
    states:
      Wait: {type: wait, seconds_path: "$.delay", next: Send}
      Send: {type: task, function: send-reminder, end: true}
```

**In studio**
1. Open **Workflows**, click the wait state.
2. Set *Wait mode* to *From the data* and *Seconds path* to `$.delay`.
3. Click **Save**.

**In the terminal**
```bash
pskit workflow run remind -i '{"delay": 30}' --sleep --history
```
Without `--sleep`, local runs skip the wait."""),

    A(539, provider="azure", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#compiler-notes-and-limits"],
      user="With engine: native on Azure our task has retry errors: [TimeoutError], max_attempts 3, backoff_rate 2. Will the Logic App honour exactly that?",
      steps=[S("search_docs", query="logic apps retry policy errors backoff",
               docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="- **Azure (Logic Apps):**")])],
      final="""Not exactly. On Logic Apps only the first retry rule of a task is used, as Logic Apps' exponential retry policy [docs/workflows.md#compiler-notes-and-limits]:
- It retries 408/429/5xx responses of the task call; the `errors` filter (`TimeoutError`) and `backoff_rate` are ignored.
- Intervals are 5 s to 1 day, at most 90 retries.
- `retry` and `catch` work on `task` states only.

So the task is retried on any 408/429/5xx failure of the call, not only on `TimeoutError`. If retrying other errors is harmful, catch them inside the handler, or use the default embedded engine on Azure, which matches the exception class names."""),

    A(540, provider="aws", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/workflows.md#retry-and-catch"],
      user="in my workflow i want catch only when payment is declined, not other errors. how do i name the error?",
      steps=[S("search_docs", query="catch errors exception class names",
               docs=[D("docs/workflows.md", "retry-and-catch", start="Error names are the")])],
      final="""Error names are the Python exception class names your handler raises [docs/workflows.md#retry-and-catch]. Make your own exception class and catch that name.

**In code**
```python
from __future__ import annotations


class PaymentDeclined(Exception):
    pass


def charge(event, ctx):
    order = dict(event.data)
    if not card_ok(order):
        raise PaymentDeclined("card declined")
    return {**order, "paid": True}
```
```yaml
workflows:
  orders:
    start_at: Charge
    states:
      Charge:
        type: task
        function: charge
        catch: [{errors: [PaymentDeclined], next: Declined}]
        end: true
      Declined: {type: task, function: notify-declined, end: true}
```
Other exceptions don't match, so the run fails as usual. `card_ok` is your own function.

**In the terminal**
```bash
pskit workflow run orders -i '{"id": 1}' --history
```"""),

    A(541, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types"],
      user="When the stock check says nothing is left, the workflow should stop as failed with a clear error name and message that we can see in the execution. Which state does that?",
      steps=[S("search_docs", query="fail state error cause",
               docs=[D("docs/workflows.md", "state-types", start="| `succeed` |", end="| `fail` |")])],
      final="""A `fail` state with `error` and `cause` [docs/workflows.md#state-types].

**In code**
```yaml
workflows:
  order:
    start_at: CheckStock
    states:
      CheckStock: {type: task, function: check-stock, next: Route}
      Route:
        type: choice
        choices:
          - {variable: "$.in_stock", equals: false, next: OutOfStock}
        default: Ship
      Ship: {type: task, function: ship, end: true}
      OutOfStock: {type: fail, error: OutOfStock, cause: no items left}
```

**In studio**
1. Open **Workflows**, add a state of type *Stop with an error*.
2. Fill in *Error* and *Cause*, and point the choice rule to it.
3. Click **Save**.

**In the terminal**
```bash
pskit workflow run order -i '{"sku": "x"}' --history
```
A failed local run prints `FAILED OutOfStock: no items left` and exits with code 2."""),

    A(542, provider="azure", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/cli.md#pskit-workflow"],
      user="when i run workflow local the wait of 20 sec is skipped. i want really wait for test",
      steps=[S("search_docs", query="workflow run local wait skipped sleep",
               docs=[D("docs/cli.md", "pskit-workflow", start="- `run` executes the workflow locally", end="- `run` executes the workflow locally")])],
      final="""Add `--sleep`. Local runs skip `wait` states unless you pass it [docs/cli.md#pskit-workflow].

**In the terminal**
```bash
pskit workflow run my-workflow -i '{"id": 1}' --sleep --history
```
`--history` shows each state, so you can see the wait happen."""),

    A(543, provider="aws", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/cli.md#pskit-workflow"],
      user="stop a running step functions execution from the cli",
      steps=[S("search_docs", query="workflow cancel execution",
               docs=[D("docs/cli.md", "pskit-workflow", start="| `cancel` |", end="| `cancel` |")])],
      final="""**In the terminal**
```bash
pskit workflow cancel <execution_id> -s prod -w order-pipeline
```
On AWS it calls `StopExecution` [docs/cli.md#pskit-workflow]. Your credentials need `states:StopExecution`. Find the id with `pskit workflow executions order-pipeline -s prod --status RUNNING`."""),

    A(544, provider="gcp", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/studio.md#test-functions", "docs/cli.md#pskit-trigger"],
      user="how do i test my deployed gcp function that runs when a file is uploaded to the bucket?",
      steps=[S("search_docs", query="test deployed storage trigger upload object",
               docs=[D("docs/studio.md", "test-functions", end="Turn on *Show the function's logs* to watch it.")]),
             S("search_docs", query="trigger storage payload key content",
               docs=[D("docs/cli.md", "pskit-trigger", start="| Type | `-d` |", end="| storage |")])],
      final="""Upload a real object to the bucket with pskit; that fires the function's trigger [docs/studio.md#test-functions].

**In studio**
1. Open **Test** with gcp / dev in the top bar.
2. Pick the function and its storage trigger. The sample payload already matches the trigger's prefix and suffix.
3. Turn on *Show the function's logs* and click **☁ Send to gcp / dev**.

**In the terminal**
```bash
pskit trigger -f my-function -e 0 -d '{"key": "in/test.csv", "content": "a,b"}'
pskit logs -f --function my-function
```
For storage the payload is `{"key": "...", "content": "..."}` [docs/cli.md#pskit-trigger]. Use your function's name. This needs Google credentials on your machine."""),

    A(545, provider="azure", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/studio.md#what-you-can-do"],
      user="i'm on the deploy page. can i quickly run one function here with some json, without going to test page? studio steps only",
      steps=[S("search_docs", query="deploy page invoke function payload",
               docs=[D("docs/studio.md", "what-you-can-do", start="| **Deploy** |", end="| **Deploy** |")])],
      final="""**In studio**
1. On **Deploy**, open the panel *Invoke a function locally*.
2. Pick the *Function* and, if needed, the *Event type* (default: direct invoke).
3. Enter the *Payload (JSON)* and click **Invoke**.

The result shows in the live log. It runs on this machine, not in Azure [docs/studio.md#what-you-can-do]."""),

    A(546, provider="aws", stage="prod", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/studio.md#what-you-can-do"],
      user="why does studio make me type aws/prod before deploy? for dev it doesn't",
      steps=[S("search_docs", query="studio typed confirmation prod stage",
               docs=[D("docs/studio.md", "what-you-can-do", start="| **Deploy** |", end="| **Deploy** |")])],
      final="""On purpose. Remove, and any deploy to a stage named `prod*`, needs a typed confirmation, so production isn't changed by a stray click [docs/studio.md#what-you-can-do].

Type `aws/prod` exactly as shown and confirm. For extra safety, run **Plan** first and read the changes in the live log."""),

    A(547, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/studio.md#what-you-can-do"],
      user="in studio, how create new function with http trigger? only the clicks please",
      steps=[S("search_docs", query="studio create function wizard",
               docs=[D("docs/studio.md", "what-you-can-do", start="| **Functions** |", end="| **Functions** |")])],
      final="""**In studio**
1. Open **Functions** and click **+ Create function**.
2. *Basics*: enter the *Function name*; the *Handler* is filled in from the name. Click *Next: Triggers →*.
3. *Triggers*: pick **HTTP endpoint**, choose the method and type the route, for example `/orders/{id}` (the path-parameter preview shows `id`).
4. Click *Next* to *Environment & permissions* and add variables if you need them.
5. *Review*: check the YAML diff and click *Create function*.
6. Click **Save**.

Studio also writes a handler stub into your code [docs/studio.md#what-you-can-do]."""),

    A(548, provider="azure", stage="dev", mode="ask", page="Code", persona="pasted_error",
      sources=["docs/studio.md#security"],
      user="the studio code editor refuses to open .pskit/azure-dev/main.tf.json. i just want to read it",
      steps=[S("search_docs", query="studio editor refuses files pskit folder",
               docs=[D("docs/studio.md", "security", start="- The file editor only reaches files", end="- The file editor only reaches files")])],
      final="""That's a safety rule: the studio editor never touches `.pskit/`, `.git/`, `.venv/`, `node_modules/` or `__pycache__`, and refuses binary files or files over 1 MiB [docs/studio.md#security].

Open it in your own editor instead, or print it:
```bash
pskit package
cat .pskit/azure-dev/main.tf.json
```
`pskit package` regenerates the file without contacting Azure."""),

    A(549, provider="aws", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/studio.md#full-vs-code-code-server-in-docker"],
      user="Our Lambdas are pinned to python3.9. When I open Full VS Code in studio, which Python will the terminal there have, and can I make it 3.9?",
      steps=[S("search_docs", query="full vs code runtimes python version",
               docs=[D("docs/studio.md", "full-vs-code-code-server-in-docker", start="**Runtimes**", end="The default is the project's own runtime.")])],
      final="""By default it uses the project's own runtime, so with `python3.9` pinned you get Python 3.9. You can also pick a **Python** (3.9 to 3.13) and/or **Node.js** version next to the image [docs/studio.md#full-vs-code-code-server-in-docker].

**In studio**
1. Open **Code** and switch to **Full VS Code**.
2. Pick Python 3.9 next to the image and click **Pull & start**.

The first start with a combination builds an image with that Python; later starts reuse it. If VS Code is already running, changing the selection offers **Restart with these runtimes**, and your files stay where they are."""),

    A(550, provider="gcp", stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/studio.md#project-environment-trigger-resources-and-remove"],
      user="We deployed a managed bucket resource reports on GCP staging. I want to upload a test object to it from the studio and see the snippet to use it in a handler.",
      steps=[S("search_docs", query="studio test a resource upload object bucket",
               docs=[D("docs/studio.md", "project-environment-trigger-resources-and-remove", start="- **Resources → Test a resource**", end="variables the bound functions get and a Python / Node.js snippet that reads them.")]),
             S("search_docs", query="test a resource use it in a handler",
               docs=[D("docs/studio.md", "project-environment-trigger-resources-and-remove", start="- **Resources → Test a resource** shows *Use it in a handler*", end="- **Resources → Test a resource** shows *Use it in a handler*")])],
      final="""**In studio**
1. Open **Resources** with gcp / staging in the top bar.
2. Click **Test** on the `reports` row (or **Resources → Test a resource**).
3. Upload a test object. Managed resources can be tested after deploy, which you've done [docs/studio.md#project-environment-trigger-resources-and-remove].
4. Open *Use it in a handler* for the Python code and the library to add, or use **Test connection** to check access.

The upload uses your machine's Google credentials."""),
]
