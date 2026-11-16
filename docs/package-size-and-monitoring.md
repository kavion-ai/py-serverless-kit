# Package size, container images, logs & metrics

What pskit checks and shows around a deploy, on every cloud:

1. how big the bundle is compared with the provider's deployment limits;
2. whether the code ships as a **zip** or as a **container image** (Amazon ECR on AWS, Azure Container Registry on
   Azure; more clouds coming soon);
3. every resource the deploy creates, what each one is for, and which ones are optional. That includes the logs and
   metrics services, which you can switch off per function;
4. after the deploy: the functions that could **not** be deployed, and why. One failing function does not stop the
   others.

## 1. Deployment size limits

Each serverless platform caps the size of a zip deployment. After building `artifact.zip`, `pskit package`, `plan`
and `deploy` print the zipped and unzipped size against those caps:

```text
  artifact artifact.zip: 812 files, 61234.5 KiB (262144.0 KiB unzipped), sha256 9c1e...
  NOTE: AWS Lambda: bundle 59.8 MB zipped, 256.0 MB unzipped (unzipped limit 250.0 MB)
  ERROR: the bundle is 256.0 MB unzipped, over AWS Lambda's 250.0 MB limit (AWS Lambda deployment package quotas).
  Deploy it as a container image in Amazon ECR: set `package.type: image` (or `auto`) in pskit.yml, or run with
  `--package-type image`. Smaller zips: `package.exclude` unused files.
```

