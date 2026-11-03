"""Category A (docs Q&A and how-to), batch 15: on-premises drivers in depth (matrix, queue and storage drivers,
custom classes, validation) and saved servers (servers list, test, deploy to a chosen machine).
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


RS = "docs/resources.md"
SV = "docs/resource-guides/onprem/services.md"

CONVERSATIONS = [
    A(281, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{RS}#storage-drivers"],
      user="One MinIO, many buckets: uploads, invoices, returns. Do I need three storage resources with the same keys repeated, or can one resource serve all three triggers?",
      steps=[S("search_docs", query="one storage service many buckets on premises",
               docs=[D(RS, "storage-drivers", start="**One storage service, many buckets (on premises).**", end="then type the bucket.")])],
      final="""One resource is enough. On premises a storage event can name a storage resource **and** a bucket: the resource is the service (driver, endpoint, keys) and `bucket` is any bucket on it. Without `bucket`, the event watches the resource's own bucket [docs/resources.md#storage-drivers].

**In code**
```yaml
resources:
  minio:
    type: storage
    external: true
    options: {driver: minio, endpoint: http://minio.example.com:9000, bucket: uploads,
              access_key_env: MINIO_ACCESS_KEY, secret_key_env: MINIO_SECRET_KEY}
functions:
  ingest:   {handler: app.handlers.ingest,   events: [{storage: {resource: minio}}]}
  invoices: {handler: app.handlers.invoices, events: [{storage: {resource: minio, bucket: invoices}}]}
  returns:  {handler: app.handlers.returns,  events: [{storage: {resource: minio, bucket: returns}}]}
```

**In studio**
In **Functions**, add a *Storage* trigger, choose *Project resource*, pick `minio`, then type the bucket.

