"""Category A (docs Q&A and how-to), batch 45: studio-first how-tos. On premises: peeking into a queue, backing up
a one-click service, a handler-module typo (real warning), deploying once to another saved server, local tests of
an on-prem project, adding a pip package, host stats, an unset SSH key variable (real error). AWS: 404 responses,
the deployed URL, JWT without authorizer (real error), SAM Globals, one function's log level. GCP: doctor and the
gcloud CLI, JWT on GCP (real error), secrets, pskit dev with curl. Azure: plan SKU, timer timezone (real
warning), removing a stage from studio. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


PR = "docs/providers.md"
OP = "onprem-on-premises"
ST = "docs/studio.md"
CLI = "docs/cli.md"
EV = "docs/events.md"
CF = "docs/configuration.md"
HD = "docs/handlers.md"
LD = "docs/local-development.md"
SV = "docs/resource-guides/onprem/services.md"

CONVERSATIONS = [
    A(871, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{ST}#project-environment-trigger-resources-and-remove", f"{CLI}#pskit-resources"],
      user="how can i see which messages are waiting in my jobs queue on the onprem host, without taking them out?",
      steps=[S("search_docs", query="see messages in queue onprem",
               docs=[D(PR, OP, start="| `GET /__pskit/queues/<name>` |", end="| `GET /__pskit/queues/<name>` |")]),
             S("search_docs", query="page through queue messages not consumed data",
               docs=[D(ST, "project-environment-trigger-resources-and-remove", start="- **On-prem services**: the create form has a *Security* box", end="**Resources → Data** pages through"),
                     D(CLI, "pskit-resources", start="| `data KEY [--offset N]", end="| `data KEY [--offset N]")])],
      final="""**In studio**
1. **Resources**: open the `jobs` row.
2. **Data** pages through what the queue holds, with previews.

