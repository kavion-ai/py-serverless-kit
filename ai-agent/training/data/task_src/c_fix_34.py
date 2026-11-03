"""Category C (fix a validation error), batch 34 (aws/gcp/azure): user-experience variety. Hand-written;
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
    # ------------------------------------------------------------------ 661  aws beginner: what does "extra inputs" mean (memory_size)
    C(661, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: recipe-box
provider:
  name: aws
  region: us-east-1
functions:
  recipes:
    handler: app.recipes.list_recipes
    memory_size: 512
    events:
      - http: GET /recipes
""", "recipes", "list_recipes"),
      user="what does \"Extra inputs are not permitted\" mean? I only gave my function more memory and now it's red.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `memory_size` to `memory` on `recipes` (value 512 stays)", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.recipes.memory_size", value=None),
          S("set_config", path="functions.recipes.memory", value=512),
      ],
      final="""It means pskit found a key it doesn't know. Every place in pskit.yml has a fixed list of keys, and `memory_size` isn't on the function's list; the key is `memory`, in MB [docs/configuration.md#functions].

I renamed it: `recipes` now has `memory: 512`. Validate for aws: valid. The Functions page shows the function without the red mark now; the **Memory (MB)** field in its Basics section writes this key for you next time."""),

    # ------------------------------------------------------------------ 662  aws informal, Deploy page job failed: batch_size 0
    C(662, provider="aws", stage="staging", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=proj("""service: mail-queue
provider:
  name: aws
  region: eu-west-1
functions:
  api:
    handler: app.mail.enqueue
    events:
      - http: POST /mail
  sender:
    handler: app.mail.send
    events:
      - queue:
          name: outgoing-mail
          batch_size: 0
""", "mail", "enqueue", "send"),
      user="i press Deploy, job is fail very fast, say pskit.yml is invalid and somthing batch_size. i want one mail per time so i put 0?",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue batch_size",
            docs=[D("docs/events.md", "queue", words=75)]),
          S("propose_plan", steps=["Set `batch_size: 1` on the `outgoing-mail` trigger of `sender` (one message per call)",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.sender.events.0.queue.batch_size", value=1),
      ],
      final="""`batch_size` is how many messages one call gets, and the smallest is 1, so 0 is not allowed [docs/events.md#queue]. For one mail per call, 1 is the right value.

`sender` now has `batch_size: 1`. `pskit validate -p aws -s staging`: valid. Press **Deploy** again on the Deploy page."""),

    # ------------------------------------------------------------------ 663  aws pasted partial: which function exceeds 900
    C(663, provider="aws", stage="prod", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/providers.md#aws-aws-lambda"],
      project=proj("""service: data-exports
provider:
  name: aws
  region: us-east-2
  timeout: 60
functions:
  list-exports:
    handler: app.exports.list_exports
    events:
      - http: GET /exports
  build-export:
    handler: app.exports.build
    timeout: 1500
    events:
      - queue: export-jobs
  cleanup:
    handler: app.exports.cleanup
    events:
      - schedule: "0 4 * * *"
""", "exports", "list_exports", "build", "cleanup"),
      user="...exceeds AWS Lambda max 900s\n\nthat's all the deploy log showed. which function?",
      steps=[
          S("get_validation"),
          S("propose_plan", say="It's `build-export`, with `timeout: 1500`; the other two use the provider's 60 s.",
            steps=["Set `functions.build-export.timeout` to 900", "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.build-export.timeout", value=900),
      ],
      final="""`build-export` asked for 1500 s, but a Lambda function stops at 900 s (15 minutes) [docs/providers.md#aws-aws-lambda].

Set it to 900. `pskit validate -p aws -s prod`: valid. The full message names the function in brackets (`[functions.build-export]`); the **Problems** button in the top bar lists it too, and clicking it opens the function."""),

    # ------------------------------------------------------------------ 664  aws beginner proposes wrong fix: handler at provider level
    C(664, provider="aws", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: todo-api
provider:
  name: aws
  region: us-west-2
functions:
  todos:
    hander: app.todos.list_todos
    events:
      - http: GET /todos
""", "todos", "list_todos"),
      user="It says handler: Field required. I think I need to put handler under provider too? Can you add it there?",
      steps=[
          S("get_validation"),
          S("propose_plan", say="Adding it under provider wouldn't help: `provider` has no `handler` key, so it would be a new error. The real cause is a typo: the function has `hander` (missing l).",
            steps=["Rename `hander` to `handler` on `todos`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.todos.hander", value=None),
          S("set_config", path="functions.todos.handler", value="app.todos.list_todos"),
      ],
      final="""Each function needs its own `handler`; yours was spelled `hander`, so pskit saw no handler and an unknown key [docs/configuration.md#functions].

Fixed the spelling on `todos` (nothing added under `provider`). Validate for aws: valid. Re-check any time with the **Validate** button in the top bar or `pskit validate -p aws`."""),

    # ------------------------------------------------------------------ 665  aws auto, terse: workflow next typo
    C(665, provider="aws", stage="dev", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: kyc-flow
provider:
  name: aws
  region: eu-central-1
functions:
  check-id:
    handler: app.kyc.check_id
  score:
    handler: app.kyc.score
  notify:
    handler: app.kyc.notify
workflows:
  kyc:
    start_at: CheckId
    states:
      CheckId: {type: task, function: check-id, next: Scoring}
      Score: {type: task, function: score, next: Notify}
      Notify: {type: task, function: notify, end: true}
""", "kyc", "check_id", "score", "notify"),
      user="fix wf. no explanation needed",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["`CheckId.next`: `Scoring` -> `Score`", "Validate for aws"]),
          S("set_config", path="workflows.kyc.states.CheckId.next", value="Score"),
      ],
      final="""`CheckId.next` -> `Score` (was `Scoring`, no such state) [docs/workflows.md#workflow-keys]. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 666  aws rejected plan: keep base timeout, override for aws only
    C(666, provider="aws", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#providers-per-cloud-overrides", "docs/providers.md#aws-aws-lambda"],
      project=proj("""service: video-thumbs
