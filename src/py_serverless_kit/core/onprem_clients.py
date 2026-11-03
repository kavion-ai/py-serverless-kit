"""Use an on-prem resource from *any* program: a script, a web app, a cron job, another service.

Two ways, both shown with Python and Node.js code and terminal commands:

* **through the pskit host** (``/__pskit/...`` HTTP API): works for every queue, bucket and
  topic whatever its driver, needs only the standard library / ``fetch``;
* **directly to the service** with its own client library, when pskit knows which one
  (Redis lists and streams, SQS / ElasticMQ, Kafka, NATS JetStream, RabbitMQ, S3 / MinIO,
  and databases / caches).

Messages written directly use the format the host's driver reads, so a pskit trigger
picks them up; reading directly next to a pskit trigger competes with it, which the text
says where it matters.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

Snip = Dict[str, Any]


def _py_env(var: str) -> str:
    return f'os.environ["{var}"]'


# ----------------------------------------------------------------------------- through the host


def via_host(kind: str, name: str, key: str, endpoint: str) -> Snip:
    """The pskit host's HTTP API: publish, look at the data, consume with leases."""
    base = endpoint.rstrip("/") or "http://127.0.0.1:8080"
    if kind == "storage":
        py = f'''import json
import os
import urllib.parse
import urllib.request

HOST = os.environ.get("PSKIT_HOST", "{base}")
TOKEN = os.environ.get("PSKIT_ADMIN_TOKEN", "")      # the host's provider.options.admin_token, if set


def call(method, path, data=None):
    req = urllib.request.Request(HOST + path, data=data, method=method)
    if TOKEN:
        req.add_header("x-pskit-token", TOKEN)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


# Write an object (fires the bucket's storage triggers)
call("PUT", "/__pskit/storage/{name}/in/hello.txt", b"hello from a script")

# List objects, 50 per page
page = json.loads(call("GET", "/__pskit/resources/{key}/data?offset=0&limit=50"))
for item in page["items"]:
    print(item["key"], item["size"])

# Read one object
obj = json.loads(call("GET", "/__pskit/resources/{key}/object?key=" + urllib.parse.quote("in/hello.txt")))
print(obj["content"])

# Delete it
call("DELETE", "/__pskit/storage/{name}/in/hello.txt")
'''
        js = f'''const HOST = process.env.PSKIT_HOST || "{base}";
const headers = process.env.PSKIT_ADMIN_TOKEN ? {{ "x-pskit-token": process.env.PSKIT_ADMIN_TOKEN }} : {{}};

async function main() {{
  // Write an object (fires the bucket's storage triggers)
  await fetch(`${{HOST}}/__pskit/storage/{name}/in/hello.txt`, {{ method: "PUT", headers, body: "hello from a script" }});

  // List objects, 50 per page
  const page = await (await fetch(`${{HOST}}/__pskit/resources/{key}/data?offset=0&limit=50`, {{ headers }})).json();
  for (const item of page.items) console.log(item.key, item.size);

  // Read one object
  const obj = await (await fetch(`${{HOST}}/__pskit/resources/{key}/object?key=${{encodeURIComponent("in/hello.txt")}}`, {{ headers }})).json();
  console.log(obj.content);

  // Delete it
  await fetch(`${{HOST}}/__pskit/storage/{name}/in/hello.txt`, {{ method: "DELETE", headers }});
}}

main();
'''
        cli = [
            f"curl -X PUT --data-binary @report.csv {base}/__pskit/storage/{name}/in/report.csv",
            f"curl '{base}/__pskit/resources/{key}/data?offset=0&limit=50'",
            f"curl '{base}/__pskit/resources/{key}/object?key=in/report.csv'",
            f"curl -X DELETE {base}/__pskit/storage/{name}/in/report.csv",
        ]
        return {"python": py, "node": js, "cli": cli, "requirements": {"python": [], "node": []}}
    path = "topics" if kind == "topic" else "queues"
    consume_py = (
        f'''
# Consume outside pskit (at-least-once): lease, process, then ack (or nack to retry).
# Do this only for a queue no pskit trigger consumes, or the two share the messages.
leased = json.loads(call("POST", "/__pskit/queues/{name}/lease", {{"batch": 10, "visibility": 60}}))["messages"]
done = []
for msg in leased:
    print("processing", msg["id"], msg["body"])
    done.append(msg["receipt"])
call("POST", "/__pskit/queues/{name}/ack", {{"receipts": done}})
'''
        if kind == "queue"
        else ""
    )
    consume_js = (
        f'''
  // Consume outside pskit (at-least-once): lease, process, then ack (or nack to retry).
  // Do this only for a queue no pskit trigger consumes, or the two share the messages.
  const {{ messages }} = await call("POST", "/__pskit/queues/{name}/lease", {{ batch: 10, visibility: 60 }});
  for (const msg of messages) console.log("processing", msg.id, msg.body);
  await call("POST", "/__pskit/queues/{name}/ack", {{ receipts: messages.map((m) => m.receipt) }});
'''
        if kind == "queue"
        else ""
    )
    py = f'''import json
import os
import urllib.request

HOST = os.environ.get("PSKIT_HOST", "{base}")
TOKEN = os.environ.get("PSKIT_ADMIN_TOKEN", "")      # the host's provider.options.admin_token, if set


def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(HOST + path, data=data, method=method)
    req.add_header("content-type", "application/json")
    if TOKEN:
        req.add_header("x-pskit-token", TOKEN)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


# Add data (goes through the resource's driver; pskit triggers receive it)
call("POST", "/__pskit/{path}/{name}", {{"message": {{"order_id": 1}}, "attributes": {{"kind": "new"}}}})
call("POST", "/__pskit/{path}/{name}", {{"messages": [{{"order_id": 2}}, {{"order_id": 3}}]}})

# Look at what is waiting, 50 per page (does not remove anything)
page = json.loads(call("GET", "/__pskit/resources/{key}/data?offset=0&limit=50"))
print(page["total"], "waiting")
for item in page["items"]:
    print(item["id"], item["body"])
{consume_py}'''
    js = f'''const HOST = process.env.PSKIT_HOST || "{base}";

async function call(method, path, body) {{
  const headers = {{ "content-type": "application/json" }};
  if (process.env.PSKIT_ADMIN_TOKEN) headers["x-pskit-token"] = process.env.PSKIT_ADMIN_TOKEN;
  const resp = await fetch(HOST + path, {{ method, headers, body: body === undefined ? undefined : JSON.stringify(body) }});
  if (!resp.ok) throw new Error(`${{resp.status}} ${{await resp.text()}}`);
  return resp.json();
}}

async function main() {{
  // Add data (goes through the resource's driver; pskit triggers receive it)
  await call("POST", "/__pskit/{path}/{name}", {{ message: {{ orderId: 1 }}, attributes: {{ kind: "new" }} }});

  // Look at what is waiting, 50 per page (does not remove anything)
  const page = await call("GET", "/__pskit/resources/{key}/data?offset=0&limit=50");
  console.log(page.total, "waiting");
  for (const item of page.items) console.log(item.id, item.body);
{consume_js}}}

main();
'''
    cli = [
        f"curl -X POST {base}/__pskit/{path}/{name} -H 'content-type: application/json' -d '{{\"order_id\": 1}}'",
        f"curl '{base}/__pskit/resources/{key}/data?offset=0&limit=50'",
    ]
    if kind == "queue":
        cli.append(f"curl {base}/__pskit/queues/{name}            # depth")
    return {"python": py, "node": js, "cli": cli, "requirements": {"python": [], "node": []}}


