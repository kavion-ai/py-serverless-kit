"""Category D (fix a handler bug), batch 14. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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


def AWS(service, region="us-east-1", extra=""):
    return f"service: {service}\nprovider:\n  name: aws\n  region: {region}\n{extra}"


def AZ(service, region="westeurope"):
    return f"service: {service}\nprovider:\n  name: azure\n  region: {region}\n"


CONVERSATIONS = [
    # ------------------------------------------------------------------ 261 onprem http, SQL built with an f-string
    B(261, provider="onprem", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: staff-dir\n" + ONPREM.format(port=8641) + """functions:
  find-staff:
    handler: app.staff.find
    events:
      - http: GET /staff
""",
          "app/__init__.py": "",
          "app/staff.py": FUTURE + """import sqlite3

DB = sqlite3.connect(":memory:")
DB.executescript(\"\"\"
CREATE TABLE staff (name TEXT, team TEXT);
INSERT INTO staff VALUES ('Ines', 'ops'), ('Omar', 'hr'), ('Lin', 'ops');
\"\"\")


def find(event, ctx):
    team = event.http.query.get("team", "")
    rows = DB.execute(f"SELECT name FROM staff WHERE team = '{team}'").fetchall()
    return {"staff": [r[0] for r in rows]}
""",
          "requirements.txt": ""}),
      user="A pentest report says GET /staff?team=... is injectable: team=x' OR '1'='1 returns every employee, HR included. The endpoint should only ever return the members of the team that was asked for. Please fix it and show me the injection no longer works.",
      steps=[
          S("read_file", path="app/staff.py"),
          S("invoke_local", function="find-staff", path="/staff?team=x' OR '1'='1"),
          S("propose_plan", steps=["Pass `team` as a query parameter (`WHERE team = ?`) instead of putting it into the SQL text",
                                   "GET the injection string (must return nothing) and team=ops locally; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/staff.py", content=FUTURE + """import sqlite3

DB = sqlite3.connect(":memory:")
DB.executescript(\"\"\"
CREATE TABLE staff (name TEXT, team TEXT);
INSERT INTO staff VALUES ('Ines', 'ops'), ('Omar', 'hr'), ('Lin', 'ops');
\"\"\")


def find(event, ctx):
    team = event.http.query.get("team", "")
    rows = DB.execute("SELECT name FROM staff WHERE team = ?", (team,)).fetchall()
    return {"staff": [r[0] for r in rows]}
"""),
          S("invoke_local", function="find-staff", path="/staff?team=x' OR '1'='1"),
          S("invoke_local", function="find-staff", path="/staff?team=ops"),
          S("validate"),
      ],
      final="""The query string was pasted into the SQL text, so `' OR '1'='1` became part of the SQL and matched every row. With a `?` placeholder, the database driver passes `team` as a value, and it is never read as SQL.

- Injection string: before `["Ines", "Omar", "Lin"]`, now `[]`.
- `team=ops`: `["Ines", "Lin"]`.
- validate (onprem, prod): valid.

Use placeholders everywhere you build SQL, also in other functions of this service."""),

    # ------------------------------------------------------------------ 262 onprem http, `or` with a bare string
    B(262, provider="onprem", stage="staging", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: cms\n" + ONPREM.format(port=8642) + """functions:
  publish:
    handler: app.cms.publish
    events:
      - http: POST /articles/{id}/publish
""",
          "app/__init__.py": "",
          "app/cms.py": FUTURE + """from py_serverless_kit import Forbidden

ROLES = {"u1": "admin", "u2": "viewer"}


def publish(event, ctx):
    role = ROLES.get(event.http.json().get("user"), "")
    if role == "admin" or "editor":
        return {"published": event.http.path_params["id"]}
    raise Forbidden("editors only")
""",
          "requirements.txt": ""}),
      user="viewers can publish. role check: role == \"admin\" or \"editor\"",
      steps=[
          S("read_file", path="app/cms.py"),
          S("invoke_local", function="publish", method="POST", path="/articles/a9/publish", data={"user": "u2"}),
          S("propose_plan", steps=["Use `role in (\"admin\", \"editor\")`; `or \"editor\"` is always true",
                                   "POST as viewer u2 (403) and admin u1 (200); validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/cms.py", content=FUTURE + """from py_serverless_kit import Forbidden

ROLES = {"u1": "admin", "u2": "viewer"}


def publish(event, ctx):
    role = ROLES.get(event.http.json().get("user"), "")
    if role in ("admin", "editor"):
        return {"published": event.http.path_params["id"]}
    raise Forbidden("editors only")
"""),
          S("invoke_local", function="publish", method="POST", path="/articles/a9/publish", data={"user": "u2"}),
          S("invoke_local", function="publish", method="POST", path="/articles/a9/publish", data={"user": "u1"}),
          S("validate"),
      ],
      final="""It reads as `(role == "admin") or ("editor")`, and a non-empty string is truthy, so the condition was always true. Now it is `role in ("admin", "editor")`.

- u2 (viewer): 403 `editors only`. u1 (admin): 200.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 263 onprem schedule, loop variable after an empty loop
    B(263, provider="onprem", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: feed-poller\n" + ONPREM.format(port=8643) + """functions:
  poll:
    handler: app.poll.run
    events:
      - schedule:
          rate: 15 minutes
          input: {items: []}
""",
          "app/__init__.py": "",
          "app/poll.py": FUTURE + """
def run(event, ctx):
    for i, item in enumerate(event.data["items"], 1):
        ctx.logger.info("item", extra={"n": i, "item": item})
    return {"processed": i}
""",
          "requirements.txt": ""}),
      user="""UnboundLocalError: cannot access local variable 'i' where it is not associated with a value
poll, only when the feed is empty""",
      steps=[
          S("read_file", path="app/poll.py"),
          S("invoke_local", function="poll", type="schedule"),
          S("propose_plan", steps=["Count with `len(items)` instead of reading the loop variable after the loop",
                                   "Run with an empty and a 2-item feed; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/poll.py", content=FUTURE + """
def run(event, ctx):
    items = event.data.get("items") or []
    for i, item in enumerate(items, 1):
        ctx.logger.info("item", extra={"n": i, "item": item})
    return {"processed": len(items)}
"""),
          S("invoke_local", function="poll", type="schedule"),
          S("invoke_local", function="poll", type="schedule", data={"items": ["a", "b"]}),
          S("validate"),
      ],
      final="""When the list is empty, the `for` loop never runs, so `i` is never set and `return {"processed": i}` fails. `len(items)` works for any size.

- Empty feed: `{"processed": 0}`. Two items: `{"processed": 2}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 264 onprem http, shallow copy of a nested template
    B(264, provider="onprem", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: doc-builder\n" + ONPREM.format(port=8644) + """functions:
  build-docs:
    handler: app.docs.build
    events:
      - http: POST /docs/build
""",
          "app/__init__.py": "",
          "app/docs.py": FUTURE + """TEMPLATE = {"version": 1, "meta": {"tags": []}}


def build(event, ctx):
    docs = []
    for item in event.http.json()["items"]:
        doc = dict(TEMPLATE)
        doc["meta"]["tags"].append(item["tag"])
        docs.append(doc)
    return {"docs": docs}
""",
          "requirements.txt": ""}),
      user="i copy the template with dict() for each doc but all docs have all tags. copy not work?",
      steps=[
          S("read_file", path="app/docs.py"),
          S("invoke_local", function="build-docs", method="POST", path="/docs/build",
            data={"items": [{"tag": "red"}, {"tag": "blue"}]}),
          S("propose_plan", steps=["Use `copy.deepcopy(TEMPLATE)`: `dict()` copies only the top level, so `meta` is shared",
                                   "POST two items locally and validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/docs.py", content=FUTURE + """import copy

TEMPLATE = {"version": 1, "meta": {"tags": []}}


def build(event, ctx):
    docs = []
    for item in event.http.json()["items"]:
        doc = copy.deepcopy(TEMPLATE)
        doc["meta"]["tags"].append(item["tag"])
        docs.append(doc)
    return {"docs": docs}
"""),
          S("invoke_local", function="build-docs", method="POST", path="/docs/build",
            data={"items": [{"tag": "red"}, {"tag": "blue"}]}),
          S("validate"),
      ],
      final="""`dict(TEMPLATE)` is a *shallow* copy: the outer dict is new, but `meta` inside is still the same dict for every doc, **and** for the template itself. So the tags piled up, even across requests. `copy.deepcopy` copies the nested parts too.

- Before: both docs `["red", "blue"]`.
- After: `["red"]` and `["blue"]`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 265 onprem http, impossible chained comparison
    B(265, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: gym-signup\n" + ONPREM.format(port=8645) + """functions:
  member:
    handler: app.gym.member
    events:
      - http: POST /members
""",
          "app/__init__.py": "",
          "app/gym.py": FUTURE + """from py_serverless_kit import BadRequest


def member(event, ctx):
    age = int(event.http.json()["age"])
    if 0 > age > 120:
        raise BadRequest("age must be 0-120")
    return {"age": age}, 201
""",
          "requirements.txt": ""}),
      user="someone signed up with age 500 and it was accepted. I check if 0 > age > 120, why doesn't it stop it?",
      steps=[
          S("read_file", path="app/gym.py"),
          S("invoke_local", function="member", method="POST", path="/members", data={"age": 500}),
          S("propose_plan", steps=["Write the range check as `not 0 <= age <= 120`",
                                   "POST age 500 (400) and 30 (201) locally; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/gym.py", content=FUTURE + """from py_serverless_kit import BadRequest


def member(event, ctx):
    age = int(event.http.json()["age"])
    if not 0 <= age <= 120:
        raise BadRequest("age must be 0-120")
    return {"age": age}, 201
"""),
          S("invoke_local", function="member", method="POST", path="/members", data={"age": 500}),
          S("invoke_local", function="member", method="POST", path="/members", data={"age": 30}),
          S("validate"),
      ],
      final="""`0 > age > 120` means "age is below 0 **and** above 120", which no number can be, so the check never fired. `not 0 <= age <= 120` means "outside 0 to 120".

- age 500: 400 `age must be 0-120` [docs/handlers.md#errors].
- age 30: 201.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 266 onprem http, :.2 is significant digits
    B(266, provider="onprem", stage="staging", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: price-tags\n" + ONPREM.format(port=8646) + """functions:
  label:
    handler: app.labels.label
    events:
      - http: GET /labels/{sku}
""",
          "app/__init__.py": "",
          "app/labels.py": FUTURE + """PRICES = {"SOFA": 1249.5, "LAMP": 39.0}


def label(event, ctx):
    price = PRICES[event.http.path_params["sku"]]
    return f"EUR {price:.2}"
""",
          "requirements.txt": ""}),
      user="""GET /labels/SOFA -> "EUR 1.2e+03"
should be EUR 1,249.50""",
      steps=[
          S("read_file", path="app/labels.py"),
          S("invoke_local", function="label", path="/labels/SOFA"),
          S("propose_plan", steps=["Use `{price:,.2f}`: `.2` means 2 significant digits, `.2f` means 2 decimals, `,` groups thousands",
                                   "GET /labels/SOFA locally and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/labels.py", content=FUTURE + """PRICES = {"SOFA": 1249.5, "LAMP": 39.0}


def label(event, ctx):
    price = PRICES[event.http.path_params["sku"]]
    return f"EUR {price:,.2f}"
"""),
          S("invoke_local", function="label", path="/labels/SOFA"),
          S("validate"),
      ],
      final="""In a format spec, `.2` without a type means **2 significant digits**, so 1249.5 became `1.2e+03`. `,.2f` means thousands separators plus 2 decimals.

- After: `EUR 1,249.50` (text/plain).
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 267 onprem http, unescaped HTML
    B(267, provider="onprem", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: welcome-page\n" + ONPREM.format(port=8647) + """functions:
  hello-page:
    handler: app.page.hello
    events:
      - http: GET /hello
""",
          "app/__init__.py": "",
          "app/page.py": FUTURE + """from py_serverless_kit import Response


def hello(event, ctx):
    name = event.http.query.get("name", "guest")
    return Response.html(f"<h1>Hello, {name}!</h1>")
""",
          "requirements.txt": ""}),
      user="Security found that GET /hello?name=<script>alert(1)</script> runs the script in the browser. The page must show whatever name is given as plain text, never as HTML. Please fix it and show the result for that exact name.",
      steps=[
          S("read_file", path="app/page.py"),
          S("invoke_local", function="hello-page", path="/hello?name=<script>alert(1)</script>"),
          S("propose_plan", steps=["Escape the name with `html.escape()` before putting it into the HTML",
                                   "GET with the script name locally and validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/page.py", content=FUTURE + """import html

from py_serverless_kit import Response


def hello(event, ctx):
    name = html.escape(event.http.query.get("name", "guest"))
    return Response.html(f"<h1>Hello, {name}!</h1>")
"""),
          S("invoke_local", function="hello-page", path="/hello?name=<script>alert(1)</script>"),
          S("validate"),
      ],
      final="""The name went into the page as raw HTML, so the browser ran `<script>`: a reflected XSS. `html.escape()` turns `<`, `>`, `&` and quotes into entities, and the browser shows them as text.

- Before: `<h1>Hello, <script>alert(1)</script>!</h1>`.
- After: `<h1>Hello, &lt;script&gt;alert(1)&lt;/script&gt;!</h1>`.
- validate (onprem, prod): valid.

Escape every user value you put into `Response.html` [docs/handlers.md#returning-a-response]."""),

    # ------------------------------------------------------------------ 268 onprem http, `in` checks dict keys
    B(268, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: invite-check\n" + ONPREM.format(port=8648) + """functions:
  invited:
    handler: app.invite.check
    events:
      - http: GET /invited
""",
          "app/__init__.py": "",
          "app/invite.py": FUTURE + """from py_serverless_kit import NotFound

GUESTS = {"g1": "ana@example.com", "g2": "raj@example.com"}


def check(event, ctx):
    email = event.http.query.get("email", "").lower()
    if email not in GUESTS:
        raise NotFound("not invited")
    return {"invited": True}
""",
          "requirements.txt": ""}),
      user="ana@example.com is in the guest list but /invited?email=ana@example.com say not invited",
      steps=[
          S("read_file", path="app/invite.py"),
          S("invoke_local", function="invited", path="/invited?email=ana@example.com"),
          S("propose_plan", steps=["Look in the dict's values: `email not in GUESTS.values()` (`in` on a dict checks keys)",
                                   "GET with ana@example.com locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/invite.py", content=FUTURE + """from py_serverless_kit import NotFound

GUESTS = {"g1": "ana@example.com", "g2": "raj@example.com"}
EMAILS = set(GUESTS.values())


def check(event, ctx):
    email = event.http.query.get("email", "").lower()
    if email not in EMAILS:
        raise NotFound("not invited")
    return {"invited": True}
"""),
          S("invoke_local", function="invited", path="/invited?email=ana@example.com"),
          S("validate"),
      ],
      final="""`email in GUESTS` looks at the **keys** (`g1`, `g2`), not the emails. Now the handler checks a set of the values.

- Before: 404 `not invited`. After: 200 `{"invited": true}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 269 aws http, "+" in a query string
    B(269, provider="aws", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AWS("audit-query", "eu-west-1") + """functions:
  events-since:
    handler: app.audit.since
    events:
      - http: GET /audit
""",
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """from datetime import datetime


def since(event, ctx):
    start = datetime.fromisoformat(event.http.query["since"])
    return {"since": start.isoformat()}
""",
          "requirements.txt": ""}),
      user="""ValueError: Invalid isoformat string: '2026-11-01T00:00:00 00:00'
GET /audit?since=2026-11-01T00:00:00+00:00 - where did the + go?""",
      steps=[
          S("read_file", path="app/audit.py"),
          S("invoke_local", function="events-since", path="/audit?since=2026-11-01T00:00:00+00:00"),
          S("propose_plan", steps=["In a query string `+` means a space: restore it with `.replace(\" \", \"+\")` and return 400 for a bad date",
                                   "GET with a raw `+` and with `%2B` locally; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/audit.py", content=FUTURE + """from datetime import datetime

from py_serverless_kit import BadRequest


def since(event, ctx):
    raw = event.http.query.get("since", "").replace(" ", "+")
    try:
        start = datetime.fromisoformat(raw)
    except ValueError:
        raise BadRequest("since must be an ISO 8601 time") from None
    return {"since": start.isoformat()}
"""),
          S("invoke_local", function="events-since", path="/audit?since=2026-11-01T00:00:00+00:00"),
          S("invoke_local", function="events-since", path="/audit?since=2026-11-01T00:00:00%2B00:00"),
          S("validate"),
      ],
      final="""In URL query strings `+` is the encoding of a space, so `+00:00` arrives as ` 00:00`. That's standard decoding, not pskit-specific. The handler now puts the `+` back and returns 400 for anything that still isn't a valid time. The proper fix on the client side is to encode the value (`encodeURIComponent`), which sends `%2B`.

- Raw `+`: 200 `{"since": "2026-11-01T00:00:00+00:00"}`.
- `%2B`: same result.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 270 aws http, [[0] * n] * m aliasing
    B(270, provider="aws", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AWS("cinema-seats", "us-east-2") + """functions:
  book-seat:
    handler: app.seats.book
    events:
      - http: POST /seats
""",
          "app/__init__.py": "",
          "app/seats.py": FUTURE + """
def book(event, ctx):
    seat = event.http.json()
    hall = [[0] * 4] * 3
    hall[seat["row"]][seat["col"]] = 1
    return {"hall": hall}
""",
          "requirements.txt": ""}),
      user="I book row 0 seat 2 and the seat map shows seat 2 booked in every row! I only changed one row.",
      steps=[
          S("read_file", path="app/seats.py"),
          S("invoke_local", function="book-seat", method="POST", path="/seats", data={"row": 0, "col": 2}),
          S("propose_plan", steps=["Build each row separately: `[[0] * 4 for _ in range(3)]` (`* 3` repeats the same row list)",
                                   "Book row 0 seat 2 locally and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/seats.py", content=FUTURE + """
def book(event, ctx):
    seat = event.http.json()
    hall = [[0] * 4 for _ in range(3)]
    hall[seat["row"]][seat["col"]] = 1
    return {"hall": hall}
"""),
          S("invoke_local", function="book-seat", method="POST", path="/seats", data={"row": 0, "col": 2}),
          S("validate"),
      ],
      final="""`[[0] * 4] * 3` doesn't make three rows. It makes a list that holds **the same row three times**, so changing one changes "all" of them. The comprehension creates a new row each time.

- Before: `[[0,0,1,0], [0,0,1,0], [0,0,1,0]]`.
- After: `[[0,0,1,0], [0,0,0,0], [0,0,0,0]]`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 271 aws storage, guess_type returns a tuple
    B(271, provider="aws", stage="staging", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": AWS("asset-meta", "ap-northeast-1") + """functions:
  meta:
    handler: app.meta.handle
    events:
      - storage: site-assets
""",
          "app/__init__.py": "",
          "app/meta.py": FUTURE + """import mimetypes


def handle(event, ctx):
    return {r.key: mimetypes.guess_type(r.key) for r in event.records}
""",
          "requirements.txt": ""}),
      user="meta writes content type as [\"image/png\", null]. want \"image/png\"",
      steps=[
          S("read_file", path="app/meta.py"),
          S("invoke_local", function="meta", type="storage", data=[{"key": "logo.png"}, {"key": "data.bin"}]),
          S("propose_plan", steps=["Take element 0 of `guess_type()` (type, encoding), default `application/octet-stream`",
                                   "Invoke with logo.png and data.bin; validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/meta.py", content=FUTURE + """import mimetypes


def content_type(key):
    ctype, _encoding = mimetypes.guess_type(key)
    return ctype or "application/octet-stream"


def handle(event, ctx):
    return {r.key: content_type(r.key) for r in event.records}
"""),
          S("invoke_local", function="meta", type="storage", data=[{"key": "logo.png"}, {"key": "data.bin"}]),
          S("validate"),
      ],
      final="""`mimetypes.guess_type()` returns a `(type, encoding)` tuple, and a tuple becomes a JSON list. Now the handler takes the type and uses `application/octet-stream` when it is unknown.

- `logo.png`: `image/png`. `data.bin`: `application/octet-stream`.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 272 aws http, Node.js JSON.stringify return
    B(272, provider="aws", stage="prod", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": AWS("catalog-js", "us-west-2", "  runtime: nodejs20\n") + """functions:
  items:
    handler: src.items.list
    events:
      - http: GET /items
""",
          "src/items.js": """exports.list = async () => {
  const items = [{ id: 1, name: "pen" }];
  return JSON.stringify({ items });
};
"""}),
      user="Ported from Lambda, where I returned { statusCode, body: JSON.stringify(...) }. I dropped statusCode but kept the JSON.stringify. Now the frontend says items is undefined and the response is text/plain. What's the pskit way?",
      steps=[
          S("read_file", path="src/items.js"),
          S("invoke_local", function="items", path="/items"),
          S("search_docs", query="nodejs handler return plain value json",
            docs=[D("docs/nodejs.md", "handlers", start="export async function hello", end="// plain value -> JSON 200")]),
          S("propose_plan", steps=["Return the object itself; pskit serialises a plain value to JSON 200",
                                   "GET /items locally and validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/items.js", content="""exports.list = async () => {
  const items = [{ id: 1, name: "pen" }];
  return { items };
};
"""),
          S("invoke_local", function="items", path="/items"),
          S("validate"),
      ],
      final="""In pskit you return the value itself: a plain object becomes JSON with status 200 [docs/nodejs.md#handlers]. A string is sent as `text/plain`, so the frontend got a string, and `.items` of a string is `undefined`.

- Before: `content-type: text/plain` (the invoke output only pretty-prints the text; a browser gets a string).
- After: `content-type: application/json`, `{"items": [{"id": 1, "name": "pen"}]}`.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 273 gcp http, "".split(",") gives [""]
    B(273, provider="gcp", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: recipes\n" + GCP.format(region="europe-west1") + """functions:
  recipes:
    handler: app.recipes.search
    events:
      - http: GET /recipes
""",
          "app/__init__.py": "",
          "app/recipes.py": FUTURE + """RECIPES = [{"name": "dal", "tags": ["vegan"]}, {"name": "ramen", "tags": ["soup"]}]


def search(event, ctx):
    wanted = event.http.query.get("tags", "").split(",")
    hits = [r["name"] for r in RECIPES if all(t in r["tags"] for t in wanted)]
    return {"recipes": hits}
""",
          "requirements.txt": ""}),
      user="GET /recipes filters by a comma-separated tags parameter. With ?tags=vegan it works. Without tags (or with ?tags=) it should return every recipe, but it returns an empty list. Please fix the no-filter case.",
      steps=[
          S("read_file", path="app/recipes.py"),
          S("invoke_local", function="recipes", path="/recipes"),
          S("propose_plan", steps=["Drop empty parts after splitting: `\"\".split(\",\")` is `[\"\"]`, a filter for the tag `\"\"`",
                                   "GET /recipes and /recipes?tags=vegan locally; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/recipes.py", content=FUTURE + """RECIPES = [{"name": "dal", "tags": ["vegan"]}, {"name": "ramen", "tags": ["soup"]}]


def search(event, ctx):
    wanted = [t.strip() for t in event.http.query.get("tags", "").split(",") if t.strip()]
    hits = [r["name"] for r in RECIPES if all(t in r["tags"] for t in wanted)]
    return {"recipes": hits}
"""),
          S("invoke_local", function="recipes", path="/recipes"),
          S("invoke_local", function="recipes", path="/recipes?tags=vegan"),
          S("validate"),
      ],
      final="""Splitting an empty string gives `[""]`, a list with one empty tag. No recipe has the tag `""`, so nothing matched. Empty parts are now dropped, so no tags means no filter (`all()` of nothing is true).

- `/recipes`: `["dal", "ramen"]`. `?tags=vegan`: `["dal"]`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 274 gcp queue, Python repr instead of JSON
    B(274, provider="gcp", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: label-printer\n" + GCP.format(region="us-central1") + """functions:
  print-label:
    handler: app.labels.handle
    events:
      - queue: label-jobs
""",
          "app/__init__.py": "",
          "app/labels.py": FUTURE + """
def handle(event, ctx):
    return {"labels": [record.json()["sku"] for record in event.records]}
""",
          "requirements.txt": ""}),
      user="""json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
the producer is a python script that publishes str(job)""",
      steps=[
          S("read_file", path="app/labels.py"),
          S("invoke_local", function="print-label", type="queue", data=["{'sku': 'BOX-3'}"]),
          S("propose_plan", steps=["Accept messages already sent as a Python repr with `ast.literal_eval` (safe, literals only) when JSON parsing fails",
                                   "Fix the producer to publish `json.dumps(job)`",
                                   "Invoke with a repr message and a JSON message; validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/labels.py", content=FUTURE + """import ast
import json


def parse(record):
    text = record.text()
    try:
        return json.loads(text)
    except ValueError:
        return ast.literal_eval(text)  # old producers sent str(dict)


def handle(event, ctx):
    return {"labels": [parse(record)["sku"] for record in event.records]}
"""),
          S("invoke_local", function="print-label", type="queue", data=["{'sku': 'BOX-3'}", {"sku": "BOX-4"}]),
          S("validate"),
      ],
      final="""`str(job)` writes a Python repr with single quotes (`{'sku': 'BOX-3'}`), and that is not JSON. The real fix is in the producer: publish `json.dumps(job)`. So messages already in the queue still work, the handler falls back to `ast.literal_eval`, which reads Python literals only and never runs code.

- Repr and JSON messages: `{"labels": ["BOX-3", "BOX-4"]}`.
- validate (gcp, staging): valid.

Once the producer is fixed and the old messages are gone, you can remove the fallback."""),

    # ------------------------------------------------------------------ 275 gcp schedule, %d and %m swapped
    B(275, provider="gcp", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: holiday-mode\n" + GCP.format(region="europe-west3") + """functions:
  holiday:
    handler: app.holiday.run
    events:
      - schedule:
          cron: "0 0 * * *"
          input:
            start: "2026-12-24"
""",
          "app/__init__.py": "",
          "app/holiday.py": FUTURE + """from datetime import datetime


def run(event, ctx):
    start = datetime.strptime(event.data["start"], "%Y-%d-%m")
    return {"holiday_starts": start.date().isoformat()}
""",
          "requirements.txt": ""}),
      user="holiday function crash: ValueError: unconverted data remains: 4. input is 2026-12-24. with 2026-11-01 no crash but it give 2026-01-11 ??",
      steps=[
          S("read_file", path="app/holiday.py"),
          S("invoke_local", function="holiday", type="schedule"),
          S("propose_plan", steps=["The format has day and month swapped: use `%Y-%m-%d` (or `date.fromisoformat`)",
                                   "Run with 2026-12-24 locally and validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/holiday.py", content=FUTURE + """from datetime import date


def run(event, ctx):
    start = date.fromisoformat(event.data["start"])
    return {"holiday_starts": start.isoformat()}
"""),
          S("invoke_local", function="holiday", type="schedule"),
          S("validate"),
      ],
      final="""The format was `%Y-%d-%m`, day before month. `2026-11-01` was read as 11 January (wrong but no error). For `2026-12-24`, `%m` could only read `2` (there is no month 24), so the `4` was left over. The input is a normal ISO date, so `date.fromisoformat` reads it correctly.

- After: `{"holiday_starts": "2026-12-24"}`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 276 gcp http, prefix check for a redirect target
    B(276, provider="gcp", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: sso-return\n" + GCP.format(region="us-east1") + """functions:
  after-login:
    handler: app.sso.after_login
    events:
      - http: GET /after-login
""",
          "app/__init__.py": "",
          "app/sso.py": FUTURE + """from py_serverless_kit import BadRequest, Response

ALLOWED = "https://app.example.com"


def after_login(event, ctx):
    target = event.http.query.get("next", ALLOWED)
    if not target.startswith(ALLOWED):
        raise BadRequest("bad redirect")
    return Response.redirect(target)
""",
          "requirements.txt": ""}),
      user="Our after-login redirect is supposed to send users only back to https://app.example.com. A tester showed that next=https://app.example.com.attacker.example/ passes the check and redirects away from our site. Please make the check strict: same scheme and exact host only.",
      steps=[
          S("read_file", path="app/sso.py"),
          S("invoke_local", function="after-login", path="/after-login?next=https://app.example.com.attacker.example/"),
          S("propose_plan", steps=["Parse `next` with `urllib.parse.urlsplit` and require scheme `https` and host exactly `app.example.com`",
                                   "GET with the attacker URL (400) and a real app path (302) locally; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sso.py", content=FUTURE + """from urllib.parse import urlsplit

from py_serverless_kit import BadRequest, Response

HOME = "https://app.example.com/"


def after_login(event, ctx):
    target = event.http.query.get("next", HOME)
    parts = urlsplit(target)
    if parts.scheme != "https" or parts.hostname != "app.example.com":
        raise BadRequest("bad redirect")
    return Response.redirect(target)
"""),
          S("invoke_local", function="after-login", path="/after-login?next=https://app.example.com.attacker.example/"),
          S("invoke_local", function="after-login", path="/after-login?next=https://app.example.com/orders"),
          S("validate"),
      ],
      final="""`startswith("https://app.example.com")` is also true for `https://app.example.com.attacker.example/`, a different host: an open redirect. The handler now parses the URL and requires `https` and the exact host `app.example.com`.

- Attacker URL: before 302 to it, now 400 `bad redirect`.
- `https://app.example.com/orders`: 302 with `location` set [docs/handlers.md#returning-a-response].
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 277 azure http, average of an empty list
    B(277, provider="azure", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": AZ("grade-calc", "northeurope") + """functions:
  average:
    handler: app.grades.average
    events:
      - http: POST /grades/average
""",
          "app/__init__.py": "",
          "app/grades.py": FUTURE + """
def average(event, ctx):
    grades = event.http.json()["grades"]
    return {"average": sum(grades) / len(grades)}
""",
          "requirements.txt": ""}),
      user="""ZeroDivisionError: division by zero
POST /grades/average {"grades": []} -> 500. should be 400""",
      steps=[
          S("read_file", path="app/grades.py"),
          S("invoke_local", function="average", method="POST", path="/grades/average", data={"grades": []}),
          S("propose_plan", steps=["Raise `BadRequest` when the list is empty, before dividing",
                                   "POST an empty list (400) and [2, 3] (200) locally; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/grades.py", content=FUTURE + """from py_serverless_kit import BadRequest


def average(event, ctx):
    grades = event.http.json().get("grades") or []
    if not grades:
        raise BadRequest("grades must not be empty")
    return {"average": sum(grades) / len(grades)}
"""),
          S("invoke_local", function="average", method="POST", path="/grades/average", data={"grades": []}),
          S("invoke_local", function="average", method="POST", path="/grades/average", data={"grades": [2, 3]}),
          S("validate"),
      ],
      final="""`len([])` is 0, so the division failed, and an uncaught exception is a 500. An empty (or missing) list now raises `BadRequest` [docs/handlers.md#errors].

- `[]`: 400 `grades must not be empty`. `[2, 3]`: 200 `{"average": 2.5}`.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 278 azure queue, case-sensitive email dedupe
    B(278, provider="azure", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": AZ("mailing-list", "swedencentral") + """functions:
  collect:
    handler: app.collect.handle
    events:
      - queue: signups
""",
          "app/__init__.py": "",
          "app/collect.py": FUTURE + """
def handle(event, ctx):
    emails = set(record.json()["email"] for record in event.records)
    return {"unique": sorted(emails)}
""",
          "requirements.txt": ""}),
      user="I use a set to remove duplicate emails, but Ana@Example.com and ana@example.com are both in the list. Isn't a set supposed to remove duplicates?",
      steps=[
          S("read_file", path="app/collect.py"),
          S("invoke_local", function="collect", type="queue",
            data=[{"email": "Ana@Example.com"}, {"email": "ana@example.com "}, {"email": "li@example.com"}]),
          S("propose_plan", steps=["Normalise each email with `.strip().lower()` before adding it to the set",
                                   "Invoke with the two spellings of Ana; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/collect.py", content=FUTURE + """
def handle(event, ctx):
    emails = set(record.json()["email"].strip().lower() for record in event.records)
    return {"unique": sorted(emails)}
"""),
          S("invoke_local", function="collect", type="queue",
            data=[{"email": "Ana@Example.com"}, {"email": "ana@example.com "}, {"email": "li@example.com"}]),
          S("validate"),
      ],
      final="""A set does remove duplicates, but only exact ones. `"Ana@Example.com"` and `"ana@example.com "` (with a space) are different strings. Now each email is trimmed and lower-cased first.

- Before: 3 entries. After: `["ana@example.com", "li@example.com"]`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 279 azure schedule, minutes:seconds without padding
    B(279, provider="azure", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AZ("race-results", "francecentral") + """functions:
  results:
    handler: app.race.results
    events:
      - schedule:
          cron: "*/10 * * * *"
          input:
            times: {kim: 307, joe: 425}
""",
          "app/__init__.py": "",
          "app/race.py": FUTURE + """
def results(event, ctx):
    return {name: f"{secs // 60}:{secs % 60}" for name, secs in event.data["times"].items()}
""",
          "requirements.txt": ""}),
      user="race times print 5:7 instead of 5:07",
      steps=[
          S("read_file", path="app/race.py"),
          S("invoke_local", function="results", type="schedule"),
          S("propose_plan", steps=["Pad the seconds: `{secs % 60:02d}`",
                                   "Run with the configured input; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/race.py", content=FUTURE + """
def results(event, ctx):
    return {name: f"{secs // 60}:{secs % 60:02d}" for name, secs in event.data["times"].items()}
"""),
          S("invoke_local", function="results", type="schedule"),
          S("validate"),
      ],
      final="""`:02d` pads to two digits.

- Before: `kim 5:7`, `joe 7:5`. After: `5:07`, `7:05`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 280 azure http, bool accepted as an int
    B(280, provider="azure", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": AZ("basket-api", "eastus") + """functions:
  set-qty:
    handler: app.basket.set_qty
    events:
      - http: PUT /basket/{sku}
""",
          "app/__init__.py": "",
          "app/basket.py": FUTURE + """from py_serverless_kit import UnprocessableEntity


def set_qty(event, ctx):
    qty = event.http.json().get("qty")
    if not isinstance(qty, int) or qty < 0:
        raise UnprocessableEntity("qty must be a non-negative integer", details={"field": "qty"})
    return {"sku": event.http.path_params["sku"], "qty": qty}
""",
          "requirements.txt": ""}),
      user="PUT /basket/{sku} must only accept a non-negative integer qty. A buggy client sent {\"qty\": true} and we stored quantity 1. JSON booleans must be rejected with the same 422 as other wrong types.",
      steps=[
          S("read_file", path="app/basket.py"),
          S("invoke_local", function="set-qty", method="PUT", path="/basket/MUG", data={"qty": True}),
          S("propose_plan", steps=["Reject `bool` explicitly: in Python `True` is an `int`, so `isinstance(True, int)` passes",
                                   "PUT qty true (422) and qty 3 (200) locally; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/basket.py", content=FUTURE + """from py_serverless_kit import UnprocessableEntity


def set_qty(event, ctx):
    qty = event.http.json().get("qty")
    if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0:
        raise UnprocessableEntity("qty must be a non-negative integer", details={"field": "qty"})
    return {"sku": event.http.path_params["sku"], "qty": qty}
"""),
          S("invoke_local", function="set-qty", method="PUT", path="/basket/MUG", data={"qty": True}),
          S("invoke_local", function="set-qty", method="PUT", path="/basket/MUG", data={"qty": 3}),
          S("validate"),
      ],
      final="""`bool` is a subclass of `int` in Python, so `isinstance(True, int)` is `True`, and `True` passed the check (and counts as 1). The check now rejects booleans first.

- `{"qty": true}`: was 200, now 422 `qty must be a non-negative integer` [docs/handlers.md#errors].
- `{"qty": 3}`: 200.
- validate (azure): valid."""),
]
