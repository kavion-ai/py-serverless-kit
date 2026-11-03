"""Category C (fix a validation error), batch 13: on-premises resources, drivers and resource-backed events.
Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import D, S  # noqa: E402
from _onprem_c import C, app, onprem  # noqa: E402

R = "docs/resources.md"
QDRIVERS = D(R, "queue-drivers", start="| Driver |", end="| `pskit_host` |")
SQS_ROW = D(R, "queue-drivers", start="| Driver |", end="| `azure_queue` |", words=330)
PUBSUB_ROW = D(R, "queue-drivers", start="| `pubsub` |", end="| `pubsub` |")
SDRIVERS = D(R, "storage-drivers", start="| Driver |", end="| `s3` |")
PRESETS = D(R, "storage-drivers", start="| Preset |", end="| `minio` |", words=330)
FIELDS = D(R, "fields", start="| Key |", end="Resource keys follow function-name rules")
FROM_EVENT = D(R, "using-a-resource-from-an-event", words=150)
CUSTOM = D(R, "custom-drivers", start="```yaml", end="```")
DRIVERS_INTRO = D(R, "on-premises-drivers", start="Set `options.driver`", end="Set `options.driver`")
EV_Q = D("docs/events.md", "queue", words=120)
EV_S = D("docs/events.md", "storage", words=120)
EV_T = D("docs/events.md", "topic", words=120)

H = dict(host="0.0.0.0")

CONVERSATIONS = [
    # ------------------------------------------------------------------ 241  pskit_host without endpoint
    C(241, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("invoices", """resources:
  print-jobs:
    type: queue
    external: true
    options: {driver: pskit_host, token_env: PRINT_HOST_TOKEN}
functions:
  render:
    handler: app.pdf.render
    events:
      - queue: {resource: print-jobs}
""", **H), **app("pdf", "render")}),
      user="Our print service is another pskit project on its own server, and this one should consume its print-jobs queue through the pskit_host driver. Prod validation: the pskit_host driver needs endpoint.",
      steps=[
          S("get_validation"),
          S("search_docs", query="pskit_host driver endpoint token", docs=[QDRIVERS]),
          S("ask_user", question="What is the URL of the print service's host (http://HOST:PORT)?", answer="http://192.0.2.20:8090"),
          S("propose_plan", steps=["Set `resources.print-jobs.options.endpoint` to `http://192.0.2.20:8090`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.print-jobs.options.endpoint", value="http://192.0.2.20:8090"),
      ],
      final="""`pskit_host` reads the built-in queues of another pskit host, so it must know that host's URL (`endpoint`) [docs/resources.md#queue-drivers].

Set `endpoint: http://192.0.2.20:8090`; `token_env: PRINT_HOST_TOKEN` stays for its admin token. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 242  minio endpoint without scheme
    C(242, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#storage-drivers"],
      project=dict(files={"pskit.yml": onprem("scan-store", """resources:
  scans:
    type: storage
    external: true
    options: {driver: minio, endpoint: "minio.example.com:9000", access_key_env: MINIO_KEY, secret_key_env: MINIO_SECRET}
functions:
  index:
    handler: app.scans.index
    events:
      - storage: {resource: scans, events: [created]}
"""), **app("scans", "index")}),
      user="resource scans endpoint must be an http(s) URL. minio is on minio.example.com:9000 no tls",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.scans.options.endpoint` to `http://minio.example.com:9000`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.scans.options.endpoint", value="http://minio.example.com:9000"),
      ],
      final="""`endpoint` must be a full URL with `http://` or `https://` [docs/resources.md#on-premises-drivers]. Without TLS it is `http://minio.example.com:9000`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 243  azure_queue message_encoding json
    C(243, provider="onprem", stage="staging", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("telemetry", """resources:
  readings:
    type: queue
    external: true
    options: {driver: azure_queue, connection_string_env: AZURE_STORAGE_CONN, message_encoding: json}
functions:
  store:
    handler: app.telemetry.store
    events:
      - queue: {resource: readings, batch_size: 16}
