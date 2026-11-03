"""Category C (fix a validation error), batch 8: on-premises resource drivers, SMTP and resources.
Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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


def app(module, *names):
    return {"app/__init__.py": "", f"app/{module}.py": handlers(*names)}


def onprem(service, rest, port=8080):
    """Header of a local on-prem pskit.yml (scaffolding); `rest` is the hand-written resources/functions part."""
    return f"""service: {service}
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: {port}
{rest}"""


MATRIX = D("docs/resources.md", "provider-matrix", start="| Provider |", end="Topics only support")
QDRIVERS = D("docs/resources.md", "queue-drivers", start="| Driver |", end="| `pskit_host` |")
SECRETS = D("docs/resources.md", "on-premises-drivers", start="**Secrets.**", end="**Secrets.**")
SMTP_STEPS = D("docs/smtp/README.md", "e-mail-triggers-smtp-on-premises", start="It takes three steps:", end="3. **Add two DNS records**")

CONVERSATIONS = [
    # ------------------------------------------------------------------ 141  queue driver kafka
    C(141, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#provider-matrix", "docs/resources.md#custom-drivers"],
      project=dict(files={"pskit.yml": onprem("click-stream", """resources:
  clicks:
    type: queue
    options: {driver: kafka}
functions:
  count-clicks:
    handler: app.clicks.count
    events:
      - queue: {resource: clicks, batch_size: 50}
"""), **app("clicks", "count")}),
      user="driver kafka not in list?? we have kafka in company",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem queue driver kafka", docs=[MATRIX]),
          S("ask_user", question="pskit has no built-in Kafka driver; Kafka needs a `custom` driver class you write. What do you want for now?",
            options=["Use the builtin queue for now", "I'll write a custom driver class"],
            answer="Use the builtin queue for now"),
          S("propose_plan", steps=["Delete `resources.clicks.options` (builtin queue)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.clicks.options", value=None),
      ],
      final="""Kafka isn't one of the queue drivers. For self-hosted brokers like Kafka the docs point to `custom` (your own class) [docs/resources.md#provider-matrix].

