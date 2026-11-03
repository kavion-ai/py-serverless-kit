"""Category C (fix a validation error), batch 15: YAML parsing, extends, variables, provider/stage overrides and
value types in on-premises projects. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import D, S  # noqa: E402
from _onprem_c import C, app, onprem  # noqa: E402

CF = "docs/configuration.md"
VARS = D(CF, "variables", start="| Syntax |", end="When a value is exactly one variable")
EXTENDS = D(CF, "extends-inherit-files")
PROVIDERS_OV = D(CF, "providers-per-cloud-overrides", start="The block for the active provider", end="The block for the active provider")
STAGES_OV = D(CF, "stages-per-stage-overrides")
PRECEDENCE = D(CF, "precedence-later-wins", words=160)
TOP = D(CF, "top-level", start="| Key |", end="| `custom` |")
PROVIDER_T = D(CF, "provider", start="| Key |", end="| `timeout` |")
PACKAGE = D(CF, "package", start="| Key |", end="| `exclude` |")
HOOKS = D(CF, "hooks", start="```yaml", end="Allowed hooks")
FUNCS = D(CF, "functions", start="| Key |", end="| `runtime`, `memory`")
SECRETS = D("docs/resources.md", "on-premises-drivers", start="**Secrets.**", end="**Secrets.**")
H = dict(host="0.0.0.0")
PING = """functions:
  ping:
    handler: app.health.ping
    events:
      - http: GET /ping
"""

CONVERSATIONS = [
    # ------------------------------------------------------------------ 281  ${file(limits.json)} missing
    C(281, provider="onprem", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#variables"],
      project=dict(files={"pskit.yml": onprem("quota", """custom:
  limits: ${file(limits.json)}
functions:
  check:
    handler: app.quota.check
    memory: ${self:custom.limits.memory}
    events:
      - http: GET /quota
"""), **app("quota", "check")}),
      user="I moved the memory setting into limits.json so ops can edit it, but the file isn't in the project yet and validation fails. Create it with memory 512.",
      steps=[
          S("get_validation"),
          S("search_docs", query="file variable json", docs=[VARS]),
          S("propose_plan", steps=["Write `limits.json` with `{\"memory\": 512}`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="limits.json", content="{\"memory\": 512}\n"),
          S("validate"),
      ],
      final="""`${file(limits.json)}` reads a file next to pskit.yml, and it didn't exist [docs/configuration.md#variables].

