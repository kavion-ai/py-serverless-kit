"""Category C (fix a validation error), batch 10: on-premises projects: event shapes, secrets, overrides, warnings.
Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def C(n, **kw):
    return dict(id=f"c_fix-{n:04d}", category="c_fix", **kw)


def handlers(*names):
    body = FUTURE
    for name in names:
        body += f"\ndef {name}(event, ctx):\n    return {{\"ok\": True, \"fn\": \"{name}\"}}\n\n"
    return body.rstrip() + "\n"


def app(module, *names):
    return {"app/__init__.py": "", f"app/{module}.py": handlers(*names)}


def onprem(service, rest, port=8080, host="127.0.0.1"):
    """Header of a local on-prem pskit.yml (scaffolding); `rest` is the hand-written part."""
    return f"""service: {service}
provider:
  name: onprem
  region: local
  options:
    host: {host}
    port: {port}
{rest}"""


SCHEDULE = D("docs/events.md", "schedule", start="```yaml", end="```")
SECRETS_CFG = D("docs/configuration.md", "variables", start="Secrets: don't put them in YAML.", end="Secrets: don't put them in YAML.")
ENV_FILE = D("docs/providers.md", "onprem-on-premises", start="env_file: .env.onprem", end="never written to Terraform state")
LIMITS = D("docs/providers.md", "onprem-on-premises", start="**Limits:** no cloud authorizer", end="**Limits:** no cloud authorizer")

CONVERSATIONS = [
    # ------------------------------------------------------------------ 181  - cron: event
    C(181, provider="onprem", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={"pskit.yml": onprem("clean-tmp", """functions:
  clean:
    handler: app.tmp.clean
    events:
      - cron: "0 4 * * *"
"""), **app("tmp", "clean")}),
      user="unknown event type 'cron'?? i want cron every day 4 am",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule cron event", docs=[SCHEDULE]),
          S("propose_plan", steps=["Change the event to `- schedule: \"0 4 * * *\"`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.clean.events.0", value={"schedule": "0 4 * * *"}),
      ],
      final="""There's no `cron` event: a cron goes under `schedule` [docs/events.md#schedule].

