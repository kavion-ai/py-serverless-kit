"""Category F (explain a config or handler), batch 3. Hand-written; assembled by tools/assemble.py.

Scope: aws / azure / gcp / onprem only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402,F401

FUTURE = "from __future__ import annotations\n\n"
GCP_OPTS = """  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
"""


def F(n, **kw):
    return dict(id=f"f_explain-{n:04d}", category="f_explain", **kw)


def onprem_yml(service, port, body):
    return f"""service: {service}
provider:
  name: onprem
  region: local
  options: {{host: 127.0.0.1, port: {port}}}
{body}"""


CONVERSATIONS = [
    # ------------------------------------------------------------------ 41 resources example on onprem
    F(41, provider="onprem", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#fields", "docs/resources.md#secrets"],
      project=dict(base="examples/18-resources"),
      user="Explain the resources section of this project and how the orders-db password reaches the code, as it would run on premises.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 42 bindings handler
    F(42, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/resources.md#what-handlers-receive"],
      project=dict(base="examples/18-resources"),
      user="what does the bindings function return? can it leak my db password?",
      steps=[S("read_file", path="app/handlers.py"),
             S("invoke_local", function="api", method="GET", path="/bindings")]),

    # ------------------------------------------------------------------ 43 rest api example on aws
    F(43, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/configuration.md#variables"],
      project=dict(base="examples/02-rest-api"),
      user="many function here. what is custom.cors and why admin-stats different?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 44 storage example on gcp
    F(44, provider="gcp", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#storage"],
      project=dict(base="examples/05-storage-events"),
      user="how do the storage triggers map on gcp",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 45 pubsub example on azure
    F(45, provider="azure", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#topic", "docs/providers.md#azure-azure-functions"],
      project=dict(base="examples/06-pubsub-topic"),
      user="We use SNS fan-out with filter policies today. Explain this topic setup and what happens to the filter on Azure.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 46 remote onprem example
    F(46, provider="onprem", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises", "docs/configuration.md#variables"],
      project=dict(base="examples/17-on-premises-remote"),
      user="this file have many ${env:...}. what happen if i not set them?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 47 redirect tuple handler
    F(47, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": onprem_yml("links", 8101, """functions:
  go:
    handler: app.links.go
    events:
      - http: GET /go/{slug}
"""),
          "app/__init__.py": "",
          "app/links.py": FUTURE + """LINKS = {"docs": "https://docs.example.com", "blog": "https://blog.example.com"}


def go(event, ctx):
    target = LINKS.get(event.http.path_params["slug"])
    if target is None:
        return {"error": "unknown link"}, 404
    return "", 302, {"location": target}
"""}),
      user="why go returns three things with commas? what is 302",
      steps=[S("read_file", path="app/links.py"),
             S("invoke_local", function="go", method="GET", path="/go/docs")]),

    # ------------------------------------------------------------------ 48 aws workflow with parallel + catch
    F(48, provider="aws", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#retry-and-catch"],
      project=dict(files={
          "pskit.yml": """service: claims
provider:
  name: aws
  region: eu-west-1
functions:
  score: {handler: app.claims.score}
  fetch-history: {handler: app.claims.history}
  fetch-policy: {handler: app.claims.policy}
  flag: {handler: app.claims.flag}
workflows:
  assess:
    start_at: Gather
    timeout: 600
    states:
      Gather:
        type: parallel
        branches:
          - start_at: History
            states:
              History: {type: task, function: fetch-history, end: true}
          - start_at: Policy
            states:
              Policy: {type: task, function: fetch-policy, end: true}
        result_path: $.facts
        next: Score
      Score:
        type: task
        function: score
        catch:
          - {errors: [States.ALL], next: Flag, result_path: $.error}
        end: true
      Flag: {type: task, function: flag, end: true}
