"""Category B (build / add), batch 29 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 561
    B(561, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: users-api
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "app/__init__.py": "",
          "app/users.py": FUTURE + """

def user(event, ctx):
    uid = event.http.path_params["id"]
    if event.http.method == "DELETE":
        return None
    return {"id": uid}
""",
          "requirements.txt": ""}),
      user="""In SAM one function handled two routes:

  UserFunction:
    Properties:
      Handler: app/users.user
      Events:
        GetUser:    {Type: Api, Properties: {Path: /users/{id}, Method: get}}
        DeleteUser: {Type: Api, Properties: {Path: /users/{id}, Method: delete}}

Same in pskit please.""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add function `user` (handler app.users.user) with two http events: GET /users/{id} and DELETE /users/{id}",
                                   "Validate for aws, invoke GET and DELETE"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.user",
            value={"handler": "app.users.user",
                   "events": [{"http": "GET /users/{id}"}, {"http": "DELETE /users/{id}"}]}),
          S("invoke_local", function="user", method="GET", path="/users/42"),
          S("invoke_local", function="user", method="DELETE", path="/users/42"),
      ],
      final="""Each SAM event becomes one item in `events` [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition]:

```yaml
functions:
  user:
    handler: app.users.user
    events:
      - http: GET /users/{id}
      - http: DELETE /users/{id}
```

- `Type: Api` (REST API) becomes a route on pskit's API Gateway **HTTP API**; the handler reads `event.http.method` as before.
- validate (aws): valid.
- invoke: GET → 200 `{"id": "42"}`; DELETE → **204** (the handler returns `None`).

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 562
    B(562, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: newsletter
provider:
  name: gcp
  region: europe-west3
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, newsletter-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="create a new project for my newsletter: people can subscribe with their email, and every monday at 9 in the morning (Berlin) the newsletter goes out",
      steps=[
          S("get_project"),
          S("search_docs", query="schedule timezone", docs=[D("docs/events.md", "schedule", end="enabled: true")]),
          S("propose_plan", steps=["Write app/news.py: subscribe (POST /subscribe, needs an email with @) and send_weekly",
                                   "Add function subscribe on POST /subscribe",
                                   "Add function send-weekly: schedule {cron: \"0 9 * * 1\", timezone: Europe/Berlin}",
                                   "Validate for gcp, run both locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/news.py", content=FUTURE + """from py_serverless_kit import BadRequest


def subscribe(event, ctx):
    email = ((event.http.json(default={}) or {}).get("email") or "").strip()
    if "@" not in email:
        raise BadRequest("a valid email is required")
    # TODO: save the email (for example in Firestore)
    return {"subscribed": email}, 201


def send_weekly(event, ctx):
    # TODO: load the subscribers and send this week's issue
    ctx.logger.info("sending newsletter")
    return {"sent": 0}
"""),
          S("set_config", path="functions.subscribe",
            value={"handler": "app.news.subscribe", "events": [{"http": "POST /subscribe"}]}),
          S("set_config", path="functions.send-weekly",
            value={"handler": "app.news.send_weekly",
                   "events": [{"schedule": {"cron": "0 9 * * 1", "timezone": "Europe/Berlin"}}]}),
          S("invoke_local", function="subscribe", method="POST", path="/subscribe", data={"email": "lena@example.com"}),
          S("invoke_local", function="send-weekly", type="schedule"),
      ],
      final="""Your newsletter project has two functions:

