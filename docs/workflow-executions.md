# Workflow executions

Every workflow run has an **execution id**. You get it back when you start a run, then use it to follow the run's status, current state, history and output from the CLI, the [dashboard](dashboard.md) or HTTP.

| Engine | Start returns | History you can browse | Cancel |
|---|---|---|---|
| on-premises (embedded engine in the host) | `202` + `execution_id` at once; `?wait=true` for the result | yes, persisted on the host | yes |
| AWS Step Functions (native) | execution ARN | yes, through the Step Functions API | yes (`StopExecution`) |
| Google Cloud Workflows (native) | execution resource name | yes, through the Executions API | yes |
| embedded orchestrator on a cloud function | the result **and** `execution_id` (synchronous) | no: the run lives in one function call | no |

## Starting a run

```bash
pskit workflow start order-pipeline -i '{"amount": 50}'
```
```
execution_id: 019a15d27569d180422fe2143473
status:       RUNNING
Follow it with: pskit workflow status 019a15d27569d180422fe2143473 --watch
```

`--wait` waits for the result (on-premises). Native engines always return at once. `--json` prints the raw response.

### On premises over HTTP

`POST /workflows/<name>` (the orchestrator's route) and `POST /__pskit/workflows/<name>` (admin) both start the run in the background:

```bash
curl -s -X POST http://127.0.0.1:8080/workflows/ping -H 'content-type: application/json' -d '{"order": 1}'
```
```json
{"execution_id": "019a15d27569d180422fe2143473", "workflow": "ping", "status": "RUNNING",
 "started_at": "2026-10-21T06:30:21.597+00:00", "stopped_at": null, "duration_ms": null,
 "current_state": null, "source": "embedded", "console": null,
 "status_url": "/__pskit/executions/019a15d27569d180422fe2143473"}
```

To wait for the result instead, use any one of these:

- `?wait=true` (also `1`, `yes`, `on`)
- `Prefer: wait`, or any `Prefer` value containing `wait`
- `x-pskit-wait: true`

A synchronous run answers `200` with `{"execution_id", "workflow", "status", "output", "duration_ms", "started_at", "stopped_at"}`. On failure it answers `500` with `error` and `cause` instead of `output`. A run started with `invoke()` from a handler, or by any other non-HTTP event, is synchronous too. Every run is recorded either way.

The body is the workflow input. With no body, the query parameters (except `wait`) become the input.

> **Changed in this release.** On premises, `POST /workflows/<name>` used to return the result synchronously. Clients that expect `output` in the response must add `?wait=true`.

### Embedded orchestrator on a cloud

On the other clouds the run happens inside the orchestrator function, so the response always carries the result:

```json
{"execution_id": "019a15d2...", "workflow": "ping", "status": "SUCCEEDED", "output": {...}, "duration_ms": 12.4}
```

A failure answers `500` with `status` set to `FAILED` (or `TIMED_OUT`), plus `error`, `cause` and `execution_id`. No history is kept. `pskit workflow start` posts to the orchestrator's HTTP URL and prints this result. `pskit workflow executions` explains why there's nothing to list.

## The execution record

```json
{
  "execution_id": "019a15d27569d180422fe2143473",
  "workflow": "order-pipeline",
  "status": "RUNNING",
  "started_at": "2026-10-21T06:30:21.597+00:00",
  "stopped_at": null,
  "duration_ms": null,
  "current_state": "Charge",
  "source": "embedded",
  "console": null,
  "input": {"amount": 50},
  "output": null,
  "error": null,
  "cause": null,
  "history": [
    {"ts": "...", "state": "Validate", "type": "task", "event": "enter"},
    {"ts": "...", "state": "Validate", "type": "task", "event": "exit", "duration_ms": 4.1},
    {"ts": "...", "state": "Charge", "type": "task", "event": "enter"}
  ]
}
```

| `status` | Meaning |
|---|---|
| `RUNNING` | in progress (`current_state` is the last state entered) |
| `SUCCEEDED` | finished; `output` is set |
| `FAILED` | a state failed, or a `fail` state ran; `error` is the exception class name or the `fail` state's `error` |
| `TIMED_OUT` | ran past `workflows.<name>.timeout` (`error: States.Timeout`) |
| `CANCELLED` | stopped by a cancel request (`error: States.Cancelled`) |
| `ABORTED` | the host stopped while it was running (on-premises), or the run was stopped on AWS |

History events: `enter` and `exit` (with `duration_ms`) for each state, `caught` when a `catch` rule routed an error, `retry` with `attempt` and `error`, and `fail` for a `fail` state. Long runs keep the newest 1000 entries and set `history_truncated` to the number dropped. List calls return the summary fields only (no `input`, `output`, `history`).

Execution ids from the embedded engine are hex strings that sort by start time. AWS ids are execution ARNs. GCP ids are `projects/.../workflows/.../executions/...`.

## Following a run

```bash
pskit workflow executions                          # all workflows, newest first
pskit workflow executions order-pipeline --status FAILED -n 50
pskit workflow status <id> --watch                 # poll every 2 s until it finishes
pskit workflow status <id> --history               # print every history event
pskit workflow cancel <id>
```
```
019a15d27b5a2e414a2a2164c474  order-pipeline     RUNNING    2026-10-21 06:30:45            @ Charge
019a15d27602c9960f1f5c672491  order-pipeline     SUCCEEDED  2026-10-21 06:30:24      61 ms
019a15d27569d180422fe2143473  order-pipeline     FAILED     2026-10-21 06:30:21       6 ms
... 12 more (use --offset 3)
```

Pages use `--offset` on premises, which gives a total count. AWS and GCP use the `--token` printed after a page. Without a workflow name, AWS and GCP show the newest runs across all workflows and offer no further pages. For AWS and GCP, pass `-w <workflow>` to `status` and `cancel` when the id alone doesn't identify the workflow.

The dashboard's **Executions** tab does the same with filters, pagination, a start dialog and a live detail panel (`pskit dashboard --serve`).

## Cancel, timeouts and restarts (embedded engine)

- **Cancel** stops the run before its next state, so a task that's already running finishes first. A `wait` state, or a retry back-off, wakes up at once. The cancel response has `cancel_requested: true`, and the status becomes `CANCELLED` shortly after. Cancelling a finished run returns it unchanged.
- **Timeout:** `workflows.<name>.timeout` (seconds) is enforced by the engine on premises and in cloud orchestrators. A run past it becomes `TIMED_OUT`. On AWS it is the state machine's `TimeoutSeconds`.
- **Restart:** records live in `<data_dir>/executions/<id>.json`. When the host starts, runs left `RUNNING` by the previous process are marked `ABORTED` (`cause: host restarted`) and a host note is logged. They are not resumed.
- **Retention and concurrency:** the host keeps the newest 500 records (`provider.options.execution_retention`; running ones are never pruned) and runs up to 8 executions at a time (`provider.options.workflow_workers`). Further starts queue and show `RUNNING` with no `current_state` until a worker picks them up.

## AWS Step Functions and Google Cloud Workflows

The CLI and the dashboard call the cloud APIs with your machine's default credentials. They need the matching extra:

```bash
pip install "py-serverless-kit[aws]"   # boto3: list/describe/history/start/stop executions
pip install "py-serverless-kit[gcp]"   # google-cloud-workflows: list/get/create/cancel executions
```

| | AWS | GCP |
|---|---|---|
| Credentials | `AWS_PROFILE`, env keys, SSO, instance role | `gcloud auth application-default login`, `GOOGLE_APPLICATION_CREDENTIALS` |
| Permissions | `states:ListExecutions`, `DescribeExecution`, `GetExecutionHistory`, `StartExecution`, `StopExecution` | `workflows.executions.list/get/create/cancel` (e.g. role Workflows Invoker + Viewer) |
| Status mapping | `PENDING_REDRIVE` → `RUNNING`; a `CANCELLED` filter queries `ABORTED` | `ACTIVE`/`QUEUED` → `RUNNING`, `UNAVAILABLE` → `FAILED` |
| History | `StateEntered`/`StateExited`/`*Failed` events (up to 1000) | the current step(s) only |
| `console` | link to the execution in the Step Functions console | link to the execution in the Cloud console |

The state machine / workflow id comes from `deployment.json` (`pskit info`), so deploy first. Without the extra, commands fail with a message naming the `pip install` to run.

## HTTP API (on-premises host)

Everything below except health needs the `x-pskit-token` header when `provider.options.admin_token` is set.

| Request | Response |
|---|---|
| `POST /__pskit/workflows/<name>[?wait=true]` | `202` summary + `status_url`, or `200`/`500` result |
| `GET /__pskit/executions?workflow=&status=&limit=20&offset=0` | `{"items": [summary], "total": n}`, newest first. `limit` is capped at 500 |
| `GET /__pskit/executions/<id>` | the full record, `404` when unknown |
| `POST /__pskit/executions/<id>/cancel` | the record with `cancel_requested: true` |

`pskit workflow run` (local, no deploy) still runs the engine in-process and prints the output. See [workflows.md](workflows.md#commands).
