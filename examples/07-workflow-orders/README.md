# 07 · Order workflow (Step Functions, portable)

An order pipeline that uses **every state type**, written once and compiled to:

| Cloud | Engine | Deployed as |
| --- | --- | --- |
| AWS | native | AWS Step Functions state machine (ASL) |
| GCP | native | Google Cloud Workflows |
| Azure and the other 7 clouds | embedded | an extra `order-pipeline-orchestrator` function running the pskit engine |

```
Validate ──catch ValueError──────────────────────────────► Rejected (fail)
   │
 Route (choice)
   ├─ total > 1000 AND NOT vip ─► ManualReview (wait 30s) ─┐
   ├─ channel == b2b OR currency == CHF ─► Invoice (pass) ──┼──────────────┐
   └─ default ──────────────────────────────────────────────┤              │
                                                            ▼              │
                       Reserve (map over items, 5 at a time) ─catch OutOfStock─► Rejected
                                                            │              │
                       Charge (retry PaymentGatewayTimeout x3,             │
                               catch PaymentDeclined ─► Declined (fail))   │
                                                            ▼              ▼
                                   Fulfil (parallel: Confirm ‖ Ship) ─► Done (succeed)
```

## State types used

| Type | State | Notes |
| --- | --- | --- |
| `task` | Validate, Charge, ReserveItem, Confirm, Ship | `function:` is a function name from `functions:` |
| `choice` | Route | `and` / `or` / `not`, numeric `gt`, string `equals` |
| `wait` | ManualReview | `seconds` or `seconds_path` |
| `pass` | Invoice | injects `result` at `result_path` |
| `map` | Reserve | `items_path`, `iterator`, `max_concurrency` |
| `parallel` | Fulfil | list of `branches`, the result is a list |
| `succeed` / `fail` | Done / Declined / Rejected | `error` + `cause` |

**Data flow:** every state receives the whole document (`input_path` narrows it). A task's
return value is stored at `result_path`: `$` replaces the document, `$.payment` adds a field,
and `null` discards the result.

**Errors:** an exception's **class name** is its error name. `retry: [{errors: [PaymentGatewayTimeout]}]`
and `catch: [{errors: [PaymentDeclined]}]` work the same way on Step Functions, Cloud
Workflows and the embedded engine. Use `*` to match everything.

Choice operators: `equals`, `not_equals`, `gt`, `gte`, `lt`, `lte`, `in`, `contains`,
`matches` (glob), `is_null`, `is_present`, plus `and` / `or` / `not`.

> AWS Step Functions fails a choice that reads a missing field. That's why `validate-order`
> normalises the order (fills in `customer.vip`, `currency`, `channel`) before `Route` reads it.

## Run locally (embedded engine)

```bash
pskit workflow run order-pipeline -i @events/happy.json      # retry kicks in, then SUCCEEDED
pskit workflow run order-pipeline -i @events/declined.json   # FAILED PaymentDeclined
pskit workflow run order-pipeline -i @events/b2b.json        # Invoice branch, no charge
pskit workflow run order-pipeline -i @events/happy.json --history   # every state transition
```

Wait states are skipped locally unless you pass `--sleep`.

Expected output of the happy path (abridged):

```json
{
  "order_id": "o-1001",
  "total": 34.0,
  "reservations": [{"sku": "sku-book", "qty": 2, "reserved": true}, {"sku": "sku-mug", "qty": 1, "reserved": true}],
  "payment": {"status": "charged", "amount": 34.0, "currency": "EUR"},
  "fulfilment": [{"email_sent_to": "ada@example.com"}, {"carrier": "DHL", "tracking": "TRK-o-1001"}]
}
```

## See what gets deployed

```bash
pskit workflow show order-pipeline --format asl    # Amazon States Language
pskit workflow show order-pipeline --format gcp    # Cloud Workflows source
pskit workflow show order-pipeline --format json   # the portable definition
```

## Deploy

```bash
pskit deploy                      # Step Functions + 5 Lambdas
pskit deploy --provider gcp       # Cloud Workflows + 5 Cloud Functions (called with OIDC)
pskit deploy --provider azure     # 5 functions + order-pipeline-orchestrator
```

Start an execution:

- **AWS:** `aws stepfunctions start-execution --state-machine-arn <arn from pskit info> --input file://events/happy.json`
- **GCP:** `gcloud workflows run order-workflow-dev-order-pipeline --data="$(cat events/happy.json)"`
- **Embedded engine:** `POST <endpoint>/workflows/order-pipeline` with the JSON input. The response is
  `{"status": "SUCCEEDED", "output": ...}`, or HTTP 500 with `error` / `cause`.

### Native vs embedded

The embedded engine runs the whole workflow **inside one function invocation**. Its tasks
are called in-process, because they live in the same bundle. The trade-offs:

- total duration is capped by the function timeout (Azure consumption: 10 minutes);
- long `wait` states keep the function running (and billed);
- there is no execution history in a cloud console; use the logs.

Use `engine: native` to fail validation on clouds without a native engine, or
`engine: embedded` to force the embedded engine everywhere. That keeps behaviour
identical across clouds.
