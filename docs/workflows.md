# Workflows (state machines)

A workflow chains functions with branching, retries, error handling, waits, parallel branches and fan-out. You define it once in `pskit.yml`, and pskit runs it:

- **natively**, as AWS Step Functions (ASL), Google Cloud Workflows or (opt-in, `engine: native`) Azure Logic Apps;
- on the **embedded engine** on every other target, inside an auto-generated orchestrator function (on premises that function runs inside the long-lived host, so the workflow is not cut off by a function timeout);
- **locally** with `pskit workflow run`, using the same engine.

```yaml
functions:
  validate: {handler: app.orders.validate}
  charge:   {handler: app.orders.charge}
  notify:   {handler: app.orders.notify}

workflows:
  order-pipeline:
    description: Validate, charge and notify
    start_at: Validate
    states:
      Validate:
        type: task
        function: validate
        retry: [{errors: [TimeoutError], max_attempts: 3, interval_seconds: 2, backoff_rate: 2}]
        catch: [{errors: [ValueError], next: Rejected}]
        next: Route
      Route:
        type: choice
        choices:
          - {variable: "$.amount", gt: 1000, next: ManualReview}
        default: Charge
      ManualReview: {type: wait, seconds: 3600, next: Charge}
      Charge:       {type: task, function: charge, result_path: "$.payment", next: Notify}
      Notify:       {type: task, function: notify, result_path: null, end: true}
      Rejected:     {type: fail, error: OrderRejected, cause: validation failed}
```

Task handlers receive `event.type == "workflow"` and the state input in `event.data`. Whatever they return is the task result:

```python
def validate(event, ctx):
    order = dict(event.data)
    if order.get("amount", 0) <= 0:
        raise ValueError("amount must be positive")   # matched by catch: errors: [ValueError]
    return {**order, "valid": True}
```

Full example: [`examples/07-workflow-orders`](../examples/07-workflow-orders).

## Workflow keys

