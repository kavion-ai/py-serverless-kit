# On-prem resources and drivers

Search terms: on-prem resource, driver, builtin queue, directory driver, redis driver, redis_stream, pskit_host,
custom driver, resource(), connection values, url_env, password_env, external resource, Add resource, Bound to

A resource is an entry under `resources:` in `pskit.yml`: a queue, bucket, topic, database, cache, SMTP server or
any other service the functions use. On premises the host decides **where** a queue, bucket or topic lives with a
**driver**; databases, caches and custom services are passed to the handlers as connection values. This page shows
both, how a one-click service becomes a resource, and how a handler uses it.

## Resource types on premises

On premises each resource type is handled like this:

| Type | Trigger | Where it lives on premises |
|---|---|---|
| `queue` | `queue: {resource: KEY}` | a driver (default `builtin`: files on the host) |
| `storage` | `storage: {resource: KEY}` | a driver (default `builtin`: a folder on the host) |
| `topic` | `topic: {resource: KEY}` | `builtin` or `directory` |
| `smtp` | `smtp: {resource: KEY}` | the [SMTP server](services/smtp.md) service |
| `database`, `cache`, `custom` | none | connection values only: the handler connects itself |

Queues, buckets and topics without a driver are **managed**: the host creates them in its data folder
(`provider.options.data_dir`). A one-click service or a cloud service is **external** (`external: true`): pskit's
deploy never creates or deletes it.

## Queue, storage and topic drivers

On-prem queue, storage and topic resources pick their backend with `options.driver` (when the main provider is not
`onprem`: `providers.onprem.resources.KEY.options.driver`). The drivers that run on your own machines:

| Driver | Types | Options |
|---|---|---|
| `builtin` (default) | queue, storage, topic | none: one JSON file per message, or a folder, under the host's `data_dir` |
| `directory` | queue, storage, topic | `path` (required): this resource's own folder, for example a shared mount |
| `redis` | queue | `url` (`redis://` or `rediss://`, or `url_env`), `key` (default: the name). Lists `<key>`, `<key>:processing`, `<key>:claims`, with crash recovery |
| `redis_stream` | queue | `url` / `url_env`, `key`, `group` (default `pskit`), `consumer`, `maxlen`. A stream with a consumer group (Redis 6.2+ / Valkey): several hosts share the work |
| `pskit_host` | queue | `endpoint` (required, for example `http://10.0.0.6:8080`), `queue`, `token` / `token_env`: a built-in queue of another pskit host, leased through its admin API |
| `minio`, `s3` | storage | an S3-compatible store; see [cloud resources](cloud-resources.md) |
| `custom` | queue, storage | `class: package.module:ClassName` plus any constructor options. See `examples/19-custom-drivers` |

Drivers for other clouds (SQS, Azure, Pub/Sub, GCS, OSS, R2, ...) are on [cloud resources](cloud-resources.md).
Any option marked as a secret may be written as `<name>_env: VARIABLE`; the host reads it from its environment
(the on-prem env file) when it starts.

```yaml
resources:
  jobs:
    type: queue
    external: true
    options: {driver: redis, url_env: PSKIT_JOBS_URL, key: jobs}
  shared-in:
    type: storage
    options: {driver: directory, path: /mnt/share/in}
  orders:
    type: queue
    external: true
    options: {driver: pskit_host, endpoint: "http://10.0.0.6:8080", queue: orders, token_env: OTHER_HOST_TOKEN}
```

## Turn an on-prem service into a resource

An on-prem service becomes a resource in one of three ways:

1. **On create**: the studio's create form adds the resource (and the triggers you ticked) to the draft when the job
   finishes; the CLI does it with `--save`. Click **Save** in studio.
2. **Later, in studio**: a service not in `pskit.yml` shows **Add to pskit.yml** on its row, and a button
   *+ &lt;key&gt; (&lt;service&gt;)* in the hint *On-prem services not in the resource list yet* at the top of the
   Resources page.
3. **By hand**: `pskit resources onprem create ...` without `--save` prints the YAML; paste it under `resources:`.

From an existing resource you can also go the other way: **+ Add resource**, pick a type, then **Create a &lt;type&gt;
on premises** in the hint box. The catalog opens filtered to services that can back that type.

Each service page lists exactly what is written; for example a PostgreSQL service `orders-db`:

```yaml
resources:
  orders-db:
    type: database
    external: true
    connection:
      host: 10.0.0.5
      port: 5432
      database: orders_db
      user: pskit
      password_env: PSKIT_ORDERS_DB_PASSWORD
      url_env: PSKIT_ORDERS_DB_URL
```

## Add or edit a resource in studio

The resource drawer edits any resource, including the on-prem driver.

