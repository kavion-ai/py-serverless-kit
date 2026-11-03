"""Category D (fix a handler bug), batch 13. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    # ------------------------------------------------------------------ 241 onprem http, 0 treated as missing
    B(241, provider="onprem", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: quotes\n" + ONPREM.format(port=8631) + """functions:
  quote:
    handler: app.quote.make_quote
    events:
      - http: POST /quotes
""",
          "app/__init__.py": "",
          "app/quote.py": FUTURE + """DEFAULT_DISCOUNT = 10


def make_quote(event, ctx):
    body = event.http.json()
    discount = body.get("discount") or DEFAULT_DISCOUNT
    price = body["price"] * (100 - discount) / 100
    return {"discount": discount, "price": price}
""",
          "requirements.txt": ""}),
      user="POST /quotes should use a 10% discount only when the client doesn't send one. Sales sends \"discount\": 0 for list-price quotes, but the quote still comes back with 10% off. Please respect an explicit 0.",
      steps=[
          S("read_file", path="app/quote.py"),
          S("invoke_local", function="quote", method="POST", path="/quotes", data={"price": 200, "discount": 0}),
          S("propose_plan", steps=["Use the default only when the key is missing or null: `body.get(\"discount\")` then `if discount is None`",
                                   "POST with discount 0 (no discount) and without discount (10%); validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/quote.py", content=FUTURE + """DEFAULT_DISCOUNT = 10


def make_quote(event, ctx):
    body = event.http.json()
    discount = body.get("discount")
    if discount is None:
        discount = DEFAULT_DISCOUNT
    price = body["price"] * (100 - discount) / 100
    return {"discount": discount, "price": price}
"""),
          S("invoke_local", function="quote", method="POST", path="/quotes", data={"price": 200, "discount": 0}),
          S("invoke_local", function="quote", method="POST", path="/quotes", data={"price": 200}),
          S("validate"),
      ],
      final="""`x or DEFAULT` replaces every *falsy* value, and `0` is falsy, so an explicit 0 became 10. Now the default is used only when `discount` is missing or `null`.

- `discount: 0`: was 180.0, now `{"discount": 0, "price": 200.0}`.
- no discount: `{"discount": 10, "price": 180.0}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 242 onprem http, dates compared as text
    B(242, provider="onprem", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: vet-visits\n" + ONPREM.format(port=8632) + """functions:
  last-visit:
    handler: app.visits.last_visit
    events:
      - http: POST /visits/last
""",
          "app/__init__.py": "",
          "app/visits.py": FUTURE + """
def last_visit(event, ctx):
    dates = event.http.json()["dates"]
    return {"last": max(dates)}
""",
          "requirements.txt": ""}),
      user="dates are like 05/11/2026 (day/month). last visit say 28/02/2026 but 05/11/2026 is newer",
      steps=[
          S("read_file", path="app/visits.py"),
          S("invoke_local", function="last-visit", method="POST", path="/visits/last",
            data={"dates": ["05/11/2026", "28/02/2026", "14/07/2025"]}),
          S("propose_plan", steps=["Parse each date with `datetime.strptime(d, \"%d/%m/%Y\")` and take `max` of the real dates",
                                   "POST the three dates locally and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/visits.py", content=FUTURE + """from datetime import datetime

FMT = "%d/%m/%Y"


def last_visit(event, ctx):
    dates = event.http.json()["dates"]
    latest = max(dates, key=lambda d: datetime.strptime(d, FMT))
    return {"last": latest}
"""),
          S("invoke_local", function="last-visit", method="POST", path="/visits/last",
            data={"dates": ["05/11/2026", "28/02/2026", "14/07/2025"]}),
          S("validate"),
      ],
      final="""`max()` on strings compares them letter by letter, so `"28/..."` beats `"05/..."` because `2 > 0`. The day is compared first, not the year. Now each date is parsed with `%d/%m/%Y` and the real dates are compared. The answer keeps the original text.

- Before: `"28/02/2026"`. After: `"05/11/2026"`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 243 onprem http, list.remove while iterating
    B(243, provider="onprem", stage="prod", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: coupon-clean\n" + ONPREM.format(port=8633) + """functions:
  valid-coupons:
    handler: app.coupons.valid
    events:
      - http: POST /coupons/valid
""",
          "app/__init__.py": "",
          "app/coupons.py": FUTURE + """
