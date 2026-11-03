"""Category B (build / add), batch 7: on-premises only. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

SERVERS = json.dumps({"servers": {
    "app-1": {"host": "192.0.2.10", "user": "pskit", "port": 22},
    "app-2": {"host": "192.0.2.11", "user": "pskit", "port": 22},
    "db-1": {"host": "192.0.2.40", "user": "pskit", "port": 22},
    "gpu-box": {"host": "192.0.2.20", "user": "pskit", "port": 22},
    "lb-1": {"host": "192.0.2.30", "user": "pskit", "port": 22}}}, indent=2)
CLUSTERS = json.dumps({"clusters": {"prod": {"orchestrator": "swarm", "master": "app-1", "servers": ["app-2"],
                                             "balancer": {"server": "lb-1", "port": 80}}}}, indent=2)


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", provider="onprem", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 121
    B(121, stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: finance-reports
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8101
functions: {}
""",
          "requirements.txt": ""}),
      user="Add GET /reports/{year}/{month} that returns a CSV download (content-type text/csv, filename report-<year>-<month>.csv) with the columns day,revenue. Use dummy numbers for the days 1-3. A month outside 1-12 must give 400.",
      steps=[
          S("get_project"),
          S("search_docs", query="return headers tuple body status content-type",
            docs=[D("docs/handlers.md", "returning-a-response", end="| `(body, status)` / `(body, status, headers)` | Flask-style |")]),
          S("propose_plan", steps=["Write `app/reports.py`: read year/month from path_params, BadRequest for a bad month, return (csv, 200, headers)",
                                   "Add function `monthly-report` on GET /reports/{year}/{month}",
                                   "Validate (onprem, prod) and call /reports/2026/10 locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/reports.py", content=FUTURE + """import csv
import io

from py_serverless_kit import BadRequest


def monthly_report(event, ctx):
    params = event.http.path_params
    year, month = params.get("year", ""), params.get("month", "")
    if not month.isdigit() or not 1 <= int(month) <= 12:
        raise BadRequest("month must be 1-12")
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\\n")
    writer.writerow(["day", "revenue"])
    for day, revenue in ((1, 1200.5), (2, 980.0), (3, 1510.25)):
        writer.writerow([day, revenue])
    headers = {
        "content-type": "text/csv",
        "content-disposition": f'attachment; filename="report-{year}-{int(month):02d}.csv"',
    }
    return out.getvalue(), 200, headers
"""),
          S("set_config", path="functions.monthly-report",
            value={"handler": "app.reports.monthly_report", "events": [{"http": "GET /reports/{year}/{month}"}]}),
          S("invoke_local", function="monthly-report", method="GET", path="/reports/2026/10"),
      ],
      final="""Added `monthly-report` on `GET /reports/{year}/{month}`. It returns `(csv_text, 200, headers)`, the Flask-style tuple [docs/handlers.md#returning-a-response], with:

- `content-type: text/csv`
- `content-disposition: attachment; filename="report-2026-10.csv"`

Checks:
- `pskit validate` (onprem, prod): valid.
- Local `GET /reports/2026/10`: 200, the CSV `day,revenue` plus the 3 dummy rows, and both headers.
- A month like `13` or `ab` raises `BadRequest`, which gives a 400.

Check the 400: `pskit invoke -f monthly-report --method GET --path /reports/2026/13`. Deploy: **Deploy** page (typed confirmation for prod) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 122
    B(122, stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: ledger
provider:
  name: onprem
  region: local
  options:
    port: 8102
functions: {}
""",
          "requirements.txt": ""}),
      user="ledger-writer on queue ledger-entries: fifo, one msg at a time, visibility 120s, timeout 20",
      steps=[
          S("get_project"),
          S("search_docs", query="queue fifo visibility_timeout on premises",
            docs=[D("docs/providers.md", "onprem-on-premises", start="| queue |", end="`BatchResult` retries only the failed ids |")]),
          S("propose_plan", steps=["Write `app/ledger.py`: apply each entry, log account + amount",
                                   "Add `ledger-writer` (timeout 20) with queue {name: ledger-entries, fifo: true, batch_size: 1, visibility_timeout: 120}",
                                   "Validate (onprem, staging), invoke"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/ledger.py", content=FUTURE + """

def write_entry(event, ctx):
    applied = []
    for record in event.records:
        entry = record.json(default={}) or {}
        ctx.logger.info("ledger entry", extra={"account": entry.get("account"), "amount": entry.get("amount")})
        applied.append(entry.get("entry_id"))
    return {"applied": applied}
"""),
          S("set_config", path="functions.ledger-writer",
            value={"handler": "app.ledger.write_entry", "timeout": 20,
                   "events": [{"queue": {"name": "ledger-entries", "fifo": True, "batch_size": 1,
                                         "visibility_timeout": 120}}]}),
          S("invoke_local", function="ledger-writer", type="queue",
            data=[{"entry_id": "e-1001", "account": "4000", "amount": -25.0}]),
      ],
      final="""Added `ledger-writer` (timeout 20 s):

```yaml
events:
  - queue: {name: ledger-entries, fifo: true, batch_size: 1, visibility_timeout: 120}
```

On premises `fifo`, `batch_size` and `visibility_timeout` are all honoured by the built-in file queue [docs/providers.md#onprem-on-premises]. Without the explicit 120 the default would be `max(30, 6 x timeout)` = 120 anyway.

- validate (onprem, staging): valid.
- invoke with one entry: `{"applied": ["e-1001"]}`.

Deploy: `pskit deploy -s staging`. Enqueue after deploy: `POST /__pskit/queues/ledger-entries`."""),

    # ------------------------------------------------------------------ 123
    B(123, stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: accounts
provider:
  name: onprem
  region: local
  options:
    port: 8103
functions:
  signup:
    handler: app.signup.create
    events:
    - http: POST /signup
""",
          "app/__init__.py": "",
          "app/signup.py": FUTURE + """

def create(event, ctx):
    return {"created": True}, 201
""",
          "requirements.txt": ""}),
      user="Every signup is published to the topic `user-signups` with an attribute `plan` (free or pro). I need two subscribers: `welcome-mail` for every signup, and `crm-sync` only for plan=pro. Both just log the user email for now.",
      steps=[
          S("get_project"),
          S("search_docs", query="topic subscriber filter attributes fan-out",
            docs=[D("docs/events.md", "topic", words=120)]),
          S("propose_plan", steps=["Write `app/subscribers.py` with `welcome` and `crm_sync`, both logging record emails",
                                   "Add `welcome-mail` on topic user-signups (no filter)",
                                   "Add `crm-sync` on topic {name: user-signups, filter: {plan: [pro]}}",
                                   "Validate for onprem and invoke crm-sync with a pro signup"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/subscribers.py", content=FUTURE + """

def _emails(event):
    return [(r.json(default={}) or {}).get("email") for r in event.records]


def welcome(event, ctx):
    emails = _emails(event)
    ctx.logger.info("welcome mail", extra={"to": emails})
    return {"welcomed": emails}


def crm_sync(event, ctx):
    emails = _emails(event)
    ctx.logger.info("crm sync", extra={"users": emails})
    return {"synced": emails}
"""),
          S("set_config", path="functions.welcome-mail",
            value={"handler": "app.subscribers.welcome", "events": [{"topic": "user-signups"}]}),
          S("set_config", path="functions.crm-sync",
            value={"handler": "app.subscribers.crm_sync",
                   "events": [{"topic": {"name": "user-signups", "filter": {"plan": ["pro"]}}}]}),
          S("invoke_local", function="crm-sync", type="topic", data=[{"email": "lee@example.com", "plan": "pro"}]),
      ],
      final="""Two subscribers on `user-signups`. On premises the topic fans out to every subscriber whose filter matches:

```yaml
functions:
  welcome-mail:
    handler: app.subscribers.welcome
    events:
      - topic: user-signups
  crm-sync:
    handler: app.subscribers.crm_sync
    events:
      - topic: {name: user-signups, filter: {plan: [pro]}}
```

The filter is an exact match on the message attributes first, then on JSON body fields [docs/providers.md#onprem-on-premises]. So `plan` works whether you publish it as an attribute or inside the body.

- `pskit validate` (onprem): valid.
- `crm-sync` invoked with a pro signup: `{"synced": ["lee@example.com"]}`.

After deploy, publish a test with `POST /__pskit/topics/user-signups` and body `{"message": {...}, "attributes": {"plan": "pro"}}`. Test locally: `pskit invoke -f welcome-mail -t topic -d '[{"email": "a@example.com"}]'`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 124
    B(124, stage="prod", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: exports
provider:
  name: onprem
  region: local
  options:
    port: 8104
functions:
  build-export:
    handler: app.exports.build
    events:
    - schedule: 0 2 * * *
""",
          "app/__init__.py": "",
          "app/exports.py": FUTURE + """

def build(event, ctx):
    return {"built": True}
""",
          "requirements.txt": ""}),
      user="somebody delete files from exports bucket and nobody know who. i want log every time a file is deleted there",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/audit.py`: log key + action for each deleted object",
                                   "Add `audit-deletes` with storage {bucket: exports, events: [deleted]}",
                                   "Validate (onprem, prod), invoke with a deleted object"]),
          S("write_file", path="app/audit.py", content=FUTURE + """

def on_delete(event, ctx):
    gone = []
    for record in event.records:
        ctx.logger.warning("file deleted", extra={"bucket": record.bucket, "key": record.key, "action": record.action})
        gone.append(record.key)
    return {"deleted": gone}
"""),
          S("set_config", path="functions.audit-deletes",
            value={"handler": "app.audit.on_delete",
                   "events": [{"storage": {"bucket": "exports", "events": ["deleted"]}}]}),
          S("invoke_local", function="audit-deletes", type="storage",
            data={"bucket": "exports", "key": "2026-10-31/orders.csv", "size": 0, "action": "deleted"}),
      ],
      final="""Done. `audit-deletes` runs each time a file disappears from the `exports` bucket and writes a WARNING log line with the bucket and key:

```yaml
- storage: {bucket: exports, events: [deleted]}
```

On premises the bucket is a folder, and the host sees `deleted` when a file is gone [docs/providers.md#onprem-on-premises].

- validate (onprem, prod): valid.
- invoke with a deleted file: `{"deleted": ["2026-10-31/orders.csv"]}`.

Note: this tells you *which* file and *when*, not *who*. Who deleted it is only in the server's own logs or permissions.

See the log lines: **Logs** page, or `pskit logs --function audit-deletes`. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 125
    B(125, stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#choice-rules", "docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: helpdesk
provider:
  name: onprem
  region: local
  options:
    port: 8105
functions:
  page-oncall:
    handler: app.tickets.page_oncall
  add-to-backlog:
    handler: app.tickets.add_to_backlog
""",
          "app/__init__.py": "",
          "app/tickets.py": FUTURE + """

def page_oncall(event, ctx):
    return {**(event.data or {}), "routed": "on-call"}


def add_to_backlog(event, ctx):
    return {**(event.data or {}), "routed": "backlog"}
""",
          "requirements.txt": ""}),
      user="tickets with priority urgent should go to page-oncall, all other tickets to add-to-backlog. can pskit decide that automatically?",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow choice branch equals default",
            docs=[D("docs/workflows.md", "choice-rules", end="next: Standard")]),
          S("propose_plan", steps=["Add workflow `route-ticket`: a choice state (priority equals urgent -> PageOncall, default Backlog)",
                                   "PageOncall and Backlog are task states that end",
                                   "Validate for onprem and run page-oncall as a workflow task"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.route-ticket",
            value={"start_at": "Route",
                   "states": {"Route": {"type": "choice",
                                        "choices": [{"variable": "$.priority", "equals": "urgent", "next": "PageOncall"}],
                                        "default": "Backlog"},
                              "PageOncall": {"type": "task", "function": "page-oncall", "end": True},
                              "Backlog": {"type": "task", "function": "add-to-backlog", "end": True}}}),
          S("invoke_local", function="page-oncall", type="workflow", data={"ticket": 311, "priority": "urgent"}),
      ],
      final="""Yes. A **workflow** with a *choice* state makes that decision:

```yaml
workflows:
  route-ticket:
    start_at: Route
    states:
      Route:
        type: choice
        choices:
          - {variable: $.priority, equals: urgent, next: PageOncall}
        default: Backlog
      PageOncall: {type: task, function: page-oncall, end: true}
      Backlog:    {type: task, function: add-to-backlog, end: true}
```

`$.priority` means "the `priority` field of the ticket". Anything that is not `urgent` goes to `default` [docs/workflows.md#choice-rules].

- `pskit validate` (onprem): valid. It runs on the embedded engine inside your host.
- `page-oncall` run with an urgent ticket: `"routed": "on-call"`.

Try the whole decision locally: `pskit workflow run route-ticket -i '{"ticket": 312, "priority": "low"}' --history`. In studio, the **Workflows** page shows the states. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 126
    B(126, stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#data-flow"],
      project=dict(files={
          "pskit.yml": """service: gallery
provider:
  name: onprem
  region: local
  options:
    port: 8106
functions:
  resize-image:
    handler: app.images.resize
  publish-album:
    handler: app.images.publish
""",
          "app/__init__.py": "",
          "app/images.py": FUTURE + """

def resize(event, ctx):
    image = dict(event.data or {})
    return {"id": image.get("id"), "thumb": f"thumbs/{image.get('id')}.jpg"}


def publish(event, ctx):
    data = dict(event.data or {})
    return {"album": data.get("album"), "published": len(data.get("thumbs") or [])}
""",
          "requirements.txt": ""}),
      user="Workflow `build-album`: input is {album, images: [{id}, ...]}. Resize every image with resize-image, at most 4 at the same time, keep the results under $.thumbs, then call publish-album with the whole data.",
      steps=[
          S("get_project"),
          S("search_docs", query="map state items_path iterator max_concurrency result_path",
            docs=[D("docs/workflows.md", "state-types", start="| `map` |", end="result is a list |"),
                  D("docs/workflows.md", "data-flow", start="- `result_path`", end="passes the input through.")]),
          S("propose_plan", steps=["Add workflow `build-album`: ResizeAll (map over $.images, max_concurrency 4, iterator Resize -> resize-image, result_path $.thumbs) -> Publish (publish-album, end)",
                                   "Validate (onprem, staging) and run resize-image as a workflow task"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.build-album",
            value={"start_at": "ResizeAll",
                   "states": {"ResizeAll": {"type": "map", "items_path": "$.images", "max_concurrency": 4,
                                            "iterator": {"start_at": "Resize",
                                                         "states": {"Resize": {"type": "task",
                                                                               "function": "resize-image",
                                                                               "end": True}}},
                                            "result_path": "$.thumbs", "next": "Publish"},
                              "Publish": {"type": "task", "function": "publish-album", "end": True}}}),
          S("invoke_local", function="resize-image", type="workflow", data={"id": "img-9"}),
      ],
      final="""Added `build-album`:

```yaml
workflows:
  build-album:
    start_at: ResizeAll
    states:
      ResizeAll:
        type: map
        items_path: $.images
        max_concurrency: 4
        iterator:
          start_at: Resize
          states:
            Resize: {type: task, function: resize-image, end: true}
        result_path: $.thumbs
        next: Publish
      Publish: {type: task, function: publish-album, end: true}
```

The map runs the iterator once per image, at most 4 at a time. Its list of results goes to `$.thumbs`, and `album` and `images` stay in the data, so `publish-album` gets all of it [docs/workflows.md#data-flow].

- `pskit validate` (onprem, staging): valid (embedded engine).
- `resize-image` with `{"id": "img-9"}`: `{"id": "img-9", "thumb": "thumbs/img-9.jpg"}`.

Run it all locally: `pskit workflow run build-album -i '{"album": "trip", "images": [{"id": "a"}, {"id": "b"}]}' --history`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 127
    B(127, stage="dev", mode="auto", page="Overview", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: todo
provider:
  name: onprem
  region: local
  options:
    port: 8107
functions: {}
""",
          "requirements.txt": ""}),
      user="new project todo list. need list all todos and add todo with title. title empty -> error. on our server not cloud",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/todos.py`: list_todos and add_todo (BadRequest for an empty title, 201 on success)",
                                   "Add `list-todos` on GET /todos and `add-todo` on POST /todos",
                                   "Validate for onprem, POST a todo locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/todos.py", content=FUTURE + """from py_serverless_kit import BadRequest

TODOS = []


def list_todos(event, ctx):
    return {"todos": TODOS}


def add_todo(event, ctx):
    title = ((event.http.json(default={}) or {}).get("title") or "").strip()
    if not title:
        raise BadRequest("title is required")
    todo = {"id": len(TODOS) + 1, "title": title, "done": False}
    TODOS.append(todo)
    return todo, 201
"""),
          S("set_config", path="functions.list-todos",
            value={"handler": "app.todos.list_todos", "events": [{"http": "GET /todos"}]}),
          S("set_config", path="functions.add-todo",
            value={"handler": "app.todos.add_todo", "events": [{"http": "POST /todos"}]}),
          S("invoke_local", function="add-todo", method="POST", path="/todos", data={"title": "Buy milk"}),
      ],
      final="""Your todo project is ready for your own server (provider `onprem`, port 8107):

```yaml
functions:
  list-todos:
    handler: app.todos.list_todos
    events:
      - http: GET /todos
  add-todo:
    handler: app.todos.add_todo
    events:
      - http: POST /todos
```

- `pskit validate` (onprem): valid.
- Local `POST /todos` with `{"title": "Buy milk"}`: 201, `{"id": 1, "title": "Buy milk", "done": false}`.
- An empty title gives 400 `title is required`.

Important: the list is only in memory, so a restart empties it. Use a database (for example a Postgres resource) before real use.

Test: `pskit invoke -f list-todos --method GET --path /todos`. Run it: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 128
    B(128, stage="staging", mode="ask", page="Deploy", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: onprem
  region: local
  options:
    port: 8108
functions:
  items:
    handler: app.items.list_items
    events:
    - http: GET /items
""",
          "app/__init__.py": "",
          "app/items.py": FUTURE + """

def list_items(event, ctx):
    return []
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="staging: run as docker container on saved server app-2, image pskit/catalog:staging, restart always",
      steps=[
          S("get_project"),
          S("search_docs", query="deploy method docker server image restart",
            docs=[D("docs/providers.md", "onprem-on-premises", start="# Docker on a server. The image is built here",
                    end="restart: unless-stopped")]),
          S("propose_plan", steps=["provider.options.deploy: {server: app-2, method: docker, image: pskit/catalog:staging, restart: always}",
                                   "provider.options.host: 0.0.0.0",
                                   "Validate (onprem, staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy",
            value={"server": "app-2", "method": "docker", "image": "pskit/catalog:staging", "restart": "always"}),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
      ],
      final="""Set:

```yaml
provider:
  options:
    host: 0.0.0.0
    port: 8108
    deploy: {server: app-2, method: docker, image: pskit/catalog:staging, restart: always}
```

Deploy builds the image on this machine (Docker CLI needed), copies it to app-2 over SSH, then runs `docker load` and `docker run` there. Docker is installed on app-2 first if it is missing (`install_docker` defaults to true, with `sudo`) [docs/providers.md#onprem-on-premises]. `host: 0.0.0.0` lets the container accept LAN traffic.

validate (onprem, staging): valid.

Deploy: **Deploy** page or `pskit deploy -s staging`. It waits until the container answers `/__pskit/health`."""),

    # ------------------------------------------------------------------ 129
    B(129, stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: telemetry
provider:
  name: onprem
  region: local
  options:
    port: 8109
functions:
  ingest:
    handler: app.ingest.receive
    events:
    - http: POST /metrics
""",
          "app/__init__.py": "",
          "app/ingest.py": FUTURE + """

def receive(event, ctx):
    return None
""",
          "requirements.txt": ""}),
      user="Deploy prod over SSH to 192.0.2.50 as user `deploy`. The key path comes from the TELEMETRY_SSH_KEY variable. Install into /srv/telemetry as a systemd service so it survives reboots. The server is an ARM64 Ubuntu box without Python. Other machines send metrics to it.",
      steps=[
          S("get_project"),
          S("search_docs", query="ssh deploy systemd python bundle target_arch",
            docs=[D("docs/providers.md", "onprem-on-premises", start="# SSH + portable CPython + systemd",
                    end="sudo: true                      # needed to write /etc/systemd/system")]),
          S("propose_plan", steps=["provider.options.deploy: method ssh, host 192.0.2.50, user deploy, pem ${env:TELEMETRY_SSH_KEY, }, path /srv/telemetry, python bundle, target_os linux, target_arch arm64, install systemd, sudo true",
                                   "provider.options.host: 0.0.0.0",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy",
            value={"method": "ssh", "host": "192.0.2.50", "user": "deploy", "pem": "${env:TELEMETRY_SSH_KEY, }",
                   "path": "/srv/telemetry", "python": "bundle", "target_os": "linux", "target_arch": "arm64",
                   "install": "systemd", "sudo": True}),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
      ],
      final="""Set:

```yaml
provider:
  options:
    host: 0.0.0.0
    port: 8109
    deploy:
      method: ssh
      host: 192.0.2.50
      user: deploy
      pem: ${env:TELEMETRY_SSH_KEY, }
      path: /srv/telemetry
      python: bundle
      target_os: linux
      target_arch: arm64
      install: systemd
      sudo: true
```

- `python: bundle` + `target_arch: arm64`: a portable ARM64 CPython is shipped with the app, and pip picks matching wheels.
- `install: systemd` + `sudo: true`: a unit in `/etc/systemd/system`, restarted on every deploy. The `sudo` must work without a password (`sudo -n`) [docs/providers.md#onprem-on-premises].
- `pem` empty (variable unset) falls back to the SSH agent / default key.

validate (onprem, prod): valid. Until `host: 0.0.0.0` was set it warned that the host would only bind 127.0.0.1.

Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. It waits for `/__pskit/health` and shows `systemctl status` if that fails."""),

    # ------------------------------------------------------------------ 130
    B(130, stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/resources.md#secrets", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: newsletter
provider:
  name: onprem
  region: local
  options:
    port: 8110
functions:
  send-digest:
    handler: app.digest.send
    events:
    - schedule: 0 8 * * 1
""",
          "app/__init__.py": "",
          "app/digest.py": FUTURE + """

def send(event, ctx):
    return {"sent": False}
""",
          "requirements.txt": ""}),
      user="I tried adding `MAIL_API_KEY: ${env:MAIL_API_KEY}` and got\n\nError: unresolved variables: env:MAIL_API_KEY\n\nThe key is not on my laptop, it only exists on the server. How should send-digest get it? Show in the result whether the key is there.",
      steps=[
          S("get_project"),
          S("search_docs", query="env_file secrets host environment on premises",
            docs=[D("docs/resources.md", "secrets", words=120)]),
          S("propose_plan", steps=["provider.options.env_file: .env.onprem (KEY=VALUE file shipped next to the host, loaded at start; not in Terraform state)",
                                   "`send` reports whether MAIL_API_KEY is set, via ctx.env (no ${env:} for it in pskit.yml)",
                                   "Validate for onprem and run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.env_file", value=".env.onprem"),
          S("write_file", path="app/digest.py", content=FUTURE + """

def send(event, ctx):
    key = ctx.env.get("MAIL_API_KEY", "")
    if not key:
        ctx.logger.warning("MAIL_API_KEY is not set, digest not sent")
        return {"sent": False, "key_present": False}
    # call your mail API with `key` here
    return {"sent": True, "key_present": True}
"""),
          S("validate"),
          S("invoke_local", function="send-digest", type="schedule"),
      ],
      final="""`${env:MAIL_API_KEY}` is resolved on the machine that runs pskit, and the value is written into the deploy files. That is why it failed on your laptop, and it is not where a secret should go. For a secret that lives on the host, use an env file instead:

```yaml
provider:
  options:
    env_file: .env.onprem
```

Put a line `MAIL_API_KEY=<your key>` in `.env.onprem` (keep it out of git). `pskit deploy` copies it next to the host as `host.env` and loads it at start. Only its digest is recorded, never the value [docs/resources.md#secrets]. The handler reads it with `ctx.env.get("MAIL_API_KEY")`.

- `pskit validate` (onprem): valid, with one warning: `.env.onprem` does not exist yet, so the host would start without it.
- Local schedule run: `{"sent": false, "key_present": false}`. The key is not here, as expected.

Create `.env.onprem` (in **Code** > **New file**), then deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 131
    B(131, stage="staging", mode="auto", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#fields", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: sessions
provider:
  name: onprem
  region: local
  options:
    port: 8111
functions:
  login:
    handler: app.auth.login
    events:
    - http: POST /login
""",
          "app/__init__.py": "",
          "app/auth.py": FUTURE + """

def login(event, ctx):
    return {"token": "t"}
""",
          "requirements.txt": ""}),
      user="On AWS login used ElastiCache Redis via REDIS_HOST/REDIS_PORT env vars from the CloudFormation stack. Here we run our own Redis at cache-1.example.com:6380, password in SESSION_CACHE_PASSWORD. Wire it the pskit way and let login report the cache it would use.",
      steps=[
          S("get_project"),
          S("search_docs", query="cache resource external connection resource() runtime api",
            docs=[D("docs/resources.md", "runtime-api", end="resources()                      # {\"jobs\": Resource(...), ...} for the current function")]),
          S("propose_plan", steps=["Add resources.session-cache: cache, external, connection {host, port 6380, password_env: SESSION_CACHE_PASSWORD}, functions [login]",
                                   "`login` reads resource(\"session-cache\") instead of REDIS_HOST/REDIS_PORT",
                                   "Validate (onprem, staging), invoke POST /login"]),
          S("set_config", path="resources.session-cache",
            value={"type": "cache", "external": True,
                   "connection": {"host": "cache-1.example.com", "port": 6380,
                                  "password_env": "SESSION_CACHE_PASSWORD"},
                   "functions": ["login"]}),
          S("write_file", path="app/auth.py", content=FUTURE + """from py_serverless_kit import resource


def login(event, ctx):
    cache = resource("session-cache")
    return {
        "token": "t",
        "cache": f'{cache["host"]}:{cache["port"]}',
        "cache_password_set": bool(ctx.env.get(cache["password_env"])),
    }
"""),
          S("validate"),
          S("invoke_local", function="login", method="POST", path="/login", data={"user": "ana"}),
      ],
      final="""Instead of stack outputs in env vars, the cache is a **resource** bound to `login`:

```yaml
resources:
  session-cache:
    type: cache
    external: true
    connection: {host: cache-1.example.com, port: 6380, password_env: SESSION_CACHE_PASSWORD}
    functions: [login]
```

`cache` must be `external: true`; pskit only hands the values over [docs/resources.md#fields]. In code, `resource("session-cache")["host"]` replaces `os.environ["REDIS_HOST"]`, and the same code works on any provider [docs/resources.md#runtime-api].

- validate (onprem, staging): valid.
- `POST /login`: 200, `"cache": "cache-1.example.com:6380"`, `"cache_password_set": false` (the variable is not set here).

Add `redis` to requirements.txt when you connect for real. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 132
    B(132, stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#fields", "docs/resources.md#secrets"],
      project=dict(files={
          "pskit.yml": """service: warehouse
provider:
  name: onprem
  region: local
  options:
    port: 8112
functions:
  sync-orders:
    handler: app.sync.run
    events:
    - schedule: 30 minutes
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """

def run(event, ctx):
    return {"synced": 0}
""",
          "requirements.txt": ""}),
      user="our ERP has a web API at https://erp.example.com/api/v2 and needs an api key (our admin put it in ERP_API_KEY on the server). how do i tell sync-orders about the ERP so it can use it?",
      steps=[
          S("get_project"),
          S("search_docs", query="custom resource external connection url api key",
            docs=[D("docs/resources.md", "fields", end="`database`, `cache` and `custom` must be `external: true`. pskit only passes their connection details along.")]),
          S("propose_plan", steps=["Add resources.erp: custom, external, connection {url: https://erp.example.com/api/v2, api_key_env: ERP_API_KEY}, functions [sync-orders]",
                                   "`run` reads the ERP url and whether the key is set",
                                   "Validate for onprem and run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.erp",
            value={"type": "custom", "external": True,
                   "connection": {"url": "https://erp.example.com/api/v2", "api_key_env": "ERP_API_KEY"},
                   "functions": ["sync-orders"]}),
          S("write_file", path="app/sync.py", content=FUTURE + """from py_serverless_kit import resource


def run(event, ctx):
    erp = resource("erp")
    key = ctx.env.get(erp["api_key_env"], "")
    # call f"{erp['url']}/orders" with the key here
    return {"synced": 0, "erp": erp["url"], "key_present": bool(key)}
"""),
          S("validate"),
          S("invoke_local", function="sync-orders", type="schedule"),
      ],
      final="""I described the ERP as a **resource** of type `custom`, and only `sync-orders` gets it:

```yaml
resources:
  erp:
    type: custom
    external: true
    connection:
      url: https://erp.example.com/api/v2
      api_key_env: ERP_API_KEY
    functions: [sync-orders]
```

`external: true` means pskit never touches the ERP. It only passes these values to the function [docs/resources.md#fields]. The key itself stays on the server. pskit.yml only has the *name* `ERP_API_KEY`, and the handler reads the value with `ctx.env` at run time.

- `pskit validate` (onprem): valid.
- Local run: `{"synced": 0, "erp": "https://erp.example.com/api/v2", "key_present": false}`. The key isn't on this computer, which is expected.

Next step: tell me which ERP endpoint lists orders and I'll write the call. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 133
    B(133, stage="prod", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": """service: inbound
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8113
resources:
  inbound-mail:
    type: smtp
    external: true
    connection: {host: 203.0.113.30, port: 25, domains: inbound.example.com, hostname: mail.inbound.example.com}
functions:
  catch-all:
    handler: app.mail.catch_all
    events:
    - smtp: inbound-mail
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """

def catch_all(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="Our SES receipt-rule Lambda did ses = event['Records'][0]['ses'] and used ses['mail']['commonHeaders']['subject'] and ses['receipt']['recipients']. Can I paste that logic into a new function `ses-compat` on inbound-mail without rewriting it?",
      steps=[
          S("get_project"),
          S("search_docs", query="smtp event SES Records compatible",
            docs=[D("docs/smtp/README.md", "what-the-handler-receives", end="# the raw MIME message")]),
          S("propose_plan", steps=["Write `app/ses_compat.py`: same SES lookups on event.data[\"Records\"][0][\"ses\"]",
                                   "Add function `ses-compat` with `- smtp: {resource: inbound-mail}`",
                                   "Validate (onprem, prod) and run a test mail locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/ses_compat.py", content=FUTURE + """

def handle(event, ctx):
    ses = event.data["Records"][0]["ses"]
    subject = ses["mail"]["commonHeaders"].get("subject")
    recipients = ses["receipt"]["recipients"]
    ctx.logger.info("ses mail", extra={"subject": subject, "recipients": recipients})
    return {"subject": subject, "recipients": recipients}
"""),
          S("set_config", path="functions.ses-compat",
            value={"handler": "app.ses_compat.handle", "events": [{"smtp": {"resource": "inbound-mail"}}]}),
          S("invoke_local", function="ses-compat", type="smtp",
            data={"from": "partner@example.org", "to": ["orders@inbound.example.com"], "subject": "PO 5521",
                  "text": "see attachment"}),
      ],
      final="""Almost unchanged. The SMTP event carries an Amazon SES receipt event in `event.data["Records"]`, so only `event[...]` becomes `event.data[...]` [docs/smtp/README.md#what-the-handler-receives]:

```python
ses = event.data["Records"][0]["ses"]
subject = ses["mail"]["commonHeaders"].get("subject")
recipients = ses["receipt"]["recipients"]
```

Added `ses-compat` on `inbound-mail`, next to `catch-all`.

- `pskit validate` (onprem, prod): valid.
- Local test mail: `{"subject": "PO 5521", "recipients": ["orders@inbound.example.com"]}`.

pskit doesn't scan for spam or check SPF/DKIM, so those SES verdicts are `GRAY`. Don't branch on them. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. Then test with a real mail, or `pskit trigger -f ses-compat`."""),

    # ------------------------------------------------------------------ 134
    B(134, stage="prod", mode="auto", page="Cluster", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises", "docs/cluster.md#load-balancer-one-url-for-the-whole-cluster-optional"],
      project=dict(files={
          "pskit.yml": """service: billing
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8081
functions:
  invoices:
    handler: app.billing.invoices
    events:
    - http: GET /invoices
""",
          "app/__init__.py": "",
          "app/billing.py": FUTURE + """

def invoices(event, ctx):
    return []
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="pskit cluster status prod says:\n\n  workload pskit-shop-prod_web: 3/3 running\n  load balancer lb-1: http://192.0.2.30 -> pskit-shop-prod\n\nput billing on the same cluster, 2 replicas, but its own port 8001 on lb-1 since shop already has 80",
      steps=[
          S("get_project"),
          S("search_docs", query="cluster balancer_port second deployment own port",
            docs=[D("docs/providers.md", "onprem-on-premises", start="**Several servers.**", end="See [cluster.md](cluster.md).")]),
          S("propose_plan", steps=["provider.options.cluster: {name: prod, replicas: 2, balancer_port: 8001}",
                                   "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.cluster", value={"name": "prod", "replicas": 2, "balancer_port": 8001}),
      ],
      final="""Set:

```yaml
provider:
  options:
    host: 0.0.0.0
    port: 8081
    cluster: {name: prod, replicas: 2, balancer_port: 8001}
```

`balancer_port` gives this deployment its own port on the cluster's load balancer, so billing gets `http://192.0.2.30:8001` and shop keeps port 80 [docs/providers.md#onprem-on-premises]. Give billing a `port` that no other deployment on the cluster uses (8081 here).

validate (onprem, prod): valid.

Open 8001 on lb-1 and 8081 from lb-1 to the cluster servers. Deploy: `pskit deploy -s prod` (or **Deploy**, typed confirmation). The output prints the public URL on lb-1."""),

    # ------------------------------------------------------------------ 135
    B(135, stage="prod", mode="ask", page="Load balancers", persona="terse_expert",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it", "docs/load-balancers.md#the-six-algorithms"],
      project=dict(files={
          "pskit.yml": """service: portal
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8115
    cluster: prod
functions:
  app:
    handler: app.portal.page
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/portal.py": FUTURE + """

def page(event, ctx):
    return "portal"
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="portal keeps server-side sessions. put it on lb `edge` under /portal with sticky round robin",
      steps=[
          S("get_project"),
          S("search_docs", query="balancer algorithm sticky_round_robin path",
            docs=[D("docs/load-balancers.md", "create-one-and-put-projects-on-it", start="A project names it", end="sent in `X-Forwarded-Prefix: /shop`. `/shop` redirects to `/shop/`.")]),
          S("propose_plan", steps=["provider.options.balancer: {name: edge, path: portal, algorithm: sticky_round_robin}",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer",
            value={"name": "edge", "path": "portal", "algorithm": "sticky_round_robin"}),
      ],
      final="""Set:

```yaml
provider:
  options:
    cluster: prod
    balancer: {name: edge, path: portal, algorithm: sticky_round_robin}
```

`sticky_round_robin` keeps a client on the same server, so the sessions survive. `/portal/...` reaches the functions without the prefix, and the prefix comes in `X-Forwarded-Prefix: /portal` [docs/load-balancers.md#create-one-and-put-projects-on-it]. The project's own `balancer` wins over any cluster route on `edge`.

validate (onprem, prod): valid.

The route is written on the next deploy: `pskit deploy -s prod` (or **Deploy**, typed confirmation). Check it with `pskit lb status edge`."""),

    # ------------------------------------------------------------------ 136
    B(136, stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/placement.md", "docs/placement.md#how-the-groups-work-together"],
      project=dict(files={
          "pskit.yml": """service: labtools
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8116
functions:
  api:
    handler: app.api.status
    events:
    - http: GET /status
  scanner:
    handler: functions.scanner.handler.main
    events:
    - http: POST /scan
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def status(event, ctx):
    return {"ok": True}
""",
          "functions/__init__.py": "",
          "functions/scanner/__init__.py": "",
          "functions/scanner/handler.py": FUTURE + """

def main(event, ctx):
    return {"scanned": True}
""",
          "functions/scanner/requirements.txt": "",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="$ pskit resources onprem servers list\n  app-1    pskit@192.0.2.10:22\n  app-2    pskit@192.0.2.11:22\n  ...\n\nscanner talks to a USB barcode scanner on MY laptop, so it must run on this machine (port 8117). api goes to app-1.",
      steps=[
          S("get_project"),
          S("search_docs", query="placement local true port group this machine",
            docs=[D("docs/placement.md", "functions-on-several-servers-on-premises", end="# this machine")]),
          S("propose_plan", steps=["provider.options.placement: default `api` on server app-1; group `laptop` {local: true, functions: [scanner], port: 8117}",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement",
            value={"default": "api", "groups": {"api": {"server": "app-1"},
                                                 "laptop": {"local": True, "functions": ["scanner"], "port": 8117}}}),
      ],
      final="""Set:

```yaml
provider:
  options:
    placement:
      default: api
      groups:
        api:    {server: app-1}
        laptop: {local: true, functions: [scanner], port: 8117}
```

`scanner` runs on this machine on port 8117. `api` and anything else you add runs on app-1 [docs/placement.md].

`pskit validate`: valid, with two warnings:
- the `laptop` group runs on this machine, so app-1 reaches it at the group's `advertise`. Tell me your laptop's LAN address and I'll set `advertise: http://<address>:8117`. Port 8117 must also be open on the laptop [docs/placement.md#how-the-groups-work-together].
- app-1 must already have python3.12 on PATH. If it doesn't, I can add `options.deploy.python: bundle`.

Deploy both groups at once: **Deploy** page or `pskit deploy -s dev`. The **Deploy** page's "Where functions run" panel shows this layout."""),

    # ------------------------------------------------------------------ 137
    B(137, stage="staging", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      project=dict(files={
          "pskit.yml": """service: shop-api
provider:
  name: onprem
  region: local
  options:
    port: 8118
functions:
  pricing:
    handler: app.pricing.quote
""",
          "app/__init__.py": "",
          "app/pricing.py": FUTURE + """

def quote(event, ctx):
    data = dict(event.data or {})
    qty = int(data.get("qty", 1))
    unit = 4.5
    return {"sku": data.get("sku"), "qty": qty, "total": round(qty * unit * (0.9 if qty >= 10 else 1.0), 2)}
""",
          "requirements.txt": ""}),
      user="make GET /price?sku=..&qty=.. that ask the pricing function and give back his answer. dont copy the price logic",
      steps=[
          S("get_project"),
          S("search_docs", query="invoke another function onprem in-process",
            docs=[D("docs/handlers.md", "invoke-calling-another-function", end="2. `local` (CLI, tests) and `onprem`: call the handler in-process. `asynchronous=True` still finishes before `invoke()` returns.")]),
          S("propose_plan", steps=["Write `app/price_api.py`: read sku/qty from the query, return invoke(\"pricing\", {...})",
                                   "Add `price-api` on GET /price",
                                   "Validate (onprem, staging), call /price?sku=TEA&qty=12"]),
          S("write_file", path="app/price_api.py", content=FUTURE + """from py_serverless_kit import BadRequest, invoke


def price(event, ctx):
    q = event.http.query
    if not q.get("sku"):
        raise BadRequest("sku is required")
    try:
        qty = int(q.get("qty", "1"))
    except ValueError:
        raise BadRequest("qty must be a number")
    return invoke("pricing", {"sku": q["sku"], "qty": qty})
"""),
          S("set_config", path="functions.price-api",
            value={"handler": "app.price_api.price", "events": [{"http": "GET /price"}]}),
          S("invoke_local", function="price-api", method="GET", path="/price?sku=TEA&qty=12"),
      ],
      final="""Done. `price-api` on `GET /price` calls `pricing` with `invoke()` and returns its answer, so the price logic stays in one place. On premises `invoke()` runs the other handler in-process [docs/handlers.md#invoke-calling-another-function].

- validate (onprem, staging): valid.
- `GET /price?sku=TEA&qty=12`: 200, `{"sku": "TEA", "qty": 12, "total": 48.6}`. 12 items got the 10% discount from `pricing`.
- A missing `sku` or a qty that is not a number gives 400.

Re-test: `pskit invoke -f price-api --method GET --path "/price?sku=TEA&qty=2"`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 138
    B(138, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: backups
provider:
  name: onprem
  region: local
  options:
    port: 8119
functions:
  nightly-backup:
    handler: app.backup.run
""",
          "app/__init__.py": "",
          "app/backup.py": FUTURE + """

def run(event, ctx):
    target = (event.data or {}).get("target", "local")
    ctx.logger.info("backup", extra={"target": target})
    return {"backup": "done", "target": target}
""",
          "requirements.txt": ""}),
      user="please add a daily timer to nightly-backup with target=nas, but don't start it yet, my boss must say ok first",
      steps=[
          S("get_project"),
          S("search_docs", query="schedule enabled false input",
            docs=[D("docs/events.md", "schedule", end="name: morning-report               # optional, used in the resource name")]),
          S("propose_plan", steps=["Add a schedule to `nightly-backup`: rate 1 day, input {target: nas}, enabled: false",
                                   "Validate for onprem and run it once by hand locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.nightly-backup.events",
            value=[{"schedule": {"rate": "1 day", "input": {"target": "nas"}, "enabled": False}}]),
          S("invoke_local", function="nightly-backup", type="schedule"),
      ],
      final="""Added the daily timer, switched off for now:

```yaml
functions:
  nightly-backup:
    handler: app.backup.run
    events:
      - schedule: {rate: 1 day, input: {target: nas}, enabled: false}
```

With `enabled: false` the schedule is in the config but does not run [docs/events.md#schedule].

- `pskit validate` (onprem): valid.
- A manual local run: `{"backup": "done", "target": "nas"}`, so the function works.

When your boss says ok, change it to `enabled: true` (or ask me), then deploy: **Deploy** page or `pskit deploy -s dev`. To run it by hand any time: **Test** page > **▶ Run locally**, or `pskit invoke -f nightly-backup -t schedule`."""),

    # ------------------------------------------------------------------ 139
    B(139, stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resource-guides/onprem/services.md#when-the-functions-move", "docs/resources.md#queue-drivers"],
      project=dict(files={
          "pskit.yml": """service: shipping-labels
provider:
  name: onprem
  region: local
  options:
    port: 8120
functions: {}
""",
          "requirements.txt": ""}),
      user="Another pskit host at http://192.0.2.60:8080 (service `orders`) has a built-in queue `labels`. I want this project to consume it with a function `print-label`, 10 at a time, no broker in between. That host has an admin token, available here as ORDERS_HOST_TOKEN.",
      steps=[
          S("get_project"),
          S("search_docs", query="pskit_host queue driver another host endpoint token",
            docs=[D("docs/resource-guides/onprem/services.md", "when-the-functions-move", start="A queue can also live in **another pskit host's built-in queue**")]),
          S("propose_plan", steps=["Add resources.labels: queue, external, options {driver: pskit_host, endpoint: http://192.0.2.60:8080, queue: labels, token_env: ORDERS_HOST_TOKEN}",
                                   "Write `app/labels.py`; add `print-label` with queue {resource: labels, batch_size: 10}",
                                   "Validate (onprem, staging), invoke with one label job"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.labels",
            value={"type": "queue", "external": True,
                   "options": {"driver": "pskit_host", "endpoint": "http://192.0.2.60:8080", "queue": "labels",
                               "token_env": "ORDERS_HOST_TOKEN"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/labels.py", content=FUTURE + """

def print_label(event, ctx):
    printed = []
    for record in event.records:
        job = record.json(default={}) or {}
        ctx.logger.info("print label", extra={"order": job.get("order_id"), "carrier": job.get("carrier")})
        printed.append(job.get("order_id"))
    return {"printed": printed}
"""),
          S("set_config", path="functions.print-label",
            value={"handler": "app.labels.print_label", "events": [{"queue": {"resource": "labels", "batch_size": 10}}]}),
          S("invoke_local", function="print-label", type="queue", data=[{"order_id": "O-77", "carrier": "DHL"}]),
      ],
      final="""Added:

```yaml
resources:
  labels:
    type: queue
    external: true
    options:
      driver: pskit_host
      endpoint: http://192.0.2.60:8080
      queue: labels
      token_env: ORDERS_HOST_TOKEN
functions:
  print-label:
    handler: app.labels.print_label
    events:
      - queue: {resource: labels, batch_size: 10}
```

Messages are leased through the other host's admin API, so a crash on either side loses nothing [docs/resource-guides/onprem/services.md#when-the-functions-move]. The token is read from `ORDERS_HOST_TOKEN` in this host's environment at start.

- `pskit validate` (onprem, staging): valid.
- Local invoke with one job: `{"printed": ["O-77"]}`.

This host must reach 192.0.2.60:8080. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 140
    B(140, stage="dev", mode="auto", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#storage-drivers"],
      project=dict(files={
          "pskit.yml": """service: docs-intake
provider:
  name: onprem
  region: local
  options:
    port: 8121
resources:
  minio:
    type: storage
    external: true
    options: {driver: minio, endpoint: "http://minio.example.com:9000", bucket: uploads, access_key_env: MINIO_ACCESS_KEY,
      secret_key_env: MINIO_SECRET_KEY}
functions:
  ingest:
    handler: app.intake.ingest
    events:
    - storage: {resource: minio}
""",
          "app/__init__.py": "",
          "app/intake.py": FUTURE + """

def ingest(event, ctx):
    return {"files": [r.key for r in event.records]}
""",
          "requirements.txt": ""}),
      user="same minio also have bucket contracts. new function on contracts bucket only new files, but dont make second minio resource with same keys again",
      steps=[
          S("get_project"),
          S("search_docs", query="one storage service many buckets resource bucket",
            docs=[D("docs/resources.md", "storage-drivers", start="**One storage service, many buckets (on premises).**", end="ingest:   {handler: app.handlers.ingest,   events: [{storage: {resource: minio}}]}                    # uploads")]),
          S("propose_plan", steps=["Add `on_contract` to `app/intake.py`",
                                   "Add `contracts` with storage {resource: minio, bucket: contracts, events: [created]}",
                                   "Validate for onprem, invoke"]),
          S("write_file", path="app/intake.py", content=FUTURE + """

def ingest(event, ctx):
    return {"files": [r.key for r in event.records]}


def on_contract(event, ctx):
    keys = [r.key for r in event.records]
    ctx.logger.info("new contracts", extra={"keys": keys})
    return {"contracts": keys}
"""),
          S("set_config", path="functions.contracts",
            value={"handler": "app.intake.on_contract",
                   "events": [{"storage": {"resource": "minio", "bucket": "contracts", "events": ["created"]}}]}),
          S("invoke_local", function="contracts", type="storage",
            data={"bucket": "contracts", "key": "2026/acme-msa.pdf", "size": 88120, "action": "created"}),
      ],
      final="""Done, with no second resource. On premises one storage resource is the *service* (driver, endpoint, keys), and `bucket` picks any bucket on it [docs/resources.md#storage-drivers]:

```yaml
functions:
  contracts:
    handler: app.intake.on_contract
    events:
      - storage: {resource: minio, bucket: contracts, events: [created]}
```

`ingest` still watches `uploads`, the resource's own bucket.

- `pskit validate` (onprem): valid.
- invoke with a new file: `{"contracts": ["2026/acme-msa.pdf"]}`.

Deploy: **Deploy** page or `pskit deploy -s dev`. Note: this only works on premises. Cloud providers reject `resource` plus a different `bucket`."""),
]
