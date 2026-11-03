"""Category A (docs Q&A and how-to), batch 10: the onprem provider itself (deploy methods, Python / Node.js on the
server, limits, the stage's machine, admin API, logs and stats). Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


P = "docs/providers.md"
ON = "onprem-on-premises"
LG = "logs-and-stats"

CONVERSATIONS = [
    A(181, provider="onprem", stage="prod", mode="ask", page="Overview", persona="informal_non_native",
      sources=[f"{P}#{ON}"],
      user="our linux server have no python and we not allowed install packages. pskit can still run function there?",
      steps=[S("search_docs", query="server has no python bundle portable",
               docs=[D(P, ON, start="When the server has **no Python**", end="contain test paths longer than `MAX_PATH`).")])],
      final="""Yes. Two ways [docs/providers.md#onprem-on-premises]:
- `python: bundle`: a portable CPython (python-build-standalone) is fetched at apply and copied with the app. Nothing is installed on the server.
- `method: docker`: the image is `FROM python:<minor>-slim` (Docker is needed on the server then).

**In code**
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    port: 8080
    deploy:
      method: ssh
      host: 192.0.2.10
      user: pskit
      path: /opt/pskit/orders
      python: bundle
```

**In studio**
1. Open **Overview & provider** and choose the *ssh* deploy method.
2. Fill in the host and user, set Python to *bundle*, and click **Save**.

`python: bundle` needs network on the first apply, unless a cached archive is present."""),

    A(182, provider="onprem", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{P}#{ON}"],
      user="Our build network is air-gapped. With python: bundle pskit downloads CPython at apply. Can we use our internal mirror or a copy we already have instead?",
      steps=[S("search_docs", query="air-gapped python bundle mirror python_home python_url",
               docs=[D(P, ON, start="When the server has **no Python**", end="(internal mirror of an `install_only` tarball).")]),
             S("search_docs", query="python bundle network first apply cache",
               docs=[D(P, ON, start="**Limits:**", end="is present.", words=300)])],
      final="""Yes, two options for air-gapped setups [docs/providers.md#onprem-on-premises]:
- `python_home`: copy a CPython tree you already have.
- `python_url` + `python_sha256`: your internal mirror of an `install_only` tarball, checked after download.

**In code**
```yaml
provider:
  name: onprem
  options:
    deploy:
      method: ssh
      host: 192.0.2.10
      python: bundle
      python_url: https://mirror.example.com/cpython-3.12-x86_64-linux-install_only.tar.gz
      python_sha256: <sha256 of that archive>
```
Use your mirror's real file name and checksum.

A cached archive under `~/.cache/pskit/python-standalone` also avoids the download."""),

    A(183, provider="onprem", stage="prod", mode="auto", page="YAML", persona="terse_expert",
      sources=[f"{P}#{ON}"],
      user="yaml only: ssh deploy to 192.0.2.40 as user deploy, systemd unit, key from env, /opt/pskit/api",
      steps=[S("search_docs", query="ssh deploy systemd sudo pem",
               docs=[D(P, ON, start="# SSH + portable CPython + systemd", end="sudo: true                      # needed to write /etc/systemd/system")])],
      final="""**In code**
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    port: 8080
    deploy:
      method: ssh
      host: 192.0.2.40
      user: deploy
      pem: ${env:PSKIT_SSH_KEY}
      known_hosts: accept-new
      path: /opt/pskit/api
      install: systemd
      sudo: true
```
`sudo: true` is needed to write `/etc/systemd/system`, unless the user is root. It's non-interactive (`sudo -n`), so the sudoers rule must not ask for a password [docs/providers.md#onprem-on-premises]."""),

    A(184, provider="onprem", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=[f"{P}#{ON}"],
      user="i want deploy with docker to my server. what do i need on my laptop and on the server?",
      steps=[S("search_docs", query="docker deploy method server laptop needs",
               docs=[D(P, ON, start="**Deploy targets** (`options.deploy`)", end="| Docker CLI, OpenSSH. Optional `.pem` |")])],
      final="""[docs/providers.md#onprem-on-premises]
- **Laptop**: the Docker CLI (the image is built there) and OpenSSH.
- **Server**: SSH. Docker is installed at deploy when it's missing (`install_docker: true` is the default). The SSH user needs passwordless `sudo` when Docker must be installed or the user can't talk to the daemon.

**In code**
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    deploy:
      method: docker
      host: 192.0.2.10
      user: pskit
      pem: ${env:PSKIT_SSH_KEY}
      image: pskit/orders:dev
      restart: unless-stopped
```

**In studio**
1. **Setup & credentials** checks ssh, scp, Docker and the key file. Click **Test SSH connection**.
2. **Overview & provider**: choose the *docker* deploy method and fill in the host.
3. **Deploy**: click **Deploy**. It waits until the container answers `/__pskit/health`."""),

    A(185, provider="onprem", stage="prod", mode="ask", page="Overview", persona="terse_expert",
      sources=[f"{P}#{ON}"],
      user="docker deploy must NOT install docker on servers that lack it. option?",
      steps=[S("search_docs", query="install_docker false refuse server without docker",
               docs=[D(P, ON, start="Set `install_docker: false`", end="is reported and left unchanged.")])],
      final="""Set `install_docker: false`. A server without Docker is then refused instead of getting it installed [docs/providers.md#onprem-on-premises].

```yaml
provider:
  name: onprem
  options:
    deploy:
      method: docker
      host: 192.0.2.10
      install_docker: false
```"""),

    A(186, provider="onprem", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{P}#{ON}"],
      user="On AWS a Lambda is killed at its timeout. We set timeout: 30 on an on-prem function that sometimes hangs on an external API. Will the host stop it after 30 seconds?",
      steps=[S("search_docs", query="on-prem timeout handler not killed remaining time",
               docs=[D(P, ON, start="**Limits:**", end="`ctx.remaining_time_ms()` still counts down.")])],
      final="""No. The on-prem host doesn't kill a handler at `timeout`. `ctx.remaining_time_ms()` still counts down [docs/providers.md#onprem-on-premises].

So put the limit in your code: give the external call its own timeout, and check the remaining time.

**In code**
```python
from __future__ import annotations

import urllib.request


def sync(event, ctx):
    seconds = max(1, ctx.remaining_time_ms() // 1000 - 2)
    with urllib.request.urlopen("https://api.example.com/orders", timeout=seconds) as resp:
        return {"status": resp.status}
```
Workflows are different: they run in the host's embedded engine and aren't cut off by a function timeout."""),

    A(187, provider="onprem", stage="prod", mode="ask", page="Overview", persona="aws_migrator",
      sources=[f"{P}#{ON}"],
      user="Our pskit.yml has provider.state with an s3 backend from the AWS days. Now we deploy on-prem and get a warning about it. What should state look like for onprem?",
      steps=[S("search_docs", query="onprem state backend s3 warning",
               docs=[D(P, ON, start="**Limits:**", end="to keep state on this machine.")])],
      final="""A state backend of `s3`, `gcs` or `azurerm` warns on-prem. Set `provider.state.backend` empty to keep the state on this machine [docs/providers.md#onprem-on-premises]. Examples 11 and 15 do this under `providers.onprem`, so the AWS settings stay for AWS.

**In code**
```yaml
provider:
  name: aws
  state:
    backend: s3
    config: {bucket: my-tf-state, key: shop.tfstate, region: eu-west-1}
providers:
  onprem:
    region: local
    state:
      backend: null
```
`backend: null` is how example 11 empties it. Validate and deploy with `-p onprem` to use the override."""),

    A(188, provider="onprem", stage="dev", mode="ask", page="Overview", persona="aws_migrator",
      sources=[f"{P}#{ON}"],
      user="we have an aws_cloudwatch_metric_alarm under terraform.extra. if I deploy the same config with -p onprem, does it break?",
      steps=[S("search_docs", query="terraform.extra cloud resource onprem omitted",
               docs=[D(P, ON, start="**Limits:**", end="is omitted with a warning.")])],
      final="""No. On-prem, a `terraform.extra` resource from another cloud (`aws_*`, `google_*`, `azurerm_*` and the other cloud prefixes) is left out with a warning [docs/providers.md#onprem-on-premises]. The deploy goes on without the alarm.

```bash
pskit validate -p onprem
```
shows the warning. For alerts on premises, look at the host's logs and stats instead (`pskit logs`, `/__pskit/stats`)."""),

    A(189, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{P}#{ON}"],
      user="last week i deployed staging with --server app-2. today i just typed pskit deploy. where did it go??",
      steps=[S("search_docs", query="stage remembers its machine deploy without server",
               docs=[D(P, ON, start="**The stage remembers its machine.**", end="`pskit deploy` prints `deployed on: <server> (<host>)`.")])],
      final="""To app-2 again. A successful deploy writes `.pskit/onprem-staging/onprem_deployed.json`, and the next `pskit deploy` without `--server` goes to the same saved server, unless `server`, `host` or `method` is set under `deploy:` in pskit.yml [docs/providers.md#onprem-on-premises]. The deploy prints `deployed on: <server> (<host>)`.

`pskit logs`, `pskit trigger` and the studio's Test and Logs pages also talk to that host.

**In the terminal**
```bash
pskit deploy -s staging --server local
pskit deploy -s staging --server app-1
```
The first deploys on this machine, the second points a single run at another saved server.

**In studio**
Open **Deploy** and pick the *Machine* before you click **Deploy**."""),

    A(190, provider="onprem", stage="prod", mode="ask", page="Logs", persona="informal_non_native",
      sources=[f"{P}#{ON}"],
      user="port 8080 of server is blocked from my pc by company firewall. pskit logs and test still work?",
      steps=[S("search_docs", query="port closed to this machine ssh control call",
               docs=[D(P, ON, start="**Ports closed to this machine.**", end="or use `pskit client tunnel`.")])],
      final="""Yes. When the host's port can't be opened from your PC, pskit sends the control calls (logs, triggers, uploads, HTTP tests) over the deploy's SSH login to `127.0.0.1:<port>` on the server. The admin token goes on stdin, not on a command line [docs/providers.md#onprem-on-premises].

Other machines that call your functions still need the port open (`options.host: 0.0.0.0` plus the firewall rule). For your own PC you can also use a tunnel:
```bash
pskit client tunnel
```"""),

    A(191, provider="onprem", stage="prod", mode="auto", page="Logs", persona="terse_expert",
      sources=[f"{P}#{LG}"],
      user="/__pskit/stats fields? reset on restart?",
      steps=[S("search_docs", query="pskit stats endpoint fields",
               docs=[D(P, LG, start="`GET /__pskit/stats` returns")])],
      final="""`GET /__pskit/stats` returns `started_at`, `uptime_s`, `functions` (per name: `invocations`, `errors`, `avg_duration_ms`, `last_duration_ms`, `last_at`, `last_error`) and `queues` (name: depth). Yes, the counters reset when the host restarts [docs/providers.md#logs-and-stats].

```bash
curl -H "x-pskit-token: ${PSKIT_ADMIN_TOKEN}" http://127.0.0.1:8080/__pskit/stats
```
The header is needed only when `admin_token` is set."""),

    A(192, provider="onprem", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=[f"{P}#{LG}"],
      user="We want our own log shipper to poll the on-prem host's log API and never miss or duplicate entries. How does paging work?",
      steps=[S("search_docs", query="logs api since next gap poll",
               docs=[D(P, LG, start="`GET /__pskit/logs` (admin token when set):", end="| `q` | case-insensitive text search in the message |"),
                     D(P, LG, start="`next` advances past filtered-out entries", end="means older matching entries exist.")])],
      final="""Poll with `since` [docs/providers.md#logs-and-stats]:
1. Start with `GET /__pskit/logs?since=0&limit=2000` (max 2000).
2. Store the returned `next`, and poll again with `since=<next>`. Entries come oldest first.
3. `next` advances past filtered-out entries, so polling with filters (`level`, `function`, `source`, `q`) doesn't stall.
4. If a response has `gap: true`, older entries were dropped from memory before you read them. Raise `options.log_buffer` (default 5000) or poll more often.

```bash
curl -H "x-pskit-token: ${PSKIT_ADMIN_TOKEN}" "http://127.0.0.1:8080/__pskit/logs?since=42&limit=2000"
```
Every entry is also appended to `<data_dir>/logs/host.jsonl`, which your shipper could read on the server instead."""),

    A(193, provider="onprem", stage="dev", mode="ask", page="Logs", persona="terse_expert",
      sources=[f"{P}#{LG}", f"{P}#{ON}"],
      user="debug-level logs from ctx.logger don't appear in pskit logs on-prem. how to lower the capture level?",
      steps=[S("search_docs", query="on-prem log level capture debug",
               docs=[D(P, LG, end="host notes (source `host`)")]),
             S("search_docs", query="options log_level capture_output",
               docs=[D(P, ON, start="    log_level: INFO", end="    capture_output: true")])],
      final="""The host captures `INFO` and above by default [docs/providers.md#logs-and-stats]. Lower it with `options.log_level`, or set `PSKIT_LOG_LEVEL` in the environment that starts the host process [docs/providers.md#onprem-on-premises].

**In code**
```yaml
provider:
  name: onprem
  options:
    log_level: DEBUG
```

**In the terminal**
```bash
pskit deploy
pskit logs --level debug --function worker
```"""),

    A(194, provider="onprem", stage="prod", mode="ask", page="Logs", persona="terse_expert",
      sources=[f"{P}#{LG}"],
      user="does host.jsonl grow forever on the server?",
      steps=[S("search_docs", query="host.jsonl rotate size",
               docs=[D(P, LG, start="Entries written during an invocation", end="Messages longer than 16 KiB are truncated.")])],
      final="""No. `<data_dir>/logs/host.jsonl` rotates at 10 MiB and keeps three old files. The history is reloaded on restart, and messages longer than 16 KiB are truncated [docs/providers.md#logs-and-stats].

To clear entries:
```bash
pskit logs --delete worker --yes
pskit logs --delete-all --yes
```"""),

    A(195, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=[f"{P}#{ON}"],
      user="a program not written in python must add messages to my on-prem queue. is there a simple http way?",
      steps=[S("search_docs", query="publish to on-prem queue from outside http",
               docs=[D(P, ON, start="Publish from outside the process:", end="| `POST /__pskit/invoke/<function>` | in-process invoke |")])],
      final="""Yes. The host has an HTTP admin API [docs/providers.md#onprem-on-premises]:
- `POST /__pskit/queues/<name>`: enqueue one JSON value, a list, or `{"messages": [...]}`. The answer is `202 {"queued": [ids]}`.
- `GET /__pskit/queues/<name>`: `{"depth": n}`.

```bash
curl -X POST -H "x-pskit-token: ${PSKIT_ADMIN_TOKEN}" -d '{"order_id": 7}' http://192.0.2.10:8080/__pskit/queues/jobs
```
Any language with an HTTP client can do this. Send the `x-pskit-token` header when the host sets `admin_token`, and bind the host on `0.0.0.0` so other machines can reach it."""),

    A(196, provider="onprem", stage="prod", mode="ask", page="Overview", persona="terse_expert",
      sources=[f"{P}#{ON}"],
      user="protect /__pskit/* admin endpoints on-prem. which header, and is health covered?",
      steps=[S("search_docs", query="admin_token header pskit endpoints health",
               docs=[D(P, ON, start="    admin_token:", end="    admin_token:")])],
      final="""Set `admin_token`. Callers send it in the `x-pskit-token` header on `/__pskit/*`, except health, which needs no token [docs/providers.md#onprem-on-premises].

```yaml
provider:
  name: onprem
  options:
    admin_token: ${env:PSKIT_ADMIN_TOKEN}
```
Keep the token in an environment variable, never as a literal in pskit.yml."""),

    A(197, provider="onprem", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{P}#{ON}"],
      user="Our service is Node.js 20 (runtime: nodejs20) and goes to a server over SSH that has no Node installed. Can pskit ship Node with the app, and what still runs in Python?",
      steps=[S("search_docs", query="onprem node.js bundle ssh server",
               docs=[D(P, ON, start="**Node.js / TypeScript services**", end="Where `node` comes from:", words=330),
                     D(P, ON, start="  node: bundle            # auto", end="host_python: python3.12"),
                     D(P, ON, start="`node: system` (the default)", end="refuses to start without")])],
      final="""Yes. Set `node: bundle`: pskit downloads the official nodejs.org build for `target_os`/`target_arch` and ships only its `node` binary [docs/providers.md#onprem-on-premises].

**In code**
```yaml
provider:
  name: onprem
  runtime: nodejs20
  options:
    deploy:
      method: ssh
      host: 192.0.2.10
      node: bundle
      python: bundle
```

What stays Python: the **host** process (HTTP, schedules, queues, storage, topics, workflow executions and logs). Each function runs in its own long-lived `node pskit_runtime/worker.js` process, started on its first invocation. So the server also needs a Python for the host: `python: bundle` (as above) downloads `host_python` (default python3.12).

With `node: system` (the default), `pskit-run.sh` refuses to start without `node` on PATH."""),

    A(198, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{P}#{ON}"],
      user="if i run pskit remove on my onprem stage, are my queue messages and files deleted too?",
      steps=[S("search_docs", query="pskit remove onprem data_dir",
               docs=[D(P, ON, start="`pskit deploy` writes the bundle", end="does not delete `data_dir`.")])],
      final="""No. `pskit remove` stops the process (or the container or systemd unit) and doesn't delete `data_dir`, where the built-in queues and buckets live [docs/providers.md#onprem-on-premises].

**In the terminal**
```bash
pskit remove -s dev
```

**In studio**
Open **Deploy** and click **Remove**. Studio asks you to type a confirmation first.

To empty a built-in queue or bucket while the host runs, use `pskit resources clear <key> --yes` before you remove."""),

    A(199, provider="onprem", stage="dev", mode="ask", page="Setup", persona="pasted_error",
      sources=[f"{P}#{ON}"],
      user="WARNING: UNPROTECTED PRIVATE KEY FILE!\nPermissions for 'C:\\\\Users\\\\me\\\\.ssh\\\\app.pem' are too open.\n\npskit deploy on windows",
      steps=[S("search_docs", query="windows openssh key unprotected icacls",
               docs=[D(P, ON, start="SSH login options, for `ssh`", end="restrict it with `icacls`.")])],
      final="""Windows OpenSSH refuses a key file that other users can read. Restrict it with `icacls` [docs/providers.md#onprem-on-premises]:

```powershell
icacls C:\\Users\\me\\.ssh\\app.pem /inheritance:r
icacls C:\\Users\\me\\.ssh\\app.pem /grant:r "$($env:USERNAME):(R)"
```
Then run the deploy again:
```bash
pskit deploy -s dev
```
In the studio, **Setup & credentials > Test SSH connection** checks the login without deploying."""),

    A(200, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{P}#{ON}"],
      user="sudo: a terminal is required to read the password; either use the -S option to read from standard input or configure an askpass helper\n\n(deploy with install: systemd)",
      steps=[S("search_docs", query="systemd sudo non-interactive password",
               docs=[D(P, ON, start="**Limits:**", end="so the sudoers rule must not ask for a password.", words=320)])],
      final="""pskit's `sudo` is non-interactive (`sudo -n`), so the SSH user needs passwordless sudo. systemd units are written to `/etc/systemd/system`, which needs it [docs/providers.md#onprem-on-premises].

Fix one of these:
1. On the server, give the deploy user a sudoers rule without a password (ask your admin; for example a file in `/etc/sudoers.d/` with `NOPASSWD`).
2. Or deploy as root.
3. Or skip systemd and run a plain process, which doesn't need sudo:
```yaml
provider:
  name: onprem
  options:
    deploy:
      method: ssh
      host: 192.0.2.10
      path: /home/pskit/orders
      install: process
      sudo: false
```
Use a `path` the user can write to."""),
]