1. Open **Resources** and click **+ Add resource** (or click a resource name to open *Resource &lt;key&gt;*).
2. **Key**: how handlers refer to it, `resource("key")`, and triggers use `resource: key`.
3. **Type**: storage, queue, topic, database, cache, custom (or smtp).
4. **Mode**: **Managed by pskit** (queue, storage, topic, smtp only: pskit creates it on deploy) or **External /
   existing** (pskit never creates or deletes it).
5. **Native name**: the real bucket / queue name; defaults to the key.
6. **Connection**: key/value pairs handed to handlers as `PSKIT_RESOURCE_<KEY>_<NAME>`. Use **From env var** for
   secrets, never a literal password.
7. **Bound functions**: tick functions to limit who gets the variables; none ticked means every function.
8. For queue, storage and topic: the **On-premises driver** box. Pick a driver chip (grouped by cloud: *Self-hosted*,
   *Built-in & custom*, AWS, Azure, ...) and fill its fields. The driver is stored in `resources.KEY.options`, or in
   `providers.onprem.resources.KEY.options` when the main provider is another cloud. **How to set up a &lt;type&gt;**
   opens the guide.
9. For the custom driver: **Class** (`package.module:ClassName`) and **Constructor arguments** (a key ending in `_env`
   is read from the host's environment).
10. Click **Add** (or **Apply**), then **Save** in the top bar.

## Use an on-prem resource from a handler

`resource("KEY")` returns the resource bound to the current function: `type`, `native_name`, `external` and the
`connection` values (keys are case-insensitive). A connection value that ends in `_env` holds the **name** of a
variable; read the value with `ctx.env[...]`. The host loads the on-prem env file at start, so those variables are
set.

```python
import psycopg

from py_serverless_kit import resource


def list_orders(event, ctx):
    db = resource("orders-db")
    with psycopg.connect(ctx.env[db["url_env"]]) as conn:
        rows = conn.execute("select id from orders order by id desc limit 5").fetchall()
    return {"ids": [r[0] for r in rows]}
```

Queues, buckets and topics are consumed through triggers, whatever the driver, and published through the host:

```python
from py_serverless_kit import resource
from py_serverless_kit.runtime.onprem_host import put_object, submit_queue, submit_topic


def publish(event, ctx):
    submit_queue(resource("jobs").native_name, {"order_id": 1})
    submit_topic(resource("events").native_name, {"type": "order.created"})
    put_object(resource("files").native_name, "in/order-1.json", b'{"order_id": 1}')
    return {"ok": True}
```

`resources()` returns every bound resource. **How to use** on a resource row (or `pskit resources usage KEY`) prints
handler code for Python and Node.js, the libraries to install and tests. More on handlers:
[handlers](../handlers.md).

## See which functions use a resource

The **Bound to** column of the Resources table shows the functions that really use a resource: ⚡ for a trigger on
it, and functions whose handler file calls `resource("key")` or reads `PSKIT_RESOURCE_<KEY>_*`. Under the chips it
says *functions: N of M* when `functions:` limits the binding, or *variables available to all N functions*. The
**Mode** column shows *external* or *managed*, plus *on-prem &lt;service&gt; · &lt;server&gt;* when a one-click
service backs it; **On-prem driver** shows the driver (`builtin` when none).

## Test, browse and clear an on-prem resource

On-prem resources can be tested from studio and the terminal once the host is deployed (otherwise from this machine).

| Task | Studio (Resources page) | CLI |
|---|---|---|
| Connection check, queue depth, object count | **Test** → *Test connection* | `pskit resources check KEY` |
| Send a test message / object | **Test** | `pskit resources send KEY -d '{"order_id": 1}'` |
| Browse messages or objects (nothing is consumed) | **Data** (queue, storage, topic) | `pskit resources data KEY [--offset 20 -n 20] [--prefix in/]` |
| Delete every message / object of a built-in resource | **Delete → Delete with its data** | `pskit resources clear KEY` |
| Handler code and tests | **How to use** | `pskit resources usage KEY` |

Browsing works for built-in and directory resources, Redis lists and streams, another pskit host and every storage
driver; SQS / ElasticMQ, Azure queues, Pub/Sub, MNS and Cloudflare queues show the depth only.

## Delete an on-prem resource

**Delete** on a resource row asks what to do, depending on what is behind it:

| Behind the resource | Choices |
|---|---|
| a one-click on-prem service | **pskit.yml only**, **Stop service, keep data**, **Delete service and data** |
| a built-in queue, bucket or topic on the host | **Delete, keep data**, **Delete with its data** |
| anything else | **Delete** (external: nothing is deleted outside; managed: the next deploy removes it) |

Triggers that use the resource are named in the confirmation and stop validating until you change them. Click
**Save** afterwards.

## See also

- [On-prem services](services/README.md)
- [Attach cloud resources to on-prem functions](cloud-resources.md)
- [Resources (all providers)](../resources.md)
- [Triggers](../triggers/README.md)
- [Existing on-prem resource guides](../resource-guides/onprem/README.md)