""",
          "app/__init__.py": "",
          "app/claims.py": FUTURE + "def score(event, ctx):\n    return {\"score\": 1}\n\n\ndef history(event, ctx):\n    return []\n\n\ndef policy(event, ctx):\n    return {}\n\n\ndef flag(event, ctx):\n    return {\"flagged\": True}\n"}),
      user="Walk me through the assess workflow: what runs in parallel, where the results go, and what happens if score throws.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 49 gcp auth iam
    F(49, provider="gcp", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: internal-reports
provider:
  name: gcp
  region: europe-west1
""" + GCP_OPTS + """functions:
  export:
    handler: app.reports.export
    events:
      - http: {path: /export, method: POST, auth: iam}
""",
          "app/__init__.py": "",
          "app/reports.py": FUTURE + "def export(event, ctx):\n    return {\"started\": True}, 202\n"}),
      user="who can call export after deploy?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 50 azure native workflow
    F(50, provider="azure", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/providers.md#azure-azure-functions", "docs/workflows.md#engines"],
      project=dict(files={
          "pskit.yml": """service: approvals
provider:
  name: azure
  region: westeurope
functions:
  check: {handler: app.flow.check}
  notify: {handler: app.flow.notify}
workflows:
  approve:
    engine: native
    start_at: Check
    states:
      Check: {type: task, function: check, next: Notify}
      Notify: {type: task, function: notify, end: true}
""",
          "app/__init__.py": "",
          "app/flow.py": FUTURE + "def check(event, ctx):\n    return {\"ok\": True}\n\n\ndef notify(event, ctx):\n    return {\"sent\": True}\n"}),
      user="engine native on azure what it mean? how i start this workflow",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 51 onprem 7 minute rate
    F(51, provider="onprem", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": onprem_yml("sensors", 8102, """functions:
  poll:
    handler: app.sensors.poll
    events:
      - schedule: {rate: 7 minutes, input: {site: plant-2}}
providers:
  aws:
    region: eu-central-1
"""),
          "app/__init__.py": "",
          "app/sensors.py": FUTURE + "def poll(event, ctx):\n    return {\"site\": event.data[\"site\"]}\n"}),
      user="EventBridge accepted rate(7 minutes) for us. Explain this schedule here, and is 7 minutes a problem anywhere?",
      steps=[S("get_project"), S("validate"), S("validate", provider="aws")]),

    # ------------------------------------------------------------------ 52 onprem embedded workflow with wait
    F(52, provider="onprem", stage="staging", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#embedded-orchestrator", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("reminders", 8103, """functions:
  send-first: {handler: app.remind.first}
  send-second: {handler: app.remind.second}
workflows:
  remind:
    start_at: First
    states:
      First: {type: task, function: send-first, next: Later}
      Later: {type: wait, seconds: 86400, next: Second}
      Second: {type: task, function: send-second, end: true}
"""),
          "app/__init__.py": "",
          "app/remind.py": FUTURE + "def first(event, ctx):\n    return {\"first\": True}\n\n\ndef second(event, ctx):\n    return {\"second\": True}\n"}),
      user="my workflow waits one day. will it break because of the timeout?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 53 aws arch, retention, tags
    F(53, provider="aws", stage="prod", mode="ask", page="Overview", persona="terse_expert",
      sources=["docs/configuration.md#provider"],
      project=dict(files={
          "pskit.yml": """service: geo
provider:
  name: aws
  region: ap-southeast-2
  architecture: arm64
  log_retention_days: 30
  tags:
    team: maps
    cost-center: "4410"
functions:
  lookup:
    handler: app.geo.lookup
    memory: 512
    events:
      - http: GET /geo/{ip}
""",
          "app/__init__.py": "",
          "app/geo.py": FUTURE + "def lookup(event, ctx):\n    return {\"ip\": event.http.path_params[\"ip\"]}\n"}),
      user="explain provider block. anything to watch with arm64?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 54 gcp schedule-only timeout 900
    F(54, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: warehouse
provider:
  name: gcp
  region: us-east1
""" + GCP_OPTS + """functions:
  nightly-load:
    handler: app.load.run
    timeout: 900
    events:
      - schedule: "0 1 * * *"
""",
          "app/__init__.py": "",
          "app/load.py": FUTURE + "def run(event, ctx):\n    return {\"loaded\": 0}\n"}),
      user="Explain what nightly-load is configured to do, and confirm the 15-minute timeout is acceptable on Cloud Functions.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 55 azure app-wide env conflict
    F(55, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: azure
  region: westeurope
functions:
  cart:
    handler: app.shop.cart
    environment:
      CACHE_TTL: "60"
    events:
      - http: GET /cart
  catalog:
    handler: app.shop.catalog
    environment:
      CACHE_TTL: "3600"
    events:
      - http: GET /catalog
""",
          "app/__init__.py": "",
          "app/shop.py": FUTURE + "import os\n\n\ndef cart(event, ctx):\n    return {\"ttl\": os.environ.get(\"CACHE_TTL\")}\n\n\ndef catalog(event, ctx):\n    return {\"ttl\": os.environ.get(\"CACHE_TTL\")}\n"}),
      user="each function has own CACHE_TTL. that works right?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 56 onprem unresolved env
    F(56, provider="onprem", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": onprem_yml("crm-sync", 8104, """functions:
  sync:
    handler: app.crm.sync
    environment:
      CRM_URL: https://crm.example.com/api
      CRM_TOKEN: ${env:CRM_SYNC_TOKEN_XYZ}
    events:
      - schedule: 30 minutes
"""),
          "app/__init__.py": "",
          "app/crm.py": FUTURE + "import os\n\n\ndef sync(event, ctx):\n    return {\"url\": os.environ[\"CRM_URL\"]}\n"}),
      user="""what does this config do? studio shows
Error: unresolved variables: env:CRM_SYNC_TOKEN_XYZ""",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 57 aws worker swallowing errors
    F(57, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: emails
provider:
  name: aws
  region: us-west-2
functions:
  sender:
    handler: app.sender.run
    events:
      - queue: {name: outgoing, dead_letter: outgoing-dlq, max_receive: 4}
""",
          "app/__init__.py": "",
          "app/sender.py": FUTURE + """

def run(event, ctx):
    for record in event.records:
        try:
            mail = record.json()
            if "@" not in mail["to"]:
                raise ValueError("bad address")
            ctx.logger.info("sent", extra={"to": mail["to"]})
        except Exception:
            ctx.logger.exception("send failed")
"""}),
      user="explain sender. my dlq is always empty, even when mails fail",
      steps=[S("read_file", path="app/sender.py"),
             S("invoke_local", function="sender", type="queue", data=[{"to": "ok@example.com"}, {"to": "broken"}])]),

    # ------------------------------------------------------------------ 58 gcp context fields
    F(58, provider="gcp", stage="staging", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: diag
provider:
  name: gcp
  region: asia-northeast1
""" + GCP_OPTS + """functions:
  whoami:
    handler: app.diag.whoami
    events:
      - http: GET /whoami
""",
          "app/__init__.py": "",
          "app/diag.py": FUTURE + """

def whoami(event, ctx):
    return {
        "function": ctx.function,
        "service": ctx.service,
        "stage": ctx.stage,
        "provider": event.provider,
        "request_id": ctx.request_id,
    }
"""}),
      user="In Lambda I'd read context.function_name and aws_request_id. Explain what whoami reads and what each value will be.",
      steps=[S("read_file", path="app/diag.py"),
             S("invoke_local", function="whoami", method="GET", path="/whoami")]),

    # ------------------------------------------------------------------ 59 azure storage deleted
    F(59, provider="azure", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: docs-index
provider:
  name: azure
  region: eastus
functions:
  index:
    handler: app.index.handle
    events:
      - storage: {bucket: documents, events: [created, deleted], suffix: .pdf}
""",
          "app/__init__.py": "",
          "app/index.py": FUTURE + "def handle(event, ctx):\n    return {\"n\": len(event.records)}\n"}),
      user="explain index trigger + check azure",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 60 onprem runtime mismatch local
    F(60, provider="onprem", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: legacy-api
provider:
  name: onprem
  region: local
  runtime: python3.9
  options: {host: 127.0.0.1, port: 8105}
functions:
  ping:
    handler: app.api.ping
    events:
      - http: GET /ping
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + "def ping(event, ctx):\n    return {\"pong\": True}\n"}),
      user="We pinned python3.9 because production servers run it. Explain what this config deploys locally and which Python actually runs it.",
      steps=[S("get_project"), S("validate")]),
]

