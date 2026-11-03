"""Category C (fix a validation error), batch 37 (aws/gcp/azure): user-experience variety. Hand-written;
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
    # ------------------------------------------------------------------ 721  aws beginner on Code page: handler with a slash
    C(721, provider="aws", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: book-club
provider:
  name: aws
  region: us-east-1
functions:
  books:
    handler: app/books.list_books
    events:
      - http: GET /books
""", "books", "list_books"),
      user="On the Code page my file is app/books.py with def list_books. I wrote handler app/books.list_books and it says it must be 'package.module.function'. What do I write?",
      steps=[
          S("get_validation"),
          S("read_file", path="app/books.py"),
          S("propose_plan", say="Use dots instead of the slash: folder `app` . file `books` (without .py) . function `list_books`.",
            steps=["Set `functions.books.handler` to `app.books.list_books`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.books.handler", value="app.books.list_books"),
      ],
      final="""A handler is written like a Python import, with dots: `app.books.list_books` [docs/configuration.md#functions].

`books` now has `handler: app.books.list_books`. Validate for aws: valid. On the Functions page, the function's **Open code** button jumps to that file, so you can check the name matches."""),

    # ------------------------------------------------------------------ 722  aws informal: {path+} not last
    C(722, provider="aws", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=proj("""service: file-api
provider:
  name: aws
  region: eu-west-1
functions:
  file-info:
    handler: app.files.info
    events:
      - http: GET /files/{path+}/info
""", "files", "info"),
      user="i want url /files/a/b/c.txt/info for give file info, pskit say invalid path template. why",
      steps=[
          S("get_validation"),
          S("ask_user", say="`{path+}` (the part with slashes) may only be the last piece of the path, so nothing can come after it.",
            question="Two options: move `info` before the path (`GET /files-info/{path+}`), or keep `/files/{path+}` and pass `?info=1`. Which?",
            options=["/files-info/{path+}", "/files/{path+} with ?info=1"], answer="/files-info/{path+}"),
          S("propose_plan", steps=["Set the route of `file-info` to `GET /files-info/{path+}`", "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.file-info.events.0", value={"http": "GET /files-info/{path+}"}),
      ],
      final="""A greedy `{path+}` matches the rest of the URL, so it must be the last segment [docs/events.md#http].

`file-info` now answers `GET /files-info/{path+}`, e.g. `/files-info/a/b/c.txt`; the handler gets `a/b/c.txt` in `event.http.path_params["path"]`. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 723  aws pasted partial: valid list (events mapping)
    C(723, provider="aws", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#functions", "docs/troubleshooting.md#configuration"],
      project=proj("""service: weather-api
provider:
  name: aws
  region: us-east-2
functions:
  forecast:
    handler: app.weather.forecast
    events:
      http: GET /forecast
""", "weather", "forecast"),
      user="Input should be a valid list",
      steps=[
          S("get_validation"),
          S("propose_plan", say="It's `events` of `forecast`: it is written as a mapping (`http:` directly under it) instead of a list item (`- http:`).",
            steps=["Write `events` as a list: `- http: GET /forecast`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.forecast.events", value=[{"http": "GET /forecast"}]),
      ],
      final="""`events` is a list, so each trigger starts with `- ` [docs/configuration.md#functions] [docs/troubleshooting.md#configuration]:
```yaml
events:
  - http: GET /forecast
```
Validate for aws: valid."""),

    # ------------------------------------------------------------------ 724  aws auto terse: concurrency auto
    C(724, provider="aws", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: search-api
provider:
  name: aws
  region: us-east-1
functions:
  search:
    handler: app.search.query
    concurrency: auto
    events:
      - http: GET /search
""", "search", "query"),
      user="concurrency: auto -> not an int. want unreserved",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `concurrency` from `search` (no reserved concurrency)", "Validate for aws, stage prod"]),
          S("set_config", path="functions.search.concurrency", value=None),
      ],
      final="""Removed `concurrency`: unset = no reservation; it only takes an int >= 0 [docs/configuration.md#functions]. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 725  aws user proposes a fix that is right
    C(725, provider="aws", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/configuration.md#variables"],
      project=proj("""service: partner-feed
provider:
  name: aws
  region: eu-west-1
functions:
  feed:
    handler: app.feed.items
    events:
      - http:
          path: /feed
          method: GET
          auth: key
""", "feed", "items"),
      user="API keys are not available on API Gateway HTTP APIs. Plan: auth: none, and the handler compares the x-api-key header with an env var that holds the key. Does that work with pskit?",
      steps=[
          S("get_validation"),
          S("search_docs", query="http auth support aws",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("propose_plan", say="Yes, that works: `none` is supported everywhere, and the key stays out of the file with `${env:...}`.",
            steps=["Set `auth: none` on `GET /feed`", "Add `environment: {FEED_API_KEY: ${env:FEED_API_KEY, not-set}}` to `feed`",
                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.feed.events.0.http.auth", value="none"),
          S("set_config", path="functions.feed.environment", value={"FEED_API_KEY": "${env:FEED_API_KEY, not-set}"}),
      ],
      final="""Your plan is right: AWS has no `key` auth in pskit, and `none` plus a check in the handler is a valid replacement [docs/events.md#http].

- `/feed`: `auth: none`
- `feed.environment.FEED_API_KEY: ${env:FEED_API_KEY, not-set}` [docs/configuration.md#variables]

`pskit validate -p aws -s staging`: valid. In the handler, compare `event.http.headers.get("x-api-key")` with `os.environ["FEED_API_KEY"]` (use `hmac.compare_digest`) and return 401 when they differ or the value is `not-set`. Set the real key before deploying."""),

    # ------------------------------------------------------------------ 726  aws rejected plan: python3.14 -> keep 3.13
    C(726, provider="aws", stage="dev", mode="ask", page="Overview", persona="terse_expert",
      sources=["docs/providers.md#providers", "docs/configuration.md#default-runtime"],
      project=proj("""service: ml-scoring
provider:
  name: aws
  region: us-east-1
  runtime: python3.14
functions:
  score:
    handler: app.scoring.score
    events:
      - http: POST /score
""", "scoring", "score"),
      user="aws rejects python3.14",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `provider.runtime` (pskit default python3.12)", "Validate for aws"],
            result={"decision": "rejected", "note": "no, code uses 3.13 features. newest AWS has."}),
          S("propose_plan", say="OK, pinning the newest one AWS supports in pskit.",
            steps=["Set `provider.runtime: python3.13`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.runtime", value="python3.13"),
      ],
      final="""AWS in pskit runs python3.9-3.13 [docs/providers.md#providers]; `runtime: python3.13` now. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 727  aws ask_user: unknown storage resource, create it?
    C(727, provider="aws", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/configuration.md#resources", "docs/events.md#events-backed-by-a-resource"],
      project=proj("""service: avatar-service
provider:
  name: aws
  region: eu-central-1
functions:
  resize-avatar:
    handler: app.avatars.resize
    events:
      - storage:
          resource: avatars
""", "avatars", "resize"),
      user="I followed a tutorial that used resource: avatars, and validate says unknown resource 'avatars'; known: <none>. What am I missing?",
      steps=[
          S("get_validation"),
          S("ask_user", say="The tutorial also had a `resources:` section that defines `avatars`; your file doesn't have it yet.",
            question="Should pskit create a new S3 bucket for avatars, or do you already have one?",
            options=["create a new bucket", "I already have one"], answer="create a new bucket"),
          S("propose_plan", steps=["Add `resources.avatars: {type: storage}` (pskit creates the bucket)", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources", value={"avatars": {"type": "storage"}}),
      ],
      final="""`resource: avatars` points to an entry under `resources:`, which was missing [docs/events.md#events-backed-by-a-resource].

Added `resources: {avatars: {type: storage}}`; pskit creates the bucket on deploy and `resize-avatar` runs for new files in it [docs/configuration.md#resources]. Validate for aws: valid. You can see and test it on the Resources page."""),

    # ------------------------------------------------------------------ 728  aws Deploy page: package job failed, service too long
    C(728, provider="aws", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/configuration.md#top-level"],
      project=proj("""service: customer-loyalty-points-calculator-api
provider:
  name: aws
  region: us-east-1
functions:
  points:
    handler: app.loyalty.points
    events:
      - http: GET /points/{customer_id}
""", "loyalty", "points"),
      user="Package job in Recent jobs is red: service must be 2-32 chars. my name is lowercase and dashes, so what",
      steps=[
          S("get_validation"),
          S("ask_user", say="Lowercase and dashes are fine; it's the length: `customer-loyalty-points-calculator-api` has 38 characters, the limit is 32.",
            question="Which shorter name do you want?", options=["loyalty-points-api", "loyalty-api"], answer="loyalty-points-api"),
          S("propose_plan", steps=["Set `service: loyalty-points-api`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="service", value="loyalty-points-api"),
      ],
      final="""`service` must be 2-32 characters; yours had 38 [docs/configuration.md#top-level].

Now `service: loyalty-points-api`. Validate for aws: valid. Press **Package** again on the Deploy page."""),

    # ------------------------------------------------------------------ 729  aws switched on Overview from gcp: timeout 3600
    C(729, provider="aws", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#providers", "docs/troubleshooting.md#provider-gotchas"],
      project=proj("""service: report-api
provider:
  name: aws
  region: us-east-1
  options:
    project: report-api-dev
functions:
  report:
    handler: app.reports.build
    timeout: 3600
    events:
      - http: GET /report
""", "reports", "build"),
      user="I switched the provider from GCP to AWS on Overview & provider and now there's an error: timeout 3600s exceeds AWS Lambda max 900s. It was fine on GCP.",
      steps=[
          S("get_validation"),
          S("ask_user", say="GCP allows 3600 s for HTTP functions, Lambda 900 s, and an HTTP call through API Gateway is cut at 30 s anyway.",
            question="How long does a `/report` request really take?", options=["under 30 s", "longer"], answer="under 30 s, usually 5"),
          S("propose_plan", steps=["Set `functions.report.timeout` to 30", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.report.timeout", value=30),
      ],
      final="""Max timeouts differ per provider: GCP 3600 s, AWS Lambda 900 s [docs/providers.md#providers], and API Gateway stops HTTP calls at 30 s [docs/troubleshooting.md#provider-gotchas].

`report` now has `timeout: 30`, enough for ~5 s requests. Validate for aws: valid. The old `options.project` is a GCP setting; if you'll deploy to GCP again, it belongs under `providers.gcp.options`."""),

    # ------------------------------------------------------------------ 730  gcp beginner: what is <root>
    C(730, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/troubleshooting.md#configuration"],
      project=proj("""service: event-tickets
provider:
  name: gcp
  region: europe-west1
  options:
    project: event-tickets-dev
functions:
  buy:
    handler: app.tickets.buy
    events:
      - http: POST /tickets
  refund:
    handler: app.tickets.refund
    events:
      - http: POST /tickets
""", "tickets", "buy", "refund"),
      user="The error starts with \"<root>: Value error\". What is root? I don't have anything called root.",
      steps=[
          S("get_validation"),
          S("propose_plan", say="`<root>` means the problem is between several parts of the file, not in one key. Here: `buy` and `refund` both use `POST /tickets`.",
            steps=["Give `refund` its own route: `POST /tickets/refund`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.refund.events.0", value={"http": "POST /tickets/refund"}),
      ],
      final="""`<root>` = the whole file. pskit checks some rules across functions, like "one function per `METHOD /path`" [docs/troubleshooting.md#configuration], and reports them there.

`refund` now uses `POST /tickets/refund`; `buy` keeps `POST /tickets`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 731  gcp informal: memory 1Gi
    C(731, provider="gcp", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: pdf-convert
provider:
  name: gcp
  region: europe-west1
  options:
    project: pdf-convert-staging
functions:
  convert:
    handler: app.pdf.convert
    memory: 1Gi
    events:
      - queue: pdf-requests
""", "pdf", "convert"),
      user="memory 1Gi like cloud run, but say unable parse string as integer. how write",
      steps=[
          S("get_validation"),
          S("propose_plan", say="In pskit memory is a plain number in MB, so 1Gi = 1024.",
            steps=["Set `functions.convert.memory` to 1024", "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.convert.memory", value=1024),
      ],
      final="""`memory` is a number of MB, without a unit [docs/configuration.md#functions]. Now `memory: 1024`. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 732  gcp wrong fix: lower provider timeout for everything
    C(732, provider="gcp", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen", "docs/configuration.md#functions"],
      project=proj("""service: video-api
provider:
  name: gcp
  region: us-central1
  timeout: 900
  options:
    project: video-api-dev
functions:
  export:
    handler: app.video.export
    events:
      - http: POST /export
  transcode:
    handler: app.video.transcode
    events:
      - queue: transcode-jobs
""", "video", "export", "transcode"),
      user="transcode: event-triggered functions are limited to 540s. I'll just drop provider.timeout to 540 for everything, right?",
      steps=[
          S("get_validation"),
          S("propose_plan", say="That passes, but it also cuts `export` (HTTP), which may run up to 3600 s on GCP. The smaller change is to override only `transcode`.",
            steps=["Keep `provider.timeout: 900`", "Set `functions.transcode.timeout: 540`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.transcode.timeout", value=540),
      ],
      final="""On GCP only event-triggered functions are limited to 540 s [docs/providers.md#gcp-google-cloud-functions-2nd-gen], so only `transcode` needed a change.

`transcode` now has `timeout: 540` (a function value overrides `provider`) [docs/configuration.md#functions]; `export` keeps 900. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 733  gcp rejected plan: jwt -> iam, not none
    C(733, provider="gcp", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#http", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: ledger-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: ledger-api-prod
functions:
  balances:
    handler: app.ledger.balances
    events:
      - http:
          path: /balances
          method: GET
          auth: jwt
          authorizer:
            issuer: https://auth.example.com/
            audience: [ledger]
""", "ledger", "balances"),
      user="Ported from Lambda with a JWT authorizer. GCP says: http auth 'jwt' is not supported on GCP; use none or iam.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `/balances` to `auth: none`, remove the `authorizer`", "Verify the JWT in the handler", "Validate for gcp, stage prod"],
            result={"decision": "rejected", "note": "No, this must never be public. Only our backend service account calls it."}),
          S("propose_plan", say="Then `iam` fits: without a public invoker binding, only identities you grant can call it.",
            steps=["Set `/balances` to `auth: iam`, remove the `authorizer`", "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.balances.events.0.http", value={"path": "/balances", "method": "GET", "auth": "iam"}),
      ],
      final="""GCP has no JWT authorizer in pskit; the choices are `none` or `iam` [docs/events.md#http]. As you asked, it stays private.

`/balances` now has `auth: iam`: no `allUsers` invoker binding [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. `pskit validate -p gcp -s prod`: valid. After deploy, grant your backend's service account the invoker role on the function; it calls with a Google identity token."""),

    # ------------------------------------------------------------------ 734  gcp auto pasted: every monday
    C(734, provider="gcp", stage="dev", mode="auto", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=proj("""service: team-standup
provider:
  name: gcp
  region: europe-west1
  options:
    project: team-standup-dev
functions:
  weekly-summary:
    handler: app.standup.weekly
    events:
      - schedule: every monday
""", "standup", "weekly"),
      user="I want the summary every Monday morning. I wrote \"every monday\" and it complains about 5 fields. Can you make it Monday 8:00 Berlin time?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the schedule to `cron: \"0 8 * * 1\"` (minute 0, hour 8, any day, any month, Monday) with `timezone: Europe/Berlin`",
                                   "Validate for gcp"]),
          S("set_config", path="functions.weekly-summary.events.0", value={"schedule": {"cron": "0 8 * * 1", "timezone": "Europe/Berlin"}}),
      ],
      final="""Words like "every monday" aren't understood; a schedule is a rate (`1 day`) or a 5-field cron [docs/events.md#schedule].

`weekly-summary` now runs at `0 8 * * 1` (Monday 08:00) with `timezone: Europe/Berlin`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 735  azure beginner: authLevel from Azure docs
    C(735, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: contact-api
provider:
  name: azure
  region: westeurope
functions:
  contact:
    handler: app.contact.send
    events:
      - http:
          path: /contact
          method: POST
          authLevel: function
""", "contact", "send"),
      user="The Azure docs say authLevel: function, so I added it. Now: authLevel Extra inputs are not permitted. Is pskit different?",
      steps=[
          S("get_validation"),
          S("propose_plan", say="Yes, pskit uses its own portable name: `auth: key` becomes Azure's function-level auth.",
            steps=["Replace `authLevel: function` with `auth: key` on `POST /contact`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.contact.events.0.http", value={"path": "/contact", "method": "POST", "auth": "key"}),
      ],
      final="""pskit writes Azure's settings for you; you use the portable `auth` key, and `auth: key` is Azure's function key (`AuthLevel.FUNCTION`) [docs/events.md#http] [docs/providers.md#azure-azure-functions].

`/contact` now has `auth: key`. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 736  azure informal: only one function red (python3.13)
    C(736, provider="azure", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/troubleshooting.md#configuration"],
      project=proj("""service: menu-service
provider:
  name: azure
  region: francecentral
functions:
  menu:
    handler: app.menu.today
    events:
      - http: GET /menu
  specials:
    handler: app.menu.specials
    runtime: python3.13
    events:
      - http: GET /specials
""", "menu", "today", "specials"),
      user="only specials function is red in list, menu is ok. both same code style, why only one",
      steps=[
          S("get_validation"),
          S("propose_plan", say="`specials` has its own `runtime: python3.13`, and Azure doesn't offer 3.13. `menu` uses the default (3.12).",
            steps=["Remove `runtime` from `specials` so it uses the same version as `menu`", "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.specials.runtime", value=None),
      ],
      final="""Only `specials` pinned `runtime: python3.13`, which Azure Functions doesn't support [docs/troubleshooting.md#configuration].

Removed it; both functions now run the default python3.12. `pskit validate -p azure -s staging`: valid."""),

    # ------------------------------------------------------------------ 737  azure wrong fix: dots instead of underscores
    C(737, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#queue"],
      project=proj("""service: order-events
provider:
  name: azure
  region: westeurope
functions:
  on-order:
    handler: app.orders.on_order
    events:
      - queue: orders_created
""", "orders", "on_order"),
      user="queue name 'orders_created' must be 3-63 lowercase letters, digits, dashes. I'll change it to orders.created then, underscores must be the problem.",
      steps=[
          S("get_validation"),
          S("propose_plan", say="Underscores are the problem, but a dot isn't allowed either; only lowercase letters, digits and dashes.",
            steps=["Set the queue of `on-order` to `orders-created`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.on-order.events.0", value={"queue": "orders-created"}),
      ],
      final="""Azure queue names allow only lowercase letters, digits and dashes, so `_` and `.` both fail [docs/events.md#queue].

`on-order` now listens on `orders-created`. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 738  azure rejected plan: pin 3.11 instead of default
    C(738, provider="azure", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/troubleshooting.md#configuration", "docs/providers.md#providers"],
      project=proj("""service: scheduler-hub
provider:
  name: azure
  region: uksouth
  runtime: python3.13
functions:
  tick:
    handler: app.hub.tick
    events:
      - schedule: 15 minutes
""", "hub", "tick"),
      user="Azure Functions does not support python3.13. What should it be?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `provider.runtime` so pskit picks python3.12", "Validate for azure"],
            result={"decision": "rejected", "note": "Our local venv and CI run 3.11, pin that so it matches."}),
          S("propose_plan", say="Good point, matching the local version avoids surprises.",
            steps=["Set `provider.runtime: python3.11`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.runtime", value="python3.11"),
      ],
      final="""Azure Functions run python3.9-3.12 [docs/providers.md#providers], so 3.13 was rejected [docs/troubleshooting.md#configuration].

As you asked, `provider.runtime: python3.11`, the same as your venv and CI. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 739  azure auto: http + timer in one item from Problems
    C(739, provider="azure", stage="prod", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/events.md#schedule", "docs/troubleshooting.md#configuration"],
      project=proj("""service: cache-warmer
provider:
  name: azure
  region: westeurope
functions:
  warm:
    handler: app.cache.warm
    events:
      - http: POST /warm
        schedule: 30 minutes
""", "cache", "warm"),
      user="Problems: warm events.0 single-key mapping. http + timer wanted",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["`events: [{http: POST /warm}, {schedule: 30 minutes}]`", "Validate for azure, stage prod"]),
          S("set_config", path="functions.warm.events", value=[{"http": "POST /warm"}, {"schedule": "30 minutes"}]),
      ],
      final="""Split into two items: `- http: POST /warm`, `- schedule: 30 minutes` [docs/troubleshooting.md#configuration]. `pskit validate -p azure -s prod`: valid."""),

    # ------------------------------------------------------------------ 740  azure ask_user: storage container for an existing account
    C(740, provider="azure", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#storage"],
      project=proj("""service: scan-ingest
provider:
  name: azure
  region: westeurope
functions:
  ingest-scan:
    handler: app.scans.ingest
    events:
      - storage:
          bucket: Scans
""", "scans", "ingest"),
      user="""ERROR: [functions.ingest-scan] ... container name ... Scans

the scanners already write into a container, I'm not sure of the exact name""",
      steps=[
          S("get_validation"),
          S("ask_user", say="Azure container names must be lowercase, so `Scans` can't be the real name of an existing container.",
            question="Please check the exact container name in the Azure portal (Storage account > Containers). What is it?",
            answer="scans-inbox"),
          S("propose_plan", steps=["Set the trigger to `storage: {bucket: scans-inbox, existing: true}`", "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest-scan.events.0", value={"storage": {"bucket": "scans-inbox", "existing": True}}),
      ],
      final="""Container names are 3-63 lowercase characters, so `Scans` was rejected [docs/events.md#storage].

The trigger now uses the scanners' container: `bucket: scans-inbox, existing: true` (pskit won't create or delete it). `pskit validate -p azure -s staging`: valid. If that container is in a different storage account than the Function App's, it also needs `options.storage_connection`."""),
]