| Key | Default | Notes |
|---|---|---|
| `start_at` | — | required; must name a state |
| `states` | — | map of state name → state |
| `description` | `""` | |
| `engine` | `auto` | `auto` = native where supported (aws, gcp), embedded elsewhere (also on Azure, where native is opt-in); `native` errors on clouds without native support; `embedded` forces the engine everywhere |
| `timeout` | — | AWS `TimeoutSeconds`; embedded orchestrator function timeout (capped at the provider's max), also enforced by the embedded engine (the run ends `TIMED_OUT`) |
| `options.type` | `STANDARD` | AWS only: `STANDARD` or `EXPRESS` |
| `options.http` | `true` | embedded only: `false` removes the orchestrator's HTTP trigger |
| `options.start_on_entry` | `true` | on premises only: `false` stops the workflow from starting when its first task function runs on its own (see below) |
| `options.sync` | `true` | Azure native only: `false` drops the `Response` actions, so the caller gets `202` at once instead of the output |

All `next` / `default` / `catch.next` targets are checked to exist, and every `function` must be defined under `functions`.

## State types

| `type` | Fields | Behaviour |
|---|---|---|
| `task` | `function`, `next`/`end`, `input_path`, `result_path`, `retry`, `catch`, `timeout_seconds` | call a function |
| `choice` | `choices` (rules with `next`), `default` | branch; with no match and no default the run fails with `States.NoChoiceMatched` |
| `wait` | `seconds` or `seconds_path`, `next`/`end` | sleep |
| `pass` | `result`, `result_path`, `next`/`end` | inject a value (or pass the input through) |
| `parallel` | `branches` (each `{start_at, states}`), `result_path`, `next`/`end` | run branches concurrently; result is a list (one item per branch) |
| `map` | `items_path`, `iterator` (`{start_at, states}`), `max_concurrency`, `result_path`, `next`/`end` | run the iterator for each item; result is a list |
| `succeed` | — | finish successfully with the current data |
| `fail` | `error`, `cause` | finish with an error |

`task`, `wait`, `pass`, `parallel` and `map` without `next` are treated as `end: true`. Every state can have a `comment`.

### Data flow

The JSON path dialect is `$`, `$.a.b`, `$.items[0]`, `$['key']`.

- `input_path` selects the part of the state input that is passed to the task (default `$`, the whole input).
- `result_path` says where the result goes in the state's data:
  - `$` (default) replaces the data with the result;
  - `$.payment` stores the result under that key and keeps the rest;
  - `null` discards the result and passes the input through.

### Choice rules

```yaml
choices:
  - {variable: "$.status", equals: "paid", next: Ship}
  - {variable: "$.amount", gte: 100, next: Review}
  - and:
      - {variable: "$.country", in: [IN, US]}
      - not: {variable: "$.vip", equals: true}
    next: Standard
  - or: [{variable: "$.email", is_present: false}, {variable: "$.email", is_null: true}]
    next: AskEmail
```

| Operator | Meaning |
|---|---|
| `equals`, `not_equals` | equality (any JSON type; `equals: null` checks for null) |
| `gt`, `gte`, `lt`, `lte` | numeric or string comparison |
| `in` | value is one of a list |
| `contains` | substring / membership |
| `matches` | glob pattern (`*`, `?`) |
| `is_null` | `true` / `false` |
| `is_present` | the path exists (`true` / `false`) |
| `and`, `or`, `not` | combinators; can be nested |

A rule whose variable is missing or of the wrong type evaluates to false instead of failing.

### Retry and catch

```yaml
retry:
  - errors: [TimeoutError, ConnectionError]   # exception class names; "*" or "States.ALL" = any
    max_attempts: 3                            # default 3
    interval_seconds: 1                        # default 1
    backoff_rate: 2.0                          # default 2.0
    max_delay_seconds: 60                      # optional cap
catch:
  - errors: ["*"]
    next: HandleError
    result_path: "$.error"                    # default; stores {"error": "...", "cause": "..."}
```

Error names are the **Python exception class names** your handler raises (e.g. `ValueError`). The first matching retrier is used. When retries are exhausted, the first matching catcher routes to its `next` state. Without a match the run fails.

## Engines

| Provider | Engine | What gets deployed |
|---|---|---|
| aws | native | `aws_sfn_state_machine` (ASL) + an IAM role that can invoke the task Lambdas |
| gcp | native | `google_workflows_workflow`; tasks are OIDC-authenticated HTTP calls to the functions |
| azure (`engine: native`) | native | a Logic App (`azurerm_logic_app_workflow` + HTTP request trigger + actions); tasks call `/_pskit/invoke/<function>` with the function key |
| all others (or `engine: embedded`) | embedded | an extra function `<workflow>-orchestrator` that runs the state machine and calls task handlers **in-process** (same bundle) |

### Embedded orchestrator

- Invoke it with `POST /workflows/<workflow>` and the JSON input as the body (when the provider supports HTTP and `options.http` isn't `false`), or invoke it directly.
- Every run has an `execution_id`. On a cloud the response is synchronous: `{"execution_id": ..., "workflow": ..., "status": "SUCCEEDED", "output": ..., "duration_ms": ...}`, or HTTP 500 `{"execution_id": ..., "status": "FAILED", "error": ..., "cause": ...}`.
- On premises the run is tracked by the host. `POST /workflows/<workflow>` answers `202` with the `execution_id` at once (`?wait=true` returns the result), and the run can be listed, followed and cancelled. See [Workflow executions](workflow-executions.md).
- On premises, a workflow whose first state is a `task` also starts when that function runs **on its own**: its HTTP route, `invoke()`, `pskit trigger`, a schedule, a queue and so on. The call's input becomes the workflow input, and the function's result is used as the first state's result, so the function does not run twice. The function's own response is unchanged. An HTTP response carries the run's id in `x-pskit-execution-id`. A failed call (an exception, or an HTTP status of 400 or more) starts nothing. Calls made by the workflow itself never start another run. With placement, the run starts on the default group even when the function runs on another group's server. Set `options.start_on_entry: false` to turn this off. Other clouds don't do this: start the workflow itself there.
- The **whole run must fit in one function invocation**: total time ≤ the provider's max timeout (e.g. 900 s on AWS/Huawei/Tencent, 600 s on Azure, 120 s on IBM). Long `wait` states don't fit; use a native engine or split the workflow. `pskit validate` warns about this.
- The HTTP route is public when the provider's HTTP is public. Set `options.http: false` for sensitive workflows.

### Compiler notes and limits

- **AWS:** `IntervalSeconds` is rounded to ≥ 1. `map` uses an inline `ItemProcessor`. `contains` compiles to `StringMatches *x*`.
- **GCP:** only the **first** retry rule of a task is used (Cloud Workflows allows one retry policy). `retry`/`catch` are honoured on `task` states only (ignored on `parallel`/`map`, with a warning). Task HTTP timeouts are capped at 1800 s.
- **Azure (Logic Apps):** the state machine runs as an interpreter: an `Until` loop over a `Switch` on the current state, with the data kept as a JSON string variable. The HTTP trigger answers with the output (`200`) or `{"error", "cause"}` (`500`); a synchronous `Response` must come within about 2 minutes, so set `options.sync: false` for long workflows. Only the **first** retry rule of a task is used, as Logic Apps' exponential retry policy (it retries 408/429/5xx responses: the `errors` filter and `backoff_rate` are ignored, intervals are 5 s–1 day, at most 90 retries). `retry`/`catch` work on `task` states only. Task calls time out after 120 s (the Logic Apps limit for outbound HTTP), and `pskit validate` warns when a task function's timeout is longer. `map` iterations run one at a time (`max_concurrency` is ignored). `matches` accepts `abc`, `abc*`, `*abc`, `*abc*` and `*`; other globs are a validation error. `is_present` treats `null` like a missing key. `result_path` can't contain array indexes. Logic Apps allow 8 levels of nesting, so `parallel` states can nest at most three deep and `map` states two deep. A run stops after 5000 states or `timeout` (default 1 hour).

## Commands

```bash
pskit workflow run order-pipeline -i '{"amount": 50}'           # local, embedded engine; wait states skipped
pskit workflow run order-pipeline -i @events/order.json --sleep --history
pskit workflow show order-pipeline                              # compiled for the current provider
pskit workflow show order-pipeline --format asl                 # asl | gcp | json
```

`workflow run` exits with code 2 when the run fails.

Deployed workflows:

```bash
pskit workflow start order-pipeline -i '{"amount": 50}'          # prints the execution_id
pskit workflow executions order-pipeline --status RUNNING
pskit workflow status <execution_id> --watch --history
pskit workflow cancel <execution_id>
```

These work against the on-premises host, AWS Step Functions and Google Cloud Workflows. See [Workflow executions](workflow-executions.md).

## Migrating Step Functions ASL

| ASL | pskit |
|---|---|
| `"Type": "Task"`, `"Resource": "arn:…:function:x"` | `type: task`, `function: x` |
| `Choice` + `NumericGreaterThan` / `StringEquals` / `BooleanEquals` / `IsPresent` / `IsNull` / `StringMatches` | `gt` / `equals` / `equals` / `is_present` / `is_null` / `matches` |
| `And` / `Or` / `Not` | `and` / `or` / `not` |
| `Wait` `Seconds` / `SecondsPath` | `seconds` / `seconds_path` |
| `Pass` `Result` | `pass` `result` |
| `Parallel` `Branches` | `parallel` `branches` |
| `Map` `ItemsPath` + `Iterator`/`ItemProcessor` + `MaxConcurrency` | `map` `items_path` + `iterator` + `max_concurrency` |
| `Retry` `ErrorEquals` / `MaxAttempts` / `IntervalSeconds` / `BackoffRate` / `MaxDelaySeconds` | `retry` `errors` / `max_attempts` / `interval_seconds` / `backoff_rate` / `max_delay_seconds` |
| `Catch` `ErrorEquals` / `Next` / `ResultPath` | `catch` `errors` / `next` / `result_path` |
| `States.ALL` | `"*"` (or `States.ALL`) |
| `InputPath` / `ResultPath` | `input_path` / `result_path` |
| `Succeed` / `Fail` (`Error`, `Cause`) | `succeed` / `fail` (`error`, `cause`) |

Not supported: `Parameters`/`ResultSelector`/`OutputPath`, intrinsic functions, `.sync`/callback service integrations, and timestamp waits. Do that shaping in a small task function instead. Walkthrough: [migrating-from-aws.md](migrating-from-aws.md).
