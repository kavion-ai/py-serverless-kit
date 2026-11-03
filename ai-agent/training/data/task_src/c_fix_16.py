"""Category C (fix a validation error), batch 16: on-premises secrets in plain text, several errors at once,
stage overrides, disabled functions and value ranges. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import D, S  # noqa: E402
from _onprem_c import C, app, mods, onprem, saved  # noqa: E402

P = "docs/providers.md"
A = "onprem-on-premises"
R = "docs/resources.md"
CF = "docs/configuration.md"
SECRETS = D(R, "on-premises-drivers", start="**Secrets.**", end="**Secrets.**")
QDRIVERS = D(R, "queue-drivers", start="| Driver |", end="| `pskit_host` |")
ADMIN = D(P, A, start="    poll_seconds: 0.5", end="never written to Terraform state")
TUNING = D(P, A, start="    execution_retention: 500", end="capture_output: true")
TRIGGERS = D(P, A, start="| Trigger |", end="| http |")
SWITCH_OFF = D(CF, "switch-something-off-on-one-cloud", start="```yaml", end="Disabled functions and workflows")
FUNCS = D(CF, "functions", start="| Key |", end="| `concurrency` |")
TOP = D(CF, "top-level", start="| Key |", end="| `provider` |")
PROVIDER_T = D(CF, "provider", start="| Key |", end="| `runtime` |")
H = dict(host="0.0.0.0")

CONVERSATIONS = [
    # ------------------------------------------------------------------ 301  admin_token in plain text
    C(301, provider="onprem", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises", "docs/configuration.md#variables"],
      project=dict(files={"pskit.yml": onprem("warehouse", """functions:
  stock:
    handler: app.stock.levels
    events:
      - http: GET /stock
