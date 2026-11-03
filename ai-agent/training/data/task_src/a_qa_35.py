"""Category A (docs Q&A and how-to), batch 35: aws / gcp / azure. Local development (hot reload, route
priority, workflow endpoint, local environment, log format, env files, headers, in-process invoke), pytest helpers
and stubbed workflow tests, Node.js / TypeScript (runtimes per cloud, one language per service, tsconfig, type
errors, secrets, error names, JavaScript scaffold, skipping npm install, dev rebuilds), trying another cloud.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


LD = "docs/local-development.md"
NJ = "docs/nodejs.md"
GS = "docs/getting-started.md"

CONVERSATIONS = [
    A(671, provider="gcp", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{LD}#pskit-dev-local-server"],
      user="every time i change my handler i stop and start pskit dev again. must i?",
      steps=[S("search_docs", query="pskit dev reload after code change",
               docs=[D(LD, "pskit-dev-local-server", start="**Hot reload:**", end="so there's no restart needed.")])],
      final="""No. Before each request `pskit dev` checks the `.py` files under `package.source`; if any changed, your modules are re-imported, so no restart is needed [docs/local-development.md#pskit-dev-local-server]."""),

    A(672, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=[f"{LD}#pskit-dev-local-server"],
      user="routes GET /items/new and GET /items/{id}. pskit dev: which one gets /items/new?",
      steps=[S("search_docs", query="pskit dev static routes parameterised priority",
               docs=[D(LD, "pskit-dev-local-server", start="| Endpoint | What it does |", end="| your `http` routes |")])],
      final="""`/items/new` goes to the static route: in `pskit dev`, static routes win over parameterised ones [docs/local-development.md#pskit-dev-local-server]. An unknown path returns 404 with the route list.

Note that `pskit invoke -f <fn>` calls the function directly, so it doesn't test routing; use `pskit dev` and curl for that."""),

    A(673, provider="azure", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{LD}#pskit-dev-local-server"],
      user="Our front-end developer runs pskit dev and wants to start the order-pipeline workflow from her browser app with a POST and see the result. Is there an endpoint for that?",
      steps=[S("search_docs", query="pskit dev workflow endpoint post",
               docs=[D(LD, "pskit-dev-local-server", start="| `POST /__pskit/workflows/<workflow>` |", end="| `POST /__pskit/workflows/<workflow>` |")])],
      final="""Yes: `POST /__pskit/workflows/<workflow>` runs the workflow on the embedded engine with the body as input [docs/local-development.md#pskit-dev-local-server].

**In the terminal**
```bash
pskit dev
curl -X POST localhost:3000/__pskit/workflows/order-pipeline -d '{"amount": 50}'
```
It answers `{"status": "SUCCEEDED", "output", "history"}`, or 500 with `FAILED`. This endpoint exists only in `pskit dev`, not on the deployed Azure app."""),

    A(674, provider="gcp", stage="dev", mode="ask", page="Code", persona="pasted_error",
      sources=[f"{LD}#environment"],
      user="KeyError: 'PSKIT_GCP_PROJECT'\n\nonly when i run pskit invoke locally. on gcp it works. my code does if os.environ['PSKIT_PROVIDER'] == 'gcp' somewhere too",
      steps=[S("search_docs", query="local run environment variables PSKIT_PROVIDER local",
               docs=[D(LD, "environment", end="`invoke()` calls between functions run in-process locally.")])],
      final="""Local runs set `PSKIT_PROVIDER=local` and `PSKIT_REGION=local`, plus `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_FUNCTION` and `PSKIT_HANDLER`. `PSKIT_GCP_PROJECT` only exists on GCP [docs/local-development.md#environment].

Fix: give it a local value in `.env` (loaded by `pskit invoke` and `pskit dev`):
```bash
# .env
PSKIT_GCP_PROJECT=my-project
```
or read it with a default in code:
```python
project = ctx.env.get("PSKIT_GCP_PROJECT", "my-project")
```
Your `PSKIT_PROVIDER == "gcp"` branch is skipped locally, because the value is `local` there."""),

    A(675, provider="aws", stage="dev", mode="ask", page="Logs", persona="terse_expert",
      sources=[f"{LD}#environment"],
      user="local invoke logs are plain text. want the json lines like in cloudwatch",
      steps=[S("search_docs", query="local logs text format json",
               docs=[D(LD, "environment", start="`invoke()` calls between functions run in-process locally.")])],
      final="""Set `PSKIT_LOG_FORMAT=json`; local runs use the readable `text` format by default [docs/local-development.md#environment].

**In the terminal**
```bash
PSKIT_LOG_FORMAT=json pskit invoke -f api
```
Or put `PSKIT_LOG_FORMAT=json` in `.env`."""),

    A(676, provider="azure", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=[f"{LD}#testing-with-pytest"],
      user="In pytest I want to check that our process-jobs queue worker marks only the bad record as failed. Code only, please.",
      steps=[S("search_docs", query="pytest queue partial failure build_event LocalRunner",
               docs=[D(LD, "testing-with-pytest", words=300)])],
      final="""**In code**
```python
# tests/test_worker.py
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, build_event

runner = LocalRunner(Project.load())


def test_queue_partial_failure():
    result = runner.invoke("process-jobs", build_event("queue", [{"ok": 1}, "not-json"]))
    assert result.failed == ["local-1"]
```
`build_event("queue", [...])` turns the list into records; in the docs example the second (bad) record is `local-1` [docs/local-development.md#testing-with-pytest]. The handler must return a `BatchResult`."""),

    A(677, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{LD}#on-premises-is-a-deploy-not-pskit-dev", f"{LD}#testing-with-pytest"],
      user="Our workflow's tasks call external payment APIs. For unit tests I want to run the workflow with fake task results. Does pskit support stubbing the tasks?",
      steps=[S("search_docs", query="unit test workflow stub tasks",
               docs=[D(LD, "on-premises-is-a-deploy-not-pskit-dev", start="To unit-test a workflow with stubbed tasks")])],
      final="""Yes. Use `py_serverless_kit.runtime.workflow.WorkflowEngine(definition, task_runner)` directly; your `task_runner` returns the fake result for each task [docs/local-development.md#on-premises-is-a-deploy-not-pskit-dev].

`examples/14-testing` shows it, together with a CI workflow that also runs `pskit validate` against several providers.

For a run with the real handlers, `runner.run_workflow("order-pipeline", {...})` returns `{"output", "history"}` and raises `WorkflowFailed` on failure."""),

    A(678, provider="aws", stage="dev", mode="ask", page="none", persona="informal_non_native",
      sources=[f"{LD}#pskit-dev-local-server", "docs/cli.md#pskit-invoke"],
      user="terminal only: i keep local vars in .env.local not .env. how pskit dev and invoke use it",
      steps=[S("search_docs", query="pskit dev env-file",
               docs=[D(LD, "pskit-dev-local-server", end="On startup it prints every route:", words=80)]),
             S("search_docs", query="pskit invoke env-file option",
               docs=[D("docs/cli.md", "pskit-invoke", start="| `--env-file", end="| `--env-file")])],
      final="""**In the terminal**
```bash
pskit dev --env-file .env.local
pskit invoke -f api --env-file .env.local
```
Both load `.env` by default; `--env-file` picks another file [docs/local-development.md#pskit-dev-local-server]."""),

    A(679, provider="azure", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=[f"{NJ}#choosing-the-runtime"],
      user="can i use nodejs24 for my azure functions with pskit?",
      steps=[S("search_docs", query="nodejs runtimes azure functions",
               docs=[D(NJ, "choosing-the-runtime", end="| Azure Functions |")])],
      final="""No. On Azure Functions pskit supports `nodejs18`, `nodejs20` and `nodejs22` [docs/nodejs.md#choosing-the-runtime].

**In code**
```yaml
provider:
  name: azure
  runtime: nodejs22
```

**In studio**
1. Open **Overview & provider**.
2. Pick `nodejs22` as *Runtime* and click **Save**.

Dependencies from `package.json` are installed by Azure's remote (Oryx) build."""),

    A(680, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{NJ}#limitations", f"{NJ}#choosing-the-runtime"],
      user="We have a Python service on GCP and want to add one function written in TypeScript to it. Can one pskit service mix both?",
      steps=[S("search_docs", query="mix python and nodejs functions one service",
               docs=[D(NJ, "limitations")])],
      final="""No. A service is either Python or Node.js [docs/nodejs.md#limitations].

Instead:
1. Create a second service for the TypeScript function:
```bash
pskit init ts-part -p gcp --typescript
```
2. Let the two services talk over HTTP or a queue (for example a Pub/Sub topic both use as a resource)."""),

    A(681, provider="aws", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=[f"{NJ}#typescript"],
      user="does pskit keep my tsconfig strict + paths when it compiles?",
      steps=[S("search_docs", query="typescript tsconfig pskit compile overrides",
               docs=[D(NJ, "typescript", end="* Type errors fail the build")])],
      final="""Yes. With a `tsconfig.json`, pskit extends it and only overrides the output settings (`outDir`, `rootDir`, `noEmit: false`), so `strict`, `target` and `paths` apply [docs/nodejs.md#typescript]. Without one it compiles to CommonJS / ES2022. Type errors fail the build."""),

    A(682, provider="azure", stage="dev", mode="ask", page="Code", persona="pasted_error",
      sources=[f"{NJ}#typescript"],
      user="error TS2580: Cannot find name 'process'. Do you need to install type definitions for node?\n\npskit package fails with this",
      steps=[S("search_docs", query="typescript process types node build fails",
               docs=[D(NJ, "typescript", start="* Type errors fail the build", end="`npm install --save-dev @types/node`.")])],
      final="""Type errors fail the build, and Node.js APIs like `process`, `Buffer` and `fs` need their types in TypeScript [docs/nodejs.md#typescript].

**In the terminal**
```bash
npm install --save-dev @types/node
pskit package
```"""),

    A(683, provider="gcp", stage="prod", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{NJ}#secrets"],
      user="in node handler how i read a secret like get_secret in python?",
      steps=[S("search_docs", query="nodejs getSecret",
               docs=[D(NJ, "secrets")])],
      final="""Use `getSecret(name, field?, { store, default })`; it works like the Python call [docs/nodejs.md#secrets].

**In code**
```ts
import { getSecret } from "pskit";

export async function api() {
  const apiKey = await getSecret("stripe", "api_key");
  return { loaded: Boolean(apiKey) };
}
```
The store comes from environment variables, as in Python (Vault / OpenBao, AWS Secrets Manager, or environment variables)."""),

    A(684, provider="aws", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{NJ}#handlers"],
      user="Our task functions are TypeScript. In the workflow I want catch: [PaymentDeclined]. What do I throw in the handler so the name matches?",
      steps=[S("search_docs", query="nodejs workflow retry catch error class name",
               docs=[D(NJ, "handlers", start="The API mirrors the [Python handler API]")])],
      final="""Retry and catch rules match the error's class name, so declare a class with that name and throw it [docs/nodejs.md#handlers].

**In code**
```ts
class PaymentDeclined extends Error {}

export async function charge(event, ctx) {
  const order = event.data;
  if (order.amount > 1000) throw new PaymentDeclined("card declined");
  return { charged: true };
}
```
```yaml
workflows:
  order-pipeline:
    start_at: Charge
    states:
      Charge:
        type: task
        function: charge
        catch:
          - errors: [PaymentDeclined]
            next: NotifyDeclined
        end: true
      NotifyDeclined: {type: task, function: notify-declined, end: true}
```"""),

    A(685, provider="aws", stage="dev", mode="ask", page="none", persona="beginner",
      sources=[f"{NJ}#nodejs-and-typescript", "docs/cli.md#pskit-init-directory"],
      user="i want a new lambda project in plain javascript, node 22, no typescript. what command?",
      steps=[S("search_docs", query="pskit init javascript nodejs runtime",
               docs=[D(NJ, "nodejs-and-typescript", end="cd my-api && pskit dev")])],
      final="""**In the terminal**
```bash
pskit init my-api -p aws --runtime nodejs22
cd my-api
pskit dev
```
With a `nodejs` runtime and no `--typescript`, the handlers are JavaScript [docs/nodejs.md#nodejs-and-typescript]."""),

    A(686, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="terse_expert",
      sources=[f"{NJ}#dependencies-and-packaging"],
      user="package the node service without running npm install, just to inspect the bundle",
      steps=[S("search_docs", query="package skip npm install node",
               docs=[D(NJ, "dependencies-and-packaging", end="it has no dependencies.")])],
      final="""**In the terminal**
```bash
pskit package --skip-deps
```
`--skip-deps` skips the install [docs/nodejs.md#dependencies-and-packaging]. To turn it off in config instead, set `package.node.install: false`. On GCP Cloud Build installs `package.json` dependencies during deploy anyway."""),

    A(687, provider="azure", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{GS}#8-switch-cloud"],
      user="Our project runs on AWS. I want to try deploying the same code to Azure without breaking the AWS setup in pskit.yml. What's the cleanest way?",
      steps=[S("search_docs", query="switch cloud per provider overrides",
               docs=[D(GS, "8-switch-cloud")])],
      final="""The code doesn't change. Put the Azure settings in a per-provider block and select it with `--provider` [docs/getting-started.md#8-switch-cloud].

**In code**
```yaml
providers:
  azure:
    region: westeurope
    options:
      subscription_id: ${env:ARM_SUBSCRIPTION_ID}
```

**In the terminal**
```bash
pskit providers
pskit validate --provider azure
pskit deploy --provider azure
```
Validate first: it lists what Azure doesn't support (for example `auth: jwt`). The AWS deploy keeps its own state in `.pskit/aws-<stage>/`."""),

    A(688, provider="gcp", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{NJ}#local-development"],
      user="my ts project with pskit dev, i change .ts file, does dev server see it?",
      steps=[S("search_docs", query="nodejs pskit dev rebuild ts change",
               docs=[D(NJ, "local-development", end="changes.")])],
      final="""Yes. pskit builds the service into `.pskit/local-node/` (compiling TypeScript), and the dev server rebuilds and restarts the worker when a `.ts`, `.js` or `.json` file changes [docs/nodejs.md#local-development].

Run `npm install` first if you have dependencies; they resolve from the project's `node_modules`."""),

    A(689, provider="aws", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=[f"{LD}#pskit-invoke-and-pskit-workflow-run"],
      user="Our admin route reads the Authorization header in the handler. How do I pass a header and a query string when I invoke it locally?",
      steps=[S("search_docs", query="pskit invoke header query path",
               docs=[D(LD, "pskit-invoke-and-pskit-workflow-run")])],
      final="""**In the terminal**
```bash
pskit invoke -f admin --path "/admin?verbose=1" -H "Authorization: Bearer x"
```
`--path` sets the path and query; `-H` adds a header [docs/local-development.md#pskit-invoke-and-pskit-workflow-run]. Use a fake token locally.

**In studio**
1. Open **Test**, pick `admin` and its HTTP trigger.
2. Edit the request (path, headers) and click **▶ Run locally**."""),

    A(690, provider="azure", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=[f"{LD}#environment"],
      user="my orders function calls invoke('billing', ...). when i test orders locally, does it call billing on azure?",
      steps=[S("search_docs", query="invoke between functions locally in-process",
               docs=[D(LD, "environment", start="`invoke()` calls between functions run in-process locally.")])],
      final="""No. Locally, `invoke()` calls between functions run in-process: `billing` runs on your machine, nothing goes to Azure [docs/local-development.md#environment].

```bash
pskit invoke -f orders -d '{"id": 1}'
```
After deploying, `invoke()` goes to the deployed `billing` function."""),
]
