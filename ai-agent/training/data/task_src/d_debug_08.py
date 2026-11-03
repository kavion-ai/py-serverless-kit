"""Category D (fix a handler bug), batch 8. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

ONPREM = """provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: {port}
"""

GCP = """provider:
  name: gcp
  region: {region}
  options:
    project: ${{env:GOOGLE_CLOUD_PROJECT, demo-project}}
"""


def B(n, **kw):
    return dict(id=f"d_debug-{n:04d}", category="d_debug", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 141 onprem http, form post parsed as JSON
    B(141, provider="onprem", stage="prod", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: contact\n" + ONPREM.format(port=8231) + """functions:
  contact-form:
    handler: app.contact.submit
    events:
      - http: POST /contact
""",
          "app/__init__.py": "",
          "app/contact.py": FUTURE + """
def submit(event, ctx):
    data = event.http.json()
    return {"thanks": data.get("name", "friend")}
""",
          "requirements.txt": ""}),
      user="my HTML contact form (a normal <form method=post>) always gets 400 'Request body is not valid JSON'. The JS fetch version sends JSON and works. I need both to work.",
      steps=[
          S("read_file", path="app/contact.py"),
          S("invoke_local", function="contact-form", method="POST", path="/contact", data="name=Ana&msg=hello"),
          S("search_docs", query="parse form body urlencoded",
            docs=[D("docs/handlers.md", "httprequest", start="| `json(default=...)` |")]),
          S("propose_plan", steps=["Try JSON with `json(default=None)`; when it isn't JSON, read the form with `event.http.form()`",
                                   "POST a form body locally and validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/contact.py", content=FUTURE + """
def submit(event, ctx):
    data = event.http.json(default=None)
    if not isinstance(data, dict):
        data = event.http.form()
    return {"thanks": data.get("name", "friend")}
