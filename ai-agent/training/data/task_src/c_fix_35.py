"""Category C (fix a validation error), batch 35 (aws/gcp/azure): user-experience variety. Hand-written;
assembled by tools/assemble.py."""

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


def proj(yml, module, *names, extra=None):
    files = {"pskit.yml": yml, "app/__init__.py": "", f"app/{module}.py": handlers(*names)}
    files.update(extra or {})
    return dict(files=files)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 681  aws beginner: "unable to parse string as an integer"
    C(681, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#queue"],
      project=proj("""service: survey-collector
provider:
  name: aws
  region: eu-west-2
functions:
  collect:
    handler: app.survey.collect
    events:
      - http: POST /answers
  tally:
    handler: app.survey.tally
    events:
      - queue:
          name: answers
          batch_size: 50
          batch_window: 10s
""", "survey", "collect", "tally"),
      user="I don't understand this one: \"Input should be a valid integer, unable to parse string as an integer\". Which string?",
      steps=[
          S("get_validation"),
          S("propose_plan", say="The string is `10s` in `batch_window` of `tally`. pskit wants a plain number of seconds there.",
            steps=["Set `batch_window: 10` on the `answers` trigger", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.tally.events.0.queue.batch_window", value=10),
      ],
      final="""`batch_window` is a whole number of seconds (0-300), so the `s` made it text instead of a number [docs/events.md#queue].

Now `batch_window: 10`: `tally` waits up to 10 seconds to collect up to 50 answers. Validate for aws: valid. The error line starts with the path (`functions.tally.events.0.batch_window`), which tells you where to look."""),

    # ------------------------------------------------------------------ 682  aws Test page: run locally works but there is an error
    C(682, provider="aws", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/providers.md#aws-aws-lambda", "docs/studio.md#test-functions"],
      project=proj("""service: geo-tiles
provider:
  name: aws
  region: us-east-1
functions:
  tile:
    handler: app.tiles.tile
    timeout: 1200
    events:
      - http: GET /tiles/{z}/{x}/{y}
""", "tiles", "tile"),
      user="On the Test page, Run locally returns 200 for tile, but the Problems button shows 1 error. If it runs, what's wrong?",
      steps=[
          S("get_validation"),
          S("search_docs", query="aws lambda limits api gateway 30 s timeout",
            docs=[D("docs/troubleshooting.md", "provider-gotchas", start="| aws |", end="| gcp |")]),
          S("propose_plan", say="Run locally only runs your handler on this machine; it doesn't check AWS limits. The error is an AWS one: `timeout 1200s exceeds AWS Lambda max 900s`.",
            steps=["Set `functions.tile.timeout` to 30 (an HTTP call through API Gateway can't wait longer anyway)", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.tile.timeout", value=30),
      ],
      final="""**▶ Run locally** calls the handler directly (`pskit invoke`), so it doesn't apply the cloud's limits [docs/studio.md#test-functions]. The deploy would fail: Lambda stops at 900 s, and API Gateway gives up on an HTTP call after 30 s [docs/troubleshooting.md#provider-gotchas].

`tile` now has `timeout: 30`. Validate for aws: valid; the Problems button shows 0 errors."""),

    # ------------------------------------------------------------------ 683  aws informal: cors "valid boolean"
    C(683, provider="aws", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=proj("""service: shop-front
provider:
  name: aws
  region: ap-south-1
functions:
  products:
    handler: app.shop.products
    events:
      - http:
          path: /products
          method: GET
          cors:
            origin: https://shop.example.com
""", "shop", "products"),
      user="why it say cors.bool should be valid boolean?? i not write any bool, i write origin only",
      steps=[
          S("get_validation"),
          S("propose_plan", say="`cors` can be `true` or a mapping; pskit tried both. The real problem is the second line: the key is `origins` (a list), not `origin`.",
            steps=["Set `cors: {origins: [\"https://shop.example.com\"]}` on `/products`", "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.products.events.0.http.cors", value={"origins": ["https://shop.example.com"]}),
      ],
      final="""`cors` takes `true` or a mapping, so pskit printed one error for each form: "not a boolean" and "`origin` is not a key". The key is `origins`, with a list [docs/events.md#http].

Now `cors: {origins: ["https://shop.example.com"]}`. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 684  aws wrong fix: paste the secret into pskit.yml
    C(684, provider="aws", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#variables", "docs/troubleshooting.md#configuration"],
      project=proj("""service: checkout
provider:
  name: aws
  region: us-east-1
functions:
  pay:
    handler: app.pay.charge
    environment:
      STRIPE_KEY: ${env:STRIPE_SECRET_KEY}
    events:
      - http: POST /pay
""", "pay", "charge"),
      user="unresolved variables: env:STRIPE_SECRET_KEY. Easiest is if I just paste my Stripe key into pskit.yml instead, right?",
      steps=[
          S("get_validation"),
          S("search_docs", say="Please don't: pskit.yml is usually committed, and then the key is in git for everyone. Let me check the options.",
            query="unresolved variables env default",
            docs=[D("docs/troubleshooting.md", "configuration", start="**`unresolved variables: env:FOO`**", end="`${env:FOO, fallback}`.")]),
          S("propose_plan", steps=["Keep the key out of pskit.yml", "Give the variable a harmless default: `${env:STRIPE_SECRET_KEY, not-set}`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.pay.environment.STRIPE_KEY", value="${env:STRIPE_SECRET_KEY, not-set}"),
      ],
      final="""The error only means `STRIPE_SECRET_KEY` isn't set in this session; `${env:...}` is the right way to keep the key out of the file [docs/configuration.md#variables].

`STRIPE_KEY` is now `${env:STRIPE_SECRET_KEY, not-set}`, so validate works without the key [docs/troubleshooting.md#configuration]. Validate for aws: valid. Before you deploy, set the real key in **Setup & credentials > Environment variables > Set for this session** (or in your shell/CI), otherwise the function gets `not-set`."""),

    # ------------------------------------------------------------------ 685  aws auto terse: hooks pre_deploy
    C(685, provider="aws", stage="prod", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#hooks"],
      project=proj("""service: billing-api
provider:
  name: aws
  region: eu-west-1
hooks:
  pre_deploy: ["python scripts/check_migrations.py"]
functions:
  invoices:
    handler: app.billing.invoices
    events:
      - http: GET /invoices
""", "billing", "invoices", extra={"scripts/check_migrations.py": "print('ok')\n"}),
      user="unknown hooks pre_deploy. rename",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["`hooks.pre_deploy` -> `hooks.before_deploy`", "Validate for aws, stage prod"]),
          S("set_config", path="hooks", value={"before_deploy": ["python scripts/check_migrations.py"]}),
      ],
      final="""`hooks.before_deploy` [docs/configuration.md#hooks]. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 686  aws rejected plan: duplicate route
    C(686, provider="aws", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/troubleshooting.md#configuration"],
      project=proj("""service: orders-api
provider:
  name: aws
  region: us-east-1
functions:
  orders-v2:
    handler: app.orders.list_v2
    events:
      - http: GET /orders
  orders-legacy:
    handler: app.orders.list_legacy
    events:
      - http: GET /orders
""", "orders", "list_v2", "list_legacy"),
      user="I added orders-v2 next to the old function and now staging validate says the route GET /orders is used by both.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove the `GET /orders` trigger from `orders-legacy` (v2 takes over)", "Validate for aws, stage staging"],
            result={"decision": "rejected", "note": "Old mobile clients still call the legacy one. Keep /orders on legacy and give v2 /v2/orders."}),
          S("propose_plan", say="Got it, the old clients keep `/orders`.",
            steps=["Change the route of `orders-v2` to `GET /v2/orders`", "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.orders-v2.events.0", value={"http": "GET /v2/orders"}),
      ],
      final="""A `METHOD /path` can belong to one function only [docs/troubleshooting.md#configuration].

As you asked: `orders-legacy` keeps `GET /orders`, `orders-v2` now answers `GET /v2/orders`. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 687  aws ask_user: service name, rename consequences
    C(687, provider="aws", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/configuration.md#top-level", "docs/configuration.md#functions"],
      project=proj("""service: Order_Service
provider:
  name: aws
  region: us-east-1
functions:
  create:
    handler: app.orders.create
    events:
      - http: POST /orders
""", "orders", "create"),
      user="""got this on my lambda project, what's wrong with the name?
Error: pskit.yml is invalid:
  - service: Value error, service must be 2-32 chars of lowercase letters, digits and dashes""",
      steps=[
          S("get_validation"),
          S("ask_user", question="The service name is part of every cloud resource name (`<service>-<stage>-<function>`), so pick it once. Which name do you want?",
            options=["order-service", "orders"], answer="order-service"),
          S("propose_plan", steps=["Set `service: order-service`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="service", value="order-service"),
      ],
      final="""`service` allows only lowercase letters, digits and dashes (2-32), so the capitals and `_` failed [docs/configuration.md#top-level].

Now `service: order-service`; the function deploys as `order-service-dev-create` [docs/configuration.md#functions]. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 688  gcp beginner: cron in words + timezone
    C(688, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=proj("""service: daily-digest
provider:
  name: gcp
  region: europe-southwest1
  options:
    project: daily-digest-dev
functions:
  digest:
    handler: app.digest.send
    events:
      - schedule:
          cron: every day at 8
""", "digest", "send"),
      user="I want the digest every morning at 8, so I wrote cron: every day at 8. It says cron must be a standard 5-field expression. What are fields?",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule cron fields timezone",
            docs=[D("docs/events.md", "schedule", words=70)]),
          S("ask_user", say="A cron has 5 fields separated by spaces: minute, hour, day of month, month, day of week. Every day at 8:00 is `0 8 * * *`.",
            question="8:00 in which time zone? (GCP supports `timezone`; without it the time is UTC.)", answer="Madrid time"),
          S("propose_plan", steps=["Set the schedule of `digest` to `cron: \"0 8 * * *\"` with `timezone: Europe/Madrid`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.digest.events.0.schedule", value={"cron": "0 8 * * *", "timezone": "Europe/Madrid"}),
      ],
      final="""A cron is five fields, `minute hour day-of-month month day-of-week`, not words [docs/events.md#schedule]. `0 8 * * *` = minute 0, hour 8, every day.

`digest` now runs at `0 8 * * *` with `timezone: Europe/Madrid`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 689  gcp informal: PSOT typo
    C(689, provider="gcp", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=proj("""service: feedback-form
provider:
  name: gcp
  region: southamerica-east1
  options:
    project: feedback-form-staging
functions:
  submit:
    handler: app.feedback.submit
    events:
      - http:
          path: /feedback
          method: PSOT
""", "feedback", "submit"),
      user="it say method must be one of GET, POST... but i write POST?? pskit is bug?",
      steps=[
          S("get_validation"),
          S("propose_plan", say="Not a bug: the file says `PSOT` (two letters swapped).",
            steps=["Set `method: POST` on `/feedback`", "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.submit.events.0.http.method", value="POST"),
      ],
      final="""The method was written `PSOT`, which isn't a real HTTP method [docs/events.md#http].

Fixed to `POST`. `pskit validate -p gcp -s staging`: valid. Tip: in the function's trigger form on the Functions page the method is a list, so this typo can't happen there."""),

    # ------------------------------------------------------------------ 690  gcp pasted partial: extra inputs, where?
    C(690, provider="gcp", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=proj("""service: user-dir
provider:
  name: gcp
  region: us-central1
  options:
    project: user-dir-dev
functions:
  user:
    handler: app.users.get_user
    events:
      - http:
          path: /users/{user-id}
          method: GET
          batch_size: 5
""", "users", "get_user"),
      user="\"Extra inputs are not permitted\" — that's all I see in the banner, the rest is cut off",
      steps=[
          S("get_validation"),
          S("propose_plan", say="There are two errors on the same trigger: `batch_size` is a queue option, and `{user-id}` has a dash.",
            steps=["Remove `batch_size` from the `http` event of `user`", "Rename the path parameter to `{user_id}`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.user.events.0.http", value={"path": "/users/{user_id}", "method": "GET"}),
      ],
      final="""Two problems on the `http` trigger of `user` [docs/events.md#http]:
1. `batch_size` belongs to `queue` events, not `http`.
2. Path parameters are identifiers, so `{user-id}` is invalid; now `{user_id}`.

Validate for gcp: valid. Read it in the handler with `event.http.path_params["user_id"]`. The full list is in the **Problems** panel (top bar), or run `pskit validate -p gcp`."""),

    # ------------------------------------------------------------------ 691  gcp Deploy page: buttons grey
    C(691, provider="gcp", stage="prod", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/events.md#http", "docs/studio.md#what-you-can-do"],
      project=proj("""service: menu-api
provider:
  name: gcp
  region: europe-west2
  options:
    project: menu-api-prod
functions:
  menu:
    handler: app.menu.today
    events:
      - http:
          path: /menu
          method: GET
          auth: key
""", "menu", "today"),
      user="The Deploy button is grey and I can't click it. Is something wrong with my project?",
      steps=[
          S("get_validation"),
          S("propose_plan", say="The buttons on the Deploy page are grey while a job is still running; look at **Recent jobs** on the same page and wait for it to finish. Your project does have one error that would make the deploy fail: `auth: key` isn't supported on GCP.",
            steps=["Set `auth: none` on `GET /menu` (a public menu)", "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.menu.events.0.http.auth", value="none"),
      ],
      final="""Two separate things:
- Grey buttons: a job (validate, package, plan, deploy...) is still running; check **Deploy > Recent jobs** [docs/studio.md#what-you-can-do].
- The project: `auth: key` is Azure/Huawei only, so the GCP deploy would have failed [docs/events.md#http]. `/menu` is now `auth: none`. `pskit validate -p gcp -s prod`: valid.

When the job finishes, press **Deploy**; for `prod` studio asks you to type a confirmation."""),

    # ------------------------------------------------------------------ 692  gcp terse: {user-id}, fix only
    C(692, provider="gcp", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=proj("""service: carts
provider:
  name: gcp
  region: europe-west1
  options:
    project: carts-dev
functions:
  cart-items:
    handler: app.carts.items
    events:
      - http: GET /carts/{cart-id}/items
""", "carts", "items"),
      user="invalid path template /carts/{cart-id}/items. fix",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Route -> `GET /carts/{cart_id}/items`", "Validate for gcp"]),
          S("set_config", path="functions.cart-items.events.0", value={"http": "GET /carts/{cart_id}/items"}),
      ],
      final="""`GET /carts/{cart_id}/items` (params must be identifiers) [docs/events.md#http]. Validate for gcp: valid. Handler: `path_params["cart_id"]`."""),

    # ------------------------------------------------------------------ 693  gcp wrong fix: end: true inside a choice rule
    C(693, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#choice-rules"],
      project=proj("""service: fraud-check
provider:
  name: gcp
  region: us-central1
  options:
    project: fraud-check-staging
functions:
  score:
    handler: app.fraud.score
  review:
    handler: app.fraud.review
workflows:
  check:
    start_at: Score
    states:
      Score: {type: task, function: score, next: Route}
      Route:
        type: choice
        choices:
          - {variable: "$.risk", lt: 20}
        default: Review
      Review: {type: task, function: review, end: true}
""", "fraud", "score", "review"),
      user="choice rule in 'Route' has no `next`. Low risk should just finish the workflow, so I'll add end: true to that rule. OK?",
      steps=[
          S("get_validation"),
          S("search_docs", query="choice rules next succeed state",
            docs=[D("docs/workflows.md", "state-types", start="| `choice` |", end="| `fail` |")]),
          S("propose_plan", say="Not quite: a choice rule only takes `next`; `end: true` in a rule is still rejected with the same error. To finish, point the rule at a `succeed` state.",
            steps=["Add a state `Approved: {type: succeed}`", "Set the rule to `{variable: \"$.risk\", lt: 20, next: Approved}`",
                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.check.states.Approved", value={"type": "succeed"}),
          S("set_config", path="workflows.check.states.Route.choices.0.next", value="Approved"),
      ],
      final="""Choice rules always jump with `next`; to end the run there, the target is a `succeed` state [docs/workflows.md#state-types].

- New state `Approved: {type: succeed}`
- Rule: risk < 20 -> `Approved`; otherwise `default: Review`

`pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 694  gcp approved with a note: database resource
    C(694, provider="gcp", stage="dev", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/configuration.md#resources"],
      project=proj("""service: crm-sync
provider:
  name: gcp
  region: europe-west1
  options:
    project: crm-sync-dev
resources:
  crm-db:
    type: database
    connection: {host: 192.0.2.40, database: crm}
functions:
  sync:
    handler: app.crm.sync
    events:
      - schedule: 30 minutes
""", "crm", "sync"),
      user="In SAM I'd just reference the RDS instance. Here the crm-db resource fails: pskit does not create database resources.",
      steps=[
          S("get_validation"),
          S("search_docs", query="database resource external connection",
            docs=[D("docs/configuration.md", "resources", end="functions: [api]                        # default: every user function")]),
          S("propose_plan", steps=["Set `resources.crm-db.external: true` (the database already exists)", "Validate for gcp"],
            result={"decision": "approved", "note": "Fine, and add the port 5432 and password_env CRM_DB_PASSWORD to the connection while you're at it."}),
          S("set_config", path="resources.crm-db",
            value={"type": "database", "external": True,
                   "connection": {"host": "192.0.2.40", "port": 5432, "database": "crm", "password_env": "CRM_DB_PASSWORD"}}),
      ],
      final="""Databases are always existing services for pskit: you mark them `external: true` and describe them in `connection`, much like referencing an RDS instance in SAM [docs/configuration.md#resources].

`crm-db` now has `external: true` and, as you added, `port: 5432` and `password_env: CRM_DB_PASSWORD` next to host and database. Validate for gcp: valid. The handler reads them with `resource("crm-db")`; set `CRM_DB_PASSWORD` in the function's environment, not in pskit.yml."""),

    # ------------------------------------------------------------------ 695  azure beginner: - cron:
    C(695, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=proj("""service: backup-runner
provider:
  name: azure
  region: westeurope
functions:
  backup:
    handler: app.backup.run
    events:
      - cron: "0 1 * * *"
""", "backup", "run"),
      user="I just want my backup to run every night at 1. It says unknown event type 'cron'. Isn't cron the normal word?",
      steps=[
          S("get_validation"),
          S("propose_plan", say="Cron is the right idea; in pskit the trigger is called `schedule`, and the cron string goes inside it.",
            steps=["Replace the trigger with `schedule: \"0 1 * * *\"`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.backup.events.0", value={"schedule": "0 1 * * *"}),
      ],
      final="""Timers are `schedule` events; you can give them a cron string directly [docs/events.md#schedule].

`backup` now has `- schedule: "0 1 * * *"`. Validate for azure: valid. On Azure the time is UTC, so this runs at 01:00 UTC."""),

    # ------------------------------------------------------------------ 696  azure informal: two triggers in one item
    C(696, provider="azure", stage="staging", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/troubleshooting.md#configuration"],
      project=proj("""service: label-printer
provider:
  name: azure
  region: northeurope
functions:
  print-label:
    handler: app.labels.print_label
    events:
      - http: POST /labels
        queue: label-jobs
""", "labels", "print_label"),
      user="i want the function start from http and also from queue. yaml say must be single-key mapping, what mean single key",
      steps=[
          S("get_validation"),
          S("propose_plan", say="Single key = each `-` item has exactly one trigger. Two triggers are two items in the list.",
            steps=["Split into two items: `- http: POST /labels` and `- queue: label-jobs`", "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.print-label.events", value=[{"http": "POST /labels"}, {"queue": "label-jobs"}]),
      ],
      final="""Each `-` item under `events` is one trigger; you had `http` and `queue` in the same item [docs/troubleshooting.md#configuration].

Now:
```yaml
events:
  - http: POST /labels
  - queue: label-jobs
```
`pskit validate -p azure -s staging`: valid. The function now starts from both."""),

    # ------------------------------------------------------------------ 697  azure pasted partial: auth: true
    C(697, provider="azure", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=proj("""service: admin-tools
provider:
  name: azure
  region: westeurope
functions:
  purge-cache:
    handler: app.admin.purge_cache
    events:
      - http:
          path: /admin/purge
          method: POST
          auth: true
""", "admin", "purge_cache"),
      user="Input should be 'none', 'iam', 'jwt' or 'key'\n\nI just want it protected",
      steps=[
          S("get_validation"),
          S("propose_plan", say="`auth` takes a name, not `true`. On Azure \"protected\" means `key`: callers must send the function key.",
            steps=["Set `auth: key` on `POST /admin/purge`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.purge-cache.events.0.http.auth", value="key"),
      ],
      final="""`auth` is one of `none`, `iam`, `jwt`, `key`; on Azure the protected choice is `key` (function key) [docs/events.md#http].

`/admin/purge` now has `auth: key`. Validate for azure: valid. After deploy, requests without the function key get 401."""),

    # ------------------------------------------------------------------ 698  azure auto: /items vs /items/
    C(698, provider="azure", stage="dev", mode="auto", page="Functions", persona="detailed_spec",
      sources=["docs/troubleshooting.md#configuration"],
      project=proj("""service: inventory
provider:
  name: azure
  region: westeurope
functions:
  list-items:
    handler: app.items.list_items
    events:
      - http: GET /items
  search-items:
    handler: app.items.search
    events:
      - http: GET /items/
""", "items", "list_items", "search"),
      user="search-items was meant to be the search endpoint. I gave it /items/ with a trailing slash so it's different from list-items, but validate still says the route is used by both.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Change the route of `search-items` to `GET /items/search`", "Validate for azure"]),
          S("set_config", path="functions.search-items.events.0", value={"http": "GET /items/search"}),
      ],
      final="""`/items` and `/items/` count as the same path, so the slash didn't separate them [docs/troubleshooting.md#configuration].

`search-items` now answers `GET /items/search`; `list-items` keeps `GET /items`. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 699  azure ask_user: Node.js version
    C(699, provider="azure", stage="dev", mode="ask", page="Overview", persona="terse_expert",
      sources=["docs/providers.md#azure-azure-functions"],
      project=dict(files={"pskit.yml": """service: badge-api
provider:
  name: azure
  region: westeurope
  runtime: nodejs16
functions:
  badge:
    handler: src.badge.render
    events:
      - http: GET /badge/{name}
""", "src/badge.js": "exports.render = async (event, ctx) => ({ ok: true });\n",
          "package.json": "{\"name\": \"badge-api\", \"version\": \"1.0.0\", \"private\": true}\n"}),
      user="runtime nodejs16 rejected",
      steps=[
          S("get_validation"),
          S("ask_user", question="Node 16 isn't accepted; Azure takes nodejs18, nodejs20 or nodejs22. Which one?",
            options=["nodejs18", "nodejs20", "nodejs22"], answer="nodejs20"),
          S("propose_plan", steps=["`provider.runtime: nodejs20`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.runtime", value="nodejs20"),
      ],
      final="""`provider.runtime: nodejs20` (Azure: Node 18/20/22) [docs/providers.md#azure-azure-functions]. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 700  azure rejected plan: queue name the producer uses
    C(700, provider="azure", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=proj("""service: invoice-mailer
provider:
  name: azure
  region: westeurope
functions:
  mail-invoice:
    handler: app.invoices.mail
    events:
      - queue: Invoice_Jobs
""", "invoices", "mail"),
      user="prod validate red on queue name Invoice_Jobs. pls fix",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename the queue to `invoice-jobs`", "Validate for azure, stage prod"],
            result={"decision": "rejected", "note": "no, the billing system already write to queue 'invoicejobs', use exactly that"}),
          S("propose_plan", say="OK, I'll use the name the billing system already writes to.",
            steps=["Set the queue of `mail-invoice` to `invoicejobs`", "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.mail-invoice.events.0", value={"queue": "invoicejobs"}),
      ],
      final="""Azure queue names allow only lowercase letters, digits and dashes, so `Invoice_Jobs` failed (capitals and `_`) [docs/events.md#queue].

As you asked, `mail-invoice` now listens on `invoicejobs`. `pskit validate -p azure -s prod`: valid. If billing created that queue itself (outside pskit), say so and I'll add `existing: true` so the deploy doesn't try to create it."""),
]
