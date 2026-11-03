"""Category C (fix a validation error), batch 3. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    # ------------------------------------------------------------------ 41  jwt on azure
    C(41, provider="azure", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: hr-portal
provider:
  name: azure
  region: swedencentral
functions:
  employees:
    handler: app.hr.employees
    events:
      - http:
          path: /employees
          method: GET
          auth: jwt
""",
          "app/__init__.py": "",
          "app/hr.py": handlers("employees")}),
      user="on aws i had jwt on employees route, now azure staging say jwt not supported. what is option for azure?",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure http auth key jwt",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("ask_user", question="On Azure pskit supports `auth: none` or `auth: key` (an Azure function key). Which one for /employees?",
            options=["key (callers send the function key)", "none (I check the token in my handler)"],
            answer="key (callers send the function key)"),
          S("propose_plan", steps=["Set `functions.employees.events.0.http.auth` to `key`",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.employees.events.0.http.auth", value="key"),
      ],
      final="""On Azure pskit can't do `jwt` (JWT auth is AWS only). The options are `none` or `key` [docs/events.md#http].

Now `/employees` has `auth: key`: Azure checks the function key (`AuthLevel.FUNCTION`). `pskit validate -p azure -s staging`: valid.

Callers must send the function key now, not the JWT. If you want to keep the JWT, use `auth: none` and check the token in the handler, or put API Management / Easy Auth in front, as the error message says."""),

    # ------------------------------------------------------------------ 42  python3.8 on gcp
    C(42, provider="gcp", stage="dev", mode="auto", page="Overview", persona="pasted_error",
      sources=["docs/configuration.md#default-runtime"],
      project=dict(files={
          "pskit.yml": """service: legacy-import
provider:
  name: gcp
  region: us-east1
  runtime: python3.8
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, legacy-import-dev}
functions:
  import-csv:
    handler: app.importer.run
    events:
      - storage:
          bucket: legacy-drops
          suffix: .csv
""",
          "app/__init__.py": "",
          "app/importer.py": handlers("run")}),
      user="""Error: pskit.yml is invalid:
  - provider.runtime: Value error, runtime must be python3.9 .. python3.14 or nodejs18, nodejs20, nodejs22, nodejs24 (provider support varies)

old app was 3.8""",
      steps=[
          S("get_validation"),
          S("search_docs", query="default runtime python version",
            docs=[D("docs/configuration.md", "default-runtime")]),
          S("propose_plan", steps=["Remove `provider.runtime: python3.8`, so pskit uses python3.12 on GCP",
                                   "Validate for gcp"]),
          S("set_config", path="provider.runtime", value=None),
      ],
      final="""pskit supports python3.9 and newer, so `python3.8` is rejected by the schema.

I removed the pin. Without `runtime:`, pskit uses python3.12 on GCP [docs/configuration.md#default-runtime]. `pskit validate` for gcp: valid.

Your 3.8 code should run on 3.12 in most cases, but test it locally with `pskit invoke -f import-csv -t storage` before you deploy. If you prefer to stay as close to 3.8 as possible, set `runtime: python3.9` instead."""),

    # ------------------------------------------------------------------ 43  service name
    C(43, provider="aws", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/configuration.md#top-level"],
      project=dict(files={
          "pskit.yml": """service: My_Bakery_Shop
provider:
  name: aws
  region: eu-south-1
functions:
  menu:
    handler: app.bakery.menu
    events:
      - http: GET /menu
""",
          "app/__init__.py": "",
          "app/bakery.py": handlers("menu")}),
      user="I named my project My_Bakery_Shop on the Overview page and now nothing validates. Is the name wrong?",
      steps=[
          S("get_validation"),
          S("search_docs", query="service name rules",
            docs=[D("docs/configuration.md", "top-level", end="| `provider` |")]),
          S("propose_plan", steps=["Rename the service to `my-bakery-shop` (lowercase, dashes)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="service", value="my-bakery-shop"),
      ],
      final="""Yes. The service name is used in cloud resource names, so it may only have lowercase letters, digits and dashes, 2-32 characters, starting with a letter [docs/configuration.md#top-level]. Capital letters and `_` are not allowed.

I renamed it to `my-bakery-shop`. Validate now says the configuration is valid."""),

    # ------------------------------------------------------------------ 44  tencent COS bucket
    C(44, provider="tencent", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/providers.md#tencent-serverless-cloud-function-scf"],
      project=dict(files={
          "pskit.yml": """service: invoice-ocr
provider:
  name: tencent
  region: ap-shanghai
functions:
  read-invoice:
    handler: app.ocr.read_invoice
    timeout: 120
    events:
      - storage:
          bucket: invoices
          prefix: inbox/
          suffix: .pdf
""",
          "app/__init__.py": "",
          "app/ocr.py": handlers("read_invoice")}),
      user="Prod validation on Tencent rejects the COS bucket name `invoices` for read-invoice. Keep the prefix and suffix filters exactly as they are, just make the bucket name acceptable.",
      steps=[
          S("get_validation"),
          S("ask_user", question="COS bucket names must end with your APPID (`<name>-<APPID>`). What is your Tencent Cloud APPID?",
            answer="1250000000"),
          S("propose_plan", steps=["Set `functions.read-invoice.events.0.storage.bucket` to `invoices-1250000000` (prefix/suffix unchanged)",
                                   "Validate for tencent, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.read-invoice.events.0.storage.bucket", value="invoices-1250000000"),
      ],
      final="""On Tencent a COS bucket name must be `<name>-<APPID>` [docs/events.md#storage].

Changed only the bucket: `bucket: invoices-1250000000`. `prefix: inbox/` and `suffix: .pdf` are unchanged. `pskit validate -p tencent -s prod`: valid."""),

    # ------------------------------------------------------------------ 45  ibm memory 8192
    C(45, provider="ibm", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#ibm-code-engine-functions"],
      project=dict(files={
          "pskit.yml": """service: embed-api
provider:
  name: ibm
  region: eu-de
functions:
  embed:
    handler: app.embed.handle
    memory: 8192
    timeout: 60
    events:
      - http: POST /embed
""",
          "app/__init__.py": "",
          "app/embed.py": handlers("handle")}),
      user="ibm staging, embed memory error. set max allowed",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.embed.memory` to 4096 (Code Engine max)",
                                   "Validate for ibm, stage staging"]),
          S("set_config", path="functions.embed.memory", value=4096),
      ],
      final="""Code Engine functions max out at 4096 MB [docs/providers.md#ibm-code-engine-functions]. Set `embed.memory: 4096`. `pskit validate -p ibm -s staging`: valid."""),

    # ------------------------------------------------------------------ 46  ibm python3.12 at function level
    C(46, provider="ibm", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#ibm-code-engine-functions", "docs/configuration.md#default-runtime"],
      project=dict(files={
          "pskit.yml": """service: qr-maker
provider:
  name: ibm
  region: jp-tok
functions:
  make-qr:
    handler: app.qr.make
    runtime: python3.12
    events:
      - http: GET /qr
  status:
    handler: app.qr.status
    events:
      - http: GET /status
""",
          "app/__init__.py": "",
          "app/qr.py": handlers("make", "status")}),
      user="why ibm say make-qr runtime not support? status function is fine and same code",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Remove `runtime: python3.12` from `make-qr`, so it uses python3.11 like `status`",
                                   "Validate for ibm"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.make-qr.runtime", value=None),
      ],
      final="""`make-qr` had its own `runtime: python3.12`, but IBM Code Engine runs only python3.11 [docs/providers.md#ibm-code-engine-functions]. `status` has no pin, so pskit gives it python3.11 automatically [docs/configuration.md#default-runtime].

I removed the pin from `make-qr`. Now both use python3.11, and validate for ibm: valid."""),

    # ------------------------------------------------------------------ 47  gcp event fn timeout 900
    C(47, provider="gcp", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#gcp-multi-trigger-functions-are-split-automatically", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: video-transcode
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, video-transcode-prod}
functions:
  transcode:
    handler: app.video.transcode
    timeout: 900
    memory: 4096
    events:
      - queue: transcode-jobs
""",
          "app/__init__.py": "",
          "app/video.py": handlers("transcode")}),
      user="`transcode` is a Pub/Sub-driven function with timeout 900. The GCP docs say Cloud Functions gen2 can run 3600 s, so why does pskit validation for prod reject 900?",
      steps=[
          S("get_validation"),
          S("search_docs", query="gcp event triggered functions timeout 540",
            docs=[D("docs/events.md", "gcp-multi-trigger-functions-are-split-automatically")]),
          S("propose_plan", steps=["Set `functions.transcode.timeout` to 540, the GCP maximum for event-triggered functions",
                                   "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.transcode.timeout", value=540),
      ],
      final="""3600 s applies to HTTP functions only. `transcode` is triggered by Pub/Sub, so it is an event-triggered deployment, and those are limited to 540 s on GCP [docs/events.md#gcp-multi-trigger-functions-are-split-automatically].

Set `transcode.timeout: 540`. `pskit validate -p gcp -s prod`: valid.

If a transcode can take longer than 9 minutes, make it HTTP-triggered (up to 3600 s) and have the producer call it, or split the work into smaller jobs."""),

    # ------------------------------------------------------------------ 48  digitalocean memory 2048
    C(48, provider="digitalocean", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/providers.md#digitalocean-functions"],
      project=dict(files={
          "pskit.yml": """service: resize-api
provider:
  name: digitalocean
  region: fra1
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE, fn-00000000-0000-0000-0000-000000000000}
functions:
  resize:
    handler: app.images.resize
    memory: 2048
    events:
      - http: POST /resize
""",
          "app/__init__.py": "",
          "app/images.py": handlers("resize")}),
      user="""  ERROR: [functions.resize.memory] memory 2048 MB is outside DigitalOcean's 128-1024 MB range

image resizing needs memory, what's the max then""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.resize.memory` to 1024 (DigitalOcean's maximum)",
                                   "Validate for digitalocean, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.resize.memory", value=1024),
      ],
      final="""The max on DigitalOcean Functions is 1024 MB (range 128-1024) [docs/providers.md#digitalocean-functions].

Set `resize.memory: 1024`. `pskit validate -p digitalocean -s prod` has no errors now. Only the `doctl` WARNING remains (install and `doctl auth init` before deploy). If large images need more than 1 GB, this function needs a provider with bigger limits."""),

    # ------------------------------------------------------------------ 49  azure queue name
    C(49, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: ticket-desk
provider:
  name: azure
  region: eastus2
functions:
  new-ticket:
    handler: app.tickets.new_ticket
    events:
      - queue: New_Tickets
""",
          "app/__init__.py": "",
          "app/tickets.py": handlers("new_ticket")}),
      user="Problems button shows 1 error on new-ticket, the queue name. It looks normal to me?",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure queue name lowercase",
            docs=[D("docs/events.md", "queue", start="On GCP a \"queue\" is a Pub/Sub topic")]),
          S("propose_plan", steps=["Rename the queue of `new-ticket` from `New_Tickets` to `new-tickets`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.new-ticket.events.0.queue", value="new-tickets"),
      ],
      final="""Azure Storage Queues are strict: the name must be 3-63 **lowercase** letters, digits and dashes. `New_Tickets` has capital letters and an underscore [docs/events.md#queue].

I renamed it to `new-tickets`. Validate for azure: valid, and the Problems count is back to 0.

If some other code sends messages to this queue, change the name there too."""),

    # ------------------------------------------------------------------ 50  azure blob deleted
    C(50, provider="azure", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#storage", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: doc-index
provider:
  name: azure
  region: francecentral
functions:
  index-doc:
    handler: app.index.on_change
    events:
      - storage:
          bucket: documents
          events: [created, deleted]
""",
          "app/__init__.py": "",
          "app/index.py": handlers("on_change")}),
      user="On S3 this function handled ObjectCreated and ObjectRemoved, so I kept `events: [created, deleted]`. Azure prod validation complains about blob triggers. Any way to get delete events on Azure?",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure blob trigger deleted events",
            docs=[D("docs/events.md", "storage", start="| Provider | Service | Filters | Notes |", end="| azure |")]),
          S("ask_user", question="Azure blob triggers only fire on created/updated blobs, so pskit has no delete event on Azure. Should I keep only `created` for `index-doc`?",
            options=["Yes, keep only created", "No, leave it, I'll deploy this function elsewhere"],
            answer="Yes, keep only created"),
          S("propose_plan", steps=["Set `functions.index-doc.events.0.storage.events` to `[created]`",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.index-doc.events.0.storage.events", value=["created"]),
      ],
      final="""Not with pskit: Azure blob triggers fire on created/updated blobs only, so there is no `deleted` event [docs/events.md#storage].

`index-doc` now has `events: [created]`. `pskit validate -p azure -s prod`: valid.

Removed documents will no longer reach the handler on Azure. If the index must drop them, you need another way, for example a periodic `schedule` function that compares the index with the container."""),

    # ------------------------------------------------------------------ 51  onprem port 70000
    C(51, provider="onprem", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/troubleshooting.md#provider-gotchas"],
      project=dict(files={
          "pskit.yml": """service: home-sensors
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 70000
functions:
  reading:
    handler: app.sensors.reading
    events:
      - http: POST /reading
""",
          "app/__init__.py": "",
          "app/sensors.py": handlers("reading")}),
      user="onprem error port must be integer 1 to 65535. i put 70000 bcz 8080 is used by other app",
      steps=[
          S("get_validation"),
          S("ask_user", question="Ports only go up to 65535. Which free port should home-sensors use? (Each service needs its own port.)",
            options=["8180", "9000", "other"],
            answer="9000"),
          S("propose_plan", steps=["Set `provider.options.port` to 9000",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.port", value=9000),
      ],
      final="""A port number can't be bigger than 65535, so 70000 is impossible. I set `provider.options.port: 9000`, as you chose. Validate for onprem: valid.

Each on-prem service runs as its own process, so give every service its own port [docs/troubleshooting.md#provider-gotchas]. Make sure nothing else on the machine uses 9000."""),

    # ------------------------------------------------------------------ 52  hooks pre_deploy
    C(52, provider="aws", stage="staging", mode="auto", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#hooks"],
      project=dict(files={
          "pskit.yml": """service: graphql-gw
provider:
  name: aws
  region: ca-central-1
hooks:
  pre_deploy:
    - python scripts/build_schema.py
functions:
  graphql:
    handler: app.gql.handle
    events:
      - http: POST /graphql
""",
          "app/__init__.py": "",
          "app/gql.py": handlers("handle")}),
      user="Ported my serverless-plugin hook as `hooks: pre_deploy:` and now the whole file is invalid. What's the hook name pskit expects to run a script before deploy?",
      steps=[
          S("get_validation"),
          S("search_docs", query="hooks allowed names before deploy",
            docs=[D("docs/configuration.md", "hooks")]),
          S("propose_plan", steps=["Rename hook `pre_deploy` to `before_deploy` (same command)",
                                   "Validate for aws, stage staging"]),
          S("set_config", path="hooks.before_deploy", value=["python scripts/build_schema.py"]),
          S("set_config", path="hooks.pre_deploy", value=None),
      ],
      final="""pskit's name is `before_deploy`. The allowed hooks are `before_`/`after_` + `package`, `deploy`, `remove` [docs/configuration.md#hooks].

Now:

```yaml
hooks:
  before_deploy: ["python scripts/build_schema.py"]
```

`pskit validate -p aws -s staging`: valid. The command runs in the project root with `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and `PSKIT_WORK_DIR` set; a non-zero exit stops the deploy."""),

    # ------------------------------------------------------------------ 53  database resource not external
    C(53, provider="aws", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/configuration.md#resources", "docs/resources.md#secrets"],
      project=dict(files={
          "pskit.yml": """service: crm-api
provider:
  name: aws
  region: eu-west-1
resources:
  crm-db:
    type: database
    connection:
      host: db.example.com
      port: 5432
      database: crm
functions:
  contacts:
    handler: app.crm.contacts
    events:
      - http: GET /contacts
""",
          "app/__init__.py": "",
          "app/crm.py": handlers("contacts")}),
      user="I added our existing Postgres as a `database` resource on the Resources page so `contacts` gets its connection details. Validation now fails on `resources.crm-db`. The password is in the env var CRM_DB_PASSWORD on the deploy machine; don't put it in the file.",
      steps=[
          S("get_validation"),
          S("search_docs", query="database resource external connection password_env",
            docs=[D("docs/configuration.md", "resources", end="functions: [api]")]),
          S("propose_plan", steps=["Set `resources.crm-db.external: true` (pskit never creates databases)",
                                   "Add `connection.password_env: CRM_DB_PASSWORD` (the variable name, not the password)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.crm-db.external", value=True),
          S("set_config", path="resources.crm-db.connection.password_env", value="CRM_DB_PASSWORD"),
      ],
      final="""pskit never creates `database` resources, so a database must be marked `external: true` [docs/configuration.md#resources].

`crm-db` now looks like this:

```yaml
resources:
  crm-db:
    type: database
    external: true
    connection: {host: db.example.com, port: 5432, database: crm, password_env: CRM_DB_PASSWORD}
```

`pskit validate` for aws: valid. Only the **name** `CRM_DB_PASSWORD` is in the file. At run time the handler reads the password with `ctx.env[db["password_env"]]`, so that variable must exist in the function's environment [docs/resources.md#secrets]."""),

    # ------------------------------------------------------------------ 54  cors origin
    C(54, provider="aws", stage="dev", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: booking-api
provider:
  name: aws
  region: us-east-1
functions:
  slots:
    handler: app.booking.slots
    events:
      - http:
          path: /slots
          method: GET
          cors:
            origin: https://app.example.com
""",
          "app/__init__.py": "",
          "app/booking.py": handlers("slots")}),
      user="""Error: pskit.yml is invalid:
  - functions.slots.events.0.cors.bool: Input should be a valid boolean
  - functions.slots.events.0.cors.CorsConfig.origin: Extra inputs are not permitted

I only want my frontend https://app.example.com allowed""",
      steps=[
          S("get_validation"),
          S("search_docs", query="cors origins mapping",
            docs=[D("docs/events.md", "http", start="**CORS**", end="max_age: 600")]),
          S("propose_plan", steps=["Replace `cors: {origin: ...}` on `slots` with `cors: {origins: [\"https://app.example.com\"]}`",
                                   "Validate for aws"]),
          S("set_config", path="functions.slots.events.0.http.cors", value={"origins": ["https://app.example.com"]}),
      ],
      final="""The key is `origins` (plural, a list), not `origin`. `cors` must be `true` or a mapping with valid keys, so pskit printed both errors [docs/events.md#http].

Now:

```yaml
- http:
    path: /slots
    method: GET
    cors:
      origins: ["https://app.example.com"]
```

`pskit validate` for aws: valid. Methods and headers keep their defaults."""),

    # ------------------------------------------------------------------ 55  workflow calls disabled function
    C(55, provider="cloudflare", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/configuration.md#switch-something-off-on-one-cloud"],
      project=dict(files={
          "pskit.yml": """service: month-close
provider:
  name: aws
  region: eu-west-1
providers:
  cloudflare:
    options:
      account_id: ${env:CLOUDFLARE_ACCOUNT_ID, 0123456789abcdef0123456789abcdef}
    functions:
      render-pdf:
        enabled: false
functions:
  collect:
    handler: app.close.collect
  render-pdf:
    handler: app.close.render_pdf
  status:
    handler: app.close.status
    events:
      - http: GET /status
workflows:
  monthly-close:
    start_at: Collect
    states:
      Collect:
        type: task
        function: collect
        next: Render
      Render:
        type: task
        function: render-pdf
        end: true
""",
          "app/__init__.py": "",
          "app/close.py": handlers("collect", "render_pdf", "status")}),
      user="I turned off `render-pdf` for Cloudflare (it needs a PDF library Pyodide doesn't have). Since then validation for Cloudflare fails with a message about the `monthly-close` workflow. On Cloudflare only the `status` endpoint matters; AWS must keep everything.",
      steps=[
          S("get_validation"),
          S("search_docs", query="disable workflow on one provider disabled function",
            docs=[D("docs/configuration.md", "switch-something-off-on-one-cloud")]),
          S("propose_plan", steps=["Add `providers.cloudflare.workflows.monthly-close.enabled: false`",
                                   "Validate for cloudflare (AWS config unchanged)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.cloudflare.workflows.monthly-close.enabled", value=False),
      ],
      final="""A workflow can't call a function that is disabled on that provider, so pskit asks you to disable the workflow too [docs/configuration.md#switch-something-off-on-one-cloud].

Added under `providers.cloudflare`:

```yaml
workflows:
  monthly-close: {enabled: false}
```

`pskit validate -p cloudflare`: valid. Warnings say `render-pdf` and `monthly-close` are disabled there, plus the usual Pyodide note. On AWS both still deploy (Step Functions)."""),

    # ------------------------------------------------------------------ 56  engine native on alibaba
    C(56, provider="alibaba", stage="staging", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#engines", "docs/workflows.md#workflow-keys"],
      project=dict(files={
          "pskit.yml": """service: loan-check
provider:
  name: alibaba
  region: cn-shenzhen
functions:
  score:
    handler: app.loan.score
  decide:
    handler: app.loan.decide
workflows:
  check:
    engine: native
    start_at: Score
    states:
      Score: {type: task, function: score, next: Decide}
      Decide: {type: task, function: decide, end: true}
""",
          "app/__init__.py": "",
          "app/loan.py": handlers("score", "decide")}),
      user="engine native error on alibaba staging. fix",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.check.engine` to `auto` (embedded on alibaba, native on aws/gcp)",
                                   "Validate for alibaba, stage staging"]),
          S("set_config", path="workflows.check.engine", value="auto"),
      ],
      final="""Alibaba has no native workflow engine in pskit; `native` only works on aws, gcp (and azure opt-in) [docs/workflows.md#engines].

Set `engine: auto`: embedded orchestrator on Alibaba, still native if you target aws/gcp later. `pskit validate -p alibaba -s staging`: valid. One WARNING remains: the embedded run is capped by the function timeout (3600 s max on Alibaba)."""),

    # ------------------------------------------------------------------ 57  gcp fifo warning
    C(57, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: chat-relay
provider:
  name: gcp
  region: europe-west2
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, chat-relay-dev}
functions:
  relay:
    handler: app.chat.relay
    events:
      - queue:
          name: chat-messages
          fifo: true
""",
          "app/__init__.py": "",
          "app/chat.py": handlers("relay")}),
      user="there's a yellow warning about fifo on my relay function. does it mean my messages will come in the wrong order?",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue fifo gcp pub/sub ignored",
            docs=[D("docs/events.md", "queue", start="| Option | aws (SQS)", end="| partial batch failure |")]),
          S("propose_plan", steps=["Remove `fifo: true` from the `relay` queue trigger (GCP ignores it anyway)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.relay.events.0.queue.fifo", value=None),
      ],
      final="""It means `fifo: true` does nothing on GCP. There a queue is a Pub/Sub topic, and pskit ignores `fifo` with a warning [docs/events.md#queue]. So yes: on GCP, pskit does not promise that messages arrive in order.

I removed `fifo: true` so the file doesn't promise something GCP won't do. Validate for gcp: valid, and the warning is gone.

If order matters, make the handler handle it, for example with a sequence number in each message. Or use AWS, where `fifo: true` gives an SQS FIFO queue."""),

    # ------------------------------------------------------------------ 58  azure fifo + timezone warnings
    C(58, provider="azure", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: payroll-jobs
provider:
  name: azure
  region: germanywestcentral
functions:
  payslips:
    handler: app.payroll.payslips
    events:
      - queue:
          name: payslip-requests
          fifo: true
  monthly-run:
    handler: app.payroll.monthly_run
    events:
      - schedule:
          cron: "0 6 1 * *"
          timezone: Europe/Berlin
""",
          "app/__init__.py": "",
          "app/payroll.py": handlers("payslips", "monthly_run")}),
      user="azure staging validate ok but 2 warnings, my boss want zero warning. but monthly-run must still start 6 oclock berlin time!",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure timer timezone ignored UTC",
            docs=[D("docs/events.md", "schedule", start="| Provider | Service | Expression |", end="| azure |"),
                  D("docs/events.md", "schedule", start="A rate that can't be expressed")]),
          S("propose_plan", steps=["Remove `fifo: true` from the `payslips` queue (Azure Storage Queues are not FIFO)",
                                   "Replace `cron: 0 6 1 * *` + `timezone: Europe/Berlin` on `monthly-run` with the UTC time `0 5 1 * *` (06:00 Berlin in winter, CET = UTC+1)",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.payslips.events.0.queue.fifo", value=None),
          S("set_config", path="functions.monthly-run.events.0.schedule.timezone", value=None),
          S("set_config", path="functions.monthly-run.events.0.schedule.cron", value="0 5 1 * *"),
      ],
      final="""Done, validate for azure staging: valid with **0 warnings**.

Why the warnings came:
1. `fifo: true`: Azure Storage Queues are not FIFO, so it was ignored. Removed.
2. `timezone: Europe/Berlin`: Azure timers always run in UTC and ignore `timezone` [docs/events.md#schedule]. So before, your job really ran at 06:00 **UTC**, not Berlin time.

Now `monthly-run` has `cron: "0 5 1 * *"` (05:00 UTC = 06:00 Berlin in winter). Important: in summer (CEST, UTC+2) this is 07:00 Berlin, because a UTC timer doesn't follow daylight saving. If it must be 06:00 Berlin all year, deploy this function to a provider that honours `timezone` (aws, gcp, alibaba)."""),

    # ------------------------------------------------------------------ 59  queue event on storage resource
    C(59, provider="aws", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#troubleshooting", "docs/events.md#events-backed-by-a-resource"],
      project=dict(files={
          "pskit.yml": """service: photo-tagger
provider:
  name: aws
  region: us-west-1
resources:
  photos:
    type: storage
functions:
  tag-photo:
    handler: app.tagger.tag_photo
    events:
      - queue: {resource: photos}
""",
          "app/__init__.py": "",
          "app/tagger.py": handlers("tag_photo")}),
      user="I want tag-photo to run when someone uploads a photo to my photos bucket. It says something about a queue event on a storage?",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue event on resource which is a storage",
            docs=[D("docs/resources.md", "troubleshooting", end="which is a storage`")]),
          S("propose_plan", steps=["Change the trigger of `tag-photo` from `queue: {resource: photos}` to `storage: {resource: photos}`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.tag-photo.events", value=[{"storage": {"resource": "photos"}}]),
      ],
      final="""The trigger type didn't match the resource: `photos` is a bucket (`type: storage`), but the trigger was a `queue` trigger. The event kind must match the resource type [docs/resources.md#troubleshooting].

Now `tag-photo` has:

```yaml
events:
  - storage: {resource: photos}
```

It runs when a file is created in the `photos` bucket (the default event is `created`). Validate for aws: valid."""),

    # ------------------------------------------------------------------ 60  providers: typo gpc
    C(60, provider="gcp", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#providers-per-cloud-overrides"],
      project=dict(files={
          "pskit.yml": """service: todo-app
provider:
  name: aws
  region: us-east-1
providers:
  gpc:
    region: europe-west1
    options:
      project: todo-app-dev-1187
functions:
  todos:
    handler: app.todo.todos
    events:
      - http: GET /todos
""",
          "app/__init__.py": "",
          "app/todo.py": handlers("todos")}),
      user="""Error: `providers:` has unknown keys ['gpc']; supported: alibaba, aws, azure, cloudflare, digitalocean, gcp, huawei, ibm, onprem, oracle, tencent

got this after switching the target to gcp""",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Move the override block from `providers.gpc` to `providers.gcp` (same region and project)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.gcp", value={"region": "europe-west1", "options": {"project": "todo-app-dev-1187"}}),
          S("set_config", path="providers.gpc", value=None),
      ],
      final="""The override block was named `gpc` instead of `gcp`. Keys under `providers:` must be real provider names, and the block for the active provider is merged into the config [docs/configuration.md#providers-per-cloud-overrides].

I moved it to `providers.gcp` (region `europe-west1`, project `todo-app-dev-1187`) and removed `gpc`. `pskit validate` for gcp: valid. The typo also meant the GCP project was never applied before."""),
]
