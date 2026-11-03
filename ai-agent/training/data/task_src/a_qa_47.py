"""Category A (docs Q&A and how-to), batch 47: studio-first how-tos. On premises: what Remove keeps, joining a
server to a cluster, hook names (real error), enqueueing with curl, e-mail triggers for a subdomain, starting a
workflow over HTTP, stage names (real error), schedule time zones. AWS: DynamoDB permissions in the function
editor, service names (real error), saved test events, --skip-deps, a 4-field cron (real error). GCP: duplicating
a function, created + deleted storage triggers, python3.8 (real error), starting a deployed workflow. Azure:
service principals for CI, auth iam (real error), sending a test queue message. Hand-written; assembled by
tools/assemble.py."""

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
WE = "docs/workflow-executions.md"
SM = "docs/smtp/README.md"

CONVERSATIONS = [
    A(911, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{PR}#{OP}", f"{ST}#what-you-can-do"],
      user="if i press Remove on the deploy page for my onprem dev, are my queue messages and files deleted too?",
      steps=[S("search_docs", query="onprem remove data",
               docs=[D(PR, OP, start="`pskit deploy` writes the bundle under", end="`pskit deploy` writes the bundle under")])],
      final="""No. On premises `pskit remove` stops the process (or container / systemd unit) and does not delete `data_dir`, where the built-in queues, buckets and topics live [docs/providers.md#onprem-on-premises]. A later deploy with the same data directory finds them again.

**In studio**
1. **Deploy > Remove** with `onprem` / `dev` in the top bar.
2. Type the confirmation studio asks for.

**In the terminal**
```bash
pskit remove -s dev
```
To empty a built-in queue or bucket on purpose, use `pskit resources clear <key>` while the host runs."""),

    A(912, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="informal_non_native",
      sources=["docs/cluster.md#set-up"],
      user="cluster prod is full. i have new server edge3 saved already. how add it to the cluster in studio, functions are running, ok?",
      steps=[S("search_docs", query="join server cluster running",
               docs=[D("docs/cluster.md", "set-up", start="3. **Join servers**", end="services, or whose swarm is locked.")])],
      final="""Yes, you can join while functions are running. pskit installs the agent, joins the server and copies the images already deployed, so replicas can start there at once [docs/cluster.md#set-up].

**In studio**
1. **Scaling cluster**: open `prod`.
2. Press **+ Join server** and pick `edge3`.
3. Watch the job output; it also prints the firewall rules edge3 needs.
4. The server's CPU / memory / disk bars appear; replicas that could not be placed get scheduled."""),

    A(913, provider="onprem", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=[f"{CF}#hooks"],
      user="Error: pskit.yml is invalid:\n  - hooks: Value error, unknown hooks ['pre_deploy']; allowed: ['after_deploy', 'after_package', 'after_remove', 'before_deploy', 'before_package', 'before_remove']",
      steps=[S("search_docs", query="hooks names before deploy",
               docs=[D(CF, "hooks")])],
      final="""The hook is called `before_deploy`, not `pre_deploy` [docs/configuration.md#hooks].

**In code**
```yaml
hooks:
  before_deploy:
    - python scripts/migrate.py
```"""),

    A(914, provider="onprem", stage="prod", mode="ask", page="none", persona="terse_expert",
      sources=[f"{PR}#{OP}", "docs/client.md#http-api"],
      user="bash cron job on another box must push a json message into the jobs queue of our onprem host. curl?",
      steps=[S("search_docs", query="enqueue message http onprem host",
               docs=[D(PR, OP, start="| Request | Effect |", end="| `POST /__pskit/queues/<name>` |")]),
             S("search_docs", query="http api client queues curl token",
               docs=[D("docs/client.md", "http-api", words=120)])],
      final="""`POST /__pskit/queues/<name>` with one JSON value, a list, or `{"messages": [...]}`; it answers `202 {"queued": [ids]}` [docs/providers.md#onprem-on-premises].

```bash
curl -X POST http://fn.internal.example:8080/__pskit/queues/jobs \\
  -H "content-type: application/json" \\
  -H "x-pskit-token: <admin token>" \\
  -d '{"order_id": 1}'
```
The token header is needed when the host has an `admin_token`. The other box must reach the host's port (`options.host: 0.0.0.0` and the firewall)."""),

    A(915, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SM}#create-it"],
      user="We want a function to run for every e-mail sent to support@... Our company mail is on Microsoft 365 for example.com. How do we set this up in studio without breaking our normal mail?",
      steps=[S("search_docs", query="email trigger smtp server studio",
               docs=[D(SM, "create-it", end="`inbound.example.com`. Changing the root domain's MX would stop every mailbox of the company from receiving mail.")])],
      final="""Use a **subdomain** such as `inbound.example.com`. Changing the MX of `example.com` would stop every company mailbox from receiving mail [docs/smtp/README.md#create-it].

**In studio**
1. **Resources > + SMTP server**.
2. **Resource key** `inbound-mail`, **Domains** `inbound.example.com`, **Where**: the functions' SSH server, **Port** `25`.
3. Tick your function under **Trigger functions**, create it, **Save**.
4. Add the A and MX records from its DNS guide at your domain provider.
5. **Deploy > Deploy** so the host knows the trigger.

Then mail to `support@inbound.example.com` runs the function. Make the server's port 25 reachable from the internet."""),

    A(916, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="informal_non_native",
      sources=[f"{PR}#{OP}", f"{WE}#starting-a-run"],
      user="other app (java) must start order-pipeline workflow on onprem host and sometimes wait the result. http possible?",
      steps=[S("search_docs", query="start workflow http onprem",
               docs=[D(PR, OP, start="| `POST /__pskit/workflows/<name>` |", end="| `GET /__pskit/executions`")])],
      final="""Yes. `POST /__pskit/workflows/order-pipeline` with the input as the JSON body starts it and returns `202 {"execution_id", ...}`. Add `?wait=true` to get the result instead [docs/providers.md#onprem-on-premises].

```bash
curl -X POST "http://fn.internal.example:8080/__pskit/workflows/order-pipeline?wait=true" \\
  -H "content-type: application/json" -H "x-pskit-token: <admin token>" \\
  -d '{"order_id": 7}'
```
Without `wait`, poll `GET /__pskit/executions/<id>`. The token header is needed when the host has an `admin_token`."""),

    A(917, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{CF}#provider"],
      user="Error: pskit.yml is invalid:\n  - provider.stage: Value error, stage must be lowercase alphanumeric/dash, max 16 chars, e.g. dev, prod",
      steps=[S("search_docs", query="stage name rules",
               docs=[D(CF, "provider", start="| `stage` | string | `dev` |", end="| `stage` | string | `dev` |")])],
      final="""A stage must be lowercase letters, digits and dashes, at most 16 characters (`[a-z][a-z0-9-]{0,15}`) [docs/configuration.md#provider]. `Prod_1` has a capital and an underscore; use `prod-1`.

**In studio**
Type `prod-1` in the stage box of the top bar (and **Overview & provider** > **Stage** if it is saved there).

**In the terminal**
```bash
pskit deploy -s prod-1
```"""),

    A(918, provider="onprem", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{PR}#{OP}", f"{EV}#schedule"],
      user="Our on-prem server runs in UTC, but the daily report must go out at 08:00 Vienna time, also in summer. How do I set that?",
      steps=[S("search_docs", query="schedule timezone",
               docs=[D(EV, "schedule", words=90)]),
             S("search_docs", query="onprem schedule timezone missing warns",
               docs=[D(PR, OP, start="| schedule | in-process rate", end="| schedule | in-process rate")])],
      final="""Give the schedule a `timezone`; the on-prem host evaluates the cron in that zone (an unknown IANA name warns and falls back to UTC) [docs/providers.md#onprem-on-premises].

**In code**
```yaml
functions:
  report:
    handler: app.handlers.report
    events:
      - schedule:
          cron: "0 8 * * *"
          timezone: Europe/Vienna
```

**In studio**
**Functions** > `report` > **Triggers** > the schedule: **At** `08:00`, **Timezone** `Europe/Vienna`, **Apply changes**."""),

    A(919, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{CF}#functions"],
      user="my save-order lambda gets AccessDenied when writing to dynamodb. how i give it permission in studio?",
      steps=[S("search_docs", query="function iam permissions dynamodb",
               docs=[D(CF, "functions", end="Event syntax is in [events.md](events.md).", words=120), D(CF, "functions", start="| `iam` | like `provider.iam` |", end="| `iam` | like `provider.iam` |")])],
      final="""Add an IAM statement to the function; pskit adds it to a dedicated role for that function [docs/configuration.md#functions].

**In studio**
1. **Functions**: click `save-order`, go to **Environment & permissions**.
2. Open *Permissions (IAM)*, press **+ Add statement**.
3. **Effect** `Allow`, **Actions** `dynamodb:PutItem` (add `dynamodb:GetItem` etc. as needed), **Resources**: the table's ARN.
4. **Apply changes**, **Save**, **Deploy > Deploy**."""),

    A(920, provider="aws", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{CF}#top-level"],
      user="Error: pskit.yml is invalid:\n  - service: Value error, service must be 2-32 chars of lowercase letters, digits and dashes\n\nwe named it My_Service like our java app",
      steps=[S("search_docs", query="service name rules",
               docs=[D(CF, "top-level")])],
      final="""The service name may only have lowercase letters, digits and dashes, 2-32 characters, starting with a letter. `My_Service` breaks that; use `my-service`.

**In studio**
**Overview & provider** > *Service* > **Service name**: `my-service`, then **Save**.

**In code**
```yaml
service: my-service
```
[docs/configuration.md#top-level]"""),

    A(921, provider="aws", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=[f"{ST}#test-functions"],
      user="in lambda console i had saved test events. studio also can save it?",
      steps=[S("search_docs", query="save test event studio",
               docs=[D(ST, "test-functions", end="`.pskit/studio/test-events.json`, like test events in the Lambda console.")])],
      final="""Yes, like the Lambda console.

**In studio**
1. **Test**: pick the function and the trigger.
2. Edit the payload in *2. Edit the event*.
3. Press **Save event** and give it a name.

Saved events are kept per function in `.pskit/studio/test-events.json` [docs/studio.md#test-functions]."""),

    A(922, provider="aws", stage="dev", mode="ask", page="none", persona="terse_expert",
      sources=[f"{CLI}#pskit-deploy"],
      user="deps already vendored in the bundle dir. deploy without pip install, command only",
      steps=[S("search_docs", query="deploy skip dependencies",
               docs=[D(CLI, "pskit-deploy", end="| `--confirm` |")])],
      final="""**In the terminal**
```bash
pskit deploy --skip-deps
```
`--skip-deps` doesn't vendor dependencies [docs/cli.md#pskit-deploy]."""),

    A(923, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#schedule"],
      user="Error: pskit.yml is invalid:\n  - functions.nightly.events.0: Value error, cron must be a standard 5-field expression: 'min hour dom month dow'\n\ni wrote \"0 2 * *\"",
      steps=[S("search_docs", query="cron 5 fields schedule",
               docs=[D(EV, "schedule", words=90)])],
      final="""A cron needs five fields; `0 2 * *` has four. Every night at 02:00 UTC is `0 2 * * *` [docs/events.md#schedule].

**In code**
```yaml
functions:
  nightly:
    handler: app.handlers.nightly
    events:
      - schedule: "0 2 * * *"
```
pskit converts the portable syntax to each cloud's dialect, so don't write the AWS `cron(...)` form."""),

    A(924, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{ST}#what-you-can-do"],
      user="i want a copy of my import function to try changes, without touch the old one. easy way?",
      steps=[S("search_docs", query="duplicate function studio",
               docs=[D(ST, "what-you-can-do", start="| **Functions** |", end="| **Functions** |")])],
      final="""**In studio**
1. **Functions**: press **Duplicate** on the `import` row. Studio creates `import-copy` and opens it.
2. HTTP routes are not copied, because two functions can't share the same `METHOD /path`. Add a new route in **Triggers** if you need one.
3. Point **Handler** at a new function if you want to change the code separately (**Code** opens the file).
4. **Apply changes**, **Save**.

Test it with **Test > ▶ Run locally** before deploying."""),

    A(925, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=[f"{EV}#storage"],
      user="my cleanup function has storage events created and deleted. on gcp it become 2 cloud functions? normal?",
      steps=[S("search_docs", query="gcp storage created deleted separate",
               docs=[D(EV, "storage", start="| Provider | Service | Filters | Notes |", end="| gcp |")]),
             S("search_docs", query="gcp multi trigger functions split",
               docs=[D(EV, "gcp-multi-trigger-functions-are-split-automatically")])],
      final="""Yes, normal. On GCP `created` and `deleted` become separate deployments [docs/events.md#storage], because a Cloud Function has one trigger; pskit splits it for you [docs/events.md#gcp-multi-trigger-functions-are-split-automatically]. Your handler and `pskit.yml` stay the same; check `record.action` (`"created"` / `"deleted"`) in the code."""),

    A(926, provider="gcp", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{CF}#provider", f"{PR}#providers"],
      user="Error: pskit.yml is invalid:\n  - provider.runtime: Value error, runtime must be python3.9 .. python3.14 or nodejs18, nodejs20, nodejs22, nodejs24 (provider support varies)\n\nold project was python3.8",
      steps=[S("search_docs", query="runtime python versions gcp",
               docs=[D(PR, "providers", start="| Provider | Tier |", end="| [`gcp`]")])],
      final="""pskit supports Python 3.9 and newer; on GCP 3.9 to 3.13 [docs/providers.md#providers].

**In studio**
**Overview & provider** > *Defaults for every function* > **Runtime**: e.g. `python3.12`, then **Save**.

**In code**
```yaml
provider:
  name: gcp
  runtime: python3.12
```
Or remove `runtime` so pskit picks python3.12 or the newest supported version below it. Then test your handlers with `pskit invoke`, since the code now runs on a newer Python."""),

    A(927, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WE}#starting-a-run"],
      user="order-pipeline is deployed to GCP prod as Cloud Workflows. How do I start one execution from my terminal with a JSON file as input and follow it?",
      steps=[S("search_docs", query="start deployed workflow execution",
               docs=[D(WE, "starting-a-run", end="`--wait` waits for the result (on-premises). Native engines always return at once. `--json` prints the raw response.")]),
             S("search_docs", query="gcp workflows executions extra credentials",
               docs=[D(WE, "aws-step-functions-and-google-cloud-workflows", words=40)])],
      final="""**In the terminal**
```bash
pip install "py-serverless-kit[gcp]"
pskit workflow start order-pipeline -i @order.json -s prod
pskit workflow status <execution id> --watch -s prod
```
On GCP it returns at once with the execution id [docs/workflow-executions.md#starting-a-run]; the id is the long `projects/.../executions/...` name. It uses your application-default credentials."""),

    A(928, provider="azure", stage="prod", mode="ask", page="Setup", persona="beginner",
      sources=["docs/getting-started.md#6-configure-cloud-credentials"],
      user="our CI must deploy to azure without az login. what does it need?",
      steps=[S("search_docs", query="azure ci service principal credentials",
               docs=[D("docs/getting-started.md", "6-configure-cloud-credentials", end="| `azure` |")])],
      final="""A service principal: set `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET` and `ARM_TENANT_ID`, plus `ARM_SUBSCRIPTION_ID` (or `options.subscription_id`) [docs/getting-started.md#6-configure-cloud-credentials].

**In the terminal**
In the CI job, with the values coming from the CI's secret store:
```bash
pskit validate -p azure
pskit deploy -s prod
```
Keep the Terraform state in a remote backend (`provider.state`) so CI and your laptop share it."""),

    A(929, provider="azure", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#http"],
      user="shop -> Azure Functions [stable] stage=dev region=westeurope\n  1 function(s), 0 workflow(s)\n  ERROR: [functions.api] http auth 'iam' is not supported on Azure; use none or key (or put API Management / Easy Auth in front)",
      steps=[S("search_docs", query="azure http auth options",
               docs=[D(EV, "http", start="**Auth support**", end="| `key` |")])],
      final="""On Azure pskit supports `auth: none` or `auth: key` (a function key) [docs/events.md#http]. For user sign-in, put API Management or Easy Auth in front, as the message says.

**In studio**
**Functions**: click `api`, **Triggers** step, set **Auth** to `key`, **Apply changes**.

**In code**
```yaml
functions:
  api:
    handler: app.handlers.api
    events:
      - http: {path: /items, method: GET, auth: key}
```"""),

    A(930, provider="azure", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=[f"{CLI}#pskit-trigger"],
      user="pskit trigger to my azure queue worker says it can't send. what it need?",
      steps=[S("search_docs", query="trigger azure queue connection string",
               docs=[D(CLI, "pskit-trigger", start="What pskit can send itself", end="| Azure |"), D(CLI, "pskit-trigger", start="¹ `AZURE_STORAGE_CONNECTION_STRING`", end="¹ `AZURE_STORAGE_CONNECTION_STRING`")])],
      final="""For Azure Storage queues pskit needs `AZURE_STORAGE_CONNECTION_STRING`, the connection string of the Function App's storage account [docs/cli.md#pskit-trigger].

**In the terminal**
Set it in your shell (copy the value from the storage account in the Azure portal), then:
```bash
pskit trigger -f worker -e 0 -d '{"order_id": 1}'
```
`pskit trigger --list` prints the `az` command and console steps if you'd rather send it another way."""),
]
