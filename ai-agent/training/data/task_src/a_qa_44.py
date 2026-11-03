"""Category A (docs Q&A and how-to), batch 44: studio-first how-tos. On premises: putting a project on a load
balancer, sticky sessions, the path prefix, lb logs, cluster-full alerts, firewall rules, Mailpit for test mail,
database resources (real validate error). AWS: arm64, reserved concurrency from serverless.yml, batch_size limit
(real error), tags. GCP: memory only on GCP, CORS typo (real error), a two-step workflow in studio, a root
main.py. Azure: function keys in studio, blob deletes (real error), app-wide environment (real warning), Logic
Apps engine. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


PR = "docs/providers.md"
LB = "docs/load-balancers.md"
LBC = "create-one-and-put-projects-on-it"
ST = "docs/studio.md"
CF = "docs/configuration.md"
EV = "docs/events.md"
SV = "docs/resource-guides/onprem/services.md"
AZ = "azure-azure-functions"
GC = "gcp-google-cloud-functions-2nd-gen"

CONVERSATIONS = [
    A(851, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="beginner",
      sources=[f"{LB}#{LBC}", f"{LB}#notes"],
      user="we already have a load balancer called edge. how do i put my project on it, in studio?",
      steps=[S("search_docs", query="studio load balancer add project",
               docs=[D(LB, "the-six-algorithms", end="animation of each.")]),
             S("search_docs", query="project balancer option route host advertise",
               docs=[D(LB, LBC, start="A project names it in `pskit.yml`", end="sent in `X-Forwarded-Prefix: /shop`. `/shop` redirects to `/shop/`."),
                     D(LB, "notes", start="* The load balancer server must reach each backend's port", end="be reached: set `host: 0.0.0.0` and `advertise`.")])],
      final="""**In studio**