""", **H), **app("telemetry", "store")}),
      user="The devices write plain JSON text into an Azure Storage queue (no base64). I set message_encoding: json and staging validation says it must be base64 or text.",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure_queue message_encoding base64 text", docs=[SQS_ROW]),
          S("propose_plan", steps=["Set `resources.readings.options.message_encoding` to `text`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.readings.options.message_encoding", value="text"),
      ],
      final="""`message_encoding` only says how the message bytes are wrapped: `base64` (what the Azure SDKs write) or `text` (as-is). JSON written as plain text is `text` [docs/resources.md#queue-drivers].

Set `message_encoding: text`. `pskit validate -p onprem -s staging`: valid. In the handler, `record.json()` still parses each message."""),

    # ------------------------------------------------------------------ 244  scaleway preset without region
    C(244, provider="onprem", stage="prod", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#storage-drivers"],
      project=dict(files={"pskit.yml": onprem("backup-check", """resources:
  backups:
    type: storage
    external: true
    options: {driver: scaleway, access_key_env: SCW_ACCESS_KEY, secret_key_env: SCW_SECRET_KEY}
functions:
  verify:
    handler: app.backup.verify
    events:
      - storage: {resource: backups, suffix: .tar.gz}
""", **H), **app("backup", "verify")}),
      user="I want to watch our Scaleway backup bucket. It says the scaleway driver needs region. Where do I find it?",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage presets extra required region", docs=[SDRIVERS]),
          S("ask_user", question="Which Scaleway region is the bucket in? It's shown in the bucket's settings (for example fr-par, nl-ams or pl-waw).",
            options=["fr-par", "nl-ams", "pl-waw"], answer="fr-par"),
          S("propose_plan", steps=["Set `resources.backups.options.region` to `fr-par`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.backups.options.region", value="fr-par"),
      ],
      final="""The preset builds the bucket's address from the region, so `scaleway` can't work without one [docs/resources.md#storage-drivers].

Set `region: fr-par`. `pskit validate -p onprem -s prod`: valid. The keys still come from `SCW_ACCESS_KEY` / `SCW_SECRET_KEY` on the host."""),

    # ------------------------------------------------------------------ 245  s3 endpoint with only a secret key
    C(245, provider="onprem", stage="dev", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#storage-drivers"],
      project=dict(files={"pskit.yml": onprem("assets", """resources:
  media:
    type: storage
    external: true
    options: {driver: s3, endpoint: "http://192.0.2.30:9000", secret_key_env: CEPH_SECRET}
functions:
  publish:
    handler: app.media.publish
    events:
      - storage: {resource: media, prefix: ready/}
"""), **app("media", "publish")}),
      user="ceph s3 resource: set both access_key and secret_key. key id env is CEPH_ACCESS",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.media.options.access_key_env` to `CEPH_ACCESS`", "Validate for onprem"]),
          S("set_config", path="resources.media.options.access_key_env", value="CEPH_ACCESS"),
      ],
      final="""S3 credentials come in pairs: both keys or neither [docs/resources.md#storage-drivers]. Added `access_key_env: CEPH_ACCESS` next to `secret_key_env`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 246  pubsub token_command as a mapping
    C(246, provider="onprem", stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("gcp-bridge", """resources:
  events-in:
    type: queue
    external: true
    options:
      driver: pubsub
      project: bridge-demo-41
      subscription: onprem-pull
      token_command: {program: gcloud, args: "auth print-access-token"}
functions:
  relay:
    handler: app.bridge.relay
    events:
      - queue: {resource: events-in}
""", **H), **app("bridge", "relay")}),
      user="The on-prem host should pull a Pub/Sub subscription using gcloud for the token. Staging validation: token_command must be a list of strings or one command line. Please write it the expected way.",
      steps=[
          S("get_validation"),
          S("search_docs", query="pubsub token_command gcloud", docs=[PUBSUB_ROW]),
          S("propose_plan", steps=["Set `resources.events-in.options.token_command` to `[gcloud, auth, print-access-token]`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.events-in.options.token_command", value=["gcloud", "auth", "print-access-token"]),
      ],
      final="""`token_command` is the command as a list of words (or one command line), not a mapping [docs/resources.md#queue-drivers].

Now `token_command` is the list `[gcloud, auth, print-access-token]`; the token is cached for 45 minutes. `pskit validate -p onprem -s staging`: valid. gcloud must be installed and logged in on the host."""),

    # ------------------------------------------------------------------ 247  custom driver with reserved `resource`
    C(247, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#custom-drivers"],
      project=dict(files={"pskit.yml": onprem("rabbit-orders", """resources:
  orders:
    type: queue
    external: true
    options:
      driver: custom
      class: app.backends:RabbitQueue
      url_env: RABBITMQ_URL
      resource: orders.v1
functions:
  fulfil:
    handler: app.orders.fulfil
    events:
      - queue: {resource: orders}
"""), **app("orders", "fulfil"), "app/backends.py": "from __future__ import annotations\n\n\nclass RabbitQueue:\n    def __init__(self, url: str = \"\", queue: str = \"\", **kw):\n        self.url, self.queue = url, queue\n"}),
      user="""  ERROR: [resources.orders] resource 'orders': `resource` is reserved and cannot be passed to a custom driver

my RabbitQueue class takes the queue name, which is orders.v1""",
      steps=[
          S("get_validation"),
          S("search_docs", query="custom driver class parameters", docs=[CUSTOM]),
          S("read_file", path="app/backends.py"),
          S("propose_plan", steps=["Rename the option `resource` to `queue` (your class's `queue` argument)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.orders.options.resource", value=None),
          S("set_config", path="resources.orders.options.queue", value="orders.v1"),
      ],
      final="""Every option except `driver` and `class` is passed to the class as a keyword argument, but `use` and `resource` are reserved for pskit [docs/resources.md#custom-drivers].

`RabbitQueue.__init__` already has a `queue` argument, so I renamed the option: `queue: orders.v1`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 248  storage driver ftp
    C(248, provider="onprem", stage="prod", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#storage-drivers", "docs/resources.md#on-premises-drivers"],
      project=dict(files={"pskit.yml": onprem("scanner-inbox", """resources:
  scans:
    type: storage
    external: true
    options: {driver: ftp}
functions:
  file-scan:
    handler: app.scans.file
    events:
      - storage: {resource: scans, events: [created]}
""", **H), **app("scans", "file")}),
      user="Our office scanner saves to an FTP share. I set driver: ftp and get 'on-premises storage driver must be one of builtin, directory, s3...'. Is there no FTP?",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage driver directory path", docs=[SDRIVERS]),
          S("ask_user", question="There's no FTP driver. Is the FTP share's folder also mounted on the server where the host runs? If yes, what is its path?",
            answer="yes, the server mounts it at /mnt/scanner"),
          S("propose_plan", steps=["Set `resources.scans.options` to `{driver: directory, path: /mnt/scanner}`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.scans.options", value={"driver": "directory", "path": "/mnt/scanner"}),
      ],
      final="""pskit has no FTP driver; it can watch a folder (`directory`), S3-compatible stores, Azure Blob, GCS or a custom class [docs/resources.md#storage-drivers].

Because the share is mounted at /mnt/scanner, I set `driver: directory, path: /mnt/scanner`. `pskit validate -p onprem -s prod`: valid. New files there trigger `file-scan`."""),

    # ------------------------------------------------------------------ 249  connection as a URL
    C(249, provider="onprem", stage="dev", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#fields", "docs/resources.md#secrets"],
      project=dict(files={"pskit.yml": onprem("reports", """resources:
  warehouse:
    type: database
    external: true
    connection: postgresql://report@192.0.2.20:5432/warehouse
functions:
  weekly:
    handler: app.reports.weekly
    events:
      - schedule: "0 6 * * 1"
"""), **app("reports", "weekly")}),
      user="In serverless.yml I had DATABASE_URL as one string, so I wrote connection: postgresql://report@192.0.2.20:5432/warehouse. pskit says connection must be a mapping of names to scalar values.",
      steps=[
          S("get_validation"),
          S("search_docs", query="resource connection mapping database", docs=[FIELDS]),
          S("propose_plan", steps=["Set `resources.warehouse.connection` to `{host: 192.0.2.20, port: 5432, database: warehouse, user: report, password_env: WAREHOUSE_DB_PASSWORD}`",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.warehouse.connection",
            value={"host": "192.0.2.20", "port": 5432, "database": "warehouse", "user": "report", "password_env": "WAREHOUSE_DB_PASSWORD"}),
      ],
      final="""`connection` is a mapping: each key becomes a value your handler reads with `resource("warehouse")` [docs/resources.md#fields].

I split the URL into `host`, `port`, `database` and `user`, plus `password_env: WAREHOUSE_DB_PASSWORD` (only the variable's name) [docs/resources.md#secrets]. Validate for onprem: valid. Build the DSN in the handler from those values."""),

    # ------------------------------------------------------------------ 250  connection key with a dash
    C(250, provider="onprem", stage="staging", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#fields"],
      project=dict(files={"pskit.yml": onprem("inventory", """resources:
  stock-db:
    type: database
    external: true
    connection: {db-host: 192.0.2.20, db-port: 3306, user: stock}
functions:
  levels:
    handler: app.stock.levels
    events:
      - http: GET /levels
""", **H), **app("stock", "levels")}),
      user="connection key 'db-host' must start with a letter and use letters, digits or _ . staging",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.stock-db.connection` to `{db_host: 192.0.2.20, db_port: 3306, user: stock}`", "Validate for onprem, stage staging"]),
          S("set_config", path="resources.stock-db.connection", value={"db_host": "192.0.2.20", "db_port": 3306, "user": "stock"}),
      ],
      final="""Connection keys become environment variable names, so `-` isn't allowed [docs/resources.md#fields]. Renamed to `db_host` and `db_port`. `pskit validate -p onprem -s staging`: valid. Update the handler to read the new key names."""),

    # ------------------------------------------------------------------ 251  connection keys differ only in case
    C(251, provider="onprem", stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#fields"],
      project=dict(files={"pskit.yml": onprem("loyalty", """resources:
  points-db:
    type: database
    external: true
    connection: {host: 192.0.2.20, HOST: 192.0.2.21, port: 5432}
functions:
  balance:
    handler: app.points.balance
    events:
      - http: GET /balance
""", **H), **app("points", "balance")}),
      user="connection keys must be unique ignoring case. colleague added HOST for new db 192.0.2.21, old is 192.0.2.20. new one is right",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Keep only `host: 192.0.2.21` in `resources.points-db.connection` (drop the duplicate `HOST`)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.points-db.connection", value={"host": "192.0.2.21", "port": 5432}),
      ],
      final="""`host` and `HOST` would become the same variable, so keys must differ ignoring case [docs/resources.md#fields].

Now there is one `host: 192.0.2.21` (the new database) plus `port: 5432`. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 252  two resource keys with the same prefix
    C(252, provider="onprem", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#fields"],
      project=dict(files={"pskit.yml": onprem("orders", """resources:
  orders-db:
    type: database
    external: true
    connection: {host: 192.0.2.20, port: 5432}
  orders_db:
    type: cache
    external: true
    connection: {host: 192.0.2.21, port: 6379}
functions:
  create:
    handler: app.orders.create
    events:
      - http: POST /orders
"""), **app("orders", "create")}),
      user="I have a Postgres resource orders-db and a Redis cache I called orders_db. Validation: they map to the same variable prefix ORDERS_DB. Rename the cache, the database name is used in handlers already.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename the cache resource `orders_db` to `orders-cache` (same type and connection)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.orders_db", value=None),
          S("set_config", path="resources.orders-cache", value={"type": "cache", "external": True, "connection": {"host": "192.0.2.21", "port": 6379}}),
      ],
      final="""Both keys become `PSKIT_RESOURCE_ORDERS_DB_*` variables (`-` turns into `_`), so they can't both exist [docs/resources.md#fields].

The cache is now `orders-cache`; `orders-db` is unchanged. Validate for onprem: valid. Handlers read the cache with `resource("orders-cache")`."""),

    # ------------------------------------------------------------------ 253  resource key starting with a digit
    C(253, provider="onprem", stage="staging", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#fields"],
      project=dict(files={"pskit.yml": onprem("login", """resources:
  2fa-cache:
    type: cache
    external: true
    connection: {host: 192.0.2.21, port: 6379}
functions:
  verify:
    handler: app.login.verify
    events:
      - http: POST /verify
""", **H), **app("login", "verify")}),
      user="Studio shows: name '2fa-cache' must start with a letter. It's the cache for two-factor codes. What name can I use?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename resource `2fa-cache` to `otp-cache`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.2fa-cache", value=None),
          S("set_config", path="resources.otp-cache", value={"type": "cache", "external": True, "connection": {"host": "192.0.2.21", "port": 6379}}),
      ],
      final="""Resource keys follow function-name rules: they start with a letter [docs/resources.md#fields].

I renamed it `otp-cache` ("one-time password"). `pskit validate -p onprem -s staging`: valid. Use `resource("otp-cache")` in `verify`."""),

    # ------------------------------------------------------------------ 254  type bucket
    C(254, provider="onprem", stage="dev", mode="auto", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#fields"],
      project=dict(files={"pskit.yml": onprem("avatars", """resources:
  avatars:
    type: bucket
functions:
  crop:
    handler: app.avatars.crop
    events:
      - storage: {resource: avatars}
"""), **app("avatars", "crop")}),
      user="resources.avatars.type: Input should be 'storage', 'queue'... it's an S3 bucket",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.avatars.type` to `storage`", "Validate for onprem"]),
          S("set_config", path="resources.avatars.type", value="storage"),
      ],
      final="""A bucket is `type: storage` in pskit [docs/resources.md#fields]. Changed it. Validate for onprem: valid. On premises it is a built-in folder bucket unless you add a driver."""),

    # ------------------------------------------------------------------ 255  functions as a string
    C(255, provider="onprem", stage="prod", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#fields"],
      project=dict(files={"pskit.yml": onprem("crm", """resources:
  crm-db:
    type: database
    external: true
    connection: {host: 192.0.2.20, port: 5432}
    functions: contacts
functions:
  contacts:
    handler: app.crm.contacts
    events:
      - http: GET /contacts
  ping:
    handler: app.crm.ping
    events:
      - http: GET /ping
""", **H), **app("crm", "contacts", "ping")}),
      user="""Error: pskit.yml is invalid:
  - resources.crm-db.functions: Input should be a valid list

only contacts should get the db""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.crm-db.functions` to `[contacts]`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.crm-db.functions", value=["contacts"]),
      ],
      final="""`functions` on a resource is a list, even for one function [docs/resources.md#fields]. Now `functions: [contacts]`, so `ping` doesn't get the binding. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 256  queue event without name
    C(256, provider="onprem", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=dict(files={"pskit.yml": onprem("emails", """functions:
  send:
    handler: app.mail.send
    events:
      - queue: {batch_size: 5, max_receive: 3}
"""), **app("mail", "send")}),
      user="queue event needs name or resource?? i make new queue for emails, how name it",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue event name batch_size", docs=[EV_Q]),
          S("propose_plan", steps=["Set `functions.send.events.0.queue.name` to `emails`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send.events.0.queue.name", value="emails"),
      ],
      final="""The event must say which queue it reads: a `name`, or a `resource` key [docs/events.md#queue].

I named it `emails`; on premises the host creates it at start. Validate for onprem: valid. Send to it with `pskit resources send` or `POST /__pskit/queues/emails`."""),

    # ------------------------------------------------------------------ 257  storage event without bucket
    C(257, provider="onprem", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#storage"],
      project=dict(files={"pskit.yml": onprem("receipts", """resources:
  uploads:
    type: storage
functions:
  ocr:
    handler: app.receipts.ocr
    events:
      - storage: {prefix: receipts/, suffix: .jpg}
""", **H), **app("receipts", "ocr")}),
      user="The function should run for new receipt photos in our uploads storage, but validate says storage event needs bucket or resource. I added the prefix and suffix, isn't that enough?",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage event resource prefix suffix", docs=[FROM_EVENT]),
          S("propose_plan", steps=["Set `functions.ocr.events.0.storage.resource` to `uploads`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ocr.events.0.storage.resource", value="uploads"),
      ],
      final="""`prefix` and `suffix` filter keys inside a bucket, but the event still has to say which bucket [docs/resources.md#using-a-resource-from-an-event].

Added `resource: uploads`, your storage resource. `pskit validate -p onprem -s staging`: valid. `ocr` runs for new `receipts/*.jpg` files."""),

    # ------------------------------------------------------------------ 258  topic event without name
    C(258, provider="onprem", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#topic"],
      project=dict(files={"pskit.yml": onprem("billing", """functions:
  receipt:
    handler: app.billing.receipt
    events:
      - topic: {filter: {kind: paid}}
""", **H), **app("billing", "receipt")}),
      user="topic event needs `name` or `resource`. topic is billing-events",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.receipt.events.0.topic.name` to `billing-events`", "Validate for onprem, stage prod"]),
          S("set_config", path="functions.receipt.events.0.topic.name", value="billing-events"),
      ],
      final="""The filter alone doesn't say which topic [docs/events.md#topic]. Added `name: billing-events`; the `kind: paid` filter stays. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 259  redis_stream without url
    C(259, provider="onprem", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("clicks", """resources:
  clickstream:
    type: queue
    external: true
    options: {driver: redis_stream, group: analytics}
functions:
  aggregate:
    handler: app.clicks.aggregate
    events:
      - queue: {resource: clickstream, batch_size: 100}
"""), **app("clicks", "aggregate")}),
      user="I'm switching clickstream to a Redis stream with consumer group analytics. Validation: the redis_stream driver needs url. The URL contains the Redis password, so it must not be in pskit.yml; it's in the host's environment as CLICKS_REDIS_URL.",
      steps=[
          S("get_validation"),
          S("search_docs", query="redis_stream url secrets _env", docs=[QDRIVERS, DRIVERS_INTRO]),
          S("propose_plan", steps=["Set `resources.clickstream.options.url_env` to `CLICKS_REDIS_URL`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.clickstream.options.url_env", value="CLICKS_REDIS_URL"),
      ],
      final="""`redis_stream` needs the Redis address, and any driver parameter can be given as `<name>_env` [docs/resources.md#queue-drivers].

Set `url_env: CLICKS_REDIS_URL`: the host reads it from its own environment at start, so the password isn't in pskit.yml or Terraform state. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 260  options.driver under connection with bad value
    C(260, provider="onprem", stage="staging", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#on-premises-drivers", "docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("returns", """resources:
  returns:
    type: queue
    external: true
    connection: {driver: elasticmq, queue_url: "http://192.0.2.40:9324/000000000000/returns"}
functions:
  process:
    handler: app.returns.process
    events:
      - queue: {resource: returns}
""", **H), **app("returns", "process")}),
      user="""  ERROR: [resources.returns] on-premises queue driver must be one of builtin, directory, redis, redis_stream, sqs, azure_queue, pubsub, mns, cloudflare_queue, pskit_host, custom; got 'elasticmq'

it IS elasticmq though""",
      steps=[
          S("get_validation"),
          S("search_docs", query="sqs driver ElasticMQ create_queue endpoint", docs=[SQS_ROW]),
          S("propose_plan", steps=["Set `resources.returns.connection.driver` to `sqs` (ElasticMQ speaks the SQS API)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.returns.connection.driver", value="sqs"),
      ],
      final="""The driver names the protocol, not the product: ElasticMQ is SQS-compatible, so it is `driver: sqs` [docs/resources.md#queue-drivers].

Changed `connection.driver` to `sqs`; `queue_url` already points at ElasticMQ. `pskit validate -p onprem -s staging`: valid."""),
]
