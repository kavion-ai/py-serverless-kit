"""Category A (docs Q&A and how-to), batch 26: aws / gcp / azure. HTTP auth per cloud (jwt, iam, key), AWS code
upload and accounts, secrets, doctor, workflow states (map, choice, parallel, data flow), orchestrator route,
enable/disable per provider, info/dashboard/tf/providers commands, packaging excludes.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(491, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      user="Our users log in with Amazon Cognito. The /account routes should only accept requests with a valid Cognito access token for our app client, and require the scope account/read. How do I configure that?",
      steps=[S("search_docs", query="jwt auth authorizer issuer audience scopes",
               docs=[D("docs/events.md", "http", start="**Auth support**", end="Example of AWS JWT auth")])],
      final="""Use `auth: jwt` with an `authorizer`. On AWS it becomes an API Gateway JWT authorizer. `issuer` and `audience` are required; `scopes` and `identity_source` are optional [docs/events.md#http].

**In code**
```yaml
functions:
  account:
    handler: app.account.get
    events:
      - http:
          path: /account
          method: GET
          auth: jwt
          authorizer:
            issuer: <your Cognito user pool's issuer URL>
            audience: [<app client id>]
            scopes: [account/read]
```
The token is read from the `Authorization` header by default.

**In studio**
1. Open **Functions** and click `account`.
2. In the HTTP trigger, set *Auth* to `jwt` and fill in the *Authorizer* issuer, audience and scopes.
3. Click **Save**.

**In the terminal**
```bash
pskit validate
```
`jwt` is AWS only; on other clouds validate the token in the handler. See `examples/02-rest-api`."""),

    A(492, provider="aws", stage="dev", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      user="ERROR: [functions.admin] jwt auth needs authorizer.issuer and authorizer.audience",
      steps=[S("search_docs", query="jwt auth needs authorizer issuer audience",
               docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")])],
      final="""`auth: jwt` on AWS needs an `authorizer` with both `issuer` and `audience` [docs/events.md#http]. Add them to the `admin` route:

```yaml
functions:
  admin:
    handler: app.admin.handler
    events:
      - http:
          path: /admin
          method: GET
          auth: jwt
          authorizer:
            issuer: https://login.example.com/
            audience: [admin-api]
```
Use your identity provider's issuer URL and the audience your tokens carry, then run `pskit validate` again."""),

    A(493, provider="gcp", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      user="Our internal reporting endpoint on GCP must not be public; only our other services (with their own service accounts) should call it. Which auth setting, and what do the callers have to do?",
      steps=[S("search_docs", query="gcp auth iam no public invoker",
               docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="| http | function URL;", end="| http | function URL;")])],
      final="""Use `auth: iam`. With `auth: none` pskit adds an `allUsers` invoker binding; with `auth: iam` it doesn't, so the function isn't public [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

**In code**
```yaml
functions:
  reports:
    handler: app.reports.handler
    events:
      - http: {path: /reports, method: GET, auth: iam}
```

Callers then need:
1. The invoker permission on this function for their service account (grant it in your project, or with `provider.terraform.extra`).
2. A Google ID token for the function's URL, sent as `Authorization: Bearer <token>`.

From another pskit function on GCP, `invoke()` already does this: it calls the target with an ID token from the metadata server.

**In studio**
1. Open **Functions**, click `reports`, and set *Auth* to `iam` in its HTTP trigger.
2. Click **Save**."""),

    A(494, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/providers.md#azure-azure-functions"],
      user="auth: iam possible on azure? like on aws",
      steps=[S("search_docs", query="azure auth iam jwt support",
               docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
             S("search_docs", query="azure limits auth",
               docs=[D("docs/providers.md", "azure-azure-functions", start="**Limits:**")])],
      final="""No. On Azure, `auth: iam` and `auth: jwt` aren't supported; validate reports an error [docs/providers.md#azure-azure-functions].

What works on Azure [docs/events.md#http]:
- `auth: key`: the route needs an Azure function key.
- `auth: none`, with Azure API Management or Easy Auth in front of the Function App, or a token check in your handler.

**In code**
```yaml
functions:
  api:
    handler: app.api.handler
    events:
      - http: {path: /orders, method: GET, auth: key}
```
If the same file also deploys to AWS with `iam`, keep that in a `providers.aws` block and use `key` under `providers.azure`."""),

    A(495, provider="aws", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/providers.md#aws-aws-lambda"],
      user="Error: decomposing request: bufio.Scanner: token too long\n\nterraform apply fails with this since we added pandas. we set artifact_upload: direct to skip the s3 bucket",
      steps=[S("search_docs", query="bufio.Scanner token too long artifact upload",
               docs=[D("docs/providers.md", "aws-aws-lambda", start="**Code upload:**", end="**Code upload:**")]),
             S("search_docs", query="aws options artifact_upload direct artifact_bucket",
               docs=[D("docs/providers.md", "aws-aws-lambda", start="provider:", end="artifact_upload: s3")])],
      final="""That error comes from inline uploads of larger bundles. `artifact_upload: direct` sends the zip inline, which is only for small bundles; with pandas the bundle is too big [docs/providers.md#aws-aws-lambda].

Go back to the default S3 upload. If you can't let pskit create a bucket, use one you already have:

**In code**
```yaml
provider:
  name: aws
  options:
    artifact_upload: s3
    artifact_bucket: my-deploy-bucket
```
Leave out `artifact_bucket` to let pskit create a private `<service>-<stage>-code-*` bucket. The deploying identity needs `s3:PutObject` on `artifact_bucket` (plus `s3:CreateBucket` when pskit creates it).

**In the terminal**
```bash
pskit deploy
```"""),

    A(496, provider="aws", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#aws-aws-lambda", "docs/getting-started.md#6-configure-cloud-credentials"],
      user="We log in to a tooling account and deploy prod into account 111122223333 by assuming a deployer role. We also want a guard so nobody deploys prod into the wrong account by mistake. What options does pskit have?",
      steps=[S("search_docs", query="aws assume role allowed account ids profile",
               docs=[D("docs/providers.md", "aws-aws-lambda", start="provider:", end="allowed_account_ids:")])],
      final="""Use `assume_role_arn` for the deployer role and `allowed_account_ids` as the guard [docs/providers.md#aws-aws-lambda].

**In code**
```yaml
stages:
  prod:
    provider:
      options:
        assume_role_arn: arn:aws:iam::111122223333:role/deployer
        allowed_account_ids: ["111122223333"]
```
`profile` (an AWS CLI profile) can be set the same way if you use a named profile for the tooling account.

**In the terminal**
```bash
aws sso login
pskit doctor -p aws
pskit plan -s prod
```
`plan` uses the assumed role, so you see what would change in the prod account before anyone deploys."""),

    A(497, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#get_secret-secrets-on-every-provider"],
      user="We keep our API secrets in Google Secret Manager. Can get_secret() read from it directly on GCP?",
      steps=[S("search_docs", query="get_secret drivers stores",
               docs=[D("docs/handlers.md", "get_secret-secrets-on-every-provider")])],
      final="""No. `get_secret()` picks its store from `PSKIT_SECRETS_DRIVER`, and the drivers are `vault` (HashiCorp Vault / OpenBao), `aws` (AWS Secrets Manager) and `env` (the default: `PSKIT_SECRET_<NAME>`, then `<NAME>`). There is no Google Secret Manager driver [docs/handlers.md#get_secret-secrets-on-every-provider].

Options on GCP:
1. Use the `env` driver: put the secret in the function's environment and read it with `get_secret("stripe-key")`. Note that environment values are written into Terraform state.
2. Use Vault / OpenBao: set `PSKIT_SECRETS_DRIVER` to `vault`, plus `PSKIT_SECRETS_URL` and `PSKIT_SECRETS_TOKEN`.
3. Call Google Secret Manager yourself with its Python client. That code then only works on GCP.

**In code**
```python
from __future__ import annotations

from py_serverless_kit import get_secret


def handler(event, ctx):
    key = get_secret("stripe-key", default="")
    return {"configured": bool(key)}
```
The handler is the same whichever store you pick."""),

    A(498, provider="azure", stage="dev", mode="ask", page="Setup", persona="terse_expert",
      sources=["docs/cli.md#pskit-doctor"],
      user="command to check this laptop is ready to deploy to azure",
      steps=[S("search_docs", query="doctor check deploy readiness",
               docs=[D("docs/cli.md", "pskit-doctor", end="pskit doctor -p onprem --json")])],
      final="""**In the terminal**
```bash
pskit doctor -p azure
```
It checks Terraform / OpenTofu, Python, the Azure CLI, credentials, the required provider options and optional SDKs, and prints how to fix what's missing on your OS. `✗` means missing (exit code 1), `!` recommended, `i` optional. Nothing is sent anywhere. Add `--json` for the full report [docs/cli.md#pskit-doctor]."""),

    A(499, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types"],
      user="The import workflow gets a list of file names in $.files. For each file the resize function should run, at most 5 at a time, and the results should be stored in $.resized. How do I model that?",
      steps=[S("search_docs", query="workflow map items_path iterator max_concurrency",
               docs=[D("docs/workflows.md", "state-types", end="| `fail` |")])],
      final="""Use a `map` state: `items_path` picks the list, `iterator` runs for each item, `max_concurrency` limits the parallel runs, and the result is a list [docs/workflows.md#state-types].

**In code**
```yaml
workflows:
  import:
    start_at: ResizeAll
    states:
      ResizeAll:
        type: map
        items_path: "$.files"
        max_concurrency: 5
        result_path: "$.resized"
        iterator:
          start_at: Resize
          states:
            Resize: {type: task, function: resize, end: true}
        end: true
```
Each `resize` call gets one file name in `event.data`.

**In studio**
1. Open **Workflows**, open `import` and add a state of type *Run steps for every item in a list* (map).
2. Set *Items path* to `$.files`, *Max concurrency* to 5 and *Result path* to `$.resized`.
3. Open *Steps per item*, add a task that calls `resize`, and click **Save**.

**In the terminal**
```bash
pskit workflow run import -i '{"files": ["a.png", "b.png"]}' --history
```"""),

    A(500, provider="aws", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/workflows.md#choice-rules"],
      user="yaml only: choice state, go to AskEmail when email missing or null, else Continue",
      steps=[S("search_docs", query="choice rules or is_present is_null default",
               docs=[D("docs/workflows.md", "choice-rules", end="| `and`, `or`, `not` |")])],
      final="""**In code**
```yaml
workflows:
  signup:
    start_at: CheckEmail
    states:
      CheckEmail:
        type: choice
        choices:
          - or: [{variable: "$.email", is_present: false}, {variable: "$.email", is_null: true}]
            next: AskEmail
        default: Continue
      AskEmail: {type: task, function: ask-email, end: true}
      Continue: {type: task, function: create-user, end: true}
```
`or` combines the two checks; `default` is taken when no rule matches [docs/workflows.md#choice-rules]."""),

    A(501, provider="azure", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#embedded-orchestrator", "docs/troubleshooting.md#security-notes"],
      user="Security review question: our payout workflow runs on Azure with the default engine. Is there any public URL that can start it, and how do we close it?",
      steps=[S("search_docs", query="embedded orchestrator public route http false",
               docs=[D("docs/workflows.md", "embedded-orchestrator", start="- Invoke it with `POST /workflows/<workflow>`", end="- Invoke it with `POST /workflows/<workflow>`"),
                     D("docs/workflows.md", "embedded-orchestrator", start="- The HTTP route is public")])],
      final="""Yes. On Azure the default engine is the embedded orchestrator, an extra function `payout-orchestrator` with a `POST /workflows/payout` route. That route is public when the provider's HTTP is public [docs/workflows.md#embedded-orchestrator].

Close it with `options.http: false`:

**In code**
```yaml
workflows:
  payout:
    options:
      http: false
    start_at: Pay
    states:
      Pay: {type: task, function: pay, end: true}
```
The orchestrator keeps running; it just has no HTTP trigger. Start runs by invoking it directly instead.

**In the terminal**
```bash
pskit validate -s prod
pskit plan -s prod
```
The plan should show the route being removed."""),

    A(502, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#data-flow"],
      user="in my workflow the charge step returns the payment and then the order data is gone in the next step. how keep both?",
      steps=[S("search_docs", query="workflow result_path keep input",
               docs=[D("docs/workflows.md", "data-flow")])],
      final="""By default `result_path` is `$`, so the task's result replaces all the data. Set `result_path: "$.payment"` to store the result under that key and keep the rest [docs/workflows.md#data-flow].

**In code**
```yaml
workflows:
  orders:
    start_at: Charge
    states:
      Charge: {type: task, function: charge, result_path: "$.payment", next: Ship}
      Ship: {type: task, function: ship, end: true}
```
`ship` then gets the order plus `payment`. `result_path: null` throws the result away and passes the input on.

**In studio**
1. Open **Workflows**, open the workflow and click the `Charge` state.
2. Set *Result path* to `$.payment` and click **Save**.

**In the terminal**
```bash
pskit workflow run orders -i '{"id": 1, "amount": 20}' --history
```"""),

    A(503, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#state-types"],
      user="i want to send email and sms at the same time in my workflow, then continue. is it possible?",
      steps=[S("search_docs", query="parallel branches workflow",
               docs=[D("docs/workflows.md", "state-types", start="| `parallel` |", end="| `parallel` |")])],
      final="""Yes, use a `parallel` state. Each branch is a small workflow of its own, the branches run at the same time, and the result is a list with one item per branch [docs/workflows.md#state-types].

**In code**
```yaml
workflows:
  notify:
    start_at: SendBoth
    states:
      SendBoth:
        type: parallel
        branches:
          - {start_at: Email, states: {Email: {type: task, function: send-email, end: true}}}
          - {start_at: Sms, states: {Sms: {type: task, function: send-sms, end: true}}}
        result_path: "$.sent"
        next: Done
      Done: {type: succeed}
```

**In studio**
1. Open **Workflows**, open the workflow and add a state of type *Run branches at the same time*.
2. Open each branch and add a task (`send-email`, `send-sms`).
3. Connect it to the next state and click **Save**.

**In the terminal**
```bash
pskit workflow run notify -i '{"user": 1}' --history
```"""),

    A(504, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#switch-something-off-on-one-cloud", "docs/studio.md#setup-logs-and-provider-differences"],
      user="We deploy the same project to AWS and GCP. The legacy-sync function only makes sense on AWS. How do I keep it in the file but not deploy it to GCP?",
      steps=[S("search_docs", query="disable function on one provider enabled false",
               docs=[D("docs/configuration.md", "switch-something-off-on-one-cloud")])],
      final="""Disable it only for GCP with `enabled: false` under `providers.gcp`. `pskit validate` reports disabled functions as warnings [docs/configuration.md#switch-something-off-on-one-cloud].

**In studio**
1. Select gcp in the top bar and open **Functions**.
2. On `legacy-sync`, change ● Enabled to ◐ Disabled on Google Cloud Functions.
3. Click **Save**. Studio writes the `providers.gcp` override for you.

**In code**
```yaml
providers:
  gcp:
    functions:
      legacy-sync: {enabled: false}
```

**In the terminal**
```bash
pskit validate -p gcp
pskit validate -p aws
```
If a workflow calls `legacy-sync`, disable that workflow on GCP too; otherwise validation fails."""),

    A(505, provider="azure", stage="dev", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/configuration.md#switch-something-off-on-one-cloud"],
      user="ERROR: workflow 'nightly' calls function 'export', which is disabled; disable the workflow too\n\ni only disabled export for azure",
      steps=[S("search_docs", query="workflow calls disabled function",
               docs=[D("docs/configuration.md", "switch-something-off-on-one-cloud", start="Disabled functions and workflows are reported")])],
      final="""A workflow that calls a disabled function is an error, because it couldn't run [docs/configuration.md#switch-something-off-on-one-cloud]. Disable `nightly` on Azure as well:

**In code**
```yaml
providers:
  azure:
    functions:
      export: {enabled: false}
    workflows:
      nightly: {enabled: false}
```

**In studio**
1. Open **Workflows** with azure in the top bar.
2. Set `nightly` to ◐ Disabled on Azure Functions and click **Save**.

Both stay deployed on the other providers."""),

    A(506, provider="aws", stage="staging", mode="auto", page="none", persona="terse_expert",
      sources=["docs/cli.md#pskit-info"],
      user="CI needs the deployed staging endpoint as JSON. which command",
      steps=[S("search_docs", query="info json endpoint deployed",
               docs=[D("docs/cli.md", "pskit-info")])],
      final="""**In the terminal**
```bash
pskit info -s staging --json
```
It prints the machine-readable record of the deployed functions, triggers, URLs and resource ids. Add `--refresh` to re-read `terraform output` instead of the saved record [docs/cli.md#pskit-info]."""),

    A(507, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/cli.md#pskit-dashboard", "docs/getting-started.md#7-deploy"],
      user="is there a page that shows all my deployed stages and their urls together?",
      steps=[S("search_docs", query="dashboard html overview deployments",
               docs=[D("docs/cli.md", "pskit-dashboard", end="| `--open` |")])],
      final="""Yes, the pskit dashboard. It's an HTML page built from every `.pskit/*/deployment.json`, so it shows each provider/stage you deployed from this project [docs/cli.md#pskit-dashboard].

**In the terminal**
```bash
pskit dashboard --open
```
It writes `.pskit/dashboard/index.html` and opens it. `pskit deploy` regenerates it after each deploy. For one stage in the terminal, `pskit info -s dev` lists the functions and URLs."""),

    A(508, provider="azure", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#package"],
      user="my project folder have big csv test data and notebooks. they go to azure too? how to keep them out",
      steps=[S("search_docs", query="package exclude globs default excludes",
               docs=[D("docs/configuration.md", "package", end="| `vendor` |"),
                     D("docs/configuration.md", "package", start="Always excluded:", end="Always excluded:")])],
      final="""Yes, everything under `package.source` is bundled unless it's excluded. `tests/**`, `.venv/**`, `.env` and a few others are always excluded, but CSV files and notebooks are not [docs/configuration.md#package].

**In code**
```yaml
package:
  exclude: ["data/**", "**/*.csv", "**/*.ipynb"]
```
`exclude` is added to the default excludes; globs are gitignore-style.

**In studio**
1. Open **Overview & provider** and find *Packaging*.
2. Add the patterns under *Exclude globs* and click **Save**.

**In the terminal**
```bash
pskit package
```
Then check `.pskit/azure-dev/artifact.zip` to see what's inside."""),

    A(509, provider="aws", stage="dev", mode="ask", page="Deploy", persona="aws_migrator",
      sources=["docs/events.md#storage", "docs/cli.md#pskit-tf----args"],
      user="I created the S3 bucket uploads-acme by hand last year. Now the storage trigger in pskit should use it. Do I import it, or what?",
      steps=[S("search_docs", query="storage existing bucket",
               docs=[D("docs/events.md", "storage", end="suffix: .csv")]),
             S("search_docs", query="terraform import existing resource pskit tf",
               docs=[D("docs/cli.md", "pskit-tf----args")])],
      final="""Two ways:

1. **Use it as is (simplest):** `existing: true` tells pskit the bucket already exists, so it adds the trigger and never creates or deletes the bucket [docs/events.md#storage].
```yaml
functions:
  on-upload:
    handler: app.uploads.handle
    events:
      - storage: {bucket: uploads-acme, existing: true}
```

2. **Let pskit manage it:** leave `existing` off, run `pskit package` to generate the workspace, then import the bucket into the Terraform state [docs/cli.md#pskit-tf----args]:
```bash
pskit package
pskit tf -- state list
pskit tf -- import <resource address> uploads-acme
```
Take the address of the bucket resource from `.pskit/aws-dev/main.tf.json`. After this, `pskit remove` would delete the bucket, so choose option 1 if the bucket must outlive this service."""),

    A(510, provider="gcp", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/cli.md#pskit-providers"],
      user="which gcp regions and python versions i can pick? where to see",
      steps=[S("search_docs", query="providers json regions runtimes",
               docs=[D("docs/cli.md", "pskit-providers")])],
      final="""Run:
```bash
pskit providers --json
```
For each provider it lists the regions, runtimes, max timeout, Terraform provider and notes [docs/cli.md#pskit-providers]. For GCP the runtimes are Python 3.9–3.13 and Node.js 18, 20, 22.

In studio, **Overview & provider** shows the *Region* and *Runtime* fields for the selected provider."""),
]
