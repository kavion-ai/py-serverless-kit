"""Category A (docs Q&A and how-to), batch 41: aws / gcp / azure workflows. Compiler notes per engine (retry
intervals, contains, first retry rule and retry scope on GCP, task timeouts, Logic Apps sync responses, task call
limits, map concurrency, nesting, is_present, result_path, run limits), embedded runs on AWS, the Step Functions
role, OIDC task calls, compiled Cloud Workflows output, exit codes, execution ids and statuses, run timeouts.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


WF = "docs/workflows.md"
WE = "docs/workflow-executions.md"
CN = "compiler-notes-and-limits"

CONVERSATIONS = [
    A(791, provider="aws", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=[f"{WF}#{CN}"],
      user="retry interval_seconds 0.5 on step functions ok?",
      steps=[S("search_docs", query="aws IntervalSeconds rounded",
               docs=[D(WF, CN, end="- **AWS:**")])],
      final="""It deploys, but on AWS `IntervalSeconds` is rounded to at least 1 [docs/workflows.md#compiler-notes-and-limits], so the first retry waits 1 s."""),

    A(792, provider="aws", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=[f"{WF}#{CN}"],
      user="choice rule with contains works in aws step functions? i heard asl has no contains",
      steps=[S("search_docs", query="choice contains step functions compile",
               docs=[D(WF, CN, end="- **AWS:**")])],
      final="""Yes. pskit compiles `contains` to `StringMatches *x*` on AWS [docs/workflows.md#compiler-notes-and-limits], so you can keep using it."""),

    A(793, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WF}#{CN}"],
      user="Our Charge task has two retry rules on GCP: one for RateLimited (5 attempts) and one for Timeout (2 attempts). Will both apply in Cloud Workflows?",
      steps=[S("search_docs", query="gcp workflows retry rules first only",
               docs=[D(WF, CN, start="- **GCP:**", end="- **GCP:**")])],
      final="""No. On GCP only the **first** retry rule of a task is used, because Cloud Workflows allows one retry policy [docs/workflows.md#compiler-notes-and-limits].

Options:
1. Merge them into one rule: `errors: [RateLimited, Timeout]` with the attempts you can accept for both.
2. Or keep the stricter one first, and handle the other error with a `catch` that routes to a retry step of your own.
3. Or set `engine: embedded` on this workflow, if the whole run fits in one function call."""),

    A(794, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="pasted_error",
      sources=[f"{WF}#{CN}"],
      user="WARNING: retry on parallel state 'Notify' is ignored on gcp?? i want retry the whole parallel",
      steps=[S("search_docs", query="gcp retry catch parallel map ignored",
               docs=[D(WF, CN, start="- **GCP:**", end="- **GCP:**")])],
      final="""On GCP `retry` and `catch` are honoured on `task` states only; on `parallel` / `map` they are ignored with a warning [docs/workflows.md#compiler-notes-and-limits].

Move the retry to the task states inside each branch:
```yaml
workflows:
  order-pipeline:
    start_at: Notify
    states:
      Notify:
        type: parallel
        branches:
          - start_at: Email
            states:
              Email:
                type: task
                function: send-email
                retry: [{errors: [SmtpError], max_attempts: 3}]
                end: true
        end: true
```"""),

    A(795, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WF}#{CN}"],
      user="One task function in our GCP workflow has timeout: 3600. Does the workflow wait that long for it?",
      steps=[S("search_docs", query="gcp workflow task http timeout cap",
               docs=[D(WF, CN, start="- **GCP:**", end="- **GCP:**")])],
      final="""No. Task HTTP timeouts are capped at 1800 s on GCP [docs/workflows.md#compiler-notes-and-limits], so the workflow stops waiting after 30 minutes even if the function still runs.

Split the work: let the task start the job (for example publish to a queue) and return, then poll its status in a later step with a `wait` state in between."""),

    A(796, provider="azure", stage="prod", mode="ask", page="Workflows", persona="pasted_error",
      sources=[f"{WF}#{CN}"],
      user="our azure logic app workflow (engine native) runs 5 minutes. the start request returns an error after about 2 min, but the run finishes fine",
      steps=[S("search_docs", query="logic apps synchronous response 2 minutes sync false",
               docs=[D(WF, CN, start="- **Azure (Logic Apps):**", words=150)])],
      final="""The HTTP trigger answers synchronously with the output, and that response must come within about 2 minutes. For long workflows set `options.sync: false` [docs/workflows.md#compiler-notes-and-limits].

**In code**
```yaml
workflows:
  order-pipeline:
    engine: native
    options:
      sync: false
```
Then the start call no longer waits for the result."""),

    A(797, provider="azure", stage="dev", mode="ask", page="Workflows", persona="pasted_error",
      sources=[f"{WF}#{CN}"],
      user="WARNING about task function timeout longer than the Logic Apps limit. my export task has timeout 300",
      steps=[S("search_docs", query="logic apps task call timeout 120",
               docs=[D(WF, CN, start="- **Azure (Logic Apps):**", words=220)])],
      final="""In a Logic App, task calls time out after 120 s (the Logic Apps limit for outbound HTTP), and `pskit validate` warns when a task function's timeout is longer [docs/workflows.md#compiler-notes-and-limits].

Options:
1. Make `export` finish within 120 s (for example, hand the heavy part to a queue worker).
2. Or run this workflow on the embedded engine (`engine: embedded`), if the whole run fits in Azure's 600 s function limit."""),

    A(798, provider="azure", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=[f"{WF}#{CN}"],
      user="logic apps: map max_concurrency 10 respected?",
      steps=[S("search_docs", query="logic apps map iterations concurrency",
               docs=[D(WF, CN, start="- **Azure (Logic Apps):**", words=320)])],
      final="""No. On Logic Apps `map` iterations run one at a time; `max_concurrency` is ignored [docs/workflows.md#compiler-notes-and-limits]."""),

    A(799, provider="azure", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WF}#{CN}"],
      user="We have a parallel inside a parallel inside a map inside another map. With engine: native on Azure, will that compile?",
      steps=[S("search_docs", query="logic apps nesting levels parallel map",
               docs=[D(WF, CN, start="- **Azure (Logic Apps):**")])],
      final="""Not if it goes past the nesting limit. Logic Apps allow 8 levels of nesting, so `parallel` states can nest at most three deep and `map` states two deep [docs/workflows.md#compiler-notes-and-limits]. Mixing both quickly uses up the levels.

Options:
1. Flatten it: move the inner map into a task function that loops in code.
2. Or keep the default engine on Azure (embedded), which doesn't compile to a Logic App; the whole run must then finish within one function call.

Run `pskit validate -p azure` to see the error for your definition."""),

    A(800, provider="azure", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=[f"{WF}#{CN}"],
      user="choice is_present on azure native: my field is null and it goes to the 'missing' branch. on aws not",
      steps=[S("search_docs", query="logic apps is_present null",
               docs=[D(WF, CN, start="- **Azure (Logic Apps):**")])],
      final="""That's a Logic Apps difference: `is_present` treats `null` like a missing key [docs/workflows.md#compiler-notes-and-limits].

To get the same result everywhere, don't send `null` (drop the key instead), or test the value explicitly in the rule (for example `is_null`), or check it in a small task function."""),

    A(801, provider="azure", stage="dev", mode="ask", page="Workflows", persona="pasted_error",
      sources=[f"{WF}#{CN}"],
      user="validate on azure (engine native) complains about result_path $.items[0].price. works on aws",
      steps=[S("search_docs", query="logic apps result_path array index",
               docs=[D(WF, CN, start="- **Azure (Logic Apps):**")])],
      final="""On Logic Apps `result_path` can't contain array indexes [docs/workflows.md#compiler-notes-and-limits].

Write the result to a plain key, for example `result_path: $.first_price`, and let the next task function put it into the list if you need it there."""),

    A(802, provider="azure", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WF}#{CN}"],
      user="Is there a limit on how long or how many steps an Azure Logic Apps workflow from pskit can run?",
      steps=[S("search_docs", query="logic apps run stops states timeout",
               docs=[D(WF, CN, start="- **Azure (Logic Apps):**")])],
      final="""Yes: a run stops after 5000 states or at the workflow's `timeout` (default 1 hour) [docs/workflows.md#compiler-notes-and-limits]. Raise `timeout` for longer runs:

```yaml
workflows:
  order-pipeline:
    engine: native
    timeout: 7200
```"""),

    A(803, provider="aws", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WF}#embedded-orchestrator"],
      user="We forced engine: embedded on AWS for one workflow. It has a 20-minute wait state. Will that work?",
      steps=[S("search_docs", query="embedded orchestrator whole run one invocation max timeout",
               docs=[D(WF, "embedded-orchestrator", start="- The **whole run must fit in one function invocation**", end="`pskit validate` warns about this.")])],
      final="""No. With the embedded engine the whole run must fit in one function invocation, at most 900 s on AWS, so a 20-minute wait can't fit; `pskit validate` warns about it [docs/workflows.md#embedded-orchestrator].

Use the native engine (Step Functions), the default on AWS:
```yaml
workflows:
  order-pipeline:
    engine: native
```
Or split the workflow at the wait."""),

    A(804, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=[f"{WF}#engines"],
      user="do i need write iam permissions so step functions can call my lambdas?",
      steps=[S("search_docs", query="step functions iam role invoke lambdas",
               docs=[D(WF, "engines", end="| gcp | native |")])],
      final="""No. pskit deploys the state machine with an IAM role that can invoke the task Lambdas [docs/workflows.md#engines]. Only what your task functions do themselves (DynamoDB, ...) needs `iam.statements`."""),

    A(805, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WF}#engines"],
      user="Our task functions on GCP use auth: iam so they aren't public. Can Cloud Workflows still call them?",
      steps=[S("search_docs", query="gcp workflows tasks oidc http calls",
               docs=[D(WF, "engines", end="| azure (`engine: native`) |")])],
      final="""Yes. On GCP the tasks are OIDC-authenticated HTTP calls to the functions [docs/workflows.md#engines], made with the invoker service account pskit creates for Workflows. `auth: iam` only removes the public invoker binding."""),

    A(806, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=[f"{WF}#commands"],
      user="show the cloud workflows yaml pskit generates for order-pipeline",
      steps=[S("search_docs", query="workflow show format gcp",
               docs=[D(WF, "commands", end="`workflow run` exits with code 2 when the run fails.")])],
      final="""**In the terminal**
```bash
pskit workflow show order-pipeline --format gcp
```
Without `--format` it shows the workflow compiled for the current provider [docs/workflows.md#commands]."""),

    A(807, provider="aws", stage="dev", mode="ask", page="none", persona="detailed_spec",
      sources=[f"{WF}#commands"],
      user="In CI we run the order-pipeline workflow locally with a test input before deploying. How does the job know the run failed?",
      steps=[S("search_docs", query="workflow run exit code fails",
               docs=[D(WF, "commands", end="`workflow run` exits with code 2 when the run fails.")])],
      final="""`pskit workflow run` exits with code 2 when the run fails [docs/workflows.md#commands], so the CI step fails on its own.

```bash
pskit workflow run order-pipeline -i @events/order.json --history
```
It runs locally on the embedded engine (wait states skipped unless you add `--sleep`), with no AWS access."""),

    A(808, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="informal_non_native",
      sources=[f"{WE}#the-execution-record"],
      user="workflow start on gcp give me a very long execution id with projects/... inside. normal?",
      steps=[S("search_docs", query="execution ids gcp format",
               docs=[D(WE, "the-execution-record", start="Execution ids from the embedded engine", end="Execution ids from the embedded engine")])],
      final="""Yes. GCP execution ids are the resource names `projects/.../workflows/.../executions/...`; AWS ids are execution ARNs [docs/workflow-executions.md#the-execution-record]. Pass the whole string:

```bash
pskit workflow status 'projects/.../executions/...' --watch
```"""),

    A(809, provider="aws", stage="prod", mode="ask", page="Workflows", persona="beginner",
      sources=[f"{WE}#the-execution-record"],
      user="one run in workflow executions shows ABORTED. what does it mean on aws?",
      steps=[S("search_docs", query="execution status aborted meaning",
               docs=[D(WE, "the-execution-record", start="| `status` | Meaning |", end="| `ABORTED` |")])],
      final="""On AWS `ABORTED` means the run was stopped [docs/workflow-executions.md#the-execution-record], for example with `pskit workflow cancel` or in the Step Functions console. See its history:

```bash
pskit workflow status <execution id> --history
```"""),

    A(810, provider="aws", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WE}#cancel-timeouts-and-restarts-embedded-engine"],
      user="How do I cap our Step Functions workflow at 15 minutes total, so a stuck run doesn't hang forever?",
      steps=[S("search_docs", query="workflow timeout step functions TimeoutSeconds",
               docs=[D(WE, "cancel-timeouts-and-restarts-embedded-engine", start="- **Timeout:**", end="On AWS it is the state machine's `TimeoutSeconds`.")])],
      final="""Set `workflows.<name>.timeout` in seconds; on AWS it becomes the state machine's `TimeoutSeconds` [docs/workflow-executions.md#cancel-timeouts-and-restarts-embedded-engine]. A run past it ends as `TIMED_OUT`.

**In code**
```yaml
workflows:
  order-pipeline:
    timeout: 900
```

**In studio**
1. Open **Workflows** and select `order-pipeline`.
2. Set *Timeout (s)* to 900 and click **Save**."""),
]
