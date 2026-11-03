# Concept: workflows

A workflow chains functions with branching, retries, waits, parallel branches, and fan-out. You define it once under `workflows` in pskit.yml. pskit runs it natively as AWS Step Functions, Google Cloud Workflows, or, when you set `engine: native`, Azure Logic Apps. Every other target uses the embedded engine inside an auto-generated `<workflow>-orchestrator` function. On premises that function runs inside the long-lived host, so the workflow is not cut off by a function timeout. `pskit workflow run` uses the same embedded engine locally.

Required keys are `start_at` (it must name a state) and `states`. `description` defaults to an empty string. `engine` defaults to `auto`: native on aws and gcp, embedded elsewhere, including Azure until you opt in. `native` is an error on a cloud without a native engine. `embedded` forces the embedded engine everywhere. `enabled` defaults to true. False keeps the workflow in the file and skips it on deploy. `timeout` is the AWS TimeoutSeconds, the embedded orchestrator function timeout capped at the provider maximum, and a limit the embedded engine enforces by ending the run `TIMED_OUT`.

`options.type` is AWS only: `STANDARD` or `EXPRESS`, default `STANDARD`. `options.http` is embedded only and defaults to true. False removes the orchestrator's HTTP trigger. `options.start_on_entry` is on premises only and defaults to true. `options.sync` is Azure native only and defaults to true. False drops the Response actions so the caller gets 202 at once.

Every `next`, `default`, and `catch.next` must name a state. Every `function` must exist under `functions`. Task handlers receive `event.type == "workflow"` and the state input in `event.data`. Their return value is the task result. Error names in `retry` and `catch` are the Python exception class names the handler raises.

Sources: `docs/workflows.md#workflows-state-machines`, `docs/workflows.md#workflow-keys`, `src/py_serverless_kit/config/schema.py`

```text
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
