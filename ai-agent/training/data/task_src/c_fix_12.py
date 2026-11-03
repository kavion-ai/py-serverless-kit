"""Category C (fix a validation error), batch 12: on-premises placement groups and project load balancers.
Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import D, S  # noqa: E402
from _onprem_c import C, FUTURE, cluster, mods, onprem, saved  # noqa: E402

PL = "docs/placement.md"
PA = "functions-on-several-servers-on-premises"
PLACEMENT = D(PL, PA, start="```yaml", end="local: {local: true")
PLACEMENT_RULES = D(PL, PA, start="Per group: one of", end="server) and `advertise`")
ONE_GROUP = D(PL, "how-the-groups-work-together", start="* A built-in queue or bucket", end="groups, give it a driver")
GATEWAY = D(PL, "deploy-urls-and-load-balancers", start="Each server answers only the HTTP routes", end="gateway: true        #")
SHARED = D(PL, "functions-that-share-a-code-file", start="Functions whose handlers sit side by side", end="pskit function split get-item")
LB = "docs/load-balancers.md"
LB_OPT = D(LB, "create-one-and-put-projects-on-it", start="A project names it", end="# or: balancer:")
LB_PREFIX = D(LB, "create-one-and-put-projects-on-it", start="The path prefix is removed", end="sent in `X-Forwarded-Prefix")
ALGOS = D(LB, "the-six-algorithms", start="| Algorithm |", end="| `least_time` |")
BUNDLE = "    deploy: {python: bundle}\n"


def placed(groups, extra=""):
    """provider.options lines: python bundle + a placement block (groups already indented 8 spaces)."""
    return BUNDLE + extra + "    placement:\n      groups:\n" + groups


CONVERSATIONS = [
    # ------------------------------------------------------------------ 221  gateway: always
    C(221, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/placement.md#deploy-urls-and-load-balancers"],
      project=dict(files={"pskit.yml": onprem("media", """functions:
  upload:
    handler: app.web.upload
    events:
      - http: POST /videos
  status:
    handler: app.video.status
    events:
      - http: GET /videos/{id}
""", host="0.0.0.0", extra=BUNDLE + "    placement:\n      gateway: always\n      groups:\n        api: {server: app-1}\n        gpu: {server: gpu-box, functions: [status]}\n"),
          **mods(web="upload", video="status"), **saved("app-1", "gpu-box")}),
      user="Prod: clients only know app-1's address, so every route must be answered there, including the status route that runs on gpu-box. I set placement.gateway: always and validation fails with 'gateway is true or false'.",
      steps=[
          S("get_validation"),
          S("search_docs", query="placement gateway every group answers every route", docs=[GATEWAY]),
          S("propose_plan", steps=["Set `provider.options.placement.gateway` to true", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.gateway", value=True),
      ],
      final="""`gateway` is a plain true/false switch; `true` is exactly what you describe: every group answers every route and passes other groups' routes on [docs/placement.md#deploy-urls-and-load-balancers].

Set `gateway: true`. `pskit validate -p onprem -s prod`: valid. `GET /videos/{id}` on app-1 is now forwarded to gpu-box."""),

    # ------------------------------------------------------------------ 222  group given as a bare server name
    C(222, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={"pskit.yml": onprem("forum", """functions:
  posts:
    handler: app.forum.posts
    events:
      - http: GET /posts
  digest:
    handler: app.mail.digest
    events:
      - schedule: "0 6 * * *"
