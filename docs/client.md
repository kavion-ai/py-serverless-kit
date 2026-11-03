# Call an on-prem host from any program: pskit client and HTTP API

Scripts, web apps, cron jobs and other services (not only pskit functions) can add data to on-prem queues and
topics, read and consume them, and read and write buckets. They do it through the deployed **pskit host**:

- **pskit client** for Python (`py_serverless_kit.client`) and Node.js (`PskitClient` in the `pskit` package);
- or plain **HTTP** from any language.

Only the host's port (`provider.options.port`, default 8080) has to be reachable. The queue or bucket behind it may
use any driver (built-in folders, Redis, Kafka, NATS, RabbitMQ, SQS / ElasticMQ, MinIO, S3, ...) and its own port can
stay closed in the firewall. That is the usual fix for scripts that time out connecting to a service directly.

```bash
pskit client info          # this project's host: endpoint, token, reachability, code for each resource
```

In the studio, each resource's **How to use** (section 7, *Call it from code*) has complete programs for that
resource, with its key, the host URL, a reachability check and the token note filled in.

## Python

```bash
pip install py-serverless-kit            # the client itself uses only the standard library
```

```python
from py_serverless_kit.client import PskitClient

client = PskitClient("http://10.0.0.5:8080", token="...")   # or PSKIT_HOST and PSKIT_ADMIN_TOKEN
client = PskitClient.from_project(".")                      # the host this project deployed

jobs = client.queue("jobs")                    # resource key or native queue name
jobs.send({"order_id": 1}, attributes={"kind": "new"})
jobs.send_batch([{"order_id": 2}, {"order_id": 3}])
print(jobs.depth())

page = jobs.peek(offset=0, limit=20)           # look without consuming (oldest first)
print(page.total, page.has_more, [m["body"] for m in page.items])

for msg in jobs.receive(batch=10, visibility=60):   # consume: leased for 60 s
    print(msg.id, msg.json())
    msg.ack()                                  # or msg.nack() to deliver it again

files = client.bucket("uploads")
files.put("in/a.csv", b"a,b\n")
print(files.get("in/a.csv"))
print([o["key"] for o in files.list(prefix="in/", limit=50).items])
for key in files.keys(prefix="in/"):           # every key, page by page
    print(key)
files.delete("in/a.csv")

client.topic("events").publish({"id": 1}, attributes={"type": "paid"})
client.invoke("report", {"day": "2026-10-22"})          # call a function directly
client.start_workflow("order", {"id": 1}, wait=True)
client.check("orders-db")                               # reachable from the host?
client.resources()                                      # keys, types, drivers, depths
```

Errors raise `PskitClientError` (`.status` is the HTTP status, 0 when the host was not reached) within `timeout`
seconds (default 10), with what to check.

## Node.js (18+)

The `pskit` package is bundled into Node.js functions. For other programs, copy it into a project:

```bash
pskit client install-node              # -> ./node_modules/pskit (no dependencies)
pskit client install-node --dir ../my-app
```

```js
const { PskitClient } = require("pskit");

const client = new PskitClient("http://10.0.0.5:8080", { token: "..." });   // or PSKIT_HOST / PSKIT_ADMIN_TOKEN

async function main() {
  const jobs = client.queue("jobs");
  await jobs.send({ orderId: 1 }, { kind: "new" });
  const page = await jobs.peek({ offset: 0, limit: 20 });
  console.log(page.total, page.items.map((m) => m.body));
  for (const msg of await jobs.receive({ batch: 10, visibility: 60 })) {
    console.log(msg.json());
    await msg.ack();
  }

  const files = client.bucket("uploads");
  await files.put("in/a.csv", "a,b\n");
  console.log((await files.get("in/a.csv")).toString());
  for await (const key of files.keys({ prefix: "in/" })) console.log(key);

  await client.topic("events").publish({ id: 1 }, { type: "paid" });
  console.log(await client.invoke("report", { day: "2026-10-22" }));
}

main();
```

TypeScript types ship with the package (`PskitClient`, `PskitQueue`, `PskitBucket`, `PskitTopic`, `PskitPage`).

## Consuming outside pskit

`receive` leases messages of a **built-in** queue: they are hidden for `visibility` seconds, `ack` deletes them,
`nack` (or no answer in time) delivers them again. Don't receive from a queue a pskit trigger consumes; the two would
share its messages. For driver-backed queues, consume with the service's own client and its own consumer group
(*On-prem services → How to use*).

## HTTP API

Send `x-pskit-token: <admin_token>` when the host sets `provider.options.admin_token`. `<name>` is a native name,
`<key>` a resource key.

