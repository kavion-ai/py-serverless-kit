"""Category A (docs Q&A and how-to), batch 42: studio-first how-tos over onprem / aws / gcp / azure. On-prem bind
address and port (Overview & provider), auth on premises, Logs filters, sending a test message to a deployed queue,
host tuning, servers without Python, Package vs Deploy; Lambda memory in the function editor, local SQS tests in
the GUI, API keys on AWS, provider-wide environment, deploy --confirm; GCP project id, GCP logs, a daily schedule in
the wizard, local workflow runs; Azure runtimes, signing in from Setup, switching a function off on Azure.
Pasted errors are real `pskit validate` output from scratch projects. Hand-written; assembled by tools/assemble.py."""

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

CONVERSATIONS = [
    A(811, provider="onprem", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=[f"{PR}#{OP}", f"{ST}#what-you-can-do"],
      user="my onprem functions work on my pc but my colleage cant open the url from his laptop. what do i change in studio?",
      steps=[S("search_docs", query="onprem host other machines bind address",
               docs=[D(PR, OP, start="`options.host` is the bind address **on the target**", end="`options.host` is the bind address **on the target**"),
                     D(PR, OP, start="**Ports closed to this machine.**", end="**Ports closed to this machine.**")])],
      final="""The host listens on `127.0.0.1` by default, so only your own machine reaches it. Use `0.0.0.0` so other machines can call it [docs/providers.md#onprem-on-premises].

**In studio**
1. **Overview & provider**: open the *On-premises options* section.
2. Set **Bind address** to `0.0.0.0`.
3. Press **Save** in the top bar.
4. **Deploy > Deploy** so the host restarts with the new address.

If it still doesn't open, the firewall on your PC probably blocks the port (default 8080): allow it there."""),

    A(812, provider="onprem", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{PR}#{OP}"],
      user="orders -> On-premises [experimental] stage=dev region=local\n  1 function(s), 0 workflow(s)\n  ERROR: [provider.options.port] options.port must be an integer from 1 to 65535\n\ni put 70000 because 8080 is used by tomcat",
      steps=[S("search_docs", query="onprem options port range own port",
               docs=[D(PR, OP, start="- **Dependencies:**", words=60)])],
      final="""Ports only go up to 65535, so 70000 can't work. Pick another free port in that range, for example 8090; each service should have its own port [docs/providers.md#onprem-on-premises].

**In studio**
1. **Overview & provider** > *On-premises options* > **Port**: type `8090`.
2. The error disappears from **Problems**; press **Save**.

**In code**
```yaml
provider:
  name: onprem
  options:
    port: 8090
```"""),

    A(813, provider="onprem", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{PR}#{OP}", "docs/handlers.md#httprequest"],
      user="  ERROR: [functions.api] auth `iam` is not enforced on-premises; use auth: none and check tokens in the handler\n\nhow do i protect the endpoint then?",
      steps=[S("search_docs", query="onprem http auth none check token handler",
               docs=[D(PR, OP, start="| Trigger | Implementation |", end="| http | the host process.")]),
             S("search_docs", query="onprem secrets env_file handlers",
               docs=[D(PR, OP, start="- **Dependencies:**", words=110)]),
             S("search_docs", query="handler read request headers",
               docs=[D("docs/handlers.md", "httprequest", end="| `query` |")])],
      final="""On premises the host has no cloud authorizer: `auth` must be `none`, and you check the token in the handler [docs/providers.md#onprem-on-premises].

**In studio**
1. **Functions**: click `api`, go to the **Triggers** step.
2. In the HTTP trigger set **Auth** to `none`, then **Apply changes** and **Save**.

**In code**
Keep the token in an env file (`API_TOKEN` in `.env.onprem`, git-ignored). The host loads it at start and handlers read it; it is never written to Terraform state.
```yaml
provider:
  name: onprem
  options:
    env_file: .env.onprem
functions:
  api:
    handler: app.handlers.api
    events:
      - http: {path: /orders, method: GET, auth: none}
```
```python
from __future__ import annotations

import os


def api(event, ctx):
    if event.http.headers.get("authorization") != "Bearer " + os.environ["API_TOKEN"]:
        return {"error": "unauthorized"}, 401
    return {"orders": []}
```
`event.http.headers` is case-insensitive [docs/handlers.md#httprequest]."""),

    A(814, provider="onprem", stage="dev", mode="ask", page="Logs", persona="beginner",
      sources=[f"{CLI}#pskit-logs", f"{ST}#setup-logs-and-provider-differences"],
      user="there are too many log lines. how do i see only the errors of my worker function?",
      steps=[S("search_docs", query="logs filter function level error",
               docs=[D(CLI, "pskit-logs", end="| `-q, --grep TEXT` |")])],
      final="""**In studio**
1. **Logs** (you are here).
2. In the toolbar pick **Function** = `worker` and **Level** = `ERROR`.
3. Optional: type a word in *Search messages…* to narrow it more.

**In the terminal**
```bash
pskit logs --function worker --level error
pskit logs -f --function worker --level error
```
`--level` is a minimum level, and `-f` keeps printing new entries [docs/cli.md#pskit-logs]."""),

    A(815, provider="onprem", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=[f"{ST}#test-functions", f"{CLI}#pskit-trigger"],
      user="worker is deployed on my server now. how i put one test msg in its queue for see it working?",
      steps=[S("search_docs", query="send test message deployed queue function",
               docs=[D(ST, "test-functions", end="an uploaded object, a topic message, an HTTP request or an invocation."),
                     D(CLI, "pskit-trigger", start="pskit trigger -f worker -e 0 -d '{\"order_id\": 1}'", end="pskit trigger -f worker -e 0 -d '[{\"id\": 1}, {\"id\": 2}]'")])],
      final="""**In studio**
1. **Test**: pick `worker` and its queue trigger in *1. Choose the event*.
2. *2. Edit the event*: change the sample payload, e.g. `{"order_id": 1}`.
3. *3. Run it*: press **☁ Send to On-premises / prod**. Turn on *Show the function's logs* to watch it run [docs/studio.md#test-functions].

**In the terminal**
```bash
pskit trigger -f worker -e 0 -d '{"order_id": 1}' -s prod
pskit logs -f --function worker -s prod
```
`-e 0` is the first trigger of `worker` [docs/cli.md#pskit-trigger]."""),

    A(816, provider="onprem", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{PR}#{OP}"],
      user="Our on-prem host should run at most 3 workflow runs at the same time and keep only the last 100 finished executions. Where do I set that in studio?",
      steps=[S("search_docs", query="workflow_workers execution_retention onprem",
               docs=[D(PR, OP, start="- **Dependencies:**", words=170)])],
      final="""**In studio**
1. **Overview & provider**: open the *Host tuning* section (it is collapsed).
2. Set **Workflow workers** to `3` (runs executing at once; further starts wait for a worker).
3. Set **Execution retention** to `100` (finished executions kept under the data directory).
4. **Save**, then **Deploy > Deploy** so the host starts with the new values.

They are `provider.options.workflow_workers` and `execution_retention` of the on-prem host [docs/providers.md#onprem-on-premises]."""),

    A(817, provider="onprem", stage="staging", mode="ask", page="YAML", persona="informal_non_native",
      sources=[f"{PR}#{OP}"],
      user="the ssh server dont have python and i cant install it. just yaml pls",
      steps=[S("search_docs", query="server no python ssh deploy",
               docs=[D(PR, OP, start="When the server has **no Python**", end="When the server has **no Python**")])],
      final="""**In code**
```yaml
provider:
  name: onprem
  options:
    deploy:
      method: ssh
      host: 192.0.2.10
      user: pskit
      path: /opt/pskit/orders
      python: bundle
```
With `python: bundle` a portable CPython is fetched at apply and copied with the app [docs/providers.md#onprem-on-premises]."""),

    A(818, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{CLI}#pskit-package", f"{CLI}#pskit-deploy"],
      user="on the deploy page what is the differnce between Package and Deploy? i dont want break something",
      steps=[S("search_docs", query="package vs deploy command",
               docs=[D(CLI, "pskit-package"), D(CLI, "pskit-deploy", end="| `--skip-deps` |")]),
             S("search_docs", query="onprem deploy writes bundle starts host",
               docs=[D(PR, OP, start="`pskit deploy` writes the bundle under", end="`pskit deploy` writes the bundle under")])],
      final="""- **Package** only builds the bundle and `main.tf.json` under `.pskit/onprem-dev/`; nothing is started or changed [docs/cli.md#pskit-package]. Safe to press any time.
- **Deploy** packages, then runs Terraform apply [docs/cli.md#pskit-deploy]. On premises that starts (or restarts) the host with your functions [docs/providers.md#onprem-on-premises].

The same in the terminal:
```bash
pskit package
pskit deploy
```"""),

    A(819, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{CF}#functions"],
      user="my lambda is slow, i want give it more memory. i am on the functions page now",
      steps=[S("search_docs", query="function memory MB setting",
               docs=[D(CF, "functions", start="| Key | Type | Default |", end="| `runtime`, `memory`, `timeout`, `architecture` |")])],
      final="""**In studio**
1. **Functions**: click your function's row.
2. In the **Basics** step, choose a bigger **Memory (MB)**, e.g. `1024` (empty means it inherits the provider's value).
3. Press **Apply changes**, then **Save**.
4. **Deploy > Deploy** to update the Lambda.

**In code**
```yaml
functions:
  api:
    handler: app.handlers.api
    memory: 1024
```
Per-function `memory` overrides the provider's value [docs/configuration.md#functions]."""),

    A(820, provider="aws", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=[f"{ST}#test-functions"],
      user="how i test my sqs function on my pc before deploy, in gui",
      steps=[S("search_docs", query="test queue function locally studio",
               docs=[D(ST, "test-functions")])],
      final="""**In studio**
1. **Test**: pick your function and its queue trigger in *1. Choose the event*.
2. *2. Edit the event*: the payload starts from a queue sample; change the messages.
3. *3. Run it*: press **▶ Run locally**. It runs the handler on this machine with a synthetic event: no cloud, no deploy [docs/studio.md#test-functions].
4. **Save event** keeps the payload for next time."""),

    A(821, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#http"],
      user="billing -> AWS Lambda [stable] stage=dev region=eu-west-1\n  1 function(s), 0 workflow(s)\n  ERROR: [functions.api] API keys are not available on API Gateway HTTP APIs; use jwt or iam",
      steps=[S("search_docs", query="http auth key iam jwt providers",
               docs=[D(EV, "http", start="**Auth support**", end="| `key` |")])],
      final="""`auth: key` works only on Azure and Huawei. On AWS use `iam` or `jwt` [docs/events.md#http].

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
`jwt` needs `authorizer.issuer` and `authorizer.audience`. Use `auth: iam` instead if only AWS callers with IAM credentials call it.

**In studio**
**Functions**: click `api`, **Triggers** step, change **Auth** in the HTTP trigger, then **Apply changes**."""),

    A(822, provider="aws", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=[f"{CF}#functions", f"{ST}#what-you-can-do"],
      user="how can i set one env variable that all my functions get? like APP_MODE=demo",
      steps=[S("search_docs", query="environment variables all functions provider level",
               docs=[D(CF, "functions", start="| `environment`, `tags` | map |", end="| `environment`, `tags` | map |"),
                     D(ST, "what-you-can-do", start="| **Overview & provider** |", end="| **Overview & provider** |")])],
      final="""Put it at provider level; every function gets it, and a function's own `environment` is merged over it [docs/configuration.md#functions].

**In studio**
1. **Overview & provider**: open *Environment variables* (available to every function).
2. Add `APP_MODE` with the value `demo`.
3. **Save**, then **Deploy > Deploy**.

**In code**
```yaml
provider:
  name: aws
  environment:
    APP_MODE: demo
```
For passwords or keys use `${env:NAME}` instead of a literal value."""),

    A(823, provider="aws", stage="prod", mode="ask", page="Deploy", persona="terse_expert",
      sources=[f"{CLI}#pskit-deploy"],
      user="only cli: deploy prod but let me see the terraform plan first, no auto-approve",
      steps=[S("search_docs", query="deploy confirm plan auto-approve",
               docs=[D(CLI, "pskit-deploy")])],
      final="""**In the terminal**
```bash
pskit deploy -s prod --confirm
```
`--confirm` runs `terraform plan -out tfplan` and then applies that plan instead of `-auto-approve` [docs/cli.md#pskit-deploy]."""),

    A(824, provider="gcp", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{PR}#gcp-google-cloud-functions-2nd-gen"],
      user="reports -> Google Cloud Functions [stable] stage=dev region=europe-west1\n  1 function(s), 0 workflow(s)\n  ERROR: [provider.options] GCP needs provider.options.project (the GCP project id)",
      steps=[S("search_docs", query="gcp options project required",
               docs=[D(PR, "gcp-google-cloud-functions-2nd-gen", end="| Trigger | Implementation |")])],
      final="""GCP needs the id of the project to deploy into; `options.project` is required [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

**In studio**
1. **Overview & provider**: open *Google Cloud Functions options*.
2. Fill **Project** with your project id (it offers `${env:GOOGLE_CLOUD_PROJECT}`), then **Save**.

**In code**
```yaml
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT}
```
With the variable form, set `GOOGLE_CLOUD_PROJECT` before validating or deploying, or write the id directly."""),

    A(825, provider="gcp", stage="dev", mode="ask", page="Logs", persona="informal_non_native",
      sources=["docs/dashboard.md#log-sources"],
      user="logs page say it cant read logs of my gcp function. what is missing on my pc?",
      steps=[S("search_docs", query="studio logs page gcp error",
               docs=[D(ST, "setup-logs-and-provider-differences", start="- **Logs** shows the logs", end="- **Logs** shows the logs")]),
             S("search_docs", query="log sources gcp needs google-cloud-logging",
               docs=[D("docs/dashboard.md", "log-sources", end="| Azure |")])],
      final="""Reading GCP logs needs two things on the machine running studio [docs/dashboard.md#log-sources]:

**In the terminal**
```bash
pip install google-cloud-logging
gcloud auth application-default login
```
Then open **Logs** again. **Setup & credentials** can also start the gcloud ADC sign-in for you. GCP logs are read only, and cloud logs lag a few seconds."""),

    A(826, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{ST}#what-you-can-do", f"{EV}#schedule"],
      user="in studio how do i make my report function run every day at 6 in the morning?",
      steps=[S("search_docs", query="studio schedule trigger cron editor",
               docs=[D(ST, "what-you-can-do", start="| **Functions** |", end="| **Functions** |")])],
      final="""**In studio**
1. **Functions**: click the `report` row.
2. Go to the **Triggers** step and, under *Add a trigger*, click **Schedule**.
3. In **Run** pick *At a specific time*, **Repeat** = *Every day*, **At** = `06:00`. The help line shows the cron it writes (`0 6 * * *`).
4. Optional: choose your **Timezone** (GCP supports it).
5. **Apply changes**, **Save**, then **Deploy > Deploy**."""),

    A(827, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{ST}#what-you-can-do", "docs/workflows.md#commands"],
      user="Before deploying the order-pipeline workflow to GCP I want to run it once on my machine with a sample order and see every step. How?",
      steps=[S("search_docs", query="run workflow locally history",
               docs=[D("docs/workflows.md", "commands", end="`workflow run` exits with code 2 when the run fails.")])],
      final="""**In studio**
1. **Deploy**: open the *Run a workflow locally* section.
2. Pick `order-pipeline` in **Workflow**, paste the sample order in **Input (JSON)** and press **Run**. It runs `pskit workflow run --history`, so each step is listed.

**In the terminal**
```bash
pskit workflow run order-pipeline -i '{"order_id": 7, "amount": 30}' --history
```
It runs on the embedded engine on your machine, without GCP; wait states are skipped unless you add `--sleep` [docs/workflows.md#commands]."""),

    A(828, provider="azure", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{PR}#azure-azure-functions"],
      user="  ERROR: [provider.runtime] Azure Functions does not support python3.13; use one of: python3.10, python3.11, python3.12, python3.9\n\nwhere do i change it",
      steps=[S("search_docs", query="azure functions python runtime versions",
               docs=[D(PR, "providers", start="| Provider | Tier |", end="| [`azure`]")])],
      final="""Azure Functions runs Python 3.9 to 3.12 only [docs/providers.md#providers], so pick `python3.12`.

**In studio**
1. **Overview & provider** > *Defaults for every function* > **Runtime**: choose `python3.12`.
2. If a function sets its own runtime, change it too (**Functions** > the function > **Runtime**).
3. **Save**.

**In code**
```yaml
provider:
  name: azure
  runtime: python3.12
```"""),

    A(829, provider="azure", stage="dev", mode="ask", page="Setup", persona="informal_non_native",
      sources=[f"{ST}#setup-logs-and-provider-differences", "docs/getting-started.md#6-configure-cloud-credentials"],
      user="first time azure. how i login and give the subscription from studio, not terminal",
      steps=[S("search_docs", query="studio setup azure login subscription",
               docs=[D(ST, "setup-logs-and-provider-differences", end="  - test the SSH connection of an on-prem deploy.")]),
             S("search_docs", query="azure credentials az login ARM_SUBSCRIPTION_ID",
               docs=[D("docs/getting-started.md", "6-configure-cloud-credentials", end="| `azure` |")])],
      final="""**In studio**
1. **Setup & credentials** with `azure` selected in the top bar. The *Checks* list shows what is missing (Terraform, Azure CLI, credentials).
2. Press **Sign in (az login)** and finish the login in the browser.
3. In *Environment variables* fill `ARM_SUBSCRIPTION_ID` and press **Set for this session**. It lasts until studio stops; nothing is written to disk.
4. The checks run again; deploy from **Deploy** when they are green.

To keep the subscription for every session, put it in the project as `options.subscription_id` on **Overview & provider** [docs/getting-started.md#6-configure-cloud-credentials]."""),

    A(830, provider="azure", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{CF}#switch-something-off-on-one-cloud", f"{ST}#setup-logs-and-provider-differences"],
      user="i deploy the same project to aws and azure. the thumbnails function should not go to azure, only aws. how?",
      steps=[S("search_docs", query="disable function only on one provider",
               docs=[D(CF, "switch-something-off-on-one-cloud")])],
      final="""Switch it off only for Azure; AWS keeps it [docs/configuration.md#switch-something-off-on-one-cloud].

**In studio**
1. **Functions**: click `thumbnails`.
2. In **Basics**, set **Deploy** to *◐ Disabled on Azure Functions* (Azure must be the provider in the top bar).
3. **Apply changes**, **Save**.

**In code**
```yaml
providers:
  azure:
    functions:
      thumbnails: {enabled: false}
```
`pskit validate -p azure` then lists it as a warning. A workflow that calls it would become an error, so disable that workflow on Azure too."""),
]
