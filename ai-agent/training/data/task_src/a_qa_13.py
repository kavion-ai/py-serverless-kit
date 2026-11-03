"""Category A (docs Q&A and how-to), batch 13: general docs asked from an on-premises project (events, configuration
overrides and variables, handler API, CLI). Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


EV = "docs/events.md"
CF = "docs/configuration.md"
HD = "docs/handlers.md"
CLI = "docs/cli.md"

YML_7MIN = """service: reports
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8080}
functions:
  sync:
    handler: app.handlers.sync
    events:
      - schedule: 7 minutes
"""

YML_IAM = """service: orders
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8080}
functions:
  api:
    handler: app.handlers.api
    events:
      - http: {path: /orders, method: POST, auth: iam}
"""

HANDLERS = """from __future__ import annotations


def sync(event, ctx):
    return {"ok": True}


def api(event, ctx):
    return {"ok": True}
"""

CONVERSATIONS = [
    A(241, provider="onprem", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=[f"{EV}#schedule"],
      project=dict(files={"pskit.yml": YML_7MIN, "app/__init__.py": "", "app/handlers.py": HANDLERS}),
      user="i need run sync every 7 minutes. somebody say cron cant do 7 minute. on my onprem it work?",
      steps=[S("search_docs", query="schedule rate 7 minutes on-prem cron",
               docs=[D(EV, "schedule", start="| onprem | in-process scheduler |", end="Azure ignores it with a warning.")]),
             S("validate", say="Let me check it on your project.")],
      final="""Yes. On-prem the scheduler runs rates in seconds, so `7 minutes` is valid there [docs/events.md#schedule]. Your project validates for onprem.

On cron-only clouds a rate like `7 minutes` can fail, so use a divisor of 60 minutes there if you deploy elsewhere too.

**In code**
```yaml
functions:
  sync:
    handler: app.handlers.sync
    events:
      - schedule: 7 minutes
```

**In studio**
1. Open **Functions** and edit `sync`.
2. In **Add a trigger**, pick *Schedule*, then *Every…* with interval 7 and minutes."""),

    A(242, provider="onprem", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=[f"{EV}#queue"],
      user="queue options on onprem: fifo, batch_window, partial batch failures — honoured or ignored?",
      steps=[S("search_docs", query="queue options on premises fifo batch_window",
               docs=[D(EV, "queue", start="On premises the same options", end="`existing: true` waits for that directory.")])],
      final="""All honoured. On premises a file broker implements `batch_size`, `batch_window`, visibility, `dead_letter`, `max_receive` and `fifo`, and a `BatchResult` retries only the failed message ids, as on AWS [docs/events.md#queue].

```yaml
functions:
  worker:
    handler: app.handlers.worker
    events:
      - queue: {name: jobs, batch_size: 20, batch_window: 5, fifo: true, dead_letter: jobs-dlq, max_receive: 3}
```"""),

    A(243, provider="onprem", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{CF}#stages-per-stage-overrides", f"{CF}#precedence-later-wins"],
      user="Same on-prem project for dev and prod: dev listens on port 8080 on this laptop, prod on port 9000 on app-1 with more memory. One pskit.yml?",
      steps=[S("search_docs", query="per-stage overrides stages block",
               docs=[D(CF, "stages-per-stage-overrides")]),
             S("search_docs", query="precedence stage provider override",
               docs=[D(CF, "precedence-later-wins")])],
      final="""Yes, with a `stages:` block. `stages.<active stage>` is merged over the base config, and dicts are deep-merged [docs/configuration.md#stages-per-stage-overrides].

**In code**
```yaml
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8080
stages:
  prod:
    provider:
      memory: 1024
      options:
        host: 0.0.0.0
        port: 9000
        deploy: {server: app-1}
```
Lists are replaced, not appended. CLI flags (`--stage`, ...) come last [docs/configuration.md#precedence-later-wins].

**In the terminal**
```bash
pskit validate -s prod
pskit deploy -s prod
```"""),

    A(244, provider="onprem", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{CF}#precedence-later-wins"],
      user="Our prod stage uses an S3 state backend for AWS. When we deploy prod with -p onprem we want local state instead. Where does that override go?",
      steps=[S("search_docs", query="stage provider override state backend onprem",
               docs=[D(CF, "precedence-later-wins")])],
      final="""Under `stages.prod.providers.onprem`. That layer is meant for exactly this: a stage that must differ for one target, such as a cloud state backend on `prod` and local state for `onprem` [docs/configuration.md#precedence-later-wins].

**In code**
```yaml
stages:
  prod:
    provider:
      state:
        backend: s3
        config: {bucket: my-tf-state, key: shop-prod.tfstate, region: eu-west-1}
    providers:
      onprem:
        state:
          backend: null
```

**In the terminal**
```bash
pskit validate -s prod -p onprem
```"""),

    A(245, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{CF}#switch-something-off-on-one-cloud"],
      user="one function uses aws only stuff. how do i keep it in the project but not deploy it to onprem?",
      steps=[S("search_docs", query="disable function on one provider",
               docs=[D(CF, "switch-something-off-on-one-cloud")])],
      final="""Turn it off only for onprem with `enabled: false` under `providers.onprem` [docs/configuration.md#switch-something-off-on-one-cloud].

**In code**
```yaml
providers:
  onprem:
    functions:
      billing-sync: {enabled: false}
```
`pskit validate` reports it as a warning. A workflow that calls a disabled function is an error, so disable that workflow too.

**In studio**
1. Open **Functions** and edit the function.
2. Disable it for the current provider only (onprem), then **Save**. The **Deploy** page also lists what won't run on the target and offers to disable it there."""),

    A(246, provider="onprem", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=[f"{CF}#variables"],
      user="port from env PORT, default 8080 if unset. syntax?",
      steps=[S("search_docs", query="variables env default",
               docs=[D(CF, "variables", end="Variables can nest across passes")])],
      final="""The syntax is `${env:NAME, default}` [docs/configuration.md#variables], but not for the port: environment values are strings, so `port: ${env:PORT, 8080}` fails validate with `options.port must be an integer from 1 to 65535`.

For a number, use a `custom` value (or a literal port per stage):
```yaml
custom:
  port: 8080
provider:
  name: onprem
  options:
    port: ${self:custom.port}
```
`${env:NAME}` with a default is fine for string options such as hosts or paths."""),

    A(247, provider="onprem", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=[f"{CF}#variables"],
      user="i have list of allowed ips in allowed.json. can pskit.yml read this file into environment?",
      steps=[S("search_docs", query="variables file json",
               docs=[D(CF, "variables", end="Variables can nest across passes")])],
      final="""Yes, with `${file(...)}`. The path is relative to pskit.yml; `.json` and `.yml` files are parsed, other files are read as stripped text [docs/configuration.md#variables].

**In code**
```yaml
custom:
  allowed: ${file(allowed.json)}
functions:
  api:
    handler: app.handlers.api
    environment:
      ALLOWED_IPS: ${file(allowed.txt)}
```
Environment values are strings, so for an environment variable use a text file (for example `allowed.txt` with comma-separated IPs) and split it in the handler. The parsed JSON form is handy under `custom:` and with `${self:custom.allowed}`."""),

    A(248, provider="onprem", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{EV}#schedule", "docs/providers.md#onprem-on-premises"],
      user="Our on-prem server runs in UTC. A report must run at 08:30 Berlin time all year, including summer time. Does the on-prem scheduler handle the timezone?",
      steps=[S("search_docs", query="schedule timezone on premises",
               docs=[D(EV, "schedule", start="- schedule: 5 minutes", end="name: morning-report", words=120)]),
             S("search_docs", query="onprem schedule IANA timezone missing warns",
               docs=[D("docs/providers.md", "onprem-on-premises", start="| schedule | in-process rate", end="| schedule | in-process rate")])],
      final="""Yes. Set `timezone` on a cron schedule. On-prem cron is evaluated in that IANA zone; a timezone that's missing on the machine warns and is evaluated in UTC [docs/providers.md#onprem-on-premises].

**In code** [docs/events.md#schedule]
```yaml
functions:
  report:
    handler: app.handlers.report
    events:
      - schedule:
          cron: "30 8 * * *"
          timezone: Europe/Berlin
          input: {report: daily}
```
The handler gets `event.data == {"report": "daily"}`.

**In studio**
In **Functions**, pick *Schedule* → *At a specific time*, set 08:30 and *Timezone* Europe/Berlin."""),

    A(249, provider="onprem", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=[f"{HD}#batchresult"],
      user="handler code only: queue worker that retries only failed records on onprem",
      steps=[S("search_docs", query="BatchResult retry failed records",
               docs=[D(HD, "batchresult")])],
      final="""**In code**
```python
from __future__ import annotations

from py_serverless_kit import BatchResult


def worker(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            order = record.json()
            ctx.logger.info("order", extra={"id": order["id"]})
        except Exception:
            result.fail(record)
    return result
```
On premises the host retries only the failed message ids and moves a message to `dead_letter` after `max_receive` [docs/handlers.md#batchresult]. Redelivery is normal, so keep the handler idempotent."""),

    A(250, provider="onprem", stage="staging", mode="ask", page="Code", persona="beginner",
      sources=[f"{HD}#context"],
      user="how does my function know if it runs in staging or prod?",
      steps=[S("search_docs", query="context stage provider attributes",
               docs=[D(HD, "context")])],
      final="""Read `ctx.stage`. The context also has `function`, `provider`, `service` and `region` [docs/handlers.md#context].

**In code**
```python
from __future__ import annotations


def api(event, ctx):
    ctx.logger.info("where", extra={"stage": ctx.stage, "provider": ctx.provider})
    return {"stage": ctx.stage, "service": ctx.service}
```
For values that differ per stage (URLs, limits), it's often cleaner to set them under `stages:` in pskit.yml and read them from `ctx.env`."""),

    A(251, provider="onprem", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{HD}#returning-a-response"],
      user="how my http handler return 201 with a header location?",
      steps=[S("search_docs", query="return status code headers http handler",
               docs=[D(HD, "returning-a-response", end="Response.no_content()")])],
      final="""Return a tuple `(body, status, headers)`, or use `Response.json` [docs/handlers.md#returning-a-response].

**In code**
```python
from __future__ import annotations

from py_serverless_kit import Response


def create(event, ctx):
    order_id = 7
    return {"id": order_id}, 201, {"location": f"/orders/{order_id}"}


def create_v2(event, ctx):
    return Response.json({"id": 7}, status=201, headers={"location": "/orders/7"})
```
Both give the same response. `None` gives 204, a `dict` gives JSON 200."""),

    A(252, provider="onprem", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=[f"{HD}#errors"],
      user="return 422 with field details from a handler, and what does an uncaught exception return?",
      steps=[S("search_docs", query="http error 422 details exception 500",
               docs=[D(HD, "errors", end="(never in production).")])],
      final="""**In code**
```python
from __future__ import annotations

from py_serverless_kit import UnprocessableEntity


def create(event, ctx):
    body = event.http.json(default={})
    if not body.get("amount"):
        raise UnprocessableEntity("invalid order", details={"field": "amount"})
    return {"ok": True}
```
That returns `422 {"error": "invalid order", "status": 422, "details": {"field": "amount"}}`. Any other exception becomes `500 {"error": "Internal Server Error", "status": 500, "request_id": ...}` and the traceback goes to the logs. `PSKIT_DEBUG=1` adds the exception text to the body; never use it in production [docs/handlers.md#errors]."""),

    A(253, provider="onprem", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": YML_IAM, "app/__init__.py": "", "app/handlers.py": HANDLERS}),
      user="On AWS our POST /orders route uses auth: iam. Can I keep that when I deploy the same function on-prem?",
      steps=[S("search_docs", query="http auth on premises iam",
               docs=[D("docs/providers.md", "onprem-on-premises", start="| http | the host process.", end="| http | the host process.")]),
             S("validate", say="Here's what validate says for your project on onprem.")],
      final="""No. On-prem the HTTP trigger runs in the host process, and `auth` must be `none`. Validate fails with: `auth `iam` is not enforced on-premises; use auth: none and check tokens in the handler` [docs/providers.md#onprem-on-premises].

Keep `iam` for AWS and override it for onprem:

**In code**
```yaml
providers:
  onprem:
    functions:
      api:
        events: [{http: {path: /orders, method: POST, auth: none}}]
```
Then check a token in the handler:
```python
from __future__ import annotations

from py_serverless_kit import Unauthorized


def api(event, ctx):
    if event.http.headers.get("authorization") != "Bearer " + ctx.env["ORDERS_API_TOKEN"]:
        raise Unauthorized("missing or wrong token")
    return {"ok": True}
```
Set `ORDERS_API_TOKEN` in the env file, not in pskit.yml."""),

    A(254, provider="onprem", stage="dev", mode="ask", page="none", persona="beginner",
      sources=[f"{CLI}#pskit-init-directory"],
      user="how do i start a brand new project for on-prem with a queue and a schedule already inside?",
      steps=[S("search_docs", query="pskit init template provider",
               docs=[D(CLI, "pskit-init-directory")])],
      final="""Use `pskit init` with `-p onprem` and the `events` template (http plus schedule, queue and storage) [docs/cli.md#pskit-init-directory].

**In the terminal**
```bash
pskit init orders -p onprem -t events
cd orders
pskit validate
```
Use `-t full` for everything, including a workflow.

**In studio**
Run `pskit studio --open` in an empty folder. The **New project** page asks for the service name, the provider (pick on-premises) and a starter template."""),

    A(255, provider="onprem", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/local-development.md#pskit-dev-local-server", "docs/local-development.md#environment"],
      user="pskit dev with secrets from .env.local instead of .env?",
      steps=[S("search_docs", query="pskit dev env file",
               docs=[D("docs/local-development.md", "pskit-dev-local-server", words=150),
                     D("docs/local-development.md", "environment")])],
      final="""Pass `--env-file` [docs/local-development.md#environment]:
```bash
pskit dev --env-file .env.local --port 3000
pskit invoke -f api --env-file .env.local
```
Keep the file git-ignored. `.env` files are also excluded from deployment bundles. For the deployed on-prem host, secrets go in `provider.options.env_file` instead."""),

    A(256, provider="onprem", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/local-development.md#testing-with-pytest"],
      user="We want pytest tests for our handlers that run in CI without starting the on-prem host. Is there a helper to build fake events?",
      steps=[S("search_docs", query="pytest handlers test events",
               docs=[D("docs/local-development.md", "testing-with-pytest", words=300)])],
      final="""Yes. `py_serverless_kit.local` has `LocalRunner` (an in-process runner), `http_event` and `build_event`. Tests run without a host or a cloud [docs/local-development.md#testing-with-pytest].

**In code**
```python
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, build_event, http_event

runner = LocalRunner(Project.load())


def test_get_item():
    resp = runner.invoke("get-item", http_event("GET", "/items/1"))
    assert resp.status == 200


def test_queue_partial_failure():
    result = runner.invoke("process-jobs", build_event("queue", [{"ok": 1}, "not-json"]))
    assert result.failed == ["local-1"]
```
`runner.run_workflow(name, data)` runs a workflow and returns `{"output", "history"}`.

**In the terminal**
```bash
pytest
```
For an end-to-end check of one function through pskit's runtime:
```bash
pskit invoke -f worker -t queue -d '[{"order_id": 1}]'
```"""),

    A(257, provider="onprem", stage="dev", mode="auto", page="Test", persona="terse_expert",
      sources=[f"{CLI}#pskit-invoke"],
      user="terminal only: local invoke of worker with 2 queue messages, and of on-upload as a storage event",
      steps=[S("search_docs", query="pskit invoke queue storage data",
               docs=[D(CLI, "pskit-invoke")])],
      final="""**In the terminal**
```bash
pskit invoke -f worker -t queue -d '[{"order_id": 1}, {"order_id": 2}]'
pskit invoke -f on-upload -t storage -d '{"bucket": "uploads", "key": "in/a.csv"}'
```
`-d` takes JSON, `@file.json` or plain text. A `BatchResult` prints as `batchItemFailures` [docs/cli.md#pskit-invoke]. This runs locally, without deploying."""),

    A(258, provider="onprem", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=[f"{CLI}#pskit-trigger"],
      user="after deploy to the onprem host, which trigger types can `pskit trigger` actually fire?",
      steps=[S("search_docs", query="pskit trigger on premises supported",
               docs=[D(CLI, "pskit-trigger", start="What pskit can send itself", end="| On premises |")])],
      final="""All of them: HTTP, queue, storage, topic, and schedule / invoke [docs/cli.md#pskit-trigger].

```bash
pskit trigger --list
pskit trigger -f worker -e 0 -d '{"order_id": 1}'
pskit trigger -f tick --direct
pskit logs -f --function worker
```
`-e` picks the trigger by its position in `events:`. A schedule is fired by invoking the function with the schedule's input."""),

    A(259, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{CLI}#pskit-info"],
      user="after deploy, how do i see the url of my functions on the server?",
      steps=[S("search_docs", query="pskit info urls endpoint",
               docs=[D(CLI, "pskit-info")])],
      final="""Run `pskit info` [docs/cli.md#pskit-info]:

**In the terminal**
```bash
pskit info -s prod
```
It shows the deployed functions, triggers and URLs. `--json` gives a machine-readable record.

**In studio**
Open **Deploy** and click **Info**.

If the URL shows `127.0.0.1` but users reach the server by a name, set `provider.options.advertise` and deploy again."""),

    A(260, provider="onprem", stage="dev", mode="ask", page="Setup", persona="informal_non_native",
      sources=[f"{CLI}#pskit-doctor"],
      user="before first onprem deploy, how i check my pc have everything (ssh, docker, terraform)?",
      steps=[S("search_docs", query="pskit doctor checks",
               docs=[D(CLI, "pskit-doctor", words=200)])],
      final="""Use `pskit doctor` [docs/cli.md#pskit-doctor].

**In the terminal**
```bash
pskit doctor -p onprem
```

**In studio**
Open **Setup & credentials**. It runs the same checks for the provider in the top bar: Terraform and, for on premises, ssh/scp, Docker and the key file. Each problem shows a download link and steps for Windows, macOS or Linux. **Test SSH connection** checks the login to your server."""),
]
