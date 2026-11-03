"""Category D (fix a handler bug), batch 11. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    # ------------------------------------------------------------------ 201 onprem http, float rounding of VAT
    B(201, provider="onprem", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: invoicing\n" + ONPREM.format(port=8611) + """functions:
  vat:
    handler: app.vat.compute
    events:
      - http: POST /vat
""",
          "app/__init__.py": "",
          "app/vat.py": FUTURE + """
def compute(event, ctx):
    net = float(event.http.json()["net"])
    vat = round(net * 0.19, 2)
    return {"net": net, "vat": vat, "gross": round(net + vat, 2)}
""",
          "requirements.txt": ""}),
      user="Our accountant found that the vat endpoint rounds wrong. For net 14.50 the VAT at 19% is 2.755, which must round half up to 2.76, but we return 2.75. Amounts come in as strings like \"14.50\". Please make the rounding commercial (half up) and keep the response fields the same.",
      steps=[
          S("read_file", path="app/vat.py"),
          S("invoke_local", function="vat", method="POST", path="/vat", data={"net": "14.50"}),
          S("propose_plan", steps=["Compute with `Decimal` from the string and `quantize(Decimal(\"0.01\"), ROUND_HALF_UP)`",
                                   "Return the amounts as strings so no float rounding happens on the way out",
                                   "POST net 14.50 locally and validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/vat.py", content=FUTURE + """from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def compute(event, ctx):
    net = Decimal(str(event.http.json()["net"]))
    vat = (net * Decimal("0.19")).quantize(CENT, rounding=ROUND_HALF_UP)
    return {"net": str(net), "vat": str(vat), "gross": str(net + vat)}
"""),
          S("invoke_local", function="vat", method="POST", path="/vat", data={"net": "14.50"}),
          S("validate"),
      ],
      final="""Two problems: `14.50 * 0.19` as a float is `2.7549999...`, and Python's `round()` uses banker's rounding anyway. `Decimal` computes exactly `2.755`, and `quantize(..., ROUND_HALF_UP)` gives `2.76`.

- Before: `"vat": 2.75`.
- After: `"vat": "2.76"`, `"gross": "17.26"`.
- validate (onprem, prod): valid.

