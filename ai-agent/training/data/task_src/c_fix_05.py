"""Category C (fix a validation error), batch 5: on-premises. Hand-written; assembled by tools/assemble.py
(tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def C(n, **kw):
    return dict(id=f"c_fix-{n:04d}", category="c_fix", **kw)


def handlers(*names):
    """A tiny handler module with the given function names (scaffolding only)."""
    body = FUTURE
    for name in names:
        body += f"\ndef {name}(event, ctx):\n    return {{\"ok\": True, \"fn\": \"{name}\"}}\n\n"
    return body.rstrip() + "\n"


def app(module, *names):
    return {"app/__init__.py": "", f"app/{module}.py": handlers(*names)}


ONPREM_TRIGGERS = D("docs/providers.md", "onprem-on-premises", start="| Trigger |", end="| workflows |")
ONPREM_OPTIONS = D("docs/providers.md", "onprem-on-premises", start="    services:", end="workflow: embedded")
DEPLOY_TABLE = D("docs/providers.md", "onprem-on-premises", start="**Deploy targets** (`options.deploy`)", end="| `docker` | image built")
LIMITS = D("docs/providers.md", "onprem-on-premises", start="**Limits:** no cloud authorizer", end="**Limits:** no cloud authorizer")

CONVERSATIONS = [
    # ------------------------------------------------------------------ 81  auth iam on-prem (pasted)
    C(81, provider="onprem", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: parts-api
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8081
functions:
  parts:
    handler: app.parts.get_part
    events:
      - http:
          path: /parts/{id}
          method: GET
          auth: iam
""", **app("parts", "get_part")}),
      user="""  ERROR: [functions.parts] auth `iam` is not enforced on-premises; use auth: none and check tokens in the handler

what do i change""",
      steps=[
          S("get_validation"),
          S("search_docs", query="on-premises http auth", docs=[ONPREM_TRIGGERS]),
          S("propose_plan", steps=["Set `functions.parts.events.0.http.auth` to `none`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.parts.events.0.http.auth", value="none"),
      ],
      final="""The on-premises host has no IAM, so `auth` must be `none` there [docs/providers.md#onprem-on-premises].

Changed `/parts/{id}` to `auth: none`. Validate for onprem: valid.

The route is open now. If it needs protection, check a token in the handler, with its value from `${env:PARTS_API_TOKEN}`."""),

    # ------------------------------------------------------------------ 82  jwt + authorizer from Lambda
    C(82, provider="onprem", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: orders-api
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
functions:
  list-orders:
    handler: app.orders.list_orders
    events:
      - http:
          path: /orders
          method: GET
          auth: jwt
          authorizer:
            issuer: https://login.example.com/
            audience: [orders-api]
""", **app("orders", "list_orders")}),
      user="We moved this API off Lambda onto our own server. In serverless.yml /orders had a Cognito JWT authorizer, so I kept `auth: jwt` with the authorizer block. Validation for onprem staging rejects it. What's the on-prem equivalent?",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem jwt authorizer not supported", docs=[
              D("docs/providers.md", "onprem-on-premises", start="**Limits:** no cloud authorizer", end="no IAM mapping.")]),
          S("propose_plan", steps=["Set `functions.list-orders.events.0.http.auth` to `none`",
                                   "Delete `functions.list-orders.events.0.http.authorizer`",
                                   "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.list-orders.events.0.http.auth", value="none"),
          S("set_config", path="functions.list-orders.events.0.http.authorizer", value=None),
      ],
      final="""There is no equivalent: on-premises pskit has no cloud authorizer, so the host can't check the JWT for you [docs/providers.md#onprem-on-premises].

`/orders` is now `auth: none` and the `authorizer` block is gone. `pskit validate -p onprem -s staging`: valid.

To keep the protection, verify the JWT in `list_orders`: read `event.http.headers["authorization"]` and check signature, issuer `https://login.example.com/` and audience `orders-api` with a JWT library from `requirements.txt`. Until then the route is public."""),

    # ------------------------------------------------------------------ 83  port as a string
    C(83, provider="onprem", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: recipe-box
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: "8080"
functions:
  recipes:
    handler: app.recipes.list_all
    events:
      - http: GET /recipes
""", **app("recipes", "list_all")}),
      user="validate says options.port must be an integer from 1 to 65535. but my port IS 8080?? i don't understand",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Set `provider.options.port` to the number 8080 (without quotes)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.port", value=8080),
      ],
      final="""The port was written as `"8080"` with quotes, so YAML read it as text, not a number. The port must be a whole number from 1 to 65535 [docs/providers.md#onprem-on-premises].

I changed it to `port: 8080` (no quotes). Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 84  log_level verbose
    C(84, provider="onprem", stage="dev", mode="auto", page="Logs", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: sensor-hub
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8095
    log_level: verbose
functions:
  ingest:
    handler: app.sensors.ingest
    events:
      - http: POST /readings
""", **app("sensors", "ingest")}),
      user="log_level error on onprem. i want everything in the logs",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.log_level` to `DEBUG`", "Validate for onprem"]),
          S("set_config", path="provider.options.log_level", value="DEBUG"),
      ],
      final="""`verbose` isn't a level; the host takes DEBUG, INFO, WARNING or ERROR [docs/providers.md#onprem-on-premises]. Set `log_level: DEBUG`, the most detailed. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 85  log_buffer too small
    C(85, provider="onprem", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: pi-weather
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    log_buffer: 50
functions:
  read-temp:
    handler: app.weather.read_temp
    events:
      - schedule: 10 minutes
""", **app("weather", "read_temp")}),
      user="raspberry pi have small memory so i put log_buffer 50. validate give error, why not allowed",
      steps=[
          S("get_validation"),
          S("search_docs", query="log_buffer minimum", docs=[
              D("docs/providers.md", "onprem-on-premises", start="log_buffer: 5000", end="(min 100)"),
              D("docs/providers.md", "logs-and-stats", start="Entries written during", end="reloaded on restart.")]),
          S("propose_plan", steps=["Set `provider.options.log_buffer` to 100 (the minimum)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.log_buffer", value=100),
      ],
      final="""`log_buffer` can't be lower than 100 [docs/providers.md#onprem-on-premises].

I set it to 100, the smallest allowed. Validate for onprem: valid. Only the newest 100 entries stay in memory; all entries are still written to `<data_dir>/logs/host.jsonl` [docs/providers.md#logs-and-stats]."""),

    # ------------------------------------------------------------------ 86  workflow_workers 0 to pause
    C(86, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises", "docs/workflows.md#workflows"],
      project=dict(files={
          "pskit.yml": """service: invoice-run
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8088
    workflow_workers: 0
functions:
  upload:
    handler: app.invoices.upload
    events:
      - http: POST /invoices
  render:
    handler: app.invoices.render
  send:
    handler: app.invoices.send
workflows:
  monthly:
    start_at: Render
    states:
      Render: {type: task, function: render, next: Send}
      Send: {type: task, function: send, end: true}
""", **app("invoices", "upload", "render", "send")}),
      user="I set `workflow_workers: 0` in prod to pause the `monthly` workflow while finance checks the templates, but the `upload` endpoint must keep working. Validation now fails for prod. What's the right way to pause only the workflow?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `provider.options.workflow_workers` (back to the default 8)",
                                   "Set `workflows.monthly.enabled: false` (kept in the file, not deployed)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.workflow_workers", value=None),
          S("set_config", path="workflows.monthly.enabled", value=False),
      ],
      final="""`workflow_workers` is how many workflow runs execute at once and must be at least 1, so 0 can't pause anything [docs/providers.md#onprem-on-premises].

Changed:
- removed `workflow_workers` (default 8 again);
- `workflows.monthly.enabled: false`: the workflow stays in pskit.yml but is not deployed.

`pskit validate -p onprem -s prod`: valid, with a WARNING that `monthly` is disabled. `upload` is not affected. When finance is done, remove `enabled: false` and deploy again."""),

    # ------------------------------------------------------------------ 87  capture_output "false" as text
    C(87, provider="onprem", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: batch-tools
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8100
    capture_output: "false"
functions:
  cleanup:
    handler: app.tools.cleanup
    events:
      - schedule: "30 2 * * *"
""", **app("tools", "cleanup")}),
      user="""  ERROR: [provider.options.capture_output] options.capture_output must be true or false

it IS false""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.capture_output` to the boolean `false` (no quotes)",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.capture_output", value=False),
      ],
      final="""It was `"false"` in quotes, which YAML reads as text, and the option needs a real true/false [docs/providers.md#onprem-on-premises].

Now `capture_output: false`. Validate for onprem: valid. `print()` and stdout/stderr lines are no longer recorded; `logging` records still are."""),

    # ------------------------------------------------------------------ 88  poll_seconds 0
    C(88, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises", "docs/resources.md#on-premises-drivers"],
      project=dict(files={
          "pskit.yml": """service: photo-drop
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8082
    poll_seconds: 0
functions:
  thumbnail:
    handler: app.photos.thumbnail
    events:
      - storage: {bucket: photos, suffix: .jpg}
""", **app("photos", "thumbnail")}),
      user="I want my function to start right away when a photo is added, so I set poll_seconds to 0. Now there's a red error. Help?",
      steps=[
          S("get_validation"),
          S("search_docs", query="poll_seconds", docs=[
              D("docs/resources.md", "on-premises-drivers", start="The host normally keeps", end="every `poll_seconds`, and each message or object change triggers the function like any local event.")]),
          S("propose_plan", steps=["Set `provider.options.poll_seconds` to 0.2 (check five times a second)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.poll_seconds", value=0.2),
      ],
      final="""`poll_seconds` is how often the host looks for new files, so it must be more than 0 [docs/resources.md#on-premises-drivers].

I set it to `0.2`: the host checks five times a second (the default is 0.5) [docs/providers.md#onprem-on-premises]. Validate for onprem: valid. A new `.jpg` in `photos` starts `thumbnail` within a fraction of a second."""),

    # ------------------------------------------------------------------ 89  deploy method ftp
    C(89, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: shift-planner
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy:
      method: ftp
functions:
  shifts:
    handler: app.shifts.list_shifts
    events:
      - http: GET /shifts
""", **app("shifts", "list_shifts")}),
      user="deploy method ftp not ok? our server only we upload with ftp before",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem deploy method options", docs=[
              D("docs/providers.md", "onprem-on-premises", start="**Deploy targets** (`options.deploy`)", end="| `docker` | image built")]),
          S("ask_user", question="pskit can't use FTP. It copies with SSH (`ssh`) or runs a Docker container (`docker`). Does the server accept SSH? If yes, give its address and SSH user.",
            options=["Yes, SSH works (I'll type host and user)", "No SSH on that server"],
            answer="yes ssh work. host 192.0.2.30 user deploy"),
          S("propose_plan", steps=["Set `provider.options.deploy` to `{method: ssh, host: 192.0.2.30, user: deploy}`",
                                   "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy", value={"method": "ssh", "host": "192.0.2.30", "user": "deploy"}),
      ],
      final="""pskit has no FTP: `deploy.method` is `local`, `ssh` (or `scp`) or `docker` [docs/providers.md#onprem-on-premises].

Now `deploy: {method: ssh, host: 192.0.2.30, user: deploy}`. Validate for onprem staging: no errors, one WARNING: the server must already have python3.12 on PATH. If it doesn't, add `python: bundle` under `deploy` and pskit ships a portable Python."""),

    # ------------------------------------------------------------------ 90  ssh without host
    C(90, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: kiosk-menu
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy:
      method: ssh
      user: kiosk
      python: bundle
      target_os: linux
      install: systemd
      sudo: true
functions:
  menu:
    handler: app.menu.today
    events:
      - http: GET /menu
""", **app("menu", "today")}),
      user="why can't I deploy? the Deploy page shows an error for prod",
      steps=[
          S("get_validation"),
          S("ask_user", question="Deploy over SSH needs the server's address, and `options.deploy.host` is missing. What is the IP or host name of the kiosk server?",
            answer="198.51.100.23"),
          S("propose_plan", steps=["Set `provider.options.deploy.host` to `198.51.100.23`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.host", value="198.51.100.23"),
      ],
      final="""With `method: ssh`, pskit must know which server to connect to, and `deploy.host` was missing [docs/providers.md#onprem-on-premises].

I added `host: 198.51.100.23` under `deploy`. Validate for onprem prod: valid. You can deploy from the **Deploy** page now; studio asks you to confirm because it's a `prod` stage."""),

    # ------------------------------------------------------------------ 91  systemd on windows target
    C(91, provider="onprem", stage="staging", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: scanner-bridge
provider:
  name: onprem
  region: local
  architecture: x86_64
  options:
    host: 0.0.0.0
    port: 8085
    deploy:
      method: ssh
      host: 192.0.2.44
      user: svc-scan
      python: bundle
      target_os: windows
      install: systemd
      sudo: true
functions:
  scan-done:
    handler: app.scanner.done
    events:
      - http: POST /scans
""", **app("scanner", "done")}),
      user="The scanner bridge runs on a Windows Server 2022 machine reached over OpenSSH, so I set `target_os: windows`. I copied `install: systemd` from example 17. Staging validation now says systemd is only valid on Linux. Fix it for Windows, keep the bundled Python.",
      steps=[
          S("get_validation"),
          S("search_docs", query="install systemd process target_os", docs=[LIMITS]),
          S("propose_plan", steps=["Set `provider.options.deploy.install` to `process`",
                                   "Delete `provider.options.deploy.sudo` (only needed for systemd units)",
                                   "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.install", value="process"),
          S("set_config", path="provider.options.deploy.sudo", value=None),
      ],
      final="""systemd exists only on Linux, so `install: systemd` is rejected with `target_os: windows` [docs/providers.md#onprem-on-premises].

Changed `deploy.install` to `process` and removed `sudo: true`, which was only there to write the unit to /etc/systemd/system. `python: bundle` is kept. `pskit validate -p onprem -s staging`: valid.

With `process` the host is started by `onprem_ctl.py start` and is not restarted automatically after a reboot, so plan a redeploy (or a Windows scheduled task) after the server restarts."""),

    # ------------------------------------------------------------------ 92  systemd with docker
    C(92, provider="onprem", stage="prod", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: label-printer
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8090
    deploy:
      method: docker
      host: 203.0.113.12
      user: ops
      image: pskit/label-printer:prod
      install: systemd
functions:
  print-label:
    handler: app.labels.print_label
    events:
      - http: POST /labels
""", **app("labels", "print_label")}),
      user="docker deploy + install systemd rejected on prod. keep docker",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `provider.options.deploy.install`", "Validate for onprem, stage prod"]),
          S("set_config", path="provider.options.deploy.install", value=None),
      ],
      final="""`install: systemd` isn't used with `method: docker`; the container is kept running by Docker's `restart` policy (default `unless-stopped`) [docs/providers.md#onprem-on-premises]. Removed `install`. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 93  docker_host without scheme
    C(93, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: ocr-service
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy:
      method: docker
      docker_host: 192.0.2.10
functions:
  ocr:
    handler: app.ocr.read_text
    events:
      - http: POST /ocr
""", **app("ocr", "read_text")}),
      user="docker_host must be a docker host URL?? i give the ip of the docker server",
      steps=[
          S("get_validation"),
          S("ask_user", question="`docker_host` needs a URL such as `ssh://user@192.0.2.10`. Which SSH user should pskit log in with on 192.0.2.10?",
            answer="ubuntu"),
          S("propose_plan", steps=["Set `provider.options.deploy.docker_host` to `ssh://ubuntu@192.0.2.10`",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.docker_host", value="ssh://ubuntu@192.0.2.10"),
      ],
      final="""A bare IP isn't enough: `docker_host` must start with `ssh://`, `tcp://`, `unix://` or `npipe://` [docs/providers.md#onprem-on-premises].

Now `docker_host: ssh://ubuntu@192.0.2.10`. Validate for onprem: valid. pskit builds the image on your machine and runs it on the server over SSH; the `ubuntu` user needs passwordless sudo if Docker must be installed there."""),

    # ------------------------------------------------------------------ 94  deploy: rsync string
    C(94, provider="onprem", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: team-wiki
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: rsync
functions:
  pages:
    handler: app.wiki.pages
    events:
      - http: GET /pages
""", **app("wiki", "pages")}),
      user="I wrote `deploy: rsync` because that's how we copy files to our server 203.0.113.15 (user ops). Validation doesn't like it. Can you write it the right way? Put it in /opt/pskit/team-wiki.",
      steps=[
          S("get_validation"),
          S("search_docs", query="deploy ssh url form", docs=[DEPLOY_TABLE]),
          S("propose_plan", steps=["Set `provider.options.deploy` to `ssh://ops@203.0.113.15/opt/pskit/team-wiki`",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy", value="ssh://ops@203.0.113.15/opt/pskit/team-wiki"),
      ],
      final="""pskit doesn't use rsync. `deploy` can be `local`, `ssh`, `docker`, an `ssh://user@host/path` URL, or a mapping with `method` [docs/providers.md#onprem-on-premises].

I wrote it as the short URL form:

```yaml
provider:
  options:
    deploy: ssh://ops@203.0.113.15/opt/pskit/team-wiki
```

Validate for onprem: no errors, one WARNING: the server must already have python3.12 on PATH. If it doesn't, use the mapping form with `python: bundle`."""),

    # ------------------------------------------------------------------ 95  target_arch armv7
    C(95, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: garden-water
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy:
      method: ssh
      host: 192.0.2.77
      user: pi
      python: bundle
      target_os: linux
      target_arch: armv7
functions:
  water:
    handler: app.garden.water
    events:
      - schedule: "0 6 * * *"
""", **app("garden", "water")}),
      user="raspberry pi deploy, target_arch armv7 give error",
      steps=[
          S("get_validation"),
          S("ask_user", question="pskit supports `x86_64` and `arm64` only. On the Pi, what does `uname -m` print?",
            options=["aarch64 (64-bit OS)", "armv7l (32-bit OS)"],
            answer="aarch64 (64-bit OS)"),
          S("propose_plan", steps=["Set `provider.options.deploy.target_arch` to `arm64`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.target_arch", value="arm64"),
      ],
      final="""`target_arch` must be `auto`, `x86_64` or `arm64` [docs/providers.md#onprem-on-premises]. Your Pi runs a 64-bit OS (`aarch64`), which is `arm64`.

Set `target_arch: arm64`. Validate for onprem: valid. pskit now picks arm64 pip wheels and the arm64 bundled Python for the Pi."""),

    # ------------------------------------------------------------------ 96  python embedded
    C(96, provider="onprem", stage="staging", mode="auto", page="Deploy", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: meter-reader
provider:
  name: onprem
  region: local
  runtime: python3.11
  architecture: x86_64
  options:
    host: 0.0.0.0
    port: 8091
    deploy:
      method: ssh
      host: 198.51.100.40
      user: meter
      python: embedded
      target_os: linux
functions:
  reading:
    handler: app.meter.reading
    events:
      - http: POST /readings
""", **app("meter", "reading")}),
      user="The staging box (198.51.100.40) has no Python at all and we can't install packages on it. I put `python: embedded` hoping pskit would ship an interpreter with the app. Validation says the value is wrong. Use whatever option does that.",
      steps=[
          S("get_validation"),
          S("search_docs", query="server has no python bundle", docs=[
              D("docs/providers.md", "onprem-on-premises", start="When the server has **no Python**", end="(the image is `FROM python:<minor>-slim`).")]),
          S("propose_plan", steps=["Set `provider.options.deploy.python` to `bundle`", "Validate for onprem, stage staging"]),
          S("set_config", path="provider.options.deploy.python", value="bundle"),
      ],
      final="""The value is `bundle`, not `embedded`: `python` takes `auto`, `system` or `bundle`, and `bundle` ships a portable CPython with the app [docs/providers.md#onprem-on-premises].

Set `deploy.python: bundle`. `pskit validate -p onprem -s staging`: valid. The first deploy downloads a python3.11 linux/x86_64 build, so the machine that runs `pskit deploy` needs network access (not the server)."""),

    # ------------------------------------------------------------------ 97  sudo: required
    C(97, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: stock-alerts
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy:
      method: ssh
      host: 192.0.2.61
      user: alerts
      python: bundle
      target_os: linux
      install: systemd
      sudo: required
functions:
  check-stock:
    handler: app.stock.check
    events:
      - schedule: 15 minutes
""", **app("stock", "check")}),
      user="prod validate: options.deploy.sudo must be a boolean. i write required because systemd need sudo",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.deploy.sudo` to `true`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.sudo", value=True),
      ],
      final="""`sudo` is a yes/no switch, so it takes `true` or `false`, not `required` [docs/providers.md#onprem-on-premises].

Now `sudo: true`. `pskit validate -p onprem -s prod`: valid. pskit runs `sudo -n`, so the `alerts` user needs passwordless sudo on 192.0.2.61 to write the systemd unit."""),

    # ------------------------------------------------------------------ 98  deploy.port quoted
    C(98, provider="onprem", stage="dev", mode="ask", page="Setup", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: badge-scan
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy:
      method: ssh
      host: 203.0.113.50
      user: badge
      port: "2222"
      python: bundle
      target_os: linux
functions:
  scan:
    handler: app.badges.scan
    events:
      - http: POST /scan
""", **app("badges", "scan")}),
      user="""badge-scan -> On-premises [experimental] stage=dev region=local
  1 function(s), 0 workflow(s)
  ERROR: [provider.options.deploy] options.deploy.port must be an integer from 1 to 65535

ssh port on that box is 2222, Test SSH connection works with it""",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Set `provider.options.deploy.port` to the number 2222 (no quotes)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.port", value=2222),
      ],
      final="""2222 is fine, but it was quoted (`"2222"`), so YAML read it as text; the SSH port must be a number [docs/providers.md#onprem-on-premises].

Changed to `port: 2222`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 99  services.schedule directory
    C(99, provider="onprem", stage="dev", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: nightly-sync
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
    services:
      schedule: {use: directory, path: /var/pskit/schedules}
      queue: builtin
functions:
  sync:
    handler: app.sync.run
    events:
      - schedule: "0 1 * * *"
""", **app("sync", "run")}),
      user="On AWS our schedules were EventBridge rules. I tried to keep them in a folder with services.schedule use: directory, but validate rejects it. How do on-prem schedules work then?",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem services schedule builtin", docs=[ONPREM_OPTIONS]),
          S("propose_plan", steps=["Set `provider.options.services.schedule` to `builtin`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.services.schedule", value="builtin"),
      ],
      final="""There is no EventBridge on-premises: the host process runs the scheduler itself, so `services.schedule` only supports `builtin` [docs/providers.md#onprem-on-premises].

Set `services.schedule: builtin`. Validate for onprem: valid. Your `0 1 * * *` cron stays in the function's `schedule` event, and the host fires it."""),

    # ------------------------------------------------------------------ 100  services.storage directory without path
    C(100, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: doc-inbox
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8083
    services:
      storage: {use: directory}
functions:
  new-doc:
    handler: app.docs.new_doc
    events:
      - storage: {bucket: inbox, suffix: .pdf}
""", **app("docs", "new_doc")}),
      user="I want to use a folder we already have for the files. I put use: directory but validate says something about path. What path?",
      steps=[
          S("get_validation"),
          S("ask_user", question="`use: directory` needs the folder where the buckets live (each bucket is a subfolder). Which folder do you already have?",
            answer="D:/shared/pskit-buckets"),
          S("propose_plan", steps=["Set `provider.options.services.storage.path` to `D:/shared/pskit-buckets`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.services.storage.path", value="D:/shared/pskit-buckets"),
      ],
      final="""With `use: directory` pskit must know which folder to use, and `path` was missing [docs/providers.md#onprem-on-premises].

Now `storage: {use: directory, path: D:/shared/pskit-buckets}`. Validate for onprem: valid. The `inbox` bucket is the folder `D:/shared/pskit-buckets/inbox`; a new `.pdf` there runs `new-doc`. Files already in the folder at the first start are recorded and don't trigger it."""),
]