# ----------------------------------------------------------------------------- directly


def direct(flavor: str, values: Dict[str, Any]) -> Optional[Snip]:
    """Client-library code for ``flavor`` (redis, redis_stream, sqs, kafka, nats, rabbitmq, s3,
    postgres, mysql, mongodb, cache_redis, memcached, smtp). ``values`` holds names and env vars."""
    v = {k: str(x) for k, x in values.items()}
    url = v.get("url_env", "PSKIT_URL")
    if flavor == "redis":
        lkey = v.get("key", "jobs")
        py = f'''import json
import os
import time
import uuid

import redis

r = redis.from_url({_py_env(url)}, socket_connect_timeout=5, socket_timeout=10)   # from {v.get("env_file", ".env.onprem")}

# Add data: the envelope the pskit redis driver reads (plain strings work too)
r.lpush("{lkey}", json.dumps({{"id": uuid.uuid4().hex, "body": json.dumps({{"order_id": 1}}),
                            "attributes": {{}}, "receives": 0, "enqueued_at": time.time()}}))

# Look at the queue without removing anything (newest first)
print(r.llen("{lkey}"), "waiting")
for raw in r.lrange("{lkey}", 0, 49):
    print(json.loads(raw)["body"] if raw.startswith(b"{{") else raw)

# Take one off the queue yourself (only if no pskit trigger consumes "{lkey}")
item = r.brpop("{lkey}", timeout=5)
'''
        js = f'''const Redis = require("ioredis");
const {{ randomUUID }} = require("crypto");

async function main() {{
  const r = new Redis(process.env.{url}, {{ connectTimeout: 5000, maxRetriesPerRequest: 1 }});

  // Add data: the envelope the pskit redis driver reads (plain strings work too)
  await r.lpush("{lkey}", JSON.stringify({{ id: randomUUID(), body: JSON.stringify({{ orderId: 1 }}), attributes: {{}}, receives: 0, enqueued_at: Date.now() / 1000 }}));

  // Look at the queue without removing anything (newest first)
  console.log(await r.llen("{lkey}"), "waiting");
  for (const raw of await r.lrange("{lkey}", 0, 49)) console.log(raw);

  // Take one off the queue yourself (only if no pskit trigger consumes "{lkey}")
  const item = await r.brpop("{lkey}", 5);
  r.disconnect();
}}

main();
'''
        cli = [f'redis-cli -u "${url}" LPUSH {lkey} \'{{"order_id": 1}}\'', f'redis-cli -u "${url}" LRANGE {lkey} 0 49',
               f'redis-cli -u "${url}" LLEN {lkey}']
        return {"python": py, "node": js, "cli": cli, "requirements": {"python": ["redis"], "node": ["ioredis"]}}
    if flavor == "redis_stream":
        skey = v.get("key", "jobs")
        py = f'''import json
import os

import redis

r = redis.from_url({_py_env(url)}, socket_connect_timeout=5, socket_timeout=10)   # from {v.get("env_file", ".env.onprem")}

# Add data (the fields the pskit redis_stream driver reads)
r.xadd("{skey}", {{"body": json.dumps({{"order_id": 1}}), "attributes": json.dumps({{"kind": "new"}})}})

# Read without consuming: the 50 oldest entries
for entry_id, fields in r.xrange("{skey}", count=50):
    print(entry_id, fields[b"body"])

# Consume with YOUR OWN consumer group (pskit's group "pskit" keeps its own position)
try:
    r.xgroup_create("{skey}", "my-app", id="0", mkstream=True)
except redis.ResponseError:
    pass                                         # the group exists
for _stream, entries in r.xreadgroup("my-app", "worker-1", {{"{skey}": ">"}}, count=10, block=2000):
    for entry_id, fields in entries:
        print("processing", fields[b"body"])
        r.xack("{skey}", "my-app", entry_id)
'''
        js = f'''const Redis = require("ioredis");

async function main() {{
  const r = new Redis(process.env.{url}, {{ connectTimeout: 5000, maxRetriesPerRequest: 1 }});

  // Add data (the fields the pskit redis_stream driver reads)
  await r.xadd("{skey}", "*", "body", JSON.stringify({{ orderId: 1 }}), "attributes", JSON.stringify({{ kind: "new" }}));

  // Read without consuming: the 50 oldest entries
  for (const [id, fields] of await r.xrange("{skey}", "-", "+", "COUNT", 50)) console.log(id, fields);

  // Consume with YOUR OWN consumer group (pskit's group "pskit" keeps its own position)
  await r.xgroup("CREATE", "{skey}", "my-app", "0", "MKSTREAM").catch(() => {{}});
  const res = await r.xreadgroup("GROUP", "my-app", "worker-1", "COUNT", 10, "BLOCK", 2000, "STREAMS", "{skey}", ">");
  for (const [, entries] of res || []) {{
    for (const [id, fields] of entries) {{
      console.log("processing", fields);
      await r.xack("{skey}", "my-app", id);
    }}
  }}
  r.disconnect();
}}

main();
'''
        cli = [f'redis-cli -u "${url}" XADD {skey} \'*\' body \'{{"order_id": 1}}\'', f'redis-cli -u "${url}" XRANGE {skey} - + COUNT 50',
               f'redis-cli -u "${url}" XINFO GROUPS {skey}']
        return {"python": py, "node": js, "cli": cli, "requirements": {"python": ["redis"], "node": ["ioredis"]}}
    if flavor == "sqs":
        queue_url = v.get("queue_url", "")
        endpoint = v.get("endpoint", "")
        ep_py = f', endpoint_url="{endpoint}"' if endpoint else ""
        ep_js = f'endpoint: "{endpoint}", ' if endpoint else ""
        creds_py = ', aws_access_key_id="pskit", aws_secret_access_key="pskit"' if endpoint else ""
        creds_js = 'credentials: { accessKeyId: "pskit", secretAccessKey: "pskit" }, ' if endpoint else ""
        py = f'''import json

import boto3
from botocore.config import Config

# Fail in seconds when the port is closed, instead of retrying for minutes
quick = Config(connect_timeout=5, read_timeout=25, retries={{"total_max_attempts": 1, "mode": "standard"}})
sqs = boto3.client("sqs", region_name="{v.get("region", "us-east-1")}"{ep_py}{creds_py}, config=quick)
QUEUE = "{queue_url}"

# Add data
sqs.send_message(QueueUrl=QUEUE, MessageBody=json.dumps({{"order_id": 1}}))

# How many are waiting
print(sqs.get_queue_attributes(QueueUrl=QUEUE, AttributeNames=["ApproximateNumberOfMessages"]))

# Read and delete (only if no pskit trigger consumes this queue)
for msg in sqs.receive_message(QueueUrl=QUEUE, MaxNumberOfMessages=10, WaitTimeSeconds=2).get("Messages", []):
    print("processing", msg["Body"])
    sqs.delete_message(QueueUrl=QUEUE, ReceiptHandle=msg["ReceiptHandle"])
'''
        js = f'''const {{ SQSClient, SendMessageCommand, ReceiveMessageCommand, DeleteMessageCommand }} = require("@aws-sdk/client-sqs");

const sqs = new SQSClient({{ region: "{v.get("region", "us-east-1")}", {ep_js}{creds_js}maxAttempts: 1, requestHandler: {{ connectionTimeout: 5000 }} }});
const QUEUE = "{queue_url}";

async function main() {{
  // Add data
  await sqs.send(new SendMessageCommand({{ QueueUrl: QUEUE, MessageBody: JSON.stringify({{ orderId: 1 }}) }}));

  // Read and delete (only if no pskit trigger consumes this queue)
  const out = await sqs.send(new ReceiveMessageCommand({{ QueueUrl: QUEUE, MaxNumberOfMessages: 10, WaitTimeSeconds: 2 }}));
  for (const msg of out.Messages || []) {{
    console.log("processing", msg.Body);
    await sqs.send(new DeleteMessageCommand({{ QueueUrl: QUEUE, ReceiptHandle: msg.ReceiptHandle }}));
  }}
}}

main();
'''
        flag = f" --endpoint-url {endpoint}" if endpoint else ""
        cli = [f"aws sqs send-message{flag} --queue-url {queue_url} --message-body '{{\"order_id\": 1}}'",
               f"aws sqs get-queue-attributes{flag} --queue-url {queue_url} --attribute-names ApproximateNumberOfMessages"]
        return {"python": py, "node": js, "cli": cli, "requirements": {"python": ["boto3"], "node": ["@aws-sdk/client-sqs"]}}
    if flavor == "kafka":
        servers, topic = v.get("bootstrap_servers", "127.0.0.1:9092"), v.get("topic", "events")
        py = f'''import json

from kafka import KafkaConsumer, KafkaProducer

SERVERS = "{servers}".split(",")

# Add data
producer = KafkaProducer(bootstrap_servers=SERVERS, value_serializer=lambda v: json.dumps(v).encode(),
                         request_timeout_ms=10000, max_block_ms=10000)
producer.send("{topic}", {{"order_id": 1}}).get(timeout=30)

# Read with YOUR OWN group id (pskit's group keeps its own offsets)
consumer = KafkaConsumer("{topic}", bootstrap_servers=SERVERS, group_id="my-app", auto_offset_reset="earliest",
                         consumer_timeout_ms=5000)
for record in consumer:
    print(record.offset, record.value)
'''
        js = f'''const {{ Kafka }} = require("kafkajs");

const kafka = new Kafka({{ brokers: "{servers}".split(","), connectionTimeout: 5000, retry: {{ retries: 1 }} }});

async function main() {{
  // Add data
  const producer = kafka.producer();
  await producer.connect();
  await producer.send({{ topic: "{topic}", messages: [{{ value: JSON.stringify({{ orderId: 1 }}) }}] }});
  await producer.disconnect();

  // Read with YOUR OWN group id (pskit's group keeps its own offsets)
  const consumer = kafka.consumer({{ groupId: "my-app" }});
  await consumer.connect();
  await consumer.subscribe({{ topic: "{topic}", fromBeginning: true }});
  await consumer.run({{ eachMessage: async ({{ message }}) => console.log(message.offset, message.value.toString()) }});
}}

main();
'''
        cli = [f"docker exec -it {v.get('container', '<container>')} rpk topic produce {topic}", f"docker exec -it {v.get('container', '<container>')} rpk topic consume {topic} -n 10",
               f"docker exec -it {v.get('container', '<container>')} rpk group describe {v.get('group_id', '<group>')}"]
        return {"python": py, "node": js, "cli": cli, "requirements": {"python": ["kafka-python"], "node": ["kafkajs"]}}
    if flavor == "nats":
        stream, subject = v.get("stream", "jobs"), v.get("subject", "jobs.jobs")
        py = f'''import asyncio
import json
import os

import nats


async def main():
    nc = await nats.connect({_py_env(url)}, connect_timeout=5, max_reconnect_attempts=1)
    js = nc.jetstream()

    # Add data
    ack = await js.publish("{subject}", json.dumps({{"order_id": 1}}).encode())
    print("stored as", ack.seq)

    # How many are waiting for pskit's consumer
    info = await js.consumer_info("{stream}", "pskit")
    print(info.num_pending, "pending")

    # Read with YOUR OWN durable consumer (pskit's "pskit" consumer keeps its own position)
    sub = await js.pull_subscribe("{subject}", durable="my-app")
    for msg in await sub.fetch(10, timeout=2):
        print("processing", msg.data)
        await msg.ack()
    await nc.close()


asyncio.run(main())
'''
        js = f'''const {{ connect, StringCodec }} = require("nats");

async function main() {{
  // nats.js takes the credentials separately from the server address.
  const u = new URL(process.env.{url});
  const nc = await connect({{ servers: `${{u.hostname}}:${{u.port || 4222}}`, user: decodeURIComponent(u.username), pass: decodeURIComponent(u.password), timeout: 5000 }});
  const js = nc.jetstream();
  const sc = StringCodec();

  // Add data
  const ack = await js.publish("{subject}", sc.encode(JSON.stringify({{ orderId: 1 }})));
  console.log("stored as", ack.seq);

  // Read with YOUR OWN durable consumer (pskit's "pskit" consumer keeps its own position)
  const jsm = await nc.jetstreamManager();
  await jsm.consumers.add("{stream}", {{ durable_name: "my-app", ack_policy: "explicit" }}).catch(() => {{}});
  const consumer = await js.consumers.get("{stream}", "my-app");
  const batch = await consumer.fetch({{ max_messages: 10, expires: 2000 }});
  for await (const m of batch) {{
    console.log("processing", sc.decode(m.data));
    m.ack();
  }}
  await nc.close();
}}

main();
'''
        cli = [f'nats --server "${url}" pub {subject} \'{{"order_id": 1}}\'', f'nats --server "${url}" stream info {stream}',
               f'nats --server "${url}" consumer info {stream} pskit']
        return {"python": py, "node": js, "cli": cli, "requirements": {"python": ["nats-py"], "node": ["nats"]}}
    if flavor == "rabbitmq":
        queue = v.get("queue", "jobs")
        py = f'''import json
import os

import pika

params = pika.URLParameters({_py_env(url)})
params.socket_timeout = 5
params.connection_attempts = 1
conn = pika.BlockingConnection(params)
ch = conn.channel()
ch.queue_declare(queue="{queue}", durable=True)

# Add data
ch.basic_publish(exchange="", routing_key="{queue}", body=json.dumps({{"order_id": 1}}),
                 properties=pika.BasicProperties(delivery_mode=2))

# How many are waiting
print(ch.queue_declare(queue="{queue}", passive=True).method.message_count, "waiting")

# Take one (only if no pskit trigger consumes this queue)
method, props, body = ch.basic_get(queue="{queue}", auto_ack=False)
if method:
    print("processing", body)
    ch.basic_ack(method.delivery_tag)
conn.close()
'''
        js = f'''const amqp = require("amqplib");

async function main() {{
  const conn = await amqp.connect(process.env.{url}, {{ timeout: 5000 }});
  const ch = await conn.createChannel();
  await ch.assertQueue("{queue}", {{ durable: true }});

  // Add data
  ch.sendToQueue("{queue}", Buffer.from(JSON.stringify({{ orderId: 1 }})), {{ persistent: true }});

  // How many are waiting
  console.log((await ch.checkQueue("{queue}")).messageCount, "waiting");

  // Take one (only if no pskit trigger consumes this queue)
  const msg = await ch.get("{queue}", {{ noAck: false }});
  if (msg) {{
    console.log("processing", msg.content.toString());
    ch.ack(msg);
  }}
  await conn.close();
}}

main();
'''
        cli = [f"open {v.get('management_url', 'http://<host>:15672')} (user {v.get('user', 'pskit')}) > Queues > {queue} > Publish / Get messages"]
        return {"python": py, "node": js, "cli": cli, "requirements": {"python": ["pika"], "node": ["amqplib"]}}
    if flavor == "s3":
        endpoint, bucket = v.get("endpoint", ""), v.get("bucket", "files")
        ak, sk = v.get("access_key_env", "S3_ACCESS_KEY"), v.get("secret_key_env", "S3_SECRET_KEY")
        py = f'''import os

import boto3
from botocore.config import Config

s3 = boto3.client("s3", endpoint_url="{endpoint}", region_name="us-east-1",
                  aws_access_key_id={_py_env(ak)}, aws_secret_access_key={_py_env(sk)},
                  config=Config(connect_timeout=5, retries={{"total_max_attempts": 1, "mode": "standard"}}))

# Add data (pskit storage triggers see it on their next poll)
s3.put_object(Bucket="{bucket}", Key="in/hello.txt", Body=b"hello")

# List, page by page
for page in s3.get_paginator("list_objects_v2").paginate(Bucket="{bucket}", PaginationConfig={{"PageSize": 50}}):
    for obj in page.get("Contents", []):
        print(obj["Key"], obj["Size"])

# Read and delete
print(s3.get_object(Bucket="{bucket}", Key="in/hello.txt")["Body"].read())
s3.delete_object(Bucket="{bucket}", Key="in/hello.txt")
'''
        js = f'''const {{ S3Client, PutObjectCommand, ListObjectsV2Command, GetObjectCommand }} = require("@aws-sdk/client-s3");

const s3 = new S3Client({{
  endpoint: "{endpoint}", region: "us-east-1", forcePathStyle: true, maxAttempts: 1, requestHandler: {{ connectionTimeout: 5000 }},
  credentials: {{ accessKeyId: process.env.{ak}, secretAccessKey: process.env.{sk} }},
}});

async function main() {{
  // Add data (pskit storage triggers see it on their next poll)
  await s3.send(new PutObjectCommand({{ Bucket: "{bucket}", Key: "in/hello.txt", Body: "hello" }}));

  // List 50 at a time
  const page = await s3.send(new ListObjectsV2Command({{ Bucket: "{bucket}", MaxKeys: 50 }}));
  for (const obj of page.Contents || []) console.log(obj.Key, obj.Size);

  // Read
  const out = await s3.send(new GetObjectCommand({{ Bucket: "{bucket}", Key: "in/hello.txt" }}));
  console.log(await out.Body.transformToString());
}}

main();
'''
        cli = [f'aws s3 cp report.csv s3://{bucket}/in/report.csv --endpoint-url {endpoint}', f"aws s3 ls s3://{bucket} --recursive --endpoint-url {endpoint}",
               f'mc alias set local {endpoint} "${ak}" "${sk}" && mc ls local/{bucket}']
        return {"python": py, "node": js, "cli": cli, "requirements": {"python": ["boto3"], "node": ["@aws-sdk/client-s3"]}}
    if flavor in ("postgres", "mysql", "mongodb", "cache_redis", "memcached", "smtp"):
        return _service_client(flavor, v, url)
    return None


