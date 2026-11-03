"""Category C (fix a validation error), batch 6: on-premises services, saved servers, placement.
Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import json
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


def mods(**modules):
    """app/<module>.py per keyword: one file per function group, so placement groups don't share code."""
    out = {"app/__init__.py": ""}
    for module, names in modules.items():
        out[f"app/{module}.py"] = handlers(*names.split())
    return out


def saved(**servers):
    """The project's saved SSH servers (.pskit/onprem-servers.json, what `pskit resources onprem servers add` writes)."""
    body = {name: {"host": host, "user": "pskit", "port": 22, "sudo": True} for name, host in servers.items()}
    return {".pskit/onprem-servers.json": json.dumps({"servers": body}, indent=2, sort_keys=True) + "\n"}


OPTIONS_BLOCK = D("docs/providers.md", "onprem-on-premises", start="    services:", end="workflow: embedded")
PLACEMENT = D("docs/placement.md", "functions-on-several-servers-on-premises", start="```yaml",
              end="local: {local: true")
PLACEMENT_RULES = D("docs/placement.md", "functions-on-several-servers-on-premises", start="Per group: one of",
                    end="server) and `advertise`")

CONVERSATIONS = [
    # ------------------------------------------------------------------ 101  services key typo
    C(101, provider="onprem", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: mailer
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
    services:
      queues: builtin
functions:
  send:
    handler: app.mail.send
    events:
      - queue: outbox
""", **mods(mail="send")}),
      user="unknown services ['queues'] on onprem validate. fix",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `provider.options.services.queues` to `queue`", "Validate for onprem"]),
          S("set_config", path="provider.options.services.queues", value=None),
          S("set_config", path="provider.options.services.queue", value="builtin"),
      ],
      final="""Typo: the service kinds are singular (`schedule`, `queue`, `storage`, `topic`, `workflow`) [docs/providers.md#onprem-on-premises]. Replaced `queues: builtin` with `queue: builtin`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 102  services.queue: redis -> resource driver
    C(102, provider="onprem", stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises", "docs/resources.md#queue-drivers"],
      project=dict(files={
          "pskit.yml": """service: order-events
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    services:
      queue: redis
functions:
  fulfil:
    handler: app.orders.fulfil
    events:
      - queue: {name: orders, batch_size: 10}
""", **mods(orders="fulfil")}),
      user="Our `orders` queue should live in the Redis we already run at redis://192.0.2.20:6379/0, not in folders. I set `services.queue: redis`, and staging validation now says services.queue.use must be builtin or directory. Where does Redis go then?",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem queue redis driver resource", docs=[
              D("docs/providers.md", "onprem-on-premises", start="A queue, bucket or topic can live in a service you already run",
                end="A queue, bucket or topic can live in a service you already run"),
              D("docs/resources.md", "queue-drivers", start="| `redis` |", end="| `redis` |")]),
          S("propose_plan", steps=["Delete `provider.options.services` (queues go back to builtin)",
                                   "Add `resources.orders: {type: queue, options: {driver: redis, url: redis://192.0.2.20:6379/0}}`",
                                   "Point the event at it: `functions.fulfil.events.0.queue` = `{resource: orders, batch_size: 10}`",
                                   "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.services", value=None),
          S("set_config", path="resources.orders",
            value={"type": "queue", "options": {"driver": "redis", "url": "redis://192.0.2.20:6379/0"}}),
          S("set_config", path="functions.fulfil.events.0.queue", value={"resource": "orders", "batch_size": 10}),
      ],
      final="""`services:` only switches between builtin and plain folders. A queue in a service you already run is a resource with `options.driver` [docs/providers.md#onprem-on-premises].

Changed:

```yaml
resources:
  orders:
    type: queue
    options: {driver: redis, url: "redis://192.0.2.20:6379/0"}
functions:
  fulfil:
    events:
      - queue: {resource: orders, batch_size: 10}
```

`services` was removed. `pskit validate -p onprem -s staging`: valid. Messages are kept in the Redis list `orders` (the key defaults to the native name) [docs/resources.md#queue-drivers]. If that Redis ever needs a password, use `url_env` instead of putting it in the URL."""),

    # ------------------------------------------------------------------ 103  services.workflow native
    C(103, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: claims-flow
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8086
    services:
      workflow: native
functions:
  check:
    handler: app.claims.check
  pay:
    handler: app.claims.pay
workflows:
  claim:
    start_at: Check
    states:
      Check: {type: task, function: check, next: Pay}
      Pay: {type: task, function: pay, end: true}
""", **mods(claims="check pay")}),
      user="On AWS this ran as a Step Functions state machine. I set `services.workflow: native` so it stays native on our servers too, but validation fails. Is there a native engine on-prem?",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem workflow engine embedded", docs=[OPTIONS_BLOCK, D("docs/providers.md", "onprem-on-premises", start="| workflows |", end="| workflows |")]),
          S("propose_plan", steps=["Set `provider.options.services.workflow` to `embedded`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.services.workflow", value="embedded"),
      ],
      final="""No: on-premises there is no Step Functions, so `services.workflow` only supports `embedded`. The workflow runs inside the host and isn't cut off by a function timeout [docs/providers.md#onprem-on-premises].

Set `services.workflow: embedded`. Validate for onprem: valid (`workflow claim: embedded engine`). The same `claim` definition still deploys to Step Functions when you validate and deploy for aws."""),

    # ------------------------------------------------------------------ 104  admin_token number
    C(104, provider="onprem", stage="prod", mode="ask", page="Setup", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises", "docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: hr-portal
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    admin_token: 482910
functions:
  leave:
    handler: app.hr.leave
    events:
      - http: POST /leave
""", **mods(hr="leave")}),
      user="admin_token must be a string error on prod. i put number 482910 for protect the admin endpoints",
      steps=[
          S("get_validation"),
          S("search_docs", query="admin_token", docs=[
              D("docs/providers.md", "onprem-on-premises", start="admin_token:", end="admin_token:")]),
          S("propose_plan", steps=["Set `provider.options.admin_token` to `${env:PSKIT_ADMIN_TOKEN, }` (read from the environment, not written in the file)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.admin_token", value="${env:PSKIT_ADMIN_TOKEN, }"),
      ],
      final="""`admin_token` must be text, and a number isn't [docs/providers.md#onprem-on-premises]. It's also a secret, so it should not be in pskit.yml at all.

Now `admin_token: "${env:PSKIT_ADMIN_TOKEN, }"`. `pskit validate -p onprem -s prod`: valid.

Before you deploy, set `PSKIT_ADMIN_TOKEN` to a long random value (**Setup & credentials** > *Environment variables*). If it's empty, `/__pskit/*` has no token. Clients then send it in the `x-pskit-token` header. Don't use 482910 any more, because it was in the file."""),

    # ------------------------------------------------------------------ 105  env_file: true
    C(105, provider="onprem", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises", "docs/resources.md#on-premises-drivers"],
      project=dict(files={
          "pskit.yml": """service: shop-sync
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
    env_file: true
functions:
  sync:
    handler: app.shop.sync
    events:
      - schedule: 30 minutes
""", **mods(shop="sync")}),
      user="I want my secrets to come from a file, so I turned on env_file: true. Now there is an error that it must be a file path. Which path?",
      steps=[
          S("get_validation"),
          S("search_docs", query="env_file secrets file onprem", docs=[
              D("docs/providers.md", "onprem-on-premises", start="env_file: .env.onprem", end="never written to Terraform state")]),
          S("propose_plan", steps=["Set `provider.options.env_file` to `.env.onprem`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.env_file", value=".env.onprem"),
      ],
      final="""`env_file` isn't an on/off switch: it's the name of the file that holds your `KEY=VALUE` secrets [docs/providers.md#onprem-on-premises].

I set `env_file: .env.onprem`. Validate for onprem: no errors, one WARNING: the file doesn't exist yet, so the host would start without it.

Next: create `.env.onprem` next to pskit.yml with one `KEY=VALUE` line per secret, and keep it out of git. pskit ships it with the host and loads it at start; the values never go into Terraform state."""),

    # ------------------------------------------------------------------ 106  empty host from the form
    C(106, provider="onprem", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: lan-chat
provider:
  name: onprem
  region: local
  options:
    host: ""
    port: 8080
functions:
  messages:
    handler: app.chat.messages
    events:
      - http: GET /messages
""", **mods(chat="messages")}),
      user="I cleared the host box because I didn't know what to type. Now validate says options.host must be a bind address. what is that?",
      steps=[
          S("get_validation"),
          S("ask_user", question="The bind address decides who can reach your functions. Should they answer only on this computer, or for other computers on your network too?",
            options=["Only this computer (127.0.0.1)", "Other computers too (0.0.0.0)"],
            answer="Other computers too (0.0.0.0)"),
          S("propose_plan", steps=["Set `provider.options.host` to `0.0.0.0`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
      ],
      final="""`host` can't be empty: it's the address the host listens on. `0.0.0.0` means "every network card", so other machines can call it [docs/providers.md#onprem-on-premises].

Set `host: 0.0.0.0`. Validate for onprem: valid. Others on your network use `http://<this computer's IP>:8080/messages`; your firewall may need to allow port 8080."""),

    # ------------------------------------------------------------------ 107  deploy.server typo -> ask which
    C(107, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: queue-dash
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy:
      server: app1
      python: bundle
functions:
  depth:
    handler: app.dash.depth
    events:
      - http: GET /depth
""", **mods(dash="depth"), **saved(**{"app-1": "192.0.2.10", "app-2": "192.0.2.11", "db-1": "192.0.2.20"})}),
      user="""Error: no saved SSH server 'app1' (pskit.yml provider.options.deploy.server names it); saved: app-1, app-2, db-1. Did you mean app-1 or app-2? ...

staging is the second app box""",
      steps=[
          S("get_validation"),
          S("ask_user", question="To be sure: is the second app box `app-2` (192.0.2.11)?", options=["app-2", "app-1"],
            answer="app-2"),
          S("propose_plan", steps=["Set `provider.options.deploy.server` to `app-2`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.server", value="app-2"),
      ],
      final="""`app1` isn't a saved server; the saved names have a dash (`app-1`, `app-2`) [docs/providers.md#onprem-on-premises].

Now `deploy.server: app-2`. `pskit validate -p onprem -s staging`: valid. Host, user and SSH login come from the saved server, so nothing else is needed in `deploy`."""),

    # ------------------------------------------------------------------ 108  deploy.server never saved
    C(108, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises", "docs/onprem-network.md#2-saving-a-server-pskit-resources-onprem-servers-add-studio-add-server"],
      project=dict(files={
          "pskit.yml": """service: price-watch
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8090
    deploy:
      server: staging-box
      python: bundle
functions:
  watch:
    handler: app.prices.watch
    events:
      - schedule: 1 hour
""", **mods(prices="watch"), **saved(**{"app-1": "192.0.2.10", "db-1": "192.0.2.20"})}),
      user="validate say no saved SSH server staging-box. my colleague tell me use staging-box",
      steps=[
          S("get_validation"),
          S("ask_user", question="This project has only `app-1` and `db-1` saved; `staging-box` isn't saved here. What should I do?",
            options=["Use app-1 for now", "I'll save staging-box first (then validate again)"],
            answer="Use app-1 for now"),
          S("propose_plan", steps=["Set `provider.options.deploy.server` to `app-1`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.server", value="app-1"),
      ],
      final="""Saved servers belong to the project (`.pskit/onprem-servers.json`), and `staging-box` was saved on your colleague's copy, not here [docs/providers.md#onprem-on-premises].

As you chose, `deploy.server` is `app-1` now. Validate for onprem: valid.

To use `staging-box` later, save it once with `pskit resources onprem servers add` (or **Resources** > On-prem services > Servers > + Add server), then put its name back [docs/onprem-network.md#2-saving-a-server-pskit-resources-onprem-servers-add-studio-add-server]."""),

    # ------------------------------------------------------------------ 109  function in two groups
    C(109, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="terse_expert",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={
          "pskit.yml": """service: media
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    placement:
      default: api
      groups:
        api: {server: app-1, functions: [upload, transcode]}
        gpu: {server: gpu-box, functions: [transcode]}
functions:
  upload:
    handler: app.web.upload
    events:
      - http: POST /videos
  transcode:
    handler: app.video.transcode
""", **mods(web="upload", video="transcode"), **saved(**{"app-1": "192.0.2.10", "gpu-box": "198.51.100.7"})}),
      user="prod: function transcode is in two groups. it belongs on gpu-box",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.api.functions` to `[upload]`",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.api.functions", value=["upload"]),
      ],
      final="""A function runs in exactly one placement group [docs/placement.md#functions-on-several-servers-on-premises]. Removed `transcode` from `api`, so `api: [upload]` and `gpu: [transcode]`. `pskit validate -p onprem -s prod`: no errors (WARNING: the servers need python3.12 on PATH, or add `deploy.python: bundle`). `invoke("transcode", ...)` from `upload` reaches gpu-box over HTTP."""),

    # ------------------------------------------------------------------ 110  placement default not a group
    C(110, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={
          "pskit.yml": """service: school-app
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {python: bundle}
    placement:
      default: web
      groups:
        main: {server: app-1}
        reports: {server: db-1, functions: [grades-report]}
functions:
  timetable:
    handler: app.school.timetable
    events:
      - http: GET /timetable
  grades-report:
    handler: app.reports.grades
    events:
      - schedule: "0 18 * * 5"
""", **mods(school="timetable", reports="grades"), **saved(**{"app-1": "192.0.2.10", "db-1": "192.0.2.20"})}),
      user="I followed the 'Where functions run' guide and now validate says options.placement.default 'web' is not one of the groups. what did I do wrong?",
      steps=[
          S("get_validation"),
          S("search_docs", query="placement default group", docs=[PLACEMENT]),
          S("propose_plan", steps=["Set `provider.options.placement.default` to `main` (your group for everything not listed)",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.default", value="main"),
      ],
      final="""`default` must be the name of one of your groups, and you have `main` and `reports`, not `web` [docs/placement.md#functions-on-several-servers-on-premises].

I set `default: main`. Validate for onprem: valid. `timetable` (and any workflow) runs on app-1, `grades-report` on db-1."""),

    # ------------------------------------------------------------------ 111  server and local in one group
    C(111, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={
          "pskit.yml": """service: lab-tools
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    advertise: http://192.0.2.5:8080
    deploy: {python: bundle}
    placement:
      default: main
      groups:
        main: {local: true}
        gpu: {server: gpu-box, local: true, functions: [train]}
functions:
  status:
    handler: app.lab.status
    events:
      - http: GET /status
  train:
    handler: app.gpu.train
""", **mods(lab="status", gpu="train"), **saved(**{"gpu-box": "198.51.100.7"})}),
      user="placement error 'pick one of server, cluster or local' on gpu group. train must go to gpu-box",
      steps=[
          S("get_validation"),
          S("search_docs", query="placement group server cluster local", docs=[PLACEMENT_RULES]),
          S("propose_plan", steps=["Delete `provider.options.placement.groups.gpu.local` (keep `server: gpu-box`)",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.gpu.local", value=None),
      ],
      final="""Each group runs in one place: `server`, `cluster` or `local: true`, not two of them [docs/placement.md#functions-on-several-servers-on-premises].

Removed `local: true` from `gpu`, so `train` runs on gpu-box. Validate for onprem: valid. `main` stays on this machine and gpu-box calls it at `advertise` (http://192.0.2.5:8080)."""),

    # ------------------------------------------------------------------ 112  group name uppercase
    C(112, provider="onprem", stage="staging", mode="auto", page="Deploy", persona="pasted_error",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={
          "pskit.yml": """service: ticketing
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {python: bundle}
    placement:
      default: web
      groups:
        web: {server: app-1}
        Mail_Workers: {server: app-2, functions: [send-ticket-mail]}
functions:
  tickets:
    handler: app.tickets.create
    events:
      - http: POST /tickets
  send-ticket-mail:
    handler: app.mailer.send
    events:
      - queue: ticket-mail
""", **mods(tickets="create", mailer="send"), **saved(**{"app-1": "192.0.2.10", "app-2": "192.0.2.11"})}),
      user="""Error: options.placement.groups.Mail_Workers: a group name is a lowercase letter, then letters, digits or - (max 21)""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename group `Mail_Workers` to `mail-workers` (same server and functions)",
                                   "Validate for onprem, stage staging"]),
          S("set_config", path="provider.options.placement.groups.Mail_Workers", value=None),
          S("set_config", path="provider.options.placement.groups.mail-workers",
            value={"server": "app-2", "functions": ["send-ticket-mail"]}),
      ],
      final="""Group names become unit and folder names, so they must be lowercase letters, digits and `-` (max 21) [docs/placement.md#functions-on-several-servers-on-premises]. Renamed `Mail_Workers` to `mail-workers`, still `{server: app-2, functions: [send-ticket-mail]}`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 113  group port out of range
    C(113, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={
          "pskit.yml": """service: analytics
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-1}
        crunch: {server: app-1, port: 80800, functions: [aggregate]}
functions:
  events:
    handler: app.api.events
    events:
      - http: POST /events
  aggregate:
    handler: app.crunch.aggregate
    events:
      - schedule: 5 minutes
""", **mods(api="events", crunch="aggregate"), **saved(**{"app-1": "192.0.2.10"})}),
      user="Both groups run on app-1, so I gave `crunch` its own port, meant to be 8081 (I think I typed an extra 0). Validation complains about the port. Please fix it to 8081.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.crunch.port` to 8081", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.crunch.port", value=8081),
      ],
      final="""Yes, `80800` is above the highest port, 65535. A group on a shared server needs its own valid port [docs/placement.md#functions-on-several-servers-on-premises].

Set `crunch.port: 8081`. Validate for onprem: valid. On app-1, `api` listens on 8080 and `crunch` on 8081. Open 8081 between the servers if other groups call it."""),

    # ------------------------------------------------------------------ 114  group key host instead of server
    C(114, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={
          "pskit.yml": """service: face-blur
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-1}
        gpu: {host: gpu-box, functions: [blur]}
functions:
  submit:
    handler: app.api.submit
    events:
      - http: POST /images
  blur:
    handler: app.gpu.blur
""", **mods(api="submit", gpu="blur"), **saved(**{"app-1": "192.0.2.10", "gpu-box": "198.51.100.7"})}),
      user="unknown keys ['host'] in gpu group. gpu-box is the server i saved",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["In `placement.groups.gpu`, replace `host: gpu-box` with `server: gpu-box`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.gpu", value={"server": "gpu-box", "functions": ["blur"]}),
      ],
      final="""A group names a saved server with `server:`. `host` isn't a group key (allowed: server, cluster or local, functions, port, advertise) [docs/placement.md#functions-on-several-servers-on-premises].

Now `gpu: {server: gpu-box, functions: [blur]}`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 115  gateway text value
    C(115, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="aws_migrator",
      sources=["docs/placement.md#deploy-urls-and-load-balancers"],
      project=dict(files={
          "pskit.yml": """service: storefront
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {python: bundle}
    placement:
      gateway: enabled
      default: web
      groups:
        web: {server: app-1}
        search: {server: app-2, functions: [search]}
