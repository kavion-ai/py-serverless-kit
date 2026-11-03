# Concept: workflow engines and commands

AWS deploys `aws_sfn_state_machine` plus an IAM role that can invoke the task Lambdas. GCP deploys `google_workflows_workflow`. Tasks are OIDC-authenticated HTTP calls. Azure with `engine: native` deploys a Logic App. Tasks call `/_pskit/invoke/<function>` with the function key. Everywhere else, or with `engine: embedded`, pskit adds `<workflow>-orchestrator`. It runs the state machine and calls task handlers in-process in the same bundle.

Invoke the embedded orchestrator with `POST /workflows/<workflow>` and a JSON body when HTTP is available and `options.http` is not false, or invoke it directly. On a cloud the response is synchronous: status `SUCCEEDED` with `output`, or HTTP 500 with status `FAILED`. On premises the host answers 202 with `execution_id` at once, and `?wait=true` returns the result. The run can be listed, followed, and cancelled.

On premises, a workflow whose first state is a task also starts when that function runs on its own, unless `options.start_on_entry` is false. The call's input is the workflow input. The function does not run twice. An HTTP status of 400 or more starts nothing. Other clouds do not do this.

The whole embedded run must fit in one function invocation. The doc gives examples of 900 s on AWS, Huawei, and Tencent, 600 s on Azure, and 120 s on IBM. `pskit validate` warns when a long wait will not fit. GCP uses only the first retry rule, and only on task states. Azure Logic Apps also uses only the first retry rule, ignores the errors filter and `backoff_rate`, runs map iterations one at a time, and stops after 5000 states or `timeout` (default 1 hour).

```
pskit workflow run order-pipeline -i "{"amount": 50}"
pskit workflow show order-pipeline --format asl
pskit workflow executions order-pipeline --status RUNNING
```

`workflow run` exits 2 when the run fails. Wait states are skipped unless `--sleep` is set. `--history` prints the execution history. Deployed start, status, and cancel work against the on-premises host, AWS Step Functions, and Google Cloud Workflows.

Sources: `docs/workflows.md#engines`, `docs/workflows.md#embedded-orchestrator`, `docs/workflows.md#commands`
