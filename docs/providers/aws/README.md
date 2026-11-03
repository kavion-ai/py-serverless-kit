# AWS Lambda provider (`aws`)

Search terms: aws, amazon web services, lambda, aws lambda, api gateway, http api, cloudwatch, aws credentials,
aws configure, aws sso, aws profile, deploy to aws, iam role, us-east-1

The `aws` provider deploys every pskit function as an AWS Lambda function. pskit writes Terraform JSON for the
`hashicorp/aws` plug-in (`>= 5.40`) and runs Terraform. It never calls the AWS API itself during a deploy.

| Fact | Value |
|---|---|
| Tier | **stable** (full trigger set, validated against the real provider plug-in) |
| Default region | `us-east-1` |
| Python runtimes | `python3.9`, `python3.10`, `python3.11`, `python3.12`, `python3.13` (default `python3.12`) |
| Node.js runtimes | `nodejs18`, `nodejs20`, `nodejs22` (Lambda `nodejs18.x` / `nodejs20.x` / `nodejs22.x`) |
| Max timeout | 900 s (an HTTP call is still cut at 30 s by API Gateway) |
| Triggers | `http`, `schedule`, `queue`, `storage`, `topic` |
| Workflows | native: AWS Step Functions |
| Dependencies | pip-installed into the zip as manylinux wheels for `x86_64` or `arm64` |

This page covers credentials, the `provider` block, deploy / info / remove and logs. Triggers, resources, IAM and
workflows are in [triggers-and-resources.md](triggers-and-resources.md).

## Set up AWS credentials for pskit

The AWS provider uses the standard AWS credential chain of the machine that runs `pskit` (or `pskit studio`). Terraform
reads it; pskit only checks that something is there.

1. Install Terraform (or OpenTofu) and the AWS CLI. `pskit doctor -p aws` prints the install commands for your OS.
2. Pick one way to sign in:

   | Way | Commands |
   |---|---|
   | Access key profile | `aws configure` (writes `~/.aws/credentials` and `~/.aws/config`) |
   | AWS IAM Identity Center (SSO) | `aws configure sso`, then `aws sso login --profile <name>` |
   | Environment variables | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`, `AWS_REGION` |
   | Named profile | `AWS_PROFILE=<name>`, or `provider.options.profile` in `pskit.yml` |
   | CI (OIDC) | let the CI job assume a role; Terraform picks up the environment variables it sets |

3. Run the check:

```bash
pskit doctor -p aws
```

`pskit doctor` reports `AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are set`, or a profile found in `~/.aws`. When the
`AWS_PROFILE` profile (or `default`) does not exist it lists the profiles it found. It exits with code 1 when something
required is missing.

4. Optional: `pip install "py-serverless-kit[aws]"` installs `boto3`. `pskit logs`, `pskit trigger`, `pskit resources
send`, **Browse account** in studio and Step Functions executions need it on your machine. Deploys do not.

## Set up AWS credentials in studio

The studio **Setup & credentials** page runs the same checks as `pskit doctor` for the provider you pick.

1. Start studio in the project folder: `pskit studio --open`.
2. In the sidebar, click **Setup & credentials**.
3. In the **Provider** list at the top, pick **AWS Lambda**. Pick your **Operating system** so install steps match it.
4. Read the **Checks** list. Each row shows a status (missing, check, optional or OK). Click **How to fix** on a row to
   see the download link and the commands for your OS.
5. To save an access key: open the **AWS credentials (aws configure)** section, fill **Profile**, **Access key ID**,
   **Secret access key**, optionally **Default region** and **Session token** (only for temporary STS / SSO
   credentials), then click **Save profile**. This writes `~/.aws/credentials` and `~/.aws/config`.
6. To use SSO, click **Sign in (aws sso)** on the credentials check. It runs `aws sso login` and shows its output in a
   **Running: ...** section.
7. To set variables such as `AWS_PROFILE` for this studio session only, use the **Environment variables** section:
   type a value and click **Set for this session**. Nothing is written to disk; the value is gone when studio stops.
8. Click **Check again** at the top until the badge says **ready to deploy to AWS Lambda**.

## Write the AWS provider block in pskit.yml

The `provider` block selects AWS and sets the defaults every function inherits. Only `name` is required.

```yaml
provider:
  name: aws
  region: eu-west-1                # default us-east-1
  stage: dev
  runtime: python3.12              # optional: default python3.12
  memory: 256                      # MB, Lambda memory_size
  timeout: 15                      # seconds, max 900
  architecture: x86_64             # or arm64 (Graviton); also picks the pip wheels
  log_retention_days: 14           # CloudWatch log group retention; null = no log group managed by pskit
  environment:
    LOG_LEVEL: INFO
  tags:
    team: payments                 # added to every resource (default_tags)
  iam:
    statements:                    # extra permissions for the shared Lambda role
      - {actions: ["dynamodb:GetItem"], resources: ["arn:aws:dynamodb:*:*:table/orders"]}
    # role: arn:aws:iam::123456789012:role/existing-lambda-role   # use your own role instead
  options:
    profile: my-profile            # AWS CLI profile Terraform uses
    assume_role_arn: arn:aws:iam::123456789012:role/deployer
    allowed_account_ids: ["123456789012"]
    artifact_bucket: my-deploy-bucket
    artifact_upload: s3            # s3 (default) | direct