""", extra="    admin_token: wh-admin-7731\n", **H), **app("stock", "levels")}),
      user="Security review before go-live: prod validates, but the reviewer flagged provider.options in pskit.yml. Fix whatever shouldn't be committed. The CI already exports PSKIT_ADMIN_TOKEN.",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("search_docs", query="admin_token env variable", docs=[ADMIN]),
          S("propose_plan", steps=["Replace the literal `admin_token` with `${env:PSKIT_ADMIN_TOKEN, }`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.admin_token", value="${env:PSKIT_ADMIN_TOKEN, }"),
      ],
      final="""The admin token was written in pskit.yml in plain text. It protects `/__pskit/*` (logs, invoke, queues) through the `x-pskit-token` header [docs/providers.md#onprem-on-premises].

Now `admin_token: "${env:PSKIT_ADMIN_TOKEN, }"`, the form the docs use: CI's variable is used at deploy, and an empty default keeps validation working on machines without it. `pskit validate -p onprem -s prod`: valid. Rotate the old token, since it is in git history."""),

    # ------------------------------------------------------------------ 302  redis URL with a password
    C(302, provider="onprem", stage="staging", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#on-premises-drivers"],
      project=dict(files={"pskit.yml": onprem("chat-queue", """resources:
  messages:
    type: queue
    external: true
    options: {driver: redis, url: "redis://:hunter22@192.0.2.40:6379/0"}
functions:
  deliver:
    handler: app.chat.deliver
    events:
      - queue: {resource: messages}
""", **H), **app("chat", "deliver")}),
      user="validate is fine but redis password is inside url in yaml. how hide it",
      steps=[
          S("get_validation"),
          S("search_docs", query="driver secrets _env", docs=[SECRETS]),
          S("ask_user", question="Which environment variable on the host should hold the Redis URL?", options=["REDIS_URL", "another name"],
            answer="REDIS_URL"),
          S("propose_plan", steps=["Replace `url` with `url_env: REDIS_URL` in `resources.messages.options`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.messages.options", value={"driver": "redis", "url_env": "REDIS_URL"}),
      ],
      final="""Any driver parameter can be `<name>_env`: the host reads the value from its own environment when it starts, so it never lands in pskit.yml or Terraform state [docs/resources.md#on-premises-drivers].

Now `options: {driver: redis, url_env: REDIS_URL}`. `pskit validate -p onprem -s staging`: valid. Put the full URL in `REDIS_URL` on the server (or in `env_file`), and change the Redis password, since it was in the file."""),

    # ------------------------------------------------------------------ 303  SQS keys in plain text
    C(303, provider="onprem", stage="prod", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#queue-drivers", "docs/resources.md#on-premises-drivers"],
      project=dict(files={"pskit.yml": onprem("sqs-bridge", """resources:
  orders:
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/orders
      access_key: EXAMPLEKEYID0000
      secret_key: example-secret-value-0000
functions:
  import-order:
    handler: app.orders.import_order
    events:
      - queue: {resource: orders}
""", **H), **app("orders", "import_order")}),
      user="Our on-prem host consumes an SQS queue. I pasted the IAM user's keys into options to get it working; now make it safe. The server has AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in its env file.",
      steps=[
          S("get_validation"),
          S("search_docs", query="sqs driver access_key AWS variables", docs=[QDRIVERS, SECRETS]),
          S("propose_plan", steps=["Delete `access_key` and `secret_key` from `resources.orders.options` (the host falls back to AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.orders.options.access_key", value=None),
          S("set_config", path="resources.orders.options.secret_key", value=None),
      ],
      final="""Without `access_key` / `secret_key`, the sqs driver uses `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` from the host's environment, which your env file already sets [docs/resources.md#queue-drivers].

Removed both keys; `queue_url` stays. `pskit validate -p onprem -s prod`: valid. Deactivate that IAM key pair and make a new one, because it was in pskit.yml."""),

    # ------------------------------------------------------------------ 304  MinIO secret in connection
    C(304, provider="onprem", stage="dev", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#on-premises-drivers"],
      project=dict(files={"pskit.yml": onprem("docs-store", """resources:
  docs:
    type: storage
    external: true
    options: {driver: minio, endpoint: "http://192.0.2.30:9000", access_key_env: MINIO_ACCESS}
    connection: {secret_key: minio-dev-pass-01}
functions:
  index:
    handler: app.docs.index
    events:
      - storage: {resource: docs}
"""), **app("docs", "index")}),
      user="move minio secret out of yaml, env MINIO_SECRET",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `resources.docs.connection`", "Set `resources.docs.options.secret_key_env` to `MINIO_SECRET`", "Validate for onprem"]),
          S("set_config", path="resources.docs.connection", value=None),
          S("set_config", path="resources.docs.options.secret_key_env", value="MINIO_SECRET"),
      ],
      final="""Done: the secret is gone from `connection` (those values are handed to handlers and written to state), and `secret_key_env: MINIO_SECRET` is read on the host at start [docs/resources.md#on-premises-drivers]. Validate for onprem: valid. Rotate that MinIO key."""),

    # ------------------------------------------------------------------ 305  pskit_host token in plain text
    C(305, provider="onprem", stage="staging", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("labels", """resources:
  print-queue:
    type: queue
    external: true
    options: {driver: pskit_host, endpoint: "http://192.0.2.20:8090", token: print-host-admin-55}
functions:
  label:
    handler: app.labels.label
    events:
      - queue: {resource: print-queue}
""", **H), **app("labels", "label")}),
      user="My teammate said I shouldn't write the other host's token in the yaml. What should I do? It validates fine.",
      steps=[
          S("get_validation"),
          S("search_docs", query="pskit_host token_env", docs=[QDRIVERS]),
          S("ask_user", question="What should the environment variable with that token be called on this host?", options=["PRINT_HOST_TOKEN", "another name"],
            answer="PRINT_HOST_TOKEN"),
          S("propose_plan", steps=["Replace `token` with `token_env: PRINT_HOST_TOKEN` in `resources.print-queue.options`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.print-queue.options.token", value=None),
          S("set_config", path="resources.print-queue.options.token_env", value="PRINT_HOST_TOKEN"),
      ],
      final="""Your teammate is right: the docs say to give `pskit_host` its token with `token_env` [docs/resources.md#queue-drivers].

Now `token_env: PRINT_HOST_TOKEN`, and the token itself goes into that variable on this host (or its `env_file`). `pskit validate -p onprem -s staging`: valid. Ask the print host's owner for a new admin token, since the old one was in the file."""),

    # ------------------------------------------------------------------ 306  env_file path wrong (warning)
    C(306, provider="onprem", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("crm-api", """functions:
  contacts:
    handler: app.crm.contacts
    events:
      - http: GET /contacts
""", extra="    env_file: .env.onprem\n"), **app("crm", "contacts"), "config/onprem.env": "LOG_FORMAT=json\n"}),
      user="""  WARNING: [provider.options.env_file] options.env_file .env.onprem does not exist yet; the host starts without it

the file is config/onprem.env""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.env_file` to `config/onprem.env`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.env_file", value="config/onprem.env"),
      ],
      final="""`env_file` is relative to pskit.yml, and it pointed at `.env.onprem`, which isn't there [docs/providers.md#onprem-on-premises]. Now `env_file: config/onprem.env`. Validate for onprem: valid, no warnings. Keep that file out of git."""),

    # ------------------------------------------------------------------ 307  auth key on premises
    C(307, provider="onprem", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("partner-api", """functions:
  rates:
    handler: app.partner.rates
    environment:
      PARTNER_KEYS_ENV: PARTNER_API_KEYS
    events:
      - http: {path: /rates, method: GET, auth: key}
""", **H), **app("partner", "rates")}),
      user="On API Gateway partners sent an x-api-key. Prod on-prem says auth `key` is not enforced on-premises. How do I keep partners authenticated?",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem http auth none check tokens handler", docs=[TRIGGERS]),
          S("propose_plan", steps=["Set `functions.rates.events.0.http.auth` to `none`", "Validate for onprem, stage prod",
                                   "Check the `x-api-key` header in the handler"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.rates.events.0.http.auth", value="none"),
      ],
      final="""The on-prem host has no API gateway, so `auth` must be `none` and the handler checks the key [docs/providers.md#onprem-on-premises].

Set `auth: none`. `pskit validate -p onprem -s prod`: valid. In `rates`, compare `event.http.headers.get("x-api-key")` with the keys from the environment and return `(..., 401)` when it doesn't match. Until then the route is open, so add the check before you deploy."""),

    # ------------------------------------------------------------------ 308  Problems: errors appear one layer at a time
    C(308, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("tiny", """functions:
  hello:
    handler: app.hello.hello
    memory: 32
    events:
      - http: GET /hello
""", extra="    log_level: verbose\n    poll_seconds: 0\n"), **app("hello", "hello")}),
      user="Fix the problems on the Functions page, I just want this tiny function to use as little as possible and log everything.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.hello.memory` to 64 (the minimum)", "Validate again to see the remaining problems"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.hello.memory", value=64),
          S("search_docs", query="log_level poll_seconds options", docs=[TUNING, ADMIN]),
          S("propose_plan", steps=["Set `provider.options.log_level` to `DEBUG` (log everything)",
                                   "Delete `provider.options.poll_seconds` (default 0.5; 0 isn't allowed)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.log_level", value="DEBUG"),
          S("set_config", path="provider.options.poll_seconds", value=None),
      ],
      final="""Three problems, found in two rounds (pskit checks the YAML schema before the provider options):
1. `memory: 32` is below the minimum of 64 MB [docs/configuration.md#functions]. Now 64.
2. `log_level: verbose` isn't a level; to log everything it is `DEBUG`.
3. `poll_seconds: 0` must be a positive number. I removed it, so the default 0.5 s applies [docs/providers.md#onprem-on-premises].

Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 309  why can't I deploy: host as a list
    C(309, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("dash", """functions:
  page:
    handler: app.dash.page
    events:
      - http: GET /
