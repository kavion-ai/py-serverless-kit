"""Category C (fix a validation error), batch 4. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def C(n, **kw):
    return dict(id=f"c_fix-{n:04d}", category="c_fix", **kw)


def handlers(*names):
    """A tiny handler module with the given function names (scaffolding only)."""
    body = FUTURE
    for name in names:
        body += f"\ndef {name}(event, ctx):\n    return {{\"ok\": True, \"fn\": \"{name}\"}}\n\n"
    return body.rstrip() + "\n"


CONVERSATIONS = [
    # ------------------------------------------------------------------ 61  queue on alibaba -> disable there
    C(61, provider="alibaba", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#alibaba-function-compute-30", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=dict(files={
          "pskit.yml": """service: shop-events
provider:
  name: gcp
  region: asia-east1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, shop-events-dev}
providers:
  alibaba:
    region: cn-hongkong
functions:
  orders-api:
    handler: app.shop.orders_api
    events:
      - http: POST /orders
  stock-sync:
    handler: app.shop.stock_sync
    events:
      - queue: stock-updates
""",
          "app/__init__.py": "",
          "app/shop.py": handlers("orders_api", "stock_sync")}),
      user="we also want deploy to alibaba for china customer. deploy page validate red on stock-sync. gcp is working fine",
      steps=[
          S("get_validation"),
          S("search_docs", query="alibaba function compute queue limits",
            docs=[D("docs/providers.md", "alibaba-function-compute-30", start="**Limits:**")]),
          S("ask_user", question="Alibaba has no queue trigger in pskit, so `stock-sync` can't run there. What should I do?",
            options=["Skip `stock-sync` on Alibaba only (GCP unchanged)", "Change its trigger on Alibaba to a topic (MNS)"],
            answer="Skip `stock-sync` on Alibaba only (GCP unchanged)"),
          S("propose_plan", steps=["Add `providers.alibaba.functions.stock-sync.enabled: false`",
                                   "Validate for alibaba"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.alibaba.functions.stock-sync.enabled", value=False),
      ],
      final="""Alibaba Function Compute has no queue events in pskit [docs/providers.md#alibaba-function-compute-30].

As you chose, `stock-sync` is now switched off only on Alibaba:

```yaml
providers:
  alibaba:
    region: cn-hongkong
    functions:
      stock-sync: {enabled: false}
```

Validate for alibaba: valid, with one WARNING that `stock-sync` is disabled (not deployed). GCP is not changed, `stock-sync` still runs there with the Pub/Sub trigger."""),

    # ------------------------------------------------------------------ 62  queue on digitalocean -> http
    C(62, provider="digitalocean", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#digitalocean-functions"],
      project=dict(files={
          "pskit.yml": """service: sms-sender
provider:
  name: digitalocean
  region: sfo3
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE, fn-00000000-0000-0000-0000-000000000000}
functions:
  send-sms:
    handler: app.sms.send
    events:
      - queue: outgoing-sms
""",
          "app/__init__.py": "",
          "app/sms.py": FUTURE + """

def send(event, ctx):
    if event.is_http:
        msg = event.http.json()
        return {"queued": False, "sent_to": msg.get("to")}
    return {"sent": len(event.records)}
"""}),
      user="On DigitalOcean staging, validation rejects the `queue` trigger of `send-sms`. Our backend can just POST to it directly, and the handler already handles HTTP (it checks `event.is_http`). Please replace the queue with `POST /sms` and test it.",
      steps=[
          S("get_validation"),
          S("read_file", path="app/sms.py"),
          S("propose_plan", steps=["Replace the `send-sms` trigger `queue: outgoing-sms` with `http: POST /sms`",
                                   "Validate for digitalocean, stage staging",
                                   "Call `send-sms` locally with POST /sms {\"to\": \"+15550100\"}"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send-sms.events", value=[{"http": "POST /sms"}]),
          S("invoke_local", function="send-sms", method="POST", path="/sms", data={"to": "+15550100"}),
      ],
      final="""DigitalOcean Functions support only `http` and `schedule` in pskit, so the queue trigger can't work there [docs/providers.md#digitalocean-functions].

