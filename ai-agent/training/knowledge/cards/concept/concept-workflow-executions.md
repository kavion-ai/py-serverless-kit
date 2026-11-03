# Workflow executions Every workflow run has an **execution id .

You get it back when you start a run, then use it to follow the run's status, current state, history and output from the CLI, the dashboard or HTTP. | Engine | Start returns | History you can browse | Cancel | |---|---|---|---| | on-premises (embedded engine in the host) | `202` + `execution_id` at once; `?wait=true` for the result | yes, persisted on the host | yes | | AWS Step Functions (native) | execution ARN | yes, through the Step Functions API | yes (`StopExecution`) | | Google Cloud Workflows (native) | execution resource name | yes, through the Executions API | yes | | embedded orchestrator on a cloud function | the result **and** `execution_id` (synchronous) | no: the run lives in one function call | no |
## Starting a run `--wait` waits for the result (on-premises)

. Native engines always return at once. `--json` prints the raw response.
### On premises over HTTP `POST /workflows/<name>` (the orchestrator's route)

and `POST /__pskit/workflows/<name>` (admin) both start the run in the background: To wait for the result instead, use any one of these: - `?wait=true` (also `1`, `yes`, `on`) - `Prefer: wait`, or any `Prefer` value containing `wait` - `x-pskit-wait: true` A synchronous run answers `200` with `{"execution_id", "workflow", "status", "output", "duration_ms", "started_at", "stopped_at"}`. On failure it answers `500` with `error` and `cause` instead of `output`. A run started with `invoke()` from a handler, or by any other non-HTTP event, is synchronous too. Every run is recorded either way. The body is the workflow input. With no body, the query parameters (except `wait`) become the input. > **Changed in this release.** On premises, `POST /workflows/<name>` used to return the result synchronously. Clients that expect `output` in the response must add `?wait=true`.
### Embedded orchestrator on a cloud

On the other clouds the run happens inside the orchestrator function, so the response always carries the result: A failure answers `500` with `status` set to `FAILED` (or `TIMED_OUT`), plus `error`, `cause` and `execution_id`. No history is kept. `pskit workflow start` posts to the orchestrator's HTTP URL and prints this result. `pskit workflow executions` explains why there's nothing to list.

```bash
pskit workflow start order-pipeline -i '{"amount": 50}'
```