```

Every key outside `options` is shared by all providers; see [configuration.md](../../configuration.md#provider).
The `options` keys are AWS-only and are described in the next section.

## AWS provider options reference

The AWS `provider.options` keys change how Terraform signs in and where the code zip goes.

| Option | Default | What it does |
|---|---|---|
| `profile` | none (credential chain) | AWS CLI profile written into the Terraform `provider "aws"` block |
| `assume_role_arn` | none | Terraform assumes this role to deploy (`assume_role { role_arn }`) |
| `allowed_account_ids` | none | list of account ids; Terraform refuses to touch any other account |
| `artifact_bucket` | a new private bucket | existing S3 bucket for the code zip. The deploying identity then needs only `s3:PutObject` there |
| `artifact_upload` | `s3` | `s3`: upload `artifact.zip` once to S3 and point every Lambda at it. `direct`: send the zip inline in each CreateFunction call (only for small bundles). Any other value is a validation error |

With `artifact_upload: s3` and no `artifact_bucket`, pskit creates a private bucket named `<service>-<stage>-code-...`
(public access blocked, `force_destroy: true`) and uploads `artifact-<hash>.zip`. This avoids Lambda's 50 MB inline
limit and the Terraform error `decomposing request: bufio.Scanner: token too long`. The deploying identity needs
`s3:CreateBucket` and `s3:PutObject`.

Per-function escape hatch: `functions.<fn>.options` is merged as-is into that function's `aws_lambda_function`
resource, for example `layers`, `vpc_config` or `tracing_config`:

```yaml
functions:
  api:
    handler: app.api.handler
    options:
      layers: ["arn:aws:lambda:eu-west-1:123456789012:layer:deps:3"]
      vpc_config: {subnet_ids: [subnet-1], security_group_ids: [sg-1]}
