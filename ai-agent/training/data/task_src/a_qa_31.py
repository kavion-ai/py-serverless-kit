"""Category A (docs Q&A and how-to), batch 31: aws / gcp / azure. Studio everyday use (provider switch, Problems,
undo, duplicate, live logs, Setup sign-in, New file, settings move, disabled trigger types), deployed tests per
cloud (trigger, schedules), resource commands (list, send, check), external caches, standalone buckets.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(591, provider="gcp", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/studio.md#what-you-can-do", "docs/studio.md#setup-logs-and-provider-differences"],
      user="Our project targets AWS today. In studio I want to switch it to GCP and see up front which of our triggers wouldn't work there. How does the switch work?",
      steps=[S("search_docs", query="studio switch provider triggers stop working",
               docs=[D("docs/studio.md", "what-you-can-do", start="| **Overview & provider** |", end="| **Overview & provider** |"),
                     D("docs/studio.md", "setup-logs-and-provider-differences", start="- **Enable / disable**")])],
      final="""Switching first lists the triggers that would stop working, and offers to disable what won't run on the new target [docs/studio.md#what-you-can-do] [docs/studio.md#setup-logs-and-provider-differences].

**In studio**
1. Open **Overview & provider** and pick the Google Cloud card.
2. Read the list of triggers and options that won't work on GCP, then click *Switch provider* (or *Switch only (fix later)*).
3. Fill in the provider option *project* (GCP needs it).
4. Check the Problems button in the top bar, then click **Save**.

