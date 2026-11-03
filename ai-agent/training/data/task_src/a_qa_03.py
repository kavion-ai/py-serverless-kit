"""Category A (docs Q&A and how-to), batch 3: studio pages, CLI commands, getting started, local development,
dashboard and troubleshooting, spread over the providers. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(41, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/cli.md#pskit-init-directory", "docs/studio.md#what-you-can-do"],
      user="how do i start a brand new project that goes to google cloud?",
      steps=[S("search_docs", query="new project scaffold init template",
               docs=[D("docs/cli.md", "pskit-init-directory"),
                     D("docs/studio.md", "what-you-can-do", start="| **New project** |", end="| **New project** |")])],
      final="""Create the project with a template, then fill in your GCP project id. GCP needs `options.project`.

**In studio**
1. Run `pskit studio --open` in an empty folder. The **New project** page appears because there's no `pskit.yml` yet.
2. Enter the service name, pick Google Cloud and a starter template [docs/studio.md#what-you-can-do].
3. In **Overview & provider**, fill in the provider option *project* and click **Save**.

**In the terminal**
```bash
pskit init my-api -p gcp -t http
cd my-api
pskit validate
```
The templates are `http`, `events`, `workflow` and `full` [docs/cli.md#pskit-init-directory].

**In code**
```yaml
service: my-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: my-gcp-project
```
Use your own project id, and run `pskit validate` again."""),

    A(42, provider="aws", stage="dev", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/studio.md#test-functions"],
      user="In the Lambda console I keep named test events per function. In the studio, how do I save a payload so I can reuse it next time?",
      steps=[S("search_docs", query="studio save test event payload",
               docs=[D("docs/studio.md", "test-functions", end="**Run locally** runs the handler")])],
      final="""**In studio**
1. Open **Test** and pick the function and its event (a trigger, or **Direct invoke**).
2. Edit the payload. It starts from a sample for that trigger type.
3. Click **Save event** and give it a name.
4. Next time, pick the saved event and click **▶ Run locally**.

Saved events are stored per function in `.pskit/studio/test-events.json`, like the test events in the Lambda console [docs/studio.md#test-functions]."""),

    A(43, provider="aws", stage="prod", mode="auto", page="Test", persona="detailed_spec",
      sources=["docs/cli.md#pskit-trigger", "docs/studio.md#test-functions"],
      user="Our SQS worker is deployed to prod. I want to push two real messages through the queue it listens on and then watch what the function logs. No local run, the real thing.",
      steps=[S("search_docs", query="send real test event to deployed function queue",
               docs=[D("docs/cli.md", "pskit-trigger", words=100)])],
      final="""Use `pskit trigger`. It sends a real event to the deployed function, the way its trigger would. For a queue trigger it sends a real SQS message [docs/cli.md#pskit-trigger].

**In the terminal**
```bash
pskit trigger -s prod -f worker -e 0 -d '[{"id": 1}, {"id": 2}]'
pskit logs -s prod -f --function worker
```
`-e 0` is the first trigger in the function's `events:`. A list in `-d` sends one message per item.

**In studio**
1. Open **Test** with aws / prod in the top bar.
2. Pick the worker and its queue trigger, and edit the payload.
3. Turn on *Show the function's logs*.
4. Click **☁ Send to aws / prod** [docs/studio.md#test-functions].

This uses your machine's AWS credentials, and boto3 must be installed (`pip install "py-serverless-kit[aws]"`)."""),

    A(44, provider="alibaba", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/cli.md#pskit-trigger"],
      user="pskit trigger can upload file to my alibaba bucket for test the storage function?",
      steps=[S("search_docs", query="pskit trigger alibaba storage upload",
               docs=[D("docs/cli.md", "pskit-trigger", start="What pskit can send itself",
                       end="and the console steps instead.", words=300)])],
      final="""No. On Alibaba, `pskit trigger` can only send HTTP requests itself. It can't upload to OSS, send queue or topic messages, or invoke the function [docs/cli.md#pskit-trigger].

Do this instead:
1. Print the ready-made commands:
```bash
pskit trigger --list
```
For a storage trigger on Alibaba, it shows the cloud CLI command (`ossutil`) and the console steps to upload a test object.
2. To test the handler logic without the cloud, run it locally with a storage event:
```bash
pskit invoke -f my-function -t storage
```"""),

    A(45, provider="azure", stage="staging", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/dashboard.md#log-sources", "docs/cli.md#pskit-logs"],
      user="The Logs page shows nothing for our Azure staging deployment, while for AWS it works. What does pskit need to read Azure logs?",
      steps=[S("search_docs", query="azure logs log analytics requirements",
               docs=[D("docs/dashboard.md", "log-sources", end="| Others | — | — | use the console link the tab shows |")]),
             S("search_docs", query="pskit logs azure read only",
               docs=[D("docs/cli.md", "pskit-logs", end="Requirements per provider: [dashboard.md](dashboard.md#log-sources).")])],
      final="""On Azure, pskit reads `AppTraces` from Log Analytics. It needs two things [docs/dashboard.md#log-sources]:
1. The deployment must have the Terraform output `log_analytics_workspace_id`. pskit's Azure provider writes that output with its Log Analytics workspace when `options.app_insights` is on, which is the default ([src/py_serverless_kit/providers/azure.py]). If you turned it off, add the output yourself with `provider.terraform.extra`.
2. The SDKs must be installed on the machine running studio or pskit:
```bash
pip install azure-monitor-query azure-identity
```

Then check from the terminal:
```bash
pskit logs -p azure -s staging -n 50
```

Azure logs in pskit are read-only (deleting is AWS and on-prem only), and cloud log pipelines lag a few seconds. If the deployment was made before the output existed, run `pskit info -p azure -s staging --refresh` to re-read the Terraform outputs."""),

    A(46, provider="onprem", stage="dev", mode="ask", page="none", persona="terse_expert",
      sources=["docs/dashboard.md#dashboard"],
      user="live dashboard for the onprem host, port 9000, open browser",
      steps=[S("search_docs", query="dashboard serve live port",
               docs=[D("docs/dashboard.md", "dashboard", start="```bash", words=45)])],
      final="""**In the terminal**
```bash
pskit dashboard --serve --open --port 9000
```
It binds `127.0.0.1` and adds the live views: host health and invocation stats, a log tail and workflow executions, with **Start** and **Cancel** [docs/dashboard.md#dashboard]. The admin token stays on the server side and never reaches the browser."""),

    A(47, provider="digitalocean", stage="dev", mode="auto", page="Setup", persona="pasted_error",
      sources=["docs/troubleshooting.md#installation-and-tooling", "docs/getting-started.md#1-install"],
      user="Neither terraform nor tofu was found on PATH\n\nthis comes when i try to deploy",
      steps=[S("search_docs", query="terraform tofu not found on PATH",
               docs=[D("docs/troubleshooting.md", "installation-and-tooling", end="`provider.terraform.binary`) at the binary.")])],
      final="""pskit deploys through Terraform, and this machine has neither `terraform` nor `tofu` on `PATH`. Install Terraform 1.5 or newer, or OpenTofu, or point `PSKIT_TERRAFORM_BIN` at the binary [docs/troubleshooting.md#installation-and-tooling].

**In studio**
1. Open **Setup & credentials** with DigitalOcean in the top bar.
2. The Terraform check shows the download link and the install steps for your OS.
3. After installing, run the checks again until Terraform shows as found.

**In the terminal**
```bash
pskit doctor -p digitalocean
```
It also checks `doctl` and the required `options.namespace`.

**In code**
If the binary isn't on `PATH`:
```yaml
provider:
  name: digitalocean
  terraform:
    binary: tofu
```"""),

    A(48, provider="tencent", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/cli.md#pskit-package", "docs/cli.md#pskit-plan", "docs/cli.md#pskit-deploy"],
      user="on the deploy page there is Package, Plan and Deploy. whats the difference, which one touches my tencent account?",
      steps=[S("search_docs", query="package plan deploy difference",
               docs=[D("docs/cli.md", "pskit-package"), D("docs/cli.md", "pskit-plan"),
                     D("docs/cli.md", "pskit-deploy", end="`--no-dashboard` | don't regenerate `.pskit/dashboard/index.html` |")])],
      final="""- **Package** builds `.pskit/tencent-dev/artifact.zip` and `main.tf.json` on your machine. It doesn't contact Tencent [docs/cli.md#pskit-package].
- **Plan** packages, runs `terraform init` and `terraform plan`, and shows what would change. It reads your account but changes nothing [docs/cli.md#pskit-plan].
- **Deploy** packages, then runs `terraform apply`. This is the one that creates or changes resources in your Tencent account [docs/cli.md#pskit-deploy].

**In studio**
1. Open **Deploy** and click **Package** to check the build, then **Plan** to see the changes.
2. Click **Deploy** and confirm.

**In the terminal**
```bash
pskit package
pskit plan
pskit deploy
```"""),

    A(49, provider="aws", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/cli.md#pskit-deploy", "docs/studio.md#what-you-can-do"],
      user="For prod our change process requires that someone reviews the exact Terraform plan before it is applied. Normal deploys seem to auto-approve. How do we do this with pskit?",
      steps=[S("search_docs", query="deploy review plan before apply no auto-approve",
               docs=[D("docs/cli.md", "pskit-deploy", end="Hooks `before_package`, `after_package`, `before_deploy` and `after_deploy` run around these steps.")])],
      final="""Use `pskit deploy --confirm`. It runs `terraform plan -out tfplan` and then applies exactly that plan, instead of `-auto-approve` [docs/cli.md#pskit-deploy].

**In the terminal**
1. Have the reviewer read the plan:
```bash
pskit plan -s prod
```
2. Deploy with the plan shown first, then applied as reviewed:
```bash
pskit deploy -s prod --confirm
```

**In studio**
1. Open **Deploy** with aws / prod in the top bar.
2. Click **Plan** and review the live log.
3. Click **Deploy**. Stages named `prod*` need a typed confirmation (`aws/prod`) before anything runs.

Keep prod's Terraform state in a remote backend (`provider.state`), so the reviewer and the deployer see the same state."""),

    A(50, provider="gcp", stage="staging", mode="ask", page="Deploy", persona="aws_migrator",
      sources=["docs/cli.md#pskit-remove", "docs/studio.md#project-environment-trigger-resources-and-remove"],
      user="With serverless framework I removed the stack but the S3 bucket with data stayed. On GCP staging I want to drop the functions but keep the bucket and the Pub/Sub topic. Possible?",
      steps=[S("search_docs", query="remove keep buckets queues topics data",
               docs=[D("docs/cli.md", "pskit-remove", words=300)]),
             S("search_docs", query="studio remove keep resources switch",
               docs=[D("docs/studio.md", "project-environment-trigger-resources-and-remove", start="- **Deploy → Remove** has a switch",
                       end="the data resources stay in the cloud.")])],
      final="""Yes. `pskit remove --keep-resources` destroys only the functions, triggers and gateways. Managed buckets, queues and topics stay with their data. It's supported on GCP [docs/cli.md#pskit-remove].

**In the terminal**
```bash
pskit remove -s staging --keep-resources
```

**In studio**
1. Open **Deploy** with gcp / staging in the top bar.
2. Turn off the switch *Remove also deletes buckets, queues and topics*.
3. Click **Remove** and type the confirmation [docs/studio.md#project-environment-trigger-resources-and-remove].

After this, pskit no longer manages the kept resources. They're remembered in `.pskit/gcp-staging/kept/`, so you can delete them later with `pskit resources delete` or import them into another stack. The code-upload bucket isn't kept.

Remove is destructive, so run it yourself. Studio asks you to confirm."""),

    A(51, provider="huawei", stage="dev", mode="auto", page="none", persona="terse_expert",
      sources=["docs/cli.md#pskit-tf----args"],
      user="need terraform state list on the generated huawei workspace",
      steps=[S("search_docs", query="run terraform command generated workspace",
               docs=[D("docs/cli.md", "pskit-tf----args")])],
      final="""**In the terminal**
```bash
pskit tf -p huawei -- state list
```
Everything after `--` goes to Terraform, run in `.pskit/huawei-dev/`. The workspace exists after `pskit package` or `pskit deploy` [docs/cli.md#pskit-tf----args]."""),

    A(52, provider="cloudflare", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/studio.md#full-vs-code-code-server-in-docker"],
      user="the code editor is small for me. where i click to open real vscode inside the studio?",
      steps=[S("search_docs", query="full vs code in studio",
               docs=[D("docs/studio.md", "full-vs-code-code-server-in-docker", end="Stop removes it; your files stay in the project folder.")])],
      final="""**In studio**
1. Open **Code** and switch to **Full VS Code**.
2. If Docker is missing or not running, studio shows how to install it. Start Docker first.
3. Click **Pull & start**. The first time, the image is downloaded and the log shows the progress.
4. VS Code opens inside the studio. Use **Open in new tab ↗** for a bigger window, and **Stop** when you're done. Your files stay in the project folder.

[docs/studio.md#full-vs-code-code-server-in-docker]"""),

    A(53, provider="azure", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=["docs/studio.md#setup-logs-and-provider-differences", "docs/getting-started.md#6-configure-cloud-credentials"],
      user="how do i log in to my azure account so i can deploy?",
      steps=[S("search_docs", query="azure login credentials subscription",
               docs=[D("docs/getting-started.md", "6-configure-cloud-credentials", start="| `azure` |", end="| `azure` |"),
                     D("docs/studio.md", "setup-logs-and-provider-differences", end="- test the SSH connection of an on-prem deploy.")])],
      final="""Sign in with `az login` and tell pskit your subscription id with `ARM_SUBSCRIPTION_ID` (or `options.subscription_id`) [docs/getting-started.md#6-configure-cloud-credentials].

**In studio**
1. Open **Setup & credentials** with Azure in the top bar.
2. Click **Sign in (az login)**. A browser login starts.
3. Under *Environment variables*, enter `ARM_SUBSCRIPTION_ID` and click **Set for this session**. It's used only by this studio session, and nothing is written to disk [docs/studio.md#setup-logs-and-provider-differences].

**In the terminal**
```bash
az login
export ARM_SUBSCRIPTION_ID=<your subscription id>
pskit doctor -p azure
```

**In code**
```yaml
provider:
  name: azure
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID}
```
`pskit validate` passes without it, but the deploy needs it."""),

    A(54, provider="onprem", stage="dev", mode="auto", page="none", persona="detailed_spec",
      sources=["docs/studio.md#security"],
      user="I'd like to run pskit studio on a build server and open it from my laptop's browser. Is that safe, and what's the recommended way?",
      steps=[S("search_docs", query="studio host bind remote access security token",
               docs=[D("docs/studio.md", "security", end="bodies are capped at 2 MiB.")]),
             S("search_docs", query="pskit studio host option warning",
               docs=[D("docs/studio.md", "studio-build-a-project-without-writing-yaml", start="| `--host` |", end="| `--host` |")])],
      final="""Be careful with this. Studio can write files in the project and run deploys with that server's cloud credentials. Anyone who has the URL with its session token gets full access [docs/studio.md#security].

Safest way: keep studio on loopback (the default) and forward the port over SSH.
```bash
pskit studio --port 8770
```
Then on your laptop:
```bash
ssh -L 8770:127.0.0.1:8770 me@build.example.com
```
Open the URL studio prints (it ends with the session token) in your laptop's browser.

`pskit studio --host 0.0.0.0` also works, but it prints a warning, because studio would then be reachable from the network [docs/studio.md#studio-build-a-project-without-writing-yaml]. Don't share the token URL. A new token is generated each time studio starts."""),

    A(55, provider="ibm", stage="prod", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#ibm-code-engine-functions", "docs/troubleshooting.md#provider-gotchas"],
      user="ibm deploy is slow and they say my code is too big. what i can do?",
      steps=[S("search_docs", query="ibm code engine bundle too large",
               docs=[D("docs/providers.md", "ibm-code-engine-functions", start="```yaml", end="`auth` must be `none`. Code is uploaded inline as base64, so keep bundles small or use `code_reference`.")])],
      final="""On IBM Code Engine, pskit uploads your code inline as base64, so a big bundle hurts. Keep it small, or use a code bundle image with `code_reference` [docs/providers.md#ibm-code-engine-functions].

**In code**
1. Put only real runtime dependencies in `requirements.txt`.
2. Keep data files out of the bundle (`tests/**` is already excluded by default):
```yaml
package:
  exclude: ["data/**", "**/*.csv"]
```
3. Or point to a code bundle image:
```yaml
provider:
  name: ibm
  options:
    code_reference: icr.io/my-namespace/bundle:v1
```

**In the terminal**
Build without deploying to check the size:
```bash
pskit package -s prod
```
The zip is in `.pskit/ibm-prod/artifact.zip`."""),

    A(56, provider="oracle", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/providers.md#oracle-oci-functions", "docs/troubleshooting.md#provider-gotchas"],
      user="ERROR: [provider.options] OCI Functions need a container image. Either set options.image_repository ...\n\nwhy an image? i only have python",
      steps=[S("search_docs", query="oracle container image image_repository",
               docs=[D("docs/troubleshooting.md", "provider-gotchas", start="| oracle |", end="| oracle |")]),
             S("search_docs", query="oci functions image options",
               docs=[D("docs/providers.md", "oracle-oci-functions", words=230)])],
      final="""OCI Functions always run your code as a container image, even for Python. You don't build the image by hand. Choose one of these [docs/troubleshooting.md#provider-gotchas]:

1. `options.image`: an image that already exists.
2. `options.image_repository`: an OCIR repository. Docker must be logged in to OCIR on this machine.

**In code**
```yaml
provider:
  name: oracle
  options:
    image_repository: ${env:OCI_IMAGE_REPOSITORY}
```

**In studio**
1. Open **Overview & provider** with Oracle selected.
2. Fill in the image option along with `compartment_id` and `subnet_ids`, which Oracle also needs.
3. Click **Save**. The problem disappears from the Problems list once it's fixed.

**In the terminal**
```bash
pskit doctor -p oracle
pskit validate -p oracle
```"""),

    A(57, provider="aws", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/local-development.md#environment"],
      user="local env vars for pskit invoke/dev: where do they come from, and can I use another file than .env?",
      steps=[S("search_docs", query="local environment variables env file invoke dev",
               docs=[D("docs/local-development.md", "environment")])],
      final="""Local runs set `PSKIT_PROVIDER=local`, `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_REGION=local`, `PSKIT_FUNCTION` and `PSKIT_HANDLER`. Then they add `provider.environment` and the function's `environment`, and finally load `.env`, or the file you pass with `--env-file` [docs/local-development.md#environment].

**In the terminal**
```bash
pskit invoke -f api --env-file .env.local
pskit dev --env-file .env.local
```

**In code**
```text
# .env.local  (keep it out of git)
DATABASE_URL=postgres://localhost/orders
LOG_LEVEL=DEBUG
```
Put real secrets only in env files that stay out of git.
`.env` is git-ignored and excluded from deployment bundles. `invoke()` calls between functions run in-process locally."""),

    A(58, provider="gcp", stage="dev", mode="auto", page="Code", persona="beginner",
      sources=["docs/local-development.md#testing-with-pytest"],
      user="my queue worker returns BatchResult. how do i write a pytest test that checks only the bad message failed?",
      steps=[S("search_docs", query="pytest queue BatchResult test local runner",
               docs=[D("docs/local-development.md", "testing-with-pytest", end="raises `WorkflowFailed` |", words=300)])],
      final="""Use `LocalRunner` with `build_event("queue", [...])`. The result has `failed`, the ids of the records that failed. Locally the ids are `local-1`, `local-2`, and so on [docs/local-development.md#testing-with-pytest].

**In code**
```python
# tests/test_worker.py
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, build_event

runner = LocalRunner(Project.load())


def test_only_bad_message_fails():
    result = runner.invoke("process-jobs", build_event("queue", [{"ok": 1}, "not-json"]))
    assert result.failed == ["local-1"]
```
Replace `process-jobs` with your function's name in pskit.yml.

**In the terminal**
```bash
pytest tests/test_worker.py
```
No cloud credentials or Terraform are needed. The test runs through the same dispatcher as in the cloud."""),

    A(59, provider="digitalocean", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/troubleshooting.md#http", "docs/local-development.md#pskit-dev-local-server"],
      user="pskit dev give 404 for /users/42/ but route is in yml?? GET /users/{id}",
      steps=[S("search_docs", query="pskit dev 404 route local",
               docs=[D("docs/troubleshooting.md", "http", start="**404 locally but works in the cloud", end="(last segment only).")]),
             S("search_docs", query="pskit dev routes unknown paths 404",
               docs=[D("docs/local-development.md", "pskit-dev-local-server", start="| Endpoint | What it does |",
                       end="unknown paths return 404 with the route list |")])],
      final="""`pskit dev` matches routes exactly [docs/troubleshooting.md#http]. Check the route list it prints at startup: unknown paths return 404 together with that list [docs/local-development.md#pskit-dev-local-server].

What to check:
1. Compare the printed route with the URL you call, character by character.
2. Make sure the method is `GET`. A matching path with the wrong method gives 405, not 404.
3. Path templates are `{id}`, plus `{path+}` for the last segment only.

**In the terminal**
```bash
pskit dev
curl http://127.0.0.1:3000/users/42
```
If it still fails, paste the route list `pskit dev` prints and I'll compare it."""),

    A(60, provider="gcp", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#state-remote-terraform-backend", "docs/troubleshooting.md#deploy-and-state"],
      user="Two of us deploy the same GCP project from different laptops and now Terraform says resources already exist. How do we share the state properly?",
      steps=[S("search_docs", query="state conflict resource already exists another machine",
               docs=[D("docs/troubleshooting.md", "deploy-and-state", end="via `pskit tf -- init -migrate-state`.")]),
             S("search_docs", query="remote terraform backend provider.state",
               docs=[D("docs/configuration.md", "state-remote-terraform-backend")])],
      final="""Each laptop has its own local state in `.pskit/`, so each one thinks it owns the resources. Move the state to a remote backend that both of you use [docs/troubleshooting.md#deploy-and-state].

**In code**
`backend` takes any Terraform backend type. For GCP, use `gcs` [docs/configuration.md#state-remote-terraform-backend]:
```yaml
provider:
  name: gcp
  state:
    backend: gcs
    config:
      bucket: my-tf-state
      prefix: orders/${opt:stage}
```

**In the terminal**
On the laptop whose state matches what's deployed, move the existing state into the bucket:
```bash
pskit tf -s prod -- init -migrate-state
```
Then the other person pulls the updated pskit.yml and deploys as usual. The state bucket must exist before you run this."""),
]
