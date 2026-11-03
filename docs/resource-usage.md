# Using resources from code: libraries, code and tests

This page is the end-to-end recipe for calling a resource from a Python or Node.js handler: which library to install,
how pskit packages it, the code, and how to test it locally and once deployed. For **your** project the studio
generates the same guide per resource, with your keys and provider filled in: **Resources → How to use** (or
`pskit resources usage <key>`).

```bash
pskit resources usage jobs                 # the whole guide for resource `jobs`, as Markdown
pskit resources usage orders-db -p onprem > docs/orders-db.md
```

## The five steps for any resource

1. **Install** the client library: add it to `requirements.txt` (Python) or `package.json` (Node.js), then
   `pip install -r requirements.txt` / `npm install` locally so `pskit invoke` and `pskit dev` can import it.
2. **Declare** the resource under `resources:` and, for queues, buckets and topics, add a trigger
   (`events: [{queue: {resource: jobs}}]`). Secrets go in variables, never in `pskit.yml`.
3. **Read** it in the handler with `resource("<key>")`: `native_name` / `nativeName`, `url`, `arn`, `id` and your
   `connection` values. A `<name>_env` value is the *name* of a variable: `ctx.env[r["password_env"]]`.
4. **Test locally** with fake events (`pskit invoke -f worker -t queue -d '[...]'`) or `pskit dev`.
5. **Deploy and test** with `pskit resources send` (queues, buckets, topics), `pskit resources check`
   (reachability, from the on-prem host when deployed there) and `pskit logs -f`.

## How dependencies reach the function

| Provider | Python (`requirements.txt`) | Node.js (`package.json`) |
|---|---|---|
| onprem | vendored into the bundle and installed on the host by `pskit deploy` | `npm install --omit=dev` into the bundle |
| aws, alibaba, tencent, huawei, ibm, digitalocean | pip-installed into the zip as Linux wheels by `pskit deploy` | installed into the zip |
| gcp | installed by Cloud Build from the bundled requirements.txt | installed by Cloud Build |
| azure | installed by the remote (Oryx) build | installed by the remote build |
| oracle | installed by the remote build | — |
| cloudflare | resolved by the Workers Python runtime (pure-Python packages only) | — |

`py_serverless_kit` (Python) and `pskit` (Node.js) are bundled with every deployment; never add them yourself.

## Which library for which resource

### Queues, buckets and topics

The **consumer** is the same everywhere: a function with a trigger receives `event.records`, and a `BatchResult`
marks failed records for retry and dead-lettering. **Publishing** depends on the provider:

| Provider | queue | storage | topic |
|---|---|---|---|
| onprem | `submit_queue` (Python, `py_serverless_kit.runtime.onprem_host`) / `submitQueue` (Node.js, `pskit`); honours the driver | `put_object` / `putObject` | `submit_topic` / `submitTopic` |
| aws | `boto3` / `@aws-sdk/client-sqs` (`resource(...).url`) | `boto3` / `@aws-sdk/client-s3` | `boto3` / `@aws-sdk/client-sns` (`.arn`) |
| gcp | `google-cloud-pubsub` / `@google-cloud/pubsub` | `google-cloud-storage` / `@google-cloud/storage` | `google-cloud-pubsub` / `@google-cloud/pubsub` |
| azure | `azure-storage-queue` / `@azure/storage-queue` | `azure-storage-blob` / `@azure/storage-blob` | `azure-servicebus` / `@azure/service-bus` |
| alibaba | `aliyun-mns-sdk` ([guide](resource-guides/alibaba/queue.md)) | S3 API on OSS: `boto3` / `@aws-sdk/client-s3` | MNS topic ([guide](resource-guides/alibaba/topic.md)) |
| tencent | `tencentcloud-sdk-python-tdmq` ([guide](resource-guides/tencent/queue.md)) | S3 API on COS | TDMQ ([guide](resource-guides/tencent/topic.md)) |
| huawei | `pika` (DMS for RabbitMQ, [guide](resource-guides/huawei/queue.md)) | S3 API on OBS | SMN ([guide](resource-guides/huawei/topic.md)) |
| oracle | `oci` ([guide](resource-guides/oracle/queue.md)) | S3 compatibility API (path style) | Notifications ([guide](resource-guides/oracle/topic.md)) |
| ibm | IBM MQ REST with `requests` ([guide](resource-guides/ibm/queue.md)) | S3 API on COS (HMAC keys) | Event Streams ([guide](resource-guides/ibm/topic.md)) |
| digitalocean | `redis` on Managed Valkey ([guide](resource-guides/digitalocean/queue.md)) | S3 API on Spaces | Managed Kafka ([guide](resource-guides/digitalocean/topic.md)) |
| cloudflare | Queues HTTP API ([guide](resource-guides/cloudflare/queue.md)) | S3 API on R2 (`region: auto`) | — |