def _service_client(flavor: str, v: Dict[str, str], url: str) -> Snip:
    host, port = v.get("host", "127.0.0.1"), v.get("port", "")
    if flavor == "postgres":
        py = f'''import os

import psycopg

with psycopg.connect({_py_env(url)}, connect_timeout=5) as conn:
    conn.execute("create table if not exists notes (id serial primary key, text text)")
    conn.execute("insert into notes (text) values (%s)", ("hello",))
    for row in conn.execute("select id, text from notes order by id desc limit 50"):
        print(row)
'''
        js = f'''const {{ Client }} = require("pg");

async function main() {{
  const db = new Client({{ connectionString: process.env.{url}, connectionTimeoutMillis: 5000 }});
  await db.connect();
  await db.query("create table if not exists notes (id serial primary key, text text)");
  await db.query("insert into notes (text) values ($1)", ["hello"]);
  console.log((await db.query("select id, text from notes order by id desc limit 50")).rows);
  await db.end();
}}

main();
'''
        return {"python": py, "node": js, "cli": [f'psql "${url}" -c "select now()"'],
                "requirements": {"python": ["psycopg[binary]"], "node": ["pg"]}}
    if flavor == "mysql":
        py = f'''import os
from urllib.parse import unquote, urlsplit

import pymysql

u = urlsplit({_py_env(url)})
conn = pymysql.connect(host=u.hostname, port=u.port or 3306, user=unquote(u.username), password=unquote(u.password),
                       database=u.path.lstrip("/"), autocommit=True, connect_timeout=5)
with conn.cursor() as cur:
    cur.execute("create table if not exists notes (id int auto_increment primary key, text varchar(200))")
    cur.execute("insert into notes (text) values (%s)", ("hello",))
    cur.execute("select id, text from notes order by id desc limit 50")
    print(cur.fetchall())
conn.close()
'''
        js = f'''const mysql = require("mysql2/promise");

async function main() {{
  const db = await mysql.createConnection({{ uri: process.env.{url}, connectTimeout: 5000 }});
  await db.query("create table if not exists notes (id int auto_increment primary key, text varchar(200))");
  await db.query("insert into notes (text) values (?)", ["hello"]);
  console.log((await db.query("select id, text from notes order by id desc limit 50"))[0]);
  await db.end();
}}

main();
'''
        return {"python": py, "node": js, "cli": [f'mysql -h {host} -P {port or 3306} -u {v.get("user", "pskit")} -p'],
                "requirements": {"python": ["pymysql"], "node": ["mysql2"]}}
    if flavor == "mongodb":
        py = f'''import os

from pymongo import MongoClient

client = MongoClient({_py_env(url)}, serverSelectionTimeoutMS=5000)
notes = client["app"]["notes"]
notes.insert_one({{"text": "hello"}})
for doc in notes.find().sort("_id", -1).limit(50):
    print(doc)
'''
        js = f'''const {{ MongoClient }} = require("mongodb");

async function main() {{
  const client = await MongoClient.connect(process.env.{url}, {{ serverSelectionTimeoutMS: 5000 }});
  const notes = client.db("app").collection("notes");
  await notes.insertOne({{ text: "hello" }});
  console.log(await notes.find().sort({{ _id: -1 }}).limit(50).toArray());
  await client.close();
}}

main();
'''
        return {"python": py, "node": js, "cli": [f'mongosh "${url}"'],
                "requirements": {"python": ["pymongo"], "node": ["mongodb"]}}
    if flavor == "cache_redis":
        py = f'''import os

import redis

r = redis.from_url({_py_env(url)}, socket_connect_timeout=5, socket_timeout=10)
r.set("greeting", "hello", ex=3600)
print(r.get("greeting"))
for key in r.scan_iter(count=100):      # browse keys page by page
    print(key)
'''
        js = f'''const Redis = require("ioredis");

async function main() {{
  const r = new Redis(process.env.{url}, {{ connectTimeout: 5000, maxRetriesPerRequest: 1 }});
  await r.set("greeting", "hello", "EX", 3600);
  console.log(await r.get("greeting"));
  const [, keys] = await r.scan(0, "COUNT", 100);
  console.log(keys);
  r.disconnect();
}}

main();
'''
        return {"python": py, "node": js, "cli": [f'redis-cli -u "${url}" SET greeting hello', f'redis-cli -u "${url}" --scan --count 100'],
                "requirements": {"python": ["redis"], "node": ["ioredis"]}}
    if flavor == "memcached":
        py = f'''from pymemcache.client.base import Client

client = Client(("{host}", {port or 11211}), connect_timeout=5, timeout=5)
client.set("greeting", "hello", expire=3600)
print(client.get("greeting"))
'''
        js = f'''const memjs = require("memjs");

async function main() {{
  const client = memjs.Client.create("{host}:{port or 11211}", {{ timeout: 5, retries: 1 }});
  await client.set("greeting", "hello", {{ expires: 3600 }});
  console.log((await client.get("greeting")).value.toString());
  client.close();
}}

main();
'''
        return {"python": py, "node": js, "cli": [f"printf 'stats\\r\\nquit\\r\\n' | nc {host} {port or 11211}"],
                "requirements": {"python": ["pymemcache"], "node": ["memjs"]}}
    py = f'''import smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg["From"], msg["To"], msg["Subject"] = "app@example.com", "you@example.com", "Hello"
msg.set_content("Sent from a script.")
with smtplib.SMTP("{host}", {port or 25}, timeout=10) as smtp:
    smtp.send_message(msg)
'''
    js = f'''const nodemailer = require("nodemailer");

nodemailer.createTransport({{ host: "{host}", port: {port or 25}, connectionTimeout: 5000 }})
  .sendMail({{ from: "app@example.com", to: "you@example.com", subject: "Hello", text: "Sent from a script." }})
  .then(() => console.log("sent"));
'''
    web = v.get("web_url", "")
    return {"python": py, "node": js, "cli": [f"open {web} to read the mails" if web else f"nc {host} {port or 25}"],
            "requirements": {"python": [], "node": ["nodemailer"]}}