```

In studio, **Overview & provider → AWS Lambda options** shows **Artifact bucket**, **Artifact upload** and **Assume
role ARN**. Set `profile` and `allowed_account_ids` on the **YAML** page.

## How pskit maps function settings to Lambda

The AWS provider turns each function's settings into `aws_lambda_function` arguments.

| pskit key | Lambda argument |
|---|---|
| function name | `function_name` = `<service>-<stage>-<function>` (lowercase, max 64 chars, a hash suffix when cut) |
| `handler` | always `pskit_entry.handler` (a generated shim that calls the pskit runtime, which calls your handler) |
| `runtime` | `runtime` (`python3.12`, `nodejs20.x`, ...) |
| `memory` / `timeout` | `memory_size` / `timeout` |
| `architecture` | `architectures` |
| `concurrency` | `reserved_concurrent_executions` |
| `environment` | `environment.variables`, plus `PSKIT_PROVIDER`, `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_REGION`, `PSKIT_FUNCTION`, `PSKIT_HANDLER` and `PSKIT_RESOURCE_*` |
| `tags` | `tags`, plus `pskit-service`, `pskit-stage`, `managed-by: py-serverless-kit` |
| `description` | `description` (first 256 characters) |
| `log_retention_days` | an `aws_cloudwatch_log_group` named `/aws/lambda/<function_name>` |

Functions share one IAM role unless they set their own `iam`. See
[triggers-and-resources.md](triggers-and-resources.md#iam-roles-and-permissions-on-aws).

## Deploy to AWS from the terminal

Deploying to AWS runs `terraform init` and `terraform apply` in `.pskit/aws-<stage>/`.

1. Create a project, or use your own:

```bash
pskit init my-api --provider aws          # -t http | events | workflow | full
cd my-api
```

2. Check the configuration against AWS, without touching the cloud:

```bash
pskit validate                            # or: pskit validate -p aws -s prod
```

3. Optional: build the zip and Terraform only, or see the plan:

```bash
pskit package -s dev                      # writes .pskit/aws-dev/artifact.zip and main.tf.json
pskit plan -s dev                         # terraform plan
```

4. Deploy:

```bash
pskit deploy -s dev                       # -auto-approve
pskit deploy -s prod --confirm            # show the plan and ask before applying
```

5. See what is deployed:

```bash
pskit info -s dev                         # functions, URLs, ids, console links
pskit info -s dev --refresh --json        # re-read the Terraform outputs
```

`--upgrade` runs `terraform init -upgrade`. `--skip-deps` skips the pip install into the bundle (only for tests: the
Lambda then lacks your dependencies). `-r eu-central-1` overrides `provider.region` for one command.

## Deploy to AWS from studio

Deploying to AWS from studio runs the same commands with the credentials of the machine that runs studio.

1. In the sidebar, click **Overview & provider**. In the **Provider** section click the **AWS Lambda** card. If the
   project used another cloud, a dialog lists what won't run on AWS; click **Switch provider** (or **Switch & disable
   on AWS Lambda** / **Switch only (fix later)**).
2. Under **Defaults for every function**, pick the **Region**, **Runtime**, **Memory (MB)**, **Timeout (s)**,
   **Architecture** and **Log retention (days)**. Fill **AWS Lambda options** if you need them.
3. Click **Save** in the top bar (or Ctrl+S).
4. In the top bar, check **validate & deploy as** shows **AWS Lambda** and type the **stage**.
5. In the sidebar, click **Deploy**. Click **Validate**, then **Plan** to preview, then **Deploy**. The live log appears
   under the buttons. A stage whose name starts with `prod` asks you to type `aws/<stage>` to confirm.
6. Click **Info** to print the URLs and ids. **Recent jobs** at the bottom keeps the finished runs.

If `pskit.yml` has unsaved changes, a **Save first?** dialog offers **Save and run** or **Run without saving**.

## Find the AWS URLs, ids and console links

After a deploy, `pskit info` reads the Terraform output `pskit` and prints, per function, the Lambda name (`id`), its
`arn`, the AWS console link and, for HTTP functions, the API base URL.

- **HTTP endpoint:** one API Gateway HTTP API per service, `$default` stage, URL
  `https://<api-id>.execute-api.<region>.amazonaws.com`. Your paths are appended as written, for example
  `https://abc123.execute-api.eu-west-1.amazonaws.com/hello`.
- **Console link:** `https://<region>.console.aws.amazon.com/lambda/home?region=<region>#/functions/<name>`.
- **Workflows:** a Step Functions state machine ARN and console link; embedded workflows show the orchestrator Lambda.
- `.pskit/aws-<stage>/deployment.json` holds the same summary; `pskit dashboard --open` renders it as a page.

## Test a deployed AWS function

pskit can send every AWS trigger type for you with your local credentials (it needs `boto3`).

```bash
pskit trigger --list                                   # how to test every function and trigger
pskit trigger -f hello -e 0 --path '/hello?name=Ada'   # HTTP call
pskit trigger -f worker -e 0 -d '{"order_id": 1}'      # SQS message
pskit trigger -f nightly --direct                      # invoke without the trigger
```

In studio: sidebar **Test** → pick the function and event → **Send to aws / dev**. Turn on **Show the function's logs**
to watch it run. **Run locally** runs the handler on your machine without AWS.

## Read AWS logs with pskit logs and studio

AWS Lambda logs go to CloudWatch Logs groups `/aws/lambda/<function_name>`. `pskit logs` reads them through `boto3`
with your local credentials, so install `pip install "py-serverless-kit[aws]"` first.

```bash
pskit logs -s dev                         # newest 100 entries, last 15 minutes by default
pskit logs -f --function worker           # follow one function
pskit logs --level error -q timeout       # filter by level and text
pskit logs --streams                      # list log streams
pskit logs --delete <stream> --yes        # delete a stream; --delete-all deletes every stream
```

Log streams can be deleted; the log group itself never is, because Terraform owns it. Without `boto3`, `pskit logs`
prints the console link instead.

In studio: sidebar **Logs**. The page reads the provider and stage in the top bar. **Stored logs** lists streams and
deletes the ones you select. If logs can't be read, fix credentials on **Setup & credentials**.

## Remove an AWS deployment

Removing an AWS stage runs `terraform destroy` in `.pskit/aws-<stage>/`.

