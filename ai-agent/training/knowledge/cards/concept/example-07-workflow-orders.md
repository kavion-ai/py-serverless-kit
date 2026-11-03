# Example: 07-workflow-orders

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.yml, requirements.txt. Comments in pskit.yml:
# 07 · Order workflow (Step Functions, portable) An order pipeline that uses

**every state type**, written once and compiled to: | Cloud | Engine | Deployed as | | --- | --- | --- | | AWS | native | AWS Step Functions state machine (ASL) | | GCP | native | Google Cloud Workflows | | Azure and the other 7 clouds | embedded | an extra `order-pipeline-orchestrator` function running the pskit engine |
## State types used | Type | State | Notes | | --- | --- | --- | | `task` |

Validate, Charge, ReserveItem, Confirm, Ship | `function:` is a function name from `functions:` | | `choice` | Route | `and` / `or` / `not`, numeric `gt`, string `equals` | | `wait` | ManualReview | `seconds` or `seconds_path` | | `pass` | Invoice | injects `result` at `result_path` | | `map` | Reserve | `items_path`, `iterator`, `max_concurrency` | | `parallel` | Fulfil | list of `branches`, the result is a list | | `succeed` / `fail` | Done / Declined / Rejected | `error` + `cause` | **Data flow:** every state receives the whole document (`input_path` narrows it). A task's return value is stored at `result_path`: `$` replaces the document, `$.payment` adds a field, and `null` discards the result. **Errors:** an exception's **class name** is its error name. `retry: [{errors: [PaymentGatewayTimeout]}]` and `catch: [{errors: [PaymentDeclined]}]` work the same way on Step Functions, Cloud Workflows and the embedded engine. Use `*` to match everything. Choice operators: `equals`, `not_equals`, `gt`, `gte`, `lt`, `lte`, `in`, `contains`, `matches` (glob), `is_null`, `is_present`, plus `and` / `or` / `not`. > AWS Step Functions fails a choice that reads a missing field. That's why `validate-order` > normalises the order (fills in `customer.vip`, `currency`, `channel`) before `Route` reads it.
## Run locally (embedded engine) Wait states are skipped locally unless you pass

`--sleep`. Expected output of the happy path (abridged):
## Deploy Start an execution: - **AWS:** `aws stepfunctions start-execution

--state-machine-arn <arn from pskit info> --input file://events/happy.json` - **GCP:** `gcloud workflows run order-workflow-dev-order-pipeline --data="$(cat events/happy.json)"` - **Embedded engine:** `POST <endpoint>/workflows/order-pipeline` with the JSON input. The response is `{"status": "SUCCEEDED", "output": ...}`, or HTTP 500 with `error` / `cause`.
### Native vs embedded

The embedded engine runs the whole workflow **inside one function invocation**. Its tasks are called in-process, because they live in the same bundle.
