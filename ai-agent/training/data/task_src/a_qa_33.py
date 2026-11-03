"""Category A (docs Q&A and how-to), batch 33: azure / aws / gcp resource guides. Azure queue base64 and poison,
app settings owned by pskit, Service Bus subscriptions / tiers / policies / dead letters, Key Vault identity, Cosmos
DB, Event Hubs, database and Redis networking, local runs against a real database; AWS cross-account queues,
connection booleans, FIFO SNS, S3 tests; GCP fan-out, retries, project id, local SDKs for resources send.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


ZR = "docs/resource-guides/azure/README.md"
ZQ = "docs/resource-guides/azure/queue.md"
ZT = "docs/resource-guides/azure/topic.md"
ZX = "docs/resource-guides/azure/custom.md"
ZDB = "docs/resource-guides/azure/database.md"
ZC = "docs/resource-guides/azure/cache.md"
AR = "docs/resource-guides/aws/README.md"
AQ = "docs/resource-guides/aws/queue.md"
AS = "docs/resource-guides/aws/storage.md"
AT = "docs/resource-guides/aws/topic.md"
AC = "docs/resource-guides/aws/cache.md"
GR = "docs/resource-guides/gcp/README.md"
GQ = "docs/resource-guides/gcp/queue.md"
GT = "docs/resource-guides/gcp/topic.md"

CONVERSATIONS = [
    A(631, provider="azure", stage="dev", mode="ask", page="Logs", persona="informal_non_native",
      sources=[f"{ZQ}#4-use-it-in-a-handler", f"{ZQ}#troubleshooting"],
      user="our other app put messages in the azure queue orders-jobs with python sdk, but they all go to orders-jobs-poison and my worker never log them. why??",
      steps=[S("search_docs", query="azure queue messages poison queue base64",
               docs=[D(ZQ, "4-use-it-in-a-handler", start="Messages must be **base64-encoded**", end="end up in the poison queue"),
                     D(ZQ, "troubleshooting", start="| Messages move to `<queue>-poison` |", end="| Messages move to `<queue>-poison` |")])],
      final="""The Azure Functions queue trigger decodes **base64** by default. Messages sent as plain text by another tool end up in the poison queue `orders-jobs-poison` [docs/resource-guides/azure/queue.md#4-use-it-in-a-handler].

Fix the sender: create the `QueueClient` with `message_encode_policy=TextBase64EncodePolicy()` (from `azure.storage.queue`), then send as before.

A message also moves to `<queue>-poison` when the handler raised 5 times, so check the worker's logs too [docs/resource-guides/azure/queue.md#troubleshooting]:
```bash
pskit logs -f --function worker
```"""),

    A(632, provider="azure", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=[f"{ZR}#how-pskit-runs-on-azure-why-some-steps-matter"],
      user="I added FEATURE_X=on in the Azure portal under environment variables of the function app. After the next pskit deploy it was gone. Why?",
      steps=[S("search_docs", query="azure app setting added in portal removed after deploy",
               docs=[D(ZR, "how-pskit-runs-on-azure-why-some-steps-matter", start="- pskit manages the Function App's app settings", end="`environment:` in `pskit.yml` instead.")])],
      final="""pskit manages the Function App's app settings with Terraform, so a setting added by hand in the portal is removed on the next `pskit deploy` [docs/resource-guides/azure/README.md#how-pskit-runs-on-azure-why-some-steps-matter]. Declare it in pskit.yml instead.

**In code**
```yaml
provider:
  environment:
    FEATURE_X: "on"
```
Quote `"on"`, or YAML reads it as a boolean.

**In studio**
1. Open **Overview & provider**.
2. Under *Environment variables*, add `FEATURE_X` = `on`, then click **Save**.

On Azure every app setting is shared by all functions of the service."""),

    A(633, provider="azure", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{ZT}#3-declare-it-in-pskityml"],
      user="Our notify function should trigger on the existing Service Bus topic order-events (namespace owned by the platform team). Does pskit change anything in their namespace, and what rights does our deploy identity need?",
      steps=[S("search_docs", query="service bus topic existing subscription created rights deploy",
               docs=[D(ZT, "3-declare-it-in-pskityml", start="- Both `servicebus_namespace_id`", end="- `topic.filter` is not applied on Azure (warning).")])],
      final="""Yes, one thing: pskit **creates a subscription** named after the function in their topic, and deletes it on `pskit remove`. The topic itself is untouched [docs/resource-guides/azure/topic.md#3-declare-it-in-pskityml].

What you need:
1. The identity running `pskit deploy` (`az login`) needs rights on the namespace to create that subscription, for example *Azure Service Bus Data Owner* or *Contributor*.
2. Both provider options, or validate reports an error:
```yaml
provider:
  options:
    servicebus_namespace_id: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ServiceBus/namespaces/<namespace>
    servicebus_connection: ORDER_EVENTS_CONN
  environment:
    ORDER_EVENTS_CONN: ${env:ORDER_EVENTS_CONN}
```
`topic.filter` isn't applied on Azure, so filter in the handler if needed."""),

    A(634, provider="azure", stage="dev", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{ZT}#azure-service-bus-topic-type-topic"],
      user="can a topic trigger use our Basic tier service bus namespace?",
      steps=[S("search_docs", query="service bus tier topics basic standard",
               docs=[D(ZT, "azure-service-bus-topic-type-topic", end="Service Bus topics need the **Standard** or **Premium** tier")])],
      final="""No. Service Bus topics need the **Standard** or **Premium** tier; Basic has queues only [docs/resource-guides/azure/topic.md#azure-service-bus-topic-type-topic].

Alternatives:
1. Upgrade the namespace (or create a Standard one) and use a `topic` trigger.
2. If one consumer is enough, use a `queue` trigger, which on Azure is a Storage queue, not Service Bus."""),

    A(635, provider="azure", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{ZT}#troubleshooting"],
      user="the notify function's subscription on order-events has 40 messages in its dead-letter queue. what puts them there?",
      steps=[S("search_docs", query="service bus subscription dead-letter messages",
               docs=[D(ZT, "troubleshooting")])],
      final="""A message goes to the subscription's dead-letter queue after the handler failed on it 10 times (`max_delivery_count`) [docs/resource-guides/azure/topic.md#troubleshooting].

1. Find the error in the logs:
```bash
pskit logs --function notify --level ERROR
```
2. Fix the handler and test it locally with one of the bodies:
```bash
pskit invoke -f notify -t topic -d '{"id": 1}'
```
3. Deploy the fix:
```bash
pskit deploy -s prod
```

If the logs show `Unauthorized`, the shared access policy lacks **Listen**."""),

    A(636, provider="azure", stage="dev", mode="ask", page="Resources", persona="aws_migrator",
      sources=[f"{ZX}#key-vault"],
      user="On AWS the Lambda role just reads Secrets Manager. Can my Azure function read Key Vault with its managed identity?",
      steps=[S("search_docs", query="azure key vault managed identity function app",
               docs=[D(ZX, "key-vault", end="Pass its tenant id, client id and secret like any other secret:")])],
      final="""No. The Function App pskit creates has no managed identity [docs/resource-guides/azure/custom.md#key-vault].

Use a service principal instead:
1. In the portal: Microsoft Entra ID → App registrations → + New registration, then *Certificates & secrets* → a new client secret.
2. Give it the *Key Vault Secrets User* role on the vault.
3. Pass its ids as app settings:
```yaml
provider:
  environment:
    AZURE_TENANT_ID: ${env:AZURE_TENANT_ID}
    AZURE_CLIENT_ID: ${env:AZURE_CLIENT_ID}
    AZURE_CLIENT_SECRET: ${env:AZURE_CLIENT_SECRET}
resources:
  vault:
    type: custom
    external: true
    connection:
      url: https://acme-kv.vault.azure.net/
```
4. In the handler, `SecretClient(resource("vault").url, DefaultAzureCredential())` from `azure-keyvault-secrets` and `azure-identity`."""),

    A(637, provider="azure", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{ZX}#cosmos-db-nosql"],
      user="We have a Cosmos DB for NoSQL account (database shop, container orders). How do I hook it up so our api function can upsert orders?",
      steps=[S("search_docs", query="cosmos db nosql custom resource azure",
               docs=[D(ZX, "cosmos-db-nosql", words=300)])],
      final="""Describe it as a `custom` resource. Keep the key in an app setting and put its *name* in `connection` [docs/resource-guides/azure/custom.md#cosmos-db-nosql].

**In code**
```yaml
provider:
  environment:
    COSMOS_KEY: ${env:COSMOS_KEY}
resources:
  orders-store:
    type: custom
    external: true
    connection:
      endpoint: https://acme-cosmos.documents.azure.com:443/
      database: shop
      container: orders
      key_env: COSMOS_KEY
```
```python
from __future__ import annotations

from azure.cosmos import CosmosClient
from py_serverless_kit import resource


def api(event, ctx):
    c = resource("orders-store")
    client = CosmosClient(c["endpoint"], credential=ctx.env[c["key_env"]])
    orders = client.get_database_client(c["database"]).get_container_client(c["container"])
    orders.upsert_item({"id": "1", "customerId": "c1", "total": 10})
```
Add `azure-cosmos` to `requirements.txt`. The URI and key are under the account's *Settings → Keys*.

**In studio**
1. **Resources** → **+ Add resource** → type custom, *External / existing*.
2. **Add connection value** for `endpoint`, `database`, `container` and `key_env`, then **Save**.

**In the terminal**
```bash
export COSMOS_KEY='<primary key>'
pskit validate
```"""),

    A(638, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=[f"{ZX}#event-hubs"],
      user="can i trigger my function from azure event hubs with pskit?",
      steps=[S("search_docs", query="event hubs trigger azure",
               docs=[D(ZX, "event-hubs")])],
      final="""No, pskit has no Event Hubs trigger [docs/resource-guides/azure/custom.md#event-hubs].

What you can do:
1. Describe the hub as a `custom` resource (`namespace`, `hub`, `connection_string_env`) and **send** to it from a handler with `azure-eventhub`.
2. To **consume** it, run a `schedule` function that reads the hub with the SDK.
3. Or, if you control the producer, send to a Storage queue or a Service Bus topic instead; both have pskit triggers on Azure."""),

    A(639, provider="azure", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{ZDB}#1-create-the-server-portal", f"{ZDB}#troubleshooting"],
      user="psycopg.OperationalError: connection timed out\n\nfrom the api function on azure, postgres flexible server. works from my laptop.",
      steps=[S("search_docs", query="azure postgres connection timed out function app",
               docs=[D(ZDB, "troubleshooting"),
                     D(ZDB, "1-create-the-server-portal", start="3. **Networking** tab", end="your own machine")])],
      final="""The server's firewall doesn't let the Function App in. The Consumption Function App has no fixed outbound IP and no VNet, so allowing your laptop's IP isn't enough [docs/resource-guides/azure/database.md#1-create-the-server-portal].

Fix in the portal: the server → *Networking* → tick **Allow public access from any Azure service within Azure to this server** → Save [docs/resource-guides/azure/database.md#troubleshooting].

No redeploy is needed. Keep `sslmode: require` in the resource's `connection`."""),

    A(640, provider="azure", stage="dev", mode="ask", page="Code", persona="pasted_error",
      sources=[f"{ZC}#2-collect-the-values", f"{ZC}#troubleshooting"],
      user="redis.exceptions.ConnectionError: Connection reset by peer\n\nazure cache for redis, i use port 6379 in connection",
      steps=[S("search_docs", query="azure redis connection reset port tls",
               docs=[D(ZC, "troubleshooting"),
                     D(ZC, "2-collect-the-values", start="| Port |", end="| TLS |")])],
      final="""Azure Redis always uses TLS; the non-TLS port 6379 is disabled by default [docs/resource-guides/azure/cache.md#2-collect-the-values]. Use the TLS port with `ssl=True`: 6380 for Azure Cache for Redis, 10000 for Azure Managed Redis.

**In code**
```yaml
resources:
  cache:
    type: cache
    external: true
    connection:
      host: acme-cache.redis.cache.windows.net
      port: 6380
      ssl: true
      password_env: CACHE_KEY
```
In the handler, pass `ssl=c.get("ssl") == "true"`: booleans in `connection` arrive as strings. Also check that the cache's *Networking* allows public access [docs/resource-guides/azure/cache.md#troubleshooting]."""),

    A(641, provider="azure", stage="prod", mode="ask", page="Resources", persona="beginner",
      sources=[f"{ZT}#2-collect-the-values"],
      user="for the service bus connection string, is it ok to copy the RootManageSharedAccessKey one?",
      steps=[S("search_docs", query="service bus shared access policy connection string",
               docs=[D(ZT, "2-collect-the-values", start="Create a dedicated policy", end="copy its *Primary Connection String*.")])],
      final="""Better not. Create a dedicated policy instead [docs/resource-guides/azure/topic.md#2-collect-the-values]:

1. Namespace → *Shared access policies* → *+ Add*.
2. Name it `pskit-app`, tick **Send** and **Listen** → Create.
3. Copy its *Primary Connection String* and export it on the machine that deploys:
```bash
export ORDER_EVENTS_CONN='<primary connection string>'
```
Then reference it in pskit.yml as `${env:ORDER_EVENTS_CONN}`, never the literal value."""),

    A(642, provider="azure", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=[f"{ZDB}#5-test", f"{ZDB}#troubleshooting"],
      user="terminal: run api locally against the real azure postgres before deploying",
      steps=[S("search_docs", query="invoke locally against real azure database",
               docs=[D(ZDB, "5-test"),
                     D(ZDB, "troubleshooting", start="| `connection timed out` locally |", end="| `connection timed out` locally |")])],
      final="""**In the terminal**
```bash
export ORDERS_DB_PASSWORD='<password>'
pskit invoke -f api
pskit resources send --list
```
`pskit invoke` runs the handler on your machine against the real server [docs/resource-guides/azure/database.md#5-test]. Your client IP must be allowed under the server's *Networking → Firewall rules*, or it times out [docs/resource-guides/azure/database.md#troubleshooting]. `resources send --list` prints the variables the function gets."""),

    A(643, provider="aws", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{AR}#how-pskit-runs-on-aws-why-some-steps-matter", f"{AQ}#3-declare-it-in-pskityml"],
      user="The analytics team's SQS queue lives in another AWS account. Can our pskit worker be triggered by it, and can our api at least send to it?",
      steps=[S("search_docs", query="sqs queue another account trigger send connection arn",
               docs=[D(AQ, "3-declare-it-in-pskityml", start="- Queue in **another account or region**", end="the trigger lookup only searches the deploy account and region."),
                     D(AR, "how-pskit-runs-on-aws-why-some-steps-matter", start="- An external bucket, queue or topic", end="must be **in the same account and region** as the functions.")])],
      final="""Trigger: no. Triggers on an external queue use a name lookup, so the queue must be in the same account and region as the functions [docs/resource-guides/aws/README.md#how-pskit-runs-on-aws-why-some-steps-matter].

Send: yes. Set `connection.arn` (pskit then uses it as-is, without a lookup) and add `url` yourself, because there is no `_URL` variable without the lookup [docs/resource-guides/aws/queue.md#3-declare-it-in-pskityml].

**In code**
```yaml
resources:
  analytics:
    type: queue
    external: true
    name: analytics-events
    connection:
      arn: arn:aws:sqs:eu-west-1:210987654321:analytics-events
      url: https://sqs.eu-west-1.amazonaws.com/210987654321/analytics-events
    functions: [api]
```
For a trigger, the messages have to reach a queue in your own account and region."""),

    A(644, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{AC}#4-use-it-in-a-handler"],
      user="in connection i wrote ssl: true for my elasticache. in code if c['ssl'] is never True. bug?",
      steps=[S("search_docs", query="connection boolean values string true",
               docs=[D(AC, "4-use-it-in-a-handler", start="For a cluster-mode endpoint")])],
      final="""Not a bug: booleans in `connection` arrive as the strings `"true"` / `"false"` [docs/resource-guides/aws/cache.md#4-use-it-in-a-handler].

**In code**
```python
ssl = c.get("ssl") == "true"
```
Numbers are strings too, so use `int(c["port"])`."""),

    A(645, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{AT}#1-create-the-topic-console"],
      user="We have a FIFO SNS topic orders.fifo. Can I subscribe a pskit Lambda to it with a topic event?",
      steps=[S("search_docs", query="sns fifo topic lambda subscription",
               docs=[D(AT, "1-create-the-topic-console")])],
      final="""No. Lambda subscriptions need a **Standard** SNS topic [docs/resource-guides/aws/topic.md#1-create-the-topic-console].

Alternatives:
1. Publish the events the function needs to a Standard topic and subscribe the function there.
2. Or trigger the function from an SQS FIFO queue in your account: describe it as an external `queue` resource with the full name, including `.fifo`, in `name`. Getting the messages into that queue is up to your publishers."""),

    A(646, provider="aws", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=[f"{AS}#5-test", "docs/studio.md#test-functions"],
      user="how do i check my deployed s3 trigger on invoices bucket really works, prefix incoming/ and .pdf?",
      steps=[S("search_docs", query="test s3 storage trigger deployed upload",
               docs=[D(AS, "5-test")]),
             S("search_docs", query="studio test send to deployed storage trigger",
               docs=[D("docs/studio.md", "test-functions", start="3. **Run locally**", end="Turn on *Show the function's logs* to watch it.")])],
      final="""Upload a matching object and watch the logs [docs/resource-guides/aws/storage.md#5-test].

**In the terminal**
```bash
pskit resources send invoices -s staging -d '{"key": "incoming/a.pdf", "content": "test"}'
pskit logs -s staging -f --function on-invoice
```

**In studio**
1. Open **Test** with aws / staging in the top bar.
2. Pick `on-invoice` and its storage trigger; the sample key matches the prefix and suffix.
3. Click **☁ Send to aws / staging** and turn on *Show the function's logs* [docs/studio.md#test-functions].

The key must start with `incoming/` and end in `.pdf`, or the function isn't triggered."""),

    A(647, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{GT}#pubsub-topic-type-topic", f"{GT}#3-declare-it-in-pskityml"],
      user="On GCP both notify and audit should receive every message published to order-events. Is that queue or topic, and does each function really get every message?",
      steps=[S("search_docs", query="gcp topic fan-out several functions every message",
               docs=[D(GT, "pubsub-topic-type-topic", end="use `topic` when several functions should"),
                     D(GT, "3-declare-it-in-pskityml", start="What pskit does with it", end="never the topic.")])],
      final="""Use `topic`. Each subscribed function gets its own Eventarc trigger with its own push subscription, so both receive every message [docs/resource-guides/gcp/topic.md#3-declare-it-in-pskityml].

**In code**
```yaml
resources:
  order-events: {type: topic, external: true, name: order-events}
functions:
  notify:
    handler: app.handlers.notify
    events:
      - topic: {resource: order-events}
  audit:
    handler: app.handlers.audit
    events:
      - topic: {resource: order-events}
```
On GCP `queue` and `topic` are both Pub/Sub topics; `topic` is the one for fan-out [docs/resource-guides/gcp/topic.md#pubsub-topic-type-topic].

**In studio**
1. **Functions** → `notify` → *Add a trigger* → topic → pick `order-events`.
2. Do the same for `audit`, then click **Save**."""),

    A(648, provider="gcp", stage="prod", mode="ask", page="Logs", persona="beginner",
      sources=[f"{GQ}#troubleshooting", f"{GQ}#3-declare-it-in-pskityml"],
      user="my gcp worker logs the same message again and again, like 50 times. how to stop that",
      steps=[S("search_docs", query="gcp same message processed again and again retry",
               docs=[D(GQ, "troubleshooting", start="| The same message is processed again and again |", end="| The same message is processed again and again |"),
                     D(GQ, "3-declare-it-in-pskityml", start="Not applied on GCP", end="Eventarc-created subscription in the console")])],
      final="""The handler raises an error on that message, and Pub/Sub retries it until it succeeds or the message expires [docs/resource-guides/gcp/queue.md#troubleshooting].

1. Find the error:
```bash
pskit logs -s prod --function worker --level ERROR
```
2. Fix the handler (or catch and log messages you can't process, so the function returns normally) and deploy.
3. Optional: a dead-letter topic can be set on the Eventarc-created subscription in the console (*Pub/Sub → Subscriptions → Edit → Dead lettering*); a redeploy may recreate it. pskit's `dead_letter` and `max_receive` are not applied on GCP [docs/resource-guides/gcp/queue.md#3-declare-it-in-pskityml]."""),

    A(649, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=[f"{GR}#values-you-need-for-every-google-cloud-resource"],
      user="i typed \"Acme Orders\" as project in options because that is what the console shows. deploy cant find the project. what goes there?",
      steps=[S("search_docs", query="gcp project id vs project name",
               docs=[D(GR, "values-you-need-for-every-google-cloud-resource")])],
      final="""`provider.options.project` needs the **project ID**, not the project name. In the console, open the project picker at the top and copy the value in the *ID* column [docs/resource-guides/gcp/README.md#values-you-need-for-every-google-cloud-resource].

**In code**
```yaml
provider:
  options:
    project: acme-orders-123456
```
(use your real ID)

**In studio**
1. Open **Overview & provider**.
2. Replace *Project* with the project ID and click **Save**."""),

    A(650, provider="gcp", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=[f"{GR}#credentials-for-deploying"],
      user="ModuleNotFoundError: No module named 'google.cloud'\n\nthis is from pskit resources send jobs -d '{\"id\": 1}' on my laptop",
      steps=[S("search_docs", query="pskit resources send gcp needs google cloud libraries",
               docs=[D(GR, "credentials-for-deploying")])],
      final="""`pskit resources send` and `pskit trigger` publish and upload from your machine with your local credentials, so on GCP they need the Google client libraries installed where pskit runs [docs/resource-guides/gcp/README.md#credentials-for-deploying].

**In the terminal**
```bash
pip install google-cloud-pubsub google-cloud-storage
gcloud auth application-default login
pskit resources send jobs -d '{"id": 1}'
```
Install them into the same environment as pskit (for example the project's `.venv`)."""),
]
