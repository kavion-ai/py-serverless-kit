"""Category A (docs Q&A and how-to), batch 4: resources and resource guides on every cloud, secrets, invoke(),
the pskit client, AWS compatibility on premises, Node.js. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(61, provider="aws", stage="dev", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resource-guides/aws/custom.md#other-aws-services-type-custom", "docs/resource-guides/aws/custom.md#dynamodb"],
      user="My Lambdas read and write an existing DynamoDB table called orders. How do I give the pskit function access to it?",
      steps=[S("search_docs", query="existing dynamodb table resource permissions",
               docs=[D("docs/resource-guides/aws/custom.md", "other-aws-services-type-custom", end="for console-created ones, paste the ARN."),
                     D("docs/resource-guides/aws/custom.md", "dynamodb", start="```yaml", words=200)])],
      final="""Declare the table as a `custom` resource with `external: true`, and grant the IAM actions yourself. pskit grants **no IAM permissions** for `custom` resources [docs/resource-guides/aws/custom.md#other-aws-services-type-custom].

**In code**
```yaml
provider:
  name: aws
  region: eu-west-1
  iam:
    statements:
      - actions: [dynamodb:GetItem, dynamodb:PutItem, dynamodb:UpdateItem, dynamodb:Query]
        resources: ["arn:aws:dynamodb:eu-west-1:123456789012:table/orders"]
resources:
  orders-table:
    type: custom
    external: true
    name: orders
    connection:
      arn: arn:aws:dynamodb:eu-west-1:123456789012:table/orders
```
Use your table's real ARN.
```python
import boto3
from py_serverless_kit import resource

table = boto3.resource("dynamodb").Table(resource("orders-table").native_name)
```
[docs/resource-guides/aws/custom.md#dynamodb]

**In studio**
1. Open **Resources** and click **+ Add resource**.
2. Set *Key* `orders-table`, *Type* custom, choose *External / existing*, enter *Native name* `orders`, and add `arn` under *Connection*.
3. Click **Save**, then add the IAM statement under the function's *Permissions (IAM)* section.

Add `boto3` to `requirements.txt`."""),

    A(62, provider="gcp", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resource-guides/gcp/database.md#3-declare-it-in-pskityml", "docs/resource-guides/gcp/database.md#4-use-it-in-a-handler"],
      user="how my function talks to my cloud sql postgres?",
      steps=[S("search_docs", query="gcp cloud sql database resource handler",
               docs=[D("docs/resource-guides/gcp/database.md", "3-declare-it-in-pskityml", words=200),
                     D("docs/resource-guides/gcp/database.md", "4-use-it-in-a-handler", words=200)])],
      final="""Declare the instance as an external `database` resource, and connect with the Cloud SQL Python connector.

**In code**
1. pskit.yml [docs/resource-guides/gcp/database.md#3-declare-it-in-pskityml]:
```yaml
provider:
  name: gcp
  options:
    project: my-project
  environment:
    ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}
resources:
  orders-db:
    type: database
    external: true
    connection:
      instance: my-project:europe-west1:orders-pg
      database: orders
      user: pskitapp
      password_env: ORDERS_DB_PASSWORD
    functions: [api]
```
2. Add `cloud-sql-python-connector[pg8000]` to `requirements.txt`.
3. In the handler, `resource("orders-db")` gives you the connection values. Read the password with `ctx.env[db["password_env"]]` and pass everything to `Connector().connect(...)` [docs/resource-guides/gcp/database.md#4-use-it-in-a-handler].

**In studio**
1. Open **Resources** and click **+ Add resource**, with *Type* database.
2. Fill in *Connection*. For the password, enter the variable name, never the password itself.
3. Under *Bound functions*, pick the functions that use it, then click **Save**.

The runtime service account also needs the **Cloud SQL Client** role. The password still reaches Terraform state through `${env:...}`. Secret Manager avoids that."""),

    A(63, provider="azure", stage="staging", mode="auto", page="Code", persona="detailed_spec",
      sources=["docs/resource-guides/azure/cache.md#3-declare-it-in-pskityml", "docs/resource-guides/azure/cache.md#4-use-it-in-a-handler"],
      user="We added Azure Cache for Redis as a resource with ssl: true in connection, but in the handler `c['ssl'] is True` is never true and the connection resets. What's going on?",
      steps=[S("search_docs", query="azure redis cache ssl connection boolean handler",
               docs=[D("docs/resource-guides/azure/cache.md", "4-use-it-in-a-handler")]),
             S("search_docs", query="azure redis connection reset tls port",
               docs=[D("docs/resource-guides/azure/cache.md", "troubleshooting")])],
      final="""Connection values reach the function as environment variables, so booleans arrive as the strings `"true"` / `"false"`. `c["ssl"] is True` is therefore always false. Your client then connects without TLS, and Azure resets the connection [docs/resource-guides/azure/cache.md#4-use-it-in-a-handler].

**In code**
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
        _client = redis.Redis(host=c["host"], port=int(c["port"]), ssl=c.get("ssl") == "true", password=pw)
    return {"hits": _client.incr("hits")}
```
`port` is a string too, so keep the `int(...)`.

Also check that you use the TLS port: 6380 for Azure Cache for Redis, 10000 for Azure Managed Redis. Make sure **Networking** allows access [docs/resource-guides/azure/cache.md#troubleshooting]."""),

    A(64, provider="cloudflare", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resource-guides/cloudflare/topic.md#topics-on-cloudflare-type-topic", "docs/resource-guides/cloudflare/topic.md#what-to-use-instead"],
      user="i need pub sub topic on cloudflare, 3 workers get same message. pskit do it?",
      steps=[S("search_docs", query="cloudflare topic pub sub fan out",
               docs=[D("docs/resource-guides/cloudflare/topic.md", "topics-on-cloudflare-type-topic", end="resource is rejected too."),
                     D("docs/resource-guides/cloudflare/topic.md", "what-to-use-instead")])],
      final="""No. Cloudflare has no pub/sub topic service that pskit can use, and there's no `topic` trigger on Cloudflare. A `topic:` event or a managed `type: topic` resource fails validation [docs/resource-guides/cloudflare/topic.md#topics-on-cloudflare-type-topic].

What you can do instead [docs/resource-guides/cloudflare/topic.md#what-to-use-instead]:
1. **One queue per consumer**: the producer sends the message to each of the 3 queues.
2. **Call the workers over HTTP**: each one has its own `workers.dev` URL or route (`pskit info`).
3. **Use a topic in another cloud**: declare it as `type: topic` with `external: true`, and publish with that cloud's HTTP API through `from js import fetch`. Python Workers have no SDKs.
4. **Run the consumers where topics exist**: aws (SNS), gcp (Pub/Sub), azure (Service Bus) or onprem."""),

    A(65, provider="digitalocean", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/resource-guides/digitalocean/queue.md#queues-on-digitalocean-type-queue"],
      user="DO: background job queue options? no queue trigger, right?",
      steps=[S("search_docs", query="digitalocean queue alternative valkey",
               docs=[D("docs/resource-guides/digitalocean/queue.md", "queues-on-digitalocean-type-queue", end="on the same Valkey list |")]),
             S("search_docs", query="digitalocean valkey queue pskit.yml worker schedule",
               docs=[D("docs/resource-guides/digitalocean/queue.md", "3-declare-it-in-pskityml", words=200)])],
      final="""Right. DigitalOcean has no managed queue service, and pskit has no `queue` trigger there [docs/resource-guides/digitalocean/queue.md#queues-on-digitalocean-type-queue]. Your options:
- **Managed Valkey list**: producers `LPUSH`, and a `schedule` function pops a batch every minute.
- **Managed Kafka**: a durable stream with many consumers.
- **On-prem host** with `driver: redis` on the same Valkey list, if messages must be handled the moment they arrive.

**In code** (Valkey list)
```yaml
provider:
  name: digitalocean
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE}
  environment:
    JOBS_REDIS_URL: ${env:JOBS_REDIS_URL}
resources:
  jobs:
    type: queue
    external: true
    name: orders:jobs
    connection:
      url_env: JOBS_REDIS_URL
functions:
  submit:
    handler: app.handlers.submit
    events: [{http: POST /jobs}]
  worker:
    handler: app.handlers.work
    events: [{schedule: 1 minute}]
```
TLS is required (`rediss://`). Keep the URL in the environment, because it contains the password."""),

    A(66, provider="oracle", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resource-guides/oracle/storage.md#3-policies", "docs/resource-guides/oracle/storage.md#4-declare-it-in-pskityml"],
      user="We deployed a storage-triggered function on OCI. The bucket exists, the deploy succeeded, but uploads never run the function. We also set prefix: incoming/. What are we missing?",
      steps=[S("search_docs", query="oci object storage trigger not firing policies",
               docs=[D("docs/resource-guides/oracle/storage.md", "3-policies")]),
             S("search_docs", query="oci storage prefix suffix events rule",
               docs=[D("docs/resource-guides/oracle/storage.md", "4-declare-it-in-pskityml", start="- pskit creates only an `oci_events_rule`")])],
      final="""Check two things.

1. **Policies.** The Events service must be allowed to invoke functions, and the functions need a dynamic-group policy to read and write objects [docs/resource-guides/oracle/storage.md#3-policies]:
```text
Allow service cloudEvents to use functions-family in compartment <name>
Allow dynamic-group pskit-functions to manage objects in compartment <name> where target.bucket.name = 'invoices'
```
Also make sure the bucket emits object events.

2. **The prefix isn't applied by OCI.** OCI Events rules can't filter by `prefix` / `suffix`. pskit warns about it, and you filter in the handler [docs/resource-guides/oracle/storage.md#4-declare-it-in-pskityml]:
```python
from __future__ import annotations


def on_invoice(event, ctx):
    for rec in event.records:
        if not rec.key.startswith("incoming/"):
            continue
        ctx.logger.info("new object", extra={"key": rec.key})
```

pskit creates only the `oci_events_rule` for an external bucket. It doesn't create the bucket or the policies."""),

    A(67, provider="huawei", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resource-guides/huawei/storage.md#3-declare-it-in-pskityml", "docs/resource-guides/huawei/storage.md#troubleshooting"],
      user="huawei: run function only when pdf come in incoming/ folder of my OBS bucket. how?",
      steps=[S("search_docs", query="huawei obs storage trigger prefix suffix",
               docs=[D("docs/resource-guides/huawei/storage.md", "3-declare-it-in-pskityml")])],
      final="""Use a storage trigger with `prefix` and `suffix`. On Huawei, OBS applies them itself [docs/resource-guides/huawei/storage.md#3-declare-it-in-pskityml].

**In code**
```yaml
provider:
  name: huawei
  region: cn-north-4
  iam:
    role: pskit-functions
resources:
  invoices:
    type: storage
    external: true
    name: acme-invoices
functions:
  on-invoice:
    handler: app.handlers.on_invoice
    events:
      - storage: {resource: invoices, prefix: incoming/, suffix: .pdf, events: [created]}
```
`iam.role` is an IAM agency with OBS permissions. Without it, the handler gets `AccessDenied`.

**In studio**
1. Open **Functions** and click the function.
2. Under *Add a trigger*, add a storage trigger and pick the resource `invoices`.
3. Set the prefix `incoming/` and the suffix `.pdf`, then click **Save**.

**In the terminal**
```bash
pskit validate -p huawei
pskit invoke -f on-invoice -t storage
```
With `external: true`, pskit creates only the OBS trigger, not the bucket."""),

    A(68, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resource-guides/onprem/secrets.md#secret-managers-on-premises",
               "docs/resource-guides/onprem/secrets.md#one-click-openbao-pskits-secrets-manager-or-localstack"],
      user="i dont want passwords in files on my server. is there a safe place for secrets?",
      steps=[S("search_docs", query="secret manager on premises get_secret",
               docs=[D("docs/resource-guides/onprem/secrets.md", "secret-managers-on-premises", end="cached for 60 seconds per function instance.", words=300)])],
      final="""Yes. Start a secret manager with one click, and read secrets in your handler with `get_secret()`. The same call works on every provider, and it needs no extra library [docs/resource-guides/onprem/secrets.md#secret-managers-on-premises].

**In studio**
1. Open **Resources > On-prem services**, click **+ Create service** and choose *Secret managers*.
2. Pick OpenBao and name it `secrets`. With that name, handlers don't need `store=`.

**In the terminal**
```bash
pskit resources onprem create secrets --service openbao --save
```
Add `--server app-1` to run it on a saved server instead of this machine.

**In code**
```python
from __future__ import annotations

from py_serverless_kit import get_secret


def handler(event, ctx):
    db_pass = get_secret("db-password")
    webhook = get_secret("stripe", "webhook")
    return {"ok": bool(db_pass and webhook)}
```
Values are cached for 60 seconds. Creating the service writes its connection to `.env.onprem`, which the host loads. Protect that file and the data volume, because they hold the OpenBao token and unseal key."""),

    A(69, provider="aws", stage="prod", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#get_secret-secrets-on-every-provider"],
      user="code only: get_secret against AWS Secrets Manager on lambda, how is the store picked?",
      steps=[S("search_docs", query="get_secret driver aws secrets manager",
               docs=[D("docs/handlers.md", "get_secret-secrets-on-every-provider")])],
      final="""**In code**
The store comes from environment variables, so the handler doesn't change. Set the variable `PSKIT_SECRETS_DRIVER` to `aws`, and it reads AWS Secrets Manager with the Lambda's credentials [docs/handlers.md#get_secret-secrets-on-every-provider].
```yaml
provider:
  name: aws
  environment:
    PSKIT_SECRETS_DRIVER: aws
```
The function's role also needs the Secrets Manager `GetSecretValue` action on your secret's ARN, under `provider.iam.statements`.
```python
from __future__ import annotations

from py_serverless_kit import get_secret


def api(event, ctx):
    key = get_secret("orders/stripe", "key")
    extra = get_secret("optional-token", default="")
    return {"configured": bool(key), "extra": bool(extra)}
```
Without the variable, the driver is `env` (`PSKIT_SECRET_<NAME>`, then `<NAME>`). Values are cached for 60 s."""),

    A(70, provider="tencent", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      user="Our order function calls invoke(\"billing\", ...). It works locally, but on Tencent it raises InvokeError. Is invoke() not supported there?",
      steps=[S("search_docs", query="invoke another function InvokeError provider",
               docs=[D("docs/handlers.md", "invoke-calling-another-function")])],
      final="""Not directly. `invoke()` finds the target natively only locally, on premises, on AWS and on GCP. Other providers, Tencent included, raise `InvokeError` unless `PSKIT_ENDPOINT_<NAME>` is set. Locally it works because the call runs in-process [docs/handlers.md#invoke-calling-another-function].

Fix: give billing an HTTP route and point the variable at its URL.

**In code**
```yaml
functions:
  billing:
    handler: app.billing.handler
    events: [{http: POST /billing}]
  orders:
    handler: app.orders.handler
    environment:
      PSKIT_ENDPOINT_BILLING: ${env:BILLING_URL}
```
`invoke("billing", data)` then POSTs to that URL. The handler code stays the same.

**In the terminal**
1. Deploy once and copy billing's URL:
```bash
pskit info -p tencent
```
2. Set `BILLING_URL` to that URL and deploy again.

The billing route is public with `auth: none`, so check a shared token in the billing handler."""),

    A(71, provider="onprem", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/client.md#call-an-on-prem-host-from-any-program-pskit-client-and-http-api", "docs/client.md#python"],
      user="A cron script on another machine has to drop jobs into our on-prem `jobs` queue. The queue is Redis-backed, and the Redis port is firewalled. Can the script still do it?",
      steps=[S("search_docs", query="send to on-prem queue from another program",
               docs=[D("docs/client.md", "call-an-on-prem-host-from-any-program-pskit-client-and-http-api", end="That is the usual fix for scripts that time out connecting to a service directly.")]),
             S("search_docs", query="pskit client python queue send",
               docs=[D("docs/client.md", "python", words=40)])],
      final="""Yes. Send through the deployed pskit host. Only the host's port (default 8080) must be reachable, and the Redis port can stay closed [docs/client.md#call-an-on-prem-host-from-any-program-pskit-client-and-http-api].

**In code**
```python
from __future__ import annotations

from py_serverless_kit.client import PskitClient

client = PskitClient("http://192.0.2.10:8080")   # the token comes from PSKIT_ADMIN_TOKEN
jobs = client.queue("jobs")
jobs.send({"order_id": 1}, attributes={"kind": "nightly"})
print(jobs.depth())
```
The client uses only the standard library, so `pip install py-serverless-kit` on that machine is enough [docs/client.md#python]. Without `token=`, the client reads `PSKIT_ADMIN_TOKEN` from the environment, so the token stays out of the script.

**In the terminal**
```bash
pskit client info
```
Run it in the project to see the host's endpoint, whether it's reachable from this machine, and sample code for each resource."""),

    A(72, provider="onprem", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/resource-guides/compatibility.md#existing-sqs-code-on-premises"],
      user="We have lots of boto3 code doing sqs.send_message. If we move these functions on-prem, do we have to rewrite it?",
      steps=[S("search_docs", query="existing boto3 sqs code on premises",
               docs=[D("docs/resource-guides/compatibility.md", "existing-sqs-code-on-premises")])],
      final="""Mostly no. The on-prem host serves the SQS API (JSON protocol) for its queues: `SendMessage`, `ReceiveMessage` with long polling, `DeleteMessage`, `GetQueueUrl` and more. Inside functions, `resource("jobs").url` is the queue URL, as on AWS [docs/resource-guides/compatibility.md#existing-sqs-code-on-premises].

**In code**
You only change how the client is created:
```python
from __future__ import annotations

import os

import boto3
from py_serverless_kit import resource

HOST_KEYS = {"aws_access_key_id": "pskit", "aws_secret_access_key": "pskit"}
sqs = boto3.client("sqs", endpoint_url=os.environ["PSKIT_ENDPOINT"], region_name="us-east-1", **HOST_KEYS)


def api(event, ctx):
    sqs.send_message(QueueUrl=resource("jobs").url, MessageBody=event.http.text())
    return {"queued": True}
```
The `send_message` line stays the same as on AWS.

Limits: sending works for every queue driver. Receiving through this API needs a built-in queue. Driver-backed queues are consumed by pskit triggers or the service's own client."""),

    A(73, provider="onprem", stage="dev", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resource-guides/compatibility.md#not-compatible-and-what-to-use", "docs/resource-guides/onprem/storage.md#pskits-amazon-s3-compatible-server-one-click"],
      user="does the on-prem host speak the S3 API too, so boto3 s3 just works?",
      steps=[S("search_docs", query="S3 API on premises host boto3",
               docs=[D("docs/resource-guides/compatibility.md", "not-compatible-and-what-to-use")]),
             S("search_docs", query="on-prem s3 compatible storage one click",
               docs=[D("docs/resource-guides/onprem/storage.md", "pskits-amazon-s3-compatible-server-one-click", end="`_SECRET_KEY` for any other program:", words=300)])],
      final="""No. The host doesn't serve the S3 API. Use an S3-compatible store (RustFS, MinIO or LocalStack), or the pskit client for built-in buckets [docs/resource-guides/compatibility.md#not-compatible-and-what-to-use].

For S3 code, use pskit's own Amazon S3 compatible server. It checks every request's signature (SigV4), and storage triggers work on it [docs/resource-guides/onprem/storage.md#pskits-amazon-s3-compatible-server-one-click].

**In studio**
1. Open **Resources > On-prem services** and click **+ Create service**.
2. Choose *Object storage*, then *Amazon S3 compatible*.

**In the terminal**
```bash
pskit resources onprem create files --service s3 --save
```

**In code**
The env file gets `PSKIT_FILES_URL`, `PSKIT_FILES_ACCESS_KEY` and `PSKIT_FILES_SECRET_KEY`. Pass them to boto3 as `endpoint_url` and the keys, and use path-style addressing. Your other S3 calls stay the same."""),

    A(74, provider="aws", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/nodejs.md#nodejs-and-typescript", "docs/nodejs.md#typescript"],
      user="can i write my functions in typescript instead of python?",
      steps=[S("search_docs", query="typescript handlers node",
               docs=[D("docs/nodejs.md", "nodejs-and-typescript", end="cd my-api && pskit dev"),
                     D("docs/nodejs.md", "typescript", end="* Type errors fail the build, with the compiler output in the error.")])],
      final="""Yes. Handlers can be JavaScript or TypeScript. The YAML, triggers, local tools and deploy commands stay the same; only `provider.runtime` changes [docs/nodejs.md#nodejs-and-typescript]. pskit compiles `.ts` files with `tsc` for you, and type errors fail the build [docs/nodejs.md#typescript].

**In the terminal**
```bash
pskit init my-api -p aws --typescript
cd my-api
pskit dev
```

**In code**
```yaml
provider:
  name: aws
  runtime: nodejs20
```

A service is either Python or Node.js. Every function uses the provider's language. Node.js 18+ and npm must be installed where you package."""),

    A(75, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/nodejs.md#limitations", "docs/nodejs.md#choosing-the-runtime"],
      user="one function python, other one node.js, same pskit.yml ok?",
      steps=[S("search_docs", query="mix python and nodejs functions one service",
               docs=[D("docs/nodejs.md", "limitations"),
                     D("docs/nodejs.md", "choosing-the-runtime", start="A service is either Python or Node.js", end="runs for you.")])],
      final="""No. A service is either Python or Node.js, and every function uses the provider's language [docs/nodejs.md#choosing-the-runtime]. A function can only pin another **Node.js** version with `functions.<name>.runtime`.

What to do: split them into two services, e.g. two folders, each with its own pskit.yml. They can call each other over HTTP or a queue [docs/nodejs.md#limitations].

```yaml
# api-py/pskit.yml
service: orders-py
provider: {name: gcp, runtime: python3.12, options: {project: my-project}}
```
```yaml
# api-node/pskit.yml
service: orders-node
provider: {name: gcp, runtime: nodejs20, options: {project: my-project}}
```"""),

    A(76, provider="azure", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/resources.md#fields"],
      user="yaml only: bind the uploads storage resource to the api function only, not to all of them",
      steps=[S("search_docs", query="resource functions binding list",
               docs=[D("docs/resources.md", "fields", end="Resource keys follow function-name rules")])],
      final="""**In code**
```yaml
resources:
  uploads:
    type: storage
    functions: [api]
```
Without `functions:`, every function you wrote gets the binding [docs/resources.md#fields]. Note that on Azure the app settings belong to the whole Function App, so every function there still sees every binding."""),

    A(77, provider="ibm", stage="dev", mode="auto", page="Code", persona="beginner",
      sources=["docs/resources.md#what-handlers-receive", "docs/resources.md#runtime-api"],
      user="i added a database resource with host and port in connection. how do i read those values in my python code?",
      steps=[S("search_docs", query="read resource connection values in handler",
               docs=[D("docs/resources.md", "runtime-api", words=60)]),
             S("search_docs", query="PSKIT_RESOURCE environment variables",
               docs=[D("docs/resources.md", "what-handlers-receive", end="`<KEY>` is the key with every non-alphanumeric character replaced by `_`")])],
      final="""Use `resource("<key>")`. It returns the connection values with lower-case keys [docs/resources.md#runtime-api].

**In code**
```python
from __future__ import annotations

from py_serverless_kit import resource


def api(event, ctx):
    db = resource("orders-db")
    host = db["host"]
    port = int(db.get("port", "5432"))
    return {"host": host, "port": port}
```
- `db.get("name", default)` doesn't fail when a key is missing. `db["name"]` raises `KeyError`.
- Values are strings, so convert numbers yourself.
- The same values are also environment variables, such as `PSKIT_RESOURCE_ORDERS_DB_HOST` [docs/resources.md#what-handlers-receive].

For the password, put only a variable name in `connection` (`password_env: ORDERS_DB_PASSWORD`) and read it with `ctx.env[db["password_env"]]`."""),

    A(78, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#examples", "docs/resources.md#on-premises-drivers"],
      user="Our on-prem worker should consume an SQS queue that lives in AWS eu-west-1, while the same project still deploys to AWS too. How do I point just the on-prem deployment at that queue, without writing the keys into the config file?",
      steps=[S("search_docs", query="on premises driver sqs queue in AWS",
               docs=[D("docs/resources.md", "examples", words=80)]),
             S("search_docs", query="driver secret env name_env host environment",
               docs=[D("docs/resources.md", "on-premises-drivers", start="**Secrets.**", end="*is* written into the files.")])],
      final="""Override the resource only for on-prem in `providers.onprem`, and give it the `sqs` driver. The host then polls and leases the queue and runs the function for each message [docs/resources.md#examples].

**In code**
```yaml
providers:
  onprem:
    resources:
      jobs:
        external: true
        options:
          driver: sqs
          queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/jobs
          access_key_env: AWS_ACCESS_KEY_ID_JOBS
          secret_key_env: AWS_SECRET_ACCESS_KEY_JOBS
          wait_seconds: 10
```
`*_env` names a variable that the host reads from its own environment at start, so the keys never land in Terraform state or `pskit_host.json` [docs/resources.md#on-premises-drivers]. Put them in `provider.options.env_file` (e.g. `.env.onprem`, kept out of git) or in the host's environment. If a variable is missing, the host stops with an error naming it.

**In the terminal**
```bash
pskit validate -p onprem -s prod
```
The AWS deployment keeps using `jobs` as a normal SQS resource."""),

    A(79, provider="alibaba", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#provider-support"],
      user="on alibaba can pskit create OSS bucket for me? no function trigger on it, only for save files",
      steps=[S("search_docs", query="managed bucket without event alibaba standalone",
               docs=[D("docs/resources.md", "provider-support", end="| alibaba, tencent, huawei, oracle, ibm, digitalocean, cloudflare |")])],
      final="""No. On Alibaba, pskit creates a bucket only when an event uses it. A managed bucket with no event is a validation error [docs/resources.md#provider-support].

Do this instead:
1. Create the bucket in the Alibaba console.
2. Declare it as external:
```yaml
resources:
  files:
    type: storage
    external: true
    name: acme-files
```
3. In the handler, `resource("files").native_name` gives the bucket name. Use the OSS SDK (add it to `requirements.txt`) to save files.

pskit never creates, changes or deletes an external bucket."""),

    A(80, provider="azure", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/resource-usage.md#how-dependencies-reach-the-function", "docs/configuration.md#package"],
      user="where does pip install happen for azure? do i need linux wheels like on aws?",
      steps=[S("search_docs", query="dependencies requirements azure install build",
               docs=[D("docs/resource-usage.md", "how-dependencies-reach-the-function")])],
      final="""On Azure, pip doesn't run on your machine. pskit puts `requirements.txt` into the bundle, and Azure's remote (Oryx) build installs it. You don't need Linux wheels locally [docs/resource-usage.md#how-dependencies-reach-the-function].

On AWS, Alibaba, Tencent, Huawei, IBM and DigitalOcean it's different: `pskit deploy` pip-installs Linux wheels into the zip.

**In code**
List only your own dependencies:
```text
requests==2.32.3
```
Never add `py-serverless-kit`. It's bundled with every deployment.

**In the terminal**
```bash
pskit package -p azure
```
This builds the bundle without deploying, so you can check what goes in."""),
]
