"""Category C (fix a validation error), batch 11: on-premises deploy options and host tuning (onprem only).
Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import D, S  # noqa: E402
from _onprem_c import C, app, onprem  # noqa: E402

P = "docs/providers.md"
A = "onprem-on-premises"
DEPLOY_YAML = D(P, A, start="    deploy:", end="method: local")
TUNING = D(P, A, start="    execution_retention: 500", end="capture_output: true")
TARGETS = D(P, A, start="**Deploy targets**", end="| `docker` |")
LIMITS = D(P, A, start="**Limits:**", end="**Limits:**")
HOSTBIND = D(P, A, start="`options.host` is the bind address", end="`options.host` is the bind address")
SSH_PARA = D(P, A, start="SSH and `scp` write", end="SSH and `scp` write")
REMOTE_DOCKER = D(P, A, start="Remote Docker (`method: docker` plus `host`", end="Remote Docker (`method: docker` plus `host`")
NO_PYTHON = D(P, A, start="When the server has **no Python**", end="When the server has **no Python**")
OPTIONS_ROW = D("docs/configuration.md", "provider", start="| `options` |", end="| `options` |")

CONVERSATIONS = [
    # ------------------------------------------------------------------ 201  execution_retention 0
    C(201, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("approvals", """functions:
  check:
    handler: app.flow.check
workflows:
  approve:
    start_at: Check
    states:
      Check: {type: task, function: check}
""", extra="    execution_retention: 0\n"), **app("flow", "check")}),
      user="I don't want the host to keep old workflow runs on disk, so I put execution_retention: 0. Now validate complains. Is there a way to keep nothing?",
      steps=[
          S("get_validation"),
          S("search_docs", query="execution_retention workflow executions kept", docs=[TUNING]),
          S("propose_plan", steps=["Set `provider.options.execution_retention` to 1 (the smallest allowed)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.execution_retention", value=1),
      ],
      final="""`execution_retention` counts the finished executions kept under `<data_dir>/executions`, and it must be at least 1, so "keep nothing" isn't possible [docs/providers.md#onprem-on-premises].

I set `execution_retention: 1`: only the newest finished run stays on disk. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 202  workflow_workers as text
    C(202, provider="onprem", stage="staging", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("render-farm", """functions:
  frame:
    handler: app.render.frame
workflows:
  render:
    start_at: Frame
    states:
      Frame: {type: task, function: frame}
""", host="0.0.0.0", extra="    workflow_workers: \"16\"\n"), **app("render", "frame")}),
      user="staging: options.workflow_workers must be an integer >= 1. it IS 16??",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Write `provider.options.workflow_workers` as the number 16, not the string \"16\"", "Validate for onprem, stage staging"]),
          S("set_config", path="provider.options.workflow_workers", value=16),
      ],
      final="""It was the quoted string `"16"`; the option needs a YAML integer [docs/providers.md#onprem-on-premises]. Now `workflow_workers: 16`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 203  deploy sftp URL
    C(203, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises", "docs/configuration.md#provider"],
      project=dict(files={"pskit.yml": onprem("billing", """functions:
  invoice:
    handler: app.billing.invoice
    events:
      - http: POST /invoices