The amounts are now strings (`"2.76"`). I did that on purpose: pskit turns a non-integer `Decimal` into a float when it writes JSON [docs/handlers.md#returning-a-response], and strings keep the exact digits. Tell me if the client needs numbers."""),

    # ------------------------------------------------------------------ 202 aws http, len() of a filter object
    B(202, provider="aws", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: user-stats
provider:
  name: aws
  region: eu-west-1
functions:
  active:
    handler: app.stats.active_users
    events:
      - http: GET /stats/active
""",
          "app/__init__.py": "",
          "app/stats.py": FUTURE + """USERS = [{"name": "li", "active": True}, {"name": "max", "active": False}, {"name": "eva", "active": True}]


def active_users(event, ctx):
    active = filter(lambda u: u["active"], USERS)
    return {"count": len(active), "names": [u["name"] for u in active]}
""",
          "requirements.txt": ""}),
      user="stats active give 500. log say object of type 'filter' has no len(). i just want count of active users",
      steps=[
          S("read_file", path="app/stats.py"),
          S("invoke_local", function="active", path="/stats/active"),
          S("propose_plan", steps=["Build a real list with a list comprehension, then take `len()` of it",
                                   "GET /stats/active locally and validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/stats.py", content=FUTURE + """USERS = [{"name": "li", "active": True}, {"name": "max", "active": False}, {"name": "eva", "active": True}]


def active_users(event, ctx):
    active = [u for u in USERS if u["active"]]
    return {"count": len(active), "names": [u["name"] for u in active]}
"""),
          S("invoke_local", function="active", path="/stats/active"),
          S("validate"),
      ],
      final="""`filter()` returns a lazy iterator, not a list, so it has no length. It can also be read only once, so `names` would have come back empty. A list comprehension gives a real list you can count and loop over again.

- Before: 500 (`TypeError: object of type 'filter' has no len()`).
- After: `{"count": 2, "names": ["li", "eva"]}`.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 203 aws storage, S3 folder marker keys
    B(203, provider="aws", stage="dev", mode="ask", page="Logs", persona="aws_migrator",
      sources=["docs/handlers.md#record", "docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: thumbs
provider:
  name: aws
  region: us-east-2
functions:
  thumb:
    handler: app.thumb.handle
    events:
      - storage:
          bucket: photo-uploads
          events: [created]
""",
          "app/__init__.py": "",
          "app/thumb.py": FUTURE + """from pathlib import PurePosixPath

ALLOWED = {".jpg", ".jpeg", ".png"}


def handle(event, ctx):
    done = []
    for record in event.records:
        suffix = PurePosixPath(record.key).suffix.lower()
        if suffix not in ALLOWED:
            raise ValueError(f"unsupported file type {record.key!r}")
        done.append(f"thumbs/{record.key}")
    return {"thumbnails": done}
""",
          "requirements.txt": ""}),
      user="When someone creates a folder in the S3 console, my thumb function errors with \"unsupported file type 'holiday/'\" and Lambda keeps retrying it. In the old Lambda I never saw this. How do I make it ignore folders?",
      steps=[
          S("read_file", path="app/thumb.py"),
          S("invoke_local", function="thumb", type="storage",
            data=[{"bucket": "photo-uploads", "key": "holiday/", "size": 0},
                  {"bucket": "photo-uploads", "key": "holiday/beach.jpg", "size": 48213}]),
          S("propose_plan", steps=["Skip keys that end with `/` (the console's zero-byte folder markers) before checking the suffix",
                                   "Invoke with a folder marker and a photo; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/thumb.py", content=FUTURE + """from pathlib import PurePosixPath

ALLOWED = {".jpg", ".jpeg", ".png"}


def handle(event, ctx):
    done = []
    for record in event.records:
        if record.key.endswith("/"):
            continue  # S3 console folder marker, not a file
        suffix = PurePosixPath(record.key).suffix.lower()
        if suffix not in ALLOWED:
            ctx.logger.warning("skipping file", extra={"key": record.key})
            continue
        done.append(f"thumbs/{record.key}")
    return {"thumbnails": done}
"""),
          S("invoke_local", function="thumb", type="storage",
            data=[{"bucket": "photo-uploads", "key": "holiday/", "size": 0},
                  {"bucket": "photo-uploads", "key": "holiday/beach.jpg", "size": 48213}]),
          S("validate"),
      ],
      final="""The S3 console "folder" is a zero-byte object whose key ends with `/`. It fires the created event like any upload, and `record.key` is `holiday/` [docs/handlers.md#record]. It has no suffix, so the handler raised, and an exception in a storage handler makes the platform retry. Now folder markers are skipped, and other file types are logged and skipped instead of raising.

- Before: `ValueError: unsupported file type 'holiday/'`.
- After: `{"thumbnails": ["thumbs/holiday/beach.jpg"]}`.
- validate (aws): valid.

You could also add `suffix: .jpg` on the storage event, but that allows only one suffix, so the handler check is still needed for `.png`."""),

    # ------------------------------------------------------------------ 204 aws http, version strings sorted as text
    B(204, provider="aws", stage="staging", mode="auto", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: release-feed
provider:
  name: aws
  region: us-east-1
functions:
  latest:
    handler: app.releases.latest
    events:
      - http: GET /releases/latest
""",
          "app/__init__.py": "",
          "app/releases.py": FUTURE + """RELEASES = ["1.8.2", "1.9.0", "1.10.0", "1.10.1"]


def latest(event, ctx):
    return {"latest": max(RELEASES)}
""",
          "requirements.txt": ""}),
      user="/releases/latest says 1.9.0. 1.10.1 exists",
      steps=[
          S("read_file", path="app/releases.py"),
          S("invoke_local", function="latest", path="/releases/latest"),
          S("propose_plan", steps=["Compare versions as integer tuples: `max(RELEASES, key=lambda v: tuple(int(p) for p in v.split(\".\")))`",
                                   "GET /releases/latest locally and validate for aws (staging)"]),
          S("write_file", path="app/releases.py", content=FUTURE + """RELEASES = ["1.8.2", "1.9.0", "1.10.0", "1.10.1"]


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def latest(event, ctx):
    return {"latest": max(RELEASES, key=version_key)}
"""),
          S("invoke_local", function="latest", path="/releases/latest"),
          S("validate"),
      ],
      final="""`max()` on strings compares character by character: `"1.9.0" > "1.10.1"` because `"9" > "1"`. `version_key` compares `(1, 10, 1)` vs `(1, 9, 0)` as numbers.

- Before: `1.9.0`. After: `1.10.1`.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 205 gcp http, Node.js === number vs string
    B(205, provider="gcp", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/nodejs.md#handlers", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: books-js\n" + GCP.format(region="us-central1") + """  runtime: nodejs20
functions:
  book:
    handler: src.books.getBook
    events:
      - http: GET /books/{id}
""",
          "src/books.js": """const { NotFound } = require("pskit");

const BOOKS = [{ id: 1, title: "Dune" }, { id: 2, title: "Emma" }];

exports.getBook = async (event) => {
  const book = BOOKS.find((b) => b.id === event.http.pathParams.id);
  if (!book) throw new NotFound("no such book");
  return book;
};
"""}),
      user="my javascript function says no such book for /books/1 but book 1 is in the list! i checked the id is 1",
      steps=[
          S("read_file", path="src/books.js"),
          S("invoke_local", function="book", path="/books/1"),
          S("propose_plan", steps=["Path params are strings: convert with `Number(...)` before comparing with `===`",
                                   "GET /books/1 locally and validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/books.js", content="""const { NotFound } = require("pskit");

const BOOKS = [{ id: 1, title: "Dune" }, { id: 2, title: "Emma" }];

exports.getBook = async (event) => {
  const id = Number(event.http.pathParams.id);
  const book = BOOKS.find((b) => b.id === id);
  if (!book) throw new NotFound("no such book");
  return book;
};
"""),
          S("invoke_local", function="book", path="/books/1"),
          S("validate"),
      ],
      final="""The id from the URL is the **text** `"1"`, while your list has the **number** `1`. `===` checks the type too, so `1 === "1"` is false. Path params are always strings, the same as in Python [docs/handlers.md#httprequest]. Now the id is converted with `Number(...)` first.

- Before: 404 `no such book`.
- After: 200 `{"id": 1, "title": "Dune"}`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 206 gcp topic, base64-decoding an already decoded body
    B(206, provider="gcp", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: audit-sink\n" + GCP.format(region="europe-west3") + """functions:
  audit:
    handler: app.audit.handle
    events:
      - topic: audit-events
""",
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """import base64
import json


def handle(event, ctx):
    actions = []
    for record in event.records:
        msg = json.loads(base64.b64decode(record.body))
        actions.append(msg["action"])
    return {"actions": actions}
""",
          "requirements.txt": ""}),
      user="""binascii.Error: Invalid base64-encoded string: number of data characters (17) cannot be 1 more than a multiple of 4
copied from my old cloud function where pubsub data was base64""",
      steps=[
          S("read_file", path="app/audit.py"),
          S("invoke_local", function="audit", type="topic", data=[{"action": "login", "user": "u1"}]),
          S("propose_plan", steps=["Drop the `base64.b64decode`: pskit already decodes the Pub/Sub data, so use `record.json()`",
                                   "Invoke with one audit message; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/audit.py", content=FUTURE + """
def handle(event, ctx):
    actions = []
    for record in event.records:
        actions.append(record.json()["action"])
    return {"actions": actions}
"""),
          S("invoke_local", function="audit", type="topic", data=[{"action": "login", "user": "u1"}]),
          S("validate"),
      ],
      final="""In a raw Cloud Function you get the Pub/Sub `data` field base64-encoded. pskit's GCP adapter decodes it before your handler runs, so `record.body` is already the JSON text. Decoding it as base64 again fails. `record.json()` parses the body directly [docs/handlers.md#record].

- Before: `binascii.Error`.
- After: `{"actions": ["login"]}`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 207 gcp http, unescaped dot in an email regex
    B(207, provider="gcp", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: newsletter\n" + GCP.format(region="europe-west1") + """functions:
  subscribe:
    handler: app.subscribe.handle
    events:
      - http: POST /subscribe
""",
          "app/__init__.py": "",
          "app/subscribe.py": FUTURE + """import re

from py_serverless_kit import UnprocessableEntity

EMAIL = re.compile(r"^[\\w.+-]+@[\\w-]+(.[\\w-]+)+$")


def handle(event, ctx):
    email = event.http.json().get("email", "")
    if not EMAIL.match(email):
        raise UnprocessableEntity("invalid email", details={"field": "email"})
    return {"subscribed": email}, 201
""",
          "requirements.txt": ""}),
      user="The subscribe endpoint must reject addresses without a real domain dot. Support reported that \"ana@examplecom\" was accepted (201) and the welcome mail bounced. Valid addresses like ana@example.com must still pass. Please fix the validation.",
      steps=[
          S("read_file", path="app/subscribe.py"),
          S("invoke_local", function="subscribe", method="POST", path="/subscribe", data={"email": "ana@examplecom"}),
          S("propose_plan", steps=["Escape the dot in the domain part: `(\\.[\\w-]+)+` (an unescaped `.` matches any character)",
                                   "POST `ana@examplecom` (must be 422) and `ana@example.com` (201); validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/subscribe.py", content=FUTURE + """import re

from py_serverless_kit import UnprocessableEntity

EMAIL = re.compile(r"^[\\w.+-]+@[\\w-]+(\\.[\\w-]+)+$")


def handle(event, ctx):
    email = event.http.json().get("email", "")
    if not EMAIL.match(email):
        raise UnprocessableEntity("invalid email", details={"field": "email"})
    return {"subscribed": email}, 201
"""),
          S("invoke_local", function="subscribe", method="POST", path="/subscribe", data={"email": "ana@examplecom"}),
          S("invoke_local", function="subscribe", method="POST", path="/subscribe", data={"email": "ana@example.com"}),
          S("validate"),
      ],
      final="""In a regex an unescaped `.` means "any character", so in `examplecom` the `.` matched the letter `c` and the rest matched `om`. `\\.` matches only a real dot.

- `ana@examplecom`: was 201, now 422 `invalid email` with `details: {"field": "email"}` [docs/handlers.md#errors].
- `ana@example.com`: 201.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 208 gcp storage, size in bytes vs MB
    B(208, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: video-intake\n" + GCP.format(region="us-west1") + """functions:
  intake:
    handler: app.intake.handle
    events:
      - storage: raw-videos
""",
          "app/__init__.py": "",
          "app/intake.py": FUTURE + """MAX_MB = 500


def handle(event, ctx):
    accepted, rejected = [], []
    for record in event.records:
        if record.size > MAX_MB:
            rejected.append(record.key)
        else:
            accepted.append(record.key)
    return {"accepted": accepted, "rejected": rejected}
""",
          "requirements.txt": ""}),
      user="intake reject every video as too big, also a 20 MB one. limit is 500 MB",
      steps=[
          S("read_file", path="app/intake.py"),
          S("invoke_local", function="intake", type="storage",
            data=[{"key": "clip.mp4", "size": 20971520}, {"key": "movie.mp4", "size": 734003200}]),
          S("propose_plan", steps=["`record.size` is in bytes: compare with `MAX_MB * 1024 * 1024`",
                                   "Invoke with a 20 MB and a 700 MB file; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/intake.py", content=FUTURE + """MAX_BYTES = 500 * 1024 * 1024


def handle(event, ctx):
    accepted, rejected = [], []
    for record in event.records:
        if (record.size or 0) > MAX_BYTES:
            rejected.append(record.key)
        else:
            accepted.append(record.key)
    return {"accepted": accepted, "rejected": rejected}
"""),
          S("invoke_local", function="intake", type="storage",
            data=[{"key": "clip.mp4", "size": 20971520}, {"key": "movie.mp4", "size": 734003200}]),
          S("validate"),
      ],
      final="""`record.size` is in **bytes** [docs/handlers.md#record], so a 20 MB file is `20971520`, much bigger than `500`. The limit is now `500 * 1024 * 1024` bytes. `or 0` also covers events without a size.

- Before: both rejected.
- After: `clip.mp4` accepted, `movie.mp4` (700 MB) rejected.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 209 azure http, list.sort() returns None
    B(209, provider="azure", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: team-board
provider:
  name: azure
  region: francecentral
functions:
  members:
    handler: app.team.members
    events:
      - http: GET /team
""",
          "app/__init__.py": "",
          "app/team.py": FUTURE + """TEAM = ["zoe", "adam", "mia"]


def members(event, ctx):
    names = list(TEAM)
    return {"members": names.sort()}
""",
          "requirements.txt": ""}),
      user="I want the team names in alphabetical order, so I added .sort(). Now the page says members: null. Why is it null?",
      steps=[
          S("read_file", path="app/team.py"),
          S("invoke_local", function="members", path="/team"),
          S("propose_plan", steps=["Use `sorted(TEAM)`, which returns a new sorted list (`.sort()` sorts in place and returns `None`)",
                                   "GET /team locally and validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/team.py", content=FUTURE + """TEAM = ["zoe", "adam", "mia"]


def members(event, ctx):
    return {"members": sorted(TEAM)}
"""),
          S("invoke_local", function="members", path="/team"),
          S("validate"),
      ],
      final="""`names.sort()` sorts the list *in place* and returns `None`, and `None` becomes `null` in JSON. `sorted(TEAM)` returns a new sorted list.

- Before: `{"members": null}`.
- After: `{"members": ["adam", "mia", "zoe"]}`.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 210 azure queue, str.strip with a prefix
    B(210, provider="azure", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: gift-images
provider:
  name: azure
  region: swedencentral
functions:
  rename:
    handler: app.rename.handle
    events:
      - queue: image-renames
""",
          "app/__init__.py": "",
          "app/rename.py": FUTURE + """
def handle(event, ctx):
    names = []
    for record in event.records:
        names.append(record.text().strip("img_"))
    return {"names": names}
""",
          "requirements.txt": ""}),
      user="i want remove img_ from start of name. img_gift.png become ft.pn ??? the g and i also gone",
      steps=[
          S("read_file", path="app/rename.py"),
          S("invoke_local", function="rename", type="queue", data=["img_gift.png", "img_mug.jpg"]),
          S("propose_plan", steps=["Use `removeprefix(\"img_\")` (Python 3.9+): `strip()` removes a *set of characters* from both ends",
                                   "Invoke with two names; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/rename.py", content=FUTURE + """
def handle(event, ctx):
    names = []
    for record in event.records:
        names.append(record.text().removeprefix("img_"))
    return {"names": names}
"""),
          S("invoke_local", function="rename", type="queue", data=["img_gift.png", "img_mug.jpg"]),
          S("validate"),
      ],
      final="""`strip("img_")` does not remove the word `img_`. It removes the letters `i`, `m`, `g` and `_` from **both ends**, as long as it finds them, so `img_gift.png` lost `img_gi` at the front and `g` at the end. `removeprefix("img_")` removes exactly that prefix (Python 3.9+).

- Before: `["ft.pn", "ug.jp"]`.
- After: `["gift.png", "mug.jpg"]`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 211 azure schedule, timedelta.seconds
    B(211, provider="azure", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: blob-janitor
provider:
  name: azure
  region: westus2
functions:
  cleanup:
    handler: app.cleanup.run
    events:
      - schedule:
          cron: "0 4 * * *"
          input:
            now: "2026-11-01T04:00:00+00:00"
            files:
              - {name: old.log, created: "2026-08-01T10:00:00+00:00"}
              - {name: today.log, created: "2026-11-01T01:00:00+00:00"}
""",
          "app/__init__.py": "",
          "app/cleanup.py": FUTURE + """from datetime import datetime

MAX_AGE_SECONDS = 30 * 24 * 3600


def run(event, ctx):
    now = datetime.fromisoformat(event.data["now"])
    expired = []
    for f in event.data["files"]:
        age = now - datetime.fromisoformat(f["created"])
        if age.seconds > MAX_AGE_SECONDS:
            expired.append(f["name"])
    return {"expired": expired}
""",
          "requirements.txt": ""}),
      user="The nightly cleanup should delete log files older than 30 days. It has never deleted anything, not even files from August. The schedule input has a fixed `now` and two sample files so it can be tested: old.log from 2026-08-01 must expire, today.log must stay. Can you find the bug?",
      steps=[
          S("read_file", path="app/cleanup.py"),
          S("invoke_local", function="cleanup", type="schedule"),
          S("propose_plan", steps=["Use `age.total_seconds()`: `timedelta.seconds` is only the seconds part below one day",
                                   "Run the schedule with its sample input; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/cleanup.py", content=FUTURE + """from datetime import datetime

MAX_AGE_SECONDS = 30 * 24 * 3600


def run(event, ctx):
    now = datetime.fromisoformat(event.data["now"])
    expired = []
    for f in event.data["files"]:
        age = now - datetime.fromisoformat(f["created"])
        if age.total_seconds() > MAX_AGE_SECONDS:
            expired.append(f["name"])
    return {"expired": expired}
"""),
          S("invoke_local", function="cleanup", type="schedule"),
          S("validate"),
      ],
      final="""`timedelta.seconds` is not the whole age. A `timedelta` stores days and seconds separately, and `.seconds` is only the part below one day (0 to 86399). It can never be bigger than 30 days in seconds. `total_seconds()` returns the whole duration.

- Before: `{"expired": []}`.
- After: `{"expired": ["old.log"]}`; `today.log` stays.
- validate (azure, prod): valid.

The schedule `input` becomes `event.data` [docs/events.md#schedule]. In production, use the real current time (`datetime.now(timezone.utc)`) instead of the fixed `now`."""),

    # ------------------------------------------------------------------ 212 azure http, str.format on a JSON template
    B(212, provider="azure", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: greet-api
provider:
  name: azure
  region: eastus2
functions:
  greet:
    handler: app.greet.greet
    events:
      - http: GET /greet
""",
          "app/__init__.py": "",
          "app/greet.py": FUTURE + """from py_serverless_kit import Response

TEMPLATE = '{"greeting": "Hello, {name}!"}'


def greet(event, ctx):
    name = event.http.query.get("name", "friend")
    return Response(200, TEMPLATE.format(name=name), {"content-type": "application/json"})
""",
          "requirements.txt": ""}),
      user="""KeyError: '"greeting"'
GET /greet?name=Lea""",
      steps=[
          S("read_file", path="app/greet.py"),
          S("invoke_local", function="greet", path="/greet?name=Lea"),
          S("propose_plan", steps=["Return a dict instead of formatting a JSON string (`format` treats the JSON braces as fields)",
                                   "GET /greet?name=Lea locally and validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/greet.py", content=FUTURE + """
def greet(event, ctx):
    name = event.http.query.get("name", "friend")
    return {"greeting": f"Hello, {name}!"}
"""),
          S("invoke_local", function="greet", path="/greet?name=Lea"),
          S("validate"),
      ],
      final="""`str.format` treats every `{...}` as a field, so the JSON's outer braces made it look for a field named `"greeting"`. Building JSON by hand is fragile anyway: a name with a `"` would break it. A dict return is turned into JSON for you [docs/handlers.md#returning-a-response].

- After: 200, `{"greeting": "Hello, Lea!"}`.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 213 onprem http, ascii decode of a UTF-8 text body
    B(213, provider="onprem", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: guestbook\n" + ONPREM.format(port=8612) + """functions:
  sign:
    handler: app.book.sign
    events:
      - http: POST /guestbook
""",
          "app/__init__.py": "",
          "app/book.py": FUTURE + """
def sign(event, ctx):
    message = event.http.body.decode("ascii").strip()
    return {"saved": message}, 201
""",
          "requirements.txt": ""}),
      user="""UnicodeDecodeError: 'ascii' codec can't decode byte 0xc3 in position 2: ordinal not in range(128)
guestbook POST, plain text body. only when people write Zoë or café""",
      steps=[
          S("read_file", path="app/book.py"),
          S("invoke_local", function="sign", method="POST", path="/guestbook", data="Zoë was here"),
          S("propose_plan", steps=["Decode the body as UTF-8 with `event.http.text()` instead of ASCII",
                                   "POST `Zoë was here` locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/book.py", content=FUTURE + """
def sign(event, ctx):
    message = event.http.text().strip()
    return {"saved": message}, 201
"""),
          S("invoke_local", function="sign", method="POST", path="/guestbook", data="Zoë was here"),
          S("validate"),
      ],
      final="""`ë` is two bytes in UTF-8 (`0xc3 0xab`), and ASCII only knows bytes up to 127. `event.http.text()` decodes the body as UTF-8 by default [docs/handlers.md#httprequest].

- Before: 500 (UnicodeDecodeError).
- After: 201, `{"saved": "Zoë was here"}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 214 onprem queue, sqlite connection at import
    B(214, provider="onprem", stage="staging", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": "service: order-ledger\n" + ONPREM.format(port=8613) + """functions:
  ledger:
    handler: app.ledger.handle
    events:
      - queue: ledger-entries
""",
          "app/__init__.py": "",
          "app/ledger.py": FUTURE + """import sqlite3

DB = sqlite3.connect("data/ledger.db")
DB.execute("CREATE TABLE IF NOT EXISTS entries (id TEXT, amount INTEGER)")


def handle(event, ctx):
    for record in event.records:
        entry = record.json()
        DB.execute("INSERT INTO entries VALUES (?, ?)", (entry["id"], entry["amount"]))
    DB.commit()
    return {"stored": len(event.records)}
""",
          "requirements.txt": ""}),
      user="The ledger worker fails before it even runs my code: sqlite3.OperationalError: unable to open database file. It's a fresh checkout. I'd like the database path to be configurable with an environment variable (default data/ledger.db), and the folder should be created if it's missing. Please test it with one entry.",
      steps=[
          S("read_file", path="app/ledger.py"),
          S("invoke_local", function="ledger", type="queue", data=[{"id": "e-1", "amount": 1200}]),
          S("propose_plan", steps=["Read the path from `LEDGER_DB` (default `data/ledger.db`), create its folder, and open the connection on first use instead of at import",
                                   "Invoke with one entry; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/ledger.py", content=FUTURE + """import os
import sqlite3
from pathlib import Path

_db = None


def db():
    global _db
    if _db is None:
        path = Path(os.environ.get("LEDGER_DB", "data/ledger.db"))
        path.parent.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(str(path))
        _db.execute("CREATE TABLE IF NOT EXISTS entries (id TEXT, amount INTEGER)")
    return _db


def handle(event, ctx):
    conn = db()
    for record in event.records:
        entry = record.json()
        conn.execute("INSERT INTO entries VALUES (?, ?)", (entry["id"], entry["amount"]))
    conn.commit()
    return {"stored": len(event.records)}
"""),
          S("invoke_local", function="ledger", type="queue", data=[{"id": "e-1", "amount": 1200}]),
          S("validate"),
      ],
      final="""SQLite creates the database *file*, but not a missing *folder*. `data/` doesn't exist in a fresh checkout, and the connect ran at import, so the function failed before your handler started. Now:

- the path comes from `LEDGER_DB` (default `data/ledger.db`); set it per function with `functions.ledger.environment` [docs/handlers.md#environment-variables];
- the folder is created with `mkdir(parents=True, exist_ok=True)`;
- the connection opens on first use and is reused by later messages on the same host.

Checks: invoke with one entry gives `{"stored": 1}`; validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 215 onprem http, PIN logged in the message
    B(215, provider="onprem", stage="prod", mode="ask", page="Logs", persona="beginner",
      sources=["docs/handlers.md#logging"],
      project=dict(files={
          "pskit.yml": "service: kiosk\n" + ONPREM.format(port=8614) + """functions:
  unlock:
    handler: app.kiosk.unlock
    events:
      - http: POST /unlock
""",
          "app/__init__.py": "",
          "app/kiosk.py": FUTURE + """import hmac
import os

from py_serverless_kit import Unauthorized


def unlock(event, ctx):
    body = event.http.json()
    ctx.logger.info(f"unlock attempt {body}")
    expected = os.environ.get("KIOSK_PIN", "")
    if not expected or not hmac.compare_digest(str(body.get("pin", "")), expected):
        raise Unauthorized("wrong pin")
    return {"unlocked": body.get("kiosk")}
""",
          "requirements.txt": ""}),
      user="I can see people's PIN codes on the Logs page, next to 'unlock attempt'. That can't be right. Can you make the log not show them?",
      steps=[
          S("read_file", path="app/kiosk.py"),
          S("invoke_local", function="unlock", method="POST", path="/unlock", data={"kiosk": "k-7", "pin": "0000"}),
          S("propose_plan", steps=["Log only the kiosk id as a structured field: `ctx.logger.info(\"unlock attempt\", extra={\"kiosk\": ...})`",
                                   "POST an unlock locally and check the log line; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/kiosk.py", content=FUTURE + """import hmac
import os

from py_serverless_kit import Unauthorized


def unlock(event, ctx):
    body = event.http.json()
    ctx.logger.info("unlock attempt", extra={"kiosk": body.get("kiosk")})
    expected = os.environ.get("KIOSK_PIN", "")
    if not expected or not hmac.compare_digest(str(body.get("pin", "")), expected):
        raise Unauthorized("wrong pin")
    return {"unlocked": body.get("kiosk")}
"""),
          S("invoke_local", function="unlock", method="POST", path="/unlock", data={"kiosk": "k-7", "pin": "0000"}),
          S("validate"),
      ],
      final="""The log line printed the whole request body, PIN included. Now it logs only the kiosk id, as a structured field [docs/handlers.md#logging].

- Before: `unlock attempt {'kiosk': 'k-7', 'pin': '0000'}`.
- After: `unlock attempt` (with `kiosk` as a field), no PIN. The 401 for a wrong PIN works as before.
- validate (onprem, prod): valid.

PINs that are already in old log files stay there; delete those logs if you need to."""),

    # ------------------------------------------------------------------ 216 onprem schedule, month + 1 in December
    B(216, provider="onprem", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: rent-reminders\n" + ONPREM.format(port=8615) + """functions:
  remind:
    handler: app.rent.remind
    events:
      - schedule:
          cron: "0 9 15 * *"
          input:
            today: "2026-11-15"
""",
          "app/__init__.py": "",
          "app/rent.py": FUTURE + """from datetime import date, timedelta


def remind(event, ctx):
    today = date.fromisoformat(event.data["today"])
    last_day = date(today.year, today.month + 1, 1) - timedelta(days=1)
    return {"due": last_day.isoformat()}
""",
          "requirements.txt": ""}),
      user="""ValueError: month must be in 1..12
tested remind with today 2026-12-15, november works""",
      steps=[
          S("read_file", path="app/rent.py"),
          S("invoke_local", function="remind", type="schedule", data={"today": "2026-12-15"}),
          S("propose_plan", steps=["Get the month length with `calendar.monthrange(year, month)[1]`, which works for December",
                                   "Run with 2026-12-15 locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/rent.py", content=FUTURE + """import calendar
from datetime import date


def remind(event, ctx):
    today = date.fromisoformat(event.data["today"])
    days = calendar.monthrange(today.year, today.month)[1]
    return {"due": date(today.year, today.month, days).isoformat()}
"""),
          S("invoke_local", function="remind", type="schedule", data={"today": "2026-12-15"}),
          S("validate"),
      ],
      final="""In December `today.month + 1` is `13`, which is not a month. `calendar.monthrange(year, month)[1]` gives the number of days in the month, so you never need month 13.

- 2026-12-15: `{"due": "2026-12-31"}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 217 onprem storage, prefix without the slash
    B(217, provider="onprem", stage="staging", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": "service: edi-drop\n" + ONPREM.format(port=8616) + """functions:
  edi:
    handler: app.edi.handle
    events:
      - storage: partner-files
""",
          "app/__init__.py": "",
          "app/edi.py": FUTURE + """
def handle(event, ctx):
    picked = [r.key for r in event.records if r.key.startswith("incoming")]
    return {"processed": picked}
""",
          "requirements.txt": ""}),
      user="edi also picks files from incoming-archive/. only incoming/ wanted",
      steps=[
          S("read_file", path="app/edi.py"),
          S("invoke_local", function="edi", type="storage",
            data=[{"key": "incoming/po-1.edi"}, {"key": "incoming-archive/po-0.edi"}]),
          S("propose_plan", steps=["Match the folder with the slash: `startswith(\"incoming/\")`",
                                   "Invoke with both keys; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/edi.py", content=FUTURE + """
def handle(event, ctx):
    picked = [r.key for r in event.records if r.key.startswith("incoming/")]
    return {"processed": picked}
"""),
          S("invoke_local", function="edi", type="storage",
            data=[{"key": "incoming/po-1.edi"}, {"key": "incoming-archive/po-0.edi"}]),
          S("validate"),
      ],
      final="""`"incoming-archive/...".startswith("incoming")` is true. Fixed to `"incoming/"`.

- Before: both keys. After: `["incoming/po-1.edi"]`.
- validate (onprem, staging): valid.

Alternative: `prefix: incoming/` on the storage event, so the host doesn't start the function for other files at all [docs/events.md#storage]."""),

    # ------------------------------------------------------------------ 218 onprem http, max() of a dict gives a key
    B(218, provider="onprem", stage="dev", mode="auto", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: quiz-night\n" + ONPREM.format(port=8617) + """functions:
  winner:
    handler: app.quiz.winner
    events:
      - http: GET /quiz/winner
""",
          "app/__init__.py": "",
          "app/quiz.py": FUTURE + """SCORES = {"ana": 42, "tom": 57, "zed": 12}


def winner(event, ctx):
    best = max(SCORES)
    return {"winner": best, "score": SCORES[best]}
""",
          "requirements.txt": ""}),
      user="quiz winner page say zed with 12 points. tom have 57!! why zed win",
      steps=[
          S("read_file", path="app/quiz.py"),
          S("invoke_local", function="winner", path="/quiz/winner"),
          S("propose_plan", steps=["Pick the highest score with `max(SCORES, key=SCORES.get)`; `max(SCORES)` compares the names"]),
          S("write_file", path="app/quiz.py", content=FUTURE + """SCORES = {"ana": 42, "tom": 57, "zed": 12}


def winner(event, ctx):
    best = max(SCORES, key=SCORES.get)
    return {"winner": best, "score": SCORES[best]}
"""),
          S("invoke_local", function="winner", path="/quiz/winner"),
          S("validate"),
      ],
      final="""`max(SCORES)` loops over the dict **keys** and picks the last name alphabetically, and `zed` comes last. `max(SCORES, key=SCORES.get)` compares the scores instead.

- Before: `{"winner": "zed", "score": 12}`.
- After: `{"winner": "tom", "score": 57}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 219 onprem http, dict mutated across requests
    B(219, provider="onprem", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: settings-api\n" + ONPREM.format(port=8618) + """functions:
  settings:
    handler: app.settings.get_settings
    events:
      - http: GET /settings
""",
          "app/__init__.py": "",
          "app/settings.py": FUTURE + """DEFAULTS = {"theme": "light", "lang": "en"}


def get_settings(event, ctx):
    settings = DEFAULTS
    if "lang" in event.http.query:
        settings["lang"] = event.http.query["lang"]
    settings["ui"] = "mobile" if event.http.query.get("mobile") == "1" else "desktop"
    return {"settings": settings, "defaults_lang": DEFAULTS["lang"]}
""",
          "requirements.txt": ""}),
      user="On the on-prem host, GET /settings sometimes returns lang=de for users who never asked for German. It seems to start after one user calls /settings?lang=de, and only a restart fixes it. The response includes defaults_lang for debugging, and that also turns into de. Please fix it so each request starts from the defaults.",
      steps=[
          S("read_file", path="app/settings.py"),
          S("invoke_local", function="settings", path="/settings?lang=de"),
          S("propose_plan", steps=["Copy the defaults per request (`dict(DEFAULTS)`) instead of changing the module-level dict",
                                   "GET /settings?lang=de locally (defaults_lang must stay en); validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/settings.py", content=FUTURE + """DEFAULTS = {"theme": "light", "lang": "en"}


def get_settings(event, ctx):
    settings = dict(DEFAULTS)
    if "lang" in event.http.query:
        settings["lang"] = event.http.query["lang"]
    settings["ui"] = "mobile" if event.http.query.get("mobile") == "1" else "desktop"
    return {"settings": settings, "defaults_lang": DEFAULTS["lang"]}
"""),
          S("invoke_local", function="settings", path="/settings?lang=de"),
          S("validate"),
      ],
      final="""`settings = DEFAULTS` doesn't copy anything: both names point to the same module-level dict. The first `?lang=de` request changed the defaults for everyone served by that process, until it restarted. `dict(DEFAULTS)` gives each request its own copy (enough here, because the values are plain strings).

- Before: `defaults_lang: "de"` after one request with `lang=de`.
- After: `settings.lang` is `de` for that request only, and `defaults_lang` stays `en`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 220 onprem http, int() of "2.0" quantity
    B(220, provider="onprem", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: cart-api\n" + ONPREM.format(port=8619) + """functions:
  add-line:
    handler: app.cart.add_line
    events:
      - http: POST /cart/lines
""",
          "app/__init__.py": "",
          "app/cart.py": FUTURE + """
def add_line(event, ctx):
    line = event.http.json()
    qty = int(line["qty"])
    return {"sku": line["sku"], "qty": qty}, 201
""",
          "requirements.txt": ""}),
      user="""ValueError: invalid literal for int() with base 10: '2.0'
the android app sends qty as "2.0". web sends "2". and someone sent abc""",
      steps=[
          S("read_file", path="app/cart.py"),
          S("invoke_local", function="add-line", method="POST", path="/cart/lines", data={"sku": "TEA-1", "qty": "2.0"}),
          S("propose_plan", steps=["Parse qty with `float()`, accept only whole positive numbers, and raise `BadRequest` for anything else",
                                   "POST qty \"2.0\" (201) and \"abc\" (400); validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/cart.py", content=FUTURE + """from py_serverless_kit import BadRequest


def parse_qty(raw):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise BadRequest("qty must be a number") from None
    if value < 1 or not value.is_integer():
        raise BadRequest("qty must be a whole number of at least 1")
    return int(value)


def add_line(event, ctx):
    line = event.http.json()
    return {"sku": line["sku"], "qty": parse_qty(line.get("qty"))}, 201
"""),
          S("invoke_local", function="add-line", method="POST", path="/cart/lines", data={"sku": "TEA-1", "qty": "2.0"}),
          S("invoke_local", function="add-line", method="POST", path="/cart/lines", data={"sku": "TEA-1", "qty": "abc"}),
          S("validate"),
      ],
      final="""`int("2.0")` fails: `int()` only reads whole-number text. `float()` reads `"2"`, `"2.0"` and `2`. The new `parse_qty` accepts only whole numbers of at least 1 and raises `BadRequest` otherwise. A bad value is now a 400 with a message, not a 500 [docs/handlers.md#errors].

- `"2.0"`: 201, `{"sku": "TEA-1", "qty": 2}`.
- `"abc"`: 400, `qty must be a number`.
- validate (onprem, staging): valid."""),
]
