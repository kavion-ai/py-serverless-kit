"""Category C (fix a validation error), batch 7: on-premises clusters, load balancers, schedules and names.
Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"
T0 = "2026-10-01T00:00:00+00:00"


def C(n, **kw):
    return dict(id=f"c_fix-{n:04d}", category="c_fix", **kw)


def handlers(*names):
    body = FUTURE
    for name in names:
        body += f"\ndef {name}(event, ctx):\n    return {{\"ok\": True, \"fn\": \"{name}\"}}\n\n"
    return body.rstrip() + "\n"


def app(module, *names):
    return {"app/__init__.py": "", f"app/{module}.py": handlers(*names)}


def cluster(name, orchestrator, **servers):
    """Saved servers plus one saved cluster whose first server is the master (what `pskit cluster create` saves)."""
    names = list(servers)
    saved = {n: {"host": h, "user": "pskit", "port": 22, "sudo": True} for n, h in servers.items()}
    nodes = {n: {"role": "master" if i == 0 else "worker", "node": n, "address": servers[n], "joined_at": T0}
             for i, n in enumerate(names)}
    item = {"orchestrator": orchestrator, "master": names[0], "advertise": servers[names[0]], "nodes": nodes,
            "capacity": {}, "alert": {}, "created_at": T0, "master_serves": orchestrator != "nomad"}
    return {".pskit/onprem-servers.json": json.dumps({"servers": saved}, indent=2, sort_keys=True) + "\n",
            ".pskit/onprem-clusters.json": json.dumps({"clusters": {name: item}}, indent=2) + "\n"}


CLUSTER_OPT = D("docs/cluster.md", "set-up", start="4. **Point the functions", end="memory: 256")
LB_OPT = D("docs/load-balancers.md", "create-one-and-put-projects-on-it", start="A project names it", end="# or: balancer:")
TRIGGERS = D("docs/providers.md", "onprem-on-premises", start="| Trigger |", end="| workflows |")
NAMES = D("docs/providers.md", "onprem-on-premises", start="Omitted services default to `builtin`", end="Omitted services default to `builtin`")

CONVERSATIONS = [
    # ------------------------------------------------------------------ 121  cluster name typo
    C(121, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="pasted_error",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    cluster: production
functions:
  cart:
    handler: app.shop.cart
    events:
      - http: GET /cart
""", **app("shop", "cart"), **cluster("prod", "swarm", **{"app-1": "192.0.2.10", "app-2": "192.0.2.11"})}),
      user="""Error: no cluster 'production' (clusters: prod). Create one: pskit cluster create NAME --master SERVER

I don't want a new cluster, we have one""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.cluster` to `prod` (the cluster you already have)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.cluster", value="prod"),
      ],
      final="""`options.cluster` must be the saved cluster's name, and yours is `prod`, not `production` [docs/cluster.md#set-up].

Set `cluster: prod`. `pskit validate -p onprem -s prod`: valid. No new cluster is needed."""),

    # ------------------------------------------------------------------ 122  replicas 0
    C(122, provider="onprem", stage="dev", mode="ask", page="Cluster", persona="beginner",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": """service: event-signup
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    cluster: {name: lab, replicas: 0}
functions:
  signup:
    handler: app.signup.create
    events:
      - http: POST /signup
""", **app("signup", "create"), **cluster("lab", "swarm", **{"app-1": "192.0.2.10", "app-2": "192.0.2.11"})}),
      user="I wanted it to use nothing when nobody signs up, like serverless, so I set replicas to 0. Validate doesn't let me. Why?",
      steps=[
          S("get_validation"),
          S("search_docs", query="cluster replicas default", docs=[CLUSTER_OPT]),
          S("propose_plan", steps=["Set `provider.options.cluster.replicas` to 1 (the smallest allowed)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.cluster.replicas", value=1),
      ],
      final="""A cluster keeps your functions running all the time; it doesn't scale to zero like a cloud function. `replicas` must be 1 to 500 [docs/cluster.md#set-up].