functions:
  home:
    handler: app.web.home
    events:
      - http: GET /
  search:
    handler: app.search.search
    events:
      - http: GET /search
""", **mods(web="home", search="search"), **saved(**{"app-1": "192.0.2.10", "app-2": "192.0.2.11"})}),
      user="On AWS, one API Gateway URL served every route. Here I want any server to answer /search too, so I set `gateway: enabled` under placement. Prod validation says gateway is true or false.",
      steps=[
          S("get_validation"),
          S("search_docs", query="placement gateway every route", docs=[
              D("docs/placement.md", "deploy-urls-and-load-balancers", start="Each server answers only", end="gateway: true")]),
          S("propose_plan", steps=["Set `provider.options.placement.gateway` to `true`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.gateway", value=True),
      ],
      final="""`gateway` is a yes/no switch, so it takes `true`, not `enabled` [docs/placement.md#deploy-urls-and-load-balancers].

Set `placement.gateway: true`. `pskit validate -p onprem -s prod`: valid. Every group now answers every route and passes the other group's routes on, so app-1 serves `/search` by forwarding to app-2. That's the closest match to one API Gateway URL."""),

    # ------------------------------------------------------------------ 116  placement lists unknown function
    C(116, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-1}
        images: {server: gpu-box, functions: [resize_image]}
functions:
  products:
    handler: app.api.products
    events:
      - http: GET /products
  resize-image:
    handler: app.images.resize
    events:
      - storage: {bucket: product-photos, suffix: .png}
""", **mods(api="products", images="resize"), **saved(**{"app-1": "192.0.2.10", "gpu-box": "198.51.100.7"})}),
      user="""  ERROR: [provider.options.placement] options.placement.groups.images: no function 'resize_image' (functions: products, resize-image)""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.images.functions` to `[resize-image]` (dash, as in `functions:`)",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.images.functions", value=["resize-image"]),
      ],
      final="""The group listed `resize_image` with an underscore, but the function is `resize-image` [docs/placement.md#functions-on-several-servers-on-premises].

Fixed: `images: {server: gpu-box, functions: [resize-image]}`. Validate for onprem: valid. New `.png` files in `product-photos` are handled on gpu-box, and the bucket belongs to that group."""),

    # ------------------------------------------------------------------ 117  two groups same server same port
    C(117, provider="onprem", stage="staging", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={
          "pskit.yml": """service: billing
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-1}
        jobs: {server: app-1, functions: [close-month]}
