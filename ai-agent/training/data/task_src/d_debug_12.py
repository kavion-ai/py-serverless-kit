"""Category D (fix a handler bug), batch 12. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    # ------------------------------------------------------------------ 221 onprem http, `is` with a string literal
    B(221, provider="onprem", stage="prod", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: admin-tools\n" + ONPREM.format(port=8621) + """functions:
  purge-cache:
    handler: app.admin.purge
    events:
      - http: POST /admin/purge
""",
          "app/__init__.py": "",
          "app/admin.py": FUTURE + """from py_serverless_kit import Forbidden


def purge(event, ctx):
    role = event.http.json().get("role", "")
    if role is not "admin":
        raise Forbidden("admins only")
    return {"purged": True}
""",
          "requirements.txt": ""}),
      user="""{"error": "admins only", "status": 403}
even when I send {"role": "admin"}. there's also a SyntaxWarning in the output""",
      steps=[
          S("read_file", path="app/admin.py"),
          S("invoke_local", function="purge-cache", method="POST", path="/admin/purge", data={"role": "admin"}),
          S("propose_plan", steps=["Compare the strings with `!=` instead of `is not` (identity)",
                                   "POST role admin locally and validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/admin.py", content=FUTURE + """from py_serverless_kit import Forbidden


def purge(event, ctx):
    role = event.http.json().get("role", "")
    if role != "admin":
        raise Forbidden("admins only")
    return {"purged": True}
"""),
          S("invoke_local", function="purge-cache", method="POST", path="/admin/purge", data={"role": "admin"}),
          S("validate"),
      ],
      final="""`is not` checks whether two values are the *same object*, not whether they are equal. The `"admin"` parsed from JSON is a new string object, so `role is not "admin"` was always true. That's exactly what the SyntaxWarning was saying. `!=` compares the text.

- Before: 403 `admins only`.
- After: 200 `{"purged": true}`, and no warning.
- validate (onprem, prod): valid.

A role taken from the request body is not real authentication. Check a token on the server side before trusting it."""),

    # ------------------------------------------------------------------ 222 onprem http, str(None) stored as "None"
    B(222, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: pet-clinic\n" + ONPREM.format(port=8622) + """functions:
  add-pet:
    handler: app.pets.add
    events:
      - http: POST /pets
""",
          "app/__init__.py": "",
          "app/pets.py": FUTURE + """
def add(event, ctx):
    body = event.http.json()
    name = str(body.get("name")).strip()
    if not name:
        return {"error": "name is required"}, 400
    return {"pet": name}, 201
""",
          "requirements.txt": ""}),
      user="in the pet list there are pets called None. i have a check for empty name, why does it not work?",
      steps=[
          S("read_file", path="app/pets.py"),
          S("invoke_local", function="add-pet", method="POST", path="/pets", data={"species": "cat"}),
          S("propose_plan", steps=["Check the raw value before converting: `body.get(\"name\") or \"\"`, and raise `BadRequest` when it is empty",
                                   "POST a pet without a name (must be 400) locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/pets.py", content=FUTURE + """from py_serverless_kit import BadRequest


def add(event, ctx):
    body = event.http.json()
    name = str(body.get("name") or "").strip()
    if not name:
        raise BadRequest("name is required")
    return {"pet": name}, 201
"""),
          S("invoke_local", function="add-pet", method="POST", path="/pets", data={"species": "cat"}),
          S("validate"),
      ],
      final="""When there is no `name`, `body.get("name")` is `None`, and `str(None)` is the text `"None"`. That is not empty, so your check passed. Now a missing name becomes `""` first, and the empty check raises `BadRequest` (400) [docs/handlers.md#errors].

- Before: 201 `{"pet": "None"}`.
- After: 400 `name is required`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 223 onprem http, %d truncates a percentage
    B(223, provider="onprem", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: promo\n" + ONPREM.format(port=8623) + """functions:
  banner:
    handler: app.promo.banner
    events:
      - http: GET /promo/banner
""",
          "app/__init__.py": "",
          "app/promo.py": FUTURE + """DISCOUNT = 12.5


def banner(event, ctx):
    return {"text": "Save %d%% today!" % DISCOUNT}
""",
          "requirements.txt": ""}),
      user="banner show save 12% but discount is 12.5. marketing angry",
      steps=[
          S("read_file", path="app/promo.py"),
          S("invoke_local", function="banner", path="/promo/banner"),
          S("propose_plan", steps=["Format with an f-string `f\"{DISCOUNT:g}%\"`: `%d` cuts the number to an integer",
                                   "GET /promo/banner locally and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/promo.py", content=FUTURE + """DISCOUNT = 12.5


def banner(event, ctx):
    return {"text": f"Save {DISCOUNT:g}% today!"}
"""),
          S("invoke_local", function="banner", path="/promo/banner"),
          S("validate"),
      ],
      final="""`%d` means "integer", so `12.5` was cut to `12`. With `{DISCOUNT:g}`, `12.5` shows as `12.5` and `15.0` as `15`.

- Before: `Save 12% today!`.
- After: `Save 12.5% today!`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 224 onprem http, zip() drops the extra item
    B(224, provider="onprem", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: price-import\n" + ONPREM.format(port=8624) + """functions:
  set-prices:
    handler: app.prices.set_prices
    events:
      - http: PUT /prices
""",
          "app/__init__.py": "",
          "app/prices.py": FUTURE + """
def set_prices(event, ctx):
    body = event.http.json()
    prices = dict(zip(body["skus"], body["prices"]))
    return {"updated": prices}
""",
          "requirements.txt": ""}),
      user="PUT /prices takes two parallel lists, skus and prices. Yesterday someone sent 3 skus but only 2 prices, and the third product silently kept its old price. The request should be refused with a 400 when the lists don't have the same length. Python 3.9 on the host, so no zip(strict=True).",
      steps=[
          S("read_file", path="app/prices.py"),
          S("invoke_local", function="set-prices", method="PUT", path="/prices",
            data={"skus": ["A1", "B2", "C3"], "prices": [9.5, 4.0]}),
          S("propose_plan", steps=["Compare the two lengths first and raise `BadRequest` when they differ (no `strict=`, which needs 3.10)",
                                   "PUT 3 skus with 2 prices (must be 400) and a matching pair (200); validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/prices.py", content=FUTURE + """from py_serverless_kit import BadRequest


def set_prices(event, ctx):
    body = event.http.json()
    skus, prices = body["skus"], body["prices"]
    if len(skus) != len(prices):
        raise BadRequest(f"got {len(skus)} skus but {len(prices)} prices")
    return {"updated": dict(zip(skus, prices))}
"""),
          S("invoke_local", function="set-prices", method="PUT", path="/prices",
            data={"skus": ["A1", "B2", "C3"], "prices": [9.5, 4.0]}),
          S("invoke_local", function="set-prices", method="PUT", path="/prices",
            data={"skus": ["A1", "B2"], "prices": [9.5, 4.0]}),
          S("validate"),
      ],
      final="""`zip()` stops at the shorter list without any error, so `C3` was dropped. The handler now compares the lengths first and raises `BadRequest` [docs/handlers.md#errors]. This works on Python 3.9; `zip(strict=True)` would need 3.10.

- 3 skus, 2 prices: 400 `got 3 skus but 2 prices`.
- 2 and 2: 200 `{"updated": {"A1": 9.5, "B2": 4.0}}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 225 onprem http, shadowing the builtin str
    B(225, provider="onprem", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: search-api\n" + ONPREM.format(port=8625) + """functions:
  search:
    handler: app.search.search
    events:
      - http: GET /search
""",
          "app/__init__.py": "",
          "app/search.py": FUTURE + """ITEMS = ["red apple", "green pear", "red cherry"]


def search(event, ctx):
    str = event.http.query.get("q", "")
    limit = int(event.http.query.get("limit", "10"))
    hits = [i for i in ITEMS if str in i][:limit]
    return {"query": str, "hits": hits, "note": "showing " + str(len(hits))}
""",
          "requirements.txt": ""}),
      user="""TypeError: 'str' object is not callable
GET /search?q=red""",
      steps=[
          S("read_file", path="app/search.py"),
          S("invoke_local", function="search", path="/search?q=red"),
          S("propose_plan", steps=["Rename the variable `str` to `query`, so the builtin `str()` works again",
                                   "GET /search?q=red locally and validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/search.py", content=FUTURE + """ITEMS = ["red apple", "green pear", "red cherry"]


def search(event, ctx):
    query = event.http.query.get("q", "")
    limit = int(event.http.query.get("limit", "10"))
    hits = [i for i in ITEMS if query in i][:limit]
    return {"query": query, "hits": hits, "note": "showing " + str(len(hits))}
"""),
          S("invoke_local", function="search", path="/search?q=red"),
          S("validate"),
      ],
      final="""The variable named `str` hid Python's built-in `str`, so `str(len(hits))` tried to call the text `"red"`. I renamed the variable to `query`.

- After: 200, `{"query": "red", "hits": ["red apple", "red cherry"], "note": "showing 2"}`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 226 onprem queue, generator consumed twice
    B(226, provider="onprem", stage="staging", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: meter-agg\n" + ONPREM.format(port=8626) + """functions:
  aggregate:
    handler: app.agg.handle
    events:
      - queue: meter-readings
""",
          "app/__init__.py": "",
          "app/agg.py": FUTURE + """
def handle(event, ctx):
    readings = (r.json() for r in event.records)
    total = sum(m["kwh"] for m in readings)
    count = len(list(readings))
    return {"total_kwh": total, "readings": count}
""",
          "requirements.txt": ""}),
      user="aggregate: total right, readings always 0",
      steps=[
          S("read_file", path="app/agg.py"),
          S("invoke_local", function="aggregate", type="queue", data=[{"kwh": 1.5}, {"kwh": 2.25}, {"kwh": 0.75}]),
          S("propose_plan", steps=["Make `readings` a list (`[...]`): a generator is empty after `sum()` used it",
                                   "Invoke with 3 readings; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/agg.py", content=FUTURE + """
def handle(event, ctx):
    readings = [r.json() for r in event.records]
    total = sum(m["kwh"] for m in readings)
    return {"total_kwh": total, "readings": len(readings)}
"""),
          S("invoke_local", function="aggregate", type="queue", data=[{"kwh": 1.5}, {"kwh": 2.25}, {"kwh": 0.75}]),
          S("validate"),
      ],
      final="""`( ... for ...)` is a generator: it can be read once. `sum()` used it up, so `list(readings)` was empty. Changed to a list comprehension.

- Before: `{"total_kwh": 4.5, "readings": 0}`.
- After: `{"total_kwh": 4.5, "readings": 3}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 227 onprem storage, action "delete" vs "deleted"
    B(227, provider="onprem", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#record", "docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": "service: media-index\n" + ONPREM.format(port=8627) + """functions:
  indexer:
    handler: app.index.handle
    events:
      - storage:
          bucket: media
          events: [created, deleted]
""",
          "app/__init__.py": "",
          "app/index.py": FUTURE + """
def handle(event, ctx):
    added, removed = [], []
    for record in event.records:
        if record.action == "delete":
            removed.append(record.key)
        else:
            added.append(record.key)
    return {"added": added, "removed": removed}
""",
          "requirements.txt": ""}),
      user="when i delete file from media folder, indexer add it again to index instead remove it",
      steps=[
          S("read_file", path="app/index.py"),
          S("invoke_local", function="indexer", type="storage",
            data=[{"key": "song.mp3", "action": "deleted"}, {"key": "cover.png", "action": "created"}]),
          S("propose_plan", steps=["Compare with the real action values `\"deleted\"` / `\"created\"`",
                                   "Invoke with one deleted and one created file; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/index.py", content=FUTURE + """
def handle(event, ctx):
    added, removed = [], []
    for record in event.records:
        if record.action == "deleted":
            removed.append(record.key)
        elif record.action == "created":
            added.append(record.key)
    return {"added": added, "removed": removed}
"""),
          S("invoke_local", function="indexer", type="storage",
            data=[{"key": "song.mp3", "action": "deleted"}, {"key": "cover.png", "action": "created"}]),
          S("validate"),
      ],
      final="""`record.action` is `"created"` or `"deleted"` [docs/handlers.md#record], never `"delete"`. So every event fell into the `else` branch and was added. Now each value is checked exactly, and an unknown action is ignored.

- Before: both files in `added`.
- After: `added: ["cover.png"]`, `removed: ["song.mp3"]`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 228 onprem schedule, isoweekday vs weekday numbers
    B(228, provider="onprem", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: standup-bot\n" + ONPREM.format(port=8628) + """functions:
  standup:
    handler: app.standup.run
    events:
      - schedule:
          cron: "0 9 * * *"
          input:
            day: "2026-11-06"
""",
          "app/__init__.py": "",
          "app/standup.py": FUTURE + """from datetime import date

WEEKEND = (5, 6)


def run(event, ctx):
    day = date.fromisoformat(event.data["day"])
    if day.isoweekday() in WEEKEND:
        return {"posted": False, "reason": "weekend"}
    return {"posted": True, "day": day.isoformat()}
""",
          "requirements.txt": ""}),
      user="The standup bot should post Monday to Friday and skip Saturday and Sunday. In practice it skips Fridays and posts on Sundays. The schedule input has a test date, 2026-11-06, which is a Friday. Please fix the weekend check.",
      steps=[
          S("read_file", path="app/standup.py"),
          S("invoke_local", function="standup", type="schedule"),
          S("propose_plan", steps=["`isoweekday()` is 1 (Mon) .. 7 (Sun): use `weekday()`, which is 0 (Mon) .. 6 (Sun), with `(5, 6)`",
                                   "Run with Friday 2026-11-06 (must post) and Sunday 2026-11-08 (must skip); validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/standup.py", content=FUTURE + """from datetime import date

WEEKEND = (5, 6)  # date.weekday(): Monday=0 .. Sunday=6


def run(event, ctx):
    day = date.fromisoformat(event.data["day"])
    if day.weekday() in WEEKEND:
        return {"posted": False, "reason": "weekend"}
    return {"posted": True, "day": day.isoformat()}
"""),
          S("invoke_local", function="standup", type="schedule"),
          S("invoke_local", function="standup", type="schedule", data={"day": "2026-11-08"}),
          S("validate"),
      ],
      final="""`isoweekday()` numbers the days 1 (Monday) to 7 (Sunday), so `(5, 6)` meant Friday and Saturday. `weekday()` numbers them 0 to 6, and there `(5, 6)` is Saturday and Sunday.

- Friday 2026-11-06: was skipped, now `{"posted": true, ...}`.
- Sunday 2026-11-08: `{"posted": false, "reason": "weekend"}`.
- validate (onprem, prod): valid.

You could also skip the weekend in the schedule itself with `cron: "0 9 * * 1-5"` [docs/events.md#schedule]."""),

    # ------------------------------------------------------------------ 229 aws http, comma list iterated as characters
    B(229, provider="aws", stage="dev", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: product-batch
provider:
  name: aws
  region: us-east-1
functions:
  batch-get:
    handler: app.batch.get_many
    events:
      - http: GET /products
""",
          "app/__init__.py": "",
          "app/batch.py": FUTURE + """PRODUCTS = {"11": "kettle", "12": "toaster", "13": "mixer"}


def get_many(event, ctx):
    ids = event.http.query.get("ids", "")
    return {"products": {i: PRODUCTS.get(i) for i in ids}}
""",
          "requirements.txt": ""}),
      user="In my old Lambda I read queryStringParameters['ids'] and it worked. Now GET /products?ids=11,12 returns keys like \"1\", \",\" and \"2\" with null values. What changed?",
      steps=[
          S("read_file", path="app/batch.py"),
          S("invoke_local", function="batch-get", path="/products?ids=11,12"),
          S("propose_plan", steps=["Split the comma list: `[i for i in ids.split(\",\") if i]` (looping over a str gives characters)",
                                   "GET /products?ids=11,12 locally and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/batch.py", content=FUTURE + """PRODUCTS = {"11": "kettle", "12": "toaster", "13": "mixer"}


def get_many(event, ctx):
    ids = [i.strip() for i in event.http.query.get("ids", "").split(",") if i.strip()]
    return {"products": {i: PRODUCTS.get(i) for i in ids}}
"""),
          S("invoke_local", function="batch-get", path="/products?ids=11,12"),
          S("validate"),
      ],
      final="""Nothing changed in the value: `event.http.query["ids"]` is the string `"11,12"`, like `queryStringParameters` [docs/handlers.md#httprequest]. The bug is in the loop: `for i in "11,12"` loops over characters. Your old code probably split the string first. Now it is split on commas, and empty parts are skipped.

- Before: keys `"1"`, `","`, `"2"`.
- After: `{"11": "kettle", "12": "toaster"}`.
- validate (aws): valid.

For `?ids=11&ids=12` (repeated parameter), use `event.http.multi_query["ids"]`."""),

    # ------------------------------------------------------------------ 230 aws http, NaN in JSON
    B(230, provider="aws", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: shop-reviews
provider:
  name: aws
  region: ca-central-1
functions:
  review-stats:
    handler: app.reviews.stats
    events:
      - http: GET /products/{sku}/reviews/stats
""",
          "app/__init__.py": "",
          "app/reviews.py": FUTURE + """REVIEWS = {"MUG-1": [4, 5], "LAMP-2": []}


def stats(event, ctx):
    scores = REVIEWS.get(event.http.path_params["sku"], [])
    avg = sum(scores) / len(scores) if scores else float("nan")
    return {"average": avg, "count": len(scores)}
""",
          "requirements.txt": ""}),
      user="""SyntaxError: Unexpected token 'N', "{"average":NaN,"count":0}" is not valid JSON
frontend, product LAMP-2""",
      steps=[
          S("read_file", path="app/reviews.py"),
          S("invoke_local", function="review-stats", path="/products/LAMP-2/reviews/stats"),
          S("propose_plan", steps=["Return `None` (JSON `null`) instead of `float(\"nan\")` when there are no reviews",
                                   "GET the stats of LAMP-2 locally and validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/reviews.py", content=FUTURE + """REVIEWS = {"MUG-1": [4, 5], "LAMP-2": []}


def stats(event, ctx):
    scores = REVIEWS.get(event.http.path_params["sku"], [])
    avg = round(sum(scores) / len(scores), 2) if scores else None
    return {"average": avg, "count": len(scores)}
"""),
          S("invoke_local", function="review-stats", path="/products/LAMP-2/reviews/stats"),
          S("validate"),
      ],
      final="""Python's `json` writes `float("nan")` as `NaN`, which is not valid JSON, so `JSON.parse` in the browser fails. With no reviews the handler now returns `None`, which becomes `null`.

- Before: body `{"average":NaN,"count":0}`.
- After: `{"average": null, "count": 0}`.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 231 aws http, hash() for an ETag
    B(231, provider="aws", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: menu-api
provider:
  name: aws
  region: eu-north-1
functions:
  menu:
    handler: app.menu.get_menu
    events:
      - http: GET /menu
""",
          "app/__init__.py": "",
          "app/menu.py": FUTURE + """import json

from py_serverless_kit import Response

MENU = {"soup": 6.5, "salad": 8.0}


def get_menu(event, ctx):
    etag = str(hash(json.dumps(MENU, sort_keys=True)))
    return Response.json(MENU, headers={"etag": f'"{etag}"'})
""",
          "requirements.txt": ""}),
      user="We added an ETag to GET /menu so browsers can cache it, but the CDN reports a different ETag almost every time even though the menu hasn't changed. The ETag must only change when the menu content changes. Can you fix it?",
      steps=[
          S("read_file", path="app/menu.py"),
          S("invoke_local", function="menu", path="/menu"),
          S("invoke_local", function="menu", path="/menu"),
          S("propose_plan", steps=["Build the ETag with `hashlib.sha256` of the JSON: `hash()` of a str is randomised per process",
                                   "Call GET /menu twice locally (same ETag) and validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/menu.py", content=FUTURE + """import hashlib
import json

from py_serverless_kit import Response

MENU = {"soup": 6.5, "salad": 8.0}


def get_menu(event, ctx):
    digest = hashlib.sha256(json.dumps(MENU, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return Response.json(MENU, headers={"etag": f'"{digest}"'})
"""),
          S("invoke_local", function="menu", path="/menu"),
          S("invoke_local", function="menu", path="/menu"),
          S("validate"),
      ],
      final="""Python randomises `hash()` of strings in every new process. Each Lambda instance, and each local run, got a different number for the same menu. `hashlib.sha256` gives the same digest everywhere for the same bytes.

- Before: two local runs gave two different ETags.
- After: both runs give the same `etag`. It changes only when `MENU` changes.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 232 aws http, Node.js json without ()
    B(232, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": """service: signup-js
provider:
  name: aws
  region: eu-west-2
  runtime: nodejs22
functions:
  signup:
    handler: src.signup.handler
    events:
      - http: POST /signup
""",
          "src/signup.js": """exports.handler = async (event, ctx) => {
  const body = event.http.json;
  return { welcome: body.name, plan: body.plan || "free" };
};
"""}),
      user="signup js function return only plan free, welcome missing. i send name in body",
      steps=[
          S("read_file", path="src/signup.js"),
          S("invoke_local", function="signup", method="POST", path="/signup", data={"name": "Ravi", "plan": "pro"}),
          S("propose_plan", steps=["Call the method: `event.http.json()`; without `()` you get the function itself",
                                   "POST a signup locally and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/signup.js", content="""exports.handler = async (event, ctx) => {
  const body = event.http.json();
  return { welcome: body.name, plan: body.plan || "free" };
};
"""),
          S("invoke_local", function="signup", method="POST", path="/signup", data={"name": "Ravi", "plan": "pro"}),
          S("validate"),
      ],
      final="""`event.http.json` without `()` is the function, not the parsed body [docs/nodejs.md#handlers]. A function's `.name` is its own name, so `welcome` was `"json"`, and `.plan` was `undefined`, so you always got `"free"`. Now it calls `event.http.json()`.

- After: `{"welcome": "Ravi", "plan": "pro"}`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 233 gcp http, min() instead of a clamp
    B(233, provider="gcp", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: feed-api\n" + GCP.format(region="us-central1") + """functions:
  feed:
    handler: app.feed.feed
    events:
      - http: GET /feed
""",
          "app/__init__.py": "",
          "app/feed.py": FUTURE + """POSTS = [f"post-{n}" for n in range(1, 251)]


def feed(event, ctx):
    limit = int(event.http.query.get("limit", "20"))
    limit = min(limit, 1)
    return {"limit": limit, "posts": POSTS[:limit]}
""",
          "requirements.txt": ""}),
      user="feed always 1 post. wanted limit clamped to 1..100",
      steps=[
          S("read_file", path="app/feed.py"),
          S("invoke_local", function="feed", path="/feed?limit=3"),
          S("propose_plan", steps=["Clamp with `max(1, min(limit, 100))`",
                                   "GET /feed?limit=3 and ?limit=0 locally; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/feed.py", content=FUTURE + """POSTS = [f"post-{n}" for n in range(1, 251)]


def feed(event, ctx):
    limit = int(event.http.query.get("limit", "20"))
    limit = max(1, min(limit, 100))
    return {"limit": limit, "posts": POSTS[:limit]}
"""),
          S("invoke_local", function="feed", path="/feed?limit=3"),
          S("invoke_local", function="feed", path="/feed?limit=0"),
          S("validate"),
      ],
      final="""`min(limit, 1)` is never more than 1. Clamp is `max(1, min(limit, 100))`.

- `limit=3`: was 1 post, now 3. `limit=0`: 1 post. Anything above 100 gives 100.
- validate (gcp): valid.

`limit=abc` still gives a 500 from `int()`; say if you want a 400 for that."""),

    # ------------------------------------------------------------------ 234 gcp schedule, sorted by name instead of sales
    B(234, provider="gcp", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: sales-digest\n" + GCP.format(region="europe-west2") + """functions:
  digest:
    handler: app.digest.run
    events:
      - schedule:
          cron: "0 7 * * 1"
          input:
            sales: {apron: 12, bowl: 40, cup: 95, dish: 3}
""",
          "app/__init__.py": "",
          "app/digest.py": FUTURE + """
def run(event, ctx):
    ranked = sorted(event.data["sales"].items(), reverse=True)
    return {"top3": [name for name, _ in ranked[:3]]}
""",
          "requirements.txt": ""}),
      user="the weekly email says top products are dish, cup, bowl but dish sold only 3! cup should be first",
      steps=[
          S("read_file", path="app/digest.py"),
          S("invoke_local", function="digest", type="schedule"),
          S("propose_plan", steps=["Sort by the sales number: `key=lambda kv: kv[1]` (now it sorts by name)",
                                   "Run with the configured input; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/digest.py", content=FUTURE + """
def run(event, ctx):
    ranked = sorted(event.data["sales"].items(), key=lambda kv: kv[1], reverse=True)
    return {"top3": [name for name, _ in ranked[:3]]}
"""),
          S("invoke_local", function="digest", type="schedule"),
          S("validate"),
      ],
      final="""`sorted()` on `(name, sales)` pairs compares the **names** first, so `reverse=True` gave reverse alphabetical order: dish, cup, bowl. `key=lambda kv: kv[1]` sorts by the sales number.

- Before: `["dish", "cup", "bowl"]`.
- After: `["cup", "bowl", "apron"]`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 235 gcp http, except Exception turns 404 into 400
    B(235, provider="gcp", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: coupons\n" + GCP.format(region="asia-south1") + """functions:
  coupon:
    handler: app.coupon.get_coupon
    events:
      - http: GET /coupons/{code}
""",
          "app/__init__.py": "",
          "app/coupon.py": FUTURE + """from py_serverless_kit import BadRequest, NotFound

COUPONS = {"WELCOME10": 10}


def get_coupon(event, ctx):
    try:
        code = event.http.path_params["code"].upper()
        if code not in COUPONS:
            raise NotFound("unknown coupon")
        return {"code": code, "percent": COUPONS[code]}
    except Exception as exc:
        raise BadRequest(str(exc))
""",
          "requirements.txt": ""}),
      user="The checkout shows \"invalid request\" for coupon codes that simply don't exist, because GET /coupons/{code} answers 400 instead of 404. We wrapped the handler in try/except to turn unexpected crashes into 400s. Unknown codes must be 404, unexpected errors can stay as they are.",
      steps=[
          S("read_file", path="app/coupon.py"),
          S("invoke_local", function="coupon", path="/coupons/NOPE"),
          S("propose_plan", steps=["Remove the catch-all `except Exception`, which also catches `NotFound` and re-raises it as 400",
                                   "GET an unknown code (404) and WELCOME10 (200) locally; validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/coupon.py", content=FUTURE + """from py_serverless_kit import NotFound

COUPONS = {"WELCOME10": 10}


def get_coupon(event, ctx):
    code = event.http.path_params["code"].upper()
    if code not in COUPONS:
        raise NotFound("unknown coupon")
    return {"code": code, "percent": COUPONS[code]}
"""),
          S("invoke_local", function="coupon", path="/coupons/NOPE"),
          S("invoke_local", function="coupon", path="/coupons/welcome10"),
          S("validate"),
      ],
      final="""`NotFound` is an exception too, so `except Exception` caught it and raised `BadRequest` instead. I removed the catch-all. pskit already turns an `HttpError` into its status, and any other exception into a JSON 500 with the traceback in the logs [docs/handlers.md#errors]. A 500 is the honest answer for an unexpected crash.

- `NOPE`: was 400, now 404 `unknown coupon`.
- `welcome10`: 200 `{"code": "WELCOME10", "percent": 10}`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 236 gcp queue, set of dicts
    B(236, provider="gcp", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: click-dedupe\n" + GCP.format(region="us-east4") + """functions:
  clicks:
    handler: app.clicks.handle
    events:
      - queue: ad-clicks
""",
          "app/__init__.py": "",
          "app/clicks.py": FUTURE + """
def handle(event, ctx):
    unique = set()
    for record in event.records:
        unique.add(record.json())
    return {"unique_clicks": len(unique)}
""",
          "requirements.txt": ""}),
      user="""TypeError: unhashable type: 'dict'
in clicks, trying to dedupe the same click sent twice""",
      steps=[
          S("read_file", path="app/clicks.py"),
          S("invoke_local", function="clicks", type="queue",
            data=[{"ad": "a1", "user": "u1"}, {"ad": "a1", "user": "u1"}, {"ad": "a2", "user": "u1"}]),
          S("propose_plan", steps=["Dedupe on a hashable key: the tuple `(click[\"ad\"], click[\"user\"])`",
                                   "Invoke with a duplicate click; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/clicks.py", content=FUTURE + """
def handle(event, ctx):
    unique = set()
    for record in event.records:
        click = record.json()
        unique.add((click["ad"], click["user"]))
    return {"unique_clicks": len(unique)}
"""),
          S("invoke_local", function="clicks", type="queue",
            data=[{"ad": "a1", "user": "u1"}, {"ad": "a1", "user": "u1"}, {"ad": "a2", "user": "u1"}]),
          S("validate"),
      ],
      final="""A set can only hold hashable values, and a dict isn't one. The handler now stores the tuple `(ad, user)`, which identifies a click.

- After: `{"unique_clicks": 2}` for 3 messages, one of them a duplicate.
- validate (gcp): valid.

This only removes duplicates within one delivery. On GCP a "queue" is Pub/Sub, which can deliver a message again later, so remember the ids you've already processed if that matters."""),

    # ------------------------------------------------------------------ 237 azure http, [-1] on an empty list
    B(237, provider="azure", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: order-history
provider:
  name: azure
  region: northeurope
functions:
  last-order:
    handler: app.history.last_order
    events:
      - http: GET /customers/{id}/last-order
""",
          "app/__init__.py": "",
          "app/history.py": FUTURE + """ORDERS = {"c1": [{"id": "o1"}, {"id": "o7"}], "c2": []}


def last_order(event, ctx):
    orders = ORDERS.get(event.http.path_params["id"], [])
    return {"last": orders[-1]}
""",
          "requirements.txt": ""}),
      user="""IndexError: list index out of range
GET /customers/c2/last-order -> 500. c2 is a new customer""",
      steps=[
          S("read_file", path="app/history.py"),
          S("invoke_local", function="last-order", path="/customers/c2/last-order"),
          S("propose_plan", steps=["Raise `NotFound` when the customer has no orders, before `orders[-1]`",
                                   "GET c2 (404) and c1 (200) locally; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/history.py", content=FUTURE + """from py_serverless_kit import NotFound

ORDERS = {"c1": [{"id": "o1"}, {"id": "o7"}], "c2": []}


def last_order(event, ctx):
    orders = ORDERS.get(event.http.path_params["id"], [])
    if not orders:
        raise NotFound("no orders yet")
    return {"last": orders[-1]}
"""),
          S("invoke_local", function="last-order", path="/customers/c2/last-order"),
          S("invoke_local", function="last-order", path="/customers/c1/last-order"),
          S("validate"),
      ],
      final="""`orders[-1]` on an empty list raises `IndexError`, and pskit turns that into a 500. A customer with no orders now gets `NotFound` (404) [docs/handlers.md#errors].

- c2: 404 `no orders yet`.
- c1: 200 `{"last": {"id": "o7"}}`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 238 azure queue, trailing newline in a text message
    B(238, provider="azure", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: health-pings
provider:
  name: azure
  region: australiaeast
functions:
  pinger:
    handler: app.ping.handle
    events:
      - queue: health-checks
""",
          "app/__init__.py": "",
          "app/ping.py": FUTURE + """
def handle(event, ctx):
    results = []
    for record in event.records:
        results.append("pong" if record.text() == "ping" else "unknown")
    return {"results": results}
""",
          "requirements.txt": ""}),
      user="the shell script put ping in queue with echo but function answer unknown. ping is ping??",
      steps=[
          S("read_file", path="app/ping.py"),
          S("invoke_local", function="pinger", type="queue", data=["ping\n"]),
          S("propose_plan", steps=["Strip whitespace before comparing: `record.text().strip()` (`echo` adds a newline)",
                                   "Invoke with `ping\\n`; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/ping.py", content=FUTURE + """
def handle(event, ctx):
    results = []
    for record in event.records:
        results.append("pong" if record.text().strip().lower() == "ping" else "unknown")
    return {"results": results}
"""),
          S("invoke_local", function="pinger", type="queue", data=["ping\n"]),
          S("validate"),
      ],
      final="""`echo ping` sends `ping` **plus a newline**, so the text is `"ping\\n"`, and that is not equal to `"ping"`. `.strip()` removes spaces and newlines at both ends (and `.lower()` accepts `PING` too).

- Before: `["unknown"]`. After: `["pong"]`.
- validate (azure): valid.

`echo -n ping` in the script would avoid the newline too, but the handler is safer this way."""),

    # ------------------------------------------------------------------ 239 azure http, capitalize() lowercases the rest
    B(239, provider="azure", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: product-titles
provider:
  name: azure
  region: japaneast
functions:
  title:
    handler: app.titles.make_title
    events:
      - http: POST /titles
""",
          "app/__init__.py": "",
          "app/titles.py": FUTURE + """
def make_title(event, ctx):
    name = event.http.json().get("name", "").strip()
    return {"title": name.capitalize()}
""",
          "requirements.txt": ""}),
      user="I only want the first letter to be big. But \"usb-C cable for iPhone\" becomes \"Usb-c cable for iphone\". Why does it change the other letters?",
      steps=[
          S("read_file", path="app/titles.py"),
          S("invoke_local", function="title", method="POST", path="/titles", data={"name": "usb-C cable for iPhone"}),
          S("propose_plan", steps=["Upper-case only the first character: `name[:1].upper() + name[1:]`",
                                   "POST the same name locally and validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/titles.py", content=FUTURE + """
def make_title(event, ctx):
    name = event.http.json().get("name", "").strip()
    return {"title": name[:1].upper() + name[1:]}
"""),
          S("invoke_local", function="title", method="POST", path="/titles", data={"name": "usb-C cable for iPhone"}),
          S("validate"),
      ],
      final="""`capitalize()` makes the first letter big **and all the others small**. `name[:1].upper() + name[1:]` changes only the first letter (and works for an empty name too).

- Before: `"Usb-c cable for iphone"`.
- After: `"Usb-C cable for iPhone"`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 240 azure http, return inside the loop
    B(240, provider="azure", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: timesheets
provider:
  name: azure
  region: canadacentral
functions:
  submit:
    handler: app.timesheet.submit
    events:
      - http: POST /timesheets
""",
          "app/__init__.py": "",
          "app/timesheet.py": FUTURE + """from py_serverless_kit import UnprocessableEntity


def submit(event, ctx):
    days = event.http.json()["days"]
    for i, day in enumerate(days):
        if not 0 <= day["hours"] <= 24:
            raise UnprocessableEntity("invalid hours", details={"day": i})
        return {"accepted": len(days)}
""",
          "requirements.txt": ""}),
      user="POST /timesheets must reject the whole timesheet when any day has hours outside 0-24, and say which day. A sheet with 30 hours on the second day was accepted. Only the first day seems to be checked. Please fix and test with a bad second day and with a valid sheet.",
      steps=[
          S("read_file", path="app/timesheet.py"),
          S("invoke_local", function="submit", method="POST", path="/timesheets",
            data={"days": [{"hours": 8}, {"hours": 30}, {"hours": 7}]}),
          S("propose_plan", steps=["Move `return` out of the `for` loop, so every day is checked before accepting",
                                   "POST a bad second day (422, day 1) and a valid sheet (200); validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/timesheet.py", content=FUTURE + """from py_serverless_kit import UnprocessableEntity


def submit(event, ctx):
    days = event.http.json()["days"]
    for i, day in enumerate(days):
        if not 0 <= day["hours"] <= 24:
            raise UnprocessableEntity("invalid hours", details={"day": i})
    return {"accepted": len(days)}
"""),
          S("invoke_local", function="submit", method="POST", path="/timesheets",
            data={"days": [{"hours": 8}, {"hours": 30}, {"hours": 7}]}),
          S("invoke_local", function="submit", method="POST", path="/timesheets",
            data={"days": [{"hours": 8}, {"hours": 7}]}),
          S("validate"),
      ],
      final="""The `return` was indented inside the `for` loop, so the handler accepted the sheet right after checking day 0. With `return` after the loop, every day is checked first.

- Bad second day: 422 `invalid hours`, `details: {"day": 1}` (days are counted from 0) [docs/handlers.md#errors].
- Valid sheet: 200 `{"accepted": 2}`.
- validate (azure): valid."""),
]
