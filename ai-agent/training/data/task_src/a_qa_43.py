"""Category A (docs Q&A and how-to), batch 43: studio-first how-tos. On premises: an existing queue folder, the
admin token, the health URL, deleting stored logs, systemd units, Docker on the laptop, a host port that times
out, moving saved servers to a new laptop. AWS: long timeouts (real validate error), S3 upload triggers from the
wizard, CloudWatch tail, sending a real upload. GCP: region, runtime service account, 540 s event limit (real
error), test Pub/Sub messages. Azure: existing resource group, queue names (real error), Logs page needs.
Hand-written; assembled by tools/assemble.py."""

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
OPT = D(PR, OP, start="- **Dependencies:**", words=170)

CONVERSATIONS = [
    A(831, provider="onprem", stage="prod", mode="ask", page="Overview", persona="informal_non_native",
      sources=[f"{PR}#{OP}", f"{EV}#storage"],
      user="we have already folder /var/pskit/queues on server with the queue files. pskit must use it not make new. where in studio?",
      steps=[S("search_docs", query="onprem queue existing directory",
               docs=[D(EV, "storage", start="| onprem | a directory of files |", end="| onprem | a directory of files |")]),
             S("search_docs", query="onprem services queue use directory path",
               docs=[OPT])],
      final="""**In studio**
1. **Overview & provider**: open *Built-in services*.
2. In the **Queue** row switch from *Built-in* to *Existing folder*.
3. Type `/var/pskit/queues` in the path field.
4. **Save**, then **Deploy > Deploy**.

It writes `provider.options.services.queue: {use: directory, path: /var/pskit/queues}` [docs/providers.md#onprem-on-premises]."""),

    A(832, provider="onprem", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=[f"{PR}#{OP}", "docs/client.md#when-connections-time-out"],
      user="what is the Admin token field on the overview page? do i need it?",
      steps=[S("search_docs", query="admin token onprem",
               docs=[OPT]),
             S("search_docs", query="admin token 401 client",
               docs=[D("docs/client.md", "when-connections-time-out", start="| `HTTP 401` |", end="| `HTTP 401` |")])],
      final="""It protects the host's control endpoints: when set, calls to `/__pskit/*` (except the health check) need the header `x-pskit-token` [docs/providers.md#onprem-on-premises]. Without it, anyone who can reach the port can enqueue messages, invoke functions or read logs, so set it for any host other machines can reach.

**In studio**
1. **Overview & provider** > *On-premises options* > **Admin token**: keep the default `${env:PSKIT_ADMIN_TOKEN, }`.
2. Set `PSKIT_ADMIN_TOKEN` in your shell before starting studio and deploying.
3. **Save**, then **Deploy > Deploy**.

**In code**
```yaml
provider:
  name: onprem
  options:
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"
```
pskit's own commands read the token from the deploy. Your own scripts get `HTTP 401` without it, so give them `PSKIT_ADMIN_TOKEN` too [docs/client.md#when-connections-time-out]."""),

    A(833, provider="onprem", stage="prod", mode="ask", page="none", persona="terse_expert",
      sources=[f"{PR}#{OP}"],
      user="health check url of the onprem host for our uptime monitor? token needed?",
      steps=[S("search_docs", query="onprem health endpoint",
               docs=[D(PR, OP, start="| Request | Effect |", end="| `GET /__pskit/health` |")])],
      final="""`GET /__pskit/health` returns the status and needs no token [docs/providers.md#onprem-on-premises].

```bash
curl http://fn.internal.example:8080/__pskit/health
```
Use your host's address and port."""),

    A(834, provider="onprem", stage="dev", mode="ask", page="Logs", persona="beginner",
      sources=[f"{CLI}#pskit-logs", "docs/dashboard.md#log-sources"],
      user="i deleted the old importer function but its logs are still on the logs page. how i clean them?",
      steps=[S("search_docs", query="delete logs studio stored logs",
               docs=[D(ST, "setup-logs-and-provider-differences", start="- **Logs** shows the logs", end="- **Logs** shows the logs")]),
             S("search_docs", query="pskit logs delete stream function onprem",
               docs=[D(CLI, "pskit-logs", start="| `--streams` |", end="| `-y, --yes` |")])],
      final="""**In studio**
1. **Logs**: open the *Stored logs* section (list, select and delete).
2. Tick the `importer` stream and delete it; studio asks to confirm.

**In the terminal**
```bash
pskit logs --streams
pskit logs --delete importer --yes
```
On premises a stream id is the function name [docs/cli.md#pskit-logs]. This clears its entries in the host's memory and in `host.jsonl`."""),

    A(835, provider="onprem", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{PR}#{OP}"],
      user="Our SSH deploy runs the host as a plain process. After a server reboot it's gone. We want a systemd unit so it comes back. What do we set?",
      steps=[S("search_docs", query="ssh deploy systemd unit restart",
               docs=[D(PR, OP, start="| `ssh` or `scp` |", end="| `ssh` or `scp` |")]),
             S("search_docs", query="install systemd sudo etc systemd system",
               docs=[D(PR, OP, start="**Limits:** no cloud authorizer", end="**Limits:** no cloud authorizer")])],
      final="""Use `install: systemd` with `sudo: true`; units are written to `/etc/systemd/system`, and apply runs `systemctl restart` and waits for `/__pskit/health` [docs/providers.md#onprem-on-premises].

**In studio**
1. **Overview & provider** > *On-premises deployment*, with **Where the host runs** = *SSH server*.
2. Set **Install as** to `systemd` and switch on **Use sudo**.
3. **Save**, then **Deploy > Deploy**.

**In code**
```yaml
provider:
  name: onprem
  options:
    deploy:
      method: ssh
      host: 192.0.2.10
      user: pskit
      install: systemd
      sudo: true
```
The `sudo` is non-interactive (`sudo -n`), so the SSH user needs a sudoers rule without a password prompt (or deploy as root)."""),

    A(836, provider="onprem", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=[f"{PR}#{OP}"],
      user="i have no server, i want run the host in docker on my own laptop. how in studio",
      steps=[S("search_docs", query="docker deploy laptop onprem",
               docs=[D(PR, OP, start="| `docker` | image built on this machine", end="| `docker` | image built on this machine"),
                     D(PR, OP, start="# Docker on this laptop only (no SSH, no .pem)", end="  image: pskit/orders:dev")])],
      final="""**In studio**
1. **Overview & provider** > *On-premises deployment*: leave **Saved server** empty.
2. **Where the host runs**: pick *Docker*. Don't fill **Docker host**, so it runs on this machine.
3. Optional: give an **Image** name, e.g. `pskit/orders:dev`.
4. **Save**, then **Deploy > Deploy**. The image is built here and the deploy waits until the container answers `/__pskit/health`.

You need Docker installed and running on the laptop; **Setup & credentials** checks it."""),

    A(837, provider="onprem", stage="prod", mode="ask", page="none", persona="pasted_error",
      sources=["docs/client.md#when-connections-time-out"],
      user="TimeoutError: timed out\n\nmy script calls the onprem host on our cloud vm at port 8080 and gets this. pskit deploy said ok and pskit logs works",
      steps=[S("search_docs", query="TimeoutError host port client",
               docs=[D("docs/client.md", "when-connections-time-out", end="| `HTTP 401` |"),
                     D(PR, OP, start="**Ports closed to this machine.**", end="**Ports closed to this machine.**")])],
      final="""That is almost always a firewall: your script can't open a TCP connection to port 8080 [docs/client.md#when-connections-time-out]. `pskit logs` still works because pskit sends its control calls over the deploy's SSH login when the port is closed [docs/providers.md#onprem-on-premises].

Fix it one of these ways:

**In the terminal**
```bash
pskit client tunnel -s prod
```
Keep it running, and point the script at `PSKIT_HOST=http://127.0.0.1:8080`.

**In code**
To call the host directly, let it listen on the network and open 8080 to your IP in the VM's security group / NSG:
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
```"""),

    A(838, provider="onprem", stage="dev", mode="ask", page="Setup", persona="informal_non_native",
      sources=[f"{CLI}#pskit-settings"],
      user="new laptop, git clone the project but studio show no servers and no clusters. old pc has them all. how move it with studio only",
      steps=[S("search_docs", query="move saved servers new machine",
               docs=[D(CLI, "pskit-settings", end="| `settings import FILE [--dry-run] [--replace] [--yes]` |")])],
      final="""Saved servers, clusters and SSH logins live in `.pskit`, which is not in git [docs/cli.md#pskit-settings].

**In studio**
1. On the old PC: press **⇅ Settings** in the top bar (or **Setup & credentials** > *Move settings to another machine*) and export. Choose a passphrase of at least 8 characters.
2. Copy the `.pskit-settings` file to the new laptop.
3. On the new laptop: **⇅ Settings** > import the file and type the passphrase.

Send the file and the passphrase by different channels."""),

    A(839, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{PR}#aws-aws-lambda"],
      user="exports -> AWS Lambda [stable] stage=dev region=us-east-1\n  1 function(s), 0 workflow(s)\n  ERROR: [functions.export] timeout 1200s exceeds AWS Lambda max 900s\n\nthe export really needs ~20 min",
      steps=[S("search_docs", query="aws lambda max timeout 900",
               docs=[D(PR, "aws-aws-lambda", start="**Limits:**", end="**Limits:**"),
                     D(PR, "providers", start="| Provider | Tier |", end="| [`aws`]")]),
             S("search_docs", query="long running work split queue workflow",
               docs=[D("docs/workflows.md", "embedded-orchestrator", start="- The **whole run must fit in one function invocation**", end="`pskit validate` warns about this.")])],
      final="""A Lambda can run at most 900 s [docs/providers.md#providers], so `timeout: 1200` can't be deployed. Set it to `900` or less and split the work:

1. Cut the export into chunks: one function lists the chunks and sends one queue message per chunk; a queue worker exports one chunk per message.
2. Or make it a workflow (Step Functions, the native engine on AWS): a `map` state runs one task per chunk, each within the Lambda limit. Embedded workflows don't help here, because the whole run must fit in one invocation [docs/workflows.md#embedded-orchestrator].

**In code**
```yaml
functions:
  export:
    handler: app.handlers.export
    timeout: 900
```"""),

    A(840, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{ST}#project-environment-trigger-resources-and-remove", f"{EV}#storage"],
      user="i want a new s3 bucket and my function run when someone upload a file there. can studio make the bucket too?",
      steps=[S("search_docs", query="studio storage trigger create bucket",
               docs=[D(ST, "project-environment-trigger-resources-and-remove", start="- **Triggers → Create new → Create & select**", end="  in the same way.")]),
             S("search_docs", query="storage event created default",
               docs=[D(EV, "storage", end="Each record has `bucket`, `key`, `size` and `action`")])],
      final="""Yes. pskit creates the bucket on deploy.

**In studio**
1. **Functions**: click your function, go to the **Triggers** step.
2. Under *Add a trigger* click **Storage**.
3. **Source**: *Create new bucket*, type the bucket name, and press **Create & select**. It also adds the bucket to Resources, so other functions can use it.
4. **Fire on**: leave *created* (the default).
5. **Apply changes**, **Save**, **Deploy > Deploy**.

**In code**
```yaml
functions:
  thumbnails:
    handler: app.handlers.thumbnails
    events:
      - storage: {bucket: uploads-bucket, events: [created]}
```
Each record in the event has `bucket`, `key`, `size` and `action` [docs/events.md#storage]."""),

    A(841, provider="aws", stage="dev", mode="ask", page="Logs", persona="terse_expert",
      sources=[f"{CLI}#pskit-logs", "docs/dashboard.md#log-sources"],
      user="tail cloudwatch of worker live. cli only",
      steps=[S("search_docs", query="pskit logs follow aws cloudwatch",
               docs=[D(CLI, "pskit-logs", start="On AWS, `--level` and `--source`", end="On AWS, `--level` and `--source`"),
                     D("docs/dashboard.md", "log-sources", start="| AWS |", end="| AWS |")])],
      final="""**In the terminal**
```bash
pskit logs -f --function worker
```
On AWS `-f` polls every 3 seconds [docs/cli.md#pskit-logs]. It needs `pip install "py-serverless-kit[aws]"` and credentials that may read CloudWatch Logs [docs/dashboard.md#log-sources]."""),

    A(842, provider="aws", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=[f"{ST}#test-functions", f"{CLI}#pskit-trigger"],
      user="thumbnails is deployed to dev. I want to upload a real test object to its S3 bucket from studio and watch what the function logs. Steps?",
      steps=[S("search_docs", query="send real event deployed storage trigger",
               docs=[D(ST, "test-functions", end="an uploaded object, a topic message, an HTTP request or an invocation. Turn on *Show the function's logs* to watch it.")]),
             S("search_docs", query="trigger storage payload key content",
               docs=[D(CLI, "pskit-trigger", start="| Type | `-d` |", end="| storage |")])],
      final="""**In studio**
1. **Test**: pick `thumbnails` and its storage trigger in *1. Choose the event*.
2. *2. Edit the event*: the sample matches the trigger's prefix and suffix; edit `key` and `content` if you like.
3. Turn on *Show the function's logs*.
4. *3. Run it*: **☁ Send to AWS Lambda / dev**. It uploads the object to the real bucket, so S3 calls the function, and the logs appear below [docs/studio.md#test-functions]."""),

    A(843, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=[f"{CF}#provider"],
      user="how do i put my gcp functions in europe instead of us?",
      steps=[S("search_docs", query="change region",
               docs=[D("docs/getting-started.md", "8-switch-cloud", words=80)]),
             S("search_docs", query="provider region setting configuration",
               docs=[D(CF, "provider", words=160)])],
      final="""Set the provider's `region`, e.g. `europe-west1`.

**In studio**
1. **Overview & provider** > *Defaults for every function* > **Region**: `europe-west1`.
2. **Save**, then **Deploy > Deploy**.

**In the terminal**
For one command only:
```bash
pskit deploy -r europe-west1
```

**In code**
```yaml
provider:
  name: gcp
  region: europe-west1
```"""),

    A(844, provider="gcp", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{PR}#gcp-google-cloud-functions-2nd-gen"],
      user="Our security team created a service account for the functions with exactly the roles they need. Where do I tell pskit to run the GCP functions as that account?",
      steps=[S("search_docs", query="gcp service account runtime identity",
               docs=[D(PR, "gcp-google-cloud-functions-2nd-gen", end="| Trigger | Implementation |")]),
             S("search_docs", query="gcp iam statements ignored service account roles",
               docs=[D(PR, "gcp-google-cloud-functions-2nd-gen", start="**Limits:**", end="**Limits:**")])],
      final="""Use `options.service_account`, the runtime identity [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

**In studio**
1. **Overview & provider** > *Google Cloud Functions options* > **Service account**: the account's email.
2. **Save**, then **Deploy > Deploy**.

**In code**
```yaml
provider:
  name: gcp
  options:
    project: my-gcp-project
    service_account: runtime@my-gcp-project.iam.gserviceaccount.com
```
On GCP `iam.statements` are ignored, so all permissions come from the roles granted to that account."""),

    A(845, provider="gcp", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{PR}#gcp-google-cloud-functions-2nd-gen"],
      user="ingest -> Google Cloud Functions [stable] stage=dev region=europe-west1\n  1 function(s), 0 workflow(s)\n  ERROR: [functions.worker] event-triggered functions are limited to 540s on GCP",
      steps=[S("search_docs", query="gcp event triggered 540",
               docs=[D(PR, "gcp-google-cloud-functions-2nd-gen", start="**Limits:**", end="**Limits:**")])],
      final="""`worker` has a queue trigger, and event-triggered functions on GCP may run at most 540 s [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

**In studio**
**Functions**: click `worker`, set **Timeout (s)** to `540` or less in **Basics**, then **Apply changes**.

**In code**
```yaml
functions:
  worker:
    handler: app.handlers.worker
    timeout: 540
    events:
      - queue: uploads
```
If one message really takes longer, split the work into smaller messages."""),

    A(846, provider="gcp", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=[f"{CLI}#pskit-trigger", f"{ST}#test-functions"],
      user="after deploy i want publish test message to pubsub topic of my fanout function. pskit can do or i need gcloud?",
      steps=[S("search_docs", query="trigger topic gcp pubsub",
               docs=[D(CLI, "pskit-trigger", start="What pskit can send itself", end="| GCP |")]),
             S("search_docs", query="topic payload attributes trigger",
               docs=[D(CLI, "pskit-trigger", start="pskit trigger -f fanout", end="pskit trigger -f fanout")])],
      final="""pskit can do it: on GCP it publishes to Pub/Sub itself with your credentials [docs/cli.md#pskit-trigger].

**In the terminal**
```bash
pskit trigger -f fanout -e 0 -d '{"message": {"id": 1}, "attributes": {"type": "order"}}'
```

**In studio**
1. **Test**: pick `fanout` and its topic trigger.
2. Edit the message, then press **☁ Send to Google Cloud Functions / dev**.

The *How to test this* panel also shows the `gcloud pubsub topics publish` command if you prefer gcloud."""),

    A(847, provider="azure", stage="prod", mode="ask", page="Overview", persona="informal_non_native",
      sources=[f"{PR}#azure-azure-functions"],
      user="company give me an existing resource group, i not allowed create new. where put it, in gui",
      steps=[S("search_docs", query="azure resource group existing",
               docs=[D(PR, "azure-azure-functions", start="- **Credentials:**", end="One **Linux Consumption Function App**", words=300)])],
      final="""**In studio**
1. **Overview & provider**: open *Azure Functions options*.
2. Type the group's name in **Resource group** (empty means pskit creates one).
3. **Save**, then **Deploy > Deploy**."""),

    A(848, provider="azure", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{PR}#azure-azure-functions"],
      user="shop -> Azure Functions [stable] stage=dev region=westeurope\n  1 function(s), 0 workflow(s)\n  ERROR: [functions.worker] queue name 'Jobs_Queue' must be 3-63 lowercase letters, digits, dashes",
      steps=[S("search_docs", query="azure queue name rules",
               docs=[D(PR, "azure-azure-functions", start="| queue | Storage Queue", end="| queue | Storage Queue")]),
             S("search_docs", query="azure storage queue name lowercase",
               docs=[D(EV, "queue", words=150)])],
      final="""On Azure a queue is a Storage Queue, and its name must be 3-63 lowercase letters, digits and dashes. Rename it, e.g. `jobs-queue`.

**In studio**
**Functions**: click `worker`, **Triggers** step, change the queue name to `jobs-queue`, then **Apply changes**.

**In code**
```yaml
functions:
  worker:
    handler: app.handlers.worker
    events:
      - queue: jobs-queue
```
Also change any code or other function that sends to the old name. The poison queue becomes `jobs-queue-poison` [docs/providers.md#azure-azure-functions]."""),

    A(849, provider="azure", stage="dev", mode="ask", page="Logs", persona="beginner",
      sources=["docs/dashboard.md#log-sources", f"{CLI}#pskit-logs"],
      user="logs page shows nothing for my azure functions. on aws it worked. why?",
      steps=[S("search_docs", query="azure logs studio",
               docs=[D(CLI, "pskit-logs", end="Requirements per provider: [dashboard.md](dashboard.md#log-sources).")]),
             S("search_docs", query="log sources azure log analytics workspace needs",
               docs=[D("docs/dashboard.md", "log-sources", start="| Azure |", end="| Azure |")])],
      final="""On Azure pskit reads logs from Log Analytics (`AppTraces`), and only when the deployment has a Terraform output `log_analytics_workspace_id` [docs/dashboard.md#log-sources]. AWS reads CloudWatch directly, so it needs nothing extra.

What you need:
1. Add that output with `provider.terraform.extra` and deploy again.
2. On the machine running studio:
```bash
pip install azure-monitor-query azure-identity
```
Azure logs are read only: retention is set on the workspace. Until then, use the console link from `pskit info`."""),

    A(850, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{EV}#http", f"{PR}#azure-azure-functions"],
      user="on azure my api functions are at /orders, not /api/orders like in tutorials. did i set something wrong?",
      steps=[S("search_docs", query="azure api prefix route",
               docs=[D(EV, "http", start="pskit's runtime also matches routes itself", end="pskit's runtime also matches routes itself")]),
             S("search_docs", query="azure routePrefix empty paths exactly as configured",
               docs=[D(PR, "azure-azure-functions", start="One **Linux Consumption Function App**", end="One **Linux Consumption Function App**")])],
      final="""No, that is how pskit sets up Azure: `routePrefix` is empty, so your paths are served exactly as configured, without `/api` [docs/providers.md#azure-azure-functions]. The same `pskit.yml` gives the same paths on the other clouds too.

If clients expect `/api/...`, put it in the paths themselves, e.g. `- http: GET /api/orders`."""),
]