`send-sms` now has `- http: POST /sms`; handler unchanged.
- `pskit validate -p digitalocean -s staging`: no errors (only the `doctl` not-installed WARNING).
- Local POST /sms with `{"to": "+15550100"}`: status 200, `{"queued": false, "sent_to": "+15550100"}`.

Note that `auth` must be `none` on DigitalOcean, so this route is public. Have the backend send a shared token and check it in the handler."""),

    # ------------------------------------------------------------------ 63  queue on ibm -> switch provider
    C(63, provider="ibm", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/providers.md#ibm-code-engine-functions", "docs/providers.md#providers"],
      project=dict(files={
          "pskit.yml": """service: newsletter
provider:
  name: ibm
functions:
  subscribe:
    handler: app.news.subscribe
    events:
      - http: POST /subscribe
  send-batch:
    handler: app.news.send_batch
    events:
      - queue: newsletter-batches
""",
          "app/__init__.py": "",
          "app/news.py": handlers("subscribe", "send_batch")}),
      user="I picked IBM because I have free credits, but validate says send-batch can't work. Can IBM do queues at all?",
      steps=[
          S("get_validation"),
          S("search_docs", query="ibm code engine triggers http only",
            docs=[D("docs/providers.md", "ibm-code-engine-functions", start="**Limits:**")]),
          S("ask_user", question="No: on IBM pskit supports only HTTP. What would you like?",
            options=["Move the whole project to AWS (it has queues)",
                     "Stay on IBM and make send-batch an HTTP route"],
            answer="Move the whole project to AWS (it has queues)"),
          S("propose_plan", steps=["Set `provider.name` to `aws` (default region us-east-1)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.name", value="aws", run_provider="aws"),
      ],
      final="""No. IBM Code Engine functions in pskit are HTTP only: no schedule, queue, storage or topic triggers [docs/providers.md#ibm-code-engine-functions].

As you chose, the project now targets AWS: `provider.name: aws`. Validate for aws: valid. On AWS `send-batch` gets an SQS queue `newsletter-batches`.

Two things to do:
1. Switch the provider select in the top bar to **aws** too, so studio validates and deploys for AWS.
2. Set up AWS credentials on **Setup & credentials** (AWS credentials) before you deploy."""),

    # ------------------------------------------------------------------ 64  queue on tencent -> invoke-only
    C(64, provider="tencent", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#events-triggers", "docs/providers.md#tencent-serverless-cloud-function-scf"],
      project=dict(files={
          "pskit.yml": """service: render-farm
provider:
  name: tencent
  region: ap-chengdu
functions:
  submit:
    handler: app.render.submit
    events:
      - http: POST /render
  render-frame:
    handler: app.render.render_frame
    timeout: 600
    events:
      - queue: frames
""",
          "app/__init__.py": "",
          "app/render.py": handlers("submit", "render_frame")}),
      user="tencent prod: drop the queue trigger on render-frame, submit calls it via invoke() anyway",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `functions.render-frame.events` (invoke-only function)",
                                   "Validate for tencent, stage prod"]),
          S("set_config", path="functions.render-frame.events", value=None),
      ],
      final="""Tencent SCF has no queue events in pskit [docs/providers.md#tencent-serverless-cloud-function-scf]. Removed `render-frame.events`: a function with no events is invoke-only, callable from `invoke()` and workflows [docs/events.md#events-triggers]. `pskit validate -p tencent -s prod`: valid."""),

    # ------------------------------------------------------------------ 65  topic on oracle -> enabled false
    C(65, provider="oracle", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/providers.md#oracle-oci-functions", "docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: claims
provider:
  name: oracle
  region: uk-london-1
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID, ocid1.compartment.oc1..aaaa}
    subnet_ids:
      - ${env:OCI_SUBNET_ID, ocid1.subnet.oc1..aaaa}
    image: ${env:OCI_IMAGE, lhr.ocir.io/mytenancy/claims:1.0}
functions:
  upload-claim:
    handler: app.claims.upload
    events:
      - storage: claim-files
  notify-adjuster:
    handler: app.claims.notify
    events:
      - topic: claim-events
""",
          "app/__init__.py": "",
          "app/claims.py": handlers("upload", "notify")}),
      user="""claims -> Oracle Cloud Functions [experimental] stage=dev region=uk-london-1
  2 function(s), 0 workflow(s)
  ERROR: [functions.notify-adjuster] Oracle Cloud Functions does not support `topic` events in pskit (supported: http, storage)

notify-adjuster isn't ready anyway, can I keep it in the file but not deploy it for now?""",
      steps=[
          S("get_validation"),
          S("search_docs", query="enabled false keep function skip deploy",
            docs=[D("docs/configuration.md", "functions", start="| `enabled` |", end="| `enabled` |")]),
          S("propose_plan", steps=["Set `functions.notify-adjuster.enabled: false` (kept in the file, skipped on deploy)",
                                   "Validate for oracle"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.notify-adjuster.enabled", value=False),
      ],
      final="""Yes. `enabled: false` keeps the function in pskit.yml and skips it on deploy [docs/configuration.md#functions].

Set `notify-adjuster.enabled: false`. `pskit validate -p oracle`: valid, with a WARNING that `notify-adjuster` is disabled.

When it's ready, remember that OCI has no topic trigger in pskit (only `http` and `storage`) [docs/providers.md#oracle-oci-functions], so it will need an `http` route or a storage event before you enable it."""),

    # ------------------------------------------------------------------ 66  handler module not found (warning)
    C(66, provider="gcp", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(base="examples/01-hello-http", files={
          "pskit.yml": """service: hello-http
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, my-gcp-project}
functions:
  hello:
    handler: app.handler.hello
    events:
      - http: GET /hello
"""}),
      user="validate says valid but there is a yellow warning 'handler module not found'. my file is in the Code page under app. is it a problem?",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Set `functions.hello.handler` to `app.handlers.hello` (the file is app/handlers.py)",
                                   "Validate for gcp",
                                   "Run `hello` locally on GET /hello"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.hello.handler", value="app.handlers.hello"),
          S("invoke_local", function="hello", method="GET", path="/hello"),
      ],
      final="""Yes, it would be a problem: the function would fail when it runs. The handler said `app.handler.hello`, but your file is `app/handlers.py` (with an **s**). The middle part must be the file name without `.py` [docs/configuration.md#functions].

I changed it to `app.handlers.hello`.
- Validate for gcp: valid, and the warning is gone.
- A local test of GET /hello returned status 200 with your greeting.

Test it again anytime with **Test** > **▶ Run locally**."""),

    # ------------------------------------------------------------------ 67  stages.prod override too big
    C(67, provider="aws", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: etl-loader
provider:
  name: aws
  region: eu-north-1
functions:
  load:
    handler: app.etl.load
    timeout: 300
    events:
      - schedule: 1 hour
stages:
  prod:
    functions:
      load:
        timeout: 1200
        memory: 2048
""",
          "app/__init__.py": "",
          "app/etl.py": handlers("load")}),
      user="`pskit validate -s dev` is fine but `-s prod` fails on `load`. In prod the loader handles much more data so I gave it more time and memory in the `stages.prod` block. Fix prod without touching dev.",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Set `stages.prod.functions.load.timeout` to 900 (AWS Lambda max); keep memory 2048",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.functions.load.timeout", value=900),
      ],
      final="""The prod override set `timeout: 1200`, but AWS Lambda allows at most 900 s. Dev keeps 300 s, so only prod failed [docs/providers.md#aws-aws-lambda].

Changed only the prod block: `stages.prod.functions.load.timeout: 900` (`memory: 2048` kept). The top-level 300 s for dev is untouched [docs/configuration.md#stages-per-stage-overrides]. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 68  timeout 0
    C(68, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions", "docs/providers.md#providers"],
      project=dict(files={
          "pskit.yml": """service: report-mail
provider:
  name: azure
  region: centralindia
functions:
  mail-report:
    handler: app.mail.report
    timeout: 0
    events:
      - schedule: "0 7 * * 1"
""",
          "app/__init__.py": "",
          "app/mail.py": handlers("report")}),
      user="i put timeout 0 for mean no limit, validate say must be greater or equal 1",
      steps=[
          S("get_validation"),
          S("search_docs", query="timeout range provider max azure",
            docs=[D("docs/providers.md", "providers", start="| [`azure`]", end="| [`azure`]")]),
          S("ask_user", question="There is no 'no limit'. On Azure the most is 600 s (10 min). How long can the report take?",
            options=["120", "300", "600 (the max)"],
            answer="300"),
          S("propose_plan", steps=["Set `functions.mail-report.timeout` to 300",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.mail-report.timeout", value=300),
      ],
      final="""0 doesn't mean "no limit" in pskit: timeout must be 1-3600 s [docs/configuration.md#functions], and on Azure the max is 600 s [docs/providers.md#providers].

I set `timeout: 300` for `mail-report`, as you chose. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 69  huawei jwt -> iam
    C(69, provider="huawei", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#huawei-functiongraph"],
      project=dict(files={
          "pskit.yml": """service: fleet-api
provider:
  name: huawei
  region: eu-west-101
  options:
    apig_instance_id: ${env:HUAWEI_APIG_INSTANCE_ID, 0123456789abcdef0123456789abcdef}
  iam:
    role: fleet-agency
functions:
  vehicles:
    handler: app.fleet.vehicles
    events:
      - http:
          path: /vehicles
          method: GET
          auth: jwt
          authorizer:
            issuer: https://login.example.com/
            audience: [fleet-api]
""",
          "app/__init__.py": "",
          "app/fleet.py": handlers("vehicles")}),
      user="huawei staging rejects jwt on /vehicles. use IAM instead, drop the authorizer",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.vehicles.events.0.http.auth` to `iam`",
                                   "Delete `functions.vehicles.events.0.http.authorizer`",
                                   "Validate for huawei, stage staging"]),
          S("set_config", path="functions.vehicles.events.0.http.auth", value="iam"),
          S("set_config", path="functions.vehicles.events.0.http.authorizer", value=None),
      ],
      final="""Huawei APIG supports `none`, `iam` and `key` (→ `NONE`/`IAM`/`APP`), not `jwt` [docs/providers.md#huawei-functiongraph]. `/vehicles` is now `auth: iam`, authorizer removed. `pskit validate -p huawei -s staging`: valid."""),

    # ------------------------------------------------------------------ 70  alibaba auth iam -> none
    C(70, provider="alibaba", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#alibaba-function-compute-30"],
      project=dict(files={
          "pskit.yml": """service: points-api
provider:
  name: alibaba
  region: cn-beijing
  iam:
    role: acs:ram::1234567890:role/fc-runtime
functions:
  balance:
    handler: app.points.balance
    events:
      - http:
          path: /balance
          method: GET
          auth: iam
""",
          "app/__init__.py": "",
          "app/points.py": handlers("balance")}),
      user="On AWS this route was AWS_IAM-protected. Alibaba prod validation now says auth iam isn't supported. Is there a RAM-based equivalent in pskit?",
      steps=[
          S("get_validation"),
          S("search_docs", query="alibaba http auth limits",
            docs=[D("docs/providers.md", "alibaba-function-compute-30", start="| Trigger |", end="| http |"),
                  D("docs/providers.md", "alibaba-function-compute-30", start="**Limits:**")]),
          S("propose_plan", steps=["Set `functions.balance.events.0.http.auth` to `none` (the only option on Alibaba)",
                                   "Validate for alibaba, stage prod",
                                   "Then protect /balance with a token check in the handler (separate change)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.balance.events.0.http.auth", value="none"),
      ],
      final="""No RAM equivalent in pskit: on Alibaba every function gets an anonymous HTTP trigger, and `auth` must be `none` [docs/providers.md#alibaba-function-compute-30].

Changed `/balance` to `auth: none`. `pskit validate -p alibaba -s prod`: valid.

The route is **public** now. Before prod traffic, check a token in the handler: put its value in the environment with `${env:BALANCE_API_TOKEN}` and compare it with the request's `Authorization` header. Shall I add that?"""),

    # ------------------------------------------------------------------ 71  resource type bucket
    C(71, provider="onprem", stage="dev", mode="auto", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#fields", "docs/configuration.md#resources"],
      project=dict(files={
          "pskit.yml": """service: scan-store
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8140
resources:
  scans:
    type: bucket
functions:
  on-scan:
    handler: app.scans.on_scan
    events:
      - storage: {resource: scans, suffix: .png}
""",
          "app/__init__.py": "",
          "app/scans.py": handlers("on_scan")}),
      user="resource scans type error, i want a bucket for scan images",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.scans.type` to `storage` (pskit's name for a bucket)",
                                   "Validate for onprem"]),
          S("set_config", path="resources.scans.type", value="storage"),
      ],
      final="""In pskit a bucket is `type: storage`. The allowed types are storage, queue, topic, database, cache, custom and smtp, and `bucket` is not one of them [docs/configuration.md#resources].

I changed `scans` to `type: storage`. Validate for onprem: valid. On-premises the bucket is a folder on the host, and `on-scan` runs for new `.png` files in it."""),

    # ------------------------------------------------------------------ 72  cloudflare auth key
    C(72, provider="cloudflare", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/providers.md#cloudflare-workers"],
      project=dict(files={
          "pskit.yml": """service: edge-webhooks
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, 0123456789abcdef0123456789abcdef}
functions:
  hook:
    handler: app.hooks.receive
    events:
      - http:
          path: /hook
          method: POST
          auth: key
""",
          "app/__init__.py": "",
          "app/hooks.py": handlers("receive")}),
      user="""  ERROR: [functions.hook] auth `key` is not supported on Workers; validate tokens in the handler or use Cloudflare Access

ok so what do I put in pskit.yml?""",
      steps=[
          S("get_validation"),
          S("search_docs", query="cloudflare auth none validate tokens handler",
            docs=[D("docs/providers.md", "cloudflare-workers", start="**Limits:**")]),
          S("propose_plan", steps=["Set `functions.hook.events.0.http.auth` to `none`",
                                   "Validate for cloudflare, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.hook.events.0.http.auth", value="none"),
      ],
      final="""In pskit.yml, `auth: none`: on Workers that is the only value [docs/providers.md#cloudflare-workers]. I changed `/hook` to `auth: none`. `pskit validate -p cloudflare -s prod`: valid (only the Pyodide warning).

The check then moves into code: compare a header such as `x-webhook-token` with `ctx.env["WEBHOOK_TOKEN"]` and reject the request when they differ. Set the value with `environment: {WEBHOOK_TOKEN: ${env:WEBHOOK_TOKEN}}`, never as a literal."""),

    # ------------------------------------------------------------------ 73  catch next -> missing state
    C(73, provider="aws", stage="staging", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#retry-and-catch"],
      project=dict(files={
          "pskit.yml": """service: shipping-flow
provider:
  name: aws
  region: us-east-1
functions:
  book-courier:
    handler: app.ship.book
  alert-ops:
    handler: app.ship.alert
workflows:
  ship:
    start_at: Book
    states:
      Book:
        type: task
        function: book-courier
        retry:
          - errors: [TimeoutError]
            max_attempts: 3
        catch:
          - errors: ["*"]
            next: HandleFailure
        end: true
      AlertOps:
        type: task
        function: alert-ops
        next: Failed
      Failed:
        type: fail
        error: ShippingFailed
""",
          "app/__init__.py": "",
          "app/ship.py": handlers("book", "alert")}),
      user="ship workflow: state 'Book' points to unknown state. catch should go to the ops alert",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.ship.states.Book.catch.0.next` to `AlertOps`",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.ship.states.Book.catch.0.next", value="AlertOps"),
      ],
      final="""The catcher pointed at `HandleFailure`, which doesn't exist; `catch.next` targets are checked like `next` [docs/workflows.md#retry-and-catch]. Now `catch: [{errors: ["*"], next: AlertOps}]`, so after the TimeoutError retries, any error goes AlertOps → Failed. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 74  storage events modified
    C(74, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: csv-checker
provider:
  name: gcp
  region: southamerica-east1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, csv-checker-dev}
functions:
  check-csv:
    handler: app.csv_check.check
    events:
      - storage:
          bucket: csv-inbox
          events: [created, modified]
          suffix: .csv
""",
          "app/__init__.py": "",
          "app/csv_check.py": handlers("check")}),
      user="I want check-csv to run when a csv is added or changed. I wrote created and modified but it says input should be created or deleted?",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage events created deleted",
            docs=[D("docs/events.md", "storage", end="Each record has")]),
          S("propose_plan", steps=["Set `functions.check-csv.events.0.storage.events` to `[created]`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.check-csv.events.0.storage.events", value=["created"]),
      ],
      final="""pskit only knows two storage events: `created` and `deleted` [docs/events.md#storage]. There is no `modified`.

On GCP, `created` becomes the Cloud Storage `finalized` event. If people change a CSV by uploading it again under the same name, test once after deploy that this starts `check-csv` too.

I set `events: [created]`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 75  literal API key (security fix)
    C(75, provider="aws", stage="prod", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#variables", "docs/troubleshooting.md#security-notes"],
      project=dict(files={
          "pskit.yml": """service: checkout
provider:
  name: aws
  region: eu-west-1
functions:
  pay:
    handler: app.pay.charge
    environment:
      PAYMENT_API_KEY: pk_live_demo_123456
      PAYMENT_MODE: live
    events:
      - http: POST /pay
""",
          "app/__init__.py": "",
          "app/pay.py": handlers("charge")}),
      user="In SAM I passed the payment key as a NoEcho parameter. Here I just pasted it into the YAML page under environment and prod validation passes. Before I commit: is that acceptable, and if not, what's the pskit way?",
      steps=[
          S("get_validation"),
          S("search_docs", query="secrets env variables yaml",
            docs=[D("docs/configuration.md", "variables", start="Secrets: don't put them in YAML")]),
          S("propose_plan", steps=["Replace the literal value of `functions.pay.environment.PAYMENT_API_KEY` with `${env:PAYMENT_API_KEY, }`",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.pay.environment.PAYMENT_API_KEY", value="${env:PAYMENT_API_KEY, }"),
      ],
      final="""Not acceptable: validate doesn't check for secrets, so it passed, but the key would be committed with pskit.yml. Don't put secrets in YAML; use `${env:...}` or a secret manager via `${tf:...}` [docs/configuration.md#variables].

Changed to:

```yaml
environment:
  PAYMENT_API_KEY: ${env:PAYMENT_API_KEY, }
  PAYMENT_MODE: live
```

`pskit validate -p aws -s prod`: valid. Export `PAYMENT_API_KEY` on the machine or CI job that runs `pskit deploy`; if it's unset, the value is empty. `${env:...}` resolves at deploy time, so the value still ends up in Terraform state; keep the state private. Rotate the key, since it was in the file."""),

    # ------------------------------------------------------------------ 76  two errors at once, azure
    C(76, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/configuration.md#default-runtime"],
      project=dict(files={
          "pskit.yml": """service: club-booking
provider:
  name: azure
  region: australiaeast
functions:
  courts:
    handler: app.club.courts
    runtime: python3.13
    events:
      - http: GET /courts
  book:
    handler: app.club.book
    events:
      - http:
          path: /book
          method: POST
          auth: iam
""",
          "app/__init__.py": "",
          "app/club.py": handlers("courts", "book")}),
      user="Fix the problems on the Functions page pls, there is 2 red",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["`courts`: remove the pinned `runtime: python3.13` (Azure max is 3.12; pskit then uses python3.12)",
                                   "`book`: change `auth: iam` to `auth: key` (Azure supports none or key)",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.courts.runtime", value=None),
          S("set_config", path="functions.book.events.0.http.auth", value="key"),
      ],
      final="""Both fixed, validate for azure: valid.

1. `courts` had `runtime: python3.13`, but Azure runs up to python3.12. I removed the pin, so pskit uses python3.12 [docs/configuration.md#default-runtime].
2. `book` had `auth: iam`, which Azure doesn't support. It's now `auth: key`, so callers must send the Azure function key [docs/events.md#http]. If you'd rather keep it open, tell me and I'll set `auth: none`."""),

    # ------------------------------------------------------------------ 77  tencent PATCH
    C(77, provider="tencent", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/troubleshooting.md#http"],
      project=dict(files={
          "pskit.yml": """service: profile-edit
provider:
  name: tencent
  region: ap-hongkong
functions:
  get-profile:
    handler: app.profile.get_profile
    events:
      - http: GET /profile/{id}
  update-profile:
    handler: app.profile.update_profile
    events:
      - http: PATCH /profile/{id}
""",
          "app/__init__.py": "",
          "app/profile.py": handlers("get_profile", "update_profile")}),
      user="Tencent rejects `PATCH /profile/{id}` on update-profile. Our mobile app sends PATCH and I can't change it. GET /profile/{id} must stay on get-profile. What's the least invasive fix?",
      steps=[
          S("get_validation"),
          S("search_docs", query="tencent api gateway patch any",
            docs=[D("docs/events.md", "http", start="Provider notes: Tencent")]),
          S("propose_plan", steps=["Change `update-profile` to `method: ANY` on /profile/{id} (Tencent can't route PATCH)",
                                   "Validate for tencent"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.update-profile.events.0.http", value={"path": "/profile/{id}", "method": "ANY"}),
      ],
      final="""Tencent's API Gateway has no `PATCH`; pskit's answer is `ANY` [docs/events.md#http].

Changed `update-profile` to `{path: /profile/{id}, method: ANY}`. `pskit validate -p tencent`: valid, so the mobile app's PATCH reaches `update-profile`.

Check one thing before deploy: `get-profile` keeps `GET` on the same path. pskit accepted both routes, but whether GET goes to the exact `GET` route or to `ANY` on the deployed gateway is not something validate can show. Test it after deploy with a GET and a PATCH. Inside `update-profile` you can check `event.http.method` and reject anything other than PATCH."""),

    # ------------------------------------------------------------------ 78  schedule with rate and cron
    C(78, provider="huawei", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: water-meter
provider:
  name: huawei
  region: cn-east-3
  iam:
    role: meter-agency
functions:
  read-meters:
    handler: app.meters.read_all
    events:
      - schedule:
          rate: 15 minutes
          cron: "0 * * * *"
""",
          "app/__init__.py": "",
          "app/meters.py": handlers("read_all")}),
      user="schedule error 'needs exactly one of rate or cron'. i want every 15 minute, the cron was old",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete the old `cron` from the `read-meters` schedule; keep `rate: 15 minutes`",
                                   "Validate for huawei"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.read-meters.events.0.schedule.cron", value=None),
      ],
      final="""A schedule takes `rate` **or** `cron`, never both [docs/events.md#schedule]. I removed the old `cron: "0 * * * *"`, so `read-meters` has only `rate: 15 minutes`. Validate for huawei: valid. On Huawei pskit makes it a timer trigger with `Rate`."""),

    # ------------------------------------------------------------------ 79  managed storage resource no event uses (alibaba)
    C(79, provider="alibaba", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#troubleshooting", "docs/configuration.md#resources"],
      project=dict(files={
          "pskit.yml": """service: report-export
provider:
  name: alibaba
  region: cn-hangzhou
resources:
  exports:
    type: storage
functions:
  export:
    handler: app.export.run
    events:
      - http: POST /export
""",
          "app/__init__.py": "",
          "app/export.py": handlers("run")}),
      user="I added a bucket called exports on the Resources page so my export function can save files there. On Alibaba it says managed storage resources that no event uses are not supported yet. What does that mean?",
      steps=[
          S("get_validation"),
          S("search_docs", query="managed resources that no event uses not supported",
            docs=[D("docs/resources.md", "troubleshooting", start="| `managed queue resources that no event uses",
                    end="| `managed queue resources that no event uses")]),
          S("ask_user", question="On Alibaba pskit can only create a bucket that a trigger uses. Your `export` function just writes to it, so the bucket has to exist already. What is the name of the OSS bucket to use? (It must already exist.)",
            answer="acme-report-exports"),
          S("propose_plan", steps=["Set `resources.exports.external: true` and `name: acme-report-exports`",
                                   "Validate for alibaba"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.exports", value={"type": "storage", "external": True, "name": "acme-report-exports"}),
      ],
      final="""It means: on Alibaba, pskit only creates a bucket when a trigger (a `storage` event) uses it. Your `export` function only writes files, so pskit can't create `exports` there. You create the bucket yourself and tell pskit to use it [docs/resources.md#troubleshooting].

Now `exports` is:

```yaml
resources:
  exports: {type: storage, external: true, name: acme-report-exports}
```

Validate for alibaba: valid. pskit never creates or deletes an external resource [docs/configuration.md#resources], so the bucket `acme-report-exports` must exist before you deploy."""),

    # ------------------------------------------------------------------ 80  function name with a space
    C(80, provider="digitalocean", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#top-level"],
      project=dict(files={
          "pskit.yml": """service: recipe-box
provider:
  name: digitalocean
  region: lon1
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE, fn-00000000-0000-0000-0000-000000000000}
functions:
  Add Recipe:
    handler: app.recipes.add
    events:
      - http: POST /recipes
""",
          "app/__init__.py": "",
          "app/recipes.py": handlers("add")}),
      user="I called my function 'Add Recipe' and now there's a red error about the name. Can't I use spaces?",
      steps=[
          S("get_validation"),
          S("search_docs", query="function names rules letters digits",
            docs=[D("docs/configuration.md", "top-level", start="| `functions` |", end="| `functions` |")]),
          S("propose_plan", steps=["Rename function `Add Recipe` to `add-recipe` (same handler and route)",
                                   "Validate for digitalocean"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.add-recipe", value={"handler": "app.recipes.add", "events": [{"http": "POST /recipes"}]}),
          S("set_config", path="functions.Add Recipe", value=None),
      ],
      final="""No spaces, sorry. A function name must start with a letter and use only letters, digits, `-` or `_` (max 63) [docs/configuration.md#top-level]. The name becomes part of the cloud function's name.

I renamed it to `add-recipe`. The handler and the `POST /recipes` route stay the same. Validate for digitalocean has no errors now (only the warning that `doctl` isn't installed yet)."""),
]