def valid(event, ctx):
    coupons = event.http.json()["coupons"]
    for c in coupons:
        if c["expired"]:
            coupons.remove(c)
    return {"valid": [c["code"] for c in coupons]}
""",
          "requirements.txt": ""}),
      user="valid-coupons keeps an expired one when two expired are next to each other",
      steps=[
          S("read_file", path="app/coupons.py"),
          S("invoke_local", function="valid-coupons", method="POST", path="/coupons/valid",
            data={"coupons": [{"code": "A", "expired": True}, {"code": "B", "expired": True}, {"code": "C", "expired": False}]}),
          S("propose_plan", steps=["Build a new filtered list instead of `remove()` inside the loop",
                                   "POST two adjacent expired coupons; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/coupons.py", content=FUTURE + """
def valid(event, ctx):
    coupons = event.http.json()["coupons"]
    return {"valid": [c["code"] for c in coupons if not c["expired"]]}
"""),
          S("invoke_local", function="valid-coupons", method="POST", path="/coupons/valid",
            data={"coupons": [{"code": "A", "expired": True}, {"code": "B", "expired": True}, {"code": "C", "expired": False}]}),
          S("validate"),
      ],
      final="""Removing from a list while looping over it shifts the next item into the current index, so the loop skips it: `A` was removed and `B` was never checked. A comprehension builds a new list.

