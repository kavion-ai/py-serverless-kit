# On-prem host control API, admin token and logs

Search terms: __pskit, control API, admin token, x-pskit-token, PSKIT_ADMIN_TOKEN, health check, enqueue, publish,
host logs, host.jsonl, stats, Lambda invoke API, SQS API, endpoint_url, pskit client

Besides your HTTP routes, the on-prem host answers a control API under `/__pskit/*`. `pskit trigger`, `pskit logs`,
`pskit resources send`, the dashboard and studio use it; scripts can use it too.

## Protect the on-prem control API with an admin token

The on-prem admin token is a shared secret for `/__pskit/*`. Set it in `pskit.yml`, read from the environment so it
stays out of the file:

```yaml
provider:
  name: onprem
  options:
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"    # empty default = no token
```

When a token is set, every `/__pskit/*` call except `GET /__pskit/health` needs the header `x-pskit-token: <token>`.
For the AWS-compatible APIs below, pass the token as the AWS access key id. pskit's own commands read the token from
the deploy record (`.pskit/onprem-<stage>/onprem_deployed.json`) and send it for you; studio keeps it server-side.
`pskit client info` prints the endpoint, the token and code to call the host. In studio: **Overview & provider** ->
**On-premises options** -> **Admin token**.

## Call the on-prem host from outside: endpoint table

These are the on-prem host control endpoints (`<endpoint>` is the URL from `pskit info`):

| Request | Effect |
|---|---|
| `GET /__pskit/health` | status; no token needed |
| `POST /__pskit/invoke/<function>` | call a function; the body is `event.data` |
| `POST /__pskit/queues/<name>` | enqueue one JSON value, a list, or `{"messages": [...]}` -> `202 {"queued": [ids]}` |
| `GET /__pskit/queues/<name>` | `{"depth": n}` |
| `POST /__pskit/topics/<name>` | publish and deliver; `{"message", "attributes"}` sets attributes for filters |
| `GET /__pskit/storage/<bucket>[?prefix=&offset=&limit=]`, `GET .../<key>` | list objects, read one |
| `PUT` / `DELETE /__pskit/storage/<bucket>/<key>` | write or delete an object, then fire storage triggers |
| `POST /__pskit/workflows/<name>[?wait=true]` | start a workflow: `202 {"execution_id", ...}` |
| `GET /__pskit/executions`, `GET /__pskit/executions/<id>`, `POST /__pskit/executions/<id>/cancel` | list, inspect, cancel runs |
| `GET /__pskit/logs`, `GET /__pskit/logs/streams`, `DELETE /__pskit/logs[?function=]` | read, summarise, clear logs |
| `GET /__pskit/stats` | invocation counters per function and queue depths |
| `GET /__pskit/resources` | `resources:` with their backend and queue depth |
| `POST /__pskit/queues/<name>/lease`, `.../ack`, `.../nack` | consume a built-in queue from another host (the `pskit_host` driver) |
| `POST /__pskit/smtp/<resource>` | deliver a parsed mail to smtp triggers (sent by the SMTP service) |

```bash
curl -X POST http://127.0.0.1:8080/__pskit/queues/jobs \
  -H "x-pskit-token: $PSKIT_ADMIN_TOKEN" -H 'content-type: application/json' -d '{"order_id": 1}'
```

From a handler running in that host (`PSKIT_ONPREM_ROOT` is set), call `submit_queue`, `submit_topic`, `put_object` or
`delete_object` from `py_serverless_kit.runtime.onprem_host`. From other programs, use `PskitClient` (Python) or
`pskit client install-node` (Node.js); see [client.md](../../client.md).

## Use AWS SDK code against the on-prem host

The on-prem host also speaks two AWS APIs, so boto3 code only changes `endpoint_url`:

- **Lambda Invoke:** `POST /2015-03-31/functions/<name or ARN>/invocations`.
- **SQS:** `POST /` with `X-Amz-Target: AmazonSQS.*` serves SendMessage(Batch), ReceiveMessage, DeleteMessage(Batch),
  ChangeMessageVisibility, GetQueueUrl, GetQueueAttributes, ListQueues, CreateQueue and PurgeQueue over the host's
  queues. A queue resource's `resource(key).url` is `<endpoint>/000000000000/<queue name>`.

```python
import os

import boto3

sqs = boto3.client(
    "sqs",
    endpoint_url=os.environ["PSKIT_ENDPOINT"],          # set inside the host
    region_name="us-east-1",
    aws_access_key_id=os.environ.get("PSKIT_ADMIN_TOKEN") or "x",
    aws_secret_access_key="x",
)
```

More: [resource-guides/compatibility.md](../../resource-guides/compatibility.md).

## Read on-prem host logs

The on-prem host records `logging` calls (`ctx.logger` and any logger, at `log_level` and above), `print()` /
stdout (`INFO`) and stderr (`WARNING`) lines when `capture_output` is true, one `invocation` entry per handler call
(function, event type, duration; for HTTP the method, path and status; failures are `ERROR`), and host notes. The
newest `log_buffer` entries (default 5000) stay in memory; every entry is appended to `<data_dir>/logs/host.jsonl`,
which rotates at 10 MiB and keeps three old files. Messages over 16 KiB are truncated.

```bash
pskit logs                          # newest 100 entries
pskit logs -f --function worker     # follow one function
pskit logs --level error --source invocation -n 500
pskit logs -q timeout --json
pskit logs --streams                # entries per function
pskit logs --delete worker --yes    # clear one function's entries
```

In studio the **Logs** page shows the same entries with filters. The `GET /__pskit/logs` query parameters (`since`,
`before`, `limit`, `level`, `function`, `source`, `q`) and the response shape are listed in
[providers.md](../../providers.md#logs-and-stats). See also [deployment/logs.md](../../deployment/logs.md).

## Read on-prem invocation stats

`GET /__pskit/stats` returns `started_at`, `uptime_s`, per function `invocations`, `errors`, `avg_duration_ms`,
`last_duration_ms`, `last_at`, `last_error`, and queue depths. Counters reset when the host restarts.
`pskit dashboard --serve` shows health, stats, logs and workflow executions; see
[deployment/monitoring-and-dashboard.md](../../deployment/monitoring-and-dashboard.md).

## See also

- [README.md](README.md): on-prem provider options
- [deploy-methods.md](deploy-methods.md)
- [workflow-executions.md](../../workflow-executions.md)
- [client.md](../../client.md)