As you chose, `clicks` is a builtin queue now (I removed `options.driver`). Validate for onprem: valid. Later you can write a class and set `driver: custom` with `class: package.module:ClassName` [docs/resources.md#custom-drivers]."""),

    # ------------------------------------------------------------------ 142  redis without url -> url_env
    C(142, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#queue-drivers", "docs/resources.md#on-premises-drivers"],
      project=dict(files={"pskit.yml": onprem("render-jobs", """resources:
  jobs:
    type: queue
    external: true
    options: {driver: redis}
functions:
  render:
    handler: app.render.frame
    events:
      - queue: {resource: jobs, batch_size: 1}
"""), **app("render", "frame")}),
      user="I switched `jobs` to our Redis. The URL contains the Redis password, so I didn't put it in pskit.yml. Prod validation now wants a url. The host machine has the env var JOBS_REDIS_URL set. How do I point to it without the password in the file?",
      steps=[
          S("get_validation"),
          S("search_docs", query="driver secret parameter _env", docs=[SECRETS]),
          S("propose_plan", steps=["Set `resources.jobs.options.url_env` to `JOBS_REDIS_URL` (the variable name only)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.jobs.options.url_env", value="JOBS_REDIS_URL"),
      ],
      final="""Any driver parameter can be given as `<name>_env: VARIABLE`, and the host reads it from its own environment at start [docs/resources.md#on-premises-drivers].

Now `options: {driver: redis, url_env: JOBS_REDIS_URL}`. `pskit validate -p onprem -s prod`: valid. Only the variable name is in the file. If `JOBS_REDIS_URL` isn't set where the host starts, the host stops with an error naming it. You can also ship it in `options.env_file`."""),

    # ------------------------------------------------------------------ 143  redis url without scheme
    C(143, provider="onprem", stage="dev", mode="auto", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("chat-relay", """resources:
  inbox:
    type: queue
    external: true
    options: {driver: redis, url: "localhost:6379"}
functions:
  relay:
    handler: app.chat.relay
    events:
      - queue: {resource: inbox}
"""), **app("chat", "relay")}),
      user="""  ERROR: [resources.inbox] resource 'inbox': the redis driver needs `url: redis://host:6379/0` (or rediss://)""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.inbox.options.url` to `redis://localhost:6379/0`", "Validate for onprem"]),
          S("set_config", path="resources.inbox.options.url", value="redis://localhost:6379/0"),
      ],
      final="""The URL needs the `redis://` scheme (and a database number) [docs/resources.md#queue-drivers]. Set `url: redis://localhost:6379/0`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 144  directory driver without path
    C(144, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#on-premises-drivers"],
      project=dict(files={"pskit.yml": onprem("fax-inbox", """resources:
  faxes:
    type: queue
    options: {driver: directory}
functions:
  file-fax:
    handler: app.fax.file
    events:
      - queue: {resource: faxes}
"""), **app("fax", "file")}),
      user="Our old fax program already writes jobs into a folder. I chose 'directory' for the queue, but it says the directory driver needs path. Help me fill it in.",
      steps=[
          S("get_validation"),
          S("ask_user", question="Which folder does the fax program write to?", answer="C:/FaxServer/outbox"),
          S("propose_plan", steps=["Set `resources.faxes.options.path` to `C:/FaxServer/outbox`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.faxes.options.path", value="C:/FaxServer/outbox"),
      ],
      final="""The `directory` driver needs to know which folder to watch, and `path` was missing [docs/resources.md#on-premises-drivers].

Now `options: {driver: directory, path: C:/FaxServer/outbox}`. Validate for onprem: valid. Test it with **Test** > **▶ Run locally** and a sample record before the first deploy."""),

    # ------------------------------------------------------------------ 145  minio without endpoint
    C(145, provider="onprem", stage="staging", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#storage-drivers"],
      project=dict(files={"pskit.yml": onprem("scan-archive", """resources:
  scans:
    type: storage
    external: true
    options: {driver: minio, access_key_env: MINIO_ACCESS_KEY, secret_key_env: MINIO_SECRET_KEY}
functions:
  index-scan:
    handler: app.scans.index
    events:
      - storage: {resource: scans, prefix: incoming/}
"""), **app("scans", "index")}),
      user="minio driver needs endpoint. staging",
      steps=[
          S("get_validation"),
          S("ask_user", question="MinIO endpoint URL for staging (e.g. http://host:9000)?", answer="http://192.0.2.20:9000"),
          S("propose_plan", steps=["Set `resources.scans.options.endpoint` to `http://192.0.2.20:9000`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.scans.options.endpoint", value="http://192.0.2.20:9000"),
      ],
      final="""The `minio` preset has no default endpoint; it's required [docs/resources.md#storage-drivers]. Set `endpoint: http://192.0.2.20:9000` (path-style). Keys stay in `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 146  s3 provider backblaze -> b2
    C(146, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#storage-drivers"],
      project=dict(files={"pskit.yml": onprem("photo-backup", """resources:
  backups:
    type: storage
    external: true
    options:
      driver: s3
      provider: backblaze
      region: us-west-004
      access_key_env: B2_KEY_ID
      secret_key_env: B2_APP_KEY
functions:
  verify:
    handler: app.backup.verify
    events:
      - storage: {resource: backups}
"""), **app("backup", "verify")}),
      user="our bucket in backblaze. provider backblaze error 'must be one of'. which name",
      steps=[
          S("get_validation"),
          S("search_docs", query="s3 presets backblaze", docs=[
              D("docs/resources.md", "storage-drivers", start="| Preset |", end="| `b2` |")]),
          S("propose_plan", steps=["Set `resources.backups.options.provider` to `b2`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.backups.options.provider", value="b2"),
      ],
      final="""Backblaze's preset is called `b2` [docs/resources.md#storage-drivers].

Now `provider: b2` (region `us-west-004` kept). Validate for onprem: valid. For B2 the application key ID goes in as `access_key`, here via `B2_KEY_ID`."""),

    # ------------------------------------------------------------------ 147  sqs without queue_url
    C(147, provider="onprem", stage="prod", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("refunds", """resources:
  refund-requests:
    type: queue
    external: true
    options: {driver: sqs}
functions:
  refund:
    handler: app.refunds.process
    events:
      - queue: {resource: refund-requests, batch_size: 10}
"""), **app("refunds", "process")}),
      user="The refunds worker now runs on our own server but must keep reading the existing SQS queue https://sqs.eu-west-1.amazonaws.com/123456789012/refund-requests. With `driver: sqs`, prod validation says it needs account_id, region. Can I just give it the URL?",
      steps=[
          S("get_validation"),
          S("search_docs", query="sqs driver queue_url", docs=[
              D("docs/resources.md", "queue-drivers", start="| `sqs` |", end="| `sqs` |")]),
          S("propose_plan", steps=["Set `resources.refund-requests.options.queue_url` to the existing queue URL",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.refund-requests.options.queue_url",
            value="https://sqs.eu-west-1.amazonaws.com/123456789012/refund-requests"),
      ],
      final="""Yes: the sqs driver takes `queue_url`, or `account_id` + `region` [docs/resources.md#queue-drivers].

Set `queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/refund-requests` (region comes from the URL). `pskit validate -p onprem -s prod`: valid. Without keys in the file, the host uses `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` from its environment, so set those on the server (or in `env_file`)."""),

    # ------------------------------------------------------------------ 148  sqs only access_key
    C(148, provider="onprem", stage="staging", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#queue-drivers", "docs/resources.md#on-premises-drivers"],
      project=dict(files={"pskit.yml": onprem("leads", """resources:
  leads:
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: https://sqs.us-east-2.amazonaws.com/123456789012/leads
      access_key: example-key-id
functions:
  score:
    handler: app.leads.score
    events:
      - queue: {resource: leads}
"""), **app("leads", "score")}),
      user="""  ERROR: [resources.leads] resource 'leads': set both access_key and secret_key (or neither)

the secret key is in env var LEADS_AWS_SECRET, key id in LEADS_AWS_KEY_ID""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `resources.leads.options.access_key` (no key in the file)",
                                   "Set `access_key_env: LEADS_AWS_KEY_ID` and `secret_key_env: LEADS_AWS_SECRET`",
                                   "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.leads.options.access_key", value=None),
          S("set_config", path="resources.leads.options.access_key_env", value="LEADS_AWS_KEY_ID"),
          S("set_config", path="resources.leads.options.secret_key_env", value="LEADS_AWS_SECRET"),
      ],
      final="""The driver needs both keys or neither, and only `access_key` was set [docs/resources.md#queue-drivers].

Both now come from the environment: `access_key_env: LEADS_AWS_KEY_ID`, `secret_key_env: LEADS_AWS_SECRET`, and the literal key id is gone from the file. `pskit validate -p onprem -s staging`: valid. The host reads both when it starts [docs/resources.md#on-premises-drivers]."""),

    # ------------------------------------------------------------------ 149  wait_seconds 60
    C(149, provider="onprem", stage="dev", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("ledger-sync", """resources:
  ledger:
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: https://sqs.ap-south-1.amazonaws.com/123456789012/ledger
      wait_seconds: 60
functions:
  sync:
    handler: app.ledger.sync
    events:
      - queue: {resource: ledger}
"""), **app("ledger", "sync")}),
      user="sqs wait_seconds 60 rejected. longest poll allowed",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.ledger.options.wait_seconds` to 20", "Validate for onprem"]),
          S("set_config", path="resources.ledger.options.wait_seconds", value=20),
      ],
      final="""SQS long polling is 0-20 s [docs/resources.md#queue-drivers]. Set `wait_seconds: 20`, the longest. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 150  topic driver redis
    C(150, provider="onprem", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#provider-matrix"],
      project=dict(files={"pskit.yml": onprem("price-feed", """resources:
  prices:
    type: topic
    options: {driver: redis, url: "redis://192.0.2.20:6379/1"}
functions:
  cache-price:
    handler: app.prices.cache
    events:
      - topic: {resource: prices}
  alert-price:
    handler: app.prices.alert
    events:
      - topic: {resource: prices, filter: {symbol: [ACME]}}
"""), **app("prices", "cache", "alert")}),
      user="I put the `prices` topic on Redis like our queues, but validation says on-premises topic driver must be builtin or directory. Both subscribers run on this one host. Make it valid with the least change.",
      steps=[
          S("get_validation"),
          S("search_docs", query="topic drivers onprem", docs=[MATRIX]),
          S("propose_plan", steps=["Delete `resources.prices.options` (topic back to builtin)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.prices.options", value=None),
      ],
      final="""Topics only support the `builtin` and `directory` drivers; Redis is for queues [docs/resources.md#provider-matrix].

Removed `options` from `prices`, so it's a builtin topic again. Validate for onprem: valid. Both subscribers are on this host, so fan-out works the same: `cache-price` gets every message, `alert-price` only `symbol: ACME`."""),

    # ------------------------------------------------------------------ 151  database options.driver
    C(151, provider="onprem", stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#fields", "docs/configuration.md#resources"],
      project=dict(files={"pskit.yml": onprem("crm", """resources:
  crm-db:
    type: database
    external: true
    connection: {host: 192.0.2.20, port: 5432, database: crm, password_env: CRM_DB_PASSWORD}
    options: {driver: postgres}
functions:
  contacts:
    handler: app.crm.contacts
    events:
      - http: GET /contacts
"""), **app("crm", "contacts")}),
      user="options.driver is not used for database resources. but how pskit know it is postgres?",
      steps=[
          S("get_validation"),
          S("search_docs", query="database resource connection fields", docs=[
              D("docs/resources.md", "fields", start="| Key | Default | Notes |", end="pskit only passes their connection details along.")]),
          S("propose_plan", steps=["Delete `resources.crm-db.options`",
                                   "Add `engine: postgres` to `resources.crm-db.connection` (passed to the function as information)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.crm-db.options", value=None),
          S("set_config", path="resources.crm-db.connection.engine", value="postgres"),
      ],
      final="""pskit doesn't talk to databases itself, so it doesn't need to know. `options.driver` is only for queues, storage and topics; a database is `external` and only its `connection` details are passed to your functions [docs/resources.md#fields].

Removed `options.driver` and added `engine: postgres` to `connection`, so your code can read it. `pskit validate -p onprem -s prod`: valid. Your handler connects with a Postgres library such as psycopg."""),

    # ------------------------------------------------------------------ 152  custom class format
    C(152, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#custom-drivers"],
      project=dict(files={"pskit.yml": onprem("amqp-bridge", """resources:
  tasks:
    type: queue
    external: true
    options: {driver: custom, class: app.backends.RabbitQueue, url_env: AMQP_URL}
functions:
  work:
    handler: app.worker.work
    events:
      - queue: {resource: tasks}
"""), **app("worker", "work")}),
      user="""  ERROR: [resources.tasks] resource 'tasks': the custom driver needs `class: package.module:ClassName` (got 'app.backends.RabbitQueue')

class RabbitQueue is in app/backends.py""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.tasks.options.class` to `app.backends:RabbitQueue` (colon before the class)",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.tasks.options.class", value="app.backends:RabbitQueue"),
      ],
      final="""The class must be written `module:ClassName`, with a colon between the module and the class [docs/resources.md#custom-drivers].

Now `class: app.backends:RabbitQueue`. Validate for onprem: valid. `url_env` is passed to the constructor as a keyword argument."""),

    # ------------------------------------------------------------------ 153  azure_queue account only
    C(153, provider="onprem", stage="staging", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("sensor-bridge", """resources:
  telemetry:
    type: queue
    external: true
    options: {driver: azure_queue, account: acmesensors}
functions:
  store:
    handler: app.telemetry.store
    events:
      - queue: {resource: telemetry, batch_size: 32}
"""), **app("telemetry", "store")}),
      user="Our devices push into an Azure Storage Queue in account acmesensors; the edge server should consume it. Staging validation says the azure_queue driver needs account_key, sas_token or connection_string. We have a SAS token in AZURE_QUEUE_SAS on the server. Like an IAM role on AWS, I'd rather not paste it.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.telemetry.options.sas_token_env` to `AZURE_QUEUE_SAS`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.telemetry.options.sas_token_env", value="AZURE_QUEUE_SAS"),
      ],
      final="""With `account`, the driver also needs a credential: `account_key` or `sas_token` (or one `connection_string`) [docs/resources.md#queue-drivers]. There's no role-based login for it on-prem.

Set `sas_token_env: AZURE_QUEUE_SAS`, so only the variable name is in the file. `pskit validate -p onprem -s staging`: valid. Messages are base64 by default, like the Azure SDKs; set `message_encoding: text` if your devices send plain text."""),

    # ------------------------------------------------------------------ 154  pubsub without project
    C(154, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("survey-results", """resources:
  answers:
    type: queue
    external: true
    options: {driver: pubsub, subscription: answers-sub}
functions:
  save-answer:
    handler: app.survey.save
    events:
      - queue: {resource: answers}
"""), **app("survey", "save")}),
      user="I want to read from a Google Pub/Sub subscription. Validate says it needs `project`. What is that?",
      steps=[
          S("get_validation"),
          S("ask_user", question="It's the Google Cloud project id that owns the subscription (shown at the top of the Google Cloud console). What is it?",
            answer="survey-prod-4821"),
          S("propose_plan", steps=["Set `resources.answers.options.project` to `survey-prod-4821`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.answers.options.project", value="survey-prod-4821"),
      ],
      final="""A short subscription name like `answers-sub` needs the project it belongs to (or the full `projects/<p>/subscriptions/<s>` path) [docs/resources.md#queue-drivers].

Set `project: survey-prod-4821`. Validate for onprem: valid. The host also needs a login for Google: `access_token`, `token_command` (for example `[gcloud, auth, print-access-token]`) or the metadata server when it runs on Google Cloud."""),

    # ------------------------------------------------------------------ 155  bucket on a directory resource
    C(155, provider="onprem", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/resources.md#storage-drivers"],
      project=dict(files={"pskit.yml": onprem("invoice-ocr", """resources:
  drop:
    type: storage
    options: {driver: directory, path: ./drop}
functions:
  ocr:
    handler: app.ocr.run
    events:
      - storage: {resource: drop, bucket: invoices, suffix: .pdf}
"""), **app("ocr", "run")}),
      user="I want `ocr` to watch the `invoices` bucket of the `drop` storage resource, which points at our ./drop folder. Validation says a directory storage resource is one folder. Keep using the ./drop folder; what should the event look like?",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage resource bucket directory one folder", docs=[
              D("docs/resources.md", "storage-drivers", start="`builtin` resources make it another bucket folder", end="`builtin` resources make it another bucket folder")]),
          S("propose_plan", steps=["Delete `functions.ocr.events.0.storage.bucket` (the event watches the folder itself)",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ocr.events.0.storage.bucket", value=None),
      ],
      final="""A `directory` resource is a single folder, so it has no buckets inside it; only builtin and S3-type resources can hold several [docs/resources.md#storage-drivers].

The event is now `storage: {resource: drop, suffix: .pdf}`: `ocr` watches `./drop` directly. Validate for onprem: valid. If you want an `invoices` subfolder only, keep the files there and add `prefix: invoices/`."""),

    # ------------------------------------------------------------------ 156  smtp event on a queue resource
    C(156, provider="onprem", stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/smtp/README.md#e-mail-triggers-smtp-on-premises"],
      project=dict(files={"pskit.yml": onprem("support-mail", """resources:
  support-inbox:
    type: queue
functions:
  new-ticket:
    handler: app.support.new_ticket
    events:
      - smtp: {resource: support-inbox}
"""), **app("support", "new_ticket")}),
      user="i want function run when email come to support. error 'smtp event on resource support-inbox, which is a queue'",
      steps=[
          S("get_validation"),
          S("search_docs", query="smtp trigger resource email", docs=[SMTP_STEPS]),
          S("propose_plan", steps=["Set `resources.support-inbox.type` to `smtp` (the SMTP server resource)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.support-inbox.type", value="smtp"),
      ],
      final="""An `smtp` trigger must point at an SMTP server resource (`type: smtp`), and `support-inbox` was a queue [docs/smtp/README.md#e-mail-triggers-smtp-on-premises].

Changed `support-inbox` to `type: smtp`. `pskit validate -p onprem -s prod`: valid.

To really receive mail, create the server from **Resources** > **+ SMTP server** (domains, port 25), then add the A and MX records from its DNS guide."""),

    # ------------------------------------------------------------------ 157  smtp event without resource
    C(157, provider="onprem", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/smtp/README.md#e-mail-triggers-smtp-on-premises"],
      project=dict(files={"pskit.yml": onprem("receipts", """functions:
  parse-receipt:
    handler: app.receipts.parse
    events:
      - smtp: {name: receipts-inbox}
"""), **app("receipts", "parse")}),
      user="""Error: pskit.yml is invalid:
  - functions.parse-receipt.events.0: Value error, smtp event needs `resource` (an smtp resource: the SMTP server that receives the mail)""",
      steps=[
          S("get_validation"),
          S("search_docs", query="smtp event resource", docs=[SMTP_STEPS]),
          S("propose_plan", steps=["Add `resources.receipts-inbox: {type: smtp}`",
                                   "Set the event to `smtp: {resource: receipts-inbox}`",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.receipts-inbox", value={"type": "smtp"}),
          S("set_config", path="functions.parse-receipt.events.0.smtp", value={"resource": "receipts-inbox"}),
      ],
      final="""An `smtp` trigger names its SMTP server with `resource`, the key of a `type: smtp` resource. `name` isn't used [docs/smtp/README.md#e-mail-triggers-smtp-on-premises].

Added `resources.receipts-inbox: {type: smtp}` and changed the event to `smtp: {resource: receipts-inbox}`. Validate for onprem: valid. Set its domains and where it runs with **Resources** > **+ SMTP server**."""),

    # ------------------------------------------------------------------ 158  smtp server without trigger (warning)
    C(158, provider="onprem", stage="prod", mode="ask", page="Resources", persona="beginner",
      sources=["docs/smtp/README.md#how-it-works"],
      project=dict(files={"pskit.yml": onprem("orders-mail", """resources:
  orders-inbox:
    type: smtp
functions:
  order-email:
    handler: app.orders.from_email
  status:
    handler: app.orders.status
    events:
      - http: GET /status
"""), **app("orders", "from_email", "status")}),
      user="Validate is OK, but there's a yellow warning that the SMTP server refuses mail with 451. I made `order-email` for the emails. What is missing?",
      steps=[
          S("get_validation"),
          S("search_docs", query="smtp 451 no function attached", docs=[
              D("docs/smtp/README.md", "how-it-works", start="- Each mail is posted to the pskit host", end="No mail is lost")]),
          S("propose_plan", steps=["Add `- smtp: {resource: orders-inbox}` to `functions.order-email.events`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.order-email.events", value=[{"smtp": {"resource": "orders-inbox"}}]),
      ],
      final="""`order-email` had no trigger, so no function was attached to the SMTP server, and it answers every mail with a temporary error (451) [docs/smtp/README.md#how-it-works].

I added `- smtp: {resource: orders-inbox}` to `order-email`. `pskit validate -p onprem -s prod`: valid, and the warning is gone. Each new mail now runs `order-email`."""),

    # ------------------------------------------------------------------ 159  cache not external
    C(159, provider="onprem", stage="dev", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/configuration.md#resources"],
      project=dict(files={"pskit.yml": onprem("session-api", """resources:
  sessions:
    type: cache
functions:
  login:
    handler: app.session.login
    events:
      - http: POST /login
"""), **app("session", "login")}),
      user="cache resource fails: pskit does not create cache resources. valkey is at 192.0.2.25:6379",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.sessions` to `{type: cache, external: true, connection: {host: 192.0.2.25, port: 6379}}`",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.sessions",
            value={"type": "cache", "external": True, "connection": {"host": "192.0.2.25", "port": 6379}}),
      ],
      final="""pskit never creates caches; a `cache` resource must be `external: true` and describe the server in `connection` [docs/configuration.md#resources]. Now `sessions: {type: cache, external: true, connection: {host: 192.0.2.25, port: 6379}}`. Validate for onprem: valid. To have pskit start Valkey for you, use **Resources** > **+ On-prem service**."""),

    # ------------------------------------------------------------------ 160  resource lists unknown function
    C(160, provider="onprem", stage="staging", mode="auto", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#fields"],
      project=dict(files={"pskit.yml": onprem("geo-tiles", """resources:
  tiles-db:
    type: database
    external: true
    connection: {host: 192.0.2.21, port: 5432, database: tiles}
    functions: [tile-server, tile-wroker]
functions:
  tile-server:
    handler: app.tiles.serve
    events:
      - http: GET /tiles/{z}/{x}/{y}
  tile-worker:
    handler: app.tiles.render
    events:
      - queue: tile-jobs
"""), **app("tiles", "serve", "render")}),
      user="resource tiles-db lists unknown function 'tile-wroker' staging",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.tiles-db.functions` to `[tile-server, tile-worker]`", "Validate for onprem, stage staging"]),
          S("set_config", path="resources.tiles-db.functions", value=["tile-server", "tile-worker"]),
      ],
      final="""Typo: `tile-wroker` instead of `tile-worker`. `functions` must list real function names [docs/resources.md#fields]. Fixed to `[tile-server, tile-worker]`. `pskit validate -p onprem -s staging`: valid; both functions get the `tiles-db` connection details."""),
]