| Method and path | Body / query | Answer |
|---|---|---|
| `GET /__pskit/health` | | host status (no token needed) |
| `GET /__pskit/resources` | | `{"items": [{key, type, name, driver, depth, consumers}]}` |
| `POST /__pskit/queues/<name>` | a JSON message, `{"message", "attributes"}` or `{"messages": [...]}` | `202 {"queued": [ids]}` |
| `GET /__pskit/queues/<name>` | | `{"depth": n}` |
| `GET /__pskit/queues/<name>/peek` | `?offset=&limit=` | a page of waiting messages |
| `POST /__pskit/queues/<name>/lease` | `{"batch": 10, "visibility": 60}` | `{"messages": [{id, body, attributes, receives, receipt}]}` (built-in queues) |
| `POST /__pskit/queues/<name>/ack` / `nack` | `{"receipts": [...]}` | `{"acked": n}` / `{"released": n}` |
| `POST /__pskit/topics/<name>` | as queues | `202 {"published": [ids]}` |
| `PUT /__pskit/storage/<bucket>/<path>` | raw bytes | `201`; fires storage triggers |
| `GET /__pskit/storage/<bucket>/<path>` | | the object's bytes |
| `DELETE /__pskit/storage/<bucket>/<path>` | | `{"deleted": true}` |
| `GET /__pskit/storage/<bucket>` | `?prefix=&offset=&limit=` | a page of `{key, size, etag}` |
| `GET /__pskit/resources/<key>/data` | `?offset=&limit=&prefix=` | a page of messages or objects |
| `GET /__pskit/resources/<key>/object` | `?key=` | `{size, encoding, content, truncated}` (first 256 KiB) |
| `DELETE /__pskit/resources/<key>/object` / `message` | `?key=` / `?id=` | delete one object / built-in queue message |
| `DELETE /__pskit/resources/<key>/data` | | empty a built-in queue, bucket or topic |
| `POST /__pskit/resources/<key>/check` | | `{ok, detail, ms}` from the host |
| `POST /__pskit/invoke/<function>` | JSON → `event.data` | `{"result": ...}` |
| `POST /__pskit/workflows/<name>` | input; `?wait=true` | `202 {execution_id}` or the result |
| `GET /__pskit/executions[/<id>]`, `POST .../<id>/cancel` | | workflow executions |
| `GET /__pskit/logs`, `GET /__pskit/stats` | | captured logs, invocation counters |

```bash
curl -X POST http://10.0.0.5:8080/__pskit/queues/jobs -H 'content-type: application/json' -d '{"order_id": 1}'
curl 'http://10.0.0.5:8080/__pskit/resources/jobs/data?offset=0&limit=20'
curl -X PUT --data-binary @report.csv http://10.0.0.5:8080/__pskit/storage/uploads/in/report.csv
```

## AWS-compatible APIs

The host also serves the **Lambda Invoke API** and the **SQS API** (for its queues), so existing boto3 / AWS SDK code
works by setting `endpoint_url` to the host (use the `admin_token` as the access key id when the host has one). See
[compatibility](resource-guides/compatibility.md).

| Method and path | |
|---|---|
| `POST /2015-03-31/functions/<name, deployed name or ARN>/invocations` | `X-Amz-Invocation-Type: RequestResponse` (default), `Event` (202), `DryRun` (204) |
| `POST /` with `X-Amz-Target: AmazonSQS.<Action>` | SendMessage(Batch), ReceiveMessage, DeleteMessage(Batch), ChangeMessageVisibility, GetQueueUrl, GetQueueAttributes, ListQueues, CreateQueue, PurgeQueue |

## When connections time out

`TimeoutError` / `ConnectTimeoutError` / `ECONNREFUSED` from a script almost always mean a firewall: the program can't
open a TCP connection to that port. The service is usually fine (`pskit resources onprem status <key>`).

| Situation | Fix |
|---|---|
| Talking to a service directly (Redis, ElasticMQ, Postgres, ...) on a cloud VM | use the pskit client / HTTP above (host port only), or `pskit resources onprem tunnel <key>` (SSH; prints the variables pointing at `127.0.0.1`), or open the port **to your IP** in the security group / NSG |
| The host port itself times out | `pskit client tunnel`, then `PSKIT_HOST=http://127.0.0.1:8080`; or open the port to your IP; and set `provider.options.host: 0.0.0.0` so the host listens on the network |
| `HTTP 401` | the host has an `admin_token`: `PSKIT_ADMIN_TOKEN=...` or `token=` |

Generated direct-client examples use short connect timeouts (about 5 s), so a closed port fails quickly with this
explanation in mind instead of hanging. The studio flags it too: *On-prem services → Details* shows when this machine
cannot reach a service, and *Call from code* checks the host.