- Before: `["B", "C"]`. After: `["C"]`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 244 onprem queue, json.dumps of an already-JSON body
    B(244, provider="onprem", stage="dev", mode="ask", page="Logs", persona="beginner",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: event-archive\n" + ONPREM.format(port=8634) + """functions:
  archive:
    handler: app.archive.handle
    events:
      - queue: app-events
""",
          "app/__init__.py": "",
          "app/archive.py": FUTURE + """import json


def handle(event, ctx):
    lines = []
    for record in event.records:
        lines.append(json.dumps(record.body))
    return {"jsonl": lines}
""",
          "requirements.txt": ""}),
      user="The archive file is full of backslashes, like \"{\\\"event\\\": \\\"signup\\\"}\", and our importer can't read it. I only want to save each message as one JSON line. What did I do wrong?",
      steps=[
          S("read_file", path="app/archive.py"),
          S("invoke_local", function="archive", type="queue", data=[{"event": "signup", "user": 7}]),
          S("propose_plan", steps=["Parse the body with `record.json()` and then `json.dumps` it once, so the text isn't encoded twice",
                                   "Invoke with one message; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/archive.py", content=FUTURE + """import json


def handle(event, ctx):
    lines = []
    for record in event.records:
        lines.append(json.dumps(record.json(), separators=(",", ":")))
    return {"jsonl": lines}
"""),
          S("invoke_local", function="archive", type="queue", data=[{"event": "signup", "user": 7}]),
          S("validate"),
      ],
      final="""The message body is already JSON **text** [docs/handlers.md#record]. `json.dumps()` on a string wraps it in quotes and escapes every `"` with a backslash. Now the body is parsed with `record.json()` and dumped once, so each line is plain JSON.

- Before: `"{\\"event\\": \\"signup\\", \\"user\\": 7}"`.
- After: `{"event":"signup","user":7}` (shown escaped inside the invoke output's own JSON).
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 245 onprem http, bytes digest in JSON
    B(245, provider="onprem", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: file-check\n" + ONPREM.format(port=8635) + """functions:
  checksum:
    handler: app.check.checksum
    events:
      - http: POST /checksum
""",
          "app/__init__.py": "",
          "app/check.py": FUTURE + """import hashlib


def checksum(event, ctx):
    digest = hashlib.sha256(event.http.body).digest()
    return {"sha256": digest, "bytes": len(event.http.body)}
""",
          "requirements.txt": ""}),
      user="POST /checksum should return the SHA-256 of the uploaded body as the usual 64-character hex string, so clients can compare it with `sha256sum`. Right now the sha256 field is a short string of garbage characters. Test with the body `hello`.",
      steps=[
          S("read_file", path="app/check.py"),
          S("invoke_local", function="checksum", method="POST", path="/checksum", data="hello"),
          S("propose_plan", steps=["Return `hexdigest()` (a hex str) instead of `digest()` (raw bytes)",
                                   "POST `hello` locally and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/check.py", content=FUTURE + """import hashlib


def checksum(event, ctx):
    digest = hashlib.sha256(event.http.body).hexdigest()
    return {"sha256": digest, "bytes": len(event.http.body)}
"""),
          S("invoke_local", function="checksum", method="POST", path="/checksum", data="hello"),
          S("validate"),
      ],
      final="""`digest()` returns 32 raw **bytes**. When pskit writes bytes into JSON it decodes them as UTF-8 and replaces what isn't valid text, so you got garbage. `hexdigest()` returns the 64-character hex string that `sha256sum` prints.

- After: `"sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"`, `"bytes": 5`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 246 onprem storage, stem of a double extension
    B(246, provider="onprem", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: backup-catalog\n" + ONPREM.format(port=8636) + """functions:
  catalog:
    handler: app.catalog.handle
    events:
      - storage: backups
""",
          "app/__init__.py": "",
          "app/catalog.py": FUTURE + """from pathlib import PurePosixPath


def handle(event, ctx):
    names = [PurePosixPath(r.key).stem for r in event.records]
    return {"backups": names}
""",
          "requirements.txt": ""}),
      user="backup name for db-2026-11-01.tar.gz show db-2026-11-01.tar. i want only db-2026-11-01",
      steps=[
          S("read_file", path="app/catalog.py"),
          S("invoke_local", function="catalog", type="storage", data=[{"key": "nightly/db-2026-11-01.tar.gz"}]),
          S("propose_plan", steps=["Cut every suffix: take the file `name` and split it at the first dot",
                                   "Invoke with a .tar.gz key; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/catalog.py", content=FUTURE + """from pathlib import PurePosixPath


def handle(event, ctx):
    names = [PurePosixPath(r.key).name.split(".", 1)[0] for r in event.records]
    return {"backups": names}
"""),
          S("invoke_local", function="catalog", type="storage", data=[{"key": "nightly/db-2026-11-01.tar.gz"}]),
          S("validate"),
      ],
      final="""`.stem` removes only the **last** suffix (`.gz`), so `.tar` stayed. Now the handler takes the file name and cuts it at the first dot.

- Before: `db-2026-11-01.tar`. After: `db-2026-11-01`.
- validate (onprem, prod): valid.

Names with a dot in the middle (`db.v2.tar.gz`) would also be cut at the first dot; tell me if you have those."""),

    # ------------------------------------------------------------------ 247 onprem http, trailing comma makes a tuple
    B(247, provider="onprem", stage="dev", mode="auto", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: weather-api\n" + ONPREM.format(port=8637) + """functions:
  today:
    handler: app.weather.today
    events:
      - http: GET /weather/today
""",
          "app/__init__.py": "",
          "app/weather.py": FUTURE + """
def today(event, ctx):
    city = event.http.query.get("city", "Oslo")
    return {"city": city, "temp_c": 4},
""",
          "requirements.txt": ""}),
      user="""TypeError: Cannot read properties of undefined (reading 'temp_c')
frontend. the api returns [{"city": "Oslo", "temp_c": 4}] - a list?""",
      steps=[
          S("read_file", path="app/weather.py"),
          S("invoke_local", function="today", path="/weather/today"),
          S("propose_plan", steps=["Remove the trailing comma after the dict: it makes the return value a one-item tuple"]),
          S("write_file", path="app/weather.py", content=FUTURE + """
def today(event, ctx):
    city = event.http.query.get("city", "Oslo")
    return {"city": city, "temp_c": 4}
"""),
          S("invoke_local", function="today", path="/weather/today"),
          S("validate"),
      ],
      final="""The trailing comma in `return {...},` makes a **tuple** with one item. pskit only treats `(body, status)` and `(body, status, headers)` tuples specially. A one-item tuple is sent as JSON, which is a list [docs/handlers.md#returning-a-response]. I removed the comma.

- Before: `[{"city": "Oslo", "temp_c": 4}]`.
- After: `{"city": "Oslo", "temp_c": 4}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 248 onprem schedule, Python 2 except syntax
    B(248, provider="onprem", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": "service: legacy-sync\n" + ONPREM.format(port=8638) + """functions:
  sync:
    handler: app.sync.run
    events:
      - schedule:
          rate: 1 hour
          input: {limit: "50"}
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """
def run(event, ctx):
    try:
        limit = int(event.data["limit"])
    except ValueError, KeyError:
        limit = 100
    return {"limit": limit}
""",
          "requirements.txt": ""}),
      user="""SyntaxError: multiple exception types must be parenthesized
ported this from an old python 2 cron script""",
      steps=[
          S("read_file", path="app/sync.py"),
          S("invoke_local", function="sync", type="schedule"),
          S("propose_plan", steps=["Write the two exception types as a tuple: `except (ValueError, KeyError):`",
                                   "Run the schedule with its input; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sync.py", content=FUTURE + """
def run(event, ctx):
    try:
        limit = int(event.data["limit"])
    except (ValueError, KeyError):
        limit = 100
    return {"limit": limit}
"""),
          S("invoke_local", function="sync", type="schedule"),
          S("validate"),
      ],
      final="""`except ValueError, KeyError:` is Python 2 syntax. In Python 3 several exception types must be a tuple: `except (ValueError, KeyError):`. The file didn't even compile, so the function could not be loaded.

- After: `{"limit": 50}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 249 aws http, split(" ") on double spaces
    B(249, provider="aws", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AWS("essay-tools") + """functions:
  word-count:
    handler: app.words.count
    events:
      - http: POST /words/count
""",
          "app/__init__.py": "",
          "app/words.py": FUTURE + """
def count(event, ctx):
    text = event.http.text()
    return {"words": len(text.split(" "))}
""",
          "requirements.txt": ""}),
      user="my word counter says 4 words for \"hello  world\\n\\nbye\". it should be 3. is it the spaces?",
      steps=[
          S("read_file", path="app/words.py"),
          S("invoke_local", function="word-count", method="POST", path="/words/count", data="hello  world\n\nbye "),
          S("propose_plan", steps=["Use `text.split()` without an argument: it splits on any run of whitespace and drops empty parts",
                                   "POST the same text locally and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/words.py", content=FUTURE + """
def count(event, ctx):
    text = event.http.text()
    return {"words": len(text.split())}
"""),
          S("invoke_local", function="word-count", method="POST", path="/words/count", data="hello  world\n\nbye "),
          S("validate"),
      ],
      final="""Yes. `split(" ")` cuts at every single space, so two spaces in a row give an empty "word", and a newline isn't a separator at all. `split()` with no argument splits on any whitespace (spaces, newlines, tabs) and skips empty parts.

- Before: 4 for `hello  world\\n\\nbye ` (with a trailing space).
- After: 3.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 250 aws queue, float equality
    B(250, provider="aws", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": AWS("reconcile", "eu-west-1") + """functions:
  reconcile:
    handler: app.recon.handle
    events:
      - queue: payments
""",
          "app/__init__.py": "",
          "app/recon.py": FUTURE + """
def handle(event, ctx):
    mismatched = []
    for record in event.records:
        inv = record.json()
        if sum(inv["payments"]) != inv["total"]:
            mismatched.append(inv["invoice"])
    return {"mismatched": mismatched}
""",
          "requirements.txt": ""}),
      user="The reconcile worker flags invoices as mismatched even when the payments add up. Example: invoice INV-9 has total 0.3 and two payments 0.1 and 0.2, and it is reported as mismatched. Amounts arrive as JSON numbers with at most 2 decimals. Fix the comparison please.",
      steps=[
          S("read_file", path="app/recon.py"),
          S("invoke_local", function="reconcile", type="queue",
            data=[{"invoice": "INV-9", "total": 0.3, "payments": [0.1, 0.2]}]),
          S("propose_plan", steps=["Compare in whole cents: `round(x * 100)` for the payments and the total",
                                   "Invoke with INV-9; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/recon.py", content=FUTURE + """
def cents(amount):
    return round(amount * 100)


def handle(event, ctx):
    mismatched = []
    for record in event.records:
        inv = record.json()
        if sum(cents(p) for p in inv["payments"]) != cents(inv["total"]):
            mismatched.append(inv["invoice"])
    return {"mismatched": mismatched}
"""),
          S("invoke_local", function="reconcile", type="queue",
            data=[{"invoice": "INV-9", "total": 0.3, "payments": [0.1, 0.2]}]),
          S("validate"),
      ],
      final="""`0.1 + 0.2` is `0.30000000000000004` as a float, so `!= 0.3` is true. With at most 2 decimals, comparing whole cents is exact: each amount becomes `round(x * 100)` before summing.

- Before: `{"mismatched": ["INV-9"]}`.
- After: `{"mismatched": []}`.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 251 aws http, sort key on a None name
    B(251, provider="aws", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": AWS("crm-api", "us-west-2") + """functions:
  contacts:
    handler: app.contacts.list_contacts
    events:
      - http: GET /contacts
""",
          "app/__init__.py": "",
          "app/contacts.py": FUTURE + """CONTACTS = [{"name": "bo"}, {"name": None}, {"name": "Al"}]


def list_contacts(event, ctx):
    names = sorted((c["name"] for c in CONTACTS), key=str.lower)
    return {"contacts": names}
""",
          "requirements.txt": ""}),
      user="""TypeError: descriptor 'lower' for 'str' objects doesn't apply to a 'NoneType' object
GET /contacts, started after an import with some empty names""",
      steps=[
          S("read_file", path="app/contacts.py"),
          S("invoke_local", function="contacts", path="/contacts"),
          S("propose_plan", steps=["Sort with a key that handles `None`: `(c or \"\").lower()`, so nameless contacts go first instead of crashing",
                                   "GET /contacts locally and validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/contacts.py", content=FUTURE + """CONTACTS = [{"name": "bo"}, {"name": None}, {"name": "Al"}]


def list_contacts(event, ctx):
    names = sorted((c["name"] for c in CONTACTS), key=lambda n: (n or "").lower())
    return {"contacts": names}
"""),
          S("invoke_local", function="contacts", path="/contacts"),
          S("validate"),
      ],
      final="""`key=str.lower` calls `str.lower(None)` for the contact without a name, and that fails. The key now treats `None` as `""`, so those contacts come first and the rest sort case-insensitively.

- After: 200, `{"contacts": [null, "Al", "bo"]}`.
- validate (aws, staging): valid.

If nameless contacts shouldn't be listed at all, filter them out instead; say which you prefer."""),

    # ------------------------------------------------------------------ 252 aws http, Node.js missing await
    B(252, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": AWS("profile-js", "eu-central-1", "  runtime: nodejs20\n") + """functions:
  profile:
    handler: src.profile.get
    events:
      - http: GET /profile/{id}
""",
          "src/profile.js": """async function loadUser(id) {
  return { id, name: "Mara", plan: "team" };
}

exports.get = async (event) => {
  const user = loadUser(event.http.pathParams.id);
  return { name: user.name, plan: user.plan };
};
"""}),
      user="Coming from Lambda + Node. GET /profile/{id} returns {} even though loadUser returns the user. Same code worked in my old handler... I think. What's wrong?",
      steps=[
          S("read_file", path="src/profile.js"),
          S("invoke_local", function="profile", path="/profile/u1"),
          S("propose_plan", steps=["`await` the async `loadUser(...)` call: without it `user` is a Promise",
                                   "GET /profile/u1 locally and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/profile.js", content="""async function loadUser(id) {
  return { id, name: "Mara", plan: "team" };
}

exports.get = async (event) => {
  const user = await loadUser(event.http.pathParams.id);
  return { name: user.name, plan: user.plan };
};
"""),
          S("invoke_local", function="profile", path="/profile/u1"),
          S("validate"),
      ],
      final="""`loadUser` is `async`, so calling it returns a **Promise**. Without `await`, `user.name` and `user.plan` are `undefined`, and JSON drops undefined fields, which leaves `{}`. pskit awaits async handlers [docs/nodejs.md#handlers], but your handler has to await its own calls.

- Before: `{}`.
- After: `{"name": "Mara", "plan": "team"}`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 253 gcp http, substring check instead of a set
    B(253, provider="gcp", stage="prod", mode="ask", page="Logs", persona="terse_expert",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: listing\n" + GCP.format(region="europe-west1") + """functions:
  listing:
    handler: app.listing.listing
    events:
      - http: GET /listing
""",
          "app/__init__.py": "",
          "app/listing.py": FUTURE + """from py_serverless_kit import BadRequest

ROWS = [{"name": "b", "date": "2026-10-02"}, {"name": "a", "date": "2026-10-09"}]


def listing(event, ctx):
    sort = event.http.query.get("sort", "name")
    if sort not in "name,date":
        raise BadRequest("sort must be name or date")
    return {"rows": sorted(ROWS, key=lambda r: r[sort])}
""",
          "requirements.txt": ""}),
      user="GET /listing?sort=am -> 500 KeyError 'am'. should be 400",
      steps=[
          S("read_file", path="app/listing.py"),
          S("invoke_local", function="listing", path="/listing?sort=am"),
          S("propose_plan", steps=["Check membership in a set `{\"name\", \"date\"}`; `in \"name,date\"` is a substring test",
                                   "GET ?sort=am (400) and ?sort=date (200); validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/listing.py", content=FUTURE + """from py_serverless_kit import BadRequest

ROWS = [{"name": "b", "date": "2026-10-02"}, {"name": "a", "date": "2026-10-09"}]
SORTS = {"name", "date"}


def listing(event, ctx):
    sort = event.http.query.get("sort", "name")
    if sort not in SORTS:
        raise BadRequest("sort must be name or date")
    return {"rows": sorted(ROWS, key=lambda r: r[sort])}
"""),
          S("invoke_local", function="listing", path="/listing?sort=am"),
          S("invoke_local", function="listing", path="/listing?sort=date"),
          S("validate"),
      ],
      final="""`"am" in "name,date"` is a substring test, and `n-am-e` contains `am`. A set checks for whole values.

- `?sort=am`: 400 `sort must be name or date`. `?sort=date`: 200.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 254 gcp queue, int(price * 100) truncation
    B(254, provider="gcp", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: charge-worker\n" + GCP.format(region="us-central1") + """functions:
  charge:
    handler: app.charge.handle
    events:
      - queue: charges
""",
          "app/__init__.py": "",
          "app/charge.py": FUTURE + """
def handle(event, ctx):
    charged = []
    for record in event.records:
        order = record.json()
        charged.append({"order": order["id"], "cents": int(order["price"] * 100)})
    return {"charged": charged}
""",
          "requirements.txt": ""}),
      user="customer pay 19.99 but payment provider get 1998 cents. we lose 1 cent each time lol",
      steps=[
          S("read_file", path="app/charge.py"),
          S("invoke_local", function="charge", type="queue", data=[{"id": "o-5", "price": 19.99}]),
          S("propose_plan", steps=["Use `round(price * 100)` instead of `int(...)`, which cuts off the decimals",
                                   "Invoke with price 19.99; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/charge.py", content=FUTURE + """
def handle(event, ctx):
    charged = []
    for record in event.records:
        order = record.json()
        charged.append({"order": order["id"], "cents": round(order["price"] * 100)})
    return {"charged": charged}
"""),
          S("invoke_local", function="charge", type="queue", data=[{"id": "o-5", "price": 19.99}]),
          S("validate"),
      ],
      final="""As a float, `19.99 * 100` is `1998.9999999999998`, and `int()` cuts off the decimals, which gives `1998`. `round()` goes to the nearest whole number, `1999`.

- Before: `"cents": 1998`. After: `"cents": 1999`.
- validate (gcp): valid.

Best of all is if the shop sends cents (integers) in the message, so no float is involved."""),

    # ------------------------------------------------------------------ 255 gcp schedule, str.replace result discarded
    B(255, provider="gcp", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: sitemap\n" + GCP.format(region="europe-west4") + """functions:
  slugs:
    handler: app.slugs.run
    events:
      - schedule:
          rate: 1 day
          input:
            titles: ["Summer Sale", "New Arrivals"]
""",
          "app/__init__.py": "",
          "app/slugs.py": FUTURE + """
def run(event, ctx):
    slugs = []
    for title in event.data["titles"]:
        slug = title.lower()
        slug.replace(" ", "-")
        slugs.append(slug)
    return {"slugs": slugs}
""",
          "requirements.txt": ""}),
      user="my slugs still have spaces: \"summer sale\". I do call replace(\" \", \"-\")! the lower() part works",
      steps=[
          S("read_file", path="app/slugs.py"),
          S("invoke_local", function="slugs", type="schedule"),
          S("propose_plan", steps=["Assign the result: `slug = slug.replace(\" \", \"-\")` (strings never change in place)",
                                   "Run the schedule with its input; validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/slugs.py", content=FUTURE + """
def run(event, ctx):
    slugs = []
    for title in event.data["titles"]:
        slug = title.lower().replace(" ", "-")
        slugs.append(slug)
    return {"slugs": slugs}
"""),
          S("invoke_local", function="slugs", type="schedule"),
          S("validate"),
      ],
      final="""Python strings can't be changed in place. `replace()` returns a **new** string, and your code threw it away. `lower()` worked because you assigned its result. Now both are chained and assigned.

- Before: `["summer sale", "new arrivals"]`.
- After: `["summer-sale", "new-arrivals"]`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 256 gcp storage, split(".")[1] as the extension
    B(256, provider="gcp", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: doc-router\n" + GCP.format(region="us-west1") + """functions:
  route-doc:
    handler: app.router.handle
    events:
      - storage: inbox-docs
""",
          "app/__init__.py": "",
          "app/router.py": FUTURE + """QUEUES = {"pdf": "pdf-render", "docx": "word-convert"}


def handle(event, ctx):
    routed = {}
    for record in event.records:
        ext = record.key.split(".")[1]
        routed[record.key] = QUEUES.get(ext, "manual-review")
    return routed
""",
          "requirements.txt": ""}),
      user="route-doc decides where an uploaded document goes by its extension. Files like contract.final.pdf end up in manual-review instead of pdf-render, and a file without any extension (README) crashes the function. Please route by the real (last) extension and send files without one to manual-review.",
      steps=[
          S("read_file", path="app/router.py"),
          S("invoke_local", function="route-doc", type="storage", data=[{"key": "contract.final.pdf"}, {"key": "README"}]),
          S("propose_plan", steps=["Take the last suffix with `os.path.splitext(key)[1]` (empty when there is none), lower-cased and without the dot",
                                   "Invoke with contract.final.pdf and README; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/router.py", content=FUTURE + """import os

QUEUES = {"pdf": "pdf-render", "docx": "word-convert"}


def handle(event, ctx):
    routed = {}
    for record in event.records:
        ext = os.path.splitext(record.key)[1].lstrip(".").lower()
        routed[record.key] = QUEUES.get(ext, "manual-review")
    return routed
"""),
          S("invoke_local", function="route-doc", type="storage", data=[{"key": "contract.final.pdf"}, {"key": "README"}]),
          S("validate"),
      ],
      final="""`key.split(".")[1]` is the part after the **first** dot: `final` for `contract.final.pdf`. For `README` there is no index 1, so it raised `IndexError`. `os.path.splitext()` returns the last extension, or `""` when there is none.

- Before: `IndexError: list index out of range`.
- After: `contract.final.pdf` → `pdf-render`, `README` → `manual-review`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 257 azure http, explicit null for a list
    B(257, provider="azure", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AZ("blog-api", "westeurope") + """functions:
  create-post:
    handler: app.posts.create
    events:
      - http: POST /posts
""",
          "app/__init__.py": "",
          "app/posts.py": FUTURE + """
def create(event, ctx):
    post = event.http.json()
    tags = [t.lower() for t in post.get("tags", [])]
    return {"title": post["title"], "tags": tags}, 201
""",
          "requirements.txt": ""}),
      user="""TypeError: 'NoneType' object is not iterable
create-post, the editor sends "tags": null when there are no tags. I have a default [] there?""",
      steps=[
          S("read_file", path="app/posts.py"),
          S("invoke_local", function="create-post", method="POST", path="/posts", data={"title": "Hello", "tags": None}),
          S("propose_plan", steps=["Use `post.get(\"tags\") or []`: the `.get()` default applies only when the key is missing, not when it is null",
                                   "POST with `tags: null` locally and validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/posts.py", content=FUTURE + """
def create(event, ctx):
    post = event.http.json()
    tags = [t.lower() for t in (post.get("tags") or [])]
    return {"title": post["title"], "tags": tags}, 201
"""),
          S("invoke_local", function="create-post", method="POST", path="/posts", data={"title": "Hello", "tags": None}),
          S("validate"),
      ],
      final="""The default of `.get("tags", [])` is used only when the key is **missing**. Your editor sends the key with the value `null`, so you got `None`. `post.get("tags") or []` covers both cases.

- After: 201, `{"title": "Hello", "tags": []}`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 258 azure queue, decimal comma
    B(258, provider="azure", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": AZ("scale-readings", "germanywestcentral") + """functions:
  weigh:
    handler: app.weigh.handle
    events:
      - queue: scale-events
""",
          "app/__init__.py": "",
          "app/weigh.py": FUTURE + """
def handle(event, ctx):
    total = 0.0
    for record in event.records:
        total += float(record.json()["kg"])
    return {"total_kg": round(total, 3)}
""",
          "requirements.txt": ""}),
      user="ValueError could not convert string to float: '1,5'. the scales in germany send kg with comma",
      steps=[
          S("read_file", path="app/weigh.py"),
          S("invoke_local", function="weigh", type="queue", data=[{"kg": "1,5"}, {"kg": "2.25"}]),
          S("propose_plan", steps=["Replace a decimal comma with a dot before `float()` (strings only; numbers pass through)",
                                   "Invoke with `1,5` and `2.25`; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/weigh.py", content=FUTURE + """
def to_kg(value):
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    return float(value)


def handle(event, ctx):
    total = sum(to_kg(record.json()["kg"]) for record in event.records)
    return {"total_kg": round(total, 3)}
"""),
          S("invoke_local", function="weigh", type="queue", data=[{"kg": "1,5"}, {"kg": "2.25"}]),
          S("validate"),
      ],
      final="""`float()` only accepts a dot as the decimal sign. The new `to_kg` turns `"1,5"` into `"1.5"` first, and numbers are passed through as they are.

- Before: `ValueError: could not convert string to float: '1,5'`.
- After: `{"total_kg": 3.75}`.
- validate (azure): valid.

Don't send thousands separators (`1.250,5`); this simple fix doesn't handle them."""),

    # ------------------------------------------------------------------ 259 azure schedule, datetime vs date
    B(259, provider="azure", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AZ("trial-expiry", "eastus") + """functions:
  expire:
    handler: app.trials.expire
    events:
      - schedule:
          cron: "0 1 * * *"
          input:
            now: "2026-11-01T01:00:00+00:00"
            trials: {acme: "2026-10-30", globex: "2026-11-20"}
""",
          "app/__init__.py": "",
          "app/trials.py": FUTURE + """from datetime import date, datetime


def expire(event, ctx):
    now = datetime.fromisoformat(event.data["now"])
    expired = [name for name, end in event.data["trials"].items() if date.fromisoformat(end) < now]
    return {"expired": expired}
""",
          "requirements.txt": ""}),
      user="""TypeError: can't compare datetime.datetime to datetime.date
expire job, every night""",
      steps=[
          S("read_file", path="app/trials.py"),
          S("invoke_local", function="expire", type="schedule"),
          S("propose_plan", steps=["Compare dates with dates: use `now.date()` on the left side",
                                   "Run the schedule with its input; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/trials.py", content=FUTURE + """from datetime import date, datetime


def expire(event, ctx):
    today = datetime.fromisoformat(event.data["now"]).date()
    expired = [name for name, end in event.data["trials"].items() if date.fromisoformat(end) < today]
    return {"expired": expired}
"""),
          S("invoke_local", function="expire", type="schedule"),
          S("validate"),
      ],
      final="""`now` is a `datetime` (date + time) and the trial end is a `date`. Python won't compare the two. `now.date()` turns the time stamp into a date first.

- After: `{"expired": ["acme"]}`.
- validate (azure, staging): valid.

Timer triggers on Azure run in UTC [docs/events.md#schedule], so `now.date()` is the UTC date."""),

    # ------------------------------------------------------------------ 260 azure http, join on ints
    B(260, provider="azure", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": AZ("lottery", "uksouth") + """functions:
  draw:
    handler: app.lottery.draw
    events:
      - http: GET /draw
""",
          "app/__init__.py": "",
          "app/lottery.py": FUTURE + """NUMBERS = [4, 8, 15, 16, 23, 42]


def draw(event, ctx):
    return f"Numbers: {', '.join(NUMBERS)}"
""",
          "requirements.txt": ""}),
      user="draw 500: sequence item 0: expected str instance, int found",
      steps=[
          S("read_file", path="app/lottery.py"),
          S("invoke_local", function="draw", path="/draw"),
          S("propose_plan", steps=["Convert the numbers first: `', '.join(str(n) for n in NUMBERS)`",
                                   "GET /draw locally and validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/lottery.py", content=FUTURE + """NUMBERS = [4, 8, 15, 16, 23, 42]


def draw(event, ctx):
    return f"Numbers: {', '.join(str(n) for n in NUMBERS)}"
"""),
          S("invoke_local", function="draw", path="/draw"),
          S("validate"),
      ],
      final="""`str.join` only joins strings. Each number is now converted with `str(n)`.

- After: 200 `text/plain`: `Numbers: 4, 8, 15, 16, 23, 42` (a `str` return is sent as text [docs/handlers.md#returning-a-response]).
- validate (azure): valid."""),
]
