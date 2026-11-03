# Build and run a workflow

Search terms: workflow, state machine, step functions, cloud workflows, logic apps, orchestration, orchestrator,
workflow builder, execution, execution id, pskit workflow run, pskit workflow start, status, history, cancel, retry,
catch, choice, parallel, map

A workflow chains functions into a state machine: steps run one after another, with branches, retries, error
handling, waits, parallel branches and loops over a list. You describe it once under `workflows:` in `pskit.yml`, or
draw it in the studio builder, and pskit runs it on every provider. The full key and operator reference is in
[workflows.md](../workflows.md); execution records are in [workflow-executions.md](../workflow-executions.md).

## Build a workflow in pskit.yml

A workflow needs functions for its `task` states, a `start_at` state and a map of `states`.

1. Write the task handlers. A task gets `event.type == "workflow"` and the state input in `event.data`; what it
   returns is the task result. A raised exception is the error that `retry` and `catch` match by class name.

   ```python
   def validate(event, ctx):
       order = dict(event.data)
       if order.get("amount", 0) <= 0:
           raise ValueError("amount must be positive")
       return {**order, "valid": True}


   def charge(event, ctx):
       return {"charged": event.data["amount"]}
   ```

2. Declare the functions and the workflow:

   ```yaml
   functions:
     validate: {handler: app.orders.validate}
     charge: {handler: app.orders.charge}

   workflows:
     order-pipeline:
       description: Validate and charge
       start_at: Validate
       states:
         Validate:
           type: task
           function: validate
           retry: [{errors: [TimeoutError], max_attempts: 3, interval_seconds: 2, backoff_rate: 2}]
           catch: [{errors: [ValueError], next: Rejected}]
           next: Charge
         Charge: {type: task, function: charge, result_path: "$.payment", end: true}
         Rejected: {type: fail, error: OrderRejected, cause: validation failed}
   ```

3. Check it: `pskit validate`. Every `next`, `default` and `catch.next` must name a state, and every `function` must
   exist under `functions`.

Full example: [`examples/07-workflow-orders`](../../examples/07-workflow-orders).

## Workflow state types

A workflow state has one of eight types:

| Type | What it does | Main keys |
|---|---|---|
| `task` | calls a function | `function`, `input_path`, `result_path`, `retry`, `catch`, `timeout_seconds` |
| `choice` | branches on the data | `choices` (rules with `next`), `default` |
| `wait` | pauses | `seconds` or `seconds_path` |
| `pass` | passes the data on, or injects `result` | `result`, `result_path` |
| `parallel` | runs branches at the same time; the result is a list | `branches` (each `{start_at, states}`) |
| `map` | runs steps for every item of a list; the result is a list | `items_path`, `iterator`, `max_concurrency` |
| `succeed` | stops successfully | |
| `fail` | stops with an error | `error`, `cause` |

