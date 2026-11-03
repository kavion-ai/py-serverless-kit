"""Category A (docs Q&A and how-to), batch 39: aws / gcp / azure. Provider options and implementation details
(allowed accounts, layers, artifact bucket, EventBridge Scheduler, profiles, Application Insights, Set-Cookie on
Azure, {path+} on Azure) and troubleshooting (Windows long paths, unresolved env variables, precedence and lists,
state on another machine, cold starts, {path+} placement, CORS credentials, public embedded workflow routes,
public buckets, missing Terraform, public routes, trailing slashes). Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


PV = "docs/providers.md"
TS = "docs/troubleshooting.md"

CONVERSATIONS = [
    A(751, provider="aws", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{PV}#aws-aws-lambda"],
      user="People switch AWS profiles a lot here. How can I make sure a prod deploy can only ever go to account 123456789012?",
      steps=[S("search_docs", query="aws allowed account ids option",
               docs=[D(PV, "aws-aws-lambda", start="**Options**", end="**Resources:**")])],
      final="""Set `options.allowed_account_ids` for prod; pskit passes it to the Terraform AWS provider block, so a deploy with credentials for another account stops instead of applying [docs/providers.md#aws-aws-lambda].

**In code**
```yaml
stages:
  prod:
    provider:
      options:
        allowed_account_ids: ["123456789012"]
```

**In the terminal**
```bash
aws sts get-caller-identity
pskit plan -s prod
```
You can also pin the profile with `options.profile`, but `allowed_account_ids` is the safety net."""),

    A(752, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{PV}#aws-aws-lambda"],
      user="We have a Lambda layer with shared deps (arn:aws:lambda:eu-west-1:123456789012:layer:deps:3). How do I attach it to the api function?",
      steps=[S("search_docs", query="lambda layers function options",
               docs=[D(PV, "aws-aws-lambda", start="**Options**", end="**Resources:**")])],
      final="""Put it in `functions.<fn>.options`, which is merged into `aws_lambda_function` [docs/providers.md#aws-aws-lambda].

**In code**
```yaml
functions:
  api:
    handler: app.api.handler
    options:
      layers: ["arn:aws:lambda:eu-west-1:123456789012:layer:deps:3"]
```

**In studio**
1. Open **Functions** and click `api`.
2. Under *Provider-specific options*, add `layers` with the ARN list, then click **Save**."""),

    A(753, provider="aws", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{PV}#aws-aws-lambda"],
      user="Our org's policies don't let deploy roles create S3 buckets. The first deploy fails creating the code bucket. Is there a way around it?",
      steps=[S("search_docs", query="aws code upload bucket artifact_bucket permissions",
               docs=[D(PV, "aws-aws-lambda", start="**Code upload:**", end="(or just `PutObject` on `artifact_bucket`).")])],
      final="""Yes. Point pskit at an existing bucket with `options.artifact_bucket`; then the deploying identity only needs `PutObject` on it [docs/providers.md#aws-aws-lambda].

**In code**
```yaml
provider:
  name: aws
  options:
    artifact_bucket: acme-deploy-artifacts
```

**In studio**
1. Open **Overview & provider**.
2. Fill in *Artifact bucket* and click **Save**.

There's also `artifact_upload: direct` (inline zip), but only for small bundles; larger ones hit the 50 MB inline limit."""),

    A(754, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=[f"{PV}#aws-aws-lambda"],
      user="schedules on aws: eventbridge rules or scheduler? timezone ok?",
      steps=[S("search_docs", query="aws schedule implementation eventbridge",
               docs=[D(PV, "aws-aws-lambda", start="| Trigger | Implementation |", end="| schedule |")])],
      final="""EventBridge Scheduler (`aws_scheduler_schedule`), which supports `timezone` [docs/providers.md#aws-aws-lambda].

```yaml
- schedule: {cron: "30 8 * * 1-5", timezone: Europe/Berlin}
```"""),

    A(755, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{TS}#installation-and-tooling"],
      user="[WinError 206] The filename or extension is too long\n\npskit package on my windows laptop, gcp project",
      steps=[S("search_docs", query="windows path too long WinError 206",
               docs=[D(TS, "installation-and-tooling", start="**Paths too long on Windows**", end="Or keep the project in a short path")])],
      final="""Windows hits its path-length limit while pskit copies the bundle into nested folders [docs/troubleshooting.md#installation-and-tooling].

Fix one of these ways:
1. Enable long paths system-wide (PowerShell as administrator):
```powershell
New-ItemProperty -Path HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
```
2. For git: `git config --system core.longpaths true`.
3. Or move the project to a short path such as `C:\\src\\app`.

Then run `pskit package` again."""),

    A(756, provider="azure", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=[f"{PV}#azure-azure-functions"],
      user="i dont want application insights for dev on azure. can turn off?",
      steps=[S("search_docs", query="azure application insights option",
               docs=[D(PV, "azure-azure-functions", start="```yaml", end="One **Linux Consumption Function App**")])],
      final="""Yes: `options.app_insights` (default `true`) [docs/providers.md#azure-azure-functions].

**In code**
```yaml
stages:
  dev:
    provider:
      options:
        app_insights: false
```

**In studio**
1. Pick stage dev, open **Overview & provider**.
2. Turn off *Application Insights* and click **Save**."""),

    A(757, provider="azure", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=[f"{PV}#azure-azure-functions"],
      user="Our login handler sets two cookies (session and csrf). On AWS both arrive; on Azure the browser only gets one. Why?",
      steps=[S("search_docs", query="azure several set-cookie headers",
               docs=[D(PV, "azure-azure-functions", start="- **Node.js:**", end="Several `Set-Cookie` headers are all kept (Python keeps only the last)")])],
      final="""On Azure, a Python handler keeps only the **last** `Set-Cookie` header; the Node.js runtime keeps them all [docs/providers.md#azure-azure-functions].

Options on Azure with Python:
1. Use one cookie that carries both values (for example a signed session cookie that contains the CSRF token).
2. Send the CSRF token in the response body or a custom header instead of a cookie.
3. Or write this service in Node.js, where several cookies work."""),

    A(758, provider="azure", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=[f"{PV}#azure-azure-functions"],
      user="catch-all /files/{path+} on azure works? or need {*path}",
      steps=[S("search_docs", query="azure path plus catch all route",
               docs=[D(PV, "azure-azure-functions", start="One **Linux Consumption Function App**", end="`{path+}` becomes Azure's `{*path}`.")])],
      final="""Write `{path+}` as usual; pskit turns it into Azure's `{*path}`. `routePrefix` is empty, so the path is served exactly as written, without `/api` [docs/providers.md#azure-azure-functions].

```yaml
- http: {method: ANY, path: "/files/{path+}"}
```
Read it with `event.http.path_params["path"]`."""),

    A(759, provider="gcp", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=[f"{TS}#configuration"],
      user="Error: unresolved variables: env:GCP_REGION\n\non my colleague's laptop. on mine it works",
      steps=[S("search_docs", query="unresolved variables env default",
               docs=[D(TS, "configuration", start="**`unresolved variables: env:FOO`**", end="Set the variable, or give a default")])],
      final="""`${env:GCP_REGION}` is set on your machine but not on your colleague's. Set it there, or give a default [docs/troubleshooting.md#configuration]:

**In code**
```yaml
provider:
  region: ${env:GCP_REGION, europe-west1}
```

**In the terminal**
```bash
export GCP_REGION=europe-west1
pskit validate -p gcp
```"""),

    A(760, provider="azure", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{TS}#configuration", "docs/configuration.md#precedence-later-wins"],
      user="Our pskit.azure.yml extends pskit.yml and adds one entry to a list of CORS origins. After merging only the child's single origin is left. Is that expected?",
      steps=[S("search_docs", query="extends child parent list merge",
               docs=[D(TS, "configuration", start="**Values from a parent file win over my child file**")])],
      final="""Yes. Lists **replace** rather than merge [docs/troubleshooting.md#configuration]. Child values win, so the child's one-item list replaces the parent's list.

Fix: repeat the full list in the child file:
```yaml
# pskit.azure.yml
extends: pskit.yml
functions:
  api:
    events:
      - http:
          path: /orders
          method: GET
          cors:
            origins: [https://shop.example.com, https://admin.example.com]
```
`events` is a list too, so the child's `events` replaces the parent's. Check the result in **YAML** or with `pskit validate -c pskit.azure.yml`."""),

    A(761, provider="aws", stage="staging", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{TS}#deploy-and-state"],
      user="Error: creating SQS Queue (orders-staging-jobs): QueueAlreadyExists\n\na teammate deployed staging from his laptop last week, now i deploy from mine",
      steps=[S("search_docs", query="resource already exists another machine state",
               docs=[D(TS, "deploy-and-state", end="**Changed nothing but Terraform wants to update the function**")])],
      final="""The default Terraform state lives in `.pskit/` on one machine, so your laptop doesn't know what your teammate created [docs/troubleshooting.md#deploy-and-state].

Fix: share the state with a remote backend.
1. Configure `provider.state` with a remote backend (S3 with a DynamoDB lock on AWS).
2. Whoever has the current state (your teammate) migrates it:
```bash
pskit tf -s staging -- init -migrate-state
```
3. Then everyone deploys against the shared state."""),

    A(762, provider="gcp", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=[f"{TS}#http"],
      user="first request to my gcp function after some time is very slow. what can i do with pskit?",
      steps=[S("search_docs", query="cold starts slow first request",
               docs=[D(TS, "http", start="**Cold starts**")])],
      final="""That's a cold start. What helps [docs/troubleshooting.md#http]:

1. Keep the bundle small: exclude data files (`package.exclude`) and avoid heavy imports at module level.
2. Increase memory (more CPU on most clouds):
```yaml
functions:
  api:
    handler: app.api.handle
    memory: 1024
```
3. Provider settings pskit doesn't model can go through `functions.<fn>.options`.

In studio: **Functions** → `api` → *Memory (MB)*, then **Save**."""),

    A(763, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{TS}#http"],
      user="404 from pskit dev for /files/a/b/meta. my route is GET /files/{path+}/meta",
      steps=[S("search_docs", query="path plus template last segment 404 locally",
               docs=[D(TS, "http", start="**404 locally but works in the cloud", end="(last segment only).")])],
      final="""`{path+}` is only allowed as the **last** segment [docs/troubleshooting.md#http], so `/files/{path+}/meta` can't match.

Options:
1. Put the fixed part first: `GET /meta/{path+}`.
2. Or use `GET /files/{path+}` and check in the handler whether `event.http.path_params["path"]` ends with `/meta`.

`pskit dev` prints the route list at startup; compare with it."""),

    A(764, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=[f"{TS}#http"],
      user="Our route has cors with allow_credentials: true and no origins. A security reviewer says any site can now call it with cookies. Is that right?",
      steps=[S("search_docs", query="cors allow credentials echoes origin",
               docs=[D(TS, "http", start="**CORS errors in the browser**", end="Preflights are answered by the runtime")])],
      final="""Yes. With `allow_credentials: true` the runtime echoes the request's `Origin` instead of `*`, so list explicit `origins` to restrict who may call [docs/troubleshooting.md#http].

**In code**
```yaml
- http:
    path: /account
    method: GET
    cors:
      origins: [https://app.example.com]
      allow_credentials: true
```

**In studio**
1. **Functions** → the function → its HTTP trigger → CORS.
2. Enter the allowed origins and click **Save**."""),

    A(765, provider="aws", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{TS}#security-notes"],
      user="One workflow uses engine: embedded on AWS. Does that create a public URL anyone could POST to?",
      steps=[S("search_docs", query="embedded orchestrator public route workflows",
               docs=[D(TS, "security-notes", start="- `auth: none` routes are public.", end="- `auth: none` routes are public.")])],
      final="""Yes. Embedded workflow orchestrators get a public `POST /workflows/<name>` route unless you set `options.http: false` [docs/troubleshooting.md#security-notes].

**In code**
```yaml
workflows:
  order-pipeline:
    engine: embedded
    options:
      http: false
```
Then start it from your code with `invoke()` or from the terminal. With the default `engine: auto`, AWS uses Step Functions instead, which has no such route."""),

    A(766, provider="aws", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{TS}#security-notes", "docs/configuration.md#escape-hatches"],
      user="can i make the s3 bucket pskit create public, for images on my website?",
      steps=[S("search_docs", query="aws created bucket public access",
               docs=[D(TS, "security-notes", start="- Created AWS buckets block public access.", end="- Created AWS buckets block public access.")])],
      final="""Not through pskit's managed bucket: buckets pskit creates on AWS block public access [docs/troubleshooting.md#security-notes].

Alternatives:
1. Serve the images through a function: `GET /images/{name}` that reads from the bucket and returns `Response.binary(data, "image/png")`.
2. Or define your own bucket and its policy as raw Terraform in `provider.terraform.extra`, outside pskit's managed resources."""),

    A(767, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{TS}#installation-and-tooling"],
      user="Error: Neither terraform nor tofu was found on PATH",
      steps=[S("search_docs", query="terraform not found on PATH",
               docs=[D(TS, "installation-and-tooling", start="**`Neither terraform nor tofu was found on PATH`**", end="point `PSKIT_TERRAFORM_BIN`")])],
      final="""pskit needs Terraform (≥ 1.5) or OpenTofu to deploy [docs/troubleshooting.md#installation-and-tooling].

**In the terminal**
```bash
pskit doctor -p gcp
```
It shows the install steps for your OS. If it's installed somewhere else, point pskit at it:
```bash
export PSKIT_TERRAFORM_BIN=/opt/terraform/terraform
```
or set `provider.terraform.binary`. `validate`, `invoke` and `dev` work without Terraform.

**In studio**
1. Open **Setup & credentials**; the Terraform check shows the download link and steps."""),

    A(768, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{TS}#security-notes", "docs/events.md#http"],
      user="my http route has no auth line. is it open for everyone on internet?",
      steps=[S("search_docs", query="auth none routes public",
               docs=[D(TS, "security-notes", start="- `auth: none` routes are public.", end="- `auth: none` routes are public.")]),
             S("search_docs", query="http auth options aws",
               docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")])],
      final="""Yes. Without `auth` the route is `auth: none`, and `auth: none` routes are public [docs/troubleshooting.md#security-notes].

On AWS you can protect it with `auth: iam` or `auth: jwt` (with an `authorizer`) [docs/events.md#http]:
```yaml
- http:
    path: /admin
    method: GET
    auth: iam
```
Or check a token in the handler and raise `Unauthorized`."""),

    A(769, provider="azure", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{TS}#configuration"],
      user="route GET /orders is used by both 'list-orders' and 'orders-admin'\n\nbut admin route is /orders/ with slash!",
      steps=[S("search_docs", query="route used by both trailing slash",
               docs=[D(TS, "configuration", start="**`route GET /x is used by both 'a' and 'b'`**", end="count as the same path")])],
      final="""`/orders` and `/orders/` count as the same path, and each `METHOD /path` may belong to one function only [docs/troubleshooting.md#configuration].

Give the admin route its own path:
```yaml
functions:
  orders-admin:
    handler: app.admin.orders
    events:
      - http: GET /admin/orders
```
Then run `pskit validate -p azure`."""),

    A(770, provider="aws", stage="dev", mode="ask", page="Setup", persona="terse_expert",
      sources=[f"{PV}#aws-aws-lambda"],
      user="pin aws cli profile acme-dev for this project in yml",
      steps=[S("search_docs", query="aws profile option",
               docs=[D(PV, "aws-aws-lambda", start="- **Credentials:**", end="- **Credentials:**")]),
             S("search_docs", query="aws provider options profile",
               docs=[D(PV, "aws-aws-lambda", start="**Options**", end="**Resources:**")])],
      final="""**In code**
```yaml
provider:
  name: aws
  options:
    profile: acme-dev
```
`options.profile` is the AWS CLI profile used for deploys [docs/providers.md#aws-aws-lambda]. Without it, the standard AWS chain applies (`AWS_PROFILE`, env keys, SSO)."""),
]
