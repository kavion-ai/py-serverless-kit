"""Category A (docs Q&A and how-to), batch 12: calling an on-prem host from other programs (pskit client, HTTP API,
AWS-compatible APIs) and existing cloud code on premises. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CL = "docs/client.md"
CO = "docs/resource-guides/compatibility.md"

CONVERSATIONS = [
    A(221, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{CL}#python"],
      user="An ops script must show the first 20 waiting messages of the on-prem `jobs` queue and the queue depth, without taking them away from our worker. Python preferred.",
      steps=[S("search_docs", query="pskit client python peek queue depth",
               docs=[D(CL, "python", start="from py_serverless_kit.client import PskitClient", end="msg.ack()", words=300)])],
      final="""Use the pskit client's `peek`. It looks without consuming, oldest first [docs/client.md#python].

**In code**
```python
from __future__ import annotations

from py_serverless_kit.client import PskitClient

client = PskitClient.from_project(".")
jobs = client.queue("jobs")
print("depth:", jobs.depth())
page = jobs.peek(offset=0, limit=20)
print(page.total, page.has_more)
for m in page.items:
    print(m["body"])
```
`pip install py-serverless-kit` is all it needs; the client uses only the standard library. `from_project(".")` finds the host this project deployed. From another machine, use `PskitClient("http://192.0.2.10:8080")` with `PSKIT_ADMIN_TOKEN` set in the environment.