| Provider | Zip limits pskit checks | Container images |
|---|---|---|
| `aws` | 250 MB unzipped; 50 MB zipped with `options.artifact_upload: direct` (the default `auto` sends zips over 50 MB through S3 instead) | **Amazon ECR**, up to 10 GB |
| `azure` | 1 GB package | **Azure Container Registry (ACR)** |
| `gcp` | 100 MB compressed, 500 MB uncompressed with modules | coming soon (Artifact Registry + Cloud Run) |
| `cloudflare` | 10 MB compressed (Workers Paid; 3 MB on Free) | coming soon (Cloudflare Containers) |
| `alibaba`, `tencent`, `huawei`, `ibm` | not checked | coming soon (each cloud's registry) |
| `oracle` | — | always images (`options.image` / `options.image_repository`) |
| `digitalocean`, `onprem` | not checked | — |

- From **80 %** of a limit you get a warning.
- **Over** a limit, `package` and `plan` report an error note, and `deploy` stops before running Terraform, so it
  never fails halfway through an upload.
- `--skip-deps` builds are smaller than the real bundle; the notes say so.
- `pskit providers` shows an `images` column, and `pskit providers --json` includes `package.limits` in bytes.

## 2. Zip or container image: `package.type`

```yaml
package:
  type: image          # zip (default) | image | auto
  image:               # all optional
    repository: shared/lambdas     # existing ECR repository (AWS) / existing registry name (Azure)
    base_image: public.ecr.aws/lambda/python:3.12   # replace the FROM line
    dockerfile_lines:              # extra instructions, before the code is copied
      - RUN dnf install -y poppler-utils
    keep: 10                       # images kept in a pskit-created ECR repository
    scan_on_push: true             # ECR image scanning
```

| `type` | What happens |
|---|---|
| `zip` | The code ships as `artifact.zip`. This is the default, and the same as before 3.2. |
| `image` | pskit builds a container image from the same bundle with your **local Docker**, pushes it to the cloud's registry and points the functions at it. |
| `auto` | A zip, switching to an image only when the bundle is over a zip limit. On clouds without image support it stays a zip (with a warning). |

Override it for one run with `--package-type zip|image|auto` on `pskit package`, `plan` or `deploy`. The flag applies
to every function. In the studio, choose it in each function's editor (**Package type**, below).

### Per function: `functions.<name>.package_type`

Only one function is big? Ship just that one as an image and keep the others as zips:

```yaml
package:
  type: zip                 # the default for every function
functions:
  api:
    handler: app.api.handler           # zip
  report:
    handler: app.report.build          # pandas + matplotlib: too big for a zip
    package_type: image                # zip | image | auto, for this function only
```

- **AWS:** zip and image functions mix freely. Every image function runs the same image (built once), so only the
  image functions need to share an `architecture` and `runtime`.
- **Azure (and other one-host providers):** one Function App runs every function, so they all ship the same way.
  Different `package_type` values are an error; set `package.type` instead.
- **Clouds without images:** `package_type: image` on a function is an error **for that function only**.
  `pskit deploy` skips it and deploys the others (see [partial deploys](#5-partial-deploys-what-was-not-deployed-and-why)).
- In the studio, each function's editor has **Package type** (inherit / Zip / Image / Auto), with the size limits.
  On Azure, choosing it there sets `package.type` for every function.

### What you need

- **Docker running** where pskit runs. Terraform's `kreuzwerker/docker` provider (4.3.0 or later) builds the image
  and pushes it. It logs in to the registry itself (an ECR token, or the ACR admin login), so no `docker login` is
  needed.
- The image is built **without provenance or SBOM attestations** (`provenance: false`, `sbom: false`). With them,
  BuildKit and Docker Desktop's containerd image store push an OCI image index holding an extra `unknown/unknown`
  manifest, and Lambda rejects it: `The image manifest, config or layer media type for the source image ... is not
  supported`.
- The handler code does not change: the image holds the same bundle (your code, the pskit runtime, the shim and
  the dependencies) as the zip.

### How it is built

After the zip is made, pskit writes `Dockerfile.pskit` and `.dockerignore` into `.pskit/<provider>-<stage>/build/`;
neither file goes into the zip. The image tag is a hash of the bundle and the Dockerfile. An unchanged project
gives the same tag, so nothing is redeployed. To build the image yourself:
`docker build -f Dockerfile.pskit .pskit/aws-dev/build`.

### AWS Lambda + Amazon ECR

- Creates an ECR repository `<service>-<stage>-functions` (`force_delete`, scan on push), plus a lifecycle policy
  keeping the last `package.image.keep` images. `package.image.repository` uses an existing repository instead.
- Builds the image `FROM public.ecr.aws/lambda/python:<version>` (or `nodejs:<version>`) with
  `CMD ["pskit_entry.handler"]`, for the function's architecture (`linux/amd64` or `linux/arm64`).
- Each function gets `package_type = "Image"` and the image pinned **by digest**, so a function always runs exactly
  the image this deploy pushed. Triggers, IAM, API Gateway, schedules and workflows are unchanged.
- One image serves every function, so every function needs the same `architecture` and `runtime` (validation
  checks this). Lambda layers cannot be attached to image functions: put those files in the image with
  `package.image.dockerfile_lines`.

### Azure Functions + Azure Container Registry

- Creates an ACR (`Basic` SKU, admin login on; `provider.options.acr_sku` picks another SKU). To use an existing
  registry, set `package.image.repository` to its name, and `provider.options.acr_resource_group` if it is in
  another resource group. The registry needs admin login enabled.
- Builds the image `FROM mcr.microsoft.com/azure-functions/python:4-python<version>` (or `node:4-node<version>`) and
  installs `requirements.txt` / `package.json` dependencies inside it.
- The Function App runs the container (`site_config.application_stack.docker`). The remote Oryx build is switched
  off, because the dependencies are already in the image.
- **Consumption plans (`Y1`, `FC1`) cannot run custom containers.** With `package.type: image` the plan defaults to
  Elastic Premium `EP1`, which is billed per hour rather than per call; validation warns about this. An explicit
  `plan_sku: Y1` with `type: image` is an error. Any `EP*`, `B*`, `S*` or `P*v3` SKU works.

### Other clouds: coming soon

On GCP, Cloudflare, Alibaba, Tencent, Huawei and IBM, `package.type: image` is a validation error that names what the
image deploy will use there. Until then, keep the bundle under the limits with `package.exclude` and fewer
dependencies.

## 3. Logs & metrics: on by default, off per function

Some providers create logs and metrics services next to your functions. Both are **on by default**. Switch one off
where a function does not need it:

```yaml
provider:
  monitoring: {logs: true, metrics: true}   # default for every function (this is the default anyway)

functions:
  healthcheck:
    handler: app.health.ping
    monitoring: {logs: false}               # this function only
  noisy-poller:
    handler: app.poll.run
    monitoring: false                       # short for {logs: false, metrics: false}
```

A function's value wins over `provider.monitoring`, which wins over the default (on). In the studio, each function
has a **Logs & metrics** section with two switches.

What each switch does on each provider:

| Provider | `logs: false` | `metrics: false` |
|---|---|---|
| `aws` | no CloudWatch log group for the function, and it runs with a role that cannot write CloudWatch Logs (a shared `lambda-nologs` role; queue consumers get an SQS-only policy instead of the managed one, which also grants logs) | no effect: Lambda's CloudWatch metrics are built in and free (warning) |
| `azure` | `host.json` sets the log level of the function's Azure functions to `None`, so nothing is sent to Application Insights | Application Insights and its Log Analytics workspace are shared by the whole Function App, so they are left out only when **every** function has both logs and metrics off (warning otherwise). `options.app_insights: false` still turns them off for the whole app |
| `gcp` | no effect: Cloud Logging is built in (warning) | no effect: Cloud Monitoring is built in (warning) |
| other clouds | no effect: pskit creates no log resources there (warning) | no effect (warning) |

If you give AWS an existing role (`iam.role`), pskit cannot remove its logging permissions. It still skips the log
group and warns you.

## 4. What a deploy creates, described

`pskit package`, `plan` and `deploy` print every Terraform resource grouped by kind, with what it is for and how to
leave out the optional ones. On deploy this happens before `terraform apply`:

```text
  Will create or update 14 resource(s):
    Functions
      aws_lambda_function x2 - Lambda function that runs your handler (api, worker)
    HTTP / API
      aws_apigatewayv2_api x1 - API Gateway HTTP API: the public endpoint of your HTTP routes (http)
      ...
    Access & permissions
      aws_iam_role x2 - execution role the functions (or schedules) run as (lambda, lambda_nologs)
    Logs & metrics
      aws_cloudwatch_log_group x1 - CloudWatch log group of a function, with its retention (logs_api) [optional: monitoring.logs: false]
```

The same list is saved as `.pskit/<provider>-<stage>/resources.json`. In the studio, **Deploy → What a deploy
creates** shows it with a *Refresh* button (it runs `pskit package --skip-deps`), and the Deploy confirmation lists it
before anything is applied. Every resource type of every built-in provider has a description. Types pskit does not
know (from `terraform.extra` or third-party providers) are listed with a generic one, so the list is always complete.

## 5. Partial deploys: what was not deployed, and why

One function that cannot be deployed no longer stops the others. `pskit deploy` deploys everything it can, then
lists what it could not deploy, with the reason, as the **last** thing it prints:

```text
Deployed part (dev) to AWS Lambda us-east-1 (partly)
...
Deployed 2 of 3 function(s). Not deployed (1):
  worker  [terraform apply]
      reason: aws_lambda_function.worker: creating Lambda Function (part-dev-worker): ... Unzipped size must be smaller than 262144000 bytes
      Terraform kept everything that does not depend on it; the failed part is retried on the next deploy
Fix the reasons above and run `pskit deploy` again; the deployed functions are not touched twice.
```

The exit status is **1** when anything was not deployed, so CI still notices.

| When | What counts | What happens to it |
|---|---|---|
| **configuration** (before Terraform) | an error about one function only: `functions.<name>...`, such as an unsupported trigger option, `auth: jwt` on Azure, or `package_type: image` on a cloud without images | skipped: it is left out of the bundle and the Terraform |
| **package size** (before Terraform) | the bundle is over the zip limit for the zip functions while other functions ship as images | the zip functions are skipped; the image functions deploy |
| **terraform apply** | Terraform reports an error on one of the function's resources, or on a resource it needs (found through the dependency graph of `main.tf.json`) | Terraform finishes everything that does not depend on it; the failed part is retried on the next deploy |

- **A skipped function keeps what was deployed before.** When something is skipped, pskit applies only the resources
  it rendered (`terraform apply -target=...`), so Terraform does not destroy the skipped function's earlier version.
  It is listed in `deployment.json` with `"status": "not_updated"`. The exception is a provider where one host runs
  every function (Azure Function App, on premises, DigitalOcean): the redeployed host no longer contains it, and the
  report says so.
- Errors shared by every function (a role, the API, the Function App, missing credentials) still fail the deploy:
  `no function was deployed`, with the reasons.
- When every function has a configuration error, nothing is skipped and the errors are reported as before.
- `deployment.json` gets `"status": "partial"` and `not_deployed: {<function>: {step, reason, previous}}`. The
  studio's Deploy page shows it above **What a deploy creates**.
- `pskit deploy --all-or-nothing` keeps the old behaviour: any error stops the deploy before Terraform, and a
  Terraform error is raised as it is.