This works with a driver or a `builtin` resource, not with a `directory` resource (a single folder). Cloud providers reject `resource` plus a different `bucket`."""),

    A(282, provider="onprem", stage="dev", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{RS}#storage-drivers"],
      user="minio on-prem driver polling a bucket with 2M objects is slow. tips?",
      steps=[S("search_docs", query="storage driver large bucket poll prefix",
               docs=[D(RS, "storage-drivers", start="Every storage driver lists the bucket")])],
      final="""Every storage driver lists the whole bucket (all pages) on each poll and diffs the ETags. On a large bucket, always set `prefix`: the host then lists only keys below it [docs/resources.md#storage-drivers].

```yaml
functions:
  ingest:
    handler: app.handlers.ingest
    events:
      - storage: {resource: files, prefix: incoming/}
provider:
  name: onprem
  options:
    poll_seconds: 5
```
Raising `poll_seconds` makes the lists less frequent. `prefix` is stripped from `record.key`."""),

    A(283, provider="onprem", stage="prod", mode="ask", page="Resources", persona="aws_migrator",
      sources=[f"{RS}#queue-drivers"],
      user="Our on-prem worker consumes a real SQS queue. The host has no AWS keys in its environment yet. Which parameters does the sqs driver need, and can it long-poll?",
      steps=[S("search_docs", query="sqs driver parameters wait_seconds credentials",
               docs=[D(RS, "queue-drivers", start="| `sqs` |", end="| `sqs` |")])],
      final="""The `sqs` driver needs `queue_url` (or `account_id` + `region`). For credentials, set `access_key` + `secret_key` (via `_env`), or put `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in the host's environment. `wait_seconds` (0-20, default 0) turns on long polling [docs/resources.md#queue-drivers].

**In code**
```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/jobs
      access_key_env: AWS_ACCESS_KEY_ID
      secret_key_env: AWS_SECRET_ACCESS_KEY
      wait_seconds: 20
functions:
  worker:
    handler: app.handlers.worker
    events:
      - queue: {resource: jobs, visibility_timeout: 120, max_receive: 5}
```
Put the two keys in the env file (`provider.options.env_file`). The host sets the message visibility to the event's `visibility_timeout`."""),

    A(284, provider="onprem", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{RS}#queue-drivers"],
      user="With the plain redis list driver, what happens to a message if the host crashes while the handler is running? Is it lost?",
      steps=[S("search_docs", query="redis driver layout claim processing crash",
               docs=[D(RS, "queue-drivers", start="**Redis layout.**")])],
      final="""It isn't lost. Claiming moves the message with `RPOPLPUSH` to `<key>:processing` and records the claim time in the hash `<key>:claims`. Every few seconds the host requeues claims older than `visibility_timeout`, plus any message in `processing` that has no claim [docs/resources.md#queue-drivers].

So after a crash the message goes back to `<key>` and is delivered again. Failed messages go back until `max_receive`, then to `dead_letter`. This is at-least-once, so keep the handler idempotent."""),

    A(285, provider="onprem", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=[f"{RS}#custom-drivers"],
      user="We want an on-prem queue backed by IBM MQ. pskit has no driver for it. What does our own class have to implement?",
      steps=[S("search_docs", query="custom queue driver class interface methods",
               docs=[D(RS, "custom-drivers", start="A queue class needs", end="stop the host with a message naming the class.")]),
             S("search_docs", query="custom driver yaml class",
               docs=[D(RS, "custom-drivers", start="resources:", end="      queue: orders")])],
      final="""A queue class needs [docs/resources.md#custom-drivers]:
- `submit(body, attributes) -> id`
- `claim(batch, visibility, now) -> [message]`
- `settle(claimed, failed_ids, max_receive, dead_letter, now)`
- optional: `depth()` and `recover(now, visibility)`; add `peek(offset, limit) -> (items, total)` to make it browsable

A message is a dict with `id`, `body`, `attributes`, `receives`, `enqueued_at`, plus any private `_` keys you need in `settle`.

**In code**
```yaml
resources:
  orders:
    type: queue
    external: true
    options:
      driver: custom
      class: app.ibmmq_queue:IbmMqQueue
      url_env: IBMMQ_URL
      queue: orders
```
Every other parameter goes to the constructor as a keyword argument. Put the client library in `requirements.txt`. Import errors, constructor errors and missing methods stop the host with a message that names the class. `examples/19-custom-drivers` has working templates."""),

    A(286, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=[f"{RS}#troubleshooting"],
      user="custom driver (queue jobs): cannot import 'app.backends'",
      steps=[S("search_docs", query="custom driver cannot import module",
               docs=[D(RS, "troubleshooting", start="| `custom driver (queue jobs): cannot import 'app.backends'`", end="| `custom driver ...: X does not implement claim, settle`")])],
      final="""The module isn't in the deployed bundle, or its library isn't installed [docs/resources.md#troubleshooting].

Check:
1. `app/backends.py` is under `package.source`, so it's packaged.
2. The class's client library (for example `pika`) is in `requirements.txt`.
3. `class` is `package.module:ClassName`, e.g. `app.backends:RabbitQueue`.

Then:
```bash
pskit validate
pskit deploy
```"""),

    A(287, provider="onprem", stage="dev", mode="auto", page="Resources", persona="terse_expert",
      sources=[f"{RS}#on-premises-drivers"],
      user="sqs driver against localstack instead of aws. param?",
      steps=[S("search_docs", query="driver endpoint emulator localstack",
               docs=[D(RS, "on-premises-drivers", start="**Emulators and private endpoints.**", end="a VPC endpoint).")])],
      final="""`endpoint`. Every HTTP driver accepts `endpoint: http(s)://...` for LocalStack, Azurite, the Pub/Sub emulator, fake-gcs-server or a VPC endpoint [docs/resources.md#on-premises-drivers].

```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: sqs
      endpoint: http://localhost:4566
      queue_url: http://localhost:4566/000000000000/jobs
```
Against a non-AWS endpoint, `create_queue` defaults to true, so the queue is created on first use."""),

    A(288, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{RS}#provider-matrix"],
      user="my company use digitalocean. which queue can my onprem functions read there?",
      steps=[S("search_docs", query="driver provider matrix digitalocean queue",
               docs=[D(RS, "provider-matrix")])],
      final="""DigitalOcean has no queue service, so there's no DigitalOcean queue driver. Use `redis` (DigitalOcean Managed Redis / Valkey) or a `custom` class. For files, the `spaces` storage driver reads DigitalOcean Spaces [docs/resources.md#provider-matrix].

**In code**
```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis
      url_env: DO_REDIS_URL
      key: jobs
```
Managed Redis uses TLS, so the URL starts with `rediss://`."""),

    A(289, provider="onprem", stage="dev", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{RS}#custom-drivers"],
      user="does pskit validate catch a wrong driver name or a missing secret_key?",
      steps=[S("search_docs", query="validate rejects driver parameters",
               docs=[D(RS, "custom-drivers", start="`pskit validate` rejects a driver", end="and a malformed `class`.")])],
      final="""Yes. `pskit validate` rejects a driver that isn't allowed for the type, missing required parameters, one of a key pair without the other, a non-http(s) `endpoint`, and a malformed `class` [docs/resources.md#custom-drivers].

It can't check that a `*_env` variable is set on the host. A missing one stops the host at start with an error naming it.
```bash
pskit validate
```"""),

    A(290, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{RS}#secrets"],
      user="Who can see our database connection values on-prem? Do they end up in files on disk?",
      steps=[S("search_docs", query="connection values stored state pskit_host.json",
               docs=[D(RS, "secrets")])],
      final="""Yes. Connection values become environment variables and are stored in Terraform state and, on premises, in `.pskit/onprem-<stage>/onprem_app/pskit_host.json`. Treat both as sensitive [docs/resources.md#secrets].

Keep secrets out of them:
- put the **name** of a variable in `connection` (`password_env: ORDERS_DB_PASSWORD`) and read it at run time with `ctx.env[db["password_env"]]`;
- put the value in the host's env file (`provider.options.env_file`), which is only recorded by its digest.

`${env:...}` is resolved on the machine running `pskit deploy`, so its value **is** written into state. `pskit info --json` and the dashboard show connection key names only."""),

    A(291, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=[f"{RS}#troubleshooting"],
      user="function 'ingest' has a queue event on resource 'uploads', which is a storage",
      steps=[S("search_docs", query="queue event on resource which is a storage",
               docs=[D(RS, "troubleshooting", start="| `function 'x' has a queue event", end="| `function 'x' has a queue event")])],
      final="""The event kind must match the resource's `type` [docs/resources.md#troubleshooting]. `uploads` is a storage resource, so use a storage event:

```yaml
functions:
  ingest:
    handler: app.handlers.ingest
    events:
      - storage: {resource: uploads}
```
If you really want a queue, add a separate `type: queue` resource and point the queue event at it."""),

    A(292, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{SV}#servers-several-machines"],
      user="before i use server app-2 i want check it have docker and sudo. how?",
      steps=[S("search_docs", query="test saved server docker sudo",
               docs=[D(SV, "servers-several-machines", end="pskit resources onprem servers remove lab")])],
      final="""Test the saved server. It reports OS, CPU, memory, disk, Docker access, sudo, and Python / Node / nginx [docs/resource-guides/onprem/services.md#servers-several-machines].

**In the terminal**
```bash
pskit resources onprem servers test app-2
```
Only checking that SSH answers (no login):
```bash
pskit resources onprem servers check
```

**In studio**
1. Open **Resources > On-prem services > Servers**.
2. Click *Test* on app-2."""),

    A(293, provider="onprem", stage="prod", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{SV}#servers-several-machines"],
      user="live cpu/mem/disk of app-1 every 5s from terminal?",
      steps=[S("search_docs", query="server top watch live cpu memory",
               docs=[D(SV, "servers-several-machines", start="pskit resources onprem servers list", end="pskit resources onprem servers top edge1 --watch 5")])],
      final="""```bash
pskit resources onprem servers top app-1 --watch 5
```
[docs/resource-guides/onprem/services.md#servers-several-machines]. In the studio, **Live** on a server in **Resources > On-prem services > Servers** shows the same until you switch it off."""),

    A(294, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{SV}#deploy-the-functions-to-a-chosen-machine"],
      user="We have two edge servers, edge-a and edge-b, and want the same service on both, each its own deployment. How do I set it up without them overwriting each other?",
      steps=[S("search_docs", query="deploy to chosen machine one stage per machine",
               docs=[D(SV, "deploy-the-functions-to-a-chosen-machine")])],
      final="""Use one stage per machine. Each stage has its own Terraform state, so the two never overwrite each other [docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine].

**In code**
```yaml
provider:
  name: onprem
  options:
    deploy: {server: edge-a, path: /opt/shop}
stages:
  edge-b:
    provider: {options: {deploy: {server: edge-b, path: /opt/shop}}}
```
The saved server's host, user, port and login replace those in `options.deploy`; `method`, `path` and the rest stay.

**In the terminal**
```bash
pskit deploy -s staging
pskit deploy -s edge-b
pskit logs -s edge-b
```

**In studio**
Open **Deploy**, set the stage in the top bar, and pick the *Machine* before **Deploy**."""),

    A(295, provider="onprem", stage="prod", mode="auto", page="Logs", persona="terse_expert",
      sources=[f"{SV}#deploy-the-functions-to-a-chosen-machine"],
      user="logs and trigger against edge-b instead of the last deployed host?",
      steps=[S("search_docs", query="logs trigger server flag other host",
               docs=[D(SV, "deploy-the-functions-to-a-chosen-machine", start="Logs, triggers and executions follow the same choice", end="never overwrite each other's deployment.")])],
      final="""Add `--server` [docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine]:
```bash
pskit logs --server edge-b
pskit trigger --server edge-b -f api
pskit resources send --server edge-b jobs
```
In the studio: **Logs > Server**. Without it, they read the host of the last deploy. The host's port must be reachable from your machine (or pskit falls back to SSH)."""),

    A(296, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{SV}#servers-several-machines"],
      user="if i remove a saved server, do the redis and postgres i created on it stop?",
      steps=[S("search_docs", query="remove saved server services keep running",
               docs=[D(SV, "servers-several-machines", start="pskit resources onprem servers remove lab", end="so editing the server later does not move them.")])],
      final="""No. Services there keep running. Services created on a server keep a copy of its connection, so editing or removing the saved server doesn't move or stop them [docs/resource-guides/onprem/services.md#servers-several-machines].

```bash
pskit resources onprem servers usage db-1
pskit resources onprem servers remove db-1
```
Check `usage` first: it lists everything that still names the server."""),

    A(297, provider="onprem", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SV}#ssh-login-key-agent-or-password"],
      user="Our lab server only allows password SSH logins and I'm on Linux. How do I save it in pskit without writing the password anywhere in the project?",
      steps=[S("search_docs", query="ssh password login sshpass linux",
               docs=[D(SV, "ssh-login-key-agent-or-password", end="Password logins go through **sshpass**", words=200)]),
             S("search_docs", query="servers add password env",
               docs=[D(SV, "servers-several-machines", start="pskit resources onprem servers add lab", end="pskit resources onprem servers add lab")])],
      final="""Install `sshpass` and pass the password through an environment variable [docs/resource-guides/onprem/services.md#ssh-login-key-agent-or-password].

**In the terminal**
```bash
export LAB_PW='<password>'
pskit resources onprem servers add lab --ssh root@192.0.2.60 --ssh-password-env LAB_PW --sudo
pskit resources onprem servers test lab
```
A typed password goes to `.pskit/ssh/` (owner-only), never to pskit.yml or a command line [docs/resource-guides/onprem/services.md#ssh-login-key-agent-or-password]. The server must allow `PasswordAuthentication`.

Long term, a key is simpler: `pskit resources onprem ssh-key root@192.0.2.60` installs one with the password once."""),

    A(298, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{SV}#web-uis"],
      user="redis commander gui password where i find? i didnt set any",
      steps=[S("search_docs", query="redis commander login generated password",
               docs=[D(SV, "web-uis", start="| Service | Companion | Default port | Login |", end="| MongoDB | Mongo Express |")])],
      final="""Redis Commander logs in as `admin` with a generated password, stored as `PSKIT_<KEY>_GUI_PASSWORD` in the env file [docs/resource-guides/onprem/services.md#web-uis].

**In studio**
Open **Resources > On-prem services**, click **Details** on the Redis service, and use *Show values*.

**In the terminal**
```bash
pskit resources onprem gui cache
```
It lists every web UI of the service with its login. Default port 8082."""),

    A(299, provider="onprem", stage="prod", mode="ask", page="Resources", persona="pasted_error",
      sources=[f"{SV}#troubleshooting"],
      user="pull access denied for redis, repository does not exist or may require 'docker login'\n(creating one-click redis on our server, company blocks docker hub)",
      steps=[S("search_docs", query="pull access denied image mirror one-click",
               docs=[D(SV, "troubleshooting", start="| `pull access denied`", end="| `pull access denied`")])],
      final="""The server can't pull the image. Point the service at a mirror you can pull, with *Advanced → Docker image* (`--image`) [docs/resource-guides/onprem/services.md#troubleshooting].

**In the terminal**
```bash
pskit resources onprem create jobs --service redis --image registry.example.com/mirror/redis:7 --server app-1 --save
```

**In studio**
In **Resources > On-prem services > + Create service**, open *Advanced* and set *Docker image* to your mirror's image."""),

    A(300, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=[f"{SV}#troubleshooting"],
      user="environment variable PSKIT_JOBS_URL (option url_env of queue jobs) is not set on the host",
      steps=[S("search_docs", query="PSKIT url not set on the host env file",
               docs=[D(SV, "troubleshooting", start="| `environment variable PSKIT_..._URL", end="| `environment variable PSKIT_..._URL")])],
      final="""`provider.options.env_file` is missing, or the env file was deleted [docs/resource-guides/onprem/services.md#troubleshooting].

1. Check pskit.yml:
```yaml
provider:
  name: onprem
  options:
    env_file: .env.onprem
```
2. Check that `.env.onprem` exists and has the `PSKIT_JOBS_URL` line. If the file is gone, create the service again with the same key, which writes it:
```bash
pskit resources onprem create jobs --service redis --save
```
3. Deploy again so the host gets the file."""),
]