Created `limits.json` with `{"memory": 512}`. Because `memory` is exactly one variable, it stays a number. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 282  circular extends
    C(282, provider="onprem", stage="staging", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#extends-inherit-files"],
      project=dict(files={"pskit.yml": "extends: base.yml\n" + onprem("portal", PING, **H),
                          "base.yml": "extends: pskit.yml\ncustom:\n  team: web\n", **app("health", "ping")}),
      user="circular `extends` error. base.yml is only for shared custom stuff",
      steps=[
          S("get_validation"),
          S("read_file", path="base.yml"),
          S("search_docs", query="extends inherit files circular", docs=[EXTENDS]),
          S("propose_plan", steps=["Remove `extends: pskit.yml` from base.yml (only pskit.yml extends base.yml)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="base.yml", content="custom:\n  team: web\n"),
          S("validate"),
      ],
      final="""pskit.yml extends base.yml and base.yml extended pskit.yml back, a loop [docs/configuration.md#extends-inherit-files].

base.yml now only holds `custom: {team: web}`; pskit.yml still extends it. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 283  ${opt:tenant}
    C(283, provider="onprem", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#variables"],
      project=dict(files={"pskit.yml": onprem("invoices-${opt:tenant}", """functions:
  create:
    handler: app.invoices.create
    events:
      - http: POST /invoices
"""), **app("invoices", "create")}),
      user="With Serverless Framework I passed --tenant on the command line and used ${opt:tenant}. pskit says unresolved variables: opt:tenant.",
      steps=[
          S("get_validation"),
          S("search_docs", query="opt variables stage provider region", docs=[VARS]),
          S("ask_user", question="pskit's `${opt:...}` only knows stage, provider and region. Which tenant is this project for? I'll keep it in `custom.tenant`.",
            answer="acme"),
          S("propose_plan", steps=["Set `custom.tenant` to `acme`", "Set `service` to `invoices-${self:custom.tenant}`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="custom.tenant", value="acme"),
          S("set_config", path="service", value="invoices-${self:custom.tenant}"),
      ],
      final="""`${opt:...}` resolves only `stage`, `provider` and `region` (the CLI flags); there is no `--tenant` [docs/configuration.md#variables].

Now `custom.tenant: acme` and `service: invoices-${self:custom.tenant}`, so the service is `invoices-acme`. Validate for onprem: valid. For several tenants, keep one small file per tenant that `extends` this one and sets `custom.tenant`."""),

    # ------------------------------------------------------------------ 284  providers: on-prem
    C(284, provider="onprem", stage="prod", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#providers-per-cloud-overrides"],
      project=dict(files={"pskit.yml": onprem("gateway", PING + """providers:
  on-prem:
    options: {port: 9000}
""", **H), **app("health", "ping")}),
      user="`providers:` has unknown keys ['on-prem']. fix",
      steps=[
          S("get_validation"),
          S("search_docs", query="providers override active provider", docs=[PROVIDERS_OV]),
          S("propose_plan", steps=["Delete `providers.on-prem` (not a provider name)",
                                   "Set `provider.options.port` to 9000 directly (this file's provider is already onprem)",
                                   "Validate for onprem, stage prod"]),
          S("set_config", path="providers.on-prem", value=None),
          S("set_config", path="provider.options.port", value=9000),
      ],
      final="""`providers:` keys must be provider names (`onprem`, not `on-prem`) [docs/configuration.md#providers-per-cloud-overrides]. This file's provider is already onprem, so an override block isn't needed: I deleted it and set `provider.options.port: 9000`. `pskit validate -p onprem -s prod`: valid, no warnings."""),

    # ------------------------------------------------------------------ 285  stages.prod.providers.local
    C(285, provider="onprem", stage="prod", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#precedence-later-wins"],
      project=dict(files={"pskit.yml": onprem("catalog", PING + """stages:
  prod:
    providers:
      local:
        options: {port: 8443}
""", **H), **app("health", "ping")}),
      user="""Error: `stages.prod.providers` has unknown keys ['local']; supported: alibaba, aws, azure, cloudflare, digitalocean, gcp, huawei, ibm, onprem, oracle, tencent

prod on our own server should be 8443""",
      steps=[
          S("get_validation"),
          S("search_docs", query="stages providers override precedence", docs=[PRECEDENCE]),
          S("propose_plan", steps=["Rename `stages.prod.providers.local` to `stages.prod.providers.onprem`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.providers.local", value=None),
          S("set_config", path="stages.prod.providers.onprem", value={"options": {"port": 8443}}),
      ],
      final="""Under `stages.<stage>.providers` the keys are provider names; `local` is a region/server name, the provider is `onprem` [docs/configuration.md#precedence-later-wins].

Now `stages.prod.providers.onprem.options.port: 8443`. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 286  tab indentation
    C(286, provider="onprem", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("todo", """functions:
  todos:
\thandler: app.todo.todos
\tevents:
\t  - http: GET /todos
"""), **app("todo", "todos")}),
      user="I edited pskit.yml in Notepad and now it says invalid YAML: found character '\\t' that cannot start any token. I didn't change anything special!",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Rewrite pskit.yml with spaces instead of the tab characters under `todos`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="pskit.yml", content=onprem("todo", """functions:
  todos:
    handler: app.todo.todos
    events:
      - http: GET /todos
""")),
          S("validate"),
      ],
      final="""Notepad inserted tab characters for the indentation under `todos`, and YAML only allows spaces.

I rewrote those lines with spaces; nothing else changed. Validate for onprem: valid. The **YAML** page's editor (or the Code page) indents with spaces, so editing there avoids this."""),

    # ------------------------------------------------------------------ 287  whole file pasted as a list item
    C(287, provider="onprem", stage="dev", mode="auto", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#top-level"],
      project=dict(files={"pskit.yml": """- service: weather
  provider:
    name: onprem
    region: local
    options:
      host: 127.0.0.1
      port: 8080
  functions:
    now:
      handler: app.weather.now
      events:
        - http: GET /now
""", **app("weather", "now")}),
      user="pskit.yml must contain a mapping at the top level?? i copy from chat",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Remove the leading `- ` and one level of indentation, so the file is a mapping", "Validate for onprem"]),
          S("write_file", path="pskit.yml", content=onprem("weather", """functions:
  now:
    handler: app.weather.now
    events:
      - http: GET /now
""")),
          S("validate"),
      ],
      final="""The pasted text started with `- `, which made the whole file a list; pskit.yml must start with keys like `service:` [docs/configuration.md#top-level]. Removed the dash and the extra indentation. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 288  ${env:PORT, 8080} becomes a string
    C(288, provider="onprem", stage="staging", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#variables", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={"pskit.yml": onprem("kiosk", PING, port="${env:KIOSK_PORT, 8080}", **H), **app("health", "ping")}),
      user="I wanted the port to come from an environment variable with 8080 as default: ${env:KIOSK_PORT, 8080}. Staging validation: options.port must be an integer from 1 to 65535. The goal is just a different port on staging (8081) than on dev.",
      steps=[
          S("get_validation"),
          S("search_docs", query="env variable default type stages override", docs=[VARS, STAGES_OV]),
          S("propose_plan", steps=["Set `provider.options.port` to 8080", "Add `stages.staging.provider.options.port: 8081`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.port", value=8080),
          S("set_config", path="stages.staging", value={"provider": {"options": {"port": 8081}}}),
      ],
      final="""Environment variables and their defaults are text, so `${env:KIOSK_PORT, 8080}` gave the string `"8080"`, and the port must be a number [docs/configuration.md#variables].

For a per-stage port I used a stage override instead: `port: 8080`, plus `stages.staging.provider.options.port: 8081` [docs/configuration.md#stages-per-stage-overrides]. `pskit validate -p onprem -s staging`: valid (staging gets 8081, dev 8080)."""),

    # ------------------------------------------------------------------ 289  ${self:custom.port} with a quoted value
    C(289, provider="onprem", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#variables"],
      project=dict(files={"pskit.yml": onprem("rates", PING + "custom:\n  port: \"8090\"\n", port="${self:custom.port}"), **app("health", "ping")}),
      user="options.port must be an integer... port comes from custom.port",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `custom.port` to the number 8090 (unquoted)", "Validate for onprem"]),
          S("set_config", path="custom.port", value=8090),
      ],
      final="""`${self:custom.port}` keeps the type of the value, and `"8090"` was a string [docs/configuration.md#variables]. Now `custom.port: 8090`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 290  stage override memory too big
    C(290, provider="onprem", stage="prod", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#provider", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={"pskit.yml": onprem("ml-api", PING + """stages:
  prod:
    provider: {memory: 40000}
""", **H), **app("health", "ping")}),
      user="Only prod fails: provider.memory: Input should be less than or equal to 32768. I wanted prod to have 4 GB.",
      steps=[
          S("get_validation"),
          S("search_docs", query="provider memory MB range", docs=[PROVIDER_T]),
          S("propose_plan", steps=["Set `stages.prod.provider.memory` to 4096 (4 GB in MB)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.provider.memory", value=4096),
      ],
      final="""`memory` is in MB (64-32768), and 40000 MB is about 40 GB [docs/configuration.md#provider]. Dev passed because the override is only under `stages.prod`.

Set `stages.prod.provider.memory: 4096` (4 GB). `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 291  Windows path in double quotes
    C(291, provider="onprem", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("scanner", PING, extra="    data_dir: \"D:\\pskit\\scanner\"\n"), **app("health", "ping")}),
      user="""Error: invalid YAML in pskit.yml: while scanning a double-quoted scalar
...
found unknown escape character 'p'

data_dir should be D:\\pskit\\scanner on this Windows PC""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rewrite pskit.yml with `data_dir: 'D:\\pskit\\scanner'` in single quotes (backslashes stay literal)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="pskit.yml", content=onprem("scanner", PING, extra="    data_dir: 'D:\\pskit\\scanner'\n")),
          S("validate"),
      ],
      final="""In double quotes YAML reads `\\p` and `\\s` as escape sequences. In single quotes backslashes are plain characters.

Now `data_dir: 'D:\\pskit\\scanner'` (forward slashes, `D:/pskit/scanner`, work too). Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 292  bad value in the extended base file
    C(292, provider="onprem", stage="staging", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#extends-inherit-files"],
      project=dict(files={"pskit.yml": """extends: base.yml
service: reports
functions:
  daily:
    handler: app.reports.daily
    events:
      - schedule: "0 5 * * *"
""", "base.yml": """provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 80800
""", **app("reports", "daily")}),
      user="Staging validation says options.port must be an integer from 1 to 65535, but pskit.yml has no port at all. Several projects share base.yml; fix it at the source, the port is 8080.",
      steps=[
          S("get_validation"),
          S("read_file", path="base.yml"),
          S("propose_plan", steps=["In base.yml change `port: 80800` to `port: 8080`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="base.yml", content="""provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
"""),
          S("validate"),
      ],
      final="""The port comes from base.yml through `extends`, and it had an extra zero (`80800`) [docs/configuration.md#extends-inherit-files].

Fixed it in base.yml (`port: 8080`), so every project that extends it gets the fix. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 293  ${env:REDIS_URL} unset -> url_env
    C(293, provider="onprem", stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#on-premises-drivers"],
      project=dict(files={"pskit.yml": onprem("jobs", """resources:
  work:
    type: queue
    external: true
    options: {driver: redis, url: "${env:REDIS_URL}"}
functions:
  worker:
    handler: app.jobs.worker
    events:
      - queue: {resource: work}
""", **H), **app("jobs", "worker")}),
      user="unresolved variables: env:REDIS_URL . the url is only on the server not my laptop",
      steps=[
          S("get_validation"),
          S("search_docs", query="driver secret _env host environment", docs=[SECRETS]),
          S("propose_plan", steps=["Replace `url: ${env:REDIS_URL}` with `url_env: REDIS_URL` in `resources.work.options`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.work.options", value={"driver": "redis", "url_env": "REDIS_URL"}),
      ],
      final="""`${env:...}` is resolved on the machine running pskit, your laptop, where `REDIS_URL` isn't set. `url_env` is read by the host on the server when it starts [docs/resources.md#on-premises-drivers].

Now `options: {driver: redis, url_env: REDIS_URL}`. `pskit validate -p onprem -s prod`: valid. The URL also stays out of Terraform state."""),

    # ------------------------------------------------------------------ 294  ${self:...} path typo
    C(294, provider="onprem", stage="dev", mode="auto", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#variables"],
      project=dict(files={"pskit.yml": onprem("feeds", """custom:
  feeds:
    interval: 30 minutes
functions:
  poll:
    handler: app.feeds.poll
    events:
      - schedule: ${self:custom.feed.interval}
"""), **app("feeds", "poll")}),
      user="""Error: unresolved variables: self:custom.feed.interval""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Point the schedule at `${self:custom.feeds.interval}` (the key is `feeds`)", "Validate for onprem"]),
          S("set_config", path="functions.poll.events.0", value={"schedule": "${self:custom.feeds.interval}"}),
      ],
      final="""The reference said `custom.feed`, but the key is `custom.feeds` [docs/configuration.md#variables]. Fixed it to `${self:custom.feeds.interval}` (30 minutes). Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 295  options at the top level
    C(295, provider="onprem", stage="staging", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#top-level", "docs/configuration.md#provider"],
      project=dict(files={"pskit.yml": onprem("recipes", PING, **H) + "options:\n  env_file: .env.onprem\n", **app("health", "ping")}),
      user="I added options: env_file at the bottom of the file and now it says options: Extra inputs are not permitted. Where does env_file go?",
      steps=[
          S("get_validation"),
          S("search_docs", query="provider options env_file", docs=[TOP]),
          S("propose_plan", steps=["Move `env_file: .env.onprem` to `provider.options.env_file`", "Delete the top-level `options`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="options", value=None),
          S("set_config", path="provider.options.env_file", value=".env.onprem"),
      ],
      final="""`options` belongs inside `provider:` (next to `host` and `port`); at the top of the file only `service`, `provider`, `functions`, `resources`, ... are allowed [docs/configuration.md#top-level].

Moved it to `provider.options.env_file`. `pskit validate -p onprem -s staging`: valid, with a WARNING that `.env.onprem` doesn't exist yet; create it with your `KEY=VALUE` lines (and keep it out of git)."""),

    # ------------------------------------------------------------------ 296  stage at the top level
    C(296, provider="onprem", stage="prod", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#provider"],
      project=dict(files={"pskit.yml": onprem("audit", PING, **H) + "stage: prod\n", **app("health", "ping")}),
      user="In serverless.yml stage was a top-level key. pskit: stage: Extra inputs are not permitted. Where does it go?",
      steps=[
          S("get_validation"),
          S("search_docs", query="provider stage default", docs=[PROVIDER_T]),
          S("propose_plan", steps=["Delete the top-level `stage`", "Set `provider.stage` to `prod`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stage", value=None),
          S("set_config", path="provider.stage", value="prod"),
      ],
      final="""In pskit the stage lives under `provider` (default `dev`), and `--stage` overrides it [docs/configuration.md#provider].

Moved it to `provider.stage: prod`. `pskit validate -p onprem -s prod`: valid. Usually you leave it out and pass `-s prod` (or pick the stage in studio's top bar)."""),

    # ------------------------------------------------------------------ 297  package.include as a string
    C(297, provider="onprem", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#package"],
      project=dict(files={"pskit.yml": onprem("thin", PING) + "package:\n  include: app/**\n", **app("health", "ping")}),
      user="package.include not a valid list?? only want app/** in the bundle",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `package.include` to `[\"app/**\"]`", "Validate for onprem"]),
          S("set_config", path="package.include", value=["app/**"]),
      ],
      final="""`include` is a list of globs [docs/configuration.md#package]. Now `include: ["app/**"]`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 298  hook value as a string
    C(298, provider="onprem", stage="staging", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#hooks"],
      project=dict(files={"pskit.yml": onprem("web-ui", PING, **H) + "hooks:\n  before_package: npm run build\n  after_deploy: python scripts/smoke.py\n",
                          **app("health", "ping")}),
      user="hooks.before_package Input should be a valid list and same for after_deploy. its one command each",
      steps=[
          S("get_validation"),
          S("search_docs", query="hooks commands list", docs=[HOOKS]),
          S("propose_plan", steps=["Make each hook a one-item list", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="hooks", value={"before_package": ["npm run build"], "after_deploy": ["python scripts/smoke.py"]}),
      ],
      final="""Each hook is a list of commands, even for one command [docs/configuration.md#hooks]. Now `before_package: ["npm run build"]` and `after_deploy: ["python scripts/smoke.py"]`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 299  memory 512MB
    C(299, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("pdf", """functions:
  render:
    handler: app.pdf.render
    memory: 512MB
    events:
      - http: POST /render
"""), **app("pdf", "render")}),
      user="Functions page shows red: memory Input should be a valid integer, unable to parse string. I typed 512MB in the Memory box.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.render.memory` to 512 (MB is the unit already)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.render.memory", value=512),
      ],
      final="""The field is already in MB ("Memory (MB)"), so it takes only the number [docs/configuration.md#functions]. Set `memory: 512`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 300  timeout 30s
    C(300, provider="onprem", stage="prod", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("export", """functions:
  csv:
    handler: app.export.csv
    timeout: 120s
    events:
      - http: GET /export.csv
""", **H), **app("export", "csv")}),
      user="""Error: pskit.yml is invalid:
  - functions.csv.timeout: Input should be a valid integer, unable to parse string as an integer""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.csv.timeout` to 120 (seconds)", "Validate for onprem, stage prod"]),
          S("set_config", path="functions.csv.timeout", value=120),
      ],
      final="""`timeout` is a number of seconds, without a unit [docs/configuration.md#functions]. Now `timeout: 120`. `pskit validate -p onprem -s prod`: valid. On premises the host doesn't kill a handler at the timeout, but `ctx.remaining_time_ms()` counts down from it."""),
]