functions:
  invoices:
    handler: app.api.invoices
    events:
      - http: GET /invoices
  close-month:
    handler: app.jobs.close_month
    events:
      - schedule: "0 3 1 * *"
""", **mods(api="invoices", jobs="close_month"), **saved(**{"app-1": "192.0.2.10"})}),
      user="staging placement: groups api and jobs both on app-1 port 8080. take the suggestion",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.jobs.port` to 8081 (as the error suggests)",
                                   "Validate for onprem, stage staging"]),
          S("set_config", path="provider.options.placement.groups.jobs.port", value=8081),
      ],
      final="""Two groups on one server can't share a port; a group on a shared server needs its own `port` [docs/placement.md#functions-on-several-servers-on-premises]. Set `jobs.port: 8081`, the port the error suggested. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 118  placement server typo
    C(118, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={
          "pskit.yml": """service: speech
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-1}
        asr: {server: gpubox, functions: [transcribe]}
functions:
  upload:
    handler: app.api.upload
    events:
      - http: POST /audio
  transcribe:
    handler: app.asr.transcribe
    timeout: 900
""", **mods(api="upload", asr="transcribe"), **saved(**{"app-1": "192.0.2.10", "gpu-box": "198.51.100.7"})}),
      user="why can't I deploy prod? it says no saved SSH server 'gpubox' but I saved the GPU server last week",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.asr.server` to `gpu-box` (the saved name)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.asr.server", value="gpu-box"),
      ],
      final="""Your GPU server is saved as `gpu-box` (with a dash), but the `asr` group said `gpubox`, so pskit couldn't find it. The message even suggests "Did you mean gpu-box?" [docs/placement.md#functions-on-several-servers-on-premises].

I changed it to `server: gpu-box`. Validate for onprem prod: valid. You can deploy from the **Deploy** page; studio asks for confirmation on `prod`."""),

    # ------------------------------------------------------------------ 119  options typo hosts (warnings)
    C(119, provider="onprem", stage="dev", mode="ask", page="Network map", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: printer-queue
provider:
  name: onprem
  region: local
  options:
    hosts: 0.0.0.0
    port: 8080
    deploy:
      method: ssh
      host: 203.0.113.30
      user: print
      python: bundle
functions:
  jobs:
    handler: app.printer.jobs
    events:
      - http: GET /jobs
""", **mods(printer="jobs")}),
      user="validate green but 2 yellow warning and from my laptop i can't open the server port 8080. i set 0.0.0.0 already",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `provider.options.hosts` to `host` (value `0.0.0.0`)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.hosts", value=None),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
      ],
      final="""The option was written `hosts`, so pskit ignored it (first warning) and the host listened on 127.0.0.1 on the server, reachable only from the server itself (second warning) [docs/providers.md#onprem-on-premises].

Renamed it to `host: 0.0.0.0`. Validate for onprem: valid, both warnings gone. Deploy again so the server picks it up; if 8080 still doesn't open, check the server's firewall."""),

    # ------------------------------------------------------------------ 120  non-default group without a place
    C(120, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={
          "pskit.yml": """service: archive
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-1}
        cold: {functions: [compress]}
functions:
  files:
    handler: app.api.files
    events:
      - http: GET /files
  compress:
    handler: app.cold.compress
    events:
      - schedule: "0 2 * * *"
""", **mods(api="files", cold="compress"), **saved(**{"app-1": "192.0.2.10", "db-1": "192.0.2.20"})}),
      user="I added a `cold` group for the nightly compression job but haven't decided where it runs. Validation fails on it. Can you set it up?",
      steps=[
          S("get_validation"),
          S("ask_user", question="Every group except the default needs a place to run. Saved servers: app-1, db-1. Where should `compress` run?",
            options=["db-1", "app-1 (needs its own port)", "This machine (local: true)"],
            answer="db-1"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.cold.server` to `db-1`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.cold.server", value="db-1"),
      ],
      final="""Only the default group may leave out where it runs. Every other group needs `server`, `cluster` or `local: true` [docs/placement.md#functions-on-several-servers-on-premises].

Set `cold: {server: db-1, functions: [compress]}`, as you chose. Validate for onprem: valid. The nightly `compress` job now runs on db-1, and `files` stays on app-1."""),
]