**In the terminal**
To check without changing anything first:
```bash
pskit validate -p gcp
```
Your handler code doesn't change."""),

    A(592, provider="gcp", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/studio.md#what-you-can-do"],
      user="where do i see all problems of my config in studio at once? studio only",
      steps=[S("search_docs", query="studio problems validated as you type",
               docs=[D("docs/studio.md", "what-you-can-do", start="Every edit goes into an in-memory draft", end="asks first.")])],
      final="""**In studio**
1. Look at the Problems button in the top bar; it shows "N errors · N warnings".
2. Click it to see the full list. Each problem links to the field it concerns.
3. Change the provider or stage in the top bar to see the problems for that target.

The checks are the same as `pskit validate`, run as you type on the draft [docs/studio.md#what-you-can-do]."""),

    A(593, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/studio.md#what-you-can-do"],
      user="oh no i deleted wrong function in studio!! not saved yet. can get back?",
      steps=[S("search_docs", query="studio undo draft not saved",
               docs=[D("docs/studio.md", "what-you-can-do", start="Every edit goes into an in-memory draft", end="asks first.")])],
      final="""Yes. Edits go into an in-memory draft and nothing touches disk until you save, and undo/redo work across pages [docs/studio.md#what-you-can-do].

**In studio**
1. Click **Undo** in the top bar (as many times as needed) until the function is back.
2. Then click **Save**.

If you had already saved, the previous file is in `.pskit/studio/backups/`."""),

    A(594, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/studio.md#what-you-can-do"],
      user="studio: clone the ingest function incl. triggers as ingest-eu",
      steps=[S("search_docs", query="studio functions table duplicate",
               docs=[D("docs/studio.md", "what-you-can-do", start="| **Functions** |", end="| **Functions** |")])],
      final="""**In studio**
1. Open **Functions**.
2. On the `ingest` row, click *Duplicate* and name the copy `ingest-eu`.
3. Open `ingest-eu` and change what must differ (queue name, environment). Two functions can't share the same `METHOD /path`, so change any HTTP route.
4. Click **Save**."""),

    A(595, provider="gcp", stage="dev", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/studio.md#setup-logs-and-provider-differences", "docs/cli.md#pskit-logs"],
      user="While I test the deployed worker on GCP dev, I want its logs streaming next to it, at level WARNING and above. Studio or CLI, both fine.",
      steps=[S("search_docs", query="live logs function level follow",
               docs=[D("docs/studio.md", "setup-logs-and-provider-differences", start="- **Logs** shows the logs", end="- **Logs** shows the logs")]),
             S("search_docs", query="pskit logs follow function level",
               docs=[D("docs/cli.md", "pskit-logs", start="| `-f, --follow` |", end="| `--level LEVEL` |")])],
      final="""**In studio**
1. Open **Functions** and click `worker`.
2. In its *Logging* section, turn on *Live logs*. Or open **Logs** with gcp / dev in the top bar [docs/studio.md#setup-logs-and-provider-differences].

**In the terminal**
```bash
pskit logs -f --function worker --level WARNING
```
`--level` is the minimum level; `-f` keeps printing new entries (it polls every 3 seconds on clouds) [docs/cli.md#pskit-logs]. GCP logs need `google-cloud-logging` and application-default credentials on your machine."""),

    A(596, provider="azure", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/studio.md#test-functions"],
      user="how i send a real request to my deployed azure http function from studio, not local?",
      steps=[S("search_docs", query="studio send to deployed function http",
               docs=[D("docs/studio.md", "test-functions", end="Turn on *Show the function's logs* to watch it.")])],
      final="""**In studio**
1. Open **Test** with azure / staging in the top bar.
2. Pick the function and its HTTP trigger, and edit the request (path, body).
3. Click **☁ Send to azure / staging**. It sends a real HTTP request to the deployed function (`pskit trigger`) [docs/studio.md#test-functions].
4. Turn on *Show the function's logs* to watch it.

**In the terminal**
```bash
pskit trigger -s staging -f api -e 0 --path /orders
```
Use your function's name. **▶ Run locally** would run it on your machine instead."""),

    A(597, provider="aws", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/cli.md#pskit-settings"],
      user="I saved a dozen named test events in studio on my old laptop. .pskit isn't in git. How do I bring them to my new laptop?",
      steps=[S("search_docs", query="move studio settings test events another machine",
               docs=[D("docs/cli.md", "pskit-settings", end="| `settings import FILE [--dry-run] [--replace] [--yes]` |"),
                     D("docs/cli.md", "pskit-settings", start="| `.pskit/studio/test-events.json` |", end="| `.pskit/studio/test-events.json` |")])],
      final="""Use pskit settings: it moves the saved test events (`.pskit/studio/test-events.json`) and other local settings in one passphrase-encrypted file [docs/cli.md#pskit-settings].

**In the terminal**
On the old laptop:
```bash
pskit settings export -o my.pskit-settings
```
On the new laptop, in the project folder:
```bash
pskit settings import my.pskit-settings --dry-run
pskit settings import my.pskit-settings
```

**In studio**
1. Click **⇅ Settings** in the header (or *Setup & credentials → Move settings to another machine*).
2. Export on the old laptop, import on the new one.

Send the file and the passphrase by different channels."""),

    A(598, provider="gcp", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/cli.md#pskit-trigger"],
      user="my nightly schedule function on gcp, i want run it now one time in the cloud not wait for night",
      steps=[S("search_docs", query="trigger schedule direct gcp",
               docs=[D("docs/cli.md", "pskit-trigger", start="What pskit can send itself", end="| GCP |")])],
      final="""Use `pskit trigger`: schedules are fired by invoking the function with the schedule's input. On GCP that goes through the function URL, so it works for functions with an HTTP deployment [docs/cli.md#pskit-trigger].

**In the terminal**
```bash
pskit trigger -f nightly --direct
pskit logs -f --function nightly
```

**In studio**
1. Open **Test**, pick `nightly` and its schedule trigger (the payload is the schedule's `input`).
2. Click **☁ Send to gcp / dev**.

To try it without the cloud, `pskit invoke -f nightly` runs it locally with the configured input."""),

    A(599, provider="azure", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/cli.md#pskit-trigger"],
      user="can pskit trigger fire my azure timer function now?",
      steps=[S("search_docs", query="trigger azure schedule invoke",
               docs=[D("docs/cli.md", "pskit-trigger", start="What pskit can send itself", end="`oci`, `ibmcloud`, `tccli`, `doctl`, `curl`) and the console steps instead.")])],
      final="""No. On Azure, pskit can send HTTP, Storage queue, Blob and Service Bus events, but not schedule / invoke calls [docs/cli.md#pskit-trigger].

Instead:
1. Print the cloud CLI command and console steps for that trigger:
```bash
pskit trigger --list
```
2. Run the handler locally with its schedule input:
```bash
pskit invoke -f nightly -t schedule
```
3. If the timer logic should be callable on demand, move it into a function with an HTTP route (or a queue trigger) that the timer function also calls."""),

    A(600, provider="aws", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#resources-storage-queues-topics-databases-any-service", "docs/resources.md#secrets"],
      user="Our api and worker functions use an existing ElastiCache Redis (host redis.prod.example.internal, port 6379, auth token in REDIS_TOKEN). How do I describe it so the handlers get the connection details?",
      steps=[S("search_docs", query="external cache resource connection password env",
               docs=[D("docs/resources.md", "resources-storage-queues-topics-databases-any-service", start="  orders-db:", end="    functions: [api, worker]")]),
             S("search_docs", query="resources secrets password_env name of variable",
               docs=[D("docs/resources.md", "secrets", end="`${env:...}` resolves on the machine")])],
      final="""Add it as an external `cache` resource. pskit never creates it; it only hands the connection values to the bound functions as `PSKIT_RESOURCE_*` variables. Put the *name* of the secret variable in `connection`, not the token [docs/resources.md#secrets].

**In code**
```yaml
resources:
  sessions:
    type: cache
    external: true
    connection:
      host: redis.prod.example.internal
      port: 6379
      token_env: REDIS_TOKEN
    functions: [api, worker]
```
```python
from __future__ import annotations

import redis
from py_serverless_kit import resource


def api(event, ctx):
    c = resource("sessions")
    r = redis.Redis.from_url(f"rediss://:{ctx.env[c['token_env']]}@{c['host']}:{c['port']}/0")
    return {"pong": r.ping()}
```
Add `redis` to `requirements.txt`, and set `REDIS_TOKEN` on the functions from your secret store. The Lambdas also need network access to the cache (VPC settings through `functions.<fn>.options`)."""),

    A(601, provider="gcp", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#provider-support"],
      user="i want pskit create a gcs bucket for reports but no function trigger on it. ok on gcp?",
      steps=[S("search_docs", query="managed resource no event standalone gcp",
               docs=[D("docs/resources.md", "provider-support", end="| azure |")])],
      final="""Yes. On GCP a managed resource without any event is supported: pskit creates the bucket [docs/resources.md#provider-support].

**In code**
```yaml
resources:
  reports: {type: storage, name: acme-reports-dev}
```
Bucket names are global on GCP, so pick a unique `name`. Functions read the native name with `resource("reports").native_name` and write with `google-cloud-storage`.

**In studio**
1. Open **Resources** and click **+ Add resource**.
2. Pick storage, keep it managed, enter the name and click **Save**."""),

    A(602, provider="aws", stage="dev", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/cli.md#pskit-resources"],
      user="cli: list buckets/queues pskit made for dev, then push one test message to the jobs resource",
      steps=[S("search_docs", query="resources list send",
               docs=[D("docs/cli.md", "pskit-resources", end="| `send --list` |")])],
      final="""**In the terminal**
```bash
pskit resources list -s dev
pskit resources send jobs -s dev -d '{"order_id": 1}'
```
`list` shows deployed and kept buckets, queues and topics with their status and Terraform address; `send` sends a message to a queue resource [docs/cli.md#pskit-resources]. It uses your machine's AWS credentials."""),

    A(603, provider="azure", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/studio.md#what-you-can-do", "docs/cli.md#pskit-info"],
      user="where in studio can i see what is deployed now, urls and so on?",
      steps=[S("search_docs", query="studio deploy info what is deployed",
               docs=[D("docs/studio.md", "what-you-can-do", start="| **Deploy** |", end="| **Deploy** |")])],
      final="""**In studio**
1. Open **Deploy** with azure / dev in the top bar.
2. Click **Info**. The live log shows the deployed functions, triggers, URLs and resource ids [docs/studio.md#what-you-can-do].

**In the terminal**
```bash
pskit info
```
Before anything is deployed, it shows the configured functions as `not deployed`."""),

    A(604, provider="aws", stage="staging", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/studio.md#what-you-can-do"],
      user="Yesterday a colleague ran a deploy from studio on this machine and it failed. Can I still see that log?",
      steps=[S("search_docs", query="studio deploy live log jobs",
               docs=[D("docs/studio.md", "what-you-can-do", start="| **Deploy** |", end="| **Deploy** |")])],
      final="""Check *Recent jobs* on the **Deploy** page. It lists earlier validate, package, plan, deploy and remove runs, and you can open a job to read its log.

If it's no longer there (for example studio was restarted), run the same command again to see the error:
```bash
pskit deploy -s staging -v
```
`-v` prints the full traceback."""),

    A(605, provider="gcp", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=["docs/studio.md#setup-logs-and-provider-differences", "docs/getting-started.md#6-configure-cloud-credentials"],
      user="studio only: log in to google cloud so i can deploy",
      steps=[S("search_docs", query="studio gcloud login application default",
               docs=[D("docs/studio.md", "setup-logs-and-provider-differences", end="- test the SSH connection of an on-prem deploy.")])],
      final="""**In studio**
1. Open **Setup & credentials** with Google Cloud selected in the top bar.
2. Click **Sign in (gcloud ADC)**. A browser login starts (`gcloud auth application-default login`) [docs/studio.md#setup-logs-and-provider-differences].
3. When it's done, click *Check again*: the credentials check should pass.
4. If the project option is missing, the checks say so; fill in *project* in **Overview & provider** and click **Save**."""),

    A(606, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#events-triggers", "docs/studio.md#setup-logs-and-provider-differences"],
      user="why E-mail (SMTP) trigger is grey in the studio? i'm on azure",
      steps=[S("search_docs", query="smtp trigger support providers",
               docs=[D("docs/events.md", "events-triggers", start="| `smtp` |", end="| `smtp` |"),
                     D("docs/events.md", "events-triggers", start="`smtp` (on premises) runs a function", end="[smtp/README.md](smtp/README.md).")])],
      final="""The `smtp` trigger exists only on premises: it runs a function when mail arrives at an SMTP server pskit sets up on your own server [docs/events.md#events-triggers]. Azure doesn't support it, so studio disables the trigger type; the tooltip names the providers that can run it.

On Azure, use a mail service that calls an HTTP route (a webhook) of your function, or that drops mails into a queue or blob container your function triggers on."""),

    A(607, provider="aws", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/studio.md#what-you-can-do"],
      user="in studio i want to add a new python file app/utils.py for helper code. where? just studio",
      steps=[S("search_docs", query="studio code editor new file",
               docs=[D("docs/studio.md", "what-you-can-do", start="| **Code** |", end="| **Code** |")])],
      final="""**In studio**
1. Open **Code**.
2. Click **New file** and enter `app/utils.py`.
3. Write your helpers in the editor and press Ctrl+S to save the file.
4. Import them in a handler with `from app.utils import ...`.

The editor has Python highlighting, search and tabs [docs/studio.md#what-you-can-do]."""),

    A(608, provider="gcp", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/cli.md#pskit-resources"],
      user="Before deploying, can I check from my machine that the external Pub/Sub topic resource billing-events is reachable with my credentials?",
      steps=[S("search_docs", query="resources check reachable",
               docs=[D("docs/cli.md", "pskit-resources", start="| `check KEY [--json]` |", end="| `check KEY [--json]` |")])],
      final="""Yes, `pskit resources check`. Without an on-prem host it runs a connection check from this machine and exits 1 when it fails [docs/cli.md#pskit-resources].

**In the terminal**
```bash
pskit resources check billing-events
```

**In studio**
1. Open **Resources** and click **Test** on the `billing-events` row.
2. Click **Test connection**.

External resources can be tested right away, without deploying."""),

    A(609, provider="azure", stage="dev", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#provider-support"],
      user="azure: managed queue resource that no event uses, only api sends to it. supported?",
      steps=[S("search_docs", query="azure standalone managed queue resource",
               docs=[D("docs/resources.md", "provider-support", end="| azure |")])],
      final="""Yes. On Azure a managed resource without an event is created: a storage queue for `type: queue` [docs/resources.md#provider-support].

```yaml
resources:
  outbox: {type: queue, functions: [api]}
```
Send to it with `azure-storage-queue` using `resource("outbox").native_name`. On Azure every function sees every binding anyway (app-wide settings), and queue names must be 3–63 lowercase letters, digits and dashes."""),

    A(610, provider="aws", stage="dev", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/cli.md#pskit-trigger"],
      user="After deploying, how do I hit GET /orders/7?verbose=1 on the real API Gateway from the terminal without looking up the URL?",
      steps=[S("search_docs", query="trigger http path deployed api",
               docs=[D("docs/cli.md", "pskit-trigger", end="| `--json` | JSON output |", words=320)])],
      final="""Use `pskit trigger` with `--path`. It sends a real HTTP request to the deployed function's URL, so you don't need to look it up [docs/cli.md#pskit-trigger].

**In the terminal**
```bash
pskit trigger -f api -e 0 --path '/orders/7?verbose=1'
```
`-e 0` is the first trigger in the function's `events:`; use your function name. `pskit info` prints the URL if you want it for curl."""),
]