Don't use `receive` here: that leases the messages, and your worker would compete for them."""),

    A(222, provider="onprem", stage="prod", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{CL}#consuming-outside-pskit"],
      user="can an external script receive/ack from the same built-in queue my pskit worker consumes?",
      steps=[S("search_docs", query="consume queue outside pskit receive ack",
               docs=[D(CL, "consuming-outside-pskit")])],
      final="""It can, but don't. The script and the trigger would share the messages, so each would see only part of them [docs/client.md#consuming-outside-pskit].

Instead:
- give the script its own built-in queue and `receive` / `ack` there;
- or, for a driver-backed queue (Redis stream, Kafka, NATS), consume with the service's own client and its **own consumer group**. *On-prem services → How to use* has the code.

`receive` leases messages for `visibility` seconds; `ack` deletes them, and `nack` (or no answer in time) delivers them again."""),

    A(223, provider="onprem", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=[f"{CL}#nodejs-18"],
      user="external node app (not a pskit function) must send to the onprem jobs queue. how do I get the client?",
      steps=[S("search_docs", query="pskit client node.js install other program",
               docs=[D(CL, "nodejs-18", end="await jobs.send({ orderId: 1 }, { kind: \"new\" });")])],
      final="""Copy the `pskit` package into the app (no dependencies) [docs/client.md#nodejs-18]:
```bash
pskit client install-node --dir ../my-app
```

**In code**
```js
const { PskitClient } = require("pskit");

const client = new PskitClient(process.env.PSKIT_HOST);  // the token comes from PSKIT_ADMIN_TOKEN

async function main() {
  await client.queue("jobs").send({ orderId: 1 }, { kind: "new" });
}

main();
```
TypeScript types ship with the package."""),

    A(224, provider="onprem", stage="prod", mode="ask", page="Test", persona="pasted_error",
      sources=[f"{CL}#when-connections-time-out"],
      user="PskitClientError: HTTP 401 from http://192.0.2.10:8080/__pskit/queues/jobs",
      steps=[S("search_docs", query="pskit client 401",
               docs=[D(CL, "when-connections-time-out", start="| Situation | Fix |", end="| `HTTP 401` |")])],
      final="""The host has an `admin_token`, and your program didn't send it. Pass the token [docs/client.md#when-connections-time-out]:
- set `PSKIT_ADMIN_TOKEN` in the program's environment, or
- or pass the `token=` argument to `PskitClient(...)`, read from your own secret store.

Over plain HTTP, send it as the `x-pskit-token` header. The token is the host's `provider.options.admin_token`."""),

    A(225, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=[f"{CL}#when-connections-time-out"],
      user="my script get TimeoutError to host 8080 on azure vm. host is running fine",
      steps=[S("search_docs", query="client timeout host port firewall",
               docs=[D(CL, "when-connections-time-out")])],
      final="""A timeout almost always means a firewall: your script can't open a TCP connection to port 8080. The host itself is usually fine [docs/client.md#when-connections-time-out].

Fix it one of these ways:
1. Tunnel over SSH, then point the script at localhost:
```bash
pskit client tunnel
```
and use `PSKIT_HOST=http://127.0.0.1:8080`.
2. Or open 8080 **to your IP** in the VM's network security group, and set `provider.options.host: 0.0.0.0` so the host listens on the network."""),

    A(226, provider="onprem", stage="staging", mode="ask", page="Workflows", persona="terse_expert",
      sources=[f"{CL}#http-api"],
      user="start workflow `order` on the onprem host via curl and block until it's done",
      steps=[S("search_docs", query="http api start workflow wait",
               docs=[D(CL, "http-api", start="| `POST /__pskit/workflows/<name>`", end="| `GET /__pskit/executions[/<id>]`")])],
      final="""Add `?wait=true`. Without it you get `202 {execution_id}` [docs/client.md#http-api].

```bash
curl -X POST -H 'content-type: application/json' -H "x-pskit-token: ${PSKIT_ADMIN_TOKEN}" \\
  -d '{"id": 1}' 'http://192.0.2.10:8080/__pskit/workflows/order?wait=true'
```
Leave out the token header when the host has no `admin_token`. Or with pskit:
```bash
pskit workflow start order -i '{"id": 1}' --wait -s staging
```"""),

    A(227, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=[f"{CL}#python", f"{CL}#call-an-on-prem-host-from-any-program-pskit-client-and-http-api"],
      user="in my python script how do i find the address and token of the host i deployed? i dont want to copy them by hand",
      steps=[S("search_docs", query="pskit client from_project host url token",
               docs=[D(CL, "python", start="from py_serverless_kit.client import PskitClient", end="PskitClient.from_project")]),
             S("search_docs", query="pskit client info endpoint token",
               docs=[D(CL, "call-an-on-prem-host-from-any-program-pskit-client-and-http-api", start="pskit client info", end="pskit client info")])],
      final="""Use `PskitClient.from_project(".")`. It connects to the host this project deployed [docs/client.md#python].

**In code**
```python
from __future__ import annotations

from py_serverless_kit.client import PskitClient

client = PskitClient.from_project(".")
print(client.queue("jobs").depth())
```
Run the script from the project folder (or pass its path). Elsewhere, set `PSKIT_HOST` and `PSKIT_ADMIN_TOKEN` instead.

**In the terminal**
```bash
pskit client info
```
shows the endpoint, the token, whether the host is reachable, and code for each resource [docs/client.md#call-an-on-prem-host-from-any-program-pskit-client-and-http-api]."""),

    A(228, provider="onprem", stage="prod", mode="auto", page="Resources", persona="terse_expert",
      sources=[f"{CL}#http-api"],
      user="curl only: upload report.csv to bucket uploads under in/, then list in/",
      steps=[S("search_docs", query="http api storage put list bucket",
               docs=[D(CL, "http-api", start="| `PUT /__pskit/storage/<bucket>/<path>`", end="| `GET /__pskit/storage/<bucket>` |")])],
      final="""**In the terminal**
```bash
curl -X PUT --data-binary @report.csv -H "x-pskit-token: ${PSKIT_ADMIN_TOKEN}" http://192.0.2.10:8080/__pskit/storage/uploads/in/report.csv
curl -H "x-pskit-token: ${PSKIT_ADMIN_TOKEN}" 'http://192.0.2.10:8080/__pskit/storage/uploads?prefix=in/'
```
The PUT answers `201` and fires storage triggers. The listing returns a page of `{key, size, etag}` [docs/client.md#http-api]."""),

    A(229, provider="onprem", stage="prod", mode="ask", page="Code", persona="aws_migrator",
      sources=[f"{CO}#existing-boto3-aws-sdk-lambda-code-on-premises"],
      user="A billing service outside pskit calls our Lambda with boto3 lambda.invoke(FunctionName=ARN). We're moving the functions on-prem. What has to change in that caller?",
      steps=[S("search_docs", query="boto3 lambda invoke on-prem host endpoint",
               docs=[D(CO, "existing-boto3-aws-sdk-lambda-code-on-premises", end="lam.invoke(FunctionName=\"billing\", InvocationType=\"Event\", Payload=b\"{}\")")]),
             S("search_docs", query="lambda invoke api on-prem supported types",
               docs=[D(CO, "existing-boto3-aws-sdk-lambda-code-on-premises", start="Supported: `RequestResponse`", end="the qualifier is ignored.")])],
      final="""One thing: set `endpoint_url` to the host. The on-prem host serves the Lambda Invoke API, and the ARN maps to your function [docs/resource-guides/compatibility.md#existing-boto3-aws-sdk-lambda-code-on-premises].

**In code**
```python
import os

import boto3

lam = boto3.client(
    "lambda",
    endpoint_url=os.environ["PSKIT_HOST"],
    region_name="eu-west-1",
    aws_access_key_id=os.environ.get("PSKIT_ADMIN_TOKEN", "pskit"),
    aws_secret_access_key="x",                       # any value
)
```
The access key id is the host's `admin_token` if it sets one. Everything else stays: `RequestResponse`, `Event` (202) and `DryRun` work, and handler errors come back as `FunctionError: Unhandled` with `errorMessage` / `errorType`. Aliases and versions don't exist on premises; the qualifier is ignored."""),

    A(230, provider="onprem", stage="dev", mode="ask", page="Test", persona="aws_migrator",
      sources=[f"{CO}#test-it"],
      user="how do I point the aws CLI at my local onprem host to send an SQS message to queue jobs?",
      steps=[S("search_docs", query="aws cli sqs send message on-prem host",
               docs=[D(CO, "test-it")])],
      final="""Use `--endpoint-url` with the host, and the queue URL on the host [docs/resource-guides/compatibility.md#test-it]:

```bash
aws sqs send-message --endpoint-url http://127.0.0.1:8080 --queue-url http://127.0.0.1:8080/000000000000/jobs --message-body hello
pskit logs -f
```
The host speaks the SQS API for its own queues. If the host sets an `admin_token`, use it as the AWS access key id."""),

    A(231, provider="onprem", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=[f"{CO}#names-arns-and-urls-in-handlers"],
      user="Our handler reads resource('jobs').arn on AWS. The same code now also deploys on-prem. What do I get there, and how do I avoid an if per provider?",
      steps=[S("search_docs", query="resource arn url native_name on-prem",
               docs=[D(CO, "names-arns-and-urls-in-handlers")])],
      final="""On premises there's no `arn`. You get `native_name`, and `url` is the SQS-compatible queue URL on the host [docs/resource-guides/compatibility.md#names-arns-and-urls-in-handlers].

To avoid branching, use the portable calls instead of the SDK:
```python
from __future__ import annotations

from py_serverless_kit import resource
from py_serverless_kit.runtime.onprem_host import submit_queue


def api(event, ctx):
    if ctx.provider == "onprem":
        return {"id": submit_queue(resource("jobs").native_name, event.http.json())}
    return {"arn": resource("jobs").arn}
```
`ctx.provider` lets you branch when you must. `invoke`, `submit_queue` and the pskit client work without any ARN."""),

    A(232, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="aws_migrator",
      sources=[f"{CO}#not-compatible-and-what-to-use"],
      user="Can our existing Step Functions state machines and SNS topics run on the on-prem host as they are?",
      steps=[S("search_docs", query="step functions sns on-prem not compatible",
               docs=[D(CO, "not-compatible-and-what-to-use")])],
      final="""No. The host doesn't speak the Step Functions or SNS APIs. Use pskit's own equivalents [docs/resource-guides/compatibility.md#not-compatible-and-what-to-use]:
- **Step Functions** → pskit workflows. On premises they run in the embedded engine. Start them with `pskit workflow run` or `client.start_workflow`.
- **SNS** → pskit topics: `submit_topic` in a handler, or `client.topic(...).publish` from a script.

**In code** (a topic)
```yaml
resources:
  order-events:
    type: topic
functions:
  billing:
    handler: app.handlers.billing
    events:
      - topic: {resource: order-events}
```
Workflows in pskit.yml use state types like `task`, `choice` and `wait`, so you rewrite the state machine as a pskit workflow once; it then runs on AWS too."""),

    A(233, provider="onprem", stage="dev", mode="ask", page="Resources", persona="aws_migrator",
      sources=[f"{CO}#other-clouds-queue-sdks", f"{CO}#buckets"],
      user="Our code uses kafka-python and boto3 s3 against AWS MSK and S3. On-prem, what do we run so this code keeps working?",
      steps=[S("search_docs", query="kafka s3 code on premises one-click",
               docs=[D(CO, "other-clouds-queue-sdks"),
                     D(CO, "buckets")])],
      final="""- **Kafka**: one-click Kafka (Redpanda) or Apache Kafka. `kafka-python` works unchanged against it [docs/resource-guides/compatibility.md#other-clouds-queue-sdks].
- **S3**: one-click RustFS, MinIO or LocalStack. Add `endpoint_url` (path-style) and their keys to your boto3 client [docs/resource-guides/compatibility.md#buckets].

**In the terminal**
```bash
pskit resources onprem create events --service kafka --attach worker --save
pskit resources onprem create files --service minio --save
```

The host itself doesn't speak the S3 API, so point boto3 at the S3-compatible service, not at the host."""),

    A(234, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=[f"{CO}#the-pskit-way-every-provider"],
      user="i copied code from a lambda project that does invoke('arn:aws:lambda:eu-west-1:123456789012:function:shop-dev-billing'). will this break on my own server?",
      steps=[S("search_docs", query="invoke lambda arn on premises",
               docs=[D(CO, "the-pskit-way-every-provider")])],
      final="""No. With pskit's `invoke`, names, deployed names (`<service>-<stage>-<function>`) and Lambda ARNs all resolve to the function of this service, on every provider. On premises it's an in-process call [docs/resource-guides/compatibility.md#the-pskit-way-every-provider].

```python
from __future__ import annotations

from py_serverless_kit import invoke


def api(event, ctx):
    return invoke("billing", {"order_id": 1})
```
The short name is easier to read, but the ARN keeps working too."""),

    A(235, provider="onprem", stage="dev", mode="auto", page="Test", persona="terse_expert",
      sources=[f"{CL}#http-api"],
      user="http endpoint to ask the host if orders-db is reachable from it?",
      steps=[S("search_docs", query="http api resource check from host",
               docs=[D(CL, "http-api", start="| `POST /__pskit/resources/<key>/check`", end="| `POST /__pskit/resources/<key>/check`")])],
      final="""`POST /__pskit/resources/<key>/check` returns `{ok, detail, ms}` from the host [docs/client.md#http-api].

```bash
curl -X POST -H "x-pskit-token: ${PSKIT_ADMIN_TOKEN}" http://127.0.0.1:8080/__pskit/resources/orders-db/check
pskit resources check orders-db
```
The second line does the same through pskit."""),

    A(236, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{CL}#call-an-on-prem-host-from-any-program-pskit-client-and-http-api"],
      user="Our Redis queue's port 6379 is closed to the office network, and we want to keep it that way. Can office scripts still add jobs to it?",
      steps=[S("search_docs", query="client host port only driver queue closed port",
               docs=[D(CL, "call-an-on-prem-host-from-any-program-pskit-client-and-http-api", end="That is the usual fix for scripts that time out connecting to a service directly.")])],
      final="""Yes. Go through the pskit host instead of Redis. Only the host's port (default 8080) must be reachable; the queue behind it can use any driver, and its own port can stay closed [docs/client.md#call-an-on-prem-host-from-any-program-pskit-client-and-http-api].

**In code**
```python
from __future__ import annotations

from py_serverless_kit.client import PskitClient

client = PskitClient("http://192.0.2.10:8080")
client.queue("jobs").send({"order_id": 1})
```
Set `PSKIT_ADMIN_TOKEN` for the script when the host has an `admin_token`.

**In studio**
Open **Resources**, then **How to use** on `jobs`. Section 7, *Call it from code*, has the full program with the key and host URL filled in."""),

    A(237, provider="onprem", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{CL}#python"],
      user="from script i want call my function report with data and also start workflow order and wait. pskit client can?",
      steps=[S("search_docs", query="pskit client invoke start_workflow",
               docs=[D(CL, "python", start="client.topic(\"events\")", end="seconds (default 10), with what to check.")])],
      final="""Yes [docs/client.md#python]:

```python
from __future__ import annotations

from py_serverless_kit.client import PskitClient, PskitClientError

client = PskitClient.from_project(".")
try:
    print(client.invoke("report", {"day": "2026-10-22"}))
    print(client.start_workflow("order", {"id": 1}, wait=True))
except PskitClientError as exc:
    print("failed:", exc.status, exc)
```
Errors raise `PskitClientError`. `.status` is the HTTP status, 0 when the host wasn't reached. The default timeout is 10 seconds."""),

    A(238, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{CL}#http-api"],
      user="is there an url that lists all resources of my host with queue depth?",
      steps=[S("search_docs", query="http api list resources depth",
               docs=[D(CL, "http-api", start="| `GET /__pskit/health`", end="| `GET /__pskit/queues/<name>` |")])],
      final="""Yes: `GET /__pskit/resources`. It returns `{"items": [{key, type, name, driver, depth, consumers}]}` [docs/client.md#http-api].

```bash
curl -H "x-pskit-token: ${PSKIT_ADMIN_TOKEN}" http://127.0.0.1:8080/__pskit/resources
```
From Python: `PskitClient.from_project(".").resources()`."""),

    A(239, provider="onprem", stage="prod", mode="ask", page="Code", persona="aws_migrator",
      sources=[f"{CO}#existing-cloud-code-with-pskit"],
      user="Our frontend calls the API Gateway URL /prod/orders today. On-prem, which URL do the same routes have?",
      steps=[S("search_docs", query="function http url on premises same paths",
               docs=[D(CO, "existing-cloud-code-with-pskit", start="| A function's HTTP URL", end="| A function's HTTP URL")])],
      final="""The same paths on the host URL. `pskit info` shows it [docs/resource-guides/compatibility.md#existing-cloud-code-with-pskit]. So a route `/orders` is `http://<host>:8080/orders`; there's no stage segment like `/prod`.

```bash
pskit info -s prod
```
Set `provider.options.advertise` if users reach the host by a DNS name, so `pskit info` shows that URL. Update the frontend's base URL once."""),

    A(240, provider="onprem", stage="prod", mode="ask", page="Test", persona="pasted_error",
      sources=[f"{CL}#when-connections-time-out"],
      user="redis.exceptions.TimeoutError: Timeout connecting to server\n\nscript on my laptop -> the one-click redis on our gcp vm",
      steps=[S("search_docs", query="script timeout service direct cloud vm",
               docs=[D(CL, "when-connections-time-out", end="| The host port itself times out |")])],
      final="""Your laptop can't open a TCP connection to the Redis port on the VM. That's the VM's firewall; Redis itself is usually fine [docs/client.md#when-connections-time-out].

Pick one:
1. Tunnel over SSH. It prints variables pointing at `127.0.0.1`:
```bash
pskit resources onprem tunnel jobs
```
2. Use the pskit client or HTTP API through the host, so only the host port is needed.
3. Open the port **to your IP only** in the GCP firewall rule.

Check the service with:
```bash
pskit resources onprem status jobs
```"""),
]