""", host="0.0.0.0", extra="    deploy: sftp://pskit@192.0.2.10/opt/pskit/billing\n"), **app("billing", "invoice")}),
      user="We used to copy Lambda zips with sftp, so I wrote deploy: sftp://pskit@192.0.2.10/opt/pskit/billing. pskit says options.deploy must be local, ssh, docker... What's the right form?",
      steps=[
          S("get_validation"),
          S("search_docs", query="deploy ssh url method scp", docs=[OPTIONS_ROW, TARGETS]),
          S("propose_plan", steps=["Change `provider.options.deploy` to `ssh://pskit@192.0.2.10/opt/pskit/billing` (same user, host and path)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy", value="ssh://pskit@192.0.2.10/opt/pskit/billing"),
      ],
      final="""pskit has no `sftp` transport. The deploy string is `local`, `ssh`, `docker` or an `ssh://user@host/path` URL, and `ssh` (alias `scp`) copies one archive to the server and starts it [docs/configuration.md#provider].

Changed it to `deploy: ssh://pskit@192.0.2.10/opt/pskit/billing`. `pskit validate -p onprem -s prod`: valid, with one WARNING: the server needs python3.12 on PATH. If it doesn't have it, add `python: bundle` (that needs the mapping form of `deploy`)."""),

    # ------------------------------------------------------------------ 204  deploy as a list
    C(204, provider="onprem", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("sensor-hub", """functions:
  ingest:
    handler: app.sensors.ingest
    events:
      - http: POST /readings
""", host="0.0.0.0", extra="    deploy: [ssh, 192.0.2.11, bundle]\n"), **app("sensors", "ingest")}),
      user="options.deploy must be a string or a mapping. i put ssh, the ip and bundle python in list, what wrong",
      steps=[
          S("get_validation"),
          S("search_docs", query="deploy method ssh host python bundle", docs=[NO_PYTHON]),
          S("propose_plan", steps=["Replace the list with a mapping: `{method: ssh, host: 192.0.2.11, python: bundle}`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy", value={"method": "ssh", "host": "192.0.2.11", "python": "bundle"}),
      ],
      final="""A list has no names, so pskit can't know which value is the host. `deploy` must be a mapping (or one string) [docs/providers.md#onprem-on-premises].

Now:
```yaml
provider:
  options:
    deploy: {method: ssh, host: 192.0.2.11, python: bundle}
```
Validate for onprem: valid. `python: bundle` ships a portable CPython, so the server needs no Python."""),

    # ------------------------------------------------------------------ 205  target_os ubuntu
    C(205, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("photo-share", """functions:
  upload:
    handler: app.photos.upload
    events:
      - http: POST /photos
""", host="0.0.0.0", extra="    deploy:\n      method: ssh\n      host: 192.0.2.10\n      python: bundle\n      target_os: ubuntu\n"),
          **app("photos", "upload")}),
      user="my server is Ubuntu 22.04 so I wrote target_os: ubuntu. Validation for staging says it must be one of auto, linux, windows, darwin. Is Ubuntu not supported??",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.deploy.target_os` to `linux` (Ubuntu is Linux)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.target_os", value="linux"),
      ],
      final="""Ubuntu is supported: `target_os` names the operating-system family, not the distribution, so Ubuntu is `linux` [docs/providers.md#onprem-on-premises].

Set `target_os: linux`. `pskit validate -p onprem -s staging`: valid. (For SSH, `auto` already means linux, so you could also delete the line.)"""),

    # ------------------------------------------------------------------ 206  install: service
    C(206, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("ticketing", """functions:
  tickets:
    handler: app.tickets.handle
    events:
      - http: ANY /tickets
""", host="0.0.0.0", extra="    deploy:\n      method: ssh\n      host: 192.0.2.10\n      python: bundle\n      install: service\n"),
          **app("tickets", "handle")}),
      user="Prod requirement: the host must come back by itself after the server reboots, so I asked for install: service. Validation says install must be process or systemd. The SSH user pskit has passwordless sudo.",
      steps=[
          S("get_validation"),
          S("search_docs", query="install systemd sudo restart", docs=[SSH_PARA]),
          S("propose_plan", steps=["Set `provider.options.deploy.install` to `systemd`",
                                   "Set `provider.options.deploy.sudo` to true (units go to /etc/systemd/system)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.install", value="systemd"),
          S("set_config", path="provider.options.deploy.sudo", value=True),
      ],
      final="""The value for a managed service is `systemd`; `install` only accepts `process` or `systemd` [docs/providers.md#onprem-on-premises].

Set `install: systemd` and `sudo: true`, because the unit is written to /etc/systemd/system and apply runs `systemctl restart`. A systemd unit starts again after a reboot. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 207  python: "3.12"
    C(207, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("quiz-bot", """functions:
  answer:
    handler: app.quiz.answer
    events:
      - http: POST /answer
""", host="0.0.0.0", extra="    deploy:\n      method: ssh\n      host: 192.0.2.11\n      python: \"3.12\"\n"),
          **app("quiz", "answer")}),
      user="deploy.python must be one of auto, system, bundle?? i want python 3.12 on server",
      steps=[
          S("get_validation"),
          S("search_docs", query="deploy python system bundle server", docs=[NO_PYTHON]),
          S("ask_user", question="Does the server already have Python 3.12 installed, or should pskit ship one with the app?",
            options=["It already has python3.12", "Ship one (bundle)"], answer="no python on it, ship it"),
          S("propose_plan", steps=["Set `provider.options.deploy.python` to `bundle`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.python", value="bundle"),
      ],
      final="""`deploy.python` says *where* Python comes from (`system` or `bundle`), not the version; the version is `provider.runtime`, python3.12 by default [docs/providers.md#onprem-on-premises].

Set `python: bundle`: a portable CPython 3.12 is downloaded at deploy and copied with the app, so the server needs no Python. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 208  docker_args string
    C(208, provider="onprem", stage="staging", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("ocr", """functions:
  scan:
    handler: app.ocr.scan
    events:
      - http: POST /scan
""", host="0.0.0.0", extra="    deploy:\n      method: docker\n      docker_args: \"--memory 1g --cpus 2\"\n"), **app("ocr", "scan")}),
      user="docker_args must be a list of strings. limit container to 1g / 2 cpus",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.deploy.docker_args` to `[\"--memory\", \"1g\", \"--cpus\", \"2\"]`", "Validate for onprem, stage staging"]),
          S("set_config", path="provider.options.deploy.docker_args", value=["--memory", "1g", "--cpus", "2"]),
      ],
      final="""`docker_args` is a list, one item per argument; pskit doesn't split a string. Now `docker_args: ["--memory", "1g", "--cpus", "2"]`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 209  user@host in host
    C(209, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("crm-sync", """functions:
  sync:
    handler: app.crm.sync
    events:
      - schedule: 30 minutes
