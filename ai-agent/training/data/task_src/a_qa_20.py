"""Category A (docs Q&A and how-to), batch 20: Terraform behaviour of on-prem deploys (terraform_data, state per
stage, pskit tf, --confirm / --upgrade, terraform.extra) and stages / overrides / extends / variables / hooks for
on-prem projects. Error texts were checked with real `pskit validate` runs. Hand-written; assembled by
tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


PR = "docs/providers.md"
OP = "onprem-on-premises"
CF = "docs/configuration.md"
AR = "docs/architecture.md"
CLI = "docs/cli.md"
PREC = "precedence-later-wins"

TFDATA = D(PR, OP, start="- **Terraform:**", end="- **Terraform:**")
RES = D(PR, OP, start="**Resources:** `terraform_data.host`", end="**Resources:** `terraform_data.host`")

CONVERSATIONS = [
    A(381, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{PR}#{OP}", f"{AR}#deploy-pipeline"],
      user="i opened .pskit/onprem-dev/main.tf.json and see terraform_data. what is that, and where is my code in it?",
      steps=[S("search_docs", query="onprem terraform_data main.tf.json",
               docs=[TFDATA, RES])],
      final="""`terraform_data` is a resource built into Terraform, so on-prem needs no provider plugin. pskit creates one, `terraform_data.host`. Creating it runs `onprem_deploy.py apply`, which starts or updates the host; destroying it runs `onprem_deploy.py destroy` [docs/providers.md#onprem-on-premises].

Your code isn't inside `main.tf.json`. It's in the bundle next to it, under `.pskit/onprem-dev/`, and the deploy script copies or starts that. You don't edit these files; pskit writes them again on every package or deploy."""),

    A(382, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="terse_expert",
      sources=[f"{CLI}#pskit-tf----args", "docs/placement.md#deploy-urls-and-load-balancers"],
      user="terminal only: list the terraform state of onprem prod. with placement groups what should i see?",
      steps=[S("search_docs", query="pskit tf state list placement terraform_data host_group",
               docs=[D(CLI, "pskit-tf----args", words=30),
                     D("docs/placement.md", "deploy-urls-and-load-balancers", end="`deployment.json` list each group's endpoint and functions.")])],
      final="""**In the terminal**
```bash
pskit tf -s prod -p onprem -- state list
```
You should see `terraform_data.host` for the default group and one `terraform_data.host_<group>` for each other group [docs/placement.md#deploy-urls-and-load-balancers]."""),

    A(383, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="informal_non_native",
      sources=[f"{CLI}#pskit-deploy"],
      user="i want see what change before onprem prod deploy really happen, not auto. possible?",
      steps=[S("search_docs", query="deploy review plan before apply confirm",
               docs=[D(CLI, "pskit-deploy")])],
      final="""Yes. `--confirm` runs `terraform plan -out tfplan` first and then applies that plan, instead of `-auto-approve` [docs/cli.md#pskit-deploy].

**In the terminal**
```bash
pskit plan -s prod
pskit deploy -s prod --confirm
```

**In studio**
1. **Deploy > Plan** shows the plan.
2. **Deploy > Deploy**: for `prod` you type `onprem/prod` to confirm."""),

    A(384, provider="onprem", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{CF}#extends-inherit-files", f"{CF}#{PREC}"],
      user="Our main pskit.yml targets AWS. I'd like the on-prem settings (port, deploy server, env file) in a separate pskit.onprem.yml so the AWS file stays clean. How?",
      steps=[S("search_docs", query="extends inherit file per provider",
               docs=[D(CF, "extends-inherit-files"), D(CF, PREC)])],
      final="""Use `extends:`. The child file inherits everything and adds or overrides what it sets [docs/configuration.md#extends-inherit-files].

**In code**
```yaml
# pskit.onprem.yml
extends: pskit.yml
provider:
  name: onprem
  options:
    port: 8080
    env_file: .env.onprem
    deploy: {server: app-1, path: /opt/pskit/shop}
```
The child's own values beat the parent's, and lists are replaced, not appended [docs/configuration.md#precedence-later-wins].

**In the terminal**
```bash
pskit validate -c pskit.onprem.yml
pskit deploy -c pskit.onprem.yml -s dev
```"""),

    A(385, provider="onprem", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=[f"{CF}#switch-something-off-on-one-cloud", f"{CF}#{PREC}"],
      user="in providers.onprem i wrote api: {events: [{http: GET /status}]} to add one route. now on onprem the other routes and the schedule of api are gone!",
      steps=[S("search_docs", query="providers override events list replace",
               docs=[D(CF, "switch-something-off-on-one-cloud"),
                     D(CF, PREC, start="Dicts are deep-merged; lists are replaced, not appended.")])],
      final="""That's how overrides work: dicts are merged, but lists are **replaced** [docs/configuration.md#precedence-later-wins]. On onprem, `api` now gets only `GET /status` [docs/configuration.md#switch-something-off-on-one-cloud].

To add a route on onprem, repeat the whole list in the override:

**In code**
```yaml
providers:
  onprem:
    functions:
      api:
        events:
          - http: GET /orders
          - http: POST /orders
          - schedule: 1 hour
          - http: GET /status
```
Or add `GET /status` to the main `events:` list, if all providers should have it."""),

    A(386, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{CF}#provider"],
      user="pskit deploy -p onprem -s Prod_1\nError: pskit.yml is invalid:\n  - provider.stage: Value error, stage must be lowercase alphanumeric/dash, max 16 chars, e.g. dev, prod",
      steps=[S("search_docs", query="stage name rules lowercase",
               docs=[D(CF, "provider", start="| `stage` |", end="| `stage` |")])],
      final="""Stage names must be lowercase letters, digits and dashes, start with a letter, and be at most 16 characters [docs/configuration.md#provider]. `Prod_1` has a capital letter and an underscore.

**In the terminal**
```bash
pskit deploy -p onprem -s prod-1
```
Stages named `prod...` need a typed confirmation in the studio's Deploy page."""),

    A(387, provider="onprem", stage="staging", mode="ask", page="YAML", persona="terse_expert",
      sources=[f"{PR}#{OP}"],
      user="do I need ${opt:stage} in data_dir so staging and prod on the same box don't share queues?",
      steps=[S("search_docs", query="data_dir default per service stage",
               docs=[D(PR, OP, start="- **Dependencies:**", words=60)])],
      final="""Not with the default. A local `data_dir` defaults to `.pskit/onprem-data/<service>-<stage>`, so it's already per stage. Over SSH it's `<path>/data`, so give each stage its own `deploy.path` [docs/providers.md#onprem-on-premises].

Only if you set `data_dir` yourself:
```yaml
provider:
  options:
    data_dir: /var/pskit/shop-${opt:stage}
```"""),

    A(388, provider="onprem", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=[f"{CF}#variables"],
      user="In serverless.yml we use ${self:custom.tableName}, ${opt:stage} and ${file(./config.json)}. Does pskit.yml understand the same syntax for our on-prem config?",
      steps=[S("search_docs", query="variables self opt file env syntax",
               docs=[D(CF, "variables", end="Variables can nest across passes")])],
      final="""Mostly yes [docs/configuration.md#variables]:

| serverless.yml | pskit.yml |
|---|---|
| `${self:custom.tableName}` | same: `${self:custom.tableName}` (any value of the merged config) |
| `${opt:stage}` | same; also `${opt:provider}`, `${opt:region}`, with `${opt:x, default}` |
| `${file(./config.json)}` | `${file(config.json)}`: `.json` / `.yml` are parsed, other files read as text |
| `${env:NAME}` | same; `${env:NAME, default}` for a default |

**In code**
```yaml
custom:
  queue: jobs-${opt:stage}
functions:
  worker:
    handler: app.jobs.work
    events:
      - queue: ${self:custom.queue}
```
Paths in `${file(...)}` are relative to the config file. Other Serverless variable sources (SSM, CloudFormation outputs) aren't supported; use `${env:...}` or a secret manager."""),

    A(389, provider="onprem", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=[f"{CF}#variables", f"{CF}#stages-per-stage-overrides"],
      user="Error: unresolved variables: self:custom.port\n\nI only defined custom.port under stages.prod, and dev fails. prod works.",
      steps=[S("search_docs", query="unresolved self variable stage override",
               docs=[D(CF, "variables", start="| `${self:dotted.path}` |", end="| `${self:dotted.path}` |"),
                     D(CF, "stages-per-stage-overrides")])],
      final="""`${self:...}` reads the merged config of the stage you run. On dev there's no `stages.dev` block, so `custom.port` doesn't exist there [docs/configuration.md#variables].

Give it a default at the top level, and override it only for prod:

**In code**
```yaml
custom:
  port: 8080
provider:
  name: onprem
  options:
    port: ${self:custom.port}
stages:
  prod:
    custom: {port: 9100}
```"""),

    A(390, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{AR}#state-handling", "docs/cli.md#pskit-settings"],
      user="where is the terraform state of my onprem deploy? should i commit it to git?",
      steps=[S("search_docs", query="terraform state location commit git",
               docs=[D(AR, "state-handling"),
                     D(CLI, "pskit-settings", start="Not inside: Terraform state", end="build output and backups.")])],
      final="""It's in `.pskit/onprem-<stage>/terraform.tfstate`. Don't commit it: `.pskit/` is git-ignored, and pskit writes a `.gitignore` there [docs/architecture.md#state-handling].

To work from another machine, move your saved servers and deploy records with `pskit settings export` / `import`. Per the docs, on-prem deploys don't need the state moved along [docs/cli.md#pskit-settings]. For a team, a remote backend in `provider.state` is the usual choice."""),

    A(391, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="pasted_error",
      sources=[f"{CF}#switch-something-off-on-one-cloud"],
      user="Error: pskit.yml is invalid:\n  - <root>: Value error, workflow 'wf' calls function 'worker', which is disabled; disable the workflow too\n\nI disabled worker only for onprem",
      steps=[S("search_docs", query="disable function workflow on one provider",
               docs=[D(CF, "switch-something-off-on-one-cloud")])],
      final="""A workflow can't run without its task function, so if `worker` is off on onprem, `wf` must be off there too [docs/configuration.md#switch-something-off-on-one-cloud].

**In code**
```yaml
providers:
  onprem:
    functions:
      worker: {enabled: false}
    workflows:
      wf: {enabled: false}
```

The studio's Deploy page offers the same fix when it lists what won't run on onprem."""),

    A(392, provider="onprem", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=[f"{CF}#terraform"],
      user="yaml only: pin terraform >= 1.9 for everyone deploying this onprem project",
      steps=[S("search_docs", query="terraform required_version",
               docs=[D(CF, "terraform")])],
      final="""**In code**
```yaml
provider:
  name: onprem
  terraform:
    required_version: ">= 1.9.0"
```
It's written into `terraform { required_version }` [docs/configuration.md#terraform]."""),

    A(393, provider="onprem", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=[f"{PR}#{OP}", f"{CF}#escape-hatches"],
      user="can i put my own terraform_data with local-exec in terraform.extra on onprem, for run a migration script? or it is removed like aws things?",
      steps=[S("search_docs", query="terraform.extra onprem omitted other cloud",
               docs=[D(PR, OP, start="**Limits:**", words=45),
                     D(CF, "escape-hatches", end="| Reference those resources |")])],
      final="""Only resources of **other clouds** (`aws_*`, `google_*`, `azurerm_*`, ...) are dropped on-prem, with a warning [docs/providers.md#onprem-on-premises]. `terraform_data` is built into Terraform, not a cloud's resource, so it isn't in that list and stays.

**In code**
```yaml
provider:
  name: onprem
  terraform:
    extra:
      resource:
        terraform_data:
          migrate:
            provisioner:
              local-exec: {command: "python scripts/migrate.py"}
```
It runs on **your** machine, when Terraform creates the resource. For a script after every deploy, a `hooks.after_deploy` command is simpler."""),

    A(394, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{AR}#deploy-pipeline", f"{CLI}#pskit-tf----args"],
      user="Our CI needs the URLs of the on-prem prod functions after deploy, as JSON. Is there a stable Terraform output, or should we parse pskit info?",
      steps=[S("search_docs", query="pskit terraform output shape functions url endpoint",
               docs=[D(AR, "deploy-pipeline", start="- **Every provider emits a `pskit` output**", end="- **Every provider emits a `pskit` output**"),
                     D(CLI, "pskit-tf----args", words=30)])],
      final="""Both work. Every provider, on-prem too, emits a `pskit` output with the same shape: `{functions: {name: {id, url?, ...}}, workflows: {...}, endpoint}` [docs/architecture.md#deploy-pipeline].

**In the terminal**
```bash
pskit tf -s prod -p onprem -- output -json
pskit info -s prod -p onprem --json
```
`pskit info --json` reads the same output (via the saved record, or `--refresh` to read it again)."""),

    A(395, provider="onprem", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{CF}#hooks"],
      user="After each on-prem deploy we want a smoke test that calls /health, and the deploy should fail if it fails. Can pskit run that?",
      steps=[S("search_docs", query="hooks after deploy smoke test",
               docs=[D(CF, "hooks")])],
      final="""Yes, with an `after_deploy` hook. Hooks run through the shell in the project root, with `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and `PSKIT_WORK_DIR` set. A non-zero exit aborts the command [docs/configuration.md#hooks].

**In code**
```yaml
hooks:
  after_deploy: ["python scripts/smoke_test.py"]
```
```python
from __future__ import annotations

import sys
import urllib.request

URL = "http://192.0.2.10:8080/health"

try:
    with urllib.request.urlopen(URL, timeout=10) as resp:
        sys.exit(0 if resp.status == 200 else 1)
except OSError:
    sys.exit(1)
```
The deploy has already happened when the hook runs. A failing hook makes `pskit deploy` exit with an error, but doesn't roll back."""),

    A(396, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{CF}#provider"],
      user="my pskit.yml has stage: prod under provider. i typed pskit deploy without -s and it deployed prod! i thought default is dev?",
      steps=[S("search_docs", query="provider stage default overridden by --stage",
               docs=[D(CF, "provider", start="| `stage` |", end="| `stage` |")])],
      final="""The default is `dev` only when `provider.stage` isn't set. Yours says `prod`, so that's the stage. `--stage` overrides it [docs/configuration.md#provider].

Safer: remove `stage:` from `pskit.yml` and always pass it:

**In the terminal**
```bash
pskit deploy -s dev
pskit deploy -s prod
```

**In studio**
The stage box in the top bar decides. Deploying a `prod...` stage there asks you to type `onprem/prod` first."""),

    A(397, provider="onprem", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=[f"{CF}#extends-inherit-files"],
      user="Error: circular `extends`: ...\\pskit.yml -> ...\\pskit.onprem.yml -> ...\\pskit.yml",
      steps=[S("search_docs", query="circular extends",
               docs=[D(CF, "extends-inherit-files")])],
      final="""Each file extends the other. `extends` must go one way only: the child names the parent, never back [docs/configuration.md#extends-inherit-files].

**In code**
Remove `extends:` from `pskit.yml` and keep it only in the child:
```yaml
# pskit.onprem.yml
extends: pskit.yml
provider:
  name: onprem
```
Then run `pskit validate -c pskit.onprem.yml`."""),

    A(398, provider="onprem", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{CF}#{PREC}"],
      user="pskit.yml has providers.onprem.options.port: 8090. pskit.onprem.yml extends it and sets provider.options.port: 8080. Which port wins when I deploy with -c pskit.onprem.yml?",
      steps=[S("search_docs", query="precedence extends providers block child",
               docs=[D(CF, PREC)])],
      final="""8080. For each file in the `extends` chain, parents come first: the parent's values, then the parent's `providers.onprem` block, then the child's values. So a child's explicit value beats its parent's per-provider override [docs/configuration.md#precedence-later-wins].

After that, `stages.<stage>` and then CLI flags (`--provider`, `--stage`, `--region`) still win. To check what you get, run `pskit validate -c pskit.onprem.yml`, or look at the **YAML** page."""),

    A(399, provider="onprem", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=[f"{CF}#hooks"],
      user="before deploy onprem i must build my vue frontend (npm run build) into static/. pskit can do it automatic?",
      steps=[S("search_docs", query="hooks before package build",
               docs=[D(CF, "hooks")])],
      final="""Yes, with a hook. `before_package` runs before the bundle is built, also inside `pskit deploy` [docs/configuration.md#hooks].

**In code**
```yaml
hooks:
  before_package: ["npm --prefix frontend run build"]
```
Hooks run in the project root, and a non-zero exit stops the command, so a failed build stops the deploy. Make sure `static/` isn't in `package.exclude`, so the files land in the bundle."""),

    A(400, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="terse_expert",
      sources=[f"{CLI}#pskit-deploy", f"{PR}#{OP}"],
      user="pskit deploy --upgrade on onprem: does it do anything?",
      steps=[S("search_docs", query="deploy upgrade terraform init provider plugins",
               docs=[D(CLI, "pskit-deploy", start="| `--upgrade` |", end="| `--upgrade` |"), TFDATA])],
      final="""Practically nothing. `--upgrade` runs `terraform init -upgrade` to update provider plugins [docs/cli.md#pskit-deploy], and on-prem uses only the built-in `terraform_data`, with no plugin download [docs/providers.md#onprem-on-premises]. It only matters if your `terraform.extra` adds providers."""),
]
