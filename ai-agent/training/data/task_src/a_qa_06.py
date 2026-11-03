"""Category A (docs Q&A and how-to), batch 6: on-premises resources (queues, buckets, topics, databases, caches,
custom services, drivers, secrets for drivers). Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


OQ = "docs/resource-guides/onprem/queue.md"
OS = "docs/resource-guides/onprem/storage.md"
OT = "docs/resource-guides/onprem/topic.md"
OR = "docs/resource-guides/onprem/README.md"

CONVERSATIONS = [
    A(101, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{OQ}#built-in-queue"],
      user="i need a queue for background jobs on my own server. do i have to install rabbitmq or something first?",
      steps=[S("search_docs", query="on-premises queue built in no setup",
               docs=[D(OQ, "built-in-queue", end="`external: true`.")])],
      final="""No. The on-prem host has a **built-in queue**: a directory under the host's `data_dir`, created when the host starts. Nothing to install [docs/resource-guides/onprem/queue.md#built-in-queue].

**In studio**
1. Open **Resources** and click **+ Add resource**.
2. Set *Key* `jobs`, *Type* queue, and keep *Managed by pskit*. Click **Save**.
3. Open **Functions**, edit your worker, and in **Add a trigger** pick *Queue* with *Resource* `jobs`.

**In code**
```yaml
resources:
  jobs:
    type: queue
  jobs-dlq:
    type: queue

functions:
  worker:
    handler: app.handlers.work
    events:
      - queue: {resource: jobs, batch_size: 10, max_receive: 3, dead_letter: jobs-dlq}
```

**In the terminal**
```bash
pskit validate
pskit deploy
pskit resources send jobs -d '{"order_id": 1}'
```