1. **Overview & provider** > *On-premises options*: set **Bind address** to `0.0.0.0` and **Advertised URL** to the address the load balancer calls, e.g. `http://192.0.2.5:8080`. A host on `127.0.0.1` can't be reached by it [docs/load-balancers.md#notes].
2. **Load balancers**: open `edge` and switch on *Put this project on edge*.
3. Optional: a **Path** (empty means `/<service>/`) and an **Algorithm for this route**.
4. **Save**, then **Deploy > Deploy**. The route is added on deploy and dropped on remove [docs/load-balancers.md#create-one-and-put-projects-on-it]."""),

    A(852, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="informal_non_native",
      sources=[f"{LB}#the-six-algorithms", f"{LB}#{LBC}"],
      user="our app keep login session in memory of the server, with load balancer users get logout randomly. which algorithm i choose?",
      steps=[S("search_docs", query="load balancer algorithm sessions in memory",
               docs=[D(LB, "the-six-algorithms", start="| Algorithm | Kind |", end="| `ip_hash` |")])],
      final="""Use `sticky_round_robin`: a user's first request picks a server and a cookie keeps the session there. The catch: busy users make it uneven, and sessions move when a server joins or leaves [docs/load-balancers.md#the-six-algorithms].

**In studio**
**Load balancers**: on your load balancer, set *Algorithm for this route* to sticky round robin, **Save**, **Deploy > Deploy**.

**In code**
```yaml
provider:
  name: onprem
  options:
    balancer: {name: edge, algorithm: sticky_round_robin}
```
For logins that survive any server change, keep sessions in a shared store such as a Redis cache instead."""),

    A(853, provider="onprem", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=[f"{LB}#{LBC}", "docs/handlers.md#httprequest"],
      user="users call http://lb1/shop/orders but in my handler event.http.path is only /orders. is that a bug?",
      steps=[S("search_docs", query="load balancer path prefix removed",
               docs=[D(LB, LBC, start="The path prefix is removed before the request reaches your functions", end="sent in `X-Forwarded-Prefix: /shop`. `/shop` redirects to `/shop/`.")])],
      final="""No, that is on purpose. The load balancer removes the path prefix before the request reaches your functions, so `/shop/orders` arrives as `/orders`, and it sends the prefix in `X-Forwarded-Prefix: /shop` [docs/load-balancers.md#create-one-and-put-projects-on-it]. Your routes stay the same with or without the load balancer.

**In code**
When you build links back to the user, add the prefix:
```python
from __future__ import annotations


def orders(event, ctx):
    prefix = event.http.headers.get("x-forwarded-prefix", "")
    return {"next": prefix + "/orders?page=2"}
```"""),

    A(854, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="terse_expert",
      sources=[f"{LB}#commands"],
      user="lb edge: which backend served each request? need the last 500",
      steps=[S("search_docs", query="load balancer logs upstream server answered",
               docs=[D(LB, "commands", start="pskit lb logs edge -n 200", end="pskit lb logs edge -n 200")])],
      final="""**In the terminal**
```bash
pskit lb logs edge -n 500
```
One line per request; `upstream=` is the server that answered [docs/load-balancers.md#commands]."""),

    A(855, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="detailed_spec",
      sources=["docs/cluster.md#alert-devops-optional"],
      user="When our prod cluster runs out of capacity we want a Slack message, at most every hour, and it should also be checked when nobody has studio open. How do we set that up?",
      steps=[S("search_docs", query="cluster full alert webhook slack",
               docs=[D("docs/cluster.md", "alert-devops-optional", words=50)]),
             S("search_docs", query="who checks cluster capacity watch cron",
               docs=[D("docs/cluster.md", "alert-devops-optional", start="**Who checks?**", end="`pskit cluster check prod` from cron.")])],
      final="""**In the terminal**
```bash
pskit cluster alerts prod --webhook https://hooks.slack.com/services/... --cooldown 60
pskit cluster alerts prod --test
pskit cluster watch prod --interval 60
```
Run `watch` around the clock on an always-on machine (a systemd unit, `tmux`, ...), or run `pskit cluster check prod` from cron instead; checks only run where pskit runs [docs/cluster.md#alert-devops-optional].

**In studio**
1. **Scaling cluster**: open `prod`, section *When every server is full*.
2. Fill **Webhook (optional)** and set **Cooldown (minutes)** to `60`; test it with the test button.
3. *Watch while the studio runs* checks only while studio is open, so keep the `watch` command above for the rest of the time.

Treat the webhook URL as a secret."""),

    A(856, provider="onprem", stage="prod", mode="ask", page="Network map", persona="informal_non_native",
      sources=["docs/onprem-network.md#network-and-firewall-rules-on-premises"],
      user="we have 3 servers + lb. i dont know which ports open between them. pskit can tell me?",
      steps=[S("search_docs", query="which ports to open servers firewall",
               docs=[D("docs/onprem-network.md", "network-and-firewall-rules-on-premises", end="cluster and load balancer pages) and in each job's output:")])],
      final="""Yes, you don't have to work it out by hand [docs/onprem-network.md#network-and-firewall-rules-on-premises].

**In the terminal**
```bash
pskit firewall
pskit firewall --server edge2
```
It lists every rule the project needs now, per server, with who connects and why, and `ufw` commands.

**In studio**
1. **Network map** shows the machines and the connections between them.
2. **Deploy** (and the cluster and load balancer pages) has a *Firewall* panel with the same rules.

`[REQUIRED]` rules must be open; optional ones can stay closed because pskit falls back to an SSH tunnel."""),

    A(857, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{SV}#one-click-services-for-on-premises-functions", f"{SV}#in-the-studio"],
      user="my function sends emails. how can i test it without sending real mails to customers?",
      steps=[S("search_docs", query="test email locally smtp",
               docs=[D("docs/smtp/README.md", "e-mail-triggers-smtp-on-premises", words=80)]),
             S("search_docs", query="mailpit one-click service",
               docs=[D(SV, "one-click-services-for-on-premises-functions", start="| Service | Use as |", end="| Redis | queue"),
                     D(SV, "one-click-services-for-on-premises-functions", start="| Mailpit (SMTP) |", end="| Mailpit (SMTP) |")])],
      final="""Start a Mailpit service: an SMTP server for development and tests on port 1025 that keeps every mail for inspection in its Mailbox web UI on port 8025 [docs/resource-guides/onprem/services.md#one-click-services-for-on-premises-functions].

**In studio**
1. **Resources > + On-prem service**: pick *Mailpit (SMTP)* and *This machine*, then **Create**.
2. Review the added resource (its connection values) and **Save**.
3. Run the function and open the Mailbox (port 8025) to read the mail.

**In code**
Point your SMTP code at it while testing, e.g. with `smtplib`:
```python
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def notify(event, ctx):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = "shop@example.com", "customer@example.com", "Your order"
    msg.set_content("Thanks!")
    with smtplib.SMTP(os.environ.get("SMTP_HOST", "127.0.0.1"), int(os.environ.get("SMTP_PORT", "1025"))) as smtp:
        smtp.send_message(msg)
    return {"sent": True}
```
Mailpit runs without authentication, so keep it on test machines only."""),

    A(858, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#fields", "docs/resources.md#resources-storage-queues-topics-databases-any-service"],
      user="Error: pskit.yml is invalid:\n  - resources.db: Value error, pskit does not create `database` resources; set `external: true` and describe it in `connection`\n\nhow do i make pskit create the postgres then",
      steps=[S("search_docs", query="database resource external connection",
               docs=[D("docs/resources.md", "fields", start="`database`, `cache` and `custom` must be `external: true`.", end="`database`, `cache` and `custom` must be `external: true`.")]),
             S("search_docs", query="one-click postgres on premises service",
               docs=[D(SV, "in-the-studio", end="5. **Create**.")])],
      final="""`resources:` never creates a database; it only passes the connection to your functions [docs/resources.md#fields]. On premises, studio can start PostgreSQL for you and add the resource.

**In studio**
1. **Resources > + On-prem service**: pick *PostgreSQL*, *This machine* or an SSH server, tick the functions.
2. **Create**, review the added resource, **Save** [docs/resource-guides/onprem/services.md#in-the-studio].

**In code**
If you run Postgres yourself, describe it as external:
```yaml
resources:
  db:
    type: database
    external: true
    connection:
      host: ${env:DB_HOST, localhost}
      port: 5432
      database: orders
      password_env: DB_PASSWORD
```
`password_env` is the name of the variable holding the password, not the password."""),

    A(859, provider="aws", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=[f"{CF}#provider"],
      user="i read arm64 lambdas are cheaper. how i switch all my functions to arm?",
      steps=[S("search_docs", query="architecture arm64",
               docs=[D(CF, "provider", start="| Key | Type | Default | Notes |", end="| `architecture` |")])],
      final="""Set `architecture: arm64` at provider level; AWS uses it, and pskit also picks matching pip wheels for it [docs/configuration.md#provider].

**In studio**
1. **Overview & provider** > *Defaults for every function* > **Architecture**: `arm64`.
2. **Save**, then **Deploy > Deploy**.

**In code**
```yaml
provider:
  name: aws
  architecture: arm64
```
Test once after the switch if you use packages with native code."""),

    A(860, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{CF}#functions"],
      user="In serverless.yml we had reservedConcurrency: 5 on the payments function. What's the pskit equivalent?",
      steps=[S("search_docs", query="reserved concurrency function",
               docs=[D(CF, "functions", start="| `concurrency` | int ≥ 0 | — |", end="| `concurrency` | int ≥ 0 | — |")]),
             S("search_docs", query="functions concurrency reserved max instances",
               docs=[D(CF, "functions", end="Event syntax is in [events.md](events.md).", words=120)])],
      final="""`concurrency` on the function: reserved concurrency (or max instances where supported) [docs/configuration.md#functions].

**In code**
```yaml
functions:
  payments:
    handler: app.payments.handle
    concurrency: 5
```

**In studio**
1. **Functions**: click `payments`, go to **Environment & permissions**.
2. *Concurrency & tags* > **Reserved concurrency / max instances**: `5`.
3. **Apply changes**, **Save**."""),

    A(861, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#queue"],
      user="Error: pskit.yml is invalid:\n  - functions.worker.events.0.batch_size: Input should be less than or equal to 10000",
      steps=[S("search_docs", query="queue batch_size limit",
               docs=[D(EV, "queue", words=40)])],
      final="""`batch_size` goes from 1 to 10000 [docs/events.md#queue]. Use 10000 at most, and add `batch_window` if you want SQS to wait for fuller batches.

**In code**
```yaml
functions:
  worker:
    handler: app.handlers.worker
    events:
      - queue: {name: jobs, batch_size: 10000, batch_window: 20}
```
`batch_window` is in seconds (0-300)."""),

    A(862, provider="aws", stage="prod", mode="ask", page="Overview", persona="informal_non_native",
      sources=[f"{CF}#provider"],
      user="finance want tag team=payments on everything we create in aws. one place for it?",
      steps=[S("search_docs", query="tags all resources",
               docs=[D(CF, "provider", start="| `tags` | map | `{}` |", end="| `tags` | map | `{}` |"),
                     D(PR, "providers", start="- Resources are tagged or labelled", end="- Resources are tagged or labelled")])],
      final="""Yes: `provider.tags`. They are merged with pskit's own `pskit-service`, `pskit-stage` and `managed-by` tags [docs/configuration.md#provider].

**In studio**
1. **Overview & provider** > *Tags*: add `team` = `payments`.
2. **Save**, then **Deploy > Deploy**.

**In code**
```yaml
provider:
  name: aws
  tags:
    team: payments
```"""),

    A(863, provider="gcp", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{CF}#providers-per-cloud-overrides"],
      user="Same pskit.yml goes to AWS and GCP. On GCP only, every function should get 1024 MB. Just the yaml please.",
      steps=[S("search_docs", query="per provider override memory",
               docs=[D(CF, "providers-per-cloud-overrides")])],
      final="""**In code**
```yaml
providers:
  gcp:
    memory: 1024
```
The block for the active provider is merged into the config, and `memory` there is shorthand for `provider.memory` [docs/configuration.md#providers-per-cloud-overrides]."""),

    A(864, provider="gcp", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#http"],
      user="Error: pskit.yml is invalid:\n  - functions.api.events.0.cors.bool: Input should be a valid boolean\n  - functions.api.events.0.cors.CorsConfig.origin: Extra inputs are not permitted",
      steps=[S("search_docs", query="cors origins option",
               docs=[D(EV, "http", start="**CORS**", end="The runtime answers `OPTIONS` preflights")])],
      final="""The key is `origins` (plural) and takes a list; `cors` is either `true` or that mapping [docs/events.md#http].

**In code**
```yaml
functions:
  api:
    handler: app.handlers.api
    events:
      - http:
          path: /items
          method: GET
          cors:
            origins: ["https://shop.example.com"]
```"""),

    A(865, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=[f"{ST}#what-you-can-do"],
      user="how make a workflow in studio: first validate-order then charge-card. both function exist already",
      steps=[S("search_docs", query="studio workflow builder states",
               docs=[D(ST, "what-you-can-do", start="| **Workflows** |", end="| **Workflows** |")])],
      final="""**In studio**
1. **Workflows** > **+ Create workflow**, give it a **Name** (e.g. `order-pipeline`).
2. In the *Add state* palette click **task**. In the inspector set **State name** `Validate` and **Function** `validate-order`.
3. Click **task** again: `Charge`, **Function** `charge-card`.
4. Select `Validate`: **Then** = *Go to* `Charge`. Select `Charge`: **Then** = *End*. Check that *Starts at* is `Validate`.
5. **Save**. Try it with **Deploy** > *Run a workflow locally*, then **Deploy > Deploy**.

On GCP the default engine compiles it to Cloud Workflows."""),

    A(866, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=[f"{PR}#{GC}"],
      user="Our repo has a main.py at the project root with some shared helpers. Any problem when we deploy this to GCP?",
      steps=[S("search_docs", query="gcp main.py source root",
               docs=[D(PR, GC, start="**Limits:**", end="**Limits:**")])],
      final="""Yes. On GCP pskit generates the bundle's root `main.py`, so you must not have your own `main.py` at the source root [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

Move the helpers into your package, e.g. `app/helpers.py`, and import them from there (`from app.helpers import ...`). Then run `pskit validate -p gcp` and test with `pskit invoke`."""),

    A(867, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{EV}#http", f"{PR}#{AZ}"],
      user="only in studio please: how do i make my azure http function need a function key?",
      steps=[S("search_docs", query="azure function key auth",
               docs=[D(EV, "http", start="**Auth support**", end="| `key` |")])],
      final="""**In studio**
1. **Functions**: click the function and go to the **Triggers** step.
2. Open its HTTP trigger and set **Auth** to `key` (on Azure this is a function key, `AuthLevel.FUNCTION`) [docs/events.md#http].
3. **Apply changes**, **Save**, then **Deploy > Deploy**."""),

    A(868, provider="azure", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#storage", f"{PR}#{AZ}"],
      user="media -> Azure Functions [stable] stage=dev region=westeurope\n  1 function(s), 0 workflow(s)\n  ERROR: [functions.cleanup] Azure blob triggers only fire on created/updated blobs\n\ni need to know when images are deleted",
      steps=[S("search_docs", query="azure blob deleted events",
               docs=[D(EV, "storage", start="| Provider | Service | Filters | Notes |", end="| azure |")])],
      final="""Azure blob triggers fire only for created/updated blobs; there is no `deleted` event on Azure [docs/events.md#storage].

Options:
1. Have the code that deletes an image also send a message to a queue, and let `cleanup` be a queue worker.
2. Keep `cleanup` for the clouds that have delete events and switch it off on Azure:
```yaml
providers:
  azure:
    functions:
      cleanup: {enabled: false}
```"""),

    A(869, provider="azure", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{PR}#{AZ}"],
      user="  WARNING: [functions.worker] environment LOG_MODE differs between functions; Azure app settings are shared by the whole Function App (last one wins)\n\nvalidate says valid. can i ignore it?",
      steps=[S("search_docs", query="azure environment app-wide warning",
               docs=[D(PR, AZ, start="**Limits:**", end="**Limits:**")])],
      final="""Don't ignore it: on Azure `environment` is app-wide [docs/providers.md#azure-azure-functions]. All functions share one Function App, so both `api` and `worker` get the same `LOG_MODE`, the last one written.

Give each function its own variable name instead:

**In code**
```yaml
functions:
  api:
    handler: app.handlers.api
    environment: {API_LOG_MODE: verbose}
  worker:
    handler: app.handlers.worker
    environment: {WORKER_LOG_MODE: quiet}
```
and read that name in each handler."""),

    A(870, provider="azure", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{PR}#{AZ}"],
      user="Our order-pipeline workflow runs on the embedded engine on Azure. How do I switch it to a Logic App in studio, and how is it started then?",
      steps=[S("search_docs", query="azure logic app native workflow",
               docs=[D(PR, AZ, start="**Native workflows (Logic Apps, opt-in).**", end="**Native workflows (Logic Apps, opt-in).**")])],
      final="""**In studio**
1. **Workflows**: open `order-pipeline`.
2. In *Settings* set **Engine** to `native`.
3. **Save**, then **Deploy > Deploy**.

It is deployed as a Logic App with an HTTP request trigger. Start it with a `POST` to the trigger's callback URL, which `pskit info` shows as the workflow `url`. That URL contains a SAS signature, so treat it like a secret [docs/providers.md#azure-azure-functions]."""),
]
