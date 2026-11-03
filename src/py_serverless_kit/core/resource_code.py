"""Ready-to-paste Python and Node.js handler code for each resource.

Queues, buckets and topics get a *publish* function and a *consume* function (the
consumer is portable; publishing uses the host on premises and the cloud SDK
elsewhere). Databases, caches and custom services get a connection example for the
client library that matches the service (PostgreSQL, MySQL, MongoDB, Redis,
Memcached, SMTP), detected from a one-click on-prem service or the connection values.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _js(name: str) -> str:
    out = "".join(p.capitalize() for p in name.replace("-", "_").split("_"))
    return out[:1].lower() + out[1:] if out else "res"


def flavor_of(res: Any, service: Optional[str] = None) -> str:
    """postgres | mysql | mongodb | redis | memcached | smtp | generic (for database/cache/custom)."""
    if service in ("postgres", "mysql", "mongodb", "memcached"):
        return service
    if service == "mariadb":
        return "mysql"
    if service in ("redis", "valkey"):
        return "redis"
    if service == "mailpit":
        return "smtp"
    conn = {str(k).lower(): v for k, v in (getattr(res, "connection", None) or {}).items()}
    url = str(conn.get("url") or "").lower()
    for prefix, name in (("postgres", "postgres"), ("mysql", "mysql"), ("mongodb", "mongodb"), ("redis", "redis")):
        if url.startswith(prefix):
            return name
    if "smtp_host" in conn:
        return "smtp"
    port = str(conn.get("port") or "")
    return {"5432": "postgres", "3306": "mysql", "27017": "mongodb", "6379": "redis", "11211": "memcached"}.get(
        port, "generic"
    )


def _secret_py(var: str, key: str) -> str:
    return f'ctx.env[r["{key}"]] if r.get("{key}") else r.get("{var}")'


def _secret_js(var: str, key: str) -> str:
    return f'r.get("{key}") ? process.env[r.get("{key}")] : r.get("{var}")'


# ----------------------------------------------------------------------------- consumers (portable)


def _consume_py(kind: str, key: str) -> str:
    if kind == "storage":
        body = (
            "    for record in event.records:\n"
            f'        ctx.logger.info("{key} object", extra={{"action": record.action, "key": record.key, "size": record.size}})\n'
        )
        return f'\n\ndef on_{key.replace("-", "_")}(event, ctx):\n    """Trigger: storage: {{resource: {key}}}"""\n' + body
    return (
        f'\n\ndef on_{key.replace("-", "_")}(event, ctx):\n'
        f'    """Trigger: {kind}: {{resource: {key}}}. A failed record is retried, then sent to dead_letter."""\n'
        "    result = BatchResult()\n"
        "    for record in event.records:\n"
        "        try:\n"
        f'            ctx.logger.info("{key} message", extra={{"id": record.id, "body": record.json(record.text())}})\n'
        "        except Exception:\n"
        "            result.fail(record)\n"
        "    return result\n"
    )


def _consume_js(kind: str, key: str) -> str:
    name = "on" + _js(key)[:1].upper() + _js(key)[1:]
    if kind == "storage":
        return (
            f"\n\n// Trigger: storage: {{resource: {key}}}\n"
            f"exports.{name} = async (event, ctx) => {{\n"
            "  for (const record of event.records) {\n"
            f'    ctx.logger.info("{key} object", {{ action: record.action, key: record.key, size: record.size }});\n'
            "  }\n"
            "};\n"
        )
    return (
        f"\n\n// Trigger: {kind}: {{resource: {key}}}. A failed record is retried, then sent to dead_letter.\n"
        f"exports.{name} = async (event, ctx) => {{\n"
        "  const result = new BatchResult();\n"
        "  for (const record of event.records) {\n"
        "    try {\n"
        f'      ctx.logger.info("{key} message", {{ id: record.id, body: record.json(record.text()) }});\n'
        "    } catch (err) {\n"
        "      result.fail(record);\n"
        "    }\n"
        "  }\n"
        "  return result;\n"
        "};\n"
    )


# ----------------------------------------------------------------------------- publishers


def _publish(provider: str, kind: str, key: str) -> Dict[str, Any]:
    fn = f"send_to_{key.replace('-', '_')}"
    jfn = "sendTo" + _js(key)[:1].upper() + _js(key)[1:]
    payload_py = "event.http.json() if event.http else event.data"
    payload_js = "event.http ? event.http.json() : event.data"
    req_py: List[str] = []
    req_js: List[str] = []
    if provider == "onprem":
        helper_py = {"queue": "submit_queue", "topic": "submit_topic", "storage": "put_object"}[kind]
        helper_js = {"queue": "submitQueue", "topic": "submitTopic", "storage": "putObject"}[kind]
        imports_py = f"from py_serverless_kit.runtime.onprem_host import {helper_py}\n"
        imports_js = helper_js
        if kind == "storage":
            call_py = (
                f'    {helper_py}(resource("{key}").native_name, "in/hello.txt", b"hello")\n'
                '    return {"written": "in/hello.txt"}\n'
            )
            call_js = f'  await {helper_js}(resource("{key}").nativeName, "in/hello.txt", "hello");\n  return {{ written: "in/hello.txt" }};\n'
        else:
            call_py = f'    message_id = {helper_py}(resource("{key}").native_name, {payload_py})\n    return {{"id": message_id}}\n'
            call_js = f'  const id = await {helper_js}(resource("{key}").nativeName, {payload_js});\n  return {{ id }};\n'
        note = "Goes through the on-prem host, so the resource's driver (built-in, Redis, Kafka, SQS, ...) is used."
    elif provider == "aws":
        req_py, req_js = ["boto3"], {"queue": ["@aws-sdk/client-sqs"], "topic": ["@aws-sdk/client-sns"], "storage": ["@aws-sdk/client-s3"]}[kind]
        if kind == "queue":
            imports_py = "import json\n\nimport boto3\n"
            call_py = f'    r = resource("{key}")\n    out = boto3.client("sqs").send_message(QueueUrl=r.url, MessageBody=json.dumps({payload_py}))\n    return {{"id": out["MessageId"]}}\n'
            imports_js = 'SQSClient, SendMessageCommand'
            call_js = f'  const out = await new SQSClient({{}}).send(new SendMessageCommand({{ QueueUrl: resource("{key}").url, MessageBody: JSON.stringify({payload_js}) }}));\n  return {{ id: out.MessageId }};\n'
        elif kind == "topic":
            imports_py = "import json\n\nimport boto3\n"
            call_py = f'    r = resource("{key}")\n    out = boto3.client("sns").publish(TopicArn=r.arn, Message=json.dumps({payload_py}))\n    return {{"id": out["MessageId"]}}\n'
            imports_js = "SNSClient, PublishCommand"
            call_js = f'  const out = await new SNSClient({{}}).send(new PublishCommand({{ TopicArn: resource("{key}").arn, Message: JSON.stringify({payload_js}) }}));\n  return {{ id: out.MessageId }};\n'
        else:
            imports_py = "import boto3\n"
            call_py = f'    boto3.client("s3").put_object(Bucket=resource("{key}").native_name, Key="in/hello.txt", Body=b"hello")\n    return {{"written": "in/hello.txt"}}\n'
            imports_js = "S3Client, PutObjectCommand"
            call_js = f'  await new S3Client({{}}).send(new PutObjectCommand({{ Bucket: resource("{key}").nativeName, Key: "in/hello.txt", Body: "hello" }}));\n  return {{ written: "in/hello.txt" }};\n'
        note = "The function's IAM role is allowed to use the resources bound to it."
    elif provider == "gcp" and kind in ("queue", "topic"):
        req_py, req_js = ["google-cloud-pubsub"], ["@google-cloud/pubsub"]
        imports_py = "import json\n\nfrom google.cloud import pubsub_v1\n"
        call_py = (
            f'    r = resource("{key}")\n    topic = r.id or pubsub_v1.PublisherClient.topic_path(ctx.env["GOOGLE_CLOUD_PROJECT"], r.native_name)\n'
            f"    future = pubsub_v1.PublisherClient().publish(topic, json.dumps({payload_py}).encode())\n"
            '    return {"id": future.result()}\n'
        )
        imports_js = "PubSub"
        call_js = f'  const r = resource("{key}");\n  const id = await new PubSub().topic(r.id || r.nativeName).publishMessage({{ json: {payload_js} }});\n  return {{ id }};\n'
        note = "Pub/Sub topic; the trigger subscribes to it."
    elif provider == "gcp":
        req_py, req_js = ["google-cloud-storage"], ["@google-cloud/storage"]
        imports_py = "from google.cloud import storage\n"
        call_py = f'    storage.Client().bucket(resource("{key}").native_name).blob("in/hello.txt").upload_from_string("hello")\n    return {{"written": "in/hello.txt"}}\n'
        imports_js = "Storage"
        call_js = f'  await new Storage().bucket(resource("{key}").nativeName).file("in/hello.txt").save("hello");\n  return {{ written: "in/hello.txt" }};\n'
        note = ""
    elif provider == "azure":
        conn_py = 'ctx.env["AzureWebJobsStorage"]'
        conn_js = "process.env.AzureWebJobsStorage"
        if kind == "queue":
            req_py, req_js = ["azure-storage-queue"], ["@azure/storage-queue"]
            imports_py = "import json\n\nfrom azure.storage.queue import QueueClient\n"
            call_py = f'    q = QueueClient.from_connection_string({conn_py}, resource("{key}").native_name)\n    out = q.send_message(json.dumps({payload_py}))\n    return {{"id": out.id}}\n'
            imports_js = "QueueServiceClient"
            call_js = f'  const q = QueueServiceClient.fromConnectionString({conn_js}).getQueueClient(resource("{key}").nativeName);\n  const out = await q.sendMessage(Buffer.from(JSON.stringify({payload_js})).toString("base64"));\n  return {{ id: out.messageId }};\n'
        elif kind == "topic":
            req_py, req_js = ["azure-servicebus"], ["@azure/service-bus"]
            imports_py = "import json\n\nfrom azure.servicebus import ServiceBusClient, ServiceBusMessage\n"
            call_py = f'    with ServiceBusClient.from_connection_string(ctx.env["SERVICEBUS_CONNECTION"]) as sb:\n        sb.get_topic_sender(resource("{key}").native_name).send_messages(ServiceBusMessage(json.dumps({payload_py})))\n    return {{"sent": True}}\n'
            imports_js = "ServiceBusClient"
            call_js = f'  const sb = new ServiceBusClient(process.env.SERVICEBUS_CONNECTION);\n  await sb.createSender(resource("{key}").nativeName).sendMessages({{ body: {payload_js} }});\n  await sb.close();\n  return {{ sent: true }};\n'
        else:
            req_py, req_js = ["azure-storage-blob"], ["@azure/storage-blob"]
            imports_py = "from azure.storage.blob import BlobServiceClient\n"
            call_py = f'    blob = BlobServiceClient.from_connection_string({conn_py}).get_blob_client(resource("{key}").native_name, "in/hello.txt")\n    blob.upload_blob(b"hello", overwrite=True)\n    return {{"written": "in/hello.txt"}}\n'
            imports_js = "BlobServiceClient"
            call_js = f'  const c = BlobServiceClient.fromConnectionString({conn_js}).getContainerClient(resource("{key}").nativeName);\n  await c.getBlockBlobClient("in/hello.txt").upload("hello", 5);\n  return {{ written: "in/hello.txt" }};\n'
        note = "Uses the Function App's storage connection (AzureWebJobsStorage) or a Service Bus setting you add."
    else:
        imports_py = ""
        call_py = f'    r = resource("{key}")\n    # Publish with your cloud\'s SDK using r.native_name and r.connection\n    return {{"name": r.native_name, "connection": r.connection}}\n'
        imports_js = ""
        call_js = f'  const r = resource("{key}");\n  // Publish with your cloud\'s SDK using r.nativeName and r.connection\n  return {{ name: r.nativeName, connection: r.connection }};\n'
        note = f"pskit has no portable publish call on {provider}; the consumer below works as is."
    head_py = f"from py_serverless_kit import BatchResult, resource\n{imports_py}"
    if provider in ("onprem",) or provider not in ("aws", "gcp", "azure"):
        pkg_js = f"const {{ BatchResult, resource{', ' + imports_js if imports_js else ''} }} = require(\"pskit\");\n"
    else:
        sdk = req_js[0]
        pkg_js = f'const {{ BatchResult, resource }} = require("pskit");\nconst {{ {imports_js} }} = require("{sdk}");\n'
    python = head_py + f'\n\ndef {fn}(event, ctx):\n    """Publish to {key}."""\n' + call_py + _consume_py(kind, key)
    node = pkg_js + f"\n// Publish to {key}.\nexports.{jfn} = async (event, ctx) => {{\n" + call_js + "};" + _consume_js(kind, key)
    return {"python": python, "node": node, "requirements": {"python": req_py, "node": req_js}, "note": note}


# ----------------------------------------------------------------------------- connections


def _connect(kind: str, key: str, flavor: str) -> Dict[str, Any]:
    fn = f"check_{key.replace('-', '_')}"
    jfn = "check" + _js(key)[:1].upper() + _js(key)[1:]
    url_py = _secret_py("url", "url_env")
    url_js = _secret_js("url", "url_env")
    pw_py = _secret_py("password", "password_env")
    pw_js = _secret_js("password", "password_env")
    req_py: List[str] = []
    req_js: List[str] = []
    if flavor == "postgres":
        req_py, req_js = ["psycopg[binary]"], ["pg"]
        py = (
            "import psycopg\n\nfrom py_serverless_kit import resource\n\n\n"
            f"def {fn}(event, ctx):\n"
            f'    r = resource("{key}")\n'
            f"    url = {url_py}\n"
            "    with psycopg.connect(url) if url else psycopg.connect(\n"
            f'        host=r["host"], port=r.get("port", 5432), dbname=r.get("database"), user=r.get("user"), password={pw_py}\n'
            "    ) as conn:\n"
            '        return {"version": conn.execute("select version()").fetchone()[0]}\n'
        )
        js = (
            'const { Client } = require("pg");\nconst { resource } = require("pskit");\n\n'
            f"exports.{jfn} = async (event, ctx) => {{\n"
            f'  const r = resource("{key}");\n'
            f"  const url = {url_js};\n"
            f'  const client = new Client(url ? {{ connectionString: url }} : {{ host: r.get("host"), port: Number(r.get("port", 5432)), database: r.get("database"), user: r.get("user"), password: {pw_js} }});\n'
            "  await client.connect();\n"
            '  try { return { version: (await client.query("select version()")).rows[0].version }; } finally { await client.end(); }\n'
            "};\n"
        )
    elif flavor == "mysql":
        req_py, req_js = ["pymysql"], ["mysql2"]
        py = (
            "import pymysql\n\nfrom py_serverless_kit import resource\n\n\n"
            f"def {fn}(event, ctx):\n"
            f'    r = resource("{key}")\n'
            "    conn = pymysql.connect(\n"
            f'        host=r["host"], port=int(r.get("port", 3306)), user=r.get("user"), password={pw_py}, database=r.get("database")\n'
            "    )\n"
            "    with conn, conn.cursor() as cur:\n"
            '        cur.execute("select version()")\n'
            '        return {"version": cur.fetchone()[0]}\n'
        )
        js = (
            'const mysql = require("mysql2/promise");\nconst { resource } = require("pskit");\n\n'
            f"exports.{jfn} = async (event, ctx) => {{\n"
            f'  const r = resource("{key}");\n'
            f'  const conn = await mysql.createConnection({{ host: r.get("host"), port: Number(r.get("port", 3306)), user: r.get("user"), password: {pw_js}, database: r.get("database") }});\n'
            '  try { const [rows] = await conn.query("select version() as v"); return { version: rows[0].v }; } finally { await conn.end(); }\n'
            "};\n"
        )
    elif flavor == "mongodb":
        req_py, req_js = ["pymongo"], ["mongodb"]
        py = (
            "from pymongo import MongoClient\n\nfrom py_serverless_kit import resource\n\n\n"
            f"def {fn}(event, ctx):\n"
            f'    r = resource("{key}")\n'
            f'    client = MongoClient({url_py} or f"mongodb://{{r[\'host\']}}:{{r.get(\'port\', 27017)}}")\n'
            "    try:\n"
            '        return {"ok": client.admin.command("ping")["ok"], "databases": client.list_database_names()}\n'
            "    finally:\n"
            "        client.close()\n"
        )
        js = (
            'const { MongoClient } = require("mongodb");\nconst { resource } = require("pskit");\n\n'
            f"exports.{jfn} = async (event, ctx) => {{\n"
            f'  const r = resource("{key}");\n'
            f'  const client = new MongoClient({url_js} || `mongodb://${{r.get("host")}}:${{r.get("port", 27017)}}`);\n'
            "  await client.connect();\n"
            '  try { return { ok: (await client.db("admin").command({ ping: 1 })).ok }; } finally { await client.close(); }\n'
            "};\n"
        )
    elif flavor == "redis":
        req_py, req_js = ["redis"], ["ioredis"]
        py = (
            "import redis\n\nfrom py_serverless_kit import resource\n\n\n"
            f"def {fn}(event, ctx):\n"
            f'    r = resource("{key}")\n'
            f"    url = {url_py}\n"
            f'    client = redis.from_url(url) if url else redis.Redis(host=r["host"], port=int(r.get("port", 6379)), password={pw_py})\n'
            f'    client.set("pskit:{key}:hello", "world", ex=60)\n'
            f'    return {{"ping": client.ping(), "value": client.get("pskit:{key}:hello").decode()}}\n'
        )
        js = (
            'const Redis = require("ioredis");\nconst { resource } = require("pskit");\n\n'
            f"exports.{jfn} = async (event, ctx) => {{\n"
            f'  const r = resource("{key}");\n'
            f"  const url = {url_js};\n"
            f'  const client = url ? new Redis(url) : new Redis({{ host: r.get("host"), port: Number(r.get("port", 6379)), password: {pw_js} }});\n'
            f'  try {{ await client.set("pskit:{key}:hello", "world", "EX", 60); return {{ ping: await client.ping(), value: await client.get("pskit:{key}:hello") }}; }} finally {{ client.disconnect(); }}\n'
            "};\n"
        )
    elif flavor == "memcached":
        req_py, req_js = ["pymemcache"], ["memjs"]
        py = (
            "from pymemcache.client.base import Client\n\nfrom py_serverless_kit import resource\n\n\n"
            f"def {fn}(event, ctx):\n"
            f'    r = resource("{key}")\n'
            '    client = Client((r["host"], int(r.get("port", 11211))))\n'
            '    client.set("pskit-hello", "world", expire=60)\n'
            '    return {"value": client.get("pskit-hello").decode()}\n'
        )
        js = (
            'const memjs = require("memjs");\nconst { resource } = require("pskit");\n\n'
            f"exports.{jfn} = async (event, ctx) => {{\n"
            f'  const r = resource("{key}");\n'
            '  const client = memjs.Client.create(`${r.get("host")}:${r.get("port", 11211)}`);\n'
            '  await client.set("pskit-hello", "world", { expires: 60 });\n'
            '  const { value } = await client.get("pskit-hello");\n  client.close();\n  return { value: value.toString() };\n'
            "};\n"
        )
    elif flavor == "smtp":
        req_js = ["nodemailer"]
        py = (
            "import smtplib\nfrom email.message import EmailMessage\n\nfrom py_serverless_kit import resource\n\n\n"
            f"def {fn}(event, ctx):\n"
            f'    r = resource("{key}")\n'
            '    msg = EmailMessage()\n    msg["From"], msg["To"], msg["Subject"] = "app@example.com", "you@example.com", "Hello from pskit"\n'
            '    msg.set_content("It works.")\n'
            '    with smtplib.SMTP(r.get("smtp_host") or r["host"], int(r.get("smtp_port") or r.get("port", 25))) as smtp:\n'
            "        smtp.send_message(msg)\n"
            '    return {"sent": True}\n'
        )
        js = (
            'const nodemailer = require("nodemailer");\nconst { resource } = require("pskit");\n\n'
            f"exports.{jfn} = async (event, ctx) => {{\n"
            f'  const r = resource("{key}");\n'
            '  const t = nodemailer.createTransport({ host: r.get("smtp_host") || r.get("host"), port: Number(r.get("smtp_port") || r.get("port", 25)) });\n'
            '  await t.sendMail({ from: "app@example.com", to: "you@example.com", subject: "Hello from pskit", text: "It works." });\n'
            "  return { sent: true };\n"
            "};\n"
        )
    else:
        py = (
            "from py_serverless_kit import resource\n\n\n"
            f"def {fn}(event, ctx):\n"
            f'    r = resource("{key}")\n'
            "    # Secrets: a `<name>_env` value is the NAME of a variable; read it with ctx.env[...]\n"
            '    secrets = {k[:-4]: ctx.env.get(v) is not None for k, v in r.connection.items() if k.endswith("_env")}\n'
            '    return {"name": r.native_name, "connection": r.connection, "secrets_set": secrets}\n'
        )
        js = (
            'const { resource } = require("pskit");\n\n'
            f"exports.{jfn} = async (event, ctx) => {{\n"
            f'  const r = resource("{key}");\n'
            "  // Secrets: a `<name>_env` value is the NAME of a variable; read it with process.env[...]\n"
            "  const secretsSet = Object.fromEntries(Object.entries(r.connection).filter(([k]) => k.endsWith(\"_env\")).map(([k, v]) => [k.slice(0, -4), v in process.env]));\n"
            "  return { name: r.nativeName, connection: r.connection, secretsSet };\n"
            "};\n"
        )
    return {
        "python": py,
        "node": js,
        "requirements": {"python": req_py, "node": req_js},
        "note": f"Connects with the values pskit passes to bound functions ({flavor} client).",
    }


def code_for(provider: str, key: str, res: Any, service: Optional[str] = None) -> Dict[str, Any]:
    """``{"flavor", "python", "node", "requirements": {"python", "node"}, "note"}`` for resource ``key``."""
    kind = str(getattr(res, "type", "") or "")
    if kind in ("queue", "storage", "topic"):
        out = _publish(provider, kind, key)
        out["flavor"] = kind
    else:
        flavor = flavor_of(res, service)
        out = _connect(kind, key, flavor)
        out["flavor"] = flavor
    return out