provider:
  name: aws
  region: us-east-1
functions:
  thumbs:
    handler: app.video.thumbs
    timeout: 1200
    events:
      - storage: video-uploads
""", "video", "thumbs"),
      user="We deploy this service to AWS and also to our own servers with -p onprem. AWS validate fails on the 1200 s timeout of thumbs.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.thumbs.timeout` to 900", "Validate for aws, stage staging"],
            result={"decision": "rejected", "note": "No, on-prem really needs 1200. Only AWS should get less."}),
          S("search_docs", say="Understood: I'll leave the shared value alone and override it for AWS only.",
            query="providers per-cloud overrides functions",
            docs=[D("docs/configuration.md", "providers-per-cloud-overrides", end="may be written directly as shorthand for `provider: {...}`.")]),
          S("propose_plan", steps=["Keep `functions.thumbs.timeout: 1200`",
                                   "Add `providers.aws.functions.thumbs.timeout: 900`",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.aws", value={"functions": {"thumbs": {"timeout": 900}}}),
      ],
      final="""Lambda stops at 900 s, so 1200 can't be deployed to AWS [docs/providers.md#aws-aws-lambda]. As you asked, the shared value stays.

- `functions.thumbs.timeout: 1200` (used by onprem)
- `providers.aws.functions.thumbs.timeout: 900` (merged in only for AWS) [docs/configuration.md#providers-per-cloud-overrides]

`pskit validate -p aws -s staging`: valid. Check the other target with `pskit validate -p onprem -s staging`."""),

    # ------------------------------------------------------------------ 667  aws ask_user: existing queue name
    C(667, provider="aws", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#events-backed-by-a-resource", "docs/events.md#queue"],
      project=proj("""service: order-worker
provider:
  name: aws
  region: eu-west-1
functions:
  worker:
    handler: app.orders.work
    events:
      - queue:
          resource: orders
""", "orders", "work"),
      user="validate say uses unknown resource 'orders'. but orders queue is there in aws, my colleage make it last year",
      steps=[
          S("get_validation"),
          S("ask_user", question="`resource: orders` points to a `resources:` entry in pskit.yml, and there is none. Since the queue already exists in AWS, I'll use it directly with `existing: true`. What is its exact name in SQS?",
            answer="orders-prod-v2"),
          S("propose_plan", steps=["Set the trigger of `worker` to `queue: {name: orders-prod-v2, existing: true}`",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.worker.events.0", value={"queue": {"name": "orders-prod-v2", "existing": True}}),
      ],
      final="""`resource:` names an entry under `resources:` in pskit.yml, not a queue in AWS, and there was no such entry [docs/events.md#events-backed-by-a-resource]. A queue made outside pskit is used with `existing: true` [docs/events.md#queue].

`worker` now has `queue: {name: orders-prod-v2, existing: true}`; pskit only connects to it and never deletes it. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 668  gcp beginner: where do I find the project id
    C(668, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: pet-photos
provider:
  name: gcp
  region: europe-west1
functions:
  upload:
    handler: app.photos.upload
    events:
      - http: POST /photos
""", "photos", "upload"),
      user="I picked Google Cloud and now it says \"GCP needs provider.options.project (the GCP project id)\". I don't know what that is. Can you set it?",
      steps=[
          S("get_validation"),
          S("ask_user", question="The project id is the name of your Google Cloud project, shown in the project picker at the top of the Google Cloud console (or `gcloud config get-value project`). It looks like `pet-photos-123456`. What is yours?",
            answer="pet-photos-481516"),
          S("propose_plan", steps=["Set `provider.options.project: pet-photos-481516`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options", value={"project": "pet-photos-481516"}),
      ],
      final="""On Google Cloud everything is created inside a project, so pskit has to know which one [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

Set `provider.options.project: pet-photos-481516`. Validate for gcp: valid. You can change it later on **Overview & provider**, in the provider's options."""),

    # ------------------------------------------------------------------ 669  gcp informal typos: evnets
    C(669, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: sensor-log
provider:
  name: gcp
  region: asia-southeast1
  options:
    project: sensor-log-dev
functions:
  ingest:
    handler: app.sensors.ingest
    evnets:
      - http: POST /readings
""", "sensors", "ingest"),
      user="i add triger in yaml but functions page dont show it and validat say evnets extra. whats wrong",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `evnets` to `events` on `ingest`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest.evnets", value=None),
          S("set_config", path="functions.ingest.events", value=[{"http": "POST /readings"}]),
      ],
      final="""Small typo: the key is `events`, you had `evnets`, so pskit rejected that key and the function had no trigger to show [docs/configuration.md#functions].

Renamed it; `ingest` has `- http: POST /readings` again. Validate for gcp: valid. The trigger shows on the Functions page now."""),

    # ------------------------------------------------------------------ 670  gcp pasted partial: unknown state
    C(670, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: loan-review
provider:
  name: gcp
  region: us-central1
  options:
    project: loan-review-staging
functions:
  collect:
    handler: app.loans.collect
  assess:
    handler: app.loans.assess
  decide:
    handler: app.loans.decide
workflows:
  review:
    start_at: Collect
    states:
      Collect: {type: task, function: collect, next: Assess}
      Assess: {type: task, function: assess, next: Decision}
      Decide: {type: task, function: decide, end: true}
""", "loans", "collect", "assess", "decide"),
      user="points to unknown state 'Decision'\n\n^ only line I copied",
      steps=[
          S("get_validation"),
          S("ask_user", question="`Assess` goes `next: Decision`, but the workflow's states are Collect, Assess and Decide. Should `Assess` continue to `Decide`?",
            options=["yes, Decide", "no, I'll add a Decision state"], answer="yes, Decide"),
          S("propose_plan", steps=["Set `Assess.next` to `Decide`", "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.review.states.Assess.next", value="Decide"),
      ],
      final="""`next` must name a state of the same workflow; `Decision` didn't exist, `Decide` does [docs/workflows.md#workflow-keys].

`Assess` now goes to `Decide`. `pskit validate -p gcp -s staging`: valid. The Workflows page draws the arrow again."""),

    # ------------------------------------------------------------------ 671  gcp terse: fix only, 540 s
    C(671, provider="gcp", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: tile-render
provider:
  name: gcp
  region: europe-west4
  options:
    project: tile-render-prod
functions:
  render:
    handler: app.tiles.render
    timeout: 900
    memory: 2048
    events:
      - topic: render-requests
""", "tiles", "render"),
      user="render: limited to 540s. just fix",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["`render.timeout`: 900 -> 540", "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.render.timeout", value=540),
      ],
      final="""`render.timeout: 540` (GCP event functions max) [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. `pskit validate -p gcp -s prod`: valid."""),

    # ------------------------------------------------------------------ 672  gcp wrong fix proposed: jwt -> key
    C(672, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      project=proj("""service: habit-app
provider:
  name: gcp
  region: europe-west1
  options:
    project: habit-app-dev
functions:
  habits:
    handler: app.habits.list_habits
    events:
      - http:
          path: /habits
          method: GET
          auth: jwt
          authorizer:
            issuer: https://securetoken.google.com/habit-app-dev
            audience: [habit-app-dev]
""", "habits", "list_habits"),
      user="Validate says jwt auth isn't supported on GCP. Our mobile app sends a Firebase ID token. I'll switch to auth: key instead, ok?",
      steps=[
          S("get_validation"),
          S("search_docs", query="http auth support providers",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("ask_user", say="`key` won't work either: it is only supported on Azure and Huawei, so GCP would report a new error.",
            question="On GCP the choices are `none` (public; your handler verifies the Firebase token) or `iam` (callers need a Google identity token, which a mobile app user normally doesn't have). Which one?",
            options=["none + verify token in the handler", "iam"], answer="none + verify token in the handler"),
          S("propose_plan", steps=["Set `/habits` to `auth: none` and remove the `authorizer`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.habits.events.0.http", value={"path": "/habits", "method": "GET", "auth": "none"}),
      ],
      final="""`jwt` is AWS-only and `key` is Azure/Huawei-only; GCP takes `none` or `iam` [docs/events.md#http].

`/habits` is now `auth: none` without an authorizer. Validate for gcp: valid. Before returning data, the handler must check `event.http.headers.get("authorization")` and verify the Firebase token; reject with `Unauthorized` when it's missing or wrong."""),

    # ------------------------------------------------------------------ 673  gcp rejected plan: start_at wrong guess
    C(673, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: blog-publish
provider:
  name: gcp
  region: us-east1
  options:
    project: blog-publish-dev
functions:
  fetch-draft:
    handler: app.blog.fetch_draft
  check-links:
    handler: app.blog.check_links
  publish:
    handler: app.blog.publish
workflows:
  publish-post:
    start_at: Start
    states:
      Fetch: {type: task, function: fetch-draft, next: CheckLinks}
      CheckLinks: {type: task, function: check-links, next: Publish}
      Publish: {type: task, function: publish, end: true}
""", "blog", "fetch_draft", "check_links", "publish"),
      user="my workflow is red on the Workflows page, something about start_at. I don't really get what start_at is",
      steps=[
          S("get_validation"),
          S("propose_plan", say="`start_at` is the name of the first step the workflow runs. Yours says `Start`, but no step has that name.",
            steps=["Set `start_at` to `CheckLinks`", "Validate for gcp"],
            result={"decision": "rejected", "note": "No, it has to fetch the draft first."}),
          S("propose_plan", say="Right, sorry: the first step is `Fetch`, which then goes to `CheckLinks`.",
            steps=["Set `start_at` to `Fetch`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.publish-post.start_at", value="Fetch"),
      ],
      final="""`start_at` must be the name of one of the workflow's states; `Start` wasn't one [docs/workflows.md#workflow-keys].

As you said, it now starts at `Fetch` -> `CheckLinks` -> `Publish`. Validate for gcp: valid. On the Workflows page the first state is the one marked as the start."""),

    # ------------------------------------------------------------------ 674  gcp auto: handler without module
    C(674, provider="gcp", stage="staging", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: invoice-pdf
provider:
  name: gcp
  region: europe-west1
  options:
    project: invoice-pdf-staging
functions:
  make-pdf:
    handler: make_pdf
    events:
      - queue: pdf-jobs
""", "invoices", "make_pdf"),
      user="handler 'make_pdf' must be package.module.function ?? the function is make_pdf, i dont understand",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", say="The function is in `app/invoices.py`, so pskit needs the full path to it.",
            steps=["Set `functions.make-pdf.handler` to `app.invoices.make_pdf`", "Validate for gcp, stage staging"]),
          S("set_config", path="functions.make-pdf.handler", value="app.invoices.make_pdf"),
      ],
      final="""`handler` must say where the function lives: folder `app`, file `invoices.py`, function `make_pdf` -> `app.invoices.make_pdf` [docs/configuration.md#functions].

Set that on `make-pdf`. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 675  azure beginner: lowercase queue name
    C(675, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#queue"],
      project=proj("""service: ticket-desk
provider:
  name: azure
  region: westeurope
functions:
  new-ticket:
    handler: app.tickets.create
    events:
      - http: POST /tickets
  triage:
    handler: app.tickets.triage
    events:
      - queue: NewTickets
""", "tickets", "create", "triage"),
      user="what does \"must be 3-63 lowercase letters, digits, dashes\" mean? My queue is called NewTickets, that's 10 letters.",
      steps=[
          S("get_validation"),
          S("propose_plan", say="The length is fine; the problem is the capital letters N and T. Azure queue names may only use small letters, digits and dashes.",
            steps=["Rename the queue of `triage` to `new-tickets`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.triage.events.0", value={"queue": "new-tickets"}),
      ],
      final="""Azure Storage Queue names must be 3-63 characters of lowercase letters, digits and dashes, so `NewTickets` failed only because of the capitals [docs/events.md#queue].

`triage` now listens on `new-tickets`. Validate for azure: valid. If `new-ticket` sends messages from code, use the new name there too."""),

    # ------------------------------------------------------------------ 676  azure informal: python 3.13 on my pc
    C(676, provider="azure", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#default-runtime", "docs/troubleshooting.md#configuration"],
      project=proj("""service: quiz-api
provider:
  name: azure
  region: northeurope
  runtime: python3.13
functions:
  questions:
    handler: app.quiz.questions
    events:
      - http: GET /questions
""", "quiz", "questions"),
      user="azure say not suport python3.13. but i have 3.13 in my pc, i must uninstall?",
      steps=[
          S("get_validation"),
          S("search_docs", query="does not support python runtime default",
            docs=[D("docs/troubleshooting.md", "configuration", start="**`<provider> does not support python3.12`**", end="(`pskit providers --json`)."),
                  D("docs/configuration.md", "default-runtime")]),
          S("propose_plan", steps=["Remove `provider.runtime` so pskit uses python3.12 on Azure", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.runtime", value=None),
      ],
      final="""No need to uninstall anything. `runtime` is the Python version in Azure's cloud, not on your PC, and Azure Functions offers 3.9 to 3.12 [docs/troubleshooting.md#configuration].

I removed `runtime: python3.13`, so pskit picks python3.12 for Azure [docs/configuration.md#default-runtime]. Validate for azure: valid. Keep your code 3.12-compatible (no 3.13-only features)."""),

    # ------------------------------------------------------------------ 677  azure pasted partial: auth iam
    C(677, provider="azure", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=proj("""service: hr-portal
provider:
  name: azure
  region: westeurope
functions:
  employees:
    handler: app.hr.employees
    events:
      - http:
          path: /employees
          method: GET
          auth: iam
""", "hr", "employees"),
      user="\"...is not supported on Azure; use none or key\" what's the actual setting it's complaining about?",
      steps=[
          S("get_validation"),
          S("ask_user", say="It's the `auth: iam` on `GET /employees`.",
            question="Azure in pskit takes `key` (callers send a function key) or `none` (public). Which one for `/employees`?",
            options=["key", "none"], answer="key"),
          S("propose_plan", steps=["Set `auth: key` on `GET /employees`", "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.employees.events.0.http.auth", value="key"),
      ],
      final="""`auth: iam` is for AWS, GCP and Huawei; on Azure only `none` and `key` exist [docs/events.md#http].

`/employees` now has `auth: key` (Azure function key). `pskit validate -p azure -s staging`: valid. After deploy, callers pass the function key with each request."""),

    # ------------------------------------------------------------------ 678  azure Problems button: errors vs warnings
    C(678, provider="azure", stage="prod", mode="ask", page="YAML", persona="beginner",
      sources=["docs/events.md#schedule", "docs/troubleshooting.md#configuration"],
      project=proj("""service: payroll-jobs
provider:
  name: azure
  region: westeurope
functions:
  monthly-run:
    handler: app.payroll.monthly
    runtime: python3.13
    events:
      - schedule:
          cron: "0 6 1 * *"
          timezone: Europe/Berlin
""", "payroll", "monthly"),
      user="The Problems button says 1 error · 1 warning. Do I have to fix both before I can deploy?",
      steps=[
          S("get_validation"),
          S("propose_plan", say="Only the error blocks a deploy; the warning tells you something is ignored.",
            steps=["Remove `runtime: python3.13` from `monthly-run` (the error), so it uses python3.12",
                   "Leave the timezone warning (Azure timers run in UTC)", "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.monthly-run.runtime", value=None),
      ],
      final="""Only errors block a deploy. Yours was `runtime: python3.13`, which Azure doesn't offer [docs/troubleshooting.md#configuration]; I removed it, so the function uses python3.12. `pskit validate -p azure -s prod`: valid, 0 errors.

The warning stays: Azure timers run in UTC, so `timezone: Europe/Berlin` is ignored and `0 6 1 * *` fires at 06:00 UTC [docs/events.md#schedule]. If it must be 06:00 Berlin time, change the hour (e.g. `0 5 1 * *` in winter)."""),

    # ------------------------------------------------------------------ 679  azure rejected plan: deleted blobs -> disable on azure
    C(679, provider="azure", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#azure-azure-functions", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=proj("""service: asset-index
provider:
  name: azure
  region: westeurope
functions:
  index:
    handler: app.assets.index
    events:
      - http: GET /assets
  on-delete:
    handler: app.assets.on_delete
    events:
      - storage:
          bucket: assets
          events: [deleted]
""", "assets", "index", "on_delete"),
      user="on-delete removes search entries when a file is deleted. Azure validate fails on it. We deploy the same service to AWS too.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Change `on-delete` to `events: [created]`", "Validate for azure, stage staging"],
            result={"decision": "rejected", "note": "That changes what it does. It has to react to deletes, so just don't deploy it on Azure."}),
          S("propose_plan", say="Understood: keep it as is and switch it off on Azure only.",
            steps=["Add `providers.azure.functions.on-delete.enabled: false`", "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure", value={"functions": {"on-delete": {"enabled": False}}}),
      ],
      final="""Azure blob triggers fire only on created/updated blobs, so a `deleted` trigger can't run there [docs/providers.md#azure-azure-functions].

As you asked, `on-delete` is unchanged and `providers.azure.functions.on-delete.enabled: false` skips it on Azure; AWS still deploys it [docs/configuration.md#switch-something-off-on-one-cloud]. `pskit validate -p azure -s staging`: valid, with one warning that `on-delete` is disabled there. On Azure deleted files keep their search entries until something else cleans them up."""),

    # ------------------------------------------------------------------ 680  azure auto: ${self:custom.queue} with custom.queues
    C(680, provider="azure", stage="dev", mode="auto", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: sms-gateway
provider:
  name: azure
  region: westeurope
custom:
  queues:
    outbound: sms-outbound
functions:
  send:
    handler: app.sms.send
    events:
      - queue: ${self:custom.queue.outbound}
""", "sms", "send"),
      user="Error: unresolved variables: self:custom.queue.outbound",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Change the reference to `${self:custom.queues.outbound}` (the key is `queues`)", "Validate for azure"]),
          S("set_config", path="functions.send.events.0", value={"queue": "${self:custom.queues.outbound}"}),
      ],
      final="""`${self:...}` must follow the real keys; `custom` has `queues`, not `queue` [docs/configuration.md#variables].

The trigger now reads `${self:custom.queues.outbound}` (= `sms-outbound`). Validate for azure: valid."""),
]