# ----------------------------------------------------------------------------- which flavor


def flavor_for(kind: str, options: Dict[str, Any], connection: Dict[str, Any], service: Optional[str]) -> Optional[str]:
    driver = options.get("driver")
    driver = driver.get("use") if isinstance(driver, dict) else driver
    cls = str(options.get("class") or "")
    if kind == "queue":
        if driver in ("redis", "redis_stream", "sqs"):
            return str(driver)
        if "kafka_queue" in cls or service == "kafka":
            return "kafka"
        if "nats_queue" in cls or service == "nats":
            return "nats"
        if "rabbitmq_queue" in cls or service == "rabbitmq":
            return "rabbitmq"
        return None
    if kind == "storage":
        return "s3" if driver in ("s3", "minio") or service == "minio" else None
    if kind in ("database", "cache", "custom"):
        from .resource_code import flavor_of

        class _R:  # flavor_of reads .connection
            pass

        res = _R()
        res.connection = connection  # type: ignore[attr-defined]
        flavor = flavor_of(res, service)
        return "cache_redis" if flavor == "redis" else (flavor if flavor != "generic" else None)
    return None


def markdown(
    title: str,
    intro: str,
    host: Optional[Snip],
    direct_snip: Optional[Snip],
    direct_label: str,
    client: Optional[Snip] = None,
    host_label: str = "Over HTTP through the pskit host (any language, any driver)",
) -> str:
    """A ``## title`` section (no heading when ``title`` is empty) with one sub-section per snippet."""

    def fence(lang: str, text: str) -> str:
        return f"```{lang}\n{text.rstrip()}\n```\n"

    out: List[str] = [f"## {title}\n", intro + "\n"] if title else []
    options = (
        ("With the pskit client (recommended: only the host port has to be open)", client),
        (host_label, host),
        (direct_label, direct_snip),
    )
    for label, snip in options:
        if not snip:
            continue
        out.append(f"### {label}\n")
        reqs = snip["requirements"]
        if reqs["python"] or reqs["node"]:
            out.append(
                "Install: "
                + (f"`pip install {' '.join(reqs['python'])}`" if reqs["python"] else "")
                + (", " if reqs["python"] and reqs["node"] else "")
                + (f"`npm install {' '.join(reqs['node'])}`" if reqs["node"] else "")
                + "\n"
            )
        if snip.get("note"):
            out.append(snip["note"] + "\n")
        out.append("Python:\n")
        out.append(fence("python", snip["python"]))
        out.append("Node.js (18+):\n")
        out.append(fence("js", snip["node"]))
        if snip.get("cli"):
            out.append("Terminal:\n")
            out.append(fence("bash", "\n".join(snip["cli"])))
    return "\n".join(out)