The S3-compatible stores need the provider's endpoint and HMAC keys:

```python
import boto3

from py_serverless_kit import resource


def write(event, ctx):
    r = resource("uploads")
    s3 = boto3.client(
        "s3",
        endpoint_url=r.get("endpoint", "https://oss-cn-hangzhou.aliyuncs.com"),
        region_name=r.get("region", "cn-hangzhou"),
        aws_access_key_id=ctx.env[r.get("access_key_env", "S3_ACCESS_KEY")],
        aws_secret_access_key=ctx.env[r.get("secret_key_env", "S3_SECRET_KEY")],
    )
    s3.put_object(Bucket=r.native_name, Key="in/hello.txt", Body=b"hello")
    return {"written": "in/hello.txt"}
```

### Databases, caches and other services

| Service | Python | Node.js |
|---|---|---|
| PostgreSQL | `psycopg[binary]` | `pg` |
| MySQL / MariaDB | `pymysql` | `mysql2` |
| MongoDB | `pymongo` | `mongodb` |
| Redis / Valkey | `redis` | `ioredis` |
| Memcached | `pymemcache` | `memjs` |
| SMTP | standard library `smtplib` | `nodemailer` |

```python
import psycopg

from py_serverless_kit import resource


def orders(event, ctx):
    r = resource("orders-db")
    url = ctx.env[r["url_env"]] if r.get("url_env") else None
    with psycopg.connect(url) if url else psycopg.connect(
        host=r["host"], port=r.get("port", 5432), dbname=r.get("database"), user=r.get("user"),
        password=ctx.env[r["password_env"]],
    ) as conn:
        return {"version": conn.execute("select version()").fetchone()[0]}
```

```js
const { Client } = require("pg");
const { resource } = require("pskit");

exports.orders = async () => {
  const r = resource("orders-db");
  const client = new Client({ host: r.get("host"), port: Number(r.get("port", 5432)), database: r.get("database"),
    user: r.get("user"), password: process.env[r.get("password_env")] });
  await client.connect();
  try { return (await client.query("select version()")).rows[0]; } finally { await client.end(); }
};
```

## On premises: from any other program

The simplest way is the **pskit client** ([client.md](client.md)): `from py_serverless_kit.client import PskitClient`
or `const { PskitClient } = require("pskit")`. It goes through the host, so only the host port must be open. Each
on-prem resource's guide (section 7, *Call it from code*) has complete programs for it: 7.1 pskit client, 7.2 HTTP,
7.3 the service's own library, 7.4 what to do when it times out.


A resource is also reachable from scripts and services that are not pskit functions in two other ways. The resource's
*How to use* guide (section 7) shows both ways with Python and Node.js code:

- **Through the pskit host** (standard library / `fetch`, any driver): `POST /__pskit/queues/<name>` and
  `/__pskit/topics/<name>` add data, `GET /__pskit/resources/<key>/data?offset=&limit=` pages through it,
  `POST /__pskit/queues/<name>/lease` + `/ack` consume with leases, `PUT` / `GET` / `DELETE` objects in buckets.
  Send `x-pskit-token` when the host sets `admin_token`.
- **Directly** to the service with its client library (Redis, Kafka, NATS, RabbitMQ, SQS, S3, databases); see
  [one-click services](resource-guides/onprem/services.md#use-it-from-any-program).

## Secrets

| Provider | Where the value lives | How the function reads it |
|---|---|---|
| onprem | `provider.options.env_file` (default `.env.onprem` for one-click services), shipped as `host.env` | `ctx.env[...]` / `process.env[...]` |
| clouds | `environment: {NAME: ${env:LOCAL_NAME}}` (resolved when you deploy) or the cloud's secret store | `ctx.env[...]` / `process.env[...]` |
| local runs | `.env` (loaded by `pskit invoke` and `pskit dev`) | same |

## Testing checklist

| Step | Command |
|---|---|
| unit-test the consumer without a cloud | `pskit invoke -f worker -t queue -d '[{"id": 1}]'` (storage: `-t storage -d '{"bucket": "b", "key": "in/a.csv"}'`) |
| run everything locally | `pskit dev`, then `curl -X POST 'localhost:3000/__pskit/invoke/worker?type=queue' -d '[...]'` |
| deploy | `pskit deploy -p <provider> -s <stage>` |
| send a real message / object | `pskit resources send <key> -d '{...}'` |
| is it reachable? | `pskit resources check <key>` |
| watch the function | `pskit logs -f --function worker` |
| every resource at once | `pskit resources send --list` |

In the studio the same lives under **Resources**: *How to use* (this guide for one resource), *Test* (send a message /
object, *Test connection*) and the **Logs** page.