""", host="0.0.0.0", extra=placed("        web: app-1\n        mail: {server: app-2, functions: [digest]}\n")),
          **mods(forum="posts", mail="digest"), **saved("app-1", "app-2")}),
      user="options.placement.groups.web must be a mapping such as {server: app1, ...}. i only want web on app-1 simple",
      steps=[
          S("get_validation"),
          S("search_docs", query="placement groups server functions", docs=[PLACEMENT]),
          S("propose_plan", steps=["Set `provider.options.placement.groups.web` to `{server: app-1}`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.web", value={"server": "app-1"}),
      ],
      final="""A group is a mapping, so the server needs its key: `web: {server: app-1}` [docs/placement.md#functions-on-several-servers-on-premises].

Changed it. Validate for onprem: valid. `posts` runs on app-1 (the first group is the default), `digest` on app-2."""),

    # ------------------------------------------------------------------ 223  functions written as a mapping
    C(223, provider="onprem", stage="staging", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={"pskit.yml": onprem("geo", """functions:
  lookup:
    handler: app.geo.lookup
    events:
      - http: GET /geo/{ip}
  tiles:
    handler: app.maps.tiles
    events:
      - http: GET /tiles/{path+}
""", host="0.0.0.0", extra=placed("        api: {server: app-1}\n        maps: {server: gpu-box, functions: {tiles: true}}\n")),
          **mods(geo="lookup", maps="tiles"), **saved("app-1", "gpu-box")}),
      user="placement.groups.maps.functions is a list of function names -- staging. fix",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.maps.functions` to `[tiles]`", "Validate for onprem, stage staging"]),
          S("set_config", path="provider.options.placement.groups.maps.functions", value=["tiles"]),
      ],
      final="""`functions` is a list of names, not a mapping [docs/placement.md#functions-on-several-servers-on-premises]. Now `maps: {server: gpu-box, functions: [tiles]}`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 224  advertise without http://
    C(224, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={"pskit.yml": onprem("claims", """functions:
  submit:
    handler: app.claims.submit
    events:
      - http: POST /claims
  score:
    handler: app.risk.score
""", host="0.0.0.0", extra=placed("        api: {server: app-1}\n        risk: {server: db-1, functions: [score], advertise: 198.51.100.20:8080}\n")),
          **mods(claims="submit", risk="score"), **saved("app-1", "db-1")}),
      user="""Error: options.placement.groups.risk.advertise is the URL the other groups call, http://HOST:PORT

the NAT address 198.51.100.20:8080 is right, I checked""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.risk.advertise` to `http://198.51.100.20:8080`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.risk.advertise", value="http://198.51.100.20:8080"),
      ],
      final="""The address is fine; it only needs the scheme, because `advertise` is a URL [docs/placement.md#functions-on-several-servers-on-premises].

Set `advertise: http://198.51.100.20:8080`. `pskit validate -p onprem -s prod`: valid. The api group now calls `score` through that NAT address."""),

    # ------------------------------------------------------------------ 225  cluster: 3 meant replicas
    C(225, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="beginner",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={"pskit.yml": onprem("webshop", """functions:
  checkout:
    handler: app.shop.checkout
    events:
      - http: POST /checkout
  stock:
    handler: app.stock.sync
    events:
      - schedule: 15 minutes
""", host="0.0.0.0", extra=placed("        jobs: {server: db-1, functions: [stock]}\n        web: {cluster: 3, functions: [checkout]}\n", )),
          **mods(shop="checkout", stock="sync"), **cluster("prod", "swarm", "app-1", "app-2"),
          ".pskit/onprem-servers.json": __import__("json").dumps({"servers": {n: {"host": h, "user": "pskit", "port": 22, "sudo": True} for n, h in (("app-1", "192.0.2.10"), ("app-2", "192.0.2.11"), ("db-1", "192.0.2.20"))}}, indent=2, sort_keys=True) + "\n"}),
      user="I want checkout on our prod cluster with 3 copies, so I wrote cluster: 3 in the web group. validate says cluster is a cluster name or {name: prod, replicas: 3}. I guess I wrote it wrong?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.web.cluster` to `{name: prod, replicas: 3}`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.web.cluster", value={"name": "prod", "replicas": 3}),
      ],
      final="""Yes: `cluster` takes the cluster's name, and the number of copies goes next to it as `replicas` [docs/placement.md#functions-on-several-servers-on-premises].

Now `web: {cluster: {name: prod, replicas: 3}, functions: [checkout]}`. `pskit validate -p onprem -s prod`: valid. `stock` stays on db-1."""),

    # ------------------------------------------------------------------ 226  server given as a list
    C(226, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="aws_migrator",
      sources=["docs/placement.md#functions-on-several-servers-on-premises", "docs/cluster.md#set-up"],
      project=dict(files={"pskit.yml": onprem("notify", """functions:
  api:
    handler: app.api.handle
    events:
      - http: ANY /notify
  push:
    handler: app.push.send
    events:
      - queue: pushes
""", host="0.0.0.0", extra=placed("        api: {server: app-1}\n        push: {server: [app-2, db-1], functions: [push]}\n")),
          **mods(api="handle", push="send"), **saved("app-1", "app-2", "db-1")}),
      user="In Lambda the push consumer scaled out by itself. Here I listed two servers for the push group and got 'server is the name of a saved server'.",
      steps=[
          S("get_validation"),
          S("search_docs", query="placement group server cluster several servers", docs=[PLACEMENT_RULES]),
          S("ask_user", question="A group runs on one saved server, or on a scaling cluster for several servers. Which do you want for `push`?",
            options=["One server: app-2", "One server: db-1", "Create a cluster later"], answer="One server: app-2"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.push.server` to `app-2`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.push.server", value="app-2"),
      ],
      final="""A group's `server` is one saved server; for several machines the group takes a `cluster` instead [docs/placement.md#functions-on-several-servers-on-premises].

Set `push: {server: app-2, functions: [push]}`. Validate for onprem: valid. To spread `push` later, create a cluster (`pskit cluster create NAME --master SERVER`) and use `cluster: NAME` for that group."""),

    # ------------------------------------------------------------------ 227  one queue consumed in two groups
    C(227, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/placement.md#how-the-groups-work-together"],
      project=dict(files={"pskit.yml": onprem("orders", """functions:
  api:
    handler: app.api.handle
    events:
      - http: POST /orders
  pack:
    handler: app.jobs.pack
    events:
      - queue: picking
  label:
    handler: app.labels.label
    events:
      - queue: picking
""", host="0.0.0.0", extra=placed("        api: {server: app-1}\n        jobs: {server: app-2, functions: [pack]}\n")),
          **mods(api="handle", jobs="pack", labels="label"), **saved("app-1", "app-2")}),
      user="queue picking triggers functions in groups jobs and api ?? label should go with pack on app-2 i forgot",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.jobs.functions` to `[pack, label]`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.jobs.functions", value=["pack", "label"]),
      ],
      final="""`label` wasn't listed, so it stayed in the default group `api`, and a built-in queue's consumers must all be in one group [docs/placement.md#how-the-groups-work-together].

Now `jobs: [pack, label]`. `pskit validate -p onprem -s staging`: valid. Both consumers of `picking` run on app-2."""),

    # ------------------------------------------------------------------ 228  queue in two groups, rejected move -> redis
    C(228, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/placement.md#how-the-groups-work-together", "docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("alerts", """functions:
  sms:
    handler: app.sms.send
    events:
      - queue: outbox
  email:
    handler: app.email.send
    events:
      - queue: outbox
""", host="0.0.0.0", extra=placed("        mail: {server: app-1}\n        gsm: {server: app-2, functions: [sms]}\n")),
          **mods(sms="send", email="send"), **saved("app-1", "app-2")}),
      user="Prod validate: queue outbox triggers functions in groups gsm and mail. sms must stay on app-2 (the GSM modem is plugged in there) and email on app-1. We already run Redis for this.",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue consumers several groups shared driver", docs=[ONE_GROUP]),
          S("propose_plan", steps=["Move `email` into the gsm group too, so both consumers run on app-2", "Validate for onprem, stage prod"],
            result={"decision": "rejected", "note": "No. Email must stay on app-1. Use our Redis."}),
          S("ask_user", question="Understood, I'll keep both servers and move `outbox` to your Redis. What is the name of the environment variable on the servers that holds the Redis URL?",
            answer="REDIS_URL, it's in the env file on both boxes"),
          S("propose_plan", steps=["Add `resources.outbox` (type queue) with `options: {driver: redis, url_env: REDIS_URL}`",
                                   "Point both events at it: `queue: {resource: outbox}`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.outbox", value={"type": "queue", "options": {"driver": "redis", "url_env": "REDIS_URL"}}),
          S("set_config", path="functions.sms.events.0", value={"queue": {"resource": "outbox"}}),
          S("set_config", path="functions.email.events.0", value={"queue": {"resource": "outbox"}}),
      ],
      final="""A built-in queue lives in one group, so its consumers can't be split; a queue with a shared driver can [docs/placement.md#how-the-groups-work-together].

As you asked, nothing moved. `outbox` is now a resource with `driver: redis, url_env: REDIS_URL`, and `sms` and `email` use `queue: {resource: outbox}`. `pskit validate -p onprem -s prod`: valid. Each host reads `REDIS_URL` from its own environment at start, so the URL is never written to Terraform state [docs/resources.md#queue-drivers]."""),

    # ------------------------------------------------------------------ 229  one bucket in two groups
    C(229, provider="onprem", stage="dev", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/placement.md#how-the-groups-work-together"],
      project=dict(files={"pskit.yml": onprem("scans", """functions:
  ocr:
    handler: app.ocr.read
    events:
      - storage: {bucket: inbox, suffix: .pdf}
  thumb:
    handler: app.thumbs.make
    events:
      - storage: {bucket: inbox, suffix: .png}
""", host="0.0.0.0", extra=placed("        api: {server: app-1}\n        gpu: {server: gpu-box, functions: [ocr]}\n")),
          **mods(ocr="read", thumbs="make"), **saved("app-1", "gpu-box")}),
      user="bucket inbox in groups gpu and api error. put thumb on gpu-box as well",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.placement.groups.gpu.functions` to `[ocr, thumb]`", "Validate for onprem"]),
          S("set_config", path="provider.options.placement.groups.gpu.functions", value=["ocr", "thumb"]),
      ],
      final="""A built-in bucket belongs to one group, so every function it triggers must be there [docs/placement.md#how-the-groups-work-together]. Now `gpu: [ocr, thumb]`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 230  local group without advertise
    C(230, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={"pskit.yml": onprem("lab-report", """functions:
  report:
    handler: app.report.build
    events:
      - http: GET /report
  plot:
    handler: app.plot.draw
""", host="0.0.0.0", extra=placed("        api: {server: app-1}\n        mine: {local: true, functions: [plot]}\n")),
          **mods(report="build", plot="draw"), **saved("app-1")}),
      user="I want to run the plot function on my own PC while report runs on app-1. Validation is valid but warns group mine runs on this machine and other groups reach it at options.advertise. What should I put there?",
      steps=[
          S("get_validation"),
          S("ask_user", question="What is this PC's address on the network app-1 can reach (for example http://192.0.2.5:8080)?",
            answer="my pc is 192.0.2.5"),
          S("propose_plan", steps=["Set `provider.options.advertise` to `http://192.0.2.5:8080`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.advertise", value="http://192.0.2.5:8080"),
      ],
      final="""When `report` on app-1 calls `plot`, it needs your PC's LAN address; `advertise` is that URL [docs/placement.md#functions-on-several-servers-on-premises].

Set `advertise: http://192.0.2.5:8080`. Validate for onprem: valid, no warnings. Allow port 8080 from app-1 in your PC's firewall."""),

    # ------------------------------------------------------------------ 231  group port quoted
    C(231, provider="onprem", stage="staging", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={"pskit.yml": onprem("hr-portal", """functions:
  portal:
    handler: app.portal.page
    events:
      - http: GET /
  payslips:
    handler: app.pay.slips
    events:
      - http: GET /payslips
""", host="0.0.0.0", extra=placed("        web: {server: app-1}\n        pay: {server: app-1, port: \"8081\", functions: [payslips]}\n")),
          **mods(portal="page", pay="slips"), **saved("app-1")}),
      user="""Error: options.placement.groups.pay.port must be a port 1..65535

8081 is a port...""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Write `provider.options.placement.groups.pay.port` as the number 8081 (no quotes)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.pay.port", value=8081),
      ],
      final="""It is, but it was written as the string `"8081"`; a group's `port` must be a YAML number [docs/placement.md#functions-on-several-servers-on-premises].

Now `port: 8081`. `pskit validate -p onprem -s staging`: valid. Both groups share app-1, on 8080 and 8081."""),

    # ------------------------------------------------------------------ 232  workflow orchestrator listed in a group
    C(232, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/placement.md#how-the-groups-work-together"],
      project=dict(files={"pskit.yml": onprem("kyc", """functions:
  start:
    handler: app.api.start
    events:
      - http: POST /kyc
  verify:
    handler: app.ml.verify
workflows:
  check:
    start_at: Verify
    states:
      Verify: {type: task, function: verify}
""", host="0.0.0.0", extra=placed("        api: {server: app-1}\n        ml: {server: gpu-box, functions: [verify, check-orchestrator]}\n")),
          **mods(api="start", ml="verify"), **saved("app-1", "gpu-box")}),
      user="I put check-orchestrator in the ml group so the whole KYC workflow runs on gpu-box next to the model. Prod validation: it orchestrates a workflow; workflows run on the default group. I need the heavy step on the GPU, that's all.",
      steps=[
          S("get_validation"),
          S("search_docs", query="placement workflow default group steps run", docs=[
              D(PL, "how-the-groups-work-together", start="| a **workflow** step", end="| start a workflow on any group")]),
          S("propose_plan", steps=["Set `provider.options.placement.groups.ml.functions` to `[verify]` (drop the orchestrator)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.ml.functions", value=["verify"]),
      ],
      final="""The workflow itself always runs on the default group, but each step runs where its function is, so listing `verify` is enough [docs/placement.md#how-the-groups-work-together].

Removed `check-orchestrator` from `ml`. `pskit validate -p onprem -s prod`: valid. The `Verify` step runs on gpu-box; the execution history stays on app-1."""),

    # ------------------------------------------------------------------ 233  balancer named twice
    C(233, provider="onprem", stage="prod", mode="auto", page="Load balancers", persona="terse_expert",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it"],
      project=dict(files={"pskit.yml": onprem("storefront", """functions:
  home:
    handler: app.store.home
    events:
      - http: GET /
""", host="0.0.0.0", extra="    advertise: http://192.0.2.10:8080\n    balancer: [edge, {name: edge, path: shop}]\n"), **mods(store="home")}),
      user="balancer names one load balancer more than once. want only /shop on edge",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.balancer` to `{name: edge, path: shop}`", "Validate for onprem, stage prod"]),
          S("set_config", path="provider.options.balancer", value={"name": "edge", "path": "shop"}),
      ],
      final="""A project gets one route per load balancer; `edge` alone would have added `/storefront/` [docs/load-balancers.md#create-one-and-put-projects-on-it]. Now `balancer: {name: edge, path: shop}`. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 234  weights as a list
    C(234, provider="onprem", stage="staging", mode="ask", page="Load balancers", persona="informal_non_native",
      sources=["docs/load-balancers.md#the-six-algorithms"],
      project=dict(files={"pskit.yml": onprem("search", """functions:
  query:
    handler: app.search.query
    events:
      - http: GET /q
""", host="0.0.0.0", extra="    advertise: http://192.0.2.10:8080\n    balancer: {name: edge, algorithm: weighted_round_robin, weights: [app-1, app-2]}\n"),
          **mods(search="query"), **saved("app-1", "app-2")}),
      user="weights maps a saved server name to weight 1..100. app-1 is big machine, app-2 small, maybe 3 to 1",
      steps=[
          S("get_validation"),
          S("search_docs", query="weighted round robin weight per server", docs=[
              D(LB, "the-six-algorithms", start="`weight` (1..100", end="`weight` (1..100")]),
          S("propose_plan", steps=["Set `provider.options.balancer.weights` to `{app-1: 3, app-2: 1}`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer.weights", value={"app-1": 3, "app-2": 1}),
      ],
      final="""`weights` is a mapping from server name to a number 1..100, not a list [docs/load-balancers.md#the-six-algorithms].

Now `weights: {app-1: 3, app-2: 1}`: app-1 gets three requests for every one on app-2. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 235  route path with capitals and a space
    C(235, provider="onprem", stage="dev", mode="ask", page="Load balancers", persona="beginner",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it"],
      project=dict(files={"pskit.yml": onprem("shop-api", """functions:
  items:
    handler: app.shop.items
    events:
      - http: GET /items
""", host="0.0.0.0", extra="    advertise: http://192.0.2.10:8080\n    balancer: {name: edge, path: Shop API}\n"), **mods(shop="items")}),
      user="I want people to open http://edge/Shop API/items. Validation says route path 'Shop API': lowercase letters, digits... Can't I have a nice name?",
      steps=[
          S("get_validation"),
          S("search_docs", query="balancer path prefix route", docs=[LB_PREFIX]),
          S("propose_plan", steps=["Set `provider.options.balancer.path` to `shop-api`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer.path", value="shop-api"),
      ],
      final="""The path becomes part of a URL, so it must be lowercase letters, digits, `.`, `_` or `-`; spaces would have to be encoded as `%20` [docs/load-balancers.md#create-one-and-put-projects-on-it].

Set `path: shop-api`, so the address is `http://edge/shop-api/items`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 236  route path __pskit
    C(236, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="detailed_spec",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it"],
      project=dict(files={"pskit.yml": onprem("ops-console", """functions:
  status:
    handler: app.ops.status
    events:
      - http: GET /status
""", host="0.0.0.0", extra="    advertise: http://192.0.2.10:8080\n    balancer: {name: edge, path: __pskit}\n"), **mods(ops="status")}),
      user="I wanted our internal ops console under /__pskit/ on the edge balancer so it looks like a system page. Prod validation rejects it. Which path should we use instead?",
      steps=[
          S("get_validation"),
          S("ask_user", question="`__pskit` is reserved for the host's own endpoints. Which path do you want instead?",
            options=["ops", "ops-console", "internal"], answer="ops"),
          S("propose_plan", steps=["Set `provider.options.balancer.path` to `ops`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer.path", value="ops"),
      ],
      final="""`__pskit` is reserved: the hosts serve their health, logs and admin endpoints under `/__pskit/`, and a route path must start with a letter or digit [docs/load-balancers.md#create-one-and-put-projects-on-it].

Set `path: ops`; the console is at `http://edge/ops/status`. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 237  algorithm random
    C(237, provider="onprem", stage="staging", mode="ask", page="Load balancers", persona="aws_migrator",
      sources=["docs/load-balancers.md#the-six-algorithms"],
      project=dict(files={"pskit.yml": onprem("ads", """functions:
  serve:
    handler: app.ads.serve
    events:
      - http: GET /ad
""", host="0.0.0.0", extra="    advertise: http://192.0.2.10:8080\n    balancer: {name: edge, algorithm: random}\n"), **mods(ads="serve")}),
      user="ALB just spreads requests, so I put algorithm: random. Staging validation: unknown load balancing algorithm 'random'. What's closest?",
      steps=[
          S("get_validation"),
          S("search_docs", query="load balancing algorithms list", docs=[ALGOS]),
          S("ask_user", question="Closest choices: `round_robin` (each server in turn, like ALB's default) or `least_connections` (fewest requests in progress, pskit's default). Which one?",
            options=["round_robin", "least_connections"], answer="round_robin"),
          S("propose_plan", steps=["Set `provider.options.balancer.algorithm` to `round_robin`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer.algorithm", value="round_robin"),
      ],
      final="""pskit's load balancers have six algorithms and no `random` [docs/load-balancers.md#the-six-algorithms].

Set `algorithm: round_robin`: each server in turn, like an ALB's default. `pskit validate -p onprem -s staging`: valid. `pskit lb algorithms` prints the trade-offs of all six."""),

    # ------------------------------------------------------------------ 238  shared code file across groups (warning)
    C(238, provider="onprem", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/placement.md#functions-that-share-a-code-file"],
      project=dict(files={"pskit.yml": onprem("library", """functions:
  books:
    handler: app.handlers.books
    events:
      - http: GET /books
  overdue:
    handler: app.handlers.overdue
    events:
      - schedule: "0 8 * * *"
""", host="0.0.0.0", extra=placed("        web: {server: app-1}\n        jobs: {server: db-1, functions: [overdue]}\n")),
          **mods(handlers="books overdue"), **saved("app-1", "db-1")}),
      user="Validation passes but warns that books (web) and overdue (jobs) share app/handlers.py. Fix it properly: overdue should get its own module, keep books where it is.",
      steps=[
          S("get_validation"),
          S("search_docs", query="functions share a code file split", docs=[SHARED]),
          S("read_file", path="app/handlers.py"),
          S("propose_plan", steps=["Write `app/overdue.py` with the `overdue` handler",
                                   "Set `functions.overdue.handler` to `app.overdue.overdue`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/overdue.py", content=FUTURE + "\ndef overdue(event, ctx):\n    return {\"ok\": True, \"fn\": \"overdue\"}\n"),
          S("set_config", path="functions.overdue.handler", value="app.overdue.overdue"),
      ],
      final="""Handlers side by side in one file are shared code: each server would get a copy of `app/handlers.py`, and validation warns when they are in different groups [docs/placement.md#functions-that-share-a-code-file].

`overdue` now lives in `app/overdue.py` (handler `app.overdue.overdue`); `books` is unchanged. Validate for onprem: valid, no warnings. You can delete the old `overdue` from `app/handlers.py`. Next time `pskit function split overdue` (studio: **Functions** > Own folder) does this for you."""),

    # ------------------------------------------------------------------ 239  group name too long
    C(239, provider="onprem", stage="staging", mode="auto", page="Deploy", persona="informal_non_native",
      sources=["docs/placement.md#functions-on-several-servers-on-premises"],
      project=dict(files={"pskit.yml": onprem("bi", """functions:
  dash:
    handler: app.dash.page
    events:
      - http: GET /dash
  etl:
    handler: app.etl.run
    events:
      - schedule: "0 1 * * *"
""", host="0.0.0.0", extra=placed("        web: {server: app-1}\n        reporting-and-analytics-jobs: {server: db-1, functions: [etl]}\n")),
          **mods(dash="page", etl="run"), **saved("app-1", "db-1")}),
      user="group name error 'a group name is a lowercase letter, then letters, digits or - (max 21)'. it is lowercase!",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename the group `reporting-and-analytics-jobs` to `analytics` (max 21 chars)", "Validate for onprem, stage staging"]),
          S("set_config", path="provider.options.placement.groups.reporting-and-analytics-jobs", value=None),
          S("set_config", path="provider.options.placement.groups.analytics", value={"server": "db-1", "functions": ["etl"]}),
      ],
      final="""It's lowercase, but 28 characters; a group name may have at most 21 because it becomes part of unit and folder names [docs/placement.md#functions-on-several-servers-on-premises]. Renamed it to `analytics` (same server and functions). `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 240  balancer name with capitals
    C(240, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="pasted_error",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it"],
      project=dict(files={"pskit.yml": onprem("tickets", """functions:
  list:
    handler: app.tickets.listing
    events:
      - http: GET /tickets
""", host="0.0.0.0", extra="    advertise: http://192.0.2.11:8080\n    balancer: Edge-LB\n"), **mods(tickets="listing")}),
      user="""  ERROR: [provider.options.balancer] options.balancer needs the load balancer's name: balancer: NAME or {name: NAME, path: ...}

I did give the name, it's Edge-LB in the Load balancers page""",
      steps=[
          S("get_validation"),
          S("ask_user", question="Load balancer names are lowercase. On the Load balancers page, is the exact name `edge-lb`?",
            options=["edge-lb", "something else"], answer="yes edge-lb, it's just shown like that in my notes"),
          S("propose_plan", steps=["Set `provider.options.balancer` to `edge-lb`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer", value="edge-lb"),
      ],
      final="""`Edge-LB` isn't a valid load balancer name because of the capitals, so pskit didn't accept it as a name [docs/load-balancers.md#create-one-and-put-projects-on-it].

Set `balancer: edge-lb`. `pskit validate -p onprem -s prod`: valid. The next deploy adds the route `/tickets/` on it."""),
]
