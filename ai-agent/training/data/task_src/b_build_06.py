"""Category B (build / add), batch 6: on-premises only. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
CLUSTERS = json.dumps({"clusters": {"prod": {"orchestrator": "swarm", "master": "app-1", "servers": ["app-2"]}}},
                      indent=2)


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", provider="onprem", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 101
    B(101, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: device-registry
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8081
functions: {}
""",
          "requirements.txt": ""}),
      user="i want a page where i put a device number in the address and it shows that device. like /devices/7. if the number is wrong it should say not found",
      steps=[
          S("get_project"),
          S("search_docs", query="http path parameter {id}",
            docs=[D("docs/events.md", "http", words=160)]),
          S("propose_plan", steps=["Write `app/devices.py`: look up event.http.path_params[\"id\"] in a small sample table, raise NotFound when it is missing",
                                   "Add function `get-device` on `GET /devices/{id}`",
                                   "Validate for onprem and call /devices/7 locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/devices.py", content=FUTURE + """from py_serverless_kit import NotFound

DEVICES = {
    "7": {"id": 7, "name": "Front door camera", "room": "Lobby"},
    "12": {"id": 12, "name": "Server room sensor", "room": "B1"},
}


def get_device(event, ctx):
    device_id = event.http.path_params.get("id", "")
    device = DEVICES.get(device_id)
    if device is None:
        raise NotFound(f"device {device_id} not found")
    return device
"""),
          S("set_config", path="functions.get-device",
            value={"handler": "app.devices.get_device", "events": [{"http": "GET /devices/{id}"}]}),
          S("invoke_local", function="get-device", method="GET", path="/devices/7"),
      ],
      final="""Done. You now have a function `get-device` on the address `GET /devices/{id}`. The `{id}` part is the device number, and the handler reads it from `event.http.path_params["id"]` [docs/events.md#http].

- `pskit validate` (onprem): valid.
- Local call to `/devices/7`: 200, `{"id": 7, "name": "Front door camera", "room": "Lobby"}`.
- An unknown number raises `NotFound`, which becomes a 404 JSON error [docs/handlers.md#errors].

The two devices are sample data in `app/devices.py`. Replace them with your real list or database later.

Test again: **Test** page > **▶ Run locally**, or `pskit invoke -f get-device --method GET --path /devices/12`. Deploy: **Deploy** page or `pskit deploy -s dev`; then open `http://127.0.0.1:8081/devices/7`."""),

    # ------------------------------------------------------------------ 102
    B(102, stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises", "docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: media
provider:
  name: onprem
  region: local
  options:
    port: 8082
functions:
  upload-api:
    handler: app.api.upload
    events:
    - http: POST /uploads
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def upload(event, ctx):
    return {"accepted": True}, 202
""",
          "requirements.txt": ""}),
      user="thumbnail worker on builtin queue `thumbnails`: batch 5, dlq thumbnails-dlq after 3 tries. records without image_id -> fail only that one",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/thumbs.py`: loop records, BatchResult.fail(record) when image_id is missing",
                                   "Add `thumbnail-worker` with queue {name: thumbnails, batch_size: 5, dead_letter: thumbnails-dlq, max_receive: 3}",
                                   "Validate (onprem, staging), invoke with one good and one bad record"]),
          S("write_file", path="app/thumbs.py", content=FUTURE + """from py_serverless_kit import BatchResult


def make_thumbnails(event, ctx):
    result = BatchResult()
    for record in event.records:
        job = record.json(default={}) or {}
        if not job.get("image_id"):
            ctx.logger.warning("no image_id", extra={"record": record.id})
            result.fail(record)
            continue
        ctx.logger.info("thumbnail", extra={"image_id": job["image_id"]})
    return result
"""),
          S("set_config", path="functions.thumbnail-worker",
            value={"handler": "app.thumbs.make_thumbnails",
                   "events": [{"queue": {"name": "thumbnails", "batch_size": 5,
                                         "dead_letter": "thumbnails-dlq", "max_receive": 3}}]}),
          S("invoke_local", function="thumbnail-worker", type="queue",
            data=[{"image_id": "img-881"}, {"size": "small"}]),
      ],
      final="""Added `thumbnail-worker` on the built-in queue `thumbnails` (`batch_size: 5`, `dead_letter: thumbnails-dlq`, `max_receive: 3`).

- validate (onprem, staging): valid.
- invoke with 2 records: the second (no `image_id`) is in `batchItemFailures`. On premises the host retries only the failed ids, and after 3 receives the message moves to `thumbnails-dlq` [docs/handlers.md#batchresult].

Nothing consumes `thumbnails-dlq` yet. Add a function on it if you want alerts. After deploy, enqueue with `POST /__pskit/queues/thumbnails` [docs/providers.md#onprem-on-premises]. Re-test: `pskit invoke -f thumbnail-worker -t queue -d '[{"image_id": "x"}]'`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 103
    B(103, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: price-watch
provider:
  name: onprem
  region: local
  options:
    port: 8083
functions:
  check-prices:
    handler: app.prices.check
""",
          "app/__init__.py": "",
          "app/prices.py": FUTURE + """

def check(event, ctx):
    shop = (event.data or {}).get("shop", "all")
    ctx.logger.info("checking prices", extra={"shop": shop})
    return {"checked": shop}
""",
          "requirements.txt": ""}),
      user="check-prices must run alone every 15 min, and give it shop=books as input pls",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add a schedule to `check-prices`: rate 15 minutes, input {shop: books}",
                                   "Validate for onprem and run the schedule locally"],
            result={"decision": "approved", "note": "make it every 10 minutes, 15 is too slow"}),
          S("set_config", path="functions.check-prices.events",
            value=[{"schedule": {"rate": "10 minutes", "input": {"shop": "books"}}}],
            say="You asked for 10 minutes instead of 15, so I'm using `rate: 10 minutes`."),
          S("invoke_local", function="check-prices", type="schedule"),
      ],
      final="""Done, with your change: `check-prices` now runs **every 10 minutes** with the input `{"shop": "books"}`:

```yaml
functions:
  check-prices:
    handler: app.prices.check
    events:
      - schedule: {rate: 10 minutes, input: {shop: books}}
```

The input arrives as `event.data` [docs/events.md#schedule].

- `pskit validate` (onprem): valid.
- Local schedule run: `{"checked": "books"}`.

On premises the host runs the schedule itself, so it starts after a deploy: **Deploy** page or `pskit deploy -s dev`. Test again: `pskit invoke -f check-prices -t schedule`."""),

    # ------------------------------------------------------------------ 104
    B(104, stage="prod", mode="auto", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: accounts-payable
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8084
    services:
      storage: {use: directory, path: /srv/ap/buckets}
functions: {}
""",
          "requirements.txt": ""}),
      user="When a PDF is dropped into the `invoices` bucket under `incoming/`, log the file name and size and return them. Only new files, not deletes, and ignore anything that is not .pdf.",
      steps=[
          S("get_project"),
          S("search_docs", query="storage event prefix suffix created",
            docs=[D("docs/events.md", "storage", words=150)]),
          S("propose_plan", steps=["Write `app/invoices.py`: for each record log key and size",
                                   "Add `on-invoice` with storage {bucket: invoices, prefix: incoming/, suffix: .pdf, events: [created]}",
                                   "Validate (onprem, prod) and invoke with a sample object"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/invoices.py", content=FUTURE + """

def on_invoice(event, ctx):
    seen = []
    for record in event.records:
        ctx.logger.info("new invoice", extra={"key": record.key, "size": record.size})
        seen.append({"key": record.key, "size": record.size})
    return {"invoices": seen}
"""),
          S("set_config", path="functions.on-invoice",
            value={"handler": "app.invoices.on_invoice",
                   "events": [{"storage": {"bucket": "invoices", "prefix": "incoming/", "suffix": ".pdf",
                                           "events": ["created"]}}]}),
          S("invoke_local", function="on-invoice", type="storage",
            data={"bucket": "invoices", "key": "2026-11/acme-4471.pdf", "size": 48213, "action": "created"}),
      ],
      final="""Added `on-invoice`:

```yaml
functions:
  on-invoice:
    handler: app.invoices.on_invoice
    events:
      - storage: {bucket: invoices, prefix: incoming/, suffix: .pdf, events: [created]}
```

Your storage service is `directory` at `/srv/ap/buckets`, so the bucket is the folder `/srv/ap/buckets/invoices`. Only `.pdf` files created under `incoming/` fire it. Files that are already there when the host first starts are recorded and not sent [docs/providers.md#onprem-on-premises].

- validate (onprem, prod): valid.
- invoke with a sample object: returned `{"invoices": [{"key": "2026-11/acme-4471.pdf", "size": 48213}]}` and logged it.

Deploy: **Deploy** page (typed confirmation for prod) or `pskit deploy -s prod`. Re-test: `pskit invoke -f on-invoice -t storage -d '{"bucket": "invoices", "key": "x.pdf", "size": 10}'`."""),

    # ------------------------------------------------------------------ 105
    B(105, stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#topic", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: fulfilment
provider:
  name: onprem
  region: local
  options:
    port: 8085
functions:
  publish-order:
    handler: app.orders.publish
    events:
    - http: POST /orders
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def publish(event, ctx):
    return {"published": True}, 202
""",
          "requirements.txt": ""}),
      user="On AWS we had an SNS topic `order-events` and a Lambda subscribed with a filter policy {\"event_type\": [\"order.shipped\"]}. It emailed the customer. How do I get the same subscriber here on-prem? Just log the email for now.",
      steps=[
          S("get_project"),
          S("search_docs", query="topic filter on premises attributes",
            docs=[D("docs/events.md", "topic", words=120),
                  D("docs/providers.md", "onprem-on-premises", start="| topic |", end="JSON body fields |")]),
          S("propose_plan", steps=["Write `app/shipping.py`: for each record read the message and log the customer email",
                                   "Add `notify-shipped` with topic {name: order-events, filter: {event_type: [order.shipped]}}",
                                   "Validate (onprem, staging) and invoke with a sample message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/shipping.py", content=FUTURE + """

def notify_shipped(event, ctx):
    sent = []
    for record in event.records:
        order = record.json(default={}) or {}
        email = order.get("customer_email")
        ctx.logger.info("would email customer", extra={"to": email, "order": order.get("order_id")})
        sent.append(email)
    return {"emailed": sent}
"""),
          S("set_config", path="functions.notify-shipped",
            value={"handler": "app.shipping.notify_shipped",
                   "events": [{"topic": {"name": "order-events", "filter": {"event_type": ["order.shipped"]}}}]}),
          S("invoke_local", function="notify-shipped", type="topic",
            data=[{"order_id": "A-1009", "event_type": "order.shipped", "customer_email": "kim@example.com"}]),
      ],
      final="""Same shape as your SNS subscription. The filter policy becomes `filter` on the topic event:

```yaml
functions:
  notify-shipped:
    handler: app.shipping.notify_shipped
    events:
      - topic: {name: order-events, filter: {event_type: [order.shipped]}}
```

On premises the topic is a built-in fan-out in the host. `filter` is an exact match on message attributes first, then on JSON body fields, so a body with `"event_type": "order.shipped"` also matches [docs/providers.md#onprem-on-premises].

- `pskit validate` (onprem, staging): valid.
- Local invoke with a sample message: `{"emailed": ["kim@example.com"]}`. The email is only logged for now.

After deploy, publish with `POST /__pskit/topics/order-events`. Re-test: `pskit invoke -f notify-shipped -t topic -d '[{"event_type": "order.shipped", "customer_email": "a@example.com"}]'`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 106
    B(106, stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/smtp/README.md#what-the-handler-receives", "docs/smtp/README.md#change-it"],
      project=dict(files={
          "pskit.yml": """service: order-desk
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8086
resources:
  orders-mail:
    type: smtp
    external: true
    connection: {host: 203.0.113.25, port: 25, domains: orders.example.com, hostname: mail.orders.example.com}
functions:
  log-mail:
    handler: app.mail.log_mail
    events:
    - smtp: {resource: orders-mail}
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """

def log_mail(event, ctx):
    ctx.logger.info("mail", extra={"subject": (event.data or {}).get("subject")})
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="Add a second function on the orders-mail SMTP server, `extract-order`. It should find order numbers like ORD-123456 in the subject or the text body and return them as a sorted, de-duplicated list together with the sender. Keep log-mail as it is.",
      steps=[
          S("get_project"),
          S("search_docs", query="smtp add another function trigger",
            docs=[D("docs/smtp/README.md", "change-it")]),
          S("propose_plan", steps=["Write `app/extract.py`: regex ORD-\\d{6} over subject + text, return {sender, orders}",
                                   "Add function `extract-order` with `- smtp: {resource: orders-mail}` (log-mail unchanged)",
                                   "Validate (onprem, prod) and run a test mail locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/extract.py", content=FUTURE + """import re

ORDER = re.compile(r"\\bORD-\\d{6}\\b")


def extract_order(event, ctx):
    mail = event.data or {}
    text = f"{mail.get('subject') or ''}\\n{mail.get('text') or ''}"
    orders = sorted(set(ORDER.findall(text)))
    ctx.logger.info("orders in mail", extra={"orders": orders})
    return {"sender": mail.get("from"), "orders": orders}
"""),
          S("set_config", path="functions.extract-order",
            value={"handler": "app.extract.extract_order", "events": [{"smtp": {"resource": "orders-mail"}}]}),
          S("invoke_local", function="extract-order", type="smtp",
            data={"from": "buyer@example.org", "to": ["po@orders.example.com"],
                  "subject": "Re: ORD-204118 and ORD-204120",
                  "text": "Please ship ORD-204120 first. ORD-204118 can wait."}),
      ],
      final="""Added `extract-order` next to `log-mail`. Both run for every mail that `orders-mail` receives:

```yaml
functions:
  extract-order:
    handler: app.extract.extract_order
    events:
      - smtp: {resource: orders-mail}
```

- `pskit validate` (onprem, prod): valid.
- Local test mail: `{"sender": "buyer@example.org", "orders": ["ORD-204118", "ORD-204120"]}`. The duplicates from the body were removed.

The SMTP server itself does not change. The new function only needs a deploy [docs/smtp/README.md#change-it]: **Deploy** page (typed confirmation for `prod`) or `pskit deploy -s prod`. Test again: **Test** page, or `pskit invoke -f extract-order -t smtp -d '{"from": "a@example.org", "subject": "ORD-000001", "text": ""}'`."""),

    # ------------------------------------------------------------------ 107
    B(107, stage="staging", mode="auto", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#retry-and-catch", "docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": """service: checkout
provider:
  name: onprem
  region: local
  options:
    port: 8087
functions:
  validate-cart:
    handler: app.steps.validate_cart
  charge-card:
    handler: app.steps.charge_card
  send-receipt:
    handler: app.steps.send_receipt
""",
          "app/__init__.py": "",
          "app/steps.py": FUTURE + """

def validate_cart(event, ctx):
    cart = dict(event.data or {})
    return {**cart, "valid": bool(cart.get("items"))}


def charge_card(event, ctx):
    cart = dict(event.data or {})
    return {**cart, "charged": True}


def send_receipt(event, ctx):
    cart = dict(event.data or {})
    return {**cart, "receipt": "sent"}
""",
          "requirements.txt": ""}),
      user="Workflow `place-order`: validate-cart -> charge-card -> send-receipt. Retry charge-card on any error 3 times, 5 s apart, doubling. Whole run max 300 s.",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow retry max_attempts interval backoff",
            docs=[D("docs/workflows.md", "retry-and-catch", words=170)]),
          S("propose_plan", steps=["Add workflow `place-order` (timeout 300): Validate -> Charge (retry States.ALL x3, 5 s, backoff 2) -> Receipt (end)",
                                   "Validate (onprem, staging), invoke charge-card as a workflow task"]),
          S("set_config", path="workflows.place-order",
            value={"timeout": 300, "start_at": "Validate",
                   "states": {"Validate": {"type": "task", "function": "validate-cart", "next": "Charge"},
                              "Charge": {"type": "task", "function": "charge-card", "next": "Receipt",
                                         "retry": [{"errors": ["States.ALL"], "max_attempts": 3,
                                                    "interval_seconds": 5, "backoff_rate": 2}]},
                              "Receipt": {"type": "task", "function": "send-receipt", "end": True}}}),
          S("invoke_local", function="charge-card", type="workflow", data={"cart_id": "c-77", "items": [1, 2]}),
      ],
      final="""Added `place-order`:

```yaml
workflows:
  place-order:
    timeout: 300
    start_at: Validate
    states:
      Validate: {type: task, function: validate-cart, next: Charge}
      Charge:
        type: task
        function: charge-card
        next: Receipt
        retry:
          - {errors: [States.ALL], max_attempts: 3, interval_seconds: 5, backoff_rate: 2}
      Receipt: {type: task, function: send-receipt, end: true}
```

So a failing charge waits 5 s, then 10 s, then 20 s [docs/workflows.md#retry-and-catch].

- validate (onprem, staging): valid. On premises it runs on the embedded engine inside the host.
- `charge-card` run as a workflow task: returned the cart with `"charged": true`.

Run the whole flow locally: `pskit workflow run place-order -i '{"cart_id": "c-77", "items": [1]}' --history`. After deploy, `POST /workflows/place-order` answers `202` with an `execution_id` [docs/workflows.md#embedded-orchestrator]. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 108
    B(108, stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises", "docs/getting-started.md"],
      project=dict(files={
          "pskit.yml": """service: kiosk
provider:
  name: onprem
functions: {}
""",
          "requirements.txt": ""}),
      user="this is a brand new project. i only want it on our own computer, nothing in the cloud. can you make it work with a simple hello?",
      steps=[
          S("get_project"),
          S("search_docs", query="onprem provider host port local process",
            docs=[D("docs/providers.md", "onprem-on-premises", end="poll_seconds: 0.5")]),
          S("propose_plan", steps=["Set provider.region `local` and options host 127.0.0.1, port 8095",
                                   "Write `app/hello.py` and add function `hello` on GET /hello",
                                   "Validate for onprem and call /hello locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.region", value="local"),
          S("set_config", path="provider.options", value={"host": "127.0.0.1", "port": 8095}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/hello.py", content=FUTURE + """

def hello(event, ctx):
    name = event.http.query.get("name", "there")
    return {"message": f"Hello, {name}!"}
"""),
          S("set_config", path="functions.hello",
            value={"handler": "app.hello.hello", "events": [{"http": "GET /hello"}]}),
          S("invoke_local", function="hello", method="GET", path="/hello?name=Kiosk"),
      ],
      final="""Your project is ready to run on your own computer, with no cloud involved. The provider is `onprem`, which runs your functions in one Python process on this machine:

```yaml
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8095}
functions:
  hello:
    handler: app.hello.hello
    events:
      - http: GET /hello
```

- `pskit validate`: valid.
- Local call `/hello?name=Kiosk`: 200, `{"message": "Hello, Kiosk!"}`.

`host: 127.0.0.1` means only this computer can call it. Use `0.0.0.0` if other machines need to reach it [docs/providers.md#onprem-on-premises].

To start it: **Deploy** page > **Deploy**, or `pskit deploy -s dev`. Then open `http://127.0.0.1:8095/hello`. To test without deploying: **Test** page > **▶ Run locally**."""),

    # ------------------------------------------------------------------ 109
    B(109, stage="prod", mode="ask", page="Deploy", persona="terse_expert",
      sources=["docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine",
               "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: inventory
provider:
  name: onprem
  region: local
  options:
    port: 8088
functions:
  stock:
    handler: app.stock.get_stock
    events:
    - http: GET /stock
""",
          "app/__init__.py": "",
          "app/stock.py": FUTURE + """

def get_stock(event, ctx):
    return {"items": 0}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="prod -> saved server app-1, /opt/pskit/inventory. box has no python. LAN must reach it.",
      steps=[
          S("get_project"),
          S("search_docs", query="deploy to saved server python bundle",
            docs=[D("docs/resource-guides/onprem/services.md", "deploy-the-functions-to-a-chosen-machine",
                    end="stay. In the studio, **Deploy → Machine** picks one for that run.")]),
          S("propose_plan", steps=["provider.options.deploy: {server: app-1, path: /opt/pskit/inventory, python: bundle}",
                                   "provider.options.host: 0.0.0.0 (LAN access)",
                                   "Validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy",
            value={"server": "app-1", "path": "/opt/pskit/inventory", "python": "bundle"}),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
      ],
      final="""Set:

```yaml
provider:
  options:
    host: 0.0.0.0
    port: 8088
    deploy: {server: app-1, path: /opt/pskit/inventory, python: bundle}
```

- `server: app-1`: the saved server's host, user, port and login are used, and the method defaults to ssh [docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine].
- `python: bundle`: a portable CPython is fetched at apply and copied with the app, so the box needs no Python. The first apply needs network on this machine [docs/providers.md#onprem-on-premises].
- `host: 0.0.0.0`: the host listens on the LAN. Open 8088 in the server's firewall.

validate (onprem, prod): valid. Before the host change it warned that a remote host bound to 127.0.0.1 only takes local traffic; that warning is gone.

Deploy: **Deploy** page (typed confirmation for prod) or `pskit deploy -s prod`. It prints `deployed on: app-1 (...)`."""),

    # ------------------------------------------------------------------ 110
    B(110, stage="dev", mode="auto", page="Resources", persona="informal_non_native",
      sources=["docs/resource-guides/onprem/database.md#3-declare-it-in-pskityml", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: clinic
provider:
  name: onprem
  region: local
  options:
    port: 8089
functions:
  patients:
    handler: app.clinic.patients
    events:
    - http: GET /patients
  reminders:
    handler: app.clinic.reminders
    events:
    - schedule: 0 7 * * *
  status:
    handler: app.clinic.status
    events:
    - http: GET /status
""",
          "app/__init__.py": "",
          "app/clinic.py": FUTURE + """

def patients(event, ctx):
    return []


def reminders(event, ctx):
    return {"sent": 0}


def status(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="we have postgres on db-1.example.com port 5432, database clinic, user clinic_app. password is in CLINIC_DB_PASSWORD. patients and reminders need it, status no. patients should show which db it use",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add resources.clinic-db: database, external, connection host/port/database/user + password_env CLINIC_DB_PASSWORD, functions [patients, reminders]",
                                   "Change `patients` to return the bound database (host, database, password set?)",
                                   "Validate for onprem, invoke GET /patients"]),
          S("set_config", path="resources.clinic-db",
            value={"type": "database", "external": True,
                   "connection": {"host": "db-1.example.com", "port": 5432, "database": "clinic",
                                  "user": "clinic_app", "password_env": "CLINIC_DB_PASSWORD"},
                   "functions": ["patients", "reminders"]}),
          S("write_file", path="app/clinic.py", content=FUTURE + """from py_serverless_kit import resource


def patients(event, ctx):
    db = resource("clinic-db")
    return {
        "db": f'{db["host"]}:{db["port"]}/{db["database"]}',
        "user": db["user"],
        "password_set": bool(ctx.env.get(db["password_env"])),
        "patients": [],
    }


def reminders(event, ctx):
    return {"sent": 0}


def status(event, ctx):
    return {"ok": True}
"""),
          S("validate"),
          S("invoke_local", function="patients", method="GET", path="/patients"),
      ],
      final="""Done:

```yaml
resources:
  clinic-db:
    type: database
    external: true
    connection:
      host: db-1.example.com
      port: 5432
      database: clinic
      user: clinic_app
      password_env: CLINIC_DB_PASSWORD
    functions: [patients, reminders]
```

`status` does not get it, because only the listed functions are bound. pskit.yml has only the variable's *name*, never the password [docs/resource-guides/onprem/database.md#3-declare-it-in-pskityml].

- validate (onprem): valid.
- `GET /patients`: 200, `{"db": "db-1.example.com:5432/clinic", "user": "clinic_app", "password_set": false, "patients": []}`. `password_set` is false because `CLINIC_DB_PASSWORD` is not set in this shell. Set it where the host runs.

To really query, add `psycopg[binary]` to requirements.txt and connect with these values. Re-test: `pskit invoke -f patients --method GET --path /patients`. Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 111
    B(111, stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#queue-drivers", "docs/resource-guides/onprem/services.md#what-gets-written"],
      project=dict(files={
          "pskit.yml": """service: notifier
provider:
  name: onprem
  region: local
  options:
    port: 8090
functions: {}
""",
          "requirements.txt": ""}),
      user="We already run Redis on cache.example.com. Use the list key `push-jobs` as a queue: a function `push-sender` consumes it, 20 messages at a time. The Redis URL has a password, so it must come from the PUSH_REDIS_URL variable on the host, not from pskit.yml.",
      steps=[
          S("get_project"),
          S("search_docs", query="redis queue driver url key",
            docs=[D("docs/resources.md", "queue-drivers", end="| `redis_stream` |"),
                  D("docs/resources.md", "on-premises-drivers", start="**Secrets.**", end="the secret never lands in Terraform state or `pskit_host.json`.")]),
          S("propose_plan", steps=["Add resources.push-jobs: queue, external, options {driver: redis, url_env: PUSH_REDIS_URL, key: push-jobs}",
                                   "Write `app/push.py` and add `push-sender` with queue {resource: push-jobs, batch_size: 20}",
                                   "Validate (onprem, staging) and invoke with two messages"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.push-jobs",
            value={"type": "queue", "external": True,
                   "options": {"driver": "redis", "url_env": "PUSH_REDIS_URL", "key": "push-jobs"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/push.py", content=FUTURE + """

def send(event, ctx):
    sent = 0
    for record in event.records:
        job = record.json(default={}) or {}
        ctx.logger.info("push", extra={"device": job.get("device"), "title": job.get("title")})
        sent += 1
    return {"sent": sent}
"""),
          S("set_config", path="functions.push-sender",
            value={"handler": "app.push.send", "events": [{"queue": {"resource": "push-jobs", "batch_size": 20}}]}),
          S("invoke_local", function="push-sender", type="queue",
            data=[{"device": "d-1", "title": "Your order shipped"}, {"device": "d-2", "title": "Sale today"}]),
      ],
      final="""Added the existing Redis list as a queue resource and a consumer:

```yaml
resources:
  push-jobs:
    type: queue
    external: true
    options: {driver: redis, url_env: PUSH_REDIS_URL, key: push-jobs}
functions:
  push-sender:
    handler: app.push.send
    events:
      - queue: {resource: push-jobs, batch_size: 20}
```

`url_env` means the host reads the URL from `PUSH_REDIS_URL` in its own environment when it starts, so the password never reaches pskit.yml or Terraform state. If the variable is missing, the host stops with an error naming it [docs/resources.md#on-premises-drivers]. You can also ship it in `provider.options.env_file`.

- `pskit validate` (onprem, staging): valid.
- Local invoke with 2 messages: `{"sent": 2}`.

Messages that other programs `LPUSH` onto `push-jobs` are delivered too [docs/resources.md#queue-drivers]. Deploy: **Deploy** page or `pskit deploy -s staging`. After that, **Resources** > **Test** sends a test message."""),

    # ------------------------------------------------------------------ 112
    B(112, stage="prod", mode="ask", page="Cluster", persona="terse_expert",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: onprem
  region: local
  options:
    port: 8080
functions:
  web:
    handler: app.web.home
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/web.py": FUTURE + """

def home(event, ctx):
    return {"shop": "open"}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="move shop to cluster prod. 3 web replicas, 0.5 cpu + 512 MB each. admin token from PSKIT_ADMIN_TOKEN",
      steps=[
          S("get_project"),
          S("search_docs", query="options.cluster replicas cpu memory",
            docs=[D("docs/cluster.md", "set-up", start="4. **Point the functions at the cluster**",
                    end="admin_token: \"${env:PSKIT_ADMIN_TOKEN}\"")]),
          S("propose_plan", steps=["provider.options.cluster: {name: prod, replicas: 3, cpu: 0.5, memory: 512}",
                                   "provider.options.admin_token: ${env:PSKIT_ADMIN_TOKEN, }",
                                   "provider.options.host: 0.0.0.0 so users reach the port on every server",
                                   "Validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.cluster",
            value={"name": "prod", "replicas": 3, "cpu": 0.5, "memory": 512}),
          S("set_config", path="provider.options.admin_token", value="${env:PSKIT_ADMIN_TOKEN, }"),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
      ],
      final="""Set:

```yaml
provider:
  options:
    port: 8080
    host: 0.0.0.0
    cluster: {name: prod, replicas: 3, cpu: 0.5, memory: 512}
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"
```

That gives 3 web replicas plus the 1 main replica, each reserving 0.5 CPU and 512 MB [docs/cluster.md#set-up]. The token is read from `PSKIT_ADMIN_TOKEN` when you deploy. With the empty default, validate passes even when the variable is unset, but then `/__pskit/*` has no token, so export it before deploying.

validate (onprem, prod): valid. Until `host: 0.0.0.0` was set it warned that the host bound to 127.0.0.1 on the target, which would keep users out.

Deploy: **Deploy** page (Run on > Scaling cluster, typed confirmation for prod) or `pskit deploy -s prod`. Docker must run on this machine to build the image. The old single-host deployment keeps running until you remove it there."""),

    # ------------------------------------------------------------------ 113
    B(113, stage="staging", mode="auto", page="Load balancers", persona="beginner",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: onprem
  region: local
  options:
    port: 8080
    deploy: {server: app-1, python: bundle}
functions:
  catalog:
    handler: app.catalog.items
    events:
    - http: GET /items
""",
          "app/__init__.py": "",
          "app/catalog.py": FUTURE + """

def items(event, ctx):
    return [{"sku": "A1"}]
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="my teammate made a load balancer called edge. how do i put this shop on it so people open it at edge/shop? can you set it up",
      steps=[
          S("get_project"),
          S("search_docs", query="put a project on a load balancer balancer option path",
            docs=[D("docs/load-balancers.md", "create-one-and-put-projects-on-it", start="A project names it",
                    end="`/shop` redirects to `/shop/`.")]),
          S("propose_plan", steps=["provider.options.balancer: {name: edge, path: shop}",
                                   "provider.options.host: 0.0.0.0 and advertise: http://192.0.2.10:8080 (app-1), so the load balancer can reach it",
                                   "Validate for onprem (staging)"]),
          S("set_config", path="provider.options.balancer", value={"name": "edge", "path": "shop"}),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
          S("set_config", path="provider.options.advertise", value="http://192.0.2.10:8080"),
      ],
      final="""Your shop is now set to go behind the `edge` load balancer at the path `/shop/`:

```yaml
provider:
  options:
    host: 0.0.0.0
    advertise: http://192.0.2.10:8080
    balancer: {name: edge, path: shop}
```

- `balancer`: every deploy adds or updates the route on `edge`, and `pskit remove` drops it. A request to `/shop/items` reaches your function as `/items` [docs/load-balancers.md#create-one-and-put-projects-on-it].
- `host: 0.0.0.0` and `advertise`: the load balancer must reach the shop on app-1. A host on 127.0.0.1 can't be reached. I used app-1's saved address; change it if the load balancer uses another one. Port 8080 must be open from the load balancer to app-1.

validate (onprem, staging): valid.

It takes effect on the next deploy: **Deploy** page or `pskit deploy -s staging`. Afterwards `pskit lb status edge` lists the route."""),

    # ------------------------------------------------------------------ 114
    B(114, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#variables", "docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: rates
provider:
  name: onprem
  region: local
  options:
    port: 8091
functions:
  fx:
    handler: app.fx.rate
    events:
    - http: GET /fx
""",
          "app/__init__.py": "",
          "app/fx.py": FUTURE + """

def rate(event, ctx):
    return {"pair": "EUR/USD"}
""",
          "requirements.txt": ""}),
      user="fx function need partner url. on my pc i have env PARTNER_URL, but if not set use https://rates.example.com. and show the url in response so i see it works",
      steps=[
          S("get_project"),
          S("search_docs", query="env variable default value pskit.yml",
            docs=[D("docs/configuration.md", "variables", end="| `${env:NAME, default}`")]),
          S("propose_plan", steps=["Add functions.fx.environment.PARTNER_URL: ${env:PARTNER_URL, https://rates.example.com}",
                                   "Return ctx.env[\"PARTNER_URL\"] from `rate`",
                                   "Validate for onprem and call GET /fx"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.fx.environment",
            value={"PARTNER_URL": "${env:PARTNER_URL, https://rates.example.com}"}),
          S("write_file", path="app/fx.py", content=FUTURE + """

def rate(event, ctx):
    return {"pair": "EUR/USD", "source": ctx.env.get("PARTNER_URL", "")}
"""),
          S("validate"),
          S("invoke_local", function="fx", method="GET", path="/fx"),
      ],
      final="""Done. `fx` now has:

```yaml
functions:
  fx:
    environment:
      PARTNER_URL: ${env:PARTNER_URL, https://rates.example.com}
```

`${env:PARTNER_URL, ...}` takes the value from your shell, and the part after the comma is used when it is not set [docs/configuration.md#variables]. The handler reads it with `ctx.env`.

- `pskit validate` (onprem): valid.
- `GET /fx`: 200, `{"pair": "EUR/USD", "source": "https://rates.example.com"}`. Here `PARTNER_URL` is not set, so the default is used.

Note: the value is taken on the machine where you run `pskit deploy`. Test with your variable: set `PARTNER_URL`, then run `pskit invoke -f fx --method GET --path /fx` again. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 115
    B(115, stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/placement.md", "docs/placement.md#how-the-groups-work-together"],
      project=dict(files={
          "pskit.yml": """service: docscan
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
functions:
  api:
    handler: app.api.submit
    events:
    - http: POST /scan
  ocr:
    handler: functions.ocr.handler.main
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """from py_serverless_kit import invoke


def submit(event, ctx):
    doc = event.http.json(default={}) or {}
    return invoke("ocr", doc)
""",
          "functions/__init__.py": "",
          "functions/ocr/__init__.py": "",
          "functions/ocr/handler.py": FUTURE + """

def main(event, ctx):
    doc = dict(event.data or {})
    return {"doc": doc.get("name"), "text": "(ocr result)"}
""",
          "functions/ocr/requirements.txt": "",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="The OCR function needs the GPU, so run `ocr` on the saved server gpu-box and everything else (the api) on app-1. The api calls ocr with invoke(), that must keep working across the two servers.",
      steps=[
          S("get_project"),
          S("search_docs", query="placement groups server functions default",
            docs=[D("docs/placement.md", "functions-on-several-servers-on-premises", end="# this machine"),
                  D("docs/placement.md", "how-the-groups-work-together", end="| an HTTP request")]),
          S("propose_plan", steps=["provider.options.placement: default `api` group on app-1, group `gpu` on gpu-box with functions [ocr]",
                                   "Validate for onprem (prod)"],
            result={"decision": "approved", "note": "call the GPU group `vision`, not `gpu`"}),
          S("set_config", path="provider.options.placement",
            value={"default": "api", "groups": {"api": {"server": "app-1"},
                                                 "vision": {"server": "gpu-box", "functions": ["ocr"]}}},
            say="Using the group name `vision` as you asked."),
      ],
      final="""Set, with the group named `vision` as you asked:

```yaml
provider:
  options:
    host: 0.0.0.0
    port: 8080
    placement:
      default: api
      groups:
        api:    {server: app-1}
        vision: {server: gpu-box, functions: [ocr]}
```

`api` (and every function not listed, plus any workflow) runs on app-1. `ocr` runs on gpu-box with only its own code and `functions/ocr/requirements.txt`. `invoke("ocr", doc)` in `api` keeps working: it runs on gpu-box and the result (or the error) comes back [docs/placement.md#how-the-groups-work-together].

validate (onprem, prod): valid, with one warning: the servers must already have python3.12 on PATH. If app-1 or gpu-box has no Python, say so and I'll add `options.deploy.python: bundle`, which ships a portable interpreter.

The two servers call each other on port 8080, so open it between app-1 and gpu-box. Deploy both groups in one go: **Deploy** page (typed confirmation for prod) or `pskit deploy -s prod`. The **Deploy** page's "Where functions run" panel shows the same layout."""),

    # ------------------------------------------------------------------ 116
    B(116, stage="staging", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#errors", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: bookings
provider:
  name: onprem
  region: local
  options:
    port: 8092
functions: {}
""",
          "requirements.txt": ""}),
      user="My Lambda behind API Gateway returned {'statusCode': 422, 'body': json.dumps({...})} when guests or date were missing, and 201 with the booking otherwise. Recreate POST /bookings without the statusCode dict juggling.",
      steps=[
          S("get_project"),
          S("search_docs", query="return status code 201 error 422",
            docs=[D("docs/handlers.md", "errors", end="# -> 422 {\"error\": \"invalid order\", \"status\": 422, \"details\": {\"field\": \"amount\"}}")]),
          S("propose_plan", steps=["Write `app/bookings.py`: UnprocessableEntity with details for missing fields, return (booking, 201)",
                                   "Add function `create-booking` on POST /bookings",
                                   "Validate (onprem, staging) and POST a valid booking locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/bookings.py", content=FUTURE + """import uuid

from py_serverless_kit import UnprocessableEntity


def create_booking(event, ctx):
    body = event.http.json(default={}) or {}
    missing = [f for f in ("guests", "date") if not body.get(f)]
    if missing:
        raise UnprocessableEntity("missing fields", details={"fields": missing})
    booking = {"id": str(uuid.uuid4()), "guests": int(body["guests"]), "date": body["date"]}
    return booking, 201
"""),
          S("set_config", path="functions.create-booking",
            value={"handler": "app.bookings.create_booking", "events": [{"http": "POST /bookings"}]}),
          S("invoke_local", function="create-booking", method="POST", path="/bookings",
            data={"guests": 4, "date": "2026-12-24"}),
      ],
      final="""In pskit you return the body and the status, and raise an error class for failures. No `statusCode`/`json.dumps` needed:

- success: `return booking, 201` (Flask-style tuple) [docs/handlers.md#returning-a-response]
- missing fields: `raise UnprocessableEntity("missing fields", details={"fields": [...]})` gives `422 {"error": ..., "status": 422, "details": ...}` [docs/handlers.md#errors]

Added `create-booking` on `POST /bookings`.

- `pskit validate` (onprem, staging): valid.
- Local POST `{"guests": 4, "date": "2026-12-24"}`: 201 with the booking and a new `id`.

Check the 422: `pskit invoke -f create-booking --method POST --path /bookings -d '{"guests": 2}'`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 117
    B(117, stage="prod", mode="auto", page="Overview", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: ingest
provider:
  name: onprem
  region: local
  options:
    port: 8093
functions: {}
""",
          "requirements.txt": ""}),
      user="queues on disk at /var/pskit/queues (not data_dir). worker `ingest-rows` on queue rows, batch 50, window 10s",
      steps=[
          S("get_project"),
          S("search_docs", query="options.services queue directory path",
            docs=[D("docs/providers.md", "onprem-on-premises", start="    services:", end="workflow: embedded                       # builtin is an alias of embedded")]),
          S("propose_plan", steps=["provider.options.services.queue: {use: directory, path: /var/pskit/queues}",
                                   "Write `app/rows.py`; add `ingest-rows` with queue {name: rows, batch_size: 50, batch_window: 10}",
                                   "Validate (onprem, prod), invoke with 3 rows"]),
          S("set_config", path="provider.options.services",
            value={"queue": {"use": "directory", "path": "/var/pskit/queues"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/rows.py", content=FUTURE + """

def ingest(event, ctx):
    rows = [r.json(default={}) for r in event.records]
    ctx.logger.info("ingest batch", extra={"rows": len(rows)})
    return {"ingested": len(rows)}
"""),
          S("set_config", path="functions.ingest-rows",
            value={"handler": "app.rows.ingest",
                   "events": [{"queue": {"name": "rows", "batch_size": 50, "batch_window": 10}}]}),
          S("invoke_local", function="ingest-rows", type="queue", data=[{"id": 1}, {"id": 2}, {"id": 3}]),
      ],
      final="""Done:

```yaml
provider:
  options:
    services:
      queue: {use: directory, path: /var/pskit/queues}
functions:
  ingest-rows:
    handler: app.rows.ingest
    events:
      - queue: {name: rows, batch_size: 50, batch_window: 10}
```

Queue files now live under `/var/pskit/queues/rows`, one JSON file per message. `batch_size` and `batch_window` are honoured on premises [docs/providers.md#onprem-on-premises]. The host's user needs write access to that path on the target.

- validate (onprem, prod): valid.
- invoke with 3 records: `{"ingested": 3}`.

Deploy: `pskit deploy -s prod` (or **Deploy**, typed confirmation). Enqueue after deploy with `POST /__pskit/queues/rows`."""),

    # ------------------------------------------------------------------ 118
    B(118, stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#storage-drivers", "docs/resources.md#on-premises-drivers"],
      project=dict(files={
          "pskit.yml": """service: photo-lab
provider:
  name: onprem
  region: local
  options:
    port: 8094
functions: {}
""",
          "requirements.txt": ""}),
      user="our MinIO console shows this for the bucket:\n\n  Bucket: raw-photos   Endpoint: http://minio.example.com:9000   Objects: 1,204   Prefix used by cameras: incoming/\n\nwhen a camera uploads a new photo there, a function should log the key and size. keys are MINIO_ACCESS_KEY / MINIO_SECRET_KEY on the host",
      steps=[
          S("get_project"),
          S("search_docs", query="minio storage driver endpoint access key prefix",
            docs=[D("docs/resources.md", "storage-drivers", start="| `minio` |", end="| `minio` | your `endpoint` | path | `endpoint` | |")]),
          S("propose_plan", steps=["Add resources.raw-photos: storage, external, name raw-photos, options {driver: minio, endpoint, prefix incoming/, access_key_env, secret_key_env}",
                                   "Write `app/photos.py`; add `on-photo` with storage {resource: raw-photos, events: [created]}",
                                   "Validate for onprem and invoke with a sample object"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.raw-photos",
            value={"type": "storage", "external": True, "name": "raw-photos",
                   "options": {"driver": "minio", "endpoint": "http://minio.example.com:9000", "prefix": "incoming/",
                               "access_key_env": "MINIO_ACCESS_KEY", "secret_key_env": "MINIO_SECRET_KEY"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/photos.py", content=FUTURE + """

def on_photo(event, ctx):
    for record in event.records:
        ctx.logger.info("new photo", extra={"key": record.key, "size": record.size})
    return {"photos": [record.key for record in event.records]}
"""),
          S("set_config", path="functions.on-photo",
            value={"handler": "app.photos.on_photo",
                   "events": [{"storage": {"resource": "raw-photos", "events": ["created"]}}]}),
          S("invoke_local", function="on-photo", type="storage",
            data={"bucket": "raw-photos", "key": "cam-04/2026-11-01T08-15.jpg", "size": 2048311, "action": "created"}),
      ],
      final="""Added the MinIO bucket as an external storage resource and a function on it:

```yaml
resources:
  raw-photos:
    type: storage
    external: true
    name: raw-photos
    options:
      driver: minio
      endpoint: http://minio.example.com:9000
      prefix: incoming/
      access_key_env: MINIO_ACCESS_KEY
      secret_key_env: MINIO_SECRET_KEY
functions:
  on-photo:
    handler: app.photos.on_photo
    events:
      - storage: {resource: raw-photos, events: [created]}
```

The host lists the bucket every `poll_seconds` and fires for new or changed objects. The 1,204 photos already there are recorded at first start and not sent. `prefix` keeps it to `incoming/`, which matters on a big bucket [docs/resources.md#storage-drivers]. The keys are read from the host's environment, never from pskit.yml [docs/resources.md#on-premises-drivers].

- `pskit validate` (onprem): valid.
- Local invoke: logged and returned `cam-04/2026-11-01T08-15.jpg`.

Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 119
    B(119, stage="staging", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: canteen
provider:
  name: onprem
  region: local
  options:
    port: 8095
functions:
  menu-mail:
    handler: app.menu.send
""",
          "app/__init__.py": "",
          "app/menu.py": FUTURE + """

def send(event, ctx):
    ctx.logger.info("menu of the day sent")
    return {"sent": True}
""",
          "requirements.txt": ""}),
      user="menu-mail must go 7:30 morning berlin time, only workdays mon-fri",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add schedule cron `30 7 * * 1-5` with timezone Europe/Berlin to `menu-mail`",
                                   "Validate (onprem, staging), run schedule locally"]),
          S("set_config", path="functions.menu-mail.events",
            value=[{"schedule": {"cron": "30 7 * * 1-5", "timezone": "Europe/Berlin"}}]),
          S("invoke_local", function="menu-mail", type="schedule"),
      ],
      final="""Done. `menu-mail` runs at 07:30 Berlin time, Monday to Friday:

```yaml
- schedule: {cron: "30 7 * * 1-5", timezone: Europe/Berlin}
```

The host evaluates the cron in that timezone, so summer and winter time are handled for you [docs/events.md#schedule].

- validate (onprem, staging): valid, with one warning: this machine has no IANA timezone database, so until deploy the schedule would be evaluated in UTC. `pskit deploy` vendors `tzdata`, so the deployed host uses Berlin time [docs/providers.md#onprem-on-premises].
- local schedule run: `{"sent": true}`.

Deploy: **Deploy** page or `pskit deploy -s staging`. Run it now for a test: `pskit invoke -f menu-mail -t schedule`."""),

    # ------------------------------------------------------------------ 120
    B(120, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: cafe-menu
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8096
functions: {}
""",
          "requirements.txt": ""}),
      user="my website at https://app.example.com needs to read the menu from my function, but the browser blocks it (cors?). please make a menu endpoint that the website can call",
      steps=[
          S("get_project"),
          S("search_docs", query="cors origins http event",
            docs=[D("docs/events.md", "http", start="- http:", words=140)]),
          S("propose_plan", steps=["Write `app/menu.py` returning the menu list",
                                   "Add function `menu` on GET /api/menu with cors origins [https://app.example.com]",
                                   "Validate for onprem and call /api/menu locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/menu.py", content=FUTURE + """

MENU = [
    {"item": "Flat white", "price": 3.4},
    {"item": "Croissant", "price": 2.1},
]


def menu(event, ctx):
    return {"menu": MENU}
"""),
          S("set_config", path="functions.menu",
            value={"handler": "app.menu.menu",
                   "events": [{"http": {"path": "/api/menu", "method": "GET",
                                        "cors": {"origins": ["https://app.example.com"]}}}]}),
          S("invoke_local", function="menu", method="GET", path="/api/menu"),
      ],
      final="""Yes, that was CORS: the browser only lets your website read the answer when the function says that site is allowed. I added a `menu` function that allows exactly your site:

```yaml
functions:
  menu:
    handler: app.menu.menu
    events:
      - http:
          path: /api/menu
          method: GET
          cors: {origins: ["https://app.example.com"]}
```

- `pskit validate` (onprem): valid.
- Local call `GET /api/menu`: 200 with the two sample menu items.

pskit adds the CORS headers and answers the browser's `OPTIONS` check for you. Your website can now call `http://<this server>:8096/api/menu` after a deploy: **Deploy** page or `pskit deploy -s dev`. Test again: **Test** page > **▶ Run locally**."""),
]