After 3 failed deliveries a message goes to `jobs-dlq`."""),

    A(102, provider="onprem", stage="prod", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{OT}#kafka-rabbitmq-exchanges-nats-mqtt-cloud-topics", f"{OT}#on-premises-topics-type-topic"],
      user="can an onprem topic resource sit on a RabbitMQ fanout exchange?",
      steps=[S("search_docs", query="on-prem topic driver rabbitmq exchange",
               docs=[D(OT, "on-premises-topics-type-topic", end="There are no drivers for external brokers."),
                     D(OT, "kafka-rabbitmq-exchanges-nats-mqtt-cloud-topics")])],
      final="""No. On premises a topic is built in (directories under `data_dir`) or a shared directory. There are no topic drivers for external brokers [docs/resource-guides/onprem/topic.md#on-premises-topics-type-topic].

Alternatives [docs/resource-guides/onprem/topic.md#kafka-rabbitmq-exchanges-nats-mqtt-cloud-topics]:
1. Bind one RabbitMQ queue per consuming function to the exchange, and consume each one as a `queue` resource with a custom queue driver (`driver: custom`, `class: app.rabbitmq_queue:RabbitQueue`).
2. Publish to the exchange from a handler with `pika`, and describe the broker as a `custom` resource.
3. Keep the fan-out inside pskit with a built-in `type: topic`.

A `driver` other than `builtin` or `directory` on a topic fails with `on-premises topic driver must be one of builtin, directory`."""),

    A(103, provider="onprem", stage="staging", mode="auto", page="YAML", persona="terse_expert",
      sources=[f"{OQ}#3-declare-it-in-pskityml", f"{OR}#secrets-name_env"],
      user="redis queue driver: url vs url_env, which one keeps the password out of the generated files?",
      steps=[S("search_docs", query="redis driver url_env password generated files",
               docs=[D(OQ, "3-declare-it-in-pskityml", end="`LPUSH jobs '<text>'`"),
                     D(OR, "secrets-name_env", end="A missing variable stops the host with an error naming it.")])],
      final="""`url_env`. With `url: redis://...` the value is written into the generated files. With `url_env: REDIS_URL` the host reads the variable from its own environment at start, so it never lands in Terraform state or `pskit_host.json` [docs/resource-guides/onprem/README.md#secrets-name_env].

**In code**
```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis
      url_env: REDIS_URL
      key: jobs
```
Every driver parameter works this way (`<name>_env: VARIABLE`). If the variable is missing on the host, the host stops with an error that names it [docs/resource-guides/onprem/queue.md#3-declare-it-in-pskityml]."""),

    A(104, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{OQ}#a-queue-on-another-on-prem-host-pskit_host"],
      user="We have two pskit deployments on different servers. Project B already has a built-in `orders` queue. We want a worker in project A to consume that same queue, without installing Redis or any broker. Is that supported, and what does B need?",
      steps=[S("search_docs", query="consume built-in queue of another on-prem host",
               docs=[D(OQ, "a-queue-on-another-on-prem-host-pskit_host", words=320)])],
      final="""Yes, with the `pskit_host` driver. Host A leases messages from B's built-in queue through B's admin API, so no broker is needed [docs/resource-guides/onprem/queue.md#a-queue-on-another-on-prem-host-pskit_host].

**In code** (project A)
```yaml
resources:
  orders:
    type: queue
    external: true
    options:
      driver: pskit_host
      endpoint: http://192.0.2.20:8080
      queue: orders
      token_env: HOST_B_TOKEN
functions:
  worker:
    handler: app.handlers.work
    events: [{queue: {resource: orders, max_receive: 3, dead_letter: orders-dlq}}]
```

What B needs:
- the queue itself (a managed `type: queue` resource, or any queue its functions publish to);
- `options.host: 0.0.0.0`, so A can reach it;
- if B sets `admin_token`, put that token in `HOST_B_TOKEN` where A runs.

B hides a leased message for `visibility_timeout` seconds, so if A crashes the message is delivered again. `pskit_host` only reaches B's **built-in** queues, not queues that use a driver on B."""),

    A(105, provider="onprem", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{OQ}#troubleshooting"],
      user="host note: pskit_host: POST http://192.0.2.20:8080/__pskit/queues/orders/lease request failed (401)\n\nworker gets nothing",
      steps=[S("search_docs", query="pskit_host request failed 401",
               docs=[D(OQ, "troubleshooting")])],
      final="""Host B has an `admin_token`, and host A doesn't send it. Set `token_env` to the variable that holds B's `admin_token` [docs/resource-guides/onprem/queue.md#troubleshooting].

**In code** (project A)
```yaml
resources:
  orders:
    type: queue
    external: true
    options:
      driver: pskit_host
      endpoint: http://192.0.2.20:8080
      queue: orders
      token_env: HOST_B_TOKEN
```

Then put the token where A's host runs, for example in the env file (`provider.options.env_file: .env.onprem`, line `HOST_B_TOKEN=<token>`), and deploy again:
```bash
pskit deploy -s prod
pskit logs -f --function worker
```"""),

    A(106, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=[f"{OS}#on-premises-storage-type-storage", f"{OS}#troubleshooting"],
      user="i deployed my storage function but the 200 csv files already in the bucket never ran. is it broken?",
      steps=[S("search_docs", query="on-prem storage existing files not triggered",
               docs=[D(OS, "on-premises-storage-type-storage"),
                     D(OS, "troubleshooting")])],
      final="""It isn't broken. The host lists each watched bucket every `poll_seconds` and compares ETags. Objects already there at the first start are recorded, not emitted [docs/resource-guides/onprem/storage.md#on-premises-storage-type-storage]. Only new or changed objects (`created`) and missing ones (`deleted`) trigger the function.

To check that it works, upload a new file [docs/resource-guides/onprem/storage.md#troubleshooting]:

**In the terminal**
```bash
pskit resources send uploads -d '{"key": "incoming/a.csv", "content": "a,b"}'
pskit logs -f --function ingest
```

**In studio**
1. Open **Resources** and click **Test** on the bucket's row.
2. Send a test object, then watch the function in **Logs**.

To process the old files, copy them in again under a new key, or handle them once from a small script."""),

    A(107, provider="onprem", stage="prod", mode="auto", page="Resources", persona="informal_non_native",
      sources=[f"{OS}#built-in-bucket"],
      user="our scanner put pdf in /mnt/scans on the server. function must run for every new pdf. how?",
      steps=[S("search_docs", query="storage trigger existing folder directory driver",
               docs=[D(OS, "built-in-bucket")])],
      final="""Point a storage resource at that folder with the `directory` driver, and add a storage trigger with a `.pdf` suffix [docs/resource-guides/onprem/storage.md#built-in-bucket].

**In code**
```yaml
resources:
  inbox:
    type: storage
    external: true
    options: {driver: directory, path: /mnt/scans}

functions:
  scan:
    handler: app.handlers.scan
    events:
      - storage: {resource: inbox, suffix: .pdf, events: [created]}
```
```python
from __future__ import annotations


def scan(event, ctx):
    for record in event.records:
        ctx.logger.info("new scan", extra={"key": record.key, "size": record.size})
```

**In studio**
1. Open **Resources** > **+ Add resource**: *Key* `inbox`, *Type* storage, *External / existing*, *On-prem driver* directory, path `/mnt/scans`.
2. Open **Functions**, add a *Storage* trigger on `inbox`, *Fire on* created, suffix `.pdf`.
3. **Save**, then deploy.

With `external: true` the host doesn't create the folder. PDFs already in the folder at the first start are not emitted."""),

    A(108, provider="onprem", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=[f"{OS}#test"],
      user="cli only: drop a test object into the uploads bucket on the deployed host",
      steps=[S("search_docs", query="send test object on-prem bucket command",
               docs=[D(OS, "test")])],
      final="""**In the terminal**
1. Through pskit:
```bash
pskit resources send uploads -d '{"key": "incoming/a.csv", "content": "a,b"}'
```
2. Or straight to the host's admin API:
```bash
curl -X PUT --data 'a,b' http://127.0.0.1:8080/__pskit/storage/uploads/incoming/b.csv
```
3. Watch the function:
```bash
pskit logs -f --function ingest
```
[docs/resource-guides/onprem/storage.md#test]"""),

    A(109, provider="onprem", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{OT}#built-in-topic", f"{OT}#troubleshooting"],
      user="pskit resources send order-events -d '{\"message\": {\"id\": 3}, \"attributes\": {\"type\": \"Paid\"}}'\naudit got it, billing did not. billing has filter type: [paid]",
      steps=[S("search_docs", query="topic filter function does not receive message",
               docs=[D(OT, "troubleshooting"),
                     D(OT, "built-in-topic", start="  order-events:", end="exact match on attributes, then JSON body fields")])],
      final="""The filter is an **exact match**. Your attribute is `Paid`, and billing's filter allows only `paid`, so billing is skipped. `audit` has no filter, so it gets every message [docs/resource-guides/onprem/topic.md#troubleshooting].

Send the value the filter expects:
```bash
pskit resources send order-events -d '{"message": {"id": 3}, "attributes": {"type": "paid"}}'
```

Or allow both spellings in the filter:
```yaml
functions:
  billing:
    handler: app.handlers.billing
    events:
      - topic: {resource: order-events, filter: {type: [paid, Paid]}}
```
The filter checks the message attributes first, then the JSON body fields [docs/resource-guides/onprem/topic.md#built-in-topic]."""),

    A(110, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{OS}#a-bucket-in-a-cloud"],
      user="Files land in an Azure Blob container from a partner. Our processing functions run on our own servers. Can the on-prem host watch that container and trigger a function per new blob? Which values do I need?",
      steps=[S("search_docs", query="on-prem storage driver azure blob container",
               docs=[D(OS, "a-bucket-in-a-cloud", end="| Google Cloud Storage |")])],
      final="""Yes. Declare the container as an external storage resource with the `azure_blob` driver. The host polls it and each new blob triggers your function like a local event [docs/resource-guides/onprem/storage.md#a-bucket-in-a-cloud].

You need `connection_string_env` (or `account` plus a key or SAS) and the `container`.

**In code**
```yaml
resources:
  partner-files:
    type: storage
    external: true
    options:
      driver: azure_blob
      connection_string_env: AZURE_STORAGE_CONNECTION_STRING
      container: partner-drop
functions:
  process:
    handler: app.handlers.process
    events:
      - storage: {resource: partner-files, events: [created]}
```
Put `AZURE_STORAGE_CONNECTION_STRING` in the host's env file (`provider.options.env_file`), not in pskit.yml.

**In studio**
1. Open **Resources** > **+ Add resource**, *Type* storage, *External / existing*.
2. Under *On-prem driver*, pick Azure Blob and fill in its fields. Secret fields can read an environment variable.
3. Add a *Storage* trigger on it in **Functions**, then **Save**.

Blobs already in the container at the first start are recorded, not emitted."""),

    A(111, provider="onprem", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{OR}#secrets-name_env"],
      user="How does provider.options.env_file actually work? Is the file committed, does the value end up in Terraform state, and which wins if the same variable is also set on the server?",
      steps=[S("search_docs", query="env_file host.env secrets on-prem",
               docs=[D(OR, "secrets-name_env", start="The simplest place for those variables", words=300)])],
      final="""[docs/resource-guides/onprem/README.md#secrets-name_env]
- `env_file` holds `KEY=VALUE` lines, relative to pskit.yml. Keep it out of git.
- `pskit deploy` copies it next to the host as `host.env` (locally, over SSH, or into the Docker image), and the host loads it at start, for every deploy method.
- Only its **digest** goes into `pskit_host.json`. Changing a secret redeploys the host, and the value isn't written anywhere else.
- Variables already set in the host's environment **win** over the file.
- One-click services write their credentials there.

**In code**
```yaml
provider:
  name: onprem
  options:
    env_file: .env.onprem
```

**In studio**
1. Open **Overview & provider**. The on-prem options include the env file.
2. Click **Save**. One-click services in **Resources > On-prem services** add `env_file` for you.

Note the difference: `${env:...}` is resolved on the machine that runs `pskit deploy` and is written into the generated files. `env_file` and `<name>_env` are not."""),

    A(112, provider="onprem", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=[f"{OR}#publishing-from-a-handler"],
      user="handler code only: put a message on queue jobs and write a file to bucket uploads from an http function, onprem",
      steps=[S("search_docs", query="publish queue put object from handler on-prem",
               docs=[D(OR, "publishing-from-a-handler", start="Handlers in the host process", end="delete_object(resource(\"uploads\").native_name")])],
      final="""**In code**
```python
from __future__ import annotations

from py_serverless_kit import resource
from py_serverless_kit.runtime.onprem_host import put_object, submit_queue


def api(event, ctx):
    body = event.http.json()
    msg_id = submit_queue(resource("jobs").native_name, body, {"kind": "new"})
    put_object(resource("uploads").native_name, "in/order.json", event.http.body or b"")
    return {"queued": msg_id}
```
- `submit_queue` returns the message id.
- Names are the resource's native name (`name`, else the key), so use `resource(...).native_name`.
- These calls go through the host and honour drivers, so the same code works for a built-in queue, Redis or SQS [docs/resource-guides/onprem/README.md#publishing-from-a-handler]."""),

    A(113, provider="onprem", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{OR}#publishing-from-a-handler"],
      user="my handler is node js not python. how i send to queue on onprem host from node?",
      steps=[S("search_docs", query="node.js submitQueue on-prem host",
               docs=[D(OR, "publishing-from-a-handler", start="Node.js handlers have the same calls", end="Names are the resource's")])],
      final="""Node.js has the same calls, from the `pskit` module. They go through the host's loopback address (`PSKIT_HOST_URL`) [docs/resource-guides/onprem/README.md#publishing-from-a-handler].

**In code**
```js
const { resource, submitQueue, putObject } = require("pskit");

exports.api = async (event, ctx) => {
  const id = await submitQueue(resource("jobs").nativeName, { orderId: 1 }, { kind: "new" });
  await putObject(resource("uploads").nativeName, "in/a.csv", "a,b\\n");
  return { id };
};
```
`submitTopic` and `deleteObject` work the same way. In Node.js the name is `nativeName`."""),

    A(114, provider="onprem", stage="prod", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resource-guides/onprem/cache.md#3-declare-it-in-pskityml",
               "docs/resource-guides/onprem/cache.md#4-use-it-in-a-handler"],
      user="we have a redis on cache.example.com. how do i use it as a cache from my functions?",
      steps=[S("search_docs", query="on-prem redis cache resource",
               docs=[D("docs/resource-guides/onprem/cache.md", "3-declare-it-in-pskityml"),
                     D("docs/resource-guides/onprem/cache.md", "4-use-it-in-a-handler")])],
      final="""Declare it as an external `cache` resource, and connect with the `redis` library.

**In code**
1. pskit.yml [docs/resource-guides/onprem/cache.md#3-declare-it-in-pskityml]:
```yaml
resources:
  cache:
    type: cache
    external: true
    connection:
      host: cache.example.com
      port: 6379
      db: 1
      ssl: false
      password_env: CACHE_PASSWORD
```
2. Add `redis` to `requirements.txt`.
3. Handler [docs/resource-guides/onprem/cache.md#4-use-it-in-a-handler]:
```python
from __future__ import annotations

import redis
from py_serverless_kit import resource

_client = None


def api(event, ctx):
    global _client
    if _client is None:
        c = resource("cache")
        pw = ctx.env[c["password_env"]]
        _client = redis.Redis(host=c["host"], port=int(c["port"]), db=int(c["db"]),
                              ssl=c.get("ssl") == "true", password=pw)
    return {"hits": _client.incr("hits")}
```
Connection values arrive as strings, so `ssl` is `"true"`/`"false"` and the port needs `int(...)`.

**In studio**
1. **Resources** > **+ Add resource**, *Type* cache, *External / existing*.
2. Add the host, port and db with **Add connection value**, and the password's variable name as `password_env`.
3. Put `CACHE_PASSWORD` where the host runs (for example the env file)."""),

    A(115, provider="onprem", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/resource-guides/onprem/database.md#troubleshooting", "docs/resource-guides/onprem/database.md#5-test"],
      user="KeyError: 'ORDERS_DB_PASSWORD'\n\nfrom ctx.env[db['password_env']] in my api handler",
      steps=[S("search_docs", query="KeyError password_env database on-prem",
               docs=[D("docs/resource-guides/onprem/database.md", "troubleshooting"),
                     D("docs/resource-guides/onprem/database.md", "5-test")])],
      final="""The resource says `password_env: ORDERS_DB_PASSWORD`, but that variable isn't set where the handler runs [docs/resource-guides/onprem/database.md#troubleshooting].

- **Local test**: set it for the command:
```bash
ORDERS_DB_PASSWORD=... pskit invoke -f api
```
- **Deployed host**: put `ORDERS_DB_PASSWORD=<password>` in the env file named by `provider.options.env_file` (for example `.env.onprem`), then deploy again. With `install: systemd` you can also set it in the unit's environment.

Keep only the variable's **name** in `connection`, never the password [docs/resource-guides/onprem/database.md#5-test]."""),

    A(116, provider="onprem", stage="staging", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{OR}#how-the-host-uses-resources"],
      user="can I put options.driver: redis on a type: cache resource so the host watches it?",
      steps=[S("search_docs", query="driver on database cache custom resources",
               docs=[D(OR, "how-the-host-uses-resources", words=330)])],
      final="""No. `database`, `cache` and `custom` resources have no driver, and `options.driver` on them is a validation error. pskit only hands their `connection` values to handlers [docs/resource-guides/onprem/README.md#how-the-host-uses-resources].

If you want Redis to **trigger** functions, declare it as a queue instead:
```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis
      url_env: REDIS_URL
      key: jobs
```
One Redis server can be the cache and the queue at once. Give them separate keys or databases (`/0`, `/1`)."""),

    A(117, provider="onprem", stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resource-guides/onprem/custom.md#example-smtp-server"],
      user="function must send mail with our company smtp (port 587). where i put host and password in pskit?",
      steps=[S("search_docs", query="send email smtp server custom resource",
               docs=[D("docs/resource-guides/onprem/custom.md", "example-smtp-server", end="functions: [notify]")])],
      final="""Describe the mail server as a `custom` resource. Put the host, port and user in `connection`, and only the **name** of the password variable [docs/resource-guides/onprem/custom.md#example-smtp-server].

**In code**
```yaml
resources:
  mail:
    type: custom
    external: true
    connection:
      host: smtp.example.com
      port: 587
      user: noreply@example.com
      from_address: noreply@example.com
      password_env: SMTP_PASSWORD
    functions: [notify]
```
```python
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from py_serverless_kit import resource


def notify(event, ctx):
    mail = resource("mail")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = mail["from_address"], "ops@example.com", "Order paid"
    msg.set_content(str(event.json()))
    with smtplib.SMTP(mail["host"], int(mail["port"])) as smtp:
        smtp.starttls()
        smtp.login(mail["user"], ctx.env[mail["password_env"]])
        smtp.send_message(msg)
```

**In studio**
1. **Resources** > **+ Add resource**, *Type* custom, *External / existing*.
2. Add the values with **Add connection value** and tick `notify` under *Bound functions*.

Set `SMTP_PASSWORD` where the host runs, for example in the env file."""),

    A(118, provider="onprem", stage="prod", mode="auto", page="Resources", persona="terse_expert",
      sources=[f"{OQ}#redis-valkey-stream-redis_stream"],
      user="3 onprem hosts should share one redis work queue, each message processed once. list or stream?",
      steps=[S("search_docs", query="redis stream consumer group several hosts",
               docs=[D(OQ, "redis-valkey-stream-redis_stream")])],
      final="""Use the stream driver, `redis_stream`. Hosts in one consumer group share the work, and the stream gives native leases and delivery counts. It needs Redis 6.2+ or Valkey [docs/resource-guides/onprem/queue.md#redis-valkey-stream-redis_stream].

**In code** (same in all three projects)
```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis_stream
      url_env: REDIS_URL
      key: jobs
      group: pskit
      maxlen: 100000
```
- An entry is acknowledged and deleted once the handler succeeded.
- A failed entry can be claimed again at once. After `max_receive` deliveries it goes to `dead_letter`.
- An entry left by a crashed host is taken over (`XAUTOCLAIM`) once it has been idle for `visibility_timeout`."""),

    A(119, provider="onprem", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{OQ}#troubleshooting", f"{OQ}#kafka-and-nats-jetstream"],
      user="kafka queue made with one-click 2 months ago. producer writes, `pskit logs --function worker` shows nothing at all, no errors",
      steps=[S("search_docs", query="kafka consumer never receives on-prem",
               docs=[D(OQ, "troubleshooting", start="| Kafka consumer never receives anything |"),
                     D(OQ, "kafka-and-nats-jetstream", end="Kafka reports no queue depth;")])],
      final="""Update the driver file. Older copies of `pskit_drivers/kafka_queue.py` polled with a zero timeout and never joined the consumer group [docs/resource-guides/onprem/queue.md#troubleshooting].

1. Replace `pskit_drivers/kafka_queue.py` with the current template, `examples/19-custom-drivers/app/kafka_queue.py` [docs/resource-guides/onprem/queue.md#kafka-and-nats-jetstream].
2. Keep `kafka-python` in `requirements.txt`.
3. Deploy again and watch:
```bash
pskit deploy
pskit logs -f --function worker
pskit logs --source host
```
Host notes (`--source host`) show endpoint problems. Kafka reports no queue depth, so an empty depth isn't a sign of trouble."""),

    A(120, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/studio.md#project-environment-trigger-resources-and-remove", "docs/cli.md#pskit-resources"],
      user="where in the studio can i see the messages sitting in my onprem queue, without my worker eating them?",
      steps=[S("search_docs", query="studio see messages in on-prem queue data",
               docs=[D("docs/studio.md", "project-environment-trigger-resources-and-remove",
                       start="- **On-prem services**: the create form has a *Security* box", end="pages through what an on-prem queue")]),
             S("search_docs", query="resources data page through queue not consumed",
               docs=[D("docs/cli.md", "pskit-resources", start="| `data KEY", end="| `data KEY")])],
      final="""**In studio**
1. Open **Resources**.
2. Open **Data** on the queue. It pages through what an on-prem queue, topic or bucket holds, with previews [docs/studio.md#project-environment-trigger-resources-and-remove].

Reading there doesn't consume the messages, so your worker still gets them [docs/cli.md#pskit-resources]."""),
]