""", host="0.0.0.0", extra="    deploy:\n      method: ssh\n      host: deploy@192.0.2.20\n      python: bundle\n"), **app("crm", "sync")}),
      user="""  ERROR: [provider.options.deploy] options.deploy.host contains characters that are not safe to pass to ssh

this is how I type it in ssh every day""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Split it: `deploy.host: 192.0.2.20` and `deploy.user: deploy`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.host", value="192.0.2.20"),
          S("set_config", path="provider.options.deploy.user", value="deploy"),
      ],
      final="""`host` is only the address; the login name goes in `user`, so the `@` was refused [docs/providers.md#onprem-on-premises].

Now `host: 192.0.2.20` and `user: deploy`, the same login as `ssh deploy@192.0.2.20`. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 210  Windows domain user, YAML escape
    C(210, provider="onprem", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("intranet", """functions:
  news:
    handler: app.news.latest
    events:
      - http: GET /news
""", host="0.0.0.0", extra="    deploy:\n      method: ssh\n      host: 192.0.2.10\n      python: bundle\n      user: \"CORP\\deploy\"\n"),
          **app("news", "latest")}),
      user="The whole file is broken now, studio says invalid YAML, unknown escape character. I only added our domain user CORP\\deploy.",
      steps=[
          S("get_validation"),
          S("ask_user", question="The SSH user can only use letters, digits, '.', '_' and '-'. What is the plain login name on the Linux server (without the CORP\\ domain part)?",
            answer="it's just deploy on that box"),
          S("propose_plan", steps=["Rewrite pskit.yml with `deploy.user: deploy` (the file doesn't parse, so it is saved whole)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="pskit.yml", content=onprem("intranet", """functions:
  news:
    handler: app.news.latest
    events:
      - http: GET /news
""", host="0.0.0.0", extra="    deploy:\n      method: ssh\n      host: 192.0.2.10\n      python: bundle\n      user: deploy\n")),
          S("validate"),
      ],
      final="""In double quotes YAML reads `\\d` as an escape sequence, so the whole file failed to parse. A domain prefix wouldn't work anyway: `deploy.user` may only contain letters, digits, `.`, `_` and `-` [docs/providers.md#onprem-on-premises].