```bash
pskit remove -s dev                       # asks for confirmation
pskit remove -s dev --yes
pskit remove -s dev --keep-resources      # keep S3 buckets, SQS queues and SNS topics with their data
```

With `--keep-resources`, the managed buckets, queues and topics are taken out of Terraform state first, so they stay in
AWS and pskit stops managing them. `pskit resources list -s dev` shows them; `pskit resources delete --all-kept -s dev`
deletes them later. The code-upload bucket is always destroyed (`force_destroy`).

In studio: **Deploy** page → set the switch under the buttons (**Remove keeps buckets, queues and topics (and their
data)** or **Remove also deletes buckets, queues and topics**) → click **Remove** → type `aws/<stage>` → **Remove**.

## AWS limits and gotchas

The AWS provider rejects or changes these settings:

- `auth: key` is a validation error: API Gateway HTTP APIs have no API keys. Use `auth: iam` or `auth: jwt`.
- `auth: jwt` needs `authorizer.issuer` and `authorizer.audience`.
- API Gateway cuts every HTTP call at 30 s, whatever the function timeout is.
- A cron that restricts both day-of-month and day-of-week is rejected (AWS cron limit).
- `invoke()` between functions calls `lambda:InvokeFunction`, which pskit does not grant. Add an `iam.statements` entry
  (see [triggers-and-resources.md](triggers-and-resources.md#call-another-function-with-invoke-on-aws)).
- Bucket names are global in S3: a `storage` bucket name that someone else owns fails at apply time.
- An existing role in `iam.role` is not changed by pskit; grant it access to bound resources yourself (a warning says so).

## Complete minimal AWS example project

The minimal AWS project below has an HTTP function, a scheduled function and an SQS worker with a dead-letter queue.

```text
hello-aws/
  pskit.yml
  requirements.txt
  app/__init__.py
  app/handlers.py
```

```yaml
service: hello-aws

provider:
  name: aws
  region: eu-west-1
  stage: dev
  memory: 256
  timeout: 15

functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello

  nightly:
    handler: app.handlers.nightly
    events:
      - schedule: {cron: "0 2 * * *", timezone: Europe/Dublin, input: {report: daily}}

  worker:
    handler: app.handlers.worker
    events:
      - queue: {name: hello-aws-jobs, batch_size: 10, dead_letter: hello-aws-jobs-dlq}
```

This config creates 23 Terraform resources: three Lambdas with log groups, the shared role, API Gateway pieces, the
EventBridge Scheduler schedule and its role, two SQS queues, the event source mapping and the code bucket.

## Handler code and commands for the minimal AWS example

The handler file `app/handlers.py` of the minimal AWS example is plain pskit code; the same file runs unchanged on
Azure, GCP and every other provider.

```python
from py_serverless_kit import BatchResult, Context, Event


def hello(event: Event, ctx: Context):
    name = event.http.query.get("name", "world")
    ctx.logger.info("saying hello", extra={"name": name})
    return {"message": f"Hello, {name}!", "provider": event.provider, "stage": ctx.stage}


def nightly(event: Event, ctx: Context):
    ctx.logger.info("nightly run", extra={"input": event.data})
    return {"ok": True}


def worker(event: Event, ctx: Context):
    result = BatchResult()
    for record in event.records:
        try:
            ctx.logger.info("job", extra={"body": record.json()})
        except Exception:
            result.fail(record.id)      # only this message is retried (ReportBatchItemFailures)
    return result
```

```bash
pskit invoke -f hello --path "/hello?name=Ada"     # run locally first
pskit deploy -s dev
pskit info -s dev                                  # prints the API URL; open <URL>/hello?name=Ada
pskit trigger -f hello -e 0 --path "/hello?name=Ada"
pskit remove -s dev --yes
```

## See also

- [triggers-and-resources.md](triggers-and-resources.md): every trigger, resources, IAM, Step Functions
- [AWS resource guides](../../resource-guides/aws/README.md): console walkthroughs for SQS, S3, SNS, RDS, ElastiCache
- [providers.md](../../providers.md#aws-aws-lambda) and [configuration.md](../../configuration.md)
- [events.md](../../events.md), [workflows.md](../../workflows.md), [handlers.md](../../handlers.md)
- [Deploy, remove and info](../../deployment/deploy-remove-info.md), [Logs](../../deployment/logs.md)
- [All providers](../README.md), [Azure](../azure/README.md), [GCP](../gcp/README.md)
