"""Category A (docs Q&A and how-to), batch 32: aws / gcp resource guides. Console-made SQS queues, S3
notifications, SNS on remove, RDS / VPC networking, Secrets Manager, DynamoDB grants, KMS; Pub/Sub topics vs
subscriptions, publisher roles, bucket locations, Cloud SQL, VPC connectors, Firestore, runtime service account.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


AQ = "docs/resource-guides/aws/queue.md"
AS = "docs/resource-guides/aws/storage.md"
AT = "docs/resource-guides/aws/topic.md"
ADB = "docs/resource-guides/aws/database.md"
AC = "docs/resource-guides/aws/custom.md"
AR = "docs/resource-guides/aws/README.md"
GR = "docs/resource-guides/gcp/README.md"
GQ = "docs/resource-guides/gcp/queue.md"
GS = "docs/resource-guides/gcp/storage.md"
GDB = "docs/resource-guides/gcp/database.md"
GC = "docs/resource-guides/gcp/cache.md"
GX = "docs/resource-guides/gcp/custom.md"

CONVERSATIONS = [
    A(611, provider="aws", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{AQ}#troubleshooting", f"{AQ}#3-declare-it-in-pskityml"],
      user="deploy fails: Queue visibility timeout: 30 seconds is less than Function timeout: 60 seconds\n\nthe queue is one we made in the SQS console, i already put visibility_timeout: 120 on the queue event",
      steps=[S("search_docs", query="queue visibility timeout less than function timeout external queue",
               docs=[D(AQ, "troubleshooting"),
                     D(AQ, "3-declare-it-in-pskityml", start="Notes:", end="- FIFO queue:")])],
      final="""The queue's visibility timeout must be at least the function timeout. `visibility_timeout` on the event only applies when pskit **creates** the queue; for a queue you made in the console, pskit doesn't change its settings [docs/resource-guides/aws/queue.md#3-declare-it-in-pskityml].

Fix it in the console:
1. SQS → your queue → **Edit** → *Visibility timeout*: at least 60 s. AWS recommends 6 × the function timeout, so 360 s here.
2. Save, then deploy again:
```bash
pskit deploy
```
You can remove `visibility_timeout` from the event, since it has no effect on an external queue [docs/resource-guides/aws/queue.md#troubleshooting]."""),

    A(612, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{AS}#3-declare-it-in-pskityml"],
      user="Our S3 bucket acme-raw-prod already has an event notification that sends new objects to another team's Lambda. I want a pskit function to also run on new .json files in that bucket. Is a storage event safe here?",
      steps=[S("search_docs", query="s3 bucket existing event notifications storage trigger",
               docs=[D(AS, "3-declare-it-in-pskityml", start="What pskit does with it", end="Only reading/writing")])],
      final="""No, not on that bucket as it is. S3 has one notification configuration per bucket. The `aws_s3_bucket_notification` pskit creates **replaces** the notifications already on the bucket, so the other team's Lambda would stop getting events, and `pskit remove` deletes it again [docs/resource-guides/aws/storage.md#3-declare-it-in-pskityml].

Safe options:
1. Route the bucket's existing notification to an SNS topic (or SQS queue), and subscribe both Lambdas to it. In pskit, trigger your function from that topic:
```yaml
resources:
  raw-events: {type: topic, external: true, name: acme-raw-events}
functions:
  ingest:
    handler: app.ingest.run
    events:
      - topic: {resource: raw-events}
```
2. If you only need to read or write objects, bind the bucket without a `storage` event; the binding still grants the S3 permissions.

Agree on option 1 with the other team before you change their notification."""),

    A(613, provider="aws", stage="staging", mode="ask", page="Deploy", persona="informal_non_native",
      sources=[f"{AT}#3-declare-it-in-pskityml", "docs/cli.md#pskit-plan"],
      user="ops team made sns topic order-events, my function subscribe to it in pskit. if i do pskit remove the topic is deleted too??",
      steps=[S("search_docs", query="pskit remove external sns topic subscription",
               docs=[D(AT, "3-declare-it-in-pskityml", start="What pskit does with it", end="`pskit remove` deletes the subscription, never the topic.")])],
      final="""No. The topic is `external: true`, so pskit only looks it up by name. `pskit remove` deletes the Lambda subscription pskit created, never the topic [docs/resource-guides/aws/topic.md#3-declare-it-in-pskityml].

To see what would be deleted first:

**In the terminal**
```bash
pskit plan -s staging --destroy
```

**In studio**
1. Open **Deploy** with aws / staging in the top bar.
2. Click **Remove**; studio asks you to confirm before anything is deleted."""),

    A(614, provider="aws", stage="dev", mode="ask", page="Resources", persona="aws_migrator",
      sources=[f"{ADB}#networking-first", f"{ADB}#3-declare-it-in-pskityml"],
      user="Our Postgres RDS instance is private in a VPC. In SAM we just set VpcConfig on the function. How do I get a pskit Lambda into the VPC so it can reach the database?",
      steps=[S("search_docs", query="lambda vpc rds private database vpc_config",
               docs=[D(ADB, "networking-first"),
                     D(ADB, "3-declare-it-in-pskityml", end="Then in the console", words=420)])],
      final="""pskit deploys Lambdas outside any VPC unless you set `functions.<fn>.options.vpc_config`; it is merged into the `aws_lambda_function`, like SAM's `VpcConfig` [docs/resource-guides/aws/database.md#networking-first].

**In code**
```yaml
provider:
  name: aws
  environment:
    ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}
  iam:
    statements:
      - actions: [ec2:CreateNetworkInterface, ec2:DescribeNetworkInterfaces, ec2:DescribeSubnets,
                  ec2:DeleteNetworkInterface, ec2:AssignPrivateIpAddresses, ec2:UnassignPrivateIpAddresses]
        resources: ["*"]
resources:
  orders-db:
    type: database
    external: true
    connection: {host: orders.abc123.eu-west-1.rds.amazonaws.com, port: 5432, database: orders,
                 user: postgres, sslmode: require, password_env: ORDERS_DB_PASSWORD}
    functions: [api]
functions:
  api:
    handler: app.handlers.api
    options:
      vpc_config:
        subnet_ids: [subnet-0aaa, subnet-0bbb]
        security_group_ids: [sg-0lambda]
```
The EC2 statement lets the Lambda create its network interfaces [docs/resource-guides/aws/database.md#3-declare-it-in-pskityml]. Then allow `sg-0lambda` on port 5432 in the database's security group.

**In studio**
1. Open **Functions**, click `api`, and add `vpc_config` under *Provider-specific options*.
2. Click **Save**.

Note: in a VPC the Lambda can't reach AWS APIs (SQS, S3, Secrets Manager) without a NAT gateway or VPC endpoints."""),

    A(615, provider="aws", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{ADB}#troubleshooting"],
      user="Error: The provided execution role does not have permissions to call CreateNetworkInterface on EC2\n\nhappened right after I added vpc_config to the reports function",
      steps=[S("search_docs", query="CreateNetworkInterface execution role vpc_config",
               docs=[D(ADB, "troubleshooting")])],
      final="""A Lambda in a VPC needs EC2 network-interface permissions on its role, and pskit doesn't add them for `vpc_config` [docs/resource-guides/aws/database.md#troubleshooting].

**In code**
```yaml
provider:
  iam:
    statements:
      - actions: [ec2:CreateNetworkInterface, ec2:DescribeNetworkInterfaces, ec2:DescribeSubnets,
                  ec2:DeleteNetworkInterface, ec2:AssignPrivateIpAddresses, ec2:UnassignPrivateIpAddresses]
        resources: ["*"]
```

**In the terminal**
```bash
pskit validate
pskit deploy
```
If `reports` uses its own `iam.role`, pskit adds no policies to it; add these actions to that role yourself."""),

    A(616, provider="aws", stage="staging", mode="ask", page="Logs", persona="beginner",
      sources=[f"{ADB}#networking-first", f"{AR}#how-pskit-runs-on-aws-why-some-steps-matter"],
      user="i put my lambda in the vpc for the database. db works now but sending to sqs just hangs until timeout. why",
      steps=[S("search_docs", query="lambda vpc timeout calling sqs s3 aws apis",
               docs=[D(ADB, "networking-first", start="A Lambda in a VPC has no internet access"),
                     D(AR, "how-pskit-runs-on-aws-why-some-steps-matter", start="- Functions run outside any VPC")])],
      final="""A Lambda inside a VPC has no internet access, so it can't reach AWS APIs like SQS, S3 or Secrets Manager unless its subnets have a **NAT gateway** or **VPC endpoints** [docs/resource-guides/aws/database.md#networking-first].

What to do:
1. Add a NAT gateway route to the subnets in `vpc_config`, or create a VPC endpoint for SQS in that VPC. pskit doesn't create either; set them up in the VPC console or your network stack.
2. Or keep the SQS sending in a function that has no `vpc_config`. Only functions that set `vpc_config` run in the VPC [docs/resource-guides/aws/README.md#how-pskit-runs-on-aws-why-some-steps-matter]."""),

    A(617, provider="aws", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=[f"{ADB}#4-use-it-in-a-handler", f"{ADB}#troubleshooting", "docs/configuration.md#functions"],
      user="rds says too many connections when traffic spikes. lambda api fn. options?",
      steps=[S("search_docs", query="too many connections rds lambda",
               docs=[D(ADB, "4-use-it-in-a-handler", start="Many concurrent Lambdas"),
                     D(ADB, "troubleshooting", start="| `too many connections` |", end="| `too many connections` |")]),
             S("search_docs", query="function concurrency reserved",
               docs=[D("docs/configuration.md", "functions", start="| `concurrency` |", end="| `concurrency` |")])],
      final="""Two options [docs/resource-guides/aws/database.md#troubleshooting]:

1. **RDS Proxy** (RDS → *Proxies*) pools the connections. Put the proxy endpoint in the resource's `connection.host`.
2. Cap the function's concurrency:
```yaml
functions:
  api:
    handler: app.handlers.api
    concurrency: 20
```
`concurrency` is reserved concurrency on Lambda [docs/configuration.md#functions]. In studio: **Functions** → `api` → *Concurrency & tags* → *Reserved concurrency / max instances*.

Open the connection once per container (module level or a cached global), not on every request."""),

    A(618, provider="aws", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#get_secret-secrets-on-every-provider", f"{AR}#how-pskit-runs-on-aws-why-some-steps-matter"],
      user="Our Stripe key is a JSON secret in AWS Secrets Manager named orders/stripe, field api_key. I'd rather not pass it as an environment variable. Show me the pskit.yml and handler code only.",
      steps=[S("search_docs", query="read secret from aws secrets manager in handler",
               docs=[D("docs/handlers.md", "get_secret-secrets-on-every-provider")]),
             S("search_docs", query="aws iam permissions secrets manager not granted",
               docs=[D(AR, "how-pskit-runs-on-aws-why-some-steps-matter", start="- For `storage`, `queue` and `topic` resources", end="granted automatically")])],
      final="""**In code**

Use `get_secret()` with the `aws` store driver; the store is chosen by environment variables, so the code stays the same elsewhere [docs/handlers.md#get_secret-secrets-on-every-provider].
```yaml
provider:
  name: aws
  environment:
    PSKIT_SECRETS_DRIVER: aws
```
```python
from __future__ import annotations

from py_serverless_kit import get_secret


def api(event, ctx):
    stripe_key = get_secret("orders/stripe", "api_key")  # one field of a JSON secret, cached 60 s
    return {"loaded": bool(stripe_key)}
```
It uses the Lambda's credentials. pskit doesn't grant Secrets Manager access automatically [docs/resource-guides/aws/README.md#how-pskit-runs-on-aws-why-some-steps-matter], so add the `GetSecretValue` action on that secret's ARN under `provider.iam.statements`."""),

    A(619, provider="aws", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{AC}#other-aws-services-type-custom", f"{AC}#dynamodb"],
      user="i made dynamodb table orders in console and add it as custom resource. now AccessDeniedException on PutItem. pskit not give permission?",
      steps=[S("search_docs", query="custom resource dynamodb permissions iam",
               docs=[D(AC, "other-aws-services-type-custom", end="only for resources you also define"),
                     D(AC, "dynamodb", words=200)])],
      final="""Right, pskit grants **no IAM permissions** for `custom` resources. Add them under `provider.iam.statements` [docs/resource-guides/aws/custom.md#other-aws-services-type-custom].

**In code**
```yaml
provider:
  iam:
    statements:
      - actions: [dynamodb:GetItem, dynamodb:PutItem, dynamodb:UpdateItem, dynamodb:Query]
        resources: ["arn:aws:dynamodb:eu-west-1:123456789012:table/orders"]
```
Paste your table's ARN from DynamoDB → the table → *General information* [docs/resource-guides/aws/custom.md#dynamodb].

**In the terminal**
```bash
pskit validate
pskit deploy
```
Only `storage`, `queue` and `topic` resources get automatic grants."""),

    A(620, provider="aws", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{AQ}#3-declare-it-in-pskityml", f"{AR}#how-pskit-runs-on-aws-why-some-steps-matter"],
      user="KMS.AccessDeniedException when api sends to the jobs queue. The queue is encrypted with our own KMS key. Other permissions look fine.",
      steps=[S("search_docs", query="sqs customer managed kms key permissions",
               docs=[D(AQ, "3-declare-it-in-pskityml", start="- Queue encrypted with a **customer-managed KMS key**", end="`provider.iam.statements`."),
                     D(AR, "how-pskit-runs-on-aws-why-some-steps-matter", start="- For `storage`, `queue` and `topic` resources", end="granted automatically")])],
      final="""pskit's `pskit-resources` policy covers SQS actions, but nothing for KMS. A queue with a customer-managed key also needs `kms:Decrypt` and `kms:GenerateDataKey` on that key [docs/resource-guides/aws/queue.md#3-declare-it-in-pskityml].

**In code**
```yaml
provider:
  iam:
    statements:
      - actions: [kms:Decrypt, kms:GenerateDataKey]
        resources: ["arn:aws:kms:eu-west-1:123456789012:key/<key id>"]
```
Use your key's ARN. Then deploy:
```bash
pskit deploy -s prod
```
Studio asks you to type a confirmation for a `prod` stage."""),

    A(621, provider="gcp", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{GQ}#pubsub-as-a-queue-type-queue", f"{GQ}#troubleshooting"],
      user="i made a pub/sub subscription jobs-sub in console and put it as name of my queue resource. deploy says not found. what is wrong",
      steps=[S("search_docs", query="gcp queue pubsub subscription not found",
               docs=[D(GQ, "pubsub-as-a-queue-type-queue", end="push subscription that feeds the function."),
                     D(GQ, "troubleshooting", start="| Deploy: topic not found |", end="| Deploy: topic not found |")])],
      final="""On GCP a pskit `queue` is a **Pub/Sub topic**, not a subscription. Eventarc creates and manages the push subscription that feeds the function [docs/resource-guides/gcp/queue.md#pubsub-as-a-queue-type-queue].

Fix:
1. Put the **topic ID** in `name` (not the subscription, not the full `projects/.../topics/...` path):
```yaml
resources:
  jobs: {type: queue, external: true, name: orders-jobs}
```
2. Make sure the topic is in the project from `provider.options.project` [docs/resource-guides/gcp/queue.md#troubleshooting].
3. You can delete `jobs-sub` unless another consumer uses it."""),

    A(622, provider="gcp", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{GR}#how-pskit-runs-on-google-cloud-why-some-steps-matter", f"{GQ}#3-declare-it-in-pskityml"],
      user="google.api_core.exceptions.PermissionDenied: 403 User not authorized to perform this action.\n\nthis is from api when it publishes to the jobs queue. i added pubsub.topics.publish in iam.statements already",
      steps=[S("search_docs", query="gcp pubsub publish permission denied runtime service account",
               docs=[D(GR, "how-pskit-runs-on-google-cloud-why-some-steps-matter", start="- **pskit grants no roles", end="don't rely on it."),
                     D(GQ, "3-declare-it-in-pskityml", start="Grant the runtime service account the right to publish", end="**Pub/Sub Publisher**.")])],
      final="""On GCP pskit grants no roles for resources, and `iam.statements` are ignored [docs/resource-guides/gcp/README.md#how-pskit-runs-on-google-cloud-why-some-steps-matter]. Grant the role in the console instead:

1. In the console: Pub/Sub → Topics → tick the topic → *Permissions* → *Add principal*.
2. Principal: the runtime service account (`provider.options.service_account`, or `<project number>-compute@developer.gserviceaccount.com` if you didn't set one).
3. Role: **Pub/Sub Publisher** → Save [docs/resource-guides/gcp/queue.md#3-declare-it-in-pskityml].

No redeploy is needed. You can remove the `iam.statements` entry; it has no effect on GCP."""),

    A(623, provider="gcp", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{GS}#1-create-the-bucket-console", f"{GS}#troubleshooting"],
      user="Our existing bucket acme-media is a multi-region EU bucket. Deploying a storage trigger on it fails with a location mismatch. provider.region is europe-west1. What are the options?",
      steps=[S("search_docs", query="gcs bucket location trigger region multi-region",
               docs=[D(GS, "1-create-the-bucket-console"),
                     D(GS, "troubleshooting", start="| Deploy: trigger location", end="| Deploy: trigger location")])],
      final="""pskit creates the Eventarc trigger in `provider.region`, and Cloud Storage triggers must be in the bucket's location. So dual- and multi-region buckets can't trigger pskit functions [docs/resource-guides/gcp/storage.md#1-create-the-bucket-console].

Options:
1. Use a single-region bucket in `europe-west1` for the files that should trigger the function (for example an upload bucket), and copy to `acme-media` from the handler.
2. Keep `acme-media` as a resource without a `storage` event, and read it from a function triggered another way (schedule, queue or HTTP).

There is no pskit setting that makes a multi-region bucket trigger work [docs/resource-guides/gcp/storage.md#troubleshooting]."""),

    A(624, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=[f"{GS}#3-declare-it-in-pskityml", f"{GS}#troubleshooting"],
      user="deploy of my storage trigger fail with error about cloud storage service agent and pubsub publisher. i dont use pubsub!",
      steps=[S("search_docs", query="storage trigger cloud storage service agent pubsub publisher",
               docs=[D(GS, "3-declare-it-in-pskityml", start="What pskit does with it", end="function is still invoked"),
                     D(GS, "troubleshooting", start="| Deploy: Cloud Storage service agent", end="| Deploy: Cloud Storage service agent")])],
      final="""Cloud Storage triggers deliver events through Pub/Sub, so pskit grants the project's Cloud Storage service agent `roles/pubsub.publisher` during deploy [docs/resource-guides/gcp/storage.md#3-declare-it-in-pskityml]. The error means the account you deploy with can't grant that role.

Fix [docs/resource-guides/gcp/storage.md#troubleshooting]:
1. Deploy with an account that may grant project IAM roles.
2. Enable the Eventarc API in the project.
3. Run the deploy again:
```bash
pskit deploy
```"""),

    A(625, provider="gcp", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{GDB}#cloud-sql-type-database", f"{GDB}#2-collect-the-values", f"{GDB}#4-use-it-in-a-handler"],
      user="How do I connect our api Cloud Function to an existing Cloud SQL Postgres instance (public IP, connection name my-project:europe-west1:orders-pg, database orders, user pskitapp)?",
      steps=[S("search_docs", query="cloud sql postgres cloud functions connector",
               docs=[D(GDB, "cloud-sql-type-database", end="in [cache.md](cache.md#3-declare-it-in-pskityml)."),
                     D(GDB, "2-collect-the-values", start="Grant the runtime service account **Cloud SQL Client**")]),
             S("search_docs", query="cloud sql python connector handler pg8000",
               docs=[D(GDB, "4-use-it-in-a-handler", words=200)])],
      final="""Use the **Cloud SQL Python Connector**: it authenticates as the function's service account and encrypts the connection, with no authorized networks to open [docs/resource-guides/gcp/database.md#cloud-sql-type-database].

**In the console** (once): grant the runtime service account **Cloud SQL Client** and enable the **Cloud SQL Admin API** [docs/resource-guides/gcp/database.md#2-collect-the-values].

**In code**
```yaml
provider:
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
Add `cloud-sql-python-connector[pg8000]` to `requirements.txt`, and connect in the handler with `Connector().connect(...)` as in the guide, taking the password from `ctx.env[db["password_env"]]` [docs/resource-guides/gcp/database.md#4-use-it-in-a-handler].

**In studio**
1. **Resources** → **+ Add resource** → type database, *Mode* *External / existing*.
2. Add the connection values (`password_env` holds the variable name `ORDERS_DB_PASSWORD`, never the password), set *Bound functions* to `api`, then **Save**.

**In the terminal**
```bash
pskit validate
pskit resources send --list
```"""),

    A(626, provider="gcp", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{GDB}#troubleshooting"],
      user="Cloud SQL Admin API has not been used in project my-project before or it is disabled.\n\nfrom our api function logs, right after the first request",
      steps=[S("search_docs", query="Cloud SQL Admin API has not been used",
               docs=[D(GDB, "troubleshooting")])],
      final="""The Cloud SQL Python Connector calls the Cloud SQL Admin API, and it isn't enabled in the project [docs/resource-guides/gcp/database.md#troubleshooting].

1. In the console, enable the **Cloud SQL Admin API** for `my-project`.
2. Wait a minute and send the request again. No redeploy is needed.

If the next error is `403 ... cloudsql.instances.get`, grant **Cloud SQL Client** to the runtime service account."""),

    A(627, provider="gcp", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{GR}#how-pskit-runs-on-google-cloud-why-some-steps-matter", f"{GC}#3-declare-it-in-pskityml"],
      user="On AWS I'd set vpc_config so the function reaches Redis. Can I set a VPC option on a GCP function in pskit for Memorystore?",
      steps=[S("search_docs", query="gcp vpc option memorystore connector",
               docs=[D(GR, "how-pskit-runs-on-google-cloud-why-some-steps-matter", start="- Functions don't run in a VPC")]),
             S("search_docs", query="vpc_connector terraform extra cloud function",
               docs=[D(GC, "3-declare-it-in-pskityml", end="`service_config` and pskit's other settings stay.", words=380)])],
      final="""No, pskit has no VPC option on GCP. Memorystore only has private IPs, so you need a **Serverless VPC Access connector** (created in the console) and add it to the function through `provider.terraform.extra` [docs/resource-guides/gcp/README.md#how-pskit-runs-on-google-cloud-why-some-steps-matter].

**In code**
```yaml
provider:
  terraform:
    extra:
      resource:
        google_cloudfunctions2_function:
          api:
            service_config:
              vpc_connector: projects/my-project/locations/europe-west1/connectors/pskit-conn
              vpc_connector_egress_settings: PRIVATE_RANGES_ONLY
```
`terraform.extra` is deep-merged, so these keys are added and pskit's other settings stay [docs/resource-guides/gcp/cache.md#3-declare-it-in-pskityml].

**In the terminal**
Check the label first: run `pskit package` and look up `google_cloudfunctions2_function` in `.pskit/gcp-dev/main.tf.json`. A function with several triggers is split into several Cloud Functions with other labels."""),

    A(628, provider="gcp", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=[f"{GC}#3-declare-it-in-pskityml"],
      user="why not just functions.api.options.service_config.vpc_connector on gcp?",
      steps=[S("search_docs", query="functions options service_config replaces",
               docs=[D(GC, "3-declare-it-in-pskityml", start="Don't use `functions.<fn>.options.service_config`")])],
      final="""Because function `options` **replace** top-level keys: your `service_config` would drop the one pskit generates, with memory, timeout and environment variables [docs/resource-guides/gcp/cache.md#3-declare-it-in-pskityml].

Use `provider.terraform.extra.resource.google_cloudfunctions2_function.<label>.service_config` instead; it is deep-merged."""),

    A(629, provider="gcp", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{GX}#firestore"],
      user="how to use firestore from my gcp function with pskit? need api key?",
      steps=[S("search_docs", query="firestore gcp custom resource",
               docs=[D(GX, "firestore", words=230)])],
      final="""No key. Google client libraries authenticate as the function's service account; grant it **Cloud Datastore User** (console: IAM & Admin → IAM → Grant access) [docs/resource-guides/gcp/custom.md#firestore].

**In code**
```yaml
resources:
  orders-store:
    type: custom
    external: true
    connection:
      database: (default)
      collection: orders
```
```python
from __future__ import annotations

from google.cloud import firestore
from py_serverless_kit import resource


def api(event, ctx):
    c = resource("orders-store")
    db = firestore.Client(project=ctx.env["PSKIT_GCP_PROJECT"], database=c["database"])
    db.collection(c["collection"]).document("1").set({"total": 10})
    return db.collection(c["collection"]).document("1").get().to_dict()
```
Add `google-cloud-firestore` to `requirements.txt`.

**In studio**
1. **Resources** → **+ Add resource** → type custom, *External / existing*.
2. **Add connection value** for `database` and `collection`, then **Save**."""),

    A(630, provider="gcp", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{GR}#how-pskit-runs-on-google-cloud-why-some-steps-matter"],
      user="Which identity do our Cloud Functions run as, and how do we make them use our own orders-runtime@my-project.iam.gserviceaccount.com instead?",
      steps=[S("search_docs", query="gcp runtime service account default compute",
               docs=[D(GR, "how-pskit-runs-on-google-cloud-why-some-steps-matter", start="- Functions run as", end="don't rely on it.")])],
      final="""Without settings they run as the project's **default compute service account** (`<project number>-compute@developer.gserviceaccount.com`). Set `provider.options.service_account` to use your own [docs/resource-guides/gcp/README.md#how-pskit-runs-on-google-cloud-why-some-steps-matter].

**In code**
```yaml
provider:
  name: gcp
  options:
    project: my-project
    service_account: orders-runtime@my-project.iam.gserviceaccount.com
```

**In studio**
1. Open **Overview & provider**.
2. Fill in *Service account* with the email, then click **Save**.

Grant that account the roles it needs (Pub/Sub Publisher, Storage Object User, ...) in the console; pskit grants none for resources."""),
]