Set `user: deploy`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 211  path with a space
    C(211, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("shop", """functions:
  catalog:
    handler: app.shop.catalog
    events:
      - http: GET /catalog
""", host="0.0.0.0", extra="    deploy:\n      method: ssh\n      host: 192.0.2.11\n      python: bundle\n      path: /opt/my apps/shop\n"),
          **app("shop", "catalog")}),
      user="Our staging box keeps apps in '/opt/my apps/'. Validation: options.deploy.path contains characters that are not safe to pass to ssh. I can create a new folder if needed, ops don't care about the name.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.deploy.path` to `/opt/my-apps/shop` (dash instead of space)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.path", value="/opt/my-apps/shop"),
      ],
      final="""Spaces are not allowed in `deploy.path`, because it is passed to ssh and scp on a command line [docs/providers.md#onprem-on-premises].

Set `path: /opt/my-apps/shop`. `pskit validate -p onprem -s staging`: valid. The folder is created at apply (with `sudo: true` if the SSH user can't write to /opt)."""),

    # ------------------------------------------------------------------ 212  image name with a space
    C(212, provider="onprem", stage="dev", mode="auto", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("pricing", """functions:
  quote:
    handler: app.pricing.quote
    events:
      - http: POST /quote
""", host="0.0.0.0", extra="    deploy:\n      method: docker\n      image: \"pricing api:dev\"\n"), **app("pricing", "quote")}),
      user="docker image name error not safe to pass to docker. fix pls",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.deploy.image` to `pricing-api:dev`", "Validate for onprem"]),
          S("set_config", path="provider.options.deploy.image", value="pricing-api:dev"),
      ],
      final="""Docker image names can't contain spaces [docs/providers.md#onprem-on-premises]. Now `image: pricing-api:dev`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 213  install_docker sometimes
    C(213, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("booking", """functions:
  book:
    handler: app.booking.book
    events:
      - http: POST /book
""", host="0.0.0.0", extra="    deploy:\n      method: docker\n      host: 192.0.2.10\n      install_docker: sometimes\n"),
          **app("booking", "book")}),
      user="I wrote install_docker: sometimes because I want Docker installed only when the server doesn't have it. Prod validation says it must be a boolean.",
      steps=[
          S("get_validation"),
          S("search_docs", query="install_docker missing docker server", docs=[REMOTE_DOCKER]),
          S("propose_plan", steps=["Set `provider.options.deploy.install_docker` to true (installs only when Docker is missing)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.install_docker", value=True),
      ],
      final="""`true` already means "only when missing": the script on the server installs Docker only when it isn't there [docs/providers.md#onprem-on-premises]. The option must be true or false.

Set `install_docker: true` (the default for a remote host). `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 214  host 127.0.0.1 on a remote target
    C(214, provider="onprem", stage="staging", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("kiosk-api", """functions:
  menu:
    handler: app.kiosk.menu
    events:
      - http: GET /menu
""", extra="    deploy: {method: ssh, host: 192.0.2.11, python: bundle}\n"), **app("kiosk", "menu")}),
      user="Validation is green but there's a warning about the host binding to 127.0.0.1 on the target. The kiosks on the shop LAN must call this API directly. Please fix it so they can.",
      steps=[
          S("get_validation"),
          S("search_docs", query="options.host bind address 0.0.0.0 remote", docs=[HOSTBIND]),
          S("propose_plan", steps=["Set `provider.options.host` to `0.0.0.0`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
      ],
      final="""`options.host` is the bind address on the server, and with 127.0.0.1 only the server itself could call it [docs/providers.md#onprem-on-premises].

Set `host: 0.0.0.0`. `pskit validate -p onprem -s staging`: valid, no warnings. Also open port 8080 in the server's firewall for the kiosk network."""),

    # ------------------------------------------------------------------ 215  systemd without sudo
    C(215, provider="onprem", stage="prod", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("ledger", """functions:
  post:
    handler: app.ledger.post
    events:
      - http: POST /entries
""", host="0.0.0.0", extra="    deploy: {method: ssh, host: 192.0.2.20, python: bundle, install: systemd}\n"), **app("ledger", "post")}),
      user="clear the systemd sudo warning on prod. ssh user is not root",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.deploy.sudo` to true", "Validate for onprem, stage prod"]),
          S("set_config", path="provider.options.deploy.sudo", value=True),
      ],
      final="""Units are written to /etc/systemd/system, which a non-root user can't write without sudo [docs/providers.md#onprem-on-premises]. Set `sudo: true`. `pskit validate -p onprem -s prod`: valid, no warnings. The sudo is `sudo -n`, so the sudoers rule must not ask for a password."""),

    # ------------------------------------------------------------------ 216  remote docker with sudo: false
    C(216, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("thumbs", """functions:
  resize:
    handler: app.images.resize
    events:
      - http: POST /resize
""", host="0.0.0.0", extra="    deploy: {method: docker, host: 198.51.100.7, sudo: false}\n"), **app("images", "resize")}),
      user="On EC2 I always avoided sudo, so I set sudo: false for the Docker deploy to our GPU box. Validate warns that installing Docker uses sudo. Do I need it?",
      steps=[
          S("get_validation"),
          S("search_docs", query="remote docker sudo install", docs=[REMOTE_DOCKER]),
          S("ask_user", question="Is Docker already installed on 198.51.100.7, and can the SSH user run `docker` without sudo?",
            options=["Yes, Docker is there and the user is in the docker group", "No / not sure"], answer="No / not sure"),
          S("propose_plan", steps=["Delete `provider.options.deploy.sudo` (remote Docker defaults to sudo: true)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.sudo", value=None),
      ],
      final="""Yes, unless Docker is already set up for that user: pskit installs Docker when it is missing, and that needs passwordless sudo [docs/providers.md#onprem-on-premises].

I removed `sudo: false`, so the default `sudo: true` applies. Validate for onprem: valid, no warnings. If you later confirm Docker is there and the user is in the docker group, `sudo: false` together with `install_docker: false` is fine."""),

    # ------------------------------------------------------------------ 217  auth: ssh-key
    C(217, provider="onprem", stage="staging", mode="ask", page="Setup", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("chat-relay", """functions:
  relay:
    handler: app.chat.relay
    events:
      - http: POST /relay
""", host="0.0.0.0", extra="    deploy: {method: ssh, host: 192.0.2.11, python: bundle, auth: ssh-key}\n"), **app("chat", "relay")}),
      user="warning auth must be key, agent or password, not 'ssh-key'. my key is loaded in ssh-agent on laptop",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.deploy.auth` to `agent` (your key is in the SSH agent)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.auth", value="agent"),
      ],
      final="""`auth` takes `key`, `agent` or `password`, and with your key in ssh-agent the right one is `agent` [docs/providers.md#onprem-on-premises].

Set `auth: agent`. `pskit validate -p onprem -s staging`: valid, no warnings. You can test the login on **Setup & credentials** > On-premises connection > **Test SSH connection**."""),

    # ------------------------------------------------------------------ 218  pem path missing
    C(218, provider="onprem", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("garden-log", """functions:
  water:
    handler: app.garden.water
    events:
      - schedule: "0 7 * * *"
""", host="0.0.0.0", extra="    deploy: {method: ssh, host: 192.0.2.10, python: bundle, pem: keys/garden.pem}\n"), **app("garden", "water")}),
      user="it says options.deploy.identity_file 'keys/garden.pem' does not exist yet. I don't have any pem file, I log in to the box with my normal ssh setup",
      steps=[
          S("get_validation"),
          S("search_docs", query="pem identity_file ssh agent default key", docs=[
              D(P, A, start="- **Credentials:**", end="- **Credentials:**")]),
          S("propose_plan", steps=["Delete `provider.options.deploy.pem` so pskit uses your SSH agent / default key", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.pem", value=None),
      ],
      final="""`pem` points at a key file, and `keys/garden.pem` doesn't exist. Without it pskit uses the SSH agent or your default key, like your normal `ssh` [docs/providers.md#onprem-on-premises].

Removed `pem`. Validate for onprem: valid, no warnings."""),

    # ------------------------------------------------------------------ 219  env_file as a list
    C(219, provider="onprem", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("payroll", """functions:
  run:
    handler: app.payroll.run
    events:
      - schedule: "0 2 1 * *"
""", host="0.0.0.0", extra="    env_file: [.env.onprem, .env.prod]\n"), **app("payroll", "run"),
          ".env.onprem": "LOG_FORMAT=json\n"}),
      user="I split the host secrets into .env.onprem and .env.prod and listed both under env_file. Prod validation: options.env_file must be a file path. Only one is allowed? Keep the one that already exists in the repo, ops merge the rest into it.",
      steps=[
          S("get_validation"),
          S("search_docs", query="env_file KEY=VALUE host", docs=[D(P, A, start="    env_file: .env.onprem", end="never written to Terraform state")]),
          S("propose_plan", steps=["Set `provider.options.env_file` to `.env.onprem` (one path)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.env_file", value=".env.onprem"),
      ],
      final="""Yes: `env_file` is one path to a `KEY=VALUE` file that ships with the host [docs/providers.md#onprem-on-premises].

Set `env_file: .env.onprem`. `pskit validate -p onprem -s prod`: valid. Ops can now merge the prod lines into that file; keep it out of git."""),

    # ------------------------------------------------------------------ 220  listen_port unknown option
    C(220, provider="onprem", stage="dev", mode="auto", page="Overview", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("metrics-api", """functions:
  scrape:
    handler: app.metrics.scrape
    events:
      - http: GET /metrics
""", extra="    listen_port: 9090\n"), **app("metrics", "scrape")}),
      user="""  WARNING: [provider.options.listen_port] unknown option 'listen_port' is ignored

so it runs on 8080?? I need 9090""",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem options port", docs=[D(P, A, start="    host: 127.0.0.1", end="port: 8080")]),
          S("propose_plan", steps=["Set `provider.options.port` to 9090", "Delete `provider.options.listen_port`", "Validate for onprem"]),
          S("set_config", path="provider.options.port", value=9090),
          S("set_config", path="provider.options.listen_port", value=None),
      ],
      final="""Yes, it would have stayed on 8080: the option is `port`, and unknown options are ignored [docs/providers.md#onprem-on-premises]. Now `port: 9090` and `listen_port` is gone. Validate for onprem: valid, no warnings."""),
]