""", host="[0.0.0.0, 127.0.0.1]", extra="    deploy: {method: ssh, host: 192.0.2.11, python: bundle}\n"), **app("dash", "page")}),
      user="why cant i deploy staging?? deploy button do nothing good",
      steps=[
          S("get_validation"),
          S("search_docs", query="options.host bind address", docs=[D(P, A, start="`options.host` is the bind address", end="`options.host` is the bind address")]),
          S("propose_plan", steps=["Set `provider.options.host` to `0.0.0.0` (one address; it already includes 127.0.0.1)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
      ],
      final="""Validation fails, so deploy stops: `options.host` must be one bind address, and it was a list [docs/providers.md#onprem-on-premises]. `0.0.0.0` listens on every interface, 127.0.0.1 included.

Set `host: 0.0.0.0`. `pskit validate -p onprem -s staging`: valid. Deploy again from the **Deploy** page (or `pskit deploy -s staging`)."""),

    # ------------------------------------------------------------------ 310  prod stage override: ssh without host
    C(310, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("timesheet", """functions:
  submit:
    handler: app.time.submit
    events:
      - http: POST /hours
stages:
  prod:
    provider:
      options:
        deploy: {method: ssh, python: bundle}
""", **H), **app("time", "submit")}),
      user="Dev runs locally and validates. For prod I added a stage override to deploy over SSH, but prod validation says options.deploy.host is required when method is ssh.",
      steps=[
          S("get_validation"),
          S("ask_user", question="Which server should prod deploy to (IP address or host name)?", answer="192.0.2.10, user pskit"),
          S("propose_plan", steps=["Set `stages.prod.provider.options.deploy` to `{method: ssh, host: 192.0.2.10, user: pskit, python: bundle}`",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.provider.options.deploy", value={"method": "ssh", "host": "192.0.2.10", "user": "pskit", "python": "bundle"}),
      ],
      final="""`method: ssh` needs to know which server; the override only said "over SSH" [docs/providers.md#onprem-on-premises].

The prod override is now `deploy: {method: ssh, host: 192.0.2.10, user: pskit, python: bundle}`; dev still runs locally. `pskit validate -p onprem -s prod`: valid. (A saved server works too: `deploy: {server: NAME}`.)"""),

    # ------------------------------------------------------------------ 311  placement lists a disabled function
    C(311, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={"pskit.yml": onprem("crm", """functions:
  api:
    handler: app.api.handle
    events:
      - http: ANY /crm
  legacy-sync:
    handler: app.legacy.sync
    enabled: false
""", extra="    deploy: {python: bundle}\n    placement:\n      groups:\n        web: {server: app-1}\n        sync: {server: app-2, functions: [legacy-sync]}\n", **H),
          **mods(api="handle", legacy="sync"), **saved("app-1", "app-2")}),
      user="""  ERROR: [provider.options.placement] options.placement.groups.sync: no function 'legacy-sync' (functions: api)

I switched legacy-sync off last week""",
      steps=[
          S("get_validation"),
          S("ask_user", question="`sync` only holds legacy-sync. Remove the whole `sync` group (nothing runs on app-2), or keep app-2 for something else?",
            options=["Remove the sync group", "Keep it"], answer="Remove the sync group"),
          S("propose_plan", steps=["Delete `provider.options.placement.groups.sync`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.sync", value=None),
      ],
      final="""A disabled function isn't deployed, so a placement group can't list it [docs/placement.md#functions-on-several-servers-on-premises].

Removed the `sync` group; `api` runs on app-1. Validate for onprem: valid (with a WARNING that `legacy-sync` is disabled). When you turn it back on, add the group again."""),

    # ------------------------------------------------------------------ 312  workflow calls a function disabled on onprem
    C(312, provider="onprem", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/configuration.md#switch-something-off-on-one-cloud"],
      project=dict(files={"pskit.yml": onprem("orders", """functions:
  charge:
    handler: app.orders.charge
  ship:
    handler: app.orders.ship
workflows:
  fulfil:
    start_at: Charge
    states:
      Charge: {type: task, function: charge, next: Ship}
      Ship: {type: task, function: ship}
providers:
  onprem:
    functions:
      charge: {enabled: false}
""", **H), **app("orders", "charge", "ship")}),
      user="Payments only run in the cloud, so I disabled charge for onprem. Now staging on-prem fails: workflow 'fulfil' calls function 'charge', which is disabled. The workflow is cloud-only too.",
      steps=[
          S("get_validation"),
          S("search_docs", query="disable function workflow one provider", docs=[SWITCH_OFF]),
          S("propose_plan", steps=["Set `providers.onprem.workflows.fulfil.enabled` to false", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.onprem.workflows", value={"fulfil": {"enabled": False}}),
      ],
      final="""A workflow can't call a disabled function, so it must be switched off on the same provider [docs/configuration.md#switch-something-off-on-one-cloud].

Added `providers.onprem.workflows.fulfil: {enabled: false}`. `pskit validate -p onprem -s staging`: valid, with warnings that `charge` and `fulfil` are disabled on premises. On the cloud both still deploy."""),

    # ------------------------------------------------------------------ 313  same route twice in one function
    C(313, provider="onprem", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("status", """functions:
  health:
    handler: app.status.health
    events:
      - http: GET /health
      - http: get /health
"""), **app("status", "health")}),
      user="route GET /health is used by both 'health' and 'health'. lol fix",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete the duplicate event `functions.health.events.1`", "Validate for onprem"]),
          S("set_config", path="functions.health.events.1", value=None),
      ],
      final="""Methods are case-insensitive, so `get /health` was the same route again [docs/configuration.md#functions]. Removed the second event. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 314  concurrency -1 for unlimited
    C(314, provider="onprem", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("ingest", """functions:
  collect:
    handler: app.ingest.collect
    concurrency: -1
    events:
      - http: POST /collect
""", **H), **app("ingest", "collect")}),
      user="In Lambda -1 meant unreserved/unlimited concurrency. Prod: concurrency Input should be greater than or equal to 0.",
      steps=[
          S("get_validation"),
          S("search_docs", query="function concurrency", docs=[FUNCS]),
          S("propose_plan", steps=["Delete `functions.collect.concurrency` (no limit is the default)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.collect.concurrency", value=None),
      ],
      final="""pskit has no `-1`: `concurrency` is an int ≥ 0 and leaving it out means no limit [docs/configuration.md#functions].

Removed it. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 315  existing: maybe
    C(315, provider="onprem", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("importer", """functions:
  load:
    handler: app.importer.load
    events:
      - queue: {name: imports, existing: maybe}
""", **H), **app("importer", "load")}),
      user="existing Input should be a valid boolean. not sure if queue there already",
      steps=[
          S("get_validation"),
          S("search_docs", query="existing true queue onprem", docs=[D(P, A, start="Omitted services default to `builtin`", end="Omitted services default to `builtin`")]),
          S("ask_user", question="Does another project (or a person) create the `imports` queue folder, or should this host create it at start?",
            options=["This host creates it", "Something else creates it"], answer="This host creates it"),
          S("propose_plan", steps=["Delete `functions.load.events.0.queue.existing` (default false: the host creates it)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.load.events.0.queue.existing", value=None),
      ],
      final="""`existing` is true or false: `true` means "don't create it, wait until it appears" [docs/providers.md#onprem-on-premises]. Since this host should create `imports`, I removed it (default false). `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 316  description as a list
    C(316, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("library", """functions:
  borrow:
    handler: app.library.borrow
    description:
      - Lends a book
      - Sends a reminder after 14 days
    events:
      - http: POST /borrow
"""), **app("library", "borrow")}),
      user="I wrote the description as two bullet points and now: description Input should be a valid string.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.borrow.description` to one string: \"Lends a book; sends a reminder after 14 days\"", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.borrow.description", value="Lends a book; sends a reminder after 14 days"),
      ],
      final="""`description` is one string, not a list [docs/configuration.md#functions]. Now "Lends a book; sends a reminder after 14 days". Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 317  timeout 0 for no timeout
    C(317, provider="onprem", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#functions", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("video", """functions:
  encode:
    handler: app.video.encode
    timeout: 0
    events:
      - queue: {name: encode-jobs, batch_size: 1}
""", **H), **app("video", "encode")}),
      user="Encoding can take very long, so I set timeout: 0 meaning no timeout. Prod validation rejects it. What's the right setting for an on-prem worker?",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem timeout host does not kill handler", docs=[D(P, A, start="**Limits:**", end="**Limits:**")]),
          S("propose_plan", steps=["Set `functions.encode.timeout` to 3600 (the maximum)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.encode.timeout", value=3600),
      ],
      final="""`timeout` is 1-3600 seconds; 0 isn't "unlimited" [docs/configuration.md#functions]. On premises the host doesn't kill a handler at its timeout anyway; `ctx.remaining_time_ms()` just counts down [docs/providers.md#onprem-on-premises].

Set `timeout: 3600`. `pskit validate -p onprem -s prod`: valid. It also makes the queue's default `visibility_timeout` 6 x 3600 s, so a long encode isn't handed to a second worker."""),

    # ------------------------------------------------------------------ 318  architecture aarch64 at provider level
    C(318, provider="onprem", stage="staging", mode="auto", page="Overview", persona="terse_expert",
      sources=["docs/configuration.md#provider"],
      project=dict(files={"pskit.yml": onprem("edge-api", """  architecture: aarch64
functions:
  read:
    handler: app.edge.read
    events:
      - http: GET /read
""", **H, extra="    deploy: {method: ssh, host: 198.51.100.7, python: bundle}\n"), **app("edge", "read")}),
      user="provider.architecture aarch64 rejected. server is ARM",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.architecture` to `arm64`", "Validate for onprem, stage staging"]),
          S("set_config", path="provider.architecture", value="arm64"),
      ],
      final="""pskit spells ARM `arm64` (`x86_64` or `arm64`) [docs/configuration.md#provider]. Changed it; pip wheels and the bundled Python are picked for arm64. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 319  runtime python3.15
    C(319, provider="onprem", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#provider"],
      project=dict(files={"pskit.yml": onprem("newpy", """  runtime: python3.15
functions:
  hi:
    handler: app.hi.hi
    events:
      - http: GET /hi
"""), **app("hi", "hi")}),
      user="runtime must be python3.9 .. python3.14. i want newest python",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `provider.runtime` (default python3.12 = the Python running pskit here)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.runtime", value=None),
      ],
      final="""The newest runtime pskit knows is python3.14 [docs/configuration.md#provider]. With `method: local` the host runs on the Python that runs pskit, and a different `runtime` only gives a warning, so I removed the pin; the default python3.12 matches this machine. Validate for onprem: valid. Install a newer Python and run pskit with it if you want 3.13/3.14."""),

    # ------------------------------------------------------------------ 320  service name too long
    C(320, provider="onprem", stage="staging", mode="ask", page="Overview", persona="beginner",
      sources=["docs/configuration.md#top-level"],
      project=dict(files={"pskit.yml": onprem("customer-feedback-collection-service", """functions:
  submit:
    handler: app.feedback.submit
    events:
      - http: POST /feedback
""", **H), **app("feedback", "submit")}),
      user="service must be 2-32 chars... my name is clear and descriptive, why so short?",
      steps=[
          S("get_validation"),
          S("search_docs", query="service name rules length", docs=[TOP]),
          S("ask_user", question="The name becomes part of process, folder and unit names, so it's limited to 32 characters. Is `customer-feedback` OK?",
            options=["customer-feedback", "feedback-service"], answer="customer-feedback"),
          S("propose_plan", steps=["Set `service` to `customer-feedback`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="service", value="customer-feedback"),
      ],
      final="""`service` is 2-32 lowercase letters, digits and `-`, and yours had 36 characters [docs/configuration.md#top-level].

Now `service: customer-feedback`. `pskit validate -p onprem -s staging`: valid. Keep the long description in a function's `description` instead."""),
]