FINALS = {
    41: """`resources:` lists four services the functions use [docs/resources.md#fields]. Validate for onprem: valid.

| Key | Type | Managed or external |
|---|---|---|
| `uploads` | storage | managed: pskit creates the bucket `resources-demo-uploads-1234` |
| `jobs` | queue | managed; `worker` reads it through `queue: {resource: jobs}` |
| `notifications` | topic | managed; the worker publishes to it |
| `orders-db` | database | `external: true`: pskit never creates or touches it, it only passes on `connection` |

`orders-db` is bound only to `api` and `worker` (`functions: [api, worker]`). On premises, `providers.onprem` adds the host and port 8090, and the managed queue, bucket and topic become folders on the host.

**The password**: it is never in pskit.yml. `connection` holds `password_env: ORDERS_DB_PASSWORD`, which is the *name* of a variable. The handler reads `resource("orders-db")`, takes that name, and looks the value up in its environment at run time. Connection values are stored in Terraform state and, on premises, in `pskit_host.json`, which is why only the variable name goes there [docs/resources.md#secrets]. For on-prem, put `ORDERS_DB_PASSWORD` in the environment of the host, for example through `options.env_file`.""",

    42: """`bindings` returns, for every resource bound to the function, four things: its type, its native name, whether it's external, and the **names** of its connection settings (`sorted(res.connection)` sorts the keys only).

The local run of `GET /bindings` returned 200 with:
- `uploads`: storage, native name `resources-demo-uploads-1234`
- `jobs`: queue; `notifications`: topic
- `orders-db`: database, external, settings `database`, `host`, `password_env`, `port`

So no, it can't leak the password. Even `password_env` only holds the variable name `ORDERS_DB_PASSWORD`, and the function shows the key name, not the value. pskit passes each binding as `PSKIT_RESOURCE_<KEY>_...` environment variables, and `pskit invoke` sets the same ones locally [docs/resources.md#what-handlers-receive]. The real password is read only inside `_dsn()`, which `worker` uses to connect and never returns.""",

    43: """It's a books REST API with 9 HTTP functions on AWS. Validate: valid.

**`custom.cors`**: `custom` is a place for your own values. `cors` there lists the allowed browser origins (`https://books.example.com` and `http://localhost:5173`) and allows credentials. The five `/books` routes reuse it with `cors: "${self:custom.cors}"`, so the list is written once [docs/configuration.md#variables].

**Why `admin-stats` is different**: it's the only route with `auth: jwt`. On AWS, API Gateway checks the JWT (issuer and audience from env variables, with defaults) before the function runs. JWT auth is AWS only [docs/events.md#http]. So the `providers:` block restates `admin-stats` with a plain `GET /admin/stats` for gcp, azure and onprem. There the route is public, and the handler itself refuses requests without an `authorization` header (`Unauthorized`).

The other routes (`cover`, `docs`, `session`) are plain public routes.""",

    44: """Validate for gcp: valid, 3 functions. On GCP, buckets are Cloud Storage buckets and events arrive through Eventarc [docs/events.md#storage]:

- `import-csv`: **created** objects in the bucket `${DATA_BUCKET}-dev` (or the demo default). On GCP the `incoming/` prefix and `.csv` suffix are applied by pskit's runtime, not by the trigger.
- `purge-index`: **deleted** objects in the same bucket.
- `audit-existing`: `existing: true` on a shared bucket, both created and deleted. `created` and `deleted` become **separate deployments** on GCP.

The `providers.gcp` block only sets region `us-central1` and the project. Unlike Azure, nothing is switched off, because GCP supports delete events.""",

    45: """Two functions subscribe to the topic `order-events`, which is fan-out: each one gets every message [docs/events.md#topic].

- `update-analytics`: no filter, gets everything.
- `notify-customer`: `filter: {event_type: ["order.shipped"]}`. On AWS that's an SNS filter policy on message attributes.

On Azure the topic is a Service Bus topic with one subscription per function. The filter is **not** applied there. Validate for azure is valid, with a warning:
`topic.filter is not applied on Azure Service Bus subscriptions`

So on Azure `notify-customer` would receive every event. That's safe here, because `app/subscribers.py` checks `event_type` again in code (`_wants()`) and skips the others [docs/providers.md#azure-azure-functions]. Keep that check in the handler whenever you rely on a filter.""",

    46: """Each `${env:NAME, default}` reads the variable on the machine that runs pskit. If it isn't set, the value after the comma is used [docs/configuration.md#variables]. Validate for onprem: valid, so all of them have defaults:

| Variable | Not set → |
|---|---|
| `PSKIT_ONPREM_URL` | `advertise: http://127.0.0.1:8090` |
| `PSKIT_ONPREM_HOST` | `deploy.host: 127.0.0.1` (SSH to this machine) |
| `PSKIT_ONPREM_USER` | `user: pskit` |
| `PSKIT_SSH_KEY` | empty `identity_file`: the SSH agent or default key is used |
| `GOOGLE_CLOUD_PROJECT`, `ARM_SUBSCRIPTION_ID` | demo values, only for gcp/azure |

So unset, a deploy would SSH to `pskit@127.0.0.1`, which is probably not what you want. Set at least `PSKIT_ONPREM_HOST` to your server before deploying.

The rest of the config: `hello` on `GET /hello` and `tick` every hour, on port 8090, installed under `/opt/pskit/factory-api` with a bundled Python and a systemd unit [docs/providers.md#onprem-on-premises].

A `${env:NAME}` **without** a default would fail validate with `unresolved variables` when it's unset.""",

    47: """A handler can return a tuple `(body, status, headers)`; pskit turns it into the HTTP answer [docs/handlers.md#returning-a-response]:

- `{"error": "unknown link"}, 404`: JSON body with status 404 (not found).
- `"", 302, {"location": target}`: empty body, status **302**, and a `location` header.

302 means "found, go over there": the browser follows `location` to the real site. That's how a link shortener works.

The local run of `GET /go/docs` returned status 302 with `location: https://docs.example.com` and no body. An unknown slug gets the 404 JSON.""",

    48: """Validate for aws/staging: valid. `assess` runs as a Step Functions state machine (`native engine`), with a 600 s limit for the whole run.

1. **Gather** (`parallel`): two branches run at the same time [docs/workflows.md#state-types]. One calls `fetch-history`, the other `fetch-policy`. When both finish, their outputs are put together as a list at `$.facts` (`result_path`), next to the original input.
2. **Score** (task `score`): gets the input plus `facts`.
3. If `score` raises any error, `catch` with `States.ALL` sends the run to **Flag**, and the error details are stored at `$.error` [docs/workflows.md#retry-and-catch]. Without an error, Score ends the run.
4. **Flag** (task `flag`) ends the run, so a failed score still ends as a **succeeded** run that has been flagged.

There's no `retry` on Score, so one failure goes straight to Flag. Try it locally with `pskit workflow run assess -i '{"claim_id": 1}'`.""",

    49: """`export` is `POST /export` with `auth: iam`. On GCP that means pskit does **not** add the public `allUsers` invoker binding [docs/events.md#http]:

- Anonymous calls are refused by Google before your code runs.
- A caller needs a Google identity that you allow to invoke this function in your project's IAM.

pskit's own Scheduler, Eventarc and Workflows use a dedicated invoker service account it creates [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

Validate for gcp/prod: valid.""",

    50: """`engine: native` on Azure means the `approve` workflow is deployed as an **Azure Logic App** (Consumption) instead of pskit's embedded orchestrator function. Validate for azure: valid, `workflow approve: native engine` [docs/workflows.md#engines].

- **Check** calls `check`, then **Notify** calls `notify`.
- Each task calls `POST /_pskit/invoke/<function>` on your Function App with the function key, so `check` and `notify` get that route automatically.

**How to start it** [docs/providers.md#azure-azure-functions]: after deploy, `pskit info` shows the workflow `url`, the Logic App's HTTP trigger. Send a `POST` there with the JSON input. That URL contains a SAS signature, so keep it secret like a password.

Locally you can try it any time with `pskit workflow run approve -i '{"id": 1}'`.""",

    51: """`poll` runs every 7 minutes and gets `{site: plant-2}` as `event.data`; the handler returns the site. On premises the in-process scheduler takes any positive rate, including ones that aren't cron-shaped [docs/events.md#schedule].

I checked both targets:
- onprem: valid.
- aws (`providers.aws`, eu-central-1): valid, as you saw with EventBridge: `rate(7 minutes)`.

Where it would be a problem: on cron-only clouds, the docs say 7 minutes can't be written as cron and fails validation; use a divisor of 60 minutes (5, 10, 15...) there. That doesn't apply to onprem or aws.""",

    52: """No. Validate for onprem/staging is valid, with `workflow remind: embedded engine`.

`remind` runs `send-first`, waits 86400 s (one day) in **Later**, then runs `send-second`.

On premises the embedded engine runs **inside the host process**, not inside a function call. So a workflow isn't cut off by a function timeout, and a one-day wait is fine [docs/providers.md#onprem-on-premises]. The host tracks the run: `POST /workflows/remind` answers 202 with an `execution_id` right away, and you can list, follow or cancel runs [docs/workflows.md#embedded-orchestrator].

On a cloud with the embedded engine this wouldn't fit, because the whole run must fit in one invocation (900 s on AWS, for example). There you'd use a native engine. One more on-prem detail: since the first state is a task, calling `send-first` on its own also starts a run; set `options.start_on_entry: false` on the workflow if you don't want that.""",

    53: """Validate for aws/prod: valid. The provider block [docs/configuration.md#provider]:

- `region: ap-southeast-2` (Sydney).
- `architecture: arm64`: Lambdas run on Graviton (ARM) instead of x86_64.
- `log_retention_days: 30`: CloudWatch keeps logs 30 days (default 14).
- `tags`: `team: maps` and `cost-center: "4410"` go on every resource, next to pskit's own `pskit-service` / `pskit-stage` tags. The quotes keep `4410` a string.

`lookup` (`GET /geo/{ip}`) has its own `memory: 512`; the rest use the defaults.

**Watch with arm64**: your dependencies. pskit installs manylinux wheels for the chosen architecture into the zip, so packages with compiled code need an `arm64` (aarch64) wheel. A package without one won't install or won't import. Pure-Python packages are fine.""",

    54: """`nightly-load` runs every day at 01:00 UTC (`0 1 * * *`) with a 900 s timeout. Validate for gcp: **valid**, so 15 minutes is accepted.

The reason is how GCP schedules work [docs/providers.md#gcp-google-cloud-functions-2nd-gen]: Cloud Scheduler calls the function over HTTP (an OIDC POST). So it's an HTTP function, which can run up to 3600 s. The 540 s limit applies to **event-triggered** functions: queue, storage and topic.

If you ever add a queue or storage trigger to `nightly-load`, the 900 s timeout would no longer be valid for that trigger. Keep the long load as a schedule-only function.""",

    55: """No, not on Azure. Validate for azure is valid, but with a warning:
`environment CACHE_TTL differs between functions; Azure app settings are shared by the whole Function App (last one wins)`

On Azure, one Function App hosts every function of the service, and `environment` is app-wide [docs/providers.md#azure-azure-functions]. So `cart` and `catalog` would both see the same `CACHE_TTL`, whichever value wins, not 60 and 3600.

Fix: use two names, for example `CART_CACHE_TTL: "60"` and `CATALOG_CACHE_TTL: "3600"`, and read the right one in each handler. On aws, gcp and onprem, per-function values work as written. Want me to rename them?""",

    56: """The config runs one function, `sync`, every 30 minutes on premises (port 8104). It gets `CRM_URL` and `CRM_TOKEN` as environment variables.

The error comes from `CRM_TOKEN: ${env:CRM_SYNC_TOKEN_XYZ}`. Validate fails with the same message:
`Error: unresolved variables: env:CRM_SYNC_TOKEN_XYZ`

`${env:NAME}` without a default must be set in the environment of the process running pskit (studio included); otherwise the whole file can't load [docs/configuration.md#variables]. Two fixes:

1. Set it: in studio, **Setup & credentials** > Environment variables > **Set for this session**, or export the variable in your shell before running `pskit`.
2. Or allow it to be empty: `${env:CRM_SYNC_TOKEN_XYZ, }`. Then `sync` must cope with an empty token.

Keeping the token in an env variable is right; don't paste it into pskit.yml.""",

    57: """`sender` reads each mail from the `outgoing` queue, checks the address, and logs `sent`. Any error is caught by `except Exception` and only logged.

That's why your DLQ is empty. The handler **never fails**: it swallows the error, returns nothing, and SQS counts every message as done. My local run shows it: `ok@example.com` was sent, `broken` logged `send failed` with `ValueError: bad address`, and the result was `null`, so no message was marked as failed.

To let failures be retried and, after `max_receive: 4`, land in `outgoing-dlq`, report them with `BatchResult` [docs/handlers.md#batchresult]:

```python
result = BatchResult()
...
        except Exception:
            ctx.logger.exception("send failed")
            result.fail(record)
return result
```

Want me to apply it and run the same two messages again?""",

    58: """`whoami` returns five values. pskit's names for the Lambda ones [docs/handlers.md#context]:

| Returns | Lambda equivalent | Local run |
|---|---|---|
| `ctx.function` | `function_name` (but the pskit name) | `whoami` |
| `ctx.service` | none | `diag` |
| `ctx.stage` | none | `staging` |
| `event.provider` | none | `local` |
| `ctx.request_id` | `aws_request_id` | a UUID |

`event.provider` is `local` under `pskit invoke`, and `gcp` once deployed. `ctx.request_id` is the platform request id there, or a UUID when the platform has none. The function name is the pskit name from pskit.yml on every cloud, so you don't need to parse prefixed cloud names.""",

    59: """`index` should run for `.pdf` files in the container `documents`, when they're **created** or **deleted**.

Validate for azure fails:
`Azure blob triggers only fire on created/updated blobs`

Azure has no blob-deleted trigger, so `deleted` can't work there [docs/events.md#storage]. Options:
1. Use `events: [created]` on Azure (or `providers.azure.functions.index.events` if the same file also targets another cloud).
2. If deletes matter, run `index` on aws, gcp or onprem, which support both.""",

    60: """It runs one function, `ping` on `GET /ping`, as a process on this machine at `127.0.0.1:8105`. Validate for onprem: valid, with a warning:

`the host runs with this interpreter (python3.12), not python3.9. Use the same Python for pskit deploy and the functions, or set options.deploy.python: bundle.`

With the default `method: local`, the host uses the interpreter that runs pskit, which is 3.12 here. `runtime: python3.9` doesn't change that [docs/providers.md#onprem-on-premises]. So a local test can pass on 3.12 with code that would break on your 3.9 servers.

Ways to match production:
- run pskit from a Python 3.9 environment, or
- for the real servers, deploy over SSH with `deploy.python: bundle` (a portable CPython is shipped) or `python: system` to use the server's 3.9.

Your handler starts with `from __future__ import annotations`, which is the right habit for 3.9.""",
}

for _c in CONVERSATIONS:
    _c["final"] = FINALS[int(_c["id"].split("-")[1])]