- `subscribe`: `POST /subscribe` with `{"email": ...}` → **201**; an email without `@` gets a 400.
- `send-weekly`: every Monday at 09:00 **Berlin time**. Google Cloud Scheduler honours `timezone`, so summer time is handled [docs/events.md#schedule].

Checks: `pskit validate` (gcp) valid; subscribe → 201 `{"subscribed": "lena@example.com"}`; send-weekly → `{"sent": 0}`.

Two TODOs remain in app/news.py: saving the emails and sending the issue. Test on **Test** > **▶ Run locally**, deploy with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 563
    B(563, provider="azure", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: shop-front
provider:
  name: azure
  region: westeurope
functions:
  orders:
    handler: app.orders.list_orders
    events:
    - http: GET /orders
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def list_orders(event, ctx):
    return {"orders": []}
""",
          "requirements.txt": ""}),
      user="""our frontend was built for the old Azure functions:

  GET https://shop-front-staging.azurewebsites.net/api/orders -> 404

the frontend can't change this week, it must keep calling /api/orders""",
      steps=[
          S("get_project"),
          S("search_docs", query="azure route prefix api",
            docs=[D("docs/providers.md", "azure-azure-functions", start="One **Linux Consumption Function App**", end="`{path+}` becomes Azure's `{*path}`.")]),
          S("propose_plan", steps=["Change the route of `orders` to GET /api/orders (pskit's Azure app has an empty routePrefix, so the path is used as written)",
                                   "Validate for azure (staging), invoke GET /api/orders"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.orders.events.0", value={"http": "GET /api/orders"}),
          S("invoke_local", function="orders", method="GET", path="/api/orders"),
      ],
      final="""Cause: classic Azure Functions put `/api` in front of every route, but pskit's Function App uses an empty `routePrefix`, so your paths are served exactly as written [docs/providers.md#azure-azure-functions]. `orders` lived at `/orders`.

Change: the route is now `GET /api/orders`.

- `pskit validate` (azure, staging): valid.
- invoke `GET /api/orders`: 200 `{"orders": []}`.

Other routes the frontend calls need the `/api` prefix too. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 564
    B(564, provider="aws", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": """service: orders-js
provider:
  name: aws
  region: us-east-1
  runtime: nodejs22
functions: {}
""",
          "package.json": "{\n  \"name\": \"orders-js\",\n  \"private\": true\n}\n"}),
      user="nodejs22 svc. GET /orders/{id} in JS, 2 hardcoded orders, else NotFound",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write src/orders.js: export getOrder, throw NotFound for unknown ids",
                                   "functions.get-order: handler src.orders.getOrder, http GET /orders/{id}",
                                   "Validate aws, invoke a known and an unknown id"]),
          S("write_file", path="src/orders.js", content="""const { NotFound } = require("pskit");

const ORDERS = {
  "1": { id: "1", total: 19.5 },
  "2": { id: "2", total: 7.25 },
};

exports.getOrder = async function (event) {
  const order = ORDERS[event.http.pathParams.id];
  if (!order) throw new NotFound("no such order");
  return order;
};
"""),
          S("set_config", path="functions.get-order",
            value={"handler": "src.orders.getOrder", "events": [{"http": "GET /orders/{id}"}]}),
          S("invoke_local", function="get-order", method="GET", path="/orders/2"),
          S("invoke_local", function="get-order", method="GET", path="/orders/9"),
      ],
      final="""```yaml
functions:
  get-order:
    handler: src.orders.getOrder
    events:
      - http: GET /orders/{id}
```

`src/orders.js` reads `event.http.pathParams.id` and throws `NotFound` from `pskit` (camelCase mirror of the Python API) [docs/nodejs.md#handlers].

- validate (aws): valid.
- invoke `/orders/2` → 200 `{"id": "2", "total": 7.25}`; `/orders/9` → 404 `no such order`.

Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 565
    B(565, provider="gcp", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#package"],
      project=dict(files={
          "pskit.yml": """service: ml-scoring
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, ml-scoring-dev}
functions:
  score:
    handler: app.score.score
    events:
    - http: POST /score
""",
          "app/__init__.py": "",
          "app/score.py": FUTURE + """

def score(event, ctx):
    return {"score": 0.5}
""",
          "data/raw/README.txt": "training data, about 2 GB, not needed at runtime\n",
          "notebooks/explore.ipynb": "{}\n",
          "requirements.txt": ""}),
      user="deploy upload so slow, i think it take my data/ folder and notebooks/ also. function need only app/. how stop that",
      steps=[
          S("get_project"),
          S("search_docs", query="package exclude files bundle",
            docs=[D("docs/configuration.md", "package", end="Always excluded:")]),
          S("propose_plan", steps=["package.exclude = [\"data/**\", \"notebooks/**\"] (added to pskit's default excludes)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="package", value={"exclude": ["data/**", "notebooks/**"]}),
      ],
      final="""Yes, by default pskit bundles everything under `package.source` (`.`) except its built-in excludes, so `data/` and `notebooks/` went into the upload [docs/configuration.md#package]. Now:

```yaml
package:
  exclude: ["data/**", "notebooks/**"]
```

`exclude` is added to the defaults (`.venv`, `tests/`, `.git`, ...), and the globs are gitignore-style (`**` = any depth).

- `pskit validate` (gcp): valid.

Build the bundle once to check it before deploying: **Deploy** > `Package` or `pskit package --skip-deps`. Then **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 566
    B(566, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: choir-signup
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="I want a simple web page with a form (name and voice type) for my choir. When people press send, my function should get what they typed and say thank you.",
      steps=[
          S("get_project"),
          S("search_docs", query="read form fields request",
            docs=[D("docs/handlers.md", "httprequest")]),
          S("propose_plan", steps=["Write app/choir.py: page() returns the HTML form, join() reads the form fields with event.http.form()",
                                   "Add function page on GET /join and function join on POST /join",
                                   "Validate for azure, open the page and send a form locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/choir.py", content=FUTURE + """import html

from py_serverless_kit import Response

FORM = \"\"\"<!doctype html>
<html><body>
<h1>Join the choir</h1>
<form method="post" action="/join">
  <label>Name <input name="name" required></label>
  <label>Voice
    <select name="voice"><option>soprano</option><option>alto</option><option>tenor</option><option>bass</option></select>
  </label>
  <button type="submit">Send</button>
</form>
</body></html>\"\"\"


def page(event, ctx):
    return Response.html(FORM)


def join(event, ctx):
    fields = event.http.form()
    name = html.escape(fields.get("name", "friend"))
    voice = html.escape(fields.get("voice", "?"))
    return Response.html(f"<p>Thank you, {name}! See you at {voice} practice.</p>")
"""),
          S("set_config", path="functions.page", value={"handler": "app.choir.page", "events": [{"http": "GET /join"}]}),
          S("set_config", path="functions.join", value={"handler": "app.choir.join", "events": [{"http": "POST /join"}]}),
          S("invoke_local", function="join", method="POST", path="/join", data="name=Mia&voice=alto"),
      ],
      final="""Done. Two functions share the address `/join`:

- `page` (`GET /join`) shows the HTML form.
- `join` (`POST /join`) reads what people typed with `event.http.form()` and answers with a thank-you page [docs/handlers.md#httprequest]. Names are HTML-escaped, so nobody can inject code.

Checks: `pskit validate` (azure) valid; sending `name=Mia&voice=alto` locally → 200 HTML "Thank you, Mia! See you at alto practice."

To try it in a browser, run `pskit dev` and open `http://127.0.0.1:3000/join`. Put it online with **Deploy** or `pskit deploy -s dev`. Next step: save the answers somewhere (for example a storage table)."""),

    # ------------------------------------------------------------------ 567
    B(567, provider="aws", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: claims
provider:
  name: aws
  region: eu-central-1
functions:
  submit:
    handler: app.claims.submit
    events:
    - http: POST /claims
""",
          "app/__init__.py": "",
          "app/claims.py": FUTURE + """

def submit(event, ctx):
    return {"claim": "received"}, 202
""",
          "requirements.txt": ""}),
      user="Security policy: deployments may not create S3 buckets. All code artifacts must go to the existing bucket `acme-deploy-artifacts-euc1`. Configure pskit for that.",
      steps=[
          S("get_project"),
          S("search_docs", query="artifact bucket code upload aws",
            docs=[D("docs/providers.md", "aws-aws-lambda", start="**Code upload:**", end="**Code upload:**")]),
          S("propose_plan", steps=["provider.options.artifact_bucket = acme-deploy-artifacts-euc1",
                                   "Validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options", value={"artifact_bucket": "acme-deploy-artifacts-euc1"}),
      ],
      final="""```yaml
provider:
  options:
    artifact_bucket: acme-deploy-artifacts-euc1
```

- With `artifact_bucket`, pskit uploads the code artifact to that bucket instead of creating its own `<service>-<stage>-code-*` bucket. The deploying identity then only needs `s3:PutObject` on it [docs/providers.md#aws-aws-lambda].
- `pskit validate` (aws, prod): valid.

The bucket must exist in a region Lambda can read from (eu-central-1 here). This service has no storage triggers, so the deploy creates no S3 buckets at all. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 568
    B(568, provider="gcp", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#variables", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: standup-bot
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, standup-bot-staging}
functions: {}
""",
          "requirements.txt": ""}),
      user="Add a Slack slash command endpoint POST /slack/standup. Verify Slack's signature: X-Slack-Signature is `v0=` + HMAC-SHA256 of `v0:<X-Slack-Request-Timestamp>:<raw body>` with the signing key from env SLACK_SIGNING_KEY. Reject old timestamps (> 5 min). The body is form-encoded; reply with `Noted, <user_name>!`.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/slack.py: check timestamp age and the v0 signature with hmac.compare_digest (401 otherwise), read user_name with event.http.form()",
                                   "Add function `standup` on POST /slack/standup with SLACK_SIGNING_KEY: ${env:SLACK_SIGNING_KEY, not-set}",
                                   "Validate for gcp (staging), invoke without signature (expect 401)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/slack.py", content=FUTURE + """import hashlib
import hmac
import time

from py_serverless_kit import Unauthorized


def standup(event, ctx):
    key = ctx.env.get("SLACK_SIGNING_KEY", "").encode()
    stamp = event.http.headers.get("x-slack-request-timestamp", "0")
    if not stamp.isdigit() or abs(time.time() - int(stamp)) > 300:
        raise Unauthorized("stale or missing timestamp")
    base = b"v0:" + stamp.encode() + b":" + event.http.body
    expected = "v0=" + hmac.new(key, base, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, event.http.headers.get("x-slack-signature", "")):
        raise Unauthorized("bad signature")
    user = event.http.form().get("user_name", "there")
    return {"response_type": "in_channel", "text": f"Noted, {user}!"}
"""),
          S("set_config", path="functions.standup",
            value={"handler": "app.slack.standup",
                   "environment": {"SLACK_SIGNING_KEY": "${env:SLACK_SIGNING_KEY, not-set}"},
                   "events": [{"http": "POST /slack/standup"}]}),
          S("invoke_local", function="standup", method="POST", path="/slack/standup", data="user_name=sam&text=done"),
      ],
      final="""Added `standup` on `POST /slack/standup`:

- Rejects requests whose `X-Slack-Request-Timestamp` is missing or more than 5 minutes off, then compares `v0=` + HMAC-SHA256 of `v0:<timestamp>:<raw body>` with `X-Slack-Signature` (`hmac.compare_digest`). Failures → **401**.
- Reads `user_name` from the form body with `event.http.form()` [docs/handlers.md#httprequest] and replies `Noted, <user_name>!` in the channel.
- The signing key comes from `SLACK_SIGNING_KEY: ${env:SLACK_SIGNING_KEY, not-set}`; pskit.yml holds no key [docs/configuration.md#variables].

Checks: `pskit validate` (gcp, staging) valid; an unsigned local call → **401** `stale or missing timestamp`, as expected.

Before deploying, set the real `SLACK_SIGNING_KEY` (CI secret, or **Setup & credentials** > Environment variables > **Set for this session**). Deploy: **Deploy** or `pskit deploy -s staging`, then paste the URL from `pskit info` into the Slack app's slash command."""),

    # ------------------------------------------------------------------ 569
    B(569, provider="azure", stage="dev", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: print-shop
provider:
  name: azure
  region: westeurope
  runtime: nodejs20
functions:
  order:
    handler: src.api.order
    events:
    - http: POST /print
""",
          "src/api.js": """exports.order = async function (event) {
  return { queued: true };
};
""",
          "package.json": "{\n  \"name\": \"print-shop\",\n  \"private\": true\n}\n"}),
      user="node project. need worker for storage queue print-jobs, each msg have file and copies, log it and give back how much pages total",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write src/worker.js: export printJobs, sum copies over event.records",
                                   "functions.print-worker: handler src.worker.printJobs, queue print-jobs",
                                   "Validate azure, invoke with two messages"]),
          S("write_file", path="src/worker.js", content="""exports.printJobs = async function (event, ctx) {
  let total = 0;
  for (const record of event.records) {
    const job = record.json();
    ctx.logger.info("print job", { file: job.file, copies: job.copies });
    total += job.copies || 1;
  }
  return { pages: total };
};
"""),
          S("set_config", path="functions.print-worker",
            value={"handler": "src.worker.printJobs", "events": [{"queue": "print-jobs"}]}),
          S("invoke_local", function="print-worker", type="queue",
            data=[{"file": "flyer.pdf", "copies": 50}, {"file": "card.pdf", "copies": 20}]),
      ],
      final="""Done. `src/worker.js` exports `printJobs`, and:

```yaml
functions:
  print-worker:
    handler: src.worker.printJobs
    events:
      - queue: print-jobs
```

- On Azure this is a Storage Queue in the app's storage account; failed messages end in `print-jobs-poison` [docs/events.md#queue].
- validate (azure): valid.
- invoke with 50 + 20 copies: two `print job` logs, result `{"pages": 70}`.

Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 570
    B(570, provider="aws", stage="prod", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/providers.md#aws-aws-lambda", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: ledger
provider:
  name: aws
  region: eu-west-1
functions:
  post:
    handler: app.ledger.post
    events:
    - http: POST /entries
""",
          "app/__init__.py": "",
          "app/ledger.py": FUTURE + """

def post(event, ctx):
    return {"ok": True}, 201
""",
          "requirements.txt": ""}),
      user="profile ledger-dev by default; prod: profile ledger-prod + allowed_account_ids 210987654321 so it can't hit the wrong account",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.profile = ledger-dev",
                                   "stages.prod.provider.options = {profile: ledger-prod, allowed_account_ids: [\"210987654321\"]}",
                                   "Validate aws prod"]),
          S("set_config", path="provider.options", value={"profile": "ledger-dev"}),
          S("set_config", path="stages",
            value={"prod": {"provider": {"options": {"profile": "ledger-prod", "allowed_account_ids": ["210987654321"]}}}}),
      ],
      final="""```yaml
provider:
  options:
    profile: ledger-dev
stages:
  prod:
    provider:
      options:
        profile: ledger-prod
        allowed_account_ids: ["210987654321"]
```

- `profile` and `allowed_account_ids` are AWS provider options [docs/providers.md#aws-aws-lambda]; with the account list set, the AWS provider refuses to run against any other account.
- The prod block is deep-merged only for `-s prod` [docs/configuration.md#stages-per-stage-overrides].
- validate (aws, prod): valid after both changes.

Deploy: `pskit deploy -s prod` (typed confirmation in studio)."""),

    # ------------------------------------------------------------------ 571
    B(571, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/studio.md#what-you-can-do"],
      project=dict(files={
          "pskit.yml": """service: reports
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, reports-dev}
functions:
  func1:
    handler: app.report.daily
    timeout: 120
    environment:
      FORMAT: pdf
    events:
    - schedule: "0 6 * * *"
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """

def daily(event, ctx):
    return {"format": ctx.env.get("FORMAT"), "function": ctx.function}
""",
          "requirements.txt": ""}),
      user="func1 is bad name. rename it daily-report but keep everything same",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add functions.daily-report with the same handler, timeout, environment and schedule as func1",
                                   "Delete functions.func1",
                                   "Validate for gcp, run daily-report locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.daily-report",
            value={"handler": "app.report.daily", "timeout": 120, "environment": {"FORMAT": "pdf"},
                   "events": [{"schedule": "0 6 * * *"}]}),
          S("set_config", path="functions.func1", value=None),
          S("invoke_local", function="daily-report", type="schedule"),
      ],
      final="""Renamed. `daily-report` has exactly func1's settings (handler, 120 s timeout, `FORMAT: pdf`, schedule 06:00 UTC) and `func1` is gone.

- `pskit validate` (gcp): valid.
- Local run: `{"format": "pdf", "function": "daily-report"}`.

Good to know: the cloud resources are named after the function, so the next deploy creates `daily-report` and deletes the old `func1` function and its scheduler job. Next time you can use the row button **Rename** on the **Functions** page. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 572
    B(572, provider="azure", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/events.md#schedule", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: greenhouse
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="New project for greenhouse sensors: POST /readings takes {sensor, celsius} (celsius must be a number between -40 and 80, otherwise 422), and an hourly job `hourly-summary` that will later compute averages. Two functions, one module app/greenhouse.py.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/greenhouse.py with reading (validates, 422 via HttpError with details) and hourly_summary",
                                   "Add function readings on POST /readings and hourly-summary on schedule 1 hour",
                                   "Validate for azure, invoke a good and a bad reading"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/greenhouse.py", content=FUTURE + """from py_serverless_kit import HttpError


def reading(event, ctx):
    body = event.http.json(default={}) or {}
    value = body.get("celsius")
    if not isinstance(value, (int, float)) or not -40 <= value <= 80:
        raise HttpError("celsius must be a number from -40 to 80", status=422, details={"field": "celsius"})
    # TODO: store the reading
    return {"sensor": body.get("sensor"), "celsius": value}, 201


def hourly_summary(event, ctx):
    # TODO: compute the averages of the last hour
    return {"sensors": 0}
"""),
          S("set_config", path="functions.readings",
            value={"handler": "app.greenhouse.reading", "events": [{"http": "POST /readings"}]}),
          S("set_config", path="functions.hourly-summary",
            value={"handler": "app.greenhouse.hourly_summary", "events": [{"schedule": "1 hour"}]}),
          S("invoke_local", function="readings", method="POST", path="/readings", data={"sensor": "gh-1", "celsius": 21.5}),
          S("invoke_local", function="readings", method="POST", path="/readings", data={"sensor": "gh-1", "celsius": 300}),
      ],
      final="""Created:

| Function | Trigger | Handler |
|---|---|---|
| `readings` | `POST /readings` | `app.greenhouse.reading` |
| `hourly-summary` | every hour (`1 hour`) | `app.greenhouse.hourly_summary` |

- A bad `celsius` raises `HttpError(..., status=422, details={"field": "celsius"})`, which pskit turns into a JSON 422 [docs/handlers.md#errors].
- `pskit validate` (azure): valid.
- invoke: 21.5 → **201**; 300 → **422** with `details.field = celsius`.

Storing readings and the averages are TODOs. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 573
    B(573, provider="aws", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#package"],
      project=dict(files={
          "pskit.yml": """service: risk
provider:
  name: aws
  region: eu-west-1
functions:
  assess:
    handler: app.risk.assess
    events:
    - http: POST /assess
""",
          "app/__init__.py": "",
          "app/risk.py": FUTURE + """

def assess(event, ctx):
    return {"risk": "low"}
""",
          "requirements.txt": "acme-risk-models==4.2.0\n"}),
      user="acme-risk-models is on our private index https://pypi.example.com/simple. make vendoring use it as extra index",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["package.pip_args = [\"--extra-index-url\", \"https://pypi.example.com/simple\"]", "Validate aws"]),
          S("set_config", path="package", value={"pip_args": ["--extra-index-url", "https://pypi.example.com/simple"]}),
      ],
      final="""```yaml
package:
  pip_args: ["--extra-index-url", "https://pypi.example.com/simple"]
```

`pip_args` are extra `pip install` flags used when pskit vendors requirements.txt into the Lambda zip [docs/configuration.md#package]. validate (aws): valid.

If the index needs a login, don't put it in the URL here; use pip's own config (`PIP_EXTRA_INDEX_URL` / a netrc file) on the build machine. Check with `pskit package` before `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 574
    B(574, provider="gcp", stage="staging", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#variables", "docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: exports
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, exports-staging}
functions:
  on-export:
    handler: app.exports.on_export
""",
          "app/__init__.py": "",
          "app/exports.py": FUTURE + """

def on_export(event, ctx):
    return {"bucket": ctx.env.get("EXPORT_BUCKET"), "files": [r.key for r in event.records]}
""",
          "requirements.txt": ""}),
      user="Give `on-export` a storage trigger on a bucket named `<service>-<stage>-files-acme` (so exports-staging-files-acme here), created by pskit, and pass the same name as EXPORT_BUCKET. Define the name once in custom and derive it from service and stage.",
      steps=[
          S("get_project"),
          S("search_docs", query="self opt variables",
            docs=[D("docs/configuration.md", "variables", end="When a value is exactly one variable")]),
          S("propose_plan", steps=["custom.export_bucket = ${self:service}-${opt:stage}-files-acme",
                                   "on-export: environment EXPORT_BUCKET: ${self:custom.export_bucket}; storage {bucket: ${self:custom.export_bucket}}",
                                   "Validate for gcp (staging), invoke a storage event"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="custom", value={"export_bucket": "${self:service}-${opt:stage}-files-acme"}),
          S("set_config", path="functions.on-export.environment", value={"EXPORT_BUCKET": "${self:custom.export_bucket}"}),
          S("set_config", path="functions.on-export.events", value=[{"storage": {"bucket": "${self:custom.export_bucket}"}}]),
          S("invoke_local", function="on-export", type="storage", data={"bucket": "exports-staging-files-acme", "key": "2026/11/orders.csv"}),
      ],
      final="""```yaml
custom:
  export_bucket: ${self:service}-${opt:stage}-files-acme
functions:
  on-export:
    environment:
      EXPORT_BUCKET: ${self:custom.export_bucket}
    events:
      - storage: {bucket: "${self:custom.export_bucket}"}
```

- `${self:service}` and `${opt:stage}` resolve to the service and the effective stage, and `${self:custom...}` reuses the value [docs/configuration.md#variables].
- `pskit validate` (gcp, staging): valid.
- invoke: `EXPORT_BUCKET` = `exports-staging-files-acme`, files `["2026/11/orders.csv"]`.

GCS bucket names are global; if `-files-acme` is taken in another project, change the suffix in one place. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 575
    B(575, provider="azure", stage="staging", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: cafe-menu
provider:
  name: azure
  region: westeurope
functions:
  menu:
    handler: app.menu.menu
    events:
    - http: GET /menu
""",
          "app/__init__.py": "",
          "app/menu.py": FUTURE + """

def menu(event, ctx):
    return {"dishes": ["soup", "salad"]}
""",
          "requirements.txt": ""}),
      user="the menu changes only once a day. can browsers keep it for 10 minutes so my function is not called every time?",
      steps=[
          S("get_project"),
          S("search_docs", query="response headers status tuple",
            docs=[D("docs/handlers.md", "returning-a-response", end="Response.binary")]),
          S("propose_plan", steps=["Return (body, 200, {\"cache-control\": \"public, max-age=600\"}) from menu",
                                   "Validate for azure (staging), call GET /menu locally to see the header"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/menu.py", content=FUTURE + """

def menu(event, ctx):
    body = {"dishes": ["soup", "salad"]}
    return body, 200, {"cache-control": "public, max-age=600"}
"""),
          S("validate"),
          S("invoke_local", function="menu", method="GET", path="/menu"),
      ],
      final="""Yes. The menu now comes with the header `cache-control: public, max-age=600`, so browsers keep it for 10 minutes before asking again. In pskit you add headers by returning `(body, status, headers)` [docs/handlers.md#returning-a-response].

- `pskit validate` (azure, staging): valid.
- Local test: 200, the dishes, and the `cache-control` header.

When you change the menu, people may see the old one for up to 10 minutes. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 576
    B(576, provider="aws", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      project=dict(files={
          "pskit.yml": """service: media
provider:
  name: aws
  region: eu-west-1
functions:
  upload-done:
    handler: app.media.upload_done
    events:
    - http: POST /uploads/done
  transcode:
    handler: app.media.transcode
""",
          "app/__init__.py": "",
          "app/media.py": FUTURE + """

def upload_done(event, ctx):
    return {"ok": True}


def transcode(event, ctx):
    ctx.logger.info("transcoding", extra={"video": (event.data or {}).get("video")})
    return {"done": True}
""",
          "requirements.txt": ""}),
      user="when upload-done called, start transcode in background and answer 202 right away, dont wait. transcode takes minutes",
      steps=[
          S("get_project"),
          S("search_docs", query="invoke asynchronous fire and forget",
            docs=[D("docs/handlers.md", "invoke-calling-another-function", end="Grant `lambda:InvokeFunction`")]),
          S("propose_plan", steps=["upload_done: invoke(\"transcode\", {video}, asynchronous=True), return 202",
                                   "Add boto3 to requirements.txt; iam statement lambda:InvokeFunction on the transcode function",
                                   "Validate for aws (staging), invoke upload-done locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/media.py", content=FUTURE + """from py_serverless_kit import invoke


def upload_done(event, ctx):
    video = (event.http.json(default={}) or {}).get("video")
    invoke("transcode", {"video": video}, asynchronous=True)
    return {"video": video, "status": "transcoding"}, 202


def transcode(event, ctx):
    ctx.logger.info("transcoding", extra={"video": (event.data or {}).get("video")})
    return {"done": True}
"""),
          S("write_file", path="requirements.txt", content="boto3\n"),
          S("set_config", path="functions.upload-done.iam",
            value={"statements": [{"actions": ["lambda:InvokeFunction"],
                                   "resources": ["arn:aws:lambda:*:*:function:media-staging-transcode"]}]}),
          S("invoke_local", function="upload-done", method="POST", path="/uploads/done", data={"video": "talk.mov"}),
      ],
      final="""Done. `upload-done` now starts `transcode` with `invoke("transcode", {...}, asynchronous=True)` and answers **202** at once; on AWS that is a fire-and-forget Lambda invoke [docs/handlers.md#invoke-calling-another-function].

- `boto3` added to requirements.txt (needed for `invoke()` on AWS).
- `upload-done` got `lambda:InvokeFunction` on `media-staging-transcode`.
- `pskit validate` (aws, staging): valid.
- Local test: 202 `{"status": "transcoding"}` and a `transcoding` log. Locally the call runs in-process and finishes before returning; in Lambda it doesn't wait.

Check the function ARN with `pskit info` after the first deploy. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 577
    B(577, provider="gcp", stage="dev", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers", "docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: alerts-js
provider:
  name: gcp
  region: us-central1
  runtime: nodejs20
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, alerts-js-dev}
functions:
  health:
    handler: src.http.health
    events:
    - http: GET /health
""",
          "src/http.js": """exports.health = async function () {
  return { ok: true };
};
""",
          "package.json": "{\n  \"name\": \"alerts-js\",\n  \"private\": true\n}\n"}),
      user="js project on gcp. subscribe new fn on pubsub topic `alerts`, log level+text of each message, count the critical",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write src/alerts.js: export onAlert, loop event.records, log level/text, count level === critical",
                                   "functions.on-alert: handler src.alerts.onAlert, topic alerts",
                                   "Validate gcp, invoke a topic event"]),
          S("write_file", path="src/alerts.js", content="""exports.onAlert = async function (event, ctx) {
  let critical = 0;
  for (const record of event.records) {
    const alert = record.json();
    ctx.logger.info("alert", { level: alert.level, text: alert.text });
    if (alert.level === "critical") critical += 1;
  }
  return { critical };
};
"""),
          S("set_config", path="functions.on-alert", value={"handler": "src.alerts.onAlert", "events": [{"topic": "alerts"}]}),
          S("invoke_local", function="on-alert", type="topic", data={"level": "critical", "text": "disk full"}),
      ],
      final="""Done:

```yaml
functions:
  on-alert:
    handler: src.alerts.onAlert
    events:
      - topic: alerts
```

- pskit creates the Pub/Sub topic `alerts` and the trigger [docs/events.md#topic]; `src/alerts.js` reads `event.records` like Python [docs/nodejs.md#handlers].
- validate (gcp): valid.
- invoke with a critical alert: one `alert` log, `{"critical": 1}`.

Re-test: `pskit invoke -f on-alert -t topic -d '{"level": "info", "text": "ok"}'`. Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 578
    B(578, provider="azure", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: id-maker
provider:
  name: azure
  region: northeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="new project please: a web address that gives me new random IDs. like ?count=5 gives 5 of them. not more than 100 at once",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/ids.py: read ?count (default 1), 400 if it isn't a number from 1 to 100, return a list of uuid4 strings",
                                   "Add function `ids` on GET /ids",
                                   "Validate for azure, try count=3 and count=500 locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/ids.py", content=FUTURE + """import uuid

from py_serverless_kit import BadRequest


def ids(event, ctx):
    raw = event.http.query.get("count", "1")
    if not raw.isdigit() or not 1 <= int(raw) <= 100:
        raise BadRequest("count must be a number from 1 to 100")
    return {"ids": [str(uuid.uuid4()) for _ in range(int(raw))]}
"""),
          S("set_config", path="functions.ids", value={"handler": "app.ids.ids", "events": [{"http": "GET /ids"}]}),
          S("invoke_local", function="ids", method="GET", path="/ids?count=3"),
          S("invoke_local", function="ids", method="GET", path="/ids?count=500"),
      ],
      final="""Your new project has one function, `ids`, at `GET /ids`:

- `?count=3` gives 3 random IDs (UUIDs); no `count` gives 1.
- A count that isn't 1 to 100 gets a **400** with `count must be a number from 1 to 100`.

Checks: `pskit validate` (azure) valid; `count=3` → 200 with three IDs; `count=500` → 400.

Try more on **Test** > **▶ Run locally** (put `/ids?count=5` in the path). Put it online with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 579
    B(579, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/nodejs.md#handlers", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: plant-reminder
provider:
  name: aws
  region: eu-west-2
  runtime: nodejs20
functions: {}
""",
          "package.json": "{\n  \"name\": \"plant-reminder\",\n  \"private\": true\n}\n"}),
      user="I write JavaScript, not Python. Can I have something that reminds me to water my plants every Sunday at 10 London time? For now it can just write a message in the log.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write src/reminder.js: export water, log the message from the schedule input",
                                   "Add function `water-plants`: schedule {cron: \"0 10 * * 0\", timezone: Europe/London, input: {plants: [fern, basil]}}",
                                   "Validate for aws, run it once locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/reminder.js", content="""exports.water = async function (event, ctx) {
  const plants = (event.data && event.data.plants) || [];
  ctx.logger.info("time to water the plants", { plants });
  return { reminded: plants.length };
};
"""),
          S("set_config", path="functions.water-plants",
            value={"handler": "src.reminder.water",
                   "events": [{"schedule": {"cron": "0 10 * * 0", "timezone": "Europe/London",
                                            "input": {"plants": ["fern", "basil"]}}}]}),
          S("invoke_local", function="water-plants", type="schedule"),
      ],
      final="""Yes, JavaScript works the same way. `water-plants` runs every Sunday at 10:00 London time and writes "time to water the plants" in the log.

- The handler is the `water` export of `src/reminder.js` [docs/nodejs.md#handlers]; the schedule's `input` arrives as `event.data`, and AWS honours `timezone` [docs/events.md#schedule].
- `pskit validate` (aws): valid.
- Local run: one log line with `["fern", "basil"]`, result `{"reminded": 2}`.

Deploy with **Deploy** or `pskit deploy -s dev`; the messages show up on the **Logs** page. Later you could send yourself an email or SMS instead of logging."""),

    # ------------------------------------------------------------------ 580
    B(580, provider="gcp", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: tickets
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, tickets-staging}
functions:
  tickets:
    handler: app.tickets.tickets
    events:
    - http: GET /tickets
""",
          "app/__init__.py": "",
          "app/tickets.py": FUTURE + """

def tickets(event, ctx):
    return {"tickets": []}
""",
          "requirements.txt": ""}),
      user="""POST https://tickets-staging.example.com/tickets -> 405 {"error": "Method Not Allowed", "status": 405}

the same function should create a ticket on POST (title required) and list on GET""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add a second http event POST /tickets to `tickets`",
                                   "Handler: on POST require title (400) and answer 201; GET still lists",
                                   "Validate for gcp (staging), invoke POST and GET"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tickets.py", content=FUTURE + """from py_serverless_kit import BadRequest


def tickets(event, ctx):
    if event.http.method == "POST":
        title = (event.http.json(default={}) or {}).get("title")
        if not title:
            raise BadRequest("title is required")
        return {"title": title, "status": "open"}, 201
    return {"tickets": []}
"""),
          S("set_config", path="functions.tickets.events",
            value=[{"http": "GET /tickets"}, {"http": "POST /tickets"}]),
          S("invoke_local", function="tickets", method="POST", path="/tickets", data={"title": "Printer jam"}),
          S("invoke_local", function="tickets", method="GET", path="/tickets"),
      ],
      final="""The 405 came from pskit's router: `/tickets` only allowed GET. Now:

```yaml
functions:
  tickets:
    events:
      - http: GET /tickets
      - http: POST /tickets
```

The handler branches on `event.http.method`: POST needs `title` (else 400) and answers **201**.

- `pskit validate` (gcp, staging): valid.
- invoke: POST → 201 `{"title": "Printer jam", "status": "open"}`; GET → 200 `{"tickets": []}`.

Deploy: **Deploy** or `pskit deploy -s staging`."""),
]