**In the terminal**
```bash
pskit resources data jobs
pskit resources data jobs --offset 20 -n 20 --json
```
Messages are not consumed [docs/cli.md#pskit-resources]. For just the count, `GET /__pskit/queues/jobs` on the host returns `{"depth": n}`."""),

    A(872, provider="onprem", stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{SV}#backups", f"{CLI}#pskit-resources-onprem"],
      user="the postgres i made with one click in studio, how i take backup before upgrade?",
      steps=[S("search_docs", query="backup one-click postgres",
               docs=[D(SV, "backups", end="| MySQL / MariaDB |")])],
      final="""**In studio**
1. **Resources** > *On-prem services*: on the PostgreSQL row press **Backup**.
2. The dump goes to `.pskit/backups/` on this machine, or pick a folder under Backup, Save to folder, Browse….

**In the terminal**
```bash
pskit resources onprem backup db
```
Use your service's key instead of `db`. PostgreSQL gives a `.sql` file; restore it with `psql -U pskit -f file.sql postgres` [docs/resource-guides/onprem/services.md#backups]."""),

    A(873, provider="onprem", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{CF}#functions"],
      user="orders -> On-premises [experimental] stage=dev region=local\n  1 function(s), 0 workflow(s)\n  WARNING: [functions.api.handler] handler module 'app.handler' not found under .\nConfiguration is valid.\n\nit says valid, so ok?",
      steps=[S("search_docs", query="handler module not found warning",
               docs=[D("docs/troubleshooting.md", "configuration", words=120)]),
             S("search_docs", query="handler string package module function",
               docs=[D(CF, "functions", start="| `handler` | string, required | — |", end="| `handler` | string, required | — |"),
                     D(HD, "handler-signatures", words=80)])],
      final="""Not ok: it is only a warning, but the deployed function would fail on every call. `handler: app.handler.hello` means the file `app/handler.py`, and pskit finds no such module. Your file is probably `app/handlers.py`.

**In studio**
**Functions**: click `api`, fix **Handler** in **Basics** to `app.handlers.hello`, **Apply changes**, **Save**.

**In code**
```yaml
functions:
  api:
    handler: app.handlers.hello
```
Then check it really runs: **Test > ▶ Run locally**, or `pskit invoke -f api`."""),

    A(874, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{SV}#deploy-the-functions-to-a-chosen-machine"],
      user="Our dev stage normally deploys to edge1. Once, I want to deploy it to the saved server edge2 for a test, without changing pskit.yml. How?",
      steps=[S("search_docs", query="deploy once to another saved server",
               docs=[D(SV, "deploy-the-functions-to-a-chosen-machine", start="```bash", end="`install` and the rest stay. In the studio, **Deploy → Machine** picks one for that run.", words=200)])],
      final="""**In studio**
1. **Deploy**: pick `edge2` in **Machine**.
2. Press **Deploy**.

**In the terminal**
```bash
pskit deploy --server edge2
```
Only that run goes to `edge2`; `pskit.yml` stays as it is [docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine].

Be aware: the stage remembers its machine, so afterwards logs, triggers and the next `pskit deploy` without `--server` go to `edge2`. Use `--server edge1` to go back, or keep a separate stage per machine [docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine]."""),

    A(875, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=[f"{LD}#on-premises-is-a-deploy-not-pskit-dev", f"{ST}#test-functions"],
      user="my project is onprem. can i try my http function on my laptop quickly without deploy every time?",
      steps=[S("search_docs", query="test locally without deploy onprem",
               docs=[D(LD, "on-premises-is-a-deploy-not-pskit-dev", end="`options.deploy.method` is `local`")]),
             S("search_docs", query="pskit dev local server hot reload",
               docs=[D(LD, "pskit-dev-local-server", words=40),
                     D(LD, "pskit-dev-local-server", start="**Hot reload:**", end="**Hot reload:**")])],
      final="""Yes. `pskit dev` and `pskit invoke` work for an on-prem project too; deploy only when you want the durable host with schedules, queues and workflows [docs/local-development.md#on-premises-is-a-deploy-not-pskit-dev].

**In studio**
1. **Test**: pick the function and its HTTP trigger.
2. Edit the request and press **▶ Run locally**.

**In the terminal**
```bash
pskit dev
```
Then call `http://127.0.0.1:3000/<your path>`. It reloads your `.py` files before each request, so no restart is needed [docs/local-development.md#pskit-dev-local-server]."""),

    A(876, provider="onprem", stage="prod", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{PR}#{OP}", f"{ST}#project-environment-trigger-resources-and-remove"],
      user="i need requests library in my function. server is linux, my pc windows. how add it so it work on server?",
      steps=[S("search_docs", query="add python dependency requirements onprem remote",
               docs=[D(PR, OP, start="- **Dependencies:**", end="- **Dependencies:**")]),
             S("search_docs", query="studio install requirements venv",
               docs=[D(ST, "project-environment-trigger-resources-and-remove", end="  page.")])],
      final="""Add it to `requirements.txt`. For a remote host pskit installs wheels that match `deploy.target_os` and `architecture`, so Windows on your PC is fine [docs/providers.md#onprem-on-premises].

**In studio**
1. **Code**: open `requirements.txt` (or **New file** if there is none) and add a line `requests`. Save it (Ctrl+S).
2. **Setup & credentials** > *Project environment*: install it into `.venv`, so **Run locally** can import it too.
3. **Deploy > Deploy**.

**In code**
```text
requests
```
in `requirements.txt` next to `pskit.yml`, and `import requests` in the handler."""),

    A(877, provider="onprem", stage="prod", mode="ask", page="none", persona="terse_expert",
      sources=[f"{PR}#logs-and-stats"],
      user="onprem host: invocations + errors per function as json, for our grafana. endpoint?",
      steps=[S("search_docs", query="onprem stats invocations errors endpoint",
               docs=[D(PR, "logs-and-stats", start="`GET /__pskit/stats` returns", end="`GET /__pskit/stats` returns")]),
             S("search_docs", query="admin token header pskit endpoints",
               docs=[D(PR, OP, start="| Request | Effect |", end="| `GET /__pskit/stats` |")])],
      final="""`GET /__pskit/stats`: per function `invocations`, `errors`, `avg_duration_ms`, `last_duration_ms`, `last_at`, `last_error`, plus queue depths. Counters reset when the host restarts [docs/providers.md#logs-and-stats].

```bash
curl -H "x-pskit-token: <admin token>" http://fn.internal.example:8080/__pskit/stats
```
The header is needed when the host has an `admin_token`."""),

    A(878, provider="onprem", stage="staging", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/troubleshooting.md#configuration", f"{PR}#{OP}"],
      user="Error: unresolved variables: env:PSKIT_SSH_KEY\n\nworks on my colleague pc, not mine",
      steps=[S("search_docs", query="unresolved variables env",
               docs=[D("docs/troubleshooting.md", "configuration", start="**`unresolved variables: env:FOO`**", end=": Set the variable, or give a default")])],
      final="""`pskit.yml` uses `${env:PSKIT_SSH_KEY}` (the SSH key path for the deploy), and that variable isn't set on your PC. Your colleague has it set. Set it, or give a default [docs/troubleshooting.md#configuration].

**In the terminal**
Set it before validating or deploying:
```bash
export PSKIT_SSH_KEY=~/.ssh/staging.pem
pskit validate
```
On Windows use `setx PSKIT_SSH_KEY C:\\Users\\you\\.ssh\\staging.pem` and open a new terminal.

**In code**
Or give the variable a default after a comma, e.g. `pem: "${env:PSKIT_SSH_KEY, }"`. An empty `pem` means the SSH agent / default key is used [docs/providers.md#onprem-on-premises]."""),

    A(879, provider="aws", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=[f"{HD}#errors"],
      user="when the order id dont exist my api should return 404, not 500. how?",
      steps=[S("search_docs", query="return 404 not found handler",
               docs=[D(HD, "errors", end="| `NotFound` | 404 |")])],
      final="""Raise `NotFound`; pskit turns it into a 404 JSON response [docs/handlers.md#errors].

**In code**
```python
from __future__ import annotations

from py_serverless_kit import NotFound

ORDERS = {"7": {"id": "7", "total": 30}}


def get_order(event, ctx):
    order_id = event.http.path_params["id"]
    if order_id not in ORDERS:
        raise NotFound(f"order {order_id} not found")
    return ORDERS[order_id]
```
Any other exception becomes a 500."""),

    A(880, provider="aws", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=[f"{CLI}#pskit-info"],
      user="deploy finish. where i find the url of my api for call it with curl?",
      steps=[S("search_docs", query="deployed url endpoint",
               docs=[D("docs/getting-started.md", "7-deploy", start="After deploying, pskit prints endpoints", end="pskit info --refresh    # re-read terraform outputs")]),
             S("search_docs", query="pskit info urls functions",
               docs=[D(CLI, "pskit-info")])],
      final="""The deploy output prints the endpoints, and you can show them again any time.

**In studio**
**Deploy > Info** shows what is deployed, with the URLs.

**In the terminal**
```bash
pskit info
curl https://<your api url>/orders
```
`pskit info` shows the deployed functions, triggers and URLs [docs/cli.md#pskit-info]."""),

    A(881, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#http"],
      user="billing -> AWS Lambda [stable] stage=dev region=us-east-1\n  1 function(s), 0 workflow(s)\n  ERROR: [functions.api] jwt auth needs authorizer.issuer and authorizer.audience",
      steps=[S("search_docs", query="jwt authorizer issuer audience",
               docs=[D(EV, "http", start="**Auth support**", end="Example of AWS JWT auth")])],
      final="""`auth: jwt` needs `authorizer.issuer` and `authorizer.audience`; `identity_source` and `scopes` are optional [docs/events.md#http].

**In code**
```yaml
functions:
  api:
    handler: app.handlers.api
    events:
      - http:
          path: /invoices
          method: GET
          auth: jwt
          authorizer:
            issuer: https://auth.example.com/
            audience: [billing-api]
```
Use your identity provider's issuer URL and the audience your tokens carry. `examples/02-rest-api` has a full example."""),

    A(882, provider="aws", stage="dev", mode="ask", page="Overview", persona="aws_migrator",
      sources=[f"{CF}#provider"],
      user="In SAM we had Globals: Function: Timeout: 10, MemorySize: 512. Where does that go in pskit?",
      steps=[S("search_docs", query="default memory timeout all functions provider",
               docs=[D(CF, "provider", start="| Key | Type | Default | Notes |", end="| `timeout` |")])],
      final="""On `provider`; every function inherits it unless it sets its own value [docs/configuration.md#provider].

**In code**
```yaml
provider:
  name: aws
  memory: 512
  timeout: 10
```

**In studio**
**Overview & provider** > *Defaults for every function*: **Memory (MB)** `512`, **Timeout (s)** `10`, then **Save**."""),

    A(883, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{HD}#environment-variables"],
      user="i want debug logs only for my checkout function, not all functions. possible?",
      steps=[S("search_docs", query="log level one function debug",
               docs=[D(HD, "environment-variables", start="Runtime switches you can set:", end="| `PSKIT_LOG_LEVEL` / `LOG_LEVEL` |")])],
      final="""Yes: set `PSKIT_LOG_LEVEL` in that function's environment; the default is `INFO` [docs/handlers.md#environment-variables].

**In studio**
1. **Functions**: click `checkout`, go to **Environment & permissions**.
2. *Logging* > **Log level**: `DEBUG`.
3. **Apply changes**, **Save**, **Deploy > Deploy**.

**In code**
```yaml
functions:
  checkout:
    handler: app.handlers.checkout
    environment:
      PSKIT_LOG_LEVEL: DEBUG
```
Then `ctx.logger.debug(...)` lines show up for `checkout` only."""),

    A(884, provider="gcp", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=[f"{CLI}#pskit-doctor"],
      user="setup page has a red line for gcloud. do i really need it to deploy?",
      steps=[S("search_docs", query="setup checks gcloud missing",
               docs=[D(ST, "setup-logs-and-provider-differences", end="Each problem shows the download link and the steps for Windows, macOS or Linux. You can also:")]),
             S("search_docs", query="doctor missing cloud cli warning credentials",
               docs=[D(CLI, "pskit-doctor", start="`✓` ok, `✗` missing (exit code 1)", end="needs credentials, not the CLI.")])],
      final="""A missing cloud CLI is only a warning: Terraform needs credentials, not the CLI [docs/cli.md#pskit-doctor]. But gcloud is the easy way to get those credentials, so install it unless you use a key file.

**In studio**
1. **Setup & credentials**: the gcloud row shows the download link and the steps for your OS.
2. After installing, press **Sign in (gcloud ADC)** (application-default login).
3. The checks run again.

**In the terminal**
```bash
pskit doctor -p gcp
```"""),

    A(885, provider="gcp", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#http", f"{PR}#gcp-google-cloud-functions-2nd-gen"],
      user="catalog -> Google Cloud Functions [stable] stage=dev region=europe-west1\n  1 function(s), 0 workflow(s)\n  ERROR: [functions.api] http auth 'jwt' is not supported on GCP; use none or iam",
      steps=[S("search_docs", query="gcp auth jwt alternative",
               docs=[D(EV, "http", start="**Auth support**", end="| `key` |")])],
      final="""On GCP pskit supports `auth: none` or `auth: iam` only; `jwt` is AWS-only [docs/events.md#http].

Options:
1. `auth: iam`: no public invoker binding, so only callers with IAM permission on the function can reach it.
2. `auth: none` and check the JWT in the handler yourself (read `event.http.headers.get("authorization")`).
3. Keep `jwt` for AWS and override the trigger on GCP:
```yaml
providers:
  gcp:
    functions:
      api: {events: [{http: {path: /items, method: GET, auth: iam}}]}
```"""),

    A(886, provider="gcp", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{HD}#get_secret-secrets-on-every-provider"],
      user="my handler need api key of stripe. where i put it safe on gcp? not in pskit.yml right?",
      steps=[S("search_docs", query="secret api key handler",
               docs=[D(HD, "get_secret-secrets-on-every-provider")])],
      final="""Right, never the literal key in `pskit.yml`. Read it with `get_secret()`; the store comes from environment variables, so the code doesn't change between clouds [docs/handlers.md#get_secret-secrets-on-every-provider].

**In code**
```python
from __future__ import annotations

from py_serverless_kit import get_secret


def charge(event, ctx):
    stripe_key = get_secret("stripe-api-key")
    return {"ok": bool(stripe_key)}
```
With the default `env` store it reads `PSKIT_SECRET_STRIPE_API_KEY`, then `STRIPE_API_KEY`. Pass it from your shell when you deploy:
```yaml
functions:
  charge:
    handler: app.handlers.charge
    environment:
      STRIPE_API_KEY: ${env:STRIPE_API_KEY}
```"""),

    A(887, provider="gcp", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=[f"{LD}#pskit-dev-local-server"],
      user="I want to run the GCP project's HTTP functions on my machine and hit them with curl and Postman while I code. No deploy. What's the command and which URL?",
      steps=[S("search_docs", query="local http server curl",
               docs=[D(LD, "pskit-dev-local-server", end="| `GET /__pskit/` | the dashboard for this project (local view) |")])],
      final="""**In the terminal**
```bash
pskit dev
```
It serves on `http://127.0.0.1:3000` and prints every route on startup, e.g. `GET http://127.0.0.1:3000/hello -> hello`. Unknown paths return 404 with the route list [docs/local-development.md#pskit-dev-local-server].

```bash
curl http://127.0.0.1:3000/hello
pskit dev --port 8080 --env-file .env.local
```
No GCP credentials are needed; handlers run through the same dispatcher as in the cloud."""),

    A(888, provider="azure", stage="prod", mode="ask", page="Overview", persona="beginner",
      sources=[f"{PR}#azure-azure-functions"],
      user="my boss want the azure functions on premium plan EP1 instead of consumption. where i change?",
      steps=[S("search_docs", query="azure plan sku premium",
               docs=[D(PR, "azure-azure-functions", start="- **Credentials:**", end="One **Linux Consumption Function App**", words=300)])],
      final="""It is `options.plan_sku`; the default is `Y1` (Consumption) [docs/providers.md#azure-azure-functions].

**In studio**
1. **Overview & provider** > *Azure Functions options* > **Plan SKU**: `EP1`.
2. **Save**, then **Deploy > Deploy**.

**In code**
```yaml
provider:
  name: azure
  options:
    plan_sku: EP1
```"""),

    A(889, provider="azure", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{PR}#azure-azure-functions", f"{EV}#schedule"],
      user="  WARNING: [functions.report] Linux Consumption timers run in UTC; timezone is ignored\n\nreport must run 7:00 berlin time",
      steps=[S("search_docs", query="azure timer timezone ignored utc",
               docs=[D(PR, "azure-azure-functions", start="**Limits:**", end="**Limits:**")])],
      final="""Azure timers ignore `timezone` and run in UTC [docs/providers.md#azure-azure-functions]. Write the time in UTC instead: 07:00 Berlin is 06:00 UTC in winter and 05:00 UTC in summer.

**In code**
```yaml
functions:
  report:
    handler: app.handlers.report
    events:
      - schedule: "0 6 * * *"
```
Change it when daylight saving time starts and ends, or run it at both hours and let the handler skip the wrong one."""),

    A(890, provider="azure", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=[f"{ST}#what-you-can-do", f"{ST}#project-environment-trigger-resources-and-remove"],
      user="i finish testing. how remove my azure dev deploy from studio",
      steps=[S("search_docs", query="studio remove deployment",
               docs=[D(ST, "what-you-can-do", start="| **Deploy** |", end="| **Deploy** |"),
                     D(ST, "project-environment-trigger-resources-and-remove", start="- **Deploy → Remove** has a switch", end="  `pskit remove --keep-resources`: functions and triggers are destroyed and the data resources stay in the cloud.")])],
      final="""**In studio**
1. Check the top bar: provider `azure`, stage `dev`.
2. **Deploy > Remove**.
3. Decide on *Remove also deletes buckets, queues and topics*: on deletes them with their data, off keeps them in Azure.
4. Type the confirmation studio asks for and start it. The live log shows the progress."""),
]
