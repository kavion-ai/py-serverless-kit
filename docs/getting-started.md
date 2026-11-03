# Getting started

## 1. Install

```bash
pip install py-serverless-kit          # CLI: `pskit` (alias: `py-serverless-kit`)
pip install "py-serverless-kit[aws]"   # optional: boto3, needed for invoke() on AWS
```

Requirements:

- **Python ≥ 3.9** for the CLI.
- **Terraform ≥ 1.5** (<https://developer.hashicorp.com/terraform/install>) or **OpenTofu**. pskit finds `terraform` or `tofu` on `PATH`; to use a specific binary, set `PSKIT_TERRAFORM_BIN` or `provider.terraform.binary`.
- Credentials for the cloud you deploy to (see [step 6](#6-configure-cloud-credentials)).

You don't need Terraform or credentials for local development, `pskit validate` or `pskit package`.

`pskit doctor -p <provider>` checks all of this (and the cloud's CLI, required provider options, and SSH / Docker for
on-premises) and prints install steps and links for your OS.

## 2. Scaffold a project

```bash
pskit init my-api --provider aws --template http   # templates: http | events | workflow | full
cd my-api
```

```
my-api/
  pskit.yml               # service, provider and function definitions
  app/__init__.py
  app/handlers.py         # your code - cloud agnostic
  requirements.txt        # runtime dependencies of your functions
  tests/test_handlers.py  # example test using LocalRunner
  .gitignore
```

## 3. Write a handler

A handler is any function that takes `(event, ctx)` or just `(event)`:

```python
# app/handlers.py
from py_serverless_kit import Context, Event, NotFound, Response


def hello(event: Event, ctx: Context):
    name = event.http.query.get("name", "world")
    ctx.logger.info("saying hello", extra={"who": name})
    return {"message": f"Hello, {name}!"}          # dict -> JSON 200


def get_item(event: Event, ctx: Context):
    item_id = event.http.path_params["id"]
    if item_id != "1":
        raise NotFound(f"item {item_id} not found")   # -> JSON 404
    return Response.json({"id": item_id}, status=200)
```

Wire them up in `pskit.yml`:

```yaml
service: my-api
provider:
  name: aws
  region: us-east-1
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
  get-item:
    handler: app.handlers.get_item
    events:
      - http: GET /items/{id}
```

See the [handler API](handlers.md) and the [configuration reference](configuration.md).

## 4. Run locally

```bash
pskit dev                                    # http://127.0.0.1:3000, hot reload
curl "http://127.0.0.1:3000/hello?name=Ada"

pskit invoke -f hello --path "/hello?name=Ada"
pskit invoke -f get-item --path /items/1
```

More in [local development](local-development.md).

## 5. Validate

```bash
pskit validate            # schema + provider capability checks
pskit package --skip-deps # build artifact + .pskit/aws-dev/main.tf.json without touching the cloud
```

## 6. Configure cloud credentials

pskit runs Terraform, so credentials come from each Terraform provider's standard sources. Set them up for the cloud you deploy to:

| Provider | Quickest setup |
|---|---|
| `aws` | `aws configure` or `aws sso login`, or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_PROFILE`. Optional `options.profile` / `options.assume_role_arn` |
| `gcp` | `gcloud auth application-default login`, or `GOOGLE_APPLICATION_CREDENTIALS=key.json`. `options.project` is required |
| `azure` | `az login` and `ARM_SUBSCRIPTION_ID` (or `options.subscription_id`). Service principals: `ARM_CLIENT_ID` / `ARM_CLIENT_SECRET` / `ARM_TENANT_ID` |
| `alibaba` | `ALICLOUD_ACCESS_KEY` / `ALICLOUD_SECRET_KEY`, or an `aliyun` CLI profile via `options.profile` |
| `oracle` | `~/.oci/config` (`oci setup config`). Optional `options.config_file_profile`. Docker is needed if you use `options.image_repository` |
| `ibm` | `IC_API_KEY` |
| `digitalocean` | `doctl auth init` (doctl must be on `PATH`). `options.namespace` is required |
| `tencent` | `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`, or `options.profile` |
| `huawei` | `HW_ACCESS_KEY` / `HW_SECRET_KEY` (+ `HW_REGION_NAME`), or `options.profile` |
| `cloudflare` | `CLOUDFLARE_API_TOKEN`. `options.account_id` is required |
| `onprem` | local: nothing to configure (the Python that runs `pskit` starts the host). Remote: OpenSSH and `options.deploy.method: ssh` (or `scp`) with an optional `.pem`, or Docker with `method: docker`, `host`, and a `.pem`. `pskit deploy` asks for the `.pem` on a terminal. The image is built locally, Docker is installed on the server when it is missing, and deploy waits until `/__pskit/health` answers. Servers without Python: `python: bundle` or Docker |

Provider-specific required options are listed in [providers.md](providers.md).

## 7. Deploy

```bash
pskit deploy                     # package -> terraform init -> terraform apply
pskit deploy --stage prod        # another stage = a separate copy of every resource
pskit deploy --confirm           # show the plan, apply that plan (no -auto-approve)
```

After deploying, pskit prints endpoints and resource ids, writes `.pskit/<provider>-<stage>/deployment.json`, and regenerates the [dashboard](dashboard.md).

```bash
pskit info              # what is deployed (from the last deploy)
pskit info --refresh    # re-read terraform outputs
pskit dashboard --open  # HTML overview of every provider/stage
```

> Terraform state is stored locally in `.pskit/<provider>-<stage>/` by default. For team use, configure a remote backend (`provider.state`); see [configuration.md](configuration.md#state-remote-terraform-backend).

## 8. Switch cloud

The code doesn't change. Pick one of three ways:

```bash
pskit deploy --provider gcp           # 1. override on the command line
```

```yaml
# 2. per-provider overrides in the same pskit.yml, selected with --provider
providers:
  gcp:
    region: europe-west1
    options: {project: my-gcp-project}
```

```yaml
# 3. a small file per cloud
# pskit.gcp.yml
extends: pskit.yml
provider:
  name: gcp
  region: europe-west1
  options: {project: my-gcp-project}
```

```bash
pskit deploy -c pskit.gcp.yml
```

Check what the target cloud supports first with `pskit providers` and `pskit validate --provider gcp`. A full example is [`examples/08-multi-cloud`](../examples/08-multi-cloud).

## 9. Remove

```bash
pskit remove            # asks for confirmation; -y to skip
pskit remove --stage prod -y
```

## Next

- [Events](events.md): queues, schedules, storage and topics.
- [Workflows](workflows.md): Step Functions-style state machines that also run on other clouds.
- [Examples](../examples/README.md)