`task`, `wait`, `pass`, `parallel` and `map` move on with `next` or stop with `end: true` (no `next` means end).
`result_path: "$.payment"` stores the result under that key; `null` drops it and passes the input on. Choice
operators (`equals`, `gt`, `in`, `matches`, `is_present`, `and`, `or`, `not`, ...) are listed in
[workflows.md](../workflows.md#choice-rules).

## Build a workflow in the studio builder

The studio **Workflows** page draws the workflow as a diagram and writes `workflows:` for you.

1. Click **Workflows** in the sidebar, then **+ Create workflow**.
2. In **New workflow**, type the **Name** and click **Create**. The workflow starts with one `pass` state, `Start`.
3. Add states from the palette above the diagram: **task**, **choice**, **wait**, **pass**, **parallel**, **map**,
   **succeed**, **fail**. A new state is chained after the selected state when that state simply ends.
4. Click a state in the diagram. The panel on the right shows its fields:
   - every state: **State name** (with **Rename**), **Comment**, and **Delete**;
   - task: **Function** (pick one, or **+ New** to create a function), **Timeout (s)**, **Retry (N)** and
     **Catch (N)** lists with **+ retry rule** and **+ catch rule**;
   - choice: **Rules** (each rule is *if*, *if not*, *all of* or *any of*, with **+ condition**, then *then go to*),
     **+ Add rule**, and **Otherwise** (empty means the run fails with `States.NoChoiceMatched`);
   - wait: **Wait** (*Fixed seconds* or *From the data*), **Seconds** or **Seconds path**;
   - pass: **Result** (JSON); fail: **Error**, **Cause**;
   - map: **Items path**, **Max concurrency**, **Steps per item** → **Edit iterator (N states) →**;
   - parallel: **Branches** → **Branch N · M states →**, **+ Add branch**;
   - **Then**: **Go to** a state, or **End**; **Data paths**: **Input path**, **Result path**.
5. Use **Starts at** above the diagram to pick the first state.
6. Inside a branch or iterator, the breadcrumb at the top leads back to the parent workflow.
7. Open **Settings** for **Description**, **Engine** (*auto*, *native*, *embedded*) and **Timeout (s)**.
8. Click **Save** in the top bar (Ctrl+S). Problems show as red marks on the states and in the top bar's problem list.

The workflow cards on the **Workflows** page show the engine, an on/off control for the current provider, and
**Delete**.

## Pick the workflow engine

The workflow engine decides where the state machine runs. `engine: auto` (the default) picks per provider:

| Provider | `auto` uses | What is deployed |
|---|---|---|
| aws | native | AWS Step Functions state machine (ASL) |
| gcp | native | Google Cloud Workflows workflow |
| azure | embedded (`engine: native` gives Azure Logic Apps) | an orchestrator function, or a Logic App |
| onprem | embedded | runs inside the host process, so no function timeout cuts it off |
| all others | embedded | an extra function `<workflow>-orchestrator` that runs the tasks in-process |

`engine: native` fails validation on a provider without a native engine. `engine: embedded` forces the embedded
engine everywhere. On a cloud the embedded run must fit in one function call (the provider's maximum timeout);
`pskit validate` warns when it may not. Print the compiled definition with `pskit workflow show`:

```bash
pskit workflow show order-pipeline                 # for the current provider
pskit workflow show order-pipeline --format asl    # auto | asl | gcp | json
```

## Run a workflow locally before deploying

`pskit workflow run` runs the workflow on this machine with the embedded engine and the real handlers. Nothing is
deployed. `wait` states are skipped unless you pass `--sleep`.

```bash
pskit workflow run order-pipeline -i '{"amount": 50}'
pskit workflow run order-pipeline -i @input.json --history --sleep
```

`--history` prints every state the run entered and left. The command exits with code 2 when the run fails.

In studio: **Deploy** → expand **Run a workflow locally** → pick the **Workflow**, type the **Input (JSON)** → click
**Run**. The output appears in the job console (it runs `pskit workflow run --history`).

## Start a deployed workflow

`pskit workflow start` starts the deployed workflow and prints its execution id.

```bash
pskit workflow start order-pipeline -i '{"amount": 50}' -s dev
pskit workflow start order-pipeline -i @input.json --wait --json
```

| Engine | What start returns |
|---|---|
| on premises | the execution id at once (`RUNNING`); `--wait` waits for the result |
| AWS Step Functions, Google Cloud Workflows | the execution id at once |
| embedded orchestrator on a cloud | the result and the execution id (the run is synchronous) |

Other ways to start a run:

- HTTP to the orchestrator: `POST /workflows/<name>` with the input as JSON body (embedded engine, unless
  `options.http: false`). On premises it answers `202` with the id; add `?wait=true` for the result.
- On premises, a workflow whose first state is a `task` also starts when that function runs on its own (its HTTP
  route, a schedule, a queue, ...). Turn this off with `options.start_on_entry: false`.
- The dashboard: `pskit dashboard --serve`, then **Workflows** → **▶ Start**
  ([monitoring and dashboard](monitoring-and-dashboard.md)).

## Follow a workflow execution: status and history

Every run has an execution id. Use it to read the status, the current state, the history, the output or the error.

```bash
pskit workflow executions                              # newest runs of every workflow
pskit workflow executions order-pipeline --status FAILED -n 50
pskit workflow status <execution-id> --watch           # poll until it finishes
pskit workflow status <execution-id> --history         # every state entered and left
pskit workflow status <execution-id> -w order-pipeline --json
```

| Flag | Command | Meaning |
|---|---|---|
| `--status` | `executions` | `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED` or `ABORTED` |
| `-n, --limit` | `executions` | page size (default 20) |
| `--offset` | `executions` | skip this many (on premises) |
| `--token` | `executions` | next-page token printed by the previous call (AWS, GCP) |
| `-w, --workflow` | `status`, `cancel` | the workflow name; helps AWS and GCP find the id |
| `--history`, `--watch`, `--json` | `status` | print the history, poll until done, raw JSON |

History is kept by the on-prem host, AWS Step Functions and Google Cloud Workflows. An embedded orchestrator on a
cloud keeps no history: the run lives in one function call. AWS and GCP need the matching extra:
`pip install "py-serverless-kit[aws]"` or `"py-serverless-kit[gcp]"`.

## Cancel a running workflow execution

`pskit workflow cancel` stops a run.

```bash
pskit workflow cancel <execution-id>
pskit workflow cancel <execution-id> -w order-pipeline     # AWS / GCP
```

On the embedded engine the run stops before its next state (a running task finishes first) and becomes `CANCELLED`.
On AWS the execution is stopped (`ABORTED`). Embedded orchestrators on other clouds can't be cancelled. In the
dashboard: **Executions** → click a run → **Cancel**.

## Tune workflow executions on premises

The on-prem host keeps the newest 500 finished execution records (`provider.options.execution_retention`) and runs up
to 8 executions at once (`provider.options.workflow_workers`). Runs left `RUNNING` when the host restarts become
`ABORTED`. In studio: **Overview & provider** → **Host tuning**. `workflows.<name>.timeout` (seconds) ends a run as
`TIMED_OUT` on every engine.

## Turn a workflow off on one provider

A workflow can stay in `pskit.yml` but skip one provider:

```yaml
providers:
  cloudflare:
    workflows:
      order-pipeline: {enabled: false}
```

A workflow that calls a disabled function is a validation error. In studio, the **Deploy** page offers **Disable
workflow on PROVIDER** when the workflow can't run there.

## See also

- [Workflows reference](../workflows.md) and [workflow executions](../workflow-executions.md)
- [Deployment types](README.md)
- [Logs](logs.md)
- [Monitoring and dashboard](monitoring-and-dashboard.md)
- [Studio guide](../studio-guide/README.md)
- [Migrating Step Functions](../migrating-from-aws.md)