I set `replicas: 1`, the smallest: one web replica plus the main replica. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 123  cpu in millicores
    C(123, provider="onprem", stage="staging", mode="auto", page="Cluster", persona="aws_migrator",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": """service: geo-lookup
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    cluster: {name: k3s-lab, replicas: 3, cpu: 128}
functions:
  lookup:
    handler: app.geo.lookup
    events:
      - http: GET /geo/{ip}
""", **app("geo", "lookup"), **cluster("k3s-lab", "kubernetes", **{"app-1": "192.0.2.10", "app-2": "192.0.2.11"})}),
      user="Coming from EKS I wrote cpu: 128 meaning 128 millicores per replica. Staging validation says cpu must be 0.05..64. Convert it.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.cluster.cpu` to 0.128 (cores, not millicores)", "Validate for onprem, stage staging"]),
          S("set_config", path="provider.options.cluster.cpu", value=0.128),
      ],
      final="""`cluster.cpu` is in CPU **cores** per replica (default 0.25), so 128 meant 128 cores [docs/cluster.md#set-up]. 128 millicores = `cpu: 0.128`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 124  memory 16 (GB or MB?)
    C(124, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="informal_non_native",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": """service: pdf-render
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    cluster: {name: prod, replicas: 2, memory: 16}
functions:
  render:
    handler: app.pdf.render
    events:
      - http: POST /render
""", **app("pdf", "render"), **cluster("prod", "swarm", **{"app-1": "192.0.2.10", "app-2": "192.0.2.11", "db-1": "192.0.2.20"})}),
      user="cluster memory error in prod, i write 16",
      steps=[
          S("get_validation"),
          S("ask_user", question="`memory` is in MB per replica, from 32 to 262144. How much should each replica reserve?",
            options=["1024 MB (1 GB)", "2048 MB (2 GB)", "16384 MB (16 GB)"],
            answer="1024 MB (1 GB)"),
          S("propose_plan", steps=["Set `provider.options.cluster.memory` to 1024", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.cluster.memory", value=1024),
      ],
      final="""`memory` is MB that each replica reserves, so 16 meant 16 MB, below the minimum of 32 [docs/cluster.md#set-up].

Set `memory: 1024` (1 GB), as you chose. `pskit validate -p onprem -s prod`: valid. With 2 replicas plus the main one, the cluster needs about 3 GB free in total."""),

    # ------------------------------------------------------------------ 125  key replica
    C(125, provider="onprem", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": """service: chat-gw
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    cluster: {name: edge, replica: 4}
functions:
  socket:
    handler: app.chat.socket
    events:
      - http: POST /messages
""", **app("chat", "socket"), **cluster("edge", "nomad", **{"app-1": "192.0.2.10", "app-2": "192.0.2.11"})}),
      user="unknown options.cluster keys ['replica']. 4 web replicas",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace `cluster.replica` with `cluster.replicas: 4`", "Validate for onprem"]),
          S("set_config", path="provider.options.cluster", value={"name": "edge", "replicas": 4}),
      ],
      final="""The key is plural, `replicas` [docs/cluster.md#set-up]. Now `cluster: {name: edge, replicas: 4}`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 126  balancer_port typo
    C(126, provider="onprem", stage="staging", mode="ask", page="Load balancers", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises", "docs/cluster.md#load-balancer-one-url-for-the-whole-cluster-optional"],
      project=dict(files={
          "pskit.yml": """service: booking
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    cluster: {name: prod, replicas: 2, balancer_port: 80880}
functions:
  slots:
    handler: app.booking.slots
    events:
      - http: GET /slots
""", **app("booking", "slots"), **cluster("prod", "swarm", **{"app-1": "192.0.2.10", "app-2": "192.0.2.11"})}),
      user="Staging and prod both run on the `prod` cluster behind the same load balancer, so I gave staging its own `balancer_port`. It was supposed to be 8088. Validation rejects the value. Fix only that.",
      steps=[
          S("get_validation"),
          S("search_docs", query="cluster balancer_port second deployment", docs=[
              D("docs/providers.md", "onprem-on-premises", start="**Several servers.**", end="**Several servers.**")]),
          S("propose_plan", steps=["Set `provider.options.cluster.balancer_port` to 8088", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.cluster.balancer_port", value=8088),
      ],
      final="""`80880` is above 65535, the highest port. `balancer_port` gives a second deployment its own port on the cluster's load balancer [docs/providers.md#onprem-on-premises].

Set `balancer_port: 8088`, nothing else changed. `pskit validate -p onprem -s staging`: valid. Open 8088 on the load balancer server's firewall."""),

    # ------------------------------------------------------------------ 127  cluster mapping without name
    C(127, provider="onprem", stage="dev", mode="ask", page="Cluster", persona="beginner",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": """service: quiz
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    cluster: {replicas: 3}
functions:
  questions:
    handler: app.quiz.questions
    events:
      - http: GET /questions
""", **app("quiz", "questions"), **cluster("classroom", "swarm", **{"app-1": "192.0.2.10", "app-2": "192.0.2.11"})}),
      user="I just want 3 copies of my quiz running. validate says options.cluster needs a name?",
      steps=[
          S("get_validation"),
          S("ask_user", question="pskit must know which cluster runs the 3 copies. This project has one saved cluster, `classroom`. Use it?",
            options=["Yes, use classroom", "No, I'll create another cluster first"],
            answer="Yes, use classroom"),
          S("propose_plan", steps=["Set `provider.options.cluster` to `{name: classroom, replicas: 3}`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.cluster", value={"name": "classroom", "replicas": 3}),
      ],
      final="""`replicas` says how many copies, but pskit also needs the cluster's `name` [docs/cluster.md#set-up].

Now `cluster: {name: classroom, replicas: 3}`. Validate for onprem: valid. Your quiz runs 3 web copies (plus the main one) spread over the cluster's servers."""),

    # ------------------------------------------------------------------ 128  balancer key algo
    C(128, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="terse_expert",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it", "docs/load-balancers.md#the-six-algorithms"],
      project=dict(files={
          "pskit.yml": """service: api-gw
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    advertise: http://192.0.2.10:8080
    balancer: {name: edge, path: api, algo: least_connections}
functions:
  ping:
    handler: app.gw.ping
    events:
      - http: GET /ping
""", **app("gw", "ping")}),
      user="unknown options.balancer keys ['algo'] on prod",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `balancer.algo` to `algorithm` (value `least_connections`)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer", value={"name": "edge", "path": "api", "algorithm": "least_connections"}),
      ],
      final="""The key is `algorithm` (allowed: name, path, algorithm, weights) [docs/load-balancers.md#create-one-and-put-projects-on-it]. Now `balancer: {name: edge, path: api, algorithm: least_connections}`. `pskit validate -p onprem -s prod`: valid. `least_connections` is already the default [docs/load-balancers.md#the-six-algorithms]."""),

    # ------------------------------------------------------------------ 129  weight 500
    C(129, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="informal_non_native",
      sources=["docs/load-balancers.md#the-six-algorithms"],
      project=dict(files={
          "pskit.yml": """service: video-api
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    advertise: http://192.0.2.10:8080
    balancer:
      name: edge
      algorithm: weighted_round_robin
      weights: {app-1: 500, app-2: 100}
functions:
  stream:
    handler: app.video.stream
    events:
      - http: GET /stream/{id}
""", **app("video", "stream")}),
      user="app-1 is big server 5 time stronger than app-2, i put weight 500 and 100. error weight must be 1..100",
      steps=[
          S("get_validation"),
          S("search_docs", query="load balancer weight range", docs=[
              D("docs/load-balancers.md", "the-six-algorithms", start="`weight` (1..100", end="`weight` (1..100")]),
          S("propose_plan", steps=["Set `provider.options.balancer.weights` to `{app-1: 5, app-2: 1}` (same 5:1 ratio)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer.weights", value={"app-1": 5, "app-2": 1}),
      ],
      final="""Each weight must be 1 to 100 [docs/load-balancers.md#the-six-algorithms]. Only the ratio matters, so 500:100 is the same as 5:1.

Now `weights: {app-1: 5, app-2: 1}`. `pskit validate -p onprem -s prod`: valid. app-1 still gets 5 requests for every 1 on app-2."""),

    # ------------------------------------------------------------------ 130  balancer without name
    C(130, provider="onprem", stage="dev", mode="ask", page="Load balancers", persona="beginner",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it"],
      project=dict(files={
          "pskit.yml": """service: shop-front
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    advertise: http://192.0.2.10:8080
    balancer: {path: shop}
functions:
  home:
    handler: app.front.home
    events:
      - http: GET /
""", **app("front", "home")}),
      user="I want my shop under /shop on our load balancer, but validate says it needs the load balancer's name. Where do I find it?",
      steps=[
          S("get_validation"),
          S("search_docs", query="balancer name path project", docs=[LB_OPT]),
          S("ask_user", question="It's the name used when the load balancer was created (`pskit lb create NAME ...`; the **Load balancers** page lists them). What is it called?",
            answer="it says edge-lb on the page"),
          S("propose_plan", steps=["Set `provider.options.balancer` to `{name: edge-lb, path: shop}`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer", value={"name": "edge-lb", "path": "shop"}),
      ],
      final="""`balancer` must name the load balancer to put the route on, and only `path` was set [docs/load-balancers.md#create-one-and-put-projects-on-it].

Now `balancer: {name: edge-lb, path: shop}`. Validate for onprem: valid. After the next deploy the shop is at `/shop/` on edge-lb, and `/shop/` is removed before the request reaches your functions."""),

    # ------------------------------------------------------------------ 131  impossible cron (31 Feb)
    C(131, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: rent-reminder
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
functions:
  remind:
    handler: app.rent.remind
    events:
      - schedule: {cron: "0 9 31 2 *"}
""", **app("rent", "remind")}),
      user="I want the reminder at the end of February. validate says the cron does not match any minute in the next year?",
      steps=[
          S("get_validation"),
          S("ask_user", question="February never has a 31st, so that cron never fires. Cron can't say \"last day of the month\". Which would you like?",
            options=["28 February at 09:00", "1 March at 09:00"],
            answer="28 February at 09:00"),
          S("propose_plan", steps=["Set `functions.remind.events.0.schedule.cron` to `0 9 28 2 *`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.remind.events.0.schedule.cron", value="0 9 28 2 *"),
      ],
      final="""`0 9 31 2 *` asks for 31 February, a date that never exists. The on-premises host checks that a cron fires at least once in the next year [docs/providers.md#onprem-on-premises].

Now `cron: "0 9 28 2 *"`: 09:00 on 28 February every year. Validate for onprem: valid. In leap years that is one day before the real end of February."""),

    # ------------------------------------------------------------------ 132  cron hour 24
    C(132, provider="onprem", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: db-backup
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
functions:
  backup:
    handler: app.backup.run
    timeout: 1800
    events:
      - schedule: {cron: "0 24 * * *", timezone: Asia/Kolkata}
""", **app("backup", "run")}),
      user="backup at midnight i wrote 0 24 * * * . error cron not match any minute",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.backup.events.0.schedule.cron` to `0 0 * * *` (midnight is hour 0)",
                                   "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.backup.events.0.schedule.cron", value="0 0 * * *"),
      ],
      final="""Cron hours go from 0 to 23, so hour 24 never comes [docs/events.md#schedule]. Midnight is hour `0`.

Now `cron: "0 0 * * *"` with `timezone: Asia/Kolkata`. `pskit validate -p onprem -s staging`: valid. The WARNING about the IANA database is only about this machine: `pskit deploy` vendors tzdata, so the deployed host runs it at 00:00 India time."""),

    # ------------------------------------------------------------------ 133  rate "every 5 minutes"
    C(133, provider="onprem", stage="dev", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: queue-monitor
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
functions:
  check-depth:
    handler: app.monitor.check_depth
    events:
      - schedule: every 5 minutes
""", **app("monitor", "check_depth")}),
      user="""Error: pskit.yml is invalid:
  - functions.check-depth.events.0: Value error, cron must be a standard 5-field expression: 'min hour dom month dow'""",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule rate shorthand minutes", docs=[
              D("docs/events.md", "schedule", start="```yaml", end="```")]),
          S("propose_plan", steps=["Set `functions.check-depth.events.0.schedule` to `5 minutes`", "Validate for onprem"]),
          S("set_config", path="functions.check-depth.events.0.schedule", value="5 minutes"),
      ],
      final="""`every 5 minutes` is neither a rate nor a cron; with the extra word pskit tried to read it as a cron. A rate is `<n> minutes|hours|days` [docs/events.md#schedule]. Changed to `- schedule: 5 minutes`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 134  queue name with slash
    C(134, provider="onprem", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: order-intake
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
functions:
  intake:
    handler: app.orders.intake
    events:
      - queue: {name: orders/incoming, batch_size: 5}
""", **app("orders", "intake")}),
      user="In SQS we grouped queues by path-like names, e.g. orders/incoming. On-prem validation says invalid queue name. What's allowed?",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem queue names path segment", docs=[NAMES]),
          S("propose_plan", steps=["Set `functions.intake.events.0.queue.name` to `orders-incoming`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.intake.events.0.queue.name", value="orders-incoming"),
      ],
      final="""On-premises every queue is a folder, so its name must be a single path segment: no slashes, no `..` [docs/providers.md#onprem-on-premises].

Renamed it to `orders-incoming` (`batch_size: 5` kept). Validate for onprem: valid. Producers that post to `/__pskit/queues/<name>` must use the new name too."""),

    # ------------------------------------------------------------------ 135  dead_letter path
    C(135, provider="onprem", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: payments
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    data_dir: /var/pskit/payments
functions:
  settle:
    handler: app.pay.settle
    events:
      - queue: {name: settlements, dead_letter: ../failed/settlements, max_receive: 3}
  audit-failed:
    handler: app.pay.audit
    events:
      - queue: {name: settlements-dlq}
""", **app("pay", "settle", "audit")}),
      user="I wanted failed settlements to land in a separate `failed` folder, so I set `dead_letter: ../failed/settlements`. Prod validation says invalid dead_letter queue name. `audit-failed` should read the dead letters.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.settle.events.0.queue.dead_letter` to `settlements-dlq` (the queue `audit-failed` reads)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.settle.events.0.queue.dead_letter", value="settlements-dlq"),
      ],
      final="""`dead_letter` is a queue **name**, not a path: it must be one path segment, without slashes or `..` [docs/providers.md#onprem-on-premises].

Set `dead_letter: settlements-dlq`, the queue `audit-failed` already consumes. `pskit validate -p onprem -s prod`: valid. After 3 failed receives a message moves there and `audit-failed` gets it [docs/events.md#queue]. Like every builtin queue, it lives under `data_dir`."""),

    # ------------------------------------------------------------------ 136  resource name with slash
    C(136, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#fields", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: notify
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
resources:
  alerts:
    type: queue
    name: team/alerts
functions:
  page-oncall:
    handler: app.notify.page
    events:
      - queue: {resource: alerts}
""", **app("notify", "page")}),
      user="""  ERROR: [resources.alerts.name] invalid queue name 'team/alerts'
  ERROR: [functions.page-oncall] invalid queue name 'team/alerts'

two errors for one thing?""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.alerts.name` to `team-alerts`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.alerts.name", value="team-alerts"),
      ],
      final="""Yes, one cause: the resource's `name` has a slash, and the function's event uses that name too, so both are reported. On-premises a queue name is one path segment [docs/providers.md#onprem-on-premises].

Set `resources.alerts.name: team-alerts`. Validate for onprem: valid, both errors gone. The event still says `resource: alerts`, the key [docs/resources.md#fields]."""),

    # ------------------------------------------------------------------ 137  bucket "uploads/in" -> prefix
    C(137, provider="onprem", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: csv-import
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
functions:
  import-csv:
    handler: app.csv_import.run
    events:
      - storage: {bucket: uploads/in, suffix: .csv}
""", **app("csv_import", "run")}),
      user="i want only files in uploads/in folder trigger. error invalid storage name",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage prefix suffix", docs=[
              D("docs/providers.md", "onprem-on-premises", start="| storage |", end="| storage |")]),
          S("propose_plan", steps=["Set `functions.import-csv.events.0.storage` to `{bucket: uploads, prefix: in/, suffix: .csv}`",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.import-csv.events.0.storage", value={"bucket": "uploads", "prefix": "in/", "suffix": ".csv"}),
      ],
      final="""The bucket name can't contain `/`. The folder inside the bucket goes in `prefix` [docs/providers.md#onprem-on-premises].

Now `storage: {bucket: uploads, prefix: in/, suffix: .csv}`. Validate for onprem: valid. Only `.csv` files under `uploads/in/` start `import-csv`."""),

    # ------------------------------------------------------------------ 138  storage events modified
    C(138, provider="onprem", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises", "docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: contracts
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
functions:
  reindex:
    handler: app.contracts.reindex
    events:
      - storage: {bucket: contracts, suffix: .docx, events: [created, modified]}
""", **app("contracts", "reindex")}),
      user="Legal edits contracts in place, and `reindex` must run when a .docx is changed as well as when it's new. I added `modified` to the storage events and prod validation now fails. How do I catch changes?",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage events created deleted changed file onprem", docs=[
              D("docs/providers.md", "onprem-on-premises", start="| storage |", end="| storage |"),
              D("docs/resources.md", "storage-drivers", start="Every storage driver lists the bucket", end="Every storage driver lists the bucket")]),
          S("propose_plan", steps=["Set `functions.reindex.events.0.storage.events` to `[created]`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.reindex.events.0.storage.events", value=["created"]),
      ],
      final="""Storage events are only `created` and `deleted`; there is no `modified` [docs/providers.md#onprem-on-premises].

Set `events: [created]`. `pskit validate -p onprem -s prod`: valid. A changed file still reaches `reindex`: the host compares each object on every poll, and a new or changed ETag emits `created` [docs/resources.md#storage-drivers]. So check in the handler whether the contract is new or an update, if that matters."""),

    # ------------------------------------------------------------------ 139  topic name wildcard
    C(139, provider="onprem", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises", "docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: audit-log
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
functions:
  record:
    handler: app.audit.record
    events:
      - topic: {name: events/*}
""", **app("audit", "record")}),
      user="With SNS + EventBridge I matched all event topics with a pattern. I tried `events/*` as the topic name here and got 'invalid topic name'. How do I subscribe to everything?",
      steps=[
          S("get_validation"),
          S("search_docs", query="topic filter attributes onprem", docs=[TRIGGERS]),
          S("propose_plan", steps=["Set `functions.record.events.0.topic.name` to `events` (one topic, no pattern)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.record.events.0.topic.name", value="events"),
      ],
      final="""Topic names have no patterns. On-premises a topic is one folder, so the name is a single segment (`/` and `*` paths are rejected) [docs/providers.md#onprem-on-premises].

Now `topic: {name: events}`. Validate for onprem: valid. Publish every event type to `events`; `record` gets them all. Other functions on the same topic can pick only some with `filter`, an exact match on message attributes, then on JSON body fields [docs/events.md#topic]."""),

    # ------------------------------------------------------------------ 140  cluster + placement warning? -> string cluster mapping wrong type
    C(140, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="terse_expert",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": """service: ledger
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    cluster: {name: prod, replicas: 600}
functions:
  post-entry:
    handler: app.ledger.post
    events:
      - http: POST /entries
""", **app("ledger", "post"), **cluster("prod", "swarm", **{"app-1": "192.0.2.10", "app-2": "192.0.2.11", "db-1": "192.0.2.20"})}),
      user="prod: options.cluster.replicas must be an integer 1..500. we need max scale, set the max",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.cluster.replicas` to 500 (the maximum)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.cluster.replicas", value=500),
      ],
      final="""`replicas` is capped at 500 [docs/cluster.md#set-up]. Set `replicas: 500`. `pskit validate -p onprem -s prod`: valid.

Each replica reserves `cpu` 0.25 and `memory` 256 MB by default, so 500 replicas need about 125 cores and 125 GB across the 3 servers. Replicas that don't fit can't be placed; `pskit cluster status prod` (or the **Scaling cluster** page) shows FULL when the servers are over a limit."""),
]