"""),
          S("invoke_local", function="contact-form", method="POST", path="/contact", data="name=Ana&msg=hello"),
          S("validate"),
      ],
      final="""A normal HTML form sends `name=Ana&msg=hello` (form encoding), not JSON. `json()` then raises `BadRequest`, which is the 400 you saw [docs/handlers.md#httprequest]. The handler now tries JSON first with `json(default=None)`, and if the body isn't a JSON object, reads it with `form()`.

- POST /contact `name=Ana&msg=hello`: 200, `{"thanks": "Ana"}`.
- validate (onprem, prod): valid. JSON requests from fetch work as before."""),

    # ------------------------------------------------------------------ 142 aws http, base64-decoding a decoded body
    B(142, provider="aws", stage="staging", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: echo
provider:
  name: aws
  region: us-east-2
functions:
  echo:
    handler: app.echo.echo
    events:
      - http: POST /echo
""",
          "app/__init__.py": "",
          "app/echo.py": FUTURE + """import base64


def echo(event, ctx):
    raw = base64.b64decode(event.http.body)
    return {"length": len(raw), "text": raw.decode("utf-8")}
""",
          "requirements.txt": ""}),
      user="With API Gateway I always did base64.b64decode(event['body']) when isBase64Encoded was true. Kept that in pskit and now POST /echo with 'hello world' fails: binascii.Error: Incorrect padding. Should I check a flag?",
      steps=[
          S("read_file", path="app/echo.py"),
          S("invoke_local", function="echo", method="POST", path="/echo", data="hello world"),
          S("search_docs", query="body bytes base64 decoded",
            docs=[D("docs/handlers.md", "httprequest", start="| `body` |", end="| `text(encoding=\"utf-8\")` |")]),
          S("propose_plan", steps=["Drop the base64 step: `event.http.body` is already decoded bytes",
                                   "POST 'hello world' locally and validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/echo.py", content=FUTURE + """
def echo(event, ctx):
    raw = event.http.body
    return {"length": len(raw), "text": raw.decode("utf-8")}
"""),
          S("invoke_local", function="echo", method="POST", path="/echo", data="hello world"),
          S("validate"),
      ],
      final="""No flag needed. `event.http.body` is `bytes` with **base64 already decoded** [docs/handlers.md#httprequest]; the AWS adapter handles `isBase64Encoded` for you. Decoding again broke the text. The handler now uses `event.http.body` directly (`event.http.text()` would give the str).

- POST /echo "hello world": 200, `{"length": 11, "text": "hello world"}`.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 143 gcp topic, event.type compared with "pubsub"
    B(143, provider="gcp", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": "service: audit\n" + GCP.format(region="us-east4") + """functions:
  audit-log:
    handler: app.audit.handle
    events:
      - topic: audit-events
      - http: POST /audit
""",
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """
def handle(event, ctx):
    if event.type == "pubsub":
        entries = [r.json() for r in event.records]
    elif event.is_http:
        entries = [event.http.json()]
    else:
        entries = []
    return {"logged": len(entries)}
""",
          "requirements.txt": ""}),
      user="audit-log logs 0 entries for pubsub messages, http path fine",
      steps=[
          S("read_file", path="app/audit.py"),
          S("invoke_local", function="audit-log", type="topic", data=[{"user": "u1", "action": "login"}]),
          S("propose_plan", steps=["Check `event.type == EventType.TOPIC` (\"topic\"), not \"pubsub\""]),
          S("write_file", path="app/audit.py", content=FUTURE + """from py_serverless_kit import EventType


def handle(event, ctx):
    if event.type == EventType.TOPIC:
        entries = [r.json() for r in event.records]
    elif event.is_http:
        entries = [event.http.json()]
    else:
        entries = []
    return {"logged": len(entries)}
"""),
          S("invoke_local", function="audit-log", type="topic", data=[{"user": "u1", "action": "login"}]),
          S("validate"),
      ],
      final="""`event.type` is portable: Pub/Sub messages arrive as `"topic"`, never `"pubsub"` [docs/handlers.md#event]. Now it compares with `EventType.TOPIC`.

- topic invoke: `{"logged": 1}` (before: 0).
- validate (gcp): valid. `event.is_batch` would also cover queue and storage if you add them later."""),

    # ------------------------------------------------------------------ 144 onprem queue, int(record.id)
    B(144, provider="onprem", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: print-queue\n" + ONPREM.format(port=8232) + """functions:
  print-job:
    handler: app.printer.handle
    events:
      - queue: print-jobs
""",
          "app/__init__.py": "",
          "app/printer.py": FUTURE + """
def handle(event, ctx):
    jobs = []
    for record in event.records:
        seq = int(record.id)
        jobs.append({"seq": seq, "doc": record.json()["doc"]})
    jobs.sort(key=lambda j: j["seq"])
    return {"printed": [j["doc"] for j in jobs]}
""",
          "requirements.txt": ""}),
      user="The print worker sorts jobs by their sequence number before printing. In tests it fails with ValueError: invalid literal for int() with base 10: 'local-0'. The producer puts a 'seq' field in every message. Print order must follow that seq. Test with seq 2 then seq 1.",
      steps=[
          S("read_file", path="app/printer.py"),
          S("invoke_local", function="print-job", type="queue", data=[{"seq": 2, "doc": "b.pdf"}, {"seq": 1, "doc": "a.pdf"}]),
          S("search_docs", query="record id message id",
            docs=[D("docs/handlers.md", "record")]),
          S("propose_plan", steps=["Sort by the message's own `seq` field; `record.id` is an opaque message id, not a number",
                                   "Invoke with seq 2 then seq 1; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/printer.py", content=FUTURE + """
def handle(event, ctx):
    jobs = [record.json() for record in event.records]
    jobs.sort(key=lambda j: j["seq"])
    return {"printed": [j["doc"] for j in jobs]}
"""),
          S("invoke_local", function="print-job", type="queue", data=[{"seq": 2, "doc": "b.pdf"}, {"seq": 1, "doc": "a.pdf"}]),
          S("validate"),
      ],
      final="""`record.id` is the queue's **message id**, used by `BatchResult` [docs/handlers.md#record]. It is a string chosen by the platform (`local-0` in tests), not your sequence. The handler now sorts by the `seq` field from the message body.

- invoke (seq 2, then seq 1): `{"printed": ["a.pdf", "b.pdf"]}`.
- validate (onprem): valid.

The sort only orders the messages within one batch. A global order needs the producer and the consumer to agree, for example on one message at a time with `batch_size: 1`."""),

    # ------------------------------------------------------------------ 145 azure http, sorted(key="name")
    B(145, provider="azure", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: team-dir
provider:
  name: azure
  region: southeastasia
functions:
  members:
    handler: app.team.members
    events:
      - http: GET /members
""",
          "app/__init__.py": "",
          "app/team.py": FUTURE + """MEMBERS = [{"name": "Zoe", "role": "qa"}, {"name": "Arun", "role": "dev"}, {"name": "Mei", "role": "pm"}]


def members(event, ctx):
    return {"members": sorted(MEMBERS, key="name")}
""",
          "requirements.txt": ""}),
      user="members list must be sort by name, but i get 'str' object is not callable",
      steps=[
          S("read_file", path="app/team.py"),
          S("invoke_local", function="members", path="/members"),
          S("propose_plan", steps=["Give `sorted` a function as key: `key=lambda m: m[\"name\"]`",
                                   "GET /members locally and validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/team.py", content=FUTURE + """MEMBERS = [{"name": "Zoe", "role": "qa"}, {"name": "Arun", "role": "dev"}, {"name": "Mei", "role": "pm"}]


def members(event, ctx):
    return {"members": sorted(MEMBERS, key=lambda m: m["name"])}
"""),
          S("invoke_local", function="members", path="/members"),
          S("validate"),
      ],
      final="""`key=` must be a **function** that gets one item and returns the value to sort by. `"name"` is only a string, so Python tried to call it. Now: `key=lambda m: m["name"]`.

- GET /members: 200, sorted Arun, Mei, Zoe.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 146 onprem schedule, json.load on a dict
    B(146, provider="onprem", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: reminders\n" + ONPREM.format(port=8233) + """functions:
  remind:
    handler: app.remind.run
    events:
      - schedule:
          cron: "0 9 * * 1-5"
          input: {channel: ops, text: Stand-up in 15 minutes}
""",
          "app/__init__.py": "",
          "app/remind.py": FUTURE + """import json


def run(event, ctx):
    cfg = json.load(event.data)
    ctx.logger.info("reminder", extra={"channel": cfg["channel"]})
    return {"sent": cfg["text"]}
""",
          "requirements.txt": ""}),
      user="I want to read the input of my schedule. I do json.load(event.data) but it says 'dict' object has no attribute 'read'. Do I need to open a file?",
      steps=[
          S("read_file", path="app/remind.py"),
          S("invoke_local", function="remind", type="schedule"),
          S("search_docs", query="schedule input event data",
            docs=[D("docs/events.md", "schedule", end="The handler gets `event.type == \"schedule\"`")]),
          S("propose_plan", steps=["Use `event.data` directly (it is already a dict); remove the json import",
                                   "Run remind as a schedule event and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/remind.py", content=FUTURE + """
def run(event, ctx):
    cfg = event.data
    ctx.logger.info("reminder", extra={"channel": cfg["channel"]})
    return {"sent": cfg["text"]}
"""),
          S("invoke_local", function="remind", type="schedule"),
          S("validate"),
      ],
      final="""No file needed. pskit already gives you the schedule `input` as a Python dict in `event.data`. `json.load()` is for reading a file, so it looked for a `.read()` method. The handler now uses `event.data` directly.

- schedule run: logs "reminder" (channel ops), returns `{"sent": "Stand-up in 15 minutes"}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 147 aws http, json(default=None).get
    B(147, provider="aws", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: feedback
provider:
  name: aws
  region: eu-south-1
functions:
  rate:
    handler: app.rate.rate
    events:
      - http: POST /rate
""",
          "app/__init__.py": "",
          "app/rate.py": FUTURE + """
def rate(event, ctx):
    data = event.http.json(default=None)
    stars = int(data.get("stars", 5))
    return {"stars": stars}
""",
          "requirements.txt": ""}),
      user="""AttributeError: 'NoneType' object has no attribute 'get'
POST /rate with an empty body. I wanted empty = 5 stars""",
      steps=[
          S("read_file", path="app/rate.py"),
          S("invoke_local", function="rate", method="POST", path="/rate"),
          S("propose_plan", steps=["Use `json(default={})` so an empty body becomes an empty dict",
                                   "POST /rate with no body locally; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/rate.py", content=FUTURE + """
def rate(event, ctx):
    data = event.http.json(default={})
    stars = int(data.get("stars", 5))
    return {"stars": stars}
"""),
          S("invoke_local", function="rate", method="POST", path="/rate"),
          S("validate"),
      ],
      final="""`json(default=None)` returns `None` for an empty body, and `None` has no `.get()` [docs/handlers.md#httprequest]. With `default={}` an empty body becomes `{}`, and `.get("stars", 5)` gives 5.

- POST /rate, empty body: 200, `{"stars": 5}`.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 148 gcp http, uuid4 not imported
    B(148, provider="gcp", stage="prod", mode="auto", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: uploads-api\n" + GCP.format(region="us-central1") + """functions:
  new-upload:
    handler: app.uploads.create
    events:
      - http: POST /uploads
""",
          "app/__init__.py": "",
          "app/uploads.py": FUTURE + """
def create(event, ctx):
    data = event.http.json(default={})
    upload_id = uuid4()
    return {"id": upload_id, "name": data.get("name", "file")}, 201
""",
          "requirements.txt": ""}),
      user="new-upload say name 'uuid4' is not defined, I use it in other project without problem",
      steps=[
          S("read_file", path="app/uploads.py"),
          S("invoke_local", function="new-upload", method="POST", path="/uploads", data={"name": "report.pdf"}),
          S("propose_plan", steps=["Add `from uuid import uuid4`"]),
          S("write_file", path="app/uploads.py", content=FUTURE + """from uuid import uuid4


def create(event, ctx):
    data = event.http.json(default={})
    upload_id = uuid4()
    return {"id": upload_id, "name": data.get("name", "file")}, 201
"""),
          S("invoke_local", function="new-upload", method="POST", path="/uploads", data={"name": "report.pdf"}),
          S("validate"),
      ],
      final="""Each file needs its own import; this one didn't import `uuid4`. Added `from uuid import uuid4`. Returning the `UUID` object is fine: pskit writes it as a string [docs/handlers.md#returning-a-response].

- POST /uploads: 201, `{"id": "<uuid>", "name": "report.pdf"}`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 149 onprem storage, endswith with two args
    B(149, provider="onprem", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: gallery\n" + ONPREM.format(port=8234) + """functions:
  index-image:
    handler: app.gallery.index
    events:
      - storage: gallery-uploads
""",
          "app/__init__.py": "",
          "app/gallery.py": FUTURE + """
def index(event, ctx):
    images = [r.key for r in event.records if r.key.lower().endswith(".jpg", ".png")]
    return {"indexed": images}
""",
          "requirements.txt": ""}),
      user="index-image: slice indices must be integers or None. there is no slice in my code??",
      steps=[
          S("read_file", path="app/gallery.py"),
          S("invoke_local", function="index-image", type="storage", data=[{"key": "cat.PNG"}, {"key": "doc.txt"}]),
          S("propose_plan", steps=["Pass the suffixes as one tuple: `endswith((\".jpg\", \".png\"))`",
                                   "Invoke with cat.PNG and doc.txt; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/gallery.py", content=FUTURE + """
IMAGE_TYPES = (".jpg", ".jpeg", ".png")


def index(event, ctx):
    images = [r.key for r in event.records if r.key.lower().endswith(IMAGE_TYPES)]
    return {"indexed": images}
"""),
          S("invoke_local", function="index-image", type="storage", data=[{"key": "cat.PNG"}, {"key": "doc.txt"}]),
          S("validate"),
      ],
      final="""Hidden slice: `endswith(".jpg", ".png")` means "ends with `.jpg`, **starting at position `.png`**". Several suffixes must be one tuple. Now `endswith(IMAGE_TYPES)` with `(".jpg", ".jpeg", ".png")`.

- invoke (cat.PNG, doc.txt): `{"indexed": ["cat.PNG"]}`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 150 azure schedule, run_until_complete in an async handler
    B(150, provider="azure", stage="staging", mode="ask", page="Code", persona="pasted_error",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": """service: health
provider:
  name: azure
  region: eastus
functions:
  ping-all:
    handler: app.health.ping_all
    events:
      - schedule: 15 minutes
""",
          "app/__init__.py": "",
          "app/health.py": FUTURE + """import asyncio

TARGETS = ["api.example.com", "www.example.com"]


async def ping(host):
    await asyncio.sleep(0)
    return {"host": host, "up": True}


async def ping_all(event, ctx):
    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(asyncio.gather(*(ping(h) for h in TARGETS)))
    return {"results": results}
""",
          "requirements.txt": ""}),
      user="""RuntimeError: This event loop is already running
ping-all, every run""",
      steps=[
          S("read_file", path="app/health.py"),
          S("invoke_local", function="ping-all", type="schedule"),
          S("propose_plan", steps=["Inside an async handler, `await asyncio.gather(...)` instead of `loop.run_until_complete`",
                                   "Run ping-all as a schedule event and validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/health.py", content=FUTURE + """import asyncio

TARGETS = ["api.example.com", "www.example.com"]


async def ping(host):
    await asyncio.sleep(0)
    return {"host": host, "up": True}


async def ping_all(event, ctx):
    results = await asyncio.gather(*(ping(h) for h in TARGETS))
    return {"results": results}
"""),
          S("invoke_local", function="ping-all", type="schedule"),
          S("validate"),
      ],
      final="""An `async def` handler already runs inside an event loop, because pskit awaits it [docs/handlers.md#handler-signatures]. `run_until_complete` tries to start that loop a second time. Inside async code, just `await`: `results = await asyncio.gather(...)`.

- schedule run: `{"results": [{"host": "api.example.com", "up": true}, {"host": "www.example.com", "up": true}]}`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 151 onprem http, path param that the route doesn't have
    B(151, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: rooms\n" + ONPREM.format(port=8235) + """functions:
  room:
    handler: app.rooms.get_room
    events:
      - http: GET /rooms
""",
          "app/__init__.py": "",
          "app/rooms.py": FUTURE + """ROOMS = {"5": "Orion", "7": "Lyra"}


def get_room(event, ctx):
    room_id = event.http.path_params["id"]
    return {"id": room_id, "name": ROOMS.get(room_id)}
""",
          "requirements.txt": ""}),
      user="I open /rooms?id=5 and get 500 KeyError: 'id'. The id is right there in the URL!",
      steps=[
          S("read_file", path="app/rooms.py"),
          S("invoke_local", function="room", path="/rooms?id=5"),
          S("search_docs", query="query string vs path params",
            docs=[D("docs/handlers.md", "httprequest", start="| `query` |", end="| `path_params` |")]),
          S("propose_plan", steps=["Read `id` from `event.http.query` (it is after `?`); `path_params` only has `{name}` parts of the route",
                                   "GET /rooms?id=5 locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/rooms.py", content=FUTURE + """from py_serverless_kit import BadRequest

ROOMS = {"5": "Orion", "7": "Lyra"}


def get_room(event, ctx):
    room_id = event.http.query.get("id")
    if room_id is None:
        raise BadRequest("id is required")
    return {"id": room_id, "name": ROOMS.get(room_id)}
"""),
          S("invoke_local", function="room", path="/rooms?id=5"),
          S("validate"),
      ],
      final="""The id is in the **query string** (after `?`), so it is in `event.http.query`. `path_params` only holds `{name}` parts of the route, and `/rooms` has none [docs/handlers.md#httprequest]. The handler now reads `query.get("id")` and answers 400 when it is missing.

- GET /rooms?id=5: 200, `{"id": "5", "name": "Orion"}`.
- validate (onprem): valid.

If you prefer URLs like `/rooms/5`, change the route to `GET /rooms/{id}` and keep `path_params["id"]`."""),

    # ------------------------------------------------------------------ 152 gcp workflow, parallel result is a list
    B(152, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": "service: pricing-wf\n" + GCP.format(region="europe-west1") + """functions:
  base-price:
    handler: app.price.base
  tax-rate:
    handler: app.price.tax
  final-price:
    handler: app.price.final
workflows:
  price:
    start_at: Lookups
    states:
      Lookups:
        type: parallel
        branches:
          - start_at: Base
            states:
              Base: {type: task, function: base-price, end: true}
          - start_at: Tax
            states:
              Tax: {type: task, function: tax-rate, end: true}
        next: Final
      Final: {type: task, function: final-price, end: true}
""",
          "app/__init__.py": "",
          "app/price.py": FUTURE + """
def base(event, ctx):
    return {"price": 100.0}


def tax(event, ctx):
    return {"rate": 0.2}


def final(event, ctx):
    data = event.data
    return {"total": round(data["price"] * (1 + data["rate"]), 2)}
""",
          "requirements.txt": ""}),
      user="In the price workflow, Final fails with TypeError: list indices must be integers or slices, not str. Lookups runs Base and Tax in parallel and Final should multiply the price by (1 + rate). Please fix Final, don't change the workflow, and test it with what Lookups really passes on.",
      steps=[
          S("read_file", path="app/price.py"),
          S("invoke_local", function="final-price", type="workflow", data=[{"price": 100.0}, {"rate": 0.2}]),
          S("search_docs", query="parallel state result list",
            docs=[D("docs/workflows.md", "state-types", start="| `parallel` |", end="| `parallel` |")]),
          S("propose_plan", steps=["In `final`, merge the list of branch results into one dict before reading price and rate",
                                   "Invoke final-price with `[{price}, {rate}]`; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/price.py", content=FUTURE + """
def base(event, ctx):
    return {"price": 100.0}


def tax(event, ctx):
    return {"rate": 0.2}


def final(event, ctx):
    data = {}
    for branch in event.data:
        data.update(branch)
    return {"total": round(data["price"] * (1 + data["rate"]), 2)}
"""),
          S("invoke_local", function="final-price", type="workflow", data=[{"price": 100.0}, {"rate": 0.2}]),
          S("validate"),
      ],
      final="""A `parallel` state's result is a **list**, one item per branch, in branch order [docs/workflows.md#state-types]. So `Final` gets `[{"price": 100.0}, {"rate": 0.2}]`, not one dict. `final` now merges the branch results before reading `price` and `rate`. The workflow is unchanged.

- final-price with `[{"price": 100.0}, {"rate": 0.2}]`: `{"total": 120.0}`.
- validate (gcp, prod): valid (native engine)."""),

    # ------------------------------------------------------------------ 153 aws storage, with_suffix without the dot
    B(153, provider="aws", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: img-convert
provider:
  name: aws
  region: ap-south-1
functions:
  to-webp:
    handler: app.convert.handle
    events:
      - storage:
          bucket: raw-images
          suffix: .png
""",
          "app/__init__.py": "",
          "app/convert.py": FUTURE + """from pathlib import PurePosixPath


def handle(event, ctx):
    out = []
    for record in event.records:
        target = PurePosixPath("webp") / PurePosixPath(record.key).with_suffix("webp")
        out.append(str(target))
    return {"targets": out}
""",
          "requirements.txt": ""}),
      user="to-webp: ValueError Invalid suffix 'webp'",
      steps=[
          S("read_file", path="app/convert.py"),
          S("invoke_local", function="to-webp", type="storage", data=[{"key": "shop/hero.png"}]),
          S("propose_plan", steps=["Pass the suffix with its dot: `with_suffix(\".webp\")`"]),
          S("write_file", path="app/convert.py", content=FUTURE + """from pathlib import PurePosixPath


def handle(event, ctx):
    out = []
    for record in event.records:
        target = PurePosixPath("webp") / PurePosixPath(record.key).with_suffix(".webp")
        out.append(str(target))
    return {"targets": out}
"""),
          S("invoke_local", function="to-webp", type="storage", data=[{"key": "shop/hero.png"}]),
          S("validate"),
      ],
      final="""`with_suffix()` needs the leading dot: `".webp"`. Fixed.

- invoke (`shop/hero.png`): `{"targets": ["webp/shop/hero.webp"]}`.
- validate (aws): valid.

Writing the result under `webp/` in the same bucket is safe here because the trigger has `suffix: .png`, so the new `.webp` files don't start the function again."""),

    # ------------------------------------------------------------------ 154 onprem queue, counter without global
    B(154, provider="onprem", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": "service: counters\n" + ONPREM.format(port=8236) + """functions:
  count-visits:
    handler: app.visits.handle
    events:
      - queue: visits
""",
          "app/__init__.py": "",
          "app/visits.py": FUTURE + """processed = 0


def handle(event, ctx):
    for record in event.records:
        processed += 1
    ctx.logger.info("visits", extra={"total_since_start": processed})
    return {"batch": len(event.records)}
""",
          "requirements.txt": ""}),
      user="""UnboundLocalError: cannot access local variable 'processed' where it is not associated with a value
count-visits""",
      steps=[
          S("read_file", path="app/visits.py"),
          S("invoke_local", function="count-visits", type="queue", data=[{"page": "/"}, {"page": "/about"}]),
          S("propose_plan", steps=["Declare `global processed` in the handler before changing it",
                                   "Invoke count-visits with two messages; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/visits.py", content=FUTURE + """processed = 0


def handle(event, ctx):
    global processed
    for record in event.records:
        processed += 1
    ctx.logger.info("visits", extra={"total_since_start": processed})
    return {"batch": len(event.records)}
"""),
          S("invoke_local", function="count-visits", type="queue", data=[{"page": "/"}, {"page": "/about"}]),
          S("validate"),
      ],
      final="""`processed += 1` inside a function makes `processed` a **local** variable, so Python never looks at the module-level one. `global processed` fixes that.

- invoke (2 messages): logs "visits" with `total_since_start` 2, returns `{"batch": 2}`.
- validate (onprem, staging): valid.

The counter lives in the host process: it restarts at 0 when the host restarts and isn't shared between servers. Use a database or cache resource for a real total."""),

    # ------------------------------------------------------------------ 155 azure queue, decode() on a str body
    B(155, provider="azure", stage="prod", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: sms-in
provider:
  name: azure
  region: westeurope
functions:
  inbound-sms:
    handler: app.sms.handle
    events:
      - queue: inbound-sms
""",
          "app/__init__.py": "",
          "app/sms.py": FUTURE + """
def handle(event, ctx):
    texts = []
    for record in event.records:
        texts.append(record.body.decode("utf-8").strip())
    return {"texts": texts}
""",
          "requirements.txt": ""}),
      user="My SQS code did record['body'].decode() on bytes. On pskit with Azure queues: 'str' object has no attribute 'decode'. Is the body type different per cloud?",
      steps=[
          S("read_file", path="app/sms.py"),
          S("invoke_local", function="inbound-sms", type="queue", data=["STOP", " HELP "]),
          S("search_docs", query="record body text decode",
            docs=[D("docs/handlers.md", "record")]),
          S("propose_plan", steps=["Use `record.text()`, which returns a str whether the body is str or bytes",
                                   "Invoke with two text messages; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sms.py", content=FUTURE + """
def handle(event, ctx):
    texts = []
    for record in event.records:
        texts.append(record.text().strip())
    return {"texts": texts}
"""),
          S("invoke_local", function="inbound-sms", type="queue", data=["STOP", " HELP "]),
          S("validate"),
      ],
      final="""It can be: `record.body` is str, bytes or a dict, depending on the source [docs/handlers.md#record]. Here it is already a str. Don't decode it yourself; `record.text()` always returns a str (and `record.json()` the parsed JSON). The handler now uses `record.text().strip()`.

- invoke ("STOP", " HELP "): `{"texts": ["STOP", "HELP"]}`.
- validate (azure, prod): valid. The same code works on SQS."""),

    # ------------------------------------------------------------------ 156 onprem smtp, cc[0] on a mail without cc
    B(156, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": "service: mail-log\n" + ONPREM.format(port=8237) + """resources:
  inbox:
    type: smtp
    external: true
    connection: {host: 192.0.2.30, port: 25, domains: mail.example.com}
functions:
  log-mail:
    handler: app.maillog.handle
    events:
      - smtp: inbox
""",
          "app/__init__.py": "",
          "app/maillog.py": FUTURE + """
def handle(event, ctx):
    mail = event.data
    first_cc = mail["cc"][0]
    ctx.logger.info("mail", extra={"from": mail["from"], "cc": first_cc})
    return {"subject": mail["subject"], "cc": first_cc}
""",
          "requirements.txt": ""}),
      user="log-mail crash IndexError list index out of range when mail have no cc. with cc it work",
      steps=[
          S("read_file", path="app/maillog.py"),
          S("invoke_local", function="log-mail", type="smtp", data={"from": "ivan@example.org", "to": "log@mail.example.com", "subject": "Hi", "text": "hello"}),
          S("propose_plan", steps=["Use the first cc only if the list is not empty, else None",
                                   "Invoke with a mail without cc; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/maillog.py", content=FUTURE + """
def handle(event, ctx):
    mail = event.data
    first_cc = mail["cc"][0] if mail["cc"] else None
    ctx.logger.info("mail", extra={"from": mail["from"], "cc": first_cc})
    return {"subject": mail["subject"], "cc": first_cc}
"""),
          S("invoke_local", function="log-mail", type="smtp", data={"from": "ivan@example.org", "to": "log@mail.example.com", "subject": "Hi", "text": "hello"}),
          S("validate"),
      ],
      final="""`mail["cc"]` is always a list, and for a mail without cc it is **empty** [docs/smtp/README.md#what-the-handler-receives], so `[0]` fails. Now the handler takes the first cc only when there is one, else `None`.

- test mail without cc: logs "mail", returns `{"subject": "Hi", "cc": null}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 157 gcp schedule, strptime vs ISO input with Z
    B(157, provider="gcp", stage="staging", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: exports-sync\n" + GCP.format(region="us-central1") + """functions:
  sync-since:
    handler: app.sync.run
    events:
      - schedule:
          cron: "*/30 * * * *"
          input: {since: "2026-11-01T00:00:00Z"}
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """from datetime import datetime


def run(event, ctx):
    since = datetime.strptime(event.data["since"], "%Y-%m-%d")
    return {"since": since.isoformat()}
""",
          "requirements.txt": ""}),
      user="sync-since reads a 'since' timestamp from the schedule input. Ops changed the input to a full ISO time with Z, and now it fails with ValueError: unconverted data remains. It must accept the full timestamp (UTC) and also still work with a plain date like 2026-11-01. It has to run on the python3.9 runtime.",
      steps=[
          S("read_file", path="app/sync.py"),
          S("invoke_local", function="sync-since", type="schedule"),
          S("propose_plan", steps=["Parse with `datetime.fromisoformat` after turning a trailing `Z` into `+00:00` (3.9 doesn't read `Z`); treat a plain date as UTC midnight",
                                   "Run sync-since as a schedule event and validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sync.py", content=FUTURE + """from datetime import datetime, timezone


def parse_since(text):
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def run(event, ctx):
    since = parse_since(event.data["since"])
    return {"since": since.isoformat()}
"""),
          S("invoke_local", function="sync-since", type="schedule"),
          S("validate"),
      ],
      final="""`strptime(..., "%Y-%m-%d")` only accepts a bare date, so `T00:00:00Z` was "unconverted data". The handler now uses `datetime.fromisoformat`, which reads both `2026-11-01` and full timestamps. On Python 3.9 it doesn't understand a trailing `Z`, so `parse_since` turns `Z` into `+00:00` first and treats times without a zone as UTC.

- schedule run with `2026-11-01T00:00:00Z`: `{"since": "2026-11-01T00:00:00+00:00"}`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 158 onprem http, PermissionError -> 500
    B(158, provider="onprem", stage="prod", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: admin-api\n" + ONPREM.format(port=8238) + """functions:
  purge-user:
    handler: app.admin.purge
    events:
      - http: DELETE /users/{id}
""",
          "app/__init__.py": "",
          "app/admin.py": FUTURE + """
def purge(event, ctx):
    if event.http.headers.get("x-role") != "admin":
        raise PermissionError("admins only")
    return None
""",
          "requirements.txt": ""}),
      user="DELETE /users/{id} as non-admin -> 500. want 403",
      steps=[
          S("read_file", path="app/admin.py"),
          S("invoke_local", function="purge-user", method="DELETE", path="/users/42"),
          S("propose_plan", steps=["Raise pskit's `Forbidden` instead of `PermissionError`"]),
          S("write_file", path="app/admin.py", content=FUTURE + """from py_serverless_kit import Forbidden


def purge(event, ctx):
    if event.http.headers.get("x-role") != "admin":
        raise Forbidden("admins only")
    return None
"""),
          S("invoke_local", function="purge-user", method="DELETE", path="/users/42"),
          S("validate"),
      ],
      final="""Only `HttpError` subclasses map to a status; Python's `PermissionError` is just an exception, so it became a 500 [docs/handlers.md#errors]. Now `raise Forbidden("admins only")`.

- DELETE /users/42 without `x-role: admin`: 403, `{"error": "admins only", "status": 403}`.
- validate (onprem, prod): valid.

An `x-role` header can be set by any client; check a real token before you trust it."""),

    # ------------------------------------------------------------------ 159 aws http, startswith with a list
    B(159, provider="aws", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: internal-metrics
provider:
  name: aws
  region: us-east-1
functions:
  metrics:
    handler: app.metrics.get_metrics
    events:
      - http: GET /metrics
""",
          "app/__init__.py": "",
          "app/metrics.py": FUTURE + """from py_serverless_kit import Forbidden

ALLOWED_PREFIXES = ["10.", "127.", "192.168."]


def get_metrics(event, ctx):
    ip = event.http.source_ip or ""
    if not ip.startswith(ALLOWED_PREFIXES):
        raise Forbidden("internal only")
    return {"requests": 1200, "errors": 3}
""",
          "requirements.txt": ""}),
      user="/metrics should only answer clients from our internal ranges (10., 127., 192.168.) and give 403 to everyone else. It returns 500 for every caller, also locally, with TypeError: startswith first arg must be str or a tuple of str, not list. Please fix and test it.",
      steps=[
          S("read_file", path="app/metrics.py"),
          S("invoke_local", function="metrics", path="/metrics"),
          S("propose_plan", steps=["Make the allowed prefixes a tuple; `str.startswith` accepts a str or a tuple",
                                   "GET /metrics locally (source 127.0.0.1) and validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/metrics.py", content=FUTURE + """from py_serverless_kit import Forbidden

ALLOWED_PREFIXES = ("10.", "127.", "192.168.")


def get_metrics(event, ctx):
    ip = event.http.source_ip or ""
    if not ip.startswith(ALLOWED_PREFIXES):
        raise Forbidden("internal only")
    return {"requests": 1200, "errors": 3}
"""),
          S("invoke_local", function="metrics", path="/metrics"),
          S("validate"),
      ],
      final="""`str.startswith()` takes one string or a **tuple** of strings, not a list. `ALLOWED_PREFIXES` is now a tuple. `event.http.source_ip` is the client IP when known [docs/handlers.md#httprequest]; local runs use `127.0.0.1`.

- GET /metrics locally: 200, `{"requests": 1200, "errors": 3}`.
- validate (aws, prod): valid.

Prefix checks are rough (`10.` also matches `100.x`). For real ranges, compare with `ipaddress.ip_address(ip) in ipaddress.ip_network(...)` and your network's CIDR blocks."""),

    # ------------------------------------------------------------------ 160 onprem workflow, task forgets to return
    B(160, provider="onprem", stage="dev", mode="auto", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#workflows-state-machines"],
      project=dict(files={
          "pskit.yml": "service: signup-flow\n" + ONPREM.format(port=8239) + """functions:
  normalize:
    handler: app.flow.normalize
  welcome:
    handler: app.flow.welcome
workflows:
  signup:
    start_at: Normalize
    states:
      Normalize: {type: task, function: normalize, next: Welcome}
      Welcome: {type: task, function: welcome, end: true}
""",
          "app/__init__.py": "",
          "app/flow.py": FUTURE + """
def normalize(event, ctx):
    user = dict(event.data)
    user["email"] = user["email"].strip().lower()


def welcome(event, ctx):
    return {"sent_to": event.data["email"]}
""",
          "requirements.txt": ""}),
      user="signup workflow: Welcome step says 'NoneType' object is not subscriptable. Normalize looks ok, it fixes the email",
      steps=[
          S("read_file", path="app/flow.py"),
          S("invoke_local", function="normalize", type="workflow", data={"email": "  Kai@Example.COM "}),
          S("propose_plan", steps=["Add `return user` at the end of `normalize`: a task's return value is the next state's input"]),
          S("write_file", path="app/flow.py", content=FUTURE + """
def normalize(event, ctx):
    user = dict(event.data)
    user["email"] = user["email"].strip().lower()
    return user


def welcome(event, ctx):
    return {"sent_to": event.data["email"]}
"""),
          S("invoke_local", function="normalize", type="workflow", data={"email": "  Kai@Example.COM "}),
          S("invoke_local", function="welcome", type="workflow", data={"email": "kai@example.com"}),
          S("validate"),
      ],
      final="""`normalize` fixed the email but never **returned** it. A function without `return` gives `None`, and whatever a task returns is the next state's input [docs/workflows.md#workflows-state-machines]. So Welcome got `None`. I added `return user`.

- normalize: `{"email": "kai@example.com"}` (before: `null`).
- welcome with that: `{"sent_to": "kai@example.com"}`.
- validate (onprem): valid."""),
]