Now `- schedule: "0 4 * * *"`, every day at 04:00. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 182  batch_size under http
    C(182, provider="onprem", stage="staging", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={"pskit.yml": onprem("bulk-import", """functions:
  import-rows:
    handler: app.bulk.import_rows
    events:
      - http: {path: /import, method: POST, batch_size: 100}
""", host="0.0.0.0"), **app("bulk", "import_rows")}),
      user="""  - functions.import-rows.events.0.batch_size: Extra inputs are not permitted""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `functions.import-rows.events.0.http.batch_size` (queue-only)", "Validate for onprem, stage staging"]),
          S("set_config", path="functions.import-rows.events.0.http.batch_size", value=None),
      ],
      final="""`batch_size` belongs to `queue` events; an HTTP request is always one call [docs/events.md#http]. Removed it. `pskit validate -p onprem -s staging`: valid. To process rows in batches of 100, have the handler put them on a queue with `batch_size: 100`."""),

    # ------------------------------------------------------------------ 183  cors origin
    C(183, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={"pskit.yml": onprem("menu-api", """functions:
  menu:
    handler: app.menu.items
    events:
      - http:
          path: /menu
          method: GET
          cors: {origin: "http://192.0.2.50:3000"}
"""), **app("menu", "items")}),
      user="My React app on http://192.0.2.50:3000 needs CORS. I wrote cors origin but there are two strange errors about bool and origin.",
      steps=[
          S("get_validation"),
          S("search_docs", query="cors origins mapping", docs=[
              D("docs/events.md", "http", start="**CORS**", end="max_age")]),
          S("propose_plan", steps=["Set `functions.menu.events.0.http.cors` to `{origins: [\"http://192.0.2.50:3000\"]}`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.menu.events.0.http.cors", value={"origins": ["http://192.0.2.50:3000"]}),
      ],
      final="""`cors` is either `true` or a mapping, and the mapping's key is `origins` (a list), not `origin`. That's why you got two errors for one mistake [docs/events.md#http].

Now `cors: {origins: ["http://192.0.2.50:3000"]}`. Validate for onprem: valid. Your React app can call `/menu` from that address."""),

    # ------------------------------------------------------------------ 184  literal password in environment
    C(184, provider="onprem", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/configuration.md#variables", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("ldap-sync", """functions:
  sync-users:
    handler: app.ldap.sync_users
    environment:
      LDAP_HOST: 192.0.2.60
      LDAP_BIND_PASSWORD: changeme-123
    events:
      - schedule: 1 hour
""", host="0.0.0.0"), **app("ldap", "sync_users")}),
      user="Before we put this repo on our Git server: validation passes, but is anything in pskit.yml that shouldn't be committed? The LDAP password is managed by ops; they can put an env file on the server.",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("search_docs", query="secrets env_file onprem", docs=[SECRETS_CFG, ENV_FILE]),
          S("propose_plan", steps=["Remove the literal `LDAP_BIND_PASSWORD` from `functions.sync-users.environment`",
                                   "Set `provider.options.env_file: .env.onprem` (ops add the password line there)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.sync-users.environment.LDAP_BIND_PASSWORD", value=None),
          S("set_config", path="provider.options.env_file", value=".env.onprem"),
      ],
      final="""Yes: `LDAP_BIND_PASSWORD` was written in pskit.yml in plain text. Secrets don't belong in YAML [docs/configuration.md#variables].

Changed:
- removed `LDAP_BIND_PASSWORD` from `environment` (`LDAP_HOST` stays);
- added `env_file: .env.onprem`: the host loads that `KEY=VALUE` file at start, and it is never written to Terraform state [docs/providers.md#onprem-on-premises].

`pskit validate -p onprem -s prod`: valid, with a WARNING that `.env.onprem` doesn't exist yet. Ops create it with the `LDAP_BIND_PASSWORD` line, and it stays out of git. The handler reads `ctx.env["LDAP_BIND_PASSWORD"]` as before. Change that LDAP password, because the old one was in the file."""),

    # ------------------------------------------------------------------ 185  literal password in connection
    C(185, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#secrets", "docs/resources.md#fields"],
      project=dict(files={"pskit.yml": onprem("pos-report", """resources:
  pos-db:
    type: database
    external: true
    connection: {host: 192.0.2.20, port: 3306, database: pos, user: report, password: changeme-123}
functions:
  daily:
    handler: app.pos.daily
    events:
      - schedule: "0 23 * * *"
"""), **app("pos", "daily")}),
      user="validate ok but my friend say password in the resources is bad. how to do correct",
      steps=[
          S("get_validation"),
          S("search_docs", query="resource connection password secret", docs=[
              D("docs/resources.md", "secrets", words=150)]),
          S("ask_user", question="What should the environment variable with the database password be called?",
            options=["POS_DB_PASSWORD", "another name"], answer="POS_DB_PASSWORD"),
          S("propose_plan", steps=["Delete `resources.pos-db.connection.password`",
                                   "Add `connection.password_env: POS_DB_PASSWORD` (only the variable name)",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.pos-db.connection.password", value=None),
          S("set_config", path="resources.pos-db.connection.password_env", value="POS_DB_PASSWORD"),
      ],
      final="""Your friend is right: `connection` values are handed to the functions as they are, so the password was in the file [docs/resources.md#fields].

Now `connection` has `password_env: POS_DB_PASSWORD` instead of the password. Validate for onprem: valid. Set `POS_DB_PASSWORD` where the host runs (or in an `env_file`), and in `daily` read it with `ctx.env[...]` using that name [docs/resources.md#secrets]. Also change the database password, because the old one was written in the file."""),

    # ------------------------------------------------------------------ 186  service name with capitals
    C(186, provider="onprem", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/configuration.md#top-level"],
      project=dict(files={"pskit.yml": """service: My_Shop
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
functions:
  home:
    handler: app.shop.home
    events:
      - http: GET /
""", **app("shop", "home")}),
      user="I named my project My_Shop and validate says service must be 2-32 chars of lowercase... can I keep the name?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `service` to `my-shop`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="service", value="my-shop"),
      ],
      final="""Almost: the service name becomes part of folder, process and unit names, so only lowercase letters, digits and dashes are allowed [docs/configuration.md#top-level].

I changed it to `service: my-shop`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 187  runtime python3.8
    C(187, provider="onprem", stage="dev", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/configuration.md#provider", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": """service: legacy-lambda
provider:
  name: onprem
  region: local
  runtime: python3.8
  options:
    host: 127.0.0.1
    port: 8080
functions:
  handler:
    handler: app.legacy.handler
    events:
      - http: POST /legacy
""", **app("legacy", "handler")}),
      user="This Lambda was on python3.8. Moving it on-prem, validation rejects the runtime. Which one should I pick for a local host?",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem runtime interpreter local", docs=[LIMITS]),
          S("propose_plan", steps=["Set `provider.runtime` to `python3.12` (the interpreter running pskit here)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.runtime", value="python3.12"),
      ],
      final="""pskit supports python3.9 and newer, so 3.8 is rejected. With `method: local` the host uses the interpreter that runs `pskit`, and validation warns when `provider.runtime` is different [docs/providers.md#onprem-on-premises].

Set `runtime: python3.12`, the Python here. Validate for onprem: valid, no warning. Run your Lambda code locally once (**Test** > **▶ Run locally**), since 3.8 to 3.12 can surface old library versions."""),

    # ------------------------------------------------------------------ 188  hooks pre_deploy
    C(188, provider="onprem", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#hooks"],
      project=dict(files={"pskit.yml": onprem("assets", """hooks:
  pre_deploy: [npm run build]
functions:
  site:
    handler: app.site.index
    events:
      - http: GET /
"""), **app("site", "index")}),
      user="unknown hooks ['pre_deploy']. run build before deploy",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `hooks.pre_deploy` to `hooks.before_deploy`", "Validate for onprem"]),
          S("set_config", path="hooks.pre_deploy", value=None),
          S("set_config", path="hooks.before_deploy", value=["npm run build"]),
      ],
      final="""Hook names are `before_` / `after_` + package, deploy or remove [docs/configuration.md#hooks]. Now `before_deploy: [npm run build]`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 189  storage event on queue resource
    C(189, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#using-a-resource-from-an-event"],
      project=dict(files={"pskit.yml": onprem("label-scan", """resources:
  labels:
    type: queue
functions:
  read-label:
    handler: app.labels.read
    events:
      - storage: {resource: labels, suffix: .png}
"""), **app("labels", "read")}),
      user="""  - <root>: Value error, function 'read-label' has a storage event on resource 'labels', which is a queue

the label pictures are files, i picked wrong type in the wizard""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.labels.type` to `storage`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.labels.type", value="storage"),
      ],
      final="""A storage event needs a storage resource, and `labels` was a queue [docs/resources.md#using-a-resource-from-an-event].

Changed `labels` to `type: storage`. Validate for onprem: valid. New `.png` files in the `labels` bucket now run `read-label`."""),

    # ------------------------------------------------------------------ 190  both name and resource
    C(190, provider="onprem", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/resources.md#using-a-resource-from-an-event"],
      project=dict(files={"pskit.yml": onprem("dispatch", """resources:
  dispatch-jobs:
    type: queue
    name: dispatch
functions:
  assign-driver:
    handler: app.dispatch.assign
    events:
      - queue: {resource: dispatch-jobs, name: dispatch-jobs, batch_size: 5}
""", host="0.0.0.0"), **app("dispatch", "assign")}),
      user="Staging validation says set either `name` or `resource` on the queue event, not both. I added `name: dispatch-jobs` because I thought the event also needs the queue's name. Keep the resource.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `functions.assign-driver.events.0.queue.name` (the resource already names the queue)",
                                   "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.assign-driver.events.0.queue.name", value=None),
      ],
      final="""With `resource`, the queue's name comes from the resource itself (`name: dispatch`), so the event takes `name` or `resource`, not both. Your `name: dispatch-jobs` was also the resource key, not the queue name `dispatch` [docs/resources.md#using-a-resource-from-an-event].

Removed `name` from the event: `queue: {resource: dispatch-jobs, batch_size: 5}`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 191  connection nested value
    C(191, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#fields"],
      project=dict(files={"pskit.yml": onprem("ticket-db", """resources:
  tickets-db:
    type: database
    external: true
    connection:
      host: 192.0.2.20
      port: 5432
      auth: {user: tickets, password_env: TICKETS_DB_PASSWORD}
functions:
  open-tickets:
    handler: app.tickets.open_tickets
    events:
      - http: GET /tickets
"""), **app("tickets", "open_tickets")}),
      user="connection.auth must be a scalar. what is scalar",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace `connection.auth` with flat keys `user: tickets` and `password_env: TICKETS_DB_PASSWORD`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.tickets-db.connection",
            value={"host": "192.0.2.20", "port": 5432, "user": "tickets", "password_env": "TICKETS_DB_PASSWORD"}),
      ],
      final="""A scalar is one plain value (text, number or true/false). `connection` values can't be another mapping like `auth: {...}` [docs/resources.md#fields].

I made it flat: `connection: {host: 192.0.2.20, port: 5432, user: tickets, password_env: TICKETS_DB_PASSWORD}`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 192  connection reserved name
    C(192, provider="onprem", stage="dev", mode="auto", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#fields"],
      project=dict(files={"pskit.yml": onprem("hr-db", """resources:
  hr:
    type: database
    external: true
    connection: {host: 192.0.2.20, port: 5432, name: hr_main}
functions:
  staff:
    handler: app.hr.staff
    events:
      - http: GET /staff
"""), **app("hr", "staff")}),
      user="""  - resources.hr.connection: Value error, connection key 'name' is reserved (set `name` on the resource itself)

name = the postgres database name""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `connection.name` to `connection.database` (value `hr_main`)", "Validate for onprem"]),
          S("set_config", path="resources.hr.connection", value={"host": "192.0.2.20", "port": 5432, "database": "hr_main"}),
      ],
      final="""`name`, `type` and `external` are reserved in `connection` [docs/resources.md#fields]. For the Postgres database name I used `database: hr_main`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 193  stages.prod port override out of range
    C(193, provider="onprem", stage="prod", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("warehouse", """functions:
  pick-list:
    handler: app.warehouse.pick_list
    events:
      - http: GET /pick-list
stages:
  prod:
    provider:
      options:
        port: 80800
"""), **app("warehouse", "pick_list")}),
      user="dev validates, prod: options.port must be an integer from 1 to 65535. prod port is 8088",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `stages.prod.provider.options.port` to 8088", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.provider.options.port", value=8088),
      ],
      final="""Only the prod override had the bad port (`80800`, above 65535); dev uses the top-level 8080 [docs/configuration.md#stages-per-stage-overrides]. Set `stages.prod.provider.options.port: 8088`. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 194  multi-cloud: iam fine on aws, not onprem
    C(194, provider="onprem", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#providers-per-cloud-overrides", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": """service: price-api
provider:
  name: aws
  region: eu-central-1
providers:
  onprem:
    region: local
    options: {host: 0.0.0.0, port: 8080}
functions:
  prices:
    handler: app.prices.list_prices
    events:
      - http: {path: /prices, method: GET, auth: iam}
""", **app("prices", "list_prices")}),
      user="Same pskit.yml goes to AWS and to our factory server. Validate for aws passes, but with the target set to onprem `prices` fails on auth iam. AWS must keep IAM auth. Fix only the onprem side.",
      steps=[
          S("get_validation"),
          S("search_docs", query="per-cloud override functions events", docs=[
              D("docs/configuration.md", "providers-per-cloud-overrides", words=170)]),
          S("propose_plan", steps=["Add `providers.onprem.functions.prices.events: [{http: {path: /prices, method: GET, auth: none}}]`",
                                   "Validate for onprem", "Validate for aws (unchanged)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.onprem.functions.prices.events",
            value=[{"http": {"path": "/prices", "method": "GET", "auth": "none"}}]),
          S("validate", provider="aws"),
      ],
      final="""The on-premises host has no IAM, so `auth` must be `none` there [docs/providers.md#onprem-on-premises]. A `providers.onprem` block changes only that target [docs/configuration.md#providers-per-cloud-overrides].

Added:

```yaml
providers:
  onprem:
    functions:
      prices:
        events:
          - http: {path: /prices, method: GET, auth: none}
```

- Validate for onprem: valid.
- Validate for aws: still valid, with `auth: iam` on API Gateway.

On the factory server `/prices` is open, so check a token in the handler for that target if it needs protection."""),

    # ------------------------------------------------------------------ 195  ${env:...} in deploy.host without default
    C(195, provider="onprem", stage="staging", mode="ask", page="Setup", persona="beginner",
      sources=["docs/configuration.md#variables"],
      project=dict(files={"pskit.yml": onprem("factory-api", """    deploy:
      method: ssh
      host: ${env:PSKIT_ONPREM_HOST}
      user: pskit
      python: bundle
      target_os: linux
functions:
  hello:
    handler: app.factory.hello
    events:
      - http: GET /hello
""", host="0.0.0.0"), **app("factory", "hello")}),
      user="I copied the remote example. Now validate says unresolved variables: env:PSKIT_ONPREM_HOST. What should I do?",
      steps=[
          S("get_validation"),
          S("ask_user", question="That line reads the server address from the `PSKIT_ONPREM_HOST` environment variable, which isn't set. What is the staging server's address? I'll use it as the default.",
            answer="203.0.113.21"),
          S("propose_plan", steps=["Set `provider.options.deploy.host` to `${env:PSKIT_ONPREM_HOST, 203.0.113.21}`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.host", value="${env:PSKIT_ONPREM_HOST, 203.0.113.21}"),
      ],
      final="""`${env:PSKIT_ONPREM_HOST}` without a default is an error when the variable isn't set [docs/configuration.md#variables].

Now `host: ${env:PSKIT_ONPREM_HOST, 203.0.113.21}`: it uses the variable when it's set, and otherwise your staging server. Validate for onprem staging: valid."""),

    # ------------------------------------------------------------------ 196  state backend s3 (warning)
    C(196, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises", "docs/configuration.md#state-remote-terraform-backend"],
      project=dict(files={"pskit.yml": """service: hybrid-api
provider:
  name: aws
  region: us-east-1
  state:
    backend: s3
    config: {bucket: acme-tf-state, key: hybrid-api.tfstate, region: us-east-1}
providers:
  onprem:
    region: local
    options: {host: 127.0.0.1, port: 8080}
functions:
  status:
    handler: app.hybrid.status
    events:
      - http: GET /status
""", **app("hybrid", "status")}),
      user="Our AWS stacks keep Terraform state in S3. With the onprem target, validate warns that the state backend still points at a cloud. The on-prem box has no AWS access. What should I change?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Add `providers.onprem.state.backend: \"\"` (local state for the onprem target only)",
                                   "Validate for onprem", "Validate for aws (unchanged)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.onprem.state", value={"backend": ""}),
          S("validate", provider="aws"),
      ],
      final="""With no AWS access, an S3 backend would fail on that machine. The fix the docs give is to set `provider.state.backend` empty under `providers.onprem`, which keeps state local [docs/providers.md#onprem-on-premises].

Added `providers.onprem.state: {backend: ""}`.
- Validate for onprem: valid, no warning.
- Validate for aws: valid; AWS still uses the S3 backend.

On-premises state now stays under `.pskit/onprem-<stage>/` on the machine that runs `pskit deploy`, so back that folder up."""),

    # ------------------------------------------------------------------ 197  terraform.extra aws resource (warning)
    C(197, provider="onprem", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": """service: orders
provider:
  name: aws
  region: us-east-1
  terraform:
    extra:
      resource:
        aws_dynamodb_table:
          orders: {name: orders, hash_key: id, billing_mode: PAY_PER_REQUEST, attribute: [{name: id, type: S}]}
providers:
  onprem:
    region: local
    options: {host: 127.0.0.1, port: 8080}
functions:
  create:
    handler: app.orders.create
    events:
      - http: POST /orders
""", **app("orders", "create")}),
      user="With the onprem target validate warns that terraform.extra resources are omitted: aws_dynamodb_table. On AWS we need the table; on-prem we use SQLite. Can I make the warning go away without losing the table on AWS?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Move `provider.terraform.extra` to `providers.aws.terraform.extra` (AWS only)",
                                   "Validate for onprem", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.aws", value={"terraform": {"extra": {"resource": {"aws_dynamodb_table": {"orders": {
              "name": "orders", "hash_key": "id", "billing_mode": "PAY_PER_REQUEST", "attribute": [{"name": "id", "type": "S"}]}}}}}}),
          S("set_config", path="provider.terraform", value=None),
          S("validate", provider="aws"),
      ],
      final="""The table was in the shared `provider.terraform.extra`, so every target got it, and on-premises deploy doesn't load the AWS Terraform provider [docs/providers.md#onprem-on-premises].

I moved it to `providers.aws.terraform.extra`:
- Validate for onprem: valid, no warning.
- Validate for aws: valid; the `orders` table is still created there."""),

    # ------------------------------------------------------------------ 198  systemd on a local Windows deploy
    C(198, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("door-sensor", """    deploy:
      install: systemd
functions:
  door:
    handler: app.door.event
    events:
      - http: POST /door
"""), **app("door", "event")}),
      user="i test on my windows laptop first. deploy install systemd error 'only valid when target_os is linux'. on the real server later is linux",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `provider.options.deploy` for now (local process on this laptop)",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy", value=None),
      ],
      final="""Without `method`, deploy is `local`, so the target is your Windows laptop, and systemd exists only on Linux [docs/providers.md#onprem-on-premises].

I removed the `deploy` block, so it runs as a normal process on the laptop. Validate for onprem: valid. For the Linux server later, add `deploy: {method: ssh, host: ..., install: systemd, sudo: true}`, or put it under `stages.prod` so dev stays local."""),

    # ------------------------------------------------------------------ 199  rate in seconds
    C(199, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("heartbeat", """functions:
  beat:
    handler: app.beat.send
    events:
      - schedule: 90 seconds
"""), **app("beat", "send")}),
      user="I want the heartbeat every 90 seconds. Validate says cron must be a standard 5-field expression. I didn't write a cron?",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule rate units minutes", docs=[SCHEDULE]),
          S("ask_user", question="Schedules count in minutes, hours or days, not seconds. Which is closer to what you need?",
            options=["every 1 minute", "every 2 minutes"], answer="every 1 minute"),
          S("propose_plan", steps=["Set `functions.beat.events.0.schedule` to `1 minute`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.beat.events.0.schedule", value="1 minute"),
      ],
      final="""`90 seconds` isn't a valid rate (only minutes, hours or days), so pskit tried to read it as a cron and failed [docs/events.md#schedule].

Now `- schedule: 1 minute`. Validate for onprem: valid. The on-premises host runs rates itself, in-process [docs/providers.md#onprem-on-premises]."""),

    # ------------------------------------------------------------------ 200  existing queue name under resources with unknown provider option
    C(200, provider="onprem", stage="prod", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("intake", """    execution_retention: 0
functions:
  intake:
    handler: app.intake.receive
    events:
      - http: POST /intake
  route:
    handler: app.intake.route
workflows:
  triage:
    start_at: Route
    states:
      Route: {type: task, function: route, end: true}
""", host="0.0.0.0"), **app("intake", "receive", "route")}),
      user="""  ERROR: [provider.options.execution_retention] options.execution_retention must be an integer >= 1

we don't need workflow history in prod, keep as little as possible""",
      steps=[
          S("get_validation"),
          S("search_docs", query="execution_retention", docs=[
              D("docs/providers.md", "onprem-on-premises", start="execution_retention: 500", end="execution_retention: 500")]),
          S("propose_plan", steps=["Set `provider.options.execution_retention` to 1 (the minimum)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.execution_retention", value=1),
      ],
      final="""`execution_retention` is how many finished workflow executions are kept, and it must be at least 1 [docs/providers.md#onprem-on-premises].

Set `execution_retention: 1`: only the latest finished `triage` run is kept under `<data_dir>/executions`. `pskit validate -p onprem -s prod`: valid."""),
]
